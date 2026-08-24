import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentHook
import io.github.codex_agent_labs.codexmobile.agent.AgentInteractionState
import io.github.codex_agent_labs.codexmobile.agent.AgentInstallationScope
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingInteraction
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.isResolving
import kotlinx.coroutines.CoroutineScope

fun publicHost(
    platform: CodexPlatform,
    clientInfo: CodexClientInfo,
): CodexHost = CodexHost(platform, clientInfo)

fun scopedPublicHost(
    platform: CodexPlatform,
    scope: CoroutineScope,
    clientInfo: CodexClientInfo,
): CodexHost = CodexHost(platform, scope, clientInfo)

fun readyAgent(host: CodexHost): CodexAgent? =
    (host.lifecycleState.value as? CodexHostState.Ready)?.agent

suspend fun openConversation(agent: CodexAgent): CodexConversation =
    agent.conversations.open()

fun supportsSkills(agent: CodexAgent): Boolean = agent.skills.isAvailable

fun conversationActions(state: AgentConversationState): Triple<Boolean, Boolean, Boolean> =
    Triple(state.canStartTurn, state.canReload, state.canCancelTurn)

fun convenienceFlags(
    agent: CodexAgent,
    conversation: CodexConversation,
    mcpServer: AgentMcpServer,
    hook: AgentHook,
    interactions: AgentInteractionState,
    interaction: AgentPendingInteraction,
): List<Boolean> = listOf(
    agent.authentication.isAuthenticated.value,
    agent.authentication.isAuthenticating.value,
    conversation.isTurnActive.value,
    agent.integrationAuthorization.isAuthorizing.value,
    mcpServer.isAuthorized,
    hook.canTrust,
    interactions.isResolving(interaction),
)

suspend fun installExtensions(
    agent: CodexAgent,
    skillDirectory: String,
    hookDirectory: String,
    plugin: AgentPluginReference,
) {
    agent.skills.install(skillDirectory, AgentInstallationScope.User)
    val hook = agent.hooks.install(hookDirectory, AgentInstallationScope.User)
    agent.hooks.trust(hook)
    agent.plugins.install(plugin)
}

suspend fun uninstallExtensions(
    agent: CodexAgent,
    skill: AgentSkill,
    hook: AgentHook,
    plugin: AgentPluginSummary,
) {
    agent.skills.uninstall(skill)
    agent.hooks.uninstall(hook)
    agent.plugins.uninstall(plugin.reference)
}

suspend fun send(
    conversation: CodexConversation,
    prompt: String,
    request: AgentTurnRequest,
) {
    conversation.send(prompt)
    conversation.send(request)
}
