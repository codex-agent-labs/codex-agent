@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPurpose
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexInteractions
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.concurrent.atomics.AtomicBoolean
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
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
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexAgentCInteractionOperationsTest {
    @Test
    fun interactionStateIsResolvingRequiresExactLivePendingIdentity(): Unit = runBlocking {
        val gates = Channel<CompletableDeferred<Unit>>(Channel.UNLIMITED)
        val responses = Channel<JsonObject>(Channel.UNLIMITED)
        val fixture = interactionOperationFixture { response ->
            responses.send(response)
            gates.receive().await()
        }
        withInteractionOperationGraph(fixture) { graph ->
            val approval = emptyInteractionOperationSlot()
            val liveInteraction = emptyInteractionOperationSlot()
            val before = emptyInteractionOperationSlot()
            val resolving = alloc<IntVar>().also { it.value = 71 }
            var operation: COpaquePointerVar? = null
            val gate = CompletableDeferred<Unit>()
            gates.send(gate)
            try {
                approval.value = awaitApproval(graph, fixture, 401)
                liveInteraction.value = pendingInteractionFromApproval(graph.context, approval.value).value
                before.value = interactionState(graph).value
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        before.value,
                        liveInteraction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(0, resolving.value)

                operation = launchApprovalForResolving(graph, approval.value)
                val wire = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { responses.receive() }
                assertEquals(
                    "accept",
                    wire.getValue("result").jsonObject.getValue("decision").jsonPrimitive.content,
                )

                val during = emptyInteractionOperationSlot().also {
                    it.value = awaitResolvingState(graph, "401")
                }
                resolving.value = 72
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        during.value,
                        liveInteraction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(1, resolving.value)

                val copied = copiedInteractionState(graph.context, liveInteraction.value, "401")
                resolving.value = 73
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        copied.state.value,
                        copied.interaction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(0, resolving.value)

                val siblingFixture = interactionOperationFixture()
                val sibling = installInteractionOperationGraph(graph.context, siblingFixture, siblingFixture.platform)
                try {
                    val siblingApproval = emptyInteractionOperationSlot().also {
                        it.value = awaitApproval(sibling, siblingFixture, 401)
                    }
                    val siblingInteraction = pendingInteractionFromApproval(graph.context, siblingApproval.value)
                    resolving.value = 74
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentInteractionStateIsResolving(
                            graph.context,
                            during.value,
                            siblingInteraction.value,
                            resolving.ptr,
                        ),
                    )
                    assertEquals(0, resolving.value)
                    destroyPendingInteraction(graph.context, siblingInteraction)
                    destroyPendingApproval(graph.context, siblingApproval)
                } finally {
                    closeAndReleaseInteractionOperationGraph(sibling)
                }

                resolving.value = 75
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        liveInteraction.value,
                        liveInteraction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(75, resolving.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        during.value,
                        graph.agent.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(75, resolving.value)

                val otherContextSlot = newInteractionOperationContext()
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionStateIsResolving(
                        otherContextSlot.value,
                        during.value,
                        liveInteraction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(75, resolving.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))

                val staleState = assertNotNull(copied.state.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateDestroy(graph.context, copied.state.ptr))
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        staleState,
                        copied.interaction.value,
                        resolving.ptr,
                    ),
                )
                assertEquals(75, resolving.value)
                val staleInteraction = assertNotNull(copied.interaction.value)
                destroyPendingInteraction(graph.context, copied.interaction)
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentInteractionStateIsResolving(
                        graph.context,
                        during.value,
                        staleInteraction,
                        resolving.ptr,
                    ),
                )
                assertEquals(75, resolving.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionStateIsResolving(graph.context, null, liveInteraction.value, resolving.ptr),
                )
                assertEquals(75, resolving.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionStateIsResolving(graph.context, during.value, null, resolving.ptr),
                )
                assertEquals(75, resolving.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentInteractionStateIsResolving(graph.context, during.value, liveInteraction.value, null),
                )
                destroyInteractionState(graph.context, during)
            } finally {
                gate.complete(Unit)
            }
            val completedOperation = checkNotNull(operation)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitInteractionOperationResult(graph.context, completedOperation.value),
            )
            destroyInteractionOperation(graph.context, completedOperation.ptr)
            val after = interactionState(graph)
            resolving.value = 76
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStateIsResolving(
                    graph.context,
                    after.value,
                    liveInteraction.value,
                    resolving.ptr,
                ),
            )
            assertEquals(0, resolving.value)

            destroyInteractionState(graph.context, before)
            destroyInteractionState(graph.context, after)
            destroyPendingInteraction(graph.context, liveInteraction)
            destroyPendingApproval(graph.context, approval)
        }
    }

    @Test
    fun resolveApprovalUsesExactOwnedPendingIdentityAndCompletesCancellableOperation(): Unit = runBlocking {
        val gates = Channel<CompletableDeferred<Unit>>(Channel.UNLIMITED)
        val responses = Channel<JsonObject>(Channel.UNLIMITED)
        val fixture = interactionOperationFixture { response ->
            responses.send(response)
            gates.receive().await()
        }
        withInteractionOperationGraph(fixture) { graph ->
            val approval = emptyInteractionOperationSlot()
            val removedAlias = emptyInteractionOperationSlot()
            val operation = emptyInteractionOperationSlot()
            val observer = InteractionOperationObserver(operation.ptr)
            val gate = CompletableDeferred<Unit>()
            gates.send(gate)
            try {
                approval.value = awaitApproval(graph, fixture, 411)
                removedAlias.value = awaitExistingApproval(graph, "411")
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsResolveApproval(
                        graph.context,
                        graph.interactions.value,
                        approval.value,
                        APPROVAL_ACCEPT,
                        interactionOperationCallback,
                        observer.userData,
                        operation.ptr,
                    ),
                )
                assertNotNull(operation.value)
                destroyPendingApproval(graph.context, approval)
                val wire = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { responses.receive() }
                assertEquals("411", wire.getValue("id").jsonPrimitive.content)
                assertEquals("accept", wire.getValue("result").jsonObject.getValue("decision").jsonPrimitive.content)
                val busyContext = alloc<COpaquePointerVar>().also { it.value = graph.context }
                assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentContextDestroy(busyContext.ptr))
                assertEquals(graph.context, busyContext.value)
                val resolvingState = emptyInteractionOperationSlot().also {
                    it.value = awaitResolvingState(graph, "411")
                }
                assertTrue(interactionStateContains(graph.context, resolvingState.value, "411"))
                destroyInteractionState(graph.context, resolvingState)
            } finally {
                gate.complete(Unit)
            }
            receiveInteractionOperationCallback(observer, graph.context, operation.value)
            assertEquals(CODEX_AGENT_STATUS_OK, awaitInteractionOperationResult(graph.context, operation.value))
            destroyInteractionOperation(graph.context, operation.ptr)
            assertEquals(1, observer.callbacks.load())
            assertNull(withTimeoutOrNull(100L) { observer.events.receive() })
            observer.dispose()
            assertEquals(0uL, approvalCount(graph))

            val staleOutput = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    removedAlias.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    staleOutput.ptr,
                ),
            )
            assertNull(staleOutput.value)

            val cancelledApproval = emptyInteractionOperationSlot().also {
                it.value = awaitApproval(graph, fixture, 412)
            }
            val cancelledInteraction = pendingInteractionFromApproval(graph.context, cancelledApproval.value)
            val cancelled = emptyInteractionOperationSlot()
            val cancelledObserver = InteractionOperationObserver(cancelled.ptr)
            val cancellingState = emptyInteractionOperationSlot()
            val cancelGate = CompletableDeferred<Unit>()
            gates.send(cancelGate)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsResolveApproval(
                        graph.context,
                        graph.interactions.value,
                        cancelledApproval.value,
                        APPROVAL_DECLINE,
                        interactionOperationCallback,
                        cancelledObserver.userData,
                        cancelled.ptr,
                    ),
                )
                assertEquals(
                    "decline",
                    withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { responses.receive() }
                        .getValue("result").jsonObject.getValue("decision").jsonPrimitive.content,
                )
                cancellingState.value = awaitResolvingState(graph, "412")
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(graph.context, cancelled.value))
            } finally {
                cancelGate.complete(Unit)
            }
            receiveInteractionOperationCallback(cancelledObserver, graph.context, cancelled.value)
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitInteractionOperationResult(graph.context, cancelled.value))
            destroyInteractionOperation(graph.context, cancelled.ptr)
            assertEquals(1, cancelledObserver.callbacks.load())
            cancelledObserver.dispose()
            val afterCancellation = emptyInteractionOperationSlot().also {
                it.value = awaitNotResolvingState(graph, "412")
            }
            assertEquals(1uL, approvalCount(graph))
            destroyInteractionState(graph.context, cancellingState)
            destroyInteractionState(graph.context, afterCancellation)

            val ownerless = copiedApproval(graph.context, cancelledApproval.value)
            val empty = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    ownerless.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertNull(empty.value)

            val siblingFixture = interactionOperationFixture()
            val sibling = installInteractionOperationGraph(graph.context, siblingFixture, siblingFixture.platform)
            try {
                val siblingApproval = emptyInteractionOperationSlot().also {
                    it.value = awaitApproval(sibling, siblingFixture, 412)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsResolveApproval(
                        graph.context,
                        graph.interactions.value,
                        siblingApproval.value,
                        APPROVAL_ACCEPT,
                        null,
                        null,
                        empty.ptr,
                    ),
                )
                assertNull(empty.value)
                destroyPendingApproval(graph.context, siblingApproval)
            } finally {
                closeAndReleaseInteractionOperationGraph(sibling)
            }

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    cancelledApproval.value,
                    Int.MAX_VALUE,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.agent.value,
                    cancelledApproval.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    graph.agent.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            val otherContext = newInteractionOperationContext()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsResolveApproval(
                    otherContext.value,
                    graph.interactions.value,
                    cancelledApproval.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val staleOwnerless = assertNotNull(ownerless.value)
            destroyPendingApproval(graph.context, ownerless)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    staleOwnerless,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    null,
                    cancelledApproval.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    null,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    cancelledApproval.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    null,
                ),
            )
            assertNull(empty.value)
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.agent.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveApproval(
                    graph.context,
                    graph.interactions.value,
                    cancelledApproval.value,
                    APPROVAL_ACCEPT,
                    null,
                    null,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.agent.value, occupied.value)

            destroyPendingApproval(graph.context, removedAlias)
            destroyPendingInteraction(graph.context, cancelledInteraction)
            destroyPendingApproval(graph.context, cancelledApproval)
        }
    }

    @Test
    fun resolveElicitationCopiesResponseAndUsesExactOwnedPendingIdentity(): Unit = runBlocking {
        val gates = Channel<CompletableDeferred<Unit>>(Channel.UNLIMITED)
        val responses = Channel<JsonObject>(Channel.UNLIMITED)
        val fixture = interactionOperationFixture { response ->
            responses.send(response)
            gates.receive().await()
        }
        withInteractionOperationGraph(fixture) { graph ->
            val elicitation = emptyInteractionOperationSlot().also {
                it.value = awaitFormElicitation(graph, fixture, 421)
            }
            val removedAlias = emptyInteractionOperationSlot().also {
                it.value = awaitExistingElicitation(graph, "421")
            }
            val response = validElicitationResponse(graph.context)
            val operation = emptyInteractionOperationSlot()
            val observer = InteractionOperationObserver(operation.ptr)
            val gate = CompletableDeferred<Unit>()
            gates.send(gate)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsResolveElicitation(
                        graph.context,
                        graph.interactions.value,
                        elicitation.value,
                        response.value,
                        interactionOperationCallback,
                        observer.userData,
                        operation.ptr,
                    ),
                )
                destroyPendingElicitation(graph.context, elicitation)
                destroyElicitationResponse(graph.context, response)
                val wire = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { responses.receive() }
                val result = wire.getValue("result").jsonObject
                assertEquals("accept", result.getValue("action").jsonPrimitive.content)
                assertEquals(
                    listOf("one"),
                    result.getValue("content").jsonObject.getValue("choices").jsonArray.map {
                        it.jsonPrimitive.content
                    },
                )
                val busyContext = alloc<COpaquePointerVar>().also { it.value = graph.context }
                assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentContextDestroy(busyContext.ptr))
                assertEquals(graph.context, busyContext.value)
                val resolvingState = emptyInteractionOperationSlot().also {
                    it.value = awaitResolvingState(graph, "421")
                }
                assertTrue(interactionStateContains(graph.context, resolvingState.value, "421"))
                destroyInteractionState(graph.context, resolvingState)
            } finally {
                gate.complete(Unit)
            }
            receiveInteractionOperationCallback(observer, graph.context, operation.value)
            assertEquals(CODEX_AGENT_STATUS_OK, awaitInteractionOperationResult(graph.context, operation.value))
            destroyInteractionOperation(graph.context, operation.ptr)
            assertEquals(1, observer.callbacks.load())
            assertNull(withTimeoutOrNull(100L) { observer.events.receive() })
            observer.dispose()
            assertEquals(0uL, elicitationCount(graph))

            val staleOutput = emptyInteractionOperationSlot()
            val staleResponse = declineElicitationResponse(graph.context)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    removedAlias.value,
                    staleResponse.value,
                    null,
                    null,
                    staleOutput.ptr,
                ),
            )
            assertNull(staleOutput.value)
            destroyElicitationResponse(graph.context, staleResponse)

            val cancelledElicitation = emptyInteractionOperationSlot().also {
                it.value = awaitFormElicitation(graph, fixture, 422)
            }
            val cancelledResponse = validElicitationResponse(graph.context)
            val cancelled = emptyInteractionOperationSlot()
            val cancelledObserver = InteractionOperationObserver(cancelled.ptr)
            val cancelGate = CompletableDeferred<Unit>()
            gates.send(cancelGate)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentInteractionsResolveElicitation(
                        graph.context,
                        graph.interactions.value,
                        cancelledElicitation.value,
                        cancelledResponse.value,
                        interactionOperationCallback,
                        cancelledObserver.userData,
                        cancelled.ptr,
                    ),
                )
                withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { responses.receive() }
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(graph.context, cancelled.value))
            } finally {
                cancelGate.complete(Unit)
            }
            receiveInteractionOperationCallback(cancelledObserver, graph.context, cancelled.value)
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitInteractionOperationResult(graph.context, cancelled.value))
            destroyInteractionOperation(graph.context, cancelled.ptr)
            assertEquals(1, cancelledObserver.callbacks.load())
            cancelledObserver.dispose()
            val afterCancellation = emptyInteractionOperationSlot().also {
                it.value = awaitNotResolvingState(graph, "422")
            }
            assertEquals(1uL, elicitationCount(graph))
            destroyInteractionState(graph.context, afterCancellation)

            val ownerless = copiedElicitation(graph.context, cancelledElicitation.value)
            val empty = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    ownerless.value,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )

            val siblingFixture = interactionOperationFixture()
            val sibling = installInteractionOperationGraph(graph.context, siblingFixture, siblingFixture.platform)
            try {
                val siblingElicitation = emptyInteractionOperationSlot().also {
                    it.value = awaitFormElicitation(sibling, siblingFixture, 422)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsResolveElicitation(
                        graph.context,
                        graph.interactions.value,
                        siblingElicitation.value,
                        cancelledResponse.value,
                        null,
                        null,
                        empty.ptr,
                    ),
                )
                destroyPendingElicitation(graph.context, siblingElicitation)
            } finally {
                closeAndReleaseInteractionOperationGraph(sibling)
            }

            val invalidResponse = emptyAcceptElicitationResponse(graph.context)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    invalidResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertNull(empty.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.agent.value,
                    cancelledElicitation.value,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    graph.agent.value,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    graph.agent.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            val otherContext = newInteractionOperationContext()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsResolveElicitation(
                    otherContext.value,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val staleOwnerless = assertNotNull(ownerless.value)
            destroyPendingElicitation(graph.context, ownerless)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    staleOwnerless,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            val staleResponsePointer = assertNotNull(invalidResponse.value)
            destroyElicitationResponse(graph.context, invalidResponse)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    staleResponsePointer,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    null,
                    cancelledElicitation.value,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    null,
                    cancelledResponse.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    null,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    cancelledResponse.value,
                    null,
                    null,
                    null,
                ),
            )
            assertNull(empty.value)
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.agent.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsResolveElicitation(
                    graph.context,
                    graph.interactions.value,
                    cancelledElicitation.value,
                    cancelledResponse.value,
                    null,
                    null,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.agent.value, occupied.value)

            destroyElicitationResponse(graph.context, cancelledResponse)
            destroyPendingElicitation(graph.context, cancelledElicitation)
            destroyPendingElicitation(graph.context, removedAlias)
        }
    }

    @Test
    fun openUrlUsesExactOwnedPendingIdentityAndOwnsBrowserPresentation(): Unit = runBlocking {
        val openedUrls = mutableListOf<Pair<String, CodexAuthorizationPurpose>>()
        val closedPresentations = AtomicInt(0)
        val browserFailure = AtomicBoolean(false)
        val cancelOnOpen = AtomicBoolean(false)
        val browserEntered = CompletableDeferred<Unit>()
        val releaseBrowser = AtomicBoolean(false)
        val browser = CodexAuthorizationBrowser { url ->
            if (browserFailure.load()) error("browser failed")
            openedUrls += url.value to url.purpose
            if (cancelOnOpen.load()) {
                browserEntered.complete(Unit)
                while (!releaseBrowser.load()) Unit
                cancelOnOpen.store(false)
            }
            CodexAuthorizationPresentation { closedPresentations.addAndFetch(1) }
        }
        val fixture = interactionOperationFixture()
        val platform = object : CodexPlatform by fixture.platform {
            override val authorizationBrowser: CodexAuthorizationBrowser = browser
        }
        withInteractionOperationGraph(fixture, platform) { graph ->
            val elicitation = emptyInteractionOperationSlot().also {
                it.value = awaitUrlElicitation(graph, fixture, 431)
            }
            val secondAlias = emptyInteractionOperationSlot().also {
                it.value = awaitExistingElicitation(graph, "431")
            }
            val first = emptyInteractionOperationSlot()
            val firstObserver = InteractionOperationObserver(first.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    elicitation.value,
                    interactionOperationCallback,
                    firstObserver.userData,
                    first.ptr,
                ),
            )
            destroyPendingElicitation(graph.context, elicitation)
            receiveInteractionOperationCallback(firstObserver, graph.context, first.value)
            assertEquals(CODEX_AGENT_STATUS_OK, awaitInteractionOperationResult(graph.context, first.value))
            destroyInteractionOperation(graph.context, first.ptr)
            assertEquals(1, firstObserver.callbacks.load())
            firstObserver.dispose()
            assertEquals(listOf(AUTHORIZATION_URL to CodexAuthorizationPurpose.EXTERNAL), openedUrls)
            assertEquals(0, closedPresentations.load())
            assertEquals(1uL, elicitationCount(graph))

            val second = emptyInteractionOperationSlot()
            val secondObserver = InteractionOperationObserver(second.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    secondAlias.value,
                    interactionOperationCallback,
                    secondObserver.userData,
                    second.ptr,
                ),
            )
            receiveInteractionOperationCallback(secondObserver, graph.context, second.value)
            assertEquals(CODEX_AGENT_STATUS_OK, awaitInteractionOperationResult(graph.context, second.value))
            destroyInteractionOperation(graph.context, second.ptr)
            assertEquals(1, secondObserver.callbacks.load())
            secondObserver.dispose()
            assertEquals(2, openedUrls.size)
            assertEquals(1, closedPresentations.load())

            browserFailure.store(true)
            val failureElicitation = emptyInteractionOperationSlot().also {
                it.value = awaitUrlElicitation(graph, fixture, 432)
            }
            val failed = emptyInteractionOperationSlot()
            val failureObserver = InteractionOperationObserver(failed.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    failureElicitation.value,
                    interactionOperationCallback,
                    failureObserver.userData,
                    failed.ptr,
                ),
            )
            receiveInteractionOperationCallback(failureObserver, graph.context, failed.value)
            assertEquals(
                CODEX_AGENT_STATUS_OPERATION_FAILED,
                awaitInteractionOperationResult(graph.context, failed.value),
            )
            val failure = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationFailure(graph.context, failed.value, failure.ptr),
            )
            assertEquals(
                "authorization_browser_failed",
                copyInteractionOperationString(graph.context, failure.value, ::codexAgentFailureCodeCopy),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(graph.context, failure.ptr))
            val failureState = interactionState(graph)
            val hasFailure = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStateHasFailure(graph.context, failureState.value, hasFailure.ptr),
            )
            assertEquals(1, hasFailure.value)
            val stateFailure = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStateFailure(graph.context, failureState.value, stateFailure.ptr),
            )
            assertEquals(
                "authorization_browser_failed",
                copyInteractionOperationString(graph.context, stateFailure.value, ::codexAgentFailureCodeCopy),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(graph.context, stateFailure.ptr))
            destroyInteractionState(graph.context, failureState)
            destroyInteractionOperation(graph.context, failed.ptr)
            assertEquals(1, failureObserver.callbacks.load())
            failureObserver.dispose()
            browserFailure.store(false)

            val cancellable = emptyInteractionOperationSlot().also {
                it.value = awaitUrlElicitation(graph, fixture, 433)
            }
            val cancelled = emptyInteractionOperationSlot()
            val cancelObserver = InteractionOperationObserver(cancelled.ptr)
            cancelOnOpen.store(true)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    cancellable.value,
                    interactionOperationCallback,
                    cancelObserver.userData,
                    cancelled.ptr,
                ),
            )
            try {
                withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) { browserEntered.await() }
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(graph.context, cancelled.value))
            } finally {
                releaseBrowser.store(true)
            }
            destroyPendingElicitation(graph.context, cancellable)
            receiveInteractionOperationCallback(cancelObserver, graph.context, cancelled.value)
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitInteractionOperationResult(graph.context, cancelled.value))
            destroyInteractionOperation(graph.context, cancelled.ptr)
            assertEquals(1, cancelObserver.callbacks.load())
            cancelObserver.dispose()

            val form = emptyInteractionOperationSlot().also {
                it.value = awaitFormElicitation(graph, fixture, 434)
            }
            val empty = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    form.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertNull(empty.value)

            val ownerless = copiedElicitation(graph.context, secondAlias.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    ownerless.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            val siblingFixture = interactionOperationFixture()
            val sibling = installInteractionOperationGraph(graph.context, siblingFixture, siblingFixture.platform)
            try {
                val siblingElicitation = emptyInteractionOperationSlot().also {
                    it.value = awaitUrlElicitation(sibling, siblingFixture, 431)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentInteractionsOpenUrl(
                        graph.context,
                        graph.interactions.value,
                        siblingElicitation.value,
                        null,
                        null,
                        empty.ptr,
                    ),
                )
                destroyPendingElicitation(graph.context, siblingElicitation)
            } finally {
                closeAndReleaseInteractionOperationGraph(sibling)
            }

            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.agent.value,
                    secondAlias.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    graph.agent.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            val otherContext = newInteractionOperationContext()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionsOpenUrl(
                    otherContext.value,
                    graph.interactions.value,
                    secondAlias.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
            val staleOwnerless = assertNotNull(ownerless.value)
            destroyPendingElicitation(graph.context, ownerless)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    staleOwnerless,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    null,
                    secondAlias.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    null,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    secondAlias.value,
                    null,
                    null,
                    null,
                ),
            )
            assertNull(empty.value)
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.agent.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    secondAlias.value,
                    null,
                    null,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.agent.value, occupied.value)

            graph.conversation.close()
            awaitNoElicitations(graph)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInteractionsOpenUrl(
                    graph.context,
                    graph.interactions.value,
                    secondAlias.value,
                    null,
                    null,
                    empty.ptr,
                ),
            )
            assertEquals(3, closedPresentations.load())

            destroyPendingElicitation(graph.context, secondAlias)
            destroyPendingElicitation(graph.context, failureElicitation)
            destroyPendingElicitation(graph.context, form)
        }
    }
}

