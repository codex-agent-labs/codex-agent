@file:JvmName("CodexJava")

package io.github.codex_agent_labs.codexagent.agent

import java.util.Optional
import java.util.concurrent.CompletableFuture
import java.util.concurrent.CompletionException
import java.util.concurrent.ExecutionException
import java.util.concurrent.Executor
import java.util.function.Consumer
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

/** Java entry points for the canonical Host -> Agent -> Conversation API. */
public fun startAsync(host: CodexHost): CompletableFuture<Void> = codexVoidFuture { host.start() }

public fun selectWorkspaceAsync(
    host: CodexHost,
    selection: CodexWorkspaceSelection,
): CompletableFuture<Void> = codexVoidFuture { host.selectWorkspace(selection) }

/** Cancelling the returned future does not interrupt resource cleanup. */
public fun closeAsync(host: CodexHost): CompletableFuture<Void> = codexVoidFuture(cancelOperation = false) {
    host.close()
}

@JvmOverloads
public fun authenticateAsync(
    agent: CodexAgent,
    method: CodexAuthenticationMethod = CodexAuthenticationMethod.ChatGptBrowser,
): CompletableFuture<Void> = codexVoidFuture { agent.authentication.authenticate(method) }

public fun cancelAuthenticationAsync(agent: CodexAgent): CompletableFuture<Void> =
    codexVoidFuture { agent.authentication.cancel() }

public fun signOutAsync(agent: CodexAgent): CompletableFuture<Void> =
    codexVoidFuture { agent.authentication.signOut() }

public fun listConversationsAsync(agent: CodexAgent): CompletableFuture<List<AgentConversationSummary>> =
    codexFuture { agent.conversations.list().javaSnapshot() }

public fun readConversationAsync(
    agent: CodexAgent,
    conversationId: ConversationId,
): CompletableFuture<AgentConversation> = codexFuture { agent.conversations.read(conversationId).javaSnapshot() }

public fun renameConversationAsync(
    agent: CodexAgent,
    conversationId: ConversationId,
    name: String,
): CompletableFuture<Void> = codexVoidFuture { agent.conversations.rename(conversationId, name) }

public fun deleteConversationAsync(
    agent: CodexAgent,
    conversationId: ConversationId,
): CompletableFuture<Void> = codexVoidFuture { agent.conversations.delete(conversationId) }

public fun openConversationAsync(agent: CodexAgent): CompletableFuture<CodexConversation> =
    codexFuture { agent.conversations.open() }

public fun openConversationAsync(
    agent: CodexAgent,
    settings: AgentConversationSettings,
): CompletableFuture<CodexConversation> = codexFuture { agent.conversations.open(settings = settings) }

public fun openConversationAsync(
    agent: CodexAgent,
    conversationId: ConversationId,
): CompletableFuture<CodexConversation> = codexFuture { agent.conversations.open(conversationId = conversationId) }

public fun openConversationAsync(
    agent: CodexAgent,
    conversationId: ConversationId,
    settings: AgentConversationSettings,
): CompletableFuture<CodexConversation> = codexFuture {
    agent.conversations.open(conversationId = conversationId, settings = settings)
}

public fun authorizeIntegrationAsync(
    agent: CodexAgent,
    target: AgentIntegration,
): CompletableFuture<Void> = codexVoidFuture { agent.integrationAuthorization.authorize(target) }

public fun cancelIntegrationAuthorizationAsync(agent: CodexAgent): CompletableFuture<Void> =
    codexVoidFuture { agent.integrationAuthorization.cancel() }

public fun resolveApprovalAsync(
    agent: CodexAgent,
    approval: AgentPendingApproval,
    decision: AgentApprovalDecision,
): CompletableFuture<Void> = codexVoidFuture { agent.interactions.resolve(approval, decision) }

public fun resolveElicitationAsync(
    agent: CodexAgent,
    elicitation: AgentPendingElicitation,
    response: AgentElicitationResponse,
): CompletableFuture<Void> = codexVoidFuture { agent.interactions.resolve(elicitation, response) }

