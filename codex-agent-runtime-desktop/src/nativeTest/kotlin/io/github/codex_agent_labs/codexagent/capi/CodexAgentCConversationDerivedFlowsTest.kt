@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexagent.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexagent.agent.CodexConversation
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexRuntimeFeature
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.staticCFunction
import kotlinx.cinterop.value
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexAgentCConversationDerivedFlowsTest {
    @Test
    fun currentMessagesGetterSubscriptionAndProjectorsPreserveOrderedOwnedTransitions(): Unit = runBlocking {
        val fixture = derivedFlowFixture(setOf(CodexRuntimeFeature.SHELL_COMMANDS))
        val graph = createDerivedFlowGraph(fixture)
        try {
            memScoped {
                val messages = subscribeDerivedFlow { callback, userData, output ->
                    codexAgentConversationCurrentMessagesSubscribe(
                        graph.context, graph.conversationHandle, callback, userData, output,
                    )
                }
                assertMessagesGet(graph.context, graph.conversationHandle, emptyList())
                receiveMessages(graph.context, messages, emptyList())
                val sendSlot = launchDerivedFlowTurn(graph, fixture)
                receiveMessages(graph.context, messages, listOf(0 to "hello"))
                assertMessagesGet(graph.context, graph.conversationHandle, listOf(0 to "hello"))
                activateDerivedFlowTurn(graph, fixture, sendSlot)
                completeDerivedFlowTurn(graph, fixture)
                val completedMessages = listOf(0 to "hello", 1 to "Canonical answer")
                receiveMessages(graph.context, messages, completedMessages)
                assertMessagesGet(graph.context, graph.conversationHandle, completedMessages)
                graph.conversation.close()
                receiveMessages(graph.context, messages, completedMessages, terminal = true)
                destroyAndQuiesceDerivedFlowSubscription(graph.context, messages)
            }
        } finally {
            graph.close()
        }
    }

    @Test
    fun activeTurnProgressGetterSubscriptionAndProjectorsPreserveNullableOwnedTransitions(): Unit = runBlocking {
        val fixture = derivedFlowFixture(setOf(CodexRuntimeFeature.SHELL_COMMANDS))
        val graph = createDerivedFlowGraph(fixture)
        try {
            memScoped {
                val progress = subscribeDerivedFlow { callback, userData, output ->
                    codexAgentConversationActiveTurnProgressSubscribe(
                        graph.context, graph.conversationHandle, callback, userData, output,
                    )
                }
                assertProgressGet(graph.context, graph.conversationHandle, null)
                receiveProgress(graph.context, progress, null)
                val sendSlot = launchDerivedFlowTurn(graph, fixture)
                activateDerivedFlowTurn(graph, fixture, sendSlot)
                receiveProgress(graph.context, progress, "working")
                assertProgressGet(graph.context, graph.conversationHandle, "working")
                completeDerivedFlowTurn(graph, fixture)
                receiveProgress(graph.context, progress, null)
                assertProgressGet(graph.context, graph.conversationHandle, null)
                graph.conversation.close()
                receiveProgress(graph.context, progress, null, terminal = true)
                destroyAndQuiesceDerivedFlowSubscription(graph.context, progress)
            }
        } finally {
            graph.close()
        }
    }

    @Test
    fun canStartTurnGetterAndSubscriptionProjectReadyActiveReadyClosed(): Unit = runBlocking {
        verifyDerivedBooleanFlow(
            getter = { context, conversation, output ->
                codexAgentConversationCanStartTurnGet(context, conversation, output)
            },
            subscribe = { context, conversation, callback, userData, output ->
                codexAgentConversationCanStartTurnSubscribe(context, conversation, callback, userData, output)
            },
            initial = true,
            running = false,
            ready = true,
        )
    }

    @Test
    fun canReloadGetterAndSubscriptionProjectReadyActiveReadyClosed(): Unit = runBlocking {
        verifyDerivedBooleanFlow(
            getter = { context, conversation, output ->
                codexAgentConversationCanReloadGet(context, conversation, output)
            },
            subscribe = { context, conversation, callback, userData, output ->
                codexAgentConversationCanReloadSubscribe(context, conversation, callback, userData, output)
            },
            initial = true,
            running = false,
            ready = true,
        )
    }

    @Test
    fun canCancelTurnGetterAndSubscriptionProjectReadyActiveReadyClosed(): Unit = runBlocking {
        verifyDerivedBooleanFlow(
            getter = { context, conversation, output ->
                codexAgentConversationCanCancelTurnGet(context, conversation, output)
            },
            subscribe = { context, conversation, callback, userData, output ->
                codexAgentConversationCanCancelTurnSubscribe(context, conversation, callback, userData, output)
            },
            initial = false,
            running = true,
            ready = false,
        )
    }

    @Test
    fun canRunShellCommandGetterAndSubscriptionProjectFeatureActiveAndDisabledStates(): Unit = runBlocking {
        verifyDerivedBooleanFlow(
            getter = { context, conversation, output ->
                codexAgentConversationCanRunShellCommandGet(context, conversation, output)
            },
            subscribe = { context, conversation, callback, userData, output ->
                codexAgentConversationCanRunShellCommandSubscribe(context, conversation, callback, userData, output)
            },
            initial = true,
            running = false,
            ready = true,
        )
        val graph = createDerivedFlowGraph(derivedFlowFixture(emptySet()))
        try {
            memScoped {
                val shell = subscribeDerivedFlow { callback, userData, output ->
                    codexAgentConversationCanRunShellCommandSubscribe(
                        graph.context, graph.conversationHandle, callback, userData, output,
                    )
                }
                assertBooleanGet(graph.context, false) {
                    codexAgentConversationCanRunShellCommandGet(graph.context, graph.conversationHandle, it)
                }
                receiveBoolean(graph.context, shell, false)
                graph.conversation.close()
                receiveBoolean(graph.context, shell, false, terminal = true)
                destroyAndQuiesceDerivedFlowSubscription(graph.context, shell)
            }
        } finally {
            graph.close()
        }
    }

    @Test
    fun isTurnActiveGetterAndSubscriptionProjectReadyActiveReadyClosed(): Unit = runBlocking {
        verifyDerivedBooleanFlow(
            getter = { context, conversation, output ->
                codexAgentConversationIsTurnActiveGet(context, conversation, output)
            },
            subscribe = { context, conversation, callback, userData, output ->
                codexAgentConversationIsTurnActiveSubscribe(context, conversation, callback, userData, output)
            },
            initial = false,
            running = true,
            ready = false,
        )
    }

    @Test
    fun gettersSubscriptionsAndTypedProjectorsFailClosedWithoutMutatingOutputs(): Unit = runBlocking {
        val graph = createDerivedFlowGraph(NativeCodexBehaviorFixture(features = emptySet()))
        val otherRuntime = CodexAgentCContextRuntime()
        val otherContext = handleRegistry.createContext(otherRuntime).requiredDerivedFlowValue()
        try {
            memScoped {
                val wrongType = createSnapshot(
                    graph.context,
                    CodexAgentCConversationStateSnapshot(graph.conversation.state.value),
                ).requiredDerivedFlowValue()
                val wrongTypeSlot = alloc<COpaquePointerVar>().also { it.value = wrongType }
                val staleSlot = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationRetain(graph.context, graph.conversationHandle, staleSlot.ptr),
                )
                val stale = assertNotNull(staleSlot.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationRelease(graph.context, staleSlot.ptr))

                val occupied = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationCurrentMessagesGet(
                        graph.context, graph.conversationHandle, occupied.ptr,
                    ),
                )
                val occupiedValue = assertNotNull(occupied.value)
                val getters = listOf<DerivedFlowGetter>(
                    ::codexAgentConversationCurrentMessagesGet,
                    ::codexAgentConversationActiveTurnProgressGet,
                    ::codexAgentConversationCanStartTurnGet,
                    ::codexAgentConversationCanReloadGet,
                    ::codexAgentConversationCanCancelTurnGet,
                    ::codexAgentConversationCanRunShellCommandGet,
                    ::codexAgentConversationIsTurnActiveGet,
                )
                getters.forEach { getter ->
                    val output = emptyDerivedFlowHandle()
                    assertEquals(CODEX_AGENT_STATUS_WRONG_CONTEXT, getter(otherContext, graph.conversationHandle, output.ptr))
                    assertNull(output.value)
                    assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, getter(graph.context, wrongType, output.ptr))
                    assertNull(output.value)
                    assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, getter(graph.context, stale, output.ptr))
                    assertNull(output.value)
                    assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, getter(graph.context, null, output.ptr))
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        getter(graph.context, graph.conversationHandle, occupied.ptr),
                    )
                    assertEquals(occupiedValue, occupied.value)
                }

                val subscriptions = listOf<DerivedFlowSubscriber>(
                    ::codexAgentConversationCurrentMessagesSubscribe,
                    ::codexAgentConversationActiveTurnProgressSubscribe,
                    ::codexAgentConversationCanStartTurnSubscribe,
                    ::codexAgentConversationCanReloadSubscribe,
                    ::codexAgentConversationCanCancelTurnSubscribe,
                    ::codexAgentConversationCanRunShellCommandSubscribe,
                    ::codexAgentConversationIsTurnActiveSubscribe,
                )
                subscriptions.forEach { subscribe ->
                    val output = emptyDerivedFlowHandle()
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_CONTEXT,
                        subscribe(otherContext, graph.conversationHandle, derivedFlowCallback, null, output.ptr),
                    )
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        subscribe(graph.context, wrongType, derivedFlowCallback, null, output.ptr),
                    )
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_STALE_HANDLE,
                        subscribe(graph.context, stale, derivedFlowCallback, null, output.ptr),
                    )
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        subscribe(graph.context, null, derivedFlowCallback, null, output.ptr),
                    )
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        subscribe(graph.context, graph.conversationHandle, null, null, output.ptr),
                    )
                    assertNull(output.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        subscribe(
                            graph.context,
                            graph.conversationHandle,
                            derivedFlowCallback,
                            null,
                            occupied.ptr,
                        ),
                    )
                    assertEquals(occupiedValue, occupied.value)
                }

                val progress = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationActiveTurnProgressGet(
                        graph.context, graph.conversationHandle, progress.ptr,
                    ),
                )
                val progressSnapshot = assertNotNull(progress.value)
                val boolean = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationCanStartTurnGet(
                        graph.context, graph.conversationHandle, boolean.ptr,
                    ),
                )
                val booleanSnapshot = assertNotNull(boolean.value)
                val staleMessagesSlot = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationCurrentMessagesGet(
                        graph.context, graph.conversationHandle, staleMessagesSlot.ptr,
                    ),
                )
                val staleMessages = assertNotNull(staleMessagesSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentSnapshotDestroy(graph.context, staleMessagesSlot.ptr),
                )
                val staleProgressSlot = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationActiveTurnProgressGet(
                        graph.context, graph.conversationHandle, staleProgressSlot.ptr,
                    ),
                )
                val staleProgress = assertNotNull(staleProgressSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentSnapshotDestroy(graph.context, staleProgressSlot.ptr),
                )
                val staleBooleanSlot = emptyDerivedFlowHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationCanStartTurnGet(
                        graph.context, graph.conversationHandle, staleBooleanSlot.ptr,
                    ),
                )
                val staleBoolean = assertNotNull(staleBooleanSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentSnapshotDestroy(graph.context, staleBooleanSlot.ptr),
                )

                val count = alloc<ULongVar>().also { it.value = 91uL }
                listOf(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT to {
                        codexAgentConversationCurrentMessagesCount(otherContext, occupiedValue, count.ptr)
                    },
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE to {
                        codexAgentConversationCurrentMessagesCount(graph.context, progressSnapshot, count.ptr)
                    },
                    CODEX_AGENT_STATUS_STALE_HANDLE to {
                        codexAgentConversationCurrentMessagesCount(graph.context, staleMessages, count.ptr)
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentConversationCurrentMessagesCount(graph.context, null, count.ptr)
                    },
                ).forEach { (expectedStatus, invoke) ->
                    count.value = 91uL
                    assertEquals(expectedStatus, invoke())
                    assertEquals(91uL, count.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationCurrentMessagesCount(graph.context, occupiedValue, null),
                )

                val child = emptyDerivedFlowHandle()
                listOf(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT to {
                        codexAgentConversationCurrentMessagesAt(otherContext, occupiedValue, 0uL, child.ptr)
                    },
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE to {
                        codexAgentConversationCurrentMessagesAt(graph.context, progressSnapshot, 0uL, child.ptr)
                    },
                    CODEX_AGENT_STATUS_STALE_HANDLE to {
                        codexAgentConversationCurrentMessagesAt(graph.context, staleMessages, 0uL, child.ptr)
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentConversationCurrentMessagesAt(graph.context, null, 0uL, child.ptr)
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentConversationCurrentMessagesAt(graph.context, occupiedValue, 0uL, child.ptr)
                    },
                ).forEach { (expectedStatus, invoke) ->
                    assertEquals(expectedStatus, invoke())
                    assertNull(child.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationCurrentMessagesAt(graph.context, occupiedValue, 0uL, null),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationCurrentMessagesAt(
                        graph.context, occupiedValue, 0uL, occupied.ptr,
                    ),
                )
                assertEquals(occupiedValue, occupied.value)

                val hasValue = alloc<IntVar>().also { it.value = 73 }
                listOf(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT to {
                        codexAgentConversationActiveTurnProgressHasValue(
                            otherContext, progressSnapshot, hasValue.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE to {
                        codexAgentConversationActiveTurnProgressHasValue(
                            graph.context, occupiedValue, hasValue.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_STALE_HANDLE to {
                        codexAgentConversationActiveTurnProgressHasValue(
                            graph.context, staleProgress, hasValue.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentConversationActiveTurnProgressHasValue(
                            graph.context, null, hasValue.ptr,
                        )
                    },
                ).forEach { (expectedStatus, invoke) ->
                    hasValue.value = 73
                    assertEquals(expectedStatus, invoke())
                    assertEquals(73, hasValue.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationActiveTurnProgressHasValue(graph.context, progressSnapshot, null),
                )
                listOf(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT to {
                        codexAgentConversationActiveTurnProgressValue(
                            otherContext, progressSnapshot, child.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE to {
                        codexAgentConversationActiveTurnProgressValue(
                            graph.context, occupiedValue, child.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_STALE_HANDLE to {
                        codexAgentConversationActiveTurnProgressValue(
                            graph.context, staleProgress, child.ptr,
                        )
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentConversationActiveTurnProgressValue(graph.context, null, child.ptr)
                    },
                    CODEX_AGENT_STATUS_NOT_READY to {
                        codexAgentConversationActiveTurnProgressValue(
                            graph.context, progressSnapshot, child.ptr,
                        )
                    },
                ).forEach { (expectedStatus, invoke) ->
                    assertEquals(expectedStatus, invoke())
                    assertNull(child.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationActiveTurnProgressValue(graph.context, progressSnapshot, null),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationActiveTurnProgressValue(
                        graph.context, progressSnapshot, occupied.ptr,
                    ),
                )
                assertEquals(occupiedValue, occupied.value)

                val booleanValue = alloc<IntVar>().also { it.value = 73 }
                listOf(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT to {
                        codexAgentStateBooleanValue(otherContext, booleanSnapshot, booleanValue.ptr)
                    },
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE to {
                        codexAgentStateBooleanValue(graph.context, occupiedValue, booleanValue.ptr)
                    },
                    CODEX_AGENT_STATUS_STALE_HANDLE to {
                        codexAgentStateBooleanValue(graph.context, staleBoolean, booleanValue.ptr)
                    },
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT to {
                        codexAgentStateBooleanValue(graph.context, null, booleanValue.ptr)
                    },
                ).forEach { (expectedStatus, invoke) ->
                    booleanValue.value = 73
                    assertEquals(expectedStatus, invoke())
                    assertEquals(73, booleanValue.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentStateBooleanValue(graph.context, booleanSnapshot, null),
                )

                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, progress.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, boolean.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, occupied.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, wrongTypeSlot.ptr))
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            otherRuntime.cancel()
            graph.close()
        }
    }
}

private typealias DerivedFlowGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<COpaquePointerVar>?,
) -> Int

private typealias DerivedFlowSubscriber = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<CFunction<(
        COpaquePointer?, COpaquePointer?, Int, COpaquePointer?, Int, COpaquePointer?,
    ) -> Unit>>?,
    COpaquePointer?,
    CPointer<COpaquePointerVar>?,
) -> Int

private data class DerivedFlowEvent(
    val context: COpaquePointer?,
    val subscription: COpaquePointer?,
    val eventStatus: Int,
    val snapshot: COpaquePointer?,
    val terminal: Int,
    val userData: COpaquePointer?,
    val publishedSubscription: COpaquePointer?,
)

private class DerivedFlowObserver(
    private val output: CPointer<COpaquePointerVar>,
) {
    val events = Channel<DerivedFlowEvent>(Channel.UNLIMITED)
    val callbacks = AtomicInt(0)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun publish(
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        eventStatus: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ) {
        callbacks.addAndFetch(1)
        events.trySend(
            DerivedFlowEvent(
                context,
                subscription,
                eventStatus,
                snapshot,
                terminal,
                userData,
                output.pointed.value,
            ),
        )
    }

    fun dispose() = reference.dispose()
}

private data class DerivedFlowSubscription(
    val slot: CPointer<COpaquePointerVar>,
    val observer: DerivedFlowObserver,
)

private val derivedFlowCallback = staticCFunction {
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        eventStatus: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ->
    checkNotNull(userData).asStableRef<DerivedFlowObserver>().get().publish(
        context,
        subscription,
        eventStatus,
        snapshot,
        terminal,
        userData,
    )
}

private fun MemScope.subscribeDerivedFlow(
    launch: (
        CodexAgentCStateCallback,
        COpaquePointer,
        CPointer<COpaquePointerVar>,
    ) -> Int,
): DerivedFlowSubscription {
    val slot = emptyDerivedFlowHandle()
    val observer = DerivedFlowObserver(slot.ptr)
    assertEquals(CODEX_AGENT_STATUS_OK, launch(derivedFlowCallback, observer.userData, slot.ptr))
    assertNotNull(slot.value)
    return DerivedFlowSubscription(slot.ptr, observer)
}

private suspend fun receiveDerivedFlowEvent(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
    terminal: Boolean,
): COpaquePointer = checkNotNull(withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) {
    subscription.observer.events.receive().let { event ->
        assertEquals(context, event.context)
        assertEquals(subscription.slot.pointed.value, event.subscription)
        assertEquals(subscription.slot.pointed.value, event.publishedSubscription)
        assertEquals(subscription.observer.userData, event.userData)
        assertEquals(CODEX_AGENT_STATUS_OK, event.eventStatus)
        assertEquals(if (terminal) 1 else 0, event.terminal)
        assertNotNull(event.snapshot)
    }
}) { "timed out waiting for derived-flow callback; terminal=$terminal" }

private suspend fun receiveBoolean(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
    expected: Boolean,
    terminal: Boolean = false,
) {
    val snapshot = receiveDerivedFlowEvent(context, subscription, terminal)
    memScoped {
        val value = alloc<IntVar>().also { it.value = -1 }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentStateBooleanValue(context, snapshot, value.ptr))
        assertEquals(if (expected) 1 else 0, value.value)
        destroyDerivedFlowSnapshot(context, snapshot)
    }
}

private suspend fun receiveMessages(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
    expected: List<Pair<Int, String>>,
    terminal: Boolean = false,
) {
    assertMessagesSnapshot(
        context,
        receiveDerivedFlowEvent(context, subscription, terminal),
        expected,
    )
}

private suspend fun receiveProgress(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
    expectedText: String?,
    terminal: Boolean = false,
) {
    assertProgressSnapshot(
        context,
        receiveDerivedFlowEvent(context, subscription, terminal),
        expectedText,
    )
}

private fun MemScope.assertBooleanGet(
    context: COpaquePointer,
    expected: Boolean,
    get: (CPointer<COpaquePointerVar>) -> Int,
) {
    val snapshot = emptyDerivedFlowHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, get(snapshot.ptr))
    val value = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentStateBooleanValue(context, assertNotNull(snapshot.value), value.ptr),
    )
    assertEquals(if (expected) 1 else 0, value.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, snapshot.ptr))
}

private fun MemScope.assertMessagesGet(
    context: COpaquePointer,
    conversation: COpaquePointer,
    expected: List<Pair<Int, String>>,
) {
    val snapshot = emptyDerivedFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationCurrentMessagesGet(context, conversation, snapshot.ptr),
    )
    assertMessagesSnapshot(context, assertNotNull(snapshot.value), expected)
}

private fun assertMessagesSnapshot(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    expected: List<Pair<Int, String>>,
) = memScoped {
    val count = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationCurrentMessagesCount(context, snapshot, count.ptr),
    )
    assertEquals(expected.size.toULong(), count.value)
    val messages = expected.indices.map { index ->
        emptyDerivedFlowHandle().also {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationCurrentMessagesAt(context, snapshot, index.toULong(), it.ptr),
            )
        }
    }
    val outOfBounds = emptyDerivedFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
        codexAgentConversationCurrentMessagesAt(context, snapshot, expected.size.toULong(), outOfBounds.ptr),
    )
    assertNull(outOfBounds.value)
    destroyDerivedFlowSnapshot(context, snapshot)
    messages.zip(expected).forEach { (message, expectedValue) ->
        val role = alloc<IntVar>().also { it.value = -1 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMessageRole(context, assertNotNull(message.value), role.ptr),
        )
        assertEquals(expectedValue.first, role.value)
        assertEquals(expectedValue.second, readDerivedFlowMessageText(context, assertNotNull(message.value)))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, message.ptr))
    }
}

