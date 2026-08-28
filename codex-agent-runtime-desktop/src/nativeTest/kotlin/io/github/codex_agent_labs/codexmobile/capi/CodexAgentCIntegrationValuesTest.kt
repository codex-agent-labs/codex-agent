@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
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

class CodexAgentCIntegrationValuesTest {
    @Test
    fun connectorIntegrationConstructorCopiesItsConnectorDependency(): Unit =
        withIntegrationContexts { context, _ ->
            val connectorSlot = createIntegrationConnector(context, "connector-id", "Connector name")
            val integrationSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorCreate(
                    context,
                    assertNotNull(connectorSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertNotNull(integrationSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            assertIntegrationString(
                context,
                assertNotNull(integrationSlot.value),
                "connector-id",
                ::codexAgentIntegrationConnectorIdCopy,
            )
            assertIntegrationString(
                context,
                assertNotNull(integrationSlot.value),
                "Connector name",
                ::codexAgentIntegrationConnectorDisplayNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr),
            )
        }

    @Test
    fun connectorIntegrationConnectorReturnsFreshIndependentlyOwnedSnapshots(): Unit =
        withIntegrationContexts { context, _ ->
            val connectorSlot = createIntegrationConnector(context, "owned-id", "Owned connector")
            val integrationSlot = emptyIntegrationHandle()
            val firstChildSlot = emptyIntegrationHandle()
            val secondChildSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorCreate(
                    context,
                    assertNotNull(connectorSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            val integration = assertNotNull(integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorConnector(context, integration, firstChildSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorConnector(context, integration, secondChildSlot.ptr),
            )
            val firstChild = assertNotNull(firstChildSlot.value)
            val secondChild = assertNotNull(secondChildSlot.value)
            assertNotEquals(firstChild, secondChild)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr),
            )
            assertIntegrationString(context, firstChild, "owned-id", ::codexAgentConnectorIdCopy)
            assertIntegrationString(context, firstChild, "Owned connector", ::codexAgentConnectorNameCopy)
            assertIntegrationString(context, firstChild, "Description", ::codexAgentConnectorDescriptionCopy)
            val flag = alloc<IntVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorHasInstallUrl(context, firstChild, flag.ptr),
            )
            assertEquals(1, flag.value)
            assertIntegrationString(
                context,
                firstChild,
                "https://example.invalid/install",
                ::codexAgentConnectorInstallUrlCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorIsAccessible(context, firstChild, flag.ptr),
            )
            assertEquals(1, flag.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorIsEnabled(context, firstChild, flag.ptr),
            )
            assertEquals(0, flag.value)
            val count = alloc<ULongVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConnectorPluginNamesCount(context, firstChild, count.ptr),
            )
            assertEquals(3uL, count.value)
            listOf("plugin-a", "plugin-a", "plugin-b").forEachIndexed { index, expected ->
                assertIntegrationStringAt(
                    context,
                    firstChild,
                    index.toULong(),
                    expected,
                    ::codexAgentConnectorPluginNamesCopyAt,
                )
            }
            assertIntegrationString(context, secondChild, "owned-id", ::codexAgentConnectorIdCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, firstChildSlot.ptr))
            assertIntegrationString(context, secondChild, "Owned connector", ::codexAgentConnectorNameCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, secondChildSlot.ptr))
        }

    @Test
    fun connectorIntegrationIdProjectsTheCanonicalConnectorId(): Unit =
        withIntegrationContexts { context, _ ->
            val connectorSlot = createIntegrationConnector(context, "canonical-id", "Display")
            val integrationSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorCreate(
                    context,
                    assertNotNull(connectorSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertIntegrationString(
                context,
                assertNotNull(integrationSlot.value),
                "canonical-id",
                ::codexAgentIntegrationConnectorIdCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
        }

    @Test
    fun connectorIntegrationDisplayNameProjectsTheCanonicalConnectorName(): Unit =
        withIntegrationContexts { context, _ ->
            val connectorSlot = createIntegrationConnector(context, "id", "Canonical display")
            val integrationSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorCreate(
                    context,
                    assertNotNull(connectorSlot.value),
                    integrationSlot.ptr,
                ),
            )
            assertIntegrationString(
                context,
                assertNotNull(integrationSlot.value),
                "Canonical display",
                ::codexAgentIntegrationConnectorDisplayNameCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
        }

    @Test
    fun connectorIntegrationRejectsInvalidContextTypeStaleAndOutputBoundaries(): Unit =
        withIntegrationContexts { context, otherContext ->
            val connectorSlot = createIntegrationConnector(context, "boundary-id", "Boundary connector")
            val connector = assertNotNull(connectorSlot.value)
            val integrationSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorCreate(context, connector, integrationSlot.ptr),
            )
            val integration = assertNotNull(integrationSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorCreate(context, connector, integrationSlot.ptr),
            )
            assertEquals(integration, integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorCreate(context, connector, null),
            )
            val invalidSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorCreate(null, connector, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorCreate(context, null, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationConnectorCreate(otherContext, connector, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationConnectorCreate(context, integration, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val childSlot = emptyIntegrationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorConnector(context, integration, childSlot.ptr),
            )
            val child = assertNotNull(childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorConnector(context, integration, childSlot.ptr),
            )
            assertEquals(child, childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorConnector(context, integration, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorConnector(null, integration, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationConnectorConnector(otherContext, integration, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationConnectorConnector(context, connector, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val required = alloc<ULongVar>().also { it.value = 83uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorIdCopy(context, integration, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorDisplayNameCopy(context, integration, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationConnectorIdCopy(otherContext, integration, null, 0uL, required.ptr),
            )
            assertEquals(83uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationConnectorIdCopy(context, connector, null, 0uL, required.ptr),
            )
            assertEquals(83uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationConnectorDisplayNameCopy(
                    otherContext,
                    integration,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(83uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationConnectorDisplayNameCopy(
                    context,
                    connector,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(83uL, required.value)

            val wrongDestroySlot = emptyIntegrationHandle().also { it.value = child }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationConnectorDestroy(context, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationConnectorDestroy(context, wrongDestroySlot.ptr),
            )
            assertEquals(child, wrongDestroySlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationConnectorDestroy(otherContext, integrationSlot.ptr),
            )
            assertEquals(integration, integrationSlot.value)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
            val staleConnector = connector
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationConnectorCreate(context, staleConnector, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val staleIntegration = integration
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr),
            )
            assertNull(integrationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationConnectorConnector(context, staleIntegration, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationConnectorIdCopy(context, staleIntegration, null, 0uL, required.ptr),
            )
            assertEquals(83uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationConnectorDisplayNameCopy(
                    context,
                    staleIntegration,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(83uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorDestroy(context, integrationSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, childSlot.ptr))
        }
}

private fun withIntegrationContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = integrationContext()
    val otherContextSlot = integrationContext()
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    try {
        block(context, otherContext)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.integrationContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyIntegrationHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.integrationView(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = value.encodeToByteArray()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
        view.size = bytes.size.toULong()
    }.ptr

private fun MemScope.createIntegrationConnector(
    context: COpaquePointer,
    id: String,
    name: String,
): COpaquePointerVar = emptyIntegrationHandle().also { slot ->
    val pluginNames = integrationViews("plugin-a", "plugin-a", "plugin-b")
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConnectorCreate(
            context,
            integrationView(id),
            integrationView(name),
            integrationView("Description"),
            1,
            integrationView("https://example.invalid/install"),
            1,
            0,
            pluginNames,
            3uL,
            slot.ptr,
        ),
    )
}

private fun MemScope.integrationViews(vararg values: String): CPointer<codex_agent_string_view> =
    allocArray<codex_agent_string_view>(values.size).also { views ->
        values.forEachIndexed { index, value ->
            val bytes = value.encodeToByteArray()
            val buffer = allocArray<UByteVar>(bytes.size)
            bytes.forEachIndexed { byteIndex, byte -> buffer[byteIndex] = byte.toUByte() }
            views[index].data = buffer
            views[index].size = bytes.size.toULong()
        }
    }

private fun MemScope.assertIntegrationString(
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

private fun MemScope.assertIntegrationStringAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    copy: (
        COpaquePointer?,
        COpaquePointer?,
        ULong,
        CPointer<UByteVar>?,
        ULong,
        CPointer<ULongVar>?,
    ) -> Int,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, index, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, index, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { byteIndex -> buffer[byteIndex].toByte() }.decodeToString(),
    )
}
