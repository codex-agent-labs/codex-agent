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
import kotlinx.cinterop.DoubleVar
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCMcpServerConfigurationValuesTest {
    @Test
    fun d098TransportCarrierIsTaggedOwnedAndFailClosed(): Unit = withMcpServerConfigurationContexts {
            context,
            otherContext,
        ->
        val httpSlot = createHttpTransport(context, "https://mcp.example.com/api")
        val stdioSlot = createStdioTransport(context, "mcp-command")
        val carrierSlot = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportFromHttp(context, assertNotNull(httpSlot.value), carrierSlot.ptr),
        )
        val carrier = assertNotNull(carrierSlot.value)

        val kind = alloc<IntVar>().also { it.value = -1 }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportKind(context, carrier, kind.ptr))
        assertEquals(0, kind.value)
        val httpChildSlot = emptyMcpServerConfigurationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttp(context, carrier, httpChildSlot.ptr))
        val httpChild = assertNotNull(httpChildSlot.value)
        assertMcpServerConfigurationString(
            context,
            httpChild,
            "https://mcp.example.com/api",
            ::codexAgentMcpTransportHttpUrlCopy,
        )
        val wrongVariantSlot = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentMcpTransportStdio(context, carrier, wrongVariantSlot.ptr),
        )
        assertNull(wrongVariantSlot.value)

        val occupiedOutput = alloc<COpaquePointerVar>().also { it.value = httpChild }
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentMcpTransportHttp(context, carrier, occupiedOutput.ptr),
        )
        assertEquals(httpChild, occupiedOutput.value)
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentMcpTransportKind(otherContext, carrier, kind.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentMcpTransportKind(context, assertNotNull(httpSlot.value), kind.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
            codexAgentMcpTransportDestroy(context, httpSlot.ptr),
        )
        assertNotNull(httpSlot.value)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
        val secondHttpChildSlot = emptyMcpServerConfigurationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttp(context, carrier, secondHttpChildSlot.ptr))
        assertNotEquals(httpChild, secondHttpChildSlot.value)
        assertMcpServerConfigurationString(
            context,
            assertNotNull(secondHttpChildSlot.value),
            "https://mcp.example.com/api",
            ::codexAgentMcpTransportHttpUrlCopy,
        )

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpChildSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, secondHttpChildSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, carrierSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, carrierSlot.ptr))
        assertNull(carrierSlot.value)
        kind.value = 41
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentMcpTransportKind(context, carrier, kind.ptr))
        assertEquals(41, kind.value)

        val stdioCarrierSlot = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportFromStdio(context, assertNotNull(stdioSlot.value), stdioCarrierSlot.ptr),
        )
        val stdioCarrier = assertNotNull(stdioCarrierSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, stdioSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportKind(context, stdioCarrier, kind.ptr))
        assertEquals(1, kind.value)
        val stdioChildSlot = emptyMcpServerConfigurationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdio(context, stdioCarrier, stdioChildSlot.ptr))
        assertMcpServerConfigurationString(
            context,
            assertNotNull(stdioChildSlot.value),
            "mcp-command",
            ::codexAgentMcpTransportStdioCommandCopy,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, stdioCarrierSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, stdioCarrierSlot.ptr))
        assertMcpServerConfigurationString(
            context,
            assertNotNull(stdioChildSlot.value),
            "mcp-command",
            ::codexAgentMcpTransportStdioCommandCopy,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, stdioChildSlot.ptr))

        val lifecycleContextSlot = emptyMcpServerConfigurationHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(lifecycleContextSlot.ptr))
        val lifecycleContext = assertNotNull(lifecycleContextSlot.value)
        val lifecycleHttpSlot = createHttpTransport(lifecycleContext, "https://mcp.example.com/lifecycle")
        val lifecycleCarrierSlot = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportFromHttp(
                lifecycleContext,
                assertNotNull(lifecycleHttpSlot.value),
                lifecycleCarrierSlot.ptr,
            ),
        )
        val lifecycleConfiguration = createMcpServerConfiguration(
            lifecycleContext,
            assertNotNull(lifecycleCarrierSlot.value),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, lifecycleConfiguration.status)
        val lifecycleChildSlot = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpServerConfigurationTransport(
                lifecycleContext,
                assertNotNull(lifecycleConfiguration.slot.value),
                lifecycleChildSlot.ptr,
            ),
        )
        val reclaimedConfiguration = assertNotNull(lifecycleConfiguration.slot.value)
        val reclaimedCarrier = assertNotNull(lifecycleCarrierSlot.value)
        val reclaimedChild = assertNotNull(lifecycleChildSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(lifecycleContextSlot.ptr))
        assertNull(lifecycleContextSlot.value)
        val configurationSentinel = alloc<IntVar>().also { it.value = 71 }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpServerConfigurationIsEnabled(
                lifecycleContext,
                reclaimedConfiguration,
                configurationSentinel.ptr,
            ),
        )
        assertEquals(71, configurationSentinel.value)
        val carrierSentinel = alloc<IntVar>().also { it.value = 72 }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpTransportKind(lifecycleContext, reclaimedCarrier, carrierSentinel.ptr),
        )
        assertEquals(72, carrierSentinel.value)
        val childSentinel = alloc<IntVar>().also { it.value = 73 }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpTransportKind(lifecycleContext, reclaimedChild, childSentinel.ptr),
        )
        assertEquals(73, childSentinel.value)
        val emptyOutput = emptyMcpServerConfigurationHandle()
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpServerConfigurationTransport(
                lifecycleContext,
                reclaimedConfiguration,
                emptyOutput.ptr,
            ),
        )
        assertNull(emptyOutput.value)
    }

    @Test
    fun d098ConfigurationProjectsEveryPropertyEnumCollectionAndOwnedChild(): Unit =
        withMcpServerConfigurationContexts { context, _ ->
            val httpSlot = createHttpTransport(context, "https://mcp.example.com/owned")
            val carrierSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportFromHttp(context, assertNotNull(httpSlot.value), carrierSlot.ptr),
            )
            val oauthSlot = createOauth(context, "client-λ", 49152)
            val toolSlots = (0..3).map { createToolConfiguration(context, 1, it) }
            val result = createMcpServerConfiguration(
                context = context,
                transport = assertNotNull(carrierSlot.value),
                name = "server_1",
                hasAuthentication = 1,
                authentication = 0,
                isEnabled = 0,
                isRequired = 1,
                supportsParallelToolCalls = 1,
                omitToolsFrom = listOf(0, 1, 2),
                startupTimeoutSeconds = 0.25,
                toolTimeoutSeconds = 1.0e19,
                defaultToolApproval = 3,
                enabledTools = listOf("tool-α", "tool-b", "tool-α"),
                disabledTools = emptyList(),
                scopes = listOf("scope-a", "scope-b"),
                oauth = assertNotNull(oauthSlot.value),
                oauthResource = "resource://λ",
                tools = linkedMapOf(
                    "auto" to assertNotNull(toolSlots[0].value),
                    "prompt" to assertNotNull(toolSlots[1].value),
                    "writes" to assertNotNull(toolSlots[2].value),
                    "approve" to assertNotNull(toolSlots[3].value),
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, result.status)
            val configuration = assertNotNull(result.slot.value)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, carrierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpOauthConfigurationDestroy(context, oauthSlot.ptr))
            toolSlots.forEach { assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpToolConfigurationDestroy(context, it.ptr)) }

            assertMcpServerConfigurationString(
                context,
                configuration,
                "server_1",
                ::codexAgentMcpServerConfigurationNameCopy,
            )
            assertMcpServerConfigurationOptionalInt(
                context,
                configuration,
                1,
                0,
                ::codexAgentMcpServerConfigurationAuthentication,
            )
            assertMcpServerConfigurationString(
                context,
                configuration,
                "local",
                ::codexAgentMcpServerConfigurationEnvironmentIdCopy,
            )
            assertMcpServerConfigurationInt(context, configuration, 0, ::codexAgentMcpServerConfigurationIsEnabled)
            assertMcpServerConfigurationInt(context, configuration, 1, ::codexAgentMcpServerConfigurationIsRequired)
            assertMcpServerConfigurationInt(
                context,
                configuration,
                1,
                ::codexAgentMcpServerConfigurationSupportsParallelToolCalls,
            )
            assertMcpServerConfigurationInt(
                context,
                configuration,
                1,
                ::codexAgentMcpServerConfigurationHasOmitToolsFrom,
            )
            assertMcpServerConfigurationCount(
                context,
                configuration,
                3UL,
                ::codexAgentMcpServerConfigurationOmitToolsFromCount,
            )
            listOf(0, 1, 2).forEachIndexed { index, expected ->
                val actual = alloc<IntVar>().also { it.value = -1 }
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerConfigurationOmitToolsFromAt(
                        context,
                        configuration,
                        index.toULong(),
                        actual.ptr,
                    ),
                )
                assertEquals(expected, actual.value)
            }
            assertMcpServerConfigurationOptionalDouble(
                context,
                configuration,
                1,
                0.25,
                ::codexAgentMcpServerConfigurationStartupTimeoutSeconds,
            )
            assertMcpServerConfigurationOptionalDouble(
                context,
                configuration,
                1,
                1.0e19,
                ::codexAgentMcpServerConfigurationToolTimeoutSeconds,
            )
            assertMcpServerConfigurationOptionalInt(
                context,
                configuration,
                1,
                3,
                ::codexAgentMcpServerConfigurationDefaultToolApproval,
            )
            assertOptionalStringList(
                context,
                configuration,
                listOf("tool-α", "tool-b", "tool-α"),
                ::codexAgentMcpServerConfigurationHasEnabledTools,
                ::codexAgentMcpServerConfigurationEnabledToolsCount,
                ::codexAgentMcpServerConfigurationEnabledToolCopyAt,
            )
            assertOptionalStringList(
                context,
                configuration,
                emptyList(),
                ::codexAgentMcpServerConfigurationHasDisabledTools,
                ::codexAgentMcpServerConfigurationDisabledToolsCount,
                ::codexAgentMcpServerConfigurationDisabledToolCopyAt,
            )
            assertOptionalStringList(
                context,
                configuration,
                listOf("scope-a", "scope-b"),
                ::codexAgentMcpServerConfigurationHasScopes,
                ::codexAgentMcpServerConfigurationScopesCount,
                ::codexAgentMcpServerConfigurationScopeCopyAt,
            )
            assertMcpServerConfigurationInt(context, configuration, 1, ::codexAgentMcpServerConfigurationHasOauth)
            val oauthChildSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationOauth(context, configuration, oauthChildSlot.ptr),
            )
            val oauthChild = assertNotNull(oauthChildSlot.value)
            val secondOauthChildSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationOauth(context, configuration, secondOauthChildSlot.ptr),
            )
            assertNotEquals(oauthChild, secondOauthChildSlot.value)
            assertMcpServerConfigurationString(
                context,
                oauthChild,
                "client-λ",
                ::codexAgentMcpOauthConfigurationClientIdCopy,
            )
            assertMcpServerConfigurationInt(
                context,
                configuration,
                1,
                ::codexAgentMcpServerConfigurationHasOauthResource,
            )
            assertMcpServerConfigurationString(
                context,
                configuration,
                "resource://λ",
                ::codexAgentMcpServerConfigurationOauthResourceCopy,
            )

            assertMcpServerConfigurationCount(
                context,
                configuration,
                4UL,
                ::codexAgentMcpServerConfigurationToolsCount,
            )
            val expectedTools = listOf("auto", "prompt", "writes", "approve")
            expectedTools.forEachIndexed { index, key ->
                assertMcpServerConfigurationStringAt(
                    context,
                    configuration,
                    index.toULong(),
                    key,
                    ::codexAgentMcpServerConfigurationToolsKeyCopyAt,
                )
                val childSlot = emptyMcpServerConfigurationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerConfigurationToolsValueAt(
                        context,
                        configuration,
                        index.toULong(),
                        childSlot.ptr,
                    ),
                )
                val child = assertNotNull(childSlot.value)
                val secondChildSlot = emptyMcpServerConfigurationHandle()
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerConfigurationToolsValueAt(
                        context,
                        configuration,
                        index.toULong(),
                        secondChildSlot.ptr,
                    ),
                )
                assertNotEquals(child, secondChildSlot.value)
                assertMcpServerConfigurationOptionalInt(
                    context,
                    child,
                    1,
                    index,
                    ::codexAgentMcpToolConfigurationApproval,
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpToolConfigurationDestroy(context, childSlot.ptr))
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpToolConfigurationDestroy(context, secondChildSlot.ptr),
                )
            }

            val transportChildSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationTransport(context, configuration, transportChildSlot.ptr),
            )
            val transportChild = assertNotNull(transportChildSlot.value)
            val secondTransportChildSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationTransport(context, configuration, secondTransportChildSlot.ptr),
            )
            assertNotEquals(transportChild, secondTransportChildSlot.value)
            val transportKind = alloc<IntVar>()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportKind(context, transportChild, transportKind.ptr))
            assertEquals(0, transportKind.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, result.slot.ptr),
            )
            assertNull(result.slot.value)
            assertMcpServerConfigurationString(
                context,
                oauthChild,
                "client-λ",
                ::codexAgentMcpOauthConfigurationClientIdCopy,
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpOauthConfigurationDestroy(context, oauthChildSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpOauthConfigurationDestroy(context, secondOauthChildSlot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, transportChildSlot.ptr))
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportDestroy(context, secondTransportChildSlot.ptr),
            )
        }

    @Test
    fun d098ConfigurationPreservesAbsentPresentEmptyDefaultsAndAllAuthenticationValues(): Unit =
        withMcpServerConfigurationContexts { context, _ ->
            val httpSlot = createHttpTransport(context, "https://mcp.example.com/defaults")
            val carrierSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportFromHttp(context, assertNotNull(httpSlot.value), carrierSlot.ptr),
            )
            val carrier = assertNotNull(carrierSlot.value)
            listOf(0, 1).forEach { authentication ->
                val result = createMcpServerConfiguration(
                    context,
                    carrier,
                    hasAuthentication = 1,
                    authentication = authentication,
                )
                assertEquals(CODEX_AGENT_STATUS_OK, result.status)
                val configuration = assertNotNull(result.slot.value)
                assertMcpServerConfigurationOptionalInt(
                    context,
                    configuration,
                    1,
                    authentication,
                    ::codexAgentMcpServerConfigurationAuthentication,
                )
                assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerConfigurationDestroy(context, result.slot.ptr))
            }
            (0..3).forEach { approval ->
                val result = createMcpServerConfiguration(
                    context,
                    carrier,
                    defaultToolApproval = approval,
                )
                assertEquals(CODEX_AGENT_STATUS_OK, result.status)
                assertMcpServerConfigurationOptionalInt(
                    context,
                    assertNotNull(result.slot.value),
                    1,
                    approval,
                    ::codexAgentMcpServerConfigurationDefaultToolApproval,
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerConfigurationDestroy(context, result.slot.ptr),
                )
                assertEquals(
                    CODEX_AGENT_STATUS_OK,
                    codexAgentMcpServerConfigurationDestroy(context, result.slot.ptr),
                )
            }

            val absent = createMcpServerConfiguration(context, carrier)
            assertEquals(CODEX_AGENT_STATUS_OK, absent.status)
            val absentConfiguration = assertNotNull(absent.slot.value)
            assertMcpServerConfigurationOptionalInt(
                context,
                absentConfiguration,
                0,
                0,
                ::codexAgentMcpServerConfigurationAuthentication,
            )
            assertMcpServerConfigurationOptionalDouble(
                context,
                absentConfiguration,
                0,
                0.0,
                ::codexAgentMcpServerConfigurationStartupTimeoutSeconds,
            )
            assertMcpServerConfigurationOptionalDouble(
                context,
                absentConfiguration,
                0,
                0.0,
                ::codexAgentMcpServerConfigurationToolTimeoutSeconds,
            )
            assertMcpServerConfigurationOptionalInt(
                context,
                absentConfiguration,
                0,
                0,
                ::codexAgentMcpServerConfigurationDefaultToolApproval,
            )
            assertAbsentOptionalList(
                context,
                absentConfiguration,
                ::codexAgentMcpServerConfigurationHasOmitToolsFrom,
                ::codexAgentMcpServerConfigurationOmitToolsFromCount,
            )
            assertAbsentOptionalList(
                context,
                absentConfiguration,
                ::codexAgentMcpServerConfigurationHasEnabledTools,
                ::codexAgentMcpServerConfigurationEnabledToolsCount,
            )
            assertAbsentOptionalList(
                context,
                absentConfiguration,
                ::codexAgentMcpServerConfigurationHasDisabledTools,
                ::codexAgentMcpServerConfigurationDisabledToolsCount,
            )
            assertAbsentOptionalList(
                context,
                absentConfiguration,
                ::codexAgentMcpServerConfigurationHasScopes,
                ::codexAgentMcpServerConfigurationScopesCount,
            )
            assertMcpServerConfigurationInt(
                context,
                absentConfiguration,
                0,
                ::codexAgentMcpServerConfigurationHasOauth,
            )
            assertMcpServerConfigurationInt(
                context,
                absentConfiguration,
                0,
                ::codexAgentMcpServerConfigurationHasOauthResource,
            )
            val notReadyOutput = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentMcpServerConfigurationOauth(context, absentConfiguration, notReadyOutput.ptr),
            )
            assertNull(notReadyOutput.value)
            val required = alloc<ULongVar>().also { it.value = 99UL }
            assertEquals(
                CODEX_AGENT_STATUS_NOT_READY,
                codexAgentMcpServerConfigurationOauthResourceCopy(
                    context,
                    absentConfiguration,
                    null,
                    0UL,
                    required.ptr,
                ),
            )
            assertEquals(99UL, required.value)
            assertMcpServerConfigurationCount(
                context,
                absentConfiguration,
                0UL,
                ::codexAgentMcpServerConfigurationToolsCount,
            )
            assertMcpServerConfigurationInt(context, absentConfiguration, 1, ::codexAgentMcpServerConfigurationIsEnabled)
            assertMcpServerConfigurationInt(context, absentConfiguration, 0, ::codexAgentMcpServerConfigurationIsRequired)
            assertMcpServerConfigurationInt(
                context,
                absentConfiguration,
                0,
                ::codexAgentMcpServerConfigurationSupportsParallelToolCalls,
            )

            val presentEmpty = createMcpServerConfiguration(
                context,
                carrier,
                omitToolsFrom = emptyList(),
                enabledTools = emptyList(),
                disabledTools = emptyList(),
                scopes = emptyList(),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, presentEmpty.status)
            val presentEmptyConfiguration = assertNotNull(presentEmpty.slot.value)
            val emptyListGetters: List<
                Pair<McpServerConfigurationIntGetter, McpServerConfigurationCountGetter>,
            > = listOf(
                ::codexAgentMcpServerConfigurationHasOmitToolsFrom to
                    ::codexAgentMcpServerConfigurationOmitToolsFromCount,
                ::codexAgentMcpServerConfigurationHasEnabledTools to
                    ::codexAgentMcpServerConfigurationEnabledToolsCount,
                ::codexAgentMcpServerConfigurationHasDisabledTools to
                    ::codexAgentMcpServerConfigurationDisabledToolsCount,
                ::codexAgentMcpServerConfigurationHasScopes to
                    ::codexAgentMcpServerConfigurationScopesCount,
            )
            emptyListGetters.forEach { (has, count) ->
                assertMcpServerConfigurationInt(context, presentEmptyConfiguration, 1, has)
                assertMcpServerConfigurationCount(context, presentEmptyConfiguration, 0UL, count)
            }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, presentEmpty.slot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpServerConfigurationDestroy(context, absent.slot.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, carrierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
        }

    @Test
    fun d098ConfigurationRejectsMalformedCanonicalAndOwnershipInputs(): Unit =
        withMcpServerConfigurationContexts { context, otherContext ->
            val httpSlot = createHttpTransport(context, "https://mcp.example.com/reject")
            val httpCarrierSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportFromHttp(context, assertNotNull(httpSlot.value), httpCarrierSlot.ptr),
            )
            val httpCarrier = assertNotNull(httpCarrierSlot.value)
            val stdioSlot = createStdioTransport(context, "stdio")
            val stdioCarrierSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportFromStdio(context, assertNotNull(stdioSlot.value), stdioCarrierSlot.ptr),
            )
            val stdioCarrier = assertNotNull(stdioCarrierSlot.value)
            val crossOauth = createOauth(context, "cross-client", 49153)
            val helperHttpSlot = createHttpTransport(
                context,
                "https://mcp.example.com/helper",
                headersHelper = "headers-command",
            )
            val helperCarrierSlot = emptyMcpServerConfigurationHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportFromHttp(
                    context,
                    assertNotNull(helperHttpSlot.value),
                    helperCarrierSlot.ptr,
                ),
            )
            val helperCarrier = assertNotNull(helperCarrierSlot.value)

            listOf(
                createMcpServerConfiguration(context, httpCarrier, hasAuthentication = 2),
                createMcpServerConfiguration(context, httpCarrier, hasAuthentication = 0, authentication = 1),
                createMcpServerConfiguration(context, httpCarrier, hasAuthentication = 1, authentication = 2),
                createMcpServerConfiguration(context, httpCarrier, isEnabled = 2),
                createMcpServerConfiguration(context, httpCarrier, name = "bad name"),
                createMcpServerConfiguration(context, httpCarrier, environmentId = " "),
                createMcpServerConfiguration(context, httpCarrier, startupTimeoutSeconds = 0.0),
                createMcpServerConfiguration(context, httpCarrier, startupTimeoutSeconds = Double.NaN),
                createMcpServerConfiguration(context, httpCarrier, startupTimeoutSeconds = 1.8446744073709552E19),
                createMcpServerConfiguration(context, httpCarrier, defaultToolApproval = 4),
                createMcpServerConfiguration(context, httpCarrier, omitToolsFrom = listOf(3)),
                createMcpServerConfiguration(
                    context,
                    httpCarrier,
                    nameView = invalidMcpServerConfigurationUtf8View(),
                ),
                createMcpServerConfiguration(context, stdioCarrier, hasAuthentication = 1, authentication = 0),
                createMcpServerConfiguration(
                    context,
                    stdioCarrier,
                    oauth = assertNotNull(crossOauth.value),
                ),
                createMcpServerConfiguration(context, stdioCarrier, oauthResource = "resource://stdio"),
                createMcpServerConfiguration(context, helperCarrier, environmentId = "remote"),
            ).forEachIndexed { index, result ->
                assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, result.status, "malformed case $index")
                assertNull(result.slot.value)
            }

            val duplicateTool = createToolConfiguration(context, 0, 0)
            val duplicate = createMcpServerConfiguration(
                context,
                httpCarrier,
                tools = linkedMapOf("duplicate" to assertNotNull(duplicateTool.value)),
                duplicateToolKey = "duplicate",
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, duplicate.status)
            assertNull(duplicate.slot.value)

            val wrongOauthType = createMcpServerConfiguration(
                context,
                httpCarrier,
                oauth = assertNotNull(duplicateTool.value),
            )
            assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, wrongOauthType.status)
            assertNull(wrongOauthType.slot.value)
            val wrongToolType = createMcpServerConfiguration(
                context,
                httpCarrier,
                tools = linkedMapOf("wrong" to assertNotNull(crossOauth.value)),
            )
            assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, wrongToolType.status)
            assertNull(wrongToolType.slot.value)

            val wrongContext = createMcpServerConfiguration(otherContext, httpCarrier)
            assertEquals(CODEX_AGENT_STATUS_WRONG_CONTEXT, wrongContext.status)
            assertNull(wrongContext.slot.value)
            val wrongType = createMcpServerConfiguration(context, assertNotNull(httpSlot.value))
            assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, wrongType.status)
            assertNull(wrongType.slot.value)

            val valid = createMcpServerConfiguration(context, httpCarrier)
            assertEquals(CODEX_AGENT_STATUS_OK, valid.status)
            val configuration = assertNotNull(valid.slot.value)
            val occupiedCreate = createMcpServerConfiguration(
                context,
                httpCarrier,
                occupiedOutput = configuration,
            )
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, occupiedCreate.status)
            assertEquals(configuration, occupiedCreate.slot.value)
            val occupied = alloc<COpaquePointerVar>().also { it.value = configuration }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerConfigurationTransport(context, configuration, occupied.ptr),
            )
            assertEquals(configuration, occupied.value)
            val count = alloc<ULongVar>().also { it.value = 88UL }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerConfigurationToolsCount(context, configuration, null),
            )
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpServerConfigurationToolsKeyCopyAt(
                    context,
                    configuration,
                    ULong.MAX_VALUE,
                    null,
                    0UL,
                    count.ptr,
                ),
            )
            assertEquals(88UL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentMcpServerConfigurationToolsCount(otherContext, configuration, count.ptr),
            )
            assertEquals(88UL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpServerConfigurationDestroy(context, httpCarrierSlot.ptr),
            )
            assertNotNull(httpCarrierSlot.value)

            val stale = configuration
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpServerConfigurationDestroy(context, valid.slot.ptr))
            val enabled = alloc<IntVar>().also { it.value = 77 }
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentMcpServerConfigurationIsEnabled(context, stale, enabled.ptr),
            )
            assertEquals(77, enabled.value)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpToolConfigurationDestroy(context, duplicateTool.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpOauthConfigurationDestroy(context, crossOauth.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, helperCarrierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, helperHttpSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, stdioCarrierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, stdioSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportDestroy(context, httpCarrierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
        }
}

private data class McpServerConfigurationCreateResult(
    val status: Int,
    val slot: COpaquePointerVar,
)

private typealias McpServerConfigurationStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int
private typealias McpServerConfigurationStringCopyAt = (
    COpaquePointer?, COpaquePointer?, ULong, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int
private typealias McpServerConfigurationIntGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?,
) -> Int
private typealias McpServerConfigurationCountGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?,
) -> Int
private typealias McpServerConfigurationOptionalIntGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<IntVar>?,
) -> Int
private typealias McpServerConfigurationOptionalDoubleGetter = (
    COpaquePointer?, COpaquePointer?, CPointer<IntVar>?, CPointer<DoubleVar>?,
) -> Int

