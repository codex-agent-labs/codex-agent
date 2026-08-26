import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

internal const val APPLE_BINDING_EVIDENCE_PROTOCOL = "codex-agent-apple-binding-evidence-v1"
internal const val APPLE_BINDING_CANONICAL_CAPABILITY_COUNT = 556

private const val appleXCTestProtocol = "codex-agent-apple-xctest-v1"
private const val appleFailureConstructorUsr =
    "$APPLE_CODEX_FAILURE_OWNER_USR(im)initWithCode:message:isRecoverable:"
private const val appleFailureCodeUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)code"
private const val appleFailureRecoverableUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)isRecoverable"
private const val appleFailureMessageUsr = "$APPLE_CODEX_FAILURE_OWNER_USR(py)message"
private const val appleConversationIdConstructorUsr = "$APPLE_CONVERSATION_ID_OWNER_USR(im)initWithValue:"
private const val appleConversationIdValueUsr = "$APPLE_CONVERSATION_ID_OWNER_USR(py)value"
private const val appleApprovalAcceptUsr = "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)accept"
private const val appleApprovalDeclineUsr = "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)decline"
private const val appleCollaborationDefaultUsr = "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)default_"
private const val appleCollaborationPlanUsr = "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)plan"
private const val appleMessageRoleUserUsr = "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)user"
private const val appleMessageRoleAssistantUsr = "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)assistant"
private const val appleInstallationScopeUserUsr = "$APPLE_INSTALLATION_SCOPE_OWNER_USR(cpy)user"
private const val appleInstallationScopeWorkspaceUsr = "$APPLE_INSTALLATION_SCOPE_OWNER_USR(cpy)workspace"
private const val appleMcpEnvironmentLocalUsr = "$APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR(cpy)local"
private const val appleMcpEnvironmentRemoteUsr = "$APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR(cpy)remote"
private const val appleAuthorizationChatGptUsr =
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)chatGptValue:"
private const val appleAuthorizationExternalUsr =
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)externalValue:"
private const val appleAuthorizationValueUsr = "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)value"
private const val appleAuthorizationPurposeUsr = "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)purpose"
private const val swiftFailureTest =
    "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()"
private const val objectiveCFailureTest =
    "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()"


private const val appleCanonicalPackage = "io.github.codex_agent_labs.codexmobile.agent"
private const val appleCanonicalAbiPackage = "io.github.codex_agent_labs.codexmobile.agent"

private fun appleOwnerUsr(objectiveCName: String): String = "c:objc(cs)$objectiveCName"

private fun appleClassType(
    canonicalOwner: String,
    swiftName: String,
    objectiveCName: String,
    swiftAst: String,
    nullable: Boolean = false,
) = AppleOrdinaryType(
    "$appleCanonicalPackage/$canonicalOwner${if (nullable) "?" else "!!"}",
    "$appleCanonicalAbiPackage.$canonicalOwner${if (nullable) "?" else ""}",
    "$swiftName${if (nullable) "?" else ""}",
    appleOwnerUsr(objectiveCName),
    swiftAst,
    "$objectiveCName *",
    appleOwnerUsr(objectiveCName),
)

private val appleString = AppleOrdinaryType(
    "kotlin/String!!", "kotlin.String", "String", "s:SS", "\$sSSD",
    "NSString *", "c:objc(cs)NSString",
)
private val appleNullableString = AppleOrdinaryType(
    "kotlin/String?", "kotlin.String?", "String?", "s:SS", "\$sSSSgD",
    "NSString *", "c:objc(cs)NSString",
)
private val appleBoolean = AppleOrdinaryType(
    "kotlin/Boolean!!", "kotlin.Boolean", "Bool", "s:Sb", "\$sSbD",
    "BOOL", "c:@T@BOOL",
)
private val appleDouble = AppleOrdinaryType(
    "kotlin/Double!!", "kotlin.Double", "Double", "s:Sd", "\$sSdD",
    "double", "c:d",
)
private val appleInt = AppleOrdinaryType(
    "kotlin/Int!!", "kotlin.Int", "Int32", "s:s5Int32V", "\$ss5Int32VD",
    "int32_t", "c:@T@int32_t",
)
private val appleLong = AppleOrdinaryType(
    "kotlin/Long!!", "kotlin.Long", "Int64", "s:s5Int64V", "\$ss5Int64VD",
    "int64_t", "c:@T@int64_t",
)
private val appleNullableInt = AppleOrdinaryType(
    "kotlin/Int?", "kotlin.Int?", "KotlinInt?", "c:objc(cs)CodexAgentInt",
    "\$sSo13CodexAgentIntCSgD", "CodexAgentInt *", "c:objc(cs)CodexAgentInt",
)
private val appleNullableLong = AppleOrdinaryType(
    "kotlin/Long?", "kotlin.Long?", "KotlinLong?", "c:objc(cs)CodexAgentLong",
    "\$sSo14CodexAgentLongCSgD", "CodexAgentLong *", "c:objc(cs)CodexAgentLong",
)
private val appleNullableDouble = AppleOrdinaryType(
    "kotlin/Double?", "kotlin.Double?", "KotlinDouble?", "c:objc(cs)CodexAgentDouble",
    "\$sSo16CodexAgentDoubleCSgD", "CodexAgentDouble *", "c:objc(cs)CodexAgentDouble",
)
private val appleConversationIdType = appleClassType(
    "ConversationId", "ConversationId", "CodexAgentConversationId", "\$sSo24CodexAgentConversationIdCD",
)
private val appleElicitationType = appleClassType(
    "AgentElicitation", "AgentElicitation", "CodexAgentAgentElicitation",
    "\$sSo010CodexAgentB11ElicitationCD",
)
private val appleApprovalPresetType = appleClassType(
    "AgentApprovalPreset", "AgentApprovalPreset", "CodexAgentAgentApprovalPreset",
    "\$sSo010CodexAgentB14ApprovalPresetCD",
)
private val appleNullableMcpEnvironmentSourceType = appleClassType(
    "AgentMcpEnvironmentSource", "AgentMcpEnvironmentSource", "CodexAgentAgentMcpEnvironmentSource",
    "\$sSo010CodexAgentB20McpEnvironmentSourceCSgD", nullable = true,
)
private val appleElicitationValidationReasonType = appleClassType(
    "AgentElicitationValidationReason", "AgentElicitationValidationReason",
    "CodexAgentAgentElicitationValidationReason", "\$sSo010CodexAgentB27ElicitationValidationReasonCD",
)
private val applePlanStepStatusType = appleClassType(
    "AgentPlanStepStatus", "AgentPlanStepStatus", "CodexAgentAgentPlanStepStatus",
    "\$sSo010CodexAgentB14PlanStepStatusCD",
)
private val appleNullableMcpToolApprovalType = appleClassType(
    "AgentMcpToolApproval", "AgentMcpToolApproval", "CodexAgentAgentMcpToolApproval",
    "\$sSo010CodexAgentB15McpToolApprovalCSgD", nullable = true,
)
private val appleCatalogFreshnessType = appleClassType(
    "AgentCatalogFreshness", "AgentCatalogFreshness", "CodexAgentAgentCatalogFreshness",
    "\$sSo010CodexAgentB16CatalogFreshnessCD",
)
private val applePluginAuthPolicyType = appleClassType(
    "AgentPluginAuthPolicy", "AgentPluginAuthPolicy", "CodexAgentAgentPluginAuthPolicy",
    "\$sSo010CodexAgentB16PluginAuthPolicyCD",
)
private val applePluginInstallPolicyType = appleClassType(
    "AgentPluginInstallPolicy", "AgentPluginInstallPolicy", "CodexAgentAgentPluginInstallPolicy",
    "\$sSo010CodexAgentB19PluginInstallPolicyCD",
)
private val applePluginReferenceType = appleClassType(
    "AgentPluginReference", "AgentPluginReference", "CodexAgentAgentPluginReference",
    "\$sSo010CodexAgentB15PluginReferenceCD",
)
private val applePluginSummaryType = appleClassType(
    "AgentPluginSummary", "AgentPluginSummary", "CodexAgentAgentPluginSummary",
    "\$sSo010CodexAgentB13PluginSummaryCD",
)
private val appleSkillScopeType = appleClassType(
    "AgentSkillScope", "AgentSkillScope", "CodexAgentAgentSkillScope",
    "\$sSo010CodexAgentB10SkillScopeCD",
)
private val appleResourceOriginType = appleClassType(
    "AgentResourceOrigin", "AgentResourceOrigin", "CodexAgentAgentResourceOrigin",
    "\$sSo010CodexAgentB14ResourceOriginCD",
)
private val appleMcpAuthStatusType = appleClassType(
    "AgentMcpAuthStatus", "AgentMcpAuthStatus", "CodexAgentAgentMcpAuthStatus",
    "\$sSo010CodexAgentB13McpAuthStatusCD",
)
private val appleNullableMcpServerConfigurationType = appleClassType(
    "AgentMcpServerConfiguration", "AgentMcpServerConfiguration", "CodexAgentAgentMcpServerConfiguration",
    "\$sSo010CodexAgentB22McpServerConfigurationCSgD", nullable = true,
)
private val appleMcpServerType = appleClassType(
    "AgentMcpServer", "AgentMcpServer", "CodexAgentAgentMcpServer",
    "\$sSo010CodexAgentB9McpServerCD",
)
private val appleWorkspaceType = appleClassType(
    "CodexWorkspace", "CodexWorkspace", "CodexAgentCodexWorkspace", "\$sSo010CodexAgentA9WorkspaceCD",
)
private val appleWorkspaceSelectionReasonType = appleClassType(
    "CodexWorkspaceSelectionReason", "CodexWorkspaceSelectionReason",
    "CodexAgentCodexWorkspaceSelectionReason", "\$sSo010CodexAgentA24WorkspaceSelectionReasonCD",
)
private val appleFormFieldType = appleClassType(
    "AgentFormFieldType", "AgentFormFieldType", "CodexAgentAgentFormFieldType",
    "\$sSo010CodexAgentB13FormFieldTypeCD",
)
private val appleNullableFormStringFormatType = appleClassType(
    "AgentFormStringFormat", "AgentFormStringFormat", "CodexAgentAgentFormStringFormat",
    "\$sSo010CodexAgentB16FormStringFormatCSgD", nullable = true,
)
private val appleNullableFormValueType = AppleOrdinaryType(
    "$appleCanonicalPackage/AgentFormValue?", "$appleCanonicalAbiPackage.AgentFormValue?",
    "(any AgentFormValue)?", "c:objc(pl)CodexAgentAgentFormValue",
    "\$sSo010CodexAgentB9FormValue_pSgD", "id<CodexAgentAgentFormValue>",
    "c:Qoobjc(pl)CodexAgentAgentFormValue",
)
private val appleHookHandlerType = AppleOrdinaryType(
    "$appleCanonicalPackage/AgentHookHandler!!", "$appleCanonicalAbiPackage.AgentHookHandler",
    "any AgentHookHandler", "c:objc(pl)CodexAgentAgentHookHandler",
    "\$sSo010CodexAgentB11HookHandler_pD", "id<CodexAgentAgentHookHandler>",
    "c:Qoobjc(pl)CodexAgentAgentHookHandler",
)
private val appleHookTrustStatusType = appleClassType(
    "AgentHookTrustStatus", "AgentHookTrustStatus", "CodexAgentAgentHookTrustStatus",
    "\$sSo010CodexAgentB15HookTrustStatusCD",
)
private val appleHookRunStatusType = appleClassType(
    "AgentHookRunStatus", "AgentHookRunStatus", "CodexAgentAgentHookRunStatus",
    "\$sSo010CodexAgentB13HookRunStatusCD",
)
private val appleConnectorType = appleClassType(
    "AgentConnector", "AgentConnector", "CodexAgentAgentConnector", "\$sSo010CodexAgentB9ConnectorCD",
)
private val appleNullablePlanProgressType = appleClassType(
    "AgentPlanProgress", "AgentPlanProgress", "CodexAgentAgentPlanProgress",
    "\$sSo010CodexAgentB12PlanProgressCSgD", nullable = true,
)
private val appleNullableWorkActivityType = appleClassType(
    "AgentWorkActivity", "AgentWorkActivity", "CodexAgentAgentWorkActivity",
    "\$sSo010CodexAgentB12WorkActivityCSgD", nullable = true,
)

private val appleStringList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:kotlin/String!!>!!", "kotlin.collections.List<kotlin.String>",
    "[String]", "s:SS", "\$sSaySSGD", "NSArray<NSString *> *", "c:Q\$objc(cs)NSArray",
    "NSArray<NSString *> * _Nonnull",
)
private fun appleClassListType(
    canonicalOwner: String,
    swiftName: String,
    objectiveCName: String,
    swiftAst: String,
) = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:$appleCanonicalPackage/$canonicalOwner!!>!!",
    "kotlin.collections.List<$appleCanonicalAbiPackage.$canonicalOwner>",
    "[$swiftName]", appleOwnerUsr(objectiveCName), swiftAst,
    "NSArray<$objectiveCName *> *", "c:Q\$objc(cs)NSArray",
    "NSArray<$objectiveCName *> * _Nonnull",
)
private val appleValidationIssueList = appleClassListType(
    "AgentElicitationValidationIssue", "AgentElicitationValidationIssue",
    "CodexAgentAgentElicitationValidationIssue", "\$sSaySo010CodexAgentB26ElicitationValidationIssueCGD",
)
private val appleServiceTierList = appleClassListType(
    "AgentServiceTier", "AgentServiceTier", "CodexAgentAgentServiceTier",
    "\$sSaySo010CodexAgentB11ServiceTierCGD",
)
private val applePlanStepList = appleClassListType(
    "AgentPlanStep", "AgentPlanStep", "CodexAgentAgentPlanStep", "\$sSaySo010CodexAgentB8PlanStepCGD",
)
private val applePluginSummaryList = appleClassListType(
    "AgentPluginSummary", "AgentPluginSummary", "CodexAgentAgentPluginSummary",
    "\$sSaySo010CodexAgentB13PluginSummaryCGD",
)
private val applePluginSkillList = appleClassListType(
    "AgentPluginSkill", "AgentPluginSkill", "CodexAgentAgentPluginSkill",
    "\$sSaySo010CodexAgentB11PluginSkillCGD",
)
private val appleConnectorList = appleClassListType(
    "AgentConnector", "AgentConnector", "CodexAgentAgentConnector", "\$sSaySo010CodexAgentB9ConnectorCGD",
)
private val appleSkillList = appleClassListType(
    "AgentSkill", "AgentSkill", "CodexAgentAgentSkill", "\$sSaySo010CodexAgentB5SkillCGD",
)
private val appleFormOptionList = appleClassListType(
    "AgentFormOption", "AgentFormOption", "CodexAgentAgentFormOption",
    "\$sSaySo010CodexAgentB10FormOptionCGD",
)
private val appleHookList = appleClassListType(
    "AgentHook", "AgentHook", "CodexAgentAgentHook", "\$sSaySo010CodexAgentB4HookCGD",
)
private val appleHookActivityList = appleClassListType(
    "AgentHookActivity", "AgentHookActivity", "CodexAgentAgentHookActivity",
    "\$sSaySo010CodexAgentB12HookActivityCGD",
)
private val appleNullableFormFieldList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:$appleCanonicalPackage/AgentFormField!!>?",
    "kotlin.collections.List<$appleCanonicalAbiPackage.AgentFormField>?",
    "[AgentFormField]?", appleOwnerUsr("CodexAgentAgentFormField"),
    "\$sSaySo010CodexAgentB9FormFieldCGSgD", "NSArray<CodexAgentAgentFormField *> *", "c:Q\$objc(cs)NSArray",
    "NSArray<CodexAgentAgentFormField *> * _Nullable",
)

