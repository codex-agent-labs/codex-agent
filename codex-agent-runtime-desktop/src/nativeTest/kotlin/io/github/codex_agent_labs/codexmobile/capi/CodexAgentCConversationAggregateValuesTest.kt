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

class CodexAgentCConversationAggregateValuesTest {
    @Test
    fun projectsAgentConversationAndMessagesWithExactOrderedSnapshots(): Unit = withAggregateContexts {
        context, _ ->
        val plugin = createAggregatePlugin(context, "plugin", "file:///plugin")
        val invocation = createAggregateInvocationFromPlugin(context, assertNotNull(plugin.value))
        val id = aggregateView("message-one")
        val clientId = aggregateView("client-one")
        val text = aggregateView("message text")
        val reasoning = aggregateView("reasoning")
        val presentEmpty = aggregateView("")
        val shell = aggregateView("pwd")
        val capabilities = aggregateInts(0, 0)
        val invocations = aggregateHandles(assertNotNull(invocation.value), assertNotNull(invocation.value))
        val message = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMessageCreate(
                context,
                id.view,
                1,
                clientId.view,
                1,
                text.view,
                1,
                1,
                reasoning.view,
                1,
                presentEmpty.view,
                1,
                shell.view,
                1,
                -7,
                capabilities,
                2uL,
                invocations,
                2uL,
                message.ptr,
            ),
        )
        id.bytes!![0] = 'X'.code.toUByte()
        text.bytes!![0] = 'X'.code.toUByte()
        invocations[0] = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, invocation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationPluginDestroy(context, plugin.ptr))

        val messageHandle = assertNotNull(message.value)
        assertAggregateString(context, messageHandle, "message-one", ::codexAgentMessageIdCopy)
        assertAggregateFlag(context, messageHandle, 1, ::codexAgentMessageHasClientMessageId)
        assertAggregateString(context, messageHandle, "client-one", ::codexAgentMessageClientMessageIdCopy)
        assertAggregateInt(context, messageHandle, 1, ::codexAgentMessageRole)
        assertAggregateString(context, messageHandle, "message text", ::codexAgentMessageTextCopy)
        assertAggregateInt(context, messageHandle, 1, ::codexAgentMessageCollaborationMode)
        assertAggregateFlag(context, messageHandle, 1, ::codexAgentMessageHasReasoning)
        assertAggregateString(context, messageHandle, "reasoning", ::codexAgentMessageReasoningCopy)
        assertAggregateFlag(context, messageHandle, 1, ::codexAgentMessageHasPlan)
        assertAggregateString(context, messageHandle, "", ::codexAgentMessagePlanCopy)
        assertAggregateFlag(context, messageHandle, 1, ::codexAgentMessageHasShellCommand)
        assertAggregateString(context, messageHandle, "pwd", ::codexAgentMessageShellCommandCopy)
        val hasExitCode = alloc<IntVar>().also { it.value = -1 }
        val exitCode = alloc<IntVar>().also { it.value = 99 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMessageExitCode(context, messageHandle, hasExitCode.ptr, exitCode.ptr),
        )
        assertEquals(1, hasExitCode.value)
        assertEquals(-7, exitCode.value)
        assertAggregateCount(context, messageHandle, 1uL, ::codexAgentMessageCapabilitiesCount)
        val hasCapability = alloc<IntVar>().also { it.value = -1 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMessageHasCapability(context, messageHandle, 0, hasCapability.ptr),
        )
        assertEquals(1, hasCapability.value)
        assertAggregateCount(context, messageHandle, 2uL, ::codexAgentMessageInvocationsCount)
        val copiedMessageInvocations = List(2) { emptyAggregateHandle() }
        copiedMessageInvocations.forEachIndexed { index, slot ->
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMessageInvocationAt(context, messageHandle, index.toULong(), slot.ptr),
            )
            assertAggregateInt(context, assertNotNull(slot.value), 0, ::codexAgentInvocationKind)
        }
        assertNotEquals(copiedMessageInvocations[0].value, copiedMessageInvocations[1].value)
        copiedMessageInvocations.forEach {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, it.ptr))
        }

        val secondMessage = createBasicAggregateMessage(context, "message-two")
        val conversationId = createAggregateConversationId(context, "conversation")
        val summary = createAggregateSummary(context, assertNotNull(conversationId.value), "title", 42L)
        val messageInputs = aggregateHandles(
            messageHandle,
            assertNotNull(secondMessage.value),
            messageHandle,
        )
        val conversation = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationValueCreate(
                context,
                assertNotNull(summary.value),
                messageInputs,
                3uL,
                conversation.ptr,
            ),
        )
        messageInputs[0] = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, message.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, message.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, secondMessage.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, summary.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversationId.ptr))

        val conversationHandle = assertNotNull(conversation.value)
        assertAggregateCount(context, conversationHandle, 3uL, ::codexAgentConversationValueMessagesCount)
        val copiedSummary = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationValueSummary(context, conversationHandle, copiedSummary.ptr),
        )
        assertAggregateString(
            context,
            assertNotNull(copiedSummary.value),
            "title",
            ::codexAgentConversationSummaryTitleCopy,
        )
        val copiedMessages = List(3) { emptyAggregateHandle() }
        copiedMessages.forEachIndexed { index, slot ->
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationValueMessageAt(context, conversationHandle, index.toULong(), slot.ptr),
            )
        }
        assertNotEquals(copiedMessages[0].value, copiedMessages[2].value)
        assertAggregateString(context, assertNotNull(copiedMessages[0].value), "message-one", ::codexAgentMessageIdCopy)
        assertAggregateString(context, assertNotNull(copiedMessages[1].value), "message-two", ::codexAgentMessageIdCopy)
        assertAggregateString(context, assertNotNull(copiedMessages[2].value), "message-one", ::codexAgentMessageIdCopy)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationValueDestroy(context, conversation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationValueDestroy(context, conversation.ptr))
        assertAggregateString(context, assertNotNull(copiedMessages[0].value), "message-one", ::codexAgentMessageIdCopy)
        copiedMessages.forEach { assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, it.ptr)) }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, copiedSummary.ptr))
    }

    @Test
    fun projectsAgentTurnRequestAndInvocationCarrierExactly(): Unit = withAggregateContexts {
        context, _ ->
        val plugin = createAggregatePlugin(context, "plugin", "file:///plugin")
        val skill = createAggregateSkill(context, "skill", "/skill")
        val pluginInvocation = createAggregateInvocationFromPlugin(context, assertNotNull(plugin.value))
        val skillInvocation = createAggregateInvocationFromSkill(context, assertNotNull(skill.value))
        assertAggregateInt(context, assertNotNull(pluginInvocation.value), 0, ::codexAgentInvocationKind)
        assertAggregateInt(context, assertNotNull(skillInvocation.value), 1, ::codexAgentInvocationKind)

        val prompt = aggregateView("prompt")
        val presentEmpty = aggregateView("")
        val absent = aggregateAbsentView()
        val effort = aggregateView("high")
        val tier = aggregateView("fast")
        val capabilities = aggregateInts(0, 0)
        val invocations = aggregateHandles(
            assertNotNull(pluginInvocation.value),
            assertNotNull(skillInvocation.value),
            assertNotNull(pluginInvocation.value),
        )
        val request = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentTurnRequestCreate(
                context,
                prompt.view,
                1,
                presentEmpty.view,
                0,
                absent,
                1,
                effort.view,
                1,
                tier.view,
                3,
                capabilities,
                2uL,
                invocations,
                3uL,
                1,
                request.ptr,
            ),
        )
        prompt.bytes!![0] = 'X'.code.toUByte()
        invocations[0] = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, pluginInvocation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, skillInvocation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationPluginDestroy(context, plugin.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationSkillDestroy(context, skill.ptr))

        val requestHandle = assertNotNull(request.value)
        assertAggregateString(context, requestHandle, "prompt", ::codexAgentTurnRequestPromptCopy)
        assertAggregateFlag(context, requestHandle, 1, ::codexAgentTurnRequestHasClientMessageId)
        assertAggregateString(context, requestHandle, "", ::codexAgentTurnRequestClientMessageIdCopy)
        assertAggregateFlag(context, requestHandle, 0, ::codexAgentTurnRequestHasModel)
        val untouchedRequired = alloc<ULongVar>().also { it.value = 41uL }
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentTurnRequestModelCopy(context, requestHandle, null, 0uL, untouchedRequired.ptr),
        )
        assertEquals(41uL, untouchedRequired.value)
        assertAggregateFlag(context, requestHandle, 1, ::codexAgentTurnRequestHasEffort)
        assertAggregateString(context, requestHandle, "high", ::codexAgentTurnRequestEffortCopy)
        assertAggregateFlag(context, requestHandle, 1, ::codexAgentTurnRequestHasServiceTier)
        assertAggregateString(context, requestHandle, "fast", ::codexAgentTurnRequestServiceTierCopy)
        assertAggregateInt(context, requestHandle, 3, ::codexAgentTurnRequestApprovalPreset)
        assertAggregateCount(context, requestHandle, 1uL, ::codexAgentTurnRequestCapabilitiesCount)
        val hasCapability = alloc<IntVar>().also { it.value = -1 }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentTurnRequestHasCapability(context, requestHandle, 0, hasCapability.ptr),
        )
        assertEquals(1, hasCapability.value)
        assertAggregateCount(context, requestHandle, 3uL, ::codexAgentTurnRequestInvocationsCount)
        assertAggregateInt(context, requestHandle, 1, ::codexAgentTurnRequestCollaborationMode)

        val copiedInvocations = List(3) { emptyAggregateHandle() }
        copiedInvocations.forEachIndexed { index, slot ->
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentTurnRequestInvocationAt(context, requestHandle, index.toULong(), slot.ptr),
            )
        }
        assertNotEquals(copiedInvocations[0].value, copiedInvocations[2].value)
        assertAggregateInt(context, assertNotNull(copiedInvocations[0].value), 0, ::codexAgentInvocationKind)
        assertAggregateInt(context, assertNotNull(copiedInvocations[1].value), 1, ::codexAgentInvocationKind)
        assertAggregateInt(context, assertNotNull(copiedInvocations[2].value), 0, ::codexAgentInvocationKind)

        val wrongDowncast = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentInvocationSkill(context, assertNotNull(copiedInvocations[0].value), wrongDowncast.ptr),
        )
        assertNull(wrongDowncast.value)
        val copiedPlugin = emptyAggregateHandle()
        val copiedSkill = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInvocationPlugin(context, assertNotNull(copiedInvocations[0].value), copiedPlugin.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentInvocationSkill(context, assertNotNull(copiedInvocations[1].value), copiedSkill.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(context, request.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnRequestDestroy(context, request.ptr))
        assertAggregateString(
            context,
            assertNotNull(copiedPlugin.value),
            "plugin",
            ::codexAgentInvocationPluginNameCopy,
        )
        assertAggregateString(
            context,
            assertNotNull(copiedSkill.value),
            "skill",
            ::codexAgentInvocationSkillNameCopy,
        )
        copiedInvocations.forEach { assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, it.ptr)) }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationPluginDestroy(context, copiedPlugin.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationSkillDestroy(context, copiedSkill.ptr))
    }

    @Test
    fun projectsAgentConversationStateTruthTableAndNullableValuesExactly(): Unit = withAggregateContexts {
        context, _ ->
        val id = createAggregateConversationId(context, "state-conversation")
        val summary = createAggregateSummary(context, assertNotNull(id.value), "state title", 5L)
        val message = createBasicAggregateMessage(context, "state-message")
        val conversation = emptyAggregateHandle()
        val messages = aggregateHandles(assertNotNull(message.value))
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationValueCreate(
                context,
                assertNotNull(summary.value),
                messages,
                1uL,
                conversation.ptr,
            ),
        )
        val progress = createAggregateTurnProgress(context, "turn")
        val failure = createAggregateFailure(context, "recoverable", true)
        val model = aggregateView("model")
        val effort = aggregateView("")
        val tier = aggregateView("tier")
        val state = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateCreate(
                context,
                2,
                1,
                assertNotNull(id.value),
                1,
                assertNotNull(conversation.value),
                assertNotNull(progress.value),
                1,
                model.view,
                1,
                effort.view,
                1,
                tier.view,
                1,
                assertNotNull(failure.value),
                state.ptr,
            ),
        )
        model.bytes!![0] = 'X'.code.toUByte()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationValueDestroy(context, conversation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, message.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, summary.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, progress.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failure.ptr))

        val stateHandle = assertNotNull(state.value)
        assertAggregateInt(context, stateHandle, 2, ::codexAgentConversationStateStatus)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateHasConversationId)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateHasConversation)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateHasModel)
        assertAggregateString(context, stateHandle, "model", ::codexAgentConversationStateModelCopy)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateHasEffort)
        assertAggregateString(context, stateHandle, "", ::codexAgentConversationStateEffortCopy)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateHasServiceTier)
        assertAggregateString(context, stateHandle, "tier", ::codexAgentConversationStateServiceTierCopy)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateCanStartTurn)
        assertAggregateFlag(context, stateHandle, 1, ::codexAgentConversationStateCanReload)
        assertAggregateFlag(context, stateHandle, 0, ::codexAgentConversationStateCanCancelTurn)

        val copiedId = emptyAggregateHandle()
        val copiedConversation = emptyAggregateHandle()
        val copiedProgress = emptyAggregateHandle()
        val copiedFailure = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateConversationId(context, stateHandle, copiedId.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateConversation(context, stateHandle, copiedConversation.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateTurnProgress(context, stateHandle, copiedProgress.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationStateFailure(context, stateHandle, copiedFailure.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, state.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, state.ptr))
        assertAggregateString(context, assertNotNull(copiedId.value), "state-conversation", ::codexAgentConversationIdValueCopy)
        assertAggregateCount(
            context,
            assertNotNull(copiedConversation.value),
            1uL,
            ::codexAgentConversationValueMessagesCount,
        )
        assertAggregateString(context, assertNotNull(copiedProgress.value), "turn", ::codexAgentTurnProgressTextCopy)
        assertAggregateString(context, assertNotNull(copiedFailure.value), "recoverable", ::codexAgentFailureCodeCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, copiedId.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationValueDestroy(context, copiedConversation.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, copiedProgress.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, copiedFailure.ptr))

        val truthProgress = createAggregateTurnProgress(context, "truth")
        val recoverableFailure = createAggregateFailure(context, "recoverable", true)
        val cases = listOf(
            StateCase(0, false, false, false, false, false),
            StateCase(1, true, false, false, false, false),
            StateCase(2, true, false, true, true, false),
            StateCase(3, false, false, false, false, true),
            StateCase(4, false, false, false, false, true),
            StateCase(5, true, false, false, false, false),
            StateCase(6, true, false, false, false, false),
            StateCase(7, true, true, true, true, false),
            StateCase(8, true, false, false, false, false),
        )
        cases.forEach { case ->
            val candidate = createAggregateState(
                context,
                case.status,
                if (case.hasId) id.value else null,
                assertNotNull(truthProgress.value),
                if (case.hasFailure) recoverableFailure.value else null,
            )
            val handle = assertNotNull(candidate.value)
            assertAggregateFlag(context, handle, case.canStart.toInt(), ::codexAgentConversationStateCanStartTurn)
            assertAggregateFlag(context, handle, case.canReload.toInt(), ::codexAgentConversationStateCanReload)
            assertAggregateFlag(context, handle, case.canCancel.toInt(), ::codexAgentConversationStateCanCancelTurn)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, candidate.ptr))
        }

        val nonRecoverableFailure = createAggregateFailure(context, "terminal", false)
        val failed = createAggregateState(
            context,
            7,
            assertNotNull(id.value),
            assertNotNull(truthProgress.value),
            assertNotNull(nonRecoverableFailure.value),
        )
        assertAggregateFlag(
            context,
            assertNotNull(failed.value),
            0,
            ::codexAgentConversationStateCanStartTurn,
        )
        assertAggregateFlag(
            context,
            assertNotNull(failed.value),
            1,
            ::codexAgentConversationStateCanReload,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, failed.ptr))

        val absentState = createAggregateState(context, 0, null, assertNotNull(truthProgress.value), null)
        val absentHandle = assertNotNull(absentState.value)
        assertAggregateFlag(context, absentHandle, 0, ::codexAgentConversationStateHasConversationId)
        assertAggregateFlag(context, absentHandle, 0, ::codexAgentConversationStateHasConversation)
        assertAggregateFlag(context, absentHandle, 0, ::codexAgentConversationStateHasModel)
        val absentChild = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentConversationStateConversationId(context, absentHandle, absentChild.ptr),
        )
        assertNull(absentChild.value)
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentConversationStateConversation(context, absentHandle, absentChild.ptr),
        )
        val required = alloc<ULongVar>().also { it.value = 73uL }
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentConversationStateModelCopy(context, absentHandle, null, 0uL, required.ptr),
        )
        assertEquals(73uL, required.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, absentState.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, id.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, truthProgress.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, recoverableFailure.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, nonRecoverableFailure.ptr))
    }

    @Test
    fun rejectsConversationAggregateBoundaryViolationsAndReclaimsSnapshots(): Unit = withAggregateContexts {
        context, otherContext ->
        val absent = aggregateAbsentView()
        val valid = aggregateView("valid")
        val message = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 2, absent, 0, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 0, null, 0uL, null, 0uL, message.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 0, absent, 9, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 0, null, 0uL, null, 0uL, message.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 0, absent, 0, valid.view, 9, 0, absent, 0, absent, 0, absent,
                0, 0, null, 0uL, null, 0uL, message.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, invalidAggregateUtf8(), 0, absent, 0, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 0, null, 0uL, null, 0uL, message.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 0, absent, 0, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 5, null, 0uL, null, 0uL, message.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 0, absent, 0, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 0, null, 1uL, null, 0uL, message.ptr,
            ),
        )
        val invalidCapability = aggregateInts(9)
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageCreate(
                context, valid.view, 0, absent, 0, valid.view, 0, 0, absent, 0, absent, 0, absent,
                0, 0, invalidCapability, 1uL, null, 0uL, message.ptr,
            ),
        )
        assertNull(message.value)

        val invalidRequest = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentTurnRequestCreate(
                context,
                valid.view,
                0,
                absent,
                0,
                absent,
                0,
                absent,
                0,
                absent,
                9,
                null,
                0uL,
                null,
                0uL,
                0,
                invalidRequest.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentTurnRequestCreate(
                context,
                valid.view,
                2,
                absent,
                0,
                absent,
                0,
                absent,
                0,
                absent,
                0,
                null,
                0uL,
                null,
                0uL,
                0,
                invalidRequest.ptr,
            ),
        )
        assertNull(invalidRequest.value)

        val live = createBasicAggregateMessage(context, "live")
        val liveHandle = assertNotNull(live.value)
        val primitive = alloc<IntVar>().also { it.value = 71 }
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentMessageRole(otherContext, liveHandle, primitive.ptr),
        )
        assertEquals(71, primitive.value)
        val summaryId = createAggregateConversationId(context, "wrong-type")
        val summary = createAggregateSummary(context, assertNotNull(summaryId.value), "wrong", 1L)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentMessageRole(context, assertNotNull(summary.value), primitive.ptr),
        )
        assertEquals(71, primitive.value)
        val wrongDestroy = emptyAggregateHandle().also { it.value = summary.value }
        assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, codexAgentMessageDestroy(context, wrongDestroy.ptr))
        assertEquals(summary.value, wrongDestroy.value)

        val occupied = emptyAggregateHandle().also { it.value = context }
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageInvocationAt(context, liveHandle, 0uL, occupied.ptr),
        )
        assertEquals(context, occupied.value)
        val badIndex = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageInvocationAt(context, liveHandle, ULong.MAX_VALUE, badIndex.ptr),
        )
        assertNull(badIndex.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMessageRole(context, liveHandle, null))
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMessageHasCapability(context, liveHandle, 9, primitive.ptr),
        )
        assertEquals(71, primitive.value)

        val stale = liveHandle
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, live.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMessageDestroy(context, live.ptr))
        val required = alloc<ULongVar>().also { it.value = 83uL }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMessageIdCopy(context, stale, null, 0uL, required.ptr),
        )
        assertEquals(83uL, required.value)

        val progress = createAggregateTurnProgress(context, "progress")
        val invalidState = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentConversationStateCreate(
                context, 9, 0, null, 0, null, assertNotNull(progress.value), 0, absent, 0, absent,
                0, absent, 0, null, invalidState.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentConversationStateCreate(
                context, 0, 2, null, 0, null, assertNotNull(progress.value), 0, absent, 0, absent,
                0, absent, 0, null, invalidState.ptr,
            ),
        )
        assertNull(invalidState.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, progress.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, summary.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, summaryId.ptr))

        val teardownContextSlot = emptyAggregateHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(teardownContextSlot.ptr))
        val teardownContext = assertNotNull(teardownContextSlot.value)
        val teardownPlugin = createAggregatePlugin(teardownContext, "teardown", "file:///teardown")
        val teardownInvocation = createAggregateInvocationFromPlugin(
            teardownContext,
            assertNotNull(teardownPlugin.value),
        )
        val teardownMessage = createBasicAggregateMessage(
            teardownContext,
            "teardown-message",
            assertNotNull(teardownInvocation.value),
        )
        val child = emptyAggregateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMessageInvocationAt(
                teardownContext,
                assertNotNull(teardownMessage.value),
                0uL,
                child.ptr,
            ),
        )
        val savedMessage = assertNotNull(teardownMessage.value)
        val savedInvocation = assertNotNull(teardownInvocation.value)
        val savedChild = assertNotNull(child.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(teardownContextSlot.ptr))
        assertNull(teardownContextSlot.value)
        primitive.value = 97
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentInvocationKind(teardownContext, savedChild, primitive.ptr),
        )
        assertEquals(97, primitive.value)
        val savedMessageSlot = emptyAggregateHandle().also { it.value = savedMessage }
        val savedInvocationSlot = emptyAggregateHandle().also { it.value = savedInvocation }
        val savedChildSlot = emptyAggregateHandle().also { it.value = savedChild }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMessageDestroy(teardownContext, savedMessageSlot.ptr),
        )
        assertEquals(savedMessage, savedMessageSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentInvocationDestroy(teardownContext, savedInvocationSlot.ptr),
        )
        assertEquals(savedInvocation, savedInvocationSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentInvocationDestroy(teardownContext, savedChildSlot.ptr),
        )
        assertEquals(savedChild, savedChildSlot.value)
    }
}