private fun MemScope.assertProgressGet(
    context: COpaquePointer,
    conversation: COpaquePointer,
    expectedText: String?,
) {
    val snapshot = emptyDerivedFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationActiveTurnProgressGet(context, conversation, snapshot.ptr),
    )
    assertProgressSnapshot(context, assertNotNull(snapshot.value), expectedText)
}

private fun assertProgressSnapshot(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    expectedText: String?,
) = memScoped {
    val hasValue = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationActiveTurnProgressHasValue(context, snapshot, hasValue.ptr),
    )
    assertEquals(if (expectedText == null) 0 else 1, hasValue.value)
    val progress = emptyDerivedFlowHandle()
    if (expectedText == null) {
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentConversationActiveTurnProgressValue(context, snapshot, progress.ptr),
        )
        assertNull(progress.value)
        destroyDerivedFlowSnapshot(context, snapshot)
    } else {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationActiveTurnProgressValue(context, snapshot, progress.ptr),
        )
        destroyDerivedFlowSnapshot(context, snapshot)
        assertEquals(expectedText, readDerivedFlowProgressText(context, assertNotNull(progress.value)))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, progress.ptr))
    }
}

private fun readDerivedFlowMessageText(context: COpaquePointer, message: COpaquePointer): String =
    readDerivedFlowString { buffer, capacity, required ->
        codexAgentMessageTextCopy(context, message, buffer, capacity, required)
    }

