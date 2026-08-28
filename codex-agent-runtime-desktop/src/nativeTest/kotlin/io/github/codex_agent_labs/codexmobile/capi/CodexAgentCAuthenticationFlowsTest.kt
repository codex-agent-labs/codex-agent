@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
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
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

class CodexAgentCAuthenticationFlowsTest {
    @Test
    fun authenticationStateProjectsCurrentTransitionsAndOwnerTerminal(): Unit = runBlocking {
        val fixture = authenticationFlowFixture()
        withAuthenticationFlowGraph(fixture) { graph ->
            val first = emptyAuthenticationFlowSlot()
            val second = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, first.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, second.ptr),
            )
            assertNotEquals(first.value, second.value)
            val current = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateValue(graph.context, first.value, current.ptr),
            )
            assertNotEquals(first.value, current.value)
            assertEquals(AUTHENTICATION_SIGNED_OUT, authenticationFlowStatus(graph.context, current.value))
            destroyAuthenticationFlowState(graph.context, current.ptr)
            destroyAuthenticationFlowSnapshot(graph.context, first.ptr)
            destroyAuthenticationFlowSnapshot(graph.context, second.ptr)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(
                    AUTHENTICATION_SIGNED_OUT,
                    receiveAuthenticationState(graph.context, subscription.value, observer).status,
                )

                launchAuthenticationFlow(graph)
                val authenticating = receiveAuthenticationStateUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.status == AUTHENTICATION_AUTHENTICATING && it.hasPendingUrl }
                assertEquals(0, authenticating.terminal)

                val pendingSnapshot = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateGet(
                        graph.context,
                        graph.authentication.value,
                        pendingSnapshot.ptr,
                    ),
                )
                val pendingState = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateValue(graph.context, pendingSnapshot.value, pendingState.ptr),
                )
                val pendingUrl = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStatePendingSignInUrl(
                        graph.context,
                        pendingState.value,
                        pendingUrl.ptr,
                    ),
                )
                destroyAuthenticationFlowState(graph.context, pendingState.ptr)
                destroyAuthenticationFlowSnapshot(graph.context, pendingSnapshot.ptr)
                val purpose = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthorizationUrlPurpose(graph.context, pendingUrl.value, purpose.ptr),
                )
                assertEquals(0, purpose.value)
                assertEquals(
                    AUTHENTICATION_URL,
                    readAuthenticationFlowUrl(graph.context, assertNotNull(pendingUrl.value)),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(graph.context, pendingUrl.ptr))

                completeAuthenticationFlow(fixture)
                val authenticated = receiveAuthenticationStateUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.status == AUTHENTICATION_AUTHENTICATED }
                assertEquals(0, authenticated.terminal)

                closeAuthenticationFlowHost(graph)
                val terminal = receiveAuthenticationStateUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.terminal == 1 }
                assertEquals(AUTHENTICATION_AUTHENTICATED, terminal.status)
                destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                if (subscription.value != null) destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                observer.dispose()
            }
        }
    }

    @Test
    fun authenticationIsAuthenticatedProjectsCurrentTransitionsAndOwnerTerminal(): Unit = runBlocking {
        val fixture = authenticationFlowFixture()
        withAuthenticationFlowGraph(fixture) { graph ->
            val current = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, graph.authentication.value, current.ptr),
            )
            val value = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentStateBooleanValue(graph.context, current.value, value.ptr),
            )
            assertEquals(0, value.value)
            destroyAuthenticationFlowSnapshot(graph.context, current.ptr)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(false, receiveAuthenticationBoolean(graph.context, subscription.value, observer).value)
                launchAuthenticationFlow(graph)
                val authenticatingStateSnapshot = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateGet(
                        graph.context,
                        graph.authentication.value,
                        authenticatingStateSnapshot.ptr,
                    ),
                )
                val authenticatingState = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateValue(
                        graph.context,
                        authenticatingStateSnapshot.value,
                        authenticatingState.ptr,
                    ),
                )
                assertEquals(
                    AUTHENTICATION_AUTHENTICATING,
                    authenticationFlowStatus(graph.context, authenticatingState.value),
                )
                destroyAuthenticationFlowState(graph.context, authenticatingState.ptr)
                destroyAuthenticationFlowSnapshot(graph.context, authenticatingStateSnapshot.ptr)
                val whileAuthenticating = emptyAuthenticationFlowSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationIsAuthenticatedGet(
                        graph.context,
                        graph.authentication.value,
                        whileAuthenticating.ptr,
                    ),
                )
                val whileAuthenticatingValue = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentStateBooleanValue(
                        graph.context,
                        whileAuthenticating.value,
                        whileAuthenticatingValue.ptr,
                    ),
                )
                assertEquals(0, whileAuthenticatingValue.value)
                destroyAuthenticationFlowSnapshot(graph.context, whileAuthenticating.ptr)
                completeAuthenticationFlow(fixture)
                val authenticated = receiveAuthenticationBooleanUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.value }
                assertEquals(0, authenticated.terminal)

                closeAuthenticationFlowHost(graph)
                val terminal = receiveAuthenticationBooleanUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.terminal == 1 }
                assertTrue(terminal.value)
                destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                if (subscription.value != null) destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                observer.dispose()
            }
        }
    }

    @Test
    fun authenticationIsAuthenticatingProjectsCurrentTransitionsAndOwnerTerminal(): Unit = runBlocking {
        val fixture = authenticationFlowFixture()
        withAuthenticationFlowGraph(fixture) { graph ->
            val current = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, graph.authentication.value, current.ptr),
            )
            val value = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentStateBooleanValue(graph.context, current.value, value.ptr),
            )
            assertEquals(0, value.value)
            destroyAuthenticationFlowSnapshot(graph.context, current.ptr)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertEquals(false, receiveAuthenticationBoolean(graph.context, subscription.value, observer).value)
                launchAuthenticationFlow(graph)
                val authenticating = receiveAuthenticationBooleanUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.value }
                assertEquals(0, authenticating.terminal)

                completeAuthenticationFlow(fixture)
                val completed = receiveAuthenticationBooleanUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { !it.value }
                assertEquals(0, completed.terminal)

                closeAuthenticationFlowHost(graph)
                val terminal = receiveAuthenticationBooleanUntil(
                    graph.context,
                    subscription.value,
                    observer,
                ) { it.terminal == 1 }
                assertEquals(false, terminal.value)
                destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                if (subscription.value != null) destroyAuthenticationFlowSubscription(graph.context, subscription.ptr)
                observer.dispose()
            }
        }
    }

    @Test
    fun authenticationFlowsFailClosedAcrossOutputTypeContextAndStaleBoundaries(): Unit = runBlocking {
        withAuthenticationFlowGraph(authenticationFlowFixture()) { graph ->
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.authentication.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, graph.authentication.value, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, graph.authentication.value, occupied.ptr),
            )
            assertEquals(graph.authentication.value, occupied.value)

            val observer = AuthenticationFlowObserver(occupied.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.authentication.value, occupied.value)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                observer.dispose()
            }

            val state = emptyAuthenticationFlowSlot()
            val boolean = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, state.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, graph.authentication.value, boolean.ptr),
            )
            val booleanSentinel = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentStateBooleanValue(graph.context, state.value, booleanSentinel.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanSentinel.value)
            val stateOutput = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateValue(graph.context, boolean.value, stateOutput.ptr),
            )
            assertNull(stateOutput.value)

            val otherContext = emptyAuthenticationFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            val crossOutput = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationStateGet(otherContext.value, graph.authentication.value, crossOutput.ptr),
            )
            assertNull(crossOutput.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))

            val alias = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRetain(graph.context, graph.authentication.value, alias.ptr),
            )
            val stale = assertNotNull(alias.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationRelease(graph.context, alias.ptr))
            val staleOutput = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, stale, staleOutput.ptr),
            )
            assertNull(staleOutput.value)
            destroyAuthenticationFlowSnapshot(graph.context, state.ptr)
            destroyAuthenticationFlowSnapshot(graph.context, boolean.ptr)
        }
    }

    @Test
    fun authenticationStateFlowFailsClosedPerCapabilityAndProjector(): Unit = runBlocking {
        withAuthenticationFlowGraph(authenticationFlowFixture()) { graph ->
            val snapshot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, snapshot.ptr),
            )

            val output = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateGet(null, graph.authentication.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateGet(graph.context, null, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateGet(graph.context, snapshot.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, null),
            )
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.authentication.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateGet(graph.context, graph.authentication.value, occupied.ptr),
            )
            assertEquals(graph.authentication.value, occupied.value)

            val otherContext = emptyAuthenticationFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationStateGet(otherContext.value, graph.authentication.value, output.ptr),
            )
            assertNull(output.value)

            val staleAuthenticationSlot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRetain(
                    graph.context,
                    graph.authentication.value,
                    staleAuthenticationSlot.ptr,
                ),
            )
            val staleAuthentication = assertNotNull(staleAuthenticationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRelease(graph.context, staleAuthenticationSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationStateGet(graph.context, staleAuthentication, output.ptr),
            )
            assertNull(output.value)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        null,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        null,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        snapshot.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentAuthenticationStateSubscribe(
                        otherContext.value,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        staleAuthentication,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        graph.authentication.value,
                        null,
                        null,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        null,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationStateSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.authentication.value, occupied.value)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                observer.dispose()
            }

            val stateOutput = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateValue(null, snapshot.value, stateOutput.ptr),
            )
            assertNull(stateOutput.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateValue(graph.context, null, stateOutput.ptr),
            )
            assertNull(stateOutput.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateValue(graph.context, graph.authentication.value, stateOutput.ptr),
            )
            assertNull(stateOutput.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationStateValue(otherContext.value, snapshot.value, stateOutput.ptr),
            )
            assertNull(stateOutput.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateValue(graph.context, snapshot.value, null),
            )
            val occupiedStateOutput = alloc<COpaquePointerVar>().also { it.value = graph.authentication.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateValue(graph.context, snapshot.value, occupiedStateOutput.ptr),
            )
            assertEquals(graph.authentication.value, occupiedStateOutput.value)

            val staleSnapshot = assertNotNull(snapshot.value)
            destroyAuthenticationFlowSnapshot(graph.context, snapshot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationStateValue(graph.context, staleSnapshot, stateOutput.ptr),
            )
            assertNull(stateOutput.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
        }
    }

    @Test
    fun authenticationIsAuthenticatedFlowFailsClosedPerCapabilityAndProjector(): Unit = runBlocking {
        withAuthenticationFlowGraph(authenticationFlowFixture()) { graph ->
            val snapshot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationIsAuthenticatedGet(
                    graph.context,
                    graph.authentication.value,
                    snapshot.ptr,
                ),
            )

            val output = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatedGet(null, graph.authentication.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, null, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, snapshot.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, graph.authentication.value, null),
            )
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.authentication.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatedGet(
                    graph.context,
                    graph.authentication.value,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.authentication.value, occupied.value)

            val otherContext = emptyAuthenticationFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationIsAuthenticatedGet(
                    otherContext.value,
                    graph.authentication.value,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val staleAuthenticationSlot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRetain(
                    graph.context,
                    graph.authentication.value,
                    staleAuthenticationSlot.ptr,
                ),
            )
            val staleAuthentication = assertNotNull(staleAuthenticationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRelease(graph.context, staleAuthenticationSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationIsAuthenticatedGet(graph.context, staleAuthentication, output.ptr),
            )
            assertNull(output.value)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        null,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        null,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        snapshot.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        otherContext.value,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        staleAuthentication,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        graph.authentication.value,
                        null,
                        null,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        null,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatedSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.authentication.value, occupied.value)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                observer.dispose()
            }

            val booleanValue = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(null, snapshot.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(graph.context, null, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentStateBooleanValue(graph.context, graph.authentication.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentStateBooleanValue(otherContext.value, snapshot.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(graph.context, snapshot.value, null),
            )

            val staleSnapshot = assertNotNull(snapshot.value)
            destroyAuthenticationFlowSnapshot(graph.context, snapshot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentStateBooleanValue(graph.context, staleSnapshot, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
        }
    }

    @Test
    fun authenticationIsAuthenticatingFlowFailsClosedPerCapabilityAndProjector(): Unit = runBlocking {
        withAuthenticationFlowGraph(authenticationFlowFixture()) { graph ->
            val snapshot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationIsAuthenticatingGet(
                    graph.context,
                    graph.authentication.value,
                    snapshot.ptr,
                ),
            )

            val output = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatingGet(null, graph.authentication.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, null, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, snapshot.value, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, graph.authentication.value, null),
            )
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.authentication.value }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationIsAuthenticatingGet(
                    graph.context,
                    graph.authentication.value,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.authentication.value, occupied.value)

            val otherContext = emptyAuthenticationFlowSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationIsAuthenticatingGet(
                    otherContext.value,
                    graph.authentication.value,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val staleAuthenticationSlot = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRetain(
                    graph.context,
                    graph.authentication.value,
                    staleAuthenticationSlot.ptr,
                ),
            )
            val staleAuthentication = assertNotNull(staleAuthenticationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationRelease(graph.context, staleAuthenticationSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationIsAuthenticatingGet(graph.context, staleAuthentication, output.ptr),
            )
            assertNull(output.value)

            val subscription = emptyAuthenticationFlowSlot()
            val observer = AuthenticationFlowObserver(subscription.ptr)
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        null,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        null,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        snapshot.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        otherContext.value,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_STALE_HANDLE,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        staleAuthentication,
                        authenticationFlowCallback,
                        observer.userData,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        graph.authentication.value,
                        null,
                        null,
                        subscription.ptr,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        null,
                    ),
                )
                assertNull(subscription.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthenticationIsAuthenticatingSubscribe(
                        graph.context,
                        graph.authentication.value,
                        authenticationFlowCallback,
                        observer.userData,
                        occupied.ptr,
                    ),
                )
                assertEquals(graph.authentication.value, occupied.value)
                assertNoAuthenticationFlowEvent(observer)
            } finally {
                observer.dispose()
            }

            val booleanValue = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(null, snapshot.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(graph.context, null, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentStateBooleanValue(graph.context, graph.authentication.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentStateBooleanValue(otherContext.value, snapshot.value, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentStateBooleanValue(graph.context, snapshot.value, null),
            )

            val staleSnapshot = assertNotNull(snapshot.value)
            destroyAuthenticationFlowSnapshot(graph.context, snapshot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentStateBooleanValue(graph.context, staleSnapshot, booleanValue.ptr),
            )
            assertEquals(AUTHENTICATION_SENTINEL, booleanValue.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
        }
    }
}

private data class AuthenticationFlowGraph(
    val contextSlot: COpaquePointerVar,
    val context: COpaquePointer,
    val host: COpaquePointerVar,
    val agent: COpaquePointerVar,
    val authentication: COpaquePointerVar,
    var hostClosed: Boolean = false,
)

private data class AuthenticationFlowEvent(
    val context: COpaquePointer?,
    val subscription: COpaquePointer?,
    val status: Int,
    val snapshot: COpaquePointer?,
    val terminal: Int,
    val publishedSubscription: COpaquePointer?,
)

private data class ObservedAuthenticationState(
    val status: Int,
    val hasPendingUrl: Boolean,
    val terminal: Int,
)

private data class ObservedAuthenticationBoolean(
    val value: Boolean,
    val terminal: Int,
)

private class AuthenticationFlowObserver(
    private val output: CPointer<COpaquePointerVar>,
) {
    val events = Channel<AuthenticationFlowEvent>(Channel.UNLIMITED)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun publishedSubscription(): COpaquePointer? = output.pointed.value
    fun dispose(): Unit = reference.dispose()
}

private val authenticationFlowCallback = staticCFunction {
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        status: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<AuthenticationFlowObserver>().get()
    observer.events.trySend(
        AuthenticationFlowEvent(
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

private fun authenticationFlowFixture(): NativeCodexBehaviorFixture = NativeCodexBehaviorFixture(
    additionalResponse = { method, params ->
        when (method) {
            "account/read" -> buildJsonObject {
                put("account", JsonNull)
                put("requiresOpenaiAuth", true)
            }

            "account/login/start" -> buildJsonObject {
                assertEquals("chatgpt", params.getValue("type").toString().trim('"'))
                put("type", "chatgpt")
                put("loginId", AUTHENTICATION_LOGIN_ID)
                put("authUrl", AUTHENTICATION_URL)
            }

            else -> null
        }
    },
)

private suspend fun withAuthenticationFlowGraph(
    fixture: NativeCodexBehaviorFixture,
    block: suspend MemScope.(AuthenticationFlowGraph) -> Unit,
) {
    memScoped {
        val contextSlot = emptyAuthenticationFlowSlot()
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
        selectAuthenticationFlowWorkspace(context, assertNotNull(host.value), fixture.workspace.path)

        val hostState = emptyAuthenticationFlowSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host.value, hostState.ptr))
        val agent = emptyAuthenticationFlowSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateAgent(context, host.value, hostState.value, agent.ptr))
        destroyAuthenticationFlowSnapshot(context, hostState.ptr)
        val authentication = emptyAuthenticationFlowSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAgentAuthentication(context, agent.value, authentication.ptr),
        )
        val graph = AuthenticationFlowGraph(contextSlot, context, host, agent, authentication)
        try {
            block(graph)
        } finally {
            if (!graph.hostClosed) closeAuthenticationFlowHost(graph)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationRelease(context, authentication.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(context, agent.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, host.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }
}

private suspend fun MemScope.selectAuthenticationFlowWorkspace(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        writeAuthenticationFlowUtf8(it.path, path)
    }
    launchAuthenticationFlowOperation(context) { output ->
        codexAgentHostSelectWorkspace(context, host, selection.ptr, null, null, output)
    }
}

private suspend fun MemScope.launchAuthenticationFlow(graph: AuthenticationFlowGraph) {
    val method = emptyAuthenticationFlowSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationMethodChatGptBrowserCreate(graph.context, method.ptr))
    try {
        launchAuthenticationFlowOperation(graph.context) { output ->
            codexAgentAuthenticationAuthenticateChatGptBrowser(
                graph.context,
                graph.authentication.value,
                method.value,
                null,
                null,
                output,
            )
        }
    } finally {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAuthenticationMethodChatGptBrowserDestroy(graph.context, method.ptr),
        )
    }
}

