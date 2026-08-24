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
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okio.FileSystem
import okio.Path.Companion.toPath
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


internal suspend fun CodexAgentClient.listModelsAction(): List<AgentModel> =
    requestAllPages(
        AppServerClientMethods.ModelList,
        params = { ModelListParams(cursor = it) },
        data = ModelListResponse::data,
        nextCursor = ModelListResponse::nextCursor,
    ) { item ->
    val serviceTiers = item.serviceTiers.orEmpty().map { tier ->
            AgentServiceTier(tier.id, tier.name, tier.description)
        }.distinctBy(AgentServiceTier::id)
    AgentModel(
        id = item.model,
        displayName = item.displayName,
        description = item.description,
        supportedEfforts = item.supportedReasoningEfforts.map { it.reasoningEffort },
        defaultEffort = item.defaultReasoningEffort,
        isDefault = item.isDefault,
        serviceTiers = serviceTiers,
        defaultServiceTier = item.defaultServiceTier,
    )
}

internal suspend fun CodexAgentClient.listSkillsAction(
    workingDirectory: String,
    forceReload: Boolean,
): AgentSkillCatalog {
    require(workingDirectory.isAbsoluteHostPath()) { "Working directory must be absolute" }
    val result = connection.request(
        AppServerClientMethods.SkillsList,
        SkillsListParams(cwds = listOf(workingDirectory), forceReload = forceReload),
    )
    val entries = result.data
    return AgentSkillCatalog(
        skills = entries.flatMap { it.skills }.map(::parseSkill)
            .distinctBy { it.path },
        errors = entries.flatMap { it.errors }.map { "${it.path}: ${it.message}" },
    ).also { catalog ->
        stateLock.withLock {
            knownSkillPaths.clear()
            catalog.skills.mapTo(knownSkillPaths, io.github.codex_agent_labs.codexagent.agent.AgentSkill::path)
        }
    }
}

internal suspend fun CodexAgentClient.readSkillAction(path: String, offset: Long): AgentSkillChunk = withContext(coroutineDispatcher) {
    require(stateLock.withLock { path in knownSkillPaths }) { "Skill was not returned by skills/list" }
    require(offset >= 0) { "Offset must not be negative" }
    val fileSystem = requireFileSystem()
    val file = path.toPath()
    val total = fileSystem.size(file)
    require(total != null) { "Skill source is not readable" }
    require(offset <= total) { "Offset exceeds skill source size" }
    val count = minOf(SKILL_CHUNK_BYTES.toLong(), total - offset).toInt()
    val bytes = fileSystem.readBytes(file, offset, count)
    val complete = if (offset + count < total) completeUtf8Length(bytes, count) else count
    val next = (offset + complete).takeIf { it < total }
    AgentSkillChunk(
        content = bytes.decodeToString(0, complete, throwOnInvalidSequence = true),
        nextOffset = next,
        totalBytes = total,
    )
}

internal suspend fun CodexAgentClient.setSkillEnabledAction(path: String, enabled: Boolean) {
    require(path.isAbsoluteHostPath()) { "Skill path must be absolute" }
    connection.request(
        AppServerClientMethods.SkillsConfigWrite,
        SkillsConfigWriteParams(path = path, enabled = enabled),
    )
}
