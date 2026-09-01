@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentElicitationValidation
import io.github.codex_agent_labs.codexagent.agent.AgentElicitationValidationIssue
import io.github.codex_agent_labs.codexagent.agent.AgentFormValue
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.get
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCFormTextListValueSnapshot(
    val value: AgentFormValue.TextList,
) : CodexAgentCSnapshot

internal data class CodexAgentCElicitationValidationSnapshot(
    val value: AgentElicitationValidation,
) : CodexAgentCSnapshot

@CName("codex_agent_form_text_list_value_create")
public fun codexAgentFormTextListValueCreate(
    context: COpaquePointer?,
    values: CPointer<codex_agent_string_view>?,
    valueCount: ULong,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val size = checkedListSize(valueCount)
    val input = exactArray(values, size)
    val copied = List(size) { index -> checkNotNull(input)[index].readUtf8() }
    installOutput(
        outValue,
        createSnapshot(
            contextPointer,
            CodexAgentCFormTextListValueSnapshot(AgentFormValue.TextList(copied)),
        ),
    )
}

@CName("codex_agent_form_text_list_value_destroy")
public fun codexAgentFormTextListValueDestroy(
    context: COpaquePointer?,
    value: CPointer<COpaquePointerVar>?,
): Int = destroyListLeafValue<CodexAgentCFormTextListValueSnapshot>(context, value)

@CName("codex_agent_form_text_list_value_count")
public fun codexAgentFormTextListValueCount(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormTextListValueSnapshot>(
        context,
        value,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outCount.pointed.value = it.value.value.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_form_text_list_value_copy_at")
public fun codexAgentFormTextListValueCopyAt(
    context: COpaquePointer?,
    value: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCFormTextListValueSnapshot>(
        context,
        value,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        if (index >= it.value.value.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(it.value.value[index.toInt()], buffer, capacity, outRequired)
    }
}

@CName("codex_agent_elicitation_validation_create")
public fun codexAgentElicitationValidationCreate(
    context: COpaquePointer?,
    issues: CPointer<COpaquePointerVar>?,
    issueCount: ULong,
    outValidation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValidation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val size = checkedListSize(issueCount)
    val input = exactArray(issues, size)
    val copied = ArrayList<AgentElicitationValidationIssue>(size)
    repeat(size) { index ->
        var value: AgentElicitationValidationIssue? = null
        val status = withPayload<CodexAgentCElicitationValidationIssueSnapshot>(
            contextPointer,
            checkNotNull(input)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            value = AgentElicitationValidationIssue(it.value.fieldName, it.value.reason)
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
        copied += checkNotNull(value)
    }
    installOutput(
        outValidation,
        createSnapshot(
            contextPointer,
            CodexAgentCElicitationValidationSnapshot(AgentElicitationValidation(copied)),
        ),
    )
}

@CName("codex_agent_elicitation_validation_destroy")
public fun codexAgentElicitationValidationDestroy(
    context: COpaquePointer?,
    validation: CPointer<COpaquePointerVar>?,
): Int = destroyListLeafValue<CodexAgentCElicitationValidationSnapshot>(context, validation)

@CName("codex_agent_elicitation_validation_issue_count")
public fun codexAgentElicitationValidationIssueCount(
    context: COpaquePointer?,
    validation: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationValidationSnapshot>(
        context,
        validation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outCount.pointed.value = it.value.issues.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_elicitation_validation_issue_at")
public fun codexAgentElicitationValidationIssueAt(
    context: COpaquePointer?,
    validation: COpaquePointer?,
    index: ULong,
    outIssue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIssue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationValidationSnapshot>(
        contextPointer,
        validation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        if (index >= it.value.issues.size.toULong()) return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        val issue = it.value.issues[index.toInt()]
        installOutput(
            outIssue,
            createSnapshot(
                contextPointer,
                CodexAgentCElicitationValidationIssueSnapshot(
                    AgentElicitationValidationIssue(issue.fieldName, issue.reason),
                ),
            ),
        )
    }
}

@CName("codex_agent_elicitation_validation_is_valid")
public fun codexAgentElicitationValidationIsValid(
    context: COpaquePointer?,
    validation: COpaquePointer?,
    outIsValid: CPointer<IntVar>?,
): Int = abiStatus {
    if (outIsValid == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationValidationSnapshot>(
        context,
        validation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outIsValid.pointed.value = if (it.value.isValid) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

private fun checkedListSize(count: ULong): Int {
    require(count <= Int.MAX_VALUE.toULong())
    return count.toInt()
}

private fun <T : kotlinx.cinterop.CPointed> exactArray(pointer: CPointer<T>?, size: Int): CPointer<T>? {
    require((size == 0) == (pointer == null))
    return pointer
}

private inline fun <reified T : CodexAgentCSnapshot> destroyListLeafValue(
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
