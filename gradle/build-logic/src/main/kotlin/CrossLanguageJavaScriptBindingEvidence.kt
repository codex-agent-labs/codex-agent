import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import org.w3c.dom.Element

internal const val JAVASCRIPT_CANONICAL_CAPABILITY_COUNT = 556
internal const val JAVASCRIPT_NPM_PACKAGE = "@${CodexAgentBuild.REPOSITORY}"

private const val packedSurfaceTest = "cjs exposes the exact Node-only SDK surface"
private const val packedLifecycleTest = "cjs projects lifecycle state failure cleanup and terminal delivery"
private const val packedCancellationTest = "cjs maps AbortSignal cancellation without starting"
private const val packedEsmTest = "esm exposes the same runtime values as CommonJS"
private const val packedCompilerTest = "typescript compiler discovers the exact installed public API"
private const val jsNodeTestClass = "jsNodeTest.CodexNodeApiTest"
private const val jsLifecycleTest =
    "$jsNodeTestClass#projectsCanonicalLifecycleIdentityFailureAndOwnership[js, node]"
private const val jsAbortBeforeStartTest =
    "$jsNodeTestClass#abortsBeforeStartingAndStopsDisposedObservation[js, node]"
private const val jsCancellationTest =
    "$jsNodeTestClass#mapsCanonicalCancellationAndRemovesAbortListener[js, node]"
private const val jsListenerFailureTest =
    "$jsNodeTestClass#isolatesListenerFailureWhileOtherObserversAndCleanupContinue[js, node]"
private const val jsAuthenticationTest =
    "$jsNodeTestClass#projectsAuthenticationStateMethodsIdentityAndDisposal[js, node]"
private const val jsAuthenticationFailureTest =
    "$jsNodeTestClass#mapsAuthenticationFailureAndAbortSignalCancellation[js, node]"

private val requiredPackedBindingTests = setOf(
    packedSurfaceTest,
    packedLifecycleTest,
    packedCancellationTest,
    packedEsmTest,
    packedCompilerTest,
)

private val requiredJsNodeBindingTests = setOf(
    jsLifecycleTest,
    jsAbortBeforeStartTest,
    jsCancellationTest,
    jsListenerFailureTest,
    jsAuthenticationTest,
    jsAuthenticationFailureTest,
)

private val requiredJavaScriptConsumerProgramFiles = setOf(
    "package-lock.json",
    "package.json",
    "negative.ts",
    "smoke.cjs",
    "smoke.mjs",
    "smoke.ts",
    "tsconfig.json",
)

private val requiredJavaScriptArtifactIds =
    listOf("commonJs", "declaration", "esm", "packageJson", "tarball")

/** Compiler-derived npm public surface. Schema 2 adds exact consumer references. */
internal data class JavaScriptPackedArtifact(
    val id: String,
    val fileName: String,
    val bytes: Long,
    val sha256: String,
)

internal data class JavaScriptPackedPublicApiEvidence(
    val schema: Int,
    val packageName: String,
    val packageVersion: String,
    val artifacts: List<JavaScriptPackedArtifact>,
    val typeExports: List<String>,
    val valueExports: List<String>,
    val commonJsExports: List<String>,
    val esmExports: List<String>,
    val publicSymbols: List<String>,
    val referencedSymbols: List<String>,
    val compilerTestId: String,
)

internal data class CrossLanguageJavaScriptBindingEvidence(
    val canonical: CrossLanguageCanonicalApiEvidence,
    val packedApi: JavaScriptPackedPublicApiEvidence,
    val projectionClaims: List<CrossLanguageProjectionClaim>,
    val applicabilityExclusions: List<CrossLanguageApplicabilityExclusion>,
    val missingCapabilityKeys: List<String>,
    val errors: List<String>,
)

internal data class CrossLanguageJavaScriptBindingFiles(
    val apiReport: File,
    val canonicalCoverageReceipt: File,
    val packedPublicApiReport: File,
    val npmTarball: File,
    val installedPackageDirectory: File,
    val consumerSourceDirectory: File,
    val compiledJsNodeTestProgramDirectory: File,
    val packedJUnitReport: File,
    val jsNodeJUnitReport: File,
)

internal fun deriveCrossLanguageJavaScriptBindingEvidence(
    canonical: CrossLanguageCanonicalApiEvidence,
    packedApi: JavaScriptPackedPublicApiEvidence,
): CrossLanguageJavaScriptBindingEvidence {
    val symbols = validateJavaScriptPackedPublicApiEvidence(packedApi, requireSchemaTwo = false)
    val referenced = packedApi.referencedSymbols.toSet()
    val missing = mutableListOf<String>()
    val errors = mutableListOf<String>()
    val provisional = mutableListOf<JavaScriptProjection>()
    val exclusions = mutableListOf<CrossLanguageApplicabilityExclusion>()

    canonical.memberKeys.forEach { key ->
        val member = parseCanonicalJavaScriptMember(key)
        val candidates = javaScriptProjectionCandidates(member, symbols).distinctBy { it.publicSymbols }
        val exclusion = javaScriptApplicabilityExclusion(member)
        val excludedOwnerHasPublicConstructor = exclusion != null && symbols.any {
            it.kind == JavaScriptPublicSymbolKind.CONSTRUCTOR && it.owner == member.simpleOwner
        }
        when {
            exclusion != null && (candidates.isNotEmpty() || excludedOwnerHasPublicConstructor) -> errors +=
                "JavaScript/TypeScript projection conflicts with applicability exclusion for $key"
            exclusion != null -> exclusions += exclusion
            candidates.isEmpty() -> missing += key
            candidates.size > 1 -> errors +=
                "Ambiguous JavaScript/TypeScript projection for $key: " +
                    candidates.joinToString { it.publicSymbols.joinToString(" + ") }
            else -> {
                val candidate = candidates.single()
                val unreferenced = if (candidate.requiresConsumerReference) {
                    candidate.publicSymbols.filterNot(referenced::contains)
                } else emptyList()
                if (unreferenced.isNotEmpty()) {
                    errors += "Unreferenced exceptional JavaScript/TypeScript projection for $key: $unreferenced"
                } else {
                    provisional += JavaScriptProjection(
                        member,
                        candidate.publicSymbols,
                        candidate.scenarios,
                        candidate.shareablePublicSymbols,
                    )
                }
            }
        }
    }

    provisional.flatMap { projection ->
        projection.publicSymbols.map { symbol -> symbol to projection }
    }.groupBy(Pair<String, JavaScriptProjection>::first).forEach { (symbol, uses) ->
        val projections = uses.map(Pair<String, JavaScriptProjection>::second)
        if (projections.size > 1 &&
            !isAllowedLiteralTypeReuse(symbol, projections) &&
            !isAllowedHostStateFlatteningReuse(symbol, projections) &&
            !isAllowedConversationControllerFlatteningReuse(symbol, projections) &&
            !isAllowedConversationStateEnvelopeReuse(symbol, projections) &&
            !isAllowedConversationStateLeafReuse(symbol, projections) &&
            !isAllowedAgentInvocationMemberReuse(symbol, projections) &&
            !isAllowedAgentTurnRequestReuse(symbol, projections) &&
            !isAllowedAgentHookHandlerReuse(symbol, projections) &&
            !isAllowedIntegrationAuthorizationReuse(symbol, projections) &&
            !isAllowedAgentFormValueReuse(symbol, projections) &&
            !isAllowedPendingInteractionReuse(symbol, projections) &&
            !isAllowedFlattenedValueReuse(symbol, projections)
        ) {
            errors += "Reused JavaScript/TypeScript public symbol $symbol for capabilities " +
                projections.map { it.member.key }.sorted()
        }
    }
    errors += invalidConversationControllerFlatteningErrors(provisional)
    errors += invalidConversationStateSnapshotErrors(provisional)
    errors += invalidAgentTurnRequestErrors(canonical.memberKeys, provisional)
    errors += invalidAgentHookHandlerErrors(canonical.memberKeys, provisional)
    errors += invalidMcpServersErrors(canonical.memberKeys, provisional)
    errors += invalidIntegrationAuthorizationErrors(canonical.memberKeys, provisional)
    errors += invalidPluginsErrors(canonical.memberKeys, provisional)
    errors += invalidAgentFormFieldErrors(canonical.memberKeys, provisional)
    errors += invalidInteractionsErrors(canonical.memberKeys, provisional)

    val rejectedKeys = errors.flatMap { error ->
        provisional.mapNotNull { projection -> projection.member.key.takeIf(error::contains) }
    }.toSet()
    val claims = provisional.filterNot { it.member.key in rejectedKeys }.map { projection ->
        CrossLanguageProjectionClaim(
            capabilityKey = projection.member.key,
            language = CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
            publicSymbols = projection.publicSymbols.sorted(),
            executedTests = listOf(packedApi.compilerTestId),
            sharedScenarios = projection.scenarios.sortedBy(CrossLanguageBindingScenario::id),
        )
    }.sortedBy(CrossLanguageProjectionClaim::capabilityKey)

    return CrossLanguageJavaScriptBindingEvidence(
        canonical = canonical,
        packedApi = packedApi,
        projectionClaims = claims,
        applicabilityExclusions = exclusions.sortedBy(CrossLanguageApplicabilityExclusion::capabilityKey),
        missingCapabilityKeys = missing.sorted(),
        errors = errors.sorted(),
    )
}

internal fun buildJavaScriptTypeScriptBindingReceipt(
    files: CrossLanguageJavaScriptBindingFiles,
): CrossLanguageBindingReceipt {
    val canonical = readCrossLanguageCanonicalApiEvidence(files.apiReport, files.canonicalCoverageReceipt)
    val packedApi = readJavaScriptPackedPublicApiEvidence(files.packedPublicApiReport)
    validateJavaScriptPackedPublicApiEvidence(packedApi, requireSchemaTwo = true)
    val artifacts = deriveJavaScriptArtifactEvidence(files, packedApi)
    val tests = deriveJavaScriptBindingTests(files)
    check(packedApi.compilerTestId == packedCompilerTest && tests.any {
        it.testId == packedCompilerTest && it.status == CrossLanguageBindingTestStatus.PASSED
    }) { "Packed public API compiler test is absent, renamed, or did not pass" }
    val scenarioEvidence = deriveJavaScriptScenarioEvidence(tests, javaScriptBindingScenarioMappings)
    val testProgramSha256 = labeledJavaScriptDigest(
        "compiled-js-node-test-program" to files.compiledJsNodeTestProgramDirectory.crossLanguageTreeDigest(),
        "packed-consumer-source" to exactJavaScriptConsumerProgramDigest(files.consumerSourceDirectory),
    )
    val testResultsSha256 = canonicalJavaScriptBindingTestsDigest(tests)
    val evidence = deriveCrossLanguageJavaScriptBindingEvidence(canonical, packedApi)
    check(evidence.errors.isEmpty()) { evidence.errors.joinToString("\n") }
    check(evidence.missingCapabilityKeys.isEmpty()) {
        summarizeMissingJavaScriptCapabilities(evidence.missingCapabilityKeys)
    }
    jsRequireSortedUnique(canonical.memberKeys, "canonical JavaScript/TypeScript capability")
    check(canonical.memberKeys.size == JAVASCRIPT_CANONICAL_CAPABILITY_COUNT) {
        "JavaScript/TypeScript receipt requires exactly $JAVASCRIPT_CANONICAL_CAPABILITY_COUNT capabilities"
    }
    val canonicalKeys = canonical.memberKeys.toSet()
    val claimKeys = evidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey)
    val exclusionKeys = evidence.applicabilityExclusions.map(CrossLanguageApplicabilityExclusion::capabilityKey)
    check(claimKeys.size == claimKeys.distinct().size &&
        exclusionKeys.size == exclusionKeys.distinct().size &&
        claimKeys.toSet().intersect(exclusionKeys.toSet()).isEmpty() &&
        claimKeys.toSet() + exclusionKeys == canonicalKeys
    ) {
        "JavaScript/TypeScript claims and exclusions do not exactly cover the canonical API"
    }
    val receipt = CrossLanguageBindingReceipt(
        phase = CrossLanguageBindingPhase.M8,
        language = CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
        canonical = evidence.canonical.canonical,
        artifacts = artifacts,
        testProgramSha256 = testProgramSha256,
        testResultsSha256 = testResultsSha256,
        publicSymbols = evidence.packedApi.publicSymbols,
        bindingTests = tests,
        scenarioEvidence = scenarioEvidence,
        projectionClaims = evidence.projectionClaims,
        applicabilityExclusions = evidence.applicabilityExclusions,
    )
    receipt.toJson() // Apply the shared schema-3 normalization and fail-closed validation.
    return receipt
}

internal data class JavaScriptBindingScenarioMapping(
    val scenario: CrossLanguageBindingScenario,
    val testIds: List<String>,
)

