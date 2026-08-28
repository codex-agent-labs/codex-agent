@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalDecision
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingElicitation
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingInteraction
import io.github.codex_agent_labs.codexmobile.agent.CodexInteractions
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

@CName("codex_agent_interaction_state_is_resolving")
public fun codexAgentInteractionStateIsResolving(
    context: COpaquePointer?,
    state: COpaquePointer?,
    interaction: COpaquePointer?,
    outResolving: CPointer<IntVar>?,
): Int = abiStatus {
    if (outResolving == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractionStateSnapshot>(context, state, CodexAgentCHandleKind.SNAPSHOT) { current ->
        withPayload<CodexAgentCPendingInteractionSnapshot>(
            context,
            interaction,
            CodexAgentCHandleKind.SNAPSHOT,
        ) { pending ->
            outResolving.pointed.value = if (current.value.isResolving(pending.value)) 1 else 0
            CODEX_AGENT_STATUS_OK
        }
    }
}

@CName("codex_agent_interactions_open_url")
public fun codexAgentInteractionsOpenUrl(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    pendingElicitation: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val input = interactionInput<CodexAgentCPendingElicitationSnapshot, AgentPendingElicitation>(
        context,
        pendingElicitation,
    ) { it.value to it.owner }
    if (input.status != CODEX_AGENT_STATUS_OK) return@abiStatus input.status
    val (pending, owner) = checkNotNull(input.value)
    startInteractionOperation(
        context,
        interactions,
        pending,
        owner,
        callback,
        userData,
        outOperation,
        validate = {
            if (pending.elicitation.url == null) CODEX_AGENT_STATUS_INVALID_ARGUMENT
            else CODEX_AGENT_STATUS_OK
        },
    ) { wrapper ->
        wrapper.core.openUrl(pending)
    }
}

@CName("codex_agent_interactions_resolve_approval")
public fun codexAgentInteractionsResolveApproval(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    pendingApproval: COpaquePointer?,
    decision: Int,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedDecision = when (decision) {
        0 -> AgentApprovalDecision.ACCEPT
        1 -> AgentApprovalDecision.DECLINE
        else -> return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val input = interactionInput<CodexAgentCPendingApprovalSnapshot, AgentPendingApproval>(
        context,
        pendingApproval,
    ) { it.value to it.owner }
    if (input.status != CODEX_AGENT_STATUS_OK) return@abiStatus input.status
    val (pending, owner) = checkNotNull(input.value)
    startInteractionOperation(context, interactions, pending, owner, callback, userData, outOperation) { wrapper ->
        wrapper.core.resolve(pending, copiedDecision)
    }
}

@CName("codex_agent_interactions_resolve_elicitation")
public fun codexAgentInteractionsResolveElicitation(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    pendingElicitation: COpaquePointer?,
    response: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val input = interactionInput<CodexAgentCPendingElicitationSnapshot, AgentPendingElicitation>(
        context,
        pendingElicitation,
    ) { it.value to it.owner }
    if (input.status != CODEX_AGENT_STATUS_OK) return@abiStatus input.status
    var copiedResponse: AgentElicitationResponse? = null
    val responseStatus = withPayload<CodexAgentCElicitationResponseSnapshot>(
        context,
        response,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copiedResponse = it.value.interactionOperationCopy()
        CODEX_AGENT_STATUS_OK
    }
    if (responseStatus != CODEX_AGENT_STATUS_OK) return@abiStatus responseStatus
    val (pending, owner) = checkNotNull(input.value)
    val copied = checkNotNull(copiedResponse)
    startInteractionOperation(
        context,
        interactions,
        pending,
        owner,
        callback,
        userData,
        outOperation,
        validate = {
            if (pending.elicitation.accepts(copied)) CODEX_AGENT_STATUS_OK
            else CODEX_AGENT_STATUS_INVALID_ARGUMENT
        },
    ) { wrapper ->
        wrapper.core.resolve(pending, copied)
    }
}

private inline fun <reified T : Any, P : AgentPendingInteraction> interactionInput(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    crossinline select: (T) -> Pair<P, CodexInteractions?>,
): CodexAgentCRegistryResult<Pair<P, CodexInteractions?>> {
    var value: Pair<P, CodexInteractions?>? = null
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        value = select(it)
        CODEX_AGENT_STATUS_OK
    }
    return CodexAgentCRegistryResult(status, value)
}

private inline fun startInteractionOperation(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    pending: AgentPendingInteraction,
    owner: CodexInteractions?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    crossinline validate: () -> Int = { CODEX_AGENT_STATUS_OK },
    crossinline execute: suspend (CodexAgentCInteractions) -> Unit,
): Int {
    val acquired = handleRegistry.acquire(context, interactions, CodexAgentCHandleKind.INTERACTIONS)
    if (acquired.status != CODEX_AGENT_STATUS_OK) return acquired.status
    val targetLease = checkNotNull(acquired.value)
    var ownedTargetLease: CodexAgentCHandleLease? = targetLease
    try {
        val wrapper = targetLease.payload as? CodexAgentCInteractions
            ?: return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        if (owner !== wrapper.core) return CODEX_AGENT_STATUS_WRONG_CONTEXT
        if (wrapper.core.state.value.pending.none { it === pending }) {
            return CODEX_AGENT_STATUS_STALE_HANDLE
        }
        val validationStatus = validate()
        if (validationStatus != CODEX_AGENT_STATUS_OK) return validationStatus
        val operationExecute: suspend () -> CodexAgentCOperationResult = {
            execute(wrapper)
            CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
        }
        val status = startCodexAgentCOperation(
            context,
            wrapper.host.runtime,
            callback,
            userData,
            outOperation,
            targetLease,
            operationExecute,
        )
        ownedTargetLease = null
        return status
    } finally {
        ownedTargetLease?.close()
    }
}

private fun AgentElicitationResponse.interactionOperationCopy(): AgentElicitationResponse = copy(
    content = content.entries.associateTo(linkedMapOf()) { (name, value) ->
        name to when (value) {
            is AgentFormValue.BooleanValue -> value.copy()
            is AgentFormValue.Number -> value.copy()
            is AgentFormValue.Text -> value.copy()
            is AgentFormValue.TextList -> value.copy(value = value.value.toList())
        }
    },
)
