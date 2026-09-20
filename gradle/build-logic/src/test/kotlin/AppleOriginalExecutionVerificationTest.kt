import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class AppleOriginalExecutionVerificationTest {
    @Test
    fun `compiler replay needs no distribution compatibility proof or XCTest inputs`() =
        OriginalAppleExecutionFixture().use { fixture ->
            val compiler = fixture.root.resolve("compiler-only-evidence.json")
            fixture.compilerEvidence.copyTo(compiler)
            fixture.distribution.deleteRecursively()
            fixture.expectedProof.parentFile.deleteRecursively()
            listOf("sdk-compatibility.json", "source", "xcresult", "xctest-package", "xctest-products", "xctest-raw")
                .forEach { fixture.execution.resolve(it).deleteRecursively() }
            assertTrue(!fixture.distribution.exists())
            assertTrue(!fixture.expectedProof.exists())
            assertTrue(!fixture.execution.resolve("xctest-raw").exists())
            val before = fixture.compilerInputDigests(compiler)
            fixture.verifyCompiler(compiler)
            assertEquals(before, fixture.compilerInputDigests(compiler))
        }

    @Test
    fun `compiler only replay rejects raw report header and consumer drift without rewriting inputs`() =
        OriginalAppleExecutionFixture().use { fixture ->
            fixture.verifyCompiler()
            val before = fixture.compilerInputDigests()
            val mutations: List<Pair<File, (File) -> Unit>> = listOf(
                fixture.swiftSymbolGraph to { file ->
                    file.writeText(file.readText().replaceFirst("\"swift.init\"", "\"swift.method\""))
                },
                fixture.compilerCommand to { file ->
                    val report = file.readReleaseObject()
                    file.atomicWriteJson(JsonObject(report + (
                        "command" to JsonArray(report.releaseArray("command") + JsonPrimitive("--unexpected"))
                    )))
                },
                fixture.compilerEvidence to { file ->
                    val report = file.readReleaseObject()
                    val canonical = report["canonical"] as JsonObject
                    file.atomicWriteJson(JsonObject(report + ("canonical" to JsonObject(
                        canonical + ("apiReportSha256" to JsonPrimitive("0".repeat(64))),
                    ))))
                },
                fixture.execution.resolve("xcframework/ios-arm64/CodexAgent.framework/Headers/CodexAgent.h") to
                    { file -> file.appendText("// changed header\n") },
                fixture.execution.resolve("consumer/CodexFailureSwiftConsumer.swift") to
                    { file -> file.appendText("// changed Swift consumer\n") },
                fixture.execution.resolve("consumer/CodexFailureObjectiveCConsumer.m") to
                    { file -> file.appendText("// changed Objective-C consumer\n") },
            )
            mutations.forEach { (file, mutate) ->
                val original = file.readBytes()
                try {
                    mutate(file)
                    val changed = fixture.compilerInputDigests()
                    assertFailsWith<IllegalStateException>(file.path) { fixture.verifyCompiler() }
                    assertEquals(changed, fixture.compilerInputDigests(), file.path)
                } finally {
                    file.writeBytes(original)
                }
                assertEquals(before, fixture.compilerInputDigests())
            }
        }

    @Test
    fun `binding replay needs no distribution compatibility native or unrelated XCTest inputs`() =
        OriginalAppleExecutionFixture().use { fixture ->
            fixture.verify()
            val reports = fixture.copyBindingReports()
            fixture.distribution.deleteRecursively()
            fixture.expectedProof.parentFile.deleteRecursively()
            listOf("sdk-compatibility.json", "source", "native-evidence", "xctest-products").forEach {
                fixture.execution.resolve(it).deleteRecursively()
            }
            assertTrue(!fixture.distribution.exists())
            assertTrue(!fixture.expectedProof.exists())
            assertTrue(!fixture.execution.resolve("native-evidence").exists())
            val before = fixture.bindingInputDigests(reports)

            fixture.verifyBinding(reports)

            assertEquals(before, fixture.bindingInputDigests(reports))
        }

    @Test
    fun `binding replay rejects raw XCTest digest report and parity drift without rewriting inputs`() =
        OriginalAppleExecutionFixture().use { fixture ->
            val reports = fixture.copyBindingReports()
            fixture.verifyBinding(reports)
            val mutations: List<Pair<File, (File) -> Unit>> = listOf(
                fixture.xctestTestsOutput to { file ->
                    file.writeText(file.readText().replaceFirst("Passed", "Failed"))
                },
                fixture.priorXCTestSummaryCommand to { file ->
                    val execution = file.readReleaseObject()
                    file.atomicWriteJson(JsonObject(execution + (
                        "command" to JsonArray(execution.releaseArray("command") + JsonPrimitive("--changed"))
                    )))
                },
                fixture.execution.resolve("xcresult/result") to { file -> file.appendText("changed\n") },
                fixture.execution.resolve("xctest-package/Package.swift") to { file -> file.appendText("// changed\n") },
                reports.resolve("xctest.json") to { file -> file.atomicWriteJson(JsonObject(emptyMap())) },
                reports.resolve("binding.json") to { file -> file.atomicWriteJson(JsonObject(emptyMap())) },
                reports.resolve("swift-parity.json") to { file -> file.atomicWriteJson(JsonObject(emptyMap())) },
                reports.resolve("objective-c-parity.json") to { file -> file.atomicWriteJson(JsonObject(emptyMap())) },
            )
            mutations.forEach { (file, mutate) ->
                val original = file.readBytes()
                try {
                    mutate(file)
                    val changed = fixture.bindingInputDigests(reports)
                    assertFailsWith<IllegalStateException>(file.path) { fixture.verifyBinding(reports) }
                    assertEquals(changed, fixture.bindingInputDigests(reports), file.path)
                } finally {
                    file.writeBytes(original)
                }
            }
        }

    @Test
    fun `replays original raw compiler and XCTest observations through the full matcher`() =
        OriginalAppleExecutionFixture().use { fixture ->
            val before = fixture.inputDigests()
            fixture.verify()
            assertEquals(before, fixture.inputDigests())
            fixture.verifyUsingPackagedTool()
            assertEquals(before, fixture.inputDigests())
        }

    @Test
    fun `raw compiler XCTest and caller cross-pairs reject without changing originals`() =
        OriginalAppleExecutionFixture().use { fixture ->
            val before = fixture.inputDigests()
            fixture.verify()
            val swift = fixture.swiftSymbolGraph
            val swiftBytes = swift.readBytes()
            swift.writeText(swift.readText().replaceFirst("\"swift.init\"", "\"swift.method\""))
            assertFailureContains("swift Apple binding symbol changed") { fixture.verify() }
            swift.writeBytes(swiftBytes)

            val tests = fixture.xctestTestsOutput
            val testsBytes = tests.readBytes()
            tests.writeText(tests.readText().replaceFirst("Passed", "Failed"))
            assertFailureContains("Swift package test statuses changed") { fixture.verify() }
            tests.writeBytes(testsBytes)

            val command = fixture.compilerCommand
            val commandValue = command.readReleaseObject()
            command.atomicWriteJson(JsonObject(commandValue + (
                "command" to JsonArray(commandValue.releaseArray("command") + JsonPrimitive("--unexpected"))
            )))
            assertFailureContains("Original Apple Swift symbolgraph command changed") { fixture.verify() }
            command.atomicWriteJson(commandValue)

            val objectiveCommand = fixture.objectiveCompilerCommand
            val objectiveValue = objectiveCommand.readReleaseObject()
            val objectiveArguments = objectiveValue.releaseArray("command").toMutableList()
            val outputIndex = objectiveArguments.indexOf(JsonPrimitive("-o"))
            objectiveArguments[outputIndex - 1] = JsonPrimitive(
                fixture.root.resolve(
                    "different/ios-arm64/CodexAgent.framework/Headers/CodexAgent.h",
                ).path,
            )
            objectiveCommand.atomicWriteJson(JsonObject(objectiveValue + (
                "command" to JsonArray(objectiveArguments)
            )))
            assertFailureContains("Original Apple Objective-C extract-api command changed") { fixture.verify() }
            objectiveCommand.atomicWriteJson(objectiveValue)
            assertEquals(before, fixture.inputDigests())

            fixture.promoteXCTestSuccessToAttemptOne()
            fixture.verify()
            val promoted = fixture.inputDigests()
            val priorSummary = fixture.priorXCTestSummaryCommand
            val priorSummaryValue = priorSummary.readReleaseObject()
            priorSummary.atomicWriteJson(JsonObject(priorSummaryValue + (
                "command" to JsonArray(priorSummaryValue.releaseArray("command") + JsonPrimitive("--changed"))
            )))
            assertFailureContains("Original Apple prior xcresult summary command changed") { fixture.verify() }
            priorSummary.atomicWriteJson(priorSummaryValue)
            val priorXcode = fixture.priorXCTestCommand
            val priorXcodeValue = priorXcode.readReleaseObject()
            priorXcode.atomicWriteJson(JsonObject(priorXcodeValue + ("exitCode" to JsonPrimitive(7))))
            assertFailureContains("continued after a failed process") { fixture.verify() }
            priorXcode.atomicWriteJson(priorXcodeValue)

            assertFailureContains("differs from the caller expectation") {
                verifyOriginalAppleExecution(
                    fixture.distribution, fixture.execution, fixture.expectedProof,
                    fixture.root.resolve("wrong-compatibility.json").apply { writeText("{}\n") },
                )
            }
            assertEquals(promoted, fixture.inputDigests())
        }

    @Test
    fun `private snapshot cannot contain or be contained by any input`() {
        val root = createTempDirectory("original-apple-overlap-guard").toFile().canonicalFile
        try {
            assertFailsWith<IllegalStateException> {
                requireOriginalAppleSnapshotDisjoint(root.resolve("snapshot"), listOf(root))
            }
            assertFailsWith<IllegalStateException> {
                requireOriginalAppleSnapshotDisjoint(root, listOf(root.resolve("input")))
            }
        } finally {
            root.deleteRecursively()
        }
    }
}

