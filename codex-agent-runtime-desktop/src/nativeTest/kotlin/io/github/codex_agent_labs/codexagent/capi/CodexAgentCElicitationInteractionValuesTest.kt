@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.DoubleVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
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

class CodexAgentCElicitationInteractionValuesTest {
    @Test
    fun formValueCarrierIsTaggedOwnedAndFailClosed(): Unit = withElicitationContexts { context, otherContext ->
        val boolean = emptyElicitationHandle()
        val number = emptyElicitationHandle()
        val text = emptyElicitationHandle()
        val textList = emptyElicitationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormBooleanValueCreate(context, 1, boolean.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormNumberValueCreate(context, 12.5, number.ptr))
        val mutableText = elicitationUtf8("copied-text")
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueCreate(context, mutableText.view, text.ptr))
        val listViews = arrayOf(elicitationUtf8("alpha"), elicitationUtf8("alpha"), elicitationUtf8("β"))
        val listInput = allocArray<codex_agent_string_view>(listViews.size)
        listViews.forEachIndexed { index, value ->
            listInput[index].data = value.view.pointed.data
            listInput[index].size = value.view.pointed.size
        }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormTextListValueCreate(context, listInput, listViews.size.toULong(), textList.ptr),
        )

        val concrete = listOf(boolean, number, text, textList)
        val carriers = List(4) { emptyElicitationHandle() }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueFromBoolean(context, assertNotNull(boolean.value), carriers[0].ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueFromNumber(context, assertNotNull(number.value), carriers[1].ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueFromText(context, assertNotNull(text.value), carriers[2].ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueFromTextList(context, assertNotNull(textList.value), carriers[3].ptr),
        )
        mutableText.bytes!![0] = 'X'.code.toUByte()
        concrete.forEachIndexed { index, slot ->
            when (index) {
                0 -> codexAgentFormBooleanValueDestroy(context, slot.ptr)
                1 -> codexAgentFormNumberValueDestroy(context, slot.ptr)
                2 -> codexAgentFormTextValueDestroy(context, slot.ptr)
                else -> codexAgentFormTextListValueDestroy(context, slot.ptr)
            }.also { assertEquals(CODEX_AGENT_STATUS_OK, it) }
        }

        carriers.forEachIndexed { expectedKind, slot ->
            val kind = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueKind(context, assertNotNull(slot.value), kind.ptr),
            )
            assertEquals(expectedKind, kind.value)
        }
        val booleanChild = emptyElicitationHandle()
        val numberChild = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueBoolean(context, assertNotNull(carriers[0].value), booleanChild.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueNumber(context, assertNotNull(carriers[1].value), numberChild.ptr),
        )
        assertElicitationInt(
            context,
            assertNotNull(booleanChild.value),
            1,
            ::codexAgentFormBooleanValueValue,
        )
        val numberValue = alloc<DoubleVar>().also { it.value = Double.NaN }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormNumberValueValue(context, assertNotNull(numberChild.value), numberValue.ptr),
        )
        assertEquals(12.5, numberValue.value)
        val textChildOne = emptyElicitationHandle()
        val textChildTwo = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueText(context, assertNotNull(carriers[2].value), textChildOne.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueText(context, assertNotNull(carriers[2].value), textChildTwo.ptr),
        )
        assertNotEquals(textChildOne.value, textChildTwo.value)
        assertElicitationString(context, assertNotNull(textChildOne.value), "copied-text", ::codexAgentFormTextValueValueCopy)

        val listChild = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormValueTextList(context, assertNotNull(carriers[3].value), listChild.ptr),
        )
        assertElicitationTextList(context, assertNotNull(listChild.value), listOf("alpha", "alpha", "β"))

        val wrongDowncast = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentFormValueNumber(context, assertNotNull(carriers[2].value), wrongDowncast.ptr),
        )
        assertNull(wrongDowncast.value)
        val sentinel = alloc<IntVar>().also { it.value = 71 }
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentFormValueKind(otherContext, assertNotNull(carriers[0].value), sentinel.ptr),
        )
        assertEquals(71, sentinel.value)

        carriers.forEach { assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, it.ptr)) }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, carriers[0].ptr))
        assertElicitationInt(
            context,
            assertNotNull(booleanChild.value),
            1,
            ::codexAgentFormBooleanValueValue,
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFormNumberValueValue(context, assertNotNull(numberChild.value), numberValue.ptr),
        )
        assertEquals(12.5, numberValue.value)
        assertElicitationString(context, assertNotNull(textChildOne.value), "copied-text", ::codexAgentFormTextValueValueCopy)
        assertElicitationTextList(context, assertNotNull(listChild.value), listOf("alpha", "alpha", "β"))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormBooleanValueDestroy(context, booleanChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormNumberValueDestroy(context, numberChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textChildOne.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textChildTwo.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, listChild.ptr))
    }

    @Test
    fun formFieldsProjectEveryScalarNullableEnumOptionAndOwnedDefault(): Unit =
        withElicitationContexts { context, _ ->
            val optionAlpha = createElicitationOption(context, "alpha", "Alpha", "first")
            val optionBeta = createElicitationOption(context, "beta", "Beta", null)
            val defaultConcrete = createElicitationTextList(context, listOf("alpha", "alpha"))
            val defaultCarrier = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueFromTextList(
                    context,
                    assertNotNull(defaultConcrete.value),
                    defaultCarrier.ptr,
                ),
            )
            val name = elicitationUtf8("choices")
            val result = createElicitationField(
                context = context,
                name = name,
                title = elicitationUtf8("Choices"),
                description = "Select values",
                isRequired = 1,
                type = 5,
                options = listOf(
                    assertNotNull(optionAlpha.value),
                    assertNotNull(optionBeta.value),
                    assertNotNull(optionAlpha.value),
                ),
                defaultValue = assertNotNull(defaultCarrier.value),
                minimum = 1.25,
                maximum = 9.5,
                format = 1,
                minimumLength = 2,
                maximumLength = 20,
                minimumSelections = 1,
                maximumSelections = 3,
                allowsOther = 1,
                isSecret = 1,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, result.status)
            val field = assertNotNull(result.slot.value)
            name.bytes!![0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, optionAlpha.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, optionBeta.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, defaultConcrete.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, defaultCarrier.ptr))

            assertElicitationString(context, field, "choices", ::codexAgentFormFieldNameCopy)
            assertElicitationString(context, field, "Choices", ::codexAgentFormFieldTitleCopy)
            assertElicitationInt(context, field, 1, ::codexAgentFormFieldHasDescription)
            assertElicitationString(context, field, "Select values", ::codexAgentFormFieldDescriptionCopy)
            assertElicitationInt(context, field, 1, ::codexAgentFormFieldIsRequired)
            assertElicitationInt(context, field, 5, ::codexAgentFormFieldType)
            assertElicitationInt(context, field, 1, ::codexAgentFormFieldHasDefaultValue)
            assertElicitationInt(context, field, 1, ::codexAgentFormFieldAllowsOther)
            assertElicitationInt(context, field, 1, ::codexAgentFormFieldIsSecret)
            assertElicitationOptionalDouble(context, field, 1, 1.25, ::codexAgentFormFieldMinimum)
            assertElicitationOptionalDouble(context, field, 1, 9.5, ::codexAgentFormFieldMaximum)
            assertElicitationOptionalInt(context, field, 1, 1, ::codexAgentFormFieldFormat)
            assertElicitationOptionalLong(context, field, 1, 2, ::codexAgentFormFieldMinimumLength)
            assertElicitationOptionalLong(context, field, 1, 20, ::codexAgentFormFieldMaximumLength)
            assertElicitationOptionalLong(context, field, 1, 1, ::codexAgentFormFieldMinimumSelections)
            assertElicitationOptionalLong(context, field, 1, 3, ::codexAgentFormFieldMaximumSelections)

            val optionCount = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldOptionsCount(context, field, optionCount.ptr))
            assertEquals(3uL, optionCount.value)
            val firstOption = emptyElicitationHandle()
            val duplicateOption = emptyElicitationHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldOptionAt(context, field, 0uL, firstOption.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldOptionAt(context, field, 2uL, duplicateOption.ptr))
            assertNotEquals(firstOption.value, duplicateOption.value)
            assertElicitationString(
                context,
                assertNotNull(firstOption.value),
                "alpha",
                ::codexAgentFormOptionValueCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(duplicateOption.value),
                "alpha",
                ::codexAgentFormOptionValueCopy,
            )
            val defaultChild = emptyElicitationHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDefaultValue(context, field, defaultChild.ptr))
            val defaultList = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueTextList(context, assertNotNull(defaultChild.value), defaultList.ptr),
            )
            assertElicitationTextList(context, assertNotNull(defaultList.value), listOf("alpha", "alpha"))

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, result.slot.ptr))
            assertElicitationString(
                context,
                assertNotNull(firstOption.value),
                "alpha",
                ::codexAgentFormOptionValueCopy,
            )
            assertElicitationTextList(context, assertNotNull(defaultList.value), listOf("alpha", "alpha"))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, firstOption.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormOptionDestroy(context, duplicateOption.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, defaultChild.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, defaultList.ptr))

            val absent = createElicitationField(context, description = null)
            assertEquals(CODEX_AGENT_STATUS_OK, absent.status)
            val absentField = assertNotNull(absent.slot.value)
            assertElicitationInt(context, absentField, 0, ::codexAgentFormFieldHasDescription)
            assertElicitationInt(context, absentField, 0, ::codexAgentFormFieldHasDefaultValue)
            val required = alloc<ULongVar>().also { it.value = 77uL }
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentFormFieldDescriptionCopy(context, absentField, null, 0uL, required.ptr),
            )
            assertEquals(77uL, required.value)
            val absentDefault = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentFormFieldDefaultValue(context, absentField, absentDefault.ptr),
            )
            assertNull(absentDefault.value)
            assertElicitationOptionalDouble(context, absentField, 0, 0.0, ::codexAgentFormFieldMinimum)
            assertElicitationOptionalLong(context, absentField, 0, 0, ::codexAgentFormFieldMinimumLength)
            val presentEmpty = createElicitationField(context, description = "")
            assertEquals(CODEX_AGENT_STATUS_OK, presentEmpty.status)
            val emptyField = assertNotNull(presentEmpty.slot.value)
            assertElicitationInt(context, emptyField, 1, ::codexAgentFormFieldHasDescription)
            assertElicitationString(context, emptyField, "", ::codexAgentFormFieldDescriptionCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, absent.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, presentEmpty.slot.ptr))
        }

    @Test
    fun elicitationAndResponseProjectEveryFieldAndOwnedCollection(): Unit =
        withElicitationContexts { context, _ ->
            val conversationId = createElicitationConversationId(context, "conversation-λ")
            val field = createElicitationField(context, name = elicitationUtf8("field"), description = "")
            val secondField = createElicitationField(context, name = elicitationUtf8("second"), description = null)
            assertEquals(CODEX_AGENT_STATUS_OK, field.status)
            assertEquals(CODEX_AGENT_STATUS_OK, secondField.status)
            val requestId = elicitationUtf8("request-1")
            val result = createElicitation(
                context,
                requestId,
                "server-1",
                assertNotNull(conversationId.value),
                "Provide input",
                listOf(
                    assertNotNull(field.slot.value),
                    assertNotNull(secondField.slot.value),
                    assertNotNull(field.slot.value),
                ),
                "",
            )
            assertEquals(CODEX_AGENT_STATUS_OK, result.status)
            val elicitation = assertNotNull(result.slot.value)
            requestId.bytes!![0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversationId.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, field.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, secondField.slot.ptr))

            assertElicitationString(context, elicitation, "request-1", ::codexAgentElicitationRequestIdCopy)
            assertElicitationString(context, elicitation, "server-1", ::codexAgentElicitationServerNameCopy)
            assertElicitationString(context, elicitation, "Provide input", ::codexAgentElicitationMessageCopy)
            assertElicitationInt(context, elicitation, 1, ::codexAgentElicitationHasForm)
            assertElicitationInt(context, elicitation, 1, ::codexAgentElicitationHasUrl)
            assertElicitationString(context, elicitation, "", ::codexAgentElicitationUrlCopy)
            val formCount = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationFormCount(context, elicitation, formCount.ptr))
            assertEquals(3uL, formCount.value)
            val idChild = emptyElicitationHandle()
            val firstFieldChild = emptyElicitationHandle()
            val secondFieldChild = emptyElicitationHandle()
            val duplicateFieldChild = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationConversationId(context, elicitation, idChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationFormAt(context, elicitation, 0uL, firstFieldChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationFormAt(context, elicitation, 1uL, secondFieldChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationFormAt(context, elicitation, 2uL, duplicateFieldChild.ptr),
            )
            assertNotEquals(firstFieldChild.value, duplicateFieldChild.value)
            assertElicitationString(
                context,
                assertNotNull(idChild.value),
                "conversation-λ",
                ::codexAgentConversationIdValueCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(firstFieldChild.value),
                "field",
                ::codexAgentFormFieldNameCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(secondFieldChild.value),
                "second",
                ::codexAgentFormFieldNameCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(duplicateFieldChild.value),
                "field",
                ::codexAgentFormFieldNameCopy,
            )

            val textConcrete = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormTextValueCreate(context, elicitationUtf8("answer").view, textConcrete.ptr),
            )
            val textCarrier = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueFromText(context, assertNotNull(textConcrete.value), textCarrier.ptr),
            )
            val listConcrete = createElicitationTextList(context, listOf("a", "a"))
            val listCarrier = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueFromTextList(context, assertNotNull(listConcrete.value), listCarrier.ptr),
            )
            val answerKey = elicitationUtf8("answer")
            val response = createElicitationResponse(
                context,
                0,
                listOf(answerKey, elicitationUtf8("choices")),
                listOf(assertNotNull(textCarrier.value), assertNotNull(listCarrier.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, response.status)
            answerKey.bytes!![0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, textConcrete.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueDestroy(context, listConcrete.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, textCarrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, listCarrier.ptr))
            val responseHandle = assertNotNull(response.slot.value)
            assertElicitationInt(context, responseHandle, 0, ::codexAgentElicitationResponseAction)
            val contentCount = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationResponseContentCount(context, responseHandle, contentCount.ptr),
            )
            assertEquals(2uL, contentCount.value)
            val answerValue = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationResponseContentValue(
                    context,
                    responseHandle,
                    elicitationUtf8("answer").view,
                    answerValue.ptr,
                ),
            )
            val answerText = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueText(context, assertNotNull(answerValue.value), answerText.ptr),
            )
            assertElicitationString(context, assertNotNull(answerText.value), "answer", ::codexAgentFormTextValueValueCopy)
            val missing = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentElicitationResponseContentValue(
                    context,
                    responseHandle,
                    elicitationUtf8("missing").view,
                    missing.ptr,
                ),
            )
            assertNull(missing.value)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, result.slot.ptr))
            assertElicitationString(
                context,
                assertNotNull(idChild.value),
                "conversation-λ",
                ::codexAgentConversationIdValueCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(firstFieldChild.value),
                "field",
                ::codexAgentFormFieldNameCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseDestroy(context, response.slot.ptr))
            assertElicitationString(context, assertNotNull(answerText.value), "answer", ::codexAgentFormTextValueValueCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, idChild.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, firstFieldChild.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, secondFieldChild.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, duplicateFieldChild.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, answerValue.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, answerText.ptr))

            val emptyResponse = createElicitationResponse(context, 1, emptyList(), emptyList())
            assertEquals(CODEX_AGENT_STATUS_OK, emptyResponse.status)
            assertElicitationInt(
                context,
                assertNotNull(emptyResponse.slot.value),
                1,
                ::codexAgentElicitationResponseAction,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentElicitationResponseContentCount(
                    context,
                    assertNotNull(emptyResponse.slot.value),
                    contentCount.ptr,
                ),
            )
            assertEquals(0uL, contentCount.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationResponseDestroy(context, emptyResponse.slot.ptr))

            val absent = createElicitation(
                context,
                elicitationUtf8("absent"),
                "server",
                assertNotNull(createElicitationConversationId(context, "c-absent").value),
                "message",
                null,
                null,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, absent.status)
            val absentHandle = assertNotNull(absent.slot.value)
            assertElicitationInt(context, absentHandle, 0, ::codexAgentElicitationHasForm)
            assertElicitationInt(context, absentHandle, 0, ::codexAgentElicitationHasUrl)
            val absentCount = alloc<ULongVar>().also { it.value = 91uL }
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentElicitationFormCount(context, absentHandle, absentCount.ptr),
            )
            assertEquals(91uL, absentCount.value)
            val presentEmpty = createElicitation(
                context,
                elicitationUtf8("empty"),
                "server",
                assertNotNull(createElicitationConversationId(context, "c-empty").value),
                "message",
                emptyList(),
                "",
            )
            assertEquals(CODEX_AGENT_STATUS_OK, presentEmpty.status)
            val emptyHandle = assertNotNull(presentEmpty.slot.value)
            assertElicitationInt(context, emptyHandle, 1, ::codexAgentElicitationHasForm)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationFormCount(context, emptyHandle, absentCount.ptr))
            assertEquals(0uL, absentCount.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, absent.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, presentEmpty.slot.ptr))
        }

    @Test
    fun pendingElicitationAndInteractionStateProjectEveryFieldAndOwnedChild(): Unit =
        withElicitationContexts { context, _ ->
            val conversation = createElicitationConversationId(context, "conversation-owned")
            val elicitation = createElicitation(
                context,
                elicitationUtf8("elicitation-owned"),
                "server",
                assertNotNull(conversation.value),
                "message",
                emptyList(),
                null,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, elicitation.status)
            val pending = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingElicitationCreate(context, assertNotNull(elicitation.slot.value), pending.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, elicitation.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversation.ptr))
            val pendingHandle = assertNotNull(pending.value)
            assertElicitationString(
                context,
                pendingHandle,
                "elicitation-owned",
                ::codexAgentPendingElicitationRequestIdCopy,
            )
            val pendingId = emptyElicitationHandle()
            val pendingChild = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingElicitationConversationId(context, pendingHandle, pendingId.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingElicitationElicitation(context, pendingHandle, pendingChild.ptr),
            )
            assertElicitationString(
                context,
                assertNotNull(pendingId.value),
                "conversation-owned",
                ::codexAgentConversationIdValueCopy,
            )
            assertElicitationString(
                context,
                assertNotNull(pendingChild.value),
                "elicitation-owned",
                ::codexAgentElicitationRequestIdCopy,
            )

            val approvalConversation = createElicitationConversationId(context, "approval-conversation")
            val approval = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalCreate(
                    context,
                    elicitationUtf8("approval-1").view,
                    assertNotNull(approvalConversation.value),
                    elicitationUtf8("Approve").view,
                    elicitationUtf8("Details").view,
                    approval.ptr,
                ),
            )
            val approvalCarrier = emptyElicitationHandle()
            val elicitationCarrier = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionFromApproval(
                    context,
                    assertNotNull(approval.value),
                    approvalCarrier.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionFromElicitation(context, pendingHandle, elicitationCarrier.ptr),
            )
            val failure = createElicitationFailure(context, "offline", "Offline", 1)
            val resolving = arrayOf(elicitationUtf8("approval-1"), elicitationUtf8("approval-1"), elicitationUtf8("other"))
            val state = createInteractionState(
                context,
                listOf(
                    assertNotNull(approvalCarrier.value),
                    assertNotNull(elicitationCarrier.value),
                    assertNotNull(approvalCarrier.value),
                ),
                resolving,
                assertNotNull(failure.value),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, state.status)
            resolving[0].bytes!![0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingApprovalDestroy(context, approval.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, approvalConversation.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingElicitationDestroy(context, pending.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, approvalCarrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, elicitationCarrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failure.ptr))
            val stateHandle = assertNotNull(state.slot.value)
            val count = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStatePendingCount(context, stateHandle, count.ptr))
            assertEquals(3uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStateResolvingRequestIdsCount(context, stateHandle, count.ptr),
            )
            assertEquals(2uL, count.value)
            assertElicitationContains(context, stateHandle, "approval-1", 1)
            assertElicitationContains(context, stateHandle, "other", 1)
            assertElicitationContains(context, stateHandle, "missing", 0)
            assertElicitationInt(context, stateHandle, 1, ::codexAgentInteractionStateHasFailure)

            val first = emptyElicitationHandle()
            val second = emptyElicitationHandle()
            val duplicate = emptyElicitationHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStatePendingAt(context, stateHandle, 0uL, first.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStatePendingAt(context, stateHandle, 1uL, second.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStatePendingAt(context, stateHandle, 2uL, duplicate.ptr))
            assertNotEquals(first.value, duplicate.value)
            assertElicitationInt(context, assertNotNull(first.value), 0, ::codexAgentPendingInteractionKind)
            assertElicitationInt(context, assertNotNull(second.value), 1, ::codexAgentPendingInteractionKind)
            val firstApproval = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionApproval(context, assertNotNull(first.value), firstApproval.ptr),
            )
            assertElicitationString(
                context,
                assertNotNull(firstApproval.value),
                "approval-1",
                ::codexAgentPendingApprovalRequestIdCopy,
            )
            val wrong = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPendingInteractionElicitation(context, assertNotNull(first.value), wrong.ptr),
            )
            assertNull(wrong.value)
            val secondPending = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionElicitation(context, assertNotNull(second.value), secondPending.ptr),
            )
            val stateFailure = emptyElicitationHandle()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateFailure(context, stateHandle, stateFailure.ptr))
            assertElicitationString(
                context,
                assertNotNull(stateFailure.value),
                "offline",
                ::codexAgentFailureCodeCopy,
            )

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateDestroy(context, state.slot.ptr))
            assertElicitationInt(context, assertNotNull(first.value), 0, ::codexAgentPendingInteractionKind)
            assertElicitationString(
                context,
                assertNotNull(stateFailure.value),
                "offline",
                ::codexAgentFailureCodeCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, first.ptr))
            assertElicitationString(
                context,
                assertNotNull(firstApproval.value),
                "approval-1",
                ::codexAgentPendingApprovalRequestIdCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingApprovalDestroy(context, firstApproval.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, second.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, duplicate.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingElicitationDestroy(context, secondPending.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, stateFailure.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, pendingId.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, pendingChild.ptr))

            val emptyState = createInteractionState(context, emptyList(), emptyArray(), null)
            assertEquals(CODEX_AGENT_STATUS_OK, emptyState.status)
            val emptyStateHandle = assertNotNull(emptyState.slot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStatePendingCount(context, emptyStateHandle, count.ptr))
            assertEquals(0uL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStateResolvingRequestIdsCount(context, emptyStateHandle, count.ptr),
            )
            assertEquals(0uL, count.value)
            assertElicitationInt(context, emptyStateHandle, 0, ::codexAgentInteractionStateHasFailure)
            val absentFailure = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentInteractionStateFailure(context, emptyStateHandle, absentFailure.ptr),
            )
            assertNull(absentFailure.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInteractionStateDestroy(context, emptyState.slot.ptr))
        }

    @Test
    fun rejectsMalformedContextTypeIndexEnumFlagUtf8AndOutputBoundaries(): Unit =
        withElicitationContexts { context, otherContext ->
            val slot = emptyElicitationHandle()
            val occupied = emptyElicitationHandle().also { it.value = context }
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentFormValueFromText(context, context, slot.ptr),
            )
            val text = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormTextValueCreate(context, elicitationUtf8("text").view, text.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormValueFromText(context, assertNotNull(text.value), occupied.ptr),
            )
            assertEquals(context, occupied.value)
            val carrier = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFormValueFromText(context, assertNotNull(text.value), carrier.ptr),
            )
            val wrongContextOutput = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentFormValueText(otherContext, assertNotNull(carrier.value), wrongContextOutput.ptr),
            )
            assertNull(wrongContextOutput.value)

            val invalidType = createElicitationField(context, type = 99)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, invalidType.status)
            assertNull(invalidType.slot.value)
            val invalidFormat = createElicitationField(context, format = 99)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, invalidFormat.status)
            val invalidFlag = createElicitationField(context, isRequired = 2)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, invalidFlag.status)
            val invalidUtf8 = createElicitationField(context, name = invalidElicitationUtf8())
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, invalidUtf8.status)
            val malformedLength = createElicitationField(context, minimumLength = -1)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, malformedLength.status)

            val field = createElicitationField(context)
            assertEquals(CODEX_AGENT_STATUS_OK, field.status)
            val badIndex = emptyElicitationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFormFieldOptionAt(context, assertNotNull(field.slot.value), 0uL, badIndex.ptr),
            )
            assertNull(badIndex.value)
            val required = alloc<ULongVar>().also { it.value = 45uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentElicitationRequestIdCopy(
                    context,
                    assertNotNull(field.slot.value),
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(45uL, required.value)

            val conversation = createElicitationConversationId(context, "conversation")
            val malformedForm = createElicitationRaw(
                context,
                assertNotNull(conversation.value),
                hasForm = 0,
                forms = listOf(assertNotNull(field.slot.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, malformedForm.status)
            val malformedUrl = createElicitationRaw(
                context,
                assertNotNull(conversation.value),
                hasUrl = 0,
                url = elicitationUtf8("not-absent"),
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, malformedUrl.status)
            val invalidAction = createElicitationResponse(context, 99, emptyList(), emptyList())
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, invalidAction.status)
            val duplicateKeys = createElicitationResponse(
                context,
                0,
                listOf(elicitationUtf8("same"), elicitationUtf8("same")),
                listOf(assertNotNull(carrier.value), assertNotNull(carrier.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, duplicateKeys.status)

            val stale = assertNotNull(field.slot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, field.slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormFieldDestroy(context, field.slot.ptr))
            val scalar = alloc<IntVar>().also { it.value = 81 }
            assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentFormFieldType(context, stale, scalar.ptr))
            assertEquals(81, scalar.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversation.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormValueDestroy(context, carrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextValueDestroy(context, text.ptr))
        }

    @Test
    fun contextTeardownReclaimsEveryOutstandingFamilySnapshot(): Unit = memScoped {
        val contextSlot = emptyElicitationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val field = createElicitationField(context)
        val conversation = createElicitationConversationId(context, "reclaim")
        val elicitation = createElicitation(
            context,
            elicitationUtf8("request"),
            "server",
            assertNotNull(conversation.value),
            "message",
            listOf(assertNotNull(field.slot.value)),
            null,
        )
        val pending = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPendingElicitationCreate(context, assertNotNull(elicitation.slot.value), pending.ptr),
        )
        val carrier = emptyElicitationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPendingInteractionFromElicitation(context, assertNotNull(pending.value), carrier.ptr),
        )
        val state = createInteractionState(context, listOf(assertNotNull(carrier.value)), emptyArray(), null)
        val handles = listOf(
            assertNotNull(field.slot.value),
            assertNotNull(conversation.value),
            assertNotNull(elicitation.slot.value),
            assertNotNull(pending.value),
            assertNotNull(carrier.value),
            assertNotNull(state.slot.value),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
        val sentinel = alloc<IntVar>().also { it.value = 99 }
        handles.forEach { handle ->
            assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentInteractionStateHasFailure(context, handle, sentinel.ptr))
            assertEquals(99, sentinel.value)
        }
    }
}

private data class ElicitationHandleResult(
    val status: Int,
    val slot: COpaquePointerVar,
)

private data class ElicitationUtf8(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private typealias ElicitationStringGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias ElicitationIntGetter = (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int

private typealias ElicitationOptionalIntGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<IntVar>?,
) -> Int

private typealias ElicitationOptionalDoubleGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<DoubleVar>?,
) -> Int

private typealias ElicitationOptionalLongGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<LongVar>?,
) -> Int

