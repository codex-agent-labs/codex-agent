import java.io.File
import java.io.OutputStream
import java.lang.reflect.Proxy
import kotlin.io.path.createTempDirectory
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertContentEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.Action
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.process.ExecOperations
import org.gradle.process.ExecResult
import org.gradle.process.ExecSpec

class AppleDistributionTasksTest {
    @Test
    fun `simulator observations are separate lossless captures with optional boot`() = withRoot { temporary ->
        for (booted in listOf(false, true)) {
            val fixture = SimulatorCaptureFixture(temporary.resolve("booted-$booted"))
            fixture.selection(booted)
            fixture.success()
            fixture.task.verify()
            fixture.assertConsumed()
            val operations = setOf("runtimes", "devices", "bootstatus", "ready-devices") +
                if (booted) emptySet() else setOf("boot")
            val simulator = fixture.task.simulatorRawEvidenceDirectory.get().asFile
            assertEquals(operations.flatMap { operation ->
                listOf("execution.json", "stdout.bin", "stderr.bin").map { "attempt-0/$operation/$it" }
            }.toSet(), verifiedRegularFiles(simulator).keys)
            assertFalse(simulator.resolve("attempt-0/failure.json").exists())
            assertEquals(fixture.devices("Booted"), simulator.resolve("attempt-0/ready-devices/stdout.bin").readText())
            assertContentEquals(byteArrayOf(0, -1, 10), simulator.resolve("attempt-0/bootstatus/stderr.bin").readBytes())
            val raw = fixture.task.rawEvidenceDirectory.get().asFile
            assertEquals(setOf("successful-attempt.json") + listOf("xcodebuild", "summary", "tests").flatMap { operation ->
                listOf("execution.json", "stdout.bin", "stderr.bin").map { "attempt-0/$operation/$it" }
            }, verifiedRegularFiles(raw).keys)
            assertEquals(0, raw.resolve("successful-attempt.json").readReleaseObject().releaseInt("attempt"))
            assertEquals(simulator.parentFile.resolve("raw"), raw)
            assertEquals("package original\n", fixture.packageDirectory.resolve("Package.swift").readText())
        }
    }

    @Test
    fun `disappeared simulator retry retains both attempts without changing retry semantics`() = withRoot { temporary ->
        val fixture = SimulatorCaptureFixture(temporary)
        fixture.selection(booted = true)
        fixture.enqueue(fixture.xcodeCommand(), "first failed XCTest\n", exit = 65)
        fixture.enqueue(fixture.devicesCommand, """{"devices":{"runtime-1":[]}}""", afterProcess = {
            assertTrue(fixture.task.simulatorRawEvidenceDirectory.file("attempt-0/failure.json").get().asFile.isFile)
        })
        fixture.selection(booted = false)
        fixture.success()
        fixture.task.verify()
        fixture.assertConsumed()
        val simulator = fixture.task.simulatorRawEvidenceDirectory.get().asFile
        assertEquals("""{"devices":{"runtime-1":[]}}""",
            simulator.resolve("attempt-0/retry-devices/stdout.bin").readText())
        assertTrue(simulator.resolve("attempt-1/boot/execution.json").isFile)
        assertFalse(simulator.resolve("attempt-1/retry-devices").exists())
        assertFalse(simulator.resolve("attempt-1/failure.json").exists())
        val failure = simulator.resolve("attempt-0/failure.json").readReleaseObject()
        assertEquals(setOf("schemaVersion", "exceptionClass", "message"), failure.keys)
        assertEquals(1, failure.releaseInt("schemaVersion"))
        assertEquals(IllegalStateException::class.java.name, failure.releaseString("exceptionClass"))
        assertTrue("failed (65)" in failure.releaseString("message"))
        val raw = fixture.task.rawEvidenceDirectory.get().asFile
        assertEquals(65, raw.resolve("attempt-0/xcodebuild/execution.json").readReleaseObject().releaseInt("exitCode"))
        assertEquals(1, raw.resolve("successful-attempt.json").readReleaseObject().releaseInt("attempt"))
    }

