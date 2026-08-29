import java.io.File

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

private const val CANONICAL_TEST_PACKAGE = "io.github.codex_agent_labs.codexagent.agent."

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
    val canonicalEvidence = readCrossLanguageCanonicalApiEvidence(apiReport, canonicalCoverageReceipt)
    check(canonicalEvidence.targetSha256.getValue("jvm-classes") == artifactDigest) {
        "Cross-language API report jvm-classes target digest mismatch"
    }
    val reportMembers = canonicalEvidence.memberKeys
    val passedTestIds = canonicalEvidence.coveredTestIds

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
            apiReportSha256 = canonicalEvidence.canonical.apiReportSha256,
            canonicalCoverageSha256 = canonicalEvidence.canonical.coverageReceiptSha256,
            compiledTestsSha256 = canonicalEvidence.compiledTestsSha256,
            testResultsSha256 = canonicalEvidence.testResultsSha256,
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
