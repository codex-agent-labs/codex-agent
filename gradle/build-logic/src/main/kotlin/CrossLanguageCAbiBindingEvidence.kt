import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

internal const val C_ABI_BOOTSTRAP_SCHEMA = 1
internal const val C_ABI_BOOTSTRAP_PROTOCOL = "codex-agent-c-abi-bootstrap-evidence-v1"
internal const val C_ABI_SCENARIO_PROOF_SCHEMA = 1
internal const val C_ABI_SCENARIO_PROOF_ARTIFACT_ID = "c-abi-scenarios"
internal const val C_ABI_BINDING_CAPABILITY_COUNT = 556
internal const val C_ABI_BINDING_PUBLIC_SYMBOL_COUNT = 777
internal const val C_ABI_BINDING_ARTIFACT_COUNT = 7
internal const val C_ABI_BINDING_CAPABILITY_SHA256 =
    "9a73e6d5b49ae052b236cb432f380b3f342d68760655e04369c31d4724d2d4a9"
internal const val C_ABI_SCENARIO_SELECTED_TEST_COUNT = 138
internal const val C_ABI_SCENARIO_MAPPING_ROW_COUNT = 231
internal const val C_ABI_SCENARIO_SELECTED_TEST_SHA256 =
    "9672bf2f656ec48d4ab4cd7f7ea60ceea250ba2ced57a3624c4c589312bbd6e6"
internal const val C_ABI_SCENARIO_MAPPING_SHA256 =
    "d544777fe7d7b0cb0c17213fd436db77c10a8cb042007ff64b2c04eed7db1929"
internal val C_ABI_BINDING_ARTIFACT_IDS = sortedSetOf(
    "c-abi-bootstrap",
    C_ABI_SCENARIO_PROOF_ARTIFACT_ID,
    "c-abi-package-macos-arm64",
    "c-abi-package-macos-x64",
    "c-abi-package-linux-arm64",
    "c-abi-package-linux-x64",
    "c-abi-package-windows-x64",
)

internal data class CrossLanguageCAbiScenarioMapping(
    val scenario: CrossLanguageBindingScenario,
    val testIds: List<String>,
)

internal data class CrossLanguageCAbiScenarioProof(
    val mappings: List<CrossLanguageCAbiScenarioMapping>,
    val testProgramSha256: String,
    val testResultsSha256: String,
)

@CacheableTask
internal abstract class GenerateCrossLanguageCAbiScenarioProofTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val bootstrapEvidence: RegularFileProperty

    @get:OutputFile
    abstract val proofFile: RegularFileProperty

    @TaskAction
    fun generate() {
        writeCrossLanguageCAbiScenarioProof(
            proofFile.get().asFile,
            bootstrapEvidence.get().asFile,
            productionCrossLanguageCAbiScenarioMappings(),
        )
    }
}

