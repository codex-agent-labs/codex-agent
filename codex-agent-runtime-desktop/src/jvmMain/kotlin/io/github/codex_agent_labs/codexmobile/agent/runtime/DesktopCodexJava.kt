@file:JvmName("DesktopCodex")

package io.github.codex_agent_labs.codexmobile.agent.runtime

import io.github.codex_agent_labs.codexmobile.agent.CodexClientInfo
import io.github.codex_agent_labs.codexmobile.agent.CodexHost
import io.github.codex_agent_labs.codexmobile.agent.CodexStorageRoots
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
