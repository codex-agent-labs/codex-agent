@file:JvmName("CodexJava")

package io.github.codex_agent_labs.codexmobile.agent

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

public fun currentConversationState(conversation: CodexConversation): AgentConversationState = conversation.state.value

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
): CodexJavaObservation = observe(conversation.state, executor, observer) { it }

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
