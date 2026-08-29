package io.github.codex_agent_labs.codexagent.appserver.runtime.host

internal data class HostFileMetadata(
    val regularFile: Boolean,
    val directory: Boolean,
    val symbolicLink: Boolean,
    val size: Long,
)

/** Platform filesystem mechanics used by the shared Desktop/Host policy. */
internal interface ExternalHostFiles {
    fun isAbsolute(path: String): Boolean
    fun joinPath(parent: String, child: String): String
    fun baseName(path: String): String
    fun canonicalize(path: String): String
    fun isCanonical(path: String): Boolean
    fun metadataOrNull(path: String): HostFileMetadata?
    fun list(path: String): List<String>
    fun createDirectories(path: String)
    fun createDirectory(path: String)
    fun readFileSnapshot(path: String, maxBytes: Long): ByteArray
    fun writeNewFile(path: String, bytes: ByteArray)
    fun deleteFile(path: String)
    fun deleteRecursively(path: String)
    fun move(source: String, destination: String)
    fun atomicReplace(source: String, destination: String)
    fun sha256(path: String): String
    fun makeExecutable(path: String)

    fun openRuntimeArchive(
        bytes: ByteArray,
        members: List<RuntimeZipMember>,
    ): RuntimeArchive
}

/** One inspected archive snapshot. Implementations must not reopen the caller's bundle path. */
internal interface RuntimeArchive {
    fun read(member: RuntimeZipMember, maxBytes: Long): ByteArray
    fun extract(member: RuntimeBundleMember, destination: String)
    fun close()
}

internal inline fun <T> closeAfter(close: () -> Unit, block: () -> T): T {
    var failure: Throwable? = null
    try {
        return block()
    } catch (error: Throwable) {
        failure = error
        throw error
    } finally {
        try {
            close()
        } catch (cleanup: Throwable) {
            if (failure == null) throw cleanup
            failure.addSuppressed(cleanup)
        }
    }
}
