@file:OptIn(
    kotlin.concurrent.atomics.ExperimentalAtomicApi::class,
    kotlinx.cinterop.ExperimentalForeignApi::class,
)

package io.github.codex_agent_labs.codexmobile.capi

import io.github.codex_agent_labs.codexmobile.agent.CodexHostState
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_client_info
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_host_options
import io.github.codex_agent_labs.codexmobile.capi.headers.codex_agent_string_view
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertSame
import kotlinx.cinterop.ByteVar
import kotlinx.cinterop.COpaquePointer
import kotlinx.cinterop.COpaquePointerVar
import kotlinx.cinterop.CPointer
import kotlinx.cinterop.IntVar
import kotlinx.cinterop.MemScope
import kotlinx.cinterop.UByteVar
import kotlinx.cinterop.alloc
import kotlinx.cinterop.allocArray
import kotlinx.cinterop.get
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.pointed
import kotlinx.cinterop.ptr
import kotlinx.cinterop.set
import kotlinx.cinterop.sizeOf
import kotlinx.cinterop.value
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield

class CodexAgentCHostFactoryTest {
    @Test
    fun rejectsInvalidFactoryInputsWithoutChangingOutput() = memScoped {
        val contextSlot = createHostFactoryContext()
        val context = assertNotNull(contextSlot.value)
        val valid = hostOptions()

        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHostCreate(context, valid.pointer, null),
        )

