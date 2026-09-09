import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.charset.StandardCharsets.UTF_8
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import javax.inject.Inject
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.LocalState
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

@DisableCachingByDefault(because = "Exports fresh exact-main verification evidence")
abstract class ExportAppleVerifiedDistributionTask @Inject constructor(
    private val exec: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val candidateCommit: Property<String>
    @get:Input abstract val version: Property<String>
    @get:Input abstract val freshSemanticVerification: Property<Boolean>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val applePackageArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val swiftPackageArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val swiftPackageChecksum: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val privacyReviewFile: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reportFiles: ConfigurableFileCollection
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val xcodeVersionFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val swiftVersionFile: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE) abstract val nativeEvidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val nativeEvidenceReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val nativeProvenance: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageSwift: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val sdkCompatibility: RegularFileProperty
    @get:Internal abstract val repositoryDirectory: DirectoryProperty
    @get:Internal abstract val canonicalBuildDirectory: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun export() {
        check(freshSemanticVerification.get()) { "Verified Apple distribution cannot be re-exported from imported evidence" }
        val repository = repositoryDirectory.get().asFile.canonicalFile
        val (commit, tree) = verifyAppleEvidenceCheckout(exec, repository, candidateCommit.get())
        val output = outputDirectory.get().asFile
        deleteReleaseTree(output); output.mkdirs()
        val artifacts = listOf(
            applePackageArchive.get().asFile,
            swiftPackageArchive.get().asFile,
            swiftPackageChecksum.get().asFile,
        ).associate { input -> input.name to copyVerified(input, output.resolve(input.name)) }
        val build = canonicalBuildDirectory.get().asFile.canonicalFile
        val reports = appleVerifiedReportLayout.mapValues { (destination, source) ->
            val input = if (destination.endsWith("privacy-required-reason-review.json"))
                privacyReviewFile.get().asFile else build.resolve(source)
            copyVerified(input, output.resolve(destination))
        }
        check(reportFiles.files.map(File::getCanonicalFile).toSet() ==
            appleVerifiedReportLayout.map { (destination, source) ->
                if (destination.endsWith("privacy-required-reason-review.json"))
                    privacyReviewFile.get().asFile.canonicalFile else build.resolve(source).canonicalFile
            }.toSet()) { "Verified Apple report inputs do not match the canonical report layout" }
        val toolchain = linkedMapOf(
            "toolchain/xcode.txt" to copyVerified(xcodeVersionFile.get().asFile, output.resolve("toolchain/xcode.txt")),
            "toolchain/swift.txt" to copyVerified(swiftVersionFile.get().asFile, output.resolve("toolchain/swift.txt")),
        )
        val nativeEvidence = verifiedRegularFiles(nativeEvidenceDirectory.get().asFile)
        val receipts = mapOf(
            IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT to copyVerified(
                nativeEvidenceReceipt.get().asFile,
                output.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT),
            ),
        )
        val identity = AppleVerifiedDistributionIdentity(
            commit, tree, version.get(), nativeProvenance.get().asFile.releaseDigest(),
            packageSwift.get().asFile.releaseDigest(),
            receipts.getValue(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).releaseDigest(),
            sdkCompatibility.get().asFile.releaseDigest(),
        )
        output.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).atomicWriteJson(
            buildAppleVerifiedDistributionProof(identity, artifacts, reports, toolchain, nativeEvidence, receipts),
        )
    }
}

