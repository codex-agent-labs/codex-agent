import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject

class CandidateManifestTasksTest {
    @Test
    fun `schema 12 structure is exact and schema 9 is rejected`() {
        val manifest = schema12CandidateManifest(VERSION, COMMIT)

        verifyCandidateManifestStructure(manifest)
        val legacy = JsonObject(manifest + ("schemaVersion" to JsonPrimitive(9)))
        assertFailsWith<IllegalStateException> { verifyCandidateManifestStructure(legacy) }
        val missingPolicy = JsonObject(manifest + ("policies" to JsonObject(
            manifest.releaseObject("policies") - "iosResourcePolicy",
        )))
        assertFailsWith<IllegalStateException> { verifyCandidateManifestStructure(missingPolicy) }
    }

    @Test
    fun `payload records traverse every Central bundle and evidence array`() {
        val manifest = schema12CandidateManifest(VERSION, COMMIT)
        val records = candidatePayloadRecords(manifest).map { it.releaseString("fileName") }
        val expectedBundles = centralBundleShardNames.map { centralBundleFileName(VERSION, it) }
        val evidence = manifest.releaseObject("evidence")
        val arrayEvidence = candidateEvidenceArrayNames.flatMap { name ->
            evidence.releaseArray(name).map { it.jsonObject.releaseString("fileName") }
        }

        assertTrue(records.containsAll(expectedBundles))
        assertTrue(records.containsAll(arrayEvidence))
        assertEquals(records.size, records.toSet().size)
    }

    @Test
    fun `extra missing and tampered payload files are rejected`() {
        val root = createTempDirectory("candidate-payload-files").toFile()
        try {
            val payload = root.resolve("payload").apply { mkdirs() }
            val swift = payload.resolve("CodexAgent-$VERSION.xcframework.zip").apply { writeText("swift") }
            val base = schema12CandidateManifest(VERSION, COMMIT)
            val artifacts = base.releaseObject("artifacts")
            val swiftRecord = buildJsonObject {
                swift.releaseRecord().forEach { (key, value) -> put(key, value) }
                put("swiftPmChecksum", JsonPrimitive(swift.releaseDigest()))
                put("members", buildJsonArray {})
            }
            val manifest = JsonObject(base + ("artifacts" to JsonObject(
                artifacts + ("swiftPackage" to swiftRecord),
            )))
            val manifestFile = root.resolve("candidate-manifest.json").apply { atomicWriteJson(manifest) }
            candidatePayloadRecords(manifest).drop(1).forEach { record ->
                payload.resolve(record.releaseString("fileName")).writeText("x")
            }

            val extra = payload.resolve("unexpected.bin").apply { writeText("x") }
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
            extra.delete()

            val missing = payload.resolve(candidatePayloadRecords(manifest).last().releaseString("fileName"))
            missing.delete()
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
            missing.writeText("x")

            swift.appendText("tampered")
            assertFailsWith<IllegalStateException> {
                verifyCandidatePayload(manifestFile, payload, VERSION, "v$VERSION", COMMIT, emptyMap())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `GitHub output contains only the plural Central bundle output`() {
        val bundles = centralBundleShardNames.map { centralBundleFileName(VERSION, it) }
        val result = buildJsonObject {
            put("releaseTag", JsonPrimitive("v$VERSION"))
            put("swiftAsset", JsonPrimitive("swift.zip"))
            put("centralBundles", buildJsonArray { bundles.forEach { add(JsonPrimitive(it)) } })
        }

        assertEquals(
            "releaseTag=v$VERSION\nswiftAsset=swift.zip\ncentralBundles=${result.releaseArray("centralBundles")}\n",
            candidateGithubOutputs(result),
        )
    }

    @Test
    fun `privacy review must be declared even with an explicit override`() {
        val root = createTempDirectory("candidate-privacy-review").toFile()
        try {
            val payload = root.resolve("payload").apply { mkdirs() }
            val declared = payload.resolve("privacy-required-reason-reviews.json").apply { writeText("{}") }
            val explicit = root.resolve(declared.name).apply { writeText("{}") }
            val manifest = buildJsonObject {
                put("policies", buildJsonObject {
                    put("privacyRequiredReasonReviews", declared.releaseRecord())
                })
            }
            assertSame(explicit, resolveCandidatePrivacyReview(manifest, payload, explicit, null))
            val absent = buildJsonObject { put("policies", buildJsonObject {}) }
            assertFailsWith<IllegalStateException> {
                resolveCandidatePrivacyReview(absent, payload, explicit, null)
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `iOS runtime metrics keep their schema 12 gates`() {
        val root = createTempDirectory("candidate-ios-metrics").toFile()
        try {
            val metrics = writeTestIosRuntimeMetrics(root.resolve("runtime-metrics.json"))
            validateIosRuntimeMetrics(metrics.readReleaseObject())
            writeTestIosRuntimeMetrics(metrics, startup = 30_000)
            assertFailsWith<IllegalStateException> {
                validateIosRuntimeMetrics(metrics.readReleaseObject())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    companion object {
        private const val VERSION = "0.2.0"
        private const val COMMIT = "0123456789abcdef0123456789abcdef01234567"
    }
}
