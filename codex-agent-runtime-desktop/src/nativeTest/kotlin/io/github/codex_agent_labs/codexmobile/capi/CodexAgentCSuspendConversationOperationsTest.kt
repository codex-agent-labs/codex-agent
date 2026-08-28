@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentCapability
import io.github.codex_agent_labs.codexmobile.agent.AgentConversation
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexmobile.agent.CodexAgent
import io.github.codex_agent_labs.codexmobile.agent.CodexConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.staticCFunction
import kotlinx.cinterop.value
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexAgentCSuspendConversationOperationsTest {
    @Test
    fun catalogOperationsPreserveOrderDuplicatesOwnedResultsAndCopiedInputs(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture { method, _ ->
            when (method) {
                "thread/list" -> suspendConversationPage(
                    suspendConversationThread("duplicate", "First", "first", 30),
                    suspendConversationThread("duplicate", "Duplicate", "duplicate", 20),
                    suspendConversationThread("third", "Third", "third", 10),
                )
                "thread/name/set", "thread/delete" -> buildJsonObject {}
                else -> null
            }
        }
        val graph = createSuspendConversationGraph(fixture)
        fixture.additionalRequests.clear()
        try {
            memScoped {
                val listSlot = emptySuspendConversationHandle()
                val observer = SuspendConversationOperationObserver(listSlot.ptr)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsList(
                        graph.context,
                        graph.conversationsHandle,
                        suspendConversationOperationCallback,
                        observer.userData,
                        listSlot.ptr,
                    ),
                )
                observer.receive(graph.context, listSlot.value)
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, listSlot.value))
                val listResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, listSlot.value, listResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, listResult.value)
                assertEquals(1, observer.callbacks.load())

                val count = alloc<ULongVar>().also { it.value = 91uL }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationConversationSummariesCount(graph.context, listSlot.value, count.ptr),
                )
                assertEquals(3uL, count.value)
                val summaries = (0uL until count.value).map { index ->
                    emptySuspendConversationHandle().also { summary ->
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            codexAgentOperationConversationSummaryAt(
                                graph.context,
                                listSlot.value,
                                index,
                                summary.ptr,
                            ),
                        )
                    }
                }
                destroySuspendConversationOperation(graph.context, listSlot.ptr)
                assertNull(withTimeoutOrNull(SUSPEND_CONVERSATION_QUIET_MILLIS) { observer.events.receive() })
                observer.dispose()

                val summaryValues = summaries.map { summary ->
                    val value = suspendConversationPayload<CodexAgentCConversationSummarySnapshot>(
                        graph.context,
                        assertNotNull(summary.value),
                        CodexAgentCHandleKind.SNAPSHOT,
                    ).value
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentConversationSummaryDestroy(graph.context, summary.ptr),
                    )
                    value
                }
                assertEquals(listOf("duplicate", "duplicate", "third"), summaryValues.map { it.conversationId.value })
                assertEquals(listOf("First", "Duplicate", "Third"), summaryValues.map { it.title })

                val readId = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCConversationIdSnapshot(ConversationId("history")),
                )
                val readSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsRead(
                        graph.context,
                        graph.conversationsHandle,
                        readId.value,
                        null,
                        null,
                        readSlot.ptr,
                    ),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(graph.context, readId.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, readSlot.value))
                val readResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, readSlot.value, readResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, readResult.value)
                val conversationValue = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationConversationValue(
                        graph.context,
                        readSlot.value,
                        conversationValue.ptr,
                    ),
                )
                destroySuspendConversationOperation(graph.context, readSlot.ptr)
                val immutablePayload = suspendConversationPayload<Any>(
                    graph.context,
                    assertNotNull(conversationValue.value),
                    CodexAgentCHandleKind.SNAPSHOT,
                )
                assertFalse(immutablePayload is CodexAgentCConversation)
                val immutable = assertIs<CodexAgentCConversationValueSnapshot>(immutablePayload)
                assertEquals("history", immutable.value.summary.conversationId.value)
                assertIs<AgentConversation>(immutable.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationValueDestroy(graph.context, conversationValue.ptr),
                )

                val renameId = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCConversationIdSnapshot(ConversationId("rename-id")),
                )
                val name = suspendConversationString("  Preserved name  ")
                val renameSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsRename(
                        graph.context,
                        graph.conversationsHandle,
                        renameId.value,
                        name.view,
                        null,
                        null,
                        renameSlot.ptr,
                    ),
                )
                name.overwrite()
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(graph.context, renameId.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, renameSlot.value))
                val renameResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, renameSlot.value, renameResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, renameResult.value)
                destroySuspendConversationOperation(graph.context, renameSlot.ptr)

                val deleteId = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCConversationIdSnapshot(ConversationId("delete-id")),
                )
                val deleteSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsDelete(
                        graph.context,
                        graph.conversationsHandle,
                        deleteId.value,
                        null,
                        null,
                        deleteSlot.ptr,
                    ),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(graph.context, deleteId.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, deleteSlot.value))
                val deleteResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, deleteSlot.value, deleteResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, deleteResult.value)
                destroySuspendConversationOperation(graph.context, deleteSlot.ptr)

                val requests = fixture.additionalRequests
                assertEquals(listOf("thread/list", "thread/name/set", "thread/delete"), requests.map { it.first })
                assertEquals("rename-id", requests[1].second.getValue("threadId").jsonPrimitive.content)
                assertEquals("Preserved name", requests[1].second.getValue("name").jsonPrimitive.content)
                assertEquals("delete-id", requests[2].second.getValue("threadId").jsonPrimitive.content)
            }
        } finally {
            graph.close()
        }
    }

    @Test
    fun conversationOperationsCopyStructuredAndDefaultInputsAndCompleteShellAndReload(): Unit = runBlocking {
        lateinit var fixture: NativeCodexBehaviorFixture
        fixture = NativeCodexBehaviorFixture(
            features = CodexRuntimeFeature.entries.toSet(),
            additionalResponse = { method, params ->
                when (method) {
                    "thread/shellCommand" -> {
                        fixture.notify(
                            "item/started",
                            buildJsonObject {
                                put("startedAtMs", 0)
                                put("threadId", params.getValue("threadId"))
                                put("turnId", "shell-turn")
                                putJsonObject("item") {
                                    put("command", params.getValue("command"))
                                    putJsonArray("commandActions") {}
                                    put("cwd", "/workspace")
                                    put("id", "shell-item")
                                    put("type", "commandExecution")
                                    put("source", "userShell")
                                    put("status", "inProgress")
                                }
                            },
                        )
                        fixture.notify(
                            "turn/completed",
                            buildJsonObject {
                                put("threadId", params.getValue("threadId"))
                                putJsonObject("turn") {
                                    put("id", "shell-turn")
                                    putJsonArray("items") {}
                                    put("status", "completed")
                                }
                            },
                        )
                        buildJsonObject {}
                    }
                    else -> null
                }
            },
        )
        val graph = createSuspendConversationGraph(fixture, openConversation = true)
        try {
            memScoped {
                val capabilities = mutableSetOf(AgentCapability.WEB_SEARCH)
                val invocations = mutableListOf<AgentInvocation>(
                    AgentInvocation.Skill("Review", "/skills/review/SKILL.md"),
                    AgentInvocation.Plugin("Drive", "plugin://drive@catalog"),
                )
                val request = AgentTurnRequest(
                    prompt = "Structured request",
                    clientMessageId = "client-structured",
                    capabilities = capabilities,
                    invocations = invocations,
                )
                val requestHandle = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCTurnRequestSnapshot(request),
                )
                val sendSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSendRequest(
                        graph.context,
                        graph.requiredConversationHandle,
                        requestHandle.value,
                        null,
                        null,
                        sendSlot.ptr,
                    ),
                )
                capabilities.clear()
                invocations.clear()
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(graph.context, requestHandle.ptr))
                withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) { fixture.turnStartObserved.await() }
                fixture.releaseTurnStart.complete(Unit)
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, sendSlot.value))
                val sendResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, sendSlot.value, sendResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, sendResult.value)
                destroySuspendConversationOperation(graph.context, sendSlot.ptr)
                graph.requiredConversation.cancelTurn()
                withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
                    while (graph.requiredConversation.state.value.status != AgentConversationStatus.READY) yield()
                }

                val structured = fixture.turnRequests[0]
                assertEquals("client-structured", structured.getValue("clientUserMessageId").jsonPrimitive.content)
                assertNull(structured["model"])
                assertNull(structured["effort"])
                assertNull(structured["serviceTier"])
                assertEquals("on-request", structured.getValue("approvalPolicy").jsonPrimitive.content)
                assertEquals("auto_review", structured.getValue("approvalsReviewer").jsonPrimitive.content)
                assertEquals(
                    listOf("text", "skill", "mention"),
                    structured.getValue("input").jsonArray.map { it.jsonObject.getValue("type").jsonPrimitive.content },
                )
                assertEquals(
                    "Use 🌐 Web search\n\$Review\n@Drive\n\nStructured request",
                    structured.getValue("input").jsonArray[0].jsonObject.getValue("text").jsonPrimitive.content,
                )

                val command = suspendConversationString("  printf copied  ")
                val shellSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationRunShellCommand(
                        graph.context,
                        graph.requiredConversationHandle,
                        command.view,
                        null,
                        null,
                        shellSlot.ptr,
                    ),
                )
                command.overwrite()
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, shellSlot.value))
                val shellResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, shellSlot.value, shellResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, shellResult.value)
                destroySuspendConversationOperation(graph.context, shellSlot.ptr)
                withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
                    while (graph.requiredConversation.state.value.status != AgentConversationStatus.READY) yield()
                }
                val shell = fixture.additionalRequests.single { it.first == "thread/shellCommand" }.second
                assertEquals("printf copied", shell.getValue("command").jsonPrimitive.content)

                val reloadSlot = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationReload(
                        graph.context,
                        graph.requiredConversationHandle,
                        null,
                        null,
                        reloadSlot.ptr,
                    ),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, awaitSuspendConversationOperation(graph.context, reloadSlot.value))
                val reloadResult = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationResult(graph.context, reloadSlot.value, reloadResult.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, reloadResult.value)
                destroySuspendConversationOperation(graph.context, reloadSlot.ptr)
                assertEquals(AgentConversationStatus.READY, graph.requiredConversation.state.value.status)
            }
        } finally {
            graph.close()
        }
    }

    @Test
    fun everyLaunchRejectsWrongContextTypeStaleNullAndOccupiedOutputs(): Unit = runBlocking {
        val fixture = NativeCodexBehaviorFixture(features = CodexRuntimeFeature.entries.toSet())
        val graph = createSuspendConversationGraph(fixture, openConversation = true)
        val otherContext = handleRegistry.createContext().requiredSuspendConversationValue()
        try {
            memScoped {
                val id = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCConversationIdSnapshot(ConversationId("validation")),
                )
                val request = suspendConversationSnapshot(
                    graph.context,
                    CodexAgentCTurnRequestSnapshot(AgentTurnRequest("validation")),
                )
                val name = suspendConversationString("validation")
                val command = suspendConversationString("pwd")
                val launches = listOf(
                    SuspendConversationLaunch("list", graph.conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) { c, t, o ->
                        codexAgentConversationsList(c, t, null, null, o)
                    },
                    SuspendConversationLaunch("read", graph.conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) { c, t, o ->
                        codexAgentConversationsRead(c, t, id.value, null, null, o)
                    },
                    SuspendConversationLaunch("rename", graph.conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) { c, t, o ->
                        codexAgentConversationsRename(c, t, id.value, name.view, null, null, o)
                    },
                    SuspendConversationLaunch("delete", graph.conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) { c, t, o ->
                        codexAgentConversationsDelete(c, t, id.value, null, null, o)
                    },
                    SuspendConversationLaunch("sendRequest", graph.requiredConversationHandle, CodexAgentCHandleKind.CONVERSATION) { c, t, o ->
                        codexAgentConversationSendRequest(c, t, request.value, null, null, o)
                    },
                    SuspendConversationLaunch("runShellCommand", graph.requiredConversationHandle, CodexAgentCHandleKind.CONVERSATION) { c, t, o ->
                        codexAgentConversationRunShellCommand(c, t, command.view, null, null, o)
                    },
                    SuspendConversationLaunch("reload", graph.requiredConversationHandle, CodexAgentCHandleKind.CONVERSATION) { c, t, o ->
                        codexAgentConversationReload(c, t, null, null, o)
                    },
                )
                launches.forEach { launch ->
                    assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, launch.invoke(graph.context, launch.target, null), launch.name)
                    val occupied = emptySuspendConversationHandle().also { it.value = graph.hostHandle }
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        launch.invoke(graph.context, launch.target, occupied.ptr),
                        launch.name,
                    )
                    assertEquals(graph.hostHandle, occupied.value, launch.name)
                    val output = emptySuspendConversationHandle()
                    assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, launch.invoke(graph.context, null, output.ptr), launch.name)
                    assertNull(output.value, launch.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        launch.invoke(graph.context, graph.hostHandle, output.ptr),
                        launch.name,
                    )
                    assertNull(output.value, launch.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_CONTEXT,
                        launch.invoke(otherContext, launch.target, output.ptr),
                        launch.name,
                    )
                    assertNull(output.value, launch.name)
                    val stale = handleRegistry.retain(graph.context, launch.target, launch.kind)
                        .requiredSuspendConversationValue()
                    assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.release(graph.context, stale, launch.kind))
                    assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, launch.invoke(graph.context, stale, output.ptr), launch.name)
                    assertNull(output.value, launch.name)
                }

                val otherId = suspendConversationSnapshot(
                    otherContext,
                    CodexAgentCConversationIdSnapshot(ConversationId("other")),
                )
                val staleId = handleRegistry.retain(
                    graph.context,
                    assertNotNull(id.value),
                    CodexAgentCHandleKind.SNAPSHOT,
                ).requiredSuspendConversationValue()
                assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.release(graph.context, staleId, CodexAgentCHandleKind.SNAPSHOT))
                val output = emptySuspendConversationHandle()
                listOf(
                    graph.hostHandle to CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    otherId.value to CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    staleId to CODEX_AGENT_STATUS_STALE_HANDLE,
                    null to CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                ).forEach { (invalidId, status) ->
                    assertEquals(
                        status,
                        codexAgentConversationsRead(
                            graph.context,
                            graph.conversationsHandle,
                            invalidId,
                            null,
                            null,
                            output.ptr,
                        ),
                    )
                    assertNull(output.value)
                }

                val otherRequest = suspendConversationSnapshot(
                    otherContext,
                    CodexAgentCTurnRequestSnapshot(AgentTurnRequest("other")),
                )
                val staleRequest = handleRegistry.retain(
                    graph.context,
                    assertNotNull(request.value),
                    CodexAgentCHandleKind.SNAPSHOT,
                ).requiredSuspendConversationValue()
                assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.release(graph.context, staleRequest, CodexAgentCHandleKind.SNAPSHOT))
                listOf(
                    graph.hostHandle to CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    otherRequest.value to CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    staleRequest to CODEX_AGENT_STATUS_STALE_HANDLE,
                    null to CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                ).forEach { (invalidRequest, status) ->
                    assertEquals(
                        status,
                        codexAgentConversationSendRequest(
                            graph.context,
                            graph.requiredConversationHandle,
                            invalidRequest,
                            null,
                            null,
                            output.ptr,
                        ),
                    )
                    assertNull(output.value)
                }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationsRename(
                        graph.context,
                        graph.conversationsHandle,
                        id.value,
                        null,
                        null,
                        null,
                        output.ptr,
                    ),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentConversationRunShellCommand(
                        graph.context,
                        graph.requiredConversationHandle,
                        null,
                        null,
                        null,
                        output.ptr,
                    ),
                )
                assertNull(output.value)

                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(otherContext, otherId.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(otherContext, otherRequest.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(graph.context, id.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(graph.context, request.ptr))
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            graph.close()
        }
    }

    @Test
    fun callbacksFailuresCancellationDestructionAndTargetLeaseAreFailClosed(): Unit = runBlocking {
        val failureFixture = NativeCodexBehaviorFixture { method, _ ->
            if (method == "thread/list") error("catalog exploded") else null
        }
        val failureGraph = createSuspendConversationGraph(failureFixture)
        try {
            memScoped {
                val operation = emptySuspendConversationHandle()
                val observer = SuspendConversationOperationObserver(operation.ptr)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsList(
                        failureGraph.context,
                        failureGraph.conversationsHandle,
                        suspendConversationOperationCallback,
                        observer.userData,
                        operation.ptr,
                    ),
                )
                observer.receive(failureGraph.context, operation.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OPERATION_FAILED,
                    awaitSuspendConversationOperation(failureGraph.context, operation.value),
                )
                val failure = emptySuspendConversationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationFailure(failureGraph.context, operation.value, failure.ptr),
                )
                assertEquals(
                    "conversation_list_failed",
                    suspendConversationPayload<io.github.codex_agent_labs.codexmobile.agent.CodexFailure>(
                        failureGraph.context,
                        assertNotNull(failure.value),
                        CodexAgentCHandleKind.FAILURE,
                    ).code,
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(failureGraph.context, failure.ptr))
                destroySuspendConversationOperation(failureGraph.context, operation.ptr)
                assertEquals(1, observer.callbacks.load())
                assertNull(withTimeoutOrNull(SUSPEND_CONVERSATION_QUIET_MILLIS) { observer.events.receive() })
                observer.dispose()
            }
        } finally {
            failureGraph.close()
        }

        val cancellationFixture = NativeCodexBehaviorFixture { _, _ -> null }
        val cancellationGraph = createSuspendConversationGraph(cancellationFixture)
        try {
            memScoped {
                val operation = emptySuspendConversationHandle()
                val observer = SuspendConversationOperationObserver(operation.ptr)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationsList(
                        cancellationGraph.context,
                        cancellationGraph.conversationsHandle,
                        suspendConversationOperationCallback,
                        observer.userData,
                        operation.ptr,
                    ),
                )
                withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
                    while (cancellationFixture.additionalRequests.none { it.first == "thread/list" }) yield()
                }
                assertEquals(
                    CODEX_AGENT_STATUS_BUSY,
                    handleRegistry.invalidateChildren(
                        cancellationGraph.context,
                        cancellationGraph.agentHandle,
                        CodexAgentCHandleKind.AGENT,
                    ),
                )
                val published = operation.value
                assertEquals(
                    CODEX_AGENT_STATUS_BUSY,
                    codexAgentOperationDestroy(cancellationGraph.context, operation.ptr),
                )
                assertEquals(published, operation.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentOperationCancel(cancellationGraph.context, operation.value),
                )
                observer.receive(cancellationGraph.context, operation.value)
                assertEquals(
                    CODEX_AGENT_STATUS_CANCELLED,
                    awaitSuspendConversationOperation(cancellationGraph.context, operation.value),
                )
                destroySuspendConversationOperation(cancellationGraph.context, operation.ptr)
                assertEquals(1, observer.callbacks.load())
                assertNull(withTimeoutOrNull(SUSPEND_CONVERSATION_QUIET_MILLIS) { observer.events.receive() })
                observer.dispose()
            }
        } finally {
            cancellationGraph.close()
        }
    }
}