private val appleNullableStringList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:kotlin/String!!>?", "kotlin.collections.List<kotlin.String>?",
    "[String]?", "s:SS", "\$sSaySSGSgD",
    "NSArray<NSString *> *", "c:Q\$objc(cs)NSArray", "NSArray<NSString *> * _Nullable",
)
private val appleNullableStringMap = AppleOrdinaryType(
    "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:kotlin/String!!>?",
    "kotlin.collections.Map<kotlin.String,kotlin.String>?", "[String : String]?", "s:SS",
    "\$sSDyS2SGSgD", "NSDictionary<NSString *,NSString *> *",
    "c:Q\$objc(cs)NSDictionary", "NSDictionary<NSString *,NSString *> * _Nullable",
    listOf("s:SS", "s:SS"),
)
private val appleMcpEnvironmentVariableList = appleClassListType(
    "AgentMcpEnvironmentVariable", "AgentMcpEnvironmentVariable", "CodexAgentAgentMcpEnvironmentVariable",
    "\$sSaySo010CodexAgentB22McpEnvironmentVariableCGD",
)
private val appleNullableMcpAuthenticationType = appleClassType(
    "AgentMcpAuthentication", "AgentMcpAuthentication", "CodexAgentAgentMcpAuthentication",
    "\$sSo010CodexAgentB17McpAuthenticationCSgD", nullable = true,
)
private val appleNullableMcpToolExposureSurfaceList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:$appleCanonicalPackage/AgentMcpToolExposureSurface!!>?",
    "kotlin.collections.List<$appleCanonicalAbiPackage.AgentMcpToolExposureSurface>?",
    "[AgentMcpToolExposureSurface]?", appleOwnerUsr("CodexAgentAgentMcpToolExposureSurface"),
    "\$sSaySo010CodexAgentB22McpToolExposureSurfaceCGSgD",
    "NSArray<CodexAgentAgentMcpToolExposureSurface *> *", "c:Q\$objc(cs)NSArray",
    "NSArray<CodexAgentAgentMcpToolExposureSurface *> * _Nullable",
)
private val appleNullableMcpOauthConfigurationType = appleClassType(
    "AgentMcpOauthConfiguration", "AgentMcpOauthConfiguration", "CodexAgentAgentMcpOauthConfiguration",
    "\$sSo010CodexAgentB21McpOauthConfigurationCSgD", nullable = true,
)
private val appleMcpTransportType = AppleOrdinaryType(
    "$appleCanonicalPackage/AgentMcpTransport!!", "$appleCanonicalAbiPackage.AgentMcpTransport",
    "any AgentMcpTransport", "c:objc(pl)CodexAgentAgentMcpTransport",
    "\$sSo010CodexAgentB12McpTransport_pD", "id<CodexAgentAgentMcpTransport>",
    "c:Qoobjc(pl)CodexAgentAgentMcpTransport",
)
private val appleMcpToolConfigurationMap = AppleOrdinaryType(
    "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:$appleCanonicalPackage/AgentMcpToolConfiguration!!>!!",
    "kotlin.collections.Map<kotlin.String,$appleCanonicalAbiPackage.AgentMcpToolConfiguration>",
    "[String : AgentMcpToolConfiguration]", "s:SS", "\$sSDySSSo010CodexAgentB20McpToolConfigurationCGD",
    "NSDictionary<NSString *,CodexAgentAgentMcpToolConfiguration *> *", "c:Q\$objc(cs)NSDictionary",
    "NSDictionary<NSString *,CodexAgentAgentMcpToolConfiguration *> * _Nonnull",
    listOf("s:SS", appleOwnerUsr("CodexAgentAgentMcpToolConfiguration")),
)
private val appleElicitationActionType = appleClassType(
    "AgentElicitationAction", "AgentElicitationAction", "CodexAgentAgentElicitationAction",
    "\$sSo010CodexAgentB17ElicitationActionCD",
)
private val appleElicitationContentMap = AppleOrdinaryType(
    "kotlin.collections/Map<INVARIANT:kotlin/String!!,INVARIANT:$appleCanonicalPackage/AgentFormValue!!>!!",
    "kotlin.collections.Map<kotlin.String,$appleCanonicalAbiPackage.AgentFormValue>",
    "[String : any AgentFormValue]", "s:SS", "\$sSDySSSo010CodexAgentB9FormValue_pGD",
    "NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *", "c:Q\$objc(cs)NSDictionary",
    "NSDictionary<NSString *,id<CodexAgentAgentFormValue>> * _Nonnull",
    listOf("s:SS", "c:objc(pl)CodexAgentAgentFormValue"),
)

private fun appleEntries(vararg values: Pair<String, String>): List<Pair<String, String>> = values.toList()

private val d065AppleEnums = listOf(
    AppleOrdinaryEnum("AgentApprovalPreset", "AgentApprovalPreset", "CodexAgentAgentApprovalPreset",
        "\$sSo010CodexAgentB14ApprovalPresetCD",
        appleEntries("NEVER" to "never", "AUTO_REVIEW" to "autoReview", "ASK_ME" to "askMe", "STRICT" to "strict"),
        listOf(AppleOrdinaryProperty("displayName", appleString))),
    AppleOrdinaryEnum("AgentAuthenticationStatus", "AgentAuthenticationStatus", "CodexAgentAgentAuthenticationStatus",
        "\$sSo010CodexAgentB20AuthenticationStatusCD",
        appleEntries("SIGNED_OUT" to "signedOut", "AUTHENTICATING" to "authenticating", "AUTHENTICATED" to "authenticated")),
    AppleOrdinaryEnum("AgentCapability", "AgentCapability", "CodexAgentAgentCapability",
        "\$sSo010CodexAgentB10CapabilityCD", appleEntries("WEB_SEARCH" to "webSearch"),
        listOf(
            AppleOrdinaryProperty("displayLabel", appleString),
            AppleOrdinaryProperty("icon", appleNullableString),
            AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("promptLabel", appleString),
        )),
    AppleOrdinaryEnum("AgentCatalogFreshness", "AgentCatalogFreshness", "CodexAgentAgentCatalogFreshness",
        "\$sSo010CodexAgentB16CatalogFreshnessCD",
        appleEntries("LIVE" to "live", "FRESH_CACHE" to "freshCache", "STALE_CACHE" to "staleCache")),
    AppleOrdinaryEnum("AgentConversationStatus", "AgentConversationStatus", "CodexAgentAgentConversationStatus",
        "\$sSo010CodexAgentB18ConversationStatusCD", appleEntries(
            "NEW" to "theNew", "OPENING" to "opening", "READY" to "ready", "STARTING_TURN" to "startingTurn",
            "RUNNING_TURN" to "runningTurn", "CANCELLING_TURN" to "cancellingTurn", "RELOADING" to "reloading",
            "FAILED" to "failed", "CLOSED" to "closed",
        )),
    AppleOrdinaryEnum("AgentElicitationAction", "AgentElicitationAction", "CodexAgentAgentElicitationAction",
        "\$sSo010CodexAgentB17ElicitationActionCD",
        appleEntries("ACCEPT" to "accept", "DECLINE" to "decline", "CANCEL" to "cancel")),
    AppleOrdinaryEnum("AgentElicitationValidationReason", "AgentElicitationValidationReason",
        "CodexAgentAgentElicitationValidationReason", "\$sSo010CodexAgentB27ElicitationValidationReasonCD",
        appleEntries(
            "MISSING_REQUIRED" to "missingRequired", "UNKNOWN_FIELD" to "unknownField",
            "INVALID_TYPE" to "invalidType", "NON_FINITE_NUMBER" to "nonFiniteNumber",
            "BELOW_MINIMUM" to "belowMinimum", "ABOVE_MAXIMUM" to "aboveMaximum",
            "NON_INTEGER" to "nonInteger", "INVALID_FORMAT" to "invalidFormat",
            "INVALID_SELECTION" to "invalidSelection", "DUPLICATE_SELECTION" to "duplicateSelection",
        )),
    AppleOrdinaryEnum("AgentFormFieldType", "AgentFormFieldType", "CodexAgentAgentFormFieldType",
        "\$sSo010CodexAgentB13FormFieldTypeCD", appleEntries(
            "STRING" to "string", "NUMBER" to "number", "INTEGER" to "integer", "BOOLEAN" to "boolean",
            "SINGLE_SELECT" to "singleSelect", "MULTI_SELECT" to "multiSelect",
        )),
    AppleOrdinaryEnum("AgentFormStringFormat", "AgentFormStringFormat", "CodexAgentAgentFormStringFormat",
        "\$sSo010CodexAgentB16FormStringFormatCD",
        appleEntries("EMAIL" to "email", "URI" to "uri", "DATE" to "date", "DATE_TIME" to "dateTime")),
    AppleOrdinaryEnum("AgentHookRunStatus", "AgentHookRunStatus", "CodexAgentAgentHookRunStatus",
        "\$sSo010CodexAgentB13HookRunStatusCD", appleEntries(
            "RUNNING" to "running", "COMPLETED" to "completed", "FAILED" to "failed",
            "BLOCKED" to "blocked", "STOPPED" to "stopped",
        )),
    AppleOrdinaryEnum("AgentHookTrustStatus", "AgentHookTrustStatus", "CodexAgentAgentHookTrustStatus",
        "\$sSo010CodexAgentB15HookTrustStatusCD",
        appleEntries("MANAGED" to "managed", "UNTRUSTED" to "untrusted", "TRUSTED" to "trusted", "MODIFIED" to "modified")),
    AppleOrdinaryEnum("AgentIntegrationAuthorizationStatus", "AgentIntegrationAuthorizationStatus",
        "CodexAgentAgentIntegrationAuthorizationStatus", "\$sSo010CodexAgentB30IntegrationAuthorizationStatusCD",
        appleEntries(
            "IDLE" to "idle", "STARTING" to "starting", "AWAITING_COMPLETION" to "awaitingCompletion",
            "AUTHORIZED" to "authorized", "FAILED" to "failed",
        )),
    AppleOrdinaryEnum("AgentMcpAuthStatus", "AgentMcpAuthStatus", "CodexAgentAgentMcpAuthStatus",
        "\$sSo010CodexAgentB13McpAuthStatusCD", appleEntries(
            "UNKNOWN" to "unknown", "UNSUPPORTED" to "unsupported", "NOT_LOGGED_IN" to "notLoggedIn",
            "BEARER_TOKEN" to "bearerToken", "OAUTH" to "oauth",
        )),
    AppleOrdinaryEnum("AgentMcpAuthentication", "AgentMcpAuthentication", "CodexAgentAgentMcpAuthentication",
        "\$sSo010CodexAgentB17McpAuthenticationCD", appleEntries("OAUTH" to "oauth", "CHAT_GPT" to "chatGpt")),
    AppleOrdinaryEnum("AgentMcpToolApproval", "AgentMcpToolApproval", "CodexAgentAgentMcpToolApproval",
        "\$sSo010CodexAgentB15McpToolApprovalCD",
        appleEntries("AUTO" to "auto_", "PROMPT" to "prompt", "WRITES" to "writes", "APPROVE" to "approve")),
    AppleOrdinaryEnum("AgentMcpToolExposureSurface", "AgentMcpToolExposureSurface",
        "CodexAgentAgentMcpToolExposureSurface", "\$sSo010CodexAgentB22McpToolExposureSurfaceCD",
        appleEntries("CODE_MODE" to "codeMode", "DEFERRED" to "deferred", "DIRECT" to "direct")),
    AppleOrdinaryEnum("AgentPlanStepStatus", "AgentPlanStepStatus", "CodexAgentAgentPlanStepStatus",
        "\$sSo010CodexAgentB14PlanStepStatusCD",
        appleEntries("PENDING" to "pending", "IN_PROGRESS" to "inProgress", "COMPLETED" to "completed")),
    AppleOrdinaryEnum("AgentPluginAuthPolicy", "AgentPluginAuthPolicy", "CodexAgentAgentPluginAuthPolicy",
        "\$sSo010CodexAgentB16PluginAuthPolicyCD", appleEntries("ON_INSTALL" to "onInstall", "ON_USE" to "onUse")),
    AppleOrdinaryEnum("AgentPluginInstallPolicy", "AgentPluginInstallPolicy", "CodexAgentAgentPluginInstallPolicy",
        "\$sSo010CodexAgentB19PluginInstallPolicyCD", appleEntries(
            "NOT_AVAILABLE" to "notAvailable", "AVAILABLE" to "available",
            "INSTALLED_BY_DEFAULT" to "installedByDefault",
        )),
    AppleOrdinaryEnum("AgentResolution", "AgentResolution", "CodexAgentAgentResolution",
        "\$sSo010CodexAgentB10ResolutionCD",
        appleEntries("Preferred" to "preferred", "Default" to "default_", "First" to "first")),
    AppleOrdinaryEnum("AgentResourceOrigin", "AgentResourceOrigin", "CodexAgentAgentResourceOrigin",
        "\$sSo010CodexAgentB14ResourceOriginCD", appleEntries(
            "USER" to "user", "WORKSPACE" to "workspace", "PLUGIN" to "plugin", "MANAGED" to "managed",
            "UNKNOWN" to "unknown",
        )),
    AppleOrdinaryEnum("AgentSkillScope", "AgentSkillScope", "CodexAgentAgentSkillScope",
        "\$sSo010CodexAgentB10SkillScopeCD",
        appleEntries("SYSTEM" to "system", "USER" to "user", "REPO" to "repo", "PLUGIN" to "plugin", "ADMIN" to "admin"),
        listOf(AppleOrdinaryProperty("displayName", appleString))),
    AppleOrdinaryEnum("AgentWorkActivity", "AgentWorkActivity", "CodexAgentAgentWorkActivity",
        "\$sSo010CodexAgentB12WorkActivityCD",
        appleEntries("RUNNING_COMMAND" to "runningCommand", "WRITING_FILES" to "writingFiles")),
    AppleOrdinaryEnum("CodexAuthorizationPurpose", "CodexAuthorizationPurpose",
        "CodexAgentCodexAuthorizationPurpose", "\$sSo010CodexAgentA20AuthorizationPurposeCD",
        appleEntries("CHAT_GPT" to "chatGpt", "EXTERNAL" to "external")),
    AppleOrdinaryEnum("CodexWorkspaceSelectionReason", "CodexWorkspaceSelectionReason",
        "CodexAgentCodexWorkspaceSelectionReason", "\$sSo010CodexAgentA24WorkspaceSelectionReasonCD",
        appleEntries(
            "NOT_SELECTED" to "notSelected", "NOT_FOUND" to "notFound", "ACCESS_REVOKED" to "accessRevoked",
            "INVALID_SELECTION" to "invalidSelection",
        )),
)

