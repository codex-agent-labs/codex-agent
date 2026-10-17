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

class CodexAgentCIntegrationStateValuesTest {
    @Test
    fun authorizationStateProjectsStatusTargetAndNullableFailure(): Unit = memScoped {
        val contextSlot = integrationStateContext()
        val context = assertNotNull(contextSlot.value)
        try {
            (0..4).forEach { expectedStatus ->
                val stateSlot = emptyIntegrationStateHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateCreate(
                        context,
                        expectedStatus,
                        null,
                        null,
                        stateSlot.ptr,
                    ),
                )
                val status = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateStatus(
                        context,
                        assertNotNull(stateSlot.value),
                        status.ptr,
                    ),
                )
                assertEquals(expectedStatus, status.value)
                val absentTarget = emptyIntegrationStateHandle()
                val absentFailure = emptyIntegrationStateHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateTarget(
                        context,
                        assertNotNull(stateSlot.value),
                        absentTarget.ptr,
                    ),
                )
                assertNull(absentTarget.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateFailure(
                        context,
                        assertNotNull(stateSlot.value),
                        absentFailure.ptr,
                    ),
                )
                assertNull(absentFailure.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateDestroy(context, stateSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentIntegrationAuthorizationStateDestroy(context, stateSlot.ptr),
                )
            }

            val connectorTargetSlot = createIntegrationStateConnectorTarget(context)
            val failureSlot = createIntegrationStateFailure(context)
            val connectorStateSlot = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateCreate(
                    context,
                    4,
                    assertNotNull(connectorTargetSlot.value),
                    assertNotNull(failureSlot.value),
                    connectorStateSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, connectorTargetSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))

            val firstTargetSlot = emptyIntegrationStateHandle()
            val secondTargetSlot = emptyIntegrationStateHandle()
            val firstFailureSlot = emptyIntegrationStateHandle()
            val secondFailureSlot = emptyIntegrationStateHandle()
            val connectorState = assertNotNull(connectorStateSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateTarget(context, connectorState, firstTargetSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateTarget(context, connectorState, secondTargetSlot.ptr),
            )
            assertNotEquals(firstTargetSlot.value, secondTargetSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateFailure(context, connectorState, firstFailureSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateFailure(context, connectorState, secondFailureSlot.ptr),
            )
            assertNotEquals(firstFailureSlot.value, secondFailureSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateDestroy(context, connectorStateSlot.ptr),
            )

            val firstTarget = assertNotNull(firstTargetSlot.value)
            val secondTarget = assertNotNull(secondTargetSlot.value)
            val kind = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationKind(context, firstTarget, kind.ptr))
            assertEquals(0, kind.value)
            val connectorSlot = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnector(context, firstTarget, connectorSlot.ptr),
            )
            assertIntegrationStateString(
                context,
                assertNotNull(connectorSlot.value),
                "state-connector",
                ::codexAgentIntegrationConnectorIdCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationConnectorDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, firstTargetSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationKind(context, secondTarget, kind.ptr))
            assertEquals(0, kind.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, secondTargetSlot.ptr))

            val firstFailure = assertNotNull(firstFailureSlot.value)
            val secondFailure = assertNotNull(secondFailureSlot.value)
            assertIntegrationStateString(
                context,
                firstFailure,
                "integration_authorization_failed",
                ::codexAgentFailureCodeCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, firstFailureSlot.ptr))
            assertIntegrationStateString(
                context,
                secondFailure,
                "Authorization failed",
                ::codexAgentFailureMessageCopy,
            )
            val recoverable = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentFailureIsRecoverable(context, secondFailure, recoverable.ptr),
            )
            assertEquals(1, recoverable.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, secondFailureSlot.ptr))

            val mcpTargetSlot = createIntegrationStateMcpTarget(context)
            val mcpStateSlot = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateCreate(
                    context,
                    3,
                    assertNotNull(mcpTargetSlot.value),
                    null,
                    mcpStateSlot.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, mcpTargetSlot.ptr))
            val projectedMcpTargetSlot = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateTarget(
                    context,
                    assertNotNull(mcpStateSlot.value),
                    projectedMcpTargetSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateDestroy(context, mcpStateSlot.ptr),
            )
            val projectedMcpTarget = assertNotNull(projectedMcpTargetSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationKind(context, projectedMcpTarget, kind.ptr))
            assertEquals(1, kind.value)
            val mcpIntegrationSlot = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServer(context, projectedMcpTarget, mcpIntegrationSlot.ptr),
            )
            assertIntegrationStateString(
                context,
                assertNotNull(mcpIntegrationSlot.value),
                "state-server",
                ::codexAgentIntegrationMcpServerIdCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, mcpIntegrationSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationDestroy(context, projectedMcpTargetSlot.ptr),
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun integrationStateRejectsContextTypeStaleAndOutputBoundaries(): Unit =
        withIntegrationStateContexts { context, otherContext ->
            val targetSlot = createIntegrationStateConnectorTarget(context)
            val failureSlot = createIntegrationStateFailure(context)
            val target = assertNotNull(targetSlot.value)
            val failure = assertNotNull(failureSlot.value)
            val output = emptyIntegrationStateHandle()

            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateCreate(context, 5, target, failure, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationAuthorizationStateCreate(otherContext, 4, target, null, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateCreate(context, 4, failure, null, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateCreate(context, 4, null, target, output.ptr),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateCreate(context, 4, target, failure, null),
            )

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateCreate(context, 4, target, failure, output.ptr),
            )
            val state = assertNotNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateCreate(context, 4, null, null, output.ptr),
            )
            assertEquals(state, output.value)

            val status = alloc<IntVar>().also { it.value = 73 }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateStatus(context, state, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationAuthorizationStateStatus(otherContext, state, status.ptr),
            )
            assertEquals(73, status.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateStatus(context, target, status.ptr),
            )
            assertEquals(73, status.value)

            val occupiedTarget = emptyIntegrationStateHandle().also { it.value = target }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateTarget(context, state, occupiedTarget.ptr),
            )
            assertEquals(target, occupiedTarget.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentIntegrationAuthorizationStateTarget(context, state, null),
            )
            val emptyTarget = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentIntegrationAuthorizationStateTarget(otherContext, state, emptyTarget.ptr),
            )
            assertNull(emptyTarget.value)
            val emptyFailure = emptyIntegrationStateHandle()
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateFailure(context, target, emptyFailure.ptr),
            )
            assertNull(emptyFailure.value)

            val wrongStateDestroy = emptyIntegrationStateHandle().also { it.value = target }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationAuthorizationStateDestroy(context, wrongStateDestroy.ptr),
            )
            assertEquals(target, wrongStateDestroy.value)
            val wrongIntegrationDestroy = emptyIntegrationStateHandle().also { it.value = state }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationDestroy(context, wrongIntegrationDestroy.ptr),
            )
            assertEquals(state, wrongIntegrationDestroy.value)

            val staleState = state
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateDestroy(context, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationAuthorizationStateDestroy(context, output.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationAuthorizationStateStatus(context, staleState, status.ptr),
            )
            assertEquals(73, status.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, targetSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentFailureRelease(context, failureSlot.ptr))
        }

    @Test
    fun contextTeardownReclaimsIntegrationStateSnapshots(): Unit = memScoped {
        val contextSlot = integrationStateContext()
        val context = assertNotNull(contextSlot.value)
        val targetSlot = createIntegrationStateConnectorTarget(context)
        val stateSlot = emptyIntegrationStateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentIntegrationAuthorizationStateCreate(
                context,
                1,
                assertNotNull(targetSlot.value),
                null,
                stateSlot.ptr,
            ),
        )
        val staleState = assertNotNull(stateSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)

        val status = alloc<IntVar>().also { it.value = 91 }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentIntegrationAuthorizationStateStatus(context, staleState, status.ptr),
        )
        assertEquals(91, status.value)
        val targetOutput = emptyIntegrationStateHandle()
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentIntegrationAuthorizationStateTarget(context, staleState, targetOutput.ptr),
        )
        assertNull(targetOutput.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentIntegrationAuthorizationStateDestroy(context, stateSlot.ptr),
        )
        assertEquals(staleState, stateSlot.value)
    }
}

