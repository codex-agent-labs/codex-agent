@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package io.github.codex_agent_labs.codexagent.capi

import io.github.codex_agent_labs.codexagent.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
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
import kotlinx.cinterop.set
import kotlinx.cinterop.value

class CodexAgentCResourceValuesTest {
    @Test
    fun pluginReferenceProjectsEveryPropertyAndNullableState() = memScoped {
        val contextSlot = createContext()
        val context = assertNotNull(contextSlot.value)
        val referenceSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val absentSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            val id = mutableStringView("plugin-id")
            val name = stringView("tools")
            val marketplace = stringView("official")
            val marketplacePath = stringView("/market/tools")
            val remotePluginId = stringView("remote-id")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceCreate(
                    context,
                    id.value,
                    name,
                    marketplace,
                    1,
                    marketplacePath,
                    1,
                    remotePluginId,
                    referenceSlot.ptr,
                ),
            )
            val reference = assertNotNull(referenceSlot.value)

            id.bytes[0] = 'X'.code.toUByte()
            assertHandleString(context, reference, "plugin-id", ::codexAgentPluginReferenceIdCopy)
            assertHandleString(context, reference, "tools", ::codexAgentPluginReferenceNameCopy)
            assertHandleString(
                context,
                reference,
                "official",
                ::codexAgentPluginReferenceMarketplaceNameCopy,
            )
            assertPresence(context, reference, 1, ::codexAgentPluginReferenceHasMarketplacePath)
            assertHandleString(
                context,
                reference,
                "/market/tools",
                ::codexAgentPluginReferenceMarketplacePathCopy,
            )
            assertPresence(context, reference, 1, ::codexAgentPluginReferenceHasRemotePluginId)
            assertHandleString(
                context,
                reference,
                "remote-id",
                ::codexAgentPluginReferenceRemotePluginIdCopy,
            )
            assertHandleString(
                context,
                reference,
                "plugin://tools@official",
                ::codexAgentPluginReferenceUriCopy,
            )

