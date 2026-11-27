import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class JavaScriptSdkValidationArtifactGraphTest {
    private val repository = File("../..").canonicalFile
    private val source = File("src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText()

    @Test
    fun `validation imports a package and stages every existing compiler and behavior proof`() {
        val validation = source.substringAfter("val javascriptSdkValidationOutputs =")
        listOf(
            "check(importedNpmSdkPackageStage.isPresent)",
            "dependsOn(verifyImportedJavaScriptSdkCompatibility, verifyJavaScriptTypeScriptBindingParity)",
            "from(javaScriptBindingParityReceipt)", "from(npmPublicApiReport)",
            "from(npmPackedTestReport)", "from(npmConsumerSourceDirectory)",
            "component.set(\"javascript\")", "phase.set(\"validation\")", "target.set(\"node\")",
            "\"binding-evidence\" to \"outputs/binding-evidence\"",
            "\"compiler-evidence\" to \"outputs/compiler-evidence\"",
            "\"test-report\" to \"outputs/test-report\"",
            "\"test-program\" to \"outputs/test-program\"",
        ).forEach { assertTrue(it in validation, it) }
        val imported = source.substringAfter("val verifyImportedNpmRuntimeValidationOutputManifest =")
            .substringBefore("val generateJavaScriptEnumDeclarations =")
        assertTrue("component.set(\"node-js\")" in imported)
        assertTrue("target.set(\"node-js-binding\")" in imported)
        assertTrue("productVersion.set(npmRuntimeBindingVersion)" in imported)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimePackageVersion\")" in source)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimeBindingValidationVersion\")" in source)
        assertTrue("npmTarball.set(npmConsumerArchive)" in source)
        assertTrue("importedNpmContractSnapshotRoot, importedNpmRuntimeValidationSnapshotRoot" in source)
        listOf("snapshotImportedNpmContractBinaryStage", "snapshotImportedNpmRuntimeValidationStage").forEach {
            assertTrue("$it.configure { dependsOn(invalidateJavaScriptSdkValidationOutputs) }" in source)
        }
        assertTrue("if (importedNpmSdkPackageStage.isPresent) dependsOn(invalidateJavaScriptSdkValidationOutputs)" in source)
    }

    @Test
    fun `imported validation graph cannot reach SDK packaging or Runtime compilation`() {
        val fixture = createTempDirectory("javascript-validation-graph-").toFile()
        try {
            val result = GradleRunner.create().withProjectDir(repository).withArguments(
                "ciProductPhase", "--dry-run", "--offline", "--console=plain",
                "-Pkotlin.daemon.jvmargs=-Xmx2g",
                "--gradle-user-home", System.getenv("GRADLE_USER_HOME") ?: File(System.getProperty("user.home"), ".gradle").path,
                "-PcodexAgent.product=sdk", "-PcodexAgent.component=javascript", "-PcodexAgent.phase=validation",
                "-PcodexAgent.sdkPackageStageRoot=${fixture.absolutePath}",
                "-PcodexAgent.contractBinaryStage=${fixture.absolutePath}",
                "-PcodexAgent.runtimePackageStage=${fixture.absolutePath}",
                "-PcodexAgent.runtimeBindingValidationStage=${fixture.absolutePath}",
                "-PcodexAgent.runtimePackageVersion=0.2.6", "-PcodexAgent.runtimeBindingValidationVersion=0.2.5",
                // Graph-only fixture identifiers; no product task or receipt executes.
                "-PcodexAgent.candidateTree=${"a".repeat(40)}",
            ).build()
            val paths = result.output.lineSequence().filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                .map { it.removeSuffix(" SKIPPED") }.toSet()
            listOf("snapshotImportedJavaScriptSdkPackage", "verifyImportedJavaScriptSdkPackage",
                "verifyImportedJavaScriptSdkCompatibility", "verifyImportedNpmRuntimeValidationOutputManifest",
                "verifyPackedNpmConsumers", "verifyJavaScriptTypeScriptBindingParity",
                "stageJavaScriptSdkValidationPhase", "writeJavaScriptSdkValidationOutputManifest",
            ).forEach { task -> assertTrue(":codex-agent-sdk:$task" in paths, result.output) }
            listOf("packageNpm", "stageNpmPackage", "verifyNpmPackDryRun", "verifyNpmDeclarationGolden",
                "writeJavaScriptSdkPackageOutputManifest", "generateNativeWrapperSdkCompatibility",
            ).forEach { task -> assertFalse(":codex-agent-sdk:$task" in paths, result.output) }
            assertFalse(paths.any { it.startsWith(":codex-agent-runtime-desktop:") ||
                it.startsWith(":codex-agent-core:") ||
                it.substringAfterLast(':').startsWith("compile") ||
                it.substringAfterLast(':').startsWith("link") }, result.output)
        } finally {
            fixture.deleteRecursively()
        }
    }

    @Test
    fun `validation missing its package fails before any product task executes`() {
        val result = GradleRunner.create().withProjectDir(repository).withArguments(
            "ciProductPhase", "--offline", "--console=plain",
            "-Pkotlin.daemon.jvmargs=-Xmx2g",
            "--gradle-user-home", System.getenv("GRADLE_USER_HOME") ?: File(System.getProperty("user.home"), ".gradle").path,
            "-PcodexAgent.product=sdk", "-PcodexAgent.component=javascript", "-PcodexAgent.phase=validation",
        ).buildAndFail()
        assertTrue("SDK JavaScript validation requires codexAgent.sdkPackageStageRoot" in result.output, result.output)
        assertFalse(result.tasks.any { it.path.startsWith(":codex-agent-sdk:") }, result.output)
    }
}