    @Test
    fun `simulator launch and retry observation failures retain raw bytes and do not retry`() = withRoot { temporary ->
        for (launch in listOf(false, true)) {
            val fixture = SimulatorCaptureFixture(temporary.resolve("launch-$launch"))
            fixture.enqueue(fixture.runtimesCommand, fixture.runtimes)
            fixture.enqueue(fixture.devicesCommand, fixture.devices("Booted"))
            fixture.enqueue(fixture.bootstatusCommand, "partial bootstatus\n", exit = 70, launch = launch)
            fixture.enqueue(fixture.devicesCommand, "partial retry listing\n", exit = 71)
            val originalFailure = assertFailsWith<IllegalStateException> { fixture.task.verify() }
            fixture.assertConsumed()
            val simulator = fixture.task.simulatorRawEvidenceDirectory.get().asFile
            val failure = simulator.resolve("attempt-0/failure.json").readReleaseObject()
            assertEquals(originalFailure.javaClass.name, failure.releaseString("exceptionClass"))
            assertEquals(originalFailure.message, failure.releaseString("message"))
            assertEquals("partial bootstatus\n", simulator.resolve("attempt-0/bootstatus/stdout.bin").readText())
            assertEquals(if (launch) "null" else "70",
                simulator.resolve("attempt-0/bootstatus/execution.json").readReleaseObject()["exitCode"].toString())
            assertEquals(71, simulator.resolve("attempt-0/retry-devices/execution.json").readReleaseObject().releaseInt("exitCode"))
            assertFalse(simulator.resolve("attempt-1").exists())
            assertFalse(fixture.task.rawEvidenceDirectory.file("successful-attempt.json").get().asFile.exists())
        }
    }

    @Test
    fun `report filesystem failure after successful XCTest processes has an original failure observation`() = withRoot { temporary ->
        val fixture = SimulatorCaptureFixture(temporary)
        fixture.selection(booted = true)
        fixture.success(afterTests = {
            fixture.task.summaryFile.get().asFile.apply {
                mkdirs(); resolve("block-report-replacement").writeText("synthetic filesystem obstruction\n")
            }
        })
        fixture.enqueue(fixture.devicesCommand, fixture.devices("Booted"))
        val originalFailure = assertFailsWith<Exception> { fixture.task.verify() }
        fixture.assertConsumed()
        val simulator = fixture.task.simulatorRawEvidenceDirectory.get().asFile
        val failure = simulator.resolve("attempt-0/failure.json").readReleaseObject()
        assertEquals(originalFailure.javaClass.name, failure.releaseString("exceptionClass"))
        assertEquals(originalFailure.message, failure.releaseString("message"))
        val raw = fixture.task.rawEvidenceDirectory.get().asFile
        listOf("xcodebuild", "summary", "tests").forEach { operation ->
            assertEquals(0, raw.resolve("attempt-0/$operation/execution.json").readReleaseObject().releaseInt("exitCode"))
        }
        assertFalse(raw.resolve("successful-attempt.json").exists())
        assertFalse(simulator.resolve("attempt-1").exists())
    }

    @Test
    fun `caught failure with no message retains JSON null`() = withRoot { temporary ->
        val fixture = SimulatorCaptureFixture(temporary)
        fixture.enqueue(fixture.runtimesCommand, fixture.runtimes)
        fixture.enqueue(fixture.devicesCommand, fixture.devices("Booted"))
        fixture.enqueue(fixture.bootstatusCommand, afterProcess = { throw IllegalStateException() })
        fixture.enqueue(fixture.devicesCommand, fixture.devices("Booted"))
        assertFailsWith<IllegalStateException> { fixture.task.verify() }
        fixture.assertConsumed()
        val failure = fixture.task.simulatorRawEvidenceDirectory.file("attempt-0/failure.json")
            .get().asFile.readReleaseObject()
        assertEquals(IllegalStateException::class.java.name, failure.releaseString("exceptionClass"))
        assertEquals(kotlinx.serialization.json.JsonNull, failure["message"])
    }

