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

private fun appleMemberOwnerUsr(memberUsr: String): String {
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
) + d065ExpectedSwiftSymbols() + d073ExpectedSwiftSymbols() + d074ExpectedSwiftSymbols()

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
) + d065ExpectedObjectiveCSymbols() + d073ExpectedObjectiveCSymbols() + d074ExpectedObjectiveCSymbols()

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
        !it.startsWith("d065:") && !it.startsWith("d073:") && !it.startsWith("d074:")
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
    return (byShape.values.map { it.single() } + d065Keys + d073Keys + d074Keys).sorted().also { capabilities ->
        check(capabilities.size == 338 && capabilities.distinct().size == 338) {
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
    val symbols = root.appleArray("symbols").map { element -> element.appleObject("$language symbol") }
        .filter { symbol -> symbol.appleObject("identifier").appleString("precise") in expected }
        .map(::normalizeAppleCompilerSymbol)
    check(symbols.map(AppleCompilerSymbol::precise).toSet() == expected.keys && symbols.size == expected.size) {
        "$language Apple binding symbol set changed"
    }
    symbols.forEach { actual ->
        val contract = expected.getValue(actual.precise)
        check(actual.interfaceLanguage == language && actual.kind == contract.kind && actual.path == contract.path &&
            actual.title == contract.title && actual.accessLevel == contract.access &&
            actual.declaration == contract.declaration && actual.typeIdentifiers == contract.typeIdentifiers &&
            actual.parameters == contract.parameters && actual.returns == contract.returns) {
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
    val selectedMemberUsrs = establishedMemberUsrs + ordinaryMemberUsrs + d073MemberUsrs + d074MemberUsrs
    check(selectedMemberUsrs.size == 338 && selectedMemberUsrs.distinct().size == 338) {
        "Selected Apple member inventory changed"
    }
    val memberOwners = selectedMemberUsrs.associateWith(::appleMemberOwnerUsr)
    val expectedMemberUsrs = expected.filterValues { it.path.size > 1 }.keys
    check(memberOwners.keys == expectedMemberUsrs) { "Expected Apple member ownership inventory changed" }
    val relationships = root.appleArray("relationships").map { it.appleObject("$language relationship") }
        .filter { relationship ->
            relationship.appleString("kind") == "memberOf" &&
                relationship.appleString("source") in memberOwners
        }.map { relationship ->
            relationship.appleString("source") to relationship.appleString("target")
        }
    check(relationships.size == memberOwners.size &&
        relationships.map(Pair<String, String>::first).toSet() == memberOwners.keys &&
        relationships.all { (source, target) -> target == memberOwners.getValue(source) }) {
        "$language Apple binding ownership relationships changed"
    }
    return symbols.sortedBy(AppleCompilerSymbol::precise)
}

private fun normalizeAppleCompilerSymbol(symbol: JsonObject): AppleCompilerSymbol {
    val identifier = symbol.appleObject("identifier")
    val fragments = symbol.appleArray("declarationFragments").map { it.appleObject("declaration fragment") }
    val signature = symbol["functionSignature"] as? JsonObject
    val parameters = signature?.appleArray("parameters")?.map { parameterElement ->
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
                    val receiverType = (inner?.firstOrNull() as? JsonObject)
                        ?.get("classType")?.let { it as? JsonObject }?.appleStringOrNull("qualType")
                    expectedConstructors[receiverType to selector]
                } ?: return@mapNotNull null
                AppleCompilerReference(
                    receiver.precise, "ObjCMessageExpr", selector, receiver.receiverType,
                    node.appleObject("type").appleString("qualType"),
                    if (selector.startsWith("init")) {
                        requireNotNull(inner).drop(1).map { argument ->
                            argument.appleObject("Objective-C constructor argument")
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
