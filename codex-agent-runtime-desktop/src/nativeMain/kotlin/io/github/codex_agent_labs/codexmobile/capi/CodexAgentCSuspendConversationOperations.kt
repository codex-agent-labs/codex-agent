@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConversation
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.pointed

@CName("codex_agent_conversations_list")
public fun codexAgentConversationsList(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCConversations>(
    context,
    conversations,
    CodexAgentCHandleKind.CONVERSATIONS,
    callback,
    userData,
    outOperation,
    runtime = { it.host.runtime },
) { wrapper ->
    CodexAgentCOperationResult(
        CODEX_AGENT_STATUS_OK,
        valueKind = CodexAgentCOperationValueKind.CONVERSATION_SUMMARIES,
        value = wrapper.core.list().map { it.suspendConversationOwnedCopy() },
    )
}

@CName("codex_agent_conversations_read")
public fun codexAgentConversationsRead(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    conversationId: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedId = copySuspendConversationId(context, conversationId)
    if (copiedId.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedId.status
    startCodexAgentCTargetOperation<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
        callback,
        userData,
        outOperation,
        runtime = { it.host.runtime },
    ) { wrapper ->
        CodexAgentCOperationResult(
            CODEX_AGENT_STATUS_OK,
            valueKind = CodexAgentCOperationValueKind.CONVERSATION_VALUE,
            value = wrapper.core.read(checkNotNull(copiedId.value)).suspendConversationOwnedCopy(),
        )
    }
}

@CName("codex_agent_conversations_rename")
public fun codexAgentConversationsRename(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    conversationId: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedId = copySuspendConversationId(context, conversationId)
    if (copiedId.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedId.status
    val copiedName = requireNotNull(name).pointed.readUtf8()
    startCodexAgentCTargetOperation<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
        callback,
        userData,
        outOperation,
        runtime = { it.host.runtime },
    ) { wrapper ->
        wrapper.core.rename(checkNotNull(copiedId.value), copiedName)
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_conversations_delete")
public fun codexAgentConversationsDelete(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    conversationId: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedId = copySuspendConversationId(context, conversationId)
    if (copiedId.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedId.status
    startCodexAgentCTargetOperation<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
        callback,
        userData,
        outOperation,
        runtime = { it.host.runtime },
    ) { wrapper ->
        wrapper.core.delete(checkNotNull(copiedId.value))
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_conversation_send_request")
public fun codexAgentConversationSendRequest(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    request: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedRequest = copySuspendTurnRequest(context, request)
    if (copiedRequest.status != CODEX_AGENT_STATUS_OK) return@abiStatus copiedRequest.status
    startCodexAgentCTargetOperation<CodexAgentCConversation>(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
        callback,
        userData,
        outOperation,
        runtime = { it.runtime },
    ) { wrapper ->
        wrapper.core.send(checkNotNull(copiedRequest.value))
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_conversation_run_shell_command")
public fun codexAgentConversationRunShellCommand(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    command: CPointer<codex_agent_string_view>?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedCommand = requireNotNull(command).pointed.readUtf8()
    startCodexAgentCTargetOperation<CodexAgentCConversation>(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
        callback,
        userData,
        outOperation,
        runtime = { it.runtime },
    ) { wrapper ->
        wrapper.core.runShellCommand(copiedCommand)
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_conversation_reload")
public fun codexAgentConversationReload(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCConversation>(
    context,
    conversation,
    CodexAgentCHandleKind.CONVERSATION,
    callback,
    userData,
    outOperation,
    runtime = { it.runtime },
) { wrapper ->
    wrapper.core.reload()
    CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
}

private fun copySuspendConversationId(
    context: COpaquePointer?,
    conversationId: COpaquePointer?,
): CodexAgentCRegistryResult<ConversationId> {
    var copied: ConversationId? = null
    val status = withPayload<CodexAgentCConversationIdSnapshot>(
        context,
        conversationId,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copied = ConversationId(it.value.value)
        CODEX_AGENT_STATUS_OK
    }
    return CodexAgentCRegistryResult(status, copied)
}

private fun copySuspendTurnRequest(
    context: COpaquePointer?,
    request: COpaquePointer?,
): CodexAgentCRegistryResult<AgentTurnRequest> {
    var copied: AgentTurnRequest? = null
    val status = withPayload<CodexAgentCTurnRequestSnapshot>(
        context,
        request,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copied = it.value.suspendConversationOwnedCopy()
        CODEX_AGENT_STATUS_OK
    }
    return CodexAgentCRegistryResult(status, copied)
}

private fun AgentInvocation.suspendConversationOwnedCopy(): AgentInvocation = when (this) {
    is AgentInvocation.Plugin -> copy()
    is AgentInvocation.Skill -> copy()
}

private fun AgentMessage.suspendConversationOwnedCopy(): AgentMessage = copy(
    capabilities = capabilities.toSet(),
    invocations = invocations.map { it.suspendConversationOwnedCopy() },
)

private fun AgentConversationSummary.suspendConversationOwnedCopy(): AgentConversationSummary = copy(
    conversationId = ConversationId(conversationId.value),
)

private fun AgentConversation.suspendConversationOwnedCopy(): AgentConversation = AgentConversation(
    summary = summary.suspendConversationOwnedCopy(),
    messages = messages.map { it.suspendConversationOwnedCopy() },
)

private fun AgentTurnRequest.suspendConversationOwnedCopy(): AgentTurnRequest = copy(
    capabilities = capabilities.toSet(),
    invocations = invocations.map { it.suspendConversationOwnedCopy() },
)
