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
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.testfixtures.ProjectBuilder

/** Configuration/command checks only; no Python producer, compiler, or Apple tool is executed. */
class AppleValidationContentTasksTest {
    @Test
    fun `fixed Python projection receives only existing selected content inputs`() {
        val root = createTempDirectory("apple-validation-content-task-").toFile()
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create("content", WriteAppleValidationContentTask::class.java)
            task.repositoryRoot.set(root)
            task.sdkVersion.set("0.8.1")
            task.packageStage.set(root.resolve("captured-package"))
            task.sdkCompatibility.set(root.resolve("sdk-compatibility.json"))
            task.canonicalApi.set(root.resolve("canonical-api.json"))
            task.canonicalCoverage.set(root.resolve("canonical-coverage.json"))
            task.swiftReceipt.set(root.resolve("swift-parity.json"))
            task.objectiveCReceipt.set(root.resolve("objective-c-parity.json"))
            task.outputFile.set(root.resolve("stage/outputs/validation/apple-validation.json"))
            for (target in listOf("ios-arm64", "ios-simulator-arm64")) {
                task.target.set(target)
                assertEquals(listOf(
                    "python3", "-m", "ci.products.sdk_apple_validation_content",
                    "--target", target, "--sdk-version", "0.8.1",
                    "--package-stage", root.resolve("captured-package").absolutePath,
                    "--sdk-compatibility", root.resolve("sdk-compatibility.json").absolutePath,
                    "--canonical-api", root.resolve("canonical-api.json").absolutePath,
                    "--canonical-coverage", root.resolve("canonical-coverage.json").absolutePath,
                    "--swift-receipt", root.resolve("swift-parity.json").absolutePath,
                    "--objective-c-receipt", root.resolve("objective-c-parity.json").absolutePath,
                    "--output", root.resolve("stage/outputs/validation/apple-validation.json").absolutePath,
                ), task.commandLine)
            }
            assertFalse(task.outputFile.get().asFile.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `task has typed configuration cache safe content inputs and one output`() {
        val type = WriteAppleValidationContentTask::class.java
        listOf("Target", "SdkVersion", "PythonExecutable").forEach {
            assertNotNull(type.getMethod("get$it").getAnnotation(Input::class.java))
        }
        assertNotNull(type.getMethod("getPackageStage").getAnnotation(InputDirectory::class.java))
        listOf("SdkCompatibility", "CanonicalApi", "CanonicalCoverage", "SwiftReceipt", "ObjectiveCReceipt").forEach {
            assertNotNull(type.getMethod("get$it").getAnnotation(InputFile::class.java))
        }
        assertNotNull(type.getMethod("getRepositoryRoot").getAnnotation(Internal::class.java))
        assertNotNull(type.getMethod("getCommandLine").getAnnotation(Internal::class.java))
        assertNotNull(type.getMethod("getOutputFile").getAnnotation(OutputFile::class.java))
        val source = File("src/main/kotlin/AppleValidationContentTasks.kt").readText()
        assertTrue("outputs.upToDateWhen { false }" in source)
        assertTrue("environment(\"PYTHONDONTWRITEBYTECODE\", \"1\")" in source)
        assertFalse("project." in source)
    }

    @Test
    fun `canonical route requires full external archive then exact singleton manifest`() {
        val source = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
        val archive = source.substringAfter("val archiveValidation =").substringBefore("val validationStage =")
        assertTrue("dependsOn(appleBindingEvidence, deviceConsumer)" in archive)
        assertTrue("archiveFile.set(executionEnvelope" in archive)
        val content = source.substringAfter("val validationContent =").substringBefore(
            "tasks.register<WriteProductOutputManifestTask>(\"writeSdkIosValidationOutputManifest\")",
        )
        assertTrue("dependsOn(archiveValidation)" in content)
        assertTrue("snapshotSdkIosValidationPackage" in content)
        assertTrue(".flatMap { it.outputDirectory }" in content)
        assertTrue("canonicalApi.set(appleBindingEvidence.flatMap { it.canonicalApiReport })" in content)
        assertTrue("canonicalCoverage.set(appleBindingEvidence.flatMap { it.canonicalCoverageReceipt })" in content)
        val manifest = source.substringAfter(
            "tasks.register<WriteProductOutputManifestTask>(\"writeSdkIosValidationOutputManifest\")",
        ).substringBefore("tasks.register(\"verifyIosRuntime\")")
        for (required in listOf(
            "dependsOn(validationContent)", "product.set(\"sdk\")", "component.set(\"sdk-ios\")",
            "phase.set(\"validation\")", "target.set(validationTarget)",
            "productVersion.set(providers.gradleProperty(\"codexAgent.sdkVersion\"))",
            "outputRoots.set(mapOf(\"apple-validation-content\" to \"outputs/validation\"))",
            "expectedOutputPaths.set(listOf(\"outputs/validation/apple-validation.json\"))",
        )) assertTrue(required in manifest, required)
        assertTrue("rootProject.layout.buildDirectory.dir(\"product-stage/sdk/sdk-ios/validation\")" in source)
        assertFalse("executionEnvelope" in manifest)
        val routing = File("src/main/kotlin/codexagent.sdk-product.gradle.kts").readText()
            .substringAfter("Triple(\"sdk\", \"sdk-ios\", \"validation\") ->").substringBefore("Triple(")
        assertTrue("project(\":codex-agent-runtime-ios\").tasks.named(\"writeSdkIosValidationOutputManifest\")" in routing)
    }
}
