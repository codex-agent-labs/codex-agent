@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentHook
import io.github.codex_agent_labs.codexmobile.agent.AgentHookCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler
import io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope
import io.github.codex_agent_labs.codexmobile.agent.AgentModel
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginDetail
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginInstallResult
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentResolution
import io.github.codex_agent_labs.codexmobile.agent.AgentSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillCatalog
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillChunk
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.pointed

@CName("codex_agent_models_list")
public fun codexAgentModelsList(
    context: COpaquePointer?,
    models: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCModels>(
    context, models, CodexAgentCHandleKind.MODELS, callback, userData, outOperation,
    runtime = { it.host.runtime },
) { target -> catalogResult(CodexAgentCOperationValueKind.MODELS, target.core.list().map(AgentModel::catalogCopy)) }

@CName("codex_agent_models_resolve")
public fun codexAgentModelsResolve(
    context: COpaquePointer?,
    models: COpaquePointer?,
    resolution: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedResolution = resolution.catalogResolution()
    startCodexAgentCTargetOperation<CodexAgentCModels>(
        context, models, CodexAgentCHandleKind.MODELS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target -> catalogResult(CodexAgentCOperationValueKind.MODEL, target.core.resolve(copiedResolution).catalogCopy()) }
}

@CName("codex_agent_models_resolve_effort")
public fun codexAgentModelsResolveEffort(
    context: COpaquePointer?,
    models: COpaquePointer?,
    model: COpaquePointer?,
    resolution: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedModel = copyCatalogInput<CodexAgentCModelSnapshot, AgentModel>(context, model) {
        it.value.catalogCopy()
    }
    if (copiedModel.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedModel.status
    val copiedResolution = resolution.catalogResolution()
    startCodexAgentCTargetOperation<CodexAgentCModels>(
        context, models, CodexAgentCHandleKind.MODELS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.STRING,
            target.core.resolveEffort(checkNotNull(copiedModel.value), copiedResolution),
        )
    }
}

@CName("codex_agent_models_resolve_service_tier")
public fun codexAgentModelsResolveServiceTier(
    context: COpaquePointer?,
    models: COpaquePointer?,
    model: COpaquePointer?,
    resolution: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedModel = copyCatalogInput<CodexAgentCModelSnapshot, AgentModel>(context, model) {
        it.value.catalogCopy()
    }
    if (copiedModel.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedModel.status
    val copiedResolution = resolution.catalogResolution()
    startCodexAgentCTargetOperation<CodexAgentCModels>(
        context, models, CodexAgentCHandleKind.MODELS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.SERVICE_TIER,
            target.core.resolveServiceTier(checkNotNull(copiedModel.value), copiedResolution)?.copy(),
        )
    }
}

@CName("codex_agent_skills_list")
public fun codexAgentSkillsList(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    forceReload: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedForceReload = forceReload.catalogBoolean()
    startCodexAgentCTargetOperation<CodexAgentCSkills>(
        context, skills, CodexAgentCHandleKind.SKILLS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.SKILL_CATALOG,
            target.core.list(copiedForceReload).catalogCopy(),
        )
    }
}

@CName("codex_agent_skills_read")
public fun codexAgentSkillsRead(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    path: CPointer<codex_agent_string_view>?,
    offset: Long,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedPath = path.catalogString()
    startCodexAgentCTargetOperation<CodexAgentCSkills>(
        context, skills, CodexAgentCHandleKind.SKILLS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(CodexAgentCOperationValueKind.SKILL_CHUNK, target.core.read(copiedPath, offset).copy())
    }
}

@CName("codex_agent_skills_install")
public fun codexAgentSkillsInstall(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    directory: CPointer<codex_agent_string_view>?,
    scope: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedDirectory = directory.catalogString()
    val copiedScope = scope.catalogInstallationScope()
    startCodexAgentCTargetOperation<CodexAgentCSkills>(
        context, skills, CodexAgentCHandleKind.SKILLS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.SKILL,
            target.core.install(copiedDirectory, copiedScope).catalogCopy(),
        )
    }
}

@CName("codex_agent_skills_uninstall")
public fun codexAgentSkillsUninstall(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    skill: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copied = copyCatalogInput<CodexAgentCSkillSnapshot, AgentSkill>(context, skill) { it.value.catalogCopy() }
    if (copied.status != CODEX_AGENT_STATUS_OK) return@abiStatus copied.status
    startCodexAgentCTargetOperation<CodexAgentCSkills>(
        context, skills, CodexAgentCHandleKind.SKILLS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target -> target.core.uninstall(checkNotNull(copied.value)); catalogUnitResult() }
}

