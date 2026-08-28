@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.AgentCapability
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginReference
import io.github.codex_agent_labs.codexmobile.agent.AgentPluginSkill
import io.github.codex_agent_labs.codexmobile.agent.AgentServiceTier
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillChunk
import io.github.codex_agent_labs.codexmobile.agent.AgentSkillScope
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.LongVar
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

internal data class CodexAgentCPluginReferenceSnapshot(
    val value: AgentPluginReference,
) : CodexAgentCSnapshot

internal data class CodexAgentCPluginSkillSnapshot(
    val value: AgentPluginSkill,
) : CodexAgentCSnapshot

internal data class CodexAgentCServiceTierSnapshot(
    val value: AgentServiceTier,
) : CodexAgentCSnapshot

internal data class CodexAgentCSkillChunkSnapshot(
    val value: AgentSkillChunk,
) : CodexAgentCSnapshot

@CName("codex_agent_plugin_reference_create")
public fun codexAgentPluginReferenceCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    name: CPointer<codex_agent_string_view>?,
    marketplaceName: CPointer<codex_agent_string_view>?,
    hasMarketplacePath: Int,
    marketplacePath: CPointer<codex_agent_string_view>?,
    hasRemotePluginId: Int,
    remotePluginId: CPointer<codex_agent_string_view>?,
    outReference: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outReference)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(hasMarketplacePath)
    requireBoolean(hasRemotePluginId)
    val value = AgentPluginReference(
        id = id.readRequiredUtf8(),
        name = name.readRequiredUtf8(),
        marketplaceName = marketplaceName.readRequiredUtf8(),
        marketplacePath = marketplacePath.readNullableUtf8(hasMarketplacePath),
        remotePluginId = remotePluginId.readNullableUtf8(hasRemotePluginId),
    )
    installOutput(
        outReference,
        createSnapshot(
            contextPointer,
            CodexAgentCPluginReferenceSnapshot(value),
        ),
    )
}

@CName("codex_agent_plugin_reference_destroy")
public fun codexAgentPluginReferenceDestroy(
    context: COpaquePointer?,
    reference: CPointer<COpaquePointerVar>?,
): Int = destroyResourceValue<CodexAgentCPluginReferenceSnapshot>(context, reference)

@CName("codex_agent_plugin_reference_id_copy")
public fun codexAgentPluginReferenceIdCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.id }

@CName("codex_agent_plugin_reference_name_copy")
public fun codexAgentPluginReferenceNameCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.name }

@CName("codex_agent_plugin_reference_marketplace_name_copy")
public fun codexAgentPluginReferenceMarketplaceNameCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.marketplaceName }

