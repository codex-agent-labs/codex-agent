import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class CrossLanguageBindingTasksTest {
    @Test
    fun `coverage dependency failure cannot leave stale binding success outputs`() {
        val root = createTempDirectory("binding-task-suppression").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"binding-cleanup-fixture\"")
            root.resolve("build.gradle.kts").writeText("""
                plugins { base }

                val coverage = layout.buildDirectory.file("reports/cross-language-api/canonical-coverage.json")
                val audit = layout.buildDirectory.file("reports/cross-language-api/binding-obligations-m7_5.json")
                val receipt = layout.buildDirectory.file("reports/cross-language-api/bindings/kotlin-parity.json")
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    delete(coverage, audit, receipt)
                }
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                val failingPrerequisite = tasks.register("failingCoveragePrerequisite") {
                    doLast { throw GradleException("intentional coverage prerequisite failure") }
                }
                tasks.register("verifyKotlinBindingParity") {
                    dependsOn(preflight, failingPrerequisite)
                }
            """.trimIndent())
            val coverage = root.staleOutput("reports/cross-language-api/canonical-coverage.json")
            val audit = root.staleOutput("reports/cross-language-api/binding-obligations-m7_5.json")
            val receipt = root.staleOutput("reports/cross-language-api/bindings/kotlin-parity.json")

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments("verifyKotlinBindingParity", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":invalidateCrossLanguageBindingParityOutputs")?.outcome,
                result.output,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":failingCoveragePrerequisite")?.outcome)
            assertTrue("intentional coverage prerequisite failure" in result.output)
            assertFalse(coverage.exists())
            assertFalse(audit.exists())
            assertFalse(receipt.exists())

            val wiring = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
            listOf(
                "reports/cross-language-api/canonical-coverage.json",
                "reports/cross-language-api/binding-obligations-m7_5.json",
                "reports/cross-language-api/bindings/kotlin-parity.json",
                "tasks.configureEach",
                "mustRunAfter(invalidateCrossLanguageBindingParityOutputs)",
                "verifyCrossLanguageApiCoverage.configure",
                "dependsOn(invalidateCrossLanguageBindingParityOutputs)",
            ).forEach { contract ->
                assertTrue(contract in wiring, "Missing convention-plugin cleanup contract: $contract")
            }
        } finally {
            root.deleteRecursively()
        }
    }

    private fun File.staleOutput(path: String): File = resolve("build/$path").apply {
        parentFile.mkdirs()
        writeText("stale passed receipt")
    }

}
