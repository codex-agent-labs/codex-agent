@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentElicitationResponse
import io.github.codex_agent_labs.codexagent.agent.AgentElicitationValidation
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

internal data class CodexAgentCFormContentSnapshot(
    val value: Map<String, AgentFormValue>,
) : CodexAgentCSnapshot

@CName("codex_agent_form_content_create")
public fun codexAgentFormContentCreate(
    context: COpaquePointer?,
    keys: CPointer<codex_agent_string_view>?,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    outContent: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outContent)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val size = checkedBehaviorSize(count)
    val keyInput = exactBehaviorArray(keys, size)
    val valueInput = exactBehaviorArray(values, size)
    val copied = linkedMapOf<String, AgentFormValue>()
    repeat(size) { index ->
        val key = checkNotNull(keyInput)[index].readUtf8()
        val status = withPayload<CodexAgentCFormValueSnapshot>(
            contextPointer,
            checkNotNull(valueInput)[index],
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copied[key] = it.value.behaviorOwnedCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
    }
    installOutput(
        outContent,
        createSnapshot(contextPointer, CodexAgentCFormContentSnapshot(copied)),
    )
}

@CName("codex_agent_form_content_destroy")
public fun codexAgentFormContentDestroy(
    context: COpaquePointer?,
    content: CPointer<COpaquePointerVar>?,
): Int = destroyBehaviorSnapshot<CodexAgentCFormContentSnapshot>(context, content)