private fun withElicitationContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyElicitationHandle()
    val otherContextSlot = emptyElicitationHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContextSlot.ptr))
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    block(context, otherContext)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
}

private fun MemScope.emptyElicitationHandle(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.elicitationUtf8(value: String): ElicitationUtf8 {
    val encoded = value.encodeToByteArray()
    val bytes = if (encoded.isEmpty()) null else allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> checkNotNull(bytes)[index] = byte.toUByte() }
    val view = alloc<codex_agent_string_view>()
    view.data = bytes
    view.size = encoded.size.toULong()
    return ElicitationUtf8(view.ptr, bytes)
}

private fun MemScope.absentElicitationUtf8(): ElicitationUtf8 = elicitationUtf8("")

private fun MemScope.invalidElicitationUtf8(): ElicitationUtf8 {
    val bytes = allocArray<UByteVar>(1)
    bytes[0] = 0x80u
    val view = alloc<codex_agent_string_view>()
    view.data = bytes
    view.size = 1uL
    return ElicitationUtf8(view.ptr, bytes)
}

private fun MemScope.createElicitationOption(
    context: COpaquePointer,
    value: String,
    title: String,
    description: String?,
): COpaquePointerVar {
    val slot = emptyElicitationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormOptionCreate(
            context,
            elicitationUtf8(value).view,
            1,
            elicitationUtf8(title).view,
            if (description == null) 0 else 1,
            (description?.let(::elicitationUtf8) ?: absentElicitationUtf8()).view,
            slot.ptr,
        ),
    )
    return slot
}

