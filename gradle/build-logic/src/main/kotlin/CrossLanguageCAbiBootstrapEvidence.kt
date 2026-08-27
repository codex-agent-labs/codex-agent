import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.LocalState
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal const val C_ABI_BOOTSTRAP_EVIDENCE_PROTOCOL = "codex-agent-c-abi-bootstrap-evidence-v1"
internal const val C_ABI_BOOTSTRAP_CAPABILITY_COUNT = 312
internal const val C_ABI_BOOTSTRAP_CAPABILITY_SHA256 =
    "4655731b655b5d27cafede8d596bbefb83509fad0e4806bc78484cc7c8c78beb"

private const val C_ABI_CANONICAL_CAPABILITY_COUNT = 556
private const val C_ABI_HEADER_SHA256 =
    "899e1410d052f87aa79c6e36812c6d72693092274fbb1072e9c842fb39acd16c"
private const val C_ABI_CINTEROP_SHA256 =
    "4a132bc83e0f69251cc9f432bb7530b4eaafe2f4d7ea1c2985ed860bedafb1c8"
private const val C_ABI_MACOS_EXPORTS_SHA256 =
    "ed1d577f98752e7d38a03797652b345eca319dcd44acfcf386407582cde75bf5"
private const val C_ABI_FOUNDATION_C_SHA256 =
    "824ff6cd728641b10bff28034a2d866c7b5631cc5724cf536376a4918081a1f1"
private const val C_ABI_FOUNDATION_CPP_SHA256 =
    "5de6cd7ce3102da418dd4715b4e75c2245d7eadc842c1540f92901ef7798b4f8"
private const val C_ABI_LIFECYCLE_C_SHA256 =
    "5d35289fa1536d4981d45bb0f39700d967078d09a318759803b5e9bcd84a5226"
private const val C_ABI_LIFECYCLE_CPP_SHA256 =
    "b29e8410aa32146d6a92e2c3fc5d38c279dedd10e50343ff46a9f7995fb609d5"
private const val C_ABI_CONVERSATION_VALUES_C_SHA256 =
    "9bd1c7284344c037426a903fa08f5997f4c4746a597b4072ec5aa2d6911256c5"
private const val C_ABI_CONFIGURATION_VALUES_C_SHA256 =
    "09f4d7b50e35bba8db3cb3272eddf81a0961dcca98932a41cea14de36039a24a"
private const val C_ABI_RESOURCE_VALUES_C_SHA256 =
    "3bf242135135ae85650c87b1c2b09b696a4f2481082b404ba0064dcffee686f3"
private const val C_ABI_ORDINARY_ENUMS_C_SHA256 =
    "9063464636e559c714e5fc5a9bf86bc82a5e82f6fd0cf5d93fc7d21b8a097e45"
private const val C_ABI_FORM_HOOK_VALUES_C_SHA256 =
    "88b60e85f2c04c9708b5211da5c40b1317117598be602df1891e9a9417d5f865"
private const val C_ABI_INVOCATION_AUTH_VALUES_C_SHA256 =
    "6815c11c3f730a92ef9e53cc14092177369812a9fe95b369d0bab3b3c9f93f55"
private const val C_ABI_PROGRESS_LIST_VALUES_C_SHA256 =
    "3761f263868a16c11975f2a18b87e807c90d809cfaf20476e86634c5cb5f30af"
private const val C_ABI_RESOURCE_LIST_VALUES_C_SHA256 =
    "b3ad64bd5a0c066f9f3f543162ab01d0a16e2ed2ef682a4531b4119a5e3bcc11"
private const val C_ABI_LIST_LEAF_VALUES_C_SHA256 =
    "486382fe97d4ba7278599f9b45dc3142f5a36a2223f3265a54416b26a8b86ed5"

private const val AGENT_PACKAGE = "io.github.codex_agent_labs.codexmobile.agent/"
private const val C_API_TEST_PACKAGE = "macosArm64Test.io.github.codex_agent_labs.codexmobile.capi."
private const val C_LIFECYCLE_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCLifecycleTest#projectsCanonicalLifecycleAndQuiescesEveryCallback[macosArm64]"
private const val C_PREPARE_FAILURE_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCLifecycleTest#projectsStructuredPrepareFailureAndQuiescesFailedHost[macosArm64]"
private const val C_VALUE_CONVERSATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCValueProjectionTest#projectsEveryConversationStatusAndFailureExactly[macosArm64]"
private const val C_VALUE_HOST_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCValueProjectionTest#projectsMissingHostStateVariantsAndPayloadsExactly[macosArm64]"
private const val C_CONVERSATION_FAILURE_TEST =
    C_API_TEST_PACKAGE + "CodexAgentCConversationValuesTest#createsAndValidatesFailures[macosArm64]"
private const val C_CONVERSATION_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConversationValuesTest#projectsConversationValuesWithIndependentNestedOwnership[macosArm64]"
private const val C_WORKSPACE_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConversationValuesTest#projectsWorkspaceDefaultsAndIndependentAvailableOwnership[macosArm64]"
private const val C_APPROVAL_WORKSPACE_ENUM_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConversationValuesTest#projectsEveryApprovalPresetAndWorkspaceSelectionReasonExactly[macosArm64]"
private const val C_FORM_OPTION_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#formOptionPreservesDefaultsNullabilityAndCopiedInput[macosArm64]"
private const val C_FORM_OPTION_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#formOptionRejectsInvalidFlagsViewsUtf8AndOccupiedOutput[macosArm64]"
private const val C_MCP_ENVIRONMENT_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#mcpEnvironmentVariableProjectsEverySourceAndAbsentSource[macosArm64]"
private const val C_MCP_ENVIRONMENT_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#mcpEnvironmentVariableRejectsBlankFlagsAbsentScalarAndUnknownSource[macosArm64]"
private const val C_MCP_OAUTH_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#mcpOauthConfigurationPreservesNullableValuesAndPortBoundaries[macosArm64]"
private const val C_MCP_OAUTH_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#mcpOauthConfigurationRejectsInvalidFlagsPairsUtf8AndPorts[macosArm64]"
private const val C_MCP_TOOL_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#mcpToolConfigurationProjectsEveryApprovalAndAbsentApproval[macosArm64]"
private const val C_ELICITATION_VALIDATION_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#elicitationValidationIssueProjectsEveryReasonAndCopiesFieldName[macosArm64]"
private const val C_PLAN_STEP_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCConfigurationValuesTest#planStepProjectsEveryStatusAndCopiesText[macosArm64]"
private const val C_PLUGIN_REFERENCE_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceValuesTest#pluginReferenceProjectsEveryPropertyAndNullableState[macosArm64]"
private const val C_RESOURCE_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceValuesTest#pluginSkillServiceTierAndSkillChunkProjectExactValues[macosArm64]"
private const val C_RESOURCE_ENUM_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceValuesTest#capabilityAndSkillScopeEntriesProjectCanonicalLabels[macosArm64]"
private const val C_FORM_HOOK_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCFormHookValuesTest#projectsBooleanNumberAndTextFormValuesExactly[macosArm64]"
private const val C_FORM_HOOK_VARIANTS_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCFormHookValuesTest#projectsEveryHookHandlerVariantExactly[macosArm64]"
private const val C_FORM_HOOK_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCFormHookValuesTest#rejectsInvalidViewsFlagsAndOutputSlots[macosArm64]"
private const val C_FORM_HOOK_HANDLE_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCFormHookValuesTest#rejectsWrongContextPayloadAndStaleHandles[macosArm64]"
private const val C_INVOCATION_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCInvocationAuthValuesTest#invocationLeavesCopyInputsAndProjectCanonicalKeys[macosArm64]"
private const val C_PENDING_APPROVAL_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCInvocationAuthValuesTest#pendingApprovalOwnsIndependentConversationIdSnapshots[macosArm64]"
private const val C_AUTHENTICATION_METHOD_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCInvocationAuthValuesTest#authenticationMethodLeavesValidateSecretsAndOwnDistinctHandles[macosArm64]"
private const val C_MODEL_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCProgressListValuesTest#modelCopiesOrderedListsDuplicatesAndNestedServiceTiers[macosArm64]"
private const val C_PLAN_PROGRESS_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCProgressListValuesTest#planProgressCopiesOrderedDuplicateStepsAndOwnsReturnedChildren[macosArm64]"
private const val C_HOOK_ACTIVITY_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCProgressListValuesTest#hookActivityProjectsEveryStatusNullableMessageAndCopiedDetails[macosArm64]"
private const val C_TURN_PROGRESS_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCProgressListValuesTest#turnProgressOwnsNestedProgressHooksAndProjectsNullability[macosArm64]"
private const val C_PROGRESS_LIST_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCProgressListValuesTest#collectionInputsBoundsOutputsContextsTypesAndDestructionFailClosed[macosArm64]"
private const val C_CONNECTOR_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceListValuesTest#connectorCopiesOrderedDuplicateNamesAndProjectsEveryProperty[macosArm64]"
private const val C_SKILL_CATALOG_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceListValuesTest#skillAndCatalogPreserveDefaultsListsAndIndependentChildren[macosArm64]"
private const val C_PLUGIN_CATALOG_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceListValuesTest#pluginSummaryAndCatalogOwnNestedValuesAndProjectEveryField[macosArm64]"
private const val C_PLUGIN_DETAIL_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceListValuesTest#pluginDetailAndInstallResultOwnOrderedNestedValues[macosArm64]"
private const val C_RESOURCE_LIST_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCResourceListValuesTest#rejectsInvalidListsFlagsEnumsUtf8ContextsTypesAndOutputs[macosArm64]"
private const val C_TEXT_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCListLeafValuesTest#textListCopiesOrderedDuplicateUtf8ValuesAndProjectsEmpty[macosArm64]"
private const val C_TEXT_LIST_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCListLeafValuesTest#textListRejectsMalformedArraysBoundsOutputsContextTypeAndStaleHandles[macosArm64]"
private const val C_ELICITATION_VALIDATION_LIST_VALUES_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCListLeafValuesTest#validationCopiesOrderedDuplicateIssuesAndReturnsIndependentChildren[macosArm64]"
private const val C_ELICITATION_VALIDATION_LIST_VALIDATION_TEST =
    C_API_TEST_PACKAGE +
        "CodexAgentCListLeafValuesTest#validationRejectsArrayOutputContextTypeAndStaleHandleFailures[macosArm64]"

internal data class CAbiBootstrapClaimSpec(
    val owner: String,
    val kind: String,
    val abi: String,
    val canonicalSignatureReference: String?,
    val headerReferences: List<String>,
    val consumerReferences: List<String>,
    val publicSymbols: List<String>,
    val nativeTestIds: List<String>,
)

internal data class CAbiBootstrapClaim(
    val capabilityKey: String,
    val headerReferences: List<String>,
    val consumerReferences: List<String>,
    val publicSymbols: List<String>,
    val nativeTestIds: List<String>,
)

private fun claim(
    owner: String,
    kind: String,
    member: String,
    headerReferences: List<String>,
    canonicalSignatureReference: String? = null,
    consumerReferences: List<String> = headerReferences,
    publicSymbols: List<String>,
    nativeTestIds: List<String>,
): CAbiBootstrapClaimSpec = CAbiBootstrapClaimSpec(
    owner = AGENT_PACKAGE + owner,
    kind = kind,
    abi = AGENT_PACKAGE + member,
    canonicalSignatureReference = canonicalSignatureReference,
    headerReferences = headerReferences,
    consumerReferences = consumerReferences,
    publicSymbols = publicSymbols,
    nativeTestIds = nativeTestIds,
)

