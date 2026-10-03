package io.github.codex_agent_labs.codexagent.appserver.runtime.host

import io.github.codex_agent_labs.codexagent.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceSelectionReason
import io.github.codex_agent_labs.codexagent.appserver.runtime.desktopFileSystem
import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.test.runTest
import okio.FileSystem
import okio.Path
import okio.buffer

class DesktopHostFilesSecurityTest {
    @Test
    fun installsOneRealStoredArchiveSnapshot() = runTest {
        withTemporaryDirectory { root ->
            val bundle = root / "bundle"
            val data = root / "data"
            desktopFileSystem.createDirectories(bundle)
            writeBundle(bundle)

            val installed = RuntimeBundleInstaller(bundle, data, descriptor()) {}.install()

            assertEquals("app", installed.appServer.readUtf8())
            assertEquals("supervisor", installed.supervisor.readUtf8())
        }
    }

    @Test
    fun rejectsSymlinkArchiveAndManagedAncestors() = runTest {
        withTemporaryDirectory { root ->
            val bundle = root / "bundle"
            val data = root / "data"
            val outside = root / "outside"
            desktopFileSystem.createDirectories(bundle)
            desktopFileSystem.createDirectories(outside)
            (outside / "sentinel").writeUtf8("keep")
            val expectedArchive = bundle / archiveName()
            val actualArchive = bundle / "actual.zip"
            actualArchive.writeBytes(bundleBytes())
            desktopFileSystem.createSymlink(expectedArchive, actualArchive)

            assertTrue(runCatching {
                RuntimeBundleInstaller(bundle, data, descriptor()) {}.install()
            }.isFailure)
            assertEquals("keep", (outside / "sentinel").readUtf8())

            desktopFileSystem.delete(expectedArchive)
            expectedArchive.writeBytes(bundleBytes())
            desktopFileSystem.createDirectories(data)
            desktopFileSystem.createSymlink(data / "runtimes", outside)
            assertTrue(runCatching {
                RuntimeBundleInstaller(bundle, data, descriptor()) {}.install()
            }.isFailure)
            assertEquals("keep", (outside / "sentinel").readUtf8())

            desktopFileSystem.delete(data / "runtimes")
            desktopFileSystem.createDirectories(data / "runtimes")
            desktopFileSystem.createSymlink(data / "runtimes" / descriptor().libraryVersion, outside)
            assertTrue(runCatching {
                RuntimeBundleInstaller(bundle, data, descriptor()) {}.install()
            }.isFailure)
            assertEquals("keep", (outside / "sentinel").readUtf8())
        }
    }

    @Test
    fun workspaceSelectionMetadataIsNoFollowAndClearOnlyUnlinksTheEntry() = runTest {
        withTemporaryDirectory { root ->
            val data = root / "data"
            val workspace = root / "workspace"
            val secondWorkspace = root / "second-workspace"
            val target = root / "selection-target"
            desktopFileSystem.createDirectories(data)
            desktopFileSystem.createDirectories(workspace)
            desktopFileSystem.createDirectories(secondWorkspace)
            val store = PathWorkspaceStore(data)
            assertIs<CodexWorkspaceResolution.Available>(
                store.select(CodexPathWorkspaceSelection(workspace.toString())),
            )
            val second = assertIs<CodexWorkspaceResolution.Available>(
                store.select(CodexPathWorkspaceSelection(secondWorkspace.toString())),
            )
            assertEquals(second, store.restore())
            store.clear()

            target.writeUtf8("\"${workspace}\"")
            desktopFileSystem.createSymlink(data / "workspace.json", target)

            val restored = store.restore()
            assertEquals(
                CodexWorkspaceSelectionReason.INVALID_SELECTION,
                assertIs<CodexWorkspaceResolution.SelectionRequired>(restored).reason,
            )
            store.clear()
            assertTrue(desktopFileSystem.metadataOrNull(data / "workspace.json") == null)
            assertTrue(desktopFileSystem.metadataOrNull(target)?.isRegularFile == true)
        }
    }
}

