@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentConversationState
import io.github.codex_agent_labs.codexmobile.agent.AgentConversationStatus
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
import kotlin.test.Test
import kotlin.test.assertEquals
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
import kotlinx.cinterop.value
import kotlinx.coroutines.runBlocking

class CodexAgentCValueProjectionTest {
    @Test
    fun projectsEveryConversationStatusAndFailureExactly() = memScoped {
        val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)

        try {
            listOf(
                AgentConversationStatus.NEW to 0,
                AgentConversationStatus.OPENING to 1,
                AgentConversationStatus.READY to 2,
                AgentConversationStatus.STARTING_TURN to 3,
                AgentConversationStatus.RUNNING_TURN to 4,
                AgentConversationStatus.CANCELLING_TURN to 5,
                AgentConversationStatus.RELOADING to 6,
                AgentConversationStatus.FAILED to 7,
                AgentConversationStatus.CLOSED to 8,
            ).forEach { (status, expectedOrdinal) ->
                val snapshot = createSnapshot(
                    context,
                    CodexAgentCConversationStateSnapshot(AgentConversationState(status = status)),
                ).requiredValue()
                try {
                    val projectedStatus = alloc<IntVar>()
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentConversationStateStatus(context, snapshot, projectedStatus.ptr),
                        status.name,
                    )
                    assertEquals(expectedOrdinal, projectedStatus.value, status.name)
                    if (status == AgentConversationStatus.NEW) {
                        val absentFailure = alloc<COpaquePointerVar>().also { it.value = null }
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            codexAgentConversationStateFailure(context, snapshot, absentFailure.ptr),
                        )
                        assertNull(absentFailure.value)
                    }
                } finally {
                    destroySnapshot(context, snapshot)
                }
            }

            val canonicalFailure = CodexFailure(
                code = "conversation_failed",
                message = "Conversation projection failed",
                isRecoverable = true,
            )
            val snapshot = createSnapshot(
                context,
                CodexAgentCConversationStateSnapshot(
                    AgentConversationState(
                        status = AgentConversationStatus.FAILED,
                        failure = canonicalFailure,
                    ),
                ),
            ).requiredValue()
            val failureSlot = alloc<COpaquePointerVar>().also { it.value = null }
            try {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationStateFailure(context, snapshot, failureSlot.ptr),
                )
                val failure = assertNotNull(failureSlot.value)
                assertCopiedString(context, failure, canonicalFailure.code, ::codexAgentFailureCodeCopy)
                assertCopiedString(context, failure, canonicalFailure.message, ::codexAgentFailureMessageCopy)
                val recoverable = alloc<IntVar>()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentFailureIsRecoverable(context, failure, recoverable.ptr),
                )
                assertEquals(1, recoverable.value)
            } finally {
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))
                assertNull(failureSlot.value)
                destroySnapshot(context, snapshot)
            }
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }

    @Test
    fun projectsMissingHostStateVariantsAndPayloadsExactly(): Unit = runBlocking {
        val host = NativeCodexBehaviorFixture().createHost()
        try {
            memScoped {
                val contextSlot = alloc<COpaquePointerVar>().also { it.value = null }
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
                val context = assertNotNull(contextSlot.value)
                try {
                    val restoring = createSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.Restoring),
                    ).requiredValue()
                    try {
                        assertHostKind(context, restoring, 1)
                    } finally {
                        destroySnapshot(context, restoring)
                    }

                    val preparingWorkspace = CodexWorkspace(
                        path = "/workspace/preparing",
                        displayName = "Preparing workspace",
                    )
                    val preparing = createSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.Preparing(preparingWorkspace)),
                    ).requiredValue()
                    try {
                        assertHostKind(context, preparing, 3)
                        assertHostWorkspace(context, preparing, preparingWorkspace)
                    } finally {
                        destroySnapshot(context, preparing)
                    }

                    val requirement = CodexWorkspaceResolution.SelectionRequired(
                        reason = CodexWorkspaceSelectionReason.ACCESS_REVOKED,
                        message = "Select an accessible workspace",
                    )
                    val workspaceRequired = createSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.WorkspaceRequired(requirement)),
                    ).requiredValue()
                    try {
                        assertHostKind(context, workspaceRequired, 2)
                        val hasWorkspace = alloc<IntVar>()
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            codexAgentHostStateHasWorkspace(context, workspaceRequired, hasWorkspace.ptr),
                        )
                        assertEquals(0, hasWorkspace.value)
                        val reason = alloc<IntVar>()
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            codexAgentHostStateRequirementReason(context, workspaceRequired, reason.ptr),
                        )
                        assertEquals(2, reason.value)
                        assertCopiedString(
                            context,
                            workspaceRequired,
                            requirement.message,
                            ::codexAgentHostStateRequirementMessageCopy,
                        )
                    } finally {
                        destroySnapshot(context, workspaceRequired)
                    }

                    val failedWorkspace = CodexWorkspace(
                        path = "/workspace/failed",
                        displayName = "Failed workspace",
                    )
                    val canonicalFailure = CodexFailure(
                        code = "runtime_prepare_failed",
                        message = "Could not prepare Codex",
                        isRecoverable = false,
                    )
                    val failed = createSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(
                            host,
                            CodexHostState.Failed(failedWorkspace, canonicalFailure),
                        ),
                    ).requiredValue()
                    try {
                        assertHostKind(context, failed, 5)
                        assertHostWorkspace(context, failed, failedWorkspace)
                        assertHostFailure(context, failed, canonicalFailure)
                    } finally {
                        destroySnapshot(context, failed)
                    }

                    val failedWithoutWorkspace = createSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(
                            host,
                            CodexHostState.Failed(null, canonicalFailure),
                        ),
                    ).requiredValue()
                    try {
                        assertHostKind(context, failedWithoutWorkspace, 5)
                        val hasWorkspace = alloc<IntVar>()
                        assertEquals(
                            CODEX_AGENT_STATUS_OK,
                            codexAgentHostStateHasWorkspace(context, failedWithoutWorkspace, hasWorkspace.ptr),
                        )
                        assertEquals(0, hasWorkspace.value)
                        val required = alloc<ULongVar>()
                        assertEquals(
                            CODEX_AGENT_STATUS_NOT_READY,
                            codexAgentHostStateWorkspacePathCopy(
                                context,
                                failedWithoutWorkspace,
                                null,
                                0UL,
                                required.ptr,
                            ),
                        )
                        assertEquals(
                            CODEX_AGENT_STATUS_NOT_READY,
                            codexAgentHostStateWorkspaceDisplayNameCopy(
                                context,
                                failedWithoutWorkspace,
                                null,
                                0UL,
                                required.ptr,
                            ),
                        )
                        assertHostFailure(context, failedWithoutWorkspace, canonicalFailure)
                    } finally {
                        destroySnapshot(context, failedWithoutWorkspace)
                    }
                } finally {
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
                    assertNull(contextSlot.value)
                }
            }
        } finally {
            host.close()
        }
    }
}

