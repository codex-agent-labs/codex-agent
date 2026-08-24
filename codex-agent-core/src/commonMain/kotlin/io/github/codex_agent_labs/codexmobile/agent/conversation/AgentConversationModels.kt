package io.github.codex_agent_labs.codexmobile.agent

@CodexBindingApi
public data class ConversationId(public val value: String) {
    init {
        require(value.isNotBlank()) { "Conversation ID must not be blank" }
    }
}

@CodexBindingApi
public data class AgentModel(
    public val id: String,
    public val displayName: String,
    public val description: String,
    public val supportedEfforts: List<String>,
    public val defaultEffort: String,
    public val isDefault: Boolean,
    public val serviceTiers: List<AgentServiceTier> = emptyList(),
    public val defaultServiceTier: String? = null,
)

@CodexBindingApi
public data class AgentServiceTier(
    public val id: String,
    public val name: String,
    public val description: String,
)

@CodexBindingApi
public enum class AgentApprovalPreset(
    public val displayName: String,
) {
    NEVER("Never"),
    AUTO_REVIEW("Auto review"),
    ASK_ME("Ask me"),
    STRICT("Strict"),
}

@CodexBindingApi
public enum class AgentApprovalDecision {
    ACCEPT,
    DECLINE,
}

@CodexBindingApi
public data class AgentConversationSettings(
    public val approvalPreset: AgentApprovalPreset = AgentApprovalPreset.AUTO_REVIEW,
    public val serviceTier: String? = null,
)

@CodexBindingApi
public data class AgentConversationSummary(
    public val conversationId: ConversationId,
    public val title: String,
    public val updatedAtEpochSeconds: Long,
)

@CodexBindingApi
public data class AgentConversation(
    public val summary: AgentConversationSummary,
    public val messages: List<AgentMessage>,
)

@CodexBindingApi
public enum class AgentMessageRole { USER, ASSISTANT }

@CodexBindingApi
public data class AgentMessage(
    public val id: String,
    public val clientMessageId: String?,
    public val role: AgentMessageRole,
    public val text: String,
    public val collaborationMode: AgentCollaborationMode = AgentCollaborationMode.DEFAULT,
    public val reasoning: String? = null,
    public val plan: String? = null,
    public val shellCommand: String? = null,
    public val exitCode: Int? = null,
    public val capabilities: Set<AgentCapability> = emptySet(),
    public val invocations: List<AgentInvocation> = emptyList(),
)

@CodexBindingApi
public enum class AgentCollaborationMode { DEFAULT, PLAN }

internal const val PLAN_CLIENT_MESSAGE_PREFIX = "codex-agent:plan:"
internal const val LEGACY_PLAN_CLIENT_MESSAGE_PREFIX = "codex-mobile:plan:"

@CodexBindingApi
public enum class AgentPlanStepStatus { PENDING, IN_PROGRESS, COMPLETED }

@CodexBindingApi
public data class AgentPlanStep(public val text: String, public val status: AgentPlanStepStatus)

@CodexBindingApi
public data class AgentPlanProgress(
    public val explanation: String? = null,
    public val steps: List<AgentPlanStep> = emptyList(),
)

@CodexBindingApi
public enum class AgentHookTrustStatus { MANAGED, UNTRUSTED, TRUSTED, MODIFIED }

@CodexBindingApi
public sealed interface AgentHookHandler {
    public data class Command(
        public val command: String,
        public val isAsync: Boolean,
    ) : AgentHookHandler

    public data class McpTool(
        public val server: String,
        public val tool: String,
    ) : AgentHookHandler

    public data object Prompt : AgentHookHandler

    public data object Agent : AgentHookHandler
}

@CodexBindingApi
public data class AgentHook(
    public val key: String,
    public val currentHash: String,
    public val isEnabled: Boolean,
    public val eventName: String,
    public val handler: AgentHookHandler,
    public val isManaged: Boolean,
    public val source: String,
    public val sourcePath: String,
    public val timeoutSeconds: Long,
    public val trustStatus: AgentHookTrustStatus,
    public val matcher: String? = null,
    public val pluginId: String? = null,
    public val statusMessage: String? = null,
    public val origin: AgentResourceOrigin = when {
        pluginId != null || source == "PLUGIN" -> AgentResourceOrigin.PLUGIN
        isManaged || source in setOf(
            "SYSTEM",
            "MDM",
            "CLOUD_REQUIREMENTS",
            "CLOUD_MANAGED_CONFIG",
            "LEGACY_MANAGED_CONFIG_FILE",
            "LEGACY_MANAGED_CONFIG_MDM",
        ) -> AgentResourceOrigin.MANAGED
        source == "USER" -> AgentResourceOrigin.USER
        source == "PROJECT" -> AgentResourceOrigin.WORKSPACE
        else -> AgentResourceOrigin.UNKNOWN
    },
    public val canUninstall: Boolean = false,
) {
    public val canTrust: Boolean
        get() = trustStatus == AgentHookTrustStatus.UNTRUSTED || trustStatus == AgentHookTrustStatus.MODIFIED
}

@CodexBindingApi
public data class AgentHookCatalog(
    public val hooks: List<AgentHook>,
    public val warnings: List<String> = emptyList(),
    public val errors: List<String> = emptyList(),
)

@CodexBindingApi
public enum class AgentHookRunStatus { RUNNING, COMPLETED, FAILED, BLOCKED, STOPPED }

@CodexBindingApi
public data class AgentHookActivity(
    public val id: String,
    public val eventName: String,
    public val handlerType: String,
    public val status: AgentHookRunStatus,
    public val statusMessage: String? = null,
    public val details: List<String> = emptyList(),
)

@CodexBindingApi
public enum class AgentCapability(
    public val id: String,
    public val displayLabel: String,
    public val icon: String?,
    public val promptLabel: String,
) {
    WEB_SEARCH("web_search", "Web search", "🌐", "Use 🌐 Web search"),
}

@CodexBindingApi
public data class AgentTurnRequest(
    public val prompt: String,
    public val clientMessageId: String? = null,
    public val model: String? = null,
    public val effort: String? = null,
    public val serviceTier: String? = null,
    public val approvalPreset: AgentApprovalPreset = AgentApprovalPreset.AUTO_REVIEW,
    public val capabilities: Set<AgentCapability> = emptySet(),
    public val invocations: List<AgentInvocation> = emptyList(),
    public val collaborationMode: AgentCollaborationMode = AgentCollaborationMode.DEFAULT,
)

internal fun deriveConversationTitle(
    explicitName: String?,
    firstUserText: String,
    maxLength: Int = 80,
): String {
    require(maxLength > 0)
    val title = explicitName?.trim()?.takeIf { it.isNotEmpty() }
        ?: firstUserText.lineSequence().firstOrNull { it.isNotBlank() }?.trim()
        ?: "New chat"
    return title.take(maxLength).trimEnd()
}
