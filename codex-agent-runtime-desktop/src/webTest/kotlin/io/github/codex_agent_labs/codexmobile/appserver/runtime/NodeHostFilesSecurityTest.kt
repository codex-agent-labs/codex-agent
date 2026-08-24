package io.github.codex_agent_labs.codexmobile.appserver.runtime

import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.NodePathWorkspaceStore
import io.github.codex_agent_labs.codexmobile.appserver.runtime.host.NodeRuntimeBundleInstaller
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import okio.Path.Companion.toPath

class NodeHostFilesSecurityTest {
    @Test
    fun rejectsSymlinkArchiveAndManagedAncestors() = runTest {
        val root = nodeTemporaryDirectory("codex-agent-node-security-")
        try {
            val bundle = nodeHost.joinPath(root, "bundle")
            val data = nodeHost.joinPath(root, "data")
            val outside = nodeHost.joinPath(root, "outside")
            nodeHost.createDirectories(bundle)
            nodeHost.createDirectories(outside)
            val sentinel = nodeHost.joinPath(outside, "sentinel")
            nodeHost.writeBytes(sentinel, "keep".encodeToByteArray())
            val descriptor = nodeTestDescriptor()
            val archiveName =
                "codex-agent-runtime-desktop-${descriptor.libraryVersion}-${descriptor.classifier}.zip"
            val expectedArchive = nodeHost.joinPath(bundle, archiveName)
            val actualArchive = nodeHost.joinPath(bundle, "actual.zip")
            val archive = nodeTestStoredZip(nodeTestBundleMembers(descriptor))
            nodeHost.writeBytes(actualArchive, archive)
            nodeHost.createSymbolicLink(expectedArchive, actualArchive)

            assertTrue(runCatching {
                NodeRuntimeBundleInstaller(bundle.toPath(), data.toPath(), descriptor).install()
            }.isFailure)
            assertEquals("keep", nodeHost.readBytes(sentinel).decodeToString())

            nodeHost.removeFile(expectedArchive)
            nodeHost.writeBytes(expectedArchive, archive)
            nodeHost.createDirectories(data)
            val runtimes = nodeHost.joinPath(data, "runtimes")
            nodeHost.createSymbolicLink(runtimes, outside)
            assertTrue(runCatching {
                NodeRuntimeBundleInstaller(bundle.toPath(), data.toPath(), descriptor).install()
            }.isFailure)
            assertEquals("keep", nodeHost.readBytes(sentinel).decodeToString())

            nodeHost.removeFile(runtimes)
            nodeHost.createDirectories(runtimes)
            nodeHost.createSymbolicLink(nodeHost.joinPath(runtimes, descriptor.libraryVersion), outside)
            assertTrue(runCatching {
                NodeRuntimeBundleInstaller(bundle.toPath(), data.toPath(), descriptor).install()
            }.isFailure)
            assertEquals("keep", nodeHost.readBytes(sentinel).decodeToString())
        } finally {
            nodeRemoveDirectory(root)
        }
    }

    @Test
    fun workspaceSelectionMetadataIsNoFollowAndClearOnlyUnlinksTheEntry() = runTest {
        val root = nodeTemporaryDirectory("codex-agent-node-workspace-security-")
        try {
            val data = nodeHost.joinPath(root, "data")
            val workspace = nodeHost.joinPath(root, "workspace")
            val target = nodeHost.joinPath(root, "selection-target")
            nodeHost.createDirectories(data)
            nodeHost.createDirectories(workspace)
            nodeHost.writeBytes(target, "\"$workspace\"".encodeToByteArray())
            val selection = nodeHost.joinPath(data, "workspace.json")
            nodeHost.createSymbolicLink(selection, target)
            val store = NodePathWorkspaceStore(data.toPath())

            val restored = store.restore()
            assertEquals(
                CodexWorkspaceSelectionReason.INVALID_SELECTION,
                assertIs<CodexWorkspaceResolution.SelectionRequired>(restored).reason,
            )
            store.clear()
            assertTrue(!nodeHost.exists(selection))
            assertEquals("\"$workspace\"", nodeHost.readBytes(target).decodeToString())

            val missingTarget = nodeHost.joinPath(root, "missing-selection-target")
            nodeHost.createSymbolicLink(selection, missingTarget)
            assertTrue(nodeHost.isSymbolicLink(selection))
            assertEquals(
                CodexWorkspaceSelectionReason.INVALID_SELECTION,
                assertIs<CodexWorkspaceResolution.SelectionRequired>(store.restore()).reason,
            )
            store.clear()
            assertTrue(runCatching { nodeHost.isSymbolicLink(selection) }.isFailure)
        } finally {
            nodeRemoveDirectory(root)
        }
    }
}
