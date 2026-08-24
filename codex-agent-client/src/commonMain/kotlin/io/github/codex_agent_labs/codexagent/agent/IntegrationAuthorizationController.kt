package io.github.codex_agent_labs.codexagent.agent

import io.github.codex_agent_labs.codexagent.appserver.client.AppServerRpcException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.async
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

public sealed interface AgentIntegration {
    public val id: String
    public val displayName: String

    public data class Connector(
        public val connector: AgentConnector,
    ) : AgentIntegration {
        override val id: String get() = connector.id
        override val displayName: String get() = connector.name
    }

    public data class McpServer(
        public val server: AgentMcpServer,
    ) : AgentIntegration {
        override val id: String get() = server.name
        override val displayName: String get() = server.displayName
    }
}

public enum class AgentIntegrationAuthorizationStatus {
    IDLE,
    STARTING,
    AWAITING_COMPLETION,
    AUTHORIZED,
    FAILED,
}

public data class AgentIntegrationAuthorizationState(
    public val status: AgentIntegrationAuthorizationStatus = AgentIntegrationAuthorizationStatus.IDLE,
    public val target: AgentIntegration? = null,
    public val failure: CodexFailure? = null,
)

internal class IntegrationAuthorizationController(
    private val client: CodexAgentClient,
    scope: CoroutineScope,
    private val authorizationBrowser: CodexAuthorizationBrowser,
    private val afterMcpTerminalClaimed: (suspend () -> Unit)? = null,
) {
    private val lock = Mutex()
    private val mutableState = MutableStateFlow(AgentIntegrationAuthorizationState())
    private val mutableActive = MutableStateFlow<AgentIntegration?>(null)
    private var presentation: CodexAuthorizationPresentation? = null
    private var completion: CompletableDeferred<Throwable?>? = null
    private var startup: Job? = null
    private var mcpAttempt: McpAttempt? = null
    private var generation = 0L
    private var activeConversationId: ConversationId? = null
    private val pendingMcpTerminals = mutableMapOf<McpAuthorizationKey, McpAttempt>()
    private var closed = false

    internal val state: StateFlow<AgentIntegrationAuthorizationState> = mutableState.asStateFlow()
    internal val active: StateFlow<AgentIntegration?> = mutableActive.asStateFlow()

    private val observation: Job = scope.launch(start = CoroutineStart.UNDISPATCHED) {
        client.events.collect(::process)
    }

    internal suspend fun authorizeConnector(
        connector: AgentConnector,
        conversationId: ConversationId?,
    ) {
        require(connector.id.isNotBlank()) { "Connector ID must not be blank" }
        val begun = begin(AgentIntegration.Connector(connector), conversationId)
        closePrevious(begun, "connector_authorization_failed", "Connector authorization failed")

        val current = try {
            runStartup(begun) {
                client.listConnectors(conversationId, forceReload = true)
                    .singleOrNull { it.id == connector.id }
                    ?: error("Connector is unavailable: ${connector.id}")
            }
        } catch (error: Throwable) {
            throw fail(begun.operation, error, "connector_authorization_failed", "Connector authorization failed")
        }
        updateTarget(begun.operation, AgentIntegration.Connector(current))
        if (current.isAccessible) {
            complete(begun.operation)
            await(begun)
            return
        }
        val url = try {
            CodexAuthorizationUrl.external(
                current.installUrl ?: error("Connector does not provide an authorization URL"),
            )
        } catch (error: Throwable) {
            throw fail(begun.operation, error, "connector_authorization_failed", "Connector authorization failed")
        }
        openAndAwait(begun, url, "connector_authorization_failed")
    }

    internal suspend fun authorizeMcpServer(
        server: AgentMcpServer,
        conversationId: ConversationId? = null,
    ) {
        require(server.name.isNotBlank()) { "MCP server name must not be blank" }
        val begun = begin(AgentIntegration.McpServer(server), conversationId)
        closePrevious(begun, "mcp_authorization_failed", "MCP authorization failed")
        val url = try {
            CodexAuthorizationUrl.external(runStartup(begun) {
                val authorizationUrl = client.startMcpOauth(server.name, conversationId) {
                    markMcpIssued(begun)
                }
                markMcpAcknowledged(begun)
                authorizationUrl
            })
        } catch (error: Throwable) {
            throw fail(
                begun.operation,
                error,
                "mcp_authorization_failed",
                "MCP authorization failed",
                mcpTombstoneThreshold = when {
                    error is AppServerRpcException -> null
                    isMcpAcknowledged(begun) -> {
                        McpTombstoneThreshold.ACKNOWLEDGED
                    }
                    else -> McpTombstoneThreshold.ISSUED
                },
            )
        }
        openAndAwait(
            begun,
            url,
            "mcp_authorization_failed",
            mcpTombstoneThreshold = McpTombstoneThreshold.ACKNOWLEDGED,
        )
    }

    internal suspend fun cancel() {
        val owned = lock.withLock {
            check(!closed) { "Integration authorization is closed" }
            if (mutableState.value.status !in ACTIVE_STATUSES) return
            if (mcpAttempt?.terminalClaimed == true) return
            generation += 1
            val result = activeResources()
            provisionMcpAttempt(result)
            presentation = null
            completion = null
            startup = null
            mcpAttempt = null
            activeConversationId = null
            publishState(AgentIntegrationAuthorizationState())
            result
        }
        val cleanupFailure = closePresentation(owned)
        withContext(NonCancellable) {
            reconcileMcpAttempt(owned)
            owned.completion?.complete(CancellationException("Integration authorization was cancelled"))
        }
        cleanupFailure?.let { throw it }
    }

    internal suspend fun close() {
        val owned = lock.withLock {
            if (closed) return
            closed = true
            generation += 1
            observation.cancel()
            activeConversationId = null
            activeResources().also {
                presentation = null
                completion = null
                startup = null
                mcpAttempt = null
                pendingMcpTerminals.clear()
                publishState(AgentIntegrationAuthorizationState())
            }
        }
        observation.join()
        val cleanupFailure = closePresentation(owned)
        withContext(NonCancellable) {
            owned.completion?.complete(CancellationException("Integration authorization was closed"))
        }
        cleanupFailure?.let { throw it }
    }

    private suspend fun begin(
        target: AgentIntegration,
        conversationId: ConversationId?,
    ): BeginResult = lock.withLock {
        check(!closed) { "Integration authorization is closed" }
        check(mutableState.value.status !in ACTIVE_STATUSES) {
            "Another integration authorization is already active"
        }
        if (target is AgentIntegration.McpServer) {
            check(McpAuthorizationKey(target.server.name, conversationId) !in pendingMcpTerminals) {
                "An earlier MCP authorization for ${target.server.name} is awaiting its terminal notification"
            }
        }
        generation += 1
        activeConversationId = conversationId
        val previous = presentation
        presentation = null
        val operationCompletion = CompletableDeferred<Throwable?>()
        val attempt = (target as? AgentIntegration.McpServer)?.let {
            McpAttempt(McpAuthorizationKey(it.server.name, conversationId))
        }
        completion = operationCompletion
        mcpAttempt = attempt
        publishState(AgentIntegrationAuthorizationState(
            status = AgentIntegrationAuthorizationStatus.STARTING,
            target = target,
        ))
        BeginResult(generation, previous, operationCompletion, attempt)
    }

    private suspend fun <T> runStartup(begun: BeginResult, block: suspend () -> T): T = coroutineScope {
        val request = async(start = CoroutineStart.LAZY) { block() }
        val accepted = lock.withLock {
            val current = mutableState.value
            if (!closed && generation == begun.operation && current.status == AgentIntegrationAuthorizationStatus.STARTING) {
                startup = request
                true
            } else {
                false
            }
        }
        if (!accepted) {
            request.cancel()
            await(begun)
            error("Cancelled authorization startup completed normally")
        }
        request.start()
        try {
            request.await()
        } catch (error: CancellationException) {
            begun.completion.await()?.let { throw it }
            throw error
        } finally {
            withContext(NonCancellable) {
                lock.withLock {
                    if (startup === request) startup = null
                }
            }
        }
    }

    private suspend fun closePrevious(begun: BeginResult, code: String, fallback: String) {
        try {
            begun.previous?.close()
        } catch (error: Throwable) {
            throw fail(begun.operation, error, code, fallback)
        }
    }

    private suspend fun updateTarget(operation: Long, target: AgentIntegration) = lock.withLock {
        val current = mutableState.value
        if (!closed && generation == operation && current.status in ACTIVE_STATUSES) {
            publishState(current.copy(target = target))
        }
    }

    private suspend fun openAndAwait(
        begun: BeginResult,
        url: CodexAuthorizationUrl,
        failureCode: String,
        mcpTombstoneThreshold: McpTombstoneThreshold? = null,
    ) {
        val opened = try {
            lock.withLock {
                val current = mutableState.value
                if (closed || generation != begun.operation ||
                    current.status != AgentIntegrationAuthorizationStatus.STARTING
                ) {
                    false
                } else {
                    presentation = authorizationBrowser.open(url)
                    publishState(current.copy(
                        status = AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION,
                    ))
                    true
                }
            }
        } catch (error: Throwable) {
            throw fail(
                begun.operation,
                error,
                failureCode,
                "Could not open the authorization URL",
                mcpTombstoneThreshold,
            )
        }
        if (!opened) {
            await(begun)
            return
        }
        try {
            currentCoroutineContext().ensureActive()
            await(begun)
        } catch (error: CancellationException) {
            abandon(begun.operation)
            throw error
        } catch (error: CodexOperationException) {
            throw error
        } catch (error: Throwable) {
            throw fail(
                begun.operation,
                error,
                failureCode,
                "Could not retain the authorization presentation",
                mcpTombstoneThreshold,
            )
        }
    }

    private suspend fun await(begun: BeginResult) {
        try {
            begun.completion.await()?.let { throw it }
            currentCoroutineContext().ensureActive()
        } catch (error: CancellationException) {
            abandon(begun.operation)
            throw error
        }
    }

    private suspend fun process(event: AgentEvent) {
        when (event) {
            AgentEvent.ConnectorsChanged -> refreshActiveConnector()
            is AgentEvent.McpOauthCompleted -> {
                val operation = lock.withLock {
                    val key = McpAuthorizationKey(event.serverName, event.conversationId)
                    pendingMcpTerminals.remove(key)?.let { pending ->
                        pending.terminalConsumed = true
                        return@withLock null
                    }
                    val snapshot = mutableState.value
                    val target = snapshot.target as? AgentIntegration.McpServer
                    if (
                        snapshot.status in ACTIVE_STATUSES &&
                            target?.server?.name == event.serverName &&
                            activeConversationId == event.conversationId
                    ) {
                        mcpAttempt?.terminalClaimed = true
                        generation
                    } else {
                        null
                    }
                }
                if (operation != null) {
                    afterMcpTerminalClaimed?.invoke()
                    if (event.success) {
                        complete(operation)
                    } else {
                        fail(
                            operation,
                            CodexOperationException(
                                codexFailure(
                                    "mcp_authorization_failed",
                                    event.error,
                                    "MCP authorization failed",
                                    true,
                                ),
                            ),
                            "mcp_authorization_failed",
                            "MCP authorization failed",
                        )
                    }
                }
            }
            is AgentEvent.Failure -> {
                val operation = lock.withLock {
                    val current = mutableState.value
                    generation.takeIf {
                        current.status in ACTIVE_STATUSES &&
                            (event.conversationId == null || event.conversationId == activeConversationId)
                    }
                }
                if (operation != null) {
                    fail(
                        operation,
                        CodexOperationException(
                            codexFailure(event.code, event.message, "Integration authorization failed", event.isRecoverable),
                        ),
                        event.code,
                        "Integration authorization failed",
                        mcpTombstoneThreshold = McpTombstoneThreshold.ISSUED,
                    )
                }
            }
            else -> Unit
        }
    }

    private suspend fun refreshActiveConnector() {
        val active = lock.withLock {
            val current = mutableState.value
            val target = current.target as? AgentIntegration.Connector
            if (current.status !in ACTIVE_STATUSES || target == null) return
            Triple(generation, target, activeConversationId)
        }
        val connector = try {
            client.listConnectors(active.third, forceReload = true).singleOrNull {
                it.id == active.second.connector.id
            }
        } catch (error: Throwable) {
            fail(active.first, error, "connector_authorization_failed", "Connector authorization failed")
            return
        }
        if (connector?.isAccessible == true) {
            updateTarget(active.first, AgentIntegration.Connector(connector))
            complete(active.first)
        }
    }

    private suspend fun complete(operation: Long) {
        val owned = lock.withLock {
            val current = mutableState.value
            if (closed || generation != operation || current.status !in ACTIVE_STATUSES) return
            activeConversationId = null
            val result = activeResources().copy(startup = null)
            presentation = null
            completion = null
            startup = null
            mcpAttempt = null
            publishState(current.copy(
                status = AgentIntegrationAuthorizationStatus.AUTHORIZED,
                failure = null,
            ))
            result
        }
        val cleanupFailure = closePresentation(owned)
        withContext(NonCancellable) {
            if (cleanupFailure != null) {
                lock.withLock {
                    val current = mutableState.value
                    if (!closed && generation == operation && current.status == AgentIntegrationAuthorizationStatus.AUTHORIZED) {
                        publishState(current.copy(
                            status = AgentIntegrationAuthorizationStatus.FAILED,
                            failure = cleanupFailure.failure,
                        ))
                    }
                }
            }
            owned.completion?.complete(cleanupFailure)
        }
    }

    private suspend fun fail(
        operation: Long,
        error: Throwable,
        code: String,
        fallback: String,
        mcpTombstoneThreshold: McpTombstoneThreshold? = null,
    ): CodexOperationException {
        if (error is CancellationException) {
            abandon(operation)
            throw error
        }
        val exception = error.asCodexOperationException(code, fallback)
        withContext(NonCancellable) {
            val owned = lock.withLock {
                val current = mutableState.value
                if (closed || generation != operation || current.status !in ACTIVE_STATUSES) return@withLock null
                val result = activeResources()
                if (mcpTombstoneThreshold != null) {
                    rememberMcpAttempt(result, mcpTombstoneThreshold)
                }
                activeConversationId = null
                presentation = null
                completion = null
                startup = null
                mcpAttempt = null
                publishState(current.copy(
                    status = AgentIntegrationAuthorizationStatus.FAILED,
                    failure = exception.failure,
                ))
                result
            }
            if (owned != null) {
                closePresentation(owned)?.let(exception::addSuppressed)
                owned.completion?.complete(exception)
            }
        }
        return exception
    }

    private suspend fun abandon(operation: Long) {
        withContext(NonCancellable) {
            val owned = lock.withLock {
                if (closed || generation != operation || mutableState.value.status !in ACTIVE_STATUSES) {
                    return@withLock null
                }
                if (mcpAttempt?.terminalClaimed == true) return@withLock null
                val result = activeResources()
                provisionMcpAttempt(result)
                activeConversationId = null
                presentation = null
                completion = null
                startup = null
                mcpAttempt = null
                publishState(AgentIntegrationAuthorizationState())
                result
            }
            if (owned != null) {
                val cleanupFailure = closePresentation(owned)
                reconcileMcpAttempt(owned)
                cleanupFailure?.let {
                    lock.withLock {
                        if (!closed && generation == operation) {
                            publishState(AgentIntegrationAuthorizationState(
                                status = AgentIntegrationAuthorizationStatus.FAILED,
                                target = owned.target,
                                failure = it.failure,
                            ))
                        }
                    }
                }
                owned.completion?.complete(CancellationException("Integration authorization was cancelled"))
            }
        }
    }

    private fun activeResources(): ActiveResources = ActiveResources(
        presentation = presentation,
        completion = completion,
        startup = startup,
        mcpAttempt = mcpAttempt,
        target = mutableState.value.target,
    )

    private suspend fun markMcpIssued(begun: BeginResult): Unit = withContext(NonCancellable) {
        lock.withLock {
            val attempt = begun.mcpAttempt ?: return@withLock
            attempt.issued = true
            val isActive = !closed &&
                generation == begun.operation &&
                mcpAttempt === attempt &&
                mutableState.value.status in ACTIVE_STATUSES
            if (!isActive && !closed && !attempt.terminalClaimed && !attempt.terminalConsumed) {
                pendingMcpTerminals[attempt.key] = attempt
            }
        }
    }

    private suspend fun markMcpAcknowledged(begun: BeginResult): Unit = withContext(NonCancellable) {
        lock.withLock { begun.mcpAttempt?.acknowledged = true }
    }

    private suspend fun isMcpAcknowledged(begun: BeginResult): Boolean =
        lock.withLock { begun.mcpAttempt?.acknowledged == true }

    private fun provisionMcpAttempt(resources: ActiveResources) {
        val attempt = resources.mcpAttempt ?: return
        if (!attempt.terminalClaimed && !attempt.terminalConsumed) {
            pendingMcpTerminals[attempt.key] = attempt
        }
    }

    private suspend fun reconcileMcpAttempt(resources: ActiveResources) {
        val attempt = resources.mcpAttempt ?: return
        lock.withLock {
            if (!attempt.issued && pendingMcpTerminals[attempt.key] === attempt) {
                pendingMcpTerminals.remove(attempt.key)
            }
        }
    }

    private fun rememberMcpAttempt(
        resources: ActiveResources,
        threshold: McpTombstoneThreshold,
    ) {
        val attempt = resources.mcpAttempt ?: return
        val reachedThreshold = when (threshold) {
            McpTombstoneThreshold.ISSUED -> attempt.issued
            McpTombstoneThreshold.ACKNOWLEDGED -> attempt.acknowledged
        }
        if (reachedThreshold && !attempt.terminalClaimed && !attempt.terminalConsumed) {
            pendingMcpTerminals[attempt.key] = attempt
        }
    }

    private suspend fun closePresentation(owned: ActiveResources): CodexOperationException? =
        withContext(NonCancellable) {
            owned.startup?.cancelAndJoin()
            try {
                owned.presentation?.close()
                null
            } catch (error: Throwable) {
                CodexOperationException(
                    failure = codexFailure(
                        code = when (owned.target) {
                            is AgentIntegration.Connector -> "connector_authorization_failed"
                            is AgentIntegration.McpServer, null -> "mcp_authorization_failed"
                        },
                        message = null,
                        fallback = "Could not close the authorization presentation",
                        isRecoverable = true,
                    ),
                    cause = error,
                )
            }
        }

    private fun publishState(state: AgentIntegrationAuthorizationState) {
        mutableState.value = state
        mutableActive.value = state.target.takeIf { state.status in ACTIVE_STATUSES }
    }

    private companion object {
        val ACTIVE_STATUSES = setOf(
            AgentIntegrationAuthorizationStatus.STARTING,
            AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION,
        )
    }

    private data class BeginResult(
        val operation: Long,
        val previous: CodexAuthorizationPresentation?,
        val completion: CompletableDeferred<Throwable?>,
        val mcpAttempt: McpAttempt?,
    )

    private data class ActiveResources(
        val presentation: CodexAuthorizationPresentation?,
        val completion: CompletableDeferred<Throwable?>?,
        val startup: Job?,
        val mcpAttempt: McpAttempt?,
        val target: AgentIntegration?,
    )

    private data class McpAttempt(
        val key: McpAuthorizationKey,
        var issued: Boolean = false,
        var acknowledged: Boolean = false,
        var terminalClaimed: Boolean = false,
        var terminalConsumed: Boolean = false,
    )

    private enum class McpTombstoneThreshold {
        ISSUED,
        ACKNOWLEDGED,
    }

    private data class McpAuthorizationKey(
        val serverName: String,
        val conversationId: ConversationId?,
    )
}