@DisableCachingByDefault(because = "Validates transported evidence and restores canonical candidate inputs")
abstract class ImportAppleVerifiedDistributionTask @Inject constructor(
    private val exec: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val candidateCommit: Property<String>
    @get:Input abstract val version: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE) abstract val evidenceDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE) abstract val nativeEvidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val nativeEvidenceReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val nativeProvenance: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageSwift: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val sdkCompatibility: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val currentXcodeVersionFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val currentSwiftVersionFile: RegularFileProperty
    @get:Internal abstract val repositoryDirectory: DirectoryProperty
    @get:Internal abstract val canonicalBuildDirectory: DirectoryProperty
    @get:OutputFile abstract val verificationReceipt: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun importEvidence() {
        val repository = repositoryDirectory.get().asFile.canonicalFile
        val (consumerCommit, consumerTree) = verifyAppleEvidenceCheckout(exec, repository, candidateCommit.get())
        val sourceFiles = verifiedRegularFiles(evidenceDirectory.get().asFile)
        val sourceProof = sourceFiles[IOS_VERIFIED_DISTRIBUTION_PROOF]
            ?: error("Verified Apple distribution proof is missing")
        val proof = sourceProof.readReleaseObject()
        val schema = proof.releaseInt("schemaVersion")
        val (producerCommit, producerTree) = appleProofProducerIdentity(proof)
        val currentNativeReceipt = nativeEvidenceReceipt.get().asFile
        val originalNativeReceipt = if (schema == 1) {
            check(producerCommit == consumerCommit && producerTree == consumerTree) {
                "Legacy Apple distribution proof cannot cross producer and consumer identities"
            }
            currentNativeReceipt
        } else {
            check(schema == 2) { "Unsupported verified Apple distribution proof schema" }
            verifyHistoricalAppleProducer(exec, repository, producerCommit, producerTree)
            sourceFiles[IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT]
                ?: error("Verified Apple distribution original native receipt is missing")
        }
        verifyAppleNativeEvidenceReceiptReuse(
            originalNativeReceipt,
            currentNativeReceipt,
            producerCommit,
            producerTree,
            consumerCommit,
            consumerTree,
        )
        val identity = AppleVerifiedDistributionIdentity(
            producerCommit, producerTree, version.get(), nativeProvenance.get().asFile.releaseDigest(),
            packageSwift.get().asFile.releaseDigest(), originalNativeReceipt.releaseDigest(),
            sdkCompatibility.get().asFile.releaseDigest(),
        )
        val inventory = verifyAppleVerifiedDistribution(
            evidenceDirectory.get().asFile, nativeEvidenceDirectory.get().asFile, identity,
        )
        check(Files.mismatch(
            currentXcodeVersionFile.get().asFile.toPath(), inventory.toolchain.getValue("toolchain/xcode.txt").toPath(),
        ) == -1L) { "Imported Apple distribution Xcode identity mismatch" }
        check(Files.mismatch(
            currentSwiftVersionFile.get().asFile.toPath(), inventory.toolchain.getValue("toolchain/swift.txt").toPath(),
        ) == -1L) { "Imported Apple distribution Swift identity mismatch" }
        val build = canonicalBuildDirectory.get().asFile
        inventory.artifacts.forEach { (path, file) -> copyVerified(file, build.resolve("distributions/$path")) }
        inventory.reports.forEach { (path, file) ->
            copyVerified(file, build.resolve(appleVerifiedReportLayout.getValue(path)))
        }
        inventory.toolchain.forEach { (path, file) ->
            copyVerified(file, build.resolve(appleVerifiedToolchainLayout.getValue(path)))
        }
        inventory.receipts.forEach { (path, file) ->
            copyVerified(file, build.resolve("imported-verified-apple/$path"))
        }
        verificationReceipt.get().asFile.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(2))
            put("protocol", JsonPrimitive("codex-agent-ios-verified-distribution-import-v2"))
            put("result", JsonPrimitive("passed"))
            put("producerCommit", JsonPrimitive(producerCommit))
            put("producerTree", JsonPrimitive(producerTree))
            put("consumerCommit", JsonPrimitive(consumerCommit))
            put("consumerTree", JsonPrimitive(consumerTree))
            put("sourceProofSha256", JsonPrimitive(inventory.proof.releaseDigest()))
            put("originalNativeEvidenceReceiptSha256", JsonPrimitive(originalNativeReceipt.releaseDigest()))
            put("currentNativeEvidenceReceiptSha256", JsonPrimitive(currentNativeReceipt.releaseDigest()))
        })
    }
}

private val appleNativeEvidenceReceiptKeys = setOf(
    "schemaVersion", "protocol", "result", "candidateCommit", "candidateTree", "cleanCheckout",
    "nativeInputsSha256", "nativeProvenanceSha256", "compilerSettingsSha256", "rustToolchain",
    "rustSrcComponent", "rustCompilerIdentitySha256", "xcodeVersionSha256", "swiftVersionSha256",
    "nativeTestsProofSha256", "slices",
)

