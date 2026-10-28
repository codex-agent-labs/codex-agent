@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.CodexInteractions
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
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
import kotlinx.cinterop.set
import kotlinx.cinterop.sizeOf
import kotlinx.cinterop.staticCFunction
import kotlinx.cinterop.value
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class CodexAgentCInteractionFlowsTest {
    @Test
    fun interactionsStateProjectsCurrentOrderedPendingAndOwnerTerminal(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        withInteractionFlowGraph(fixture) { graph ->
            val first = emptyInteractionFlowSlot()
            val second = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsStateGet(graph.context, graph.interactions.value, first.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsStateGet(graph.context, graph.interactions.value, second.ptr),
            )
            assertNotEquals(first.value, second.value)
            assertEquals(
                emptyList(),
                readInteractionState(graph, assertNotNull(first.value), terminal = 0).kinds,
            )
            destroyInteractionFlowSnapshot(graph.context, second.ptr)

            val subscription = emptyInteractionFlowSlot()
            val observer = InteractionFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsStateSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(emptyList(), receiveInteractionState(graph, observer, subscription.value).kinds)

                fixture.request(301, INTERACTION_APPROVAL_METHOD, approvalRequest())
                assertEquals(
                    listOf(INTERACTION_APPROVAL_KIND),
                    receiveInteractionStateUntil(graph, observer, subscription.value) {
                        it.kinds == listOf(INTERACTION_APPROVAL_KIND)
                    }.kinds,
                )

                fixture.request(302, INTERACTION_ELICITATION_METHOD, urlElicitation(302))
                assertEquals(
                    listOf(INTERACTION_APPROVAL_KIND, INTERACTION_ELICITATION_KIND),
                    receiveInteractionStateUntil(graph, observer, subscription.value) {
                        it.kinds == listOf(INTERACTION_APPROVAL_KIND, INTERACTION_ELICITATION_KIND)
                    }.kinds,
                )

                closeInteractionFlowHost(graph)
                val terminal = receiveInteractionStateUntil(graph, observer, subscription.value) {
                    it.terminal == 1
                }
                assertEquals(1, terminal.terminal)
                destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                assertNoInteractionFlowEvent(observer)
            } finally {
                if (subscription.value != null) {
                    destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                }
                observer.dispose()
            }
        }
    }

    @Test
    fun interactionsApprovalsProjectCurrentChangeOwnedIdentityAndOwnerTerminal(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        withInteractionFlowGraph(fixture) { graph ->
            val current = emptyInteractionFlowSlot()
            val second = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, current.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, second.ptr),
            )
            assertNotEquals(current.value, second.value)
            assertEquals(
                emptyList(),
                readInteractionApprovals(graph, assertNotNull(current.value), terminal = 0).requestIds,
            )
            destroyInteractionFlowSnapshot(graph.context, second.ptr)

            val subscription = emptyInteractionFlowSlot()
            val observer = InteractionFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsApprovalsSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(
                    emptyList(),
                    receiveInteractionApprovals(graph, observer, subscription.value).requestIds,
                )

                fixture.request(311, INTERACTION_APPROVAL_METHOD, approvalRequest())
                assertEquals(
                    listOf("311"),
                    receiveInteractionApprovalsUntil(graph, observer, subscription.value) {
                        it.requestIds == listOf("311")
                    }.requestIds,
                )

                closeInteractionFlowHost(graph)
                val terminal = receiveInteractionApprovalsUntil(graph, observer, subscription.value) {
                    it.terminal == 1
                }
                assertEquals(1, terminal.terminal)
                destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                assertNoInteractionFlowEvent(observer)
            } finally {
                if (subscription.value != null) {
                    destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                }
                observer.dispose()
            }
        }
    }

    @Test
    fun interactionsElicitationsProjectCurrentChangeOwnedIdentityAndOwnerTerminal(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        withInteractionFlowGraph(fixture) { graph ->
            val current = emptyInteractionFlowSlot()
            val second = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, current.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, second.ptr),
            )
            assertNotEquals(current.value, second.value)
            assertEquals(
                emptyList(),
                readInteractionElicitations(graph, assertNotNull(current.value), terminal = 0).requestIds,
            )
            destroyInteractionFlowSnapshot(graph.context, second.ptr)

            val subscription = emptyInteractionFlowSlot()
            val observer = InteractionFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsElicitationsSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(
                    emptyList(),
                    receiveInteractionElicitations(graph, observer, subscription.value).requestIds,
                )

                fixture.request(321, INTERACTION_ELICITATION_METHOD, urlElicitation(321))
                assertEquals(
                    listOf("321"),
                    receiveInteractionElicitationsUntil(graph, observer, subscription.value) {
                        it.requestIds == listOf("321")
                    }.requestIds,
                )

                closeInteractionFlowHost(graph)
                val terminal = receiveInteractionElicitationsUntil(graph, observer, subscription.value) {
                    it.terminal == 1
                }
                assertEquals(1, terminal.terminal)
                destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                assertNoInteractionFlowEvent(observer)
            } finally {
                if (subscription.value != null) {
                    destroyInteractionFlowSubscription(graph.context, subscription.ptr)
                }
                observer.dispose()
            }
        }
    }

    @Test
    fun interactionFlowsFailClosedAcrossOutputTypeContextBoundsAndStaleBoundaries(): Unit = runBlocking {
        withInteractionFlowGraph(NativeCodexBehaviorFixture()) { graph ->
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.interactions.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsStateGet(graph.context, graph.interactions.value, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, occupied.ptr),
            )
            assertEquals(graph.interactions.value, occupied.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsStateSubscribe(
                    graph.context,
                    graph.interactions.value,
                    null,
                    null,
                    occupied.ptr,
                ),
            )

            val approvals = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, approvals.ptr),
            )
            val sentinel = alloc<ULongVar>().also { it.value = 73uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsElicitationsCount(graph.context, approvals.value, sentinel.ptr),
            )
            assertEquals(73uL, sentinel.value)
            val child = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsAt(graph.context, approvals.value, 0uL, child.ptr),
            )
            assertNull(child.value)
            destroyInteractionFlowSnapshot(graph.context, approvals.ptr)

            val otherContext = emptyInteractionFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            val crossOutput = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsStateGet(otherContext.value, graph.interactions.value, crossOutput.ptr),
            )
            assertNull(crossOutput.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val alias = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsRetain(graph.context, graph.interactions.value, alias.ptr),
            )
            val stale = assertNotNull(alias.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(graph.context, alias.ptr))
            val staleOutput = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsElicitationsGet(graph.context, stale, staleOutput.ptr),
            )
            assertNull(staleOutput.value)
        }
    }

    @Test
    fun interactionsElicitationsRejectExactTargetSubscriptionProjectionContextAndBounds(): Unit = runBlocking {
        withInteractionFlowGraph(NativeCodexBehaviorFixture()) { graph ->
            val output = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsGet(graph.context, null, output.ptr),
            )
            val snapshot = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, snapshot.ptr),
            )
            val count = alloc<ULongVar>().also { it.value = 79uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsCount(graph.context, snapshot.value, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsElicitationsCount(graph.context, graph.interactions.value, count.ptr),
            )
            assertEquals(79uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsAt(graph.context, snapshot.value, 0uL, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsAt(graph.context, snapshot.value, ULong.MAX_VALUE, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsAt(graph.context, snapshot.value, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsElicitationsAt(graph.context, graph.interactions.value, 0uL, output.ptr),
            )
            assertNull(output.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsElicitationsSubscribe(
                    graph.context,
                    graph.interactions.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            val nullTargetObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsElicitationsSubscribe(
                        graph.context,
                        null,
                        interactionFlowCallback,
                        nullTargetObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(nullTargetObserver)
            } finally {
                nullTargetObserver.dispose()
            }
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.interactions.value }
            val occupiedObserver = InteractionFlowObserver(occupied.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsElicitationsSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        occupiedObserver.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.interactions.value, occupied.value)
                assertNoInteractionFlowEvent(occupiedObserver)
            } finally {
                occupiedObserver.dispose()
            }

            val otherContext = emptyInteractionFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsElicitationsGet(otherContext.value, graph.interactions.value, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsElicitationsCount(otherContext.value, snapshot.value, count.ptr),
            )
            assertEquals(79uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsElicitationsAt(otherContext.value, snapshot.value, 0uL, output.ptr),
            )
            val crossObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsElicitationsSubscribe(
                        otherContext.value,
                        graph.interactions.value,
                        interactionFlowCallback,
                        crossObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(crossObserver)
            } finally {
                crossObserver.dispose()
            }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val alias = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsRetain(graph.context, graph.interactions.value, alias.ptr),
            )
            val staleService = assertNotNull(alias.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(graph.context, alias.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsElicitationsGet(graph.context, staleService, output.ptr),
            )
            val staleObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentInteractionsElicitationsSubscribe(
                        graph.context,
                        staleService,
                        interactionFlowCallback,
                        staleObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(staleObserver)
            } finally {
                staleObserver.dispose()
            }
            val staleSnapshot = assertNotNull(snapshot.value)
            destroyInteractionFlowSnapshot(graph.context, snapshot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsElicitationsCount(graph.context, staleSnapshot, count.ptr),
            )
            assertEquals(79uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsElicitationsAt(graph.context, staleSnapshot, 0uL, output.ptr),
            )
            assertNull(output.value)
        }
    }

    @Test
    fun interactionsApprovalsRejectExactTargetSubscriptionProjectionContextAndBounds(): Unit = runBlocking {
        withInteractionFlowGraph(NativeCodexBehaviorFixture()) { graph ->
            val output = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsGet(graph.context, null, output.ptr),
            )
            val snapshot = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, snapshot.ptr),
            )
            val count = alloc<ULongVar>().also { it.value = 73uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsCount(graph.context, snapshot.value, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsApprovalsCount(graph.context, graph.interactions.value, count.ptr),
            )
            assertEquals(73uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsAt(graph.context, snapshot.value, 0uL, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsAt(graph.context, snapshot.value, ULong.MAX_VALUE, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsAt(graph.context, snapshot.value, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsApprovalsAt(graph.context, graph.interactions.value, 0uL, output.ptr),
            )
            assertNull(output.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsApprovalsSubscribe(
                    graph.context,
                    graph.interactions.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            val nullTargetObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsApprovalsSubscribe(
                        graph.context,
                        null,
                        interactionFlowCallback,
                        nullTargetObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(nullTargetObserver)
            } finally {
                nullTargetObserver.dispose()
            }
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.interactions.value }
            val occupiedObserver = InteractionFlowObserver(occupied.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsApprovalsSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        occupiedObserver.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.interactions.value, occupied.value)
                assertNoInteractionFlowEvent(occupiedObserver)
            } finally {
                occupiedObserver.dispose()
            }

            val otherContext = emptyInteractionFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsApprovalsGet(otherContext.value, graph.interactions.value, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsApprovalsCount(otherContext.value, snapshot.value, count.ptr),
            )
            assertEquals(73uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsApprovalsAt(otherContext.value, snapshot.value, 0uL, output.ptr),
            )
            val crossObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsApprovalsSubscribe(
                        otherContext.value,
                        graph.interactions.value,
                        interactionFlowCallback,
                        crossObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(crossObserver)
            } finally {
                crossObserver.dispose()
            }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val alias = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsRetain(graph.context, graph.interactions.value, alias.ptr),
            )
            val staleService = assertNotNull(alias.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(graph.context, alias.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsApprovalsGet(graph.context, staleService, output.ptr),
            )
            val staleObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentInteractionsApprovalsSubscribe(
                        graph.context,
                        staleService,
                        interactionFlowCallback,
                        staleObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(staleObserver)
            } finally {
                staleObserver.dispose()
            }
            val staleSnapshot = assertNotNull(snapshot.value)
            destroyInteractionFlowSnapshot(graph.context, snapshot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsApprovalsCount(graph.context, staleSnapshot, count.ptr),
            )
            assertEquals(73uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsApprovalsAt(graph.context, staleSnapshot, 0uL, output.ptr),
            )
            assertNull(output.value)
        }
    }

    @Test
    fun interactionsStateRejectsExactTargetSubscriptionProjectorContextAndStaleBoundaries(): Unit = runBlocking {
        withInteractionFlowGraph(NativeCodexBehaviorFixture()) { graph ->
            val output = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsStateGet(graph.context, null, output.ptr),
            )
            assertNull(output.value)
            val state = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsStateGet(graph.context, graph.interactions.value, state.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsStateValue(graph.context, state.value, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsStateValue(graph.context, graph.interactions.value, output.ptr),
            )
            assertNull(output.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsStateSubscribe(
                    graph.context,
                    graph.interactions.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            val nullTargetObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsStateSubscribe(
                        graph.context,
                        null,
                        interactionFlowCallback,
                        nullTargetObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(nullTargetObserver)
            } finally {
                nullTargetObserver.dispose()
            }
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.interactions.value }
            val occupiedObserver = InteractionFlowObserver(occupied.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionsStateSubscribe(
                        graph.context,
                        graph.interactions.value,
                        interactionFlowCallback,
                        occupiedObserver.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.interactions.value, occupied.value)
                assertNoInteractionFlowEvent(occupiedObserver)
            } finally {
                occupiedObserver.dispose()
            }

            val otherContext = emptyInteractionFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsStateGet(otherContext.value, graph.interactions.value, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsStateValue(otherContext.value, state.value, output.ptr),
            )
            val crossObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsStateSubscribe(
                        otherContext.value,
                        graph.interactions.value,
                        interactionFlowCallback,
                        crossObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(crossObserver)
            } finally {
                crossObserver.dispose()
            }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val alias = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsRetain(graph.context, graph.interactions.value, alias.ptr),
            )
            val staleService = assertNotNull(alias.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(graph.context, alias.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsStateGet(graph.context, staleService, output.ptr),
            )
            val staleObserver = InteractionFlowObserver(output.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentInteractionsStateSubscribe(
                        graph.context,
                        staleService,
                        interactionFlowCallback,
                        staleObserver.userData,
                        output.ptr,
                    ),
                )
                assertNoInteractionFlowEvent(staleObserver)
            } finally {
                staleObserver.dispose()
            }

            val staleSnapshot = assertNotNull(state.value)
            destroyInteractionFlowSnapshot(graph.context, state.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsStateValue(graph.context, staleSnapshot, output.ptr),
            )
            assertNull(output.value)
        }
    }
}

private data class InteractionFlowGraph(
    val contextSlot: COpaquePointerVar,
    val context: COpaquePointer,
    val host: COpaquePointerVar,
    val agent: COpaquePointerVar,
    val interactions: COpaquePointerVar,
    val core: CodexInteractions,
    var hostClosed: Boolean = false,
)

private data class InteractionFlowEvent(
    val context: COpaquePointer?,
    val subscription: COpaquePointer?,
    val status: Int,
    val snapshot: COpaquePointer?,
    val terminal: Int,
    val publishedSubscription: COpaquePointer?,
)

private data class ObservedInteractionState(
    val kinds: List<Int>,
    val terminal: Int,
)

private data class ObservedInteractionList(
    val requestIds: List<String>,
    val terminal: Int,
)

private class InteractionFlowObserver(
    private val output: CPointer<COpaquePointerVar>,
) {
    val events = Channel<InteractionFlowEvent>(Channel.UNLIMITED)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun publishedSubscription(): COpaquePointer? = output.pointed.value
    fun dispose(): Unit = reference.dispose()
}

private val interactionFlowCallback = staticCFunction {
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        status: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<InteractionFlowObserver>().get()
    observer.events.trySend(
        InteractionFlowEvent(
            context,
            subscription,
            status,
            snapshot,
            terminal,
            observer.publishedSubscription(),
        ),
    )
    Unit
}

private suspend fun withInteractionFlowGraph(
    fixture: NativeCodexBehaviorFixture,
    block: suspend MemScope.(InteractionFlowGraph) -> Unit,
) {
    memScoped {
        val contextSlot = emptyInteractionFlowSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
        val runtime = contextLease.payload as CodexAgentCContextRuntime
        assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())
        val created = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            CodexAgentCHost(fixture.createHost(), runtime),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, created.status)
        val host = alloc<COpaquePointerVar>().also { it.value = assertNotNull(created.value) }
        selectInteractionFlowWorkspace(context, assertNotNull(host.value), fixture.workspace.path)

        val hostState = emptyInteractionFlowSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host.value, hostState.ptr))
        val agent = emptyInteractionFlowSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHostStateAgent(context, host.value, hostState.value, agent.ptr),
        )
        destroyInteractionFlowSnapshot(context, hostState.ptr)
        val interactions = emptyInteractionFlowSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAgentInteractions(context, agent.value, interactions.ptr),
        )
        val serviceLease = assertNotNull(
            handleRegistry.acquire(
                context,
                interactions.value,
                CodexAgentCHandleKind.INTERACTIONS,
            ).value,
        )
        val wrapper = serviceLease.payload as CodexAgentCInteractions
        val core = wrapper.core
        val owner = wrapper.owner
        assertEquals(CODEX_AGENT_STATUS_OK, serviceLease.close())
        owner.conversations.open(fixture.newConversationId)

        val graph = InteractionFlowGraph(contextSlot, context, host, agent, interactions, core)
        try {
            block(graph)
        } finally {
            if (!graph.hostClosed) closeInteractionFlowHost(graph)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(context, interactions.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(context, agent.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, host.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }
}

private suspend fun MemScope.selectInteractionFlowWorkspace(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        writeInteractionFlowUtf8(it.path, path)
    }
    launchInteractionFlowOperation(context) { output ->
        codexAgentHostSelectWorkspace(context, host, selection.ptr, null, null, output)
    }
}