private suspend fun completeAuthenticationFlow(fixture: NativeCodexBehaviorFixture) {
    fixture.notify(
        "account/login/completed",
        buildJsonObject {
            put("success", true)
            put("loginId", AUTHENTICATION_LOGIN_ID)
        },
    )
}

private suspend fun MemScope.closeAuthenticationFlowHost(graph: AuthenticationFlowGraph) {
    if (graph.hostClosed) return
    launchAuthenticationFlowOperation(graph.context) { output ->
        codexAgentHostClose(graph.context, graph.host.value, null, null, output)
    }
    graph.hostClosed = true
}

private suspend fun MemScope.launchAuthenticationFlowOperation(
    context: COpaquePointer,
    launch: (CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = emptyAuthenticationFlowSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, launch(operation.ptr))
    withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
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
    destroyAuthenticationFlowOperation(context, operation.ptr)
}

private suspend fun receiveAuthenticationState(
    context: COpaquePointer,
    subscription: COpaquePointer?,
    observer: AuthenticationFlowObserver,
): ObservedAuthenticationState {
    val event = receiveAuthenticationFlowEvent(context, subscription, observer)
    val snapshot = assertNotNull(event.snapshot)
    return memScoped {
        val state = emptyAuthenticationFlowSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateValue(context, snapshot, state.ptr))
        val hasPendingUrl = alloc<IntVar>()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentAuthenticationStateHasPendingSignInUrl(context, state.value, hasPendingUrl.ptr),
        )
        if (hasPendingUrl.value == 1) {
            val url = emptyAuthenticationFlowSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStatePendingSignInUrl(context, state.value, url.ptr),
            )
            assertNotNull(url.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, url.ptr))
        }
        val observed = ObservedAuthenticationState(
            authenticationFlowStatus(context, state.value),
            hasPendingUrl.value == 1,
            event.terminal,
        )
        destroyAuthenticationFlowState(context, state.ptr)
        val snapshotSlot = alloc<COpaquePointerVar>().also { it.value = snapshot }
        destroyAuthenticationFlowSnapshot(context, snapshotSlot.ptr)
        observed
    }
}

