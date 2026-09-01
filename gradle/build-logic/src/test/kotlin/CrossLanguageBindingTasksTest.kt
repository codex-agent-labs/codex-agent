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
                val canonicalPreflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    delete(coverage, receipt)
                }
                val javaPreflight = tasks.register<Delete>("invalidateJavaBindingParityOutput") {
                    delete(javaReceipt)
                }
                val javaScriptPreflight = tasks.register<Delete>(
                    "invalidateJavaScriptTypeScriptBindingParityOutput",
                ) {
                    delete(javaScriptReceipt)
                }
                val applePreflight = tasks.register<Delete>("invalidateCodexAgentAppleBindingEvidence") {
                    delete(swiftReceipt, objectiveCReceipt)
                }
                val preflights = setOf(
                    canonicalPreflight.name,
                    javaPreflight.name,
                    javaScriptPreflight.name,
                    applePreflight.name,
                )
                tasks.configureEach {
                    if (name !in preflights) {
                        mustRunAfter(canonicalPreflight, javaPreflight, javaScriptPreflight, applePreflight)
                    }
                }
                val failingPrerequisite = tasks.register("failingCoveragePrerequisite") {
                    doLast { throw GradleException("intentional coverage prerequisite failure") }
                }
                val coverageGate = tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(canonicalPreflight, failingPrerequisite)
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
                    dependsOn(javaPreflight, coverageGate)
                    doLast {
                        javaReceipt.get().asFile.apply {
                            parentFile.mkdirs()
                            writeText("unexpected Java success")
                        }
                    }
                }
                val javaScriptGate = tasks.register("verifyJavaScriptTypeScriptBindingParity") {
                    dependsOn(javaScriptPreflight, coverageGate)
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
                }
            """.trimIndent())
            val coverage = root.staleOutput("reports/cross-language-api/canonical-coverage.json")
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
            assertEquals(TaskOutcome.SUCCESS, result.task(":invalidateJavaBindingParityOutput")?.outcome)
            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":invalidateJavaScriptTypeScriptBindingParityOutput")?.outcome,
            )
            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":invalidateCodexAgentAppleBindingEvidence")?.outcome,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":failingCoveragePrerequisite")?.outcome)
            assertTrue("intentional coverage prerequisite failure" in result.output)
            assertFalse(coverage.exists())
            assertFalse(receipt.exists())
            assertFalse(javaReceipt.exists())
            assertFalse(javaScriptReceipt.exists())
            assertFalse(swiftReceipt.exists())
            assertFalse(objectiveCReceipt.exists())

            val coreWiring = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
            listOf(
                "reports/cross-language-api/canonical-coverage.json",
                "reports/cross-language-api/bindings/kotlin-parity.json",
                "tasks.configureEach",
                "mustRunAfter(invalidateCrossLanguageBindingParityOutputs)",
                "verifyCrossLanguageApiCoverage.configure",
                "dependsOn(invalidateCrossLanguageBindingParityOutputs)",
            ).forEach { contract ->
                assertTrue(contract in coreWiring, "Missing Contract cleanup contract: $contract")
            }
            listOf(
                "java-parity.json",
                "invalidateJavaScriptTypeScriptBindingParityOutput",
                "invalidateCodexAgentAppleBindingEvidence",
                "invalidateCodexAgentCAbiBootstrapEvidence",
            ).forEach { forbidden -> assertFalse(forbidden in coreWiring, forbidden) }
            val sdkWiring = File("src/main/kotlin/codexagent.root-release.gradle.kts").readText()
            assertTrue("\"invalidateJavaBindingParityOutput\"" in sdkWiring)
            assertTrue("sdkFacadeProject.tasks.register<Delete>(" in sdkWiring)
            assertTrue("dependsOn(\n        invalidateJavaBindingParityOutput," in sdkWiring)
            assertFalse("\"prepareContractInputs\"," in sdkWiring)
            val javaScriptWiring = File("src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText()
            assertTrue("rootProject.tasks.matching { it.name == \"prepareContractInputs\" }" in javaScriptWiring)
            assertTrue("mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)" in javaScriptWiring)
            val appleWiring = File("src/main/kotlin/codexagent.ios-runtime.gradle.kts").readText()
            assertTrue("dependsOn(invalidateAppleBindingEvidence)" in appleWiring)
            assertTrue("mustRunAfter(invalidateAppleBindingEvidence)" in appleWiring)
            assertTrue("rootProject.tasks.matching { it.name == \"prepareContractInputs\" }" in appleWiring)
            assertTrue("dependsOn(appleBindingEvidence)" in appleWiring)
            val cAbiWiring = File(
                "../../runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
            ).readText()
            assertTrue("providers.gradleProperty(\"codexAgent.contractManifest\")" in cAbiWiring)
            assertTrue("mustRunAfter(invalidateCAbiBootstrapEvidence)" in cAbiWiring)
            assertFalse("prepareContractInputs" in cAbiWiring)
            assertFalse(":codex-agent-core" in cAbiWiring)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `Contract preparation failure cannot outrun SDK parity preflights`() {
        val root = createTempDirectory("binding-contract-preflight").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText(
                """
                rootProject.name = "binding-contract-preflight"
                include(":core", ":sdk", ":js", ":ios")
                """.trimIndent(),
            )
            root.resolve("build.gradle.kts").writeText(
                """
                plugins { base }

                tasks.register("prepareContractInputs") {
                    doLast { throw GradleException("intentional Contract preparation failure") }
                }
                tasks.register("auditSdkParity") {
                    dependsOn(
                        ":core:verifyJavaBindingParity",
                        "verifyImportedSdkBindingParity",
                        ":js:verifyJavaScriptTypeScriptBindingParity",
                        ":ios:generateCodexAgentAppleBindingEvidence",
                    )
                }
                val importedReceipt = layout.buildDirectory.file(
                    "reports/sdk/imported-binding-parity.json",
                )
                val importedPreflight = project(":sdk").tasks.register<Delete>(
                    "invalidateImportedSdkBindingParityOutput",
                ) {
                    delete(importedReceipt)
                }
                tasks.named("prepareContractInputs").configure {
                    mustRunAfter(importedPreflight)
                }
                tasks.register("verifyImportedSdkBindingParity") {
                    dependsOn(importedPreflight, ":core:verifyCrossLanguageApiCoverage")
                }
                """.trimIndent(),
            )
            root.resolve("core").mkdir()
            root.resolve("core/build.gradle.kts").writeText(
                """
                plugins { base }

                val canonicalPreflight = tasks.register<Delete>(
                    "invalidateCrossLanguageBindingParityOutputs",
                )
                canonicalPreflight.configure { dependsOn(":prepareContractInputs") }
                val coverage = tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(canonicalPreflight)
                }
                tasks.register("verifyJavaBindingParity") {
                    dependsOn(":sdk:invalidateJavaBindingParityOutput", coverage)
                }
                """.trimIndent(),
            )
            val families = listOf(
                Triple("sdk", "invalidateJavaBindingParityOutput", "java-parity.json"),
                Triple(
                    "js",
                    "invalidateJavaScriptTypeScriptBindingParityOutput",
                    "javascript-typescript-parity.json",
                ),
                Triple("ios", "invalidateCodexAgentAppleBindingEvidence", "swift-parity.json"),
            )
            val producerNames = mapOf(
                "js" to "verifyJavaScriptTypeScriptBindingParity",
                "ios" to "generateCodexAgentAppleBindingEvidence",
            )
            families.forEach { (projectName, preflightName, receiptName) ->
                root.resolve(projectName).mkdir()
                val producer = producerNames[projectName]
                root.resolve("$projectName/build.gradle.kts").writeText(
                    """
                    plugins { base }

                    val receipt = project(":core").layout.buildDirectory.file(
                        "reports/cross-language-api/bindings/$receiptName",
                    )
                    val preflight = tasks.register<Delete>("$preflightName") {
                        delete(receipt)
                    }
                    rootProject.tasks.named("prepareContractInputs").configure {
                        mustRunAfter(preflight)
                    }
                    ${if (producer == null) "" else """
                    tasks.register("$producer") {
                        dependsOn(preflight, ":core:verifyCrossLanguageApiCoverage")
                    }
                    """.trimIndent()}
                    """.trimIndent(),
                )
            }
            val receipts = families.map { (_, _, receiptName) ->
                root.staleFile("core/build/reports/cross-language-api/bindings/$receiptName")
            } + root.staleFile("build/reports/sdk/imported-binding-parity.json")
            val arguments = listOf(
                "auditSdkParity",
                "--continue",
                "--parallel",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            )
            fun runFailure() = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(arguments)
                .buildAndFail()

            val first = runFailure()
            assertTrue("intentional Contract preparation failure" in first.output)
            families.forEach { (projectName, preflightName, _) ->
                assertEquals(
                    TaskOutcome.SUCCESS,
                    first.task(":$projectName:$preflightName")?.outcome,
                    first.output,
                )
            }
            assertEquals(
                TaskOutcome.SUCCESS,
                first.task(":sdk:invalidateImportedSdkBindingParityOutput")?.outcome,
                first.output,
            )
            assertEquals(TaskOutcome.FAILED, first.task(":prepareContractInputs")?.outcome)
            receipts.forEach { assertFalse(it.exists(), it.path) }

            receipts.forEach { it.apply { parentFile.mkdirs(); writeText("stale passed receipt") } }
            val reused = runFailure()
            assertTrue("Configuration cache entry reused." in reused.output, reused.output)
            families.forEach { (projectName, preflightName, _) ->
                assertEquals(
                    TaskOutcome.SUCCESS,
                    reused.task(":$projectName:$preflightName")?.outcome,
                    reused.output,
                )
            }
            assertEquals(
                TaskOutcome.SUCCESS,
                reused.task(":sdk:invalidateImportedSdkBindingParityOutput")?.outcome,
                reused.output,
            )
            assertEquals(TaskOutcome.FAILED, reused.task(":prepareContractInputs")?.outcome)
            receipts.forEach { assertFalse(it.exists(), it.path) }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `external prerequisite failure cannot outrun Apple invalidation without a Core reverse edge`() {
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

                val coverage = layout.buildDirectory.file(
                    "reports/cross-language-api/canonical-coverage.json",
                )
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs") {
                    delete(coverage)
                }
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                val failing = tasks.register("failingCanonicalPrerequisite") {
                    doLast {
                        check(!coverage.get().asFile.exists())
                        throw GradleException("intentional canonical prerequisite failure")
                    }
                }
                tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(preflight, failing)
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
                val preflight = tasks.register<Delete>("invalidateCodexAgentAppleBindingEvidence") {
                    delete(swift, objectiveC)
                }
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                project(":core").tasks.matching {
                    it.name == "invalidateCrossLanguageBindingParityOutputs"
                }.configureEach {
                    mustRunAfter(preflight)
                }
                tasks.register("generateCodexAgentAppleBindingEvidence") {
                    dependsOn(preflight, ":core:verifyCrossLanguageApiCoverage")
                }
                val failingDirect = tasks.register("failingDirectApplePrerequisite") {
                    doLast {
                        check(!swift.get().asFile.exists())
                        check(!objectiveC.get().asFile.exists())
                        throw GradleException("intentional direct Apple prerequisite failure")
                    }
                }
                tasks.register("directAppleGate") {
                    dependsOn(preflight, failingDirect)
                }
            """.trimIndent())

            val coverage = root.staleFile(
                "core/build/reports/cross-language-api/canonical-coverage.json",
            )
            val swift = root.staleFile(
                "ios/build/reports/cross-language-api/bindings/swift-parity.json",
            )
            val objectiveC = root.staleFile(
                "ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
            )
            val forwardResult = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(
                    ":ios:generateCodexAgentAppleBindingEvidence",
                    "--parallel",
                    "--stacktrace",
                )
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                forwardResult.task(":core:invalidateCrossLanguageBindingParityOutputs")?.outcome,
                forwardResult.output,
            )
            assertEquals(
                TaskOutcome.SUCCESS,
                forwardResult.task(":ios:invalidateCodexAgentAppleBindingEvidence")?.outcome,
                forwardResult.output,
            )
            assertEquals(
                TaskOutcome.FAILED,
                forwardResult.task(":core:failingCanonicalPrerequisite")?.outcome,
            )
            assertTrue("intentional canonical prerequisite failure" in forwardResult.output)
            assertFalse(coverage.exists())
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
