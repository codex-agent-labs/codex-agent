package io.github.codex_agent_labs.codexmobile.agent

import kotlinx.coroutines.flow.StateFlow

@CodexBindingApi
public class CodexAuthentication internal constructor(
    private val agent: CodexAgent,
) {
    public val state: StateFlow<AgentAuthenticationState> = agent.authenticationState
    public val isAuthenticated: StateFlow<Boolean> = agent.authenticationIsAuthenticated
    public val isAuthenticating: StateFlow<Boolean> = agent.authenticationIsAuthenticating

    @Throws(Exception::class)
    public suspend fun authenticate(
        method: CodexAuthenticationMethod = CodexAuthenticationMethod.ChatGptBrowser,
    ): Unit = agent.authenticate(method)

    @Throws(Exception::class)
    public suspend fun cancel(): Unit = agent.cancelAuthentication()

    @Throws(Exception::class)
    public suspend fun signOut(): Unit = agent.signOut()
}

@CodexBindingApi
public class CodexInteractions internal constructor(
    private val agent: CodexAgent,
) {
    public val state: StateFlow<AgentInteractionState> = agent.interactionState
    public val approvals: StateFlow<List<AgentPendingApproval>> = agent.pendingApprovals
    public val elicitations: StateFlow<List<AgentPendingElicitation>> = agent.pendingElicitations

    @Throws(Exception::class)
    public suspend fun resolve(
        approval: AgentPendingApproval,
        decision: AgentApprovalDecision,
    ): Unit = agent.resolveApproval(approval, decision)

    @Throws(Exception::class)
    public suspend fun resolve(
        elicitation: AgentPendingElicitation,
        response: AgentElicitationResponse,
    ): Unit = agent.resolveElicitation(elicitation, response)

    @Throws(Exception::class)
    public suspend fun openUrl(elicitation: AgentPendingElicitation): Unit =
        agent.openElicitationUrl(elicitation)
}

@CodexBindingApi
public class CodexIntegrationAuthorization internal constructor(
    private val agent: CodexAgent,
) {
    public val state: StateFlow<AgentIntegrationAuthorizationState> = agent.integrationAuthorizationState
    public val active: StateFlow<AgentIntegration?> = agent.activeIntegrationAuthorization
    public val isAuthorizing: StateFlow<Boolean> = agent.integrationAuthorizationIsAuthorizing

    @Throws(Exception::class)
    public suspend fun <T : AgentIntegration> authorize(target: T): Unit = when (target) {
        is AgentIntegration.Connector -> agent.authorizeConnector(target.connector)
        is AgentIntegration.McpServer -> agent.authorizeMcpServer(target.server)
    }

    @Throws(Exception::class)
    public suspend fun cancel(): Unit = agent.cancelIntegrationAuthorization()
}

@CodexBindingApi
public class CodexConversations internal constructor(
    private val agent: CodexAgent,
) {
    public val active: StateFlow<CodexConversation?> = agent.activeConversation

    @Throws(Exception::class)
    public suspend fun list(): List<AgentConversationSummary> = agent.listConversations()

    @Throws(Exception::class)
    public suspend fun read(id: ConversationId): AgentConversation = agent.readConversation(id)

    @Throws(Exception::class)
    public suspend fun rename(id: ConversationId, name: String): Unit = agent.renameConversation(id, name)

    @Throws(Exception::class)
    public suspend fun delete(id: ConversationId): Unit = agent.deleteConversation(id)

    @Throws(Exception::class)
    public suspend fun open(
        conversationId: ConversationId? = null,
        settings: AgentConversationSettings = AgentConversationSettings(),
    ): CodexConversation = agent.openConversation(conversationId, settings)
}

