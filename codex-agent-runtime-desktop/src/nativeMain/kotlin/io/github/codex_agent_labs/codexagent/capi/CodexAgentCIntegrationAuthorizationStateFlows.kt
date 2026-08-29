@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentIntegration
import io.github.codex_agent_labs.codexagent.agent.AgentIntegrationAuthorizationState
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine

internal data class CodexAgentCIntegrationAuthorizationStateFlowSnapshot(
    val value: AgentIntegrationAuthorizationState,
) : CodexAgentCSnapshot

internal data class CodexAgentCIntegrationAuthorizationActiveFlowSnapshot(
    val value: AgentIntegration?,
) : CodexAgentCSnapshot

@CName("codex_agent_integration_authorization_state_get")
public fun codexAgentIntegrationAuthorizationStateGet(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationCurrent(
    context,
    authorization,
    outSnapshot,
    select = { it.core.state.value },
) { contextPointer, value ->
    createSnapshot(
        contextPointer,
        CodexAgentCIntegrationAuthorizationStateFlowSnapshot(value.integrationAuthorizationFlowCopy()),
    )
}

@CName("codex_agent_integration_authorization_state_subscribe")
public fun codexAgentIntegrationAuthorizationStateSubscribe(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationSubscribe(
    context,
    authorization,
    callback,
    userData,
    outSubscription,
    states = { it.core.state },
) { contextPointer, value ->
    createSnapshot(
        contextPointer,
        CodexAgentCIntegrationAuthorizationStateFlowSnapshot(value.integrationAuthorizationFlowCopy()),
    )
}

@CName("codex_agent_integration_authorization_active_get")
public fun codexAgentIntegrationAuthorizationActiveGet(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationCurrent(
    context,
    authorization,
    outSnapshot,
    select = { it.core.active.value },
) { contextPointer, value ->
    createSnapshot(
        contextPointer,
        CodexAgentCIntegrationAuthorizationActiveFlowSnapshot(value?.integrationStateOwnedCopy()),
    )
}

@CName("codex_agent_integration_authorization_active_subscribe")
public fun codexAgentIntegrationAuthorizationActiveSubscribe(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationSubscribe(
    context,
    authorization,
    callback,
    userData,
    outSubscription,
    states = { it.core.active },
) { contextPointer, value ->
    createSnapshot(
        contextPointer,
        CodexAgentCIntegrationAuthorizationActiveFlowSnapshot(value?.integrationStateOwnedCopy()),
    )
}

@CName("codex_agent_integration_authorization_is_authorizing_get")
public fun codexAgentIntegrationAuthorizationIsAuthorizingGet(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationCurrent(
    context,
    authorization,
    outSnapshot,
    select = { it.core.isAuthorizing.value },
    snapshot = ::createCodexAgentCBooleanStateSnapshot,
)

@CName("codex_agent_integration_authorization_is_authorizing_subscribe")
public fun codexAgentIntegrationAuthorizationIsAuthorizingSubscribe(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = integrationAuthorizationSubscribe(
    context,
    authorization,
    callback,
    userData,
    outSubscription,
    states = { it.core.isAuthorizing },
    snapshot = ::createCodexAgentCBooleanStateSnapshot,
)

@CName("codex_agent_integration_authorization_state_value")
public fun codexAgentIntegrationAuthorizationStateValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationAuthorizationStateFlowSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outState,
            createSnapshot(
                contextPointer,
                CodexAgentCIntegrationStateSnapshot(it.value.integrationAuthorizationFlowCopy()),
            ),
        )
    }
}

@CName("codex_agent_integration_authorization_active_has_value")
public fun codexAgentIntegrationAuthorizationActiveHasValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationAuthorizationActiveFlowSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasValue.pointed.value = if (it.value == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_integration_authorization_active_value")
public fun codexAgentIntegrationAuthorizationActiveValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outIntegration: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outIntegration)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationAuthorizationActiveFlowSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = it.value ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outIntegration,
            createSnapshot(contextPointer, CodexAgentCIntegrationSnapshot(value.integrationStateOwnedCopy())),
        )
    }
}

private fun AgentIntegrationAuthorizationState.integrationAuthorizationFlowCopy(): AgentIntegrationAuthorizationState =
    copy(target = target?.integrationStateOwnedCopy(), failure = failure?.copy())

private fun <T> integrationAuthorizationCurrent(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
    select: (CodexAgentCIntegrationAuthorization) -> T,
    snapshot: (COpaquePointer, T) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationAuthorization>(
        contextPointer,
        authorization,
        CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
    ) { wrapper ->
        installOutput(outSnapshot, snapshot(contextPointer, select(wrapper)))
    }
}

private fun <T> integrationAuthorizationSubscribe(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
    states: (CodexAgentCIntegrationAuthorization) -> Flow<T>,
    snapshot: (COpaquePointer, T) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCIntegrationAuthorization>(
        contextPointer,
        authorization,
        CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
    ) { wrapper ->
        val ownedStates = combine(wrapper.host.core.lifecycleState, states(wrapper)) { hostState, value ->
            value to ((hostState as? CodexHostState.Ready)?.agent !== wrapper.owner)
        }
        startCodexAgentCStateSubscription(
            contextPointer,
            wrapper.host.runtime,
            ownedStates,
            snapshot = { (value, _) -> snapshot(contextPointer, value).integrationAuthorizationStateSnapshot() },
            isTerminal = { (_, terminal) -> terminal },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

private fun CodexAgentCRegistryResult<COpaquePointer>.integrationAuthorizationStateSnapshot():
    CodexAgentCStateSnapshot = CodexAgentCStateSnapshot(status, value)