    @Test
    fun `simulator capture rejects overlapping inputs before cleanup or any process`() = withRoot { temporary ->
        val fixture = SimulatorCaptureFixture(temporary)
        val simulator = fixture.task.simulatorRawEvidenceDirectory.get().asFile
        simulator.mkdirs()
        val original = simulator.resolve("Package.swift").apply { writeText("original must remain\n") }
        fixture.task.packageDirectory.set(simulator)
        assertFailsWith<IllegalStateException> { fixture.task.verify() }
        fixture.assertConsumed()
        assertEquals("original must remain\n", original.readText())
        assertFalse(fixture.task.rawEvidenceDirectory.get().asFile.exists())
    }

    @Test
    fun `actual capture wrapper retains nonzero and launch failure bytes before throwing`() = withRoot { temporaryRoot ->
        val root = temporaryRoot.canonicalFile
        val bytes = byteArrayOf(-1, 0, 10)
        for (launchFailure in listOf(false, true)) for (explicitDirectory in listOf(false, true)) {
            var stdout: OutputStream? = null
            var stderr: OutputStream? = null
            val defaultDirectory = root.resolve("project-aware-default").apply { mkdirs() }
            var configuredDirectory = defaultDirectory
            val spec = Proxy.newProxyInstance(ExecSpec::class.java.classLoader, arrayOf(ExecSpec::class.java)) { _, method, args ->
                when (method.name) {
                    "setStandardOutput" -> stdout = args!![0] as OutputStream
                    "setErrorOutput" -> stderr = args!![0] as OutputStream
                    "workingDir", "setWorkingDir" -> configuredDirectory = args!![0] as File
                    "getWorkingDir" -> return@newProxyInstance configuredDirectory
                }
                null
            } as ExecSpec
            val operations = Proxy.newProxyInstance(ExecOperations::class.java.classLoader,
                arrayOf(ExecOperations::class.java)) { _, method, args ->
                check(method.name == "exec")
                @Suppress("UNCHECKED_CAST")
                (args!![0] as Action<ExecSpec>).execute(spec)
                stdout!!.write(bytes); stderr!!.write(bytes.reversedArray())
                if (launchFailure) error("original launch failure")
                Proxy.newProxyInstance(ExecResult::class.java.classLoader, arrayOf(ExecResult::class.java)) { _, call, _ ->
                    check(call.name == "getExitValue")
                    65
                } as ExecResult
            } as ExecOperations
            val capture = root.resolve("capture-$launchFailure-$explicitDirectory")
            val failure = assertFailsWith<IllegalStateException> {
                operations.captureReleaseProcess(listOf("/synthetic/tool", "unchanged argument"),
                    workingDirectory = if (explicitDirectory) root else null, captureDirectory = capture)
            }
            assertTrue(if (launchFailure) "original launch failure" in failure.message.orEmpty()
                else "failed (65)" in failure.message.orEmpty())
            assertContentEquals(bytes, capture.resolve("stdout.bin").readBytes())
            assertContentEquals(bytes.reversedArray(), capture.resolve("stderr.bin").readBytes())
            assertEquals(if (launchFailure) "null" else "65",
                capture.resolve("execution.json").readReleaseObject().getValue("exitCode").toString())
            assertEquals(kotlinx.serialization.json.JsonPrimitive(
                (if (explicitDirectory) root else defaultDirectory).absolutePath),
                capture.resolve("execution.json").readReleaseObject().getValue("workingDirectory"))
        }
    }

