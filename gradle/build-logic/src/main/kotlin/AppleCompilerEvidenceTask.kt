import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal const val APPLE_COMPILER_EVIDENCE_PROTOCOL = "codex-agent-apple-compiler-evidence-v1"
internal const val APPLE_CODEX_FAILURE_OWNER_USR = "c:objc(cs)CodexAgentCodexFailure"
internal const val APPLE_CONVERSATION_ID_OWNER_USR = "c:objc(cs)CodexAgentConversationId"
internal const val APPLE_APPROVAL_DECISION_OWNER_USR = "c:objc(cs)CodexAgentAgentApprovalDecision"
internal const val APPLE_COLLABORATION_MODE_OWNER_USR = "c:objc(cs)CodexAgentAgentCollaborationMode"
internal const val APPLE_MESSAGE_ROLE_OWNER_USR = "c:objc(cs)CodexAgentAgentMessageRole"
internal const val APPLE_INSTALLATION_SCOPE_OWNER_USR = "c:objc(cs)CodexAgentAgentInstallationScope"
internal const val APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR = "c:objc(cs)CodexAgentAgentMcpEnvironmentSource"
internal const val APPLE_AUTHORIZATION_URL_OWNER_USR = "c:objc(cs)CodexAgentCodexAuthorizationUrl"
internal const val APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR =
    "c:objc(cs)CodexAgentCodexAuthorizationUrlCompanion"
private const val APPLE_CODEX_FAILURE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/CodexFailure"
private const val APPLE_CONVERSATION_ID_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/ConversationId"
private const val APPLE_APPROVAL_DECISION_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentApprovalDecision"
private const val APPLE_COLLABORATION_MODE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentCollaborationMode"
private const val APPLE_MESSAGE_ROLE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentMessageRole"
private const val APPLE_INSTALLATION_SCOPE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentInstallationScope"
private const val APPLE_MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER =
    "io.github.codex_agent_labs.codexmobile.agent/AgentMcpEnvironmentSource"

private val appleCodexFailureMembers = linkedMapOf(
    "constructor:<init>" to "$APPLE_CODEX_FAILURE_OWNER_USR(im)initWithCode:message:isRecoverable:",
    "property:code" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)code",
    "property:isRecoverable" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)isRecoverable",
    "property:message" to "$APPLE_CODEX_FAILURE_OWNER_USR(py)message",
)

private val appleCodexFailureCoverageTokens = mapOf(
    "constructor:<init>" to
        "api-v1:CodexFailure#constructor:<init>#sha256:db9872249097654acec4959fcef85fbac47c20419b28bbceee4a2ed40f619dce",
    "property:code" to
        "api-v1:CodexFailure#property:code#sha256:3a601436ff450cdd3e651dfc2e9faf56278431319e63c16c5fc2bff9417f10f9",
    "property:isRecoverable" to
        "api-v1:CodexFailure#property:isRecoverable#sha256:8973cb954621824ea55abdabe7aa39d7b8db93b56057971121255b2e7bd0cfa6",
    "property:message" to
        "api-v1:CodexFailure#property:message#sha256:8bc0e280b734d05df8b06e7f8f5544ba9323faa14cd59b35531b05ea3023ddad",
)

private val appleConversationIdMembers = linkedMapOf(
    "conversation-id:constructor:<init>" to "$APPLE_CONVERSATION_ID_OWNER_USR(im)initWithValue:",
    "conversation-id:property:value" to "$APPLE_CONVERSATION_ID_OWNER_USR(py)value",
)

private val appleConversationIdCoverageTokens = mapOf(
    "conversation-id:constructor:<init>" to
        "api-v1:ConversationId#constructor:<init>#sha256:9d99d061ecf0a53892277568e9139bd83e1f5cc70b1a9725943f892e99723bd3",
    "conversation-id:property:value" to
        "api-v1:ConversationId#property:value#sha256:d0c5dcf6402ad6595ff8b063d896bbb1d2c818322353860f18edfb17c84e1dfa",
)

private val appleApprovalDecisionMembers = linkedMapOf(
    "enum-entry:ACCEPT" to "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)accept",
    "enum-entry:DECLINE" to "$APPLE_APPROVAL_DECISION_OWNER_USR(cpy)decline",
)

private val appleApprovalDecisionCoverageTokens = mapOf(
    "enum-entry:ACCEPT" to
        "api-v1:AgentApprovalDecision#enum-entry:ACCEPT#sha256:c6613f75901ffd0146f3c8f945f73fabdc67efb237d52809c8a1e062835dc868",
    "enum-entry:DECLINE" to
        "api-v1:AgentApprovalDecision#enum-entry:DECLINE#sha256:db4d1df5ec20f42363a10d2b7a416c5e114a21663f8f70e0b32f4608dade7d56",
)

private val appleCollaborationModeMembers = linkedMapOf(
    "enum-entry:DEFAULT" to "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)default_",
    "enum-entry:PLAN" to "$APPLE_COLLABORATION_MODE_OWNER_USR(cpy)plan",
)

private val appleCollaborationModeCoverageTokens = mapOf(
    "enum-entry:DEFAULT" to
        "api-v1:AgentCollaborationMode#enum-entry:DEFAULT#sha256:e7a82ccb52ea70efb42bb512dfc2ef7616813fd6e0668c6d661f6b3b01c8a3d3",
    "enum-entry:PLAN" to
        "api-v1:AgentCollaborationMode#enum-entry:PLAN#sha256:ec0e7395b27d5e890c396ea4e39af43f49b093b933ee9062c83fc9c07a754e4d",
)

private val appleMessageRoleMembers = linkedMapOf(
    "enum-entry:USER" to "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)user",
    "enum-entry:ASSISTANT" to "$APPLE_MESSAGE_ROLE_OWNER_USR(cpy)assistant",
)

private val appleMessageRoleCoverageTokens = mapOf(
    "enum-entry:USER" to
        "api-v1:AgentMessageRole#enum-entry:USER#sha256:5572c10ccfb5180d31c30ba322e62f73ce28013434d77ee9e6fe416e076fe895",
    "enum-entry:ASSISTANT" to
        "api-v1:AgentMessageRole#enum-entry:ASSISTANT#sha256:f369c4f0e47685b440320333006c0c058783ee2a55f2b9c554839a8d9a0df128",
)

private val appleInstallationScopeMembers = linkedMapOf(
    "enum-entry:User" to "$APPLE_INSTALLATION_SCOPE_OWNER_USR(cpy)user",
    "enum-entry:Workspace" to "$APPLE_INSTALLATION_SCOPE_OWNER_USR(cpy)workspace",
)

private val appleInstallationScopeCoverageTokens = mapOf(
    "enum-entry:User" to
        "api-v1:AgentInstallationScope#enum-entry:User#sha256:2f69afc19c6f7a1b033fe00173acf97939c51d49f4e8f10c4cf7ee75d42477a3",
    "enum-entry:Workspace" to
        "api-v1:AgentInstallationScope#enum-entry:Workspace#sha256:fff8b4780086308bd27166be208daf44e8bb8595bcd4ce0de0fc4cd7d261b267",
)

private val appleMcpEnvironmentSourceMembers = linkedMapOf(
    "enum-entry:LOCAL" to "$APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR(cpy)local",
    "enum-entry:REMOTE" to "$APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR(cpy)remote",
)

private val appleMcpEnvironmentSourceCoverageTokens = mapOf(
    "enum-entry:LOCAL" to
        "api-v1:AgentMcpEnvironmentSource#enum-entry:LOCAL#sha256:40057398186ec13d19eb3fc39bc9c1049a83d95baaf69b91e2ae6af4f15216cb",
    "enum-entry:REMOTE" to
        "api-v1:AgentMcpEnvironmentSource#enum-entry:REMOTE#sha256:6f5abdbe115733f4b06fa9e6652b6e6ed03d721494d32a2cee5b175c41b686e7",
)

private const val appleCanonicalPackage = "io.github.codex_agent_labs.codexmobile.agent"
private const val appleCanonicalAbiPackage = "io.github.codex_agent_labs.codexmobile.agent"

internal data class AppleOrdinaryType(
    val canonical: String,
    val abi: String,
    val swift: String,
    val swiftIdentifier: String,
    val swiftAst: String,
    val objectiveC: String,
    val objectiveCIdentifier: String,
    val objectiveCAst: String = objectiveC,
    val swiftIdentifiers: List<String> = listOf(swiftIdentifier),
)

internal data class AppleOrdinaryParameter(
    val name: String,
    val type: AppleOrdinaryType,
    val hasDefault: Boolean = false,
    val objectiveCAst: String = type.objectiveCAst,
)

internal data class AppleOrdinaryProperty(
    val canonicalName: String,
    val type: AppleOrdinaryType,
    val appleName: String = canonicalName,
)

internal data class AppleOrdinaryEnum(
    val canonicalOwner: String,
    val swiftName: String,
    val objectiveCName: String,
    val swiftAst: String,
    val entries: List<Pair<String, String>>,
    val properties: List<AppleOrdinaryProperty> = emptyList(),
)

internal data class AppleOrdinaryValue(
    val canonicalOwner: String,
    val swiftName: String,
    val objectiveCName: String,
    val swiftConstructorAst: String,
    val parameters: List<AppleOrdinaryParameter>,
    val properties: List<AppleOrdinaryProperty>,
) {
    val objectiveCSelector: String = "initWith" +
        parameters.first().name.replaceFirstChar(Char::uppercaseChar) + ":" +
        parameters.drop(1).joinToString("") { "${it.name}:" }
}

internal data class AppleOrdinaryCapability(val canonicalKey: String, val usr: String)

private fun appleOwnerUsr(objectiveCName: String): String = "c:objc(cs)$objectiveCName"

private val appleMemberUsrPattern = Regex("""^(c:objc\(cs\)[^()]+)\((cpy|py|im)\)([^()]+)$""")

private val d083ProtocolMemberOwners = linkedMapOf(
    "c:objc(pl)CodexAgentAgentIntegration(py)displayName" to
        "c:objc(pl)CodexAgentAgentIntegration",
    "c:objc(pl)CodexAgentAgentIntegration(py)id" to
        "c:objc(pl)CodexAgentAgentIntegration",
    "c:objc(pl)CodexAgentAgentInvocation(py)key" to
        "c:objc(pl)CodexAgentAgentInvocation",
    "c:objc(pl)CodexAgentAgentInvocation(py)name" to
        "c:objc(pl)CodexAgentAgentInvocation",
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId" to
        "c:objc(pl)CodexAgentAgentPendingInteraction",
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId" to
        "c:objc(pl)CodexAgentAgentPendingInteraction",
)

private fun appleMemberOwnerUsr(memberUsr: String): String {
    d083ProtocolMemberOwners[memberUsr]?.let { return it }
    val match = checkNotNull(appleMemberUsrPattern.matchEntire(memberUsr)) {
        "Unexpected Apple member USR: $memberUsr"
    }
    return match.groupValues[1]
}

