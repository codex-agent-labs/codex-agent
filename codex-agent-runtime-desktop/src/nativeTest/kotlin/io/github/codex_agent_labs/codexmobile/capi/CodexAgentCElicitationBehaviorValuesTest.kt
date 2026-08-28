@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentElicitation
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationAction
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse
import io.github.codex_agent_labs.codexmobile.agent.AgentFormField
import io.github.codex_agent_labs.codexmobile.agent.AgentFormFieldType
import io.github.codex_agent_labs.codexmobile.agent.AgentFormOption
import io.github.codex_agent_labs.codexmobile.agent.AgentFormStringFormat
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
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
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCElicitationBehaviorValuesTest {
    @Test
    fun formFieldAcceptsEveryTypeBoundFormatAndSelectionRule(): Unit =
        withBehaviorContexts { context, _ ->
            val string = behaviorField("string", AgentFormFieldType.STRING, isRequired = true)
            assertFieldAccepts(context, string, AgentFormValue.Text("value"), true)
            assertFieldAccepts(context, string, null, false)
            assertFieldAccepts(context, string, AgentFormValue.Text("  "), false)
            assertFieldAccepts(context, string, AgentFormValue.BooleanValue(true), false)

            val number = behaviorField("number", AgentFormFieldType.NUMBER, minimum = 1.0, maximum = 3.0)
            listOf(1.0, 2.5, 3.0).forEach {
                assertFieldAccepts(context, number, AgentFormValue.Number(it), true)
            }
            listOf(0.9, 3.1, Double.NaN, Double.POSITIVE_INFINITY).forEach {
                assertFieldAccepts(context, number, AgentFormValue.Number(it), false)
            }

            val integer = behaviorField("integer", AgentFormFieldType.INTEGER, minimum = -2.0, maximum = 2.0)
            listOf(-2.0, 0.0, 2.0).forEach {
                assertFieldAccepts(context, integer, AgentFormValue.Number(it), true)
            }
            listOf(-3.0, 1.5, 3.0).forEach {
                assertFieldAccepts(context, integer, AgentFormValue.Number(it), false)
            }

            val boolean = behaviorField("boolean", AgentFormFieldType.BOOLEAN)
            assertFieldAccepts(context, boolean, AgentFormValue.BooleanValue(false), true)
            assertFieldAccepts(context, boolean, AgentFormValue.Text("false"), false)

            listOf(
                AgentFormStringFormat.EMAIL to ("user@example.com" to "invalid"),
                AgentFormStringFormat.URI to ("https://example.com/path" to "not a uri"),
                AgentFormStringFormat.DATE to ("2024-02-29" to "2026-02-31"),
                AgentFormStringFormat.DATE_TIME to
                    ("2026-01-01T12:00:00.123+01:00" to "2026-01-01T12:00:00+garbage"),
            ).forEach { (format, values) ->
                val field = behaviorField("formatted", AgentFormFieldType.STRING, format = format)
                assertFieldAccepts(context, field, AgentFormValue.Text(values.first), true)
                assertFieldAccepts(context, field, AgentFormValue.Text(values.second), false)
            }

            val options = listOf(AgentFormOption("alpha"), AgentFormOption("beta"))
            val single = behaviorField("single", AgentFormFieldType.SINGLE_SELECT, options = options)
            assertFieldAccepts(context, single, AgentFormValue.Text("alpha"), true)
            assertFieldAccepts(context, single, AgentFormValue.Text("other"), false)
            assertFieldAccepts(context, single.copy(allowsOther = true), AgentFormValue.Text("other"), true)
            assertFieldAccepts(context, single.copy(allowsOther = true), AgentFormValue.Text(" "), false)

            val multi = behaviorField(
                "multi",
                AgentFormFieldType.MULTI_SELECT,
                isRequired = true,
                options = options,
                minimumSelections = 1,
                maximumSelections = 2,
            )
            assertFieldAccepts(context, multi, AgentFormValue.TextList(listOf("alpha", "beta")), true)
            assertFieldAccepts(context, multi, AgentFormValue.TextList(emptyList()), false)
            assertFieldAccepts(context, multi, AgentFormValue.TextList(listOf("alpha", "alpha")), false)
            assertFieldAccepts(context, multi, AgentFormValue.TextList(listOf("other")), false)
            assertFieldAccepts(
                context,
                multi.copy(allowsOther = true),
                AgentFormValue.TextList(listOf("alpha", "other")),
                true,
            )
        }

    @Test
    fun elicitationInitialValidateAndAcceptUseExactOwnedMapSemantics(): Unit =
        withBehaviorContexts { context, _ ->
            val defaultSelections = mutableListOf("a")
            val elicitationValue = comprehensiveElicitation(defaultSelections)
            val elicitation = behaviorSnapshot(context, CodexAgentCElicitationSnapshot(elicitationValue))
            val elicitationHandle = assertNotNull(elicitation.value)

            val initial = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationInitialValues(context, elicitationHandle, initial.ptr),
            )
            val initialHandle = assertNotNull(initial.value)
            val count = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormContentCount(context, initialHandle, count.ptr))
            assertEquals(2uL, count.value)
            val keys = buildSet {
                repeat(count.value.toInt()) { index ->
                    add(copyBehaviorKey(context, initialHandle, index.toULong()))
                }
            }
            assertEquals(setOf("count", "default_many"), keys)

            val initialMany = emptyBehaviorHandle()
            val secondInitialMany = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormContentValueAt(
                    context,
                    initialHandle,
                    behaviorUtf8("default_many").view,
                    initialMany.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormContentValueAt(
                    context,
                    initialHandle,
                    behaviorUtf8("default_many").view,
                    secondInitialMany.ptr,
                ),
            )
            assertNotEquals(initialMany.value, secondInitialMany.value)
            defaultSelections += "b"
            assertFormValue(context, assertNotNull(initialMany.value), AgentFormValue.TextList(listOf("a")))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormContentDestroy(context, initial.ptr))
            assertFormValue(context, assertNotNull(initialMany.value), AgentFormValue.TextList(listOf("a")))
            assertFormValue(context, assertNotNull(secondInitialMany.value), AgentFormValue.TextList(listOf("a")))

            val duplicateSelections = mutableListOf("first")
            val first = behaviorSnapshot(context, CodexAgentCFormValueSnapshot(AgentFormValue.Text("discarded")))
            val second = behaviorSnapshot(
                context,
                CodexAgentCFormValueSnapshot(AgentFormValue.TextList(duplicateSelections)),
            )
            val duplicate = createBehaviorContent(
                context,
                listOf("same", "same"),
                listOf(assertNotNull(first.value), assertNotNull(second.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, duplicate.status)
            duplicateSelections += "mutated"
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, first.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, second.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormContentCount(context, assertNotNull(duplicate.slot.value), count.ptr),
            )
            assertEquals(1uL, count.value)
            val duplicateValue = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormContentValueAt(
                    context,
                    assertNotNull(duplicate.slot.value),
                    behaviorUtf8("same").view,
                    duplicateValue.ptr,
                ),
            )
            assertFormValue(
                context,
                assertNotNull(duplicateValue.value),
                AgentFormValue.TextList(listOf("first")),
            )

            assertValidationReason(context, elicitationHandle, emptyMap(), MISSING_REQUIRED)
            assertValidationReason(
                context,
                elicitationHandle,
                mapOf("name" to AgentFormValue.Text("ok"), "other" to AgentFormValue.Text("x")),
                UNKNOWN_FIELD,
            )
            val invalidValues = listOf(
                Triple("name", AgentFormValue.Number(1.0), INVALID_TYPE),
                Triple("name", AgentFormValue.Text("x"), BELOW_MINIMUM),
                Triple("name", AgentFormValue.Text("abcde"), ABOVE_MAXIMUM),
                Triple("email", AgentFormValue.Text("invalid"), INVALID_FORMAT),
                Triple("date", AgentFormValue.Text("2026-02-31"), INVALID_FORMAT),
                Triple("timestamp", AgentFormValue.Text("2026-01-01T12:00:00+garbage"), INVALID_FORMAT),
                Triple("ratio", AgentFormValue.Text("one"), INVALID_TYPE),
                Triple("enabled", AgentFormValue.Text("true"), INVALID_TYPE),
                Triple("choice", AgentFormValue.Number(1.0), INVALID_TYPE),
                Triple("many", AgentFormValue.Text("a"), INVALID_TYPE),
                Triple("count", AgentFormValue.Number(Double.NaN), NON_FINITE_NUMBER),
                Triple("count", AgentFormValue.Number(0.0), BELOW_MINIMUM),
                Triple("count", AgentFormValue.Number(4.0), ABOVE_MAXIMUM),
                Triple("count", AgentFormValue.Number(1.5), NON_INTEGER),
                Triple("choice", AgentFormValue.Text("z"), INVALID_SELECTION),
                Triple("many", AgentFormValue.TextList(listOf("z")), INVALID_SELECTION),
                Triple("many", AgentFormValue.TextList(emptyList()), BELOW_MINIMUM),
                Triple("many", AgentFormValue.TextList(listOf("a", "b", "c")), ABOVE_MAXIMUM),
                Triple("many", AgentFormValue.TextList(listOf("a", "a")), DUPLICATE_SELECTION),
            )
            invalidValues.forEach { (name, value, reason) ->
                assertValidationReason(
                    context,
                    elicitationHandle,
                    mapOf("name" to AgentFormValue.Text("ok"), name to value),
                    reason,
                )
            }

            val selected = mutableListOf("a")
            val validValues = mapOf(
                "name" to AgentFormValue.Text("ok"),
                "email" to AgentFormValue.Text("user@example.com"),
                "date" to AgentFormValue.Text("2024-02-29"),
                "timestamp" to AgentFormValue.Text("2026-01-01T12:00:00.123+01:00"),
                "count" to AgentFormValue.Number(2.0),
                "ratio" to AgentFormValue.Number(0.5),
                "enabled" to AgentFormValue.BooleanValue(true),
                "choice" to AgentFormValue.Text("a"),
                "many" to AgentFormValue.TextList(selected),
            )
            val valid = behaviorSnapshot(context, CodexAgentCFormContentSnapshot(validValues))
            val validation = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidate(context, elicitationHandle, valid.value, validation.ptr),
            )
            val isValid = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationValidationIsValid(context, validation.value, isValid.ptr),
            )
            assertEquals(1, isValid.value)

            val accepted = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationAccept(context, elicitationHandle, valid.value, accepted.ptr),
            )
            selected += "b"
            val acceptedMany = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationResponseContentValue(
                    context,
                    accepted.value,
                    behaviorUtf8("many").view,
                    acceptedMany.ptr,
                ),
            )
            assertFormValue(
                context,
                assertNotNull(acceptedMany.value),
                AgentFormValue.TextList(listOf("a")),
            )

            val invalid = behaviorSnapshot(context, CodexAgentCFormContentSnapshot(emptyMap()))
            val rejected = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationAccept(context, elicitationHandle, invalid.value, rejected.ptr),
            )
            assertNull(rejected.value)
        }

    @Test
    fun responseFactoriesAndElicitationAcceptsImplementExactTruthTable(): Unit =
        withBehaviorContexts { context, _ ->
            val required = behaviorField("required", AgentFormFieldType.STRING, isRequired = true)
            val elicitation = behaviorSnapshot(
                context,
                CodexAgentCElicitationSnapshot(behaviorElicitation(listOf(required))),
            )
            val empty = behaviorSnapshot(context, CodexAgentCFormContentSnapshot(emptyMap()))
            val validContent = mapOf("required" to AgentFormValue.Text("answer"))
            val valid = behaviorSnapshot(context, CodexAgentCFormContentSnapshot(validContent))
            val accepted = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationAccept(context, elicitation.value, valid.value, accepted.ptr),
            )
            assertElicitationAccepts(context, assertNotNull(elicitation.value), accepted.value, true)

            val invalidAccept = behaviorSnapshot(
                context,
                CodexAgentCElicitationResponseSnapshot(
                    AgentElicitationResponse(AgentElicitationAction.ACCEPT),
                ),
            )
            assertElicitationAccepts(context, assertNotNull(elicitation.value), invalidAccept.value, false)

            val decline = emptyBehaviorHandle()
            val cancel = emptyBehaviorHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseDecline(context, decline.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseCancel(context, cancel.ptr))
            assertResponse(context, assertNotNull(decline.value), 1, 0uL)
            assertResponse(context, assertNotNull(cancel.value), 2, 0uL)
            assertElicitationAccepts(context, assertNotNull(elicitation.value), decline.value, true)
            assertElicitationAccepts(context, assertNotNull(elicitation.value), cancel.value, true)

            listOf(AgentElicitationAction.DECLINE, AgentElicitationAction.CANCEL).forEach { action ->
                val nonEmpty = behaviorSnapshot(
                    context,
                    CodexAgentCElicitationResponseSnapshot(AgentElicitationResponse(action, validContent)),
                )
                assertElicitationAccepts(context, assertNotNull(elicitation.value), nonEmpty.value, false)
            }

            val urlOnly = behaviorSnapshot(
                context,
                CodexAgentCElicitationSnapshot(behaviorElicitation(form = null, url = "https://example.com")),
            )
            val emptyAccepted = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationAccept(context, urlOnly.value, empty.value, emptyAccepted.ptr),
            )
            assertElicitationAccepts(context, assertNotNull(urlOnly.value), emptyAccepted.value, true)
            assertElicitationAccepts(context, assertNotNull(urlOnly.value), accepted.value, false)
        }

    @Test
    fun behaviorSurfaceRejectsInvalidBoundariesAndContextTeardownReclaimsSnapshots(): Unit =
        withBehaviorContexts { context, otherContext ->
            val field = behaviorSnapshot(
                context,
                CodexAgentCFormFieldSnapshot(behaviorField("field", AgentFormFieldType.STRING)),
            )
            val value = behaviorSnapshot(
                context,
                CodexAgentCFormValueSnapshot(AgentFormValue.Text("value")),
            )
            val content = createBehaviorContent(
                context,
                listOf("field"),
                listOf(assertNotNull(value.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, content.status)
            val contentHandle = assertNotNull(content.slot.value)
            val elicitation = behaviorSnapshot(
                context,
                CodexAgentCElicitationSnapshot(
                    behaviorElicitation(listOf(behaviorField("field", AgentFormFieldType.STRING))),
                ),
            )
            val response = behaviorSnapshot(
                context,
                CodexAgentCElicitationResponseSnapshot(
                    AgentElicitationResponse(
                        AgentElicitationAction.ACCEPT,
                        mapOf("field" to AgentFormValue.Text("value")),
                    ),
                ),
            )

            val primitive = alloc<IntVar>().also { it.value = 91 }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentFormFieldAccepts(otherContext, field.value, value.value, primitive.ptr),
            )
            assertEquals(91, primitive.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentFormFieldAccepts(context, value.value, value.value, primitive.ptr),
            )
            assertEquals(91, primitive.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentFormContentCount(context, field.value, alloc<ULongVar>().ptr),
            )

            val occupied = emptyBehaviorHandle().also { it.value = context }
            val fieldKey = behaviorUtf8("field")
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentCreate(
                    context,
                    fieldKey.view,
                    behaviorHandleArray(assertNotNull(value.value)),
                    1uL,
                    occupied.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentCreate(context, null, null, 1uL, emptyBehaviorHandle().ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentCreate(
                    context,
                    fieldKey.view,
                    behaviorHandleArray(assertNotNull(value.value)),
                    0uL,
                    emptyBehaviorHandle().ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationInitialValues(context, elicitation.value, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationValidate(context, elicitation.value, contentHandle, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationAccept(context, elicitation.value, contentHandle, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationResponseDecline(context, occupied.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentElicitationResponseCancel(context, occupied.ptr),
            )
            assertEquals(context, occupied.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentValueAt(context, contentHandle, fieldKey.view, occupied.ptr),
            )
            assertEquals(context, occupied.value)

            val missing = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentFormContentValueAt(
                    context,
                    contentHandle,
                    behaviorUtf8("missing").view,
                    missing.ptr,
                ),
            )
            assertNull(missing.value)
            val required = alloc<ULongVar>().also { it.value = 77uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentKeyCopy(context, contentHandle, 1uL, null, 0uL, required.ptr),
            )
            assertEquals(77uL, required.value)

            val malformed = malformedBehaviorUtf8()
            val malformedOutput = emptyBehaviorHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentValueAt(context, contentHandle, malformed.view, malformedOutput.ptr),
            )
            assertNull(malformedOutput.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormContentCreate(
                    context,
                    malformed.view,
                    behaviorHandleArray(assertNotNull(value.value)),
                    1uL,
                    malformedOutput.ptr,
                ),
            )

            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentElicitationAccepts(otherContext, elicitation.value, response.value, primitive.ptr),
            )
            assertEquals(91, primitive.value)
            val staleField = assertNotNull(field.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, field.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentFormFieldAccepts(context, staleField, value.value, primitive.ptr),
            )
            assertEquals(91, primitive.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormContentDestroy(context, content.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormContentDestroy(context, content.slot.ptr))
            assertNull(content.slot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentFormContentCount(context, contentHandle, alloc<ULongVar>().ptr),
            )
        }

    @Test
    fun contextTeardownReclaimsOutstandingBehaviorSnapshots(): Unit = memScoped {
        val contextSlot = emptyBehaviorHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val value = behaviorSnapshot(
            context,
            CodexAgentCFormValueSnapshot(AgentFormValue.Text("value")),
        )
        val content = createBehaviorContent(
            context,
            listOf("key"),
            listOf(assertNotNull(value.value)),
        )
        val child = emptyBehaviorHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormContentValueAt(
                context,
                assertNotNull(content.slot.value),
                behaviorUtf8("key").view,
                child.ptr,
            ),
        )
        val handles = listOf(assertNotNull(content.slot.value), assertNotNull(child.value))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
        val count = alloc<ULongVar>().also { it.value = 55uL }
        handles.forEach { handle ->
            assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentFormContentCount(context, handle, count.ptr))
            assertEquals(55uL, count.value)
        }
    }
}

private data class BehaviorHandleResult(
    val status: Int,
    val slot: COpaquePointerVar,
)

private data class BehaviorUtf8(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private const val MISSING_REQUIRED = 0
private const val UNKNOWN_FIELD = 1
private const val INVALID_TYPE = 2
private const val NON_FINITE_NUMBER = 3
private const val BELOW_MINIMUM = 4
private const val ABOVE_MAXIMUM = 5
private const val NON_INTEGER = 6
private const val INVALID_FORMAT = 7
private const val INVALID_SELECTION = 8
private const val DUPLICATE_SELECTION = 9

private fun withBehaviorContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyBehaviorHandle()
    val otherContextSlot = emptyBehaviorHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContextSlot.ptr))
    block(assertNotNull(contextSlot.value), assertNotNull(otherContextSlot.value))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
}