    @Test
    fun `raw process capture preserves exact streams including failure and empty diagnostics`() = withRoot { temporaryRoot ->
        val root = temporaryRoot.canonicalFile
        val bytes = byteArrayOf(0, -1, -61, 40, 10)
        for (exit in listOf(0, 65, null)) {
            val directory = root.resolve("capture-$exit")
            val command = listOf("/usr/bin/xcrun", "swiftc", "argument with spaces")
            writeReleaseProcessCapture(directory, command, root, mapOf("LC_ALL" to "C"), exit, bytes, byteArrayOf())
            assertContentEquals(bytes, directory.resolve("stdout.bin").readBytes())
            assertContentEquals(byteArrayOf(), directory.resolve("stderr.bin").readBytes())
            val record = directory.resolve("execution.json").readReleaseObject()
            assertEquals(exit?.toString() ?: "null", record.getValue("exitCode").toString())
            assertEquals(setOf("execution.json", "stdout.bin", "stderr.bin"), verifiedRegularFiles(directory).keys)
            val before = verifiedRegularFiles(directory).mapValues { (_, file) -> file.releaseDigest() }
            assertFailsWith<IllegalStateException> {
                writeReleaseProcessCapture(directory, command, root, emptyMap(), 0, byteArrayOf(), bytes)
            }
            assertEquals(before, verifiedRegularFiles(directory).mapValues { (_, file) -> file.releaseDigest() })
        }
        val linked = root.resolve("linked")
        Files.createSymbolicLink(linked.toPath(), root.toPath())
        assertFailsWith<IllegalStateException> {
            writeReleaseProcessCapture(linked.resolve("new"), listOf("tool"), root, emptyMap(), 0, bytes, bytes)
        }
        assertFalse(root.resolve("new").exists())
    }

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
        val releaseRegistration = repository.resolve(
            "gradle/build-logic/src/main/kotlin/IosAppleReleaseVerificationTasks.kt",
        ).readText()
        assertTrue(
            "CodexAgent.framework/META-INF/codex-agent" in releaseRegistration,
            "SwiftPM binary ZIP omits SDK compatibility metadata",
        )
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
                file("sdk-compatibility.json"),
                directory("TestApp"),
            ),
            output,
        )
        val packageRoot = output.resolve("CodexAgentPackage")
        assertEquals("inputs/Package.swift", packageRoot.resolve("Package.swift").readText())
        assertEquals("Sources", packageRoot.resolve("Sources/content").readText())
        assertEquals("Framework", packageRoot.resolve("CodexAgent.xcframework/content").readText())
        assertEquals("codex-license", packageRoot.resolve("openai-codex-LICENSE.txt").readText())
        assertEquals("codex-notice", packageRoot.resolve("openai-codex-NOTICE.txt").readText())
        assertEquals(
            "sdk-compatibility.json",
            packageRoot.resolve("META-INF/codex-agent/sdk-compatibility.json").readText(),
        )
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

