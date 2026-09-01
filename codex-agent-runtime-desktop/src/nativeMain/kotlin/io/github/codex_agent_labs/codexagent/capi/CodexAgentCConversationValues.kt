@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexagent.agent.AgentConversationSummary
import io.github.codex_agent_labs.codexagent.agent.CodexFailure
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexagent.agent.ConversationId
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCConversationIdSnapshot(
    val value: ConversationId,
) : CodexAgentCSnapshot

internal data class CodexAgentCConversationSummarySnapshot(
    val value: AgentConversationSummary,
) : CodexAgentCSnapshot

internal data class CodexAgentCWorkspaceSnapshot(
    val value: CodexWorkspace,
) : CodexAgentCSnapshot

internal data class CodexAgentCWorkspaceAvailableSnapshot(
    val value: CodexWorkspaceResolution.Available,
) : CodexAgentCSnapshot

internal data class CodexAgentCWorkspaceSelectionRequiredSnapshot(
    val value: CodexWorkspaceResolution.SelectionRequired,
) : CodexAgentCSnapshot

@CName("codex_agent_failure_create")
public fun codexAgentFailureCreate(
    context: COpaquePointer?,
    code: CPointer<codex_agent_string_view>?,
    message: CPointer<codex_agent_string_view>?,
    isRecoverable: Int,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure) || (isRecoverable != 0 && isRecoverable != 1)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outFailure,
        createFailure(
            pointer,
            CodexFailure(code.readUtf8(), message.readUtf8(), isRecoverable == 1),
        ),
    )
}

@CName("codex_agent_conversation_id_create")
public fun codexAgentConversationIdCreate(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outConversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversationId)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outConversationId,
        createSnapshot(pointer, CodexAgentCConversationIdSnapshot(ConversationId(value.readUtf8()))),
    )
}

@CName("codex_agent_conversation_id_destroy")
public fun codexAgentConversationIdDestroy(
    context: COpaquePointer?,
    conversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    releaseTypedSnapshot<CodexAgentCConversationIdSnapshot>(context, conversationId)
}

@CName("codex_agent_conversation_id_value_copy")
public fun codexAgentConversationIdValueCopy(
    context: COpaquePointer?,
    conversationId: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCConversationIdSnapshot>(
        context,
        conversationId,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.value, buffer, capacity, outRequired) }
}

@CName("codex_agent_conversation_summary_create")
public fun codexAgentConversationSummaryCreate(
    context: COpaquePointer?,
    conversationId: COpaquePointer?,
    title: CPointer<codex_agent_string_view>?,
    updatedAtEpochSeconds: Long,
    outSummary: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSummary)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedTitle = title.readUtf8()
    withPayload<CodexAgentCConversationIdSnapshot>(
        context,
        conversationId,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { id ->
        installOutput(
            outSummary,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCConversationSummarySnapshot(
                    AgentConversationSummary(
                        conversationId = ConversationId(id.value.value),
                        title = copiedTitle,
                        updatedAtEpochSeconds = updatedAtEpochSeconds,
                    ),
                ),
            ),
        )
    }
}

@CName("codex_agent_conversation_summary_destroy")
public fun codexAgentConversationSummaryDestroy(
    context: COpaquePointer?,
    summary: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    releaseTypedSnapshot<CodexAgentCConversationSummarySnapshot>(context, summary)
}

@CName("codex_agent_conversation_summary_conversation_id")
public fun codexAgentConversationSummaryConversationId(
    context: COpaquePointer?,
    summary: COpaquePointer?,
    outConversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversationId)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationSummarySnapshot>(
        context,
        summary,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { snapshot ->
        installOutput(
            outConversationId,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCConversationIdSnapshot(ConversationId(snapshot.value.conversationId.value)),
            ),
        )
    }
}

@CName("codex_agent_conversation_summary_title_copy")
public fun codexAgentConversationSummaryTitleCopy(
    context: COpaquePointer?,
    summary: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCConversationSummarySnapshot>(
        context,
        summary,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.title, buffer, capacity, outRequired) }
}

@CName("codex_agent_conversation_summary_updated_at_epoch_seconds")
public fun codexAgentConversationSummaryUpdatedAtEpochSeconds(
    context: COpaquePointer?,
    summary: COpaquePointer?,
    outUpdatedAtEpochSeconds: CPointer<LongVar>?,
): Int = abiStatus {
    if (outUpdatedAtEpochSeconds == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationSummarySnapshot>(
        context,
        summary,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outUpdatedAtEpochSeconds.pointed.value = it.value.updatedAtEpochSeconds
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_workspace_create")
public fun codexAgentWorkspaceCreate(
    context: COpaquePointer?,
    path: CPointer<codex_agent_string_view>?,
    hasDisplayName: Int,
    displayName: CPointer<codex_agent_string_view>?,
    outWorkspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outWorkspace) || (hasDisplayName != 0 && hasDisplayName != 1)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedPath = path.readUtf8()
    val workspace = if (hasDisplayName == 0) {
        displayName.requireEmpty()
        CodexWorkspace(copiedPath)
    } else {
        CodexWorkspace(copiedPath, displayName.readUtf8())
    }
    installOutput(outWorkspace, createSnapshot(pointer, CodexAgentCWorkspaceSnapshot(workspace)))
}

@CName("codex_agent_workspace_destroy")
public fun codexAgentWorkspaceDestroy(
    context: COpaquePointer?,
    workspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    releaseTypedSnapshot<CodexAgentCWorkspaceSnapshot>(context, workspace)
}

@CName("codex_agent_workspace_path_copy")
public fun codexAgentWorkspacePathCopy(
    context: COpaquePointer?,
    workspace: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCWorkspaceSnapshot>(context, workspace, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(it.value.path, buffer, capacity, outRequired)
    }
}

@CName("codex_agent_workspace_display_name_copy")
public fun codexAgentWorkspaceDisplayNameCopy(
    context: COpaquePointer?,
    workspace: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCWorkspaceSnapshot>(context, workspace, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(it.value.displayName, buffer, capacity, outRequired)
    }
}

@CName("codex_agent_workspace_resolution_available_create")
public fun codexAgentWorkspaceResolutionAvailableCreate(
    context: COpaquePointer?,
    workspace: COpaquePointer?,
    outAvailable: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outAvailable)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCWorkspaceSnapshot>(context, workspace, CodexAgentCHandleKind.SNAPSHOT) {
        val copied = CodexWorkspace(it.value.path, it.value.displayName)
        installOutput(
            outAvailable,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCWorkspaceAvailableSnapshot(CodexWorkspaceResolution.Available(copied)),
            ),
        )
    }
}

