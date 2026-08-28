@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentConversation
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentHook
import io.github.codex_agent_labs.codexmobile.agent.AgentHookCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler
import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentModel
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginDetail
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallResult
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier
import io.github.codex_agent_labs.codexmobile.agent.AgentSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillChunk
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

@CName("codex_agent_operation_conversation_summaries_count")
public fun codexAgentOperationConversationSummariesCount(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = operationListCount(
    context,
    operation,
    outCount,
    CodexAgentCOperationValueKind.CONVERSATION_SUMMARIES,
)

@CName("codex_agent_operation_conversation_summary_at")
public fun codexAgentOperationConversationSummaryAt(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    index: ULong,
    outSummary: CPointer<COpaquePointerVar>?,
): Int = operationListItem<AgentConversationSummary>(
    context,
    operation,
    index,
    outSummary,
    CodexAgentCOperationValueKind.CONVERSATION_SUMMARIES,
) { CodexAgentCConversationSummarySnapshot(it.operationCopy()) }

@CName("codex_agent_operation_conversation_value")
public fun codexAgentOperationConversationValue(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outConversation: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentConversation>(
    context,
    operation,
    outConversation,
    CodexAgentCOperationValueKind.CONVERSATION_VALUE,
) { CodexAgentCConversationValueSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_models_count")
public fun codexAgentOperationModelsCount(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = operationListCount(context, operation, outCount, CodexAgentCOperationValueKind.MODELS)

@CName("codex_agent_operation_model_at")
public fun codexAgentOperationModelAt(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    index: ULong,
    outModel: CPointer<COpaquePointerVar>?,
): Int = operationListItem<AgentModel>(
    context,
    operation,
    index,
    outModel,
    CodexAgentCOperationValueKind.MODELS,
) { CodexAgentCModelSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_model")
public fun codexAgentOperationModel(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outModel: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentModel>(
    context,
    operation,
    outModel,
    CodexAgentCOperationValueKind.MODEL,
) { CodexAgentCModelSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_string_copy")
public fun codexAgentOperationStringCopy(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = withOperationValue<String>(context, operation, CodexAgentCOperationValueKind.STRING) {
    copyUtf8(it, buffer, capacity, outRequired)
}

@CName("codex_agent_operation_has_service_tier")
public fun codexAgentOperationHasServiceTier(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outHasServiceTier: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasServiceTier == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withOperationPayload(context, operation, CodexAgentCOperationValueKind.SERVICE_TIER) {
        if (it != null && it !is AgentServiceTier) return@withOperationPayload CODEX_AGENT_STATUS_INTERNAL_ERROR
        outHasServiceTier.pointed.value = if (it == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_operation_service_tier")
public fun codexAgentOperationServiceTier(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outServiceTier: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outServiceTier)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withOperationPayload(contextPointer, operation, CodexAgentCOperationValueKind.SERVICE_TIER) { value ->
        val tier = value as? AgentServiceTier ?: return@withOperationPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outServiceTier,
            createSnapshot(contextPointer, CodexAgentCServiceTierSnapshot(tier.copy())),
        )
    }
}

@CName("codex_agent_operation_skill_catalog")
public fun codexAgentOperationSkillCatalog(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentSkillCatalog>(
    context,
    operation,
    outCatalog,
    CodexAgentCOperationValueKind.SKILL_CATALOG,
) { CodexAgentCSkillCatalogSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_skill_chunk")
public fun codexAgentOperationSkillChunk(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outChunk: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentSkillChunk>(
    context,
    operation,
    outChunk,
    CodexAgentCOperationValueKind.SKILL_CHUNK,
) { CodexAgentCSkillChunkSnapshot(it.copy()) }

@CName("codex_agent_operation_skill")
public fun codexAgentOperationSkill(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentSkill>(
    context,
    operation,
    outSkill,
    CodexAgentCOperationValueKind.SKILL,
) { CodexAgentCSkillSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_hook_catalog")
public fun codexAgentOperationHookCatalog(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentHookCatalog>(
    context,
    operation,
    outCatalog,
    CodexAgentCOperationValueKind.HOOK_CATALOG,
) { CodexAgentCHookCatalogSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_hook")
public fun codexAgentOperationHook(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outHook: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentHook>(
    context,
    operation,
    outHook,
    CodexAgentCOperationValueKind.HOOK,
) { CodexAgentCHookSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_plugin_catalog")
public fun codexAgentOperationPluginCatalog(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCatalog: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentPluginCatalog>(
    context,
    operation,
    outCatalog,
    CodexAgentCOperationValueKind.PLUGIN_CATALOG,
) { CodexAgentCPluginCatalogSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_plugin_detail")
public fun codexAgentOperationPluginDetail(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outDetail: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentPluginDetail>(
    context,
    operation,
    outDetail,
    CodexAgentCOperationValueKind.PLUGIN_DETAIL,
) { CodexAgentCPluginDetailSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_plugin_install_result")
public fun codexAgentOperationPluginInstallResult(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outResult: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentPluginInstallResult>(
    context,
    operation,
    outResult,
    CodexAgentCOperationValueKind.PLUGIN_INSTALL_RESULT,
) { CodexAgentCPluginInstallResultSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_connectors_count")
public fun codexAgentOperationConnectorsCount(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = operationListCount(context, operation, outCount, CodexAgentCOperationValueKind.CONNECTORS)

@CName("codex_agent_operation_connector_at")
public fun codexAgentOperationConnectorAt(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    index: ULong,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = operationListItem<AgentConnector>(
    context,
    operation,
    index,
    outConnector,
    CodexAgentCOperationValueKind.CONNECTORS,
) { CodexAgentCConnectorSnapshot(it.operationCopy()) }

@CName("codex_agent_operation_mcp_servers_count")
public fun codexAgentOperationMcpServersCount(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = operationListCount(context, operation, outCount, CodexAgentCOperationValueKind.MCP_SERVERS)

@CName("codex_agent_operation_mcp_server_at")
public fun codexAgentOperationMcpServerAt(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    index: ULong,
    outServer: CPointer<COpaquePointerVar>?,
): Int = operationListItem<AgentMcpServer>(
    context,
    operation,
    index,
    outServer,
    CodexAgentCOperationValueKind.MCP_SERVERS,
) { CodexAgentCMcpServerSnapshot(it.cAbiOwnedCopy()) }

@CName("codex_agent_operation_mcp_server")
public fun codexAgentOperationMcpServer(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outServer: CPointer<COpaquePointerVar>?,
): Int = operationSnapshot<AgentMcpServer>(
    context,
    operation,
    outServer,
    CodexAgentCOperationValueKind.MCP_SERVER,
) { CodexAgentCMcpServerSnapshot(it.cAbiOwnedCopy()) }

private fun operationListCount(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
    kind: CodexAgentCOperationValueKind,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withOperationValue<List<*>>(context, operation, kind) {
        outCount.pointed.value = it.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : Any> operationListItem(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    index: ULong,
    output: CPointer<COpaquePointerVar>?,
    kind: CodexAgentCOperationValueKind,
    crossinline snapshot: (T) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withOperationValue<List<*>>(contextPointer, operation, kind) { values ->
        val value = values.itemAt(index) as? T ?: return@withOperationValue CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(output, createSnapshot(contextPointer, snapshot(value)))
    }
}

private inline fun <reified T : Any> operationSnapshot(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    kind: CodexAgentCOperationValueKind,
    crossinline snapshot: (T) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withOperationValue<T>(contextPointer, operation, kind) {
        installOutput(output, createSnapshot(contextPointer, snapshot(it)))
    }
}

private inline fun <reified T : Any> withOperationValue(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    kind: CodexAgentCOperationValueKind,
    crossinline block: (T) -> Int,
): Int = withOperationPayload(context, operation, kind) {
    val value = it as? T ?: return@withOperationPayload CODEX_AGENT_STATUS_INTERNAL_ERROR
    block(value)
}

private inline fun withOperationPayload(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    kind: CodexAgentCOperationValueKind,
    block: (Any?) -> Int,
): Int {
    val queried = queryCodexAgentCOperation(context, operation)
    if (queried.status != CODEX_AGENT_STATUS_OK) return queried.status
    val result = checkNotNull(queried.value)
    if (result.status != CODEX_AGENT_STATUS_OK) return result.status
    if (result.valueKind != kind) return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
    return block(result.value)
}

private fun List<*>.itemAt(index: ULong): Any? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())

private fun AgentConversationSummary.operationCopy(): AgentConversationSummary = copy(
    conversationId = ConversationId(conversationId.value),
)

private fun AgentConversation.operationCopy(): AgentConversation = AgentConversation(
    summary = summary.operationCopy(),
    messages = messages.map(AgentMessage::operationCopy),
)

private fun AgentMessage.operationCopy(): AgentMessage = copy(
    capabilities = capabilities.toSet(),
    invocations = invocations.map(AgentInvocation::operationCopy),
)

private fun AgentInvocation.operationCopy(): AgentInvocation = when (this) {
    is AgentInvocation.Plugin -> copy()
    is AgentInvocation.Skill -> copy()
}

private fun AgentModel.operationCopy(): AgentModel = copy(
    supportedEfforts = supportedEfforts.toList(),
    serviceTiers = serviceTiers.map { it.copy() },
)

private fun AgentSkill.operationCopy(): AgentSkill = copy(dependencies = dependencies.toList())

private fun AgentSkillCatalog.operationCopy(): AgentSkillCatalog = copy(
    skills = skills.map(AgentSkill::operationCopy),
    errors = errors.toList(),
)

private fun AgentHook.operationCopy(): AgentHook = copy(handler = handler.operationCopy())

private fun AgentHookHandler.operationCopy(): AgentHookHandler = when (this) {
    AgentHookHandler.Agent -> AgentHookHandler.Agent
    is AgentHookHandler.Command -> copy()
    is AgentHookHandler.McpTool -> copy()
    AgentHookHandler.Prompt -> AgentHookHandler.Prompt
}

private fun AgentHookCatalog.operationCopy(): AgentHookCatalog = copy(
    hooks = hooks.map(AgentHook::operationCopy),
    warnings = warnings.toList(),
    errors = errors.toList(),
)

private fun AgentPluginReference.operationCopy(): AgentPluginReference = copy()

private fun AgentPluginSkill.operationCopy(): AgentPluginSkill = copy()

private fun AgentConnector.operationCopy(): AgentConnector = copy(pluginNames = pluginNames.toList())

private fun AgentPluginSummary.operationCopy(): AgentPluginSummary = copy(
    reference = reference.operationCopy(),
    capabilities = capabilities.toList(),
)

private fun AgentPluginCatalog.operationCopy(): AgentPluginCatalog = copy(
    plugins = plugins.map(AgentPluginSummary::operationCopy),
    errors = errors.toList(),
)

private fun AgentPluginDetail.operationCopy(): AgentPluginDetail = copy(
    summary = summary.operationCopy(),
    skills = skills.map(AgentPluginSkill::operationCopy),
    connectors = connectors.map(AgentConnector::operationCopy),
    mcpServers = mcpServers.toList(),
)

private fun AgentPluginInstallResult.operationCopy(): AgentPluginInstallResult = copy(
    connectorsNeedingAuthentication = connectorsNeedingAuthentication.map(AgentConnector::operationCopy),
)
