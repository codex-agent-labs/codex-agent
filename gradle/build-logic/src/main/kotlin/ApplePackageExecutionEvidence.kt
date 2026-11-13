import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/**
 * Raw observations from one Apple package replay. This transport is not a verdict or receipt:
 * its caller must authenticate the complete directory and all replay inputs before use.
 * stderr is deliberately merged into stdout because that is the observation made by the
 * existing ProcessBuilder runner.
 */
internal enum class ApplePackageExecutionStep(
    val directoryName: String,
    val expectedExitCode: Int,
    val effect: ApplePackageExecutionEffect = ApplePackageExecutionEffect.NONE,
) {
    TOOLCHAIN_BEFORE_XCODE("00-toolchain-before-xcode", 0),
    TOOLCHAIN_BEFORE_SWIFT("01-toolchain-before-swift", 0),
    DEVICE_PLATFORM("02-device-platform", 0),
    DEVICE_ARCHITECTURE("03-device-architecture", 0),
    SIMULATOR_PLATFORM("04-simulator-platform", 0),
    SIMULATOR_ARCHITECTURE("05-simulator-architecture", 0),
    ASSEMBLE_XCFRAMEWORK("06-assemble-xcframework", 0, ApplePackageExecutionEffect.TREE),
    DEVICE_STRIP("07-device-strip", 0, ApplePackageExecutionEffect.FILE),
    DEVICE_NORMALIZE("08-device-normalize", 0, ApplePackageExecutionEffect.FILE),
    DEVICE_PATH_SCAN("09-device-path-scan", 1),
    SIMULATOR_STRIP("10-simulator-strip", 0, ApplePackageExecutionEffect.FILE),
    SIMULATOR_NORMALIZE("11-simulator-normalize", 0, ApplePackageExecutionEffect.FILE),
    SIMULATOR_PATH_SCAN("12-simulator-path-scan", 1),
    AVAILABLE_LIBRARIES("13-available-libraries", 0),
    REWRITE_AVAILABLE_LIBRARIES("14-rewrite-available-libraries", 0, ApplePackageExecutionEffect.FILE),
    TOOLCHAIN_AFTER_XCODE("15-toolchain-after-xcode", 0),
    TOOLCHAIN_AFTER_SWIFT("16-toolchain-after-swift", 0),
}

internal enum class ApplePackageExecutionEffect { NONE, FILE, TREE }

internal data class ApplePackageExecutionContext(
    val scratchDirectory: File,
    val workDirectory: File,
    val sourceSnapshot: File,
    val binaryFrameworks: File,
    val developerDirectory: File,
)

/**
 * Records only the byte observations and output effects needed to drive the unchanged pure
 * package replay later. Commands must be requested and recorded in the fixed program order.
 */