internal fun verifyAppleNativeEvidenceReceiptReuse(
    originalFile: File,
    currentFile: File,
    producerCommit: String,
    producerTree: String,
    consumerCommit: String,
    consumerTree: String,
) {
    val original = originalFile.readReleaseObject()
    val current = currentFile.readReleaseObject()
    listOf(original, current).forEach { receipt ->
        check(receipt.keys == appleNativeEvidenceReceiptKeys &&
            receipt.releaseInt("schemaVersion") == 2 &&
            receipt.releaseString("protocol") == "codex-agent-ios-native-evidence-v2" &&
            receipt.releaseString("result") == "passed" && receipt.releaseBoolean("cleanCheckout")) {
            "Apple native evidence receipt is invalid"
        }
    }
    check(original.releaseString("candidateCommit") == producerCommit &&
        original.releaseString("candidateTree") == producerTree &&
        current.releaseString("candidateCommit") == consumerCommit &&
        current.releaseString("candidateTree") == consumerTree) {
        "Apple native evidence receipt producer or consumer identity mismatch"
    }
    val identityFields = setOf("candidateCommit", "candidateTree")
    check(original.filterKeys { it !in identityFields } == current.filterKeys { it !in identityFields }) {
        "Apple native evidence changed between producer and consumer"
    }
}

private fun verifyHistoricalAppleProducer(
    exec: ExecOperations,
    repository: File,
    commit: String,
    tree: String,
) {
    val output = ByteArrayOutputStream()
    exec.exec {
        workingDir(repository)
        commandLine("git", "rev-parse", "$commit^{commit}", "$commit^{tree}")
        standardOutput = output
    }.assertNormalExitValue()
    check(output.toString(UTF_8).lineSequence().filter(String::isNotBlank).toList() == listOf(commit, tree)) {
        "Verified Apple distribution producer commit/tree mismatch"
    }
}

@CacheableTask
abstract class StageImportedAppleSdkPackageArtifactsTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val evidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val verificationReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val nativeEvidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val nativeEvidenceReceipt: RegularFileProperty
    @get:Input abstract val version: Property<String>
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty
    @get:LocalState abstract val workDirectory: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:OutputDirectory abstract val validationEvidenceDirectory: DirectoryProperty

    @TaskAction
    fun stage() = stageImportedAppleSdkPackageArtifacts(
        evidenceDirectory.get().asFile,
        verificationReceipt.get().asFile,
        sdkCompatibility.get().asFile,
        nativeEvidenceDirectory.get().asFile,
        nativeEvidenceReceipt.get().asFile,
        version.get(),
        ownedBuildDirectory.get().asFile,
        workDirectory.get().asFile,
        outputDirectory.get().asFile,
        validationEvidenceDirectory.get().asFile,
    )
}

