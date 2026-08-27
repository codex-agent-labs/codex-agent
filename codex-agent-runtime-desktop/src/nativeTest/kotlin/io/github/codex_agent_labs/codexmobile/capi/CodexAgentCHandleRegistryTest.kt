@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import kotlin.concurrent.atomics.AtomicBoolean
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.alloc
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking

class CodexAgentCHandleRegistryTest {
    @Test
    fun rejectsUnknownWrongContextAndWrongTypeWithoutDereferencingPointers(): Unit = runBlocking {
        memScoped {
            val registry = CodexAgentCHandleRegistry()
        val firstContext = registry.createContext().requiredValue()
        val secondContext = registry.createContext().requiredValue()
        val host = registry.createEntry(
            firstContext,
            CodexAgentCHandleKind.HOST,
            "host",
        ).requiredValue()
        val unknown = alloc<ByteVar>().ptr

        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            registry.acquire(null, host, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(unknown, host, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(firstContext, unknown, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            registry.acquire(secondContext, host, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            registry.acquire(firstContext, host, CodexAgentCHandleKind.AGENT).status,
        )
        val failedRetain = registry.retain(
            firstContext,
            unknown,
            CodexAgentCHandleKind.HOST,
        )
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, failedRetain.status)
        assertNull(failedRetain.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            registry.release(secondContext, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            registry.release(firstContext, host, CodexAgentCHandleKind.AGENT),
        )
        registry.acquire(firstContext, host, CodexAgentCHandleKind.HOST).requiredValue().also {
            assertEquals("host", it.payload)
            assertEquals(CODEX_AGENT_STATUS_OK, it.close())
        }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(firstContext, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )

            assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(firstContext))
            assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(secondContext))
        }
    }

    @Test
    fun retainCreatesDistinctTokensAndDestroyReleasesOnlyThatAlias(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val original = registry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            "host",
        ).requiredValue()
        val alias = registry.retain(
            context,
            original,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        assertTrue(original != alias)

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, original, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, original, CodexAgentCHandleKind.HOST).status,
        )
        registry.acquire(context, alias, CodexAgentCHandleKind.HOST).requiredValue().also { lease ->
            assertEquals("host", lease.payload)
            assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        }