private data class SuspendConversationGraph(
    val fixture: NativeCodexBehaviorFixture,
    val runtime: CodexAgentCContextRuntime,
    val context: COpaquePointer,
    val hostHandle: COpaquePointer,
    val agentHandle: COpaquePointer,
    val conversationsHandle: COpaquePointer,
    val conversationHandle: COpaquePointer?,
    val host: CodexAgentCHost,
    val agent: CodexAgent,
    val conversation: CodexConversation?,
) {
    val requiredConversationHandle: COpaquePointer get() = checkNotNull(conversationHandle)
    val requiredConversation: CodexConversation get() = checkNotNull(conversation)

    suspend fun close() {
        runCatching { conversation?.close() }
        host.core.close()
        conversationHandle?.let { handle ->
            handleRegistry.semanticClose(context, handle, CodexAgentCHandleKind.CONVERSATION) {
                CODEX_AGENT_STATUS_OK
            }
            handleRegistry.release(context, handle, CodexAgentCHandleKind.CONVERSATION)
        }
        handleRegistry.semanticClose(context, conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, conversationsHandle, CodexAgentCHandleKind.CONVERSATIONS)
        handleRegistry.semanticClose(context, agentHandle, CodexAgentCHandleKind.AGENT) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, agentHandle, CodexAgentCHandleKind.AGENT)
        handleRegistry.semanticClose(context, hostHandle, CodexAgentCHandleKind.HOST) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, hostHandle, CodexAgentCHandleKind.HOST)
        assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(context))
        runtime.cancel()
    }
}

