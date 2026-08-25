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
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonArray
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
        assertTrue(conversation.state.messages.isEmpty())
        assertNull(conversation.state.turnProgress)
        assertTrue(conversation.state.canStartTurn)
        assertTrue(conversation.state.canReload)
        assertFalse(conversation.state.canCancelTurn)
        assertFalse(conversation.state.canRunShellCommand)
        assertFalse(conversation.state.isTurnActive)
        assertTrue(isFrozen(conversation.state))
        assertTrue(isFrozen(conversation.state.messages))
        assertEquals(0, enumerablePropertyCount(conversation))

        val conversationStates = mutableListOf<CodexConversationState>()
        val conversationObservation = conversation.observeState { conversationStates += it }
        awaitCondition { conversationStates.isNotEmpty() }
        assertEquals(listOf("ready"), conversationStates.map(CodexConversationState::status))

        conversation.send("hello").await()
        awaitCondition { conversation.state.status == "running_turn" }
        val activeState = conversation.state
        assertEquals(listOf("hello"), activeState.messages.map(CodexMessage::text))
        assertNull(activeState.turnProgress)
        assertFalse(activeState.canStartTurn)
        assertFalse(activeState.canReload)
        assertTrue(activeState.canCancelTurn)
        assertFalse(activeState.canRunShellCommand)
        assertTrue(activeState.isTurnActive)

        runtime.emitAgentMessageDelta("working")
        awaitCondition {
            conversation.state.turnProgress?.text == "working" &&
                conversationStates.any { it.turnProgress?.text == "working" }
        }
        val progressState = conversation.state
        assertEquals("working", progressState.turnProgress?.text)
        val textProgress = checkNotNull(progressState.turnProgress)
        assertNull(textProgress.planProgress)
        assertTrue(textProgress.hookActivities.isEmpty())
        assertTrue(isFrozen(textProgress))
        assertTrue(isFrozen(textProgress.hookActivities))

        runtime.emitPlanUpdated()
        awaitCondition {
            conversation.state.turnProgress?.planProgress?.steps?.singleOrNull()?.status == "in_progress"
        }
        val planProgress = checkNotNull(checkNotNull(conversation.state.turnProgress).planProgress)
        assertEquals("Executing the plan", planProgress.explanation)
        assertEquals(listOf("Inspect runtime"), planProgress.steps.map(AgentPlanStep::text))
        assertEquals(listOf("in_progress"), planProgress.steps.map(AgentPlanStep::status))
        assertTrue(isFrozen(planProgress))
        assertTrue(isFrozen(planProgress.steps))
        planProgress.steps.forEach { assertTrue(isFrozen(it)) }

        runtime.emitHookStarted()
        awaitCondition {
            conversation.state.turnProgress?.hookActivities?.singleOrNull()?.status == "running"
        }
        val runningHook = checkNotNull(conversation.state.turnProgress).hookActivities.single()
        assertEquals("hook-js", runningHook.id)
        assertEquals("STOP", runningHook.eventName)
        assertEquals("COMMAND", runningHook.handlerType)
        assertEquals("Running hook", runningHook.statusMessage)
        assertEquals(listOf("started"), runningHook.details.toList())
        assertTrue(isFrozen(runningHook))
        assertTrue(isFrozen(runningHook.details))

        runtime.emitHookCompleted()
        awaitCondition {
            conversation.state.turnProgress?.hookActivities?.singleOrNull()?.status == "completed"
        }
        val completedHook = checkNotNull(conversation.state.turnProgress).hookActivities.single()
        assertEquals("Complete", completedHook.statusMessage)
        assertEquals(listOf("finished", "detached"), completedHook.details.toList())
        assertEquals("running", runningHook.status)
        assertEquals(listOf("started"), runningHook.details.toList())
        assertTrue(isFrozen(completedHook))
        assertTrue(isFrozen(completedHook.details))

        runtime.completeTurn()
        awaitCondition { conversation.state.status == "ready" && conversation.state.messages.size == 2 }
        awaitCondition { conversationStates.any { it.messages.size == 2 && !it.isTurnActive } }
        val messageState = conversation.state
        val messages = messageState.messages
        assertEquals(listOf("user-1", "assistant-1"), messages.map(CodexMessage::id))
        assertEquals(listOf("hello", "world"), messages.map(CodexMessage::text))
        assertEquals(listOf("user", "assistant"), messages.map(CodexMessage::role))
        assertNull(messageState.turnProgress)
        assertTrue(messageState.canStartTurn)
        assertTrue(messageState.canReload)
        assertFalse(messageState.canCancelTurn)
        assertFalse(messageState.canRunShellCommand)
        assertFalse(messageState.isTurnActive)
        assertTrue(isFrozen(messageState))
        assertTrue(isFrozen(messages))
        messages.forEach { assertTrue(isFrozen(it)) }
        assertTrue(conversationStates.any { it.isTurnActive && it.canCancelTurn })
        assertTrue(conversationStates.any { it.turnProgress?.text == "working" })
        assertTrue(conversationStates.any { it.messages.size == 2 && !it.isTurnActive })
        conversationStates.forEach {
            assertTrue(isFrozen(it))
            assertTrue(isFrozen(it.messages))
            it.turnProgress?.let { progress ->
                assertTrue(isFrozen(progress))
                assertTrue(isFrozen(progress.hookActivities))
                progress.hookActivities.forEach { activity ->
                    assertTrue(isFrozen(activity))
                    assertTrue(isFrozen(activity.details))
                }
                progress.planProgress?.let { plan ->
                    assertTrue(isFrozen(plan))
                    assertTrue(isFrozen(plan.steps))
                    plan.steps.forEach { step -> assertTrue(isFrozen(step)) }
                }
            }
        }

        val failure = runCatching { conversation.runShellCommand("pwd").await() }.exceptionOrNull()
        val codexError = assertIs<CodexError>(failure)
        assertEquals("CodexError", codexError.asDynamic().name as String)
        assertEquals("unsupported_feature", codexError.code)
        assertFalse(codexError.recoverable)

        val blankName = runCatching { agent.rename("thread-history", "  ").await() }.exceptionOrNull()
        assertEquals("Conversation name must not be blank", blankName?.message)
        val blankId = runCatching { agent.delete("  ").await() }.exceptionOrNull()
        assertEquals("Conversation ID must not be blank", blankId?.message)
        assertNull(runtime.renamedConversationId)
        assertNull(runtime.deletedConversationId)

        agent.rename("thread-history", "  Useful name  ").await()
        assertEquals("thread-history", runtime.renamedConversationId)
        assertEquals("Useful name", runtime.renamedConversationName)

        runtime.failNextRename = true
        val renameFailure = runCatching { agent.rename("thread-history", "Rejected").await() }.exceptionOrNull()
        val renameError = assertIs<CodexError>(renameFailure)
        assertEquals("conversation_rename_failed", renameError.code)
        assertEquals("rename denied", renameError.message)
        assertTrue(renameError.recoverable)

        val deleteEntered = CompletableDeferred<Unit>()
        val deleteRelease = CompletableDeferred<Unit>()
        runtime.deleteEntered = deleteEntered
        runtime.deleteRelease = deleteRelease
        val deletion = agent.delete("thread-js")
        try {
            deleteEntered.await()
            assertEquals("closed", conversation.state.status)
            assertNull(agent.activeConversation)
            assertEquals("thread-js", runtime.deletedConversationId)
        } finally {
            deleteRelease.complete(Unit)
        }
        deletion.await()
        conversation.dispose().await()
        awaitCondition { conversationObservation.isClosed }
        assertEquals("closed", conversationStates.last().status)
        assertTrue(conversationObservation.isClosed)
        assertNull(agent.activeConversation)

        host.close().await()
        host.close().await()
        awaitCondition { hostObservation.isClosed && activeObservation.isClosed }
        assertEquals("closed", hostStates.last())
        assertTrue(hostObservation.isClosed)
        assertTrue(activeObservation.isClosed)
        assertTrue(runtime.closed)

        val shellRuntime = ApiTestRuntime()
        val shellHost = wrapCodexHost(CoreHost(
            ApiTestPlatform(shellRuntime, features = setOf(CodexRuntimeFeature.SHELL_COMMANDS)),
            CodexClientInfo("node_test", "Node Test", "test"),
        ))
        try {
            shellHost.start().await()
            val shellConversation = assertIs<CodexAgent>(shellHost.agent).openConversation().await()
            val shellAvailability = mutableListOf<Boolean>()
            shellConversation.observeState { shellAvailability += it.canRunShellCommand }
            awaitCondition { shellAvailability.lastOrNull() == true }
            assertTrue(shellConversation.state.canRunShellCommand)

            shellConversation.send("hello").await()
            awaitCondition {
                !shellConversation.state.canRunShellCommand && shellAvailability.lastOrNull() == false
            }
            shellRuntime.completeTurn()
            awaitCondition {
                shellConversation.state.status == "ready" && shellConversation.state.canRunShellCommand &&
                    shellAvailability.lastOrNull() == true
            }
            assertTrue(shellAvailability.first())
            assertTrue(false in shellAvailability)
            assertTrue(shellAvailability.last())
        } finally {
            shellHost.close().await()
        }
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

    @Test
    fun projectsAuthenticationStateMethodsIdentityAndDisposal() = runTest {
        val runtime = ApiTestRuntime()
        val core = CoreHost(ApiTestPlatform(runtime), CodexClientInfo("node_test", "Node Test", "test"))
        val host = wrapCodexHost(core)
        host.start().await()
        val agent = assertIs<CodexAgent>(host.agent)
        val authentication = agent.authentication

        assertSame(authentication, agent.authentication)
        assertEquals(0, enumerablePropertyCount(authentication))
        assertEquals("signed_out", authentication.state.status)
        assertFalse(authentication.isAuthenticated)
        assertFalse(authentication.isAuthenticating)
        assertTrue(isFrozen(authentication.state))

        val states = mutableListOf<CodexAuthenticationState>()
        val authenticated = mutableListOf<Boolean>()
        val authenticating = mutableListOf<Boolean>()
        val stateObservation = authentication.observeState(states::add)
        val authenticatedObservation = authentication.observeAuthenticated(authenticated::add)
        val authenticatingObservation = authentication.observeAuthenticating(authenticating::add)
        val disposedStates = mutableListOf<String>()
        val disposedObservation = authentication.observeState { disposedStates += it.status }
        awaitCondition {
            states.isNotEmpty() && authenticated.isNotEmpty() &&
                authenticating.isNotEmpty() && disposedStates.isNotEmpty()
        }
        disposedObservation.dispose()

        authentication.authenticate("chatgpt_browser").await()
        awaitCondition {
            states.lastOrNull()?.pendingSignInUrl == "https://auth.openai.com/oauth?state=login-1" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        assertEquals("https://auth.openai.com/oauth?state=login-1", authentication.state.pendingSignInUrl)
        assertEquals("authenticating", states.last().status)
        assertTrue(authentication.isAuthenticating)

        authentication.cancel().await()
        awaitCondition {
            states.lastOrNull()?.failure?.code == "authentication_failed" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }
        assertEquals("signed_out", authentication.state.status)
        assertEquals("authentication_failed", authentication.state.failure?.code)
        assertEquals("signed_out", states.last().status)
        assertTrue(isFrozen(checkNotNull(authentication.state.failure)))
        assertEquals(1, runtime.cancelRequests)

        authentication.authenticate("chatgpt_device_code").await()
        awaitCondition {
            states.lastOrNull()?.deviceUserCode == "ABCD-EFGH" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == true
        }
        assertEquals("authenticating", authentication.state.status)
        assertEquals("https://auth.openai.com/device", authentication.state.deviceVerificationUrl)
        assertEquals("ABCD-EFGH", authentication.state.deviceUserCode)
        assertEquals("https://auth.openai.com/device", states.last().deviceVerificationUrl)
        authentication.cancel().await()
        awaitCondition {
            states.lastOrNull()?.status == "signed_out" &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }

        authentication.authenticate("api_key", "sk-js-test").await()
        awaitCondition {
            states.lastOrNull()?.status == "authenticated" &&
                authenticated.lastOrNull() == true && authenticating.lastOrNull() == false
        }
        assertEquals("authenticated", authentication.state.status)
        assertEquals("sk-js-test", runtime.apiKey)

        authentication.signOut().await()
        awaitCondition {
            states.lastOrNull()?.let { it.status == "signed_out" && it.failure == null } == true &&
                authenticated.lastOrNull() == false && authenticating.lastOrNull() == false
        }
        assertEquals(1, runtime.logoutRequests)
        assertEquals(listOf("signed_out"), disposedStates)

        host.close().await()
        awaitCondition {
            stateObservation.isClosed && authenticatedObservation.isClosed && authenticatingObservation.isClosed
        }
    }

    @Test
    fun mapsAuthenticationFailureAndAbortSignalCancellation() = runTest {
        val failedRuntime = ApiTestRuntime().apply { failNextAccountRead = true }
        val failedHost = wrapCodexHost(
            CoreHost(ApiTestPlatform(failedRuntime), CodexClientInfo("node_test", "Node Test", "test")),
        )
        failedHost.start().await()
        val failedAuthentication = assertIs<CodexAgent>(failedHost.agent).authentication
        val failure = runCatching { failedAuthentication.authenticate().await() }.exceptionOrNull()
        val codexError = assertIs<CodexError>(failure)
        assertEquals("authentication_failed", codexError.code)
        assertTrue(codexError.recoverable)
        assertEquals("authentication denied", codexError.message)
        assertEquals("authentication_failed", failedAuthentication.state.failure?.code)
        assertTrue(isFrozen(failedAuthentication.state))
        failedHost.close().await()

        val readEntered = CompletableDeferred<Unit>()
        val readRelease = CompletableDeferred<Unit>()
        val cancelledRuntime = ApiTestRuntime().apply {
            accountReadEntered = readEntered
            accountReadRelease = readRelease
        }
        val cancelledHost = wrapCodexHost(
            CoreHost(ApiTestPlatform(cancelledRuntime), CodexClientInfo("node_test", "Node Test", "test")),
        )
        cancelledHost.start().await()
        val cancelledAuthentication = assertIs<CodexAgent>(cancelledHost.agent).authentication
        val controller = js("new AbortController()")
        val operation = cancelledAuthentication.authenticate(
            signal = controller.signal.unsafeCast<AbortSignal>(),
        )
        readEntered.await()
        controller.abort()
        readRelease.complete(Unit)

        val abort = runCatching { operation.await() }.exceptionOrNull()
        assertEquals("AbortError", abort?.asDynamic()?.name as String)
        awaitCondition { cancelledAuthentication.state.status == "signed_out" }
        assertFalse(cancelledAuthentication.isAuthenticating)
        cancelledHost.close().await()
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
    private val features: Set<CodexRuntimeFeature> = emptySet(),
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
        features = features,
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
    var failNextAccountRead: Boolean = false
    var accountReadEntered: CompletableDeferred<Unit>? = null
    var accountReadRelease: CompletableDeferred<Unit>? = null
    var apiKey: String? = null
    var cancelRequests: Int = 0
    var logoutRequests: Int = 0
    var renamedConversationId: String? = null
    var renamedConversationName: String? = null
    var deletedConversationId: String? = null
    var failNextRename: Boolean = false
    var deleteEntered: CompletableDeferred<Unit>? = null
    var deleteRelease: CompletableDeferred<Unit>? = null
    private var loginAttempts: Int = 0

    suspend fun completeTurn(): Unit = notify("turn/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turn", completedTurn())
    })

    suspend fun emitAgentMessageDelta(text: String): Unit = notify("item/agentMessage/delta", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("itemId", "assistant-live")
        put("delta", text)
    })

    suspend fun emitPlanUpdated(): Unit = notify("turn/plan/updated", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("explanation", "Executing the plan")
        putJsonArray("plan") {
            add(buildJsonObject {
                put("step", "Inspect runtime")
                put("status", "inProgress")
            })
        }
    })

    suspend fun emitHookStarted(): Unit = notify("hook/started", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("run", hookRun("running", "Running hook", listOf("started")))
    })

    suspend fun emitHookCompleted(): Unit = notify("hook/completed", buildJsonObject {
        put("threadId", "thread-js")
        put("turnId", "turn-js")
        put("run", hookRun("completed", "Complete", listOf("finished", "detached")))
    })

    override suspend fun start(): Unit {
        started = true
    }

    override suspend fun send(line: CodexJsonLine): Unit {
        val request = Json.parseToJsonElement(line.value).jsonObject
        val id = request["id"]?.jsonPrimitive?.long ?: return
        when (request["method"]?.jsonPrimitive?.content) {
            "initialize" -> respond(id, initializeResult())
            "thread/start" -> respond(id, threadStartResult())
            "thread/read" -> respond(id, threadReadResult())
            "thread/name/set" -> {
                val params = checkNotNull(request["params"]).jsonObject
                renamedConversationId = params["threadId"]?.jsonPrimitive?.content
                renamedConversationName = params["name"]?.jsonPrimitive?.content
                if (failNextRename) {
                    failNextRename = false
                    respondError(id, "rename denied")
                } else {
                    respond(id, buildJsonObject {})
                }
            }
            "thread/delete" -> {
                deletedConversationId = checkNotNull(request["params"])
                    .jsonObject["threadId"]?.jsonPrimitive?.content
                deleteEntered?.complete(Unit)
                deleteRelease?.await()
                respond(id, buildJsonObject {})
            }
            "turn/start" -> respond(id, turnStartResult())
            "account/read" -> {
                accountReadEntered?.complete(Unit)
                accountReadRelease?.await()
                if (failNextAccountRead) {
                    failNextAccountRead = false
                    respondError(id, "authentication denied")
                } else {
                    respond(id, buildJsonObject {
                        put("account", JsonNull)
                        put("requiresOpenaiAuth", true)
                    })
                }
            }
            "account/login/start" -> {
                val params = checkNotNull(request["params"]).jsonObject
                when (params["type"]?.jsonPrimitive?.content) {
                    "chatgpt" -> respond(id, buildJsonObject {
                        put("type", "chatgpt")
                        put("loginId", "login-${++loginAttempts}")
                        put("authUrl", "https://auth.openai.com/oauth?state=login-$loginAttempts")
                    })
                    "chatgptDeviceCode" -> respond(id, buildJsonObject {
                        put("type", "chatgptDeviceCode")
                        put("loginId", "login-${++loginAttempts}")
                        put("userCode", "ABCD-EFGH")
                        put("verificationUrl", "https://auth.openai.com/device")
                    })
                    "apiKey" -> {
                        apiKey = params["apiKey"]?.jsonPrimitive?.content
                        respond(id, buildJsonObject { put("type", "apiKey") })
                    }
                    else -> error("Unexpected authentication method")
                }
            }
            "account/login/cancel" -> {
                cancelRequests += 1
                val loginId = checkNotNull(request["params"]).jsonObject["loginId"]!!.jsonPrimitive.content
                notify("account/login/completed", buildJsonObject {
                    put("loginId", loginId)
                    put("success", false)
                    put("error", "cancelled")
                })
                respond(id, buildJsonObject { put("status", "canceled") })
            }
            "account/logout" -> {
                logoutRequests += 1
                respond(id, buildJsonObject {})
            }
            else -> respond(id, buildJsonObject {})
        }
    }

    private suspend fun respond(id: Long, result: JsonObject): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("id", id)
                put("result", result)
            }.toString(),
        )))
    }

    private suspend fun respondError(id: Long, message: String): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("id", id)
                putJsonObject("error") {
                    put("code", -32000)
                    put("message", message)
                }
            }.toString(),
        )))
    }

    private suspend fun notify(method: String, params: JsonObject): Unit {
        eventChannel.send(CodexRuntimeEvent.Received(CodexJsonLine(
            buildJsonObject {
                put("method", method)
                put("params", params)
            }.toString(),
        )))
    }

    override fun close(): Unit {
        closed = true
        eventChannel.close()
    }
}