internal fun appleCompilerFixtureMemberOwnerUsr(memberUsr: String): String = appleMemberOwnerUsr(memberUsr)

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
private val appleConversationSummaryType = appleClassType(
    "AgentConversationSummary", "AgentConversationSummary", "CodexAgentAgentConversationSummary",
    "\$sSo010CodexAgentB19ConversationSummaryCD",
)
private val appleMessageRoleType = appleClassType(
    "AgentMessageRole", "AgentMessageRole", "CodexAgentAgentMessageRole",
    "\$sSo010CodexAgentB11MessageRoleCD",
)
private val appleCollaborationModeType = appleClassType(
    "AgentCollaborationMode", "AgentCollaborationMode", "CodexAgentAgentCollaborationMode",
    "\$sSo010CodexAgentB17CollaborationModeCD",
)
private val appleCapabilitySet = AppleOrdinaryType(
    "kotlin.collections/Set<INVARIANT:$appleCanonicalPackage/AgentCapability!!>!!",
    "kotlin.collections.Set<$appleCanonicalAbiPackage.AgentCapability>",
    "Set<AgentCapability>", "s:Sh", "\$sShySo010CodexAgentB10CapabilityCGD",
    "NSSet<CodexAgentAgentCapability *> *", "c:Q\$objc(cs)NSSet",
    "NSSet<CodexAgentAgentCapability *> * _Nonnull",
    listOf("s:Sh", appleOwnerUsr("CodexAgentAgentCapability")),
)
private val appleInvocationList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:$appleCanonicalPackage/AgentInvocation!!>!!",
    "kotlin.collections.List<$appleCanonicalAbiPackage.AgentInvocation>",
    "[any AgentInvocation]", "c:objc(pl)CodexAgentAgentInvocation",
    "\$sSaySo010CodexAgentB10Invocation_pGD",
    "NSArray<id<CodexAgentAgentInvocation>> *", "c:Q\$objc(cs)NSArray",
    "NSArray<id<CodexAgentAgentInvocation>> * _Nonnull",
)
private val appleMessageList = appleClassListType(
    "AgentMessage", "AgentMessage", "CodexAgentAgentMessage", "\$sSaySo010CodexAgentB7MessageCGD",
)
private val appleAuthenticationStatusType = appleClassType(
    "AgentAuthenticationStatus", "AgentAuthenticationStatus", "CodexAgentAgentAuthenticationStatus",
    "\$sSo010CodexAgentB20AuthenticationStatusCD",
)
private val appleNullableAuthorizationUrlType = appleClassType(
    "CodexAuthorizationUrl", "CodexAuthorizationUrl", "CodexAgentCodexAuthorizationUrl",
    "\$sSo010CodexAgentA16AuthorizationUrlCSgD", nullable = true,
)
private val appleNullableFailureType = appleClassType(
    "CodexFailure", "CodexFailure", "CodexAgentCodexFailure",
    "\$sSo010CodexAgentA7FailureCSgD", nullable = true,
)
private val appleConversationStatusType = appleClassType(
    "AgentConversationStatus", "AgentConversationStatus", "CodexAgentAgentConversationStatus",
    "\$sSo010CodexAgentB18ConversationStatusCD",
)
private val appleNullableConversationIdType = appleClassType(
    "ConversationId", "ConversationId", "CodexAgentConversationId",
    "\$sSo24CodexAgentConversationIdCSgD", nullable = true,
)
private val appleNullableConversationType = appleClassType(
    "AgentConversation", "AgentConversation", "CodexAgentAgentConversation",
    "\$sSo010CodexAgentB12ConversationCSgD", nullable = true,
)
private val appleTurnProgressType = appleClassType(
    "AgentTurnProgress", "AgentTurnProgress", "CodexAgentAgentTurnProgress",
    "\$sSo010CodexAgentB12TurnProgressCD",
)
private val appleIntegrationAuthorizationStatusType = appleClassType(
    "AgentIntegrationAuthorizationStatus", "AgentIntegrationAuthorizationStatus",
    "CodexAgentAgentIntegrationAuthorizationStatus",
    "\$sSo010CodexAgentB30IntegrationAuthorizationStatusCD",
)
private val appleNullableIntegrationType = AppleOrdinaryType(
    "$appleCanonicalPackage/AgentIntegration?", "$appleCanonicalAbiPackage.AgentIntegration?",
    "(any AgentIntegration)?", "c:objc(pl)CodexAgentAgentIntegration",
    "\$sSo010CodexAgentB11Integration_pSgD", "id<CodexAgentAgentIntegration>",
    "c:Qoobjc(pl)CodexAgentAgentIntegration",
)
private val applePendingInteractionType = AppleOrdinaryType(
    "$appleCanonicalPackage/AgentPendingInteraction!!",
    "$appleCanonicalAbiPackage.AgentPendingInteraction",
    "any AgentPendingInteraction", "c:objc(pl)CodexAgentAgentPendingInteraction",
    "\$sSo010CodexAgentB18PendingInteraction_pD", "id<CodexAgentAgentPendingInteraction>",
    "c:Qoobjc(pl)CodexAgentAgentPendingInteraction",
)
private val applePendingInteractionList = AppleOrdinaryType(
    "kotlin.collections/List<INVARIANT:$appleCanonicalPackage/AgentPendingInteraction!!>!!",
    "kotlin.collections.List<$appleCanonicalAbiPackage.AgentPendingInteraction>",
    "[any AgentPendingInteraction]", "c:objc(pl)CodexAgentAgentPendingInteraction",
    "\$sSaySo010CodexAgentB18PendingInteraction_pGD",
    "NSArray<id<CodexAgentAgentPendingInteraction>> *", "c:Q\$objc(cs)NSArray",
    "NSArray<id<CodexAgentAgentPendingInteraction>> * _Nonnull",
)
private val appleStringSet = AppleOrdinaryType(
    "kotlin.collections/Set<INVARIANT:kotlin/String!!>!!",
    "kotlin.collections.Set<kotlin.String>",
    "Set<String>", "s:Sh", "\$sShySSGD",
    "NSSet<NSString *> *", "c:Q\$objc(cs)NSSet", "NSSet<NSString *> * _Nonnull",
    listOf("s:Sh", "s:SS"),
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

private val d079AppleValues = listOf(
    AppleOrdinaryValue(
        "AgentConversation", "AgentConversation", "CodexAgentAgentConversation",
        "\$sySo010CodexAgentB12ConversationCSo0abbC7SummaryC_SaySo0abB7MessageCGtcABmcD",
        listOf(
            AppleOrdinaryParameter("summary", appleConversationSummaryType),
            AppleOrdinaryParameter(
                "messages", appleMessageList, objectiveCAst = "NSArray<CodexAgentAgentMessage *> *",
            ),
        ), listOf(
            AppleOrdinaryProperty("messages", appleMessageList),
            AppleOrdinaryProperty("summary", appleConversationSummaryType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentMessage", "AgentMessage", "CodexAgentAgentMessage",
        "\$sySo010CodexAgentB7MessageCSS_SSSgSo0abbC4RoleCSSSo0abB17CollaborationModeCA3C" +
            "So0aB3IntCSgShySo0abB10CapabilityCGSaySo0abB10Invocation_pGtcABmcD",
        listOf(
            AppleOrdinaryParameter("id", appleString),
            AppleOrdinaryParameter("clientMessageId", appleNullableString),
            AppleOrdinaryParameter(
                "role", appleMessageRoleType, objectiveCAst = "CodexAgentAgentMessageRole * _Nonnull",
            ),
            AppleOrdinaryParameter("text", appleString),
            AppleOrdinaryParameter(
                "collaborationMode", appleCollaborationModeType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentCollaborationMode * _Nonnull",
            ),
            AppleOrdinaryParameter("reasoning", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("plan", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("shellCommand", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("exitCode", appleNullableInt, hasDefault = true),
            AppleOrdinaryParameter(
                "capabilities", appleCapabilitySet, hasDefault = true,
                objectiveCAst = "NSSet<CodexAgentAgentCapability *> *",
            ),
            AppleOrdinaryParameter(
                "invocations", appleInvocationList, hasDefault = true,
                objectiveCAst = "NSArray<id<CodexAgentAgentInvocation>> *",
            ),
        ), listOf(
            AppleOrdinaryProperty("capabilities", appleCapabilitySet),
            AppleOrdinaryProperty("clientMessageId", appleNullableString),
            AppleOrdinaryProperty("collaborationMode", appleCollaborationModeType),
            AppleOrdinaryProperty("exitCode", appleNullableInt),
            AppleOrdinaryProperty("id", appleString),
            AppleOrdinaryProperty("invocations", appleInvocationList),
            AppleOrdinaryProperty("plan", appleNullableString),
            AppleOrdinaryProperty("reasoning", appleNullableString),
            AppleOrdinaryProperty("role", appleMessageRoleType),
            AppleOrdinaryProperty("shellCommand", appleNullableString),
            AppleOrdinaryProperty("text", appleString),
        ),
    ),
    AppleOrdinaryValue(
        "AgentTurnRequest", "AgentTurnRequest", "CodexAgentAgentTurnRequest",
        "\$sySo010CodexAgentB11TurnRequestCSS_SSSgA3CSo0abB14ApprovalPresetCShySo0abB10CapabilityCG" +
            "SaySo0abB10Invocation_pGSo0abB17CollaborationModeCtcABmcD",
        listOf(
            AppleOrdinaryParameter("prompt", appleString),
            AppleOrdinaryParameter("clientMessageId", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("model", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("effort", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter("serviceTier", appleNullableString, hasDefault = true),
            AppleOrdinaryParameter(
                "approvalPreset", appleApprovalPresetType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentApprovalPreset * _Nonnull",
            ),
            AppleOrdinaryParameter(
                "capabilities", appleCapabilitySet, hasDefault = true,
                objectiveCAst = "NSSet<CodexAgentAgentCapability *> *",
            ),
            AppleOrdinaryParameter(
                "invocations", appleInvocationList, hasDefault = true,
                objectiveCAst = "NSArray<id<CodexAgentAgentInvocation>> *",
            ),
            AppleOrdinaryParameter(
                "collaborationMode", appleCollaborationModeType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentCollaborationMode * _Nonnull",
            ),
        ), listOf(
            AppleOrdinaryProperty("approvalPreset", appleApprovalPresetType),
            AppleOrdinaryProperty("capabilities", appleCapabilitySet),
            AppleOrdinaryProperty("clientMessageId", appleNullableString),
            AppleOrdinaryProperty("collaborationMode", appleCollaborationModeType),
            AppleOrdinaryProperty("effort", appleNullableString),
            AppleOrdinaryProperty("invocations", appleInvocationList),
            AppleOrdinaryProperty("model", appleNullableString),
            AppleOrdinaryProperty("prompt", appleString),
            AppleOrdinaryProperty("serviceTier", appleNullableString),
        ),
    ),
)

private val d080AppleValues = listOf(
    AppleOrdinaryValue(
        "AgentAuthenticationState", "AgentAuthenticationState", "CodexAgentAgentAuthenticationState",
        "\$sySo010CodexAgentB19AuthenticationStateCSo0abbC6StatusC_So0abA16AuthorizationUrlCSgAGSSSg" +
            "So0abA7FailureCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter(
                "status", appleAuthenticationStatusType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentAuthenticationStatus *",
            ),
            AppleOrdinaryParameter(
                "pendingSignInUrl", appleNullableAuthorizationUrlType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexAuthorizationUrl *",
            ),
            AppleOrdinaryParameter(
                "deviceVerificationUrl", appleNullableAuthorizationUrlType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexAuthorizationUrl *",
            ),
            AppleOrdinaryParameter(
                "deviceUserCode", appleNullableString, hasDefault = true,
                objectiveCAst = "NSString *",
            ),
            AppleOrdinaryParameter(
                "failure", appleNullableFailureType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexFailure *",
            ),
        ),
        listOf(
            AppleOrdinaryProperty("deviceUserCode", appleNullableString),
            AppleOrdinaryProperty("deviceVerificationUrl", appleNullableAuthorizationUrlType),
            AppleOrdinaryProperty("failure", appleNullableFailureType),
            AppleOrdinaryProperty("pendingSignInUrl", appleNullableAuthorizationUrlType),
            AppleOrdinaryProperty("status", appleAuthenticationStatusType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentConversationState", "AgentConversationState", "CodexAgentAgentConversationState",
        "\$sySo010CodexAgentB17ConversationStateCSo0abbC6StatusC_So0abC2IdCSgSo0abbC0CSg" +
            "So0abB12TurnProgressCSSSgA2MSo0abA7FailureCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter(
                "status", appleConversationStatusType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentConversationStatus *",
            ),
            AppleOrdinaryParameter(
                "conversationId", appleNullableConversationIdType, hasDefault = true,
                objectiveCAst = "CodexAgentConversationId *",
            ),
            AppleOrdinaryParameter(
                "conversation", appleNullableConversationType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentConversation *",
            ),
            AppleOrdinaryParameter(
                "turnProgress", appleTurnProgressType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentTurnProgress *",
            ),
            AppleOrdinaryParameter(
                "model", appleNullableString, hasDefault = true, objectiveCAst = "NSString *",
            ),
            AppleOrdinaryParameter(
                "effort", appleNullableString, hasDefault = true, objectiveCAst = "NSString *",
            ),
            AppleOrdinaryParameter(
                "serviceTier", appleNullableString, hasDefault = true, objectiveCAst = "NSString *",
            ),
            AppleOrdinaryParameter(
                "failure", appleNullableFailureType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexFailure *",
            ),
        ),
        listOf(
            AppleOrdinaryProperty("canCancelTurn", appleBoolean),
            AppleOrdinaryProperty("canReload", appleBoolean),
            AppleOrdinaryProperty("canStartTurn", appleBoolean),
            AppleOrdinaryProperty("conversation", appleNullableConversationType),
            AppleOrdinaryProperty("conversationId", appleNullableConversationIdType),
            AppleOrdinaryProperty("effort", appleNullableString),
            AppleOrdinaryProperty("failure", appleNullableFailureType),
            AppleOrdinaryProperty("model", appleNullableString),
            AppleOrdinaryProperty("serviceTier", appleNullableString),
            AppleOrdinaryProperty("status", appleConversationStatusType),
            AppleOrdinaryProperty("turnProgress", appleTurnProgressType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentIntegrationAuthorizationState", "AgentIntegrationAuthorizationState",
        "CodexAgentAgentIntegrationAuthorizationState",
        "\$sySo010CodexAgentB29IntegrationAuthorizationStateCSo0abbcD6StatusC_So0abbC0_pSg" +
            "So0abA7FailureCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter(
                "status", appleIntegrationAuthorizationStatusType, hasDefault = true,
                objectiveCAst = "CodexAgentAgentIntegrationAuthorizationStatus *",
            ),
            AppleOrdinaryParameter(
                "target", appleNullableIntegrationType, hasDefault = true,
                objectiveCAst = "id<CodexAgentAgentIntegration> _Nullable",
            ),
            AppleOrdinaryParameter(
                "failure", appleNullableFailureType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexFailure *",
            ),
        ),
        listOf(
            AppleOrdinaryProperty("failure", appleNullableFailureType),
            AppleOrdinaryProperty("status", appleIntegrationAuthorizationStatusType),
            AppleOrdinaryProperty("target", appleNullableIntegrationType),
        ),
    ),
    AppleOrdinaryValue(
        "AgentInteractionState", "AgentInteractionState", "CodexAgentAgentInteractionState",
        "\$sySo010CodexAgentB16InteractionStateCSaySo0abb7PendingC0_pG_ShySSG" +
            "So0abA7FailureCSgtcABmcD",
        listOf(
            AppleOrdinaryParameter(
                "pending", applePendingInteractionList, hasDefault = true,
                objectiveCAst = "NSArray<id<CodexAgentAgentPendingInteraction>> *",
            ),
            AppleOrdinaryParameter(
                "resolvingRequestIds", appleStringSet, hasDefault = true,
                objectiveCAst = "NSSet<NSString *> *",
            ),
            AppleOrdinaryParameter(
                "failure", appleNullableFailureType, hasDefault = true,
                objectiveCAst = "CodexAgentCodexFailure *",
            ),
        ),
        listOf(
            AppleOrdinaryProperty("failure", appleNullableFailureType),
            AppleOrdinaryProperty("pending", applePendingInteractionList),
            AppleOrdinaryProperty("resolvingRequestIds", appleStringSet),
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
        "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)chatGptValue:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl.Companion|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.Companion.external|" +
            "external(kotlin.String){}[0]|return=$appleCanonicalPackage/CodexAuthorizationUrl!!|" +
            "suspend=false|parameters=[REGULAR:kotlin/String!!:default=false:vararg=false]",
        "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)externalValue:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl|kind=property|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.value|{}value[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)value",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexAuthorizationUrl|kind=property|" +
            "abi=$appleCanonicalAbiPackage/CodexAuthorizationUrl.purpose|{}purpose[0]|propertyKind=VAL|" +
            "type=$appleCanonicalPackage/CodexAuthorizationPurpose!!",
        "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)purpose",
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

private val d079OrdinaryCapabilities: List<AppleOrdinaryCapability> = buildList {
    d079AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "${ownerUsr}(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "${ownerUsr}(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 25 && capabilities.map { it.canonicalKey }.distinct().size == 25 &&
        capabilities.map { it.usr }.distinct().size == 25
    ) { "D079 Apple ordinary capability inventory changed" }
}
private val d079OrdinaryCapabilitiesByKey = d079OrdinaryCapabilities.associateBy { it.canonicalKey }

private val d080InteractionMethods = listOf(
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentInteractionState|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentInteractionState.isResolving|" +
            "isResolving($appleCanonicalAbiPackage.AgentPendingInteraction){}[0]|" +
            "return=kotlin/Boolean!!|suspend=false|parameters=[" +
            "REGULAR:$appleCanonicalPackage/AgentPendingInteraction!!:default=false:vararg=false]",
        "c:objc(cs)CodexAgentAgentInteractionState(im)isResolvingInteraction:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentInteractionState|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentInteractionState.pendingFor|" +
            "pendingFor($appleCanonicalAbiPackage.ConversationId){}[0]|" +
            "return=kotlin.collections/List<INVARIANT:$appleCanonicalPackage/AgentPendingInteraction!!>!!|" +
            "suspend=false|parameters=[" +
            "REGULAR:$appleCanonicalPackage/ConversationId!!:default=false:vararg=false]",
        "c:objc(cs)CodexAgentAgentInteractionState(im)pendingForConversationId:",
    ),
)

private val d080Capabilities: List<AppleOrdinaryCapability> = buildList {
    d080AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
    addAll(d080InteractionMethods)
}.also { capabilities ->
    check(capabilities.size == 28 && capabilities.map { it.canonicalKey }.distinct().size == 28 &&
        capabilities.map { it.usr }.distinct().size == 28
    ) { "D080 Apple snapshot capability inventory changed" }
}
private val d080CapabilitiesByKey = d080Capabilities.associateBy { it.canonicalKey }

private val d081AppleObjects = listOf(
    Triple(
        "AgentHookHandler.Agent", "CodexAgentAgentHookHandlerAgent",
        "\$sSo010CodexAgentb11HookHandlerB0CD",
    ),
    Triple(
        "AgentHookHandler.Prompt", "CodexAgentAgentHookHandlerPrompt",
        "\$sSo010CodexAgentB17HookHandlerPromptCD",
    ),
    Triple(
        "CodexAuthenticationMethod.ChatGptBrowser", "CodexAgentCodexAuthenticationMethodChatGptBrowser",
        "\$sSo010CodexAgentA34AuthenticationMethodChatGptBrowserCD",
    ),
    Triple(
        "CodexAuthenticationMethod.ChatGptDeviceCode", "CodexAgentCodexAuthenticationMethodChatGptDeviceCode",
        "\$sSo010CodexAgentA37AuthenticationMethodChatGptDeviceCodeCD",
    ),
    Triple(
        "CodexHostState.Closed", "CodexAgentCodexHostStateClosed",
        "\$sSo010CodexAgentA15HostStateClosedCD",
    ),
    Triple(
        "CodexHostState.New", "CodexAgentCodexHostStateNew",
        "\$sSo010CodexAgentA12HostStateNewCD",
    ),
    Triple(
        "CodexHostState.Restoring", "CodexAgentCodexHostStateRestoring",
        "\$sSo010CodexAgentA18HostStateRestoringCD",
    ),
)

private val d081Capabilities = d081AppleObjects.map { (canonicalOwner, objectiveCName) ->
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/$canonicalOwner|kind=object|" +
            "abi=$appleCanonicalAbiPackage/$canonicalOwner|null[0]",
        "${appleOwnerUsr(objectiveCName)}(cpy)shared",
    )
}.also { capabilities ->
    check(capabilities.size == 7 && capabilities.map { it.canonicalKey }.distinct().size == 7 &&
        capabilities.map { it.usr }.distinct().size == 7
    ) { "D081 Apple singleton capability inventory changed" }
}
private val d081CapabilitiesByKey = d081Capabilities.associateBy { it.canonicalKey }

private val d082ElicitationCapabilities = listOf(
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitationResponse.Companion|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitationResponse.Companion.cancel|cancel(){}[0]|" +
            "return=$appleCanonicalPackage/AgentElicitationResponse!!|suspend=false|parameters=[]",
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)cancel",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitationResponse.Companion|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitationResponse.Companion.decline|decline(){}[0]|" +
            "return=$appleCanonicalPackage/AgentElicitationResponse!!|suspend=false|parameters=[]",
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)decline",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitation|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitation.accepts|" +
            "accepts($appleCanonicalAbiPackage.AgentElicitationResponse){}[0]|return=kotlin/Boolean!!|" +
            "suspend=false|parameters=[REGULAR:$appleCanonicalPackage/AgentElicitationResponse!!:" +
            "default=false:vararg=false]",
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptsResponse:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitation|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitation.accept|" +
            "accept(kotlin.collections.Map<kotlin.String,$appleCanonicalAbiPackage.AgentFormValue>){}[0]|" +
            "return=$appleCanonicalPackage/AgentElicitationResponse!!|suspend=false|" +
            "parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!," +
            "INVARIANT:$appleCanonicalPackage/AgentFormValue!!>!!:default=false:vararg=false]",
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptContent:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitation|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitation.initialValues|initialValues(){}[0]|" +
            "return=kotlin.collections/Map<INVARIANT:kotlin/String!!," +
            "INVARIANT:$appleCanonicalPackage/AgentFormValue!!>!!|suspend=false|parameters=[]",
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)initialValues",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentElicitation|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentElicitation.validate|" +
            "validate(kotlin.collections.Map<kotlin.String,$appleCanonicalAbiPackage.AgentFormValue>){}[0]|" +
            "return=$appleCanonicalPackage/AgentElicitationValidation!!|suspend=false|" +
            "parameters=[REGULAR:kotlin.collections/Map<INVARIANT:kotlin/String!!," +
            "INVARIANT:$appleCanonicalPackage/AgentFormValue!!>!!:default=false:vararg=false]",
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)validateContent:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentFormField|kind=function|" +
            "abi=$appleCanonicalAbiPackage/AgentFormField.accepts|" +
            "accepts($appleCanonicalAbiPackage.AgentFormValue?){}[0]|return=kotlin/Boolean!!|suspend=false|" +
            "parameters=[REGULAR:$appleCanonicalPackage/AgentFormValue?:default=false:vararg=false]",
        "${appleOwnerUsr("CodexAgentAgentFormField")}(im)acceptsValue:",
    ),
).also { capabilities ->
    check(capabilities.size == 7 && capabilities.map { it.canonicalKey }.distinct().size == 7 &&
        capabilities.map { it.usr }.distinct().size == 7
    ) { "D082 Apple elicitation capability inventory changed" }
}
private val d082ElicitationCapabilitiesByKey = d082ElicitationCapabilities.associateBy { it.canonicalKey }

private val d083ProtocolCapabilities = listOf(
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentIntegration|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentIntegration.displayName|{}displayName[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "c:objc(pl)CodexAgentAgentIntegration(py)displayName",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentIntegration|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentIntegration.id|{}id[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "c:objc(pl)CodexAgentAgentIntegration(py)id",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentInvocation|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentInvocation.key|{}key[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "c:objc(pl)CodexAgentAgentInvocation(py)key",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentInvocation|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentInvocation.name|{}name[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "c:objc(pl)CodexAgentAgentInvocation(py)name",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentPendingInteraction|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentPendingInteraction.conversationId|{}conversationId[0]|" +
            "propertyKind=VAL|type=$appleCanonicalPackage/ConversationId!!",
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/AgentPendingInteraction|kind=property|" +
            "abi=$appleCanonicalAbiPackage/AgentPendingInteraction.requestId|{}requestId[0]|" +
            "propertyKind=VAL|type=kotlin/String!!",
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId",
    ),
).also { capabilities ->
    check(capabilities.size == 6 && capabilities.map { it.canonicalKey }.distinct().size == 6 &&
        capabilities.map { it.usr }.distinct().size == 6 &&
        capabilities.associate { it.usr to appleMemberOwnerUsr(it.usr) } == d083ProtocolMemberOwners
    ) { "D083 Apple protocol capability inventory changed" }
}
private val d083ProtocolCapabilitiesByKey = d083ProtocolCapabilities.associateBy { it.canonicalKey }

private val d084PlatformType = AppleOrdinaryType(
    "$appleCanonicalPackage/CodexPlatform!!", "$appleCanonicalAbiPackage.CodexPlatform",
    "any CodexPlatform", "c:objc(pl)CodexAgentCodexPlatform", "\$sSo010CodexAgentA8Platform_pD",
    "id<CodexAgentCodexPlatform>", "c:Qoobjc(pl)CodexAgentCodexPlatform",
    "id<CodexAgentCodexPlatform>",
)
private val d084ClientInfoType = appleClassType(
    "CodexClientInfo", "CodexClientInfo", "CodexAgentCodexClientInfo",
    "\$sSo010CodexAgentA10ClientInfoCD",
)
private val d084NullableWorkspaceType = AppleOrdinaryType(
    "$appleCanonicalPackage/CodexWorkspace?", "$appleCanonicalAbiPackage.CodexWorkspace?",
    "CodexWorkspace?", appleOwnerUsr("CodexAgentCodexWorkspace"), "\$sSo010CodexAgentA9WorkspaceCSgD",
    "CodexAgentCodexWorkspace *", appleOwnerUsr("CodexAgentCodexWorkspace"),
    "CodexAgentCodexWorkspace *",
)
private val d084FailureType = appleClassType(
    "CodexFailure", "CodexFailure", "CodexAgentCodexFailure", "\$sSo010CodexAgentA7FailureCD",
)
private val d084AgentType = appleClassType(
    "CodexAgent", "CodexAgent", "CodexAgentCodexAgent", "\$sSo010CodexAgentaB0CD",
)
private val d084SelectionRequiredType = appleClassType(
    "CodexWorkspaceResolution.SelectionRequired", "CodexWorkspaceResolutionSelectionRequired",
    "CodexAgentCodexWorkspaceResolutionSelectionRequired",
    "\$sSo010CodexAgentA36WorkspaceResolutionSelectionRequiredCD",
)
private val d084HostStateFlowType = AppleOrdinaryType(
    "kotlinx.coroutines.flow/StateFlow<INVARIANT:$appleCanonicalPackage/CodexHostState!!>!!",
    "kotlinx.coroutines.flow.StateFlow<$appleCanonicalAbiPackage.CodexHostState>",
    "any Kotlinx_coroutines_coreStateFlow", "c:objc(pl)CodexAgentKotlinx_coroutines_coreStateFlow",
    "\$sSo42CodexAgentKotlinx_coroutines_coreStateFlow_pD",
    "id<CodexAgentKotlinx_coroutines_coreStateFlow>",
    "c:Qoobjc(pl)CodexAgentKotlinx_coroutines_coreStateFlow",
)

private val d084AppleValues = listOf(
    AppleOrdinaryValue(
        "CodexHost", "CodexHost", "CodexAgentCodexHost",
        "\$sySo010CodexAgentA4HostCSo0abA8Platform_p_So0abA10ClientInfoCtcABmcD",
        listOf(
            AppleOrdinaryParameter("platform", d084PlatformType),
            AppleOrdinaryParameter("clientInfo", d084ClientInfoType),
        ),
        emptyList(),
    ),
    AppleOrdinaryValue(
        "CodexHostState.Failed", "CodexHostStateFailed", "CodexAgentCodexHostStateFailed",
        "\$sySo010CodexAgentA15HostStateFailedCSo0abA9WorkspaceCSg_So0abA7FailureCtcABmcD",
        listOf(
            AppleOrdinaryParameter("workspace", d084NullableWorkspaceType),
            AppleOrdinaryParameter("failure", d084FailureType),
        ),
        listOf(
            AppleOrdinaryProperty("failure", d084FailureType),
            AppleOrdinaryProperty("workspace", d084NullableWorkspaceType),
        ),
    ),
    AppleOrdinaryValue(
        "CodexHostState.Preparing", "CodexHostStatePreparing", "CodexAgentCodexHostStatePreparing",
        "\$sySo010CodexAgentA18HostStatePreparingCSo0abA9WorkspaceC_tcABmcD",
        listOf(AppleOrdinaryParameter("workspace", appleWorkspaceType)),
        listOf(AppleOrdinaryProperty("workspace", appleWorkspaceType)),
    ),
    AppleOrdinaryValue(
        "CodexHostState.Ready", "CodexHostStateReady", "CodexAgentCodexHostStateReady",
        "\$sySo010CodexAgentA14HostStateReadyCSo0abaB0C_tcABmcD",
        listOf(AppleOrdinaryParameter("agent", d084AgentType)),
        listOf(AppleOrdinaryProperty("agent", d084AgentType)),
    ),
    AppleOrdinaryValue(
        "CodexHostState.WorkspaceRequired", "CodexHostStateWorkspaceRequired",
        "CodexAgentCodexHostStateWorkspaceRequired",
        "\$sySo010CodexAgentA26HostStateWorkspaceRequiredCSo0abae19ResolutionSelectionF0C_tcABmcD",
        listOf(AppleOrdinaryParameter("requirement", d084SelectionRequiredType)),
        listOf(AppleOrdinaryProperty("requirement", d084SelectionRequiredType)),
    ),
)

private val d084ExceptionalHostCapabilities = listOf(
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexHost|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexHost.close|close(){}[0]|return=kotlin/Unit|" +
            "suspend=true|parameters=[]",
        "${appleOwnerUsr("CodexAgentCodexHost")}(im)closeWithCompletionHandler:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexHost|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexHost.selectWorkspace|" +
            "selectWorkspace($appleCanonicalAbiPackage.CodexWorkspaceSelection){}[0]|return=kotlin/Unit|" +
            "suspend=true|parameters=[REGULAR:$appleCanonicalPackage/CodexWorkspaceSelection!!:" +
            "default=false:vararg=false]",
        "${appleOwnerUsr("CodexAgentCodexHost")}(im)selectWorkspaceSelection:completionHandler:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexHost|kind=function|" +
            "abi=$appleCanonicalAbiPackage/CodexHost.start|start(){}[0]|return=kotlin/Unit|" +
            "suspend=true|parameters=[]",
        "${appleOwnerUsr("CodexAgentCodexHost")}(im)startWithCompletionHandler:",
    ),
    AppleOrdinaryCapability(
        "common|owner=$appleCanonicalPackage/CodexHost|kind=property|" +
            "abi=$appleCanonicalAbiPackage/CodexHost.lifecycleState|{}lifecycleState[0]|propertyKind=VAL|" +
            "type=${d084HostStateFlowType.canonical}",
        "${appleOwnerUsr("CodexAgentCodexHost")}(py)lifecycleState",
    ),
)

private val d084Capabilities: List<AppleOrdinaryCapability> = buildList {
    d084AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleOrdinaryCapability(appleConstructorKey(owner), "$ownerUsr(im)${owner.objectiveCSelector}"))
        owner.properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner.canonicalOwner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
    addAll(d084ExceptionalHostCapabilities)
}.also { capabilities ->
    check(capabilities.size == 14 && capabilities.map { it.canonicalKey }.distinct().size == 14 &&
        capabilities.map { it.usr }.distinct().size == 14
    ) { "D084 Apple Host/state capability inventory changed" }
}
private val d084CapabilitiesByKey = d084Capabilities.associateBy { it.canonicalKey }
private val d084SwiftAsyncMemberUsrs =
    d084ExceptionalHostCapabilities.filter { "|kind=function|" in it.canonicalKey }
        .mapTo(linkedSetOf(), AppleOrdinaryCapability::usr)

private val d085AuthenticationType = appleClassType(
    "CodexAuthentication", "CodexAuthentication", "CodexAgentCodexAuthentication",
    "\$sSo010CodexAgentA14AuthenticationCD",
)
private val d085ConnectorsType = appleClassType(
    "CodexConnectors", "CodexConnectors", "CodexAgentCodexConnectors",
    "\$sSo010CodexAgentA10ConnectorsCD",
)
private val d085ConversationsType = appleClassType(
    "CodexConversations", "CodexConversations", "CodexAgentCodexConversations",
    "\$sSo010CodexAgentA13ConversationsCD",
)
private val d085HooksType = appleClassType(
    "CodexHooks", "CodexHooks", "CodexAgentCodexHooks", "\$sSo010CodexAgentA5HooksCD",
)
private val d085IntegrationAuthorizationType = appleClassType(
    "CodexIntegrationAuthorization", "CodexIntegrationAuthorization",
    "CodexAgentCodexIntegrationAuthorization", "\$sSo010CodexAgentA24IntegrationAuthorizationCD",
)
private val d085InteractionsType = appleClassType(
    "CodexInteractions", "CodexInteractions", "CodexAgentCodexInteractions",
    "\$sSo010CodexAgentA12InteractionsCD",
)
private val d085McpServersType = appleClassType(
    "CodexMcpServers", "CodexMcpServers", "CodexAgentCodexMcpServers",
    "\$sSo010CodexAgentA10McpServersCD",
)
private val d085ModelsType = appleClassType(
    "CodexModels", "CodexModels", "CodexAgentCodexModels", "\$sSo010CodexAgentA6ModelsCD",
)
private val d085PluginsType = appleClassType(
    "CodexPlugins", "CodexPlugins", "CodexAgentCodexPlugins", "\$sSo010CodexAgentA7PluginsCD",
)
private val d085SkillsType = appleClassType(
    "CodexSkills", "CodexSkills", "CodexAgentCodexSkills", "\$sSo010CodexAgentA6SkillsCD",
)

private val d085PropertyOwners: List<Pair<String, List<AppleOrdinaryProperty>>> = listOf(
    "CodexAgent" to listOf(
        AppleOrdinaryProperty("authentication", d085AuthenticationType),
        AppleOrdinaryProperty("connectors", d085ConnectorsType),
        AppleOrdinaryProperty("conversations", d085ConversationsType),
        AppleOrdinaryProperty("hooks", d085HooksType),
        AppleOrdinaryProperty("integrationAuthorization", d085IntegrationAuthorizationType),
        AppleOrdinaryProperty("interactions", d085InteractionsType),
        AppleOrdinaryProperty("mcpServers", d085McpServersType),
        AppleOrdinaryProperty("models", d085ModelsType),
        AppleOrdinaryProperty("plugins", d085PluginsType),
        AppleOrdinaryProperty("skills", d085SkillsType),
        AppleOrdinaryProperty("workspace", appleWorkspaceType),
    ),
    "CodexConnectors" to listOf(AppleOrdinaryProperty("isAvailable", appleBoolean)),
    "CodexHooks" to listOf(AppleOrdinaryProperty("isAvailable", appleBoolean)),
    "CodexMcpServers" to listOf(AppleOrdinaryProperty("isAvailable", appleBoolean)),
    "CodexPlugins" to listOf(AppleOrdinaryProperty("isAvailable", appleBoolean)),
    "CodexSkills" to listOf(AppleOrdinaryProperty("isAvailable", appleBoolean)),
)

private val d085Capabilities: List<AppleOrdinaryCapability> = buildList {
    d085PropertyOwners.forEach { (owner, properties) ->
        val ownerUsr = appleOwnerUsr("CodexAgent$owner")
        properties.forEach { property ->
            add(AppleOrdinaryCapability(
                applePropertyKey(owner, property), "$ownerUsr(py)${property.appleName}",
            ))
        }
    }
}.also { capabilities ->
    check(capabilities.size == 16 && capabilities.map { it.canonicalKey }.distinct().size == 16 &&
        capabilities.map { it.usr }.distinct().size == 16
    ) { "D085 Apple property capability inventory changed" }
}
private val d085CapabilitiesByKey = d085Capabilities.associateBy { it.canonicalKey }

internal val appleCompilerFixtureD065Capabilities: List<AppleOrdinaryCapability>
    get() = d065OrdinaryCapabilities

internal fun appleCompilerFixtureD065SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d065ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD065ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d065ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD073Capabilities: List<AppleOrdinaryCapability>
    get() = d073OrdinaryCapabilities

internal fun appleCompilerFixtureD073SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d073ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD073ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d073ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD074Capabilities: List<AppleOrdinaryCapability>
    get() = d074OrdinaryCapabilities

internal fun appleCompilerFixtureD074SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d074ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD074ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d074ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD075Capabilities: List<AppleOrdinaryCapability>
    get() = d075OrdinaryCapabilities

internal fun appleCompilerFixtureD075SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d075ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD075ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d075ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD076Capabilities: List<AppleOrdinaryCapability>
    get() = d076AuthorizationUrlCapabilities

internal fun appleCompilerFixtureD076SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d076ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD076ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d076ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD077Capabilities: List<AppleOrdinaryCapability>
    get() = d077OrdinaryCapabilities

internal fun appleCompilerFixtureD077SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d077ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD077ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d077ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD078Capabilities: List<AppleOrdinaryCapability>
    get() = d078OrdinaryCapabilities

internal fun appleCompilerFixtureD078SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d078ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD078ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d078ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD079Capabilities: List<AppleOrdinaryCapability>
    get() = d079OrdinaryCapabilities

internal fun appleCompilerFixtureD079SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d079ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD079ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d079ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD080Capabilities: List<AppleOrdinaryCapability>
    get() = d080Capabilities

internal fun appleCompilerFixtureD080SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d080ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD080ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d080ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD081Capabilities: List<AppleOrdinaryCapability>
    get() = d081Capabilities

internal fun appleCompilerFixtureD081SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d081ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD081ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d081ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD082Capabilities: List<AppleOrdinaryCapability>
    get() = d082ElicitationCapabilities

internal fun appleCompilerFixtureD082SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d082ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD082ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d082ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD083Capabilities: List<AppleOrdinaryCapability>
    get() = d083ProtocolCapabilities

internal fun appleCompilerFixtureD083SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d083ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD083ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d083ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD084Capabilities: List<AppleOrdinaryCapability>
    get() = d084Capabilities

internal fun appleCompilerFixtureD084SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d084ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD084SwiftCallbackSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d084ExpectedSwiftCallbackSymbols()

internal fun appleCompilerFixtureD084ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d084ExpectedObjectiveCSymbols()

internal val appleCompilerFixtureD085Capabilities: List<AppleOrdinaryCapability>
    get() = d085Capabilities

internal fun appleCompilerFixtureD085SwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d085ExpectedSwiftSymbols()

internal fun appleCompilerFixtureD085ObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> =
    d085ExpectedObjectiveCSymbols()

internal fun appleCompilerFixtureSwiftReferences(): List<AppleCompilerReference> =
    expectedSwiftAppleBindingReferences()

internal fun appleCompilerFixtureObjectiveCReferences(): List<AppleCompilerReference> =
    expectedObjectiveCAppleBindingReferences()

private val appleBindingMembers =
    appleCodexFailureMembers + appleConversationIdMembers + appleApprovalDecisionMembers +
        appleCollaborationModeMembers + appleMessageRoleMembers + appleInstallationScopeMembers +
        appleMcpEnvironmentSourceMembers + d065OrdinaryCapabilities.associate {
            "d065:${it.canonicalKey}" to it.usr
        } + d073OrdinaryCapabilities.associate {
            "d073:${it.canonicalKey}" to it.usr
        } + d074OrdinaryCapabilities.associate {
            "d074:${it.canonicalKey}" to it.usr
        } + d075OrdinaryCapabilities.associate {
            "d075:${it.canonicalKey}" to it.usr
        } + d076AuthorizationUrlCapabilities.associate {
            "d076:${it.canonicalKey}" to it.usr
        } + d077OrdinaryCapabilities.associate {
            "d077:${it.canonicalKey}" to it.usr
        } + d078OrdinaryCapabilities.associate {
            "d078:${it.canonicalKey}" to it.usr
        } + d079OrdinaryCapabilities.associate {
            "d079:${it.canonicalKey}" to it.usr
        } + d080Capabilities.associate {
            "d080:${it.canonicalKey}" to it.usr
        } + d081Capabilities.associate {
            "d081:${it.canonicalKey}" to it.usr
        } + d082ElicitationCapabilities.associate {
            "d082:${it.canonicalKey}" to it.usr
        } + d083ProtocolCapabilities.associate {
            "d083:${it.canonicalKey}" to it.usr
        } + d084Capabilities.associate {
            "d084:${it.canonicalKey}" to it.usr
        } + d085Capabilities.associate {
            "d085:${it.canonicalKey}" to it.usr
        }
private val appleBindingCoverageTokens =
    appleCodexFailureCoverageTokens + appleConversationIdCoverageTokens + appleApprovalDecisionCoverageTokens +
        appleCollaborationModeCoverageTokens + appleMessageRoleCoverageTokens + appleInstallationScopeCoverageTokens +
        appleMcpEnvironmentSourceCoverageTokens

private fun appleBindingShape(capability: String): String {
    val token = crossLanguageApiCoverageToken(capability)
    return appleBindingCoverageTokens.entries.singleOrNull { it.value == token }?.key
        ?: d065OrdinaryCapabilitiesByKey[capability]?.let { "d065:${it.canonicalKey}" }
        ?: d073OrdinaryCapabilitiesByKey[capability]?.let { "d073:${it.canonicalKey}" }
        ?: d074OrdinaryCapabilitiesByKey[capability]?.let { "d074:${it.canonicalKey}" }
        ?: d075OrdinaryCapabilitiesByKey[capability]?.let { "d075:${it.canonicalKey}" }
        ?: d076AuthorizationUrlCapabilitiesByKey[capability]?.let { "d076:${it.canonicalKey}" }
        ?: d077OrdinaryCapabilitiesByKey[capability]?.let { "d077:${it.canonicalKey}" }
        ?: d078OrdinaryCapabilitiesByKey[capability]?.let { "d078:${it.canonicalKey}" }
        ?: d079OrdinaryCapabilitiesByKey[capability]?.let { "d079:${it.canonicalKey}" }
        ?: d080CapabilitiesByKey[capability]?.let { "d080:${it.canonicalKey}" }
        ?: d081CapabilitiesByKey[capability]?.let { "d081:${it.canonicalKey}" }
        ?: d082ElicitationCapabilitiesByKey[capability]?.let { "d082:${it.canonicalKey}" }
        ?: d083ProtocolCapabilitiesByKey[capability]?.let { "d083:${it.canonicalKey}" }
        ?: d084CapabilitiesByKey[capability]?.let { "d084:${it.canonicalKey}" }
        ?: d085CapabilitiesByKey[capability]?.let { "d085:${it.canonicalKey}" }
        ?: error("Unexpected canonical Apple binding capability: $capability")
}

internal data class AppleCompilerSymbol(
    val precise: String,
    val interfaceLanguage: String,
    val kind: String,
    val path: List<String>,
    val title: String,
    val accessLevel: String,
    val declaration: String,
    val typeIdentifiers: List<String>,
    val parameters: List<Pair<String, String>>,
    val returns: String?,
)

internal data class AppleCompilerReference(
    val precise: String,
    val kind: String,
    val name: String,
    val receiverType: String?,
    val valueType: String,
    val argumentTypes: List<String>,
)

internal data class ExpectedAppleCompilerSymbol(
    val kind: String,
    val path: List<String>,
    val title: String,
    val access: String,
    val declaration: String,
    val typeIdentifiers: List<String>,
    val parameters: List<Pair<String, String>> = emptyList(),
    val returns: String? = null,
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
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)chatGptValue:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexAuthorizationUrl", "Companion", "chatGpt(value:)"),
        "chatGpt(value:)", "open", "func chatGpt(value: String) -> CodexAuthorizationUrl",
        listOf("s:SS", APPLE_AUTHORIZATION_URL_OWNER_USR), listOf("value" to "value: String"),
        "CodexAuthorizationUrl",
    ),
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)externalValue:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexAuthorizationUrl", "Companion", "external(value:)"),
        "external(value:)", "open", "func external(value: String) -> CodexAuthorizationUrl",
        listOf("s:SS", APPLE_AUTHORIZATION_URL_OWNER_USR), listOf("value" to "value: String"),
        "CodexAuthorizationUrl",
    ),
    "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)value" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexAuthorizationUrl", "value"), "value", "open",
        "var value: String { get }", listOf("s:SS"),
    ),
    "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)purpose" to ExpectedAppleCompilerSymbol(
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

private fun d079ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d079AppleValues.forEach { owner ->
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

private fun d080ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d080AppleValues.forEach { owner ->
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
    val owner = "AgentInteractionState"
    val ownerUsr = appleOwnerUsr("CodexAgentAgentInteractionState")
    put("$ownerUsr(im)isResolvingInteraction:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf(owner, "isResolving(interaction:)"), "isResolving(interaction:)", "open",
        "func isResolving(interaction: any AgentPendingInteraction) -> Bool",
        listOf(applePendingInteractionType.swiftIdentifier, appleBoolean.swiftIdentifier),
        listOf("interaction" to "interaction: any AgentPendingInteraction"), "Bool",
    ))
    put("$ownerUsr(im)pendingForConversationId:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf(owner, "pendingFor(conversationId:)"), "pendingFor(conversationId:)", "open",
        "func pendingFor(conversationId: ConversationId) -> [any AgentPendingInteraction]",
        listOf(appleConversationIdType.swiftIdentifier, applePendingInteractionType.swiftIdentifier),
        listOf("conversationId" to "conversationId: ConversationId"), "[any AgentPendingInteraction]",
    ))
}

