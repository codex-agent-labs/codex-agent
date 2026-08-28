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
import kotlinx.cinterop.LongVar
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

class CodexAgentCHookCatalogValuesTest {
    @Test
    fun projectsEveryHookFieldHandlerTrustAndOriginExactly(): Unit = withHookContexts { context, _ ->
        val handlers = (0..3).map { createHandlerCarrier(context, it) }
        val cases = listOf(
            HookCase(handlers[0], 0, 0, "USER", null, 0, 0, 0),
            HookCase(handlers[1], 1, 1, "PROJECT", null, 0, 0, 1, matcher = ""),
            HookCase(handlers[2], 2, 2, "OTHER", "", 0, 0, 2, pluginId = ""),
            HookCase(handlers[3], 3, 3, "SYSTEM", null, 1, 0, 3, statusMessage = ""),
            HookCase(handlers[0], 0, 0, "OTHER", null, 0, 0, 4),
            HookCase(handlers[1], 1, 2, "PLUGIN", "plugin", 0, 1, 0),
        )

        cases.forEachIndexed { index, case ->
            val hook = createHook(context, index, case)
            assertHook(context, hook, index, case)
            val child = emptyHookSlot()
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandler(context, hook, child.ptr))
            val childHandle = assertNotNull(child.value)
            val kind = alloc<IntVar>().also { it.value = -1 }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerKind(context, childHandle, kind.ptr))
            assertEquals(case.handlerKind, kind.value)
            assertWrongHandlerProjection(context, childHandle, case.handlerKind)
            val hookSlot = pointerSlot(hook)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, hookSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, hookSlot.ptr))
            projectAndAssertHandler(context, childHandle, case.handlerKind)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerDestroy(context, child.ptr))
        }

        handlers.forEach { handler ->
            val slot = pointerSlot(handler)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerDestroy(context, slot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerDestroy(context, slot.ptr))
        }
    }

    @Test
    fun projectsOrderedDuplicateCatalogAndFreshChildrenExactly(): Unit = withHookContexts { context, _ ->
        val handler = createHandlerCarrier(context, 1)
        val first = createHook(context, 10, HookCase(handler, 1, 1, "PROJECT", null, 0, 0, 1))
        val second = createHook(context, 11, HookCase(handler, 1, 2, "USER", null, 0, 0, 0))
        val hooks = allocArray<COpaquePointerVar>(3)
        hooks[0] = first
        hooks[1] = second
        hooks[2] = first
        val warnings = stringViews(listOf("warning", "warning", ""))
        val errors = stringViews(listOf("error", "error"))
        val catalogSlot = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookCatalogCreate(context, hooks, 3uL, warnings.views, 3uL, errors.views, 2uL, catalogSlot.ptr),
        )
        warnings.items.forEach { if (it.bytes != null) it.bytes[0] = 'X'.code.toUByte() }
        errors.items.forEach { if (it.bytes != null) it.bytes[0] = 'X'.code.toUByte() }
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, pointerSlot(first).ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, pointerSlot(second).ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerDestroy(context, pointerSlot(handler).ptr))

        val catalog = assertNotNull(catalogSlot.value)
        assertCount(context, catalog, 3uL, ::codexAgentHookCatalogHooksCount)
        assertCount(context, catalog, 3uL, ::codexAgentHookCatalogWarningsCount)
        assertCount(context, catalog, 2uL, ::codexAgentHookCatalogErrorsCount)
        listOf("warning", "warning", "").forEachIndexed { index, value ->
            assertCopiedAt(context, catalog, index.toULong(), value, ::codexAgentHookCatalogWarningsCopyAt)
        }
        listOf("error", "error").forEachIndexed { index, value ->
            assertCopiedAt(context, catalog, index.toULong(), value, ::codexAgentHookCatalogErrorsCopyAt)
        }

        val firstChild = emptyHookSlot()
        val middleChild = emptyHookSlot()
        val duplicateChild = emptyHookSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogHooksAt(context, catalog, 0uL, firstChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogHooksAt(context, catalog, 1uL, middleChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogHooksAt(context, catalog, 2uL, duplicateChild.ptr))
        assertNotEquals(firstChild.value, duplicateChild.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogDestroy(context, catalogSlot.ptr))
        assertCopied(context, assertNotNull(firstChild.value), "key-10", ::codexAgentHookKeyCopy)
        assertCopied(context, assertNotNull(middleChild.value), "key-11", ::codexAgentHookKeyCopy)
        assertCopied(context, assertNotNull(duplicateChild.value), "key-10", ::codexAgentHookKeyCopy)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, firstChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, middleChild.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, duplicateChild.ptr))
    }

    @Test
    fun rejectsInvalidHookCatalogInputsAndHandleMisuseExactly(): Unit = withHookContexts { context, other ->
        val concrete = emptyHookSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentAcquire(context, concrete.ptr))
        val handlerSlot = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookHandlerFromAgent(context, concrete.value, handlerSlot.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentDestroy(context, concrete.ptr))
        val handler = assertNotNull(handlerSlot.value)
        val empty = utf8View("")

        listOf(-1, 2).forEach { invalidFlag ->
            val output = emptyHookSlot()
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentHookCreate(
                    context, utf8View("key").view, utf8View("hash").view, invalidFlag,
                    utf8View("event").view, handler, 0, utf8View("USER").view,
                    utf8View("path").view, 1, 0, 0, empty.view, 0, empty.view,
                    0, empty.view, 0, 0, 0, output.ptr,
                ),
            )
            assertNull(output.value)
        }
        listOf(
            intArrayOf(1, -1, 0, 0, 0, 0),
            intArrayOf(1, 2, 0, 0, 0, 0),
            intArrayOf(1, 0, -1, 0, 0, 0),
            intArrayOf(1, 0, 2, 0, 0, 0),
            intArrayOf(1, 0, 0, -1, 0, 0),
            intArrayOf(1, 0, 0, 2, 0, 0),
            intArrayOf(1, 0, 0, 0, -1, 0),
            intArrayOf(1, 0, 0, 0, 2, 0),
            intArrayOf(1, 0, 0, 0, 0, -1),
            intArrayOf(1, 0, 0, 0, 0, 2),
        ).forEach { flags ->
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                createFlaggedHook(context, handler, flags),
            )
        }
        listOf(-1, 4).forEach { invalidTrust ->
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, createInvalidHook(context, handler, invalidTrust, 0, 0))
        }
        listOf(-1, 5).forEach { invalidOrigin ->
            assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, createInvalidHook(context, handler, 0, 1, invalidOrigin))
        }
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, createInvalidHook(context, handler, 0, 0, 1))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, createInvalidHook(context, handler, 0, 2, 0))

        val invalidUtf8 = invalidUtf8View()
        val invalidOutput = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookCreate(
                context, invalidUtf8, utf8View("hash").view, 1, utf8View("event").view,
                handler, 0, utf8View("USER").view, utf8View("path").view, 1, 0,
                0, empty.view, 0, empty.view, 0, empty.view, 0, 0, 0, invalidOutput.ptr,
            ),
        )
        assertNull(invalidOutput.value)

        val hook = createHook(context, 20, HookCase(handler, 0, 0, "USER", null, 0, 0, 0))
        val required = alloc<ULongVar>().also { it.value = 91uL }
        val flag = alloc<IntVar>().also { it.value = 93 }
        assertEquals(
            CODEX_AGENT_STATUS_WRONG_CONTEXT,
            codexAgentHookKeyCopy(other, hook, null, 0uL, required.ptr),
        )
        assertEquals(91uL, required.value)
        assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, codexAgentHookHandlerKind(context, hook, flag.ptr))
        assertEquals(93, flag.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookTimeoutSeconds(context, hook, null))

        val occupied = pointerSlot(context)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookHandler(context, hook, occupied.ptr))
        assertEquals(context, occupied.value)
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentHookCatalogHooksAt(context, hook, 0uL, occupied.ptr))
        assertEquals(context, occupied.value)

        val wrongSlot = pointerSlot(hook)
        assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, codexAgentHookHandlerDestroy(context, wrongSlot.ptr))
        assertEquals(hook, wrongSlot.value)
        val stale = hook
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, wrongSlot.ptr))
        assertNull(wrongSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookDestroy(context, wrongSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentHookKeyCopy(context, stale, null, 0uL, required.ptr))
        assertEquals(91uL, required.value)

        val catalogSlot = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookCatalogCreate(context, null, 1uL, null, 0uL, null, 0uL, catalogSlot.ptr),
        )
        val malformedWarnings = allocArray<codex_agent_string_view>(1)
        malformedWarnings[0].data = invalidUtf8.pointed.data
        malformedWarnings[0].size = invalidUtf8.pointed.size
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookCatalogCreate(
                context, null, 0uL, malformedWarnings, 1uL, null, 0uL, catalogSlot.ptr,
            ),
        )
        assertNull(catalogSlot.value)

        val emptyCatalog = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookCatalogCreate(context, null, 0uL, null, 0uL, null, 0uL, emptyCatalog.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookCatalogWarningsCopyAt(context, emptyCatalog.value, 0uL, null, 0uL, required.ptr),
        )
        val child = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHookCatalogHooksAt(context, emptyCatalog.value, 0uL, child.ptr),
        )
        assertNull(child.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogDestroy(context, emptyCatalog.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerDestroy(context, handlerSlot.ptr))
    }

    @Test
    fun reclaimsHookCatalogSnapshotsAndDestroyIsIdempotent(): Unit = memScoped {
        val contextSlot = emptyHookSlot()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
        val context = assertNotNull(contextSlot.value)
        val handler = createHandlerCarrier(context, 3)
        val hook = createHook(context, 30, HookCase(handler, 3, 3, "SYSTEM", null, 1, 0, 3))
        val hooks = allocArray<COpaquePointerVar>(1).also { it[0] = hook }
        val catalog = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookCatalogCreate(context, hooks, 1uL, null, 0uL, null, 0uL, catalog.ptr),
        )
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogDestroy(context, catalog.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookCatalogDestroy(context, catalog.ptr))

        val liveCatalog = emptyHookSlot()
        assertEquals(
            CODEX_AGENT_STATUS_OK,
            codexAgentHookCatalogCreate(context, hooks, 1uL, null, 0uL, null, 0uL, liveCatalog.ptr),
        )
        val liveCatalogHandle = assertNotNull(liveCatalog.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)

        val kind = alloc<IntVar>().also { it.value = 71 }
        assertEquals(CODEX_AGENT_STATUS_STALE_HANDLE, codexAgentHookHandlerKind(context, handler, kind.ptr))
        assertEquals(71, kind.value)
        val required = alloc<ULongVar>().also { it.value = 73uL }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentHookKeyCopy(context, hook, null, 0uL, required.ptr),
        )
        assertEquals(73uL, required.value)
        val count = alloc<ULongVar>().also { it.value = 79uL }
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentHookCatalogHooksCount(context, liveCatalogHandle, count.ptr),
        )
        assertEquals(79uL, count.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentHookCatalogDestroy(context, liveCatalog.ptr),
        )
        assertEquals(liveCatalogHandle, liveCatalog.value)
    }
}

