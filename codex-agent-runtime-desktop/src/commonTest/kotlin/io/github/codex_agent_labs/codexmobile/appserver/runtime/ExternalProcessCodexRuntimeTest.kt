package io.github.codex_agent_labs.codexmobile.appserver.runtime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest

@OptIn(ExperimentalCoroutinesApi::class)
class ExternalProcessCodexRuntimeTest {
    @Test
    fun emitsFramedOutputBeforeEofAndExitThenRejectsWrites() = runTest {
        val process = FakeExternalHostProcess()
        val runtime = runtime(process)
        val events = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            runtime.events.toList()
        }

        runtime.start()
        process.output.send("{\"value\":".encodeToByteArray())
        process.output.send("1}\n{}\n".encodeToByteArray())
        process.completion.complete(7)
        advanceUntilIdle()
        assertFalse(events.isCompleted, "Process exit overtook open stdout")
        process.output.close()
        advanceUntilIdle()

        assertEquals(
            listOf(
                CodexRuntimeEvent.Received(CodexJsonLine("{\"value\":1}")),
                CodexRuntimeEvent.Received(CodexJsonLine("{}")),
                CodexRuntimeEvent.EndOfFile,
                CodexRuntimeEvent.Exited(7),
            ),
            events.await(),
        )
        assertIs<IllegalStateException>(runCatching { runtime.send(CodexJsonLine("{}")) }.exceptionOrNull())
        runtime.close()
        assertEquals(1, process.closeCount)
    }

    @Test
    fun serializesNewlineTerminatedWrites() = runTest {
        val entered = Channel<Unit>(2)
        val release = Channel<Unit>(2)
        val writes = mutableListOf<String>()
        var activeWrites = 0
        var maximumActiveWrites = 0
        val process = FakeExternalHostProcess { line ->
            activeWrites++
            maximumActiveWrites = maxOf(maximumActiveWrites, activeWrites)
            entered.send(Unit)
            release.receive()
            writes += line
            activeWrites--
        }
        val runtime = runtime(process)
        runtime.start()

        val first = async { runtime.send(CodexJsonLine("one")) }
        entered.receive()
        val second = async(start = CoroutineStart.UNDISPATCHED) { runtime.send(CodexJsonLine("two")) }
        advanceUntilIdle()
        assertFalse(second.isCompleted)
        release.send(Unit)
        entered.receive()
        release.send(Unit)
        first.await()
        second.await()

        assertEquals(1, maximumActiveWrites)
        assertEquals(listOf("one\n", "two\n"), writes)
        runtime.close()
        assertEquals(1, process.closeCount)
        advanceUntilIdle()
    }

    @Test
    fun closeDuringStartOwnsAndClosesTheAcquiredProcessExactlyOnce() = runTest {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val process = FakeExternalHostProcess()
        val runtime = runtime {
            entered.complete(Unit)
            release.await()
            process
        }
        val events = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            runtime.events.toList()
        }
        val start = async { runCatching { runtime.start() }.exceptionOrNull() }

        entered.await()
        runtime.close()
        runtime.close()
        release.complete(Unit)
        advanceUntilIdle()

        assertIs<IllegalStateException>(start.await())
        assertEquals(1, process.closeCount)
        assertEquals(0, process.collectCalls + process.drainCalls + process.awaitCalls)
        assertTrue(events.await().isEmpty())
    }

    @Test
    fun launchAndSendCancellationEmitNoFailureEventsAndReleaseOwnership() = runTest {
        val launchEntered = CompletableDeferred<Unit>()
        val releaseLaunch = CompletableDeferred<Unit>()
        val launchProcess = FakeExternalHostProcess()
        val launchingRuntime = runtime {
            launchEntered.complete(Unit)
            releaseLaunch.await()
            launchProcess
        }
        val launchEvents = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            launchingRuntime.events.toList()
        }
        val start = async { launchingRuntime.start() }

        launchEntered.await()
        start.cancelAndJoin()
        releaseLaunch.complete(Unit)
        advanceUntilIdle()

        assertEquals(1, launchProcess.closeCount)
        assertTrue(launchEvents.await().isEmpty())

        val writeEntered = CompletableDeferred<Unit>()
        val writeProcess = FakeExternalHostProcess {
            writeEntered.complete(Unit)
            awaitCancellation()
        }
        val writingRuntime = runtime(writeProcess)
        val writeEvents = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            writingRuntime.events.toList()
        }
        writingRuntime.start()
        val send = async { writingRuntime.send(CodexJsonLine("{}")) }
        writeEntered.await()
        send.cancelAndJoin()
        writingRuntime.close()
        advanceUntilIdle()

        assertTrue(writeEvents.await().none { it is CodexRuntimeEvent.IoFailure })
        assertEquals(1, writeProcess.closeCount)
    }

    @Test
    fun startAndWriteFailuresAreVisible() = runTest {
        val startRuntime = runtime {
            throw IllegalStateException("launch failed")
        }
        val startEvents = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            startRuntime.events.toList()
        }
        assertIs<IllegalStateException>(runCatching { startRuntime.start() }.exceptionOrNull())
        advanceUntilIdle()
        assertEquals(listOf(CodexRuntimeEvent.StartFailure("launch failed")), startEvents.await())

        val process = FakeExternalHostProcess { throw IllegalStateException("write failed") }
        val runtime = runtime(process)
        val events = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            runtime.events.toList()
        }
        runtime.start()
        assertIs<IllegalStateException>(runCatching { runtime.send(CodexJsonLine("{}")) }.exceptionOrNull())
        process.exit(0)
        advanceUntilIdle()

        assertTrue(events.await().any { it == CodexRuntimeEvent.IoFailure("write failed") })
    }

    @Test
    fun completionFailureIsBoundedAndClosesWithSyntheticExit() = runTest {
        val process = FakeExternalHostProcess()
        val runtime = runtime(process)
        val events = backgroundScope.async(UnconfinedTestDispatcher(testScheduler)) {
            runtime.events.toList()
        }
        runtime.start()
        process.output.close()
        process.completion.completeExceptionally(IllegalStateException("x".repeat(600)))
        advanceUntilIdle()

        val actual = events.await()
        assertEquals(500, assertIs<CodexRuntimeEvent.IoFailure>(actual.first { it is CodexRuntimeEvent.IoFailure }).message.length)
        val eofIndex = actual.indexOf(CodexRuntimeEvent.EndOfFile)
        assertTrue(eofIndex >= 0)
        assertTrue(eofIndex < actual.indexOf(CodexRuntimeEvent.Exited(-1)))
        assertEquals(CodexRuntimeEvent.Exited(-1), actual.last())
        assertEquals(1, process.closeCount)
    }

    private fun kotlinx.coroutines.test.TestScope.runtime(
        process: FakeExternalHostProcess,
    ): CodexRuntime = runtime { process }

    private fun kotlinx.coroutines.test.TestScope.runtime(
        launch: suspend () -> ExternalHostProcess,
    ): CodexRuntime = ExternalProcessCodexRuntime(StandardTestDispatcher(testScheduler), launch)
}

private class FakeExternalHostProcess(
    private val writeAction: suspend (String) -> Unit = {},
) : ExternalHostProcess {
    val output = Channel<ByteArray>(Channel.UNLIMITED)
    val completion = CompletableDeferred<Int>()
    var closeCount = 0
    var collectCalls = 0
    var drainCalls = 0
    var awaitCalls = 0

    override suspend fun collectStdout(emit: suspend (ByteArray, Int) -> Unit) {
        collectCalls++
        for (bytes in output) emit(bytes, bytes.size)
    }

    override suspend fun drainStderr() { drainCalls++ }
    override suspend fun awaitExit(): Int {
        awaitCalls++
        return completion.await()
    }
    override suspend fun write(line: String): Unit = writeAction(line)

    override fun close() {
        closeCount++
        output.close()
        completion.complete(0)
    }

    fun exit(code: Int) {
        output.close()
        completion.complete(code)
    }
}