private fun d081ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d081AppleObjects.forEach { (_, objectiveCName) ->
        val swiftName = objectiveCName.removePrefix("CodexAgent")
        val ownerUsr = appleOwnerUsr(objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(swiftName), swiftName, "public", "class $swiftName", emptyList(),
        ))
        put("$ownerUsr(cpy)shared", ExpectedAppleCompilerSymbol(
            "swift.type.property", listOf(swiftName, "shared"), "shared", "open",
            "class var shared: $swiftName { get }", listOf(ownerUsr),
        ))
    }
}

private fun d082ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion") to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentElicitationResponse", "Companion"),
        "AgentElicitationResponse.Companion", "public", "class Companion", emptyList(),
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)cancel" to
        ExpectedAppleCompilerSymbol(
            "swift.method", listOf("AgentElicitationResponse", "Companion", "cancel()"),
            "cancel()", "open", "func cancel() -> AgentElicitationResponse",
            listOf(appleOwnerUsr("CodexAgentAgentElicitationResponse")), emptyList(),
            "AgentElicitationResponse",
        ),
    "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)decline" to
        ExpectedAppleCompilerSymbol(
            "swift.method", listOf("AgentElicitationResponse", "Companion", "decline()"),
            "decline()", "open", "func decline() -> AgentElicitationResponse",
            listOf(appleOwnerUsr("CodexAgentAgentElicitationResponse")), emptyList(),
            "AgentElicitationResponse",
        ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptContent:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("AgentElicitation", "accept(content:)"), "accept(content:)", "open",
        "func accept(content: [String : any AgentFormValue]) -> AgentElicitationResponse",
        listOf(
            "s:SS", "c:objc(pl)CodexAgentAgentFormValue",
            appleOwnerUsr("CodexAgentAgentElicitationResponse"),
        ),
        listOf("content" to "content: [String : any AgentFormValue]"), "AgentElicitationResponse",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptsResponse:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("AgentElicitation", "accepts(response:)"), "accepts(response:)", "open",
        "func accepts(response: AgentElicitationResponse) -> Bool",
        listOf(appleOwnerUsr("CodexAgentAgentElicitationResponse"), "s:Sb"),
        listOf("response" to "response: AgentElicitationResponse"), "Bool",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)initialValues" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("AgentElicitation", "initialValues()"), "initialValues()", "open",
        "func initialValues() -> [String : any AgentFormValue]",
        listOf("s:SS", "c:objc(pl)CodexAgentAgentFormValue"), emptyList(),
        "[String : any AgentFormValue]",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)validateContent:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("AgentElicitation", "validate(content:)"), "validate(content:)", "open",
        "func validate(content: [String : any AgentFormValue]) -> AgentElicitationValidation",
        listOf(
            "s:SS", "c:objc(pl)CodexAgentAgentFormValue",
            appleOwnerUsr("CodexAgentAgentElicitationValidation"),
        ),
        listOf("content" to "content: [String : any AgentFormValue]"), "AgentElicitationValidation",
    ),
    "${appleOwnerUsr("CodexAgentAgentFormField")}(im)acceptsValue:" to ExpectedAppleCompilerSymbol(
        "swift.method", listOf("AgentFormField", "accepts(value:)"), "accepts(value:)", "open",
        "func accepts(value: (any AgentFormValue)?) -> Bool",
        listOf("c:objc(pl)CodexAgentAgentFormValue", "s:Sb"),
        listOf("value" to "value: (any AgentFormValue)?"), "Bool",
    ),
)

