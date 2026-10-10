import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/** Synthetic retained observations only, not XCTest result, source, receipt or hosted admission. */
class AppleOriginalSimulatorExecutionTest {
    @Test
    fun `first attempt replays optional boot and preserves all original bytes`() {
        for (booted in listOf(false, true)) SimulatorReplayFixture(booted = booted).use { fixture ->
            val before = fixture.inventory()
            fixture.verify()
            assertEquals(before, fixture.inventory())
        }
    }

    @Test
    fun `failed replay keeps its original rejection and preserves input bytes`() {
        SimulatorReplayFixture().use { fixture ->
            val marker = fixture.root.resolve("xctest-raw/successful-attempt.json")
            marker.atomicWriteJson(JsonObject(mapOf(
                "schemaVersion" to JsonPrimitive(2), "attempt" to JsonPrimitive(0),
            )))
            val before = fixture.inventory()
            val failure = assertFailsWith<IllegalStateException> { fixture.verify() }
            assertEquals("Original simulator successful attempt schema changed", failure.message)
            assertEquals(before, fixture.inventory())
        }
    }

    @Test
    fun `retry requires observed failure and disappearance including nonprocess failure`() {
        for (failure in listOf("boot", "bootstatus", "ready-status", "xcode", "filesystem", "launch")) {
            SimulatorReplayFixture(failure = failure).use { fixture ->
                val before = fixture.inventory()
                fixture.verify()
                assertEquals(before, fixture.inventory())
            }
        }
    }

    @Test
    fun `caller pins cwd original destination and ready report are independently bound`() {
        SimulatorReplayFixture().use { fixture ->
            assertFailsWith<IllegalStateException> { fixture.verify(runtime = "iOS 27.0") }
            assertFailsWith<IllegalStateException> { fixture.verify(device = "another-device-type") }
            assertFailsWith<IllegalStateException> { fixture.verify(cwd = "/different/original") }
            assertFailsWith<IllegalStateException> { fixture.verify(cwd = "relative") }
            fixture.rejectMutation("reports/simulator-devices.json") { it.appendText("\n") }
            fixture.rejectMutation("xctest-raw/attempt-0/xcodebuild/execution.json") { file ->
                val value = file.readReleaseObject()
                val command = value.releaseArray("command").toMutableList()
                command[4] = JsonPrimitive("platform=iOS Simulator,id=different-device")
                file.atomicWriteJson(JsonObject(value + ("command" to JsonArray(command))))
            }
        }
    }

    @Test
    fun `strict process schema environment and simulator JSON field types reject`() {
        SimulatorReplayFixture().use { fixture ->
            val execution = "simulator-raw/attempt-0/runtimes/execution.json"
            listOf(
                "schemaVersion" to JsonPrimitive("1"),
                "exitCode" to JsonPrimitive("0"),
                "exitCode" to JsonPrimitive(true),
                "workingDirectory" to JsonPrimitive("/another/cwd"),
                "environment" to JsonObject(mapOf("LC_ALL" to JsonPrimitive("C"))),
                "extra" to JsonPrimitive("unknown"),
            ).forEach { (name, value) ->
                fixture.rejectMutation(execution) { file ->
                    file.atomicWriteJson(JsonObject(file.readReleaseObject() + (name to value)))
                }
            }
            fixture.rejectMutation(execution) { file ->
                val value = file.readReleaseObject()
                file.atomicWriteJson(JsonObject(value + (
                    "command" to JsonArray(value.releaseArray("command") + JsonPrimitive("--extra"))
                )))
            }
            for (path in listOf("runtimes", "devices", "ready-devices")) {
                fixture.rejectMutation("simulator-raw/attempt-0/$path/stdout.bin") { file ->
                    file.writeText(file.readText().replace("\"isAvailable\":true", "\"isAvailable\":\"true\""))
                }
            }
            for (field in listOf("schemaVersion", "attempt")) {
                fixture.rejectMutation("xctest-raw/successful-attempt.json") { file ->
                    val value = file.readReleaseObject()
                    file.atomicWriteJson(JsonObject(value + (field to JsonPrimitive(value.releaseInt(field).toString()))))
                }
            }
        }
    }

    @Test
    fun `retry cannot follow retained success without caught failure or a still present device`() {
        SimulatorReplayFixture(failure = "filesystem").use { fixture ->
            fixture.rejectMutation("simulator-raw/attempt-0/failure.json") { it.delete() }
            for ((field, value) in listOf(
                "schemaVersion" to JsonPrimitive("1"), "message" to JsonPrimitive(1),
                "exceptionClass" to JsonPrimitive(""), "extra" to JsonNull,
            )) fixture.rejectMutation("simulator-raw/attempt-0/failure.json") { file ->
                file.atomicWriteJson(JsonObject(file.readReleaseObject() + (field to value)))
            }
            fixture.rejectMutation("simulator-raw/attempt-0/retry-devices/stdout.bin") { file ->
                file.writeText(fixture.devices(0, "Shutdown"))
            }
            fixture.rejectMutation("simulator-raw/attempt-0/retry-devices/execution.json") { file ->
                file.atomicWriteJson(JsonObject(file.readReleaseObject() + ("exitCode" to JsonPrimitive(65))))
            }
            fixture.rejectMutation("simulator-raw/attempt-0/bootstatus/execution.json") { file ->
                file.atomicWriteJson(JsonObject(file.readReleaseObject() + ("exitCode" to JsonPrimitive(65))))
            }
        }
    }

