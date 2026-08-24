package io.github.codex_agent_labs.codexmobile.appserver.runtime

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.withContext
import okio.FileSystem
import okio.HashingSource
import okio.Path
import okio.blackholeSink
import okio.buffer

internal data class DesktopCodexRuntimeConfiguration(
    val appServerExecutable: Path,
    val processSupervisorExecutable: Path,
    val processSupervisorSha256: String,
    val workingDirectory: Path,
)

internal class DesktopCodexRuntimeFactory private constructor(
    private val configuration: DesktopCodexRuntimeConfiguration,
    private val validateConfiguration: (DesktopCodexRuntimeConfiguration) -> Unit,
    private val startProcess: suspend (DesktopCodexRuntimeConfiguration) -> DesktopProcess,
) : CodexRuntimeFactory {
    internal constructor(configuration: DesktopCodexRuntimeConfiguration) : this(
        configuration,
        ::validateDesktopConfiguration,
        ::startDesktopProcess,
    )

    internal constructor(
        configuration: DesktopCodexRuntimeConfiguration,
        startProcess: suspend (DesktopCodexRuntimeConfiguration) -> DesktopProcess,
    ) : this(configuration, {}, startProcess)

    override fun create(): CodexRuntime = ExternalProcessCodexRuntime(desktopProcessDispatcher) {
        validateConfiguration(configuration)
        startProcess(configuration)
    }
}

internal interface DesktopProcess : ExternalHostProcess {
    fun readStdout(buffer: ByteArray): Int
    fun readStderr(buffer: ByteArray): Int
    fun write(bytes: ByteArray)
    fun waitForExit(): Int?

    override suspend fun collectStdout(emit: suspend (ByteArray, Int) -> Unit) {
        val buffer = ByteArray(STREAM_BUFFER_SIZE)
        while (true) {
            val count = readStdout(buffer)
            if (count == 0) return
            check(count > 0) { "Codex app-server stdout read failed" }
            emit(buffer, count)
        }
    }

    override suspend fun drainStderr() {
        val buffer = ByteArray(STREAM_BUFFER_SIZE)
        while (readStderr(buffer) > 0) Unit
    }

    override suspend fun awaitExit(): Int =
        checkNotNull(waitForExit()) { "Codex app-server process wait failed" }

    override suspend fun write(line: String) = withContext(desktopProcessDispatcher) {
        write(line.encodeToByteArray())
    }

    private companion object {
        const val STREAM_BUFFER_SIZE = 8 * 1024
    }
}

internal expect suspend fun startDesktopProcess(
    configuration: DesktopCodexRuntimeConfiguration,
): DesktopProcess

internal expect fun currentDesktopTarget(): String

internal expect val desktopProcessDispatcher: CoroutineDispatcher

internal expect val desktopFileSystem: FileSystem

private fun validateDesktopConfiguration(configuration: DesktopCodexRuntimeConfiguration) {
    val executable = configuration.appServerExecutable
    val supervisor = configuration.processSupervisorExecutable
    val workingDirectory = configuration.workingDirectory
    check(executable.isAbsolute) { "Codex app-server path must be absolute" }
    check(supervisor.isAbsolute) { "Process-supervisor path must be absolute" }
    check(workingDirectory.isAbsolute) { "Desktop working-directory path must be absolute" }
    check(executable.isRegularFile()) { "Codex app server does not exist" }
    check(supervisor.isRegularFile()) { "Codex process supervisor does not exist" }
    check(desktopFileSystem.metadataOrNull(supervisor)?.symlinkTarget == null) {
        "Codex process supervisor must not be a symbolic link"
    }
    check(runCatching { desktopFileSystem.canonicalize(supervisor) }.getOrNull() == supervisor) {
        "Codex process-supervisor path must be canonical"
    }
    check(desktopFileSystem.metadataOrNull(workingDirectory)?.isDirectory == true) {
        "Desktop working directory does not exist"
    }
    val distribution = desktopCodexDistribution(currentDesktopTarget())
    check(supervisor.name == distribution.supervisorExecutableName) {
        "Expected process supervisor '${distribution.supervisorExecutableName}' for ${distribution.target}"
    }
    check(executable.sha256() == distribution.binarySha256) {
        "Codex app-server checksum does not match ${distribution.target}"
    }
    check(configuration.processSupervisorSha256.matches(Regex("[0-9a-f]{64}"))) {
        "Process-supervisor SHA-256 must be 64 lowercase hexadecimal characters"
    }
    check(supervisor.sha256() == configuration.processSupervisorSha256) {
        "Codex process-supervisor checksum does not match ${distribution.target}"
    }
}

private fun Path.isRegularFile(): Boolean = desktopFileSystem.metadataOrNull(this)?.isRegularFile == true

internal fun Path.sha256(): String {
    val hashingSource = HashingSource.sha256(desktopFileSystem.source(this))
    val buffered = hashingSource.buffer()
    try {
        buffered.readAll(blackholeSink())
    } finally {
        buffered.close()
    }
    return hashingSource.hash.hex()
}
