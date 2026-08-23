package io.github.codex_agent_labs.codexmobile.agent

import kotlin.random.Random
import okio.FileSystem
import okio.Path

internal interface AgentFileStore {
    fun metadata(path: Path): AgentFileMetadata?

    fun list(path: Path): List<Path>

    fun canonicalize(path: Path): Path

    fun isRegularFile(path: Path): Boolean

    fun readUtf8(path: Path): String

    fun size(path: Path): Long?

    fun readBytes(path: Path, offset: Long, byteCount: Int): ByteArray

    fun readBytes(path: Path): ByteArray

    fun writeUtf8Atomically(path: Path, value: String)

    fun writeBytesAtomically(path: Path, value: ByteArray)

    fun createDirectories(path: Path)

    fun atomicMove(source: Path, target: Path)

    fun delete(path: Path)

    fun deleteRecursively(path: Path)

    fun clearDirectory(path: Path)
}

internal data class AgentFileMetadata(
    val isRegularFile: Boolean,
    val isDirectory: Boolean,
    val isSymbolicLink: Boolean,
)

internal expect val systemAgentFileStore: AgentFileStore

internal fun FileSystem.asAgentFileStore(): AgentFileStore = OkioAgentFileStore(this)

private class OkioAgentFileStore(
    private val fileSystem: FileSystem,
) : AgentFileStore {
    override fun metadata(path: Path): AgentFileMetadata? = fileSystem.metadataOrNull(path)?.let {
        AgentFileMetadata(it.isRegularFile, it.isDirectory, it.symlinkTarget != null)
    }

    override fun list(path: Path): List<Path> = fileSystem.list(path)

    override fun canonicalize(path: Path): Path = fileSystem.canonicalize(path)

    override fun isRegularFile(path: Path): Boolean =
        fileSystem.metadataOrNull(path)?.isRegularFile == true

    override fun readUtf8(path: Path): String = fileSystem.read(path) {
        readByteArray().decodeToString(throwOnInvalidSequence = true)
    }

    override fun size(path: Path): Long? =
        fileSystem.metadataOrNull(path)?.takeIf { it.isRegularFile }?.size

    override fun readBytes(path: Path, offset: Long, byteCount: Int): ByteArray =
        fileSystem.read(path) {
            skip(offset)
            readByteArray(byteCount.toLong())
        }

    override fun readBytes(path: Path): ByteArray = fileSystem.read(path) { readByteArray() }

    override fun writeUtf8Atomically(path: Path, value: String) {
        writeBytesAtomically(path, value.encodeToByteArray())
    }

    override fun writeBytesAtomically(path: Path, value: ByteArray) {
        val parent = checkNotNull(path.parent) { "A persisted file must have a parent directory" }
        fileSystem.createDirectories(parent)
        val next = parent / ".${path.name}.next-${Random.nextLong().toULong()}"
        try {
            fileSystem.write(next) { write(value) }
            fileSystem.atomicMove(next, path)
        } catch (error: Throwable) {
            runCatching { fileSystem.delete(next) }
            throw error
        }
    }

    override fun createDirectories(path: Path) = fileSystem.createDirectories(path)

    override fun atomicMove(source: Path, target: Path) = fileSystem.atomicMove(source, target)

    override fun delete(path: Path) {
        fileSystem.delete(path, mustExist = false)
    }

    override fun deleteRecursively(path: Path) {
        fileSystem.deleteRecursively(path, mustExist = false)
    }

    override fun clearDirectory(path: Path) {
        fileSystem.listOrNull(path).orEmpty().forEach { fileSystem.delete(it, mustExist = false) }
    }
}
