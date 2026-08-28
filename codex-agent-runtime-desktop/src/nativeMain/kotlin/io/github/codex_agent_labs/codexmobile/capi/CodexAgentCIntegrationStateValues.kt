@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentIntegration
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegrationAuthorizationState
import io.github.codex_agent_labs.codexmobile.agent.AgentIntegrationAuthorizationStatus
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCIntegrationSnapshot(
    val value: AgentIntegration,
) : CodexAgentCSnapshot

internal data class CodexAgentCIntegrationStateSnapshot(
    val value: AgentIntegrationAuthorizationState,
) : CodexAgentCSnapshot

@CName("codex_agent_integration_from_connector")
public fun codexAgentIntegrationFromConnector(
    context: COpaquePointer?,
    connector: COpaquePointer?,
    outIntegration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIntegration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationConnectorSnapshot>(
        contextPointer,
        connector,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outIntegration,
            createSnapshot(contextPointer, CodexAgentCIntegrationSnapshot(it.value.integrationStateOwnedCopy())),
        )
    }
}

@CName("codex_agent_integration_from_mcp_server")
public fun codexAgentIntegrationFromMcpServer(
    context: COpaquePointer?,
    server: COpaquePointer?,
    outIntegration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIntegration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationMcpServerSnapshot>(
        contextPointer,
        server,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outIntegration,
            createSnapshot(contextPointer, CodexAgentCIntegrationSnapshot(it.value.integrationStateOwnedCopy())),
        )
    }
}

@CName("codex_agent_integration_destroy")
public fun codexAgentIntegrationDestroy(
    context: COpaquePointer?,
    integration: CPointer<COpaquePointerVar>?,
): Int = destroyIntegrationStateValue<CodexAgentCIntegrationSnapshot>(context, integration)

@CName("codex_agent_integration_kind")
public fun codexAgentIntegrationKind(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    outKind: CPointer<IntVar>?,
): Int = integrationStateInt<CodexAgentCIntegrationSnapshot>(context, integration, outKind) {
    when (it.value) {
        is AgentIntegration.Connector -> 0
        is AgentIntegration.McpServer -> 1
    }
}

