package io.github.codex_agent_labs.codexmobile.agent.runtime

import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNotSame
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import platform.CoreFoundation.CFRunLoopGetMain
import platform.CoreFoundation.CFRunLoopRunInMode
import platform.CoreFoundation.CFRunLoopStop
import platform.CoreFoundation.kCFRunLoopDefaultMode
import platform.Foundation.NSThread

class CodexObjectiveCTest {
    @Test
    fun conversationStatePreservesCanonicalCapabilitiesAndFailure() {
        val state = AgentConversationState(
            status = AgentConversationStatus.FAILED,
            conversationId = ConversationId("thread-1"),
            failure = CodexFailure("turn_failed", "Could not finish turn", true),
        ).toCDXState()

        assertEquals(CDXConversationStatus.FAILED, state.status)
        assertEquals("thread-1", state.conversationId)
        assertEquals("turn_failed", state.failure?.code)
        assertEquals("Could not finish turn", state.failure?.message)
        assertTrue(state.failure?.isRecoverable == true)
        assertTrue(state.canStartTurn)
        assertTrue(state.canReload)
        assertFalse(state.canCancelTurn)
    }

    @Test
    fun everyCanonicalConversationStatusHasAStableFacadeStatus() {
        AgentConversationStatus.entries.forEach { status ->
            val mapped = AgentConversationState(status = status).toCDXState()
            assertEquals(status.name, mapped.status.name)
            assertNull(mapped.failure)
        }
    }

    @Test
    fun identityCachePreservesEveryCanonicalObjectWrapperForTheOwnerLifetime() {
        val cache = CDXIdentityCache<Any, Any>()
        val first = Any()
        val second = Any()

        val firstWrapper = cache.getOrPut(first) { Any() }
        assertSame(firstWrapper, cache.getOrPut(first) { Any() })

        val secondWrapper = cache.getOrPut(second) { Any() }
        assertNotSame(firstWrapper, secondWrapper)
        assertSame(secondWrapper, cache.getOrPut(second) { Any() })
        assertSame(firstWrapper, cache.getOrPut(first) { Any() })
    }

    @Test
    @OptIn(ExperimentalForeignApi::class)
    fun unexpectedOperationFailureDoesNotLeakThrowableDetails() {
        val secret = "secret-" + "x".repeat(1_000)
        val completions = mutableListOf<Pair<CDXOperationResult, Boolean>>()
        CoroutineScope(SupervisorJob() + Dispatchers.Default).operation(
            completion = { completions += it to NSThread.isMainThread },
            block = { error(secret) },
        )

        if (completions.isEmpty()) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 1.0, false)
        val (result, isMainThread) = completions.single()
        val failure = assertNotNull(result.failure)
        assertFalse(result.success)
        assertEquals("operation_failed", failure.code)
        assertEquals("Codex operation failed", failure.message)
        assertFalse(failure.isRecoverable)
        assertFalse(failure.message.contains("secret"))
        assertTrue(isMainThread)
    }

    @Test
    @OptIn(ExperimentalForeignApi::class)
    fun cancellingAnOperationCompletesExactlyOnceOnMain() {
        val completions = mutableListOf<Pair<CDXOperationResult, Boolean>>()
        val operation = CoroutineScope(SupervisorJob() + Dispatchers.Default).operation(
            completion = {
                completions += it to NSThread.isMainThread
                CFRunLoopStop(CFRunLoopGetMain())
            },
            block = { awaitCancellation() },
        )

        operation.cancel()
        operation.cancel()

        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 1.0, false)
        val (result, isMainThread) = completions.single()
        assertFalse(result.success)
        assertEquals("cancelled", result.failure?.code)
        assertTrue(isMainThread)
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, false)
        assertEquals(1, completions.size)
    }
}
