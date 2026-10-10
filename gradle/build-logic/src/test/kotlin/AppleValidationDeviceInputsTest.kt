import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder

/** Copy and Gradle wiring fixtures only; they grant no source, host, or execution authority. */
class AppleValidationDeviceInputsTest {
    @Test
    fun `task stages exact consumer and package bytes`() = fixture().use { fixture ->
        val task = fixture.task()
        val before = fixture.inputDigests()

        task.stage()

        assertEquals(before, fixture.inputDigests())
        assertEquals(fixture.testApplication.digests(), task.stagedTestApplicationDirectory.get().asFile.digests())
        assertEquals(fixture.packageDirectory.digests(), task.stagedPackageDirectory.get().asFile.digests())
        assertEquals(fixture.work.resolve("CodexAgentTestApp"), task.stagedTestApplicationDirectory.get().asFile)
        assertEquals(fixture.work.resolve("CodexAgentPackage"), task.stagedPackageDirectory.get().asFile)
    }

    @Test
    fun `rejects missing and empty required inputs`() {
        listOf("project", "manifest", "empty").forEach { mutation ->
            fixture().use { fixture ->
                when (mutation) {
                    "project" -> fixture.testApplication.resolve(
                        "CodexAgentTestApp.xcodeproj/project.pbxproj",
                    ).delete()
                    "manifest" -> fixture.packageDirectory.resolve("Package.swift").delete()
                    else -> fixture.packageDirectory.resolve("Sources/Client.swift").writeBytes(byteArrayOf())
                }
                assertFailsWith<IllegalStateException>(mutation) { fixture.task().stage() }
                assertFalse(fixture.work.exists())
            }
        }
    }

    @Test
    fun `rejects symbolic inputs without creating output`() = fixture().use { fixture ->
        val link = fixture.testApplication.resolve("Sources/Linked.swift").toPath()
        Files.createSymbolicLink(link, fixture.testApplication.resolve("Sources/App.swift").toPath())

        assertFailsWith<IllegalStateException> { fixture.task().stage() }

        assertFalse(fixture.work.exists())
    }

    @Test
    fun `rejects stale and overlapping work without deleting caller files`() {
        fixture().use { fixture ->
            val marker = fixture.work.apply { mkdirs() }.resolve("caller-marker").apply {
                writeText("preserve\n")
            }
            assertFailsWith<IllegalStateException> { fixture.task().stage() }
            assertTrue(marker.isFile)
            assertEquals("preserve\n", marker.readText())
        }
        fixture().use { fixture ->
            val before = fixture.inputDigests()
            assertFailsWith<IllegalStateException> {
                fixture.task(work = fixture.packageDirectory.resolve("work")).stage()
            }
            assertEquals(before, fixture.inputDigests())
        }
    }
}

private class AppleValidationDeviceFixture : AutoCloseable {
    val root = createTempDirectory("apple-validation-device").toFile().canonicalFile
    val testApplication = root.resolve("test-application")
    val packageDirectory = root.resolve("package")
    val work = root.resolve("work")

    init {
        testApplication.resolve("CodexAgentTestApp.xcodeproj/project.pbxproj").fixture("project\n")
        testApplication.resolve("Sources/App.swift").fixture("app\n")
        packageDirectory.resolve("Package.swift").fixture("// swift-tools-version: 6.0\n")
        packageDirectory.resolve("Sources/Client.swift").fixture("client\n")
    }

    fun task(work: File = this.work) = ProjectBuilder.builder()
        .withProjectDir(root.resolve("project").apply { mkdirs() }).build().tasks.create(
            "stageAppleValidationDeviceInputs",
            StageAppleValidationDeviceInputsTask::class.java,
        ).apply {
            testApplicationDirectory.set(testApplication)
            packageDirectory.set(this@AppleValidationDeviceFixture.packageDirectory)
            workDirectory.set(work)
        }

    fun inputDigests() = mapOf(
        "test-application" to testApplication.digests(),
        "package" to packageDirectory.digests(),
    )

    override fun close() {
        root.deleteRecursively()
    }
}

private fun File.fixture(contents: String) {
    parentFile.mkdirs()
    writeText(contents)
}

private fun File.digests() = verifiedRegularFiles(this).mapValues { (_, file) -> file.releaseDigest() }

private fun fixture() = AppleValidationDeviceFixture()
