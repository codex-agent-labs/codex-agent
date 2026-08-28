@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentElicitation
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationAction
import io.github.codex_agent_labs.codexmobile.agent.AgentElicitationResponse
import io.github.codex_agent_labs.codexmobile.agent.AgentFormField
import io.github.codex_agent_labs.codexmobile.agent.AgentFormFieldType
import io.github.codex_agent_labs.codexmobile.agent.AgentFormOption
import io.github.codex_agent_labs.codexmobile.agent.AgentFormStringFormat
import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue
import io.github.codex_agent_labs.codexmobile.agent.AgentInteractionState
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingElicitation
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingInteraction
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexInteractions
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.DoubleVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCFormValueSnapshot(
    val value: AgentFormValue,
) : CodexAgentCSnapshot

internal data class CodexAgentCFormFieldSnapshot(
    val value: AgentFormField,
) : CodexAgentCSnapshot

internal data class CodexAgentCElicitationSnapshot(
    val value: AgentElicitation,
) : CodexAgentCSnapshot

internal data class CodexAgentCElicitationResponseSnapshot(
    val value: AgentElicitationResponse,
) : CodexAgentCSnapshot

internal data class CodexAgentCPendingElicitationSnapshot(
    val value: AgentPendingElicitation,
    val owner: CodexInteractions? = null,
) : CodexAgentCSnapshot

internal data class CodexAgentCPendingInteractionSnapshot(
    val value: AgentPendingInteraction,
    val owner: CodexInteractions? = null,
) : CodexAgentCSnapshot

internal data class CodexAgentCInteractionStateSnapshot(
    val value: AgentInteractionState,
    val owner: CodexInteractions? = null,
) : CodexAgentCSnapshot

private fun AgentFormValue.cAbiElicitationOwnedCopy(): AgentFormValue = when (this) {
    is AgentFormValue.BooleanValue -> copy()
    is AgentFormValue.Number -> copy()
    is AgentFormValue.Text -> copy()
    is AgentFormValue.TextList -> copy(value = value.toList())
}

private fun AgentFormField.cAbiElicitationOwnedCopy(): AgentFormField = copy(
    options = options.map { it.copy() },
    defaultValue = defaultValue?.cAbiElicitationOwnedCopy(),
)

private fun AgentElicitation.cAbiElicitationOwnedCopy(): AgentElicitation = copy(
    conversationId = ConversationId(conversationId.value),
    form = form?.map { it.cAbiElicitationOwnedCopy() },
)

private fun AgentElicitationResponse.cAbiElicitationOwnedCopy(): AgentElicitationResponse = copy(
    content = content.entries.associateTo(linkedMapOf()) { it.key to it.value.cAbiElicitationOwnedCopy() },
)

private fun AgentPendingInteraction.cAbiElicitationOwnedCopy(): AgentPendingInteraction = when (this) {
    is AgentPendingApproval -> copy(conversationId = ConversationId(conversationId.value))
    is AgentPendingElicitation -> AgentPendingElicitation(elicitation.cAbiElicitationOwnedCopy())
}

private fun AgentInteractionState.cAbiElicitationOwnedCopy(): AgentInteractionState = copy(
    pending = pending.map { it.cAbiElicitationOwnedCopy() },
    resolvingRequestIds = resolvingRequestIds.toSet(),
    failure = failure?.copy(),
)

