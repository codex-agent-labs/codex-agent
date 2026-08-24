import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexHost as CoreHost
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceStore
import io.github.codex_agent_labs.codexmobile.agent.PreparedCodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexJsonLine
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntimeEvent
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.yield
import kotlinx.coroutines.await
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject

class CodexNodeApiTest {
    @Test
    fun projectsCanonicalLifecycleIdentityFailureAndOwnership() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val hostStates = mutableListOf<String>()
        val hostObservation = host.observeState { hostStates += it.status }

        yield()
        assertEquals(listOf("new"), hostStates)
        assertTrue(isFrozen(host.state))
        assertEquals(0, enumerablePropertyCount(host))
        host.start().await()
        yield()
        assertEquals("ready", host.state.status)
        assertEquals("ready", hostStates.last())

        val agent = assertIs<CodexAgent>(host.agent)
        assertSame(agent, host.state.agent)
        val active = mutableListOf<CodexConversation?>()
        val activeObservation = agent.observeActiveConversation { active += it }
        awaitCondition { active.isNotEmpty() }
        assertNull(active.single())

        val conversation = agent.openConversation().await()
        awaitCondition { active.lastOrNull() != null }
        assertSame(conversation, agent.activeConversation)
        assertSame(conversation, active.last())
        assertEquals("ready", conversation.state.status)
        assertEquals("thread-js", conversation.state.conversationId)
        assertFalse(conversation.state.isTurnActive)
        assertTrue(isFrozen(conversation.state))
        assertTrue(isFrozen(conversation.state.messages))
        assertEquals(0, enumerablePropertyCount(conversation))

        val conversationStates = mutableListOf<String>()
        val conversationObservation = conversation.observeState { conversationStates += it.status }
        awaitCondition { conversationStates.isNotEmpty() }
        assertEquals(listOf("ready"), conversationStates)

        val failure = runCatching { conversation.runShellCommand("pwd").await() }.exceptionOrNull()
        val codexError = assertIs<CodexError>(failure)
        assertEquals("CodexError", codexError.asDynamic().name as String)
        assertEquals("unsupported_feature", codexError.code)
        assertFalse(codexError.recoverable)

        conversation.dispose().await()
        awaitCondition { conversationObservation.isClosed }
        assertEquals("closed", conversationStates.last())
        assertTrue(conversationObservation.isClosed)
        assertNull(agent.activeConversation)

        host.close().await()
        host.close().await()
        awaitCondition { hostObservation.isClosed && activeObservation.isClosed }
        assertEquals("closed", hostStates.last())
        assertTrue(hostObservation.isClosed)
        assertTrue(activeObservation.isClosed)
        assertTrue(runtime.closed)
    }

    @Test
    fun abortsBeforeStartingAndStopsDisposedObservation() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val values = mutableListOf<String>()
        val observation = host.observeState { values += it.status }
        yield()
        observation.dispose()
        observation.dispose()

        val controller = js("new AbortController()")
        controller.abort()
        val error = runCatching {
            host.start(controller.signal.unsafeCast<AbortSignal>()).await()
        }.exceptionOrNull()
        assertEquals("AbortError", error?.asDynamic()?.name as String)
        assertEquals("new", host.state.status)
        assertEquals(listOf("new"), values)
        assertTrue(observation.isClosed)
        assertFalse(runtime.started)
        host.close().await()
        yield()
        assertEquals(listOf("new"), values)
    }

    @Test
    fun mapsCanonicalCancellationAndRemovesAbortListener() = runTest {
        val restoreEntered = CompletableDeferred<Unit>()
        val restoreRelease = CompletableDeferred<Unit>()
        val runtime = ApiTestRuntime()
        val core = CoreHost(
            ApiTestPlatform(runtime, restoreEntered, restoreRelease),
            CodexClientInfo("node_test", "Node Test", "test"),
        )
        val host = wrapCodexHost(core)
        val signal = CountingAbortSignal()

        val start = host.start(signal)
        restoreEntered.await()
        val close = host.close()
        restoreRelease.complete(Unit)

        val error = runCatching { start.await() }.exceptionOrNull()
        assertEquals("AbortError", error?.asDynamic()?.name as String)
        close.await()
        assertEquals("closed", host.state.status)
        assertEquals(1, signal.additions)
        assertEquals(1, signal.removals)
        assertFalse(runtime.started)
    }

    @Test
    fun isolatesListenerFailureWhileOtherObserversAndCleanupContinue() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        val console = js("globalThis.console")
        val originalConsoleError = console.error
        val reported = mutableListOf<Throwable>()
        console.error = { error: Throwable -> reported += error }
        try {
            val failedObservation = host.observeState { error("listener failed") }
            val states = mutableListOf<String>()
            val healthyObservation = host.observeState { states += it.status }
            awaitCondition { failedObservation.isClosed && reported.size == 1 && states.isNotEmpty() }

            host.start().await()
            awaitCondition { states.lastOrNull() == "ready" }
            host.close().await()
            awaitCondition { healthyObservation.isClosed }

            assertEquals("new", states.first())
            assertTrue("ready" in states)
            assertEquals("closed", states.last())
            assertEquals("listener failed", reported.single().message)
            assertTrue(runtime.closed)
        } finally {
            console.error = originalConsoleError
            host.close().await()
        }
    }
}

