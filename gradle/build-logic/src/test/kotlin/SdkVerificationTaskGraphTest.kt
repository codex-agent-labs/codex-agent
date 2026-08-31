import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class SdkVerificationTaskGraphTest {
    @Test
    fun `missing imported evidence deletes stale success before input validation fails`() {
        withFixture { root, report ->
            report.parentFile.mkdirs()
            report.writeText("stale passed report\n")

            val result = runner(root, "verifySdk").buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":invalidateImportedSdkBindingParityOutput")?.outcome,
                result.output,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":verifyImportedSdkBindingParity")?.outcome)
            assertFalse(report.exists())
            assertTrue("evidenceDirectory" in result.output)
        }
    }

    @Test
    fun `failed imported evidence suppresses SDK gates across continue cache reuse and abbreviation`() {
        withFixture { root, report ->
            report.parentFile.mkdirs()
            report.writeText("stale passed report\n")

            val primed = runner(root, "verifySdk").buildAndFail()
            assertEquals(TaskOutcome.FAILED, primed.task(":verifyImportedSdkBindingParity")?.outcome)
            assertFalse(report.exists())
            report.writeText("stale passed report\n")

            val reused = runner(root, "verifySdk", "--continue", "--parallel").buildAndFail()
            assertTrue("Reusing configuration cache." in reused.output, reused.output)
            assertEquals(
                TaskOutcome.SUCCESS,
                reused.task(":invalidateImportedSdkBindingParityOutput")?.outcome,
            )
            assertEquals(TaskOutcome.FAILED, reused.task(":verifyImportedSdkBindingParity")?.outcome)
            for (task in listOf(
                "verifySdkFacadePublicationMetadata",
                "verifySdkFacadeConsumers",
                "verifySdk",
            )) {
                assertFalse(reused.task(":$task")?.outcome == TaskOutcome.SUCCESS, task)
            }
            assertFalse(report.exists())
            report.writeText("stale passed report\n")

            val abbreviated = runner(root, "vS", "--continue").buildAndFail()
            assertEquals(
                TaskOutcome.SUCCESS,
                abbreviated.task(":invalidateImportedSdkBindingParityOutput")?.outcome,
            )
            assertEquals(TaskOutcome.FAILED, abbreviated.task(":verifyImportedSdkBindingParity")?.outcome)
            assertFalse(report.exists())
        }
    }

    @Test
    fun `production wiring requires imported evidence and runs it before SDK consumers`() {
        val source = File("src/main/kotlin/codexagent.root-release.gradle.kts").readText()
        val wiring = source.substringAfter("val importedSdkBindingEvidence =")
            .substringBefore("fun publicationTask")

        assertTrue("providers.gradleProperty(SDK_BINDING_EVIDENCE_DIRECTORY_PROPERTY)" in wiring)
        assertTrue("sdkFacadeProject.tasks.register<Delete>(" in wiring)
        assertTrue("\"invalidateImportedSdkBindingParityOutput\"" in wiring)
        assertTrue("rootProject.tasks.matching { it.name == \"prepareContractInputs\" }" in wiring)
        assertTrue("mustRunAfter(invalidateImportedSdkBindingParityOutput)" in wiring)
        assertTrue("dependsOn(invalidateImportedSdkBindingParityOutput," in wiring)
        assertTrue("\":codex-agent-core:verifyCrossLanguageApiCoverage\"" in wiring)
        assertTrue("canonicalApiReport.set(" in wiring)
        assertTrue("canonicalCoverageReceipt.set(" in wiring)
        assertTrue(
            "verifySdkFacadePublicationMetadata.configure { dependsOn(verifyImportedSdkBindingParity) }" in
                wiring,
        )
        assertTrue(
            "verifySdkFacadeConsumers.configure { dependsOn(verifyImportedSdkBindingParity) }" in wiring,
        )
        assertFalse("gradle.startParameter" in wiring)
        assertFalse("SDK verification rejects --continue" in wiring)

        val verifySdk = wiring.substringAfter("tasks.register(\"verifySdk\")")
        assertTrue("verifyImportedSdkBindingParity" in verifySdk)
        assertTrue("verifySdkFacadePublicationMetadata" in verifySdk)
        assertTrue("verifySdkFacadeConsumers" in verifySdk)

        for (optional in listOf("onlyIf", ".orElse(", ".orNull", ".isPresent", "no-op", "noop")) {
            assertFalse(optional in wiring, optional)
        }
    }

    @Test
    fun `SDK owns Java parity while Contract verification has no downstream language edge`() {
        val sdkSource = File("src/main/kotlin/codexagent.root-release.gradle.kts").readText()
        val contractSource = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()

        listOf(
            "project(\":codex-agent-core\")",
            "project(\":codex-agent-sdk\")",
            "\"invalidateJavaBindingParityOutput\"",
            "sdkFacadeProject.tasks.register<Delete>(",
            "sdkCoreProject.tasks.register<VerifyJavaBindingParityTask>(\"verifyJavaBindingParity\")",
            "reports/cross-language-api/bindings/java-parity.json",
            ":codex-agent-core:verifyCrossLanguageApiCoverage",
            ":codex-agent-core:jvmJar",
            ":codex-agent-core:bundleAndroidMainAar",
            ":codex-agent-runtime-desktop:jvmJar",
            ":codex-agent-runtime-android:bundleReleaseAar",
        ).forEach { contract ->
            assertTrue(contract in sdkSource, "Missing SDK-owned Java contract: $contract")
        }
        listOf(
            "VerifyJavaBindingParityTask",
            "verifyJavaBindingParity",
            "java-parity.json",
            "codex-agent-runtime-desktop",
            "codex-agent-runtime-android",
            "verifyJavaScriptTypeScriptBindingParity",
            "invalidateCodexAgentAppleBindingEvidence",
            "invalidateCodexAgentCAbiBootstrapEvidence",
        ).forEach { forbidden ->
            assertFalse(forbidden in contractSource, "Contract still owns downstream surface: $forbidden")
        }
        val coreCheck = contractSource.substringAfter("afterEvaluate {")
        assertTrue("tasks.named(\"check\").configure" in coreCheck)
        assertTrue("setDependsOn(listOf(" in coreCheck)
        assertTrue("verifyProtocolSource" in coreCheck)
        assertTrue("verifyKotlinBindingParity" in coreCheck)
        val verifySdk = sdkSource.substringAfter("tasks.register(\"verifySdk\")")
            .substringBefore("fun publicationTask")
        assertTrue("verifyImportedSdkBindingParity" in verifySdk)
        assertFalse("verifyJavaBindingParity" in verifySdk)
    }

    private fun withFixture(block: (File, File) -> Unit) {
        val root = createTempDirectory("sdk-verification-task-graph").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"sdk-verification-task-graph\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                plugins { id("codexagent.codex-runtime") }

                val evidenceProperty = "codexAgent.sdkBindingEvidenceDirectory"
                val report = layout.buildDirectory.file("reports/sdk/imported-binding-parity.json")
                val preflight = tasks.register<Delete>("invalidateImportedSdkBindingParityOutput") {
                    delete(report)
                }
                val importedEvidence = layout.dir(providers.gradleProperty(evidenceProperty).map(::file))
                val verifyImportedEvidence = tasks.register<VerifyImportedSdkBindingParityTask>(
                    "verifyImportedSdkBindingParity",
                ) {
                    dependsOn(preflight)
                    evidenceDirectory.set(importedEvidence)
                    resultFile.set(report)
                }
                val verifySdkFacadePublicationMetadata = tasks.register("verifySdkFacadePublicationMetadata") {
                    dependsOn(verifyImportedEvidence)
                }
                val verifySdkFacadeConsumers = tasks.register("verifySdkFacadeConsumers") {
                    dependsOn(verifyImportedEvidence)
                }
                tasks.register("verifySdk") {
                    dependsOn(
                        verifyImportedEvidence,
                        verifySdkFacadePublicationMetadata,
                        verifySdkFacadeConsumers,
                    )
                }
                """.trimIndent() + "\n",
            )
            block(root, root.resolve("build/reports/sdk/imported-binding-parity.json"))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun runner(root: File, vararg tasks: String) = GradleRunner.create()
        .withProjectDir(root)
        .withPluginClasspath()
        .withArguments(
            *tasks,
            "--configuration-cache",
            "--configuration-cache-problems=fail",
            "--console=plain",
            "--stacktrace",
        )
}
