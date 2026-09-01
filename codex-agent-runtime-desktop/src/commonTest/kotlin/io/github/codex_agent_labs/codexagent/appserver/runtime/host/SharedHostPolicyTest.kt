package io.github.codex_agent_labs.codexagent.appserver.runtime.host

import io.github.codex_agent_labs.codexagent.agent.CodexPathWorkspaceSelection
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceResolution
import io.github.codex_agent_labs.codexagent.agent.CodexWorkspaceSelectionReason
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertIs
import kotlin.test.assertTrue
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.test.runTest

class SharedHostPolicyTest {
    @Test
    fun parserAndArchivePreflightRejectInvalidTrustBoundaryInputs() {
        assertFailsWith<IllegalArgumentException> {
            parseRuntimeBundleManifest(
                """{"schemaVersion":1,"libraryVersion":1,"appServerVersion":"1","target":"t","classifier":"c","members":[]}"""
                    .encodeToByteArray(),
            )
        }
        assertFailsWith<IllegalArgumentException> {
            parseRuntimeBundleManifest(
                """{"schemaVersion":1,"libraryVersion":"1","appServerVersion":"1","target":"t","classifier":"c","members":[{"name":1,"size":1,"sha256":"${"a".repeat(64)}","executable":false}]}"""
                    .encodeToByteArray(),
            )
        }

        val aggregateBomb = testStoredZip(linkedMapOf(
            "one" to byteArrayOf(1),
            "two" to byteArrayOf(2),
        )).also { bytes ->
            signatureOffsets(bytes, LOCAL_SIGNATURE).forEach { offset ->
                writeU16(bytes, offset + 8, RUNTIME_ZIP_DEFLATED)
            }
            signatureOffsets(bytes, CENTRAL_SIGNATURE).forEach { offset ->
                writeU16(bytes, offset + 10, RUNTIME_ZIP_DEFLATED)
                writeU32(bytes, offset + 24, 300L * 1024 * 1024)
            }
        }
        assertEquals(
            "Runtime ZIP uncompressed size is invalid",
            assertFailsWith<IllegalArgumentException> { inspectRuntimeZip(aggregateBomb) }.message,
        )

        val storedSizeMismatch = testStoredZip(linkedMapOf("one" to byteArrayOf(1))).also { bytes ->
            writeU32(bytes, signatureOffsets(bytes, CENTRAL_SIGNATURE).single() + 24, 2)
        }
        assertEquals(
            "Runtime ZIP stored entry size is invalid",
            assertFailsWith<IllegalArgumentException> { inspectRuntimeZip(storedSizeMismatch) }.message,
        )
    }

    @Test
    fun manifestValidatorRejectsIdentityPinShapeSizeAndExecutableChanges() {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val manifest = parseRuntimeBundleManifest(bundle.members.getValue(RUNTIME_MANIFEST_NAME))
        val zipMembers = inspectRuntimeZip(bundle.archive)
        validateRuntimeBundleManifest(descriptor, manifest, zipMembers)

        val appServer = manifest.members.single { it.name == descriptor.appServerName }
        val supervisor = manifest.members.single { it.name == descriptor.supervisorName }
        val invalid = listOf(
            manifest.copy(target = "other") to zipMembers,
            manifest.copy(members = manifest.members.map {
                if (it == appServer) it.copy(sha256 = "f".repeat(64)) else it
            }) to zipMembers,
            manifest.copy(members = manifest.members.dropLast(1)) to zipMembers,
            manifest.copy(members = manifest.members.dropLast(1) + appServer) to zipMembers,
            manifest to zipMembers.dropLast(1),
            manifest to (zipMembers.dropLast(1) + zipMembers.first()),
            manifest.copy(members = manifest.members.map {
                if (it == appServer) it.copy(size = it.size + 1) else it
            }) to zipMembers,
            manifest.copy(members = manifest.members.map {
                if (it == supervisor) it.copy(executable = false) else it
            }) to zipMembers,
        )
        invalid.forEach { (invalidManifest, invalidZipMembers) ->
            assertFailsWith<IllegalArgumentException> {
                validateRuntimeBundleManifest(descriptor, invalidManifest, invalidZipMembers)
            }
        }
    }