private data class HookCase(
    val handler: COpaquePointer,
    val handlerKind: Int,
    val trustStatus: Int,
    val source: String,
    val pluginForOrigin: String?,
    val isManaged: Int,
    val hasOrigin: Int,
    val expectedOrigin: Int,
    val matcher: String? = null,
    val pluginId: String? = pluginForOrigin,
    val statusMessage: String? = null,
)

private data class HookTestView(
    val view: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>?,
)

private data class HookTestViews(
    val views: CPointer<codex_agent_string_view>?,
    val items: List<HookTestView>,
)

private typealias HookCopy = (
    COpaquePointer?, COpaquePointer?, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias HookCopyAt = (
    COpaquePointer?, COpaquePointer?, ULong, CPointer<UByteVar>?, ULong, CPointer<ULongVar>?,
) -> Int

private typealias HookCount = (COpaquePointer?, COpaquePointer?, CPointer<ULongVar>?) -> Int

private fun withHookContexts(block: MemScope.(COpaquePointer, COpaquePointer) -> Unit): Unit = memScoped {
    val contextSlot = emptyHookSlot()
    val otherSlot = emptyHookSlot()
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(contextSlot.ptr))
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(otherSlot.ptr))
    try {
        block(assertNotNull(contextSlot.value), assertNotNull(otherSlot.value))
    } finally {
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(otherSlot.ptr))
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
    }
}

