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


internal suspend fun CodexAgentClient.resolveApprovalAction(requestId: String, decision: AgentApprovalDecision) {
    stateLock.withLock { pendingBuiltInApprovals.remove(requestId) }?.let { pending ->
        if (decision == AgentApprovalDecision.ACCEPT) {
            pending.permit = true
            executeBuiltInTool(pending)
        } else {
            respondBuiltInResult(
                pending.wireId,
                BuiltInToolResult.text("The user declined this built-in tool mutation.", false),
            )
        }
        return
    }
    val pending = stateLock.withLock { pendingApprovalRequests.remove(requestId) }
        ?: error("Approval request is no longer pending")
    val wireDecision = JsonPrimitive(decision.name.lowercase())
    when (pending.type) {
        ApprovalType.COMMAND -> connection.respond(
            pending.wireId,
            AppServerServerMethods.ItemCommandExecutionRequestApproval,
            CommandExecutionRequestApprovalResponse(wireDecision),
        )
        ApprovalType.FILE_CHANGE -> connection.respond(
            pending.wireId,
            AppServerServerMethods.ItemFileChangeRequestApproval,
            FileChangeRequestApprovalResponse(wireDecision),
        )
    }
}

internal suspend fun CodexAgentClient.resolveElicitationAction(
    requestId: String,
    response: AgentElicitationResponse,
) {
    val pending = stateLock.withLock { pendingElicitationRequests[requestId] }
        ?: error("Elicitation request is no longer pending")
    require(pending.elicitation.accepts(response)) { "Elicitation response is invalid" }
    stateLock.withLock {
        check(pendingElicitationRequests.remove(requestId) === pending) {
            "Elicitation request is no longer pending"
        }
    }
    when (pending) {
        is PendingElicitation.Mcp -> connection.respond(
            pending.wireId,
            AppServerServerMethods.McpServerElicitationRequest,
            elicitationResponse(response),
        )
        is PendingElicitation.UserInput -> connection.respond(
            pending.wireId,
            AppServerServerMethods.ItemToolRequestUserInput,
            ToolRequestUserInputResponse(
                answers = if (response.action == AgentElicitationAction.ACCEPT) {
                    response.content.mapValues { (_, value) ->
                        ToolRequestUserInputAnswer(
                            when (value) {
                                is AgentFormValue.Text -> listOf(value.value)
                                is AgentFormValue.Number -> listOf(value.value.toString())
                                is AgentFormValue.BooleanValue -> listOf(value.value.toString())
                                is AgentFormValue.TextList -> value.value
                            },
                        )
                    }
                } else {
                    emptyMap()
                },
            ),
        )
    }
}

internal suspend fun CodexAgentClient.closeSuspendingAction() {
    turnStateLock.withLock {
        shellStartupCompletions.values.forEach { it.complete(false) }
        shellStartupCompletions.clear()
        activeTurns.clear()
        startingTurns.clear()
        pendingTerminalsDuringStart.clear()
        recentTerminalTurnIds.clear()
        cancellingTurns.clear()
        cancelledTurns.clear()
    }
    val closeNow = stateLock.withLock {
        if (closed) {
            false
        } else {
            closed = true
            pendingApprovalRequests.clear()
            pendingBuiltInApprovals.clear()
            pendingElicitationRequests.clear()
            workItems.clear()
            userShellItems.clear()
            commentaryItems.clear()
            knownSkillPaths.clear()
            openedConversations.clear()
            conversationOwners.clear()
            conversationRuntimeSettings.clear()
            true
        }
    }
    if (!closeNow) return
    connection.shutdown()
    scope.cancel()
    eventsChannel.close()
}