@CName("codex_agent_hooks_list")
public fun codexAgentHooksList(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCHooks>(
    context, hooks, CodexAgentCHandleKind.HOOKS, callback, userData, outOperation,
    runtime = { it.host.runtime },
) { target -> catalogResult(CodexAgentCOperationValueKind.HOOK_CATALOG, target.core.list().catalogCopy()) }

@CName("codex_agent_hooks_install")
public fun codexAgentHooksInstall(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    directory: CPointer<codex_agent_string_view>?,
    scope: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedDirectory = directory.catalogString()
    val copiedScope = scope.catalogInstallationScope()
    startCodexAgentCTargetOperation<CodexAgentCHooks>(
        context, hooks, CodexAgentCHandleKind.HOOKS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.HOOK,
            target.core.install(copiedDirectory, copiedScope).catalogCopy(),
        )
    }
}

@CName("codex_agent_hooks_uninstall")
public fun codexAgentHooksUninstall(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    hook: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startHookUnitOperation(context, hooks, hook, callback, userData, outOperation) { target, copied ->
    target.core.uninstall(copied)
}

@CName("codex_agent_hooks_trust")
public fun codexAgentHooksTrust(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    hook: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startHookUnitOperation(context, hooks, hook, callback, userData, outOperation) { target, copied ->
    target.core.trust(copied)
}

@CName("codex_agent_plugins_list")
public fun codexAgentPluginsList(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    forceReload: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedForceReload = forceReload.catalogBoolean()
    startCodexAgentCTargetOperation<CodexAgentCPlugins>(
        context, plugins, CodexAgentCHandleKind.PLUGINS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.PLUGIN_CATALOG,
            target.core.list(copiedForceReload).catalogCopy(),
        )
    }
}

@CName("codex_agent_plugins_read")
public fun codexAgentPluginsRead(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    plugin: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startPluginOperation(
    context, plugins, plugin, callback, userData, outOperation, CodexAgentCOperationValueKind.PLUGIN_DETAIL,
) { target, copied -> target.core.read(copied).catalogCopy() }

@CName("codex_agent_plugins_install")
public fun codexAgentPluginsInstall(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    plugin: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startPluginOperation(
    context, plugins, plugin, callback, userData, outOperation, CodexAgentCOperationValueKind.PLUGIN_INSTALL_RESULT,
) { target, copied -> target.core.install(copied).catalogCopy() }

@CName("codex_agent_plugins_uninstall")
public fun codexAgentPluginsUninstall(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    plugin: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startPluginOperation(
    context, plugins, plugin, callback, userData, outOperation, CodexAgentCOperationValueKind.NONE,
) { target, copied -> target.core.uninstall(copied); null }

@CName("codex_agent_connectors_list")
public fun codexAgentConnectorsList(
    context: COpaquePointer?,
    connectors: COpaquePointer?,
    forceReload: Int,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copiedForceReload = forceReload.catalogBoolean()
    startCodexAgentCTargetOperation<CodexAgentCConnectors>(
        context, connectors, CodexAgentCHandleKind.CONNECTORS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.CONNECTORS,
            target.core.list(copiedForceReload).map(AgentConnector::catalogCopy),
        )
    }
}

@CName("codex_agent_mcp_servers_list")
public fun codexAgentMcpServersList(
    context: COpaquePointer?,
    mcpServers: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCMcpServers>(
    context, mcpServers, CodexAgentCHandleKind.MCP_SERVERS, callback, userData, outOperation,
    runtime = { it.host.runtime },
) { target ->
    catalogResult(CodexAgentCOperationValueKind.MCP_SERVERS, target.core.list().map { it.cAbiOwnedCopy() })
}

@CName("codex_agent_mcp_servers_add")
public fun codexAgentMcpServersAdd(
    context: COpaquePointer?,
    mcpServers: COpaquePointer?,
    configuration: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copied = copyCatalogInput<CodexAgentCMcpServerConfigurationSnapshot, io.github.codex_agent_labs.codexmobile.agent.AgentMcpServerConfiguration>(
        context,
        configuration,
    ) { it.value.cAbiOwnedCopy() }
    if (copied.status != CODEX_AGENT_STATUS_OK) return@abiStatus copied.status
    startCodexAgentCTargetOperation<CodexAgentCMcpServers>(
        context, mcpServers, CodexAgentCHandleKind.MCP_SERVERS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target ->
        catalogResult(
            CodexAgentCOperationValueKind.MCP_SERVER,
            target.core.add(checkNotNull(copied.value)).cAbiOwnedCopy(),
        )
    }
}

@CName("codex_agent_mcp_servers_remove")
public fun codexAgentMcpServersRemove(
    context: COpaquePointer?,
    mcpServers: COpaquePointer?,
    server: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val copied = copyCatalogInput<CodexAgentCMcpServerSnapshot, io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer>(
        context,
        server,
    ) { it.value.cAbiOwnedCopy() }
    if (copied.status != CODEX_AGENT_STATUS_OK) return@abiStatus copied.status
    startCodexAgentCTargetOperation<CodexAgentCMcpServers>(
        context, mcpServers, CodexAgentCHandleKind.MCP_SERVERS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target -> target.core.remove(checkNotNull(copied.value)); catalogUnitResult() }
}

private fun startHookUnitOperation(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    hook: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    execute: suspend (CodexAgentCHooks, AgentHook) -> Unit,
): Int = abiStatus {
    val copied = copyCatalogInput<CodexAgentCHookSnapshot, AgentHook>(context, hook) { it.value.catalogCopy() }
    if (copied.status != CODEX_AGENT_STATUS_OK) return@abiStatus copied.status
    startCodexAgentCTargetOperation<CodexAgentCHooks>(
        context, hooks, CodexAgentCHandleKind.HOOKS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target -> execute(target, checkNotNull(copied.value)); catalogUnitResult() }
}

private fun startPluginOperation(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    plugin: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    valueKind: CodexAgentCOperationValueKind,
    execute: suspend (CodexAgentCPlugins, AgentPluginReference) -> Any?,
): Int = abiStatus {
    val copied = copyCatalogInput<CodexAgentCPluginReferenceSnapshot, AgentPluginReference>(context, plugin) {
        it.value.copy()
    }
    if (copied.status != CODEX_AGENT_STATUS_OK) return@abiStatus copied.status
    startCodexAgentCTargetOperation<CodexAgentCPlugins>(
        context, plugins, CodexAgentCHandleKind.PLUGINS, callback, userData, outOperation,
        runtime = { it.host.runtime },
    ) { target -> catalogResult(valueKind, execute(target, checkNotNull(copied.value))) }
}

private inline fun <reified S : CodexAgentCSnapshot, T : Any> copyCatalogInput(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    crossinline copy: (S) -> T,
): CodexAgentCRegistryResult<T> {
    var copied: T? = null
    val status = withPayload<S>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copied = copy(it)
        CODEX_AGENT_STATUS_OK
    }
    return CodexAgentCRegistryResult(status, copied.takeIf { status == CODEX_AGENT_STATUS_OK })
}

private fun catalogResult(kind: CodexAgentCOperationValueKind, value: Any?): CodexAgentCOperationResult =
    CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK, valueKind = kind, value = value)

private fun catalogUnitResult(): CodexAgentCOperationResult = catalogResult(CodexAgentCOperationValueKind.NONE, null)

private fun Int.catalogBoolean(): Boolean {
    require(this == 0 || this == 1)
    return this == 1
}

private fun Int.catalogResolution(): AgentResolution = when (this) {
    0 -> AgentResolution.Preferred
    1 -> AgentResolution.Default
    2 -> AgentResolution.First
    else -> throw IllegalArgumentException("Invalid model resolution")
}

private fun Int.catalogInstallationScope(): AgentInstallationScope = when (this) {
    0 -> AgentInstallationScope.User
    1 -> AgentInstallationScope.Workspace
    else -> throw IllegalArgumentException("Invalid installation scope")
}

private fun CPointer<codex_agent_string_view>?.catalogString(): String = requireNotNull(this).pointed.readUtf8()

private fun AgentModel.catalogCopy(): AgentModel = copy(
    supportedEfforts = supportedEfforts.toList(),
    serviceTiers = serviceTiers.map { it.copy() },
)

private fun AgentSkill.catalogCopy(): AgentSkill = copy(dependencies = dependencies.toList())

private fun AgentSkillCatalog.catalogCopy(): AgentSkillCatalog = copy(
    skills = skills.map(AgentSkill::catalogCopy),
    errors = errors.toList(),
)

private fun AgentHookHandler.catalogCopy(): AgentHookHandler = when (this) {
    AgentHookHandler.Agent -> AgentHookHandler.Agent
    is AgentHookHandler.Command -> copy()
    is AgentHookHandler.McpTool -> copy()
    AgentHookHandler.Prompt -> AgentHookHandler.Prompt
}

private fun AgentHook.catalogCopy(): AgentHook = copy(handler = handler.catalogCopy())

private fun AgentHookCatalog.catalogCopy(): AgentHookCatalog = copy(
    hooks = hooks.map(AgentHook::catalogCopy),
    warnings = warnings.toList(),
    errors = errors.toList(),
)

private fun AgentConnector.catalogCopy(): AgentConnector = copy(pluginNames = pluginNames.toList())

private fun AgentPluginSummary.catalogCopy(): AgentPluginSummary = copy(
    reference = reference.copy(),
    capabilities = capabilities.toList(),
)

private fun AgentPluginCatalog.catalogCopy(): AgentPluginCatalog = copy(
    plugins = plugins.map(AgentPluginSummary::catalogCopy),
    errors = errors.toList(),
)

private fun AgentPluginDetail.catalogCopy(): AgentPluginDetail = copy(
    summary = summary.catalogCopy(),
    skills = skills.map { it.copy() },
    connectors = connectors.map(AgentConnector::catalogCopy),
    mcpServers = mcpServers.toList(),
)

private fun AgentPluginInstallResult.catalogCopy(): AgentPluginInstallResult = copy(
    connectorsNeedingAuthentication = connectorsNeedingAuthentication.map(AgentConnector::catalogCopy),
)
