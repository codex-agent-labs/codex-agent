import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

internal const val NATIVE_WRAPPER_CLAIM_HEADER =
    "capabilityKey\tpublicSymbols\texecutedTests\tcompilerEvidenceIds\tsharedScenarios"
internal const val NATIVE_WRAPPER_COMPILER_HEADER = "compilerEvidenceId\tpublicSymbols"
internal const val NATIVE_WRAPPER_TEST_HEADER = "executedTestId\tstatus"
internal const val NATIVE_WRAPPER_HOST_CONSUMER_HEADER =
    "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus"
private const val NATIVE_WRAPPER_HOST_EVIDENCE_KIND = "cross-language-host-consumer"
private const val NATIVE_WRAPPER_PACKAGE_KIND = "native-wrapper-package"

internal data class CrossLanguageNativeWrapperClaim(
    val capabilityKey: String,
    val publicSymbols: List<String>,
    val executedTests: List<String>,
    val compilerEvidenceIds: List<String>,
    val sharedScenarios: List<CrossLanguageBindingScenario>,
)

internal data class CrossLanguageNativeWrapperCompilerEvidence(
    val evidenceId: String,
    val publicSymbols: List<String>,
)

private data class CrossLanguageNativeWrapperHostConsumerEvidence(
    val classifier: String,
    val packageArtifactId: String,
    val packageSha256: String,
    val nativeLibrarySha256: String,
    val testId: String,
)

private data class CrossLanguageNativeWrapperLaneIdentity(
    val runnerOs: String,
    val runnerArch: String,
    val toolchainIdentitySha256: String,
    val candidateCommit: String,
    val candidateTree: String,
)

internal data class CrossLanguageNativeWrapperEvidenceInput(
    val phase: CrossLanguageBindingPhase,
    val language: CrossLanguageBinding,
    val apiReport: File,
    val canonicalCoverageReceipt: File,
    val cAbiBootstrapEvidence: File,
    val claims: File,
    val compilerEvidence: File,
    val testProgram: File,
    val testResults: File,
    val packageArtifacts: Map<String, File>,
    val hostEvidenceDirectory: File,
    val stagedCAbiSdks: File,
)

@CacheableTask
internal abstract class GenerateCrossLanguageNativeWrapperBindingReceiptTask : DefaultTask() {
    @get:Input
    abstract val phase: Property<String>

    @get:Input
    abstract val language: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val cAbiBootstrapEvidence: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val claims: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val compilerEvidence: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val testProgram: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val testResults: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageArtifacts: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val hostEvidenceDirectory: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stagedCAbiSdks: DirectoryProperty

    @get:OutputFile
    abstract val receipt: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = receipt.get().asFile
        Files.deleteIfExists(output.toPath())
        val phaseValue = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phase.get() }
            ?: error("Unknown native wrapper binding phase: ${phase.get()}")
        val languageValue = CrossLanguageBinding.entries.singleOrNull { it.id == language.get() }
            ?: error("Unknown native wrapper binding language: ${language.get()}")
        val packages = nativeWrapperPackageArtifacts(languageValue, packageArtifacts.get().asFile)
        val expected = deriveCrossLanguageNativeWrapperBindingReceipt(
            CrossLanguageNativeWrapperEvidenceInput(
                phase = phaseValue,
                language = languageValue,
                apiReport = apiReport.get().asFile,
                canonicalCoverageReceipt = canonicalCoverageReceipt.get().asFile,
                cAbiBootstrapEvidence = cAbiBootstrapEvidence.get().asFile,
                claims = claims.get().asFile,
                compilerEvidence = compilerEvidence.get().asFile,
                testProgram = testProgram.get().asFile,
                testResults = testResults.get().asFile,
                packageArtifacts = packages,
                hostEvidenceDirectory = hostEvidenceDirectory.get().asFile,
                stagedCAbiSdks = stagedCAbiSdks.get().asFile,
            ),
        )
        writeCrossLanguageBindingReceipt(output, expected)
        check(readCrossLanguageBindingReceipt(output).toJson() == expected.toJson()) {
            "Native wrapper binding receipt does not match freshly recomputed evidence"
        }
    }
}

