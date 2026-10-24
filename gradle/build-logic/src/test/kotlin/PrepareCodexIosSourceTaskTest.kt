import java.io.File
import java.nio.file.FileSystems
import java.nio.file.Files
import java.nio.file.attribute.FileTime
import java.nio.file.attribute.PosixFilePermission
import java.security.MessageDigest
import java.util.zip.GZIPOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContains
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.testfixtures.ProjectBuilder
import org.junit.Assume.assumeTrue

class PrepareCodexIosSourceTaskTest {
    @Test
    fun `identical validated source preserves mtimes while differences replace and symlinks reject`() {
        assumeTrue(FileSystems.getDefault().supportedFileAttributeViews().contains("posix"))
        val project = fixture()
        try {
            val revision = "0".repeat(40)
            val archive = project.resolve("codex.tar.gz")
            val lock = "locked\n".encodeToByteArray()
            writeTarGz(
                archive,
                mapOf(
                    "codex-$revision/marker.txt" to "source\n".encodeToByteArray(),
                    "codex-$revision/codex-rs/Cargo.lock" to lock,
                ),
            )
            project.resolve("change.patch").writeText("")
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            val prepare = task(project, revision, archive.sha256(), lock.sha256())
            prepare.prepare()

            val output = project.resolve("build/codex-source")
            val marker = output.resolve("marker.txt")
            val expectedBytes = verifiedRegularFiles(output).mapValues { it.value.sha256() }
            val expectedPermissions = Files.getPosixFilePermissions(marker.toPath())
            Files.setLastModifiedTime(marker.toPath(), FileTime.fromMillis(1_234_567_000L))
            val preservedTime = Files.getLastModifiedTime(marker.toPath())
            prepare.prepare()
            assertEquals(preservedTime, Files.getLastModifiedTime(marker.toPath()))
            assertEquals(expectedBytes, verifiedRegularFiles(output).mapValues { it.value.sha256() })

            val invalidSource = assertFailsWith<IllegalStateException> {
                task(project, revision, "0".repeat(64), lock.sha256()).prepare()
            }
            assertContains(invalidSource.message.orEmpty(), "source archive SHA-256 mismatch")
            assertEquals(expectedBytes, verifiedRegularFiles(output).mapValues { it.value.sha256() })
            assertEquals(preservedTime, Files.getLastModifiedTime(marker.toPath()))

            marker.writeText("tampered\n")
            prepare.prepare()
            assertEquals("source\n", marker.readText())
            output.resolve("unexpected-empty-directory").mkdir()
            prepare.prepare()
            assertFalse(output.resolve("unexpected-empty-directory").exists())

            val changedPermissions = expectedPermissions.toMutableSet().apply {
                if (!remove(PosixFilePermission.OWNER_EXECUTE)) add(PosixFilePermission.OWNER_EXECUTE)
            }
            Files.setPosixFilePermissions(marker.toPath(), changedPermissions)
            prepare.prepare()
            assertEquals(expectedPermissions, Files.getPosixFilePermissions(marker.toPath()))

            val unsafe = output.resolve("unsafe-link")
            Files.createSymbolicLink(unsafe.toPath(), marker.toPath())
            val failure = assertFailsWith<IllegalStateException> { prepare.prepare() }
            assertContains(failure.message.orEmpty(), "unsafe entry")
            assertTrue(Files.isSymbolicLink(unsafe.toPath()))
        } finally {
            project.deleteRecursively()
        }
    }

    @Test
    fun `validates patches and stages the exact GitHub API source revision`() {
        val project = fixture()
        try {
            val revision = "1".repeat(40)
            val archive = project.resolve("codex.tar.gz")
            writeTarGz(
                archive,
                mapOf(
                    "openai-codex-${revision.take(7)}/marker.txt" to "before\n".encodeToByteArray(),
                    "openai-codex-${revision.take(7)}/codex-rs/Cargo.lock" to
                        "locked\n".encodeToByteArray(),
                ),
            )
            project.resolve("change.patch").writeText(
                """
                diff --git a/marker.txt b/marker.txt
                --- a/marker.txt
                +++ b/marker.txt
                @@ -1 +1 @@
                -before
                +after
                """.trimIndent() + "\n",
            )
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            task(project, revision, archive.sha256(), "locked\n".encodeToByteArray().sha256()).prepare()

            assertEquals("after\n", project.resolve("build/codex-source/marker.txt").readText())
            assertTrue(project.resolve("build/codex-source/codex-rs/ios-bridge/Cargo.toml").isFile)
            assertEquals(
                "sqlite-patched\n",
                project.resolve(
                    "build/codex-source/codex-rs/third-party/libsqlite3-sys/sqlite3/sqlite3.c",
                ).readText(),
            )
        } finally {
            project.deleteRecursively()
        }
    }