private val d065AppleValues = listOf(
    AppleOrdinaryValue("AgentConversationSummary", "AgentConversationSummary", "CodexAgentAgentConversationSummary",
        "\$sySo010CodexAgentB19ConversationSummaryCSo0abC2IdC_SSs5Int64VtcABmcD",
        listOf(
            AppleOrdinaryParameter("conversationId", appleConversationIdType),
            AppleOrdinaryParameter("title", appleString),
            AppleOrdinaryParameter("updatedAtEpochSeconds", appleLong),
        ), listOf(
            AppleOrdinaryProperty("conversationId", appleConversationIdType),
            AppleOrdinaryProperty("title", appleString),
            AppleOrdinaryProperty("updatedAtEpochSeconds", appleLong),
        )),
    AppleOrdinaryValue("AgentFormOption", "AgentFormOption", "CodexAgentAgentFormOption",
        "\$sySo010CodexAgentB10FormOptionCSS_S2SSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("value", appleString),
            AppleOrdinaryParameter("title", appleString, hasDefault = true),
            AppleOrdinaryParameter("description", appleNullableString, hasDefault = true,
                objectiveCAst = "NSString * _Nullable"),
        ), listOf(
            AppleOrdinaryProperty("description", appleNullableString, "description_"),
            AppleOrdinaryProperty("title", appleString),
            AppleOrdinaryProperty("value", appleString),
        )),
    AppleOrdinaryValue("AgentMcpEnvironmentVariable", "AgentMcpEnvironmentVariable",
        "CodexAgentAgentMcpEnvironmentVariable",
        "\$sySo010CodexAgentB22McpEnvironmentVariableCSS_So0abbcD6SourceCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter("source", appleNullableMcpEnvironmentSourceType, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("source", appleNullableMcpEnvironmentSourceType),
        )),
    AppleOrdinaryValue("AgentMcpOauthConfiguration", "AgentMcpOauthConfiguration",
        "CodexAgentAgentMcpOauthConfiguration",
        "\$sySo010CodexAgentB21McpOauthConfigurationCSSSg_So0aB3IntCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("clientId", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("callbackPort", appleNullableInt, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("callbackPort", appleNullableInt),
            AppleOrdinaryProperty("clientId", appleNullableString),
        )),
    AppleOrdinaryValue("AgentPluginReference", "AgentPluginReference", "CodexAgentAgentPluginReference",
        "\$sySo010CodexAgentB15PluginReferenceCSS_S3SSgACtcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString), AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter("marketplaceName", appleString),
            AppleOrdinaryParameter("marketplacePath", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("remotePluginId", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("id", appleString), AppleOrdinaryProperty("marketplaceName", appleString),
            AppleOrdinaryProperty("marketplacePath", appleNullableString), AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("remotePluginId", appleNullableString), AppleOrdinaryProperty("uri", appleString),
        )),
    AppleOrdinaryValue("AgentPluginSkill", "AgentPluginSkill", "CodexAgentAgentPluginSkill",
        "\$sySo010CodexAgentB11PluginSkillCSS_SSSbSSSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("description", appleString),
            AppleOrdinaryParameter("isEnabled", appleBoolean),
            AppleOrdinaryParameter("path", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("isEnabled", appleBoolean), AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("path", appleNullableString),
        )),
    AppleOrdinaryValue("AgentServiceTier", "AgentServiceTier", "CodexAgentAgentServiceTier",
        "\$sySo010CodexAgentB11ServiceTierCSS_S2StcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString), AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter("description", appleString),
        ), listOf(
            AppleOrdinaryProperty("description", appleString, "description_"), AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("name", appleString),
        )),
    AppleOrdinaryValue("AgentSkillChunk", "AgentSkillChunk", "CodexAgentAgentSkillChunk",
        "\$sySo010CodexAgentB10SkillChunkCSS_So0aB4LongCSgs5Int64VtcABmcD",
        listOf(
            AppleOrdinaryParameter("content", appleString), AppleOrdinaryParameter("nextOffset", appleNullableLong),
            AppleOrdinaryParameter("totalBytes", appleLong),
        ), listOf(
            AppleOrdinaryProperty("content", appleString), AppleOrdinaryProperty("nextOffset", appleNullableLong),
            AppleOrdinaryProperty("totalBytes", appleLong),
        )),
    AppleOrdinaryValue("CodexClientInfo", "CodexClientInfo", "CodexAgentCodexClientInfo",
        "\$sySo010CodexAgentA10ClientInfoCSS_S2StcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("title", appleString),
            AppleOrdinaryParameter("version", appleString),
        ), listOf(
            AppleOrdinaryProperty("name", appleString), AppleOrdinaryProperty("title", appleString),
            AppleOrdinaryProperty("version", appleString),
        )),
    AppleOrdinaryValue("CodexWorkspace", "CodexWorkspace", "CodexAgentCodexWorkspace",
        "\$sySo010CodexAgentA9WorkspaceCSS_SStcABmcD",
        listOf(
            AppleOrdinaryParameter("path", appleString),
            AppleOrdinaryParameter("displayName", appleString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("displayName", appleString), AppleOrdinaryProperty("path", appleString),
        )),
    AppleOrdinaryValue("AgentConversationSettings", "AgentConversationSettings",
        "CodexAgentAgentConversationSettings",
        "\$sySo010CodexAgentB20ConversationSettingsCSo0abB14ApprovalPresetC_SSSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("approvalPreset", appleApprovalPresetType, hasDefault = true),
            AppleOrdinaryParameter("serviceTier", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("approvalPreset", appleApprovalPresetType),
            AppleOrdinaryProperty("serviceTier", appleNullableString),
        )),
    AppleOrdinaryValue("AgentElicitationValidationIssue", "AgentElicitationValidationIssue",
        "CodexAgentAgentElicitationValidationIssue",
        "\$sySo010CodexAgentB26ElicitationValidationIssueCSS_So0abbcD6ReasonCtcABmcD",
        listOf(
            AppleOrdinaryParameter("fieldName", appleString),
            AppleOrdinaryParameter("reason", appleElicitationValidationReasonType),
        ), listOf(
            AppleOrdinaryProperty("fieldName", appleString),
            AppleOrdinaryProperty("reason", appleElicitationValidationReasonType),
        )),
    AppleOrdinaryValue("AgentPlanStep", "AgentPlanStep", "CodexAgentAgentPlanStep",
        "\$sySo010CodexAgentB8PlanStepCSS_So0abbcD6StatusCtcABmcD",
        listOf(
            AppleOrdinaryParameter("text", appleString), AppleOrdinaryParameter("status", applePlanStepStatusType),
        ), listOf(
            AppleOrdinaryProperty("status", applePlanStepStatusType), AppleOrdinaryProperty("text", appleString),
        )),
    AppleOrdinaryValue("AgentMcpToolConfiguration", "AgentMcpToolConfiguration",
        "CodexAgentAgentMcpToolConfiguration",
        "\$sySo010CodexAgentB20McpToolConfigurationCSo0abbcD8ApprovalCSg_tcABmcD",
        listOf(AppleOrdinaryParameter("approval", appleNullableMcpToolApprovalType, hasDefault = true)),
        listOf(AppleOrdinaryProperty("approval", appleNullableMcpToolApprovalType))),
)

