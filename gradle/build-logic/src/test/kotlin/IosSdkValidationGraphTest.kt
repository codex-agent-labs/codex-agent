import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Real plugin dry-run only: placeholder inputs grant no artifact, compiler, XCTest or host acceptance. */
class IosSdkValidationGraphTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }

    @Test
    fun `validation consumes private original package and Contract snapshots without product producers`() {
        val root = createTempDirectory("ios-sdk-validation-graph-").toFile().canonicalFile
        try {
            val originalPackage = root.resolve("package-stage").apply { mkdirs() }
            val originalContract = root.resolve("contract-stage").apply { mkdirs() }
            val compatibility = root.resolve("sdk-compatibility.json").apply { writeText("synthetic graph input\n") }
            val tree = "3".repeat(40)
            val target = "ios-simulator-arm64"
            val inspection = root.resolve("inspect.gradle").apply {
                writeText(
                    """
                    gradle.taskGraph.whenReady {
                        def ios = gradle.rootProject.findProject(':codex-agent-runtime-ios')
                        if (ios == null) return
                        def dependencies = { task -> gradle.taskGraph.getDependencies(task)*.path.sort().join(',') }
                        def compiler = ios.tasks.named('generateCodexAgentAppleCompilerEvidence').get()
                        def binding = ios.tasks.named('generateCodexAgentAppleBindingEvidence').get()
                        def tests = ios.tasks.named('verifyCodexAgentSwiftAuthenticationTests').get()
                        ['COMPILER': compiler, 'BINDING': binding].each { label, task ->
                            println('VALIDATION_' + label + '_FRAMEWORK=' + task.xcframeworkDirectory.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_CANONICAL=' + task.canonicalApiReport.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_COVERAGE=' + task.canonicalCoverageReceipt.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_DEPS=' + dependencies(task))
                        }
                        println('VALIDATION_XCTEST_PACKAGE=' + tests.packageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_BINDING_PACKAGE=' + binding.xctestPackageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_XCTEST_DEPS=' + dependencies(tests))
                        ['PACKAGE': 'snapshotSdkIosValidationPackage',
                         'CONTRACT': 'snapshotImportedAppleContractEvidence'].each { label, name ->
                            def task = ios.tasks.named(name).get()
                            println('VALIDATION_' + label + '_SOURCE=' + task.sourceDirectory.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_SNAPSHOT=' + task.outputDirectory.get().asFile.canonicalPath)
                        }
                        def prepared = ios.tasks.named('prepareSdkIosValidationPackage').get()
                        println('VALIDATION_COMPATIBILITY=' + prepared.sdkCompatibility.get().asFile.canonicalPath)
                        println('VALIDATION_PREPARE_DEPS=' + dependencies(prepared))
                    }
                    """.trimIndent() + "\n",
                )
            }
            val result = GradleRunner.create().withProjectDir(repository)
                .withEnvironment(System.getenv().filterKeys {
                    it !in setOf("CODEX_AGENT_IMPORTED_SWIFT_ZIP", "CODEX_AGENT_SWIFT_COMPILATION_DIRECTORY")
                })
                .withArguments(
                    ":codex-agent-runtime-ios:generateCodexAgentAppleBindingEvidence",
                    "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
                    "-PcodexAgent.product=sdk", "-PcodexAgent.component=sdk-ios", "-PcodexAgent.phase=validation",
                    "-PcodexAgent.target=$target", "-PcodexAgent.iosValidationPackageStage=${originalPackage.path}",
                    "-PcodexAgent.contractBinaryStage=${originalContract.path}",
                    "-PcodexAgent.sdkCompatibilityFile=${compatibility.path}",
                    "-PcodexAgent.sdkVersion=0.8.0", "-PcodexAgent.contractVersion=0.8.0",
                    "-PcodexAgent.candidateTree=$tree", "--init-script", inspection.path,
                ).build()
            val selected = result.output.lineSequence()
                .filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                .map { it.removeSuffix(" SKIPPED") }.toList()
            val ios = ":codex-agent-runtime-ios:"
            val expected = setOf(
                "invalidateCodexAgentAppleBindingEvidence", "resetImportedAppleContractEvidence",
                "snapshotImportedAppleContractEvidence", "verifyImportedAppleContractEvidence",
                "snapshotSdkIosValidationPackage", "verifySdkIosValidationPackage", "prepareSdkIosValidationPackage",
                "verifyAppleToolchain", "generateCodexAgentAppleCompilerEvidence",
                "verifyCodexAgentSwiftAuthenticationTests", "generateCodexAgentAppleBindingEvidence",
            ).map { ios + it }.toSet()
            assertEquals(expected, selected.filter { it.startsWith(ios) }.toSet(), result.output)
            assertFalse(selected.any { it.startsWith(":codex-agent-core:") || it.startsWith(":codex-agent-sdk:") }, result.output)
            assertFalse(selected.any { path ->
                val name = path.substringAfterLast(':').lowercase()
                listOf("compilekotlin", "compilejava", "cinterop", "cargo", "rust", "link", "assemble",
                    "stagecodexagent", "packagecodexagent", "crosslanguageapicoverage").any { it in name }
            }, result.output)
            fun value(name: String) = result.output.lineSequence().single { it.startsWith("VALIDATION_$name=") }
                .substringAfter('=')
            val build = repository.resolve("codex-agent-runtime-ios/build").canonicalFile
            val packageRoot = build.resolve("imported-sdk-validation/$tree/$target")
            val contractRoot = build.resolve("imported-apple-contract-evidence/$tree/contract")
            assertEquals(originalPackage.path, value("PACKAGE_SOURCE"))
            assertEquals(originalContract.path, value("CONTRACT_SOURCE"))
            assertEquals(packageRoot.resolve("package-stage").path, value("PACKAGE_SNAPSHOT"))
            assertEquals(contractRoot.path, value("CONTRACT_SNAPSHOT"))
            assertEquals(compatibility.path, value("COMPATIBILITY"))
            listOf("COMPILER", "BINDING").forEach { task ->
                assertEquals(packageRoot.resolve("extracted/xcframework").path, value("${task}_FRAMEWORK"))
                assertEquals(contractRoot.resolve("outputs/evidence/canonical-api.json").path, value("${task}_CANONICAL"))
                assertEquals(contractRoot.resolve("outputs/evidence/canonical-coverage.json").path, value("${task}_COVERAGE"))
            }
            listOf("XCTEST", "BINDING").forEach { task ->
                assertEquals(packageRoot.resolve("extracted/package").path, value("${task}_PACKAGE"))
            }
            fun dependencies(name: String) = value("${name}_DEPS").split(',').toSet()
            assertEquals(setOf(ios + "verifySdkIosValidationPackage"), dependencies("PREPARE"))
            assertEquals(setOf("invalidateCodexAgentAppleBindingEvidence", "verifyAppleToolchain",
                "prepareSdkIosValidationPackage", "verifyImportedAppleContractEvidence").map { ios + it }.toSet(),
                dependencies("COMPILER"))
            assertEquals(setOf("invalidateCodexAgentAppleBindingEvidence", "verifyAppleToolchain",
                "prepareSdkIosValidationPackage").map { ios + it }.toSet(), dependencies("XCTEST"))
            assertEquals(setOf("invalidateCodexAgentAppleBindingEvidence", "generateCodexAgentAppleCompilerEvidence",
                "verifyCodexAgentSwiftAuthenticationTests", "verifyImportedAppleContractEvidence",
                "prepareSdkIosValidationPackage").map { ios + it }.toSet(), dependencies("BINDING"))
            listOf(
                "snapshotSdkIosValidationPackage" to "verifySdkIosValidationPackage",
                "verifySdkIosValidationPackage" to "prepareSdkIosValidationPackage",
                "prepareSdkIosValidationPackage" to "generateCodexAgentAppleCompilerEvidence",
                "prepareSdkIosValidationPackage" to "verifyCodexAgentSwiftAuthenticationTests",
                "snapshotImportedAppleContractEvidence" to "verifyImportedAppleContractEvidence",
                "verifyImportedAppleContractEvidence" to "generateCodexAgentAppleCompilerEvidence",
                "generateCodexAgentAppleCompilerEvidence" to "generateCodexAgentAppleBindingEvidence",
                "verifyCodexAgentSwiftAuthenticationTests" to "generateCodexAgentAppleBindingEvidence",
            ).forEach { (before, after) ->
                assertTrue(selected.indexOf(ios + before) < selected.indexOf(ios + after), result.output)
            }
            assertEquals(emptyList(), originalPackage.listFiles()!!.toList())
            assertEquals(emptyList(), originalContract.listFiles()!!.toList())
            assertEquals("synthetic graph input\n", compatibility.readText())
        } finally {
            root.deleteRecursively()
        }
    }
}
