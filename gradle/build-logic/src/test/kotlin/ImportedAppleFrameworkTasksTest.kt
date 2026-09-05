import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.io.path.createTempDirectory
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.apache.commons.compress.archivers.zip.UnixStat
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream

class ImportedAppleFrameworkTasksTest {
    @Test
    fun `Kotlin Native framework platform uses supported-platform plist semantics`() {
        val infoPlist = File("CodexAgent.framework/Info.plist")
        assertEquals(
            listOf(
                "/usr/bin/plutil", "-extract", "CFBundleSupportedPlatforms.0", "raw", "-o", "-",
                infoPlist.absolutePath,
            ),
            importedFrameworkPlatformCommand(infoPlist),
        )
        verifyImportedFrameworkPlatform("iphoneos", "iPhoneOS\n")
        verifyImportedFrameworkPlatform("iphonesimulator", "iPhoneSimulator\n")
        val failure = assertFailsWith<IllegalStateException> {
            verifyImportedFrameworkPlatform("iphoneos", "iPhoneSimulator\n")
        }
        assertEquals(
            "Imported framework platform mismatch: expected=iphoneos actual=iPhoneSimulator",
            failure.message,
        )
    }

    @Test
    fun `verified XCFramework archive is extracted only through its import proof`() = fixture().use { fixture ->
        extractVerifiedAppleXCFramework(
            fixture.evidence, fixture.receipt, "0.2.0", fixture.work, fixture.output,
        )
        assertEquals(
            setOf("Info.plist", "ios-arm64", "ios-arm64-simulator"),
            fixture.output.list()?.toSet(),
        )
        assertTrue(fixture.output.resolve("ios-arm64/CodexAgent.framework/CodexAgent").isFile)
        assertFalse(fixture.output.walkTopDown().any { java.nio.file.Files.isSymbolicLink(it.toPath()) })
    }

    @Test
    fun `unsafe incomplete or cross-paired verified XCFramework archives are rejected`() {
        listOf("proof", "archive", "traversal", "duplicate", "symlink", "missing-slice").forEach { case ->
            fixture().use { fixture ->
                when (case) {
                    "proof" -> fixture.proof.appendText("changed")
                    "archive" -> fixture.archive.appendText("tampered")
                    "traversal" -> fixture.writeArchive(extra = listOf("CodexAgent.xcframework/../escape"))
                    "duplicate" -> fixture.writeArchive(extra = listOf("CodexAgent.xcframework/Info.plist/"))
                    "symlink" -> fixture.writeArchive(symlink = true)
                    else -> fixture.writeArchive(includeSimulator = false)
                }
                if (case !in setOf("proof", "archive")) fixture.writeProofAndReceipt()
                assertFailsWith<IllegalStateException>(case) {
                    extractVerifiedAppleXCFramework(
                        fixture.evidence, fixture.receipt, "0.2.0", fixture.work, fixture.output,
                    )
                }
                assertFalse(fixture.output.exists())
            }
        }
    }

    @Test
    fun `imported parity wiring consumes extracted framework without local assembly`() {
        val source = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
        val imported = source.substringAfter("verifiedDistributionTasks.importedXCFramework?.let")
            .substringBefore("tasks.register(\"verifyIosRuntime\")")
        assertTrue("stageCodexAgentAppleDistribution" in imported)
        assertTrue("appleCompilerEvidence.configure" in imported)
        assertEquals(3, imported.split("xcframeworkDirectory.set(imported.flatMap").size - 1)
        assertFalse("prepareCodexAgentReleaseXCFramework" in imported)
        val registration = File("src/main/kotlin/IosVerifiedDistributionRegistration.kt").readText()
        assertTrue("if (distribution.sdkCompatibilityFile != null)" in registration)
        assertTrue("dependsOn(\":codex-agent-sdk:generateNativeWrapperSdkCompatibility\")" in registration)
    }
}

private class VerifiedXCFrameworkFixture : AutoCloseable {
    private val root = createTempDirectory("verified-xcframework").toFile()
    val evidence = root.resolve("evidence").apply { mkdirs() }
    val archive = evidence.resolve("CodexAgent-0.2.0.xcframework.zip")
    val proof = evidence.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    val receipt = root.resolve("verification-receipt.json")
    val work = root.resolve("work")
    val output = root.resolve("output")

    init {
        writeArchive()
        writeProofAndReceipt()
    }

    fun writeArchive(
        includeSimulator: Boolean = true,
        extra: List<String> = emptyList(),
        symlink: Boolean = false,
    ) {
        val members = mutableListOf("CodexAgent.xcframework/Info.plist")
        val slices = listOf("ios-arm64") + if (includeSimulator) listOf("ios-arm64-simulator") else emptyList()
        slices.forEach { slice ->
            val framework = "CodexAgent.xcframework/$slice/CodexAgent.framework"
            members += listOf(
                "$framework/CodexAgent",
                "$framework/Headers/CodexAgent.h",
                "$framework/Modules/module.modulemap",
                "$framework/Info.plist",
                "$framework/PrivacyInfo.xcprivacy",
                "$framework/META-INF/codex-agent/sdk-compatibility.json",
            )
        }
        val symlinkPath = "CodexAgent.xcframework/ios-arm64/CodexAgent.framework/linked"
        ZipArchiveOutputStream(archive).use { zip ->
            (members + extra + if (symlink) listOf(symlinkPath) else emptyList()).forEach { path ->
                val entry = ZipArchiveEntry(path).apply {
                    unixMode = when {
                        path == symlinkPath -> UnixStat.LINK_FLAG or UnixStat.DEFAULT_LINK_PERM
                        path.endsWith('/') -> UnixStat.DIR_FLAG or UnixStat.DEFAULT_DIR_PERM
                        else -> UnixStat.FILE_FLAG or UnixStat.DEFAULT_FILE_PERM
                    }
                }
                zip.putArchiveEntry(entry)
                if (!path.endsWith('/')) zip.write("fixture:$path\n".toByteArray())
                zip.closeArchiveEntry()
            }
        }
    }

    fun writeProofAndReceipt() {
        proof.atomicWriteJson(buildJsonObject {
            put("artifacts", buildJsonArray { add(archive.releaseRecord(archive.name)) })
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

    override fun close() = root.deleteRecursively().let { }
}

private fun fixture() = VerifiedXCFrameworkFixture()
