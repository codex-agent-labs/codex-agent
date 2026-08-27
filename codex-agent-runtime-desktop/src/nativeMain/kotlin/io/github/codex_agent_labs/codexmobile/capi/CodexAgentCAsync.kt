@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
    kotlinx.coroutines.DelicateCoroutinesApi::class,
    kotlinx.coroutines.ExperimentalCoroutinesApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.CodexConversation
import io.github.codex_agent_labs.codexmobile.agent.CodexConversations
import io.github.codex_agent_labs.codexmobile.agent.CodexFailure
import io.github.codex_agent_labs.codexmobile.agent.CodexOperationException
import kotlin.concurrent.atomics.AtomicBoolean
import kotlin.concurrent.atomics.AtomicReference
import kotlinx.cinterop.CFunction
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.invoke
import kotlinx.cinterop.pointed
import kotlinx.cinterop.value
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.takeWhile
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.coroutines.yield

internal typealias CodexAgentCOperationCallback = CPointer<
    CFunction<(COpaquePointer?, COpaquePointer?, COpaquePointer?) -> Unit>
>

internal typealias CodexAgentCStateCallback = CPointer<
    CFunction<(
        COpaquePointer?,
        COpaquePointer?,
        Int,
        COpaquePointer?,
        Int,
        COpaquePointer?,
    ) -> Unit>
>

internal class CodexAgentCContextRuntime {
    private val rootJob = SupervisorJob()
    val scope: CoroutineScope = CoroutineScope(rootJob + Dispatchers.Default)
    private val callbackGate = Mutex()
    private val accepting = AtomicBoolean(true)

    val acceptsLaunches: Boolean get() = accepting.load()

    fun launch(block: suspend () -> Unit): Job =
        scope.launch(start = CoroutineStart.ATOMIC) { block() }

    suspend fun callback(block: () -> Unit): Boolean =
        try {
            callbackGate.withLock {
                block()
                true
            }
        } catch (_: Throwable) {
            // A foreign callback must never unwind through Kotlin/Native.
            false
        }

    fun cancel() {
        accepting.store(false)
        rootJob.cancel()
    }
}

internal data class CodexAgentCOperationResult(
    val status: Int,
    val conversation: CodexConversation? = null,
    val conversations: CodexConversations? = null,
    val failure: CodexFailure? = null,
)

internal class CodexAgentCOperation(
    val runtime: CodexAgentCContextRuntime,
    private val context: COpaquePointer,
    private val callback: CodexAgentCOperationCallback?,
    private val userData: COpaquePointer?,
) {
    private val result = AtomicReference<CodexAgentCOperationResult?>(null)
    private val job = AtomicReference<Job?>(null)
    private val semanticallyClosed = AtomicBoolean(false)

    fun start(
        handle: COpaquePointer,
        contextLease: CodexAgentCContextLease,
        targetLease: CodexAgentCHandleLease?,
        execute: suspend () -> CodexAgentCOperationResult,
    ): Int = try {
        job.store(runtime.launch {
            val completed = try {
                execute()
            } catch (_: CancellationException) {
                CodexAgentCOperationResult(CODEX_AGENT_STATUS_CANCELLED)
            } catch (_: OutOfMemoryError) {
                CodexAgentCOperationResult(CODEX_AGENT_STATUS_OUT_OF_MEMORY)
            } catch (error: CodexOperationException) {
                CodexAgentCOperationResult(CODEX_AGENT_STATUS_OPERATION_FAILED, failure = error.failure)
            } catch (_: Throwable) {
                CodexAgentCOperationResult(CODEX_AGENT_STATUS_INTERNAL_ERROR)
            }
            withContext(NonCancellable) {
                try {
                    result.compareAndSet(null, completed)
                    callback?.let { notify ->
                        runtime.callback { notify.invoke(context, handle, userData) }
                    }
                } finally {
                    closeLease(targetLease)
                    if (closeAsyncEntry(context, handle, CodexAgentCHandleKind.OPERATION) ==
                        CODEX_AGENT_STATUS_OK
                    ) {
                        semanticallyClosed.store(true)
                    }
                    closeLease(contextLease)
                }
            }
        })
        CODEX_AGENT_STATUS_OK
    } catch (_: OutOfMemoryError) {
        CODEX_AGENT_STATUS_OUT_OF_MEMORY
    } catch (_: Throwable) {
        CODEX_AGENT_STATUS_INTERNAL_ERROR
    }

    fun cancel() {
        job.load()?.cancel()
    }

    fun completedResult(): CodexAgentCOperationResult? = result.load()

    fun isQuiescent(): Boolean = job.load()?.isCompleted == true && semanticallyClosed.load()
}

