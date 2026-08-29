package io.github.codex_agent_labs.codexagent.agent

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
    @CoversApi(
        "api-v1:AgentApprovalDecision#enum-entry:ACCEPT#sha256:cb5db919ac1743570a758b03085e6357f26e451d4d653547e46c29046dfaefa1",
        "api-v1:AgentInteractionState#function:pendingFor#sha256:2bebcaadef437171e1b388d9e511da26ebf3a2b0ac3282fd78d82f052fa7099a",
        "api-v1:AgentInteractionState#property:failure#sha256:064e2aaa74a41e57b21222dca9b44501343efff7943f308ac05a108f2359104f",
        "api-v1:AgentInteractionState#property:pending#sha256:2bb229dd0cad4c8f9fc989139109e7ccf14522500db5f365454ef83a12ba87f5",
        "api-v1:AgentPendingApproval#constructor:<init>#sha256:ea0520159338472abf7d7cc59f82e1fbceb5e52836e973e9f6e1f9c5800ad6b4",
        "api-v1:AgentPendingApproval#property:conversationId#sha256:e671f7ee7aaa440c4a9f89751c846328f7edf6224eebeccc643f08da606bb352",
        "api-v1:AgentPendingApproval#property:details#sha256:29e9aae3364ccbf4b074f8f8bc594e7a9d3df1db4eb0f75a141aec84b203deef",
        "api-v1:AgentPendingApproval#property:requestId#sha256:bec37c4b3a85baf27fa4c472a6413ce724f0d06df51f2f0c57d6f505ed64a1c2",
        "api-v1:AgentPendingElicitation#constructor:<init>#sha256:ef650c2f08192e99dc049f0e76693061de6aa4cddf099c459ab4f7fa004eede1",
        "api-v1:AgentPendingElicitation#property:conversationId#sha256:2a738333591986240b57befad04b197e73372aa3becffab41934e86f6f829de3",
        "api-v1:AgentPendingElicitation#property:elicitation#sha256:b70d2cabcf88919cbdbe37c09ca2ce9384bb04eecb12cb81f4219bd7c9d2ff6f",
        "api-v1:AgentPendingElicitation#property:requestId#sha256:4ff8fb1f80798a3af2d81e2517741f547d0834990625d6f97fefb87d610133f8",
        "api-v1:AgentPendingInteraction#property:conversationId#sha256:f18693ceffdeb8cb2e68e093bb35b397e9aaffe98882cece37b36a4d29bc2a65",
        "api-v1:AgentPendingInteraction#property:requestId#sha256:c332b49f33c4d37434b7a4aa2732435e4a0e40daff7e26f0c6461626a147167b",
        "api-v1:CodexInteractions#function:openUrl#sha256:101b6d9a07b2e95410c7bc59f0a00d2ae7faa25c370dcfbd5a6ecd8928fd1755",
        "api-v1:CodexInteractions#function:resolve#sha256:b4d272cab7027f71eb52bb8a95f274f3bda663e687578c2a290cb10b2caeadb2",
        "api-v1:CodexInteractions#function:resolve#sha256:56fcf044aba04c5b57f26eac71900c1f4cb00252795b4c839dbc5acded32810c",
        "api-v1:CodexInteractions#property:approvals#sha256:57e4029d87038829a2667c4e3fa3a3bf94efa2c3a03fbf82c5b5958023de6e30",
        "api-v1:CodexInteractions#property:elicitations#sha256:f4cbe5203dd56e561e10a9bbc564f3d39d3f9bd4e1f805d6f3dde6bc8e6d2cd9",
        "api-v1:CodexInteractions#property:state#sha256:9c5c9154b79d89263fe7c9b18ea2a06f37a5bf486be3991c9da996deba616cda",
    )
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
            authorizationBrowser = CodexAuthorizationBrowser { error("browser failed") },
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
            assertEquals(
                listOf(approval, elicitation),
                agent.interactions.state.value.pendingFor(ConversationId("thread-1")),
            )
            assertTrue(agent.interactions.state.value.pendingFor(ConversationId("other")).isEmpty())
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

            process.request(203, "mcpServer/elicitation/request", urlElicitation(203))
            val urlElicitation = withTimeout(1_000) {
                agent.interactions.elicitations.first { it.size == 1 }.single()
            }
            val browserFailure = assertFailsWith<CodexOperationException> {
                agent.interactions.openUrl(urlElicitation)
            }
            assertEquals("authorization_browser_failed", browserFailure.failure.code)
            assertEquals(browserFailure.failure, agent.interactions.state.value.failure)
        } finally {
            agent.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentInteractionState#property:resolvingRequestIds#sha256:4a4279b4f2b6da5c0410616302fd36335bba9abc5f161e94d04654612d6a7a24",
    )
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
    @CoversApi(
        "api-v1:AgentInteractionState#constructor:<init>#sha256:16bfd4583234a43416025115d66106cd793a0a2973924ea283d72873032b61f9",
    )
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
