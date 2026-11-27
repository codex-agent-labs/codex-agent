import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class RuntimeBundleEvidenceTest {
    @Test
    fun `staging rejects a classifier changed after inspection before reading its manifest`() {
        val root = createTempDirectory("runtime-evidence-bundle").toFile()
        try {
            val archive = root.resolve("classifier.zip")
            writeClassifier(archive, "original")
            val inspectedSha256 = archive.releaseDigest()
            writeClassifier(archive, "changed")

            val failure = assertFailsWith<IllegalStateException> {
                stageRuntimeBundleForEvidence(
                    archive, "macosArm64", "app-server-macos-arm64", inspectedSha256, root.resolve("evidence"),
                )
            }
            assertTrue(failure.message.orEmpty().contains("changed after inspection"))
            assertTrue(root.resolve("evidence/bundle").listFiles().orEmpty().isEmpty())

            val staged = stageRuntimeBundleForEvidence(
                archive, "macosArm64", "app-server-macos-arm64", archive.releaseDigest(), root.resolve("accepted"),
            )
            val copy = staged.bundle.resolve("codex-agent-runtime-desktop-0.8.0-app-server-macos-arm64.zip")
            assertEquals(archive.releaseDigest(), copy.releaseDigest())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun writeClassifier(archive: File, payload: String) {
        ZipOutputStream(archive.outputStream()).use { zip ->
            zip.putNextEntry(ZipEntry("codex-runtime-manifest.json"))
            zip.write(
                """{"schemaVersion":1,"libraryVersion":"0.8.0","target":"macosArm64","classifier":"app-server-macos-arm64"}"""
                    .toByteArray(),
            )
            zip.closeEntry()
            zip.putNextEntry(ZipEntry("payload.txt"))
            zip.write(payload.toByteArray())
            zip.closeEntry()
        }
    }
}