private fun withMcpServerConfigurationContexts(
    block: MemScope.(COpaquePointer, COpaquePointer) -> Unit,
): Unit = memScoped {
    val contextSlot = emptyMcpServerConfigurationHandle()
    val otherContextSlot = emptyMcpServerConfigurationHandle()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherContextSlot.ptr))
    try {
        block(assertNotNull(contextSlot.value), assertNotNull(otherContextSlot.value))
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherContextSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(otherContextSlot.value)
        assertNull(contextSlot.value)
    }
}

private fun MemScope.emptyMcpServerConfigurationHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.mcpServerConfigurationView(value: String): CPointer<codex_agent_string_view> {
    val bytes = value.encodeToByteArray()
    return alloc<codex_agent_string_view>().also { view ->
        view.size = bytes.size.toULong()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
    }.ptr
}

private fun MemScope.invalidMcpServerConfigurationUtf8View(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3U
    bytes[1] = 0x28U
    return alloc<codex_agent_string_view>().also {
        it.data = bytes
        it.size = 2UL
    }.ptr
}

private fun MemScope.mcpServerConfigurationStringArray(values: List<String>): CPointer<codex_agent_string_view>? {
    if (values.isEmpty()) return null
    return allocArray<codex_agent_string_view>(values.size).also { array ->
        values.forEachIndexed { index, value ->
            val view = mcpServerConfigurationView(value).pointed
            array[index].data = view.data
            array[index].size = view.size
        }
    }
}