private fun readDerivedFlowProgressText(context: COpaquePointer, progress: COpaquePointer): String =
    readDerivedFlowString { buffer, capacity, required ->
        codexAgentTurnProgressTextCopy(context, progress, buffer, capacity, required)
    }

private fun readDerivedFlowString(
    copy: (CPointer<UByteVar>?, ULong, CPointer<ULongVar>) -> Int,
): String = memScoped {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(null, 0uL, required.ptr))
    val size = required.value.toInt()
    val buffer = allocArray<UByteVar>(size)
    assertEquals(CODEX_AGENT_STATUS_OK, copy(buffer, size.toULong(), required.ptr))
    ByteArray(size) { index -> buffer[index].toByte() }.decodeToString()
}

private fun destroyDerivedFlowSnapshot(context: COpaquePointer, snapshot: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = snapshot }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot.ptr))
    assertNull(slot.value)
}

private suspend fun destroyDerivedFlowSubscription(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
) {
    withTimeout(DERIVED_FLOW_TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentSubscriptionDestroy(context, subscription.slot)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("subscription destroy failed with $status")
            }
        }
    }
    assertNull(subscription.slot.pointed.value)
}

private suspend fun awaitDerivedFlowOperation(context: COpaquePointer, operation: COpaquePointer?): Int =
    withTimeout(DERIVED_FLOW_TIMEOUT_MILLIS) {
        memScoped {
            val result = alloc<IntVar>()
            while (true) {
                when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                    CODEX_AGENT_STATUS_NOT_READY -> yield()
                    CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                    else -> error("operation result query failed with $status")
                }
            }
            error("unreachable")
        }
    }

