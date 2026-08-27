@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import kotlin.concurrent.atomics.AtomicInt
import kotlin.concurrent.atomics.AtomicReference
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.StableRef
import kotlinx.cinterop.asStableRef
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.withContext

internal const val CODEX_AGENT_STATUS_STALE_HANDLE: Int = 3
internal const val CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE: Int = 4
internal const val CODEX_AGENT_STATUS_WRONG_CONTEXT: Int = 5
internal const val CODEX_AGENT_STATUS_BUSY: Int = 6
internal const val CODEX_AGENT_STATUS_CANCELLED: Int = 7
internal const val CODEX_AGENT_STATUS_CLOSED: Int = 11

internal enum class CodexAgentCHandleKind {
    HOST,
    AGENT,
    CONVERSATION,
    OPERATION,
    SUBSCRIPTION,
    SNAPSHOT,
}

internal data class CodexAgentCRegistryResult<out T : Any>(
    val status: Int,
    val value: T? = null,
)

/**
 * Owns every StableRef marker used as a C handle. Incoming pointers are only
 * compared as map keys; only markers removed from this registry are disposed.
 *
 * ponytail: one process-wide copy-on-write state favors simple linearization;
 * shard by context only if profiling shows registry contention or copy cost.
 */
internal class CodexAgentCHandleRegistry(
    private val allocateMarker: () -> COpaquePointer = ::allocateNativeMarker,
    private val disposeMarker: (COpaquePointer) -> Unit = ::disposeNativeMarker,
    private val beforeCloseFinalize: () -> Unit = {},
) {
    private val state = AtomicReference(RegistryState())

    fun createContext(): CodexAgentCRegistryResult<COpaquePointer> = allocateAndInstall { marker ->
        mutate { current ->
            if (marker in current.contexts || marker in current.tokens ||
                current.nextContextId == ULong.MAX_VALUE
            ) {
                return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_INTERNAL_ERROR))
            }
            val id = current.nextContextId
            val context = ContextRecord(id = id)
            val updated = current.copy(
                nextContextId = id + 1uL,
                contexts = current.contexts + (marker to context),
            )
            changed(updated, success(marker))
        }
    }

    fun destroyContext(context: COpaquePointer?): Int {
        if (context == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        return guardedStatus {
            mutate { current ->
                if (context !in current.contexts) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_STALE_HANDLE)
                }
                val helped = finalizeCompletedCloses(current, context)
                val record = checkNotNull(helped.contexts[context])
                if (hasNonterminalSemanticEntry(helped, record)) {
                    return@mutate Mutation(helped, CODEX_AGENT_STATUS_BUSY)
                }
                if (record.leases != 0) {
                    val updated = if (record.phase == ContextPhase.LIVE) {
                        helped.copy(
                            contexts = helped.contexts + (
                                context to record.copy(phase = ContextPhase.TEARING_DOWN)
                            ),
                        )
                    } else {
                        helped
                    }
                    return@mutate Mutation(updated, CODEX_AGENT_STATUS_BUSY)
                }
                val tearingDown = if (record.phase == ContextPhase.LIVE) {
                    helped.copy(
                        contexts = helped.contexts + (
                            context to record.copy(phase = ContextPhase.TEARING_DOWN)
                        ),
                    )
                } else {
                    helped
                }
                val reclaimed = reclaimContext(tearingDown, context)
                changed(reclaimed.state, CODEX_AGENT_STATUS_OK, reclaimed.markers)
            }
        }
    }

    fun createEntry(
        context: COpaquePointer?,
        kind: CodexAgentCHandleKind,
        payload: Any,
        parent: COpaquePointer? = null,
        parentKind: CodexAgentCHandleKind? = null,
    ): CodexAgentCRegistryResult<COpaquePointer> {
        if (context == null || (parent == null) != (parentKind == null)) {
            return failure(CODEX_AGENT_STATUS_INVALID_ARGUMENT)
        }
        return allocateAndInstall { marker ->
            mutate { current ->
                val contextRecord = current.contexts[context]
                    ?.takeIf { it.phase == ContextPhase.LIVE }
                    ?: return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_STALE_HANDLE))
                val parentStamp = if (parent == null) {
                    null
                } else {
                    val resolved = resolve(
                        current,
                        context,
                        parent,
                        checkNotNull(parentKind),
                        checkLifecycle = true,
                    )
                    if (resolved.status != CODEX_AGENT_STATUS_OK) {
                        return@mutate unchanged(current, failure(resolved.status))
                    }
                    ParentStamp(
                        checkNotNull(resolved.entryKey),
                        checkNotNull(resolved.entry).generation,
                    )
                }
                if (marker in current.contexts || marker in current.tokens ||
                    current.nextEntryId == ULong.MAX_VALUE
                ) {
                    return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_INTERNAL_ERROR))
                }
                val key = EntryKey(contextRecord.id, current.nextEntryId)
                val entry = EntryRecord(
                    kind = kind,
                    parent = parentStamp,
                    payload = payload,
                    aliases = 1,
                )
                val token = TokenRecord(contextRecord.id, key, kind)
                val updatedContext = contextRecord.copy(
                    tokens = contextRecord.tokens + marker,
                    entries = contextRecord.entries + key,
                )
                val updated = current.copy(
                    nextEntryId = current.nextEntryId + 1uL,
                    contexts = current.contexts + (context to updatedContext),
                    tokens = current.tokens + (marker to token),
                    entries = current.entries + (key to entry),
                )
                changed(updated, success(marker))
            }
        }
    }

    fun retain(
        context: COpaquePointer?,
        handle: COpaquePointer?,
        expectedKind: CodexAgentCHandleKind,
    ): CodexAgentCRegistryResult<COpaquePointer> {
        if (context == null || handle == null) {
            return failure(CODEX_AGENT_STATUS_INVALID_ARGUMENT)
        }
        return allocateAndInstall { marker ->
            mutate { current ->
                val resolved = resolve(
                    current,
                    context,
                    handle,
                    expectedKind,
                    checkLifecycle = true,
                )
                if (resolved.status != CODEX_AGENT_STATUS_OK) {
                    return@mutate unchanged(current, failure(resolved.status))
                }
                val contextRecord = checkNotNull(resolved.context)
                val entry = checkNotNull(resolved.entry)
                if (marker in current.contexts || marker in current.tokens ||
                    entry.aliases == Int.MAX_VALUE
                ) {
                    return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_INTERNAL_ERROR))
                }
                val key = checkNotNull(resolved.entryKey)
                val token = TokenRecord(contextRecord.id, key, expectedKind)
                val updated = current.copy(
                    contexts = current.contexts + (
                        context to contextRecord.copy(tokens = contextRecord.tokens + marker)
                    ),
                    tokens = current.tokens + (marker to token),
                    entries = current.entries + (key to entry.copy(aliases = entry.aliases + 1)),
                )
                changed(updated, success(marker))
            }
        }
    }

    /** Releases one alias even after its parent or logical resource is closed. */
    fun release(
        context: COpaquePointer?,
        handle: COpaquePointer?,
        expectedKind: CodexAgentCHandleKind,
    ): Int {
        if (context == null || handle == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        return guardedStatus {
            mutate { current ->
                val contextRecord = current.contexts[context]
                    ?.takeIf { it.phase == ContextPhase.LIVE }
                    ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_STALE_HANDLE)
                val token = current.tokens[handle]
                    ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_STALE_HANDLE)
                if (token.phase != TokenPhase.LIVE) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_STALE_HANDLE)
                }
                if (token.contextId != contextRecord.id) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_WRONG_CONTEXT)
                }
                if (token.kind != expectedKind) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE)
                }
                val entry = current.entries[token.entry]
                    ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_STALE_HANDLE)
                if (entry.kind != token.kind || entry.aliases <= 0) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
                }
                if (entry.aliases == 1 &&
                    entry.kind != CodexAgentCHandleKind.SNAPSHOT &&
                    entry.lifecycle == EntryLifecycle.OPEN &&
                    hasCurrentAncestors(current, entry)
                ) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_BUSY)
                }
                val aliases = entry.aliases - 1
                val updatedEntry = entry.copy(
                    aliases = aliases,
                    payload = entry.payload.takeUnless {
                        entry.leases == 0 && aliases == 0 &&
                            (entry.lifecycle == EntryLifecycle.CLOSED ||
                                entry.kind == CodexAgentCHandleKind.SNAPSHOT)
                    },
                )
                val updated = current.copy(
                    tokens = current.tokens + (handle to token.copy(phase = TokenPhase.RELEASED)),
                    entries = current.entries + (token.entry to updatedEntry),
                )
                changed(updated, CODEX_AGENT_STATUS_OK)
            }
        }
    }

    fun acquire(
        context: COpaquePointer?,
        handle: COpaquePointer?,
        expectedKind: CodexAgentCHandleKind,
    ): CodexAgentCRegistryResult<CodexAgentCHandleLease> {
        if (context == null || handle == null) {
            return failure(CODEX_AGENT_STATUS_INVALID_ARGUMENT)
        }
        return guardedResult {
            mutate { current ->
                val resolved = resolve(
                    current,
                    context,
                    handle,
                    expectedKind,
                    checkLifecycle = true,
                )
                if (resolved.status != CODEX_AGENT_STATUS_OK) {
                    return@mutate unchanged(current, failure(resolved.status))
                }
                val contextRecord = checkNotNull(resolved.context)
                val entry = checkNotNull(resolved.entry)
                val key = checkNotNull(resolved.entryKey)
                val payload = entry.payload
                    ?: return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_INTERNAL_ERROR))
                if (contextRecord.leases == Int.MAX_VALUE || entry.leases == Int.MAX_VALUE) {
                    return@mutate unchanged(current, failure(CODEX_AGENT_STATUS_BUSY))
                }
                val updated = current.copy(
                    contexts = current.contexts + (
                        context to contextRecord.copy(leases = contextRecord.leases + 1)
                    ),
                    entries = current.entries + (key to entry.copy(leases = entry.leases + 1)),
                )
                changed(
                    updated,
                    success(CodexAgentCHandleLease(payload) { releaseLease(context, key) }),
                )
            }
        }
    }

    fun invalidateChildren(
        context: COpaquePointer?,
        parent: COpaquePointer?,
        expectedKind: CodexAgentCHandleKind,
    ): Int {
        if (context == null || parent == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        return guardedStatus {
            mutate { current ->
                val resolved = resolve(
                    current,
                    context,
                    parent,
                    expectedKind,
                    checkLifecycle = true,
                )
                if (resolved.status != CODEX_AGENT_STATUS_OK) {
                    return@mutate unchanged(current, resolved.status)
                }
                val key = checkNotNull(resolved.entryKey)
                val entry = checkNotNull(resolved.entry)
                if (entry.generation == ULong.MAX_VALUE) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
                }
                if (hasLeasedSubtree(current, key)) {
                    return@mutate unchanged(current, CODEX_AGENT_STATUS_BUSY)
                }
                changed(
                    current.copy(
                        entries = current.entries + (
                            key to entry.copy(generation = entry.generation + 1uL)
                        ),
                    ),
                    CODEX_AGENT_STATUS_OK,
                )
            }
        }
    }

    suspend fun semanticClose(
        context: COpaquePointer?,
        handle: COpaquePointer?,
        expectedKind: CodexAgentCHandleKind,
        close: suspend (Any) -> Int,
    ): Int {
        if (context == null || handle == null) return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        val started = guardedCloseStart {
            mutate { current ->
                val resolved = resolve(
                    current,
                    context,
                    handle,
                    expectedKind,
                    checkLifecycle = false,
                )
                if (resolved.status != CODEX_AGENT_STATUS_OK) {
                    return@mutate unchanged(current, CloseStart(resolved.status))
                }
                val contextRecord = checkNotNull(resolved.context)
                val key = checkNotNull(resolved.entryKey)
                val entry = checkNotNull(resolved.entry)
                when (entry.lifecycle) {
                    EntryLifecycle.CLOSING -> {
                        val completion = entry.closeCompletion
                            ?: return@mutate unchanged(
                                current,
                                CloseStart(CODEX_AGENT_STATUS_INTERNAL_ERROR),
                            )
                        if (completion.status.load() == CLOSE_PENDING) {
                            unchanged(current, CloseStart(CODEX_AGENT_STATUS_BUSY))
                        } else {
                            unchanged(
                                current,
                                CloseStart(
                                    CODEX_AGENT_STATUS_OK,
                                    CloseClaim(context, key, null, completion),
                                ),
                            )
                        }
                    }

                    EntryLifecycle.CLOSED -> unchanged(
                        current,
                        CloseStart(entry.closeStatus ?: CODEX_AGENT_STATUS_INTERNAL_ERROR),
                    )

                    EntryLifecycle.OPEN -> {
                        val payload = entry.payload
                            ?: return@mutate unchanged(
                                current,
                                CloseStart(CODEX_AGENT_STATUS_INTERNAL_ERROR),
                            )
                        if (entry.generation == ULong.MAX_VALUE) {
                            return@mutate unchanged(
                                current,
                                CloseStart(CODEX_AGENT_STATUS_INTERNAL_ERROR),
                            )
                        }
                        if (hasLeasedSubtree(current, key) ||
                            contextRecord.leases == Int.MAX_VALUE
                        ) {
                            return@mutate unchanged(current, CloseStart(CODEX_AGENT_STATUS_BUSY))
                        }
                        val completion = CloseCompletion()
                        val updated = current.copy(
                            contexts = current.contexts + (
                                context to contextRecord.copy(leases = contextRecord.leases + 1)
                            ),
                            entries = current.entries + (
                                key to entry.copy(
                                    generation = entry.generation + 1uL,
                                    lifecycle = EntryLifecycle.CLOSING,
                                    closeCompletion = completion,
                                    leases = entry.leases + 1,
                                )
                            ),
                        )
                        changed(
                            updated,
                            CloseStart(
                                CODEX_AGENT_STATUS_OK,
                                CloseClaim(context, key, payload, completion),
                            ),
                        )
                    }
                }
            }
        }
        val claim = started.claim ?: return started.status
        if (claim.payload != null) {
            val closeStatus = try {
                withContext(NonCancellable) { close(claim.payload) }
            } catch (_: CancellationException) {
                CODEX_AGENT_STATUS_CANCELLED
            } catch (_: OutOfMemoryError) {
                CODEX_AGENT_STATUS_OUT_OF_MEMORY
            } catch (_: Throwable) {
                CODEX_AGENT_STATUS_INTERNAL_ERROR
            }
            claim.completion.status.store(closeStatus)
        }
        val closeStatus = claim.completion.status.load()
        if (closeStatus == CLOSE_PENDING) return CODEX_AGENT_STATUS_INTERNAL_ERROR
        val completionStatus = finishClose(claim)
        return if (completionStatus == CODEX_AGENT_STATUS_OK) closeStatus else completionStatus
    }

    internal fun releaseLease(context: COpaquePointer, key: EntryKey): Int = guardedStatus {
        mutate { current ->
            val contextRecord = current.contexts[context]
                ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            val entry = current.entries[key]
                ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            if (contextRecord.leases <= 0 || entry.leases <= 0) {
                return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            }
            val entryLeases = entry.leases - 1
            val updatedEntry = entry.copy(
                leases = entryLeases,
                payload = entry.payload.takeUnless {
                    entryLeases == 0 && entry.aliases == 0 &&
                        (entry.lifecycle == EntryLifecycle.CLOSED ||
                            entry.kind == CodexAgentCHandleKind.SNAPSHOT)
                },
            )
            val updatedContext = contextRecord.copy(leases = contextRecord.leases - 1)
            changed(
                current.copy(
                    contexts = current.contexts + (context to updatedContext),
                    entries = current.entries + (key to updatedEntry),
                ),
                CODEX_AGENT_STATUS_OK,
            )
        }
    }

    private fun finishClose(claim: CloseClaim): Int = guardedStatus {
        beforeCloseFinalize()
        mutate { current ->
            val contextRecord = current.contexts[claim.context]
            if (contextRecord == null || contextRecord.id != claim.entry.contextId) {
                return@mutate unchanged(current, CODEX_AGENT_STATUS_OK)
            }
            val entry = current.entries[claim.entry]
                ?: return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            if (entry.closeCompletion !== claim.completion) {
                return@mutate unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            }
            val closeStatus = claim.completion.status.load()
            if (closeStatus == CLOSE_PENDING) {
                return@mutate unchanged(current, CODEX_AGENT_STATUS_BUSY)
            }
            when (entry.lifecycle) {
                EntryLifecycle.CLOSED -> unchanged(
                    current,
                    if (entry.closeStatus == closeStatus) {
                        CODEX_AGENT_STATUS_OK
                    } else {
                        CODEX_AGENT_STATUS_INTERNAL_ERROR
                    },
                )
                EntryLifecycle.CLOSING -> changed(
                    finalizeClose(current, claim.context, claim.entry, contextRecord, entry, closeStatus),
                    CODEX_AGENT_STATUS_OK,
                )
                EntryLifecycle.OPEN -> unchanged(current, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            }
        }
    }

    private fun finalizeCompletedCloses(
        current: RegistryState,
        contextPointer: COpaquePointer,
    ): RegistryState {
        var updated = current
        val entryKeys = checkNotNull(current.contexts[contextPointer]).entries
        entryKeys.forEach { key ->
            val entry = checkNotNull(updated.entries[key])
            val completion = entry.closeCompletion
            if (entry.lifecycle == EntryLifecycle.CLOSING && completion != null) {
                val closeStatus = completion.status.load()
                if (closeStatus != CLOSE_PENDING) {
                    val context = checkNotNull(updated.contexts[contextPointer])
                    updated = finalizeClose(
                        updated,
                        contextPointer,
                        key,
                        context,
                        entry,
                        closeStatus,
                    )
                }
            }
        }
        return updated
    }

    private fun finalizeClose(
        current: RegistryState,
        contextPointer: COpaquePointer,
        key: EntryKey,
        context: ContextRecord,
        entry: EntryRecord,
        closeStatus: Int,
    ): RegistryState {
        check(entry.lifecycle == EntryLifecycle.CLOSING)
        check(entry.leases > 0 && context.leases > 0)
        val entryLeases = entry.leases - 1
        val updatedEntry = entry.copy(
            lifecycle = EntryLifecycle.CLOSED,
            closeStatus = closeStatus,
            leases = entryLeases,
            payload = if (entryLeases == 0) null else entry.payload,
        )
        return current.copy(
            contexts = current.contexts + (
                contextPointer to context.copy(leases = context.leases - 1)
            ),
            entries = current.entries + (key to updatedEntry),
        )
    }

    private fun hasNonterminalSemanticEntry(
        current: RegistryState,
        context: ContextRecord,
    ): Boolean = context.entries.any { key ->
        val entry = current.entries[key] ?: return@any true
        entry.kind != CodexAgentCHandleKind.SNAPSHOT &&
            entry.lifecycle != EntryLifecycle.CLOSED &&
            hasCurrentAncestors(current, entry)
    }

    private fun hasLeasedSubtree(current: RegistryState, root: EntryKey): Boolean =
        current.entries.any { (key, entry) ->
            entry.leases > 0 && isSameOrDescendant(current, key, root)
        }

    private fun isSameOrDescendant(
        current: RegistryState,
        candidate: EntryKey,
        ancestor: EntryKey,
    ): Boolean {
        var key = candidate
        while (true) {
            if (key == ancestor) return true
            key = current.entries[key]?.parent?.entry ?: return false
        }
    }

    private fun resolve(
        current: RegistryState,
        contextPointer: COpaquePointer,
        handle: COpaquePointer,
        expectedKind: CodexAgentCHandleKind,
        checkLifecycle: Boolean,
    ): Resolution {
        val context = current.contexts[contextPointer]
            ?: return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        if (context.phase != ContextPhase.LIVE) {
            return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        }
        val token = current.tokens[handle]
            ?: return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        if (token.phase != TokenPhase.LIVE) {
            return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        }
        if (token.contextId != context.id) {
            return Resolution(CODEX_AGENT_STATUS_WRONG_CONTEXT)
        }
        if (token.kind != expectedKind) {
            return Resolution(CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE)
        }
        val entry = current.entries[token.entry]
            ?: return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        if (entry.kind != token.kind || token.entry.contextId != context.id) {
            return Resolution(CODEX_AGENT_STATUS_INTERNAL_ERROR)
        }
        if (!hasCurrentAncestors(current, entry)) {
            return Resolution(CODEX_AGENT_STATUS_STALE_HANDLE)
        }
        if (checkLifecycle) {
            when (entry.lifecycle) {
                EntryLifecycle.OPEN -> Unit
                EntryLifecycle.CLOSING -> return Resolution(CODEX_AGENT_STATUS_BUSY)
                EntryLifecycle.CLOSED -> return Resolution(CODEX_AGENT_STATUS_CLOSED)
            }
        }
        return Resolution(CODEX_AGENT_STATUS_OK, context, token.entry, entry)
    }

    private fun hasCurrentAncestors(
        current: RegistryState,
        initial: EntryRecord,
    ): Boolean {
        var entry = initial
        while (true) {
            val parent = entry.parent ?: return true
            val parentEntry = current.entries[parent.entry] ?: return false
            if (parentEntry.generation != parent.generation) return false
            entry = parentEntry
        }
    }

    private fun reclaimContext(
        current: RegistryState,
        contextPointer: COpaquePointer,
    ): Reclamation {
        val context = checkNotNull(current.contexts[contextPointer])
        check(context.phase == ContextPhase.TEARING_DOWN && context.leases == 0)
        return Reclamation(
            state = current.copy(
                contexts = current.contexts - contextPointer,
                tokens = current.tokens - context.tokens,
                entries = current.entries - context.entries,
            ),
            markers = listOf(contextPointer) + context.tokens,
        )
    }

    private fun allocateAndInstall(
        install: (COpaquePointer) -> CodexAgentCRegistryResult<COpaquePointer>,
    ): CodexAgentCRegistryResult<COpaquePointer> {
        val marker = try {
            allocateMarker()
        } catch (_: OutOfMemoryError) {
            return failure(CODEX_AGENT_STATUS_OUT_OF_MEMORY)
        } catch (_: Throwable) {
            return failure(CODEX_AGENT_STATUS_INTERNAL_ERROR)
        }
        var installed = false
        return try {
            install(marker).also { installed = it.status == CODEX_AGENT_STATUS_OK }
        } catch (_: OutOfMemoryError) {
            failure(CODEX_AGENT_STATUS_OUT_OF_MEMORY)
        } catch (_: Throwable) {
            failure(CODEX_AGENT_STATUS_INTERNAL_ERROR)
        } finally {
            if (!installed) runCatching { disposeMarker(marker) }
        }
    }

    private fun <T> mutate(block: (RegistryState) -> Mutation<T>): T {
        while (true) {
            val current = state.load()
            val mutation = block(current)
            if (mutation.state === current) return mutation.result
            if (state.compareAndSet(current, mutation.state)) {
                mutation.disposeAfterCommit.forEach { marker ->
                    runCatching { disposeMarker(marker) }
                }
                return mutation.result
            }
        }
    }

    private fun <T : Any> guardedResult(
        block: () -> CodexAgentCRegistryResult<T>,
    ): CodexAgentCRegistryResult<T> = try {
        block()
    } catch (_: OutOfMemoryError) {
        failure(CODEX_AGENT_STATUS_OUT_OF_MEMORY)
    } catch (_: Throwable) {
        failure(CODEX_AGENT_STATUS_INTERNAL_ERROR)
    }

    private fun guardedStatus(block: () -> Int): Int = try {
        block()
    } catch (_: OutOfMemoryError) {
        CODEX_AGENT_STATUS_OUT_OF_MEMORY
    } catch (_: Throwable) {
        CODEX_AGENT_STATUS_INTERNAL_ERROR
    }

    private fun guardedCloseStart(block: () -> CloseStart): CloseStart = try {
        block()
    } catch (_: OutOfMemoryError) {
        CloseStart(CODEX_AGENT_STATUS_OUT_OF_MEMORY)
    } catch (_: Throwable) {
        CloseStart(CODEX_AGENT_STATUS_INTERNAL_ERROR)
    }
}

