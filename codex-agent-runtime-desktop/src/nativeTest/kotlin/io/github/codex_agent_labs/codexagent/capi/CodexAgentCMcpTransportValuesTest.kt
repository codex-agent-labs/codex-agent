@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
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
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCMcpTransportValuesTest {
    @Test
    fun httpConstructorAndPropertiesPreserveNullableOrderedMaps(): Unit = withTransportContexts { context, _ ->
        val url = mutableTransportView("https://mcp.example.com/path")
        val bearer = mutableTransportView("MCP_TOKEN")
        val helper = mutableTransportView("mcp-headers")
        val firstHeaderKey = mutableTransportView("X-First")
        val firstHeaderValue = mutableTransportView("one")
        val headerKeys = transportStringArray(firstHeaderKey.view, transportView("X-Second"))
        val headerValues = transportStringArray(firstHeaderValue.view, transportView("two"))
        val environmentHeaderKeys = transportStringArray(
            transportView("Authorization"),
            transportView("X-Remote"),
        )
        val environmentHeaderValues = transportStringArray(
            transportView("MCP_AUTH"),
            transportView("MCP_REMOTE"),
        )
        val transportSlot = emptyTransportHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportHttpCreate(
                context,
                url.view,
                1,
                bearer.view,
                1,
                headerKeys,
                headerValues,
                2UL,
                1,
                environmentHeaderKeys,
                environmentHeaderValues,
                2UL,
                1,
                helper.view,
                transportSlot.ptr,
            ),
        )
        val transport = assertNotNull(transportSlot.value)

        url.bytes[0] = 'X'.code.toUByte()
        bearer.bytes[0] = 'X'.code.toUByte()
        helper.bytes[0] = 'X'.code.toUByte()
        firstHeaderKey.bytes[0] = 'Y'.code.toUByte()
        firstHeaderValue.bytes[0] = 'Y'.code.toUByte()
        setTransportString(headerKeys, 1, transportView("changed"))
        setTransportString(headerValues, 1, transportView("changed"))
        setTransportString(environmentHeaderKeys, 0, transportView("changed"))
        setTransportString(environmentHeaderValues, 0, transportView("changed"))

        assertTransportString(context, transport, "https://mcp.example.com/path", ::codexAgentMcpTransportHttpUrlCopy)
        assertTransportInt(context, transport, 1, ::codexAgentMcpTransportHttpHasBearerTokenEnvironmentVariable)
        assertTransportString(
            context,
            transport,
            "MCP_TOKEN",
            ::codexAgentMcpTransportHttpBearerTokenEnvironmentVariableCopy,
        )
        assertTransportInt(context, transport, 1, ::codexAgentMcpTransportHttpHasHeaders)
        assertTransportCount(context, transport, 2UL, ::codexAgentMcpTransportHttpHeadersCount)
        assertTransportStringAt(context, transport, 0UL, "X-First", ::codexAgentMcpTransportHttpHeadersKeyCopyAt)
        assertTransportStringAt(context, transport, 0UL, "one", ::codexAgentMcpTransportHttpHeadersValueCopyAt)
        assertTransportStringAt(context, transport, 1UL, "X-Second", ::codexAgentMcpTransportHttpHeadersKeyCopyAt)
        assertTransportStringAt(context, transport, 1UL, "two", ::codexAgentMcpTransportHttpHeadersValueCopyAt)
        assertTransportInt(context, transport, 1, ::codexAgentMcpTransportHttpHasEnvironmentHeaders)
        assertTransportCount(context, transport, 2UL, ::codexAgentMcpTransportHttpEnvironmentHeadersCount)
        assertTransportStringAt(
            context,
            transport,
            0UL,
            "Authorization",
            ::codexAgentMcpTransportHttpEnvironmentHeadersKeyCopyAt,
        )
        assertTransportStringAt(
            context,
            transport,
            0UL,
            "MCP_AUTH",
            ::codexAgentMcpTransportHttpEnvironmentHeadersValueCopyAt,
        )
        assertTransportStringAt(
            context,
            transport,
            1UL,
            "X-Remote",
            ::codexAgentMcpTransportHttpEnvironmentHeadersKeyCopyAt,
        )
        assertTransportStringAt(
            context,
            transport,
            1UL,
            "MCP_REMOTE",
            ::codexAgentMcpTransportHttpEnvironmentHeadersValueCopyAt,
        )
        assertTransportInt(context, transport, 1, ::codexAgentMcpTransportHttpHasHeadersHelper)
        assertTransportString(context, transport, "mcp-headers", ::codexAgentMcpTransportHttpHeadersHelperCopy)

        val absentSlot = emptyTransportHandle()
        val absentView = absentTransportView()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportHttpCreate(
                context,
                transportView("https://mcp.example.com"),
                0,
                absentView,
                0,
                null,
                null,
                0UL,
                0,
                null,
                null,
                0UL,
                0,
                absentView,
                absentSlot.ptr,
            ),
        )
        val absent = assertNotNull(absentSlot.value)
        assertTransportInt(context, absent, 0, ::codexAgentMcpTransportHttpHasBearerTokenEnvironmentVariable)
        assertTransportAbsentString(context, absent, ::codexAgentMcpTransportHttpBearerTokenEnvironmentVariableCopy)
        assertTransportInt(context, absent, 0, ::codexAgentMcpTransportHttpHasHeaders)
        assertTransportAbsentCount(context, absent, ::codexAgentMcpTransportHttpHeadersCount)
        assertTransportInt(context, absent, 0, ::codexAgentMcpTransportHttpHasEnvironmentHeaders)
        assertTransportAbsentCount(context, absent, ::codexAgentMcpTransportHttpEnvironmentHeadersCount)
        assertTransportInt(context, absent, 0, ::codexAgentMcpTransportHttpHasHeadersHelper)
        assertTransportAbsentString(context, absent, ::codexAgentMcpTransportHttpHeadersHelperCopy)

        val emptySlot = emptyTransportHandle()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportHttpCreate(
                context,
                transportView("http://127.0.0.1:8080/mcp"),
                0,
                absentView,
                1,
                null,
                null,
                0UL,
                1,
                null,
                null,
                0UL,
                0,
                absentView,
                emptySlot.ptr,
            ),
        )
        val empty = assertNotNull(emptySlot.value)
        assertTransportInt(context, empty, 1, ::codexAgentMcpTransportHttpHasHeaders)
        assertTransportCount(context, empty, 0UL, ::codexAgentMcpTransportHttpHeadersCount)
        assertTransportInt(context, empty, 1, ::codexAgentMcpTransportHttpHasEnvironmentHeaders)
        assertTransportCount(context, empty, 0UL, ::codexAgentMcpTransportHttpEnvironmentHeadersCount)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, transportSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, absentSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, emptySlot.ptr))
    }

    @Test
    fun stdioConstructorAndPropertiesPreserveMapListsAndOwnedChildren(): Unit =
        withTransportContexts { context, _ ->
            val firstVariableSlot = emptyTransportHandle()
            val secondVariableSlot = emptyTransportHandle()
            val absentView = absentTransportView()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableCreate(
                    context,
                    transportView("HOME"),
                    0,
                    0,
                    firstVariableSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableCreate(
                    context,
                    transportView("REMOTE_TOKEN"),
                    1,
                    1,
                    secondVariableSlot.ptr,
                ),
            )
            val firstVariable = assertNotNull(firstVariableSlot.value)
            val secondVariable = assertNotNull(secondVariableSlot.value)
            val command = mutableTransportView("node")
            val firstArgument = mutableTransportView("server.js")
            val arguments = transportStringArray(firstArgument.view, transportView("--safe"), firstArgument.view)
            val workingDirectory = mutableTransportView("/workspace")
            val firstEnvironmentKey = mutableTransportView("STATIC")
            val firstEnvironmentValue = mutableTransportView("value")
            val environmentKeys = transportStringArray(firstEnvironmentKey.view, transportView("TOKEN"))
            val environmentValues = transportStringArray(firstEnvironmentValue.view, transportView("secret-ref"))
            val forwardedEnvironment = transportHandleArray(firstVariable, secondVariable, firstVariable)
            val transportSlot = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioCreate(
                    context,
                    command.view,
                    arguments,
                    3UL,
                    1,
                    workingDirectory.view,
                    1,
                    environmentKeys,
                    environmentValues,
                    2UL,
                    forwardedEnvironment,
                    3UL,
                    transportSlot.ptr,
                ),
            )
            val transport = assertNotNull(transportSlot.value)

            command.bytes[0] = 'X'.code.toUByte()
            firstArgument.bytes[0] = 'X'.code.toUByte()
            workingDirectory.bytes[0] = 'X'.code.toUByte()
            firstEnvironmentKey.bytes[0] = 'X'.code.toUByte()
            firstEnvironmentValue.bytes[0] = 'X'.code.toUByte()
            setTransportString(arguments, 1, transportView("changed"))
            setTransportString(environmentKeys, 1, transportView("changed"))
            setTransportString(environmentValues, 1, transportView("changed"))
            forwardedEnvironment[0] = secondVariable
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableDestroy(context, firstVariableSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableDestroy(context, secondVariableSlot.ptr),
            )

            assertTransportString(context, transport, "node", ::codexAgentMcpTransportStdioCommandCopy)
            assertTransportCount(context, transport, 3UL, ::codexAgentMcpTransportStdioArgumentsCount)
            assertTransportStringAt(context, transport, 0UL, "server.js", ::codexAgentMcpTransportStdioArgumentCopyAt)
            assertTransportStringAt(context, transport, 1UL, "--safe", ::codexAgentMcpTransportStdioArgumentCopyAt)
            assertTransportStringAt(context, transport, 2UL, "server.js", ::codexAgentMcpTransportStdioArgumentCopyAt)
            assertTransportInt(context, transport, 1, ::codexAgentMcpTransportStdioHasWorkingDirectory)
            assertTransportString(
                context,
                transport,
                "/workspace",
                ::codexAgentMcpTransportStdioWorkingDirectoryCopy,
            )
            assertTransportInt(context, transport, 1, ::codexAgentMcpTransportStdioHasEnvironment)
            assertTransportCount(context, transport, 2UL, ::codexAgentMcpTransportStdioEnvironmentCount)
            assertTransportStringAt(
                context,
                transport,
                0UL,
                "STATIC",
                ::codexAgentMcpTransportStdioEnvironmentKeyCopyAt,
            )
            assertTransportStringAt(
                context,
                transport,
                0UL,
                "value",
                ::codexAgentMcpTransportStdioEnvironmentValueCopyAt,
            )
            assertTransportStringAt(
                context,
                transport,
                1UL,
                "TOKEN",
                ::codexAgentMcpTransportStdioEnvironmentKeyCopyAt,
            )
            assertTransportStringAt(
                context,
                transport,
                1UL,
                "secret-ref",
                ::codexAgentMcpTransportStdioEnvironmentValueCopyAt,
            )
            assertTransportCount(context, transport, 3UL, ::codexAgentMcpTransportStdioForwardedEnvironmentCount)

            val returnedFirstSlot = emptyTransportHandle()
            val returnedSecondSlot = emptyTransportHandle()
            val returnedDuplicateSlot = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioForwardedEnvironmentAt(context, transport, 0UL, returnedFirstSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioForwardedEnvironmentAt(context, transport, 1UL, returnedSecondSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioForwardedEnvironmentAt(context, transport, 2UL, returnedDuplicateSlot.ptr),
            )
            val returnedFirst = assertNotNull(returnedFirstSlot.value)
            val returnedSecond = assertNotNull(returnedSecondSlot.value)
            val returnedDuplicate = assertNotNull(returnedDuplicateSlot.value)
            assertTrue(returnedFirst != returnedDuplicate)
            assertTransportString(context, returnedFirst, "HOME", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertTransportString(context, returnedSecond, "REMOTE_TOKEN", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertTransportString(context, returnedDuplicate, "HOME", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableDestroy(context, returnedFirstSlot.ptr),
            )
            assertTransportString(context, returnedDuplicate, "HOME", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, transportSlot.ptr))
            assertTransportString(context, returnedSecond, "REMOTE_TOKEN", ::codexAgentMcpEnvironmentVariableNameCopy)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableDestroy(context, returnedSecondSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpEnvironmentVariableDestroy(context, returnedDuplicateSlot.ptr),
            )

            val absentSlot = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    null,
                    0UL,
                    0,
                    absentView,
                    0,
                    null,
                    null,
                    0UL,
                    null,
                    0UL,
                    absentSlot.ptr,
                ),
            )
            val absent = assertNotNull(absentSlot.value)
            assertTransportCount(context, absent, 0UL, ::codexAgentMcpTransportStdioArgumentsCount)
            assertTransportInt(context, absent, 0, ::codexAgentMcpTransportStdioHasWorkingDirectory)
            assertTransportAbsentString(context, absent, ::codexAgentMcpTransportStdioWorkingDirectoryCopy)
            assertTransportInt(context, absent, 0, ::codexAgentMcpTransportStdioHasEnvironment)
            assertTransportAbsentCount(context, absent, ::codexAgentMcpTransportStdioEnvironmentCount)
            assertTransportCount(context, absent, 0UL, ::codexAgentMcpTransportStdioForwardedEnvironmentCount)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, absentSlot.ptr))

            val presentEmptySlot = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    null,
                    0UL,
                    0,
                    absentView,
                    1,
                    null,
                    null,
                    0UL,
                    null,
                    0UL,
                    presentEmptySlot.ptr,
                ),
            )
            val presentEmpty = assertNotNull(presentEmptySlot.value)
            assertTransportInt(context, presentEmpty, 1, ::codexAgentMcpTransportStdioHasEnvironment)
            assertTransportCount(context, presentEmpty, 0UL, ::codexAgentMcpTransportStdioEnvironmentCount)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, presentEmptySlot.ptr))
        }

    @Test
    fun constructorsRejectDuplicateKeysMalformedInputsAndPreserveOutputs(): Unit =
        withTransportContexts { context, otherContext ->
            val absent = absentTransportView()
            val duplicateKeys = transportStringArray(transportView("same"), transportView("same"))
            val values = transportStringArray(transportView("first"), transportView("second"))
            val output = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    1,
                    duplicateKeys,
                    values,
                    2UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
            )
            assertNull(output.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    null,
                    0UL,
                    0,
                    absent,
                    1,
                    duplicateKeys,
                    values,
                    2UL,
                    null,
                    0UL,
                    output.ptr,
                ),
            )
            assertNull(output.value)

            val invalidUtf8 = invalidTransportUtf8View()
            val invalidCases = listOf(
                codexAgentMcpTransportHttpCreate(
                    context, invalidUtf8, 0, absent, 0, null, null, 0UL, 0, null, null, 0UL, 0, absent, output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    1,
                    invalidUtf8,
                    values,
                    1UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    2,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    0,
                    duplicateKeys,
                    values,
                    0UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    1,
                    duplicateKeys,
                    null,
                    1UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("http://example.com"),
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    1,
                    transportView(""),
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView(" "),
                    null,
                    0UL,
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    null,
                    0UL,
                    output.ptr,
                ),
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    duplicateKeys,
                    0UL,
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    null,
                    0UL,
                    output.ptr,
                ),
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    null,
                    0UL,
                    0,
                    absent,
                    0,
                    null,
                    null,
                    1UL,
                    null,
                    0UL,
                    output.ptr,
                ),
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    null,
                    0UL,
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    null,
                    ULong.MAX_VALUE,
                    output.ptr,
                ),
            )
            invalidCases.forEach { assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, it) }
            assertNull(output.value)

            output.value = otherContext
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    output.ptr,
                ),
            )
            assertEquals(otherContext, output.value)
        }

    @Test
    fun gettersRejectWrongContextTypeStaleAndBoundsWithoutChangingOutputs(): Unit =
        withTransportContexts { context, otherContext ->
            val absent = absentTransportView()
            val httpSlot = emptyTransportHandle()
            val stdioSlot = emptyTransportHandle()
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportHttpCreate(
                    context,
                    transportView("https://mcp.example.com"),
                    0,
                    absent,
                    1,
                    transportStringArray(transportView("key")),
                    transportStringArray(transportView("value")),
                    1UL,
                    0,
                    null,
                    null,
                    0UL,
                    0,
                    absent,
                    httpSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentMcpTransportStdioCreate(
                    context,
                    transportView("mcp"),
                    transportStringArray(transportView("arg")),
                    1UL,
                    0,
                    absent,
                    0,
                    null,
                    null,
                    0UL,
                    null,
                    0UL,
                    stdioSlot.ptr,
                ),
            )
            val http = assertNotNull(httpSlot.value)
            val stdio = assertNotNull(stdioSlot.value)
            val required = alloc<ULongVar>().also { it.value = 71UL }
            val count = alloc<ULongVar>().also { it.value = 73UL }
            val present = alloc<IntVar>().also { it.value = 79 }
            val childSlot = emptyTransportHandle()

            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentMcpTransportHttpUrlCopy(otherContext, http, null, 0UL, required.ptr),
            )
            assertEquals(71UL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpTransportHttpUrlCopy(context, stdio, null, 0UL, required.ptr),
            )
            assertEquals(71UL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpTransportStdioArgumentsCount(context, http, count.ptr),
            )
            assertEquals(73UL, count.value)
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpTransportHttpHasHeaders(context, stdio, present.ptr),
            )
            assertEquals(79, present.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportHttpHeadersKeyCopyAt(context, http, 1UL, null, 0UL, required.ptr),
            )
            assertEquals(71UL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportStdioArgumentCopyAt(context, stdio, ULong.MAX_VALUE, null, 0UL, required.ptr),
            )
            assertEquals(71UL, required.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportStdioForwardedEnvironmentAt(context, stdio, 0UL, childSlot.ptr),
            )
            assertNull(childSlot.value)
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentMcpTransportHttpHasHeaders(context, http, null))
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentMcpTransportHttpUrlCopy(context, http, null, 0UL, null),
            )

            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentMcpTransportHttpDestroy(context, stdioSlot.ptr),
            )
            assertEquals(stdio, stdioSlot.value)
            val stale = http
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportHttpDestroy(context, httpSlot.ptr))
            assertNull(httpSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentMcpTransportHttpUrlCopy(context, stale, null, 0UL, required.ptr),
            )
            assertEquals(71UL, required.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, stdioSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentMcpTransportStdioDestroy(context, stdioSlot.ptr))
        }

    @Test
    fun contextTeardownReclaimsOutstandingTransportValues() = memScoped {
        val contextSlot = emptyTransportHandle()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val transportSlot = emptyTransportHandle()
        val absent = absentTransportView()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentMcpTransportHttpCreate(
                context,
                transportView("https://mcp.example.com"),
                0,
                absent,
                0,
                null,
                null,
                0UL,
                0,
                null,
                null,
                0UL,
                0,
                absent,
                transportSlot.ptr,
            ),
        )
        val transport = assertNotNull(transportSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
        val required = alloc<ULongVar>().also { it.value = 83UL }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentMcpTransportHttpUrlCopy(context, transport, null, 0UL, required.ptr),
        )
        assertEquals(83UL, required.value)
    }
}

