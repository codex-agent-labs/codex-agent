import java.io.File
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * File boundary for the existing pure replay. Both expectations must be supplied from the
 * SAME authenticated original upload; hashing current arguments is not an authority.
 * This verifies content only and never authenticates an upload, receipt, producer or host.
 */
internal fun verifyBoundOriginalApplePackageExecution(
    evidenceDirectory: File,
    productDirectory: File,
    version: String,
    binaryFrameworks: File,
    sourceSnapshot: File,
    sdkCompatibility: File,
    workDirectory: File,
    bindingFile: File,
    expectedBindingSha256: String,
    expectedExecutionFiles: File,
    expectedXcodeVersion: String,
    expectedXcodeBuild: String,
    expectedSwiftVersion: String,
) {
    listOf(bindingFile, expectedExecutionFiles).forEach {
        requireApplePackagePathWithoutSymlinks(it, "original package binding")
        check(it.isFile) { "Original Apple package binding file is missing" }
    }
    requireOriginalAppleSnapshotDisjoint(workDirectory, listOf(bindingFile, expectedExecutionFiles))
    val bindingBefore = bindingFile.readBytes()
    val executionBefore = expectedExecutionFiles.readBytes()
    check(expectedBindingSha256.matches(Regex("sha256:[0-9a-f]{64}")) &&
        "sha256:${bindingFile.releaseDigest()}" == expectedBindingSha256) {
        "Original Apple package binding digest changed"
    }
    val binding = bindingFile.readCanonicalOriginalApplePackageObject()
    check(binding.keys == setOf("schemaVersion", "context", "inputs") &&
        binding["schemaVersion"]?.toString() == "1") {
        "Original Apple package binding schema is invalid"
    }
    val context = binding["context"] as? JsonObject ?: error("Original Apple package context is invalid")
    check(context.keys == setOf("scratchDirectory", "workDirectory", "sourceSnapshot",
        "binaryFrameworks", "developerDirectory")) { "Original Apple package context fields are invalid" }
    fun path(role: String): File {
        val value = context[role] as? kotlinx.serialization.json.JsonPrimitive
            ?: error("Original Apple package context path is invalid")
        check(value.isString && value.content.none(Char::isISOControl)) {
            "Original Apple package context path is invalid"
        }
        return File(value.content)
    }
    val originalContext = ApplePackageExecutionContext(path("scratchDirectory"), path("workDirectory"),
        path("sourceSnapshot"), path("binaryFrameworks"), path("developerDirectory"))
    val inputs = binding["inputs"] as? JsonObject ?: error("Original Apple package inputs are invalid")
    check(inputs.keys == setOf("product", "binary", "source", "compatibility")) {
        "Original Apple package input roles are invalid"
    }
    fun digests(value: JsonObject): Map<String, String> = value.mapValues { (path, digest) ->
        check(path.isNotBlank() && !path.startsWith('/') && '\\' !in path &&
            path.none(Char::isISOControl) && path.split('/').none { it.isEmpty() || it == "." || it == ".." }) {
            "Original Apple package inventory path is invalid"
        }
        val primitive = digest as? kotlinx.serialization.json.JsonPrimitive
            ?: error("Original Apple package inventory digest is invalid")
        check(primitive.isString && primitive.content.matches(Regex("[0-9a-f]{64}"))) {
            "Original Apple package inventory digest is invalid"
        }
        primitive.content
    }
    val expected = inputs.mapValues { (_, value) ->
        digests(value as? JsonObject ?: error("Original Apple package input inventory is invalid"))
    } + ("execution" to digests(expectedExecutionFiles.readCanonicalOriginalApplePackageObject()))
    try {
        verifyOriginalApplePackageExecution(evidenceDirectory, productDirectory, version, binaryFrameworks,
            sourceSnapshot, sdkCompatibility, workDirectory, originalContext, expected,
            expectedXcodeVersion, expectedXcodeBuild, expectedSwiftVersion)
    } finally {
        listOf(bindingFile, expectedExecutionFiles).forEach {
            requireApplePackagePathWithoutSymlinks(it, "original package binding recheck")
        }
        check(bindingFile.readBytes().contentEquals(bindingBefore) &&
            expectedExecutionFiles.readBytes().contentEquals(executionBefore)) {
            "Original Apple package binding changed during replay"
        }
    }
}

