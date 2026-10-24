@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
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

class CodexAgentCProgressListValuesTest {
    @Test
    fun modelCopiesOrderedListsDuplicatesAndNestedServiceTiers() = memScoped {
        val contextSlot = createProgressContext()
        val context = assertNotNull(contextSlot.value)
        val firstTierSlot = emptyProgressHandle()
        val secondTierSlot = emptyProgressHandle()
        val modelSlot = emptyProgressHandle()
        val emptyModelSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentServiceTierCreate(
                context,
                progressView("fast"),
                progressView("Fast"),
                progressView("Low latency"),
                firstTierSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentServiceTierCreate(
                context,
                progressView("flex"),
                progressView("Flex"),
                progressView("Lower cost"),
                secondTierSlot.ptr,
            ),
        )
        val firstTier = assertNotNull(firstTierSlot.value)
        val secondTier = assertNotNull(secondTierSlot.value)
        val mutableId = mutableProgressView("model-id")
        val mutableEffort = mutableProgressView("low")
        val highEffort = progressView("high")
        val efforts = progressStringArray(mutableEffort.value, highEffort, mutableEffort.value)
        val tiers = progressHandleArray(firstTier, secondTier, firstTier)
        val defaultTier = mutableProgressView("fast")
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentModelCreate(
                context,
                mutableId.value,
                progressView("Model"),
                progressView("Description"),
                efforts,
                3UL,
                progressView("medium"),
                1,
                tiers,
                3UL,
                1,
                defaultTier.value,
                modelSlot.ptr,
            ),
        )
        val model = assertNotNull(modelSlot.value)
        mutableId.bytes[0] = 'X'.code.toUByte()
        mutableEffort.bytes[0] = 'X'.code.toUByte()
        defaultTier.bytes[0] = 'X'.code.toUByte()
        tiers[0] = secondTier
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, firstTierSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, secondTierSlot.ptr))

        assertProgressString(context, model, "model-id", ::codexAgentModelIdCopy)
        assertProgressString(context, model, "Model", ::codexAgentModelDisplayNameCopy)
        assertProgressString(context, model, "Description", ::codexAgentModelDescriptionCopy)
        assertProgressString(context, model, "medium", ::codexAgentModelDefaultEffortCopy)
        assertProgressCount(context, model, 3UL, ::codexAgentModelSupportedEffortsCount)
        assertProgressStringAt(context, model, 0UL, "low", ::codexAgentModelSupportedEffortCopyAt)
        assertProgressStringAt(context, model, 1UL, "high", ::codexAgentModelSupportedEffortCopyAt)
        assertProgressStringAt(context, model, 2UL, "low", ::codexAgentModelSupportedEffortCopyAt)
        assertProgressInt(context, model, 1, ::codexAgentModelIsDefault)
        assertProgressCount(context, model, 3UL, ::codexAgentModelServiceTiersCount)
        assertProgressInt(context, model, 1, ::codexAgentModelHasDefaultServiceTier)
        assertProgressString(context, model, "fast", ::codexAgentModelDefaultServiceTierCopy)

        val nestedFirstSlot = emptyProgressHandle()
        val nestedDuplicateSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelServiceTierAt(context, model, 0UL, nestedFirstSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelServiceTierAt(context, model, 2UL, nestedDuplicateSlot.ptr))
        val nestedFirst = assertNotNull(nestedFirstSlot.value)
        val nestedDuplicate = assertNotNull(nestedDuplicateSlot.value)
        assertTrue(nestedFirst != nestedDuplicate)
        assertProgressString(context, nestedFirst, "fast", ::codexAgentServiceTierIdCopy)
        assertProgressString(context, nestedDuplicate, "fast", ::codexAgentServiceTierIdCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, nestedFirstSlot.ptr))
        assertProgressString(context, nestedDuplicate, "fast", ::codexAgentServiceTierIdCopy)

        val absent = progressView("")
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentModelCreate(
                context,
                progressView("empty"),
                progressView("Empty"),
                progressView(""),
                null,
                0UL,
                progressView(""),
                0,
                null,
                0UL,
                0,
                absent,
                emptyModelSlot.ptr,
            ),
        )
        val emptyModel = assertNotNull(emptyModelSlot.value)
        assertProgressCount(context, emptyModel, 0UL, ::codexAgentModelSupportedEffortsCount)
        assertProgressCount(context, emptyModel, 0UL, ::codexAgentModelServiceTiersCount)
        assertProgressInt(context, emptyModel, 0, ::codexAgentModelHasDefaultServiceTier)
        assertProgressAbsentString(context, emptyModel, ::codexAgentModelDefaultServiceTierCopy)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelDestroy(context, modelSlot.ptr))
        assertProgressString(context, nestedDuplicate, "fast", ::codexAgentServiceTierIdCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, nestedDuplicateSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelDestroy(context, emptyModelSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }

    @Test
    fun planProgressCopiesOrderedDuplicateStepsAndOwnsReturnedChildren() = memScoped {
        val contextSlot = createProgressContext()
        val context = assertNotNull(contextSlot.value)
        val firstStepSlot = emptyProgressHandle()
        val secondStepSlot = emptyProgressHandle()
        val progressSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanStepCreate(context, progressView("first"), 0, firstStepSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanStepCreate(context, progressView("second"), 2, secondStepSlot.ptr),
        )
        val firstStep = assertNotNull(firstStepSlot.value)
        val secondStep = assertNotNull(secondStepSlot.value)
        val explanation = mutableProgressView("why")
        val steps = progressHandleArray(firstStep, secondStep, firstStep)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanProgressCreate(context, 1, explanation.value, steps, 3UL, progressSlot.ptr),
        )
        val progress = assertNotNull(progressSlot.value)
        explanation.bytes[0] = 'X'.code.toUByte()
        steps[0] = secondStep
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, firstStepSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, secondStepSlot.ptr))

        assertProgressInt(context, progress, 1, ::codexAgentPlanProgressHasExplanation)
        assertProgressString(context, progress, "why", ::codexAgentPlanProgressExplanationCopy)
        assertProgressCount(context, progress, 3UL, ::codexAgentPlanProgressStepsCount)
        val missingStepSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanProgressStepAt(context, progress, 3UL, missingStepSlot.ptr),
        )
        assertNull(missingStepSlot.value)
        val returnedFirstSlot = emptyProgressHandle()
        val returnedSecondSlot = emptyProgressHandle()
        val returnedDuplicateSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressStepAt(context, progress, 0UL, returnedFirstSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressStepAt(context, progress, 1UL, returnedSecondSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressStepAt(context, progress, 2UL, returnedDuplicateSlot.ptr))
        val returnedFirst = assertNotNull(returnedFirstSlot.value)
        val returnedSecond = assertNotNull(returnedSecondSlot.value)
        val returnedDuplicate = assertNotNull(returnedDuplicateSlot.value)
        assertTrue(returnedFirst != returnedDuplicate)
        assertProgressString(context, returnedFirst, "first", ::codexAgentPlanStepTextCopy)
        assertProgressString(context, returnedSecond, "second", ::codexAgentPlanStepTextCopy)
        assertProgressString(context, returnedDuplicate, "first", ::codexAgentPlanStepTextCopy)
        assertProgressInt(context, returnedFirst, 0, ::codexAgentPlanStepStatus)
        assertProgressInt(context, returnedSecond, 2, ::codexAgentPlanStepStatus)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, returnedFirstSlot.ptr))
        assertProgressString(context, returnedDuplicate, "first", ::codexAgentPlanStepTextCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressDestroy(context, progressSlot.ptr))
        assertProgressString(context, returnedSecond, "second", ::codexAgentPlanStepTextCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, returnedSecondSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, returnedDuplicateSlot.ptr))

        val emptySlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanProgressCreate(context, 0, progressView(""), null, 0UL, emptySlot.ptr),
        )
        val empty = assertNotNull(emptySlot.value)
        assertProgressInt(context, empty, 0, ::codexAgentPlanProgressHasExplanation)
        assertProgressAbsentString(context, empty, ::codexAgentPlanProgressExplanationCopy)
        assertProgressCount(context, empty, 0UL, ::codexAgentPlanProgressStepsCount)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressDestroy(context, emptySlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }

    @Test
    fun hookActivityProjectsEveryStatusNullableMessageAndCopiedDetails() = memScoped {
        val contextSlot = createProgressContext()
        val context = assertNotNull(contextSlot.value)
        val statusValues = listOf(0, 1, 2, 3, 4)
        statusValues.forEachIndexed { index, status ->
            val activitySlot = emptyProgressHandle()
            val mutableId = mutableProgressView("hook-$index")
            val mutableDetail = mutableProgressView("detail-$index")
            val details = progressStringArray(mutableDetail.value, progressView("shared"), mutableDetail.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHookActivityCreate(
                    context,
                    mutableId.value,
                    progressView("event"),
                    progressView("command"),
                    status,
                    1,
                    progressView("message"),
                    details,
                    3UL,
                    activitySlot.ptr,
                ),
            )
            val activity = assertNotNull(activitySlot.value)
            mutableId.bytes[0] = 'X'.code.toUByte()
            mutableDetail.bytes[0] = 'X'.code.toUByte()
            setProgressString(details, 0, progressView("changed"))
            assertProgressString(context, activity, "hook-$index", ::codexAgentHookActivityIdCopy)
            assertProgressString(context, activity, "event", ::codexAgentHookActivityEventNameCopy)
            assertProgressString(context, activity, "command", ::codexAgentHookActivityHandlerTypeCopy)
            assertProgressInt(context, activity, status, ::codexAgentHookActivityStatus)
            assertProgressInt(context, activity, 1, ::codexAgentHookActivityHasStatusMessage)
            assertProgressString(context, activity, "message", ::codexAgentHookActivityStatusMessageCopy)
            assertProgressCount(context, activity, 3UL, ::codexAgentHookActivityDetailsCount)
            assertProgressStringAt(context, activity, 0UL, "detail-$index", ::codexAgentHookActivityDetailCopyAt)
            assertProgressStringAt(context, activity, 1UL, "shared", ::codexAgentHookActivityDetailCopyAt)
            assertProgressStringAt(context, activity, 2UL, "detail-$index", ::codexAgentHookActivityDetailCopyAt)
            val untouched = alloc<ULongVar>().also { it.value = 89UL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHookActivityDetailCopyAt(context, activity, 3UL, null, 0UL, untouched.ptr),
            )
            assertEquals(89UL, untouched.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookActivityDestroy(context, activitySlot.ptr))
        }

        val emptySlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookActivityCreate(
                context,
                progressView("empty"),
                progressView("event"),
                progressView("prompt"),
                0,
                0,
                progressView(""),
                null,
                0UL,
                emptySlot.ptr,
            ),
        )
        val empty = assertNotNull(emptySlot.value)
        assertProgressInt(context, empty, 0, ::codexAgentHookActivityHasStatusMessage)
        assertProgressAbsentString(context, empty, ::codexAgentHookActivityStatusMessageCopy)
        assertProgressCount(context, empty, 0UL, ::codexAgentHookActivityDetailsCount)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookActivityDestroy(context, emptySlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }

    @Test
    fun turnProgressOwnsNestedProgressHooksAndProjectsNullability() = memScoped {
        val contextSlot = createProgressContext()
        val context = assertNotNull(contextSlot.value)
        val stepSlot = emptyProgressHandle()
        val planSlot = emptyProgressHandle()
        val hookSlot = emptyProgressHandle()
        val turnSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepCreate(context, progressView("step"), 1, stepSlot.ptr))
        val step = assertNotNull(stepSlot.value)
        val steps = progressHandleArray(step)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanProgressCreate(context, 1, progressView("explain"), steps, 1UL, planSlot.ptr),
        )
        val planProgress = assertNotNull(planSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookActivityCreate(
                context,
                progressView("hook"),
                progressView("event"),
                progressView("agent"),
                3,
                1,
                progressView("blocked"),
                progressStringArray(progressView("detail")),
                1UL,
                hookSlot.ptr,
            ),
        )
        val hook = assertNotNull(hookSlot.value)
        val mutableText = mutableProgressView("text")
        val hooks = progressHandleArray(hook, hook)
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentTurnProgressCreate(
                context,
                mutableText.value,
                progressView("commentary"),
                progressView("reasoning"),
                progressView("plan"),
                1,
                planProgress,
                progressView("shell"),
                1,
                -7,
                1,
                1,
                hooks,
                2UL,
                1,
                turnSlot.ptr,
            ),
        )
        val turn = assertNotNull(turnSlot.value)
        mutableText.bytes[0] = 'X'.code.toUByte()
        hooks[0] = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressDestroy(context, planSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookActivityDestroy(context, hookSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, stepSlot.ptr))

        assertProgressString(context, turn, "text", ::codexAgentTurnProgressTextCopy)
        assertProgressString(context, turn, "commentary", ::codexAgentTurnProgressCommentaryCopy)
        assertProgressString(context, turn, "reasoning", ::codexAgentTurnProgressReasoningCopy)
        assertProgressString(context, turn, "plan", ::codexAgentTurnProgressPlanCopy)
        assertProgressString(context, turn, "shell", ::codexAgentTurnProgressShellOutputCopy)
        assertProgressInt(context, turn, 1, ::codexAgentTurnProgressHasPlanProgress)
        assertProgressNullableInt(context, turn, 1, -7, ::codexAgentTurnProgressShellExitCode)
        assertProgressNullableInt(context, turn, 1, 1, ::codexAgentTurnProgressWorkActivity)
        assertProgressCount(context, turn, 2UL, ::codexAgentTurnProgressHookActivitiesCount)
        assertProgressInt(context, turn, 1, ::codexAgentTurnProgressIsTruncated)
        val missingHookSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentTurnProgressHookActivityAt(context, turn, 2UL, missingHookSlot.ptr),
        )
        assertNull(missingHookSlot.value)

        val firstPlanSlot = emptyProgressHandle()
        val secondPlanSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressPlanProgress(context, turn, firstPlanSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressPlanProgress(context, turn, secondPlanSlot.ptr))
        val firstPlan = assertNotNull(firstPlanSlot.value)
        val secondPlan = assertNotNull(secondPlanSlot.value)
        assertTrue(firstPlan != secondPlan)
        assertProgressString(context, firstPlan, "explain", ::codexAgentPlanProgressExplanationCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressDestroy(context, firstPlanSlot.ptr))
        assertProgressString(context, secondPlan, "explain", ::codexAgentPlanProgressExplanationCopy)

        val firstHookSlot = emptyProgressHandle()
        val duplicateHookSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressHookActivityAt(context, turn, 0UL, firstHookSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressHookActivityAt(context, turn, 1UL, duplicateHookSlot.ptr))
        val firstHook = assertNotNull(firstHookSlot.value)
        val duplicateHook = assertNotNull(duplicateHookSlot.value)
        assertTrue(firstHook != duplicateHook)
        assertProgressString(context, firstHook, "hook", ::codexAgentHookActivityIdCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookActivityDestroy(context, firstHookSlot.ptr))
        assertProgressString(context, duplicateHook, "hook", ::codexAgentHookActivityIdCopy)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, turnSlot.ptr))
        assertProgressString(context, secondPlan, "explain", ::codexAgentPlanProgressExplanationCopy)
        assertProgressString(context, duplicateHook, "hook", ::codexAgentHookActivityIdCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanProgressDestroy(context, secondPlanSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookActivityDestroy(context, duplicateHookSlot.ptr))

        val emptyTurnSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentTurnProgressCreate(
                context,
                progressView(""),
                progressView(""),
                progressView(""),
                progressView(""),
                0,
                null,
                progressView(""),
                0,
                0,
                0,
                0,
                null,
                0UL,
                0,
                emptyTurnSlot.ptr,
            ),
        )
        val emptyTurn = assertNotNull(emptyTurnSlot.value)
        assertProgressInt(context, emptyTurn, 0, ::codexAgentTurnProgressHasPlanProgress)
        val absentPlanSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_NOT_READY,
            codexAgentTurnProgressPlanProgress(context, emptyTurn, absentPlanSlot.ptr),
        )
        assertNull(absentPlanSlot.value)
        assertProgressNullableInt(context, emptyTurn, 0, 0, ::codexAgentTurnProgressShellExitCode)
        assertProgressNullableInt(context, emptyTurn, 0, 0, ::codexAgentTurnProgressWorkActivity)
        assertProgressCount(context, emptyTurn, 0UL, ::codexAgentTurnProgressHookActivitiesCount)
        assertProgressInt(context, emptyTurn, 0, ::codexAgentTurnProgressIsTruncated)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, emptyTurnSlot.ptr))

        val runningTurnSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            createBareTurn(context, hasWork = 1, work = 0, out = runningTurnSlot.ptr),
        )
        val runningTurn = assertNotNull(runningTurnSlot.value)
        assertProgressNullableInt(context, runningTurn, 1, 0, ::codexAgentTurnProgressWorkActivity)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentTurnProgressDestroy(context, runningTurnSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }

    @Test
    fun collectionInputsBoundsOutputsContextsTypesAndDestructionFailClosed() = memScoped {
        val contextSlot = createProgressContext()
        val otherContextSlot = createProgressContext()
        val context = assertNotNull(contextSlot.value)
        val otherContext = assertNotNull(otherContextSlot.value)
        val empty = progressView("")
        val invalidModelSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentModelCreate(
                context,
                progressView("id"),
                progressView("name"),
                empty,
                null,
                1UL,
                empty,
                0,
                null,
                0UL,
                0,
                empty,
                invalidModelSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentModelCreate(
                context,
                progressView("id"),
                progressView("name"),
                empty,
                null,
                0UL,
                empty,
                2,
                null,
                0UL,
                0,
                empty,
                invalidModelSlot.ptr,
            ),
        )
        assertNull(invalidModelSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentModelCreate(
                context,
                progressView("id"),
                progressView("name"),
                empty,
                null,
                0UL,
                empty,
                0,
                null,
                1UL,
                0,
                empty,
                invalidModelSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentModelCreate(
                context,
                progressView("id"),
                progressView("name"),
                empty,
                null,
                0UL,
                empty,
                0,
                null,
                0UL,
                0,
                progressView("contradiction"),
                invalidModelSlot.ptr,
            ),
        )

        val stepSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepCreate(context, progressView("step"), 0, stepSlot.ptr))
        val step = assertNotNull(stepSlot.value)
        val invalidPlanSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanProgressCreate(context, 0, progressView("contradiction"), null, 0UL, invalidPlanSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanProgressCreate(context, 0, empty, null, 1UL, invalidPlanSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentPlanProgressCreate(context, 2, empty, null, 0UL, invalidPlanSlot.ptr),
        )

        val invalidHookSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookActivityCreate(
                context,
                progressView("id"),
                progressView("event"),
                progressView("handler"),
                5,
                0,
                empty,
                null,
                0UL,
                invalidHookSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookActivityCreate(
                context,
                progressView("id"),
                progressView("event"),
                progressView("handler"),
                0,
                2,
                empty,
                null,
                0UL,
                invalidHookSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookActivityCreate(
                context,
                progressView("id"),
                progressView("event"),
                progressView("handler"),
                0,
                0,
                progressView("contradiction"),
                null,
                0UL,
                invalidHookSlot.ptr,
            ),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookActivityCreate(
                context,
                progressView("id"),
                progressView("event"),
                progressView("handler"),
                0,
                0,
                empty,
                null,
                1UL,
                invalidHookSlot.ptr,
            ),
        )

        val invalidTurnSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hasPlan = 0, plan = step, out = invalidTurnSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hasPlan = 2, out = invalidTurnSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hasExit = 0, exit = 7, out = invalidTurnSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hasWork = 0, work = 1, out = invalidTurnSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hasWork = 1, work = 2, out = invalidTurnSlot.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            createBareTurn(context, hooks = null, hookCount = 1UL, out = invalidTurnSlot.ptr),
        )
        assertNull(invalidTurnSlot.value)

        val modelSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentModelCreate(
                context,
                progressView("id"),
                progressView("name"),
                empty,
                null,
                0UL,
                empty,
                0,
                null,
                0UL,
                0,
                empty,
                modelSlot.ptr,
            ),
        )
        val model = assertNotNull(modelSlot.value)
        val count = alloc<ULongVar>().also { it.value = 73UL }
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentModelSupportedEffortsCount(otherContext, model, count.ptr),
        )
        assertEquals(73UL, count.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentModelSupportedEffortsCount(context, step, count.ptr),
        )
        assertEquals(73UL, count.value)
        val childSlot = emptyProgressHandle()
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentModelServiceTierAt(context, model, 0UL, childSlot.ptr))
        assertNull(childSlot.value)
        val required = alloc<ULongVar>().also { it.value = 91UL }
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentModelSupportedEffortCopyAt(context, model, ULong.MAX_VALUE, null, 0UL, required.ptr),
        )
        assertEquals(91UL, required.value)

        val wrongDestroy = alloc<COpaquePointerVar>().also { it.value = step }
        assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, codexAgentModelDestroy(context, wrongDestroy.ptr))
        assertEquals(step, wrongDestroy.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelDestroy(context, modelSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentModelDestroy(context, modelSlot.ptr))
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentModelIdCopy(context, model, null, 0UL, required.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPlanStepDestroy(context, stepSlot.ptr))
        val reclaimedSlot = emptyProgressHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentPlanProgressCreate(otherContext, 0, empty, null, 0UL, reclaimedSlot.ptr),
        )
        val reclaimed = assertNotNull(reclaimedSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        count.value = 67UL
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentPlanProgressStepsCount(otherContext, reclaimed, count.ptr),
        )
        assertEquals(67UL, count.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.createProgressContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyProgressHandle(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.progressView(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = value.encodeToByteArray()
        view.size = bytes.size.toULong()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
    }.ptr

private fun MemScope.mutableProgressView(value: String): ProgressMutableStringView {
    val bytes = value.encodeToByteArray()
    require(bytes.isNotEmpty())
    val buffer = allocArray<UByteVar>(bytes.size)
    bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    return ProgressMutableStringView(
        value = alloc<codex_agent_string_view>().also { view ->
            view.data = buffer
            view.size = bytes.size.toULong()
        }.ptr,
        bytes = buffer,
    )
}

private fun MemScope.progressStringArray(
    vararg values: CPointer<codex_agent_string_view>,
): CPointer<codex_agent_string_view> = allocArray<codex_agent_string_view>(values.size).also { array ->
    values.forEachIndexed { index, value -> setProgressString(array, index, value) }
}

private fun setProgressString(
    array: CPointer<codex_agent_string_view>,
    index: Int,
    value: CPointer<codex_agent_string_view>,
) {
    array[index].data = value.pointed.data
    array[index].size = value.pointed.size
}

private fun MemScope.progressHandleArray(vararg values: COpaquePointer?): CPointer<COpaquePointerVar> =
    allocArray<COpaquePointerVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }

private fun MemScope.assertProgressString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: ProgressStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0UL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size.coerceAtLeast(1))
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, bytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertProgressStringAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    copy: ProgressStringCopyAt,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, index, null, 0UL, required.ptr))
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size)
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, index, buffer, bytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertProgressAbsentString(
    context: COpaquePointer,
    handle: COpaquePointer,
    copy: ProgressStringCopy,
) {
    val required = alloc<ULongVar>().also { it.value = 73UL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, copy(context, handle, null, 0UL, required.ptr))
    assertEquals(73UL, required.value)
}

