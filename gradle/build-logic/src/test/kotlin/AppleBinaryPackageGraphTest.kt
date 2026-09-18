import java.io.File
import java.lang.reflect.Proxy
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.provider.ProviderFactory
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.testkit.runner.GradleRunner

/** Configuration/provider checks only: synthetic inputs are not Apple content or host evidence. */
class AppleBinaryPackageGraphTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
    private val tree = "2".repeat(40)

    @Test
    fun `binary package graph imports verified framework snapshots without compiler or test producers`() {
        val root = createTempDirectory("apple-binary-package-graph-").toFile().canonicalFile
        try {
            val binary = root.resolve("binary-stage").apply { mkdirs() }
            val request = root.resolve("compatibility-request.json").apply { writeText("synthetic graph input\n") }
            val inspection = root.resolve("inspect.gradle").apply {
                writeText(
                    """
                    gradle.taskGraph.whenReady {
                        def sdk = gradle.rootProject.findProject(':codex-agent-sdk')
                        if (sdk == null) return
                        def ios = gradle.rootProject.project(':codex-agent-runtime-ios')
                        def manifest = sdk.tasks.named('writeSdkIosPackageOutputManifest').get()
                        def stage = ios.tasks.named('stageBinaryCodexAgentIosSdkPackageArtifacts').get()
                        def dependencies = { task -> gradle.taskGraph.getDependencies(task)*.path.sort().join(',') }
                        ['Device', 'Simulator'].each { target ->
                            def task = ios.tasks.named('importCodexAgentIos' + target + 'Framework').get()
                            println('BINARY_' + target + '_INPUT=' + task.frameworkDirectory.get().asFile.canonicalPath)
                            println('BINARY_' + target + '_DEPS=' + dependencies(task))
                        }
                        println('BINARY_STAGE_DEPS=' + dependencies(stage))
                        println('BINARY_MANIFEST_DEPS=' + dependencies(manifest))
                        println('BINARY_ROOTS=' + manifest.outputRoots.get().collect { key, value -> key + '=' + value }.sort().join(','))
                        println('BINARY_OUTPUT=' + stage.outputDirectory.get().asFile.canonicalPath)
                        println('BINARY_WORK=' + stage.workDirectory.get().asFile.canonicalPath)
                        println('BINARY_OWNED=' + stage.ownedBuildDirectory.get().asFile.canonicalPath)
                        println('BINARY_COMPATIBILITY=' + stage.sdkCompatibility.get().asFile.canonicalPath)
                        println('BINARY_VERSION=' + stage.version.get())
                        println('BINARY_ARCHIVES=' + [stage.applePackageArchive, stage.swiftPackageArchive,
                            stage.swiftPackageChecksum].collect { it.get().asFile.canonicalPath }.join('|'))
                    }
                    """.trimIndent() + "\n",
                )
            }
            val result = GradleRunner.create().withProjectDir(repository)
                .withEnvironment(System.getenv().filterKeys { it != "CODEX_AGENT_IMPORTED_SWIFT_ZIP" })
                .withArguments(
                    "ciProductPhase", "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
                    "-PcodexAgent.product=sdk", "-PcodexAgent.component=sdk-ios", "-PcodexAgent.phase=package",
                    "-PcodexAgent.iosPackageFromBinary=true", "-PcodexAgent.target=ios",
                    "-PcodexAgent.candidateCommit=${"1".repeat(40)}", "-PcodexAgent.candidateTree=$tree",
                    "-PcodexAgent.sdkIosBinaryStageRoot=${binary.path}",
                    "-PcodexAgent.sdkCompatibilityRequest=${request.path}",
                    "--init-script", inspection.path,
                ).build()
            val selected = result.output.lineSequence()
                .filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                .map { it.removeSuffix(" SKIPPED") }.toList()
            val sdk = ":codex-agent-sdk:"
            val ios = ":codex-agent-runtime-ios:"
            val expected = listOf(
                sdk + "invalidateSdkIosPackagePhase", sdk + "snapshotImportedSdkIosBinaryStage",
                sdk + "verifyImportedSdkIosBinaryStage", sdk + "generateNativeWrapperSdkCompatibility",
                ios + "importCodexAgentIosDeviceFramework", ios + "importCodexAgentIosSimulatorFramework",
                ios + "assembleCodexAgentReleaseXCFrameworkFromImports", ios + "prepareCodexAgentReleaseXCFramework",
                ios + "packageCodexAgentAppleDistribution", ios + "packageCodexAgentSwiftPackageBinary",
                ios + "generateCodexAgentSwiftPackageChecksum", ios + "stageBinaryCodexAgentIosSdkPackageArtifacts",
                sdk + "stageSdkIosPackagePhase", sdk + "stageSdkIosPackageEvidence",
                sdk + "writeSdkIosPackageOutputManifest",
            )
            expected.forEach { assertTrue(it in selected, result.output) }
            assertFalse(selected.any { path ->
                val name = path.substringAfterLast(':').lowercase()
                listOf("compile", "link", "cinterop", "cargo", "rust", "xctest", "authenticationtests",
                    "compilerevidence", "bindingevidence", "transported", "verifieddistribution",
                    "swiftpackageproof", "simulatorcompilation").any { it in name } ||
                    name == "verifycodexagentswiftpackage" || name == "iossimulatorarm64test" ||
                    name == "assemblecodexagentreleasexcframework"
            }, result.output)
            fun value(prefix: String) = result.output.lineSequence().single { it.startsWith("$prefix=") }.substringAfter('=')
            val sdkBuild = repository.resolve("codex-agent-sdk/build").canonicalFile
            val phaseRoot = sdkBuild.resolve("product-stage/sdk/sdk-ios/package")
            listOf("Device" to "ios-arm64", "Simulator" to "ios-simulator-arm64").forEach { (name, target) ->
                assertEquals(sdkBuild.resolve("imported-sdk-binary-stages/$tree/sdk-ios/outputs/apple-binary/$target/CodexAgent.framework").path,
                    value("BINARY_${name}_INPUT"))
                assertEquals(sdk + "verifyImportedSdkIosBinaryStage", value("BINARY_${name}_DEPS"))
            }
            assertEquals("apple=outputs/apple,evidence=outputs/evidence,maven=outputs/maven", value("BINARY_ROOTS"))
            assertEquals(phaseRoot.resolve("outputs/apple").path, value("BINARY_OUTPUT"))
            assertEquals(sdkBuild.path, value("BINARY_OWNED"))
            assertEquals(sdkBuild.resolve("apple-sdk-package-tasks/$tree/binary-stage-work").path, value("BINARY_WORK"))
            assertFalse(File(value("BINARY_WORK")).toPath().startsWith(phaseRoot.toPath()))
            assertEquals(sdkBuild.resolve("sdk-compatibility/$tree/META-INF/codex-agent/sdk-compatibility.json").path,
                value("BINARY_COMPATIBILITY"))
            val version = value("BINARY_VERSION")
            val distributions = repository.resolve("codex-agent-runtime-ios/build/distributions").canonicalFile
            assertEquals(listOf("CodexAgentPackage-$version.zip", "CodexAgent-$version.xcframework.zip",
                "CodexAgent-$version.xcframework.zip.sha256").joinToString("|") { distributions.resolve(it).path },
                value("BINARY_ARCHIVES"))
            assertEquals(setOf(sdk + "verifyImportedSdkIosBinaryStage", sdk + "generateNativeWrapperSdkCompatibility",
                ios + "packageCodexAgentAppleDistribution", ios + "packageCodexAgentSwiftPackageBinary",
                ios + "generateCodexAgentSwiftPackageChecksum"), value("BINARY_STAGE_DEPS").split(',').toSet())
            assertEquals(setOf(sdk + "stageSdkIosPackageEvidence", ios + "stageBinaryCodexAgentIosSdkPackageArtifacts"),
                value("BINARY_MANIFEST_DEPS").split(',').toSet())
            listOf(
                sdk + "verifyImportedSdkIosBinaryStage" to ios + "importCodexAgentIosDeviceFramework",
                sdk + "verifyImportedSdkIosBinaryStage" to ios + "importCodexAgentIosSimulatorFramework",
                ios + "importCodexAgentIosDeviceFramework" to ios + "assembleCodexAgentReleaseXCFrameworkFromImports",
                ios + "importCodexAgentIosSimulatorFramework" to ios + "assembleCodexAgentReleaseXCFrameworkFromImports",
                ios + "assembleCodexAgentReleaseXCFrameworkFromImports" to ios + "prepareCodexAgentReleaseXCFramework",
                ios + "generateCodexAgentSwiftPackageChecksum" to ios + "stageBinaryCodexAgentIosSdkPackageArtifacts",
                ios + "stageBinaryCodexAgentIosSdkPackageArtifacts" to sdk + "writeSdkIosPackageOutputManifest",
            ).forEach { (before, after) -> assertTrue(selected.indexOf(before) < selected.indexOf(after), result.output) }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `binary package mode requires exact phase and both original input locators`() {
        withMode { mode ->
            assertFalse(mode(emptyMap(), emptyMap()))
            assertTrue(mode(properties(), emptyMap()))
            listOf("codexAgent.iosPackageFromBinary" to "false", "codexAgent.product" to "runtime",
                "codexAgent.component" to "sdk-core", "codexAgent.phase" to "binary",
                "codexAgent.target" to "desktop").forEach { (key, value) ->
                assertFailsWith<IllegalStateException>(key) { mode(properties() + (key to value), emptyMap()) }
            }
            assertFailsWith<IllegalStateException> { mode(properties() - "codexAgent.target", emptyMap()) }
            listOf("codexAgent.sdkIosBinaryStageRoot", "codexAgent.sdkCompatibilityRequest").forEach { key ->
                assertFailsWith<IllegalStateException>(key) { mode(properties() - key, emptyMap()) }
                assertFailsWith<IllegalStateException>(key) { mode(properties() + (key to " "), emptyMap()) }
            }
        }
    }

    @Test
    fun `binary package mode rejects every old distribution and framework override`() {
        withMode { mode ->
            listOf(IOS_VERIFIED_DISTRIBUTION_PROPERTY, "codexAgent.iosExpectedDistributionProof",
                "codexAgent.iosExpectedSdkCompatibility", "codexAgent.iosNativeEvidenceDirectory",
                "codexAgent.iosDeviceFrameworkDirectory", "codexAgent.iosSimulatorFrameworkDirectory").forEach { key ->
                assertFailsWith<IllegalStateException>(key) { mode(properties() + (key to ""), emptyMap()) }
            }
            assertFailsWith<IllegalStateException> {
                mode(properties(), mapOf("CODEX_AGENT_IMPORTED_SWIFT_ZIP" to ""))
            }
        }
    }

    private fun properties() = mapOf(
        "codexAgent.iosPackageFromBinary" to "true", "codexAgent.product" to "sdk",
        "codexAgent.component" to "sdk-ios", "codexAgent.phase" to "package",
        "codexAgent.target" to "ios",
        "codexAgent.sdkIosBinaryStageRoot" to "/synthetic/binary", "codexAgent.sdkCompatibilityRequest" to "/synthetic/request.json",
    )

    /** Only provider lookup is substituted; the production mode validator runs unchanged. */
    private fun withMode(block: ((Map<String, String>, Map<String, String>) -> Boolean) -> Unit) {
        val root = createTempDirectory("apple-binary-mode-").toFile()
        try {
            val factory = ProjectBuilder.builder().withProjectDir(root).build().providers
            block { properties, environment ->
                val providers = Proxy.newProxyInstance(ProviderFactory::class.java.classLoader,
                    arrayOf(ProviderFactory::class.java)) { _, method, arguments ->
                    val values = when (method.name) {
                        "gradleProperty" -> properties
                        "environmentVariable" -> environment
                        else -> error("Unexpected provider call: ${method.name}")
                    }
                    factory.provider { values[arguments!![0] as String] }
                } as ProviderFactory
                val project = Proxy.newProxyInstance(Project::class.java.classLoader, arrayOf(Project::class.java)) { _, method, _ ->
                    check(method.name == "getProviders") { "Unexpected project call: ${method.name}" }
                    providers
                } as Project
                project.usesAppleBinaryPackageInputs()
            }
        } finally {
            root.deleteRecursively()
        }
    }
}