private suspend fun createSuspendConversationGraph(
    fixture: NativeCodexBehaviorFixture,
    openConversation: Boolean = false,
): SuspendConversationGraph {
    val runtime = CodexAgentCContextRuntime()
    val context = handleRegistry.createContext(runtime).requiredSuspendConversationValue()
    val host = CodexAgentCHost(fixture.createHost(), runtime)
    val hostHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        host,
    ).requiredSuspendConversationValue()
    host.core.selectWorkspace(CodexPathWorkspaceSelection(fixture.workspace.path))
    val agent = (host.core.lifecycleState.value as CodexHostState.Ready).agent
    val agentHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.AGENT,
        CodexAgentCAgent(agent, host),
        hostHandle,
        CodexAgentCHandleKind.HOST,
    ).requiredSuspendConversationValue()
    val conversationsHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.CONVERSATIONS,
        CodexAgentCConversations(agent.conversations, host, agent),
        agentHandle,
        CodexAgentCHandleKind.AGENT,
    ).requiredSuspendConversationValue()
    val conversation = if (openConversation) agent.conversations.open() else null
    val conversationHandle = conversation?.let {
        handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.CONVERSATION,
            CodexAgentCConversation(it, runtime),
            conversationsHandle,
            CodexAgentCHandleKind.CONVERSATIONS,
        ).requiredSuspendConversationValue()
    }
    return SuspendConversationGraph(
        fixture,
        runtime,
        context,
        hostHandle,
        agentHandle,
        conversationsHandle,
        conversationHandle,
        host,
        agent,
        conversation,
    )
}

