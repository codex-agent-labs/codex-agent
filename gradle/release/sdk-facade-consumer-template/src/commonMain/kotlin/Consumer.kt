import io.github.codex_agent_labs.codexagent.agent.AgentInstallationScope
import io.github.codex_agent_labs.codexagent.agent.AgentPluginReference
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace

fun facadeValues(): List<String> {
    val client = CodexClientInfo("sdk_facade_consumer", "SDK facade consumer", "1.0")
    val workspace = CodexWorkspace("/workspace", "Workspace")
    val plugin = AgentPluginReference("plugin-id", "plugin", "marketplace")
    return listOf(
        client.name,
        client.title,
        client.version,
        workspace.path,
        workspace.displayName,
        plugin.id,
        plugin.name,
        plugin.marketplaceName,
        plugin.uri,
        AgentInstallationScope.User.name,
    )
}
