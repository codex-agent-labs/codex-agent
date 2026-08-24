package io.github.codex_agent_labs.codexmobile.agent

import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

class IntegrationAuthorizationControllerTest {
    @Test
    fun publicFacadeAuthorizesConnectorAndMcpTargetsThroughOneActiveProjection(): Unit = runBlocking {
        val connectorAccessible = AtomicBoolean(false)
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "app/list" -> server.respond(message.id, connectorList(connectorAccessible.get()))
                "mcpServer/oauth/login" -> server.respond(message.id, buildJsonObject {
                    put("authorizationUrl", "https://accounts.example.com/oauth/drive-mcp")
                })
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        var closed = 0
        val agent = CodexAgent(
            workspace = CodexWorkspace("/workspace"),
            workingDirectory = "/workspace",
            features = setOf(CodexRuntimeFeature.CONNECTORS, CodexRuntimeFeature.MCP_SERVERS),
            client = client,
            parentScope = this,
            authorizationBrowser = CodexAuthorizationBrowser {
                CodexAuthorizationPresentation { closed += 1 }
            },
        )
        try {
            agent.start()
            assertFalse(agent.integrationAuthorization.isAuthorizing.value)
            val connectorAuthorization = async {
                agent.integrationAuthorization.authorize(AgentIntegration.Connector(connector()))
            }
            withTimeout(1_000) {
                agent.integrationAuthorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertTrue(agent.integrationAuthorization.isAuthorizing.value)
            assertIs<AgentIntegration.Connector>(withTimeout(1_000) {
                agent.integrationAuthorization.active.first { it != null }
            })
            connectorAccessible.set(true)
            process.notify("app/list/updated", connectorList(isAccessible = true))
            connectorAuthorization.await()
            assertFalse(agent.integrationAuthorization.isAuthorizing.value)
            assertEquals(null, withTimeout(1_000) {
                agent.integrationAuthorization.active.first { it == null }
            })
            assertTrue(
                assertIs<AgentIntegration.Connector>(agent.integrationAuthorization.state.value.target)
                    .connector.isAccessible,
            )

            val mcp = mcpServer("drive-mcp")
            val mcpAuthorization = async {
                agent.integrationAuthorization.authorize(AgentIntegration.McpServer(mcp))
            }
            withTimeout(1_000) {
                agent.integrationAuthorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertTrue(agent.integrationAuthorization.isAuthorizing.value)
            assertEquals(
                mcp,
                assertIs<AgentIntegration.McpServer>(withTimeout(1_000) {
                    agent.integrationAuthorization.active.first { it != null }
                }).server,
            )
            process.notify("mcpServer/oauthLogin/completed", completion(mcp.name, success = true))
            mcpAuthorization.await()
            assertEquals(AgentIntegrationAuthorizationStatus.AUTHORIZED, agent.integrationAuthorization.state.value.status)
            assertFalse(agent.integrationAuthorization.isAuthorizing.value)
            assertEquals(null, withTimeout(1_000) {
                agent.integrationAuthorization.active.first { it == null }
            })
            assertEquals(2, closed)
        } finally {
            agent.close()
        }
    }

    @Test
    fun facadeCancelStopsAStartingRequestWithoutOpeningALateBrowser(): Unit = runBlocking {
        val requestId = CompletableDeferred<Long>()
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "mcpServer/oauth/login" -> requestId.complete(requireNotNull(message.id))
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 5_000)
        val opened = AtomicInteger()
        val agent = authorizationAgent(client, this) {
            opened.incrementAndGet()
            CodexAuthorizationPresentation.None
        }
        try {
            agent.start()
            val operation = async {
                agent.integrationAuthorization.authorize(AgentIntegration.McpServer(mcpServer("drive")))
            }
            val pendingRequestId = withTimeout(1_000) { requestId.await() }
            assertIs<AgentIntegration.McpServer>(agent.integrationAuthorization.active.value)
            assertTrue(agent.integrationAuthorization.isAuthorizing.value)

            agent.integrationAuthorization.cancel()
            operation.join()
            assertTrue(operation.isCancelled)
            assertEquals(AgentIntegrationAuthorizationStatus.IDLE, agent.integrationAuthorization.state.value.status)
            assertEquals(null, agent.integrationAuthorization.active.value)
            assertFalse(agent.integrationAuthorization.isAuthorizing.value)

            process.respond(pendingRequestId, buildJsonObject {
                put("authorizationUrl", "https://accounts.example.com/oauth/drive")
            })
            repeat(10) { yield() }
            assertEquals(0, opened.get())
        } finally {
            agent.close()
        }
    }

    @Test
    fun terminalPresentationCloseFailureFailsTheAuthorization(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = authorizationAgent(client, this) {
            CodexAuthorizationPresentation { error("terminal presentation close failed") }
        }
        try {
            agent.start()
            val operation = async {
                runCatching {
                    agent.integrationAuthorization.authorize(AgentIntegration.McpServer(mcpServer("drive")))
                }
            }
            withTimeout(1_000) {
                agent.integrationAuthorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }

            process.notify("mcpServer/oauthLogin/completed", completion("drive", success = true))
            val failure = assertIs<CodexOperationException>(operation.await().exceptionOrNull())
            assertEquals("terminal presentation close failed", failure.cause?.message)
            assertEquals(AgentIntegrationAuthorizationStatus.FAILED, agent.integrationAuthorization.state.value.status)
        } finally {
            agent.close()
        }
    }

    @Test
    fun cancelSurfacesPresentationCloseFailureAndStillCancelsTheAuthorization(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = authorizationAgent(client, this) {
            CodexAuthorizationPresentation { error("cancel presentation close failed") }
        }
        try {
            agent.start()
            val operation = async {
                agent.integrationAuthorization.authorize(AgentIntegration.McpServer(mcpServer("drive")))
            }
            withTimeout(1_000) {
                agent.integrationAuthorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }

            val failure = assertFailsWith<CodexOperationException> { agent.integrationAuthorization.cancel() }
            assertEquals("cancel presentation close failed", failure.cause?.message)
            operation.join()
            assertTrue(operation.isCancelled)
            assertEquals(AgentIntegrationAuthorizationStatus.IDLE, agent.integrationAuthorization.state.value.status)
        } finally {
            agent.close()
        }
    }

    @Test
    fun agentCloseClearsActiveAuthorizationAndPendingInteractionsEvenWhenPresentationCloseFails(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val agent = authorizationAgent(client, this) {
            CodexAuthorizationPresentation { error("close presentation failed") }
        }
        try {
            agent.start()
            agent.conversations.open()
            process.request(301, "item/commandExecution/requestApproval", buildJsonObject {
                put("itemId", "item-1")
                put("startedAtMs", 1)
                put("threadId", "thread-1")
                put("turnId", "turn-1")
                put("command", "git status")
                put("reason", "Inspect")
            })
            withTimeout(1_000) { agent.interactions.approvals.first { it.isNotEmpty() } }
            val operation = async {
                agent.integrationAuthorization.authorize(AgentIntegration.McpServer(mcpServer("drive")))
            }
            withTimeout(1_000) {
                agent.integrationAuthorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }

            val failure = assertFailsWith<CodexOperationException> { agent.close() }
            assertEquals("close presentation failed", failure.cause?.message)
            operation.join()
            assertTrue(operation.isCancelled)
            assertEquals(AgentIntegrationAuthorizationStatus.IDLE, agent.integrationAuthorization.state.value.status)
            assertEquals(null, agent.integrationAuthorization.active.value)
            assertTrue(agent.interactions.state.value.pending.isEmpty())
            assertTrue(agent.interactions.state.value.resolvingRequestIds.isEmpty())
            assertTrue(agent.interactions.approvals.value.isEmpty())
            assertTrue(agent.interactions.elicitations.value.isEmpty())
        } finally {
            runCatching { agent.close() }
        }
    }

    @Test
    fun accessibleConnectorAuthorizesWithoutOpeningTheBrowser(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "app/list" -> server.respond(message.id, connectorList(isAccessible = true))
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val browserOpens = AtomicInteger()
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser {
                browserOpens.incrementAndGet()
                CodexAuthorizationPresentation.None
            },
        )
        try {
            authorization.authorizeConnector(connector(), null)

            assertEquals(AgentIntegrationAuthorizationStatus.AUTHORIZED, authorization.state.value.status)
            val target = assertIs<AgentIntegration.Connector>(authorization.state.value.target)
            assertEquals("Drive", target.connector.name)
            assertTrue(target.connector.isAccessible)
            assertEquals(0, browserOpens.get())
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun connectorWithoutAnAuthorizationUrlFailsClearly(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "app/list" -> server.respond(
                    message.id,
                    connectorList(isAccessible = false, includeInstallUrl = false),
                )
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        try {
            assertFailsWith<CodexOperationException> { authorization.authorizeConnector(connector(), null) }

            assertEquals(AgentIntegrationAuthorizationStatus.FAILED, authorization.state.value.status)
            assertEquals("Connector authorization failed", authorization.state.value.failure?.message)
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun connectorRefreshCompletesAuthorizationAndCancelIsIdempotent(): Unit = runBlocking {
        val accessible = AtomicBoolean(false)
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "app/list" -> server.respond(message.id, connectorList(accessible.get()))
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val opened = AtomicInteger()
        val closed = AtomicInteger()
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser {
                opened.incrementAndGet()
                CodexAuthorizationPresentation { closed.incrementAndGet() }
            },
        )
        try {
            val firstAuthorization = async {
                authorization.authorizeConnector(connector(), ConversationId("thread-1"))
            }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertEquals(1, opened.get())

            accessible.set(true)
            process.notify("app/list/updated", connectorList(isAccessible = true))
            firstAuthorization.await()
            assertEquals(AgentIntegrationAuthorizationStatus.AUTHORIZED, authorization.state.value.status)
            assertIs<AgentIntegration.Connector>(authorization.state.value.target)
            assertEquals(1, closed.get())

            accessible.set(false)
            val secondAuthorization = async { authorization.authorizeConnector(connector(), null) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertEquals(2, opened.get())
            authorization.cancel()
            authorization.cancel()
            secondAuthorization.join()
            assertEquals(AgentIntegrationAuthorizationStatus.IDLE, authorization.state.value.status)
            assertTrue(secondAuthorization.isCancelled)
            assertEquals(2, closed.get())
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun connectorBrowserFailureReleasesTheAttemptAsFailed(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "app/list" -> server.respond(message.id, connectorList(isAccessible = false))
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { error("browser failed") },
        )
        try {
            assertFailsWith<CodexOperationException> { authorization.authorizeConnector(connector(), null) }
            assertEquals(AgentIntegrationAuthorizationStatus.FAILED, authorization.state.value.status)
            assertEquals("Could not open the authorization URL", authorization.state.value.failure?.message)
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun callerCancellationFailsAndReleasesTheActiveAuthorization(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "mcpServer/oauth/login" -> Unit
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 5_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        try {
            val operation = async { authorization.authorizeMcpServer(mcpServer("drive")) }
            withTimeout(1_000) {
                authorization.state.first { it.status == AgentIntegrationAuthorizationStatus.STARTING }
            }
            operation.cancelAndJoin()

            assertEquals(AgentIntegrationAuthorizationStatus.IDLE, authorization.state.value.status)
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun cancelBeforeMcpRequestEnqueueDoesNotBlockSameKeyRetry(): Unit = runBlocking {
        val initializationStarted = CompletableDeferred<Unit>()
        val blockedStartup = FakeCodexRuntime { message, _ ->
            if (message.method == "initialize") initializationStarted.complete(Unit)
        }
        val readyRuntime = oauthRuntime()
        val runtimes = ArrayDeque<FakeCodexRuntime>().apply {
            add(blockedStartup)
            add(readyRuntime)
        }
        val client = CodexAgentClient({ runtimes.removeFirst() }, requestTimeoutMillis = 5_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        val drive = mcpServer("drive")
        try {
            val cancelled = async { authorization.authorizeMcpServer(drive) }
            withTimeout(1_000) { initializationStarted.await() }
            authorization.cancel()
            cancelled.join()
            assertTrue(cancelled.isCancelled)

            val retry = async { authorization.authorizeMcpServer(drive) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            readyRuntime.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true),
            )
            retry.await()
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun cancelAtTheMcpEnqueueBoundaryBlocksRetryUntilTheStaleTerminal(): Unit = runBlocking {
        val initialize = CompletableDeferred<Pair<Long, FakeCodexRuntime>>()
        val requests = Channel<Pair<Long, FakeCodexRuntime>>(Channel.UNLIMITED)
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> initialize.complete(checkNotNull(message.id) to server)
                "mcpServer/oauth/login" -> requests.trySend(checkNotNull(message.id) to server)
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 5_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        val drive = mcpServer("drive")
        val conversationId = ConversationId("thread-boundary")
        val controllerLock = authorization.controllerLock()
        var lockHeld = false
        try {
            val cancelled = async { authorization.authorizeMcpServer(drive, conversationId) }
            val (initializeId, initializeServer) = withTimeout(1_000) { initialize.await() }

            controllerLock.lock()
            lockHeld = true
            val cancelling = async(start = CoroutineStart.UNDISPATCHED) { authorization.cancel() }
            val earlyRetry = async(start = CoroutineStart.UNDISPATCHED) {
                runCatching { authorization.authorizeMcpServer(drive, conversationId) }
            }
            initializeServer.respond(initializeId, buildJsonObject {})
            withTimeout(1_000) { requests.receive() }

            controllerLock.unlock()
            lockHeld = false
            cancelling.await()
            cancelled.join()
            assertTrue(cancelled.isCancelled)
            val rejection = assertIs<IllegalStateException>(earlyRetry.await().exceptionOrNull())
            assertTrue("awaiting its terminal notification" in rejection.message.orEmpty())

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = false, error = "stale", threadId = conversationId.value),
            )
            authorization.awaitNoPendingMcpTerminal(drive.name, conversationId)

            val retry = async { authorization.authorizeMcpServer(drive, conversationId) }
            val (retryId, retryServer) = withTimeout(1_000) { requests.receive() }
            retryServer.respond(retryId, buildJsonObject {
                put("authorizationUrl", "https://accounts.example.com/oauth/drive")
            })
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            retry.await()
        } finally {
            if (lockHeld) controllerLock.unlock()
            authorization.close()
            client.close()
        }
    }

    @Test
    fun browserFailureBlocksSameKeyRetryUntilTheStartedAttemptCompletes(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val browserOpens = AtomicInteger()
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser {
                if (browserOpens.incrementAndGet() == 1) error("browser failed")
                CodexAuthorizationPresentation.None
            },
        )
        val conversationId = ConversationId("thread-1")
        val drive = mcpServer("drive")
        try {
            val failure = assertFailsWith<CodexOperationException> {
                authorization.authorizeMcpServer(drive, conversationId)
            }
            assertEquals("browser failed", failure.cause?.message)

            val rejection = assertFailsWith<IllegalStateException> {
                authorization.authorizeMcpServer(drive, conversationId)
            }
            assertTrue("awaiting its terminal notification" in rejection.message.orEmpty())

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = false, error = "stale", threadId = conversationId.value),
            )
            authorization.awaitNoPendingMcpTerminal(drive.name, conversationId)

            val retry = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) {
                authorization.state.first { it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION }
            }
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            retry.await()
            assertEquals(2, browserOpens.get())
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun cancelAfterMcpStartupIsIssuedBlocksSameKeyRetryUntilItsTerminal(): Unit = runBlocking {
        val requests = Channel<Pair<Long, FakeCodexRuntime>>(Channel.UNLIMITED)
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "mcpServer/oauth/login" -> requests.trySend(checkNotNull(message.id) to server)
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 5_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        val conversationId = ConversationId("thread-1")
        val drive = mcpServer("drive")
        try {
            val cancelled = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) { requests.receive() }
            authorization.cancel()
            cancelled.join()
            assertTrue(cancelled.isCancelled)

            val rejection = assertFailsWith<IllegalStateException> {
                authorization.authorizeMcpServer(drive, conversationId)
            }
            assertTrue("awaiting its terminal notification" in rejection.message.orEmpty())

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = false, error = "stale", threadId = conversationId.value),
            )
            repeat(10) { yield() }

            val retry = async { authorization.authorizeMcpServer(drive, conversationId) }
            val (retryRequestId, retryServer) = withTimeout(1_000) { requests.receive() }
            retryServer.respond(retryRequestId, buildJsonObject {
                put("authorizationUrl", "https://accounts.example.com/oauth/drive")
            })
            withTimeout(1_000) {
                authorization.state.first { it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION }
            }

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            retry.await()
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun cancelledMcpAttemptBlocksOnlyItsKeyUntilTheStaleTerminalEventIsConsumed(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        val conversationId = ConversationId("thread-1")
        val drive = mcpServer("drive")
        try {
            val cancelled = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) {
                authorization.state.first { it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION }
            }
            authorization.cancel()
            cancelled.join()
            assertTrue(cancelled.isCancelled)

            val rejection = assertFailsWith<IllegalStateException> {
                authorization.authorizeMcpServer(drive, conversationId)
            }
            assertTrue("awaiting its terminal notification" in rejection.message.orEmpty())

            val calendar = mcpServer("calendar")
            val otherTarget = async { authorization.authorizeMcpServer(calendar, conversationId) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION &&
                        (it.target as? AgentIntegration.McpServer)?.server?.name == calendar.name
                }
            }
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = false, error = "stale", threadId = conversationId.value),
            )
            repeat(10) { yield() }
            assertEquals(AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION, authorization.state.value.status)
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(calendar.name, success = true, threadId = conversationId.value),
            )
            otherTarget.await()

            val retry = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION &&
                        (it.target as? AgentIntegration.McpServer)?.server?.name == drive.name
                }
            }
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            retry.await()
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun mcpCompletionFromTheWrongThreadIsIgnored(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        )
        val conversationId = ConversationId("thread-1")
        try {
            val operation = async { authorization.authorizeMcpServer(mcpServer("drive"), conversationId) }
            withTimeout(1_000) {
                authorization.state.first { it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION }
            }

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion("drive", success = true, threadId = "thread-2"),
            )
            repeat(10) { yield() }
            assertEquals(AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION, authorization.state.value.status)

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion("drive", success = true, threadId = conversationId.value),
            )
            operation.await()
        } finally {
            authorization.close()
            client.close()
        }
    }

    @Test
    fun claimedMcpTerminalWinsOverCancellationWithoutLeavingATombstone(): Unit = runBlocking {
        val process = oauthRuntime()
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        val terminalClaimed = CompletableDeferred<Unit>()
        val releaseTerminal = CompletableDeferred<Unit>()
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
            afterMcpTerminalClaimed = {
                terminalClaimed.complete(Unit)
                releaseTerminal.await()
            },
        )
        val drive = mcpServer("drive")
        val conversationId = ConversationId("thread-claim")
        try {
            val operation = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            withTimeout(1_000) { terminalClaimed.await() }
            authorization.cancel()
            releaseTerminal.complete(Unit)
            operation.await()
            assertEquals(AgentIntegrationAuthorizationStatus.AUTHORIZED, authorization.state.value.status)

            val retry = async { authorization.authorizeMcpServer(drive, conversationId) }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion(drive.name, success = true, threadId = conversationId.value),
            )
            retry.await()
        } finally {
            releaseTerminal.complete(Unit)
            authorization.close()
            client.close()
        }
    }

    @Test
    fun correlatesOneAttemptAndClosesEachBrowserPresentation(): Unit = runBlocking {
        val process = FakeCodexRuntime { message, server ->
            when (message.method) {
                "initialize" -> server.respond(message.id, buildJsonObject {})
                "mcpServer/oauth/login" -> server.respond(
                    message.id,
                    buildJsonObject {
                        put(
                            "authorizationUrl",
                            "https://accounts.example.com/oauth/${message.params.requiredString("name")}",
                        )
                    },
                )
            }
        }
        val client = CodexAgentClient({ process }, requestTimeoutMillis = 1_000)
        var opened = 0
        var closed = 0
        var openedUrl: CodexAuthorizationUrl? = null
        val authorization = IntegrationAuthorizationController(
            client,
            this,
            CodexAuthorizationBrowser { url ->
                openedUrl = url
                opened += 1
                CodexAuthorizationPresentation { closed += 1 }
            },
        )
        try {
            val drive = mcpServer("drive")
            val driveAuthorization = async {
                authorization.authorizeMcpServer(drive, ConversationId("thread-1"))
            }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertEquals("https://accounts.example.com/oauth/drive", openedUrl?.value)
            val target = assertIs<AgentIntegration.McpServer>(authorization.state.value.target)
            assertEquals(drive, target.server)
            assertFailsWith<IllegalStateException> {
                authorization.authorizeMcpServer(mcpServer("calendar"))
            }

            process.notify("mcpServer/oauthLogin/completed", completion("calendar", success = true))
            yield()
            assertEquals(
                AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION,
                authorization.state.value.status,
            )

            process.notify(
                "mcpServer/oauthLogin/completed",
                completion("drive", success = true, threadId = "thread-1"),
            )
            driveAuthorization.await()
            assertEquals(AgentIntegrationAuthorizationStatus.AUTHORIZED, authorization.state.value.status)
            assertEquals(1, closed)

            val calendarAuthorization = async {
                runCatching { authorization.authorizeMcpServer(mcpServer("calendar")) }
            }
            withTimeout(1_000) {
                authorization.state.first {
                    it.status == AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
                }
            }
            assertEquals(2, opened)
            process.notify(
                "mcpServer/oauthLogin/completed",
                completion("calendar", success = false, error = "denied"),
            )
            assertIs<CodexOperationException>(calendarAuthorization.await().exceptionOrNull())
            assertEquals(AgentIntegrationAuthorizationStatus.FAILED, authorization.state.value.status)
            assertEquals("denied", authorization.state.value.failure?.message)
            assertEquals(2, closed)
        } finally {
            authorization.close()
            client.close()
        }
    }
}