private data class SuspendConversationLaunch(
    val name: String,
    val target: COpaquePointer,
    val kind: CodexAgentCHandleKind,
    val invoke: (
        COpaquePointer?,
        COpaquePointer?,
        CPointer<COpaquePointerVar>?,
    ) -> Int,
)

private data class SuspendConversationOperationEvent(
    val context: COpaquePointer?,
    val operation: COpaquePointer?,
    val userData: COpaquePointer?,
    val publishedOperation: COpaquePointer?,
)

private class SuspendConversationOperationObserver(
    private val output: CPointer<COpaquePointerVar>,
) {
    val events = Channel<SuspendConversationOperationEvent>(Channel.UNLIMITED)
    val callbacks = AtomicInt(0)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    suspend fun receive(context: COpaquePointer, operation: COpaquePointer?) {
        withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
            events.receive().also { event ->
                assertEquals(context, event.context)
                assertEquals(operation, event.operation)
                assertEquals(operation, event.publishedOperation)
                assertEquals(userData, event.userData)
            }
        }
    }

    fun dispose() = reference.dispose()

    fun publish(context: COpaquePointer?, operation: COpaquePointer?, userData: COpaquePointer?) {
        callbacks.addAndFetch(1)
        events.trySend(SuspendConversationOperationEvent(context, operation, userData, output.pointed.value))
    }
}

