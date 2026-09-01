@file:OptIn(ExperimentalObjCName::class)

package io.github.codex_agent_labs.codexagent.agent.runtime

import io.github.codex_agent_labs.codexagent.agent.AgentConversationState
import io.github.codex_agent_labs.codexagent.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexagent.agent.CodexAgent as CoreAgent
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexConversation as CoreConversation
import io.github.codex_agent_labs.codexagent.agent.CodexFailure as CoreFailure
import io.github.codex_agent_labs.codexagent.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexagent.agent.CodexHostState as CoreHostState
import io.github.codex_agent_labs.codexagent.agent.CodexOperationException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import platform.Foundation.NSRecursiveLock
import platform.Foundation.NSURL
import kotlin.experimental.ExperimentalObjCName
import kotlin.native.ObjCName

@ObjCName("CDXHostStatus", exact = true)
public enum class CDXHostStatus {
    @ObjCName("initial")
    NEW,
    RESTORING,
    WORKSPACE_REQUIRED,
    PREPARING,
    READY,
    FAILED,
    CLOSED,
}

@ObjCName("CDXConversationStatus", exact = true)
public enum class CDXConversationStatus {
    @ObjCName("initial")
    NEW,
    OPENING,
    READY,
    STARTING_TURN,
    RUNNING_TURN,
    CANCELLING_TURN,
    RELOADING,
    FAILED,
    CLOSED,
}

@ObjCName("CDXFailure", exact = true)
public class CDXFailure internal constructor(
    public val code: String,
    public val message: String,
    public val isRecoverable: Boolean,
)

@ObjCName("CDXOperationResult", exact = true)
public class CDXOperationResult internal constructor(
    public val success: Boolean,
    public val failure: CDXFailure?,
)

@ObjCName("CDXConversationResult", exact = true)
public class CDXConversationResult internal constructor(
    public val conversation: CDXConversation?,
    public val failure: CDXFailure?,
)

@ObjCName("CDXHostState", exact = true)
public class CDXHostState internal constructor(
    public val status: CDXHostStatus,
    public val agent: CDXAgent?,
    public val failure: CDXFailure?,
    public val workspacePath: String?,
    public val requirementMessage: String?,
)

@ObjCName("CDXConversationState", exact = true)
public class CDXConversationState internal constructor(
    public val status: CDXConversationStatus,
    public val conversationId: String?,
    public val failure: CDXFailure?,
    public val canStartTurn: Boolean,
    public val canReload: Boolean,
    public val canCancelTurn: Boolean,
)

/**
 * A cancellable Objective-C operation.
 *
 * Its completion block is invoked exactly once on the main queue, including after cancellation.
 */
@ObjCName("CDXOperation", exact = true)
public class CDXOperation internal constructor(private val job: Job) {
    /** Requests cancellation. Safe to call more than once. */
    public fun cancel() {
        job.cancel(CancellationException("Objective-C operation cancelled"))
    }

    /** Alias for cancellation for Objective-C ownership symmetry. */
    public fun dispose() {
        cancel()
    }
}

/**
 * A closeable Objective-C state observation.
 *
 * Handlers receive the current value and later changes serially on the main queue. Invalidation is
 * idempotent, waits for an in-flight handler unless it invalidates itself, and prevents new handler
 * invocations. A throwing handler invalidates only its own observation.
 */
@ObjCName("CDXObservation", exact = true)
public class CDXObservation internal constructor(private val observation: CodexStateObservation) {
    /** Stops callbacks. Safe to call more than once. */
    public fun invalidate() {
        observation.close()
    }

    /** Alias for invalidation for Objective-C ownership symmetry. */
    public fun dispose() {
        invalidate()
    }
}

/** Objective-C Host projection. Completion blocks are invoked exactly once on the main queue. */
@ObjCName("CDXHost", exact = true)
public class CDXHost(
    sandboxRootPath: String,
    clientName: String,
    clientTitle: String,
    clientVersion: String,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val delegate = CoreHost(
        platform = IosCodexPlatform(sandboxRootPath),
        clientInfo = CodexClientInfo(clientName, clientTitle, clientVersion),
    )
    private val agents = CDXIdentityCache<CoreAgent, CDXAgent>()

    public val state: CDXHostState
        get() = delegate.lifecycleState.value.toCDXState(::wrap)

    @ObjCName("startWith")
    public fun start(completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion) { delegate.start() }

    @ObjCName("selectWorkspace")
    public fun selectWorkspaceURL(
        @ObjCName("URL") url: NSURL,
        completion: (CDXOperationResult) -> Unit,
    ): CDXOperation =
        scope.operation(completion) { delegate.selectWorkspace(IosCodexWorkspaceSelection(url)) }

    @ObjCName("observeStateWith")
    public fun observeState(handler: (CDXHostState) -> Unit): CDXObservation = CDXObservation(
        CodexStateObservation(delegate.lifecycleState) { value ->
            handler(checkNotNull(value as? CoreHostState).toCDXState(::wrap))
        },
    )

    @ObjCName("disposeWith")
    public fun dispose(completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion) { delegate.close() }

    private fun wrap(agent: CoreAgent): CDXAgent = agents.getOrPut(agent) { CDXAgent(agent) { delegate.close() } }
}