private fun MemScope.mcpServerConfigurationIntArray(values: List<Int>): CPointer<IntVar>? {
    if (values.isEmpty()) return null
    return allocArray<IntVar>(values.size).also { array -> values.forEachIndexed { index, value -> array[index] = value } }
}

private fun MemScope.mcpServerConfigurationHandleArray(values: List<COpaquePointer>): CPointer<COpaquePointerVar>? {
    if (values.isEmpty()) return null
    return allocArray<COpaquePointerVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }
}

private fun MemScope.createHttpTransport(
    context: COpaquePointer,
    url: String,
    headersHelper: String? = null,
): COpaquePointerVar {
    val slot = emptyMcpServerConfigurationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpTransportHttpCreate(
            context,
            mcpServerConfigurationView(url),
            0,
            mcpServerConfigurationView(""),
            0,
            null,
            null,
            0UL,
            0,
            null,
            null,
            0UL,
            if (headersHelper == null) 0 else 1,
            mcpServerConfigurationView(headersHelper ?: ""),
            slot.ptr,
        ),
    )
    return slot
}

private fun MemScope.createStdioTransport(context: COpaquePointer, command: String): COpaquePointerVar {
    val slot = emptyMcpServerConfigurationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpTransportStdioCreate(
            context,
            mcpServerConfigurationView(command),
            null,
            0UL,
            0,
            mcpServerConfigurationView(""),
            0,
            null,
            null,
            0UL,
            null,
            0UL,
            slot.ptr,
        ),
    )
    return slot
}

