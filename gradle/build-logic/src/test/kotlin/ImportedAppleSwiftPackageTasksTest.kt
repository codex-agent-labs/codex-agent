import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.apache.commons.compress.archivers.zip.UnixStat
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream

/** Synthetic receipt-bound transport fixtures; no Apple product/compiler acceptance. */
class ImportedAppleSwiftPackageTasksTest {
    @Test
    fun `Swift package bytes are imported exactly without rewriting original transport`() = fixture().use { fixture ->
        val originals = fixture.originalDigests()
        repeat(2) {
            fixture.importPackage()
            assertEquals(fixture.packageMembers, verifiedRegularFiles(fixture.output).mapValues { it.value.readText() })
            assertEquals(originals, fixture.originalDigests())
            fixture.output.resolve("stale-consumer-file").writeText("must disappear on next import")
        }
    }

    @Test
    fun `schema two receipt keeps original producer distinct from current consumer`() = fixture().use { fixture ->
        fixture.writeProof(schema = 2)
        fixture.importPackage()
        assertEquals(fixture.packageMembers, verifiedRegularFiles(fixture.output).mapValues { it.value.readText() })
    }

    @Test
    fun `crosspaired and unsafe original package members fail before output publication`() {
        listOf(
            "framework", "compatibility", "missing-tests", "extra-framework", "symlink",
            "special", "traversal", "absolute", "backslash", "duplicate",
        ).forEach { mutation -> fixture().use { fixture ->
            val members = fixture.packageMembers.toMutableMap()
            var extra: Pair<String, Int>? = null
            when (mutation) {
                "framework" -> members["CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent"] = "different runtime"
                "compatibility" -> members[fixture.compatibilityPath] = "different compatibility"
                "missing-tests" -> members.keys.removeAll { it.startsWith("Tests/") }
                "extra-framework" -> members["CodexAgent.xcframework/extra"] = "unexpected"
                "symlink" -> extra = "Sources/link" to (UnixStat.LINK_FLAG or UnixStat.DEFAULT_LINK_PERM)
                "special" -> extra = "Sources/pipe" to (0x1000 or UnixStat.DEFAULT_FILE_PERM)
                "traversal" -> extra = "../escape" to fixture.regularMode
                "absolute" -> extra = "/escape" to fixture.regularMode
                "backslash" -> extra = "Sources\\escape" to fixture.regularMode
                "duplicate" -> extra = "Package.swift" to fixture.regularMode
            }
            fixture.writePackage(members, extra)
            // Rebind fixture proof so semantic/archive checks, not a stale ZIP digest, reject it.
            fixture.writeProof()
            assertFailsWith<IllegalStateException>(mutation) { fixture.importPackage() }
            assertFalse(fixture.output.exists(), mutation)
        } }
    }

    @Test
    fun `changed original proof or ZIP is rejected against the retained receipt`() {
        listOf("proof", "package", "framework").forEach { mutation -> fixture().use { fixture ->
            when (mutation) {
                "proof" -> fixture.proof.appendText("changed")
                "package" -> fixture.packageArchive.appendText("changed")
                else -> fixture.frameworkArchive.appendText("changed")
            }
            assertFailsWith<IllegalStateException>(mutation) { fixture.importPackage() }
            assertFalse(fixture.output.exists(), mutation)
        } }
    }

    @Test
    fun `imported consumers use original package and never reconstruct checkout sources`() {
        val source = File("src/main/kotlin/IosVerifiedDistributionRegistration.kt").readText()
        val imported = source.substringAfter("val swiftPackage =")
        assertTrue("tasks.register<ImportVerifiedCodexAgentSwiftPackageTask>" in imported)
        assertTrue("dependsOn(validate)" in imported)
        assertTrue("verificationReceipt.set(validate.flatMap { it.verificationReceipt })" in imported)
        val stage = imported.substringAfter("tasks.named<StageCodexAgentAppleDistributionTask>")
            .substringBefore("distribution.verifyCodexAgentSwiftAuthenticationTests.configure")
        assertTrue("onlyIf { false }" in stage)
        listOf("verifyCodexAgentSwiftAuthenticationTests", "verifyIosLicensePackaging").forEach { name ->
            val consumer = imported.substringAfter("distribution.$name.configure {").substringBefore("\n    }")
            assertTrue("dependsOn(swiftPackage)" in consumer, name)
            assertTrue("packageDirectory.set(swiftPackage.flatMap { it.packageDirectory })" in consumer, name)
        }
        assertTrue("from(layout.projectDirectory.dir(\"apple/TestApp\"))" in imported)
        assertTrue("workingDir(consumerDirectory)" in imported)
        assertFalse("apple/Sources" in imported)
        assertFalse("apple/Tests" in imported)
        val plugin = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
        assertTrue("VerifySwiftAuthenticationTestsTask::packageDirectory" in plugin)
        assertTrue("VerifySwiftAuthenticationTestsTask::resultBundleDirectory" in plugin)
    }

    private fun fixture() = ImportedSwiftPackageFixture()
}