private fun MemScope.createElicitationTextList(
    context: COpaquePointer,
    values: List<String>,
): COpaquePointerVar {
    val views = values.map(::elicitationUtf8)
    val input = if (views.isEmpty()) null else allocArray<codex_agent_string_view>(views.size).also { array ->
        views.forEachIndexed { index, value ->
            array[index].data = value.view.pointed.data
            array[index].size = value.view.pointed.size
        }
    }
    val slot = emptyElicitationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFormTextListValueCreate(context, input, views.size.toULong(), slot.ptr),
    )
    return slot
}

@Suppress("LongParameterList")
private fun MemScope.createElicitationField(
    context: COpaquePointer,
    name: ElicitationUtf8 = elicitationUtf8("name"),
    title: ElicitationUtf8 = elicitationUtf8("title"),
    description: String? = null,
    isRequired: Int = 0,
    type: Int = 0,
    options: List<COpaquePointer> = emptyList(),
    defaultValue: COpaquePointer? = null,
    minimum: Double? = null,
    maximum: Double? = null,
    format: Int? = null,
    minimumLength: Long? = null,
    maximumLength: Long? = null,
    minimumSelections: Long? = null,
    maximumSelections: Long? = null,
    allowsOther: Int = 0,
    isSecret: Int = 0,
): ElicitationHandleResult {
    val optionInput = if (options.isEmpty()) null else allocArray<COpaquePointerVar>(options.size).also { array ->
        options.forEachIndexed { index, value -> array[index] = value }
    }
    val slot = emptyElicitationHandle()
    val status = codexAgentFormFieldCreate(
        context,
        name.view,
        title.view,
        if (description == null) 0 else 1,
        (description?.let(::elicitationUtf8) ?: absentElicitationUtf8()).view,
        isRequired,
        type,
        optionInput,
        options.size.toULong(),
        if (defaultValue == null) 0 else 1,
        defaultValue,
        if (minimum == null) 0 else 1,
        minimum ?: 0.0,
        if (maximum == null) 0 else 1,
        maximum ?: 0.0,
        if (format == null) 0 else 1,
        format ?: 0,
        if (minimumLength == null) 0 else 1,
        minimumLength ?: 0,
        if (maximumLength == null) 0 else 1,
        maximumLength ?: 0,
        if (minimumSelections == null) 0 else 1,
        minimumSelections ?: 0,
        if (maximumSelections == null) 0 else 1,
        maximumSelections ?: 0,
        allowsOther,
        isSecret,
        slot.ptr,
    )
    return ElicitationHandleResult(status, slot)
}

