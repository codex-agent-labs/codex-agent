import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Replays the complete Firebase Android evidence gate against a protected input
 * binding.  The caller must authenticate the intermediate Firebase transport,
 * its source commit/tree, the original lane receipt, and [expectedReleaseAar].
 * This comparison grants no receipt, producer, Firebase-host, or source trust.
 */
internal fun verifyOriginalFirebaseAndroidEvidence(
    evidenceDirectory: File,
    protectedObservationDirectory: File,
    expectedReleaseAar: File,
    expectedCandidateCommit: String,
    expectedCandidateTree: String,
    expectedTrustedSourceCommit: String,
    expectedTrustedSourceTree: String,
    applicationId: (File) -> String,
    testIdentity: (File) -> AndroidManifestIdentity,
): FirebaseAndroidEvidenceVerification {
    val evidence = evidenceDirectory.absoluteFile
    val observation = protectedObservationDirectory.absoluteFile
    val expectedAar = expectedReleaseAar.absoluteFile
    listOf(evidence, observation, expectedAar).forEach {
        requireAndroidOriginalPathWithoutSymlinks(it)
    }
    check(evidence.canonicalFile == evidence && observation.canonicalFile == observation &&
        expectedAar.canonicalFile == expectedAar && evidence != observation &&
        evidence.toPath().let { path -> !observation.toPath().startsWith(path) } &&
        observation.toPath().let { path -> !evidence.toPath().startsWith(path) } &&
        expectedAar.toPath().let { path -> !path.startsWith(evidence.toPath()) && !path.startsWith(observation.toPath()) }
    ) { "Original Firebase Android inputs are not normalized and disjoint" }
    check(expectedCandidateCommit.isGitOid() && expectedCandidateTree.isGitOid() &&
        expectedTrustedSourceCommit.isGitOid() && expectedTrustedSourceTree.isGitOid()) {
        "Original Firebase Android expected Git identities are invalid"
    }
    check(expectedAar.isFile && expectedAar.name == FIREBASE_RELEASE_AAR) {
        "Original Firebase Android expected release AAR is missing or misnamed"
    }

    fun digests(root: File) = verifiedRegularFiles(root).mapValues { (_, file) -> file.releaseDigest() }
    val evidenceBefore = digests(evidence)
    val observationBefore = digests(observation)
    val expectedAarSize = expectedAar.length()
    val expectedAarDigest = expectedAar.releaseDigest()
    val expectedEvidence = candidateFirebaseAndroidEvidenceFileNames.toSet()
    check(evidenceBefore.keys == expectedEvidence) {
        "Original Firebase Android final evidence inventory is invalid"
    }
    check(observationBefore.keys.containsAll(setOf(
        "input-binding.json", "lane-receipt.json", "matrix.json",
    )) && observationBefore.keys.subtract(setOf(
        "input-binding.json", "lane-receipt.json", "matrix.json",
    )).let { results -> results.isNotEmpty() && results.all { it.startsWith("results/") && it.endsWith(".xml") } }) {
        "Original Firebase Android protected observation inventory is invalid"
    }

    try {
        val bindingFile = observation.resolve("input-binding.json")
        check(bindingFile.length() in 1..64 * 1024) {
            "Original Firebase Android input binding size is invalid"
        }
        val bindingText = bindingFile.readText()
        val binding = releaseJson.parseToJsonElement(bindingText) as? JsonObject
            ?: error("Original Firebase Android input binding is not an object")
        check(bindingText == Json.encodeToString(JsonElement.serializer(), binding) + "\n" &&
            binding.keys.toList() == binding.keys.sorted()) {
            "Original Firebase Android input binding is not canonical JSON"
        }
        check(binding.keys == setOf(
            "schemaVersion", "kind", "candidateCommit", "candidateTree",
            "trustedSourceCommit", "trustedSourceTree", "files",
        ) && binding["schemaVersion"] == kotlinx.serialization.json.JsonPrimitive(1) &&
            binding["kind"] == kotlinx.serialization.json.JsonPrimitive("firebase-android-input-binding") &&
            binding["candidateCommit"] == kotlinx.serialization.json.JsonPrimitive(expectedCandidateCommit) &&
            binding["candidateTree"] == kotlinx.serialization.json.JsonPrimitive(expectedCandidateTree) &&
            binding["trustedSourceCommit"] == kotlinx.serialization.json.JsonPrimitive(expectedTrustedSourceCommit) &&
            binding["trustedSourceTree"] == kotlinx.serialization.json.JsonPrimitive(expectedTrustedSourceTree)) {
            "Original Firebase Android input binding identity is invalid"
        }
        val logicalFiles = mapOf(
            "application.apk" to evidence.resolve(FIREBASE_APPLICATION_APK),
            "test.apk" to evidence.resolve(FIREBASE_TEST_APK),
            "runtime.aar" to evidence.resolve(FIREBASE_RELEASE_AAR),
            "lane-receipt.json" to observation.resolve("lane-receipt.json"),
        ).toSortedMap()
        val records = binding.releaseArray("files").map { value ->
            value as? JsonObject ?: error("Original Firebase Android input binding file is invalid")
        }
        check(records.size == logicalFiles.size && records.map { it.releaseString("relativePath") } == logicalFiles.keys.toList()) {
            "Original Firebase Android input binding file set is invalid"
        }
        records.zip(logicalFiles.values).forEach { (record, file) ->
            check(record.keys == setOf("relativePath", "bytes", "sha256") &&
                record.keys.toList() == record.keys.sorted() &&
                file.length() > 0 && record["bytes"] == kotlinx.serialization.json.JsonPrimitive(file.length()) &&
                record["relativePath"] == kotlinx.serialization.json.JsonPrimitive(record.releaseString("relativePath")) &&
                record["sha256"] == kotlinx.serialization.json.JsonPrimitive(record.releaseString("sha256")) &&
                record.releaseString("sha256").matches(Regex("sha256:[0-9a-f]{64}")) &&
                record.releaseString("sha256") == "sha256:${file.releaseDigest()}") {
                "Original Firebase Android protected input binding changed"
            }
        }

        val laneReceipt = observation.resolve("lane-receipt.json").readReleaseObject()
        check(laneReceipt.releaseInt("schemaVersion") == 1 &&
            laneReceipt.releaseString("repository") == CodexAgentBuild.REPOSITORY &&
            laneReceipt.releaseString("workflowPath") == ".github/workflows/ci.yml" &&
            laneReceipt.releaseString("event") in setOf("pull_request", "merge_group") &&
            laneReceipt.releaseString("validationCommit") == expectedCandidateCommit &&
            laneReceipt.releaseString("validationTree") == expectedCandidateTree &&
            laneReceipt.releaseString("lane") == "android" &&
            laneReceipt.releaseString("artifactName") == "codex-agent-ci-android-$expectedCandidateTree" &&
            laneReceipt.releaseLong("runId") > 0 && laneReceipt.releaseInt("runAttempt") > 0 &&
            laneReceipt.releaseString("result") == "passed") {
            "Original Firebase Android protected lane receipt identity is invalid"
        }

        check(Files.mismatch(
            expectedAar.toPath(), evidence.resolve(FIREBASE_RELEASE_AAR).toPath(),
        ) == -1L) { "Original Firebase Android release AAR differs from its authenticated binary" }
        check(Files.mismatch(
            observation.resolve("matrix.json").toPath(), evidence.resolve(FIREBASE_MATRIX_FILE).toPath(),
        ) == -1L) { "Original Firebase Android matrix differs from its protected observation" }
        val protectedReport = findPassingAndroidRuntimeReport(observation.resolve("results")).file
        check(Files.mismatch(
            protectedReport.toPath(), evidence.resolve(FIREBASE_ANDROID_REPORT).toPath(),
        ) == -1L) { "Original Firebase Android report differs from its protected observation" }

        val runtimeSha256 = expectedAar.singleZipEntryDigest(AAR_RUNTIME_ENTRY)
        val imported = verifyImportedAndroidReleaseAar(
            expectedAar, evidence.resolve(FIREBASE_ANDROID_EVIDENCE_FILE),
            expectedCandidateCommit, runtimeSha256,
        )
        val verified = verifyFirebaseAndroidRuntimeEvidenceArtifacts(
            evidence.resolve(FIREBASE_ANDROID_EVIDENCE_FILE), evidence,
            expectedCandidateCommit, runtimeSha256, applicationId, testIdentity,
        )
        check(imported.releaseString("releaseAarSha256") == verified.releaseAarSha256 &&
            imported.releaseString("bundledRuntimeSha256") == verified.bundledRuntimeSha256) {
            "Original Firebase Android imported AAR verification differs from the full evidence gate"
        }
        check(evidence.resolve(FIREBASE_ANDROID_VERIFICATION_RECEIPT_FILE).readReleaseObject() ==
            firebaseAndroidVerificationReceipt(verified)) {
            "Original Firebase Android retained verification receipt differs from trusted replay"
        }
        return verified
    } finally {
        listOf(evidence, observation, expectedAar).forEach(::requireAndroidOriginalPathWithoutSymlinks)
        check(digests(evidence) == evidenceBefore && digests(observation) == observationBefore &&
            expectedAar.isFile && expectedAar.length() == expectedAarSize &&
            expectedAar.releaseDigest() == expectedAarDigest) {
            "Original Firebase Android inputs changed during verification"
        }
    }
}

