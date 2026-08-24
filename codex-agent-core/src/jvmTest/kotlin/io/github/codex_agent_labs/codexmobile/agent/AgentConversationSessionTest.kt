package io.github.codex_agent_labs.codexmobile.agent

import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonObject

class CodexConversationTest {
    @Test
    @CoversApi(
        "api-v1:CodexConversation#function:close#sha256:1a37318fcc42ec84e867d25ad8c0c7574984d646de86d56b12c9f1724dbc6316",
        "api-v1:CodexConversation#function:send#sha256:aa5276c5df75376bd85e76e9d6e0d22a2686e3750f7846b63b6cb691306ccf0e",
        "api-v1:CodexConversation#function:send#sha256:896de881b2f923b26fb8f174befd7690cb47846843170e0c37c96dc33de5cd53",
        "api-v1:CodexConversation#property:activeTurnProgress#sha256:75e93147db1930bc06dffaf1b7ee4d157e115853b7a14e00539a936e80055695",
        "api-v1:CodexConversation#property:canCancelTurn#sha256:1c626c86d51ddf7156a51094ce474ce34487b79478c2cceff2147cb310f218d1",
        "api-v1:CodexConversation#property:canReload#sha256:c0031a88332b32f3e028ef76ec4c4acfb17de4879768b0ff384fc2127cf4b772",
        "api-v1:CodexConversation#property:canRunShellCommand#sha256:b1b1c85848cf73aae2617974799725889979c8ddf798b3f8b6487500941f22a2",
        "api-v1:CodexConversation#property:canStartTurn#sha256:cc7376e7f1fa5c1522737a090133d87a57f96312e9f45e1294d4fe65ec7749b7",
        "api-v1:CodexConversation#property:currentMessages#sha256:ea176cdb0613f06a181231b4b5c6fe5c74b29aab7fe58a121f09fa3dd2f005a6",
        "api-v1:CodexConversation#property:isTurnActive#sha256:a6ad2c79ebd7df80b68d237ddbe805c5fdd78a41fe484f4d6e11ebd9544c9193",
        "api-v1:CodexConversation#property:state#sha256:b38b7c53bc8b8e6668714295854779949afb3a18710e837ae62e9a0d62ba808f",
    )
    fun exposesCanonicalMessagesTurnProgressAndCapabilitiesAsStateFlows(): Unit = runBlocking {
        val turnCount = AtomicInteger()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                "turn/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-${turnCount.incrementAndGet()}") }
                })
                "thread/read" -> server.respond(message.id, canonicalConversation())
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val conversation = testConversation(client, this)
        try {
            assertFalse(conversation.isTurnActive.value)
            conversation.open()
            assertTrue(conversation.currentMessages.value.isEmpty())
            assertNull(conversation.activeTurnProgress.value)
            assertTrue(conversation.canStartTurn.value)
            assertTrue(conversation.canReload.value)
            assertFalse(conversation.canCancelTurn.value)
            assertTrue(conversation.canRunShellCommand.value)

            conversation.send("hello")
            assertEquals("hello", conversation.currentMessages.value.single().text)
            assertEquals(AgentMessageRole.USER, conversation.currentMessages.value.single().role)
            assertFalse(conversation.canStartTurn.value)
            assertFalse(conversation.canReload.value)
            assertTrue(conversation.canCancelTurn.value)
            assertFalse(conversation.canRunShellCommand.value)
            assertTrue(conversation.isTurnActive.value)

            conversation.process(AgentEvent.TextDelta(ConversationId("thread-1"), "working"))
            assertEquals("working", conversation.activeTurnProgress.value?.text)

            process.notify("turn/completed", completedTurn("turn-1"))
            withTimeout(1_000) {
                conversation.state.first { it.status == AgentConversationStatus.READY }
            }
            assertEquals(
                listOf(AgentMessageRole.USER, AgentMessageRole.ASSISTANT),
                conversation.currentMessages.value.map(AgentMessage::role),
            )
            assertNull(conversation.activeTurnProgress.value)
            assertTrue(conversation.canStartTurn.value)
            assertTrue(conversation.canReload.value)
            assertFalse(conversation.canCancelTurn.value)
            assertTrue(conversation.canRunShellCommand.value)
            assertFalse(conversation.isTurnActive.value)

            conversation.send(AgentTurnRequest("structured", clientMessageId = "client-2"))
            assertEquals("structured", conversation.currentMessages.value.last().text)
            assertEquals("client-2", conversation.currentMessages.value.last().clientMessageId)
            process.notify("turn/completed", completedTurn("turn-2"))
            withTimeout(1_000) {
                conversation.state.first { it.status == AgentConversationStatus.READY }
            }

            conversation.close()
            assertFalse(conversation.canStartTurn.value)
            assertFalse(conversation.canReload.value)
            assertFalse(conversation.canCancelTurn.value)
            assertFalse(conversation.canRunShellCommand.value)
            assertFalse(conversation.isTurnActive.value)

            val withoutShell = testConversation(client, this, features = emptySet())
            try {
                withoutShell.open()
                assertTrue(withoutShell.canStartTurn.value)
                assertFalse(withoutShell.canRunShellCommand.value)
            } finally {
                withoutShell.close()
            }
        } finally {
            conversation.close()
            client.close()
        }
    }

    @Test
    fun callerCancellationLeavesTurnAndRefreshInRecoverableFailedState(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-cancelled") }
                })
                "turn/start", "thread/read" -> Unit
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 5_000)
        val conversation = testConversation(client, this)
        try {
            conversation.open()
            val sending = async { conversation.send(AgentTurnRequest("hello")) }
            withTimeout(1_000) {
                conversation.state.first { it.status == AgentConversationStatus.STARTING_TURN }
            }
            sending.cancelAndJoin()
            assertEquals(AgentConversationStatus.FAILED, conversation.state.value.status)
            assertEquals("turn_start_failed", conversation.state.value.failure?.code)
            assertFalse(conversation.isTurnActive.value)

            val refreshing = async { conversation.reload() }
            withTimeout(1_000) {
                conversation.state.first { it.status == AgentConversationStatus.RELOADING }
            }
            refreshing.cancelAndJoin()
            assertEquals(AgentConversationStatus.FAILED, conversation.state.value.status)
            assertEquals("reload_failed", conversation.state.value.failure?.code)
        } finally {
            conversation.close()
            client.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:CodexConversation#function:cancelTurn#sha256:13876fb392e13c0ecabcbc6e935baee4f07e0313bebe877eb92fe1049524ae0e",
    )
    fun cancellationWaitsForTheTurnIdWhenProgressArrivesBeforeTheStartResponse(): Unit = runBlocking {
        val releaseStart = CountDownLatch(1)
        val interruptReceived = CountDownLatch(1)
        val interruptCount = AtomicInteger()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-early-progress") }
                })
                "turn/start" -> {
                    server.notify(
                        "item/agentMessage/delta",
                        buildJsonObject {
                            put("threadId", "thread-early-progress")
                            put("turnId", "turn-early-progress")
                            put("itemId", "item-1")
                            put("delta", "working")
                        },
                    )
                    check(releaseStart.await(1, TimeUnit.SECONDS))
                    server.respond(message.id, buildJsonObject {
                        putJsonObject("turn") { put("id", "turn-early-progress") }
                    })
                }
                "turn/interrupt" -> {
                    interruptCount.incrementAndGet()
                    interruptReceived.countDown()
                    server.respond(message.id, buildJsonObject {})
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val conversation = testConversation(client, this)
        try {
            conversation.open()
            val sending = async { conversation.send(AgentTurnRequest("hello")) }
            withTimeout(1_000) {
                conversation.state.first { it.status == AgentConversationStatus.RUNNING_TURN }
            }
            assertTrue(conversation.isTurnActive.value)

            conversation.cancelTurn()
            assertEquals(AgentConversationStatus.CANCELLING_TURN, conversation.state.value.status)
            assertTrue(conversation.isTurnActive.value)
            assertEquals(0, interruptCount.get())

            releaseStart.countDown()
            sending.await()
            assertTrue(interruptReceived.await(1, TimeUnit.SECONDS))
            conversation.cancelTurn()
            assertEquals(1, interruptCount.get())
        } finally {
            releaseStart.countDown()
            conversation.close()
            client.close()
        }
    }

    @Test
    fun pendingCancellationDoesNotInterruptAfterTurnStartupFails(): Unit = runBlocking {
        val startRequest = CompletableDeferred<Long>()
        val interruptCount = AtomicInteger()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-failed-start") }
                })
                "turn/start" -> startRequest.complete(checkNotNull(message.id))
                "turn/interrupt" -> {
                    interruptCount.incrementAndGet()
                    server.respond(message.id, buildJsonObject {})
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val conversation = testConversation(client, this)
        try {
            conversation.open()
            val sending = async(start = CoroutineStart.UNDISPATCHED) {
                assertFailsWith<CodexOperationException> {
                    conversation.send(AgentTurnRequest("hello"))
                }
            }
            val requestId = withTimeout(1_000) { startRequest.await() }

            conversation.cancelTurn()
            process.sendRaw(buildJsonObject {
                put("id", requestId)
                putJsonObject("error") {
                    put("code", -32000)
                    put("message", "startup failed")
                }
            }.toString())

            sending.await()
            assertEquals(AgentConversationStatus.FAILED, conversation.state.value.status)
            assertEquals(0, interruptCount.get())
        } finally {
            conversation.close()
            client.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentHookActivity#constructor:<init>#sha256:8d3e78913731b32cb35d825b18a295f8640bcc4fa430ae77b8ac7b280b317579",
        "api-v1:AgentHookActivity#property:id#sha256:4e127ae76d055fa7fc966d9c93c6b365381bd287866783637f17ac9de0a71a6e",
        "api-v1:AgentHookRunStatus#enum-entry:RUNNING#sha256:1f8a7c92ed1db42c2f89f19d0666e2ed7fb8583b98121bc1014a069d1580c569",
        "api-v1:AgentTurnProgress#property:hookActivities#sha256:4819ab08e67ef108984b0aba800bc1b41ff6fe7cef24e58c3cdd39f2638ba670",
        "api-v1:AgentTurnProgress#property:isTruncated#sha256:27bded2fd4b2d09e53ed279fd38d9cfa450ffc6fde55cce15cdab946bb75a636",
        "api-v1:AgentTurnProgress#property:text#sha256:978c7346f9d22f46e785e788ea9b773342aa03156ea32f9493cea925ea81a00e",
    )
    fun liveTurnTextAndHookActivityAreStrictlyBounded(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-bounds") }
                })
                "turn/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-bounds") }
                })
                "turn/interrupt" -> server.respond(message.id, buildJsonObject {})
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val conversation = testConversation(client, this)
        try {
            val conversationId = conversation.open()
            conversation.send(AgentTurnRequest("hello"))
            conversation.process(AgentEvent.TextDelta(conversationId, "x".repeat(256 * 1024 + 1)))
            repeat(25) { index ->
                conversation.process(
                    AgentEvent.HookActivityChanged(
                        conversationId,
                        AgentHookActivity(
                            id = "hook-$index",
                            eventName = "preToolUse",
                            handlerType = "command",
                            status = AgentHookRunStatus.RUNNING,
                        ),
                    ),
                )
            }

            val progress = conversation.state.value.turnProgress
            assertEquals(256 * 1024, progress.text.length)
            assertTrue(progress.isTruncated)
            assertEquals(20, progress.hookActivities.size)
            assertEquals("hook-5", progress.hookActivities.first().id)
            assertEquals("hook-24", progress.hookActivities.last().id)
        } finally {
            conversation.close()
            client.close()
        }
    }

    @Test
    @CoversApi(
        "api-v1:AgentConversationState#property:conversation#sha256:2d95356c473f8bb9dcc11b501dbff92c501894f8875c8d2dc46ca12a12451960",
        "api-v1:AgentConversationState#property:failure#sha256:f6f10db61d720b9e668d4e1244d9ca53599ad5afc541cb58803effcc0940ce84",
        "api-v1:AgentConversationState#property:model#sha256:dd24f7948e0c1e27e098ae07fa86af45561b9aed76aa453a936dbb86d5f86f4a",
        "api-v1:AgentConversationState#property:status#sha256:ded3dd2f6886ce3804c35498e614a62125b2024a2215064ecd677805a7d44a3f",
        "api-v1:AgentConversationState#property:turnProgress#sha256:c758cf03cca6f758d6682464b69f1a3931fee531282070d7038d5f884ae64ea8",
        "api-v1:AgentPlanProgress#constructor:<init>#sha256:5994d72fb26bfe32d20371d65948c7fc3a70d3a50d99427015d0ea999eb8e979",
        "api-v1:AgentPlanProgress#property:steps#sha256:3b251b8f1cfee2101603f5c98fdc3a086c29aaa7e6e52570958439c2f545703c",
        "api-v1:AgentPlanStep#constructor:<init>#sha256:d916f08f4809f9cb48b084e6a9b62a6530673c9d747b5109e3c0b92619e03668",
        "api-v1:AgentPlanStep#property:text#sha256:1323dc137dbbd65928978d4585928892b9d17ca398e586d7423657a60f59b723",
        "api-v1:AgentPlanStepStatus#enum-entry:IN_PROGRESS#sha256:3c7575db40ca7e571d572ae447cdae7a7047466ef963bce927a5a026598f1864",
        "api-v1:AgentTurnProgress#constructor:<init>#sha256:504e0cff6aa5773e491af4f58ccf93f05df240ecd6134e0af331536b482aff95",
        "api-v1:AgentTurnProgress#property:commentary#sha256:aa6581c62bf9e697b37dbad986467ff380692db007854b684f895b7c8652f3a8",
        "api-v1:AgentTurnProgress#property:planProgress#sha256:f15b3f6a71e1afa0c6c65079dd5d80e495569f2fa702e4c2258defaeed4b720e",
        "api-v1:AgentTurnProgress#property:plan#sha256:46516ffb4fca2b1b44ae324ea501892ebbd205be42f1537870e19295b6ebf213",
        "api-v1:AgentTurnProgress#property:reasoning#sha256:9839a1e553e5913558d972eae7ed00c05f739a39bd5077d6b86314e60d3dfe45",
        "api-v1:AgentTurnProgress#property:shellExitCode#sha256:5836620dea51d710595c01fa9bafcd5c14cc9938e9f3c0f5aba9bc66a9bf3c05",
        "api-v1:AgentTurnProgress#property:shellOutput#sha256:973cea05275c0e29424afb962ad943e5784d192f3794fc444d4360f2e9ed3bac",
        "api-v1:AgentTurnProgress#property:workActivity#sha256:459fddbc9c0d833e140410d97ea89d57c3f85b4a7687ffe3e7bf4954633b04a5",
        "api-v1:AgentWorkActivity#enum-entry:WRITING_FILES#sha256:0fc95aaeda2f9858f13568d5bdb8a12988e7d445dbf49db53ce6c17b42db03b9",
        "api-v1:CodexConversation#function:reload#sha256:db962ae202892a26cfdb3636ab8a188da26e86222defe4af7a376fadfc963509",
    )
    fun reducesOnlyItsLiveTurnAndReconcilesOnceWithoutLosingAFailedDraft(): Unit = runBlocking {
        val reads = AtomicInteger()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "thread/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("thread") { put("id", "thread-1") }
                })
                "turn/start" -> server.respond(message.id, buildJsonObject {
                    putJsonObject("turn") { put("id", "turn-${reads.get() + 1}") }
                })
                "thread/read" -> if (reads.incrementAndGet() == 2) {
                    server.sendRaw(buildJsonObject {
                        put("id", message.id)
                        putJsonObject("error") {
                            put("code", -32000)
                            put("message", "offline")
                        }
                    }.toString())
                } else {
                    server.respond(message.id, canonicalConversation())
                }
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val conversation = testConversation(client, this)
        try {
            val conversationId = conversation.open()
            assertEquals(ConversationId("thread-1"), conversationId)
            assertEquals(AgentConversationStatus.READY, conversation.state.value.status)
            withTimeout(1_000) { conversation.state.first { it.model == "test" } }

            conversation.send(AgentTurnRequest("hello"))
            conversation.process(AgentEvent.TextDelta(ConversationId("other"), "ignore"))
            conversation.process(AgentEvent.TextDelta(conversationId, "answer"))
            conversation.process(AgentEvent.TextDelta(conversationId, "note", isCommentary = true))
            conversation.process(AgentEvent.ReasoningSummaryDelta(conversationId, "thinking", "reason-1", 0))
            conversation.process(AgentEvent.PlanDelta(conversationId, "plan", "plan-1"))
            conversation.process(
                AgentEvent.PlanUpdated(
                    conversationId,
                    AgentPlanProgress(steps = listOf(AgentPlanStep("ship", AgentPlanStepStatus.IN_PROGRESS))),
                ),
            )
            conversation.process(AgentEvent.ShellOutputDelta(conversationId, "output"))
            conversation.process(AgentEvent.ShellCommandCompleted(conversationId, 0))
            conversation.process(AgentEvent.WorkActivityChanged(conversationId, AgentWorkActivity.WRITING_FILES))
            conversation.process(
                AgentEvent.HookActivityChanged(
                    conversationId,
                    AgentHookActivity(
                        id = "hook-1",
                        eventName = "preToolUse",
                        handlerType = "command",
                        status = AgentHookRunStatus.RUNNING,
                    ),
                ),
            )

            val draft = conversation.state.value.turnProgress
            assertEquals("answer", draft.text)
            assertEquals("note", draft.commentary)
            assertEquals("thinking", draft.reasoning)
            assertEquals("plan", draft.plan)
            assertEquals("ship", draft.planProgress?.steps?.single()?.text)
            assertEquals("output", draft.shellOutput)
            assertEquals(0, draft.shellExitCode)
            assertEquals(AgentWorkActivity.WRITING_FILES, draft.workActivity)
            assertEquals("hook-1", draft.hookActivities.single().id)

            process.notify("turn/completed", completedTurn("turn-1"))
            withTimeout(1_000) {
                conversation.state.first { reads.get() == 1 && it.status == AgentConversationStatus.READY }
            }
            assertEquals("Canonical answer", conversation.state.value.conversation?.messages?.last()?.text)
            assertEquals(AgentTurnProgress(), conversation.state.value.turnProgress)
            conversation.process(AgentEvent.TurnCompleted(conversationId))
            assertEquals(1, reads.get())

            conversation.send(AgentTurnRequest("again"))
            conversation.process(AgentEvent.TextDelta(conversationId, "keep me"))
            process.notify("turn/completed", completedTurn("turn-2"))
            withTimeout(1_000) {
                conversation.state.first { reads.get() == 2 && it.status == AgentConversationStatus.FAILED }
            }
            assertEquals(2, reads.get())
            assertEquals(AgentConversationStatus.FAILED, conversation.state.value.status)
            assertEquals("keep me", conversation.state.value.turnProgress.text)
            assertTrue(assertNotNull(conversation.state.value.failure).isRecoverable)

            conversation.reload()
            assertEquals(3, reads.get())
            assertEquals(AgentConversationStatus.READY, conversation.state.value.status)
            assertEquals(AgentTurnProgress(), conversation.state.value.turnProgress)
        } finally {
            conversation.close()
            client.close()
        }
    }
}