/**
 * Pure replay of caller-authenticated original package execution bytes. The retained process
 * observations and effects grant no receipt, producer, source, or host authority by themselves.
 * expectedOriginalInputs must come from the same authenticated original execution binding as
 * the evidence; hashes reconstructed from these current arguments are not an authority.
 */
internal fun verifyOriginalApplePackageExecution(
    evidenceDirectory: File,
    productDirectory: File,
    version: String,
    binaryFrameworks: File,
    sourceSnapshot: File,
    sdkCompatibility: File,
    workDirectory: File,
    originalContext: ApplePackageExecutionContext,
    expectedOriginalInputs: Map<String, Map<String, String>>,
    expectedXcodeVersion: String,
    expectedXcodeBuild: String,
    expectedSwiftVersion: String,
) {
    val suppliedInputs = listOf(
        evidenceDirectory, productDirectory, binaryFrameworks, sourceSnapshot, sdkCompatibility,
    )
    (suppliedInputs + workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "original package replay")
    }
    val evidence = evidenceDirectory.canonicalFile
    val product = productDirectory.canonicalFile
    val binary = binaryFrameworks.canonicalFile
    val source = sourceSnapshot.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val work = workDirectory.canonicalFile
    val inputs = listOf(evidence, product, binary, source, compatibility)
    (inputs + work).forEach { requireApplePackagePathWithoutSymlinks(it, "original package replay") }
    check(listOf(evidence, product, binary, source).all(File::isDirectory) &&
        compatibility.isFile && compatibility.length() > 0L &&
        !Files.isSymbolicLink(compatibility.toPath())) {
        "Original Apple package replay input is missing or unsafe"
    }
    requireOriginalAppleSnapshotDisjoint(work, inputs)
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Original Apple package replay work must be fresh"
    }
    requireHistoricalApplePackageContext(originalContext)

    fun treeDigests(root: File) = verifiedRegularFiles(root).mapValues { (_, file) -> file.releaseDigest() }
    val evidenceBefore = treeDigests(evidence)
    val productBefore = treeDigests(product)
    val binaryBefore = treeDigests(binary)
    val sourceBefore = treeDigests(source)
    val compatibilityBefore = compatibility.releaseDigest()
    val expectedBindings = expectedOriginalInputs.mapValues { (_, inventory) -> inventory.toMap() }
    check(expectedBindings.keys == setOf("execution", "product", "binary", "source", "compatibility") &&
        expectedBindings.values.all { it.isNotEmpty() } &&
        expectedBindings.getValue("compatibility").keys == setOf("sdk-compatibility.json") &&
        expectedBindings.values.flatMap { it.values }.all { it.matches(Regex("[0-9a-f]{64}")) }) {
        "Original Apple package execution input binding is invalid"
    }
    check(expectedBindings == mapOf(
        "execution" to evidenceBefore,
        "product" to productBefore,
        "binary" to binaryBefore,
        "source" to sourceBefore,
        "compatibility" to mapOf("sdk-compatibility.json" to compatibilityBefore),
    )) { "Original Apple package execution input binding changed" }
    try {
        val events = readOriginalApplePackageEvents(evidence, originalContext)

        verifyAppleToolchainOutput(
            events[0].combined,
            events[1].combined,
            expectedXcodeVersion,
            expectedXcodeBuild,
            expectedSwiftVersion,
        )

        val localContext = ApplePackageExecutionContext(
            scratchDirectory = work.resolve("scratch"),
            workDirectory = work,
            sourceSnapshot = source,
            binaryFrameworks = binary,
            developerDirectory = work.resolve("developer-unused"),
        )
        var index = 2
        var localAvailableLibraries: String? = null
        fun consume(command: List<String>, scan: Boolean): OriginalApplePackageEvent {
            check(index in 2..14) { "Unexpected Apple package replay callback" }
            val event = events[index]
            val isScan = event.step in setOf(
                ApplePackageExecutionStep.DEVICE_PATH_SCAN,
                ApplePackageExecutionStep.SIMULATOR_PATH_SCAN,
            )
            check(scan == isScan && command == applePackageExecutionCommand(
                localContext,
                event.step,
                localAvailableLibraries,
            )) { "Local Apple package replay command changed at ${event.step.directoryName}" }
            restoreOriginalApplePackageEffect(event, localContext)
            if (event.step == ApplePackageExecutionStep.AVAILABLE_LIBRARIES) {
                localAvailableLibraries = event.combined
            }
            index += 1
            return event
        }

        verifyAppleBinaryPackageReplay(
            product,
            version,
            binary,
            source,
            compatibility,
            work,
            listOf(localContext.scratchDirectory.path, work.path, source.path),
            capture = { command -> consume(command, false).combined },
            scan = { command -> consume(command, true).let { it.exitCode to it.combined } },
        )
        check(index == 15) { "Original Apple package execution callback count changed" }
        verifyAppleToolchainOutput(
            events[15].combined,
            events[16].combined,
            expectedXcodeVersion,
            expectedXcodeBuild,
            expectedSwiftVersion,
        )
    } finally {
        inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "original package replay recheck") }
        check(treeDigests(evidence) == evidenceBefore && treeDigests(product) == productBefore &&
            treeDigests(binary) == binaryBefore && treeDigests(source) == sourceBefore &&
            compatibility.isFile && !Files.isSymbolicLink(compatibility.toPath()) &&
            compatibility.releaseDigest() == compatibilityBefore && expectedOriginalInputs == expectedBindings) {
            "Original Apple package replay input changed"
        }
    }
}

