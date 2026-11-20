import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/**
 * Executes the exact saved registration block in an isolated Gradle fixture.
 * This is narrower than full iOS plugin configuration: no Apple plugin, compiler,
 * Python projection or semantic admission runs. The task classes are real.
 */
class IosSdkMetadataRegistrationTest {
    private val source = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
    private val start = "// Artifact-only iOS metadata registration. Original receipt/source admission is caller-owned."
    private val end = "tasks.register(\"verifyIosRuntime\")"

    @Test
    fun `exact metadata graph consumes only imported artifacts and emits singleton content manifest`() = fixture { root ->
        val result = runner(root, properties(root), "writeSdkIosMetadataOutputManifest").build()
        val selected = Regex("^(:\\S+) SKIPPED$", RegexOption.MULTILINE).findAll(result.output)
            .map { it.groupValues[1] }.toList()
        assertEquals(listOf(":writeSdkIosMetadataContent", ":writeSdkIosMetadataOutputManifest"), selected, result.output)
        assertTrue("METADATA_REGISTERED=true" in result.output, result.output)
        assertFalse(root.resolve("build/product-stage/sdk/sdk-ios/metadata").exists())
        assertFalse(root.resolve("original-package").exists())
    }

    @Test
    fun `unrelated identity never registers metadata producers despite supplied artifact properties`() = fixture { root ->
        listOf("codexAgent.product" to "runtime", "codexAgent.component" to "sdk-core",
            "codexAgent.phase" to "validation", "codexAgent.target" to "ios-arm64").forEach { changed ->
            val result = runner(root, properties(root) + changed, "help").build()
            assertTrue("METADATA_REGISTERED=false" in result.output, result.output)
            assertFalse("\n:writeSdkIosMetadata" in result.output, result.output)
        }
    }

    @Test
    fun `selected metadata rejects each missing or blank original input before graph execution`() = fixture { root ->
        listOf("codexAgent.sdkVersion", "codexAgent.iosMetadataPackageStage",
            "codexAgent.iosMetadataDeviceValidationContent", "codexAgent.iosMetadataSimulatorValidationContent",
        ).forEach { property ->
            val result = runner(root, properties(root) - property, "help").buildAndFail()
            assertTrue("Imported iOS metadata requires $property" in result.output, result.output)
            assertFalse("\n:writeSdkIosMetadata" in result.output, result.output)
        }
        val result = runner(root, properties(root) + ("codexAgent.iosMetadataPackageStage" to " "), "help").buildAndFail()
        assertTrue("Imported iOS metadata requires codexAgent.iosMetadataPackageStage" in result.output, result.output)
    }

    private fun properties(root: File) = mapOf(
        "codexAgent.product" to "sdk", "codexAgent.component" to "sdk-ios",
        "codexAgent.phase" to "metadata", "codexAgent.target" to "ios", "codexAgent.sdkVersion" to "0.8.1",
        "codexAgent.iosMetadataPackageStage" to root.resolve("original-package").path,
        "codexAgent.iosMetadataDeviceValidationContent" to root.resolve("device/apple-validation.json").path,
        "codexAgent.iosMetadataSimulatorValidationContent" to root.resolve("simulator/apple-validation.json").path,
    )

    private fun runner(root: File, properties: Map<String, String>, task: String) = GradleRunner.create()
        .withProjectDir(root).withPluginClasspath()
        .withArguments(listOf(task, "--dry-run", "--offline", "--no-configuration-cache", "--console=plain") +
            properties.map { (key, value) -> "-P$key=$value" })

    private fun fixture(block: (File) -> Unit) {
        val root = createTempDirectory("ios-metadata-registration-").toFile().canonicalFile
        try {
            assertEquals(1, source.split(start).size - 1)
            val registration = source.substringAfter(start).substringBefore(end)
            check(registration.contains("writeSdkIosMetadataOutputManifest"))
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"ios-metadata-fixture\"\n")
            root.resolve("build.gradle.kts").writeText(
                "plugins { id(\"codexagent.codex-runtime\") apply false }\n" + registration + "\n" +
                    """
                    val registered = tasks.names.contains("writeSdkIosMetadataContent")
                    println("METADATA_REGISTERED=" + registered)
                    if (registered) {
                        val content = tasks.named<WriteIosSdkMetadataContentTask>("writeSdkIosMetadataContent").get()
                        val manifest = tasks.named<WriteProductOutputManifestTask>("writeSdkIosMetadataOutputManifest").get()
                        check(content.taskDependencies.getDependencies(content).isEmpty())
                        check(manifest.taskDependencies.getDependencies(manifest) == setOf(content))
                        check(content.sdkVersion.get() == "0.8.1")
                        check(content.packageStage.get().asFile == file("original-package"))
                        check(content.deviceValidation.get().asFile == file("device/apple-validation.json"))
                        check(content.simulatorValidation.get().asFile == file("simulator/apple-validation.json"))
                        val stage = layout.buildDirectory.dir("product-stage/sdk/sdk-ios/metadata").get().asFile
                        check(content.outputFile.get().asFile == stage.resolve("outputs/evidence/apple-metadata.json"))
                        check(content.repositoryRoot.get().asFile == projectDir)
                        check(content.producerSources.files == setOf(file("ci/products")))
                        check(listOf(manifest.product.get(), manifest.component.get(), manifest.phase.get(),
                            manifest.target.get(), manifest.productVersion.get()) == listOf("sdk", "sdk-ios", "metadata", "ios", "0.8.1"))
                        check(manifest.outputRoots.get() == mapOf("apple-metadata-content" to "outputs/evidence"))
                        check(manifest.expectedOutputPaths.get() == listOf("outputs/evidence/apple-metadata.json"))
                        check(manifest.outputsDirectory.get().asFile == stage.resolve("outputs"))
                        check(manifest.stageRoot.get().asFile == stage)
                        check(manifest.manifestFile.get().asFile == stage.resolve("output-manifest.json"))
                        check(manifest.repositoryRoot.get().asFile == projectDir)
                    }
                    """.trimIndent() + "\n",
            )
            block(root)
        } finally {
            root.deleteRecursively()
        }
    }
}
