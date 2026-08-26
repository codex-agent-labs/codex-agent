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
                val javaReceipt = layout.buildDirectory.file("reports/cross-language-api/bindings/java-parity.json")
                val javaScriptReceipt = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/javascript-typescript-parity.json",
                )
                val javaScriptPreflight = tasks.register<Delete>(
                    "invalidateJavaScriptTypeScriptBindingParityOutput",
                ) {
                    delete(javaScriptReceipt)
                }
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    dependsOn(javaScriptPreflight)
                    delete(coverage, audit, receipt, javaReceipt)
                }
                tasks.configureEach {
                    if (name !in setOf(preflight.name, javaScriptPreflight.name)) {
                        mustRunAfter(preflight)
                    }
                }
                val failingPrerequisite = tasks.register("failingCoveragePrerequisite") {
                    doLast { throw GradleException("intentional coverage prerequisite failure") }
                }
                val coverageGate = tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(preflight, failingPrerequisite)
                    doLast {
                        coverage.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected coverage success")
                        }
                    }
                }
                val kotlinGate = tasks.register("verifyKotlinBindingParity") {
                    dependsOn(coverageGate)
                    doLast {
                        receipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected Kotlin success")
                        }
                    }
                }
                val javaGate = tasks.register("verifyJavaBindingParity") {
                    dependsOn(coverageGate)
                    doLast {
                        javaReceipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected Java success")
                        }
                    }
                }
                val javaScriptGate = tasks.register("verifyJavaScriptTypeScriptBindingParity") {
                    dependsOn(coverageGate)
                    doLast {
                        javaScriptReceipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected JavaScript success")
                        }
                    }
                }
                tasks.register("auditCrossLanguageBindingParity") {
                    dependsOn(kotlinGate, javaGate, javaScriptGate)
                    doLast {
                        audit.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected audit success")
                        }
                    }
                }
            """.trimIndent())
            val coverage = root.staleOutput("reports/cross-language-api/canonical-coverage.json")
            val audit = root.staleOutput("reports/cross-language-api/binding-obligations-m7_5.json")
            val receipt = root.staleOutput("reports/cross-language-api/bindings/kotlin-parity.json")
            val javaReceipt = root.staleOutput("reports/cross-language-api/bindings/java-parity.json")
            val javaScriptReceipt = root.staleOutput(
                "reports/cross-language-api/bindings/javascript-typescript-parity.json",
            )

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments("auditCrossLanguageBindingParity", "--stacktrace")
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
            assertFalse(javaReceipt.exists())
            assertFalse(javaScriptReceipt.exists())

            val wiring = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
            listOf(
                "reports/cross-language-api/canonical-coverage.json",
                "reports/cross-language-api/binding-obligations-m7_5.json",
                "reports/cross-language-api/bindings/kotlin-parity.json",
                "reports/cross-language-api/bindings/java-parity.json",
                "javascript-typescript-parity.json",
                "tasks.configureEach",
                "mustRunAfter(invalidateCrossLanguageBindingParityOutputs)",
                "verifyCrossLanguageApiCoverage.configure",
                "dependsOn(invalidateCrossLanguageBindingParityOutputs)",
                ":codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity",
                "kotlinReceipt.set(verifyKotlinBindingParity.flatMap",
                "javaReceipt.set(verifyJavaBindingParity.flatMap",
                "javaScriptTypeScriptReceipt.set(javaScriptTypeScriptBindingParityReceiptFile)",
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
