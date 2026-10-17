import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull

/**
 * Replay simulator selection observations in a caller-owned immutable evidence snapshot.
 * Runtime/device pins and original cwd are independent caller inputs. Original source,
 * producer, receipt and host authentication, and the complete XCTest binding gate,
 * remain mandatory caller responsibilities. This function invokes no process.
 */
internal fun verifyOriginalAppleSimulatorExecution(
    executionDirectory: File,
    expectedRuntimeName: String,
    expectedDeviceTypeIdentifier: String,
    originalWorkingDirectory: String,
) {
    listOf(expectedRuntimeName, expectedDeviceTypeIdentifier).forEach {
        check(it.isNotBlank() && it == it.trim() && it.none(Char::isISOControl)) {
            "Original simulator caller pin is invalid"
        }
    }
    check(File(originalWorkingDirectory).isAbsolute &&
        File(originalWorkingDirectory).toPath().normalize().toString() == originalWorkingDirectory &&
        originalWorkingDirectory.none(Char::isISOControl)) { "Original simulator caller cwd is invalid" }
    val raw = executionDirectory.resolve("simulator-raw")
    val xctest = executionDirectory.resolve("xctest-raw")
    val report = executionDirectory.resolve("reports/simulator-devices.json")
    val inputs = listOf(raw, xctest, report)
    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "original simulator evidence") }
    check(report.isFile) { "Original simulator ready report is missing" }
    val originalRaw = verifiedRegularFiles(raw).mapValues { (_, file) -> file.releaseDigest() }
    val originalXCTest = verifiedRegularFiles(xctest).mapValues { (_, file) -> file.releaseDigest() }
    val originalReport = report.readBytes()
    try {
        val marker = xctest.resolve("successful-attempt.json")
            .readCanonicalOriginalAppleObject("Original simulator successful attempt")
        check(marker.keys == setOf("schemaVersion", "attempt") && marker.simulatorInteger("schemaVersion") == 1) {
            "Original simulator successful attempt schema changed"
        }
        val successful = marker.simulatorInteger("attempt")
        check(successful in 0..1) { "Original simulator successful attempt is invalid" }
        val expectedFiles = mutableSetOf<String>()
        val listDevices = listOf("/usr/bin/xcrun", "simctl", "list", "-j", "devices", "available")

        (0..successful).forEach { attempt ->
            val prefix = "attempt-$attempt"
            fun process(name: String, command: List<String>, requireSuccess: Boolean): Int? {
                listOf("execution.json", "stdout.bin", "stderr.bin").forEach { expectedFiles += "$prefix/$name/$it" }
                val execution = raw.verifyOriginalAppleProcess("$prefix/$name", requireSuccess)
                check(execution.simulatorInteger("schemaVersion") == 1 && execution.releaseCommand() == command &&
                    (execution["workingDirectory"] === JsonNull ||
                        execution.releaseWorkingDirectory() == originalWorkingDirectory)) {
                    "Original simulator command or caller cwd changed: $prefix/$name"
                }
                return execution.releaseExitCodeOrNull()
            }
            process("runtimes", listOf("/usr/bin/xcrun", "simctl", "list", "-j", "runtimes"), true)
            process("devices", listDevices, true)
            val selected = selectSimulator(
                raw.resolve("$prefix/runtimes/stdout.bin").readSimulatorListing(runtimes = true),
                raw.resolve("$prefix/devices/stdout.bin").readSimulatorListing(selection = true),
                expectedRuntimeName, expectedDeviceTypeIdentifier,
            )
            val commands = linkedMapOf<String, List<String>>()
            if (selected.state != "Booted") {
                commands["boot"] = listOf("/usr/bin/xcrun", "simctl", "boot", selected.udid)
            }
            commands["bootstatus"] = listOf("/usr/bin/xcrun", "simctl", "bootstatus", selected.udid, "-b")
            commands["ready-devices"] = listDevices
            val observed = commands.keys.filter { name -> originalRaw.keys.any { it.startsWith("$prefix/$name/") } }
            check(observed == commands.keys.take(observed.size) &&
                (attempt != successful || observed == commands.keys.toList())) {
                "Original simulator operation capture is incomplete or out of order: $prefix"
            }
            val exits = observed.associateWith { name ->
                process(name, commands.getValue(name), attempt == successful)
            }
            observed.dropLast(1).forEach { name ->
                check(exits[name] == 0) { "Original simulator continued after a failed process: $prefix/$name" }
            }
            val readyStatus = if (exits["ready-devices"] == 0) runCatching {
                simulatorStatus(raw.resolve("$prefix/ready-devices/stdout.bin").readSimulatorListing(),
                    selected.runtimeIdentifier, selected.udid)
            }.getOrNull() else null
            val xcodePath = "$prefix/xcodebuild/execution.json"
            if (attempt == successful || xcodePath in originalXCTest) {
                check(observed == commands.keys.toList() && exits.values.all { it == 0 } &&
                    readyStatus == SimulatorStatus(true, "Booted")) {
                    "Original XCTest ran before its selected simulator was ready: $prefix"
                }
                val execution = xctest.verifyOriginalAppleProcess("$prefix/xcodebuild", attempt == successful)
                check(execution.simulatorInteger("schemaVersion") == 1) { "Original XCTest execution schema changed" }
                val command = execution.releaseCommand()
                val destinations = command.indices.filter { command[it] == "-destination" }
                check(command.firstOrNull() == "xcodebuild" && destinations.size == 1 &&
                    command.getOrNull(destinations.single() + 1) == "platform=iOS Simulator,id=${selected.udid}") {
                    "Original XCTest destination differs from its selected simulator: $prefix"
                }
            }
            if (attempt == successful) {
                check(originalReport.contentEquals(raw.resolve("$prefix/ready-devices/stdout.bin").readBytes())) {
                    "Original simulator ready report differs from the successful attempt"
                }
            } else {
                expectedFiles += "$prefix/failure.json"
                val failure = raw.resolve("$prefix/failure.json")
                    .readCanonicalOriginalAppleObject("Original simulator caught failure")
                val exception = failure["exceptionClass"] as? JsonPrimitive
                val message = failure["message"]
                check(failure.keys == setOf("schemaVersion", "exceptionClass", "message") &&
                    failure.simulatorInteger("schemaVersion") == 1 && exception != null && exception.isString &&
                    exception.content.isNotBlank() && exception.content.none(Char::isISOControl) &&
                    (message === JsonNull || message is JsonPrimitive && message.isString)) {
                    "Original simulator caught failure schema changed"
                }
                process("retry-devices", listDevices, true)
                check(shouldRetryDisappearedSimulator(
                    raw.resolve("$prefix/retry-devices/stdout.bin").readSimulatorListing(),
                    selected.runtimeIdentifier, selected.udid, attempt,
                )) { "Original simulator retry is not justified by disappearance" }
            }
        }
        check(originalRaw.keys == expectedFiles) { "Original simulator raw inventory changed" }
    } finally {
        inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "original simulator evidence recheck") }
        check(verifiedRegularFiles(raw).mapValues { (_, file) -> file.releaseDigest() } == originalRaw &&
            verifiedRegularFiles(xctest).mapValues { (_, file) -> file.releaseDigest() } == originalXCTest &&
            report.readBytes().contentEquals(originalReport)) { "Original simulator inputs changed during replay" }
    }
}