    @Test
    fun `rejects an archive hash before replacing output`() {
        val project = fixture()
        try {
            val revision = "2".repeat(40)
            val archive = project.resolve("codex.tar.gz")
            writeTarGz(
                archive,
                mapOf(
                    "codex-$revision/marker.txt" to "source\n".encodeToByteArray(),
                    "codex-$revision/codex-rs/Cargo.lock" to "locked\n".encodeToByteArray(),
                ),
            )
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            project.resolve("change.patch").writeText("")
            val failure = assertFailsWith<IllegalStateException> {
                task(project, revision, "0".repeat(64), "1".repeat(64)).prepare()
            }

            assertTrue(failure.message.orEmpty().contains("Codex iOS source archive SHA-256 mismatch"))
            assertFalse(project.resolve("build/codex-source").exists())
        } finally {
            project.deleteRecursively()
        }
    }

    @Test
    fun `rejects a Cargo lock hash before applying patches`() {
        val project = fixture()
        try {
            val revision = "3".repeat(40)
            val archive = project.resolve("codex.tar.gz")
            writeTarGz(
                archive,
                mapOf(
                    "codex-$revision/marker.txt" to "source\n".encodeToByteArray(),
                    "codex-$revision/codex-rs/Cargo.lock" to "changed\n".encodeToByteArray(),
                ),
            )
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            project.resolve("change.patch").writeText("")

            val failure = assertFailsWith<IllegalStateException> {
                task(project, revision, archive.sha256(), "0".repeat(64)).prepare()
            }

            assertTrue(failure.message.orEmpty().contains("Cargo.lock SHA-256 mismatch"))
            assertFalse(project.resolve("build/codex-source").exists())
        } finally {
            project.deleteRecursively()
        }
    }

    @Test
    fun `rejects a prepared Cargo lock hash after applying patches`() {
        val project = fixture()
        try {
            val revision = "4".repeat(40)
            val archive = project.resolve("codex.tar.gz")
            val lock = "locked\n".encodeToByteArray()
            val patchedLock = "patched\n".encodeToByteArray()
            val wrongPin = "0".repeat(64)
            writeTarGz(
                archive,
                mapOf(
                    "codex-$revision/marker.txt" to "source\n".encodeToByteArray(),
                    "codex-$revision/codex-rs/Cargo.lock" to lock,
                ),
            )
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            project.resolve("change.patch").writeText(
                """
                diff --git a/codex-rs/Cargo.lock b/codex-rs/Cargo.lock
                --- a/codex-rs/Cargo.lock
                +++ b/codex-rs/Cargo.lock
                @@ -1 +1 @@
                -locked
                +patched
                """.trimIndent() + "\n",
            )

            val failure = assertFailsWith<IllegalStateException> {
                task(project, revision, archive.sha256(), lock.sha256(), wrongPin).prepare()
            }

            assertContains(failure.message.orEmpty(), "Prepared Codex iOS Cargo.lock SHA-256 mismatch")
            assertContains(failure.message.orEmpty(), "expected=$wrongPin")
            assertContains(failure.message.orEmpty(), "actual=${patchedLock.sha256()}")
            assertFalse(project.resolve("build/codex-source").exists())
        } finally {
            project.deleteRecursively()
        }
    }