@CodexBindingApi
public class CodexModels internal constructor(
    private val agent: CodexAgent,
) {
    @Throws(Exception::class)
    public suspend fun list(): List<AgentModel> = agent.listModels()

    @Throws(Exception::class)
    public suspend fun resolve(
        resolution: AgentResolution = AgentResolution.Preferred,
    ): AgentModel {
        val models = list()
        if (models.isEmpty()) throw AgentModelUnavailableException()
        val preferredId = if (resolution == AgentResolution.Preferred) agent.modelPreferences().modelId else null
        return models.resolveModel(resolution, preferredId)
    }

    @Throws(Exception::class)
    public suspend fun resolveEffort(
        model: AgentModel,
        resolution: AgentResolution = AgentResolution.Preferred,
    ): String = model.resolveEffort(
        resolution,
        if (resolution == AgentResolution.Preferred) agent.modelPreferences().effort else null,
    )

    @Throws(Exception::class)
    public suspend fun resolveServiceTier(
        model: AgentModel,
        resolution: AgentResolution = AgentResolution.Preferred,
    ): AgentServiceTier? = model.resolveServiceTier(
        resolution,
        if (resolution == AgentResolution.Preferred) agent.modelPreferences().serviceTierId else null,
    )
}

@CodexBindingApi
public class CodexSkills internal constructor(
    private val agent: CodexAgent,
) {
    public val isAvailable: Boolean get() = agent.supports(CodexRuntimeFeature.SKILLS)

    @Throws(Exception::class)
    public suspend fun list(forceReload: Boolean = false): AgentSkillCatalog = agent.listSkills(forceReload)

    @Throws(Exception::class)
    public suspend fun read(path: String, offset: Long = 0): AgentSkillChunk = agent.readSkill(path, offset)

    @Throws(Exception::class)
    public suspend fun install(directory: String, scope: AgentInstallationScope): AgentSkill =
        agent.installSkill(directory, scope)

    @Throws(Exception::class)
    public suspend fun uninstall(skill: AgentSkill): Unit = agent.uninstallSkill(skill)
}

@CodexBindingApi
public class CodexHooks internal constructor(
    private val agent: CodexAgent,
) {
    public val isAvailable: Boolean get() = agent.supports(CodexRuntimeFeature.HOOKS)

    @Throws(Exception::class)
    public suspend fun list(): AgentHookCatalog = agent.listHooks()

    @Throws(Exception::class)
    public suspend fun install(directory: String, scope: AgentInstallationScope): AgentHook =
        agent.installHook(directory, scope)

    @Throws(Exception::class)
    public suspend fun uninstall(hook: AgentHook): Unit = agent.uninstallHook(hook)

    @Throws(Exception::class)
    public suspend fun trust(hook: AgentHook): Unit = agent.trustHook(hook)
}

@CodexBindingApi
public class CodexPlugins internal constructor(
    private val agent: CodexAgent,
) {
    public val isAvailable: Boolean get() = agent.supports(CodexRuntimeFeature.PLUGINS)

    @Throws(Exception::class)
    public suspend fun list(forceReload: Boolean = false): AgentPluginCatalog = agent.listPlugins(forceReload)

    @Throws(Exception::class)
    public suspend fun read(plugin: AgentPluginReference): AgentPluginDetail = agent.readPlugin(plugin)

    @Throws(Exception::class)
    public suspend fun install(plugin: AgentPluginReference): AgentPluginInstallResult = agent.installPlugin(plugin)

    @Throws(Exception::class)
    public suspend fun uninstall(plugin: AgentPluginReference): Unit = agent.uninstallPlugin(plugin)
}

@CodexBindingApi
public class CodexConnectors internal constructor(
    private val agent: CodexAgent,
) {
    public val isAvailable: Boolean get() = agent.supports(CodexRuntimeFeature.CONNECTORS)

    @Throws(Exception::class)
    public suspend fun list(forceReload: Boolean = false): List<AgentConnector> =
        agent.listConnectors(forceReload)
}

@CodexBindingApi
public class CodexMcpServers internal constructor(
    private val agent: CodexAgent,
) {
    public val isAvailable: Boolean get() = agent.supports(CodexRuntimeFeature.MCP_SERVERS)

    @Throws(Exception::class)
    public suspend fun list(): List<AgentMcpServer> = agent.listMcpServers()

    @Throws(Exception::class)
    public suspend fun add(configuration: AgentMcpServerConfiguration): AgentMcpServer =
        agent.addMcpServer(configuration)

    @Throws(Exception::class)
    public suspend fun remove(server: AgentMcpServer): Unit = agent.removeMcpServer(server)
}

internal data class AgentModelPreferences(
    val modelId: String?,
    val effort: String?,
    val serviceTierId: String?,
)