internal fun stageImportedAppleSdkPackageArtifacts(
    evidenceDirectory: File,
    verificationReceipt: File,
    sdkCompatibility: File,
    nativeEvidenceDirectory: File,
    nativeEvidenceReceipt: File,
    version: String,
    ownedBuildDirectory: File,
    temporaryDirectory: File,
    outputDirectory: File,
    validationEvidenceDirectory: File,
) {
    listOf(
        evidenceDirectory, verificationReceipt, sdkCompatibility,
        nativeEvidenceDirectory, nativeEvidenceReceipt,
    ).forEach {
        requireApplePackagePathWithoutSymlinks(it, "input")
    }
    listOf(
        ownedBuildDirectory, temporaryDirectory, outputDirectory, validationEvidenceDirectory,
    ).forEach {
        requireApplePackagePathWithoutSymlinks(it, "owned")
    }
    val evidence = evidenceDirectory.canonicalFile
    val receipt = verificationReceipt.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val nativeEvidence = nativeEvidenceDirectory.canonicalFile
    val nativeReceipt = nativeEvidenceReceipt.canonicalFile
    val ownedRoot = ownedBuildDirectory.canonicalFile
    val temporary = temporaryDirectory.canonicalFile
    val output = outputDirectory.canonicalFile
    val validationOutput = validationEvidenceDirectory.canonicalFile
    listOf(evidence, nativeEvidence).forEach { input ->
        check(input.isDirectory && !Files.isSymbolicLink(input.toPath())) {
            "Imported Apple SDK evidence is missing or unsafe: $input"
        }
    }
    listOf(receipt, compatibility, nativeReceipt).forEach { input ->
        check(input.isFile && !Files.isSymbolicLink(input.toPath())) {
            "Imported Apple SDK input is missing or unsafe: ${input.name}"
        }
    }
    check(!ownedRoot.exists() || ownedRoot.isDirectory) {
        "Imported Apple SDK owned build path is not a directory: $ownedRoot"
    }
    val ownedOutputs = listOf(temporary, output, validationOutput)
    ownedOutputs.forEach { owned ->
        check(owned.toPath() != ownedRoot.toPath() &&
            owned.toPath().startsWith(ownedRoot.toPath())) {
            "Imported Apple SDK output is outside its owned build directory: $owned"
        }
        check(!Files.exists(owned.toPath(), LinkOption.NOFOLLOW_LINKS) ||
            !Files.isSymbolicLink(owned.toPath())) {
            "Imported Apple SDK output is a symbolic link: $owned"
        }
        listOf(evidence, receipt, compatibility, nativeEvidence, nativeReceipt).forEach { input ->
            check(!owned.toPath().startsWith(input.toPath()) && !input.toPath().startsWith(owned.toPath())) {
                "Imported Apple SDK output overlaps an input: $owned"
            }
        }
    }
    ownedOutputs.forEachIndexed { index, left -> ownedOutputs.drop(index + 1).forEach { right ->
        check(!left.toPath().startsWith(right.toPath()) && !right.toPath().startsWith(left.toPath())) {
            "Imported Apple SDK owned directories overlap: $left and $right"
        }
    } }

    val sourceFiles = verifiedRegularFiles(evidence)
    val nativeFiles = verifiedRegularFiles(nativeEvidence)
    check(nativeFiles.isNotEmpty()) {
        "Imported Apple native evidence is empty"
    }

    // Resolve and validate every source before invalidating either owned destination.
    val receiptBytes = receipt.readBytes()
    val compatibilityBytes = compatibility.readBytes()
    val nativeReceiptBytes = nativeReceipt.readBytes()
    ownedRoot.mkdirs()
    deleteReleaseTree(temporary)
    val capturedEvidence = temporary.resolve("verified-distribution").apply { mkdirs() }
    sourceFiles.forEach { (path, source) -> copyVerified(source, capturedEvidence.resolve(path)) }
    val capturedNativeEvidence = temporary.resolve("current-native-evidence").apply { mkdirs() }
    nativeFiles.forEach { (path, source) -> copyVerified(source, capturedNativeEvidence.resolve(path)) }
    val capturedReceipt = temporary.resolve("verification-receipt.json")
    capturedReceipt.writeBytes(receiptBytes)
    val capturedNativeReceipt = temporary.resolve("current-native-evidence-receipt.json")
    capturedNativeReceipt.writeBytes(nativeReceiptBytes)
    val capturedCompatibility = temporary.resolve("sdk-compatibility.json")
    capturedCompatibility.writeBytes(compatibilityBytes)
    val names = listOf(
        "CodexAgentPackage-$version.zip",
        "CodexAgent-$version.xcframework.zip",
        "CodexAgent-$version.xcframework.zip.sha256",
    )
    val sourceProof = sourceFiles[IOS_VERIFIED_DISTRIBUTION_PROOF]
        ?: error("Verified Apple distribution proof is missing")
    val capturedProof = capturedEvidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    val capturedSourceFiles = verifiedRegularFiles(capturedEvidence)
    val capturedNativeFiles = verifiedRegularFiles(capturedNativeEvidence)
    val importReceipt = capturedReceipt.readReleaseObject()
    val originalNativeReceipt = capturedEvidence.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
    check(importReceipt.releaseInt("schemaVersion") == 2 && originalNativeReceipt.isFile &&
        originalNativeReceipt.releaseDigest() ==
        importReceipt.releaseString("originalNativeEvidenceReceiptSha256") &&
        capturedNativeReceipt.releaseDigest() ==
        importReceipt.releaseString("currentNativeEvidenceReceiptSha256")) {
        "Imported Apple SDK native receipt closure mismatch"
    }
    val proofObject = capturedProof.readReleaseObject()
    val artifactValues = proofObject.releaseArray("artifacts")
    val artifactRecords = artifactValues.map { value ->
        value as? JsonObject ?: error("Verified Apple artifact record is invalid")
    }
    check(artifactRecords.size == names.size) { "Verified Apple artifact inventory is incomplete" }
    val captured = names.associateWith { name ->
        val source = sourceFiles[name] ?: error("Verified Apple archive is missing: $name")
        val record = artifactRecords.singleOrNull { it.releaseString("fileName") == name }
            ?: error("Verified Apple artifact record is missing or duplicated: $name")
        check(record.keys == setOf("fileName", "bytes", "sha256")) {
            "Verified Apple artifact record is invalid: $name"
        }
        val destination = capturedEvidence.resolve(name)
        verifyReleaseRecord(destination, record)
        destination
    }
    val distributionRecords = listOf("artifacts", "reports", "toolchain", "receipts").flatMap {
        verifyApplePackageRecordGroup(proofObject, it, capturedSourceFiles)
    }
    check(distributionRecords.size == distributionRecords.toSet().size &&
        distributionRecords.toSet() + IOS_VERIFIED_DISTRIBUTION_PROOF == sourceFiles.keys) {
        "Imported Apple distribution closure inventory mismatch"
    }
    check(verifyApplePackageRecordGroup(proofObject, "nativeEvidence", capturedNativeFiles) == nativeFiles.keys) {
        "Imported Apple native evidence closure inventory mismatch"
    }
    val packageDirectory = temporary.resolve("verified-package")
    extractVerifiedAppleSwiftPackage(
        capturedEvidence,
        capturedReceipt,
        version,
        temporary.resolve("package-verification"),
        packageDirectory,
    )
    check(Files.mismatch(
        packageDirectory.resolve("META-INF/codex-agent/sdk-compatibility.json").toPath(),
        capturedCompatibility.toPath(),
    ) == -1L) { "Imported Apple SDK compatibility differs from the authoritative declaration" }
    val archive = captured.getValue("CodexAgent-$version.xcframework.zip")
    val checksum = captured.getValue("CodexAgent-$version.xcframework.zip.sha256")
    check(checksum.readBytes().contentEquals("${archive.releaseDigest()}\n".toByteArray())) {
        "Imported Apple SDK checksum is not exact"
    }
    check(sameApplePackageFiles(sourceFiles, evidence, capturedEvidence) &&
        sameApplePackageFiles(nativeFiles, nativeEvidence, capturedNativeEvidence) &&
        Files.mismatch(receipt.toPath(), capturedReceipt.toPath()) == -1L &&
        Files.mismatch(nativeReceipt.toPath(), capturedNativeReceipt.toPath()) == -1L &&
        Files.mismatch(compatibility.toPath(), capturedCompatibility.toPath()) == -1L &&
        Files.mismatch(sourceProof.toPath(), capturedProof.toPath()) == -1L) {
        "Imported Apple SDK input changed while it was being verified"
    }

    val staged = temporary.resolve("staged-product").apply { mkdirs() }
    captured.forEach { (name, source) -> Files.copy(source.toPath(), staged.resolve(name).toPath()) }
    val stagedValidation = temporary.resolve("staged-validation").apply { mkdirs() }
    val validationSources = buildMap {
        sourceFiles.keys.filter { it !in names }.forEach { path ->
            put("verified-distribution/$path", capturedEvidence.resolve(path))
        }
        nativeFiles.keys.forEach { path ->
            put("current-native-evidence/$path", capturedNativeEvidence.resolve(path))
        }
        put("receipts/verified-distribution-import.json", capturedReceipt)
        put("receipts/current-ios-native-evidence.json", capturedNativeReceipt)
    }
    validationSources.forEach { (path, source) -> copyVerified(source, stagedValidation.resolve(path)) }
    deleteReleaseTree(output)
    copyReleaseTree(staged, output)
    deleteReleaseTree(validationOutput)
    copyReleaseTree(stagedValidation, validationOutput)
    val published = verifiedRegularFiles(output)
    check(published.keys == names.toSet() && published.all { (name, file) ->
        Files.mismatch(file.toPath(), captured.getValue(name).toPath()) == -1L
    }) { "Imported Apple SDK package artifact copy changed" }
    val publishedValidation = verifiedRegularFiles(validationOutput)
    check(publishedValidation.keys == validationSources.keys && publishedValidation.all { (path, file) ->
        Files.mismatch(file.toPath(), validationSources.getValue(path).toPath()) == -1L
    }) {
        "Imported Apple SDK validation evidence inventory changed"
    }
}

