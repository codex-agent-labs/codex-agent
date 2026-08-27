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

class CodexAgentCListLeafValuesTest {
    @Test
    fun textListCopiesOrderedDuplicateUtf8ValuesAndProjectsEmpty(): Unit = withListLeafContexts { context, _ ->
        val emptySlot = emptyListLeafHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormTextListValueCreate(context, null, 0uL, emptySlot.ptr),
        )
        val empty = assertNotNull(emptySlot.value)
        assertListLeafCount(context, empty, 0uL, ::codexAgentFormTextListValueCount)
        val required = alloc<ULongVar>().also { it.value = 71uL }
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormTextListValueCopyAt(context, empty, 0uL, null, 0uL, required.ptr),
        )
        assertEquals(71uL, required.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, emptySlot.ptr))

        val input = stringViewArray("alpha", "βeta", "alpha", "")
        val slot = emptyListLeafHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormTextListValueCreate(context, input.views, 4uL, slot.ptr),
        )
        val value = assertNotNull(slot.value)
        input.bytes[0]?.set(0, 'X'.code.toUByte())
        val replacement = utf8Bytes("changed")
        input.views[1].data = replacement
        input.views[1].size = "changed".length.toULong()
        assertListLeafCount(context, value, 4uL, ::codexAgentFormTextListValueCount)
        listOf("alpha", "βeta", "alpha", "").forEachIndexed { index, expected ->
            assertIndexedString(context, value, index.toULong(), expected)
        }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, slot.ptr))
        assertNull(slot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, slot.ptr))
    }

    @Test
    fun textListRejectsMalformedArraysBoundsOutputsContextTypeAndStaleHandles(): Unit =
        withListLeafContexts { context, otherContext ->
            val malformedSlot = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, malformedStringViewArray(), 1uL, malformedSlot.ptr),
            )
            assertNull(malformedSlot.value)

            val input = stringViewArray("value")
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, null, 1uL, malformedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, input.views, 0uL, malformedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, input.views, ULong.MAX_VALUE, malformedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, input.views, 1uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(null, input.views, 1uL, malformedSlot.ptr),
            )

            val slot = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormTextListValueCreate(context, input.views, 1uL, slot.ptr),
            )
            val value = assertNotNull(slot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCreate(context, input.views, 1uL, slot.ptr),
            )
            assertEquals(value, slot.value)

            val count = alloc<ULongVar>().also { it.value = 83uL }
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormTextListValueCount(context, value, null))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentFormTextListValueCount(otherContext, value, count.ptr),
            )
            assertEquals(83uL, count.value)
            val required = alloc<ULongVar>().also { it.value = 89uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCopyAt(context, value, 1uL, null, 0uL, required.ptr),
            )
            assertEquals(89uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormTextListValueCopyAt(context, value, 0uL, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentFormTextListValueCopyAt(otherContext, value, 0uL, null, 0uL, required.ptr),
            )
            assertEquals(89uL, required.value)

            val validationSlot = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationCreate(context, null, 0uL, validationSlot.ptr),
            )
            val validation = assertNotNull(validationSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentFormTextListValueCount(context, validation, count.ptr),
            )
            assertEquals(83uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentFormTextListValueCopyAt(context, validation, 0uL, null, 0uL, required.ptr),
            )
            assertEquals(89uL, required.value)
            val wrongSlot = emptyListLeafHandleSlot().also { it.value = validation }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentFormTextListValueDestroy(context, wrongSlot.ptr),
            )
            assertEquals(validation, wrongSlot.value)

            val stale = value
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentFormTextListValueCount(context, stale, count.ptr))
            assertEquals(83uL, count.value)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormTextListValueDestroy(context, null))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationDestroy(context, validationSlot.ptr),
            )
        }

    @Test
    fun validationCopiesOrderedDuplicateIssuesAndReturnsIndependentChildren(): Unit =
        withListLeafContexts { context, _ ->
            val firstSlot = createValidationIssue(context, "first", 0)
            val secondSlot = createValidationIssue(context, "second", 9)
            val first = assertNotNull(firstSlot.value)
            val second = assertNotNull(secondSlot.value)
            val inputs = allocArray<COpaquePointerVar>(3)
            inputs[0] = first
            inputs[1] = second
            inputs[2] = first
            val validationSlot = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationCreate(context, inputs, 3uL, validationSlot.ptr),
            )
            val validation = assertNotNull(validationSlot.value)
            inputs[0] = null
            inputs[1] = null
            inputs[2] = null
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, firstSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, secondSlot.ptr))

            assertListLeafCount(context, validation, 3uL, ::codexAgentElicitationValidationIssueCount)
            assertValidationFlag(context, validation, 0)
            val children = List(3) { emptyListLeafHandleSlot() }
            listOf("first" to 0, "second" to 9, "first" to 0).forEachIndexed { index, expected ->
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentElicitationValidationIssueAt(
                        context,
                        validation,
                        index.toULong(),
                        children[index].ptr,
                    ),
                )
                assertValidationIssue(context, assertNotNull(children[index].value), expected.first, expected.second)
            }
            assertNotEquals(children[0].value, children[2].value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationDestroy(context, validationSlot.ptr),
            )
            children.forEachIndexed { index, child ->
                val expected = if (index == 1) "second" to 9 else "first" to 0
                assertValidationIssue(context, assertNotNull(child.value), expected.first, expected.second)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, child.ptr))
            }

            val emptySlot = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationCreate(context, null, 0uL, emptySlot.ptr),
            )
            val empty = assertNotNull(emptySlot.value)
            assertListLeafCount(context, empty, 0uL, ::codexAgentElicitationValidationIssueCount)
            assertValidationFlag(context, empty, 1)
            val child = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationIssueAt(context, empty, 0uL, child.ptr),
            )
            assertNull(child.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationDestroy(context, emptySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationDestroy(context, emptySlot.ptr))
        }

    @Test
    fun validationRejectsArrayOutputContextTypeAndStaleHandleFailures(): Unit =
        withListLeafContexts { context, otherContext ->
            val issueSlot = createValidationIssue(context, "field", 1)
            val issue = assertNotNull(issueSlot.value)
            val issues = allocArray<COpaquePointerVar>(1)
            issues[0] = issue
            val output = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationCreate(context, null, 1uL, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationCreate(context, issues, 0uL, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationCreate(context, issues, ULong.MAX_VALUE, output.ptr),
            )
            issues[0] = null
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )
            issues[0] = issue

            val otherIssueSlot = createValidationIssue(otherContext, "other", 2)
            issues[0] = assertNotNull(otherIssueSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )

            val textSlot = emptyListLeafHandleSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueCreate(context, null, 0uL, textSlot.ptr))
            val text = assertNotNull(textSlot.value)
            issues[0] = text
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )

            val staleIssueSlot = createValidationIssue(context, "stale", 3)
            val staleIssue = assertNotNull(staleIssueSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationIssueDestroy(context, staleIssueSlot.ptr),
            )
            issues[0] = staleIssue
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )
            assertNull(output.value)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentElicitationValidationCreate(context, null, 0uL, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentElicitationValidationCreate(null, null, 0uL, output.ptr))

            issues[0] = issue
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )
            val validation = assertNotNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationCreate(context, issues, 1uL, output.ptr),
            )
            assertEquals(validation, output.value)

            val count = alloc<ULongVar>().also { it.value = 97uL }
            val isValid = alloc<IntVar>().also { it.value = 101 }
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentElicitationValidationIssueCount(context, validation, null))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentElicitationValidationIsValid(context, validation, null))
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationValidationIssueCount(otherContext, validation, count.ptr),
            )
            assertEquals(97uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationValidationIsValid(otherContext, validation, isValid.ptr),
            )
            assertEquals(101, isValid.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentElicitationValidationIssueCount(context, text, count.ptr),
            )
            assertEquals(97uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentElicitationValidationIsValid(context, text, isValid.ptr),
            )
            assertEquals(101, isValid.value)

            val child = emptyListLeafHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationIssueAt(context, validation, 1uL, child.ptr),
            )
            assertNull(child.value)
            child.value = issue
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationIssueAt(context, validation, 0uL, child.ptr),
            )
            assertEquals(issue, child.value)
            child.value = null
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationValidationIssueAt(otherContext, validation, 0uL, child.ptr),
            )
            assertNull(child.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidationIssueAt(context, validation, 0uL, null),
            )

            val wrongDestroy = emptyListLeafHandleSlot().also { it.value = text }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentElicitationValidationDestroy(context, wrongDestroy.ptr),
            )
            assertEquals(text, wrongDestroy.value)
            val wrongContextDestroy = emptyListLeafHandleSlot().also { it.value = validation }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationValidationDestroy(otherContext, wrongContextDestroy.ptr),
            )
            assertEquals(validation, wrongContextDestroy.value)

            val stale = validation
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationDestroy(context, output.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentElicitationValidationIssueCount(context, stale, count.ptr),
            )
            assertEquals(97uL, count.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationDestroy(context, output.ptr))
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentElicitationValidationDestroy(context, null))

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, textSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, issueSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationIssueDestroy(otherContext, otherIssueSlot.ptr),
            )
        }
}

