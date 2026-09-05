import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import javax.inject.Inject
import kotlinx.serialization.json.JsonObject
import org.apache.commons.compress.archivers.zip.UnixStat
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipFile
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations

internal fun importedFrameworkPlatformCommand(infoPlist: File) = listOf(
    "/usr/bin/plutil", "-extract", "CFBundleSupportedPlatforms.0", "raw", "-o", "-", infoPlist.absolutePath,
)

internal fun verifyImportedFrameworkPlatform(expected: String, actual: String) {
    val normalized = actual.trim()
    check(normalized.equals(expected, ignoreCase = true)) {
        "Imported framework platform mismatch: expected=$expected actual=$normalized"
    }
}

private const val MAX_VERIFIED_XCFRAMEWORK_ENTRIES = 100_000
private const val MAX_VERIFIED_XCFRAMEWORK_BYTES = 4_294_967_296L

internal fun extractVerifiedAppleXCFramework(
    evidenceDirectory: File,
    verificationReceipt: File,
    version: String,
    temporaryDirectory: File,
    outputDirectory: File,
) {
    check(PRODUCT_SEMVER.matches(version)) { "Imported Apple SDK version is invalid" }
    val receipt = verificationReceipt.readReleaseObject()
    check(receipt.keys == setOf(
        "schemaVersion", "protocol", "result", "candidateCommit", "candidateTree",
        "sourceProofSha256", "nativeEvidenceReceiptSha256",
    ) && receipt.releaseInt("schemaVersion") == 1 &&
        receipt.releaseString("protocol") == "codex-agent-ios-verified-distribution-import-v1" &&
        receipt.releaseString("result") == "passed" &&
        receipt.releaseString("candidateCommit").matches(Regex("[0-9a-f]{40}")) &&
        receipt.releaseString("candidateTree").matches(Regex("[0-9a-f]{40}")) &&
        receipt.releaseString("sourceProofSha256").matches(Regex("[0-9a-f]{64}")) &&
        receipt.releaseString("nativeEvidenceReceiptSha256").matches(Regex("[0-9a-f]{64}"))) {
        "Imported Apple distribution verification receipt is invalid"
    }
    val files = verifiedRegularFiles(evidenceDirectory)
    val proof = files[IOS_VERIFIED_DISTRIBUTION_PROOF]
        ?: error("Verified Apple distribution proof is missing")
    val heldProof = temporaryDirectory.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    temporaryDirectory.mkdirs()
    Files.copy(proof.toPath(), heldProof.toPath(), REPLACE_EXISTING)
    check(heldProof.releaseDigest() == receipt.releaseString("sourceProofSha256")) {
        "Imported Apple distribution proof differs from its verification receipt"
    }
    val archiveName = "CodexAgent-$version.xcframework.zip"
    val archive = files[archiveName] ?: error("Verified Apple XCFramework archive is missing")
    val artifact = heldProof.readReleaseObject().releaseArray("artifacts").map { value ->
        value as? JsonObject ?: error("Verified Apple artifact record is invalid")
    }.singleOrNull { it.releaseString("fileName") == archiveName }
        ?: error("Verified Apple XCFramework artifact record is missing or duplicated")
    check(artifact.keys == setOf("fileName", "bytes", "sha256")) {
        "Verified Apple XCFramework artifact record is invalid"
    }

    val heldArchive = temporaryDirectory.resolve(archiveName)
    Files.copy(archive.toPath(), heldArchive.toPath(), REPLACE_EXISTING)
    verifyReleaseRecord(heldArchive, artifact)
    val extracted = temporaryDirectory.resolve("extracted")
    deleteReleaseTree(extracted)
    extractStrictXCFrameworkArchive(heldArchive, extracted)
    deleteReleaseTree(outputDirectory)
    copyReleaseTree(extracted, outputDirectory)
    verifiedRegularFiles(outputDirectory)
}

