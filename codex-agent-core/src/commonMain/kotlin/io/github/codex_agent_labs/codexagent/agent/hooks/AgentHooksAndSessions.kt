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


internal suspend fun CodexAgentClient.listHooksAction(workingDirectory: String): AgentHookCatalog {
    validateWorkingDirectory(workingDirectory)
    val entries = connection.request(
        AppServerClientMethods.HooksList,
        HooksListParams(listOf(workingDirectory)),
    ).data
    return AgentHookCatalog(
        hooks = entries.flatMap(HooksListEntry::hooks)
            .map(::parseHook)
            .map { hook -> hook.copy(canUninstall = ownedResources?.ownsHook(hook) == true) }
            .distinctBy(AgentHook::key)
            .sortedBy(AgentHook::key),
        warnings = entries.flatMap(HooksListEntry::warnings).distinct(),
        errors = entries.flatMap(HooksListEntry::errors).map { "${it.path}: ${it.message}" }.distinct(),
    )
}

private fun parseHook(hook: HookMetadata): AgentHook = when (hook) {
    is HookMetadataCommand -> hook.toAgentHook(
        AgentHookHandler.Command(hook.command, hook.async ?: false),
    )
    is HookMetadataMcpTool -> hook.toAgentHook(
        AgentHookHandler.McpTool(hook.server, hook.tool),
    )
    is HookMetadataPromptHookMetadata -> hook.toAgentHook(AgentHookHandler.Prompt)
    is HookMetadataAgentHookMetadata -> hook.toAgentHook(AgentHookHandler.Agent)
}

private fun HookMetadataCommand.toAgentHook(handler: AgentHookHandler): AgentHook = AgentHook(
    key = key,
    currentHash = currentHash,
    isEnabled = enabled,
    eventName = eventName.name,
    handler = handler,
    isManaged = isManaged,
    source = source.name,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSec,
    trustStatus = enumValueOf(trustStatus.name),
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
)

private fun HookMetadataMcpTool.toAgentHook(handler: AgentHookHandler): AgentHook = AgentHook(
    key = key,
    currentHash = currentHash,
    isEnabled = enabled,
    eventName = eventName.name,
    handler = handler,
    isManaged = isManaged,
    source = source.name,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSec,
    trustStatus = enumValueOf(trustStatus.name),
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
)

private fun HookMetadataPromptHookMetadata.toAgentHook(handler: AgentHookHandler): AgentHook = AgentHook(
    key = key,
    currentHash = currentHash,
    isEnabled = enabled,
    eventName = eventName.name,
    handler = handler,
    isManaged = isManaged,
    source = source.name,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSec,
    trustStatus = enumValueOf(trustStatus.name),
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
)

private fun HookMetadataAgentHookMetadata.toAgentHook(handler: AgentHookHandler): AgentHook = AgentHook(
    key = key,
    currentHash = currentHash,
    isEnabled = enabled,
    eventName = eventName.name,
    handler = handler,
    isManaged = isManaged,
    source = source.name,
    sourcePath = sourcePath,
    timeoutSeconds = timeoutSec,
    trustStatus = enumValueOf(trustStatus.name),
    matcher = matcher,
    pluginId = pluginId,
    statusMessage = statusMessage,
)

internal suspend fun CodexAgentClient.setHookEnabledAction(key: String, enabled: Boolean) {
    require(key.isNotBlank()) { "Hook key must not be blank" }
    writeHookState(key) { put("enabled", enabled) }
}

internal suspend fun CodexAgentClient.trustHookAction(key: String, currentHash: String) {
    require(key.isNotBlank()) { "Hook key must not be blank" }
    require(currentHash.isNotBlank()) { "Hook hash must not be blank" }
    writeHookState(key) { put("trusted_hash", currentHash) }
}

internal suspend fun CodexAgentClient.writeHookStateAction(key: String, state: JsonObjectBuilder.() -> Unit) {
    connection.request(
        AppServerClientMethods.ConfigBatchWrite,
        ConfigBatchWriteParams(
            edits = listOf(
                ConfigEdit(
                    keyPath = "hooks.state",
                    mergeStrategy = MergeStrategy.UPSERT,
                    value = buildJsonObject { putJsonObject(key, state) },
                ),
            ),
            reloadUserConfig = true,
        ),
    )
}

internal suspend fun CodexAgentClient.startMcpOauthAction(
    serverName: String,
    conversationId: ConversationId?,
    onRequestEnqueued: (suspend () -> Unit)?,
): String {
    require(serverName.isNotBlank()) { "MCP server name must not be blank" }
    return connection.request(
        AppServerClientMethods.McpServerOauthLogin,
        McpServerOauthLoginParams(name = serverName, threadId = conversationId?.value),
        onRequestEnqueued = onRequestEnqueued,
    ).authorizationUrl.also(::requireSafeAuthUrl)
}

internal suspend fun CodexAgentClient.listConversationsAction(): List<AgentConversationSummary> {
    val threads = requestAllPages(
        AppServerClientMethods.ThreadList,
        params = { cursor ->
            ThreadListParams(
                cursor = cursor,
                sortDirection = SortDirection.DESC,
                sortKey = ThreadSortKey.UPDATED_AT,
            )
        },
        data = ThreadListResponse::data,
        nextCursor = ThreadListResponse::nextCursor,
        transform = { it },
    )
    return threads.map { thread ->
        conversationSummary(
            thread,
            shellTranscriptStore.read(thread.id).firstOrNull()?.let { "!${it.command}" },
        )
    }
}

