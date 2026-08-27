@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentHookActivity
import io.github.codex_agent_labs.codexmobile.agent.AgentHookRunStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentModel
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentPlanStep
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentWorkActivity
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCModelSnapshot(
    val value: AgentModel,
) : CodexAgentCSnapshot

internal data class CodexAgentCPlanProgressSnapshot(
    val value: AgentPlanProgress,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookActivitySnapshot(
    val value: AgentHookActivity,
) : CodexAgentCSnapshot

internal data class CodexAgentCTurnProgressSnapshot(
    val value: AgentTurnProgress,
) : CodexAgentCSnapshot

@CName("codex_agent_model_create")
public fun codexAgentModelCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    displayName: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    supportedEfforts: CPointer<codex_agent_string_view>?,
    supportedEffortCount: ULong,
    defaultEffort: CPointer<codex_agent_string_view>?,
    isDefault: Int,
    serviceTiers: CPointer<COpaquePointerVar>?,
    serviceTierCount: ULong,
    hasDefaultServiceTier: Int,
    defaultServiceTier: CPointer<codex_agent_string_view>?,
    outModel: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outModel)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(isDefault)
    requireBooleanFlag(hasDefaultServiceTier)
    val copiedEfforts = copyStringViews(supportedEfforts, supportedEffortCount)
    val copiedTiers = mutableListOf<AgentServiceTier>()
    val tierStatus = copyServiceTiers(contextPointer, serviceTiers, serviceTierCount, copiedTiers)
    if (tierStatus != CODEX_AGENT_STATUS_OK) return@abiStatus tierStatus
    val value = AgentModel(
        id = id.readRequiredUtf8(),
        displayName = displayName.readRequiredUtf8(),
        description = description.readRequiredUtf8(),
        supportedEfforts = copiedEfforts,
        defaultEffort = defaultEffort.readRequiredUtf8(),
        isDefault = isDefault == 1,
        serviceTiers = copiedTiers,
        defaultServiceTier = defaultServiceTier.readOptionalUtf8(hasDefaultServiceTier),
    )
    installOutput(outModel, createSnapshot(contextPointer, CodexAgentCModelSnapshot(value)))
}

@CName("codex_agent_model_destroy")
public fun codexAgentModelDestroy(
    context: COpaquePointer?,
    model: CPointer<COpaquePointerVar>?,
): Int = destroyProgressValue<CodexAgentCModelSnapshot>(context, model)

