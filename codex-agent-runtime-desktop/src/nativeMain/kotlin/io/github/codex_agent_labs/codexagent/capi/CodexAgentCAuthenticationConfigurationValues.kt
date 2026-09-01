@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentApprovalPreset
import io.github.codex_agent_labs.codexagent.agent.AgentAuthenticationState
import io.github.codex_agent_labs.codexagent.agent.AgentAuthenticationStatus
import io.github.codex_agent_labs.codexagent.agent.AgentConversationSettings
import io.github.codex_agent_labs.codexagent.agent.CodexAuthorizationPurpose
import io.github.codex_agent_labs.codexagent.agent.CodexAuthorizationUrl
import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexFailure
import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCAuthenticationStateValueSnapshot(
    val value: AgentAuthenticationState,
) : CodexAgentCSnapshot

internal data class CodexAgentCConversationSettingsSnapshot(
    val value: AgentConversationSettings,
) : CodexAgentCSnapshot

internal data class CodexAgentCAuthorizationUrlSnapshot(
    val value: CodexAuthorizationUrl,
) : CodexAgentCSnapshot

internal data class CodexAgentCClientInfoValueSnapshot(
    val value: CodexClientInfo,
) : CodexAgentCSnapshot

@CName("codex_agent_authentication_state_create")
public fun codexAgentAuthenticationStateCreate(
    context: COpaquePointer?,
    status: Int,
    hasPendingSignInUrl: Int,
    pendingSignInUrl: COpaquePointer?,
    hasDeviceVerificationUrl: Int,
    deviceVerificationUrl: COpaquePointer?,
    hasDeviceUserCode: Int,
    deviceUserCode: CPointer<codex_agent_string_view>?,
    hasFailure: Int,
    failure: COpaquePointer?,
    outState: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outState)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireAuthenticationConfigurationFlag(hasPendingSignInUrl)
    requireAuthenticationConfigurationFlag(hasDeviceVerificationUrl)
    requireAuthenticationConfigurationFlag(hasDeviceUserCode)
    requireAuthenticationConfigurationFlag(hasFailure)
    if (hasPendingSignInUrl == 0) require(pendingSignInUrl == null)
    if (hasDeviceVerificationUrl == 0) require(deviceVerificationUrl == null)
    if (hasFailure == 0) require(failure == null)

    val copiedDeviceUserCode = deviceUserCode.readAuthenticationConfigurationOptionalUtf8(hasDeviceUserCode)
    var copiedPendingSignInUrl: CodexAuthorizationUrl? = null
    if (hasPendingSignInUrl == 1) {
        val result = withPayload<CodexAgentCAuthorizationUrlSnapshot>(
            contextPointer,
            pendingSignInUrl,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedPendingSignInUrl = it.value.authenticationConfigurationCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (result != CODEX_AGENT_STATUS_OK) return@abiStatus result
    }
    var copiedDeviceVerificationUrl: CodexAuthorizationUrl? = null
    if (hasDeviceVerificationUrl == 1) {
        val result = withPayload<CodexAgentCAuthorizationUrlSnapshot>(
            contextPointer,
            deviceVerificationUrl,
            CodexAgentCHandleKind.SNAPSHOT,
        ) {
            copiedDeviceVerificationUrl = it.value.authenticationConfigurationCopy()
            CODEX_AGENT_STATUS_OK
        }
        if (result != CODEX_AGENT_STATUS_OK) return@abiStatus result
    }
    var copiedFailure: CodexFailure? = null
    if (hasFailure == 1) {
        val result = withPayload<CodexFailure>(
            contextPointer,
            failure,
            CodexAgentCHandleKind.FAILURE,
        ) {
            copiedFailure = it.copy()
            CODEX_AGENT_STATUS_OK
        }
        if (result != CODEX_AGENT_STATUS_OK) return@abiStatus result
    }
    installOutput(
        outState,
        createSnapshot(
            contextPointer,
            CodexAgentCAuthenticationStateValueSnapshot(
                AgentAuthenticationState(
                    status = authenticationStatusFromConfigurationC(status),
                    pendingSignInUrl = copiedPendingSignInUrl,
                    deviceVerificationUrl = copiedDeviceVerificationUrl,
                    deviceUserCode = copiedDeviceUserCode,
                    failure = copiedFailure,
                ),
            ),
        ),
    )
}

