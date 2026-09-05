import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFailsWith
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class AppleVerifiedDistributionTest {
    @Test
    fun `exact verified distribution and transported native evidence validate`() = fixture().use {
        val inventory = it.verify()
        assertEquals(appleVerifiedArtifactNames("0.2.0"), inventory.artifacts.keys)
        assertEquals(appleVerifiedReportLayout.keys, inventory.reports.keys)
        assertEquals(appleVerifiedToolchainLayout.keys, inventory.toolchain.keys)
        assertEquals(setOf(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT), inventory.receipts.keys)
        assertEquals(
            setOf(
                "reports/cross-language-api/apple/compiler-evidence.json",
                "reports/cross-language-api/apple/binding-evidence.json",
                "reports/cross-language-api/bindings/swift-parity.json",
                "reports/cross-language-api/bindings/objective-c-parity.json",
            ),
            inventory.reports.keys.filter { it.startsWith("reports/cross-language-api/") }.toSet(),
        )
    }

    @Test
    fun `legacy proof remains valid only without a retained receipt record`() = fixture().use {
        it.rebuildProof(schema = 1)
        assertEquals(emptyMap(), it.verify().receipts)
    }

    @Test
    fun `schema two requires the exact original native receipt`() = fixture().use {
        val original = it.distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
        original.appendText("tampered")
        assertFailsWith<IllegalStateException> { it.verify() }
        original.delete()
        assertFailsWith<IllegalStateException> { it.verify() }
        Unit
    }

    @Test
    fun `native receipt reuse permits only producer and consumer Git identity changes`() {
        val original = nativeReceipt("1".repeat(40), "2".repeat(40))
        val current = nativeReceipt("3".repeat(40), "4".repeat(40))
        verifyAppleNativeEvidenceReceiptReuse(
            original, current,
            "1".repeat(40), "2".repeat(40), "3".repeat(40), "4".repeat(40),
        )
        current.writeText(nativeReceiptJson("3".repeat(40), "4".repeat(40), nativeInputs = "9".repeat(64)))
        assertFailsWith<IllegalStateException> {
            verifyAppleNativeEvidenceReceiptReuse(
                original, current,
                "1".repeat(40), "2".repeat(40), "3".repeat(40), "4".repeat(40),
            )
        }
        original.parentFile.deleteRecursively()
        current.parentFile.deleteRecursively()
    }

    @Test
    fun `tampered or extra report is rejected`() = fixture().use {
        val report = it.distribution.resolve(appleVerifiedReportLayout.keys.first())
        report.appendText("tampered")
        assertFailsWith<IllegalStateException> { it.verify() }
        it.rebuildProof()
        it.distribution.resolve("reports/extra.txt").apply { parentFile.mkdirs(); writeText("extra") }
        assertFailsWith<IllegalStateException> { it.verify() }
        Unit
    }

    @Test
    fun `distribution cannot be paired with different native slices`() = fixture().use {
        it.nativeEvidence.resolve(appleRustSliceSpecs.first().archiveName).appendText("different")
        assertFailsWith<IllegalStateException> { it.verify() }
        Unit
    }

    @Test
    fun `compatibility bytes and exact paths are required in both Apple archives`() = fixture().use {
        it.writeSource("wrong/sdk-compatibility.json")
        it.rebuildProof()
        assertFailsWith<IllegalStateException> { it.verify() }
        it.writeSource("META-INF/codex-agent/sdk-compatibility.json")

        it.writeSwift(
            "CodexAgent.xcframework/ios-arm64/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json",
        )
        it.rebuildProof()
        assertFailsWith<IllegalStateException> { it.verify() }

        it.writeSwift(*swiftCompatibilityPaths, payload = "changed".toByteArray())
        it.rebuildProof()
        assertFailsWith<IllegalStateException> { it.verify() }
        Unit
    }

    @Test
    fun `compatibility declaration is canonical and matches the Apple package version`() = fixture().use {
        listOf(
            "{\"schemaVersion\":1,\"sdkVersion\":\"0.2.1\"}\n",
            "{\"schemaVersion\":1}\n",
            "{\"schemaVersion\":1,\"sdkVersion\":2}\n",
            "{ \"schemaVersion\": 1, \"sdkVersion\": \"0.2.0\" }\n",
            "{\"sdkVersion\":\"0.2.0\",\"schemaVersion\":1}\n",
            "{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\",\"sdkVersion\":\"0.2.0\"}\n",
        ).forEach { contents ->
            it.writeCompatibility(contents.toByteArray())
            it.rebuildProof()
            assertFails { it.verify() }
        }
    }

    @Test
    fun `compiler and language parity receipts are mandatory exact reports`() {
        listOf(
            "reports/cross-language-api/apple/compiler-evidence.json",
            "reports/cross-language-api/apple/binding-evidence.json",
            "reports/cross-language-api/bindings/swift-parity.json",
            "reports/cross-language-api/bindings/objective-c-parity.json",
        ).forEach { path ->
            fixture().use { changed ->
                changed.distribution.resolve(path).appendText("tampered")
                assertFailsWith<IllegalStateException>(path) { changed.verify() }
            }
        }
    }
}

private val swiftCompatibilityPaths = arrayOf(
    "CodexAgent.xcframework/ios-arm64/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json",
    "CodexAgent.xcframework/ios-arm64-simulator/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json",
)

