@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentInvocation
import io.github.codex_agent_labs.codexmobile.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthenticationMethod
import io.github.codex_agent_labs.codexmobile.agent.CodexInteractions
import io.github.codex_agent_labs.codexmobile.agent.ConversationId
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCInvocationPluginSnapshot(
    val value: AgentInvocation.Plugin,
) : CodexAgentCSnapshot

internal data class CodexAgentCInvocationSkillSnapshot(
    val value: AgentInvocation.Skill,
) : CodexAgentCSnapshot

internal data class CodexAgentCPendingApprovalSnapshot(
    val value: AgentPendingApproval,
    val owner: CodexInteractions? = null,
) : CodexAgentCSnapshot

internal data class CodexAgentCApiKeyAuthenticationMethodSnapshot(
    val value: CodexAuthenticationMethod.ApiKey,
) : CodexAgentCSnapshot

internal data class CodexAgentCChatGptBrowserAuthenticationMethodSnapshot(
    val value: CodexAuthenticationMethod.ChatGptBrowser,
) : CodexAgentCSnapshot

internal data class CodexAgentCChatGptDeviceCodeAuthenticationMethodSnapshot(
    val value: CodexAuthenticationMethod.ChatGptDeviceCode,
) : CodexAgentCSnapshot

@CName("codex_agent_invocation_plugin_create")
public fun codexAgentInvocationPluginCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    uri: CPointer<codex_agent_string_view>?,
    outPlugin: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outPlugin)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = AgentInvocation.Plugin(name.readRequiredUtf8(), uri.readRequiredUtf8())
    installOutput(
        outPlugin,
        createSnapshot(contextPointer, CodexAgentCInvocationPluginSnapshot(value)),
    )
}