private fun MemScope.createElicitationConversationId(context: COpaquePointer, value: String): COpaquePointerVar {
    val slot = emptyElicitationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationIdCreate(context, elicitationUtf8(value).view, slot.ptr),
    )
    return slot
}

private fun MemScope.createElicitation(
    context: COpaquePointer,
    requestId: ElicitationUtf8,
    serverName: String,
    conversationId: COpaquePointer,
    message: String,
    form: List<COpaquePointer>?,
    url: String?,
): ElicitationHandleResult = createElicitationRaw(
    context,
    conversationId,
    requestId,
    serverName,
    message,
    if (form == null) 0 else 1,
    form.orEmpty(),
    if (url == null) 0 else 1,
    url?.let(::elicitationUtf8) ?: absentElicitationUtf8(),
)

@Suppress("LongParameterList")
private fun MemScope.createElicitationRaw(
    context: COpaquePointer,
    conversationId: COpaquePointer,
    requestId: ElicitationUtf8 = elicitationUtf8("request"),
    serverName: String = "server",
    message: String = "message",
    hasForm: Int = 0,
    forms: List<COpaquePointer> = emptyList(),
    hasUrl: Int = 0,
    url: ElicitationUtf8 = absentElicitationUtf8(),
): ElicitationHandleResult {
    val formInput = if (forms.isEmpty()) null else allocArray<COpaquePointerVar>(forms.size).also { array ->
        forms.forEachIndexed { index, value -> array[index] = value }
    }
    val slot = emptyElicitationHandle()
    val status = codexAgentElicitationCreate(
        context,
        requestId.view,
        elicitationUtf8(serverName).view,
        conversationId,
        elicitationUtf8(message).view,
        hasForm,
        formInput,
        forms.size.toULong(),
        hasUrl,
        url.view,
        slot.ptr,
    )
    return ElicitationHandleResult(status, slot)
}