private suspend fun destroyDerivedFlowOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(DERIVED_FLOW_TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentOperationDestroy(context, operation)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("operation destroy failed with $status")
            }
        }
    }
    assertNull(operation.pointed.value)
}

private fun derivedFlowFixture(features: Set<CodexRuntimeFeature>): NativeCodexBehaviorFixture =
    NativeCodexBehaviorFixture(
        features = features,
        additionalResponse = { method, _ ->
            if (method == "thread/read") derivedFlowConversationReadResponse() else null
        },
    )

private suspend fun MemScope.launchDerivedFlowTurn(
    graph: DerivedFlowGraph,
    fixture: NativeCodexBehaviorFixture,
): CPointer<COpaquePointerVar> {
    val request = createSnapshot(
        graph.context,
        CodexAgentCTurnRequestSnapshot(AgentTurnRequest("hello", clientMessageId = "client-1")),
    ).requiredDerivedFlowValue()
    val requestSlot = alloc<COpaquePointerVar>().also { it.value = request }
    val operation = emptyDerivedFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationSendRequest(
            graph.context,
            graph.conversationHandle,
            request,
            null,
            null,
            operation.ptr,
        ),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(graph.context, requestSlot.ptr))
    checkNotNull(withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) {
        fixture.turnStartObserved.await()
    }) { "timed out waiting for fixture turn/start" }
    return operation.ptr
}

