@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentMcpEnvironmentVariable
import io.github.codex_agent_labs.codexagent.agent.AgentMcpTransport
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

internal data class CodexAgentCMcpTransportHttpSnapshot(
    val value: AgentMcpTransport.Http,
) : CodexAgentCSnapshot

internal data class CodexAgentCMcpTransportStdioSnapshot(
    val value: AgentMcpTransport.Stdio,
) : CodexAgentCSnapshot

@CName("codex_agent_mcp_transport_http_create")
public fun codexAgentMcpTransportHttpCreate(
    context: COpaquePointer?,
    url: CPointer<codex_agent_string_view>?,
    hasBearerTokenEnvironmentVariable: Int,
    bearerTokenEnvironmentVariable: CPointer<codex_agent_string_view>?,
    hasHeaders: Int,
    headerKeys: CPointer<codex_agent_string_view>?,
    headerValues: CPointer<codex_agent_string_view>?,
    headerCount: ULong,
    hasEnvironmentHeaders: Int,
    environmentHeaderKeys: CPointer<codex_agent_string_view>?,
    environmentHeaderValues: CPointer<codex_agent_string_view>?,
    environmentHeaderCount: ULong,
    hasHeadersHelper: Int,
    headersHelper: CPointer<codex_agent_string_view>?,
    outTransport: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTransport)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = AgentMcpTransport.Http(
        url = url.readTransportRequiredUtf8(),
        bearerTokenEnvironmentVariable = bearerTokenEnvironmentVariable.readTransportOptionalUtf8(
            hasBearerTokenEnvironmentVariable,
        ),
        headers = copyOptionalTransportStringMap(hasHeaders, headerKeys, headerValues, headerCount),
        environmentHeaders = copyOptionalTransportStringMap(
            hasEnvironmentHeaders,
            environmentHeaderKeys,
            environmentHeaderValues,
            environmentHeaderCount,
        ),
        headersHelper = headersHelper.readTransportOptionalUtf8(hasHeadersHelper),
    )
    installOutput(outTransport, createSnapshot(contextPointer, CodexAgentCMcpTransportHttpSnapshot(value)))
}

@CName("codex_agent_mcp_transport_http_destroy")
public fun codexAgentMcpTransportHttpDestroy(
    context: COpaquePointer?,
    transport: CPointer<COpaquePointerVar>?,
): Int = destroyMcpTransport<CodexAgentCMcpTransportHttpSnapshot>(context, transport)

@CName("codex_agent_mcp_transport_http_url_copy")
public fun codexAgentMcpTransportHttpUrlCopy(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportString<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    buffer,
    capacity,
    outRequired,
) { it.value.url }

@CName("codex_agent_mcp_transport_http_has_bearer_token_environment_variable")
public fun codexAgentMcpTransportHttpHasBearerTokenEnvironmentVariable(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outHasValue) {
    if (it.value.bearerTokenEnvironmentVariable == null) 0 else 1
}

@CName("codex_agent_mcp_transport_http_bearer_token_environment_variable_copy")
public fun codexAgentMcpTransportHttpBearerTokenEnvironmentVariableCopy(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalMcpTransportString<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    buffer,
    capacity,
    outRequired,
) { it.value.bearerTokenEnvironmentVariable }

@CName("codex_agent_mcp_transport_http_has_headers")
public fun codexAgentMcpTransportHttpHasHeaders(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasHeaders: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outHasHeaders) {
    if (it.value.headers == null) 0 else 1
}

@CName("codex_agent_mcp_transport_http_headers_count")
public fun codexAgentMcpTransportHttpHeadersCount(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpTransportMapCount<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outCount) {
    it.value.headers
}

@CName("codex_agent_mcp_transport_http_headers_key_copy_at")
public fun codexAgentMcpTransportHttpHeadersKeyCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.headers },
    Map.Entry<String, String>::key,
)

@CName("codex_agent_mcp_transport_http_headers_value_copy_at")
public fun codexAgentMcpTransportHttpHeadersValueCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.headers },
    Map.Entry<String, String>::value,
)

@CName("codex_agent_mcp_transport_http_has_environment_headers")
public fun codexAgentMcpTransportHttpHasEnvironmentHeaders(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasEnvironmentHeaders: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outHasEnvironmentHeaders) {
    if (it.value.environmentHeaders == null) 0 else 1
}

@CName("codex_agent_mcp_transport_http_environment_headers_count")
public fun codexAgentMcpTransportHttpEnvironmentHeadersCount(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpTransportMapCount<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outCount) {
    it.value.environmentHeaders
}

@CName("codex_agent_mcp_transport_http_environment_headers_key_copy_at")
public fun codexAgentMcpTransportHttpEnvironmentHeadersKeyCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.environmentHeaders },
    Map.Entry<String, String>::key,
)

@CName("codex_agent_mcp_transport_http_environment_headers_value_copy_at")
public fun codexAgentMcpTransportHttpEnvironmentHeadersValueCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.environmentHeaders },
    Map.Entry<String, String>::value,
)

