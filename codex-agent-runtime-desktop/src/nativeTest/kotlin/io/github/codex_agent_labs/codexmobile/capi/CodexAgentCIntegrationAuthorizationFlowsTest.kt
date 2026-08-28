@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegration
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentMcpServer
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_path_workspace_selection
import kotlin.concurrent.atomics.AtomicInt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.sizeOf
import kotlinx.cinterop.staticCFunction
import kotlinx.cinterop.value
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

class CodexAgentCIntegrationAuthorizationFlowsTest {
    @Test
    fun integrationAuthorizationStateGetAndSubscribeProjectConnectorAndMcpTransitions(): Unit = runBlocking {
        withReadyIntegrationFlowGraph { graph ->
            val subscription = emptyFlowHandle()
            val observer = IntegrationFlowObserver(subscription.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    observer.userData,
                    subscription.ptr,
                ),
            )
            val subscriptionHandle = assertNotNull(subscription.value)

            exerciseIntegrationTransitions(
                graph,
                initial = {
                    assertEquals(ProjectedAuthorizationState(0, null, null, 0), currentAuthorizationState(graph))
                    assertEquals(
                        ProjectedAuthorizationState(0, null, null, 0),
                        receiveAuthorizationState(graph.context, observer, subscriptionHandle),
                    )
                },
                connectorActive = {
                    assertEquals(
                        ProjectedAuthorizationState(1, 0, CONNECTOR_ID, 0),
                        currentAuthorizationState(graph),
                    )
                    assertEquals(
                        ProjectedAuthorizationState(1, 0, CONNECTOR_ID, 0),
                        receiveAuthorizationStateUntil(graph.context, observer, subscriptionHandle) {
                            it.status == 1 && it.targetId == CONNECTOR_ID
                        },
                    )
                },
                connectorDone = {
                    assertEquals(
                        ProjectedAuthorizationState(3, 0, CONNECTOR_ID, 0),
                        currentAuthorizationState(graph),
                    )
                    assertEquals(
                        ProjectedAuthorizationState(3, 0, CONNECTOR_ID, 0),
                        receiveAuthorizationStateUntil(graph.context, observer, subscriptionHandle) {
                            it.status == 3 && it.targetId == CONNECTOR_ID
                        },
                    )
                },
                mcpActive = {
                    assertEquals(
                        ProjectedAuthorizationState(2, 1, MCP_NAME, 0),
                        awaitCurrentAuthorizationState(graph, status = 2),
                    )
                    assertEquals(
                        ProjectedAuthorizationState(2, 1, MCP_NAME, 0),
                        receiveAuthorizationStateUntil(graph.context, observer, subscriptionHandle) {
                            it.status == 2 && it.targetId == MCP_NAME
                        },
                    )
                },
                mcpDone = {
                    assertEquals(
                        ProjectedAuthorizationState(3, 1, MCP_NAME, 0),
                        currentAuthorizationState(graph),
                    )
                    assertEquals(
                        ProjectedAuthorizationState(3, 1, MCP_NAME, 0),
                        receiveAuthorizationStateUntil(graph.context, observer, subscriptionHandle) {
                            it.status == 3 && it.targetId == MCP_NAME
                        },
                    )
                },
            )

            destroyIntegrationFlowSubscription(graph.context, subscription.ptr)
            observer.dispose()
        }
    }

    @Test
    fun integrationAuthorizationActiveGetAndSubscribeProjectNullConnectorMcpNull(): Unit = runBlocking {
        withReadyIntegrationFlowGraph { graph ->
            val subscription = emptyFlowHandle()
            val observer = IntegrationFlowObserver(subscription.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationActiveSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    observer.userData,
                    subscription.ptr,
                ),
            )
            val subscriptionHandle = assertNotNull(subscription.value)

            exerciseIntegrationTransitions(
                graph,
                initial = {
                    assertEquals(ProjectedActive(null, null, 0), currentAuthorizationActive(graph))
                    assertEquals(
                        ProjectedActive(null, null, 0),
                        receiveAuthorizationActive(graph.context, observer, subscriptionHandle),
                    )
                },
                connectorActive = {
                    assertEquals(ProjectedActive(0, CONNECTOR_ID, 0), currentAuthorizationActive(graph))
                    assertEquals(
                        ProjectedActive(0, CONNECTOR_ID, 0),
                        receiveAuthorizationActiveUntil(graph.context, observer, subscriptionHandle) {
                            it.targetId == CONNECTOR_ID
                        },
                    )
                },
                connectorDone = {
                    assertEquals(ProjectedActive(null, null, 0), currentAuthorizationActive(graph))
                    assertEquals(
                        ProjectedActive(null, null, 0),
                        receiveAuthorizationActiveUntil(graph.context, observer, subscriptionHandle) {
                            it.targetId == null
                        },
                    )
                },
                mcpActive = {
                    assertEquals(ProjectedActive(1, MCP_NAME, 0), currentAuthorizationActive(graph))
                    assertEquals(
                        ProjectedActive(1, MCP_NAME, 0),
                        receiveAuthorizationActiveUntil(graph.context, observer, subscriptionHandle) {
                            it.targetId == MCP_NAME
                        },
                    )
                },
                mcpDone = {
                    assertEquals(ProjectedActive(null, null, 0), currentAuthorizationActive(graph))
                    assertEquals(
                        ProjectedActive(null, null, 0),
                        receiveAuthorizationActiveUntil(graph.context, observer, subscriptionHandle) {
                            it.targetId == null
                        },
                    )
                },
            )

            destroyIntegrationFlowSubscription(graph.context, subscription.ptr)
            observer.dispose()
        }
    }

    @Test
    fun integrationAuthorizationIsAuthorizingGetAndSubscribeProjectFalseTrueFalse(): Unit = runBlocking {
        withReadyIntegrationFlowGraph { graph ->
            val subscription = emptyFlowHandle()
            val observer = IntegrationFlowObserver(subscription.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationIsAuthorizingSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    observer.userData,
                    subscription.ptr,
                ),
            )
            val subscriptionHandle = assertNotNull(subscription.value)

            exerciseIntegrationTransitions(
                graph,
                initial = {
                    assertEquals(ProjectedBoolean(false, 0), currentAuthorizationBoolean(graph))
                    assertEquals(
                        ProjectedBoolean(false, 0),
                        receiveAuthorizationBoolean(graph.context, observer, subscriptionHandle),
                    )
                },
                connectorActive = {
                    assertEquals(ProjectedBoolean(true, 0), currentAuthorizationBoolean(graph))
                    assertEquals(
                        ProjectedBoolean(true, 0),
                        receiveAuthorizationBooleanUntil(graph.context, observer, subscriptionHandle, true),
                    )
                },
                connectorDone = {
                    assertEquals(ProjectedBoolean(false, 0), currentAuthorizationBoolean(graph))
                    assertEquals(
                        ProjectedBoolean(false, 0),
                        receiveAuthorizationBooleanUntil(graph.context, observer, subscriptionHandle, false),
                    )
                },
                mcpActive = {
                    assertEquals(ProjectedBoolean(true, 0), currentAuthorizationBoolean(graph))
                    assertEquals(
                        ProjectedBoolean(true, 0),
                        receiveAuthorizationBooleanUntil(graph.context, observer, subscriptionHandle, true),
                    )
                },
                mcpDone = {
                    assertEquals(ProjectedBoolean(false, 0), currentAuthorizationBoolean(graph))
                    assertEquals(
                        ProjectedBoolean(false, 0),
                        receiveAuthorizationBooleanUntil(graph.context, observer, subscriptionHandle, false),
                    )
                },
            )

            destroyIntegrationFlowSubscription(graph.context, subscription.ptr)
            observer.dispose()
        }
    }

    @Test
    fun integrationAuthorizationFlowsRejectBoundariesAndTerminateQuiescentlyWithOwnerLifecycle(): Unit = runBlocking {
        val resources = IntegrationFlowResources()
        memScoped {
            val graph = readyIntegrationFlowGraph(resources)
            val otherContext = emptyFlowHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
            val occupied = alloc<COpaquePointerVar>().also { it.value = graph.host.value }
            val output = emptyFlowHandle()

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateGet(graph.context, graph.authorization.value, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationActiveGet(graph.context, graph.authorization.value, occupied.ptr),
            )
            assertEquals(graph.host.value, occupied.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationAuthorizationIsAuthorizingGet(
                    otherContext.value,
                    graph.authorization.value,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateGet(graph.context, graph.host.value, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateSubscribe(
                    graph.context,
                    graph.authorization.value,
                    null,
                    null,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val stateSnapshot = emptyFlowHandle()
            val activeSnapshot = emptyFlowHandle()
            val booleanSnapshot = emptyFlowHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateGet(
                    graph.context,
                    graph.authorization.value,
                    stateSnapshot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationActiveGet(
                    graph.context,
                    graph.authorization.value,
                    activeSnapshot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationIsAuthorizingGet(
                    graph.context,
                    graph.authorization.value,
                    booleanSnapshot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateValue(
                    graph.context,
                    booleanSnapshot.value,
                    output.ptr,
                ),
            )
            val sentinel = alloc<IntVar>().also { it.value = 91 }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationActiveHasValue(
                    graph.context,
                    stateSnapshot.value,
                    sentinel.ptr,
                ),
            )
            assertEquals(91, sentinel.value)
            val staleStateSnapshot = assertNotNull(stateSnapshot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, stateSnapshot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationAuthorizationStateValue(
                    graph.context,
                    staleStateSnapshot,
                    output.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, activeSnapshot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(graph.context, booleanSnapshot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationActiveSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    null,
                    occupied.ptr,
                ),
            )
            assertEquals(graph.host.value, occupied.value)

            val stateSubscription = emptyFlowHandle()
            val activeSubscription = emptyFlowHandle()
            val booleanSubscription = emptyFlowHandle()
            val stateObserver = IntegrationFlowObserver(stateSubscription.ptr)
            val activeObserver = IntegrationFlowObserver(activeSubscription.ptr)
            val booleanObserver = IntegrationFlowObserver(booleanSubscription.ptr)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    stateObserver.userData,
                    stateSubscription.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationActiveSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    activeObserver.userData,
                    activeSubscription.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationIsAuthorizingSubscribe(
                    graph.context,
                    graph.authorization.value,
                    integrationFlowCallback,
                    booleanObserver.userData,
                    booleanSubscription.ptr,
                ),
            )
            val stateHandle = assertNotNull(stateSubscription.value)
            val activeHandle = assertNotNull(activeSubscription.value)
            val booleanHandle = assertNotNull(booleanSubscription.value)
            assertEquals(
                ProjectedAuthorizationState(0, null, null, 0),
                receiveAuthorizationState(graph.context, stateObserver, stateHandle),
            )
            assertEquals(
                ProjectedActive(null, null, 0),
                receiveAuthorizationActive(graph.context, activeObserver, activeHandle),
            )
            assertEquals(
                ProjectedBoolean(false, 0),
                receiveAuthorizationBoolean(graph.context, booleanObserver, booleanHandle),
            )

            val staleAuthorization = assertNotNull(graph.authorization.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationRelease(graph.context, graph.authorization.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationAuthorizationStateGet(graph.context, staleAuthorization, output.ptr),
            )
            closeIntegrationFlowHost(graph)

            assertEquals(
                ProjectedAuthorizationState(0, null, null, 1),
                receiveAuthorizationState(graph.context, stateObserver, stateHandle),
            )
            assertEquals(
                ProjectedActive(null, null, 1),
                receiveAuthorizationActive(graph.context, activeObserver, activeHandle),
            )
            assertEquals(
                ProjectedBoolean(false, 1),
                receiveAuthorizationBoolean(graph.context, booleanObserver, booleanHandle),
            )
            destroyIntegrationFlowSubscription(graph.context, stateSubscription.ptr)
            destroyIntegrationFlowSubscription(graph.context, activeSubscription.ptr)
            destroyIntegrationFlowSubscription(graph.context, booleanSubscription.ptr)
            assertNoIntegrationFlowEvent(stateObserver)
            assertNoIntegrationFlowEvent(activeObserver)
            assertNoIntegrationFlowEvent(booleanObserver)
            assertEquals(2, stateObserver.callbacks.load())
            assertEquals(2, activeObserver.callbacks.load())
            assertEquals(2, booleanObserver.callbacks.load())
            stateObserver.dispose()
            activeObserver.dispose()
            booleanObserver.dispose()

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(graph.context, graph.agent.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(graph.context, graph.host.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(graph.contextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
        }
    }
}

private data class ProjectedAuthorizationState(
    val status: Int,
    val targetKind: Int?,
    val targetId: String?,
    val terminal: Int,
)

private data class ProjectedActive(val targetKind: Int?, val targetId: String?, val terminal: Int)
private data class ProjectedBoolean(val value: Boolean, val terminal: Int)

private data class IntegrationFlowEvent(
    val context: COpaquePointer?,
    val subscription: COpaquePointer?,
    val status: Int,
    val snapshot: COpaquePointer?,
    val terminal: Int,
    val userData: COpaquePointer?,
    val publishedSubscription: COpaquePointer?,
)

private class IntegrationFlowObserver(val output: CPointer<COpaquePointerVar>) {
    val callbacks = AtomicInt(0)
    val events = Channel<IntegrationFlowEvent>(Channel.UNLIMITED)
    private val reference = StableRef.create(this)
    val userData: COpaquePointer = reference.asCPointer()

    fun dispose() = reference.dispose()
}

private val integrationFlowCallback = staticCFunction {
        context: COpaquePointer?,
        subscription: COpaquePointer?,
        status: Int,
        snapshot: COpaquePointer?,
        terminal: Int,
        userData: COpaquePointer?,
    ->
    val observer = checkNotNull(userData).asStableRef<IntegrationFlowObserver>().get()
    observer.callbacks.addAndFetch(1)
    observer.events.trySend(
        IntegrationFlowEvent(
            context,
            subscription,
            status,
            snapshot,
            terminal,
            userData,
            observer.output.pointed.value,
        ),
    )
    Unit
}

private class IntegrationFlowResources {
    val connectorRequest = CompletableDeferred<Unit>()
    val releaseConnector = CompletableDeferred<Unit>()
    val fixture = NativeCodexBehaviorFixture(
        features = setOf(CodexRuntimeFeature.CONNECTORS, CodexRuntimeFeature.MCP_SERVERS),
        additionalResponse = { method, _ ->
            when (method) {
                "app/list" -> {
                    connectorRequest.complete(Unit)
                    releaseConnector.await()
                    connectorListResponse()
                }
                "mcpServer/oauth/login" -> buildJsonObject {
                    put("authorizationUrl", "https://auth.example.com/mcp")
                }
                else -> null
            }
        },
    )
}

private data class IntegrationFlowGraph(
    val resources: IntegrationFlowResources,
    val contextSlot: COpaquePointerVar,
    val context: COpaquePointer,
    val host: COpaquePointerVar,
    val agent: COpaquePointerVar,
    val authorization: COpaquePointerVar,
)

private suspend fun withReadyIntegrationFlowGraph(
    block: suspend MemScope.(IntegrationFlowGraph) -> Unit,
) {
    val resources = IntegrationFlowResources()
    memScoped {
        val graph = readyIntegrationFlowGraph(resources)
        try {
            block(graph)
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationRelease(graph.context, graph.authorization.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAgentRelease(graph.context, graph.agent.ptr))
            closeIntegrationFlowHost(graph)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(graph.context, graph.host.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(graph.contextSlot.ptr))
        }
    }
}

private suspend fun MemScope.readyIntegrationFlowGraph(
    resources: IntegrationFlowResources,
): IntegrationFlowGraph {
    val contextSlot = emptyFlowHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    val context = assertNotNull(contextSlot.value)
    val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
    val runtime = contextLease.payload as CodexAgentCContextRuntime
    assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())
    val hostEntry = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        CodexAgentCHost(resources.fixture.createHost(), runtime),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, hostEntry.status)
    val host = alloc<COpaquePointerVar>().also { it.value = assertNotNull(hostEntry.value) }
    selectIntegrationFlowWorkspace(context, assertNotNull(host.value), resources.fixture.workspace.path)

    val hostState = emptyFlowHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host.value, hostState.ptr))
    val agent = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostStateAgent(context, host.value, hostState.value, agent.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, hostState.ptr))
    val authorization = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentAgentIntegrationAuthorization(context, agent.value, authorization.ptr),
    )
    return IntegrationFlowGraph(resources, contextSlot, context, host, agent, authorization)
}

private suspend fun MemScope.exerciseIntegrationTransitions(
    graph: IntegrationFlowGraph,
    initial: suspend () -> Unit,
    connectorActive: suspend () -> Unit,
    connectorDone: suspend () -> Unit,
    mcpActive: suspend () -> Unit,
    mcpDone: suspend () -> Unit,
) {
    initial()
    val connectorTarget = integrationFlowTarget(
        graph.context,
        AgentIntegration.Connector(
            AgentConnector(CONNECTOR_ID, "Drive input", isAccessible = false, pluginNames = listOf("input-plugin")),
        ),
    )
    val connectorOperation = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationAuthorize(
            graph.context,
            graph.authorization.value,
            connectorTarget.value,
            null,
            null,
            connectorOperation.ptr,
        ),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, connectorTarget.ptr))
    withTimeout(TIMEOUT_MILLIS) { graph.resources.connectorRequest.await() }
    connectorActive()
    graph.resources.releaseConnector.complete(Unit)
    assertEquals(CODEX_AGENT_STATUS_OK, awaitIntegrationFlowOperation(graph.context, connectorOperation.value))
    destroyIntegrationFlowOperation(graph.context, connectorOperation.ptr)
    connectorDone()

    val mcpTarget = integrationFlowTarget(
        graph.context,
        AgentIntegration.McpServer(AgentMcpServer(MCP_NAME, "Drive MCP", AgentMcpAuthStatus.NOT_LOGGED_IN)),
    )
    val mcpOperation = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationAuthorize(
            graph.context,
            graph.authorization.value,
            mcpTarget.value,
            null,
            null,
            mcpOperation.ptr,
        ),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(graph.context, mcpTarget.ptr))
    awaitIntegrationFlowRequest(graph.resources.fixture, "mcpServer/oauth/login")
    mcpActive()
    graph.resources.fixture.notify(
        "mcpServer/oauthLogin/completed",
        buildJsonObject { put("name", MCP_NAME); put("success", true) },
    )
    assertEquals(CODEX_AGENT_STATUS_OK, awaitIntegrationFlowOperation(graph.context, mcpOperation.value))
    destroyIntegrationFlowOperation(graph.context, mcpOperation.ptr)
    mcpDone()
}

