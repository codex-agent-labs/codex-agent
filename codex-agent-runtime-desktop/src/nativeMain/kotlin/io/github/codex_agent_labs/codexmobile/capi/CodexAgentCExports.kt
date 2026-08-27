@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexOperationException
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_conversation_open_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_host_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

@CName("codex_agent_host_create")
public fun codexAgentHostCreate(
    context: COpaquePointer?,
    options: CPointer<codex_agent_host_options>?,
    outHost: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHost)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextLease = handleRegistry.acquireContext(context)
    if (contextLease.status != CODEX_AGENT_STATUS_OK) return@abiStatus contextLease.status
    val lease = checkNotNull(contextLease.value)
    try {
        val runtime = lease.payload as? CodexAgentCContextRuntime
            ?: return@abiStatus CODEX_AGENT_STATUS_INTERNAL_ERROR
        val host = parseHostOptions(options).createHost(runtime)
        installOutput(
            outHost,
            handleRegistry.createEntry(
                checkNotNull(context),
                CodexAgentCHandleKind.HOST,
                host,
            ),
        )
    } finally {
        lease.close()
    }
}

@CName("codex_agent_host_retain")
public fun codexAgentHostRetain(
    context: COpaquePointer?,
    host: COpaquePointer?,
    outHost: CPointer<COpaquePointerVar>?,
): Int = retainHandle(context, host, outHost, CodexAgentCHandleKind.HOST)

@CName("codex_agent_host_release")
public fun codexAgentHostRelease(
    context: COpaquePointer?,
    host: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, host, CodexAgentCHandleKind.HOST)

@CName("codex_agent_host_state_get")
public fun codexAgentHostStateGet(
    context: COpaquePointer?,
    host: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHost>(
        context,
        host,
        CodexAgentCHandleKind.HOST,
        includeClosed = true,
    ) { wrapper ->
        installOutput(
            outSnapshot,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCHostStateSnapshot(wrapper.core, wrapper.core.lifecycleState.value),
            ),
        )
    }
}

@CName("codex_agent_agent_retain")
public fun codexAgentAgentRetain(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outAgent: CPointer<COpaquePointerVar>?,
): Int = retainHandle(context, agent, outAgent, CodexAgentCHandleKind.AGENT)

@CName("codex_agent_agent_release")
public fun codexAgentAgentRelease(
    context: COpaquePointer?,
    agent: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, agent, CodexAgentCHandleKind.AGENT)

@CName("codex_agent_agent_conversations")
public fun codexAgentAgentConversations(
    context: COpaquePointer?,
    agent: COpaquePointer?,
    outConversations: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversations)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAgent>(context, agent, CodexAgentCHandleKind.AGENT) { wrapper ->
        installOutput(
            outConversations,
            wrapper.projectConversations(checkNotNull(context), checkNotNull(agent)),
        )
    }
}

@CName("codex_agent_conversations_retain")
public fun codexAgentConversationsRetain(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    outConversations: CPointer<COpaquePointerVar>?,
): Int = retainHandle(
    context,
    conversations,
    outConversations,
    CodexAgentCHandleKind.CONVERSATIONS,
)

@CName("codex_agent_conversations_release")
public fun codexAgentConversationsRelease(
    context: COpaquePointer?,
    conversations: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, conversations, CodexAgentCHandleKind.CONVERSATIONS)

@CName("codex_agent_conversations_active_get")
public fun codexAgentConversationsActiveGet(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
    ) { wrapper ->
        installOutput(
            outSnapshot,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCActiveConversationSnapshot(wrapper.core, wrapper.core.active.value),
            ),
        )
    }
}

@CName("codex_agent_conversation_retain")
public fun codexAgentConversationRetain(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outConversation: CPointer<COpaquePointerVar>?,
): Int = retainHandle(
    context,
    conversation,
    outConversation,
    CodexAgentCHandleKind.CONVERSATION,
)

@CName("codex_agent_conversation_release")
public fun codexAgentConversationRelease(
    context: COpaquePointer?,
    conversation: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, conversation, CodexAgentCHandleKind.CONVERSATION)