@CName("codex_agent_model_id_copy")
public fun codexAgentModelIdCopy(
    context: COpaquePointer?,
    model: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCModelSnapshot>(context, model, buffer, capacity, outRequired) { it.value.id }

@CName("codex_agent_model_display_name_copy")
public fun codexAgentModelDisplayNameCopy(
    context: COpaquePointer?,
    model: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCModelSnapshot>(context, model, buffer, capacity, outRequired) {
    it.value.displayName
}

@CName("codex_agent_model_description_copy")
public fun codexAgentModelDescriptionCopy(
    context: COpaquePointer?,
    model: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCModelSnapshot>(context, model, buffer, capacity, outRequired) {
    it.value.description
}

@CName("codex_agent_model_supported_efforts_count")
public fun codexAgentModelSupportedEffortsCount(
    context: COpaquePointer?,
    model: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = progressCount<CodexAgentCModelSnapshot>(context, model, outCount) { it.value.supportedEfforts.size }

@CName("codex_agent_model_supported_effort_copy_at")
public fun codexAgentModelSupportedEffortCopyAt(
    context: COpaquePointer?,
    model: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressStringAt<CodexAgentCModelSnapshot>(context, model, index, buffer, capacity, outRequired) {
    it.value.supportedEfforts
}

@CName("codex_agent_model_default_effort_copy")
public fun codexAgentModelDefaultEffortCopy(
    context: COpaquePointer?,
    model: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCModelSnapshot>(context, model, buffer, capacity, outRequired) {
    it.value.defaultEffort
}

@CName("codex_agent_model_is_default")
public fun codexAgentModelIsDefault(
    context: COpaquePointer?,
    model: COpaquePointer?,
    outIsDefault: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCModelSnapshot>(context, model, outIsDefault) { if (it.value.isDefault) 1 else 0 }

@CName("codex_agent_model_service_tiers_count")
public fun codexAgentModelServiceTiersCount(
    context: COpaquePointer?,
    model: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = progressCount<CodexAgentCModelSnapshot>(context, model, outCount) { it.value.serviceTiers.size }

@CName("codex_agent_model_service_tier_at")
public fun codexAgentModelServiceTierAt(
    context: COpaquePointer?,
    model: COpaquePointer?,
    index: ULong,
    outTier: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTier)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCModelSnapshot>(contextPointer, model, CodexAgentCHandleKind.SNAPSHOT) {
        val tier = it.value.serviceTiers.itemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(outTier, createSnapshot(contextPointer, CodexAgentCServiceTierSnapshot(tier.copy())))
    }
}

@CName("codex_agent_model_has_default_service_tier")
public fun codexAgentModelHasDefaultServiceTier(
    context: COpaquePointer?,
    model: COpaquePointer?,
    outHasDefaultServiceTier: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCModelSnapshot>(context, model, outHasDefaultServiceTier) {
    if (it.value.defaultServiceTier == null) 0 else 1
}

@CName("codex_agent_model_default_service_tier_copy")
public fun codexAgentModelDefaultServiceTierCopy(
    context: COpaquePointer?,
    model: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalProgressString<CodexAgentCModelSnapshot>(context, model, buffer, capacity, outRequired) {
    it.value.defaultServiceTier
}

@CName("codex_agent_plan_progress_create")
public fun codexAgentPlanProgressCreate(
    context: COpaquePointer?,
    hasExplanation: Int,
    explanation: CPointer<codex_agent_string_view>?,
    steps: CPointer<COpaquePointerVar>?,
    stepCount: ULong,
    outProgress: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outProgress)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(hasExplanation)
    val copiedSteps = mutableListOf<AgentPlanStep>()
    val stepStatus = copyPlanSteps(contextPointer, steps, stepCount, copiedSteps)
    if (stepStatus != CODEX_AGENT_STATUS_OK) return@abiStatus stepStatus
    val value = AgentPlanProgress(
        explanation = explanation.readOptionalUtf8(hasExplanation),
        steps = copiedSteps,
    )
    installOutput(outProgress, createSnapshot(contextPointer, CodexAgentCPlanProgressSnapshot(value)))
}

@CName("codex_agent_plan_progress_destroy")
public fun codexAgentPlanProgressDestroy(
    context: COpaquePointer?,
    progress: CPointer<COpaquePointerVar>?,
): Int = destroyProgressValue<CodexAgentCPlanProgressSnapshot>(context, progress)

@CName("codex_agent_plan_progress_has_explanation")
public fun codexAgentPlanProgressHasExplanation(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outHasExplanation: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCPlanProgressSnapshot>(context, progress, outHasExplanation) {
    if (it.value.explanation == null) 0 else 1
}

@CName("codex_agent_plan_progress_explanation_copy")
public fun codexAgentPlanProgressExplanationCopy(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalProgressString<CodexAgentCPlanProgressSnapshot>(
    context,
    progress,
    buffer,
    capacity,
    outRequired,
) { it.value.explanation }

@CName("codex_agent_plan_progress_steps_count")
public fun codexAgentPlanProgressStepsCount(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = progressCount<CodexAgentCPlanProgressSnapshot>(context, progress, outCount) { it.value.steps.size }

@CName("codex_agent_plan_progress_step_at")
public fun codexAgentPlanProgressStepAt(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    index: ULong,
    outStep: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outStep)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPlanProgressSnapshot>(contextPointer, progress, CodexAgentCHandleKind.SNAPSHOT) {
        val step = it.value.steps.itemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(outStep, createSnapshot(contextPointer, CodexAgentCPlanStepSnapshot(step.copy())))
    }
}

@CName("codex_agent_hook_activity_create")
public fun codexAgentHookActivityCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    eventName: CPointer<codex_agent_string_view>?,
    handlerType: CPointer<codex_agent_string_view>?,
    status: Int,
    hasStatusMessage: Int,
    statusMessage: CPointer<codex_agent_string_view>?,
    details: CPointer<codex_agent_string_view>?,
    detailCount: ULong,
    outActivity: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outActivity)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(hasStatusMessage)
    val value = AgentHookActivity(
        id = id.readRequiredUtf8(),
        eventName = eventName.readRequiredUtf8(),
        handlerType = handlerType.readRequiredUtf8(),
        status = hookRunStatusFromC(status),
        statusMessage = statusMessage.readOptionalUtf8(hasStatusMessage),
        details = copyStringViews(details, detailCount),
    )
    installOutput(outActivity, createSnapshot(contextPointer, CodexAgentCHookActivitySnapshot(value)))
}

@CName("codex_agent_hook_activity_destroy")
public fun codexAgentHookActivityDestroy(
    context: COpaquePointer?,
    activity: CPointer<COpaquePointerVar>?,
): Int = destroyProgressValue<CodexAgentCHookActivitySnapshot>(context, activity)

@CName("codex_agent_hook_activity_id_copy")
public fun codexAgentHookActivityIdCopy(
    context: COpaquePointer?, activity: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCHookActivitySnapshot>(context, activity, buffer, capacity, outRequired) {
    it.value.id
}

@CName("codex_agent_hook_activity_event_name_copy")
public fun codexAgentHookActivityEventNameCopy(
    context: COpaquePointer?, activity: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCHookActivitySnapshot>(context, activity, buffer, capacity, outRequired) {
    it.value.eventName
}

@CName("codex_agent_hook_activity_handler_type_copy")
public fun codexAgentHookActivityHandlerTypeCopy(
    context: COpaquePointer?, activity: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCHookActivitySnapshot>(context, activity, buffer, capacity, outRequired) {
    it.value.handlerType
}

@CName("codex_agent_hook_activity_status")
public fun codexAgentHookActivityStatus(
    context: COpaquePointer?,
    activity: COpaquePointer?,
    outStatus: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCHookActivitySnapshot>(context, activity, outStatus) { hookRunStatusToC(it.value.status) }

@CName("codex_agent_hook_activity_has_status_message")
public fun codexAgentHookActivityHasStatusMessage(
    context: COpaquePointer?,
    activity: COpaquePointer?,
    outHasStatusMessage: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCHookActivitySnapshot>(context, activity, outHasStatusMessage) {
    if (it.value.statusMessage == null) 0 else 1
}

@CName("codex_agent_hook_activity_status_message_copy")
public fun codexAgentHookActivityStatusMessageCopy(
    context: COpaquePointer?, activity: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalProgressString<CodexAgentCHookActivitySnapshot>(
    context,
    activity,
    buffer,
    capacity,
    outRequired,
) { it.value.statusMessage }

@CName("codex_agent_hook_activity_details_count")
public fun codexAgentHookActivityDetailsCount(
    context: COpaquePointer?,
    activity: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = progressCount<CodexAgentCHookActivitySnapshot>(context, activity, outCount) { it.value.details.size }

@CName("codex_agent_hook_activity_detail_copy_at")
public fun codexAgentHookActivityDetailCopyAt(
    context: COpaquePointer?, activity: COpaquePointer?, index: ULong, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressStringAt<CodexAgentCHookActivitySnapshot>(context, activity, index, buffer, capacity, outRequired) {
    it.value.details
}

@CName("codex_agent_turn_progress_create")
public fun codexAgentTurnProgressCreate(
    context: COpaquePointer?,
    text: CPointer<codex_agent_string_view>?,
    commentary: CPointer<codex_agent_string_view>?,
    reasoning: CPointer<codex_agent_string_view>?,
    plan: CPointer<codex_agent_string_view>?,
    hasPlanProgress: Int,
    planProgress: COpaquePointer?,
    shellOutput: CPointer<codex_agent_string_view>?,
    hasShellExitCode: Int,
    shellExitCode: Int,
    hasWorkActivity: Int,
    workActivity: Int,
    hookActivities: CPointer<COpaquePointerVar>?,
    hookActivityCount: ULong,
    isTruncated: Int,
    outProgress: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outProgress)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(hasPlanProgress)
    requireBooleanFlag(hasShellExitCode)
    requireBooleanFlag(hasWorkActivity)
    requireBooleanFlag(isTruncated)
    if (hasPlanProgress == 0) require(planProgress == null)
    if (hasShellExitCode == 0) require(shellExitCode == 0)
    if (hasWorkActivity == 0) require(workActivity == 0)
    val copiedPlan = mutableListOf<AgentPlanProgress>()
    if (hasPlanProgress == 1) {
        val status = withPayload<CodexAgentCPlanProgressSnapshot>(
            contextPointer,
            planProgress,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedPlan += it.value.deepCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
    }
    val copiedHooks = mutableListOf<AgentHookActivity>()
    val hookStatus = copyHookActivities(contextPointer, hookActivities, hookActivityCount, copiedHooks)
    if (hookStatus != CODEX_AGENT_STATUS_OK) return@abiStatus hookStatus
    val value = AgentTurnProgress(
        text = text.readRequiredUtf8(),
        commentary = commentary.readRequiredUtf8(),
        reasoning = reasoning.readRequiredUtf8(),
        plan = plan.readRequiredUtf8(),
        planProgress = copiedPlan.singleOrNull(),
        shellOutput = shellOutput.readRequiredUtf8(),
        shellExitCode = if (hasShellExitCode == 1) shellExitCode else null,
        workActivity = if (hasWorkActivity == 1) workActivityFromC(workActivity) else null,
        hookActivities = copiedHooks,
        isTruncated = isTruncated == 1,
    )
    installOutput(outProgress, createSnapshot(contextPointer, CodexAgentCTurnProgressSnapshot(value)))
}

@CName("codex_agent_turn_progress_destroy")
public fun codexAgentTurnProgressDestroy(
    context: COpaquePointer?,
    progress: CPointer<COpaquePointerVar>?,
): Int = destroyProgressValue<CodexAgentCTurnProgressSnapshot>(context, progress)

@CName("codex_agent_turn_progress_text_copy")
public fun codexAgentTurnProgressTextCopy(
    context: COpaquePointer?, progress: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCTurnProgressSnapshot>(context, progress, buffer, capacity, outRequired) {
    it.value.text
}

@CName("codex_agent_turn_progress_commentary_copy")
public fun codexAgentTurnProgressCommentaryCopy(
    context: COpaquePointer?, progress: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCTurnProgressSnapshot>(context, progress, buffer, capacity, outRequired) {
    it.value.commentary
}

@CName("codex_agent_turn_progress_reasoning_copy")
public fun codexAgentTurnProgressReasoningCopy(
    context: COpaquePointer?, progress: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCTurnProgressSnapshot>(context, progress, buffer, capacity, outRequired) {
    it.value.reasoning
}

@CName("codex_agent_turn_progress_plan_copy")
public fun codexAgentTurnProgressPlanCopy(
    context: COpaquePointer?, progress: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCTurnProgressSnapshot>(context, progress, buffer, capacity, outRequired) {
    it.value.plan
}

@CName("codex_agent_turn_progress_has_plan_progress")
public fun codexAgentTurnProgressHasPlanProgress(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outHasPlanProgress: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCTurnProgressSnapshot>(context, progress, outHasPlanProgress) {
    if (it.value.planProgress == null) 0 else 1
}

@CName("codex_agent_turn_progress_plan_progress")
public fun codexAgentTurnProgressPlanProgress(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outPlanProgress: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outPlanProgress)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCTurnProgressSnapshot>(contextPointer, progress, CodexAgentCHandleKind.SNAPSHOT) {
        val nested = it.value.planProgress ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outPlanProgress,
            createSnapshot(contextPointer, CodexAgentCPlanProgressSnapshot(nested.deepCopy())),
        )
    }
}

@CName("codex_agent_turn_progress_shell_output_copy")
public fun codexAgentTurnProgressShellOutputCopy(
    context: COpaquePointer?, progress: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyProgressString<CodexAgentCTurnProgressSnapshot>(context, progress, buffer, capacity, outRequired) {
    it.value.shellOutput
}

@CName("codex_agent_turn_progress_shell_exit_code")
public fun codexAgentTurnProgressShellExitCode(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outHasShellExitCode: CPointer<IntVar>?,
    outShellExitCode: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasShellExitCode == null || outShellExitCode == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCTurnProgressSnapshot>(context, progress, CodexAgentCHandleKind.SNAPSHOT) {
        val value = it.value.shellExitCode
        outHasShellExitCode.pointed.value = if (value == null) 0 else 1
        outShellExitCode.pointed.value = value ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_turn_progress_work_activity")
public fun codexAgentTurnProgressWorkActivity(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outHasWorkActivity: CPointer<IntVar>?,
    outWorkActivity: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasWorkActivity == null || outWorkActivity == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCTurnProgressSnapshot>(context, progress, CodexAgentCHandleKind.SNAPSHOT) {
        val value = it.value.workActivity
        outHasWorkActivity.pointed.value = if (value == null) 0 else 1
        outWorkActivity.pointed.value = if (value == null) 0 else workActivityToC(value)
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_turn_progress_hook_activities_count")
public fun codexAgentTurnProgressHookActivitiesCount(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = progressCount<CodexAgentCTurnProgressSnapshot>(context, progress, outCount) { it.value.hookActivities.size }

@CName("codex_agent_turn_progress_hook_activity_at")
public fun codexAgentTurnProgressHookActivityAt(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    index: ULong,
    outActivity: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outActivity)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCTurnProgressSnapshot>(contextPointer, progress, CodexAgentCHandleKind.SNAPSHOT) {
        val activity = it.value.hookActivities.itemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outActivity,
            createSnapshot(contextPointer, CodexAgentCHookActivitySnapshot(activity.deepCopy())),
        )
    }
}

@CName("codex_agent_turn_progress_is_truncated")
public fun codexAgentTurnProgressIsTruncated(
    context: COpaquePointer?,
    progress: COpaquePointer?,
    outIsTruncated: CPointer<IntVar>?,
): Int = progressInt<CodexAgentCTurnProgressSnapshot>(context, progress, outIsTruncated) {
    if (it.value.isTruncated) 1 else 0
}

private fun requireBooleanFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readOptionalUtf8(hasValue: Int): String? {
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0UL)
        return null
    }
    return view.readUtf8()
}

private fun copyStringViews(
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): List<String> {
    require(count <= Int.MAX_VALUE.toULong())
    if (count == 0UL) return emptyList()
    val pointer = requireNotNull(values)
    return List(count.toInt()) { index -> pointer[index].readUtf8() }
}

private fun copyServiceTiers(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentServiceTier>,
): Int {
    if (count > Int.MAX_VALUE.toULong()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (count == 0UL) return CODEX_AGENT_STATUS_OK
    val pointer = values ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    repeat(count.toInt()) { index ->
        val status = withPayload<CodexAgentCServiceTierSnapshot>(
            context,
            pointer[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private fun copyPlanSteps(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentPlanStep>,
): Int {
    if (count > Int.MAX_VALUE.toULong()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (count == 0UL) return CODEX_AGENT_STATUS_OK
    val pointer = values ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    repeat(count.toInt()) { index ->
        val status = withPayload<CodexAgentCPlanStepSnapshot>(
            context,
            pointer[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private fun copyHookActivities(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentHookActivity>,
): Int {
    if (count > Int.MAX_VALUE.toULong()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (count == 0UL) return CODEX_AGENT_STATUS_OK
    val pointer = values ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    repeat(count.toInt()) { index ->
        val status = withPayload<CodexAgentCHookActivitySnapshot>(
            context,
            pointer[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.deepCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private inline fun <reified T : CodexAgentCSnapshot> destroyProgressValue(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyProgressString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> String,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalProgressString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> String?,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> progressCount(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        outCount.pointed.value = select(it).toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> progressInt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<IntVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it)
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyProgressStringAt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> List<String>,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it).itemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun <T> List<T>.itemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())

private fun hookRunStatusFromC(value: Int): AgentHookRunStatus = when (value) {
    0 -> AgentHookRunStatus.RUNNING
    1 -> AgentHookRunStatus.COMPLETED
    2 -> AgentHookRunStatus.FAILED
    3 -> AgentHookRunStatus.BLOCKED
    4 -> AgentHookRunStatus.STOPPED
    else -> throw IllegalArgumentException("Unknown hook run status")
}

private fun hookRunStatusToC(value: AgentHookRunStatus): Int = when (value) {
    AgentHookRunStatus.RUNNING -> 0
    AgentHookRunStatus.COMPLETED -> 1
    AgentHookRunStatus.FAILED -> 2
    AgentHookRunStatus.BLOCKED -> 3
    AgentHookRunStatus.STOPPED -> 4
}

private fun workActivityFromC(value: Int): AgentWorkActivity = when (value) {
    0 -> AgentWorkActivity.RUNNING_COMMAND
    1 -> AgentWorkActivity.WRITING_FILES
    else -> throw IllegalArgumentException("Unknown work activity")
}

private fun workActivityToC(value: AgentWorkActivity): Int = when (value) {
    AgentWorkActivity.RUNNING_COMMAND -> 0
    AgentWorkActivity.WRITING_FILES -> 1
}

private fun AgentPlanProgress.deepCopy(): AgentPlanProgress = copy(steps = steps.map { it.copy() })

private fun AgentHookActivity.deepCopy(): AgentHookActivity = copy(details = details.toList())