private fun MemScope.currentAuthorizationState(graph: IntegrationFlowGraph): ProjectedAuthorizationState {
    val snapshot = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationStateGet(graph.context, graph.authorization.value, snapshot.ptr),
    )
    return projectAuthorizationState(graph.context, assertNotNull(snapshot.value), terminal = 0)
}

private suspend fun MemScope.awaitCurrentAuthorizationState(
    graph: IntegrationFlowGraph,
    status: Int,
): ProjectedAuthorizationState = withTimeout(TIMEOUT_MILLIS) {
    while (true) {
        val current = currentAuthorizationState(graph)
        if (current.status == status) return@withTimeout current
        yield()
    }
    error("unreachable")
}

private fun MemScope.currentAuthorizationActive(graph: IntegrationFlowGraph): ProjectedActive {
    val snapshot = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationActiveGet(graph.context, graph.authorization.value, snapshot.ptr),
    )
    return projectAuthorizationActive(graph.context, assertNotNull(snapshot.value), terminal = 0)
}

private fun MemScope.currentAuthorizationBoolean(graph: IntegrationFlowGraph): ProjectedBoolean {
    val snapshot = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationIsAuthorizingGet(
            graph.context,
            graph.authorization.value,
            snapshot.ptr,
        ),
    )
    return projectAuthorizationBoolean(graph.context, assertNotNull(snapshot.value), terminal = 0)
}