        assertEquals(
            CODEX_AGENT_STATUS_INTERNAL_ERROR,
            registry.semanticClose(context, alias, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_INTERNAL_ERROR
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_INTERNAL_ERROR,
            registry.semanticClose(context, alias, CodexAgentCHandleKind.HOST) {
                error("completed close must be replayed")
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, alias, CodexAgentCHandleKind.HOST),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun parentGenerationInvalidatesChildrenAndGrandchildren(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val host = registry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            "host",
        ).requiredValue()
        val agent = registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        val conversation = registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATION,
            "conversation",
            agent,
            CodexAgentCHandleKind.AGENT,
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, agent, CodexAgentCHandleKind.AGENT).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, conversation, CodexAgentCHandleKind.CONVERSATION).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, agent, CodexAgentCHandleKind.AGENT),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, conversation, CodexAgentCHandleKind.CONVERSATION),
        )

        val replacement = registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "replacement",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, replacement, CodexAgentCHandleKind.AGENT).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_CLOSED,
            registry.acquire(context, host, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, replacement, CodexAgentCHandleKind.AGENT),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun concurrentCloseHasOneOwnerAndReplaysItsStatus(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.OPERATION,
            "operation",
        ).requiredValue()
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()

        val owner = async(Dispatchers.Default) {
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                entered.complete(Unit)
                release.await()
                CODEX_AGENT_STATUS_CANCELLED
            }
        }
        entered.await()
        val contender = async(Dispatchers.Default) {
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                error("a concurrent close cannot acquire ownership")
            }
        }
        assertEquals(CODEX_AGENT_STATUS_BUSY, contender.await())
        release.complete(Unit)
        assertEquals(CODEX_AGENT_STATUS_CANCELLED, owner.await())
        assertEquals(
            CODEX_AGENT_STATUS_CANCELLED,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                error("the recorded close result must be replayed")
            },
        )

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, handle, CodexAgentCHandleKind.OPERATION),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun closeBodyCanReenterRegistryWithoutDeadlocking(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.SUBSCRIPTION,
            "subscription",
        ).requiredValue()
        val alias = registry.retain(
            context,
            handle,
            CodexAgentCHandleKind.SUBSCRIPTION,
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.SUBSCRIPTION) {
                assertEquals(
                    CODEX_AGENT_STATUS_BUSY,
                    registry.semanticClose(context, alias, CodexAgentCHandleKind.SUBSCRIPTION) {
                        error("reentrant close cannot own the same transition")
                    },
                )
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, alias, CodexAgentCHandleKind.SUBSCRIPTION) {
                error("the alias must replay the completed close")
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, alias, CodexAgentCHandleKind.SUBSCRIPTION),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, handle, CodexAgentCHandleKind.SUBSCRIPTION),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun closeAndInvalidationWaitForSelfAndDescendantLeases(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val host = registry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            "host",
        ).requiredValue()
        val agent = registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()

        val hostLease = registry.acquire(context, host, CodexAgentCHandleKind.HOST).requiredValue()
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                error("a self lease must block close")
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, hostLease.close())

        val childLease = registry.acquire(context, agent, CodexAgentCHandleKind.AGENT).requiredValue()
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                error("a descendant lease must block close")
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, childLease.close())
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, agent, CodexAgentCHandleKind.AGENT).status,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun contextRefusesOpenSemanticResourceWithoutBlockingItsClose(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val host = registry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            "host",
        ).requiredValue()

        assertEquals(CODEX_AGENT_STATUS_BUSY, registry.destroyContext(context))
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.release(context, host, CodexAgentCHandleKind.HOST),
        )
        registry.acquire(context, host, CodexAgentCHandleKind.HOST).requiredValue().also {
            assertEquals("host", it.payload)
            assertEquals(CODEX_AGENT_STATUS_OK, it.close())
        }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun cancellationCannotInterruptCloseCleanup(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.OPERATION,
            "operation",
        ).requiredValue()
        val entered = CompletableDeferred<Unit>()
        val continueCleanup = CompletableDeferred<Unit>()
        val cleanupCompleted = AtomicBoolean(false)

        val owner = launch(Dispatchers.Default) {
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                entered.complete(Unit)
                continueCleanup.await()
                cleanupCompleted.store(true)
                CODEX_AGENT_STATUS_OK
            }
        }
        entered.await()
        owner.cancel()
        continueCleanup.complete(Unit)
        owner.join()

        assertTrue(cleanupCompleted.load())
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                error("completed cleanup must be replayed")
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun completedCloseCanBeHelpedAfterFinalizationFailure(): Unit = runBlocking {
        val failFinalization = AtomicBoolean(true)
        val effects = AtomicInt(0)
        val registry = CodexAgentCHandleRegistry(
            beforeCloseFinalize = {
                if (failFinalization.compareAndSet(true, false)) throw OutOfMemoryError()
            },
        )
        val context = registry.createContext().requiredValue()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.OPERATION,
            "operation",
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OUT_OF_MEMORY,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                effects.addAndFetch(1)
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.OPERATION) {
                error("the completed effect cannot run twice")
            },
        )
        assertEquals(1, effects.load())
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun teardownHelpSurvivesExactContextPointerReuse(): Unit = runBlocking {
        memScoped {
            val contextMarker = alloc<ByteVar>().ptr
            val handleMarker = alloc<ByteVar>().ptr
            val markers = listOf(contextMarker, handleMarker, contextMarker)
            var markerIndex = 0
            var originalContext: COpaquePointer? = null
            var replacementContext: COpaquePointer? = null
            lateinit var registry: CodexAgentCHandleRegistry
            registry = CodexAgentCHandleRegistry(
                allocateMarker = { markers[markerIndex++] },
                disposeMarker = {},
                beforeCloseFinalize = {
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        registry.destroyContext(assertNotNull(originalContext)),
                    )
                    replacementContext = registry.createContext().requiredValue()
                },
            )
            originalContext = registry.createContext().requiredValue()
            val handle = registry.createEntry(
                originalContext,
                CodexAgentCHandleKind.OPERATION,
                "operation",
            ).requiredValue()

            assertEquals(
                CODEX_AGENT_STATUS_CANCELLED,
                registry.semanticClose(
                    originalContext,
                    handle,
                    CodexAgentCHandleKind.OPERATION,
                ) { CODEX_AGENT_STATUS_CANCELLED },
            )
            assertEquals(originalContext, replacementContext)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                registry.destroyContext(assertNotNull(replacementContext)),
            )
        }
    }

    @Test
    fun committedReclamationAttemptsEveryDisposerWithoutChangingSuccess() {
        val attempts = mutableListOf<COpaquePointer>()
        val failFirst = AtomicBoolean(true)
        val registry = CodexAgentCHandleRegistry(
            allocateMarker = { StableRef.create(TestMarker()).asCPointer() },
            disposeMarker = { pointer ->
                attempts += pointer
                pointer.asStableRef<TestMarker>().dispose()
                if (failFirst.compareAndSet(true, false)) error("injected disposer failure")
            },
        )
        val context = registry.createContext().requiredValue()
        registry.createEntry(
            context,
            CodexAgentCHandleKind.SNAPSHOT,
            "snapshot",
        ).requiredValue()

        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
        assertEquals(2, attempts.size)
        assertEquals(2, attempts.toSet().size)
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, registry.destroyContext(context))
    }

    @Test
    fun leaseCloseReportsReleasingAndRetriesFailure(): Unit = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val calls = AtomicInt(0)
        val lease = CodexAgentCHandleLease("payload") {
            calls.addAndFetch(1)
            entered.complete(Unit)
            runBlocking { release.await() }
            CODEX_AGENT_STATUS_OK
        }
        val owner = async(Dispatchers.Default) { lease.close() }
        entered.await()
        assertEquals(CODEX_AGENT_STATUS_BUSY, lease.close())
        release.complete(Unit)
        assertEquals(CODEX_AGENT_STATUS_OK, owner.await())
        assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        assertEquals(1, calls.load())

        val retries = AtomicInt(0)
        val retrying = CodexAgentCHandleLease("payload") {
            if (retries.addAndFetch(1) == 1) {
                CODEX_AGENT_STATUS_INTERNAL_ERROR
            } else {
                CODEX_AGENT_STATUS_OK
            }
        }
        assertEquals(CODEX_AGENT_STATUS_INTERNAL_ERROR, retrying.close())
        assertEquals(CODEX_AGENT_STATUS_OK, retrying.close())
        assertEquals(CODEX_AGENT_STATUS_OK, retrying.close())
        assertEquals(2, retries.load())
    }

    @Test
    fun teardownIsBusyUntilLeaseEndsThenReclaimsEveryMarkerExactlyOnce(): Unit = runBlocking {
        val disposed = Channel<COpaquePointer>(Channel.UNLIMITED)
        val registry = CodexAgentCHandleRegistry(
            allocateMarker = { StableRef.create(TestMarker()).asCPointer() },
            disposeMarker = { pointer ->
                pointer.asStableRef<TestMarker>().dispose()
                check(disposed.trySend(pointer).isSuccess)
            },
        )
        val context = registry.createContext().requiredValue()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.SNAPSHOT,
            "snapshot",
        ).requiredValue()
        val tombstone = registry.retain(
            context,
            handle,
            CodexAgentCHandleKind.SNAPSHOT,
        ).requiredValue()
        val lease = registry.acquire(
            context,
            handle,
            CodexAgentCHandleKind.SNAPSHOT,
        ).requiredValue()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, tombstone, CodexAgentCHandleKind.SNAPSHOT),
        )

        val start = CompletableDeferred<Unit>()
        val teardown = async(Dispatchers.Default) {
            start.await()
            registry.destroyContext(context)
        }
        start.complete(Unit)
        assertEquals(CODEX_AGENT_STATUS_BUSY, teardown.await())
        assertTrue(disposed.tryReceive().isFailure)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, handle, CodexAgentCHandleKind.SNAPSHOT).status,
        )
        assertEquals("snapshot", lease.payload)

        assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        assertTrue(disposed.tryReceive().isFailure)
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
        val reclaimed = List(3) { disposed.receive() }
        assertEquals(3, reclaimed.toSet().size)
        assertTrue(disposed.tryReceive().isFailure)
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, registry.destroyContext(context))
        assertTrue(disposed.tryReceive().isFailure)
    }

    @Test
    fun foreignValidationRacingOwnerTeardownNeverDereferencesFreedToken(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val local = registry.createContext().requiredValue()
        repeat(16) {
            val foreign = registry.createContext().requiredValue()
            val handle = registry.createEntry(
                foreign,
                CodexAgentCHandleKind.HOST,
                it,
            ).requiredValue()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                registry.semanticClose(foreign, handle, CodexAgentCHandleKind.HOST) {
                    CODEX_AGENT_STATUS_OK
                },
            )
            val start = CompletableDeferred<Unit>()
            val validation = async(Dispatchers.Default) {
                start.await()
                registry.acquire(local, handle, CodexAgentCHandleKind.HOST)
            }
            val teardown = async(Dispatchers.Default) {
                start.await()
                registry.destroyContext(foreign)
            }
            start.complete(Unit)
            val result = validation.await()
            assertTrue(
                result.status == CODEX_AGENT_STATUS_WRONG_CONTEXT ||
                    result.status == CODEX_AGENT_STATUS_STALE_HANDLE,
            )
            assertNull(result.value)
            assertEquals(CODEX_AGENT_STATUS_OK, teardown.await())
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                registry.acquire(local, handle, CodexAgentCHandleKind.HOST).status,
            )
        }
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(local))
    }
}

private class TestMarker

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}