internal class ApplePackageExecutionRecorder(
    evidenceDirectory: File,
    private val context: ApplePackageExecutionContext,
) {
    private val evidence = requireNormalizedAppleExecutionPath(evidenceDirectory, "evidence")
    private val scratch = requireNormalizedAppleExecutionPath(context.scratchDirectory, "scratch")
    private val work = requireNormalizedAppleExecutionPath(context.workDirectory, "work")
    private val source = requireNormalizedAppleExecutionPath(context.sourceSnapshot, "source")
    private val binary = requireNormalizedAppleExecutionPath(context.binaryFrameworks, "binary")
    private val developer = requireNormalizedAppleExecutionPath(context.developerDirectory, "developer")
    private val steps = ApplePackageExecutionStep.entries
    private var next = 0
    private var availableLibraries: String? = null
    private val capturedDigests = linkedMapOf<String, String>()

    init {
        listOf(scratch, source, binary, developer).forEach {
            check(it.isDirectory) { "Apple package execution context is missing: $it" }
        }
        requireOriginalAppleSnapshotDisjoint(evidence, listOf(scratch, work, source, binary, developer))
        requireOriginalAppleSnapshotDisjoint(work, listOf(scratch, source, binary, developer, evidence))
        requireApplePackagePathWithoutSymlinks(evidence, "execution evidence")
        check(!Files.exists(evidence.toPath(), LinkOption.NOFOLLOW_LINKS)) {
            "Apple package execution evidence must be fresh"
        }
        Files.createDirectories(evidence.parentFile.toPath())
        Files.createDirectory(evidence.toPath())
    }

    internal fun expectedCommand(): List<String> {
        check(next < steps.size) { "Apple package execution is already complete" }
        return applePackageExecutionCommand(context, steps[next], availableLibraries)
    }

    internal fun record(command: List<String>, exitCode: Int?, combinedOutput: ByteArray) {
        check(next < steps.size) { "Unexpected extra Apple package execution event" }
        val step = steps[next]
        check(command == applePackageExecutionCommand(context, step, availableLibraries)) {
            "Apple package execution command mismatch for ${step.directoryName}"
        }
        val directory = evidence.resolve(step.directoryName)
        Files.createDirectory(directory.toPath())
        directory.resolve("combined.bin").writeBytes(combinedOutput)
        directory.resolve("execution.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("ordinal", JsonPrimitive(next))
            put("operation", JsonPrimitive(step.directoryName))
            put("command", buildJsonArray { command.forEach { add(JsonPrimitive(it)) } })
            put("workingDirectory", JsonPrimitive(scratch.path))
            put("environment", buildJsonObject {
                applePackageExecutionEnvironment(context).toSortedMap().forEach { (name, value) -> put(name, JsonPrimitive(value)) }
            })
            put("exitCode", exitCode?.let(::JsonPrimitive) ?: kotlinx.serialization.json.JsonNull)
            put("streamMode", JsonPrimitive("stderr-merged-into-stdout"))
        })
        if (exitCode != step.expectedExitCode) {
            error("Apple package execution failed at ${step.directoryName}: exit=$exitCode")
        }
        captureApplePackageExecutionEffect(context, step, directory)
        verifiedRegularFiles(directory).forEach { (relative, file) ->
            capturedDigests["${step.directoryName}/$relative"] = file.releaseDigest()
        }
        if (step == ApplePackageExecutionStep.AVAILABLE_LIBRARIES) {
            availableLibraries = combinedOutput.toString(Charsets.UTF_8)
        }
        next += 1
    }

    internal fun finish() {
        check(next == steps.size) { "Apple package execution evidence is incomplete" }
        val expected = steps.flatMap { step ->
            val prefix = step.directoryName
            buildList {
                add("$prefix/combined.bin")
                add("$prefix/execution.json")
                when (step.effect) {
                    ApplePackageExecutionEffect.NONE -> Unit
                    ApplePackageExecutionEffect.FILE -> add("$prefix/effect.bin")
                    ApplePackageExecutionEffect.TREE -> {
                        val effect = evidence.resolve("$prefix/effect")
                        addAll(verifiedRegularFiles(effect).keys.map { "$prefix/effect/$it" })
                    }
                }
            }
        }.toSet()
        val actual = verifiedRegularFiles(evidence)
        check(actual.keys == expected && actual.mapValues { (_, file) -> file.releaseDigest() } == capturedDigests) {
            "Apple package execution evidence inventory changed"
        }
    }

}

internal fun applePackageExecutionEnvironment(context: ApplePackageExecutionContext) = mapOf(
        "PATH" to "/usr/bin:/bin:/usr/sbin:/sbin",
        "LC_ALL" to "C",
        "LANG" to "C",
        "HOME" to context.scratchDirectory.path,
        "TMPDIR" to context.scratchDirectory.path,
        "DEVELOPER_DIR" to context.developerDirectory.path,
    )

internal fun applePackageExecutionCommand(
    context: ApplePackageExecutionContext, step: ApplePackageExecutionStep, availableLibraries: String?,
): List<String> {
        val binary = context.binaryFrameworks
        val work = context.workDirectory
        val scratch = context.scratchDirectory
        val source = context.sourceSnapshot
        val device = binary.resolve("ios-arm64/CodexAgent.framework")
        val simulator = binary.resolve("ios-simulator-arm64/CodexAgent.framework")
        val assembled = work.resolve("assembled/CodexAgent.xcframework")
        val release = work.resolve("release/CodexAgent.xcframework")
        fun archive(slice: String) = release.resolve("$slice/CodexAgent.framework/CodexAgent")
        fun stripped(slice: String) = release.resolve("$slice/CodexAgent.framework/CodexAgent.stripped")
        fun normalized(slice: String) = release.resolve("$slice/CodexAgent.framework/CodexAgent.normalized")
        val prefixes = listOf(scratch.path, work.path, source.path)
        return when (step) {
            ApplePackageExecutionStep.TOOLCHAIN_BEFORE_XCODE,
            ApplePackageExecutionStep.TOOLCHAIN_AFTER_XCODE -> listOf("/usr/bin/xcodebuild", "-version")
            ApplePackageExecutionStep.TOOLCHAIN_BEFORE_SWIFT,
            ApplePackageExecutionStep.TOOLCHAIN_AFTER_SWIFT -> listOf("/usr/bin/xcrun", "swift", "--version")
            ApplePackageExecutionStep.DEVICE_PLATFORM ->
                importedFrameworkPlatformCommand(device.resolve("Info.plist"))
            ApplePackageExecutionStep.DEVICE_ARCHITECTURE ->
                listOf("/usr/bin/xcrun", "lipo", "-info", device.resolve("CodexAgent").path)
            ApplePackageExecutionStep.SIMULATOR_PLATFORM ->
                importedFrameworkPlatformCommand(simulator.resolve("Info.plist"))
            ApplePackageExecutionStep.SIMULATOR_ARCHITECTURE ->
                listOf("/usr/bin/xcrun", "lipo", "-info", simulator.resolve("CodexAgent").path)
            ApplePackageExecutionStep.ASSEMBLE_XCFRAMEWORK ->
                importedXCFrameworkAssemblyCommand(device, simulator, assembled)
            ApplePackageExecutionStep.DEVICE_STRIP ->
                stripReleaseArchiveCommand(archive("ios-arm64"), stripped("ios-arm64"))
            ApplePackageExecutionStep.DEVICE_NORMALIZE ->
                libtoolNormalizeCommand(stripped("ios-arm64"), normalized("ios-arm64"))
            ApplePackageExecutionStep.DEVICE_PATH_SCAN ->
                pathPrefixScanCommand(archive("ios-arm64"), prefixes)
            ApplePackageExecutionStep.SIMULATOR_STRIP ->
                stripReleaseArchiveCommand(archive("ios-arm64-simulator"), stripped("ios-arm64-simulator"))
            ApplePackageExecutionStep.SIMULATOR_NORMALIZE ->
                libtoolNormalizeCommand(stripped("ios-arm64-simulator"), normalized("ios-arm64-simulator"))
            ApplePackageExecutionStep.SIMULATOR_PATH_SCAN ->
                pathPrefixScanCommand(archive("ios-arm64-simulator"), prefixes)
            ApplePackageExecutionStep.AVAILABLE_LIBRARIES -> listOf(
                "/usr/bin/plutil", "-extract", "AvailableLibraries", "json", "-o", "-",
                release.resolve("Info.plist").path,
            )
            ApplePackageExecutionStep.REWRITE_AVAILABLE_LIBRARIES -> listOf(
                "/usr/bin/plutil", "-replace", "AvailableLibraries", "-json",
                sortedAvailableLibraries(checkNotNull(availableLibraries) {
                    "Apple AvailableLibraries observation is missing"
                }), release.resolve("Info.plist").path,
            )
        }
    }