private suspend fun MemScope.receiveAuthorizationState(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
): ProjectedAuthorizationState {
    val event = receiveIntegrationFlowEvent(observer, context, subscription)
    return projectAuthorizationState(context, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun MemScope.receiveAuthorizationStateUntil(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
    predicate: (ProjectedAuthorizationState) -> Boolean,
): ProjectedAuthorizationState = withTimeout(TIMEOUT_MILLIS) {
    while (true) {
        val value = receiveAuthorizationState(context, observer, subscription)
        if (predicate(value)) return@withTimeout value
    }
    error("unreachable")
}

private fun MemScope.projectAuthorizationState(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    terminal: Int,
): ProjectedAuthorizationState {
    val firstState = emptyFlowHandle()
    val secondState = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationStateValue(context, snapshot, firstState.ptr),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationStateValue(context, snapshot, secondState.ptr),
    )
    assertNotEquals(firstState.value, secondState.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationAuthorizationStateDestroy(context, secondState.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, destroyIntegrationFlowSnapshot(context, snapshot))
    val state = assertNotNull(firstState.value)
    val status = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationAuthorizationStateStatus(context, state, status.ptr))
    val target = emptyFlowHandle()
    val failure = emptyFlowHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationStateTarget(context, state, target.ptr),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationStateFailure(context, state, failure.ptr),
    )
    assertNull(failure.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationAuthorizationStateDestroy(context, firstState.ptr))
    val projectedTarget = target.value?.let { projectIntegrationTarget(context, target) }
    return ProjectedAuthorizationState(status.value, projectedTarget?.first, projectedTarget?.second, terminal)
}