internal fun productionCrossLanguageCAbiScenarioMappings(): List<CrossLanguageCAbiScenarioMapping> {
    val stateFlows = listOf(
        "CodexAgentCAuthenticationFlowsTest#authenticationIsAuthenticatedProjectsCurrentTransitionsAndOwnerTerminal",
        "CodexAgentCAuthenticationFlowsTest#authenticationIsAuthenticatingProjectsCurrentTransitionsAndOwnerTerminal",
        "CodexAgentCAuthenticationFlowsTest#authenticationStateProjectsCurrentTransitionsAndOwnerTerminal",
        "CodexAgentCConversationDerivedFlowsTest#activeTurnProgressGetterSubscriptionAndProjectorsPreserveNullableOwnedTransitions",
        "CodexAgentCConversationDerivedFlowsTest#canCancelTurnGetterAndSubscriptionProjectReadyActiveReadyClosed",
        "CodexAgentCConversationDerivedFlowsTest#canReloadGetterAndSubscriptionProjectReadyActiveReadyClosed",
        "CodexAgentCConversationDerivedFlowsTest#canRunShellCommandGetterAndSubscriptionProjectFeatureActiveAndDisabledStates",
        "CodexAgentCConversationDerivedFlowsTest#canStartTurnGetterAndSubscriptionProjectReadyActiveReadyClosed",
        "CodexAgentCConversationDerivedFlowsTest#currentMessagesGetterSubscriptionAndProjectorsPreserveOrderedOwnedTransitions",
        "CodexAgentCConversationDerivedFlowsTest#isTurnActiveGetterAndSubscriptionProjectReadyActiveReadyClosed",
        "CodexAgentCIntegrationAuthorizationFlowsTest#integrationAuthorizationActiveGetAndSubscribeProjectNullConnectorMcpNull",
        "CodexAgentCIntegrationAuthorizationFlowsTest#integrationAuthorizationIsAuthorizingGetAndSubscribeProjectFalseTrueFalse",
        "CodexAgentCIntegrationAuthorizationFlowsTest#integrationAuthorizationStateGetAndSubscribeProjectConnectorAndMcpTransitions",
        "CodexAgentCInteractionFlowsTest#interactionsApprovalsProjectCurrentChangeOwnedIdentityAndOwnerTerminal",
        "CodexAgentCInteractionFlowsTest#interactionsElicitationsProjectCurrentChangeOwnedIdentityAndOwnerTerminal",
        "CodexAgentCInteractionFlowsTest#interactionsStateProjectsCurrentOrderedPendingAndOwnerTerminal",
    ).map(::cAbiNativeTestId)
    val asyncSuccess = listOf(
        "CodexAgentCInteractionOperationsTest#openUrlUsesExactOwnedPendingIdentityAndOwnsBrowserPresentation",
        "CodexAgentCInteractionOperationsTest#resolveApprovalUsesExactOwnedPendingIdentityAndCompletesCancellableOperation",
        "CodexAgentCInteractionOperationsTest#resolveElicitationCopiesResponseAndUsesExactOwnedPendingIdentity",
        "CodexAgentCSuspendCatalogOperationsTest#connectorsListPreservesOrderAndDuplicates",
        "CodexAgentCSuspendCatalogOperationsTest#hooksInstallReturnsFreshOwnedHook",
        "CodexAgentCSuspendCatalogOperationsTest#hooksListReturnsFreshCatalog",
        "CodexAgentCSuspendCatalogOperationsTest#hooksTrustIsUnitAndCopiesHook",
        "CodexAgentCSuspendCatalogOperationsTest#hooksUninstallIsUnitAndConsumesCopiedInput",
        "CodexAgentCSuspendCatalogOperationsTest#mcpServersAddCopiesConfigurationAndReturnsServer",
        "CodexAgentCSuspendCatalogOperationsTest#mcpServersListReturnsFreshOrderedServers",
        "CodexAgentCSuspendCatalogOperationsTest#mcpServersRemoveIsUnitAndCopiesServer",
        "CodexAgentCSuspendCatalogOperationsTest#modelsListReturnsFreshOrderedDuplicates",
        "CodexAgentCSuspendCatalogOperationsTest#modelsResolveEffortCopiesModelBeforeLaunch",
        "CodexAgentCSuspendCatalogOperationsTest#modelsResolveHonorsExactResolution",
        "CodexAgentCSuspendCatalogOperationsTest#modelsResolveServiceTierDistinguishesPresentAndAbsent",
        "CodexAgentCSuspendCatalogOperationsTest#pluginsInstallReturnsFreshResult",
        "CodexAgentCSuspendCatalogOperationsTest#pluginsListCopiesFlagAndCatalog",
        "CodexAgentCSuspendCatalogOperationsTest#pluginsReadReturnsFreshDetail",
        "CodexAgentCSuspendCatalogOperationsTest#pluginsUninstallIsUnitAndCopiesReference",
        "CodexAgentCSuspendCatalogOperationsTest#skillsInstallReturnsFreshOwnedSkill",
        "CodexAgentCSuspendCatalogOperationsTest#skillsListCopiesFlagAndCatalog",
        "CodexAgentCSuspendCatalogOperationsTest#skillsReadCopiesPathAndOffset",
        "CodexAgentCSuspendCatalogOperationsTest#skillsUninstallIsUnitAndConsumesCopiedInput",
        "CodexAgentCSuspendConversationOperationsTest#catalogOperationsPreserveOrderDuplicatesOwnedResultsAndCopiedInputs",
        "CodexAgentCSuspendConversationOperationsTest#conversationOperationsCopyStructuredAndDefaultInputsAndCompleteShellAndReload",
        "CodexAgentCSuspendLifecycleOperationsTest#authenticationAuthenticateCopiesAndExecutesEveryMethodVariant",
        "CodexAgentCSuspendLifecycleOperationsTest#authenticationCancelCompletesCanonicalOperation",
        "CodexAgentCSuspendLifecycleOperationsTest#authenticationSignOutCompletesCanonicalOperation",
        "CodexAgentCSuspendLifecycleOperationsTest#hostStartCompletesCanonicalOperationAndHoldsTargetThroughCallback",
        "CodexAgentCSuspendLifecycleOperationsTest#integrationAuthorizationAuthorizeCopiesAndExecutesBothTargetVariants",
        "CodexAgentCSuspendLifecycleOperationsTest#integrationAuthorizationCancelCompletesCanonicalOperation",
    ).map(::cAbiNativeTestId)
    val values = listOf(
        "CodexAgentCAuthenticationConfigurationValuesTest#authenticationStateAndConversationSettingsProjectDefaultsNullabilityAndEveryEnum",
        "CodexAgentCAuthenticationConfigurationValuesTest#authenticationStateOwnsFreshNestedUrlsFailureAndCopiedCode",
        "CodexAgentCAuthenticationConfigurationValuesTest#authorizationUrlsAndClientInfoPreserveValuesAndRejectCanonicalInvalidInputs",
        "CodexAgentCConfigurationValuesTest#elicitationValidationIssueProjectsEveryReasonAndCopiesFieldName",
        "CodexAgentCConfigurationValuesTest#formOptionPreservesDefaultsNullabilityAndCopiedInput",
        "CodexAgentCConfigurationValuesTest#mcpEnvironmentVariableProjectsEverySourceAndAbsentSource",
        "CodexAgentCConfigurationValuesTest#mcpOauthConfigurationPreservesNullableValuesAndPortBoundaries",
        "CodexAgentCConfigurationValuesTest#mcpToolConfigurationProjectsEveryApprovalAndAbsentApproval",
        "CodexAgentCConfigurationValuesTest#planStepProjectsEveryStatusAndCopiesText",
        "CodexAgentCConversationAggregateValuesTest#projectsAgentConversationAndMessagesWithExactOrderedSnapshots",
        "CodexAgentCConversationAggregateValuesTest#projectsAgentConversationStateTruthTableAndNullableValuesExactly",
        "CodexAgentCConversationAggregateValuesTest#projectsAgentTurnRequestAndInvocationCarrierExactly",
        "CodexAgentCConversationValuesTest#createsAndValidatesFailures",
        "CodexAgentCConversationValuesTest#projectsConversationValuesWithIndependentNestedOwnership",
        "CodexAgentCConversationValuesTest#projectsEveryApprovalPresetAndWorkspaceSelectionReasonExactly",
        "CodexAgentCConversationValuesTest#projectsWorkspaceDefaultsAndIndependentAvailableOwnership",
        "CodexAgentCElicitationBehaviorValuesTest#elicitationInitialValidateAndAcceptUseExactOwnedMapSemantics",
        "CodexAgentCElicitationBehaviorValuesTest#formFieldAcceptsEveryTypeBoundFormatAndSelectionRule",
        "CodexAgentCElicitationBehaviorValuesTest#responseFactoriesAndElicitationAcceptsImplementExactTruthTable",
        "CodexAgentCElicitationInteractionValuesTest#elicitationAndResponseProjectEveryFieldAndOwnedCollection",
        "CodexAgentCElicitationInteractionValuesTest#formFieldsProjectEveryScalarNullableEnumOptionAndOwnedDefault",
        "CodexAgentCElicitationInteractionValuesTest#pendingElicitationAndInteractionStateProjectEveryFieldAndOwnedChild",
        "CodexAgentCFormHookValuesTest#projectsBooleanNumberAndTextFormValuesExactly",
        "CodexAgentCFormHookValuesTest#projectsEveryHookHandlerVariantExactly",
        "CodexAgentCHookCatalogValuesTest#projectsEveryHookFieldHandlerTrustAndOriginExactly",
        "CodexAgentCHookCatalogValuesTest#projectsOrderedDuplicateCatalogAndFreshChildrenExactly",
        "CodexAgentCIntegrationMcpValuesTest#mcpServerIntegrationConstructorCopiesItsServerDependency",
        "CodexAgentCIntegrationMcpValuesTest#mcpServerIntegrationDisplayNameProjectsTheCanonicalServerDisplayName",
        "CodexAgentCIntegrationMcpValuesTest#mcpServerIntegrationIdProjectsTheCanonicalServerName",
        "CodexAgentCIntegrationMcpValuesTest#mcpServerIntegrationServerReturnsFreshCompleteIndependentlyOwnedSnapshots",
        "CodexAgentCIntegrationStateValuesTest#authorizationStateProjectsStatusTargetAndNullableFailure",
        "CodexAgentCIntegrationValuesTest#connectorIntegrationConnectorReturnsFreshIndependentlyOwnedSnapshots",
        "CodexAgentCIntegrationValuesTest#connectorIntegrationConstructorCopiesItsConnectorDependency",
        "CodexAgentCIntegrationValuesTest#connectorIntegrationDisplayNameProjectsTheCanonicalConnectorName",
        "CodexAgentCIntegrationValuesTest#connectorIntegrationIdProjectsTheCanonicalConnectorId",
        "CodexAgentCInvocationAuthValuesTest#authenticationMethodLeavesValidateSecretsAndOwnDistinctHandles",
        "CodexAgentCInvocationAuthValuesTest#invocationLeavesCopyInputsAndProjectCanonicalKeys",
        "CodexAgentCInvocationAuthValuesTest#pendingApprovalOwnsIndependentConversationIdSnapshots",
        "CodexAgentCListLeafValuesTest#textListCopiesOrderedDuplicateUtf8ValuesAndProjectsEmpty",
        "CodexAgentCListLeafValuesTest#validationCopiesOrderedDuplicateIssuesAndReturnsIndependentChildren",
        "CodexAgentCMcpServerConfigurationValuesTest#d098ConfigurationProjectsEveryPropertyEnumCollectionAndOwnedChild",
        "CodexAgentCMcpServerValuesTest#agentMcpServerAuthStatusAndIsAuthorizedProjectAllFiveCanonicalCases",
        "CodexAgentCMcpServerValuesTest#agentMcpServerConfigurationPreservesNullabilityDeepCopiesAndReturnsFreshOwnedChildren",
        "CodexAgentCMcpServerValuesTest#agentMcpServerConstructorNamesOriginAndCanRemoveUseCanonicalValuesAndCopiedInput",
        "CodexAgentCMcpTransportValuesTest#httpConstructorAndPropertiesPreserveNullableOrderedMaps",
        "CodexAgentCMcpTransportValuesTest#stdioConstructorAndPropertiesPreserveMapListsAndOwnedChildren",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentApprovalDecision",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentAuthenticationStatus",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentCatalogFreshness",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentCollaborationMode",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentElicitationAction",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentFormFieldType",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentFormStringFormat",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentHookRunStatus",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentHookTrustStatus",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentInstallationScope",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentIntegrationAuthorizationStatus",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentMcpAuthStatus",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentMcpAuthentication",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentMcpToolExposureSurface",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentMessageRole",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentPluginAuthPolicy",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentPluginInstallPolicy",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentResolution",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentResourceOrigin",
        "CodexAgentCOrdinaryEnumsTest#validatesAgentWorkActivity",
        "CodexAgentCOrdinaryEnumsTest#validatesCodexAuthorizationPurpose",
        "CodexAgentCProgressListValuesTest#hookActivityProjectsEveryStatusNullableMessageAndCopiedDetails",
        "CodexAgentCProgressListValuesTest#modelCopiesOrderedListsDuplicatesAndNestedServiceTiers",
        "CodexAgentCProgressListValuesTest#planProgressCopiesOrderedDuplicateStepsAndOwnsReturnedChildren",
        "CodexAgentCProgressListValuesTest#turnProgressOwnsNestedProgressHooksAndProjectsNullability",
        "CodexAgentCResourceListValuesTest#connectorCopiesOrderedDuplicateNamesAndProjectsEveryProperty",
        "CodexAgentCResourceListValuesTest#pluginDetailAndInstallResultOwnOrderedNestedValues",
        "CodexAgentCResourceListValuesTest#pluginSummaryAndCatalogOwnNestedValuesAndProjectEveryField",
        "CodexAgentCResourceListValuesTest#skillAndCatalogPreserveDefaultsListsAndIndependentChildren",
        "CodexAgentCResourceValuesTest#capabilityAndSkillScopeEntriesProjectCanonicalLabels",
        "CodexAgentCResourceValuesTest#pluginReferenceProjectsEveryPropertyAndNullableState",
        "CodexAgentCResourceValuesTest#pluginSkillServiceTierAndSkillChunkProjectExactValues",
        "CodexAgentCRootValueAccessorsTest#hostSubtypePayloadsAreExactFreshAndFailClosed",
        "CodexAgentCRootValueAccessorsTest#pendingForPreservesOrderDuplicatesOwnershipAndErrors",
        "CodexAgentCSealedBasePropertyValuesTest#integrationBasePropertiesProjectBothConcreteVariants",
        "CodexAgentCSealedBasePropertyValuesTest#invocationBasePropertiesProjectBothConcreteVariants",
        "CodexAgentCSealedBasePropertyValuesTest#pendingInteractionBasePropertiesProjectBothVariantsAndFreshConversationIds",
        "CodexAgentCServiceHandlesTest#agentFacadesAreIdentityStableExactAndFailClosed",
        "CodexAgentCServiceHandlesTest#agentWorkspaceIsAnOwnedSnapshotAndFailsClosed",
        "CodexAgentCServiceHandlesTest#availabilityReflectsEveryRuntimeFeatureAndPreservesFailureSentinels",
        "CodexAgentCValueProjectionTest#projectsEveryConversationStatusAndFailureExactly",
        "CodexAgentCValueProjectionTest#projectsMissingHostStateVariantsAndPayloadsExactly",
    ).map(::cAbiNativeTestId)
    val lifecycle = cAbiNativeTestId("CodexAgentCLifecycleTest#projectsCanonicalLifecycleAndQuiescesEveryCallback")
    val hostFactory = cAbiNativeTestId("CodexAgentCHostFactoryTest#createsCopiedCanonicalHostWithOwnedRetainedAndClosedAliases")
    val isResolving = cAbiNativeTestId(
        "CodexAgentCInteractionOperationsTest#interactionStateIsResolvingRequiresExactLivePendingIdentity",
    )
    val openUrl = asyncSuccess[0]
    val interactionOperations = asyncSuccess.take(3)
    val interactionFlows = stateFlows.takeLast(3)
    val serviceFacades = values.single { it.contains("#agentFacadesAreIdentityStableExactAndFailClosed[") }
    val agentWorkspace = values.single { it.contains("#agentWorkspaceIsAnOwnedSnapshotAndFailsClosed[") }
    val failures = values.single { it.contains("#createsAndValidatesFailures[") }
    fun value(method: String) = values.single { it.contains("#$method[") }
    val nullability = listOf(
        value("authenticationStateAndConversationSettingsProjectDefaultsNullabilityAndEveryEnum"),
        value("mcpOauthConfigurationPreservesNullableValuesAndPortBoundaries"),
        value("projectsAgentConversationStateTruthTableAndNullableValuesExactly"),
        stateFlows.single { it.contains("#integrationAuthorizationActiveGetAndSubscribeProjectNullConnectorMcpNull[") },
        value("agentMcpServerConfigurationPreservesNullabilityDeepCopiesAndReturnsFreshOwnedChildren"),
        value("httpConstructorAndPropertiesPreserveNullableOrderedMaps"),
        value("pluginReferenceProjectsEveryPropertyAndNullableState"),
        asyncSuccess.single { it.contains("#modelsResolveServiceTierDistinguishesPresentAndAbsent[") },
    )
    val collections = listOf(
        value("projectsAgentConversationAndMessagesWithExactOrderedSnapshots"),
        stateFlows.single { it.contains("#currentMessagesGetterSubscriptionAndProjectorsPreserveOrderedOwnedTransitions[") },
        value("elicitationAndResponseProjectEveryFieldAndOwnedCollection"),
        value("projectsOrderedDuplicateCatalogAndFreshChildrenExactly"),
        value("textListCopiesOrderedDuplicateUtf8ValuesAndProjectsEmpty"),
        value("validationCopiesOrderedDuplicateIssuesAndReturnsIndependentChildren"),
        value("httpConstructorAndPropertiesPreserveNullableOrderedMaps"),
        value("stdioConstructorAndPropertiesPreserveMapListsAndOwnedChildren"),
        value("modelCopiesOrderedListsDuplicatesAndNestedServiceTiers"),
        value("planProgressCopiesOrderedDuplicateStepsAndOwnsReturnedChildren"),
        value("connectorCopiesOrderedDuplicateNamesAndProjectsEveryProperty"),
        value("pluginDetailAndInstallResultOwnOrderedNestedValues"),
        value("pluginSummaryAndCatalogOwnNestedValuesAndProjectEveryField"),
        value("skillAndCatalogPreserveDefaultsListsAndIndependentChildren"),
        value("pendingForPreservesOrderDuplicatesOwnershipAndErrors"),
        asyncSuccess.single { it.contains("#connectorsListPreservesOrderAndDuplicates[") },
        asyncSuccess.single { it.contains("#modelsListReturnsFreshOrderedDuplicates[") },
        asyncSuccess.single { it.contains("#catalogOperationsPreserveOrderDuplicatesOwnedResultsAndCopiedInputs[") },
    )
    val mappings = listOf(
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.ASYNC_SUCCESS, asyncSuccess),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.ASYNC_FAILURE, listOf(openUrl)),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.CANCELLATION, interactionOperations),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.STATE_CURRENT_VALUE, stateFlows),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.STATE_SUBSEQUENT_VALUE, stateFlows),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.SUBSCRIPTION_CANCELLATION, listOf(lifecycle)),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.TERMINAL_DELIVERY, stateFlows + lifecycle),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.STRUCTURED_FAILURE, listOf(openUrl, failures)),
        CrossLanguageCAbiScenarioMapping(
            CrossLanguageBindingScenario.IDENTITY,
            listOf(isResolving) + interactionOperations + serviceFacades + interactionFlows,
        ),
        CrossLanguageCAbiScenarioMapping(
            CrossLanguageBindingScenario.PARENT_CHILD_OWNERSHIP,
            stateFlows + listOf(lifecycle, hostFactory, serviceFacades, agentWorkspace),
        ),
        CrossLanguageCAbiScenarioMapping(
            CrossLanguageBindingScenario.REPEATED_CLOSE_DISPOSE,
            listOf(lifecycle, hostFactory),
        ),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.NULLABILITY, nullability),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.COLLECTION_IMMUTABILITY_ORDERING, collections),
        CrossLanguageCAbiScenarioMapping(CrossLanguageBindingScenario.VALUE_CONVERSION, values),
    )
    val selected = mappings.flatMap(CrossLanguageCAbiScenarioMapping::testIds).distinct().sorted()
    val rows = mappings.flatMap { mapping -> mapping.testIds.map { mapping.scenario.id to it } }
    val selectedSha256 = selected.joinToString(separator = "", transform = { it + "\n" })
        .byteInputStream().releaseDigest()
    val mappingSha256 = rows.sortedWith(compareBy<Pair<String, String>> { it.first }.thenBy { it.second })
        .joinToString(separator = "", transform = { it.first + "\t" + it.second + "\n" })
        .byteInputStream().releaseDigest()
    check(stateFlows.size == 16 && asyncSuccess.size == 31 && values.size == 88 &&
        nullability.size == 8 && collections.size == 18 &&
        selected.size == C_ABI_SCENARIO_SELECTED_TEST_COUNT &&
        rows.size == C_ABI_SCENARIO_MAPPING_ROW_COUNT &&
        selectedSha256 == C_ABI_SCENARIO_SELECTED_TEST_SHA256 &&
        mappingSha256 == C_ABI_SCENARIO_MAPPING_SHA256) {
            "C ABI production scenario map drift: states=${stateFlows.size} async=${asyncSuccess.size} " +
            "values=${values.size} nullability=${nullability.size} collections=${collections.size} " +
            "selected=${selected.size}/$selectedSha256 rows=${rows.size}/$mappingSha256"
    }
    return mappings
}