@CName("codex_agent_integration_connector")
public fun codexAgentIntegrationConnector(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    outConnector: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConnector)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationSnapshot>(
        contextPointer,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val connector = it.value as? AgentIntegration.Connector
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(
            outConnector,
            createSnapshot(
                contextPointer,
                CodexAgentCIntegrationConnectorSnapshot(connector.integrationStateOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_integration_mcp_server")
public fun codexAgentIntegrationMcpServer(
    context: COpaquePointer?,
    integration: COpaquePointer?,
    outServer: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outServer)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationSnapshot>(
        contextPointer,
        integration,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val server = it.value as? AgentIntegration.McpServer
            ?: return@withPayload CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        installOutput(
            outServer,
            createSnapshot(
                contextPointer,
                CodexAgentCIntegrationMcpServerSnapshot(server.integrationStateOwnedCopy()),
            ),
        )
    }
}

@CName("codex_agent_integration_authorization_state_create")
public fun codexAgentIntegrationAuthorizationStateCreate(
    context: COpaquePointer?,
    status: Int,
    target: COpaquePointer?,
    failure: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    var copiedTarget: AgentIntegration? = null
    if (target != null) {
        val targetStatus = withPayload<CodexAgentCIntegrationSnapshot>(
            contextPointer,
            target,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedTarget = it.value.integrationStateOwnedCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (targetStatus != CODEX_AGENT_STATUS_OK) return@abiStatus targetStatus
    }
    var copiedFailure: CodexFailure? = null
    if (failure != null) {
        val failureStatus = withPayload<CodexFailure>(
            contextPointer,
            failure,
            CodexAgentCHandleKind.FAILURE,
        ) {
            copiedFailure = it.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (failureStatus != CODEX_AGENT_STATUS_OK) return@abiStatus failureStatus
    }
    installOutput(
        outState,
        createSnapshot(
            contextPointer,
            CodexAgentCIntegrationStateSnapshot(
                AgentIntegrationAuthorizationState(
                    status = integrationAuthorizationStatusFromCValue(status),
                    target = copiedTarget,
                    failure = copiedFailure,
                ),
            ),
        ),
    )
}

@CName("codex_agent_integration_authorization_state_destroy")
public fun codexAgentIntegrationAuthorizationStateDestroy(
    context: COpaquePointer?,
    state: CPointer<COpaquePointerVar>?,
): Int = destroyIntegrationStateValue<CodexAgentCIntegrationStateSnapshot>(context, state)

@CName("codex_agent_integration_authorization_state_status")
public fun codexAgentIntegrationAuthorizationStateStatus(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outStatus: CPointer<IntVar>?,
): Int = integrationStateInt<CodexAgentCIntegrationStateSnapshot>(context, state, outStatus) {
    integrationAuthorizationStatusToCValue(it.value.status)
}

@CName("codex_agent_integration_authorization_state_target")
public fun codexAgentIntegrationAuthorizationStateTarget(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outTarget: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTarget)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationStateSnapshot>(
        contextPointer,
        state,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val target = it.value.target ?: return@withPayload CODEX_AGENT_STATUS_OK
        installOutput(
            outTarget,
            createSnapshot(contextPointer, CodexAgentCIntegrationSnapshot(target.integrationStateOwnedCopy())),
        )
    }
}

@CName("codex_agent_integration_authorization_state_failure")
public fun codexAgentIntegrationAuthorizationStateFailure(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationStateSnapshot>(
        contextPointer,
        state,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val failure = it.value.failure ?: return@withPayload CODEX_AGENT_STATUS_OK
        installOutput(outFailure, createFailure(contextPointer, failure.copy()))
    }
}

private fun AgentIntegration.integrationStateOwnedCopy(): AgentIntegration = when (this) {
    is AgentIntegration.Connector -> integrationStateOwnedCopy()
    is AgentIntegration.McpServer -> integrationStateOwnedCopy()
}

private fun AgentIntegration.Connector.integrationStateOwnedCopy(): AgentIntegration.Connector =
    AgentIntegration.Connector(connector.copy(pluginNames = connector.pluginNames.toList()))

private fun AgentIntegration.McpServer.integrationStateOwnedCopy(): AgentIntegration.McpServer =
    AgentIntegration.McpServer(server.cAbiOwnedCopy())

private fun integrationAuthorizationStatusFromCValue(value: Int): AgentIntegrationAuthorizationStatus = when (value) {
    0 -> AgentIntegrationAuthorizationStatus.IDLE
    1 -> AgentIntegrationAuthorizationStatus.STARTING
    2 -> AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION
    3 -> AgentIntegrationAuthorizationStatus.AUTHORIZED
    4 -> AgentIntegrationAuthorizationStatus.FAILED
    else -> throw IllegalArgumentException("Unknown integration authorization status")
}

private fun integrationAuthorizationStatusToCValue(value: AgentIntegrationAuthorizationStatus): Int = when (value) {
    AgentIntegrationAuthorizationStatus.IDLE -> 0
    AgentIntegrationAuthorizationStatus.STARTING -> 1
    AgentIntegrationAuthorizationStatus.AWAITING_COMPLETION -> 2
    AgentIntegrationAuthorizationStatus.AUTHORIZED -> 3
    AgentIntegrationAuthorizationStatus.FAILED -> 4
}

private inline fun <reified T : CodexAgentCSnapshot> destroyIntegrationStateValue(
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

private inline fun <reified T : CodexAgentCSnapshot> integrationStateInt(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    output: CPointer<IntVar>?,
    select: (T) -> Int,
): Int = abiStatus {
    if (output == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        output.pointed.value = select(it)
        CODEX_AGENT_STATUS_OK
    }
}
