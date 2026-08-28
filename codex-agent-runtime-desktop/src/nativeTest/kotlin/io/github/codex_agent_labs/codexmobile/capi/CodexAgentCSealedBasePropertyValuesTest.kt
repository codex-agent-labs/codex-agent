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

class CodexAgentCSealedBasePropertyValuesTest {
    @Test
    fun invocationBasePropertiesProjectBothConcreteVariants(): Unit = withSealedBaseContexts { context, _ ->
        val pluginSlot = createSealedBasePluginInvocation(context)
        val skillSlot = createSealedBaseSkillInvocation(context)
        val plugin = assertNotNull(pluginSlot.value)
        val skill = assertNotNull(skillSlot.value)
        try {
            assertSealedBaseString(context, plugin, "review-plugin", ::codexAgentInvocationNameCopy)
            assertSealedBaseString(
                context,
                plugin,
                "plugin:plugin://review@official",
                ::codexAgentInvocationKeyCopy,
            )
            assertSealedBaseString(context, skill, "review-skill", ::codexAgentInvocationNameCopy)
            assertSealedBaseString(
                context,
                skill,
                "skill:/skills/review.md",
                ::codexAgentInvocationKeyCopy,
            )

            val pluginChild = emptySealedBaseHandle()
            val skillChild = emptySealedBaseHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPlugin(context, plugin, pluginChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationSkill(context, skill, skillChild.ptr),
            )
            assertSealedBaseString(
                context,
                assertNotNull(pluginChild.value),
                "review-plugin",
                ::codexAgentInvocationPluginNameCopy,
            )
            assertSealedBaseString(
                context,
                assertNotNull(skillChild.value),
                "review-skill",
                ::codexAgentInvocationSkillNameCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationPluginDestroy(context, pluginChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentInvocationSkillDestroy(context, skillChild.ptr),
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, pluginSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, pluginSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, skillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, skillSlot.ptr))
        }
    }

