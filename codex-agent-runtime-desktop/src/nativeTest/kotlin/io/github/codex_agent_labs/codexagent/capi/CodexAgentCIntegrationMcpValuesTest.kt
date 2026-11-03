@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthentication
import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexagent.agent.AgentMcpOauthConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServer
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServerConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolApproval
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolExposureSurface
import io.github.codex_agent_labs.codexagent.agent.AgentMcpTransport
import io.github.codex_agent_labs.codexagent.agent.AgentResourceOrigin
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
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCIntegrationMcpValuesTest {
    @Test
    fun mcpServerIntegrationConstructorCopiesItsServerDependency(): Unit =
        withIntegrationMcpContexts { context, _ ->
            val fixture = mutableIntegrationMcpServerFixture()
            val sourceSlot = integrationMcpServerSource(context, fixture.server)
            val integrationSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(
                    context,
                    assertNotNull(sourceSlot.value),
                    integrationSlot.ptr,
                ),
            )
            fixture.mutateCallerCollections()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, sourceSlot.ptr))
            assertIntegrationMcpString(
                context,
                assertNotNull(integrationSlot.value),
                EXPECTED_MCP_SERVER.name,
                ::codexAgentIntegrationMcpServerIdCopy,
            )
            assertIntegrationMcpString(
                context,
                assertNotNull(integrationSlot.value),
                EXPECTED_MCP_SERVER.displayName,
                ::codexAgentIntegrationMcpServerDisplayNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )
        }

    @Test
    fun mcpServerIntegrationServerReturnsFreshCompleteIndependentlyOwnedSnapshots(): Unit =
        withIntegrationMcpContexts { context, _ ->
            val fixture = mutableIntegrationMcpServerFixture()
            val sourceSlot = integrationMcpServerSource(context, fixture.server)
            val integrationSlot = emptyIntegrationMcpHandle()
            val firstChildSlot = emptyIntegrationMcpHandle()
            val secondChildSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(
                    context,
                    assertNotNull(sourceSlot.value),
                    integrationSlot.ptr,
                ),
            )
            fixture.mutateCallerCollections()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, sourceSlot.ptr))
            val integration = assertNotNull(integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerServer(context, integration, firstChildSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerServer(context, integration, secondChildSlot.ptr),
            )
            val firstChild = assertNotNull(firstChildSlot.value)
            val secondChild = assertNotNull(secondChildSlot.value)
            assertNotEquals(firstChild, secondChild)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )

            assertCompleteIntegrationMcpServer(context, firstChild, EXPECTED_MCP_SERVER)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, firstChildSlot.ptr))
            assertCompleteIntegrationMcpServer(context, secondChild, EXPECTED_MCP_SERVER)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, secondChildSlot.ptr))

            val absentSourceSlot = integrationMcpServerSource(
                context,
                AgentMcpServer("absent", "Absent configuration", AgentMcpAuthStatus.NOT_LOGGED_IN),
            )
            val absentIntegrationSlot = emptyIntegrationMcpHandle()
            val absentChildSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(
                    context,
                    assertNotNull(absentSourceSlot.value),
                    absentIntegrationSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, absentSourceSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerServer(
                    context,
                    assertNotNull(absentIntegrationSlot.value),
                    absentChildSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, absentIntegrationSlot.ptr),
            )
            var visitedAbsent = false
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                withPayload<CodexAgentCMcpServerSnapshot>(
                    context,
                    assertNotNull(absentChildSlot.value),
                    CodexAgentCHandleKind.SNAPSHOT,
                ) {
                    assertNull(it.value.configuration)
                    visitedAbsent = true
                    CODEX_AGENT_STATUS_OK
                },
            )
            assertTrue(visitedAbsent)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, absentChildSlot.ptr))
        }

    @Test
    fun mcpServerIntegrationIdProjectsTheCanonicalServerName(): Unit =
        withIntegrationMcpContexts { context, _ ->
            val sourceSlot = integrationMcpServerSource(context, EXPECTED_MCP_SERVER)
            val integrationSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(
                    context,
                    assertNotNull(sourceSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertIntegrationMcpString(
                context,
                assertNotNull(integrationSlot.value),
                "server_id",
                ::codexAgentIntegrationMcpServerIdCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, sourceSlot.ptr))
        }

    @Test
    fun mcpServerIntegrationDisplayNameProjectsTheCanonicalServerDisplayName(): Unit =
        withIntegrationMcpContexts { context, _ ->
            val sourceSlot = integrationMcpServerSource(context, EXPECTED_MCP_SERVER)
            val integrationSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(
                    context,
                    assertNotNull(sourceSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertIntegrationMcpString(
                context,
                assertNotNull(integrationSlot.value),
                "Server display",
                ::codexAgentIntegrationMcpServerDisplayNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, sourceSlot.ptr))
        }

    @Test
    fun mcpServerIntegrationRejectsInvalidContextTypeStaleAndOutputBoundaries(): Unit =
        withIntegrationMcpContexts { context, otherContext ->
            val sourceSlot = integrationMcpServerSource(context, EXPECTED_MCP_SERVER)
            val source = assertNotNull(sourceSlot.value)
            val integrationSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerCreate(context, source, integrationSlot.ptr),
            )
            val integration = assertNotNull(integrationSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerCreate(context, source, integrationSlot.ptr),
            )
            assertEquals(integration, integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerCreate(context, source, null),
            )
            val invalidSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerCreate(null, source, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerCreate(context, null, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationMcpServerCreate(otherContext, source, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationMcpServerCreate(context, integration, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val childSlot = emptyIntegrationMcpHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerServer(context, integration, childSlot.ptr),
            )
            val child = assertNotNull(childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerServer(context, integration, childSlot.ptr),
            )
            assertEquals(child, childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerServer(context, integration, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerServer(null, integration, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationMcpServerServer(otherContext, integration, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationMcpServerServer(context, source, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val required = alloc<ULongVar>().also { it.value = 97uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerIdCopy(context, integration, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerDisplayNameCopy(context, integration, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationMcpServerIdCopy(otherContext, integration, null, 0uL, required.ptr),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationMcpServerIdCopy(context, source, null, 0uL, required.ptr),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationMcpServerDisplayNameCopy(
                    otherContext,
                    integration,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationMcpServerDisplayNameCopy(
                    context,
                    source,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)

            val wrongDestroySlot = emptyIntegrationMcpHandle().also { it.value = child }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationMcpServerDestroy(context, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationMcpServerDestroy(context, wrongDestroySlot.ptr),
            )
            assertEquals(child, wrongDestroySlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationMcpServerDestroy(otherContext, integrationSlot.ptr),
            )
            assertEquals(integration, integrationSlot.value)

            val staleSource = source
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, sourceSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationMcpServerCreate(context, staleSource, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val staleIntegration = integration
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )
            assertNull(integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationMcpServerServer(context, staleIntegration, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationMcpServerIdCopy(context, staleIntegration, null, 0uL, required.ptr),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationMcpServerDisplayNameCopy(
                    context,
                    staleIntegration,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, integrationSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, childSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, childSlot.ptr))
        }
}

private val EXPECTED_MCP_SERVER: AgentMcpServer = AgentMcpServer(
    name = "server_id",
    displayName = "Server display",
    authStatus = AgentMcpAuthStatus.OAUTH,
    configuration = AgentMcpServerConfiguration(
        name = "server_config",
        transport = AgentMcpTransport.Http(
            url = "https://mcp.example.invalid/api",
            bearerTokenEnvironmentVariable = "MCP_TOKEN",
            headers = linkedMapOf("header-a" to "value-a", "header-b" to "value-b"),
            environmentHeaders = linkedMapOf("X-Token" to "MCP_TOKEN", "X-Trace" to "TRACE_ID"),
            headersHelper = "headers-helper",
        ),
        authentication = AgentMcpAuthentication.OAUTH,
        environmentId = "local",
        isEnabled = false,
        isRequired = true,
        supportsParallelToolCalls = true,
        omitToolsFrom = listOf(
            AgentMcpToolExposureSurface.DIRECT,
            AgentMcpToolExposureSurface.CODE_MODE,
        ),
        startupTimeoutSeconds = 3.5,
        toolTimeoutSeconds = 7.25,
        defaultToolApproval = AgentMcpToolApproval.WRITES,
        enabledTools = listOf("tool-a", "tool-a", "tool-b"),
        disabledTools = listOf("tool-c"),
        scopes = listOf("scope-a", "scope-b"),
        oauth = AgentMcpOauthConfiguration(clientId = "client-id", callbackPort = 4321),
        oauthResource = "https://resource.example.invalid/",
        tools = linkedMapOf(
            "tool-a" to AgentMcpToolConfiguration(AgentMcpToolApproval.APPROVE),
            "tool-b" to AgentMcpToolConfiguration(),
        ),
    ),
    origin = AgentResourceOrigin.WORKSPACE,
    canRemove = true,
)

private data class MutableIntegrationMcpServerFixture(
    val server: AgentMcpServer,
    val headers: MutableMap<String, String>,
    val environmentHeaders: MutableMap<String, String>,
    val omitToolsFrom: MutableList<AgentMcpToolExposureSurface>,
    val enabledTools: MutableList<String>,
    val disabledTools: MutableList<String>,
    val scopes: MutableList<String>,
    val tools: MutableMap<String, AgentMcpToolConfiguration>,
) {
    fun mutateCallerCollections() {
        headers.clear()
        environmentHeaders["mutated"] = "mutated"
        omitToolsFrom.clear()
        enabledTools += "mutated"
        disabledTools.clear()
        scopes.reverse()
        tools.clear()
    }
}

private fun mutableIntegrationMcpServerFixture(): MutableIntegrationMcpServerFixture {
    val headers = linkedMapOf("header-a" to "value-a", "header-b" to "value-b")
    val environmentHeaders = linkedMapOf("X-Token" to "MCP_TOKEN", "X-Trace" to "TRACE_ID")
    val omitToolsFrom = mutableListOf(
        AgentMcpToolExposureSurface.DIRECT,
        AgentMcpToolExposureSurface.CODE_MODE,
    )
    val enabledTools = mutableListOf("tool-a", "tool-a", "tool-b")
    val disabledTools = mutableListOf("tool-c")
    val scopes = mutableListOf("scope-a", "scope-b")
    val tools = linkedMapOf(
        "tool-a" to AgentMcpToolConfiguration(AgentMcpToolApproval.APPROVE),
        "tool-b" to AgentMcpToolConfiguration(),
    )
    return MutableIntegrationMcpServerFixture(
        server = AgentMcpServer(
            name = "server_id",
            displayName = "Server display",
            authStatus = AgentMcpAuthStatus.OAUTH,
            configuration = AgentMcpServerConfiguration(
                name = "server_config",
                transport = AgentMcpTransport.Http(
                    url = "https://mcp.example.invalid/api",
                    bearerTokenEnvironmentVariable = "MCP_TOKEN",
                    headers = headers,
                    environmentHeaders = environmentHeaders,
                    headersHelper = "headers-helper",
                ),
                authentication = AgentMcpAuthentication.OAUTH,
                environmentId = "local",
                isEnabled = false,
                isRequired = true,
                supportsParallelToolCalls = true,
                omitToolsFrom = omitToolsFrom,
                startupTimeoutSeconds = 3.5,
                toolTimeoutSeconds = 7.25,
                defaultToolApproval = AgentMcpToolApproval.WRITES,
                enabledTools = enabledTools,
                disabledTools = disabledTools,
                scopes = scopes,
                oauth = AgentMcpOauthConfiguration(clientId = "client-id", callbackPort = 4321),
                oauthResource = "https://resource.example.invalid/",
                tools = tools,
            ),
            origin = AgentResourceOrigin.WORKSPACE,
            canRemove = true,
        ),
        headers = headers,
        environmentHeaders = environmentHeaders,
        omitToolsFrom = omitToolsFrom,
        enabledTools = enabledTools,
        disabledTools = disabledTools,
        scopes = scopes,
        tools = tools,
    )
}

private fun withIntegrationMcpContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = integrationMcpContext()
    val otherContextSlot = integrationMcpContext()
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    try {
        block(context, otherContext)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.integrationMcpContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyIntegrationMcpHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.integrationMcpServerSource(
    context: COpaquePointer,
    server: AgentMcpServer,
): COpaquePointerVar = emptyIntegrationMcpHandle().also { slot ->
    val created = createSnapshot(context, CodexAgentCMcpServerSnapshot(server))
    assertEquals(CODEX_AGENT_STATUS_OK, created.status)
    slot.value = assertNotNull(created.value)
}

private fun MemScope.assertCompleteIntegrationMcpServer(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: AgentMcpServer,
) {
    var visited = false
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        withPayload<CodexAgentCMcpServerSnapshot>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { snapshot ->
            val actual = snapshot.value
            assertEquals(expected, actual)
            assertEquals(expected.name, actual.name)
            assertEquals(expected.displayName, actual.displayName)
            assertEquals(expected.authStatus, actual.authStatus)
            assertEquals(expected.origin, actual.origin)
            assertEquals(expected.canRemove, actual.canRemove)
            assertEquals(expected.isAuthorized, actual.isAuthorized)
            assertFalse(actual === expected)
            val expectedConfiguration = assertNotNull(expected.configuration)
            val actualConfiguration = assertNotNull(actual.configuration)
            assertFalse(actualConfiguration === expectedConfiguration)
            assertEquals(expectedConfiguration.name, actualConfiguration.name)
            assertEquals(expectedConfiguration.authentication, actualConfiguration.authentication)
            assertEquals(expectedConfiguration.environmentId, actualConfiguration.environmentId)
            assertEquals(expectedConfiguration.isEnabled, actualConfiguration.isEnabled)
            assertEquals(expectedConfiguration.isRequired, actualConfiguration.isRequired)
            assertEquals(
                expectedConfiguration.supportsParallelToolCalls,
                actualConfiguration.supportsParallelToolCalls,
            )
            assertEquals(expectedConfiguration.omitToolsFrom, actualConfiguration.omitToolsFrom)
            assertEquals(expectedConfiguration.startupTimeoutSeconds, actualConfiguration.startupTimeoutSeconds)
            assertEquals(expectedConfiguration.toolTimeoutSeconds, actualConfiguration.toolTimeoutSeconds)
            assertEquals(expectedConfiguration.defaultToolApproval, actualConfiguration.defaultToolApproval)
            assertEquals(expectedConfiguration.enabledTools, actualConfiguration.enabledTools)
            assertEquals(expectedConfiguration.disabledTools, actualConfiguration.disabledTools)
            assertEquals(expectedConfiguration.scopes, actualConfiguration.scopes)
            assertEquals(expectedConfiguration.oauth, actualConfiguration.oauth)
            assertEquals(expectedConfiguration.oauthResource, actualConfiguration.oauthResource)
            assertEquals(expectedConfiguration.tools, actualConfiguration.tools)
            val expectedTransport = expectedConfiguration.transport as AgentMcpTransport.Http
            val actualTransport = actualConfiguration.transport as AgentMcpTransport.Http
            assertFalse(actualTransport === expectedTransport)
            assertEquals(expectedTransport.url, actualTransport.url)
            assertEquals(
                expectedTransport.bearerTokenEnvironmentVariable,
                actualTransport.bearerTokenEnvironmentVariable,
            )
            assertEquals(expectedTransport.headers, actualTransport.headers)
            assertEquals(expectedTransport.environmentHeaders, actualTransport.environmentHeaders)
            assertEquals(expectedTransport.headersHelper, actualTransport.headersHelper)
            visited = true
            CODEX_AGENT_STATUS_OK
        },
    )
    assertTrue(visited)
}

private fun MemScope.assertIntegrationMcpString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: (
        COpaquePointer?,
        COpaquePointer?,
        CPointer<UByteVar>?,
        ULong,
        CPointer<ULongVar>?,
    ) -> Int,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { index -> buffer[index].toByte() }.decodeToString(),
    )
}