@CName("codex_agent_mcp_transport_http_has_headers_helper")
public fun codexAgentMcpTransportHttpHasHeadersHelper(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasHeadersHelper: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportHttpSnapshot>(context, transport, outHasHeadersHelper) {
    if (it.value.headersHelper == null) 0 else 1
}

@CName("codex_agent_mcp_transport_http_headers_helper_copy")
public fun codexAgentMcpTransportHttpHeadersHelperCopy(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalMcpTransportString<CodexAgentCMcpTransportHttpSnapshot>(
    context,
    transport,
    buffer,
    capacity,
    outRequired,
) { it.value.headersHelper }

@CName("codex_agent_mcp_transport_stdio_create")
public fun codexAgentMcpTransportStdioCreate(
    context: COpaquePointer?,
    command: CPointer<codex_agent_string_view>?,
    arguments: CPointer<codex_agent_string_view>?,
    argumentCount: ULong,
    hasWorkingDirectory: Int,
    workingDirectory: CPointer<codex_agent_string_view>?,
    hasEnvironment: Int,
    environmentKeys: CPointer<codex_agent_string_view>?,
    environmentValues: CPointer<codex_agent_string_view>?,
    environmentCount: ULong,
    forwardedEnvironment: CPointer<COpaquePointerVar>?,
    forwardedEnvironmentCount: ULong,
    outTransport: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTransport)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedForwardedEnvironment = mutableListOf<AgentMcpEnvironmentVariable>()
    val copyStatus = copyMcpTransportEnvironmentVariables(
        contextPointer,
        forwardedEnvironment,
        forwardedEnvironmentCount,
        copiedForwardedEnvironment,
    )
    if (copyStatus != CODEX_AGENT_STATUS_OK) return@abiStatus copyStatus
    val value = AgentMcpTransport.Stdio(
        command = command.readTransportRequiredUtf8(),
        arguments = copyMcpTransportStrings(arguments, argumentCount),
        workingDirectory = workingDirectory.readTransportOptionalUtf8(hasWorkingDirectory),
        environment = copyOptionalTransportStringMap(
            hasEnvironment,
            environmentKeys,
            environmentValues,
            environmentCount,
        ),
        forwardedEnvironment = copiedForwardedEnvironment,
    )
    installOutput(outTransport, createSnapshot(contextPointer, CodexAgentCMcpTransportStdioSnapshot(value)))
}

@CName("codex_agent_mcp_transport_stdio_destroy")
public fun codexAgentMcpTransportStdioDestroy(
    context: COpaquePointer?,
    transport: CPointer<COpaquePointerVar>?,
): Int = destroyMcpTransport<CodexAgentCMcpTransportStdioSnapshot>(context, transport)

@CName("codex_agent_mcp_transport_stdio_command_copy")
public fun codexAgentMcpTransportStdioCommandCopy(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportString<CodexAgentCMcpTransportStdioSnapshot>(
    context,
    transport,
    buffer,
    capacity,
    outRequired,
) { it.value.command }

@CName("codex_agent_mcp_transport_stdio_arguments_count")
public fun codexAgentMcpTransportStdioArgumentsCount(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpTransportCount<CodexAgentCMcpTransportStdioSnapshot>(context, transport, outCount) {
    it.value.arguments.size
}

@CName("codex_agent_mcp_transport_stdio_argument_copy_at")
public fun codexAgentMcpTransportStdioArgumentCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportStringAt<CodexAgentCMcpTransportStdioSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
) { it.value.arguments }

@CName("codex_agent_mcp_transport_stdio_has_working_directory")
public fun codexAgentMcpTransportStdioHasWorkingDirectory(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasWorkingDirectory: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportStdioSnapshot>(context, transport, outHasWorkingDirectory) {
    if (it.value.workingDirectory == null) 0 else 1
}

@CName("codex_agent_mcp_transport_stdio_working_directory_copy")
public fun codexAgentMcpTransportStdioWorkingDirectoryCopy(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyOptionalMcpTransportString<CodexAgentCMcpTransportStdioSnapshot>(
    context,
    transport,
    buffer,
    capacity,
    outRequired,
) { it.value.workingDirectory }

@CName("codex_agent_mcp_transport_stdio_has_environment")
public fun codexAgentMcpTransportStdioHasEnvironment(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outHasEnvironment: CPointer<IntVar>?,
): Int = mcpTransportInt<CodexAgentCMcpTransportStdioSnapshot>(context, transport, outHasEnvironment) {
    if (it.value.environment == null) 0 else 1
}

@CName("codex_agent_mcp_transport_stdio_environment_count")
public fun codexAgentMcpTransportStdioEnvironmentCount(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpTransportMapCount<CodexAgentCMcpTransportStdioSnapshot>(context, transport, outCount) {
    it.value.environment
}

@CName("codex_agent_mcp_transport_stdio_environment_key_copy_at")
public fun codexAgentMcpTransportStdioEnvironmentKeyCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportStdioSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.environment },
    Map.Entry<String, String>::key,
)

@CName("codex_agent_mcp_transport_stdio_environment_value_copy_at")
public fun codexAgentMcpTransportStdioEnvironmentValueCopyAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpTransportMapAt<CodexAgentCMcpTransportStdioSnapshot>(
    context,
    transport,
    index,
    buffer,
    capacity,
    outRequired,
    { it.value.environment },
    Map.Entry<String, String>::value,
)

@CName("codex_agent_mcp_transport_stdio_forwarded_environment_count")
public fun codexAgentMcpTransportStdioForwardedEnvironmentCount(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    outCount: CPointer<ULongVar>?,
): Int = mcpTransportCount<CodexAgentCMcpTransportStdioSnapshot>(context, transport, outCount) {
    it.value.forwardedEnvironment.size
}

@CName("codex_agent_mcp_transport_stdio_forwarded_environment_at")
public fun codexAgentMcpTransportStdioForwardedEnvironmentAt(
    context: COpaquePointer?,
    transport: COpaquePointer?,
    index: ULong,
    outVariable: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outVariable)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpTransportStdioSnapshot>(
        contextPointer,
        transport,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val variable = it.value.forwardedEnvironment.transportItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        installOutput(
            outVariable,
            createSnapshot(contextPointer, CodexAgentCMcpEnvironmentVariableSnapshot(variable.copy())),
        )
    }
}

private fun CPointer<codex_agent_string_view>?.readTransportRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readTransportOptionalUtf8(hasValue: Int): String? {
    requireMcpTransportFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0UL)
        return null
    }
    return view.readUtf8()
}