private fun JsonObject.simulatorInteger(name: String): Int {
    val value = this[name] as? JsonPrimitive ?: error("Original simulator integer is missing: $name")
    check(!value.isString && value.intOrNull != null) { "Original simulator integer is invalid: $name" }
    return checkNotNull(value.intOrNull)
}

/** Required JSON types only; selection/status/retry interpretation stays in the existing helpers. */
private fun File.readSimulatorListing(runtimes: Boolean = false, selection: Boolean = false): String {
    val text = readStrictUtf8()
    val root = releaseJson.parseToJsonElement(text) as? JsonObject ?: error("Original simulator listing is invalid")
    val rows = if (runtimes) root.releaseArray("runtimes") else {
        JsonArray(root.releaseObject("devices").values.flatMap { value ->
            (value as? JsonArray ?: error("Original simulator device array is invalid")).toList()
        })
    }
    rows.forEach { value ->
        val row = value as? JsonObject ?: error("Original simulator listing row is invalid")
        val strings = if (runtimes) listOf("name", "identifier")
            else listOf("udid", "state") + if (selection) listOf("deviceTypeIdentifier") else emptyList()
        strings.forEach { name ->
            val field = row[name] as? JsonPrimitive
            check(field != null && field.isString && field.content.isNotBlank() && field.content.none(Char::isISOControl)) {
                "Original simulator listing string is invalid: $name"
            }
        }
        val available = row["isAvailable"] as? JsonPrimitive
        check(available != null && !available.isString && available.booleanOrNull != null) {
            "Original simulator listing availability is invalid"
        }
    }
    return text
}
