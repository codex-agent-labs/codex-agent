package io.github.codex_agent_labs.codexmobile.appserver.runtime

import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotSame
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import okio.Path.Companion.toPath

class JvmDesktopLifecycleOrderingTest {
    @Test
    fun `blocking process IO uses the elastic dispatcher`() {
        assertSame(Dispatchers.IO, desktopProcessDispatcher)
    }

    @Test
    fun `blocking writes leave the caller thread`(): Unit = runBlocking {
        val process = RecordingWriteProcess()
        val runtime = DesktopCodexRuntimeFactory(
            DesktopCodexRuntimeConfiguration(
                "unused".toPath(), "unused".toPath(), "0".repeat(64), "unused".toPath(),
            ),
            startProcess = { process },
        ).create()
        try {
            runtime.start()
            val caller = Thread.currentThread()
            runtime.send(CodexJsonLine("{}"))
            assertNotSame(caller, process.writeThread)
        } finally {
            runtime.close()
        }
    }

    @Test
    fun `exit waits for stdout to drain`(): Unit = runBlocking {
        val process = BlockingStdoutProcess()
        val runtime = DesktopCodexRuntimeFactory(
            DesktopCodexRuntimeConfiguration(
                "unused".toPath(), "unused".toPath(), "0".repeat(64), "unused".toPath(),
            ),
            startProcess = { process },
        ).create()
        val firstEvent = async { runtime.events.first() }
        try {
            runtime.start()
            assertTrue(process.stdoutStarted.await(5, TimeUnit.SECONDS))
            assertTrue(process.exitObserved.await(5, TimeUnit.SECONDS))
            assertFalse(firstEvent.isCompleted, "Process exit overtook unread stdout")
            process.releaseStdout.countDown()
            assertIs<CodexRuntimeEvent.Received>(withTimeout(5_000) { firstEvent.await() })
        } finally {
            runtime.close()
        }
    }
}

private class RecordingWriteProcess : DesktopProcess {
    private val exit = CountDownLatch(1)
    var writeThread: Thread? = null

    override fun readStdout(buffer: ByteArray) = 0
    override fun readStderr(buffer: ByteArray) = 0
    override fun write(bytes: ByteArray) { writeThread = Thread.currentThread() }
    override fun waitForExit(): Int {
        exit.await()
        return 0
    }
    override fun close() { exit.countDown() }
}

private class BlockingStdoutProcess : DesktopProcess {
    val stdoutStarted = CountDownLatch(1)
    val exitObserved = CountDownLatch(1)
    val releaseStdout = CountDownLatch(1)
    private val firstRead = AtomicBoolean(true)

    override fun readStdout(buffer: ByteArray): Int {
        if (!firstRead.compareAndSet(true, false)) return 0
        stdoutStarted.countDown()
        check(releaseStdout.await(5, TimeUnit.SECONDS)) { "Timed out waiting to release stdout" }
        val line = "{}\n".encodeToByteArray()
        line.copyInto(buffer)
        return line.size
    }

    override fun readStderr(buffer: ByteArray) = 0
    override fun write(bytes: ByteArray) = Unit
    override fun waitForExit(): Int {
        exitObserved.countDown()
        return 0
    }
    override fun close() { releaseStdout.countDown() }
}