@CName("codex_agent_conversation_is_same")
public fun codexAgentConversationIsSame(
    context: COpaquePointer?,
    left: COpaquePointer?,
    right: COpaquePointer?,
    outSame: CPointer<IntVar>?,
): Int = abiStatus {
    if (outSame == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversation>(
        context,
        left,
        CodexAgentCHandleKind.CONVERSATION,
    ) { leftWrapper ->
        withPayload<CodexAgentCConversation>(
            context,
            right,
            CodexAgentCHandleKind.CONVERSATION,
        ) { rightWrapper ->
            outSame.pointed.value = if (leftWrapper.core === rightWrapper.core) 1 else 0
            CODEX_AGENT_STATUS_OK
        }
    }
}

@CName("codex_agent_conversation_state_get")
public fun codexAgentConversationStateGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversation>(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
        includeClosed = true,
    ) { wrapper ->
        installOutput(
            outSnapshot,
            createSnapshot(
                checkNotNull(context),
                CodexAgentCConversationStateSnapshot(wrapper.core.state.value),
            ),
        )
    }
}

@CName("codex_agent_host_select_workspace")
public fun codexAgentHostSelectWorkspace(
    context: COpaquePointer?,
    host: COpaquePointer?,
    selection: CPointer<codex_agent_path_workspace_selection>?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsed = parseWorkspaceSelection(selection)
    val acquired = handleRegistry.acquireAndInvalidateChildren(
        context,
        host,
        CodexAgentCHandleKind.HOST,
    )
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val targetLease = checkNotNull(acquired.value)
    val wrapper = targetLease.payload as? CodexAgentCHost
    if (wrapper == null) {
        targetLease.close()
        return@abiStatus CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
    }
    wrapper.clearInvalidatedChildren(checkNotNull(context))
    startCodexAgentCOperation(
        context,
        wrapper.runtime,
        callback,
        userData,
        outOperation,
        targetLease,
    ) {
        wrapper.core.selectWorkspace(parsed)
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_host_close")
public fun codexAgentHostClose(
    context: COpaquePointer?,
    host: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val acquired = handleRegistry.acquireIncludingClosed(
        context,
        host,
        CodexAgentCHandleKind.HOST,
    )
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val closeTarget = checkNotNull(acquired.value)
    val owned = closeTarget.payload as? CodexAgentCHost
    if (owned == null) {
        closeTarget.close()
        return@abiStatus CODEX_AGENT_STATUS_INTERNAL_ERROR
    }
    startCodexAgentCOperation(
        context,
        owned.runtime,
        callback,
        userData,
        outOperation,
        closeTarget,
    ) {
        val status = handleRegistry.semanticClose(
            context,
            host,
            CodexAgentCHandleKind.HOST,
            closeTarget,
        ) {
            try {
                (it as CodexAgentCHost).core.close()
                CODEX_AGENT_STATUS_OK
            } catch (error: CodexOperationException) {
                owned.closeFailure.store(error.failure)
                CODEX_AGENT_STATUS_OPERATION_FAILED
            }
        }
        CodexAgentCOperationResult(
            status,
            failure = owned.closeFailure.load().takeIf {
                status == CODEX_AGENT_STATUS_OPERATION_FAILED
            },
        )
    }
}

@CName("codex_agent_host_state_subscribe")
public fun codexAgentHostStateSubscribe(
    context: COpaquePointer?,
    host: COpaquePointer?,
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
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    withPayload<CodexAgentCHost>(context, host, CodexAgentCHandleKind.HOST) { wrapper ->
        startCodexAgentCStateSubscription(
            context,
            wrapper.runtime,
            wrapper.core.lifecycleState,
            snapshot = { state ->
                createSnapshot(
                    checkNotNull(context),
                    CodexAgentCHostStateSnapshot(wrapper.core, state),
                ).asStateSnapshot()
            },
            isTerminal = { it is CodexHostState.Closed },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

@CName("codex_agent_conversations_active_subscribe")
public fun codexAgentConversationsActiveSubscribe(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
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
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    withPayload<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
    ) { wrapper ->
        startCodexAgentCStateSubscription(
            context,
            wrapper.host.runtime,
            wrapper.activeState(),
            snapshot = { state ->
                createSnapshot(
                    checkNotNull(context),
                    CodexAgentCActiveConversationSnapshot(wrapper.core, state.conversation),
                ).asStateSnapshot()
            },
            isTerminal = { it.terminal },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

@CName("codex_agent_conversations_open")
public fun codexAgentConversationsOpen(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    options: CPointer<codex_agent_conversation_open_options>?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsed = parseOpenOptions(options)
    val acquired = handleRegistry.acquireAndInvalidateChildren(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
    )
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val targetLease = checkNotNull(acquired.value)
    val wrapper = targetLease.payload as? CodexAgentCConversations
    if (wrapper == null) {
        targetLease.close()
        return@abiStatus CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
    }
    wrapper.clearInvalidatedChildren(checkNotNull(context))
    startCodexAgentCOperation(
        context,
        wrapper.host.runtime,
        callback,
        userData,
        outOperation,
        targetLease,
    ) {
        CodexAgentCOperationResult(
            CODEX_AGENT_STATUS_OK,
            conversation = wrapper.core.open(parsed.conversationId, parsed.settings),
            conversations = wrapper.core,
        )
    }
}

@CName("codex_agent_conversation_send")
public fun codexAgentConversationSend(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    prompt: CPointer<codex_agent_string_view>?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    val parsedPrompt = requireNotNull(prompt).pointed.readUtf8()
    startConversationOperation(
        context,
        conversation,
        callback,
        userData,
        outOperation,
    ) { it.core.send(parsedPrompt) }
}

@CName("codex_agent_conversation_cancel_turn")
public fun codexAgentConversationCancelTurn(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startConversationOperation(
    context,
    conversation,
    callback,
    userData,
    outOperation,
) { it.core.cancelTurn() }

@CName("codex_agent_conversation_close")
public fun codexAgentConversationClose(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val acquired = handleRegistry.acquireIncludingClosed(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
    )
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val closeTarget = checkNotNull(acquired.value)
    val owned = closeTarget.payload as? CodexAgentCConversation
    if (owned == null) {
        closeTarget.close()
        return@abiStatus CODEX_AGENT_STATUS_INTERNAL_ERROR
    }
    startCodexAgentCOperation(
        context,
        owned.runtime,
        callback,
        userData,
        outOperation,
        closeTarget,
    ) {
        val status = handleRegistry.semanticClose(
            context,
            conversation,
            CodexAgentCHandleKind.CONVERSATION,
            closeTarget,
        ) {
            try {
                (it as CodexAgentCConversation).core.close()
                CODEX_AGENT_STATUS_OK
            } catch (error: CodexOperationException) {
                owned.closeFailure.store(error.failure)
                CODEX_AGENT_STATUS_OPERATION_FAILED
            }
        }
        CodexAgentCOperationResult(
            status,
            failure = owned.closeFailure.load().takeIf {
                status == CODEX_AGENT_STATUS_OPERATION_FAILED
            },
        )
    }
}

@CName("codex_agent_conversation_state_subscribe")
public fun codexAgentConversationStateSubscribe(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
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
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    withPayload<CodexAgentCConversation>(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
    ) { wrapper ->
        startCodexAgentCStateSubscription(
            context,
            wrapper.runtime,
            wrapper.core.state,
            snapshot = { state ->
                createSnapshot(
                    checkNotNull(context),
                    CodexAgentCConversationStateSnapshot(state),
                ).asStateSnapshot()
            },
            isTerminal = { it.status == AgentConversationStatus.CLOSED },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

@CName("codex_agent_operation_cancel")
public fun codexAgentOperationCancel(
    context: COpaquePointer?,
    operation: COpaquePointer?,
): Int = abiStatus { cancelCodexAgentCOperation(context, operation) }

@CName("codex_agent_operation_result")
public fun codexAgentOperationResult(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outResult: CPointer<IntVar>?,
): Int = abiStatus {
    if (outResult == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val result = queryCodexAgentCOperation(context, operation)
    if (result.status == CODEX_AGENT_STATUS_OK) {
        outResult.pointed.value = checkNotNull(result.value).status
    }
    result.status
}

@CName("codex_agent_operation_conversation")
public fun codexAgentOperationConversation(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    operation: COpaquePointer?,
    outConversation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val result = queryCodexAgentCOperation(context, operation)
    if (result.status != CODEX_AGENT_STATUS_OK) return@abiStatus result.status
    val conversation = checkNotNull(result.value).conversation
        ?: return@abiStatus CODEX_AGENT_STATUS_NOT_READY
    withPayload<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
    ) {
        if (checkNotNull(result.value).conversations !== it.core) {
            return@withPayload CODEX_AGENT_STATUS_WRONG_CONTEXT
        }
        if (it.core.active.value !== conversation) {
            return@withPayload CODEX_AGENT_STATUS_STALE_HANDLE
        }
        installOutput(
            outConversation,
            it.projectConversation(
                checkNotNull(context),
                checkNotNull(conversations),
                conversation,
                allowLeasedTransitionParent = true,
            ),
        )
    }
}

@CName("codex_agent_operation_failure")
public fun codexAgentOperationFailure(
    context: COpaquePointer?,
    operation: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val result = queryCodexAgentCOperation(context, operation)
    if (result.status != CODEX_AGENT_STATUS_OK) return@abiStatus result.status
    val failure = checkNotNull(result.value).failure ?: return@abiStatus CODEX_AGENT_STATUS_NOT_READY
    installOutput(outFailure, createFailure(checkNotNull(context), failure))
}

@CName("codex_agent_operation_destroy")
public fun codexAgentOperationDestroy(
    context: COpaquePointer?,
    operation: CPointer<COpaquePointerVar>?,
): Int = destroyAsyncHandle(context, operation, ::destroyCodexAgentCOperation)

@CName("codex_agent_subscription_destroy")
public fun codexAgentSubscriptionDestroy(
    context: COpaquePointer?,
    subscription: CPointer<COpaquePointerVar>?,
): Int = destroyAsyncHandle(context, subscription, ::destroyCodexAgentCStateSubscription)

@CName("codex_agent_snapshot_destroy")
public fun codexAgentSnapshotDestroy(
    context: COpaquePointer?,
    snapshot: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, snapshot, CodexAgentCHandleKind.SNAPSHOT)

@CName("codex_agent_host_state_kind")
public fun codexAgentHostStateKind(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = abiStatus {
    if (outKind == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outKind.pointed.value = it.state.kind()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_host_state_agent")
public fun codexAgentHostStateAgent(
    context: COpaquePointer?,
    host: COpaquePointer?,
    snapshot: COpaquePointer?,
    outAgent: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outAgent)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHost>(context, host, CodexAgentCHandleKind.HOST) { hostWrapper ->
        withPayload<CodexAgentCHostStateSnapshot>(
            context,
            snapshot,
            CodexAgentCHandleKind.SNAPSHOT,
        ) { stateSnapshot ->
            if (stateSnapshot.owner !== hostWrapper.core) {
                return@withPayload CODEX_AGENT_STATUS_WRONG_CONTEXT
            }
            val ready = stateSnapshot.state as? CodexHostState.Ready
                ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
            val current = hostWrapper.core.lifecycleState.value as? CodexHostState.Ready
            if (current?.agent !== ready.agent) return@withPayload CODEX_AGENT_STATUS_STALE_HANDLE
            installOutput(
                outAgent,
                hostWrapper.projectAgent(checkNotNull(context), checkNotNull(host), ready.agent),
            )
        }
    }
}

@CName("codex_agent_host_state_failure")
public fun codexAgentHostStateFailure(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val failed = it.state as? CodexHostState.Failed
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(outFailure, createFailure(checkNotNull(context), failed.failure))
    }
}

@CName("codex_agent_host_state_has_workspace")
public fun codexAgentHostStateHasWorkspace(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outHasWorkspace: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasWorkspace == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasWorkspace.pointed.value = if (it.state.workspaceOrNull() == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_host_state_workspace_path_copy")
public fun codexAgentHostStateWorkspacePathCopy(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyHostWorkspace(context, snapshot, buffer, capacity, outRequired) { it.path }

@CName("codex_agent_host_state_workspace_display_name_copy")
public fun codexAgentHostStateWorkspaceDisplayNameCopy(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyHostWorkspace(context, snapshot, buffer, capacity, outRequired) { it.displayName }

@CName("codex_agent_host_state_requirement_reason")
public fun codexAgentHostStateRequirementReason(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outReason: CPointer<IntVar>?,
): Int = abiStatus {
    if (outReason == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val required = it.state as? CodexHostState.WorkspaceRequired
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        outReason.pointed.value = required.requirement.reason.ordinal
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_host_state_requirement_message_copy")
public fun codexAgentHostStateRequirementMessageCopy(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val required = it.state as? CodexHostState.WorkspaceRequired
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        copyUtf8(required.requirement.message, buffer, capacity, outRequired)
    }
}

@CName("codex_agent_active_conversation")
public fun codexAgentActiveConversation(
    context: COpaquePointer?,
    conversations: COpaquePointer?,
    snapshot: COpaquePointer?,
    outConversation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversations>(
        context,
        conversations,
        CodexAgentCHandleKind.CONVERSATIONS,
    ) { conversationsWrapper ->
        withPayload<CodexAgentCActiveConversationSnapshot>(
            context,
            snapshot,
            CodexAgentCHandleKind.SNAPSHOT,
        ) { active ->
            if (active.owner !== conversationsWrapper.core) {
                return@withPayload CODEX_AGENT_STATUS_WRONG_CONTEXT
            }
            if (conversationsWrapper.core.active.value !== active.conversation) {
                return@withPayload CODEX_AGENT_STATUS_STALE_HANDLE
            }
            val conversation = active.conversation ?: return@withPayload CODEX_AGENT_STATUS_OK
            installOutput(
                outConversation,
                conversationsWrapper.projectConversation(
                    checkNotNull(context),
                    checkNotNull(conversations),
                    conversation,
                ),
            )
        }
    }
}

@CName("codex_agent_conversation_state_status")
public fun codexAgentConversationStateStatus(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outStatus: CPointer<IntVar>?,
): Int = abiStatus {
    if (outStatus == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outStatus.pointed.value = it.state.status.ordinal
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_conversation_state_failure")
public fun codexAgentConversationStateFailure(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val failure = it.state.failure ?: return@withPayload CODEX_AGENT_STATUS_OK
        installOutput(outFailure, createFailure(checkNotNull(context), failure))
    }
}

@CName("codex_agent_failure_retain")
public fun codexAgentFailureRetain(
    context: COpaquePointer?,
    failure: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = retainHandle(context, failure, outFailure, CodexAgentCHandleKind.FAILURE)

@CName("codex_agent_failure_release")
public fun codexAgentFailureRelease(
    context: COpaquePointer?,
    failure: CPointer<COpaquePointerVar>?,
): Int = releaseHandle(context, failure, CodexAgentCHandleKind.FAILURE)

@CName("codex_agent_failure_code_copy")
public fun codexAgentFailureCodeCopy(
    context: COpaquePointer?,
    failure: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFailure(context, failure, buffer, capacity, outRequired) { it.code }

@CName("codex_agent_failure_message_copy")
public fun codexAgentFailureMessageCopy(
    context: COpaquePointer?,
    failure: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFailure(context, failure, buffer, capacity, outRequired) { it.message }

@CName("codex_agent_failure_is_recoverable")
public fun codexAgentFailureIsRecoverable(
    context: COpaquePointer?,
    failure: COpaquePointer?,
    outIsRecoverable: CPointer<IntVar>?,
): Int = abiStatus {
    if (outIsRecoverable == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexFailure>(context, failure, CodexAgentCHandleKind.FAILURE) {
        outIsRecoverable.pointed.value = if (it.isRecoverable) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

private fun retainHandle(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    kind: CodexAgentCHandleKind,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(output, handleRegistry.retain(context, handle, kind))
}

internal fun releaseHandle(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
    kind: CodexAgentCHandleKind,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = handleRegistry.release(context, handle, kind)
    if (status == CODEX_AGENT_STATUS_OK) slot.pointed.value = null
    status
}

internal fun validEmptyOutput(output: CPointer<COpaquePointerVar>?): Boolean =
    output != null && output.pointed.value == null

internal fun installOutput(
    output: CPointer<COpaquePointerVar>?,
    result: CodexAgentCRegistryResult<COpaquePointer>,
): Int {
    if (result.status == CODEX_AGENT_STATUS_OK) {
        checkNotNull(output).pointed.value = checkNotNull(result.value)
    }
    return result.status
}

internal inline fun <reified T : Any> withPayload(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    kind: CodexAgentCHandleKind,
    includeClosed: Boolean = false,
    block: (T) -> Int,
): Int {
    val result = if (includeClosed) {
        handleRegistry.acquireIncludingClosed(context, handle, kind)
    } else {
        handleRegistry.acquire(context, handle, kind)
    }
    if (result.status != CODEX_AGENT_STATUS_OK) return result.status
    val lease = checkNotNull(result.value)
    val status = try {
        val payload = lease.payload as? T ?: return CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        block(payload)
    } finally {
        lease.close()
    }
    return status
}

private fun copyHostWorkspace(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCHostStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val workspace = it.state.workspaceOrNull() ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(select(workspace), buffer, capacity, outRequired)
    }
}

private fun copyFailure(
    context: COpaquePointer?,
    failure: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexFailure) -> String,
): Int = abiStatus {
    withPayload<CodexFailure>(context, failure, CodexAgentCHandleKind.FAILURE) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private fun CodexAgentCRegistryResult<COpaquePointer>.asStateSnapshot(): CodexAgentCStateSnapshot =
    CodexAgentCStateSnapshot(status, value)

private fun startConversationOperation(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    execute: suspend (CodexAgentCConversation) -> Unit,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val acquired = handleRegistry.acquire(
        context,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
    )
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val targetLease = checkNotNull(acquired.value)
    val wrapper = targetLease.payload as? CodexAgentCConversation
    if (wrapper == null) {
        targetLease.close()
        return@abiStatus CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
    }
    startCodexAgentCOperation(
        context,
        wrapper.runtime,
        callback,
        userData,
        outOperation,
        targetLease,
    ) {
        execute(wrapper)
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

private fun destroyAsyncHandle(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
    destroy: (COpaquePointer?, COpaquePointer?) -> Int,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = destroy(context, handle)
    if (status == CODEX_AGENT_STATUS_OK) slot.pointed.value = null
    status
}