internal val cAbiBootstrapClaimSpecs: List<CAbiBootstrapClaimSpec> = buildList {
    val conversationStatus = "codex_agent_conversation_state_status"
    val conversationFailure = "codex_agent_conversation_state_failure"
    add(claim(
        "AgentConversationState", "property", "AgentConversationState.failure",
        listOf(conversationFailure), publicSymbols = listOf(conversationFailure),
        nativeTestIds = listOf(C_VALUE_CONVERSATION_TEST),
    ))
    add(claim(
        "AgentConversationState", "property", "AgentConversationState.status",
        listOf(conversationStatus), publicSymbols = listOf(conversationStatus),
        nativeTestIds = listOf(C_LIFECYCLE_TEST, C_VALUE_CONVERSATION_TEST),
    ))
    listOf(
        "CANCELLING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_CANCELLING_TURN",
        "CLOSED" to "CODEX_AGENT_CONVERSATION_STATUS_CLOSED",
        "FAILED" to "CODEX_AGENT_CONVERSATION_STATUS_FAILED",
        "NEW" to "CODEX_AGENT_CONVERSATION_STATUS_NEW",
        "OPENING" to "CODEX_AGENT_CONVERSATION_STATUS_OPENING",
        "READY" to "CODEX_AGENT_CONVERSATION_STATUS_READY",
        "RELOADING" to "CODEX_AGENT_CONVERSATION_STATUS_RELOADING",
        "RUNNING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_RUNNING_TURN",
        "STARTING_TURN" to "CODEX_AGENT_CONVERSATION_STATUS_STARTING_TURN",
    ).forEach { (entry, macro) ->
        add(claim(
            "AgentConversationStatus", "enum-entry", "AgentConversationStatus.$entry",
            listOf(macro, conversationStatus), publicSymbols = listOf(conversationStatus),
            nativeTestIds = listOf(C_VALUE_CONVERSATION_TEST),
        ))
    }
    add(claim(
        "CodexAgent", "property", "CodexAgent.conversations",
        listOf("codex_agent_agent_conversations"),
        publicSymbols = listOf("codex_agent_agent_conversations"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexConversations", "function", "CodexConversations.open",
        listOf("codex_agent_conversations_open"),
        publicSymbols = listOf("codex_agent_conversations_open"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexConversations", "property", "CodexConversations.active",
        listOf(
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            "codex_agent_active_conversation",
        ),
        publicSymbols = listOf(
            "codex_agent_conversations_active_get",
            "codex_agent_conversations_active_subscribe",
            "codex_agent_active_conversation",
        ),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    listOf(
        Triple("cancelTurn", "codex_agent_conversation_cancel_turn", "function"),
        Triple("close", "codex_agent_conversation_close", "function"),
        Triple("send", "codex_agent_conversation_send", "function"),
        Triple("state", "codex_agent_conversation_state_get", "property"),
    ).forEach { (member, symbol, kind) ->
        val symbols = if (member == "state") {
            listOf(symbol, "codex_agent_conversation_state_subscribe")
        } else {
            listOf(symbol)
        }
        add(claim(
            "CodexConversation", kind, "CodexConversation.$member",
            symbols,
            canonicalSignatureReference = if (member == "send") "send(kotlin.String){}[0]" else null,
            publicSymbols = symbols,
            nativeTestIds = listOf(C_LIFECYCLE_TEST),
        ))
    }
    listOf(
        Triple("code", "codex_agent_failure_code_copy", listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST)),
        Triple(
            "isRecoverable",
            "codex_agent_failure_is_recoverable",
            listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST, C_VALUE_HOST_TEST),
        ),
        Triple("message", "codex_agent_failure_message_copy", listOf(C_PREPARE_FAILURE_TEST, C_VALUE_CONVERSATION_TEST)),
    ).forEach { (member, symbol, tests) ->
        add(claim(
            "CodexFailure", "property", "CodexFailure.$member",
            listOf(symbol), publicSymbols = listOf(symbol), nativeTestIds = tests,
        ))
    }
    fun hostState(
        owner: String,
        kind: String,
        member: String,
        macro: String,
        payloadSymbols: List<String>,
        tests: List<String>,
    ) {
        val symbols = listOf("codex_agent_host_state_kind") + payloadSymbols
        add(claim(
            owner, kind, member,
            listOf(macro) + symbols,
            publicSymbols = symbols,
            nativeTestIds = tests,
        ))
    }
    hostState(
        "CodexHostState.Closed", "object", "CodexHostState.Closed",
        "CODEX_AGENT_HOST_STATE_CLOSED", emptyList(), listOf(C_LIFECYCLE_TEST),
    )
    hostState(
        "CodexHostState.Failed", "constructor", "CodexHostState.Failed.<init>",
        "CODEX_AGENT_HOST_STATE_FAILED",
        listOf(
            "codex_agent_host_state_has_workspace",
            "codex_agent_host_state_workspace_path_copy",
            "codex_agent_host_state_workspace_display_name_copy",
            "codex_agent_host_state_failure",
        ),
        listOf(C_PREPARE_FAILURE_TEST, C_VALUE_HOST_TEST),
    )
    add(claim(
        "CodexHostState.Failed", "property", "CodexHostState.Failed.failure",
        listOf("codex_agent_host_state_failure"),
        publicSymbols = listOf("codex_agent_host_state_failure"),
        nativeTestIds = listOf(C_PREPARE_FAILURE_TEST, C_VALUE_HOST_TEST),
    ))
    hostState(
        "CodexHostState.New", "object", "CodexHostState.New",
        "CODEX_AGENT_HOST_STATE_NEW", emptyList(), listOf(C_LIFECYCLE_TEST),
    )
    hostState(
        "CodexHostState.Preparing", "constructor", "CodexHostState.Preparing.<init>",
        "CODEX_AGENT_HOST_STATE_PREPARING",
        listOf(
            "codex_agent_host_state_has_workspace",
            "codex_agent_host_state_workspace_path_copy",
            "codex_agent_host_state_workspace_display_name_copy",
        ),
        listOf(C_VALUE_HOST_TEST),
    )
    hostState(
        "CodexHostState.Ready", "constructor", "CodexHostState.Ready.<init>",
        "CODEX_AGENT_HOST_STATE_READY", listOf("codex_agent_host_state_agent"),
        listOf(C_LIFECYCLE_TEST),
    )
    add(claim(
        "CodexHostState.Ready", "property", "CodexHostState.Ready.agent",
        listOf("codex_agent_host_state_agent"),
        publicSymbols = listOf("codex_agent_host_state_agent"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    hostState(
        "CodexHostState.Restoring", "object", "CodexHostState.Restoring",
        "CODEX_AGENT_HOST_STATE_RESTORING", emptyList(), listOf(C_VALUE_HOST_TEST),
    )
    hostState(
        "CodexHostState.WorkspaceRequired", "constructor", "CodexHostState.WorkspaceRequired.<init>",
        "CODEX_AGENT_HOST_STATE_WORKSPACE_REQUIRED",
        listOf(
            "codex_agent_host_state_requirement_reason",
            "codex_agent_host_state_requirement_message_copy",
        ),
        listOf(C_VALUE_HOST_TEST),
    )
    listOf(
        Triple("close", "codex_agent_host_close", "function"),
        Triple("selectWorkspace", "codex_agent_host_select_workspace", "function"),
        Triple("lifecycleState", "codex_agent_host_state_get", "property"),
    ).forEach { (member, symbol, kind) ->
        val symbols = if (member == "lifecycleState") {
            listOf(symbol, "codex_agent_host_state_subscribe")
        } else {
            listOf(symbol)
        }
        val tests = if (member == "selectWorkspace") {
            listOf(C_LIFECYCLE_TEST, C_PREPARE_FAILURE_TEST)
        } else {
            listOf(C_LIFECYCLE_TEST)
        }
        add(claim(
            "CodexHost", kind, "CodexHost.$member",
            symbols, publicSymbols = symbols, nativeTestIds = tests,
        ))
    }
    add(claim(
        "CodexPathWorkspaceSelection", "constructor", "CodexPathWorkspaceSelection.<init>",
        listOf("codex_agent_path_workspace_selection_t", "codex_agent_host_select_workspace"),
        publicSymbols = listOf("codex_agent_host_select_workspace"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))
    add(claim(
        "CodexPathWorkspaceSelection", "property", "CodexPathWorkspaceSelection.path",
        listOf("codex_agent_string_view_t path;", "codex_agent_host_select_workspace"),
        consumerReferences = listOf("workspace_selection.path", "codex_agent_host_select_workspace"),
        publicSymbols = listOf("codex_agent_host_select_workspace"),
        nativeTestIds = listOf(C_LIFECYCLE_TEST),
    ))

    fun ordinary(
        owner: String,
        kind: String,
        member: String,
        symbols: List<String>,
        tests: List<String>,
        signature: String? = null,
    ) {
        add(claim(
            owner,
            kind,
            "$owner.$member",
            symbols,
            canonicalSignatureReference = signature,
            publicSymbols = symbols,
            nativeTestIds = tests,
        ))
    }

    fun enumEntry(
        owner: String,
        entry: String,
        macro: String,
        symbols: List<String>,
        test: String,
    ) {
        add(claim(
            owner,
            "enum-entry",
            "$owner.$entry",
            listOf(macro) + symbols,
            publicSymbols = symbols,
            nativeTestIds = listOf(test),
        ))
    }

    fun ordinaryEnum(
        owner: String,
        validator: String,
        testMethod: String,
        entries: List<Pair<String, String>>,
    ) {
        val test = C_API_TEST_PACKAGE + "CodexAgentCOrdinaryEnumsTest#$testMethod[macosArm64]"
        entries.forEach { (entry, macro) ->
            enumEntry(owner, entry, macro, listOf(validator), test)
        }
    }

    ordinary(
        "CodexFailure",
        "constructor",
        "<init>",
        listOf("codex_agent_failure_create"),
        listOf(C_CONVERSATION_FAILURE_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.Boolean){}[0]",
    )
    ordinary(
        "ConversationId",
        "constructor",
        "<init>",
        listOf("codex_agent_conversation_id_create", "codex_agent_conversation_id_destroy"),
        listOf(C_CONVERSATION_VALUES_TEST),
        "<init>(kotlin.String){}[0]",
    )
    ordinary(
        "ConversationId", "property", "value",
        listOf("codex_agent_conversation_id_value_copy"), listOf(C_CONVERSATION_VALUES_TEST),
    )
    ordinary(
        "AgentConversationSummary",
        "constructor",
        "<init>",
        listOf("codex_agent_conversation_summary_create", "codex_agent_conversation_summary_destroy"),
        listOf(C_CONVERSATION_VALUES_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String;kotlin.Long){}[0]",
    )
    ordinary(
        "AgentConversationSummary", "property", "conversationId",
        listOf("codex_agent_conversation_summary_conversation_id"), listOf(C_CONVERSATION_VALUES_TEST),
    )
    ordinary(
        "AgentConversationSummary", "property", "title",
        listOf("codex_agent_conversation_summary_title_copy"), listOf(C_CONVERSATION_VALUES_TEST),
    )
    ordinary(
        "AgentConversationSummary", "property", "updatedAtEpochSeconds",
        listOf("codex_agent_conversation_summary_updated_at_epoch_seconds"),
        listOf(C_CONVERSATION_VALUES_TEST),
    )
    ordinary(
        "CodexWorkspace",
        "constructor",
        "<init>",
        listOf("codex_agent_workspace_create", "codex_agent_workspace_destroy"),
        listOf(C_WORKSPACE_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String){}[0]",
    )
    ordinary(
        "CodexWorkspace", "property", "path",
        listOf("codex_agent_workspace_path_copy"), listOf(C_WORKSPACE_VALUES_TEST),
    )
    ordinary(
        "CodexWorkspace", "property", "displayName",
        listOf("codex_agent_workspace_display_name_copy"), listOf(C_WORKSPACE_VALUES_TEST),
    )
    ordinary(
        "CodexWorkspaceResolution.Available",
        "constructor",
        "<init>",
        listOf(
            "codex_agent_workspace_resolution_available_create",
            "codex_agent_workspace_resolution_available_destroy",
        ),
        listOf(C_WORKSPACE_VALUES_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace){}[0]",
    )
    ordinary(
        "CodexWorkspaceResolution.Available", "property", "workspace",
        listOf("codex_agent_workspace_resolution_available_workspace"), listOf(C_WORKSPACE_VALUES_TEST),
    )
    ordinary(
        "CodexWorkspaceResolution.SelectionRequired",
        "constructor",
        "<init>",
        listOf(
            "codex_agent_workspace_selection_required_create",
            "codex_agent_workspace_selection_required_destroy",
        ),
        listOf(C_APPROVAL_WORKSPACE_ENUM_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason;kotlin.String){}[0]",
    )
    ordinary(
        "CodexWorkspaceResolution.SelectionRequired", "property", "reason",
        listOf("codex_agent_workspace_selection_required_reason"), listOf(C_APPROVAL_WORKSPACE_ENUM_TEST),
    )
    ordinary(
        "CodexWorkspaceResolution.SelectionRequired", "property", "message",
        listOf("codex_agent_workspace_selection_required_message_copy"),
        listOf(C_APPROVAL_WORKSPACE_ENUM_TEST),
    )
    ordinary(
        "AgentApprovalPreset", "property", "displayName",
        listOf("codex_agent_approval_preset_display_name_copy"), listOf(C_APPROVAL_WORKSPACE_ENUM_TEST),
    )
    listOf(
        "ASK_ME" to "CODEX_AGENT_APPROVAL_PRESET_ASK_ME",
        "AUTO_REVIEW" to "CODEX_AGENT_APPROVAL_PRESET_AUTO_REVIEW",
        "NEVER" to "CODEX_AGENT_APPROVAL_PRESET_NEVER",
        "STRICT" to "CODEX_AGENT_APPROVAL_PRESET_STRICT",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentApprovalPreset", entry, macro,
            listOf("codex_agent_approval_preset_display_name_copy"), C_APPROVAL_WORKSPACE_ENUM_TEST,
        )
    }
    listOf(
        "ACCESS_REVOKED" to "CODEX_AGENT_WORKSPACE_REASON_ACCESS_REVOKED",
        "INVALID_SELECTION" to "CODEX_AGENT_WORKSPACE_REASON_INVALID_SELECTION",
        "NOT_FOUND" to "CODEX_AGENT_WORKSPACE_REASON_NOT_FOUND",
        "NOT_SELECTED" to "CODEX_AGENT_WORKSPACE_REASON_NOT_SELECTED",
    ).forEach { (entry, macro) ->
        enumEntry(
            "CodexWorkspaceSelectionReason", entry, macro,
            listOf(
                "codex_agent_workspace_selection_required_create",
                "codex_agent_workspace_selection_required_reason",
            ),
            C_APPROVAL_WORKSPACE_ENUM_TEST,
        )
    }

    ordinary(
        "AgentFormOption",
        "constructor",
        "<init>",
        listOf("codex_agent_form_option_create", "codex_agent_form_option_destroy"),
        listOf(C_FORM_OPTION_VALUES_TEST, C_FORM_OPTION_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String?){}[0]",
    )
    ordinary(
        "AgentFormOption", "property", "value",
        listOf("codex_agent_form_option_value_copy"), listOf(C_FORM_OPTION_VALUES_TEST),
    )
    ordinary(
        "AgentFormOption", "property", "title",
        listOf("codex_agent_form_option_title_copy"), listOf(C_FORM_OPTION_VALUES_TEST),
    )
    ordinary(
        "AgentFormOption", "property", "description",
        listOf("codex_agent_form_option_has_description", "codex_agent_form_option_description_copy"),
        listOf(C_FORM_OPTION_VALUES_TEST),
    )
    ordinary(
        "AgentMcpEnvironmentVariable",
        "constructor",
        "<init>",
        listOf(
            "codex_agent_mcp_environment_variable_create",
            "codex_agent_mcp_environment_variable_destroy",
        ),
        listOf(C_MCP_ENVIRONMENT_VALUES_TEST, C_MCP_ENVIRONMENT_VALIDATION_TEST),
        "<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentMcpEnvironmentSource?){}[0]",
    )
    ordinary(
        "AgentMcpEnvironmentVariable", "property", "name",
        listOf("codex_agent_mcp_environment_variable_name_copy"), listOf(C_MCP_ENVIRONMENT_VALUES_TEST),
    )
    ordinary(
        "AgentMcpEnvironmentVariable", "property", "source",
        listOf("codex_agent_mcp_environment_variable_source"), listOf(C_MCP_ENVIRONMENT_VALUES_TEST),
    )
    listOf(
        "LOCAL" to "CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_LOCAL",
        "REMOTE" to "CODEX_AGENT_MCP_ENVIRONMENT_SOURCE_REMOTE",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentMcpEnvironmentSource", entry, macro,
            listOf(
                "codex_agent_mcp_environment_variable_create",
                "codex_agent_mcp_environment_variable_source",
            ),
            C_MCP_ENVIRONMENT_VALUES_TEST,
        )
    }
    ordinary(
        "AgentMcpOauthConfiguration",
        "constructor",
        "<init>",
        listOf("codex_agent_mcp_oauth_configuration_create", "codex_agent_mcp_oauth_configuration_destroy"),
        listOf(C_MCP_OAUTH_VALUES_TEST, C_MCP_OAUTH_VALIDATION_TEST),
        "<init>(kotlin.String?;kotlin.Int?){}[0]",
    )
    ordinary(
        "AgentMcpOauthConfiguration", "property", "clientId",
        listOf(
            "codex_agent_mcp_oauth_configuration_has_client_id",
            "codex_agent_mcp_oauth_configuration_client_id_copy",
        ),
        listOf(C_MCP_OAUTH_VALUES_TEST),
    )
    ordinary(
        "AgentMcpOauthConfiguration", "property", "callbackPort",
        listOf("codex_agent_mcp_oauth_configuration_callback_port"), listOf(C_MCP_OAUTH_VALUES_TEST),
    )
    ordinary(
        "AgentMcpToolConfiguration",
        "constructor",
        "<init>",
        listOf("codex_agent_mcp_tool_configuration_create", "codex_agent_mcp_tool_configuration_destroy"),
        listOf(C_MCP_TOOL_VALUES_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.AgentMcpToolApproval?){}[0]",
    )
    ordinary(
        "AgentMcpToolConfiguration", "property", "approval",
        listOf("codex_agent_mcp_tool_configuration_approval"), listOf(C_MCP_TOOL_VALUES_TEST),
    )
    listOf(
        "APPROVE" to "CODEX_AGENT_MCP_TOOL_APPROVAL_APPROVE",
        "AUTO" to "CODEX_AGENT_MCP_TOOL_APPROVAL_AUTO",
        "PROMPT" to "CODEX_AGENT_MCP_TOOL_APPROVAL_PROMPT",
        "WRITES" to "CODEX_AGENT_MCP_TOOL_APPROVAL_WRITES",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentMcpToolApproval", entry, macro,
            listOf("codex_agent_mcp_tool_configuration_create", "codex_agent_mcp_tool_configuration_approval"),
            C_MCP_TOOL_VALUES_TEST,
        )
    }
    ordinary(
        "AgentElicitationValidationIssue",
        "constructor",
        "<init>",
        listOf(
            "codex_agent_elicitation_validation_issue_create",
            "codex_agent_elicitation_validation_issue_destroy",
        ),
        listOf(C_ELICITATION_VALIDATION_VALUES_TEST),
        "<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentElicitationValidationReason){}[0]",
    )
    ordinary(
        "AgentElicitationValidationIssue", "property", "fieldName",
        listOf("codex_agent_elicitation_validation_issue_field_name_copy"),
        listOf(C_ELICITATION_VALIDATION_VALUES_TEST),
    )
    ordinary(
        "AgentElicitationValidationIssue", "property", "reason",
        listOf("codex_agent_elicitation_validation_issue_reason"),
        listOf(C_ELICITATION_VALIDATION_VALUES_TEST),
    )
    listOf(
        "ABOVE_MAXIMUM" to "CODEX_AGENT_ELICITATION_VALIDATION_ABOVE_MAXIMUM",
        "BELOW_MINIMUM" to "CODEX_AGENT_ELICITATION_VALIDATION_BELOW_MINIMUM",
        "DUPLICATE_SELECTION" to "CODEX_AGENT_ELICITATION_VALIDATION_DUPLICATE_SELECTION",
        "INVALID_FORMAT" to "CODEX_AGENT_ELICITATION_VALIDATION_INVALID_FORMAT",
        "INVALID_SELECTION" to "CODEX_AGENT_ELICITATION_VALIDATION_INVALID_SELECTION",
        "INVALID_TYPE" to "CODEX_AGENT_ELICITATION_VALIDATION_INVALID_TYPE",
        "MISSING_REQUIRED" to "CODEX_AGENT_ELICITATION_VALIDATION_MISSING_REQUIRED",
        "NON_FINITE_NUMBER" to "CODEX_AGENT_ELICITATION_VALIDATION_NON_FINITE_NUMBER",
        "NON_INTEGER" to "CODEX_AGENT_ELICITATION_VALIDATION_NON_INTEGER",
        "UNKNOWN_FIELD" to "CODEX_AGENT_ELICITATION_VALIDATION_UNKNOWN_FIELD",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentElicitationValidationReason", entry, macro,
            listOf(
                "codex_agent_elicitation_validation_issue_create",
                "codex_agent_elicitation_validation_issue_reason",
            ),
            C_ELICITATION_VALIDATION_VALUES_TEST,
        )
    }
    ordinary(
        "AgentPlanStep",
        "constructor",
        "<init>",
        listOf("codex_agent_plan_step_create", "codex_agent_plan_step_destroy"),
        listOf(C_PLAN_STEP_VALUES_TEST),
        "<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.AgentPlanStepStatus){}[0]",
    )
    ordinary(
        "AgentPlanStep", "property", "text",
        listOf("codex_agent_plan_step_text_copy"), listOf(C_PLAN_STEP_VALUES_TEST),
    )
    ordinary(
        "AgentPlanStep", "property", "status",
        listOf("codex_agent_plan_step_status"), listOf(C_PLAN_STEP_VALUES_TEST),
    )
    listOf(
        "COMPLETED" to "CODEX_AGENT_PLAN_STEP_COMPLETED",
        "IN_PROGRESS" to "CODEX_AGENT_PLAN_STEP_IN_PROGRESS",
        "PENDING" to "CODEX_AGENT_PLAN_STEP_PENDING",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentPlanStepStatus", entry, macro,
            listOf("codex_agent_plan_step_create", "codex_agent_plan_step_status"), C_PLAN_STEP_VALUES_TEST,
        )
    }

    ordinary(
        "AgentPluginReference",
        "constructor",
        "<init>",
        listOf("codex_agent_plugin_reference_create", "codex_agent_plugin_reference_destroy"),
        listOf(C_PLUGIN_REFERENCE_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String?;kotlin.String?){}[0]",
    )
    listOf(
        "id" to listOf("codex_agent_plugin_reference_id_copy"),
        "name" to listOf("codex_agent_plugin_reference_name_copy"),
        "marketplaceName" to listOf("codex_agent_plugin_reference_marketplace_name_copy"),
        "marketplacePath" to listOf(
            "codex_agent_plugin_reference_has_marketplace_path",
            "codex_agent_plugin_reference_marketplace_path_copy",
        ),
        "remotePluginId" to listOf(
            "codex_agent_plugin_reference_has_remote_plugin_id",
            "codex_agent_plugin_reference_remote_plugin_id_copy",
        ),
        "uri" to listOf("codex_agent_plugin_reference_uri_copy"),
    ).forEach { (property, symbols) ->
        ordinary(
            "AgentPluginReference", "property", property, symbols, listOf(C_PLUGIN_REFERENCE_VALUES_TEST),
        )
    }
    ordinary(
        "AgentPluginSkill",
        "constructor",
        "<init>",
        listOf("codex_agent_plugin_skill_create", "codex_agent_plugin_skill_destroy"),
        listOf(C_RESOURCE_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.Boolean;kotlin.String?){}[0]",
    )
    listOf(
        "name" to listOf("codex_agent_plugin_skill_name_copy"),
        "description" to listOf("codex_agent_plugin_skill_description_copy"),
        "isEnabled" to listOf("codex_agent_plugin_skill_is_enabled"),
        "path" to listOf("codex_agent_plugin_skill_has_path", "codex_agent_plugin_skill_path_copy"),
    ).forEach { (property, symbols) ->
        ordinary("AgentPluginSkill", "property", property, symbols, listOf(C_RESOURCE_VALUES_TEST))
    }
    ordinary(
        "AgentServiceTier",
        "constructor",
        "<init>",
        listOf("codex_agent_service_tier_create", "codex_agent_service_tier_destroy"),
        listOf(C_RESOURCE_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String){}[0]",
    )
    listOf(
        "id" to "codex_agent_service_tier_id_copy",
        "name" to "codex_agent_service_tier_name_copy",
        "description" to "codex_agent_service_tier_description_copy",
    ).forEach { (property, symbol) ->
        ordinary("AgentServiceTier", "property", property, listOf(symbol), listOf(C_RESOURCE_VALUES_TEST))
    }
    ordinary(
        "AgentSkillChunk",
        "constructor",
        "<init>",
        listOf("codex_agent_skill_chunk_create", "codex_agent_skill_chunk_destroy"),
        listOf(C_RESOURCE_VALUES_TEST),
        "<init>(kotlin.String;kotlin.Long?;kotlin.Long){}[0]",
    )
    listOf(
        "content" to "codex_agent_skill_chunk_content_copy",
        "nextOffset" to "codex_agent_skill_chunk_next_offset",
        "totalBytes" to "codex_agent_skill_chunk_total_bytes",
    ).forEach { (property, symbol) ->
        ordinary("AgentSkillChunk", "property", property, listOf(symbol), listOf(C_RESOURCE_VALUES_TEST))
    }
    listOf(
        "id" to listOf("codex_agent_capability_id_copy"),
        "displayLabel" to listOf("codex_agent_capability_display_label_copy"),
        "icon" to listOf("codex_agent_capability_has_icon", "codex_agent_capability_icon_copy"),
        "promptLabel" to listOf("codex_agent_capability_prompt_label_copy"),
    ).forEach { (property, symbols) ->
        ordinary("AgentCapability", "property", property, symbols, listOf(C_RESOURCE_ENUM_VALUES_TEST))
    }
    enumEntry(
        "AgentCapability",
        "WEB_SEARCH",
        "CODEX_AGENT_CAPABILITY_WEB_SEARCH",
        listOf("codex_agent_capability_id_copy"),
        C_RESOURCE_ENUM_VALUES_TEST,
    )
    ordinary(
        "AgentSkillScope", "property", "displayName",
        listOf("codex_agent_skill_scope_display_name_copy"), listOf(C_RESOURCE_ENUM_VALUES_TEST),
    )
    listOf(
        "ADMIN" to "CODEX_AGENT_SKILL_SCOPE_ADMIN",
        "PLUGIN" to "CODEX_AGENT_SKILL_SCOPE_PLUGIN",
        "REPO" to "CODEX_AGENT_SKILL_SCOPE_REPO",
        "SYSTEM" to "CODEX_AGENT_SKILL_SCOPE_SYSTEM",
        "USER" to "CODEX_AGENT_SKILL_SCOPE_USER",
    ).forEach { (entry, macro) ->
        enumEntry(
            "AgentSkillScope", entry, macro,
            listOf("codex_agent_skill_scope_display_name_copy"), C_RESOURCE_ENUM_VALUES_TEST,
        )
    }

    ordinaryEnum(
        "AgentApprovalDecision",
        "codex_agent_approval_decision_validate",
        "validatesAgentApprovalDecision",
        listOf(
            "ACCEPT" to "CODEX_AGENT_APPROVAL_DECISION_ACCEPT",
            "DECLINE" to "CODEX_AGENT_APPROVAL_DECISION_DECLINE",
        ),
    )
    ordinaryEnum(
        "AgentAuthenticationStatus",
        "codex_agent_authentication_status_validate",
        "validatesAgentAuthenticationStatus",
        listOf(
            "AUTHENTICATED" to "CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATED",
            "AUTHENTICATING" to "CODEX_AGENT_AUTHENTICATION_STATUS_AUTHENTICATING",
            "SIGNED_OUT" to "CODEX_AGENT_AUTHENTICATION_STATUS_SIGNED_OUT",
        ),
    )
    ordinaryEnum(
        "AgentCatalogFreshness",
        "codex_agent_catalog_freshness_validate",
        "validatesAgentCatalogFreshness",
        listOf(
            "FRESH_CACHE" to "CODEX_AGENT_CATALOG_FRESHNESS_FRESH_CACHE",
            "LIVE" to "CODEX_AGENT_CATALOG_FRESHNESS_LIVE",
            "STALE_CACHE" to "CODEX_AGENT_CATALOG_FRESHNESS_STALE_CACHE",
        ),
    )
    ordinaryEnum(
        "AgentCollaborationMode",
        "codex_agent_collaboration_mode_validate",
        "validatesAgentCollaborationMode",
        listOf(
            "DEFAULT" to "CODEX_AGENT_COLLABORATION_MODE_DEFAULT",
            "PLAN" to "CODEX_AGENT_COLLABORATION_MODE_PLAN",
        ),
    )
    ordinaryEnum(
        "AgentElicitationAction",
        "codex_agent_elicitation_action_validate",
        "validatesAgentElicitationAction",
        listOf(
            "ACCEPT" to "CODEX_AGENT_ELICITATION_ACTION_ACCEPT",
            "CANCEL" to "CODEX_AGENT_ELICITATION_ACTION_CANCEL",
            "DECLINE" to "CODEX_AGENT_ELICITATION_ACTION_DECLINE",
        ),
    )
    ordinaryEnum(
        "AgentFormFieldType",
        "codex_agent_form_field_type_validate",
        "validatesAgentFormFieldType",
        listOf(
            "BOOLEAN" to "CODEX_AGENT_FORM_FIELD_TYPE_BOOLEAN",
            "INTEGER" to "CODEX_AGENT_FORM_FIELD_TYPE_INTEGER",
            "MULTI_SELECT" to "CODEX_AGENT_FORM_FIELD_TYPE_MULTI_SELECT",
            "NUMBER" to "CODEX_AGENT_FORM_FIELD_TYPE_NUMBER",
            "SINGLE_SELECT" to "CODEX_AGENT_FORM_FIELD_TYPE_SINGLE_SELECT",
            "STRING" to "CODEX_AGENT_FORM_FIELD_TYPE_STRING",
        ),
    )
    ordinaryEnum(
        "AgentFormStringFormat",
        "codex_agent_form_string_format_validate",
        "validatesAgentFormStringFormat",
        listOf(
            "DATE" to "CODEX_AGENT_FORM_STRING_FORMAT_DATE",
            "DATE_TIME" to "CODEX_AGENT_FORM_STRING_FORMAT_DATE_TIME",
            "EMAIL" to "CODEX_AGENT_FORM_STRING_FORMAT_EMAIL",
            "URI" to "CODEX_AGENT_FORM_STRING_FORMAT_URI",
        ),
    )
    ordinaryEnum(
        "AgentHookRunStatus",
        "codex_agent_hook_run_status_validate",
        "validatesAgentHookRunStatus",
        listOf(
            "BLOCKED" to "CODEX_AGENT_HOOK_RUN_STATUS_BLOCKED",
            "COMPLETED" to "CODEX_AGENT_HOOK_RUN_STATUS_COMPLETED",
            "FAILED" to "CODEX_AGENT_HOOK_RUN_STATUS_FAILED",
            "RUNNING" to "CODEX_AGENT_HOOK_RUN_STATUS_RUNNING",
            "STOPPED" to "CODEX_AGENT_HOOK_RUN_STATUS_STOPPED",
        ),
    )
    ordinaryEnum(
        "AgentHookTrustStatus",
        "codex_agent_hook_trust_status_validate",
        "validatesAgentHookTrustStatus",
        listOf(
            "MANAGED" to "CODEX_AGENT_HOOK_TRUST_STATUS_MANAGED",
            "MODIFIED" to "CODEX_AGENT_HOOK_TRUST_STATUS_MODIFIED",
            "TRUSTED" to "CODEX_AGENT_HOOK_TRUST_STATUS_TRUSTED",
            "UNTRUSTED" to "CODEX_AGENT_HOOK_TRUST_STATUS_UNTRUSTED",
        ),
    )
    ordinaryEnum(
        "AgentInstallationScope",
        "codex_agent_installation_scope_validate",
        "validatesAgentInstallationScope",
        listOf(
            "User" to "CODEX_AGENT_INSTALLATION_SCOPE_USER",
            "Workspace" to "CODEX_AGENT_INSTALLATION_SCOPE_WORKSPACE",
        ),
    )
    ordinaryEnum(
        "AgentIntegrationAuthorizationStatus",
        "codex_agent_integration_authorization_status_validate",
        "validatesAgentIntegrationAuthorizationStatus",
        listOf(
            "AUTHORIZED" to "CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AUTHORIZED",
            "AWAITING_COMPLETION" to "CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_AWAITING_COMPLETION",
            "FAILED" to "CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_FAILED",
            "IDLE" to "CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_IDLE",
            "STARTING" to "CODEX_AGENT_INTEGRATION_AUTHORIZATION_STATUS_STARTING",
        ),
    )
    ordinaryEnum(
        "AgentMcpAuthStatus",
        "codex_agent_mcp_auth_status_validate",
        "validatesAgentMcpAuthStatus",
        listOf(
            "BEARER_TOKEN" to "CODEX_AGENT_MCP_AUTH_STATUS_BEARER_TOKEN",
            "NOT_LOGGED_IN" to "CODEX_AGENT_MCP_AUTH_STATUS_NOT_LOGGED_IN",
            "OAUTH" to "CODEX_AGENT_MCP_AUTH_STATUS_OAUTH",
            "UNKNOWN" to "CODEX_AGENT_MCP_AUTH_STATUS_UNKNOWN",
            "UNSUPPORTED" to "CODEX_AGENT_MCP_AUTH_STATUS_UNSUPPORTED",
        ),
    )
    ordinaryEnum(
        "AgentMcpAuthentication",
        "codex_agent_mcp_authentication_validate",
        "validatesAgentMcpAuthentication",
        listOf(
            "CHAT_GPT" to "CODEX_AGENT_MCP_AUTHENTICATION_CHAT_GPT",
            "OAUTH" to "CODEX_AGENT_MCP_AUTHENTICATION_OAUTH",
        ),
    )
    ordinaryEnum(
        "AgentMcpToolExposureSurface",
        "codex_agent_mcp_tool_exposure_surface_validate",
        "validatesAgentMcpToolExposureSurface",
        listOf(
            "CODE_MODE" to "CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_CODE_MODE",
            "DEFERRED" to "CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DEFERRED",
            "DIRECT" to "CODEX_AGENT_MCP_TOOL_EXPOSURE_SURFACE_DIRECT",
        ),
    )
    ordinaryEnum(
        "AgentMessageRole",
        "codex_agent_message_role_validate",
        "validatesAgentMessageRole",
        listOf(
            "ASSISTANT" to "CODEX_AGENT_MESSAGE_ROLE_ASSISTANT",
            "USER" to "CODEX_AGENT_MESSAGE_ROLE_USER",
        ),
    )
    ordinaryEnum(
        "AgentPluginAuthPolicy",
        "codex_agent_plugin_auth_policy_validate",
        "validatesAgentPluginAuthPolicy",
        listOf(
            "ON_INSTALL" to "CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_INSTALL",
            "ON_USE" to "CODEX_AGENT_PLUGIN_AUTH_POLICY_ON_USE",
        ),
    )
    ordinaryEnum(
        "AgentPluginInstallPolicy",
        "codex_agent_plugin_install_policy_validate",
        "validatesAgentPluginInstallPolicy",
        listOf(
            "AVAILABLE" to "CODEX_AGENT_PLUGIN_INSTALL_POLICY_AVAILABLE",
            "INSTALLED_BY_DEFAULT" to "CODEX_AGENT_PLUGIN_INSTALL_POLICY_INSTALLED_BY_DEFAULT",
            "NOT_AVAILABLE" to "CODEX_AGENT_PLUGIN_INSTALL_POLICY_NOT_AVAILABLE",
        ),
    )
    ordinaryEnum(
        "AgentResolution",
        "codex_agent_resolution_validate",
        "validatesAgentResolution",
        listOf(
            "Default" to "CODEX_AGENT_RESOLUTION_DEFAULT",
            "First" to "CODEX_AGENT_RESOLUTION_FIRST",
            "Preferred" to "CODEX_AGENT_RESOLUTION_PREFERRED",
        ),
    )
    ordinaryEnum(
        "AgentResourceOrigin",
        "codex_agent_resource_origin_validate",
        "validatesAgentResourceOrigin",
        listOf(
            "MANAGED" to "CODEX_AGENT_RESOURCE_ORIGIN_MANAGED",
            "PLUGIN" to "CODEX_AGENT_RESOURCE_ORIGIN_PLUGIN",
            "UNKNOWN" to "CODEX_AGENT_RESOURCE_ORIGIN_UNKNOWN",
            "USER" to "CODEX_AGENT_RESOURCE_ORIGIN_USER",
            "WORKSPACE" to "CODEX_AGENT_RESOURCE_ORIGIN_WORKSPACE",
        ),
    )
    ordinaryEnum(
        "AgentWorkActivity",
        "codex_agent_work_activity_validate",
        "validatesAgentWorkActivity",
        listOf(
            "RUNNING_COMMAND" to "CODEX_AGENT_WORK_ACTIVITY_RUNNING_COMMAND",
            "WRITING_FILES" to "CODEX_AGENT_WORK_ACTIVITY_WRITING_FILES",
        ),
    )
    ordinaryEnum(
        "CodexAuthorizationPurpose",
        "codex_agent_authorization_purpose_validate",
        "validatesCodexAuthorizationPurpose",
        listOf(
            "CHAT_GPT" to "CODEX_AGENT_AUTHORIZATION_PURPOSE_CHAT_GPT",
            "EXTERNAL" to "CODEX_AGENT_AUTHORIZATION_PURPOSE_EXTERNAL",
        ),
    )

    ordinary(
        "AgentFormValue.BooleanValue",
        "constructor",
        "<init>",
        listOf("codex_agent_form_boolean_value_create", "codex_agent_form_boolean_value_destroy"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_VALIDATION_TEST),
        "<init>(kotlin.Boolean){}[0]",
    )
    ordinary(
        "AgentFormValue.BooleanValue",
        "property",
        "value",
        listOf("codex_agent_form_boolean_value_value"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    ordinary(
        "AgentFormValue.Number",
        "constructor",
        "<init>",
        listOf("codex_agent_form_number_value_create", "codex_agent_form_number_value_destroy"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_VALIDATION_TEST),
        "<init>(kotlin.Double){}[0]",
    )
    ordinary(
        "AgentFormValue.Number",
        "property",
        "value",
        listOf("codex_agent_form_number_value_value"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    ordinary(
        "AgentFormValue.Text",
        "constructor",
        "<init>",
        listOf("codex_agent_form_text_value_create", "codex_agent_form_text_value_destroy"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_VALIDATION_TEST),
        "<init>(kotlin.String){}[0]",
    )
    ordinary(
        "AgentFormValue.Text",
        "property",
        "value",
        listOf("codex_agent_form_text_value_value_copy"),
        listOf(C_FORM_HOOK_VALUES_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    add(claim(
        "AgentHookHandler.Agent",
        "object",
        "AgentHookHandler.Agent",
        listOf("codex_agent_hook_handler_agent_acquire", "codex_agent_hook_handler_agent_destroy"),
        publicSymbols = listOf(
            "codex_agent_hook_handler_agent_acquire",
            "codex_agent_hook_handler_agent_destroy",
        ),
        nativeTestIds = listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    ))
    ordinary(
        "AgentHookHandler.Command",
        "constructor",
        "<init>",
        listOf("codex_agent_hook_handler_command_create", "codex_agent_hook_handler_command_destroy"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.Boolean){}[0]",
    )
    ordinary(
        "AgentHookHandler.Command",
        "property",
        "command",
        listOf("codex_agent_hook_handler_command_command_copy"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    ordinary(
        "AgentHookHandler.Command",
        "property",
        "isAsync",
        listOf("codex_agent_hook_handler_command_is_async"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    ordinary(
        "AgentHookHandler.McpTool",
        "constructor",
        "<init>",
        listOf("codex_agent_hook_handler_mcp_tool_create", "codex_agent_hook_handler_mcp_tool_destroy"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String){}[0]",
    )
    ordinary(
        "AgentHookHandler.McpTool",
        "property",
        "server",
        listOf("codex_agent_hook_handler_mcp_tool_server_copy"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    ordinary(
        "AgentHookHandler.McpTool",
        "property",
        "tool",
        listOf("codex_agent_hook_handler_mcp_tool_tool_copy"),
        listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    )
    add(claim(
        "AgentHookHandler.Prompt",
        "object",
        "AgentHookHandler.Prompt",
        listOf("codex_agent_hook_handler_prompt_acquire", "codex_agent_hook_handler_prompt_destroy"),
        publicSymbols = listOf(
            "codex_agent_hook_handler_prompt_acquire",
            "codex_agent_hook_handler_prompt_destroy",
        ),
        nativeTestIds = listOf(C_FORM_HOOK_VARIANTS_TEST, C_FORM_HOOK_HANDLE_TEST),
    ))

    ordinary(
        "AgentInvocation.Plugin",
        "constructor",
        "<init>",
        listOf("codex_agent_invocation_plugin_create", "codex_agent_invocation_plugin_destroy"),
        listOf(C_INVOCATION_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String){}[0]",
    )
    listOf(
        "key" to "codex_agent_invocation_plugin_key_copy",
        "name" to "codex_agent_invocation_plugin_name_copy",
        "uri" to "codex_agent_invocation_plugin_uri_copy",
    ).forEach { (property, symbol) ->
        ordinary("AgentInvocation.Plugin", "property", property, listOf(symbol), listOf(C_INVOCATION_VALUES_TEST))
    }
    ordinary(
        "AgentInvocation.Skill",
        "constructor",
        "<init>",
        listOf("codex_agent_invocation_skill_create", "codex_agent_invocation_skill_destroy"),
        listOf(C_INVOCATION_VALUES_TEST),
        "<init>(kotlin.String;kotlin.String){}[0]",
    )
    listOf(
        "key" to "codex_agent_invocation_skill_key_copy",
        "name" to "codex_agent_invocation_skill_name_copy",
        "path" to "codex_agent_invocation_skill_path_copy",
    ).forEach { (property, symbol) ->
        ordinary("AgentInvocation.Skill", "property", property, listOf(symbol), listOf(C_INVOCATION_VALUES_TEST))
    }
    ordinary(
        "AgentPendingApproval",
        "constructor",
        "<init>",
        listOf("codex_agent_pending_approval_create", "codex_agent_pending_approval_destroy"),
        listOf(C_PENDING_APPROVAL_VALUES_TEST),
        "<init>(kotlin.String;io.github.codex_agent_labs.codexmobile.agent.ConversationId;kotlin.String;kotlin.String){}[0]",
    )
    listOf(
        "conversationId" to "codex_agent_pending_approval_conversation_id",
        "details" to "codex_agent_pending_approval_details_copy",
        "requestId" to "codex_agent_pending_approval_request_id_copy",
        "title" to "codex_agent_pending_approval_title_copy",
    ).forEach { (property, symbol) ->
        ordinary("AgentPendingApproval", "property", property, listOf(symbol), listOf(C_PENDING_APPROVAL_VALUES_TEST))
    }
    ordinary(
        "CodexAuthenticationMethod.ApiKey",
        "constructor",
        "<init>",
        listOf(
            "codex_agent_authentication_method_api_key_create",
            "codex_agent_authentication_method_api_key_destroy",
        ),
        listOf(C_AUTHENTICATION_METHOD_VALUES_TEST),
        "<init>(kotlin.String){}[0]",
    )
    ordinary(
        "CodexAuthenticationMethod.ApiKey",
        "property",
        "value",
        listOf("codex_agent_authentication_method_api_key_value_copy"),
        listOf(C_AUTHENTICATION_METHOD_VALUES_TEST),
    )
    add(claim(
        "CodexAuthenticationMethod.ChatGptBrowser",
        "object",
        "CodexAuthenticationMethod.ChatGptBrowser",
        listOf(
            "codex_agent_authentication_method_chat_gpt_browser_create",
            "codex_agent_authentication_method_chat_gpt_browser_destroy",
        ),
        publicSymbols = listOf(
            "codex_agent_authentication_method_chat_gpt_browser_create",
            "codex_agent_authentication_method_chat_gpt_browser_destroy",
        ),
        nativeTestIds = listOf(C_AUTHENTICATION_METHOD_VALUES_TEST),
    ))
    add(claim(
        "CodexAuthenticationMethod.ChatGptDeviceCode",
        "object",
        "CodexAuthenticationMethod.ChatGptDeviceCode",
        listOf(
            "codex_agent_authentication_method_chat_gpt_device_code_create",
            "codex_agent_authentication_method_chat_gpt_device_code_destroy",
        ),
        publicSymbols = listOf(
            "codex_agent_authentication_method_chat_gpt_device_code_create",
            "codex_agent_authentication_method_chat_gpt_device_code_destroy",
        ),
        nativeTestIds = listOf(C_AUTHENTICATION_METHOD_VALUES_TEST),
    ))

    ordinary(
        "AgentConnector", "constructor", "<init>",
        listOf("codex_agent_connector_create", "codex_agent_connector_destroy"),
        listOf(C_CONNECTOR_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String?;kotlin.Boolean;kotlin.Boolean;" +
            "kotlin.collections.List<kotlin.String>){}[0]",
    )
    listOf(
        "description" to listOf("codex_agent_connector_description_copy"),
        "id" to listOf("codex_agent_connector_id_copy"),
        "installUrl" to listOf(
            "codex_agent_connector_has_install_url",
            "codex_agent_connector_install_url_copy",
        ),
        "isAccessible" to listOf("codex_agent_connector_is_accessible"),
        "isEnabled" to listOf("codex_agent_connector_is_enabled"),
        "name" to listOf("codex_agent_connector_name_copy"),
        "pluginNames" to listOf(
            "codex_agent_connector_plugin_names_count",
            "codex_agent_connector_plugin_names_copy_at",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentConnector", "property", property, symbols, listOf(C_CONNECTOR_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentElicitationValidation", "constructor", "<init>",
        listOf("codex_agent_elicitation_validation_create", "codex_agent_elicitation_validation_destroy"),
        listOf(C_ELICITATION_VALIDATION_LIST_VALUES_TEST, C_ELICITATION_VALIDATION_LIST_VALIDATION_TEST),
        "<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent." +
            "AgentElicitationValidationIssue>){}[0]",
    )
    ordinary(
        "AgentElicitationValidation", "property", "isValid",
        listOf("codex_agent_elicitation_validation_is_valid"),
        listOf(C_ELICITATION_VALIDATION_LIST_VALUES_TEST),
    )
    ordinary(
        "AgentElicitationValidation", "property", "issues",
        listOf(
            "codex_agent_elicitation_validation_issue_count",
            "codex_agent_elicitation_validation_issue_at",
        ),
        listOf(C_ELICITATION_VALIDATION_LIST_VALUES_TEST),
    )

    ordinary(
        "AgentFormValue.TextList", "constructor", "<init>",
        listOf("codex_agent_form_text_list_value_create", "codex_agent_form_text_list_value_destroy"),
        listOf(C_TEXT_LIST_VALUES_TEST, C_TEXT_LIST_VALIDATION_TEST),
        "<init>(kotlin.collections.List<kotlin.String>){}[0]",
    )
    ordinary(
        "AgentFormValue.TextList", "property", "value",
        listOf("codex_agent_form_text_list_value_count", "codex_agent_form_text_list_value_copy_at"),
        listOf(C_TEXT_LIST_VALUES_TEST),
    )

    ordinary(
        "AgentHookActivity", "constructor", "<init>",
        listOf("codex_agent_hook_activity_create", "codex_agent_hook_activity_destroy"),
        listOf(C_HOOK_ACTIVITY_LIST_VALUES_TEST, C_PROGRESS_LIST_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs.codexmobile.agent." +
            "AgentHookRunStatus;kotlin.String?;kotlin.collections.List<kotlin.String>){}[0]",
    )
    listOf(
        "details" to listOf(
            "codex_agent_hook_activity_details_count",
            "codex_agent_hook_activity_detail_copy_at",
        ),
        "eventName" to listOf("codex_agent_hook_activity_event_name_copy"),
        "handlerType" to listOf("codex_agent_hook_activity_handler_type_copy"),
        "id" to listOf("codex_agent_hook_activity_id_copy"),
        "status" to listOf("codex_agent_hook_activity_status"),
        "statusMessage" to listOf(
            "codex_agent_hook_activity_has_status_message",
            "codex_agent_hook_activity_status_message_copy",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentHookActivity", "property", property, symbols, listOf(C_HOOK_ACTIVITY_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentModel", "constructor", "<init>",
        listOf("codex_agent_model_create", "codex_agent_model_destroy"),
        listOf(C_MODEL_LIST_VALUES_TEST, C_PROGRESS_LIST_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.collections.List<kotlin.String>;" +
            "kotlin.String;kotlin.Boolean;kotlin.collections.List<io.github.codex_agent_labs." +
            "codexmobile.agent.AgentServiceTier>;kotlin.String?){}[0]",
    )
    listOf(
        "defaultEffort" to listOf("codex_agent_model_default_effort_copy"),
        "defaultServiceTier" to listOf(
            "codex_agent_model_has_default_service_tier",
            "codex_agent_model_default_service_tier_copy",
        ),
        "description" to listOf("codex_agent_model_description_copy"),
        "displayName" to listOf("codex_agent_model_display_name_copy"),
        "id" to listOf("codex_agent_model_id_copy"),
        "isDefault" to listOf("codex_agent_model_is_default"),
        "serviceTiers" to listOf(
            "codex_agent_model_service_tiers_count",
            "codex_agent_model_service_tier_at",
        ),
        "supportedEfforts" to listOf(
            "codex_agent_model_supported_efforts_count",
            "codex_agent_model_supported_effort_copy_at",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentModel", "property", property, symbols, listOf(C_MODEL_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentPlanProgress", "constructor", "<init>",
        listOf("codex_agent_plan_progress_create", "codex_agent_plan_progress_destroy"),
        listOf(C_PLAN_PROGRESS_LIST_VALUES_TEST, C_PROGRESS_LIST_VALIDATION_TEST),
        "<init>(kotlin.String?;kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent." +
            "AgentPlanStep>){}[0]",
    )
    listOf(
        "explanation" to listOf(
            "codex_agent_plan_progress_has_explanation",
            "codex_agent_plan_progress_explanation_copy",
        ),
        "steps" to listOf(
            "codex_agent_plan_progress_steps_count",
            "codex_agent_plan_progress_step_at",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentPlanProgress", "property", property, symbols, listOf(C_PLAN_PROGRESS_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentPluginCatalog", "constructor", "<init>",
        listOf("codex_agent_plugin_catalog_create", "codex_agent_plugin_catalog_destroy"),
        listOf(C_PLUGIN_CATALOG_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary>;" +
            "kotlin.collections.List<kotlin.String>;io.github.codex_agent_labs.codexmobile.agent." +
            "AgentCatalogFreshness){}[0]",
    )
    listOf(
        "errors" to listOf(
            "codex_agent_plugin_catalog_errors_count",
            "codex_agent_plugin_catalog_errors_copy_at",
        ),
        "freshness" to listOf("codex_agent_plugin_catalog_freshness"),
        "plugins" to listOf(
            "codex_agent_plugin_catalog_plugins_count",
            "codex_agent_plugin_catalog_plugins_at",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentPluginCatalog", "property", property, symbols, listOf(C_PLUGIN_CATALOG_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentPluginDetail", "constructor", "<init>",
        listOf("codex_agent_plugin_detail_create", "codex_agent_plugin_detail_destroy"),
        listOf(C_PLUGIN_DETAIL_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary;kotlin.String;" +
            "kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentPluginSkill>;" +
            "kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentConnector>;" +
            "kotlin.collections.List<kotlin.String>;kotlin.Int){}[0]",
    )
    listOf(
        "connectors" to listOf(
            "codex_agent_plugin_detail_connectors_count",
            "codex_agent_plugin_detail_connectors_at",
        ),
        "description" to listOf("codex_agent_plugin_detail_description_copy"),
        "hookCount" to listOf("codex_agent_plugin_detail_hook_count"),
        "mcpServers" to listOf(
            "codex_agent_plugin_detail_mcp_servers_count",
            "codex_agent_plugin_detail_mcp_servers_copy_at",
        ),
        "skills" to listOf(
            "codex_agent_plugin_detail_skills_count",
            "codex_agent_plugin_detail_skills_at",
        ),
        "summary" to listOf("codex_agent_plugin_detail_summary"),
    ).forEach { (property, symbols) ->
        ordinary("AgentPluginDetail", "property", property, symbols, listOf(C_PLUGIN_DETAIL_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentPluginInstallResult", "constructor", "<init>",
        listOf("codex_agent_plugin_install_result_create", "codex_agent_plugin_install_result_destroy"),
        listOf(C_PLUGIN_DETAIL_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy;" +
            "kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentConnector>;" +
            "kotlin.String?){}[0]",
    )
    listOf(
        "authPolicy" to listOf("codex_agent_plugin_install_result_auth_policy"),
        "connectorsNeedingAuthentication" to listOf(
            "codex_agent_plugin_install_result_connectors_count",
            "codex_agent_plugin_install_result_connectors_at",
        ),
        "message" to listOf(
            "codex_agent_plugin_install_result_has_message",
            "codex_agent_plugin_install_result_message_copy",
        ),
    ).forEach { (property, symbols) ->
        ordinary(
            "AgentPluginInstallResult", "property", property, symbols,
            listOf(C_PLUGIN_DETAIL_LIST_VALUES_TEST),
        )
    }

    ordinary(
        "AgentPluginSummary", "constructor", "<init>",
        listOf("codex_agent_plugin_summary_create", "codex_agent_plugin_summary_destroy"),
        listOf(C_PLUGIN_CATALOG_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference;kotlin.String;" +
            "kotlin.String;kotlin.Boolean;kotlin.Boolean;io.github.codex_agent_labs.codexmobile.agent." +
            "AgentPluginInstallPolicy;io.github.codex_agent_labs.codexmobile.agent.AgentPluginAuthPolicy;" +
            "kotlin.Boolean;kotlin.collections.List<kotlin.String>;kotlin.String?;kotlin.String?;" +
            "kotlin.String?;kotlin.String?){}[0]",
    )
    listOf(
        "authPolicy" to listOf("codex_agent_plugin_summary_auth_policy"),
        "brandColor" to listOf(
            "codex_agent_plugin_summary_has_brand_color",
            "codex_agent_plugin_summary_brand_color_copy",
        ),
        "capabilities" to listOf(
            "codex_agent_plugin_summary_capabilities_count",
            "codex_agent_plugin_summary_capabilities_copy_at",
        ),
        "description" to listOf("codex_agent_plugin_summary_description_copy"),
        "displayName" to listOf("codex_agent_plugin_summary_display_name_copy"),
        "installPolicy" to listOf("codex_agent_plugin_summary_install_policy"),
        "isAvailable" to listOf("codex_agent_plugin_summary_is_available"),
        "isEnabled" to listOf("codex_agent_plugin_summary_is_enabled"),
        "isInstalled" to listOf("codex_agent_plugin_summary_is_installed"),
        "privacyPolicyUrl" to listOf(
            "codex_agent_plugin_summary_has_privacy_policy_url",
            "codex_agent_plugin_summary_privacy_policy_url_copy",
        ),
        "reference" to listOf("codex_agent_plugin_summary_reference"),
        "termsOfServiceUrl" to listOf(
            "codex_agent_plugin_summary_has_terms_of_service_url",
            "codex_agent_plugin_summary_terms_of_service_url_copy",
        ),
        "websiteUrl" to listOf(
            "codex_agent_plugin_summary_has_website_url",
            "codex_agent_plugin_summary_website_url_copy",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentPluginSummary", "property", property, symbols, listOf(C_PLUGIN_CATALOG_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentSkill", "constructor", "<init>",
        listOf("codex_agent_skill_create", "codex_agent_skill_destroy"),
        listOf(C_SKILL_CATALOG_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs." +
            "codexmobile.agent.AgentSkillScope;kotlin.Boolean;kotlin.String?;" +
            "kotlin.collections.List<kotlin.String>;kotlin.Boolean;io.github.codex_agent_labs." +
            "codexmobile.agent.AgentResourceOrigin){}[0]",
    )
    listOf(
        "brandColor" to listOf("codex_agent_skill_has_brand_color", "codex_agent_skill_brand_color_copy"),
        "canUninstall" to listOf("codex_agent_skill_can_uninstall"),
        "dependencies" to listOf(
            "codex_agent_skill_dependencies_count",
            "codex_agent_skill_dependencies_copy_at",
        ),
        "description" to listOf("codex_agent_skill_description_copy"),
        "displayName" to listOf("codex_agent_skill_display_name_copy"),
        "isEnabled" to listOf("codex_agent_skill_is_enabled"),
        "name" to listOf("codex_agent_skill_name_copy"),
        "origin" to listOf("codex_agent_skill_origin"),
        "path" to listOf("codex_agent_skill_path_copy"),
        "scope" to listOf("codex_agent_skill_scope"),
    ).forEach { (property, symbols) ->
        ordinary("AgentSkill", "property", property, symbols, listOf(C_SKILL_CATALOG_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentSkillCatalog", "constructor", "<init>",
        listOf("codex_agent_skill_catalog_create", "codex_agent_skill_catalog_destroy"),
        listOf(C_SKILL_CATALOG_LIST_VALUES_TEST, C_RESOURCE_LIST_VALIDATION_TEST),
        "<init>(kotlin.collections.List<io.github.codex_agent_labs.codexmobile.agent.AgentSkill>;" +
            "kotlin.collections.List<kotlin.String>){}[0]",
    )
    listOf(
        "errors" to listOf(
            "codex_agent_skill_catalog_errors_count",
            "codex_agent_skill_catalog_errors_copy_at",
        ),
        "skills" to listOf(
            "codex_agent_skill_catalog_skills_count",
            "codex_agent_skill_catalog_skills_at",
        ),
    ).forEach { (property, symbols) ->
        ordinary("AgentSkillCatalog", "property", property, symbols, listOf(C_SKILL_CATALOG_LIST_VALUES_TEST))
    }

    ordinary(
        "AgentTurnProgress", "constructor", "<init>",
        listOf("codex_agent_turn_progress_create", "codex_agent_turn_progress_destroy"),
        listOf(C_TURN_PROGRESS_LIST_VALUES_TEST, C_PROGRESS_LIST_VALIDATION_TEST),
        "<init>(kotlin.String;kotlin.String;kotlin.String;kotlin.String;io.github.codex_agent_labs." +
            "codexmobile.agent.AgentPlanProgress?;kotlin.String;kotlin.Int?;io.github.codex_agent_labs." +
            "codexmobile.agent.AgentWorkActivity?;kotlin.collections.List<io.github.codex_agent_labs." +
            "codexmobile.agent.AgentHookActivity>;kotlin.Boolean){}[0]",
    )
    listOf(
        "commentary" to listOf("codex_agent_turn_progress_commentary_copy"),
        "hookActivities" to listOf(
            "codex_agent_turn_progress_hook_activities_count",
            "codex_agent_turn_progress_hook_activity_at",
        ),
        "isTruncated" to listOf("codex_agent_turn_progress_is_truncated"),
        "plan" to listOf("codex_agent_turn_progress_plan_copy"),
        "planProgress" to listOf(
            "codex_agent_turn_progress_has_plan_progress",
            "codex_agent_turn_progress_plan_progress",
        ),
        "reasoning" to listOf("codex_agent_turn_progress_reasoning_copy"),
        "shellExitCode" to listOf("codex_agent_turn_progress_shell_exit_code"),
        "shellOutput" to listOf("codex_agent_turn_progress_shell_output_copy"),
        "text" to listOf("codex_agent_turn_progress_text_copy"),
        "workActivity" to listOf("codex_agent_turn_progress_work_activity"),
    ).forEach { (property, symbols) ->
        ordinary("AgentTurnProgress", "property", property, symbols, listOf(C_TURN_PROGRESS_LIST_VALUES_TEST))
    }
}.sortedWith(compareBy(CAbiBootstrapClaimSpec::owner, CAbiBootstrapClaimSpec::kind, CAbiBootstrapClaimSpec::abi))

internal fun deriveCAbiBootstrapClaims(
    canonicalKeys: List<String>,
    headerText: String,
    consumerText: String,
    exportedSymbols: Set<String>,
    passedNativeTestIds: Set<String>,
    claimSpecs: List<CAbiBootstrapClaimSpec> = cAbiBootstrapClaimSpecs,
): List<CAbiBootstrapClaim> {
    check(canonicalKeys.size == C_ABI_CANONICAL_CAPABILITY_COUNT &&
        canonicalKeys.size == canonicalKeys.distinct().size && canonicalKeys == canonicalKeys.sorted()) {
        "C ABI bootstrap requires the exact sorted 556-capability canonical inventory"
    }
    check(claimSpecs.size == C_ABI_BOOTSTRAP_CAPABILITY_COUNT &&
        claimSpecs.distinctBy { Triple(it.owner, it.kind, it.abi) }.size ==
        C_ABI_BOOTSTRAP_CAPABILITY_COUNT) {
        "C ABI bootstrap claim specifications are missing or duplicated"
    }
    val records = canonicalKeys.groupBy(::cAbiApiIdentity)
    val claims = claimSpecs.map { spec ->
        val identity = Triple(spec.owner, spec.kind, spec.abi)
        val candidates = records[identity].orEmpty().filter { key ->
            spec.canonicalSignatureReference?.let(key::contains) ?: true
        }
        check(candidates.size == 1) {
            "Missing or ambiguous exact canonical C ABI capability $identity " +
                "signature=${spec.canonicalSignatureReference}: $candidates"
        }
        val key = candidates.single()
        listOf(spec.headerReferences, spec.consumerReferences, spec.publicSymbols, spec.nativeTestIds).forEach {
            check(it.isNotEmpty() && it == it.distinct()) { "C ABI claim contains empty or duplicate evidence: $key" }
        }
        spec.headerReferences.forEach { reference ->
            check(headerText.containsCReference(reference)) {
                "Missing C ABI public header reference $reference for $key"
            }
        }
        spec.consumerReferences.forEach { reference ->
            check(consumerText.containsCReference(reference)) {
                "Missing compiled C consumer reference $reference for $key"
            }
        }
        spec.publicSymbols.forEach { symbol ->
            check(symbol in exportedSymbols) { "Missing exported C ABI symbol $symbol for $key" }
        }
        spec.nativeTestIds.forEach { testId ->
            check(testId in passedNativeTestIds) { "Missing passed Native C ABI test $testId for $key" }
        }
        CAbiBootstrapClaim(
            capabilityKey = key,
            headerReferences = spec.headerReferences.sorted(),
            consumerReferences = spec.consumerReferences.sorted(),
            publicSymbols = spec.publicSymbols.sorted(),
            nativeTestIds = spec.nativeTestIds.sorted(),
        )
    }.sortedBy(CAbiBootstrapClaim::capabilityKey)
    val keys = claims.map(CAbiBootstrapClaim::capabilityKey)
    check(keys.size == C_ABI_BOOTSTRAP_CAPABILITY_COUNT && keys.size == keys.distinct().size) {
        "C ABI bootstrap capability selection is not exact"
    }
    check(keys.sortedNewlineSha256() == C_ABI_BOOTSTRAP_CAPABILITY_SHA256) {
        "C ABI bootstrap capability signature drift: ${keys.sortedNewlineSha256()}"
    }
    return claims
}

private fun cAbiApiIdentity(key: String): Triple<String, String, String> {
    val ownerPrefix = "common|owner="
    val kindMarker = "|kind="
    val abiMarker = "|abi="
    check(key.startsWith(ownerPrefix)) { "Invalid canonical C ABI key owner: $key" }
    val kindIndex = key.indexOf(kindMarker, ownerPrefix.length)
    val abiIndex = key.indexOf(abiMarker, kindIndex + kindMarker.length)
    val abiEnd = key.indexOf('|', abiIndex + abiMarker.length)
    check(kindIndex > ownerPrefix.length && abiIndex > kindIndex && abiEnd > abiIndex) {
        "Invalid canonical C ABI key shape: $key"
    }
    return Triple(
        key.substring(ownerPrefix.length, kindIndex),
        key.substring(kindIndex + kindMarker.length, abiIndex),
        key.substring(abiIndex + abiMarker.length, abiEnd),
    )
}

private fun List<String>.sortedNewlineSha256(): String = MessageDigest.getInstance("SHA-256")
    .digest(sorted().joinToString(separator = "", transform = { "$it\n" }).encodeToByteArray())
    .joinToString("") { byte -> "%02x".format(byte) }

private fun exactExportPolicy(file: File): Set<String> {
    check(file.releaseDigest() == C_ABI_MACOS_EXPORTS_SHA256) { "Reviewed macOS C ABI export policy drift" }
    val rows = file.readLines().filter(String::isNotBlank)
    check(rows.size == 323 && rows == rows.sorted() && rows.size == rows.distinct().size &&
        rows.all { it.startsWith("_codex_agent_") }) {
        "macOS C ABI export policy must contain the exact sorted 323-symbol inventory"
    }
    return rows.mapTo(sortedSetOf()) { it.removePrefix("_") }
}

private fun String.containsCReference(reference: String): Boolean = Regex(
    "(?<![A-Za-z0-9_])${Regex.escape(reference)}(?![A-Za-z0-9_])",
).containsMatchIn(this)

private fun normalizedCodexSymbols(output: String): Set<String> {
    val symbols = output.lineSequence()
    .map(String::trim)
    .filter(String::isNotEmpty)
    .map { it.substringAfterLast(' ').removePrefix("_") }
    .filter { it.startsWith("codex_agent_") }
    .toList()
    check(symbols.size == symbols.distinct().size) { "Duplicated C ABI symbols in tool output: $symbols" }
    return symbols.toCollection(sortedSetOf())
}

@DisableCachingByDefault(because = "Compiles and executes consumers with the installed macOS toolchain")
abstract class GenerateCAbiBootstrapEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalApiReport: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val reviewedHeader: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val cinteropDefinition: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val exportPolicy: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val foundationCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val foundationCppConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lifecycleCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val lifecycleCppConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val conversationValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val configurationValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val resourceValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val ordinaryEnumsCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val formHookValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val invocationAuthValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val progressListValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val resourceListValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val listLeafValuesCConsumer: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val releaseLibrary: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val generatedHeader: RegularFileProperty

    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val nativeTestExecutable: RegularFileProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeTestResults: DirectoryProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeMainSources: DirectoryProperty

    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nativeTestSources: DirectoryProperty

    @get:LocalState abstract val consumerOutputDirectory: DirectoryProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        check(System.getProperty("os.name").lowercase().contains("mac") &&
            System.getProperty("os.arch").lowercase() in setOf("aarch64", "arm64")) {
            "C ABI bootstrap evidence requires a macOS Arm64 host"
        }

        val canonical = readCrossLanguageCanonicalApiEvidence(
            canonicalApiReport.get().asFile,
            canonicalCoverageReceipt.get().asFile,
        )
        val header = reviewedHeader.get().asFile.also {
            check(it.releaseDigest() == C_ABI_HEADER_SHA256) { "Reviewed C ABI header drift" }
        }
        val cinterop = cinteropDefinition.get().asFile.also {
            check(it.releaseDigest() == C_ABI_CINTEROP_SHA256) { "Reviewed C ABI cinterop definition drift" }
        }
        val exports = exactExportPolicy(exportPolicy.get().asFile)
        val foundationC = foundationCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_FOUNDATION_C_SHA256) { "Reviewed C foundation consumer drift" }
        }
        val foundationCpp = foundationCppConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_FOUNDATION_CPP_SHA256) { "Reviewed C++ foundation consumer drift" }
        }
        val lifecycleC = lifecycleCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_LIFECYCLE_C_SHA256) { "Reviewed C lifecycle consumer drift" }
        }
        val lifecycleCpp = lifecycleCppConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_LIFECYCLE_CPP_SHA256) { "Reviewed C++ lifecycle consumer drift" }
        }
        val conversationValuesC = conversationValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_CONVERSATION_VALUES_C_SHA256) {
                "Reviewed C conversation-values consumer drift"
            }
        }
        val configurationValuesC = configurationValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_CONFIGURATION_VALUES_C_SHA256) {
                "Reviewed C configuration-values consumer drift"
            }
        }
        val resourceValuesC = resourceValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_RESOURCE_VALUES_C_SHA256) {
                "Reviewed C resource-values consumer drift"
            }
        }
        val ordinaryEnumsC = ordinaryEnumsCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_ORDINARY_ENUMS_C_SHA256) {
                "Reviewed C ordinary-enums consumer drift"
            }
        }
        val formHookValuesC = formHookValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_FORM_HOOK_VALUES_C_SHA256) {
                "Reviewed C form-hook-values consumer drift"
            }
        }
        val invocationAuthValuesC = invocationAuthValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_INVOCATION_AUTH_VALUES_C_SHA256) {
                "Reviewed C invocation-auth-values consumer drift"
            }
        }
        val progressListValuesC = progressListValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_PROGRESS_LIST_VALUES_C_SHA256) {
                "Reviewed C progress-list-values consumer drift"
            }
        }
        val resourceListValuesC = resourceListValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_RESOURCE_LIST_VALUES_C_SHA256) {
                "Reviewed C resource-list-values consumer drift"
            }
        }
        val listLeafValuesC = listLeafValuesCConsumer.get().asFile.also {
            check(it.releaseDigest() == C_ABI_LIST_LEAF_VALUES_C_SHA256) {
                "Reviewed C list-leaf-values consumer drift"
            }
        }
        val library = releaseLibrary.get().asFile
        val generated = generatedHeader.get().asFile
        val nativeExecutable = nativeTestExecutable.get().asFile
        listOf(library, generated, nativeExecutable).forEach {
            check(it.isFile && !Files.isSymbolicLink(it.toPath()) && it.length() > 0L) {
                "C ABI bootstrap artifact is missing, empty, or symbolic: $it"
            }
        }

        val testReports = nativeTestResults.get().asFile.listFiles()
            .orEmpty().filter { it.isFile && it.extension == "xml" && ".capi." in it.name }.sorted()
        check(testReports.isNotEmpty()) { "C ABI Native JUnit reports are missing" }
        val nativeTests = testReports.flatMap(::readCanonicalTestReport)
        val duplicateTests = nativeTests.groupingBy(CanonicalTestResult::testId).eachCount()
            .filterValues { it != 1 }.keys.sorted()
        check(duplicateTests.isEmpty()) { "Duplicate C ABI Native test identities: $duplicateTests" }
        check(nativeTests.all { it.status == CanonicalTestStatus.PASSED }) {
            "C ABI Native test inventory contains skipped or failed tests"
        }
        val passedTests = nativeTests.mapTo(sortedSetOf(), CanonicalTestResult::testId)

        val work = consumerOutputDirectory.get().asFile
        check(work.deleteRecursively() || !work.exists()) { "Could not clear C ABI consumer work directory" }
        check(work.mkdirs()) { "Could not create C ABI consumer work directory" }
        val clang = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "--find", "clang")).trim()
        val clangCpp = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "--find", "clang++")).trim()
        val sdk = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"),
        ).trim()
        val clangVersion = processes.captureReleaseProcess(listOf(clang, "--version")).trim()
        val include = header.parentFile.absolutePath
        val rpath = library.parentFile.absolutePath
        val consumers = listOf(
            compileConsumer("c11-foundation", clang, "c11", foundationC, work, include, library, rpath, sdk, true),
            compileConsumer("c11-lifecycle", clang, "c11", lifecycleC, work, include, library, rpath, sdk, true),
            compileConsumer(
                "c++17-foundation", clangCpp, "c++17", foundationCpp,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c++17-lifecycle", clangCpp, "c++17", lifecycleCpp,
                work, include, library, rpath, sdk, false,
            ),
            compileConsumer(
                "c11-conversation-values", clang, "c11", conversationValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-configuration-values", clang, "c11", configurationValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-resource-values", clang, "c11", resourceValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-ordinary-enums", clang, "c11", ordinaryEnumsC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-form-hook-values", clang, "c11", formHookValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-invocation-auth-values", clang, "c11", invocationAuthValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-progress-list-values", clang, "c11", progressListValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-resource-list-values", clang, "c11", resourceListValuesC,
                work, include, library, rpath, sdk, true,
            ),
            compileConsumer(
                "c11-list-leaf-values", clang, "c11", listLeafValuesC,
                work, include, library, rpath, sdk, true,
            ),
        )

        val defined = normalizedCodexSymbols(
            processes.captureReleaseProcess(listOf("/usr/bin/nm", "-gU", library.absolutePath)),
        )
        check(defined == exports) { "Dylib/export-policy mismatch: missing=${exports - defined} extra=${defined - exports}" }
        val cConsumerImports = consumers.filter { it.source.extension == "c" }
            .flatMapTo(sortedSetOf()) { consumer ->
                normalizedCodexSymbols(
                    processes.captureReleaseProcess(listOf("/usr/bin/nm", "-u", consumer.artifact.absolutePath)),
                )
            }
        check(cConsumerImports == exports) {
            "C consumer import union mismatch: missing=${exports - cConsumerImports} " +
                "extra=${cConsumerImports - exports}"
        }
        val fileIdentity = processes.captureReleaseProcess(
            listOf("/usr/bin/file", "-b", library.absolutePath),
        ).trim()
        check(fileIdentity == "Mach-O 64-bit dynamically linked shared library arm64") {
            "C ABI release library is not Mach-O Arm64: $fileIdentity"
        }
        val installNames = processes.captureReleaseProcess(
            listOf("/usr/bin/otool", "-D", library.absolutePath),
        )
            .lineSequence().map(String::trim).filter(String::isNotEmpty).drop(1).toList()
        check(installNames == listOf("@rpath/libcodex_agent.dylib")) {
            "Unexpected C ABI dylib install name: $installNames"
        }
        val linkedIdentity = processes.captureReleaseProcess(
            listOf("/usr/bin/otool", "-L", library.absolutePath),
        ).lineSequence().map(String::trim).firstOrNull { it.startsWith("@rpath/libcodex_agent.dylib ") }
        check(linkedIdentity ==
            "@rpath/libcodex_agent.dylib (compatibility version 1.0.0, current version 1.4.0)") {
            "Unexpected C ABI dylib loader versions: $linkedIdentity"
        }

        val claims = deriveCAbiBootstrapClaims(
            canonical.memberKeys,
            header.readText(),
            listOf(
                lifecycleC,
                conversationValuesC,
                configurationValuesC,
                resourceValuesC,
                ordinaryEnumsC,
                formHookValuesC,
                invocationAuthValuesC,
                progressListValuesC,
                resourceListValuesC,
                listLeafValuesC,
            )
                .joinToString("\n") { it.readText() },
            exports,
            passedTests,
        )
        val observedKeys = claims.map(CAbiBootstrapClaim::capabilityKey)
        val missingKeys = (canonical.memberKeys.toSet() - observedKeys.toSet()).sorted()
        check(missingKeys.size == C_ABI_CANONICAL_CAPABILITY_COUNT - C_ABI_BOOTSTRAP_CAPABILITY_COUNT &&
            observedKeys.toSet().intersect(missingKeys.toSet()).isEmpty() &&
            (observedKeys + missingKeys).sorted() == canonical.memberKeys) {
            "C ABI bootstrap observed/missing partition is not exact"
        }

        val report = buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("protocol", JsonPrimitive(C_ABI_BOOTSTRAP_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed"))
            put("milestone", JsonPrimitive("D096"))
            put("language", JsonPrimitive("c-abi"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
                put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
                put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
                put("capabilityCount", JsonPrimitive(canonical.memberKeys.size))
                put("observedCapabilityCount", JsonPrimitive(observedKeys.size))
                put("observedCapabilitySha256", JsonPrimitive(observedKeys.sortedNewlineSha256()))
                put("observedCapabilityKeys", JsonArray(observedKeys.map(::JsonPrimitive)))
                put("missingCapabilityKeys", JsonArray(missingKeys.map(::JsonPrimitive)))
            })
            put("toolchain", buildJsonObject {
                put("clang", JsonPrimitive(clang))
                put("clangCpp", JsonPrimitive(clangCpp))
                put("clangVersion", JsonPrimitive(clangVersion))
                put("macosSdk", JsonPrimitive(sdk))
            })
            put("artifacts", buildJsonObject {
                put("reviewedHeaderSha256", JsonPrimitive(header.releaseDigest()))
                put("cinteropDefinitionSha256", JsonPrimitive(cinterop.releaseDigest()))
                put("exportPolicySha256", JsonPrimitive(exportPolicy.get().asFile.releaseDigest()))
                put("generatedHeaderSha256", JsonPrimitive(generated.releaseDigest()))
                put("releaseLibrarySha256", JsonPrimitive(library.releaseDigest()))
                put("nativeTestExecutableSha256", JsonPrimitive(nativeExecutable.releaseDigest()))
                put("nativeMainSourcesSha256", JsonPrimitive(nativeMainSources.get().asFile.crossLanguageTreeDigest()))
                put("nativeTestSourcesSha256", JsonPrimitive(nativeTestSources.get().asFile.crossLanguageTreeDigest()))
                put("nativeTestResultsSha256", JsonPrimitive(nativeTestResults.get().asFile.crossLanguageTreeDigest()))
                put("fileIdentity", JsonPrimitive(fileIdentity))
                put("installName", JsonPrimitive(installNames.single()))
            })
            put("compilerConsumers", buildJsonArray {
                consumers.forEach { consumer ->
                    add(buildJsonObject {
                        put("id", JsonPrimitive(consumer.id))
                        put("sourceSha256", JsonPrimitive(consumer.source.releaseDigest()))
                        put("artifactSha256", JsonPrimitive(consumer.artifact.releaseDigest()))
                        put("executed", JsonPrimitive(consumer.executed))
                    })
                }
            })
            put("linkedPublicSymbols", JsonArray(exports.sorted().map(::JsonPrimitive)))
            put("nativeTests", buildJsonArray {
                nativeTests.sortedBy(CanonicalTestResult::testId).forEach { test ->
                    add(buildJsonObject {
                        put("testId", JsonPrimitive(test.testId))
                        put("status", JsonPrimitive("passed"))
                    })
                }
            })
            put("claims", buildJsonArray {
                claims.forEach { claim ->
                    add(buildJsonObject {
                        put("capabilityKey", JsonPrimitive(claim.capabilityKey))
                        put("headerReferences", JsonArray(claim.headerReferences.map(::JsonPrimitive)))
                        put("consumerReferences", JsonArray(claim.consumerReferences.map(::JsonPrimitive)))
                        put("publicSymbols", JsonArray(claim.publicSymbols.map(::JsonPrimitive)))
                        put("nativeTestIds", JsonArray(claim.nativeTestIds.map(::JsonPrimitive)))
                    })
                }
            })
        }
        output.atomicWriteJson(report)
        check(output.readText() == releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), report) + "\n") {
            "C ABI bootstrap evidence is not canonically encoded"
        }
    }

    private fun compileConsumer(
        id: String,
        compiler: String,
        standard: String,
        source: File,
        work: File,
        include: String,
        library: File,
        rpath: String,
        sdk: String,
        execute: Boolean,
    ): CompiledCAbiConsumer {
        val artifact = work.resolve(if (execute) id else "$id.o")
        val command = mutableListOf(
            compiler,
            "-std=$standard",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-pedantic",
            "-arch",
            "arm64",
            "-isysroot",
            sdk,
            "-I$include",
            source.absolutePath,
        )
        if (execute) {
            command += listOf(library.absolutePath, "-Wl,-rpath,$rpath", "-o", artifact.absolutePath)
        } else {
            command += listOf("-c", "-o", artifact.absolutePath)
        }
        processes.captureReleaseProcess(command)
        check(artifact.isFile && artifact.length() > 0L) { "C ABI consumer artifact is empty: $id" }
        if (execute) processes.captureReleaseProcess(listOf(artifact.absolutePath))
        return CompiledCAbiConsumer(id, source, artifact, execute)
    }
}

private data class CompiledCAbiConsumer(
    val id: String,
    val source: File,
    val artifact: File,
    val executed: Boolean,
)
