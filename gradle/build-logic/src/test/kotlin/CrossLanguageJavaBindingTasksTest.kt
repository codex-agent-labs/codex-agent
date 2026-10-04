import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder

class CrossLanguageJavaBindingTasksTest {
    @Test
    fun `imported parity removes producers and still rejects missing real evidence`() {
        val root = createTempDirectory("imported-java-parity-").toFile()
        try {
            val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build()
            val producer = project.tasks.register("forbiddenProductBuild")
            val task = project.tasks.create("verifyJavaBindingParity", VerifyJavaBindingParityTask::class.java)
            task.dependsOn(producer)
            val inputs = root.resolve("originals").apply { mkdirs() }
            task.useImportedInputs(inputs)
            assertTrue(task.taskDependencies.getDependencies(task).isEmpty())
            assertEquals(inputs.resolve("core-jvm.jar"), task.coreJvmJar.get().asFile)
            assertEquals(inputs.resolve("core-android.aar"), task.coreAndroidAar.get().asFile)
            assertEquals(inputs.resolve("desktop-runtime.jar"), task.desktopRuntimeJar.get().asFile)
            assertEquals(inputs.resolve("android-runtime.aar"), task.androidRuntimeAar.get().asFile)
            assertEquals(inputs.resolve("compiled-java-tests"), task.compiledJavaTests.get().asFile)
            assertEquals(inputs.resolve("test-results"), task.testResults.get().asFile)
            val output = root.resolve("new-evidence/java-parity.json").apply {
                parentFile.mkdirs()
                writeText("stale success")
            }
            task.receiptFile.set(output)
            assertFailsWith<Exception> { task.verify() }
            assertFalse(output.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `parity cannot overwrite an original input`() {
        val root = createTempDirectory("imported-java-parity-").toFile()
        try {
            val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build()
            val task = project.tasks.create("verifyJavaBindingParity", VerifyJavaBindingParityTask::class.java)
            task.useImportedInputs(root)
            val original = root.resolve("core-jvm.jar").apply { writeText("preserved bytes") }
            task.receiptFile.set(original)
            val failure = assertFailsWith<IllegalStateException> { task.verify() }
            assertTrue("separate from its original inputs" in failure.message.orEmpty())
            assertEquals("preserved bytes", original.readText())
        } finally {
            root.deleteRecursively()
        }
    }
}