internal class CodexAgentCHandleLease internal constructor(
    val payload: Any,
    private val release: () -> Int,
) {
    private val phase = AtomicReference(LeaseReleasePhase.OPEN)

    fun close(): Int {
        while (true) {
            when (val current = phase.load()) {
                LeaseReleasePhase.RELEASED -> return CODEX_AGENT_STATUS_OK
                LeaseReleasePhase.RELEASING -> return CODEX_AGENT_STATUS_BUSY
                LeaseReleasePhase.OPEN -> if (!phase.compareAndSet(current, LeaseReleasePhase.RELEASING)) {
                    continue
                }
            }
            break
        }
        val status = try {
            release()
        } catch (_: OutOfMemoryError) {
            CODEX_AGENT_STATUS_OUT_OF_MEMORY
        } catch (_: Throwable) {
            CODEX_AGENT_STATUS_INTERNAL_ERROR
        }
        phase.store(
            if (status == CODEX_AGENT_STATUS_OK) {
                LeaseReleasePhase.RELEASED
            } else {
                LeaseReleasePhase.OPEN
            },
        )
        return status
    }
}

private class NativeMarker

private fun allocateNativeMarker(): COpaquePointer =
    StableRef.create(NativeMarker()).asCPointer()

private fun disposeNativeMarker(pointer: COpaquePointer) {
    pointer.asStableRef<NativeMarker>().dispose()
}

