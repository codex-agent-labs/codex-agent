import java.io.File
import java.security.MessageDigest
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder

class PrepareRuntimePinnedArchiveTaskTest {
    @Test
    fun `online mode retains URI validation without performing a download`() = withTask { task, _ ->
        task.offlineMode.set(false)
        assertFailsWith<java.net.URISyntaxException> { task.prepare() }
        assertFalse(task.outputFile.get().asFile.exists())
    }

    @Test
    fun `offline miss fails before resolving the download URI`() = withTask { task, root ->
        assertTrue(task.offlineMode.get())
        val error = assertFailsWith<IllegalStateException> { task.prepare() }
        assertTrue("Offline Runtime archive preparation requires" in error.message.orEmpty())
        assertFalse(task.outputFile.get().asFile.exists())
        assertFalse(root.resolve("build/tmp/prepare/archive.tar.gz").exists())
    }

    @Test
    fun `offline exact existing output is reused unchanged`() = withTask { task, _ ->
        val output = task.outputFile.get().asFile
        output.parentFile.mkdirs()
        output.writeBytes(pinnedBytes)
        val modified = output.lastModified()

        task.prepare()

        assertContentEquals(pinnedBytes, output.readBytes())
        assertEquals(modified, output.lastModified())
    }

    @Test
    fun `offline local archive replaces only after exact digest verification`() = withTask { task, root ->
        val local = root.resolve("local.tar.gz").apply { writeBytes(pinnedBytes) }
        task.localArchive.set(local)
        task.prepare()
        assertContentEquals(pinnedBytes, task.outputFile.get().asFile.readBytes())
        assertContentEquals(pinnedBytes, local.readBytes())

        val previous = "invalid previous output".toByteArray()
        task.outputFile.get().asFile.writeBytes(previous)
        local.writeText("tampered archive")
        val error = assertFailsWith<IllegalStateException> { task.prepare() }
        assertEquals("Pinned archive SHA-256 mismatch", error.message)
        assertContentEquals(previous, task.outputFile.get().asFile.readBytes())
    }

    @Test
    fun `offline wrong existing output never permits a download`() = withTask { task, _ ->
        val output = task.outputFile.get().asFile
        output.parentFile.mkdirs()
        output.writeText("stale output")
        val error = assertFailsWith<IllegalStateException> { task.prepare() }
        assertTrue("Offline Runtime archive preparation requires" in error.message.orEmpty())
        assertEquals("stale output", output.readText())
    }

    private val pinnedBytes = "opaque pinned archive fixture".toByteArray()

    private fun withTask(action: (PrepareRuntimePinnedArchiveTask, File) -> Unit) {
        val root = createTempDirectory("runtime-pinned-archive").toFile()
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            project.gradle.startParameter.isOffline = true
            val task = project.tasks.create("prepare", PrepareRuntimePinnedArchiveTask::class.java)
            // An invalid URI makes a missing guard fail locally, without a network attempt.
            task.sourceUrl.set("not a valid URI")
            task.expectedSha256.set(MessageDigest.getInstance("SHA-256").digest(pinnedBytes)
                .joinToString("") { "%02x".format(it) })
            task.outputFile.set(root.resolve("output/archive.tar.gz"))
            action(task, root)
        } finally {
            root.deleteRecursively()
        }
    }
}
