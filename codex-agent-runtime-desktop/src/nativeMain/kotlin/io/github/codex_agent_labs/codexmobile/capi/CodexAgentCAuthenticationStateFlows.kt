@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentAuthenticationState
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPurpose
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine

internal data class CodexAgentCBooleanStateSnapshot(
    val value: Boolean,
) : CodexAgentCSnapshot

internal fun createCodexAgentCBooleanStateSnapshot(
    context: COpaquePointer,
    value: Boolean,
): CodexAgentCRegistryResult<COpaquePointer> =
    createSnapshot(context, CodexAgentCBooleanStateSnapshot(value))

@CName("codex_agent_authentication_state_get")
public fun codexAgentAuthenticationStateGet(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowGet(context, authentication, outSnapshot) {
    CodexAgentCAuthenticationStateValueSnapshot(it.core.state.value.authenticationFlowCopy())
}

@CName("codex_agent_authentication_state_subscribe")
public fun codexAgentAuthenticationStateSubscribe(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CPointer<CFunction<(
        COpaquePointer?,
        COpaquePointer?,
        Int,
        COpaquePointer?,
        Int,
        COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowSubscribe(
    context,
    authentication,
    callback,
    userData,
    outSubscription,
    states = { it.core.state },
) { pointer, value ->
    createSnapshot(pointer, CodexAgentCAuthenticationStateValueSnapshot(value.authenticationFlowCopy()))
}

@CName("codex_agent_authentication_is_authenticated_get")
public fun codexAgentAuthenticationIsAuthenticatedGet(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowGet(context, authentication, outSnapshot) {
    CodexAgentCBooleanStateSnapshot(it.core.isAuthenticated.value)
}

@CName("codex_agent_authentication_is_authenticated_subscribe")
public fun codexAgentAuthenticationIsAuthenticatedSubscribe(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CPointer<CFunction<(
        COpaquePointer?,
        COpaquePointer?,
        Int,
        COpaquePointer?,
        Int,
        COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowSubscribe(
    context,
    authentication,
    callback,
    userData,
    outSubscription,
    states = { it.core.isAuthenticated },
    snapshot = ::createCodexAgentCBooleanStateSnapshot,
)

@CName("codex_agent_authentication_is_authenticating_get")
public fun codexAgentAuthenticationIsAuthenticatingGet(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowGet(context, authentication, outSnapshot) {
    CodexAgentCBooleanStateSnapshot(it.core.isAuthenticating.value)
}

@CName("codex_agent_authentication_is_authenticating_subscribe")
public fun codexAgentAuthenticationIsAuthenticatingSubscribe(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CPointer<CFunction<(
        COpaquePointer?,
        COpaquePointer?,
        Int,
        COpaquePointer?,
        Int,
        COpaquePointer?,
    ) -> Unit>>?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int = authenticationStateFlowSubscribe(
    context,
    authentication,
    callback,
    userData,
    outSubscription,
    states = { it.core.isAuthenticating },
    snapshot = ::createCodexAgentCBooleanStateSnapshot,
)

@CName("codex_agent_authentication_state_value")
public fun codexAgentAuthenticationStateValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAuthenticationStateValueSnapshot>(
        contextPointer,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outState,
            createSnapshot(
                contextPointer,
                CodexAgentCAuthenticationStateValueSnapshot(it.value.authenticationFlowCopy()),
            ),
        )
    }
}

@CName("codex_agent_state_boolean_value")
public fun codexAgentStateBooleanValue(
    context: COpaquePointer?,
    snapshot: COpaquePointer?,
    outValue: CPointer<IntVar>?,
): Int = abiStatus {
    if (outValue == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCBooleanStateSnapshot>(
        context,
        snapshot,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outValue.pointed.value = if (it.value) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

private fun authenticationStateFlowGet(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    outSnapshot: CPointer<COpaquePointerVar>?,
    snapshot: (CodexAgentCAuthentication) -> CodexAgentCSnapshot,
): Int = abiStatus {
    if (!validEmptyOutput(outSnapshot)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAuthentication>(
        contextPointer,
        authentication,
        CodexAgentCHandleKind.AUTHENTICATION,
    ) {
        installOutput(outSnapshot, createSnapshot(contextPointer, snapshot(it)))
    }
}

private fun <T> authenticationStateFlowSubscribe(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CodexAgentCStateCallback?,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
    states: (CodexAgentCAuthentication) -> StateFlow<T>,
    snapshot: (COpaquePointer, T) -> CodexAgentCRegistryResult<COpaquePointer>,
): Int = abiStatus {
    if (callback == null || !validEmptyOutput(outSubscription)) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAuthentication>(
        contextPointer,
        authentication,
        CodexAgentCHandleKind.AUTHENTICATION,
    ) { wrapper ->
        val source = states(wrapper)
        val observed = combine(wrapper.host.core.lifecycleState, source) { hostState, value ->
            value to ((hostState as? CodexHostState.Ready)?.agent !== wrapper.owner)
        }
        startCodexAgentCStateSubscription(
            contextPointer,
            wrapper.host.runtime,
            observed,
            snapshot = { (value, _) ->
                val created = snapshot(contextPointer, value)
                CodexAgentCStateSnapshot(created.status, created.value)
            },
            isTerminal = { (_, terminal) -> terminal },
            callback = callback,
            userData = userData,
            outSubscription = outSubscription,
        )
    }
}

private fun AgentAuthenticationState.authenticationFlowCopy(): AgentAuthenticationState = copy(
    pendingSignInUrl = pendingSignInUrl?.authenticationFlowCopy(),
    deviceVerificationUrl = deviceVerificationUrl?.authenticationFlowCopy(),
    failure = failure?.copy(),
)

private fun CodexAuthorizationUrl.authenticationFlowCopy(): CodexAuthorizationUrl = when (purpose) {
    CodexAuthorizationPurpose.CHAT_GPT -> CodexAuthorizationUrl.chatGpt(value)
    CodexAuthorizationPurpose.EXTERNAL -> CodexAuthorizationUrl.external(value)
}
