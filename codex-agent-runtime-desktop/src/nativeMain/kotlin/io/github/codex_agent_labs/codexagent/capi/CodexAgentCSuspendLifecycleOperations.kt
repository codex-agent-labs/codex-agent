@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentIntegration
import io.github.codex_agent_labs.codexagent.agent.CodexAuthenticationMethod
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer

@CName("codex_agent_host_start")
public fun codexAgentHostStart(
    context: COpaquePointer?,
    host: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCHost>(
    context,
    host,
    CodexAgentCHandleKind.HOST,
    callback,
    userData,
    outOperation,
    runtime = { it.runtime },
) {
    it.core.start()
    CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
}

@CName("codex_agent_authentication_authenticate_api_key")
public fun codexAgentAuthenticationAuthenticateApiKey(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    method: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = authenticate<CodexAgentCApiKeyAuthenticationMethodSnapshot>(
    context,
    authentication,
    method,
    callback,
    userData,
    outOperation,
) { CodexAuthenticationMethod.ApiKey(it.value.value) }

@CName("codex_agent_authentication_authenticate_chat_gpt_browser")
public fun codexAgentAuthenticationAuthenticateChatGptBrowser(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    method: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = authenticate<CodexAgentCChatGptBrowserAuthenticationMethodSnapshot>(
    context,
    authentication,
    method,
    callback,
    userData,
    outOperation,
) { CodexAuthenticationMethod.ChatGptBrowser }

@CName("codex_agent_authentication_authenticate_chat_gpt_device_code")
public fun codexAgentAuthenticationAuthenticateChatGptDeviceCode(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    method: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = authenticate<CodexAgentCChatGptDeviceCodeAuthenticationMethodSnapshot>(
    context,
    authentication,
    method,
    callback,
    userData,
    outOperation,
) { CodexAuthenticationMethod.ChatGptDeviceCode }

@CName("codex_agent_authentication_cancel")
public fun codexAgentAuthenticationCancel(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = authenticationOperation(
    context,
    authentication,
    callback,
    userData,
    outOperation,
) { it.core.cancel() }

@CName("codex_agent_authentication_sign_out")
public fun codexAgentAuthenticationSignOut(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = authenticationOperation(
    context,
    authentication,
    callback,
    userData,
    outOperation,
) { it.core.signOut() }

@CName("codex_agent_integration_authorization_authorize")
public fun codexAgentIntegrationAuthorizationAuthorize(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    target: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    var copied: AgentIntegration? = null
    val copyStatus = withPayload<CodexAgentCIntegrationSnapshot>(
        contextPointer,
        target,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copied = it.value.lifecycleOperationCopy()
        CODEX_AGENT_STATUS_OK
    }
    if (copyStatus != CODEX_AGENT_STATUS_OK) return@abiStatus copyStatus
    startCodexAgentCTargetOperation<CodexAgentCIntegrationAuthorization>(
        contextPointer,
        authorization,
        CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
        callback,
        userData,
        outOperation,
        runtime = { it.host.runtime },
    ) {
        it.core.authorize(checkNotNull(copied))
        CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
    }
}

@CName("codex_agent_integration_authorization_cancel")
public fun codexAgentIntegrationAuthorizationCancel(
    context: COpaquePointer?,
    authorization: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
): Int = startCodexAgentCTargetOperation<CodexAgentCIntegrationAuthorization>(
    context,
    authorization,
    CodexAgentCHandleKind.INTEGRATION_AUTHORIZATION,
    callback,
    userData,
    outOperation,
    runtime = { it.host.runtime },
) {
    it.core.cancel()
    CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
}

private inline fun <reified T : Any> authenticate(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    method: COpaquePointer?,
    callback: CPointer<CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>>?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    copy: (T) -> CodexAuthenticationMethod,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    var copied: CodexAuthenticationMethod? = null
    val copyStatus = withPayload<T>(contextPointer, method, CodexAgentCHandleKind.SNAPSHOT) {
        copied = copy(it)
        CODEX_AGENT_STATUS_OK
    }
    if (copyStatus != CODEX_AGENT_STATUS_OK) return@abiStatus copyStatus
    authenticationOperation(
        contextPointer,
        authentication,
        callback,
        userData,
        outOperation,
    ) { it.core.authenticate(checkNotNull(copied)) }
}

private inline fun authenticationOperation(
    context: COpaquePointer?,
    authentication: COpaquePointer?,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    crossinline execute: suspend (CodexAgentCAuthentication) -> Unit,
): Int = startCodexAgentCTargetOperation<CodexAgentCAuthentication>(
    context,
    authentication,
    CodexAgentCHandleKind.AUTHENTICATION,
    callback,
    userData,
    outOperation,
    runtime = { it.host.runtime },
) {
    execute(it)
    CodexAgentCOperationResult(CODEX_AGENT_STATUS_OK)
}

private fun AgentIntegration.lifecycleOperationCopy(): AgentIntegration = when (this) {
    is AgentIntegration.Connector -> copy(connector = connector.copy(pluginNames = connector.pluginNames.toList()))
    is AgentIntegration.McpServer -> copy(server = server.cAbiOwnedCopy())
}
