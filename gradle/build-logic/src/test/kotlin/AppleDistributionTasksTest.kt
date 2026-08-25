import java.io.File
import kotlin.io.path.createTempDirectory
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import org.gradle.api.tasks.CacheableTask

class AppleDistributionTasksTest {
    @Test
    fun `Swift and Objective-C consumers have four separately identified XCTest methods`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("build.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val apple = repository.resolve("codex-agent-runtime-ios/apple")
        val manifest = apple.resolve("Package.swift").readText()
        val registration = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.ios-runtime.gradle.kts",
        ).readText()
        val simulatorTask = repository.resolve(
            "gradle/build-logic/src/main/kotlin/SwiftAuthenticationTestTask.kt",
        ).readText()
        val objectiveCConsumer = apple.resolve(
            "Tests/CodexAgentObjectiveCConsumer/CodexAgentObjectiveCConsumer.m",
        ).readText()
        val swiftConsumer = apple.resolve(
            "Tests/CodexAgentObservationTests/CodexAgentObservationTests.swift",
        ).readText()
        val swiftTestCount = Files.walk(apple.resolve("Tests").toPath()).use { paths ->
            paths.filter { it.toString().endsWith(".swift") }
                .mapToInt { path -> Regex("""\bfunc\s+test\w*\s*\(""").findAll(path.toFile().readText()).count() }
                .sum()
        }