private fun verifyApplePackageRecordGroup(
    proof: JsonObject,
    name: String,
    available: Map<String, File>,
): Set<String> = proof.releaseArray(name).map { value ->
    val record = value as? JsonObject ?: error("Imported Apple $name record is invalid")
    check(record.keys == setOf("fileName", "bytes", "sha256")) {
        "Imported Apple $name record is invalid"
    }
    val path = record.releaseString("fileName")
    val file = available[path] ?: error("Imported Apple $name file is missing: $path")
    verifyReleaseRecord(file, record)
    path
}.also { paths ->
    check(paths.size == paths.toSet().size) { "Imported Apple $name records are duplicated" }
}.toSet()

private fun sameApplePackageFiles(expected: Map<String, File>, source: File, captured: File): Boolean {
    val current = verifiedRegularFiles(source)
    val held = verifiedRegularFiles(captured)
    return current.keys == expected.keys && held.keys == expected.keys && expected.keys.all { path ->
        Files.mismatch(current.getValue(path).toPath(), held.getValue(path).toPath()) == -1L
    }
}

@DisableCachingByDefault(because = "Verifies transported Apple package and external evidence without producing content")
abstract class VerifyTransportedAppleSdkPackageClosureTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val productDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val validationEvidenceDirectory: DirectoryProperty
    // These expectations must come from an independently authenticated caller;
    // configuring them does not itself authorize the transported closure.
    @get:Optional @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val expectedSdkCompatibility: RegularFileProperty
    @get:Optional @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val expectedDistributionProof: RegularFileProperty
    @get:Input abstract val version: Property<String>
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty
    @get:LocalState abstract val workDirectory: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun verify() = verifyTransportedAppleSdkPackageClosure(
        productDirectory.get().asFile,
        validationEvidenceDirectory.get().asFile,
        version.get(),
        ownedBuildDirectory.get().asFile,
        workDirectory.get().asFile,
        expectedSdkCompatibility.orNull?.asFile,
        expectedDistributionProof.orNull?.asFile,
    )
}