private suspend fun MemScope.activateDerivedFlowTurn(
    graph: DerivedFlowGraph,
    fixture: NativeCodexBehaviorFixture,
    operation: CPointer<COpaquePointerVar>,
) {
    fixture.releaseTurnStart.complete(Unit)
    assertEquals(CODEX_AGENT_STATUS_OK, awaitDerivedFlowOperation(graph.context, operation.pointed.value))
    destroyDerivedFlowOperation(graph.context, operation)
}

private suspend fun completeDerivedFlowTurn(
    graph: DerivedFlowGraph,
    fixture: NativeCodexBehaviorFixture,
) {
    fixture.notify(
        "turn/completed",
        buildJsonObject {
            put("threadId", fixture.newConversationId.value)
            put("turn", buildJsonObject {
                put("id", "native-turn")
                putJsonArray("items") {}
                put("status", "completed")
            })
        },
    )
    checkNotNull(withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) {
        while (graph.conversation.state.value.status != AgentConversationStatus.READY) yield()
        Unit
    }) {
        "timed out waiting for conversation READY after turn/completed; state=${graph.conversation.state.value}"
    }
}

private suspend fun verifyDerivedBooleanFlow(
    getter: DerivedFlowGetter,
    subscribe: DerivedFlowSubscriber,
    initial: Boolean,
    running: Boolean,
    ready: Boolean,
) {
    val fixture = derivedFlowFixture(setOf(CodexRuntimeFeature.SHELL_COMMANDS))
    val graph = createDerivedFlowGraph(fixture)
    try {
        memScoped {
            val subscription = subscribeDerivedFlow { callback, userData, output ->
                subscribe(
                    graph.context,
                    graph.conversationHandle,
                    callback,
                    userData,
                    output,
                )
            }
            assertBooleanGet(graph.context, initial) {
                getter(graph.context, graph.conversationHandle, it)
            }
            receiveBoolean(graph.context, subscription, initial)
            val operation = launchDerivedFlowTurn(graph, fixture)
            activateDerivedFlowTurn(graph, fixture, operation)
            receiveBoolean(graph.context, subscription, running)
            assertBooleanGet(graph.context, running) {
                getter(graph.context, graph.conversationHandle, it)
            }
            completeDerivedFlowTurn(graph, fixture)
            receiveBoolean(graph.context, subscription, ready)
            assertBooleanGet(graph.context, ready) {
                getter(graph.context, graph.conversationHandle, it)
            }
            graph.conversation.close()
            receiveBoolean(graph.context, subscription, false, terminal = true)
            destroyAndQuiesceDerivedFlowSubscription(graph.context, subscription)
        }
    } finally {
        graph.close()
    }
}

