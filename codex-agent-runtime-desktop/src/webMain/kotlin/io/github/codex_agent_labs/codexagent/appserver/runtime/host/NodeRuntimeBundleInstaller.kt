package io.github.codex_agent_labs.codexagent.appserver.runtime.host

import io.github.codex_agent_labs.codexagent.appserver.runtime.nodeHost
import okio.Path

internal class NodeRuntimeBundleInstaller(
    bundleDirectory: Path,
    dataDirectory: Path,
    descriptor: RuntimeBundleDescriptor,
) {
    private val delegate = SharedRuntimeBundleInstaller(
        bundleDirectory.toString(),
        dataDirectory.toString(),
        descriptor,
        NodeHostFiles,
    )

    suspend fun install(): InstalledRuntime = delegate.install()
}

internal object NodeHostFiles : ExternalHostFiles {
    override fun isAbsolute(path: String): Boolean = nodeHost.isAbsolute(path)
    override fun joinPath(parent: String, child: String): String = nodeHost.joinPath(parent, child)
    override fun baseName(path: String): String = nodeHost.baseName(path)
    override fun canonicalize(path: String): String = nodeHost.realPath(path)
    override fun isCanonical(path: String): Boolean =
        runCatching { nodeHost.realPath(path) == nodeHost.resolvePath(path) }.getOrDefault(false)

    override fun metadataOrNull(path: String): HostFileMetadata? = runCatching {
        val symbolicLink = nodeHost.isSymbolicLink(path)
        if (symbolicLink) {
            HostFileMetadata(regularFile = false, directory = false, symbolicLink = true, size = 0)
        } else {
            val regularFile = nodeHost.isFile(path)
            HostFileMetadata(
                regularFile = regularFile,
                directory = nodeHost.isDirectory(path),
                symbolicLink = false,
                size = if (regularFile) nodeHost.fileSize(path) else 0,
            )
        }
    }.getOrNull()

    override fun list(path: String): List<String> = nodeHost.list(path)
    override fun createDirectories(path: String): Unit = nodeHost.createDirectories(path)
    override fun createDirectory(path: String): Unit = nodeHost.createDirectory(path)
    override fun readFileSnapshot(path: String, maxBytes: Long): ByteArray =
        nodeHost.readFileSnapshot(path, maxBytes)

    override fun writeNewFile(path: String, bytes: ByteArray): Unit = nodeHost.writeNewBytes(path, bytes)
    override fun deleteFile(path: String): Unit = nodeHost.removeFile(path)
    override fun deleteRecursively(path: String): Unit = nodeHost.removePath(path)
    override fun move(source: String, destination: String): Unit = nodeHost.move(source, destination)
    override fun atomicReplace(source: String, destination: String): Unit =
        nodeHost.atomicReplace(source, destination)

    override fun sha256(path: String): String = nodeHost.sha256(path)
    override fun makeExecutable(path: String): Unit = nodeHost.makeExecutable(path)

    override fun openRuntimeArchive(
        bytes: ByteArray,
        members: List<RuntimeZipMember>,
    ): RuntimeArchive = NodeRuntimeArchive(bytes, members.associateBy(RuntimeZipMember::name))
}

private class NodeRuntimeArchive(
    private val archive: ByteArray,
    private val members: Map<String, RuntimeZipMember>,
) : RuntimeArchive {
    override fun read(member: RuntimeZipMember, maxBytes: Long): ByteArray = decode(member, maxBytes)

    override fun extract(member: RuntimeBundleMember, destination: String) {
        nodeHost.writeNewBytes(destination, decode(members.getValue(member.name), member.size))
    }

    override fun close(): Unit = Unit

    private fun decode(requested: RuntimeZipMember, maxBytes: Long): ByteArray {
        val member = members.getValue(requested.name)
        require(member == requested && member.size in 0..maxBytes) {
            "Runtime ZIP member '${requested.name}' is invalid"
        }
        val compressed = archive.copyOfRange(member.dataOffset, member.dataOffset + member.compressedSize)
        val bytes = when (member.compression) {
            RUNTIME_ZIP_STORED -> compressed
            RUNTIME_ZIP_DEFLATED -> nodeHost.inflateRaw(compressed, (member.size + 1).toInt())
            else -> error("Runtime ZIP entry is unsupported")
        }
        require(bytes.size.toLong() == member.size) { "Runtime ZIP member '${member.name}' is corrupt" }
        return bytes
    }
}