private class OriginalAppleExecutionFixture : AutoCloseable {
    val root = createTempDirectory("original-apple-execution").toFile().canonicalFile
    val distribution = root.resolve("distribution").apply { mkdirs() }
    val execution = root.resolve("execution").apply { mkdirs() }
    val expectedProof = root.resolve("expected/verified-distribution-proof.json")
    private val expectedCompatibility = root.resolve("expected/sdk-compatibility.json")
    private val compatibilityBytes = "{\"schemaVersion\":1,\"sdkVersion\":\"0.2.0\"}\n".toByteArray()
    private val producerCommit = "1".repeat(40)
    private val producerTree = "2".repeat(40)
    private val version = "0.2.0"
    val swiftSymbolGraph get() = execution.resolve(
        "compiler-raw/ios-arm64/swift-symbols/CodexAgent.symbols.json",
    )
    val xctestTestsOutput get() = execution.resolve("xctest-raw/attempt-0/tests/stdout.bin")
    val compilerCommand get() = execution.resolve("compiler-raw/ios-arm64/swift-symbolgraph/execution.json")
    val objectiveCompilerCommand get() =
        execution.resolve("compiler-raw/ios-arm64/objective-c-extract-api/execution.json")
    val priorXCTestCommand get() = execution.resolve("xctest-raw/attempt-0/xcodebuild/execution.json")
    val priorXCTestSummaryCommand get() = execution.resolve("xctest-raw/attempt-0/summary/execution.json")
    val compilerEvidence get() = distribution.resolve("reports/cross-language-api/apple/compiler-evidence.json")

