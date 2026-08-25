import java.io.File
import java.nio.file.Files
import java.nio.file.attribute.FileTime
import java.nio.file.attribute.PosixFileAttributeView
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Task
import org.gradle.testfixtures.ProjectBuilder

class SwiftPackageProofTaskTest {
    @Test
    fun `records exact clean immutable candidate proof`() = withFixture { fixture ->
        val proof = fixture.record().readReleaseObject()
        assertEquals(1, proof.releaseInt("schemaVersion"))
        assertEquals("swiftpm-candidate-v1", proof.releaseString("protocol"))
        assertEquals("passed", proof.releaseString("result"))
        assertEquals(fixture.commit, proof.releaseString("candidateCommit"))
        assertTrue(proof.releaseBoolean("cleanCheckout"))
        assertEquals(fixture.repo.canonicalPath, proof.releaseString("canonicalBuildRoot"))
        assertEquals(fixture.archive.name, proof.releaseString("archiveName"))
        assertEquals(fixture.archive.releaseDigest(), proof.releaseString("swiftPmChecksum"))
        assertEquals(fixture.archive.length(), proof.releaseLong("archiveBytes"))
        assertEquals(fixture.checksum.releaseDigest(), proof.releaseString("checksumFileSha256"))
        assertEquals(fixture.manifest.releaseDigest(), proof.releaseString("packageSwiftSha256"))
        assertEquals(fixture.provenance.releaseDigest(), proof.releaseString("nativeProvenanceSha256"))
    }

    @Test
    fun `rejects a different checked out commit`() = withFixture { fixture ->
        val failure = assertFailsWith<IllegalStateException> { fixture.record("0".repeat(40)) }
        assertTrue(failure.message.orEmpty().contains("does not match"))
    }

    @Test
    fun `rejects a dirty tracked checkout`() = withFixture { fixture ->
        fixture.manifest.appendText("\n// dirty\n")
        val failure = assertFailsWith<IllegalStateException> { fixture.record() }
        assertTrue(failure.message.orEmpty().contains("clean checkout"))
    }

    @Test
    fun `rejects an untracked Swift input`() =
        assertUntrackedRejected("codex-agent-runtime-ios/apple/Sources/CodexAgentAuthentication/New.swift")

    @Test
    fun `rejects an untracked Rust input`() =
        assertUntrackedRejected("codex-agent-runtime-ios/native/bridge/src/new.rs")

    @Test
    fun `rejects an untracked native patch input`() =
        assertUntrackedRejected("codex-agent-runtime-ios/native/patches/0004-untracked.patch")

    @Test
    fun `rejects an untracked Gradle configuration input`() = assertUntrackedRejected("gradle.properties")

    @Test
    fun `accepts ignored build outputs while recording proof`() = withFixture { fixture ->
        fixture.writeUntracked("build/generated/candidate.bin")
        val proof = fixture.record().readReleaseObject()
        assertEquals(fixture.commit, proof.releaseString("candidateCommit"))
        assertTrue(proof.releaseBoolean("cleanCheckout"))
    }

    @Test
    fun `rejects a generated checksum output mismatch`() = withFixture { fixture ->
        fixture.checksum.writeText("0".repeat(64))
        val failure = assertFailsWith<IllegalStateException> { fixture.record() }
        assertTrue(failure.message.orEmpty().contains("Generated SwiftPM checksum"))
    }

    @Test
    fun `rejects a committed Package swift checksum mismatch`() = withFixture(checksumMatches = false) { fixture ->
        val failure = assertFailsWith<IllegalStateException> { fixture.record() }
        assertTrue(failure.message.orEmpty().contains("Package.swift checksum"))
    }

    @Test
    fun `rejects changed archive bytes against committed metadata`() = withFixture { fixture ->
        fixture.writeArchive("different candidate bytes")
        val failure = assertFailsWith<IllegalStateException> { fixture.record() }
        assertTrue(failure.message.orEmpty().contains("Package.swift checksum"))
    }

    @Test
    fun `requires canonical candidate proof path`() = withFixture { fixture ->
        val other = fixture.repo.resolve("build/other/swiftpm-proof.json")
        val failure = assertFailsWith<IllegalStateException> { fixture.record(output = other) }
        assertTrue(failure.message.orEmpty().contains("canonical commit-isolated"))
        assertFalse(other.exists())
    }

    @Test
    fun `checksum updater changes only the canonical checksum and preserves permissions`() =
        withFixture(checksumMatches = false) { fixture ->
            val before = fixture.manifest.readText()
            val permissions = posixPermissions(fixture.manifest)
            fixture.update()
            assertEquals(
                before.replace("0".repeat(64), fixture.archive.releaseDigest()),
                fixture.manifest.readText(),
            )
            assertEquals(permissions, posixPermissions(fixture.manifest))
        }

    @Test
    fun `checksum updater does not rewrite an unchanged manifest`() = withFixture { fixture ->
        val fixedTime = FileTime.fromMillis(1_700_000_000_000)
        Files.setLastModifiedTime(fixture.manifest.toPath(), fixedTime)
        val before = fixture.manifest.readBytes()
        fixture.update()
        assertContentEquals(before, fixture.manifest.readBytes())
        assertEquals(fixedTime, Files.getLastModifiedTime(fixture.manifest.toPath()))
    }

    @Test
    fun `checksum updater rejects an archive checksum mismatch without mutation`() = withFixture { fixture ->
        fixture.checksum.writeText("${"f".repeat(64)}\n")
        val before = fixture.manifest.readBytes()
        assertFailsWith<IllegalStateException> { fixture.update() }
        assertContentEquals(before, fixture.manifest.readBytes())
    }

