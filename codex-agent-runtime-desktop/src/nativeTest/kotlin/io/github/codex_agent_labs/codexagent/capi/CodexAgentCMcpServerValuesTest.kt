@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentMcpServerConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpTransport
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
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

class CodexAgentCMcpServerValuesTest {
    @Test
    fun agentMcpServerConstructorNamesOriginAndCanRemoveUseCanonicalValuesAndCopiedInput(): Unit =
        withMcpServerContexts { context, _ ->
            val originCases = listOf(
                0 to "user",
                1 to "workspace",
                2 to "plugin",
                3 to "managed",
                4 to "unknown",
            )
            originCases.forEachIndexed { index, (origin, label) ->
                val name = mutableMcpServerView("server_$label")
                val displayName = mutableMcpServerView("Server $label")
                val slot = emptyMcpServerHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerCreate(
                        context,
                        name.view,
                        displayName.view,
                        0,
                        null,
                        origin,
                        index % 2,
                        slot.ptr,
                    ),
                )
                val server = assertNotNull(slot.value)
                name.bytes[0] = 'X'.code.toUByte()
                displayName.bytes[0] = 'X'.code.toUByte()
                assertMcpServerString(context, server, "server_$label", ::codexAgentMcpServerNameCopy)
                assertMcpServerString(context, server, "Server $label", ::codexAgentMcpServerDisplayNameCopy)
                assertMcpServerInt(context, server, origin, ::codexAgentMcpServerOrigin)
                assertMcpServerInt(context, server, index % 2, ::codexAgentMcpServerCanRemove)
                assertMcpServerInt(context, server, 0, ::codexAgentMcpServerHasConfiguration)
                val absentConfiguration = emptyMcpServerHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_NOT_READY,
                    codexAgentMcpServerConfiguration(context, server, absentConfiguration.ptr),
                )
                assertNull(absentConfiguration.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, slot.ptr))
            }
        }

    @Test
    fun agentMcpServerAuthStatusAndIsAuthorizedProjectAllFiveCanonicalCases(): Unit =
        withMcpServerContexts { context, _ ->
            val cases = listOf(
                0 to 0,
                1 to 0,
                2 to 0,
                3 to 1,
                4 to 1,
            )
            cases.forEach { (authStatus, isAuthorized) ->
                val slot = createMcpServer(context, authStatus = authStatus)
                val server = assertNotNull(slot.value)
                assertMcpServerInt(context, server, authStatus, ::codexAgentMcpServerAuthStatus)
                assertMcpServerInt(context, server, isAuthorized, ::codexAgentMcpServerIsAuthorized)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, slot.ptr))
            }
        }

    @Test
    fun agentMcpServerConfigurationPreservesNullabilityDeepCopiesAndReturnsFreshOwnedChildren(): Unit =
        withMcpServerContexts { context, _ ->
            val arguments = mutableListOf("server.js", "--safe")
            val enabledTools = mutableListOf("read", "write")
            val tools = linkedMapOf("read" to AgentMcpToolConfiguration())
            val sourceConfiguration = AgentMcpServerConfiguration(
                name = "owned_server",
                transport = AgentMcpTransport.Stdio(command = "node", arguments = arguments),
                enabledTools = enabledTools,
                tools = tools,
            )
            val sourceSlot = createMcpServerConfigurationSnapshot(context, sourceConfiguration)
            val source = assertNotNull(sourceSlot.value)
            val serverSlot = createMcpServer(context, configuration = source)
            val server = assertNotNull(serverSlot.value)

            arguments[0] = "changed.js"
            enabledTools[0] = "changed"
            tools.clear()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, sourceSlot.ptr),
            )
            assertMcpServerInt(context, server, 1, ::codexAgentMcpServerHasConfiguration)

            val firstChildSlot = emptyMcpServerHandle()
            val secondChildSlot = emptyMcpServerHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfiguration(context, server, firstChildSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfiguration(context, server, secondChildSlot.ptr),
            )
            val firstChild = assertNotNull(firstChildSlot.value)
            val secondChild = assertNotNull(secondChildSlot.value)
            assertNotEquals(firstChild, secondChild)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, serverSlot.ptr))

            assertMcpServerConfigurationPayload(context, firstChild)
            assertMcpServerConfigurationPayload(context, secondChild)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, firstChildSlot.ptr),
            )
            assertMcpServerConfigurationPayload(context, secondChild)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, secondChildSlot.ptr),
            )
        }

    @Test
    fun agentMcpServerConstructorRejectsInvalidEnumsFlagsDependenciesAndOutputs(): Unit =
        withMcpServerContexts { context, otherContext ->
            val name = mcpServerView("server")
            val displayName = mcpServerView("Server")
            listOf(-1, 5, Int.MIN_VALUE, Int.MAX_VALUE).forEach { invalidAuthStatus ->
                val slot = emptyMcpServerHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentMcpServerCreate(
                        context,
                        name,
                        displayName,
                        invalidAuthStatus,
                        null,
                        4,
                        0,
                        slot.ptr,
                    ),
                )
                assertNull(slot.value)
            }
            listOf(-1, 5, Int.MIN_VALUE, Int.MAX_VALUE).forEach { invalidOrigin ->
                val slot = emptyMcpServerHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentMcpServerCreate(
                        context,
                        name,
                        displayName,
                        0,
                        null,
                        invalidOrigin,
                        0,
                        slot.ptr,
                    ),
                )
                assertNull(slot.value)
            }
            listOf(-1, 2, Int.MIN_VALUE, Int.MAX_VALUE).forEach { invalidCanRemove ->
                val slot = emptyMcpServerHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentMcpServerCreate(
                        context,
                        name,
                        displayName,
                        0,
                        null,
                        4,
                        invalidCanRemove,
                        slot.ptr,
                    ),
                )
                assertNull(slot.value)
            }

            val configurationSlot = createMcpServerConfigurationSnapshot(context, basicMcpServerConfiguration())
            val configuration = assertNotNull(configurationSlot.value)
            val output = emptyMcpServerHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(null, name, displayName, 0, null, 4, 0, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(context, null, displayName, 0, null, 4, 0, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(context, name, null, 0, null, 4, 0, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(context, invalidMcpServerUtf8View(), displayName, 0, null, 4, 0, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentMcpServerCreate(
                    otherContext,
                    name,
                    displayName,
                    0,
                    configuration,
                    4,
                    0,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val wrongTypeSlot = createMcpServer(context)
            val wrongType = assertNotNull(wrongTypeSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpServerCreate(context, name, displayName, 0, wrongType, 4, 0, output.ptr),
            )
            assertNull(output.value)

            val staleConfiguration = configuration
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, configurationSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentMcpServerCreate(
                    context,
                    name,
                    displayName,
                    0,
                    staleConfiguration,
                    4,
                    0,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            output.value = wrongType
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(context, name, displayName, 0, null, 4, 0, output.ptr),
            )
            assertEquals(wrongType, output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerCreate(context, name, displayName, 0, null, 4, 0, null),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, wrongTypeSlot.ptr))
        }

    @Test
    fun agentMcpServerGettersAndDestroyRejectWrongContextTypeStaleAndInvalidOutputs(): Unit =
        withMcpServerContexts { context, otherContext ->
            val configurationSlot = createMcpServerConfigurationSnapshot(context, basicMcpServerConfiguration())
            val configuration = assertNotNull(configurationSlot.value)
            val serverSlot = createMcpServer(context, configuration = configuration)
            val server = assertNotNull(serverSlot.value)
            val required = alloc<ULongVar>().also { it.value = 91uL }
            val scalar = alloc<IntVar>().also { it.value = 73 }
            val childSlot = emptyMcpServerHandle()

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerNameCopy(context, server, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerDisplayNameCopy(context, server, null, 0uL, null),
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerAuthStatus(context, server, null))
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerHasConfiguration(context, server, null),
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerConfiguration(context, server, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerOrigin(context, server, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerCanRemove(context, server, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerIsAuthorized(context, server, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpServerDestroy(context, null))

            val occupiedChildSlot = emptyMcpServerHandle().also { it.value = server }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerConfiguration(context, server, occupiedChildSlot.ptr),
            )
            assertEquals(server, occupiedChildSlot.value)

            assertMcpServerWrongContextAndType(
                context,
                otherContext,
                server,
                configuration,
                required.ptr,
                scalar.ptr,
                childSlot.ptr,
            )
            assertEquals(91uL, required.value)
            assertEquals(73, scalar.value)
            assertNull(childSlot.value)

            val wrongDestroy = emptyMcpServerHandle().also { it.value = configuration }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpServerDestroy(context, wrongDestroy.ptr),
            )
            assertEquals(configuration, wrongDestroy.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentMcpServerDestroy(otherContext, serverSlot.ptr),
            )
            assertEquals(server, serverSlot.value)

            val staleServer = server
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, serverSlot.ptr))
            assertNull(serverSlot.value)
            assertMcpServerStaleGetters(context, staleServer, required.ptr, scalar.ptr, childSlot.ptr)
            assertEquals(91uL, required.value)
            assertEquals(73, scalar.value)
            assertNull(childSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, serverSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, configurationSlot.ptr),
            )
        }

    @Test
    fun agentMcpServerDestroyIsIdempotentAndContextTeardownReclaimsOwnedSnapshots(): Unit = memScoped {
        val contextSlot = mcpServerContext()
        val context = assertNotNull(contextSlot.value)
        val configurationSlot = createMcpServerConfigurationSnapshot(context, basicMcpServerConfiguration())
        val serverSlot = createMcpServer(context, configuration = assertNotNull(configurationSlot.value))
        val server = assertNotNull(serverSlot.value)
        val childSlot = emptyMcpServerHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpServerConfiguration(context, server, childSlot.ptr),
        )
        val child = assertNotNull(childSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)

        val required = alloc<ULongVar>().also { it.value = 91uL }
        val scalar = alloc<IntVar>().also { it.value = 73 }
        val staleChildSlot = emptyMcpServerHandle()
        assertMcpServerStaleGetters(context, server, required.ptr, scalar.ptr, staleChildSlot.ptr)
        assertEquals(91uL, required.value)
        assertEquals(73, scalar.value)
        assertNull(staleChildSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpServerConfigurationNameCopy(context, child, null, 0uL, required.ptr),
        )
        assertEquals(91uL, required.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))

        val idempotentContextSlot = mcpServerContext()
        val idempotentContext = assertNotNull(idempotentContextSlot.value)
        val idempotentConfigurationSlot =
            createMcpServerConfigurationSnapshot(idempotentContext, basicMcpServerConfiguration())
        val idempotentServerSlot =
            createMcpServer(idempotentContext, configuration = assertNotNull(idempotentConfigurationSlot.value))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(idempotentContext, idempotentServerSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(idempotentContext, idempotentServerSlot.ptr))
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpServerConfigurationDestroy(idempotentContext, idempotentConfigurationSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpServerConfigurationDestroy(idempotentContext, idempotentConfigurationSlot.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(idempotentContextSlot.ptr))
        assertNull(idempotentContextSlot.value)
    }
}

