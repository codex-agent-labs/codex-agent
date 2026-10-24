@file:JvmName("DesktopCodex")

package io.github.codex_agent_labs.codexagent.agent.runtime

import io.github.codex_agent_labs.codexagent.agent.CodexClientInfo
import io.github.codex_agent_labs.codexagent.agent.CodexHost
import io.github.codex_agent_labs.codexagent.agent.CodexStorageRoots
import java.nio.file.Path
import okio.Path.Companion.toOkioPath

public fun createHost(
    bundleDirectory: Path,
    dataDirectory: Path,
    clientInfo: CodexClientInfo,
): CodexHost = CodexHost(
    DesktopCodexPlatform(bundleDirectory.toOkioPath(), dataDirectory.toOkioPath()),
    clientInfo,
)

public fun createHost(
    bundleDirectory: Path,
    dataDirectory: Path,
    clientInfo: CodexClientInfo,
    storageRoots: CodexStorageRoots,
): CodexHost = CodexHost(
    DesktopCodexPlatform(bundleDirectory.toOkioPath(), dataDirectory.toOkioPath(), storageRoots),
    clientInfo,
)
