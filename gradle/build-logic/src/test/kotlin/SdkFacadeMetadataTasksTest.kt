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
class SdkFacadeMetadataTasksTest {
    private fun requestValue(root: File): JsonObject = JsonObject(mapOf(
        "sdkVersion" to JsonPrimitive("0.8.7"),
        "packageStage" to JsonPrimitive(root.resolve("package").absolutePath),
        "packageReceipt" to JsonPrimitive(root.resolve("package.json").absolutePath),
        "contractDigest" to JsonPrimitive("sha256:" + "a".repeat(64)),
        "componentDigests" to JsonObject(emptyMap()),
        "validations" to JsonObject(sdkFacadeConsumerCompileTasks.keys.associateWith { target -> JsonObject(mapOf(
            "stageRoot" to JsonPrimitive(root.resolve("originals/$target/stage").absolutePath),
            "phaseReceipt" to JsonPrimitive(root.resolve("originals/$target/receipt.json").absolutePath),
        )) }),
    ))

    @Test
    fun `referenced inputs are lazy and include exact eleven original pairs`() {
        val root = createTempDirectory("facade-metadata-inputs-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val request = root.resolve("request.json")
            var reads = 0
            val provider = project.providers.provider { reads++; sdkFacadeMetadataInputFiles(request) }
            val inputs = project.files(provider)
            project.registerSdkFacadeMetadataTasks(project.layout.file(project.providers.provider { request }),
                project.providers.provider { "0.8.7" }, inputs)
            assertEquals(0, reads)
            assertFalse(request.exists())
            request.writeText(requestValue(root).toString())
            val expected = setOf(root.resolve("package"), root.resolve("package.json")) +
                sdkFacadeConsumerCompileTasks.keys.flatMap { target -> listOf(
                    root.resolve("originals/$target/stage"), root.resolve("originals/$target/receipt.json"),
                ) }
            assertEquals(expected, inputs.files)
            assertEquals(24, inputs.files.size)
            assertTrue(reads > 0)
            val value = requestValue(root)
            val validations = value.getValue("validations") as JsonObject
            for (targets in listOf(validations - "jvm", validations + ("extra" to validations.getValue("jvm")))) {
                request.writeText(JsonObject(value + ("validations" to JsonObject(targets))).toString())
                assertFailsWith<IllegalStateException> { sdkFacadeMetadataInputFiles(request) }
            }
            for (path in listOf("relative/package", root.resolve("a/../package").path)) {
                request.writeText(JsonObject(value + ("packageStage" to JsonPrimitive(path))).toString())
                assertFailsWith<IllegalStateException> { sdkFacadeMetadataInputFiles(request) }
            }
            request.writeText(JsonObject(value + ("unexpected" to JsonPrimitive(true))).toString())
            assertFailsWith<IllegalStateException> { sdkFacadeMetadataInputFiles(request) }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `fixed writer and manifest join only explicit imported inputs`() {
        val root = createTempDirectory("facade metadata task ").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val request = project.layout.projectDirectory.file("caller request.json")
            val original = root.resolve("original validation/content.json")
            val callerInputs = project.files(original)
            val manifest = project.registerSdkFacadeMetadataTasks(
                project.providers.provider { request }, project.providers.provider { "0.8.7" }, callerInputs,
            ).get()
            val content = project.tasks.getByName("writeSdkCoreMetadataContent") as WriteSdkFacadeMetadataContentTask
            val stage = root.resolve("build/product-stage/sdk/sdk-core/metadata/common")
            assertEquals(listOf(
                "python3", "-m", "ci.products.sdk_platform_metadata",
                "--request", request.asFile.absolutePath,
                "--output", stage.resolve("outputs/evidence/facade-metadata.json").absolutePath,
            ), content.commandLine)
            assertEquals(setOf(original), content.callerInputs.files)
            assertEquals(emptySet(), content.taskDependencies.getDependencies(content))
            assertEquals(setOf(content), manifest.taskDependencies.getDependencies(manifest))
            assertEquals(listOf("sdk", "sdk-core", "metadata", "common", "0.8.7"), listOf(
                manifest.product.get(), manifest.component.get(), manifest.phase.get(),
                manifest.target.get(), manifest.productVersion.get(),
            ))
            assertEquals(mapOf("sdk-facade-metadata-content" to "outputs/evidence"), manifest.outputRoots.get())
            assertEquals(listOf("outputs/evidence/facade-metadata.json"), manifest.expectedOutputPaths.get())
            assertEquals(stage, manifest.stageRoot.get().asFile)
            assertEquals(stage.resolve("output-manifest.json"), manifest.manifestFile.get().asFile)
            assertFalse(stage.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `existing stage and mismatched request version fail before any process`() {
        val root = createTempDirectory("facade-metadata-preflight-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create("content", WriteSdkFacadeMetadataContentTask::class.java)
            val stage = root.resolve("stage")
            val request = root.resolve("request.json").apply { writeText("{\"sdkVersion\":\"0.8.6\"}\n") }
            task.repositoryRoot.set(root)
            task.stageRoot.set(stage)
            task.outputFile.set(stage.resolve("outputs/evidence/facade-metadata.json"))
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
    fun `registration requires explicit request and version`() {
        val root = createTempDirectory("facade-metadata-registration-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val absent = project.objects.fileProperty()
            assertFailsWith<IllegalStateException> {
                project.registerSdkFacadeMetadataTasks(absent, project.providers.provider { "0.8.7" }, project.files())
            }
            absent.set(root.resolve("request.json"))
            assertFailsWith<IllegalStateException> {
                project.registerSdkFacadeMetadataTasks(absent, project.providers.provider { "latest" }, project.files())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `task tracks caller references separately and delegates schema to Python`() {
        val type = WriteSdkFacadeMetadataContentTask::class.java
        assertNotNull(type.getMethod("getRequestFile").getAnnotation(InputFile::class.java))
        for (name in listOf("CallerInputs", "ProducerSources")) {
            assertNotNull(type.getMethod("get$name").getAnnotation(InputFiles::class.java))
        }
        assertNotNull(type.getMethod("getOutputFile").getAnnotation(OutputFile::class.java))
        val source = File("src/main/kotlin/SdkFacadeMetadataTasks.kt").readText()
        assertTrue("outputs.upToDateWhen { false }" in source)
        assertTrue("environment(\"PYTHONDONTWRITEBYTECODE\", \"1\")" in source)
        for (forbidden in listOf("ExecOperations.exec", "publishToMaven", "compileKotlin", "VerifyStagedKmpConsumerTask")) {
            assertFalse(forbidden in source, forbidden)
        }
    }
}