internal fun nativeWrapperPackageArtifacts(
    language: CrossLanguageBinding,
    packageRoot: File,
): Map<String, File> = verifiedRegularFiles(packageRoot).mapKeys { (path, _) ->
    "${language.id}-package/$path"
}

@CacheableTask
internal abstract class AdvanceCrossLanguageBindingReceiptPhaseTask : DefaultTask() {
    @get:Input
    abstract val phase: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val sourceReceipt: RegularFileProperty

    @get:OutputFile
    abstract val receipt: RegularFileProperty

    @TaskAction
    fun advance() {
        val output = receipt.get().asFile
        Files.deleteIfExists(output.toPath())
        val phaseValue = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phase.get() }
            ?: error("Unknown carried binding phase: ${phase.get()}")
        advanceCrossLanguageBindingReceiptPhase(sourceReceipt.get().asFile, phaseValue, output)
    }
}

internal fun advanceCrossLanguageBindingReceiptPhase(
    source: File,
    phase: CrossLanguageBindingPhase,
    output: File,
): CrossLanguageBindingReceipt {
    check(source.canonicalFile != output.canonicalFile) { "Carried binding receipt output must be distinct" }
    val original = readCrossLanguageBindingReceipt(source)
    check(original.phase.ordinal <= phase.ordinal && original.language.isActive(phase)) {
        "Cannot carry ${original.language.id} receipt from ${original.phase.name} to ${phase.name}"
    }
    val advanced = original.copy(phase = phase)
    writeCrossLanguageBindingReceipt(output, advanced)
    return readCrossLanguageBindingReceipt(output).also { actual ->
        check(actual.toJson() == advanced.toJson()) { "Carried binding receipt does not match its source evidence" }
    }
}