private fun testConversation(
    client: CodexAgentClient,
    scope: CoroutineScope,
    features: Set<CodexRuntimeFeature> = CodexRuntimeFeature.entries.toSet(),
): CodexConversation =
    CodexConversation(
        client = client,
        scope = scope,
        workingDirectory = "/workspace",
        features = features,
        onClose = CodexConversation::closeOwned,
    )

private fun completedTurn(turnId: String) = buildJsonObject {
    put("threadId", "thread-1")
    putJsonObject("turn") {
        put("id", turnId)
        put("status", "completed")
    }
}

private fun conversationApprovalRequest() = buildJsonObject {
    put("itemId", "item-1")
    put("startedAtMs", 1)
    put("threadId", "thread-1")
    put("turnId", "turn-1")
    put("command", "git status")
}

private fun canonicalConversation() = buildJsonObject {
    put(
        "thread",
        thread(
            id = "thread-1",
            name = "Canonical",
            preview = "Canonical answer",
            updatedAt = 10,
            turns = buildJsonArray {
                add(buildJsonObject {
                    put("id", "turn-1")
                    put("status", "completed")
                    put("items", buildJsonArray {
                        add(plainUserMessage("user-1", "client-1", "hello"))
                        add(buildJsonObject {
                            put("id", "codex-1")
                            put("type", "agentMessage")
                            put("phase", "final_answer")
                            put("text", "Canonical answer")
                        })
                    })
                })
            },
        ),
    )
}