private fun MemScope.assertProgressCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    getter: ProgressCountGetter,
) {
    val actual = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, actual.ptr))
    assertEquals(expected, actual.value)
}

private fun MemScope.assertProgressInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: ProgressIntGetter,
) {
    val actual = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, actual.ptr))
    assertEquals(expected, actual.value)
}

private fun MemScope.assertProgressNullableInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHas: Int,
    expectedValue: Int,
    getter: ProgressNullableIntGetter,
) {
    val has = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    val value = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, has.ptr, value.ptr))
    assertEquals(expectedHas, has.value)
    assertEquals(expectedValue, value.value)
}

private fun MemScope.createBareTurn(
    context: COpaquePointer,
    hasPlan: Int = 0,
    plan: COpaquePointer? = null,
    hasExit: Int = 0,
    exit: Int = 0,
    hasWork: Int = 0,
    work: Int = 0,
    hooks: CPointer<COpaquePointerVar>? = null,
    hookCount: ULong = 0UL,
    out: CPointer<COpaquePointerVar>,
): Int {
    val empty = progressView("")
    return codexAgentTurnProgressCreate(
        context,
        empty,
        empty,
        empty,
        empty,
        hasPlan,
        plan,
        empty,
        hasExit,
        exit,
        hasWork,
        work,
        hooks,
        hookCount,
        0,
        out,
    )
}

private typealias ProgressStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias ProgressStringCopyAt = (
    COpaquePointer?, COpaquePointer?, ULong, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias ProgressCountGetter = (COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?) -> Int
private typealias ProgressIntGetter = (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int
private typealias ProgressNullableIntGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<IntVar>?,
) -> Int

private data class ProgressMutableStringView(
    val value: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>,
)