private fun MemScope.assertHostKind(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    expectedKind: Int,
) {
    val kind = alloc<IntVar>()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateKind(context, snapshot, kind.ptr))
    assertEquals(expectedKind, kind.value)
}

private fun MemScope.assertHostWorkspace(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    expected: CodexWorkspace,
) {
    val hasWorkspace = alloc<IntVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostStateHasWorkspace(context, snapshot, hasWorkspace.ptr),
    )
    assertEquals(1, hasWorkspace.value)
    assertCopiedString(context, snapshot, expected.path, ::codexAgentHostStateWorkspacePathCopy)
    assertCopiedString(
        context,
        snapshot,
        expected.displayName,
        ::codexAgentHostStateWorkspaceDisplayNameCopy,
    )
}

private fun MemScope.assertHostFailure(
    context: COpaquePointer,
    snapshot: COpaquePointer,
    expected: CodexFailure,
) {
    val failureSlot = alloc<COpaquePointerVar>().also { it.value = null }
    try {
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHostStateFailure(context, snapshot, failureSlot.ptr),
        )
        val failure = assertNotNull(failureSlot.value)
        assertCopiedString(context, failure, expected.code, ::codexAgentFailureCodeCopy)
        assertCopiedString(context, failure, expected.message, ::codexAgentFailureMessageCopy)
        val recoverable = alloc<IntVar>()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentFailureIsRecoverable(context, failure, recoverable.ptr),
        )
        assertEquals(if (expected.isRecoverable) 1 else 0, recoverable.value)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))
        assertNull(failureSlot.value)
    }
}

private fun MemScope.assertCopiedString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: StringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0UL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    assertEquals(expected, ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.destroySnapshot(context: COpaquePointer, snapshot: COpaquePointer) {
    val slot = alloc<COpaquePointerVar>().also { it.value = snapshot }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot.ptr))
    assertNull(slot.value)
}

private fun <T : Any> CodexAgentCRegistryResult<T>.requiredValue(): T {
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    return assertNotNull(value)
}

private typealias StringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int