private suspend fun MemScope.closeInteractionFlowHost(graph: InteractionFlowGraph) {
    if (graph.hostClosed) return
    launchInteractionFlowOperation(graph.context) { output ->
        codexAgentHostClose(graph.context, graph.host.value, null, null, output)
    }
    graph.hostClosed = true
}

private suspend fun MemScope.launchInteractionFlowOperation(
    context: COpaquePointer,
    launch: (CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = emptyInteractionFlowSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, launch(operation.ptr))
    withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
        val result = alloc<IntVar>()
        while (true) {
            when (val status = codexAgentOperationResult(context, operation.value, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> {
                    assertEquals(CODEX_AGENT_STATUS_OK, result.value)
                    break
                }

                else -> error("operation result failed with $status")
            }
        }
    }
    destroyInteractionFlowOperation(context, operation.ptr)
}

private suspend fun receiveInteractionState(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
): ObservedInteractionState {
    val event = receiveInteractionFlowEvent(graph.context, observer, subscription)
    return readInteractionState(graph, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun receiveInteractionStateUntil(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
    predicate: (ObservedInteractionState) -> Boolean,
): ObservedInteractionState = withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
    while (true) {
        val observed = receiveInteractionState(graph, observer, subscription)
        if (predicate(observed)) return@withTimeout observed
    }
    error("unreachable")
}

private fun readInteractionState(
    graph: InteractionFlowGraph,
    snapshot: COpaquePointer,
    terminal: Int,
): ObservedInteractionState = memScoped {
    val state = emptyInteractionFlowSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsStateValue(graph.context, snapshot, state.ptr),
    )
    val count = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionStatePendingCount(graph.context, state.value, count.ptr),
    )
    val expected = interactionStatePendingReferences(graph, assertNotNull(state.value))
    val children = buildList {
        repeat(count.value.toInt()) { index ->
            val interaction = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStatePendingAt(
                    graph.context,
                    state.value,
                    index.toULong(),
                    interaction.ptr,
                ),
            )
            add(assertNotNull(interaction.value))
        }
    }
    val stateSlot = alloc<COpaquePointerVar>().also { it.value = state.value }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateDestroy(graph.context, stateSlot.ptr))
    destroyInteractionFlowSnapshot(graph.context, snapshot)
    val kinds = buildList {
        children.forEachIndexed { index, interaction ->
            assertLiveInteractionSnapshot(graph, interaction, expected[index])
            val kind = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionKind(graph.context, interaction, kind.ptr),
            )
            add(kind.value)
            val interactionSlot = alloc<COpaquePointerVar>().also { it.value = interaction }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionDestroy(graph.context, interactionSlot.ptr),
            )
        }
    }
    ObservedInteractionState(kinds, terminal)
}

