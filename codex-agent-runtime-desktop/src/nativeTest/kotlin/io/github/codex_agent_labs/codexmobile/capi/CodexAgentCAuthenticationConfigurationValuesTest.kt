@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
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

class CodexAgentCAuthenticationConfigurationValuesTest {
    @Test
    fun authenticationStateAndConversationSettingsProjectDefaultsNullabilityAndEveryEnum() = memScoped {
        val contextSlot = createAuthenticationConfigurationContext()
        val context = assertNotNull(contextSlot.value)
        val absent = authenticationConfigurationAbsentView()
        try {
            (0..2).forEach { expectedStatus ->
                val stateSlot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateCreate(
                        context,
                        expectedStatus,
                        0,
                        null,
                        0,
                        null,
                        0,
                        absent,
                        0,
                        null,
                        stateSlot.ptr,
                    ),
                )
                val state = assertNotNull(stateSlot.value)
                val projected = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateStatus(context, state, projected.ptr),
                )
                assertEquals(expectedStatus, projected.value)
                listOf(
                    ::codexAgentAuthenticationStateHasPendingSignInUrl,
                    ::codexAgentAuthenticationStateHasDeviceVerificationUrl,
                    ::codexAgentAuthenticationStateHasDeviceUserCode,
                    ::codexAgentAuthenticationStateHasFailure,
                ).forEach { hasValue ->
                    projected.value = -1
                    assertEquals(CODEX_AGENT_STATUS_OK, hasValue(context, state, projected.ptr))
                    assertEquals(0, projected.value)
                }
                val missing = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_NOT_READY,
                    codexAgentAuthenticationStatePendingSignInUrl(context, state, missing.ptr),
                )
                assertNull(missing.value)
                assertEquals(
                    CODEX_AGENT_STATUS_NOT_READY,
                    codexAgentAuthenticationStateDeviceVerificationUrl(context, state, missing.ptr),
                )
                assertNull(missing.value)
                assertEquals(
                    CODEX_AGENT_STATUS_NOT_READY,
                    codexAgentAuthenticationStateFailure(context, state, missing.ptr),
                )
                assertNull(missing.value)
                val required = alloc<ULongVar>().also { it.value = 73uL }
                assertEquals(
                    CODEX_AGENT_STATUS_NOT_READY,
                    codexAgentAuthenticationStateDeviceUserCodeCopy(
                        context,
                        state,
                        null,
                        0uL,
                        required.ptr,
                    ),
                )
                assertEquals(73uL, required.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateDestroy(context, stateSlot.ptr),
                )
                assertNull(stateSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthenticationStateDestroy(context, stateSlot.ptr),
                )
            }

            val presentEmptyCodeStateSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateCreate(
                    context,
                    0,
                    0,
                    null,
                    0,
                    null,
                    1,
                    absent,
                    0,
                    null,
                    presentEmptyCodeStateSlot.ptr,
                ),
            )
            val presentEmptyCodeState = assertNotNull(presentEmptyCodeStateSlot.value)
            val present = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateHasDeviceUserCode(
                    context,
                    presentEmptyCodeState,
                    present.ptr,
                ),
            )
            assertEquals(1, present.value)
            assertAuthenticationConfigurationString(
                context,
                presentEmptyCodeState,
                "",
                ::codexAgentAuthenticationStateDeviceUserCodeCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateDestroy(context, presentEmptyCodeStateSlot.ptr),
            )

            (0..3).forEach { expectedPreset ->
                val tier = when (expectedPreset) {
                    0 -> mutableAuthenticationConfigurationStringView("")
                    1 -> null
                    else -> mutableAuthenticationConfigurationStringView("tier-$expectedPreset")
                }
                val settingsSlot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSettingsCreate(
                        context,
                        expectedPreset,
                        if (tier == null) 0 else 1,
                        tier?.view ?: absent,
                        settingsSlot.ptr,
                    ),
                )
                val settings = assertNotNull(settingsSlot.value)
                if (tier != null && tier.bytes != null) tier.bytes[0] = 'X'.code.toUByte()
                val projected = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSettingsApprovalPreset(context, settings, projected.ptr),
                )
                assertEquals(expectedPreset, projected.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSettingsHasServiceTier(context, settings, projected.ptr),
                )
                assertEquals(if (tier == null) 0 else 1, projected.value)
                if (tier == null) {
                    val required = alloc<ULongVar>().also { it.value = 91uL }
                    assertEquals(
                        CODEX_AGENT_STATUS_NOT_READY,
                        codexAgentConversationSettingsServiceTierCopy(
                            context,
                            settings,
                            null,
                            0uL,
                            required.ptr,
                        ),
                    )
                    assertEquals(91uL, required.value)
                } else {
                    assertAuthenticationConfigurationString(
                        context,
                        settings,
                        if (expectedPreset == 0) "" else "tier-$expectedPreset",
                        ::codexAgentConversationSettingsServiceTierCopy,
                    )
                }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSettingsDestroy(context, settingsSlot.ptr),
                )
                assertNull(settingsSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationSettingsDestroy(context, settingsSlot.ptr),
                )
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun authenticationStateOwnsFreshNestedUrlsFailureAndCopiedCode() = memScoped {
        val contextSlot = createAuthenticationConfigurationContext()
        val context = assertNotNull(contextSlot.value)
        val pendingSlot = authenticationConfigurationEmptyHandleSlot()
        val deviceSlot = authenticationConfigurationEmptyHandleSlot()
        val sourceFailureSlot = authenticationConfigurationEmptyHandleSlot()
        val stateSlot = authenticationConfigurationEmptyHandleSlot()
        val firstPendingSlot = authenticationConfigurationEmptyHandleSlot()
        val secondPendingSlot = authenticationConfigurationEmptyHandleSlot()
        val projectedDeviceSlot = authenticationConfigurationEmptyHandleSlot()
        val firstFailureSlot = authenticationConfigurationEmptyHandleSlot()
        val secondFailureSlot = authenticationConfigurationEmptyHandleSlot()
        try {
            val pendingInput = mutableAuthenticationConfigurationStringView(
                "https://auth.openai.com/authorize?client=native",
            )
            val deviceInput = mutableAuthenticationConfigurationStringView(
                "https://example.com/device",
            )
            val codeInput = mutableAuthenticationConfigurationStringView("ABCD-1234")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlChatGpt(context, pendingInput.view, pendingSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlExternal(context, deviceInput.view, deviceSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureCreate(
                    context,
                    authenticationConfigurationStringView("authentication_failed"),
                    authenticationConfigurationStringView("Authentication failed"),
                    1,
                    sourceFailureSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateCreate(
                    context,
                    1,
                    1,
                    assertNotNull(pendingSlot.value),
                    1,
                    assertNotNull(deviceSlot.value),
                    1,
                    codeInput.view,
                    1,
                    assertNotNull(sourceFailureSlot.value),
                    stateSlot.ptr,
                ),
            )
            val state = assertNotNull(stateSlot.value)
            pendingInput.bytes!![0] = 'X'.code.toUByte()
            deviceInput.bytes!![0] = 'X'.code.toUByte()
            codeInput.bytes!![0] = 'X'.code.toUByte()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, pendingSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, deviceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, sourceFailureSlot.ptr))

            val projected = alloc<IntVar>().also { it.value = -1 }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateStatus(context, state, projected.ptr),
            )
            assertEquals(1, projected.value)
            listOf(
                ::codexAgentAuthenticationStateHasPendingSignInUrl,
                ::codexAgentAuthenticationStateHasDeviceVerificationUrl,
                ::codexAgentAuthenticationStateHasDeviceUserCode,
                ::codexAgentAuthenticationStateHasFailure,
            ).forEach { hasValue ->
                projected.value = -1
                assertEquals(CODEX_AGENT_STATUS_OK, hasValue(context, state, projected.ptr))
                assertEquals(1, projected.value)
            }
            assertAuthenticationConfigurationString(
                context,
                state,
                "ABCD-1234",
                ::codexAgentAuthenticationStateDeviceUserCodeCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStatePendingSignInUrl(context, state, firstPendingSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStatePendingSignInUrl(context, state, secondPendingSlot.ptr),
            )
            assertNotEquals(firstPendingSlot.value, secondPendingSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateDeviceVerificationUrl(
                    context,
                    state,
                    projectedDeviceSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateFailure(context, state, firstFailureSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateFailure(context, state, secondFailureSlot.ptr),
            )
            assertNotEquals(firstFailureSlot.value, secondFailureSlot.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateDestroy(context, stateSlot.ptr),
            )
            assertAuthenticationConfigurationString(
                context,
                assertNotNull(firstPendingSlot.value),
                "https://auth.openai.com/authorize?client=native",
                ::codexAgentAuthorizationUrlValueCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlPurpose(context, firstPendingSlot.value, projected.ptr),
            )
            assertEquals(0, projected.value)
            assertAuthenticationConfigurationString(
                context,
                assertNotNull(secondPendingSlot.value),
                "https://auth.openai.com/authorize?client=native",
                ::codexAgentAuthorizationUrlValueCopy,
            )
            assertAuthenticationConfigurationString(
                context,
                assertNotNull(projectedDeviceSlot.value),
                "https://example.com/device",
                ::codexAgentAuthorizationUrlValueCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlPurpose(context, projectedDeviceSlot.value, projected.ptr),
            )
            assertEquals(1, projected.value)
            assertAuthenticationConfigurationString(
                context,
                assertNotNull(firstFailureSlot.value),
                "authentication_failed",
                ::codexAgentFailureCodeCopy,
            )
            assertAuthenticationConfigurationString(
                context,
                assertNotNull(secondFailureSlot.value),
                "Authentication failed",
                ::codexAgentFailureMessageCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureIsRecoverable(context, secondFailureSlot.value, projected.ptr),
            )
            assertEquals(1, projected.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateDestroy(context, stateSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, pendingSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, deviceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, firstPendingSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, secondPendingSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlDestroy(context, projectedDeviceSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, sourceFailureSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, firstFailureSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, secondFailureSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun authorizationUrlsAndClientInfoPreserveValuesAndRejectCanonicalInvalidInputs() = memScoped {
        val contextSlot = createAuthenticationConfigurationContext()
        val context = assertNotNull(contextSlot.value)
        try {
            listOf(
                "https://auth.openai.com/authorize?client=codex",
                "https://chatgpt.com/",
                "https://login.chatgpt.com:443/",
            ).forEach { value ->
                val input = mutableAuthenticationConfigurationStringView(value)
                val urlSlot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthorizationUrlChatGpt(context, input.view, urlSlot.ptr),
                )
                input.bytes!![0] = 'X'.code.toUByte()
                val purpose = alloc<IntVar>().also { it.value = -1 }
                assertAuthenticationConfigurationString(
                    context,
                    assertNotNull(urlSlot.value),
                    value,
                    ::codexAgentAuthorizationUrlValueCopy,
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthorizationUrlPurpose(context, urlSlot.value, purpose.ptr),
                )
                assertEquals(0, purpose.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, urlSlot.ptr))
            }
            listOf(
                "https://accounts.example.com/oauth",
                "http://localhost:8787/callback",
                "http://127.0.0.1:8787/callback",
                "http://[::1]:8787/callback",
            ).forEach { value ->
                val urlSlot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthorizationUrlExternal(
                        context,
                        authenticationConfigurationStringView(value),
                        urlSlot.ptr,
                    ),
                )
                val purpose = alloc<IntVar>().also { it.value = -1 }
                assertAuthenticationConfigurationString(
                    context,
                    assertNotNull(urlSlot.value),
                    value,
                    ::codexAgentAuthorizationUrlValueCopy,
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentAuthorizationUrlPurpose(context, urlSlot.value, purpose.ptr),
                )
                assertEquals(1, purpose.value)
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(context, urlSlot.ptr))
            }

            listOf(
                "http://auth.openai.com/",
                "https://openai.com.evil.example/",
                "https://evilopenai.com/",
                "https://user@openai.com/",
                "https://openai.com:444/",
                "https://openai.com:/",
                "https://openai.com./",
            ).forEach { rejected ->
                val slot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthorizationUrlChatGpt(
                        context,
                        authenticationConfigurationStringView(rejected),
                        slot.ptr,
                    ),
                    rejected,
                )
                assertNull(slot.value)
            }
            listOf(
                "http://192.168.1.2/login",
                "ftp://accounts.example.com/login",
                "https://user@accounts.example.com/login",
                "https://accounts.example.com:0/login",
                "https://accounts.example.com:65536/login",
                "https://accounts.example.com:/login",
                "https://accounts.example.com\\@evil.example/login",
                "https://accounts.example.com/space here",
            ).forEach { rejected ->
                val slot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentAuthorizationUrlExternal(
                        context,
                        authenticationConfigurationStringView(rejected),
                        slot.ptr,
                    ),
                    rejected,
                )
                assertNull(slot.value)
            }
            val malformedUrlSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlExternal(
                    context,
                    invalidAuthenticationConfigurationUtf8View(),
                    malformedUrlSlot.ptr,
                ),
            )
            assertNull(malformedUrlSlot.value)

            val name = mutableAuthenticationConfigurationStringView("codex_native")
            val title = mutableAuthenticationConfigurationStringView("Codex Native")
            val version = mutableAuthenticationConfigurationStringView("1.7")
            val clientSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentClientInfoValueCreate(
                    context,
                    name.view,
                    title.view,
                    version.view,
                    clientSlot.ptr,
                ),
            )
            name.bytes!![0] = 'X'.code.toUByte()
            title.bytes!![0] = 'X'.code.toUByte()
            version.bytes!![0] = 'X'.code.toUByte()
            val client = assertNotNull(clientSlot.value)
            assertAuthenticationConfigurationString(
                context,
                client,
                "codex_native",
                ::codexAgentClientInfoValueNameCopy,
            )
            assertAuthenticationConfigurationString(
                context,
                client,
                "Codex Native",
                ::codexAgentClientInfoValueTitleCopy,
            )
            assertAuthenticationConfigurationString(
                context,
                client,
                "1.7",
                ::codexAgentClientInfoValueVersionCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentClientInfoValueDestroy(context, clientSlot.ptr))
            assertNull(clientSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentClientInfoValueDestroy(context, clientSlot.ptr))

            listOf(
                Triple("", "App", "1"),
                Triple("app", "App\nName", "1"),
                Triple("app", "App", "1\u0000"),
            ).forEach { (invalidName, invalidTitle, invalidVersion) ->
                val slot = authenticationConfigurationEmptyHandleSlot()
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentClientInfoValueCreate(
                        context,
                        authenticationConfigurationStringView(invalidName),
                        authenticationConfigurationStringView(invalidTitle),
                        authenticationConfigurationStringView(invalidVersion),
                        slot.ptr,
                    ),
                )
                assertNull(slot.value)
            }
            val malformedClientSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentClientInfoValueCreate(
                    context,
                    invalidAuthenticationConfigurationUtf8View(),
                    authenticationConfigurationStringView("App"),
                    authenticationConfigurationStringView("1"),
                    malformedClientSlot.ptr,
                ),
            )
            assertNull(malformedClientSlot.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun authenticationConfigurationHandlesFailClosedAcrossTypeContextStaleAndTeardown() = memScoped {
        val firstContextSlot = createAuthenticationConfigurationContext()
        val secondContextSlot = createAuthenticationConfigurationContext()
        val firstContext = assertNotNull(firstContextSlot.value)
        val secondContext = assertNotNull(secondContextSlot.value)
        val absent = authenticationConfigurationAbsentView()
        val urlSlot = authenticationConfigurationEmptyHandleSlot()
        val settingsSlot = authenticationConfigurationEmptyHandleSlot()
        val stateSlot = authenticationConfigurationEmptyHandleSlot()
        val clientSlot = authenticationConfigurationEmptyHandleSlot()
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlExternal(
                    firstContext,
                    authenticationConfigurationStringView("https://example.com/sign-in"),
                    urlSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSettingsCreate(firstContext, 1, 0, absent, settingsSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateCreate(
                    firstContext,
                    0,
                    1,
                    assertNotNull(urlSlot.value),
                    0,
                    null,
                    0,
                    absent,
                    0,
                    null,
                    stateSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentClientInfoValueCreate(
                    firstContext,
                    authenticationConfigurationStringView("client"),
                    authenticationConfigurationStringView("Client"),
                    authenticationConfigurationStringView("1"),
                    clientSlot.ptr,
                ),
            )
            val state = assertNotNull(stateSlot.value)
            val settings = assertNotNull(settingsSlot.value)
            val url = assertNotNull(urlSlot.value)
            val client = assertNotNull(clientSlot.value)
            val projected = alloc<IntVar>().also { it.value = 73 }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationStateStatus(secondContext, state, projected.ptr),
            )
            assertEquals(73, projected.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateStatus(firstContext, settings, projected.ptr),
            )
            assertEquals(73, projected.value)
            val required = alloc<ULongVar>().also { it.value = 97uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthorizationUrlValueCopy(firstContext, client, null, 0uL, required.ptr),
            )
            assertEquals(97uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentClientInfoValueNameCopy(secondContext, client, null, 0uL, required.ptr),
            )
            assertEquals(97uL, required.value)

            val wrongDestroy = alloc<COpaquePointerVar>().also { it.value = settings }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateDestroy(firstContext, wrongDestroy.ptr),
            )
            assertEquals(settings, wrongDestroy.value)
            val wrongContextDestroy = alloc<COpaquePointerVar>().also { it.value = url }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthorizationUrlDestroy(secondContext, wrongContextDestroy.ptr),
            )
            assertEquals(url, wrongContextDestroy.value)
            val occupiedChild = alloc<COpaquePointerVar>().also { it.value = client }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStatePendingSignInUrl(
                    firstContext,
                    state,
                    occupiedChild.ptr,
                ),
            )
            assertEquals(client, occupiedChild.value)

            val invalidSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext, 0, 0, null, 0, null, 0, absent, 0, null, null,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateStatus(firstContext, state, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStatePendingSignInUrl(firstContext, state, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateDestroy(firstContext, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext, 3, 0, null, 0, null, 0, absent, 0, null, invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext, 0, 2, null, 0, null, 0, absent, 0, null, invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext, 0, 0, url, 0, null, 0, absent, 0, null, invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext, 0, 1, null, 0, null, 0, absent, 0, null, invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthenticationStateCreate(
                    firstContext,
                    0,
                    0,
                    null,
                    0,
                    null,
                    1,
                    invalidAuthenticationConfigurationUtf8View(),
                    0,
                    null,
                    invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentAuthenticationStateCreate(
                    secondContext, 0, 1, url, 0, null, 0, absent, 0, null, invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentAuthenticationStateCreate(
                    firstContext, 0, 0, null, 0, null, 0, absent, 1, url, invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsCreate(firstContext, 4, 0, absent, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsCreate(firstContext, 1, 0, absent, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsApprovalPreset(firstContext, settings, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsCreate(firstContext, 1, 2, absent, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsCreate(
                    firstContext,
                    1,
                    0,
                    authenticationConfigurationStringView("not-absent"),
                    invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentConversationSettingsCreate(
                    firstContext,
                    1,
                    1,
                    invalidAuthenticationConfigurationUtf8View(),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlExternal(null, authenticationConfigurationStringView("https://x.test"), invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlExternal(
                    firstContext,
                    authenticationConfigurationStringView("https://x.test"),
                    null,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlPurpose(firstContext, url, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlExternal(firstContext, null, invalidSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentClientInfoValueCreate(
                    firstContext,
                    authenticationConfigurationStringView("client"),
                    null,
                    authenticationConfigurationStringView("1"),
                    invalidSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentClientInfoValueCreate(
                    firstContext,
                    authenticationConfigurationStringView("client"),
                    authenticationConfigurationStringView("Client"),
                    authenticationConfigurationStringView("1"),
                    null,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentClientInfoValueNameCopy(firstContext, client, null, 0uL, null),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentAuthorizationUrlExternal(
                    firstContext,
                    authenticationConfigurationStringView("https://occupied.test"),
                    urlSlot.ptr,
                ),
            )
            assertEquals(url, urlSlot.value)

            val staleState = state
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateDestroy(firstContext, stateSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateDestroy(firstContext, stateSlot.ptr))
            projected.value = 83
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationStateStatus(firstContext, staleState, projected.ptr),
            )
            assertEquals(83, projected.value)

            val teardownContextSlot = createAuthenticationConfigurationContext()
            val teardownContext = assertNotNull(teardownContextSlot.value)
            val teardownUrlSlot = authenticationConfigurationEmptyHandleSlot()
            val teardownSettingsSlot = authenticationConfigurationEmptyHandleSlot()
            val teardownStateSlot = authenticationConfigurationEmptyHandleSlot()
            val teardownClientSlot = authenticationConfigurationEmptyHandleSlot()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthorizationUrlExternal(
                    teardownContext,
                    authenticationConfigurationStringView("https://teardown.test"),
                    teardownUrlSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSettingsCreate(
                    teardownContext,
                    3,
                    1,
                    authenticationConfigurationStringView("fast"),
                    teardownSettingsSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentAuthenticationStateCreate(
                    teardownContext,
                    2,
                    1,
                    teardownUrlSlot.value,
                    0,
                    null,
                    0,
                    absent,
                    0,
                    null,
                    teardownStateSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentClientInfoValueCreate(
                    teardownContext,
                    authenticationConfigurationStringView("teardown"),
                    authenticationConfigurationStringView("Teardown"),
                    authenticationConfigurationStringView("1"),
                    teardownClientSlot.ptr,
                ),
            )
            val teardownUrl = assertNotNull(teardownUrlSlot.value)
            val teardownSettings = assertNotNull(teardownSettingsSlot.value)
            val teardownState = assertNotNull(teardownStateSlot.value)
            val teardownClient = assertNotNull(teardownClientSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(teardownContextSlot.ptr))
            assertNull(teardownContextSlot.value)
            projected.value = 101
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthenticationStateStatus(teardownContext, teardownState, projected.ptr),
            )
            assertEquals(101, projected.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentConversationSettingsApprovalPreset(
                    teardownContext,
                    teardownSettings,
                    projected.ptr,
                ),
            )
            assertEquals(101, projected.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentAuthorizationUrlPurpose(teardownContext, teardownUrl, projected.ptr),
            )
            assertEquals(101, projected.value)
            required.value = 109uL
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentClientInfoValueNameCopy(
                    teardownContext,
                    teardownClient,
                    null,
                    0uL,
                    required.ptr,
                ),
            )
            assertEquals(109uL, required.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthenticationStateDestroy(firstContext, stateSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSettingsDestroy(firstContext, settingsSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentAuthorizationUrlDestroy(firstContext, urlSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentClientInfoValueDestroy(firstContext, clientSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(firstContextSlot.ptr))
        }
    }
}

private fun MemScope.createAuthenticationConfigurationContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.authenticationConfigurationEmptyHandleSlot(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.authenticationConfigurationAbsentView(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also {
        it.data = null
        it.size = 0uL
    }.ptr

private fun MemScope.authenticationConfigurationStringView(
    value: String,
): CPointer<codex_agent_string_view> {
    val bytes = value.encodeToByteArray()
    val data = if (bytes.isEmpty()) {
        null
    } else {
        allocArray<UByteVar>(bytes.size).also { buffer ->
            bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
        }
    }
    return alloc<codex_agent_string_view>().also {
        it.data = data
        it.size = bytes.size.toULong()
    }.ptr
}

private fun MemScope.mutableAuthenticationConfigurationStringView(
    value: String,
): AuthenticationConfigurationMutableStringView {
    val bytes = value.encodeToByteArray()
    val data = if (bytes.isEmpty()) {
        null
    } else {
        allocArray<UByteVar>(bytes.size).also { buffer ->
            bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
        }
    }
    return AuthenticationConfigurationMutableStringView(
        view = alloc<codex_agent_string_view>().also {
            it.data = data
            it.size = bytes.size.toULong()
        }.ptr,
        bytes = data,
    )
}

private fun MemScope.invalidAuthenticationConfigurationUtf8View(): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = allocArray<UByteVar>(2)
        bytes[0] = 0xc3u
        bytes[1] = 0x28u
        view.data = bytes
        view.size = 2uL
    }.ptr

private fun MemScope.assertAuthenticationConfigurationString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: AuthenticationConfigurationStringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (expectedBytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { index -> buffer[index].toByte() }.decodeToString(),
    )
}

private typealias AuthenticationConfigurationStringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private data class AuthenticationConfigurationMutableStringView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)