private fun cAbiNativeTestId(classAndMethod: String): String =
    "macosArm64Test.io.github.codex_agent_labs.codexagent.capi." + classAndMethod + "[macosArm64]"

/**
 * Frozen expectations are explicit so compact unit fixtures do not weaken production callers.
 * The artifact identities are verified by the calling aggregate before this pure adapter runs.
 */
internal data class CrossLanguageCAbiBindingEvidenceInput(
    val bootstrapEvidence: File,
    val scenarioMappings: List<CrossLanguageCAbiScenarioMapping>,
    val artifactIdentities: List<CrossLanguageBindingArtifactIdentity>,
    val testProgramSha256: String,
    val testResultsSha256: String,
    val expectedCapabilityCount: Int = C_ABI_BINDING_CAPABILITY_COUNT,
    val expectedPublicSymbolCount: Int = C_ABI_BINDING_PUBLIC_SYMBOL_COUNT,
    val expectedCapabilitySha256: String = C_ABI_BINDING_CAPABILITY_SHA256,
)

internal fun deriveCrossLanguageCAbiBindingReceipt(
    input: CrossLanguageCAbiBindingEvidenceInput,
): CrossLanguageBindingReceipt {
    check(input.expectedCapabilityCount > 0) { "Expected C ABI capability count must be positive" }
    check(input.expectedPublicSymbolCount > 0) { "Expected C ABI public-symbol count must be positive" }
    requireCAbiSha256(input.expectedCapabilitySha256, "expected capability inventory")
    requireCAbiSha256(input.testProgramSha256, "C ABI test program")
    requireCAbiSha256(input.testResultsSha256, "C ABI test results")

    val bootstrap = readCAbiBootstrapEvidence(input.bootstrapEvidence)
    check(bootstrap.capabilityCount == input.expectedCapabilityCount &&
        bootstrap.observedCapabilityCount == input.expectedCapabilityCount &&
        bootstrap.claims.size == input.expectedCapabilityCount) {
        "C ABI bootstrap capability counts are inconsistent with the frozen expectation"
    }
    check(bootstrap.missingCapabilityKeys.isEmpty()) {
        "C ABI bootstrap has residual capabilities: ${bootstrap.missingCapabilityKeys}"
    }
    val capabilityKeys = bootstrap.observedCapabilityKeys
    check(capabilityKeys == capabilityKeys.distinct().sorted()) {
        "C ABI bootstrap observed capability inventory is not exact, unique, and sorted"
    }
    val actualCapabilitySha256 = crossLanguageCAbiCapabilitySha256(capabilityKeys)
    check(bootstrap.observedCapabilitySha256 == actualCapabilitySha256 &&
        actualCapabilitySha256 == input.expectedCapabilitySha256) {
        "C ABI bootstrap capability inventory digest is inconsistent"
    }
    check(bootstrap.claims.map(CAbiBindingBootstrapClaim::capabilityKey) == capabilityKeys) {
        "C ABI bootstrap claims do not exactly match the observed capability inventory"
    }

    val publicSymbols = bootstrap.linkedPublicSymbols
    check(publicSymbols.size == input.expectedPublicSymbolCount &&
        publicSymbols == publicSymbols.distinct().sorted()) {
        "C ABI bootstrap public-symbol inventory is inconsistent with the frozen expectation"
    }
    publicSymbols.forEach { requireCAbiExactRecord(it, "C ABI linked public symbol") }
    val publicSymbolSet = publicSymbols.toSet()

    val passedTests = bootstrap.nativeTests.associate { test -> test.testId to test.status }
    check(passedTests.size == bootstrap.nativeTests.size && bootstrap.nativeTests.all {
        it.status == CrossLanguageBindingTestStatus.PASSED
    }) { "C ABI bootstrap native-test inventory is duplicated or not entirely passed" }
    check(bootstrap.nativeTests.map(CAbiBindingBootstrapTest::testId) == passedTests.keys.sorted()) {
        "C ABI bootstrap native-test inventory is not sorted"
    }

    bootstrap.claims.forEach { claim ->
        requireCAbiExactRecord(claim.capabilityKey, "C ABI bootstrap claim capability")
        requireCAbiExactInventory(claim.headerReferences, "header references for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.consumerReferences, "consumer references for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.publicSymbols, "public symbols for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.nativeTestIds, "native tests for ${claim.capabilityKey}")
        check(claim.publicSymbols.all(publicSymbolSet::contains)) {
            "C ABI bootstrap claim ${claim.capabilityKey} references a stale public symbol"
        }
        check(claim.publicSymbols.all(claim.headerReferences.toSet()::contains) &&
            claim.publicSymbols.all(claim.consumerReferences.toSet()::contains)) {
            "C ABI bootstrap claim ${claim.capabilityKey} lacks an exact header or consumer reference"
        }
        check(claim.nativeTestIds.all { passedTests[it] == CrossLanguageBindingTestStatus.PASSED }) {
            "C ABI bootstrap claim ${claim.capabilityKey} references a missing or non-passed test"
        }
    }

    requireCAbiArtifactIdentities(input)
    val scenarioEvidence = requireCAbiScenarioMappings(input.scenarioMappings, bootstrap)
    val scenarioTests = scenarioEvidence.associate { it.scenario to it.testIds.toSet() }
    val projectionClaims = bootstrap.claims.map { claim ->
        val executedTests = claim.nativeTestIds.toSet()
        val scenarios = CrossLanguageBindingScenario.entries.filter { scenario ->
            scenarioTests.getValue(scenario).any(executedTests::contains)
        }
        check(scenarios.isNotEmpty()) {
            "C ABI bootstrap claim ${claim.capabilityKey} has no directly mapped scenario"
        }
        CrossLanguageProjectionClaim(
            capabilityKey = claim.capabilityKey,
            language = CrossLanguageBinding.C_ABI,
            publicSymbols = claim.publicSymbols,
            executedTests = claim.nativeTestIds,
            sharedScenarios = scenarios,
        )
    }

    return CrossLanguageBindingReceipt(
        phase = CrossLanguageBindingPhase.M8,
        language = CrossLanguageBinding.C_ABI,
        canonical = CrossLanguageBindingCanonicalIdentity(
            apiReportSha256 = bootstrap.apiReportSha256,
            coverageReceiptSha256 = bootstrap.coverageReceiptSha256,
        ),
        artifacts = input.artifactIdentities,
        testProgramSha256 = input.testProgramSha256,
        testResultsSha256 = input.testResultsSha256,
        publicSymbols = publicSymbols,
        bindingTests = bootstrap.nativeTests.map { test ->
            CrossLanguageBindingTestEvidence(CrossLanguageBinding.C_ABI, test.testId, test.status)
        },
        scenarioEvidence = scenarioEvidence,
        projectionClaims = projectionClaims,
        applicabilityExclusions = emptyList(),
    )
}

internal fun writeCrossLanguageCAbiBindingReceipt(
    output: File,
    input: CrossLanguageCAbiBindingEvidenceInput,
): CrossLanguageBindingReceipt {
    val expected = deriveCrossLanguageCAbiBindingReceipt(input)
    writeCrossLanguageBindingReceipt(output, expected)
    return readCrossLanguageBindingReceipt(output).also { actual ->
        check(actual == expected.cAbiNormalizedForComparison()) {
            "C ABI cross-language binding receipt did not round-trip exactly"
        }
    }
}

internal fun writeCrossLanguageCAbiScenarioProof(
    output: File,
    bootstrapEvidence: File,
    mappings: List<CrossLanguageCAbiScenarioMapping>,
    expectedCapabilityCount: Int = C_ABI_BINDING_CAPABILITY_COUNT,
    expectedPublicSymbolCount: Int = C_ABI_BINDING_PUBLIC_SYMBOL_COUNT,
    expectedCapabilitySha256: String = C_ABI_BINDING_CAPABILITY_SHA256,
): CrossLanguageCAbiScenarioProof {
    val bootstrap = requireCAbiScenarioProofBootstrap(
        bootstrapEvidence,
        mappings,
        expectedCapabilityCount,
        expectedPublicSymbolCount,
        expectedCapabilitySha256,
    )
    output.atomicWriteJson(cAbiScenarioProofJson(bootstrapEvidence, bootstrap, mappings))
    return readCrossLanguageCAbiScenarioProof(
        output,
        bootstrapEvidence,
        expectedCapabilityCount,
        expectedPublicSymbolCount,
        expectedCapabilitySha256,
    )
}

internal fun readCrossLanguageCAbiScenarioProof(
    proofFile: File,
    bootstrapEvidence: File,
    expectedCapabilityCount: Int = C_ABI_BINDING_CAPABILITY_COUNT,
    expectedPublicSymbolCount: Int = C_ABI_BINDING_PUBLIC_SYMBOL_COUNT,
    expectedCapabilitySha256: String = C_ABI_BINDING_CAPABILITY_SHA256,
): CrossLanguageCAbiScenarioProof {
    check(proofFile.isFile && !Files.isSymbolicLink(proofFile.toPath())) {
        "C ABI scenario proof is missing, non-regular, or a symlink: $proofFile"
    }
    val contents = proofFile.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("C ABI scenario proof must be a JSON object")
    root.cAbiRequireKeys(
        "C ABI scenario proof",
        "schemaVersion", "artifactId", "result", "bootstrapSha256", "capabilitySha256",
        "nativeTestSourcesSha256", "nativeTestResultsSha256", "scenarios",
    )
    check(root.cAbiExactInt("schemaVersion") == C_ABI_SCENARIO_PROOF_SCHEMA &&
        root.cAbiExactString("artifactId") == C_ABI_SCENARIO_PROOF_ARTIFACT_ID &&
        root.cAbiExactString("result") == "passed") {
        "C ABI scenario proof identity is not exact schema-1 passed c-abi-scenarios evidence"
    }
    val mappings = root.cAbiExactArray("scenarios").map { value ->
        val row = value.cAbiExactObject("C ABI scenario proof row").also {
            it.cAbiRequireKeys("C ABI scenario proof row", "id", "testIds")
        }
        val id = row.cAbiExactString("id")
        val scenario = CrossLanguageBindingScenario.entries.singleOrNull { it.id == id }
            ?: error("Unknown C ABI scenario proof id: $id")
        CrossLanguageCAbiScenarioMapping(scenario, row.cAbiExactStrings("testIds"))
    }
    check(mappings.map { it.scenario.id } == mappings.map { it.scenario.id }.sorted() &&
        mappings.all { it.testIds == it.testIds.sorted() }) {
        "C ABI scenario proof rows and test IDs must be exactly sorted"
    }
    val bootstrap = requireCAbiScenarioProofBootstrap(
        bootstrapEvidence,
        mappings,
        expectedCapabilityCount,
        expectedPublicSymbolCount,
        expectedCapabilitySha256,
    )
    requireCAbiSha256(root.cAbiExactString("bootstrapSha256"), "C ABI scenario bootstrap")
    requireCAbiSha256(root.cAbiExactString("capabilitySha256"), "C ABI scenario capability")
    requireCAbiSha256(root.cAbiExactString("nativeTestSourcesSha256"), "C ABI scenario test program")
    requireCAbiSha256(root.cAbiExactString("nativeTestResultsSha256"), "C ABI scenario test results")
    val expected = cAbiScenarioProofJson(bootstrapEvidence, bootstrap, mappings)
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), expected) + "\n") {
        "C ABI scenario proof is stale or not canonically encoded"
    }
    return CrossLanguageCAbiScenarioProof(
        mappings = mappings,
        testProgramSha256 = bootstrap.nativeTestSourcesSha256,
        testResultsSha256 = bootstrap.nativeTestResultsSha256,
    )
}

