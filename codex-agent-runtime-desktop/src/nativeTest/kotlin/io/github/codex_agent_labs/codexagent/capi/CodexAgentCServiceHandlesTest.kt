@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.CodexAgent
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexRuntimeFeature
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.value
import kotlinx.coroutines.runBlocking

class CodexAgentCServiceHandlesTest {
    @Test
    fun agentFacadesAreIdentityStableExactAndFailClosed(): Unit = runBlocking {
        val graph = createServiceGraph()
        val otherContext = handleRegistry.createContext().requiredServiceValue()
        try {
            memScoped {
                val occupied = emptyServiceHandle().also { it.value = graph.agentHandle }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    SERVICE_SPECS.first().accessor(graph.context, graph.agentHandle, occupied.ptr),
                )
                assertEquals(graph.agentHandle, occupied.value)
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    SERVICE_SPECS.first().accessor(graph.context, graph.agentHandle, null),
                )

                val handles = SERVICE_SPECS.map { spec ->
                    val first = emptyServiceHandle()
                    val second = emptyServiceHandle()
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        spec.accessor(graph.context, graph.hostHandle, first.ptr),
                        spec.name,
                    )
                    assertNull(first.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_CONTEXT,
                        spec.accessor(otherContext, graph.agentHandle, first.ptr),
                        spec.name,
                    )
                    assertNull(first.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.accessor(graph.context, graph.agentHandle, first.ptr),
                        spec.name,
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.accessor(graph.context, graph.agentHandle, second.ptr),
                        spec.name,
                    )
                    val firstHandle = assertNotNull(first.value, spec.name)
                    val secondHandle = assertNotNull(second.value, spec.name)
                    assertNotEquals(firstHandle, secondHandle, spec.name)
                    val firstPayload = servicePayload(graph.context, firstHandle, spec.kind)
                    val secondPayload = servicePayload(graph.context, secondHandle, spec.kind)
                    assertTrue(firstPayload === secondPayload, spec.name)
                    assertTrue(spec.core(firstPayload) === spec.expectedCore(graph.agent), spec.name)
                    ServiceHandles(first, second)
                }

                SERVICE_SPECS.forEachIndexed { index, spec ->
                    val handlesForSpec = handles[index]
                    val wrong = handles[(index + 1) % handles.size]
                    val alias = emptyServiceHandle()
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        spec.retain(graph.context, wrong.second.value, alias.ptr),
                        spec.name,
                    )
                    assertNull(alias.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_CONTEXT,
                        spec.retain(otherContext, handlesForSpec.first.value, alias.ptr),
                        spec.name,
                    )
                    assertNull(alias.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.retain(graph.context, handlesForSpec.first.value, alias.ptr),
                        spec.name,
                    )
                    assertTrue(
                        servicePayload(graph.context, assertNotNull(alias.value), spec.kind) ===
                            servicePayload(
                                graph.context,
                                assertNotNull(handlesForSpec.first.value),
                                spec.kind,
                            ),
                        spec.name,
                    )
                    assertEquals(CODEX_AGENT_STATUS_OK, spec.release(graph.context, alias.ptr), spec.name)
                    assertNull(alias.value, spec.name)
                    assertEquals(CODEX_AGENT_STATUS_OK, spec.release(graph.context, alias.ptr), spec.name)

