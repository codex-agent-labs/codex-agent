package io.github.codex_agent_labs.codexmobile.appserver.runtime.host

import io.github.codex_agent_labs.codexmobile.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking

class SharedInstallerLockTest {
    @Test
    fun twoInstallerInstancesShareTheSameTransactionLock() = runBlocking {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        files.beforeFirstDataMutation = {
            entered.countDown()
            check(release.await(10, TimeUnit.SECONDS)) { "Timed out releasing installer mutation" }
        }
        val first = async(Dispatchers.Default) {
            SharedRuntimeBundleInstaller("/bundle", "/data", descriptor, files).install()
        }
        assertTrue(entered.await(10, TimeUnit.SECONDS), "Timed out entering installer mutation")
        val operationsWhileFirstOwnsLock = files.operations
        val second = async(start = CoroutineStart.UNDISPATCHED) {
            SharedRuntimeBundleInstaller("/bundle", "/data", descriptor, files).install()
        }
        try {
            assertEquals(operationsWhileFirstOwnsLock, files.operations)
        } finally {
            release.countDown()
        }

        val results = listOf(first, second).awaitAll()
        assertEquals(results[0], results[1])
        assertEquals(1, files.promotions)
    }

    @Test
    fun cancelledInstallerWaiterNeverEntersTheTransaction() = runBlocking {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members)
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        files.beforeFirstDataMutation = {
            entered.countDown()
            check(release.await(10, TimeUnit.SECONDS)) { "Timed out releasing installer mutation" }
        }
        val owner = async(Dispatchers.Default) {
            SharedRuntimeBundleInstaller("/bundle", "/data", descriptor, files).install()
        }
        assertTrue(entered.await(10, TimeUnit.SECONDS), "Timed out entering installer mutation")
        val operationsWhileOwnerHoldsLock = files.operations
        val waiter = async(start = CoroutineStart.UNDISPATCHED) {
            SharedRuntimeBundleInstaller("/bundle", "/data", descriptor, files).install()
        }
        try {
            assertEquals(operationsWhileOwnerHoldsLock, files.operations)
            waiter.cancelAndJoin()
            assertEquals(operationsWhileOwnerHoldsLock, files.operations)
        } finally {
            release.countDown()
        }
        owner.await()
        assertEquals(1, files.promotions)
    }

    @Test
    fun twoWorkspaceStoreInstancesShareTheSameStateLock() = runBlocking {
        val files = FakeHostFiles(ByteArray(22), emptyMap()).apply {
            directories += setOf("/data", "/workspace")
        }
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        files.beforeFirstDataMutation = {
            entered.countDown()
            check(release.await(10, TimeUnit.SECONDS)) { "Timed out releasing workspace mutation" }
        }
        val firstStore = SharedPathWorkspaceStore("/data", files)
        val secondStore = SharedPathWorkspaceStore("/data", files)
        val select = async(Dispatchers.Default) {
            firstStore.select(CodexPathWorkspaceSelection("/workspace"))
        }
        assertTrue(entered.await(10, TimeUnit.SECONDS), "Timed out entering workspace mutation")
        val operationsWhileFirstOwnsLock = files.operations
        val clear = async(start = CoroutineStart.UNDISPATCHED) { secondStore.clear() }
        try {
            assertEquals(operationsWhileFirstOwnsLock, files.operations)
        } finally {
            release.countDown()
        }
        assertIs<CodexWorkspaceResolution.Available>(select.await())
        clear.await()
        assertEquals(
            CodexWorkspaceSelectionReason.NOT_SELECTED,
            assertIs<CodexWorkspaceResolution.SelectionRequired>(firstStore.restore()).reason,
        )
    }
}