private class ImportedSwiftPackageFixture : AutoCloseable {
    private val root = createTempDirectory("imported-apple-swift-package").toFile()
    val evidence = root.resolve("evidence").apply { mkdirs() }
    val proof = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    private val receipt = root.resolve("verification-receipt.json")
    val packageArchive = evidence.resolve("CodexAgentPackage-0.2.0.zip")
    val frameworkArchive = evidence.resolve("CodexAgent-0.2.0.xcframework.zip")
    val output = root.resolve("output/CodexAgentPackage")
    val compatibilityPath = "META-INF/codex-agent/sdk-compatibility.json"
    val regularMode = UnixStat.FILE_FLAG or UnixStat.DEFAULT_FILE_PERM
    private val frameworkMembers = buildMap {
        put("CodexAgent.xcframework/Info.plist", "plist")
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            listOf("CodexAgent", "Headers/CodexAgent.h", "Modules/module.modulemap", "Info.plist", "PrivacyInfo.xcprivacy").forEach { member ->
                put("CodexAgent.xcframework/$slice/CodexAgent.framework/$member", "original:$slice/$member")
            }
        }
    }
    val packageMembers = frameworkMembers + mapOf(
        "Package.swift" to "original package manifest",
        "Sources/Original.swift" to "original Swift source",
        "Tests/Original.swift" to "original Swift tests",
        "LICENSE.txt" to "license",
        "THIRD_PARTY_NOTICES.md" to "notices",
        "openai-codex-LICENSE.txt" to "codex license",
        "openai-codex-NOTICE.txt" to "codex notice",
        compatibilityPath to "original compatibility",
    )

    init {
        writeArchive(frameworkArchive, frameworkMembers + listOf("ios-arm64", "ios-arm64-simulator").associate { slice ->
            "CodexAgent.xcframework/$slice/CodexAgent.framework/$compatibilityPath" to "original compatibility"
        })
        writePackage(packageMembers)
        writeProof()
    }

    fun importPackage() = extractVerifiedAppleSwiftPackage(evidence, receipt, "0.2.0", root.resolve("work"), output)

    fun originalDigests() = (listOf(receipt) + evidence.listFiles()!!.toList()).associate { it.name to it.releaseDigest() }

    fun writePackage(members: Map<String, String>, extra: Pair<String, Int>? = null) = writeArchive(packageArchive, members, extra)

    private fun writeArchive(archive: File, members: Map<String, String>, extra: Pair<String, Int>? = null) {
        ZipArchiveOutputStream(archive).use { zip ->
            members.forEach { (path, contents) ->
                zip.putArchiveEntry(ZipArchiveEntry(path).apply { unixMode = regularMode })
                zip.write(contents.toByteArray())
                zip.closeArchiveEntry()
            }
            extra?.let { (path, mode) ->
                // ZipArchiveEntry(String) normalizes backslashes before writing; preserve
                // the literal hostile name so this fixture actually exercises the boundary.
                val entry = object : ZipArchiveEntry(path) {
                    override fun getName(): String = path
                }.apply { unixMode = mode }
                zip.putArchiveEntry(entry)
                zip.write("extra".toByteArray())
                zip.closeArchiveEntry()
            }
        }
        extra?.let { (path, _) ->
            java.util.zip.ZipFile(archive).use { zip ->
                check(zip.entries().asSequence().any { it.name == path }) {
                    "Hostile fixture member name was normalized before extraction: $path"
                }
            }
        }
    }

    fun writeProof(schema: Int = 1) {
        proof.atomicWriteJson(buildJsonObject {
            if (schema == 2) {
                put("candidateCommit", JsonPrimitive("a".repeat(40)))
                put("candidateTree", JsonPrimitive("b".repeat(40)))
                put("nativeEvidenceReceiptSha256", JsonPrimitive("c".repeat(64)))
            }
            put("artifacts", buildJsonArray {
                listOf(packageArchive, frameworkArchive).forEach { file -> add(buildJsonObject {
                    put("fileName", JsonPrimitive(file.name))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                }) }
            })
        })
        receipt.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(schema))
            put("protocol", JsonPrimitive("codex-agent-ios-verified-distribution-import-v$schema"))
            put("result", JsonPrimitive("passed"))
            if (schema == 1) {
                put("candidateCommit", JsonPrimitive("a".repeat(40)))
                put("candidateTree", JsonPrimitive("b".repeat(40)))
                put("nativeEvidenceReceiptSha256", JsonPrimitive("c".repeat(64)))
            } else {
                put("producerCommit", JsonPrimitive("a".repeat(40)))
                put("producerTree", JsonPrimitive("b".repeat(40)))
                put("consumerCommit", JsonPrimitive("d".repeat(40)))
                put("consumerTree", JsonPrimitive("e".repeat(40)))
                put("originalNativeEvidenceReceiptSha256", JsonPrimitive("c".repeat(64)))
                put("currentNativeEvidenceReceiptSha256", JsonPrimitive("f".repeat(64)))
            }
            put("sourceProofSha256", JsonPrimitive(proof.releaseDigest()))
        })
    }

    override fun close() = root.deleteRecursively().let { Unit }
}
