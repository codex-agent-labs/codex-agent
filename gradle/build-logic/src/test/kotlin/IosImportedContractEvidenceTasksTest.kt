import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.Task
import org.gradle.api.tasks.Delete
import org.gradle.testfixtures.ProjectBuilder

/** Registration and artifact graph checks, not Apple compiler or Contract admission evidence. */
class IosImportedContractEvidenceTasksTest {
    @Test
    fun `imported evidence snapshots exact original Contract identity behind its invalidator`() = fixture { project ->
        val original = project.layout.projectDirectory.dir("original-contract")
        val invalidate = project.tasks.register("invalidateAppleEvidence", Delete::class.java)
        val imported = project.registerIosImportedContractEvidenceTasks(
            project.providers.provider { original },
            project.providers.provider { "0.2.3" },
            project.providers.provider { "a".repeat(40) },
            invalidate,
        )
        val verifier = imported.verify.get()
        assertEquals(listOf("contract", "contract", "binary", "common", "0.2.3"), listOf(
            verifier.product.get(), verifier.component.get(), verifier.phase.get(),
            verifier.target.get(), verifier.productVersion.get(),
        ))
        val root = project.layout.buildDirectory.dir(
            "imported-apple-contract-evidence/${"a".repeat(40)}/contract",
        ).get().asFile
        assertEquals(root, verifier.stageRoot.get().asFile)
        assertEquals(root.resolve("outputs/evidence/canonical-api.json"), imported.canonicalApi.get().asFile)
        assertEquals(root.resolve("outputs/evidence/canonical-coverage.json"), imported.canonicalCoverage.get().asFile)
        val snapshot = project.tasks.named(
            "snapshotImportedAppleContractEvidence", SnapshotImportedProductStageTask::class.java,
        ).get()
        assertEquals(original.asFile, snapshot.sourceDirectory.get().asFile)
        assertEquals(root, snapshot.outputDirectory.get().asFile)
        val reset = project.tasks.named("resetImportedAppleContractEvidence", Delete::class.java).get()
        assertEquals(setOf(root), reset.targetFiles.files)
        assertFalse(original.asFile in reset.targetFiles.files)
        assertEquals(setOf(
            "verifyImportedAppleContractEvidence", "snapshotImportedAppleContractEvidence",
            "resetImportedAppleContractEvidence", "invalidateAppleEvidence",
        ), taskClosure(verifier).map { it.name }.toSet())
    }

    @Test
    fun `missing imports invalid versions and unsafe snapshot identities fail before registration`() {
        listOf("source", "version", "tree").forEach { invalid -> fixture { project ->
            val source = project.objects.directoryProperty()
            if (invalid != "source") source.set(project.layout.projectDirectory.dir("original-contract"))
            val error = assertFailsWith<IllegalStateException> {
                project.registerIosImportedContractEvidenceTasks(
                    source,
                    project.providers.provider { if (invalid == "version") "not-semver" else "0.2.3" },
                    project.providers.provider { if (invalid == "tree") "../../original-contract" else "a".repeat(40) },
                    project.tasks.register("invalidateAppleEvidence", Delete::class.java),
                )
            }
            assertTrue("Imported Apple evidence requires" in error.message.orEmpty())
            assertFalse("snapshotImportedAppleContractEvidence" in project.tasks.names)
            assertFalse("verifyImportedAppleContractEvidence" in project.tasks.names)
        } }
    }

    @Test
    fun `imported branch removes core producers from both existing Apple evidence tasks`() {
        val source = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
        val imported = source.substringAfter("verifiedDistributionTasks.importedXCFramework?.let")
            .substringBefore("tasks.register(\"verifyIosRuntime\")")
        assertTrue("registerIosImportedContractEvidenceTasks(" in imported)
        assertTrue("providers.gradleProperty(\"codexAgent.contractBinaryStage\")" in imported)
        assertTrue("providers.gradleProperty(\"codexAgent.contractVersion\")" in imported)
        assertFalse(":codex-agent-core:" in imported)
        assertFalse("core/build" in imported)
        assertFalse("prepareCodexAgentReleaseXCFramework" in imported)
        listOf("appleCompilerEvidence.configure {", "appleBindingEvidence.configure {").forEach { marker ->
            val task = imported.substringAfter(marker).substringBefore("\n    }")
            assertTrue("setDependsOn(listOf(" in task, marker)
            assertTrue("contractEvidence.verify," in task, marker)
            assertTrue("canonicalApiReport.set(contractEvidence.canonicalApi)" in task, marker)
            assertTrue("canonicalCoverageReceipt.set(contractEvidence.canonicalCoverage)" in task, marker)
            assertTrue("xcframeworkDirectory.set(imported.flatMap" in task, marker)
        }
        assertTrue("verifyAppleToolchain," in imported)
        assertTrue("appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests," in imported)
        assertTrue("delete(appleCompilerEvidenceFile)" in imported)
        assertTrue(":codex-agent-core:verifyCrossLanguageApiCoverage" in source.substringBefore(
            "verifiedDistributionTasks.importedXCFramework?.let",
        ))
        // Existing semantic task implementations and output receipt types are unchanged.
        assertTrue("tasks.register<AppleCompilerEvidenceTask>" in source)
        assertTrue("tasks.register<GenerateAppleBindingEvidenceTask>" in source)
        assertTrue("swiftReceiptFile.set(swiftBindingReceiptFile)" in source)
        assertTrue("objectiveCReceiptFile.set(objectiveCBindingReceiptFile)" in source)
    }

    private fun taskClosure(task: Task): Set<Task> = setOf(task) +
        task.taskDependencies.getDependencies(task).flatMap(::taskClosure)

    private fun fixture(block: (Project) -> Unit) {
        val root = createTempDirectory("ios-imported-contract-evidence").toFile().canonicalFile
        try {
            block(ProjectBuilder.builder().withProjectDir(root).build())
        } finally {
            root.deleteRecursively()
        }
    }
}