private suspend fun receiveInteractionApprovals(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
): ObservedInteractionList {
    val event = receiveInteractionFlowEvent(graph.context, observer, subscription)
    return readInteractionApprovals(graph, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun receiveInteractionApprovalsUntil(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
    predicate: (ObservedInteractionList) -> Boolean,
): ObservedInteractionList = withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
    while (true) {
        val observed = receiveInteractionApprovals(graph, observer, subscription)
        if (predicate(observed)) return@withTimeout observed
    }
    error("unreachable")
}

private fun readInteractionApprovals(
    graph: InteractionFlowGraph,
    snapshot: COpaquePointer,
    terminal: Int,
): ObservedInteractionList = memScoped {
    val count = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsApprovalsCount(graph.context, snapshot, count.ptr),
    )
    val expected = approvalReferences(graph, snapshot)
    val children = buildList {
        repeat(count.value.toInt()) { index ->
            val approval = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsAt(
                    graph.context,
                    snapshot,
                    index.toULong(),
                    approval.ptr,
                ),
            )
            add(assertNotNull(approval.value))
        }
    }
    destroyInteractionFlowSnapshot(graph.context, snapshot)
    val requestIds = buildList {
        children.forEachIndexed { index, approval ->
            assertLiveApprovalSnapshot(graph, approval, expected[index])
            add(copyPendingRequestId(graph.context, approval, ::codexAgentPendingApprovalRequestIdCopy))
            val approvalSlot = alloc<COpaquePointerVar>().also { it.value = approval }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalDestroy(graph.context, approvalSlot.ptr),
            )
        }
    }
    ObservedInteractionList(requestIds, terminal)
}