private data class AggregateTestView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private data class StateCase(
    val status: Int,
    val hasId: Boolean,
    val hasFailure: Boolean,
    val canStart: Boolean,
    val canReload: Boolean,
    val canCancel: Boolean,
)

private typealias AggregateStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias AggregateIntGetter = (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int

private typealias AggregateCountGetter = (COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?) -> Int

private fun withAggregateContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val context = emptyAggregateHandle()
    val otherContext = emptyAggregateHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(context.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContext.ptr))
    try {
        block(assertNotNull(context.value), assertNotNull(otherContext.value))
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContext.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(context.ptr))
        assertNull(otherContext.value)
        assertNull(context.value)
    }
}

private fun MemScope.emptyAggregateHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.aggregateView(value: String): AggregateTestView {
    val encoded = value.encodeToByteArray()
    val bytes = if (encoded.isEmpty()) null else allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> checkNotNull(bytes)[index] = byte.toUByte() }
    return AggregateTestView(
        alloc<codex_agent_string_view>().also {
            it.data = bytes
            it.size = encoded.size.toULong()
        }.ptr,
        bytes,
    )
}

private fun MemScope.aggregateAbsentView(): CPointer<codex_agent_string_view> = aggregateView("").view

private fun MemScope.invalidAggregateUtf8(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    return alloc<codex_agent_string_view>().also {
        it.data = bytes
        it.size = 2uL
    }.ptr
}