    init {
        expectedCompatibility.parentFile.mkdirs()
        expectedCompatibility.writeBytes(compatibilityBytes)
        execution.resolve("sdk-compatibility.json").writeBytes(compatibilityBytes)
        execution.resolve("source/Package.swift").writeFixture("// retained package\n")
        execution.resolve("source/native-provenance.json").writeFixture("{}\n")
        execution.resolve("consumer/CodexFailureSwiftConsumer.swift").writeFixture("// swift consumer\n")
        execution.resolve("consumer/CodexFailureObjectiveCConsumer.m").writeFixture("// objective-c consumer\n")
        execution.resolve("xcresult/result").writeFixture("xcresult\n")
        execution.resolve("xctest-package/Package.swift").writeFixture("// xctest package\n")
        execution.resolve("xctest-products/CodexAgentTests.xctest/test").writeFixture("xctest product\n")
        writeFrameworks()
        val base = reflectedBindingFixture()
        writeCanonicalInputs(base.first)
        writeCompilerRaw()
        val compiler = writeCompilerEvidence(base.second)
        val xctest = writeXCTestRaw()
        writeFinalEvidence(compiler, xctest)
        writeNativeEvidence()
        writeDistributionArtifacts()
        writeDistributionProof()
    }

    fun verify() = verifyOriginalAppleExecution(
        distribution, execution, expectedProof, expectedCompatibility,
    )