internal val javaScriptBindingScenarioMappings = listOf(
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_SUCCESS,
        listOf(packedLifecycleTest, jsLifecycleTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_FAILURE,
        listOf(packedLifecycleTest, jsLifecycleTest, jsAuthenticationFailureTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.CANCELLATION,
        listOf(packedCancellationTest, jsAbortBeforeStartTest, jsCancellationTest, jsAuthenticationFailureTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
        listOf(packedLifecycleTest, jsLifecycleTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
        listOf(packedLifecycleTest, jsLifecycleTest, jsListenerFailureTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
        listOf(packedLifecycleTest, jsAbortBeforeStartTest, jsListenerFailureTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.TERMINAL_DELIVERY,
        listOf(packedLifecycleTest, jsLifecycleTest, jsListenerFailureTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.STRUCTURED_FAILURE,
        listOf(packedLifecycleTest, jsLifecycleTest, jsAuthenticationFailureTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.IDENTITY,
        listOf(jsLifecycleTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
        listOf(jsLifecycleTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE,
        listOf(packedLifecycleTest, jsLifecycleTest, jsAbortBeforeStartTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.NULLABILITY,
        listOf(packedCompilerTest, jsLifecycleTest, jsAuthenticationTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING,
        listOf(jsLifecycleTest),
    ),
    JavaScriptBindingScenarioMapping(
        CrossLanguageBindingScenario.VALUE_CONVERSION,
        listOf(packedSurfaceTest, jsLifecycleTest, jsAuthenticationTest),
    ),
)

private fun deriveJavaScriptArtifactEvidence(
    files: CrossLanguageJavaScriptBindingFiles,
    packedApi: JavaScriptPackedPublicApiEvidence,
): List<CrossLanguageBindingArtifactIdentity> {
    val installed = files.installedPackageDirectory
    check(installed.isDirectory && !Files.isSymbolicLink(installed.toPath())) {
        "Installed JavaScript/TypeScript package directory is missing or a symlink: $installed"
    }
    val actualFiles = mapOf(
        "commonJs" to installed.resolve("index.cjs"),
        "declaration" to installed.resolve("index.d.ts"),
        "esm" to installed.resolve("index.mjs"),
        "packageJson" to installed.resolve("package.json"),
        "tarball" to files.npmTarball,
    )
    val actual = actualFiles.map { (id, file) ->
        exactJavaScriptArtifact(id, file)
    }.sortedBy(JavaScriptPackedArtifact::id)
    check(actual == packedApi.artifacts) {
        "Packed public API artifact identities do not match the exact npm files"
    }

    val packageContents = actualFiles.getValue("packageJson").readText()
    val packageJson = releaseJson.parseToJsonElement(packageContents) as? JsonObject
        ?: error("Installed npm package.json must be a JSON object")
    check(packageJson.jsExactString("name") == JAVASCRIPT_NPM_PACKAGE) {
        "Installed npm package has the wrong coordinate"
    }
    check(packageJson.jsExactString("name") == packedApi.packageName &&
        packageJson.jsExactString("version") == packedApi.packageVersion) {
        "Packed public API package identity does not match installed package.json"
    }
    return actual.map { CrossLanguageBindingArtifactIdentity(it.id, it.sha256) }
}

private fun exactJavaScriptArtifact(id: String, file: File): JavaScriptPackedArtifact {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "JavaScript/TypeScript artifact $id is missing, non-regular, or a symlink: $file"
    }
    val bytes = file.length()
    check(bytes > 0L) { "JavaScript/TypeScript artifact $id is empty: $file" }
    return JavaScriptPackedArtifact(id, file.name, bytes, file.releaseDigest())
}

private fun exactJavaScriptConsumerProgramDigest(directory: File): String {
    check(directory.isDirectory && !Files.isSymbolicLink(directory.toPath())) {
        "JavaScript/TypeScript consumer source directory is missing or a symlink: $directory"
    }
    val entries = directory.listFiles()?.toList()
        ?: error("JavaScript/TypeScript consumer source directory is unreadable: $directory")
    check(entries.none { Files.isSymbolicLink(it.toPath()) } && entries.all(File::isFile)) {
        "JavaScript/TypeScript consumer source contains a symlink or non-file entry"
    }
    val names = entries.map(File::getName).toSet()
    check(names.size == entries.size && names == requiredJavaScriptConsumerProgramFiles) {
        "JavaScript/TypeScript consumer source inventory differs: " +
            "expected=${requiredJavaScriptConsumerProgramFiles.sorted()} actual=${names.sorted()}"
    }
    return directory.crossLanguageTreeDigest()
}

private fun deriveJavaScriptBindingTests(
    files: CrossLanguageJavaScriptBindingFiles,
): List<CrossLanguageBindingTestEvidence> {
    val packed = readPackedJavaScriptTestResults(files.packedJUnitReport)
    requireExactJavaScriptTestInventory(packed, requiredPackedBindingTests, "packed npm")
    val jsNode = readCanonicalTestReport(files.jsNodeJUnitReport)
    requireExactJavaScriptTestInventory(jsNode, requiredJsNodeBindingTests, "compiled jsNode")
    return (packed + jsNode).sortedBy(CanonicalTestResult::testId).map { result ->
        check(result.status == CanonicalTestStatus.PASSED) {
            "JavaScript/TypeScript binding test did not pass: ${result.testId}: ${result.status}"
        }
        CrossLanguageBindingTestEvidence(
            CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
            result.testId,
            CrossLanguageBindingTestStatus.PASSED,
        )
    }
}

private fun readPackedJavaScriptTestResults(file: File): List<CanonicalTestResult> {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "Packed npm JUnit report is missing, non-regular, or a symlink: $file"
    }
    val root = secureDocumentBuilderFactory(namespaceAware = true).newDocumentBuilder().parse(file).documentElement
    check(root.tagName == "testsuites") { "Packed npm JUnit report has no testsuites root" }
    val cases = root.getElementsByTagName("testcase")
    val results = (0 until cases.length).map { index ->
        val test = cases.item(index) as? Element ?: error("Packed npm JUnit testcase is malformed")
        val id = test.getAttribute("name")
        jsRequireRecord(id, "packed npm binding test")
        val terminals = (0 until test.childNodes.length).mapNotNull { childIndex ->
            test.childNodes.item(childIndex) as? Element
        }.map(Element::getTagName)
        check(terminals.count { it in setOf("skipped", "failure", "error") } <= 1) {
            "Packed npm JUnit testcase has conflicting results: $id"
        }
        CanonicalTestResult(
            id,
            when {
                terminals.any { it == "failure" || it == "error" } -> CanonicalTestStatus.FAILED
                "skipped" in terminals -> CanonicalTestStatus.SKIPPED
                else -> CanonicalTestStatus.PASSED
            },
        )
    }
    val duplicates = results.groupingBy(CanonicalTestResult::testId).eachCount()
        .filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "Packed npm JUnit test identities are ambiguous: $duplicates" }
    return results.sortedBy(CanonicalTestResult::testId)
}

private fun requireExactJavaScriptTestInventory(
    results: List<CanonicalTestResult>,
    expected: Set<String>,
    label: String,
) {
    val actual = results.map(CanonicalTestResult::testId).toSet()
    check(actual.size == results.size && actual == expected) {
        "JavaScript/TypeScript $label test inventory differs: " +
            "missing=${(expected - actual).sorted()} stale=${(actual - expected).sorted()}"
    }
}

internal fun deriveJavaScriptScenarioEvidence(
    tests: List<CrossLanguageBindingTestEvidence>,
    mappings: List<JavaScriptBindingScenarioMapping>,
): List<CrossLanguageScenarioEvidence> {
    check(tests.all {
        it.language == CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT &&
            it.status == CrossLanguageBindingTestStatus.PASSED
    }) { "JavaScript/TypeScript scenario evidence requires only passed JavaScript tests" }
    val testIds = tests.map(CrossLanguageBindingTestEvidence::testId).toSet()
    check(testIds.size == tests.size && testIds == requiredPackedBindingTests + requiredJsNodeBindingTests) {
        "JavaScript/TypeScript scenario test inventory is not exact"
    }
    val grouped = mappings.groupBy(JavaScriptBindingScenarioMapping::scenario)
    check(grouped.keys == CrossLanguageBindingScenario.entries.toSet() && grouped.values.all { it.size == 1 }) {
        "JavaScript/TypeScript scenario mapping is not an exact one-per-scenario inventory"
    }
    mappings.forEach { mapping ->
        check(mapping.testIds.isNotEmpty() && mapping.testIds.distinct().size == mapping.testIds.size) {
            "JavaScript/TypeScript scenario ${mapping.scenario.id} has missing or duplicate tests"
        }
        val stale = mapping.testIds.toSet() - testIds
        check(stale.isEmpty()) {
            "JavaScript/TypeScript scenario ${mapping.scenario.id} references stale tests: ${stale.sorted()}"
        }
    }
    return mappings.map { mapping ->
        CrossLanguageScenarioEvidence(
            CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
            mapping.scenario,
            mapping.testIds.sorted(),
        )
    }.sortedBy { it.scenario.id }
}

internal fun labeledJavaScriptDigest(vararg records: Pair<String, String>): String {
    check(records.isNotEmpty() && records.map(Pair<String, String>::first).distinct().size == records.size) {
        "JavaScript/TypeScript labeled digest records are empty or duplicated"
    }
    records.forEach { (label, digest) ->
        jsRequireRecord(label, "JavaScript/TypeScript digest label")
        jsRequireSha256(digest, "JavaScript/TypeScript digest $label")
    }
    return records.sortedBy(Pair<String, String>::first).joinToString(separator = "") { (label, digest) ->
        "$label\u0000$digest\n"
    }.byteInputStream().releaseDigest()
}

internal fun canonicalJavaScriptBindingTestsDigest(
    tests: List<CrossLanguageBindingTestEvidence>,
): String {
    check(tests.isNotEmpty() && tests.map(CrossLanguageBindingTestEvidence::testId).distinct().size == tests.size) {
        "JavaScript/TypeScript binding test digest requires a nonempty unique inventory"
    }
    return tests.sortedBy(CrossLanguageBindingTestEvidence::testId).joinToString(separator = "") { test ->
        "${test.language.id}\u0000${test.testId}\u0000${test.status.name}\n"
    }.byteInputStream().releaseDigest()
}

internal fun summarizeMissingJavaScriptCapabilities(keys: List<String>): String {
    check(keys.isNotEmpty()) { "Missing JavaScript/TypeScript capability summary requires at least one key" }
    val ownerCounts = keys.map(::parseCanonicalJavaScriptMember)
        .groupingBy(CanonicalJavaScriptMember::simpleOwner)
        .eachCount()
        .entries
        .sortedWith(
            compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key },
        )
    val largest = ownerCounts.take(12).joinToString { "${it.key}=${it.value}" }
    val remainder = (ownerCounts.size - 12).takeIf { it > 0 }?.let { ", +$it owners" }.orEmpty()
    return "Missing ${keys.size} JavaScript/TypeScript capabilities across ${ownerCounts.size} canonical owners; " +
        "largest owners: $largest$remainder"
}

internal fun readJavaScriptPackedPublicApiEvidence(file: File): JavaScriptPackedPublicApiEvidence {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "Packed JavaScript/TypeScript public API report is missing, non-regular, or a symlink: $file"
    }
    val contents = file.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("Packed JavaScript/TypeScript public API report must be a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "Packed JavaScript/TypeScript public API report is not canonically encoded"
    }
    root.jsRequireKeys(
        "packed public API report", "schema", "result", "language", "toolchain", "package",
        "artifacts", "exports", "publicSymbols", "compilerEvidence",
    )
    val schema = root.jsExactInt("schema")
    check(schema == 1 || schema == 2) { "Unsupported packed public API schema: $schema" }
    check(root.jsExactString("result") == "passed") { "Packed public API report did not pass" }
    check(root.jsExactString("language") == CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT.id) {
        "Packed public API report has the wrong language"
    }
    root.jsExactObject("toolchain").also { toolchain ->
        toolchain.jsRequireKeys("packed public API toolchain", "node", "typescript")
        jsRequireRecord(toolchain.jsExactString("node"), "Node toolchain")
        jsRequireRecord(toolchain.jsExactString("typescript"), "TypeScript toolchain")
    }
    val packageObject = root.jsExactObject("package").also {
        it.jsRequireKeys("packed public API package", "name", "version")
    }
    val packageName = packageObject.jsExactString("name").also {
        jsRequireRecord(it, "npm package name")
    }
    val packageVersion = packageObject.jsExactString("version").also {
        jsRequireRecord(it, "npm package version")
    }
    val artifactObject = root.jsExactObject("artifacts")
    artifactObject.jsRequireKeys(
        "packed public API artifacts", "tarball", "packageJson", "declaration", "commonJs", "esm",
    )
    val artifacts = artifactObject.entries.map { (id, value) ->
        val artifact = value as? JsonObject ?: error("Packed public API artifact $id must be an object")
        artifact.jsRequireKeys("packed public API artifact $id", "fileName", "bytes", "sha256")
        val fileName = artifact.jsExactString("fileName")
        check(fileName.isNotBlank() && fileName == File(fileName).name && fileName.none(Char::isISOControl)) {
            "Packed public API artifact $id has an unsafe file name"
        }
        val bytes = artifact.jsExactLong("bytes")
        check(bytes > 0) { "Packed public API artifact $id is empty" }
        JavaScriptPackedArtifact(id, fileName, bytes, artifact.jsExactSha256("sha256"))
    }.sortedBy(JavaScriptPackedArtifact::id)

    val exports = root.jsExactObject("exports").also {
        it.jsRequireKeys("packed public API exports", "types", "values", "commonJs", "esm")
    }
    val typeExports = exports.jsExactStrings("types").also { jsRequireSortedUnique(it, "type export") }
    val valueExports = exports.jsExactStrings("values").also { jsRequireSortedUnique(it, "value export") }
    val commonJsExports = exports.jsExactStrings("commonJs").also { jsRequireSortedUnique(it, "CommonJS export") }
    val esmExports = exports.jsExactStrings("esm").also { jsRequireSortedUnique(it, "ESM export") }
    check(valueExports == commonJsExports && valueExports == esmExports) {
        "Packed public API runtime exports disagree"
    }
    val publicSymbols = root.jsExactStrings("publicSymbols").also {
        jsRequireSortedUnique(it, "public symbol")
        check(it.isNotEmpty()) { "Packed public API symbol inventory is empty" }
        it.forEach(::parseJavaScriptPublicSymbol)
    }
    val compiler = root.jsExactObject("compilerEvidence")
    if (schema == 1) {
        compiler.jsRequireKeys("packed public API compiler evidence", "testId", "status")
    } else {
        compiler.jsRequireKeys(
            "packed public API compiler evidence", "testId", "status", "referencedSymbols",
        )
    }
    val compilerTestId = compiler.jsExactString("testId").also {
        jsRequireRecord(it, "compiler evidence test")
    }
    check(compiler.jsExactString("status") == "passed") { "Packed public API compiler evidence did not pass" }
    val references = if (schema == 2) compiler.jsExactStrings("referencedSymbols").also {
        jsRequireSortedUnique(it, "consumer-referenced public symbol")
        val stale = it.toSet() - publicSymbols.toSet()
        check(stale.isEmpty()) { "Consumer evidence references stale public symbols: ${stale.sorted()}" }
    } else emptyList()

    return JavaScriptPackedPublicApiEvidence(
        schema = schema,
        packageName = packageName,
        packageVersion = packageVersion,
        artifacts = artifacts,
        typeExports = typeExports,
        valueExports = valueExports,
        commonJsExports = commonJsExports,
        esmExports = esmExports,
        publicSymbols = publicSymbols,
        referencedSymbols = references,
        compilerTestId = compilerTestId,
    ).also { validateJavaScriptPackedPublicApiEvidence(it, requireSchemaTwo = false) }
}

private enum class CanonicalJavaScriptMemberKind { CONSTRUCTOR, ENUM_ENTRY, FUNCTION, OBJECT, PROPERTY }

private data class CanonicalJavaScriptMember(
    val key: String,
    val owner: String,
    val name: String,
    val kind: CanonicalJavaScriptMemberKind,
    val parameters: List<CanonicalJavaScriptParameter>,
    val returnType: String?,
    val isSuspend: Boolean,
    val propertyKind: CanonicalJavaScriptPropertyKind?,
) {
    val simpleOwner: String = owner.substringAfterLast('/')
}

private enum class CanonicalJavaScriptPropertyKind { VAL, VAR }

private data class CanonicalJavaScriptParameter(
    val type: String,
    val hasDefault: Boolean,
    val isVararg: Boolean,
)

private enum class JavaScriptPublicSymbolKind { CLASS, CONSTRUCTOR, FUNCTION, GETTER, METHOD, PROPERTY, TYPE }

private data class JavaScriptPublicSymbol(
    val raw: String,
    val kind: JavaScriptPublicSymbolKind,
    val owner: String?,
    val name: String,
    val signature: String?,
    val qualifiers: Set<String> = emptySet(),
)

private data class JavaScriptParameter(
    val name: String,
    val type: String,
    val optional: Boolean,
    val vararg: Boolean,
)

private data class JavaScriptSignature(
    val parameters: List<JavaScriptParameter>,
    val returnType: String?,
)

private data class JavaScriptProjectionCandidate(
    val publicSymbols: List<String>,
    val scenarios: List<CrossLanguageBindingScenario>,
    val requiresConsumerReference: Boolean,
    val shareablePublicSymbols: Set<String> = emptySet(),
)

private data class JavaScriptProjection(
    val member: CanonicalJavaScriptMember,
    val publicSymbols: List<String>,
    val scenarios: List<CrossLanguageBindingScenario>,
    val shareablePublicSymbols: Set<String>,
)

private fun parseCanonicalJavaScriptMember(key: String): CanonicalJavaScriptMember {
    val fields = key.split('|')
    check(fields.size >= 5 && fields.first() == "common") { "Unsupported canonical API key: $key" }
    val owner = fields.jsCanonicalField("owner")
    val kind = when (fields.jsCanonicalField("kind")) {
        "constructor" -> CanonicalJavaScriptMemberKind.CONSTRUCTOR
        "enum-entry" -> CanonicalJavaScriptMemberKind.ENUM_ENTRY
        "function" -> CanonicalJavaScriptMemberKind.FUNCTION
        "object" -> CanonicalJavaScriptMemberKind.OBJECT
        "property" -> CanonicalJavaScriptMemberKind.PROPERTY
        else -> error("Unsupported canonical JavaScript/TypeScript member kind in $key")
    }
    val abi = fields.jsCanonicalField("abi")
    val isObjectCapability = kind == CanonicalJavaScriptMemberKind.OBJECT
    if (isObjectCapability) {
        check(fields.size == 5 && abi == owner && fields.last() == "null[0]") {
            "Malformed canonical class/object ABI in $key"
        }
    }
    val name = if (isObjectCapability) {
        owner.substringAfterLast('/').substringAfterLast('.')
    } else abi.removePrefix("$owner.").substringBefore('(')
    check(name.isNotBlank()) { "Canonical API member has no ABI name: $key" }
    val parameters = fields.firstOrNull { it.startsWith("parameters=") }
        ?.substringAfter('=')
        ?.removeSurrounding("[", "]")
        ?.takeIf(String::isNotEmpty)
        ?.let(::splitJavaScriptTopLevel)
        ?.map { parameter ->
            check(parameter.startsWith("REGULAR:")) { "Unsupported canonical parameter in $key" }
            val end = parameter.indexOf(":default=")
            check(end > "REGULAR:".length) { "Malformed canonical parameter in $key" }
            val flagRecords = parameter.substring(end + 1).split(':')
            val flags = flagRecords.associate { flag ->
                val parts = flag.split('=', limit = 2)
                check(parts.size == 2) { "Malformed canonical parameter in $key" }
                parts[0] to parts[1]
            }
            check(flagRecords.size == 2 && flags.keys == setOf("default", "vararg") &&
                flags.values.all { it == "true" || it == "false" }
            ) {
                "Malformed canonical parameter flags in $key"
            }
            CanonicalJavaScriptParameter(
                type = parameter.substring("REGULAR:".length, end),
                hasDefault = flags.getValue("default").toBooleanStrict(),
                isVararg = flags.getValue("vararg").toBooleanStrict(),
            )
        }.orEmpty()
    val propertyKind = if (kind == CanonicalJavaScriptMemberKind.PROPERTY) {
        val value = fields.jsCanonicalField("propertyKind")
        CanonicalJavaScriptPropertyKind.entries.singleOrNull { it.name == value }
            ?: error("Unsupported canonical property kind in $key")
    } else {
        check(fields.none { it.startsWith("propertyKind=") }) {
            "Non-property canonical member declares a property kind in $key"
        }
        null
    }
    return CanonicalJavaScriptMember(
        key = key,
        owner = owner,
        name = name,
        kind = kind,
        parameters = parameters,
        returnType = fields.firstOrNull {
            it.startsWith(if (kind == CanonicalJavaScriptMemberKind.PROPERTY) "type=" else "return=")
        }?.substringAfter('='),
        isSuspend = fields.firstOrNull { it.startsWith("suspend=") }?.substringAfter('=') == "true",
        propertyKind = propertyKind,
    )
}

private fun List<String>.jsCanonicalField(name: String): String =
    singleOrNull { it.startsWith("$name=") }?.substringAfter('=')
        ?: error("Canonical API key is missing $name")

private fun parseJavaScriptPublicSymbol(raw: String): JavaScriptPublicSymbol {
    jsRequireRecord(raw, "JavaScript/TypeScript public symbol")
    val kind = JavaScriptPublicSymbolKind.entries.singleOrNull { raw.startsWith(it.name.lowercase() + ":") }
        ?: error("Unsupported JavaScript/TypeScript public symbol: $raw")
    val rest = raw.substringAfter(':')
    return when (kind) {
        JavaScriptPublicSymbolKind.CLASS, JavaScriptPublicSymbolKind.TYPE -> {
            val name = rest.substringBefore(':')
            check(name.isNotBlank()) { "Malformed JavaScript/TypeScript public symbol: $raw" }
            val signature = rest.substringAfter(':', "")
            if (kind == JavaScriptPublicSymbolKind.TYPE) {
                check(signature.isNotBlank()) { "Malformed JavaScript/TypeScript public type: $raw" }
            }
            JavaScriptPublicSymbol(raw, kind, null, name, signature)
        }
        JavaScriptPublicSymbolKind.FUNCTION -> {
            val separator = rest.indexOf(":(")
            check(separator > 0) { "Malformed JavaScript/TypeScript public function: $raw" }
            val signature = rest.substring(separator + 1)
            parseJavaScriptSignature(signature, requireReturn = true)
            JavaScriptPublicSymbol(raw, kind, null, rest.substring(0, separator), signature)
        }
        JavaScriptPublicSymbolKind.CONSTRUCTOR,
        JavaScriptPublicSymbolKind.GETTER,
        JavaScriptPublicSymbolKind.METHOD,
        JavaScriptPublicSymbolKind.PROPERTY,
        -> {
            val ownerEnd = rest.indexOf('#')
            check(ownerEnd > 0) { "Malformed JavaScript/TypeScript owned symbol: $raw" }
            val member = rest.substring(ownerEnd + 1)
            if (kind == JavaScriptPublicSymbolKind.CONSTRUCTOR) {
                check(member.startsWith('(')) { "Malformed JavaScript/TypeScript constructor: $raw" }
                parseJavaScriptSignature(member, requireReturn = false)
                return JavaScriptPublicSymbol(raw, kind, rest.substring(0, ownerEnd), "constructor", member)
            }
            val signatureStart = when (kind) {
                JavaScriptPublicSymbolKind.METHOD -> member.indexOf(":(")
                else -> member.indexOf(':')
            }
            check(signatureStart >= 0) { "Malformed JavaScript/TypeScript owned symbol: $raw" }
            val nameAndQualifiers = member.substring(0, signatureStart)
            val qualifierSearchStart = if (nameAndQualifiers.startsWith('[')) {
                val computedNameEnd = nameAndQualifiers.indexOf(']')
                check(computedNameEnd > 1) { "Malformed JavaScript/TypeScript computed member: $raw" }
                computedNameEnd + 1
            } else 0
            val qualifierStart = nameAndQualifiers.indexOf('[', qualifierSearchStart)
            val name = if (qualifierStart < 0) nameAndQualifiers else nameAndQualifiers.substring(0, qualifierStart)
            check(name.isNotBlank()) { "Malformed JavaScript/TypeScript owned symbol: $raw" }
            val qualifiers = if (qualifierStart < 0) emptySet() else {
                check(nameAndQualifiers.endsWith(']')) { "Malformed JavaScript/TypeScript qualifiers: $raw" }
                nameAndQualifiers.substring(qualifierStart + 1, nameAndQualifiers.lastIndex)
                    .split(',').also { values ->
                        check(values.isNotEmpty() && values.all(String::isNotBlank) && values.distinct().size == values.size) {
                            "Malformed JavaScript/TypeScript qualifiers: $raw"
                        }
                    }.toSet()
            }
            val allowedQualifiers = when (kind) {
                JavaScriptPublicSymbolKind.METHOD -> setOf("static")
                JavaScriptPublicSymbolKind.GETTER -> setOf("optional", "static")
                JavaScriptPublicSymbolKind.PROPERTY -> setOf("optional", "readonly", "static")
                else -> emptySet()
            }
            check(qualifiers.all(allowedQualifiers::contains)) {
                "Unsupported JavaScript/TypeScript qualifiers: $raw"
            }
            val signature = member.substring(signatureStart + 1)
            if (kind == JavaScriptPublicSymbolKind.METHOD) {
                parseJavaScriptSignature(signature, requireReturn = true)
            } else check(signature.isNotBlank()) {
                "Malformed JavaScript/TypeScript member type: $raw"
            }
            JavaScriptPublicSymbol(raw, kind, rest.substring(0, ownerEnd), name, signature, qualifiers)
        }
    }
}

private fun javaScriptProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (member.isD059InteractionsSurfaceMember()) {
        return interactionsProjectionCandidates(member, symbols)
    }
    if (member.isD057AgentFormFieldSurfaceMember()) {
        return agentFormFieldProjectionCandidates(member, symbols)
    }
    if (member.isD054PluginsSurfaceMember()) {
        return pluginsProjectionCandidates(member, symbols)
    }
    if (member.isD051IntegrationAuthorizationSurfaceMember()) {
        return integrationAuthorizationProjectionCandidates(member, symbols)
    }
    if (member.isD050McpServersSurfaceMember()) {
        return mcpServersProjectionCandidates(member, symbols)
    }
    if (member.isD048AgentHookHandlerSurfaceMember()) {
        return agentHookHandlerProjectionCandidates(member, symbols)
    }
    if (member.isD047AgentTurnRequestSurfaceMember()) {
        return agentTurnRequestProjectionCandidates(member, symbols)
    }
    if (member.isD044HostStateOwner()) return hostStateFlatteningProjectionCandidates(member, symbols)
    if (member.simpleOwner == "AgentConversationState" && member.name in d046ConversationStateMemberNames) {
        return conversationStateSnapshotProjectionCandidates(member, symbols)
    }
    if (member.simpleOwner == "CodexAgent" && member.name == "conversations") {
        return conversationsFlatteningProjectionCandidates(member, symbols)
    }
    if (member.isD043SurfaceMember() && !member.isExactD043SurfaceMember()) return emptyList()
    val flattened = flattenedValueProjectionCandidates(member, symbols)
    if (flattened.isNotEmpty() || member.requiresExactD043FlattenedProjection()) return flattened
    return when (member.kind) {
        CanonicalJavaScriptMemberKind.OBJECT -> objectProjectionCandidates(member, symbols)
        CanonicalJavaScriptMemberKind.ENUM_ENTRY -> enumProjectionCandidates(member, symbols)
        CanonicalJavaScriptMemberKind.PROPERTY -> propertyProjectionCandidates(member, symbols)
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> constructorProjectionCandidates(member, symbols)
        CanonicalJavaScriptMemberKind.FUNCTION -> functionProjectionCandidates(member, symbols)
    }
}

private const val javaScriptApprovalPresetDisplayName =
    "function:codexApprovalPresetDisplayName:(preset: CodexApprovalPreset): string"
private const val javaScriptAgentCapabilityDisplayLabel =
    "function:agentCapabilityDisplayLabel:(capability: AgentCapability): string"
private const val javaScriptAgentCapabilityIcon =
    "function:agentCapabilityIcon:(capability: AgentCapability): string | null | undefined"
private const val javaScriptAgentCapabilityId =
    "function:agentCapabilityId:(capability: AgentCapability): string"
private const val javaScriptAgentCapabilityPromptLabel =
    "function:agentCapabilityPromptLabel:(capability: AgentCapability): string"
private const val javaScriptAgentInvocationType =
    "type:AgentInvocation:AgentPluginInvocation | AgentSkillInvocation"
private const val javaScriptAgentTurnRequestType =
    "type:AgentTurnRequest:{ readonly prompt: string; " +
        "readonly clientMessageId?: string | null | undefined; " +
        "readonly model?: string | null | undefined; " +
        "readonly effort?: string | null | undefined; " +
        "readonly serviceTier?: string | null | undefined; " +
        "readonly approvalPreset?: CodexApprovalPreset; " +
        "readonly capabilities?: ReadonlyArray<AgentCapability>; " +
        "readonly invocations?: ReadonlyArray<AgentInvocation>; " +
        "readonly collaborationMode?: AgentCollaborationMode; }"
private const val javaScriptSendRequest =
    "method:CodexConversation#sendRequest:" +
        "(request: AgentTurnRequest, signal?: AbortSignal | null | undefined): Promise<void>"
private val javaScriptAgentTurnRequestSymbols = listOf(
    javaScriptAgentTurnRequestType,
    javaScriptSendRequest,
).sorted()
private const val javaScriptAgentHookHandlerType =
    "type:AgentHookHandler:{ readonly type: \"agent\"; } | " +
        "{ readonly type: \"command\"; readonly command: string; readonly isAsync: boolean; } | " +
        "{ readonly type: \"mcp_tool\"; readonly server: string; readonly tool: string; } | " +
        "{ readonly type: \"prompt\"; }"
private const val javaScriptAgentMcpTransportType =
    "type:AgentMcpTransport:AgentMcpStdioTransport | AgentMcpHttpTransport"
private val javaScriptMcpServersSymbols = listOf(
    "class:AgentMcpHttpTransport",
    "class:AgentMcpServer",
    "class:AgentMcpServerConfiguration",
    "class:AgentMcpStdioTransport",
    "class:CodexMcpServers",
    "constructor:AgentMcpHttpTransport#(url: string, " +
        "bearerTokenEnvironmentVariable?: string | null | undefined, " +
        "headers?: Readonly<Record<string, string>> | null | undefined, " +
        "environmentHeaders?: Readonly<Record<string, string>> | null | undefined, " +
        "headersHelper?: string | null | undefined)",
    "constructor:AgentMcpServer#(name: string, displayName: string, " +
        "authStatus: AgentMcpAuthStatus, " +
        "configuration?: AgentMcpServerConfiguration | null | undefined, " +
        "origin?: AgentResourceOrigin, canRemove?: boolean)",
    "constructor:AgentMcpServerConfiguration#(name: string, transport: AgentMcpTransport, " +
        "authentication?: AgentMcpAuthentication | null | undefined, environmentId?: string, " +
        "isEnabled?: boolean, isRequired?: boolean, supportsParallelToolCalls?: boolean, " +
        "omitToolsFrom?: ReadonlyArray<AgentMcpToolExposureSurface> | null | undefined, " +
        "startupTimeoutSeconds?: number | null | undefined, " +
        "toolTimeoutSeconds?: number | null | undefined, " +
        "defaultToolApproval?: AgentMcpToolApproval | null | undefined, " +
        "enabledTools?: ReadonlyArray<string> | null | undefined, " +
        "disabledTools?: ReadonlyArray<string> | null | undefined, " +
        "scopes?: ReadonlyArray<string> | null | undefined, " +
        "oauth?: AgentMcpOauthConfiguration | null | undefined, " +
        "oauthResource?: string | null | undefined, " +
        "tools?: Readonly<Record<string, AgentMcpToolConfiguration>>)",
    "constructor:AgentMcpStdioTransport#(command: string, arguments?: ReadonlyArray<string>, " +
        "workingDirectory?: string | null | undefined, " +
        "environment?: Readonly<Record<string, string>> | null | undefined, " +
        "forwardedEnvironment?: ReadonlyArray<AgentMcpEnvironmentVariable>)",
    "getter:AgentMcpHttpTransport#bearerTokenEnvironmentVariable:string | null | undefined",
    "getter:AgentMcpHttpTransport#environmentHeaders:" +
        "Readonly<Record<string, string>> | null | undefined",
    "getter:AgentMcpHttpTransport#headers:Readonly<Record<string, string>> | null | undefined",
    "getter:AgentMcpHttpTransport#headersHelper:string | null | undefined",
    "getter:AgentMcpHttpTransport#url:string",
    "getter:AgentMcpServer#authStatus:AgentMcpAuthStatus",
    "getter:AgentMcpServer#canRemove:boolean",
    "getter:AgentMcpServer#configuration:AgentMcpServerConfiguration | null | undefined",
    "getter:AgentMcpServer#displayName:string",
    "getter:AgentMcpServer#isAuthorized:boolean",
    "getter:AgentMcpServer#name:string",
    "getter:AgentMcpServer#origin:AgentResourceOrigin",
    "getter:AgentMcpServerConfiguration#authentication:AgentMcpAuthentication | null | undefined",
    "getter:AgentMcpServerConfiguration#defaultToolApproval:AgentMcpToolApproval | null | undefined",
    "getter:AgentMcpServerConfiguration#disabledTools:ReadonlyArray<string> | null | undefined",
    "getter:AgentMcpServerConfiguration#enabledTools:ReadonlyArray<string> | null | undefined",
    "getter:AgentMcpServerConfiguration#environmentId:string",
    "getter:AgentMcpServerConfiguration#isEnabled:boolean",
    "getter:AgentMcpServerConfiguration#isRequired:boolean",
    "getter:AgentMcpServerConfiguration#name:string",
    "getter:AgentMcpServerConfiguration#oauth:AgentMcpOauthConfiguration | null | undefined",
    "getter:AgentMcpServerConfiguration#oauthResource:string | null | undefined",
    "getter:AgentMcpServerConfiguration#omitToolsFrom:" +
        "ReadonlyArray<AgentMcpToolExposureSurface> | null | undefined",
    "getter:AgentMcpServerConfiguration#scopes:ReadonlyArray<string> | null | undefined",
    "getter:AgentMcpServerConfiguration#startupTimeoutSeconds:number | null | undefined",
    "getter:AgentMcpServerConfiguration#supportsParallelToolCalls:boolean",
    "getter:AgentMcpServerConfiguration#toolTimeoutSeconds:number | null | undefined",
    "getter:AgentMcpServerConfiguration#tools:Readonly<Record<string, AgentMcpToolConfiguration>>",
    "getter:AgentMcpServerConfiguration#transport:AgentMcpTransport",
    "getter:AgentMcpStdioTransport#arguments:ReadonlyArray<string>",
    "getter:AgentMcpStdioTransport#command:string",
    "getter:AgentMcpStdioTransport#environment:Readonly<Record<string, string>> | null | undefined",
    "getter:AgentMcpStdioTransport#forwardedEnvironment:ReadonlyArray<AgentMcpEnvironmentVariable>",
    "getter:AgentMcpStdioTransport#workingDirectory:string | null | undefined",
    "getter:CodexAgent#mcpServers:CodexMcpServers",
    "getter:CodexMcpServers#isAvailable:boolean",
    "method:CodexMcpServers#add:(configuration: AgentMcpServerConfiguration, " +
        "signal?: AbortSignal | null | undefined): Promise<AgentMcpServer>",
    "method:CodexMcpServers#list:(signal?: AbortSignal | null | undefined): " +
        "Promise<ReadonlyArray<AgentMcpServer>>",
    "method:CodexMcpServers#remove:(server: AgentMcpServer, " +
        "signal?: AbortSignal | null | undefined): Promise<void>",
    javaScriptAgentMcpTransportType,
).sorted()
private const val javaScriptAgentIntegrationType =
    "type:AgentIntegration:AgentConnectorIntegration | AgentMcpServerIntegration"
private val javaScriptIntegrationAuthorizationSymbols = listOf(
    "class:AgentConnectorIntegration",
    "class:AgentIntegrationAuthorizationState",
    "class:AgentMcpServerIntegration",
    "class:CodexIntegrationAuthorization",
    "constructor:AgentConnectorIntegration#(connector: AgentConnector)",
    "constructor:AgentIntegrationAuthorizationState#(" +
        "status?: AgentIntegrationAuthorizationStatus, " +
        "target?: AgentIntegration | null | undefined, " +
        "failure?: CodexFailure | null | undefined)",
    "constructor:AgentMcpServerIntegration#(server: AgentMcpServer)",
    "getter:AgentConnectorIntegration#connector:AgentConnector",
    "getter:AgentConnectorIntegration#displayName:string",
    "getter:AgentConnectorIntegration#id:string",
    "getter:AgentIntegrationAuthorizationState#failure:CodexFailure | null | undefined",
    "getter:AgentIntegrationAuthorizationState#status:AgentIntegrationAuthorizationStatus",
    "getter:AgentIntegrationAuthorizationState#target:AgentIntegration | null | undefined",
    "getter:AgentMcpServerIntegration#displayName:string",
    "getter:AgentMcpServerIntegration#id:string",
    "getter:AgentMcpServerIntegration#server:AgentMcpServer",
    "getter:CodexAgent#integrationAuthorization:CodexIntegrationAuthorization",
    "getter:CodexIntegrationAuthorization#active:AgentIntegration | null | undefined",
    "getter:CodexIntegrationAuthorization#isAuthorizing:boolean",
    "getter:CodexIntegrationAuthorization#state:AgentIntegrationAuthorizationState",
    "method:CodexIntegrationAuthorization#authorize:(target: AgentIntegration, " +
        "signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexIntegrationAuthorization#cancel:(signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexIntegrationAuthorization#observeActive:(listener: " +
        "(target: AgentIntegration | null | undefined) => void): CodexObservation",
    "method:CodexIntegrationAuthorization#observeAuthorizing:(listener: " +
        "(isAuthorizing: boolean) => void): CodexObservation",
    "method:CodexIntegrationAuthorization#observeState:(listener: " +
        "(state: AgentIntegrationAuthorizationState) => void): CodexObservation",
    javaScriptAgentIntegrationType,
).sorted()
private val javaScriptPluginsSymbols = listOf(
    "class:AgentPluginCatalog",
    "class:AgentPluginDetail",
    "class:AgentPluginInstallResult",
    "class:AgentPluginReference",
    "class:AgentPluginSkill",
    "class:AgentPluginSummary",
    "class:CodexPlugins",
    "constructor:AgentPluginCatalog#(plugins: ReadonlyArray<AgentPluginSummary>, " +
        "errors?: ReadonlyArray<string>, freshness?: AgentCatalogFreshness)",
    "constructor:AgentPluginDetail#(summary: AgentPluginSummary, description: string, " +
        "skills: ReadonlyArray<AgentPluginSkill>, connectors: ReadonlyArray<AgentConnector>, " +
        "mcpServers: ReadonlyArray<string>, hookCount: number)",
    "constructor:AgentPluginInstallResult#(authPolicy: AgentPluginAuthPolicy, " +
        "connectorsNeedingAuthentication: ReadonlyArray<AgentConnector>, " +
        "message?: string | null | undefined)",
    "constructor:AgentPluginReference#(id: string, name: string, marketplaceName: string, " +
        "marketplacePath?: string | null | undefined, " +
        "remotePluginId?: string | null | undefined)",
    "constructor:AgentPluginSkill#(name: string, description: string, isEnabled: boolean, " +
        "path?: string | null | undefined)",
    "constructor:AgentPluginSummary#(reference: AgentPluginReference, displayName: string, " +
        "description: string, isInstalled: boolean, isEnabled: boolean, " +
        "installPolicy: AgentPluginInstallPolicy, authPolicy: AgentPluginAuthPolicy, " +
        "isAvailable: boolean, capabilities?: ReadonlyArray<string>, " +
        "brandColor?: string | null | undefined, privacyPolicyUrl?: string | null | undefined, " +
        "termsOfServiceUrl?: string | null | undefined, websiteUrl?: string | null | undefined)",
    "getter:AgentPluginCatalog#errors:ReadonlyArray<string>",
    "getter:AgentPluginCatalog#freshness:AgentCatalogFreshness",
    "getter:AgentPluginCatalog#plugins:ReadonlyArray<AgentPluginSummary>",
    "getter:AgentPluginDetail#connectors:ReadonlyArray<AgentConnector>",
    "getter:AgentPluginDetail#description:string",
    "getter:AgentPluginDetail#hookCount:number",
    "getter:AgentPluginDetail#mcpServers:ReadonlyArray<string>",
    "getter:AgentPluginDetail#skills:ReadonlyArray<AgentPluginSkill>",
    "getter:AgentPluginDetail#summary:AgentPluginSummary",
    "getter:AgentPluginInstallResult#authPolicy:AgentPluginAuthPolicy",
    "getter:AgentPluginInstallResult#connectorsNeedingAuthentication:ReadonlyArray<AgentConnector>",
    "getter:AgentPluginInstallResult#message:string | null | undefined",
    "getter:AgentPluginReference#id:string",
    "getter:AgentPluginReference#marketplaceName:string",
    "getter:AgentPluginReference#marketplacePath:string | null | undefined",
    "getter:AgentPluginReference#name:string",
    "getter:AgentPluginReference#remotePluginId:string | null | undefined",
    "getter:AgentPluginReference#uri:string",
    "getter:AgentPluginSkill#description:string",
    "getter:AgentPluginSkill#isEnabled:boolean",
    "getter:AgentPluginSkill#name:string",
    "getter:AgentPluginSkill#path:string | null | undefined",
    "getter:AgentPluginSummary#authPolicy:AgentPluginAuthPolicy",
    "getter:AgentPluginSummary#brandColor:string | null | undefined",
    "getter:AgentPluginSummary#capabilities:ReadonlyArray<string>",
    "getter:AgentPluginSummary#description:string",
    "getter:AgentPluginSummary#displayName:string",
    "getter:AgentPluginSummary#installPolicy:AgentPluginInstallPolicy",
    "getter:AgentPluginSummary#isAvailable:boolean",
    "getter:AgentPluginSummary#isEnabled:boolean",
    "getter:AgentPluginSummary#isInstalled:boolean",
    "getter:AgentPluginSummary#privacyPolicyUrl:string | null | undefined",
    "getter:AgentPluginSummary#reference:AgentPluginReference",
    "getter:AgentPluginSummary#termsOfServiceUrl:string | null | undefined",
    "getter:AgentPluginSummary#websiteUrl:string | null | undefined",
    "getter:CodexAgent#plugins:CodexPlugins",
    "getter:CodexPlugins#isAvailable:boolean",
    "method:CodexPlugins#install:(plugin: AgentPluginReference, " +
        "signal?: AbortSignal | null | undefined): Promise<AgentPluginInstallResult>",
    "method:CodexPlugins#list:(forceReload?: boolean, " +
        "signal?: AbortSignal | null | undefined): Promise<AgentPluginCatalog>",
    "method:CodexPlugins#read:(plugin: AgentPluginReference, " +
        "signal?: AbortSignal | null | undefined): Promise<AgentPluginDetail>",
    "method:CodexPlugins#uninstall:(plugin: AgentPluginReference, " +
        "signal?: AbortSignal | null | undefined): Promise<void>",
).sorted()
private const val javaScriptAgentFormValueType =
    "type:AgentFormValue:AgentFormBooleanValue | AgentFormNumberValue | " +
        "AgentFormTextListValue | AgentFormTextValue"
private val javaScriptAgentFormFieldSymbols = listOf(
    "class:AgentFormField",
    "constructor:AgentFormField#(name: string, title: string, type: AgentFormFieldType, " +
        "description?: string | null | undefined, isRequired?: boolean, " +
        "options?: ReadonlyArray<AgentFormOption>, " +
        "defaultValue?: AgentFormValue | null | undefined, " +
        "minimum?: number | null | undefined, maximum?: number | null | undefined, " +
        "format?: AgentFormStringFormat | null | undefined, " +
        "minimumLength?: bigint | null | undefined, maximumLength?: bigint | null | undefined, " +
        "minimumSelections?: bigint | null | undefined, maximumSelections?: bigint | null | undefined, " +
        "allowsOther?: boolean, isSecret?: boolean)",
    "getter:AgentFormField#allowsOther:boolean",
    "getter:AgentFormField#defaultValue:AgentFormValue | null | undefined",
    "getter:AgentFormField#description:string | null | undefined",
    "getter:AgentFormField#format:AgentFormStringFormat | null | undefined",
    "getter:AgentFormField#isRequired:boolean",
    "getter:AgentFormField#isSecret:boolean",
    "getter:AgentFormField#maximum:number | null | undefined",
    "getter:AgentFormField#maximumLength:bigint | null | undefined",
    "getter:AgentFormField#maximumSelections:bigint | null | undefined",
    "getter:AgentFormField#minimum:number | null | undefined",
    "getter:AgentFormField#minimumLength:bigint | null | undefined",
    "getter:AgentFormField#minimumSelections:bigint | null | undefined",
    "getter:AgentFormField#name:string",
    "getter:AgentFormField#options:ReadonlyArray<AgentFormOption>",
    "getter:AgentFormField#title:string",
    "getter:AgentFormField#type:AgentFormFieldType",
    "method:AgentFormField#accepts:(value: AgentFormValue | null | undefined): boolean",
    javaScriptAgentFormValueType,
).sorted()
private const val javaScriptPendingInteractionType =
    "type:AgentPendingInteraction:AgentPendingApproval | AgentPendingElicitation"
private val javaScriptInteractionsSymbols = listOf(
    "class:AgentElicitation",
    "class:AgentElicitationResponse",
    "class:AgentInteractionState",
    "class:AgentPendingApproval",
    "class:AgentPendingElicitation",
    "class:CodexInteractions",
    "constructor:AgentElicitation#(requestId: string, serverName: string, conversationId: string, " +
        "message: string, form?: ReadonlyArray<AgentFormField> | null | undefined, " +
        "url?: string | null | undefined)",
    "constructor:AgentElicitationResponse#(action: AgentElicitationAction, " +
        "content?: Readonly<Record<string, AgentFormValue>>)",
    "constructor:AgentInteractionState#(pending?: ReadonlyArray<AgentPendingInteraction>, " +
        "resolvingRequestIds?: ReadonlyArray<string>, failure?: CodexFailure | null | undefined)",
    "constructor:AgentPendingApproval#(requestId: string, conversationId: string, " +
        "title: string, details: string)",
    "constructor:AgentPendingElicitation#(elicitation: AgentElicitation)",
    "getter:AgentElicitation#conversationId:string",
    "getter:AgentElicitation#form:ReadonlyArray<AgentFormField> | null | undefined",
    "getter:AgentElicitation#message:string",
    "getter:AgentElicitation#requestId:string",
    "getter:AgentElicitation#serverName:string",
    "getter:AgentElicitation#url:string | null | undefined",
    "getter:AgentElicitationResponse#action:AgentElicitationAction",
    "getter:AgentElicitationResponse#content:Readonly<Record<string, AgentFormValue>>",
    "getter:AgentInteractionState#failure:CodexFailure | null | undefined",
    "getter:AgentInteractionState#pending:ReadonlyArray<AgentPendingInteraction>",
    "getter:AgentInteractionState#resolvingRequestIds:ReadonlyArray<string>",
    "getter:AgentPendingApproval#conversationId:string",
    "getter:AgentPendingApproval#details:string",
    "getter:AgentPendingApproval#requestId:string",
    "getter:AgentPendingApproval#title:string",
    "getter:AgentPendingElicitation#conversationId:string",
    "getter:AgentPendingElicitation#elicitation:AgentElicitation",
    "getter:AgentPendingElicitation#requestId:string",
    "getter:CodexAgent#interactions:CodexInteractions",
    "getter:CodexInteractions#approvals:ReadonlyArray<AgentPendingApproval>",
    "getter:CodexInteractions#elicitations:ReadonlyArray<AgentPendingElicitation>",
    "getter:CodexInteractions#state:AgentInteractionState",
    "method:AgentElicitation#accept:(content: Readonly<Record<string, AgentFormValue>>): " +
        "AgentElicitationResponse",
    "method:AgentElicitation#accepts:(response: AgentElicitationResponse): boolean",
    "method:AgentElicitation#initialValues:(): Readonly<Record<string, AgentFormValue>>",
    "method:AgentElicitation#validate:(content: Readonly<Record<string, AgentFormValue>>): " +
        "AgentElicitationValidation",
    "method:AgentElicitationResponse#cancel[static]:(): AgentElicitationResponse",
    "method:AgentElicitationResponse#decline[static]:(): AgentElicitationResponse",
    "method:AgentInteractionState#isResolving:(interaction: AgentPendingInteraction): boolean",
    "method:AgentInteractionState#pendingFor:(conversationId: string): " +
        "ReadonlyArray<AgentPendingInteraction>",
    "method:CodexInteractions#observeApprovals:(listener: " +
        "(approvals: ReadonlyArray<AgentPendingApproval>) => void): CodexObservation",
    "method:CodexInteractions#observeElicitations:(listener: " +
        "(elicitations: ReadonlyArray<AgentPendingElicitation>) => void): CodexObservation",
    "method:CodexInteractions#observeState:(listener: " +
        "(state: AgentInteractionState) => void): CodexObservation",
    "method:CodexInteractions#openUrl:(elicitation: AgentPendingElicitation, " +
        "signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexInteractions#resolve:(approval: AgentPendingApproval, " +
        "decision: AgentApprovalDecision, signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexInteractions#resolve:(elicitation: AgentPendingElicitation, " +
        "response: AgentElicitationResponse, signal?: AbortSignal | null | undefined): Promise<void>",
    javaScriptPendingInteractionType,
).sorted()
private const val javaScriptAgentMessageCapabilities =
    "getter:CodexMessage#capabilities:ReadonlyArray<AgentCapability>"
private const val javaScriptApiKeyAuthentication =
    "method:CodexAuthentication#authenticate:" +
        "(method: \"api_key\", apiKey: string, signal?: AbortSignal | null | undefined): Promise<void>"
private const val javaScriptCreateCodexHost =
    "function:createCodexHost:" +
        "(bundleDirectory: string, dataDirectory: string, clientName: string, " +
        "clientTitle: string, clientVersion: string): CodexHost"
private const val javaScriptSkillScopeDisplayName =
    "function:agentSkillScopeDisplayName:(scope: AgentSkillScope): string"
private const val javaScriptDeleteConversation =
    "method:CodexAgent#delete:" +
        "(conversationId: string, signal?: AbortSignal | null | undefined): Promise<void>"
private const val javaScriptReadConversation =
    "method:CodexAgent#readConversation:" +
        "(conversationId: string, signal?: AbortSignal | null | undefined): Promise<AgentConversation>"
private const val javaScriptRenameConversation =
    "method:CodexAgent#rename:" +
        "(conversationId: string, name: string, " +
        "signal?: AbortSignal | null | undefined): Promise<void>"
private const val javaScriptSelectWorkspace =
    "method:CodexHost#selectWorkspace:" +
        "(path: string, signal?: AbortSignal | null | undefined): Promise<void>"
private const val javaScriptHostStateGetter = "getter:CodexHost#state:CodexHostState"
private const val javaScriptHostStateObserver =
    "method:CodexHost#observeState:(listener: (state: CodexHostState) => void): CodexObservation"
private const val javaScriptHostStateStatus = "getter:CodexHostState#status:CodexHostStatus"
private const val javaScriptHostStateWorkspace =
    "getter:CodexHostState#workspace:CodexWorkspace | null | undefined"
private const val javaScriptHostStateAgent = "getter:CodexHostState#agent:CodexAgent | null | undefined"
private const val javaScriptHostStateFailure =
    "getter:CodexHostState#failure:CodexFailure | null | undefined"
private const val javaScriptHostStateSelectionReason =
    "getter:CodexHostState#selectionReason:CodexWorkspaceSelectionReason | null | undefined"
private const val javaScriptHostStateSelectionMessage =
    "getter:CodexHostState#selectionMessage:string | null | undefined"
private val javaScriptHostStateEnvelope = setOf(javaScriptHostStateGetter, javaScriptHostStateObserver)
private val javaScriptHostStateSharedSymbols = javaScriptHostStateEnvelope + setOf(
    javaScriptHostStateStatus,
    javaScriptHostStateWorkspace,
    javaScriptHostStateSelectionReason,
    javaScriptHostStateSelectionMessage,
)

private val javaScriptConversationIdSymbols = listOf(
    javaScriptDeleteConversation,
    javaScriptOpenConversation,
    javaScriptReadConversation,
    javaScriptRenameConversation,
).sorted()

private const val javaScriptActiveConversation =
    "getter:CodexAgent#activeConversation:CodexConversation | null | undefined"
private const val javaScriptObserveActiveConversation =
    "method:CodexAgent#observeActiveConversation:" +
        "(listener: (conversation: CodexConversation | null | undefined) => void): CodexObservation"
private const val javaScriptListConversations =
    "method:CodexAgent#listConversations:" +
        "(signal?: AbortSignal | null | undefined): Promise<ReadonlyArray<AgentConversationSummary>>"
private val javaScriptConversationsEnvelope = setOf(
    javaScriptActiveConversation,
    javaScriptDeleteConversation,
    javaScriptListConversations,
    javaScriptObserveActiveConversation,
    javaScriptOpenConversation,
    javaScriptReadConversation,
    javaScriptRenameConversation,
)

private fun agentInvocationBaseSymbols(name: String): List<String> = listOf(
    javaScriptAgentInvocationType,
    "getter:AgentPluginInvocation#$name:string",
    "getter:AgentSkillInvocation#$name:string",
).sorted()

private fun flattenedValueProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val projectedSymbols = when {
        member.isExactProperty("AgentApprovalPreset", "displayName", "kotlin/String!!") ->
            listOf(javaScriptApprovalPresetDisplayName)
        member.exactAgentCapabilityMetadataSymbol() != null ->
            listOf(checkNotNull(member.exactAgentCapabilityMetadataSymbol()))
        member.exactAgentInvocationBaseName() != null ->
            agentInvocationBaseSymbols(checkNotNull(member.exactAgentInvocationBaseName()))
        member.isExactAgentMessageCapabilities() -> listOf(javaScriptAgentMessageCapabilities)
        member.isExactApiKeyAuthenticationMethodMember() -> listOf(javaScriptApiKeyAuthentication)
        member.isExactConversationSettingsMember() -> listOf(javaScriptOpenConversation)
        member.isExactConversationIdMember() -> javaScriptConversationIdSymbols
        member.isExactCodexClientInfoMember() -> listOf(javaScriptCreateCodexHost)
        member.isExactPathWorkspaceSelectionMember() -> listOf(javaScriptSelectWorkspace)
        member.isExactAgentSkillScopeDisplayName() -> listOf(javaScriptSkillScopeDisplayName)
        else -> return emptyList()
    }
    val hasExactInventory = if (member.isExactApiKeyAuthenticationMethodMember()) {
        hasExactAuthenticationOverloadInventory(symbols)
    } else {
        hasExactJavaScriptSymbolInventory(symbols, projectedSymbols)
    }
    if (!hasExactInventory) return emptyList()
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = projectedSymbols,
            scenarios = listOf(
                if (member.isExactAgentMessageCapabilities()) {
                    CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING
                } else {
                    CrossLanguageBindingScenario.VALUE_CONVERSION
                },
            ),
            requiresConsumerReference = true,
        )
    )
}

private fun agentTurnRequestProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val requestMember = member.isExactD047AgentTurnRequestMember()
    val send = member.isExactD047SendRequest()
    if ((!requestMember && !send) || !hasExactD047AgentTurnRequestInventory(symbols)) return emptyList()
    val projectedSymbols = if (send) javaScriptAgentTurnRequestSymbols else listOf(javaScriptAgentTurnRequestType)
    val scenarios = if (send) {
        listOf(
            CrossLanguageBindingScenario.ASYNC_SUCCESS,
            CrossLanguageBindingScenario.ASYNC_FAILURE,
            CrossLanguageBindingScenario.CANCELLATION,
            CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
        )
    } else {
        buildList {
            add(CrossLanguageBindingScenario.VALUE_CONVERSION)
            if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR ||
                member.name in setOf("capabilities", "invocations")
            ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
            if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR ||
                member.name in setOf("clientMessageId", "model", "effort", "serviceTier")
            ) add(CrossLanguageBindingScenario.NULLABILITY)
        }
    }
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = projectedSymbols,
            scenarios = scenarios,
            requiresConsumerReference = true,
            shareablePublicSymbols = setOf(javaScriptAgentTurnRequestType),
        ),
    )
}

