@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_conversation_open_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.ByteVar
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
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

class CodexAgentCLifecycleTest {
    @Test
    fun projectsCanonicalLifecycleAndQuiescesEveryCallback(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        val secondFixture = NativeCodexBehaviorFixture()

        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)

            val throwingSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val throwingObserver = StateObserver(throwingSlot.ptr, throwOnFirst = true)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateSubscribe(
                    context,
                    host,
                    stateCallback,
                    throwingObserver.userData,
                    throwingSlot.ptr,
                ),
            )

            val hostSubscriptionSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val hostObserver = StateObserver(hostSubscriptionSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateSubscribe(
                    context,
                    host,
                    stateCallback,
                    hostObserver.userData,
                    hostSubscriptionSlot.ptr,
                ),
            )

            val cancelledSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val cancelledObserver = StateObserver(cancelledSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateSubscribe(
                    context,
                    host,
                    stateCallback,
                    cancelledObserver.userData,
                    cancelledSlot.ptr,
                ),
            )

            receiveHostState(context, throwingObserver, throwingSlot.value).also {
                assertEquals(HOST_NEW, it.value)
                assertEquals(0, it.terminal)
            }
            receiveHostState(context, hostObserver, hostSubscriptionSlot.value).also {
                assertEquals(HOST_NEW, it.value)
                assertEquals(0, it.terminal)
            }
            receiveHostState(context, cancelledObserver, cancelledSlot.value).also {
                assertEquals(HOST_NEW, it.value)
                assertEquals(0, it.terminal)
            }
            val cancelledHandle = assertNotNull(cancelledSlot.value)
            destroySubscription(context, cancelledSlot.ptr)
            withTimeout(TIMEOUT_MILLIS) { cancelledObserver.events.receive() }.also { event ->
                assertEquals(context, event.context)
                assertEquals(cancelledHandle, event.subscription)
                assertEquals(CODEX_AGENT_STATUS_CANCELLED, event.eventStatus)
                assertNull(event.snapshot)
                assertEquals(1, event.terminal)
                assertEquals(cancelledObserver.userData, event.userData)
                assertEquals(cancelledHandle, event.publishedSubscription)
            }
            assertEquals(2, cancelledObserver.callbacks.load())
            assertNoStateCallback(cancelledObserver)
            destroySubscription(context, throwingSlot.ptr)
            assertEquals(1, throwingObserver.callbacks.load())
            assertNoStateCallback(throwingObserver)
            throwingObserver.dispose()

            selectReady(
                context = context,
                host = host,
                path = fixture.workspace.path,
                reentrantDestroy = true,
            )
            assertEquals(
                listOf(fixture.workspace.path),
                fixture.selectedWorkspaces.map { (it as CodexPathWorkspaceSelection).path },
            )
            assertEquals(listOf(fixture.workspace), fixture.preparedWorkspaces)
            assertTrue(fixture.runtimeStarted)

            var readySeen = false
            while (!readySeen) {
                val state = receiveHostState(context, hostObserver, hostSubscriptionSlot.value)
                assertEquals(0, state.terminal)
                readySeen = state.value == HOST_READY
            }
            assertEquals(2, cancelledObserver.callbacks.load())
            assertNoStateCallback(cancelledObserver)
            cancelledObserver.dispose()

            assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentContextDestroy(contextSlot.ptr))
            assertEquals(context, contextSlot.value)

            val children = readyChildren(context, host)
            val activeSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val activeObserver = StateObserver(activeSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsActiveSubscribe(
                    context,
                    children.conversations,
                    stateCallback,
                    activeObserver.userData,
                    activeSlot.ptr,
                ),
            )
            receiveActive(context, children.conversations, activeObserver, activeSlot.value).also {
                assertNull(it.handle)
                assertEquals(0, it.terminal)
            }

            val defaultOpenSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val defaultConversationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val defaultOpenObserver = OperationObserver(
                outputSlot = defaultOpenSlot.ptr,
                conversations = children.conversations,
                conversationOutput = defaultConversationSlot.ptr,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsOpen(
                    context,
                    children.conversations,
                    null,
                    operationCallback,
                    defaultOpenObserver.userData,
                    defaultOpenSlot.ptr,
                ),
            )
            receiveOperation(defaultOpenObserver, context, defaultOpenSlot.value).also {
                assertEquals(CODEX_AGENT_STATUS_OK, it.projectionStatus)
                assertEquals(defaultConversationSlot.value, it.projectedConversation)
            }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitOperationResult(context, defaultOpenSlot.value),
            )
            val defaultConversation = assertNotNull(defaultConversationSlot.value)
            destroyOperation(context, defaultOpenSlot.ptr)
            assertNoOperationCallback(defaultOpenObserver)
            defaultOpenObserver.dispose()

            fixture.openRequests.single().also { (method, params) ->
                assertEquals("thread/start", method)
                assertEquals("on-request", params["approvalPolicy"]?.jsonPrimitive?.content)
                assertEquals("auto_review", params["approvalsReviewer"]?.jsonPrimitive?.content)
                assertNull(params["serviceTier"])
            }

            val activeDefault = receiveActive(
                context,
                children.conversations,
                activeObserver,
                activeSlot.value,
            ).handle
            assertSameConversation(context, defaultConversation, assertNotNull(activeDefault))

            val conversationSubscriptionSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val conversationObserver = StateObserver(conversationSubscriptionSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationStateSubscribe(
                    context,
                    defaultConversation,
                    stateCallback,
                    conversationObserver.userData,
                    conversationSubscriptionSlot.ptr,
                ),
            )
            receiveConversationState(
                context,
                conversationObserver,
                conversationSubscriptionSlot.value,
            ).also {
                assertEquals(CONVERSATION_READY, it.value)
                assertEquals(0, it.terminal)
            }

            val prompt = alloc<codex_agent_string_view>().also { writeUtf8(it, "native hello") }
            val sendSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSend(
                    context,
                    defaultConversation,
                    prompt.ptr,
                    null,
                    null,
                    sendSlot.ptr,
                ),
            )
            withTimeout(TIMEOUT_MILLIS) { fixture.turnStartObserved.await() }

            val cancelSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationCancelTurn(
                    context,
                    defaultConversation,
                    null,
                    null,
                    cancelSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, cancelSlot.value))
            destroyOperation(context, cancelSlot.ptr)

            var cancellingSeen = false
            while (!cancellingSeen) {
                cancellingSeen = receiveConversationState(
                    context,
                    conversationObserver,
                    conversationSubscriptionSlot.value,
                ).value == CONVERSATION_CANCELLING
            }
            fixture.releaseTurnStart.complete(Unit)
            withTimeout(TIMEOUT_MILLIS) { fixture.interruptObserved.await() }
            assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, sendSlot.value))
            destroyOperation(context, sendSlot.ptr)

            var returnedReady = false
            while (!returnedReady) {
                returnedReady = receiveConversationState(
                    context,
                    conversationObserver,
                    conversationSubscriptionSlot.value,
                ).value == CONVERSATION_READY
            }
            val turnInput = fixture.turnRequests.single().getValue("input").jsonArray
                .single().jsonObject
            assertEquals("text", turnInput["type"]?.jsonPrimitive?.content)
            assertEquals("native hello", turnInput["text"]?.jsonPrimitive?.content)
            assertEquals(1, fixture.interruptRequests.size)

            val explicitOptions = alloc<codex_agent_conversation_open_options>().also { options ->
                options.struct_size = sizeOf<codex_agent_conversation_open_options>().toUInt()
                options.has_conversation_id = 1
                writeUtf8(options.conversation_id, "resumed-native-thread")
                options.has_approval_preset = 1
                options.approval_preset = APPROVAL_ASK_ME
                options.has_service_tier = 1
                writeUtf8(options.service_tier, "fast")
            }
            val explicitOpenSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsOpen(
                    context,
                    children.conversations,
                    explicitOptions.ptr,
                    null,
                    null,
                    explicitOpenSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, explicitOpenSlot.value))
            val explicitConversationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationConversation(
                    context,
                    children.conversations,
                    explicitOpenSlot.value,
                    explicitConversationSlot.ptr,
                ),
            )
            val explicitConversation = assertNotNull(explicitConversationSlot.value)

            var defaultTerminal = false
            while (!defaultTerminal) {
                val state = receiveConversationState(
                    context,
                    conversationObserver,
                    conversationSubscriptionSlot.value,
                )
                defaultTerminal = state.terminal == 1
                if (defaultTerminal) assertEquals(CONVERSATION_CLOSED, state.value)
            }
            destroySubscription(context, conversationSubscriptionSlot.ptr)
            assertNoStateCallback(conversationObserver)
            conversationObserver.dispose()

            fixture.openRequests[1].also { (method, params) ->
                assertEquals("thread/resume", method)
                assertEquals(
                    "resumed-native-thread",
                    params["threadId"]?.jsonPrimitive?.content,
                )
                assertEquals("on-request", params["approvalPolicy"]?.jsonPrimitive?.content)
                assertEquals("user", params["approvalsReviewer"]?.jsonPrimitive?.content)
                assertEquals("fast", params["serviceTier"]?.jsonPrimitive?.content)
            }

            var activeExplicit: COpaquePointer? = null
            while (activeExplicit == null) {
                val event = receiveActive(
                    context,
                    children.conversations,
                    activeObserver,
                    activeSlot.value,
                )
                event.handle?.let { candidate ->
                    if (sameConversation(context, explicitConversation, candidate)) {
                        activeExplicit = candidate
                    } else {
                        releaseConversation(context, candidate)
                    }
                }
            }
            assertSameConversation(context, explicitConversation, assertNotNull(activeExplicit))

            val secondHost = installFixtureHost(context, secondFixture)
            selectReady(context, secondHost, secondFixture.workspace.path)
            val secondChildren = readyChildren(context, secondHost)
            val wrongConversation = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentOperationConversation(
                    context,
                    secondChildren.conversations,
                    explicitOpenSlot.value,
                    wrongConversation.ptr,
                ),
            )
            assertNull(wrongConversation.value)

            val ownedActiveSnapshot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsActiveGet(
                    context,
                    children.conversations,
                    ownedActiveSnapshot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentActiveConversation(
                    context,
                    secondChildren.conversations,
                    ownedActiveSnapshot.value,
                    wrongConversation.ptr,
                ),
            )
            destroySnapshot(context, assertNotNull(ownedActiveSnapshot.value))

            closeHost(context, secondHost)
            releaseConversations(context, secondChildren.conversations)
            releaseAgent(context, secondChildren.agent)
            releaseHost(context, secondHost)
            assertTrue(secondFixture.runtimeClosed)

            destroyOperation(context, explicitOpenSlot.ptr)

            val explicitStateSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val explicitStateObserver = StateObserver(explicitStateSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationStateSubscribe(
                    context,
                    explicitConversation,
                    stateCallback,
                    explicitStateObserver.userData,
                    explicitStateSlot.ptr,
                ),
            )
            receiveConversationState(context, explicitStateObserver, explicitStateSlot.value).also {
                assertEquals(CONVERSATION_READY, it.value)
                assertEquals(0, it.terminal)
            }

            closeConversation(context, explicitConversation)
            var explicitTerminal = false
            while (!explicitTerminal) {
                val state = receiveConversationState(
                    context,
                    explicitStateObserver,
                    explicitStateSlot.value,
                )
                explicitTerminal = state.terminal == 1
                if (explicitTerminal) assertEquals(CONVERSATION_CLOSED, state.value)
            }
            assertConversationState(context, explicitConversation, CONVERSATION_CLOSED)
            destroySubscription(context, explicitStateSlot.ptr)
            assertNoStateCallback(explicitStateObserver)
            explicitStateObserver.dispose()

            closeHost(context, host)
            var hostTerminal = false
            while (!hostTerminal) {
                val state = receiveHostState(context, hostObserver, hostSubscriptionSlot.value)
                hostTerminal = state.terminal == 1
                if (hostTerminal) assertEquals(HOST_CLOSED, state.value)
            }
            var activeTerminal = false
            while (!activeTerminal) {
                val event = receiveRawState(activeObserver, context, activeSlot.value)
                activeTerminal = event.terminal == 1
                destroySnapshot(context, assertNotNull(event.snapshot))
            }
            assertHostState(context, host, HOST_CLOSED)

            destroySubscription(context, hostSubscriptionSlot.ptr)
            destroySubscription(context, activeSlot.ptr)
            assertNoStateCallback(hostObserver)
            assertNoStateCallback(activeObserver)
            hostObserver.dispose()
            activeObserver.dispose()

            releaseConversation(context, defaultConversation)
            releaseConversation(context, assertNotNull(activeDefault))
            releaseConversation(context, explicitConversation)
            releaseConversation(context, assertNotNull(activeExplicit))
            releaseConversations(context, children.conversations)
            releaseAgent(context, children.agent)
            releaseHost(context, host)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
            assertTrue(fixture.runtimeClosed)
        }
    }

    @Test
    fun operationCancelAndConcurrentDestroyQuiesceBeforeSuccess(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)
            selectReady(context, host, fixture.workspace.path)
            val children = readyChildren(context, host)

            val openSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsOpen(
                    context,
                    children.conversations,
                    null,
                    null,
                    null,
                    openSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, openSlot.value))
            val conversationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationConversation(
                    context,
                    children.conversations,
                    openSlot.value,
                    conversationSlot.ptr,
                ),
            )
            val conversation = assertNotNull(conversationSlot.value)
            destroyOperation(context, openSlot.ptr)

            val prompt = alloc<codex_agent_string_view>().also { writeUtf8(it, "cancel me") }
            val sendSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val observer = OperationObserver(sendSlot.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSend(
                    context,
                    conversation,
                    prompt.ptr,
                    operationCallback,
                    observer.userData,
                    sendSlot.ptr,
                ),
            )
            withTimeout(TIMEOUT_MILLIS) { fixture.turnStartObserved.await() }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentOperationCancel(context, sendSlot.value))
            assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentOperationDestroy(context, sendSlot.ptr))
            assertNotNull(sendSlot.value)

            receiveOperation(observer, context, sendSlot.value)
            assertEquals(CODEX_AGENT_STATUS_CANCELLED, awaitOperationResult(context, sendSlot.value))
            destroyOperation(context, sendSlot.ptr)
            assertNull(sendSlot.value)
            assertNoOperationCallback(observer)
            observer.dispose()
            fixture.releaseTurnStart.complete(Unit)

            closeHost(context, host)
            releaseConversation(context, conversation)
            releaseConversations(context, children.conversations)
            releaseAgent(context, children.agent)
            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertTrue(fixture.runtimeClosed)
        }
    }

    @Test
    fun throwingOperationCallbackPreservesResultAndQuiescesOnce(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)
            val selection = alloc<codex_agent_path_workspace_selection>().also {
                it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
                writeUtf8(it.path, fixture.workspace.path)
            }
            val operationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val observer = OperationObserver(
                outputSlot = operationSlot.ptr,
                destroyFromCallback = true,
                throwOnFirst = true,
            )

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostSelectWorkspace(
                    context,
                    host,
                    selection.ptr,
                    operationCallback,
                    observer.userData,
                    operationSlot.ptr,
                ),
            )
            receiveOperation(observer, context, operationSlot.value).also {
                assertEquals(CODEX_AGENT_STATUS_BUSY, it.reentrantDestroyStatus)
            }
            assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, operationSlot.value))
            destroyOperation(context, operationSlot.ptr)
            assertNoOperationCallback(observer)
            assertEquals(1, observer.callbacks.load())
            observer.dispose()

            closeHost(context, host)
            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
            assertTrue(fixture.runtimeClosed)
        }
    }

    @Test
    fun operationTargetLeaseRejectsConflictingOpenUntilCallbackExit(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)
            selectReady(context, host, fixture.workspace.path)
            val children = readyChildren(context, host)

            val firstOperationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val firstConversationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val conflictingOperationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            val observer = OperationObserver(
                outputSlot = firstOperationSlot.ptr,
                conversations = children.conversations,
                conversationOutput = firstConversationSlot.ptr,
                conflictingConversations = children.conversations,
                conflictingOperationOutput = conflictingOperationSlot.ptr,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsOpen(
                    context,
                    children.conversations,
                    null,
                    operationCallback,
                    observer.userData,
                    firstOperationSlot.ptr,
                ),
            )
            receiveOperation(observer, context, firstOperationSlot.value).also {
                assertEquals(CODEX_AGENT_STATUS_OK, it.projectionStatus)
                assertEquals(CODEX_AGENT_STATUS_BUSY, it.conflictingTransitionStatus)
                assertNull(it.conflictingOperation)
            }
            assertNull(conflictingOperationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitOperationResult(context, firstOperationSlot.value),
            )
            val firstConversation = assertNotNull(firstConversationSlot.value)
            destroyOperation(context, firstOperationSlot.ptr)
            assertNoOperationCallback(observer)
            observer.dispose()

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationsOpen(
                    context,
                    children.conversations,
                    null,
                    null,
                    null,
                    conflictingOperationSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitOperationResult(context, conflictingOperationSlot.value),
            )
            val retryConversationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationConversation(
                    context,
                    children.conversations,
                    conflictingOperationSlot.value,
                    retryConversationSlot.ptr,
                ),
            )
            val retryConversation = assertNotNull(retryConversationSlot.value)
            destroyOperation(context, conflictingOperationSlot.ptr)

            closeHost(context, host)
            releaseConversation(context, firstConversation)
            releaseConversation(context, retryConversation)
            releaseConversations(context, children.conversations)
            releaseAgent(context, children.agent)
            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
            assertTrue(fixture.runtimeClosed)
        }
    }

    @Test
    fun projectsStructuredPrepareFailureAndQuiescesFailedHost(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture(
            prepareFailure = IllegalStateException(),
        )
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)
            val selection = alloc<codex_agent_path_workspace_selection>().also {
                it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
                writeUtf8(it.path, fixture.workspace.path)
            }
            val operationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostSelectWorkspace(
                    context,
                    host,
                    selection.ptr,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            val operation = assertNotNull(operationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OPERATION_FAILED,
                awaitOperationResult(context, operation),
            )
            assertEquals(listOf(fixture.workspace), fixture.preparedWorkspaces)
            assertTrue(!fixture.runtimeStarted)

            val operationFailureSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentOperationFailure(context, operation, operationFailureSlot.ptr),
            )
            val operationFailure = assertNotNull(operationFailureSlot.value)
            assertProjectedFailure(context, operationFailure)

            val retainedFailureSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureRetain(context, operationFailure, retainedFailureSlot.ptr),
            )
            val retainedFailure = assertNotNull(retainedFailureSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureRelease(context, operationFailureSlot.ptr),
            )
            assertNull(operationFailureSlot.value)
            assertProjectedFailure(context, retainedFailure)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureRelease(context, retainedFailureSlot.ptr),
            )
            assertNull(retainedFailureSlot.value)

            val snapshotSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateGet(context, host, snapshotSlot.ptr),
            )
            val snapshot = assertNotNull(snapshotSlot.value)
            val kind = alloc<IntVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateKind(context, snapshot, kind.ptr),
            )
            assertEquals(HOST_FAILED, kind.value)
            val hostFailureSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostStateFailure(context, snapshot, hostFailureSlot.ptr),
            )
            assertProjectedFailure(context, assertNotNull(hostFailureSlot.value))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureRelease(context, hostFailureSlot.ptr),
            )
            destroySnapshot(context, snapshot)
            destroyOperation(context, operationSlot.ptr)

            assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentContextDestroy(contextSlot.ptr))
            assertEquals(context, contextSlot.value)
            closeHost(context, host)
            assertHostState(context, host, HOST_CLOSED)
            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }

    @Test
    fun hostCloseOwnsPrivateAliasAfterCallerAliasRelease(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)
            selectReady(context, host, fixture.workspace.path)

            val callerAliasSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostRetain(context, host, callerAliasSlot.ptr),
            )
            val closeOperationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostClose(
                    context,
                    callerAliasSlot.value,
                    null,
                    null,
                    closeOperationSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostRelease(context, callerAliasSlot.ptr),
            )
            assertNull(callerAliasSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitOperationResult(context, closeOperationSlot.value),
            )
            destroyOperation(context, closeOperationSlot.ptr)
            assertHostState(context, host, HOST_CLOSED)
            assertTrue(fixture.runtimeClosed)
            assertEquals(1, fixture.runtimeCloseCalls)

            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }

    @Test
    fun rejectsInvalidSlotsFlagsAndUtf8WithoutMutation(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture()
        memScoped {
            val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
            val context = assertNotNull(contextSlot.value)
            val host = installFixtureHost(context, fixture)

            val operationSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHostSelectWorkspace(
                    context,
                    host,
                    null,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertNull(operationSlot.value)

            val invalidSelection = alloc<codex_agent_path_workspace_selection>().also { selection ->
                selection.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
                writeBytes(selection.path, byteArrayOf(0xc3.toByte(), 0x28))
            }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHostSelectWorkspace(
                    context,
                    host,
                    invalidSelection.ptr,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertNull(operationSlot.value)

            val sentinel = alloc<ByteVar>().ptr
            operationSlot.value = sentinel
            val validSelection = alloc<codex_agent_path_workspace_selection>().also { selection ->
                selection.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
                writeUtf8(selection.path, fixture.workspace.path)
            }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHostSelectWorkspace(
                    context,
                    host,
                    validSelection.ptr,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertEquals(sentinel, operationSlot.value)
            operationSlot.value = null

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHostStateSubscribe(context, host, null, null, operationSlot.ptr),
            )
            assertNull(operationSlot.value)

            val invalidOptions = alloc<codex_agent_conversation_open_options>().also { options ->
                options.struct_size = sizeOf<codex_agent_conversation_open_options>().toUInt()
                options.has_conversation_id = 0
                writeBytes(options.conversation_id, byteArrayOf())
                options.has_approval_preset = 2
                options.approval_preset = 0
                options.has_service_tier = 0
                writeBytes(options.service_tier, byteArrayOf())
            }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationsOpen(
                    context,
                    host,
                    invalidOptions.ptr,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertNull(operationSlot.value)

            val invalidPrompt = alloc<codex_agent_string_view>().also {
                writeBytes(it, byteArrayOf(0xc3.toByte(), 0x28))
            }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSend(
                    context,
                    null,
                    invalidPrompt.ptr,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertNull(operationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSend(
                    context,
                    null,
                    null,
                    null,
                    null,
                    operationSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentOperationResult(context, null, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentOperationDestroy(context, null),
            )

            closeHost(context, host)
            releaseHost(context, host)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }
}

private data class OperationEvent(
    val context: COpaquePointer?,
    val operation: COpaquePointer?,
    val userData: COpaquePointer?,
    val publishedOperation: COpaquePointer?,
    val reentrantDestroyStatus: Int?,
    val projectionStatus: Int?,
    val projectedConversation: COpaquePointer?,
    val conflictingTransitionStatus: Int?,
    val conflictingOperation: COpaquePointer?,
)

private class OperationObserver(
    val outputSlot: CPointer<COpaquePointerVar>,
    val destroyFromCallback: Boolean = false,
    val conversations: COpaquePointer? = null,
    val conversationOutput: CPointer<COpaquePointerVar>? = null,
    val throwOnFirst: Boolean = false,
    val conflictingConversations: COpaquePointer? = null,
    val conflictingOperationOutput: CPointer<COpaquePointerVar>? = null,
) {
    val events = Channel<OperationEvent>(Channel.UNLIMITED)
    val callbacks = AtomicInt(0)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun dispose() = reference.dispose()
}

private data class StateEvent(
    val context: COpaquePointer?,
    val subscription: COpaquePointer?,
    val eventStatus: Int,
    val snapshot: COpaquePointer?,
    val terminal: Int,
    val userData: COpaquePointer?,
    val publishedSubscription: COpaquePointer?,
)

private class StateObserver(
    val outputSlot: CPointer<COpaquePointerVar>,
    val throwOnFirst: Boolean = false,
) {
    val events = Channel<StateEvent>(Channel.UNLIMITED)
    val callbacks = AtomicInt(0)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun dispose() = reference.dispose()
}

private val operationCallback = staticCFunction {
        context: COpaquePointer?,
        operation: COpaquePointer?,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<OperationObserver>().get()
    val invocation = observer.callbacks.addAndFetch(1)
    val projectionStatus = if (observer.conversations != null && observer.conversationOutput != null) {
        codexAgentOperationConversation(
            context,
            observer.conversations,
            operation,
            observer.conversationOutput,
        )
    } else {
        null
    }
    val conflictingTransitionStatus = if (
        observer.conflictingConversations != null && observer.conflictingOperationOutput != null
    ) {
        codexAgentConversationsOpen(
            context,
            observer.conflictingConversations,
            null,
            null,
            null,
            observer.conflictingOperationOutput,
        )
    } else {
        null
    }
    val destroyStatus = if (observer.destroyFromCallback) {
        codexAgentOperationDestroy(context, observer.outputSlot)
    } else {
        null
    }
    observer.events.trySend(
        OperationEvent(
            context = context,
            operation = operation,
            userData = userData,
            publishedOperation = observer.outputSlot.pointed.value,
            reentrantDestroyStatus = destroyStatus,
            projectionStatus = projectionStatus,
            projectedConversation = observer.conversationOutput?.pointed?.value,
            conflictingTransitionStatus = conflictingTransitionStatus,
            conflictingOperation = observer.conflictingOperationOutput?.pointed?.value,
        ),
    )
    if (observer.throwOnFirst && invocation == 1) error("injected operation callback failure")
}

private val stateCallback = staticCFunction {
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        eventStatus: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<StateObserver>().get()
    val invocation = observer.callbacks.addAndFetch(1)
    observer.events.trySend(
        StateEvent(
            context = context,
            subscription = subscription,
            eventStatus = eventStatus,
            snapshot = snapshot,
            terminal = terminal,
            userData = userData,
            publishedSubscription = observer.outputSlot.pointed.value,
        ),
    )
    if (observer.throwOnFirst && invocation == 1) error("injected state callback failure")
}

private data class ObservedState(val value: Int, val terminal: Int)
private data class ObservedActive(val handle: COpaquePointer?, val terminal: Int)
private data class ReadyChildren(val agent: COpaquePointer, val conversations: COpaquePointer)

private suspend fun receiveOperation(
    observer: OperationObserver,
    context: COpaquePointer,
    operation: COpaquePointer?,
): OperationEvent = withTimeout(TIMEOUT_MILLIS) {
    observer.events.receive().also { event ->
        assertEquals(context, event.context)
        assertEquals(operation, event.operation)
        assertEquals(operation, event.publishedOperation)
        assertEquals(observer.userData, event.userData)
    }
}

private suspend fun receiveRawState(
    observer: StateObserver,
    context: COpaquePointer,
    subscription: COpaquePointer?,
): StateEvent = withTimeout(TIMEOUT_MILLIS) {
    observer.events.receive().also { event ->
        assertEquals(context, event.context)
        assertEquals(subscription, event.subscription)
        assertEquals(subscription, event.publishedSubscription)
        assertEquals(observer.userData, event.userData)
        assertEquals(CODEX_AGENT_STATUS_OK, event.eventStatus)
    }
}

private suspend fun receiveHostState(
    context: COpaquePointer,
    observer: StateObserver,
    subscription: COpaquePointer?,
): ObservedState {
    val event = receiveRawState(observer, context, subscription)
    val snapshot = assertNotNull(event.snapshot)
    val kind = memScoped {
        val output = alloc<IntVar>()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateKind(context, snapshot, output.ptr))
        output.value
    }
    destroySnapshot(context, snapshot)
    return ObservedState(kind, event.terminal)
}

private suspend fun receiveConversationState(
    context: COpaquePointer,
    observer: StateObserver,
    subscription: COpaquePointer?,
): ObservedState {
    val event = receiveRawState(observer, context, subscription)
    val snapshot = assertNotNull(event.snapshot)
    val status = memScoped {
        val output = alloc<IntVar>()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateStatus(context, snapshot, output.ptr),
        )
        output.value
    }
    destroySnapshot(context, snapshot)
    return ObservedState(status, event.terminal)
}

private suspend fun receiveActive(
    context: COpaquePointer,
    conversations: COpaquePointer,
    observer: StateObserver,
    subscription: COpaquePointer?,
): ObservedActive {
    val event = receiveRawState(observer, context, subscription)
    val snapshot = assertNotNull(event.snapshot)
    val active = memScoped {
        val output = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentActiveConversation(context, conversations, snapshot, output.ptr),
        )
        output.value
    }
    destroySnapshot(context, snapshot)
    return ObservedActive(active, event.terminal)
}

private suspend fun awaitOperationResult(
    context: COpaquePointer,
    operation: COpaquePointer?,
): Int = withTimeout(TIMEOUT_MILLIS) {
    memScoped {
        val result = alloc<IntVar>()
        var completed: Int? = null
        while (completed == null) {
            when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> completed = result.value
                else -> error("operation result query failed with $status")
            }
        }
        checkNotNull(completed)
    }
}

private suspend fun destroyOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(TIMEOUT_MILLIS) {
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

private suspend fun destroySubscription(
    context: COpaquePointer,
    subscription: CPointer<COpaquePointerVar>,
) {
    withTimeout(TIMEOUT_MILLIS) {
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

private suspend fun assertNoOperationCallback(observer: OperationObserver) {
    assertNull(withTimeoutOrNull(QUIET_MILLIS) { observer.events.receive() })
}

private suspend fun assertNoStateCallback(observer: StateObserver) {
    assertNull(withTimeoutOrNull(QUIET_MILLIS) { observer.events.receive() })
}

private suspend fun MemScope.selectReady(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
    reentrantDestroy: Boolean = false,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        writeUtf8(it.path, path)
    }
    val operation = alloc<COpaquePointerVar>().also { it.value = null }
    val observer = OperationObserver(operation.ptr, destroyFromCallback = reentrantDestroy)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostSelectWorkspace(
            context,
            host,
            selection.ptr,
            operationCallback,
            observer.userData,
            operation.ptr,
        ),
    )
    receiveOperation(observer, context, operation.value).also {
        if (reentrantDestroy) assertEquals(CODEX_AGENT_STATUS_BUSY, it.reentrantDestroyStatus)
    }
    assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, operation.value))
    destroyOperation(context, operation.ptr)
    assertNoOperationCallback(observer)
    observer.dispose()
}

private fun installFixtureHost(
    context: COpaquePointer,
    fixture: NativeCodexBehaviorFixture,
): COpaquePointer {
    val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
    val runtime = contextLease.payload as CodexAgentCContextRuntime
    assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())
    val created = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        CodexAgentCHost(fixture.createHost(), runtime),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    return assertNotNull(created.value)
}