private fun d083ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    "c:objc(pl)CodexAgentAgentIntegration" to ExpectedAppleCompilerSymbol(
        "swift.protocol", listOf("AgentIntegration"), "AgentIntegration", "public",
        "protocol AgentIntegration", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentIntegration(py)displayName" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentIntegration", "displayName"), "displayName", "public",
        "var displayName: String { get }", listOf("s:SS"),
    ),
    "c:objc(pl)CodexAgentAgentIntegration(py)id" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentIntegration", "id"), "id", "public",
        "var id: String { get }", listOf("s:SS"),
    ),
    "c:objc(pl)CodexAgentAgentInvocation" to ExpectedAppleCompilerSymbol(
        "swift.protocol", listOf("AgentInvocation"), "AgentInvocation", "public",
        "protocol AgentInvocation", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentInvocation(py)key" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentInvocation", "key"), "key", "public",
        "var key: String { get }", listOf("s:SS"),
    ),
    "c:objc(pl)CodexAgentAgentInvocation(py)name" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentInvocation", "name"), "name", "public",
        "var name: String { get }", listOf("s:SS"),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction" to ExpectedAppleCompilerSymbol(
        "swift.protocol", listOf("AgentPendingInteraction"), "AgentPendingInteraction", "public",
        "protocol AgentPendingInteraction", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentPendingInteraction", "conversationId"), "conversationId", "public",
        "var conversationId: ConversationId { get }", listOf(APPLE_CONVERSATION_ID_OWNER_USR),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId" to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("AgentPendingInteraction", "requestId"), "requestId", "public",
        "var requestId: String { get }", listOf("s:SS"),
    ),
)

private fun d084ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d084AppleValues.forEach { owner ->
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
    val hostUsr = appleOwnerUsr("CodexAgentCodexHost")
    put("$hostUsr(im)closeWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "close()"), "close()", "open",
        "func close() async throws", emptyList(), emptyList(), "Void",
    ))
    put("$hostUsr(im)selectWorkspaceSelection:completionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "selectWorkspace(selection:)"),
        "selectWorkspace(selection:)", "open",
        "func selectWorkspace(selection: any CodexWorkspaceSelection) async throws",
        listOf("c:objc(pl)CodexAgentCodexWorkspaceSelection"),
        listOf("selection" to "selection: any CodexWorkspaceSelection"), "Void",
    ))
    put("$hostUsr(im)startWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "start()"), "start()", "open",
        "func start() async throws", emptyList(), emptyList(), "Void",
    ))
    put("$hostUsr(py)lifecycleState", ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexHost", "lifecycleState"), "lifecycleState", "open",
        "var lifecycleState: any Kotlinx_coroutines_coreStateFlow { get }",
        listOf("c:objc(pl)CodexAgentKotlinx_coroutines_coreStateFlow"),
    ))
}

private fun d084ExpectedSwiftCallbackSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    val hostUsr = appleOwnerUsr("CodexAgentCodexHost")
    put("$hostUsr(im)closeWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "close(completionHandler:)"),
        "close(completionHandler:)", "open",
        "func close(completionHandler: @escaping @Sendable ((any Error)?) -> Void)",
        listOf("s:s5ErrorP", "s:s4Voida"),
        listOf("completionHandler" to "completionHandler: @Sendable ((any Error)?) -> Void"), "Void",
    ))
    put("$hostUsr(im)selectWorkspaceSelection:completionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "selectWorkspace(selection:completionHandler:)"),
        "selectWorkspace(selection:completionHandler:)", "open",
        "func selectWorkspace(selection: any CodexWorkspaceSelection, " +
            "completionHandler: @escaping @Sendable ((any Error)?) -> Void)",
        listOf("c:objc(pl)CodexAgentCodexWorkspaceSelection", "s:s5ErrorP", "s:s4Voida"),
        listOf(
            "selection" to "selection: any CodexWorkspaceSelection",
            "completionHandler" to "completionHandler: @Sendable ((any Error)?) -> Void",
        ),
        "Void",
    ))
    put("$hostUsr(im)startWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "swift.method", listOf("CodexHost", "start(completionHandler:)"),
        "start(completionHandler:)", "open",
        "func start(completionHandler: @escaping @Sendable ((any Error)?) -> Void)",
        listOf("s:s5ErrorP", "s:s4Voida"),
        listOf("completionHandler" to "completionHandler: @Sendable ((any Error)?) -> Void"), "Void",
    ))
}

private fun d085ExpectedSwiftSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d085PropertyOwners.forEach { (owner, properties) ->
        val ownerUsr = appleOwnerUsr("CodexAgent$owner")
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "swift.class", listOf(owner), owner, "public", "class $owner", emptyList(),
        ))
        properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "swift.property", listOf(owner, property.appleName), property.appleName, "open",
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
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)chatGptValue:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexAuthorizationUrlCompanion", "chatGptValue:"),
        "chatGptValue:", "public",
        "- (CodexAgentCodexAuthorizationUrl *) chatGptValue:(NSString *) value;",
        listOf(APPLE_AUTHORIZATION_URL_OWNER_USR, "c:objc(cs)NSString"),
        listOf("value" to "(NSString *) value"), "CodexAgentCodexAuthorizationUrl *",
    ),
    "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)externalValue:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexAuthorizationUrlCompanion", "externalValue:"),
        "externalValue:", "public",
        "- (CodexAgentCodexAuthorizationUrl *) externalValue:(NSString *) value;",
        listOf(APPLE_AUTHORIZATION_URL_OWNER_USR, "c:objc(cs)NSString"),
        listOf("value" to "(NSString *) value"), "CodexAgentCodexAuthorizationUrl *",
    ),
    "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)value" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexAuthorizationUrl", "value"),
        "value", "public", "@property (readonly) NSString * value;", listOf("c:objc(cs)NSString"),
    ),
    "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)purpose" to ExpectedAppleCompilerSymbol(
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

private fun d079ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d079AppleValues.forEach { owner ->
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

private fun d080ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d080AppleValues.forEach { owner ->
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
    val owner = "CodexAgentAgentInteractionState"
    val ownerUsr = appleOwnerUsr(owner)
    put("$ownerUsr(im)isResolvingInteraction:", ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf(owner, "isResolvingInteraction:"), "isResolvingInteraction:", "public",
        "- (BOOL) isResolvingInteraction:(id<CodexAgentAgentPendingInteraction>) interaction;",
        listOf(appleBoolean.objectiveCIdentifier, applePendingInteractionType.objectiveCIdentifier),
        listOf("interaction" to "(id<CodexAgentAgentPendingInteraction>) interaction"), "BOOL",
    ))
    put("$ownerUsr(im)pendingForConversationId:", ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf(owner, "pendingForConversationId:"), "pendingForConversationId:", "public",
        "- (NSArray<id<CodexAgentAgentPendingInteraction>> *) " +
            "pendingForConversationId:(CodexAgentConversationId *) conversationId;",
        listOf(applePendingInteractionList.objectiveCIdentifier, appleConversationIdType.objectiveCIdentifier),
        listOf("conversationId" to "(CodexAgentConversationId *) conversationId"),
        "NSArray<id<CodexAgentAgentPendingInteraction>> *",
    ))
}

private fun d081ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d081AppleObjects.forEach { (_, objectiveCName) ->
        val ownerUsr = appleOwnerUsr(objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(objectiveCName), objectiveCName, "public",
            "@interface $objectiveCName : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        put("$ownerUsr(cpy)shared", ExpectedAppleCompilerSymbol(
            "objective-c.type.property", listOf(objectiveCName, "shared"), "shared", "public",
            "@property (class, readonly, getter=shared) $objectiveCName * shared;", listOf(ownerUsr),
        ))
    }
}