private suspend fun MemScope.receiveAuthorizationActive(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
): ProjectedActive {
    val event = receiveIntegrationFlowEvent(observer, context, subscription)
    return projectAuthorizationActive(context, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun MemScope.receiveAuthorizationActiveUntil(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
    predicate: (ProjectedActive) -> Boolean,
): ProjectedActive = withTimeout(TIMEOUT_MILLIS) {
    while (true) {
        val value = receiveAuthorizationActive(context, observer, subscription)
        if (predicate(value)) return@withTimeout value
    }
    error("unreachable")
}

private fun MemScope.projectAuthorizationActive(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    terminal: Int,
): ProjectedActive {
    val hasValue = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationActiveHasValue(context, snapshot, hasValue.ptr),
    )
    val integration = emptyFlowHandle()
    if (hasValue.value == 0) {
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentIntegrationAuthorizationActiveValue(context, snapshot, integration.ptr),
        )
        assertNull(integration.value)
        assertEquals(CODEX_AGENT_STATUS_OK, destroyIntegrationFlowSnapshot(context, snapshot))
        return ProjectedActive(null, null, terminal)
    }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationAuthorizationActiveValue(context, snapshot, integration.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, destroyIntegrationFlowSnapshot(context, snapshot))
    val target = projectIntegrationTarget(context, integration)
    return ProjectedActive(target.first, target.second, terminal)
}

