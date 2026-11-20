@file:OptIn(
    kotlin.experimental.ExperimentalNativeApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexagent.capi

import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.ULongVar
import kotlinx.cinterop.pointed
import kotlinx.cinterop.set
import kotlinx.cinterop.value

internal const val RUNTIME_IDENTITY_SCHEMA_VERSION: Int = GENERATED_RUNTIME_IDENTITY_SCHEMA_VERSION
private val runtimeIdentityBytes: ByteArray = GENERATED_RUNTIME_IDENTITY_JSON.encodeToByteArray()

internal const val CODEX_AGENT_STATUS_OK: Int = 0
internal const val CODEX_AGENT_STATUS_INVALID_ARGUMENT: Int = 1
internal const val CODEX_AGENT_STATUS_OUT_OF_MEMORY: Int = 2
internal const val CODEX_AGENT_STATUS_INTERNAL_ERROR: Int = 8
internal const val CODEX_AGENT_STATUS_BUFFER_TOO_SMALL: Int = 9
internal const val CODEX_AGENT_STATUS_WOULD_DEADLOCK: Int = 12
internal const val CODEX_AGENT_STATUS_NOT_READY: Int = 13
internal const val CODEX_AGENT_STATUS_OPERATION_FAILED: Int = 14

internal val handleRegistry = CodexAgentCHandleRegistry()

@CName("codex_agent_abi_version")
public fun codexAgentAbiVersion(): UInt = GENERATED_ABI_VERSION_CURRENT

@CName("codex_agent_abi_is_compatible")
public fun codexAgentAbiIsCompatible(requestedVersion: UInt): Int =
    if (requestedVersion in GENERATED_ABI_VERSION_MINIMUM_COMPATIBLE..GENERATED_ABI_VERSION_CURRENT) 1 else 0

@CName("codex_agent_runtime_identity")
public fun codexAgentRuntimeIdentity(
    buffer: CPointer<UByteVar>?,
    inoutSize: CPointer<ULongVar>?,
): Int = abiStatus {
    if (inoutSize == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val capacity = inoutSize.pointed.value
    val required = runtimeIdentityBytes.size.toULong() + 1uL
    inoutSize.pointed.value = required
    if (buffer == null || capacity < required) return@abiStatus CODEX_AGENT_STATUS_BUFFER_TOO_SMALL
    runtimeIdentityBytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    buffer[runtimeIdentityBytes.size] = 0u.toUByte()
    CODEX_AGENT_STATUS_OK
}

@CName("codex_agent_context_create")
public fun codexAgentContextCreate(outContext: CPointer<COpaquePointerVar>?): Int = abiStatus {
    if (outContext == null || outContext.pointed.value != null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val runtime = CodexAgentCContextRuntime()
    val created = handleRegistry.createContext(runtime)
    if (created.status == CODEX_AGENT_STATUS_OK) {
        outContext.pointed.value = checkNotNull(created.value)
    } else {
        runtime.cancel()
    }
    created.status
}

@CName("codex_agent_context_destroy")
public fun codexAgentContextDestroy(context: CPointer<COpaquePointerVar>?): Int = abiStatus {
    if (context == null) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val pointer = context.pointed.value ?: return@abiStatus CODEX_AGENT_STATUS_OK
    val destroyed = handleRegistry.destroyContextWithPayload(pointer)
    if (destroyed.status == CODEX_AGENT_STATUS_OK) {
        (destroyed.payload as? CodexAgentCContextRuntime)?.cancel()
        context.pointed.value = null
    }
    destroyed.status
}

internal inline fun abiStatus(block: () -> Int): Int = try {
    block()
} catch (_: OutOfMemoryError) {
    CODEX_AGENT_STATUS_OUT_OF_MEMORY
} catch (_: IllegalArgumentException) {
    CODEX_AGENT_STATUS_INVALID_ARGUMENT
} catch (_: Throwable) {
    CODEX_AGENT_STATUS_INTERNAL_ERROR
}