private fun d082ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion") to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentElicitationResponseCompanion"),
        "CodexAgentAgentElicitationResponseCompanion", "public",
        "@interface CodexAgentAgentElicitationResponseCompanion : CodexAgentBase",
        listOf("c:objc(cs)CodexAgentBase"),
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)cancel" to
        ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf("CodexAgentAgentElicitationResponseCompanion", "cancel"),
            "cancel", "public", "- (CodexAgentAgentElicitationResponse *) cancel;",
            listOf(appleOwnerUsr("CodexAgentAgentElicitationResponse")), emptyList(),
            "CodexAgentAgentElicitationResponse *",
        ),
    "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)decline" to
        ExpectedAppleCompilerSymbol(
            "objective-c.method", listOf("CodexAgentAgentElicitationResponseCompanion", "decline"),
            "decline", "public", "- (CodexAgentAgentElicitationResponse *) decline;",
            listOf(appleOwnerUsr("CodexAgentAgentElicitationResponse")), emptyList(),
            "CodexAgentAgentElicitationResponse *",
        ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptContent:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentAgentElicitation", "acceptContent:"),
        "acceptContent:", "public",
        "- (CodexAgentAgentElicitationResponse *) " +
            "acceptContent:(NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *) content;",
        listOf(
            appleOwnerUsr("CodexAgentAgentElicitationResponse"), "c:Q\$objc(cs)NSDictionary",
        ),
        listOf("content" to "(NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *) content"),
        "CodexAgentAgentElicitationResponse *",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptsResponse:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentAgentElicitation", "acceptsResponse:"),
        "acceptsResponse:", "public",
        "- (BOOL) acceptsResponse:(CodexAgentAgentElicitationResponse *) response;",
        listOf("c:@T@BOOL", appleOwnerUsr("CodexAgentAgentElicitationResponse")),
        listOf("response" to "(CodexAgentAgentElicitationResponse *) response"), "BOOL",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)initialValues" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentAgentElicitation", "initialValues"),
        "initialValues", "public",
        "- (NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *) initialValues;",
        listOf("c:Q\$objc(cs)NSDictionary"), emptyList(),
        "NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *",
    ),
    "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)validateContent:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentAgentElicitation", "validateContent:"),
        "validateContent:", "public",
        "- (CodexAgentAgentElicitationValidation *) " +
            "validateContent:(NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *) content;",
        listOf(
            appleOwnerUsr("CodexAgentAgentElicitationValidation"), "c:Q\$objc(cs)NSDictionary",
        ),
        listOf("content" to "(NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *) content"),
        "CodexAgentAgentElicitationValidation *",
    ),
    "${appleOwnerUsr("CodexAgentAgentFormField")}(im)acceptsValue:" to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentAgentFormField", "acceptsValue:"),
        "acceptsValue:", "public", "- (BOOL) acceptsValue:(id<CodexAgentAgentFormValue>) value;",
        listOf("c:@T@BOOL", "c:Qoobjc(pl)CodexAgentAgentFormValue"),
        listOf("value" to "(id<CodexAgentAgentFormValue>) value"), "BOOL",
    ),
)

private fun d083ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = linkedMapOf(
    "c:objc(pl)CodexAgentAgentIntegration" to ExpectedAppleCompilerSymbol(
        "objective-c.protocol", listOf("CodexAgentAgentIntegration"),
        "CodexAgentAgentIntegration", "public", "@protocol CodexAgentAgentIntegration", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentIntegration(py)displayName" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentIntegration", "displayName"),
        "displayName", "public", "@property (readonly) NSString * displayName;",
        listOf("c:objc(cs)NSString"),
    ),
    "c:objc(pl)CodexAgentAgentIntegration(py)id" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentIntegration", "id"),
        "id", "public", "@property (readonly) NSString * id;", listOf("c:objc(cs)NSString"),
    ),
    "c:objc(pl)CodexAgentAgentInvocation" to ExpectedAppleCompilerSymbol(
        "objective-c.protocol", listOf("CodexAgentAgentInvocation"),
        "CodexAgentAgentInvocation", "public", "@protocol CodexAgentAgentInvocation", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentInvocation(py)key" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentInvocation", "key"),
        "key", "public", "@property (readonly) NSString * key;", listOf("c:objc(cs)NSString"),
    ),
    "c:objc(pl)CodexAgentAgentInvocation(py)name" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentInvocation", "name"),
        "name", "public", "@property (readonly) NSString * name;", listOf("c:objc(cs)NSString"),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction" to ExpectedAppleCompilerSymbol(
        "objective-c.protocol", listOf("CodexAgentAgentPendingInteraction"),
        "CodexAgentAgentPendingInteraction", "public",
        "@protocol CodexAgentAgentPendingInteraction", emptyList(),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentPendingInteraction", "conversationId"),
        "conversationId", "public", "@property (readonly) CodexAgentConversationId * conversationId;",
        listOf(APPLE_CONVERSATION_ID_OWNER_USR),
    ),
    "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId" to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentAgentPendingInteraction", "requestId"),
        "requestId", "public", "@property (readonly) NSString * requestId;",
        listOf("c:objc(cs)NSString"),
    ),
)

private fun d084ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d084AppleValues.forEach { owner ->
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
    val host = "CodexAgentCodexHost"
    val hostUsr = appleOwnerUsr(host)
    put("$hostUsr(im)closeWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf(host, "closeWithCompletionHandler:"),
        "closeWithCompletionHandler:", "public",
        "- (void) closeWithCompletionHandler:(void (^)(NSError *)) completionHandler;",
        listOf("c:v", "c:v", "c:objc(cs)NSError"),
        listOf("completionHandler" to "(void (^)(NSError *)) completionHandler"), "void",
    ))
    put("$hostUsr(im)selectWorkspaceSelection:completionHandler:", ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf(host, "selectWorkspaceSelection:completionHandler:"),
        "selectWorkspaceSelection:completionHandler:", "public",
        "- (void) selectWorkspaceSelection:(id<CodexAgentCodexWorkspaceSelection>) selection " +
            "completionHandler:(void (^)(NSError *)) completionHandler;",
        listOf("c:v", "c:Qoobjc(pl)CodexAgentCodexWorkspaceSelection", "c:v", "c:objc(cs)NSError"),
        listOf(
            "selection" to "(id<CodexAgentCodexWorkspaceSelection>) selection",
            "completionHandler" to "(void (^)(NSError *)) completionHandler",
        ),
        "void",
    ))
    put("$hostUsr(im)startWithCompletionHandler:", ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf(host, "startWithCompletionHandler:"),
        "startWithCompletionHandler:", "public",
        "- (void) startWithCompletionHandler:(void (^)(NSError *)) completionHandler;",
        listOf("c:v", "c:v", "c:objc(cs)NSError"),
        listOf("completionHandler" to "(void (^)(NSError *)) completionHandler"), "void",
    ))
    put("$hostUsr(py)lifecycleState", ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf(host, "lifecycleState"), "lifecycleState", "public",
        "@property (readonly) id<CodexAgentKotlinx_coroutines_coreStateFlow> lifecycleState;",
        listOf("c:Qoobjc(pl)CodexAgentKotlinx_coroutines_coreStateFlow"),
    ))
}

private fun d085ExpectedObjectiveCSymbols(): Map<String, ExpectedAppleCompilerSymbol> = buildMap {
    d085PropertyOwners.forEach { (owner, properties) ->
        val objectiveCName = "CodexAgent$owner"
        val ownerUsr = appleOwnerUsr(objectiveCName)
        put(ownerUsr, ExpectedAppleCompilerSymbol(
            "objective-c.class", listOf(objectiveCName), objectiveCName, "public",
            "@interface $objectiveCName : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
        ))
        properties.forEach { property ->
            put("$ownerUsr(py)${property.appleName}", ExpectedAppleCompilerSymbol(
                "objective-c.property", listOf(objectiveCName, property.appleName),
                property.appleName, "public",
                "@property (readonly) ${property.type.objectiveC} ${property.appleName};",
                listOf(property.type.objectiveCIdentifier),
            ))
        }
    }
}

private data class AppleCompilerSlice(
    val name: String,
    val sdkName: String,
    val targetTriple: String,
)

private data class InspectedAppleCompilerSlice(
    val specification: AppleCompilerSlice,
    val sdkVersion: String,
    val framework: File,
    val swiftSurface: List<AppleCompilerSymbol>,
    val objectiveCSurface: List<AppleCompilerSymbol>,
    val swiftReferences: List<AppleCompilerReference>,
    val objectiveCReferences: List<AppleCompilerReference>,
)

private val appleCompilerSlices = listOf(
    AppleCompilerSlice("ios-arm64", "iphoneos", "arm64-apple-ios15.0"),
    AppleCompilerSlice("ios-arm64-simulator", "iphonesimulator", "arm64-apple-ios15.0-simulator"),
)

private val expectedSwiftAppleBindingSymbols = linkedMapOf(
    APPLE_CODEX_FAILURE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("CodexFailure"), "CodexFailure", "public", "class CodexFailure", emptyList(),
    ),
    appleCodexFailureMembers.getValue("constructor:<init>") to ExpectedAppleCompilerSymbol(
        "swift.init", listOf("CodexFailure", "init(code:message:isRecoverable:)"),
        "init(code:message:isRecoverable:)", "public",
        "init(code: String, message: String, isRecoverable: Bool)", listOf("s:SS", "s:SS", "s:Sb"),
        listOf("code" to "code: String", "message" to "message: String", "isRecoverable" to "isRecoverable: Bool"),
    ),
    appleCodexFailureMembers.getValue("property:code") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "code"), "code", "open",
        "var code: String { get }", listOf("s:SS"),
    ),
    appleCodexFailureMembers.getValue("property:isRecoverable") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "isRecoverable"), "isRecoverable", "open",
        "var isRecoverable: Bool { get }", listOf("s:Sb"),
    ),
    appleCodexFailureMembers.getValue("property:message") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("CodexFailure", "message"), "message", "open",
        "var message: String { get }", listOf("s:SS"),
    ),
    APPLE_CONVERSATION_ID_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("ConversationId"), "ConversationId", "public",
        "class ConversationId", emptyList(),
    ),
    appleConversationIdMembers.getValue("conversation-id:constructor:<init>") to ExpectedAppleCompilerSymbol(
        "swift.init", listOf("ConversationId", "init(value:)"), "init(value:)", "public",
        "init(value: String)", listOf("s:SS"), listOf("value" to "value: String"),
    ),
    appleConversationIdMembers.getValue("conversation-id:property:value") to ExpectedAppleCompilerSymbol(
        "swift.property", listOf("ConversationId", "value"), "value", "open",
        "var value: String { get }", listOf("s:SS"),
    ),
    APPLE_APPROVAL_DECISION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentApprovalDecision"), "AgentApprovalDecision", "public",
        "class AgentApprovalDecision", emptyList(),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:ACCEPT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentApprovalDecision", "accept"), "accept", "open",
        "class var accept: AgentApprovalDecision { get }", listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:DECLINE") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentApprovalDecision", "decline"), "decline", "open",
        "class var decline: AgentApprovalDecision { get }", listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    APPLE_COLLABORATION_MODE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentCollaborationMode"), "AgentCollaborationMode", "public",
        "class AgentCollaborationMode", emptyList(),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:DEFAULT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentCollaborationMode", "default_"), "default_", "open",
        "class var default_: AgentCollaborationMode { get }", listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:PLAN") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentCollaborationMode", "plan"), "plan", "open",
        "class var plan: AgentCollaborationMode { get }", listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    APPLE_MESSAGE_ROLE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentMessageRole"), "AgentMessageRole", "public",
        "class AgentMessageRole", emptyList(),
    ),
    appleMessageRoleMembers.getValue("enum-entry:USER") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMessageRole", "user"), "user", "open",
        "class var user: AgentMessageRole { get }", listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    appleMessageRoleMembers.getValue("enum-entry:ASSISTANT") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMessageRole", "assistant"), "assistant", "open",
        "class var assistant: AgentMessageRole { get }", listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    APPLE_INSTALLATION_SCOPE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentInstallationScope"), "AgentInstallationScope", "public",
        "class AgentInstallationScope", emptyList(),
    ),
    appleInstallationScopeMembers.getValue("enum-entry:User") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentInstallationScope", "user"), "user", "open",
        "class var user: AgentInstallationScope { get }", listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR),
    ),
    appleInstallationScopeMembers.getValue("enum-entry:Workspace") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentInstallationScope", "workspace"), "workspace", "open",
        "class var workspace: AgentInstallationScope { get }", listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR),
    ),
    APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "swift.class", listOf("AgentMcpEnvironmentSource"), "AgentMcpEnvironmentSource", "public",
        "class AgentMcpEnvironmentSource", emptyList(),
    ),
    appleMcpEnvironmentSourceMembers.getValue("enum-entry:LOCAL") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMcpEnvironmentSource", "local"), "local", "open",
        "class var local: AgentMcpEnvironmentSource { get }", listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR),
    ),
    appleMcpEnvironmentSourceMembers.getValue("enum-entry:REMOTE") to ExpectedAppleCompilerSymbol(
        "swift.type.property", listOf("AgentMcpEnvironmentSource", "remote"), "remote", "open",
        "class var remote: AgentMcpEnvironmentSource { get }", listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR),
    ),
) + d065ExpectedSwiftSymbols() + d073ExpectedSwiftSymbols() + d074ExpectedSwiftSymbols() +
    d075ExpectedSwiftSymbols() + d076ExpectedSwiftSymbols() + d077ExpectedSwiftSymbols() +
    d078ExpectedSwiftSymbols() + d079ExpectedSwiftSymbols() + d080ExpectedSwiftSymbols() +
    d081ExpectedSwiftSymbols() + d082ExpectedSwiftSymbols() + d083ExpectedSwiftSymbols() +
    d084ExpectedSwiftSymbols() + d085ExpectedSwiftSymbols()

private val expectedObjectiveCAppleBindingSymbols = linkedMapOf(
    APPLE_CODEX_FAILURE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentCodexFailure"), "CodexAgentCodexFailure", "public",
        "@interface CodexAgentCodexFailure : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
    ),
    appleCodexFailureMembers.getValue("constructor:<init>") to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentCodexFailure", "initWithCode:message:isRecoverable:"),
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
    appleCodexFailureMembers.getValue("property:code") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "code"), "code", "public",
        "@property (readonly) NSString * code;", listOf("c:objc(cs)NSString"),
    ),
    appleCodexFailureMembers.getValue("property:isRecoverable") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "isRecoverable"), "isRecoverable", "public",
        "@property (readonly) BOOL isRecoverable;", listOf("c:@T@BOOL"),
    ),
    appleCodexFailureMembers.getValue("property:message") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentCodexFailure", "message"), "message", "public",
        "@property (readonly) NSString * message;", listOf("c:objc(cs)NSString"),
    ),
    APPLE_CONVERSATION_ID_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentConversationId"), "CodexAgentConversationId", "public",
        "@interface CodexAgentConversationId : CodexAgentBase", listOf("c:objc(cs)CodexAgentBase"),
    ),
    appleConversationIdMembers.getValue("conversation-id:constructor:<init>") to ExpectedAppleCompilerSymbol(
        "objective-c.method", listOf("CodexAgentConversationId", "initWithValue:"),
        "initWithValue:", "public", "- (instancetype) initWithValue:(NSString *) value;",
        listOf("c:objc(cs)NSString"), listOf("value" to "(NSString *) value"), "instancetype",
    ),
    appleConversationIdMembers.getValue("conversation-id:property:value") to ExpectedAppleCompilerSymbol(
        "objective-c.property", listOf("CodexAgentConversationId", "value"), "value", "public",
        "@property (readonly) NSString * value;", listOf("c:objc(cs)NSString"),
    ),
    APPLE_APPROVAL_DECISION_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentApprovalDecision"), "CodexAgentAgentApprovalDecision", "public",
        "@interface CodexAgentAgentApprovalDecision : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:ACCEPT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentApprovalDecision", "accept"), "accept", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * accept;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    appleApprovalDecisionMembers.getValue("enum-entry:DECLINE") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentApprovalDecision", "decline"), "decline", "public",
        "@property (class, readonly) CodexAgentAgentApprovalDecision * decline;",
        listOf(APPLE_APPROVAL_DECISION_OWNER_USR),
    ),
    APPLE_COLLABORATION_MODE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentCollaborationMode"),
        "CodexAgentAgentCollaborationMode", "public",
        "@interface CodexAgentAgentCollaborationMode : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:DEFAULT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentCollaborationMode", "default_"), "default_", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * default_;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    appleCollaborationModeMembers.getValue("enum-entry:PLAN") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentCollaborationMode", "plan"), "plan", "public",
        "@property (class, readonly) CodexAgentAgentCollaborationMode * plan;",
        listOf(APPLE_COLLABORATION_MODE_OWNER_USR),
    ),
    APPLE_MESSAGE_ROLE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentMessageRole"),
        "CodexAgentAgentMessageRole", "public",
        "@interface CodexAgentAgentMessageRole : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleMessageRoleMembers.getValue("enum-entry:USER") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMessageRole", "user"), "user", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * user;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    appleMessageRoleMembers.getValue("enum-entry:ASSISTANT") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMessageRole", "assistant"), "assistant", "public",
        "@property (class, readonly) CodexAgentAgentMessageRole * assistant;",
        listOf(APPLE_MESSAGE_ROLE_OWNER_USR),
    ),
    APPLE_INSTALLATION_SCOPE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentInstallationScope"),
        "CodexAgentAgentInstallationScope", "public",
        "@interface CodexAgentAgentInstallationScope : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleInstallationScopeMembers.getValue("enum-entry:User") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentInstallationScope", "user"), "user", "public",
        "@property (class, readonly) CodexAgentAgentInstallationScope * user;",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR),
    ),
    appleInstallationScopeMembers.getValue("enum-entry:Workspace") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentInstallationScope", "workspace"), "workspace", "public",
        "@property (class, readonly) CodexAgentAgentInstallationScope * workspace;",
        listOf(APPLE_INSTALLATION_SCOPE_OWNER_USR),
    ),
    APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR to ExpectedAppleCompilerSymbol(
        "objective-c.class", listOf("CodexAgentAgentMcpEnvironmentSource"),
        "CodexAgentAgentMcpEnvironmentSource", "public",
        "@interface CodexAgentAgentMcpEnvironmentSource : CodexAgentKotlinEnum",
        listOf("c:objc(cs)CodexAgentKotlinEnum"),
    ),
    appleMcpEnvironmentSourceMembers.getValue("enum-entry:LOCAL") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMcpEnvironmentSource", "local"), "local", "public",
        "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * local;",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR),
    ),
    appleMcpEnvironmentSourceMembers.getValue("enum-entry:REMOTE") to ExpectedAppleCompilerSymbol(
        "objective-c.type.property", listOf("CodexAgentAgentMcpEnvironmentSource", "remote"), "remote", "public",
        "@property (class, readonly) CodexAgentAgentMcpEnvironmentSource * remote;",
        listOf(APPLE_MCP_ENVIRONMENT_SOURCE_OWNER_USR),
    ),
) + d065ExpectedObjectiveCSymbols() + d073ExpectedObjectiveCSymbols() + d074ExpectedObjectiveCSymbols() +
    d075ExpectedObjectiveCSymbols() + d076ExpectedObjectiveCSymbols() + d077ExpectedObjectiveCSymbols() +
    d078ExpectedObjectiveCSymbols() + d079ExpectedObjectiveCSymbols() + d080ExpectedObjectiveCSymbols() +
    d081ExpectedObjectiveCSymbols() + d082ExpectedObjectiveCSymbols() + d083ExpectedObjectiveCSymbols() +
    d084ExpectedObjectiveCSymbols() + d085ExpectedObjectiveCSymbols()

