@file:OptIn(kotlin.concurrent.atomics.ExperimentalAtomicApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceStore
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.agent.PreparedCodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexJsonLine
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntimeEvent
import kotlin.concurrent.atomics.AtomicBoolean
import kotlin.concurrent.atomics.AtomicInt
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

internal class NativeCodexBehaviorFixture(
    private val prepareFailure: Throwable? = null,
    private val features: Set<CodexRuntimeFeature> = emptySet(),
    private val onServerResponse: suspend (JsonObject) -> Unit = {},
    private val additionalResponse: suspend (String, JsonObject) -> JsonObject? = { _, _ -> null },
) {
    val workspace = CodexWorkspace("/workspace", "Native fixture workspace")
    val clientInfo = CodexClientInfo("native_fixture", "Native Fixture", "test")
    val newConversationId = ConversationId("native-thread")

    val selectedWorkspaces = mutableListOf<CodexWorkspaceSelection>()
    val preparedWorkspaces = mutableListOf<CodexWorkspace>()
    val openRequests = mutableListOf<Pair<String, JsonObject>>()
    val turnRequests = mutableListOf<JsonObject>()
    val interruptRequests = mutableListOf<JsonObject>()
    val additionalRequests = mutableListOf<Pair<String, JsonObject>>()
    val serverResponses = mutableListOf<JsonObject>()

    val turnStartObserved = CompletableDeferred<Unit>()
    val releaseTurnStart = CompletableDeferred<Unit>()
    val interruptObserved = CompletableDeferred<Unit>()

    private val runtime = ScriptedRuntime()

    val runtimeStarted: Boolean get() = runtime.started.load()
    val runtimeClosed: Boolean get() = runtime.closed.load()
    val runtimeCloseCalls: Int get() = runtime.closeCalls.load()

    val platform: CodexPlatform = object : CodexPlatform {
        override val authorizationBrowser =
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
        override val workspaceStore: CodexWorkspaceStore = object : CodexWorkspaceStore {
            override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution {
                selectedWorkspaces += selection
                require(selection is CodexPathWorkspaceSelection)
                return CodexWorkspaceResolution.Available(workspace)
            }

            override suspend fun restore(): CodexWorkspaceResolution =
                CodexWorkspaceResolution.SelectionRequired(
                    CodexWorkspaceSelectionReason.NOT_SELECTED,
                    "Select a workspace",
                )

            override suspend fun clear(): Unit = Unit
        }

        override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
            preparedWorkspaces += workspace
            prepareFailure?.let { throw it }
            return PreparedCodexRuntime(
                runtimeFactory = { runtime },
                workspacePath = workspace.path,
                features = features,
            )
        }
    }

    fun createHost(): CodexHost = CodexHost(platform, clientInfo)

    suspend fun notify(method: String, params: JsonObject): Unit = runtime.notify(method, params)

    suspend fun request(id: Long, method: String, params: JsonObject): Unit =
        runtime.request(id, method, params)

    private inner class ScriptedRuntime : CodexRuntime {
        val started = AtomicBoolean(false)
        val closed = AtomicBoolean(false)
        val closeCalls = AtomicInt(0)
        private val eventChannel = Channel<CodexRuntimeEvent>(Channel.UNLIMITED)

        override val events: Flow<CodexRuntimeEvent> = eventChannel.receiveAsFlow()

        override suspend fun start() {
            check(!closed.load()) { "runtime is closed" }
            check(started.compareAndSet(false, true)) { "runtime already started" }
        }

        override suspend fun send(line: CodexJsonLine) {
            check(started.load() && !closed.load()) { "runtime is not running" }
            val request = Json.parseToJsonElement(line.value).jsonObject
            val method = request["method"]?.jsonPrimitive?.content
            if (method == null) {
                serverResponses += request
                onServerResponse(request)
                return
            }
            val params = request["params"]?.jsonObject ?: buildJsonObject {}
            when (method) {
                "initialize" -> respond(
                    request,
                    buildJsonObject {
                        put("codexHome", "/tmp/codex-native-fixture")
                        put("platformFamily", "unix")
                        put("platformOs", "native-test")
                        put("userAgent", "native-fixture")
                    },
                )

                "thread/start", "thread/resume" -> {
                    openRequests += method to params
                    val id = if (method == "thread/resume") {
                        params.getValue("threadId").jsonPrimitive.content
                    } else {
                        newConversationId.value
                    }
                    respond(request, openResponse(id, params))
                }

                "turn/start" -> {
                    turnRequests += params
                    val threadId = params.getValue("threadId").jsonPrimitive.content
                    turnStartObserved.complete(Unit)
                    notify(
                        "item/agentMessage/delta",
                        buildJsonObject {
                            put("threadId", threadId)
                            put("turnId", TURN_ID)
                            put("itemId", "native-item")
                            put("delta", "working")
                        },
                    )
                    // Keep the start response pending so cancellation can prove it waits for the turn ID.
                    releaseTurnStart.await()
                    respond(request, buildJsonObject { put("turn", turn(TURN_ID, "inProgress")) })
                }

                "turn/interrupt" -> {
                    interruptRequests += params
                    respond(request, buildJsonObject {})
                    notify(
                        "turn/completed",
                        buildJsonObject {
                            put("threadId", params.getValue("threadId"))
                            put("turn", turn(TURN_ID, "completed"))
                        },
                    )
                    interruptObserved.complete(Unit)
                }

                "thread/read" -> {
                    val id = params.getValue("threadId").jsonPrimitive.content
                    respond(
                        request,
                        additionalResponse(method, params)
                            ?: buildJsonObject { put("thread", thread(id)) },
                    )
                }

                else -> {
                    additionalRequests += method to params
                    additionalResponse(method, params)?.let { respond(request, it) }
                }
            }
        }

        override fun close() {
            closeCalls.addAndFetch(1)
            if (closed.compareAndSet(false, true)) eventChannel.close()
        }

        private suspend fun respond(request: JsonObject, result: JsonObject) {
            val id = request["id"] ?: return
            emit(buildJsonObject { put("id", id); put("result", result) })
        }

        suspend fun notify(method: String, params: JsonObject) {
            emit(buildJsonObject { put("method", method); put("params", params) })
        }

        suspend fun request(id: Long, method: String, params: JsonObject) {
            emit(buildJsonObject { put("id", id); put("method", method); put("params", params) })
        }

        private suspend fun emit(value: JsonObject) {
            eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(value.toString())))
        }
    }

    private fun openResponse(id: String, params: JsonObject): JsonObject = buildJsonObject {
        put("approvalPolicy", params.getValue("approvalPolicy"))
        put("approvalsReviewer", params.getValue("approvalsReviewer"))
        put("cwd", workspace.path)
        put("model", "native-test")
        put("modelProvider", "openai")
        putJsonObject("sandbox") { put("type", "dangerFullAccess") }
        put("thread", thread(id))
        params["serviceTier"]?.let { put("serviceTier", it) }
    }

    private fun thread(id: String): JsonObject = buildJsonObject {
        put("cliVersion", "test")
        put("createdAt", 0)
        put("cwd", workspace.path)
        put("ephemeral", false)
        put("id", id)
        put("modelProvider", "openai")
        put("preview", "")
        put("sessionId", id)
        put("source", "cli")
        putJsonObject("status") { put("type", "idle") }
        putJsonArray("turns") {}
        put("updatedAt", 0)
    }

    private fun turn(id: String, status: String): JsonObject = buildJsonObject {
        put("id", id)
        put("items", buildJsonArray {})
        put("status", status)
    }

    private companion object {
        const val TURN_ID = "native-turn"
    }
}