private data class InteractionOperationGraph(
    val context: COpaquePointer,
    val host: COpaquePointerVar,
    val agent: COpaquePointerVar,
    val interactions: COpaquePointerVar,
    val core: CodexInteractions,
    val conversation: CodexConversation,
    var hostClosed: Boolean = false,
)

private data class CopiedInteractionState(
    val state: COpaquePointerVar,
    val interaction: COpaquePointerVar,
)

private data class InteractionOperationEvent(
    val context: COpaquePointer?,
    val operation: COpaquePointer?,
    val userData: COpaquePointer?,
    val publishedOperation: COpaquePointer?,
)

private class InteractionOperationObserver(
    private val output: CPointer<COpaquePointerVar>,
) {
    val callbacks = AtomicInt(0)
    val events = Channel<InteractionOperationEvent>(Channel.UNLIMITED)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun publishedOperation(): COpaquePointer? = output.pointed.value
    fun dispose(): Unit = reference.dispose()
}

private val interactionOperationCallback = staticCFunction {
        context: COpaquePointer?,
        operation: COpaquePointer?,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<InteractionOperationObserver>().get()
    observer.callbacks.addAndFetch(1)
    observer.events.trySend(
        InteractionOperationEvent(context, operation, userData, observer.publishedOperation()),
    )
    Unit
}

