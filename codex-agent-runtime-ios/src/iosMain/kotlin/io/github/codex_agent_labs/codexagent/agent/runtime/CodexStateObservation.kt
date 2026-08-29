package io.github.codex_agent_labs.codexagent.agent.runtime

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import platform.Foundation.NSRecursiveLock

/**
 * A cancellable StateFlow observation for Apple clients.
 *
 * Values are delivered serially on the main queue. Closing waits for an in-flight callback unless
 * that callback closes its own observation, and no callback starts after close returns.
 */
public class CodexStateObservation private constructor(
    state: StateFlow<*>,
    onValue: (Any?) -> Unit,
    deliveryDispatcher: CoroutineDispatcher,
    @Suppress("UNUSED_PARAMETER") constructorMarker: Unit,
) : AutoCloseable {
    public constructor(
        state: StateFlow<*>,
        onValue: (Any?) -> Unit,
    ) : this(state, onValue, Dispatchers.Main.immediate, Unit)

    internal constructor(
        state: StateFlow<*>,
        onValue: (Any?) -> Unit,
        deliveryDispatcher: CoroutineDispatcher,
    ) : this(state, onValue, deliveryDispatcher, Unit)

    private val deliveryLock = NSRecursiveLock()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var closed = false

    init {
        scope.launch(start = CoroutineStart.UNDISPATCHED) {
            state.collect { value ->
                withContext(deliveryDispatcher) {
                    deliveryLock.lock()
                    try {
                        if (!closed) {
                            try {
                                onValue(value)
                            } catch (_: Throwable) {
                                closeLocked()
                            }
                        }
                    } finally {
                        deliveryLock.unlock()
                    }
                }
            }
        }
    }

    /** Stops delivering values. Safe to call more than once. */
    override fun close() {
        deliveryLock.lock()
        try {
            closeLocked()
        } finally {
            deliveryLock.unlock()
        }
    }

    private fun closeLocked() {
        if (closed) return
        closed = true
        scope.cancel()
    }
}