private fun agentHookHandlerProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD048AgentHookHandlerMember() || !hasExactD048AgentHookHandlerInventory(symbols)) {
        return emptyList()
    }
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = listOf(javaScriptAgentHookHandlerType),
        scenarios = listOf(
            CrossLanguageBindingScenario.VALUE_CONVERSION,
            CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING,
        ),
        requiresConsumerReference = true,
        shareablePublicSymbols = setOf(javaScriptAgentHookHandlerType),
    ))
}

private fun CanonicalJavaScriptMember.isD048AgentHookHandlerSurfaceMember(): Boolean =
    simpleOwner.startsWith("AgentHookHandler.")

private fun CanonicalJavaScriptMember.isExactD048AgentHookHandlerMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return false
    return when (simpleOwner) {
        "AgentHookHandler.Agent", "AgentHookHandler.Prompt" ->
            kind == CanonicalJavaScriptMemberKind.OBJECT &&
                name == simpleOwner.substringAfterLast('.') && parameters.isEmpty() &&
                returnType == null && !isSuspend && propertyKind == null
        "AgentHookHandler.Command" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                "AgentHookHandler.Command",
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", false, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "command" -> isExactProperty("AgentHookHandler.Command", name, "kotlin/String!!")
                "isAsync" -> isExactProperty("AgentHookHandler.Command", name, "kotlin/Boolean!!")
                else -> false
            }
            else -> false
        }
        "AgentHookHandler.McpTool" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                "AgentHookHandler.McpTool",
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "server", "tool" -> isExactProperty(
                    "AgentHookHandler.McpTool",
                    name,
                    "kotlin/String!!",
                )
                else -> false
            }
            else -> false
        }
        else -> false
    }
}

private fun hasExactD048AgentHookHandlerInventory(symbols: List<JavaScriptPublicSymbol>): Boolean =
    hasExactJavaScriptSymbolInventory(symbols, listOf(javaScriptAgentHookHandlerType)) &&
        symbols.filter { it.owner == null && it.name == "AgentHookHandler" }
            .map(JavaScriptPublicSymbol::raw) == listOf(javaScriptAgentHookHandlerType)

private fun mcpServersProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD050McpServersMember() ||
        !hasExactJavaScriptSymbolInventory(symbols, javaScriptMcpServersSymbols)
    ) return emptyList()
    val projected = member.d050McpServersPublicSymbols()
    val scenarios = buildList {
        add(CrossLanguageBindingScenario.VALUE_CONVERSION)
        if (member.parameters.any { it.type.startsWith("kotlin.collections/") } || member.name in setOf(
                "arguments",
                "environment",
                "forwardedEnvironment",
                "headers",
                "environmentHeaders",
                "omitToolsFrom",
                "enabledTools",
                "disabledTools",
                "scopes",
                "tools",
                "configuration",
            )
        ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
        if (member.kind == CanonicalJavaScriptMemberKind.FUNCTION) {
            add(CrossLanguageBindingScenario.ASYNC_SUCCESS)
            add(CrossLanguageBindingScenario.ASYNC_FAILURE)
            add(CrossLanguageBindingScenario.CANCELLATION)
            add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
        } else if (member.simpleOwner == "CodexAgent" || member.simpleOwner == "CodexMcpServers") {
            add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
        }
    }
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = projected,
        scenarios = scenarios.distinct(),
        requiresConsumerReference = true,
    ))
}

private fun CanonicalJavaScriptMember.isD050McpServersSurfaceMember(): Boolean =
    simpleOwner in setOf(
        "AgentMcpTransport.Stdio",
        "AgentMcpTransport.Http",
        "AgentMcpServerConfiguration",
        "AgentMcpServer",
        "CodexMcpServers",
    ) || simpleOwner == "CodexAgent" && name == "mcpServers"

