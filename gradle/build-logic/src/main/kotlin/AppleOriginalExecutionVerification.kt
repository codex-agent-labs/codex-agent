import java.io.File
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.intOrNull

private val originalAppleExecutionRoots = setOf(
    "compiler-raw", "xcframework", "xcresult", "xctest-package", "xctest-products", "xctest-raw",
    "native-evidence",
)

private val originalAppleExecutionFiles = setOf(
    "canonical/canonical-api.json",
    "canonical/canonical-coverage.json",
    "consumer/CodexFailureSwiftConsumer.swift",
    "consumer/CodexFailureObjectiveCConsumer.m",
    "source/Package.swift",
    "source/native-provenance.json",
    "sdk-compatibility.json",
)

private val originalAppleCompilerSlices = linkedMapOf(
    "ios-arm64" to Pair("iphoneos", "arm64-apple-ios15.0"),
    "ios-arm64-simulator" to Pair("iphonesimulator", "arm64-apple-ios15.0-simulator"),
)

private data class OriginalAppleCompilerSliceReplay(
    val swiftSurface: List<AppleCompilerSymbol>,
    val objectiveCSurface: List<AppleCompilerSymbol>,
    val swiftReferences: List<AppleCompilerReference>,
    val objectiveCReferences: List<AppleCompilerReference>,
    val sdkVersion: String,
)

/**
 * Replays the retained Apple compiler and XCTest observations without invoking an Apple toolchain.
 * The caller remains responsible for authenticating the supplied original producer and transport.
 */
