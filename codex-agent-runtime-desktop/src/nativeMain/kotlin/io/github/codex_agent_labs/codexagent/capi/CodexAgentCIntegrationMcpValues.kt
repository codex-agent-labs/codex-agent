@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentIntegration
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCIntegrationMcpServerSnapshot(
    val value: AgentIntegration.McpServer,
) : CodexAgentCSnapshot

@CName("codex_agent_integration_mcp_server_create")
public fun codexAgentIntegrationMcpServerCreate(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outIntegration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIntegration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCMcpServerSnapshot>(contextPointer, server, CodexAgentCHandleKind.SNAPSHOT) {
        val integration = AgentIntegration.McpServer(it.value.cAbiOwnedCopy())
        installOutput(
            outIntegration,
            createSnapshot(contextPointer, CodexAgentCIntegrationMcpServerSnapshot(integration)),
        )
    }
}

@CName("codex_agent_integration_mcp_server_destroy")
public fun codexAgentIntegrationMcpServerDestroy(
    context: COpaquePointer?,
    integration: CPointer<COpaquePointerVar>?,
): Int = destroyIntegrationMcpServer(context, integration)

@CName("codex_agent_integration_mcp_server_server")
public fun codexAgentIntegrationMcpServerServer(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    outServer: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outServer)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationMcpServerSnapshot>(
        contextPointer,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outServer,
            createSnapshot(
                contextPointer,
                CodexAgentCMcpServerSnapshot(it.value.server.cAbiOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_integration_mcp_server_id_copy")
public fun codexAgentIntegrationMcpServerIdCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyIntegrationMcpServerString(
    context,
    integration,
    buffer,
    capacity,
    outRequired,
) { it.value.id }

@CName("codex_agent_integration_mcp_server_display_name_copy")
public fun codexAgentIntegrationMcpServerDisplayNameCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyIntegrationMcpServerString(
    context,
    integration,
    buffer,
    capacity,
    outRequired,
) { it.value.displayName }

private fun destroyIntegrationMcpServer(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<CodexAgentCIntegrationMcpServerSnapshot>(
        context,
        handle,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { CODEX_AGENT_STATUS_OK }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

private fun copyIntegrationMcpServerString(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCIntegrationMcpServerSnapshot) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCIntegrationMcpServerSnapshot>(
        context,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}
