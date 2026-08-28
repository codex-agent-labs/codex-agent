@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexmobile.agent.AgentCapability
import io.github.codex_agent_labs.codexmobile.agent.AgentCollaborationMode
import io.github.codex_agent_labs.codexmobile.agent.AgentConversation
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationSummary
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentMessage
import io.github.codex_agent_labs.codexmobile.agent.AgentMessageRole
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnProgress
import io.github.codex_agent_labs.codexmobile.agent.AgentTurnRequest
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
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

internal data class CodexAgentCInvocationAggregateSnapshot(
    val value: AgentInvocation,
) : CodexAgentCSnapshot

internal data class CodexAgentCMessageSnapshot(
    val value: AgentMessage,
) : CodexAgentCSnapshot

internal data class CodexAgentCConversationValueSnapshot(
    val value: AgentConversation,
) : CodexAgentCSnapshot

internal data class CodexAgentCTurnRequestSnapshot(
    val value: AgentTurnRequest,
) : CodexAgentCSnapshot

@CName("codex_agent_invocation_from_plugin")
public fun codexAgentInvocationFromPlugin(
    context: COpaquePointer?,
    plugin: COpaquePointer?,
    outInvocation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outInvocation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInvocationPluginSnapshot>(contextPointer, plugin, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(
            outInvocation,
            createSnapshot(contextPointer, CodexAgentCInvocationAggregateSnapshot(it.value.aggregateCopy())),
        )
    }
}

@CName("codex_agent_invocation_from_skill")
public fun codexAgentInvocationFromSkill(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    outInvocation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outInvocation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInvocationSkillSnapshot>(contextPointer, skill, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(
            outInvocation,
            createSnapshot(contextPointer, CodexAgentCInvocationAggregateSnapshot(it.value.aggregateCopy())),
        )
    }
}

@CName("codex_agent_invocation_destroy")
public fun codexAgentInvocationDestroy(
    context: COpaquePointer?,
    invocation: CPointer<COpaquePointerVar>?,
): Int = destroyConversationAggregate<CodexAgentCInvocationAggregateSnapshot>(context, invocation)

@CName("codex_agent_invocation_kind")
public fun codexAgentInvocationKind(
    context: COpaquePointer?,
    invocation: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCInvocationAggregateSnapshot>(context, invocation, outKind) {
    when (it.value) {
        is AgentInvocation.Plugin -> 0
        is AgentInvocation.Skill -> 1
    }
}

@CName("codex_agent_invocation_plugin")
public fun codexAgentInvocationPlugin(
    context: COpaquePointer?,
    invocation: COpaquePointer?,
    outPlugin: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outPlugin)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInvocationAggregateSnapshot>(
        contextPointer,
        invocation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val plugin = it.value as? AgentInvocation.Plugin ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outPlugin,
            createSnapshot(contextPointer, CodexAgentCInvocationPluginSnapshot(plugin.copy())),
        )
    }
}

@CName("codex_agent_invocation_skill")
public fun codexAgentInvocationSkill(
    context: COpaquePointer?,
    invocation: COpaquePointer?,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSkill)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInvocationAggregateSnapshot>(
        contextPointer,
        invocation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val skill = it.value as? AgentInvocation.Skill ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outSkill,
            createSnapshot(contextPointer, CodexAgentCInvocationSkillSnapshot(skill.copy())),
        )
    }
}