private val d073AppleValues = listOf(
    AppleOrdinaryValue("AgentConnector", "AgentConnector", "CodexAgentAgentConnector",
        "\$sySo010CodexAgentB9ConnectorCSS_S3SSgS2bSaySSGtcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString), AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter("description", appleString, hasDefault = true),
            AppleOrdinaryParameter("installUrl", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("isAccessible", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("isEnabled", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("pluginNames", appleStringList, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("id", appleString), AppleOrdinaryProperty("installUrl", appleNullableString),
            AppleOrdinaryProperty("isAccessible", appleBoolean), AppleOrdinaryProperty("isEnabled", appleBoolean),
            AppleOrdinaryProperty("name", appleString), AppleOrdinaryProperty("pluginNames", appleStringList),
        )),
    AppleOrdinaryValue("AgentElicitationValidation", "AgentElicitationValidation",
        "CodexAgentAgentElicitationValidation",
        "\$sySo010CodexAgentB21ElicitationValidationCSaySo0abbcD5IssueCG_tcABmcD",
        listOf(AppleOrdinaryParameter("issues", appleValidationIssueList)),
        listOf(
            AppleOrdinaryProperty("isValid", appleBoolean),
            AppleOrdinaryProperty("issues", appleValidationIssueList),
        )),
    AppleOrdinaryValue("AgentFormValue.BooleanValue", "AgentFormValueBooleanValue",
        "CodexAgentAgentFormValueBooleanValue", "\$sySo010CodexAgentb16FormValueBooleanD0CSb_tcABmcD",
        listOf(AppleOrdinaryParameter("value", appleBoolean)),
        listOf(AppleOrdinaryProperty("value", appleBoolean))),
    AppleOrdinaryValue("AgentFormValue.Number", "AgentFormValueNumber", "CodexAgentAgentFormValueNumber",
        "\$sySo010CodexAgentB15FormValueNumberCSd_tcABmcD",
        listOf(AppleOrdinaryParameter("value", appleDouble)),
        listOf(AppleOrdinaryProperty("value", appleDouble))),
    AppleOrdinaryValue("AgentFormValue.Text", "AgentFormValueText", "CodexAgentAgentFormValueText",
        "\$sySo010CodexAgentB13FormValueTextCSS_tcABmcD",
        listOf(AppleOrdinaryParameter("value", appleString)),
        listOf(AppleOrdinaryProperty("value", appleString))),
    AppleOrdinaryValue("AgentFormValue.TextList", "AgentFormValueTextList",
        "CodexAgentAgentFormValueTextList", "\$sySo010CodexAgentB17FormValueTextListCSaySSG_tcABmcD",
        listOf(AppleOrdinaryParameter("value", appleStringList)),
        listOf(AppleOrdinaryProperty("value", appleStringList))),
    AppleOrdinaryValue("AgentModel", "AgentModel", "CodexAgentAgentModel",
        "\$sySo010CodexAgentB5ModelCSS_S2SSaySSGSSSbSaySo0abB11ServiceTierCGSSSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString), AppleOrdinaryParameter("displayName", appleString),
            AppleOrdinaryParameter("description", appleString),
            AppleOrdinaryParameter("supportedEfforts", appleStringList),
            AppleOrdinaryParameter("defaultEffort", appleString), AppleOrdinaryParameter("isDefault", appleBoolean),
            AppleOrdinaryParameter("serviceTiers", appleServiceTierList, hasDefault = true),
            AppleOrdinaryParameter("defaultServiceTier", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("defaultEffort", appleString),
            AppleOrdinaryProperty("defaultServiceTier", appleNullableString),
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("displayName", appleString), AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("isDefault", appleBoolean),
            AppleOrdinaryProperty("serviceTiers", appleServiceTierList),
            AppleOrdinaryProperty("supportedEfforts", appleStringList),
        )),
    AppleOrdinaryValue("AgentPlanProgress", "AgentPlanProgress", "CodexAgentAgentPlanProgress",
        "\$sySo010CodexAgentB12PlanProgressCSSSg_SaySo0abbC4StepCGtcABmcD",
        listOf(
            AppleOrdinaryParameter("explanation", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("steps", applePlanStepList, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("explanation", appleNullableString),
            AppleOrdinaryProperty("steps", applePlanStepList),
        )),
    AppleOrdinaryValue("AgentPluginCatalog", "AgentPluginCatalog", "CodexAgentAgentPluginCatalog",
        "\$sySo010CodexAgentB13PluginCatalogCSaySo0abbC7SummaryCG_SaySSGSo0abbD9FreshnessCtcABmcD",
        listOf(
            AppleOrdinaryParameter("plugins", applePluginSummaryList),
            AppleOrdinaryParameter("errors", appleStringList, hasDefault = true),
            AppleOrdinaryParameter("freshness", appleCatalogFreshnessType, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("errors", appleStringList),
            AppleOrdinaryProperty("freshness", appleCatalogFreshnessType),
            AppleOrdinaryProperty("plugins", applePluginSummaryList),
        )),
    AppleOrdinaryValue("AgentPluginDetail", "AgentPluginDetail", "CodexAgentAgentPluginDetail",
        "\$sySo010CodexAgentB12PluginDetailCSo0abbC7SummaryC_SSSaySo0abbC5SkillCGSaySo0abB9ConnectorCGSaySSGs5Int32VtcABmcD",
        listOf(
            AppleOrdinaryParameter("summary", applePluginSummaryType),
            AppleOrdinaryParameter("description", appleString),
            AppleOrdinaryParameter("skills", applePluginSkillList),
            AppleOrdinaryParameter("connectors", appleConnectorList),
            AppleOrdinaryParameter("mcpServers", appleStringList),
            AppleOrdinaryParameter("hookCount", appleInt, objectiveCAst = "int"),
        ), listOf(
            AppleOrdinaryProperty("connectors", appleConnectorList),
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("hookCount", appleInt), AppleOrdinaryProperty("mcpServers", appleStringList),
            AppleOrdinaryProperty("skills", applePluginSkillList),
            AppleOrdinaryProperty("summary", applePluginSummaryType),
        )),
    AppleOrdinaryValue("AgentPluginInstallResult", "AgentPluginInstallResult",
        "CodexAgentAgentPluginInstallResult",
        "\$sySo010CodexAgentB19PluginInstallResultCSo0abbC10AuthPolicyC_SaySo0abB9ConnectorCGSSSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("authPolicy", applePluginAuthPolicyType),
            AppleOrdinaryParameter("connectorsNeedingAuthentication", appleConnectorList),
            AppleOrdinaryParameter("message", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("authPolicy", applePluginAuthPolicyType),
            AppleOrdinaryProperty("connectorsNeedingAuthentication", appleConnectorList),
            AppleOrdinaryProperty("message", appleNullableString),
        )),
    AppleOrdinaryValue("AgentPluginSummary", "AgentPluginSummary", "CodexAgentAgentPluginSummary",
        "\$sySo010CodexAgentB13PluginSummaryCSo0abbC9ReferenceC_S2SS2bSo0abbC13InstallPolicyCSo0abbc4AuthG0CSbSaySSGSSSgA3JtcABmcD",
        listOf(
            AppleOrdinaryParameter("reference", applePluginReferenceType),
            AppleOrdinaryParameter("displayName", appleString), AppleOrdinaryParameter("description", appleString),
            AppleOrdinaryParameter("isInstalled", appleBoolean), AppleOrdinaryParameter("isEnabled", appleBoolean),
            AppleOrdinaryParameter("installPolicy", applePluginInstallPolicyType),
            AppleOrdinaryParameter("authPolicy", applePluginAuthPolicyType),
            AppleOrdinaryParameter("isAvailable", appleBoolean),
            AppleOrdinaryParameter("capabilities", appleStringList, hasDefault = true),
            AppleOrdinaryParameter("brandColor", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("privacyPolicyUrl", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("termsOfServiceUrl", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("websiteUrl", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("authPolicy", applePluginAuthPolicyType),
            AppleOrdinaryProperty("brandColor", appleNullableString),
            AppleOrdinaryProperty("capabilities", appleStringList),
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("displayName", appleString),
            AppleOrdinaryProperty("installPolicy", applePluginInstallPolicyType),
            AppleOrdinaryProperty("isAvailable", appleBoolean), AppleOrdinaryProperty("isEnabled", appleBoolean),
            AppleOrdinaryProperty("isInstalled", appleBoolean),
            AppleOrdinaryProperty("privacyPolicyUrl", appleNullableString),
            AppleOrdinaryProperty("reference", applePluginReferenceType),
            AppleOrdinaryProperty("termsOfServiceUrl", appleNullableString),
            AppleOrdinaryProperty("websiteUrl", appleNullableString),
        )),
    AppleOrdinaryValue("AgentSkill", "AgentSkill", "CodexAgentAgentSkill",
        "\$sySo010CodexAgentB5SkillCSS_S3SSo0abbC5ScopeCSbSSSgSaySSGSbSo0abB14ResourceOriginCtcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("displayName", appleString),
            AppleOrdinaryParameter("description", appleString), AppleOrdinaryParameter("path", appleString),
            AppleOrdinaryParameter("scope", appleSkillScopeType), AppleOrdinaryParameter("isEnabled", appleBoolean),
            AppleOrdinaryParameter("brandColor", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("dependencies", appleStringList, hasDefault = true),
            AppleOrdinaryParameter("canUninstall", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("origin", appleResourceOriginType, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("brandColor", appleNullableString),
            AppleOrdinaryProperty("canUninstall", appleBoolean),
            AppleOrdinaryProperty("dependencies", appleStringList),
            AppleOrdinaryProperty("description", appleString, "description_"),
            AppleOrdinaryProperty("displayName", appleString), AppleOrdinaryProperty("isEnabled", appleBoolean),
            AppleOrdinaryProperty("name", appleString), AppleOrdinaryProperty("origin", appleResourceOriginType),
            AppleOrdinaryProperty("path", appleString), AppleOrdinaryProperty("scope", appleSkillScopeType),
        )),
    AppleOrdinaryValue("AgentSkillCatalog", "AgentSkillCatalog", "CodexAgentAgentSkillCatalog",
        "\$sySo010CodexAgentB12SkillCatalogCSaySo0abbC0CG_SaySSGtcABmcD",
        listOf(
            AppleOrdinaryParameter("skills", appleSkillList),
            AppleOrdinaryParameter("errors", appleStringList, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("errors", appleStringList), AppleOrdinaryProperty("skills", appleSkillList),
        )),
    AppleOrdinaryValue("CodexPathWorkspaceSelection", "CodexPathWorkspaceSelection",
        "CodexAgentCodexPathWorkspaceSelection", "\$sySo010CodexAgentA22PathWorkspaceSelectionCSS_tcABmcD",
        listOf(AppleOrdinaryParameter("path", appleString)), listOf(AppleOrdinaryProperty("path", appleString))),
    AppleOrdinaryValue("CodexWorkspaceResolution.Available", "CodexWorkspaceResolutionAvailable",
        "CodexAgentCodexWorkspaceResolutionAvailable",
        "\$sySo010CodexAgentA28WorkspaceResolutionAvailableCSo0abaC0C_tcABmcD",
        listOf(AppleOrdinaryParameter("workspace", appleWorkspaceType)),
        listOf(AppleOrdinaryProperty("workspace", appleWorkspaceType))),
    AppleOrdinaryValue("CodexWorkspaceResolution.SelectionRequired",
        "CodexWorkspaceResolutionSelectionRequired", "CodexAgentCodexWorkspaceResolutionSelectionRequired",
        "\$sySo010CodexAgentA36WorkspaceResolutionSelectionRequiredCSo0abacE6ReasonC_SStcABmcD",
        listOf(
            AppleOrdinaryParameter("reason", appleWorkspaceSelectionReasonType),
            AppleOrdinaryParameter("message", appleString),
        ), listOf(
            AppleOrdinaryProperty("message", appleString),
            AppleOrdinaryProperty("reason", appleWorkspaceSelectionReasonType),
    )),
)

private val d074AppleValues = listOf(
    AppleOrdinaryValue("AgentElicitation", "AgentElicitation", "CodexAgentAgentElicitation",
        "\$sySo010CodexAgentB11ElicitationCSS_SSSo0aB14ConversationIdCSSSaySo0abB9FormFieldCGSgSSSgtcABmcD",
        listOf(
            AppleOrdinaryParameter("requestId", appleString),
            AppleOrdinaryParameter("serverName", appleString),
            AppleOrdinaryParameter("conversationId", appleConversationIdType),
            AppleOrdinaryParameter("message", appleString),
            AppleOrdinaryParameter("form", appleNullableFormFieldList, hasDefault = true),
            AppleOrdinaryParameter("url", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("conversationId", appleConversationIdType),
            AppleOrdinaryProperty("form", appleNullableFormFieldList),
            AppleOrdinaryProperty("message", appleString),
            AppleOrdinaryProperty("requestId", appleString),
            AppleOrdinaryProperty("serverName", appleString),
            AppleOrdinaryProperty("url", appleNullableString),
        )),
    AppleOrdinaryValue("AgentFormField", "AgentFormField", "CodexAgentAgentFormField",
        "\$sySo010CodexAgentB9FormFieldCSS_S2SSgSbSo0abbcD4TypeCSaySo0abbC6OptionCGSo0abbC5Value_pSgSo0aB6DoubleCSgAMSo0abbC12StringFormatCSgSo0aB4LongCSgA3SS2btcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("title", appleString),
            AppleOrdinaryParameter("description", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("isRequired", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("type", appleFormFieldType),
            AppleOrdinaryParameter("options", appleFormOptionList, hasDefault = true),
            AppleOrdinaryParameter("defaultValue", appleNullableFormValueType, hasDefault = true),
            AppleOrdinaryParameter("minimum", appleNullableDouble, hasDefault = true),
            AppleOrdinaryParameter("maximum", appleNullableDouble, hasDefault = true),
            AppleOrdinaryParameter("format", appleNullableFormStringFormatType, hasDefault = true),
            AppleOrdinaryParameter("minimumLength", appleNullableLong, hasDefault = true),
            AppleOrdinaryParameter("maximumLength", appleNullableLong, hasDefault = true),
            AppleOrdinaryParameter("minimumSelections", appleNullableLong, hasDefault = true),
            AppleOrdinaryParameter("maximumSelections", appleNullableLong, hasDefault = true),
            AppleOrdinaryParameter("allowsOther", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("isSecret", appleBoolean, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("allowsOther", appleBoolean),
            AppleOrdinaryProperty("defaultValue", appleNullableFormValueType),
            AppleOrdinaryProperty("description", appleNullableString, "description_"),
            AppleOrdinaryProperty("format", appleNullableFormStringFormatType),
            AppleOrdinaryProperty("isRequired", appleBoolean), AppleOrdinaryProperty("isSecret", appleBoolean),
            AppleOrdinaryProperty("maximum", appleNullableDouble),
            AppleOrdinaryProperty("maximumLength", appleNullableLong),
            AppleOrdinaryProperty("maximumSelections", appleNullableLong),
            AppleOrdinaryProperty("minimum", appleNullableDouble),
            AppleOrdinaryProperty("minimumLength", appleNullableLong),
            AppleOrdinaryProperty("minimumSelections", appleNullableLong),
            AppleOrdinaryProperty("name", appleString), AppleOrdinaryProperty("options", appleFormOptionList),
            AppleOrdinaryProperty("title", appleString), AppleOrdinaryProperty("type", appleFormFieldType),
        )),
    AppleOrdinaryValue("AgentHook", "AgentHook", "CodexAgentAgentHook",
        "\$sySo010CodexAgentB4HookCSS_SSSbSSSo0abbC7Handler_pSbS2Ss5Int64VSo0abbC11TrustStatusCSSSgA2HSo0abB14ResourceOriginCSbtcABmcD",
        listOf(
            AppleOrdinaryParameter("key", appleString), AppleOrdinaryParameter("currentHash", appleString),
            AppleOrdinaryParameter("isEnabled", appleBoolean), AppleOrdinaryParameter("eventName", appleString),
            AppleOrdinaryParameter("handler", appleHookHandlerType),
            AppleOrdinaryParameter("isManaged", appleBoolean), AppleOrdinaryParameter("source", appleString),
            AppleOrdinaryParameter("sourcePath", appleString), AppleOrdinaryParameter("timeoutSeconds", appleLong),
            AppleOrdinaryParameter("trustStatus", appleHookTrustStatusType),
            AppleOrdinaryParameter("matcher", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("pluginId", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("statusMessage", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("origin", appleResourceOriginType, hasDefault = true),
            AppleOrdinaryParameter("canUninstall", appleBoolean, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("canTrust", appleBoolean), AppleOrdinaryProperty("canUninstall", appleBoolean),
            AppleOrdinaryProperty("currentHash", appleString), AppleOrdinaryProperty("eventName", appleString),
            AppleOrdinaryProperty("handler", appleHookHandlerType), AppleOrdinaryProperty("isEnabled", appleBoolean),
            AppleOrdinaryProperty("isManaged", appleBoolean), AppleOrdinaryProperty("key", appleString),
            AppleOrdinaryProperty("matcher", appleNullableString),
            AppleOrdinaryProperty("origin", appleResourceOriginType),
            AppleOrdinaryProperty("pluginId", appleNullableString), AppleOrdinaryProperty("source", appleString),
            AppleOrdinaryProperty("sourcePath", appleString),
            AppleOrdinaryProperty("statusMessage", appleNullableString),
            AppleOrdinaryProperty("timeoutSeconds", appleLong),
            AppleOrdinaryProperty("trustStatus", appleHookTrustStatusType),
        )),
    AppleOrdinaryValue("AgentHookActivity", "AgentHookActivity", "CodexAgentAgentHookActivity",
        "\$sySo010CodexAgentB12HookActivityCSS_S2SSo0abbC9RunStatusCSSSgSaySSGtcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString), AppleOrdinaryParameter("eventName", appleString),
            AppleOrdinaryParameter("handlerType", appleString),
            AppleOrdinaryParameter("status", appleHookRunStatusType),
            AppleOrdinaryParameter("statusMessage", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("details", appleStringList, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("details", appleStringList), AppleOrdinaryProperty("eventName", appleString),
            AppleOrdinaryProperty("handlerType", appleString), AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("status", appleHookRunStatusType),
            AppleOrdinaryProperty("statusMessage", appleNullableString),
        )),
    AppleOrdinaryValue("AgentHookCatalog", "AgentHookCatalog", "CodexAgentAgentHookCatalog",
        "\$sySo010CodexAgentB11HookCatalogCSaySo0abbC0CG_SaySSGAFtcABmcD",
        listOf(
            AppleOrdinaryParameter("hooks", appleHookList),
            AppleOrdinaryParameter("warnings", appleStringList, hasDefault = true),
            AppleOrdinaryParameter("errors", appleStringList, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("errors", appleStringList), AppleOrdinaryProperty("hooks", appleHookList),
            AppleOrdinaryProperty("warnings", appleStringList),
        )),
    AppleOrdinaryValue("AgentHookHandler.Command", "AgentHookHandlerCommand",
        "CodexAgentAgentHookHandlerCommand", "\$sySo010CodexAgentB18HookHandlerCommandCSS_SbtcABmcD",
        listOf(AppleOrdinaryParameter("command", appleString), AppleOrdinaryParameter("isAsync", appleBoolean)),
        listOf(AppleOrdinaryProperty("command", appleString), AppleOrdinaryProperty("isAsync", appleBoolean))),
    AppleOrdinaryValue("AgentHookHandler.McpTool", "AgentHookHandlerMcpTool",
        "CodexAgentAgentHookHandlerMcpTool", "\$sySo010CodexAgentB18HookHandlerMcpToolCSS_SStcABmcD",
        listOf(AppleOrdinaryParameter("server", appleString), AppleOrdinaryParameter("tool", appleString)),
        listOf(AppleOrdinaryProperty("server", appleString), AppleOrdinaryProperty("tool", appleString))),
    AppleOrdinaryValue("AgentIntegration.Connector", "AgentIntegrationConnector",
        "CodexAgentAgentIntegrationConnector", "\$sySo010CodexAgentB20IntegrationConnectorCSo0abbD0C_tcABmcD",
        listOf(AppleOrdinaryParameter("connector", appleConnectorType)),
        listOf(
            AppleOrdinaryProperty("connector", appleConnectorType),
            AppleOrdinaryProperty("displayName", appleString), AppleOrdinaryProperty("id", appleString),
        )),
    AppleOrdinaryValue("AgentInvocation.Plugin", "AgentInvocationPlugin",
        "CodexAgentAgentInvocationPlugin", "\$sySo010CodexAgentB16InvocationPluginCSS_SStcABmcD",
        listOf(AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("uri", appleString)),
        listOf(
            AppleOrdinaryProperty("key", appleString), AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("uri", appleString),
        )),
    AppleOrdinaryValue("AgentInvocation.Skill", "AgentInvocationSkill",
        "CodexAgentAgentInvocationSkill", "\$sySo010CodexAgentB15InvocationSkillCSS_SStcABmcD",
        listOf(AppleOrdinaryParameter("name", appleString), AppleOrdinaryParameter("path", appleString)),
        listOf(
            AppleOrdinaryProperty("key", appleString), AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("path", appleString),
        )),
    AppleOrdinaryValue("AgentTurnProgress", "AgentTurnProgress", "CodexAgentAgentTurnProgress",
        "\$sySo010CodexAgentB12TurnProgressCSS_S3SSo0abb4PlanD0CSgSSSo0aB3IntCSgSo0abB12WorkActivityCSgSaySo0abb4HookH0CGSbtcABmcD",
        listOf(
            AppleOrdinaryParameter("text", appleString, hasDefault = true),
            AppleOrdinaryParameter("commentary", appleString, hasDefault = true),
            AppleOrdinaryParameter("reasoning", appleString, hasDefault = true),
            AppleOrdinaryParameter("plan", appleString, hasDefault = true),
            AppleOrdinaryParameter("planProgress", appleNullablePlanProgressType, hasDefault = true),
            AppleOrdinaryParameter("shellOutput", appleString, hasDefault = true),
            AppleOrdinaryParameter("shellExitCode", appleNullableInt, hasDefault = true),
            AppleOrdinaryParameter("workActivity", appleNullableWorkActivityType, hasDefault = true),
            AppleOrdinaryParameter("hookActivities", appleHookActivityList, hasDefault = true),
            AppleOrdinaryParameter("isTruncated", appleBoolean, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("commentary", appleString),
            AppleOrdinaryProperty("hookActivities", appleHookActivityList),
            AppleOrdinaryProperty("isTruncated", appleBoolean), AppleOrdinaryProperty("plan", appleString),
            AppleOrdinaryProperty("planProgress", appleNullablePlanProgressType),
            AppleOrdinaryProperty("reasoning", appleString),
            AppleOrdinaryProperty("shellExitCode", appleNullableInt),
            AppleOrdinaryProperty("shellOutput", appleString), AppleOrdinaryProperty("text", appleString),
            AppleOrdinaryProperty("workActivity", appleNullableWorkActivityType),
        )),
    AppleOrdinaryValue("CodexAuthenticationMethod.ApiKey", "CodexAuthenticationMethodApiKey",
        "CodexAgentCodexAuthenticationMethodApiKey", "\$sySo010CodexAgentA26AuthenticationMethodApiKeyCSS_tcABmcD",
        listOf(AppleOrdinaryParameter("value", appleString)), listOf(AppleOrdinaryProperty("value", appleString))),
)

private val d075AppleValues = listOf(
    AppleOrdinaryValue("AgentPendingApproval", "AgentPendingApproval", "CodexAgentAgentPendingApproval",
        "\$sySo010CodexAgentB15PendingApprovalCSS_So0aB14ConversationIdCS2StcABmcD",
        listOf(
            AppleOrdinaryParameter("requestId", appleString),
            AppleOrdinaryParameter("conversationId", appleConversationIdType),
            AppleOrdinaryParameter("title", appleString),
            AppleOrdinaryParameter("details", appleString),
        ), listOf(
            AppleOrdinaryProperty("conversationId", appleConversationIdType),
            AppleOrdinaryProperty("details", appleString),
            AppleOrdinaryProperty("requestId", appleString),
            AppleOrdinaryProperty("title", appleString),
        )),
    AppleOrdinaryValue("AgentPendingElicitation", "AgentPendingElicitation", "CodexAgentAgentPendingElicitation",
        "\$sySo010CodexAgentB18PendingElicitationCSo0abbD0C_tcABmcD",
        listOf(AppleOrdinaryParameter("elicitation", appleElicitationType)),
        listOf(
            AppleOrdinaryProperty("conversationId", appleConversationIdType),
            AppleOrdinaryProperty("elicitation", appleElicitationType),
            AppleOrdinaryProperty("requestId", appleString),
        )),
)

private val d077AppleValues = listOf(
    AppleOrdinaryValue(
        "AgentMcpServer", "AgentMcpServer", "CodexAgentAgentMcpServer",
        "\$sySo010CodexAgentB9McpServerCSS_SSSo0abbC10AuthStatusCSo0abbcD13ConfigurationCSgSo0abB14ResourceOriginCSbtcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter("displayName", appleString),
            AppleOrdinaryParameter("authStatus", appleMcpAuthStatusType),
            AppleOrdinaryParameter(
                "configuration", appleNullableMcpServerConfigurationType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentMcpServerConfiguration * _Nullable",
            ),
            AppleOrdinaryParameter("origin", appleResourceOriginType, hasDefault = true),
            AppleOrdinaryParameter("canRemove", appleBoolean, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("authStatus", appleMcpAuthStatusType),
            AppleOrdinaryProperty("canRemove", appleBoolean),
            AppleOrdinaryProperty("configuration", appleNullableMcpServerConfigurationType),
            AppleOrdinaryProperty("displayName", appleString),
            AppleOrdinaryProperty("isAuthorized", appleBoolean),
            AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("origin", appleResourceOriginType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentIntegration.McpServer", "AgentIntegrationMcpServer", "CodexAgentAgentIntegrationMcpServer",
        "\$sySo010CodexAgentB20IntegrationMcpServerCSo0abbdE0C_tcABmcD",
        listOf(AppleOrdinaryParameter("server", appleMcpServerType)),
        listOf(
            AppleOrdinaryProperty("displayName", appleString), AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("server", appleMcpServerType),
        ),
    ),
)

private val d078AppleValues = listOf(
    AppleOrdinaryValue(
        "AgentMcpTransport.Http", "AgentMcpTransportHttp", "CodexAgentAgentMcpTransportHttp",
        "\$sySo010CodexAgentB16McpTransportHttpCSS_SSSgSDyS2SGSgAeCtcABmcD",
        listOf(
            AppleOrdinaryParameter("url", appleString),
            AppleOrdinaryParameter("bearerTokenEnvironmentVariable", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter(
                "headers", appleNullableStringMap, hasDefault = true,
                objectiveCAst = "NSDictionary<NSString *,NSString *> *",
            ),
            AppleOrdinaryParameter(
                "environmentHeaders", appleNullableStringMap, hasDefault = true,
                objectiveCAst = "NSDictionary<NSString *,NSString *> *",
            ),
            AppleOrdinaryParameter("headersHelper", appleNullableString, hasDefault = true),
        ), listOf(
            AppleOrdinaryProperty("bearerTokenEnvironmentVariable", appleNullableString),
            AppleOrdinaryProperty("environmentHeaders", appleNullableStringMap),
            AppleOrdinaryProperty("headers", appleNullableStringMap),
            AppleOrdinaryProperty("headersHelper", appleNullableString),
            AppleOrdinaryProperty("url", appleString),
        ),
    ),
    AppleOrdinaryValue(
        "AgentMcpTransport.Stdio", "AgentMcpTransportStdio", "CodexAgentAgentMcpTransportStdio",
        "\$sySo010CodexAgentB17McpTransportStdioCSS_SaySSGSSSgSDyS2SGSgSaySo0abbC19EnvironmentVariableCGtcABmcD",
        listOf(
            AppleOrdinaryParameter("command", appleString),
            AppleOrdinaryParameter(
                "arguments", appleStringList, hasDefault = true, objectiveCAst = "NSArray<NSString *> *",
            ),
            AppleOrdinaryParameter("workingDirectory", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter(
                "environment", appleNullableStringMap, hasDefault = true,
                objectiveCAst = "NSDictionary<NSString *,NSString *> *",
            ),
            AppleOrdinaryParameter(
                "forwardedEnvironment", appleMcpEnvironmentVariableList, hasDefault = true,
                objectiveCAst = "NSArray<CodexAgentAgentMcpEnvironmentVariable *> *",
            ),
        ), listOf(
            AppleOrdinaryProperty("arguments", appleStringList), AppleOrdinaryProperty("command", appleString),
            AppleOrdinaryProperty("environment", appleNullableStringMap),
            AppleOrdinaryProperty("forwardedEnvironment", appleMcpEnvironmentVariableList),
            AppleOrdinaryProperty("workingDirectory", appleNullableString),
        ),
    ),
    AppleOrdinaryValue(
        "AgentMcpServerConfiguration", "AgentMcpServerConfiguration", "CodexAgentAgentMcpServerConfiguration",
        "\$sySo010CodexAgentB22McpServerConfigurationCSS_So0abbC9Transport_pSo0abbC14AuthenticationCSg" +
            "SSS3bSaySo0abbC19ToolExposureSurfaceCGSgSo0aB6DoubleCSgAMSo0abbcH8ApprovalCSgSaySSGSgA2R" +
            "So0abbc5OauthE0CSgSSSgSDySSSo0abbchE0CGtcABmcD",
        listOf(
            AppleOrdinaryParameter("name", appleString),
            AppleOrdinaryParameter(
                "transport", appleMcpTransportType,
                objectiveCAst = "id<CodexAgentAgentMcpTransport> _Nonnull",
            ),
            AppleOrdinaryParameter("authentication", appleNullableMcpAuthenticationType, hasDefault = true),
            AppleOrdinaryParameter("environmentId", appleString, hasDefault = true),
            AppleOrdinaryParameter("isEnabled", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("isRequired", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter("supportsParallelToolCalls", appleBoolean, hasDefault = true),
            AppleOrdinaryParameter(
                "omitToolsFrom", appleNullableMcpToolExposureSurfaceList, hasDefault = true,
                objectiveCAst = "NSArray<CodexAgentAgentMcpToolExposureSurface *> *",
            ),
            AppleOrdinaryParameter("startupTimeoutSeconds", appleNullableDouble, hasDefault = true),
            AppleOrdinaryParameter("toolTimeoutSeconds", appleNullableDouble, hasDefault = true),
            AppleOrdinaryParameter("defaultToolApproval", appleNullableMcpToolApprovalType, hasDefault = true),
            AppleOrdinaryParameter(
                "enabledTools", appleNullableStringList, hasDefault = true, objectiveCAst = "NSArray<NSString *> *",
            ),
            AppleOrdinaryParameter(
                "disabledTools", appleNullableStringList, hasDefault = true, objectiveCAst = "NSArray<NSString *> *",
            ),
            AppleOrdinaryParameter(
                "scopes", appleNullableStringList, hasDefault = true, objectiveCAst = "NSArray<NSString *> *",
            ),
            AppleOrdinaryParameter("oauth", appleNullableMcpOauthConfigurationType, hasDefault = true),
            AppleOrdinaryParameter("oauthResource", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter(
                "tools", appleMcpToolConfigurationMap, hasDefault = true,
                objectiveCAst = "NSDictionary<NSString *,CodexAgentAgentMcpToolConfiguration *> *",
            ),
        ), listOf(
            AppleOrdinaryProperty("authentication", appleNullableMcpAuthenticationType),
            AppleOrdinaryProperty("defaultToolApproval", appleNullableMcpToolApprovalType),
            AppleOrdinaryProperty("disabledTools", appleNullableStringList),
            AppleOrdinaryProperty("enabledTools", appleNullableStringList),
            AppleOrdinaryProperty("environmentId", appleString), AppleOrdinaryProperty("isEnabled", appleBoolean),
            AppleOrdinaryProperty("isRequired", appleBoolean), AppleOrdinaryProperty("name", appleString),
            AppleOrdinaryProperty("oauth", appleNullableMcpOauthConfigurationType),
            AppleOrdinaryProperty("oauthResource", appleNullableString),
            AppleOrdinaryProperty("omitToolsFrom", appleNullableMcpToolExposureSurfaceList),
            AppleOrdinaryProperty("scopes", appleNullableStringList),
            AppleOrdinaryProperty("startupTimeoutSeconds", appleNullableDouble),
            AppleOrdinaryProperty("supportsParallelToolCalls", appleBoolean),
            AppleOrdinaryProperty("toolTimeoutSeconds", appleNullableDouble),
            AppleOrdinaryProperty("tools", appleMcpToolConfigurationMap),
            AppleOrdinaryProperty("transport", appleMcpTransportType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentElicitationResponse", "AgentElicitationResponse", "CodexAgentAgentElicitationResponse",
        "\$sySo010CodexAgentB19ElicitationResponseCSo0abbC6ActionC_SDySSSo0abB9FormValue_pGtcABmcD",
        listOf(
            AppleOrdinaryParameter("action", appleElicitationActionType),
            AppleOrdinaryParameter(
                "content", appleElicitationContentMap, hasDefault = true,
                objectiveCAst = "NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *",
            ),
        ), listOf(
            AppleOrdinaryProperty("action", appleElicitationActionType),
            AppleOrdinaryProperty("content", appleElicitationContentMap),
        ),
    ),
)

private fun appleEnumKey(owner: String, entry: String): String =
    "common|owner=$appleCanonicalPackage/$owner|kind=enum-entry|" +
        "abi=$appleCanonicalAbiPackage/$owner.$entry|null[0]"

private fun applePropertyKey(owner: String, property: AppleOrdinaryProperty): String =
    "common|owner=$appleCanonicalPackage/$owner|kind=property|" +
        "abi=$appleCanonicalAbiPackage/$owner.${property.canonicalName}|{}${property.canonicalName}[0]|" +
        "propertyKind=VAL|type=${property.type.canonical}"

private fun appleConstructorKey(value: AppleOrdinaryValue): String =
    "common|owner=$appleCanonicalPackage/${value.canonicalOwner}|kind=constructor|" +
        "abi=$appleCanonicalAbiPackage/${value.canonicalOwner}.<init>|" +
        "<init>(${value.parameters.joinToString(";") { it.type.abi }}){}[0]|" +
        "return=$appleCanonicalPackage/${value.canonicalOwner}|suspend=false|parameters=[" +
        value.parameters.joinToString(",") {
            "REGULAR:${it.type.canonical}:default=${it.hasDefault}:vararg=false"
        } + "]"

private val d065OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d065AppleEnums.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        owner.entries.forEach { (canonical, apple) ->
            add(AppleOrdinaryCapability(appleEnumKey(owner.canonicalOwner, canonical), "$ownerUsr(cpy)$apple"))
        }
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
    d065AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 158 && capabilities.map { it.canonicalKey }.distinct().size == 158 &&
        capabilities.map { it.usr }.distinct().size == 158
    ) { "D065 Apple ordinary capability inventory changed" }
}
private val d065OrdinaryCapabilitiesByKey = d065OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d073OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 81 && capabilities.map { it.canonicalKey }.distinct().size == 81 &&
        capabilities.map { it.usr }.distinct().size == 81
    ) { "D073 Apple ordinary capability inventory changed" }
}
private val d073OrdinaryCapabilitiesByKey = d073OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d074OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 83 && capabilities.map { it.canonicalKey }.distinct().size == 83 &&
        capabilities.map { it.usr }.distinct().size == 83
    ) { "D074 Apple ordinary capability inventory changed" }
}
private val d074OrdinaryCapabilitiesByKey = d074OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d075OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 9 && capabilities.map { it.canonicalKey }.distinct().size == 9 &&
        capabilities.map { it.usr }.distinct().size == 9
    ) { "D075 Apple ordinary capability inventory changed" }
}
private val d075OrdinaryCapabilitiesByKey = d075OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d076AuthorizationUrlCapabilities = listOf(
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl.Companion|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.Companion.chatGpt|" +
            "chatGpt(kotlin.String){}[0]|return=$appleCanonicalPackage/CodexAuthorizationUrl!!|" +
            "suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
        appleAuthorizationChatGptUsr,
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl.Companion|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.Companion.external|" +
            "external(kotlin.String){}[0]|return=$appleCanonicalPackage/CodexAuthorizationUrl!!|" +
            "suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
        appleAuthorizationExternalUsr,
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl|kind=property|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.value|{}value[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        appleAuthorizationValueUsr,
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl|kind=property|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.purpose|{}purpose[0]|propertyKind=VAL|" +
            "type=$appleCanonicalPackage/CodexAuthorizationPurpose!!",
        appleAuthorizationPurposeUsr,
    ),
).also { capabilities ->
    check(capabilities.size == 4 && capabilities.map { it.canonicalKey }.distinct().size == 4 &&
        capabilities.map { it.usr }.distinct().size == 4
    ) { "D076 Apple authorization URL capability inventory changed" }
}
private val d076AuthorizationUrlCapabilitiesByKey = d076AuthorizationUrlCapabilities.associateBy {
    it.canonicalKey
}

private val d077OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 12 && capabilities.map { it.canonicalKey }.distinct().size == 12 &&
        capabilities.map { it.usr }.distinct().size == 12
    ) { "D077 Apple ordinary capability inventory changed" }
}
private val d077OrdinaryCapabilitiesByKey = d077OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d078OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 33 && capabilities.map { it.canonicalKey }.distinct().size == 33 &&
        capabilities.map { it.usr }.distinct().size == 33
    ) { "D078 Apple ordinary capability inventory changed" }
}
private val d078OrdinaryCapabilitiesByKey = d078OrdinaryCapabilities.associateBy { it.canonicalKey }


private val expectedAppleTests = listOf(
    "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
    swiftFailureTest,
    objectiveCFailureTest,
    "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
).sorted()

internal data class AppleBindingTargetDigests(
    val frameworkSha256: String,
    val binarySha256: String,
    val headerSha256: String,
    val moduleMapSha256: String,
)

internal data class AppleBindingInputDigests(
    val compilerEvidenceSha256: String,
    val xcframeworkSha256: String,
    val swiftConsumerSha256: String,
    val objectiveCConsumerSha256: String,
    val xctestEvidenceSha256: String,
    val xcresultSha256: String,
    val targets: Map<String, AppleBindingTargetDigests>,
)

private data class AppleCompilerClaim(
    val canonicalKey: String,
    val swiftUsr: String,
    val objectiveCUsr: String,
)


private fun swiftConstructorTitle(parameters: List<AppleOrdinaryParameter>): String =
    "init(${parameters.joinToString("") { "${it.name}:" }})"

private fun d065ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d065AppleEnums.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        owner.entries.forEach { (_, apple) ->
            put("$ownerUsr(cpy)$apple", ExpectedAppleCompilerSymbol(
                "swift.type.property", listOf(owner.swiftName, apple), apple, "open",
                "class var $apple: ${owner.swiftName} { get }", listOf(ownerUsr),
            ))
        }
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
    d065AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.map { it.type.swiftIdentifier },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
}

private fun d073ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.map { it.type.swiftIdentifier },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
}

private fun d074ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.map { it.type.swiftIdentifier },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
}

private fun d075ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.map { it.type.swiftIdentifier },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
}

private fun d076ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    APPLE_AUTHORIZATION_URL_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("CodexAuthorizationUrl"), "CodexAuthorizationUrl", "public",
        "class CodexAuthorizationUrl", emptyList(),
    ),
    APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("CodexAuthorizationUrl", "Companion"),
        "CodexAuthorizationUrl.Companion", "public", "class Companion", emptyList(),
    ),
    appleAuthorizationChatGptUsr to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexAuthorizationUrl", "Companion", "chatGpt(value:)"),
        "chatGpt(value:)", "open", "func chatGpt(value: String) -> CodexAuthorizationUrl",
        listOf("s:SS", APPLE_AUTHORIZATION_URL_OWNER_USR), listOf("value" to "value: String"),
        "CodexAuthorizationUrl",
    ),
    appleAuthorizationExternalUsr to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexAuthorizationUrl", "Companion", "external(value:)"),
        "external(value:)", "open", "func external(value: String) -> CodexAuthorizationUrl",
        listOf("s:SS", APPLE_AUTHORIZATION_URL_OWNER_USR), listOf("value" to "value: String"),
        "CodexAuthorizationUrl",
    ),
    appleAuthorizationValueUsr to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexAuthorizationUrl", "value"), "value", "open",
        "var value: String { get }", listOf("s:SS"),
    ),
    appleAuthorizationPurposeUsr to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexAuthorizationUrl", "purpose"), "purpose", "open",
        "var purpose: CodexAuthorizationPurpose { get }",
        listOf("c:objc(cs)CodexAgentCodexAuthorizationPurpose"),
    ),
)

private fun d077ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.map { it.type.swiftIdentifier },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                listOf(property.type.swiftIdentifier),
            ))
        }
    }
}

private fun d078ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner.swiftName), owner.swiftName, "public",
            "class ${owner.swiftName}", emptyList(),
        ))
        val title = swiftConstructorTitle(owner.parameters)
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "swift.init", listOf(owner.swiftName, title), title, "public",
            "init(${owner.parameters.joinToString(", ") { "${it.name}: ${it.type.swift}" }})",
            owner.parameters.flatMap { it.type.swiftIdentifiers },
            owner.parameters.map { it.name to "${it.name}: ${it.type.swift}" },
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner.swiftName, property.appleName), property.appleName, "open",
                "var ${property.appleName}: ${property.type.swift} { get }",
                property.type.swiftIdentifiers,
            ))
        }
    }
}