private fun readyChildren(context: COpaquePointer, host: COpaquePointer): ReadyChildren = memScoped {
    val snapshot = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host, snapshot.ptr))
    val agent = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostStateAgent(context, host, snapshot.value, agent.ptr),
    )
    destroySnapshot(context, assertNotNull(snapshot.value))
    val conversations = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentAgentConversations(context, agent.value, conversations.ptr),
    )
    ReadyChildren(assertNotNull(agent.value), assertNotNull(conversations.value))
}

private suspend fun MemScope.closeConversation(
    context: COpaquePointer,
    conversation: COpaquePointer,
) {
    val operation = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationClose(context, conversation, null, null, operation.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, operation.value))
    destroyOperation(context, operation.ptr)
}

private suspend fun MemScope.closeHost(context: COpaquePointer, host: COpaquePointer) {
    val operation = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostClose(context, host, null, null, operation.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, awaitOperationResult(context, operation.value))
    destroyOperation(context, operation.ptr)
}

private fun assertHostState(context: COpaquePointer, host: COpaquePointer, expected: Int) = memScoped {
    val snapshot = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host, snapshot.ptr))
    val kind = alloc<IntVar>()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateKind(context, snapshot.value, kind.ptr))
    assertEquals(expected, kind.value)
    destroySnapshot(context, assertNotNull(snapshot.value))
}