private fun CanonicalJavaScriptMember.isExactD050McpServersMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return false
    fun canonical(name: String, nullable: Boolean = false): String =
        "$canonicalAgentPackage/$name${if (nullable) "?" else "!!"}"
    fun list(type: String, nullable: Boolean = false): String =
        "kotlin.collections/List<INVARIANT:$type>${if (nullable) "?" else "!!"}"
    fun map(value: String, nullable: Boolean = false): String =
        "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:$value>" +
            if (nullable) "?" else "!!"
    return when (simpleOwner) {
        "AgentMcpTransport.Stdio" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!"), true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter(map("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter(
                        list(canonical("AgentMcpEnvironmentVariable")),
                        true,
                        false,
                    ),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "command" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "arguments" -> isExactProperty(simpleOwner, name, list("kotlin/String!!"))
                "workingDirectory" -> isExactProperty(simpleOwner, name, "kotlin/String?")
                "environment" -> isExactProperty(simpleOwner, name, map("kotlin/String!!", nullable = true))
                "forwardedEnvironment" ->
                    isExactProperty(simpleOwner, name, list(canonical("AgentMcpEnvironmentVariable")))
                else -> false
            }
            else -> false
        }
        "AgentMcpTransport.Http" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter(map("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter(map("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "url" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "bearerTokenEnvironmentVariable", "headersHelper" ->
                    isExactProperty(simpleOwner, name, "kotlin/String?")
                "headers", "environmentHeaders" ->
                    isExactProperty(simpleOwner, name, map("kotlin/String!!", nullable = true))
                else -> false
            }
            else -> false
        }
        "AgentMcpServerConfiguration" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpTransport"), false, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpAuthentication", true), true, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", true, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                    CanonicalJavaScriptParameter(
                        list(canonical("AgentMcpToolExposureSurface"), nullable = true),
                        true,
                        false,
                    ),
                    CanonicalJavaScriptParameter("kotlin/Double?", true, false),
                    CanonicalJavaScriptParameter("kotlin/Double?", true, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpToolApproval", true), true, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!", nullable = true), true, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpOauthConfiguration", true), true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter(
                        map(canonical("AgentMcpToolConfiguration")),
                        true,
                        false,
                    ),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "name", "environmentId" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "transport" -> isExactProperty(simpleOwner, name, canonical("AgentMcpTransport"))
                "authentication" ->
                    isExactProperty(simpleOwner, name, canonical("AgentMcpAuthentication", true))
                "isEnabled", "isRequired", "supportsParallelToolCalls" ->
                    isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
                "omitToolsFrom" -> isExactProperty(
                    simpleOwner,
                    name,
                    list(canonical("AgentMcpToolExposureSurface"), nullable = true),
                )
                "startupTimeoutSeconds", "toolTimeoutSeconds" ->
                    isExactProperty(simpleOwner, name, "kotlin/Double?")
                "defaultToolApproval" ->
                    isExactProperty(simpleOwner, name, canonical("AgentMcpToolApproval", true))
                "enabledTools", "disabledTools", "scopes" ->
                    isExactProperty(simpleOwner, name, list("kotlin/String!!", nullable = true))
                "oauth" -> isExactProperty(simpleOwner, name, canonical("AgentMcpOauthConfiguration", true))
                "oauthResource" -> isExactProperty(simpleOwner, name, "kotlin/String?")
                "tools" -> isExactProperty(simpleOwner, name, map(canonical("AgentMcpToolConfiguration")))
                else -> false
            }
            else -> false
        }
        "AgentMcpServer" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpAuthStatus"), false, false),
                    CanonicalJavaScriptParameter(canonical("AgentMcpServerConfiguration", true), true, false),
                    CanonicalJavaScriptParameter(canonical("AgentResourceOrigin"), true, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "name", "displayName" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "authStatus" -> isExactProperty(simpleOwner, name, canonical("AgentMcpAuthStatus"))
                "configuration" ->
                    isExactProperty(simpleOwner, name, canonical("AgentMcpServerConfiguration", true))
                "origin" -> isExactProperty(simpleOwner, name, canonical("AgentResourceOrigin"))
                "canRemove", "isAuthorized" -> isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
                else -> false
            }
            else -> false
        }
        "CodexMcpServers" -> when (name) {
            "isAvailable" -> isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
            "list" -> isExactFunction(
                simpleOwner,
                name,
                list(canonical("AgentMcpServer")),
                expectedSuspend = true,
                expectedParameters = emptyList(),
            )
            "add" -> isExactFunction(
                simpleOwner,
                name,
                canonical("AgentMcpServer"),
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter(canonical("AgentMcpServerConfiguration"), false, false),
                ),
            )
            "remove" -> isExactFunction(
                simpleOwner,
                name,
                "kotlin/Unit",
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter(canonical("AgentMcpServer"), false, false),
                ),
            )
            else -> false
        }
        "CodexAgent" -> name == "mcpServers" &&
            isExactProperty(simpleOwner, name, canonical("CodexMcpServers"))
        else -> false
    }
}

private fun CanonicalJavaScriptMember.d050McpServersPublicSymbols(): List<String> {
    val publicOwner = when (simpleOwner) {
        "AgentMcpTransport.Stdio" -> "AgentMcpStdioTransport"
        "AgentMcpTransport.Http" -> "AgentMcpHttpTransport"
        else -> simpleOwner
    }
    val expectedKind = when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> JavaScriptPublicSymbolKind.CONSTRUCTOR
        CanonicalJavaScriptMemberKind.FUNCTION -> JavaScriptPublicSymbolKind.METHOD
        CanonicalJavaScriptMemberKind.PROPERTY -> JavaScriptPublicSymbolKind.GETTER
        else -> error("Unsupported D050 MCP Servers capability kind: $key")
    }
    val memberSymbol = javaScriptMcpServersSymbols.single { raw ->
        val symbol = parseJavaScriptPublicSymbol(raw)
        symbol.kind == expectedKind && symbol.owner == publicOwner &&
            symbol.name == if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) "constructor" else name
    }
    return buildList {
        when {
            kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR -> add("class:$publicOwner")
            simpleOwner == "CodexMcpServers" && name == "isAvailable" -> add("class:CodexMcpServers")
        }
        if (simpleOwner == "AgentMcpServerConfiguration" && name == "transport") {
            add(javaScriptAgentMcpTransportType)
        }
        add(memberSymbol)
    }.sorted()
}

private fun agentFormFieldProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD057AgentFormFieldMember() ||
        !hasExactD057AgentFormFieldInventory(symbols)
    ) return emptyList()
    val projected = member.d057AgentFormFieldPublicSymbols()
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = projected,
        scenarios = buildList {
            add(CrossLanguageBindingScenario.VALUE_CONVERSION)
            if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR ||
                member.name in setOf("options", "defaultValue", "accepts")
            ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
            if (member.returnType?.endsWith('?') == true ||
                member.parameters.any { it.type.endsWith('?') }
            ) add(CrossLanguageBindingScenario.NULLABILITY)
        }.distinct(),
        shareablePublicSymbols = projected.filterTo(mutableSetOf()) { it == javaScriptAgentFormValueType },
        requiresConsumerReference = true,
    ))
}

private fun hasExactD057AgentFormFieldInventory(symbols: List<JavaScriptPublicSymbol>): Boolean =
    hasExactJavaScriptSymbolInventory(symbols, javaScriptAgentFormFieldSymbols) &&
        symbols.filter { symbol ->
            symbol.owner == "AgentFormField" ||
                symbol.kind == JavaScriptPublicSymbolKind.CLASS && symbol.name == "AgentFormField" ||
                symbol.owner == null && symbol.name == "AgentFormValue"
        }.map(JavaScriptPublicSymbol::raw) == javaScriptAgentFormFieldSymbols

private fun CanonicalJavaScriptMember.isD057AgentFormFieldSurfaceMember(): Boolean =
    simpleOwner == "AgentFormField"

private fun CanonicalJavaScriptMember.isExactD057AgentFormFieldMember(): Boolean {
    if (owner != "$canonicalAgentPackage/AgentFormField") return false
    fun canonical(name: String, nullable: Boolean = false): String =
        "$canonicalAgentPackage/$name${if (nullable) "?" else "!!"}"
    fun list(type: String): String = "kotlin.collections/List<INVARIANT:$type>!!"
    return when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
            simpleOwner,
            listOf(
                CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                CanonicalJavaScriptParameter("kotlin/String?", true, false),
                CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                CanonicalJavaScriptParameter(canonical("AgentFormFieldType"), false, false),
                CanonicalJavaScriptParameter(list(canonical("AgentFormOption")), true, false),
                CanonicalJavaScriptParameter(canonical("AgentFormValue", nullable = true), true, false),
                CanonicalJavaScriptParameter("kotlin/Double?", true, false),
                CanonicalJavaScriptParameter("kotlin/Double?", true, false),
                CanonicalJavaScriptParameter(canonical("AgentFormStringFormat", nullable = true), true, false),
                CanonicalJavaScriptParameter("kotlin/Long?", true, false),
                CanonicalJavaScriptParameter("kotlin/Long?", true, false),
                CanonicalJavaScriptParameter("kotlin/Long?", true, false),
                CanonicalJavaScriptParameter("kotlin/Long?", true, false),
                CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
            ),
        )
        CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
            "name", "title" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
            "description" -> isExactProperty(simpleOwner, name, "kotlin/String?")
            "isRequired", "allowsOther", "isSecret" ->
                isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
            "type" -> isExactProperty(simpleOwner, name, canonical("AgentFormFieldType"))
            "options" -> isExactProperty(simpleOwner, name, list(canonical("AgentFormOption")))
            "defaultValue" ->
                isExactProperty(simpleOwner, name, canonical("AgentFormValue", nullable = true))
            "minimum", "maximum" -> isExactProperty(simpleOwner, name, "kotlin/Double?")
            "format" ->
                isExactProperty(simpleOwner, name, canonical("AgentFormStringFormat", nullable = true))
            "minimumLength", "maximumLength", "minimumSelections", "maximumSelections" ->
                isExactProperty(simpleOwner, name, "kotlin/Long?")
            else -> false
        }
        CanonicalJavaScriptMemberKind.FUNCTION -> name == "accepts" && isExactFunction(
            simpleOwner,
            name,
            "kotlin/Boolean!!",
            expectedSuspend = false,
            expectedParameters = listOf(
                CanonicalJavaScriptParameter(canonical("AgentFormValue", nullable = true), false, false),
            ),
        )
        else -> false
    }
}

private fun CanonicalJavaScriptMember.d057AgentFormFieldPublicSymbols(): List<String> {
    val expectedKind = when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> JavaScriptPublicSymbolKind.CONSTRUCTOR
        CanonicalJavaScriptMemberKind.PROPERTY -> JavaScriptPublicSymbolKind.GETTER
        CanonicalJavaScriptMemberKind.FUNCTION -> JavaScriptPublicSymbolKind.METHOD
        else -> error("Unsupported D057 AgentFormField capability kind: $key")
    }
    val memberSymbol = javaScriptAgentFormFieldSymbols.single { raw ->
        val symbol = parseJavaScriptPublicSymbol(raw)
        symbol.kind == expectedKind && symbol.owner == simpleOwner &&
            symbol.name == if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) "constructor" else name
    }
    return buildList {
        if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) add("class:AgentFormField")
        if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR ||
            name == "defaultValue" || name == "accepts"
        ) add(javaScriptAgentFormValueType)
        add(memberSymbol)
    }.distinct().sorted()
}

private fun interactionsProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD059InteractionsMember() ||
        !hasExactD059InteractionsInventory(symbols)
    ) return emptyList()
    val projected = member.d059InteractionsPublicSymbols()
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = projected,
        scenarios = buildList {
            add(CrossLanguageBindingScenario.VALUE_CONVERSION)
            if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR || member.name in setOf(
                    "form",
                    "content",
                    "initialValues",
                    "validate",
                    "accept",
                    "accepts",
                    "pending",
                    "resolvingRequestIds",
                    "pendingFor",
                    "isResolving",
                    "state",
                    "approvals",
                    "elicitations",
                )
            ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
            if (member.returnType?.endsWith('?') == true ||
                member.parameters.any { it.type.endsWith('?') }
            ) add(CrossLanguageBindingScenario.NULLABILITY)
            if (member.simpleOwner == "CodexInteractions" ||
                member.simpleOwner == "CodexAgent" && member.name == "interactions"
            ) add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
            if (member.simpleOwner == "CodexInteractions" && member.kind == CanonicalJavaScriptMemberKind.FUNCTION) {
                add(CrossLanguageBindingScenario.ASYNC_SUCCESS)
                add(CrossLanguageBindingScenario.ASYNC_FAILURE)
                add(CrossLanguageBindingScenario.CANCELLATION)
            }
            if (member.simpleOwner == "CodexInteractions" && member.kind == CanonicalJavaScriptMemberKind.PROPERTY) {
                add(CrossLanguageBindingScenario.STATE_CURRENT_VALUE)
                add(CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE)
                add(CrossLanguageBindingScenario.IDENTITY)
            }
        }.distinct(),
        shareablePublicSymbols = projected.filterTo(mutableSetOf()) {
            it == javaScriptPendingInteractionType
        },
        requiresConsumerReference = true,
    ))
}

private fun hasExactD059InteractionsInventory(symbols: List<JavaScriptPublicSymbol>): Boolean {
    val exactOwners = setOf(
        "AgentElicitation",
        "AgentElicitationResponse",
        "AgentInteractionState",
        "AgentPendingApproval",
        "AgentPendingElicitation",
        "CodexInteractions",
    )
    return javaScriptInteractionsSymbols.distinct().size == javaScriptInteractionsSymbols.size &&
        symbols.filter { symbol ->
            symbol.owner in exactOwners ||
                symbol.kind == JavaScriptPublicSymbolKind.CLASS && symbol.name in exactOwners ||
                symbol.owner == "CodexAgent" && symbol.name == "interactions" ||
                symbol.owner == null && symbol.name == "AgentPendingInteraction"
        }.map(JavaScriptPublicSymbol::raw) == javaScriptInteractionsSymbols
}

private fun CanonicalJavaScriptMember.isD059InteractionsSurfaceMember(): Boolean =
    simpleOwner in setOf(
        "AgentElicitation",
        "AgentElicitationResponse",
        "AgentElicitationResponse.Companion",
        "AgentInteractionState",
        "AgentPendingApproval",
        "AgentPendingElicitation",
        "AgentPendingInteraction",
        "CodexInteractions",
    ) || simpleOwner == "CodexAgent" && name == "interactions"

private fun CanonicalJavaScriptMember.isExactD059InteractionsMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return false
    fun canonical(name: String, nullable: Boolean = false): String =
        "$canonicalAgentPackage/$name${if (nullable) "?" else "!!"}"
    fun list(type: String, nullable: Boolean = false): String =
        "kotlin.collections/List<INVARIANT:$type>${if (nullable) "?" else "!!"}"
    fun set(type: String): String = "kotlin.collections/Set<INVARIANT:$type>!!"
    fun map(value: String): String =
        "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:$value>!!"
    fun stateFlow(type: String): String = "kotlinx.coroutines.flow/StateFlow<INVARIANT:$type>!!"
    return when (simpleOwner) {
        "AgentElicitation" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(canonical("ConversationId"), false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(list(canonical("AgentFormField"), nullable = true), true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "requestId", "serverName", "message" ->
                    isExactProperty(simpleOwner, name, "kotlin/String!!")
                "conversationId" -> isExactProperty(simpleOwner, name, canonical("ConversationId"))
                "form" -> isExactProperty(simpleOwner, name, list(canonical("AgentFormField"), nullable = true))
                "url" -> isExactProperty(simpleOwner, name, "kotlin/String?")
                else -> false
            }
            CanonicalJavaScriptMemberKind.FUNCTION -> when (name) {
                "initialValues" -> isExactFunction(
                    simpleOwner,
                    name,
                    map(canonical("AgentFormValue")),
                    expectedSuspend = false,
                    expectedParameters = emptyList(),
                )
                "validate", "accept" -> isExactFunction(
                    simpleOwner,
                    name,
                    canonical(if (name == "validate") "AgentElicitationValidation" else "AgentElicitationResponse"),
                    expectedSuspend = false,
                    expectedParameters = listOf(
                        CanonicalJavaScriptParameter(map(canonical("AgentFormValue")), false, false),
                    ),
                )
                "accepts" -> isExactFunction(
                    simpleOwner,
                    name,
                    "kotlin/Boolean!!",
                    expectedSuspend = false,
                    expectedParameters = listOf(
                        CanonicalJavaScriptParameter(canonical("AgentElicitationResponse"), false, false),
                    ),
                )
                else -> false
            }
            else -> false
        }
        "AgentElicitationResponse" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(canonical("AgentElicitationAction"), false, false),
                    CanonicalJavaScriptParameter(map(canonical("AgentFormValue")), true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "action" -> isExactProperty(simpleOwner, name, canonical("AgentElicitationAction"))
                "content" -> isExactProperty(simpleOwner, name, map(canonical("AgentFormValue")))
                else -> false
            }
            else -> false
        }
        "AgentElicitationResponse.Companion" -> kind == CanonicalJavaScriptMemberKind.FUNCTION &&
            name in setOf("decline", "cancel") && isExactFunction(
                simpleOwner,
                name,
                canonical("AgentElicitationResponse"),
                expectedSuspend = false,
                expectedParameters = emptyList(),
            )
        "AgentPendingApproval" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(canonical("ConversationId"), false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "requestId", "title", "details" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "conversationId" -> isExactProperty(simpleOwner, name, canonical("ConversationId"))
                else -> false
            }
            else -> false
        }
        "AgentPendingElicitation" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(CanonicalJavaScriptParameter(canonical("AgentElicitation"), false, false)),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "requestId" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "conversationId" -> isExactProperty(simpleOwner, name, canonical("ConversationId"))
                "elicitation" -> isExactProperty(simpleOwner, name, canonical("AgentElicitation"))
                else -> false
            }
            else -> false
        }
        "AgentPendingInteraction" -> kind == CanonicalJavaScriptMemberKind.PROPERTY && when (name) {
            "requestId" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
            "conversationId" -> isExactProperty(simpleOwner, name, canonical("ConversationId"))
            else -> false
        }
        "AgentInteractionState" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(list(canonical("AgentPendingInteraction")), true, false),
                    CanonicalJavaScriptParameter(set("kotlin/String!!"), true, false),
                    CanonicalJavaScriptParameter(canonical("CodexFailure", nullable = true), true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "pending" -> isExactProperty(simpleOwner, name, list(canonical("AgentPendingInteraction")))
                "resolvingRequestIds" -> isExactProperty(simpleOwner, name, set("kotlin/String!!"))
                "failure" -> isExactProperty(simpleOwner, name, canonical("CodexFailure", nullable = true))
                else -> false
            }
            CanonicalJavaScriptMemberKind.FUNCTION -> when (name) {
                "pendingFor" -> isExactFunction(
                    simpleOwner,
                    name,
                    list(canonical("AgentPendingInteraction")),
                    expectedSuspend = false,
                    expectedParameters = listOf(
                        CanonicalJavaScriptParameter(canonical("ConversationId"), false, false),
                    ),
                )
                "isResolving" -> isExactFunction(
                    simpleOwner,
                    name,
                    "kotlin/Boolean!!",
                    expectedSuspend = false,
                    expectedParameters = listOf(
                        CanonicalJavaScriptParameter(canonical("AgentPendingInteraction"), false, false),
                    ),
                )
                else -> false
            }
            else -> false
        }
        "CodexInteractions" -> when (kind) {
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "state" -> isExactProperty(simpleOwner, name, stateFlow(canonical("AgentInteractionState")))
                "approvals" -> isExactProperty(
                    simpleOwner,
                    name,
                    stateFlow(list(canonical("AgentPendingApproval"))),
                )
                "elicitations" -> isExactProperty(
                    simpleOwner,
                    name,
                    stateFlow(list(canonical("AgentPendingElicitation"))),
                )
                else -> false
            }
            CanonicalJavaScriptMemberKind.FUNCTION -> when (name) {
                "openUrl" -> isExactFunction(
                    simpleOwner,
                    name,
                    "kotlin/Unit",
                    expectedSuspend = true,
                    expectedParameters = listOf(
                        CanonicalJavaScriptParameter(canonical("AgentPendingElicitation"), false, false),
                    ),
                )
                "resolve" -> parameters.size == 2 && isExactFunction(
                    simpleOwner,
                    name,
                    "kotlin/Unit",
                    expectedSuspend = true,
                    expectedParameters = when (parameters.first().type) {
                        canonical("AgentPendingApproval") -> listOf(
                            CanonicalJavaScriptParameter(canonical("AgentPendingApproval"), false, false),
                            CanonicalJavaScriptParameter(canonical("AgentApprovalDecision"), false, false),
                        )
                        canonical("AgentPendingElicitation") -> listOf(
                            CanonicalJavaScriptParameter(canonical("AgentPendingElicitation"), false, false),
                            CanonicalJavaScriptParameter(canonical("AgentElicitationResponse"), false, false),
                        )
                        else -> return false
                    },
                )
                else -> false
            }
            else -> false
        }
        "CodexAgent" -> name == "interactions" &&
            isExactProperty(simpleOwner, name, canonical("CodexInteractions"))
        else -> false
    }
}

private fun CanonicalJavaScriptMember.d059InteractionsPublicSymbols(): List<String> {
    fun exact(kind: JavaScriptPublicSymbolKind, owner: String, name: String): String {
        val matches = javaScriptInteractionsSymbols.filter { raw ->
            val symbol = parseJavaScriptPublicSymbol(raw)
            symbol.kind == kind && symbol.owner == owner && symbol.name == name
        }
        if (matches.size == 1) return matches.single()
        check(owner == "CodexInteractions" && name == "resolve" && matches.size == 2)
        val pendingType = if (parameters.first().type.endsWith("/AgentPendingApproval!!")) {
            "AgentPendingApproval"
        } else "AgentPendingElicitation"
        val parameterName = if (pendingType == "AgentPendingApproval") "approval" else "elicitation"
        return matches.single { "$parameterName: $pendingType" in it }
    }
    val owner = simpleOwner.removeSuffix(".Companion")
    val expectedKind = when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> JavaScriptPublicSymbolKind.CONSTRUCTOR
        CanonicalJavaScriptMemberKind.PROPERTY -> JavaScriptPublicSymbolKind.GETTER
        CanonicalJavaScriptMemberKind.FUNCTION -> JavaScriptPublicSymbolKind.METHOD
        else -> error("Unsupported D059 Interactions capability kind: $key")
    }
    if (simpleOwner == "AgentPendingInteraction") return listOf(javaScriptPendingInteractionType)
    val publicName = if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) "constructor" else name
    return buildList {
        if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) add("class:$owner")
        if (simpleOwner == "CodexAgent" && name == "interactions") add("class:CodexInteractions")
        if (simpleOwner == "CodexInteractions" && kind == CanonicalJavaScriptMemberKind.PROPERTY) {
            val observer = when (name) {
                "state" -> "observeState"
                "approvals" -> "observeApprovals"
                "elicitations" -> "observeElicitations"
                else -> error("Unsupported D059 Interactions state property: $key")
            }
            add(exact(JavaScriptPublicSymbolKind.METHOD, owner, observer))
        }
        add(exact(expectedKind, owner, publicName))
    }.sorted()
}

private fun pluginsProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD054PluginsMember() || !hasExactD054PluginsInventory(symbols)) return emptyList()
    val scenarios = buildList {
        add(CrossLanguageBindingScenario.VALUE_CONVERSION)
        if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR || member.name in setOf(
                "plugins",
                "errors",
                "capabilities",
                "skills",
                "connectors",
                "mcpServers",
                "connectorsNeedingAuthentication",
            )
        ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
        if (member.returnType?.endsWith("?") == true ||
            member.parameters.any { it.type.endsWith("?") }
        ) {
            add(CrossLanguageBindingScenario.NULLABILITY)
        }
        if (member.kind == CanonicalJavaScriptMemberKind.FUNCTION) {
            add(CrossLanguageBindingScenario.ASYNC_SUCCESS)
            add(CrossLanguageBindingScenario.ASYNC_FAILURE)
            add(CrossLanguageBindingScenario.CANCELLATION)
            add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
        } else if (member.simpleOwner == "CodexPlugins" || member.simpleOwner == "CodexAgent") {
            add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
        }
    }
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = member.d054PluginsPublicSymbols(),
        scenarios = scenarios.distinct(),
        requiresConsumerReference = true,
    ))
}

private fun CanonicalJavaScriptMember.isD054PluginsSurfaceMember(): Boolean =
    simpleOwner in setOf(
        "AgentPluginReference",
        "AgentPluginCatalog",
        "AgentPluginSummary",
        "AgentPluginDetail",
        "AgentPluginSkill",
        "AgentPluginInstallResult",
        "CodexPlugins",
    ) || simpleOwner == "CodexAgent" && name == "plugins"

