package io.github.codex_agent_labs.codexagent.agent

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

public class CodexAgent internal constructor(
    public val workspace: CodexWorkspace,
    private val workingDirectory: String,
    features: Set<CodexRuntimeFeature>,
    private val client: CodexAgentClient,
    parentScope: CoroutineScope,
    authorizationBrowser: CodexAuthorizationBrowser,
) {
    private val lock = Mutex()
    private val scope = CoroutineScope(
        parentScope.coroutineContext + SupervisorJob(parentScope.coroutineContext[Job]),
    )
    private val authenticationController = AuthenticationController(client, scope, authorizationBrowser)
    private val interactionController = InteractionController(client, scope, authorizationBrowser)
    private val integrationAuthorizationController =
        IntegrationAuthorizationController(client, scope, authorizationBrowser)
    private val mutableActiveConversation = MutableStateFlow<CodexConversation?>(null)
    private var conversationGeneration = 0L
    private var signingOut = false
    private var closed = false

    private val runtimeFeatures: Set<CodexRuntimeFeature> = features.toSet()
    internal val authenticationState: StateFlow<AgentAuthenticationState> = authenticationController.state
    internal val interactionState: StateFlow<AgentInteractionState> = interactionController.state
    internal val pendingApprovals: StateFlow<List<AgentPendingApproval>> = interactionController.approvals
    internal val pendingElicitations: StateFlow<List<AgentPendingElicitation>> = interactionController.elicitations
    internal val integrationAuthorizationState: StateFlow<AgentIntegrationAuthorizationState> =
        integrationAuthorizationController.state
    internal val activeIntegrationAuthorization: StateFlow<AgentIntegration?> =
        integrationAuthorizationController.active
    internal val activeConversation: StateFlow<CodexConversation?> =
        mutableActiveConversation.asStateFlow()

    public val authentication: CodexAuthentication = CodexAuthentication(this)
    public val interactions: CodexInteractions = CodexInteractions(this)
    public val integrationAuthorization: CodexIntegrationAuthorization = CodexIntegrationAuthorization(this)
    public val conversations: CodexConversations = CodexConversations(this)
    public val models: CodexModels = CodexModels(this)
    public val skills: CodexSkills = CodexSkills(this)
    public val hooks: CodexHooks = CodexHooks(this)
    public val plugins: CodexPlugins = CodexPlugins(this)
    public val connectors: CodexConnectors = CodexConnectors(this)
    public val mcpServers: CodexMcpServers = CodexMcpServers(this)

    internal suspend fun start(): Unit = client.start()

    @Throws(Exception::class)
    internal suspend fun authenticate(
        method: CodexAuthenticationMethod = CodexAuthenticationMethod.ChatGptBrowser,
    ): Unit {
        requireOpen()
        authenticationController.authenticate(method)
    }

    @Throws(Exception::class)
    internal suspend fun cancelAuthentication(): Unit {
        requireOpen()
        authenticationController.cancel()
    }

    @Throws(Exception::class)
    internal suspend fun signOut(): Unit {
        val conversation = lock.withLock {
            checkOpenLocked()
            check(!signingOut) { "Sign-out is already in progress" }
            signingOut = true
            conversationGeneration += 1
            mutableActiveConversation.value.also { mutableActiveConversation.value = null }
        }
        var failure: Throwable? = null
        try {
            withContext(NonCancellable) {
                try {
                    completeCleanup(
                        listOf(
                            { conversation?.let { releaseConversation(it) } },
                            { authenticationController.signOut() },
                        ),
                    )
                } catch (error: Throwable) {
                    failure = error
                }
            }
            failure?.let {
                throw it.asCodexOperationException("authentication_failed", "Could not sign out")
            }
            currentCoroutineContext().ensureActive()
        } finally {
            withContext(NonCancellable) {
                lock.withLock {
                    if (!closed) signingOut = false
                }
            }
        }
    }

    @Throws(Exception::class)
    internal suspend fun resolveApproval(
        approval: AgentPendingApproval,
        decision: AgentApprovalDecision,
    ): Unit {
        requireOpen()
        interactionController.resolveApproval(approval, decision)
    }

    @Throws(Exception::class)
    internal suspend fun resolveElicitation(
        elicitation: AgentPendingElicitation,
        response: AgentElicitationResponse,
    ): Unit {
        requireOpen()
        interactionController.resolveElicitation(elicitation, response)
    }

    @Throws(Exception::class)
    internal suspend fun openElicitationUrl(elicitation: AgentPendingElicitation): Unit {
        requireOpen()
        interactionController.openUrl(elicitation)
    }

    @Throws(Exception::class)
    internal suspend fun listConversations(): List<AgentConversationSummary> {
        requireOpen()
        return codexOperation("conversation_list_failed", "Could not list conversations") {
            client.listConversations()
        }
    }

    @Throws(Exception::class)
    internal suspend fun readConversation(conversationId: ConversationId): AgentConversation {
        requireOpen()
        return codexOperation("conversation_read_failed", "Could not read conversation") {
            client.readConversation(conversationId)
        }
    }

    @Throws(Exception::class)
    internal suspend fun renameConversation(conversationId: ConversationId, name: String): Unit {
        requireOpen()
        require(name.isNotBlank()) { "Conversation name must not be blank" }
        codexOperation("conversation_rename_failed", "Could not rename conversation") {
            client.renameConversation(conversationId, name)
        }
    }

    @Throws(Exception::class)
    internal suspend fun deleteConversation(conversationId: ConversationId): Unit {
        requireOpen()
        mutableActiveConversation.value
            ?.takeIf { it.state.value.conversationId == conversationId }
            ?.close()
        requireOpen()
        codexOperation("conversation_delete_failed", "Could not delete conversation") {
            client.deleteConversation(conversationId)
        }
    }

    @Throws(Exception::class)
    internal suspend fun openConversation(
        conversationId: ConversationId? = null,
        settings: AgentConversationSettings = AgentConversationSettings(),
    ): CodexConversation {
        val transition = lock.withLock {
            checkOpenLocked()
            check(!signingOut) { "Sign-out is in progress" }
            val conversation = CodexConversation(
                client = client,
                scope = scope,
                workingDirectory = workingDirectory,
                features = runtimeFeatures,
                onClose = ::closeConversation,
            )
            conversationGeneration += 1
            val previous = mutableActiveConversation.value
            mutableActiveConversation.value = conversation
            ConversationTransition(conversationGeneration, previous, conversation)
        }
        val conversation = transition.conversation

        var openedId: ConversationId? = null
        try {
            withContext(NonCancellable) {
                transition.previous?.let { releaseConversation(it) }
            }
            currentCoroutineContext().ensureActive()
            val mayOpen = lock.withLock {
                !closed &&
                    mutableActiveConversation.value === conversation &&
                    conversationGeneration == transition.generation &&
                    !signingOut
            }
            if (!mayOpen) throw CancellationException("Conversation opening was superseded")
            openedId = conversation.open(conversationId, settings)
        } catch (error: Throwable) {
            withContext(NonCancellable) {
                lock.withLock {
                    if (mutableActiveConversation.value === conversation) {
                        mutableActiveConversation.value = null
                    }
                }
                try {
                    releaseConversation(conversation, openedId ?: conversation.state.value.conversationId)
                } catch (_: Throwable) {
                    // Preserve the failure that prevented the conversation from opening.
                }
            }
            if (error is CancellationException || error is CodexOperationException) throw error
            throw error.asCodexOperationException("open_failed", "Could not open conversation")
        }

        val accepted = withContext(NonCancellable) {
            lock.withLock {
                !closed &&
                    mutableActiveConversation.value === conversation &&
                    conversationGeneration == transition.generation &&
                    !signingOut
            }
        }
        if (!accepted) {
            withContext(NonCancellable) { releaseConversation(conversation, openedId) }
            throw CancellationException("Conversation opening was superseded")
        }
        try {
            currentCoroutineContext().ensureActive()
        } catch (error: CancellationException) {
            withContext(NonCancellable) {
                lock.withLock {
                    if (mutableActiveConversation.value === conversation) {
                        conversationGeneration += 1
                        mutableActiveConversation.value = null
                    }
                }
                releaseConversation(conversation, openedId)
            }
            throw error
        }
        return conversation
    }

    @Throws(Exception::class)
    internal suspend fun listModels(): List<AgentModel> {
        requireOpen()
        return codexOperation("model_list_failed", "Could not list models") { client.listModels() }
    }

    internal suspend fun modelPreferences(): AgentModelPreferences {
        requireOpen()
        return codexOperation("model_preferences_failed", "Could not read model preferences") {
            client.readModelPreferences(workingDirectory)
        }
    }

    @Throws(Exception::class)
    internal suspend fun listSkills(forceReload: Boolean = false): AgentSkillCatalog {
        requireOpen()
        requireFeature(CodexRuntimeFeature.SKILLS)
        return codexOperation("skill_list_failed", "Could not list skills") {
            client.listSkills(workingDirectory, forceReload)
        }
    }

    @Throws(Exception::class)
    internal suspend fun readSkill(path: String, offset: Long = 0): AgentSkillChunk {
        requireOpen()
        requireFeature(CodexRuntimeFeature.SKILLS)
        require(path.isAbsoluteHostPath()) { "Skill path must be absolute" }
        require(offset >= 0) { "Offset must not be negative" }
        return codexOperation("skill_read_failed", "Could not read skill") { client.readSkill(path, offset) }
    }

    internal suspend fun installSkill(directory: String, scope: AgentInstallationScope): AgentSkill {
        requireOpen()
        requireFeature(CodexRuntimeFeature.SKILLS)
        return codexOperation("skill_install_failed", "Could not install skill") {
            client.installSkill(directory, scope, workingDirectory)
        }
    }

    internal suspend fun uninstallSkill(skill: AgentSkill) {
        requireOpen()
        requireFeature(CodexRuntimeFeature.SKILLS)
        codexOperation("skill_uninstall_failed", "Could not uninstall skill") {
            client.uninstallSkill(skill, workingDirectory)
        }
    }

    @Throws(Exception::class)
    internal suspend fun setSkillEnabled(skill: AgentSkill, isEnabled: Boolean): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.SKILLS)
        require(skill.path.isAbsoluteHostPath()) { "Skill path must be absolute" }
        codexOperation("skill_update_failed", "Could not update skill") {
            client.setSkillEnabled(skill.path, isEnabled)
        }
    }

    @Throws(Exception::class)
    internal suspend fun listHooks(): AgentHookCatalog {
        requireOpen()
        requireFeature(CodexRuntimeFeature.HOOKS)
        return codexOperation("hook_list_failed", "Could not list hooks") { client.listHooks(workingDirectory) }
    }

    internal suspend fun installHook(directory: String, scope: AgentInstallationScope): AgentHook {
        requireOpen()
        requireFeature(CodexRuntimeFeature.HOOKS)
        return codexOperation("hook_install_failed", "Could not install hook") {
            client.installHook(directory, scope, workingDirectory)
        }
    }

    internal suspend fun uninstallHook(hook: AgentHook) {
        requireOpen()
        requireFeature(CodexRuntimeFeature.HOOKS)
        codexOperation("hook_uninstall_failed", "Could not uninstall hook") {
            client.uninstallHook(hook, workingDirectory)
        }
    }

    @Throws(Exception::class)
    internal suspend fun setHookEnabled(hook: AgentHook, isEnabled: Boolean): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.HOOKS)
        require(hook.key.isNotBlank()) { "Hook key must not be blank" }
        codexOperation("hook_update_failed", "Could not update hook") {
            client.setHookEnabled(hook.key, isEnabled)
        }
    }

    @Throws(Exception::class)
    internal suspend fun trustHook(hook: AgentHook): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.HOOKS)
        require(hook.key.isNotBlank()) { "Hook key must not be blank" }
        require(hook.currentHash.isNotBlank()) { "Hook hash must not be blank" }
        codexOperation("hook_trust_failed", "Could not trust hook") {
            client.trustHook(hook.key, hook.currentHash)
        }
    }

    @Throws(Exception::class)
    internal suspend fun listPlugins(forceRefresh: Boolean = false): AgentPluginCatalog {
        requireOpen()
        requireFeature(CodexRuntimeFeature.PLUGINS)
        return codexOperation("plugin_list_failed", "Could not list plugins") {
            client.listMergedPlugins(workingDirectory, forceRefresh)
        }
    }

    @Throws(Exception::class)
    internal suspend fun readPlugin(plugin: AgentPluginReference): AgentPluginDetail {
        requireOpen()
        requireFeature(CodexRuntimeFeature.PLUGINS)
        requireValidPlugin(plugin)
        return codexOperation("plugin_read_failed", "Could not read plugin") { client.readPlugin(plugin) }
    }

    @Throws(Exception::class)
    internal suspend fun installPlugin(plugin: AgentPluginReference): AgentPluginInstallResult {
        requireOpen()
        requireFeature(CodexRuntimeFeature.PLUGINS)
        requireValidPlugin(plugin)
        return codexOperation("plugin_install_failed", "Could not install plugin") { client.installPlugin(plugin) }
    }

    @Throws(Exception::class)
    internal suspend fun uninstallPlugin(plugin: AgentPluginReference): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.PLUGINS)
        requireValidPlugin(plugin)
        codexOperation("plugin_uninstall_failed", "Could not uninstall plugin") {
            client.uninstallPlugin(plugin)
        }
    }

    @Throws(Exception::class)
    internal suspend fun setPluginEnabled(plugin: AgentPluginSummary, isEnabled: Boolean): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.PLUGINS)
        require(plugin.reference.id.isNotBlank() && '.' !in plugin.reference.id) { "Invalid plugin ID" }
        codexOperation("plugin_update_failed", "Could not update plugin") {
            client.setPluginEnabled(plugin.reference.id, isEnabled)
        }
    }

    @Throws(Exception::class)
    internal suspend fun listConnectors(forceReload: Boolean = false): List<AgentConnector> {
        requireOpen()
        requireFeature(CodexRuntimeFeature.CONNECTORS)
        return codexOperation("connector_list_failed", "Could not list connectors") {
            client.listConnectors(
                mutableActiveConversation.value?.state?.value?.conversationId,
                forceReload,
            )
        }
    }

    @Throws(Exception::class)
    internal suspend fun listMcpServers(): List<AgentMcpServer> {
        requireOpen()
        requireFeature(CodexRuntimeFeature.MCP_SERVERS)
        return codexOperation("mcp_server_list_failed", "Could not list MCP servers") {
            client.listMcpServers(workingDirectory)
        }
    }

    internal suspend fun addMcpServer(configuration: AgentMcpServerConfiguration): AgentMcpServer {
        requireOpen()
        requireFeature(CodexRuntimeFeature.MCP_SERVERS)
        return codexOperation("mcp_server_add_failed", "Could not add MCP server") {
            client.addMcpServer(configuration, workingDirectory)
        }
    }

    internal suspend fun removeMcpServer(server: AgentMcpServer) {
        requireOpen()
        requireFeature(CodexRuntimeFeature.MCP_SERVERS)
        codexOperation("mcp_server_remove_failed", "Could not remove MCP server") {
            client.removeMcpServer(server, workingDirectory)
        }
    }

    @Throws(Exception::class)
    internal suspend fun authorizeConnector(connector: AgentConnector): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.CONNECTORS)
        integrationAuthorizationController.authorizeConnector(
            connector,
            mutableActiveConversation.value?.state?.value?.conversationId,
        )
    }

    @Throws(Exception::class)
    internal suspend fun authorizeMcpServer(
        server: AgentMcpServer,
        conversationId: ConversationId? = null,
    ): Unit {
        requireOpen()
        requireFeature(CodexRuntimeFeature.MCP_SERVERS)
        integrationAuthorizationController.authorizeMcpServer(
            server,
            conversationId ?: mutableActiveConversation.value?.state?.value?.conversationId,
        )
    }

    @Throws(Exception::class)
    internal suspend fun cancelIntegrationAuthorization(): Unit {
        requireOpen()
        integrationAuthorizationController.cancel()
    }

    internal suspend fun close(): Unit {
        val conversation = lock.withLock {
            if (closed) return
            closed = true
            signingOut = false
            conversationGeneration += 1
            mutableActiveConversation.value.also { mutableActiveConversation.value = null }
        }
        withContext(NonCancellable) {
            completeCleanup(
                listOf(
                    { conversation?.let { releaseConversation(it) } },
                    { integrationAuthorizationController.close() },
                    { interactionController.close() },
                    { authenticationController.close() },
                    { client.closeSuspendingAction() },
                    { scope.cancel() },
                ),
            )
        }
    }

    private suspend fun closeConversation(conversation: CodexConversation) {
        lock.withLock {
            if (!closed && mutableActiveConversation.value === conversation) {
                conversationGeneration += 1
                mutableActiveConversation.value = null
            }
        }
        releaseConversation(conversation)
    }

    private suspend fun releaseConversation(
        conversation: CodexConversation,
        knownConversationId: ConversationId? = conversation.state.value.conversationId,
    ) {
        val release = lock.withLock {
            conversation.agentReleaseCompletion?.let { ReleaseClaim(it, false) }
                ?: CompletableDeferred<Throwable?>().let { completion ->
                    conversation.agentReleaseCompletion = completion
                    ReleaseClaim(completion, true)
                }
        }
        if (!release.owner) {
            release.completion.await()?.let { throw it }
            knownConversationId?.let { detachConversation(conversation, it) }
            currentCoroutineContext().ensureActive()
            return
        }
        var failure: Throwable? = null
        withContext(NonCancellable) {
            try {
                val conversationId = knownConversationId ?: conversation.state.value.conversationId
                completeCleanup(
                    listOf(
                        { conversation.closeOwned() },
                        { conversationId?.let { detachConversation(conversation, it) } },
                    ),
                )
            } catch (error: Throwable) {
                failure = error
            } finally {
                release.completion.complete(failure)
            }
        }
        failure?.let { throw it }
        currentCoroutineContext().ensureActive()
    }

    private suspend fun detachConversation(conversation: CodexConversation, conversationId: ConversationId) {
        val result = client.detachConversation(conversationId, conversation)
        var failure = result.failure
        if (result.owned) {
            try {
                interactionController.detachConversation(conversationId)
            } catch (error: Throwable) {
                if (failure == null) failure = error
            }
        }
        failure?.let { throw it }
    }

    private suspend fun requireOpen(): Unit = lock.withLock { checkOpenLocked() }

    private fun checkOpenLocked() {
        check(!closed) { "Codex agent is closed" }
    }

    internal fun supports(feature: CodexRuntimeFeature): Boolean = feature in runtimeFeatures

    private fun requireFeature(feature: CodexRuntimeFeature) {
        if (feature !in runtimeFeatures) {
            throw CodexOperationException(
                CodexFailure(
                    code = "unsupported_feature",
                    message = "Runtime feature ${feature.name} is not supported",
                    isRecoverable = false,
                ),
            )
        }
    }

    private fun requireValidPlugin(plugin: AgentPluginReference) {
        require(plugin.id.isNotBlank()) { "Plugin ID must not be blank" }
        require(plugin.name.isNotBlank()) { "Plugin name must not be blank" }
        require(plugin.marketplaceName.isNotBlank()) { "Plugin marketplace must not be blank" }
        require(plugin.marketplacePath != null || !plugin.remotePluginId.isNullOrBlank()) {
            "Remote plugin is missing its catalog identifier"
        }
    }

    private data class ConversationTransition(
        val generation: Long,
        val previous: CodexConversation?,
        val conversation: CodexConversation,
    )

    private data class ReleaseClaim(
        val completion: CompletableDeferred<Throwable?>,
        val owner: Boolean,
    )
}