private fun assertConversationState(
    context: COpaquePointer,
    conversation: COpaquePointer,
    expected: Int,
) = memScoped {
    val snapshot = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationStateGet(context, conversation, snapshot.ptr),
    )
    val status = alloc<IntVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationStateStatus(context, snapshot.value, status.ptr),
    )
    assertEquals(expected, status.value)
    destroySnapshot(context, assertNotNull(snapshot.value))
}

private fun assertSameConversation(
    context: COpaquePointer,
    left: COpaquePointer,
    right: COpaquePointer,
) {
    assertTrue(sameConversation(context, left, right))
}

private fun sameConversation(
    context: COpaquePointer,
    left: COpaquePointer,
    right: COpaquePointer,
): Boolean = memScoped {
    val same = alloc<IntVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationIsSame(context, left, right, same.ptr),
    )
    same.value == 1
}

private fun destroySnapshot(context: COpaquePointer, snapshot: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = snapshot }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot.ptr))
    assertNull(slot.value)
}

private fun releaseHost(context: COpaquePointer, host: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = host }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, slot.ptr))
}

private fun releaseAgent(context: COpaquePointer, agent: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = agent }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(context, slot.ptr))
}

private fun releaseConversations(context: COpaquePointer, conversations: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = conversations }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationsRelease(context, slot.ptr))
}