internal fun crossLanguageCAbiCapabilitySha256(capabilityKeys: List<String>): String =
    capabilityKeys.sorted().joinToString(separator = "", transform = { "$it\n" })
        .byteInputStream().releaseDigest()

internal data class CAbiBindingBootstrapClaim(
    val capabilityKey: String,
    val headerReferences: List<String>,
    val consumerReferences: List<String>,
    val publicSymbols: List<String>,
    val nativeTestIds: List<String>,
)

internal data class CAbiBindingBootstrapTest(
    val testId: String,
    val status: CrossLanguageBindingTestStatus,
)

internal data class CAbiBindingBootstrapEvidence(
    val apiReportSha256: String,
    val coverageReceiptSha256: String,
    val capabilityCount: Int,
    val observedCapabilityCount: Int,
    val observedCapabilitySha256: String,
    val observedCapabilityKeys: List<String>,
    val missingCapabilityKeys: List<String>,
    val nativeTestSourcesSha256: String,
    val nativeTestResultsSha256: String,
    val linkedPublicSymbols: List<String>,
    val nativeTests: List<CAbiBindingBootstrapTest>,
    val claims: List<CAbiBindingBootstrapClaim>,
)

internal fun readCAbiBootstrapEvidence(file: File): CAbiBindingBootstrapEvidence {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "C ABI bootstrap evidence is missing, non-regular, or a symlink: $file"
    }
    val contents = file.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("C ABI bootstrap evidence must be a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "C ABI bootstrap evidence is not canonically encoded"
    }
    root.cAbiRequireKeys(
        "C ABI bootstrap evidence",
        "schemaVersion", "protocol", "result", "milestone", "language", "canonical", "toolchain",
        "artifacts", "compilerConsumers", "linkedPublicSymbols", "nativeTests", "claims",
    )
    check(root.cAbiExactInt("schemaVersion") == C_ABI_BOOTSTRAP_SCHEMA) {
        "Unsupported C ABI bootstrap evidence schema"
    }
    check(root.cAbiExactString("protocol") == C_ABI_BOOTSTRAP_PROTOCOL) {
        "Unsupported C ABI bootstrap evidence protocol"
    }
    check(root.cAbiExactString("result") == "observed" &&
        root.cAbiExactString("milestone") == "D104" &&
        root.cAbiExactString("language") == "c-abi") {
        "C ABI bootstrap evidence identity is not exact D104 observed c-abi evidence"
    }

    val canonical = root.cAbiExactObject("canonical").also {
        it.cAbiRequireKeys(
            "C ABI bootstrap canonical identity",
            "apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "capabilityCount",
            "observedCapabilityCount", "observedCapabilitySha256", "observedCapabilityKeys",
            "missingCapabilityKeys",
        )
    }
    listOf("apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "observedCapabilitySha256")
        .forEach { name -> requireCAbiSha256(canonical.cAbiExactString(name), "C ABI bootstrap $name") }

    root.cAbiExactObject("toolchain").also { toolchain ->
        toolchain.cAbiRequireKeys("C ABI bootstrap toolchain", "clang", "clangCpp", "clangVersion", "macosSdk")
        listOf("clang", "clangCpp", "macosSdk").forEach { name ->
            requireCAbiExactRecord(toolchain.cAbiExactString(name), "toolchain $name")
        }
        requireCAbiExactMultilineRecord(toolchain.cAbiExactString("clangVersion"), "toolchain clangVersion")
    }
    val artifacts = root.cAbiExactObject("artifacts").also { artifacts ->
        artifacts.cAbiRequireKeys(
            "C ABI bootstrap artifacts",
            "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
            "generatedHeaderSha256", "releaseLibrarySha256", "nativeTestExecutableSha256",
            "nativeMainSourcesSha256", "nativeTestSourcesSha256", "nativeTestResultsSha256",
            "fileIdentity", "installName",
        )
        artifacts.keys.filter { it.endsWith("Sha256") }.forEach { name ->
            requireCAbiSha256(artifacts.cAbiExactString(name), "C ABI bootstrap artifact $name")
        }
        listOf("fileIdentity", "installName").forEach { name ->
            requireCAbiExactRecord(artifacts.cAbiExactString(name), "C ABI bootstrap artifact $name")
        }
    }

    val consumerIds = root.cAbiExactArray("compilerConsumers").map { value ->
        val consumer = value.cAbiExactObject("C ABI compiler consumer").also {
            it.cAbiRequireKeys(
                "C ABI compiler consumer", "id", "sourceSha256", "artifactSha256", "executed",
            )
        }
        val id = consumer.cAbiExactString("id").also {
            requireCAbiExactRecord(it, "C ABI compiler consumer")
        }
        requireCAbiSha256(consumer.cAbiExactString("sourceSha256"), "C ABI compiler consumer source")
        requireCAbiSha256(consumer.cAbiExactString("artifactSha256"), "C ABI compiler consumer artifact")
        consumer.cAbiExactBoolean("executed")
        id
    }
    check(consumerIds.isNotEmpty() && consumerIds.size == consumerIds.distinct().size) {
        "C ABI bootstrap compiler-consumer inventory is empty or duplicated"
    }

    val nativeTests = root.cAbiExactArray("nativeTests").map { value ->
        val test = value.cAbiExactObject("C ABI native test").also {
            it.cAbiRequireKeys("C ABI native test", "testId", "status")
        }
        val testId = test.cAbiExactString("testId").also {
            requireCAbiExactRecord(it, "C ABI native test")
        }
        val status = when (test.cAbiExactString("status")) {
            "passed" -> CrossLanguageBindingTestStatus.PASSED
            "failed" -> CrossLanguageBindingTestStatus.FAILED
            "skipped" -> CrossLanguageBindingTestStatus.SKIPPED
            else -> error("Unknown C ABI bootstrap native-test status")
        }
        CAbiBindingBootstrapTest(testId, status)
    }
    val claims = root.cAbiExactArray("claims").map { value ->
        val claim = value.cAbiExactObject("C ABI bootstrap claim").also {
            it.cAbiRequireKeys(
                "C ABI bootstrap claim", "capabilityKey", "headerReferences", "consumerReferences",
                "publicSymbols", "nativeTestIds",
            )
        }
        CAbiBindingBootstrapClaim(
            capabilityKey = claim.cAbiExactString("capabilityKey"),
            headerReferences = claim.cAbiExactStrings("headerReferences"),
            consumerReferences = claim.cAbiExactStrings("consumerReferences"),
            publicSymbols = claim.cAbiExactStrings("publicSymbols"),
            nativeTestIds = claim.cAbiExactStrings("nativeTestIds"),
        )
    }
    return CAbiBindingBootstrapEvidence(
        apiReportSha256 = canonical.cAbiExactString("apiReportSha256"),
        coverageReceiptSha256 = canonical.cAbiExactString("coverageReceiptSha256"),
        capabilityCount = canonical.cAbiExactInt("capabilityCount"),
        observedCapabilityCount = canonical.cAbiExactInt("observedCapabilityCount"),
        observedCapabilitySha256 = canonical.cAbiExactString("observedCapabilitySha256"),
        observedCapabilityKeys = canonical.cAbiExactStrings("observedCapabilityKeys"),
        missingCapabilityKeys = canonical.cAbiExactStrings("missingCapabilityKeys"),
        nativeTestSourcesSha256 = artifacts.cAbiExactString("nativeTestSourcesSha256"),
        nativeTestResultsSha256 = artifacts.cAbiExactString("nativeTestResultsSha256"),
        linkedPublicSymbols = root.cAbiExactStrings("linkedPublicSymbols"),
        nativeTests = nativeTests,
        claims = claims,
    )
}