private suspend fun receiveInteractionElicitations(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
): ObservedInteractionList {
    val event = receiveInteractionFlowEvent(graph.context, observer, subscription)
    return readInteractionElicitations(graph, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun receiveInteractionElicitationsUntil(
    graph: InteractionFlowGraph,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
    predicate: (ObservedInteractionList) -> Boolean,
): ObservedInteractionList = withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
    while (true) {
        val observed = receiveInteractionElicitations(graph, observer, subscription)
        if (predicate(observed)) return@withTimeout observed
    }
    error("unreachable")
}

private fun readInteractionElicitations(
    graph: InteractionFlowGraph,
    snapshot: COpaquePointer,
    terminal: Int,
): ObservedInteractionList = memScoped {
    val count = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsElicitationsCount(graph.context, snapshot, count.ptr),
    )
    val expected = elicitationReferences(graph, snapshot)
    val children = buildList {
        repeat(count.value.toInt()) { index ->
            val elicitation = emptyInteractionFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsElicitationsAt(
                    graph.context,
                    snapshot,
                    index.toULong(),
                    elicitation.ptr,
                ),
            )
            add(assertNotNull(elicitation.value))
        }
    }
    destroyInteractionFlowSnapshot(graph.context, snapshot)
    val requestIds = buildList {
        children.forEachIndexed { index, elicitation ->
            assertLiveElicitationSnapshot(graph, elicitation, expected[index])
            add(copyPendingRequestId(graph.context, elicitation, ::codexAgentPendingElicitationRequestIdCopy))
            val elicitationSlot = alloc<COpaquePointerVar>().also { it.value = elicitation }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingElicitationDestroy(graph.context, elicitationSlot.ptr),
            )
        }
    }
    ObservedInteractionList(requestIds, terminal)
}

