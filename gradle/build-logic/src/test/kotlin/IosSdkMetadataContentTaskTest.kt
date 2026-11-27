import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.testfixtures.ProjectBuilder

/** Configuration/command checks only; the canonical Python writer is tested separately. */
class IosSdkMetadataContentTaskTest {
    @Test
    fun `canonical writer receives only package and two validation projections`() {
        val root = createTempDirectory("ios-sdk-metadata-content-task-").toFile()
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create("content", WriteIosSdkMetadataContentTask::class.java)
            task.repositoryRoot.set(root)
            task.sdkVersion.set("0.8.1")
            task.packageStage.set(root.resolve("captured-package"))
            task.deviceValidation.set(root.resolve("device/apple-validation.json"))
            task.simulatorValidation.set(root.resolve("simulator/apple-validation.json"))
            task.outputFile.set(root.resolve("stage/outputs/evidence/apple-metadata.json"))

            assertEquals(listOf(
                "python3", "-m", "ci.products.sdk_apple_metadata",
                "--sdk-version", "0.8.1",
                "--package-stage", root.resolve("captured-package").absolutePath,
                "--device-validation", root.resolve("device/apple-validation.json").absolutePath,
                "--simulator-validation", root.resolve("simulator/apple-validation.json").absolutePath,
                "--output", root.resolve("stage/outputs/evidence/apple-metadata.json").absolutePath,
            ), task.commandLine)
            assertFalse(task.outputFile.get().asFile.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `task exposes typed content inputs and one output without product tooling`() {
        val type = WriteIosSdkMetadataContentTask::class.java
        listOf("SdkVersion", "PythonExecutable").forEach {
            assertNotNull(type.getMethod("get$it").getAnnotation(Input::class.java))
        }
        assertNotNull(type.getMethod("getPackageStage").getAnnotation(InputDirectory::class.java))
        listOf("DeviceValidation", "SimulatorValidation").forEach {
            assertNotNull(type.getMethod("get$it").getAnnotation(InputFile::class.java))
        }
        assertNotNull(type.getMethod("getProducerSources").getAnnotation(InputFiles::class.java))
        assertNotNull(type.getMethod("getRepositoryRoot").getAnnotation(Internal::class.java))
        assertNotNull(type.getMethod("getCommandLine").getAnnotation(Internal::class.java))
        assertNotNull(type.getMethod("getOutputFile").getAnnotation(OutputFile::class.java))

        val source = File("src/main/kotlin/IosSdkMetadataContentTask.kt").readText()
        assertTrue("outputs.upToDateWhen { false }" in source)
        assertTrue("environment(\"PYTHONDONTWRITEBYTECODE\", \"1\")" in source)
        for (forbidden in listOf("xcodebuild", "swift", "clang", "linkReleaseFramework", "sourceSnapshot")) {
            assertFalse(forbidden in source, forbidden)
        }
    }
}