private fun MemScope.createHandlerCarrier(context: COpaquePointer, kind: Int): COpaquePointer {
    val concrete = emptyHookSlot()
    val carrier = emptyHookSlot()
    when (kind) {
        0 -> {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentAcquire(context, concrete.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerFromAgent(context, concrete.value, carrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentDestroy(context, concrete.ptr))
        }
        1 -> {
            val command = utf8View("command")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHookHandlerCommandCreate(context, command.view, 1, concrete.ptr),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerFromCommand(context, concrete.value, carrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerCommandDestroy(context, concrete.ptr))
        }
        2 -> {
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHookHandlerMcpToolCreate(
                    context, utf8View("server").view, utf8View("tool").view, concrete.ptr,
                ),
            )
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerFromMcpTool(context, concrete.value, carrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerMcpToolDestroy(context, concrete.ptr))
        }
        3 -> {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptAcquire(context, concrete.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerFromPrompt(context, concrete.value, carrier.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptDestroy(context, concrete.ptr))
        }
        else -> error("Unknown handler test kind")
    }
    return assertNotNull(carrier.value)
}

private fun MemScope.createHook(context: COpaquePointer, index: Int, case: HookCase): COpaquePointer {
    val key = utf8View("key-$index")
    val hash = utf8View("hash-$index")
    val event = utf8View("event-$index")
    val source = utf8View(case.source)
    val path = utf8View("path-$index")
    val matcher = optionalView(case.matcher)
    val plugin = optionalView(case.pluginId)
    val status = optionalView(case.statusMessage)
    val output = emptyHookSlot()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHookCreate(
            context, key.view, hash.view, index and 1, event.view, case.handler,
            case.isManaged, source.view, path.view, 100L + index, case.trustStatus,
            if (case.matcher == null) 0 else 1, matcher.view,
            if (case.pluginId == null) 0 else 1, plugin.view,
            if (case.statusMessage == null) 0 else 1, status.view,
            case.hasOrigin, if (case.hasOrigin == 1) case.expectedOrigin else 0,
            (index + 1) and 1, output.ptr,
        ),
    )
    listOf(key, hash, event, source, path, matcher, plugin, status).forEach {
        if (it.bytes != null && it.view.pointed.size > 0uL) it.bytes[0] = 'X'.code.toUByte()
    }
    return assertNotNull(output.value)
}

