import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import org.gradle.testfixtures.ProjectBuilder

/** Real archive and Python inventory checks, not Apple execution or receipt admission. */
class AppleValidationEvidenceTaskTest {
    @Test
    fun `task archive preserves empty streams through strict Python transport inventory`() = fixture { root ->
        val source = root.resolve("raw").apply { mkdirs() }
        source.resolve("stdout.bin").writeBytes(byteArrayOf(0, -1, 10))
        source.resolve("stderr.bin").writeBytes(byteArrayOf())
        val stage = root.resolve("external-execution")
        val archive = stage.resolve("apple-validation-evidence.zip")
        val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build()
        val task = project.tasks.register("archiveEvidence", ArchiveAppleValidationEvidenceTask::class.java).get()
        task.sourceLayout.set(mapOf("device-raw" to source.path))
        task.evidenceInputs.from(source)
        task.archiveFile.set(archive)
        task.archive()

        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("ci/products/sdk_apple_validation_evidence.py").isFile }
        val script = """
            import sys
            from pathlib import Path
            from ci.products.sdk_apple_validation_evidence import verify_apple_validation_evidence_archive
            from ci.products.inventory import regular_file_inventory
            stage = Path(sys.argv[1])
            member = 'apple-validation-evidence.zip'
            records = verify_apple_validation_evidence_archive(stage / member, ('device-raw',))
            assert [(r['relativePath'], r['bytes']) for r in records] == [
                ('device-raw/stderr.bin', 0), ('device-raw/stdout.bin', 3)]
            inventory = regular_file_inventory(stage)
            assert len(inventory) == 1 and inventory[0]['relativePath'] == member
            assert inventory[0]['bytes'] > 0
            assert not (stage / 'output-manifest.json').exists()
        """.trimIndent()
        val process = ProcessBuilder("python3", "-c", script, stage.path)
            .directory(repository).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().readText()
        assertEquals(0, process.waitFor(), output)
        assertEquals(0L, source.resolve("stderr.bin").length())
    }

    @Test
    fun `task rejects undeclared source layout without publishing`() = fixture { root ->
        val source = root.resolve("source").apply { mkdirs() }
        source.resolve("raw").writeText("original")
        val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build()
        val task = project.tasks.register("archiveEvidence", ArchiveAppleValidationEvidenceTask::class.java).get()
        val archive = root.resolve("output.zip")
        task.sourceLayout.set(mapOf("raw" to source.path))
        task.archiveFile.set(archive)
        assertFailsWith<IllegalStateException> { task.archive() }
        assertFalse(archive.exists())
    }

    private fun fixture(block: (File) -> Unit) {
        val root = createTempDirectory("apple-validation-envelope-").toFile().canonicalFile
        try { block(root) } finally { root.deleteRecursively() }
    }
}