private fun releaseConversation(context: COpaquePointer, conversation: COpaquePointer) = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = conversation }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationRelease(context, slot.ptr))
}

private fun MemScope.assertProjectedFailure(context: COpaquePointer, failure: COpaquePointer) {
    assertFailureString(
        context,
        failure,
        FAILURE_CODE,
        ::codexAgentFailureCodeCopy,
    )
    assertFailureString(
        context,
        failure,
        FAILURE_MESSAGE,
        ::codexAgentFailureMessageCopy,
    )
    val recoverable = alloc<IntVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFailureIsRecoverable(context, failure, recoverable.ptr),
    )
    assertEquals(1, recoverable.value)
}

private fun MemScope.assertFailureString(
    context: COpaquePointer,
    failure: COpaquePointer,
    expected: String,
    copy: FailureStringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, failure, null, 0UL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)

    val buffer = allocArray<UByteVar>(expectedBytes.size)
    repeat(expectedBytes.size) { buffer[it] = BUFFER_SENTINEL }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, failure, buffer, expectedBytes.size.toULong() - 1UL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    repeat(expectedBytes.size) { assertEquals(BUFFER_SENTINEL, buffer[it]) }

    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, failure, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString(),
    )
}

private fun MemScope.writeUtf8(target: codex_agent_string_view, value: String) {
    writeBytes(target, value.encodeToByteArray())
}

private fun MemScope.writeBytes(target: codex_agent_string_view, bytes: ByteArray) {
    target.size = bytes.size.toULong()
    target.data = if (bytes.isEmpty()) {
        null
    } else {
        allocArray<UByteVar>(bytes.size).also { buffer ->
            bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
        }
    }
}

private const val HOST_NEW = 0
private const val HOST_READY = 4
private const val HOST_FAILED = 5
private const val HOST_CLOSED = 6
private const val CONVERSATION_READY = 2
private const val CONVERSATION_CANCELLING = 5
private const val CONVERSATION_CLOSED = 8
private const val APPROVAL_ASK_ME = 2
private const val FAILURE_CODE = "runtime_prepare_failed"
private const val FAILURE_MESSAGE = "Could not prepare Codex"
private val BUFFER_SENTINEL: UByte = 0xa5u
private const val TIMEOUT_MILLIS = 10_000L
private const val QUIET_MILLIS = 50L

private typealias FailureStringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int