public fun openElicitationUrlAsync(
    agent: CodexAgent,
    elicitation: AgentPendingElicitation,
): CompletableFuture<Void> = codexVoidFuture { agent.interactions.openUrl(elicitation) }

public fun listModelsAsync(agent: CodexAgent): CompletableFuture<List<AgentModel>> =
    codexFuture { agent.models.list().map { it.javaSnapshot() }.javaSnapshot() }

@JvmOverloads
public fun resolveModelAsync(
    agent: CodexAgent,
    resolution: AgentResolution = AgentResolution.Preferred,
): CompletableFuture<AgentModel> = codexFuture { agent.models.resolve(resolution).javaSnapshot() }

@JvmOverloads
public fun resolveEffortAsync(
    agent: CodexAgent,
    model: AgentModel,
    resolution: AgentResolution = AgentResolution.Preferred,
): CompletableFuture<String> = codexFuture { agent.models.resolveEffort(model, resolution) }

@JvmOverloads
public fun resolveServiceTierAsync(
    agent: CodexAgent,
    model: AgentModel,
    resolution: AgentResolution = AgentResolution.Preferred,
): CompletableFuture<Optional<AgentServiceTier>> = codexOptionalFuture {
    agent.models.resolveServiceTier(model, resolution)
}

@JvmOverloads
public fun listSkillsAsync(
    agent: CodexAgent,
    forceReload: Boolean = false,
): CompletableFuture<AgentSkillCatalog> = codexFuture { agent.skills.list(forceReload).javaSnapshot() }

@JvmOverloads
public fun readSkillAsync(
    agent: CodexAgent,
    path: String,
    offset: Long = 0,
): CompletableFuture<AgentSkillChunk> = codexFuture { agent.skills.read(path, offset) }

public fun installSkillAsync(
    agent: CodexAgent,
    directory: String,
    scope: AgentInstallationScope,
): CompletableFuture<AgentSkill> = codexFuture { agent.skills.install(directory, scope).javaSnapshot() }

public fun uninstallSkillAsync(
    agent: CodexAgent,
    skill: AgentSkill,
): CompletableFuture<Void> = codexVoidFuture { agent.skills.uninstall(skill) }

public fun listHooksAsync(agent: CodexAgent): CompletableFuture<AgentHookCatalog> =
    codexFuture { agent.hooks.list().javaSnapshot() }

public fun installHookAsync(
    agent: CodexAgent,
    directory: String,
    scope: AgentInstallationScope,
): CompletableFuture<AgentHook> = codexFuture { agent.hooks.install(directory, scope) }

public fun uninstallHookAsync(
    agent: CodexAgent,
    hook: AgentHook,
): CompletableFuture<Void> = codexVoidFuture { agent.hooks.uninstall(hook) }

public fun trustHookAsync(
    agent: CodexAgent,
    hook: AgentHook,
): CompletableFuture<Void> = codexVoidFuture { agent.hooks.trust(hook) }

@JvmOverloads
public fun listPluginsAsync(
    agent: CodexAgent,
    forceReload: Boolean = false,
): CompletableFuture<AgentPluginCatalog> = codexFuture { agent.plugins.list(forceReload).javaSnapshot() }

public fun readPluginAsync(
    agent: CodexAgent,
    plugin: AgentPluginReference,
): CompletableFuture<AgentPluginDetail> = codexFuture { agent.plugins.read(plugin).javaSnapshot() }

public fun installPluginAsync(
    agent: CodexAgent,
    plugin: AgentPluginReference,
): CompletableFuture<AgentPluginInstallResult> = codexFuture { agent.plugins.install(plugin).javaSnapshot() }

public fun uninstallPluginAsync(
    agent: CodexAgent,
    plugin: AgentPluginReference,
): CompletableFuture<Void> = codexVoidFuture { agent.plugins.uninstall(plugin) }

