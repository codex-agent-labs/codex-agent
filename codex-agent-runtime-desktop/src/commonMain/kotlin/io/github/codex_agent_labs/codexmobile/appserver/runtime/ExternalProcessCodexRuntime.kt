@file:OptIn(kotlin.concurrent.atomics.ExperimentalAtomicApi::class)

package io.github.codex_agent_labs.codexmobile.appserver.runtime

import kotlin.concurrent.atomics.AtomicBoolean
import kotlin.concurrent.atomics.AtomicReference
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.selects.select
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

internal interface ExternalHostProcess {
    suspend fun collectStdout(emit: suspend (ByteArray, Int) -> Unit)
    suspend fun drainStderr()
    suspend fun awaitExit(): Int
    suspend fun write(line: String)
    fun close()
}

internal class ExternalProcessCodexRuntime(
    dispatcher: CoroutineDispatcher = Dispatchers.Default,
    private val launch: suspend () -> ExternalHostProcess,
) : CodexRuntime {
    private val scope = CoroutineScope(SupervisorJob() + dispatcher)
    private val eventChannel = Channel<CodexRuntimeEvent>(EVENT_BUFFER_SIZE)
    private val sendMutex = Mutex()
    private val state = AtomicReference<State>(State.New)
    private val finished = AtomicBoolean(false)

    override val events: Flow<CodexRuntimeEvent> = eventChannel.receiveAsFlow()

    override suspend fun start() {
        check(state.compareAndSet(State.New, State.Starting)) {
            if (state.load() === State.Closed) "Codex runtime is closed"
            else "Codex runtime was already started"
        }
        val pending = scope.async { launch() }
        val process = try {
            pending.await()
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            state.compareAndSet(State.Starting, State.Closed)
            scope.launch {
                val acquired = runCatching { pending.await() }.getOrNull()
                if (acquired == null) finishClose() else stopAcquired(Session(acquired))
            }
            throw cancelled
        } catch (error: Throwable) {
            if (state.compareAndSet(State.Starting, State.Closed)) {
                eventChannel.trySend(CodexRuntimeEvent.StartFailure(error.visibleMessage()))
            }
            finishClose()
            throw error
        }
        val session = Session(process)
        if (!state.compareAndSet(State.Starting, State.Running(session))) {
            stopAcquired(session)
            error("Codex runtime is closed")
        }
        watch(session)
    }

    override suspend fun send(line: CodexJsonLine) = sendMutex.withLock {
        val running = state.load() as? State.Running
        check(running != null) { "Codex App Server is not running" }
        try {
            running.session.process.write(line.value + '\n')
        } catch (cancelled: kotlinx.coroutines.CancellationException) {
            throw cancelled
        } catch (error: Throwable) {
            emit(running.session, CodexRuntimeEvent.IoFailure(error.visibleMessage()))
            throw error
        }
    }

    override fun close() {
        when (val previous = state.exchange(State.Closed)) {
            State.Closed -> return
            State.New -> finishClose()
            State.Starting -> Unit
            is State.Running -> previous.session.stop()
            is State.Exiting -> previous.session.stop()
        }
    }

    private fun watch(session: Session) {
        val stdoutJob = scope.launch(start = CoroutineStart.LAZY) {
            try {
                val framer = JsonLineFramer()
                session.process.collectStdout { bytes, count ->
                    framer.accept(bytes, count) { line ->
                        emit(session, CodexRuntimeEvent.Received(CodexJsonLine(line)))
                    }
                }
                framer.finish { line ->
                    emit(session, CodexRuntimeEvent.Received(CodexJsonLine(line)))
                }
                emit(session, CodexRuntimeEvent.EndOfFile)
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                emit(session, CodexRuntimeEvent.IoFailure(error.visibleMessage()))
            }
        }
        session.attachStdout(stdoutJob)
        stdoutJob.start()
        scope.launch {
            try {
                session.process.drainStderr()
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                emit(session, CodexRuntimeEvent.IoFailure(error.visibleMessage()))
            }
        }
        scope.launch {
            val exit = try {
                Exit(session.process.awaitExit(), null)
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (error: Throwable) {
                Exit(-1, error)
            }
            val exiting = beginExit(session)
            if (exiting != null && exit.failure != null) {
                emit(session, CodexRuntimeEvent.IoFailure(exit.failure.visibleMessage()))
                session.closeProcess()
            }
            stdoutJob.join()
            session.closeProcess()
            if (exiting != null && state.compareAndSet(exiting, State.Closed)) {
                session.stopEvents()
                eventChannel.send(CodexRuntimeEvent.Exited(exit.code))
            }
            finishClose()
        }
    }

    private fun stopAcquired(session: Session) {
        session.stop()
        finishClose()
    }

    private fun beginExit(session: Session): State.Exiting? {
        while (true) {
            when (val current = state.load()) {
                is State.Running -> {
                    if (current.session !== session) return null
                    val exiting = State.Exiting(session)
                    if (state.compareAndSet(current, exiting)) return exiting
                }
                is State.Exiting -> return current.takeIf { it.session === session }
                State.New, State.Starting, State.Closed -> return null
            }
        }
    }

    private suspend fun emit(session: Session, event: CodexRuntimeEvent) {
        if (!owns(session)) return
        select {
            session.eventsStopped.onAwait {}
            eventChannel.onSend(event) {}
        }
    }

    private fun owns(session: Session): Boolean = when (val current = state.load()) {
        is State.Running -> current.session === session
        is State.Exiting -> current.session === session
        State.New, State.Starting, State.Closed -> false
    }

    private fun finishClose() {
        if (!finished.compareAndSet(false, true)) return
        eventChannel.close()
        scope.cancel()
    }

    private inner class Session(val process: ExternalHostProcess) {
        val eventsStopped = CompletableDeferred<Unit>()
        private val stdoutJob = AtomicReference<Job?>(null)
        private val processClosed = AtomicBoolean(false)

        fun attachStdout(job: Job) {
            check(stdoutJob.compareAndSet(null, job))
            if (eventsStopped.isCompleted) job.cancel()
        }

        fun stop() {
            stopEvents()
            closeProcess()
        }

        fun stopEvents() {
            eventsStopped.complete(Unit)
            stdoutJob.load()?.cancel()
        }

        fun closeProcess() {
            if (processClosed.compareAndSet(false, true)) runCatching { process.close() }
        }
    }

    private sealed interface State {
        data object New : State
        data object Starting : State
        data object Closed : State
        class Running(val session: Session) : State
        class Exiting(val session: Session) : State
    }

    private data class Exit(val code: Int, val failure: Throwable?)

    private fun Throwable.visibleMessage(): String =
        message?.take(MAX_FAILURE_MESSAGE_LENGTH)?.takeIf(String::isNotBlank) ?: this::class.simpleName ?: "Codex failure"

    private companion object {
        const val EVENT_BUFFER_SIZE = 64
        const val MAX_FAILURE_MESSAGE_LENGTH = 500
    }
}