internal fun deriveCrossLanguageNativeWrapperBindingReceipt(
    input: CrossLanguageNativeWrapperEvidenceInput,
): CrossLanguageBindingReceipt {
    check(input.language in nativeWrapperBindings && input.language.isActive(input.phase)) {
        "Native wrapper evidence language is inactive or not a native wrapper"
    }
    val canonical = readCrossLanguageCanonicalApiEvidence(input.apiReport, input.canonicalCoverageReceipt)
    val cAbiBootstrap = readCAbiBootstrapEvidence(input.cAbiBootstrapEvidence)
    val claims = readCrossLanguageNativeWrapperClaims(input.claims)
    val compilerEvidence = readCrossLanguageNativeWrapperCompilerEvidence(input.compilerEvidence)
    val testResults = readCrossLanguageNativeWrapperTestResults(input.testResults)
    val stagedCAbiSdks = readCrossLanguageNativeWrapperSdkIndex(input.stagedCAbiSdks)
    val (hostConsumerProofs, hostArtifacts) = deriveCrossLanguageNativeWrapperHostConsumerProofs(
        input,
        stagedCAbiSdks,
    )

    check(claims.map(CrossLanguageNativeWrapperClaim::capabilityKey) == canonical.memberKeys.sorted()) {
        "${input.language.id} wrapper claims do not exactly match the canonical capability inventory"
    }
    check(cAbiBootstrap.apiReportSha256 == canonical.canonical.apiReportSha256 &&
        cAbiBootstrap.coverageReceiptSha256 == canonical.canonical.coverageReceiptSha256 &&
        cAbiBootstrap.observedCapabilityKeys == canonical.memberKeys.sorted() &&
        cAbiBootstrap.missingCapabilityKeys.isEmpty()) {
        "${input.language.id} C ABI reference evidence does not match the canonical capability inventory"
    }
    val cAbiClaims = cAbiBootstrap.claims.associateBy(CAbiBindingBootstrapClaim::capabilityKey)
    check(cAbiClaims.size == claims.size && cAbiClaims.keys == claims.mapTo(mutableSetOf()) { it.capabilityKey }) {
        "${input.language.id} C ABI reference claim inventory is incomplete or duplicated"
    }
    val passedCAbiTests = cAbiBootstrap.nativeTests.filter {
        it.status == CrossLanguageBindingTestStatus.PASSED
    }.mapTo(mutableSetOf(), CAbiBindingBootstrapTest::testId)
    val compilerById = compilerEvidence.associateBy(CrossLanguageNativeWrapperCompilerEvidence::evidenceId)
    val passedTests = testResults.toSet()
    val usedCompilerEvidence = claims.flatMap(CrossLanguageNativeWrapperClaim::compilerEvidenceIds)
    val usedTests = claims.flatMap(CrossLanguageNativeWrapperClaim::executedTests)
    claims.forEach { claim ->
        requireExactNativeWrapperReferenceEvidence(claim, cAbiClaims.getValue(claim.capabilityKey), passedCAbiTests)
        val provenSymbols = claim.compilerEvidenceIds.flatMap { evidenceId ->
            compilerById[evidenceId]?.publicSymbols
                ?: error("${input.language.id} claim ${claim.capabilityKey} references stale compiler evidence $evidenceId")
        }.toSet()
        check(claim.publicSymbols.all(provenSymbols::contains)) {
            "${input.language.id} claim ${claim.capabilityKey} lacks exact compiler evidence"
        }
        check(claim.executedTests.all(passedTests::contains)) {
            "${input.language.id} claim ${claim.capabilityKey} references a missing or non-passed test"
        }
    }
    check(usedCompilerEvidence.toSet() == compilerById.keys) {
        "${input.language.id} compiler evidence is missing or unclaimed"
    }
    check(usedTests.toSet() == passedTests) {
        "${input.language.id} executed test evidence is missing or unclaimed"
    }
    val scenarios = CrossLanguageBindingScenario.entries.map { scenario ->
        CrossLanguageScenarioEvidence(
            input.language,
            scenario,
            claims.filter { scenario in it.sharedScenarios }
                .flatMap(CrossLanguageNativeWrapperClaim::executedTests)
                .distinct()
                .sorted()
                .also { check(it.isNotEmpty()) { "Missing ${input.language.id} scenario ${scenario.id}" } },
        )
    }
    val artifacts = buildList {
        add(CrossLanguageBindingArtifactIdentity("${input.language.id}-claims", input.claims.releaseDigest()))
        add(CrossLanguageBindingArtifactIdentity(
            "${input.language.id}-compiler-evidence",
            input.compilerEvidence.releaseDigest(),
        ))
        add(CrossLanguageBindingArtifactIdentity(
            "c-abi-bootstrap-reference",
            input.cAbiBootstrapEvidence.releaseDigest(),
        ))
        input.packageArtifacts.toSortedMap().forEach { (id, file) ->
            requireNativeWrapperEvidenceFile(file, "package artifact $id")
            add(CrossLanguageBindingArtifactIdentity(id, file.releaseDigest()))
        }
        addAll(hostArtifacts)
        add(CrossLanguageBindingArtifactIdentity(
            "native-wrapper-c-abi-sdk-index",
            input.stagedCAbiSdks.resolve("codex-agent-native-wrapper-sdks.json").releaseDigest(),
        ))
    }
    check(input.packageArtifacts.isNotEmpty()) { "Native wrapper package artifact inventory is empty" }
    requireNativeWrapperEvidenceFile(input.testProgram, "test program")

    return CrossLanguageBindingReceipt(
        phase = input.phase,
        language = input.language,
        canonical = canonical.canonical,
        artifacts = artifacts,
        testProgramSha256 = input.testProgram.releaseDigest(),
        testResultsSha256 = input.testResults.releaseDigest(),
        publicSymbols = compilerEvidence.flatMap(CrossLanguageNativeWrapperCompilerEvidence::publicSymbols)
            .distinct()
            .sorted(),
        bindingTests = testResults.map { testId ->
            CrossLanguageBindingTestEvidence(
                input.language,
                testId,
                CrossLanguageBindingTestStatus.PASSED,
            )
        },
        scenarioEvidence = scenarios,
        projectionClaims = claims.map { claim ->
            CrossLanguageProjectionClaim(
                capabilityKey = claim.capabilityKey,
                language = input.language,
                publicSymbols = claim.publicSymbols,
                executedTests = claim.executedTests,
                sharedScenarios = claim.sharedScenarios,
            )
        },
        applicabilityExclusions = emptyList(),
        hostConsumerProofs = hostConsumerProofs,
    )
}

