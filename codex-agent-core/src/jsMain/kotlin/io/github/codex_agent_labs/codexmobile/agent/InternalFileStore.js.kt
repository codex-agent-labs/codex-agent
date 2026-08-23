package io.github.codex_agent_labs.codexmobile.agent

import kotlin.random.Random
import okio.Path
import okio.Path.Companion.toPath

internal actual val systemAgentFileStore: AgentFileStore = NodeAgentFileStore

private object NodeAgentFileStore : AgentFileStore {
    private val fs: dynamic = js("require('node:fs')")

    override fun metadata(path: Path): AgentFileMetadata? = runCatching {
        val value = fs.lstatSync(path.toString())
        AgentFileMetadata(
            isRegularFile = value.isFile() as Boolean,
            isDirectory = value.isDirectory() as Boolean,
            isSymbolicLink = value.isSymbolicLink() as Boolean,
        )
    }.getOrNull()

    override fun list(path: Path): List<Path> =
        (fs.readdirSync(path.toString()) as Array<String>).map { path / it }

    override fun canonicalize(path: Path): Path = (fs.realpathSync(path.toString()) as String).toPath()

    override fun isRegularFile(path: Path): Boolean =
        runCatching { fs.statSync(path.toString()).isFile() as Boolean }.getOrDefault(false)

    override fun readUtf8(path: Path): String =
        fs.readFileSync(path.toString(), "utf8") as String

    override fun size(path: Path): Long? = runCatching {
        (fs.statSync(path.toString()).size as Number).toLong()
    }.getOrNull()

    override fun readBytes(path: Path, offset: Long, byteCount: Int): ByteArray {
        require(byteCount >= 0 && offset >= 0 && offset <= Int.MAX_VALUE.toLong() - byteCount)
        val bytes = fs.readFileSync(path.toString())
        return ByteArray(byteCount) { index ->
            (bytes[offset.toInt() + index] as Number).toByte()
        }
    }

    override fun readBytes(path: Path): ByteArray {
        val bytes = fs.readFileSync(path.toString())
        val size = (bytes.length as Number).toInt()
        return ByteArray(size) { index -> (bytes[index] as Number).toByte() }
    }

    override fun writeUtf8Atomically(path: Path, value: String) {
        val parent = checkNotNull(path.parent) { "A persisted file must have a parent directory" }
        val next = parent / ".${path.name}.next-${Random.nextLong().toULong()}"
        fs.mkdirSync(parent.toString(), js("({ recursive: true })"))
        try {
            fs.writeFileSync(next.toString(), value, "utf8")
            fs.renameSync(next.toString(), path.toString())
        } catch (error: Throwable) {
            runCatching { fs.rmSync(next.toString(), js("({ force: true })")) }
            throw error
        }
    }

    override fun writeBytesAtomically(path: Path, value: ByteArray) {
        val parent = checkNotNull(path.parent) { "A persisted file must have a parent directory" }
        val next = parent / ".${path.name}.next-${Random.nextLong().toULong()}"
        fs.mkdirSync(parent.toString(), js("({ recursive: true })"))
        try {
            fs.writeFileSync(next.toString(), value)
            fs.renameSync(next.toString(), path.toString())
        } catch (error: Throwable) {
            runCatching { fs.rmSync(next.toString(), js("({ force: true })")) }
            throw error
        }
    }

    override fun createDirectories(path: Path) {
        fs.mkdirSync(path.toString(), js("({ recursive: true })"))
    }

    override fun atomicMove(source: Path, target: Path) {
        fs.renameSync(source.toString(), target.toString())
    }

    override fun delete(path: Path) {
        fs.rmSync(path.toString(), js("({ force: true })"))
    }

    override fun deleteRecursively(path: Path) {
        fs.rmSync(path.toString(), js("({ recursive: true, force: true })"))
    }

    override fun clearDirectory(path: Path) {
        fs.rmSync(path.toString(), js("({ recursive: true, force: true })"))
    }
}
