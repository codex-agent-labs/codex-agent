@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConnector
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegration
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCIntegrationConnectorSnapshot(
    val value: AgentIntegration.Connector,
) : CodexAgentCSnapshot

@CName("codex_agent_integration_connector_create")
public fun codexAgentIntegrationConnectorCreate(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outIntegration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIntegration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCConnectorSnapshot>(contextPointer, connector, CodexAgentCHandleKind.SNAPSHOT) {
        val integration = AgentIntegration.Connector(it.value.integrationOwnedCopy())
        installOutput(
            outIntegration,
            createSnapshot(contextPointer, CodexAgentCIntegrationConnectorSnapshot(integration)),
        )
    }
}

@CName("codex_agent_integration_connector_destroy")
public fun codexAgentIntegrationConnectorDestroy(
    context: COpaquePointer?,
    integration: CPointer<COpaquePointerVar>?,
): Int = destroyIntegrationConnector(context, integration)

@CName("codex_agent_integration_connector_connector")
public fun codexAgentIntegrationConnectorConnector(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConnector)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationConnectorSnapshot>(
        contextPointer,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outConnector,
            createSnapshot(
                contextPointer,
                CodexAgentCConnectorSnapshot(it.value.connector.integrationOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_integration_connector_id_copy")
public fun codexAgentIntegrationConnectorIdCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyIntegrationConnectorString(
    context,
    integration,
    buffer,
    capacity,
    outRequired,
) { it.value.id }

@CName("codex_agent_integration_connector_display_name_copy")
public fun codexAgentIntegrationConnectorDisplayNameCopy(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyIntegrationConnectorString(
    context,
    integration,
    buffer,
    capacity,
    outRequired,
) { it.value.displayName }

private fun destroyIntegrationConnector(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<CodexAgentCIntegrationConnectorSnapshot>(
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

private fun copyIntegrationConnectorString(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (CodexAgentCIntegrationConnectorSnapshot) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCIntegrationConnectorSnapshot>(
        context,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copyUtf8(select(it), buffer, capacity, outRequired)
    }
}

private fun AgentConnector.integrationOwnedCopy(): AgentConnector = copy(
    pluginNames = pluginNames.toList(),
)