private fun MemScope.createOauth(context: COpaquePointer, clientId: String, callbackPort: Int): COpaquePointerVar {
    val slot = emptyMcpServerConfigurationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpOauthConfigurationCreate(
            context,
            1,
            mcpServerConfigurationView(clientId),
            1,
            callbackPort,
            slot.ptr,
        ),
    )
    return slot
}

private fun MemScope.createToolConfiguration(
    context: COpaquePointer,
    hasApproval: Int,
    approval: Int,
): COpaquePointerVar {
    val slot = emptyMcpServerConfigurationHandle()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentMcpToolConfigurationCreate(context, hasApproval, approval, slot.ptr),
    )
    return slot
}

private fun MemScope.createMcpServerConfiguration(
    context: COpaquePointer,
    transport: COpaquePointer,
    name: String = "server",
    nameView: CPointer<codex_agent_string_view>? = null,
    environmentId: String = "local",
    hasAuthentication: Int = 0,
    authentication: Int = 0,
    isEnabled: Int = 1,
    isRequired: Int = 0,
    supportsParallelToolCalls: Int = 0,
    omitToolsFrom: List<Int>? = null,
    startupTimeoutSeconds: Double? = null,
    toolTimeoutSeconds: Double? = null,
    defaultToolApproval: Int? = null,
    enabledTools: List<String>? = null,
    disabledTools: List<String>? = null,
    scopes: List<String>? = null,
    oauth: COpaquePointer? = null,
    oauthResource: String? = null,
    tools: LinkedHashMap<String, COpaquePointer> = linkedMapOf(),
    duplicateToolKey: String? = null,
    occupiedOutput: COpaquePointer? = null,
): McpServerConfigurationCreateResult {
    val keys = tools.keys.toMutableList().also { if (duplicateToolKey != null) it += duplicateToolKey }
    val values = tools.values.toMutableList().also {
        if (duplicateToolKey != null) it += requireNotNull(tools[duplicateToolKey])
    }
    val slot = alloc<COpaquePointerVar>().also { it.value = occupiedOutput }
    val status = codexAgentMcpServerConfigurationCreate(
        context,
        nameView ?: mcpServerConfigurationView(name),
        transport,
        hasAuthentication,
        authentication,
        mcpServerConfigurationView(environmentId),
        isEnabled,
        isRequired,
        supportsParallelToolCalls,
        if (omitToolsFrom == null) 0 else 1,
        omitToolsFrom?.let { mcpServerConfigurationIntArray(it) },
        omitToolsFrom?.size?.toULong() ?: 0UL,
        if (startupTimeoutSeconds == null) 0 else 1,
        startupTimeoutSeconds ?: 0.0,
        if (toolTimeoutSeconds == null) 0 else 1,
        toolTimeoutSeconds ?: 0.0,
        if (defaultToolApproval == null) 0 else 1,
        defaultToolApproval ?: 0,
        if (enabledTools == null) 0 else 1,
        enabledTools?.let { mcpServerConfigurationStringArray(it) },
        enabledTools?.size?.toULong() ?: 0UL,
        if (disabledTools == null) 0 else 1,
        disabledTools?.let { mcpServerConfigurationStringArray(it) },
        disabledTools?.size?.toULong() ?: 0UL,
        if (scopes == null) 0 else 1,
        scopes?.let { mcpServerConfigurationStringArray(it) },
        scopes?.size?.toULong() ?: 0UL,
        if (oauth == null) 0 else 1,
        oauth,
        if (oauthResource == null) 0 else 1,
        mcpServerConfigurationView(oauthResource ?: ""),
        mcpServerConfigurationStringArray(keys),
        mcpServerConfigurationHandleArray(values),
        keys.size.toULong(),
        slot.ptr,
    )
    return McpServerConfigurationCreateResult(status, slot)
}