@JvmOverloads
public fun listConnectorsAsync(
    agent: CodexAgent,
    forceReload: Boolean = false,
): CompletableFuture<List<AgentConnector>> =
    codexFuture { agent.connectors.list(forceReload).map { it.javaSnapshot() }.javaSnapshot() }

public fun listMcpServersAsync(agent: CodexAgent): CompletableFuture<List<AgentMcpServer>> =
    codexFuture { agent.mcpServers.list().map { it.javaSnapshot() }.javaSnapshot() }

public fun addMcpServerAsync(
    agent: CodexAgent,
    configuration: AgentMcpServerConfiguration,
): CompletableFuture<AgentMcpServer> = codexFuture { agent.mcpServers.add(configuration).javaSnapshot() }

public fun removeMcpServerAsync(
    agent: CodexAgent,
    server: AgentMcpServer,
): CompletableFuture<Void> = codexVoidFuture { agent.mcpServers.remove(server) }

public fun sendAsync(
    conversation: CodexConversation,
    prompt: String,
): CompletableFuture<Void> = codexVoidFuture { conversation.send(prompt) }

public fun sendAsync(
    conversation: CodexConversation,
    request: AgentTurnRequest,
): CompletableFuture<Void> = codexVoidFuture { conversation.send(request) }

public fun runShellCommandAsync(
    conversation: CodexConversation,
    command: String,
): CompletableFuture<Void> = codexVoidFuture { conversation.runShellCommand(command) }

public fun cancelTurnAsync(conversation: CodexConversation): CompletableFuture<Void> =
    codexVoidFuture { conversation.cancelTurn() }

public fun reloadAsync(conversation: CodexConversation): CompletableFuture<Void> =
    codexVoidFuture { conversation.reload() }

/** Cancelling the returned future does not interrupt resource cleanup. */
public fun closeAsync(conversation: CodexConversation): CompletableFuture<Void> =
    codexVoidFuture(cancelOperation = false) { conversation.close() }

public fun currentLifecycleState(host: CodexHost): CodexHostState = host.lifecycleState.value

public fun currentConversationState(conversation: CodexConversation): AgentConversationState =
    conversation.state.value.javaSnapshot()

public fun currentAuthenticationState(agent: CodexAgent): AgentAuthenticationState = agent.authentication.state.value

public fun isAuthenticated(agent: CodexAgent): Boolean = agent.authentication.isAuthenticated.value

public fun isAuthenticating(agent: CodexAgent): Boolean = agent.authentication.isAuthenticating.value

public fun currentIntegrationAuthorizationState(agent: CodexAgent): AgentIntegrationAuthorizationState =
    agent.integrationAuthorization.state.value.javaSnapshot()

public fun activeIntegrationAuthorization(agent: CodexAgent): Optional<AgentIntegration> =
    Optional.ofNullable(agent.integrationAuthorization.active.value?.javaSnapshot())

public fun isIntegrationAuthorizing(agent: CodexAgent): Boolean =
    agent.integrationAuthorization.isAuthorizing.value

public fun currentInteractionState(agent: CodexAgent): AgentInteractionState =
    agent.interactions.state.value.javaSnapshot()

public fun currentApprovals(agent: CodexAgent): List<AgentPendingApproval> =
    agent.interactions.approvals.value.javaSnapshot()

public fun currentElicitations(agent: CodexAgent): List<AgentPendingElicitation> =
    agent.interactions.elicitations.value.javaSnapshot()

public fun currentTurnProgress(conversation: CodexConversation): Optional<AgentTurnProgress> =
    Optional.ofNullable(conversation.activeTurnProgress.value?.javaSnapshot())

public fun canCancelTurn(conversation: CodexConversation): Boolean = conversation.canCancelTurn.value

public fun canReload(conversation: CodexConversation): Boolean = conversation.canReload.value

public fun canRunShellCommand(conversation: CodexConversation): Boolean = conversation.canRunShellCommand.value

public fun canStartTurn(conversation: CodexConversation): Boolean = conversation.canStartTurn.value