    fun verifyCompiler(compiler: File = compilerEvidence) = verifyOriginalAppleCompilerEvidence(
        readCrossLanguageCanonicalApiEvidence(
            execution.resolve("canonical/canonical-api.json"), execution.resolve("canonical/canonical-coverage.json"),
        ),
        compiler, execution.resolve("compiler-raw"), execution.resolve("xcframework"),
        execution.resolve("consumer/CodexFailureSwiftConsumer.swift"),
        execution.resolve("consumer/CodexFailureObjectiveCConsumer.m"),
    )

    fun compilerInputDigests(compiler: File = compilerEvidence): Map<String, String> = buildMap {
        verifiedRegularFiles(execution).forEach { (path, file) -> put("execution/$path", file.releaseDigest()) }
        put("compiler-evidence", compiler.releaseDigest())
    }

    fun copyBindingReports(): File = root.resolve("retained-binding-reports").also { reports ->
        reports.mkdirs()
        mapOf(
            compilerEvidence to "compiler.json",
            distribution.resolve("reports/swift-authentication-tests-summary.json") to "xctest.json",
            distribution.resolve("reports/cross-language-api/apple/binding-evidence.json") to "binding.json",
            distribution.resolve("reports/cross-language-api/bindings/swift-parity.json") to "swift-parity.json",
            distribution.resolve("reports/cross-language-api/bindings/objective-c-parity.json") to
                "objective-c-parity.json",
        ).forEach { (source, name) -> source.copyTo(reports.resolve(name)) }
    }

    fun verifyBinding(reports: File) = verifyOriginalAppleBindingEvidence(
        readCrossLanguageCanonicalApiEvidence(
            execution.resolve("canonical/canonical-api.json"), execution.resolve("canonical/canonical-coverage.json"),
        ),
        execution,
        reports.resolve("compiler.json"),
        reports.resolve("xctest.json"),
        reports.resolve("binding.json"),
        reports.resolve("swift-parity.json"),
        reports.resolve("objective-c-parity.json"),
    )

    fun bindingInputDigests(reports: File): Map<String, String> = buildMap {
        verifiedRegularFiles(execution).forEach { (path, file) -> put("execution/$path", file.releaseDigest()) }
        verifiedRegularFiles(reports).forEach { (path, file) -> put("reports/$path", file.releaseDigest()) }
    }

    fun verifyUsingPackagedTool() {
        val java = File(
            System.getProperty("java.home"),
            "bin/${if (System.getProperty("os.name").startsWith("Windows")) "java.exe" else "java"}",
        )
        val jar = File(checkNotNull(System.getProperty("codexAgent.releaseToolingJar")))
        val process = ProcessBuilder(
            java.path, "-jar", jar.path, "verify-original-apple-execution",
            "--distribution-directory", distribution.path,
            "--execution-directory", execution.path,
            "--expected-distribution-proof", expectedProof.path,
            "--expected-sdk-compatibility", expectedCompatibility.path,
        ).directory(root).redirectErrorStream(true).start()
        val log = process.inputStream.bufferedReader().use { it.readText() }
        assertEquals(0, process.waitFor(), log)
    }

    fun inputDigests(): Map<String, String> = buildMap {
        verifiedRegularFiles(distribution).forEach { (path, file) -> put("distribution/$path", file.releaseDigest()) }
        verifiedRegularFiles(execution).forEach { (path, file) -> put("execution/$path", file.releaseDigest()) }
        put("expected-proof", expectedProof.releaseDigest())
        put("expected-compatibility", expectedCompatibility.releaseDigest())
    }