private fun MemScope.assertHook(context: COpaquePointer, hook: COpaquePointer, index: Int, case: HookCase) {
    assertCopied(context, hook, "key-$index", ::codexAgentHookKeyCopy)
    assertCopied(context, hook, "hash-$index", ::codexAgentHookCurrentHashCopy)
    assertCopied(context, hook, "event-$index", ::codexAgentHookEventNameCopy)
    assertCopied(context, hook, case.source, ::codexAgentHookSourceCopy)
    assertCopied(context, hook, "path-$index", ::codexAgentHookSourcePathCopy)
    assertFlag(context, hook, index and 1, ::codexAgentHookIsEnabled)
    assertFlag(context, hook, case.isManaged, ::codexAgentHookIsManaged)
    assertFlag(context, hook, (index + 1) and 1, ::codexAgentHookCanUninstall)
    assertFlag(context, hook, if (case.trustStatus == 1 || case.trustStatus == 3) 1 else 0, ::codexAgentHookCanTrust)
    val timeout = alloc<LongVar>().also { it.value = Long.MIN_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookTimeoutSeconds(context, hook, timeout.ptr))
    assertEquals(100L + index, timeout.value)
    val trust = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookTrustStatus(context, hook, trust.ptr))
    assertEquals(case.trustStatus, trust.value)
    val origin = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookOrigin(context, hook, origin.ptr))
    assertEquals(case.expectedOrigin, origin.value)
    assertOptional(context, hook, case.matcher, ::codexAgentHookHasMatcher, ::codexAgentHookMatcherCopy)
    assertOptional(context, hook, case.pluginId, ::codexAgentHookHasPluginId, ::codexAgentHookPluginIdCopy)
    assertOptional(
        context, hook, case.statusMessage,
        ::codexAgentHookHasStatusMessage, ::codexAgentHookStatusMessageCopy,
    )
}