@CName("codex_agent_invocation_plugin_destroy")
public fun codexAgentInvocationPluginDestroy(
    context: COpaquePointer?,
    plugin: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCInvocationPluginSnapshot>(context, plugin)

@CName("codex_agent_invocation_plugin_name_copy")
public fun codexAgentInvocationPluginNameCopy(
    context: COpaquePointer?,
    plugin: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationPluginSnapshot>(
    context,
    plugin,
    buffer,
    capacity,
    outRequired,
) { it.value.name }

@CName("codex_agent_invocation_plugin_uri_copy")
public fun codexAgentInvocationPluginUriCopy(
    context: COpaquePointer?,
    plugin: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationPluginSnapshot>(
    context,
    plugin,
    buffer,
    capacity,
    outRequired,
) { it.value.uri }

@CName("codex_agent_invocation_plugin_key_copy")
public fun codexAgentInvocationPluginKeyCopy(
    context: COpaquePointer?,
    plugin: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationPluginSnapshot>(
    context,
    plugin,
    buffer,
    capacity,
    outRequired,
) { it.value.key }

@CName("codex_agent_invocation_skill_create")
public fun codexAgentInvocationSkillCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    path: CPointer<codex_agent_string_view>?,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSkill)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = AgentInvocation.Skill(name.readRequiredUtf8(), path.readRequiredUtf8())
    installOutput(
        outSkill,
        createSnapshot(contextPointer, CodexAgentCInvocationSkillSnapshot(value)),
    )
}

@CName("codex_agent_invocation_skill_destroy")
public fun codexAgentInvocationSkillDestroy(
    context: COpaquePointer?,
    skill: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCInvocationSkillSnapshot>(context, skill)

@CName("codex_agent_invocation_skill_name_copy")
public fun codexAgentInvocationSkillNameCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationSkillSnapshot>(
    context,
    skill,
    buffer,
    capacity,
    outRequired,
) { it.value.name }

@CName("codex_agent_invocation_skill_path_copy")
public fun codexAgentInvocationSkillPathCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationSkillSnapshot>(
    context,
    skill,
    buffer,
    capacity,
    outRequired,
) { it.value.path }

@CName("codex_agent_invocation_skill_key_copy")
public fun codexAgentInvocationSkillKeyCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCInvocationSkillSnapshot>(
    context,
    skill,
    buffer,
    capacity,
    outRequired,
) { it.value.key }

@CName("codex_agent_pending_approval_create")
public fun codexAgentPendingApprovalCreate(
    context: COpaquePointer?,
    requestId: CPointer<codex_agent_string_view>?,
    conversationId: COpaquePointer?,
    title: CPointer<codex_agent_string_view>?,
    details: CPointer<codex_agent_string_view>?,
    outApproval: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outApproval)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val copiedRequestId = requestId.readRequiredUtf8()
    val copiedTitle = title.readRequiredUtf8()
    val copiedDetails = details.readRequiredUtf8()
    withPayload<CodexAgentCConversationIdSnapshot>(
        contextPointer,
        conversationId,
        CodexAgentCHandleKind.SNAPSHOT,
    ) { id ->
        val value = AgentPendingApproval(
            requestId = copiedRequestId,
            conversationId = ConversationId(id.value.value),
            title = copiedTitle,
            details = copiedDetails,
        )
        installOutput(
            outApproval,
            createSnapshot(contextPointer, CodexAgentCPendingApprovalSnapshot(value)),
        )
    }
}

@CName("codex_agent_pending_approval_destroy")
public fun codexAgentPendingApprovalDestroy(
    context: COpaquePointer?,
    approval: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCPendingApprovalSnapshot>(context, approval)

@CName("codex_agent_pending_approval_request_id_copy")
public fun codexAgentPendingApprovalRequestIdCopy(
    context: COpaquePointer?,
    approval: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCPendingApprovalSnapshot>(
    context,
    approval,
    buffer,
    capacity,
    outRequired,
) { it.value.requestId }

@CName("codex_agent_pending_approval_conversation_id")
public fun codexAgentPendingApprovalConversationId(
    context: COpaquePointer?,
    approval: COpaquePointer?,
    outConversationId: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outConversationId)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPendingApprovalSnapshot>(
        contextPointer,
        approval,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        installOutput(
            outConversationId,
            createSnapshot(
                contextPointer,
                CodexAgentCConversationIdSnapshot(ConversationId(it.value.conversationId.value)),
            ),
        )
    }
}

@CName("codex_agent_pending_approval_title_copy")
public fun codexAgentPendingApprovalTitleCopy(
    context: COpaquePointer?,
    approval: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCPendingApprovalSnapshot>(
    context,
    approval,
    buffer,
    capacity,
    outRequired,
) { it.value.title }

@CName("codex_agent_pending_approval_details_copy")
public fun codexAgentPendingApprovalDetailsCopy(
    context: COpaquePointer?,
    approval: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCPendingApprovalSnapshot>(
    context,
    approval,
    buffer,
    capacity,
    outRequired,
) { it.value.details }

@CName("codex_agent_authentication_method_api_key_create")
public fun codexAgentAuthenticationMethodApiKeyCreate(
    context: COpaquePointer?,
    value: CPointer<codex_agent_string_view>?,
    outMethod: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMethod)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val method = CodexAuthenticationMethod.ApiKey(value.readRequiredUtf8())
    installOutput(
        outMethod,
        createSnapshot(contextPointer, CodexAgentCApiKeyAuthenticationMethodSnapshot(method)),
    )
}

@CName("codex_agent_authentication_method_api_key_destroy")
public fun codexAgentAuthenticationMethodApiKeyDestroy(
    context: COpaquePointer?,
    method: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCApiKeyAuthenticationMethodSnapshot>(context, method)

@CName("codex_agent_authentication_method_api_key_value_copy")
public fun codexAgentAuthenticationMethodApiKeyValueCopy(
    context: COpaquePointer?,
    method: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyInvocationAuthString<CodexAgentCApiKeyAuthenticationMethodSnapshot>(
    context,
    method,
    buffer,
    capacity,
    outRequired,
) { it.value.value }

@CName("codex_agent_authentication_method_chat_gpt_browser_create")
public fun codexAgentAuthenticationMethodChatGptBrowserCreate(
    context: COpaquePointer?,
    outMethod: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMethod)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outMethod,
        createSnapshot(
            contextPointer,
            CodexAgentCChatGptBrowserAuthenticationMethodSnapshot(
                CodexAuthenticationMethod.ChatGptBrowser,
            ),
        ),
    )
}

@CName("codex_agent_authentication_method_chat_gpt_browser_destroy")
public fun codexAgentAuthenticationMethodChatGptBrowserDestroy(
    context: COpaquePointer?,
    method: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCChatGptBrowserAuthenticationMethodSnapshot>(
    context,
    method,
)

@CName("codex_agent_authentication_method_chat_gpt_device_code_create")
public fun codexAgentAuthenticationMethodChatGptDeviceCodeCreate(
    context: COpaquePointer?,
    outMethod: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outMethod)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    installOutput(
        outMethod,
        createSnapshot(
            contextPointer,
            CodexAgentCChatGptDeviceCodeAuthenticationMethodSnapshot(
                CodexAuthenticationMethod.ChatGptDeviceCode,
            ),
        ),
    )
}

@CName("codex_agent_authentication_method_chat_gpt_device_code_destroy")
public fun codexAgentAuthenticationMethodChatGptDeviceCodeDestroy(
    context: COpaquePointer?,
    method: CPointer<COpaquePointerVar>?,
): Int = destroyInvocationAuthValue<CodexAgentCChatGptDeviceCodeAuthenticationMethodSnapshot>(
    context,
    method,
)

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private inline fun <reified T : CodexAgentCSnapshot> destroyInvocationAuthValue(
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

private inline fun <reified T : CodexAgentCSnapshot> copyInvocationAuthString(
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