                    val stale = assertNotNull(handlesForSpec.first.value)
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.release(graph.context, handlesForSpec.first.ptr),
                        spec.name,
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_STALE_HANDLE,
                        spec.retain(graph.context, stale, alias.ptr),
                        spec.name,
                    )
                    assertNull(alias.value, spec.name)
                }

                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    handleRegistry.invalidateChildren(
                        graph.context,
                        graph.agentHandle,
                        CodexAgentCHandleKind.AGENT,
                    ),
                )
                SERVICE_SPECS.forEachIndexed { index, spec ->
                    val alias = emptyServiceHandle()
                    assertEquals(
                        CODEX_AGENT_STATUS_STALE_HANDLE,
                        spec.retain(graph.context, handles[index].second.value, alias.ptr),
                        spec.name,
                    )
                    assertNull(alias.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.release(graph.context, handles[index].second.ptr),
                        spec.name,
                    )
                    assertNull(handles[index].second.value, spec.name)
                }
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            graph.close()
        }
    }

    @Test
    fun agentWorkspaceIsAnOwnedSnapshotAndFailsClosed(): Unit = runBlocking {
        val graph = createServiceGraph()
        val otherContext = handleRegistry.createContext().requiredServiceValue()
        try {
            memScoped {
                val workspace = emptyServiceHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                    codexAgentAgentWorkspace(graph.context, graph.hostHandle, workspace.ptr),
                )
                assertNull(workspace.value)
                assertEquals(
                    CODEX_AGENT_STATUS_WRONG_CONTEXT,
                    codexAgentAgentWorkspace(otherContext, graph.agentHandle, workspace.ptr),
                )
                assertNull(workspace.value)
                val occupied = emptyServiceHandle().also { it.value = graph.hostHandle }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAgentWorkspace(graph.context, graph.agentHandle, occupied.ptr),
                )
                assertEquals(graph.hostHandle, occupied.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAgentWorkspace(graph.context, graph.agentHandle, workspace.ptr),
                )
                val snapshotHandle = assertNotNull(workspace.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    handleRegistry.invalidateChildren(
                        graph.context,
                        graph.agentHandle,
                        CodexAgentCHandleKind.AGENT,
                    ),
                )
                val snapshot = servicePayload(
                    graph.context,
                    snapshotHandle,
                    CodexAgentCHandleKind.SNAPSHOT,
                ) as CodexAgentCWorkspaceSnapshot
                assertEquals(graph.fixture.workspace.path, snapshot.value.path)
                assertEquals(graph.fixture.workspace.displayName, snapshot.value.displayName)
                assertFalse(snapshot.value === graph.agent.workspace)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentWorkspaceDestroy(graph.context, workspace.ptr),
                )
                assertNull(workspace.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(graph.context, workspace.ptr))
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            graph.close()
        }
    }

    @Test
    fun availabilityReflectsEveryRuntimeFeatureAndPreservesFailureSentinels(): Unit = runBlocking {
        verifyAvailability(emptySet())
        verifyAvailability(AVAILABLE_FEATURES)
        AVAILABILITY_SPECS.forEach { verifyAvailability(setOf(it.feature)) }
    }

    private suspend fun verifyAvailability(features: Set<CodexRuntimeFeature>) {
        val graph = createServiceGraph(features)
        val otherContext = handleRegistry.createContext().requiredServiceValue()
        try {
            memScoped {
                val handles = AVAILABILITY_SPECS.map { spec ->
                    emptyServiceHandle().also { slot ->
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            spec.accessor(graph.context, graph.agentHandle, slot.ptr),
                            spec.name,
                        )
                    }
                }
                AVAILABILITY_SPECS.forEachIndexed { index, spec ->
                    val output = alloc<IntVar>().also { it.value = 73 }
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_CONTEXT,
                        spec.getter(otherContext, handles[index].value, output.ptr),
                        spec.name,
                    )
                    assertEquals(73, output.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        spec.getter(
                            graph.context,
                            handles[(index + 1) % handles.size].value,
                            output.ptr,
                        ),
                        spec.name,
                    )
                    assertEquals(73, output.value, spec.name)
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        spec.getter(graph.context, handles[index].value, null),
                        spec.name,
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.getter(graph.context, handles[index].value, output.ptr),
                        spec.name,
                    )
                    assertEquals(if (spec.feature in features) 1 else 0, output.value, spec.name)
                }
                AVAILABILITY_SPECS.forEachIndexed { index, spec ->
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        spec.release(graph.context, handles[index].ptr),
                        spec.name,
                    )
                }
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(otherContext))
            graph.close()
        }
    }
}

