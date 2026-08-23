package io.github.codex_agent_labs.codexmobile.agent

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
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

class InteractionControllerTest {
    @Test
    fun publicFacadeProjectsSanitizedApprovalsAndElicitationsAndResolvesThem(): Unit = runBlocking {
        val approvalResponse = CompletableDeferred<Unit>()
        val elicitationResponse = CompletableDeferred<Unit>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                null -> when (message.id) {
                    201L -> approvalResponse.complete(Unit)
                    202L -> elicitationResponse.complete(Unit)
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = CodexAgent(
            workspace = CodexWorkspace("/workspace"),
            workingDirectory = "/workspace",
            features = emptySet(),
            client = client,
            parentScope = this,
            authorizationBrowser = CodexAuthorizationBrowser {
                CodexAuthorizationPresentation {}
            },
        )
        try {
            agent.start()
            client.openConversation(ConversationId("thread-1"))
            process.request(
                201,
                "item/commandExecution/requestApproval",
                approvalRequest("Inspect\u202Ehidden\nworkspace"),
            )
            process.request(202, "mcpServer/elicitation/request", formElicitation())

            val approval = withTimeout(1_000) { agent.interactions.approvals.first { it.size == 1 }.single() }
            val elicitation = withTimeout(1_000) { agent.interactions.elicitations.first { it.size == 1 }.single() }
            assertTrue("\\u{202E}" in approval.details)
            assertTrue("\\u{A}" in approval.details)
            assertTrue('\u202E' !in approval.details && '\n' !in approval.details)

            assertFailsWith<IllegalStateException> {
                agent.interactions.resolve(approval.copy(), AgentApprovalDecision.ACCEPT)
            }
            assertFailsWith<IllegalStateException> {
                agent.interactions.resolve(elicitation.copy(), AgentElicitationResponse.decline())
            }
            assertFailsWith<IllegalStateException> { agent.interactions.openUrl(elicitation.copy()) }

            agent.interactions.resolve(approval, AgentApprovalDecision.ACCEPT)
            agent.interactions.resolve(
                elicitation,
                AgentElicitationResponse(
                    AgentElicitationAction.ACCEPT,
                    mapOf("choices" to AgentFormValue.TextList(listOf("one"))),
                ),
            )
            approvalResponse.await()
            elicitationResponse.await()
            withTimeout(1_000) { agent.interactions.approvals.first { it.isEmpty() } }
            withTimeout(1_000) { agent.interactions.elicitations.first { it.isEmpty() } }
        } finally {
            agent.close()
        }
    }

    @Test
    fun cancelledResolutionCanBeRetried(): Unit = runBlocking {
        val response = CompletableDeferred<JsonObject>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                null -> if (message.id == 105L) {
                    response.complete(message.objectValue.getValue("result").jsonObject)
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val interactions = InteractionController(client, this)
        var clientLockHeld = false
        try {
            client.openConversation(ConversationId("thread-1"))
            process.request(105, "item/commandExecution/requestApproval", approvalRequest())
            val approval = assertIs<AgentPendingApproval>(
                withTimeout(1_000) {
                    interactions.state.first { it.pending.any { pending -> pending.requestId == "105" } }
                }.pending.single(),
            )

            client.stateLock.lock()
            clientLockHeld = true
            val cancelled = async(start = CoroutineStart.UNDISPATCHED) {
                interactions.resolveApproval(approval, AgentApprovalDecision.ACCEPT)
            }
            withTimeout(1_000) { interactions.state.first { "105" in it.resolvingRequestIds } }
            cancelled.cancel()
            assertFailsWith<CancellationException> { cancelled.await() }
            assertTrue("105" !in interactions.state.value.resolvingRequestIds)
            assertTrue(interactions.state.value.pending.any { it.requestId == "105" })

            client.stateLock.unlock()
            clientLockHeld = false
            interactions.resolveApproval(approval, AgentApprovalDecision.ACCEPT)
            assertEquals("accept", response.await().getValue("decision").jsonPrimitive.content)
        } finally {
            if (clientLockHeld) client.stateLock.unlock()
            interactions.close()
            client.close()
        }
    }

    @Test
    fun snapshotsCallerOwnedElicitationCollectionsBeforeResolving(): Unit = runBlocking {
        val wireResponse = CompletableDeferred<JsonObject>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                null -> if (message.id == 104L) {
                    wireResponse.complete(message.objectValue.getValue("result").jsonObject)
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val interactions = InteractionController(client, this)
        var stateLockHeld = false
        try {
            client.openConversation(ConversationId("thread-1"))
            process.request(104, "mcpServer/elicitation/request", formElicitation())
            val elicitation = assertIs<AgentPendingElicitation>(withTimeout(1_000) {
                interactions.state.first { state -> state.pending.any { it.requestId == "104" } }
            }.pending.single())

            val selected = mutableListOf("one")
            val content = mutableMapOf<String, AgentFormValue>(
                "choices" to AgentFormValue.TextList(selected),
            )
            client.stateLock.lock()
            stateLockHeld = true
            val resolution = async(start = CoroutineStart.UNDISPATCHED) {
                interactions.resolveElicitation(
                    elicitation,
                    AgentElicitationResponse(AgentElicitationAction.ACCEPT, content),
                )
            }
            selected += "two"
            content["unknown"] = AgentFormValue.Text("changed")
            client.stateLock.unlock()
            stateLockHeld = false

            resolution.await()
            val encoded = wireResponse.await().getValue("content").jsonObject
            assertEquals(listOf("one"), encoded.getValue("choices").jsonArray.map { it.jsonPrimitive.content })
            assertEquals(setOf("choices"), encoded.keys)
        } finally {
            if (stateLockHeld) client.stateLock.unlock()
            interactions.close()
            client.close()
        }
    }

    @Test
    fun keepsRequestsForEveryObserverAndOwnsResolutionAndBrowserCleanup(): Unit = runBlocking {
        val approvalResponse = CompletableDeferred<JsonObject>()
        val elicitationResponse = CompletableDeferred<JsonObject>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                null -> when (message.id) {
                    101L -> approvalResponse.complete(message.objectValue.getValue("result").jsonObject)
                    102L -> elicitationResponse.complete(message.objectValue.getValue("result").jsonObject)
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        var openedUrl: CodexAuthorizationUrl? = null
        var openedCount = 0
        var closedCount = 0
        val interactions = InteractionController(
            client,
            this,
            CodexAuthorizationBrowser { url ->
                openedUrl = url
                openedCount += 1
                CodexAuthorizationPresentation { closedCount += 1 }
            },
        )
        try {
            client.openConversation(ConversationId("thread-1"))
            yield()

            process.request(101, "item/commandExecution/requestApproval", approvalRequest())
            process.request(102, "mcpServer/elicitation/request", urlElicitation(102))

            val firstObserver = async {
                withTimeout(1_000) { interactions.state.first { it.pending.size == 2 } }
            }
            val secondObserver = async {
                withTimeout(1_000) { interactions.state.first { it.pending.size == 2 } }
            }
            val pending = firstObserver.await().pending
            assertEquals(pending, secondObserver.await().pending)
            val approval = assertIs<AgentPendingApproval>(pending[0])
            val elicitation = assertIs<AgentPendingElicitation>(pending[1])
            assertEquals(pending, interactions.state.value.pending)

            interactions.resolveApproval(approval, AgentApprovalDecision.ACCEPT)
            assertEquals("accept", approvalResponse.await().getValue("decision").jsonPrimitive.content)
            assertFailsWith<IllegalStateException> {
                interactions.resolveApproval(approval, AgentApprovalDecision.ACCEPT)
            }

            interactions.openUrl(elicitation)
            interactions.openUrl(elicitation)
            assertEquals("https://accounts.example.com/authorize", openedUrl?.value)
            assertEquals(2, openedCount)
            assertEquals(1, closedCount)

            interactions.resolveElicitation(
                elicitation,
                AgentElicitationResponse(AgentElicitationAction.ACCEPT),
            )
            assertEquals("accept", elicitationResponse.await().getValue("action").jsonPrimitive.content)
            assertEquals(2, closedCount)
            assertTrue(interactions.state.value.pending.isEmpty())

            process.request(103, "mcpServer/elicitation/request", urlElicitation(103))
            val lastElicitation = assertIs<AgentPendingElicitation>(withTimeout(1_000) {
                interactions.state.first { it.pending.any { pending -> pending.requestId == "103" } }
            }.pending.single())
            interactions.openUrl(lastElicitation)
            client.eventsChannel.send(AgentEvent.TurnCompleted(ConversationId("thread-1")))
            withTimeout(1_000) { interactions.state.first { it.pending.isEmpty() } }
            assertEquals(3, closedCount)
        } finally {
            interactions.close()
            client.close()
        }
    }

    @Test
    fun lateResolutionFailureAfterCloseDoesNotRepublishState(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val interactions = InteractionController(client, this)
        var clientLockHeld = false
        try {
            client.openConversation(ConversationId("thread-1"))
            process.request(106, "item/commandExecution/requestApproval", approvalRequest())
            val approval = assertIs<AgentPendingApproval>(withTimeout(1_000) {
                interactions.approvals.first { it.isNotEmpty() }
            }.single())

            client.stateLock.lock()
            clientLockHeld = true
            val resolution = async(start = CoroutineStart.UNDISPATCHED) {
                runCatching { interactions.resolveApproval(approval, AgentApprovalDecision.ACCEPT) }
            }
            withTimeout(1_000) { interactions.state.first { "106" in it.resolvingRequestIds } }
            interactions.close()
            process.close()
            client.stateLock.unlock()
            clientLockHeld = false

            assertIs<CodexOperationException>(resolution.await().exceptionOrNull())
            assertEquals(AgentInteractionState(), interactions.state.value)
            assertTrue(interactions.approvals.value.isEmpty())
            assertTrue(interactions.elicitations.value.isEmpty())
        } finally {
            if (clientLockHeld) client.stateLock.unlock()
            runCatching { interactions.close() }
            client.close()
        }
    }

    @Test
    fun lateResolutionCompletionAfterDetachDoesNotRemoveReplacementRequest(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/resume" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val interactions = InteractionController(client, this)
        var clientLockHeld = false
        try {
            val firstConversation = ConversationId("thread-1")
            client.openConversation(firstConversation)
            process.request(107, "item/commandExecution/requestApproval", approvalRequest())
            val original = assertIs<AgentPendingApproval>(withTimeout(1_000) {
                interactions.approvals.first { it.isNotEmpty() }
            }.single())

            client.stateLock.lock()
            clientLockHeld = true
            val resolution = async(start = CoroutineStart.UNDISPATCHED) {
                interactions.resolveApproval(original, AgentApprovalDecision.ACCEPT)
            }
            withTimeout(1_000) { interactions.state.first { "107" in it.resolvingRequestIds } }
            interactions.detachConversation(firstConversation)

            val replacementConversation = ConversationId("thread-2")
            client.eventsChannel.send(AgentEvent.ApprovalRequested(
                conversationId = replacementConversation,
                requestId = original.requestId,
                title = "Replacement",
                details = "Replacement details",
            ))
            val replacement = withTimeout(1_000) {
                interactions.approvals.first { it.singleOrNull()?.conversationId == replacementConversation }
            }.single()

            client.stateLock.unlock()
            clientLockHeld = false
            resolution.await()

            assertTrue(interactions.state.value.pending.single() === replacement)
            assertTrue(interactions.state.value.resolvingRequestIds.isEmpty())
            assertEquals(null, interactions.state.value.failure)
        } finally {
            if (clientLockHeld) client.stateLock.unlock()
            interactions.close()
            client.close()
        }
    }
}

private fun approvalRequest(reason: String = "Inspect the workspace") = buildJsonObject {
    put("itemId", "item-1")
    put("startedAtMs", 1)
    put("threadId", "thread-1")
    put("turnId", "turn-1")
    put("command", "git status")
    put("reason", reason)
}

private fun urlElicitation(id: Int) = buildJsonObject {
    put("serverName", "example")
    put("threadId", "thread-1")
    put("elicitationId", "elicitation-$id")
    put("message", "Sign in")
    put("url", "https://accounts.example.com/authorize")
    put("turnId", "turn-1")
    put("mode", "url")
}

private fun formElicitation() = buildJsonObject {
    put("serverName", "example")
    put("threadId", "thread-1")
    put("elicitationId", "elicitation-104")
    put("message", "Choose")
    put("turnId", "turn-1")
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