@CName("codex_agent_message_create")
public fun codexAgentMessageCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    hasClientMessageId: Int,
    clientMessageId: CPointer<codex_agent_string_view>?,
    role: Int,
    text: CPointer<codex_agent_string_view>?,
    collaborationMode: Int,
    hasReasoning: Int,
    reasoning: CPointer<codex_agent_string_view>?,
    hasPlan: Int,
    plan: CPointer<codex_agent_string_view>?,
    hasShellCommand: Int,
    shellCommand: CPointer<codex_agent_string_view>?,
    hasExitCode: Int,
    exitCode: Int,
    capabilities: CPointer<IntVar>?,
    capabilityCount: ULong,
    invocations: CPointer<COpaquePointerVar>?,
    invocationCount: ULong,
    outMessage: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMessage)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireAggregateFlag(hasClientMessageId)
    requireAggregateFlag(hasReasoning)
    requireAggregateFlag(hasPlan)
    requireAggregateFlag(hasShellCommand)
    requireAggregateFlag(hasExitCode)
    if (hasExitCode == 0) require(exitCode == 0)
    val copiedInvocations = mutableListOf<AgentInvocation>()
    val invocationStatus = copyAggregateInvocations(
        contextPointer,
        invocations,
        invocationCount,
        copiedInvocations,
    )
    if (invocationStatus != CODEX_AGENT_STATUS_OK) return@abiStatus invocationStatus
    val value = AgentMessage(
        id = id.readRequiredAggregateUtf8(),
        clientMessageId = clientMessageId.readOptionalAggregateUtf8(hasClientMessageId),
        role = messageRoleFromAggregateC(role),
        text = text.readRequiredAggregateUtf8(),
        collaborationMode = collaborationModeFromAggregateC(collaborationMode),
        reasoning = reasoning.readOptionalAggregateUtf8(hasReasoning),
        plan = plan.readOptionalAggregateUtf8(hasPlan),
        shellCommand = shellCommand.readOptionalAggregateUtf8(hasShellCommand),
        exitCode = if (hasExitCode == 1) exitCode else null,
        capabilities = copyAggregateCapabilities(capabilities, capabilityCount),
        invocations = copiedInvocations,
    )
    installOutput(outMessage, createSnapshot(contextPointer, CodexAgentCMessageSnapshot(value)))
}

@CName("codex_agent_message_destroy")
public fun codexAgentMessageDestroy(
    context: COpaquePointer?,
    message: CPointer<COpaquePointerVar>?,
): Int = destroyConversationAggregate<CodexAgentCMessageSnapshot>(context, message)

@CName("codex_agent_message_id_copy")
public fun codexAgentMessageIdCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateString<CodexAgentCMessageSnapshot>(context, message, buffer, capacity, outRequired) {
    it.value.id
}

@CName("codex_agent_message_has_client_message_id")
public fun codexAgentMessageHasClientMessageId(
    context: COpaquePointer?, message: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outHasValue) {
    it.value.clientMessageId.aggregatePresence()
}

@CName("codex_agent_message_client_message_id_copy")
public fun codexAgentMessageClientMessageIdCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCMessageSnapshot>(
    context, message, buffer, capacity, outRequired,
) { it.value.clientMessageId }

@CName("codex_agent_message_role")
public fun codexAgentMessageRole(
    context: COpaquePointer?, message: COpaquePointer?, outRole: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outRole) {
    messageRoleToAggregateC(it.value.role)
}

@CName("codex_agent_message_text_copy")
public fun codexAgentMessageTextCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateString<CodexAgentCMessageSnapshot>(context, message, buffer, capacity, outRequired) {
    it.value.text
}

@CName("codex_agent_message_collaboration_mode")
public fun codexAgentMessageCollaborationMode(
    context: COpaquePointer?, message: COpaquePointer?, outMode: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outMode) {
    collaborationModeToAggregateC(it.value.collaborationMode)
}

@CName("codex_agent_message_has_reasoning")
public fun codexAgentMessageHasReasoning(
    context: COpaquePointer?, message: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outHasValue) {
    it.value.reasoning.aggregatePresence()
}

@CName("codex_agent_message_reasoning_copy")
public fun codexAgentMessageReasoningCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCMessageSnapshot>(
    context, message, buffer, capacity, outRequired,
) { it.value.reasoning }

@CName("codex_agent_message_has_plan")
public fun codexAgentMessageHasPlan(
    context: COpaquePointer?, message: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outHasValue) {
    it.value.plan.aggregatePresence()
}

@CName("codex_agent_message_plan_copy")
public fun codexAgentMessagePlanCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCMessageSnapshot>(
    context, message, buffer, capacity, outRequired,
) { it.value.plan }