internal fun appleBindingCapabilityKeys(memberKeys: List<String>): List<String> {
    val ownerPrefixes = setOf(
        "common|owner=$APPLE_CODEX_FAILURE_CANONICAL_OWNER|",
        "common|owner=$APPLE_CONVERSATION_ID_CANONICAL_OWNER|",
        "common|owner=$APPLE_APPROVAL_DECISION_CANONICAL_OWNER|",
        "common|owner=$APPLE_COLLABORATION_MODE_CANONICAL_OWNER|",
        "common|owner=$APPLE_MESSAGE_ROLE_CANONICAL_OWNER|",
        "common|owner=$APPLE_INSTALLATION_SCOPE_CANONICAL_OWNER|",
        "common|owner=$APPLE_MCP_ENVIRONMENT_SOURCE_CANONICAL_OWNER|",
    )
    val byShape = memberKeys.filter { key -> ownerPrefixes.any { prefix -> key.startsWith(prefix) } }.groupBy { key ->
        appleBindingShape(key)
    }
    val priorMembers = appleBindingMembers.filterKeys {
        !it.startsWith("d065:") && !it.startsWith("d073:") && !it.startsWith("d074:") &&
            !it.startsWith("d075:") && !it.startsWith("d076:") && !it.startsWith("d077:") &&
            !it.startsWith("d078:") && !it.startsWith("d079:") && !it.startsWith("d080:") &&
            !it.startsWith("d081:") && !it.startsWith("d082:") && !it.startsWith("d083:") &&
            !it.startsWith("d084:") && !it.startsWith("d085:")
    }
    check(byShape.keys == priorMembers.keys) {
        "Canonical Apple binding capability set changed: ${byShape.keys.sorted()}"
    }
    check(byShape.values.all { it.size == 1 }) { "Canonical Apple binding capabilities are overloaded" }
    val d065Keys = d065OrdinaryCapabilities.map { it.canonicalKey }
    check(d065Keys.all(memberKeys::contains)) { "Canonical D065 Apple binding capability set changed" }
    val d073Keys = d073OrdinaryCapabilities.map { it.canonicalKey }
    check(d073Keys.all(memberKeys::contains)) { "Canonical D073 Apple binding capability set changed" }
    val d074Keys = d074OrdinaryCapabilities.map { it.canonicalKey }
    check(d074Keys.all(memberKeys::contains)) { "Canonical D074 Apple binding capability set changed" }
    val d075Keys = d075OrdinaryCapabilities.map { it.canonicalKey }
    check(d075Keys.all(memberKeys::contains)) { "Canonical D075 Apple binding capability set changed" }
    val d076Keys = d076AuthorizationUrlCapabilities.map { it.canonicalKey }
    check(d076Keys.all(memberKeys::contains)) { "Canonical D076 Apple binding capability set changed" }
    val d077Keys = d077OrdinaryCapabilities.map { it.canonicalKey }
    check(d077Keys.all(memberKeys::contains)) { "Canonical D077 Apple binding capability set changed" }
    val d078Keys = d078OrdinaryCapabilities.map { it.canonicalKey }
    check(d078Keys.all(memberKeys::contains)) { "Canonical D078 Apple binding capability set changed" }
    val d079Keys = d079OrdinaryCapabilities.map { it.canonicalKey }
    check(d079Keys.all(memberKeys::contains)) { "Canonical D079 Apple binding capability set changed" }
    val d080Keys = d080Capabilities.map { it.canonicalKey }
    check(d080Keys.all(memberKeys::contains)) { "Canonical D080 Apple binding capability set changed" }
    val d081Keys = d081Capabilities.map { it.canonicalKey }
    check(d081Keys.all(memberKeys::contains)) { "Canonical D081 Apple binding capability set changed" }
    val d082Keys = d082ElicitationCapabilities.map { it.canonicalKey }
    check(d082Keys.all(memberKeys::contains)) { "Canonical D082 Apple binding capability set changed" }
    val d083Keys = d083ProtocolCapabilities.map { it.canonicalKey }
    check(d083Keys.all(memberKeys::contains)) { "Canonical D083 Apple binding capability set changed" }
    val d084Keys = d084Capabilities.map { it.canonicalKey }
    check(d084Keys.all(memberKeys::contains)) { "Canonical D084 Apple binding capability set changed" }
    val d085Keys = d085Capabilities.map { it.canonicalKey }
    check(d085Keys.all(memberKeys::contains)) { "Canonical D085 Apple binding capability set changed" }
    return (byShape.values.map { it.single() } + d065Keys + d073Keys + d074Keys + d075Keys + d076Keys +
        d077Keys + d078Keys + d079Keys + d080Keys + d081Keys + d082Keys + d083Keys + d084Keys + d085Keys)
        .sorted().also { capabilities ->
        check(capabilities.size == 499 && capabilities.distinct().size == 499) {
            "Canonical Apple binding capability count changed"
        }
    }
}

internal fun swiftSymbolGraphCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    output: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "swift-symbolgraph-extract", "-module-name", "CodexAgent", "-target", target,
    "-sdk", sdk.absolutePath, "-F", frameworkSearchPath.absolutePath,
    "-module-cache-path", moduleCache.absolutePath, "-minimum-access-level", "public",
    "-skip-synthesized-members", "-output-dir", output.absolutePath,
)

internal fun objectiveCExtractApiCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    header: File,
    output: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "clang", "-extract-api", "-x", "objective-c-header", "-target", target,
    "-isysroot", sdk.absolutePath, "-fmodules", "-fmodules-cache-path=${moduleCache.absolutePath}",
    "-F", frameworkSearchPath.absolutePath, header.absolutePath, "-o", output.absolutePath,
)

internal fun swiftConsumerAstCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    consumer: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "swiftc", "-typecheck", "-dump-ast", "-dump-ast-format", "json",
    "-target", target, "-sdk", sdk.absolutePath, "-F", frameworkSearchPath.absolutePath,
    "-module-cache-path", moduleCache.absolutePath, consumer.absolutePath,
)

internal fun objectiveCConsumerAstCommand(
    target: String,
    sdk: File,
    frameworkSearchPath: File,
    moduleCache: File,
    consumer: File,
): List<String> = listOf(
    "/usr/bin/xcrun", "clang", "-fsyntax-only", "-x", "objective-c", "-target", target,
    "-isysroot", sdk.absolutePath, "-fmodules", "-fmodules-cache-path=${moduleCache.absolutePath}",
    "-F", frameworkSearchPath.absolutePath, "-Xclang", "-ast-dump=json", consumer.absolutePath,
)

internal fun parseSwiftAppleBindingSurface(json: String): List<AppleCompilerSymbol> =
    parseAppleBindingSurface(json, "swift", expectedSwiftAppleBindingSymbols)

internal fun parseObjectiveCAppleBindingSurface(json: String): List<AppleCompilerSymbol> =
    parseAppleBindingSurface(json, "objective-c", expectedObjectiveCAppleBindingSymbols)

private fun parseAppleBindingSurface(
    json: String,
    language: String,
    expected: Map<String, ExpectedAppleCompilerSymbol>,
): List<AppleCompilerSymbol> {
    val root = appleJsonObject(json, "$language API")
    val rawSymbols = root.appleArray("symbols").map { element -> element.appleObject("$language symbol") }
        .filter { symbol -> symbol.appleObject("identifier").appleString("precise") in expected }
        .map(::normalizeAppleCompilerSymbol)
    fun matches(actual: AppleCompilerSymbol, contract: ExpectedAppleCompilerSymbol): Boolean =
        actual.kind == contract.kind && actual.path == contract.path && actual.title == contract.title &&
            actual.accessLevel == contract.access && actual.declaration == contract.declaration &&
            actual.typeIdentifiers == contract.typeIdentifiers && actual.parameters == contract.parameters &&
            actual.returns == contract.returns
    if (language == "swift") {
        val callbacks = d084ExpectedSwiftCallbackSymbols()
        d084SwiftAsyncMemberUsrs.forEach { precise ->
            val variants = rawSymbols.filter { it.precise == precise }
            check(variants.size == 2 && variants.all { it.interfaceLanguage == "swift" } &&
                variants.count { matches(it, expected.getValue(precise)) } == 1 &&
                variants.count { matches(it, callbacks.getValue(precise)) } == 1
            ) { "Swift D084 async/callback surface changed: $precise" }
        }
    }
    val symbols = rawSymbols.filter { actual ->
        language != "swift" || actual.precise !in d084SwiftAsyncMemberUsrs ||
            matches(actual, expected.getValue(actual.precise))
    }
    check(symbols.map(AppleCompilerSymbol::precise).toSet() == expected.keys && symbols.size == expected.size) {
        "$language Apple binding symbol set changed"
    }
    symbols.forEach { actual ->
        val contract = expected.getValue(actual.precise)
        check(actual.interfaceLanguage == language && matches(actual, contract)) {
            "$language Apple binding symbol changed: ${actual.precise}"
        }
    }
    val establishedMemberUsrs = listOf(
        appleCodexFailureMembers, appleConversationIdMembers, appleApprovalDecisionMembers,
        appleCollaborationModeMembers, appleMessageRoleMembers, appleInstallationScopeMembers,
        appleMcpEnvironmentSourceMembers,
    ).flatMap { it.values }
    check(establishedMemberUsrs.size == 16 && establishedMemberUsrs.distinct().size == 16) {
        "Established Apple member inventory changed"
    }
    val ordinaryMemberUsrs = d065OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(ordinaryMemberUsrs.size == 158 && ordinaryMemberUsrs.distinct().size == 158) {
        "D065 Apple member inventory changed"
    }
    val d073MemberUsrs = d073OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d073MemberUsrs.size == 81 && d073MemberUsrs.distinct().size == 81) {
        "D073 Apple member inventory changed"
    }
    val d074MemberUsrs = d074OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d074MemberUsrs.size == 83 && d074MemberUsrs.distinct().size == 83) {
        "D074 Apple member inventory changed"
    }
    val d075MemberUsrs = d075OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d075MemberUsrs.size == 9 && d075MemberUsrs.distinct().size == 9) {
        "D075 Apple member inventory changed"
    }
    val d076MemberUsrs = d076AuthorizationUrlCapabilities.map(AppleOrdinaryCapability::usr)
    check(d076MemberUsrs.size == 4 && d076MemberUsrs.distinct().size == 4) {
        "D076 Apple member inventory changed"
    }
    val d077MemberUsrs = d077OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d077MemberUsrs.size == 12 && d077MemberUsrs.distinct().size == 12) {
        "D077 Apple member inventory changed"
    }
    val d078MemberUsrs = d078OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d078MemberUsrs.size == 33 && d078MemberUsrs.distinct().size == 33) {
        "D078 Apple member inventory changed"
    }
    val d079MemberUsrs = d079OrdinaryCapabilities.map(AppleOrdinaryCapability::usr)
    check(d079MemberUsrs.size == 25 && d079MemberUsrs.distinct().size == 25) {
        "D079 Apple member inventory changed"
    }
    val d080MemberUsrs = d080Capabilities.map(AppleOrdinaryCapability::usr)
    check(d080MemberUsrs.size == 28 && d080MemberUsrs.distinct().size == 28) {
        "D080 Apple member inventory changed"
    }
    val d081MemberUsrs = d081Capabilities.map(AppleOrdinaryCapability::usr)
    check(d081MemberUsrs.size == 7 && d081MemberUsrs.distinct().size == 7) {
        "D081 Apple member inventory changed"
    }
    val d082MemberUsrs = d082ElicitationCapabilities.map(AppleOrdinaryCapability::usr)
    check(d082MemberUsrs.size == 7 && d082MemberUsrs.distinct().size == 7) {
        "D082 Apple member inventory changed"
    }
    val d083MemberUsrs = d083ProtocolCapabilities.map(AppleOrdinaryCapability::usr)
    check(d083MemberUsrs.size == 6 && d083MemberUsrs.distinct().size == 6) {
        "D083 Apple member inventory changed"
    }
    val d084MemberUsrs = d084Capabilities.map(AppleOrdinaryCapability::usr)
    check(d084MemberUsrs.size == 14 && d084MemberUsrs.distinct().size == 14) {
        "D084 Apple member inventory changed"
    }
    val d085MemberUsrs = d085Capabilities.map(AppleOrdinaryCapability::usr)
    check(d085MemberUsrs.size == 16 && d085MemberUsrs.distinct().size == 16) {
        "D085 Apple member inventory changed"
    }
    val selectedMemberUsrs = establishedMemberUsrs + ordinaryMemberUsrs + d073MemberUsrs + d074MemberUsrs +
        d075MemberUsrs + d076MemberUsrs + d077MemberUsrs + d078MemberUsrs + d079MemberUsrs +
        d080MemberUsrs + d081MemberUsrs + d082MemberUsrs + d083MemberUsrs + d084MemberUsrs + d085MemberUsrs
    check(selectedMemberUsrs.size == 499 && selectedMemberUsrs.distinct().size == 499) {
        "Selected Apple member inventory changed"
    }
    val memberOwners = selectedMemberUsrs.associateWith(::appleMemberOwnerUsr)
    val expectedMemberUsrs = expected.keys.intersect(selectedMemberUsrs.toSet())
    check(memberOwners.keys == expectedMemberUsrs) { "Expected Apple member ownership inventory changed" }
    val relationships = root.appleArray("relationships").map { it.appleObject("$language relationship") }
        .filter { relationship ->
            relationship.appleString("source") in memberOwners
        }.map { relationship ->
            Triple(
                relationship.appleString("kind"),
                relationship.appleString("source"),
                relationship.appleString("target"),
            )
        }
    val relationshipsBySource = relationships.groupBy { it.second }
    check(relationships.map { it.second }.toSet() == memberOwners.keys &&
        relationshipsBySource.all { (source, values) ->
            values.size == if (language == "swift" && source in d084SwiftAsyncMemberUsrs) 2 else 1
        } && relationships.all { (kind, source, target) ->
            kind == (if (language == "swift" && source in d083MemberUsrs) "requirementOf" else "memberOf") &&
                target == memberOwners.getValue(source)
        }) {
        "$language Apple binding ownership relationships changed"
    }
    return symbols.sortedBy(AppleCompilerSymbol::precise)
}

private fun normalizeAppleCompilerSymbol(symbol: JsonObject): AppleCompilerSymbol {
    val identifier = symbol.appleObject("identifier")
    val fragments = symbol.appleArray("declarationFragments").map { it.appleObject("declaration fragment") }
    val signature = symbol["functionSignature"] as? JsonObject
    val parameters = signature?.get("parameters")?.appleArray("function parameters")?.map { parameterElement ->
        val parameter = parameterElement.appleObject("function parameter")
        parameter.appleString("name") to fragmentsText(parameter.appleArray("declarationFragments"))
    }.orEmpty()
    val returns = signature?.get("returns")?.let { value -> fragmentsText(value.appleArray("function returns")) }
    return AppleCompilerSymbol(
        precise = identifier.appleString("precise"),
        interfaceLanguage = identifier.appleString("interfaceLanguage"),
        kind = symbol.appleObject("kind").appleString("identifier"),
        path = symbol.appleArray("pathComponents").map { it.appleString("path component") },
        title = symbol.appleObject("names").appleString("title"),
        accessLevel = symbol.appleString("accessLevel"),
        declaration = fragmentsText(JsonArray(fragments)),
        typeIdentifiers = fragments.filter { it.appleString("kind") == "typeIdentifier" }
            .map { it.appleString("preciseIdentifier") },
        parameters = parameters,
        returns = returns,
    )
}