private fun MemScope.projectAndAssertHandler(context: COpaquePointer, handler: COpaquePointer, kind: Int) {
    val output = emptyHookSlot()
    val status = when (kind) {
        0 -> codexAgentHookHandlerAgent(context, handler, output.ptr)
        1 -> codexAgentHookHandlerCommand(context, handler, output.ptr)
        2 -> codexAgentHookHandlerMcpTool(context, handler, output.ptr)
        3 -> codexAgentHookHandlerPrompt(context, handler, output.ptr)
        else -> error("Unknown handler test kind")
    }
    assertEquals(CODEX_AGENT_STATUS_OK, status)
    val concrete = assertNotNull(output.value)
    when (kind) {
        0 -> assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerAgentDestroy(context, output.ptr))
        1 -> {
            assertCopied(context, concrete, "command", ::codexAgentHookHandlerCommandCommandCopy)
            assertFlag(context, concrete, 1, ::codexAgentHookHandlerCommandIsAsync)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerCommandDestroy(context, output.ptr))
        }
        2 -> {
            assertCopied(context, concrete, "server", ::codexAgentHookHandlerMcpToolServerCopy)
            assertCopied(context, concrete, "tool", ::codexAgentHookHandlerMcpToolToolCopy)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerMcpToolDestroy(context, output.ptr))
        }
        3 -> assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHookHandlerPromptDestroy(context, output.ptr))
    }
}

private fun MemScope.assertWrongHandlerProjection(
    context: COpaquePointer,
    handler: COpaquePointer,
    kind: Int,
) {
    val output = emptyHookSlot()
    val status = when ((kind + 1) % 4) {
        0 -> codexAgentHookHandlerAgent(context, handler, output.ptr)
        1 -> codexAgentHookHandlerCommand(context, handler, output.ptr)
        2 -> codexAgentHookHandlerMcpTool(context, handler, output.ptr)
        else -> codexAgentHookHandlerPrompt(context, handler, output.ptr)
    }
    assertEquals(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE, status)
    assertNull(output.value)
}

private fun MemScope.createInvalidHook(
    context: COpaquePointer,
    handler: COpaquePointer,
    trust: Int,
    hasOrigin: Int,
    origin: Int,
): Int {
    val empty = utf8View("")
    val output = emptyHookSlot()
    return codexAgentHookCreate(
        context, utf8View("key").view, utf8View("hash").view, 1,
        utf8View("event").view, handler, 0, utf8View("USER").view,
        utf8View("path").view, 1, trust, 0, empty.view, 0, empty.view,
        0, empty.view, hasOrigin, origin, 0, output.ptr,
    )
}