@CName("codex_agent_form_value_from_boolean")
public fun codexAgentFormValueFromBoolean(
    context: COpaquePointer?,
    booleanValue: COpaquePointer?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = formValueFrom<CodexAgentCFormBooleanValueSnapshot>(context, booleanValue, outValue) { it.value }

@CName("codex_agent_form_value_from_number")
public fun codexAgentFormValueFromNumber(
    context: COpaquePointer?,
    numberValue: COpaquePointer?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = formValueFrom<CodexAgentCFormNumberValueSnapshot>(context, numberValue, outValue) { it.value }

@CName("codex_agent_form_value_from_text")
public fun codexAgentFormValueFromText(
    context: COpaquePointer?,
    textValue: COpaquePointer?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = formValueFrom<CodexAgentCFormTextValueSnapshot>(context, textValue, outValue) { it.value }

@CName("codex_agent_form_value_from_text_list")
public fun codexAgentFormValueFromTextList(
    context: COpaquePointer?,
    textListValue: COpaquePointer?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = formValueFrom<CodexAgentCFormTextListValueSnapshot>(context, textListValue, outValue) { it.value }

@CName("codex_agent_form_value_destroy")
public fun codexAgentFormValueDestroy(
    context: COpaquePointer?,
    value: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCFormValueSnapshot>(context, value)

@CName("codex_agent_form_value_kind")
public fun codexAgentFormValueKind(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormValueSnapshot>(context, value, outKind) {
    when (it.value) {
        is AgentFormValue.BooleanValue -> 0
        is AgentFormValue.Number -> 1
        is AgentFormValue.Text -> 2
        is AgentFormValue.TextList -> 3
    }
}

@CName("codex_agent_form_value_boolean")
public fun codexAgentFormValueBoolean(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outBooleanValue: CPointer<COpaquePointerVar>?,
): Int = formValueDowncast(context, value, outBooleanValue) {
    CodexAgentCFormBooleanValueSnapshot(it as? AgentFormValue.BooleanValue ?: return@formValueDowncast null)
}

@CName("codex_agent_form_value_number")
public fun codexAgentFormValueNumber(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outNumberValue: CPointer<COpaquePointerVar>?,
): Int = formValueDowncast(context, value, outNumberValue) {
    CodexAgentCFormNumberValueSnapshot(it as? AgentFormValue.Number ?: return@formValueDowncast null)
}

@CName("codex_agent_form_value_text")
public fun codexAgentFormValueText(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outTextValue: CPointer<COpaquePointerVar>?,
): Int = formValueDowncast(context, value, outTextValue) {
    CodexAgentCFormTextValueSnapshot(it as? AgentFormValue.Text ?: return@formValueDowncast null)
}

@CName("codex_agent_form_value_text_list")
public fun codexAgentFormValueTextList(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outTextListValue: CPointer<COpaquePointerVar>?,
): Int = formValueDowncast(context, value, outTextListValue) {
    val selected = it as? AgentFormValue.TextList ?: return@formValueDowncast null
    CodexAgentCFormTextListValueSnapshot(selected.copy(value = selected.value.toList()))
}

@CName("codex_agent_form_field_create")
public fun codexAgentFormFieldCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    title: CPointer<codex_agent_string_view>?,
    hasDescription: Int,
    description: CPointer<codex_agent_string_view>?,
    isRequired: Int,
    type: Int,
    options: CPointer<COpaquePointerVar>?,
    optionCount: ULong,
    hasDefaultValue: Int,
    defaultValue: COpaquePointer?,
    hasMinimum: Int,
    minimum: Double,
    hasMaximum: Int,
    maximum: Double,
    hasFormat: Int,
    format: Int,
    hasMinimumLength: Int,
    minimumLength: Long,
    hasMaximumLength: Int,
    maximumLength: Long,
    hasMinimumSelections: Int,
    minimumSelections: Long,
    hasMaximumSelections: Int,
    maximumSelections: Long,
    allowsOther: Int,
    isSecret: Int,
    outField: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outField)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedOptions = mutableListOf<AgentFormOption>()
    val optionStatus = copyElicitationHandles<CodexAgentCFormOptionSnapshot, AgentFormOption>(
        contextPointer,
        options,
        optionCount,
        copiedOptions,
    ) { it.value.copy() }
    if (optionStatus != CODEX_AGENT_STATUS_OK) return@abiStatus optionStatus
    var copiedDefault: AgentFormValue? = null
    val defaultStatus = copyOptionalFormValue(contextPointer, hasDefaultValue, defaultValue) {
        copiedDefault = it
    }
    if (defaultStatus != CODEX_AGENT_STATUS_OK) return@abiStatus defaultStatus
    val field = AgentFormField(
        name = name.readElicitationRequiredUtf8(),
        title = title.readElicitationRequiredUtf8(),
        description = description.readElicitationOptionalUtf8(hasDescription),
        isRequired = elicitationBoolean(isRequired),
        type = formFieldTypeFromC(type),
        options = copiedOptions,
        defaultValue = copiedDefault,
        minimum = optionalElicitationDouble(hasMinimum, minimum),
        maximum = optionalElicitationDouble(hasMaximum, maximum),
        format = optionalFormStringFormat(hasFormat, format),
        minimumLength = optionalElicitationLong(hasMinimumLength, minimumLength),
        maximumLength = optionalElicitationLong(hasMaximumLength, maximumLength),
        minimumSelections = optionalElicitationLong(hasMinimumSelections, minimumSelections),
        maximumSelections = optionalElicitationLong(hasMaximumSelections, maximumSelections),
        allowsOther = elicitationBoolean(allowsOther),
        isSecret = elicitationBoolean(isSecret),
    )
    installOutput(outField, createSnapshot(contextPointer, CodexAgentCFormFieldSnapshot(field.cAbiElicitationOwnedCopy())))
}

@CName("codex_agent_form_field_destroy")
public fun codexAgentFormFieldDestroy(
    context: COpaquePointer?,
    field: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCFormFieldSnapshot>(context, field)

@CName("codex_agent_form_field_name_copy")
public fun codexAgentFormFieldNameCopy(
    context: COpaquePointer?, field: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCFormFieldSnapshot>(context, field, buffer, capacity, outRequired) {
    it.value.name
}

@CName("codex_agent_form_field_title_copy")
public fun codexAgentFormFieldTitleCopy(
    context: COpaquePointer?, field: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCFormFieldSnapshot>(context, field, buffer, capacity, outRequired) {
    it.value.title
}

@CName("codex_agent_form_field_has_description")
public fun codexAgentFormFieldHasDescription(
    context: COpaquePointer?, field: COpaquePointer?, outHasDescription: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outHasDescription) {
    if (it.value.description == null) 0 else 1
}

@CName("codex_agent_form_field_description_copy")
public fun codexAgentFormFieldDescriptionCopy(
    context: COpaquePointer?, field: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalElicitationString<CodexAgentCFormFieldSnapshot>(context, field, buffer, capacity, outRequired) {
    it.value.description
}

@CName("codex_agent_form_field_is_required")
public fun codexAgentFormFieldIsRequired(
    context: COpaquePointer?, field: COpaquePointer?, outIsRequired: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outIsRequired) {
    if (it.value.isRequired) 1 else 0
}

@CName("codex_agent_form_field_type")
public fun codexAgentFormFieldType(
    context: COpaquePointer?, field: COpaquePointer?, outType: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outType) {
    it.value.type.toCValue()
}

@CName("codex_agent_form_field_options_count")
public fun codexAgentFormFieldOptionsCount(
    context: COpaquePointer?, field: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = elicitationCount<CodexAgentCFormFieldSnapshot>(context, field, outCount) { it.value.options.size }

@CName("codex_agent_form_field_option_at")
public fun codexAgentFormFieldOptionAt(
    context: COpaquePointer?, field: COpaquePointer?, index: ULong,
    outOption: CPointer<COpaquePointerVar>?,
): Int = elicitationChild<CodexAgentCFormFieldSnapshot>(context, field, index, outOption) {
    val value = it.value.options.elicitationItemAt(index) ?: return@elicitationChild null
    CodexAgentCFormOptionSnapshot(value.copy())
}

@CName("codex_agent_form_field_has_default_value")
public fun codexAgentFormFieldHasDefaultValue(
    context: COpaquePointer?, field: COpaquePointer?, outHasDefaultValue: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outHasDefaultValue) {
    if (it.value.defaultValue == null) 0 else 1
}

@CName("codex_agent_form_field_default_value")
public fun codexAgentFormFieldDefaultValue(
    context: COpaquePointer?, field: COpaquePointer?, outDefaultValue: CPointer<COpaquePointerVar>?,
): Int = elicitationOptionalChild<CodexAgentCFormFieldSnapshot>(context, field, outDefaultValue) {
    it.value.defaultValue?.let { value -> CodexAgentCFormValueSnapshot(value.cAbiElicitationOwnedCopy()) }
}

@CName("codex_agent_form_field_minimum")
public fun codexAgentFormFieldMinimum(
    context: COpaquePointer?, field: COpaquePointer?, outHasMinimum: CPointer<IntVar>?,
    outMinimum: CPointer<DoubleVar>?,
): Int = optionalElicitationDouble<CodexAgentCFormFieldSnapshot>(context, field, outHasMinimum, outMinimum) {
    it.value.minimum
}

@CName("codex_agent_form_field_maximum")
public fun codexAgentFormFieldMaximum(
    context: COpaquePointer?, field: COpaquePointer?, outHasMaximum: CPointer<IntVar>?,
    outMaximum: CPointer<DoubleVar>?,
): Int = optionalElicitationDouble<CodexAgentCFormFieldSnapshot>(context, field, outHasMaximum, outMaximum) {
    it.value.maximum
}

@CName("codex_agent_form_field_format")
public fun codexAgentFormFieldFormat(
    context: COpaquePointer?, field: COpaquePointer?, outHasFormat: CPointer<IntVar>?,
    outFormat: CPointer<IntVar>?,
): Int = optionalElicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outHasFormat, outFormat) {
    it.value.format?.toCValue()
}

@CName("codex_agent_form_field_minimum_length")
public fun codexAgentFormFieldMinimumLength(
    context: COpaquePointer?, field: COpaquePointer?, outHasValue: CPointer<IntVar>?, outValue: CPointer<LongVar>?,
): Int = optionalElicitationLong<CodexAgentCFormFieldSnapshot>(context, field, outHasValue, outValue) {
    it.value.minimumLength
}

@CName("codex_agent_form_field_maximum_length")
public fun codexAgentFormFieldMaximumLength(
    context: COpaquePointer?, field: COpaquePointer?, outHasValue: CPointer<IntVar>?, outValue: CPointer<LongVar>?,
): Int = optionalElicitationLong<CodexAgentCFormFieldSnapshot>(context, field, outHasValue, outValue) {
    it.value.maximumLength
}

@CName("codex_agent_form_field_minimum_selections")
public fun codexAgentFormFieldMinimumSelections(
    context: COpaquePointer?, field: COpaquePointer?, outHasValue: CPointer<IntVar>?, outValue: CPointer<LongVar>?,
): Int = optionalElicitationLong<CodexAgentCFormFieldSnapshot>(context, field, outHasValue, outValue) {
    it.value.minimumSelections
}

@CName("codex_agent_form_field_maximum_selections")
public fun codexAgentFormFieldMaximumSelections(
    context: COpaquePointer?, field: COpaquePointer?, outHasValue: CPointer<IntVar>?, outValue: CPointer<LongVar>?,
): Int = optionalElicitationLong<CodexAgentCFormFieldSnapshot>(context, field, outHasValue, outValue) {
    it.value.maximumSelections
}

@CName("codex_agent_form_field_allows_other")
public fun codexAgentFormFieldAllowsOther(
    context: COpaquePointer?, field: COpaquePointer?, outAllowsOther: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outAllowsOther) {
    if (it.value.allowsOther) 1 else 0
}

@CName("codex_agent_form_field_is_secret")
public fun codexAgentFormFieldIsSecret(
    context: COpaquePointer?, field: COpaquePointer?, outIsSecret: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCFormFieldSnapshot>(context, field, outIsSecret) {
    if (it.value.isSecret) 1 else 0
}

@CName("codex_agent_elicitation_create")
public fun codexAgentElicitationCreate(
    context: COpaquePointer?,
    requestId: CPointer<codex_agent_string_view>?,
    serverName: CPointer<codex_agent_string_view>?,
    conversationId: COpaquePointer?,
    message: CPointer<codex_agent_string_view>?,
    hasForm: Int,
    form: CPointer<COpaquePointerVar>?,
    formCount: ULong,
    hasUrl: Int,
    url: CPointer<codex_agent_string_view>?,
    outElicitation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outElicitation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireElicitationFlag(hasForm)
    val copiedForm = if (hasForm == 0) {
        require(form == null && formCount == 0UL)
        null
    } else {
        val output = mutableListOf<AgentFormField>()
        val status = copyElicitationHandles<CodexAgentCFormFieldSnapshot, AgentFormField>(
            contextPointer,
            form,
            formCount,
            output,
        ) { it.value.cAbiElicitationOwnedCopy() }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
        output
    }
    var copiedId: ConversationId? = null
    val idStatus = withPayload<CodexAgentCConversationIdSnapshot>(
        contextPointer,
        conversationId,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copiedId = ConversationId(it.value.value)
        CODEX_AGENT_STATUS_OK
    }
    if (idStatus != CODEX_AGENT_STATUS_OK) return@abiStatus idStatus
    val value = AgentElicitation(
        requestId = requestId.readElicitationRequiredUtf8(),
        serverName = serverName.readElicitationRequiredUtf8(),
        conversationId = checkNotNull(copiedId),
        message = message.readElicitationRequiredUtf8(),
        form = copiedForm,
        url = url.readElicitationOptionalUtf8(hasUrl),
    )
    installOutput(outElicitation, createSnapshot(contextPointer, CodexAgentCElicitationSnapshot(value)))
}

@CName("codex_agent_elicitation_destroy")
public fun codexAgentElicitationDestroy(
    context: COpaquePointer?, elicitation: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCElicitationSnapshot>(context, elicitation)

@CName("codex_agent_elicitation_request_id_copy")
public fun codexAgentElicitationRequestIdCopy(
    context: COpaquePointer?, elicitation: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCElicitationSnapshot>(context, elicitation, buffer, capacity, outRequired) {
    it.value.requestId
}

@CName("codex_agent_elicitation_server_name_copy")
public fun codexAgentElicitationServerNameCopy(
    context: COpaquePointer?, elicitation: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCElicitationSnapshot>(context, elicitation, buffer, capacity, outRequired) {
    it.value.serverName
}

@CName("codex_agent_elicitation_conversation_id")
public fun codexAgentElicitationConversationId(
    context: COpaquePointer?, elicitation: COpaquePointer?, outConversationId: CPointer<COpaquePointerVar>?,
): Int = elicitationOptionalChild<CodexAgentCElicitationSnapshot>(context, elicitation, outConversationId) {
    CodexAgentCConversationIdSnapshot(ConversationId(it.value.conversationId.value))
}

@CName("codex_agent_elicitation_message_copy")
public fun codexAgentElicitationMessageCopy(
    context: COpaquePointer?, elicitation: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCElicitationSnapshot>(context, elicitation, buffer, capacity, outRequired) {
    it.value.message
}

@CName("codex_agent_elicitation_has_form")
public fun codexAgentElicitationHasForm(
    context: COpaquePointer?, elicitation: COpaquePointer?, outHasForm: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCElicitationSnapshot>(context, elicitation, outHasForm) {
    if (it.value.form == null) 0 else 1
}

@CName("codex_agent_elicitation_form_count")
public fun codexAgentElicitationFormCount(
    context: COpaquePointer?, elicitation: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationSnapshot>(context, elicitation, CodexAgentCHandleKind.SNAPSHOT) {
        val values = it.value.form ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        outCount.pointed.value = values.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_elicitation_form_at")
public fun codexAgentElicitationFormAt(
    context: COpaquePointer?, elicitation: COpaquePointer?, index: ULong,
    outField: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outField)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationSnapshot>(contextPointer, elicitation, CodexAgentCHandleKind.SNAPSHOT) {
        val values = it.value.form ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        val selected = values.elicitationItemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outField,
            createSnapshot(contextPointer, CodexAgentCFormFieldSnapshot(selected.cAbiElicitationOwnedCopy())),
        )
    }
}

@CName("codex_agent_elicitation_has_url")
public fun codexAgentElicitationHasUrl(
    context: COpaquePointer?, elicitation: COpaquePointer?, outHasUrl: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCElicitationSnapshot>(context, elicitation, outHasUrl) {
    if (it.value.url == null) 0 else 1
}

@CName("codex_agent_elicitation_url_copy")
public fun codexAgentElicitationUrlCopy(
    context: COpaquePointer?, elicitation: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalElicitationString<CodexAgentCElicitationSnapshot>(
    context,
    elicitation,
    buffer,
    capacity,
    outRequired,
) { it.value.url }

@CName("codex_agent_elicitation_response_create")
public fun codexAgentElicitationResponseCreate(
    context: COpaquePointer?,
    action: Int,
    contentKeys: CPointer<codex_agent_string_view>?,
    contentValues: CPointer<COpaquePointerVar>?,
    contentCount: ULong,
    outResponse: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outResponse)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val size = checkedElicitationSize(contentCount)
    val keys = exactElicitationArray(contentKeys, size)
    val values = exactElicitationArray(contentValues, size)
    val copied = linkedMapOf<String, AgentFormValue>()
    repeat(size) { index ->
        val key = checkNotNull(keys)[index].readUtf8()
        if (copied.containsKey(key)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
        val status = withPayload<CodexAgentCFormValueSnapshot>(
            contextPointer,
            checkNotNull(values)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copied[key] = it.value.cAbiElicitationOwnedCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
    }
    val response = AgentElicitationResponse(elicitationActionFromC(action), copied)
    installOutput(
        outResponse,
        createSnapshot(contextPointer, CodexAgentCElicitationResponseSnapshot(response.cAbiElicitationOwnedCopy())),
    )
}

@CName("codex_agent_elicitation_response_destroy")
public fun codexAgentElicitationResponseDestroy(
    context: COpaquePointer?, response: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCElicitationResponseSnapshot>(context, response)

@CName("codex_agent_elicitation_response_action")
public fun codexAgentElicitationResponseAction(
    context: COpaquePointer?, response: COpaquePointer?, outAction: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCElicitationResponseSnapshot>(context, response, outAction) {
    it.value.action.toCValue()
}

@CName("codex_agent_elicitation_response_content_count")
public fun codexAgentElicitationResponseContentCount(
    context: COpaquePointer?, response: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = elicitationCount<CodexAgentCElicitationResponseSnapshot>(context, response, outCount) {
    it.value.content.size
}

@CName("codex_agent_elicitation_response_content_value")
public fun codexAgentElicitationResponseContentValue(
    context: COpaquePointer?, response: COpaquePointer?, key: CPointer<codex_agent_string_view>?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedKey = key.readElicitationRequiredUtf8()
    withPayload<CodexAgentCElicitationResponseSnapshot>(
        contextPointer,
        response,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val selected = it.value.content[copiedKey] ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outValue,
            createSnapshot(contextPointer, CodexAgentCFormValueSnapshot(selected.cAbiElicitationOwnedCopy())),
        )
    }
}

@CName("codex_agent_pending_elicitation_create")
public fun codexAgentPendingElicitationCreate(
    context: COpaquePointer?, elicitation: COpaquePointer?,
    outPendingElicitation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outPendingElicitation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationSnapshot>(contextPointer, elicitation, CodexAgentCHandleKind.SNAPSHOT) {
        val value = AgentPendingElicitation(it.value.cAbiElicitationOwnedCopy())
        installOutput(
            outPendingElicitation,
            createSnapshot(contextPointer, CodexAgentCPendingElicitationSnapshot(value)),
        )
    }
}

@CName("codex_agent_pending_elicitation_destroy")
public fun codexAgentPendingElicitationDestroy(
    context: COpaquePointer?, pendingElicitation: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCPendingElicitationSnapshot>(context, pendingElicitation)

@CName("codex_agent_pending_elicitation_elicitation")
public fun codexAgentPendingElicitationElicitation(
    context: COpaquePointer?, pendingElicitation: COpaquePointer?,
    outElicitation: CPointer<COpaquePointerVar>?,
): Int = elicitationOptionalChild<CodexAgentCPendingElicitationSnapshot>(
    context,
    pendingElicitation,
    outElicitation,
) { CodexAgentCElicitationSnapshot(it.value.elicitation.cAbiElicitationOwnedCopy()) }

@CName("codex_agent_pending_elicitation_request_id_copy")
public fun codexAgentPendingElicitationRequestIdCopy(
    context: COpaquePointer?, pendingElicitation: COpaquePointer?, buffer: CPointer<UByteVar>?, capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyElicitationString<CodexAgentCPendingElicitationSnapshot>(
    context,
    pendingElicitation,
    buffer,
    capacity,
    outRequired,
) { it.value.requestId }

@CName("codex_agent_pending_elicitation_conversation_id")
public fun codexAgentPendingElicitationConversationId(
    context: COpaquePointer?, pendingElicitation: COpaquePointer?,
    outConversationId: CPointer<COpaquePointerVar>?,
): Int = elicitationOptionalChild<CodexAgentCPendingElicitationSnapshot>(
    context,
    pendingElicitation,
    outConversationId,
) { CodexAgentCConversationIdSnapshot(ConversationId(it.value.conversationId.value)) }

@CName("codex_agent_pending_interaction_from_approval")
public fun codexAgentPendingInteractionFromApproval(
    context: COpaquePointer?, approval: COpaquePointer?, outInteraction: CPointer<COpaquePointerVar>?,
): Int = pendingInteractionFrom<CodexAgentCPendingApprovalSnapshot>(context, approval, outInteraction) {
    it.value to it.owner
}

@CName("codex_agent_pending_interaction_from_elicitation")
public fun codexAgentPendingInteractionFromElicitation(
    context: COpaquePointer?, pendingElicitation: COpaquePointer?, outInteraction: CPointer<COpaquePointerVar>?,
): Int = pendingInteractionFrom<CodexAgentCPendingElicitationSnapshot>(
    context,
    pendingElicitation,
    outInteraction,
) { it.value to it.owner }

@CName("codex_agent_pending_interaction_destroy")
public fun codexAgentPendingInteractionDestroy(
    context: COpaquePointer?, interaction: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCPendingInteractionSnapshot>(context, interaction)

@CName("codex_agent_pending_interaction_kind")
public fun codexAgentPendingInteractionKind(
    context: COpaquePointer?, interaction: COpaquePointer?, outKind: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCPendingInteractionSnapshot>(context, interaction, outKind) {
    when (it.value) {
        is AgentPendingApproval -> 0
        is AgentPendingElicitation -> 1
    }
}

@CName("codex_agent_pending_interaction_approval")
public fun codexAgentPendingInteractionApproval(
    context: COpaquePointer?, interaction: COpaquePointer?, outApproval: CPointer<COpaquePointerVar>?,
): Int = pendingInteractionDowncast(context, interaction, outApproval) { value, owner ->
    val approval = value as? AgentPendingApproval ?: return@pendingInteractionDowncast null
    CodexAgentCPendingApprovalSnapshot(
        if (owner == null) {
            approval.copy(conversationId = ConversationId(approval.conversationId.value))
        } else {
            approval
        },
        owner,
    )
}

@CName("codex_agent_pending_interaction_elicitation")
public fun codexAgentPendingInteractionElicitation(
    context: COpaquePointer?, interaction: COpaquePointer?, outElicitation: CPointer<COpaquePointerVar>?,
): Int = pendingInteractionDowncast(context, interaction, outElicitation) { value, owner ->
    val elicitation = value as? AgentPendingElicitation ?: return@pendingInteractionDowncast null
    CodexAgentCPendingElicitationSnapshot(
        if (owner == null) {
            AgentPendingElicitation(elicitation.elicitation.cAbiElicitationOwnedCopy())
        } else {
            elicitation
        },
        owner,
    )
}

@CName("codex_agent_interaction_state_create")
public fun codexAgentInteractionStateCreate(
    context: COpaquePointer?,
    pending: CPointer<COpaquePointerVar>?,
    pendingCount: ULong,
    resolvingRequestIds: CPointer<codex_agent_string_view>?,
    resolvingRequestIdCount: ULong,
    hasFailure: Int,
    failure: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedPending = mutableListOf<AgentPendingInteraction>()
    val pendingStatus = copyElicitationHandles<CodexAgentCPendingInteractionSnapshot, AgentPendingInteraction>(
        contextPointer,
        pending,
        pendingCount,
        copiedPending,
    ) { it.value.cAbiElicitationOwnedCopy() }
    if (pendingStatus != CODEX_AGENT_STATUS_OK) return@abiStatus pendingStatus
    val resolvingSize = checkedElicitationSize(resolvingRequestIdCount)
    val resolvingInput = exactElicitationArray(resolvingRequestIds, resolvingSize)
    val copiedResolving = buildSet {
        repeat(resolvingSize) { add(checkNotNull(resolvingInput)[it].readUtf8()) }
    }
    var copiedFailure: CodexFailure? = null
    val failureStatus = copyOptionalFailure(contextPointer, hasFailure, failure) { copiedFailure = it }
    if (failureStatus != CODEX_AGENT_STATUS_OK) return@abiStatus failureStatus
    val state = AgentInteractionState(copiedPending, copiedResolving, copiedFailure)
    installOutput(
        outState,
        createSnapshot(contextPointer, CodexAgentCInteractionStateSnapshot(state.cAbiElicitationOwnedCopy())),
    )
}

@CName("codex_agent_interaction_state_destroy")
public fun codexAgentInteractionStateDestroy(
    context: COpaquePointer?, state: CPointer<COpaquePointerVar>?,
): Int = destroyElicitationSnapshot<CodexAgentCInteractionStateSnapshot>(context, state)

@CName("codex_agent_interaction_state_pending_count")
public fun codexAgentInteractionStatePendingCount(
    context: COpaquePointer?, state: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = elicitationCount<CodexAgentCInteractionStateSnapshot>(context, state, outCount) { it.value.pending.size }

@CName("codex_agent_interaction_state_pending_at")
public fun codexAgentInteractionStatePendingAt(
    context: COpaquePointer?, state: COpaquePointer?, index: ULong,
    outInteraction: CPointer<COpaquePointerVar>?,
): Int = elicitationChild<CodexAgentCInteractionStateSnapshot>(context, state, index, outInteraction) {
    val value = it.value.pending.elicitationItemAt(index) ?: return@elicitationChild null
    CodexAgentCPendingInteractionSnapshot(
        if (it.owner == null) value.cAbiElicitationOwnedCopy() else value,
        it.owner,
    )
}

@CName("codex_agent_interaction_state_resolving_request_ids_count")
public fun codexAgentInteractionStateResolvingRequestIdsCount(
    context: COpaquePointer?, state: COpaquePointer?, outCount: CPointer<ULongVar>?,
): Int = elicitationCount<CodexAgentCInteractionStateSnapshot>(context, state, outCount) {
    it.value.resolvingRequestIds.size
}

@CName("codex_agent_interaction_state_resolving_request_ids_contains")
public fun codexAgentInteractionStateResolvingRequestIdsContains(
    context: COpaquePointer?, state: COpaquePointer?, requestId: CPointer<codex_agent_string_view>?,
    outContains: CPointer<IntVar>?,
): Int = abiStatus {
    if (outContains == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copied = requestId.readElicitationRequiredUtf8()
    withPayload<CodexAgentCInteractionStateSnapshot>(context, state, CodexAgentCHandleKind.SNAPSHOT) {
        outContains.pointed.value = if (copied in it.value.resolvingRequestIds) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_interaction_state_has_failure")
public fun codexAgentInteractionStateHasFailure(
    context: COpaquePointer?, state: COpaquePointer?, outHasFailure: CPointer<IntVar>?,
): Int = elicitationInt<CodexAgentCInteractionStateSnapshot>(context, state, outHasFailure) {
    if (it.value.failure == null) 0 else 1
}

@CName("codex_agent_interaction_state_failure")
public fun codexAgentInteractionStateFailure(
    context: COpaquePointer?, state: COpaquePointer?, outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCInteractionStateSnapshot>(contextPointer, state, CodexAgentCHandleKind.SNAPSHOT) {
        val failure = it.value.failure ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(outFailure, createFailure(contextPointer, failure.copy()))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> formValueFrom(
    context: COpaquePointer?,
    concrete: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> AgentFormValue,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, concrete, CodexAgentCHandleKind.SNAPSHOT) {
        installOutput(
            output,
            createSnapshot(
                contextPointer,
                CodexAgentCFormValueSnapshot(select(it).cAbiElicitationOwnedCopy()),
            ),
        )
    }
}

private fun formValueDowncast(
    context: COpaquePointer?,
    value: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    snapshot: (AgentFormValue) -> CodexAgentCSnapshot?,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormValueSnapshot>(contextPointer, value, CodexAgentCHandleKind.SNAPSHOT) {
        val selected = snapshot(it.value) ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(output, createSnapshot(contextPointer, selected))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> pendingInteractionFrom(
    context: COpaquePointer?,
    concrete: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> Pair<AgentPendingInteraction, CodexInteractions?>,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, concrete, CodexAgentCHandleKind.SNAPSHOT) {
        val (selected, owner) = select(it)
        installOutput(
            output,
            createSnapshot(
                contextPointer,
                CodexAgentCPendingInteractionSnapshot(
                    if (owner == null) selected.cAbiElicitationOwnedCopy() else selected,
                    owner,
                ),
            ),
        )
    }
}

private fun pendingInteractionDowncast(
    context: COpaquePointer?,
    interaction: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    snapshot: (AgentPendingInteraction, CodexInteractions?) -> CodexAgentCSnapshot?,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPendingInteractionSnapshot>(
        contextPointer,
        interaction,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val selected = snapshot(it.value, it.owner)
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(output, createSnapshot(contextPointer, selected))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> destroyElicitationSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT) else status
}

private inline fun <reified T : CodexAgentCSnapshot> elicitationInt(
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

private inline fun <reified T : CodexAgentCSnapshot> elicitationCount(
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

private inline fun <reified T : CodexAgentCSnapshot> copyElicitationString(
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

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalElicitationString(
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

private inline fun <reified T : CodexAgentCSnapshot> elicitationChild(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> CodexAgentCSnapshot?,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val snapshot = select(it) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(output, createSnapshot(contextPointer, snapshot))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> elicitationOptionalChild(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    crossinline select: (T) -> CodexAgentCSnapshot?,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(contextPointer, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val snapshot = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(output, createSnapshot(contextPointer, snapshot))
    }
}

private inline fun <reified T : CodexAgentCSnapshot> optionalElicitationInt(
    context: COpaquePointer?, handle: COpaquePointer?, outHasValue: CPointer<IntVar>?,
    outValue: CPointer<IntVar>?, crossinline select: (T) -> Int?,
): Int = abiStatus {
    if (outHasValue == null || outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it)
        outHasValue.pointed.value = if (value == null) 0 else 1
        outValue.pointed.value = value ?: 0
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> optionalElicitationDouble(
    context: COpaquePointer?, handle: COpaquePointer?, outHasValue: CPointer<IntVar>?,
    outValue: CPointer<DoubleVar>?, crossinline select: (T) -> Double?,
): Int = abiStatus {
    if (outHasValue == null || outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it)
        outHasValue.pointed.value = if (value == null) 0 else 1
        outValue.pointed.value = value ?: 0.0
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> optionalElicitationLong(
    context: COpaquePointer?, handle: COpaquePointer?, outHasValue: CPointer<IntVar>?,
    outValue: CPointer<LongVar>?, crossinline select: (T) -> Long?,
): Int = abiStatus {
    if (outHasValue == null || outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it)
        outHasValue.pointed.value = if (value == null) 0 else 1
        outValue.pointed.value = value ?: 0L
        CODEX_AGENT_STATUS_OK
    }
}

private fun copyOptionalFormValue(
    context: COpaquePointer,
    hasValue: Int,
    value: COpaquePointer?,
    install: (AgentFormValue?) -> Unit,
): Int {
    requireElicitationFlag(hasValue)
    if (hasValue == 0) {
        if (value != null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        install(null)
        return CODEX_AGENT_STATUS_OK
    }
    if (value == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    return withPayload<CodexAgentCFormValueSnapshot>(context, value, CodexAgentCHandleKind.SNAPSHOT) {
        install(it.value.cAbiElicitationOwnedCopy())
        CODEX_AGENT_STATUS_OK
    }
}

private fun copyOptionalFailure(
    context: COpaquePointer,
    hasValue: Int,
    value: COpaquePointer?,
    install: (CodexFailure?) -> Unit,
): Int {
    requireElicitationFlag(hasValue)
    if (hasValue == 0) {
        if (value != null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        install(null)
        return CODEX_AGENT_STATUS_OK
    }
    if (value == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    return withPayload<CodexFailure>(context, value, CodexAgentCHandleKind.FAILURE) {
        install(it.copy())
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot, V> copyElicitationHandles(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<V>,
    crossinline copy: (T) -> V,
): Int {
    val size = checkedElicitationSize(count)
    val input = exactElicitationArray(values, size)
    repeat(size) { index ->
        val status = withPayload<T>(context, checkNotNull(input)[index], CodexAgentCHandleKind.SNAPSHOT) {
            output += copy(it)
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return status
    }
    return CODEX_AGENT_STATUS_OK
}

private fun CPointer<codex_agent_string_view>?.readElicitationRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readElicitationOptionalUtf8(hasValue: Int): String? {
    requireElicitationFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0UL)
        return null
    }
    return view.readUtf8()
}

private fun requireElicitationFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun elicitationBoolean(value: Int): Boolean {
    requireElicitationFlag(value)
    return value == 1
}

private fun optionalElicitationDouble(hasValue: Int, value: Double): Double? {
    requireElicitationFlag(hasValue)
    if (hasValue == 0) require(value == 0.0)
    return if (hasValue == 0) null else value
}

private fun optionalElicitationLong(hasValue: Int, value: Long): Long? {
    requireElicitationFlag(hasValue)
    if (hasValue == 0) require(value == 0L)
    return if (hasValue == 0) null else value
}

private fun optionalFormStringFormat(hasValue: Int, value: Int): AgentFormStringFormat? {
    requireElicitationFlag(hasValue)
    if (hasValue == 0) {
        require(value == 0)
        return null
    }
    return formStringFormatFromC(value)
}

private fun formFieldTypeFromC(value: Int): AgentFormFieldType = when (value) {
    0 -> AgentFormFieldType.STRING
    1 -> AgentFormFieldType.NUMBER
    2 -> AgentFormFieldType.INTEGER
    3 -> AgentFormFieldType.BOOLEAN
    4 -> AgentFormFieldType.SINGLE_SELECT
    5 -> AgentFormFieldType.MULTI_SELECT
    else -> throw IllegalArgumentException("Unknown form field type")
}

private fun AgentFormFieldType.toCValue(): Int = when (this) {
    AgentFormFieldType.STRING -> 0
    AgentFormFieldType.NUMBER -> 1
    AgentFormFieldType.INTEGER -> 2
    AgentFormFieldType.BOOLEAN -> 3
    AgentFormFieldType.SINGLE_SELECT -> 4
    AgentFormFieldType.MULTI_SELECT -> 5
}

private fun formStringFormatFromC(value: Int): AgentFormStringFormat = when (value) {
    0 -> AgentFormStringFormat.EMAIL
    1 -> AgentFormStringFormat.URI
    2 -> AgentFormStringFormat.DATE
    3 -> AgentFormStringFormat.DATE_TIME
    else -> throw IllegalArgumentException("Unknown form string format")
}

private fun AgentFormStringFormat.toCValue(): Int = when (this) {
    AgentFormStringFormat.EMAIL -> 0
    AgentFormStringFormat.URI -> 1
    AgentFormStringFormat.DATE -> 2
    AgentFormStringFormat.DATE_TIME -> 3
}

private fun elicitationActionFromC(value: Int): AgentElicitationAction = when (value) {
    0 -> AgentElicitationAction.ACCEPT
    1 -> AgentElicitationAction.DECLINE
    2 -> AgentElicitationAction.CANCEL
    else -> throw IllegalArgumentException("Unknown elicitation action")
}

private fun AgentElicitationAction.toCValue(): Int = when (this) {
    AgentElicitationAction.ACCEPT -> 0
    AgentElicitationAction.DECLINE -> 1
    AgentElicitationAction.CANCEL -> 2
}

private fun checkedElicitationSize(count: ULong): Int {
    require(count <= Int.MAX_VALUE.toULong())
    return count.toInt()
}

private fun <T : kotlinx.cinterop.CPointed> exactElicitationArray(pointer: CPointer<T>?, size: Int): CPointer<T>? {
    require((size == 0) == (pointer == null))
    return pointer
}

private fun <T> List<T>.elicitationItemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())