private enum class ContextPhase { LIVE, TEARING_DOWN }

private enum class TokenPhase { LIVE, RELEASED }

private enum class EntryLifecycle { OPEN, CLOSING, CLOSED }

private enum class LeaseReleasePhase { OPEN, RELEASING, RELEASED }

private const val CLOSE_PENDING: Int = Int.MIN_VALUE

private class CloseCompletion {
    val status = AtomicInt(CLOSE_PENDING)
}

internal data class EntryKey(
    val contextId: ULong,
    val entryId: ULong,
)

private data class ParentStamp(
    val entry: EntryKey,
    val generation: ULong,
)

private data class ContextRecord(
    val id: ULong,
    val phase: ContextPhase = ContextPhase.LIVE,
    val leases: Int = 0,
    val tokens: Set<COpaquePointer> = emptySet(),
    val entries: Set<EntryKey> = emptySet(),
)

private data class TokenRecord(
    val contextId: ULong,
    val entry: EntryKey,
    val kind: CodexAgentCHandleKind,
    val phase: TokenPhase = TokenPhase.LIVE,
)

private data class EntryRecord(
    val kind: CodexAgentCHandleKind,
    val parent: ParentStamp?,
    val generation: ULong = 0uL,
    val lifecycle: EntryLifecycle = EntryLifecycle.OPEN,
    val closeStatus: Int? = null,
    val closeCompletion: CloseCompletion? = null,
    val aliases: Int,
    val leases: Int = 0,
    val payload: Any?,
)