private fun objectiveCConstructorDeclaration(owner: AppleOrdinaryValue): String {
    val parameters = owner.parameters.mapIndexed { index, parameter ->
        val selector = if (index == 0) {
            "initWith${parameter.name.replaceFirstChar(Char::uppercaseChar)}:"
        } else {
            "${parameter.name}:"
        }
        "$selector(${parameter.type.objectiveC}) ${parameter.name}"
    }
    return "- (instancetype) ${parameters.joinToString(" ")};"
}

private fun d065ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d065AppleEnums.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentKotlinEnum",
            listOf("c:objc(cs)CodexAgentKotlinEnum"),
        ))
        owner.entries.forEach { (_, apple) ->
            put("$ownerUsr(cpy)$apple", ExpectedAppleCompilerSymbol(
                "objective-c.type.property", listOf(owner.objectiveCName, apple), apple, "public",
                "@property (class, readonly) ${owner.objectiveCName} * $apple;", listOf(ownerUsr),
            ))
        }
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
    d065AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun d073ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun d074ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun d075ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun d076ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    APPLE_AUTHORIZATION_URL_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentCodexAuthorizationUrl"),
        "CodexAgentCodexAuthorizationUrl", "public",
        "@interface CodexAgentCodexAuthorizationUrl : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"),
    ),
    APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentCodexAuthorizationUrlCompanion"),
        "CodexAgentCodexAuthorizationUrlCompanion", "public",
        "@interface CodexAgentCodexAuthorizationUrlCompanion : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"),
    ),
    appleAuthorizationChatGptUsr to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexAuthorizationUrlCompanion", "chatGptValue:"),
        "chatGptValue:", "public",
        "- (CodexAgentCodexAuthorizationUrl *) chatGptValue:(NSString *) value;",
        listOf(APPLE_AUTHORIZATION_URL_OWNER_USR, "c:objc(cs)NSString"),
        listOf("value" to "(NSString *) value"), "CodexAgentCodexAuthorizationUrl *",
    ),
    appleAuthorizationExternalUsr to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexAuthorizationUrlCompanion", "externalValue:"),
        "externalValue:", "public",
        "- (CodexAgentCodexAuthorizationUrl *) externalValue:(NSString *) value;",
        listOf(APPLE_AUTHORIZATION_URL_OWNER_USR, "c:objc(cs)NSString"),
        listOf("value" to "(NSString *) value"), "CodexAgentCodexAuthorizationUrl *",
    ),
    appleAuthorizationValueUsr to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexAuthorizationUrl", "value"),
        "value", "public", "@property (readonly) NSString * value;", listOf("c:objc(cs)NSString"),
    ),
    appleAuthorizationPurposeUsr to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexAuthorizationUrl", "purpose"),
        "purpose", "public", "@property (readonly) CodexAgentCodexAuthorizationPurpose * purpose;",
        listOf("c:objc(cs)CodexAgentCodexAuthorizationPurpose"),
    ),
)