private fun MemScope.aggregateHandles(vararg values: COpaquePointer): CPointer<COpaquePointerVar> =
    allocArray<COpaquePointerVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }

private fun MemScope.aggregateInts(vararg values: Int): CPointer<IntVar> =
    allocArray<IntVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }

private fun MemScope.createAggregatePlugin(
    context: COpaquePointer,
    name: String,
    uri: String,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationPluginCreate(context, aggregateView(name).view, aggregateView(uri).view, it.ptr),
    )
}

private fun MemScope.createAggregateSkill(
    context: COpaquePointer,
    name: String,
    path: String,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationSkillCreate(context, aggregateView(name).view, aggregateView(path).view, it.ptr),
    )
}

private fun MemScope.createAggregateInvocationFromPlugin(
    context: COpaquePointer,
    plugin: COpaquePointer,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationFromPlugin(context, plugin, it.ptr))
}

private fun MemScope.createAggregateInvocationFromSkill(
    context: COpaquePointer,
    skill: COpaquePointer,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationFromSkill(context, skill, it.ptr))
}

private fun MemScope.createBasicAggregateMessage(
    context: COpaquePointer,
    id: String,
    invocation: COpaquePointer? = null,
): COpaquePointerVar = emptyAggregateHandle().also { output ->
    val absent = aggregateAbsentView()
    val invocations = invocation?.let { aggregateHandles(it) }
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMessageCreate(
            context,
            aggregateView(id).view,
            0,
            absent,
            0,
            aggregateView("text-$id").view,
            0,
            0,
            absent,
            0,
            absent,
            0,
            absent,
            0,
            0,
            null,
            0uL,
            invocations,
            if (invocation == null) 0uL else 1uL,
            output.ptr,
        ),
    )
}