private fun MemScope.createElicitationResponse(
    context: COpaquePointer,
    action: Int,
    keys: List<ElicitationUtf8>,
    values: List<COpaquePointer>,
): ElicitationHandleResult {
    require(keys.size == values.size)
    val keyInput = if (keys.isEmpty()) null else allocArray<codex_agent_string_view>(keys.size).also { array ->
        keys.forEachIndexed { index, key ->
            array[index].data = key.view.pointed.data
            array[index].size = key.view.pointed.size
        }
    }
    val valueInput = if (values.isEmpty()) null else allocArray<COpaquePointerVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }
    val slot = emptyElicitationHandle()
    val status = codexAgentElicitationResponseCreate(
        context,
        action,
        keyInput,
        valueInput,
        keys.size.toULong(),
        slot.ptr,
    )
    return ElicitationHandleResult(status, slot)
}

private fun MemScope.createElicitationFailure(
    context: COpaquePointer,
    code: String,
    message: String,
    recoverable: Int,
): COpaquePointerVar {
    val slot = emptyElicitationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFailureCreate(
            context,
            elicitationUtf8(code).view,
            elicitationUtf8(message).view,
            recoverable,
            slot.ptr,
        ),
    )
    return slot
}

private fun MemScope.createInteractionState(
    context: COpaquePointer,
    pending: List<COpaquePointer>,
    resolving: Array<ElicitationUtf8>,
    failure: COpaquePointer?,
): ElicitationHandleResult {
    val pendingInput = if (pending.isEmpty()) null else allocArray<COpaquePointerVar>(pending.size).also { array ->
        pending.forEachIndexed { index, value -> array[index] = value }
    }
    val resolvingInput = if (resolving.isEmpty()) null else
        allocArray<codex_agent_string_view>(resolving.size).also { array ->
            resolving.forEachIndexed { index, value ->
                array[index].data = value.view.pointed.data
                array[index].size = value.view.pointed.size
            }
        }
    val slot = emptyElicitationHandle()
    val status = codexAgentInteractionStateCreate(
        context,
        pendingInput,
        pending.size.toULong(),
        resolvingInput,
        resolving.size.toULong(),
        if (failure == null) 0 else 1,
        failure,
        slot.ptr,
    )
    return ElicitationHandleResult(status, slot)
}

