@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentInteractionState
import io.github.codex_agent_labs.codexagent.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexagent.agent.AgentPendingElicitation
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexInteractions
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine

internal data class CodexAgentCApprovalsStateSnapshot(
    val values: List<AgentPendingApproval>,
    val owner: CodexInteractions,
) : CodexAgentCSnapshot

internal data class CodexAgentCElicitationsStateSnapshot(
    val values: List<AgentPendingElicitation>,
    val owner: CodexInteractions,
) : CodexAgentCSnapshot

@CName("codex_agent_interactions_state_get")
public fun codexAgentInteractionsStateGet(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowGet(context, interactions, outSnapshot) {
    CodexAgentCInteractionStateSnapshot(it.core.state.value.interactionsFlowCopy(), it.core)
}

@CName("codex_agent_interactions_state_subscribe")
public fun codexAgentInteractionsStateSubscribe(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    callback: CPointer<CFunction<(
        COpaquePointer?,
        COpaquePointer?,
        Int,
        COpaquePointer?,
        Int,
        COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowSubscribe(
    context,
    interactions,
    callback,
    userData,
    outSubscription,
    states = { it.core.state },
) { pointer, value, owner ->
    createSnapshot(pointer, CodexAgentCInteractionStateSnapshot(value.interactionsFlowCopy(), owner))
}

@CName("codex_agent_interactions_approvals_get")
public fun codexAgentInteractionsApprovalsGet(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowGet(context, interactions, outSnapshot) {
    CodexAgentCApprovalsStateSnapshot(it.core.approvals.value.toList(), it.core)
}

@CName("codex_agent_interactions_approvals_subscribe")
public fun codexAgentInteractionsApprovalsSubscribe(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowSubscribe(
    context,
    interactions,
    callback,
    userData,
    outSubscription,
    states = { it.core.approvals },
) { pointer, value, owner ->
    createSnapshot(pointer, CodexAgentCApprovalsStateSnapshot(value.toList(), owner))
}

@CName("codex_agent_interactions_elicitations_get")
public fun codexAgentInteractionsElicitationsGet(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowGet(context, interactions, outSnapshot) {
    CodexAgentCElicitationsStateSnapshot(it.core.elicitations.value.toList(), it.core)
}

@CName("codex_agent_interactions_elicitations_subscribe")
public fun codexAgentInteractionsElicitationsSubscribe(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = interactionsStateFlowSubscribe(
    context,
    interactions,
    callback,
    userData,
    outSubscription,
    states = { it.core.elicitations },
) { pointer, value, owner ->
    createSnapshot(pointer, CodexAgentCElicitationsStateSnapshot(value.toList(), owner))
}

@CName("codex_agent_interactions_state_value")
public fun codexAgentInteractionsStateValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractionStateSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outState,
            createSnapshot(
                contextPointer,
                CodexAgentCInteractionStateSnapshot(it.value.interactionsFlowCopy(), it.owner),
            ),
        )
    }
}

@CName("codex_agent_interactions_approvals_count")
public fun codexAgentInteractionsApprovalsCount(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = interactionsListCount<CodexAgentCApprovalsStateSnapshot>(context, snapshot, outCount) {
    it.values.size
}

@CName("codex_agent_interactions_approvals_at")
public fun codexAgentInteractionsApprovalsAt(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    index: ULong,
    outApproval: CPointer<COpaquePointerVar>?,
): Int = interactionsListAt<CodexAgentCApprovalsStateSnapshot>(
    context,
    snapshot,
    index,
    outApproval,
) {
    CodexAgentCPendingApprovalSnapshot(it.values[index.toInt()], it.owner)
}

@CName("codex_agent_interactions_elicitations_count")
public fun codexAgentInteractionsElicitationsCount(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = interactionsListCount<CodexAgentCElicitationsStateSnapshot>(context, snapshot, outCount) {
    it.values.size
}

@CName("codex_agent_interactions_elicitations_at")
public fun codexAgentInteractionsElicitationsAt(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    index: ULong,
    outElicitation: CPointer<COpaquePointerVar>?,
): Int = interactionsListAt<CodexAgentCElicitationsStateSnapshot>(
    context,
    snapshot,
    index,
    outElicitation,
) {
    CodexAgentCPendingElicitationSnapshot(it.values[index.toInt()], it.owner)
}

private inline fun interactionsStateFlowGet(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
    snapshot: (CodexAgentCInteractions) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractions>(
        contextPointer,
        interactions,
        CodexAgentCHandleKind.INTERACTIONS,
    ) {
        installOutput(outSnapshot, createSnapshot(contextPointer, snapshot(it)))
    }
}

private inline fun <T> interactionsStateFlowSubscribe(
    context: COpaquePointer?,
    interactions: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
    states: (CodexAgentCInteractions) -> StateFlow<T>,
    crossinline snapshot: (
        COpaquePointer,
        T,
        CodexInteractions,
    ) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractions>(
        contextPointer,
        interactions,
        CodexAgentCHandleKind.INTERACTIONS,
    ) { wrapper ->
        val observed = combine(wrapper.host.core.lifecycleState, states(wrapper)) { hostState, value ->
            value to ((hostState as? CodexHostState.Ready)?.agent !== wrapper.owner)
        }
        startCodexAgentCStateSubscription(
            contextPointer,
            wrapper.host.runtime,
            observed,
            snapshot = { (value, _) ->
                val created = snapshot(contextPointer, value, wrapper.core)
                CodexAgentCStateSnapshot(created.status, created.value)
            },
            isTerminal = { (_, terminal) -> terminal },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

private inline fun <reified T : CodexAgentCSnapshot> interactionsListCount(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
    crossinline count: (T) -> Int,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, snapshot, CodexAgentCHandleKind.SNAPSHOT) {
        outCount.pointed.value = count(it).toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> interactionsListAt(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    index: ULong,
    output: CPointer<COpaquePointerVar>?,
    crossinline value: (T) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output) || index > Int.MAX_VALUE.toULong()) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, snapshot, CodexAgentCHandleKind.SNAPSHOT) {
        val size = when (it) {
            is CodexAgentCApprovalsStateSnapshot -> it.values.size
            is CodexAgentCElicitationsStateSnapshot -> it.values.size
            else -> return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        }
        if (index >= size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(output, createSnapshot(contextPointer, value(it)))
    }
}

private fun AgentInteractionState.interactionsFlowCopy(): AgentInteractionState = copy(
    pending = pending.toList(),
    resolvingRequestIds = resolvingRequestIds.toSet(),
    failure = failure?.copy(),
)