private data class ListLeafStringArray(
    val views: CPointer<codex_agent_string_view>,
    val bytes: List<CPointer<UByteVar>?>,
)

private typealias ListLeafCountFunction = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<ULongVar>?,
) -> Int

private fun withListLeafContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyListLeafHandleSlot()
    val otherContextSlot = emptyListLeafHandleSlot()
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

private fun MemScope.emptyListLeafHandleSlot(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.utf8Bytes(value: String): CPointer<UByteVar>? {
    val encoded = value.encodeToByteArray()
    if (encoded.isEmpty()) return null
    return allocArray<UByteVar>(encoded.size).also { bytes ->
        encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    }
}

private fun MemScope.stringViewArray(vararg values: String): ListLeafStringArray {
    val views = allocArray<codex_agent_string_view>(values.size)
    val bytes = values.mapIndexed { index, value ->
        utf8Bytes(value).also {
            views[index].data = it
            views[index].size = value.encodeToByteArray().size.toULong()
        }
    }
    return ListLeafStringArray(views, bytes)
}

private fun MemScope.malformedStringViewArray(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    return allocArray<codex_agent_string_view>(1).also {
        it[0].data = bytes
        it[0].size = 2uL
    }
}

private fun MemScope.createValidationIssue(
    context: COpaquePointer,
    fieldName: String,
    reason: Int,
): COpaquePointerVar {
    val field = stringViewArray(fieldName)
    return emptyListLeafHandleSlot().also {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentElicitationValidationIssueCreate(context, field.views, reason, it.ptr),
        )
    }
}

