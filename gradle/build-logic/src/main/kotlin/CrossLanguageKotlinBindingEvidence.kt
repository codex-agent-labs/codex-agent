import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

internal data class KotlinBindingDigestEvidence(
    val artifactSha256: String,
    val apiReportSha256: String,
    val canonicalCoverageSha256: String,
    val compiledTestsSha256: String,
    val testResultsSha256: String,
)

internal data class KotlinBindingCapabilityClaim(
    val capabilityKey: String,
    val publicSymbol: String,
)

internal data class KotlinBindingScenarioMapping(
    val scenarioId: String,
    val canonicalTestIds: List<String>,
) {
    constructor(scenarioId: String, canonicalTestId: String) : this(scenarioId, listOf(canonicalTestId))
}

internal data class CrossLanguageKotlinBindingEvidence(
    val digests: KotlinBindingDigestEvidence,
    val capabilityClaims: List<KotlinBindingCapabilityClaim>,
    val bindingTests: List<CrossLanguageBindingTestEvidence>,
    val scenarioEvidence: List<CrossLanguageScenarioEvidence>,
)

private const val CANONICAL_TEST_PACKAGE = "io.github.codex_agent_labs.codexmobile.agent."

internal val kotlinBindingScenarioMappings = listOf(
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_SUCCESS.id,
        CANONICAL_TEST_PACKAGE +
            "IntegrationAuthorizationControllerTest#publicFacadeAuthorizesConnectorAndMcpTargetsThroughOneActiveProjection",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.ASYNC_FAILURE.id,
        CANONICAL_TEST_PACKAGE +
            "IntegrationAuthorizationControllerTest#connectorWithoutAnAuthorizationUrlFailsClearly",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.CANCELLATION.id,
        CANONICAL_TEST_PACKAGE +
            "CodexConversationTest#cancellationWaitsForTheTurnIdWhenProgressArrivesBeforeTheStartResponse",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_CURRENT_VALUE.id,
        CANONICAL_TEST_PACKAGE +
            "AuthenticationControllerTest#deviceCodeAuthenticationProjectsTheLiveFacadeState",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE.id,
        CANONICAL_TEST_PACKAGE +
            "CodexConversationTest#exposesCanonicalMessagesTurnProgressAndCapabilitiesAsStateFlows",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION.id,
        CANONICAL_TEST_PACKAGE +
            "CodexConversationTest#exposesCanonicalMessagesTurnProgressAndCapabilitiesAsStateFlows",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.TERMINAL_DELIVERY.id,
        CANONICAL_TEST_PACKAGE +
            "InteractionControllerTest#lateResolutionFailureAfterCloseDoesNotRepublishState",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.STRUCTURED_FAILURE.id,
        CANONICAL_TEST_PACKAGE +
            "CrossLanguageDomainValueContractTest#failureAndWorkspaceValuesExposeEverySupportedFieldAndInvariant",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.IDENTITY.id,
        CANONICAL_TEST_PACKAGE +
            "CodexHostTest#ownedHostUsesClientIdentityPreparedPathAndDeclaredFeatures",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP.id,
        CANONICAL_TEST_PACKAGE +
            "CodexHostTest#restoresSelectsReplacesRetriesAndClosesOneOwnedGraph",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE.id,
        CANONICAL_TEST_PACKAGE +
            "CodexHostTest#readyAgentPublishesReturnedConversationAndResolvesTypedApproval",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.NULLABILITY.id,
        CANONICAL_TEST_PACKAGE +
            "AgentModelResolutionTest#serviceTierResolutionIsNullableOnlyWhenTheModelHasNoTiers",
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING.id,
        listOf(
            CANONICAL_TEST_PACKAGE +
                "CodexPublicApiAdoptionTest#elicitationHelpersShareOneValidatorAndSnapshotResponses",
            CANONICAL_TEST_PACKAGE +
                "AgentPluginCatalogMergeTest#mergesInstalledStateWithoutReorderingAvailablePlugins",
        ),
    ),
    KotlinBindingScenarioMapping(
        CrossLanguageBindingScenario.VALUE_CONVERSION.id,
        CANONICAL_TEST_PACKAGE +
            "AgentMcpConfigurationTest#typedConfigurationRoundTripsEverySupportedField",
    ),
)