private fun withMcpServerContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = mcpServerContext()
    val otherContextSlot = mcpServerContext()
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    try {
        block(context, otherContext)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.mcpServerContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyMcpServerHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private data class MutableMcpServerView(
    val bytes: CPointer<UByteVar>,
    val view: CPointer<codex_agent_string_view>,
)

private fun MemScope.mutableMcpServerView(value: String): MutableMcpServerView {
    val encoded = value.encodeToByteArray()
    val bytes = allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    val view = alloc<codex_agent_string_view>()
    view.data = bytes
    view.size = encoded.size.toULong()
    return MutableMcpServerView(bytes, view.ptr)
}

private fun MemScope.mcpServerView(value: String): CPointer<codex_agent_string_view> =
    mutableMcpServerView(value).view

private fun MemScope.invalidMcpServerUtf8View(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = allocArray<UByteVar>(1)
        bytes[0] = 0xffu
        view.data = bytes
        view.size = 1uL
    }.ptr

private fun MemScope.createMcpServer(
    context: COpaquePointer,
    authStatus: Int = 0,
    configuration: COpaquePointer? = null,
    origin: Int = 4,
    canRemove: Int = 0,
): COpaquePointerVar = emptyMcpServerHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpServerCreate(
            context,
            mcpServerView("server"),
            mcpServerView("Server"),
            authStatus,
            configuration,
            origin,
            canRemove,
            slot.ptr,
        ),
    )
}

