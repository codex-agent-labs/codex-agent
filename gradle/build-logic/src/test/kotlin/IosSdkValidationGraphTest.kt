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
            val originalTestApp = root.resolve("TestApp").apply { mkdirs() }
            val originalCompilerConsumers = root.resolve("CompilerEvidence").apply { mkdirs() }
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
                        def device = ios.tasks.named('verifySdkIosDeviceConsumer').get()
                        def deviceInputs = ios.tasks.named('stageSdkIosValidationDeviceInputs').get()
                        ['COMPILER': compiler, 'BINDING': binding].each { label, task ->
                            println('VALIDATION_' + label + '_FRAMEWORK=' + task.xcframeworkDirectory.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_CANONICAL=' + task.canonicalApiReport.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_COVERAGE=' + task.canonicalCoverageReceipt.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_SWIFT_CONSUMER=' + task.swiftConsumer.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_OBJC_CONSUMER=' + task.objectiveCConsumer.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_DEPS=' + dependencies(task))
                        }
                        println('VALIDATION_XCTEST_PACKAGE=' + tests.packageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_BINDING_PACKAGE=' + binding.xctestPackageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_XCTEST_DEPS=' + dependencies(tests))
                        println('VALIDATION_DEVICE_TESTAPP=' + device.testApplicationDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_PACKAGE=' + device.packageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_EXECUTION=' + device.workDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_RAW=' + device.rawEvidenceDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_ARCHIVE=' + device.archiveDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_DEPS=' + dependencies(device))
                        println('VALIDATION_DEVICE_INPUT_DEPS=' + dependencies(deviceInputs))
                        println('VALIDATION_DEVICE_COMMAND=' + device.commandLine.join('|'))
                        println('VALIDATION_DEVICE_TESTAPP_SOURCE=' + deviceInputs.testApplicationDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_PACKAGE_SOURCE=' + deviceInputs.packageDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_STAGED_TESTAPP=' + deviceInputs.stagedTestApplicationDirectory.get().asFile.canonicalPath)
                        println('VALIDATION_DEVICE_WORK=' + deviceInputs.workDirectory.get().asFile.canonicalPath)
                        ['PACKAGE': 'snapshotSdkIosValidationPackage',
                         'CONTRACT': 'snapshotImportedAppleContractEvidence'].each { label, name ->
                            def task = ios.tasks.named(name).get()
                            println('VALIDATION_' + label + '_SOURCE=' + task.sourceDirectory.get().asFile.canonicalPath)
                            println('VALIDATION_' + label + '_SNAPSHOT=' + task.outputDirectory.get().asFile.canonicalPath)
                        }
                        def prepared = ios.tasks.named('prepareSdkIosValidationPackage').get()
                        println('VALIDATION_COMPATIBILITY=' + prepared.sdkCompatibility.get().asFile.canonicalPath)
                        println('VALIDATION_PREPARE_DEPS=' + dependencies(prepared))
                        def archive = ios.tasks.named('archiveSdkIosValidationEvidence').get()
                        println('VALIDATION_ARCHIVE_DEPS=' + dependencies(archive))
                        println('VALIDATION_ARCHIVE_FILE=' + archive.archiveFile.get().asFile.canonicalPath)
                        println('VALIDATION_ARCHIVE_LAYOUT=' + archive.sourceLayout.get().collect { key, path ->
                            key + '=' + new File(path).canonicalPath }.sort().join('|'))
                        println('VALIDATION_ARCHIVE_INPUTS=' + archive.evidenceInputs.files.collect { it.canonicalPath }.sort().join('|'))
                        println('VALIDATION_HAS_PRODUCT_MANIFEST=' + (ios.tasks.findByName('writeSdkIosValidationOutputManifest') != null))
                    }
                    """.trimIndent() + "\n",
                )
            }
            val result = GradleRunner.create().withProjectDir(repository)
                .withEnvironment(System.getenv().filterKeys {
                    it !in setOf("CODEX_AGENT_IMPORTED_SWIFT_ZIP", "CODEX_AGENT_SWIFT_COMPILATION_DIRECTORY")
                })
                .withArguments(
                    ":codex-agent-runtime-ios:archiveSdkIosValidationEvidence",
                    "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
                    "-PcodexAgent.product=sdk", "-PcodexAgent.component=sdk-ios", "-PcodexAgent.phase=validation",
                    "-PcodexAgent.target=$target", "-PcodexAgent.iosValidationPackageStage=${originalPackage.path}",
                    "-PcodexAgent.contractBinaryStage=${originalContract.path}",
                    "-PcodexAgent.sdkCompatibilityFile=${compatibility.path}",
                    "-PcodexAgent.iosValidationTestApplicationDirectory=${originalTestApp.path}",
                    "-PcodexAgent.iosValidationCompilerConsumersDirectory=${originalCompilerConsumers.path}",
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
                "stageSdkIosValidationDeviceInputs", "verifySdkIosDeviceConsumer",
                "archiveSdkIosValidationEvidence",
            ).map { ios + it }.toSet()
            assertEquals(expected, selected.filter { it.startsWith(ios) }.toSet(), result.output)
            assertFalse(":ciProductPhase" in selected, result.output)
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
            assertEquals("false", value("HAS_PRODUCT_MANIFEST"))
            assertEquals(packageRoot.resolve("execution-envelope/apple-validation-evidence.zip").path, value("ARCHIVE_FILE"))
            assertFalse(File(value("ARCHIVE_FILE")).toPath().startsWith(build.resolve("product-stage").toPath()))
            assertEquals(originalPackage.path, value("PACKAGE_SOURCE"))
            assertEquals(originalContract.path, value("CONTRACT_SOURCE"))
            assertEquals(packageRoot.resolve("package-stage").path, value("PACKAGE_SNAPSHOT"))
            assertEquals(contractRoot.path, value("CONTRACT_SNAPSHOT"))
            assertEquals(compatibility.path, value("COMPATIBILITY"))
            assertEquals(packageRoot.resolve("device-consumer/CodexAgentTestApp").path, value("DEVICE_TESTAPP"))
            assertEquals(value("DEVICE_TESTAPP"), value("DEVICE_STAGED_TESTAPP"))
            assertEquals(packageRoot.resolve("device-consumer/CodexAgentPackage").path, value("DEVICE_PACKAGE"))
            val deviceExecution = packageRoot.resolve("device-execution")
            assertEquals(deviceExecution.path, value("DEVICE_EXECUTION"))
            assertEquals(deviceExecution.resolve("raw").path, value("DEVICE_RAW"))
            assertEquals(deviceExecution.resolve("CodexAgentTestApp.xcarchive").path, value("DEVICE_ARCHIVE"))
            val expectedLayout = mapOf(
                "canonical/canonical-api.json" to contractRoot.resolve("outputs/evidence/canonical-api.json"),
                "canonical/canonical-coverage.json" to contractRoot.resolve("outputs/evidence/canonical-coverage.json"),
                "consumer/CodexFailureSwiftConsumer.swift" to originalCompilerConsumers.resolve("CodexFailureSwiftConsumer.swift"),
                "consumer/CodexFailureObjectiveCConsumer.m" to originalCompilerConsumers.resolve("CodexFailureObjectiveCConsumer.m"),
                "reports/compiler-evidence.json" to build.resolve("reports/cross-language-api/apple/compiler-evidence.json"),
                "reports/binding-evidence.json" to build.resolve("reports/cross-language-api/apple/binding-evidence.json"),
                "reports/swift-parity.json" to build.resolve("reports/cross-language-api/bindings/swift-parity.json"),
                "reports/objective-c-parity.json" to build.resolve("reports/cross-language-api/bindings/objective-c-parity.json"),
                "reports/xctest-summary.json" to build.resolve("swift-authentication-tests-summary.json"),
                "reports/simulator-devices.json" to build.resolve("simulator-devices.json"),
                "compiler-raw" to build.resolve("apple-compiler-evidence-task/raw"),
                "xcframework" to packageRoot.resolve("extracted/xcframework"),
                "xctest-raw" to build.resolve("swift-authentication-evidence-task/raw"),
                "xcresult" to build.resolve("swift-authentication-tests.xcresult"),
                "xctest-package" to packageRoot.resolve("extracted/CodexAgentPackage"),
                "xctest-products" to build.resolve("swift-simulator-compilation-derived-data/Build/Products"),
                "device-raw" to deviceExecution.resolve("raw"),
                "device-archive" to deviceExecution.resolve("CodexAgentTestApp.xcarchive"),
                "device-test-application" to packageRoot.resolve("device-consumer/CodexAgentTestApp"),
                "device-package" to packageRoot.resolve("device-consumer/CodexAgentPackage"),
                "toolchain" to build.resolve("reports/ios-release/toolchain"),
            ).mapValues { (_, path) -> path.path }
            val actualLayout = value("ARCHIVE_LAYOUT").split('|').associate { it.substringBefore('=') to it.substringAfter('=') }
            assertEquals(21, expectedLayout.size)
            assertEquals(expectedLayout, actualLayout)
            assertEquals(expectedLayout.values.toSet(), value("ARCHIVE_INPUTS").split('|').toSet())
            assertEquals(originalTestApp.path, value("DEVICE_TESTAPP_SOURCE"))
            assertEquals(packageRoot.resolve("extracted/CodexAgentPackage").path, value("DEVICE_PACKAGE_SOURCE"))
            assertEquals(packageRoot.resolve("device-consumer").path, value("DEVICE_WORK"))
            val deviceCommand = value("DEVICE_COMMAND").split('|')
            assertEquals("/usr/bin/xcodebuild", deviceCommand.first())
            assertEquals("generic/platform=iOS", deviceCommand[deviceCommand.indexOf("-destination") + 1])
            assertEquals(value("DEVICE_ARCHIVE"), deviceCommand[deviceCommand.indexOf("-archivePath") + 1])
            assertTrue("ARCHS=arm64" in deviceCommand && "CODE_SIGNING_ALLOWED=NO" in deviceCommand)
            assertEquals(listOf("clean", "archive"), deviceCommand.takeLast(2))
            listOf("COMPILER", "BINDING").forEach { task ->
                assertEquals(packageRoot.resolve("extracted/xcframework").path, value("${task}_FRAMEWORK"))
                assertEquals(contractRoot.resolve("outputs/evidence/canonical-api.json").path, value("${task}_CANONICAL"))
                assertEquals(contractRoot.resolve("outputs/evidence/canonical-coverage.json").path, value("${task}_COVERAGE"))
                assertEquals(originalCompilerConsumers.resolve("CodexFailureSwiftConsumer.swift").path,
                    value("${task}_SWIFT_CONSUMER"))
                assertEquals(originalCompilerConsumers.resolve("CodexFailureObjectiveCConsumer.m").path,
                    value("${task}_OBJC_CONSUMER"))
            }
            listOf("XCTEST", "BINDING").forEach { task ->
                assertEquals(packageRoot.resolve("extracted/CodexAgentPackage").path, value("${task}_PACKAGE"))
            }
            fun dependencies(name: String) = value("${name}_DEPS").split(',').toSet()
            assertEquals(setOf(ios + "generateCodexAgentAppleBindingEvidence", ios + "verifySdkIosDeviceConsumer"), dependencies("ARCHIVE"))
            assertEquals(setOf(ios + "verifySdkIosValidationPackage"), dependencies("PREPARE"))
            assertEquals(setOf(ios + "prepareSdkIosValidationPackage"), dependencies("DEVICE_INPUT"))
            assertEquals(setOf("invalidateCodexAgentAppleBindingEvidence", "verifyAppleToolchain",
                "stageSdkIosValidationDeviceInputs").map { ios + it }.toSet(), dependencies("DEVICE"))
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
                "prepareSdkIosValidationPackage" to "stageSdkIosValidationDeviceInputs",
                "stageSdkIosValidationDeviceInputs" to "verifySdkIosDeviceConsumer",
                "generateCodexAgentAppleBindingEvidence" to "archiveSdkIosValidationEvidence",
                "verifySdkIosDeviceConsumer" to "archiveSdkIosValidationEvidence",
            ).forEach { (before, after) ->
                assertTrue(selected.indexOf(ios + before) < selected.indexOf(ios + after), result.output)
            }
            assertEquals(emptyList(), originalPackage.listFiles()!!.toList())
            assertEquals(emptyList(), originalContract.listFiles()!!.toList())
            assertEquals(emptyList(), originalTestApp.listFiles()!!.toList())
            assertEquals(emptyList(), originalCompilerConsumers.listFiles()!!.toList())
            assertEquals("synthetic graph input\n", compatibility.readText())
        } finally {
            root.deleteRecursively()
        }
    }
}
