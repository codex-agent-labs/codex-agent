package io.github.codex_agent_labs.codexagent.agent

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

public sealed interface AgentPendingInteraction {
    public val requestId: String
    public val conversationId: ConversationId
}

public data class AgentPendingApproval(
    public override val requestId: String,
    public override val conversationId: ConversationId,
    public val title: String,
    public val details: String,
) : AgentPendingInteraction

public data class AgentPendingElicitation(
    public val elicitation: AgentElicitation,
) : AgentPendingInteraction {
    public override val requestId: String get() = elicitation.requestId
    public override val conversationId: ConversationId get() = elicitation.conversationId
}

public data class AgentInteractionState(
    public val pending: List<AgentPendingInteraction> = emptyList(),
    public val resolvingRequestIds: Set<String> = emptySet(),
    public val failure: CodexFailure? = null,
) {
    public fun pendingFor(conversationId: ConversationId): List<AgentPendingInteraction> =
        pending.filter { it.conversationId == conversationId }
}

internal class InteractionController(
    private val client: CodexAgentClient,
    scope: CoroutineScope,
    private val authorizationBrowser: CodexAuthorizationBrowser? = null,
) {
    private val lock = Mutex()
    private val mutableState = MutableStateFlow(AgentInteractionState())
    private val mutableApprovals = MutableStateFlow<List<AgentPendingApproval>>(emptyList())
    private val mutableElicitations = MutableStateFlow<List<AgentPendingElicitation>>(emptyList())
    private val presentations = mutableMapOf<String, CodexAuthorizationPresentation>()
    private var closed = false

    internal val state: StateFlow<AgentInteractionState> = mutableState.asStateFlow()
    internal val approvals: StateFlow<List<AgentPendingApproval>> = mutableApprovals.asStateFlow()
    internal val elicitations: StateFlow<List<AgentPendingElicitation>> = mutableElicitations.asStateFlow()

    private val observation: Job = scope.launch(start = CoroutineStart.UNDISPATCHED) {
        client.events.collect(::process)
    }

    internal suspend fun resolveApproval(approval: AgentPendingApproval, decision: AgentApprovalDecision) {
        beginResolution(approval)
        try {
            client.resolveApproval(approval.requestId, decision)
        } catch (error: Throwable) {
            if (error is CancellationException) {
                withContext(NonCancellable) {
                    runCatching { finishResolution(approval, succeeded = false) }
                }
                throw error
            }
            val exception = error.asCodexOperationException("approval_resolution_failed", "Could not resolve approval")
            withContext(NonCancellable) {
                runCatching { finishResolution(approval, exception.failure, succeeded = false) }
            }
            throw exception
        }
        finishPublicResolution(
            approval,
            "approval_resolution_failed",
            "Could not resolve approval",
        )
    }

    internal suspend fun resolveElicitation(
        pendingElicitation: AgentPendingElicitation,
        response: AgentElicitationResponse,
    ) {
        val snapshot = response.snapshot()
        val elicitation = lock.withLock {
            check(mutableState.value.pending.any { it === pendingElicitation }) {
                "Elicitation is no longer pending"
            }
            pendingElicitation.elicitation
        }
        require(elicitation.accepts(snapshot)) { "Elicitation response is invalid" }
        beginResolution(pendingElicitation)
        try {
            client.resolveElicitation(pendingElicitation.requestId, snapshot)
        } catch (error: Throwable) {
            if (error is CancellationException) {
                withContext(NonCancellable) {
                    runCatching { finishResolution(pendingElicitation, succeeded = false) }
                }
                throw error
            }
            val exception = error.asCodexOperationException(
                "elicitation_resolution_failed",
                "Could not resolve elicitation",
            )
            withContext(NonCancellable) {
                runCatching { finishResolution(pendingElicitation, exception.failure, succeeded = false) }
            }
            throw exception
        }
        finishPublicResolution(
            pendingElicitation,
            "elicitation_resolution_failed",
            "Could not resolve elicitation",
        )
    }

    internal suspend fun openUrl(elicitation: AgentPendingElicitation) {
        val url = lock.withLock {
            check(!closed) { "Interactions are closed" }
            check(mutableState.value.pending.any { it === elicitation }) {
                "URL elicitation is no longer pending"
            }
            elicitation.elicitation.url ?: error("Elicitation does not contain a URL")
        }
        val opener = authorizationBrowser ?: error("An authorization browser is required")
        val opened = try {
            opener.open(CodexAuthorizationUrl.external(url))
        } catch (error: Throwable) {
            val exception = error.asCodexOperationException(
                "authorization_browser_failed",
                "Could not open elicitation URL",
            )
            lock.withLock {
                if (!closed && mutableState.value.pending.any { it === elicitation }) {
                    publishState(mutableState.value.copy(failure = exception.failure))
                }
            }
            throw exception
        }
        var cleanupFailure: Throwable? = null
        withContext(NonCancellable) {
            try {
                var closeOpened = false
                val previous = lock.withLock {
                    if (closed || mutableState.value.pending.none { it === elicitation }) {
                        closeOpened = true
                        null
                    } else {
                        presentations.put(elicitation.requestId, opened)
                    }
                }
                if (closeOpened) opened.close()
                previous?.close()
            } catch (error: Throwable) {
                cleanupFailure = error
            }
        }
        cleanupFailure?.let { error ->
            val exception = error.asCodexOperationException(
                "authorization_browser_failed",
                "Could not update the elicitation URL",
            )
            withContext(NonCancellable) {
                lock.withLock {
                    if (!closed && mutableState.value.pending.any { it === elicitation }) {
                        publishState(mutableState.value.copy(failure = exception.failure))
                    }
                }
            }
            throw exception
        }
        currentCoroutineContext().ensureActive()
    }

    internal suspend fun detachConversation(conversationId: ConversationId) {
        val owned = lock.withLock { removeForConversation(conversationId) }
        completeCleanup(owned.map { presentation -> { presentation.close() } })
    }

    internal suspend fun close() {
        val owned = lock.withLock {
            if (closed) return
            closed = true
            observation.cancel()
            val result = presentations.values.toList()
            presentations.clear()
            publishState(AgentInteractionState())
            result
        }
        observation.join()
        completeCleanup(owned.map { presentation -> { presentation.close() } })
    }

    private suspend fun beginResolution(interaction: AgentPendingInteraction) {
        lock.withLock {
            val current = mutableState.value
            check(!closed) { "Interactions are closed" }
            check(interaction.requestId !in current.resolvingRequestIds) { "Interaction is already resolving" }
            check(current.pending.any { it === interaction }) {
                "Interaction is no longer pending"
            }
            publishState(current.copy(
                resolvingRequestIds = current.resolvingRequestIds + interaction.requestId,
                failure = null,
            ))
        }
    }

    private suspend fun finishResolution(
        interaction: AgentPendingInteraction,
        failure: CodexFailure? = null,
        succeeded: Boolean,
    ) {
        val presentation = lock.withLock {
            val current = mutableState.value
            if (closed || current.pending.none { it === interaction }) return
            publishState(current.copy(
                pending = if (succeeded) current.pending.filterNot { it === interaction } else current.pending,
                resolvingRequestIds = current.resolvingRequestIds - interaction.requestId,
                failure = failure,
            ))
            presentations.remove(interaction.requestId)
        }
        presentation?.close()
    }

    private suspend fun process(event: AgentEvent) {
        val closedPresentations = lock.withLock {
            if (closed) return
            when (event) {
                is AgentEvent.ApprovalRequested -> {
                    add(
                        AgentPendingApproval(
                            event.requestId,
                            event.conversationId,
                            event.title,
                            event.details,
                        ),
                    )
                    emptyList()
                }
                is AgentEvent.ElicitationRequested -> {
                    add(AgentPendingElicitation(event.elicitation))
                    emptyList()
                }
                is AgentEvent.TurnCompleted -> removeForConversation(event.conversationId)
                is AgentEvent.Failure -> event.conversationId?.let(::removeForConversation).orEmpty()
                else -> emptyList()
            }
        }
        val cleanupFailure = runCatching {
            completeCleanup(closedPresentations.map { presentation -> { presentation.close() } })
        }.exceptionOrNull()
        if (cleanupFailure != null) {
            val failure = cleanupFailure.asCodexOperationException(
                "authorization_browser_failed",
                "Could not close an interaction presentation",
            ).failure
            lock.withLock {
                if (!closed) publishState(mutableState.value.copy(failure = failure))
            }
        }
    }

    private fun add(interaction: AgentPendingInteraction) {
        val current = mutableState.value
        if (current.pending.none { it.requestId == interaction.requestId }) {
            publishState(current.copy(
                pending = current.pending + interaction,
                failure = null,
            ))
        }
    }

    private fun removeForConversation(conversationId: ConversationId): List<CodexAuthorizationPresentation> {
        val current = mutableState.value
        val ids = current.pending.filter { it.conversationId == conversationId }
            .mapTo(mutableSetOf()) { it.requestId }
        if (ids.isEmpty()) return emptyList()
        publishState(current.copy(
            pending = current.pending.filterNot { it.requestId in ids },
            resolvingRequestIds = current.resolvingRequestIds - ids,
        ))
        return ids.mapNotNull(presentations::remove)
    }

    private suspend fun finishPublicResolution(
        interaction: AgentPendingInteraction,
        code: String,
        fallback: String,
    ) {
        var cleanupFailure: Throwable? = null
        withContext(NonCancellable) {
            try {
                finishResolution(interaction, succeeded = true)
            } catch (error: Throwable) {
                cleanupFailure = error
            }
        }
        cleanupFailure?.let { error ->
            val exception = error.asCodexOperationException(code, fallback)
            throw exception
        }
        currentCoroutineContext().ensureActive()
    }

    private fun publishState(state: AgentInteractionState) {
        mutableState.value = state
        mutableApprovals.value = state.pending.filterIsInstance<AgentPendingApproval>()
        mutableElicitations.value = state.pending.filterIsInstance<AgentPendingElicitation>()
    }
}