private fun withIntegrationStateContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = integrationStateContext()
    val otherContextSlot = integrationStateContext()
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    try {
        block(context, otherContext)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.integrationStateContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.emptyIntegrationStateHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.integrationStateView(value: String): CPointer<codex_agent_string_view> =
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

private fun MemScope.createIntegrationStateConnectorTarget(
    context: COpaquePointer,
): COpaquePointerVar {
    val connectorSlot = emptyIntegrationStateHandle()
    val connectorIntegrationSlot = emptyIntegrationStateHandle()
    val targetSlot = emptyIntegrationStateHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConnectorCreate(
            context,
            integrationStateView("state-connector"),
            integrationStateView("State connector"),
            integrationStateView("State connector description"),
            0,
            integrationStateView(""),
            1,
            1,
            null,
            0uL,
            connectorSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationConnectorCreate(
            context,
            assertNotNull(connectorSlot.value),
            connectorIntegrationSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationFromConnector(
            context,
            assertNotNull(connectorIntegrationSlot.value),
            targetSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationConnectorDestroy(context, connectorIntegrationSlot.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connectorSlot.ptr))
    return targetSlot
}

private fun MemScope.createIntegrationStateMcpTarget(
    context: COpaquePointer,
): COpaquePointerVar {
    val serverSlot = emptyIntegrationStateHandle()
    val serverIntegrationSlot = emptyIntegrationStateHandle()
    val targetSlot = emptyIntegrationStateHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpServerCreate(
            context,
            integrationStateView("state-server"),
            integrationStateView("State server"),
            0,
            null,
            4,
            1,
            serverSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationMcpServerCreate(
            context,
            assertNotNull(serverSlot.value),
            serverIntegrationSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationFromMcpServer(
            context,
            assertNotNull(serverIntegrationSlot.value),
            targetSlot.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationMcpServerDestroy(context, serverIntegrationSlot.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, serverSlot.ptr))
    return targetSlot
}

private fun MemScope.createIntegrationStateFailure(
    context: COpaquePointer,
): COpaquePointerVar = emptyIntegrationStateHandle().also { slot ->
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentFailureCreate(
            context,
            integrationStateView("integration_authorization_failed"),
            integrationStateView("Authorization failed"),
            1,
            slot.ptr,
        ),
    )
}

private fun MemScope.assertIntegrationStateString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: (
        COpaquePointer?,
        COpaquePointer?,
        CPointer<UByteVar>?,
        ULong,
        CPointer<ULongVar>?,
    ) -> Int,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0uL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(
        expected,
        ByteArray(expectedBytes.size) { index -> buffer[index].toByte() }.decodeToString(),
    )
}
