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
                val swiftReceipt = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/swift-parity.json",
                )
                val objectiveCReceipt = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/objective-c-parity.json",
                )
                val javaScriptPreflight = tasks.register<Delete>(
                    "invalidateJavaScriptTypeScriptBindingParityOutput",
                ) {
                    delete(javaScriptReceipt)
                }
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    dependsOn(javaScriptPreflight, "invalidateCodexAgentAppleBindingEvidence")
                    delete(coverage, audit, receipt, javaReceipt)
                }
                val applePreflight = tasks.register<Delete>("invalidateCodexAgentAppleBindingEvidence") {
                    delete(swiftReceipt, objectiveCReceipt)
                }
                tasks.configureEach {
                    if (name !in setOf(preflight.name, javaScriptPreflight.name, applePreflight.name)) {
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
                val appleGate = tasks.register("generateCodexAgentAppleBindingEvidence") {
                    dependsOn(coverageGate, applePreflight)
                    doLast {
                        swiftReceipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected Swift success")
                        }
                        objectiveCReceipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected Objective-C success")
                        }
                    }
                }
                tasks.register("auditCrossLanguageBindingParity") {
                    dependsOn(kotlinGate, javaGate, javaScriptGate, appleGate)
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
            val swiftReceipt = root.staleOutput("reports/cross-language-api/bindings/swift-parity.json")
            val objectiveCReceipt = root.staleOutput(
                "reports/cross-language-api/bindings/objective-c-parity.json",
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
            assertFalse(swiftReceipt.exists())
            assertFalse(objectiveCReceipt.exists())

            val wiring = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
            listOf(
                "reports/cross-language-api/canonical-coverage.json",
                "reports/cross-language-api/binding-obligations-m7_5.json",
                "reports/cross-language-api/bindings/kotlin-parity.json",
                "reports/cross-language-api/bindings/java-parity.json",
                "javascript-typescript-parity.json",
                "swift-parity.json",
                "objective-c-parity.json",
                "rootProject.allprojects",
                "tasks.configureEach",
                "mustRunAfter(invalidateCrossLanguageBindingParityOutputs)",
                "invalidateJavaScriptTypeScriptBindingParityOutput",
                "invalidateCodexAgentAppleBindingEvidence",
                "verifyCrossLanguageApiCoverage.configure",
                "dependsOn(invalidateCrossLanguageBindingParityOutputs)",
                ":codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity",
                ":codex-agent-runtime-ios:generateCodexAgentAppleBindingEvidence",
                "kotlinReceipt.set(verifyKotlinBindingParity.flatMap",
                "javaReceipt.set(verifyJavaBindingParity.flatMap",
                "javaScriptTypeScriptReceipt.set(javaScriptTypeScriptBindingParityReceiptFile)",
                "swiftReceipt.set(swiftBindingParityReceiptFile)",
                "objectiveCReceipt.set(objectiveCBindingParityReceiptFile)",
            ).forEach { contract ->
                assertTrue(contract in wiring, "Missing convention-plugin cleanup contract: $contract")
            }
            val appleWiring = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
            assertTrue("dependsOn(invalidateAppleBindingEvidence)" in appleWiring)
            assertTrue("mustRunAfter(invalidateAppleBindingEvidence)" in appleWiring)
            assertTrue("dependsOn(appleBindingEvidence)" in appleWiring)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `external prerequisite failure cannot outrun aggregate or direct Apple invalidation`() {
        val root = createTempDirectory("binding-cross-project-cleanup").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("""
                rootProject.name = "binding-cross-project-cleanup"
                include(":core", ":ios")
            """.trimIndent())
            root.resolve("build.gradle.kts").writeText("plugins { base }")
            root.resolve("core").mkdir()
            root.resolve("core/build.gradle.kts").writeText("""
                plugins { base }

                val audit = layout.buildDirectory.file(
                    "reports/cross-language-api/binding-obligations-m7_5.json",
                )
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    dependsOn(":ios:invalidateCodexAgentAppleBindingEvidence")
                    shouldRunAfter(":ios:failingIosPrerequisite")
                    delete(audit)
                }
                val invalidationTaskNames = setOf(
                    preflight.name,
                    "invalidateJavaScriptTypeScriptBindingParityOutput",
                    "invalidateCodexAgentAppleBindingEvidence",
                )
                rootProject.allprojects {
                    tasks.configureEach {
                        if (name !in invalidationTaskNames) mustRunAfter(preflight)
                    }
                }
                tasks.register("auditCrossLanguageBindingParity") {
                    dependsOn(preflight, ":ios:generateCodexAgentAppleBindingEvidence")
                    doLast {
                        audit.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected aggregate success")
                        }
                    }
                }
            """.trimIndent())
            root.resolve("ios").mkdir()
            root.resolve("ios/build.gradle.kts").writeText("""
                plugins { base }

                val swift = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/swift-parity.json",
                )
                val objectiveC = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/objective-c-parity.json",
                )
                val aggregate = rootProject.layout.projectDirectory.file(
                    "core/build/reports/cross-language-api/binding-obligations-m7_5.json",
                )
                val preflight = tasks.register<Delete>("invalidateCodexAgentAppleBindingEvidence") {
                    delete(swift, objectiveC)
                }
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                val failing = tasks.register("failingIosPrerequisite") {
                    doLast {
                        check(!swift.get().asFile.exists())
                        check(!objectiveC.get().asFile.exists())
                        check(!aggregate.asFile.exists())
                        throw GradleException("intentional iOS prerequisite failure")
                    }
                }
                tasks.register("generateCodexAgentAppleBindingEvidence") {
                    dependsOn(preflight, failing)
                }
                val failingDirect = tasks.register("failingDirectApplePrerequisite") {
                    doLast {
                        check(!swift.get().asFile.exists())
                        check(!objectiveC.get().asFile.exists())
                        throw GradleException("intentional direct Apple prerequisite failure")
                    }
                }
                preflight.configure {
                    shouldRunAfter(failingDirect)
                }
                tasks.register("directAppleGate") {
                    dependsOn(preflight, failingDirect)
                }
            """.trimIndent())

            val audit = root.staleFile(
                "core/build/reports/cross-language-api/binding-obligations-m7_5.json",
            )
            val swift = root.staleFile(
                "ios/build/reports/cross-language-api/bindings/swift-parity.json",
            )
            val objectiveC = root.staleFile(
                "ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
            )
            val aggregateResult = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(":core:auditCrossLanguageBindingParity", "--parallel", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                aggregateResult.task(":core:invalidateCrossLanguageBindingParityOutputs")?.outcome,
                aggregateResult.output,
            )
            assertEquals(
                TaskOutcome.SUCCESS,
                aggregateResult.task(":ios:invalidateCodexAgentAppleBindingEvidence")?.outcome,
                aggregateResult.output,
            )
            assertEquals(TaskOutcome.FAILED, aggregateResult.task(":ios:failingIosPrerequisite")?.outcome)
            assertTrue("intentional iOS prerequisite failure" in aggregateResult.output)
            assertFalse(audit.exists())
            assertFalse(swift.exists())
            assertFalse(objectiveC.exists())

            swift.apply { parentFile.mkdirs(); writeText("stale Swift success") }
            objectiveC.apply { parentFile.mkdirs(); writeText("stale Objective-C success") }
            val directResult = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(":ios:directAppleGate", "--parallel", "--stacktrace")
                .buildAndFail()
            assertEquals(
                TaskOutcome.SUCCESS,
                directResult.task(":ios:invalidateCodexAgentAppleBindingEvidence")?.outcome,
                directResult.output,
            )
            assertEquals(
                TaskOutcome.FAILED,
                directResult.task(":ios:failingDirectApplePrerequisite")?.outcome,
            )
            assertTrue("intentional direct Apple prerequisite failure" in directResult.output)
            assertFalse(swift.exists())
            assertFalse(objectiveC.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun File.staleOutput(path: String): File = staleFile("build/$path")

    private fun File.staleFile(path: String): File = resolve(path).apply {
        parentFile.mkdirs()
        writeText("stale passed receipt")
    }

}