    @Test
    fun `raw inventory rejects extra missing out of order and symbolic observations`() {
        SimulatorReplayFixture(booted = true).use { fixture ->
            val before = fixture.inventory()
            val extra = fixture.root.resolve("simulator-raw/attempt-0/failure.json")
            extra.writeText("{}\n")
            assertFailsWith<IllegalStateException> { fixture.verify() }
            extra.delete()
            fixture.rejectMutation("simulator-raw/attempt-0/bootstatus/stderr.bin") { it.delete() }
            val step = fixture.root.resolve("simulator-raw/attempt-0/bootstatus")
            val held = fixture.root.resolve("held-bootstatus")
            Files.move(step.toPath(), held.toPath())
            try {
                assertFailsWith<IllegalStateException> { fixture.verify() }
            } finally {
                Files.move(held.toPath(), step.toPath())
            }
            fixture.rejectMutation("simulator-raw/attempt-0/ready-devices/stdout.bin") { file ->
                file.delete()
                Files.createSymbolicLink(file.toPath(), fixture.root.resolve("reports/simulator-devices.json").toPath())
            }
            assertEquals(before, fixture.inventory())
        }
    }
}

private class SimulatorReplayFixture(booted: Boolean = false, failure: String? = null) : AutoCloseable {
    val root = createTempDirectory("apple-original-simulator-").toFile().canonicalFile
    private val originalCwd = "/original/checkout/codex-agent-runtime-ios"
    private val runtimeName = "iOS 26.5"
    private val deviceType = "com.apple.CoreSimulator.SimDeviceType.iPhone-17"
    private val listDevices = listOf("/usr/bin/xcrun", "simctl", "list", "-j", "devices", "available")
    private val tripletEnvironment = mapOf("LC_ALL" to "C", "LANG" to "C")

    init {
        if (failure != null) attempt(0, booted = false, failure = failure)
        val successful = if (failure == null) 0 else 1
        attempt(successful, booted, failure = null)
        root.resolve("xctest-raw/successful-attempt.json").atomicWriteJson(JsonObject(mapOf(
            "schemaVersion" to JsonPrimitive(1), "attempt" to JsonPrimitive(successful),
        )))
        root.resolve("reports/simulator-devices.json").apply {
            parentFile.mkdirs(); writeText(devices(successful, "Booted"))
        }
    }

    fun devices(attempt: Int, state: String) =
        """{"devices":{"runtime-1":[{"udid":"device-$attempt","isAvailable":true,"state":"$state","deviceTypeIdentifier":"$deviceType","optional":"preserved"}]}}"""

    private fun capture(attempt: Int, operation: String, command: List<String>, output: String = "", exit: Int? = 0) {
        writeReleaseProcessCapture(root.resolve("simulator-raw/attempt-$attempt/$operation"), command,
            if (exit == null) null else File(originalCwd), tripletEnvironment, exit,
            output.toByteArray(), byteArrayOf())
    }

    private fun attempt(attempt: Int, booted: Boolean, failure: String?) {
        capture(attempt, "runtimes", listOf("/usr/bin/xcrun", "simctl", "list", "-j", "runtimes"),
            """{"runtimes":[{"name":"$runtimeName","isAvailable":true,"identifier":"runtime-1","optional":"preserved"}]}""")
        capture(attempt, "devices", listDevices, devices(attempt, if (booted) "Booted" else "Shutdown"))
        if (!booted) capture(attempt, "boot", listOf("/usr/bin/xcrun", "simctl", "boot", "device-$attempt"),
            exit = if (failure == "boot") 65 else if (failure == "launch") null else 0)
        if (failure !in setOf("boot", "launch")) {
            capture(attempt, "bootstatus", listOf("/usr/bin/xcrun", "simctl", "bootstatus", "device-$attempt", "-b"),
                exit = if (failure == "bootstatus") 65 else 0)
            if (failure != "bootstatus") {
                capture(attempt, "ready-devices", listDevices,
                    devices(attempt, if (failure == "ready-status") "Shutdown" else "Booted"))
                if (failure != "ready-status") {
                    val command = swiftAuthenticationXcodebuildCommand("device-$attempt", File("/original/derived"),
                        File("/original/swift-authentication-tests.xcresult"))
                    writeReleaseProcessCapture(root.resolve("xctest-raw/attempt-$attempt/xcodebuild"), command,
                        File("/original/CodexAgentPackage"), tripletEnvironment, if (failure == "xcode") 65 else 0,
                        byteArrayOf(0, -1, 10), byteArrayOf())
                }
            }
        }
        if (failure != null) {
            root.resolve("simulator-raw/attempt-$attempt/failure.json").atomicWriteJson(JsonObject(mapOf(
                "schemaVersion" to JsonPrimitive(1),
                "exceptionClass" to JsonPrimitive(if (failure == "filesystem") "java.nio.file.FileSystemException"
                    else "java.lang.IllegalStateException"),
                "message" to if (failure == "launch") JsonNull else JsonPrimitive("original observed failure\n$failure"),
            )))
            capture(attempt, "retry-devices", listDevices, """{"devices":{"runtime-1":[]}}""")
        }
    }

    fun verify(runtime: String = runtimeName, device: String = deviceType, cwd: String = originalCwd) =
        verifyOriginalAppleSimulatorExecution(root, runtime, device, cwd)

    fun inventory() = verifiedRegularFiles(root).mapValues { (_, file) -> file.releaseDigest() }

    fun rejectMutation(path: String, mutate: (File) -> Unit) {
        val file = root.resolve(path)
        val bytes = file.readBytes()
        try {
            mutate(file)
            assertFailsWith<IllegalStateException>(path) { verify() }
        } finally {
            Files.deleteIfExists(file.toPath())
            file.writeBytes(bytes)
        }
    }

    override fun close() { root.deleteRecursively() }
}
