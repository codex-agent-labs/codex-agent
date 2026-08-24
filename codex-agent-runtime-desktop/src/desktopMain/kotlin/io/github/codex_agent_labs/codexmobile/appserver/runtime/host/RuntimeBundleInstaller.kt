package io.github.codex_agent_labs.codexmobile.appserver.runtime.host

import io.github.codex_agent_labs.codexmobile.appserver.runtime.desktopFileSystem
import kotlin.random.Random
import okio.Buffer
import okio.FileSystem
import okio.HashingSource
import okio.Path
import okio.Path.Companion.toPath
import okio.Source
import okio.blackholeSink
import okio.buffer
import okio.openZip

internal class RuntimeBundleInstaller(
    bundleDirectory: Path,
    dataDirectory: Path,
    descriptor: RuntimeBundleDescriptor,
    fileSystem: FileSystem = desktopFileSystem,
    makeExecutable: (Path) -> Unit,
) {
    private val delegate = SharedRuntimeBundleInstaller(
        bundleDirectory.toString(),
        dataDirectory.toString(),
        descriptor,
        DesktopHostFiles(fileSystem, makeExecutable),
    )

    suspend fun install(): InstalledRuntime = delegate.install()
}

internal class DesktopHostFiles(
    private val fileSystem: FileSystem = desktopFileSystem,
    private val executable: (Path) -> Unit = {},
) : ExternalHostFiles {
    override fun isAbsolute(path: String): Boolean = path.toPath().isAbsolute
    override fun joinPath(parent: String, child: String): String = (parent.toPath() / child).toString()
    override fun baseName(path: String): String = path.toPath().name
    override fun canonicalize(path: String): String = fileSystem.canonicalize(path.toPath()).toString()
    override fun isCanonical(path: String): Boolean =
        runCatching { fileSystem.canonicalize(path.toPath()) == path.toPath() }.getOrDefault(false)

    override fun metadataOrNull(path: String): HostFileMetadata? =
        fileSystem.metadataOrNull(path.toPath())?.let { metadata ->
            HostFileMetadata(
                regularFile = metadata.isRegularFile,
                directory = metadata.isDirectory,
                symbolicLink = metadata.symlinkTarget != null,
                size = metadata.size ?: 0,
            )
        }

    override fun list(path: String): List<String> = fileSystem.list(path.toPath()).map(Path::name)
    override fun createDirectories(path: String): Unit = fileSystem.createDirectories(path.toPath())
    override fun createDirectory(path: String): Unit = fileSystem.createDirectory(path.toPath(), mustCreate = true)

    override fun readFileSnapshot(path: String, maxBytes: Long): ByteArray {
        // ponytail: the caller protects the canonical bundle root; add platform
        // no-follow handle opens if concurrently untrusted writers are supported.
        val before = metadataOrNull(path)
        require(before?.let { it.regularFile && !it.symbolicLink && it.size in 0..maxBytes } == true) {
            "File snapshot is unavailable"
        }
        val source = fileSystem.source(path.toPath())
        val bytes = closeAfter(source::close) { source.readBounded(maxBytes) }
        val after = metadataOrNull(path)
        require(after == before && bytes.size.toLong() == before.size) { "File changed while being read" }
        return bytes
    }

    override fun writeNewFile(path: String, bytes: ByteArray) {
        val sink = fileSystem.sink(path.toPath(), mustCreate = true).buffer()
        closeAfter(sink::close) { sink.write(bytes) }
    }

    override fun deleteFile(path: String): Unit = fileSystem.delete(path.toPath(), mustExist = false)
    override fun deleteRecursively(path: String): Unit =
        fileSystem.deleteRecursively(path.toPath(), mustExist = false)

    override fun move(source: String, destination: String): Unit =
        fileSystem.atomicMove(source.toPath(), destination.toPath())

    override fun atomicReplace(source: String, destination: String): Unit =
        fileSystem.atomicMove(source.toPath(), destination.toPath())

    override fun sha256(path: String): String {
        val hashing = HashingSource.sha256(fileSystem.source(path.toPath()))
        val source = hashing.buffer()
        closeAfter(source::close) { source.readAll(blackholeSink()) }
        return hashing.hash.hex()
    }

    override fun makeExecutable(path: String): Unit = executable(path.toPath())

    override fun openRuntimeArchive(
        bytes: ByteArray,
        members: List<RuntimeZipMember>,
    ): RuntimeArchive {
        val directory = FileSystem.SYSTEM_TEMPORARY_DIRECTORY /
            "codex-runtime-archive-${Random.nextLong().toString().replace('-', '0')}"
        fileSystem.createDirectory(directory, mustCreate = true)
        val snapshot = directory / "runtime.zip"
        return try {
            writeNewFile(snapshot.toString(), bytes)
            check(readFileSnapshot(snapshot.toString(), bytes.size.toLong()).contentEquals(bytes)) {
                "Runtime archive snapshot is corrupt"
            }
            DesktopRuntimeArchive(fileSystem, directory, snapshot, fileSystem.openZip(snapshot))
        } catch (error: Throwable) {
            runCatching { fileSystem.deleteRecursively(directory, mustExist = false) }
                .exceptionOrNull()?.let(error::addSuppressed)
            throw error
        }
    }
}

private class DesktopRuntimeArchive(
    private val fileSystem: FileSystem,
    private val directory: Path,
    private val snapshot: Path,
    private val zip: FileSystem,
) : RuntimeArchive {
    override fun read(member: RuntimeZipMember, maxBytes: Long): ByteArray {
        require(member.size in 0..maxBytes) { "Runtime ZIP member '${member.name}' is too large" }
        val source = zip.source("/${member.name}".toPath())
        val bytes = closeAfter(source::close) { source.readBounded(maxBytes) }
        require(bytes.size.toLong() == member.size) { "Runtime ZIP member '${member.name}' is corrupt" }
        return bytes
    }

    override fun extract(member: RuntimeBundleMember, destination: String) {
        val source = zip.source("/${member.name}".toPath())
        closeAfter(source::close) {
            val sink = fileSystem.sink(destination.toPath(), mustCreate = true).buffer()
            closeAfter(sink::close) {
                val buffer = Buffer()
                var copied = 0L
                while (copied <= member.size) {
                    val read = source.read(buffer, minOf(8_192L, member.size + 1 - copied))
                    if (read == -1L) break
                    sink.write(buffer, read)
                    copied += read
                }
                require(copied == member.size && source.read(buffer, 1) == -1L) {
                    "Runtime ZIP member '${member.name}' is corrupt"
                }
            }
        }
    }

    override fun close() {
        var failure: Throwable? = null
        try {
            zip.close()
        } catch (error: Throwable) {
            failure = error
        }
        try {
            check(fileSystem.metadataOrNull(snapshot)?.symlinkTarget == null) {
                "Runtime archive snapshot was replaced"
            }
            fileSystem.deleteRecursively(directory, mustExist = false)
        } catch (cleanup: Throwable) {
            if (failure == null) throw cleanup
            failure.addSuppressed(cleanup)
        }
        failure?.let { throw it }
    }
}

private fun Source.readBounded(maxBytes: Long): ByteArray {
    require(maxBytes in 0..Int.MAX_VALUE.toLong()) { "File snapshot limit is invalid" }
    val buffer = Buffer()
    var total = 0L
    while (total <= maxBytes) {
        val read = read(buffer, minOf(8_192L, maxBytes + 1 - total))
        if (read == -1L) break
        total += read
    }
    require(total <= maxBytes) { "File exceeds its size limit" }
    return buffer.readByteArray()
}