private fun MemScope.createFlaggedHook(
    context: COpaquePointer,
    handler: COpaquePointer,
    flags: IntArray,
): Int {
    val empty = utf8View("")
    val output = emptyHookSlot()
    return codexAgentHookCreate(
        context, utf8View("key").view, utf8View("hash").view, flags[0],
        utf8View("event").view, handler, flags[1], utf8View("USER").view,
        utf8View("path").view, 1, 0, flags[2], empty.view, flags[3], empty.view,
        flags[4], empty.view, 0, 0, flags[5], output.ptr,
    )
}

private fun MemScope.assertOptional(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String?,
    has: (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int,
    copy: HookCopy,
) {
    assertFlag(context, handle, if (expected == null) 0 else 1, has)
    if (expected == null) {
        val required = alloc<ULongVar>().also { it.value = 17uL }
        assertEquals(CODEX_AGENT_STATUS_NOT_READY, copy(context, handle, null, 0uL, required.ptr))
        assertEquals(17uL, required.value)
    } else {
        assertCopied(context, handle, expected, copy)
    }
}

private fun MemScope.assertFlag(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    function: (COpaquePointer?, COpaquePointer?, CPointer<IntVar>?) -> Int,
) {
    val output = alloc<IntVar>().also { it.value = -1 }
    assertEquals(CODEX_AGENT_STATUS_OK, function(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertCount(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: ULong,
    function: HookCount,
) {
    val output = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(CODEX_AGENT_STATUS_OK, function(context, handle, output.ptr))
    assertEquals(expected, output.value)
}

private fun MemScope.assertCopied(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    function: HookCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        function(context, handle, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val output = allocArray<UByteVar>(maxOf(1, bytes.size))
    assertEquals(CODEX_AGENT_STATUS_OK, function(context, handle, output, bytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(bytes.size) { output[it].toByte() }.decodeToString())
}

private fun MemScope.assertCopiedAt(
    context: COpaquePointer,
    handle: COpaquePointer,
    index: ULong,
    expected: String,
    function: HookCopyAt,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>().also { it.value = ULong.MAX_VALUE }
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        function(context, handle, index, null, 0uL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val output = allocArray<UByteVar>(maxOf(1, bytes.size))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        function(context, handle, index, output, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { output[it].toByte() }.decodeToString())
}

private fun MemScope.stringViews(values: List<String>): HookTestViews {
    if (values.isEmpty()) return HookTestViews(null, emptyList())
    val items = values.map { utf8View(it) }
    val views = allocArray<codex_agent_string_view>(items.size)
    items.forEachIndexed { index, item ->
        views[index].data = item.view.pointed.data
        views[index].size = item.view.pointed.size
    }
    return HookTestViews(views, items)
}

private fun MemScope.optionalView(value: String?): HookTestView = utf8View(value.orEmpty())

private fun MemScope.utf8View(value: String): HookTestView {
    val encoded = value.encodeToByteArray()
    if (encoded.isEmpty()) {
        return HookTestView(
            alloc<codex_agent_string_view>().also { it.data = null; it.size = 0uL }.ptr,
            null,
        )
    }
    val bytes = allocArray<UByteVar>(encoded.size)
    encoded.forEachIndexed { index, byte -> bytes[index] = byte.toUByte() }
    return HookTestView(
        alloc<codex_agent_string_view>().also {
            it.data = bytes
            it.size = encoded.size.toULong()
        }.ptr,
        bytes,
    )
}

private fun MemScope.invalidUtf8View(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    return alloc<codex_agent_string_view>().also { it.data = bytes; it.size = 2uL }.ptr
}

private fun MemScope.emptyHookSlot(): COpaquePointerVar = alloc<COpaquePointerVar>().also { it.value = null }

private fun MemScope.pointerSlot(value: COpaquePointer): COpaquePointerVar =
    alloc<COpaquePointerVar>().also { it.value = value }
