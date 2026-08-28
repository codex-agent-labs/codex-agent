@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged

internal data class CodexAgentCCurrentMessagesStateSnapshot(
    val value: List<AgentMessage>,
) : CodexAgentCSnapshot

internal data class CodexAgentCActiveTurnProgressStateSnapshot(
    val value: AgentTurnProgress?,
) : CodexAgentCSnapshot

@CName("codex_agent_conversation_current_messages_get")
public fun codexAgentConversationCurrentMessagesGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationStateFlowGet(context, conversation, outSnapshot) { contextPointer, wrapper ->
    createSnapshot(
        contextPointer,
        CodexAgentCCurrentMessagesStateSnapshot(
            wrapper.core.currentMessages.value.map { it.aggregateCopy() },
        ),
    )
}

@CName("codex_agent_conversation_active_turn_progress_get")
public fun codexAgentConversationActiveTurnProgressGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationStateFlowGet(context, conversation, outSnapshot) { contextPointer, wrapper ->
    createSnapshot(
        contextPointer,
        CodexAgentCActiveTurnProgressStateSnapshot(
            wrapper.core.activeTurnProgress.value?.aggregateCopy(),
        ),
    )
}

@CName("codex_agent_conversation_can_start_turn_get")
public fun codexAgentConversationCanStartTurnGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowGet(context, conversation, outSnapshot) {
    it.core.canStartTurn.value
}

@CName("codex_agent_conversation_can_reload_get")
public fun codexAgentConversationCanReloadGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowGet(context, conversation, outSnapshot) {
    it.core.canReload.value
}

@CName("codex_agent_conversation_can_cancel_turn_get")
public fun codexAgentConversationCanCancelTurnGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowGet(context, conversation, outSnapshot) {
    it.core.canCancelTurn.value
}

@CName("codex_agent_conversation_can_run_shell_command_get")
public fun codexAgentConversationCanRunShellCommandGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowGet(context, conversation, outSnapshot) {
    it.core.canRunShellCommand.value
}

@CName("codex_agent_conversation_is_turn_active_get")
public fun codexAgentConversationIsTurnActiveGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowGet(context, conversation, outSnapshot) {
    it.core.isTurnActive.value
}

@CName("codex_agent_conversation_current_messages_subscribe")
public fun codexAgentConversationCurrentMessagesSubscribe(
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
): Int = conversationStateFlowSubscribe(
    context,
    conversation,
    callback,
    userData,
    outSubscription,
    states = { wrapper -> wrapper.lifecycleAware(wrapper.core.currentMessages) },
    snapshot = { contextPointer, value ->
        createSnapshot(
            contextPointer,
            CodexAgentCCurrentMessagesStateSnapshot(value.map { it.aggregateCopy() }),
        )
    },
)

@CName("codex_agent_conversation_active_turn_progress_subscribe")
public fun codexAgentConversationActiveTurnProgressSubscribe(
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
): Int = conversationStateFlowSubscribe(
    context,
    conversation,
    callback,
    userData,
    outSubscription,
    states = { wrapper -> wrapper.lifecycleAware(wrapper.core.activeTurnProgress) },
    snapshot = { contextPointer, value ->
        createSnapshot(
            contextPointer,
            CodexAgentCActiveTurnProgressStateSnapshot(value?.aggregateCopy()),
        )
    },
)

