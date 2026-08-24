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
    @CoversApi(
        "api-v1:AgentApprovalDecision#enum-entry:ACCEPT#sha256:c6613f75901ffd0146f3c8f945f73fabdc67efb237d52809c8a1e062835dc868",
        "api-v1:AgentInteractionState#function:pendingFor#sha256:08307041ebff699e5ae22007d411599025c4275ecd7ba025cfa31ee522e269b4",
        "api-v1:AgentInteractionState#property:failure#sha256:7080551831f3c3b2368a281750ad45912cbb4b25f81036210b69a4045aa1fcb8",
        "api-v1:AgentInteractionState#property:pending#sha256:10fbf36988a81d4af15d4838836e5eb81e416af5857feb53b3da1489870f08b1",
        "api-v1:AgentPendingApproval#constructor:<init>#sha256:d36d1c527facbf77aef6ab0428e6f7777d6d05c5c96330417dd2a6956184fb57",
        "api-v1:AgentPendingApproval#property:conversationId#sha256:887bfbda3318ffd52e5dcf35b99fbf8ea38f0bd452c7d47998b29f21cc894115",
        "api-v1:AgentPendingApproval#property:details#sha256:44ea68a0bf7feab1522ed42d43fb45ed6ac17cf2aa9993b17b8eed70314e79ae",
        "api-v1:AgentPendingApproval#property:requestId#sha256:fd0c32a7d1e38b0654696c08bcf2265a592d5ef67d744d6e0c8498bec84d5788",
        "api-v1:AgentPendingElicitation#constructor:<init>#sha256:7321ecbedd6ed0aecb6b866a116d05d21590b1bc5e57486a0e76b2d441d5a374",
        "api-v1:AgentPendingElicitation#property:conversationId#sha256:7949bbe281579a5a7997d366d50f5553bf648b72aa836562fe8720d8f23ca3ec",
        "api-v1:AgentPendingElicitation#property:elicitation#sha256:157dddfc7f6cb679afe7cd4d0cfa3f88429775c99e5b5db9c5dcb930279cde25",
        "api-v1:AgentPendingElicitation#property:requestId#sha256:96ac11f269d0cb2c513b838a8fdad948e4c988d542ad63f8c554e55232fb32a4",
        "api-v1:AgentPendingInteraction#property:conversationId#sha256:2169271cd2b78533552e14cfc6d811f99921d4ba0e0a471628d69c8386aaf1b4",
        "api-v1:AgentPendingInteraction#property:requestId#sha256:76afd10111bafff507f9198b8a047cc1ca09559084d29e01fd7d4859dd4a8acf",
        "api-v1:CodexInteractions#function:openUrl#sha256:14ac0e7cc6c67c15dc676e0009de45616b44950f3090357adbb72307ae23be5c",
        "api-v1:CodexInteractions#function:resolve#sha256:e3b367ed45c3a07f913b1c9d44d92e9ce90fac35794a04941d2ab4b07fbcec56",
        "api-v1:CodexInteractions#function:resolve#sha256:cd22511653ca191997ed753c35699e2dbf6b31d32a27519bde1bec64c6789559",
        "api-v1:CodexInteractions#property:approvals#sha256:5010b605e9dae5c13177ac80ad2d8925c94022f76b57c52aa7ac35d7842ca6da",
        "api-v1:CodexInteractions#property:elicitations#sha256:d25818743ec91e05a7fc781ed39ed2ba9a0a4da675f0447c76bd76d4a415f63f",
        "api-v1:CodexInteractions#property:state#sha256:ee707951ac40aa02c7cf0720ee2171cfcf0d31c847cb46e0c537e4600821c004",
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
        "api-v1:AgentInteractionState#property:resolvingRequestIds#sha256:654e56f37a63fbcd185e5f33d03bbe939c47a5a4d743acb0b2dac67a3faa43a5",
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
        "api-v1:AgentInteractionState#constructor:<init>#sha256:2f20415a7cd63439aa6fdb6a8f0a9a0377383530651884faf19da842eb3a9471",
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
