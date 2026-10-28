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
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.readBytes
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCConversationValuesTest {
    @Test
    fun createsAndValidatesFailures(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val failureSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureCreate(
                    context,
                    stringView("failure_code"),
                    stringView("Failure message"),
                    1,
                    failureSlot.ptr,
                ),
            )
            val failure = assertNotNull(failureSlot.value)
            assertCopiedString("failure_code") { buffer, capacity, required ->
                codexAgentFailureCodeCopy(context, failure, buffer, capacity, required)
            }
            assertCopiedString("Failure message") { buffer, capacity, required ->
                codexAgentFailureMessageCopy(context, failure, buffer, capacity, required)
            }
            val recoverable = alloc<IntVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureIsRecoverable(context, failure, recoverable.ptr),
            )
            assertEquals(1, recoverable.value)

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFailureCreate(
                    context,
                    stringView("other"),
                    stringView("Other"),
                    0,
                    failureSlot.ptr,
                ),
            )
            assertEquals(failure, failureSlot.value)

            listOf(
                Triple(stringView(" "), stringView("message"), 0),
                Triple(stringView("code"), stringView(" "), 0),
                Triple(stringView("code"), stringView("x".repeat(501)), 0),
                Triple(stringView("code"), stringView("message"), 2),
            ).forEach { (code, message, flag) ->
                val invalidSlot = alloc<COpaquePointerVar>().also { it.value = null }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentFailureCreate(context, code, message, flag, invalidSlot.ptr),
                )
                assertNull(invalidSlot.value)
            }
            val invalidUtf8Slot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentFailureCreate(
                    context,
                    byteView(0xc3),
                    stringView("message"),
                    0,
                    invalidUtf8Slot.ptr,
                ),
            )
            assertNull(invalidUtf8Slot.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))
            assertNull(failureSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun projectsConversationValuesWithIndependentNestedOwnership(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val otherContextSlot = newContext()
        val otherContext = assertNotNull(otherContextSlot.value)
        val idSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val summarySlot = alloc<COpaquePointerVar>().also { it.value = null }
        val firstNestedSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val secondNestedSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationIdCreate(context, stringView("thread-123"), idSlot.ptr),
            )
            val id = assertNotNull(idSlot.value)
            assertCopiedString("thread-123") { buffer, capacity, required ->
                codexAgentConversationIdValueCopy(context, id, buffer, capacity, required)
            }
            val untouched = alloc<ULongVar>().also { it.value = 71uL }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentConversationIdValueCopy(otherContext, id, null, 0uL, untouched.ptr),
            )
            assertEquals(71uL, untouched.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSummaryCreate(
                    context,
                    id,
                    stringView("Native summary"),
                    1_725_000_123L,
                    summarySlot.ptr,
                ),
            )
            val summary = assertNotNull(summarySlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, idSlot.ptr))
            assertNull(idSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, idSlot.ptr))

            assertCopiedString("Native summary") { buffer, capacity, required ->
                codexAgentConversationSummaryTitleCopy(context, summary, buffer, capacity, required)
            }
            val updated = alloc<LongVar>()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSummaryUpdatedAtEpochSeconds(context, summary, updated.ptr),
            )
            assertEquals(1_725_000_123L, updated.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSummaryConversationId(context, summary, firstNestedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentConversationSummaryConversationId(context, summary, secondNestedSlot.ptr),
            )
            val firstNested = assertNotNull(firstNestedSlot.value)
            val secondNested = assertNotNull(secondNestedSlot.value)
            assertNotEquals(firstNested, secondNested)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, summarySlot.ptr))
            assertCopiedString("thread-123") { buffer, capacity, required ->
                codexAgentConversationIdValueCopy(context, firstNested, buffer, capacity, required)
            }

            val wrongTypeSlot = alloc<COpaquePointerVar>().also { it.value = firstNested }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentWorkspaceDestroy(context, wrongTypeSlot.ptr),
            )
            assertEquals(firstNested, wrongTypeSlot.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, firstNestedSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, secondNestedSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationSummaryDestroy(context, summarySlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, idSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun projectsWorkspaceDefaultsAndIndependentAvailableOwnership(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val workspaceSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val availableSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val firstNestedSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val secondNestedSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceCreate(
                    context,
                    stringView("/workspace/default"),
                    0,
                    emptyView(),
                    workspaceSlot.ptr,
                ),
            )
            val workspace = assertNotNull(workspaceSlot.value)
            assertCopiedString("/workspace/default") { buffer, capacity, required ->
                codexAgentWorkspacePathCopy(context, workspace, buffer, capacity, required)
            }
            assertCopiedString("/workspace/default") { buffer, capacity, required ->
                codexAgentWorkspaceDisplayNameCopy(context, workspace, buffer, capacity, required)
            }

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceResolutionAvailableCreate(context, workspace, availableSlot.ptr),
            )
            val available = assertNotNull(availableSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, workspaceSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceResolutionAvailableWorkspace(context, available, firstNestedSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceResolutionAvailableWorkspace(context, available, secondNestedSlot.ptr),
            )
            val firstNested = assertNotNull(firstNestedSlot.value)
            assertNotEquals(firstNested, assertNotNull(secondNestedSlot.value))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceResolutionAvailableDestroy(context, availableSlot.ptr),
            )
            assertCopiedString("/workspace/default") { buffer, capacity, required ->
                codexAgentWorkspaceDisplayNameCopy(context, firstNested, buffer, capacity, required)
            }

            listOf(
                Triple(0, stringView("contradiction"), stringView("/workspace/a")),
                Triple(2, emptyView(), stringView("/workspace/b")),
                Triple(1, stringView(" "), stringView("/workspace/c")),
                Triple(0, emptyView(), stringView(" ")),
                Triple(0, emptyView(), stringView("bad\u0000path")),
            ).forEach { (flag, display, path) ->
                val invalidSlot = alloc<COpaquePointerVar>().also { it.value = null }
                assertEquals(
                    CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                    codexAgentWorkspaceCreate(context, path, flag, display, invalidSlot.ptr),
                )
                assertNull(invalidSlot.value)
            }

            val explicitSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceCreate(
                    context,
                    stringView("/workspace/explicit"),
                    1,
                    stringView("Explicit workspace"),
                    explicitSlot.ptr,
                ),
            )
            assertCopiedString("Explicit workspace") { buffer, capacity, required ->
                codexAgentWorkspaceDisplayNameCopy(
                    context,
                    assertNotNull(explicitSlot.value),
                    buffer,
                    capacity,
                    required,
                )
            }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, explicitSlot.ptr))
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, firstNestedSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, secondNestedSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentWorkspaceResolutionAvailableDestroy(context, availableSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, workspaceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun projectsEveryApprovalPresetAndWorkspaceSelectionReasonExactly(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        try {
            listOf(
                0 to "Never",
                1 to "Auto review",
                2 to "Ask me",
                3 to "Strict",
            ).forEach { (preset, displayName) ->
                assertCopiedString(displayName) { buffer, capacity, required ->
                    codexAgentApprovalPresetDisplayNameCopy(preset, buffer, capacity, required)
                }
            }
            val invalidRequired = alloc<ULongVar>().also { it.value = 41uL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentApprovalPresetDisplayNameCopy(4, null, 0uL, invalidRequired.ptr),
            )
            assertEquals(41uL, invalidRequired.value)

            listOf(
                0 to "No workspace selected",
                1 to "Workspace not found",
                2 to "Workspace access revoked",
                3 to "Workspace selection invalid",
            ).forEach { (reason, message) ->
                val requiredSlot = alloc<COpaquePointerVar>().also { it.value = null }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentWorkspaceSelectionRequiredCreate(
                        context,
                        reason,
                        stringView(message),
                        requiredSlot.ptr,
                    ),
                )
                val required = assertNotNull(requiredSlot.value)
                val projectedReason = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentWorkspaceSelectionRequiredReason(
                        context,
                        required,
                        projectedReason.ptr,
                    ),
                )
                assertEquals(reason, projectedReason.value)
                assertCopiedString(message) { buffer, capacity, outRequired ->
                    codexAgentWorkspaceSelectionRequiredMessageCopy(
                        context,
                        required,
                        buffer,
                        capacity,
                        outRequired,
                    )
                }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentWorkspaceSelectionRequiredDestroy(context, requiredSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentWorkspaceSelectionRequiredDestroy(context, requiredSlot.ptr),
                )
            }

            val invalidSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentWorkspaceSelectionRequiredCreate(
                    context,
                    4,
                    stringView("Invalid"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun contextTeardownReclaimsOutstandingImmutableValues(): Unit = memScoped {
        val contextSlot = newContext()
        val context = assertNotNull(contextSlot.value)
        val idSlot = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationIdCreate(context, stringView("teardown-id"), idSlot.ptr),
        )
        val id = assertNotNull(idSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
        val required = alloc<ULongVar>().also { it.value = 99uL }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentConversationIdValueCopy(context, id, null, 0uL, required.ptr),
        )
        assertEquals(99uL, required.value)
    }

    private fun MemScope.newContext(): COpaquePointerVar =
        alloc<COpaquePointerVar>().also {
            it.value = null
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
        }

    private fun MemScope.stringView(value: String): CPointer<codex_agent_string_view> =
        byteView(*value.encodeToByteArray().map(Byte::toInt).toIntArray())

    private fun MemScope.emptyView(): CPointer<codex_agent_string_view> =
        alloc<codex_agent_string_view>().also {
            it.data = null
            it.size = 0uL
        }.ptr

    private fun MemScope.byteView(vararg values: Int): CPointer<codex_agent_string_view> =
        alloc<codex_agent_string_view>().also { view ->
            view.data = if (values.isEmpty()) {
                null
            } else {
                allocArray<UByteVar>(values.size).also { buffer ->
                    values.forEachIndexed { index, value -> buffer[index] = value.toUByte() }
                }
            }
            view.size = values.size.toULong()
        }.ptr

    private fun MemScope.assertCopiedString(
        expected: String,
        copy: (CPointer<UByteVar>?, ULong, CPointer<ULongVar>?) -> Int,
    ) {
        val expectedBytes = expected.encodeToByteArray()
        val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
        assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(null, 0uL, required.ptr))
        assertEquals(expectedBytes.size.toULong(), required.value)
        val buffer = allocArray<UByteVar>(expectedBytes.size)
        assertEquals(CODEX_AGENT_STATUS_OK, copy(buffer, expectedBytes.size.toULong(), required.ptr))
        assertEquals(expected, buffer.readBytes(expectedBytes.size).decodeToString())
    }
}