private fun requireCAbiScenarioProofBootstrap(
    bootstrapEvidence: File,
    mappings: List<CrossLanguageCAbiScenarioMapping>,
    expectedCapabilityCount: Int,
    expectedPublicSymbolCount: Int,
    expectedCapabilitySha256: String,
): CAbiBindingBootstrapEvidence {
    val bootstrap = readCAbiBootstrapEvidence(bootstrapEvidence)
    check(expectedCapabilityCount > 0 && expectedPublicSymbolCount > 0) {
        "C ABI scenario proof expectations must be positive"
    }
    requireCAbiSha256(expectedCapabilitySha256, "expected C ABI scenario capability inventory")
    check(bootstrap.capabilityCount == expectedCapabilityCount &&
        bootstrap.observedCapabilityCount == expectedCapabilityCount &&
        bootstrap.claims.size == expectedCapabilityCount &&
        bootstrap.missingCapabilityKeys.isEmpty()) {
        "C ABI scenario proof requires the exact closed capability inventory"
    }
    val capabilityKeys = bootstrap.observedCapabilityKeys
    check(capabilityKeys == capabilityKeys.distinct().sorted() &&
        bootstrap.claims.map(CAbiBindingBootstrapClaim::capabilityKey) == capabilityKeys &&
        crossLanguageCAbiCapabilitySha256(capabilityKeys) == expectedCapabilitySha256 &&
        bootstrap.observedCapabilitySha256 == expectedCapabilitySha256) {
        "C ABI scenario proof capability inventory is stale or inconsistent"
    }
    val publicSymbols = bootstrap.linkedPublicSymbols
    check(publicSymbols.size == expectedPublicSymbolCount &&
        publicSymbols == publicSymbols.distinct().sorted()) {
        "C ABI scenario proof public-symbol inventory is stale or inconsistent"
    }
    publicSymbols.forEach { requireCAbiExactRecord(it, "C ABI linked public symbol") }
    val publicSymbolSet = publicSymbols.toSet()
    val passedTests = bootstrap.nativeTests.associate { it.testId to it.status }
    check(passedTests.size == bootstrap.nativeTests.size &&
        bootstrap.nativeTests.all { it.status == CrossLanguageBindingTestStatus.PASSED } &&
        bootstrap.nativeTests.map(CAbiBindingBootstrapTest::testId) == passedTests.keys.sorted()) {
        "C ABI scenario proof native-test inventory is duplicated, unsorted, or not passed"
    }
    bootstrap.claims.forEach { claim ->
        requireCAbiExactRecord(claim.capabilityKey, "C ABI bootstrap claim capability")
        requireCAbiExactInventory(claim.headerReferences, "header references for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.consumerReferences, "consumer references for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.publicSymbols, "public symbols for ${claim.capabilityKey}")
        requireCAbiExactInventory(claim.nativeTestIds, "native tests for ${claim.capabilityKey}")
        check(claim.publicSymbols.all(publicSymbolSet::contains) &&
            claim.publicSymbols.all(claim.headerReferences.toSet()::contains) &&
            claim.publicSymbols.all(claim.consumerReferences.toSet()::contains) &&
            claim.nativeTestIds.all { passedTests[it] == CrossLanguageBindingTestStatus.PASSED }) {
            "C ABI scenario proof claim is stale or incomplete: ${claim.capabilityKey}"
        }
    }
    val scenarioEvidence = requireCAbiScenarioMappings(mappings, bootstrap)
    val scenarioTests = scenarioEvidence.associate { it.scenario to it.testIds.toSet() }
    bootstrap.claims.forEach { claim ->
        check(scenarioTests.values.any { tests -> tests.any(claim.nativeTestIds.toSet()::contains) }) {
            "C ABI scenario proof claim ${claim.capabilityKey} has no directly mapped scenario"
        }
    }
    return bootstrap
}

