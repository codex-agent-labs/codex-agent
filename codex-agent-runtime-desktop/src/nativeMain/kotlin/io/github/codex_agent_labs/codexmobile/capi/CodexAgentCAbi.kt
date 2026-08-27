@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.asStableRef
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value

private const val ABI_VERSION_CURRENT: UInt = 0x01000000u
private const val ABI_VERSION_MINIMUM_COMPATIBLE: UInt = 0x01000000u

internal const val CODEX_AGENT_STATUS_OK: Int = 0
internal const val CODEX_AGENT_STATUS_INVALID_ARGUMENT: Int = 1
internal const val CODEX_AGENT_STATUS_OUT_OF_MEMORY: Int = 2
internal const val CODEX_AGENT_STATUS_INTERNAL_ERROR: Int = 8

private class CodexAgentCContext

@CName("codex_agent_abi_version")
public fun codexAgentAbiVersion(): UInt = ABI_VERSION_CURRENT

@CName("codex_agent_abi_is_compatible")
public fun codexAgentAbiIsCompatible(requestedVersion: UInt): Int =
    if (requestedVersion in ABI_VERSION_MINIMUM_COMPATIBLE..ABI_VERSION_CURRENT) 1 else 0

@CName("codex_agent_context_create")
public fun codexAgentContextCreate(outContext: CPointer<COpaquePointerVar>?): Int = abiStatus {
    if (outContext == null || outContext.pointed.value != null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    outContext.pointed.value = StableRef.create(CodexAgentCContext()).asCPointer()
    CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_context_destroy")
public fun codexAgentContextDestroy(context: CPointer<COpaquePointerVar>?): Int = abiStatus {
    if (context == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    pointer.asStableRef<CodexAgentCContext>().dispose()
    context.pointed.value = null
    CODEX_AGENT_STATUS_OK
}

private inline fun abiStatus(block: () -> Int): Int = try {
    block()
} catch (_: OutOfMemoryError) {
    CODEX_AGENT_STATUS_OUT_OF_MEMORY
} catch (_: Throwable) {
    CODEX_AGENT_STATUS_INTERNAL_ERROR
}