/** The caller supplies the trusted executable and a sanitized parent process environment. */
internal fun verifyOriginalFirebaseAndroidEvidenceWithApkanalyzer(
    evidenceDirectory: File,
    protectedObservationDirectory: File,
    expectedReleaseAar: File,
    expectedCandidateCommit: String,
    expectedCandidateTree: String,
    expectedTrustedSourceCommit: String,
    expectedTrustedSourceTree: String,
    apkanalyzerExecutable: File,
): FirebaseAndroidEvidenceVerification {
    val analyzer = apkanalyzerExecutable.absoluteFile
    requireAndroidOriginalPathWithoutSymlinks(analyzer)
    check(analyzer.canonicalFile == analyzer && analyzer.isFile) {
        "Original Firebase Android apkanalyzer is missing or unsafe"
    }
    val analyzerSize = analyzer.length()
    val analyzerDigest = analyzer.releaseDigest()
    fun manifest(apk: File): String {
        val command = listOf(analyzer.absolutePath, "manifest", "print", apk.absolutePath)
        val output = ByteArrayOutputStream()
        val process = ProcessBuilder(command).redirectErrorStream(true).start()
        process.inputStream.use { it.copyTo(output) }
        val text = output.toString(Charsets.UTF_8.name())
        check(process.waitFor() == 0) { "apkanalyzer failed: ${text.trim()}" }
        return text
    }
    try {
        return verifyOriginalFirebaseAndroidEvidence(
            evidenceDirectory, protectedObservationDirectory, expectedReleaseAar,
            expectedCandidateCommit, expectedCandidateTree, expectedTrustedSourceCommit,
            expectedTrustedSourceTree,
            applicationId = { parseAndroidApplicationId(manifest(it)) },
            testIdentity = { parseAndroidManifestIdentity(manifest(it)) },
        )
    } finally {
        requireAndroidOriginalPathWithoutSymlinks(analyzer)
        check(analyzer.isFile && analyzer.length() == analyzerSize && analyzer.releaseDigest() == analyzerDigest) {
            "Original Firebase Android apkanalyzer changed during verification"
        }
    }
}

private fun firebaseAndroidVerificationReceipt(
    verified: FirebaseAndroidEvidenceVerification,
): JsonObject = buildJsonObject {
    put("schemaVersion", 1)
    put("result", "passed")
    put("evidenceSha256", verified.evidenceSha256)
    put("firebaseMatrixSha256", verified.matrixSha256)
    put("testReportSha256", verified.testReportSha256)
    put("applicationApkSha256", verified.applicationApkSha256)
    put("testApkSha256", verified.testApkSha256)
    put("releaseAarSha256", verified.releaseAarSha256)
    put("bundledRuntimeSha256", verified.bundledRuntimeSha256)
}

private fun String.isGitOid(): Boolean = matches(Regex("[0-9a-f]{40}"))

private fun requireAndroidOriginalPathWithoutSymlinks(file: File) {
    var current: File? = file
    while (current != null) {
        check(!Files.isSymbolicLink(current.toPath())) {
            "Original Firebase Android input path has a symbolic parent: $current"
        }
        current = current.parentFile
    }
}