private fun MemScope.createAggregateConversationId(context: COpaquePointer, value: String): COpaquePointerVar =
    emptyAggregateHandle().also {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationIdCreate(context, aggregateView(value).view, it.ptr),
        )
    }

private fun MemScope.createAggregateSummary(
    context: COpaquePointer,
    conversationId: COpaquePointer,
    title: String,
    updatedAt: Long,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationSummaryCreate(context, conversationId, aggregateView(title).view, updatedAt, it.ptr),
    )
}

private fun MemScope.createAggregateTurnProgress(context: COpaquePointer, text: String): COpaquePointerVar =
    emptyAggregateHandle().also {
        val empty = aggregateView("").view
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentTurnProgressCreate(
                context,
                aggregateView(text).view,
                empty,
                empty,
                empty,
                0,
                null,
                empty,
                0,
                0,
                0,
                0,
                null,
                0uL,
                0,
                it.ptr,
            ),
        )
    }

private fun MemScope.createAggregateFailure(
    context: COpaquePointer,
    code: String,
    recoverable: Boolean,
): COpaquePointerVar = emptyAggregateHandle().also {
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFailureCreate(
            context,
            aggregateView(code).view,
            aggregateView("message-$code").view,
            recoverable.toInt(),
            it.ptr,
        ),
    )
}