internal fun verifyTransportedAppleSdkPackageClosure(
    productDirectory: File,
    validationEvidenceDirectory: File,
    version: String,
    ownedBuildDirectory: File,
    workDirectory: File,
    expectedSdkCompatibility: File? = null,
    expectedDistributionProof: File? = null,
) {
    check(PRODUCT_SEMVER.matches(version)) { "Transported Apple SDK version is invalid" }
    check((expectedSdkCompatibility == null) == (expectedDistributionProof == null)) {
        "Transported Apple SDK caller expectations must be supplied together"
    }
    val expectedInputs = listOfNotNull(expectedSdkCompatibility, expectedDistributionProof)
    (listOf(productDirectory, validationEvidenceDirectory) + expectedInputs).forEach {
        requireApplePackagePathWithoutSymlinks(it, "transported input")
    }
    listOf(ownedBuildDirectory, workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "verification work")
    }
    val product = productDirectory.canonicalFile
    val validation = validationEvidenceDirectory.canonicalFile
    val expectedCompatibility = expectedSdkCompatibility?.canonicalFile
    val expectedProof = expectedDistributionProof?.canonicalFile
    val ownedRoot = ownedBuildDirectory.canonicalFile
    val work = workDirectory.canonicalFile
    listOfNotNull(expectedCompatibility, expectedProof).forEach { input ->
        check(input.isFile && !Files.isSymbolicLink(input.toPath())) {
            "Transported Apple SDK caller expectation is missing or unsafe: $input"
        }
    }
    val productFiles = verifiedRegularFiles(product)
    val validationFiles = verifiedRegularFiles(validation)
    check(productFiles.keys == appleVerifiedArtifactNames(version)) {
        "Transported Apple SDK product inventory mismatch"
    }
    check((!ownedRoot.exists() || ownedRoot.isDirectory) && work.toPath() != ownedRoot.toPath() &&
        work.toPath().startsWith(ownedRoot.toPath()) &&
        !work.toPath().startsWith(product.toPath()) && !product.toPath().startsWith(work.toPath()) &&
        !work.toPath().startsWith(validation.toPath()) && !validation.toPath().startsWith(work.toPath()) &&
        listOfNotNull(expectedCompatibility, expectedProof).all { input ->
            !work.toPath().startsWith(input.toPath()) && !input.toPath().startsWith(work.toPath())
        }) {
        "Transported Apple SDK verification work directory is unsafe"
    }
    val protectedRoots = listOf(File(System.getProperty("user.home")).canonicalFile, File(".").canonicalFile)
    check(protectedRoots.none { protected ->
        protected.toPath() == work.toPath() || protected.toPath().startsWith(work.toPath())
    }) { "Transported Apple SDK verification work directory is too broad" }
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS) || !Files.isSymbolicLink(work.toPath())) {
        "Transported Apple SDK verification work directory is a symbolic link"
    }

    val importReceiptPath = "receipts/verified-distribution-import.json"
    val currentNativeReceiptPath = "receipts/current-ios-native-evidence.json"
    val distributionPrefix = "verified-distribution/"
    val nativePrefix = "current-native-evidence/"
    val distributionFiles = validationFiles.filterKeys { it.startsWith(distributionPrefix) }
        .mapKeys { (path, _) -> path.removePrefix(distributionPrefix) }
    val nativeFiles = validationFiles.filterKeys { it.startsWith(nativePrefix) }
        .mapKeys { (path, _) -> path.removePrefix(nativePrefix) }
    check(distributionFiles.keys.intersect(productFiles.keys).isEmpty()) {
        "Transported Apple SDK product is duplicated in external validation evidence"
    }
    check(distributionFiles.isNotEmpty() && nativeFiles.isNotEmpty() &&
        validationFiles.keys == distributionFiles.keys.map { "$distributionPrefix$it" }.toSet() +
        nativeFiles.keys.map { "$nativePrefix$it" } + setOf(importReceiptPath, currentNativeReceiptPath)) {
        "Transported Apple SDK validation evidence inventory mismatch"
    }

    val expectedCompatibilityBytes = expectedCompatibility?.readBytes()
    val expectedProofBytes = expectedProof?.readBytes()
    ownedRoot.mkdirs()
    deleteReleaseTree(work)
    val capturedProduct = work.resolve("product").apply { mkdirs() }
    productFiles.forEach { (path, file) -> copyVerified(file, capturedProduct.resolve(path)) }
    val capturedValidation = work.resolve("validation").apply { mkdirs() }
    validationFiles.forEach { (path, file) -> copyVerified(file, capturedValidation.resolve(path)) }
    val capturedExpectedCompatibility = expectedCompatibilityBytes?.let { bytes ->
        work.resolve("caller-expected/sdk-compatibility.json").apply {
            parentFile.mkdirs()
            writeBytes(bytes)
        }
    }
    val capturedExpectedProof = expectedProofBytes?.let { bytes ->
        work.resolve("caller-expected/verified-distribution-proof.json").apply {
            parentFile.mkdirs()
            writeBytes(bytes)
        }
    }
    val reconstructed = work.resolve("verified-distribution").apply { mkdirs() }
    productFiles.keys.forEach { path -> copyVerified(capturedProduct.resolve(path), reconstructed.resolve(path)) }
    distributionFiles.keys.forEach { path ->
        copyVerified(capturedValidation.resolve("$distributionPrefix$path"), reconstructed.resolve(path))
    }
    val capturedNative = work.resolve("current-native-evidence").apply { mkdirs() }
    nativeFiles.keys.forEach { path ->
        copyVerified(capturedValidation.resolve("$nativePrefix$path"), capturedNative.resolve(path))
    }
    val importReceipt = capturedValidation.resolve(importReceiptPath).readReleaseObject()
    val currentNativeReceipt = capturedValidation.resolve(currentNativeReceiptPath)
    val proofFile = reconstructed.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    val proof = proofFile.readReleaseObject()
    if (capturedExpectedProof != null) {
        check(Files.mismatch(proofFile.toPath(), capturedExpectedProof.toPath()) == -1L) {
            "Transported Apple SDK distribution proof differs from the caller expectation"
        }
    }
    val receiptKeys = setOf(
        "schemaVersion", "protocol", "result", "producerCommit", "producerTree",
        "consumerCommit", "consumerTree", "sourceProofSha256",
        "originalNativeEvidenceReceiptSha256", "currentNativeEvidenceReceiptSha256",
    )
    check(importReceipt.keys == receiptKeys && importReceipt.releaseInt("schemaVersion") == 2 &&
        importReceipt.releaseString("protocol") == "codex-agent-ios-verified-distribution-import-v2" &&
        importReceipt.releaseString("result") == "passed" &&
        proofFile.releaseDigest() == importReceipt.releaseString("sourceProofSha256")) {
        "Transported Apple SDK import receipt is invalid"
    }
    val (producerCommit, producerTree) = appleProofProducerIdentity(proof)
    val consumerCommit = importReceipt.releaseString("consumerCommit")
    val consumerTree = importReceipt.releaseString("consumerTree")
    check(importReceipt.releaseString("producerCommit") == producerCommit &&
        importReceipt.releaseString("producerTree") == producerTree &&
        listOf(consumerCommit, consumerTree).all { it.matches(Regex("[0-9a-f]{40}")) }) {
        "Transported Apple SDK producer or consumer identity mismatch"
    }
    val originalNativeReceipt = reconstructed.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
    check(originalNativeReceipt.releaseDigest() ==
        importReceipt.releaseString("originalNativeEvidenceReceiptSha256") &&
        currentNativeReceipt.releaseDigest() ==
        importReceipt.releaseString("currentNativeEvidenceReceiptSha256")) {
        "Transported Apple SDK native receipt digest mismatch"
    }
    verifyAppleNativeEvidenceReceiptReuse(
        originalNativeReceipt, currentNativeReceipt,
        producerCommit, producerTree, consumerCommit, consumerTree,
    )
    verifyAppleVerifiedDistribution(
        reconstructed,
        capturedNative,
        AppleVerifiedDistributionIdentity(
            producerCommit,
            producerTree,
            version,
            proof.releaseString("nativeProvenanceSha256"),
            proof.releaseString("packageSwiftSha256"),
            originalNativeReceipt.releaseDigest(),
            capturedExpectedCompatibility?.releaseDigest()
                ?: proof.releaseString("sdkCompatibilitySha256"),
        ),
    )
    check(sameApplePackageFiles(productFiles, product, capturedProduct) &&
        sameApplePackageFiles(validationFiles, validation, capturedValidation) &&
        (expectedCompatibility == null || Files.mismatch(
            expectedCompatibility.toPath(), capturedExpectedCompatibility!!.toPath(),
        ) == -1L) &&
        (expectedProof == null || Files.mismatch(
            expectedProof.toPath(), capturedExpectedProof!!.toPath(),
        ) == -1L)) {
        "Transported Apple SDK inputs changed during verification"
    }
}

private fun requireApplePackagePathWithoutSymlinks(file: File, role: String) {
    var current: File? = file.absoluteFile
    while (current != null) {
        check(!Files.isSymbolicLink(current.toPath())) {
            "Imported Apple SDK $role path has a symbolic parent: $current"
        }
        current = current.parentFile
    }
}

private fun copyVerified(source: File, destination: File): File {
    check(source.isFile && !Files.isSymbolicLink(source.toPath())) { "Verified Apple input is missing or unsafe: $source" }
    destination.parentFile.mkdirs()
    Files.copy(source.toPath(), destination.toPath(), REPLACE_EXISTING)
    return destination
}