private suspend fun MemScope.receiveAuthorizationBoolean(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
): ProjectedBoolean {
    val event = receiveIntegrationFlowEvent(observer, context, subscription)
    return projectAuthorizationBoolean(context, assertNotNull(event.snapshot), event.terminal)
}

private suspend fun MemScope.receiveAuthorizationBooleanUntil(
    context: COpaquePointer,
    observer: IntegrationFlowObserver,
    subscription: COpaquePointer,
    expected: Boolean,
): ProjectedBoolean = withTimeout(TIMEOUT_MILLIS) {
    while (true) {
        val value = receiveAuthorizationBoolean(context, observer, subscription)
        if (value.value == expected) return@withTimeout value
    }
    error("unreachable")
}

private fun MemScope.projectAuthorizationBoolean(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    terminal: Int,
): ProjectedBoolean {
    val value = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentStateBooleanValue(context, snapshot, value.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, destroyIntegrationFlowSnapshot(context, snapshot))
    return ProjectedBoolean(value.value != 0, terminal)
}

private fun MemScope.projectIntegrationTarget(
    context: COpaquePointer,
    integration: COpaquePointerVar,
): Pair<Int, String> {
    val handle = assertNotNull(integration.value)
    val kind = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationKind(context, handle, kind.ptr))
    val concrete = emptyFlowHandle()
    val copy: (COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?) -> Int
    val destroy: (COpaquePointer?, CPointer<COpaquePointerVar>?) -> Int
    when (kind.value) {
        0 -> {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationConnector(context, handle, concrete.ptr))
            copy = ::codexAgentIntegrationConnectorIdCopy
            destroy = ::codexAgentIntegrationConnectorDestroy
        }
        1 -> {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationMcpServer(context, handle, concrete.ptr))
            copy = ::codexAgentIntegrationMcpServerIdCopy
            destroy = ::codexAgentIntegrationMcpServerDestroy
        }
        else -> error("unexpected integration kind ${kind.value}")
    }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, integration.ptr))
    val id = readIntegrationFlowString(context, assertNotNull(concrete.value), copy)
    assertEquals(CODEX_AGENT_STATUS_OK, destroy(context, concrete.ptr))
    return kind.value to id
}