@CName("codex_agent_conversation_can_start_turn_subscribe")
public fun codexAgentConversationCanStartTurnSubscribe(
    context: COpaquePointer?, conversation: COpaquePointer?, callback: CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?, outSubscription: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowSubscribe(
    context, conversation, callback, userData, outSubscription,
) { it.core.canStartTurn }

@CName("codex_agent_conversation_can_reload_subscribe")
public fun codexAgentConversationCanReloadSubscribe(
    context: COpaquePointer?, conversation: COpaquePointer?, callback: CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?, outSubscription: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowSubscribe(
    context, conversation, callback, userData, outSubscription,
) { it.core.canReload }

@CName("codex_agent_conversation_can_cancel_turn_subscribe")
public fun codexAgentConversationCanCancelTurnSubscribe(
    context: COpaquePointer?, conversation: COpaquePointer?, callback: CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?, outSubscription: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowSubscribe(
    context, conversation, callback, userData, outSubscription,
) { it.core.canCancelTurn }

@CName("codex_agent_conversation_can_run_shell_command_subscribe")
public fun codexAgentConversationCanRunShellCommandSubscribe(
    context: COpaquePointer?, conversation: COpaquePointer?, callback: CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?, outSubscription: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowSubscribe(
    context, conversation, callback, userData, outSubscription,
) { it.core.canRunShellCommand }

@CName("codex_agent_conversation_is_turn_active_subscribe")
public fun codexAgentConversationIsTurnActiveSubscribe(
    context: COpaquePointer?, conversation: COpaquePointer?, callback: CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?, outSubscription: CPointer<COpaquePointerVar>?,
): Int = conversationBooleanStateFlowSubscribe(
    context, conversation, callback, userData, outSubscription,
) { it.core.isTurnActive }

@CName("codex_agent_conversation_current_messages_count")
public fun codexAgentConversationCurrentMessagesCount(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCCurrentMessagesStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outCount.pointed.value = it.value.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_conversation_current_messages_at")
public fun codexAgentConversationCurrentMessagesAt(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    index: ULong,
    outMessage: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMessage)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCCurrentMessagesStateSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = if (index > Int.MAX_VALUE.toULong()) null else it.value.getOrNull(index.toInt())
        value ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outMessage,
            createSnapshot(contextPointer, CodexAgentCMessageSnapshot(value.aggregateCopy())),
        )
    }
}

@CName("codex_agent_conversation_active_turn_progress_has_value")
public fun codexAgentConversationActiveTurnProgressHasValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCActiveTurnProgressStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasValue.pointed.value = if (it.value == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_conversation_active_turn_progress_value")
public fun codexAgentConversationActiveTurnProgressValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outProgress: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outProgress)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCActiveTurnProgressStateSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = it.value ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outProgress,
            createSnapshot(contextPointer, CodexAgentCTurnProgressSnapshot(value.aggregateCopy())),
        )
    }
}

private fun conversationStateFlowGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
    snapshot: (COpaquePointer, CodexAgentCConversation) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversation>(
        contextPointer,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
        includeClosed = true,
    ) {
        installOutput(outSnapshot, snapshot(contextPointer, it))
    }
}

private fun conversationBooleanStateFlowGet(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
    value: (CodexAgentCConversation) -> Boolean,
): Int = conversationStateFlowGet(context, conversation, outSnapshot) { contextPointer, wrapper ->
    createCodexAgentCBooleanStateSnapshot(contextPointer, value(wrapper))
}

private fun <T> conversationStateFlowSubscribe(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
    states: (CodexAgentCConversation) -> Flow<Pair<T, Boolean>>,
    snapshot: (COpaquePointer, T) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversation>(
        contextPointer,
        conversation,
        CodexAgentCHandleKind.CONVERSATION,
    ) { wrapper ->
        startCodexAgentCStateSubscription(
            contextPointer,
            wrapper.runtime,
            states(wrapper),
            snapshot = { (value, _) ->
                val created = snapshot(contextPointer, value)
                CodexAgentCStateSnapshot(created.status, created.value)
            },
            isTerminal = { (_, terminal) -> terminal },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

private fun conversationBooleanStateFlowSubscribe(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
    states: (CodexAgentCConversation) -> Flow<Boolean>,
): Int = conversationStateFlowSubscribe(
    context,
    conversation,
    callback,
    userData,
    outSubscription,
    states = { wrapper -> wrapper.booleanLifecycleAware(states(wrapper)) },
    snapshot = ::createCodexAgentCBooleanStateSnapshot,
)

private fun <T> CodexAgentCConversation.lifecycleAware(states: Flow<T>): Flow<Pair<T, Boolean>> =
    combine(states, core.state) { value, state ->
        val terminal = state.status == AgentConversationStatus.CLOSED
        value to terminal
    }.distinctUntilChanged()

private fun CodexAgentCConversation.booleanLifecycleAware(
    states: Flow<Boolean>,
): Flow<Pair<Boolean, Boolean>> = combine(states, core.state) { value, state ->
    val terminal = state.status == AgentConversationStatus.CLOSED
    (if (terminal) false else value) to terminal
}.distinctUntilChanged()