private fun MemScope.assertElicitationString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    getter: ElicitationStringGetter,
) {
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    val expectedBytes = expected.encodeToByteArray()
    assertEquals(
        if (expectedBytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        getter(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = if (expectedBytes.isEmpty()) null else allocArray<UByteVar>(expectedBytes.size)
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, buffer, required.value, required.ptr))
    val actual = if (expectedBytes.isEmpty()) ByteArray(0) else ByteArray(expectedBytes.size) { buffer!![it].toByte() }
    assertEquals(expected, actual.decodeToString())
}

private fun MemScope.assertElicitationInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: ElicitationIntGetter,
) {
    val output = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertElicitationOptionalInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHas: Int,
    expected: Int,
    getter: ElicitationOptionalIntGetter,
) {
    val has = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, has.ptr, value.ptr))
    assertEquals(expectedHas, has.value)
    assertEquals(expected, value.value)
}

private fun MemScope.assertElicitationOptionalDouble(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHas: Int,
    expected: Double,
    getter: ElicitationOptionalDoubleGetter,
) {
    val has = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<DoubleVar>().also { it.value = Double.NaN }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, has.ptr, value.ptr))
    assertEquals(expectedHas, has.value)
    assertEquals(expected.toBits(), value.value.toBits())
}

private fun MemScope.assertElicitationOptionalLong(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHas: Int,
    expected: Long,
    getter: ElicitationOptionalLongGetter,
) {
    val has = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<LongVar>().also { it.value = Long.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, has.ptr, value.ptr))
    assertEquals(expectedHas, has.value)
    assertEquals(expected, value.value)
}

private fun MemScope.assertElicitationTextList(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: List<String>,
) {
    val count = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFormTextListValueCount(context, handle, count.ptr))
    assertEquals(expected.size.toULong(), count.value)
    expected.forEachIndexed { index, value ->
        assertElicitationString(context, handle, value) { c, h, b, capacity, required ->
            codexAgentFormTextListValueCopyAt(c, h, index.toULong(), b, capacity, required)
        }
    }
}

private fun MemScope.assertElicitationContains(
    context: COpaquePointer,
    state: COpaquePointer,
    requestId: String,
    expected: Int,
) {
    val contains = alloc<IntVar>().also { it.value = -1 }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInteractionStateResolvingRequestIdsContains(
            context,
            state,
            elicitationUtf8(requestId).view,
            contains.ptr,
        ),
    )
    assertEquals(expected, contains.value)
}