internal fun startCodexAgentCOperation(
    context: COpaquePointer?,
    runtime: CodexAgentCContextRuntime,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    targetLease: CodexAgentCHandleLease? = null,
    execute: suspend () -> CodexAgentCOperationResult,
): Int {
    if (outOperation == null || outOperation.pointed.value != null) {
        targetLease?.close()
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val acquiredContext = handleRegistry.acquireContext(context)
    if (acquiredContext.status != CODEX_AGENT_STATUS_OK) {
        targetLease?.close()
        return acquiredContext.status
    }
    val contextLease = checkNotNull(acquiredContext.value)
    if (!runtime.acceptsLaunches) {
        targetLease?.close()
        val releaseStatus = contextLease.close()
        return if (releaseStatus == CODEX_AGENT_STATUS_OK) CODEX_AGENT_STATUS_CLOSED else releaseStatus
    }
    val contextPointer = checkNotNull(context)
    val operation = CodexAgentCOperation(runtime, contextPointer, callback, userData)
    val created = handleRegistry.createEntry(
        contextPointer,
        CodexAgentCHandleKind.OPERATION,
        operation,
    )
    if (created.status != CODEX_AGENT_STATUS_OK) {
        targetLease?.close()
        val releaseStatus = contextLease.close()
        return if (releaseStatus == CODEX_AGENT_STATUS_OK) created.status else releaseStatus
    }
    val handle = checkNotNull(created.value)
    outOperation.pointed.value = handle
    val startStatus = operation.start(handle, contextLease, targetLease, execute)
    if (startStatus == CODEX_AGENT_STATUS_OK) return startStatus
    outOperation.pointed.value = null
    targetLease?.close()
    contextLease.close()
    val abandonStatus = handleRegistry.abandonOpenEntry(
        contextPointer,
        handle,
        CodexAgentCHandleKind.OPERATION,
    )
    return if (abandonStatus == CODEX_AGENT_STATUS_OK) startStatus else abandonStatus
}

internal fun cancelCodexAgentCOperation(context: COpaquePointer?, operation: COpaquePointer?): Int =
    withPayload<CodexAgentCOperation>(
        context,
        operation,
        CodexAgentCHandleKind.OPERATION,
        includeClosed = true,
    ) {
        it.cancel()
        CODEX_AGENT_STATUS_OK
    }

internal fun queryCodexAgentCOperation(
    context: COpaquePointer?,
    operation: COpaquePointer?,
): CodexAgentCRegistryResult<CodexAgentCOperationResult> {
    var completed: CodexAgentCOperationResult? = null
    val status = withPayload<CodexAgentCOperation>(
        context,
        operation,
        CodexAgentCHandleKind.OPERATION,
        includeClosed = true,
    ) {
        completed = it.completedResult()
        CODEX_AGENT_STATUS_OK
    }
    return when {
        status != CODEX_AGENT_STATUS_OK -> CodexAgentCRegistryResult(status)
        completed == null -> CodexAgentCRegistryResult(CODEX_AGENT_STATUS_NOT_READY)
        else -> CodexAgentCRegistryResult(CODEX_AGENT_STATUS_OK, completed)
    }
}

internal fun destroyCodexAgentCOperation(context: COpaquePointer?, operation: COpaquePointer?): Int {
    var payload: CodexAgentCOperation? = null
    val acquireStatus = withPayload<CodexAgentCOperation>(
        context,
        operation,
        CodexAgentCHandleKind.OPERATION,
        includeClosed = true,
    ) {
        payload = it
        CODEX_AGENT_STATUS_OK
    }
    if (acquireStatus != CODEX_AGENT_STATUS_OK) return acquireStatus
    val owned = checkNotNull(payload)
    owned.cancel()
    return if (owned.isQuiescent()) {
        handleRegistry.release(context, operation, CodexAgentCHandleKind.OPERATION)
    } else {
        CODEX_AGENT_STATUS_BUSY
    }
}

internal data class CodexAgentCStateSnapshot(
    val eventStatus: Int,
    val snapshot: COpaquePointer?,
)

internal class CodexAgentCStateSubscription<T>(
    val runtime: CodexAgentCContextRuntime,
    private val context: COpaquePointer,
    private val states: StateFlow<T>,
    private val snapshot: (T) -> CodexAgentCStateSnapshot,
    private val isTerminal: (T) -> Boolean,
    private val callback: CodexAgentCStateCallback,
    private val userData: COpaquePointer?,
) {
    private val job = AtomicReference<Job?>(null)
    private val terminalDelivered = AtomicBoolean(false)
    private val semanticallyClosed = AtomicBoolean(false)

    fun start(handle: COpaquePointer, contextLease: CodexAgentCContextLease): Int = try {
        job.store(runtime.launch {
            try {
                states.takeWhile { value ->
                    val terminal = isTerminal(value)
                    !deliver(handle, snapshot(value), terminal)
                }.collect()
                deliverTerminal(handle, CODEX_AGENT_STATUS_CLOSED)
            } catch (_: CancellationException) {
                deliverTerminal(handle, CODEX_AGENT_STATUS_CANCELLED)
            } catch (_: OutOfMemoryError) {
                deliverTerminal(handle, CODEX_AGENT_STATUS_OUT_OF_MEMORY)
            } catch (_: Throwable) {
                deliverTerminal(handle, CODEX_AGENT_STATUS_INTERNAL_ERROR)
            } finally {
                withContext(NonCancellable) {
                    if (closeAsyncEntry(context, handle, CodexAgentCHandleKind.SUBSCRIPTION) ==
                        CODEX_AGENT_STATUS_OK
                    ) {
                        semanticallyClosed.store(true)
                    }
                    closeLease(contextLease)
                }
            }
        })
        CODEX_AGENT_STATUS_OK
    } catch (_: OutOfMemoryError) {
        CODEX_AGENT_STATUS_OUT_OF_MEMORY
    } catch (_: Throwable) {
        CODEX_AGENT_STATUS_INTERNAL_ERROR
    }

    fun cancel() {
        job.load()?.cancel()
    }

    fun isQuiescent(): Boolean = job.load()?.isCompleted == true && semanticallyClosed.load()

    private suspend fun deliver(
        handle: COpaquePointer,
        event: CodexAgentCStateSnapshot,
        stateIsTerminal: Boolean,
    ): Boolean = withContext(NonCancellable) {
        val terminal = stateIsTerminal || event.eventStatus != CODEX_AGENT_STATUS_OK
        if (!terminal || terminalDelivered.compareAndSet(false, true)) {
            val callbackSucceeded = runtime.callback {
                callback.invoke(
                    context,
                    handle,
                    event.eventStatus,
                    event.snapshot,
                    if (terminal) 1 else 0,
                    userData,
                )
            }
            if (!callbackSucceeded) terminalDelivered.store(true)
            terminal || !callbackSucceeded
        } else {
            terminal
        }
    }

    private suspend fun deliverTerminal(handle: COpaquePointer, status: Int) {
        withContext(NonCancellable) {
            if (terminalDelivered.compareAndSet(false, true)) {
                runtime.callback { callback.invoke(context, handle, status, null, 1, userData) }
            }
        }
    }
}

internal fun <T> startCodexAgentCStateSubscription(
    context: COpaquePointer?,
    runtime: CodexAgentCContextRuntime,
    states: StateFlow<T>,
    snapshot: (T) -> CodexAgentCStateSnapshot,
    isTerminal: (T) -> Boolean,
    callback: CodexAgentCStateCallback,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int {
    if (outSubscription == null || outSubscription.pointed.value != null) {
        return CODEX_AGENT_STATUS_INVALID_ARGUMENT
    }
    val acquiredContext = handleRegistry.acquireContext(context)
    if (acquiredContext.status != CODEX_AGENT_STATUS_OK) {
        return acquiredContext.status
    }
    val contextLease = checkNotNull(acquiredContext.value)
    if (!runtime.acceptsLaunches) {
        val releaseStatus = contextLease.close()
        return if (releaseStatus == CODEX_AGENT_STATUS_OK) CODEX_AGENT_STATUS_CLOSED else releaseStatus
    }
    val contextPointer = checkNotNull(context)
    val subscription = CodexAgentCStateSubscription(
        runtime,
        contextPointer,
        states,
        snapshot,
        isTerminal,
        callback,
        userData,
    )
    val created = handleRegistry.createEntry(
        contextPointer,
        CodexAgentCHandleKind.SUBSCRIPTION,
        subscription,
    )
    if (created.status != CODEX_AGENT_STATUS_OK) {
        val releaseStatus = contextLease.close()
        return if (releaseStatus == CODEX_AGENT_STATUS_OK) created.status else releaseStatus
    }
    val handle = checkNotNull(created.value)
    outSubscription.pointed.value = handle
    val startStatus = subscription.start(handle, contextLease)
    if (startStatus == CODEX_AGENT_STATUS_OK) return startStatus
    outSubscription.pointed.value = null
    contextLease.close()
    val abandonStatus = handleRegistry.abandonOpenEntry(
        contextPointer,
        handle,
        CodexAgentCHandleKind.SUBSCRIPTION,
    )
    return if (abandonStatus == CODEX_AGENT_STATUS_OK) startStatus else abandonStatus
}

internal fun destroyCodexAgentCStateSubscription(
    context: COpaquePointer?,
    subscription: COpaquePointer?,
): Int {
    var payload: CodexAgentCStateSubscription<*>? = null
    val acquireStatus = withPayload<CodexAgentCStateSubscription<*>>(
        context,
        subscription,
        CodexAgentCHandleKind.SUBSCRIPTION,
        includeClosed = true,
    ) {
        payload = it
        CODEX_AGENT_STATUS_OK
    }
    if (acquireStatus != CODEX_AGENT_STATUS_OK) return acquireStatus
    val owned = checkNotNull(payload)
    owned.cancel()
    return if (owned.isQuiescent()) {
        handleRegistry.release(context, subscription, CodexAgentCHandleKind.SUBSCRIPTION)
    } else {
        CODEX_AGENT_STATUS_BUSY
    }
}

private suspend fun closeAsyncEntry(
    context: COpaquePointer,
    handle: COpaquePointer,
    kind: CodexAgentCHandleKind,
): Int {
    while (true) {
        when (val status = handleRegistry.semanticClose(context, handle, kind) {
            CODEX_AGENT_STATUS_OK
        }) {
            CODEX_AGENT_STATUS_OK -> return status
            CODEX_AGENT_STATUS_BUSY -> yield()
            else -> return status
        }
    }
}

private suspend fun closeLease(lease: CodexAgentCContextLease) {
    while (lease.close() == CODEX_AGENT_STATUS_BUSY) yield()
}

private suspend fun closeLease(lease: CodexAgentCHandleLease?) {
    while (lease?.close() == CODEX_AGENT_STATUS_BUSY) yield()
}