            val empty = stringView("")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("minimal-id"),
                    stringView("minimal"),
                    stringView("local"),
                    0,
                    empty,
                    0,
                    empty,
                    absentSlot.ptr,
                ),
            )
            val absent = assertNotNull(absentSlot.value)
            assertPresence(context, absent, 0, ::codexAgentPluginReferenceHasMarketplacePath)
            assertAbsentHandleString(context, absent, ::codexAgentPluginReferenceMarketplacePathCopy)
            assertPresence(context, absent, 0, ::codexAgentPluginReferenceHasRemotePluginId)
            assertAbsentHandleString(context, absent, ::codexAgentPluginReferenceRemotePluginIdCopy)
            assertHandleString(
                context,
                absent,
                "plugin://minimal@local",
                ::codexAgentPluginReferenceUriCopy,
            )

            val invalidSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    invalidUtf8View(),
                    stringView("name"),
                    stringView("market"),
                    0,
                    empty,
                    0,
                    empty,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    1,
                    invalidUtf8View(),
                    0,
                    empty,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    2,
                    empty,
                    0,
                    empty,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    0,
                    empty,
                    2,
                    empty,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    0,
                    stringView("must-be-absent"),
                    0,
                    empty,
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    context,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    0,
                    empty,
                    0,
                    stringView("must-be-absent"),
                    invalidSlot.ptr,
                ),
            )
            assertNull(invalidSlot.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, absentSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, absentSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginReferenceDestroy(context, referenceSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun pluginSkillServiceTierAndSkillChunkProjectExactValues() = memScoped {
        val contextSlot = createContext()
        val context = assertNotNull(contextSlot.value)
        val skillSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val absentSkillSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val tierSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val chunkSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val absentChunkSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            val skillName = mutableStringView("review")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSkillCreate(
                    context,
                    skillName.value,
                    stringView("Review changes"),
                    1,
                    1,
                    stringView("/skills/review.md"),
                    skillSlot.ptr,
                ),
            )
            val skill = assertNotNull(skillSlot.value)
            skillName.bytes[0] = 'X'.code.toUByte()
            assertHandleString(context, skill, "review", ::codexAgentPluginSkillNameCopy)
            assertHandleString(context, skill, "Review changes", ::codexAgentPluginSkillDescriptionCopy)
            assertPresence(context, skill, 1, ::codexAgentPluginSkillIsEnabled)
            assertPresence(context, skill, 1, ::codexAgentPluginSkillHasPath)
            assertHandleString(context, skill, "/skills/review.md", ::codexAgentPluginSkillPathCopy)

            val empty = stringView("")
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSkillCreate(
                    context,
                    stringView("disabled"),
                    stringView("Disabled skill"),
                    0,
                    0,
                    empty,
                    absentSkillSlot.ptr,
                ),
            )
            val absentSkill = assertNotNull(absentSkillSlot.value)
            assertPresence(context, absentSkill, 0, ::codexAgentPluginSkillIsEnabled)
            assertPresence(context, absentSkill, 0, ::codexAgentPluginSkillHasPath)
            assertAbsentHandleString(context, absentSkill, ::codexAgentPluginSkillPathCopy)

            val invalidSkill = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginSkillCreate(
                    context,
                    invalidUtf8View(),
                    stringView("invalid"),
                    1,
                    0,
                    empty,
                    invalidSkill.ptr,
                ),
            )
            assertNull(invalidSkill.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginSkillCreate(
                    context,
                    stringView("invalid"),
                    stringView("invalid"),
                    2,
                    0,
                    empty,
                    invalidSkill.ptr,
                ),
            )
            assertNull(invalidSkill.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginSkillCreate(
                    context,
                    stringView("invalid"),
                    stringView("invalid"),
                    1,
                    2,
                    empty,
                    invalidSkill.ptr,
                ),
            )
            assertNull(invalidSkill.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginSkillCreate(
                    context,
                    stringView("invalid"),
                    stringView("invalid"),
                    1,
                    0,
                    stringView("must-be-absent"),
                    invalidSkill.ptr,
                ),
            )
            assertNull(invalidSkill.value)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentServiceTierCreate(
                    context,
                    stringView("fast"),
                    stringView("Fast"),
                    stringView("Lower latency"),
                    tierSlot.ptr,
                ),
            )
            val tier = assertNotNull(tierSlot.value)
            assertHandleString(context, tier, "fast", ::codexAgentServiceTierIdCopy)
            assertHandleString(context, tier, "Fast", ::codexAgentServiceTierNameCopy)
            assertHandleString(context, tier, "Lower latency", ::codexAgentServiceTierDescriptionCopy)
            val invalidTier = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentServiceTierCreate(
                    context,
                    invalidUtf8View(),
                    stringView("Invalid"),
                    stringView("Invalid UTF-8"),
                    invalidTier.ptr,
                ),
            )
            assertNull(invalidTier.value)

            val nextOffset = Long.MIN_VALUE + 17L
            val totalBytes = Long.MAX_VALUE - 19L
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillChunkCreate(
                    context,
                    stringView("chunk-content"),
                    1,
                    nextOffset,
                    totalBytes,
                    chunkSlot.ptr,
                ),
            )
            val chunk = assertNotNull(chunkSlot.value)
            assertHandleString(context, chunk, "chunk-content", ::codexAgentSkillChunkContentCopy)
            assertChunkOffsets(context, chunk, 1, nextOffset, totalBytes)

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentSkillChunkCreate(
                    context,
                    stringView("last"),
                    0,
                    0L,
                    -1L,
                    absentChunkSlot.ptr,
                ),
            )
            assertChunkOffsets(context, assertNotNull(absentChunkSlot.value), 0, 0L, -1L)

            val invalidChunk = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillChunkCreate(
                    context,
                    invalidUtf8View(),
                    0,
                    0L,
                    0L,
                    invalidChunk.ptr,
                ),
            )
            assertNull(invalidChunk.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillChunkCreate(
                    context,
                    stringView("invalid"),
                    2,
                    0L,
                    0L,
                    invalidChunk.ptr,
                ),
            )
            assertNull(invalidChunk.value)
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentSkillChunkCreate(
                    context,
                    stringView("invalid"),
                    0,
                    1L,
                    0L,
                    invalidChunk.ptr,
                ),
            )
            assertNull(invalidChunk.value)
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillChunkDestroy(context, absentChunkSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillChunkDestroy(context, absentChunkSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillChunkDestroy(context, chunkSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSkillChunkDestroy(context, chunkSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, tierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentServiceTierDestroy(context, tierSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, absentSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, absentSkillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, skillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(context, skillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        }
    }

    @Test
    fun capabilityAndSkillScopeEntriesProjectCanonicalLabels() = memScoped {
        assertEnumString(0, "web_search", ::codexAgentCapabilityIdCopy)
        assertEnumString(0, "Web search", ::codexAgentCapabilityDisplayLabelCopy)
        val hasIcon = alloc<IntVar>()
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentCapabilityHasIcon(0, hasIcon.ptr))
        assertEquals(1, hasIcon.value)
        assertEnumString(0, "🌐", ::codexAgentCapabilityIconCopy)
        assertEnumString(0, "Use 🌐 Web search", ::codexAgentCapabilityPromptLabelCopy)

        listOf(
            0 to "Built in",
            1 to "User",
            2 to "Workspace",
            3 to "Plugin",
            4 to "Managed",
        ).forEach { (entry, label) ->
            assertEnumString(entry, label, ::codexAgentSkillScopeDisplayNameCopy)
        }

        val required = alloc<ULongVar>()
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentCapabilityIdCopy(1, null, 0UL, required.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentCapabilityHasIcon(-1, hasIcon.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentSkillScopeDisplayNameCopy(5, null, 0UL, required.ptr),
        )
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentCapabilityHasIcon(0, null),
        )
    }

    @Test
    fun resourceValuesEnforceContextPayloadOutputAndDestructionSemantics() = memScoped {
        val firstContextSlot = createContext()
        val secondContextSlot = createContext()
        val firstContext = assertNotNull(firstContextSlot.value)
        val secondContext = assertNotNull(secondContextSlot.value)
        val referenceSlot = alloc<COpaquePointerVar>().also { it.value = null }
        val skillSlot = alloc<COpaquePointerVar>().also { it.value = null }
        try {
            val empty = stringView("")
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentPluginReferenceCreate(
                    null,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    0,
                    empty,
                    0,
                    empty,
                    referenceSlot.ptr,
                ),
            )
            assertNull(referenceSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceCreate(
                    firstContext,
                    stringView("id"),
                    stringView("name"),
                    stringView("market"),
                    0,
                    empty,
                    0,
                    empty,
                    referenceSlot.ptr,
                ),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginSkillCreate(
                    firstContext,
                    stringView("skill"),
                    stringView("description"),
                    1,
                    0,
                    empty,
                    skillSlot.ptr,
                ),
            )
            val reference = assertNotNull(referenceSlot.value)
            val skill = assertNotNull(skillSlot.value)
            val required = alloc<ULongVar>()

            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPluginReferenceIdCopy(firstContext, skill, null, 0UL, required.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentPluginReferenceIdCopy(secondContext, reference, null, 0UL, required.ptr),
            )

            val wrongDestroySlot = alloc<COpaquePointerVar>().also { it.value = skill }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE,
                codexAgentPluginReferenceDestroy(firstContext, wrongDestroySlot.ptr),
            )
            assertEquals(skill, wrongDestroySlot.value)

            val occupiedOutput = alloc<COpaquePointerVar>().also { it.value = reference }
            assertEquals(
                CODEX_AGENT_STATUS_INVALID_ARGUMENT,
                codexAgentServiceTierCreate(
                    firstContext,
                    stringView("id"),
                    stringView("name"),
                    stringView("description"),
                    occupiedOutput.ptr,
                ),
            )
            assertEquals(reference, occupiedOutput.value)

            val aliasSlot = alloc<COpaquePointerVar>().also { it.value = reference }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceDestroy(firstContext, referenceSlot.ptr),
            )
            assertNull(referenceSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentPluginReferenceDestroy(firstContext, referenceSlot.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentPluginReferenceDestroy(firstContext, aliasSlot.ptr),
            )
            assertEquals(reference, aliasSlot.value)

            val reclaimedSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentServiceTierCreate(
                    secondContext,
                    stringView("reclaimed"),
                    stringView("Reclaimed"),
                    stringView("Owned by context"),
                    reclaimedSlot.ptr,
                ),
            )
            val reclaimed = assertNotNull(reclaimedSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertNull(secondContextSlot.value)
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentServiceTierIdCopy(secondContext, reclaimed, null, 0UL, required.ptr),
            )
        } finally {
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentPluginSkillDestroy(firstContext, skillSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(firstContextSlot.ptr))
        }
    }
}

