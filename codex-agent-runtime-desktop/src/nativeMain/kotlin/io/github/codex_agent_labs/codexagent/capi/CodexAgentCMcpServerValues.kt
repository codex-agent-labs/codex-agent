@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentMcpAuthStatus
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServer
import io.github.codex_agent_labs.codexagent.agent.AgentMcpServerConfiguration
import io.github.codex_agent_labs.codexagent.agent.AgentResourceOrigin
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCMcpServerSnapshot(
    val value: AgentMcpServer,
) : CodexAgentCSnapshot

@CName("codex_agent_mcp_server_create")
public fun codexAgentMcpServerCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    displayName: CPointer<codex_agent_string_view>?,
    authStatus: Int,
    configuration: COpaquePointer?,
    origin: Int,
    canRemove: Int,
    outServer: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outServer)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireMcpServerBoolean(canRemove)
    val copiedConfiguration = if (configuration == null) {
        null
    } else {
        var copied: AgentMcpServerConfiguration? = null
        val status = withPayload<CodexAgentCMcpServerConfigurationSnapshot>(
            contextPointer,
            configuration,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copied = it.value.cAbiOwnedCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (status != CODEX_AGENT_STATUS_OK) return@abiStatus status
        checkNotNull(copied)
    }
    val value = AgentMcpServer(
        name = name.readMcpServerRequiredUtf8(),
        displayName = displayName.readMcpServerRequiredUtf8(),
        authStatus = mcpServerAuthStatusFromCValue(authStatus),
        configuration = copiedConfiguration,
        origin = mcpServerOriginFromCValue(origin),
        canRemove = canRemove == 1,
    )
    installOutput(
        outServer,
        createSnapshot(contextPointer, CodexAgentCMcpServerSnapshot(value.cAbiOwnedCopy())),
    )
}

@CName("codex_agent_mcp_server_destroy")
public fun codexAgentMcpServerDestroy(
    context: COpaquePointer?,
    server: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (server == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = server.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<CodexAgentCMcpServerSnapshot>(
        context,
        handle,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, server, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

@CName("codex_agent_mcp_server_name_copy")
public fun codexAgentMcpServerNameCopy(
    context: COpaquePointer?,
    server: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerString(context, server, buffer, capacity, outRequired) { it.value.name }

@CName("codex_agent_mcp_server_display_name_copy")
public fun codexAgentMcpServerDisplayNameCopy(
    context: COpaquePointer?,
    server: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyMcpServerString(context, server, buffer, capacity, outRequired) { it.value.displayName }

@CName("codex_agent_mcp_server_auth_status")
public fun codexAgentMcpServerAuthStatus(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outAuthStatus: CPointer<IntVar>?,
): Int = mcpServerInt(context, server, outAuthStatus) { mcpServerAuthStatusToCValue(it.value.authStatus) }

@CName("codex_agent_mcp_server_has_configuration")
public fun codexAgentMcpServerHasConfiguration(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outHasConfiguration: CPointer<IntVar>?,
): Int = mcpServerInt(context, server, outHasConfiguration) {
    if (it.value.configuration == null) 0 else 1
}

@CName("codex_agent_mcp_server_configuration")
public fun codexAgentMcpServerConfiguration(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outConfiguration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConfiguration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerSnapshot>(
        contextPointer,
        server,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val configuration = it.value.configuration ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outConfiguration,
            createSnapshot(
                contextPointer,
                CodexAgentCMcpServerConfigurationSnapshot(configuration.cAbiOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_mcp_server_origin")
public fun codexAgentMcpServerOrigin(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outOrigin: CPointer<IntVar>?,
): Int = mcpServerInt(context, server, outOrigin) { mcpServerOriginToCValue(it.value.origin) }

@CName("codex_agent_mcp_server_can_remove")
public fun codexAgentMcpServerCanRemove(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outCanRemove: CPointer<IntVar>?,
): Int = mcpServerInt(context, server, outCanRemove) { if (it.value.canRemove) 1 else 0 }

@CName("codex_agent_mcp_server_is_authorized")
public fun codexAgentMcpServerIsAuthorized(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outIsAuthorized: CPointer<IntVar>?,
): Int = mcpServerInt(context, server, outIsAuthorized) { if (it.value.isAuthorized) 1 else 0 }

internal fun AgentMcpServer.cAbiOwnedCopy(): AgentMcpServer = copy(
    configuration = configuration?.cAbiOwnedCopy(),
)

private fun CPointer<codex_agent_string_view>?.readMcpServerRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun requireMcpServerBoolean(value: Int) {
    require(value == 0 || value == 1)
}

private fun mcpServerAuthStatusFromCValue(value: Int): AgentMcpAuthStatus = when (value) {
    0 -> AgentMcpAuthStatus.UNKNOWN
    1 -> AgentMcpAuthStatus.UNSUPPORTED
    2 -> AgentMcpAuthStatus.NOT_LOGGED_IN
    3 -> AgentMcpAuthStatus.BEARER_TOKEN
    4 -> AgentMcpAuthStatus.OAUTH
    else -> throw IllegalArgumentException("Unknown MCP authentication status")
}

private fun mcpServerAuthStatusToCValue(value: AgentMcpAuthStatus): Int = when (value) {
    AgentMcpAuthStatus.UNKNOWN -> 0
    AgentMcpAuthStatus.UNSUPPORTED -> 1
    AgentMcpAuthStatus.NOT_LOGGED_IN -> 2
    AgentMcpAuthStatus.BEARER_TOKEN -> 3
    AgentMcpAuthStatus.OAUTH -> 4
}

private fun mcpServerOriginFromCValue(value: Int): AgentResourceOrigin = when (value) {
    0 -> AgentResourceOrigin.USER
    1 -> AgentResourceOrigin.WORKSPACE
    2 -> AgentResourceOrigin.PLUGIN
    3 -> AgentResourceOrigin.MANAGED
    4 -> AgentResourceOrigin.UNKNOWN
    else -> throw IllegalArgumentException("Unknown MCP server origin")
}

private fun mcpServerOriginToCValue(value: AgentResourceOrigin): Int = when (value) {
    AgentResourceOrigin.USER -> 0
    AgentResourceOrigin.WORKSPACE -> 1
    AgentResourceOrigin.PLUGIN -> 2
    AgentResourceOrigin.MANAGED -> 3
    AgentResourceOrigin.UNKNOWN -> 4
}

private fun copyMcpServerString(
    context: COpaquePointer?,
    server: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCMcpServerSnapshot) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCMcpServerSnapshot>(context, server, CodexAgentCHandleKind.SNAPSHOT) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private fun mcpServerInt(
    context: COpaquePointer?,
    server: COpaquePointer?,
    output: CPointer<IntVar>?,
    select: (CodexAgentCMcpServerSnapshot) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerSnapshot>(context, server, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it)
        CODEX_AGENT_STATUS_OK
    }
}
