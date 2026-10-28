package io.github.codex_agent_labs.codexagent.appserver.runtime.host

import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceStore
import io.github.codex_agent_labs.codexagent.appserver.runtime.desktopFileSystem
import okio.FileSystem
import okio.Path

internal class PathWorkspaceStore(
    dataDirectory: Path,
    fileSystem: FileSystem = desktopFileSystem,
) : CodexWorkspaceStore {
    private val delegate = SharedPathWorkspaceStore(
        dataDirectory.toString(),
        DesktopHostFiles(fileSystem),
    )

    override suspend fun select(selection: CodexWorkspaceSelection): CodexWorkspaceResolution =
        delegate.select(selection)

    override suspend fun restore(): CodexWorkspaceResolution = delegate.restore()
    override suspend fun clear(): Unit = delegate.clear()
    fun resolve(path: String): CodexWorkspaceResolution = delegate.resolve(path)
}