/** Actual task/capture wrapper with scripted process observations, never an Apple tool invocation. */
private class SimulatorCaptureFixture(directory: File) {
    private data class Observation(
        val command: List<String>, val output: String, val exit: Int, val launch: Boolean,
        val afterProcess: () -> Unit,
    )
    private val root = directory.canonicalFile.apply { mkdirs() }
    private val observations = mutableListOf<Observation>()
    private var consumed = 0
    private val processes = Proxy.newProxyInstance(ExecOperations::class.java.classLoader,
        arrayOf(ExecOperations::class.java)) { _, method, arguments ->
        check(method.name == "exec")
        check(consumed < observations.size) { "Unexpected simulator process" }
        val observation = observations[consumed++]
        var stdout: OutputStream? = null
        var stderr: OutputStream? = null
        var workingDirectory = root
        var command = emptyList<String>()
        val spec = Proxy.newProxyInstance(ExecSpec::class.java.classLoader, arrayOf(ExecSpec::class.java)) specHandler@ { _, call, args ->
            when (call.name) {
                "commandLine" -> command = (args!![0] as Iterable<*>).map { it.toString() }
                "setStandardOutput" -> stdout = args!![0] as OutputStream
                "setErrorOutput" -> stderr = args!![0] as OutputStream
                "workingDir", "setWorkingDir" -> workingDirectory = args!![0] as File
                "getWorkingDir" -> return@specHandler workingDirectory
            }
            null
        } as ExecSpec
        @Suppress("UNCHECKED_CAST")
        (arguments!![0] as Action<ExecSpec>).execute(spec)
        assertEquals(observation.command, command)
        stdout!!.write(observation.output.toByteArray(Charsets.UTF_8))
        stderr!!.write(byteArrayOf(0, -1, 10))
        if (command.first() == "xcodebuild") {
            File(command[command.indexOf("-resultBundlePath") + 1]).resolve("result").apply {
                parentFile.mkdirs(); writeText("synthetic original result\n")
            }
        }
        observation.afterProcess()
        if (observation.launch) error("synthetic original launch failure")
        Proxy.newProxyInstance(ExecResult::class.java.classLoader, arrayOf(ExecResult::class.java)) { _, call, _ ->
            check(call.name == "getExitValue")
            observation.exit
        } as ExecResult
    } as ExecOperations
    private val project = ProjectBuilder.builder().withProjectDir(root).build()
    val packageDirectory = root.resolve("CodexAgentPackage").apply {
        mkdirs(); resolve("Package.swift").writeText("package original\n")
    }
    val task = project.tasks.create("swiftAuthentication", VerifySwiftAuthenticationTestsTask::class.java, processes).apply {
        packageDirectory.set(this@SimulatorCaptureFixture.packageDirectory)
        runtimeName.set("iOS 26.5")
        deviceTypeIdentifier.set("iphone-17")
        expectedTestIdentifiers.set(listOf("Suite/testOne()"))
        derivedDataDirectory.set(root.resolve("derived"))
        resultBundleDirectory.set(root.resolve("swift-authentication-tests.xcresult"))
        summaryFile.set(root.resolve("reports/summary.json"))
        simulatorDevicesFile.set(root.resolve("reports/simulator-devices.json"))
    }
    val runtimesCommand = listOf("/usr/bin/xcrun", "simctl", "list", "-j", "runtimes")
    val devicesCommand = listOf("/usr/bin/xcrun", "simctl", "list", "-j", "devices", "available")
    val bootstatusCommand = listOf("/usr/bin/xcrun", "simctl", "bootstatus", "device-1", "-b")
    val runtimes = """{"runtimes":[{"name":"iOS 26.5","isAvailable":true,"identifier":"runtime-1"}]}"""

    fun devices(state: String) = """{"devices":{"runtime-1":[{"isAvailable":true,"deviceTypeIdentifier":"iphone-17","udid":"device-1","state":"$state"}]}}"""
    fun enqueue(command: List<String>, output: String = "", exit: Int = 0, launch: Boolean = false,
                afterProcess: () -> Unit = {}) {
        observations += Observation(command, output, exit, launch, afterProcess)
    }
    fun selection(booted: Boolean) {
        enqueue(runtimesCommand, runtimes)
        enqueue(devicesCommand, devices(if (booted) "Booted" else "Shutdown"))
        if (!booted) enqueue(listOf("/usr/bin/xcrun", "simctl", "boot", "device-1"))
        enqueue(bootstatusCommand)
        enqueue(devicesCommand, devices("Booted"))
    }
    fun xcodeCommand() = swiftAuthenticationXcodebuildCommand("device-1",
        task.derivedDataDirectory.get().asFile, task.resultBundleDirectory.get().asFile)
    fun success(afterTests: () -> Unit = {}) {
        enqueue(xcodeCommand(), "XCTest passed\n")
        val query = listOf("/usr/bin/xcrun", "xcresulttool", "get", "test-results")
        val suffix = listOf("--path", task.resultBundleDirectory.get().asFile.absolutePath, "--compact")
        enqueue(query + "summary" + suffix, """{"totalTestCount":1,"failedTests":0}""")
        enqueue(query + "tests" + suffix,
            """{"devices":[],"testNodes":[{"name":"testOne()","nodeType":"Test Case","nodeIdentifier":"Suite/testOne()","result":"Passed"}],"testPlanConfigurations":[]}""",
            afterProcess = afterTests)
    }
    fun assertConsumed() = assertEquals(observations.size, consumed)
}
