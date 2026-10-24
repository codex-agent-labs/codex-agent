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

internal fun importedXCFrameworkAssemblyCommand(device: File, simulator: File, output: File) = listOf(
    "/usr/bin/xcodebuild", "-create-xcframework",
    "-framework", device.absolutePath, "-framework", simulator.absolutePath,
    "-output", output.absolutePath,
)

internal fun verifyImportedAppleFramework(source: File, platform: String, capture: (List<String>) -> String) {
    val required = listOf("CodexAgent", "Headers/CodexAgent.h", "Modules/module.modulemap", "Info.plist")
    required.forEach { relative ->
        val file = source.resolve(relative)
        check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
            "Imported $platform framework member is missing or unsafe: $relative"
        }
    }
    Files.walk(source.toPath()).use { paths ->
        check(paths.noneMatch(Files::isSymbolicLink)) { "Imported framework contains a symbolic link" }
    }
    verifyImportedFrameworkPlatform(platform, capture(importedFrameworkPlatformCommand(source.resolve("Info.plist"))))
    check("arm64" in capture(listOf("/usr/bin/xcrun", "lipo", "-info", source.resolve("CodexAgent").absolutePath))) {
        "Imported framework does not contain arm64"
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
    val heldArchive = captureVerifiedAppleArchive(
        evidenceDirectory, verificationReceipt, version,
        "CodexAgent-$version.xcframework.zip", temporaryDirectory,
    )
    val extracted = temporaryDirectory.resolve("extracted")
    deleteReleaseTree(extracted)
    extractStrictAppleArchive(heldArchive, extracted, "CodexAgent.xcframework/")
    verifyExtractedXCFramework(extracted)
    deleteReleaseTree(outputDirectory)
    copyReleaseTree(extracted, outputDirectory)
    verifiedRegularFiles(outputDirectory)
}

