@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentFormValue
import io.github.codex_agent_labs.codexmobile.agent.AgentHookHandler
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.DoubleVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCFormBooleanValueSnapshot(
    val value: AgentFormValue.BooleanValue,
) : CodexAgentCSnapshot

internal data class CodexAgentCFormNumberValueSnapshot(
    val value: AgentFormValue.Number,
) : CodexAgentCSnapshot

internal data class CodexAgentCFormTextValueSnapshot(
    val value: AgentFormValue.Text,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookHandlerAgentSnapshot(
    val value: AgentHookHandler.Agent,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookHandlerCommandSnapshot(
    val value: AgentHookHandler.Command,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookHandlerMcpToolSnapshot(
    val value: AgentHookHandler.McpTool,
) : CodexAgentCSnapshot

internal data class CodexAgentCHookHandlerPromptSnapshot(
    val value: AgentHookHandler.Prompt,
) : CodexAgentCSnapshot

@CName("codex_agent_form_boolean_value_create")
public fun codexAgentFormBooleanValueCreate(
    context: COpaquePointer?,
    value: Int,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(value)
    installOutput(
        outValue,
        createSnapshot(
            context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            CodexAgentCFormBooleanValueSnapshot(AgentFormValue.BooleanValue(value == 1)),
        ),
    )
}

@CName("codex_agent_form_boolean_value_destroy")
public fun codexAgentFormBooleanValueDestroy(
    context: COpaquePointer?,
    value: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCFormBooleanValueSnapshot>(context, value)

@CName("codex_agent_form_boolean_value_value")
public fun codexAgentFormBooleanValueValue(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outValue: CPointer<IntVar>?,
): Int = abiStatus {
    if (outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormBooleanValueSnapshot>(context, value, CodexAgentCHandleKind.SNAPSHOT) {
        outValue.pointed.value = if (it.value.value) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_form_number_value_create")
public fun codexAgentFormNumberValueCreate(
    context: COpaquePointer?,
    value: Double,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outValue,
        createSnapshot(
            context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            CodexAgentCFormNumberValueSnapshot(AgentFormValue.Number(value)),
        ),
    )
}

@CName("codex_agent_form_number_value_destroy")
public fun codexAgentFormNumberValueDestroy(
    context: COpaquePointer?,
    value: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCFormNumberValueSnapshot>(context, value)

@CName("codex_agent_form_number_value_value")
public fun codexAgentFormNumberValueValue(
    context: COpaquePointer?,
    value: COpaquePointer?,
    outValue: CPointer<DoubleVar>?,
): Int = abiStatus {
    if (outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCFormNumberValueSnapshot>(context, value, CodexAgentCHandleKind.SNAPSHOT) {
        outValue.pointed.value = it.value.value
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_form_text_value_create")
public fun codexAgentFormTextValueCreate(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outValue: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outValue)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copied = value.readRequiredUtf8()
    installOutput(
        outValue,
        createSnapshot(
            context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            CodexAgentCFormTextValueSnapshot(AgentFormValue.Text(copied)),
        ),
    )
}

@CName("codex_agent_form_text_value_destroy")
public fun codexAgentFormTextValueDestroy(
    context: COpaquePointer?,
    value: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCFormTextValueSnapshot>(context, value)

@CName("codex_agent_form_text_value_value_copy")
public fun codexAgentFormTextValueValueCopy(
    context: COpaquePointer?,
    value: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFormHookString<CodexAgentCFormTextValueSnapshot>(
    context,
    value,
    buffer,
    capacity,
    outRequired,
) { it.value.value }

@CName("codex_agent_hook_handler_agent_acquire")
public fun codexAgentHookHandlerAgentAcquire(
    context: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = acquireFormHookSingleton(
    context,
    outHandler,
    CodexAgentCHookHandlerAgentSnapshot(AgentHookHandler.Agent),
)

@CName("codex_agent_hook_handler_agent_destroy")
public fun codexAgentHookHandlerAgentDestroy(
    context: COpaquePointer?,
    handler: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCHookHandlerAgentSnapshot>(context, handler)

@CName("codex_agent_hook_handler_command_create")
public fun codexAgentHookHandlerCommandCreate(
    context: COpaquePointer?,
    command: CPointer<codex_agent_string_view>?,
    isAsync: Int,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHandler)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBooleanFlag(isAsync)
    val copied = command.readRequiredUtf8()
    installOutput(
        outHandler,
        createSnapshot(
            context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            CodexAgentCHookHandlerCommandSnapshot(AgentHookHandler.Command(copied, isAsync == 1)),
        ),
    )
}

@CName("codex_agent_hook_handler_command_destroy")
public fun codexAgentHookHandlerCommandDestroy(
    context: COpaquePointer?,
    handler: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCHookHandlerCommandSnapshot>(context, handler)

@CName("codex_agent_hook_handler_command_command_copy")
public fun codexAgentHookHandlerCommandCommandCopy(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFormHookString<CodexAgentCHookHandlerCommandSnapshot>(
    context,
    handler,
    buffer,
    capacity,
    outRequired,
) { it.value.command }

@CName("codex_agent_hook_handler_command_is_async")
public fun codexAgentHookHandlerCommandIsAsync(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    outIsAsync: CPointer<IntVar>?,
): Int = abiStatus {
    if (outIsAsync == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCHookHandlerCommandSnapshot>(context, handler, CodexAgentCHandleKind.SNAPSHOT) {
        outIsAsync.pointed.value = if (it.value.isAsync) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_hook_handler_mcp_tool_create")
public fun codexAgentHookHandlerMcpToolCreate(
    context: COpaquePointer?,
    server: CPointer<codex_agent_string_view>?,
    tool: CPointer<codex_agent_string_view>?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outHandler)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedServer = server.readRequiredUtf8()
    val copiedTool = tool.readRequiredUtf8()
    installOutput(
        outHandler,
        createSnapshot(
            context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            CodexAgentCHookHandlerMcpToolSnapshot(AgentHookHandler.McpTool(copiedServer, copiedTool)),
        ),
    )
}

@CName("codex_agent_hook_handler_mcp_tool_destroy")
public fun codexAgentHookHandlerMcpToolDestroy(
    context: COpaquePointer?,
    handler: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCHookHandlerMcpToolSnapshot>(context, handler)

@CName("codex_agent_hook_handler_mcp_tool_server_copy")
public fun codexAgentHookHandlerMcpToolServerCopy(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFormHookString<CodexAgentCHookHandlerMcpToolSnapshot>(
    context,
    handler,
    buffer,
    capacity,
    outRequired,
) { it.value.server }

@CName("codex_agent_hook_handler_mcp_tool_tool_copy")
public fun codexAgentHookHandlerMcpToolToolCopy(
    context: COpaquePointer?,
    handler: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyFormHookString<CodexAgentCHookHandlerMcpToolSnapshot>(
    context,
    handler,
    buffer,
    capacity,
    outRequired,
) { it.value.tool }

@CName("codex_agent_hook_handler_prompt_acquire")
public fun codexAgentHookHandlerPromptAcquire(
    context: COpaquePointer?,
    outHandler: CPointer<COpaquePointerVar>?,
): Int = acquireFormHookSingleton(
    context,
    outHandler,
    CodexAgentCHookHandlerPromptSnapshot(AgentHookHandler.Prompt),
)

@CName("codex_agent_hook_handler_prompt_destroy")
public fun codexAgentHookHandlerPromptDestroy(
    context: COpaquePointer?,
    handler: CPointer<COpaquePointerVar>?,
): Int = destroyFormHookValue<CodexAgentCHookHandlerPromptSnapshot>(context, handler)

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun requireBooleanFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun acquireFormHookSingleton(
    context: COpaquePointer?,
    output: CPointer<COpaquePointerVar>?,
    snapshot: CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(output)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        output,
        createSnapshot(context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT, snapshot),
    )
}

private inline fun <reified T : CodexAgentCSnapshot> destroyFormHookValue(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val validation = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (validation != CODEX_AGENT_STATUS_OK) return@abiStatus validation
    releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
}

private inline fun <reified T : CodexAgentCSnapshot> copyFormHookString(
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