private suspend fun destroyAndQuiesceDerivedFlowSubscription(
    context: COpaquePointer,
    subscription: DerivedFlowSubscription,
) {
    destroyDerivedFlowSubscription(context, subscription)
    assertNull(withTimeoutOrNull(DERIVED_FLOW_QUIET_MILLIS) { subscription.observer.events.receive() })
    subscription.observer.dispose()
}

private data class DerivedFlowGraph(
    val fixture: NativeCodexBehaviorFixture,
    val runtime: CodexAgentCContextRuntime,
    val context: COpaquePointer,
    val hostHandle: COpaquePointer,
    val agentHandle: COpaquePointer,
    val conversationsHandle: COpaquePointer,
    val conversationHandle: COpaquePointer,
    val host: CodexAgentCHost,
    val conversation: CodexConversation,
) {
    suspend fun close() {
        fixture.releaseTurnStart.complete(Unit)
        runtime.cancel()
        withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) { runCatching { conversation.close() } }
        withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) { runCatching { host.core.close() } }
        handleRegistry.semanticClose(context, conversationHandle, CodexAgentCHandleKind.CONVERSATION) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, conversationHandle, CodexAgentCHandleKind.CONVERSATION)
        handleRegistry.semanticClose(context, conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS)
        handleRegistry.semanticClose(context, agentHandle, CodexAgentCHandleKind.AGENT) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, agentHandle, CodexAgentCHandleKind.AGENT)
        handleRegistry.semanticClose(context, hostHandle, CodexAgentCHandleKind.HOST) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, hostHandle, CodexAgentCHandleKind.HOST)
        val destroyed = withTimeoutOrNull(DERIVED_FLOW_TIMEOUT_MILLIS) {
            while (true) {
                when (val status = handleRegistry.destroyContext(context)) {
                    CODEX_AGENT_STATUS_BUSY -> yield()
                    else -> return@withTimeoutOrNull status
                }
            }
            error("unreachable")
        }
        assertEquals(CODEX_AGENT_STATUS_OK, destroyed)
    }
}