private fun hookRun(status: String, statusMessage: String, details: List<String>): JsonObject = buildJsonObject {
    put("displayOrder", 0)
    putJsonArray("entries") {
        details.forEach { detail ->
            add(buildJsonObject {
                put("kind", "context")
                put("text", detail)
            })
        }
    }
    put("eventName", "stop")
    put("executionMode", "sync")
    put("handlerType", "command")
    put("id", "hook-js")
    put("scope", "turn")
    put("sourcePath", "/workspace/.codex/hooks.json")
    put("startedAt", 0)
    put("status", status)
    put("statusMessage", statusMessage)
}

private fun initializeResult(): JsonObject = buildJsonObject {
    put("codexHome", "/tmp/codex")
    put("platformFamily", "unix")
    put("platformOs", "node")
    put("userAgent", "test")
}

private fun threadStartResult(): JsonObject = buildJsonObject {
    put("thread", threadResult())
    put("approvalPolicy", "on-request")
    put("approvalsReviewer", "user")
    put("cwd", "/workspace")
    put("model", "test")
    put("modelProvider", "openai")
    putJsonObject("sandbox") { put("type", "dangerFullAccess") }
}

private fun threadReadResult(): JsonObject = buildJsonObject {
    put("thread", threadResult(buildJsonArray { add(completedTurn()) }))
}

private fun threadResult(turns: JsonArray = buildJsonArray {}): JsonObject = buildJsonObject {
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
    put("turns", turns)
    put("updatedAt", 0)
}

private fun turnStartResult(): JsonObject = buildJsonObject {
    putJsonObject("turn") {
        put("id", "turn-js")
        putJsonArray("items") {}
        put("status", "inProgress")
    }
}

private fun completedTurn(): JsonObject = buildJsonObject {
    put("id", "turn-js")
    putJsonArray("items") {
        add(buildJsonObject {
            put("id", "user-1")
            put("type", "userMessage")
            putJsonArray("content") {
                add(buildJsonObject {
                    put("type", "text")
                    put("text", "hello")
                })
            }
        })
        add(buildJsonObject {
            put("id", "assistant-1")
            put("type", "agentMessage")
            put("text", "world")
        })
    }
    put("status", "completed")
}