private fun deriveCrossLanguageNativeWrapperHostConsumerProofs(
    input: CrossLanguageNativeWrapperEvidenceInput,
    stagedSdkIndex: CrossLanguageNativeWrapperSdkIndex,
): Pair<List<CrossLanguageBindingHostConsumerProof>, List<CrossLanguageBindingArtifactIdentity>> {
    val specsByClassifier = crossLanguageCAbiTargetSpecs.values.associateBy {
        it.classifier.removePrefix("c-abi-")
    }
    val expectedFiles = specsByClassifier.keys.flatMap { classifier ->
        listOf("$classifier.tsv", "$classifier-lane-receipt.json")
    }.toSet()
    val files = verifiedRegularFiles(input.hostEvidenceDirectory)
    check(files.keys == expectedFiles) {
        "Native wrapper host evidence requires exactly one TSV and lane receipt for all five classifiers"
    }
    val sdkByClassifier = stagedSdkIndex.records.values.associateBy(
        CrossLanguageNativeWrapperSdkRecord::classifier,
    )
    val artifacts = mutableListOf<CrossLanguageBindingArtifactIdentity>()
    val proofs = specsByClassifier.toSortedMap().map { (classifier, spec) ->
        val evidenceFile = files.getValue("$classifier.tsv")
        val laneReceiptFile = files.getValue("$classifier-lane-receipt.json")
        val evidence = readCrossLanguageNativeWrapperHostConsumerEvidence(evidenceFile)
        check(evidence.classifier == classifier) {
            "Native wrapper host evidence classifier mismatch: $classifier"
        }
        val packageFile = input.packageArtifacts[evidence.packageArtifactId]
            ?: error("Native wrapper host evidence references unknown package ${evidence.packageArtifactId}")
        requireNativeWrapperEvidenceFile(packageFile, "host package ${evidence.packageArtifactId}")
        check(packageFile.releaseDigest() == evidence.packageSha256) {
            "Native wrapper host package hash mismatch: $classifier"
        }
        val sdk = sdkByClassifier[classifier]
            ?: error("Native wrapper staged SDK is missing classifier $classifier")
        check(sdk.librarySha256 == evidence.nativeLibrarySha256) {
            "Native wrapper host native-library hash mismatch: $classifier"
        }
        val lane = readCrossLanguageNativeWrapperLaneIdentity(
            laneReceiptFile,
            input.language,
            classifier,
            spec,
            evidenceFile,
            evidence.packageSha256,
            stagedSdkIndex,
        )
        artifacts += CrossLanguageBindingArtifactIdentity(
            "${input.language.id}-host-consumer-$classifier",
            evidenceFile.releaseDigest(),
        )
        artifacts += CrossLanguageBindingArtifactIdentity(
            "${input.language.id}-host-lane-receipt-$classifier",
            laneReceiptFile.releaseDigest(),
        )
        CrossLanguageBindingHostConsumerProof(
            classifier = classifier,
            runnerOs = lane.runnerOs,
            runnerArch = lane.runnerArch,
            toolchainIdentitySha256 = lane.toolchainIdentitySha256,
            packageArtifactId = evidence.packageArtifactId,
            packageSha256 = evidence.packageSha256,
            nativeLibrarySha256 = evidence.nativeLibrarySha256,
            testId = evidence.testId,
            status = CrossLanguageBindingTestStatus.PASSED,
            candidateCommit = lane.candidateCommit,
            candidateTree = lane.candidateTree,
        )
    }
    return proofs to artifacts.sortedBy(CrossLanguageBindingArtifactIdentity::id)
}

