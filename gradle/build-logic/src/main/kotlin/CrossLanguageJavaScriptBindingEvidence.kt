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
internal const val JAVASCRIPT_NPM_PACKAGE = "@codex-agent-labs/codex-agent"

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

    canonical.memberKeys.forEach { key ->
        val member = parseCanonicalJavaScriptMember(key)
        val candidates = javaScriptProjectionCandidates(member, symbols).distinctBy { it.publicSymbols }
        when {
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
                    provisional += JavaScriptProjection(member, candidate.publicSymbols, candidate.scenarios)
                }
            }
        }
    }

    provisional.flatMap { projection ->
        projection.publicSymbols.map { symbol -> symbol to projection }
    }.groupBy(Pair<String, JavaScriptProjection>::first).forEach { (symbol, uses) ->
        val projections = uses.map(Pair<String, JavaScriptProjection>::second)
        if (projections.size > 1 && !isAllowedLiteralTypeReuse(symbol, projections)) {
            errors += "Reused JavaScript/TypeScript public symbol $symbol for capabilities " +
                projections.map { it.member.key }.sorted()
        }
    }

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
    check(claimKeys.size == claimKeys.distinct().size && claimKeys.toSet() == canonicalKeys) {
        "JavaScript/TypeScript claims do not exactly cover the canonical API"
    }
    val receipt = CrossLanguageBindingReceipt(
        phase = CrossLanguageBindingPhase.M7_5,
        language = CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
        canonical = evidence.canonical.canonical,
        artifacts = artifacts,
        testProgramSha256 = testProgramSha256,
        testResultsSha256 = testResultsSha256,
        publicSymbols = evidence.packedApi.publicSymbols,
        bindingTests = tests,
        scenarioEvidence = scenarioEvidence,
        projectionClaims = evidence.projectionClaims,
        applicabilityExclusions = emptyList(),
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
        listOf(jsLifecycleTest, jsAuthenticationTest),
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
)

private data class JavaScriptProjection(
    val member: CanonicalJavaScriptMember,
    val publicSymbols: List<String>,
    val scenarios: List<CrossLanguageBindingScenario>,
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
): List<JavaScriptProjectionCandidate> = when (member.kind) {
    CanonicalJavaScriptMemberKind.OBJECT -> objectProjectionCandidates(member, symbols)
    CanonicalJavaScriptMemberKind.ENUM_ENTRY -> enumProjectionCandidates(member, symbols)
    CanonicalJavaScriptMemberKind.PROPERTY -> propertyProjectionCandidates(member, symbols)
    CanonicalJavaScriptMemberKind.CONSTRUCTOR -> constructorProjectionCandidates(member, symbols)
    CanonicalJavaScriptMemberKind.FUNCTION -> functionProjectionCandidates(member, symbols)
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
    val elementType = unwrapStateFlowType(type)
    val target = when (member.simpleOwner to member.name) {
        "CodexHost" to "lifecycleState" -> Triple("CodexHost", "state", "observeState")
        "CodexConversations" to "active" -> Triple("CodexAgent", "activeConversation", "observeActiveConversation")
        "CodexConversation" to "state" -> Triple("CodexConversation", "state", "observeState")
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
        JavaScriptProjectionCandidate(
            publicSymbols = listOf(getter.raw, observer.raw).sorted(),
            scenarios = listOf(
                CrossLanguageBindingScenario.STATE_CURRENT_VALUE,
                CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE,
                CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION,
            ),
            requiresConsumerReference = true,
        )
    }
}

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
            scenarios = listOf(CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP),
            requiresConsumerReference = true,
        )
    }
}

private fun functionProjectionCandidates(
    member: CanonicalJavaScriptMember,
    symbols: List<JavaScriptPublicSymbol>,
): List<JavaScriptProjectionCandidate> {
    val targetOwner = when (member.simpleOwner) {
        "CodexConversations" -> "CodexAgent"
        else -> javascriptOwnerName(member.simpleOwner.removeSuffix(".Companion"))
    }
    val targetName = when {
        member.simpleOwner == "CodexConversations" && member.name == "open" -> "openConversation"
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
    val canonicalParameters = member.parameters
    val canonicalPackage = member.owner.substringBeforeLast('/')
    val canonicalShape = !member.isSuspend && member.returnType == member.owner &&
        canonicalParameters.size == 2 && canonicalParameters.none { it.hasDefault || it.isVararg } &&
        canonicalParameters[0].type == "$canonicalPackage/CodexPlatform!!" &&
        canonicalParameters[1].type == "$canonicalPackage/CodexClientInfo!!"
    return canonicalShape && actual.returnType == "CodexHost" &&
        actual.parameters.map(JavaScriptParameter::name) == expectedNames &&
        actual.parameters.all { !it.optional && !it.vararg && normalizeJavaScriptType(it.type) == "string" }
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
        base.endsWith("/CodexAuthorizationUrl") -> "string"
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
