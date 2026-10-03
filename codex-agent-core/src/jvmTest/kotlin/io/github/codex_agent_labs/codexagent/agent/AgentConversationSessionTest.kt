package io.github.codex_agent_labs.codexagent.agent

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
        "api-v1:CodexConversation#function:close#sha256:4da738a807b788f206dc6acb8285bd3a7e57fd4c138d57322b53b4034d765247",
        "api-v1:CodexConversation#function:send#sha256:0f496fac7f915485f7bac2272847319b31eab19cfa432beafae41be5b6f23199",
        "api-v1:CodexConversation#function:send#sha256:86ce4fd9be2b6db0bd74c1fdab490f4dfa5e9176e2d77a2114f64443004e5aa2",
        "api-v1:CodexConversation#property:activeTurnProgress#sha256:aced3dafefcfef206102eeee5398467dd04026e0d5fe96f0d0abbfd0bb23b0f7",
        "api-v1:CodexConversation#property:canCancelTurn#sha256:3b21d41c72465540c6630478df44b072d2e3342ea93a186e71b9e152b08c5b23",
        "api-v1:CodexConversation#property:canReload#sha256:c6105dce0ec3928bb53c02500735a1fa6c671ad22e07aec3468f2f01c9756f26",
        "api-v1:CodexConversation#property:canRunShellCommand#sha256:aae9be7ef5e498b6f30c630cfb431b83712f4531b2990c05b6b512eb89cf2b33",
        "api-v1:CodexConversation#property:canStartTurn#sha256:ce5baa0598d529fe5f370b2e763feb75ea47b8084e759f15bf8dfb55a0d8606f",
        "api-v1:CodexConversation#property:currentMessages#sha256:f3e1936024c59761cec3109994c8200556f13402c0291616c207afabe5ece9da",
        "api-v1:CodexConversation#property:isTurnActive#sha256:42a0aab9e5090bf526f2c6494953dae3f1aa37dcd6c1250f99dd546f97dd20c8",
        "api-v1:CodexConversation#property:state#sha256:ebfe03c30ccc85dbe8bc90387477766b5448bc397d7e94a4e9170305039d8544",
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
        "api-v1:CodexConversation#function:cancelTurn#sha256:d26d4787953704f00dc0242094f252a471e7e85227df9f8551ec1a9ed0992005",
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
        "api-v1:AgentHookActivity#constructor:<init>#sha256:054ee6647b178a110d6ae4b06669a9c6787d6d82f2d136967108fa7d8718d62a",
        "api-v1:AgentHookActivity#property:id#sha256:b363aff292e7be9781b0ccb0f7c9355f17df41f3936648b7b421f6fe12a323ad",
        "api-v1:AgentHookRunStatus#enum-entry:RUNNING#sha256:682b36fddc3a19bfa8f523e52744443848688580ddaecbe4e968e4e732f10089",
        "api-v1:AgentTurnProgress#property:hookActivities#sha256:73b627a0a1d28b16e729e8328ae3d0851d8c180e9f0cb850269b1d7a1c818427",
        "api-v1:AgentTurnProgress#property:isTruncated#sha256:720a74a314b0a9fdbe4e66e34693cb8af5729c6541c9ec70028c7bb17ad87e4b",
        "api-v1:AgentTurnProgress#property:text#sha256:f7190407ed697e2942b03d200048095b808c99b2770f7a65f24eef004f2763ae",
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
        "api-v1:AgentConversationState#property:conversation#sha256:60150f522c78dcfc34ce26dfe70a5fbd3a72e52840599f3c86cdea6674fdfe8a",
        "api-v1:AgentConversationState#property:failure#sha256:f23d8a4a3df718367745d27b51bdff78783b660cdb47df99d3eeefd8f8971983",
        "api-v1:AgentConversationState#property:model#sha256:b967d1e6f65c46a54ec2a94205fa088818657ebdcc5301f4ee4231bd7fb9885c",
        "api-v1:AgentConversationState#property:status#sha256:51948b8cdb7b87f66ffe5307107bb8bee5c3808e0c55d4152d2445b849d54913",
        "api-v1:AgentConversationState#property:turnProgress#sha256:c8e73278cf677931c2540891e225b9132d05761310ccffc04a702f26ab3c663d",
        "api-v1:AgentPlanProgress#constructor:<init>#sha256:c824bda7371aed5087a37705c4d9bcdb6b879ae24ba98b26e107e8c212fe8721",
        "api-v1:AgentPlanProgress#property:steps#sha256:b541ed82b2a87a6c0892870e0963aa18a21a772cefc74402b3191111afc0377b",
        "api-v1:AgentPlanStep#constructor:<init>#sha256:e1b8d77105a198d58d5ce4740f72ac31d67a04925d8151a68c2f14b0903bb62d",
        "api-v1:AgentPlanStep#property:text#sha256:11a2741f71bfab60a9b898516f936c989790d52105ceef532d431b666d989dca",
        "api-v1:AgentPlanStepStatus#enum-entry:IN_PROGRESS#sha256:e72eb6ce0aa866ca62f52923bf3455419b082d73cd072b6ebc441781444bd063",
        "api-v1:AgentTurnProgress#constructor:<init>#sha256:8340a1f1df95b7d94fc97bae51f20afba3187e12061c81c81f30111789deca70",
        "api-v1:AgentTurnProgress#property:commentary#sha256:174c385561f75a12b5e9014d606d16d32e0b21fd27d3d96ed8c3c86e2a5636d8",
        "api-v1:AgentTurnProgress#property:planProgress#sha256:29548fec2681673e6876afa6c9c79ed853a4d40823eae1f91d836725e65d08a7",
        "api-v1:AgentTurnProgress#property:plan#sha256:f43fa61b8754f6b12f53873c83042851e98a0c0a3c248023a48a8721f9cd27c7",
        "api-v1:AgentTurnProgress#property:reasoning#sha256:44fb8a5b9fbce57ac7730a4762b4e93619fe9355f3c93c4462bc624fc3b13f21",
        "api-v1:AgentTurnProgress#property:shellExitCode#sha256:ddb106fabab77eb322e96817b0af1217beccd6807da7985c49af1098dc47a510",
        "api-v1:AgentTurnProgress#property:shellOutput#sha256:8af64f309d939e9c0aa8d2c9b6bb8e4ba752c4a27b21383813d0e6ac3a536e53",
        "api-v1:AgentTurnProgress#property:workActivity#sha256:d44e5f1aac386969aee36182851bd919ecb7192427329060a58d0cb73fb43182",
        "api-v1:AgentWorkActivity#enum-entry:WRITING_FILES#sha256:196a3686dd559f1bac1c6ebb8e1fb7f765efbfa5e3c5dd1b3935f0f5ce44f0a2",
        "api-v1:CodexConversation#function:reload#sha256:7e7acff291309ae6dc2f1880b75766a5e2f5fb9c90f25239432c05efb02c8a6a",
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