private fun d082ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptContent:",
        "declref_expr", "accept", null,
        "\$sySo010CodexAgentB19ElicitationResponseCSDySSSo0abB9FormValue_pG_tcSo0abbC0CcD",
        emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptsResponse:",
        "declref_expr", "accepts", null,
        "\$sySbSo010CodexAgentB19ElicitationResponseC_tcSo0abbC0CcD", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)initialValues",
        "declref_expr", "initialValues", null,
        "\$sySDySSSo010CodexAgentB9FormValue_pGycSo0abB11ElicitationCcD", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)validateContent:",
        "declref_expr", "validate", null,
        "\$sySo010CodexAgentB21ElicitationValidationCSDySSSo0abB9FormValue_pG_tcSo0abbC0CcD",
        emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentFormField")}(im)acceptsValue:",
        "declref_expr", "accepts", null,
        "\$sySbSo010CodexAgentB9FormValue_pSg_tcSo0abbC5FieldCcD", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)cancel",
        "declref_expr", "cancel", null,
        "\$sySo010CodexAgentB19ElicitationResponseCycSo0abbcD9CompanionCcD", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)decline",
        "declref_expr", "decline", null,
        "\$sySo010CodexAgentB19ElicitationResponseCycSo0abbcD9CompanionCcD", emptyList(),
    ),
)

private fun d082ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptContent:",
        "ObjCMessageExpr", "acceptContent:", "CodexAgentAgentElicitation *",
        "CodexAgentAgentElicitationResponse *",
        listOf("NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *"),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)acceptsResponse:",
        "ObjCMessageExpr", "acceptsResponse:", "CodexAgentAgentElicitation *", "BOOL",
        listOf("CodexAgentAgentElicitationResponse *"),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)initialValues",
        "ObjCMessageExpr", "initialValues", "CodexAgentAgentElicitation *",
        "NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitation")}(im)validateContent:",
        "ObjCMessageExpr", "validateContent:", "CodexAgentAgentElicitation *",
        "CodexAgentAgentElicitationValidation *",
        listOf("NSDictionary<NSString *,id<CodexAgentAgentFormValue>> *"),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentFormField")}(im)acceptsValue:",
        "ObjCMessageExpr", "acceptsValue:", "CodexAgentAgentFormField *", "BOOL",
        listOf("id<CodexAgentAgentFormValue>"),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)cancel",
        "ObjCMessageExpr", "cancel", "CodexAgentAgentElicitationResponseCompanion *",
        "CodexAgentAgentElicitationResponse *", emptyList(),
    ),
    AppleCompilerReference(
        "${appleOwnerUsr("CodexAgentAgentElicitationResponseCompanion")}(im)decline",
        "ObjCMessageExpr", "decline", "CodexAgentAgentElicitationResponseCompanion *",
        "CodexAgentAgentElicitationResponse *", emptyList(),
    ),
)

private fun d083ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentIntegration(py)displayName",
        "member_ref_expr", "displayName", null, "\$sSSD", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentIntegration(py)id",
        "member_ref_expr", "id", null, "\$sSSD", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentInvocation(py)key",
        "member_ref_expr", "key", null, "\$sSSD", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentInvocation(py)name",
        "member_ref_expr", "name", null, "\$sSSD", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId",
        "member_ref_expr", "conversationId", null, "\$sSo24CodexAgentConversationIdCD", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId",
        "member_ref_expr", "requestId", null, "\$sSSD", emptyList(),
    ),
)

private fun d083ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = listOf(
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentIntegration(py)displayName", "ObjCPropertyRefExpr", "displayName",
        "id<CodexAgentAgentIntegration>", "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentIntegration(py)id", "ObjCPropertyRefExpr", "id",
        "id<CodexAgentAgentIntegration>", "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentInvocation(py)key", "ObjCPropertyRefExpr", "key",
        "id<CodexAgentAgentInvocation>", "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentInvocation(py)name", "ObjCPropertyRefExpr", "name",
        "id<CodexAgentAgentInvocation>", "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)conversationId", "ObjCPropertyRefExpr",
        "conversationId", "id<CodexAgentAgentPendingInteraction>", "<pseudo-object type>", emptyList(),
    ),
    AppleCompilerReference(
        "c:objc(pl)CodexAgentAgentPendingInteraction(py)requestId", "ObjCPropertyRefExpr", "requestId",
        "id<CodexAgentAgentPendingInteraction>", "<pseudo-object type>", emptyList(),
    ),
)

private fun d084ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d084AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference(
            "$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList(),
        ))
        owner.properties.forEach { property ->
            add(AppleCompilerReference(
                "$ownerUsr(py)${property.appleName}", "member_ref_expr", property.appleName,
                null, property.type.swiftAst, emptyList(),
            ))
        }
    }
    val hostUsr = appleOwnerUsr("CodexAgentCodexHost")
    add(AppleCompilerReference(
        "$hostUsr(im)closeWithCompletionHandler:", "declref_expr", "close", null,
        "\$syyyYaKcSo010CodexAgentA4HostCcD", emptyList(),
    ))
    add(AppleCompilerReference(
        "$hostUsr(im)selectWorkspaceSelection:completionHandler:", "declref_expr",
        "selectWorkspace", null, "\$syySo010CodexAgentA18WorkspaceSelection_p_tYaKcSo0abA4HostCcD",
        emptyList(),
    ))
    add(AppleCompilerReference(
        "$hostUsr(im)startWithCompletionHandler:", "declref_expr", "start", null,
        "\$syyyYaKcSo010CodexAgentA4HostCcD", emptyList(),
    ))
    add(AppleCompilerReference(
        "$hostUsr(py)lifecycleState", "member_ref_expr", "lifecycleState", null,
        d084HostStateFlowType.swiftAst, emptyList(),
    ))
}

private fun d084ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d084AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference(
            "$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr", owner.objectiveCSelector,
            owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map(AppleOrdinaryParameter::objectiveCAst),
        ))
        owner.properties.forEach { property ->
            add(AppleCompilerReference(
                "$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr", property.appleName,
                "${owner.objectiveCName} *", "<pseudo-object type>", emptyList(),
            ))
        }
    }
    val hostUsr = appleOwnerUsr("CodexAgentCodexHost")
    listOf("closeWithCompletionHandler:", "startWithCompletionHandler:").forEach { selector ->
        add(AppleCompilerReference(
            "$hostUsr(im)$selector", "ObjCMessageExpr", selector, "CodexAgentCodexHost *", "void",
            listOf("void (^)(NSError *)"),
        ))
    }
    add(AppleCompilerReference(
        "$hostUsr(im)selectWorkspaceSelection:completionHandler:", "ObjCMessageExpr",
        "selectWorkspaceSelection:completionHandler:", "CodexAgentCodexHost *", "void",
        listOf("id<CodexAgentCodexWorkspaceSelection>", "void (^)(NSError *)"),
    ))
    add(AppleCompilerReference(
        "$hostUsr(py)lifecycleState", "ObjCPropertyRefExpr", "lifecycleState",
        "CodexAgentCodexHost *", "<pseudo-object type>", emptyList(),
    ))
}

private fun d085ExpectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d085PropertyOwners.forEach { (owner, properties) ->
        val ownerUsr = appleOwnerUsr("CodexAgent$owner")
        properties.forEach { property ->
            add(AppleCompilerReference(
                "$ownerUsr(py)${property.appleName}", "member_ref_expr", property.appleName,
                null, property.type.swiftAst, emptyList(),
            ))
        }
    }
}

private fun d085ExpectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    d085PropertyOwners.forEach { (owner, properties) ->
        val objectiveCName = "CodexAgent$owner"
        val ownerUsr = appleOwnerUsr(objectiveCName)
        properties.forEach { property ->
            add(AppleCompilerReference(
                "$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr", property.appleName,
                "$objectiveCName *", "<pseudo-object type>", emptyList(),
            ))
        }
    }
}

private fun expectedSwiftAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    add(AppleCompilerReference(
        appleCodexFailureMembers.getValue("constructor:<init>"), "declref_expr", "init", null,
        "\$sySo010CodexAgentA7FailureCSS_SSSbtcABmcD", emptyList(),
    ))
    add(AppleCompilerReference(appleCodexFailureMembers.getValue("property:code"), "member_ref_expr", "code",
        null, appleString.swiftAst, emptyList()))
    add(AppleCompilerReference(appleCodexFailureMembers.getValue("property:isRecoverable"), "member_ref_expr",
        "isRecoverable", null, appleBoolean.swiftAst, emptyList()))
    add(AppleCompilerReference(appleCodexFailureMembers.getValue("property:message"), "member_ref_expr", "message",
        null, appleString.swiftAst, emptyList()))
    add(AppleCompilerReference(
        appleConversationIdMembers.getValue("conversation-id:constructor:<init>"), "declref_expr", "init", null,
        "\$sySo24CodexAgentConversationIdCSS_tcABmcD", emptyList(),
    ))
    add(AppleCompilerReference(appleConversationIdMembers.getValue("conversation-id:property:value"),
        "member_ref_expr", "value", null, appleString.swiftAst, emptyList()))
    listOf(
        appleApprovalDecisionMembers to "\$sSo010CodexAgentB16ApprovalDecisionCD",
        appleCollaborationModeMembers to "\$sSo010CodexAgentB17CollaborationModeCD",
        appleMessageRoleMembers to "\$sSo010CodexAgentB11MessageRoleCD",
        appleInstallationScopeMembers to "\$sSo010CodexAgentB17InstallationScopeCD",
        appleMcpEnvironmentSourceMembers to "\$sSo010CodexAgentB20McpEnvironmentSourceCD",
    ).forEach { (members, swiftAst) ->
        members.forEach { (_, usr) ->
            add(AppleCompilerReference(usr, "member_ref_expr", usr.substringAfter("(cpy)"), null,
                swiftAst, emptyList()))
        }
    }
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
    d073AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d074AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d075AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d077AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d078AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d079AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    d080AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "declref_expr", "init", null,
            owner.swiftConstructorAst, emptyList()))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "member_ref_expr",
                property.appleName, null, property.type.swiftAst, emptyList()))
        }
    }
    add(AppleCompilerReference(
        "c:objc(cs)CodexAgentAgentInteractionState(im)isResolvingInteraction:",
        "declref_expr", "isResolving", null,
        "\$sySbSo010CodexAgentB18PendingInteraction_p_tcSo0abbD5StateCcD", emptyList(),
    ))
    add(AppleCompilerReference(
        "c:objc(cs)CodexAgentAgentInteractionState(im)pendingForConversationId:",
        "declref_expr", "pendingFor", null,
        "\$sySaySo010CodexAgentB18PendingInteraction_pGSo0aB14ConversationIdC_tcSo0abbD5StateCcD",
        emptyList(),
    ))
    d081AppleObjects.forEach { (_, objectiveCName, swiftAst) ->
        add(AppleCompilerReference(
            "${appleOwnerUsr(objectiveCName)}(cpy)shared", "member_ref_expr", "shared", null,
            swiftAst, emptyList(),
        ))
    }
    addAll(d082ExpectedSwiftAppleBindingReferences())
    addAll(d083ExpectedSwiftAppleBindingReferences())
    addAll(d084ExpectedSwiftAppleBindingReferences())
    addAll(d085ExpectedSwiftAppleBindingReferences())
    add(AppleCompilerReference(
        "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)chatGptValue:",
        "declref_expr", "chatGpt", null,
        "\$sySo010CodexAgentA16AuthorizationUrlCSS_tcSo0abacD9CompanionCcD", emptyList(),
    ))
    add(AppleCompilerReference(
        "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)externalValue:",
        "declref_expr", "external", null,
        "\$sySo010CodexAgentA16AuthorizationUrlCSS_tcSo0abacD9CompanionCcD", emptyList(),
    ))
    add(AppleCompilerReference(
        "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)value", "member_ref_expr", "value", null,
        appleString.swiftAst, emptyList(),
    ))
    add(AppleCompilerReference(
        "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)purpose", "member_ref_expr", "purpose", null,
        "\$sSo010CodexAgentA20AuthorizationPurposeCD", emptyList(),
    ))
}.sortedBy(AppleCompilerReference::precise)

private fun expectedObjectiveCAppleBindingReferences(): List<AppleCompilerReference> = buildList {
    add(AppleCompilerReference(
        appleCodexFailureMembers.getValue("constructor:<init>"), "ObjCMessageExpr",
        "initWithCode:message:isRecoverable:", "CodexAgentCodexFailure", "CodexAgentCodexFailure *",
        listOf("NSString *", "NSString *", "BOOL"),
    ))
    listOf("code", "isRecoverable", "message").forEach { name ->
        add(AppleCompilerReference(appleCodexFailureMembers.getValue("property:$name"), "ObjCPropertyRefExpr",
            name, "CodexAgentCodexFailure *", "<pseudo-object type>", emptyList()))
    }
    add(AppleCompilerReference(
        appleConversationIdMembers.getValue("conversation-id:constructor:<init>"), "ObjCMessageExpr",
        "initWithValue:", "CodexAgentConversationId", "CodexAgentConversationId *", listOf("NSString *"),
    ))
    add(AppleCompilerReference(appleConversationIdMembers.getValue("conversation-id:property:value"),
        "ObjCPropertyRefExpr", "value", "CodexAgentConversationId *", "<pseudo-object type>", emptyList()))
    listOf(
        appleApprovalDecisionMembers to "CodexAgentAgentApprovalDecision",
        appleCollaborationModeMembers to "CodexAgentAgentCollaborationMode",
        appleMessageRoleMembers to "CodexAgentAgentMessageRole",
        appleInstallationScopeMembers to "CodexAgentAgentInstallationScope",
        appleMcpEnvironmentSourceMembers to "CodexAgentAgentMcpEnvironmentSource",
    ).forEach { (members, objectiveCName) ->
        members.forEach { (_, usr) ->
            val name = usr.substringAfter("(cpy)")
            add(AppleCompilerReference(usr, "ObjCMessageExpr", name, objectiveCName,
                "$objectiveCName * _Nonnull", emptyList()))
        }
    }
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
    d079AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
    d080AppleValues.forEach { owner ->
        val ownerUsr = appleOwnerUsr(owner.objectiveCName)
        add(AppleCompilerReference("$ownerUsr(im)${owner.objectiveCSelector}", "ObjCMessageExpr",
            owner.objectiveCSelector, owner.objectiveCName, "${owner.objectiveCName} *",
            owner.parameters.map { it.objectiveCAst }))
        owner.properties.forEach { property ->
            add(AppleCompilerReference("$ownerUsr(py)${property.appleName}", "ObjCPropertyRefExpr",
                property.appleName, "${owner.objectiveCName} *", "<pseudo-object type>", emptyList()))
        }
    }
    add(AppleCompilerReference(
        "c:objc(cs)CodexAgentAgentInteractionState(im)isResolvingInteraction:",
        "ObjCMessageExpr", "isResolvingInteraction:", "CodexAgentAgentInteractionState *", "BOOL",
        listOf("id<CodexAgentAgentPendingInteraction> _Nonnull"),
    ))
    add(AppleCompilerReference(
        "c:objc(cs)CodexAgentAgentInteractionState(im)pendingForConversationId:",
        "ObjCMessageExpr", "pendingForConversationId:", "CodexAgentAgentInteractionState *",
        "NSArray<id<CodexAgentAgentPendingInteraction>> *", listOf("CodexAgentConversationId *"),
    ))
    d081AppleObjects.forEach { (_, objectiveCName) ->
        add(AppleCompilerReference(
            "${appleOwnerUsr(objectiveCName)}(cpy)shared", "ObjCMessageExpr", "shared", objectiveCName,
            "$objectiveCName * _Nonnull", emptyList(),
        ))
    }
    addAll(d082ExpectedObjectiveCAppleBindingReferences())
    addAll(d083ExpectedObjectiveCAppleBindingReferences())
    addAll(d084ExpectedObjectiveCAppleBindingReferences())
    addAll(d085ExpectedObjectiveCAppleBindingReferences())
    listOf("chatGptValue:", "externalValue:").forEach { selector ->
        add(AppleCompilerReference(
            "$APPLE_AUTHORIZATION_URL_COMPANION_OWNER_USR(im)$selector", "ObjCMessageExpr", selector,
            "CodexAgentCodexAuthorizationUrlCompanion *", "CodexAgentCodexAuthorizationUrl *",
            listOf("NSString *"),
        ))
    }
    listOf("value", "purpose").forEach { name ->
        add(AppleCompilerReference(
            "$APPLE_AUTHORIZATION_URL_OWNER_USR(py)$name", "ObjCPropertyRefExpr", name,
            "CodexAgentCodexAuthorizationUrl *", "<pseudo-object type>", emptyList(),
        ))
    }
}.sortedBy(AppleCompilerReference::precise)

internal fun parseSwiftAppleBindingReferences(json: String): List<AppleCompilerReference> {
    val references = appleJsonObject(json, "Swift consumer AST").walkAppleObjects().mapNotNull { node ->
        val declaration = node["decl"] as? JsonObject ?: return@mapNotNull null
        val precise = declaration.appleStringOrNull("decl_usr") ?: return@mapNotNull null
        if (precise !in appleBindingMembers.values) return@mapNotNull null
        AppleCompilerReference(
            precise, node.appleString("_kind"), declaration.appleString("base_name"), null,
            node.appleString("type"), emptyList(),
        )
    }.toList().groupBy(AppleCompilerReference::precise).map { (precise, values) ->
        check(values.distinct().size == 1) { "Swift reference is ambiguous: $precise" }
        values.first()
    }.sortedBy(AppleCompilerReference::precise)
    check(references == expectedSwiftAppleBindingReferences()) { "Swift Apple binding references changed" }
    return references
}

