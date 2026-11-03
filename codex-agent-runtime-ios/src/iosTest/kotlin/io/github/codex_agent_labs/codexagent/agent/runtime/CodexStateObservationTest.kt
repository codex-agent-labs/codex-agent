package io.github.codex_agent_labs.codexagent.agent.runtime

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue
import kotlinx.cinterop.ExperimentalForeignApi
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.DelicateCoroutinesApi
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.newSingleThreadContext
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.yield
import platform.CoreFoundation.CFRunLoopGetMain
import platform.CoreFoundation.CFRunLoopRunInMode
import platform.CoreFoundation.CFRunLoopStop
import platform.CoreFoundation.kCFRunLoopDefaultMode
import platform.Foundation.NSThread

class CodexStateObservationTest {
    @Test
    fun observesTheSubscriptionValueAndUpdatesExactlyOnce() = runBlocking {
        withSerialDelivery { deliveryDispatcher ->
            val state = MutableStateFlow("initial")
            val values = Channel<Any?>(Channel.UNLIMITED)
            val observation = observeForTest(state, deliveryDispatcher) { values.trySend(it) }

            assertEquals("initial", withTimeout(1_000) { values.receive() })
            state.value = "updated"
            assertEquals("updated", withTimeout(1_000) { values.receive() })

            observation.close()
            observation.close()
        }
    }

    @Test
    fun closeWaitsForAnInFlightCallbackAndPreventsLaterDelivery() = runBlocking {
        withSerialDelivery { deliveryDispatcher ->
            val state = MutableStateFlow("initial")
            val values = Channel<Any?>(Channel.UNLIMITED)
            val callbackEntered = Channel<Unit>(Channel.UNLIMITED)
            val releaseCallback = Channel<Unit>(Channel.UNLIMITED)
            val callbackExited = Channel<Unit>(Channel.UNLIMITED)
            val observation = observeForTest(state, deliveryDispatcher) { value ->
                if (value == "blocked") {
                    callbackEntered.trySend(Unit)
                    runBlocking { releaseCallback.receive() }
                    callbackExited.trySend(Unit)
                }
                values.trySend(value)
            }

            assertEquals("initial", withTimeout(1_000) { values.receive() })
            state.value = "blocked"
            withTimeout(1_000) { callbackEntered.receive() }

            val closeStarted = Channel<Unit>(Channel.UNLIMITED)
            val closeReturned = Channel<Unit>(Channel.UNLIMITED)
            val closeJob = launch(Dispatchers.Default) {
                closeStarted.send(Unit)
                observation.close()
                closeReturned.send(Unit)
            }
            withTimeout(1_000) { closeStarted.receive() }
            yield()
            assertTrue(closeReturned.tryReceive().isFailure)

            releaseCallback.send(Unit)
            withTimeout(1_000) { callbackExited.receive() }
            withTimeout(1_000) { closeReturned.receive() }
            closeJob.join()
            assertEquals("blocked", withTimeout(1_000) { values.receive() })

            state.value = "ignored"
            assertNull(withTimeoutOrNull(100) { values.receive() })
        }
    }

    @Test
    fun callbackCanCloseItsOwnObservation() = runBlocking {
        withSerialDelivery { deliveryDispatcher ->
            val state = MutableStateFlow("initial")
            val values = Channel<Any?>(Channel.UNLIMITED)
            lateinit var observation: CodexStateObservation
            observation = observeForTest(state, deliveryDispatcher) { value ->
                if (value == "close") observation.close()
                values.trySend(value)
            }

            assertEquals("initial", withTimeout(1_000) { values.receive() })
            state.value = "close"
            assertEquals("close", withTimeout(1_000) { values.receive() })
            observation.close()

            state.value = "ignored"
            assertNull(withTimeoutOrNull(100) { values.receive() })
        }
    }

    @Test
    fun callbackFailureClosesOnlyThatObservation() = runBlocking {
        withSerialDelivery { deliveryDispatcher ->
            val state = MutableStateFlow("initial")
            val failedValues = Channel<Any?>(Channel.UNLIMITED)
            val healthyValues = Channel<Any?>(Channel.UNLIMITED)
            val failedObservation = observeForTest(state, deliveryDispatcher) { value ->
                failedValues.trySend(value)
                if (value == "fail") error("expected callback failure")
            }
            val healthyObservation = observeForTest(state, deliveryDispatcher) { healthyValues.trySend(it) }

            assertEquals("initial", withTimeout(1_000) { failedValues.receive() })
            assertEquals("initial", withTimeout(1_000) { healthyValues.receive() })
            state.value = "fail"
            assertEquals("fail", withTimeout(1_000) { failedValues.receive() })
            assertEquals("fail", withTimeout(1_000) { healthyValues.receive() })
            state.value = "healthy"
            assertEquals("healthy", withTimeout(1_000) { healthyValues.receive() })
            assertNull(withTimeoutOrNull(100) { failedValues.receive() })

            failedObservation.close()
            healthyObservation.close()
        }
    }

    @Test
    @OptIn(ExperimentalForeignApi::class)
    fun publicObservationDeliversOnTheMainQueue() {
        val state = MutableStateFlow("initial")
        val mainQueue = Channel<Pair<Any?, Boolean>>(Channel.UNLIMITED)
        val observation = CodexStateObservation(state) { value ->
            mainQueue.trySend(value to NSThread.isMainThread)
            if (value == "background") CFRunLoopStop(CFRunLoopGetMain())
        }

        assertEquals("initial" to true, mainQueue.tryReceive().getOrNull())
        runBlocking(Dispatchers.Default) { state.value = "background" }
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 1.0, false)
        assertEquals("background" to true, mainQueue.tryReceive().getOrNull())
        observation.close()
    }
}

private fun observeForTest(
    state: MutableStateFlow<String>,
    deliveryDispatcher: CoroutineDispatcher,
    onValue: (Any?) -> Unit,
): CodexStateObservation = CodexStateObservation(state, onValue, deliveryDispatcher)

@OptIn(DelicateCoroutinesApi::class, ExperimentalCoroutinesApi::class)
private suspend fun withSerialDelivery(block: suspend (CoroutineDispatcher) -> Unit) {
    val dispatcher = newSingleThreadContext("CodexStateObservationTest")
    try {
        block(dispatcher)
    } finally {
        dispatcher.close()
    }
}
