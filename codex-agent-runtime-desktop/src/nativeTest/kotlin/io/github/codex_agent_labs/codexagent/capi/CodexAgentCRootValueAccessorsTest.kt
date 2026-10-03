@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.agent.AgentElicitation
import io.github.codex_agent_labs.codexagent.agent.AgentInteractionState
import io.github.codex_agent_labs.codexagent.agent.AgentPendingApproval
import io.github.codex_agent_labs.codexagent.agent.AgentPendingElicitation
import io.github.codex_agent_labs.codexagent.agent.CodexFailure
import io.github.codex_agent_labs.codexagent.agent.CodexHostState
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspace
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexagent.agent.ConversationId
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

class CodexAgentCRootValueAccessorsTest {
    @Test
    fun hostSubtypePayloadsAreExactFreshAndFailClosed(): Unit = runBlocking {
        val host = NativeCodexBehaviorFixture().createHost()
        try {
            memScoped {
                val contextSlot = rootEmptyHandle()
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
                val context = assertNotNull(contextSlot.value)
                try {
                    val failedWorkspace = CodexWorkspace("/failed", "Failed")
                    val preparingWorkspace = CodexWorkspace("/preparing", "Preparing")
                    val requirement = CodexWorkspaceResolution.SelectionRequired(
                        CodexWorkspaceSelectionReason.ACCESS_REVOKED,
                        "Choose another workspace",
                    )
                    val failed = rootSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(
                            host,
                            CodexHostState.Failed(
                                failedWorkspace,
                                CodexFailure("prepare_failed", "failed", false),
                            ),
                        ),
                    )
                    val preparing = rootSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.Preparing(preparingWorkspace)),
                    )
                    val required = rootSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.WorkspaceRequired(requirement)),
                    )
                    val failedChild = rootEmptyHandle()
                    val preparingChild = rootEmptyHandle()
                    val requirementChild = rootEmptyHandle()
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentHostStateFailedWorkspace(context, failed, failedChild.ptr),
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentHostStatePreparingWorkspace(context, preparing, preparingChild.ptr),
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentHostStateWorkspaceRequiredRequirement(context, required, requirementChild.ptr),
                    )

                    rootDestroySnapshot(context, failed)
                    rootDestroySnapshot(context, preparing)
                    rootDestroySnapshot(context, required)
                    assertRootCopiedString(
                        context,
                        assertNotNull(failedChild.value),
                        failedWorkspace.path,
                        ::codexAgentWorkspacePathCopy,
                    )
                    assertRootCopiedString(
                        context,
                        assertNotNull(preparingChild.value),
                        preparingWorkspace.displayName,
                        ::codexAgentWorkspaceDisplayNameCopy,
                    )
                    val reason = alloc<IntVar>().also { it.value = -1 }
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentWorkspaceSelectionRequiredReason(
                            context,
                            assertNotNull(requirementChild.value),
                            reason.ptr,
                        ),
                    )
                    assertEquals(2, reason.value)
                    assertRootCopiedString(
                        context,
                        assertNotNull(requirementChild.value),
                        requirement.message,
                        ::codexAgentWorkspaceSelectionRequiredMessageCopy,
                    )

                    val wrongSubtype = rootEmptyHandle()
                    val preparingAgain = rootSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(host, CodexHostState.Preparing(preparingWorkspace)),
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                        codexAgentHostStateFailedWorkspace(context, preparingAgain, wrongSubtype.ptr),
                    )
                    assertNull(wrongSubtype.value)
                    rootDestroySnapshot(context, preparingAgain)

                    val failedWithoutWorkspace = rootSnapshot(
                        context,
                        CodexAgentCHostStateSnapshot(
                            host,
                            CodexHostState.Failed(null, CodexFailure("failed", "failed", true)),
                        ),
                    )
                    assertEquals(
                        CODEX_AGENT_STATUS_NOT_READY,
                        codexAgentHostStateFailedWorkspace(context, failedWithoutWorkspace, wrongSubtype.ptr),
                    )
                    assertNull(wrongSubtype.value)
                    rootDestroySnapshot(context, failedWithoutWorkspace)

                    val occupied = rootEmptyHandle().also { it.value = failedChild.value }
                    assertEquals(
                        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                        codexAgentHostStatePreparingWorkspace(context, null, occupied.ptr),
                    )
                    assertEquals(failedChild.value, occupied.value)
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, failedChild.ptr))
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentWorkspaceDestroy(context, preparingChild.ptr))
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentWorkspaceSelectionRequiredDestroy(context, requirementChild.ptr),
                    )
                } finally {
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
                    assertNull(contextSlot.value)
                }
            }
        } finally {
            host.close()
        }
    }

    @Test
    fun pendingForPreservesOrderDuplicatesOwnershipAndErrors(): Unit = memScoped {
        val contextSlot = rootEmptyHandle()
        val otherContextSlot = rootEmptyHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val otherContext = assertNotNull(otherContextSlot.value)
        try {
            val target = ConversationId("target")
            val other = ConversationId("other")
            val approval = AgentPendingApproval("approval", target, "Title", "Details")
            val elicitation = AgentPendingElicitation(
                AgentElicitation("elicitation", "server", target, "Message"),
            )
            val state = rootSnapshot(
                context,
                CodexAgentCInteractionStateSnapshot(
                    AgentInteractionState(
                        pending = listOf(
                            approval,
                            AgentPendingApproval("other", other, "Other", "Other"),
                            elicitation,
                            approval,
                        ),
                    ),
                ),
            )
            val id = rootSnapshot(context, CodexAgentCConversationIdSnapshot(target))
            val list = rootEmptyHandle()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInteractionStatePendingFor(otherContext, state, id, list.ptr),
            )
            assertNull(list.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInteractionStatePendingFor(context, state, id, list.ptr),
            )
            val count = alloc<ULongVar>().also { it.value = 99uL }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionListCount(context, assertNotNull(list.value), count.ptr),
            )
            assertEquals(3uL, count.value)

            val children = List(3) { rootEmptyHandle() }
            children.forEachIndexed { index, child ->
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionListAt(
                        context,
                        assertNotNull(list.value),
                        index.toULong(),
                        child.ptr,
                    ),
                )
            }
            val invalid = rootEmptyHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingInteractionListAt(context, assertNotNull(list.value), 3uL, invalid.ptr),
            )
            assertNull(invalid.value)
            val staleList = assertNotNull(list.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionListDestroy(context, list.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionListDestroy(context, list.ptr))
            rootDestroySnapshot(context, state)
            rootDestroySnapshot(context, id)

            val expectedKinds = listOf(0, 1, 0)
            val expectedIds = listOf("approval", "elicitation", "approval")
            children.forEachIndexed { index, child ->
                val kind = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionKind(context, assertNotNull(child.value), kind.ptr),
                )
                assertEquals(expectedKinds[index], kind.value)
                val concrete = rootEmptyHandle()
                if (kind.value == 0) {
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentPendingInteractionApproval(context, assertNotNull(child.value), concrete.ptr),
                    )
                    assertRootCopiedString(
                        context,
                        assertNotNull(concrete.value),
                        expectedIds[index],
                        ::codexAgentPendingApprovalRequestIdCopy,
                    )
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingApprovalDestroy(context, concrete.ptr))
                } else {
                    assertEquals(
                        CODEX_AGENT_STATUS_OK,
                        codexAgentPendingInteractionElicitation(context, assertNotNull(child.value), concrete.ptr),
                    )
                    assertRootCopiedString(
                        context,
                        assertNotNull(concrete.value),
                        expectedIds[index],
                        ::codexAgentPendingElicitationRequestIdCopy,
                    )
                    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingElicitationDestroy(context, concrete.ptr))
                }
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingInteractionDestroy(context, child.ptr))
            }

            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentPendingInteractionListCount(context, staleList, count.ptr),
            )
            assertEquals(3uL, count.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        }
    }
}

private fun MemScope.rootEmptyHandle(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun rootSnapshot(context: COpaquePointer, snapshot: CodexAgentCSnapshot): COpaquePointer {
    val result = createSnapshot(context, snapshot)
    assertEquals(CODEX_AGENT_STATUS_OK, result.status)
    return assertNotNull(result.value)
}

private fun MemScope.rootDestroySnapshot(context: COpaquePointer, snapshot: COpaquePointer) {
    val slot = rootEmptyHandle().also { it.value = snapshot }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, slot.ptr))
    assertNull(slot.value)
}

private fun MemScope.assertRootCopiedString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: RootStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private typealias RootStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int