private fun cAbiScenarioProofJson(
    bootstrapEvidence: File,
    bootstrap: CAbiBindingBootstrapEvidence,
    mappings: List<CrossLanguageCAbiScenarioMapping>,
): JsonObject = buildJsonObject {
    put("schemaVersion", JsonPrimitive(C_ABI_SCENARIO_PROOF_SCHEMA))
    put("artifactId", JsonPrimitive(C_ABI_SCENARIO_PROOF_ARTIFACT_ID))
    put("result", JsonPrimitive("passed"))
    put("bootstrapSha256", JsonPrimitive(bootstrapEvidence.releaseDigest()))
    put("capabilitySha256", JsonPrimitive(bootstrap.observedCapabilitySha256))
    put("nativeTestSourcesSha256", JsonPrimitive(bootstrap.nativeTestSourcesSha256))
    put("nativeTestResultsSha256", JsonPrimitive(bootstrap.nativeTestResultsSha256))
    put("scenarios", buildJsonArray {
        mappings.sortedBy { it.scenario.id }.forEach { mapping ->
            add(buildJsonObject {
                put("id", JsonPrimitive(mapping.scenario.id))
                put("testIds", buildJsonArray {
                    mapping.testIds.sorted().forEach { add(JsonPrimitive(it)) }
                })
            })
        }
    })
}