private fun readCrossLanguageNativeWrapperHostConsumerEvidence(
    file: File,
): CrossLanguageNativeWrapperHostConsumerEvidence {
    val rows = readNativeWrapperTsv(file, NATIVE_WRAPPER_HOST_CONSUMER_HEADER, 6)
    check(rows.size == 1) { "Native wrapper host consumer TSV must contain exactly one result" }
    val columns = rows.single()
    check(columns[2].matches(Regex("[0-9a-f]{64}")) && columns[3].matches(Regex("[0-9a-f]{64}"))) {
        "Native wrapper host consumer hashes are invalid"
    }
    check(columns[5] == "passed") { "Native wrapper host consumer did not pass: ${columns[0]}" }
    return CrossLanguageNativeWrapperHostConsumerEvidence(
        classifier = columns[0],
        packageArtifactId = columns[1],
        packageSha256 = columns[2],
        nativeLibrarySha256 = columns[3],
        testId = columns[4],
    )
}

private fun readCrossLanguageNativeWrapperLaneIdentity(
    file: File,
    language: CrossLanguageBinding,
    classifier: String,
    spec: CrossLanguageCAbiTargetSpec,
    hostEvidence: File,
    packageSha256: String,
    stagedSdkIndex: CrossLanguageNativeWrapperSdkIndex,
): CrossLanguageNativeWrapperLaneIdentity {
    requireNativeWrapperEvidenceFile(file, "host lane receipt $classifier")
    val root = releaseJson.parseToJsonElement(file.readText()).jsonObject
    check(root.keys == setOf(
        "schemaVersion", "repository", "workflowPath", "event", "runId", "runAttempt", "pullRequest",
        "baseCommit", "headCommit", "validationCommit", "validationTree", "lane", "artifactName", "runner",
        "toolchain", "inputFiles", "artifacts", "evidence", "result",
    ) && root.nativeWrapperExactInt("schemaVersion") == 2 &&
        root.nativeWrapperExactString("workflowPath") == ".github/workflows/ci.yml" &&
        root.nativeWrapperExactString("result") == "passed") {
        "Native wrapper host lane receipt schema or result mismatch: $classifier"
    }
    val expectedLane = "desktop-$classifier"
    check(root.nativeWrapperExactString("lane") == expectedLane &&
        root.nativeWrapperExactString("artifactName").startsWith("codex-agent-ci-$expectedLane-") &&
        root.nativeWrapperExactString("validationCommit") == stagedSdkIndex.producerCommit &&
        root.nativeWrapperExactString("validationTree") == stagedSdkIndex.producerTree) {
        "Native wrapper host lane candidate identity mismatch: $classifier"
    }
    val runner = root.nativeWrapperExactObject("runner")
    check(runner.keys == setOf("os", "arch", "image", "imageVersion") &&
        runner.nativeWrapperExactString("os") == spec.runnerOs &&
        runner.nativeWrapperExactString("arch") == spec.runnerArch &&
        runner.values.all { it.jsonPrimitive.isString && it.jsonPrimitive.content.isExactNativeWrapperRecord() }) {
        "Native wrapper host runner identity mismatch: $classifier"
    }
    val toolchain = root.nativeWrapperExactObject("toolchain")
    check(toolchain.isNotEmpty() && toolchain.values.all {
        it.jsonPrimitive.isString && it.jsonPrimitive.content.isExactNativeWrapperRecord()
    }) { "Native wrapper host toolchain identity is malformed: $classifier" }
    val validationActions = toolchain.nativeWrapperExactString("validationActions").split(',')
    check(validationActions == validationActions.distinct().sorted() && "test" in validationActions) {
        "Native wrapper host lane did not execute tests: $classifier"
    }
    val requiredToolchain = when (language) {
        CrossLanguageBinding.PYTHON -> setOf("python")
        CrossLanguageBinding.CSHARP -> setOf("dotnet")
        CrossLanguageBinding.RUST -> setOf("cargo", "rustc")
        CrossLanguageBinding.CPP -> setOf("cmake", "cppCompiler")
        CrossLanguageBinding.DART -> setOf("dart")
        else -> error("Unsupported native wrapper host toolchain language: ${language.id}")
    }
    val selectedToolchain = requiredToolchain.sorted().associateWith { id ->
        toolchain.nativeWrapperExactString(id).also { value ->
            check(value != "unavailable") { "Native wrapper host toolchain is unavailable: $id/$classifier" }
        }
    }
    requireDeclaredNativeWrapperLaneEvidence(root, hostEvidence.releaseDigest(), NATIVE_WRAPPER_HOST_EVIDENCE_KIND)
    requireDeclaredNativeWrapperLaneArtifact(root, packageSha256, NATIVE_WRAPPER_PACKAGE_KIND)
    val toolchainBytes = selectedToolchain.entries.joinToString(separator = "", transform = { (id, value) ->
        "$id=$value\n"
    })
    return CrossLanguageNativeWrapperLaneIdentity(
        runnerOs = spec.runnerOs,
        runnerArch = spec.runnerArch,
        toolchainIdentitySha256 = toolchainBytes.byteInputStream().releaseDigest(),
        candidateCommit = root.nativeWrapperExactString("validationCommit"),
        candidateTree = root.nativeWrapperExactString("validationTree"),
    )
}