private fun MemScope.assertListLeafCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    count: ListLeafCountFunction,
) {
    val output = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, count(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertIndexedString(
    context: COpaquePointer,
    value: COpaquePointer,
    index: ULong,
    expected: String,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (expectedBytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        codexAgentFormTextListValueCopyAt(context, value, index, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(maxOf(1, expectedBytes.size))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormTextListValueCopyAt(
            context,
            value,
            index,
            buffer,
            expectedBytes.size.toULong(),
            required.ptr,
        ),
    )
    assertEquals(expected, ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertValidationFlag(
    context: COpaquePointer,
    validation: COpaquePointer,
    expected: Int,
) {
    val output = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIsValid(context, validation, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertValidationIssue(
    context: COpaquePointer,
    issue: COpaquePointer,
    fieldName: String,
    reason: Int,
) {
    val expected = fieldName.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        codexAgentElicitationValidationIssueFieldNameCopy(context, issue, null, 0uL, required.ptr),
    )
    assertEquals(expected.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expected.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidationIssueFieldNameCopy(
            context,
            issue,
            buffer,
            expected.size.toULong(),
            required.ptr,
        ),
    )
    assertEquals(fieldName, ByteArray(expected.size) { buffer[it].toByte() }.decodeToString())
    val projectedReason = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidationIssueReason(context, issue, projectedReason.ptr),
    )
    assertEquals(reason, projectedReason.value)
}