private fun requireCAbiArtifactIdentities(input: CrossLanguageCAbiBindingEvidenceInput) {
    val ids = input.artifactIdentities.map(CrossLanguageBindingArtifactIdentity::id)
    check(input.artifactIdentities.size == C_ABI_BINDING_ARTIFACT_COUNT &&
        ids.toSet() == C_ABI_BINDING_ARTIFACT_IDS) {
        "C ABI binding artifact inventory does not match the frozen expectation"
    }
    check(ids.size == ids.distinct().size) { "C ABI binding artifact identities are duplicated" }
    input.artifactIdentities.forEach { artifact ->
        requireCAbiExactRecord(artifact.id, "C ABI binding artifact identity")
        requireCAbiSha256(artifact.sha256, "C ABI binding artifact ${artifact.id}")
    }
}

private fun requireCAbiScenarioMappings(
    mappings: List<CrossLanguageCAbiScenarioMapping>,
    bootstrap: CAbiBindingBootstrapEvidence,
): List<CrossLanguageScenarioEvidence> {
    val grouped = mappings.groupBy(CrossLanguageCAbiScenarioMapping::scenario)
    check(grouped.keys == CrossLanguageBindingScenario.entries.toSet() &&
        grouped.values.all { it.size == 1 }) {
        "C ABI scenario mapping must contain exactly one row for each of the 14 shared scenarios"
    }
    val passedTests = bootstrap.nativeTests.filter { it.status == CrossLanguageBindingTestStatus.PASSED }
        .mapTo(mutableSetOf(), CAbiBindingBootstrapTest::testId)
    val claimTests = bootstrap.claims.flatMapTo(mutableSetOf(), CAbiBindingBootstrapClaim::nativeTestIds)
    return CrossLanguageBindingScenario.entries.map { scenario ->
        val testIds = grouped.getValue(scenario).single().testIds
        check(testIds.isNotEmpty() && testIds.size == testIds.distinct().size) {
            "C ABI scenario ${scenario.id} has missing or duplicate test IDs"
        }
        testIds.forEach { testId ->
            requireCAbiExactRecord(testId, "C ABI scenario ${scenario.id} test")
            check(testId in passedTests) {
                "C ABI scenario ${scenario.id} references a missing or non-passed test: $testId"
            }
            check(testId in claimTests) {
                "C ABI scenario ${scenario.id} references a family-level test not owned by a claim: $testId"
            }
        }
        CrossLanguageScenarioEvidence(CrossLanguageBinding.C_ABI, scenario, testIds.sorted())
    }
}