private data class OriginalApplePackageEvent(
    val step: ApplePackageExecutionStep,
    val directory: File,
    val combined: String,
    val exitCode: Int,
)

private fun readOriginalApplePackageEvents(
    evidence: File,
    originalContext: ApplePackageExecutionContext,
): List<OriginalApplePackageEvent> {
    val actual = verifiedRegularFiles(evidence)
    val expected = linkedSetOf<String>()
    var availableLibraries: String? = null
    val events = ApplePackageExecutionStep.entries.mapIndexed { ordinal, step ->
        val directory = evidence.resolve(step.directoryName)
        val files = verifiedRegularFiles(directory)
        val localExpected = linkedSetOf("combined.bin", "execution.json")
        when (step.effect) {
            ApplePackageExecutionEffect.NONE -> Unit
            ApplePackageExecutionEffect.FILE -> localExpected += "effect.bin"
            ApplePackageExecutionEffect.TREE -> {
                val effects = verifiedRegularFiles(directory.resolve("effect"))
                check(effects.isNotEmpty()) { "Original Apple package execution tree effect is empty" }
                localExpected += effects.keys.map { "effect/$it" }
            }
        }
        check(files.keys == localExpected) {
            "Original Apple package execution event inventory changed: ${step.directoryName}"
        }
        expected += localExpected.map { "${step.directoryName}/$it" }
        val executionFile = directory.resolve("execution.json")
        val execution = executionFile.readCanonicalOriginalApplePackageObject()
        check(execution.keys == setOf(
            "schemaVersion", "ordinal", "operation", "command", "workingDirectory",
            "environment", "exitCode", "streamMode",
        ) && execution.releaseStrictInt("schemaVersion") == 1 && execution.releaseStrictInt("ordinal") == ordinal &&
            execution.releaseString("operation") == step.directoryName &&
            execution.releaseString("workingDirectory") == originalContext.scratchDirectory.path &&
            execution.releaseString("streamMode") == "stderr-merged-into-stdout" &&
            execution.releaseStrictInt("exitCode") == step.expectedExitCode &&
            execution.releaseStringMap("environment") == applePackageExecutionEnvironment(originalContext)) {
            "Original Apple package execution metadata changed: ${step.directoryName}"
        }
        val command = execution.releaseStrictStringArray("command")
        check(command == applePackageExecutionCommand(originalContext, step, availableLibraries)) {
            "Original Apple package execution command changed: ${step.directoryName}"
        }
        val combined = directory.resolve("combined.bin").readOriginalApplePackageCombined()
        if (step == ApplePackageExecutionStep.AVAILABLE_LIBRARIES) availableLibraries = combined
        OriginalApplePackageEvent(step, directory, combined, step.expectedExitCode)
    }
    check(actual.keys == expected) { "Original Apple package execution inventory changed" }
    return events
}