private fun requireDeclaredNativeWrapperLaneEvidence(root: JsonObject, sha256: String, kind: String) {
    val matches = root.nativeWrapperExactArray("evidence").map(JsonElement::jsonObject).filter { record ->
        check(record.keys == setOf("relativePath", "kind", "sha256")) {
            "Native wrapper host lane evidence record schema mismatch"
        }
        record.nativeWrapperExactString("sha256") == sha256 && record.nativeWrapperExactString("kind") == kind
    }
    check(matches.size == 1) { "Native wrapper host evidence is not exactly declared by its lane receipt" }
}

private fun requireDeclaredNativeWrapperLaneArtifact(root: JsonObject, sha256: String, kind: String) {
    val matches = root.nativeWrapperExactArray("artifacts").map(JsonElement::jsonObject).filter { record ->
        check(record.keys == setOf("relativePath", "kind", "bytes", "sha256")) {
            "Native wrapper host lane artifact record schema mismatch"
        }
        record.nativeWrapperExactLong("bytes") >= 0 &&
            record.nativeWrapperExactString("sha256") == sha256 && record.nativeWrapperExactString("kind") == kind
    }
    check(matches.size == 1) { "Native wrapper host package is not exactly declared by its lane receipt" }
}

private fun JsonObject.nativeWrapperExactString(name: String): String = getValue(name).jsonPrimitive.also {
    check(it.isString) { "Native wrapper host lane field is not a string: $name" }
}.content

private fun JsonObject.nativeWrapperExactInt(name: String): Int = getValue(name).jsonPrimitive.also {
    check(!it.isString) { "Native wrapper host lane field is not an integer: $name" }
}.content.toInt()

private fun JsonObject.nativeWrapperExactLong(name: String): Long = getValue(name).jsonPrimitive.also {
    check(!it.isString) { "Native wrapper host lane field is not an integer: $name" }
}.content.toLong()

private fun JsonObject.nativeWrapperExactObject(name: String): JsonObject = getValue(name).jsonObject
private fun JsonObject.nativeWrapperExactArray(name: String): JsonArray = getValue(name).jsonArray

private fun requireExactNativeWrapperReferenceEvidence(
    claim: CrossLanguageNativeWrapperClaim,
    cAbiClaim: CAbiBindingBootstrapClaim,
    passedCAbiTests: Set<String>,
) {
    val header = claim.compilerEvidenceIds.filter { it.startsWith("c-header:") }
        .map { it.removePrefix("c-header:") }
    val fixtures = claim.compilerEvidenceIds.filter { it.startsWith("cabi-fixture:") }
        .map { it.removePrefix("cabi-fixture:") }
    val enumCompilerEvidence = claim.compilerEvidenceIds.filter { "header-enum:" in it }
    if ("|kind=enum-entry|" in claim.capabilityKey) {
        check(enumCompilerEvidence.size == 1 && header.isEmpty() && fixtures.isEmpty() &&
            enumCompilerEvidence.single().substringAfterLast(':').toIntOrNull() != null) {
            "${claim.capabilityKey} requires one exact compiled enum-header reference"
        }
    } else {
        check(enumCompilerEvidence.isEmpty() && header == cAbiClaim.headerReferences &&
            fixtures == cAbiClaim.nativeTestIds && fixtures.all(passedCAbiTests::contains)) {
            "${claim.capabilityKey} does not exactly resolve its reviewed header and passed C ABI references"
        }
    }
}