private fun CrossLanguageBindingReceipt.cAbiNormalizedForComparison(): CrossLanguageBindingReceipt = copy(
    artifacts = artifacts.sortedBy(CrossLanguageBindingArtifactIdentity::id),
    publicSymbols = publicSymbols.sorted(),
    bindingTests = bindingTests.sortedBy(CrossLanguageBindingTestEvidence::testId),
    scenarioEvidence = scenarioEvidence.map { it.copy(testIds = it.testIds.sorted()) }.sortedBy { it.scenario.id },
    projectionClaims = projectionClaims.map { claim ->
        claim.copy(
            publicSymbols = claim.publicSymbols.sorted(),
            executedTests = claim.executedTests.sorted(),
            sharedScenarios = claim.sharedScenarios.sortedBy(CrossLanguageBindingScenario::id),
        )
    }.sortedBy(CrossLanguageProjectionClaim::capabilityKey),
)

private fun requireCAbiExactInventory(values: List<String>, label: String) {
    check(values.isNotEmpty() && values.size == values.distinct().size) { "$label is empty or duplicated" }
    values.forEach { requireCAbiExactRecord(it, label) }
}

private fun requireCAbiExactRecord(value: String, label: String) {
    check(value.isNotBlank() && value == value.trim() && '*' !in value && value.none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $value"
    }
}

private fun requireCAbiExactMultilineRecord(value: String, label: String) {
    check(value.isNotBlank() && value == value.trim() && '*' !in value &&
        value.none { it != '\n' && it.isISOControl() } &&
        value.lineSequence().all { it.isNotBlank() && it == it.trim() }) {
        "$label is blank, untrimmed, wildcarded, or contains an invalid control: $value"
    }
}

private fun requireCAbiSha256(value: String, label: String) {
    check(value.length == 64 && value.all { it in '0'..'9' || it in 'a'..'f' }) {
        "$label SHA-256 is not exact"
    }
}

private fun JsonObject.cAbiRequireKeys(label: String, vararg expected: String) {
    check(keys == expected.toSet()) {
        "Invalid $label keys: expected=${expected.sorted()} actual=${keys.sorted()}"
    }
}

private fun JsonObject.cAbiExactString(name: String): String {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON string: $name")
    check(primitive.isString) { "JSON field $name must be a string" }
    return primitive.contentOrNull ?: error("Missing JSON string: $name")
}

private fun JsonObject.cAbiExactInt(name: String): Int {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON integer: $name")
    check(!primitive.isString) { "JSON field $name must be an integer" }
    return primitive.intOrNull ?: error("Missing JSON integer: $name")
}

private fun JsonObject.cAbiExactBoolean(name: String): Boolean {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON boolean: $name")
    check(!primitive.isString) { "JSON field $name must be a boolean" }
    return primitive.booleanOrNull ?: error("Missing JSON boolean: $name")
}

private fun JsonObject.cAbiExactArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing JSON array: $name")

private fun JsonObject.cAbiExactObject(name: String): JsonObject = this[name] as? JsonObject
    ?: error("Missing JSON object: $name")

private fun JsonElement.cAbiExactObject(label: String): JsonObject = this as? JsonObject
    ?: error("$label must be a JSON object")

private fun JsonObject.cAbiExactStrings(name: String): List<String> = cAbiExactArray(name).map { value ->
    val primitive = value as? JsonPrimitive ?: error("$name must contain only strings")
    check(primitive.isString) { "$name must contain only strings" }
    primitive.content
}
