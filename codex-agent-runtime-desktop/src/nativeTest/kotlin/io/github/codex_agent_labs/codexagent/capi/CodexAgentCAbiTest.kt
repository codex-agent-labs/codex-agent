@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.value

class CodexAgentCAbiTest {
    @Test
    fun reportsExactCompatibleAbiVersion() {
        val minimum = 0x01000000u
        val current = 0x010D0000u

        assertEquals(1, RUNTIME_IDENTITY_SCHEMA_VERSION)
        assertEquals(current, codexAgentAbiVersion())
        assertEquals(1, codexAgentAbiIsCompatible(minimum))
        assertEquals(1, codexAgentAbiIsCompatible(current))
        assertEquals(1, codexAgentAbiIsCompatible(current - 1u))
        assertEquals(0, codexAgentAbiIsCompatible(minimum - 1u))
        assertEquals(0, codexAgentAbiIsCompatible(current + 1u))
        assertEquals(0, codexAgentAbiIsCompatible(0x02000000u))
    }

    @Test
    fun runtimeIdentityUsesCallerBufferAndCanonicalNulTerminatedJson() = memScoped {
        val sentinel = alloc<UByteVar>()
        sentinel.value = 0x5au.toUByte()
        assertEquals(CODEX_AGENT_STATUS_INVALID_ARGUMENT, codexAgentRuntimeIdentity(sentinel.ptr, null))
        assertEquals(0x5au.toUByte(), sentinel.value)

        val size = alloc<ULongVar>()
        size.value = 0uL
        assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, codexAgentRuntimeIdentity(null, size.ptr))
        val required = GENERATED_RUNTIME_IDENTITY_JSON.encodeToByteArray().size + 1
        assertEquals(required.toULong(), size.value)

        val undersized = allocArray<UByteVar>(required - 1)
        repeat(required - 1) { undersized[it] = 0x5au.toUByte() }
        size.value = (required - 1).toULong()
        assertEquals(
            CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
            codexAgentRuntimeIdentity(undersized, size.ptr),
        )
        assertEquals(required.toULong(), size.value)
        repeat(required - 1) { assertEquals(0x5au.toUByte(), undersized[it]) }

        val buffer = allocArray<UByteVar>(required)
        repeat(required) { buffer[it] = 0x5au.toUByte() }
        size.value = required.toULong()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentRuntimeIdentity(buffer, size.ptr))
        assertEquals(required.toULong(), size.value)
        assertEquals(0u.toUByte(), buffer[required - 1])
        val json = ByteArray(required - 1) { buffer[it].toByte() }.decodeToString()
        assertEquals(GENERATED_RUNTIME_IDENTITY_JSON, json)
        assertTrue(json.none { it.isWhitespace() })
        assertEquals(
            listOf(
                "appServerVersion",
                "buildInputDigest",
                "cAbiVersion",
                "componentId",
                "contractComponentDigest",
                "contractDigest",
                "runtimeCompatibilityVersion",
                "schemaVersion",
                "target",
            ),
            Regex("\\\"([A-Za-z]+)\\\":").findAll(json).map { it.groupValues[1] }.toList(),
        )

        repeat(required) { buffer[it] = 0x5au.toUByte() }
        size.value = required.toULong()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentRuntimeIdentity(buffer, size.ptr))
        assertEquals(0u.toUByte(), buffer[required - 1])
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