internal fun deriveCrossLanguageKotlinBindingEvidence(
    kotlinArtifact: File,
    apiReport: File,
    canonicalCoverageReceipt: File,
    scenarioMappings: List<KotlinBindingScenarioMapping> = kotlinBindingScenarioMappings,
): CrossLanguageKotlinBindingEvidence {
    check(kotlinArtifact.exists()) { "Kotlin binding artifact is missing" }
    check(apiReport.isFile && apiReport.length() > 0L) { "Cross-language API report is missing or empty" }
    check(canonicalCoverageReceipt.isFile && canonicalCoverageReceipt.length() > 0L) {
        "Canonical coverage receipt is missing or empty"
    }

    val artifactDigest = kotlinArtifact.kotlinBindingArtifactDigest()
    val reportRoot = apiReport.readReleaseObject()
    val jvmTargets = reportRoot.releaseArray("targets").map { value ->
        val target = value as? JsonObject ?: error("Invalid cross-language API target")
        check(target.keys == setOf("kind", "sha256")) { "Invalid cross-language API target shape" }
        target.releaseString("kind") to target.exactTargetSha256()
    }.filter { (kind, _) -> kind == "jvm-classes" }
    check(jvmTargets.size == 1) { "Cross-language API report must contain exactly one jvm-classes target" }
    check(jvmTargets.single().second == artifactDigest) {
        "Cross-language API report jvm-classes target digest mismatch"
    }

    val reportMembers = readCrossLanguageApiMemberKeys(apiReport)
    val reportDigest = apiReport.releaseDigest()
    val coverage = canonicalCoverageReceipt.readReleaseObject()
    check(coverage.keys == setOf(
        "schema", "result", "kotlinCompilerVersion", "canonicalTestTask", "apiReportSha256",
        "compiledTestsSha256", "testResultsSha256", "members", "claims",
    )) { "Invalid canonical coverage receipt shape" }
    check(coverage.releaseInt("schema") == 1) { "Unsupported canonical coverage receipt schema" }
    check(coverage.releaseString("result") == "passed") { "Canonical coverage receipt did not pass" }
    check(coverage.releaseString("kotlinCompilerVersion").isNotBlank()) {
        "Canonical coverage Kotlin compiler identity is blank"
    }
    check(coverage.releaseString("canonicalTestTask").isNotBlank()) {
        "Canonical coverage test task identity is blank"
    }
    check(coverage.releaseString("apiReportSha256") == reportDigest) {
        "Canonical coverage API report digest mismatch"
    }
    val compiledTestsDigest = coverage.exactSha256("compiledTestsSha256")
    val testResultsDigest = coverage.exactSha256("testResultsSha256")

    val receiptMembers = coverage.releaseArray("members").map { value ->
        (value as? JsonPrimitive)?.content ?: error("Invalid canonical coverage member")
    }
    requireUniqueExact(receiptMembers, "Canonical coverage member")
    check(receiptMembers == reportMembers) { "Canonical coverage member/report mismatch" }

    val receiptClaims = coverage.releaseArray("claims").map { value ->
        val claim = value as? JsonObject ?: error("Invalid canonical coverage claim")
        check(claim.keys == setOf("testId", "members")) { "Invalid canonical coverage claim shape" }
        val testId = claim.releaseString("testId")
        val members = claim.releaseArray("members").map { member ->
            (member as? JsonPrimitive)?.content ?: error("Invalid canonical coverage claim member")
        }
        requireExact(testId, "Canonical coverage claim test")
        check(members.isNotEmpty()) { "Canonical coverage claim is empty: $testId" }
        requireUniqueExact(members, "Canonical coverage claim member for $testId")
        testId to members
    }
    requireUniqueExact(receiptClaims.map(Pair<String, List<String>>::first), "Canonical coverage claim test")

    val reportMemberSet = reportMembers.toSet()
    val claimedMembers = receiptClaims.flatMap(Pair<String, List<String>>::second).toSet()
    check(claimedMembers == reportMemberSet) {
        "Canonical coverage claim/member mismatch: missing=${(reportMemberSet - claimedMembers).sorted()} " +
            "stale=${(claimedMembers - reportMemberSet).sorted()}"
    }
    val passedTestIds = receiptClaims.map(Pair<String, List<String>>::first).toSet()

    val scenarioById = CrossLanguageBindingScenario.entries.associateBy(CrossLanguageBindingScenario::id)
    val mappingsByScenario = scenarioMappings.groupBy(KotlinBindingScenarioMapping::scenarioId)
    mappingsByScenario.filterValues { it.size > 1 }.forEach { (scenarioId, mappings) ->
        val label = if (mappings.map(KotlinBindingScenarioMapping::canonicalTestIds).distinct().size == 1) {
            "Duplicate"
        } else {
            "Conflicting"
        }
        error("$label Kotlin binding scenario mapping $scenarioId")
    }
    val unknownScenarios = (mappingsByScenario.keys - scenarioById.keys).sorted()
    check(unknownScenarios.isEmpty()) { "Unknown Kotlin binding scenarios: $unknownScenarios" }
    val missingScenarios = (scenarioById.keys - mappingsByScenario.keys).sorted()
    check(missingScenarios.isEmpty()) { "Missing Kotlin binding scenarios: $missingScenarios" }

    val scenarioEvidence = CrossLanguageBindingScenario.entries.map { scenario ->
        val mapping = mappingsByScenario.getValue(scenario.id).single()
        check(mapping.canonicalTestIds.isNotEmpty()) { "Kotlin binding scenario has no test: ${scenario.id}" }
        requireUniqueExact(mapping.canonicalTestIds, "Kotlin binding scenario test for ${scenario.id}")
        val staleTests = (mapping.canonicalTestIds.toSet() - passedTestIds).sorted()
        check(staleTests.isEmpty()) {
            "Unknown, stale, or non-passed Kotlin binding scenario tests for ${scenario.id}: $staleTests"
        }
        CrossLanguageScenarioEvidence(CrossLanguageBinding.KOTLIN, scenario, mapping.canonicalTestIds.sorted())
    }

    return CrossLanguageKotlinBindingEvidence(
        digests = KotlinBindingDigestEvidence(
            artifactSha256 = artifactDigest,
            apiReportSha256 = reportDigest,
            canonicalCoverageSha256 = canonicalCoverageReceipt.releaseDigest(),
            compiledTestsSha256 = compiledTestsDigest,
            testResultsSha256 = testResultsDigest,
        ),
        capabilityClaims = reportMembers.map { member ->
            KotlinBindingCapabilityClaim(member, member)
        },
        bindingTests = scenarioEvidence.flatMap(CrossLanguageScenarioEvidence::testIds).distinct().sorted().map { testId ->
            CrossLanguageBindingTestEvidence(
                CrossLanguageBinding.KOTLIN,
                testId,
                CrossLanguageBindingTestStatus.PASSED,
            )
        },
        scenarioEvidence = scenarioEvidence,
    )
}

private fun JsonObject.exactSha256(name: String): String = releaseString(name).also { digest ->
    check(digest.length == 64 && digest.all { it in '0'..'9' || it in 'a'..'f' }) {
        "Canonical coverage $name is not an exact SHA-256"
    }
}

private fun JsonObject.exactTargetSha256(): String = releaseString("sha256").also { digest ->
    check(digest.length == 64 && digest.all { it in '0'..'9' || it in 'a'..'f' }) {
        "Cross-language API target sha256 is not an exact SHA-256"
    }
}

private fun requireUniqueExact(values: List<String>, label: String) {
    values.forEach { requireExact(it, label) }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label identities are duplicated: $duplicates" }
}

private fun requireExact(value: String, label: String) {
    check(value.isNotBlank() && '*' !in value) { "$label is blank or wildcard: $value" }
}

internal fun File.kotlinBindingArtifactDigest(): String = when {
    isFile && length() > 0L -> releaseDigest()
    isDirectory -> crossLanguageTreeDigest()
    else -> error("Kotlin binding artifact is empty or unsupported")
}