private fun MemScope.assertMcpServerConfigurationString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: McpServerConfigurationStringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0UL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size.coerceAtLeast(1))
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertMcpServerConfigurationStringAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    copy: McpServerConfigurationStringCopyAt,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, index, null, 0UL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, index, buffer, expectedBytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertMcpServerConfigurationInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: McpServerConfigurationIntGetter,
) {
    val output = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertMcpServerConfigurationCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    getter: McpServerConfigurationCountGetter,
) {
    val output = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertMcpServerConfigurationOptionalInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHasValue: Int,
    expectedValue: Int,
    getter: McpServerConfigurationOptionalIntGetter,
) {
    val hasValue = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, hasValue.ptr, value.ptr))
    assertEquals(expectedHasValue, hasValue.value)
    assertEquals(expectedValue, value.value)
}

private fun MemScope.assertMcpServerConfigurationOptionalDouble(
    context: COpaquePointer,
    handle: COpaquePointer,
    expectedHasValue: Int,
    expectedValue: Double,
    getter: McpServerConfigurationOptionalDoubleGetter,
) {
    val hasValue = alloc<IntVar>().also { it.value = -1 }
    val value = alloc<DoubleVar>().also { it.value = -1.0 }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, hasValue.ptr, value.ptr))
    assertEquals(expectedHasValue, hasValue.value)
    assertEquals(expectedValue, value.value)
}

private fun MemScope.assertOptionalStringList(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: List<String>,
    has: McpServerConfigurationIntGetter,
    count: McpServerConfigurationCountGetter,
    copyAt: McpServerConfigurationStringCopyAt,
) {
    assertMcpServerConfigurationInt(context, handle, 1, has)
    assertMcpServerConfigurationCount(context, handle, expected.size.toULong(), count)
    expected.forEachIndexed { index, value ->
        assertMcpServerConfigurationStringAt(context, handle, index.toULong(), value, copyAt)
    }
}

private fun MemScope.assertAbsentOptionalList(
    context: COpaquePointer,
    handle: COpaquePointer,
    has: McpServerConfigurationIntGetter,
    count: McpServerConfigurationCountGetter,
) {
    assertMcpServerConfigurationInt(context, handle, 0, has)
    val output = alloc<ULongVar>().also { it.value = 91UL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, count(context, handle, output.ptr))
    assertEquals(91UL, output.value)
}