internal fun parseObjectiveCAppleBindingReferences(json: String): List<AppleCompilerReference> {
    val nodes = appleJsonObject(json, "Objective-C consumer AST").walkAppleObjects().toList()
    val expected = expectedObjectiveCAppleBindingReferences()
    val expectedClassMessages = expected.filter { it.kind == "ObjCMessageExpr" && !it.name.startsWith("init") }
        .associateBy { it.receiverType to it.name }
    val expectedConstructors = expected.filter { it.kind == "ObjCMessageExpr" && it.name.startsWith("init") }
        .associateBy { it.receiverType to it.name }
    val finiteInstanceMethodUsrs =
        (d076AuthorizationUrlCapabilities + d080InteractionMethods + d082ElicitationCapabilities +
            d084ExceptionalHostCapabilities.filter { "|kind=function|" in it.canonicalKey })
        .mapTo(mutableSetOf(), AppleOrdinaryCapability::usr)
    val expectedFiniteInstanceMessages = expected.filter {
        it.kind == "ObjCMessageExpr" && it.precise in finiteInstanceMethodUsrs
    }.associateBy { it.receiverType to it.name }
    val expectedProperties = expected.filter { it.kind == "ObjCPropertyRefExpr" }
        .associateBy { it.receiverType to it.name }

    val references = nodes.mapNotNull { node ->
        when (node.appleStringOrNull("kind")) {
            "ObjCMessageExpr" -> {
                val selector = node.appleStringOrNull("selector") ?: return@mapNotNull null
                val classType = (node["classType"] as? JsonObject)?.appleStringOrNull("qualType")
                val inner = node["inner"] as? JsonArray
                val receiver = if (classType != null) {
                    expectedClassMessages[classType to selector]
                } else {
                    val receiverNode = inner?.firstOrNull() as? JsonObject
                    val constructorReceiverType = receiverNode
                        ?.get("classType")?.let { it as? JsonObject }?.appleStringOrNull("qualType")
                    val instanceReceiverType = (receiverNode?.get("type") as? JsonObject)
                        ?.appleStringOrNull("qualType")
                    expectedConstructors[constructorReceiverType to selector]
                        ?: expectedFiniteInstanceMessages[instanceReceiverType to selector]
                } ?: return@mapNotNull null
                AppleCompilerReference(
                    receiver.precise, "ObjCMessageExpr", selector, receiver.receiverType,
                    node.appleObject("type").appleString("qualType"),
                    if (selector.startsWith("init") || receiver.precise in finiteInstanceMethodUsrs) {
                        requireNotNull(inner).drop(1).map { argument ->
                            argument.appleObject("Objective-C instance argument")
                                .appleObject("type").appleString("qualType")
                        }
                    } else {
                        emptyList()
                    },
                )
            }
            "ObjCPropertyRefExpr" -> {
                val name = (node["property"] as? JsonObject)?.appleStringOrNull("name")
                    ?: return@mapNotNull null
                val receiverType = (node["inner"] as? JsonArray)?.firstOrNull()
                    ?.appleObject("Objective-C property receiver")
                    ?.appleObject("type")?.appleString("qualType")
                    ?: return@mapNotNull null
                val expectedReference = expectedProperties[receiverType to name] ?: return@mapNotNull null
                check(node.appleBoolean("isMessagingGetter")) {
                    "Objective-C property is not a getter: $receiverType.$name"
                }
                AppleCompilerReference(
                    expectedReference.precise, "ObjCPropertyRefExpr", name, receiverType,
                    node.appleObject("type").appleString("qualType"), emptyList(),
                )
            }
            else -> null
        }
    }.groupBy(AppleCompilerReference::precise).map { (precise, values) ->
        check(values.distinct().size == 1) { "Objective-C reference is ambiguous: $precise" }
        values.first()
    }.sortedBy(AppleCompilerReference::precise)
    check(references == expected) {
        "Objective-C Apple binding references changed; " +
            "missing=${expected.filterNot(references::contains)}; " +
            "unexpected=${references.filterNot(expected::contains)}"
    }
    return references
}
private fun JsonObject.walkAppleObjects(): Sequence<JsonObject> = sequence {
    yield(this@walkAppleObjects)
    for (value in values) yieldAll(value.walkAppleObjects())
}

private fun JsonElement.walkAppleObjects(): Sequence<JsonObject> = when (this) {
    is JsonObject -> walkAppleObjects()
    is JsonArray -> asSequence().flatMap { it.walkAppleObjects() }
    else -> emptySequence()
}

private fun fragmentsText(fragments: JsonArray): String = fragments.joinToString("") { fragment ->
    fragment.appleObject("declaration fragment").appleString("spelling")
}

private fun appleJsonObject(json: String, label: String): JsonObject =
    releaseJson.parseToJsonElement(json) as? JsonObject ?: error("$label is not a JSON object")

private fun JsonElement.appleObject(label: String): JsonObject = this as? JsonObject
    ?: error("$label is not a JSON object")

private fun JsonElement.appleArray(label: String): JsonArray = this as? JsonArray
    ?: error("$label is not a JSON array")

private fun JsonElement.appleString(label: String): String {
    val primitive = this as? JsonPrimitive ?: error("$label is not a string")
    check(primitive.isString) { "$label is not a string" }
    return primitive.content
}

private fun JsonObject.appleObject(name: String): JsonObject = this[name]?.appleObject(name)
    ?: error("Missing JSON object: $name")
private fun JsonObject.appleArray(name: String): JsonArray = this[name]?.appleArray(name)
    ?: error("Missing JSON array: $name")
private fun JsonObject.appleString(name: String): String = this[name]?.appleString(name)
    ?: error("Missing JSON string: $name")
private fun JsonObject.appleStringOrNull(name: String): String? = (this[name] as? JsonPrimitive)
    ?.takeIf { it.isString }?.contentOrNull
private fun JsonObject.appleBoolean(name: String): Boolean {
    val primitive = this[name] as? JsonPrimitive ?: error("$name is not a boolean")
    check(!primitive.isString && primitive.content in setOf("true", "false")) { "$name is not a boolean" }
    return primitive.content == "true"
}

private fun AppleCompilerSymbol.toJson(): JsonObject = buildJsonObject {
    put("precise", JsonPrimitive(precise)); put("interfaceLanguage", JsonPrimitive(interfaceLanguage))
    put("kind", JsonPrimitive(kind)); put("path", buildJsonArray { path.forEach { add(JsonPrimitive(it)) } })
    put("title", JsonPrimitive(title)); put("accessLevel", JsonPrimitive(accessLevel))
    put("declaration", JsonPrimitive(declaration))
    put("typeIdentifiers", buildJsonArray { typeIdentifiers.forEach { add(JsonPrimitive(it)) } })
    put("parameters", buildJsonArray { parameters.forEach { (name, declaration) -> add(buildJsonObject {
        put("name", JsonPrimitive(name)); put("declaration", JsonPrimitive(declaration))
    }) } })
    put("returns", returns?.let(::JsonPrimitive) ?: kotlinx.serialization.json.JsonNull)
}

private fun AppleCompilerReference.toJson(): JsonObject = buildJsonObject {
    put("precise", JsonPrimitive(precise)); put("kind", JsonPrimitive(kind)); put("name", JsonPrimitive(name))
    put("receiverType", receiverType?.let(::JsonPrimitive) ?: kotlinx.serialization.json.JsonNull)
    put("valueType", JsonPrimitive(valueType))
    put("argumentTypes", buildJsonArray { argumentTypes.forEach { add(JsonPrimitive(it)) } })
}

internal fun appleCompilerJsonDigest(value: JsonElement): String {
    val bytes = (releaseJson.encodeToString(JsonElement.serializer(), value) + "\n").encodeToByteArray()
    return MessageDigest.getInstance("SHA-256").digest(bytes)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}

private fun symbolsJson(symbols: List<AppleCompilerSymbol>) = buildJsonArray { symbols.forEach { add(it.toJson()) } }
private fun referencesJson(references: List<AppleCompilerReference>) =
    buildJsonArray { references.forEach { add(it.toJson()) } }

@DisableCachingByDefault(because = "Invokes the installed, pinned Apple compiler toolchain")
abstract class AppleCompilerEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val xcframeworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalApiReport: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val canonicalCoverageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val swiftConsumer: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val objectiveCConsumer: RegularFileProperty
    @get:Input abstract val minimumIosVersion: Property<String>
    @get:Input abstract val expectedXcodeVersion: Property<String>
    @get:Input abstract val expectedXcodeBuild: Property<String>
    @get:Input abstract val expectedSwiftVersion: Property<String>
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = evidenceFile.get().asFile
        Files.deleteIfExists(output.toPath())
        check(minimumIosVersion.get() == "15.0") { "Apple compiler evidence target contract changed" }
        val canonical = readCrossLanguageCanonicalApiEvidence(
            canonicalApiReport.get().asFile, canonicalCoverageReceipt.get().asFile,
        )
        val capabilities = appleBindingCapabilityKeys(canonical.memberKeys)
        val xcodeOutput = processes.captureReleaseProcess(listOf("/usr/bin/xcodebuild", "-version"))
        val swiftOutput = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "swift", "--version"))
        verifyAppleToolchainOutput(
            xcodeOutput, swiftOutput, expectedXcodeVersion.get(), expectedXcodeBuild.get(), expectedSwiftVersion.get(),
        )
        val clangVersion = processes.captureReleaseProcess(listOf("/usr/bin/xcrun", "clang", "--version"))
            .lineSequence().firstOrNull()?.also { check(it.startsWith("Apple clang version ")) }
            ?: error("Apple Clang version is missing")
        val xcframework = xcframeworkDirectory.get().asFile
        val work = temporaryDir.resolve("compiler-evidence").also { deleteReleaseTree(it); Files.createDirectories(it.toPath()) }
        val slices = appleCompilerSlices.map { specification -> inspectSlice(specification, xcframework, work) }
        check(slices.map(InspectedAppleCompilerSlice::swiftSurface).distinct().size == 1) {
            "Swift Apple binding device and simulator surfaces differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::objectiveCSurface).distinct().size == 1) {
            "Objective-C Apple binding device and simulator surfaces differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::swiftReferences).distinct().size == 1) {
            "Swift Apple binding device and simulator references differ"
        }
        check(slices.map(InspectedAppleCompilerSlice::objectiveCReferences).distinct().size == 1) {
            "Objective-C Apple binding device and simulator references differ"
        }
        val swiftSurface = slices.first().swiftSurface
        val objectiveCSurface = slices.first().objectiveCSurface
        val swiftReferences = slices.first().swiftReferences
        val objectiveCReferences = slices.first().objectiveCReferences
        val swiftSurfaceJson = symbolsJson(swiftSurface)
        val objectiveCSurfaceJson = symbolsJson(objectiveCSurface)
        val swiftReferencesJson = referencesJson(swiftReferences)
        val objectiveCReferencesJson = referencesJson(objectiveCReferences)
        output.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1)); put("protocol", JsonPrimitive(APPLE_COMPILER_EVIDENCE_PROTOCOL))
            put("result", JsonPrimitive("observed")); put("moduleName", JsonPrimitive("CodexAgent"))
            put("canonical", buildJsonObject {
                put("apiReportSha256", JsonPrimitive(canonical.canonical.apiReportSha256))
                put("coverageReceiptSha256", JsonPrimitive(canonical.canonical.coverageReceiptSha256))
                put("nativeTargetSha256", JsonPrimitive(canonical.targetSha256.getValue("native")))
                put("capabilities", buildJsonArray { capabilities.forEach { add(JsonPrimitive(it)) } })
            })
            put("toolchain", buildJsonObject {
                put("xcodeVersion", JsonPrimitive(expectedXcodeVersion.get()))
                put("xcodeBuild", JsonPrimitive(expectedXcodeBuild.get()))
                put("swiftVersion", JsonPrimitive(expectedSwiftVersion.get()))
                put("clangVersion", JsonPrimitive(clangVersion))
            })
            put("artifacts", buildJsonObject {
                put("xcframeworkSha256", JsonPrimitive(xcframework.crossLanguageTreeDigest()))
                put("swiftConsumerSha256", JsonPrimitive(swiftConsumer.get().asFile.releaseDigest()))
                put("objectiveCConsumerSha256", JsonPrimitive(objectiveCConsumer.get().asFile.releaseDigest()))
            })
            put("targets", buildJsonArray { slices.forEach { slice -> add(slice.toJson()) } })
            put("surface", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftSurfaceJson)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCSurfaceJson)))
                put("swift", swiftSurfaceJson); put("objectiveC", objectiveCSurfaceJson)
            })
            put("references", buildJsonObject {
                put("swiftSha256", JsonPrimitive(appleCompilerJsonDigest(swiftReferencesJson)))
                put("objectiveCSha256", JsonPrimitive(appleCompilerJsonDigest(objectiveCReferencesJson)))
                put("swift", swiftReferencesJson); put("objectiveC", objectiveCReferencesJson)
            })
            put("claims", buildJsonArray { capabilities.forEach { capability ->
                val shape = appleBindingShape(capability)
                val precise = appleBindingMembers.getValue(shape)
                add(buildJsonObject {
                    put("canonicalKey", JsonPrimitive(capability))
                    put("swiftUsr", JsonPrimitive(precise)); put("objectiveCUsr", JsonPrimitive(precise))
                })
            } })
        })
    }

    private fun inspectSlice(specification: AppleCompilerSlice, xcframework: File, work: File): InspectedAppleCompilerSlice {
        val frameworkSearchPath = xcframework.resolve(specification.name)
        val framework = frameworkSearchPath.resolve("CodexAgent.framework")
        val header = framework.resolve("Headers/CodexAgent.h")
        val moduleMap = framework.resolve("Modules/module.modulemap")
        val binary = framework.resolve("CodexAgent")
        listOf(header, moduleMap, binary).forEach { file ->
            check(file.isFile && file.length() > 0L && !Files.isSymbolicLink(file.toPath())) {
                "Apple compiler evidence framework member is missing or unsafe: $file"
            }
        }
        val sdkPath = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", specification.sdkName, "--show-sdk-path"),
        ).trim().let(::File).also { check(it.isDirectory) { "Apple SDK is missing: $it" } }
        val sdkVersion = processes.captureReleaseProcess(
            listOf("/usr/bin/xcrun", "--sdk", specification.sdkName, "--show-sdk-version"),
        ).trim().also { check(it.matches(Regex("[0-9]+(?:\\.[0-9]+)*"))) { "Apple SDK version is invalid" } }
        val sliceWork = work.resolve(specification.name).also { Files.createDirectories(it.toPath()) }
        val swiftOutput = sliceWork.resolve("swift-symbols").also { Files.createDirectories(it.toPath()) }
        val swiftCache = sliceWork.resolve("swift-module-cache").also { Files.createDirectories(it.toPath()) }
        processes.captureReleaseProcess(swiftSymbolGraphCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, swiftCache, swiftOutput,
        ))
        val swiftSymbolGraph = swiftOutput.resolve("CodexAgent.symbols.json")
        check(swiftSymbolGraph.isFile && swiftSymbolGraph.length() > 0L) { "Swift symbol graph was not produced" }
        val objectiveCExtractApi = sliceWork.resolve("CodexAgent.objc.symbols.json")
        val clangCache = sliceWork.resolve("clang-module-cache").also { Files.createDirectories(it.toPath()) }
        processes.captureReleaseProcess(objectiveCExtractApiCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, clangCache, header, objectiveCExtractApi,
        ))
        check(objectiveCExtractApi.isFile && objectiveCExtractApi.length() > 0L) {
            "Objective-C extract-api output was not produced"
        }
        val swiftConsumerCache = sliceWork.resolve("swift-consumer-cache")
            .also { Files.createDirectories(it.toPath()) }
        val objectiveCConsumerCache = sliceWork.resolve("objective-c-consumer-cache")
            .also { Files.createDirectories(it.toPath()) }
        val swiftAst = processes.captureReleaseProcess(swiftConsumerAstCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, swiftConsumerCache,
            swiftConsumer.get().asFile,
        ))
        val objectiveCAst = processes.captureReleaseProcess(objectiveCConsumerAstCommand(
            specification.targetTriple, sdkPath, frameworkSearchPath, objectiveCConsumerCache,
            objectiveCConsumer.get().asFile,
        ))
        return InspectedAppleCompilerSlice(
            specification, sdkVersion, framework,
            parseSwiftAppleBindingSurface(swiftSymbolGraph.readText()),
            parseObjectiveCAppleBindingSurface(objectiveCExtractApi.readText()),
            parseSwiftAppleBindingReferences(swiftAst),
            parseObjectiveCAppleBindingReferences(objectiveCAst),
        )
    }
}

private fun InspectedAppleCompilerSlice.toJson(): JsonObject = buildJsonObject {
    put("name", JsonPrimitive(specification.name)); put("sdk", JsonPrimitive(specification.sdkName))
    put("sdkVersion", JsonPrimitive(sdkVersion)); put("targetTriple", JsonPrimitive(specification.targetTriple))
    put("frameworkSha256", JsonPrimitive(framework.crossLanguageTreeDigest()))
    put("binarySha256", JsonPrimitive(framework.resolve("CodexAgent").releaseDigest()))
    put("headerSha256", JsonPrimitive(framework.resolve("Headers/CodexAgent.h").releaseDigest()))
    put("moduleMapSha256", JsonPrimitive(framework.resolve("Modules/module.modulemap").releaseDigest()))
}
