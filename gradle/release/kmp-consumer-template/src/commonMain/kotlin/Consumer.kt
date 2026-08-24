import io.github.codex_agent_labs.codexagent.agent.AgentConversationState
import io.github.codex_agent_labs.codexagent.agent.AgentHook
import io.github.codex_agent_labs.codexagent.agent.AgentPluginSummary
import io.github.codex_agent_labs.codexagent.agent.AgentSkill
import io.github.codex_agent_labs.codexagent.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexagent.agent.CodexAgent
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexConversation
import io.github.codex_agent_labs.codexagent.agent.CodexHost
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexPlatform
import io.github.codex_agent_labs.codexagent.agent.CodexRuntimeFeature
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

fun readyAgent(state: CodexHostState): CodexAgent? =
    (state as? CodexHostState.Ready)?.agent

suspend fun openConversation(agent: CodexAgent): CodexConversation =
    agent.openConversation()

fun supports(agent: CodexAgent, feature: CodexRuntimeFeature): Boolean =
    feature in agent.features

fun conversationActions(state: AgentConversationState): Triple<Boolean, Boolean, Boolean> =
    Triple(state.canStartTurn, state.canReload, state.canCancelTurn)

suspend fun mutateExtensions(
    agent: CodexAgent,
    skill: AgentSkill,
    hook: AgentHook,
    plugin: AgentPluginSummary,
) {
    agent.setSkillEnabled(skill, isEnabled = true)
    agent.setHookEnabled(hook, isEnabled = true)
    agent.trustHook(hook)
    agent.setPluginEnabled(plugin, isEnabled = true)
}

suspend fun send(
    conversation: CodexConversation,
    prompt: String,
    request: AgentTurnRequest,
) {
    conversation.send(prompt)
    conversation.send(request)
}