@CName("codex_agent_authentication_state_destroy")
public fun codexAgentAuthenticationStateDestroy(
    context: COpaquePointer?,
    state: CPointer<COpaquePointerVar>?,
): Int = destroyAuthenticationConfigurationSnapshot<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
)

@CName("codex_agent_authentication_state_status")
public fun codexAgentAuthenticationStateStatus(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outStatus: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    outStatus,
) { authenticationStatusToConfigurationC(it.value.status) }

@CName("codex_agent_authentication_state_has_pending_sign_in_url")
public fun codexAgentAuthenticationStateHasPendingSignInUrl(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    outHasValue,
) { if (it.value.pendingSignInUrl == null) 0 else 1 }

@CName("codex_agent_authentication_state_pending_sign_in_url")
public fun codexAgentAuthenticationStatePendingSignInUrl(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outUrl: CPointer<COpaquePointerVar>?,
): Int = authenticationStateUrl(context, state, outUrl) { it.pendingSignInUrl }

@CName("codex_agent_authentication_state_has_device_verification_url")
public fun codexAgentAuthenticationStateHasDeviceVerificationUrl(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    outHasValue,
) { if (it.value.deviceVerificationUrl == null) 0 else 1 }

@CName("codex_agent_authentication_state_device_verification_url")
public fun codexAgentAuthenticationStateDeviceVerificationUrl(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outUrl: CPointer<COpaquePointerVar>?,
): Int = authenticationStateUrl(context, state, outUrl) { it.deviceVerificationUrl }

@CName("codex_agent_authentication_state_has_device_user_code")
public fun codexAgentAuthenticationStateHasDeviceUserCode(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    outHasValue,
) { if (it.value.deviceUserCode == null) 0 else 1 }

@CName("codex_agent_authentication_state_device_user_code_copy")
public fun codexAgentAuthenticationStateDeviceUserCodeCopy(
    context: COpaquePointer?,
    state: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationOptionalString<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    buffer,
    capacity,
    outRequired,
) { it.value.deviceUserCode }

@CName("codex_agent_authentication_state_has_failure")
public fun codexAgentAuthenticationStateHasFailure(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthenticationStateValueSnapshot>(
    context,
    state,
    outHasValue,
) { if (it.value.failure == null) 0 else 1 }

@CName("codex_agent_authentication_state_failure")
public fun codexAgentAuthenticationStateFailure(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outFailure: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outFailure)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAuthenticationStateValueSnapshot>(
        contextPointer,
        state,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = it.value.failure ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(outFailure, createFailure(contextPointer, value.copy()))
    }
}

@CName("codex_agent_conversation_settings_create")
public fun codexAgentConversationSettingsCreate(
    context: COpaquePointer?,
    approvalPreset: Int,
    hasServiceTier: Int,
    serviceTier: CPointer<codex_agent_string_view>?,
    outSettings: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSettings)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = AgentConversationSettings(
        approvalPreset = approvalPresetFromConfigurationC(approvalPreset),
        serviceTier = serviceTier.readAuthenticationConfigurationOptionalUtf8(hasServiceTier),
    )
    installOutput(
        outSettings,
        createSnapshot(contextPointer, CodexAgentCConversationSettingsSnapshot(value.copy())),
    )
}

@CName("codex_agent_conversation_settings_destroy")
public fun codexAgentConversationSettingsDestroy(
    context: COpaquePointer?,
    settings: CPointer<COpaquePointerVar>?,
): Int = destroyAuthenticationConfigurationSnapshot<CodexAgentCConversationSettingsSnapshot>(
    context,
    settings,
)

