package io.github.codex_agent_labs.codexagent.agent.runtime

import io.github.codex_agent_labs.codexagent.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexagent.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexagent.agent.CodexAuthorizationUrl
import io.github.codex_agent_labs.codexagent.agent.CodexPlatform
import io.github.codex_agent_labs.codexagent.agent.CodexStorageRoots
import io.github.codex_agent_labs.codexagent.appserver.runtime.NodeCodexRuntimeConfiguration
import io.github.codex_agent_labs.codexagent.appserver.runtime.NodeCodexRuntimeFactory
import io.github.codex_agent_labs.codexagent.appserver.runtime.currentNodeTarget
import io.github.codex_agent_labs.codexagent.appserver.runtime.desktopCodexDistribution
import io.github.codex_agent_labs.codexagent.appserver.runtime.nodeHost
import io.github.codex_agent_labs.codexagent.appserver.runtime.host.NodeHostFiles
import okio.Path

/**
 * Node support for [io.github.codex_agent_labs.codexagent.agent.CodexHost].
 *
 * The caller must verify the signed Maven classifier artifact (or independently
 * authenticate those exact bytes) before placing it in `bundleDirectory`, and
 * must keep that directory non-attacker-writable. This runtime verifies content
 * and cache integrity, not the artifact signature.
 */
public class NodeCodexPlatform(
    bundleDirectory: Path,
    dataDirectory: Path,
    storageRoots: CodexStorageRoots? = null,
) : CodexPlatform by ExternalHostCodexPlatform(
    bundleDirectory = bundleDirectory,
    dataDirectory = dataDirectory,
    storageRoots = storageRoots,
    distribution = desktopCodexDistribution(currentNodeTarget()),
    files = NodeHostFiles,
    authorizationBrowser = NodeCodexAuthorizationBrowser,
    createRuntimeFactory = { runtime, workspace ->
        NodeCodexRuntimeFactory(
            NodeCodexRuntimeConfiguration(
                appServerExecutable = runtime.appServer,
                workingDirectory = workspace,
                processSupervisorExecutable = runtime.supervisor,
                processSupervisorSha256 = runtime.supervisorSha256,
            ),
        )
    },
)

private object NodeCodexAuthorizationBrowser : CodexAuthorizationBrowser {
    override fun open(url: CodexAuthorizationUrl): CodexAuthorizationPresentation {
        nodeHost.openUrl(url.value)
        return CodexAuthorizationPresentation.None
    }
}