private fun MemScope.emptyBehaviorHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.behaviorUtf8(value: String): BehaviorUtf8 {
    val encoded = value.encodeToByteArray()
    val bytes = if (encoded.isEmpty()) null else allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> checkNotNull(bytes)[index] = byte.toUByte() }
    val view = alloc<codex_agent_string_view>()
    view.data = bytes
    view.size = encoded.size.toULong()
    return BehaviorUtf8(view.ptr, bytes)
}

private fun MemScope.malformedBehaviorUtf8(): BehaviorUtf8 {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    val view = alloc<codex_agent_string_view>()
    view.data = bytes
    view.size = 2uL
    return BehaviorUtf8(view.ptr, bytes)
}

private fun MemScope.behaviorHandleArray(vararg handles: COpaquePointer): CPointer<COpaquePointerVar> =
    allocArray<COpaquePointerVar>(handles.size).also { values ->
        handles.forEachIndexed { index, handle -> values[index] = handle }
    }

private fun MemScope.behaviorSnapshot(
    context: COpaquePointer,
    snapshot: CodexAgentCSnapshot,
): COpaquePointerVar = emptyBehaviorHandle().also { slot ->
    val result = createSnapshot(context, snapshot)
    assertEquals(CODEX_AGENT_STATUS_OK, result.status)
    slot.value = assertNotNull(result.value)
}

