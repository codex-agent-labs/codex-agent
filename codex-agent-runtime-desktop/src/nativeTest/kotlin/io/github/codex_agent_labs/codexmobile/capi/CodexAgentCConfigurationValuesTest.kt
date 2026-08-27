@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
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

class CodexAgentCConfigurationValuesTest {
    @Test
    fun formOptionPreservesDefaultsNullabilityAndCopiedInput(): Unit = withTwoContexts { context, otherContext ->
        val value = utf8View("value")
        val absent = absentView()
        val defaultSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormOptionCreate(context, value.view, 0, absent, 0, absent, defaultSlot.ptr),
        )
        val defaultOption = assertNotNull(defaultSlot.value)
        value.bytes!![0] = 'X'.code.toUByte()
        assertCopiedString(context, defaultOption, "value", ::codexAgentFormOptionValueCopy)
        assertCopiedString(context, defaultOption, "value", ::codexAgentFormOptionTitleCopy)
        val hasDescription = alloc<IntVar>().also { it.value = -1 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormOptionHasDescription(context, defaultOption, hasDescription.ptr),
        )
        assertEquals(0, hasDescription.value)
        val required = alloc<ULongVar>().also { it.value = 97uL }
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentFormOptionDescriptionCopy(context, defaultOption, null, 0uL, required.ptr),
        )
        assertEquals(97uL, required.value)

        val titledValue = utf8View("id")
        val title = utf8View("Title")
        val description = utf8View("Description")
        val detailedSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormOptionCreate(
                context,
                titledValue.view,
                1,
                title.view,
                1,
                description.view,
                detailedSlot.ptr,
            ),
        )
        val detailedOption = assertNotNull(detailedSlot.value)
        title.bytes!![0] = 'Z'.code.toUByte()
        description.bytes!![0] = 'Z'.code.toUByte()
        assertCopiedString(context, detailedOption, "id", ::codexAgentFormOptionValueCopy)
        assertCopiedString(context, detailedOption, "Title", ::codexAgentFormOptionTitleCopy)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormOptionHasDescription(context, detailedOption, hasDescription.ptr),
        )
        assertEquals(1, hasDescription.value)
        assertCopiedString(context, detailedOption, "Description", ::codexAgentFormOptionDescriptionCopy)

        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentFormOptionValueCopy(otherContext, defaultOption, null, 0uL, required.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentPlanStepDestroy(context, defaultSlot.ptr),
        )
        assertEquals(defaultOption, defaultSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, defaultSlot.ptr))
        assertNull(defaultSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, defaultSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, detailedSlot.ptr))
    }

    @Test
    fun formOptionRejectsInvalidFlagsViewsUtf8AndOccupiedOutput(): Unit = withTwoContexts { context, _ ->
        val value = utf8View("value").view
        val title = utf8View("title").view
        val absent = absentView()
        val slot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormOptionCreate(context, value, 2, title, 0, absent, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormOptionCreate(context, value, 0, title, 0, absent, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormOptionCreate(context, value, 0, absent, -1, title, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormOptionCreate(context, invalidUtf8View(), 0, absent, 0, absent, slot.ptr),
        )
        slot.value = context
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentFormOptionCreate(context, value, 0, absent, 0, absent, slot.ptr),
        )
        assertEquals(context, slot.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormOptionDestroy(context, null))
    }

    @Test
    fun mcpEnvironmentVariableProjectsEverySourceAndAbsentSource(): Unit = withTwoContexts { context, _ ->
        listOf(0 to "LOCAL", 1 to "REMOTE").forEach { (source, label) ->
            val name = utf8View("ENV_$label")
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableCreate(context, name.view, 1, source, slot.ptr),
                label,
            )
            val variable = assertNotNull(slot.value)
            name.bytes!![0] = 'X'.code.toUByte()
            assertCopiedString(context, variable, "ENV_$label", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertOptionalInt(
                context,
                variable,
                expectedPresent = 1,
                expectedValue = source,
                project = ::codexAgentMcpEnvironmentVariableSource,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpEnvironmentVariableDestroy(context, slot.ptr))
        }

        val absentSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpEnvironmentVariableCreate(context, utf8View("OPTIONAL").view, 0, 0, absentSlot.ptr),
        )
        assertOptionalInt(
            context,
            assertNotNull(absentSlot.value),
            expectedPresent = 0,
            expectedValue = 0,
            project = ::codexAgentMcpEnvironmentVariableSource,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpEnvironmentVariableDestroy(context, absentSlot.ptr))
    }

    @Test
    fun mcpEnvironmentVariableRejectsBlankFlagsAbsentScalarAndUnknownSource(): Unit = withTwoContexts { context, _ ->
        val slot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpEnvironmentVariableCreate(context, utf8View("   ").view, 0, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpEnvironmentVariableCreate(context, utf8View("NAME").view, 2, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpEnvironmentVariableCreate(context, utf8View("NAME").view, 0, 1, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpEnvironmentVariableCreate(context, utf8View("NAME").view, 1, 2, slot.ptr),
        )
    }

    @Test
    fun mcpOauthConfigurationPreservesNullableValuesAndPortBoundaries(): Unit = withTwoContexts { context, _ ->
        val absent = absentView()
        val absentSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpOauthConfigurationCreate(context, 0, absent, 0, 0, absentSlot.ptr),
        )
        val absentConfiguration = assertNotNull(absentSlot.value)
        val hasClientId = alloc<IntVar>().also { it.value = -1 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpOauthConfigurationHasClientId(context, absentConfiguration, hasClientId.ptr),
        )
        assertEquals(0, hasClientId.value)
        val required = alloc<ULongVar>().also { it.value = 81uL }
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentMcpOauthConfigurationClientIdCopy(context, absentConfiguration, null, 0uL, required.ptr),
        )
        assertEquals(81uL, required.value)
        assertOptionalInt(
            context,
            absentConfiguration,
            expectedPresent = 0,
            expectedValue = 0,
            project = ::codexAgentMcpOauthConfigurationCallbackPort,
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpOauthConfigurationDestroy(context, absentSlot.ptr),
        )

        listOf(1, 65535).forEach { port ->
            val clientId = utf8View("client-$port")
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpOauthConfigurationCreate(context, 1, clientId.view, 1, port, slot.ptr),
                port.toString(),
            )
            val configuration = assertNotNull(slot.value)
            clientId.bytes!![0] = 'X'.code.toUByte()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpOauthConfigurationHasClientId(context, configuration, hasClientId.ptr),
            )
            assertEquals(1, hasClientId.value)
            assertCopiedString(
                context,
                configuration,
                "client-$port",
                ::codexAgentMcpOauthConfigurationClientIdCopy,
            )
            assertOptionalInt(
                context,
                configuration,
                expectedPresent = 1,
                expectedValue = port,
                project = ::codexAgentMcpOauthConfigurationCallbackPort,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpOauthConfigurationDestroy(context, slot.ptr))
        }
    }

    @Test
    fun mcpOauthConfigurationRejectsInvalidFlagsPairsUtf8AndPorts(): Unit = withTwoContexts { context, _ ->
        val absent = absentView()
        val slot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpOauthConfigurationCreate(context, -1, absent, 0, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpOauthConfigurationCreate(context, 0, utf8View("client").view, 0, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpOauthConfigurationCreate(context, 1, invalidUtf8View(), 0, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpOauthConfigurationCreate(context, 0, absent, 2, 0, slot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpOauthConfigurationCreate(context, 0, absent, 0, 1, slot.ptr),
        )
        listOf(0, 65536).forEach { port ->
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpOauthConfigurationCreate(context, 0, absent, 1, port, slot.ptr),
                port.toString(),
            )
        }
    }

    @Test
    fun mcpToolConfigurationProjectsEveryApprovalAndAbsentApproval(): Unit = withTwoContexts { context, _ ->
        listOf(0 to "AUTO", 1 to "PROMPT", 2 to "WRITES", 3 to "APPROVE").forEach { (approval, label) ->
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpToolConfigurationCreate(context, 1, approval, slot.ptr),
                label,
            )
            assertOptionalInt(
                context,
                assertNotNull(slot.value),
                expectedPresent = 1,
                expectedValue = approval,
                project = ::codexAgentMcpToolConfigurationApproval,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpToolConfigurationDestroy(context, slot.ptr))
        }
        val absentSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpToolConfigurationCreate(context, 0, 0, absentSlot.ptr),
        )
        assertOptionalInt(
            context,
            assertNotNull(absentSlot.value),
            expectedPresent = 0,
            expectedValue = 0,
            project = ::codexAgentMcpToolConfigurationApproval,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpToolConfigurationDestroy(context, absentSlot.ptr))

        val invalidSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpToolConfigurationCreate(context, 2, 0, invalidSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpToolConfigurationCreate(context, 0, 1, invalidSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpToolConfigurationCreate(context, 1, 4, invalidSlot.ptr),
        )
    }

    @Test
    fun elicitationValidationIssueProjectsEveryReasonAndCopiesFieldName(): Unit = withTwoContexts { context, _ ->
        listOf(
            0 to "MISSING_REQUIRED",
            1 to "UNKNOWN_FIELD",
            2 to "INVALID_TYPE",
            3 to "NON_FINITE_NUMBER",
            4 to "BELOW_MINIMUM",
            5 to "ABOVE_MAXIMUM",
            6 to "NON_INTEGER",
            7 to "INVALID_FORMAT",
            8 to "INVALID_SELECTION",
            9 to "DUPLICATE_SELECTION",
        ).forEach { (reason, label) ->
            val fieldName = utf8View("field-$label")
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationIssueCreate(context, fieldName.view, reason, slot.ptr),
                label,
            )
            val issue = assertNotNull(slot.value)
            fieldName.bytes!![0] = 'X'.code.toUByte()
            assertCopiedString(
                context,
                issue,
                "field-$label",
                ::codexAgentElicitationValidationIssueFieldNameCopy,
            )
            val projectedReason = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationIssueReason(context, issue, projectedReason.ptr),
            )
            assertEquals(reason, projectedReason.value, label)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, slot.ptr))
        }
        val invalidSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentElicitationValidationIssueCreate(context, utf8View("field").view, 10, invalidSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentElicitationValidationIssueCreate(context, invalidUtf8View(), 0, invalidSlot.ptr),
        )
    }

    @Test
    fun planStepProjectsEveryStatusAndCopiesText(): Unit = withTwoContexts { context, _ ->
        listOf(0 to "PENDING", 1 to "IN_PROGRESS", 2 to "COMPLETED").forEach { (status, label) ->
            val text = utf8View("step-$label")
            val slot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPlanStepCreate(context, text.view, status, slot.ptr),
                label,
            )
            val step = assertNotNull(slot.value)
            text.bytes!![0] = 'X'.code.toUByte()
            assertCopiedString(context, step, "step-$label", ::codexAgentPlanStepTextCopy)
            val projectedStatus = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPlanStepStatus(context, step, projectedStatus.ptr),
            )
            assertEquals(status, projectedStatus.value, label)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, slot.ptr))
            assertNull(slot.value)
        }
        val invalidSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanStepCreate(context, utf8View("step").view, 3, invalidSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanStepCreate(context, invalidUtf8View(), 0, invalidSlot.ptr),
        )
    }

    @Test
    fun gettersRejectNullOutputsWrongPayloadAndStaleHandles(): Unit = withTwoContexts { context, _ ->
        val absent = absentView()
        val formSlot = emptyHandleSlot()
        val planSlot = emptyHandleSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormOptionCreate(context, utf8View("value").view, 0, absent, 0, absent, formSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanStepCreate(context, utf8View("step").view, 0, planSlot.ptr),
        )
        val form = assertNotNull(formSlot.value)
        val plan = assertNotNull(planSlot.value)
        val output = alloc<IntVar>().also { it.value = 73 }
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentFormOptionHasDescription(context, form, null))
        assertEquals(73, output.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentPlanStepStatus(context, form, output.ptr),
        )
        assertEquals(73, output.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentFormOptionValueCopy(context, plan, null, 0uL, alloc<ULongVar>().ptr),
        )
        val stale = plan
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, planSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentPlanStepStatus(context, stale, output.ptr))
        assertEquals(73, output.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, formSlot.ptr))
    }
}

private data class TestStringView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private typealias StringCopyFunction = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private typealias OptionalIntFunction = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<IntVar>?,
    CPointer<IntVar>?,
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

private fun MemScope.utf8View(value: String): TestStringView {
    val encoded = value.encodeToByteArray()
    if (encoded.isEmpty()) return TestStringView(absentView(), null)
    val bytes = allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    return TestStringView(
        alloc<codex_agent_string_view>().also {
            it.data = bytes
            it.size = encoded.size.toULong()
        }.ptr,
        bytes,
    )
}

private fun MemScope.absentView(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also {
        it.data = null
        it.size = 0uL
    }.ptr

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
    copy: StringCopyFunction,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(maxOf(1, expectedBytes.size))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    val actual = ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString()
    assertEquals(expected, actual)
}

private fun MemScope.assertOptionalInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedPresent: Int,
    expectedValue: Int,
    project: OptionalIntFunction,
) {
    val present = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, project(context, handle, present.ptr, value.ptr))
    assertEquals(expectedPresent, present.value)
    assertEquals(expectedValue, value.value)
}