private fun CanonicalJavaScriptMember.isExactD054PluginsMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return false
    fun canonical(name: String, nullable: Boolean = false): String =
        "$canonicalAgentPackage/$name${if (nullable) "?" else "!!"}"
    fun list(type: String): String = "kotlin.collections/List<INVARIANT:$type>!!"
    return when (simpleOwner) {
        "AgentPluginReference" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "id", "name", "marketplaceName", "uri" ->
                    isExactProperty(simpleOwner, name, "kotlin/String!!")
                "marketplacePath", "remotePluginId" ->
                    isExactProperty(simpleOwner, name, "kotlin/String?")
                else -> false
            }
            else -> false
        }
        "AgentPluginCatalog" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(list(canonical("AgentPluginSummary")), false, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!"), true, false),
                    CanonicalJavaScriptParameter(canonical("AgentCatalogFreshness"), true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "plugins" -> isExactProperty(simpleOwner, name, list(canonical("AgentPluginSummary")))
                "errors" -> isExactProperty(simpleOwner, name, list("kotlin/String!!"))
                "freshness" -> isExactProperty(simpleOwner, name, canonical("AgentCatalogFreshness"))
                else -> false
            }
            else -> false
        }
        "AgentPluginSummary" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginReference"), false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", false, false),
                    CanonicalJavaScriptParameter(canonical("AgentPluginInstallPolicy"), false, false),
                    CanonicalJavaScriptParameter(canonical("AgentPluginAuthPolicy"), false, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", false, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!"), true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "reference" -> isExactProperty(simpleOwner, name, canonical("AgentPluginReference"))
                "displayName", "description" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "isInstalled", "isEnabled", "isAvailable" ->
                    isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
                "installPolicy" ->
                    isExactProperty(simpleOwner, name, canonical("AgentPluginInstallPolicy"))
                "authPolicy" -> isExactProperty(simpleOwner, name, canonical("AgentPluginAuthPolicy"))
                "capabilities" -> isExactProperty(simpleOwner, name, list("kotlin/String!!"))
                "brandColor", "privacyPolicyUrl", "termsOfServiceUrl", "websiteUrl" ->
                    isExactProperty(simpleOwner, name, "kotlin/String?")
                else -> false
            }
            else -> false
        }
        "AgentPluginDetail" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginSummary"), false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter(list(canonical("AgentPluginSkill")), false, false),
                    CanonicalJavaScriptParameter(list(canonical("AgentConnector")), false, false),
                    CanonicalJavaScriptParameter(list("kotlin/String!!"), false, false),
                    CanonicalJavaScriptParameter("kotlin/Int!!", false, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "summary" -> isExactProperty(simpleOwner, name, canonical("AgentPluginSummary"))
                "description" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "skills" -> isExactProperty(simpleOwner, name, list(canonical("AgentPluginSkill")))
                "connectors" -> isExactProperty(simpleOwner, name, list(canonical("AgentConnector")))
                "mcpServers" -> isExactProperty(simpleOwner, name, list("kotlin/String!!"))
                "hookCount" -> isExactProperty(simpleOwner, name, "kotlin/Int!!")
                else -> false
            }
            else -> false
        }
        "AgentPluginSkill" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", false, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "name", "description" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                "isEnabled" -> isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
                "path" -> isExactProperty(simpleOwner, name, "kotlin/String?")
                else -> false
            }
            else -> false
        }
        "AgentPluginInstallResult" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginAuthPolicy"), false, false),
                    CanonicalJavaScriptParameter(list(canonical("AgentConnector")), false, false),
                    CanonicalJavaScriptParameter("kotlin/String?", true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "authPolicy" -> isExactProperty(simpleOwner, name, canonical("AgentPluginAuthPolicy"))
                "connectorsNeedingAuthentication" ->
                    isExactProperty(simpleOwner, name, list(canonical("AgentConnector")))
                "message" -> isExactProperty(simpleOwner, name, "kotlin/String?")
                else -> false
            }
            else -> false
        }
        "CodexPlugins" -> when (name) {
            "isAvailable" -> isExactProperty(simpleOwner, name, "kotlin/Boolean!!")
            "list" -> isExactFunction(
                simpleOwner,
                name,
                canonical("AgentPluginCatalog"),
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter("kotlin/Boolean!!", true, false),
                ),
            )
            "read" -> isExactFunction(
                simpleOwner,
                name,
                canonical("AgentPluginDetail"),
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginReference"), false, false),
                ),
            )
            "install" -> isExactFunction(
                simpleOwner,
                name,
                canonical("AgentPluginInstallResult"),
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginReference"), false, false),
                ),
            )
            "uninstall" -> isExactFunction(
                simpleOwner,
                name,
                "kotlin/Unit",
                expectedSuspend = true,
                expectedParameters = listOf(
                    CanonicalJavaScriptParameter(canonical("AgentPluginReference"), false, false),
                ),
            )
            else -> false
        }
        "CodexAgent" -> name == "plugins" && isExactProperty(simpleOwner, name, canonical("CodexPlugins"))
        else -> false
    }
}

private fun hasExactD054PluginsInventory(symbols: List<JavaScriptPublicSymbol>): Boolean {
    if (!hasExactJavaScriptSymbolInventory(symbols, javaScriptPluginsSymbols)) return false
    val publicOwners = setOf(
        "AgentPluginReference",
        "AgentPluginCatalog",
        "AgentPluginSummary",
        "AgentPluginDetail",
        "AgentPluginSkill",
        "AgentPluginInstallResult",
        "CodexPlugins",
    )
    return symbols.filter { symbol ->
        symbol.owner in publicOwners ||
            symbol.kind == JavaScriptPublicSymbolKind.CLASS && symbol.name in publicOwners ||
            symbol.owner == "CodexAgent" && symbol.name == "plugins"
    }.map(JavaScriptPublicSymbol::raw) == javaScriptPluginsSymbols
}

private fun CanonicalJavaScriptMember.d054PluginsPublicSymbols(): List<String> {
    val expectedKind = when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> JavaScriptPublicSymbolKind.CONSTRUCTOR
        CanonicalJavaScriptMemberKind.FUNCTION -> JavaScriptPublicSymbolKind.METHOD
        CanonicalJavaScriptMemberKind.PROPERTY -> JavaScriptPublicSymbolKind.GETTER
        else -> error("Unsupported D054 Plugins capability kind: $key")
    }
    val memberSymbol = javaScriptPluginsSymbols.single { raw ->
        val symbol = parseJavaScriptPublicSymbol(raw)
        symbol.kind == expectedKind && symbol.owner == simpleOwner &&
            symbol.name == if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) "constructor" else name
    }
    return buildList {
        if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR ||
            simpleOwner == "CodexPlugins" && name == "isAvailable"
        ) add("class:$simpleOwner")
        add(memberSymbol)
    }.sorted()
}

private fun integrationAuthorizationProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactD051IntegrationAuthorizationMember() ||
        !hasExactJavaScriptSymbolInventory(symbols, javaScriptIntegrationAuthorizationSymbols)
    ) return emptyList()
    val projected = member.d051IntegrationAuthorizationPublicSymbols()
    val stateFlow = member.simpleOwner == "CodexIntegrationAuthorization" &&
        member.kind == CanonicalJavaScriptMemberKind.PROPERTY
    val scenarios = buildList {
        add(CrossLanguageBindingScenario.VALUE_CONVERSION)
        if (member.simpleOwner == "AgentIntegrationAuthorizationState") {
            add(CrossLanguageBindingScenario.NULLABILITY)
            add(CrossLanguageBindingScenario.STRUCTURED_FAILURE)
        }
        if (stateFlow) {
            add(CrossLanguageBindingScenario.STATE_CURRENT_VALUE)
            add(CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE)
            add(CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION)
        }
        if (member.kind == CanonicalJavaScriptMemberKind.FUNCTION) {
            add(CrossLanguageBindingScenario.ASYNC_SUCCESS)
            add(CrossLanguageBindingScenario.ASYNC_FAILURE)
            add(CrossLanguageBindingScenario.CANCELLATION)
        }
        if (member.simpleOwner == "CodexIntegrationAuthorization" || member.simpleOwner == "CodexAgent") {
            add(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP)
        }
        if (member.simpleOwner in setOf(
                "AgentIntegration",
                "AgentIntegration.Connector",
                "AgentIntegration.McpServer",
                "AgentIntegrationAuthorizationState",
            )
        ) add(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING)
    }
    val shareable = projected.filterTo(mutableSetOf()) { symbol ->
        symbol == javaScriptAgentIntegrationType ||
            symbol.startsWith("getter:AgentConnectorIntegration#id:") ||
            symbol.startsWith("getter:AgentConnectorIntegration#displayName:") ||
            symbol.startsWith("getter:AgentMcpServerIntegration#id:") ||
            symbol.startsWith("getter:AgentMcpServerIntegration#displayName:")
    }
    return listOf(JavaScriptProjectionCandidate(
        publicSymbols = projected,
        scenarios = scenarios.distinct(),
        requiresConsumerReference = true,
        shareablePublicSymbols = shareable,
    ))
}

private fun CanonicalJavaScriptMember.isD051IntegrationAuthorizationSurfaceMember(): Boolean =
    simpleOwner in setOf(
        "AgentIntegration",
        "AgentIntegration.Connector",
        "AgentIntegration.McpServer",
        "AgentIntegrationAuthorizationState",
        "CodexIntegrationAuthorization",
    ) || simpleOwner == "CodexAgent" && name == "integrationAuthorization"

private fun CanonicalJavaScriptMember.isExactD051IntegrationAuthorizationMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return false
    fun canonical(name: String, nullable: Boolean = false): String =
        "$canonicalAgentPackage/$name${if (nullable) "?" else "!!"}"
    return when (simpleOwner) {
        "AgentIntegration" -> kind == CanonicalJavaScriptMemberKind.PROPERTY &&
            name in setOf("id", "displayName") &&
            isExactProperty(simpleOwner, name, "kotlin/String!!")
        "AgentIntegration.Connector" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(CanonicalJavaScriptParameter(canonical("AgentConnector"), false, false)),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "connector" -> isExactProperty(simpleOwner, name, canonical("AgentConnector"))
                "id", "displayName" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                else -> false
            }
            else -> false
        }
        "AgentIntegration.McpServer" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(CanonicalJavaScriptParameter(canonical("AgentMcpServer"), false, false)),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "server" -> isExactProperty(simpleOwner, name, canonical("AgentMcpServer"))
                "id", "displayName" -> isExactProperty(simpleOwner, name, "kotlin/String!!")
                else -> false
            }
            else -> false
        }
        "AgentIntegrationAuthorizationState" -> when (kind) {
            CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
                simpleOwner,
                listOf(
                    CanonicalJavaScriptParameter(canonical("AgentIntegrationAuthorizationStatus"), true, false),
                    CanonicalJavaScriptParameter(canonical("AgentIntegration", nullable = true), true, false),
                    CanonicalJavaScriptParameter(canonical("CodexFailure", nullable = true), true, false),
                ),
            )
            CanonicalJavaScriptMemberKind.PROPERTY -> when (name) {
                "status" -> isExactProperty(
                    simpleOwner,
                    name,
                    canonical("AgentIntegrationAuthorizationStatus"),
                )
                "target" -> isExactProperty(simpleOwner, name, canonical("AgentIntegration", nullable = true))
                "failure" -> isExactProperty(simpleOwner, name, canonical("CodexFailure", nullable = true))
                else -> false
            }
            else -> false
        }
        "CodexIntegrationAuthorization" -> when (name) {
            "state" -> isExactProperty(
                simpleOwner,
                name,
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:" +
                    canonical("AgentIntegrationAuthorizationState") + ">!!",
            )
            "active" -> isExactProperty(
                simpleOwner,
                name,
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:" +
                    canonical("AgentIntegration", nullable = true) + ">!!",
            )
            "isAuthorizing" -> isExactProperty(
                simpleOwner,
                name,
                "kotlinx.coroutines.flow/StateFlow<INVARIANT:kotlin/Boolean!!>!!",
            )
            "authorize" -> isExactFunction(
                simpleOwner,
                name,
                "kotlin/Unit",
                expectedSuspend = true,
                expectedParameters = listOf(CanonicalJavaScriptParameter("^A1", false, false)),
            ) && key.contains(
                "|abi=$canonicalAgentPackage/CodexIntegrationAuthorization.authorize|" +
                    "authorize(0:0){0§<$canonicalAgentPackage.AgentIntegration>}[0]|",
            )
            "cancel" -> isExactFunction(
                simpleOwner,
                name,
                "kotlin/Unit",
                expectedSuspend = true,
                expectedParameters = emptyList(),
            )
            else -> false
        }
        "CodexAgent" -> name == "integrationAuthorization" &&
            isExactProperty(simpleOwner, name, canonical("CodexIntegrationAuthorization"))
        else -> false
    }
}

private fun CanonicalJavaScriptMember.d051IntegrationAuthorizationPublicSymbols(): List<String> {
    fun symbol(kind: JavaScriptPublicSymbolKind, owner: String, name: String): String =
        javaScriptIntegrationAuthorizationSymbols.single { raw ->
            parseJavaScriptPublicSymbol(raw).let {
                it.kind == kind && it.owner == owner && it.name == name
            }
        }
    return when (simpleOwner) {
        "AgentIntegration" -> listOf(
            javaScriptAgentIntegrationType,
            symbol(JavaScriptPublicSymbolKind.GETTER, "AgentConnectorIntegration", name),
            symbol(JavaScriptPublicSymbolKind.GETTER, "AgentMcpServerIntegration", name),
        )
        "AgentIntegration.Connector", "AgentIntegration.McpServer" -> {
            val publicOwner = if (simpleOwner.endsWith("Connector")) {
                "AgentConnectorIntegration"
            } else {
                "AgentMcpServerIntegration"
            }
            if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) listOf(
                "class:$publicOwner",
                symbol(JavaScriptPublicSymbolKind.CONSTRUCTOR, publicOwner, "constructor"),
            ) else listOf(symbol(JavaScriptPublicSymbolKind.GETTER, publicOwner, name))
        }
        "AgentIntegrationAuthorizationState" -> if (kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) {
            listOf(
                "class:AgentIntegrationAuthorizationState",
                symbol(
                    JavaScriptPublicSymbolKind.CONSTRUCTOR,
                    "AgentIntegrationAuthorizationState",
                    "constructor",
                ),
            )
        } else listOf(symbol(JavaScriptPublicSymbolKind.GETTER, simpleOwner, name))
        "CodexIntegrationAuthorization" -> when (kind) {
            CanonicalJavaScriptMemberKind.PROPERTY -> buildList {
                if (name == "state") add("class:CodexIntegrationAuthorization")
                add(symbol(JavaScriptPublicSymbolKind.GETTER, simpleOwner, name))
                add(symbol(
                    JavaScriptPublicSymbolKind.METHOD,
                    simpleOwner,
                    when (name) {
                        "state" -> "observeState"
                        "active" -> "observeActive"
                        else -> "observeAuthorizing"
                    },
                ))
            }
            CanonicalJavaScriptMemberKind.FUNCTION ->
                listOf(symbol(JavaScriptPublicSymbolKind.METHOD, simpleOwner, name))
            else -> error("Unsupported integration authorization capability: $key")
        }
        "CodexAgent" -> listOf(symbol(JavaScriptPublicSymbolKind.GETTER, simpleOwner, name))
        else -> error("Unsupported integration authorization capability: $key")
    }.sorted()
}

private fun CanonicalJavaScriptMember.isD047AgentTurnRequestSurfaceMember(): Boolean =
    simpleOwner == "AgentTurnRequest" ||
        simpleOwner == "CodexConversation" && name == "send" &&
        parameters.any { "/AgentTurnRequest" in it.type }

private fun CanonicalJavaScriptMember.isExactD047AgentTurnRequestMember(): Boolean {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage || simpleOwner != "AgentTurnRequest") return false
    val canonical = { name: String -> "$canonicalAgentPackage/$name!!" }
    val expectedProperties = mapOf(
        "prompt" to "kotlin/String!!",
        "clientMessageId" to "kotlin/String?",
        "model" to "kotlin/String?",
        "effort" to "kotlin/String?",
        "serviceTier" to "kotlin/String?",
        "approvalPreset" to canonical("AgentApprovalPreset"),
        "capabilities" to
            "kotlin.collections/Set<INVARIANT:${canonical("AgentCapability")}>!!",
        "invocations" to
            "kotlin.collections/List<INVARIANT:${canonical("AgentInvocation")}>!!",
        "collaborationMode" to canonical("AgentCollaborationMode"),
    )
    return when (kind) {
        CanonicalJavaScriptMemberKind.CONSTRUCTOR -> isExactConstructor(
            "AgentTurnRequest",
            listOf(
                CanonicalJavaScriptParameter("kotlin/String!!", false, false),
                CanonicalJavaScriptParameter("kotlin/String?", true, false),
                CanonicalJavaScriptParameter("kotlin/String?", true, false),
                CanonicalJavaScriptParameter("kotlin/String?", true, false),
                CanonicalJavaScriptParameter("kotlin/String?", true, false),
                CanonicalJavaScriptParameter(canonical("AgentApprovalPreset"), true, false),
                CanonicalJavaScriptParameter(
                    "kotlin.collections/Set<INVARIANT:${canonical("AgentCapability")}>!!",
                    true,
                    false,
                ),
                CanonicalJavaScriptParameter(
                    "kotlin.collections/List<INVARIANT:${canonical("AgentInvocation")}>!!",
                    true,
                    false,
                ),
                CanonicalJavaScriptParameter(canonical("AgentCollaborationMode"), true, false),
            ),
        )
        CanonicalJavaScriptMemberKind.PROPERTY -> expectedProperties[name]?.let { type ->
            isExactProperty("AgentTurnRequest", name, type)
        } == true
        else -> false
    }
}

private fun CanonicalJavaScriptMember.isExactD047SendRequest(): Boolean =
    owner == "$canonicalAgentPackage/CodexConversation" && isExactFunction(
        expectedOwner = "CodexConversation",
        expectedName = "send",
        expectedReturnType = "kotlin/Unit",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalAgentPackage/AgentTurnRequest!!",
                hasDefault = false,
                isVararg = false,
            ),
        ),
    )

private fun hasExactD047AgentTurnRequestInventory(symbols: List<JavaScriptPublicSymbol>): Boolean {
    if (!hasExactJavaScriptSymbolInventory(symbols, javaScriptAgentTurnRequestSymbols)) return false
    val related = symbols.filter { symbol ->
        symbol.owner == "AgentTurnRequest" || symbol.owner == null && symbol.name == "AgentTurnRequest" ||
            symbol.owner == "CodexConversation" && symbol.name == "sendRequest"
    }.map(JavaScriptPublicSymbol::raw).sorted()
    return related == javaScriptAgentTurnRequestSymbols
}

private fun hostStateFlatteningProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val leaves = member.exactD044HostStateLeaves() ?: return emptyList()
    val projectedSymbols = (javaScriptHostStateEnvelope + javaScriptHostStateStatus + leaves).sorted()
    if (!hasExactD044HostStateInventory(symbols, projectedSymbols)) return emptyList()
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = projectedSymbols,
            scenarios = javaScriptStateScenarios + CrossLanguageBindingScenario.VALUE_CONVERSION,
            requiresConsumerReference = true,
            shareablePublicSymbols = projectedSymbols.toSet().intersect(javaScriptHostStateSharedSymbols),
        ),
    )
}

private fun conversationsFlatteningProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactConversationsProperty()) return emptyList()
    val projectedSymbols = javaScriptConversationsEnvelope.sorted()
    if (!hasExactD045ConversationInventory(symbols, projectedSymbols)) return emptyList()
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = projectedSymbols,
            scenarios = listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP),
            requiresConsumerReference = true,
            shareablePublicSymbols = javaScriptConversationsEnvelope,
        ),
    )
}

private fun hasExactD045ConversationInventory(
    symbols: List<JavaScriptPublicSymbol>,
    expectedSymbols: List<String>,
): Boolean = hasExactJavaScriptSymbolInventory(symbols, expectedSymbols) && expectedSymbols.all { raw ->
    val expected = parseJavaScriptPublicSymbol(raw)
    symbols.filter { it.owner == expected.owner && it.name == expected.name }
        .map(JavaScriptPublicSymbol::raw) == listOf(raw)
}

private fun CanonicalJavaScriptMember.isExactConversationsProperty(): Boolean =
    owner == "$canonicalAgentPackage/CodexAgent" && isExactProperty(
        "CodexAgent",
        "conversations",
        "$canonicalAgentPackage/CodexConversations!!",
    )

private fun hasExactD044HostStateInventory(
    symbols: List<JavaScriptPublicSymbol>,
    expectedSymbols: List<String>,
): Boolean = hasExactJavaScriptSymbolInventory(symbols, expectedSymbols) && expectedSymbols.all { raw ->
    val expected = parseJavaScriptPublicSymbol(raw)
    symbols.filter { it.owner == expected.owner && it.name == expected.name }
        .map(JavaScriptPublicSymbol::raw) == listOf(raw)
}

private fun CanonicalJavaScriptMember.isD044HostStateOwner(): Boolean = simpleOwner in setOf(
    "CodexHostState.Failed",
    "CodexHostState.Preparing",
    "CodexHostState.Ready",
    "CodexHostState.WorkspaceRequired",
    "CodexWorkspaceResolution.Available",
    "CodexWorkspaceResolution.SelectionRequired",
)

private fun CanonicalJavaScriptMember.exactD044HostStateLeaves(): Set<String>? {
    if (owner.substringBeforeLast('/') != canonicalAgentPackage) return null
    return when {
        isExactProperty("CodexHostState.Preparing", "workspace", "$canonicalAgentPackage/CodexWorkspace!!") ||
            isExactProperty(
                "CodexWorkspaceResolution.Available",
                "workspace",
                "$canonicalAgentPackage/CodexWorkspace!!",
            ) ||
            isExactProperty("CodexHostState.Failed", "workspace", "$canonicalAgentPackage/CodexWorkspace?") ->
            setOf(javaScriptHostStateWorkspace)
        isExactProperty("CodexHostState.Ready", "agent", "$canonicalAgentPackage/CodexAgent!!") ->
            setOf(javaScriptHostStateAgent)
        isExactProperty("CodexHostState.Failed", "failure", "$canonicalAgentPackage/CodexFailure!!") ->
            setOf(javaScriptHostStateFailure)
        isExactProperty(
            "CodexHostState.WorkspaceRequired",
            "requirement",
            "$canonicalAgentPackage/CodexWorkspaceResolution.SelectionRequired!!",
        ) -> setOf(javaScriptHostStateSelectionReason, javaScriptHostStateSelectionMessage)
        isExactProperty(
            "CodexWorkspaceResolution.SelectionRequired",
            "reason",
            "$canonicalAgentPackage/CodexWorkspaceSelectionReason!!",
        ) -> setOf(javaScriptHostStateSelectionReason)
        isExactProperty("CodexWorkspaceResolution.SelectionRequired", "message", "kotlin/String!!") ->
            setOf(javaScriptHostStateSelectionMessage)
        else -> null
    }
}

private fun CanonicalJavaScriptMember.isExactD044HostLifecycleState(): Boolean =
    owner == "$canonicalAgentPackage/CodexHost" && isExactProperty(
        "CodexHost",
        "lifecycleState",
        "kotlinx.coroutines.flow/StateFlow<INVARIANT:$canonicalAgentPackage/CodexHostState!!>!!",
    )

private fun CanonicalJavaScriptMember.exactAgentCapabilityMetadataSymbol(): String? {
    if (owner != "io.github.codex_agent_labs.codexagent.agent/AgentCapability") return null
    return when {
        isExactProperty("AgentCapability", "displayLabel", "kotlin/String!!") ->
            javaScriptAgentCapabilityDisplayLabel
        isExactProperty("AgentCapability", "icon", "kotlin/String?") -> javaScriptAgentCapabilityIcon
        isExactProperty("AgentCapability", "id", "kotlin/String!!") -> javaScriptAgentCapabilityId
        isExactProperty("AgentCapability", "promptLabel", "kotlin/String!!") ->
            javaScriptAgentCapabilityPromptLabel
        else -> null
    }
}

private fun CanonicalJavaScriptMember.exactAgentInvocationBaseName(): String? {
    if (owner != "io.github.codex_agent_labs.codexagent.agent/AgentInvocation") return null
    return listOf("key", "name").singleOrNull { isExactProperty("AgentInvocation", it, "kotlin/String!!") }
}

private fun CanonicalJavaScriptMember.isExactAgentMessageCapabilities(): Boolean =
    owner == "io.github.codex_agent_labs.codexagent.agent/AgentMessage" && isExactProperty(
        "AgentMessage",
        "capabilities",
        "kotlin.collections/Set<INVARIANT:io.github.codex_agent_labs.codexagent.agent/AgentCapability!!>!!",
    )

private fun CanonicalJavaScriptMember.requiresExactD043FlattenedProjection(): Boolean =
    exactAgentCapabilityMetadataSymbol() != null || exactAgentInvocationBaseName() != null ||
        isExactAgentMessageCapabilities()

private fun CanonicalJavaScriptMember.isD043SurfaceMember(): Boolean = when (simpleOwner) {
    "AgentCapability" -> name in setOf("displayLabel", "icon", "id", "promptLabel")
    "AgentInvocation" -> name in setOf("key", "name")
    "AgentInvocation.Plugin" -> name == "<init>" || name in setOf("key", "name", "uri")
    "AgentInvocation.Skill" -> name == "<init>" || name in setOf("key", "name", "path")
    "AgentMessage" -> name in setOf("capabilities", "collaborationMode", "invocations")
    else -> false
}