private suspend fun createDerivedFlowGraph(fixture: NativeCodexBehaviorFixture): DerivedFlowGraph {
    val runtime = CodexAgentCContextRuntime()
    val context = handleRegistry.createContext(runtime).requiredDerivedFlowValue()
    val host = CodexAgentCHost(fixture.createHost(), runtime)
    val hostHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        host,
    ).requiredDerivedFlowValue()
    host.core.selectWorkspace(CodexPathWorkspaceSelection(fixture.workspace.path))
    val agent = (host.core.lifecycleState.value as CodexHostState.Ready).agent
    val agentHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.AGENT,
        CodexAgentCAgent(agent, host),
        hostHandle,
        CodexAgentCHandleKind.HOST,
    ).requiredDerivedFlowValue()
    val conversationsHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.CONVERSATIONS,
        CodexAgentCConversations(agent.conversations, host, agent),
        agentHandle,
        CodexAgentCHandleKind.AGENT,
    ).requiredDerivedFlowValue()
    val conversation = agent.conversations.open()
    val conversationHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.CONVERSATION,
        CodexAgentCConversation(conversation, runtime),
        conversationsHandle,
        CodexAgentCHandleKind.CONVERSATIONS,
    ).requiredDerivedFlowValue()
    return DerivedFlowGraph(
        fixture,
        runtime,
        context,
        hostHandle,
        agentHandle,
        conversationsHandle,
        conversationHandle,
        host,
        conversation,
    )
}

