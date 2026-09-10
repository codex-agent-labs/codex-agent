import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Task/provider graph checks only; synthetic paths are not Apple semantic or host evidence. */
class AppleCanonicalPackageGraphTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }

    @Test
    fun `canonical sdk ios package selects the caller-bound Apple graph and exact product root`() {
        withInputs { inputs ->
            val inspection = inputs.root.resolve("graph.gradle").apply {
                writeText(
                    """
                    gradle.projectsEvaluated {
                        def sdk = gradle.rootProject.findProject(':codex-agent-sdk')
                        if (sdk == null) return
                        def ios = gradle.rootProject.findProject(':codex-agent-runtime-ios')
                        if (ios == null) throw new GradleException('Canonical Apple graph has no iOS project')
                        def manifest = sdk.tasks.named('writeSdkIosPackageOutputManifest').get()
                        def stage = ios.tasks.named('stageImportedCodexAgentIosSdkPackageArtifacts').get()
                        def verifier = ios.tasks.named('verifyTransportedCodexAgentIosSdkPackageClosure').get()
                        println('CODEX_APPLE_ROOTS=' + manifest.outputRoots.get().collect {
                            key, value -> key + '=' + value
                        }.sort().join(','))
                        println('CODEX_APPLE_STAGE=' + stage.outputDirectory.get().asFile.canonicalPath)
                        println('CODEX_APPLE_VALIDATION=' +
                            stage.validationEvidenceDirectory.get().asFile.canonicalPath)
                        println('CODEX_APPLE_STAGE_WORK=' + stage.workDirectory.get().asFile.canonicalPath)
                        println('CODEX_APPLE_VERIFY_WORK=' + verifier.workDirectory.get().asFile.canonicalPath)
                        println('CODEX_APPLE_EXPECTED=' +
                            verifier.expectedSdkCompatibility.get().asFile.canonicalPath + '|' +
                            verifier.expectedDistributionProof.get().asFile.canonicalPath)
                        println('CODEX_APPLE_DIRECT_DEPENDENCIES=' +
                            manifest.taskDependencies.getDependencies(manifest)*.path.sort().join(','))
                    }
                    """.trimIndent() + "\n",
                )
            }
            val result = runner(inputs, inspection, expectedCompatibility = true, expectedProof = true).build()
            val selected = result.output.lineSequence()
                .filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                .map { it.removeSuffix(" SKIPPED") }
                .toSet()
            listOf(
                ":codex-agent-sdk:invalidateSdkIosPackagePhase",
                ":codex-agent-runtime-ios:validateImportedCodexAgentIosVerifiedDistribution",
                ":codex-agent-runtime-ios:stageImportedCodexAgentIosSdkPackageArtifacts",
                ":codex-agent-runtime-ios:verifyTransportedCodexAgentIosSdkPackageClosure",
                ":codex-agent-sdk:stageSdkIosPackagePhase",
                ":codex-agent-sdk:stageSdkIosPackageEvidence",
                ":codex-agent-sdk:writeSdkIosPackageOutputManifest",
            ).forEach { assertTrue(it in selected, result.output) }
            assertFalse(selected.any {
                it.substringAfterLast(':').startsWith("compile") ||
                    it.substringAfterLast(':').startsWith("link")
            }, result.output)

            assertEquals(
                "CODEX_APPLE_ROOTS=apple=outputs/apple,evidence=outputs/evidence,maven=outputs/maven",
                outputLine(result.output, "CODEX_APPLE_ROOTS="),
            )
            val canonicalStage = repository.resolve(
                "codex-agent-sdk/build/product-stage/sdk/sdk-ios/package",
            ).canonicalFile
            assertEquals(
                canonicalStage.resolve("outputs/apple").path,
                outputLine(result.output, "CODEX_APPLE_STAGE=").substringAfter('='),
            )
            listOf("CODEX_APPLE_VALIDATION=", "CODEX_APPLE_STAGE_WORK=", "CODEX_APPLE_VERIFY_WORK=")
                .forEach { prefix ->
                    val path = File(outputLine(result.output, prefix).substringAfter('=')).canonicalFile
                    assertFalse(path.toPath().startsWith(canonicalStage.toPath()), "$prefix$path")
                }
            assertEquals(
                "CODEX_APPLE_EXPECTED=${inputs.expectedCompatibility.path}|${inputs.expectedProof.path}",
                outputLine(result.output, "CODEX_APPLE_EXPECTED="),
            )
            assertTrue(
                ":codex-agent-runtime-ios:verifyTransportedCodexAgentIosSdkPackageClosure" in
                    outputLine(result.output, "CODEX_APPLE_DIRECT_DEPENDENCIES="),
                result.output,
            )
        }
    }

    @Test
    fun `canonical sdk ios package requires both caller expectations`() {
        withInputs { inputs ->
            listOf(false to false, true to false).forEach { (compatibility, proof) ->
                val result = runner(inputs, null, compatibility, proof).buildAndFail()
                assertTrue(
                    "requires imported Apple artifacts and caller expectations" in result.output ||
                        "caller expectations must be supplied together" in result.output,
                    result.output,
                )
                assertFalse(result.tasks.any { !it.path.startsWith(":build-logic:") }, result.output)
            }
        }
    }

    @Test
    fun `core and Android package tasks configure without an ios project`() {
        val root = createTempDirectory("sdk-package-without-ios-").toFile().canonicalFile
        try {
            root.resolve("settings.gradle").writeText("rootProject.name = 'sdk-package-without-ios'\n")
            root.resolve("build.gradle").writeText(
                """
                plugins {
                    id 'codexagent.native-wrapper-sdk' apply false
                }
                group = 'io.github.codex-agent-labs'
                version = '0.2.0'
                rootProject.ext.set('codexAgent.sdkDefaultRuntimeVersion', '0.2.6')
                rootProject.ext.set('codexAgent.sdkVersion', '0.2.0')
                apply plugin: 'codexagent.native-wrapper-sdk'
                tasks.register('inspectSdkPackageTasks') {
                    doLast {
                        assert gradle.rootProject.allprojects*.path == [':']
                        assert tasks.findByName('writeSdkCorePackageOutputManifest') != null
                        assert tasks.findByName('writeSdkAndroidPackageOutputManifest') != null
                    }
                }
                """.trimIndent() + "\n",
            )
            GradleRunner.create()
                .withProjectDir(root)
                .withPluginClasspath()
                .withArguments("inspectSdkPackageTasks", "--offline", "--no-configuration-cache", "--console=plain")
                .build()
        } finally {
            root.deleteRecursively()
        }
    }

    private fun runner(
        inputs: Inputs,
        inspection: File?,
        expectedCompatibility: Boolean,
        expectedProof: Boolean,
    ): GradleRunner {
        val arguments = mutableListOf(
            "ciProductPhase", "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
            "-PcodexAgent.product=sdk", "-PcodexAgent.component=sdk-ios", "-PcodexAgent.phase=package",
            "-PcodexAgent.candidateCommit=${"1".repeat(40)}",
            "-PcodexAgent.candidateTree=${"2".repeat(40)}",
            "-PcodexAgent.contractBinaryStage=${inputs.contractStage.path}",
            "-PcodexAgent.contractVersion=0.2.0",
            "-PcodexAgent.iosNativeEvidenceDirectory=${inputs.nativeEvidence.path}",
            "-PcodexAgent.iosVerifiedDistributionDirectory=${inputs.distribution.path}",
            "-PcodexAgent.sdkCompatibilityRequest=${inputs.compatibilityRequest.path}",
            "-PcodexAgent.sdkIosBinaryStageRoot=${inputs.binaryStage.path}",
        )
        if (expectedCompatibility) {
            arguments += "-PcodexAgent.iosExpectedSdkCompatibility=${inputs.expectedCompatibility.path}"
        }
        if (expectedProof) arguments += "-PcodexAgent.iosExpectedDistributionProof=${inputs.expectedProof.path}"
        if (inspection != null) arguments += listOf("--init-script", inspection.path)
        return GradleRunner.create().withProjectDir(repository).withArguments(arguments)
    }

    private fun outputLine(output: String, prefix: String): String = output.lineSequence().single {
        it.startsWith(prefix)
    }

    private fun withInputs(block: (Inputs) -> Unit) {
        val root = createTempDirectory("apple-canonical-package-graph-").toFile().canonicalFile
        try {
            fun directory(name: String) = root.resolve(name).apply { mkdirs() }
            fun file(name: String) = root.resolve(name).apply {
                parentFile.mkdirs()
                writeText("synthetic graph input\n")
            }
            block(
                Inputs(
                    root,
                    directory("contract-stage"),
                    directory("native-evidence"),
                    directory("verified-distribution"),
                    directory("binary-stage"),
                    file("compatibility-request.json"),
                    file("expected/sdk-compatibility.json"),
                    file("expected/verified-distribution-proof.json"),
                ),
            )
        } finally {
            root.deleteRecursively()
        }
    }

    private data class Inputs(
        val root: File,
        val contractStage: File,
        val nativeEvidence: File,
        val distribution: File,
        val binaryStage: File,
        val compatibilityRequest: File,
        val expectedCompatibility: File,
        val expectedProof: File,
    )
}
