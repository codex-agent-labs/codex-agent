import java.io.File
import java.nio.file.Files
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

/** Synthetic proof-bound archives; no Apple compiler, XCTest, or product receipt acceptance. */
class AppleSdkDistributionPackageTaskTest {
    @Test
    fun `artifact stage preserves exact original archives`() = fixture().use { fixture ->
        val before = fixture.originalDigests()
        fixture.output.apply { mkdirs() }.resolve("stale").writeText("remove")
        fixture.stage()
        assertEquals(before, fixture.originalDigests())
        assertEquals(before.filterKeys { it != IOS_VERIFIED_DISTRIBUTION_PROOF }, fixture.outputDigests())
    }

    @Test
    fun `artifact stage rejects crosspaired compatibility and stale checksum before publication`() {
        listOf("framework", "compatibility", "checksum", "missing").forEach { mutation ->
            fixture().use { fixture ->
                fixture.output.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
                when (mutation) {
                    "framework" -> fixture.rewritePackage("different-device-binary")
                    "compatibility" -> fixture.rewritePackage(compatibility = "different")
                    "checksum" -> fixture.rewriteChecksum("0".repeat(64) + "\n")
                    else -> fixture.removePackageArchive()
                }
                if (mutation != "missing") fixture.rebindProof()
                assertFailsWith<IllegalStateException>(mutation) { fixture.stage() }
                assertEquals("preserved", fixture.output.resolve("sentinel").readText())
            }
        }
    }

    @Test
    fun `artifact stage rejects unsafe output aliases without deleting an input`() = fixture().use { fixture ->
        val before = fixture.originalDigests()
        assertFailsWith<IllegalStateException> {
            fixture.stageWithEvidenceOutput()
        }
        assertEquals(before, fixture.originalDigests())
    }

    @Test
    fun `artifact stage rejects unowned output symbolic parents and swapped compatibility without deletion`() {
        listOf(
            "unowned", "symlink-output", "symlink-dotdot-output",
            "symlink-input", "symlink-dotdot-input", "swapped",
        ).forEach { mutation -> fixture().use { fixture ->
            val destination = when (mutation) {
                "unowned" -> fixture.unownedOutput
                "symlink-output" -> fixture.symbolicOutput()
                "symlink-dotdot-output" -> fixture.symbolicDotDotOutput()
                else -> fixture.output
            }
            destination.parentFile.mkdirs()
            destination.apply { mkdirs() }.resolve("sentinel").writeText("preserved")
            assertFailsWith<IllegalStateException>(mutation) {
                when (mutation) {
                    "swapped" -> fixture.stage(compatibility = fixture.receipt)
                    "symlink-input" -> fixture.stage(compatibility = fixture.symbolicCompatibility())
                    "symlink-dotdot-input" -> fixture.stage(compatibility = fixture.symbolicDotDotCompatibility())
                    else -> fixture.stage(output = destination)
                }
            }
            assertEquals("preserved", destination.resolve("sentinel").readText())
            assertTrue(fixture.receipt.isFile)
        } }
    }

    @Test
    fun `registration requires full imported verification and does not build a framework`() {
        val source = File("src/main/kotlin/IosVerifiedDistributionRegistration.kt").readText()
        val registration = source.substringAfter(
            "tasks.register<StageImportedAppleSdkPackageArtifactsTask>",
        ).substringBefore("tasks.named<StageCodexAgentAppleDistributionTask>")
        assertTrue("dependsOn(validate)" in registration)
        assertTrue("verificationReceipt.set(validate.flatMap" in registration)
        assertTrue("sdkCompatibility.set(it)" in registration)
        assertFalse("prepareCodexAgentReleaseXCFramework" in registration)
        assertFalse("assembleCodexAgentReleaseXCFramework" in registration)
        assertFalse("compileKotlin" in registration)
    }
}

