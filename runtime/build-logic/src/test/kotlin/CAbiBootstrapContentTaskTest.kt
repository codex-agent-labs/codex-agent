import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class CAbiBootstrapContentTaskTest {
    @Test
    fun `delegates canonical content to Python and preserves original raw bytes`() = fixture { root, raw, content ->
        val original = raw.readBytes().toList()
        val contract = root.resolve("contract").apply { mkdir() }
        val projected = "{\"fixture\":\"content only\"}\n"
        content.writeText("stale sidecar")
        prepareCAbiBootstrapContent(raw, content, listOf(contract))
        assertFalse(content.exists())
        writeCAbiBootstrapContent(raw, content, contract) { command, capture ->
            assertEquals(listOf("python3", "-E", "-s", "-B", "-m", "ci.products.sdk_runtime_content", "bootstrap",
                "--raw", raw.absolutePath, "--contract-directory", contract.absolutePath), command)
            assertEquals(content.parentFile, capture.parentFile)
            assertTrue(capture != content && capture != raw)
            assertFalse(content.exists())
            // Command/stdout fixture only: this never claims real bootstrap or host acceptance.
            capture.writeText(projected)
        }
        assertEquals(projected, content.readText())
        assertEquals(original, raw.readBytes().toList())
        assertEquals(setOf(raw.name, content.name), raw.parentFile.listFiles()!!.map { it.name }.toSet())
    }

    @Test
    fun `invalid sidecar scopes preserve old sidecar and original evidence`() = fixture { root, raw, content ->
        content.writeText("old sidecar")
        val original = raw.readText()
        for (inputs in listOf(listOf(raw), listOf(content), listOf(content.parentFile))) {
            assertFailsWith<IllegalStateException> { prepareCAbiBootstrapContent(raw, content, inputs) }
        }
        val wrong = raw.parentFile.resolve("wrong.json").apply { writeText("wrong destination sentinel") }
        assertFailsWith<IllegalStateException> { prepareCAbiBootstrapContent(raw, wrong, emptyList()) }
        assertFailsWith<IllegalStateException> {
            prepareCAbiBootstrapContent(raw, root.resolve("build/../bootstrap-content.json"), emptyList())
        }
        assertEquals("old sidecar", content.readText())
        assertEquals("wrong destination sentinel", wrong.readText())
        assertEquals(original, raw.readText())
        val external = root.resolve("external.json").apply { writeText("external sentinel") }
        content.delete()
        Files.createSymbolicLink(content.toPath(), external.toPath())
        try {
            assertFailsWith<IllegalStateException> { prepareCAbiBootstrapContent(raw, content, emptyList()) }
            assertEquals("external sentinel", external.readText())
            assertEquals(original, raw.readText())
        } finally {
            Files.delete(content.toPath())
        }
    }

    @Test
    fun `failed empty or mutating projector never publishes sidecar`() {
        for (case in listOf("failure", "empty", "mutation")) fixture { root, raw, content ->
            val original = raw.readText()
            prepareCAbiBootstrapContent(raw, content, emptyList())
            assertFailsWith<IllegalStateException> {
                writeCAbiBootstrapContent(raw, content, root.resolve("contract")) { _, capture ->
                    when (case) {
                        "failure" -> error("projector rejected original raw evidence")
                        "empty" -> capture.writeText("")
                        "mutation" -> { capture.writeText("projected"); raw.appendText("mutation") }
                    }
                }
            }
            assertFalse(content.exists())
            assertEquals(listOf(raw.name), raw.parentFile.listFiles()!!.map { it.name })
            if (case != "mutation") assertEquals(original, raw.readText())
        }
    }

    @Test
    fun `sidecar delegation follows complete existing raw evidence gate`() {
        val source = File("src/main/kotlin/CrossLanguageCAbiBootstrapEvidence.kt").readText()
        val task = source.substringAfter("abstract class GenerateCAbiBootstrapEvidenceTask")
            .substringBefore("private fun compileConsumer")
        assertTrue(task.indexOf("prepareCAbiBootstrapContent(output, content, inputs.files.files)") <
            task.indexOf("Files.deleteIfExists(output.toPath())"))
        assertTrue(task.indexOf("output.atomicWriteJson(report)") < task.indexOf("writeCAbiBootstrapContent(output, content,"))
        assertTrue(task.indexOf("C ABI bootstrap evidence is not canonically encoded") <
            task.indexOf("writeCAbiBootstrapContent(output, content,"))
        assertTrue("contentProducerSources: ConfigurableFileCollection" in task)
        assertTrue("standardOutput = stdout" in task)
    }

    private fun fixture(action: (File, File, File) -> Unit) {
        val root = createTempDirectory("bootstrap-content-task-").toFile().canonicalFile
        try {
            val raw = root.resolve("build/bootstrap-evidence.json").apply {
                parentFile.mkdirs(); writeText("original raw evidence fixture\n")
            }
            action(root, raw, raw.parentFile.resolve("bootstrap-content.json"))
        } finally {
            root.deleteRecursively()
        }
    }
}