private data class TransportMutableStringView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>,
)

private typealias TransportStringCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias TransportStringCopyAt = (
    COpaquePointer?, COpaquePointer?, ULong, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias TransportIntGetter = (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int
private typealias TransportCountGetter = (COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?) -> Int

private fun withTransportContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyTransportHandle()
    val otherContextSlot = emptyTransportHandle()
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

private fun MemScope.emptyTransportHandle(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.transportView(value: String): CPointer<codex_agent_string_view> {
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

private fun MemScope.mutableTransportView(value: String): TransportMutableStringView {
    val encoded = value.encodeToByteArray()
    require(encoded.isNotEmpty())
    val bytes = allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    return TransportMutableStringView(
        alloc<codex_agent_string_view>().also {
            it.data = bytes
            it.size = encoded.size.toULong()
        }.ptr,
        bytes,
    )
}

private fun MemScope.absentTransportView(): CPointer<codex_agent_string_view> = transportView("")

private fun MemScope.invalidTransportUtf8View(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3U
    bytes[1] = 0x28U
    return alloc<codex_agent_string_view>().also {
        it.data = bytes
        it.size = 2UL
    }.ptr
}

private fun MemScope.transportStringArray(
    vararg values: CPointer<codex_agent_string_view>,
): CPointer<codex_agent_string_view> = allocArray<codex_agent_string_view>(values.size).also { array ->
    values.forEachIndexed { index, value -> setTransportString(array, index, value) }
}

private fun setTransportString(
    array: CPointer<codex_agent_string_view>,
    index: Int,
    value: CPointer<codex_agent_string_view>,
) {
    array[index].data = value.pointed.data
    array[index].size = value.pointed.size
}

private fun MemScope.transportHandleArray(vararg values: COpaquePointer?): CPointer<COpaquePointerVar> =
    allocArray<COpaquePointerVar>(values.size).also { array ->
        values.forEachIndexed { index, value -> array[index] = value }
    }

private fun MemScope.assertTransportString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: TransportStringCopy,
) {
    val expectedBytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(context, handle, null, 0UL, required.ptr))
    assertEquals(expectedBytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(expectedBytes.size.coerceAtLeast(1))
    assertEquals(CODEX_AGENT_STATUS_OK, copy(context, handle, buffer, expectedBytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(expectedBytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertTransportStringAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    copy: TransportStringCopyAt,
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

private fun MemScope.assertTransportAbsentString(
    context: COpaquePointer,
    handle: COpaquePointer,
    copy: TransportStringCopy,
) {
    val required = alloc<ULongVar>().also { it.value = 89UL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, copy(context, handle, null, 0UL, required.ptr))
    assertEquals(89UL, required.value)
}

private fun MemScope.assertTransportInt(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: TransportIntGetter,
) {
    val actual = alloc<IntVar>().also { it.value = Int.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, actual.ptr))
    assertEquals(expected, actual.value)
}

private fun MemScope.assertTransportCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    getter: TransportCountGetter,
) {
    val actual = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, actual.ptr))
    assertEquals(expected, actual.value)
}

private fun MemScope.assertTransportAbsentCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    getter: TransportCountGetter,
) {
    val actual = alloc<ULongVar>().also { it.value = 97UL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, getter(context, handle, actual.ptr))
    assertEquals(97UL, actual.value)
}