private suspend fun receiveAuthenticationStateUntil(
    context: COpaquePointer,
    subscription: COpaquePointer?,
    observer: AuthenticationFlowObserver,
    predicate: (ObservedAuthenticationState) -> Boolean,
): ObservedAuthenticationState = withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
    while (true) {
        val observed = receiveAuthenticationState(context, subscription, observer)
        if (predicate(observed)) return@withTimeout observed
    }
    error("unreachable")
}

private suspend fun receiveAuthenticationBoolean(
    context: COpaquePointer,
    subscription: COpaquePointer?,
    observer: AuthenticationFlowObserver,
): ObservedAuthenticationBoolean {
    val event = receiveAuthenticationFlowEvent(context, subscription, observer)
    val snapshot = assertNotNull(event.snapshot)
    return memScoped {
        val output = alloc<IntVar>().also { it.value = AUTHENTICATION_SENTINEL }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentStateBooleanValue(context, snapshot, output.ptr))
        val snapshotSlot = alloc<COpaquePointerVar>().also { it.value = snapshot }
        destroyAuthenticationFlowSnapshot(context, snapshotSlot.ptr)
        ObservedAuthenticationBoolean(output.value == 1, event.terminal)
    }
}

private suspend fun receiveAuthenticationBooleanUntil(
    context: COpaquePointer,
    subscription: COpaquePointer?,
    observer: AuthenticationFlowObserver,
    predicate: (ObservedAuthenticationBoolean) -> Boolean,
): ObservedAuthenticationBoolean = withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
    while (true) {
        val observed = receiveAuthenticationBoolean(context, subscription, observer)
        if (predicate(observed)) return@withTimeout observed
    }
    error("unreachable")
}

