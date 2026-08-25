import io.github.codex_agent_labs.codexagent.agent.runtime.DesktopCodexPlatform
import okio.Path

fun desktopPlatform(bundleDirectory: Path, dataDirectory: Path) =
    DesktopCodexPlatform(bundleDirectory, dataDirectory)