@CName("codex_agent_conversation_settings_approval_preset")
public fun codexAgentConversationSettingsApprovalPreset(
    context: COpaquePointer?,
    settings: COpaquePointer?,
    outApprovalPreset: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCConversationSettingsSnapshot>(
    context,
    settings,
    outApprovalPreset,
) { approvalPresetToConfigurationC(it.value.approvalPreset) }

@CName("codex_agent_conversation_settings_has_service_tier")
public fun codexAgentConversationSettingsHasServiceTier(
    context: COpaquePointer?,
    settings: COpaquePointer?,
    outHasValue: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCConversationSettingsSnapshot>(
    context,
    settings,
    outHasValue,
) { if (it.value.serviceTier == null) 0 else 1 }

@CName("codex_agent_conversation_settings_service_tier_copy")
public fun codexAgentConversationSettingsServiceTierCopy(
    context: COpaquePointer?,
    settings: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationOptionalString<CodexAgentCConversationSettingsSnapshot>(
    context,
    settings,
    buffer,
    capacity,
    outRequired,
) { it.value.serviceTier }

@CName("codex_agent_authorization_url_chat_gpt")
public fun codexAgentAuthorizationUrlChatGpt(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outUrl: CPointer<COpaquePointerVar>?,
): Int = createAuthorizationUrl(context, value, outUrl) { CodexAuthorizationUrl.chatGpt(it) }

@CName("codex_agent_authorization_url_external")
public fun codexAgentAuthorizationUrlExternal(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outUrl: CPointer<COpaquePointerVar>?,
): Int = createAuthorizationUrl(context, value, outUrl) { CodexAuthorizationUrl.external(it) }

@CName("codex_agent_authorization_url_destroy")
public fun codexAgentAuthorizationUrlDestroy(
    context: COpaquePointer?,
    url: CPointer<COpaquePointerVar>?,
): Int = destroyAuthenticationConfigurationSnapshot<CodexAgentCAuthorizationUrlSnapshot>(context, url)

@CName("codex_agent_authorization_url_value_copy")
public fun codexAgentAuthorizationUrlValueCopy(
    context: COpaquePointer?,
    url: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationString<CodexAgentCAuthorizationUrlSnapshot>(
    context,
    url,
    buffer,
    capacity,
    outRequired,
) { it.value.value }

@CName("codex_agent_authorization_url_purpose")
public fun codexAgentAuthorizationUrlPurpose(
    context: COpaquePointer?,
    url: COpaquePointer?,
    outPurpose: CPointer<IntVar>?,
): Int = authenticationConfigurationInt<CodexAgentCAuthorizationUrlSnapshot>(
    context,
    url,
    outPurpose,
) { authorizationPurposeToConfigurationC(it.value.purpose) }

@CName("codex_agent_client_info_value_create")
public fun codexAgentClientInfoValueCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    title: CPointer<codex_agent_string_view>?,
    version: CPointer<codex_agent_string_view>?,
    outClientInfo: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outClientInfo)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = CodexClientInfo(
        name = name.readAuthenticationConfigurationRequiredUtf8(),
        title = title.readAuthenticationConfigurationRequiredUtf8(),
        version = version.readAuthenticationConfigurationRequiredUtf8(),
    )
    installOutput(
        outClientInfo,
        createSnapshot(contextPointer, CodexAgentCClientInfoValueSnapshot(value.copy())),
    )
}

@CName("codex_agent_client_info_value_destroy")
public fun codexAgentClientInfoValueDestroy(
    context: COpaquePointer?,
    clientInfo: CPointer<COpaquePointerVar>?,
): Int = destroyAuthenticationConfigurationSnapshot<CodexAgentCClientInfoValueSnapshot>(
    context,
    clientInfo,
)

@CName("codex_agent_client_info_value_name_copy")
public fun codexAgentClientInfoValueNameCopy(
    context: COpaquePointer?, clientInfo: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationString<CodexAgentCClientInfoValueSnapshot>(
    context, clientInfo, buffer, capacity, outRequired,
) { it.value.name }

@CName("codex_agent_client_info_value_title_copy")
public fun codexAgentClientInfoValueTitleCopy(
    context: COpaquePointer?, clientInfo: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationString<CodexAgentCClientInfoValueSnapshot>(
    context, clientInfo, buffer, capacity, outRequired,
) { it.value.title }

@CName("codex_agent_client_info_value_version_copy")
public fun codexAgentClientInfoValueVersionCopy(
    context: COpaquePointer?, clientInfo: COpaquePointer?, buffer: CPointer<UByteVar>?,
    capacity: ULong, outRequired: CPointer<ULongVar>?,
): Int = copyAuthenticationConfigurationString<CodexAgentCClientInfoValueSnapshot>(
    context, clientInfo, buffer, capacity, outRequired,
) { it.value.version }

private fun createAuthorizationUrl(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outUrl: CPointer<COpaquePointerVar>?,
    create: (String) -> CodexAuthorizationUrl,
): Int = abiStatus {
    if (!validEmptyOutput(outUrl)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outUrl,
        createSnapshot(
            contextPointer,
            CodexAgentCAuthorizationUrlSnapshot(
                create(value.readAuthenticationConfigurationRequiredUtf8()),
            ),
        ),
    )
}

private fun authenticationStateUrl(
    context: COpaquePointer?,
    state: COpaquePointer?,
    outUrl: CPointer<COpaquePointerVar>?,
    select: (AgentAuthenticationState) -> CodexAuthorizationUrl?,
): Int = abiStatus {
    if (!validEmptyOutput(outUrl)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCAuthenticationStateValueSnapshot>(
        contextPointer,
        state,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = select(it.value) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        installOutput(
            outUrl,
            createSnapshot(
                contextPointer,
                CodexAgentCAuthorizationUrlSnapshot(value.authenticationConfigurationCopy()),
            ),
        )
    }
}

private inline fun <reified T : CodexAgentCSnapshot> destroyAuthenticationConfigurationSnapshot(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val status = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (status == CODEX_AGENT_STATUS_OK) {
        releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
    } else {
        status
    }
}

private inline fun <reified T : CodexAgentCSnapshot> authenticationConfigurationInt(
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

private inline fun <reified T : CodexAgentCSnapshot> copyAuthenticationConfigurationString(
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

private inline fun <reified T : CodexAgentCSnapshot> copyAuthenticationConfigurationOptionalString(
    context: COpaquePointer?,
    handle: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (T) -> String?,
): Int = abiStatus {
    withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        val value = select(it) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun CPointer<codex_agent_string_view>?.readAuthenticationConfigurationRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readAuthenticationConfigurationOptionalUtf8(
    hasValue: Int,
): String? {
    requireAuthenticationConfigurationFlag(hasValue)
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0uL)
        return null
    }
    return view.readUtf8()
}

private fun requireAuthenticationConfigurationFlag(value: Int) {
    require(value == 0 || value == 1)
}

private fun authenticationStatusFromConfigurationC(value: Int): AgentAuthenticationStatus = when (value) {
    0 -> AgentAuthenticationStatus.SIGNED_OUT
    1 -> AgentAuthenticationStatus.AUTHENTICATING
    2 -> AgentAuthenticationStatus.AUTHENTICATED
    else -> throw IllegalArgumentException("Unknown authentication status")
}

private fun authenticationStatusToConfigurationC(value: AgentAuthenticationStatus): Int = when (value) {
    AgentAuthenticationStatus.SIGNED_OUT -> 0
    AgentAuthenticationStatus.AUTHENTICATING -> 1
    AgentAuthenticationStatus.AUTHENTICATED -> 2
}

private fun approvalPresetFromConfigurationC(value: Int): AgentApprovalPreset = when (value) {
    0 -> AgentApprovalPreset.NEVER
    1 -> AgentApprovalPreset.AUTO_REVIEW
    2 -> AgentApprovalPreset.ASK_ME
    3 -> AgentApprovalPreset.STRICT
    else -> throw IllegalArgumentException("Unknown approval preset")
}

private fun approvalPresetToConfigurationC(value: AgentApprovalPreset): Int = when (value) {
    AgentApprovalPreset.NEVER -> 0
    AgentApprovalPreset.AUTO_REVIEW -> 1
    AgentApprovalPreset.ASK_ME -> 2
    AgentApprovalPreset.STRICT -> 3
}

private fun authorizationPurposeToConfigurationC(value: CodexAuthorizationPurpose): Int = when (value) {
    CodexAuthorizationPurpose.CHAT_GPT -> 0
    CodexAuthorizationPurpose.EXTERNAL -> 1
}

private fun CodexAuthorizationUrl.authenticationConfigurationCopy(): CodexAuthorizationUrl = when (purpose) {
    CodexAuthorizationPurpose.CHAT_GPT -> CodexAuthorizationUrl.chatGpt(value)
    CodexAuthorizationPurpose.EXTERNAL -> CodexAuthorizationUrl.external(value)
}