private fun MemScope.createContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.stringView(value: String): CPointer<codex_agent_string_view> =
    alloc<codex_agent_string_view>().also { view ->
        val bytes = value.encodeToByteArray()
        view.size = bytes.size.toULong()
        view.data = if (bytes.isEmpty()) {
            null
        } else {
            allocArray<UByteVar>(bytes.size).also { buffer ->
                bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
            }
        }
    }.ptr

private fun MemScope.mutableStringView(value: String): MutableStringView {
    val bytes = value.encodeToByteArray()
    require(bytes.isNotEmpty())
    val buffer = allocArray<UByteVar>(bytes.size)
    bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    return MutableStringView(
        value = alloc<codex_agent_string_view>().also { view ->
            view.data = buffer
            view.size = bytes.size.toULong()
        }.ptr,
        bytes = buffer,
    )
}

private fun MemScope.invalidUtf8View(): CPointer<codex_agent_string_view> {
    val bytes = allocArray<UByteVar>(2)
    bytes[0] = 0xc3u
    bytes[1] = 0x28u
    return alloc<codex_agent_string_view>().also { view ->
        view.data = bytes
        view.size = 2uL
    }.ptr
}

private fun MemScope.assertHandleString(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: String,
    copy: HandleStringCopy,
) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(
        if (bytes.isEmpty()) CODEX_AGENT_STATUS_OK else CODEX_AGENT_STATUS_BUFFER_TOO_SMALL,
        copy(context, handle, null, 0UL, required.ptr),
    )
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size.coerceAtLeast(1))
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        copy(context, handle, buffer, bytes.size.toULong(), required.ptr),
    )
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private fun MemScope.assertAbsentHandleString(
    context: COpaquePointer,
    handle: COpaquePointer,
    copy: HandleStringCopy,
) {
    val required = alloc<ULongVar>().also { it.value = 73UL }
    assertEquals(CODEX_AGENT_STATUS_NOT_READY, copy(context, handle, null, 0UL, required.ptr))
    assertEquals(73UL, required.value)
}

