@file:OptIn(kotlin.js.ExperimentalWasmJsInterop::class)

package io.github.codex_agent_labs.codexmobile.agent

import kotlin.js.JsAny
import kotlin.random.Random
import okio.Path
import okio.Path.Companion.toPath

internal actual val systemAgentFileStore: AgentFileStore = NodeAgentFileStore

private object NodeAgentFileStore : AgentFileStore {
    override fun metadata(path: Path): AgentFileMetadata? = runCatching {
        val value = nodeLstatSync(path.toString())
        AgentFileMetadata(value.isFile(), value.isDirectory(), value.isSymbolicLink())
    }.getOrNull()

    override fun list(path: Path): List<Path> {
        val values = nodeReadDirectorySync(path.toString())
        return List(nodeArrayLength(values)) { index -> path / nodeArrayString(values, index) }
    }

    override fun canonicalize(path: Path): Path = nodeRealPathSync(path.toString()).toPath()

    override fun isRegularFile(path: Path): Boolean =
        runCatching { nodeStatSync(path.toString()).isFile() }.getOrDefault(false)

    override fun readUtf8(path: Path): String = nodeReadFileSync(path.toString(), "utf8")

    override fun size(path: Path): Long? = runCatching {
        nodeStatSync(path.toString()).size.toLong()
    }.getOrNull()

    override fun readBytes(path: Path, offset: Long, byteCount: Int): ByteArray {
        require(byteCount >= 0 && offset >= 0 && offset <= Int.MAX_VALUE.toLong() - byteCount)
        val buffer = nodeReadBufferSync(path.toString())
        check(offset <= nodeBufferLength(buffer).toLong() - byteCount)
        return ByteArray(byteCount) { index -> nodeBufferByte(buffer, offset.toInt() + index).toByte() }
    }

    override fun readBytes(path: Path): ByteArray {
        val buffer = nodeReadBufferSync(path.toString())
        return ByteArray(nodeBufferLength(buffer)) { index -> nodeBufferByte(buffer, index).toByte() }
    }

    override fun writeUtf8Atomically(path: Path, value: String) {
        val parent = checkNotNull(path.parent) { "A persisted file must have a parent directory" }
        val next = parent / ".${path.name}.next-${Random.nextLong().toULong()}"
        nodeMkdirSync(parent.toString(), recursiveDirectoryOptions())
        try {
            nodeWriteFileSync(next.toString(), value, "utf8")
            nodeRenameSync(next.toString(), path.toString())
        } catch (error: Throwable) {
            runCatching { nodeRmSync(next.toString(), forceRemoveOptions()) }
            throw error
        }
    }

    override fun writeBytesAtomically(path: Path, value: ByteArray) {
        val parent = checkNotNull(path.parent) { "A persisted file must have a parent directory" }
        val next = parent / ".${path.name}.next-${Random.nextLong().toULong()}"
        nodeMkdirSync(parent.toString(), recursiveDirectoryOptions())
        try {
            nodeWriteBufferSync(next.toString(), value.toNodeBuffer())
            nodeRenameSync(next.toString(), path.toString())
        } catch (error: Throwable) {
            runCatching { nodeRmSync(next.toString(), forceRemoveOptions()) }
            throw error
        }
    }

    override fun createDirectories(path: Path) = nodeMkdirSync(path.toString(), recursiveDirectoryOptions())

    override fun atomicMove(source: Path, target: Path) =
        nodeRenameSync(source.toString(), target.toString())

    override fun delete(path: Path) {
        nodeRmSync(path.toString(), forceRemoveOptions())
    }

    override fun deleteRecursively(path: Path) {
        nodeRmSync(path.toString(), recursiveForceRemoveOptions())
    }

    override fun clearDirectory(path: Path) {
        nodeRmSync(path.toString(), recursiveForceRemoveOptions())
    }
}

@JsFun("() => ({ recursive: true })")
private external fun recursiveDirectoryOptions(): JsAny

@JsFun("() => ({ force: true })")
private external fun forceRemoveOptions(): JsAny

@JsFun("() => ({ recursive: true, force: true })")
private external fun recursiveForceRemoveOptions(): JsAny

private fun nodeBufferLength(value: JsAny): Int = js("value.length")

private fun nodeBufferByte(value: JsAny, index: Int): Int = js("value[index]")

private fun nodeArrayLength(value: JsAny): Int = js("value.length")

private fun nodeArrayString(value: JsAny, index: Int): String = js("value[index]")

private fun ByteArray.toNodeBuffer(): JsAny {
    val result = newNodeBuffer(size)
    indices.forEach { index -> setNodeBufferByte(result, index, this[index].toInt() and 0xff) }
    return result
}

@JsFun("size => new Uint8Array(size)")
private external fun newNodeBuffer(size: Int): JsAny

private fun setNodeBufferByte(value: JsAny, index: Int, byte: Int): Unit = js("value[index] = byte")