internal fun applePackageExecutionEffectSource(
    context: ApplePackageExecutionContext, step: ApplePackageExecutionStep,
): File {
    val work = context.workDirectory
    return when (step) {
        ApplePackageExecutionStep.ASSEMBLE_XCFRAMEWORK -> work.resolve("assembled/CodexAgent.xcframework")
        ApplePackageExecutionStep.DEVICE_STRIP ->
            work.resolve("release/CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent.stripped")
        ApplePackageExecutionStep.DEVICE_NORMALIZE ->
            work.resolve("release/CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent.normalized")
        ApplePackageExecutionStep.SIMULATOR_STRIP ->
            work.resolve("release/CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/CodexAgent.stripped")
        ApplePackageExecutionStep.SIMULATOR_NORMALIZE ->
            work.resolve("release/CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/CodexAgent.normalized")
        ApplePackageExecutionStep.REWRITE_AVAILABLE_LIBRARIES ->
            work.resolve("release/CodexAgent.xcframework/Info.plist")
        else -> error("Apple package execution step has no output effect")
    }
}

private fun captureApplePackageExecutionEffect(
    context: ApplePackageExecutionContext, step: ApplePackageExecutionStep, eventDirectory: File,
) {
        if (step.effect == ApplePackageExecutionEffect.NONE) return
        val sourceEffect = applePackageExecutionEffectSource(context, step)
        requireApplePackagePathWithoutSymlinks(sourceEffect, "execution effect")
        when (step.effect) {
            ApplePackageExecutionEffect.NONE -> Unit
            ApplePackageExecutionEffect.FILE -> {
                check(sourceEffect.isFile && !Files.isSymbolicLink(sourceEffect.toPath()) && sourceEffect.length() > 0L) {
                    "Apple package execution file effect is missing: ${step.directoryName}"
                }
                val before = sourceEffect.releaseDigest()
                val held = eventDirectory.resolve("effect.bin")
                Files.copy(sourceEffect.toPath(), held.toPath(), StandardCopyOption.COPY_ATTRIBUTES)
                check(sourceEffect.releaseDigest() == before && held.releaseDigest() == before) {
                    "Apple package execution file effect changed during capture"
                }
            }
            ApplePackageExecutionEffect.TREE -> {
                val before = verifiedRegularFiles(sourceEffect).mapValues { (_, file) -> file.releaseDigest() }
                check(before.isNotEmpty()) { "Apple package execution tree effect is empty" }
                val held = eventDirectory.resolve("effect")
                copyReleaseTree(sourceEffect, held)
                check(verifiedRegularFiles(sourceEffect).mapValues { (_, file) -> file.releaseDigest() } == before &&
                    verifiedRegularFiles(held).mapValues { (_, file) -> file.releaseDigest() } == before) {
                    "Apple package execution tree effect changed during capture"
                }
            }
        }
    }
private fun requireNormalizedAppleExecutionPath(file: File, role: String): File {
    check(file.isAbsolute && file.toPath().normalize() == file.toPath() && file.canonicalFile == file) {
        "Apple package execution $role path must be absolute and normalized"
    }
    requireApplePackagePathWithoutSymlinks(file, "execution $role")
    return file
}