@CName("codex_agent_workspace_resolution_available_destroy")
public fun codexAgentWorkspaceResolutionAvailableDestroy(
    context: COpaquePointer?,
    available: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    releaseTypedSnapshot<CodexAgentCWorkspaceAvailableSnapshot>(context, available)
}

@CName("codex_agent_workspace_resolution_available_workspace")
public fun codexAgentWorkspaceResolutionAvailableWorkspace(
    context: COpaquePointer?,
    available: COpaquePointer?,
    outWorkspace: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outWorkspace)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCWorkspaceAvailableSnapshot>(
        context,
        available,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val copied = CodexWorkspace(it.value.workspace.path, it.value.workspace.displayName)
        installOutput(
            outWorkspace,
            createSnapshot(checkNotNull(context), CodexAgentCWorkspaceSnapshot(copied)),
        )
    }
}

@CName("codex_agent_workspace_selection_required_create")
public fun codexAgentWorkspaceSelectionRequiredCreate(
    context: COpaquePointer?,
    reason: Int,
    message: CPointer<codex_agent_string_view>?,
    outRequired: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outRequired)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val required = CodexWorkspaceResolution.SelectionRequired(
        reason = reason.toWorkspaceSelectionReason(),
        message = message.readUtf8(),
    )
    installOutput(
        outRequired,
        createSnapshot(pointer, CodexAgentCWorkspaceSelectionRequiredSnapshot(required)),
    )
}

@CName("codex_agent_workspace_selection_required_destroy")
public fun codexAgentWorkspaceSelectionRequiredDestroy(
    context: COpaquePointer?,
    required: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    releaseTypedSnapshot<CodexAgentCWorkspaceSelectionRequiredSnapshot>(context, required)
}

@CName("codex_agent_workspace_selection_required_reason")
public fun codexAgentWorkspaceSelectionRequiredReason(
    context: COpaquePointer?,
    required: COpaquePointer?,
    outReason: CPointer<IntVar>?,
): Int = abiStatus {
    if (outReason == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCWorkspaceSelectionRequiredSnapshot>(
        context,
        required,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outReason.pointed.value = it.value.reason.toCValue()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_workspace_selection_required_message_copy")
public fun codexAgentWorkspaceSelectionRequiredMessageCopy(
    context: COpaquePointer?,
    required: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCWorkspaceSelectionRequiredSnapshot>(
        context,
        required,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.message, buffer, capacity, outRequired) }
}

@CName("codex_agent_approval_preset_display_name_copy")
public fun codexAgentApprovalPresetDisplayNameCopy(
    preset: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    copyUtf8(preset.toApprovalPreset().displayName, buffer, capacity, outRequired)
}

private fun CPointer<codex_agent_string_view>?.readUtf8(): String = requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.requireEmpty(): Unit = requireNotNull(this).pointed.run {
    require(data == null && size == 0uL)
}

private inline fun <reified T : CodexAgentCSnapshot> releaseTypedSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int {
    if (slot == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return CODEX_AGENT_STATUS_OK
    val typeStatus = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (typeStatus != CODEX_AGENT_STATUS_OK) return typeStatus
    return releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
}

private fun Int.toApprovalPreset(): AgentApprovalPreset = when (this) {
    0 -> AgentApprovalPreset.NEVER
    1 -> AgentApprovalPreset.AUTO_REVIEW
    2 -> AgentApprovalPreset.ASK_ME
    3 -> AgentApprovalPreset.STRICT
    else -> throw IllegalArgumentException("Unknown approval preset")
}

private fun Int.toWorkspaceSelectionReason(): CodexWorkspaceSelectionReason = when (this) {
    0 -> CodexWorkspaceSelectionReason.NOT_SELECTED
    1 -> CodexWorkspaceSelectionReason.NOT_FOUND
    2 -> CodexWorkspaceSelectionReason.ACCESS_REVOKED
    3 -> CodexWorkspaceSelectionReason.INVALID_SELECTION
    else -> throw IllegalArgumentException("Unknown workspace selection reason")
}

private fun CodexWorkspaceSelectionReason.toCValue(): Int = when (this) {
    CodexWorkspaceSelectionReason.NOT_SELECTED -> 0
    CodexWorkspaceSelectionReason.NOT_FOUND -> 1
    CodexWorkspaceSelectionReason.ACCESS_REVOKED -> 2
    CodexWorkspaceSelectionReason.INVALID_SELECTION -> 3
}