@CName("codex_agent_plugin_reference_has_marketplace_path")
public fun codexAgentPluginReferenceHasMarketplacePath(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    outHasMarketplacePath: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasMarketplacePath == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPluginReferenceSnapshot>(
        context,
        reference,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasMarketplacePath.pointed.value = if (it.value.marketplacePath == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_plugin_reference_marketplace_path_copy")
public fun codexAgentPluginReferenceMarketplacePathCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.marketplacePath }

@CName("codex_agent_plugin_reference_has_remote_plugin_id")
public fun codexAgentPluginReferenceHasRemotePluginId(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    outHasRemotePluginId: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasRemotePluginId == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPluginReferenceSnapshot>(
        context,
        reference,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasRemotePluginId.pointed.value = if (it.value.remotePluginId == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_plugin_reference_remote_plugin_id_copy")
public fun codexAgentPluginReferenceRemotePluginIdCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.remotePluginId }

@CName("codex_agent_plugin_reference_uri_copy")
public fun codexAgentPluginReferenceUriCopy(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginReference(context, reference, buffer, capacity, outRequired) { it.uri }

@CName("codex_agent_plugin_skill_create")
public fun codexAgentPluginSkillCreate(
    context: COpaquePointer?,
    name: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    isEnabled: Int,
    hasPath: Int,
    path: CPointer<codex_agent_string_view>?,
    outSkill: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outSkill)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(isEnabled)
    requireBoolean(hasPath)
    val value = AgentPluginSkill(
        name = name.readRequiredUtf8(),
        description = description.readRequiredUtf8(),
        isEnabled = isEnabled == 1,
        path = path.readNullableUtf8(hasPath),
    )
    installOutput(
        outSkill,
        createSnapshot(contextPointer, CodexAgentCPluginSkillSnapshot(value)),
    )
}

@CName("codex_agent_plugin_skill_destroy")
public fun codexAgentPluginSkillDestroy(
    context: COpaquePointer?,
    skill: CPointer<COpaquePointerVar>?,
): Int = destroyResourceValue<CodexAgentCPluginSkillSnapshot>(context, skill)

@CName("codex_agent_plugin_skill_name_copy")
public fun codexAgentPluginSkillNameCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginSkill(context, skill, buffer, capacity, outRequired) { it.name }

@CName("codex_agent_plugin_skill_description_copy")
public fun codexAgentPluginSkillDescriptionCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginSkill(context, skill, buffer, capacity, outRequired) { it.description }

@CName("codex_agent_plugin_skill_is_enabled")
public fun codexAgentPluginSkillIsEnabled(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    outIsEnabled: CPointer<IntVar>?,
): Int = abiStatus {
    if (outIsEnabled == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPluginSkillSnapshot>(
        context,
        skill,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outIsEnabled.pointed.value = if (it.value.isEnabled) 1 else 0
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_plugin_skill_has_path")
public fun codexAgentPluginSkillHasPath(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    outHasPath: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasPath == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCPluginSkillSnapshot>(
        context,
        skill,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasPath.pointed.value = if (it.value.path == null) 0 else 1
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_plugin_skill_path_copy")
public fun codexAgentPluginSkillPathCopy(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyPluginSkill(context, skill, buffer, capacity, outRequired) { it.path }

@CName("codex_agent_service_tier_create")
public fun codexAgentServiceTierCreate(
    context: COpaquePointer?,
    id: CPointer<codex_agent_string_view>?,
    name: CPointer<codex_agent_string_view>?,
    description: CPointer<codex_agent_string_view>?,
    outTier: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outTier)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = AgentServiceTier(
        id.readRequiredUtf8(),
        name.readRequiredUtf8(),
        description.readRequiredUtf8(),
    )
    installOutput(
        outTier,
        createSnapshot(contextPointer, CodexAgentCServiceTierSnapshot(value)),
    )
}

@CName("codex_agent_service_tier_destroy")
public fun codexAgentServiceTierDestroy(
    context: COpaquePointer?,
    tier: CPointer<COpaquePointerVar>?,
): Int = destroyResourceValue<CodexAgentCServiceTierSnapshot>(context, tier)

@CName("codex_agent_service_tier_id_copy")
public fun codexAgentServiceTierIdCopy(
    context: COpaquePointer?,
    tier: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyServiceTier(context, tier, buffer, capacity, outRequired) { it.id }

@CName("codex_agent_service_tier_name_copy")
public fun codexAgentServiceTierNameCopy(
    context: COpaquePointer?,
    tier: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyServiceTier(context, tier, buffer, capacity, outRequired) { it.name }

@CName("codex_agent_service_tier_description_copy")
public fun codexAgentServiceTierDescriptionCopy(
    context: COpaquePointer?,
    tier: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyServiceTier(context, tier, buffer, capacity, outRequired) { it.description }

@CName("codex_agent_skill_chunk_create")
public fun codexAgentSkillChunkCreate(
    context: COpaquePointer?,
    content: CPointer<codex_agent_string_view>?,
    hasNextOffset: Int,
    nextOffset: Long,
    totalBytes: Long,
    outChunk: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (!validEmptyOutput(outChunk)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val contextPointer = context ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    requireBoolean(hasNextOffset)
    if (hasNextOffset == 0) require(nextOffset == 0L)
    val value = AgentSkillChunk(
        content = content.readRequiredUtf8(),
        nextOffset = if (hasNextOffset == 1) nextOffset else null,
        totalBytes = totalBytes,
    )
    installOutput(
        outChunk,
        createSnapshot(contextPointer, CodexAgentCSkillChunkSnapshot(value)),
    )
}

@CName("codex_agent_skill_chunk_destroy")
public fun codexAgentSkillChunkDestroy(
    context: COpaquePointer?,
    chunk: CPointer<COpaquePointerVar>?,
): Int = destroyResourceValue<CodexAgentCSkillChunkSnapshot>(context, chunk)

@CName("codex_agent_skill_chunk_content_copy")
public fun codexAgentSkillChunkContentCopy(
    context: COpaquePointer?,
    chunk: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copySkillChunk(context, chunk, buffer, capacity, outRequired) { it.content }

@CName("codex_agent_skill_chunk_next_offset")
public fun codexAgentSkillChunkNextOffset(
    context: COpaquePointer?,
    chunk: COpaquePointer?,
    outHasNextOffset: CPointer<IntVar>?,
    outNextOffset: CPointer<LongVar>?,
): Int = abiStatus {
    if (outHasNextOffset == null || outNextOffset == null) {
        return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    withPayload<CodexAgentCSkillChunkSnapshot>(
        context,
        chunk,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outHasNextOffset.pointed.value = if (it.value.nextOffset == null) 0 else 1
        outNextOffset.pointed.value = it.value.nextOffset ?: 0L
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_skill_chunk_total_bytes")
public fun codexAgentSkillChunkTotalBytes(
    context: COpaquePointer?,
    chunk: COpaquePointer?,
    outTotalBytes: CPointer<LongVar>?,
): Int = abiStatus {
    if (outTotalBytes == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    withPayload<CodexAgentCSkillChunkSnapshot>(
        context,
        chunk,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        outTotalBytes.pointed.value = it.value.totalBytes
        CODEX_AGENT_STATUS_OK
    }
}

@CName("codex_agent_capability_id_copy")
public fun codexAgentCapabilityIdCopy(
    capability: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyCapability(capability, buffer, capacity, outRequired) { it.id }

@CName("codex_agent_capability_display_label_copy")
public fun codexAgentCapabilityDisplayLabelCopy(
    capability: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyCapability(capability, buffer, capacity, outRequired) { it.displayLabel }

@CName("codex_agent_capability_has_icon")
public fun codexAgentCapabilityHasIcon(
    capability: Int,
    outHasIcon: CPointer<IntVar>?,
): Int = abiStatus {
    if (outHasIcon == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val value = capabilityValue(capability) ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    outHasIcon.pointed.value = if (value.icon == null) 0 else 1
    CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_capability_icon_copy")
public fun codexAgentCapabilityIconCopy(
    capability: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyCapability(capability, buffer, capacity, outRequired) { it.icon }

@CName("codex_agent_capability_prompt_label_copy")
public fun codexAgentCapabilityPromptLabelCopy(
    capability: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = copyCapability(capability, buffer, capacity, outRequired) { it.promptLabel }

@CName("codex_agent_skill_scope_display_name_copy")
public fun codexAgentSkillScopeDisplayNameCopy(
    scope: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
): Int = abiStatus {
    val value = when (scope) {
        0 -> AgentSkillScope.SYSTEM
        1 -> AgentSkillScope.USER
        2 -> AgentSkillScope.REPO
        3 -> AgentSkillScope.PLUGIN
        4 -> AgentSkillScope.ADMIN
        else -> return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    copyUtf8(value.displayName, buffer, capacity, outRequired)
}

private fun requireBoolean(value: Int) {
    require(value == 0 || value == 1)
}

private fun CPointer<codex_agent_string_view>?.readRequiredUtf8(): String =
    requireNotNull(this).pointed.readUtf8()

private fun CPointer<codex_agent_string_view>?.readNullableUtf8(hasValue: Int): String? {
    val view = requireNotNull(this).pointed
    if (hasValue == 0) {
        require(view.data == null && view.size == 0uL)
        return null
    } else {
        return view.readUtf8()
    }
}

private inline fun <reified T : CodexAgentCSnapshot> destroyResourceValue(
    context: COpaquePointer?,
    slot: CPointer<COpaquePointerVar>?,
): Int = abiStatus {
    if (slot == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val handle = slot.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val validation = withPayload<T>(context, handle, CodexAgentCHandleKind.SNAPSHOT) {
        CODEX_AGENT_STATUS_OK
    }
    if (validation != CODEX_AGENT_STATUS_OK) return@abiStatus validation
    releaseHandle(context, slot, CodexAgentCHandleKind.SNAPSHOT)
}

private fun copyPluginReference(
    context: COpaquePointer?,
    reference: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (AgentPluginReference) -> String?,
): Int = abiStatus {
    withPayload<CodexAgentCPluginReferenceSnapshot>(
        context,
        reference,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = select(it.value) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun copyPluginSkill(
    context: COpaquePointer?,
    skill: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (AgentPluginSkill) -> String?,
): Int = abiStatus {
    withPayload<CodexAgentCPluginSkillSnapshot>(
        context,
        skill,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        val value = select(it.value) ?: return@withPayload CODEX_AGENT_STATUS_NOT_READY
        copyUtf8(value, buffer, capacity, outRequired)
    }
}

private fun copyServiceTier(
    context: COpaquePointer?,
    tier: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (AgentServiceTier) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCServiceTierSnapshot>(
        context,
        tier,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copyUtf8(select(it.value), buffer, capacity, outRequired)
    }
}

private fun copySkillChunk(
    context: COpaquePointer?,
    chunk: COpaquePointer?,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (AgentSkillChunk) -> String,
): Int = abiStatus {
    withPayload<CodexAgentCSkillChunkSnapshot>(
        context,
        chunk,
        CodexAgentCHandleKind.SNAPSHOT,
    ) {
        copyUtf8(select(it.value), buffer, capacity, outRequired)
    }
}

private fun copyCapability(
    capability: Int,
    buffer: CPointer<UByteVar>?,
    capacity: ULong,
    outRequired: CPointer<ULongVar>?,
    select: (AgentCapability) -> String?,
): Int = abiStatus {
    val value = capabilityValue(capability) ?: return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val selected = select(value) ?: return@abiStatus CODEX_AGENT_STATUS_NOT_READY
    copyUtf8(selected, buffer, capacity, outRequired)
}

private fun capabilityValue(capability: Int): AgentCapability? = when (capability) {
    0 -> AgentCapability.WEB_SEARCH
    else -> null
}