private fun interactionOperationFixture(
    onServerResponse: suspend (JsonObject) -> Unit = {},
): NativeCodexBehaviorFixture = NativeCodexBehaviorFixture(onServerResponse = onServerResponse)

private suspend fun withInteractionOperationGraph(
    fixture: NativeCodexBehaviorFixture,
    platform: CodexPlatform = fixture.platform,
    block: suspend MemScope.(InteractionOperationGraph) -> Unit,
) {
    memScoped {
        val contextSlot = newInteractionOperationContext()
        val context = assertNotNull(contextSlot.value)
        val graph = installInteractionOperationGraph(context, fixture, platform)
        try {
            block(graph)
        } finally {
            closeAndReleaseInteractionOperationGraph(graph)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }
}

private suspend fun MemScope.installInteractionOperationGraph(
    context: COpaquePointer,
    fixture: NativeCodexBehaviorFixture,
    platform: CodexPlatform,
): InteractionOperationGraph {
    val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
    val runtime = contextLease.payload as CodexAgentCContextRuntime
    assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())
    val created = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        CodexAgentCHost(CodexHost(platform, fixture.clientInfo), runtime),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    val host = alloc<COpaquePointerVar>().also { it.value = assertNotNull(created.value) }
    selectInteractionOperationWorkspace(context, assertNotNull(host.value), fixture.workspace.path)

    val hostState = emptyInteractionOperationSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host.value, hostState.ptr))
    val agent = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostStateAgent(context, host.value, hostState.value, agent.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, hostState.ptr))
    val interactions = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentAgentInteractions(context, agent.value, interactions.ptr),
    )
    val serviceLease = assertNotNull(
        handleRegistry.acquire(context, interactions.value, CodexAgentCHandleKind.INTERACTIONS).value,
    )
    val wrapper = serviceLease.payload as CodexAgentCInteractions
    val core = wrapper.core
    val owner = wrapper.owner
    assertEquals(CODEX_AGENT_STATUS_OK, serviceLease.close())
    val conversation = owner.conversations.open(fixture.newConversationId)
    return InteractionOperationGraph(context, host, agent, interactions, core, conversation)
}