@CName("codex_agent_form_content_count")
public fun codexAgentFormContentCount(
    context: COpaquePointer?,
    content: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = abiStatus {
    if (outCount == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormContentSnapshot>(context, content, CodexAgentCHandleKind.SNAPSHOT) {
        outCount.pointed.value = it.value.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_form_content_key_copy")
public fun codexAgentFormContentKeyCopy(
    context: COpaquePointer?,
    content: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    withPayload<CodexAgentCFormContentSnapshot>(context, content, CodexAgentCHandleKind.SNAPSHOT) {
        val key = it.value.keys.behaviorItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(key, buffer, capacity, outRequired)
    }
}

@CName("codex_agent_form_content_value_at")
public fun codexAgentFormContentValueAt(
    context: COpaquePointer?,
    content: COpaquePointer?,
    key: CPointer<codex_agent_string_view>?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedKey = requireNotNull(key).pointed.readUtf8()
    withPayload<CodexAgentCFormContentSnapshot>(
        contextPointer,
        content,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val selected = it.value[copiedKey] ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outValue,
            createSnapshot(contextPointer, CodexAgentCFormValueSnapshot(selected.behaviorOwnedCopy())),
        )
    }
}

@CName("codex_agent_form_field_accepts")
public fun codexAgentFormFieldAccepts(
    context: COpaquePointer?,
    field: COpaquePointer?,
    value: COpaquePointer?,
    outAccepts: CPointer<IntVar>?,
): Int = abiStatus {
    if (outAccepts == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormFieldSnapshot>(context, field, CodexAgentCHandleKind.SNAPSHOT) { fieldSnapshot ->
        if (value == null) {
            outAccepts.pointed.value = fieldSnapshot.value.accepts(null).toCBehaviorBoolean()
            return@withPayload CODEX_AGENT_STATUS_OK
        }
        withPayload<CodexAgentCFormValueSnapshot>(context, value, CodexAgentCHandleKind.SNAPSHOT) {
            outAccepts.pointed.value = fieldSnapshot.value.accepts(it.value).toCBehaviorBoolean()
            CODEX_AGENT_STATUS_OK
        }
    }
}

@CName("codex_agent_elicitation_initial_values")
public fun codexAgentElicitationInitialValues(
    context: COpaquePointer?,
    elicitation: COpaquePointer?,
    outContent: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outContent)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationSnapshot>(
        contextPointer,
        elicitation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outContent,
            createSnapshot(
                contextPointer,
                CodexAgentCFormContentSnapshot(it.value.initialValues().behaviorOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_elicitation_validate")
public fun codexAgentElicitationValidate(
    context: COpaquePointer?,
    elicitation: COpaquePointer?,
    content: COpaquePointer?,
    outValidation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValidation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withElicitationAndContent(contextPointer, elicitation, content) { elicitationSnapshot, contentSnapshot ->
        val validation = elicitationSnapshot.value.validate(contentSnapshot.value)
        installOutput(
            outValidation,
            createSnapshot(contextPointer, CodexAgentCElicitationValidationSnapshot(validation.behaviorOwnedCopy())),
        )
    }
}

@CName("codex_agent_elicitation_accept")
public fun codexAgentElicitationAccept(
    context: COpaquePointer?,
    elicitation: COpaquePointer?,
    content: COpaquePointer?,
    outResponse: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outResponse)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withElicitationAndContent(contextPointer, elicitation, content) { elicitationSnapshot, contentSnapshot ->
        val response = elicitationSnapshot.value.accept(contentSnapshot.value)
        installOutput(
            outResponse,
            createSnapshot(contextPointer, CodexAgentCElicitationResponseSnapshot(response.behaviorOwnedCopy())),
        )
    }
}

@CName("codex_agent_elicitation_accepts")
public fun codexAgentElicitationAccepts(
    context: COpaquePointer?,
    elicitation: COpaquePointer?,
    response: COpaquePointer?,
    outAccepts: CPointer<IntVar>?,
): Int = abiStatus {
    if (outAccepts == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCElicitationSnapshot>(
        context,
        elicitation,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { elicitationSnapshot ->
        withPayload<CodexAgentCElicitationResponseSnapshot>(
            context,
            response,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            outAccepts.pointed.value = elicitationSnapshot.value.accepts(it.value).toCBehaviorBoolean()
            CODEX_AGENT_STATUS_OK
        }
    }
}

@CName("codex_agent_elicitation_response_decline")
public fun codexAgentElicitationResponseDecline(
    context: COpaquePointer?,
    outResponse: CPointer<COpaquePointerVar>?,
): Int = createBehaviorResponse(context, outResponse, AgentElicitationResponse.decline())

@CName("codex_agent_elicitation_response_cancel")
public fun codexAgentElicitationResponseCancel(
    context: COpaquePointer?,
    outResponse: CPointer<COpaquePointerVar>?,
): Int = createBehaviorResponse(context, outResponse, AgentElicitationResponse.cancel())

private inline fun withElicitationAndContent(
    context: COpaquePointer,
    elicitation: COpaquePointer?,
    content: COpaquePointer?,
    crossinline block: (CodexAgentCElicitationSnapshot, CodexAgentCFormContentSnapshot) -> Int,
): Int = withPayload<CodexAgentCElicitationSnapshot>(
    context,
    elicitation,
    CodexAgentCHandleKind.SNAPSHOT,
) { elicitationSnapshot ->
    withPayload<CodexAgentCFormContentSnapshot>(context, content, CodexAgentCHandleKind.SNAPSHOT) {
        block(elicitationSnapshot, it)
    }
}

private fun createBehaviorResponse(
    context: COpaquePointer?,
    outResponse: CPointer<COpaquePointerVar>?,
    response: AgentElicitationResponse,
): Int = abiStatus {
    if (!validEmptyOutput(outResponse)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outResponse,
        createSnapshot(contextPointer, CodexAgentCElicitationResponseSnapshot(response.behaviorOwnedCopy())),
    )
}

private inline fun <reified T : CodexAgentCSnapshot> destroyBehaviorSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT) else status
}

private fun AgentFormValue.behaviorOwnedCopy(): AgentFormValue = when (this) {
    is AgentFormValue.BooleanValue -> copy()
    is AgentFormValue.Number -> copy()
    is AgentFormValue.Text -> copy()
    is AgentFormValue.TextList -> copy(value = value.toList())
}

private fun Map<String, AgentFormValue>.behaviorOwnedCopy(): Map<String, AgentFormValue> =
    entries.associateTo(linkedMapOf()) { it.key to it.value.behaviorOwnedCopy() }

private fun AgentElicitationResponse.behaviorOwnedCopy(): AgentElicitationResponse =
    copy(content = content.behaviorOwnedCopy())

private fun AgentElicitationValidation.behaviorOwnedCopy(): AgentElicitationValidation =
    AgentElicitationValidation(issues.map { it.copy() })

private fun Boolean.toCBehaviorBoolean(): Int = if (this) 1 else 0

private fun checkedBehaviorSize(count: ULong): Int {
    require(count <= Int.MAX_VALUE.toULong())
    return count.toInt()
}

private fun <T : kotlinx.cinterop.CPointed> exactBehaviorArray(pointer: CPointer<T>?, size: Int): CPointer<T>? {
    require((size == 0) == (pointer == null))
    return pointer
}

private fun <T> Collection<T>.behaviorItemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else elementAtOrNull(index.toInt())
