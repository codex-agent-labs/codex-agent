@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.runBlocking

class CodexAgentCProjectionRegistryTest {
    @Test
    fun contextPayloadIsReturnedOnlyAfterSuccessfulUnleasedDestroy() {
        val registry = CodexAgentCHandleRegistry()
        val payload = Any()
        val context = registry.createContext(payload).requiredValue()
        val otherContext = registry.createContext().requiredValue()
        val failure = registry.createEntry(
            context,
            CodexAgentCHandleKind.FAILURE,
            "failure",
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            registry.acquire(otherContext, failure, CodexAgentCHandleKind.FAILURE).status,
        )
        val lease = registry.acquireContext(context).requiredValue()
        assertTrue(lease.payload === payload)

        registry.destroyContextWithPayload(context).also { result ->
            assertEquals(CODEX_AGENT_STATUS_BUSY, result.status)
            assertNull(result.payload)
        }
        assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        registry.destroyContextWithPayload(context).also { result ->
            assertEquals(CODEX_AGENT_STATUS_OK, result.status)
            assertTrue(result.payload === payload)
        }
        registry.destroyContextWithPayload(context).also { result ->
            assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, result.status)
            assertNull(result.payload)
        }
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, registry.acquireContext(context).status)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, failure, CodexAgentCHandleKind.FAILURE).status,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(otherContext))
    }

    @Test
    fun closedSemanticPayloadSurvivesUntilItsLeaseAndLastAliasAreReleased(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val payload = Any()
        val handle = registry.createEntry(
            context,
            CodexAgentCHandleKind.HOST,
            payload,
        ).requiredValue()
        val alias = registry.retain(context, handle, CodexAgentCHandleKind.HOST).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, handle, CodexAgentCHandleKind.HOST) { closedPayload ->
                assertTrue(closedPayload === payload)
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.release(context, handle, CodexAgentCHandleKind.HOST))
        assertEquals(CODEX_AGENT_STATUS_CLOSED, registry.acquire(context, alias, CodexAgentCHandleKind.HOST).status)

        val closedLease = registry.acquireIncludingClosed(
            context,
            alias,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        assertTrue(closedLease.payload === payload)
        assertEquals(CODEX_AGENT_STATUS_OK, registry.release(context, alias, CodexAgentCHandleKind.HOST))
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquireIncludingClosed(context, alias, CodexAgentCHandleKind.HOST).status,
        )
        assertEquals(CODEX_AGENT_STATUS_BUSY, registry.destroyContext(context))
        assertTrue(closedLease.payload === payload)
        assertEquals(CODEX_AGENT_STATUS_OK, closedLease.close())
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun failureIsAReleasableImmutableValueAndDoesNotBlockContextDestroy() {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val failure = registry.createEntry(
            context,
            CodexAgentCHandleKind.FAILURE,
            "failure",
        ).requiredValue()
        val alias = registry.retain(context, failure, CodexAgentCHandleKind.FAILURE).requiredValue()

        assertEquals(CODEX_AGENT_STATUS_OK, registry.release(context, failure, CodexAgentCHandleKind.FAILURE))
        registry.acquire(context, alias, CodexAgentCHandleKind.FAILURE).requiredValue().also { lease ->
            assertEquals("failure", lease.payload)
            assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        }
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, alias, CodexAgentCHandleKind.FAILURE).status,
        )
    }

    @Test
    fun conversationsRequireExactTypeContextAndParentGeneration(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val otherContext = registry.createContext().requiredValue()
        val host = registry.createEntry(context, CodexAgentCHandleKind.HOST, "host").requiredValue()
        val agent = registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        val conversations = registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATIONS,
            "conversations",
            agent,
            CodexAgentCHandleKind.AGENT,
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            registry.acquire(context, conversations, CodexAgentCHandleKind.CONVERSATION).status,
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            registry.acquire(otherContext, conversations, CodexAgentCHandleKind.CONVERSATIONS).status,
        )
        registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATIONS,
            "wrong-parent-type",
            agent,
            CodexAgentCHandleKind.HOST,
        ).also { result ->
            assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, result.status)
            assertNull(result.value)
        }

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.invalidateChildren(context, agent, CodexAgentCHandleKind.AGENT),
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, conversations, CodexAgentCHandleKind.CONVERSATIONS).status,
        )
        val replacement = registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATIONS,
            "replacement",
            agent,
            CodexAgentCHandleKind.AGENT,
        ).requiredValue()
        registry.acquire(context, replacement, CodexAgentCHandleKind.CONVERSATIONS).requiredValue().also { lease ->
            assertEquals("replacement", lease.payload)
            assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        }

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) { CODEX_AGENT_STATUS_OK },
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquire(context, replacement, CodexAgentCHandleKind.CONVERSATIONS).status,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(otherContext))
    }

    @Test
    fun hostTransitionLeaseBlocksAgentProjectionUntilTheNewGenerationIsStable(): Unit = runBlocking {
        val registry = CodexAgentCHandleRegistry()
        val context = registry.createContext().requiredValue()
        val host = registry.createEntry(context, CodexAgentCHandleKind.HOST, "host").requiredValue()
        val oldAgent = registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "old-agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        val transition = registry.acquireAndInvalidateChildren(
            context,
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.acquireAndInvalidateChildren(
                context,
                host,
                CodexAgentCHandleKind.HOST,
            ).status,
        )
        val getter = registry.acquire(context, host, CodexAgentCHandleKind.HOST).requiredValue()

        registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "racing-agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).also { result ->
            assertEquals(CODEX_AGENT_STATUS_BUSY, result.status)
            assertNull(result.value)
        }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.retain(context, oldAgent, CodexAgentCHandleKind.AGENT).status,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, getter.close())
        assertEquals(CODEX_AGENT_STATUS_OK, transition.close())
        registry.createEntry(
            context,
            CodexAgentCHandleKind.AGENT,
            "new-agent",
            host,
            CodexAgentCHandleKind.HOST,
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }

    @Test
    fun conversationsTransitionLeaseBlocksConversationProjectionUntilTheNewGenerationIsStable(): Unit =
        runBlocking {
            val registry = CodexAgentCHandleRegistry()
            val context = registry.createContext().requiredValue()
            val host = registry.createEntry(context, CodexAgentCHandleKind.HOST, "host").requiredValue()
            val agent = registry.createEntry(
                context,
                CodexAgentCHandleKind.AGENT,
                "agent",
                host,
                CodexAgentCHandleKind.HOST,
            ).requiredValue()
            val conversations = registry.createEntry(
                context,
                CodexAgentCHandleKind.CONVERSATIONS,
                "conversations",
                agent,
                CodexAgentCHandleKind.AGENT,
            ).requiredValue()
            val oldConversation = registry.createEntry(
                context,
                CodexAgentCHandleKind.CONVERSATION,
                "old-conversation",
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ).requiredValue()
            val transition = registry.acquireAndInvalidateChildren(
                context,
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ).requiredValue()
            assertEquals(
                CODEX_AGENT_STATUS_BUSY,
                registry.acquireAndInvalidateChildren(
                    context,
                    conversations,
                    CodexAgentCHandleKind.CONVERSATIONS,
                ).status,
            )
            val getter = registry.acquire(
                context,
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ).requiredValue()

            registry.createEntry(
                context,
                CodexAgentCHandleKind.CONVERSATION,
                "racing-conversation",
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ).also { result ->
                assertEquals(CODEX_AGENT_STATUS_BUSY, result.status)
                assertNull(result.value)
            }
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                registry.retain(
                    context,
                    oldConversation,
                    CodexAgentCHandleKind.CONVERSATION,
                ).status,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, getter.close())
            assertEquals(CODEX_AGENT_STATUS_OK, transition.close())
            registry.createEntry(
                context,
                CodexAgentCHandleKind.CONVERSATION,
                "new-conversation",
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ).requiredValue()

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                    CODEX_AGENT_STATUS_OK
                },
            )
            assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
        }

    @Test
    fun closeTargetConsumesReleasedConversationAliasAndReplaysStatus(): Unit = runBlocking {
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
        val conversations = registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATIONS,
            "conversations",
            agent,
            CodexAgentCHandleKind.AGENT,
        ).requiredValue()
        val payload = Any()
        val callerAlias = registry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATION,
            payload,
            conversations,
            CodexAgentCHandleKind.CONVERSATIONS,
        ).requiredValue()
        val survivor = registry.retain(
            context,
            callerAlias,
            CodexAgentCHandleKind.CONVERSATION,
        ).requiredValue()
        val closeTarget = registry.acquireIncludingClosed(
            context,
            callerAlias,
            CodexAgentCHandleKind.CONVERSATION,
        ).requiredValue()

        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, callerAlias, CodexAgentCHandleKind.CONVERSATION),
        )
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            registry.acquireIncludingClosed(
                context,
                callerAlias,
                CodexAgentCHandleKind.CONVERSATION,
            ).status,
        )
        registry.acquire(
            context,
            survivor,
            CodexAgentCHandleKind.CONVERSATION,
        ).requiredValue().also { lease ->
            assertTrue(lease.payload === payload)
            assertEquals(CODEX_AGENT_STATUS_OK, lease.close())
        }
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.invalidateChildren(
                context,
                conversations,
                CodexAgentCHandleKind.CONVERSATIONS,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_BUSY,
            registry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST),
        )

        var closeEffects = 0
        assertEquals(
            CODEX_AGENT_STATUS_CANCELLED,
            registry.semanticClose(
                context,
                callerAlias,
                CodexAgentCHandleKind.CONVERSATION,
                closeTarget = closeTarget,
            ) {
                assertTrue(it === payload)
                closeEffects += 1
                CODEX_AGENT_STATUS_CANCELLED
            },
        )
        assertEquals(
            CODEX_AGENT_STATUS_CANCELLED,
            registry.semanticClose(
                context,
                callerAlias,
                CodexAgentCHandleKind.CONVERSATION,
                closeTarget = closeTarget,
            ) {
                error("completed close effect must not replay")
            },
        )
        assertEquals(1, closeEffects)
        assertEquals(
            CODEX_AGENT_STATUS_CLOSED,
            registry.acquire(context, survivor, CodexAgentCHandleKind.CONVERSATION).status,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, closeTarget.close())
        assertEquals(CODEX_AGENT_STATUS_OK, closeTarget.close())
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.invalidateChildren(context, host, CodexAgentCHandleKind.HOST),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.release(context, survivor, CodexAgentCHandleKind.CONVERSATION),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            registry.semanticClose(context, host, CodexAgentCHandleKind.HOST) {
                CODEX_AGENT_STATUS_OK
            },
        )
        assertEquals(CODEX_AGENT_STATUS_OK, registry.destroyContext(context))
    }
}

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}