private fun restoreOriginalApplePackageEffect(
    event: OriginalApplePackageEvent,
    localContext: ApplePackageExecutionContext,
) {
    if (event.step.effect == ApplePackageExecutionEffect.NONE) return
    val destination = applePackageExecutionEffectSource(localContext, event.step)
    requireApplePackagePathWithoutSymlinks(destination, "restored package execution effect")
    when (event.step.effect) {
        ApplePackageExecutionEffect.NONE -> Unit
        ApplePackageExecutionEffect.TREE -> {
            check(!Files.exists(destination.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                "Apple package replay tree effect destination is not fresh"
            }
            copyReleaseTree(event.directory.resolve("effect"), destination)
        }
        ApplePackageExecutionEffect.FILE -> {
            val source = event.directory.resolve("effect.bin")
            check(source.isFile && !Files.isSymbolicLink(source.toPath()) && source.length() > 0L) {
                "Original Apple package replay file effect is missing"
            }
            Files.createDirectories(destination.parentFile.toPath())
            if (event.step == ApplePackageExecutionStep.REWRITE_AVAILABLE_LIBRARIES) {
                check(destination.isFile && !Files.isSymbolicLink(destination.toPath())) {
                    "Apple package replay plist effect destination is missing or unsafe"
                }
                Files.copy(source.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING,
                    StandardCopyOption.COPY_ATTRIBUTES)
            } else {
                check(!Files.exists(destination.toPath(), LinkOption.NOFOLLOW_LINKS)) {
                    "Apple package replay file effect destination is not fresh"
                }
                Files.copy(source.toPath(), destination.toPath(), StandardCopyOption.COPY_ATTRIBUTES)
            }
        }
    }
}

private fun requireHistoricalApplePackageContext(context: ApplePackageExecutionContext) {
    val roles = listOf(
        "scratch" to context.scratchDirectory,
        "work" to context.workDirectory,
        "source" to context.sourceSnapshot,
        "binary" to context.binaryFrameworks,
        "developer" to context.developerDirectory,
    )
    roles.forEach { (role, file) ->
        check(file.isAbsolute && file.path.startsWith("/") && '\\' !in file.path && '\u0000' !in file.path &&
            file.toPath().normalize() == file.toPath()) {
            "Original Apple package $role path is not normalized POSIX"
        }
    }
    roles.forEachIndexed { index, (_, left) ->
        roles.drop(index + 1).forEach { (_, right) ->
            check(!left.toPath().startsWith(right.toPath()) && !right.toPath().startsWith(left.toPath())) {
                "Original Apple package execution paths overlap"
            }
        }
    }
}

private fun File.readCanonicalOriginalApplePackageObject(): JsonObject {
    check(isFile && !Files.isSymbolicLink(toPath())) { "Original Apple package execution metadata is missing" }
    val contents = readOriginalApplePackageUtf8()
    val value = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("Original Apple package execution metadata is not an object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), value) + "\n") {
        "Original Apple package execution metadata is not canonical"
    }
    return value
}

private fun File.readOriginalApplePackageUtf8(): String {
    check(isFile && !Files.isSymbolicLink(toPath())) { "Original Apple package execution file is missing" }
    return Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(readBytes())).toString()
}

private fun File.readOriginalApplePackageCombined(): String {
    check(isFile && !Files.isSymbolicLink(toPath())) { "Original Apple package combined stream is missing" }
    return readBytes().toString(Charsets.UTF_8)
}

private fun JsonObject.releaseStrictStringArray(name: String): List<String> {
    val values = this[name] as? JsonArray ?: error("Missing JSON array: $name")
    return values.map { value ->
        check(value.jsonPrimitive.isString) { "Original Apple package execution command is not textual" }
        value.jsonPrimitive.content
    }
}

private fun JsonObject.releaseStrictInt(name: String): Int {
    val value = this[name]?.jsonPrimitive ?: error("Missing JSON integer: $name")
    check(!value.isString && value.intOrNull != null) {
        "Original Apple package execution integer is not numeric: $name"
    }
    return value.intOrNull!!
}

private fun JsonObject.releaseStringMap(name: String): Map<String, String> {
    val values = this[name] as? JsonObject ?: error("Missing JSON object: $name")
    return values.mapValues { (_, value) ->
        check(value.jsonPrimitive.isString) { "Original Apple package execution environment is not textual" }
        value.jsonPrimitive.content
    }
}