private fun authorizationAgent(
    client: CodexAgentClient,
    scope: CoroutineScope,
    open: (CodexAuthorizationUrl) -> CodexAuthorizationPresentation,
): CodexAgent = CodexAgent(
    workspace = CodexWorkspace("/workspace"),
    workingDirectory = "/workspace",
    features = setOf(CodexRuntimeFeature.CONNECTORS, CodexRuntimeFeature.MCP_SERVERS),
    client = client,
    parentScope = scope,
    authorizationBrowser = CodexAuthorizationBrowser(open),
)

private fun IntegrationAuthorizationController.controllerLock(): Mutex =
    javaClass.getDeclaredField("lock").let { field ->
        field.isAccessible = true
        field.get(this) as Mutex
    }

private suspend fun IntegrationAuthorizationController.awaitNoPendingMcpTerminal(
    serverName: String,
    conversationId: ConversationId?,
) {
    withTimeout(1_000) {
        while (hasPendingMcpTerminal(serverName, conversationId)) yield()
    }
}

private suspend fun IntegrationAuthorizationController.hasPendingMcpTerminal(
    serverName: String,
    conversationId: ConversationId?,
): Boolean {
    val controllerLock = controllerLock()
    controllerLock.lock()
    return try {
        val pending = javaClass.getDeclaredField("pendingMcpTerminals").let { field ->
            field.isAccessible = true
            field.get(this) as Map<*, *>
        }
        pending.keys.any { key ->
            key != null &&
                key.privateField("serverName") == serverName &&
                key.privateField("conversationId") == conversationId
        }
    } finally {
        controllerLock.unlock()
    }
}