private class AppleSdkPackageFixture : AutoCloseable {
    private val root = createTempDirectory("apple-sdk-package-stage").toFile().canonicalFile
    private val owned = root.resolve("owned").apply { mkdirs() }
    val evidence = root.resolve("evidence").apply { mkdirs() }
    val receipt = root.resolve("receipt.json")
    private val compatibility = root.resolve("sdk-compatibility.json").apply {
        writeText("{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n")
    }
    private val work = owned.resolve("work")
    val output = owned.resolve("output")
    val unownedOutput = root.resolve("unowned/output")
    private val packageArchive = evidence.resolve("CodexAgentPackage-0.2.0.zip")
    private val frameworkArchive = evidence.resolve("CodexAgent-0.2.0.xcframework.zip")
    private val checksum = evidence.resolve("CodexAgent-0.2.0.xcframework.zip.sha256")
    private val frameworkMembers = buildMap {
        put("CodexAgent.xcframework/Info.plist", "plist")
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            val framework = "CodexAgent.xcframework/$slice/CodexAgent.framework"
            put("$framework/CodexAgent", "binary:$slice")
            put("$framework/Headers/CodexAgent.h", "header")
            put("$framework/Modules/module.modulemap", "module")
            put("$framework/Info.plist", "framework plist")
            put("$framework/PrivacyInfo.xcprivacy", "privacy")
            put("$framework/META-INF/codex-agent/sdk-compatibility.json", compatibility.readText())
        }
    }

    init {
        writeZip(frameworkArchive, frameworkMembers)
        rewritePackage()
        checksum.writeText("${frameworkArchive.releaseDigest()}\n")
        rebindProof()
    }

    fun stage(output: File = this.output, compatibility: File = this.compatibility) =
        stageImportedAppleSdkPackageArtifacts(
        evidence, receipt, compatibility, "0.2.0", owned, work, output,
    )

    fun stageWithEvidenceOutput() = stageImportedAppleSdkPackageArtifacts(
        evidence, receipt, compatibility, "0.2.0", root, work, evidence,
    )

    fun symbolicOutput(): File {
        val link = owned.resolve("linked")
        Files.createSymbolicLink(link.toPath(), root.resolve("unowned").apply { mkdirs() }.toPath())
        return link.resolve("output")
    }

    fun symbolicDotDotOutput(): File {
        val link = owned.resolve("linked-dotdot")
        Files.createSymbolicLink(link.toPath(), owned.resolve("child").apply { mkdirs() }.toPath())
        return link.resolve("../output")
    }

    fun symbolicCompatibility(): File {
        val link = root.resolve("linked-input")
        Files.createSymbolicLink(link.toPath(), root.toPath())
        return link.resolve("sdk-compatibility.json")
    }

    fun symbolicDotDotCompatibility(): File {
        val link = root.resolve("linked-input-dotdot")
        Files.createSymbolicLink(link.toPath(), root.resolve("input-child").apply { mkdirs() }.toPath())
        return link.resolve("../sdk-compatibility.json")
    }

    fun rewritePackage(deviceBinary: String = "binary:ios-arm64", compatibility: String = this.compatibility.readText()) {
        val packageFramework = frameworkMembers.toMutableMap().apply {
            this["CodexAgent.xcframework/ios-arm64/CodexAgent.framework/CodexAgent"] = deviceBinary
            keys.filter { it.endsWith("sdk-compatibility.json") }.forEach { remove(it) }
        }
        writeZip(packageArchive, packageFramework + mapOf(
            "Package.swift" to "// package",
            "Sources/CodexAgent.swift" to "public struct CodexAgent {}",
            "Tests/CodexAgentTests.swift" to "// test",
            "LICENSE.txt" to "license",
            "THIRD_PARTY_NOTICES.md" to "notices",
            "openai-codex-LICENSE.txt" to "codex license",
            "openai-codex-NOTICE.txt" to "codex notice",
            "META-INF/codex-agent/sdk-compatibility.json" to compatibility,
        ))
    }

    fun rewriteChecksum(contents: String) = checksum.writeText(contents)
    fun removePackageArchive() = packageArchive.delete().let { }

    fun rebindProof() {
        val proof = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
        proof.atomicWriteJson(buildJsonObject {
            put("artifacts", buildJsonArray {
                listOf(packageArchive, frameworkArchive, checksum).forEach { file -> add(buildJsonObject {
                    put("fileName", JsonPrimitive(file.name))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                }) }
            })
        })
        receipt.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive("codex-agent-ios-verified-distribution-import-v1"))
            put("result", JsonPrimitive("passed"))
            put("candidateCommit", JsonPrimitive("1".repeat(40)))
            put("candidateTree", JsonPrimitive("2".repeat(40)))
            put("sourceProofSha256", JsonPrimitive(proof.releaseDigest()))
            put("nativeEvidenceReceiptSha256", JsonPrimitive("3".repeat(64)))
        })
    }

    fun originalDigests() = verifiedRegularFiles(evidence).mapValues { it.value.releaseDigest() }
    fun outputDigests() = verifiedRegularFiles(output).mapValues { it.value.releaseDigest() }

    private fun writeZip(file: File, members: Map<String, String>) {
        ZipOutputStream(file.outputStream()).use { archive -> members.forEach { (path, contents) ->
            archive.putNextEntry(ZipEntry(path))
            archive.write(contents.toByteArray())
            archive.closeEntry()
        } }
    }

    override fun close() = root.deleteRecursively().let { }
}

private fun fixture() = AppleSdkPackageFixture()