private fun CanonicalJavaScriptMember.isExactD043SurfaceMember(): Boolean {
    if (owner.substringBeforeLast('/') != "io.github.codex_agent_labs.codexagent.agent") return false
    return exactAgentCapabilityMetadataSymbol() != null || exactAgentInvocationBaseName() != null ||
        isExactAgentMessageCapabilities() ||
        isExactProperty("AgentMessage", "collaborationMode", "$canonicalAgentPackage/AgentCollaborationMode!!") ||
        isExactProperty(
            "AgentMessage",
            "invocations",
            "kotlin.collections/List<INVARIANT:$canonicalAgentPackage/AgentInvocation!!>!!",
        ) || isExactConstructor(
            "AgentInvocation.Plugin",
            List(2) { CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false) },
        ) || listOf("key", "name", "uri").any {
            isExactProperty("AgentInvocation.Plugin", it, "kotlin/String!!")
        } || isExactConstructor(
            "AgentInvocation.Skill",
            List(2) { CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false) },
        ) || listOf("key", "name", "path").any {
            isExactProperty("AgentInvocation.Skill", it, "kotlin/String!!")
        }
}

private const val canonicalAgentPackage = "io.github.codex_agent_labs.codexagent.agent"

private fun CanonicalJavaScriptMember.isExactConversationSettingsMember(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactConstructor(
        "AgentConversationSettings",
        listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/AgentApprovalPreset!!",
                hasDefault = true,
                isVararg = false,
            ),
            CanonicalJavaScriptParameter("kotlin/String?", hasDefault = true, isVararg = false),
        ),
    ) || isExactProperty(
        "AgentConversationSettings",
        "approvalPreset",
        "$canonicalPackage/AgentApprovalPreset!!",
    ) || isExactProperty("AgentConversationSettings", "serviceTier", "kotlin/String?")
}

private fun CanonicalJavaScriptMember.isExactConversationIdMember(): Boolean =
    isExactConstructor(
        "ConversationId",
        listOf(CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false)),
    ) || isExactProperty("ConversationId", "value", "kotlin/String!!")

private fun CanonicalJavaScriptMember.isExactCodexClientInfoMember(): Boolean =
    isExactConstructor(
        "CodexClientInfo",
        List(3) {
            CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false)
        },
    ) || listOf("name", "title", "version").any {
        isExactProperty("CodexClientInfo", it, "kotlin/String!!")
    }

private fun CanonicalJavaScriptMember.isExactPathWorkspaceSelectionMember(): Boolean =
    isExactConstructor(
        "CodexPathWorkspaceSelection",
        listOf(CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false)),
    ) || isExactProperty("CodexPathWorkspaceSelection", "path", "kotlin/String!!")

private fun CanonicalJavaScriptMember.isExactAgentSkillScopeDisplayName(): Boolean =
    owner == "io.github.codex_agent_labs.codexagent.agent/AgentSkillScope" &&
        isExactProperty("AgentSkillScope", "displayName", "kotlin/String!!")

private fun CanonicalJavaScriptMember.isExactApiKeyAuthenticationMethodMember(): Boolean =
    isExactConstructor(
        "CodexAuthenticationMethod.ApiKey",
        listOf(CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false)),
    ) || isExactProperty("CodexAuthenticationMethod.ApiKey", "value", "kotlin/String!!")

private fun CanonicalJavaScriptMember.isExactConstructor(
    expectedOwner: String,
    expectedParameters: List<CanonicalJavaScriptParameter>,
): Boolean = simpleOwner == expectedOwner && kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR &&
    name == "<init>" && parameters == expectedParameters &&
    returnType == "${owner.substringBeforeLast('/')}/$expectedOwner" && !isSuspend && propertyKind == null

private fun CanonicalJavaScriptMember.isExactProperty(
    expectedOwner: String,
    expectedName: String,
    expectedType: String,
): Boolean = simpleOwner == expectedOwner && kind == CanonicalJavaScriptMemberKind.PROPERTY &&
    name == expectedName && parameters.isEmpty() && returnType == expectedType && !isSuspend &&
    propertyKind == CanonicalJavaScriptPropertyKind.VAL

private fun hasExactJavaScriptSymbolInventory(
    symbols: List<JavaScriptPublicSymbol>,
    expectedSymbols: List<String>,
): Boolean = expectedSymbols.distinct().size == expectedSymbols.size && expectedSymbols.all { raw ->
    val expected = parseJavaScriptPublicSymbol(raw)
    symbols.filter {
        it.kind == expected.kind && it.owner == expected.owner && it.name == expected.name
    }.map(JavaScriptPublicSymbol::raw) == listOf(raw)
}

private fun javaScriptApplicabilityExclusion(
    member: CanonicalJavaScriptMember,
): CrossLanguageApplicabilityExclusion? {
    val canonicalPackage = member.owner.substringBeforeLast('/')
    fun canonical(name: String, nullable: Boolean = false, nonNull: Boolean = false): String =
        "$canonicalPackage/$name" + when {
            nullable -> "?"
            nonNull -> "!!"
            else -> ""
        }
    fun parameter(type: String, hasDefault: Boolean) =
        CanonicalJavaScriptParameter(type, hasDefault = hasDefault, isVararg = false)
    val expectedParameters = when (member.simpleOwner) {
        "AgentAuthenticationState" -> listOf(
            parameter(canonical("AgentAuthenticationStatus", nonNull = true), true),
            parameter(canonical("CodexAuthorizationUrl", nullable = true), true),
            parameter(canonical("CodexAuthorizationUrl", nullable = true), true),
            parameter("kotlin/String?", true),
            parameter(canonical("CodexFailure", nullable = true), true),
        )
        "AgentConversationState" -> listOf(
            parameter(canonical("AgentConversationStatus", nonNull = true), true),
            parameter(canonical("ConversationId", nullable = true), true),
            parameter(canonical("AgentConversation", nullable = true), true),
            parameter(canonical("AgentTurnProgress", nonNull = true), true),
            parameter("kotlin/String?", true),
            parameter("kotlin/String?", true),
            parameter("kotlin/String?", true),
            parameter(canonical("CodexFailure", nullable = true), true),
        )
        "AgentMessage" -> listOf(
            parameter("kotlin/String!!", false),
            parameter("kotlin/String?", false),
            parameter(canonical("AgentMessageRole", nonNull = true), false),
            parameter("kotlin/String!!", false),
            parameter(canonical("AgentCollaborationMode", nonNull = true), true),
            parameter("kotlin/String?", true),
            parameter("kotlin/String?", true),
            parameter("kotlin/String?", true),
            parameter("kotlin/Int?", true),
            parameter(
                "kotlin.collections/Set<INVARIANT:${canonical("AgentCapability", nonNull = true)}>!!",
                true,
            ),
            parameter(
                "kotlin.collections/List<INVARIANT:${canonical("AgentInvocation", nonNull = true)}>!!",
                true,
            ),
        )
        "AgentTurnProgress" -> listOf(
            parameter("kotlin/String!!", true),
            parameter("kotlin/String!!", true),
            parameter("kotlin/String!!", true),
            parameter("kotlin/String!!", true),
            parameter(canonical("AgentPlanProgress", nullable = true), true),
            parameter("kotlin/String!!", true),
            parameter("kotlin/Int?", true),
            parameter(canonical("AgentWorkActivity", nullable = true), true),
            parameter(
                "kotlin.collections/List<INVARIANT:${canonical("AgentHookActivity", nonNull = true)}>!!",
                true,
            ),
            parameter("kotlin/Boolean!!", true),
        )
        "CodexFailure" -> listOf(
            parameter("kotlin/String!!", false),
            parameter("kotlin/String!!", false),
            parameter("kotlin/Boolean!!", false),
        )
        "CodexHostState.Failed" -> listOf(
            parameter(canonical("CodexWorkspace", nullable = true), false),
            parameter(canonical("CodexFailure", nonNull = true), false),
        )
        "CodexHostState.Preparing" ->
            listOf(parameter(canonical("CodexWorkspace", nonNull = true), false))
        "CodexHostState.Ready" ->
            listOf(parameter(canonical("CodexAgent", nonNull = true), false))
        "CodexHostState.WorkspaceRequired" -> listOf(
            parameter(canonical("CodexWorkspaceResolution.SelectionRequired", nonNull = true), false),
        )
        "CodexWorkspace" -> listOf(
            parameter("kotlin/String!!", false),
            parameter("kotlin/String!!", true),
        )
        "CodexWorkspaceResolution.Available" ->
            listOf(parameter(canonical("CodexWorkspace", nonNull = true), false))
        "CodexWorkspaceResolution.SelectionRequired" -> listOf(
            parameter(canonical("CodexWorkspaceSelectionReason", nonNull = true), false),
            parameter("kotlin/String!!", false),
        )
        else -> return null
    }
    if (!member.isExactConstructor(member.simpleOwner, expectedParameters)) return null
    val reason = when (member.simpleOwner) {
        "CodexHostState.Failed",
        "CodexHostState.Preparing",
        "CodexHostState.Ready",
        "CodexHostState.WorkspaceRequired",
        "CodexWorkspaceResolution.Available",
        "CodexWorkspaceResolution.SelectionRequired",
        -> "JavaScript receives this canonical state variant from the SDK; its constructor is intentionally private."
        else ->
            "JavaScript receives this canonical immutable snapshot from the SDK; its constructor is intentionally private."
    }
    return CrossLanguageApplicabilityExclusion(
        member.key,
        CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
        reason,
    )
}

private data class JavaScriptObjectLiteralProjection(
    val typeName: String,
    val literal: String,
)

private fun objectProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val projection = when (member.simpleOwner) {
        "CodexAuthenticationMethod.ChatGptBrowser" ->
            JavaScriptObjectLiteralProjection("CodexAuthenticationMethod", "\"chatgpt_browser\"")
        "CodexAuthenticationMethod.ChatGptDeviceCode" ->
            JavaScriptObjectLiteralProjection("CodexAuthenticationMethod", "\"chatgpt_device_code\"")
        "CodexHostState.New" -> JavaScriptObjectLiteralProjection("CodexHostStatus", "\"new\"")
        "CodexHostState.Restoring" -> JavaScriptObjectLiteralProjection("CodexHostStatus", "\"restoring\"")
        "CodexHostState.Closed" -> JavaScriptObjectLiteralProjection("CodexHostStatus", "\"closed\"")
        else -> return emptyList()
    }
    return symbols.filter {
        it.kind == JavaScriptPublicSymbolKind.TYPE && it.name == projection.typeName &&
            projection.literal in exactJavaScriptStringLiteralUnion(it.signature.orEmpty()).orEmpty()
    }.map {
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(it.raw),
            scenarios = listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            requiresConsumerReference = true,
        )
    }
}

private fun enumProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val owner = javascriptOwnerName(member.simpleOwner)
    val literal = "\"${member.name.lowercase()}\""
    return symbols.filter {
        it.kind == JavaScriptPublicSymbolKind.TYPE && it.name == owner &&
            literal in exactJavaScriptStringLiteralUnion(it.signature.orEmpty()).orEmpty()
    }.map {
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(it.raw),
            scenarios = listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            requiresConsumerReference = false,
        )
    }
}

private fun propertyProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val type = member.returnType ?: return emptyList()
    if (isStateFlowType(type)) {
        return if (member.propertyKind == CanonicalJavaScriptPropertyKind.VAL) {
            stateFlowProjectionCandidates(member, type, symbols)
        } else emptyList()
    }
    val owner = javascriptOwnerName(member.simpleOwner)
    val name = javascriptMemberName(member.simpleOwner, member.name)
    return symbols.filter {
        it.owner == owner && it.name == name &&
            it.kind in setOf(JavaScriptPublicSymbolKind.GETTER, JavaScriptPublicSymbolKind.PROPERTY) &&
            "static" !in it.qualifiers &&
            (when (member.propertyKind) {
                CanonicalJavaScriptPropertyKind.VAL ->
                    it.kind == JavaScriptPublicSymbolKind.GETTER || "readonly" in it.qualifiers
                CanonicalJavaScriptPropertyKind.VAR ->
                    it.kind == JavaScriptPublicSymbolKind.PROPERTY && "readonly" !in it.qualifiers
                null -> false
            }) &&
            "optional" !in it.qualifiers && javascriptTypeCompatible(it.signature.orEmpty(), type)
    }.map {
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(it.raw),
            scenarios = listOf(CrossLanguageBindingScenario.VALUE_CONVERSION),
            requiresConsumerReference = false,
        )
    }
}

private fun stateFlowProjectionCandidates(
    member: CanonicalJavaScriptMember,
    type: String,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (member.simpleOwner == "CodexConversation") {
        return conversationStateFlowProjectionCandidates(member, type, symbols)
    }
    val elementType = unwrapStateFlowType(type)
    val target = when (member.simpleOwner to member.name) {
        "CodexHost" to "lifecycleState" -> Triple("CodexHost", "state", "observeState")
        "CodexConversations" to "active" -> Triple("CodexAgent", "activeConversation", "observeActiveConversation")
        "CodexAuthentication" to "isAuthenticated" ->
            Triple("CodexAuthentication", "isAuthenticated", "observeAuthenticated")
        "CodexAuthentication" to "isAuthenticating" ->
            Triple("CodexAuthentication", "isAuthenticating", "observeAuthenticating")
        else -> Triple(
            javascriptOwnerName(member.simpleOwner),
            javascriptMemberName(member.simpleOwner, member.name),
            "observe" + javascriptMemberName(member.simpleOwner, member.name).replaceFirstChar(Char::uppercase),
        )
    }
    val getters = symbols.filter {
        it.owner == target.first && it.name == target.second &&
            it.kind in setOf(JavaScriptPublicSymbolKind.GETTER, JavaScriptPublicSymbolKind.PROPERTY) &&
            "static" !in it.qualifiers &&
            (it.kind == JavaScriptPublicSymbolKind.GETTER || "readonly" in it.qualifiers) &&
            "optional" !in it.qualifiers && javascriptTypeCompatible(it.signature.orEmpty(), elementType)
    }
    val observers = symbols.filter {
        it.owner == target.first && it.name == target.third && it.kind == JavaScriptPublicSymbolKind.METHOD &&
            "static" !in it.qualifiers && javascriptObserverSignatureCompatible(it.signature.orEmpty(), elementType)
    }
    return getters.flatMap { getter -> observers.map { observer -> getter to observer } }.map { (getter, observer) ->
        val publicSymbols = listOf(getter.raw, observer.raw).sorted()
        JavaScriptProjectionCandidate(
            publicSymbols = publicSymbols,
            scenarios = listOf(
                CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
            ),
            requiresConsumerReference = true,
            shareablePublicSymbols = if (
                member.isExactD044HostLifecycleState() && publicSymbols.toSet() == javaScriptHostStateEnvelope
            ) {
                javaScriptHostStateEnvelope
            } else {
                emptySet()
            },
        )
    }
}

private const val javaScriptConversationStateGetter =
    "getter:CodexConversation#state:CodexConversationState"
private const val javaScriptConversationStateObserver =
    "method:CodexConversation#observeState:(listener: (state: CodexConversationState) => void): CodexObservation"
private const val javaScriptConversationStateConversation =
    "getter:CodexConversationState#conversation:AgentConversation | null | undefined"
private const val javaScriptConversationStateTurnProgress =
    "getter:CodexConversationState#turnProgress:CodexTurnProgress | null | undefined"
private val javaScriptConversationStateEnvelope = setOf(
    javaScriptConversationStateGetter,
    javaScriptConversationStateObserver,
)
private val d046ConversationStateMemberNames = setOf("conversation", "turnProgress")

private fun conversationStateSnapshotProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val leaf = when {
        member.isExactD046Conversation() -> javaScriptConversationStateConversation
        member.isExactD046TurnProgress() -> javaScriptConversationStateTurnProgress
        else -> return emptyList()
    }
    val inventory = (
        javaScriptConversationStateEnvelope + javaScriptConversationStateConversation +
            javaScriptConversationStateTurnProgress
        ).sorted()
    if (!hasExactConversationStateSnapshotInventory(symbols, inventory)) return emptyList()
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = (javaScriptConversationStateEnvelope + leaf).sorted(),
            scenarios = javaScriptStateScenarios + CrossLanguageBindingScenario.VALUE_CONVERSION,
            requiresConsumerReference = true,
            shareablePublicSymbols = javaScriptConversationStateEnvelope,
        ),
    )
}

private fun hasExactConversationStateSnapshotInventory(
    symbols: List<JavaScriptPublicSymbol>,
    expectedSymbols: List<String>,
): Boolean = hasExactJavaScriptSymbolInventory(symbols, expectedSymbols) && expectedSymbols.all { raw ->
    val expected = parseJavaScriptPublicSymbol(raw)
    symbols.filter { it.owner == expected.owner && it.name == expected.name }
        .map(JavaScriptPublicSymbol::raw) == listOf(raw)
}

private fun CanonicalJavaScriptMember.isExactD046Conversation(): Boolean =
    owner == "$canonicalAgentPackage/AgentConversationState" && isExactProperty(
        "AgentConversationState",
        "conversation",
        "$canonicalAgentPackage/AgentConversation?",
    )

private fun CanonicalJavaScriptMember.isExactD046TurnProgress(): Boolean =
    owner == "$canonicalAgentPackage/AgentConversationState" && isExactProperty(
        "AgentConversationState",
        "turnProgress",
        "$canonicalAgentPackage/AgentTurnProgress!!",
    )

private fun CanonicalJavaScriptMember.isExactD046ConversationState(): Boolean =
    owner == "$canonicalAgentPackage/CodexConversation" && isExactProperty(
        "CodexConversation",
        "state",
        "kotlinx.coroutines.flow/StateFlow<INVARIANT:$canonicalAgentPackage/AgentConversationState!!>!!",
    )

private fun CanonicalJavaScriptMember.isExactD046ActiveTurnProgress(): Boolean =
    owner == "$canonicalAgentPackage/CodexConversation" && isExactProperty(
        "CodexConversation",
        "activeTurnProgress",
        "kotlinx.coroutines.flow/StateFlow<INVARIANT:$canonicalAgentPackage/AgentTurnProgress?>!!",
    )

private fun conversationStateFlowProjectionCandidates(
    member: CanonicalJavaScriptMember,
    type: String,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!type.startsWith("kotlinx.coroutines.flow/StateFlow<") || !type.endsWith(">!!")) return emptyList()
    val elementType = unwrapStateFlowType(type)
    val stateGetters = symbols.filter {
        it.owner == "CodexConversation" && it.name == "state" &&
            it.kind in setOf(JavaScriptPublicSymbolKind.GETTER, JavaScriptPublicSymbolKind.PROPERTY)
    }
    val stateObservers = symbols.filter {
        it.owner == "CodexConversation" && it.name == "observeState" &&
            it.kind == JavaScriptPublicSymbolKind.METHOD
    }
    if (stateGetters.map(JavaScriptPublicSymbol::raw) != listOf(javaScriptConversationStateGetter) ||
        stateObservers.map(JavaScriptPublicSymbol::raw) != listOf(javaScriptConversationStateObserver)
    ) return emptyList()
    val projectedSymbols = if (member.name == "state") {
        val canonicalPackage = member.owner.substringBeforeLast('/')
        if (elementType != "$canonicalPackage/AgentConversationState!!") return emptyList()
        listOf(javaScriptConversationStateGetter, javaScriptConversationStateObserver)
    } else {
        val leafName = when (member.name) {
            "activeTurnProgress" -> "turnProgress"
            "currentMessages" -> "messages"
            else -> member.name
        }
        val namedLeaves = symbols.filter {
            it.owner == "CodexConversationState" && it.name == leafName &&
                it.kind in setOf(JavaScriptPublicSymbolKind.GETTER, JavaScriptPublicSymbolKind.PROPERTY)
        }
        val leaves = namedLeaves.filter {
            "static" !in it.qualifiers &&
                (it.kind == JavaScriptPublicSymbolKind.GETTER || "readonly" in it.qualifiers) &&
                "optional" !in it.qualifiers && javascriptTypeCompatible(it.signature.orEmpty(), elementType)
        }
        if (leaves.isEmpty() || leaves.size != namedLeaves.size) return emptyList()
        return leaves.map { leaf ->
            JavaScriptProjectionCandidate(
                publicSymbols = (javaScriptConversationStateEnvelope + leaf.raw).sorted(),
                scenarios = javaScriptStateScenarios,
                requiresConsumerReference = true,
                shareablePublicSymbols = javaScriptConversationStateEnvelope,
            )
        }
    }
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = projectedSymbols.sorted(),
            scenarios = javaScriptStateScenarios,
            requiresConsumerReference = true,
            shareablePublicSymbols = javaScriptConversationStateEnvelope,
        )
    )
}

private val javaScriptStateScenarios = listOf(
    CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
    CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
    CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
)

private fun constructorProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val candidates = if (member.simpleOwner == "CodexHost") {
        symbols.filter {
            it.kind == JavaScriptPublicSymbolKind.FUNCTION && it.name == "createCodexHost" &&
                javascriptHostFactorySignatureCompatible(it.signature.orEmpty(), member)
        }
    } else {
        val owner = javascriptOwnerName(member.simpleOwner)
        symbols.filter {
            it.kind == JavaScriptPublicSymbolKind.CONSTRUCTOR && it.owner == owner &&
                javascriptSignatureCompatible(it.signature.orEmpty(), member)
        }
    }
    return candidates.map {
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(it.raw),
            scenarios = listOf(
                if (member.simpleOwner == "CodexHost") {
                    CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP
                } else {
                    CrossLanguageBindingScenario.VALUE_CONVERSION
                },
            ),
            requiresConsumerReference = true,
        )
    }
}

private fun functionProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    when (member.simpleOwner to member.name) {
        "CodexAuthentication" to "authenticate" ->
            return authenticationProjectionCandidates(member, symbols)
        "CodexConversations" to "open" ->
            return openConversationProjectionCandidates(member, symbols)
        "CodexConversations" to "read" ->
            return readConversationProjectionCandidates(member, symbols)
    }
    val targetOwner = when (member.simpleOwner) {
        "CodexConversations" -> "CodexAgent"
        else -> javascriptOwnerName(member.simpleOwner.removeSuffix(".Companion"))
    }
    val targetName = when {
        member.isExactListConversationsFunction() -> "listConversations"
        member.simpleOwner == "CodexConversation" && member.name == "send" &&
            member.parameters.firstOrNull()?.type?.contains("AgentTurnRequest") == true -> "sendRequest"
        else -> javascriptMemberName(member.simpleOwner, member.name)
    }
    val candidates = symbols.filter {
        it.kind == JavaScriptPublicSymbolKind.METHOD && it.owner == targetOwner && it.name == targetName &&
            ("static" in it.qualifiers) == member.simpleOwner.endsWith(".Companion") &&
            (if (member.simpleOwner == "CodexHost" && member.name == "selectWorkspace") {
                javascriptSelectWorkspaceSignatureCompatible(it.signature.orEmpty(), member)
            } else javascriptSignatureCompatible(it.signature.orEmpty(), member))
    }
    val scenarios = buildList {
        add(if (member.isSuspend) CrossLanguageBindingScenario.ASYNC_SUCCESS else CrossLanguageBindingScenario.VALUE_CONVERSION)
        if (member.isSuspend) add(CrossLanguageBindingScenario.ASYNC_FAILURE)
        if (member.name == "cancel") add(CrossLanguageBindingScenario.CANCELLATION)
        if (member.name == "close") add(CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE)
    }
    return candidates.map {
        JavaScriptProjectionCandidate(listOf(it.raw), scenarios, requiresConsumerReference = true)
    }
}

private val javaScriptAuthenticationOverloads = setOf(
    "method:CodexAuthentication#authenticate:" +
        "(method: \"api_key\", apiKey: string, signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexAuthentication#authenticate:" +
        "(method: \"chatgpt_device_code\", apiKey?: null, signal?: AbortSignal | null | undefined): Promise<void>",
    "method:CodexAuthentication#authenticate:" +
        "(method?: \"chatgpt_browser\" | null | undefined, apiKey?: null, " +
        "signal?: AbortSignal | null | undefined): Promise<void>",
)

private fun authenticationProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactAuthenticationFunction() || !hasExactAuthenticationOverloadInventory(symbols)) {
        return emptyList()
    }
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = javaScriptAuthenticationOverloads.sorted(),
            scenarios = listOf(
                CrossLanguageBindingScenario.ASYNC_SUCCESS,
                CrossLanguageBindingScenario.ASYNC_FAILURE,
                CrossLanguageBindingScenario.CANCELLATION,
            ),
            requiresConsumerReference = true,
        )
    )
}

private fun CanonicalJavaScriptMember.isExactAuthenticationFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        expectedOwner = "CodexAuthentication",
        expectedName = "authenticate",
        expectedReturnType = "kotlin/Unit",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/CodexAuthenticationMethod!!",
                hasDefault = true,
                isVararg = false,
            ),
        ),
    )
}

