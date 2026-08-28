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
import kotlinx.coroutines.flow.Flow
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
    val valueKind: CodexAgentCOperationValueKind = CodexAgentCOperationValueKind.NONE,
    val value: Any? = null,
)

internal enum class CodexAgentCOperationValueKind {
    NONE,
    CONVERSATION_SUMMARIES,
    CONVERSATION_VALUE,
    MODELS,
    MODEL,
    STRING,
    SERVICE_TIER,
    SKILL_CATALOG,
    SKILL_CHUNK,
    SKILL,
    HOOK_CATALOG,
    HOOK,
    PLUGIN_CATALOG,
    PLUGIN_DETAIL,
    PLUGIN_INSTALL_RESULT,
    CONNECTORS,
    MCP_SERVERS,
    MCP_SERVER,
}

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
    var ownedTargetLease = targetLease
    var ownedContextLease: CodexAgentCContextLease? = null
    var unstartedHandle: COpaquePointer? = null
    try {
        if (outOperation == null || outOperation.pointed.value != null) {
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        }
        val acquiredContext = handleRegistry.acquireContext(context)
        if (acquiredContext.status != CODEX_AGENT_STATUS_OK) return acquiredContext.status
        val contextLease = checkNotNull(acquiredContext.value)
        ownedContextLease = contextLease
        if (!runtime.acceptsLaunches) {
            ownedTargetLease?.let { if (it.close() == CODEX_AGENT_STATUS_OK) ownedTargetLease = null }
            val releaseStatus = contextLease.close()
            if (releaseStatus == CODEX_AGENT_STATUS_OK) ownedContextLease = null
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
            ownedTargetLease?.let { if (it.close() == CODEX_AGENT_STATUS_OK) ownedTargetLease = null }
            val releaseStatus = contextLease.close()
            if (releaseStatus == CODEX_AGENT_STATUS_OK) ownedContextLease = null
            return if (releaseStatus == CODEX_AGENT_STATUS_OK) created.status else releaseStatus
        }
        val handle = checkNotNull(created.value)
        unstartedHandle = handle
        outOperation.pointed.value = handle
        val startStatus = operation.start(handle, contextLease, ownedTargetLease, execute)
        if (startStatus == CODEX_AGENT_STATUS_OK) {
            unstartedHandle = null
            ownedTargetLease = null
            ownedContextLease = null
            return startStatus
        }
        outOperation.pointed.value = null
        ownedTargetLease?.let { if (it.close() == CODEX_AGENT_STATUS_OK) ownedTargetLease = null }
        if (contextLease.close() == CODEX_AGENT_STATUS_OK) ownedContextLease = null
        val abandonStatus = handleRegistry.abandonOpenEntry(
            contextPointer,
            handle,
            CodexAgentCHandleKind.OPERATION,
        )
        if (abandonStatus == CODEX_AGENT_STATUS_OK) unstartedHandle = null
        return if (abandonStatus == CODEX_AGENT_STATUS_OK) startStatus else abandonStatus
    } finally {
        unstartedHandle?.let { handle ->
            if (outOperation?.pointed?.value == handle) outOperation.pointed.value = null
            handleRegistry.abandonOpenEntry(context, handle, CodexAgentCHandleKind.OPERATION)
        }
        ownedTargetLease?.close()
        ownedContextLease?.close()
    }
}

internal inline fun <reified T : Any> startCodexAgentCTargetOperation(
    context: COpaquePointer?,
    target: COpaquePointer?,
    targetKind: CodexAgentCHandleKind,
    callback: CodexAgentCOperationCallback?,
    userData: COpaquePointer?,
    outOperation: CPointer<COpaquePointerVar>?,
    crossinline runtime: (T) -> CodexAgentCContextRuntime,
    crossinline execute: suspend (T) -> CodexAgentCOperationResult,
): Int = abiStatus {
    if (!validEmptyOutput(outOperation)) return@abiStatus CODEX_AGENT_STATUS_INVALID_ARGUMENT
    val acquired = handleRegistry.acquire(context, target, targetKind)
    if (acquired.status != CODEX_AGENT_STATUS_OK) return@abiStatus acquired.status
    val targetLease = checkNotNull(acquired.value)
    var ownedTargetLease: CodexAgentCHandleLease? = targetLease
    try {
        val wrapper = targetLease.payload as? T
            ?: return@abiStatus CODEX_AGENT_STATUS_WRONG_HANDLE_TYPE
        val operationRuntime = runtime(wrapper)
        val operationExecute: suspend () -> CodexAgentCOperationResult = { execute(wrapper) }
        val status = startCodexAgentCOperation(
            context,
            operationRuntime,
            callback,
            userData,
            outOperation,
            targetLease,
            operationExecute,
        )
        ownedTargetLease = null
        status
    } finally {
        ownedTargetLease?.close()
    }
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
    private val states: Flow<T>,
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
    states: Flow<T>,
    snapshot: (T) -> CodexAgentCStateSnapshot,
    isTerminal: (T) -> Boolean,
    callback: CodexAgentCStateCallback,
    userData: COpaquePointer?,
    outSubscription: CPointer<COpaquePointerVar>?,
): Int {
    var ownedContextLease: CodexAgentCContextLease? = null
    var unstartedHandle: COpaquePointer? = null
    try {
        if (outSubscription == null || outSubscription.pointed.value != null) {
            return CODEX_AGENT_STATUS_INVALID_ARGUMENT
        }
        val acquiredContext = handleRegistry.acquireContext(context)
        if (acquiredContext.status != CODEX_AGENT_STATUS_OK) return acquiredContext.status
        val contextLease = checkNotNull(acquiredContext.value)
        ownedContextLease = contextLease
        if (!runtime.acceptsLaunches) {
            val releaseStatus = contextLease.close()
            if (releaseStatus == CODEX_AGENT_STATUS_OK) ownedContextLease = null
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
            if (releaseStatus == CODEX_AGENT_STATUS_OK) ownedContextLease = null
            return if (releaseStatus == CODEX_AGENT_STATUS_OK) created.status else releaseStatus
        }
        val handle = checkNotNull(created.value)
        unstartedHandle = handle
        outSubscription.pointed.value = handle
        val startStatus = subscription.start(handle, contextLease)
        if (startStatus == CODEX_AGENT_STATUS_OK) {
            unstartedHandle = null
            ownedContextLease = null
            return startStatus
        }
        outSubscription.pointed.value = null
        if (contextLease.close() == CODEX_AGENT_STATUS_OK) ownedContextLease = null
        val abandonStatus = handleRegistry.abandonOpenEntry(
            contextPointer,
            handle,
            CodexAgentCHandleKind.SUBSCRIPTION,
        )
        if (abandonStatus == CODEX_AGENT_STATUS_OK) unstartedHandle = null
        return if (abandonStatus == CODEX_AGENT_STATUS_OK) startStatus else abandonStatus
    } finally {
        unstartedHandle?.let { handle ->
            if (outSubscription?.pointed?.value == handle) outSubscription.pointed.value = null
            handleRegistry.abandonOpenEntry(context, handle, CodexAgentCHandleKind.SUBSCRIPTION)
        }
        ownedContextLease?.close()
    }
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