internal suspend fun CodexAgentClient.readConversationAction(conversationId: ConversationId): AgentConversation {
    val thread = connection.request(
        AppServerClientMethods.ThreadRead,
        ThreadReadParams(conversationId.value, includeTurns = true),
    ).thread
    check(thread.id == conversationId.value) { "App-server returned another thread" }
    val transcripts = shellTranscriptStore.read(conversationId.value).groupBy(ShellTranscript::turnId)
    val recordedInvocations = turnInputMetadataStore.read(conversationId.value)
    val messages = thread.turns.flatMap { turn ->
        transcripts[turn.id].orEmpty().flatMap(::shellTranscriptMessages) + conversationMessages(
            turn.items.map { item ->
                PROTOCOL_JSON.encodeToJsonElement(ThreadItem.serializer(), item)
            },
            recordedInvocations,
        )
    }
    return AgentConversation(
        conversationSummary(thread, transcripts.values.flatten().firstOrNull()?.let { "!${it.command}" }),
        messages,
    )
}

internal suspend fun CodexAgentClient.renameConversationAction(conversationId: ConversationId, name: String) {
    val snapshot = name.trim()
    require(snapshot.isNotEmpty()) { "Conversation name must not be blank" }
    connection.request(
        AppServerClientMethods.ThreadNameSet,
        ThreadSetNameParams(name = snapshot, threadId = conversationId.value),
    )
}

internal suspend fun CodexAgentClient.deleteConversationAction(conversationId: ConversationId) {
    connection.request(
        AppServerClientMethods.ThreadDelete,
        ThreadDeleteParams(conversationId.value),
    )
    stateLock.withLock {
        openedConversations -= conversationId
        conversationOwners -= conversationId
        conversationRuntimeSettings -= conversationId
    }
    shellTranscriptStore.delete(conversationId.value)
    turnInputMetadataStore.delete(conversationId.value)
    turnStateLock.withLock {
        shellStartupCompletions.remove(conversationId)?.complete(false)
        activeTurns -= conversationId
        startingTurns -= conversationId
        pendingTerminalsDuringStart.keys.removeAll { it.first == conversationId }
        recentTerminalTurnIds -= conversationId
        cancellingTurns -= conversationId
        cancelledTurns -= conversationId
    }
}

internal suspend fun CodexAgentClient.detachConversationAction(
    conversationId: ConversationId,
    owner: Any,
): ConversationDetachResult = conversationOwnershipLock.withLock {
    if (stateLock.withLock { conversationOwners[conversationId] !== owner }) {
        return@withLock ConversationDetachResult(owned = false)
    }
    var failure: Throwable? = null
    try {
        cancelPendingBuiltInTools(conversationId, null, "Conversation was closed")
    } catch (error: Throwable) {
        failure = error
    }
    val pending = stateLock.withLock {
        val approvals = pendingApprovalRequests.entries
            .filter { it.value.conversationId == conversationId }
            .map { it.key to it.value }
        approvals.forEach { (requestId) -> pendingApprovalRequests.remove(requestId) }
        val elicitations = pendingElicitationRequests.entries
            .filter { it.value.elicitation.conversationId == conversationId }
            .map { it.key to it.value }
        elicitations.forEach { (requestId) -> pendingElicitationRequests.remove(requestId) }
        openedConversations -= conversationId
        conversationOwners -= conversationId
        conversationRuntimeSettings -= conversationId
        workItems.entries.removeAll { it.value.first == conversationId }
        approvals.map { it.second } to elicitations.map { it.second }
    }
    turnStateLock.withLock {
        shellStartupCompletions.remove(conversationId)?.complete(false)
        activeTurns -= conversationId
        startingTurns -= conversationId
        pendingTerminalsDuringStart.keys.removeAll { it.first == conversationId }
        recentTerminalTurnIds -= conversationId
        cancellingTurns -= conversationId
        cancelledTurns -= conversationId
    }
    pending.first.forEach { approval ->
        runCatching {
            when (approval.type) {
                ApprovalType.COMMAND -> connection.respond(
                    approval.wireId,
                    AppServerServerMethods.ItemCommandExecutionRequestApproval,
                    CommandExecutionRequestApprovalResponse(JsonPrimitive("decline")),
                )
                ApprovalType.FILE_CHANGE -> connection.respond(
                    approval.wireId,
                    AppServerServerMethods.ItemFileChangeRequestApproval,
                    FileChangeRequestApprovalResponse(JsonPrimitive("decline")),
                )
            }
        }
    }
    pending.second.forEach { elicitation ->
        runCatching {
            when (elicitation) {
                is PendingElicitation.Mcp -> connection.respond(
                    elicitation.wireId,
                    AppServerServerMethods.McpServerElicitationRequest,
                    McpServerElicitationRequestResponse(McpServerElicitationAction.DECLINE),
                )
                is PendingElicitation.UserInput -> connection.respond(
                    elicitation.wireId,
                    AppServerServerMethods.ItemToolRequestUserInput,
                    ToolRequestUserInputResponse(emptyMap()),
                )
            }
        }
    }
    ConversationDetachResult(owned = true, failure = failure)
}

internal suspend fun <P, R, T, U> CodexAgentClient.requestAllPagesAction(
    method: AppServerMethod<P, R>,
    params: (String?) -> P,
    data: (R) -> List<T>,
    nextCursor: (R) -> String?,
    transform: (T) -> U,
): List<U> {
    val values = mutableListOf<U>()
    val seenCursors = mutableSetOf<String>()
    var cursor: String? = null
    do {
        val page = connection.request(method, params(cursor))
        values += data(page).map(transform)
        cursor = nextCursor(page)
        check(cursor == null || seenCursors.add(cursor)) { "App-server repeated a pagination cursor" }
    } while (cursor != null)
    return values
}