private data class RegistryState(
    val nextContextId: ULong = 1uL,
    val nextEntryId: ULong = 1uL,
    val contexts: Map<COpaquePointer, ContextRecord> = emptyMap(),
    val tokens: Map<COpaquePointer, TokenRecord> = emptyMap(),
    val entries: Map<EntryKey, EntryRecord> = emptyMap(),
)

private data class Resolution(
    val status: Int,
    val context: ContextRecord? = null,
    val entryKey: EntryKey? = null,
    val entry: EntryRecord? = null,
)

private data class CloseClaim(
    val context: COpaquePointer,
    val entry: EntryKey,
    val payload: Any?,
    val completion: CloseCompletion,
)

private data class CloseStart(
    val status: Int,
    val claim: CloseClaim? = null,
)

private data class Reclamation(
    val state: RegistryState,
    val markers: List<COpaquePointer>,
)

private data class Mutation<T>(
    val state: RegistryState,
    val result: T,
    val disposeAfterCommit: List<COpaquePointer> = emptyList(),
)

private fun <T> unchanged(state: RegistryState, result: T): Mutation<T> =
    Mutation(state, result)

private fun <T> changed(
    state: RegistryState,
    result: T,
    disposeAfterCommit: List<COpaquePointer> = emptyList(),
): Mutation<T> = Mutation(state, result, disposeAfterCommit)

private fun <T : Any> success(value: T): CodexAgentCRegistryResult<T> =
    CodexAgentCRegistryResult(CODEX_AGENT_STATUS_OK, value)

private fun <T : Any> failure(status: Int): CodexAgentCRegistryResult<T> =
    CodexAgentCRegistryResult(status)
