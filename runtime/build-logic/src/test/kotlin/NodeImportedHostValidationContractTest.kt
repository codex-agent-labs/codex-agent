import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class NodeImportedHostValidationContractTest {
    private val source = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
    private val validation = source.substringAfter("fun registerNodeRuntimeValidation(")
        .substringBefore("val nodeJsBindingValidationRoot =")

    @Test
    fun `canonical ordinary Node validation requires the actual native host`() {
        val guard = source.substringAfter("val nodeValidationComponent =")
            .substringBefore("val nodeValidationManifestFile =")
        listOf(
            "providers.gradleProperty(\"codexAgent.product\").orNull == \"runtime\"",
            "providers.gradleProperty(\"codexAgent.component\").orNull in setOf(\"node-js\", \"node-wasm\")",
            "providers.gradleProperty(\"codexAgent.phase\").orNull == \"validation\"",
            "providers.gradleProperty(\"codexAgent.target\").orNull != \"node-js-binding\"",
            "check(providers.gradleProperty(\"codexAgent.target\").get() == nodeValidationComponent)",
        ).forEach { assertTrue(it in guard, it) }
        assertTrue("nodeCAbiCatalog.hostTarget(" in source)
        assertTrue("System.getProperty(\"os.name\")" in source)
        assertTrue("System.getProperty(\"os.arch\")" in source)
    }

    @Test
    fun `adapter and native imports retain distinct original versions and exact verifiers`() {
        val adapter = validation.substringAfter("val verifyPackage =")
            .substringBefore("val verifyNativePackage =")
        val native = validation.substringAfter("val verifyNativePackage =")
            .substringBefore("val packagePrerequisite:")
        assertTrue("providers.gradleProperty(\"codexAgent.runtimePackageVersion\")" in adapter)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimeNativePackageVersion\")" in native)
        assertTrue("providers.provider { component }" in adapter)
        assertTrue("providers.provider { nodeValidationComponent }" in native)
        listOf(adapter, native).forEach {
            assertTrue("registerRuntimeOutputVerification(" in it)
            assertTrue("\"package\"" in it)
            assertFalse("runtimeProductVersion" in it)
            assertFalse("orElse" in it)
        }
        val compatibility = validation.substringAfter("val nativePackageCompatibilityVersion =")
            .substringBefore("evidenceTask.configure {")
        assertTrue("if (importedNodeRuntimeNativePackageStage.isPresent)" in compatibility)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimeNativePackageVersion\").map(::runtimeCompatibilityVersion)" in compatibility)
        assertTrue("else {\n        nodeValidationCompatibilityVersion" in compatibility)
        assertTrue("nodeValidationNativePackageRoot.zip(nativePackageCompatibilityVersion)" in validation)
        assertFalse("nodeValidationNativePackageRoot.zip(nodeValidationCompatibilityVersion)" in validation)
        assertTrue("\"validation\",\n        providers.provider { nodeValidationComponent },\n        runtimeProductVersion," in validation)
    }

    @Test
    fun `classifier provider captures immutable classifier rather than Gradle script`() {
        val beforeTask = validation.substringBefore("evidenceTask.configure {")
        val classifier = validation.substringAfter("classifierArchive.set(")
            .substringBefore("compiledNodeTestRuntime.set(")
        assertTrue("val nativePackageClassifier = nodeValidationDistribution.classifier" in beforeTask)
        assertTrue("\$nativePackageClassifier.zip" in classifier)
        assertFalse("nodeValidationDistribution" in classifier)
        assertFalse("project" in classifier)
    }

    @Test
    fun `repeat validation clears only its own host stage and snapshots before recapture`() {
        assertTrue("product-stage/runtime/\$component/validation/\$nodeValidationComponent" in validation)
        assertFalse("\"product-stage/runtime/\$component/validation\"" in validation)
        assertTrue("imported-runtime-package-stages/\$it/\$component/\$nodeValidationComponent" in validation)
        assertTrue("imported-runtime-native-package-stages/\$it/\$component/\$nodeValidationComponent" in validation)
        assertTrue("\"snapshotImported\${title}NativeRuntimePackageStage\"" in validation)
        val invalidator = validation.substringAfter("val invalidate =")
            .substringBefore("val verifyPackage =")
        listOf("phaseRoot,", "importedPackageSnapshotRoot,", "importedNodeNativePackageSnapshotRoot,").forEach {
            assertTrue(it in invalidator, it)
        }
        assertTrue("snapshotImportedPackage.configure { dependsOn(invalidate) }" in invalidator)
        assertTrue("snapshotImportedNodeNativeRuntimePackage.configure { dependsOn(invalidate) }" in invalidator)
        assertFalse("node-js-binding" in invalidator)
        assertFalse("nodeJsBindingValidationRoot" in invalidator)
    }

    @Test
    fun `both imported families retain executors and raw evidence without package producers`() {
        val prerequisites = validation.substringAfter("val packagePrerequisite:")
            .substringBefore("evidenceTask.configure {")
        assertTrue("if (importedNodeRuntimePackageStage.isPresent) {\n        verifyPackage" in prerequisites)
        assertTrue("if (importedNodeRuntimeNativePackageStage.isPresent) {\n        verifyNativePackage" in prerequisites)
        assertTrue("tasks.named<RecordNodeRuntimeEvidenceTask>(" in validation)
        assertTrue("dependsOn(invalidate, packagePrerequisite, nativePackagePrerequisite)" in validation)
        assertTrue("classifierArchive.set(" in validation)
        assertTrue("compiledNodeTestRuntime.set(packageRoot.map" in validation)
        assertTrue("outputs/validation-runner/\$runnerArchiveName" in validation)
        assertTrue("from(evidenceTask.flatMap { it.evidenceFile }) { into(\"node-evidence\") }" in validation)
        assertTrue("from(evidenceTask.flatMap { it.testReport }) { into(\"test-report\") }" in validation)
        assertEquals(2, Regex("^registerNodeRuntimeValidation\\(", RegexOption.MULTILINE).findAll(validation).count())
        assertTrue("\"codex-agent-node-runtime-evidence-runner.zip\"" in validation)
        assertTrue("\"codex-agent-node-wasm-runtime-evidence-runner.zip\"" in validation)
    }
}