private fun Any.privateField(name: String): Any? = javaClass.getDeclaredField(name).let { field ->
    field.isAccessible = true
    field.get(this)
}

private fun oauthRuntime(): FakeCodexRuntime = FakeCodexRuntime { message, server ->
    when (message.method) {
        "initialize" -> server.respond(message.id, buildJsonObject {})
        "thread/start" -> server.respond(message.id, buildJsonObject {
            put("thread", buildJsonObject { put("id", "thread-1") })
        })
        "mcpServer/oauth/login" -> server.respond(message.id, buildJsonObject {
            put("authorizationUrl", "https://accounts.example.com/oauth/${message.params.requiredString("name")}")
        })
    }
}

private fun connector(): AgentConnector = AgentConnector(
    id = "drive",
    name = "Drive",
    description = "Files",
    installUrl = "https://accounts.example.com/oauth",
)

private fun mcpServer(name: String): AgentMcpServer = AgentMcpServer(
    name = name,
    displayName = name.replaceFirstChar(Char::uppercase),
    authStatus = AgentMcpAuthStatus.NOT_LOGGED_IN,
)

private fun completion(
    name: String,
    success: Boolean,
    error: String? = null,
    threadId: String? = null,
) = buildJsonObject {
    put("name", name)
    put("success", success)
    error?.let { put("error", it) }
    threadId?.let { put("threadId", it) }
}

private fun connectorList(
    isAccessible: Boolean,
    includeInstallUrl: Boolean = true,
) = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("id", "drive")
            put("name", "Drive")
            put("description", "Files")
            if (includeInstallUrl) put("installUrl", "https://accounts.example.com/oauth")
            put("isAccessible", isAccessible)
            put("isEnabled", true)
        })
    }
}