private fun descriptor() = RuntimeBundleDescriptor(
    libraryVersion = "1.2.3",
    appServerVersion = "0.149.0",
    target = "testTarget",
    classifier = "test-classifier",
    appServerName = "codex",
    appServerSha256 = APP_SHA,
    supervisorName = "supervisor",
)

private fun bundleBytes(): ByteArray {
    val descriptor = descriptor()
    val members = linkedMapOf(
        descriptor.appServerName to "app".encodeToByteArray(),
        descriptor.supervisorName to "supervisor".encodeToByteArray(),
        RUNTIME_LICENSE_NAME to "license".encodeToByteArray(),
        RUNTIME_NOTICE_NAME to "notice".encodeToByteArray(),
    )
    val hashes = mapOf(
        descriptor.appServerName to APP_SHA,
        descriptor.supervisorName to SUPERVISOR_SHA,
        RUNTIME_LICENSE_NAME to LICENSE_SHA,
        RUNTIME_NOTICE_NAME to NOTICE_SHA,
    )
    val manifest = buildString {
        append("{\"schemaVersion\":1,\"libraryVersion\":\"${descriptor.libraryVersion}\",")
        append("\"appServerVersion\":\"${descriptor.appServerVersion}\",")
        append("\"target\":\"${descriptor.target}\",\"classifier\":\"${descriptor.classifier}\",\"members\":[")
        members.entries.forEachIndexed { index, (name, bytes) ->
            if (index > 0) append(',')
            append("{\"name\":\"$name\",\"size\":${bytes.size},\"sha256\":\"${hashes.getValue(name)}\",")
            append("\"executable\":")
            append(name == descriptor.appServerName || name == descriptor.supervisorName)
            append('}')
        }
        append("]}")
    }.encodeToByteArray()
    members[RUNTIME_MANIFEST_NAME] = manifest
    return testStoredZip(members)
}

private fun writeBundle(directory: Path) {
    (directory / archiveName()).writeBytes(bundleBytes())
}

private fun archiveName() =
    "codex-agent-runtime-desktop-${descriptor().libraryVersion}-${descriptor().classifier}.zip"

private fun Path.writeBytes(bytes: ByteArray) {
    val sink = desktopFileSystem.sink(this).buffer()
    try {
        sink.write(bytes)
    } finally {
        sink.close()
    }
}

private fun Path.writeUtf8(value: String) {
    val sink = desktopFileSystem.sink(this).buffer()
    try {
        sink.writeUtf8(value)
    } finally {
        sink.close()
    }
}

private fun Path.readUtf8(): String {
    val source = desktopFileSystem.source(this).buffer()
    return try {
        source.readUtf8()
    } finally {
        source.close()
    }
}

private suspend fun withTemporaryDirectory(block: suspend (Path) -> Unit) {
    val root = FileSystem.SYSTEM_TEMPORARY_DIRECTORY /
        "codex-host-files-${Random.nextLong().toString().replace('-', '0')}"
    desktopFileSystem.createDirectory(root, mustCreate = true)
    try {
        block(root)
    } finally {
        desktopFileSystem.deleteRecursively(root, mustExist = false)
    }
}

private const val APP_SHA = "a172cedcae47474b615c54d510a5d84a8dea3032e958587430b413538be3f333"
private const val SUPERVISOR_SHA = "0834c2d60725ac5902257b3b78dd161ad26d1c0290dbf1e47cc14add5b8c8142"
private const val LICENSE_SHA = "cc1d3b0234846714b0aeda6cc34b057b4305bb83dd447fb88f816efeb59a4e96"
private const val NOTICE_SHA = "9368a7d21e018f64ae3327d2f25cd4d7693b2d85328e4bb680bcfcbd4c26b90e"