private fun extractStrictXCFrameworkArchive(archiveFile: File, output: File) {
    val rootName = "CodexAgent.xcframework"
    val prefix = "$rootName/"
    val seen = mutableSetOf<String>()
    var count = 0
    var bytes = 0L
    ZipFile(archiveFile).use { archive ->
        val entries = archive.entries
        while (entries.hasMoreElements()) {
            val entry = entries.nextElement()
            count += 1
            check(count <= MAX_VERIFIED_XCFRAMEWORK_ENTRIES) {
                "Verified Apple XCFramework archive contains too many entries"
            }
            val name = entry.name
            val parts = name.removeSuffix("/").split('/')
            val expectedType = if (entry.isDirectory) UnixStat.DIR_FLAG else UnixStat.FILE_FLAG
            val storedType = entry.unixMode and UnixStat.FILE_TYPE_FLAG
            check(name.startsWith(prefix) && parts.none { it.isEmpty() || it == "." || it == ".." } &&
                '\\' !in name && name.none { it.code < 32 || it.code == 127 } &&
                seen.add(name.removeSuffix("/")) &&
                entry.method in setOf(ZipArchiveEntry.STORED, ZipArchiveEntry.DEFLATED) &&
                !entry.isUnixSymlink &&
                (storedType == 0 || storedType == expectedType)) {
                "Verified Apple XCFramework archive entry is unsafe or duplicated: $name"
            }
            val relative = name.removePrefix(prefix)
            if (relative.isEmpty()) {
                check(entry.isDirectory && entry.size == 0L) {
                    "Verified Apple XCFramework archive root entry is invalid"
                }
                Files.createDirectories(output.toPath())
                continue
            }
            val destination = output.toPath().resolve(relative).normalize()
            check(destination.startsWith(output.toPath())) {
                "Verified Apple XCFramework archive entry escapes its root: $name"
            }
            if (entry.isDirectory) {
                check(entry.size == 0L) { "Verified Apple XCFramework directory has a payload: $name" }
                Files.createDirectories(destination)
            } else {
                check(entry.size >= 0L) { "Verified Apple XCFramework archive entry size is invalid: $name" }
                check(entry.size <= MAX_VERIFIED_XCFRAMEWORK_BYTES - bytes) {
                    "Verified Apple XCFramework archive expands beyond its limit"
                }
                Files.createDirectories(destination.parent)
                archive.getInputStream(entry).use { input ->
                    Files.newOutputStream(destination).use { outputStream ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        var memberBytes = 0L
                        while (true) {
                            val read = input.read(buffer)
                            if (read < 0) break
                            memberBytes = Math.addExact(memberBytes, read.toLong())
                            check(memberBytes <= entry.size) {
                                "Verified Apple XCFramework archive entry exceeds its declared size: $name"
                            }
                            bytes = Math.addExact(bytes, read.toLong())
                            check(bytes <= MAX_VERIFIED_XCFRAMEWORK_BYTES) {
                                "Verified Apple XCFramework archive expands beyond its limit"
                            }
                            outputStream.write(buffer, 0, read)
                        }
                        check(memberBytes == entry.size) {
                            "Verified Apple XCFramework archive entry size changed: $name"
                        }
                    }
                }
            }
        }
    }
    check(output.list()?.toSet() == setOf("Info.plist", "ios-arm64", "ios-arm64-simulator")) {
        "Verified Apple XCFramework slice inventory is invalid"
    }
    listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
        val framework = output.resolve("$slice/CodexAgent.framework")
        listOf(
            "CodexAgent", "Headers/CodexAgent.h", "Modules/module.modulemap", "Info.plist",
            "PrivacyInfo.xcprivacy", "META-INF/codex-agent/sdk-compatibility.json",
        ).forEach { relative ->
            val file = framework.resolve(relative)
            check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
                "Verified Apple XCFramework member is missing or unsafe: $slice/$relative"
            }
        }
    }
}

@CacheableTask
abstract class ImportVerifiedCodexAgentXCFrameworkTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val evidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val verificationReceipt: RegularFileProperty
    @get:Input abstract val version: Property<String>
    @get:OutputDirectory abstract val xcframeworkDirectory: DirectoryProperty

    @TaskAction
    fun importFramework() = extractVerifiedAppleXCFramework(
        evidenceDirectory.get().asFile,
        verificationReceipt.get().asFile,
        version.get(),
        temporaryDir,
        xcframeworkDirectory.get().asFile,
    )
}

@CacheableTask
abstract class ImportCodexAgentFrameworkTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val frameworkDirectory: DirectoryProperty
    @get:Input abstract val platformName: Property<String>
    @get:OutputDirectory abstract val importedFrameworkDirectory: DirectoryProperty

    @TaskAction
    fun importFramework() {
        val source = frameworkDirectory.get().asFile
        val required = listOf("CodexAgent", "Headers/CodexAgent.h", "Modules/module.modulemap", "Info.plist")
        required.forEach { relative ->
            val file = source.resolve(relative)
            check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
                "Imported ${platformName.get()} framework member is missing or unsafe: $relative"
            }
        }
        Files.walk(source.toPath()).use { paths ->
            check(paths.noneMatch(Files::isSymbolicLink)) { "Imported framework contains a symbolic link" }
        }
        val actualPlatform = capture(*importedFrameworkPlatformCommand(source.resolve("Info.plist")).toTypedArray())
        verifyImportedFrameworkPlatform(platformName.get(), actualPlatform)
        check("arm64" in capture("/usr/bin/xcrun", "lipo", "-info", source.resolve("CodexAgent").absolutePath)) {
            "Imported framework does not contain arm64"
        }
        val output = importedFrameworkDirectory.get().asFile
        deleteReleaseTree(output)
        copyReleaseTree(source, output)
    }

    private fun capture(vararg command: String): String {
        val output = ByteArrayOutputStream()
        processes.exec { commandLine(command.toList()); standardOutput = output }.assertNormalExitValue()
        return output.toString()
    }
}

@CacheableTask
abstract class AssembleImportedCodexAgentXCFrameworkTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val deviceFrameworkDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val simulatorFrameworkDirectory: DirectoryProperty
    @get:Input abstract val appleToolchainIdentity: Property<String>
    @get:OutputDirectory abstract val xcframeworkDirectory: DirectoryProperty

    @TaskAction
    fun assemble() {
        val output = xcframeworkDirectory.get().asFile
        deleteReleaseTree(output)
        output.parentFile.mkdirs()
        processes.exec {
            commandLine(
                "/usr/bin/xcodebuild", "-create-xcframework",
                "-framework", deviceFrameworkDirectory.get().asFile.absolutePath,
                "-framework", simulatorFrameworkDirectory.get().asFile.absolutePath,
                "-output", output.absolutePath,
            )
        }.assertNormalExitValue()
    }
}
