@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCInvocationAuthValuesTest {
    @Test
    fun invocationLeavesCopyInputsAndProjectCanonicalKeys() = memScoped {
        val firstContextSlot = createInvocationAuthContext()
        val secondContextSlot = createInvocationAuthContext()
        val firstContext = assertNotNull(firstContextSlot.value)
        val secondContext = assertNotNull(secondContextSlot.value)
        val pluginSlot = emptyHandleSlot()
        val skillSlot = emptyHandleSlot()
        try {
            val pluginName = mutableInvocationAuthStringView("review-tools")
            val pluginUri = mutableInvocationAuthStringView("plugin://review@official")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPluginCreate(
                    firstContext,
                    pluginName.view,
                    pluginUri.view,
                    pluginSlot.ptr,
                ),
            )
            val plugin = assertNotNull(pluginSlot.value)
            pluginName.bytes[0] = 'X'.code.toUByte()
            pluginUri.bytes[0] = 'X'.code.toUByte()
            assertInvocationAuthString(
                firstContext,
                plugin,
                "review-tools",
                ::codexAgentInvocationPluginNameCopy,
            )
            assertInvocationAuthString(
                firstContext,
                plugin,
                "plugin://review@official",
                ::codexAgentInvocationPluginUriCopy,
            )
            assertInvocationAuthString(
                firstContext,
                plugin,
                "plugin:plugin://review@official",
                ::codexAgentInvocationPluginKeyCopy,
            )

            val skillName = mutableInvocationAuthStringView("review")
            val skillPath = mutableInvocationAuthStringView("/skills/review.md")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationSkillCreate(
                    firstContext,
                    skillName.view,
                    skillPath.view,
                    skillSlot.ptr,
                ),
            )
            val skill = assertNotNull(skillSlot.value)
            skillName.bytes[0] = 'X'.code.toUByte()
            skillPath.bytes[0] = 'X'.code.toUByte()
            assertInvocationAuthString(
                firstContext,
                skill,
                "review",
                ::codexAgentInvocationSkillNameCopy,
            )
            assertInvocationAuthString(
                firstContext,
                skill,
                "/skills/review.md",
                ::codexAgentInvocationSkillPathCopy,
            )
            assertInvocationAuthString(
                firstContext,
                skill,
                "skill:/skills/review.md",
                ::codexAgentInvocationSkillKeyCopy,
            )

            val required = alloc<ULongVar>().also { it.value = 73uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInvocationPluginNameCopy(firstContext, skill, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInvocationPluginNameCopy(secondContext, plugin, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)

            val wrongDestroy = alloc<COpaquePointerVar>().also { it.value = skill }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInvocationPluginDestroy(firstContext, wrongDestroy.ptr),
            )
            assertEquals(skill, wrongDestroy.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationPluginCreate(
                    firstContext,
                    invocationAuthStringView("occupied"),
                    invocationAuthStringView("plugin://occupied"),
                    pluginSlot.ptr,
                ),
            )
            assertEquals(plugin, pluginSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationSkillCreate(
                    firstContext,
                    invocationAuthStringView("missing-output"),
                    invocationAuthStringView("/missing-output"),
                    null,
                ),
            )

            val invalidSlot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationPluginCreate(
                    firstContext,
                    null,
                    invocationAuthStringView("plugin://null"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationPluginCreate(
                    firstContext,
                    invocationAuthStringView("invalid"),
                    invalidInvocationAuthUtf8View(),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationSkillCreate(
                    firstContext,
                    null,
                    invocationAuthStringView("/null"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationSkillCreate(
                    firstContext,
                    invocationAuthStringView("invalid"),
                    invalidInvocationAuthUtf8View(),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationPluginCreate(
                    null,
                    invocationAuthStringView("null-context"),
                    invocationAuthStringView("plugin://null-context"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)

            val stalePlugin = plugin
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPluginDestroy(firstContext, pluginSlot.ptr),
            )
            assertNull(pluginSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPluginDestroy(firstContext, pluginSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInvocationPluginKeyCopy(
                    firstContext,
                    stalePlugin,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationSkillDestroy(firstContext, skillSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationSkillDestroy(firstContext, skillSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPluginDestroy(firstContext, pluginSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(firstContextSlot.ptr))
        }
    }

    @Test
    fun pendingApprovalOwnsIndependentConversationIdSnapshots() = memScoped {
        val firstContextSlot = createInvocationAuthContext()
        val secondContextSlot = createInvocationAuthContext()
        val firstContext = assertNotNull(firstContextSlot.value)
        val secondContext = assertNotNull(secondContextSlot.value)
        val conversationIdSlot = emptyHandleSlot()
        val otherConversationIdSlot = emptyHandleSlot()
        val approvalSlot = emptyHandleSlot()
        val firstNestedSlot = emptyHandleSlot()
        val secondNestedSlot = emptyHandleSlot()
        try {
            val conversationIdInput = mutableInvocationAuthStringView("conversation-17")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdCreate(
                    firstContext,
                    conversationIdInput.view,
                    conversationIdSlot.ptr,
                ),
            )
            val originalConversationId = assertNotNull(conversationIdSlot.value)
            val requestId = mutableInvocationAuthStringView("approval-9")
            val title = mutableInvocationAuthStringView("Run command?")
            val details = mutableInvocationAuthStringView("git status")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    requestId.view,
                    originalConversationId,
                    title.view,
                    details.view,
                    approvalSlot.ptr,
                ),
            )
            val approval = assertNotNull(approvalSlot.value)
            requestId.bytes[0] = 'X'.code.toUByte()
            title.bytes[0] = 'X'.code.toUByte()
            details.bytes[0] = 'X'.code.toUByte()
            conversationIdInput.bytes[0] = 'X'.code.toUByte()

            assertInvocationAuthString(
                firstContext,
                approval,
                "approval-9",
                ::codexAgentPendingApprovalRequestIdCopy,
            )
            assertInvocationAuthString(
                firstContext,
                approval,
                "Run command?",
                ::codexAgentPendingApprovalTitleCopy,
            )
            assertInvocationAuthString(
                firstContext,
                approval,
                "git status",
                ::codexAgentPendingApprovalDetailsCopy,
            )

            val invalidSlot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    null,
                    originalConversationId,
                    invocationAuthStringView("title"),
                    invocationAuthStringView("details"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    invocationAuthStringView("request"),
                    originalConversationId,
                    invocationAuthStringView("title"),
                    invalidInvocationAuthUtf8View(),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    invocationAuthStringView("request"),
                    null,
                    invocationAuthStringView("title"),
                    invocationAuthStringView("details"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    invocationAuthStringView("occupied"),
                    originalConversationId,
                    invocationAuthStringView("occupied"),
                    invocationAuthStringView("occupied"),
                    approvalSlot.ptr,
                ),
            )
            assertEquals(approval, approvalSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalCreate(
                    null,
                    invocationAuthStringView("request"),
                    originalConversationId,
                    invocationAuthStringView("title"),
                    invocationAuthStringView("details"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdCreate(
                    secondContext,
                    invocationAuthStringView("other-conversation"),
                    otherConversationIdSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentPendingApprovalCreate(
                    firstContext,
                    invocationAuthStringView("request"),
                    assertNotNull(otherConversationIdSlot.value),
                    invocationAuthStringView("title"),
                    invocationAuthStringView("details"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(firstContext, conversationIdSlot.ptr),
            )
            assertNull(conversationIdSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalConversationId(
                    firstContext,
                    approval,
                    firstNestedSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalConversationId(
                    firstContext,
                    approval,
                    secondNestedSlot.ptr,
                ),
            )
            val firstNested = assertNotNull(firstNestedSlot.value)
            val secondNested = assertNotNull(secondNestedSlot.value)
            assertNotEquals(originalConversationId, firstNested)
            assertNotEquals(firstNested, secondNested)

            val occupiedNested = alloc<COpaquePointerVar>().also { it.value = firstNested }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingApprovalConversationId(
                    firstContext,
                    approval,
                    occupiedNested.ptr,
                ),
            )
            assertEquals(firstNested, occupiedNested.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPendingApprovalConversationId(
                    firstContext,
                    firstNested,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)

            val required = alloc<ULongVar>().also { it.value = 89uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentPendingApprovalRequestIdCopy(
                    secondContext,
                    approval,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(89uL, required.value)
            val wrongDestroy = alloc<COpaquePointerVar>().also { it.value = firstNested }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPendingApprovalDestroy(firstContext, wrongDestroy.ptr),
            )
            assertEquals(firstNested, wrongDestroy.value)

            val staleApproval = approval
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalDestroy(firstContext, approvalSlot.ptr),
            )
            assertNull(approvalSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalDestroy(firstContext, approvalSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentPendingApprovalRequestIdCopy(
                    firstContext,
                    staleApproval,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertInvocationAuthString(
                firstContext,
                firstNested,
                "conversation-17",
                ::codexAgentConversationIdValueCopy,
            )
            assertInvocationAuthString(
                firstContext,
                secondNested,
                "conversation-17",
                ::codexAgentConversationIdValueCopy,
            )
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(firstContext, firstNestedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(firstContext, firstNestedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(firstContext, secondNestedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingApprovalDestroy(firstContext, approvalSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(firstContext, conversationIdSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdDestroy(secondContext, otherConversationIdSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(firstContextSlot.ptr))
        }
    }

    @Test
    fun authenticationMethodLeavesValidateSecretsAndOwnDistinctHandles() = memScoped {
        val firstContextSlot = createInvocationAuthContext()
        val secondContextSlot = createInvocationAuthContext()
        val firstContext = assertNotNull(firstContextSlot.value)
        val secondContext = assertNotNull(secondContextSlot.value)
        val apiKeySlot = emptyHandleSlot()
        val firstBrowserSlot = emptyHandleSlot()
        val secondBrowserSlot = emptyHandleSlot()
        val deviceCodeSlot = emptyHandleSlot()
        try {
            val secret = mutableInvocationAuthStringView("sk-live-secret")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodApiKeyCreate(
                    firstContext,
                    secret.view,
                    apiKeySlot.ptr,
                ),
            )
            val apiKey = assertNotNull(apiKeySlot.value)
            secret.bytes[0] = 'X'.code.toUByte()
            assertInvocationAuthString(
                firstContext,
                apiKey,
                "sk-live-secret",
                ::codexAgentAuthenticationMethodApiKeyValueCopy,
            )

            val invalidSlot = emptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodApiKeyCreate(firstContext, null, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodApiKeyCreate(
                    firstContext,
                    invalidInvocationAuthUtf8View(),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodApiKeyCreate(
                    firstContext,
                    invocationAuthStringView(" \t\n"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodApiKeyCreate(
                    firstContext,
                    invocationAuthStringView("not-installed"),
                    apiKeySlot.ptr,
                ),
            )
            assertEquals(apiKey, apiKeySlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptBrowserCreate(
                    firstContext,
                    firstBrowserSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptBrowserCreate(
                    firstContext,
                    secondBrowserSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptDeviceCodeCreate(
                    firstContext,
                    deviceCodeSlot.ptr,
                ),
            )
            val firstBrowser = assertNotNull(firstBrowserSlot.value)
            val secondBrowser = assertNotNull(secondBrowserSlot.value)
            val deviceCode = assertNotNull(deviceCodeSlot.value)
            assertNotEquals(firstBrowser, secondBrowser)
            assertNotEquals(firstBrowser, deviceCode)
            assertNotEquals(secondBrowser, deviceCode)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodChatGptBrowserCreate(
                    firstContext,
                    firstBrowserSlot.ptr,
                ),
            )
            assertEquals(firstBrowser, firstBrowserSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationMethodChatGptDeviceCodeCreate(null, invalidSlot.ptr),
            )
            assertNull(invalidSlot.value)

            val required = alloc<ULongVar>().also { it.value = 97uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationMethodApiKeyValueCopy(
                    firstContext,
                    firstBrowser,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationMethodApiKeyValueCopy(
                    secondContext,
                    apiKey,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)

            val wrongDestroy = alloc<COpaquePointerVar>().also { it.value = deviceCode }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationMethodChatGptBrowserDestroy(
                    firstContext,
                    wrongDestroy.ptr,
                ),
            )
            assertEquals(deviceCode, wrongDestroy.value)

            val staleApiKey = apiKey
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodApiKeyDestroy(firstContext, apiKeySlot.ptr),
            )
            assertNull(apiKeySlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodApiKeyDestroy(firstContext, apiKeySlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationMethodApiKeyValueCopy(
                    firstContext,
                    staleApiKey,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(97uL, required.value)
        } finally {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodApiKeyDestroy(firstContext, apiKeySlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptBrowserDestroy(
                    firstContext,
                    firstBrowserSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptBrowserDestroy(
                    firstContext,
                    firstBrowserSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptBrowserDestroy(
                    firstContext,
                    secondBrowserSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptDeviceCodeDestroy(
                    firstContext,
                    deviceCodeSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationMethodChatGptDeviceCodeDestroy(
                    firstContext,
                    deviceCodeSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(firstContextSlot.ptr))
        }
    }
}

private fun MemScope.createInvocationAuthContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyHandleSlot(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.invocationAuthStringView(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = value.encodeToByteArray()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
        view.size = bytes.size.toULong()
    }.ptr

private fun MemScope.mutableInvocationAuthStringView(value: String): InvocationAuthMutableStringView {
    val bytes = value.encodeToByteArray()
    require(bytes.isNotEmpty())
    val buffer = allocArray<UByteVar>(bytes.size)
    bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    return InvocationAuthMutableStringView(
        view = alloc<codex_agent_string_view>().also {
            it.data = buffer
            it.size = bytes.size.toULong()
        }.ptr,
        bytes = buffer,
    )
}

private fun MemScope.invalidInvocationAuthUtf8View(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = allocArray<UByteVar>(2)
        bytes[0] = 0xc3u
        bytes[1] = 0x28u
        view.data = bytes
        view.size = 2uL
    }.ptr

private fun MemScope.assertInvocationAuthString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: InvocationAuthStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private typealias InvocationAuthStringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private data class InvocationAuthMutableStringView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>,
)