private suspend fun MemScope.closeAndReleaseInteractionOperationGraph(graph: InteractionOperationGraph) {
    if (!graph.hostClosed) {
        launchInteractionOperationWithoutCallback(graph.context) { output ->
            codexAgentHostClose(graph.context, graph.host.value, null, null, output)
        }
        graph.hostClosed = true
    }
    if (graph.interactions.value != null) {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionsRelease(graph.context, graph.interactions.ptr))
    }
    if (graph.agent.value != null) {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(graph.context, graph.agent.ptr))
    }
    if (graph.host.value != null) {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(graph.context, graph.host.ptr))
    }
}

private fun MemScope.newInteractionOperationContext(): COpaquePointerVar =
    emptyInteractionOperationSlot().also {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
        assertNotNull(it.value)
    }

private suspend fun MemScope.selectInteractionOperationWorkspace(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        writeInteractionOperationUtf8(it.path, path)
    }
    launchInteractionOperationWithoutCallback(context) { output ->
        codexAgentHostSelectWorkspace(context, host, selection.ptr, null, null, output)
    }
}

private suspend fun MemScope.launchInteractionOperationWithoutCallback(
    context: COpaquePointer,
    launch: (CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = emptyInteractionOperationSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, launch(operation.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, awaitInteractionOperationResult(context, operation.value))
    destroyInteractionOperation(context, operation.ptr)
}

private suspend fun MemScope.awaitApproval(
    graph: InteractionOperationGraph,
    fixture: NativeCodexBehaviorFixture,
    id: Long,
): COpaquePointer {
    fixture.request(id, APPROVAL_METHOD, approvalRequest())
    return awaitExistingApproval(graph, id.toString())
}

private suspend fun MemScope.awaitExistingApproval(
    graph: InteractionOperationGraph,
    requestId: String,
): COpaquePointer = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    while (true) {
        val snapshot = emptyInteractionOperationSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, snapshot.ptr),
        )
        val count = alloc<ULongVar>()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInteractionsApprovalsCount(graph.context, snapshot.value, count.ptr),
        )
        repeat(count.value.toInt()) { index ->
            val approval = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsApprovalsAt(
                    graph.context,
                    snapshot.value,
                    index.toULong(),
                    approval.ptr,
                ),
            )
            if (copyInteractionOperationString(
                    graph.context,
                    approval.value,
                    ::codexAgentPendingApprovalRequestIdCopy,
                ) == requestId
            ) {
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
                return@withTimeout assertNotNull(approval.value)
            }
            destroyPendingApproval(graph.context, approval)
        }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
        yield()
    }
    error("unreachable")
}