    @Test
    fun `checksum updater rejects ambiguous or noncanonical targets without mutation`() = withFixture { fixture ->
        val canonical = fixture.manifest.readText()
        val variants = listOf(
            canonical + canonical,
            canonical.replace(SWIFTPM_TEST_URL, "https://example.invalid/CodexAgent.zip"),
            canonical.replace(".binaryTarget", ".target"),
        )
        variants.forEach { contents ->
            fixture.manifest.writeText(contents)
            val before = fixture.manifest.readBytes()
            assertFailsWith<IllegalStateException> { fixture.update() }
            assertContentEquals(before, fixture.manifest.readBytes())
        }
    }

    @Test
    fun `checksum updater rejects a symbolic link manifest without mutation`() = withFixture { fixture ->
        val target = fixture.repo.resolve("Package.target.swift")
        Files.move(fixture.manifest.toPath(), target.toPath())
        Files.createSymbolicLink(fixture.manifest.toPath(), File(target.name).toPath())
        val before = target.readBytes()
        assertFailsWith<IllegalStateException> { fixture.update() }
        assertTrue(Files.isSymbolicLink(fixture.manifest.toPath()))
        assertContentEquals(before, target.readBytes())
    }

    @Test
    fun `checksum verification remains read only`() = withFixture { fixture ->
        val fixedTime = FileTime.fromMillis(1_700_000_000_000)
        Files.setLastModifiedTime(fixture.manifest.toPath(), fixedTime)
        val before = fixture.manifest.readBytes()
        fixture.verify()
        assertContentEquals(before, fixture.manifest.readBytes())
        assertEquals(fixedTime, Files.getLastModifiedTime(fixture.manifest.toPath()))
    }

    @Test
    fun `proof graph retains exact producers without clean`() {
        val root = ProjectBuilder.builder().withName("root").build()
        val ios = ProjectBuilder.builder().withName("codex-agent-runtime-ios").withParent(root).build()
        root.tasks.register("clean")
        ios.tasks.register("clean")
        val packageBinary = ios.tasks.register("packageCodexAgentSwiftPackageBinary")
        val checksum = ios.tasks.register("generateCodexAgentSwiftPackageChecksum") { dependsOn(packageBinary) }
        val toolchain = ios.tasks.register("verifyAppleToolchain")
        val proof = ios.tasks.register("recordCodexAgentSwiftPackageProof") {
            dependsOnSwiftPackageProofProducers(toolchain, checksum)
        }
        val graph = transitiveDependencies(proof.get())

        assertEquals(3, graph.size)
        assertEquals(
            setOf(
                ":codex-agent-runtime-ios:packageCodexAgentSwiftPackageBinary",
                ":codex-agent-runtime-ios:generateCodexAgentSwiftPackageChecksum",
                ":codex-agent-runtime-ios:verifyAppleToolchain",
            ),
            graph.map(Task::getPath).toSet(),
        )
        assertEquals(1, graph.count { it.name == "packageCodexAgentSwiftPackageBinary" })
        assertFalse(graph.any { it.name == "clean" })
    }

    @Test
    fun `root release path has no legacy Swift proof staging`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("build.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val rootBuild = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.root-release.gradle.kts",
        ).readText()
        val registration = repository.resolve(
            "gradle/build-logic/src/main/kotlin/IosAppleReleaseVerificationTasks.kt",
        ).readText()

        assertFalse("RecordSwiftPackageProofTask" in rootBuild)
        assertFalse("stage" + "Protected" in rootBuild)
        assertTrue("recordCodexAgentSwiftPackageProof" in registration)
        assertTrue("updateCodexAgentSwiftPackageChecksum" in registration)
        assertTrue("dependsOn(packageCodexAgentSwiftPackageBinary, generateCodexAgentSwiftPackageChecksum)" in registration)
        assertTrue("manifestFile.set(rootProject.layout.projectDirectory.file(\"Package.swift\"))" in registration)
        assertTrue("mustRunAfter(updateCodexAgentSwiftPackageChecksum)" in registration)
        assertFalse("dependsOn(updateCodexAgentSwiftPackageChecksum)" in registration)
        assertFalse("SwiftPackageAB" in rootBuild + registration)
        assertFalse("swiftPmBaselineProof" in rootBuild + registration)
        assertFalse("clean.configure" in registration)
    }

    private fun transitiveDependencies(task: Task): Set<Task> {
        val result = linkedSetOf<Task>()
        fun visit(current: Task) {
            current.taskDependencies.getDependencies(current).forEach { if (result.add(it)) visit(it) }
        }
        visit(task)
        return result
    }

    private fun withFixture(checksumMatches: Boolean = true, test: (SwiftPackageFixture) -> Unit) {
        val directory = createTempDirectory("swiftpm-proof").toFile()
        try { test(SwiftPackageFixture(directory, checksumMatches)) } finally { directory.deleteRecursively() }
    }

    private fun assertUntrackedRejected(path: String) = withFixture { fixture ->
        fixture.writeUntracked(path)
        val failure = assertFailsWith<IllegalStateException> { fixture.record() }
        assertTrue(failure.message.orEmpty().contains("non-ignored untracked"))
    }

    private fun posixPermissions(file: File) =
        Files.getFileAttributeView(file.toPath(), PosixFileAttributeView::class.java)
            ?.readAttributes()?.permissions()
}