private fun MemScope.assertPresence(
    context: COpaquePointer,
    handle: COpaquePointer,
    expected: Int,
    getter: PresenceGetter,
) {
    val actual = alloc<IntVar>()
    assertEquals(CODEX_AGENT_STATUS_OK, getter(context, handle, actual.ptr))
    assertEquals(expected, actual.value)
}

private fun MemScope.assertChunkOffsets(
    context: COpaquePointer,
    chunk: COpaquePointer,
    expectedHasNextOffset: Int,
    expectedNextOffset: Long,
    expectedTotalBytes: Long,
) {
    val hasNextOffset = alloc<IntVar>()
    val nextOffset = alloc<LongVar>()
    val totalBytes = alloc<LongVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentSkillChunkNextOffset(context, chunk, hasNextOffset.ptr, nextOffset.ptr),
    )
    assertEquals(expectedHasNextOffset, hasNextOffset.value)
    assertEquals(expectedNextOffset, nextOffset.value)
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentSkillChunkTotalBytes(context, chunk, totalBytes.ptr),
    )
    assertEquals(expectedTotalBytes, totalBytes.value)
}

private fun MemScope.assertEnumString(entry: Int, expected: String, copy: EnumStringCopy) {
    val bytes = expected.encodeToByteArray()
    val required = alloc<ULongVar>()
    assertEquals(CODEX_AGENT_STATUS_BUFFER_TOO_SMALL, copy(entry, null, 0UL, required.ptr))
    assertEquals(bytes.size.toULong(), required.value)
    val buffer = allocArray<UByteVar>(bytes.size)
    assertEquals(CODEX_AGENT_STATUS_OK, copy(entry, buffer, bytes.size.toULong(), required.ptr))
    assertEquals(expected, ByteArray(bytes.size) { buffer[it].toByte() }.decodeToString())
}

private typealias HandleStringCopy = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private typealias PresenceGetter = (
    COpaquePointer?,
    COpaquePointer?,
    CPointer<IntVar>?,
) -> Int

private typealias EnumStringCopy = (
    Int,
    CPointer<UByteVar>?,
    ULong,
    CPointer<ULongVar>?,
) -> Int

private data class MutableStringView(
    val value: CPointer<codex_agent_string_view>,
    val bytes: CPointer<UByteVar>,
)