    @Test
    fun installerUsesOneSnapshotAndPreservesOldInstallWhenPromotionFails() = runTest {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members)
        files.replaceBundleAfterSnapshot = true
        val installer = installer(files, descriptor)

        val installed = installer.install()
        assertEquals("app", files.text(installed.appServer.toString()))
        assertEquals(1, files.archiveOpenCount)
        assertTrue(files.openedInspectedSnapshot)

        val firstPromotions = files.promotions
        assertEquals(installed, installer.install())
        assertEquals(firstPromotions, files.promotions)

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failPromotionBeforeCommit = true
        val failure = runCatching { installer.install() }.exceptionOrNull()
        assertIs<IllegalStateException>(failure)
        assertEquals("corrupt", files.text(installed.appServer.toString()))
        assertTrue(files.names("/data/runtimes/1.2.3").none { ".staging-" in it || ".corrupt-" in it })

        files.failPromotionBeforeCommit = false
        assertEquals("app", files.text(installer.install().appServer.toString()))
    }

    @Test
    fun ambiguousMovesAndCleanupKeepAValidInstallOrRecoveryBackup() = runTest {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members)
        val installer = installer(files, descriptor)
        val installed = installer.install()
        val versionDirectory = "/data/runtimes/${descriptor.libraryVersion}"

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failDisplacementAfterCommit = true
        files.failPromotionBeforeCommit = true
        assertIs<IllegalStateException>(runCatching { installer.install() }.exceptionOrNull())
        assertEquals("corrupt", files.text(installed.appServer.toString()))

        files.failDisplacementAfterCommit = false
        files.failPromotionBeforeCommit = false
        assertEquals("app", files.text(installer.install().appServer.toString()))

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failDisplacementAfterCommit = true
        files.failDisplacementProbe = true
        val displacement = assertIs<IllegalStateException>(
            runCatching { installer.install() }.exceptionOrNull(),
        )
        assertEquals("injected displacement committed failure", displacement.message)
        assertEquals("injected recovery probe failure", displacement.suppressedExceptions.single().message)
        files.failDisplacementAfterCommit = false
        files.failDisplacementProbe = false
        assertEquals("app", files.text(installer.install().appServer.toString()))

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failPromotionBeforeCommit = true
        files.failPromotionRecoveryProbe = true
        val promotion = assertIs<IllegalStateException>(
            runCatching { installer.install() }.exceptionOrNull(),
        )
        assertEquals("injected promotion failure", promotion.message)
        assertEquals("injected recovery probe failure", promotion.suppressedExceptions.single().message)
        files.failPromotionBeforeCommit = false
        files.failPromotionRecoveryProbe = false
        assertEquals("app", files.text(installer.install().appServer.toString()))

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failPromotionAfterCommit = true
        assertEquals("app", files.text(installer.install().appServer.toString()))
        files.failPromotionAfterCommit = false

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failCorruptDelete = true
        assertEquals("app", files.text(installer.install().appServer.toString()))
        assertTrue(files.names(versionDirectory).any { ".corrupt-" in it })
        files.failCorruptDelete = false
        installer.install()
        assertTrue(files.names(versionDirectory).none { ".corrupt-" in it })

        files.writeExisting(installed.appServer.toString(), "corrupt")
        files.failDisplacementAfterCommit = true
        files.failPromotionBeforeCommit = true
        files.failRollbackBeforeCommit = true
        val failure = assertIs<IllegalStateException>(
            runCatching { installer.install() }.exceptionOrNull(),
        )
        assertTrue(failure.suppressedExceptions.any { "rollback" in it.message.orEmpty() })
        assertTrue(runCatching { files.text(installed.appServer.toString()) }.isFailure)
        assertTrue(files.names(versionDirectory).any { ".corrupt-" in it })

        files.failDisplacementAfterCommit = false
        files.failPromotionBeforeCommit = false
        files.failRollbackBeforeCommit = false
        assertEquals("app", files.text(installer.install().appServer.toString()))
        assertTrue(files.names(versionDirectory).none { ".corrupt-" in it })
    }

    @Test
    fun archiveAndResourceCloseFailuresPreserveThePrimaryFailure() = runTest {
        val descriptor = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(descriptor)
        val files = FakeHostFiles(bundle.archive, bundle.members).apply {
            failArchiveRead = true
            failArchiveClose = true
        }
        val failure = assertIs<IllegalStateException>(
            runCatching { installer(files, descriptor).install() }.exceptionOrNull(),
        )
        assertEquals("injected archive read failure", failure.message)
        assertEquals("injected archive close failure", failure.suppressedExceptions.single().message)

        val resourceFailure = assertIs<IllegalStateException>(runCatching {
            closeAfter(
                close = { throw IllegalStateException("injected descriptor close failure") },
                block = { throw IllegalStateException("injected descriptor read failure") },
            )
        }.exceptionOrNull())
        assertEquals("injected descriptor read failure", resourceFailure.message)
        assertEquals("injected descriptor close failure", resourceFailure.suppressedExceptions.single().message)
    }

    @Test
    fun descriptorValidationPrecedesFilesystemAndInstallersConverge() = runTest {
        val valid = testRuntimeDescriptor()
        val bundle = testRuntimeBundle(valid)
        val invalidFiles = FakeHostFiles(bundle.archive, bundle.members).also { it.operations = 0 }
        val invalid = valid.copy(libraryVersion = "..")
        assertIs<IllegalArgumentException>(
            runCatching { installer(invalidFiles, invalid).install() }.exceptionOrNull(),
        )
        assertEquals(0, invalidFiles.operations)
        assertFailsWith<IllegalArgumentException> {
            validateRuntimeBundleDescriptor(valid.copy(supervisorName = valid.appServerName))
        }

        val files = FakeHostFiles(bundle.archive, bundle.members)
        val results = listOf(
            async { installer(files, valid).install() },
            async { installer(files, valid).install() },
        ).awaitAll()
        assertEquals(results[0], results[1])
        assertEquals(1, files.promotions)

        val oversizedManifest = ByteArray(MAX_RUNTIME_MANIFEST_BYTES + 1) { 'x'.code.toByte() }
        val oversizedBundle = testStoredZip(linkedMapOf(
            RUNTIME_MANIFEST_NAME to oversizedManifest,
            "codex" to "app".encodeToByteArray(),
            "supervisor" to "supervisor".encodeToByteArray(),
            RUNTIME_LICENSE_NAME to "license".encodeToByteArray(),
            RUNTIME_NOTICE_NAME to "notice".encodeToByteArray(),
        ))
        val oversizedFiles = FakeHostFiles(oversizedBundle, emptyMap())
        assertIs<IllegalArgumentException>(
            runCatching { installer(oversizedFiles, valid).install() }.exceptionOrNull(),
        )
        assertEquals(0, oversizedFiles.archiveOpenCount)
        assertTrue("/data" !in oversizedFiles.directories)

        val aliasFiles = FakeHostFiles(bundle.archive, bundle.members).apply {
            symbolicLinks["/bundle-link"] = "/bundle"
        }
        val aliased = SharedRuntimeBundleInstaller("/bundle-link", "/data", valid, aliasFiles).install()
        assertEquals("app", aliasFiles.text(aliased.appServer.toString()))
    }

    @Test
    fun workspaceStateIsStrictAtomicAndNoFollow() = runTest {
        val files = FakeHostFiles(ByteArray(22), emptyMap()).apply {
            directories += setOf("/data", "/one", "/two")
        }
        val firstStore = SharedPathWorkspaceStore("/data", files)
        val secondStore = SharedPathWorkspaceStore("/data", files)

        val first = assertIs<CodexWorkspaceResolution.Available>(
            firstStore.select(CodexPathWorkspaceSelection("/one")),
        )
        assertEquals(first, secondStore.restore())
        val original = files.bytes("/data/workspace.json")

        files.failAtomicReplace = true
        assertIs<IllegalStateException>(
            runCatching { secondStore.select(CodexPathWorkspaceSelection("/two")) }.exceptionOrNull(),
        )
        assertContentEquals(original, files.bytes("/data/workspace.json"))
        assertTrue(files.names("/data").none { it.startsWith(".workspace-") })

        files.failAtomicReplace = false
        files.failAtomicReplaceAfterCommit = true
        val second = assertIs<CodexWorkspaceResolution.Available>(
            secondStore.select(CodexPathWorkspaceSelection("/two")),
        )
        assertEquals(second, firstStore.restore())
        files.failAtomicReplaceAfterCommit = false

        files.writeExisting("/data/workspace.json", "1")
        assertEquals(
            CodexWorkspaceSelectionReason.INVALID_SELECTION,
            assertIs<CodexWorkspaceResolution.SelectionRequired>(firstStore.restore()).reason,
        )
        files.remove("/data/workspace.json")
        files.symbolicLinks["/data/workspace.json"] = "/two"
        assertEquals(
            CodexWorkspaceSelectionReason.INVALID_SELECTION,
            assertIs<CodexWorkspaceResolution.SelectionRequired>(firstStore.restore()).reason,
        )
        firstStore.clear()
        assertTrue("/data/workspace.json" !in files.symbolicLinks)

        files.directories += "/data/workspace.json"
        assertIs<IllegalArgumentException>(runCatching { firstStore.clear() }.exceptionOrNull())
        assertTrue("/data/workspace.json" in files.directories)
    }

    private fun installer(files: FakeHostFiles, descriptor: RuntimeBundleDescriptor) =
        SharedRuntimeBundleInstaller("/bundle", "/data", descriptor, files)
}