public fun currentMessages(conversation: CodexConversation): List<AgentMessage> =
    conversation.currentMessages.value.map { it.javaSnapshot() }.javaSnapshot()

public fun isTurnActive(conversation: CodexConversation): Boolean = conversation.isTurnActive.value

public fun observeLifecycle(
    host: CodexHost,
    executor: Executor,
    observer: Consumer<in CodexHostState>,
): CodexJavaObservation = observe(host.lifecycleState, executor, observer) { it }

public fun observeActiveConversation(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in Optional<CodexConversation>>,
): CodexJavaObservation = observe(agent.conversations.active, executor, observer) { Optional.ofNullable(it) }

public fun observeConversation(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in AgentConversationState>,
): CodexJavaObservation = observe(conversation.state, executor, observer) { it.javaSnapshot() }

public fun observeAuthenticationState(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in AgentAuthenticationState>,
): CodexJavaObservation = observe(agent.authentication.state, executor, observer) { it }

public fun observeAuthenticated(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(agent.authentication.isAuthenticated, executor, observer) { it }

public fun observeAuthenticating(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(agent.authentication.isAuthenticating, executor, observer) { it }

public fun observeIntegrationAuthorizationState(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in AgentIntegrationAuthorizationState>,
): CodexJavaObservation = observe(agent.integrationAuthorization.state, executor, observer) { it.javaSnapshot() }

public fun observeActiveIntegrationAuthorization(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in Optional<AgentIntegration>>,
): CodexJavaObservation = observe(agent.integrationAuthorization.active, executor, observer) {
    Optional.ofNullable(it?.javaSnapshot())
}

public fun observeIntegrationAuthorizing(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(agent.integrationAuthorization.isAuthorizing, executor, observer) { it }

public fun observeInteractionState(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in AgentInteractionState>,
): CodexJavaObservation = observe(agent.interactions.state, executor, observer) { it.javaSnapshot() }

public fun observeApprovals(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in List<AgentPendingApproval>>,
): CodexJavaObservation = observe(agent.interactions.approvals, executor, observer) { it.javaSnapshot() }

public fun observeElicitations(
    agent: CodexAgent,
    executor: Executor,
    observer: Consumer<in List<AgentPendingElicitation>>,
): CodexJavaObservation = observe(agent.interactions.elicitations, executor, observer) { it.javaSnapshot() }

public fun observeTurnProgress(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Optional<AgentTurnProgress>>,
): CodexJavaObservation = observe(conversation.activeTurnProgress, executor, observer) {
    Optional.ofNullable(it?.javaSnapshot())
}

public fun observeCanCancelTurn(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(conversation.canCancelTurn, executor, observer) { it }

public fun observeCanReload(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(conversation.canReload, executor, observer) { it }

public fun observeCanRunShellCommand(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(conversation.canRunShellCommand, executor, observer) { it }

public fun observeCanStartTurn(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(conversation.canStartTurn, executor, observer) { it }

public fun observeMessages(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in List<AgentMessage>>,
): CodexJavaObservation = observe(conversation.currentMessages, executor, observer) {
    it.map { message -> message.javaSnapshot() }.javaSnapshot()
}

public fun observeTurnActive(
    conversation: CodexConversation,
    executor: Executor,
    observer: Consumer<in Boolean>,
): CodexJavaObservation = observe(conversation.isTurnActive, executor, observer) { it }

public fun readyAgent(state: CodexHostState): Optional<CodexAgent> =
    Optional.ofNullable((state as? CodexHostState.Ready)?.agent)

public fun hostWorkspace(state: CodexHostState): Optional<CodexWorkspace> = Optional.ofNullable(
    when (state) {
        is CodexHostState.Preparing -> state.workspace
        is CodexHostState.Ready -> state.agent.workspace
        is CodexHostState.Failed -> state.workspace
        else -> null
    },
)

public fun hostFailure(state: CodexHostState): Optional<CodexFailure> =
    Optional.ofNullable((state as? CodexHostState.Failed)?.failure)

public fun activeConversation(agent: CodexAgent): Optional<CodexConversation> =
    Optional.ofNullable(agent.conversations.active.value)

public fun conversationId(state: AgentConversationState): Optional<ConversationId> =
    Optional.ofNullable(state.conversationId)

public fun conversationFailure(state: AgentConversationState): Optional<CodexFailure> =
    Optional.ofNullable(state.failure)

/** Extracts the canonical structured failure from direct or Future-wrapped errors. */
public fun failure(error: Throwable): Optional<CodexFailure> {
    var current = error
    while (current is CompletionException || current is ExecutionException) {
        current = current.cause ?: break
    }
    return Optional.ofNullable((current as? CodexOperationException)?.failure)
}

public fun conversationSettings(): CodexConversationSettingsBuilder = CodexConversationSettingsBuilder()

public fun turnRequest(prompt: String): CodexTurnRequestBuilder = CodexTurnRequestBuilder(prompt)

public class CodexConversationSettingsBuilder public constructor() {
    private var approvalPreset: AgentApprovalPreset = AgentApprovalPreset.AUTO_REVIEW
    private var serviceTier: String? = null

    public fun approvalPreset(value: AgentApprovalPreset): CodexConversationSettingsBuilder = apply {
        approvalPreset = value
    }

    public fun serviceTier(value: String): CodexConversationSettingsBuilder = apply {
        serviceTier = value
    }

    public fun clearServiceTier(): CodexConversationSettingsBuilder = apply { serviceTier = null }

    public fun build(): AgentConversationSettings = AgentConversationSettings(approvalPreset, serviceTier)
}

public class CodexTurnRequestBuilder public constructor(
    private val prompt: String,
) {
    private var clientMessageId: String? = null
    private var model: String? = null
    private var effort: String? = null
    private var serviceTier: String? = null
    private var approvalPreset: AgentApprovalPreset = AgentApprovalPreset.AUTO_REVIEW
    private var capabilities: Set<AgentCapability> = emptySet()
    private var invocations: List<AgentInvocation> = emptyList()
    private var collaborationMode: AgentCollaborationMode = AgentCollaborationMode.DEFAULT

    public fun clientMessageId(value: String): CodexTurnRequestBuilder = apply { clientMessageId = value }

    public fun clearClientMessageId(): CodexTurnRequestBuilder = apply { clientMessageId = null }

    public fun model(value: String): CodexTurnRequestBuilder = apply { model = value }

    public fun clearModel(): CodexTurnRequestBuilder = apply { model = null }

    public fun effort(value: String): CodexTurnRequestBuilder = apply { effort = value }

    public fun clearEffort(): CodexTurnRequestBuilder = apply { effort = null }

    public fun serviceTier(value: String): CodexTurnRequestBuilder = apply { serviceTier = value }

    public fun clearServiceTier(): CodexTurnRequestBuilder = apply { serviceTier = null }

    public fun approvalPreset(value: AgentApprovalPreset): CodexTurnRequestBuilder = apply {
        approvalPreset = value
    }

    public fun capabilities(values: Collection<AgentCapability>): CodexTurnRequestBuilder = apply {
        capabilities = values.toSet()
    }

    public fun invocations(values: Collection<AgentInvocation>): CodexTurnRequestBuilder = apply {
        invocations = values.toList()
    }

    public fun collaborationMode(value: AgentCollaborationMode): CodexTurnRequestBuilder = apply {
        collaborationMode = value
    }

    public fun build(): AgentTurnRequest = AgentTurnRequest(
        prompt = prompt,
        clientMessageId = clientMessageId,
        model = model,
        effort = effort,
        serviceTier = serviceTier,
        approvalPreset = approvalPreset,
        capabilities = capabilities,
        invocations = invocations,
        collaborationMode = collaborationMode,
    )
}

public interface CodexJavaObservation : AutoCloseable {
    public val isClosed: Boolean
    public override fun close(): Unit
}

private class DefaultCodexJavaObservation(
    private val job: Job,
) : CodexJavaObservation {
    private val monitor = Any()
    private var active = true

    override val isClosed: Boolean get() = synchronized(monitor) { !active }

    fun dispatch(action: () -> Unit): Boolean = synchronized(monitor) {
        if (!active) return false
        action()
        active
    }

    override fun close(): Unit {
        val cancel = synchronized(monitor) {
            if (!active) false else {
                active = false
                true
            }
        }
        if (cancel) job.cancel()
    }
}

private fun codexVoidFuture(
    cancelOperation: Boolean = true,
    operation: suspend () -> Unit,
): CompletableFuture<Void> {
    val future = CompletableFuture<Void>()
    val job = CoroutineScope(Dispatchers.Default).launch {
        try {
            operation()
            future.complete(null)
        } catch (_: CancellationException) {
            future.cancel(false)
        } catch (error: Throwable) {
            future.completeExceptionally(error)
        }
    }
    if (cancelOperation) {
        future.whenComplete { _, _ ->
            if (future.isCancelled) job.cancel(CancellationException("Java future was cancelled"))
        }
    }
    return future
}

private fun <T> codexFuture(operation: suspend () -> T): CompletableFuture<T> {
    val future = CompletableFuture<T>()
    val job = CoroutineScope(Dispatchers.Default).launch {
        try {
            future.complete(operation())
        } catch (_: CancellationException) {
            future.cancel(false)
        } catch (error: Throwable) {
            future.completeExceptionally(error)
        }
    }
    future.whenComplete { _, _ ->
        if (future.isCancelled) job.cancel(CancellationException("Java future was cancelled"))
    }
    return future
}

private fun <T : Any> codexOptionalFuture(operation: suspend () -> T?): CompletableFuture<Optional<T>> =
    codexFuture { Optional.ofNullable(operation()) }

private fun <T> List<T>.javaSnapshot(): List<T> = java.util.Collections.unmodifiableList(ArrayList(this))

private fun <T> Set<T>.javaSnapshot(): Set<T> = java.util.Collections.unmodifiableSet(LinkedHashSet(this))

private fun <K, V> Map<K, V>.javaSnapshot(): Map<K, V> =
    java.util.Collections.unmodifiableMap(LinkedHashMap(this))

private fun AgentModel.javaSnapshot(): AgentModel = copy(
    supportedEfforts = supportedEfforts.javaSnapshot(),
    serviceTiers = serviceTiers.javaSnapshot(),
)

private fun AgentConversation.javaSnapshot(): AgentConversation = copy(
    messages = messages.map { it.javaSnapshot() }.javaSnapshot(),
)

private fun AgentMessage.javaSnapshot(): AgentMessage = copy(
    capabilities = capabilities.javaSnapshot(),
    invocations = invocations.javaSnapshot(),
)

private fun AgentConversationState.javaSnapshot(): AgentConversationState = copy(
    conversation = conversation?.javaSnapshot(),
    turnProgress = turnProgress.javaSnapshot(),
)

private fun AgentTurnProgress.javaSnapshot(): AgentTurnProgress = copy(
    planProgress = planProgress?.copy(steps = planProgress.steps.javaSnapshot()),
    hookActivities = hookActivities.map { it.copy(details = it.details.javaSnapshot()) }.javaSnapshot(),
)

private fun AgentSkill.javaSnapshot(): AgentSkill = copy(dependencies = dependencies.javaSnapshot())

private fun AgentSkillCatalog.javaSnapshot(): AgentSkillCatalog = copy(
    skills = skills.map { it.javaSnapshot() }.javaSnapshot(),
    errors = errors.javaSnapshot(),
)

private fun AgentHookCatalog.javaSnapshot(): AgentHookCatalog = copy(
    hooks = hooks.javaSnapshot(),
    warnings = warnings.javaSnapshot(),
    errors = errors.javaSnapshot(),
)

private fun AgentPluginSummary.javaSnapshot(): AgentPluginSummary = copy(capabilities = capabilities.javaSnapshot())

private fun AgentPluginCatalog.javaSnapshot(): AgentPluginCatalog = copy(
    plugins = plugins.map { it.javaSnapshot() }.javaSnapshot(),
    errors = errors.javaSnapshot(),
)

private fun AgentConnector.javaSnapshot(): AgentConnector = copy(pluginNames = pluginNames.javaSnapshot())

private fun AgentPluginDetail.javaSnapshot(): AgentPluginDetail = copy(
    summary = summary.javaSnapshot(),
    skills = skills.javaSnapshot(),
    connectors = connectors.map { it.javaSnapshot() }.javaSnapshot(),
    mcpServers = mcpServers.javaSnapshot(),
)

private fun AgentPluginInstallResult.javaSnapshot(): AgentPluginInstallResult = copy(
    connectorsNeedingAuthentication = connectorsNeedingAuthentication.map { it.javaSnapshot() }.javaSnapshot(),
)

private fun AgentMcpServer.javaSnapshot(): AgentMcpServer = copy(configuration = configuration?.javaSnapshot())

private fun AgentMcpServerConfiguration.javaSnapshot(): AgentMcpServerConfiguration = copy(
    transport = transport.javaSnapshot(),
    omitToolsFrom = omitToolsFrom?.javaSnapshot(),
    enabledTools = enabledTools?.javaSnapshot(),
    disabledTools = disabledTools?.javaSnapshot(),
    scopes = scopes?.javaSnapshot(),
    tools = tools.javaSnapshot(),
)

private fun AgentMcpTransport.javaSnapshot(): AgentMcpTransport = when (this) {
    is AgentMcpTransport.Stdio -> copy(
        arguments = arguments.javaSnapshot(),
        environment = environment?.javaSnapshot(),
        forwardedEnvironment = forwardedEnvironment.javaSnapshot(),
    )
    is AgentMcpTransport.Http -> copy(
        headers = headers?.javaSnapshot(),
        environmentHeaders = environmentHeaders?.javaSnapshot(),
    )
}

private fun AgentIntegration.javaSnapshot(): AgentIntegration = when (this) {
    is AgentIntegration.Connector -> copy(connector = connector.javaSnapshot())
    is AgentIntegration.McpServer -> copy(server = server.javaSnapshot())
}

private fun AgentIntegrationAuthorizationState.javaSnapshot(): AgentIntegrationAuthorizationState =
    copy(target = target?.javaSnapshot())

private fun AgentInteractionState.javaSnapshot(): AgentInteractionState = copy(
    pending = pending.javaSnapshot(),
    resolvingRequestIds = resolvingRequestIds.javaSnapshot(),
)

private fun <T, R> observe(
    state: StateFlow<T>,
    executor: Executor,
    observer: Consumer<in R>,
    transform: (T) -> R,
): CodexJavaObservation {
    val job = Job()
    val observation = DefaultCodexJavaObservation(job)
    CoroutineScope(job + Dispatchers.Default).launch(start = CoroutineStart.UNDISPATCHED) {
        try {
            state.collect { value ->
                if (!deliver(executor, observation, observer, transform(value))) {
                    throw CancellationException("Java state observation stopped")
                }
            }
        } finally {
            observation.close()
        }
    }
    return observation
}

private suspend fun <T> deliver(
    executor: Executor,
    observation: DefaultCodexJavaObservation,
    observer: Consumer<in T>,
    value: T,
): Boolean {
    val completion = CompletableDeferred<Boolean>()
    try {
        executor.execute {
            try {
                completion.complete(observation.dispatch { observer.accept(value) })
            } catch (error: Throwable) {
                observation.close()
                completion.complete(false)
                if (error is Error) throw error
            }
        }
    } catch (error: Throwable) {
        observation.close()
        if (error is Error) throw error
        return false
    }
    return completion.await()
}