private fun MemScope.createBehaviorContent(
    context: COpaquePointer,
    keys: List<String>,
    values: List<COpaquePointer>,
): BehaviorHandleResult {
    require(keys.size == values.size)
    val encoded = keys.map { behaviorUtf8(it) }
    val keyInput = if (encoded.isEmpty()) null else allocArray<codex_agent_string_view>(encoded.size).also { array ->
        encoded.forEachIndexed { index, value ->
            array[index].data = value.view.pointed.data
            array[index].size = value.view.pointed.size
        }
    }
    val valueInput = if (values.isEmpty()) null else behaviorHandleArray(*values.toTypedArray())
    val slot = emptyBehaviorHandle()
    return BehaviorHandleResult(
        codexAgentFormContentCreate(context, keyInput, valueInput, keys.size.toULong(), slot.ptr),
        slot,
    )
}

private fun MemScope.assertFieldAccepts(
    context: COpaquePointer,
    field: AgentFormField,
    value: AgentFormValue?,
    expected: Boolean,
) {
    val fieldHandle = behaviorSnapshot(context, CodexAgentCFormFieldSnapshot(field))
    val valueHandle = value?.let { behaviorSnapshot(context, CodexAgentCFormValueSnapshot(it)) }
    val accepted = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormFieldAccepts(context, fieldHandle.value, valueHandle?.value, accepted.ptr),
    )
    assertEquals(if (expected) 1 else 0, accepted.value, "$field should accept $value")
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, fieldHandle.ptr))
    valueHandle?.let { assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, it.ptr)) }
}