internal class FakeHostFiles(
    archive: ByteArray,
    private val archiveMembers: Map<String, ByteArray>,
) : ExternalHostFiles {
    val directories = mutableSetOf("/", "/bundle")
    val symbolicLinks = mutableMapOf<String, String>()
    private val originalArchive = archive.copyOf()
    private val files = mutableMapOf(archivePath to originalArchive.copyOf())
    private var inspectedSnapshot: ByteArray? = null
    var operations = 0
    var archiveOpenCount = 0
    var openedInspectedSnapshot = false
    var promotions = 0
    var replaceBundleAfterSnapshot = false
    var failDisplacementAfterCommit = false
    var failDisplacementProbe = false
    var failPromotionBeforeCommit = false
    var failPromotionRecoveryProbe = false
    var failPromotionAfterCommit = false
    var failRollbackBeforeCommit = false
    var failCorruptDelete = false
    var failAtomicReplace = false
    var failAtomicReplaceAfterCommit = false
    var failArchiveRead = false
    var failArchiveClose = false
    var beforeFirstDataMutation: (() -> Unit)? = null
    private var pendingRecoveryProbeFailures = 0

    override fun isAbsolute(path: String): Boolean = operation { path.startsWith('/') }
    override fun joinPath(parent: String, child: String): String = operation {
        if (parent == "/") "/$child" else "${parent.trimEnd('/')}/$child"
    }
    override fun baseName(path: String): String = operation { path.substringAfterLast('/') }
    override fun canonicalize(path: String): String = operation {
        symbolicLinks[path]?.let(::canonicalize) ?: path
    }
    override fun isCanonical(path: String): Boolean = operation { path !in symbolicLinks }

    override fun metadataOrNull(path: String): HostFileMetadata? = operation {
        if (pendingRecoveryProbeFailures > 0) {
            pendingRecoveryProbeFailures--
            throw IllegalStateException("injected recovery probe failure")
        }
        when (path) {
            in symbolicLinks -> HostFileMetadata(false, false, true, 0)
            in directories -> HostFileMetadata(false, true, false, 0)
            in files -> HostFileMetadata(true, false, false, files.getValue(path).size.toLong())
            else -> null
        }
    }

    override fun list(path: String): List<String> = operation {
        check(path in directories) { "Not a directory: $path" }
        val prefix = if (path == "/") "/" else "$path/"
        (directories + files.keys + symbolicLinks.keys)
            .asSequence()
            .filter { it.startsWith(prefix) && it != path }
            .map { it.removePrefix(prefix).substringBefore('/') }
            .filter(String::isNotEmpty)
            .toSet()
            .sorted()
    }

    override fun createDirectories(path: String) = operation<Unit> {
        if (path == "/data") beforeFirstDataMutation?.also {
            beforeFirstDataMutation = null
            it()
        }
        var current = ""
        path.split('/').filter(String::isNotEmpty).forEach { component ->
            current += "/$component"
            check(current !in symbolicLinks) { "Symbolic-link directory: $current" }
            check(current !in files) { "File is not a directory: $current" }
            directories += current
        }
    }

    override fun createDirectory(path: String) = operation<Unit> {
        check(metadata(path) == null) { "Path exists: $path" }
        check(path.substringBeforeLast('/', "/").ifEmpty { "/" } in directories)
        directories += path
    }

    override fun readFileSnapshot(path: String, maxBytes: Long): ByteArray = operation {
        check(path !in symbolicLinks)
        val value = files.getValue(path)
        require(value.size.toLong() <= maxBytes) { "File exceeds its size limit" }
        val result = value.copyOf()
        if (path == archivePath) {
            inspectedSnapshot = result
            if (replaceBundleAfterSnapshot) files[path] = "replaced".encodeToByteArray()
        }
        result
    }

    override fun writeNewFile(path: String, bytes: ByteArray) = operation<Unit> {
        check(metadata(path) == null) { "Path exists: $path" }
        files[path] = bytes.copyOf()
    }

    override fun deleteFile(path: String) = operation<Unit> {
        check(path !in directories) { "Refusing to delete a directory as a file" }
        files.remove(path)
        symbolicLinks.remove(path)
    }

    override fun deleteRecursively(path: String) = operation<Unit> {
        if (failCorruptDelete && ".corrupt-" in path) {
            throw IllegalStateException("injected corrupt cleanup failure")
        }
        symbolicLinks.remove(path)
        files.keys.filter { it == path || it.startsWith("$path/") }.forEach(files::remove)
        directories.filter { it == path || it.startsWith("$path/") }
            .sortedByDescending(String::length)
            .forEach(directories::remove)
    }

    override fun move(source: String, destination: String) = operation<Unit> {
        val displacement = ".corrupt-" in destination
        val promotion = ".staging-" in source
        val rollback = ".corrupt-" in source
        if (promotion && failPromotionBeforeCommit) {
            if (failPromotionRecoveryProbe) pendingRecoveryProbeFailures = 2
            throw IllegalStateException("injected promotion failure")
        }
        if (rollback && failRollbackBeforeCommit) throw IllegalStateException("injected rollback failure")
        check(metadata(destination) == null) { "Destination exists: $destination" }
        relocate(source, destination)
        if (displacement && failDisplacementAfterCommit) {
            if (failDisplacementProbe) pendingRecoveryProbeFailures = 1
            throw IllegalStateException("injected displacement committed failure")
        }
        if (promotion) {
            promotions++
            if (failPromotionAfterCommit) throw IllegalStateException("injected promotion committed failure")
        }
    }

    override fun atomicReplace(source: String, destination: String) = operation<Unit> {
        if (failAtomicReplace) throw IllegalStateException("injected replace failure")
        check(source in files)
        check(destination !in directories)
        files[destination] = files.remove(source)!!
        symbolicLinks.remove(destination)
        if (failAtomicReplaceAfterCommit) throw IllegalStateException("injected replace committed failure")
    }

    override fun sha256(path: String): String = operation { fakeHash(files.getValue(path)) }
    override fun makeExecutable(path: String): Unit = operation { check(path in files) }

    override fun openRuntimeArchive(
        bytes: ByteArray,
        members: List<RuntimeZipMember>,
    ): RuntimeArchive = operation {
        archiveOpenCount++
        openedInspectedSnapshot = bytes.contentEquals(inspectedSnapshot)
        check(openedInspectedSnapshot)
        if (replaceBundleAfterSnapshot) {
            files[archivePath] = originalArchive.copyOf()
            replaceBundleAfterSnapshot = false
        }
        object : RuntimeArchive {
            override fun read(member: RuntimeZipMember, maxBytes: Long): ByteArray {
                if (failArchiveRead) throw IllegalStateException("injected archive read failure")
                val value = archiveMembers.getValue(member.name)
                require(value.size.toLong() == member.size && member.size <= maxBytes)
                return value.copyOf()
            }

            override fun extract(member: RuntimeBundleMember, destination: String) {
                val value = archiveMembers.getValue(member.name)
                require(value.size.toLong() == member.size)
                writeNewFile(destination, value)
            }

            override fun close() {
                if (failArchiveClose) throw IllegalStateException("injected archive close failure")
            }
        }
    }

    fun text(path: String): String = files.getValue(path).decodeToString()
    fun bytes(path: String): ByteArray = files.getValue(path).copyOf()
    fun names(path: String): List<String> = list(path)
    fun writeExisting(path: String, value: String) { files[path] = value.encodeToByteArray() }
    fun remove(path: String) { files.remove(path); symbolicLinks.remove(path); directories.remove(path) }

    private fun metadata(path: String): HostFileMetadata? = when (path) {
        in symbolicLinks -> HostFileMetadata(false, false, true, 0)
        in directories -> HostFileMetadata(false, true, false, 0)
        in files -> HostFileMetadata(true, false, false, files.getValue(path).size.toLong())
        else -> null
    }

    private fun relocate(source: String, destination: String) {
        val directoryEntries = directories.filter { it == source || it.startsWith("$source/") }
        val fileEntries = files.filterKeys { it == source || it.startsWith("$source/") }
        val linkEntries = symbolicLinks.filterKeys { it == source || it.startsWith("$source/") }
        check(directoryEntries.isNotEmpty() || fileEntries.isNotEmpty() || linkEntries.isNotEmpty())
        directoryEntries.sortedByDescending(String::length).forEach(directories::remove)
        fileEntries.keys.forEach(files::remove)
        linkEntries.keys.forEach(symbolicLinks::remove)
        directoryEntries.forEach { directories += destination + it.removePrefix(source) }
        fileEntries.forEach { (path, bytes) -> files[destination + path.removePrefix(source)] = bytes }
        linkEntries.forEach { (path, target) -> symbolicLinks[destination + path.removePrefix(source)] = target }
    }

    private inline fun <T> operation(block: () -> T): T {
        operations++
        return block()
    }

    private companion object {
        const val archivePath = "/bundle/codex-agent-runtime-desktop-1.2.3-test-classifier.zip"
    }
}