private class VerifiedDistributionFixture : AutoCloseable {
    private val root = createTempDirectory("apple-verified-distribution").toFile()
    val distribution = root.resolve("distribution").apply { mkdirs() }
    val nativeEvidence = root.resolve("native-evidence").apply { mkdirs() }
    private val provenance = root.resolve("provenance.json").apply { writeText("{}") }
    private val packageSwift = root.resolve("Package.swift").apply { writeText("// package") }
    private val nativeReceipt = root.resolve("native-receipt.json").apply { writeText("{}") }
    private var sdkCompatibility = "{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n".toByteArray()
    private val identity get() = AppleVerifiedDistributionIdentity(
        "1".repeat(40), "2".repeat(40), "0.2.0", provenance.releaseDigest(),
        packageSwift.releaseDigest(), nativeReceipt.releaseDigest(), sdkCompatibility.sha256(),
    )

    init {
        val swift = distribution.resolve("CodexAgent-0.2.0.xcframework.zip").apply {
            zip(*swiftCompatibilityPaths)
        }
        distribution.resolve("CodexAgentPackage-0.2.0.zip").zip(
            "META-INF/codex-agent/sdk-compatibility.json",
        )
        distribution.resolve("CodexAgent-0.2.0.xcframework.zip.sha256").writeText(swift.releaseDigest())
        appleVerifiedReportLayout.keys.forEach { path ->
            distribution.resolve(path).apply { parentFile.mkdirs(); writeText(path) }
        }
        appleVerifiedToolchainLayout.keys.forEach { path ->
            distribution.resolve(path).apply { parentFile.mkdirs(); writeText(path) }
        }
        (appleRustSliceSpecs.flatMap { listOf(it.archiveName, it.proofName) } + IOS_NATIVE_TESTS_PROOF).forEach {
            nativeEvidence.resolve(it).writeText(it)
        }
        rebuildProof()
    }

    fun rebuildProof(schema: Int = 2) {
        val all = verifiedRegularFiles(distribution)
        val artifacts = all.filterKeys { it in appleVerifiedArtifactNames("0.2.0") }
        val reports = all.filterKeys { it in appleVerifiedReportLayout }
        val toolchain = all.filterKeys { it in appleVerifiedToolchainLayout }
        val retainedReceipt = distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
        if (schema == 2) {
            retainedReceipt.parentFile.mkdirs()
            retainedReceipt.writeBytes(nativeReceipt.readBytes())
        } else retainedReceipt.delete()
        val proof = buildAppleVerifiedDistributionProof(
            identity, artifacts, reports, toolchain, verifiedRegularFiles(nativeEvidence),
            if (schema == 2) mapOf(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT to retainedReceipt) else emptyMap(),
        )
        val encoded = if (schema == 2) proof else JsonObject(proof.filterKeys { it != "receipts" }.mapValues {
            when (it.key) {
                "schemaVersion" -> JsonPrimitive(1)
                "protocol" -> JsonPrimitive("codex-agent-ios-verified-distribution-v1")
                else -> it.value
            }
        })
        distribution.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).atomicWriteJson(encoded)
    }

    fun verify() = verifyAppleVerifiedDistribution(distribution, nativeEvidence, identity)

    fun writeSource(vararg paths: String, payload: ByteArray = sdkCompatibility) {
        distribution.resolve("CodexAgentPackage-0.2.0.zip").zip(*paths, payload = payload)
    }

    fun writeSwift(vararg paths: String, payload: ByteArray = sdkCompatibility) {
        distribution.resolve("CodexAgent-0.2.0.xcframework.zip").zip(*paths, payload = payload)
    }

    fun writeCompatibility(payload: ByteArray) {
        sdkCompatibility = payload
        writeSource("META-INF/codex-agent/sdk-compatibility.json")
        writeSwift(*swiftCompatibilityPaths)
        val swift = distribution.resolve("CodexAgent-0.2.0.xcframework.zip")
        distribution.resolve("CodexAgent-0.2.0.xcframework.zip.sha256").writeText(swift.releaseDigest())
    }

    private fun File.zip(vararg paths: String, payload: ByteArray = sdkCompatibility) {
        outputStream().use { output ->
            ZipOutputStream(output).use { archive ->
                paths.forEach { path ->
                    archive.putNextEntry(ZipEntry(path))
                    archive.write(payload)
                    archive.closeEntry()
                }
            }
        }
    }

    private fun ByteArray.sha256(): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(this).joinToString("") { "%02x".format(it.toInt() and 0xff) }
    override fun close() = root.deleteRecursively().let { }
}

private fun fixture() = VerifiedDistributionFixture()

private fun nativeReceipt(commit: String, tree: String): File {
    val root = createTempDirectory("apple-native-receipt-reuse").toFile()
    return root.resolve("receipt.json").apply { writeText(nativeReceiptJson(commit, tree)) }
}

private fun nativeReceiptJson(commit: String, tree: String, nativeInputs: String = "5".repeat(64)): String =
    buildJsonObject {
        put("schemaVersion", JsonPrimitive(2))
        put("protocol", JsonPrimitive("codex-agent-ios-native-evidence-v2"))
        put("result", JsonPrimitive("passed"))
        put("candidateCommit", JsonPrimitive(commit))
        put("candidateTree", JsonPrimitive(tree))
        put("cleanCheckout", JsonPrimitive(true))
        put("nativeInputsSha256", JsonPrimitive(nativeInputs))
        put("nativeProvenanceSha256", JsonPrimitive("6".repeat(64)))
        put("compilerSettingsSha256", JsonPrimitive("7".repeat(64)))
        put("rustToolchain", JsonPrimitive("1.95.0"))
        put("rustSrcComponent", JsonPrimitive("required"))
        put("rustCompilerIdentitySha256", JsonPrimitive("8".repeat(64)))
        put("xcodeVersionSha256", JsonPrimitive("a".repeat(64)))
        put("swiftVersionSha256", JsonPrimitive("b".repeat(64)))
        put("nativeTestsProofSha256", JsonPrimitive("c".repeat(64)))
        put("slices", buildJsonArray { })
    }.toString()