private fun MemScope.assertValidationReason(
    context: COpaquePointer,
    elicitation: COpaquePointer,
    values: Map<String, AgentFormValue>,
    expectedReason: Int,
) {
    val content = behaviorSnapshot(context, CodexAgentCFormContentSnapshot(values))
    val validation = emptyBehaviorHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidate(context, elicitation, content.value, validation.ptr),
    )
    val issueCount = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidationIssueCount(context, validation.value, issueCount.ptr),
    )
    assertEquals(1uL, issueCount.value)
    val issue = emptyBehaviorHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidationIssueAt(context, validation.value, 0uL, issue.ptr),
    )
    val reason = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationValidationIssueReason(context, issue.value, reason.ptr),
    )
    assertEquals(expectedReason, reason.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationIssueDestroy(context, issue.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationValidationDestroy(context, validation.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormContentDestroy(context, content.ptr))
}

private fun MemScope.assertElicitationAccepts(
    context: COpaquePointer,
    elicitation: COpaquePointer,
    response: COpaquePointer?,
    expected: Boolean,
) {
    val accepted = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationAccepts(context, elicitation, response, accepted.ptr),
    )
    assertEquals(if (expected) 1 else 0, accepted.value)
}

private fun MemScope.assertResponse(
    context: COpaquePointer,
    response: COpaquePointer,
    expectedAction: Int,
    expectedCount: ULong,
) {
    val action = alloc<IntVar>().also { it.value = -1 }
    val count = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseAction(context, response, action.ptr))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationResponseContentCount(context, response, count.ptr),
    )
    assertEquals(expectedAction, action.value)
    assertEquals(expectedCount, count.value)
}