private suspend fun receiveIntegrationFlowEvent(
    observer: IntegrationFlowObserver,
    context: COpaquePointer,
    subscription: COpaquePointer,
): IntegrationFlowEvent = withTimeout(TIMEOUT_MILLIS) {
    observer.events.receive().also {
        assertEquals(context, it.context)
        assertEquals(subscription, it.subscription)
        assertEquals(subscription, it.publishedSubscription)
        assertEquals(observer.userData, it.userData)
        assertEquals(CODEX_AGENT_STATUS_OK, it.status)
    }
}

private suspend fun MemScope.selectIntegrationFlowWorkspace(
    context: COpaquePointer,
    host: COpaquePointer,
    path: String,
) {
    val selection = alloc<codex_agent_path_workspace_selection>().also {
        it.struct_size = sizeOf<codex_agent_path_workspace_selection>().toUInt()
        val bytes = path.encodeToByteArray()
        it.path.size = bytes.size.toULong()
        it.path.data = allocArray<UByteVar>(bytes.size).also { buffer ->
            bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
        }
    }
    launchIntegrationFlowOperation(context) { output ->
        codexAgentHostSelectWorkspace(context, host, selection.ptr, null, null, output)
    }
}

private suspend fun MemScope.closeIntegrationFlowHost(graph: IntegrationFlowGraph) {
    launchIntegrationFlowOperation(graph.context) { output ->
        codexAgentHostClose(graph.context, graph.host.value, null, null, output)
    }
}