private fun MemScope.createAggregateState(
    context: COpaquePointer,
    status: Int,
    conversationId: COpaquePointer?,
    turnProgress: COpaquePointer,
    failure: COpaquePointer?,
): COpaquePointerVar = emptyAggregateHandle().also {
    val absent = aggregateAbsentView()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationStateCreate(
            context,
            status,
            conversationId.aggregatePresence(),
            conversationId,
            0,
            null,
            turnProgress,
            0,
            absent,
            0,
            absent,
            0,
            absent,
            failure.aggregatePresence(),
            failure,
            it.ptr,
        ),
    )
}

private fun MemScope.assertAggregateString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: AggregateStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(maxOf(1, bytes.size))
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, bytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertAggregateInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: AggregateIntGetter,
) {
    val value = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, value.ptr))
    assertEquals(expected, value.value)
}

private fun MemScope.assertAggregateFlag(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: AggregateIntGetter,
): Unit = assertAggregateInt(context, handle, expected, getter)

private fun MemScope.assertAggregateCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    getter: AggregateCountGetter,
) {
    val value = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, value.ptr))
    assertEquals(expected, value.value)
}

private fun Boolean.toInt(): Int = if (this) 1 else 0

private fun Any?.aggregatePresence(): Int = if (this == null) 0 else 1