private fun d077ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun d078ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(owner.objectiveCName), owner.objectiveCName, "public",
            "@interface ${owner.objectiveCName} : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(im)${owner.objectiveCSelector}", ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf(owner.objectiveCName, owner.objectiveCSelector),
            owner.objectiveCSelector, "public", objectiveCConstructorDeclaration(owner),
            owner.parameters.map { it.type.objectiveCIdentifier },
            owner.parameters.map { it.name to "(${it.type.objectiveC}) ${it.name}" },
            "instancetype",
        ))
        owner.properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(owner.objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private fun Map<String, ExpectedAppleCompilerSymbol>.appleSymbols(interfaceLanguage: String): List<AppleCompilerSymbol> =
    map { (precise, symbol) ->
        AppleCompilerSymbol(
            precise, interfaceLanguage, symbol.kind, symbol.path, symbol.title, symbol.access,
            symbol.declaration, symbol.typeIdentifiers, symbol.parameters, symbol.returns,
        )
    }

internal fun deriveCrossLanguageAppleBindingEvidence(
    canonical: CrossLanguageCanonicalApiEvidence,
    compilerEvidence: JsonObject,
    xctestEvidence: JsonObject,
    digests: AppleBindingInputDigests,
): JsonObject {
    listOf(
        "compiler evidence" to digests.compilerEvidenceSha256,
        "XCFramework" to digests.xcframeworkSha256,
        "Swift consumer" to digests.swiftConsumerSha256,
        "Objective-C consumer" to digests.objectiveCConsumerSha256,
        "XCTest evidence" to digests.xctestEvidenceSha256,
        "xcresult" to digests.xcresultSha256,
    ).forEach { (label, digest) -> digest.appleSha256(label) }
    digests.targets.forEach { (target, values) ->
        listOf(
            "framework" to values.frameworkSha256,
            "binary" to values.binarySha256,
            "header" to values.headerSha256,
            "module map" to values.moduleMapSha256,
        ).forEach { (label, digest) -> digest.appleSha256("$target $label") }
    }
    check(canonical.memberKeys.size == APPLE_BINDING_CANONICAL_CAPABILITY_COUNT) {
        "Apple binding evidence requires exactly $APPLE_BINDING_CANONICAL_CAPABILITY_COUNT canonical capabilities"
    }
    check(canonical.memberKeys == canonical.memberKeys.distinct().sorted()) {
        "Apple binding canonical capability inventory is duplicated or unsorted"
    }
    canonical.canonical.apiReportSha256.appleSha256("canonical API report")
    canonical.canonical.coverageReceiptSha256.appleSha256("canonical coverage receipt")
    canonical.targetSha256.getValue("native").appleSha256("canonical native target")
    val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)
    check(capabilities.size == 396) { "Apple binding capability count changed" }
    val usrByCapability = capabilities.associateWith(::appleBindingUsr)

    compilerEvidence.appleKeys(
        "Apple compiler evidence",
        "schemaVersion", "protocol", "result", "moduleName", "canonical", "toolchain", "artifacts",
        "targets", "surface", "references", "claims",
    )
    check(compilerEvidence.appleInt("schemaVersion") == 1) { "Unsupported Apple compiler evidence schema" }
    check(compilerEvidence.appleString("protocol") == APPLE_COMPILER_EVIDENCE_PROTOCOL) {
        "Unsupported Apple compiler evidence protocol"
    }
    check(compilerEvidence.appleString("result") == "observed") { "Apple compiler evidence was not observed" }
    check(compilerEvidence.appleString("moduleName") == "CodexAgent") { "Apple compiler module changed" }

    val compilerCanonical = compilerEvidence.appleObject("canonical").also {
        it.appleKeys(
            "Apple compiler canonical identity",
            "apiReportSha256", "coverageReceiptSha256", "nativeTargetSha256", "capabilities",
        )
    }
    check(compilerCanonical.appleSha256("apiReportSha256") == canonical.canonical.apiReportSha256 &&
        compilerCanonical.appleSha256("coverageReceiptSha256") == canonical.canonical.coverageReceiptSha256 &&
        compilerCanonical.appleSha256("nativeTargetSha256") == canonical.targetSha256.getValue("native") &&
        compilerCanonical.appleStrings("capabilities") == capabilities
    ) { "Apple compiler evidence canonical identity changed" }

    compilerEvidence.appleObject("toolchain").also { toolchain ->
        toolchain.appleKeys(
            "Apple compiler toolchain", "xcodeVersion", "xcodeBuild", "swiftVersion", "clangVersion",
        )
        listOf("xcodeVersion", "xcodeBuild", "swiftVersion", "clangVersion").forEach { name ->
            toolchain.appleString(name).appleRecord("Apple compiler toolchain $name")
        }
    }
    val compilerArtifacts = compilerEvidence.appleObject("artifacts").also {
        it.appleKeys(
            "Apple compiler artifacts", "xcframeworkSha256", "swiftConsumerSha256", "objectiveCConsumerSha256",
        )
    }
    check(compilerArtifacts.appleSha256("xcframeworkSha256") == digests.xcframeworkSha256 &&
        compilerArtifacts.appleSha256("swiftConsumerSha256") == digests.swiftConsumerSha256 &&
        compilerArtifacts.appleSha256("objectiveCConsumerSha256") == digests.objectiveCConsumerSha256
    ) { "Apple compiler artifact identity changed" }

    validateAppleTargets(compilerEvidence.appleArray("targets"), digests.targets)
    val surfaces = compilerEvidence.appleObject("surface").also {
        it.appleKeys("Apple compiler surfaces", "swiftSha256", "objectiveCSha256", "swift", "objectiveC")
    }
    val swiftSurfaceJson = surfaces.appleArray("swift")
    val objectiveCSurfaceJson = surfaces.appleArray("objectiveC")
    check(surfaces.appleSha256("swiftSha256") == appleCompilerJsonDigest(swiftSurfaceJson) &&
        surfaces.appleSha256("objectiveCSha256") == appleCompilerJsonDigest(objectiveCSurfaceJson)
    ) { "Apple compiler surface digest changed" }
    val swiftSurface = swiftSurfaceJson.map { it.appleSymbol() }
    val objectiveCSurface = objectiveCSurfaceJson.map { it.appleSymbol() }
    check(swiftSurface == expectedSwiftAppleBindingSurface()) { "Swift Apple binding compiler surface changed" }
    check(objectiveCSurface == expectedObjectiveCAppleBindingSurface()) {
        "Objective-C Apple binding compiler surface changed"
    }

    val references = compilerEvidence.appleObject("references").also {
        it.appleKeys("Apple compiler references", "swiftSha256", "objectiveCSha256", "swift", "objectiveC")
    }
    val swiftReferencesJson = references.appleArray("swift")
    val objectiveCReferencesJson = references.appleArray("objectiveC")
    check(references.appleSha256("swiftSha256") == appleCompilerJsonDigest(swiftReferencesJson) &&
        references.appleSha256("objectiveCSha256") == appleCompilerJsonDigest(objectiveCReferencesJson)
    ) { "Apple compiler reference digest changed" }
    val swiftReferences = swiftReferencesJson.map { it.appleReference() }
    val objectiveCReferences = objectiveCReferencesJson.map { it.appleReference() }
    check(swiftReferences == expectedSwiftAppleBindingReferences()) {
        "Swift Apple binding compiler references changed"
    }
    check(objectiveCReferences == expectedObjectiveCAppleBindingReferences()) {
        "Objective-C Apple binding compiler references changed"
    }

    val compilerClaims = compilerEvidence.appleArray("claims").map { value ->
        val claim = value.appleObject("Apple compiler claim").also {
            it.appleKeys("Apple compiler claim", "canonicalKey", "swiftUsr", "objectiveCUsr")
        }
        AppleCompilerClaim(
            claim.appleString("canonicalKey"),
            claim.appleString("swiftUsr"),
            claim.appleString("objectiveCUsr"),
        )
    }
    val expectedClaims = capabilities.map { capability ->
        AppleCompilerClaim(capability, usrByCapability.getValue(capability), usrByCapability.getValue(capability))
    }
    check(compilerClaims == expectedClaims) { "Apple compiler claims changed" }

    validateAppleXCTestEvidence(xctestEvidence, digests.xcresultSha256)
    val missing = (canonical.memberKeys.toSet() - capabilities.toSet()).sorted()
    check(missing.size == 160) { "Apple partial binding gap count changed: ${missing.size}" }
    val swiftSymbols = swiftSurface.map(AppleCompilerSymbol::precise).sorted()
    val objectiveCSymbols = objectiveCSurface.map(AppleCompilerSymbol::precise).sorted()
    val swiftReferenced = swiftReferences.map(AppleCompilerReference::precise).sorted()
    val objectiveCReferenced = objectiveCReferences.map(AppleCompilerReference::precise).sorted()

    return buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("protocol", JsonPrimitive(APPLE_BINDING_EVIDENCE_PROTOCOL))
        put("result", JsonPrimitive("observed"))
        put("canonical", buildJsonObject {
            put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
            put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
            put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
            put("capabilityCount", JsonPrimitive(canonical.memberKeys.size))
        })
        put("artifacts", buildJsonObject {
            put("compilerEvidenceSha256", JsonPrimitive(digests.compilerEvidenceSha256))
            put("xcframeworkSha256", JsonPrimitive(digests.xcframeworkSha256))
            put("swiftConsumerSha256", JsonPrimitive(digests.swiftConsumerSha256))
            put("objectiveCConsumerSha256", JsonPrimitive(digests.objectiveCConsumerSha256))
            put("xctestEvidenceSha256", JsonPrimitive(digests.xctestEvidenceSha256))
            put("xcresultSha256", JsonPrimitive(digests.xcresultSha256))
        })
        put("languages", buildJsonArray {
            add(appleLanguageEvidence(
                "objective-c", objectiveCSymbols, objectiveCReferenced, capabilities,
                usrByCapability, objectiveCFailureTest, missing,
            ))
            add(appleLanguageEvidence(
                "swift", swiftSymbols, swiftReferenced, capabilities,
                usrByCapability, swiftFailureTest, missing,
            ))
        })
    }
}