private fun assertFormValue(
    context: COpaquePointer,
    value: COpaquePointer,
    expected: AgentFormValue,
) {
    var actual: AgentFormValue? = null
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        withPayload<CodexAgentCFormValueSnapshot>(context, value, CodexAgentCHandleKind.SNAPSHOT) {
            actual = it.value
            CODEX_AGENT_STATUS_OK
        },
    )
    assertEquals(expected, actual)
}

private fun MemScope.copyBehaviorKey(
    context: COpaquePointer,
    content: COpaquePointer,
    index: ULong,
): String {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        codexAgentFormContentKeyCopy(context, content, index, null, 0uL, required.ptr),
    )
    val bytes = allocArray<UByteVar>(required.value.toInt())
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormContentKeyCopy(context, content, index, bytes, required.value, required.ptr),
    )
    return ByteArray(required.value.toInt()) { bytes[it].toByte() }.decodeToString()
}

private fun behaviorElicitation(
    form: List<AgentFormField>? = null,
    url: String? = null,
): AgentElicitation = AgentElicitation(
    requestId = "request",
    serverName = "server",
    conversationId = ConversationId("conversation"),
    message = "Provide input",
    form = form,
    url = url,
)

private fun comprehensiveElicitation(defaultSelections: MutableList<String>): AgentElicitation =
    behaviorElicitation(
        listOf(
            AgentFormField(
                "name",
                "Name",
                isRequired = true,
                type = AgentFormFieldType.STRING,
                minimumLength = 2,
                maximumLength = 4,
            ),
            AgentFormField("email", "Email", type = AgentFormFieldType.STRING, format = AgentFormStringFormat.EMAIL),
            AgentFormField("date", "Date", type = AgentFormFieldType.STRING, format = AgentFormStringFormat.DATE),
            AgentFormField(
                "timestamp",
                "Timestamp",
                type = AgentFormFieldType.STRING,
                format = AgentFormStringFormat.DATE_TIME,
            ),
            AgentFormField(
                "count",
                "Count",
                type = AgentFormFieldType.INTEGER,
                defaultValue = AgentFormValue.Number(2.0),
                minimum = 1.0,
                maximum = 3.0,
            ),
            AgentFormField("ratio", "Ratio", type = AgentFormFieldType.NUMBER),
            AgentFormField("enabled", "Enabled", type = AgentFormFieldType.BOOLEAN),
            AgentFormField(
                "choice",
                "Choice",
                type = AgentFormFieldType.SINGLE_SELECT,
                options = listOf(AgentFormOption("a")),
            ),
            AgentFormField(
                "many",
                "Many",
                type = AgentFormFieldType.MULTI_SELECT,
                options = listOf(AgentFormOption("a"), AgentFormOption("b"), AgentFormOption("c")),
                minimumSelections = 1,
                maximumSelections = 2,
            ),
            AgentFormField(
                "default_many",
                "Default many",
                type = AgentFormFieldType.MULTI_SELECT,
                options = listOf(AgentFormOption("a"), AgentFormOption("b")),
                defaultValue = AgentFormValue.TextList(defaultSelections),
            ),
        ),
    )

private fun behaviorField(
    name: String,
    type: AgentFormFieldType,
    isRequired: Boolean = false,
    options: List<AgentFormOption> = emptyList(),
    minimum: Double? = null,
    maximum: Double? = null,
    format: AgentFormStringFormat? = null,
    minimumSelections: Long? = null,
    maximumSelections: Long? = null,
): AgentFormField = AgentFormField(
    name = name,
    title = name,
    type = type,
    isRequired = isRequired,
    options = options,
    minimum = minimum,
    maximum = maximum,
    format = format,
    minimumSelections = minimumSelections,
    maximumSelections = maximumSelections,
)