private val suspendConversationOperationCallback = staticCFunction {
        context: COpaquePointer?,
        operation: COpaquePointer?,
        userData: COpaquePointer?,
    ->
    checkNotNull(userData).asStableRef<SuspendConversationOperationObserver>().get()
        .publish(context, operation, userData)
}

private data class SuspendConversationString(
    val view: CPointer<codex_agent_string_view>,
    val data: CPointer<UByteVar>?,
    val size: Int,
) {
    fun overwrite() {
        repeat(size) { index -> checkNotNull(data)[index] = 'x'.code.toUByte() }
    }
}

private fun MemScope.suspendConversationString(value: String): SuspendConversationString {
    val encoded = value.encodeToByteArray()
    val data = if (encoded.isEmpty()) null else allocArray<UByteVar>(encoded.size).also { buffer ->
        encoded.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    }
    val view = alloc<codex_agent_string_view>().also {
        it.size = encoded.size.toULong()
        it.data = data
    }
    return SuspendConversationString(view.ptr, data, encoded.size)
}

private fun MemScope.emptySuspendConversationHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.suspendConversationSnapshot(
    context: COpaquePointer,
    snapshot: CodexAgentCSnapshot,
): COpaquePointerVar = emptySuspendConversationHandle().also {
    it.value = createSnapshot(context, snapshot).requiredSuspendConversationValue()
}