private fun validateAppleTargets(
    values: JsonArray,
    actualDigests: Map<String, AppleBindingTargetDigests>,
) {
    val expectedTargets = linkedMapOf(
        "ios-arm64" to Pair("iphoneos", "arm64-apple-ios15.0"),
        "ios-arm64-simulator" to Pair("iphonesimulator", "arm64-apple-ios15.0-simulator"),
    )
    check(actualDigests.keys == expectedTargets.keys) { "Apple compiler target artifacts changed" }
    val targets = values.map { value ->
        val target = value.appleObject("Apple compiler target").also {
            it.appleKeys(
                "Apple compiler target", "name", "sdk", "sdkVersion", "targetTriple",
                "frameworkSha256", "binarySha256", "headerSha256", "moduleMapSha256",
            )
        }
        val name = target.appleString("name")
        val expected = expectedTargets[name] ?: error("Unexpected Apple compiler target: $name")
        check(target.appleString("sdk") == expected.first && target.appleString("targetTriple") == expected.second) {
            "Apple compiler target identity changed: $name"
        }
        check(target.appleString("sdkVersion").matches(Regex("[0-9]+(?:\\.[0-9]+)*"))) {
            "Apple compiler SDK version is invalid: $name"
        }
        val actual = actualDigests.getValue(name)
        check(target.appleSha256("frameworkSha256") == actual.frameworkSha256 &&
            target.appleSha256("binarySha256") == actual.binarySha256 &&
            target.appleSha256("headerSha256") == actual.headerSha256 &&
            target.appleSha256("moduleMapSha256") == actual.moduleMapSha256
        ) { "Apple compiler target artifact changed: $name" }
        name to actual
    }
    check(targets.map(Pair<String, AppleBindingTargetDigests>::first) == expectedTargets.keys.toList()) {
        "Apple compiler target inventory changed"
    }
    check(targets.map { it.second.headerSha256 }.distinct().size == 1 &&
        targets.map { it.second.moduleMapSha256 }.distinct().size == 1
    ) { "Apple compiler device and simulator interfaces differ" }
}

private fun validateAppleXCTestEvidence(evidence: JsonObject, xcresultSha256: String) {
    evidence.appleKeys(
        "Apple XCTest evidence",
        "schemaVersion", "protocol", "result", "totalTestCount", "failedTests", "xcresultSha256", "tests",
    )
    check(evidence.appleInt("schemaVersion") == 1 &&
        evidence.appleString("protocol") == appleXCTestProtocol &&
        evidence.appleString("result") == "passed" &&
        evidence.appleInt("totalTestCount") == expectedAppleTests.size &&
        evidence.appleInt("failedTests") == 0 &&
        evidence.appleSha256("xcresultSha256") == xcresultSha256
    ) { "Apple XCTest evidence identity or result changed" }
    val tests = evidence.appleArray("tests").map { value ->
        val test = value.appleObject("Apple XCTest result").also {
            it.appleKeys("Apple XCTest result", "identifier", "status")
        }
        test.appleString("identifier") to test.appleString("status")
    }
    check(tests == expectedAppleTests.map { it to "Passed" }) { "Apple XCTest inventory or status changed" }
}

private fun appleLanguageEvidence(
    language: String,
    publicSymbols: List<String>,
    referencedSymbols: List<String>,
    capabilities: List<String>,
    usrByCapability: Map<String, String>,
    behaviorTest: String,
    missing: List<String>,
) = buildJsonObject {
    val ownerUsrs = expectedSwiftAppleBindingSurface()
        .filter { it.kind == "swift.class" }
        .map(AppleCompilerSymbol::precise)
        .toSet()
    check(publicSymbols.size == 481 && referencedSymbols.size == 396 && ownerUsrs.size == 85 &&
        referencedSymbols.toSet() == publicSymbols.toSet() - ownerUsrs
    ) { "$language Apple binding symbol/reference inventory changed" }
    put("language", JsonPrimitive(language))
    put("publicSymbols", publicSymbols.appleJsonStrings())
    put("referencedSymbols", referencedSymbols.appleJsonStrings())
    put("claims", buildJsonArray {
        capabilities.forEach { capability ->
            val usr = usrByCapability.getValue(capability)
            add(buildJsonObject {
                put("canonicalKey", JsonPrimitive(capability))
                put("publicSymbol", JsonPrimitive(usr))
                put("compilerReference", JsonPrimitive(usr))
                put("behaviorTest", JsonPrimitive(behaviorTest))
            })
        }
    })
    put("exclusions", buildJsonArray {})
    put("missingCapabilityKeys", missing.appleJsonStrings())
}

private fun appleBindingUsr(capability: String): String =
    d065OrdinaryCapabilitiesByKey[capability]?.usr
        ?: d073OrdinaryCapabilitiesByKey[capability]?.usr
        ?: d074OrdinaryCapabilitiesByKey[capability]?.usr
        ?: d075OrdinaryCapabilitiesByKey[capability]?.usr
        ?: d076AuthorizationUrlCapabilitiesByKey[capability]?.usr
        ?: d077OrdinaryCapabilitiesByKey[capability]?.usr
        ?: d078OrdinaryCapabilitiesByKey[capability]?.usr ?: when {
    "|owner=io.github.codex_agent_labs.codexmobile.agent/CodexFailure|kind=constructor|" in capability ->
        appleFailureConstructorUsr
    "|owner=io.github.codex_agent_labs.codexmobile.agent/ConversationId|kind=constructor|" in capability ->
        appleConversationIdConstructorUsr
    "|owner=io.github.codex_agent_labs.codexmobile.agent/ConversationId|kind=property|" in capability &&
        "|{}value[0]|" in capability -> appleConversationIdValueUsr
    "|{}code[0]|" in capability -> appleFailureCodeUsr
    "|{}isRecoverable[0]|" in capability -> appleFailureRecoverableUsr
    "|{}message[0]|" in capability -> appleFailureMessageUsr
    ".ACCEPT|null[0]" in capability -> appleApprovalAcceptUsr
    ".DECLINE|null[0]" in capability -> appleApprovalDeclineUsr
    ".DEFAULT|null[0]" in capability -> appleCollaborationDefaultUsr
    ".PLAN|null[0]" in capability -> appleCollaborationPlanUsr
    ".USER|null[0]" in capability -> appleMessageRoleUserUsr
    ".ASSISTANT|null[0]" in capability -> appleMessageRoleAssistantUsr
    ".User|null[0]" in capability -> appleInstallationScopeUserUsr
    ".Workspace|null[0]" in capability -> appleInstallationScopeWorkspaceUsr
    ".LOCAL|null[0]" in capability -> appleMcpEnvironmentLocalUsr
    ".REMOTE|null[0]" in capability -> appleMcpEnvironmentRemoteUsr
        else -> error("Unexpected canonical Apple binding capability: $capability")
    }

private fun expectedSwiftAppleBindingSurface(): List<AppleCompilerSymbol> = listOf(
    AppleCompilerSymbol(
        APPLE_CODEX_FAILURE_OWNER_USR, "swift", "swift.class", listOf("CodexFailure"),
        "CodexFailure", "public", "class CodexFailure", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureConstructorUsr, "swift", "swift.init",
        listOf("CodexFailure", "init(code:message:isRecoverable:)"),
        "init(code:message:isRecoverable:)", "public",
        "init(code: String, message: String, isRecoverable: Bool)", listOf("s:SS", "s:SS", "s:Sb"),
        listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
        null,
    ),
    AppleCompilerSymbol(
        appleFailureCodeUsr, "swift", "swift.property", listOf("CodexFailure", "code"),
        "code", "open", "var code: String { get }", listOf("s:SS"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureRecoverableUsr, "swift", "swift.property", listOf("CodexFailure", "isRecoverable"),
        "isRecoverable", "open", "var isRecoverable: Bool { get }", listOf("s:Sb"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureMessageUsr, "swift", "swift.property", listOf("CodexFailure", "message"),
        "message", "open", "var message: String { get }", listOf("s:SS"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_CONVERSATION_ID_OWNER_USR, "swift", "swift.class", listOf("ConversationId"),
        "ConversationId", "public", "class ConversationId", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleConversationIdConstructorUsr, "swift", "swift.init", listOf("ConversationId", "init(value:)"),
        "init(value:)", "public", "init(value: String)", listOf("s:SS"),
        listOf("value" to "value: String"), null,
    ),
    AppleCompilerSymbol(
        appleConversationIdValueUsr, "swift", "swift.property", listOf("ConversationId", "value"),
        "value", "open", "var value: String { get }", listOf("s:SS"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_APPROVAL_DECISION_OWNER_USR, "swift", "swift.class", listOf("AgentApprovalDecision"),
        "AgentApprovalDecision", "public", "class AgentApprovalDecision", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalAcceptUsr, "swift", "swift.type.property", listOf("AgentApprovalDecision", "accept"),
        "accept", "open", "class var accept: AgentApprovalDecision { get }",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalDeclineUsr, "swift", "swift.type.property", listOf("AgentApprovalDecision", "decline"),
        "decline", "open", "class var decline: AgentApprovalDecision { get }",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_COLLABORATION_MODE_OWNER_USR, "swift", "swift.class", listOf("AgentCollaborationMode"),
        "AgentCollaborationMode", "public", "class AgentCollaborationMode", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleCollaborationDefaultUsr, "swift", "swift.type.property",
        listOf("AgentCollaborationMode", "default_"), "default_", "open",
        "class var default_: AgentCollaborationMode { get }",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleCollaborationPlanUsr, "swift", "swift.type.property", listOf("AgentCollaborationMode", "plan"),
        "plan", "open", "class var plan: AgentCollaborationMode { get }",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_MESSAGE_ROLE_OWNER_USR, "swift", "swift.class", listOf("AgentMessageRole"),
        "AgentMessageRole", "public", "class AgentMessageRole", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMessageRoleUserUsr, "swift", "swift.type.property", listOf("AgentMessageRole", "user"),
        "user", "open", "class var user: AgentMessageRole { get }",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMessageRoleAssistantUsr, "swift", "swift.type.property",
        listOf("AgentMessageRole", "assistant"), "assistant", "open",
        "class var assistant: AgentMessageRole { get }",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_INSTALLATION_SCOPE_OWNER_USR, "swift", "swift.class", listOf("AgentInstallationScope"),
        "AgentInstallationScope", "public", "class AgentInstallationScope", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleInstallationScopeUserUsr, "swift", "swift.type.property", listOf("AgentInstallationScope", "user"),
        "user", "open", "class var user: AgentInstallationScope { get }",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleInstallationScopeWorkspaceUsr, "swift", "swift.type.property",
        listOf("AgentInstallationScope", "workspace"), "workspace", "open",
        "class var workspace: AgentInstallationScope { get }",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR, "swift", "swift.class", listOf("AgentMcpEnvironmentSource"),
        "AgentMcpEnvironmentSource", "public", "class AgentMcpEnvironmentSource", emptyList(), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMcpEnvironmentLocalUsr, "swift", "swift.type.property",
        listOf("AgentMcpEnvironmentSource", "local"), "local", "open",
        "class var local: AgentMcpEnvironmentSource { get }",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMcpEnvironmentRemoteUsr, "swift", "swift.type.property",
        listOf("AgentMcpEnvironmentSource", "remote"), "remote", "open",
        "class var remote: AgentMcpEnvironmentSource { get }",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR), emptyList(), null,
    ),
).plus(d065ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d073ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d074ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d075ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d076ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d077ExpectedSwiftSymbols().appleSymbols("swift"))
    .plus(d078ExpectedSwiftSymbols().appleSymbols("swift")).sortedBy(AppleCompilerSymbol::precise)

private fun expectedObjectiveCAppleBindingSurface(): List<AppleCompilerSymbol> = listOf(
    AppleCompilerSymbol(
        APPLE_CODEX_FAILURE_OWNER_USR, "objective-c", "objective-c.class", listOf("CodexAgentCodexFailure"),
        "CodexAgentCodexFailure", "public", "@interface CodexAgentCodexFailure : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureConstructorUsr, "objective-c", "objective-c.method",
        listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
        "initWithCode:message:isRecoverable:", "public",
        "- (instancetype) initWithCode:(NSString *) code message:(NSString *) message " +
            "isRecoverable:(BOOL) isRecoverable;",
        listOf("c:objc(cs)NSString", "c:objc(cs)NSString", "c:@T@BOOL"),
        listOf(
            "code" to "(NSString *) code",
            "message" to "(NSString *) message",
            "isRecoverable" to "(BOOL) isRecoverable",
        ),
        "instancetype",
    ),
    AppleCompilerSymbol(
        appleFailureCodeUsr, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "code"),
        "code", "public", "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureRecoverableUsr, "objective-c", "objective-c.property",
        listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
        "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleFailureMessageUsr, "objective-c", "objective-c.property", listOf("CodexAgentCodexFailure", "message"),
        "message", "public", "@property (readonly) NSString * message;",
        listOf("c:objc(cs)NSString"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_CONVERSATION_ID_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentConversationId"), "CodexAgentConversationId", "public",
        "@interface CodexAgentConversationId : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleConversationIdConstructorUsr, "objective-c", "objective-c.method",
        listOf("CodexAgentConversationId", "initWithValue:"), "initWithValue:", "public",
        "- (instancetype) initWithValue:(NSString *) value;", listOf("c:objc(cs)NSString"),
        listOf("value" to "(NSString *) value"), "instancetype",
    ),
    AppleCompilerSymbol(
        appleConversationIdValueUsr, "objective-c", "objective-c.property",
        listOf("CodexAgentConversationId", "value"), "value", "public",
        "@property (readonly) NSString * value;", listOf("c:objc(cs)NSString"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_APPROVAL_DECISION_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentApprovalDecision"), "CodexAgentAgentApprovalDecision", "public",
        "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalAcceptUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleApprovalDeclineUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_COLLABORATION_MODE_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentCollaborationMode"), "CodexAgentAgentCollaborationMode", "public",
        "@interface CodexAgentAgentCollaborationMode : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleCollaborationDefaultUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentCollaborationMode", "default_"), "default_", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * default_;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleCollaborationPlanUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentCollaborationMode", "plan"), "plan", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * plan;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_MESSAGE_ROLE_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentMessageRole"), "CodexAgentAgentMessageRole", "public",
        "@interface CodexAgentAgentMessageRole : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMessageRoleUserUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentMessageRole", "user"), "user", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * user;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMessageRoleAssistantUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentMessageRole", "assistant"), "assistant", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * assistant;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_INSTALLATION_SCOPE_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentInstallationScope"), "CodexAgentAgentInstallationScope", "public",
        "@interface CodexAgentAgentInstallationScope : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleInstallationScopeUserUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentInstallationScope", "user"), "user", "public",
        "@property (class, readonly) CodexAgentAgentInstallationScope * user;",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleInstallationScopeWorkspaceUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentInstallationScope", "workspace"), "workspace", "public",
        "@property (class, readonly) CodexAgentAgentInstallationScope * workspace;",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR, "objective-c", "objective-c.class",
        listOf("CodexAgentAgentMcpEnvironmentSource"), "CodexAgentAgentMcpEnvironmentSource", "public",
        "@interface CodexAgentAgentMcpEnvironmentSource : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMcpEnvironmentLocalUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentMcpEnvironmentSource", "local"), "local", "public",
        "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * local;",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR), emptyList(), null,
    ),
    AppleCompilerSymbol(
        appleMcpEnvironmentRemoteUsr, "objective-c", "objective-c.type.property",
        listOf("CodexAgentAgentMcpEnvironmentSource", "remote"), "remote", "public",
        "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * remote;",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR), emptyList(), null,
    ),
).plus(d065ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d073ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d074ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d075ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d076ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d077ExpectedObjectiveCSymbols().appleSymbols("objective-c"))
    .plus(d078ExpectedObjectiveCSymbols().appleSymbols("objective-c")).sortedBy(AppleCompilerSymbol::precise)