private fun hasExactAuthenticationOverloadInventory(symbols: List<JavaScriptPublicSymbol>): Boolean {
    val overloads = symbols.filter {
        it.owner == "CodexAuthentication" && it.name == "authenticate" &&
            it.kind == JavaScriptPublicSymbolKind.METHOD
    }.map(JavaScriptPublicSymbol::raw)
    return overloads.size == javaScriptAuthenticationOverloads.size &&
        overloads.toSet() == javaScriptAuthenticationOverloads
}

private const val javaScriptOpenConversation =
    "method:CodexAgent#openConversation:" +
        "(conversationId?: string | null | undefined, approvalPreset?: CodexApprovalPreset | null | undefined, " +
        "serviceTier?: string | null | undefined, signal?: AbortSignal | null | undefined): Promise<CodexConversation>"

private fun openConversationProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val overloads = symbols.filter {
        it.owner == "CodexAgent" && it.name == "openConversation" &&
            it.kind == JavaScriptPublicSymbolKind.METHOD
    }.map(JavaScriptPublicSymbol::raw)
    if (!member.isExactOpenConversationFunction() || overloads != listOf(javaScriptOpenConversation)) {
        return emptyList()
    }
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = overloads,
            scenarios = listOf(
                CrossLanguageBindingScenario.ASYNC_SUCCESS,
                CrossLanguageBindingScenario.ASYNC_FAILURE,
                CrossLanguageBindingScenario.CANCELLATION,
                CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
            ),
            requiresConsumerReference = true,
        )
    )
}

private fun CanonicalJavaScriptMember.isExactOpenConversationFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        expectedOwner = "CodexConversations",
        expectedName = "open",
        expectedReturnType = "$canonicalPackage/CodexConversation!!",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/ConversationId?",
                hasDefault = true,
                isVararg = false,
            ),
            CanonicalJavaScriptParameter(
                "$canonicalPackage/AgentConversationSettings!!",
                hasDefault = true,
                isVararg = false,
            ),
        ),
    )
}

private fun CanonicalJavaScriptMember.isExactListConversationsFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        expectedOwner = "CodexConversations",
        expectedName = "list",
        expectedReturnType =
            "kotlin.collections/List<INVARIANT:$canonicalPackage/AgentConversationSummary!!>!!",
        expectedSuspend = true,
        expectedParameters = emptyList(),
    )
}

private fun readConversationProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    if (!member.isExactReadConversationFunction() ||
        !hasExactD045ConversationInventory(symbols, listOf(javaScriptReadConversation))
    ) return emptyList()
    return listOf(
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(javaScriptReadConversation),
            scenarios = listOf(
                CrossLanguageBindingScenario.ASYNC_SUCCESS,
                CrossLanguageBindingScenario.ASYNC_FAILURE,
            ),
            requiresConsumerReference = true,
            shareablePublicSymbols = setOf(javaScriptReadConversation),
        ),
    )
}

private fun CanonicalJavaScriptMember.isExactReadConversationFunction(): Boolean =
    owner == "$canonicalAgentPackage/CodexConversations" && isExactFunction(
        expectedOwner = "CodexConversations",
        expectedName = "read",
        expectedReturnType = "$canonicalAgentPackage/AgentConversation!!",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalAgentPackage/ConversationId!!",
                hasDefault = false,
                isVararg = false,
            ),
        ),
    )

private fun CanonicalJavaScriptMember.isExactFunction(
    expectedOwner: String,
    expectedName: String,
    expectedReturnType: String,
    expectedSuspend: Boolean,
    expectedParameters: List<CanonicalJavaScriptParameter>,
): Boolean = simpleOwner == expectedOwner && kind == CanonicalJavaScriptMemberKind.FUNCTION &&
    name == expectedName && parameters == expectedParameters && returnType == expectedReturnType &&
    isSuspend == expectedSuspend && propertyKind == null

private fun javascriptSignatureCompatible(
    signature: String,
    member: CanonicalJavaScriptMember,
): Boolean {
    val actual = parseJavaScriptSignatureOrNull(signature, requireReturn = member.kind != CanonicalJavaScriptMemberKind.CONSTRUCTOR)
        ?: return false
    if (!javascriptParametersCompatible(actual.parameters, member)) return false
    if (member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) return actual.returnType == null
    val actualReturn = actual.returnType ?: return false
    val expectedReturn = member.returnType ?: "kotlin/Unit!!"
    return if (member.isSuspend) {
        actualReturn.startsWith("Promise<") && actualReturn.endsWith('>') &&
            splitJavaScriptTopLevelUnion(actualReturn).size == 1 &&
            javascriptTypeCompatible(actualReturn.substring("Promise<".length, actualReturn.lastIndex), expectedReturn)
    } else javascriptTypeCompatible(actualReturn, expectedReturn)
}

private fun findClosingJavaScriptParenthesis(signature: String): Int {
    var angle = 0
    var parenthesis = 0
    signature.forEachIndexed { index, char ->
        when (char) {
            '<' -> angle++
            '>' -> if (angle > 0) angle--
            '(' -> if (angle == 0) parenthesis++
            ')' -> if (angle == 0 && --parenthesis == 0) return index
        }
    }
    return -1
}

private fun parseJavaScriptSignature(
    signature: String,
    requireReturn: Boolean,
): JavaScriptSignature = parseJavaScriptSignatureOrNull(signature, requireReturn)
    ?: error("Malformed JavaScript/TypeScript signature: $signature")

private fun parseJavaScriptSignatureOrNull(
    signature: String,
    requireReturn: Boolean,
): JavaScriptSignature? {
    val close = findClosingJavaScriptParenthesis(signature)
    if (!signature.startsWith('(') || close < 0) return null
    val suffix = signature.substring(close + 1)
    val returnType = when {
        suffix.isEmpty() && !requireReturn -> null
        suffix.startsWith(": ") && suffix.length > 2 -> suffix.substring(2)
        else -> return null
    }
    val parameters = splitJavaScriptTopLevel(signature.substring(1, close)).filter(String::isNotBlank).map { raw ->
        val separator = raw.indexOf(':')
        if (separator <= 0) return null
        val rawName = raw.substring(0, separator)
        val vararg = rawName.startsWith("...")
        val withoutVararg = rawName.removePrefix("...")
        val optional = withoutVararg.endsWith('?')
        val name = withoutVararg.removeSuffix("?")
        if (name.isBlank() || name.any { !it.isLetterOrDigit() && it != '_' && it != '$' }) return null
        val type = raw.substring(separator + 1).trim()
        if (type.isBlank()) return null
        JavaScriptParameter(name, type, optional, vararg)
    }
    return JavaScriptSignature(parameters, returnType)
}

private fun javascriptParametersCompatible(
    actual: List<JavaScriptParameter>,
    member: CanonicalJavaScriptMember,
): Boolean {
    val expected = member.parameters
    val hasAbortSignal = actual.size == expected.size + 1 && member.isSuspend &&
        actual.last().isIdiomaticAbortSignal()
    if (actual.size != expected.size && !hasAbortSignal) return false
    return expected.indices.all { index ->
        val actualParameter = actual[index]
        val expectedParameter = expected[index]
        actualParameter.optional == expectedParameter.hasDefault &&
            actualParameter.vararg == expectedParameter.isVararg &&
            javascriptTypeCompatible(actualParameter.type, expectedParameter.type)
    }
}

private fun JavaScriptParameter.isIdiomaticAbortSignal(): Boolean =
    name == "signal" && optional && !vararg &&
        exactJavaScriptUnion(type, "AbortSignal | null | undefined")

private fun javascriptHostFactorySignatureCompatible(
    signature: String,
    member: CanonicalJavaScriptMember,
): Boolean {
    val actual = parseJavaScriptSignatureOrNull(signature, requireReturn = true) ?: return false
    val expectedNames = listOf("bundleDirectory", "dataDirectory", "clientName", "clientTitle", "clientVersion")
    return member.isExactCodexHostFactoryConstructor() && actual.returnType == "CodexHost" &&
        actual.parameters.map(JavaScriptParameter::name) == expectedNames &&
        actual.parameters.all { !it.optional && !it.vararg && normalizeJavaScriptType(it.type) == "string" }
}

private fun CanonicalJavaScriptMember.isExactCodexHostFactoryConstructor(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactConstructor(
        "CodexHost",
        listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/CodexPlatform!!",
                hasDefault = false,
                isVararg = false,
            ),
            CanonicalJavaScriptParameter(
                "$canonicalPackage/CodexClientInfo!!",
                hasDefault = false,
                isVararg = false,
            ),
        ),
    )
}

private fun javascriptSelectWorkspaceSignatureCompatible(
    signature: String,
    member: CanonicalJavaScriptMember,
): Boolean {
    val actual = parseJavaScriptSignatureOrNull(signature, requireReturn = true) ?: return false
    val canonicalParameter = member.parameters.singleOrNull()
    val canonicalPackage = member.owner.substringBeforeLast('/')
    val canonicalShape = member.isSuspend && member.returnType in setOf("kotlin/Unit", "kotlin/Unit!!") &&
        canonicalParameter != null && !canonicalParameter.hasDefault && !canonicalParameter.isVararg &&
        canonicalParameter.type == "$canonicalPackage/CodexWorkspaceSelection!!"
    return canonicalShape && actual.returnType == "Promise<void>" && actual.parameters.size == 2 &&
        actual.parameters[0] == JavaScriptParameter("path", "string", optional = false, vararg = false) &&
        actual.parameters[1].isIdiomaticAbortSignal()
}

private fun javascriptObserverSignatureCompatible(signature: String, canonicalType: String): Boolean {
    val observer = parseJavaScriptSignatureOrNull(signature, requireReturn = true) ?: return false
    if (observer.returnType != "CodexObservation" || observer.parameters.size != 1) return false
    val listener = observer.parameters.single()
    if (listener.optional || listener.vararg) return false
    val callbackClose = findClosingJavaScriptParenthesis(listener.type)
    if (!listener.type.startsWith('(') || callbackClose < 0 ||
        listener.type.substring(callbackClose + 1) != " => void"
    ) return false
    val callback = parseJavaScriptSignatureOrNull(
        listener.type.substring(0, callbackClose + 1) + ": void",
        requireReturn = true,
    ) ?: return false
    return callback.parameters.size == 1 && !callback.parameters.single().optional &&
        !callback.parameters.single().vararg && callback.returnType == "void" &&
        javascriptTypeCompatible(callback.parameters.single().type, canonicalType)
}

private fun javascriptTypeCompatible(actualType: String, canonicalType: String): Boolean {
    val expected = canonicalJavaScriptType(canonicalType) ?: return false
    return exactJavaScriptUnion(actualType, expected)
}

private fun exactJavaScriptUnion(actual: String, expected: String): Boolean {
    val actualMembers = splitJavaScriptTopLevelUnion(actual).map(::normalizeJavaScriptType)
    val expectedMembers = splitJavaScriptTopLevelUnion(expected).map(::normalizeJavaScriptType)
    return actualMembers.distinct().size == actualMembers.size &&
        expectedMembers.distinct().size == expectedMembers.size && actualMembers.toSet() == expectedMembers.toSet()
}

private fun canonicalJavaScriptType(type: String): String? {
    val withoutVariance = type.removePrefix("INVARIANT:")
    val nullable = withoutVariance.endsWith('?')
    val base = when {
        nullable -> withoutVariance.dropLast(1)
        withoutVariance.endsWith("!!") -> withoutVariance.dropLast(2)
        else -> withoutVariance
    }
    val rendered = when {
        base == "kotlin/String" || base == "kotlin/Char" -> "string"
        base == "kotlin/Boolean" -> "boolean"
        base in setOf(
            "kotlin/Byte", "kotlin/Short", "kotlin/Int", "kotlin/Float", "kotlin/Double",
        ) -> "number"
        base == "kotlin/Long" -> "bigint"
        base == "kotlin/Unit" -> "void"
        base.endsWith("/ConversationId") -> "string"
        base.endsWith("/CodexAuthorizationUrl") -> "CodexAuthorizationUrl"
        base.startsWith("kotlin.collections/List<") -> canonicalCollectionType(base, "ReadonlyArray", 1)
        base.startsWith("kotlin.collections/Set<") -> canonicalCollectionType(base, "ReadonlySet", 1)
        base.startsWith("kotlin.collections/Map<") -> canonicalCollectionType(base, "ReadonlyMap", 2)
        '<' in base -> return null
        else -> javascriptOwnerName(base.substringAfterLast('/'))
    } ?: return null
    return if (nullable) "$rendered | null | undefined" else rendered
}

private fun canonicalCollectionType(type: String, owner: String, arity: Int): String? {
    if (!type.endsWith('>')) return null
    val arguments = splitJavaScriptTopLevel(type.substringAfter('<').dropLast(1))
    if (arguments.size != arity) return null
    val rendered = arguments.map { canonicalJavaScriptType(it) ?: return null }
    return "$owner<${rendered.joinToString(", ")}>"
}

private fun splitJavaScriptTopLevelUnion(value: String): List<String> =
    splitJavaScriptTopLevel(value, separator = '|')

private fun normalizeJavaScriptType(value: String): String =
    value.trim().removeSuffix(";").replace(Regex("\\s+"), " ")

private fun isStateFlowType(type: String): Boolean =
    type.trimEnd('!', '?').startsWith("kotlinx.coroutines.flow/StateFlow<")

private fun unwrapStateFlowType(type: String): String {
    val base = type.trimEnd('!', '?')
    return base.substringAfter('<').removeSuffix(">").removePrefix("INVARIANT:")
}

private fun javascriptOwnerName(canonical: String): String = when (canonical) {
    "AgentApprovalPreset" -> "CodexApprovalPreset"
    "AgentAuthenticationState" -> "CodexAuthenticationState"
    "AgentAuthenticationStatus" -> "CodexAuthenticationStatus"
    "AgentConversationStatus" -> "CodexConversationStatus"
    "AgentFormValue.BooleanValue" -> "AgentFormBooleanValue"
    "AgentFormValue.Number" -> "AgentFormNumberValue"
    "AgentFormValue.Text" -> "AgentFormTextValue"
    "AgentFormValue.TextList" -> "AgentFormTextListValue"
    "AgentInvocation.Plugin" -> "AgentPluginInvocation"
    "AgentInvocation.Skill" -> "AgentSkillInvocation"
    "AgentMessageRole" -> "CodexMessageRole"
    "AgentWorkActivity" -> "CodexWorkActivity"
    "AgentMessage" -> "CodexMessage"
    "AgentTurnProgress" -> "CodexTurnProgress"
    "AgentConversationState" -> "CodexConversationState"
    else -> canonical
}

private fun javascriptMemberName(owner: String, canonical: String): String = when (owner to canonical) {
    "CodexFailure" to "isRecoverable" -> "recoverable"
    "AgentTurnProgress" to "isTruncated" -> "truncated"
    else -> canonical
}

private fun exactJavaScriptStringLiteralUnion(signature: String): Set<String>? {
    val literals = splitJavaScriptTopLevelUnion(signature).map(::normalizeJavaScriptType)
    return literals.takeIf { values ->
        values.isNotEmpty() && values.distinct().size == values.size &&
            values.all { Regex("\"[a-z0-9_]+\"").matches(it) }
    }?.toSet()
}

private fun isAllowedLiteralTypeReuse(symbol: String, projections: List<JavaScriptProjection>): Boolean {
    if (!symbol.startsWith("type:")) return false
    return when {
        projections.all { it.member.kind == CanonicalJavaScriptMemberKind.ENUM_ENTRY } ->
            projections.map { it.member.owner }.distinct().size == 1
        projections.all { it.member.kind == CanonicalJavaScriptMemberKind.OBJECT } ->
            projections.map { it.member.owner.substringBeforeLast('.') }.distinct().size == 1
        else -> false
    }
}

private val d044HostStateMembers = setOf(
    "CodexHostState.Failed" to "failure",
    "CodexHostState.Failed" to "workspace",
    "CodexHostState.Preparing" to "workspace",
    "CodexHostState.Ready" to "agent",
    "CodexHostState.WorkspaceRequired" to "requirement",
    "CodexWorkspaceResolution.Available" to "workspace",
    "CodexWorkspaceResolution.SelectionRequired" to "message",
    "CodexWorkspaceResolution.SelectionRequired" to "reason",
)

private fun JavaScriptProjection.isExactD044HostStateProjection(): Boolean {
    val leaves = member.exactD044HostStateLeaves() ?: return false
    val expectedSymbols = (javaScriptHostStateEnvelope + javaScriptHostStateStatus + leaves).sorted()
    return publicSymbols == expectedSymbols &&
        shareablePublicSymbols == expectedSymbols.toSet().intersect(javaScriptHostStateSharedSymbols)
}

private fun isAllowedHostStateFlatteningReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    val hostStateProjections = projections.filter(JavaScriptProjection::isExactD044HostStateProjection)
    fun exactHostStateMembers(expected: Set<Pair<String, String>>): Boolean =
        hostStateProjections.size == expected.size &&
            hostStateProjections.map { it.member.simpleOwner to it.member.name }.toSet() == expected

    return when (symbol) {
        in javaScriptHostStateEnvelope -> {
            val lifecycle = projections.singleOrNull { projection ->
                projection.member.isExactD044HostLifecycleState() &&
                    projection.publicSymbols == javaScriptHostStateEnvelope.sorted() &&
                    projection.shareablePublicSymbols == javaScriptHostStateEnvelope
            }
            projections.size == 9 && lifecycle != null && exactHostStateMembers(d044HostStateMembers)
        }
        javaScriptHostStateStatus ->
            projections.size == 8 && exactHostStateMembers(d044HostStateMembers)
        javaScriptHostStateWorkspace ->
            projections.size == 3 && exactHostStateMembers(
                setOf(
                    "CodexHostState.Failed" to "workspace",
                    "CodexHostState.Preparing" to "workspace",
                    "CodexWorkspaceResolution.Available" to "workspace",
                ),
            )
        javaScriptHostStateSelectionReason ->
            projections.size == 2 && exactHostStateMembers(
                setOf(
                    "CodexHostState.WorkspaceRequired" to "requirement",
                    "CodexWorkspaceResolution.SelectionRequired" to "reason",
                ),
            )
        javaScriptHostStateSelectionMessage ->
            projections.size == 2 && exactHostStateMembers(
                setOf(
                    "CodexHostState.WorkspaceRequired" to "requirement",
                    "CodexWorkspaceResolution.SelectionRequired" to "message",
                ),
            )
        else -> false
    }
}

private fun isAllowedConversationControllerFlatteningReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (symbol !in javaScriptConversationsEnvelope) return false
    val parent = projections.singleOrNull { projection ->
        projection.member.isExactConversationsProperty() &&
            projection.publicSymbols == javaScriptConversationsEnvelope.sorted() &&
            projection.shareablePublicSymbols == javaScriptConversationsEnvelope
    } ?: return false
    fun exactChild(
        predicate: (CanonicalJavaScriptMember) -> Boolean,
        publicSymbols: List<String> = listOf(symbol),
    ): JavaScriptProjection? = projections.singleOrNull { projection ->
        projection !== parent && predicate(projection.member) &&
            projection.publicSymbols == publicSymbols.sorted()
    }
    fun exactConversationIds(): List<JavaScriptProjection> = projections.filter { projection ->
        projection.member.owner.substringBeforeLast('/') == canonicalAgentPackage &&
            projection.member.isExactConversationIdMember() &&
            projection.publicSymbols == javaScriptConversationIdSymbols
    }
    val inCanonicalPackage: (CanonicalJavaScriptMember) -> Boolean = {
        it.owner.substringBeforeLast('/') == canonicalAgentPackage
    }
    return when (symbol) {
        javaScriptActiveConversation, javaScriptObserveActiveConversation ->
            projections.size == 2 && exactChild(
                predicate = { member ->
                    inCanonicalPackage(member) && member.isExactActiveConversationsProperty()
                },
                publicSymbols = listOf(javaScriptActiveConversation, javaScriptObserveActiveConversation),
            ) != null
        javaScriptListConversations ->
            projections.size == 2 && exactChild(predicate = { member ->
                inCanonicalPackage(member) && member.isExactListConversationsFunction()
            }) != null
        javaScriptReadConversation ->
            projections.size == 4 &&
                exactChild(CanonicalJavaScriptMember::isExactReadConversationFunction) != null &&
                exactConversationIds().size == 2
        javaScriptRenameConversation ->
            projections.size == 4 && exactChild(predicate = { member ->
                inCanonicalPackage(member) && member.isExactRenameConversationFunction()
            }) != null && exactConversationIds().size == 2
        javaScriptDeleteConversation ->
            projections.size == 4 && exactChild(predicate = { member ->
                inCanonicalPackage(member) && member.isExactDeleteConversationFunction()
            }) != null && exactConversationIds().size == 2
        javaScriptOpenConversation -> {
            val settings = projections.filter { projection ->
                projection.member.owner.substringBeforeLast('/') == canonicalAgentPackage &&
                    projection.member.isExactConversationSettingsMember() &&
                    projection.publicSymbols == listOf(javaScriptOpenConversation)
            }
            projections.size == 7 && exactChild(predicate = { member ->
                inCanonicalPackage(member) && member.isExactOpenConversationFunction()
            }) != null && exactConversationIds().size == 2 && settings.size == 3
        }
        else -> false
    }
}

private fun invalidConversationControllerFlatteningErrors(
    projections: List<JavaScriptProjection>,
): List<String> {
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptConversationsEnvelope::contains)
    }
    val parents = related.filter { it.member.isExactConversationsProperty() }
    if (parents.isEmpty()) return emptyList()
    val exact = related.size == 12 && parents.size == 1 &&
        related.all { it.member.owner.substringBeforeLast('/') == canonicalAgentPackage } &&
        related.count { projection ->
            projection.member.isExactActiveConversationsProperty() && projection.publicSymbols ==
                listOf(javaScriptActiveConversation, javaScriptObserveActiveConversation).sorted()
        } == 1 &&
        related.count { it.member.isExactListConversationsFunction() } == 1 &&
        related.count { it.member.isExactReadConversationFunction() } == 1 &&
        related.count { it.member.isExactOpenConversationFunction() } == 1 &&
        related.count { it.member.isExactRenameConversationFunction() } == 1 &&
        related.count { it.member.isExactDeleteConversationFunction() } == 1 &&
        related.count { it.member.isExactConversationIdMember() } == 2 &&
        related.count { it.member.isExactConversationSettingsMember() } == 3
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript conversation controller flattening for capabilities " +
            related.map { it.member.key }.sorted(),
    )
}

private fun CanonicalJavaScriptMember.isExactActiveConversationsProperty(): Boolean =
    owner == "$canonicalAgentPackage/CodexConversations" && isExactProperty(
        "CodexConversations",
        "active",
        "kotlinx.coroutines.flow/StateFlow<INVARIANT:$canonicalAgentPackage/CodexConversation?>!!",
    )

private fun isAllowedConversationStateEnvelopeReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (symbol !in javaScriptConversationStateEnvelope) return false
    val snapshots = projections.filter {
        it.member.isExactD046Conversation() || it.member.isExactD046TurnProgress()
    }
    val aggregates = projections - snapshots.toSet()
    val exactAggregates = aggregates.all { projection ->
        symbol in projection.shareablePublicSymbols && projection.member.simpleOwner == "CodexConversation" &&
            projection.member.kind == CanonicalJavaScriptMemberKind.PROPERTY &&
            projection.member.propertyKind == CanonicalJavaScriptPropertyKind.VAL &&
            projection.member.returnType?.let(::isStateFlowType) == true
    } && aggregates.map { it.member.owner }.distinct().size == 1
    if (snapshots.isEmpty()) return exactAggregates
    return exactAggregates && snapshots.size == 2 && snapshots.all { projection ->
        symbol in projection.shareablePublicSymbols &&
            projection.publicSymbols.toSet() == javaScriptConversationStateEnvelope + when {
                projection.member.isExactD046Conversation() -> javaScriptConversationStateConversation
                projection.member.isExactD046TurnProgress() -> javaScriptConversationStateTurnProgress
                else -> return@all false
            }
    } && aggregates.count { it.member.isExactD046ConversationState() } == 1 &&
        aggregates.count { it.member.isExactD046ActiveTurnProgress() } == 1
}

private fun isAllowedConversationStateLeafReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (projections.size != 2 || symbol in javaScriptConversationStateEnvelope) return false
    if (symbol == javaScriptConversationStateTurnProgress) {
        val snapshot = projections.singleOrNull { it.member.isExactD046TurnProgress() } ?: return false
        val aggregate = projections.singleOrNull { it.member.isExactD046ActiveTurnProgress() } ?: return false
        return snapshot.publicSymbols.toSet() == javaScriptConversationStateEnvelope + symbol &&
            snapshot.shareablePublicSymbols == javaScriptConversationStateEnvelope &&
            aggregate.publicSymbols.toSet() == javaScriptConversationStateEnvelope + symbol &&
            aggregate.shareablePublicSymbols == javaScriptConversationStateEnvelope
    }
    val ordinary = projections.singleOrNull {
        it.member.simpleOwner == "AgentConversationState" &&
            it.member.kind == CanonicalJavaScriptMemberKind.PROPERTY &&
            it.member.propertyKind == CanonicalJavaScriptPropertyKind.VAL &&
            it.member.returnType?.let(::isStateFlowType) == false
    } ?: return false
    val aggregate = projections.singleOrNull {
        it.member.simpleOwner == "CodexConversation" &&
            it.member.kind == CanonicalJavaScriptMemberKind.PROPERTY &&
            it.member.propertyKind == CanonicalJavaScriptPropertyKind.VAL &&
            it.member.returnType?.let(::isStateFlowType) == true
    } ?: return false
    val ordinaryType = ordinary.member.returnType ?: return false
    val aggregateType = aggregate.member.returnType ?: return false
    if (ordinary.member.owner.substringBeforeLast('/') != aggregate.member.owner.substringBeforeLast('/') ||
        ordinary.member.name != aggregate.member.name || unwrapStateFlowType(aggregateType) != ordinaryType ||
        ordinary.publicSymbols != listOf(symbol) || ordinary.shareablePublicSymbols.isNotEmpty() ||
        aggregate.publicSymbols.toSet() != javaScriptConversationStateEnvelope + symbol ||
        aggregate.shareablePublicSymbols != javaScriptConversationStateEnvelope
    ) return false
    val leaf = parseJavaScriptPublicSymbol(symbol)
    return leaf.owner == "CodexConversationState" && leaf.name == ordinary.member.name &&
        leaf.kind in setOf(JavaScriptPublicSymbolKind.GETTER, JavaScriptPublicSymbolKind.PROPERTY) &&
        "static" !in leaf.qualifiers && "optional" !in leaf.qualifiers &&
        (leaf.kind == JavaScriptPublicSymbolKind.GETTER || "readonly" in leaf.qualifiers) &&
        javascriptTypeCompatible(leaf.signature.orEmpty(), ordinaryType)
}

private fun invalidConversationStateSnapshotErrors(
    projections: List<JavaScriptProjection>,
): List<String> {
    val snapshots = projections.filter {
        it.member.isExactD046Conversation() || it.member.isExactD046TurnProgress()
    }
    if (snapshots.isEmpty()) return emptyList()
    val related = projections.filter { projection ->
        projection in snapshots || projection.member.isExactD046ConversationState() ||
            projection.member.isExactD046ActiveTurnProgress()
    }
    val exact = snapshots.size == 2 &&
        snapshots.count { it.member.isExactD046Conversation() } == 1 &&
        snapshots.count { it.member.isExactD046TurnProgress() } == 1 &&
        related.count { it.member.isExactD046ConversationState() } == 1 &&
        related.count { it.member.isExactD046ActiveTurnProgress() } == 1
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript conversation state snapshot for capabilities " +
            related.map { it.member.key }.sorted(),
    )
}

private fun isAllowedAgentTurnRequestReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (symbol != javaScriptAgentTurnRequestType || projections.size != 11) return false
    val requestMembers = projections.filter { it.member.isExactD047AgentTurnRequestMember() }
    val send = projections.singleOrNull { it.member.isExactD047SendRequest() } ?: return false
    return requestMembers.size == 10 &&
        requestMembers.map { it.member.key }.distinct().size == 10 &&
        requestMembers.all {
            it.publicSymbols == listOf(javaScriptAgentTurnRequestType) &&
                it.shareablePublicSymbols == setOf(javaScriptAgentTurnRequestType)
        } &&
        send.publicSymbols == javaScriptAgentTurnRequestSymbols &&
        send.shareablePublicSymbols == setOf(javaScriptAgentTurnRequestType)
}

private fun invalidAgentTurnRequestErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD047AgentTurnRequestSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptAgentTurnRequestSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val requestMembers = canonicalMembers.filter(CanonicalJavaScriptMember::isExactD047AgentTurnRequestMember)
    val sendMembers = canonicalMembers.filter(CanonicalJavaScriptMember::isExactD047SendRequest)
    val exact = canonicalMembers.size == 11 && requestMembers.size == 10 && sendMembers.size == 1 &&
        related.size == 11 && related.map { it.member.key }.distinct().size == 11 &&
        related.count { projection ->
            projection.member.isExactD047AgentTurnRequestMember() &&
                projection.publicSymbols == listOf(javaScriptAgentTurnRequestType) &&
                projection.shareablePublicSymbols == setOf(javaScriptAgentTurnRequestType)
        } == 10 &&
        related.count { projection ->
            projection.member.isExactD047SendRequest() &&
                projection.publicSymbols == javaScriptAgentTurnRequestSymbols &&
                projection.shareablePublicSymbols == setOf(javaScriptAgentTurnRequestType)
        } == 1
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript AgentTurnRequest family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun isAllowedAgentHookHandlerReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean = symbol == javaScriptAgentHookHandlerType && projections.size == 8 &&
    projections.map { it.member.key }.distinct().size == 8 &&
    projections.all {
        it.member.isExactD048AgentHookHandlerMember() &&
            it.publicSymbols == listOf(javaScriptAgentHookHandlerType) &&
            it.shareablePublicSymbols == setOf(javaScriptAgentHookHandlerType)
    }

private fun invalidAgentHookHandlerErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD048AgentHookHandlerSurfaceMember)
    val related = projections.filter { javaScriptAgentHookHandlerType in it.publicSymbols }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 8 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD048AgentHookHandlerMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 8 &&
        related.size == 8 && related.map { it.member.key }.distinct().size == 8 &&
        related.all {
            it.member.isExactD048AgentHookHandlerMember() &&
                it.publicSymbols == listOf(javaScriptAgentHookHandlerType) &&
                it.shareablePublicSymbols == setOf(javaScriptAgentHookHandlerType)
        }
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript AgentHookHandler family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun invalidMcpServersErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD050McpServersSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptMcpServersSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 43 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD050McpServersMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 43 &&
        related.size == 43 && related.map { it.member.key }.distinct().size == 43 &&
        related.all { projection ->
            projection.member.isExactD050McpServersMember() &&
                projection.publicSymbols == projection.member.d050McpServersPublicSymbols() &&
                projection.shareablePublicSymbols.isEmpty()
        } && related.flatMap(JavaScriptProjection::publicSymbols).toSet() ==
        javaScriptMcpServersSymbols.toSet()
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript MCP Servers family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun isAllowedIntegrationAuthorizationReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (symbol == javaScriptAgentIntegrationType) {
        return projections.size == 2 && projections.map { it.member.name }.toSet() ==
            setOf("id", "displayName") && projections.all {
            it.member.simpleOwner == "AgentIntegration" &&
                it.member.isExactD051IntegrationAuthorizationMember() &&
                symbol in it.shareablePublicSymbols
        }
    }
    val parsed = parseJavaScriptPublicSymbol(symbol)
    if (parsed.kind != JavaScriptPublicSymbolKind.GETTER || parsed.owner !in setOf(
            "AgentConnectorIntegration",
            "AgentMcpServerIntegration",
        ) || parsed.name !in setOf("id", "displayName")
    ) return false
    val nestedOwner = if (parsed.owner == "AgentConnectorIntegration") {
        "AgentIntegration.Connector"
    } else {
        "AgentIntegration.McpServer"
    }
    return projections.size == 2 && projections.all {
        it.member.name == parsed.name && it.member.isExactD051IntegrationAuthorizationMember() &&
            symbol in it.shareablePublicSymbols
    } && projections.map { it.member.simpleOwner }.toSet() == setOf("AgentIntegration", nestedOwner)
}

private fun invalidIntegrationAuthorizationErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD051IntegrationAuthorizationSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptIntegrationAuthorizationSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 20 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD051IntegrationAuthorizationMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 20 &&
        related.size == 20 && related.map { it.member.key }.distinct().size == 20 &&
        related.all { projection ->
            projection.member.isExactD051IntegrationAuthorizationMember() &&
                projection.publicSymbols == projection.member.d051IntegrationAuthorizationPublicSymbols()
        } && related.flatMap(JavaScriptProjection::publicSymbols).toSet() ==
        javaScriptIntegrationAuthorizationSymbols.toSet()
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript integration authorization family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun invalidPluginsErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD054PluginsSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptPluginsSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 47 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD054PluginsMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 47 &&
        related.size == 47 && related.map { it.member.key }.distinct().size == 47 &&
        related.all { projection ->
            projection.member.isExactD054PluginsMember() &&
                projection.publicSymbols == projection.member.d054PluginsPublicSymbols() &&
                projection.shareablePublicSymbols.isEmpty()
        } && related.flatMap(JavaScriptProjection::publicSymbols).toSet() ==
        javaScriptPluginsSymbols.toSet()
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript Plugins family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun isAllowedAgentFormValueReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    if (symbol != javaScriptAgentFormValueType || projections.size != 3) return false
    val expectedNames = setOf("constructor", "defaultValue", "accepts")
    return projections.all { projection ->
        projection.member.isExactD057AgentFormFieldMember() &&
            projection.shareablePublicSymbols == setOf(javaScriptAgentFormValueType) &&
            projection.publicSymbols == projection.member.d057AgentFormFieldPublicSymbols()
    } && projections.map { projection ->
        if (projection.member.kind == CanonicalJavaScriptMemberKind.CONSTRUCTOR) "constructor"
        else projection.member.name
    }.toSet() == expectedNames
}

private fun invalidAgentFormFieldErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD057AgentFormFieldSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptAgentFormFieldSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 18 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD057AgentFormFieldMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 18 &&
        related.size == 18 && related.map { it.member.key }.distinct().size == 18 &&
        related.all { projection ->
            projection.member.isExactD057AgentFormFieldMember() &&
                projection.publicSymbols == projection.member.d057AgentFormFieldPublicSymbols() &&
                projection.shareablePublicSymbols ==
                projection.publicSymbols.filterTo(mutableSetOf()) { it == javaScriptAgentFormValueType }
        } && related.flatMap(JavaScriptProjection::publicSymbols).toSet() ==
        javaScriptAgentFormFieldSymbols.toSet()
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript AgentFormField family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun isAllowedPendingInteractionReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean = symbol == javaScriptPendingInteractionType && projections.size == 2 &&
    projections.all { projection ->
        projection.member.simpleOwner == "AgentPendingInteraction" &&
            projection.member.name in setOf("requestId", "conversationId") &&
            projection.member.isExactD059InteractionsMember() &&
            projection.publicSymbols == listOf(javaScriptPendingInteractionType) &&
            projection.shareablePublicSymbols == setOf(javaScriptPendingInteractionType)
    }

private fun invalidInteractionsErrors(
    canonicalKeys: List<String>,
    projections: List<JavaScriptProjection>,
): List<String> {
    val canonicalMembers = canonicalKeys.map(::parseCanonicalJavaScriptMember)
        .filter(CanonicalJavaScriptMember::isD059InteractionsSurfaceMember)
    val related = projections.filter { projection ->
        projection.publicSymbols.any(javaScriptInteractionsSymbols::contains)
    }
    if (canonicalMembers.isEmpty() && related.isEmpty()) return emptyList()
    val exact = canonicalMembers.size == 40 &&
        canonicalMembers.all(CanonicalJavaScriptMember::isExactD059InteractionsMember) &&
        canonicalMembers.map(CanonicalJavaScriptMember::key).distinct().size == 40 &&
        related.size == 40 && related.map { it.member.key }.distinct().size == 40 &&
        related.all { projection ->
            projection.member.isExactD059InteractionsMember() &&
                projection.publicSymbols == projection.member.d059InteractionsPublicSymbols() &&
                projection.shareablePublicSymbols ==
                projection.publicSymbols.filterTo(mutableSetOf()) { it == javaScriptPendingInteractionType }
        } && related.flatMap(JavaScriptProjection::publicSymbols).toSet() ==
        javaScriptInteractionsSymbols.toSet()
    return if (exact) emptyList() else listOf(
        "Incomplete JavaScript/TypeScript Interactions family for capabilities " +
            (canonicalMembers.map(CanonicalJavaScriptMember::key) + related.map { it.member.key })
                .distinct()
                .sorted(),
    )
}

private fun isAllowedAgentInvocationMemberReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    val leaf = when {
        symbol == javaScriptAgentInvocationType -> null
        symbol.startsWith("getter:AgentPluginInvocation#") -> "AgentInvocation.Plugin"
        symbol.startsWith("getter:AgentSkillInvocation#") -> "AgentInvocation.Skill"
        else -> return false
    }
    if (symbol == javaScriptAgentInvocationType) {
        return projections.size == 2 && projections.all { projection ->
            val name = projection.member.exactAgentInvocationBaseName() ?: return@all false
            projection.publicSymbols == agentInvocationBaseSymbols(name)
        } && projections.mapNotNull { it.member.exactAgentInvocationBaseName() }.toSet() == setOf("key", "name")
    }
    val parsed = parseJavaScriptPublicSymbol(symbol)
    val name = parsed.name
    val base = projections.singleOrNull {
        it.member.exactAgentInvocationBaseName() == name && it.publicSymbols == agentInvocationBaseSymbols(name)
    } ?: return false
    val nested = projections.singleOrNull {
        it.member.owner == "$canonicalAgentPackage/$leaf" &&
            it.member.isExactProperty(checkNotNull(leaf), name, "kotlin/String!!") &&
            it.publicSymbols == listOf(symbol)
    } ?: return false
    return base !== nested && projections.size == 2
}

private fun isAllowedFlattenedValueReuse(
    symbol: String,
    projections: List<JavaScriptProjection>,
): Boolean {
    val members = projections.map(JavaScriptProjection::member)
    if (members.map { it.owner.substringBeforeLast('/') }.distinct().size != 1) return false
    if (symbol == javaScriptCreateCodexHost) {
        return members.size == 5 && members.map(CanonicalJavaScriptMember::key).distinct().size == 5 &&
            members.count(CanonicalJavaScriptMember::isExactCodexHostFactoryConstructor) == 1 &&
            members.count(CanonicalJavaScriptMember::isExactCodexClientInfoMember) == 4
    }
    if (symbol == javaScriptApiKeyAuthentication) {
        return members.size == 3 && members.map(CanonicalJavaScriptMember::key).distinct().size == 3 &&
            members.count(CanonicalJavaScriptMember::isExactAuthenticationFunction) == 1 &&
            members.count {
                it.isExactConstructor(
                    "CodexAuthenticationMethod.ApiKey",
                    listOf(
                        CanonicalJavaScriptParameter(
                            "kotlin/String!!",
                            hasDefault = false,
                            isVararg = false,
                        ),
                    ),
                )
            } == 1 && members.count {
                it.isExactProperty("CodexAuthenticationMethod.ApiKey", "value", "kotlin/String!!")
            } == 1
    }
    val accepts: (CanonicalJavaScriptMember) -> Boolean = when (symbol) {
        javaScriptOpenConversation -> { member ->
            member.isExactOpenConversationFunction() || member.isExactConversationSettingsMember() ||
                member.isExactConversationIdMember()
        }
        javaScriptRenameConversation -> { member ->
            member.isExactRenameConversationFunction() || member.isExactConversationIdMember()
        }
        javaScriptDeleteConversation -> { member ->
            member.isExactDeleteConversationFunction() || member.isExactConversationIdMember()
        }
        javaScriptSelectWorkspace -> { member ->
            member.isExactSelectWorkspaceFunction() || member.isExactPathWorkspaceSelectionMember()
        }
        else -> return false
    }
    return members.any {
        it.isExactConversationSettingsMember() || it.isExactConversationIdMember() ||
            it.isExactPathWorkspaceSelectionMember()
    } && members.all(accepts)
}

private fun CanonicalJavaScriptMember.isExactRenameConversationFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        "CodexConversations",
        "rename",
        "kotlin/Unit",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/ConversationId!!",
                hasDefault = false,
                isVararg = false,
            ),
            CanonicalJavaScriptParameter("kotlin/String!!", hasDefault = false, isVararg = false),
        ),
    )
}

private fun CanonicalJavaScriptMember.isExactDeleteConversationFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        "CodexConversations",
        "delete",
        "kotlin/Unit",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/ConversationId!!",
                hasDefault = false,
                isVararg = false,
            ),
        ),
    )
}

private fun CanonicalJavaScriptMember.isExactSelectWorkspaceFunction(): Boolean {
    val canonicalPackage = owner.substringBeforeLast('/')
    return isExactFunction(
        "CodexHost",
        "selectWorkspace",
        "kotlin/Unit",
        expectedSuspend = true,
        expectedParameters = listOf(
            CanonicalJavaScriptParameter(
                "$canonicalPackage/CodexWorkspaceSelection!!",
                hasDefault = false,
                isVararg = false,
            ),
        ),
    )
}

private fun splitJavaScriptTopLevel(value: String, separator: Char = ','): List<String> {
    if (value.isBlank()) return emptyList()
    var angle = 0
    var parenthesis = 0
    var bracket = 0
    var brace = 0
    var start = 0
    val result = mutableListOf<String>()
    value.forEachIndexed { index, char ->
        when (char) {
            '<' -> angle++
            '>' -> if (angle > 0) angle--
            '(' -> parenthesis++
            ')' -> parenthesis--
            '[' -> bracket++
            ']' -> bracket--
            '{' -> brace++
            '}' -> brace--
            separator -> if (angle == 0 && parenthesis == 0 && bracket == 0 && brace == 0) {
                result += value.substring(start, index).trim()
                start = index + 1
            }
        }
        check(angle >= 0 && parenthesis >= 0 && bracket >= 0 && brace >= 0) {
            "Malformed JavaScript/TypeScript nested value: $value"
        }
    }
    check(angle == 0 && parenthesis == 0 && bracket == 0 && brace == 0) {
        "Malformed JavaScript/TypeScript nested value: $value"
    }
    result += value.substring(start).trim()
    return result
}

private fun validateJavaScriptPackedPublicApiEvidence(
    evidence: JavaScriptPackedPublicApiEvidence,
    requireSchemaTwo: Boolean,
): List<JavaScriptPublicSymbol> {
    check(evidence.schema == 1 || evidence.schema == 2) {
        "Unsupported packed public API schema: ${evidence.schema}"
    }
    if (requireSchemaTwo) check(evidence.schema == 2) {
        "A JavaScript/TypeScript parity receipt requires packed public API schema 2"
    }
    check(evidence.packageName == JAVASCRIPT_NPM_PACKAGE) {
        "Unexpected JavaScript/TypeScript npm coordinate: ${evidence.packageName}"
    }
    check(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?")
        .matches(evidence.packageVersion)) {
        "Malformed JavaScript/TypeScript npm version: ${evidence.packageVersion}"
    }

    val artifactIds = evidence.artifacts.map(JavaScriptPackedArtifact::id)
    check(artifactIds == requiredJavaScriptArtifactIds) {
        "Packed public API artifact inventory differs: expected=$requiredJavaScriptArtifactIds actual=$artifactIds"
    }
    val fileNames = evidence.artifacts.map(JavaScriptPackedArtifact::fileName)
    check(fileNames.distinct().size == fileNames.size) { "Packed public API artifact file names are duplicated" }
    val expectedFileNames = mapOf(
        "commonJs" to "index.cjs",
        "declaration" to "index.d.ts",
        "esm" to "index.mjs",
        "packageJson" to "package.json",
        "tarball" to "codex-agent-${evidence.packageVersion}.tgz",
    )
    evidence.artifacts.forEach { artifact ->
        jsRequireRecord(artifact.id, "packed public API artifact")
        check(
            artifact.fileName.isNotBlank() && artifact.fileName !in setOf(".", "..") &&
                artifact.fileName == File(artifact.fileName).name && artifact.fileName.none(Char::isISOControl),
        ) { "Packed public API artifact ${artifact.id} has an unsafe file name" }
        check(artifact.bytes > 0) { "Packed public API artifact ${artifact.id} is empty" }
        jsRequireSha256(artifact.sha256, "packed public API artifact ${artifact.id}")
        check(artifact.fileName == expectedFileNames.getValue(artifact.id)) {
            "Packed public API artifact ${artifact.id} has unexpected file name: ${artifact.fileName}"
        }
    }

    listOf(
        evidence.typeExports to "type export",
        evidence.valueExports to "value export",
        evidence.commonJsExports to "CommonJS export",
        evidence.esmExports to "ESM export",
        evidence.publicSymbols to "public symbol",
        evidence.referencedSymbols to "consumer-referenced public symbol",
    ).forEach { (values, label) -> jsRequireSortedUnique(values, label) }
    check(evidence.publicSymbols.isNotEmpty()) { "Packed public API symbol inventory is empty" }
    val symbols = evidence.publicSymbols.map(::parseJavaScriptPublicSymbol)
    val classNames = symbols.filter { it.kind == JavaScriptPublicSymbolKind.CLASS }.map(JavaScriptPublicSymbol::name)
    val typeNames = symbols.filter { it.kind == JavaScriptPublicSymbolKind.TYPE }.map(JavaScriptPublicSymbol::name)
    val functionNames = symbols.filter { it.kind == JavaScriptPublicSymbolKind.FUNCTION }.map(JavaScriptPublicSymbol::name)
    jsRequireSortedUnique(classNames.sorted(), "public class")
    jsRequireSortedUnique(typeNames.sorted(), "public type")
    jsRequireSortedUnique(functionNames.sorted(), "public function")
    val expectedTypeExports = (classNames + typeNames).sorted()
    val expectedValueExports = (classNames + functionNames).sorted()
    check(evidence.typeExports == expectedTypeExports) {
        "Packed public API type exports do not match compiler symbols"
    }
    check(evidence.valueExports == expectedValueExports) {
        "Packed public API value exports do not match compiler symbols"
    }
    check(evidence.commonJsExports == expectedValueExports && evidence.esmExports == expectedValueExports) {
        "Packed public API runtime exports do not match compiler symbols"
    }
    val classes = classNames.toSet()
    symbols.filter { it.owner != null }.forEach { symbol ->
        check(symbol.owner in classes) { "Public member owner is not an exported class: ${symbol.raw}" }
    }

    if (evidence.schema == 1) check(evidence.referencedSymbols.isEmpty()) {
        "Packed public API schema 1 cannot contain consumer references"
    }
    val staleReferences = evidence.referencedSymbols.toSet() - evidence.publicSymbols.toSet()
    check(staleReferences.isEmpty()) {
        "Consumer evidence references stale public symbols: ${staleReferences.sorted()}"
    }
    jsRequireRecord(evidence.compilerTestId, "compiler evidence test")
    return symbols
}

private fun JsonObject.jsRequireKeys(label: String, vararg expected: String) {
    check(keys == expected.toSet()) {
        "Invalid $label keys: expected=${expected.sorted()} actual=${keys.sorted()}"
    }
}

private fun JsonObject.jsExactString(name: String): String {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON string: $name")
    check(primitive.isString) { "JSON field $name must be a string" }
    return primitive.contentOrNull ?: error("Missing JSON string: $name")
}

private fun JsonObject.jsExactInt(name: String): Int {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON integer: $name")
    check(!primitive.isString) { "JSON field $name must be an integer" }
    return primitive.intOrNull ?: error("Missing JSON integer: $name")
}

private fun JsonObject.jsExactLong(name: String): Long {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON long: $name")
    check(!primitive.isString) { "JSON field $name must be a long" }
    return primitive.longOrNull ?: error("Missing JSON long: $name")
}

private fun JsonObject.jsExactObject(name: String): JsonObject = this[name] as? JsonObject
    ?: error("Missing JSON object: $name")

private fun JsonObject.jsExactStrings(name: String): List<String> {
    val array = this[name] as? JsonArray ?: error("Missing JSON array: $name")
    return array.map { value ->
        val primitive = value as? JsonPrimitive ?: error("$name must contain only strings")
        check(primitive.isString) { "$name must contain only strings" }
        primitive.content
    }
}

private fun JsonObject.jsExactSha256(name: String): String = jsExactString(name).also {
    jsRequireSha256(it, name)
}

private fun jsRequireSha256(value: String, label: String) {
    check(value.length == 64 && value.all { char -> char in '0'..'9' || char in 'a'..'f' }) {
        "$label is not an exact SHA-256"
    }
}

private fun jsRequireSortedUnique(values: List<String>, label: String) {
    values.forEach { jsRequireRecord(it, label) }
    check(values == values.sorted()) { "$label inventory is not sorted" }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it > 1 }.keys
    check(duplicates.isEmpty()) { "$label inventory is duplicated: ${duplicates.sorted()}" }
}

private fun jsRequireRecord(value: String, label: String) {
    check(value.isNotBlank() && value == value.trim() && '*' !in value && value.none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $value"
    }
}