private suspend fun MemScope.awaitUrlElicitation(
    graph: InteractionOperationGraph,
    fixture: NativeCodexBehaviorFixture,
    id: Long,
): COpaquePointer {
    fixture.request(id, ELICITATION_METHOD, urlElicitation(id))
    return awaitExistingElicitation(graph, id.toString())
}

private suspend fun MemScope.awaitFormElicitation(
    graph: InteractionOperationGraph,
    fixture: NativeCodexBehaviorFixture,
    id: Long,
): COpaquePointer {
    fixture.request(id, ELICITATION_METHOD, formElicitation(id))
    return awaitExistingElicitation(graph, id.toString())
}

private suspend fun MemScope.awaitExistingElicitation(
    graph: InteractionOperationGraph,
    requestId: String,
): COpaquePointer = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    while (true) {
        val snapshot = emptyInteractionOperationSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, snapshot.ptr),
        )
        val count = alloc<ULongVar>()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInteractionsElicitationsCount(graph.context, snapshot.value, count.ptr),
        )
        repeat(count.value.toInt()) { index ->
            val elicitation = emptyInteractionOperationSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionsElicitationsAt(
                    graph.context,
                    snapshot.value,
                    index.toULong(),
                    elicitation.ptr,
                ),
            )
            if (copyInteractionOperationString(
                    graph.context,
                    elicitation.value,
                    ::codexAgentPendingElicitationRequestIdCopy,
                ) == requestId
            ) {
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
                return@withTimeout assertNotNull(elicitation.value)
            }
            destroyPendingElicitation(graph.context, elicitation)
        }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
        yield()
    }
    error("unreachable")
}