    fun promoteXCTestSuccessToAttemptOne() {
        val raw = execution.resolve("xctest-raw")
        copyReleaseTree(raw.resolve("attempt-0"), raw.resolve("attempt-1"))
        raw.resolve("successful-attempt.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1)); put("attempt", JsonPrimitive(1))
        })
    }

    private fun writeFrameworks() {
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            val framework = execution.resolve("xcframework/$slice/CodexAgent.framework")
            framework.resolve("CodexAgent").writeFixture("binary:$slice\n")
            framework.resolve("Headers/CodexAgent.h").writeFixture("header\n")
            framework.resolve("Modules/module.modulemap").writeFixture("modulemap\n")
            framework.resolve("Info.plist").writeFixture("plist:$slice\n")
        }
    }

    private fun writeCanonicalInputs(canonical: CrossLanguageCanonicalApiEvidence) {
        val api = execution.resolve("canonical/canonical-api.json")
        api.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2))
            put("libraryUniqueName", JsonPrimitive("codex-agent-core"))
            put("markerAnnotation", JsonPrimitive("sample.CodexBindingApi"))
            put("signatureVersion", JsonPrimitive(2))
            put("boundaryTypes", JsonArray(emptyList()))
            put("memberExclusionAnnotation", JsonPrimitive("sample.CodexBindingApiKotlinOnly"))
            put("excludedReachableTypes", JsonArray(emptyList()))
            put("excludedMemberKeys", JsonArray(emptyList()))
            put("dataClassMetadataAvailable", JsonPrimitive(true))
            put("dataClassNames", JsonArray(emptyList()))
            put("owners", buildJsonArray { add(buildJsonObject {
                put("name", JsonPrimitive("sample/Owner"))
                put("capabilities", canonical.memberKeys.jsonStrings())
            }) })
            put("targets", buildJsonArray {
                listOf("native", "wasm", "jvm-classes").forEachIndexed { index, kind ->
                    add(buildJsonObject {
                        put("kind", JsonPrimitive(kind)); put("sha256", JsonPrimitive("${index + 3}".repeat(64)))
                    })
                }
            })
        })
        execution.resolve("canonical/canonical-coverage.json").atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(2)); put("result", JsonPrimitive("passed"))
            put("kotlinCompilerVersion", JsonPrimitive("2.3.10"))
            put("canonicalTestTask", JsonPrimitive(":codex-agent-core:jvmTest"))
            put("apiReportSha256", JsonPrimitive(api.releaseDigest()))
            put("compiledTestsSha256", JsonPrimitive("6".repeat(64)))
            put("testResultsSha256", JsonPrimitive("7".repeat(64)))
            put("capabilities", canonical.memberKeys.jsonStrings())
            put("claims", buildJsonArray { add(buildJsonObject {
                put("testId", JsonPrimitive("sample.CanonicalTest#behavior"))
                put("capabilities", canonical.memberKeys.jsonStrings())
            }) })
        })
    }

    private fun writeCompilerRaw() {
        val raw = execution.resolve("compiler-raw")
        val environment = mapOf("LC_ALL" to "C", "LANG" to "C")
        fun capture(path: String, command: List<String>, stdout: String = "", working: File = root) {
            writeReleaseProcessCapture(
                raw.resolve(path), command, working, environment, 0,
                stdout.toByteArray(), byteArrayOf(),
            )
        }
        capture("toolchain/xcode", listOf("/usr/bin/xcodebuild", "-version"), "Xcode 26.6\nBuild version 17F113\n")
        capture("toolchain/swift", listOf("/usr/bin/xcrun", "swift", "--version"), "Apple Swift version 6.3.3\n")
        capture("toolchain/clang", listOf("/usr/bin/xcrun", "clang", "--version"), "Apple clang version 21.0.0\n")
        val swiftSurface = reflectedCompilerRaw(
            "swiftSurfaceJson", arrayOf<Any?>(true, null, null, null, null, null, null, null, null, null),
        )
        val objectiveSurface = reflectedCompilerRaw(
            "objectiveCSurfaceJson", arrayOf<Any?>(true, null, null, null, null),
        )
        val swiftReferences = reflectedCompilerRaw("swiftReferencesJson", arrayOfNulls<Any>(1))
        val objectiveReferences = reflectedCompilerRaw("objectiveCReferencesJson", arrayOfNulls<Any>(1))
        mapOf(
            "ios-arm64" to Pair("iphoneos", "arm64-apple-ios15.0"),
            "ios-arm64-simulator" to Pair("iphonesimulator", "arm64-apple-ios15.0-simulator"),
        ).forEach { (slice, specification) ->
            val sdk = File("/Applications/Xcode.app/Contents/Developer/Platforms/${specification.first}.sdk")
            val frameworkSearch = execution.resolve("xcframework/$slice")
            val work = root.resolve("compiler-work/$slice")
            val swiftOutput = raw.resolve("$slice/swift-symbols")
            val objectiveOutput = raw.resolve("$slice/CodexAgent.objc.symbols.json")
            capture("$slice/sdk-path", listOf(
                "/usr/bin/xcrun", "--sdk", specification.first, "--show-sdk-path",
            ), "${sdk.path}\n")
            capture("$slice/sdk-version", listOf(
                "/usr/bin/xcrun", "--sdk", specification.first, "--show-sdk-version",
            ), "26.6\n")
            capture("$slice/swift-symbolgraph", swiftSymbolGraphCommand(
                specification.second, sdk, frameworkSearch, work.resolve("swift-module-cache"), swiftOutput,
            ))
            swiftOutput.resolve("CodexAgent.symbols.json").writeFixture(swiftSurface)
            capture("$slice/objective-c-extract-api", objectiveCExtractApiCommand(
                specification.second, sdk, frameworkSearch, work.resolve("clang-module-cache"),
                frameworkSearch.resolve("CodexAgent.framework/Headers/CodexAgent.h"), objectiveOutput,
            ))
            objectiveOutput.writeFixture(objectiveSurface)
            capture("$slice/swift-consumer-ast", swiftConsumerAstCommand(
                specification.second, sdk, frameworkSearch, work.resolve("swift-consumer-cache"),
                execution.resolve("consumer/CodexFailureSwiftConsumer.swift"),
            ), swiftReferences)
            capture("$slice/objective-c-consumer-ast", objectiveCConsumerAstCommand(
                specification.second, sdk, frameworkSearch, work.resolve("objective-c-consumer-cache"),
                execution.resolve("consumer/CodexFailureObjectiveCConsumer.m"),
            ), objectiveReferences)
        }
    }

    private fun writeCompilerEvidence(base: JsonObject): JsonObject {
        val canonical = readCrossLanguageCanonicalApiEvidence(
            execution.resolve("canonical/canonical-api.json"), execution.resolve("canonical/canonical-coverage.json"),
        )
        val targets = listOf("ios-arm64", "ios-arm64-simulator").mapIndexed { index, slice ->
            val framework = execution.resolve("xcframework/$slice/CodexAgent.framework")
            buildJsonObject {
                put("name", JsonPrimitive(slice))
                put("sdk", JsonPrimitive(if (index == 0) "iphoneos" else "iphonesimulator"))
                put("sdkVersion", JsonPrimitive("26.6"))
                put("targetTriple", JsonPrimitive(
                    if (index == 0) "arm64-apple-ios15.0" else "arm64-apple-ios15.0-simulator",
                ))
                put("frameworkSha256", JsonPrimitive(framework.crossLanguageTreeDigest()))
                put("binarySha256", JsonPrimitive(framework.resolve("CodexAgent").releaseDigest()))
                put("headerSha256", JsonPrimitive(framework.resolve("Headers/CodexAgent.h").releaseDigest()))
                put("moduleMapSha256", JsonPrimitive(framework.resolve("Modules/module.modulemap").releaseDigest()))
            }
        }
        val compiler = JsonObject(base + mapOf(
            "canonical" to buildJsonObject {
                put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
                put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
                put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
                put("capabilities", appleBindingCapabilityKeys(canonical.memberKeys).jsonStrings())
            },
            "toolchain" to buildJsonObject {
                put("xcodeVersion", JsonPrimitive("26.6")); put("xcodeBuild", JsonPrimitive("17F113"))
                put("swiftVersion", JsonPrimitive("6.3.3")); put("clangVersion", JsonPrimitive("Apple clang version 21.0.0"))
            },
            "artifacts" to buildJsonObject {
                put("xcframeworkSha256", JsonPrimitive(execution.resolve("xcframework").crossLanguageTreeDigest()))
                put("swiftConsumerSha256", JsonPrimitive(
                    execution.resolve("consumer/CodexFailureSwiftConsumer.swift").releaseDigest(),
                ))
                put("objectiveCConsumerSha256", JsonPrimitive(
                    execution.resolve("consumer/CodexFailureObjectiveCConsumer.m").releaseDigest(),
                ))
            },
            "targets" to JsonArray(targets),
        ))
        distribution.resolve("reports/cross-language-api/apple/compiler-evidence.json").apply {
            parentFile.mkdirs(); atomicWriteJson(compiler)
        }
        return compiler
    }

    private fun writeXCTestRaw(): JsonObject {
        val summaryJson = "{\"totalTestCount\":4,\"failedTests\":0}"
        val testsJson = releaseJson.encodeToString(JsonElement.serializer(), buildJsonObject {
            put("devices", JsonArray(emptyList()))
            put("testNodes", buildJsonArray { expectedAppleTests.forEach { identifier -> add(buildJsonObject {
                put("nodeType", JsonPrimitive("Test Case")); put("nodeIdentifier", JsonPrimitive(identifier))
                put("name", JsonPrimitive(identifier.substringAfter('/'))); put("result", JsonPrimitive("Passed"))
            }) } })
            put("testPlanConfigurations", JsonArray(emptyList()))
        })
        val raw = execution.resolve("xctest-raw")
        val resultBundle = root.resolve("swift-authentication-tests.xcresult")
        val environment = mapOf("LC_ALL" to "C", "LANG" to "C")
        writeReleaseProcessCapture(
            raw.resolve("attempt-0/xcodebuild"),
            swiftAuthenticationXcodebuildCommand("SIMULATOR", root.resolve("derived"), resultBundle),
            root.resolve("CodexAgentPackage"), environment, 0, byteArrayOf(), byteArrayOf(),
        )
        writeReleaseProcessCapture(
            raw.resolve("attempt-0/summary"),
            listOf("/usr/bin/xcrun", "xcresulttool", "get", "test-results", "summary", "--path", resultBundle.path, "--compact"),
            root, environment, 0, summaryJson.toByteArray(), byteArrayOf(),
        )
        writeReleaseProcessCapture(
            raw.resolve("attempt-0/tests"),
            listOf("/usr/bin/xcrun", "xcresulttool", "get", "test-results", "tests", "--path", resultBundle.path, "--compact"),
            root, environment, 0, testsJson.toByteArray(), byteArrayOf(),
        )
        raw.resolve("successful-attempt.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1)); put("attempt", JsonPrimitive(0))
        })
        val evidence = swiftTestEvidence(
            parseSwiftTestSummary(summaryJson), parseSwiftTestCaseResults(testsJson),
            execution.resolve("xcresult").crossLanguageTreeDigest(),
        )
        distribution.resolve("reports/swift-authentication-tests-summary.json").apply {
            parentFile.mkdirs(); atomicWriteJson(evidence)
        }
        return evidence
    }

    private fun writeFinalEvidence(compiler: JsonObject, xctest: JsonObject) {
        val canonical = readCrossLanguageCanonicalApiEvidence(
            execution.resolve("canonical/canonical-api.json"), execution.resolve("canonical/canonical-coverage.json"),
        )
        val digests = AppleBindingInputDigests(
            distribution.resolve("reports/cross-language-api/apple/compiler-evidence.json").releaseDigest(),
            execution.resolve("xcframework").crossLanguageTreeDigest(),
            execution.resolve("consumer/CodexFailureSwiftConsumer.swift").releaseDigest(),
            execution.resolve("consumer/CodexFailureObjectiveCConsumer.m").releaseDigest(),
            distribution.resolve("reports/swift-authentication-tests-summary.json").releaseDigest(),
            execution.resolve("xcresult").crossLanguageTreeDigest(),
            execution.resolve("xctest-package").crossLanguageTreeDigest(),
            listOf("ios-arm64", "ios-arm64-simulator").associateWith { slice ->
                val framework = execution.resolve("xcframework/$slice/CodexAgent.framework")
                AppleBindingTargetDigests(
                    framework.crossLanguageTreeDigest(), framework.resolve("CodexAgent").releaseDigest(),
                    framework.resolve("Headers/CodexAgent.h").releaseDigest(),
                    framework.resolve("Modules/module.modulemap").releaseDigest(),
                )
            },
        )
        val binding = deriveCrossLanguageAppleBindingEvidence(canonical, compiler, xctest, digests)
        val bindingFile = distribution.resolve("reports/cross-language-api/apple/binding-evidence.json").apply {
            parentFile.mkdirs(); atomicWriteJson(binding)
        }
        mapOf(
            CrossLanguageBinding.SWIFT to "reports/cross-language-api/bindings/swift-parity.json",
            CrossLanguageBinding.OBJECTIVE_C to "reports/cross-language-api/bindings/objective-c-parity.json",
        ).forEach { (language, path) ->
            writeCrossLanguageBindingReceipt(
                distribution.resolve(path),
                buildAppleBindingParityReceipt(binding, language, digests, bindingFile.releaseDigest()),
            )
        }
        (appleVerifiedReportLayout.keys - setOf(
            "reports/cross-language-api/apple/compiler-evidence.json",
            "reports/cross-language-api/apple/binding-evidence.json",
            "reports/cross-language-api/bindings/swift-parity.json",
            "reports/cross-language-api/bindings/objective-c-parity.json",
            "reports/swift-authentication-tests-summary.json",
        )).forEach { distribution.resolve(it).writeFixture("$it\n") }
        appleVerifiedToolchainLayout.keys.forEach { distribution.resolve(it).writeFixture("$it\n") }
    }

    private fun writeNativeEvidence() {
        val native = execution.resolve("native-evidence")
        (appleRustSliceSpecs.flatMap { listOf(it.archiveName, it.proofName) } + IOS_NATIVE_TESTS_PROOF)
            .forEach { native.resolve(it).writeFixture("$it\n") }
        distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT).writeFixture("{}\n")
    }

    private fun writeDistributionArtifacts() {
        val frameworkArchive = distribution.resolve("CodexAgent-$version.xcframework.zip")
        writeZip(frameworkArchive, listOf("ios-arm64", "ios-arm64-simulator").associate { slice ->
            "CodexAgent.xcframework/$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json" to
                compatibilityBytes
        })
        writeZip(
            distribution.resolve("CodexAgentPackage-$version.zip"),
            mapOf("META-INF/codex-agent/sdk-compatibility.json" to compatibilityBytes),
        )
        distribution.resolve("CodexAgent-$version.xcframework.zip.sha256")
            .writeText("${frameworkArchive.releaseDigest()}\n")
    }

    private fun writeDistributionProof() {
        val nativeReceipt = distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
        val identity = AppleVerifiedDistributionIdentity(
            producerCommit, producerTree, version,
            execution.resolve("source/native-provenance.json").releaseDigest(),
            execution.resolve("source/Package.swift").releaseDigest(), nativeReceipt.releaseDigest(),
            expectedCompatibility.releaseDigest(),
        )
        val artifacts = appleVerifiedArtifactNames(version).associateWith(distribution::resolve)
        val reports = appleVerifiedReportLayout.keys.associateWith(distribution::resolve)
        val toolchain = appleVerifiedToolchainLayout.keys.associateWith(distribution::resolve)
        val receipt = mapOf(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT to nativeReceipt)
        distribution.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).atomicWriteJson(buildAppleVerifiedDistributionProof(
            identity, artifacts, reports, toolchain, verifiedRegularFiles(execution.resolve("native-evidence")), receipt,
        ))
        expectedProof.parentFile.mkdirs()
        distribution.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF).copyTo(expectedProof)
    }

    @Suppress("UNCHECKED_CAST")
    private fun reflectedBindingFixture(): Pair<CrossLanguageCanonicalApiEvidence, JsonObject> {
        val test = CrossLanguageAppleBindingEvidenceTest()
        val method = test.javaClass.declaredMethods.single { it.name == "fixture" && it.parameterCount == 0 }
            .apply { isAccessible = true }
        val fixture = method.invoke(test)
        fun field(name: String): Any = fixture.javaClass.getDeclaredField(name).apply { isAccessible = true }.get(fixture)
        return field("canonical") as CrossLanguageCanonicalApiEvidence to field("compiler") as JsonObject
    }

    private fun reflectedCompilerRaw(name: String, arguments: Array<Any?>): String {
        val test = AppleCompilerEvidenceTaskTest()
        val method = test.javaClass.declaredMethods.single {
            it.name == name && it.parameterCount == arguments.size
        }.apply { isAccessible = true }
        return method.invoke(test, *arguments) as String
    }

    override fun close() {
        root.deleteRecursively()
    }
}

private fun File.writeFixture(contents: String) {
    parentFile.mkdirs()
    writeText(contents)
}

private fun List<String>.jsonStrings(): JsonArray = JsonArray(map(::JsonPrimitive))

private fun writeZip(file: File, members: Map<String, ByteArray>) {
    file.parentFile.mkdirs()
    ZipOutputStream(file.outputStream()).use { archive ->
        members.forEach { (path, bytes) ->
            archive.putNextEntry(ZipEntry(path)); archive.write(bytes); archive.closeEntry()
        }
    }
}

private fun assertFailureContains(expected: String, block: () -> Unit) {
    val failure = assertFailsWith<IllegalStateException>(block = block)
    assertTrue(failure.message?.contains(expected) == true, failure.message)
}
