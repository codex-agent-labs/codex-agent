import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.testfixtures.ProjectBuilder

/** Configuration and rejected preflight only; no Python, compiler, or hosted worker runs. */
class SdkAndroidMetadataTasksTest {
    private fun requestValue(root: File) = JsonObject(mapOf(
        "sdkVersion" to JsonPrimitive("0.8.7"),
        "packageStage" to JsonPrimitive(root.resolve("package").absolutePath),
        "packageReceipt" to JsonPrimitive(root.resolve("package.json").absolutePath),
        "validationStage" to JsonPrimitive(root.resolve("validation").absolutePath),
        "validationReceipt" to JsonPrimitive(root.resolve("validation.json").absolutePath),
        "releaseAarSha256" to JsonPrimitive("sha256:" + "a".repeat(64)),
        "bundledRuntimeSha256" to JsonPrimitive("sha256:" + "b".repeat(64)),
    ))

    @Test
    fun `referenced inputs are lazy and exact`() {
        val root = createTempDirectory("android-metadata-inputs-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val request = root.resolve("request.json")
            var reads = 0
            val provider = project.providers.provider { reads++; sdkAndroidMetadataInputFiles(request) }
            val inputs = project.files(provider)
            project.registerSdkAndroidMetadataTasks(project.layout.file(project.providers.provider { request }),
                project.providers.provider { "0.8.7" }, inputs)
            assertEquals(0, reads)
            assertFalse(request.exists())
            request.writeText(requestValue(root).toString())
            assertEquals(setOf(root.resolve("package"), root.resolve("package.json"),
                root.resolve("validation"), root.resolve("validation.json")), inputs.files)
            assertTrue(reads > 0)
            for (value in listOf(
                JsonObject(requestValue(root) + ("unexpected" to JsonPrimitive(true))),
                JsonObject(requestValue(root) + ("packageStage" to JsonPrimitive("relative/package"))),
                JsonObject(requestValue(root) + ("validationReceipt" to JsonPrimitive(true))),
            )) {
                request.writeText(value.toString())
                assertFailsWith<IllegalStateException> { sdkAndroidMetadataInputFiles(request) }
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `fixed writer and manifest use only explicit imported inputs`() {
        val root = createTempDirectory("android metadata task ").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val request = project.layout.projectDirectory.file("caller request.json")
            val original = root.resolve("original validation/content.json")
            val manifest = project.registerSdkAndroidMetadataTasks(
                project.providers.provider { request }, project.providers.provider { "0.8.7" },
                project.files(original),
            ).get()
            val content = project.tasks.getByName("writeSdkAndroidMetadataContent") as
                WriteSdkAndroidMetadataContentTask
            val stage = root.resolve("build/product-stage/sdk/sdk-android/metadata/android")
            assertEquals(listOf(
                "python3", "-m", "ci.products.sdk_android_metadata",
                "--request", request.asFile.absolutePath,
                "--output", stage.resolve("outputs/evidence/android-metadata.json").absolutePath,
            ), content.commandLine)
            assertEquals(setOf(original), content.callerInputs.files)
            assertEquals(emptySet(), content.taskDependencies.getDependencies(content))
            assertEquals(setOf(content), manifest.taskDependencies.getDependencies(manifest))
            assertEquals(listOf("sdk", "sdk-android", "metadata", "android", "0.8.7"), listOf(
                manifest.product.get(), manifest.component.get(), manifest.phase.get(),
                manifest.target.get(), manifest.productVersion.get(),
            ))
            assertEquals(mapOf("android-metadata-content" to "outputs/evidence"), manifest.outputRoots.get())
            assertEquals(listOf("outputs/evidence/android-metadata.json"), manifest.expectedOutputPaths.get())
            assertEquals(stage, manifest.stageRoot.get().asFile)
            assertEquals(stage.resolve("output-manifest.json"), manifest.manifestFile.get().asFile)
            assertFalse(stage.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `existing stage and mismatched request version fail before process`() {
        val root = createTempDirectory("android-metadata-preflight-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create("content", WriteSdkAndroidMetadataContentTask::class.java)
            val stage = root.resolve("stage")
            val request = root.resolve("request.json").apply { writeText("{\"sdkVersion\":\"0.8.6\"}\n") }
            task.repositoryRoot.set(root)
            task.stageRoot.set(stage)
            task.outputFile.set(stage.resolve("outputs/evidence/android-metadata.json"))
            task.requestFile.set(request)
            task.sdkVersion.set("0.8.7")
            stage.mkdir()
            val stale = stage.resolve("stale.json").apply { writeText("{}\n") }
            assertTrue(assertFailsWith<IllegalStateException> { task.writeContent() }.message!!.contains("fresh"))
            stale.delete()
            stage.resolve("outputs/evidence").mkdirs()
            assertTrue(assertFailsWith<IllegalStateException> { task.writeContent() }.message!!.contains("SDK version"))
            assertFalse(task.outputFile.get().asFile.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `registration requires request and semver and task has no compilation graph`() {
        val root = createTempDirectory("android-metadata-registration-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val absent = project.objects.fileProperty()
            assertFailsWith<IllegalStateException> {
                project.registerSdkAndroidMetadataTasks(absent, project.providers.provider { "0.8.7" }, project.files())
            }
            absent.set(root.resolve("request.json"))
            assertFailsWith<IllegalStateException> {
                project.registerSdkAndroidMetadataTasks(absent, project.providers.provider { "latest" }, project.files())
            }
            val type = WriteSdkAndroidMetadataContentTask::class.java
            assertNotNull(type.getMethod("getRequestFile").getAnnotation(InputFile::class.java))
            for (name in listOf("CallerInputs", "ProducerSources")) {
                assertNotNull(type.getMethod("get$name").getAnnotation(InputFiles::class.java))
            }
            assertNotNull(type.getMethod("getOutputFile").getAnnotation(OutputFile::class.java))
            val source = File("src/main/kotlin/SdkAndroidMetadataTasks.kt").readText()
            assertTrue("outputs.upToDateWhen { false }" in source)
            assertTrue("environment(\"PYTHONDONTWRITEBYTECODE\", \"1\")" in source)
            for (forbidden in listOf("publishToMaven", "compileKotlin", "VerifyStagedKmpConsumerTask",
                    "Firebase", "apkanalyzer")) {
                assertFalse(forbidden in source, forbidden)
            }
        } finally {
            root.deleteRecursively()
        }
    }
}
