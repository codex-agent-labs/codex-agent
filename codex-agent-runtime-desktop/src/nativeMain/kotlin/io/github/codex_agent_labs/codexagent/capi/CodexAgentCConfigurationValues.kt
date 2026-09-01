@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentElicitationValidationIssue
import io.github.codex_agent_labs.codexagent.agent.AgentElicitationValidationReason
import io.github.codex_agent_labs.codexagent.agent.AgentFormOption
import io.github.codex_agent_labs.codexagent.agent.AgentMcpEnvironmentSource
import io.github.codex_agent_labs.codexagent.agent.AgentMcpEnvironmentVariable
import io.github.codex_agent_labs.codexagent.agent.AgentMcpOauthConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolApproval
import io.github.codex_agent_labs.codexagent.agent.AgentMcpToolConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentPlanStep
import io.github.codex_agent_labs.codexagent.agent.AgentPlanStepStatus
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCFormOptionSnapshot(
    val value: AgentFormOption,
) : CodexAgentCSnapshot

internal data class CodexAgentCMcpEnvironmentVariableSnapshot(
    val value: AgentMcpEnvironmentVariable,
) : CodexAgentCSnapshot

internal data class CodexAgentCMcpOauthConfigurationSnapshot(
    val value: AgentMcpOauthConfiguration,
) : CodexAgentCSnapshot

internal data class CodexAgentCMcpToolConfigurationSnapshot(
    val value: AgentMcpToolConfiguration,
) : CodexAgentCSnapshot

internal data class CodexAgentCElicitationValidationIssueSnapshot(
    val value: AgentElicitationValidationIssue,
) : CodexAgentCSnapshot

internal data class CodexAgentCPlanStepSnapshot(
    val value: AgentPlanStep,
) : CodexAgentCSnapshot

@CName("codex_agent_form_option_create")
public fun codexAgentFormOptionCreate(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    hasTitle: Int,
    title: CPointer<codex_agent_string_view>?,
    hasDescription: Int,
    description: CPointer<codex_agent_string_view>?,
    outOption: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOption)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedValue = value.readRequiredUtf8()
    val parsedTitle = title.readOptionalUtf8(hasTitle)
    val parsedDescription = description.readOptionalUtf8(hasDescription)
    installOutput(
        outOption,
        createSnapshot(
            pointer,
            CodexAgentCFormOptionSnapshot(
                AgentFormOption(
                    value = parsedValue,
                    title = parsedTitle ?: parsedValue,
                    description = parsedDescription,
                ),
            ),
        ),
    )
}

