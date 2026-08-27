@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.DoubleVar
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

class CodexAgentCFormHookValuesTest {
    @Test
    fun projectsBooleanNumberAndTextFormValuesExactly(): Unit = withTwoContexts { context, _ ->
        listOf(0, 1).forEach { expected ->
            val slot = emptyHandleSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormBooleanValueCreate(context, expected, slot.ptr))
            val projected = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormBooleanValueValue(context, assertNotNull(slot.value), projected.ptr),
            )
            assertEquals(expected, projected.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormBooleanValueDestroy(context, slot.ptr))
            assertNull(slot.value)
        }

        listOf(12.5, Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY, Double.NaN).forEach { expected ->
            val slot = emptyHandleSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormNumberValueCreate(context, expected, slot.ptr))
            val projected = alloc<DoubleVar>().also { it.value = 0.0 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormNumberValueValue(context, assertNotNull(slot.value), projected.ptr),
            )
            if (expected.isNaN()) {
                assertTrue(projected.value.isNaN())
            } else {
                assertEquals(expected.toBits(), projected.value.toBits())
            }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormNumberValueDestroy(context, slot.ptr))
            assertNull(slot.value)
        }

        val text = utf8View("copied text")
        val textSlot = emptyHandleSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueCreate(context, text.view, textSlot.ptr))
        text.bytes!![0] = 'X'.code.toUByte()
        assertCopiedString(
            context,
            assertNotNull(textSlot.value),
            "copied text",
            ::codexAgentFormTextValueValueCopy,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textSlot.ptr))
        assertNull(textSlot.value)
    }

    @Test
    fun projectsEveryHookHandlerVariantExactly(): Unit = withTwoContexts { context, _ ->
        val agentOne = emptyHandleSlot()
        val agentTwo = emptyHandleSlot()
        val promptOne = emptyHandleSlot()
        val promptTwo = emptyHandleSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentAcquire(context, agentOne.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentAcquire(context, agentTwo.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptAcquire(context, promptOne.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptAcquire(context, promptTwo.ptr))
        assertNotEquals(agentOne.value, agentTwo.value)
        assertNotEquals(promptOne.value, promptTwo.value)
        assertNotEquals(agentOne.value, promptOne.value)

        listOf(0, 1).forEach { isAsync ->
            val command = utf8View("command-$isAsync")
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHookHandlerCommandCreate(context, command.view, isAsync, slot.ptr),
            )
            val handler = assertNotNull(slot.value)
            command.bytes!![0] = 'X'.code.toUByte()
            assertCopiedString(
                context,
                handler,
                "command-$isAsync",
                ::codexAgentHookHandlerCommandCommandCopy,
            )
            val projected = alloc<IntVar>().also { it.value = -1 }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerCommandIsAsync(context, handler, projected.ptr))
            assertEquals(isAsync, projected.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerCommandDestroy(context, slot.ptr))
        }

        val server = utf8View("server")
        val tool = utf8View("tool")
        val mcpSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookHandlerMcpToolCreate(context, server.view, tool.view, mcpSlot.ptr),
        )
        val mcp = assertNotNull(mcpSlot.value)
        server.bytes!![0] = 'X'.code.toUByte()
        tool.bytes!![0] = 'X'.code.toUByte()
        assertCopiedString(context, mcp, "server", ::codexAgentHookHandlerMcpToolServerCopy)
        assertCopiedString(context, mcp, "tool", ::codexAgentHookHandlerMcpToolToolCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerMcpToolDestroy(context, mcpSlot.ptr))

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentDestroy(context, agentOne.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentDestroy(context, agentTwo.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptDestroy(context, promptOne.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptDestroy(context, promptTwo.ptr))
    }

    @Test
    fun rejectsInvalidViewsFlagsAndOutputSlots(): Unit = withTwoContexts { context, _ ->
        val slot = emptyHandleSlot()
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormBooleanValueCreate(context, -1, slot.ptr))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormBooleanValueCreate(context, 2, slot.ptr))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormTextValueCreate(context, null, slot.ptr))
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormTextValueCreate(context, invalidUtf8View(), slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerCommandCreate(context, utf8View("command").view, -1, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerCommandCreate(context, utf8View("command").view, 2, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerCommandCreate(context, invalidUtf8View(), 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerMcpToolCreate(context, null, utf8View("tool").view, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerMcpToolCreate(context, utf8View("server").view, null, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerMcpToolCreate(context, invalidUtf8View(), utf8View("tool").view, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerMcpToolCreate(context, utf8View("server").view, invalidUtf8View(), slot.ptr),
        )

        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormBooleanValueCreate(context, 0, null))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormNumberValueCreate(context, 1.0, null))
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormTextValueCreate(context, utf8View("text").view, null),
        )
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookHandlerAgentAcquire(context, null))
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerCommandCreate(context, utf8View("command").view, 0, null),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookHandlerMcpToolCreate(
                context,
                utf8View("server").view,
                utf8View("tool").view,
                null,
            ),
        )
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookHandlerPromptAcquire(context, null))

        slot.value = context
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormBooleanValueCreate(context, 0, slot.ptr))
        assertEquals(context, slot.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookHandlerAgentAcquire(context, slot.ptr))
        assertEquals(context, slot.value)
    }

    @Test
    fun rejectsWrongContextPayloadAndStaleHandles(): Unit = withTwoContexts { context, otherContext ->
        val textSlot = emptyHandleSlot()
        val commandSlot = emptyHandleSlot()
        val promptSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormTextValueCreate(context, utf8View("text").view, textSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookHandlerCommandCreate(context, utf8View("command").view, 1, commandSlot.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptAcquire(context, promptSlot.ptr))
        val text = assertNotNull(textSlot.value)
        val command = assertNotNull(commandSlot.value)
        val prompt = assertNotNull(promptSlot.value)
        val required = alloc<ULongVar>().also { it.value = 71uL }
        val projected = alloc<IntVar>().also { it.value = 73 }

        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormBooleanValueValue(context, text, null))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormNumberValueValue(context, text, null))
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormTextValueValueCopy(context, text, null, 0uL, null),
        )

        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentFormTextValueValueCopy(otherContext, text, null, 0uL, required.ptr),
        )
        assertEquals(71uL, required.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentHookHandlerCommandCommandCopy(context, text, null, 0uL, required.ptr),
        )
        assertEquals(71uL, required.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentHookHandlerCommandIsAsync(context, prompt, projected.ptr),
        )
        assertEquals(73, projected.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentFormTextValueDestroy(context, commandSlot.ptr),
        )
        assertEquals(command, commandSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentHookHandlerAgentDestroy(context, promptSlot.ptr),
        )
        assertEquals(prompt, promptSlot.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookHandlerCommandIsAsync(context, command, null))

        val stale = text
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textSlot.ptr))
        assertNull(textSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textSlot.ptr))
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentFormTextValueValueCopy(context, stale, null, 0uL, required.ptr),
        )
        assertEquals(71uL, required.value)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerCommandDestroy(context, commandSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptDestroy(context, promptSlot.ptr))
    }
}

private data class FormHookTestStringView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private typealias FormHookStringCopyFunction = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private fun withTwoContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyHandleSlot()
    val otherContextSlot = emptyHandleSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContextSlot.ptr))
    try {
        block(assertNotNull(contextSlot.value), assertNotNull(otherContextSlot.value))
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(otherContextSlot.value)
        assertNull(contextSlot.value)
    }
}

private fun MemScope.emptyHandleSlot(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.utf8View(value: String): FormHookTestStringView {
    val encoded = value.encodeToByteArray()
    if (encoded.isEmpty()) {
        return FormHookTestStringView(
            alloc<codex_agent_string_view>().also {
                it.data = null
                it.size = 0uL
            }.ptr,
            null,
        )
    }
    val bytes = allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    return FormHookTestStringView(
        alloc<codex_agent_string_view>().also {
            it.data = bytes
            it.size = encoded.size.toULong()
        }.ptr,
        bytes,
    )
}

private fun MemScope.invalidUtf8View(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    return alloc<codex_agent_string_view>().also {
        it.data = bytes
        it.size = 2uL
    }.ptr
}

private fun MemScope.assertCopiedString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: FormHookStringCopyFunction,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(maxOf(1, expectedBytes.size))
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr))
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString(),
    )
}