private fun d065ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d065AppleEnums.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        owner.entries.forEach { (_, apple) ->
            add(AppleCompilerReference("$ownerUsr(cpy)$apple", "member_ref_expr", apple, null,
                owner.swiftAst, emptyList()))
        }
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d065AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d065ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d065AppleEnums.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        owner.entries.forEach { (_, apple) ->
            add(AppleCompilerReference("$ownerUsr(cpy)$apple", "ObjCMessageExpr", apple,
                owner.objectiveCName, "${owner.objectiveCName} * _Nonnull", emptyList()))
        }
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
    d065AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun d073ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d073ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun d074ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d074ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun d075ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d075ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun d076ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleAuthorizationChatGptUsr, "declref_expr", "chatGpt", null,
        "\$sySo010CodexAgentA16AuthorizationUrlCSS_tcSo0abacD9CompanionCcD", emptyList(),
    ),
    AppleCompilerReference(
        appleAuthorizationExternalUsr, "declref_expr", "external", null,
        "\$sySo010CodexAgentA16AuthorizationUrlCSS_tcSo0abacD9CompanionCcD", emptyList(),
    ),
    AppleCompilerReference(appleAuthorizationValueUsr, "member_ref_expr", "value", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleAuthorizationPurposeUsr, "member_ref_expr", "purpose", null,
        "\$sSo010CodexAgentA20AuthorizationPurposeCD", emptyList(),
    ),
)

private fun d076ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleAuthorizationChatGptUsr, "ObjCMessageExpr", "chatGptValue:",
        "CodexAgentCodexAuthorizationUrlCompanion *", "CodexAgentCodexAuthorizationUrl *",
        listOf("NSString *"),
    ),
    AppleCompilerReference(
        appleAuthorizationExternalUsr, "ObjCMessageExpr", "externalValue:",
        "CodexAgentCodexAuthorizationUrlCompanion *", "CodexAgentCodexAuthorizationUrl *",
        listOf("NSString *"),
    ),
    AppleCompilerReference(
        appleAuthorizationValueUsr, "ObjCPropertyRefExpr", "value", "CodexAgentCodexAuthorizationUrl *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleAuthorizationPurposeUsr, "ObjCPropertyRefExpr", "purpose", "CodexAgentCodexAuthorizationUrl *",
        "<pseudo-object type>", emptyList(),
    ),
)

private fun d077ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d077ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun d078ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
}

private fun d078ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
}

private fun expectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleFailureConstructorUsr, "declref_expr", "init", null,
        "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD", emptyList(),
    ),
    AppleCompilerReference(appleFailureCodeUsr, "member_ref_expr", "code", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleFailureRecoverableUsr, "member_ref_expr", "isRecoverable", null, "\$sSbD", emptyList(),
    ),
    AppleCompilerReference(appleFailureMessageUsr, "member_ref_expr", "message", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleConversationIdConstructorUsr, "declref_expr", "init", null,
        "\$sySo24CodexAgentConversationIdCSS_tcABmcD", emptyList(),
    ),
    AppleCompilerReference(appleConversationIdValueUsr, "member_ref_expr", "value", null, "\$sSSD", emptyList()),
    AppleCompilerReference(
        appleApprovalAcceptUsr, "member_ref_expr", "accept", null,
        "\$sSo010CodexAgentB16ApprovalDecisionCD", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalDeclineUsr, "member_ref_expr", "decline", null,
        "\$sSo010CodexAgentB16ApprovalDecisionCD", emptyList(),
    ),
    AppleCompilerReference(
        appleCollaborationDefaultUsr, "member_ref_expr", "default_", null,
        "\$sSo010CodexAgentB17CollaborationModeCD", emptyList(),
    ),
    AppleCompilerReference(
        appleCollaborationPlanUsr, "member_ref_expr", "plan", null,
        "\$sSo010CodexAgentB17CollaborationModeCD", emptyList(),
    ),
    AppleCompilerReference(
        appleMessageRoleUserUsr, "member_ref_expr", "user", null,
        "\$sSo010CodexAgentB11MessageRoleCD", emptyList(),
    ),
    AppleCompilerReference(
        appleMessageRoleAssistantUsr, "member_ref_expr", "assistant", null,
        "\$sSo010CodexAgentB11MessageRoleCD", emptyList(),
    ),
    AppleCompilerReference(
        appleInstallationScopeUserUsr, "member_ref_expr", "user", null,
        "\$sSo010CodexAgentB17InstallationScopeCD", emptyList(),
    ),
    AppleCompilerReference(
        appleInstallationScopeWorkspaceUsr, "member_ref_expr", "workspace", null,
        "\$sSo010CodexAgentB17InstallationScopeCD", emptyList(),
    ),
    AppleCompilerReference(
        appleMcpEnvironmentLocalUsr, "member_ref_expr", "local", null,
        "\$sSo010CodexAgentB20McpEnvironmentSourceCD", emptyList(),
    ),
    AppleCompilerReference(
        appleMcpEnvironmentRemoteUsr, "member_ref_expr", "remote", null,
        "\$sSo010CodexAgentB20McpEnvironmentSourceCD", emptyList(),
    ),
).plus(d065ExpectedSwiftAppleBindingReferences())
    .plus(d073ExpectedSwiftAppleBindingReferences())
    .plus(d074ExpectedSwiftAppleBindingReferences())
    .plus(d075ExpectedSwiftAppleBindingReferences())
    .plus(d076ExpectedSwiftAppleBindingReferences())
    .plus(d077ExpectedSwiftAppleBindingReferences())
    .plus(d078ExpectedSwiftAppleBindingReferences()).sortedBy(AppleCompilerReference::precise)

private fun expectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        appleFailureConstructorUsr, "ObjCMessageExpr", "initWithCode:message:isRecoverable:",
        "CodexAgentCodexFailure", "CodexAgentCodexFailure *", listOf("NSString *", "NSString *", "BOOL"),
    ),
    AppleCompilerReference(
        appleFailureCodeUsr, "ObjCPropertyRefExpr", "code", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleFailureRecoverableUsr, "ObjCPropertyRefExpr", "isRecoverable", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleFailureMessageUsr, "ObjCPropertyRefExpr", "message", "CodexAgentCodexFailure *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleConversationIdConstructorUsr, "ObjCMessageExpr", "initWithValue:",
        "CodexAgentConversationId", "CodexAgentConversationId *", listOf("NSString *"),
    ),
    AppleCompilerReference(
        appleConversationIdValueUsr, "ObjCPropertyRefExpr", "value", "CodexAgentConversationId *",
        "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalAcceptUsr, "ObjCMessageExpr", "accept", "CodexAgentAgentApprovalDecision",
        "CodexAgentAgentApprovalDecision * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleApprovalDeclineUsr, "ObjCMessageExpr", "decline", "CodexAgentAgentApprovalDecision",
        "CodexAgentAgentApprovalDecision * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleCollaborationDefaultUsr, "ObjCMessageExpr", "default_", "CodexAgentAgentCollaborationMode",
        "CodexAgentAgentCollaborationMode * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleCollaborationPlanUsr, "ObjCMessageExpr", "plan", "CodexAgentAgentCollaborationMode",
        "CodexAgentAgentCollaborationMode * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleMessageRoleUserUsr, "ObjCMessageExpr", "user", "CodexAgentAgentMessageRole",
        "CodexAgentAgentMessageRole * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleMessageRoleAssistantUsr, "ObjCMessageExpr", "assistant", "CodexAgentAgentMessageRole",
        "CodexAgentAgentMessageRole * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleInstallationScopeUserUsr, "ObjCMessageExpr", "user", "CodexAgentAgentInstallationScope",
        "CodexAgentAgentInstallationScope * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleInstallationScopeWorkspaceUsr, "ObjCMessageExpr", "workspace", "CodexAgentAgentInstallationScope",
        "CodexAgentAgentInstallationScope * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleMcpEnvironmentLocalUsr, "ObjCMessageExpr", "local", "CodexAgentAgentMcpEnvironmentSource",
        "CodexAgentAgentMcpEnvironmentSource * _Nonnull", emptyList(),
    ),
    AppleCompilerReference(
        appleMcpEnvironmentRemoteUsr, "ObjCMessageExpr", "remote", "CodexAgentAgentMcpEnvironmentSource",
        "CodexAgentAgentMcpEnvironmentSource * _Nonnull", emptyList(),
    ),
).plus(d065ExpectedObjectiveCAppleBindingReferences())
    .plus(d073ExpectedObjectiveCAppleBindingReferences())
    .plus(d074ExpectedObjectiveCAppleBindingReferences())
    .plus(d075ExpectedObjectiveCAppleBindingReferences())
    .plus(d076ExpectedObjectiveCAppleBindingReferences())
    .plus(d077ExpectedObjectiveCAppleBindingReferences())
    .plus(d078ExpectedObjectiveCAppleBindingReferences()).sortedBy(AppleCompilerReference::precise)

private fun JsonElement.appleSymbol(): AppleCompilerSymbol {
    val symbol = appleObject("Apple compiler symbol").also {
        it.appleKeys(
            "Apple compiler symbol", "precise", "interfaceLanguage", "kind", "path", "title", "accessLevel",
            "declaration", "typeIdentifiers", "parameters", "returns",
        )
    }
    return AppleCompilerSymbol(
        symbol.appleString("precise"), symbol.appleString("interfaceLanguage"), symbol.appleString("kind"),
        symbol.appleStrings("path"), symbol.appleString("title"), symbol.appleString("accessLevel"),
        symbol.appleString("declaration"), symbol.appleStrings("typeIdentifiers", unique = false),
        symbol.appleArray("parameters").map { value ->
            val parameter = value.appleObject("Apple compiler parameter").also {
                it.appleKeys("Apple compiler parameter", "name", "declaration")
            }
            parameter.appleString("name") to parameter.appleString("declaration")
        },
        symbol.appleNullableString("returns"),
    )
}

private fun JsonElement.appleReference(): AppleCompilerReference {
    val reference = appleObject("Apple compiler reference").also {
        it.appleKeys(
            "Apple compiler reference", "precise", "kind", "name", "receiverType", "valueType", "argumentTypes",
        )
    }
    return AppleCompilerReference(
        reference.appleString("precise"), reference.appleString("kind"), reference.appleString("name"),
        reference.appleNullableString("receiverType"), reference.appleString("valueType"),
        reference.appleStrings("argumentTypes", unique = false, allowAsterisk = true),
    )
}

private fun JsonObject.appleKeys(label: String, vararg keys: String) {
    check(this.keys == keys.toSet()) {
        "$label keys changed: expected=${keys.sorted()} actual=${this.keys.sorted()}"
    }
}

private fun JsonElement.appleObject(label: String): JsonObject = this as? JsonObject
    ?: error("$label is not a JSON object")

private fun JsonObject.appleObject(name: String): JsonObject = this[name]?.appleObject(name)
    ?: error("Missing Apple JSON object: $name")

private fun JsonObject.appleArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing Apple JSON array: $name")

private fun JsonObject.appleString(name: String): String {
    val value = this[name] as? JsonPrimitive ?: error("Missing Apple JSON string: $name")
    check(value.isString) { "Apple JSON field $name is not a string" }
    return value.contentOrNull ?: error("Missing Apple JSON string: $name")
}

private fun JsonObject.appleNullableString(name: String): String? = when (val value = this[name]) {
    JsonNull -> null
    is JsonPrimitive -> {
        check(value.isString) { "Apple JSON field $name is not a nullable string" }
        value.content
    }
    else -> error("Apple JSON field $name is not a nullable string")
}

private fun JsonObject.appleInt(name: String): Int {
    val value = this[name] as? JsonPrimitive ?: error("Missing Apple JSON integer: $name")
    check(!value.isString) { "Apple JSON field $name is not an integer" }
    return value.intOrNull ?: error("Apple JSON field $name is not an integer")
}

private fun JsonObject.appleSha256(name: String): String = appleString(name).also { digest ->
    digest.appleSha256("Apple JSON field $name")
}

private fun String.appleSha256(label: String) {
    check(length == 64 && all { it in '0'..'9' || it in 'a'..'f' }) { "$label is not an exact SHA-256" }
}

private fun JsonObject.appleStrings(
    name: String,
    unique: Boolean = true,
    allowAsterisk: Boolean = false,
): List<String> = appleArray(name).map { value ->
    val primitive = value as? JsonPrimitive ?: error("Apple JSON array $name contains a non-string")
    check(primitive.isString) { "Apple JSON array $name contains a non-string" }
    primitive.content
}.also { values ->
    check(!unique || values.size == values.distinct().size) { "Apple JSON array $name contains duplicates" }
    values.forEach { it.appleRecord("Apple JSON array $name", allowAsterisk) }
}

private fun String.appleRecord(label: String, allowAsterisk: Boolean = false) {
    check(isNotBlank() && this == trim() && (allowAsterisk || '*' !in this) && none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $this"
    }
}

private fun Iterable<String>.appleJsonStrings(): JsonArray = buildJsonArray {
    this@appleJsonStrings.forEach { add(JsonPrimitive(it)) }
}

private fun readCanonicalAppleBindingObject(file: File, label: String): JsonObject {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "$label is missing, non-regular, or a symlink: $file"
    }
    val contents = file.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject ?: error("$label is not a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "$label is not canonically encoded"
    }
    return root
}

private fun appleBindingTargetDigests(xcframework: File): Map<String, AppleBindingTargetDigests> = listOf(
    "ios-arm64", "ios-arm64-simulator",
).associateWith { name ->
    val framework = xcframework.resolve("$name/CodexAgent.framework")
    val binary = framework.resolve("CodexAgent")
    val header = framework.resolve("Headers/CodexAgent.h")
    val moduleMap = framework.resolve("Modules/module.modulemap")
    listOf(binary, header, moduleMap).forEach { file ->
        check(file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L) {
            "Apple binding artifact is missing, empty, or unsafe: $file"
        }
    }
    AppleBindingTargetDigests(
        framework.crossLanguageTreeDigest(), binary.releaseDigest(), header.releaseDigest(), moduleMap.releaseDigest(),
    )
}

@CacheableTask
abstract class GenerateAppleBindingEvidenceTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalApiReport: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalCoverageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val compilerEvidence: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcframeworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val swiftConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val objectiveCConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val xctestEvidence: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcresultDirectory: DirectoryProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val compilerFile = compilerEvidence.get().asFile
        val xctestFile = xctestEvidence.get().asFile
        val xcframework = xcframeworkDirectory.get().asFile
        val xcresult = xcresultDirectory.get().asFile
        val report = deriveCrossLanguageAppleBindingEvidence(
            readCrossLanguageCanonicalApiEvidence(
                canonicalApiReport.get().asFile,
                canonicalCoverageReceipt.get().asFile,
            ),
            readCanonicalAppleBindingObject(compilerFile, "Apple compiler evidence"),
            readCanonicalAppleBindingObject(xctestFile, "Apple XCTest evidence"),
            AppleBindingInputDigests(
                compilerFile.releaseDigest(),
                xcframework.crossLanguageTreeDigest(),
                appleBindingFileDigest(swiftConsumer.get().asFile, "Swift compiler consumer"),
                appleBindingFileDigest(objectiveCConsumer.get().asFile, "Objective-C compiler consumer"),
                xctestFile.releaseDigest(),
                xcresult.crossLanguageTreeDigest(),
                appleBindingTargetDigests(xcframework),
            ),
        )
        output.atomicWriteJson(report)
        check(readCanonicalAppleBindingObject(output, "Apple binding evidence") == report) {
            "Apple binding evidence does not match freshly derived observations"
        }
    }
}

private fun appleBindingFileDigest(file: File, label: String): String {
    check(file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L) {
        "$label is missing, empty, or a symlink: $file"
    }
    return file.releaseDigest()
}