private fun MemScope.interactionState(graph: InteractionOperationGraph): COpaquePointerVar =
    emptyInteractionOperationSlot().also {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInteractionsStateGet(graph.context, graph.interactions.value, it.ptr),
        )
    }

private suspend fun MemScope.awaitResolvingState(
    graph: InteractionOperationGraph,
    requestId: String,
): COpaquePointer = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    while (true) {
        val state = interactionState(graph)
        if (interactionStateContains(graph.context, state.value, requestId)) {
            return@withTimeout assertNotNull(state.value)
        }
        destroyInteractionState(graph.context, state)
        yield()
    }
    error("unreachable")
}

private suspend fun MemScope.awaitNotResolvingState(
    graph: InteractionOperationGraph,
    requestId: String,
): COpaquePointer = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    while (true) {
        val state = interactionState(graph)
        if (!interactionStateContains(graph.context, state.value, requestId)) {
            return@withTimeout assertNotNull(state.value)
        }
        destroyInteractionState(graph.context, state)
        yield()
    }
    error("unreachable")
}

private fun MemScope.interactionStateContains(
    context: COpaquePointer,
    state: COpaquePointer?,
    requestId: String,
): Boolean {
    val contains = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionStateResolvingRequestIdsContains(
            context,
            state,
            interactionOperationUtf8(requestId),
            contains.ptr,
        ),
    )
    return contains.value == 1
}