private fun MemScope.createMcpServerConfigurationSnapshot(
    context: COpaquePointer,
    configuration: AgentMcpServerConfiguration,
): COpaquePointerVar = emptyMcpServerHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        installOutput(
            slot.ptr,
            createSnapshot(context, CodexAgentCMcpServerConfigurationSnapshot(configuration)),
        ),
    )
}

private fun basicMcpServerConfiguration(): AgentMcpServerConfiguration =
    AgentMcpServerConfiguration(
        name = "server",
        transport = AgentMcpTransport.Stdio(command = "node", arguments = listOf("server.js")),
    )

private fun MemScope.assertMcpServerString(
    context: COpaquePointer,
    server: COpaquePointer,
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
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, server, null, 0uL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, server, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { index -> buffer[index].toByte() }.decodeToString(),
    )
}

private fun MemScope.assertMcpServerInt(
    context: COpaquePointer,
    server: COpaquePointer,
    expected: Int,
    get: (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int,
) {
    val output = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, get(context, server, output.ptr))
    assertEquals(expected, output.value)
}

private fun assertMcpServerConfigurationPayload(context: COpaquePointer, configuration: COpaquePointer) {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
            context,
            configuration,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            assertEquals("owned_server", it.value.name)
            val transport = it.value.transport as AgentMcpTransport.Stdio
            assertEquals("node", transport.command)
            assertEquals(listOf("server.js", "--safe"), transport.arguments)
            assertEquals(listOf("read", "write"), it.value.enabledTools)
            assertEquals(setOf("read"), it.value.tools.keys)
            CODEX_AGENT_STATUS_OK
        },
    )
}

