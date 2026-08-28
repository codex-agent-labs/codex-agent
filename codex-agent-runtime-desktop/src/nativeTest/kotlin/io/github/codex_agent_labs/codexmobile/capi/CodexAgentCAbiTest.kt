@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexmobile.capi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.value

class CodexAgentCAbiTest {
    @Test
    fun reportsExactCompatibleAbiVersion() {
        val minimum = 0x01000000u
        val current = 0x01050000u

        assertEquals(current, codexAgentAbiVersion())
        assertEquals(1, codexAgentAbiIsCompatible(minimum))
        assertEquals(1, codexAgentAbiIsCompatible(current))
        assertEquals(1, codexAgentAbiIsCompatible(current - 1u))
        assertEquals(0, codexAgentAbiIsCompatible(minimum - 1u))
        assertEquals(0, codexAgentAbiIsCompatible(current + 1u))
        assertEquals(0, codexAgentAbiIsCompatible(0x02000000u))
    }

    @Test
    fun contextRequiresUniqueInitiallyNullOutputSlot() = memScoped {
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentContextCreate(null))
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentContextDestroy(null))

        val slot = alloc<COpaquePointerVar>()
        val sentinel = alloc<ByteVar>().ptr
        slot.value = sentinel
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentContextCreate(slot.ptr))
        assertEquals(sentinel, slot.value)

        slot.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(slot.ptr))
        val context = assertNotNull(slot.value)
        val entry = handleRegistry.createEntry(
            context,
            CodexAgentCHandleKind.SNAPSHOT,
            "lease",
        )
        assertEquals(CODEX_AGENT_STATUS_OK, entry.status)
        val lease = handleRegistry.acquire(
            context,
            assertNotNull(entry.value),
            CodexAgentCHandleKind.SNAPSHOT,
        )
        assertEquals(CODEX_AGENT_STATUS_OK, lease.status)
        assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentContextDestroy(slot.ptr))
        assertEquals(context, slot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, assertNotNull(lease.value).close())
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(slot.ptr))
        assertEquals(null, slot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(slot.ptr))
        assertEquals(null, slot.value)
    }
}