internal data class TestBundle(
    val archive: ByteArray,
    val members: Map<String, ByteArray>,
)

internal fun testRuntimeDescriptor() = RuntimeBundleDescriptor(
    libraryVersion = "1.2.3",
    appServerVersion = "0.149.0",
    target = "testTarget",
    classifier = "test-classifier",
    appServerName = "codex",
    appServerSha256 = fakeHash("app".encodeToByteArray()),
    supervisorName = "supervisor",
)

internal fun testRuntimeBundle(descriptor: RuntimeBundleDescriptor): TestBundle {
    val members = linkedMapOf(
        descriptor.appServerName to "app".encodeToByteArray(),
        descriptor.supervisorName to "supervisor".encodeToByteArray(),
        RUNTIME_LICENSE_NAME to "license".encodeToByteArray(),
        RUNTIME_NOTICE_NAME to "notice".encodeToByteArray(),
    )
    val manifest = buildString {
        append("{\"schemaVersion\":1,\"libraryVersion\":\"${descriptor.libraryVersion}\",")
        append("\"appServerVersion\":\"${descriptor.appServerVersion}\",")
        append("\"target\":\"${descriptor.target}\",\"classifier\":\"${descriptor.classifier}\",\"members\":[")
        members.entries.forEachIndexed { index, (name, bytes) ->
            if (index > 0) append(',')
            append("{\"name\":\"$name\",\"size\":${bytes.size},\"sha256\":\"${fakeHash(bytes)}\",")
            append("\"executable\":")
            append(name == descriptor.appServerName || name == descriptor.supervisorName)
            append('}')
        }
        append("]}")
    }.encodeToByteArray()
    members[RUNTIME_MANIFEST_NAME] = manifest
    return TestBundle(testStoredZip(members), members)
}