/** Objective-C Agent projection. Completion blocks are invoked exactly once on the main queue. */
@ObjCName("CDXAgent", exact = true)
public class CDXAgent internal constructor(
    private val delegate: CoreAgent,
    private val disposeDelegate: suspend () -> Unit,
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val conversations = CDXIdentityCache<CoreConversation, CDXConversation>()

    public val activeConversation: CDXConversation?
        get() = delegate.conversations.active.value?.let(::wrap)

    @ObjCName("openConversationWith")
    public fun openConversation(completion: (CDXConversationResult) -> Unit): CDXOperation {
        val job = scope.launch(start = CoroutineStart.UNDISPATCHED) {
            val result = try {
                CDXConversationResult(wrap(delegate.conversations.open()), null)
            } catch (error: Throwable) {
                CDXConversationResult(null, error.toCDXFailure())
            }
            deliver { completion(result) }
        }
        return CDXOperation(job)
    }

    @ObjCName("observeActiveConversationWith")
    public fun observeActiveConversation(handler: (CDXConversation?) -> Unit): CDXObservation = CDXObservation(
        CodexStateObservation(delegate.conversations.active) { value ->
            handler((value as? CoreConversation)?.let(::wrap))
        },
    )

    @ObjCName("disposeWith")
    public fun dispose(completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion, disposeDelegate)

    private fun wrap(conversation: CoreConversation): CDXConversation =
        conversations.getOrPut(conversation, ::CDXConversation)
}

/** Objective-C Conversation projection. Completion blocks are invoked exactly once on the main queue. */
@ObjCName("CDXConversation", exact = true)
public class CDXConversation internal constructor(private val delegate: CoreConversation) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    public val state: CDXConversationState
        get() = delegate.state.value.toCDXState()

    @ObjCName("send")
    public fun sendPrompt(prompt: String, completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion) { delegate.send(prompt) }

    @ObjCName("cancelTurnWith")
    public fun cancelTurn(completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion) { delegate.cancelTurn() }

    @ObjCName("observeStateWith")
    public fun observeState(handler: (CDXConversationState) -> Unit): CDXObservation = CDXObservation(
        CodexStateObservation(delegate.state) { value ->
            handler(checkNotNull(value as? AgentConversationState).toCDXState())
        },
    )

    @ObjCName("disposeWith")
    public fun dispose(completion: (CDXOperationResult) -> Unit): CDXOperation =
        scope.operation(completion) { delegate.close() }
}

internal fun CoroutineScope.operation(
    completion: (CDXOperationResult) -> Unit,
    block: suspend () -> Unit,
): CDXOperation {
    val job = launch(start = CoroutineStart.UNDISPATCHED) {
        val result = try {
            block()
            CDXOperationResult(true, null)
        } catch (error: Throwable) {
            CDXOperationResult(false, error.toCDXFailure())
        }
        deliver { completion(result) }
    }
    return CDXOperation(job)
}

private suspend fun deliver(block: () -> Unit) {
    withContext(NonCancellable + Dispatchers.Main.immediate) {
        runCatching(block)
    }
}

private fun Throwable.toCDXFailure(): CDXFailure = when (this) {
    is CodexOperationException -> failure.toCDXFailure()
    is CancellationException -> CDXFailure("cancelled", "Operation cancelled", true)
    else -> CDXFailure("operation_failed", "Codex operation failed", false)
}

private fun CoreFailure.toCDXFailure(): CDXFailure = CDXFailure(code, message, isRecoverable)

private fun CoreHostState.toCDXState(wrap: (CoreAgent) -> CDXAgent): CDXHostState = when (this) {
    CoreHostState.New -> CDXHostState(CDXHostStatus.NEW, null, null, null, null)
    CoreHostState.Restoring -> CDXHostState(CDXHostStatus.RESTORING, null, null, null, null)
    is CoreHostState.WorkspaceRequired -> CDXHostState(
        CDXHostStatus.WORKSPACE_REQUIRED,
        null,
        null,
        null,
        requirement.message,
    )
    is CoreHostState.Preparing -> CDXHostState(CDXHostStatus.PREPARING, null, null, workspace.path, null)
    is CoreHostState.Ready -> CDXHostState(CDXHostStatus.READY, wrap(agent), null, agent.workspace.path, null)
    is CoreHostState.Failed -> CDXHostState(
        CDXHostStatus.FAILED,
        null,
        failure.toCDXFailure(),
        workspace?.path,
        null,
    )
    CoreHostState.Closed -> CDXHostState(CDXHostStatus.CLOSED, null, null, null, null)
}

internal fun AgentConversationState.toCDXState(): CDXConversationState = CDXConversationState(
    status = status.toCDXStatus(),
    conversationId = conversationId?.value,
    failure = failure?.toCDXFailure(),
    canStartTurn = canStartTurn,
    canReload = canReload,
    canCancelTurn = canCancelTurn,
)

private fun AgentConversationStatus.toCDXStatus(): CDXConversationStatus = when (this) {
    AgentConversationStatus.NEW -> CDXConversationStatus.NEW
    AgentConversationStatus.OPENING -> CDXConversationStatus.OPENING
    AgentConversationStatus.READY -> CDXConversationStatus.READY
    AgentConversationStatus.STARTING_TURN -> CDXConversationStatus.STARTING_TURN
    AgentConversationStatus.RUNNING_TURN -> CDXConversationStatus.RUNNING_TURN
    AgentConversationStatus.CANCELLING_TURN -> CDXConversationStatus.CANCELLING_TURN
    AgentConversationStatus.RELOADING -> CDXConversationStatus.RELOADING
    AgentConversationStatus.FAILED -> CDXConversationStatus.FAILED
    AgentConversationStatus.CLOSED -> CDXConversationStatus.CLOSED
}

internal class CDXIdentityCache<K : Any, V : Any> {
    private val lock = NSRecursiveLock()
    private val cached = mutableListOf<Pair<K, V>>()

    fun getOrPut(key: K, create: (K) -> V): V {
        lock.lock()
        return try {
            cached.firstOrNull { it.first === key }?.second
                ?: create(key).also { cached += key to it }
        } finally {
            lock.unlock()
        }
    }
}
