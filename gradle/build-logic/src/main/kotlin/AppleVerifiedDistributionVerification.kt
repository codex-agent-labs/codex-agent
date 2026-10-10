import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import kotlinx.serialization.json.JsonObject

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

internal fun appleProofProducerIdentity(proof: JsonObject): Pair<String, String> {
    val commit = proof.releaseString("candidateCommit")
    val tree = proof.releaseString("candidateTree")
    check(listOf(commit, tree).all { value ->
        value.length == 40 && value.all { it in '0'..'9' || it in 'a'..'f' }
    }) { "Apple proof producer Git identity is invalid" }
    return commit to tree
}

internal fun verifyApplePackageRecordGroup(
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

internal fun sameApplePackageFiles(expected: Map<String, File>, source: File, captured: File): Boolean {
    val current = verifiedRegularFiles(source)
    val held = verifiedRegularFiles(captured)
    return current.keys == expected.keys && held.keys == expected.keys && expected.keys.all { path ->
        Files.mismatch(current.getValue(path).toPath(), held.getValue(path).toPath()) == -1L
    }
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

internal fun requireApplePackagePathWithoutSymlinks(file: File, role: String) {
    var current: File? = file.absoluteFile
    while (current != null) {
        check(!Files.isSymbolicLink(current.toPath())) {
            "Imported Apple SDK $role path has a symbolic parent: $current"
        }
        current = current.parentFile
    }
}

internal fun copyVerified(source: File, destination: File): File {
    check(source.isFile && !Files.isSymbolicLink(source.toPath())) { "Verified Apple input is missing or unsafe: $source" }
    destination.parentFile.mkdirs()
    Files.copy(source.toPath(), destination.toPath(), REPLACE_EXISTING)
    return destination
}