@CName("codex_agent_form_option_destroy")
public fun codexAgentFormOptionDestroy(
    context: COpaquePointer?,
    option: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCFormOptionSnapshot>(context, option)

@CName("codex_agent_form_option_value_copy")
public fun codexAgentFormOptionValueCopy(
    context: COpaquePointer?,
    option: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyConfigurationValue<CodexAgentCFormOptionSnapshot>(
    context,
    option,
    buffer,
    capacity,
    outRequired,
) { it.value.value }

@CName("codex_agent_form_option_title_copy")
public fun codexAgentFormOptionTitleCopy(
    context: COpaquePointer?,
    option: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyConfigurationValue<CodexAgentCFormOptionSnapshot>(
    context,
    option,
    buffer,
    capacity,
    outRequired,
) { it.value.title }

@CName("codex_agent_form_option_has_description")
public fun codexAgentFormOptionHasDescription(
    context: COpaquePointer?,
    option: COpaquePointer?,
    outHasDescription: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasDescription == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormOptionSnapshot>(context, option, CodexAgentCHandleKind.SNAPSHOT) {
        outHasDescription.pointed.value = if (it.value.description == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_form_option_description_copy")
public fun codexAgentFormOptionDescriptionCopy(
    context: COpaquePointer?,
    option: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalConfigurationValue<CodexAgentCFormOptionSnapshot>(
    context,
    option,
    buffer,
    capacity,
    outRequired,
) { it.value.description }

@CName("codex_agent_mcp_environment_variable_create")
public fun codexAgentMcpEnvironmentVariableCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    hasSource: Int,
    source: Int,
    outVariable: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outVariable)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedName = name.readRequiredUtf8()
    val parsedSource = optionalMcpEnvironmentSource(hasSource, source)
    installOutput(
        outVariable,
        createSnapshot(
            pointer,
            CodexAgentCMcpEnvironmentVariableSnapshot(
                AgentMcpEnvironmentVariable(parsedName, parsedSource),
            ),
        ),
    )
}

@CName("codex_agent_mcp_environment_variable_destroy")
public fun codexAgentMcpEnvironmentVariableDestroy(
    context: COpaquePointer?,
    variable: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCMcpEnvironmentVariableSnapshot>(context, variable)

@CName("codex_agent_mcp_environment_variable_name_copy")
public fun codexAgentMcpEnvironmentVariableNameCopy(
    context: COpaquePointer?,
    variable: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyConfigurationValue<CodexAgentCMcpEnvironmentVariableSnapshot>(
    context,
    variable,
    buffer,
    capacity,
    outRequired,
) { it.value.name }

@CName("codex_agent_mcp_environment_variable_source")
public fun codexAgentMcpEnvironmentVariableSource(
    context: COpaquePointer?,
    variable: COpaquePointer?,
    outHasSource: CPointer<IntVar>?,
    outSource: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasSource == null || outSource == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpEnvironmentVariableSnapshot>(
        context,
        variable,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val source = it.value.source
        val projected = source?.toCValue() ?: 0
        outHasSource.pointed.value = if (source == null) 0 else 1
        outSource.pointed.value = projected
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_mcp_oauth_configuration_create")
public fun codexAgentMcpOauthConfigurationCreate(
    context: COpaquePointer?,
    hasClientId: Int,
    clientId: CPointer<codex_agent_string_view>?,
    hasCallbackPort: Int,
    callbackPort: Int,
    outConfiguration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConfiguration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedClientId = clientId.readOptionalUtf8(hasClientId)
    val parsedCallbackPort = optionalScalar(hasCallbackPort, callbackPort)
    installOutput(
        outConfiguration,
        createSnapshot(
            pointer,
            CodexAgentCMcpOauthConfigurationSnapshot(
                AgentMcpOauthConfiguration(parsedClientId, parsedCallbackPort),
            ),
        ),
    )
}

@CName("codex_agent_mcp_oauth_configuration_destroy")
public fun codexAgentMcpOauthConfigurationDestroy(
    context: COpaquePointer?,
    configuration: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCMcpOauthConfigurationSnapshot>(context, configuration)

@CName("codex_agent_mcp_oauth_configuration_has_client_id")
public fun codexAgentMcpOauthConfigurationHasClientId(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasClientId: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasClientId == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpOauthConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasClientId.pointed.value = if (it.value.clientId == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_mcp_oauth_configuration_client_id_copy")
public fun codexAgentMcpOauthConfigurationClientIdCopy(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalConfigurationValue<CodexAgentCMcpOauthConfigurationSnapshot>(
    context,
    configuration,
    buffer,
    capacity,
    outRequired,
) { it.value.clientId }

@CName("codex_agent_mcp_oauth_configuration_callback_port")
public fun codexAgentMcpOauthConfigurationCallbackPort(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasCallbackPort: CPointer<IntVar>?,
    outCallbackPort: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasCallbackPort == null || outCallbackPort == null) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    withPayload<CodexAgentCMcpOauthConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val callbackPort = it.value.callbackPort
        outHasCallbackPort.pointed.value = if (callbackPort == null) 0 else 1
        outCallbackPort.pointed.value = callbackPort ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_mcp_tool_configuration_create")
public fun codexAgentMcpToolConfigurationCreate(
    context: COpaquePointer?,
    hasApproval: Int,
    approval: Int,
    outConfiguration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConfiguration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedApproval = optionalMcpToolApproval(hasApproval, approval)
    installOutput(
        outConfiguration,
        createSnapshot(
            pointer,
            CodexAgentCMcpToolConfigurationSnapshot(AgentMcpToolConfiguration(parsedApproval)),
        ),
    )
}

@CName("codex_agent_mcp_tool_configuration_destroy")
public fun codexAgentMcpToolConfigurationDestroy(
    context: COpaquePointer?,
    configuration: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCMcpToolConfigurationSnapshot>(context, configuration)

@CName("codex_agent_mcp_tool_configuration_approval")
public fun codexAgentMcpToolConfigurationApproval(
    context: COpaquePointer?,
    configuration: COpaquePointer?,
    outHasApproval: CPointer<IntVar>?,
    outApproval: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasApproval == null || outApproval == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpToolConfigurationSnapshot>(
        context,
        configuration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val approval = it.value.approval
        outHasApproval.pointed.value = if (approval == null) 0 else 1
        outApproval.pointed.value = approval?.toCValue() ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_elicitation_validation_issue_create")
public fun codexAgentElicitationValidationIssueCreate(
    context: COpaquePointer?,
    fieldName: CPointer<codex_agent_string_view>?,
    reason: Int,
    outIssue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIssue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedFieldName = fieldName.readRequiredUtf8()
    val parsedReason = elicitationValidationReasonFromCValue(reason)
    installOutput(
        outIssue,
        createSnapshot(
            pointer,
            CodexAgentCElicitationValidationIssueSnapshot(
                AgentElicitationValidationIssue(parsedFieldName, parsedReason),
            ),
        ),
    )
}

@CName("codex_agent_elicitation_validation_issue_destroy")
public fun codexAgentElicitationValidationIssueDestroy(
    context: COpaquePointer?,
    issue: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCElicitationValidationIssueSnapshot>(context, issue)

@CName("codex_agent_elicitation_validation_issue_field_name_copy")
public fun codexAgentElicitationValidationIssueFieldNameCopy(
    context: COpaquePointer?,
    issue: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyConfigurationValue<CodexAgentCElicitationValidationIssueSnapshot>(
    context,
    issue,
    buffer,
    capacity,
    outRequired,
) { it.value.fieldName }

@CName("codex_agent_elicitation_validation_issue_reason")
public fun codexAgentElicitationValidationIssueReason(
    context: COpaquePointer?,
    issue: COpaquePointer?,
    outReason: CPointer<IntVar>?,
): Int = abiStatus {
    if (outReason == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationValidationIssueSnapshot>(
        context,
        issue,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outReason.pointed.value = it.value.reason.toCValue()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_plan_step_create")
public fun codexAgentPlanStepCreate(
    context: COpaquePointer?,
    text: CPointer<codex_agent_string_view>?,
    status: Int,
    outStep: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outStep)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val parsedText = text.readRequiredUtf8()
    val parsedStatus = planStepStatusFromCValue(status)
    installOutput(
        outStep,
        createSnapshot(
            pointer,
            CodexAgentCPlanStepSnapshot(AgentPlanStep(parsedText, parsedStatus)),
        ),
    )
}

@CName("codex_agent_plan_step_destroy")
public fun codexAgentPlanStepDestroy(
    context: COpaquePointer?,
    step: CPointer<COpaquePointerVar>?,
): Int = destroyTypedSnapshot<CodexAgentCPlanStepSnapshot>(context, step)

@CName("codex_agent_plan_step_text_copy")
public fun codexAgentPlanStepTextCopy(
    context: COpaquePointer?,
    step: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyConfigurationValue<CodexAgentCPlanStepSnapshot>(
    context,
    step,
    buffer,
    capacity,
    outRequired,
) { it.value.text }

@CName("codex_agent_plan_step_status")
public fun codexAgentPlanStepStatus(
    context: COpaquePointer?,
    step: COpaquePointer?,
    outStatus: CPointer<IntVar>?,
): Int = abiStatus {
    if (outStatus == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPlanStepSnapshot>(context, step, CodexAgentCHandleKind.SNAPSHOT) {
        outStatus.pointed.value = it.value.status.toCValue()
        CODEX_AGENT_STATUS_OK
    }
}

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readOptionalUtf8(hasValue: Int): String? {
    requireFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0uL)
        return null
    } else {
        return view.readUtf8()
    }
}

private fun requireFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun optionalScalar(hasValue: Int, value: Int): Int? {
    requireFlag(hasValue)
    if (hasValue == 0) {
        require(value == 0)
        return null
    }
    return value
}

private fun optionalMcpEnvironmentSource(hasValue: Int, value: Int): AgentMcpEnvironmentSource? {
    val present = optionalScalar(hasValue, value) ?: return null
    return mcpEnvironmentSourceFromCValue(present)
}

private fun mcpEnvironmentSourceFromCValue(value: Int): AgentMcpEnvironmentSource = when (value) {
    0 -> AgentMcpEnvironmentSource.LOCAL
    1 -> AgentMcpEnvironmentSource.REMOTE
    else -> throw IllegalArgumentException("Unknown MCP environment source")
}

private fun AgentMcpEnvironmentSource.toCValue(): Int = when (this) {
    AgentMcpEnvironmentSource.LOCAL -> 0
    AgentMcpEnvironmentSource.REMOTE -> 1
}

private fun optionalMcpToolApproval(hasValue: Int, value: Int): AgentMcpToolApproval? {
    val present = optionalScalar(hasValue, value) ?: return null
    return mcpToolApprovalFromCValue(present)
}

private fun mcpToolApprovalFromCValue(value: Int): AgentMcpToolApproval = when (value) {
    0 -> AgentMcpToolApproval.AUTO
    1 -> AgentMcpToolApproval.PROMPT
    2 -> AgentMcpToolApproval.WRITES
    3 -> AgentMcpToolApproval.APPROVE
    else -> throw IllegalArgumentException("Unknown MCP tool approval")
}

private fun AgentMcpToolApproval.toCValue(): Int = when (this) {
    AgentMcpToolApproval.AUTO -> 0
    AgentMcpToolApproval.PROMPT -> 1
    AgentMcpToolApproval.WRITES -> 2
    AgentMcpToolApproval.APPROVE -> 3
}

private fun elicitationValidationReasonFromCValue(value: Int): AgentElicitationValidationReason = when (value) {
    0 -> AgentElicitationValidationReason.MISSING_REQUIRED
    1 -> AgentElicitationValidationReason.UNKNOWN_FIELD
    2 -> AgentElicitationValidationReason.INVALID_TYPE
    3 -> AgentElicitationValidationReason.NON_FINITE_NUMBER
    4 -> AgentElicitationValidationReason.BELOW_MINIMUM
    5 -> AgentElicitationValidationReason.ABOVE_MAXIMUM
    6 -> AgentElicitationValidationReason.NON_INTEGER
    7 -> AgentElicitationValidationReason.INVALID_FORMAT
    8 -> AgentElicitationValidationReason.INVALID_SELECTION
    9 -> AgentElicitationValidationReason.DUPLICATE_SELECTION
    else -> throw IllegalArgumentException("Unknown elicitation validation reason")
}

private fun AgentElicitationValidationReason.toCValue(): Int = when (this) {
    AgentElicitationValidationReason.MISSING_REQUIRED -> 0
    AgentElicitationValidationReason.UNKNOWN_FIELD -> 1
    AgentElicitationValidationReason.INVALID_TYPE -> 2
    AgentElicitationValidationReason.NON_FINITE_NUMBER -> 3
    AgentElicitationValidationReason.BELOW_MINIMUM -> 4
    AgentElicitationValidationReason.ABOVE_MAXIMUM -> 5
    AgentElicitationValidationReason.NON_INTEGER -> 6
    AgentElicitationValidationReason.INVALID_FORMAT -> 7
    AgentElicitationValidationReason.INVALID_SELECTION -> 8
    AgentElicitationValidationReason.DUPLICATE_SELECTION -> 9
}

private fun planStepStatusFromCValue(value: Int): AgentPlanStepStatus = when (value) {
    0 -> AgentPlanStepStatus.PENDING
    1 -> AgentPlanStepStatus.IN_PROGRESS
    2 -> AgentPlanStepStatus.COMPLETED
    else -> throw IllegalArgumentException("Unknown plan step status")
}

private fun AgentPlanStepStatus.toCValue(): Int = when (this) {
    AgentPlanStepStatus.PENDING -> 0
    AgentPlanStepStatus.IN_PROGRESS -> 1
    AgentPlanStepStatus.COMPLETED -> 2
}

private inline fun <reified T : CodexAgentCSnapshot> destroyTypedSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyConfigurationValue(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (T) -> String,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalConfigurationValue(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (T) -> String?,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}