private fun MemScope.emptyDerivedFlowHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredDerivedFlowValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}

private fun derivedFlowConversationReadResponse() = buildJsonObject {
    putJsonObject("thread") {
        put("cliVersion", "test")
        put("createdAt", 0)
        put("cwd", "/workspace")
        put("ephemeral", false)
        put("id", "native-thread")
        put("modelProvider", "openai")
        put("name", "Canonical")
        put("preview", "Canonical answer")
        put("sessionId", "native-thread")
        put("source", "cli")
        putJsonObject("status") { put("type", "idle") }
        put("updatedAt", 10)
        putJsonArray("turns") {
            add(buildJsonObject {
                put("id", "native-turn")
                put("status", "completed")
                putJsonArray("items") {
                    add(buildJsonObject {
                        put("id", "user-1")
                        put("clientId", "client-1")
                        put("type", "userMessage")
                        putJsonArray("content") {
                            add(buildJsonObject {
                                put("type", "text")
                                put("text", "hello")
                            })
                        }
                    })
                    add(buildJsonObject {
                        put("id", "codex-1")
                        put("type", "agentMessage")
                        put("phase", "final_answer")
                        put("text", "Canonical answer")
                    })
                }
            })
        }
    }
}

private const val DERIVED_FLOW_TIMEOUT_MILLIS = 5_000L
private const val DERIVED_FLOW_QUIET_MILLIS = 25L
