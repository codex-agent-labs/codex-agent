package io.github.codex_agent_labs.codexmobile.agent.runtime

import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationUrl
import io.github.codex_agent_labs.codexmobile.agent.CodexPlatform
import io.github.codex_agent_labs.codexmobile.agent.CodexStorageRoots
import io.github.codex_agent_labs.codexmobile.appserver.runtime.DesktopCodexRuntimeConfiguration
import io.github.codex_agent_labs.codexmobile.appserver.runtime.DesktopCodexRuntimeFactory
import io.github.codex_agent_labs.codexmobile.appserver.runtime.currentDesktopTarget
import io.github.codex_agent_labs.codexmobile.appserver.runtime.desktopCodexDistribution
import io.github.codex_agent_labs.codexmobile.appserver.runtime.makeDesktopExecutable
import io.github.codex_agent_labs.codexmobile.appserver.runtime.openDesktopAuthorizationUrl
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.DesktopHostFiles
import okio.Path

/**
 * Desktop support for [io.github.codex_agent_labs.codexmobile.agent.CodexHost].
 *
 * A `null` `storageRoots` uses `dataDirectory/cache` and
 * `dataDirectory/state`. Pass [CodexStorageRoots] explicitly to override those
 * roots; an empty value disables client cache and state persistence.
 *
 * The caller must verify the signed Maven classifier artifact (or independently
 * authenticate those exact bytes) before placing it in `bundleDirectory`, and
 * must keep that directory non-attacker-writable. This runtime verifies content
 * and cache integrity, not the artifact signature.
 */
public class DesktopCodexPlatform public constructor(
    bundleDirectory: Path,
    dataDirectory: Path,
    storageRoots: CodexStorageRoots? = null,
) : CodexPlatform by ExternalHostCodexPlatform(
    bundleDirectory = bundleDirectory,
    dataDirectory = dataDirectory,
    storageRoots = storageRoots,
    distribution = desktopCodexDistribution(currentDesktopTarget()),
    files = DesktopHostFiles(executable = ::makeDesktopExecutable),
    authorizationBrowser = DesktopCodexAuthorizationBrowser,
    createRuntimeFactory = { runtime, workspace ->
        DesktopCodexRuntimeFactory(
            DesktopCodexRuntimeConfiguration(
                appServerExecutable = runtime.appServer,
                processSupervisorExecutable = runtime.supervisor,
                processSupervisorSha256 = runtime.supervisorSha256,
                workingDirectory = workspace,
            ),
        )
    },
)

private object DesktopCodexAuthorizationBrowser : CodexAuthorizationBrowser {
    override fun open(url: CodexAuthorizationUrl): CodexAuthorizationPresentation {
        openDesktopAuthorizationUrl(url.value)
        return CodexAuthorizationPresentation.None
    }
}