        assertTrue("name: \"CodexAgentObjectiveCConsumer\"" in manifest)
        assertTrue("path: \"Tests/CodexAgentObjectiveCConsumer\"" in manifest)
        assertTrue("publicHeadersPath: \"include\"" in manifest)
        assertTrue("testsDirectory.set(layout.projectDirectory.dir(\"apple/Tests\"))" in registration)
        val expectedIdentifiers = listOf(
            "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
            "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()",
            "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()",
            "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
        )
        expectedIdentifiers.forEach { identifier -> assertTrue("\"$identifier\"" in registration) }
        assertTrue("\"build-for-testing\"" in simulatorTask)
        assertTrue("Files.deleteIfExists(summaryFile.get().asFile.toPath())" in simulatorTask)
        assertTrue("#import <CodexAgent/CodexAgent.h>" in objectiveCConsumer)
        listOf(
            "startWithCompletion", "selectWorkspaceURL", "observeStateWithHandler", "disposeWithCompletion",
            "openConversationWithCompletion", "observeActiveConversationWithHandler",
            "sendPrompt", "cancelTurnWithCompletion",
        ).forEach { selector -> assertTrue(selector in objectiveCConsumer, "missing Objective-C selector $selector") }
        listOf("operation_failed", "Codex operation failed", "failure.isRecoverable").forEach { value ->
            assertTrue(value in objectiveCConsumer, "missing exact Objective-C failure assertion $value")
        }
        assertTrue("func testObjectiveCConsumerExposesStructuredFailure() async" in swiftConsumer)
        assertTrue("CDXRunObjectiveCConsumer" in swiftConsumer)
        assertEquals(4, swiftTestCount)
    }

    @Test
    fun `structured simulator JSON selects exact available runtime and device`() {
        val selection = selectSimulator(
            """{"runtimes":[{"name":"iOS 26.5","isAvailable":true,"identifier":"runtime-1"}]}""",
            """{"devices":{"runtime-1":[{"isAvailable":true,"deviceTypeIdentifier":"iphone-17","udid":"device-1","state":"Shutdown"}]}}""",
            "iOS 26.5",
            "iphone-17",
        )
        assertEquals(SimulatorSelection("runtime-1", "device-1", "Shutdown"), selection)
        assertEquals(
            SimulatorStatus(true, "Shutdown"),
            simulatorStatus(
                """{"devices":{"runtime-1":[{"isAvailable":true,"udid":"device-1","state":"Shutdown"}]}}""",
                "runtime-1",
                "device-1",
            ),
        )
        assertEquals(
            null,
            simulatorStatus("""{"devices":{"runtime-1":[]}}""", "runtime-1", "device-1"),
        )
        val missing = """{"devices":{"runtime-1":[]}}"""
        assertTrue(shouldRetryDisappearedSimulator(missing, "runtime-1", "device-1", 0))
        assertTrue(shouldRetryDisappearedSimulator("""{"devices":{}}""", "runtime-1", "device-1", 0))
        assertFalse(shouldRetryDisappearedSimulator(missing, "runtime-1", "device-1", 1))
        assertFalse(shouldRetryDisappearedSimulator("invalid", "runtime-1", "device-1", 0))
        assertFailsWith<IllegalStateException> {
            selectSimulator(
                """{"runtimes":[]}""",
                """{"devices":{}}""",
                "iOS 26.5",
                "iphone-17",
            )
        }
    }

    @Test
    fun `xcresult validation binds exact test identities statuses and bundle digest`() = withRoot { root ->
        val expected = listOf("Suite/testOne()", "Suite/testTwo()")
        fun tests(secondIdentifier: String = expected[1], secondStatus: String = "Passed") = """
            {
              "devices": [],
              "testNodes": [{
                "name": "Suite",
                "nodeType": "Test Suite",
                "children": [
                  {"name":"testOne()","nodeType":"Test Case","nodeIdentifier":"${expected[0]}","result":"Passed"},
                  {"name":"${secondIdentifier.substringAfter('/')}","nodeType":"Test Case","nodeIdentifier":"$secondIdentifier","result":"$secondStatus"}
                ]
              }],
              "testPlanConfigurations": []
            }
        """.trimIndent()
        val summary = parseSwiftTestSummary("""{"totalTestCount":2,"failedTests":0}""")
        assertEquals(SwiftTestSummary(2, 0), parseSwiftTestSummary("""{"totalTestCount":2}"""))
        assertFailsWith<IllegalStateException> {
            parseSwiftTestSummary("""{"totalTestCount":2,"failedTests":"zero"}""")
        }
        val results = parseSwiftTestCaseResults(tests())
        assertEquals(expected.map { SwiftTestCaseResult(it, "Passed") }, results)
        verifySwiftTestCaseResults(summary, results, expected)
        assertFailsWith<IllegalStateException> {
            verifySwiftTestCaseResults(summary, parseSwiftTestCaseResults(tests("Suite/testOther()")), expected)
        }
        assertFailsWith<IllegalStateException> {
            verifySwiftTestCaseResults(summary, parseSwiftTestCaseResults(tests(secondStatus = "Failed")), expected)
        }
        assertFailsWith<IllegalStateException> {
            verifySwiftTestCaseResults(SwiftTestSummary(1, 0), results, expected)
        }
        assertFailsWith<IllegalStateException> { parseSwiftTestCaseResults(tests(expected[0])) }
        assertFailsWith<IllegalStateException> {
            parseSwiftTestCaseResults("""
                {
                  "devices": [],
                  "testNodes": [
                    {"name":"testOne()","nodeType":"Test Case","nodeIdentifier":"Suite/testOne()","result":"Passed"},
                    {"name":"Suite","nodeType":"Test Suite","children":{}}
                  ],
                  "testPlanConfigurations": []
                }
            """.trimIndent())
        }

        val bundle = root.resolve("tests.xcresult").apply { mkdirs() }
        val payload = bundle.resolve("result").apply { writeText("passed") }
        val digest = bundle.crossLanguageTreeDigest()
        val evidence = swiftTestEvidence(summary, results, digest)
        assertEquals("codex-agent-apple-xctest-v1", evidence.releaseString("protocol"))
        assertEquals(digest, evidence.releaseString("xcresultSha256"))
        assertEquals(2, evidence.releaseArray("tests").size)
        payload.writeText("changed")
        assertNotEquals(digest, bundle.crossLanguageTreeDigest())

        assertFailsWith<IllegalStateException> { verifySwiftTestSummary(SwiftTestSummary(2, 1), 2) }
        assertFailsWith<IllegalStateException> { verifySwiftTestSummary(SwiftTestSummary(0, 0), 0) }
    }

    @Test
    fun `process arguments are explicit and failures retain stderr`() {
        val root = File("/tmp/release args")
        assertEquals(
            listOf(
                "/usr/bin/xcrun", "libtool", "-static", "-D", "-no_warning_for_no_symbols",
                "/tmp/release args/CodexAgent", "-o", "/tmp/release args/CodexAgent.normalized",
            ),
            libtoolNormalizeCommand(root.resolve("CodexAgent"), root.resolve("CodexAgent.normalized")),
        )
        assertEquals(
            listOf(
                "/usr/bin/xcrun", "strip", "-S", "-x", "-o",
                "/tmp/release args/CodexAgent.stripped", "/tmp/release args/CodexAgent",
            ),
            stripReleaseArchiveCommand(root.resolve("CodexAgent"), root.resolve("CodexAgent.stripped")),
        )
        assertEquals(
            listOf(
                "/usr/bin/grep", "-a", "-F", "-q", "-e", "/builder home", "-e", "/checkout",
                "/tmp/release args/CodexAgent",
            ),
            pathPrefixScanCommand(root.resolve("CodexAgent"), listOf("/builder home", "/checkout")),
        )
        verifyPathPrefixScan(1, root.resolve("CodexAgent"), listOf("/checkout"), "")
        assertFailsWith<IllegalStateException> {
            verifyPathPrefixScan(0, root.resolve("CodexAgent"), listOf("/checkout"), "")
        }
        assertFailsWith<IllegalStateException> {
            verifyPathPrefixScan(2, root.resolve("CodexAgent"), listOf("/checkout"), "grep failed")
        }
        val xcodebuild = swiftAuthenticationXcodebuildCommand("device", root.resolve("derived"), root.resolve("tests.xcresult"))
        assertEquals("xcodebuild", xcodebuild.first())
        assertTrue("platform=iOS Simulator,id=device" in xcodebuild)
        assertEquals(
            "test-without-building",
            swiftAuthenticationXcodebuildCommand(
                "device", root.resolve("derived"), root.resolve("tests.xcresult"), true,
            ).last(),
        )
        assertEquals(
            listOf(
                "xcodebuild", "-create-xcframework", "-framework", "/tmp/release args/CodexAgent.framework",
                "-output", "/tmp/release args/CodexAgent.xcframework",
            ),
            swiftSimulatorXCFrameworkCommand(
                root.resolve("CodexAgent.framework"),
                root.resolve("CodexAgent.xcframework"),
            ),
        )
        val simulatorBuild = swiftSimulatorBuildForTestingCommand(root.resolve("derived"))
        assertTrue("generic/platform=iOS Simulator" in simulatorBuild)
        assertEquals("build-for-testing", simulatorBuild.last())
        assertTrue(VerifySwiftSimulatorCompilationTask::class.java.isAnnotationPresent(CacheableTask::class.java))
        val failure = assertFailsWith<IllegalStateException> {
            requireSuccessfulReleaseProcess(listOf("xcodebuild", "test"), 65, "", "tests failed")
        }
        assertTrue(failure.message.orEmpty().contains("tests failed"))
    }

    @Test
    fun `release archive normalization removes checkout roots and preserves exported symbols`() = withRoot { root ->
        if (!File("/usr/bin/xcrun").canExecute()) return@withRoot
        fun run(command: List<String>) {
            val process = ProcessBuilder(command).redirectErrorStream(true).start()
            val output = process.inputStream.bufferedReader().readText()
            check(process.waitFor() == 0) { "${command.joinToString(" ")} failed: $output" }
        }
        fun normalized(name: String): File {
            val directory = root.resolve(name).apply { mkdirs() }
            val source = directory.resolve("source.c").apply {
                writeText("int codex_export(void) { return 7; }")
            }
            val objectFile = directory.resolve("source.o")
            val archive = directory.resolve("CodexAgent")
            val stripped = directory.resolve("CodexAgent.stripped")
            val normalized = directory.resolve("CodexAgent.normalized")
            run(listOf("/usr/bin/xcrun", "clang", "-g", "-c", source.absolutePath, "-o", objectFile.absolutePath))
            run(listOf("/usr/bin/xcrun", "libtool", "-static", "-D", objectFile.absolutePath, "-o", archive.absolutePath))
            run(stripReleaseArchiveCommand(archive, stripped))
            run(libtoolNormalizeCommand(stripped, normalized))
            return normalized
        }
        val first = normalized("one")
        val second = normalized("two")
        assertTrue(Files.mismatch(first.toPath(), second.toPath()) == -1L)
        val strings = ProcessBuilder("/usr/bin/strings", first.absolutePath).start().inputStream.bufferedReader().readText()
        assertFalse(root.absolutePath in strings)
        val symbols = ProcessBuilder("/usr/bin/xcrun", "nm", "-gU", first.absolutePath)
            .start().inputStream.bufferedReader().readText()
        assertTrue("_codex_export" in symbols)
    }

    @Test
    fun `distribution staging copies the exact package and sample layout`() = withRoot { root ->
        fun directory(name: String) = root.resolve(name).apply { mkdirs(); resolve("content").writeText(name) }
        fun file(name: String) = root.resolve(name).apply { parentFile.mkdirs(); writeText(name) }
        val output = root.resolve("distribution")
        stageAppleDistribution(
            AppleDistributionInputs(
                file("inputs/Package.swift"), directory("Sources"), directory("Tests"), directory("Framework"),
                file("LICENSE"), file("THIRD_PARTY_NOTICES.md"), file("codex-license"), file("codex-notice"),
                directory("TestApp"),
            ),
            output,
        )
        val packageRoot = output.resolve("CodexAgentPackage")
        assertEquals("inputs/Package.swift", packageRoot.resolve("Package.swift").readText())
        assertEquals("Sources", packageRoot.resolve("Sources/content").readText())
        assertEquals("Framework", packageRoot.resolve("CodexAgent.xcframework/content").readText())
        assertEquals("TestApp", output.resolve("CodexAgentTestApp/content").readText())
    }

    @Test
    fun `privacy placement and XCFramework library order are exact`() = withRoot { root ->
        val privacy = root.resolve("PrivacyInfo.xcprivacy").apply { writeText("privacy") }
        val framework = root.resolve("CodexAgent.xcframework")
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            framework.resolve("$slice/CodexAgent.framework/PrivacyInfo.xcprivacy").apply {
                parentFile.mkdirs(); writeText("privacy")
            }
        }
        verifyPrivacyPlacement(framework, privacy)
        assertEquals(
            "[{\"LibraryIdentifier\":\"a\"},{\"LibraryIdentifier\":\"b\"}]",
            sortedAvailableLibraries(
                "[{\"LibraryIdentifier\":\"b\"},{\"LibraryIdentifier\":\"a\"}]",
            ),
        )
        framework.resolve("ios-arm64/CodexAgent.framework/PrivacyInfo.xcprivacy").writeText("changed")
        assertFailsWith<IllegalStateException> { verifyPrivacyPlacement(framework, privacy) }
    }

    @Test
    fun `license verification compares bytes and emits deterministic SHA256 lines`() = withRoot { root ->
        val source = root.resolve("LICENSE").apply { writeText("license") }
        val packaged = root.resolve("package/LICENSE.txt").apply { parentFile.mkdirs(); writeText("license") }
        val build = root.resolve("build.gradle.kts").apply {
            writeText("GNU General Public License v3.0 or later")
        }
        val report = verifyPackagedLicenses(listOf(source to packaged), build)
        assertEquals("${packaged.releaseDigest()}  ${packaged.absolutePath}\n", report)
        packaged.appendText("changed")
        assertFailsWith<IllegalStateException> { verifyPackagedLicenses(listOf(source to packaged), build) }
    }

    private fun withRoot(block: (File) -> Unit) {
        val root = createTempDirectory("apple-distribution").toFile()
        try { block(root) } finally { root.deleteRecursively() }
    }
}