private suspend fun receiveInteractionFlowEvent(
    context: COpaquePointer,
    observer: InteractionFlowObserver,
    subscription: COpaquePointer?,
): InteractionFlowEvent = withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
    observer.events.receive().also {
        assertEquals(context, it.context)
        assertEquals(subscription, it.subscription)
        assertEquals(subscription, it.publishedSubscription)
        assertEquals(CODEX_AGENT_STATUS_OK, it.status)
    }
}

private fun assertLiveInteractionSnapshot(
    graph: InteractionFlowGraph,
    handle: COpaquePointer,
    expected: Any,
) {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, handle, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val snapshot = lease.payload as CodexAgentCPendingInteractionSnapshot
    assertTrue(snapshot.owner === graph.core)
    assertTrue(snapshot.value === expected)
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
}

private fun assertLiveApprovalSnapshot(
    graph: InteractionFlowGraph,
    handle: COpaquePointer,
    expected: Any,
) {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, handle, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val snapshot = lease.payload as CodexAgentCPendingApprovalSnapshot
    assertTrue(snapshot.owner === graph.core)
    assertTrue(snapshot.value === expected)
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
}

private fun assertLiveElicitationSnapshot(
    graph: InteractionFlowGraph,
    handle: COpaquePointer,
    expected: Any,
) {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, handle, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val snapshot = lease.payload as CodexAgentCPendingElicitationSnapshot
    assertTrue(snapshot.owner === graph.core)
    assertTrue(snapshot.value === expected)
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
}