private suspend fun awaitCondition(condition: () -> Boolean) {
    repeat(100) {
        if (condition()) return
        yield()
    }
    assertTrue(condition(), "Condition did not become true")
}

private class ApiTestPlatform(
    private val runtime: ApiTestRuntime,
    private val restoreEntered: CompletableDeferred<Unit>? = null,
    private val restoreRelease: CompletableDeferred<Unit>? = null,
) : CodexPlatform {
    override val authorizationBrowser: CodexAuthorizationBrowser =
        CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
    override val workspaceStore: CodexWorkspaceStore = object : CodexWorkspaceStore {
        override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution =
            CodexWorkspaceResolution.Available(CodexWorkspace("/workspace"))

        override suspend fun restore(): CodexWorkspaceResolution {
            restoreEntered?.complete(Unit)
            restoreRelease?.await()
            return CodexWorkspaceResolution.Available(CodexWorkspace("/workspace"))
        }

        override suspend fun clear(): Unit = Unit
    }

    override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime = PreparedCodexRuntime(
        runtimeFactory = { runtime },
        workspacePath = workspace.path,
        features = emptySet<CodexRuntimeFeature>(),
    )
}

private class CountingAbortSignal : AbortSignal {
    override val aborted: Boolean = false
    var additions: Int = 0
    var removals: Int = 0
    private var listener: (() -> Unit)? = null

    override fun addEventListener(type: String, listener: () -> Unit): Unit {
        assertEquals("abort", type)
        additions += 1
        this.listener = listener
    }

    override fun removeEventListener(type: String, listener: () -> Unit): Unit {
        assertEquals("abort", type)
        assertSame(this.listener, listener)
        removals += 1
        this.listener = null
    }
}

private fun isFrozen(value: Any): Boolean = js("Object.isFrozen(value)")

private fun enumerablePropertyCount(value: Any): Int = js("Object.keys(value).length")

private class ApiTestRuntime : CodexRuntime {
    private val eventChannel = Channel<CodexRuntimeEvent>(Channel.UNLIMITED)
    override val events: Flow<CodexRuntimeEvent> = eventChannel.receiveAsFlow()
    var started: Boolean = false
    var closed: Boolean = false

    override suspend fun start(): Unit {
        started = true
    }

    override suspend fun send(line: CodexJsonLine): Unit {
        val request = Json.parseToJsonElement(line.value).jsonObject
        val id = request["id"]?.jsonPrimitive?.long ?: return
        val result = when (request["method"]?.jsonPrimitive?.content) {
            "initialize" -> initializeResult()
            "thread/start" -> threadStartResult()
            else -> buildJsonObject {}
        }
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("id", id)
                put("result", result)
            }.toString(),
        )))
    }

    override fun close(): Unit {
        closed = true
        eventChannel.close()
    }
}

private fun initializeResult(): JsonObject = buildJsonObject {
    put("codexHome", "/tmp/codex")
    put("platformFamily", "unix")
    put("platformOs", "node")
    put("userAgent", "test")
}

private fun threadStartResult(): JsonObject = buildJsonObject {
    putJsonObject("thread") {
        put("id", "thread-js")
        put("cliVersion", "0.149.0")
        put("createdAt", 0)
        put("cwd", "/workspace")
        put("ephemeral", false)
        put("modelProvider", "openai")
        put("preview", "")
        put("conversationId", "thread-js")
        put("sessionId", "thread-js")
        put("source", "cli")
        putJsonObject("status") { put("type", "idle") }
        putJsonArray("turns") {}
        put("updatedAt", 0)
    }
    put("approvalPolicy", "on-request")
    put("approvalsReviewer", "user")
    put("cwd", "/workspace")
    put("model", "test")
    put("modelProvider", "openai")
    putJsonObject("sandbox") { put("type", "dangerFullAccess") }
}