private suspend fun receiveAuthenticationFlowEvent(
    context: COpaquePointer,
    subscription: COpaquePointer?,
    observer: AuthenticationFlowObserver,
): AuthenticationFlowEvent = withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
    observer.events.receive().also {
        assertEquals(context, it.context)
        assertEquals(subscription, it.subscription)
        assertEquals(subscription, it.publishedSubscription)
        assertEquals(CODEX_AGENT_STATUS_OK, it.status)
    }
}

private fun MemScope.authenticationFlowStatus(context: COpaquePointer, state: COpaquePointer?): Int {
    val status = alloc<IntVar>()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateStatus(context, state, status.ptr))
    return status.value
}

private suspend fun destroyAuthenticationFlowSubscription(
    context: COpaquePointer,
    subscription: CPointer<COpaquePointerVar>,
) {
    withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
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

private suspend fun destroyAuthenticationFlowOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(AUTHENTICATION_TIMEOUT_MILLIS) {
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

private suspend fun assertNoAuthenticationFlowEvent(observer: AuthenticationFlowObserver) {
    assertNull(withTimeoutOrNull(100L) { observer.events.receive() })
}

private fun destroyAuthenticationFlowSnapshot(context: COpaquePointer, slot: CPointer<COpaquePointerVar>) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot))
    assertNull(slot.pointed.value)
}