private fun MemScope.pendingInteractionFromApproval(
    context: COpaquePointer,
    approval: COpaquePointer?,
): COpaquePointerVar = emptyInteractionOperationSlot().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionFromApproval(context, approval, it.ptr),
    )
}

private fun MemScope.pendingInteractionFromElicitation(
    context: COpaquePointer,
    elicitation: COpaquePointer?,
): COpaquePointerVar = emptyInteractionOperationSlot().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionFromElicitation(context, elicitation, it.ptr),
    )
}

private fun MemScope.copiedInteractionState(
    context: COpaquePointer,
    liveInteraction: COpaquePointer?,
    requestId: String,
): CopiedInteractionState {
    val pending = allocArray<COpaquePointerVar>(1).also { it[0] = liveInteraction }
    val resolving = allocArray<codex_agent_string_view>(1).also {
        writeInteractionOperationUtf8(it[0], requestId)
    }
    val state = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionStateCreate(
            context,
            pending,
            1uL,
            resolving,
            1uL,
            0,
            null,
            state.ptr,
        ),
    )
    val interaction = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionStatePendingAt(context, state.value, 0uL, interaction.ptr),
    )
    return CopiedInteractionState(state, interaction)
}

private fun MemScope.copiedApproval(
    context: COpaquePointer,
    approval: COpaquePointer?,
): COpaquePointerVar {
    val live = pendingInteractionFromApproval(context, approval)
    val copied = copiedInteractionState(context, live.value, "copied")
    val result = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionApproval(context, copied.interaction.value, result.ptr),
    )
    destroyPendingInteraction(context, live)
    destroyPendingInteraction(context, copied.interaction)
    destroyInteractionState(context, copied.state)
    return result
}

private fun MemScope.copiedElicitation(
    context: COpaquePointer,
    elicitation: COpaquePointer?,
): COpaquePointerVar {
    val live = pendingInteractionFromElicitation(context, elicitation)
    val copied = copiedInteractionState(context, live.value, "copied")
    val result = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionElicitation(context, copied.interaction.value, result.ptr),
    )
    destroyPendingInteraction(context, live)
    destroyPendingInteraction(context, copied.interaction)
    destroyInteractionState(context, copied.state)
    return result
}

private fun MemScope.validElicitationResponse(context: COpaquePointer): COpaquePointerVar {
    val selected = allocArray<codex_agent_string_view>(1).also {
        writeInteractionOperationUtf8(it[0], "one")
    }
    val list = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormTextListValueCreate(context, selected, 1uL, list.ptr),
    )
    val value = emptyInteractionOperationSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueFromTextList(context, list.value, value.ptr))
    val keys = allocArray<codex_agent_string_view>(1).also {
        writeInteractionOperationUtf8(it[0], "choices")
    }
    val values = allocArray<COpaquePointerVar>(1).also { it[0] = value.value }
    val response = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationResponseCreate(context, ELICITATION_ACCEPT, keys, values, 1uL, response.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, value.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, list.ptr))
    return response
}

private fun MemScope.declineElicitationResponse(context: COpaquePointer): COpaquePointerVar =
    emptyInteractionOperationSlot().also {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentElicitationResponseCreate(context, ELICITATION_DECLINE, null, null, 0uL, it.ptr),
        )
    }

private fun MemScope.emptyAcceptElicitationResponse(context: COpaquePointer): COpaquePointerVar =
    emptyInteractionOperationSlot().also {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentElicitationResponseCreate(context, ELICITATION_ACCEPT, null, null, 0uL, it.ptr),
        )
    }

private fun MemScope.launchApprovalForResolving(
    graph: InteractionOperationGraph,
    approval: COpaquePointer?,
): COpaquePointerVar = emptyInteractionOperationSlot().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsResolveApproval(
            graph.context,
            graph.interactions.value,
            approval,
            APPROVAL_ACCEPT,
            null,
            null,
            it.ptr,
        ),
    )
}

