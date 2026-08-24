package io.github.codex_agent_labs.codexmobile.agent.runtime

import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationBrowser
import io.github.codex_agent_labs.codexmobile.agent.CodexAuthorizationPresentation
import io.github.codex_agent_labs.codexmobile.agent.CodexRuntimeFeature
import io.github.codex_agent_labs.codexmobile.agent.CodexStorageRoots
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspace
import io.github.codex_agent_labs.codexmobile.appserver.runtime.CodexRuntimeFactory
import io.github.codex_agent_labs.codexmobile.appserver.runtime.DesktopCodexDistribution
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.FakeHostFiles
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.RuntimeBundleDescriptor
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.testRuntimeBundle
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.testRuntimeDescriptor
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.test.runTest
import okio.Path.Companion.toPath

class ExternalHostCodexPlatformTest {
    @Test
    fun preparesCanonicalWorkspaceAfterInstallWithoutStartingRuntime() = runTest {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members).apply {
            directories += "/workspace"
            symbolicLinks["/workspace-link"] = "/workspace"
        }
        val browser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None }
        var factoryCalls = 0
        var runtimeCreates = 0
        var factoryFailure: CancellationException? = null
        val factory = CodexRuntimeFactory {
            runtimeCreates++
            error("Runtime creation is outside platform preparation")
        }
        val platform = ExternalHostCodexPlatform(
            bundleDirectory = "/bundle".toPath(),
            dataDirectory = "/data".toPath(),
            storageRoots = null,
            distribution = descriptor.distribution(),
            files = files,
            authorizationBrowser = browser,
        ) { installed, workspace ->
            factoryCalls++
            factoryFailure?.let { throw it }
            assertEquals("app", files.text(installed.appServer.toString()))
            assertEquals("/workspace".toPath(), workspace)
            factory
        }

        val prepared = platform.prepare(CodexWorkspace("/workspace-link"))

        assertSame(browser, platform.authorizationBrowser)
        assertSame(factory, prepared.runtimeFactory)
        assertEquals("/workspace", prepared.workspacePath)
        assertEquals(externalHostCodexRuntimeFeatures, prepared.features)
        assertEquals(
            CodexStorageRoots("/data/cache".toPath(), "/data/state".toPath()),
            prepared.storageRoots,
        )
        assertEquals(1, files.archiveOpenCount)
        assertEquals(1, files.promotions)
        assertEquals(1, factoryCalls)
        assertEquals(0, runtimeCreates)

        val cancellation = CancellationException("cancel platform preparation")
        factoryFailure = cancellation
        assertSame(
            cancellation,
            assertFailsWith<CancellationException> {
                platform.prepare(CodexWorkspace("/workspace"))
            },
        )
        assertEquals(1, files.promotions)
    }

    @Test
    fun rejectsUnavailableWorkspaceBeforeArchiveOrDataMutation() = runTest {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members)
        var factoryCalls = 0
        val platform = ExternalHostCodexPlatform(
            bundleDirectory = "/bundle".toPath(),
            dataDirectory = "/data".toPath(),
            storageRoots = null,
            distribution = descriptor.distribution(),
            files = files,
            authorizationBrowser = CodexAuthorizationBrowser { CodexAuthorizationPresentation.None },
        ) { _, _ ->
            factoryCalls++
            CodexRuntimeFactory { error("unreachable") }
        }

        assertEquals(
            "Workspace is unavailable",
            assertFailsWith<IllegalArgumentException> {
                platform.prepare(CodexWorkspace("/missing"))
            }.message,
        )
        assertEquals(0, files.archiveOpenCount)
        assertEquals(0, files.promotions)
        assertEquals(0, factoryCalls)
        assertTrue("/data" !in files.directories)
    }

    @Test
    fun featureAndStorageRootContractIsSharedAndExplicit() {
        assertEquals(CodexRuntimeFeature.entries.toSet(), externalHostCodexRuntimeFeatures)
        val data = "/app/data".toPath()
        assertEquals(
            CodexStorageRoots(data / "cache", data / "state"),
            resolveExternalHostStorageRoots(data, configured = null),
        )

        val custom = CodexStorageRoots("/cache".toPath(), "/state".toPath())
        assertSame(custom, resolveExternalHostStorageRoots(data, custom))

        val disabled = CodexStorageRoots()
        assertSame(disabled, resolveExternalHostStorageRoots(data, disabled))
    }
}

private fun RuntimeBundleDescriptor.distribution() = DesktopCodexDistribution(
    libraryVersion = libraryVersion,
    appServerVersion = appServerVersion,
    target = target,
    classifier = classifier,
    binarySha256 = appServerSha256,
    executableName = appServerName,
    supervisorExecutableName = supervisorName,
)