private data class ServiceGraph(
    val fixture: NativeCodexBehaviorFixture,
    val runtime: CodexAgentCContextRuntime,
    val context: COpaquePointer,
    val hostHandle: COpaquePointer,
    val agentHandle: COpaquePointer,
    val host: CodexAgentCHost,
    val agent: CodexAgent,
) {
    suspend fun close() {
        host.core.close()
        handleRegistry.release(context, agentHandle, CodexAgentCHandleKind.AGENT)
        handleRegistry.semanticClose(context, hostHandle, CodexAgentCHandleKind.HOST) {
            CODEX_AGENT_STATUS_OK
        }
        handleRegistry.release(context, hostHandle, CodexAgentCHandleKind.HOST)
        assertEquals(CODEX_AGENT_STATUS_OK, handleRegistry.destroyContext(context))
        runtime.cancel()
    }
}

private suspend fun createServiceGraph(
    features: Set<CodexRuntimeFeature> = emptySet(),
): ServiceGraph {
    val fixture = NativeCodexBehaviorFixture(features = features)
    val runtime = CodexAgentCContextRuntime()
    val context = handleRegistry.createContext(runtime).requiredServiceValue()
    val host = CodexAgentCHost(fixture.createHost(), runtime)
    val hostHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.HOST,
        host,
    ).requiredServiceValue()
    host.core.selectWorkspace(CodexPathWorkspaceSelection(fixture.workspace.path))
    val agent = (host.core.lifecycleState.value as CodexHostState.Ready).agent
    val agentHandle = handleRegistry.createEntry(
        context,
        CodexAgentCHandleKind.AGENT,
        CodexAgentCAgent(agent, host),
        hostHandle,
        CodexAgentCHandleKind.HOST,
    ).requiredServiceValue()
    return ServiceGraph(fixture, runtime, context, hostHandle, agentHandle, host, agent)
}

private data class ServiceHandles(
    val first: COpaquePointerVar,
    val second: COpaquePointerVar,
)

private data class ServiceSpec(
    val name: String,
    val kind: CodexAgentCHandleKind,
    val accessor: ServiceAccessor,
    val retain: ServiceAccessor,
    val release: ServiceRelease,
    val expectedCore: (CodexAgent) -> Any,
    val core: (Any) -> Any,
)

private data class AvailabilitySpec(
    val name: String,
    val feature: CodexRuntimeFeature,
    val accessor: ServiceAccessor,
    val getter: ServiceAvailability,
    val release: ServiceRelease,
)