private suspend fun receiveInteractionOperationCallback(
    observer: InteractionOperationObserver,
    context: COpaquePointer,
    operation: COpaquePointer?,
): InteractionOperationEvent = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    observer.events.receive().also {
        assertEquals(context, it.context)
        assertEquals(operation, it.operation)
        assertEquals(operation, it.publishedOperation)
        assertEquals(observer.userData, it.userData)
    }
}

private suspend fun awaitInteractionOperationResult(
    context: COpaquePointer,
    operation: COpaquePointer?,
): Int = withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
    memScoped {
        val result = alloc<IntVar>()
        while (true) {
            when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                else -> error("operation result failed with $status")
            }
        }
        error("unreachable")
    }
}

private suspend fun destroyInteractionOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
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

private fun MemScope.approvalCount(graph: InteractionOperationGraph): ULong {
    val snapshot = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsApprovalsGet(graph.context, graph.interactions.value, snapshot.ptr),
    )
    val count = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsApprovalsCount(graph.context, snapshot.value, count.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
    return count.value
}

private fun MemScope.elicitationCount(graph: InteractionOperationGraph): ULong {
    val snapshot = emptyInteractionOperationSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsElicitationsGet(graph.context, graph.interactions.value, snapshot.ptr),
    )
    val count = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionsElicitationsCount(graph.context, snapshot.value, count.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, snapshot.ptr))
    return count.value
}

private suspend fun MemScope.awaitNoElicitations(graph: InteractionOperationGraph) {
    withTimeout(INTERACTION_OPERATION_TIMEOUT_MILLIS) {
        while (elicitationCount(graph) != 0uL) yield()
    }
}

private fun destroyInteractionState(context: COpaquePointer, state: COpaquePointerVar) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateDestroy(context, state.ptr))
    assertNull(state.value)
}

private fun destroyPendingInteraction(context: COpaquePointer, interaction: COpaquePointerVar) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, interaction.ptr))
    assertNull(interaction.value)
}

private fun destroyPendingApproval(context: COpaquePointer, approval: COpaquePointerVar) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingApprovalDestroy(context, approval.ptr))
    assertNull(approval.value)
}

private fun destroyPendingElicitation(context: COpaquePointer, elicitation: COpaquePointerVar) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingElicitationDestroy(context, elicitation.ptr))
    assertNull(elicitation.value)
}

private fun destroyElicitationResponse(context: COpaquePointer, response: COpaquePointerVar) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseDestroy(context, response.ptr))
    assertNull(response.value)
}

private fun MemScope.copyInteractionOperationString(
    context: COpaquePointer,
    handle: COpaquePointer?,
    copy: (COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?) -> Int,
): String {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    val bytes = allocArray<UByteVar>(required.value.toInt())
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, bytes, required.value, required.ptr))
    return ByteArray(required.value.toInt()) { bytes[it].toByte() }.decodeToString()
}

private fun MemScope.emptyInteractionOperationSlot(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.interactionOperationUtf8(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { writeInteractionOperationUtf8(it, value) }.ptr

private fun MemScope.writeInteractionOperationUtf8(target: codex_agent_string_view, value: String) {
    val bytes = value.encodeToByteArray()
    target.size = bytes.size.toULong()
    target.data = if (bytes.isEmpty()) null else allocArray<UByteVar>(bytes.size).also { buffer ->
        bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    }
}

private fun approvalRequest(): JsonObject = buildJsonObject {
    put("itemId", "native-item")
    put("startedAtMs", 1)
    put("threadId", "native-thread")
    put("turnId", "native-turn")
    put("command", "git status")
    put("reason", "Inspect the workspace")
}

private fun urlElicitation(id: Long): JsonObject = buildJsonObject {
    put("serverName", "native")
    put("threadId", "native-thread")
    put("elicitationId", "native-elicitation-$id")
    put("message", "Sign in")
    put("url", AUTHORIZATION_URL)
    put("turnId", "native-turn")
    put("mode", "url")
}

private fun formElicitation(id: Long): JsonObject = buildJsonObject {
    put("serverName", "native")
    put("threadId", "native-thread")
    put("elicitationId", "native-elicitation-$id")
    put("message", "Choose")
    put("turnId", "native-turn")
    put("mode", "form")
    putJsonObject("requestedSchema") {
        put("type", "object")
        putJsonArray("required") { add(JsonPrimitive("choices")) }
        putJsonObject("properties") {
            putJsonObject("choices") {
                put("type", "array")
                putJsonObject("items") {
                    putJsonArray("enum") {
                        add(JsonPrimitive("one"))
                        add(JsonPrimitive("two"))
                    }
                }
            }
        }
    }
}

private const val APPROVAL_METHOD = "item/commandExecution/requestApproval"
private const val ELICITATION_METHOD = "mcpServer/elicitation/request"
private const val AUTHORIZATION_URL = "https://accounts.example.com/authorize"
private const val APPROVAL_ACCEPT = 0
private const val APPROVAL_DECLINE = 1
private const val ELICITATION_ACCEPT = 0
private const val ELICITATION_DECLINE = 1
private const val INTERACTION_OPERATION_TIMEOUT_MILLIS = 10_000L