internal fun verifyOriginalAppleExecution(
    distributionDirectory: File,
    executionDirectory: File,
    expectedDistributionProof: File,
    expectedSdkCompatibility: File,
) {
    val inputs = listOf(
        distributionDirectory, executionDirectory, expectedDistributionProof, expectedSdkCompatibility,
    )
    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "original execution") }
    check(distributionDirectory.isDirectory && executionDirectory.isDirectory &&
        expectedDistributionProof.isFile && expectedSdkCompatibility.isFile) {
        "Original Apple execution input is missing"
    }
    val distribution = distributionDirectory.canonicalFile
    val execution = executionDirectory.canonicalFile
    check(distribution.toPath() != execution.toPath() &&
        !distribution.toPath().startsWith(execution.toPath()) &&
        !execution.toPath().startsWith(distribution.toPath())) {
        "Original Apple distribution and execution inputs overlap"
    }

    val temporary = Files.createTempDirectory("codex-agent-original-apple-execution-").toFile().canonicalFile
    try {
        requireOriginalAppleSnapshotDisjoint(temporary, inputs)
        val originalDistribution = verifiedRegularFiles(distribution)
        val originalExecution = verifiedRegularFiles(execution)
        val originalDistributionDigests = originalDistribution.mapValues { (_, file) -> file.releaseDigest() }
        val originalExecutionDigests = originalExecution.mapValues { (_, file) -> file.releaseDigest() }
        val expectedProofBytes = expectedDistributionProof.readBytes()
        val expectedCompatibilityBytes = expectedSdkCompatibility.readBytes()
        val heldDistribution = temporary.resolve("distribution")
        val heldExecution = temporary.resolve("execution")
        copyReleaseTree(distribution, heldDistribution)
        copyReleaseTree(execution, heldExecution)
        val heldProof = temporary.resolve("caller/verified-distribution-proof.json").also {
            it.parentFile.mkdirs()
            Files.write(it.toPath(), expectedProofBytes)
        }
        val heldCompatibility = temporary.resolve("caller/sdk-compatibility.json").also {
            Files.write(it.toPath(), expectedCompatibilityBytes)
        }
        check(verifiedRegularFiles(heldDistribution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalDistributionDigests &&
            verifiedRegularFiles(heldExecution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalExecutionDigests) {
            "Original Apple private snapshot differs from its inputs"
        }
        verifyOriginalAppleSnapshot(heldDistribution, heldExecution, heldProof, heldCompatibility)
        check(verifiedRegularFiles(heldDistribution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalDistributionDigests &&
            verifiedRegularFiles(heldExecution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalExecutionDigests && heldProof.readBytes().contentEquals(expectedProofBytes) &&
            heldCompatibility.readBytes().contentEquals(expectedCompatibilityBytes)) {
            "Original Apple private snapshot changed during verification"
        }
        inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "original execution recheck") }
        check(verifiedRegularFiles(distribution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalDistributionDigests &&
            verifiedRegularFiles(execution).mapValues { (_, file) -> file.releaseDigest() } ==
            originalExecutionDigests &&
            expectedDistributionProof.readBytes().contentEquals(expectedProofBytes) &&
            expectedSdkCompatibility.readBytes().contentEquals(expectedCompatibilityBytes)) {
            "Original Apple execution inputs changed during verification"
        }
    } finally {
        deleteReleaseTree(temporary)
    }
}

internal fun requireOriginalAppleSnapshotDisjoint(temporary: File, inputs: List<File>) {
    val snapshot = temporary.canonicalFile.toPath()
    check(inputs.map(File::getCanonicalFile).none { input ->
        input.toPath().startsWith(snapshot) || snapshot.startsWith(input.toPath())
    }) { "Original Apple private snapshot overlaps an input" }
}

private fun verifyOriginalAppleSnapshot(
    distribution: File,
    execution: File,
    expectedProof: File,
    expectedCompatibility: File,
) {
    val executionFiles = verifiedRegularFiles(execution)
    check(executionFiles.keys.all { path ->
        path in originalAppleExecutionFiles || originalAppleExecutionRoots.any { path.startsWith("$it/") }
    } && originalAppleExecutionFiles.all(executionFiles::containsKey) &&
        originalAppleExecutionRoots.all { root -> executionFiles.keys.any { it.startsWith("$root/") } }) {
        "Original Apple execution inventory is missing or contains extra files"
    }
    val proofFile = distribution.resolve(IOS_VERIFIED_DISTRIBUTION_PROOF)
    check(Files.mismatch(proofFile.toPath(), expectedProof.toPath()) == -1L) {
        "Original Apple distribution proof differs from the caller expectation"
    }
    val compatibility = execution.resolve("sdk-compatibility.json")
    check(Files.mismatch(compatibility.toPath(), expectedCompatibility.toPath()) == -1L) {
        "Original Apple SDK compatibility differs from the caller expectation"
    }
    val proof = proofFile.readCanonicalOriginalAppleObject("Original Apple distribution proof")
    val version = proof.releaseString("version")
    check(PRODUCT_SEMVER.matches(version)) { "Original Apple distribution version is invalid" }
    val nativeReceipt = distribution.resolve(IOS_ORIGINAL_NATIVE_EVIDENCE_RECEIPT)
    val identity = AppleVerifiedDistributionIdentity(
        proof.releaseString("candidateCommit"), proof.releaseString("candidateTree"), version,
        execution.resolve("source/native-provenance.json").releaseDigest(),
        execution.resolve("source/Package.swift").releaseDigest(), nativeReceipt.releaseDigest(),
        expectedCompatibility.releaseDigest(),
    )
    verifyAppleVerifiedDistribution(distribution, execution.resolve("native-evidence"), identity)

    val canonical = readCrossLanguageCanonicalApiEvidence(
        execution.resolve("canonical/canonical-api.json"),
        execution.resolve("canonical/canonical-coverage.json"),
    )
    val compilerFile = distribution.resolve("reports/cross-language-api/apple/compiler-evidence.json")
    val compiler = compilerFile.readCanonicalOriginalAppleObject("Original Apple compiler evidence")
    val rawSlices = verifyOriginalAppleCompilerRaw(execution.resolve("compiler-raw"), compiler)
    verifyCompilerReportDomains(compiler, rawSlices)

    val xctestFile = distribution.resolve("reports/swift-authentication-tests-summary.json")
    val xctest = xctestFile.readCanonicalOriginalAppleObject("Original Apple XCTest evidence")
    verifyOriginalAppleXCTestRaw(execution.resolve("xctest-raw"), execution, xctest)

    val xcframework = execution.resolve("xcframework")
    val xcresult = execution.resolve("xcresult")
    val xctestPackage = execution.resolve("xctest-package")
    val digests = AppleBindingInputDigests(
        compilerFile.releaseDigest(),
        xcframework.crossLanguageTreeDigest(),
        execution.resolve("consumer/CodexFailureSwiftConsumer.swift").requiredOriginalAppleFileDigest(
            "Swift compiler consumer",
        ),
        execution.resolve("consumer/CodexFailureObjectiveCConsumer.m").requiredOriginalAppleFileDigest(
            "Objective-C compiler consumer",
        ),
        xctestFile.releaseDigest(),
        xcresult.crossLanguageTreeDigest(),
        xctestPackage.crossLanguageTreeDigest(),
        originalAppleBindingTargetDigests(xcframework),
    )
    val derived = deriveCrossLanguageAppleBindingEvidence(canonical, compiler, xctest, digests)
    val bindingFile = distribution.resolve("reports/cross-language-api/apple/binding-evidence.json")
    val retained = bindingFile.readCanonicalOriginalAppleObject("Original Apple binding evidence")
    check(derived == retained) { "Original Apple binding evidence differs from replayed observations" }
    val bindingDigest = bindingFile.releaseDigest()
    mapOf(
        CrossLanguageBinding.SWIFT to "reports/cross-language-api/bindings/swift-parity.json",
        CrossLanguageBinding.OBJECTIVE_C to "reports/cross-language-api/bindings/objective-c-parity.json",
    ).forEach { (language, path) ->
        val expected = buildAppleBindingParityReceipt(derived, language, digests, bindingDigest)
        val actual = readCrossLanguageBindingReceipt(distribution.resolve(path))
        check(actual.toJson() == expected.toJson()) {
            "${language.id} original Apple parity receipt differs from replayed observations"
        }
    }
}

private fun verifyOriginalAppleCompilerRaw(
    raw: File,
    compiler: JsonObject,
): Map<String, OriginalAppleCompilerSliceReplay> {
    val triplet = setOf("execution.json", "stdout.bin", "stderr.bin")
    val expected = buildSet {
        listOf("xcode", "swift", "clang").forEach { tool ->
            triplet.forEach { add("toolchain/$tool/$it") }
        }
        originalAppleCompilerSlices.keys.forEach { slice ->
            listOf(
                "sdk-path", "sdk-version", "swift-symbolgraph", "objective-c-extract-api",
                "swift-consumer-ast", "objective-c-consumer-ast",
            ).forEach { operation -> triplet.forEach { add("$slice/$operation/$it") } }
            add("$slice/swift-symbols/CodexAgent.symbols.json")
            add("$slice/CodexAgent.objc.symbols.json")
        }
    }
    check(verifiedRegularFiles(raw).keys == expected) { "Original Apple compiler raw inventory changed" }
    val compilerToolchain = compiler.releaseObject("toolchain")
    val xcode = raw.verifyOriginalAppleProcess("toolchain/xcode", true)
    val swift = raw.verifyOriginalAppleProcess("toolchain/swift", true)
    val clang = raw.verifyOriginalAppleProcess("toolchain/clang", true)
    check(xcode.releaseCommand() == listOf("/usr/bin/xcodebuild", "-version") &&
        swift.releaseCommand() == listOf("/usr/bin/xcrun", "swift", "--version") &&
        clang.releaseCommand() == listOf("/usr/bin/xcrun", "clang", "--version")) {
        "Original Apple compiler toolchain command changed"
    }
    verifyAppleToolchainOutput(
        raw.resolve("toolchain/xcode/stdout.bin").readStrictUtf8(),
        raw.resolve("toolchain/swift/stdout.bin").readStrictUtf8(),
        compilerToolchain.releaseString("xcodeVersion"), compilerToolchain.releaseString("xcodeBuild"),
        compilerToolchain.releaseString("swiftVersion"),
    )
    val clangLine = raw.resolve("toolchain/clang/stdout.bin").readStrictUtf8()
        .lineSequence().firstOrNull()?.takeIf { it.startsWith("Apple clang version ") }
        ?: error("Original Apple Clang version is missing")
    check(clangLine == compilerToolchain.releaseString("clangVersion")) {
        "Original Apple Clang version changed"
    }

    var frameworkRoot: String? = null
    var swiftConsumer: String? = null
    var objectiveCConsumer: String? = null
    return originalAppleCompilerSlices.mapValues { (slice, specification) ->
        val sdkPathExecution = raw.verifyOriginalAppleProcess("$slice/sdk-path", true)
        val sdkVersionExecution = raw.verifyOriginalAppleProcess("$slice/sdk-version", true)
        check(sdkPathExecution.releaseCommand() ==
            listOf("/usr/bin/xcrun", "--sdk", specification.first, "--show-sdk-path") &&
            sdkVersionExecution.releaseCommand() ==
            listOf("/usr/bin/xcrun", "--sdk", specification.first, "--show-sdk-version")) {
            "Original Apple SDK query command changed: $slice"
        }
        val sdk = File(raw.resolve("$slice/sdk-path/stdout.bin").readStrictUtf8().trim())
        val sdkVersion = raw.resolve("$slice/sdk-version/stdout.bin").readStrictUtf8().trim()
        check(sdk.isAbsolute && sdkVersion.matches(Regex("[0-9]+(?:\\.[0-9]+)*"))) {
            "Original Apple SDK observation is invalid: $slice"
        }
        val swiftGraphExecution = raw.verifyOriginalAppleProcess("$slice/swift-symbolgraph", true)
        val swiftGraphCommand = swiftGraphExecution.releaseCommand()
        val frameworkSearch = swiftGraphCommand.originalAppleArgument("-F", slice)
        val swiftCache = swiftGraphCommand.originalAppleArgument("-module-cache-path", slice)
        val swiftOutput = swiftGraphCommand.originalAppleArgument("-output-dir", slice)
        check(swiftGraphCommand == swiftSymbolGraphCommand(
            specification.second, sdk, File(frameworkSearch), File(swiftCache), File(swiftOutput),
        ) && swiftOutput.normalizedOriginalApplePath().endsWith("/$slice/swift-symbols")) {
            "Original Apple Swift symbolgraph command changed: $slice"
        }
        val objectiveExecution = raw.verifyOriginalAppleProcess("$slice/objective-c-extract-api", true)
        val objectiveCommand = objectiveExecution.releaseCommand()
        val objectiveFramework = objectiveCommand.originalAppleArgument("-F", slice)
        val objectiveCache = objectiveCommand.single { it.startsWith("-fmodules-cache-path=") }
            .substringAfter('=').requiredOriginalAppleAbsolutePath("Objective-C module cache", slice)
        val objectiveOutput = objectiveCommand.originalAppleArgument("-o", slice)
        val objectiveHeader = objectiveCommand[objectiveCommand.indexOf("-o") - 1]
        check(objectiveCommand == objectiveCExtractApiCommand(
            specification.second, sdk, File(objectiveFramework), File(objectiveCache), File(objectiveHeader),
            File(objectiveOutput),
        ) && objectiveOutput.normalizedOriginalApplePath().endsWith("/$slice/CodexAgent.objc.symbols.json") &&
            File(objectiveHeader) == File(frameworkSearch, "CodexAgent.framework/Headers/CodexAgent.h")) {
            "Original Apple Objective-C extract-api command changed: $slice"
        }
        check(frameworkSearch == objectiveFramework &&
            frameworkSearch.normalizedOriginalApplePath().endsWith("/$slice")) {
            "Original Apple compiler framework search path changed: $slice"
        }
        val currentFrameworkRoot = frameworkSearch.normalizedOriginalApplePath().removeSuffix("/$slice")
        check(frameworkRoot == null || frameworkRoot == currentFrameworkRoot) {
            "Original Apple compiler slices use different XCFramework roots"
        }
        frameworkRoot = currentFrameworkRoot

        val swiftAstExecution = raw.verifyOriginalAppleProcess("$slice/swift-consumer-ast", true)
        val swiftAstCommand = swiftAstExecution.releaseCommand()
        val observedSwiftConsumer = swiftAstCommand.last()
        check(swiftAstCommand == swiftConsumerAstCommand(
            specification.second, sdk, File(frameworkSearch),
            File(swiftAstCommand.originalAppleArgument("-module-cache-path", slice)),
            File(observedSwiftConsumer),
        ) && observedSwiftConsumer.normalizedOriginalApplePath().endsWith(
            "/CodexFailureSwiftConsumer.swift",
        ) && (swiftConsumer == null || swiftConsumer == observedSwiftConsumer)) {
            "Original Apple Swift consumer command changed: $slice"
        }
        swiftConsumer = observedSwiftConsumer
        val objectiveAstExecution = raw.verifyOriginalAppleProcess("$slice/objective-c-consumer-ast", true)
        val objectiveAstCommand = objectiveAstExecution.releaseCommand()
        val observedObjectiveConsumer = objectiveAstCommand.last()
        val objectiveAstCache = objectiveAstCommand.single { it.startsWith("-fmodules-cache-path=") }
            .substringAfter('=').requiredOriginalAppleAbsolutePath("Objective-C consumer module cache", slice)
        check(objectiveAstCommand == objectiveCConsumerAstCommand(
            specification.second, sdk, File(frameworkSearch), File(objectiveAstCache), File(observedObjectiveConsumer),
        ) && observedObjectiveConsumer.normalizedOriginalApplePath().endsWith(
            "/CodexFailureObjectiveCConsumer.m",
        ) && (objectiveCConsumer == null || objectiveCConsumer == observedObjectiveConsumer)) {
            "Original Apple Objective-C consumer command changed: $slice"
        }
        objectiveCConsumer = observedObjectiveConsumer

        val swiftSurface = parseSwiftAppleBindingSurface(
            raw.resolve("$slice/swift-symbols/CodexAgent.symbols.json").readStrictUtf8(),
        )
        val objectiveSurface = parseObjectiveCAppleBindingSurface(
            raw.resolve("$slice/CodexAgent.objc.symbols.json").readStrictUtf8(),
        )
        val swiftReferences = parseSwiftAppleBindingReferences(
            raw.resolve("$slice/swift-consumer-ast/stdout.bin").readStrictUtf8(),
        )
        val objectiveReferences = parseObjectiveCAppleBindingReferences(
            raw.resolve("$slice/objective-c-consumer-ast/stdout.bin").readStrictUtf8(),
        )
        OriginalAppleCompilerSliceReplay(
            swiftSurface, objectiveSurface, swiftReferences, objectiveReferences, sdkVersion,
        )
    }
}

private fun verifyCompilerReportDomains(
    compiler: JsonObject,
    slices: Map<String, OriginalAppleCompilerSliceReplay>,
) {
    val values = slices.values.toList()
    check(values.map(OriginalAppleCompilerSliceReplay::swiftSurface).distinct().size == 1 &&
        values.map(OriginalAppleCompilerSliceReplay::objectiveCSurface).distinct().size == 1 &&
        values.map(OriginalAppleCompilerSliceReplay::swiftReferences).distinct().size == 1 &&
        values.map(OriginalAppleCompilerSliceReplay::objectiveCReferences).distinct().size == 1) {
        "Original Apple compiler device and simulator observations differ"
    }
    val surfaces = compiler.releaseObject("surface")
    val references = compiler.releaseObject("references")
    val first = values.first()
    check(surfaces.releaseArray("swift").map { it.appleSymbol() } == first.swiftSurface &&
        surfaces.releaseArray("objectiveC").map { it.appleSymbol() } == first.objectiveCSurface &&
        references.releaseArray("swift").map { it.appleReference() } == first.swiftReferences &&
        references.releaseArray("objectiveC").map { it.appleReference() } == first.objectiveCReferences) {
        "Original Apple compiler report differs from raw compiler observations"
    }
    val targetVersions = compiler.releaseArray("targets").associate { value ->
        val target = value as? JsonObject ?: error("Original Apple compiler target is invalid")
        target.releaseString("name") to target.releaseString("sdkVersion")
    }
    check(targetVersions == slices.mapValues { (_, value) -> value.sdkVersion }) {
        "Original Apple compiler SDK versions differ from raw observations"
    }
}

private fun verifyOriginalAppleXCTestRaw(raw: File, execution: File, retained: JsonObject) {
    val marker = raw.resolve("successful-attempt.json")
        .readCanonicalOriginalAppleObject("Original Apple XCTest successful attempt")
    check(marker.keys == setOf("schemaVersion", "attempt") && marker.releaseInt("schemaVersion") == 1) {
        "Original Apple XCTest successful-attempt record is invalid"
    }
    val successfulAttempt = marker.releaseInt("attempt")
    check(successfulAttempt in 0..1) { "Original Apple XCTest successful attempt is invalid" }
    val triplet = setOf("execution.json", "stdout.bin", "stderr.bin")
    val files = verifiedRegularFiles(raw).keys
    val allowed = buildSet {
        add("successful-attempt.json")
        (0..successfulAttempt).forEach { attempt ->
            listOf("xcodebuild", "summary", "tests").forEach { operation ->
                triplet.forEach { add("attempt-$attempt/$operation/$it") }
            }
        }
    }
    check(files.all { it in allowed }) {
        "Original Apple XCTest raw inventory changed"
    }
    if (successfulAttempt == 0) {
        check(files == allowed) { "Original Apple XCTest successful capture is incomplete" }
    } else {
        val successful = allowed.filter { it.startsWith("attempt-1/") || it == "successful-attempt.json" }.toSet()
        check(files.containsAll(successful)) { "Original Apple XCTest successful capture is incomplete" }
        val operationOrder = listOf("xcodebuild", "summary", "tests")
        val failedOperations = operationOrder.filter { operation ->
            triplet.all { files.contains("attempt-0/$operation/$it") }
        }
        val priorFiles = files.filter { it.startsWith("attempt-0/") }.toSet()
        val expectedPriorFiles = failedOperations.flatMap { operation ->
            triplet.map { "attempt-0/$operation/$it" }
        }.toSet()
        check(failedOperations == operationOrder.take(failedOperations.size) && priorFiles == expectedPriorFiles) {
            "Original Apple XCTest failed-attempt capture is incomplete or out of order"
        }
    }
    val selected = raw.resolve("attempt-$successfulAttempt")
    val xcode = selected.verifyOriginalAppleProcess("xcodebuild", true)
    val summary = selected.verifyOriginalAppleProcess("summary", true)
    val tests = selected.verifyOriginalAppleProcess("tests", true)
    val xcodeCommand = xcode.releaseCommand()
    check(xcodeCommand.size == 11 && xcodeCommand.first() == "xcodebuild" &&
        xcodeCommand[1] == "-scheme" && xcodeCommand[2] == "CodexAgent-Package" &&
        xcodeCommand[3] == "-destination" && xcodeCommand[4].startsWith("platform=iOS Simulator,id=") &&
        xcodeCommand[5] == "-derivedDataPath" && File(xcodeCommand[6]).isAbsolute &&
        xcodeCommand[7] == "-resultBundlePath" && File(xcodeCommand[8]).isAbsolute &&
        xcodeCommand[9] == "CODE_SIGNING_ALLOWED=NO" &&
        xcodeCommand[10] in setOf("test", "test-without-building")) {
        "Original Apple XCTest command changed"
    }
    val destination = xcodeCommand[4].removePrefix("platform=iOS Simulator,id=")
    check(destination.isNotBlank() && xcodeCommand == swiftAuthenticationXcodebuildCommand(
        destination, File(xcodeCommand[6]), File(xcodeCommand[8]), xcodeCommand.last() == "test-without-building",
    ) && xcode.releaseWorkingDirectory().normalizedOriginalApplePath().endsWith("/CodexAgentPackage")) {
        "Original Apple XCTest command identity changed"
    }
    val resultPath = xcodeCommand[8]
    check(resultPath.normalizedOriginalApplePath().endsWith("/swift-authentication-tests.xcresult") &&
        summary.releaseCommand() == listOf(
            "/usr/bin/xcrun", "xcresulttool", "get", "test-results", "summary",
            "--path", resultPath, "--compact",
        ) && tests.releaseCommand() == listOf(
            "/usr/bin/xcrun", "xcresulttool", "get", "test-results", "tests",
            "--path", resultPath, "--compact",
        )) { "Original Apple xcresult query command changed" }
    (0 until successfulAttempt).forEach { attempt ->
        val attemptRoot = raw.resolve("attempt-$attempt")
        val operations = listOf("xcodebuild", "summary", "tests").filter { operation ->
            files.contains("attempt-$attempt/$operation/execution.json")
        }
        val captures = operations.associateWith { operation ->
            attemptRoot.verifyOriginalAppleProcess(operation, false)
        }
        captures["xcodebuild"]?.let { prior ->
            val command = prior.releaseCommand()
            check(command.size == 11 && command[3] == "-destination" &&
                command[4].startsWith("platform=iOS Simulator,id=") &&
                command == swiftAuthenticationXcodebuildCommand(
                    command[4].removePrefix("platform=iOS Simulator,id="),
                    File(xcodeCommand[6]), File(resultPath), xcodeCommand.last() == "test-without-building",
                ) && (prior["workingDirectory"] === JsonNull ||
                prior.releaseWorkingDirectory() == xcode.releaseWorkingDirectory())) {
                "Original Apple prior XCTest command changed"
            }
        }
        captures["summary"]?.let { prior ->
            check(prior.releaseCommand() == summary.releaseCommand() &&
                (prior["workingDirectory"] === JsonNull ||
                    prior.releaseWorkingDirectory() == summary.releaseWorkingDirectory())) {
                "Original Apple prior xcresult summary command changed"
            }
        }
        captures["tests"]?.let { prior ->
            check(prior.releaseCommand() == tests.releaseCommand() &&
                (prior["workingDirectory"] === JsonNull ||
                    prior.releaseWorkingDirectory() == tests.releaseWorkingDirectory())) {
                "Original Apple prior xcresult tests command changed"
            }
        }
        operations.dropLast(1).forEach { operation ->
            check(captures.getValue(operation).releaseExitCodeOrNull() == 0) {
                "Original Apple prior XCTest capture continued after a failed process"
            }
        }
    }
    val parsedSummary = parseSwiftTestSummary(selected.resolve("summary/stdout.bin").readStrictUtf8())
    val parsedTests = parseSwiftTestCaseResults(selected.resolve("tests/stdout.bin").readStrictUtf8())
    verifySwiftTestCaseResults(parsedSummary, parsedTests, expectedAppleTests)
    val reconstructed = swiftTestEvidence(
        parsedSummary, parsedTests, execution.resolve("xcresult").crossLanguageTreeDigest(),
    )
    check(reconstructed == retained) { "Original Apple XCTest evidence differs from raw xcresult observations" }
}

private fun File.verifyOriginalAppleProcess(path: String, requireSuccess: Boolean): JsonObject {
    val capture = resolve(path)
    check(verifiedRegularFiles(capture).keys == setOf("execution.json", "stdout.bin", "stderr.bin")) {
        "Original Apple process capture inventory changed: $path"
    }
    val execution = capture.resolve("execution.json")
        .readCanonicalOriginalAppleObject("Original Apple process execution")
    check(execution.keys == setOf("schemaVersion", "command", "workingDirectory", "environment", "exitCode") &&
        execution.releaseInt("schemaVersion") == 1 && execution.releaseCommand().isNotEmpty()) {
        "Original Apple process execution schema changed: $path"
    }
    val environment = execution.releaseObject("environment")
    check(environment == JsonObject(mapOf("LC_ALL" to JsonPrimitive("C"), "LANG" to JsonPrimitive("C")))) {
        "Original Apple process environment changed: $path"
    }
    val workingDirectory = execution["workingDirectory"]
    if (requireSuccess || workingDirectory !== JsonNull) execution.releaseWorkingDirectory()
    val exit = execution["exitCode"]
    check(if (requireSuccess) {
        exit is JsonPrimitive && !exit.isString && exit.intOrNull == 0
    } else {
        exit === JsonNull || exit is JsonPrimitive && !exit.isString && exit.intOrNull != null
    }) { "Original Apple process result changed: $path" }
    return execution
}

private fun JsonObject.releaseCommand(): List<String> = releaseArray("command").map { value ->
    val primitive = value as? JsonPrimitive ?: error("Original Apple process command contains a non-string")
    check(primitive.isString && primitive.content.isNotBlank() && primitive.content.none(Char::isISOControl)) {
        "Original Apple process command contains an invalid argument"
    }
    primitive.content
}

private fun JsonObject.releaseWorkingDirectory(): String {
    val value = this["workingDirectory"] as? JsonPrimitive
        ?: error("Original Apple process working directory is missing")
    check(value.isString && File(value.content).isAbsolute &&
        value.content == value.content.normalizedOriginalApplePath()) {
        "Original Apple process working directory is invalid"
    }
    return value.content
}

private fun JsonObject.releaseExitCodeOrNull(): Int? {
    val value = this["exitCode"]
    if (value === JsonNull) return null
    val primitive = value as? JsonPrimitive ?: error("Original Apple process result is invalid")
    check(!primitive.isString && primitive.intOrNull != null) { "Original Apple process result is invalid" }
    return primitive.intOrNull
}

private fun List<String>.originalAppleArgument(name: String, slice: String): String {
    val indices = indices.filter { this[it] == name }
    check(indices.size == 1 && indices.single() + 1 < size) {
        "Original Apple compiler argument changed for $slice: $name"
    }
    return get(indices.single() + 1).requiredOriginalAppleAbsolutePath(name, slice)
}

private fun String.requiredOriginalAppleAbsolutePath(label: String, context: String): String = also { value ->
    check(File(value).isAbsolute && value == value.normalizedOriginalApplePath()) {
        "Original Apple path is invalid for $context: $label"
    }
}

private fun String.normalizedOriginalApplePath(): String = File(this).toPath().normalize().toString()
    .replace(File.separatorChar, '/')

private fun File.readCanonicalOriginalAppleObject(label: String): JsonObject {
    check(isFile && !Files.isSymbolicLink(toPath())) { "$label is missing or unsafe" }
    val contents = readStrictUtf8()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject ?: error("$label is not a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "$label is not canonically encoded"
    }
    return root
}

private fun File.readStrictUtf8(): String {
    check(isFile && !Files.isSymbolicLink(toPath())) { "Original Apple evidence file is missing or unsafe: $this" }
    val bytes = readBytes()
    return Charsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString()
}

private fun File.requiredOriginalAppleFileDigest(label: String): String {
    check(isFile && !Files.isSymbolicLink(toPath()) && length() > 0L) { "$label is missing, empty, or unsafe" }
    return releaseDigest()
}

private fun originalAppleBindingTargetDigests(xcframework: File): Map<String, AppleBindingTargetDigests> =
    originalAppleCompilerSlices.keys.associateWith { slice ->
        val framework = xcframework.resolve("$slice/CodexAgent.framework")
        val binary = framework.resolve("CodexAgent")
        val header = framework.resolve("Headers/CodexAgent.h")
        val moduleMap = framework.resolve("Modules/module.modulemap")
        listOf(binary, header, moduleMap).forEach { it.requiredOriginalAppleFileDigest("Apple binding artifact") }
        AppleBindingTargetDigests(
            framework.crossLanguageTreeDigest(), binary.releaseDigest(), header.releaseDigest(), moduleMap.releaseDigest(),
        )
    }