private fun interactionStatePendingReferences(
    graph: InteractionFlowGraph,
    state: COpaquePointer,
): List<Any> {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, state, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val snapshot = lease.payload as CodexAgentCInteractionStateSnapshot
    assertTrue(snapshot.owner === graph.core)
    val values = snapshot.value.pending.toList()
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
    return values
}

private fun approvalReferences(
    graph: InteractionFlowGraph,
    snapshot: COpaquePointer,
): List<Any> {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, snapshot, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val payload = lease.payload as CodexAgentCApprovalsStateSnapshot
    assertTrue(payload.owner === graph.core)
    val values = payload.values.toList()
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
    return values
}

private fun elicitationReferences(
    graph: InteractionFlowGraph,
    snapshot: COpaquePointer,
): List<Any> {
    val lease = assertNotNull(
        handleRegistry.acquire(graph.context, snapshot, CodexAgentCHandleKind.SNAPSHOT).value,
    )
    val payload = lease.payload as CodexAgentCElicitationsStateSnapshot
    assertTrue(payload.owner === graph.core)
    val values = payload.values.toList()
    assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
    return values
}

private typealias PendingRequestIdCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private fun MemScope.copyPendingRequestId(
    context: COpaquePointer,
    handle: COpaquePointer?,
    copy: PendingRequestIdCopy,
): String {
    val required = alloc<ULongVar>()
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    val size = required.value.toInt()
    val buffer = allocArray<UByteVar>(size)
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, required.value, required.ptr))
    return ByteArray(size) { buffer[it].toByte() }.decodeToString()
}

