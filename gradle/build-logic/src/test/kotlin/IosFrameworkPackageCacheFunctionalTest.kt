import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.gradle.testkit.runner.BuildResult
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class IosFrameworkPackageCacheFunctionalTest {
    @Test
    fun `Swift package changes restore the imported XCFramework without assembly`() {
        if (!File("/usr/bin/xcodebuild").canExecute() || !File("/usr/bin/xcrun").canExecute()) return

        val project = createTempDirectory("ios-framework-package-cache").toFile()
        try {
            val testKitDirectory = project.resolve("gradle-user-home")
            writeFrameworkFixture(project.resolve("fixtures/device/CodexAgent.framework"), "iphoneos")
            writeFrameworkFixture(project.resolve("fixtures/simulator/CodexAgent.framework"), "iphonesimulator")
            project.resolve("apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy").apply {
                parentFile.mkdirs()
                writeText(PRIVACY_MANIFEST)
            }
            project.resolve("settings.gradle.kts").writeText("rootProject.name = \"ios-framework-cache-test\"\n")
            project.resolve("gradle.properties").writeText("org.gradle.caching=true\n")
            writeBuild(project, "device-sdk-1|simulator-sdk-1")

            val first = run(project, testKitDirectory, true)
            assertTaskOutcomes(first, TaskOutcome.SUCCESS)
            assertImportedGraph(first)
            val archive = project.resolve("build/distributions/CodexAgent-fixture.xcframework.zip")
            val archiveBytes = archive.readBytes()

            project.resolve("build").deleteRecursively()
            writePackageOnlyChanges(project)

            val restored = run(project, testKitDirectory, true)
            assertTaskOutcomes(restored, TaskOutcome.FROM_CACHE)
            assertImportedGraph(restored)
            assertContentEquals(archiveBytes, archive.readBytes())

            writeBuild(project, "device-sdk-2|simulator-sdk-2")
            project.resolve("build").deleteRecursively()
            val newToolchain = run(project, testKitDirectory, true)
            assertTaskOutcomes(newToolchain, TaskOutcome.FROM_CACHE, IMPORT_TASKS)
            assertTaskOutcomes(newToolchain, TaskOutcome.SUCCESS, listOf(ASSEMBLE_TASK, PREPARE_TASK))
            assertTaskOutcomes(newToolchain, TaskOutcome.FROM_CACHE, listOf(PACKAGE_TASK))

            project.resolve("fixtures/device/CodexAgent.framework/Headers/CodexAgent.h")
                .writeText("int codex_fixture(void);\nint device_only_fixture(void);\n")
            project.resolve("build").deleteRecursively()
            val newDeviceMember = run(project, testKitDirectory, true)
            assertTaskOutcomes(newDeviceMember, TaskOutcome.SUCCESS, listOf(DEVICE_IMPORT) + PACKAGE_GRAPH)
            assertTaskOutcomes(newDeviceMember, TaskOutcome.FROM_CACHE, listOf(SIMULATOR_IMPORT))

            project.resolve("apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy")
                .writeText(PRIVACY_MANIFEST.replace("<false/>", "<true/>"))
            project.resolve("build").deleteRecursively()
            val newPrivacyManifest = run(project, testKitDirectory, true)
            assertTaskOutcomes(newPrivacyManifest, TaskOutcome.FROM_CACHE, IMPORT_TASKS + ASSEMBLE_TASK)
            assertTaskOutcomes(newPrivacyManifest, TaskOutcome.SUCCESS, listOf(PREPARE_TASK, PACKAGE_TASK))
            val privacyArchiveBytes = archive.readBytes()

            project.resolve("build").deleteRecursively()
            val cacheDisabled = run(project, testKitDirectory, false)
            assertTaskOutcomes(cacheDisabled, TaskOutcome.SUCCESS)
            assertContentEquals(privacyArchiveBytes, archive.readBytes())
        } finally {
            project.deleteRecursively()
        }
    }

    private fun run(project: File, testKitDirectory: File, buildCache: Boolean): BuildResult = GradleRunner.create()
        .withProjectDir(project)
        .withTestKitDir(testKitDirectory)
        .withPluginClasspath()
        .withArguments(
            if (buildCache) "--build-cache" else "--no-build-cache",
            "--console=plain",
            "--stacktrace",
            PACKAGE_TASK,
        )
        .build()

    private fun assertTaskOutcomes(
        result: BuildResult,
        expected: TaskOutcome,
        tasks: List<String> = CACHED_GRAPH,
    ) {
        assertEquals(
            tasks.associateWith { expected },
            tasks.associateWith { task -> result.task(":$task")?.outcome },
        )
    }

    private fun assertImportedGraph(result: BuildResult) {
        assertTrue(CACHED_GRAPH.all { task -> result.task(":$task") != null })
        assertNull(result.task(":assembleCodexAgentReleaseXCFramework"))
    }

    private fun writePackageOnlyChanges(project: File) {
        mapOf(
            "Package.swift" to "// root package metadata only\n",
            "apple/Package.swift" to "// inner package metadata only\n",
            "apple/Sources/CodexAgentAuthentication/Wrapper.swift" to "internal let fixture = 1\n",
            "apple/Tests/CodexAgentAuthenticationTests/WrapperTests.swift" to "// test-only change\n",
            "docs/ios.md" to "Package documentation only.\n",
        ).forEach { (path, content) ->
            project.resolve(path).apply { parentFile.mkdirs(); writeText(content) }
        }
    }

    private fun writeBuild(project: File, appleToolchainIdentity: String) {
        project.resolve("build.gradle.kts").writeText(fixtureBuild(appleToolchainIdentity))
    }

    private fun writeFrameworkFixture(framework: File, platform: String) {
        framework.resolve("Headers/CodexAgent.h").apply {
            parentFile.mkdirs()
            writeText("int codex_fixture(void);\n")
        }
        framework.resolve("Modules/module.modulemap").apply {
            parentFile.mkdirs()
            writeText("framework module CodexAgent { umbrella header \"CodexAgent.h\" export * }\n")
        }
        framework.resolve("Info.plist").writeText(frameworkPlist(platform))
        val source = framework.resolve("fixture.c").apply {
            writeText("int codex_fixture(void) { return 7; }\n")
        }
        val objectFile = framework.resolve("fixture.o")
        val target = if (platform == "iphoneos") "arm64-apple-ios15.0" else "arm64-apple-ios15.0-simulator"
        runProcess(
            "/usr/bin/xcrun", "--sdk", platform, "clang", "-target", target,
            "-c", source.absolutePath, "-o", objectFile.absolutePath,
        )
        runProcess(
            "/usr/bin/xcrun", "libtool", "-static", "-D", objectFile.absolutePath,
            "-o", framework.resolve("CodexAgent").absolutePath,
        )
        source.delete()
        objectFile.delete()
    }

    private fun runProcess(vararg command: String) {
        val process = ProcessBuilder(command.toList()).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().readText()
        check(process.waitFor() == 0) { "${command.joinToString(" ")} failed: $output" }
    }

    private fun frameworkPlist(platform: String): String {
        val supportedPlatform = if (platform == "iphoneos") "iPhoneOS" else "iPhoneSimulator"
        return """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0"><dict>
              <key>CFBundleExecutable</key><string>CodexAgent</string>
              <key>CFBundleIdentifier</key><string>com.openai.CodexAgent.fixture</string>
              <key>CFBundleName</key><string>CodexAgent</string>
              <key>CFBundlePackageType</key><string>FMWK</string>
              <key>CFBundleSupportedPlatforms</key><array><string>$supportedPlatform</string></array>
              <key>MinimumOSVersion</key><string>15.0</string>
            </dict></plist>
        """.trimIndent() + "\n"
    }

    private companion object {
        const val DEVICE_IMPORT = "importFixtureDeviceFramework"
        const val SIMULATOR_IMPORT = "importFixtureSimulatorFramework"
        const val ASSEMBLE_TASK = "assembleCodexAgentReleaseXCFrameworkFromImports"
        const val PREPARE_TASK = "prepareCodexAgentReleaseXCFramework"
        const val PACKAGE_TASK = "packageCodexAgentSwiftPackageBinary"
        val IMPORT_TASKS = listOf(DEVICE_IMPORT, SIMULATOR_IMPORT)
        val PACKAGE_GRAPH = listOf(ASSEMBLE_TASK, PREPARE_TASK, PACKAGE_TASK)
        val CACHED_GRAPH = IMPORT_TASKS + PACKAGE_GRAPH
        fun fixtureBuild(appleToolchainIdentity: String) = """
            plugins { id("codexagent.codex-runtime") }

            version = "fixture"
            tasks.register("verifyAppleToolchain")
            tasks.register("assembleCodexAgentReleaseXCFramework") {
                doLast { error("native framework fallback must not run") }
            }
            val device = tasks.register<ImportCodexAgentFrameworkTask>("importFixtureDeviceFramework") {
                frameworkDirectory.set(layout.projectDirectory.dir("fixtures/device/CodexAgent.framework"))
                platformName.set("iphoneos")
                importedFrameworkDirectory.set(layout.buildDirectory.dir("imported/device/CodexAgent.framework"))
            }
            val simulator = tasks.register<ImportCodexAgentFrameworkTask>("importFixtureSimulatorFramework") {
                frameworkDirectory.set(layout.projectDirectory.dir("fixtures/simulator/CodexAgent.framework"))
                platformName.set("iphonesimulator")
                importedFrameworkDirectory.set(layout.buildDirectory.dir("imported/simulator/CodexAgent.framework"))
            }
            val distribution = registerIosAppleDistributionTasks(
                1,
                "fixture",
                providers.provider { "$appleToolchainIdentity" },
                device,
                simulator,
            )
            distribution.prepareCodexAgentReleaseXCFramework.configure {
                forbiddenAbsolutePathPrefixes.set(listOf("/not-present-in-fixture"))
            }
            registerIosAppleReleaseVerificationTasks(distribution, "15.0", "fixture")
        """.trimIndent() + "\n"
        val PRIVACY_MANIFEST = """
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0"><dict><key>NSPrivacyTracking</key><false/></dict></plist>
        """.trimIndent() + "\n"
    }
}