@CName("codex_agent_message_has_shell_command")
public fun codexAgentMessageHasShellCommand(
    context: COpaquePointer?, message: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outHasValue) {
    it.value.shellCommand.aggregatePresence()
}

@CName("codex_agent_message_shell_command_copy")
public fun codexAgentMessageShellCommandCopy(
    context: COpaquePointer?, message: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCMessageSnapshot>(
    context, message, buffer, capacity, outRequired,
) { it.value.shellCommand }

@CName("codex_agent_message_exit_code")
public fun codexAgentMessageExitCode(
    context: COpaquePointer?,
    message: COpaquePointer?,
    outHasExitCode: CPointer<IntVar>?,
    outExitCode: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasExitCode == null || outExitCode == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMessageSnapshot>(context, message, CodexAgentCHandleKind.SNAPSHOT) {
        outHasExitCode.pointed.value = it.value.exitCode.aggregatePresence()
        outExitCode.pointed.value = it.value.exitCode ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_message_capabilities_count")
public fun codexAgentMessageCapabilitiesCount(
    context: COpaquePointer?, message: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = conversationAggregateCount<CodexAgentCMessageSnapshot>(context, message, outCount) {
    it.value.capabilities.size
}

@CName("codex_agent_message_has_capability")
public fun codexAgentMessageHasCapability(
    context: COpaquePointer?, message: COpaquePointer?, capability: Int, outHasCapability: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCMessageSnapshot>(context, message, outHasCapability) {
    if (capabilityFromAggregateC(capability) in it.value.capabilities) 1 else 0
}

@CName("codex_agent_message_invocations_count")
public fun codexAgentMessageInvocationsCount(
    context: COpaquePointer?, message: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = conversationAggregateCount<CodexAgentCMessageSnapshot>(context, message, outCount) {
    it.value.invocations.size
}

@CName("codex_agent_message_invocation_at")
public fun codexAgentMessageInvocationAt(
    context: COpaquePointer?,
    message: COpaquePointer?,
    index: ULong,
    outInvocation: CPointer<COpaquePointerVar>?,
): Int = aggregateInvocationAt<CodexAgentCMessageSnapshot>(context, message, index, outInvocation) {
    it.value.invocations
}

@CName("codex_agent_conversation_value_create")
public fun codexAgentConversationValueCreate(
    context: COpaquePointer?,
    summary: COpaquePointer?,
    messages: CPointer<COpaquePointerVar>?,
    messageCount: ULong,
    outConversation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    var copiedSummary: AgentConversationSummary? = null
    val summaryStatus = withPayload<CodexAgentCConversationSummarySnapshot>(
        contextPointer,
        summary,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copiedSummary = it.value.aggregateCopy()
        CODEX_AGENT_STATUS_OK
    }
    if (summaryStatus != CODEX_AGENT_STATUS_OK) return@abiStatus summaryStatus
    val copiedMessages = mutableListOf<AgentMessage>()
    val messageStatus = copyAggregateMessages(contextPointer, messages, messageCount, copiedMessages)
    if (messageStatus != CODEX_AGENT_STATUS_OK) return@abiStatus messageStatus
    installOutput(
        outConversation,
        createSnapshot(
            contextPointer,
            CodexAgentCConversationValueSnapshot(
                AgentConversation(checkNotNull(copiedSummary), copiedMessages),
            ),
        ),
    )
}

@CName("codex_agent_conversation_value_destroy")
public fun codexAgentConversationValueDestroy(
    context: COpaquePointer?,
    conversation: CPointer<COpaquePointerVar>?,
): Int = destroyConversationAggregate<CodexAgentCConversationValueSnapshot>(context, conversation)

@CName("codex_agent_conversation_value_summary")
public fun codexAgentConversationValueSummary(
    context: COpaquePointer?, conversation: COpaquePointer?, outSummary: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSummary)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationValueSnapshot>(
        contextPointer,
        conversation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outSummary,
            createSnapshot(contextPointer, CodexAgentCConversationSummarySnapshot(it.value.summary.aggregateCopy())),
        )
    }
}

@CName("codex_agent_conversation_value_messages_count")
public fun codexAgentConversationValueMessagesCount(
    context: COpaquePointer?, conversation: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = conversationAggregateCount<CodexAgentCConversationValueSnapshot>(context, conversation, outCount) {
    it.value.messages.size
}

@CName("codex_agent_conversation_value_message_at")
public fun codexAgentConversationValueMessageAt(
    context: COpaquePointer?,
    conversation: COpaquePointer?,
    index: ULong,
    outMessage: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMessage)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationValueSnapshot>(
        contextPointer,
        conversation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = it.value.messages.aggregateItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(outMessage, createSnapshot(contextPointer, CodexAgentCMessageSnapshot(value.aggregateCopy())))
    }
}

@CName("codex_agent_turn_request_create")
public fun codexAgentTurnRequestCreate(
    context: COpaquePointer?,
    prompt: CPointer<codex_agent_string_view>?,
    hasClientMessageId: Int,
    clientMessageId: CPointer<codex_agent_string_view>?,
    hasModel: Int,
    model: CPointer<codex_agent_string_view>?,
    hasEffort: Int,
    effort: CPointer<codex_agent_string_view>?,
    hasServiceTier: Int,
    serviceTier: CPointer<codex_agent_string_view>?,
    approvalPreset: Int,
    capabilities: CPointer<IntVar>?,
    capabilityCount: ULong,
    invocations: CPointer<COpaquePointerVar>?,
    invocationCount: ULong,
    collaborationMode: Int,
    outRequest: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outRequest)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireAggregateFlag(hasClientMessageId)
    requireAggregateFlag(hasModel)
    requireAggregateFlag(hasEffort)
    requireAggregateFlag(hasServiceTier)
    val copiedInvocations = mutableListOf<AgentInvocation>()
    val invocationStatus = copyAggregateInvocations(
        contextPointer,
        invocations,
        invocationCount,
        copiedInvocations,
    )
    if (invocationStatus != CODEX_AGENT_STATUS_OK) return@abiStatus invocationStatus
    val value = AgentTurnRequest(
        prompt = prompt.readRequiredAggregateUtf8(),
        clientMessageId = clientMessageId.readOptionalAggregateUtf8(hasClientMessageId),
        model = model.readOptionalAggregateUtf8(hasModel),
        effort = effort.readOptionalAggregateUtf8(hasEffort),
        serviceTier = serviceTier.readOptionalAggregateUtf8(hasServiceTier),
        approvalPreset = approvalPresetFromAggregateC(approvalPreset),
        capabilities = copyAggregateCapabilities(capabilities, capabilityCount),
        invocations = copiedInvocations,
        collaborationMode = collaborationModeFromAggregateC(collaborationMode),
    )
    installOutput(outRequest, createSnapshot(contextPointer, CodexAgentCTurnRequestSnapshot(value)))
}

@CName("codex_agent_turn_request_destroy")
public fun codexAgentTurnRequestDestroy(
    context: COpaquePointer?,
    request: CPointer<COpaquePointerVar>?,
): Int = destroyConversationAggregate<CodexAgentCTurnRequestSnapshot>(context, request)

@CName("codex_agent_turn_request_prompt_copy")
public fun codexAgentTurnRequestPromptCopy(
    context: COpaquePointer?, request: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateString<CodexAgentCTurnRequestSnapshot>(context, request, buffer, capacity, outRequired) {
    it.value.prompt
}

@CName("codex_agent_turn_request_has_client_message_id")
public fun codexAgentTurnRequestHasClientMessageId(
    context: COpaquePointer?, request: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outHasValue) {
    it.value.clientMessageId.aggregatePresence()
}

@CName("codex_agent_turn_request_client_message_id_copy")
public fun codexAgentTurnRequestClientMessageIdCopy(
    context: COpaquePointer?, request: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCTurnRequestSnapshot>(
    context, request, buffer, capacity, outRequired,
) { it.value.clientMessageId }

@CName("codex_agent_turn_request_has_model")
public fun codexAgentTurnRequestHasModel(
    context: COpaquePointer?, request: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outHasValue) {
    it.value.model.aggregatePresence()
}

@CName("codex_agent_turn_request_model_copy")
public fun codexAgentTurnRequestModelCopy(
    context: COpaquePointer?, request: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCTurnRequestSnapshot>(
    context, request, buffer, capacity, outRequired,
) { it.value.model }

@CName("codex_agent_turn_request_has_effort")
public fun codexAgentTurnRequestHasEffort(
    context: COpaquePointer?, request: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outHasValue) {
    it.value.effort.aggregatePresence()
}

@CName("codex_agent_turn_request_effort_copy")
public fun codexAgentTurnRequestEffortCopy(
    context: COpaquePointer?, request: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCTurnRequestSnapshot>(
    context, request, buffer, capacity, outRequired,
) { it.value.effort }

@CName("codex_agent_turn_request_has_service_tier")
public fun codexAgentTurnRequestHasServiceTier(
    context: COpaquePointer?, request: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outHasValue) {
    it.value.serviceTier.aggregatePresence()
}

@CName("codex_agent_turn_request_service_tier_copy")
public fun codexAgentTurnRequestServiceTierCopy(
    context: COpaquePointer?, request: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCTurnRequestSnapshot>(
    context, request, buffer, capacity, outRequired,
) { it.value.serviceTier }

@CName("codex_agent_turn_request_approval_preset")
public fun codexAgentTurnRequestApprovalPreset(
    context: COpaquePointer?, request: COpaquePointer?, outPreset: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outPreset) {
    approvalPresetToAggregateC(it.value.approvalPreset)
}

@CName("codex_agent_turn_request_capabilities_count")
public fun codexAgentTurnRequestCapabilitiesCount(
    context: COpaquePointer?, request: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = conversationAggregateCount<CodexAgentCTurnRequestSnapshot>(context, request, outCount) {
    it.value.capabilities.size
}

@CName("codex_agent_turn_request_has_capability")
public fun codexAgentTurnRequestHasCapability(
    context: COpaquePointer?, request: COpaquePointer?, capability: Int, outHasCapability: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outHasCapability) {
    if (capabilityFromAggregateC(capability) in it.value.capabilities) 1 else 0
}

@CName("codex_agent_turn_request_invocations_count")
public fun codexAgentTurnRequestInvocationsCount(
    context: COpaquePointer?, request: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = conversationAggregateCount<CodexAgentCTurnRequestSnapshot>(context, request, outCount) {
    it.value.invocations.size
}

@CName("codex_agent_turn_request_invocation_at")
public fun codexAgentTurnRequestInvocationAt(
    context: COpaquePointer?,
    request: COpaquePointer?,
    index: ULong,
    outInvocation: CPointer<COpaquePointerVar>?,
): Int = aggregateInvocationAt<CodexAgentCTurnRequestSnapshot>(context, request, index, outInvocation) {
    it.value.invocations
}

@CName("codex_agent_turn_request_collaboration_mode")
public fun codexAgentTurnRequestCollaborationMode(
    context: COpaquePointer?, request: COpaquePointer?, outMode: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCTurnRequestSnapshot>(context, request, outMode) {
    collaborationModeToAggregateC(it.value.collaborationMode)
}

@CName("codex_agent_conversation_state_create")
public fun codexAgentConversationStateCreate(
    context: COpaquePointer?,
    status: Int,
    hasConversationId: Int,
    conversationId: COpaquePointer?,
    hasConversation: Int,
    conversation: COpaquePointer?,
    turnProgress: COpaquePointer?,
    hasModel: Int,
    model: CPointer<codex_agent_string_view>?,
    hasEffort: Int,
    effort: CPointer<codex_agent_string_view>?,
    hasServiceTier: Int,
    serviceTier: CPointer<codex_agent_string_view>?,
    hasFailure: Int,
    failure: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireAggregateFlag(hasConversationId)
    requireAggregateFlag(hasConversation)
    requireAggregateFlag(hasModel)
    requireAggregateFlag(hasEffort)
    requireAggregateFlag(hasServiceTier)
    requireAggregateFlag(hasFailure)
    if (hasConversationId == 0) require(conversationId == null)
    if (hasConversation == 0) require(conversation == null)
    if (hasFailure == 0) require(failure == null)
    var copiedId: ConversationId? = null
    if (hasConversationId == 1) {
        val idStatus = withPayload<CodexAgentCConversationIdSnapshot>(
            contextPointer,
            conversationId,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedId = ConversationId(it.value.value)
            CODEX_AGENT_STATUS_OK
        }
        if (idStatus != CODEX_AGENT_STATUS_OK) return@abiStatus idStatus
    }
    var copiedConversation: AgentConversation? = null
    if (hasConversation == 1) {
        val conversationStatus = withPayload<CodexAgentCConversationValueSnapshot>(
            contextPointer,
            conversation,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedConversation = it.value.aggregateCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (conversationStatus != CODEX_AGENT_STATUS_OK) return@abiStatus conversationStatus
    }
    var copiedProgress: AgentTurnProgress? = null
    val progressStatus = withPayload<CodexAgentCTurnProgressSnapshot>(
        contextPointer,
        turnProgress,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copiedProgress = it.value.aggregateCopy()
        CODEX_AGENT_STATUS_OK
    }
    if (progressStatus != CODEX_AGENT_STATUS_OK) return@abiStatus progressStatus
    var copiedFailure: CodexFailure? = null
    if (hasFailure == 1) {
        val failureStatus = withPayload<CodexFailure>(contextPointer, failure, CodexAgentCHandleKind.FAILURE) {
            copiedFailure = it.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (failureStatus != CODEX_AGENT_STATUS_OK) return@abiStatus failureStatus
    }
    val value = AgentConversationState(
        status = conversationStatusFromAggregateC(status),
        conversationId = copiedId,
        conversation = copiedConversation,
        turnProgress = checkNotNull(copiedProgress),
        model = model.readOptionalAggregateUtf8(hasModel),
        effort = effort.readOptionalAggregateUtf8(hasEffort),
        serviceTier = serviceTier.readOptionalAggregateUtf8(hasServiceTier),
        failure = copiedFailure,
    )
    installOutput(outState, createSnapshot(contextPointer, CodexAgentCConversationStateSnapshot(value)))
}

@CName("codex_agent_conversation_state_has_conversation_id")
public fun codexAgentConversationStateHasConversationId(
    context: COpaquePointer?, state: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outHasValue) {
    it.state.conversationId.aggregatePresence()
}

@CName("codex_agent_conversation_state_conversation_id")
public fun codexAgentConversationStateConversationId(
    context: COpaquePointer?, state: COpaquePointer?, outConversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversationId)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val id = it.state.conversationId ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outConversationId,
            createSnapshot(contextPointer, CodexAgentCConversationIdSnapshot(ConversationId(id.value))),
        )
    }
}

@CName("codex_agent_conversation_state_has_conversation")
public fun codexAgentConversationStateHasConversation(
    context: COpaquePointer?, state: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outHasValue) {
    it.state.conversation.aggregatePresence()
}

@CName("codex_agent_conversation_state_conversation")
public fun codexAgentConversationStateConversation(
    context: COpaquePointer?, state: COpaquePointer?, outConversation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val value = it.state.conversation ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outConversation,
            createSnapshot(contextPointer, CodexAgentCConversationValueSnapshot(value.aggregateCopy())),
        )
    }
}

@CName("codex_agent_conversation_state_turn_progress")
public fun codexAgentConversationStateTurnProgress(
    context: COpaquePointer?, state: COpaquePointer?, outProgress: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outProgress)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConversationStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(
            outProgress,
            createSnapshot(contextPointer, CodexAgentCTurnProgressSnapshot(it.state.turnProgress.aggregateCopy())),
        )
    }
}

@CName("codex_agent_conversation_state_has_model")
public fun codexAgentConversationStateHasModel(
    context: COpaquePointer?, state: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outHasValue) {
    it.state.model.aggregatePresence()
}

@CName("codex_agent_conversation_state_model_copy")
public fun codexAgentConversationStateModelCopy(
    context: COpaquePointer?, state: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCConversationStateSnapshot>(
    context, state, buffer, capacity, outRequired,
) { it.state.model }

@CName("codex_agent_conversation_state_has_effort")
public fun codexAgentConversationStateHasEffort(
    context: COpaquePointer?, state: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outHasValue) {
    it.state.effort.aggregatePresence()
}

@CName("codex_agent_conversation_state_effort_copy")
public fun codexAgentConversationStateEffortCopy(
    context: COpaquePointer?, state: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCConversationStateSnapshot>(
    context, state, buffer, capacity, outRequired,
) { it.state.effort }

@CName("codex_agent_conversation_state_has_service_tier")
public fun codexAgentConversationStateHasServiceTier(
    context: COpaquePointer?, state: COpaquePointer?, outHasValue: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outHasValue) {
    it.state.serviceTier.aggregatePresence()
}

@CName("codex_agent_conversation_state_service_tier_copy")
public fun codexAgentConversationStateServiceTierCopy(
    context: COpaquePointer?, state: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = conversationAggregateOptionalString<CodexAgentCConversationStateSnapshot>(
    context, state, buffer, capacity, outRequired,
) { it.state.serviceTier }

@CName("codex_agent_conversation_state_can_start_turn")
public fun codexAgentConversationStateCanStartTurn(
    context: COpaquePointer?, state: COpaquePointer?, outCanStart: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outCanStart) {
    if (it.state.canStartTurn) 1 else 0
}

@CName("codex_agent_conversation_state_can_reload")
public fun codexAgentConversationStateCanReload(
    context: COpaquePointer?, state: COpaquePointer?, outCanReload: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outCanReload) {
    if (it.state.canReload) 1 else 0
}

@CName("codex_agent_conversation_state_can_cancel_turn")
public fun codexAgentConversationStateCanCancelTurn(
    context: COpaquePointer?, state: COpaquePointer?, outCanCancel: CPointer<IntVar>?,
): Int = conversationAggregateInt<CodexAgentCConversationStateSnapshot>(context, state, outCanCancel) {
    if (it.state.canCancelTurn) 1 else 0
}

private fun requireAggregateFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun CPointer<codex_agent_string_view>?.readRequiredAggregateUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readOptionalAggregateUtf8(hasValue: Int): String? {
    val value = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(value.data == null && value.size == 0uL)
        return null
    }
    return value.readUtf8()
}

private fun copyAggregateCapabilities(values: CPointer<IntVar>?, count: ULong): Set<AgentCapability> {
    val size = aggregateArraySize(values, count)
    return buildSet {
        repeat(size) { add(capabilityFromAggregateC(checkNotNull(values)[it])) }
    }
}

private fun copyAggregateInvocations(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentInvocation>,
): Int {
    val size = aggregateArraySize(values, count)
    repeat(size) { index ->
        val status = withPayload<CodexAgentCInvocationAggregateSnapshot>(
            context,
            checkNotNull(values)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.aggregateCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private fun copyAggregateMessages(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentMessage>,
): Int {
    val size = aggregateArraySize(values, count)
    repeat(size) { index ->
        val status = withPayload<CodexAgentCMessageSnapshot>(
            context,
            checkNotNull(values)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            output += it.value.aggregateCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private fun <T : kotlinx.cinterop.CPointed> aggregateArraySize(values: CPointer<T>?, count: ULong): Int {
    require(count <= Int.MAX_VALUE.toULong())
    require((count == 0uL) == (values == null))
    return count.toInt()
}

private inline fun <reified T : CodexAgentCSnapshot> destroyConversationAggregate(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT) else status
}

private inline fun <reified T : Any> conversationAggregateString(
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

private inline fun <reified T : Any> conversationAggregateOptionalString(
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

private inline fun <reified T : Any> conversationAggregateInt(
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

private inline fun <reified T : Any> conversationAggregateCount(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<ULongVar>?,
    crossinline select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it).toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> aggregateInvocationAt(
    context: COpaquePointer?,
    owner: COpaquePointer?,
    index: ULong,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> List<AgentInvocation>,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, owner, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it).aggregateItemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            output,
            createSnapshot(contextPointer, CodexAgentCInvocationAggregateSnapshot(value.aggregateCopy())),
        )
    }
}

private fun <T> List<T>.aggregateItemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())

private fun Any?.aggregatePresence(): Int = if (this == null) 0 else 1

private fun AgentInvocation.aggregateCopy(): AgentInvocation = when (this) {
    is AgentInvocation.Plugin -> copy()
    is AgentInvocation.Skill -> copy()
}

private fun AgentMessage.aggregateCopy(): AgentMessage = copy(
    capabilities = capabilities.toSet(),
    invocations = invocations.map { it.aggregateCopy() },
)

private fun AgentConversationSummary.aggregateCopy(): AgentConversationSummary = copy(
    conversationId = ConversationId(conversationId.value),
)

private fun AgentConversation.aggregateCopy(): AgentConversation = AgentConversation(
    summary = summary.aggregateCopy(),
    messages = messages.map { it.aggregateCopy() },
)

private fun AgentTurnProgress.aggregateCopy(): AgentTurnProgress = copy(
    planProgress = planProgress?.let { it.copy(steps = it.steps.map { step -> step.copy() }) },
    hookActivities = hookActivities.map { it.copy(details = it.details.toList()) },
)

private fun messageRoleFromAggregateC(value: Int): AgentMessageRole = when (value) {
    0 -> AgentMessageRole.USER
    1 -> AgentMessageRole.ASSISTANT
    else -> throw IllegalArgumentException("Unknown message role")
}

private fun messageRoleToAggregateC(value: AgentMessageRole): Int = when (value) {
    AgentMessageRole.USER -> 0
    AgentMessageRole.ASSISTANT -> 1
}

private fun collaborationModeFromAggregateC(value: Int): AgentCollaborationMode = when (value) {
    0 -> AgentCollaborationMode.DEFAULT
    1 -> AgentCollaborationMode.PLAN
    else -> throw IllegalArgumentException("Unknown collaboration mode")
}

private fun collaborationModeToAggregateC(value: AgentCollaborationMode): Int = when (value) {
    AgentCollaborationMode.DEFAULT -> 0
    AgentCollaborationMode.PLAN -> 1
}

private fun approvalPresetFromAggregateC(value: Int): AgentApprovalPreset = when (value) {
    0 -> AgentApprovalPreset.NEVER
    1 -> AgentApprovalPreset.AUTO_REVIEW
    2 -> AgentApprovalPreset.ASK_ME
    3 -> AgentApprovalPreset.STRICT
    else -> throw IllegalArgumentException("Unknown approval preset")
}

private fun approvalPresetToAggregateC(value: AgentApprovalPreset): Int = when (value) {
    AgentApprovalPreset.NEVER -> 0
    AgentApprovalPreset.AUTO_REVIEW -> 1
    AgentApprovalPreset.ASK_ME -> 2
    AgentApprovalPreset.STRICT -> 3
}

private fun capabilityFromAggregateC(value: Int): AgentCapability = when (value) {
    0 -> AgentCapability.WEB_SEARCH
    else -> throw IllegalArgumentException("Unknown capability")
}

private fun conversationStatusFromAggregateC(value: Int): AgentConversationStatus = when (value) {
    0 -> AgentConversationStatus.NEW
    1 -> AgentConversationStatus.OPENING
    2 -> AgentConversationStatus.READY
    3 -> AgentConversationStatus.STARTING_TURN
    4 -> AgentConversationStatus.RUNNING_TURN
    5 -> AgentConversationStatus.CANCELLING_TURN
    6 -> AgentConversationStatus.RELOADING
    7 -> AgentConversationStatus.FAILED
    8 -> AgentConversationStatus.CLOSED
    else -> throw IllegalArgumentException("Unknown conversation status")
}