private suspend fun destroyInteractionFlowSubscription(
    context: COpaquePointer,
    subscription: CPointer<COpaquePointerVar>,
) {
    withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentSubscriptionDestroy(context, subscription)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("subscription destroy failed with $status")
            }
        }
    }
    assertNull(subscription.pointed.value)
}

private suspend fun destroyInteractionFlowOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(INTERACTION_FLOW_TIMEOUT_MILLIS) {
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

private suspend fun assertNoInteractionFlowEvent(observer: InteractionFlowObserver) {
    assertNull(withTimeoutOrNull(100L) { observer.events.receive() })
}

private fun destroyInteractionFlowSnapshot(
    context: COpaquePointer,
    snapshot: COpaquePointer,
) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = snapshot }
    destroyInteractionFlowSnapshot(context, slot.ptr)
}

private fun destroyInteractionFlowSnapshot(
    context: COpaquePointer,
    slot: CPointer<COpaquePointerVar>,
) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot))
    assertNull(slot.pointed.value)
}

private fun MemScope.emptyInteractionFlowSlot(): COpaquePointerVar = alloc<COpaquePointerVar>().also {
    it.value = null
}

private fun MemScope.writeInteractionFlowUtf8(target: codex_agent_string_view, value: String) {
    val bytes = value.encodeToByteArray()
    target.size = bytes.size.toULong()
    target.data = allocArray<UByteVar>(bytes.size).also { buffer ->
        bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    }
}

private fun approvalRequest() = buildJsonObject {
    put("itemId", "native-item")
    put("startedAtMs", 1)
    put("threadId", "native-thread")
    put("turnId", "native-turn")
    put("command", "git status")
    put("reason", "Inspect the workspace")
}

private fun urlElicitation(id: Long) = buildJsonObject {
    put("serverName", "native")
    put("threadId", "native-thread")
    put("elicitationId", "native-elicitation-$id")
    put("message", "Sign in")
    put("url", "https://accounts.example.com/authorize")
    put("turnId", "native-turn")
    put("mode", "url")
}

private const val INTERACTION_APPROVAL_METHOD = "item/commandExecution/requestApproval"
private const val INTERACTION_ELICITATION_METHOD = "mcpServer/elicitation/request"
private const val INTERACTION_APPROVAL_KIND = 0
private const val INTERACTION_ELICITATION_KIND = 1
private const val INTERACTION_FLOW_TIMEOUT_MILLIS = 10_000L