private fun assertMcpServerWrongContextAndType(
    context: COpaquePointer,
    otherContext: COpaquePointer,
    server: COpaquePointer,
    wrongType: COpaquePointer,
    required: CPointer<ULongVar>,
    scalar: CPointer<IntVar>,
    child: CPointer<COpaquePointerVar>,
) {
    listOf(
        codexAgentMcpServerNameCopy(otherContext, server, null, 0uL, required),
        codexAgentMcpServerDisplayNameCopy(otherContext, server, null, 0uL, required),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_WRONG_CONTEXT, it) }
    listOf(
        codexAgentMcpServerAuthStatus(otherContext, server, scalar),
        codexAgentMcpServerHasConfiguration(otherContext, server, scalar),
        codexAgentMcpServerOrigin(otherContext, server, scalar),
        codexAgentMcpServerCanRemove(otherContext, server, scalar),
        codexAgentMcpServerIsAuthorized(otherContext, server, scalar),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_WRONG_CONTEXT, it) }
    assertEquals(CODEX_AGENT_STATUS_WRONG_CONTEXT, codexAgentMcpServerConfiguration(otherContext, server, child))

    listOf(
        codexAgentMcpServerNameCopy(context, wrongType, null, 0uL, required),
        codexAgentMcpServerDisplayNameCopy(context, wrongType, null, 0uL, required),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, it) }
    listOf(
        codexAgentMcpServerAuthStatus(context, wrongType, scalar),
        codexAgentMcpServerHasConfiguration(context, wrongType, scalar),
        codexAgentMcpServerOrigin(context, wrongType, scalar),
        codexAgentMcpServerCanRemove(context, wrongType, scalar),
        codexAgentMcpServerIsAuthorized(context, wrongType, scalar),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, it) }
    assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, codexAgentMcpServerConfiguration(context, wrongType, child))
}

private fun assertMcpServerStaleGetters(
    context: COpaquePointer,
    staleServer: COpaquePointer,
    required: CPointer<ULongVar>,
    scalar: CPointer<IntVar>,
    child: CPointer<COpaquePointerVar>,
) {
    listOf(
        codexAgentMcpServerNameCopy(context, staleServer, null, 0uL, required),
        codexAgentMcpServerDisplayNameCopy(context, staleServer, null, 0uL, required),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, it) }
    listOf(
        codexAgentMcpServerAuthStatus(context, staleServer, scalar),
        codexAgentMcpServerHasConfiguration(context, staleServer, scalar),
        codexAgentMcpServerOrigin(context, staleServer, scalar),
        codexAgentMcpServerCanRemove(context, staleServer, scalar),
        codexAgentMcpServerIsAuthorized(context, staleServer, scalar),
    ).forEach { assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, it) }
    assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentMcpServerConfiguration(context, staleServer, child))
}
