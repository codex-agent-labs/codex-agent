@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar

@CName("codex_agent_invocation_name_copy")
public fun codexAgentInvocationNameCopy(
    context: COpaquePointer?,
    invocation: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCInvocationAggregateSnapshot>(
        context,
        invocation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.name, buffer, capacity, outRequired) }
}

@CName("codex_agent_invocation_key_copy")
public fun codexAgentInvocationKeyCopy(
    context: COpaquePointer?,
    invocation: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCInvocationAggregateSnapshot>(
        context,
        invocation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.key, buffer, capacity, outRequired) }
}

@CName("codex_agent_pending_interaction_request_id_copy")
public fun codexAgentPendingInteractionRequestIdCopy(
    context: COpaquePointer?,
    interaction: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCPendingInteractionSnapshot>(
        context,
        interaction,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.requestId, buffer, capacity, outRequired) }
}

@CName("codex_agent_pending_interaction_conversation_id")
public fun codexAgentPendingInteractionConversationId(
    context: COpaquePointer?,
    interaction: COpaquePointer?,
    outConversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversationId)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPendingInteractionSnapshot>(
        contextPointer,
        interaction,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outConversationId,
            createSnapshot(
                contextPointer,
                CodexAgentCConversationIdSnapshot(ConversationId(it.value.conversationId.value)),
            ),
        )
    }
}

@CName("codex_agent_integration_id_copy")
public fun codexAgentIntegrationIdCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCIntegrationSnapshot>(
        context,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.id, buffer, capacity, outRequired) }
}

@CName("codex_agent_integration_display_name_copy")
public fun codexAgentIntegrationDisplayNameCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCIntegrationSnapshot>(
        context,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { copyUtf8(it.value.displayName, buffer, capacity, outRequired) }
}