        val sentinel = alloc<ByteVar>().ptr
        val output = alloc<COpaquePointerVar>().also { it.value = sentinel }
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHostCreate(context, valid.pointer, output.ptr),
        )
        assertEquals(sentinel, output.value)

        output.value = null
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHostCreate(null, valid.pointer, output.ptr),
        )
        assertNull(output.value)
        assertEquals(
            CODEX_AGENT_STATUS_INVALID_ARGUMENT,
            codexAgentHostCreate(context, null, output.ptr),
        )
        assertNull(output.value)

        val undersizedOptions = hostOptions()
        undersizedOptions.pointer.pointed.struct_size =
            (sizeOf<codex_agent_host_options>() - 1).toUInt()
        assertCreateRejected(context, undersizedOptions.pointer, output)

        val undersizedClientInfo = hostOptions()
        undersizedClientInfo.pointer.pointed.client_info.struct_size =
            undersizedClientInfo.pointer.pointed.client_info.struct_size - 1u
        assertCreateRejected(context, undersizedClientInfo.pointer, output)

        val absentDirectory = hostOptions()
        absentDirectory.pointer.pointed.bundle_directory.data = null
        absentDirectory.pointer.pointed.bundle_directory.size = 1uL
        assertCreateRejected(context, absentDirectory.pointer, output)

        val invalidDirectoryUtf8 = hostOptions()
        writeInvalidUtf8(invalidDirectoryUtf8.pointer.pointed.data_directory)
        assertCreateRejected(context, invalidDirectoryUtf8.pointer, output)

        val invalidClientUtf8 = hostOptions()
        writeInvalidUtf8(invalidClientUtf8.pointer.pointed.client_info.name)
        assertCreateRejected(context, invalidClientUtf8.pointer, output)

        val invalidClientValue = hostOptions(clientTitle = " \t")
        assertCreateRejected(context, invalidClientValue.pointer, output)

        val staleContextSlot = createHostFactoryContext()
        val staleContext = assertNotNull(staleContextSlot.value)
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(staleContextSlot.ptr))
        assertNull(staleContextSlot.value)
        assertEquals(
            CODEX_AGENT_STATUS_STALE_HANDLE,
            codexAgentHostCreate(staleContext, valid.pointer, output.ptr),
        )
        assertNull(output.value)

        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
        assertNull(contextSlot.value)
    }

    @Test
    fun createsCopiedCanonicalHostWithOwnedRetainedAndClosedAliases(): Unit = runBlocking {
        memScoped {
            val contextSlot = createHostFactoryContext()
            val context = assertNotNull(contextSlot.value)
            val options = hostOptions(
                bundleDirectory = "/tmp/codex-bundle-α",
                dataDirectory = "/tmp/codex-data-β",
                clientName = "códex-agent",
                clientTitle = "Cliente π",
                clientVersion = "2026.8-β",
            )
            val hostSlot = alloc<COpaquePointerVar>().also { it.value = null }

            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostCreate(context, options.pointer, hostSlot.ptr),
            )
            val host = assertNotNull(hostSlot.value)

            // The C caller may reuse every input byte as soon as create returns.
            options.poison()
            val contextLease = assertNotNull(handleRegistry.acquireContext(context).value)
            val runtime = assertNotNull(contextLease.payload as? CodexAgentCContextRuntime)
            val hostLease = assertNotNull(
                handleRegistry.acquire(context, host, CodexAgentCHandleKind.HOST).value,
            )
            val wrapper = assertNotNull(hostLease.payload as? CodexAgentCHost)
            assertSame(runtime, wrapper.runtime)
            assertEquals(CodexHostState.New, wrapper.core.lifecycleState.value)
            assertEquals(CODEX_AGENT_STATUS_OK, hostLease.close())
            assertEquals(CODEX_AGENT_STATUS_OK, contextLease.close())

            val aliasSlot = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRetain(context, host, aliasSlot.ptr))
            val alias = assertNotNull(aliasSlot.value)
            assertNotEquals(host, alias)

            val secondContextSlot = createHostFactoryContext()
            val secondContext = assertNotNull(secondContextSlot.value)
            val wrongContextOutput = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentHostRetain(secondContext, alias, wrongContextOutput.ptr),
            )
            assertNull(wrongContextOutput.value)
            val wrongContextRelease = alloc<COpaquePointerVar>().also { it.value = alias }
            assertEquals(
                CODEX_AGENT_STATUS_WRONG_CONTEXT,
                codexAgentHostRelease(secondContext, wrongContextRelease.ptr),
            )
            assertEquals(alias, wrongContextRelease.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(secondContextSlot.ptr))

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, hostSlot.ptr))
            assertNull(hostSlot.value)
            val staleOutput = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_STALE_HANDLE,
                codexAgentHostRetain(context, host, staleOutput.ptr),
            )
            assertNull(staleOutput.value)

            assertEquals(CODEX_AGENT_STATUS_BUSY, codexAgentHostRelease(context, aliasSlot.ptr))
            assertEquals(alias, aliasSlot.value)

            val closeOperation = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                codexAgentHostClose(context, alias, null, null, closeOperation.ptr),
            )
            assertEquals(
                CODEX_AGENT_STATUS_OK,
                awaitHostFactoryOperation(context, assertNotNull(closeOperation.value)),
            )
            assertClosedHostFactoryState(context, alias)
            destroyHostFactoryOperation(context, closeOperation.ptr)

            val closedOutput = alloc<COpaquePointerVar>().also { it.value = null }
            assertEquals(
                CODEX_AGENT_STATUS_CLOSED,
                codexAgentHostRetain(context, alias, closedOutput.ptr),
            )
            assertNull(closedOutput.value)

            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostRelease(context, aliasSlot.ptr))
            assertNull(aliasSlot.value)
            assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextDestroy(contextSlot.ptr))
            assertNull(contextSlot.value)
        }
    }
}

private fun MemScope.createHostFactoryContext(): COpaquePointerVar =
    alloc<COpaquePointerVar>().also {
        it.value = null
        assertEquals(CODEX_AGENT_STATUS_OK, codexAgentContextCreate(it.ptr))
    }

private fun MemScope.assertCreateRejected(
    context: COpaquePointer,
    options: CPointer<codex_agent_host_options>,
    output: COpaquePointerVar,
) {
    assertNull(output.value)
    assertEquals(
        CODEX_AGENT_STATUS_INVALID_ARGUMENT,
        codexAgentHostCreate(context, options, output.ptr),
    )
    assertNull(output.value)
}

