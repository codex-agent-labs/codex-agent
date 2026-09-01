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


internal suspend fun CodexAgentClient.handleNotificationAction(notification: ServerNotification) {
    when (notification) {
        is ServerNotificationAccountLoginCompletedNotification -> {
            val params = notification.params
            val completion = LoginCompletion(
                loginId = params.loginId ?: error("Login completion ID is missing"),
                success = params.success,
                error = params.error,
            )
            val applyNow = loginStateLock.withLock {
                if (cancelledLoginIds.remove(completion.loginId)) {
                    if (loginId == completion.loginId) loginId = null
                    false
                } else if (loginStarting) {
                    loginCompletedDuringStart = completion
                    false
                } else if (loginId == completion.loginId) {
                    loginId = null
                    true
                } else {
                    false
                }
            }
            if (applyNow) applyLoginCompletion(completion)
        }

        is ServerNotificationAccountUpdatedNotification -> {
            if (notification.params.authMode?.jsonPrimitive?.contentOrNull == "chatgpt") {
                emitAuthenticated()
            }
        }

        is ServerNotificationSkillsChangedNotification ->
            eventsChannel.send(AgentEvent.SkillsChanged)

        is ServerNotificationAppListUpdatedNotification ->
            eventsChannel.send(AgentEvent.ConnectorsChanged)

        is ServerNotificationMcpServerOauthLoginCompletedNotification -> eventsChannel.send(
            AgentEvent.McpOauthCompleted(
                serverName = notification.params.name,
                conversationId = notification.params.threadId?.let(::ConversationId),
                success = notification.params.success,
                error = notification.params.error,
            ),
        )

        is ServerNotificationItemAgentMessageDeltaNotification -> {
            val params = notification.params
            val conversationId = ConversationId(params.threadId)
            eventsChannel.send(
                AgentEvent.TextDelta(
                    conversationId = conversationId,
                    text = params.delta,
                    itemId = params.itemId,
                    isCommentary = params.itemId in commentaryItems,
                ),
            )
        }

        is ServerNotificationItemReasoningSummaryTextDeltaNotification -> {
            val params = notification.params
            eventsChannel.send(
                AgentEvent.ReasoningSummaryDelta(
                    conversationId = ConversationId(params.threadId),
                    text = params.delta,
                    itemId = params.itemId,
                    summaryIndex = params.summaryIndex,
                ),
            )
        }

        is ServerNotificationItemPlanDeltaNotification -> {
            val params = notification.params
            eventsChannel.send(
                AgentEvent.PlanDelta(
                    conversationId = ConversationId(params.threadId),
                    text = params.delta,
                    itemId = params.itemId,
                ),
            )
        }

        is ServerNotificationTurnPlanUpdatedNotification -> {
            val params = notification.params
            eventsChannel.send(
                AgentEvent.PlanUpdated(
                    conversationId = ConversationId(params.threadId),
                    progress = AgentPlanProgress(
                        explanation = params.explanation,
                        steps = params.plan.map { step ->
                            AgentPlanStep(
                                text = step.step,
                                status = enumValueOf(step.status.name),
                            )
                        },
                    ),
                ),
            )
        }

        is ServerNotificationHookStartedNotification -> eventsChannel.send(
            AgentEvent.HookActivityChanged(
                ConversationId(notification.params.threadId),
                notification.params.run.toAgentHookActivity(),
            ),
        )

        is ServerNotificationHookCompletedNotification -> eventsChannel.send(
            AgentEvent.HookActivityChanged(
                ConversationId(notification.params.threadId),
                notification.params.run.toAgentHookActivity(),
            ),
        )

        is ServerNotificationItemCommandExecutionOutputDeltaNotification -> {
            val params = notification.params
            if (params.itemId in userShellItems) {
                eventsChannel.send(
                    AgentEvent.ShellOutputDelta(
                        conversationId = ConversationId(params.threadId),
                        text = params.delta,
                    ),
                )
            }
        }

        is ServerNotificationItemStartedNotification -> {
            val params = notification.params
            val item = params.item
            if (
                item is ThreadItemAgentMessageThreadItem &&
                (item.phase as? JsonPrimitive)?.contentOrNull == "commentary"
            ) {
                commentaryItems += item.id
            }
            updateItemActivity(params.threadId, params.turnId, item, started = true)
        }

        is ServerNotificationItemCompletedNotification -> {
            val params = notification.params
            completeUserShellItem(params.threadId, params.turnId, params.item)
            updateItemActivity(params.threadId, params.turnId, params.item, started = false)
            (params.item as? ThreadItemAgentMessageThreadItem)?.let { commentaryItems -= it.id }
        }

        is ServerNotificationTurnCompletedNotification -> {
            val params = notification.params
            val conversationId = ConversationId(params.threadId)
            val event = if (params.turn.status == TurnStatus.FAILED) {
                val detail = params.turn.error?.message ?: "Turn failed"
                AgentEvent.Failure(conversationId, "turn_failed", detail, true)
            } else {
                AgentEvent.TurnCompleted(conversationId)
            }
            if (finishTurn(conversationId, params.turn.id, event)) eventsChannel.send(event)
        }

        is ServerNotificationErrorNotification -> {
            val params = notification.params
            if (!params.willRetry) {
                val conversationId = ConversationId(params.threadId)
                val event = AgentEvent.Failure(conversationId, "turn_error", params.error.message, true)
                if (finishTurn(conversationId, params.turnId, event)) eventsChannel.send(event)
            }
        }

        else -> Unit
    }
}
