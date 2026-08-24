package io.github.codex_agent_labs.codexmobile.agent.runtime

import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.CodexStorageRoots
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceStore
import io.github.codex_agent_labs.codexmobile.agent.PreparedCodexRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntimeFactory
import io.github.codex_agent_labs.codexmobile.appserver.runtime.DesktopCodexDistribution
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.ExternalHostFiles
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.InstalledRuntime
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.RuntimeBundleDescriptor
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.SharedPathWorkspaceStore
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.SharedRuntimeBundleInstaller
import okio.Path
import okio.Path.Companion.toPath

internal class ExternalHostCodexPlatform(
    bundleDirectory: Path,
    dataDirectory: Path,
    storageRoots: CodexStorageRoots?,
    distribution: DesktopCodexDistribution,
    files: ExternalHostFiles,
    override val authorizationBrowser: CodexAuthorizationBrowser,
    private val createRuntimeFactory: (InstalledRuntime, Path) -> CodexRuntimeFactory,
) : CodexPlatform {
    private val pathWorkspaceStore = SharedPathWorkspaceStore(dataDirectory.toString(), files)
    override val workspaceStore: CodexWorkspaceStore = pathWorkspaceStore
    private val effectiveStorageRoots = resolveExternalHostStorageRoots(dataDirectory, storageRoots)
    private val installer = SharedRuntimeBundleInstaller(
        bundleDirectory = bundleDirectory.toString(),
        dataDirectory = dataDirectory.toString(),
        descriptor = distribution.runtimeBundleDescriptor(),
        files = files,
    )

    override suspend fun prepare(workspace: CodexWorkspace): PreparedCodexRuntime {
        val resolved = pathWorkspaceStore.resolve(workspace.path)
        require(resolved is CodexWorkspaceResolution.Available) { "Workspace is unavailable" }
        val runtime = installer.install()
        return PreparedCodexRuntime(
            runtimeFactory = createRuntimeFactory(runtime, resolved.workspace.path.toPath()),
            workspacePath = resolved.workspace.path,
            features = externalHostCodexRuntimeFeatures,
            storageRoots = effectiveStorageRoots,
        )
    }
}

internal val externalHostCodexRuntimeFeatures = setOf(
    CodexRuntimeFeature.SHELL_COMMANDS,
    CodexRuntimeFeature.SKILLS,
    CodexRuntimeFeature.HOOKS,
    CodexRuntimeFeature.PLUGINS,
    CodexRuntimeFeature.CONNECTORS,
    CodexRuntimeFeature.MCP_SERVERS,
)

internal fun resolveExternalHostStorageRoots(
    dataDirectory: Path,
    configured: CodexStorageRoots?,
): CodexStorageRoots = configured ?: CodexStorageRoots(
    cacheRoot = dataDirectory / "cache",
    stateRoot = dataDirectory / "state",
)

private fun DesktopCodexDistribution.runtimeBundleDescriptor() = RuntimeBundleDescriptor(
    libraryVersion = libraryVersion,
    appServerVersion = appServerVersion,
    target = target,
    classifier = classifier,
    appServerName = executableName,
    appServerSha256 = binarySha256,
    supervisorName = supervisorExecutableName,
)