private fun destroyAuthenticationFlowState(context: COpaquePointer, slot: CPointer<COpaquePointerVar>) {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateDestroy(context, slot))
    assertNull(slot.pointed.value)
}

private fun MemScope.emptyAuthenticationFlowSlot(): COpaquePointerVar = alloc<COpaquePointerVar>().also {
    it.value = null
}

private fun MemScope.writeAuthenticationFlowUtf8(target: codex_agent_string_view, value: String) {
    val bytes = value.encodeToByteArray()
    target.size = bytes.size.toULong()
    target.data = allocArray<UByteVar>(bytes.size).also { buffer ->
        bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    }
}

private fun MemScope.readAuthenticationFlowUrl(context: COpaquePointer, url: COpaquePointer): String {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        codexAgentAuthorizationUrlValueCopy(context, url, null, 0uL, required.ptr),
    )
    val buffer = allocArray<UByteVar>(required.value.toInt())
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentAuthorizationUrlValueCopy(context, url, buffer, required.value, required.ptr),
    )
    return ByteArray(required.value.toInt()) { buffer[it].toByte() }.decodeToString()
}

private const val AUTHENTICATION_SIGNED_OUT = 0
private const val AUTHENTICATION_AUTHENTICATING = 1
private const val AUTHENTICATION_AUTHENTICATED = 2
private const val AUTHENTICATION_SENTINEL = 73
private const val AUTHENTICATION_LOGIN_ID = "native-authentication-flow"
private const val AUTHENTICATION_URL = "https://auth.openai.com/native-flow"
private const val AUTHENTICATION_TIMEOUT_MILLIS = 10_000L
