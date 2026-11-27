@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.CodexAgent
import io.github.codex_agent_labs.codexagent.agent.CodexAuthentication
import io.github.codex_agent_labs.codexagent.agent.CodexConnectors
import io.github.codex_agent_labs.codexagent.agent.CodexHooks
import io.github.codex_agent_labs.codexagent.agent.CodexIntegrationAuthorization
import io.github.codex_agent_labs.codexagent.agent.CodexInteractions
import io.github.codex_agent_labs.codexagent.agent.CodexMcpServers
import io.github.codex_agent_labs.codexagent.agent.CodexModels
import io.github.codex_agent_labs.codexagent.agent.CodexPlugins
import io.github.codex_agent_labs.codexagent.agent.CodexSkills
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal class CodexAgentCAuthentication(
    val core: CodexAuthentication,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCInteractions(
    val core: CodexInteractions,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCIntegrationAuthorization(
    val core: CodexIntegrationAuthorization,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCModels(
    val core: CodexModels,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCSkills(
    val core: CodexSkills,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCHooks(
    val core: CodexHooks,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCPlugins(
    val core: CodexPlugins,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCConnectors(
    val core: CodexConnectors,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

internal class CodexAgentCMcpServers(
    val core: CodexMcpServers,
    val owner: CodexAgent,
    val host: CodexAgentCHost,
)

@CName("codex_agent_agent_authentication")
public fun codexAgentAgentAuthentication(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outAuthentication: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outAuthentication) { wrapper, pointer, handle ->
    wrapper.projectAuthentication(pointer, handle)
}

@CName("codex_agent_agent_interactions")
public fun codexAgentAgentInteractions(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outInteractions: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outInteractions) { wrapper, pointer, handle ->
    wrapper.projectInteractions(pointer, handle)
}

@CName("codex_agent_agent_integration_authorization")
public fun codexAgentAgentIntegrationAuthorization(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outAuthorization: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outAuthorization) { wrapper, pointer, handle ->
    wrapper.projectIntegrationAuthorization(pointer, handle)
}

@CName("codex_agent_agent_models")
public fun codexAgentAgentModels(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outModels: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outModels) { wrapper, pointer, handle ->
    wrapper.projectModels(pointer, handle)
}

@CName("codex_agent_agent_skills")
public fun codexAgentAgentSkills(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outSkills: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outSkills) { wrapper, pointer, handle ->
    wrapper.projectSkills(pointer, handle)
}

@CName("codex_agent_agent_hooks")
public fun codexAgentAgentHooks(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outHooks: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outHooks) { wrapper, pointer, handle ->
    wrapper.projectHooks(pointer, handle)
}

@CName("codex_agent_agent_plugins")
public fun codexAgentAgentPlugins(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outPlugins: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outPlugins) { wrapper, pointer, handle ->
    wrapper.projectPlugins(pointer, handle)
}

@CName("codex_agent_agent_connectors")
public fun codexAgentAgentConnectors(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outConnectors: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outConnectors) { wrapper, pointer, handle ->
    wrapper.projectConnectors(pointer, handle)
}

@CName("codex_agent_agent_mcp_servers")
public fun codexAgentAgentMcpServers(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outMcpServers: CPointer<COpaquePointerVar>?,
): Int = projectAgentService(context, agent, outMcpServers) { wrapper, pointer, handle ->
    wrapper.projectMcpServers(pointer, handle)
}

@CName("codex_agent_agent_workspace")
public fun codexAgentAgentWorkspace(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outWorkspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outWorkspace)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAgent>(pointer, agent, CodexAgentCHandleKind.AGENT) { wrapper ->
        val workspace = wrapper.core.workspace
        installOutput(
            outWorkspace,
            createSnapshot(
                pointer,
                CodexAgentCWorkspaceSnapshot(CodexWorkspace(workspace.path, workspace.displayName)),
            ),
        )
    }
}

@CName("codex_agent_authentication_retain")
public fun codexAgentAuthenticationRetain(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    outAuthentication: CPointer<COpaquePointerVar>?,
): Int = retainService(context, authentication, outAuthentication, CodexAgentCHandleKind.AUTHENTICATION)

@CName("codex_agent_authentication_release")
public fun codexAgentAuthenticationRelease(
    context: COpaquePointer?,
    authentication: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, authentication, CodexAgentCHandleKind.AUTHENTICATION)

@CName("codex_agent_interactions_retain")
public fun codexAgentInteractionsRetain(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    outInteractions: CPointer<COpaquePointerVar>?,
): Int = retainService(context, interactions, outInteractions, CodexAgentCHandleKind.INTERACTIONS)

@CName("codex_agent_interactions_release")
public fun codexAgentInteractionsRelease(
    context: COpaquePointer?,
    interactions: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, interactions, CodexAgentCHandleKind.INTERACTIONS)

@CName("codex_agent_integration_authorization_retain")
public fun codexAgentIntegrationAuthorizationRetain(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    outAuthorization: CPointer<COpaquePointerVar>?,
): Int = retainService(
    context,
    authorization,
    outAuthorization,
    CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
)

@CName("codex_agent_integration_authorization_release")
public fun codexAgentIntegrationAuthorizationRelease(
    context: COpaquePointer?,
    authorization: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, authorization, CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION)

@CName("codex_agent_models_retain")
public fun codexAgentModelsRetain(
    context: COpaquePointer?,
    models: COpaquePointer?,
    outModels: CPointer<COpaquePointerVar>?,
): Int = retainService(context, models, outModels, CodexAgentCHandleKind.MODELS)

@CName("codex_agent_models_release")
public fun codexAgentModelsRelease(
    context: COpaquePointer?,
    models: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, models, CodexAgentCHandleKind.MODELS)

@CName("codex_agent_skills_retain")
public fun codexAgentSkillsRetain(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    outSkills: CPointer<COpaquePointerVar>?,
): Int = retainService(context, skills, outSkills, CodexAgentCHandleKind.SKILLS)

@CName("codex_agent_skills_release")
public fun codexAgentSkillsRelease(
    context: COpaquePointer?,
    skills: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, skills, CodexAgentCHandleKind.SKILLS)

@CName("codex_agent_hooks_retain")
public fun codexAgentHooksRetain(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    outHooks: CPointer<COpaquePointerVar>?,
): Int = retainService(context, hooks, outHooks, CodexAgentCHandleKind.HOOKS)

@CName("codex_agent_hooks_release")
public fun codexAgentHooksRelease(
    context: COpaquePointer?,
    hooks: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, hooks, CodexAgentCHandleKind.HOOKS)

@CName("codex_agent_plugins_retain")
public fun codexAgentPluginsRetain(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    outPlugins: CPointer<COpaquePointerVar>?,
): Int = retainService(context, plugins, outPlugins, CodexAgentCHandleKind.PLUGINS)

@CName("codex_agent_plugins_release")
public fun codexAgentPluginsRelease(
    context: COpaquePointer?,
    plugins: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, plugins, CodexAgentCHandleKind.PLUGINS)

@CName("codex_agent_connectors_retain")
public fun codexAgentConnectorsRetain(
    context: COpaquePointer?,
    connectors: COpaquePointer?,
    outConnectors: CPointer<COpaquePointerVar>?,
): Int = retainService(context, connectors, outConnectors, CodexAgentCHandleKind.CONNECTORS)

@CName("codex_agent_connectors_release")
public fun codexAgentConnectorsRelease(
    context: COpaquePointer?,
    connectors: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, connectors, CodexAgentCHandleKind.CONNECTORS)

@CName("codex_agent_mcp_servers_retain")
public fun codexAgentMcpServersRetain(
    context: COpaquePointer?,
    mcpServers: COpaquePointer?,
    outMcpServers: CPointer<COpaquePointerVar>?,
): Int = retainService(context, mcpServers, outMcpServers, CodexAgentCHandleKind.MCP_SERVERS)

@CName("codex_agent_mcp_servers_release")
public fun codexAgentMcpServersRelease(
    context: COpaquePointer?,
    mcpServers: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, mcpServers, CodexAgentCHandleKind.MCP_SERVERS)

@CName("codex_agent_skills_is_available")
public fun codexAgentSkillsIsAvailable(
    context: COpaquePointer?,
    skills: COpaquePointer?,
    outIsAvailable: CPointer<IntVar>?,
): Int = serviceAvailability<CodexAgentCSkills>(
    context,
    skills,
    outIsAvailable,
    CodexAgentCHandleKind.SKILLS,
) { it.core.isAvailable }

@CName("codex_agent_hooks_is_available")
public fun codexAgentHooksIsAvailable(
    context: COpaquePointer?,
    hooks: COpaquePointer?,
    outIsAvailable: CPointer<IntVar>?,
): Int = serviceAvailability<CodexAgentCHooks>(
    context,
    hooks,
    outIsAvailable,
    CodexAgentCHandleKind.HOOKS,
) { it.core.isAvailable }

@CName("codex_agent_plugins_is_available")
public fun codexAgentPluginsIsAvailable(
    context: COpaquePointer?,
    plugins: COpaquePointer?,
    outIsAvailable: CPointer<IntVar>?,
): Int = serviceAvailability<CodexAgentCPlugins>(
    context,
    plugins,
    outIsAvailable,
    CodexAgentCHandleKind.PLUGINS,
) { it.core.isAvailable }

@CName("codex_agent_connectors_is_available")
public fun codexAgentConnectorsIsAvailable(
    context: COpaquePointer?,
    connectors: COpaquePointer?,
    outIsAvailable: CPointer<IntVar>?,
): Int = serviceAvailability<CodexAgentCConnectors>(
    context,
    connectors,
    outIsAvailable,
    CodexAgentCHandleKind.CONNECTORS,
) { it.core.isAvailable }

@CName("codex_agent_mcp_servers_is_available")
public fun codexAgentMcpServersIsAvailable(
    context: COpaquePointer?,
    mcpServers: COpaquePointer?,
    outIsAvailable: CPointer<IntVar>?,
): Int = serviceAvailability<CodexAgentCMcpServers>(
    context,
    mcpServers,
    outIsAvailable,
    CodexAgentCHandleKind.MCP_SERVERS,
) { it.core.isAvailable }

private inline fun projectAgentService(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    project: (
        CodexAgentCAgent,
        COpaquePointer,
        COpaquePointer,
    ) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val agentPointer = agent ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAgent>(
        contextPointer,
        agentPointer,
        CodexAgentCHandleKind.AGENT,
    ) { wrapper ->
        installOutput(output, project(wrapper, contextPointer, agentPointer))
    }
}

private fun retainService(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    kind: CodexAgentCHandleKind,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(output, handleRegistry.retain(context, handle, kind))
}

private inline fun <reified T : Any> serviceAvailability(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<IntVar>?,
    kind: CodexAgentCHandleKind,
    available: (T) -> Boolean,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, kind) {
        output.pointed.value = if (available(it)) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}