private fun fakeHash(bytes: ByteArray): String =
    "0123456789abcdef"[bytes.fold(0) { value, byte -> value + (byte.toInt() and 0xff) } and 0xf]
        .toString().repeat(64)

internal fun testStoredZip(entries: LinkedHashMap<String, ByteArray>): ByteArray {
    val output = ByteWriter()
    val offsets = mutableMapOf<String, Int>()
    entries.forEach { (name, bytes) ->
        offsets[name] = output.size
        output.u32(LOCAL_SIGNATURE).u16(20).u16(0).u16(0).u16(0).u16(0)
            .u32(crc32(bytes)).u32(bytes.size).u32(bytes.size).u16(name.length).u16(0)
            .bytes(name.encodeToByteArray()).bytes(bytes)
    }
    val centralOffset = output.size
    entries.forEach { (name, bytes) ->
        output.u32(CENTRAL_SIGNATURE).u16(20).u16(20).u16(0).u16(0).u16(0).u16(0)
            .u32(crc32(bytes)).u32(bytes.size).u32(bytes.size).u16(name.length).u16(0).u16(0)
            .u16(0).u16(0).u32(0).u32(offsets.getValue(name)).bytes(name.encodeToByteArray())
    }
    val centralSize = output.size - centralOffset
    output.u32(EOCD_SIGNATURE).u16(0).u16(0).u16(entries.size).u16(entries.size)
        .u32(centralSize).u32(centralOffset).u16(0)
    return output.toByteArray()
}