    @Test
    fun `patches are relative content-sensitive task inputs`() {
        val project = fixture()
        try {
            val archive = project.resolve("codex.tar.gz").apply { writeText("archive") }
            project.resolve("bridge").mkdir()
            project.resolve("bridge/Cargo.toml").writeText("[package]\nname = \"bridge\"\n")
            val patch = project.resolve("change.patch").apply { writeText("patch") }
            val task = task(project, "5".repeat(40), archive.sha256(), "0".repeat(64))
            val getter = PrepareCodexIosSourceTask::class.java.getMethod("getPatches")

            assertTrue(getter.isAnnotationPresent(InputFiles::class.java))
            assertEquals(
                PathSensitivity.RELATIVE,
                getter.getAnnotation(PathSensitive::class.java).value,
            )
        } finally {
            project.deleteRecursively()
        }
    }

    private fun fixture() = createTempDirectory("codex-ios-source-task").toFile()

    private fun task(
        projectDirectory: File,
        revision: String,
        archiveHash: String,
        cargoLockHash: String,
        preparedCargoLockHash: String = cargoLockHash,
    ): PrepareCodexIosSourceTask {
        val sqliteSource = "sqlite-original\n".encodeToByteArray()
        val sqliteArchive = projectDirectory.resolve("libsqlite3-sys.crate")
        writeTarGz(
            sqliteArchive,
            mapOf("libsqlite3-sys-0.37.0/sqlite3/sqlite3.c" to sqliteSource),
        )
        projectDirectory.resolve("sqlite.patch").writeText(
            """
            diff --git a/sqlite3/sqlite3.c b/sqlite3/sqlite3.c
            --- a/sqlite3/sqlite3.c
            +++ b/sqlite3/sqlite3.c
            @@ -1 +1 @@
            -sqlite-original
            +sqlite-patched
            """.trimIndent() + "\n",
        )
        val project = ProjectBuilder.builder().withProjectDir(projectDirectory).build()
        return project.tasks.register("prepareCodexIosSource", PrepareCodexIosSourceTask::class.java).get().apply {
            this.revision.set(revision)
            archiveSha256.set(archiveHash)
            cargoLockSha256.set(cargoLockHash)
            preparedCargoLockSha256.set(preparedCargoLockHash)
            sourceArchive.set(project.layout.projectDirectory.file("codex.tar.gz"))
            sqliteVersion.set("0.37.0")
            sqliteArchiveSha256.set(sqliteArchive.sha256())
            sqliteSourceSha256.set(sqliteSource.sha256())
            patchedSqliteSourceSha256.set("sqlite-patched\n".encodeToByteArray().sha256())
            this.sqliteArchive.set(project.layout.projectDirectory.file("libsqlite3-sys.crate"))
            sqlitePatch.set(project.layout.projectDirectory.file("sqlite.patch"))
            patches.from(project.layout.projectDirectory.file("change.patch"))
            bridgeSource.set(project.layout.projectDirectory.dir("bridge"))
            outputDirectory.set(project.layout.buildDirectory.dir("codex-source"))
        }
    }

    private fun writeTarGz(target: File, entries: Map<String, ByteArray>) {
        GZIPOutputStream(target.outputStream()).use { output ->
            entries.forEach { (name, contents) ->
                val header = ByteArray(512)
                name.toByteArray().copyInto(header)
                octal(header, 100, 8, 493)
                octal(header, 108, 8, 0)
                octal(header, 116, 8, 0)
                octal(header, 124, 12, contents.size.toLong())
                octal(header, 136, 12, 0)
                repeat(8) { header[148 + it] = ' '.code.toByte() }
                header[156] = '0'.code.toByte()
                "ustar\u0000".toByteArray().copyInto(header, 257)
                "00".toByteArray().copyInto(header, 263)
                val checksum = header.sumOf { it.toInt() and 0xff }
                "%06o\u0000 ".format(checksum).toByteArray().copyInto(header, 148)
                output.write(header)
                output.write(contents)
                repeat((512 - contents.size % 512) % 512) { output.write(0) }
            }
            output.write(ByteArray(1024))
        }
    }

    private fun octal(target: ByteArray, offset: Int, length: Int, value: Long) {
        ("%0${length - 1}o\u0000".format(value)).toByteArray().copyInto(target, offset)
    }

    private fun File.sha256() = readBytes().sha256()

    private fun ByteArray.sha256() = MessageDigest.getInstance("SHA-256").digest(this)
        .joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
