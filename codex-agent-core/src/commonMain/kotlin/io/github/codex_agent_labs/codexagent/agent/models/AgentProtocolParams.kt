package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.appserver.client.AppServerConnection
import io.github.codex_agent_labs.codexagent.appserver.client.AppServerEvent
import io.github.codex_agent_labs.codexagent.appserver.client.AppServerRpcException
import io.github.codex_agent_labs.codexagent.appserver.client.AppServerTimeoutException
import io.github.codex_agent_labs.codexagent.appserver.protocol.generated.*
import io.github.codex_agent_labs.codexagent.appserver.runtime.CodexRuntimeFactory
import io.github.codex_agent_labs.codexagent.agent.AgentCatalogFreshness
import io.github.codex_agent_labs.codexagent.agent.AgentCapability
import io.github.codex_agent_labs.codexagent.agent.AgentConnector
import io.github.codex_agent_labs.codexagent.agent.AgentCollaborationMode
import io.github.codex_agent_labs.codexagent.agent.AgentConversation
import io.github.codex_agent_labs.codexagent.agent.AgentConversationSummary
import io.github.codex_agent_labs.codexagent.agent.AgentElicitationAction
import io.github.codex_agent_labs.codexagent.agent.AgentElicitationResponse
import io.github.codex_agent_labs.codexagent.agent.AgentEvent
import io.github.codex_agent_labs.codexagent.agent.AgentFormValue
import io.github.codex_agent_labs.codexagent.agent.AgentInvocation
import io.github.codex_agent_labs.codexagent.agent.AgentHook
import io.github.codex_agent_labs.codexagent.agent.AgentHookActivity
import io.github.codex_agent_labs.codexagent.agent.AgentHookCatalog
import io.github.codex_agent_labs.codexagent.agent.AgentHookRunStatus
import io.github.codex_agent_labs.codexagent.agent.AgentHookTrustStatus
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServer
import io.github.codex_agent_labs.codexagent.agent.AgentMessage
import io.github.codex_agent_labs.codexagent.agent.AgentMessageRole
import io.github.codex_agent_labs.codexagent.agent.AgentModel
import io.github.codex_agent_labs.codexagent.agent.AgentApprovalDecision
import io.github.codex_agent_labs.codexagent.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexagent.agent.AgentPluginAuthPolicy
import io.github.codex_agent_labs.codexagent.agent.AgentPluginCatalog
import io.github.codex_agent_labs.codexagent.agent.AgentPluginDetail
import io.github.codex_agent_labs.codexagent.agent.AgentPluginInstallResult
import io.github.codex_agent_labs.codexagent.agent.AgentPluginReference
import io.github.codex_agent_labs.codexagent.agent.AgentPluginUnavailableException
import io.github.codex_agent_labs.codexagent.agent.AgentPlanProgress
import io.github.codex_agent_labs.codexagent.agent.AgentPlanStep
import io.github.codex_agent_labs.codexagent.agent.AgentPlanStepStatus
import io.github.codex_agent_labs.codexagent.agent.AgentConversationSettings
import io.github.codex_agent_labs.codexagent.agent.AgentServiceTier
import io.github.codex_agent_labs.codexagent.agent.AgentSkillCatalog
import io.github.codex_agent_labs.codexagent.agent.AgentSkillChunk
import io.github.codex_agent_labs.codexagent.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexagent.agent.AgentWorkActivity
import io.github.codex_agent_labs.codexagent.agent.ConversationId
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonObjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject
import kotlinx.serialization.KSerializer


internal fun CodexAgentClient.shellTranscriptMessagesAction(transcript: ShellTranscript): List<AgentMessage> = listOf(
    AgentMessage(
        id = "shell-user-${transcript.itemId}",
        clientMessageId = null,
        role = AgentMessageRole.USER,
        text = "!${transcript.command}",
        shellCommand = transcript.command,
    ),
    AgentMessage(
        id = transcript.itemId,
        clientMessageId = null,
        role = AgentMessageRole.ASSISTANT,
        text = transcript.output,
        shellCommand = transcript.command,
        exitCode = transcript.exitCode,
    ),
)

internal fun CodexAgentClient.pluginReadParamsAction(plugin: AgentPluginReference) = PluginReadParams(
    pluginName = plugin.appServerPluginName(),
    marketplacePath = plugin.marketplacePath,
    remoteMarketplaceName = plugin.marketplaceName.takeIf { plugin.marketplacePath == null },
)

internal fun CodexAgentClient.pluginInstallParamsAction(plugin: AgentPluginReference) = PluginInstallParams(
    pluginName = plugin.appServerPluginName(),
    marketplacePath = plugin.marketplacePath,
    remoteMarketplaceName = plugin.marketplaceName.takeIf { plugin.marketplacePath == null },
)

internal fun CodexAgentClient.pluginUninstallParamsAction(plugin: AgentPluginReference) = PluginUninstallParams(
    pluginId = if (plugin.marketplacePath == null) plugin.appServerPluginName() else plugin.id,
)

internal fun CodexAgentClient.pluginEnablementParamsAction(pluginId: String, enabled: Boolean) = ConfigValueWriteParams(
    keyPath = "plugins.$pluginId.enabled",
    value = JsonPrimitive(enabled),
    mergeStrategy = MergeStrategy.UPSERT,
)

internal fun CodexAgentClient.approvalsReviewerAction(preset: AgentApprovalPreset) = when (preset) {
    AgentApprovalPreset.AUTO_REVIEW -> ApprovalsReviewer.AUTO_REVIEW
    else -> ApprovalsReviewer.USER
}

internal fun AgentApprovalPreset.wireApprovalPolicy(): String = when (this) {
    AgentApprovalPreset.NEVER -> "never"
    AgentApprovalPreset.AUTO_REVIEW,
    AgentApprovalPreset.ASK_ME,
    -> "on-request"
    AgentApprovalPreset.STRICT -> "untrusted"
}

internal fun CodexAgentClient.elicitationResponseAction(response: AgentElicitationResponse): McpServerElicitationRequestResponse {
    val content = if (response.action == AgentElicitationAction.ACCEPT) {
        buildJsonObject {
            response.content.forEach { (name, value) ->
                put(
                    name,
                    when (value) {
                        is AgentFormValue.Text -> JsonPrimitive(value.value)
                        is AgentFormValue.Number -> JsonPrimitive(value.value)
                        is AgentFormValue.BooleanValue -> JsonPrimitive(value.value)
                        is AgentFormValue.TextList -> JsonArray(value.value.map(::JsonPrimitive))
                    },
                )
            }
        }
    } else {
        null
    }
    return McpServerElicitationRequestResponse(
        action = when (response.action) {
            AgentElicitationAction.ACCEPT -> McpServerElicitationAction.ACCEPT
            AgentElicitationAction.DECLINE -> McpServerElicitationAction.DECLINE
            AgentElicitationAction.CANCEL -> McpServerElicitationAction.CANCEL
        },
        content = content,
    )
}