internal fun readCrossLanguageNativeWrapperClaims(file: File): List<CrossLanguageNativeWrapperClaim> =
    readNativeWrapperTsv(file, NATIVE_WRAPPER_CLAIM_HEADER, 5).map { columns ->
        CrossLanguageNativeWrapperClaim(
            capabilityKey = columns[0],
            publicSymbols = columns[1].exactNativeWrapperList("claim public symbols"),
            executedTests = columns[2].exactNativeWrapperList("claim executed tests"),
            compilerEvidenceIds = columns[3].exactNativeWrapperList("claim compiler evidence"),
            sharedScenarios = columns[4].exactNativeWrapperList("claim scenarios").map { id ->
                CrossLanguageBindingScenario.entries.singleOrNull { it.id == id }
                    ?: error("Unknown native wrapper scenario: $id")
            },
        )
    }.also { claims ->
        requireSortedUnique(claims.map(CrossLanguageNativeWrapperClaim::capabilityKey), "native wrapper capability")
    }

internal fun readCrossLanguageNativeWrapperCompilerEvidence(
    file: File,
): List<CrossLanguageNativeWrapperCompilerEvidence> =
    readNativeWrapperTsv(file, NATIVE_WRAPPER_COMPILER_HEADER, 2).map { columns ->
        CrossLanguageNativeWrapperCompilerEvidence(
            columns[0],
            columns[1].exactNativeWrapperList("compiler public symbols"),
        )
    }.also { evidence ->
        requireSortedUnique(
            evidence.map(CrossLanguageNativeWrapperCompilerEvidence::evidenceId),
            "native wrapper compiler evidence",
        )
    }

internal fun readCrossLanguageNativeWrapperTestResults(file: File): List<String> =
    readNativeWrapperTsv(file, NATIVE_WRAPPER_TEST_HEADER, 2).map { columns ->
        check(columns[1] == "passed") { "Native wrapper test ${columns[0]} did not pass" }
        columns[0]
    }.also { tests -> requireSortedUnique(tests, "native wrapper executed test") }

private fun readNativeWrapperTsv(file: File, header: String, columnCount: Int): List<List<String>> {
    requireNativeWrapperEvidenceFile(file, "TSV evidence")
    val contents = file.readText()
    check(contents.endsWith('\n') && '\r' !in contents) { "Native wrapper TSV must use canonical LF encoding" }
    val lines = contents.dropLast(1).split('\n')
    check(lines.firstOrNull() == header && lines.size > 1) { "Invalid or empty native wrapper TSV: $file" }
    return lines.drop(1).map { line ->
        line.split('\t').also { columns ->
            check(columns.size == columnCount && columns.all(String::isExactNativeWrapperRecord)) {
                "Malformed native wrapper TSV row: $line"
            }
        }
    }
}

private fun String.exactNativeWrapperList(label: String): List<String> = split(',').also { values ->
    check(values.all(String::isExactNativeWrapperRecord) && values == values.distinct().sorted()) {
        "$label must be a sorted unique exact inventory"
    }
}

private fun String.isExactNativeWrapperRecord(): Boolean =
    isNotBlank() && this == trim() && '*' !in this && none(Char::isISOControl)

private fun requireSortedUnique(values: List<String>, label: String) {
    check(values.isNotEmpty() && values == values.distinct().sorted()) {
        "$label inventory must be nonempty, sorted, and unique"
    }
}

private fun requireNativeWrapperEvidenceFile(file: File, label: String) {
    check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
        "Native wrapper $label is missing, empty, non-regular, or a symlink: $file"
    }
}
