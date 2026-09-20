import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFailsWith
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class FirebaseAndroidOriginalEvidenceTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("ci/receipt.py").isFile }
    private val laneReceiptSchemaVersion = Regex(
        "(?m)^LANE_RECEIPT_SCHEMA_VERSION = ([1-9][0-9]*)$",
    ).findAll(repository.resolve("ci/receipt.py").readText()).single().groupValues[1].toInt()

    @Test
    fun `protected binding and full existing Firebase gate accept exact original bytes`() = withFixture { fixture ->
        assertEquals(laneReceiptSchemaVersion, FIREBASE_ANDROID_LANE_RECEIPT_SCHEMA_VERSION)
        val result = fixture.verify()

        assertEquals(fixture.app.releaseDigest(), result.applicationApkSha256)
        assertEquals(fixture.testApk.releaseDigest(), result.testApkSha256)
        assertEquals(fixture.expectedAar.releaseDigest(), result.releaseAarSha256)
        assertEquals(fixture.runtime.releaseDigest(), result.bundledRuntimeSha256)
    }

    @Test
    fun `old or malformed bindings and wrong immutable identities reject`() {
        listOf<(Fixture) -> Unit>(
            { it.observation.resolve("input-binding.json").delete() },
            { it.changeBinding("schemaVersion", JsonPrimitive(2)) },
            { it.changeBinding("schemaVersion", JsonPrimitive("1")) },
            { it.changeBinding("kind", JsonPrimitive("unbound")) },
            { it.changeBinding("candidateCommit", JsonPrimitive("f".repeat(40))) },
            { it.changeBinding("candidateTree", JsonPrimitive("f".repeat(40))) },
            { it.changeBinding("trustedSourceCommit", JsonPrimitive("f".repeat(40))) },
            { it.changeBinding("trustedSourceTree", JsonPrimitive("f".repeat(40))) },
            { it.changeFiles { files -> JsonArray(files.dropLast(1)) } },
            { it.changeFiles { files -> JsonArray(listOf(files[1], files[0]) + files.drop(2)) } },
            { it.changeFirstFile("bytes", JsonPrimitive(it.app.length().toString())) },
        ).forEach { mutate ->
            withFixture { fixture ->
                fixture.verify()
                mutate(fixture)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `binding requires exact canonical bytes and rejects duplicate fields`() {
        listOf<(Fixture) -> Unit>(
            { it.changeBindingText { text -> " $text" } },
            { it.changeBindingText { text -> text.replaceFirst(
                "\"candidateCommit\":", "\"candidateCommit\":\"${"0".repeat(40)}\",\"candidateCommit\":"
            ) } },
        ).forEach { mutate ->
            withFixture { fixture ->
                fixture.verify()
                mutate(fixture)
                assertFails { fixture.verify() }
            }
        }
    }

    @Test
    fun `protected tested inputs matrix report and original lane receipt cannot drift`() {
        listOf<(Fixture) -> Unit>(
            { it.app.appendText("changed") },
            { it.testApk.appendText("changed") },
            { it.aar.appendText("changed") },
            { it.observation.resolve("matrix.json").appendText(" ") },
            { it.observation.resolve("results/result.xml").appendText(" ") },
            { it.changeLaneReceipt("validationCommit", JsonPrimitive("f".repeat(40))) },
            { it.changeLaneReceipt("schemaVersion", JsonPrimitive(1)) },
            { it.observation.resolve("lane-receipt.json").appendText(" ") },
        ).forEach { mutate ->
            withFixture { fixture ->
                fixture.verify()
                mutate(fixture)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    @Test
    fun `authenticated AAR and trusted semantic replay remain mandatory`() {
        listOf<(Fixture) -> Unit>(
            { it.expectedAar.appendText("different") },
            { it.evidence.resolve(FIREBASE_ANDROID_VERIFICATION_RECEIPT_FILE).writeText("{}") },
            { it.evidence.resolve(FIREBASE_ANDROID_EVIDENCE_FILE).appendText(" ") },
            { it.report.writeText(it.report.readText().replace("failures=\"0\"", "failures=\"1\"")) },
        ).forEach { mutate ->
            withFixture { fixture ->
                fixture.verify()
                mutate(fixture)
                assertFailsWith<IllegalStateException> { fixture.verify() }
            }
        }
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("firebase-original-evidence").toFile().canonicalFile
        try {
            block(Fixture(root, laneReceiptSchemaVersion))
        } finally {
            root.deleteRecursively()
        }
    }

    private class Fixture(root: File, private val laneReceiptSchemaVersion: Int) {
        val evidence = root.resolve("final-evidence").apply { mkdirs() }
        val observation = root.resolve("protected-observation").apply { mkdirs() }
        val runtime = root.resolve("runtime.so").apply { writeText("pinned runtime") }
        val app = evidence.resolve(FIREBASE_APPLICATION_APK)
        val testApk = evidence.resolve(FIREBASE_TEST_APK)
        val aar = evidence.resolve(FIREBASE_RELEASE_AAR)
        val expectedAar = root.resolve(FIREBASE_RELEASE_AAR)
        val report = evidence.resolve(FIREBASE_ANDROID_REPORT)
        private val matrix = evidence.resolve(FIREBASE_MATRIX_FILE)

        init {
            zip(app, mapOf(APK_RUNTIME_ENTRY to runtime.readBytes()))
            zip(testApk, mapOf("classes.dex" to "test".encodeToByteArray()))
            zip(aar, mapOf(AAR_RUNTIME_ENTRY to runtime.readBytes()))
            expectedAar.writeBytes(aar.readBytes())
            matrix.writeText(matrixJson())
            report.writeText(reportXml())
            evidence.resolve(FIREBASE_ANDROID_EVIDENCE_FILE).atomicWriteJson(
                buildFirebaseAndroidEvidence(FirebaseAndroidEvidenceValues(
                    CANDIDATE_COMMIT,
                    FirebaseTestMatrix(
                        "matrix-test", "test-project", "gs://bucket/results", FIREBASE_DEVICE_MODEL,
                        FIREBASE_DEVICE_API, FIREBASE_DEVICE_LOCALE, FIREBASE_DEVICE_ORIENTATION,
                    ),
                    matrix.releaseDigest(), report.releaseDigest(), app.releaseDigest(),
                    testApk.releaseDigest(), aar.releaseDigest(), runtime.releaseDigest(), runtime.releaseDigest(),
                )),
            )
            val verified = verifyFirebaseAndroidRuntimeEvidenceArtifacts(
                evidence.resolve(FIREBASE_ANDROID_EVIDENCE_FILE), evidence, CANDIDATE_COMMIT,
                runtime.releaseDigest(), { FIREBASE_APPLICATION_ID },
                { AndroidManifestIdentity(FIREBASE_TEST_APPLICATION_ID, FIREBASE_APPLICATION_ID) },
            )
            writeFirebaseAndroidVerificationReceipt(
                evidence.resolve(FIREBASE_ANDROID_VERIFICATION_RECEIPT_FILE), verified,
            )
            observation.resolve("matrix.json").writeBytes(matrix.readBytes())
            observation.resolve("results").mkdir()
            observation.resolve("results/result.xml").writeBytes(report.readBytes())
            observation.resolve("lane-receipt.json").atomicWriteJson(laneReceipt())
            writeBinding()
        }

        fun verify() = verifyOriginalFirebaseAndroidEvidence(
            evidence, observation, expectedAar, CANDIDATE_COMMIT, CANDIDATE_TREE,
            SOURCE_COMMIT, SOURCE_TREE,
            applicationId = { FIREBASE_APPLICATION_ID },
            testIdentity = { AndroidManifestIdentity(FIREBASE_TEST_APPLICATION_ID, FIREBASE_APPLICATION_ID) },
        )

        fun changeBinding(name: String, value: JsonPrimitive) {
            val path = observation.resolve("input-binding.json")
            writeCanonical(path, JsonObject(path.readReleaseObject() + (name to value)))
        }

        fun changeFiles(change: (JsonArray) -> JsonArray) {
            val path = observation.resolve("input-binding.json")
            val current = path.readReleaseObject()
            writeCanonical(path, JsonObject(current + ("files" to change(current.releaseArray("files")))))
        }

        fun changeFirstFile(name: String, value: JsonPrimitive) {
            changeFiles { files ->
                val first = files.first() as JsonObject
                JsonArray(listOf(JsonObject(first + (name to value))) + files.drop(1))
            }
        }

        fun changeBindingText(change: (String) -> String) {
            val path = observation.resolve("input-binding.json")
            path.writeText(change(path.readText()))
        }

        fun changeLaneReceipt(name: String, value: JsonPrimitive) {
            val path = observation.resolve("lane-receipt.json")
            path.atomicWriteJson(JsonObject(path.readReleaseObject() + (name to value)))
        }

        private fun writeBinding() {
            val bound = mapOf(
                "application.apk" to app,
                "test.apk" to testApk,
                "runtime.aar" to aar,
                "lane-receipt.json" to observation.resolve("lane-receipt.json"),
            ).toSortedMap()
            writeCanonical(observation.resolve("input-binding.json"), buildJsonObject {
                put("candidateCommit", CANDIDATE_COMMIT)
                put("candidateTree", CANDIDATE_TREE)
                put("files", buildJsonArray {
                    bound.forEach { (name, file) ->
                        add(buildJsonObject {
                            put("bytes", file.length())
                            put("relativePath", name)
                            put("sha256", "sha256:${file.releaseDigest()}")
                        })
                    }
                })
                put("kind", "firebase-android-input-binding")
                put("schemaVersion", 1)
                put("trustedSourceCommit", SOURCE_COMMIT)
                put("trustedSourceTree", SOURCE_TREE)
            })
        }

        private fun writeCanonical(file: File, value: JsonObject) {
            file.writeText(Json.encodeToString(JsonElement.serializer(), value) + "\n")
        }

        private fun laneReceipt() = buildJsonObject {
            put("schemaVersion", laneReceiptSchemaVersion)
            put("repository", CodexAgentBuild.REPOSITORY)
            put("workflowPath", ".github/workflows/ci.yml")
            put("event", "pull_request")
            put("validationCommit", CANDIDATE_COMMIT)
            put("validationTree", CANDIDATE_TREE)
            put("lane", "android")
            put("artifactName", "codex-agent-ci-android-$CANDIDATE_TREE")
            put("runId", 17)
            put("runAttempt", 2)
            put("result", "passed")
        }

        private fun zip(file: File, entries: Map<String, ByteArray>) {
            ZipOutputStream(file.outputStream()).use { output ->
                entries.forEach { (name, bytes) ->
                    output.putNextEntry(ZipEntry(name))
                    output.write(bytes)
                    output.closeEntry()
                }
            }
        }
    }

    companion object {
        private const val CANDIDATE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
        private const val CANDIDATE_TREE = "1111111111111111111111111111111111111111"
        private const val SOURCE_COMMIT = "2222222222222222222222222222222222222222"
        private const val SOURCE_TREE = "3333333333333333333333333333333333333333"

        private fun matrixJson() = """
            {
              "testMatrixId":"matrix-test","projectId":"test-project","state":"FINISHED",
              "outcomeSummary":"SUCCESS",
              "resultStorage":{"googleCloudStorage":{"gcsPath":"gs://bucket/results"}},
              "testExecutions":[{
                "state":"FINISHED",
                "environment":{"androidDevice":{"androidModelId":"$FIREBASE_DEVICE_MODEL",
                  "androidVersionId":"$FIREBASE_DEVICE_API","locale":"$FIREBASE_DEVICE_LOCALE",
                  "orientation":"$FIREBASE_DEVICE_ORIENTATION"}}
              }]
            }
        """.trimIndent()

        private fun reportXml() = """
            <testsuite tests="3" failures="0" errors="0" skipped="0">
              <testcase classname="$ANDROID_RUNTIME_TEST_CLASS"
                name="missingNonExecutableAndCorruptOverridesFailClosed"/>
              <testcase classname="$ANDROID_RUNTIME_TEST_CLASS"
                name="successfulRuntimeInstallsCertificatePrivacyAndCleanupPolicies"/>
              <testcase classname="$ANDROID_RUNTIME_TEST_CLASS"
                name="javaHostLifecycleIsObservableAndIdempotentlyCloseable"/>
            </testsuite>
        """.trimIndent()
    }
}