private fun crc32(bytes: ByteArray): Int {
    var crc = -1
    bytes.forEach { byte ->
        crc = crc xor (byte.toInt() and 0xff)
        repeat(8) { crc = (crc ushr 1) xor (0xedb88320.toInt() and -(crc and 1)) }
    }
    return crc.inv()
}

private class ByteWriter {
    private val values = mutableListOf<Byte>()
    val size get() = values.size
    fun u16(value: Int) = apply { repeat(2) { values += (value ushr (it * 8)).toByte() } }
    fun u32(value: Int) = apply { repeat(4) { values += (value ushr (it * 8)).toByte() } }
    fun bytes(value: ByteArray) = apply { values.addAll(value.toList()) }
    fun toByteArray(): ByteArray = values.toByteArray()
}

private fun signatureOffsets(bytes: ByteArray, signature: Int): List<Int> =
    (0..bytes.size - 4).filter { index ->
        (0..3).all { byte -> bytes[index + byte].toInt() and 0xff == signature ushr (byte * 8) and 0xff }
    }

private fun writeU32(bytes: ByteArray, offset: Int, value: Long) {
    repeat(4) { bytes[offset + it] = (value ushr (it * 8)).toByte() }
}

private fun writeU16(bytes: ByteArray, offset: Int, value: Int) {
    repeat(2) { bytes[offset + it] = (value ushr (it * 8)).toByte() }
}

private const val LOCAL_SIGNATURE = 0x04034b50
private const val CENTRAL_SIGNATURE = 0x02014b50
private const val EOCD_SIGNATURE = 0x06054b50
