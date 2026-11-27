@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentElicitation
import io.github.codex_agent_labs.codexagent.agent.AgentFormField
import io.github.codex_agent_labs.codexagent.agent.AgentFormValue
import io.github.codex_agent_labs.codexagent.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexagent.agent.AgentPendingElicitation
import io.github.codex_agent_labs.codexagent.agent.AgentPendingInteraction
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexInteractions
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.ConversationId
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCPendingInteractionListSnapshot(
    val values: List<AgentPendingInteraction>,
    val owner: CodexInteractions? = null,
) : CodexAgentCSnapshot

@CName("codex_agent_host_state_failed_workspace")
public fun codexAgentHostStateFailedWorkspace(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outWorkspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outWorkspace)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val failed = it.state as? CodexHostState.Failed
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        val workspace = failed.workspace ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outWorkspace,
            createSnapshot(
                contextPointer,
                CodexAgentCWorkspaceSnapshot(CodexWorkspace(workspace.path, workspace.displayName)),
            ),
        )
    }
}

@CName("codex_agent_host_state_preparing_workspace")
public fun codexAgentHostStatePreparingWorkspace(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outWorkspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outWorkspace)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val preparing = it.state as? CodexHostState.Preparing
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(
            outWorkspace,
            createSnapshot(
                contextPointer,
                CodexAgentCWorkspaceSnapshot(
                    CodexWorkspace(preparing.workspace.path, preparing.workspace.displayName),
                ),
            ),
        )
    }
}

@CName("codex_agent_host_state_workspace_required_requirement")
public fun codexAgentHostStateWorkspaceRequiredRequirement(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outRequirement: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outRequirement)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val required = it.state as? CodexHostState.WorkspaceRequired
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(
            outRequirement,
            createSnapshot(
                contextPointer,
                CodexAgentCWorkspaceSelectionRequiredSnapshot(
                    CodexWorkspaceResolution.SelectionRequired(
                        reason = required.requirement.reason,
                        message = required.requirement.message,
                    ),
                ),
            ),
        )
    }
}

@CName("codex_agent_interaction_state_pending_for")
public fun codexAgentInteractionStatePendingFor(
    context: COpaquePointer?,
    state: COpaquePointer?,
    conversationId: COpaquePointer?,
    outPending: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outPending)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractionStateSnapshot>(
        contextPointer,
        state,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { stateSnapshot ->
        withPayload<CodexAgentCConversationIdSnapshot>(
            contextPointer,
            conversationId,
            CodexAgentCHandleKind.SNAPSHOT,
        ) { idSnapshot ->
            val selected = stateSnapshot.value.pendingFor(ConversationId(idSnapshot.value.value))
            val values = if (stateSnapshot.owner == null) {
                selected.map(AgentPendingInteraction::rootOwnedCopy)
            } else {
                selected
            }
            installOutput(
                outPending,
                createSnapshot(
                    contextPointer,
                    CodexAgentCPendingInteractionListSnapshot(values, stateSnapshot.owner),
                ),
            )
        }
    }
}

@CName("codex_agent_pending_interaction_list_destroy")
public fun codexAgentPendingInteractionListDestroy(
    context: COpaquePointer?,
    pending: CPointer<COpaquePointerVar>?,
): Int = destroyRootSnapshot<CodexAgentCPendingInteractionListSnapshot>(context, pending)

@CName("codex_agent_pending_interaction_list_count")
public fun codexAgentPendingInteractionListCount(
    context: COpaquePointer?,
    pending: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPendingInteractionListSnapshot>(
        context,
        pending,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outCount.pointed.value = it.values.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_pending_interaction_list_at")
public fun codexAgentPendingInteractionListAt(
    context: COpaquePointer?,
    pending: COpaquePointer?,
    index: ULong,
    outInteraction: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outInteraction)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPendingInteractionListSnapshot>(
        contextPointer,
        pending,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { snapshot ->
        if (index > Int.MAX_VALUE.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        val interaction = snapshot.values.getOrNull(index.toInt())
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outInteraction,
            createSnapshot(
                contextPointer,
                CodexAgentCPendingInteractionSnapshot(
                    if (snapshot.owner == null) interaction.rootOwnedCopy() else interaction,
                    snapshot.owner,
                ),
            ),
        )
    }
}

private inline fun <reified T : CodexAgentCSnapshot> destroyRootSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
    releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
}

private fun AgentFormValue.rootOwnedCopy(): AgentFormValue = when (this) {
    is AgentFormValue.BooleanValue -> copy()
    is AgentFormValue.Number -> copy()
    is AgentFormValue.Text -> copy()
    is AgentFormValue.TextList -> copy(value = value.toList())
}

private fun AgentFormField.rootOwnedCopy(): AgentFormField = copy(
    options = options.map { it.copy() },
    defaultValue = defaultValue?.rootOwnedCopy(),
)

private fun AgentElicitation.rootOwnedCopy(): AgentElicitation = copy(
    conversationId = ConversationId(conversationId.value),
    form = form?.map(AgentFormField::rootOwnedCopy),
)

private fun AgentPendingInteraction.rootOwnedCopy(): AgentPendingInteraction = when (this) {
    is AgentPendingApproval -> copy(conversationId = ConversationId(conversationId.value))
    is AgentPendingElicitation -> AgentPendingElicitation(elicitation.rootOwnedCopy())
}