private suspend fun MemScope.launchIntegrationFlowOperation(
    context: COpaquePointer,
    launch: (CPointer<COpaquePointerVar>) -> Int,
) {
    val operation = emptyFlowHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, launch(operation.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, awaitIntegrationFlowOperation(context, operation.value))
    destroyIntegrationFlowOperation(context, operation.ptr)
}

private suspend fun awaitIntegrationFlowOperation(context: COpaquePointer, operation: COpaquePointer?): Int =
    withTimeout(TIMEOUT_MILLIS) {
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

private suspend fun destroyIntegrationFlowOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(TIMEOUT_MILLIS) {
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

private suspend fun destroyIntegrationFlowSubscription(
    context: COpaquePointer,
    subscription: CPointer<COpaquePointerVar>,
) {
    withTimeout(TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentSubscriptionDestroy(context, subscription)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("subscription destroy failed with $status")
            }
        }
    }
    assertNull(subscription.pointed.value)
}

private fun MemScope.integrationFlowTarget(
    context: COpaquePointer,
    target: AgentIntegration,
): COpaquePointerVar = emptyFlowHandle().also {
    val created = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.SNAPSHOT,
        CodexAgentCIntegrationSnapshot(target),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    it.value = assertNotNull(created.value)
}

private suspend fun awaitIntegrationFlowRequest(fixture: NativeCodexBehaviorFixture, method: String) {
    withTimeout(TIMEOUT_MILLIS) {
        while (fixture.additionalRequests.none { it.first == method }) yield()
    }
}

private suspend fun assertNoIntegrationFlowEvent(observer: IntegrationFlowObserver) {
    assertNull(withTimeoutOrNull(QUIET_MILLIS) { observer.events.receive() })
}

private fun MemScope.emptyFlowHandle(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun destroyIntegrationFlowSnapshot(context: COpaquePointer, snapshot: COpaquePointer): Int = memScoped {
    val slot = alloc<COpaquePointerVar>().also { it.value = snapshot }
    codexAgentSnapshotDestroy(context, slot.ptr)
}

private fun MemScope.readIntegrationFlowString(
    context: COpaquePointer,
    handle: COpaquePointer,
    copy: (COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?) -> Int,
): String {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    val buffer = allocArray<UByteVar>(required.value.toInt())
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, required.value, required.ptr))
    return ByteArray(required.value.toInt()) { buffer[it].toByte() }.decodeToString()
}

private fun connectorListResponse(): JsonObject = buildJsonObject {
    putJsonArray("data") {
        add(buildJsonObject {
            put("id", CONNECTOR_ID)
            put("name", "Drive")
            put("description", "Files")
            put("isAccessible", true)
            put("isEnabled", true)
        })
    }
}

private const val CONNECTOR_ID = "drive-flow"
private const val MCP_NAME = "drive-flow-mcp"
private const val TIMEOUT_MILLIS = 10_000L
private const val QUIET_MILLIS = 100L