private fun <T : Any> suspendConversationPayload(
    context: COpaquePointer,
    handle: COpaquePointer,
    kind: CodexAgentCHandleKind,
): T {
    val lease = handleRegistry.acquire(context, handle, kind).requiredSuspendConversationValue()
    @Suppress("UNCHECKED_CAST")
    return (lease.payload as T).also { assertEquals(CODEX_AGENT_STATUS_OK, lease.close()) }
}

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredSuspendConversationValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}

private suspend fun awaitSuspendConversationOperation(
    context: COpaquePointer,
    operation: COpaquePointer?,
): Int = withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
    memScoped {
        val result = alloc<IntVar>()
        while (true) {
            when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                else -> error("operation result query failed with $status")
            }
        }
        error("unreachable")
    }
}

private suspend fun destroySuspendConversationOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(SUSPEND_CONVERSATION_TIMEOUT_MILLIS) {
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

private fun suspendConversationPage(vararg threads: JsonObject): JsonObject = buildJsonObject {
    put("data", buildJsonArray { threads.forEach { add(it) } })
    put("nextCursor", JsonNull)
}

private fun suspendConversationThread(
    id: String,
    name: String?,
    preview: String,
    updatedAt: Long,
): JsonObject = buildJsonObject {
    put("cliVersion", "test")
    put("createdAt", 0)
    put("cwd", "/workspace")
    put("ephemeral", false)
    put("id", id)
    put("modelProvider", "openai")
    name?.let { put("name", it) }
    put("preview", preview)
    put("sessionId", id)
    put("source", "cli")
    putJsonObject("status") { put("type", "idle") }
    putJsonArray("turns") {}
    put("updatedAt", updatedAt)
}

private const val SUSPEND_CONVERSATION_TIMEOUT_MILLIS = 5_000L
private const val SUSPEND_CONVERSATION_QUIET_MILLIS = 25L
