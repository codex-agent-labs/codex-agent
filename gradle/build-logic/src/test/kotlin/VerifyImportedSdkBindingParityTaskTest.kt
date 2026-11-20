import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import org.gradle.testfixtures.ProjectBuilder

class VerifyImportedSdkBindingParityTaskTest {
    @Test
    fun `requires and receipts the exact complete M11 evidence directory`() {
        val root = createTempDirectory("imported-sdk-binding").toFile()
        try {
            val evidence = root.resolve("evidence").apply { mkdirs() }
            val members = (0 until 556).map { index ->
                "common|owner=sample/Owner|kind=property|abi=sample/Owner.value$index"
            }.sorted()
            val fixture = CrossLanguageBindingCliFixture(
                evidence,
                members,
                "binding-obligations-m11.json",
            )
            CrossLanguageBinding.entries.forEach { language ->
                fixture.writeReceipt(
                    language,
                    phase = CrossLanguageBindingPhase.M11,
                    excludedMembers = if (language == CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT) {
                        members.take(12)
                    } else {
                        emptyList()
                    },
                )
            }
            fixture.writeCompleteAudit(CrossLanguageBindingPhase.M11)
            CrossLanguageBinding.entries.forEach { language ->
                fixture.receipt(language).copyTo(evidence.resolve("${language.id}-parity.json"))
            }
            fixture.receiptDirectory.deleteRecursively()

            val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build()
            val result = root.resolve("result.json")
            val canonicalApi = evidence.resolve("canonical-api.json").copyTo(root.resolve("canonical-api.json"))
            val canonicalCoverage = evidence.resolve("canonical-coverage.json")
                .copyTo(root.resolve("canonical-coverage.json"))
            val task = project.tasks.create(
                "verifyImportedSdkBindingParity",
                VerifyImportedSdkBindingParityTask::class.java,
            ).apply {
                canonicalApiReport.set(canonicalApi)
                canonicalCoverageReceipt.set(canonicalCoverage)
                evidenceDirectory.set(evidence)
                resultFile.set(result)
            }

            task.verify()

            val report = result.readReleaseObject()
            assertEquals("passed", report.releaseString("result"))
            assertEquals(556, report.releaseInt("capabilityCount"))
            assertEquals(11, report.releaseInt("languageCount"))
            assertEquals(14, report.releaseInt("scenarioCount"))
            assertEquals(canonicalApi.releaseDigest(), report.releaseString("canonicalApiSha256"))
            assertEquals(
                canonicalCoverage.releaseDigest(),
                report.releaseString("canonicalCoverageSha256"),
            )
            assertEquals(6_104, report.releaseInt("active"))
            assertEquals(0, report.releaseInt("pending"))
            assertEquals(12, report.releaseInt("excluded"))
            assertEquals(6_104, report.releaseInt("satisfied"))
            assertEquals(0, report.releaseInt("missing"))

            evidence.resolve("extra.json").writeText("{}\n")
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            evidence.resolve("extra.json").delete()

            val dart = evidence.resolve("dart-parity.json")
            val dartBytes = dart.readBytes()
            dart.delete()
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            dart.writeBytes(dartBytes)

            val kotlin = evidence.resolve("kotlin-parity.json")
            val kotlinBytes = kotlin.readBytes()
            kotlin.writeBytes(evidence.resolve("java-parity.json").readBytes())
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            kotlin.writeBytes(kotlinBytes)

            canonicalApi.appendText(" ")
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            canonicalApi.writeBytes(evidence.resolve("canonical-api.json").readBytes())

            canonicalCoverage.appendText(" ")
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            canonicalCoverage.writeBytes(evidence.resolve("canonical-coverage.json").readBytes())

            val externalDart = root.resolve("external-dart-parity.json").apply { writeBytes(dartBytes) }
            dart.delete()
            Files.createSymbolicLink(dart.toPath(), externalDart.toPath())
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
            Files.delete(dart.toPath())

            task.evidenceDirectory.set(root.resolve("missing-evidence"))
            result.writeText("stale passed report\n")
            assertFailsWith<IllegalStateException> { task.verify() }
            assertFalse(result.exists())
        } finally {
            root.deleteRecursively()
        }
    }
}