private fun MemScope.hostOptions(
    bundleDirectory: String = "/tmp/codex-bundle",
    dataDirectory: String = "/tmp/codex-data",
    clientName: String = "codex-agent",
    clientTitle: String = "Codex Agent",
    clientVersion: String = "2026.8",
): HostFactoryOptions {
    val buffers = mutableListOf<HostFactoryBuffer>()
    val options = alloc<codex_agent_host_options>()
    options.struct_size = sizeOf<codex_agent_host_options>().toUInt()
    writeHostFactoryUtf8(options.bundle_directory, bundleDirectory, buffers)
    writeHostFactoryUtf8(options.data_directory, dataDirectory, buffers)
    options.client_info.struct_size = sizeOf<codex_agent_client_info>().toUInt()
    writeHostFactoryUtf8(options.client_info.name, clientName, buffers)
    writeHostFactoryUtf8(options.client_info.title, clientTitle, buffers)
    writeHostFactoryUtf8(options.client_info.version, clientVersion, buffers)
    return HostFactoryOptions(options.ptr, buffers)
}

private fun MemScope.writeHostFactoryUtf8(
    target: codex_agent_string_view,
    value: String,
    buffers: MutableList<HostFactoryBuffer>,
) {
    val bytes = value.encodeToByteArray()
    val buffer = allocArray<UByteVar>(bytes.size)
    bytes.forEachIndexed { index, byte -> buffer[index] = byte.toUByte() }
    target.data = buffer
    target.size = bytes.size.toULong()
    buffers += HostFactoryBuffer(buffer, bytes.size)
}

private fun MemScope.writeInvalidUtf8(target: codex_agent_string_view) {
    val buffer = allocArray<UByteVar>(2)
    buffer[0] = 0xc3u
    buffer[1] = 0x28u
    target.data = buffer
    target.size = 2uL
}

private suspend fun awaitHostFactoryOperation(
    context: COpaquePointer,
    operation: COpaquePointer,
): Int = withTimeout(HOST_FACTORY_TIMEOUT_MILLIS) {
    memScoped {
        val result = alloc<IntVar>()
        while (true) {
            when (val status = codexAgentOperationResult(context, operation, result.ptr)) {
                CODEX_AGENT_STATUS_NOT_READY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout result.value
                else -> error("operation result query failed with $status")
            }
        }
        error("unreachable")
    }
}

private suspend fun destroyHostFactoryOperation(
    context: COpaquePointer,
    operation: CPointer<COpaquePointerVar>,
) {
    withTimeout(HOST_FACTORY_TIMEOUT_MILLIS) {
        while (true) {
            when (val status = codexAgentOperationDestroy(context, operation)) {
                CODEX_AGENT_STATUS_BUSY -> yield()
                CODEX_AGENT_STATUS_OK -> return@withTimeout
                else -> error("operation destroy failed with $status")
            }
        }
    }
    assertNull(operation.pointed.value)
}

private fun assertClosedHostFactoryState(context: COpaquePointer, host: COpaquePointer) = memScoped {
    val snapshot = alloc<COpaquePointerVar>().also { it.value = null }
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentHostStateGet(context, host, snapshot.ptr))
    val kind = alloc<IntVar>()
    assertEquals(
        CODEX_AGENT_STATUS_OK,
        codexAgentHostStateKind(context, assertNotNull(snapshot.value), kind.ptr),
    )
    assertEquals(HOST_FACTORY_STATE_CLOSED, kind.value)
    assertEquals(CODEX_AGENT_STATUS_OK, codexAgentSnapshotDestroy(context, snapshot.ptr))
    assertNull(snapshot.value)
}

private data class HostFactoryOptions(
    val pointer: CPointer<codex_agent_host_options>,
    private val buffers: List<HostFactoryBuffer>,
) {
    fun poison() {
        buffers.forEach(HostFactoryBuffer::poison)
    }
}

private data class HostFactoryBuffer(
    private val pointer: CPointer<UByteVar>,
    private val size: Int,
) {
    fun poison() {
        repeat(size) { pointer[it] = 0xffu }
    }
}

private const val HOST_FACTORY_STATE_CLOSED = 6
private const val HOST_FACTORY_TIMEOUT_MILLIS = 5_000L