    @Test
    fun pendingInteractionBasePropertiesProjectBothVariantsAndFreshConversationIds(): Unit =
        withSealedBaseContexts { context, _ ->
            val approvalSlot = createSealedBaseApprovalInteraction(context)
            val elicitationSlot = createSealedBaseElicitationInteraction(context)
            val approval = assertNotNull(approvalSlot.value)
            val elicitation = assertNotNull(elicitationSlot.value)
            val firstIdSlot = emptySealedBaseHandle()
            val secondIdSlot = emptySealedBaseHandle()
            val elicitationIdSlot = emptySealedBaseHandle()
            try {
                assertSealedBaseString(
                    context,
                    approval,
                    "approval-request",
                    ::codexAgentPendingInteractionRequestIdCopy,
                )
                assertSealedBaseString(
                    context,
                    elicitation,
                    "elicitation-request",
                    ::codexAgentPendingInteractionRequestIdCopy,
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionConversationId(context, approval, firstIdSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionConversationId(context, approval, secondIdSlot.ptr),
                )
                assertNotEquals(firstIdSlot.value, secondIdSlot.value)
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionConversationId(
                        context,
                        elicitation,
                        elicitationIdSlot.ptr,
                    ),
                )

                val approvalChild = emptySealedBaseHandle()
                val elicitationChild = emptySealedBaseHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionApproval(context, approval, approvalChild.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionElicitation(context, elicitation, elicitationChild.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingApprovalDestroy(context, approvalChild.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingElicitationDestroy(context, elicitationChild.ptr),
                )

                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, approvalSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, approvalSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, elicitationSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, elicitationSlot.ptr),
                )

                assertSealedBaseString(
                    context,
                    assertNotNull(firstIdSlot.value),
                    "approval-conversation",
                    ::codexAgentConversationIdValueCopy,
                )
                assertSealedBaseString(
                    context,
                    assertNotNull(secondIdSlot.value),
                    "approval-conversation",
                    ::codexAgentConversationIdValueCopy,
                )
                assertSealedBaseString(
                    context,
                    assertNotNull(elicitationIdSlot.value),
                    "elicitation-conversation",
                    ::codexAgentConversationIdValueCopy,
                )
            } finally {
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, approvalSlot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentPendingInteractionDestroy(context, elicitationSlot.ptr),
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, firstIdSlot.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, firstIdSlot.ptr))
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, secondIdSlot.ptr))
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentConversationIdDestroy(context, elicitationIdSlot.ptr),
                )
            }
        }

    @Test
    fun integrationBasePropertiesProjectBothConcreteVariants(): Unit = withSealedBaseContexts { context, _ ->
        val connectorSlot = createSealedBaseConnectorIntegration(context)
        val mcpSlot = createSealedBaseMcpIntegration(context)
        val connector = assertNotNull(connectorSlot.value)
        val mcp = assertNotNull(mcpSlot.value)
        try {
            assertSealedBaseString(context, connector, "drive", ::codexAgentIntegrationIdCopy)
            assertSealedBaseString(
                context,
                connector,
                "Drive connector",
                ::codexAgentIntegrationDisplayNameCopy,
            )
            assertSealedBaseString(context, mcp, "review-mcp", ::codexAgentIntegrationIdCopy)
            assertSealedBaseString(
                context,
                mcp,
                "Review MCP",
                ::codexAgentIntegrationDisplayNameCopy,
            )

            val connectorChild = emptySealedBaseHandle()
            val mcpChild = emptySealedBaseHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnector(context, connector, connectorChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServer(context, mcp, mcpChild.ptr),
            )
            assertSealedBaseString(
                context,
                assertNotNull(connectorChild.value),
                "drive",
                ::codexAgentIntegrationConnectorIdCopy,
            )
            assertSealedBaseString(
                context,
                assertNotNull(mcpChild.value),
                "review-mcp",
                ::codexAgentIntegrationMcpServerIdCopy,
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationConnectorDestroy(context, connectorChild.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentIntegrationMcpServerDestroy(context, mcpChild.ptr),
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, connectorSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, mcpSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, mcpSlot.ptr))
        }
    }

    @Test
    fun sealedBaseAccessorsFailClosedAndContextReclaimsSnapshots(): Unit = memScoped {
        val contextSlot = sealedBaseContext()
        val otherContextSlot = sealedBaseContext()
        val context = assertNotNull(contextSlot.value)
        val otherContext = assertNotNull(otherContextSlot.value)
        val invocationSlot = createSealedBasePluginInvocation(context)
        val interactionSlot = createSealedBaseApprovalInteraction(context)
        val integrationSlot = createSealedBaseConnectorIntegration(context)
        val wrongTypeSlot = emptySealedBaseHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentConversationIdCreate(context, sealedBaseView("wrong-type"), wrongTypeSlot.ptr),
        )
        val invocation = assertNotNull(invocationSlot.value)
        val interaction = assertNotNull(interactionSlot.value)
        val integration = assertNotNull(integrationSlot.value)
        val wrongType = assertNotNull(wrongTypeSlot.value)
        val required = alloc<ULongVar>().also { it.value = 73uL }
        val childSlot = emptySealedBaseHandle()
        try {
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentInvocationNameCopy(context, invocation, null, 0uL, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentInvocationNameCopy(otherContext, invocation, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentInvocationKeyCopy(context, wrongType, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPendingInteractionRequestIdCopy(context, wrongType, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentIntegrationIdCopy(context, wrongType, null, 0uL, required.ptr),
            )
            assertEquals(73uL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingInteractionConversationId(context, interaction, null),
            )
            childSlot.value = wrongType
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPendingInteractionConversationId(context, interaction, childSlot.ptr),
            )
            assertEquals(wrongType, childSlot.value)
            childSlot.value = null
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentPendingInteractionConversationId(otherContext, interaction, childSlot.ptr),
            )
            assertNull(childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPendingInteractionConversationId(context, wrongType, childSlot.ptr),
            )
            assertNull(childSlot.value)

            val staleInvocation = invocation
            val staleInteraction = interaction
            val staleIntegration = integration
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationDestroy(context, invocationSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPendingInteractionDestroy(context, interactionSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationDestroy(context, integrationSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentInvocationNameCopy(context, staleInvocation, null, 0uL, required.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentPendingInteractionConversationId(context, staleInteraction, childSlot.ptr),
            )
            assertNull(childSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentIntegrationDisplayNameCopy(context, staleIntegration, null, 0uL, required.ptr),
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, wrongTypeSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }

        val reclaimContextSlot = sealedBaseContext()
        val reclaimContext = assertNotNull(reclaimContextSlot.value)
        createSealedBasePluginInvocation(reclaimContext)
        createSealedBaseSkillInvocation(reclaimContext)
        createSealedBaseApprovalInteraction(reclaimContext)
        createSealedBaseElicitationInteraction(reclaimContext)
        createSealedBaseConnectorIntegration(reclaimContext)
        createSealedBaseMcpIntegration(reclaimContext)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(reclaimContextSlot.ptr))
        assertNull(reclaimContextSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(reclaimContextSlot.ptr))
    }
}

private fun withSealedBaseContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = sealedBaseContext()
    val otherContextSlot = sealedBaseContext()
    val context = assertNotNull(contextSlot.value)
    val otherContext = assertNotNull(otherContextSlot.value)
    try {
        block(context, otherContext)
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.sealedBaseContext(): COpaquePointerVar = alloc<COpaquePointerVar>().also {
    it.value = null
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
}

private fun MemScope.emptySealedBaseHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.sealedBaseView(value: String): CPointer<codex_agent_string_view> =
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

private fun MemScope.createSealedBasePluginInvocation(context: COpaquePointer): COpaquePointerVar {
    val leaf = emptySealedBaseHandle()
    val aggregate = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationPluginCreate(
            context,
            sealedBaseView("review-plugin"),
            sealedBaseView("plugin://review@official"),
            leaf.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationFromPlugin(context, assertNotNull(leaf.value), aggregate.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationPluginDestroy(context, leaf.ptr))
    return aggregate
}

private fun MemScope.createSealedBaseSkillInvocation(context: COpaquePointer): COpaquePointerVar {
    val leaf = emptySealedBaseHandle()
    val aggregate = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationSkillCreate(
            context,
            sealedBaseView("review-skill"),
            sealedBaseView("/skills/review.md"),
            leaf.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentInvocationFromSkill(context, assertNotNull(leaf.value), aggregate.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentInvocationSkillDestroy(context, leaf.ptr))
    return aggregate
}

private fun MemScope.createSealedBaseApprovalInteraction(context: COpaquePointer): COpaquePointerVar {
    val conversationId = emptySealedBaseHandle()
    val approval = emptySealedBaseHandle()
    val interaction = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationIdCreate(
            context,
            sealedBaseView("approval-conversation"),
            conversationId.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingApprovalCreate(
            context,
            sealedBaseView("approval-request"),
            assertNotNull(conversationId.value),
            sealedBaseView("Approve?"),
            sealedBaseView("Review the request"),
            approval.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionFromApproval(
            context,
            assertNotNull(approval.value),
            interaction.ptr,
        ),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingApprovalDestroy(context, approval.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversationId.ptr))
    return interaction
}

private fun MemScope.createSealedBaseElicitationInteraction(context: COpaquePointer): COpaquePointerVar {
    val conversationId = emptySealedBaseHandle()
    val elicitation = emptySealedBaseHandle()
    val pending = emptySealedBaseHandle()
    val interaction = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConversationIdCreate(
            context,
            sealedBaseView("elicitation-conversation"),
            conversationId.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentElicitationCreate(
            context,
            sealedBaseView("elicitation-request"),
            sealedBaseView("review-server"),
            assertNotNull(conversationId.value),
            sealedBaseView("Provide review input"),
            0,
            null,
            0uL,
            0,
            sealedBaseView(""),
            elicitation.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingElicitationCreate(
            context,
            assertNotNull(elicitation.value),
            pending.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentPendingInteractionFromElicitation(
            context,
            assertNotNull(pending.value),
            interaction.ptr,
        ),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPendingElicitationDestroy(context, pending.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentElicitationDestroy(context, elicitation.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConversationIdDestroy(context, conversationId.ptr))
    return interaction
}

private fun MemScope.createSealedBaseConnectorIntegration(context: COpaquePointer): COpaquePointerVar {
    val connector = emptySealedBaseHandle()
    val concrete = emptySealedBaseHandle()
    val integration = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentConnectorCreate(
            context,
            sealedBaseView("drive"),
            sealedBaseView("Drive connector"),
            sealedBaseView("Drive files"),
            0,
            sealedBaseView(""),
            1,
            1,
            null,
            0uL,
            connector.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationConnectorCreate(context, assertNotNull(connector.value), concrete.ptr),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationFromConnector(context, assertNotNull(concrete.value), integration.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationConnectorDestroy(context, concrete.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentConnectorDestroy(context, connector.ptr))
    return integration
}

private fun MemScope.createSealedBaseMcpIntegration(context: COpaquePointer): COpaquePointerVar {
    val server = emptySealedBaseHandle()
    val concrete = emptySealedBaseHandle()
    val integration = emptySealedBaseHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpServerCreate(
            context,
            sealedBaseView("review-mcp"),
            sealedBaseView("Review MCP"),
            0,
            null,
            4,
            1,
            server.ptr,
        ),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationMcpServerCreate(context, assertNotNull(server.value), concrete.ptr),
    )
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentIntegrationFromMcpServer(context, assertNotNull(concrete.value), integration.ptr),
    )
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentIntegrationMcpServerDestroy(context, concrete.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerDestroy(context, server.ptr))
    return integration
}

private fun MemScope.assertSealedBaseString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: SealedBaseStringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(expectedBytes.size.toULong(), required.value)
    val shortBuffer = allocArray<UByteVar>(expectedBytes.size.coerceAtLeast(1))
    required.value = ULong.MAX_VALUE
    assertEquals(
        CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, shortBuffer, (expectedBytes.size - 1).toULong(), required.ptr),
    )
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

private typealias SealedBaseStringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int