private val SERVICE_SPECS = listOf(
    ServiceSpec(
        "authentication",
        CodexAgentCHandleKind.AUTHENTICATION,
        ::codexAgentAgentAuthentication,
        ::codexAgentAuthenticationRetain,
        ::codexAgentAuthenticationRelease,
        { it.authentication },
        { (it as CodexAgentCAuthentication).core },
    ),
    ServiceSpec(
        "interactions",
        CodexAgentCHandleKind.INTERACTIONS,
        ::codexAgentAgentInteractions,
        ::codexAgentInteractionsRetain,
        ::codexAgentInteractionsRelease,
        { it.interactions },
        { (it as CodexAgentCInteractions).core },
    ),
    ServiceSpec(
        "integrationAuthorization",
        CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
        ::codexAgentAgentIntegrationAuthorization,
        ::codexAgentIntegrationAuthorizationRetain,
        ::codexAgentIntegrationAuthorizationRelease,
        { it.integrationAuthorization },
        { (it as CodexAgentCIntegrationAuthorization).core },
    ),
    ServiceSpec(
        "models",
        CodexAgentCHandleKind.MODELS,
        ::codexAgentAgentModels,
        ::codexAgentModelsRetain,
        ::codexAgentModelsRelease,
        { it.models },
        { (it as CodexAgentCModels).core },
    ),
    ServiceSpec(
        "skills",
        CodexAgentCHandleKind.SKILLS,
        ::codexAgentAgentSkills,
        ::codexAgentSkillsRetain,
        ::codexAgentSkillsRelease,
        { it.skills },
        { (it as CodexAgentCSkills).core },
    ),
    ServiceSpec(
        "hooks",
        CodexAgentCHandleKind.HOOKS,
        ::codexAgentAgentHooks,
        ::codexAgentHooksRetain,
        ::codexAgentHooksRelease,
        { it.hooks },
        { (it as CodexAgentCHooks).core },
    ),
    ServiceSpec(
        "plugins",
        CodexAgentCHandleKind.PLUGINS,
        ::codexAgentAgentPlugins,
        ::codexAgentPluginsRetain,
        ::codexAgentPluginsRelease,
        { it.plugins },
        { (it as CodexAgentCPlugins).core },
    ),
    ServiceSpec(
        "connectors",
        CodexAgentCHandleKind.CONNECTORS,
        ::codexAgentAgentConnectors,
        ::codexAgentConnectorsRetain,
        ::codexAgentConnectorsRelease,
        { it.connectors },
        { (it as CodexAgentCConnectors).core },
    ),
    ServiceSpec(
        "mcpServers",
        CodexAgentCHandleKind.MCP_SERVERS,
        ::codexAgentAgentMcpServers,
        ::codexAgentMcpServersRetain,
        ::codexAgentMcpServersRelease,
        { it.mcpServers },
        { (it as CodexAgentCMcpServers).core },
    ),
)

private val AVAILABILITY_SPECS = listOf(
    AvailabilitySpec(
        "skills",
        CodexRuntimeFeature.SKILLS,
        ::codexAgentAgentSkills,
        ::codexAgentSkillsIsAvailable,
        ::codexAgentSkillsRelease,
    ),
    AvailabilitySpec(
        "hooks",
        CodexRuntimeFeature.HOOKS,
        ::codexAgentAgentHooks,
        ::codexAgentHooksIsAvailable,
        ::codexAgentHooksRelease,
    ),
    AvailabilitySpec(
        "plugins",
        CodexRuntimeFeature.PLUGINS,
        ::codexAgentAgentPlugins,
        ::codexAgentPluginsIsAvailable,
        ::codexAgentPluginsRelease,
    ),
    AvailabilitySpec(
        "connectors",
        CodexRuntimeFeature.CONNECTORS,
        ::codexAgentAgentConnectors,
        ::codexAgentConnectorsIsAvailable,
        ::codexAgentConnectorsRelease,
    ),
    AvailabilitySpec(
        "mcpServers",
        CodexRuntimeFeature.MCP_SERVERS,
        ::codexAgentAgentMcpServers,
        ::codexAgentMcpServersIsAvailable,
        ::codexAgentMcpServersRelease,
    ),
)

private val AVAILABLE_FEATURES = setOf(
    CodexRuntimeFeature.SKILLS,
    CodexRuntimeFeature.HOOKS,
    CodexRuntimeFeature.PLUGINS,
    CodexRuntimeFeature.CONNECTORS,
    CodexRuntimeFeature.MCP_SERVERS,
)

private fun MemScope.emptyServiceHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun servicePayload(
    context: COpaquePointer,
    handle: COpaquePointer,
    kind: CodexAgentCHandleKind,
): Any {
    val lease = handleRegistry.acquire(context, handle, kind).requiredServiceValue()
    return lease.payload.also { assertEquals(CODEX_AGENT_STATUS_OK, lease.close()) }
}

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredServiceValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}

private typealias ServiceAccessor = (
    COpaquePointer?, COpaquePointer?, CPointer<COpaquePointerVar>?,
) -> Int

private typealias ServiceRelease = (
    COpaquePointer?, CPointer<COpaquePointerVar>?,
) -> Int

private typealias ServiceAvailability = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?,
) -> Int