private fun captureVerifiedAppleArchive(
    evidenceDirectory: File,
    verificationReceipt: File,
    version: String,
    archiveName: String,
    temporaryDirectory: File,
): File {
    check(PRODUCT_SEMVER.matches(version)) { "Imported Apple SDK version is invalid" }
    val receipt = verificationReceipt.readReleaseObject()
    val schema = receipt.releaseInt("schemaVersion")
    val identityKeys = if (schema == 1) {
        setOf("candidateCommit", "candidateTree", "nativeEvidenceReceiptSha256")
    } else {
        setOf(
            "producerCommit", "producerTree", "consumerCommit", "consumerTree",
            "originalNativeEvidenceReceiptSha256", "currentNativeEvidenceReceiptSha256",
        )
    }
    check(schema in setOf(1, 2) && receipt.keys == setOf(
        "schemaVersion", "protocol", "result", "sourceProofSha256",
    ) + identityKeys &&
        receipt.releaseString("protocol") == "codex-agent-ios-verified-distribution-import-v$schema" &&
        receipt.releaseString("result") == "passed" &&
        receipt.releaseString("sourceProofSha256").matches(Regex("[0-9a-f]{64}")) &&
        identityKeys.all { key -> receipt.releaseString(key).matches(Regex(
            if (key.endsWith("Sha256")) "[0-9a-f]{64}" else "[0-9a-f]{40}",
        )) }) {
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
    val heldProofObject = heldProof.readReleaseObject()
    if (schema == 2) {
        check(heldProofObject.releaseString("candidateCommit") == receipt.releaseString("producerCommit") &&
            heldProofObject.releaseString("candidateTree") == receipt.releaseString("producerTree") &&
            heldProofObject.releaseString("nativeEvidenceReceiptSha256") ==
            receipt.releaseString("originalNativeEvidenceReceiptSha256")) {
            "Imported Apple distribution receipt roles differ from its proof"
        }
    }
    val archive = files[archiveName] ?: error("Verified Apple archive is missing: $archiveName")
    val artifact = heldProofObject.releaseArray("artifacts").map { value ->
        value as? JsonObject ?: error("Verified Apple artifact record is invalid")
    }.singleOrNull { it.releaseString("fileName") == archiveName }
        ?: error("Verified Apple XCFramework artifact record is missing or duplicated")
    check(artifact.keys == setOf("fileName", "bytes", "sha256")) {
        "Verified Apple XCFramework artifact record is invalid"
    }

    val heldArchive = temporaryDirectory.resolve(archiveName)
    Files.copy(archive.toPath(), heldArchive.toPath(), REPLACE_EXISTING)
    verifyReleaseRecord(heldArchive, artifact)
    return heldArchive
}

internal fun extractStrictAppleArchive(archiveFile: File, output: File, prefix: String) {
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
                entry.rawName?.none { it == '\\'.code.toByte() } == true &&
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
}

private fun verifyExtractedXCFramework(output: File) {
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

internal fun extractVerifiedAppleSwiftPackage(
    evidenceDirectory: File,
    verificationReceipt: File,
    version: String,
    temporaryDirectory: File,
    outputDirectory: File,
) {
    val heldArchive = captureVerifiedAppleArchive(
        evidenceDirectory, verificationReceipt, version,
        "CodexAgentPackage-$version.zip", temporaryDirectory,
    )
    val extracted = temporaryDirectory.resolve("swift-package")
    deleteReleaseTree(extracted)
    extractStrictAppleArchive(heldArchive, extracted, "")
    val packageFiles = verifiedRegularFiles(extracted)
    val compatibilityPath = "META-INF/codex-agent/sdk-compatibility.json"
    listOf(
        "Package.swift", "LICENSE.txt", "THIRD_PARTY_NOTICES.md", "openai-codex-LICENSE.txt",
        "openai-codex-NOTICE.txt", compatibilityPath,
    ).forEach { path ->
        check(packageFiles[path]?.length()?.let { it > 0L } == true) {
            "Verified Apple Swift package member is missing or empty: $path"
        }
    }
    listOf("Sources/", "Tests/").forEach { prefix ->
        check(packageFiles.any { (path, file) -> path.startsWith(prefix) && file.length() > 0L }) {
            "Verified Apple Swift package source tree is missing: $prefix"
        }
    }
    val reference = temporaryDirectory.resolve("reference-xcframework")
    extractVerifiedAppleXCFramework(
        evidenceDirectory, verificationReceipt, version,
        temporaryDirectory.resolve("reference-import"), reference,
    )
    val referenceFiles = verifiedRegularFiles(reference)
    val compatibilityPaths = setOf("ios-arm64", "ios-arm64-simulator").map { slice ->
        "$slice/CodexAgent.framework/$compatibilityPath"
    }.toSet()
    compatibilityPaths.forEach { path ->
        check(Files.mismatch(
            referenceFiles.getValue(path).toPath(), packageFiles.getValue(compatibilityPath).toPath(),
        ) == -1L) { "Verified Apple Swift package compatibility differs from its XCFramework" }
    }
    // The existing XCFramework ZIP adds exactly these two resources; the Swift ZIP retains
    // the original framework and carries the same declaration once at package root.
    val expectedFrameworkFiles = referenceFiles.filterKeys { it !in compatibilityPaths }
    val frameworkFiles = verifiedRegularFiles(extracted.resolve("CodexAgent.xcframework"))
    check(frameworkFiles.keys == expectedFrameworkFiles.keys && frameworkFiles.all { (path, file) ->
        Files.mismatch(file.toPath(), expectedFrameworkFiles.getValue(path).toPath()) == -1L
    }) { "Verified Apple Swift package framework differs from its XCFramework artifact" }
    deleteReleaseTree(outputDirectory)
    copyReleaseTree(extracted, outputDirectory)
    verifiedRegularFiles(outputDirectory)
}

@CacheableTask
abstract class ImportVerifiedCodexAgentSwiftPackageTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val evidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val verificationReceipt: RegularFileProperty
    @get:Input abstract val version: Property<String>
    @get:OutputDirectory abstract val packageDirectory: DirectoryProperty

    @TaskAction
    fun importPackage() = extractVerifiedAppleSwiftPackage(
        evidenceDirectory.get().asFile,
        verificationReceipt.get().asFile,
        version.get(),
        temporaryDir,
        packageDirectory.get().asFile,
    )
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
        verifyImportedAppleFramework(source, platformName.get()) { capture(*it.toTypedArray()) }
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
            commandLine(importedXCFrameworkAssemblyCommand(
                deviceFrameworkDirectory.get().asFile, simulatorFrameworkDirectory.get().asFile, output,
            ))
        }.assertNormalExitValue()
    }
}
