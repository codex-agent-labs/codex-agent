package io.github.codex_agent_labs.codexmobile.appserver.runtime

import okio.Path

internal data class NodeCodexRuntimeConfiguration(
    val appServerExecutable: Path,
    val workingDirectory: Path,
    val processSupervisorExecutable: Path,
    val processSupervisorSha256: String,
)

internal class NodeCodexRuntimeFactory(
    private val configuration: NodeCodexRuntimeConfiguration,
) : CodexRuntimeFactory {
    override fun create(): CodexRuntime = NodeCodexRuntime(configuration)
}

internal class NodeCodexRuntime(
    private val configuration: NodeCodexRuntimeConfiguration,
    private val prepare: (NodeCodexRuntimeConfiguration) -> NodeLaunchSpec = ::validateNodeLaunch,
    private val launcher: NodeProcessLauncher = DefaultNodeProcessLauncher,
) : CodexRuntime by ExternalProcessCodexRuntime(
    launch = { launcher.launch(prepare(configuration)) },
)

internal fun validateNodeLaunch(configuration: NodeCodexRuntimeConfiguration): NodeLaunchSpec {
    fun canonical(value: Path, kind: String): String {
        val raw = value.toString()
        check(nodeHost.isAbsolute(raw)) { "$kind must be absolute" }
        val resolved = nodeHost.realPath(raw)
        check(nodeHost.resolvePath(raw) == resolved) { "$kind must not be a symbolic link" }
        return resolved
    }

    val target = currentNodeTarget()
    val distribution = desktopCodexDistribution(target)
    val executable = canonical(configuration.appServerExecutable, "App Server executable")
    val supervisor = canonical(configuration.processSupervisorExecutable, "Process supervisor executable")
    val workingDirectory = canonical(configuration.workingDirectory, "Working directory")
    check(nodeHost.isFile(executable)) { "App Server executable is not a regular file" }
    check(nodeHost.isFile(supervisor)) { "Process supervisor executable is not a regular file" }
    check(nodeHost.isDirectory(workingDirectory)) { "Working directory is not a directory" }
    check(nodeHost.baseName(executable) == distribution.executableName) {
        "App Server executable name mismatch"
    }
    check(nodeHost.baseName(supervisor) == distribution.supervisorExecutableName) {
        "Process supervisor executable name mismatch"
    }
    nodeHost.requireExecutable(executable)
    nodeHost.requireExecutable(supervisor)
    check(nodeHost.sha256(executable) == distribution.binarySha256) { "App Server checksum mismatch" }
    check(configuration.processSupervisorSha256.matches(Regex("[0-9a-f]{64}"))) {
        "Process supervisor SHA-256 must be 64 lowercase hexadecimal characters"
    }
    check(nodeHost.sha256(supervisor) == configuration.processSupervisorSha256) {
        "Process supervisor checksum mismatch"
    }
    return NodeLaunchSpec(
        command = supervisor,
        arguments = arrayOf(executable),
        workingDirectory = workingDirectory,
        detached = false,
        target = target,
    )
}