private fun copyMcpTransportStrings(
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): List<String> {
    require(count <= Int.MAX_VALUE.toULong())
    if (count == 0UL) {
        require(values == null)
        return emptyList()
    }
    val pointer = requireNotNull(values)
    return List(count.toInt()) { index -> pointer[index].readUtf8() }
}

private fun copyOptionalTransportStringMap(
    hasMap: Int,
    keys: CPointer<codex_agent_string_view>?,
    values: CPointer<codex_agent_string_view>?,
    count: ULong,
): Map<String, String>? {
    requireMcpTransportFlag(hasMap)
    require(count <= Int.MAX_VALUE.toULong())
    if (hasMap == 0) {
        require(count == 0UL && keys == null && values == null)
        return null
    }
    if (count == 0UL) {
        require(keys == null && values == null)
        return linkedMapOf()
    }
    val keyPointer = requireNotNull(keys)
    val valuePointer = requireNotNull(values)
    val copied = linkedMapOf<String, String>()
    repeat(count.toInt()) { index ->
        val key = keyPointer[index].readUtf8()
        require(!copied.containsKey(key)) { "Duplicate map key" }
        copied[key] = valuePointer[index].readUtf8()
    }
    return copied
}

private fun copyMcpTransportEnvironmentVariables(
    context: COpaquePointer,
    values: CPointer<COpaquePointerVar>?,
    count: ULong,
    output: MutableList<AgentMcpEnvironmentVariable>,
): Int {
    if (count > Int.MAX_VALUE.toULong()) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    if (count == 0UL) return if (values == null) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = values ?: return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    repeat(count.toInt()) { index ->
        val status = withPayload<CodexAgentCMcpEnvironmentVariableSnapshot>(
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

private fun requireMcpTransportFlag(value: Int) {
    require(value == 0 || value == 1)
}

private inline fun <reified T : CodexAgentCSnapshot> destroyMcpTransport(
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

private inline fun <reified T : CodexAgentCSnapshot> copyMcpTransportString(
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

private inline fun <reified T : CodexAgentCSnapshot> copyOptionalMcpTransportString(
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

private inline fun <reified T : CodexAgentCSnapshot> mcpTransportInt(
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

private inline fun <reified T : CodexAgentCSnapshot> mcpTransportCount(
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

private inline fun <reified T : CodexAgentCSnapshot> mcpTransportMapCount(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<ULongVar>?,
    crossinline select: (T) -> Map<String, String>?,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val map = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        output.pointed.value = map.size.toULong()
        CODEX_AGENT_STATUS_OK
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyMcpTransportStringAt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> List<String>,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it).transportItemAt(index) ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private inline fun <reified T : CodexAgentCSnapshot> copyMcpTransportMapAt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    index: ULong,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    crossinline select: (T) -> Map<String, String>?,
    crossinline project: (Map.Entry<String, String>) -> String,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val map = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        val entry = map.entries.toList().transportItemAt(index)
            ?: return@withPayload CODEX_AGENT_STATUS_INVALID_ARGUMENT
        copyUtf8(project(entry), buffer, capacity, outRequired)
    }
}

private fun <T> List<T>.transportItemAt(index: ULong): T? =
    if (index > Int.MAX_VALUE.toULong()) null else getOrNull(index.toInt())
