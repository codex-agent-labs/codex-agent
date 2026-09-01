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


internal suspend fun CodexAgentClient.finishTurnAction(
    conversationId: ConversationId,
    turnId: String,
    event: AgentEvent,
): Boolean {
    val accepted = turnStateLock.withLock {
        val recent = recentTerminalTurnIds[conversationId].orEmpty()
        when {
            turnId in recent -> false
            conversationId in startingTurns -> {
                pendingTerminalsDuringStart[conversationId to turnId] = event
                false
            }
            activeTurns[conversationId] == turnId -> {
                activeTurns -= conversationId
                cancellingTurns -= conversationId
                if (cancelledTurns[conversationId] == turnId) cancelledTurns -= conversationId
                rememberTerminalTurnLocked(conversationId, turnId)
                true
            }
            else -> false
        }
    }
    if (!accepted) return false
    cleanupFinishedTurnAction(conversationId, turnId)
    return true
}

internal suspend fun CodexAgentClient.publishAcceptedTerminalAction(
    conversationId: ConversationId,
    terminal: PendingTurnTerminal,
) {
    turnStateLock.withLock { rememberTerminalTurnLocked(conversationId, terminal.turnId) }
    cleanupFinishedTurnAction(conversationId, terminal.turnId)
    eventsChannel.send(terminal.event)
}

private suspend fun CodexAgentClient.cleanupFinishedTurnAction(
    conversationId: ConversationId,
    turnId: String,
) {
    cancelPendingBuiltInTools(conversationId, turnId, "Built-in tool call is no longer active")
    val removedWork = stateLock.withLock {
        workItems.entries.removeAll { it.value.first == conversationId }
    }
    if (removedWork) eventsChannel.send(AgentEvent.WorkActivityChanged(conversationId, null))
}

private fun CodexAgentClient.rememberTerminalTurnLocked(conversationId: ConversationId, turnId: String) {
    val recent = recentTerminalTurnIds.getOrPut(conversationId, ::ArrayDeque)
    recent.remove(turnId)
    recent.addLast(turnId)
    while (recent.size > MAX_RECENT_TERMINAL_TURNS) recent.removeFirst()
}

private const val MAX_RECENT_TERMINAL_TURNS = 32

internal suspend fun CodexAgentClient.updateItemActivityAction(
    threadId: String,
    turnId: String,
    item: ThreadItem,
    started: Boolean,
) {
    val conversationId = ConversationId(threadId)
    val itemId = when (item) {
        is ThreadItemCommandExecutionThreadItem -> item.id
        is ThreadItemFileChangeThreadItem -> item.id
        else -> return
    }
    if (
        started && item is ThreadItemCommandExecutionThreadItem &&
        item.source == CommandExecutionSource.USER_SHELL
    ) {
        var deferredTerminal: PendingTurnTerminal? = null
        val accepted = turnStateLock.withLock {
            val startup = shellStartupCompletions.remove(conversationId)
            if (startup != null) {
                startingTurns -= conversationId
                val pending = pendingTerminalsDuringStart.remove(conversationId to turnId)
                pendingTerminalsDuringStart.keys.removeAll { it.first == conversationId }
                if (pending != null) {
                    rememberTerminalTurnLocked(conversationId, turnId)
                    deferredTerminal = PendingTurnTerminal(turnId, pending)
                    startup.complete(false)
                    false
                } else {
                    activeTurns[conversationId] = turnId
                    startup.complete(true)
                    true
                }
            } else {
                false
            }
        }
        deferredTerminal?.let {
            publishAcceptedTerminalAction(conversationId, it)
            return
        }
        if (accepted) stateLock.withLock { userShellItems += itemId }
    }
    val activity = when (item) {
        is ThreadItemCommandExecutionThreadItem -> AgentWorkActivity.RUNNING_COMMAND
        is ThreadItemFileChangeThreadItem -> AgentWorkActivity.WRITING_FILES
    }
    if (started) {
        stateLock.withLock { workItems[itemId] = conversationId to activity }
        eventsChannel.send(AgentEvent.WorkActivityChanged(conversationId, activity))
    } else if (!started && stateLock.withLock { workItems.remove(itemId) != null }) {
        val activity = stateLock.withLock {
            workItems.values.lastOrNull { it.first == conversationId }?.second
        }
        eventsChannel.send(
            AgentEvent.WorkActivityChanged(
                conversationId,
                activity,
            ),
        )
    }
}

internal suspend fun CodexAgentClient.completeUserShellItemAction(threadId: String, turnId: String, item: ThreadItem) {
    if (item !is ThreadItemCommandExecutionThreadItem) return
    if (stateLock.withLock { userShellItems.remove(item.id) } ||
        item.source == CommandExecutionSource.USER_SHELL
    ) {
        runCatching {
            shellTranscriptStore.upsert(
                threadId,
                ShellTranscript(
                    turnId = turnId,
                    itemId = item.id,
                    command = item.command,
                    output = item.aggregatedOutput.orEmpty().boundedShellTranscript(),
                    exitCode = item.exitCode?.toInt(),
                ),
            )
        }
        eventsChannel.send(
            AgentEvent.ShellCommandCompleted(
                conversationId = ConversationId(threadId),
                exitCode = item.exitCode?.toInt(),
            ),
        )
    }
}
