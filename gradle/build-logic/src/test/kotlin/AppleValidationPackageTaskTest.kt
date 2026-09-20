import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder

/** Gradle wrapper wiring only; the delegated helper owns archive and content verification. */
class AppleValidationPackageTaskTest {
    @Test
    fun `task exposes the exact extracted package inputs`() = fixture().use { fixture ->
        val task = fixture.task()

        task.prepare()

        assertEquals(fixture.work.resolve("package"), task.packageDirectory.get().asFile)
        assertEquals(fixture.work.resolve("xcframework"), task.xcframeworkDirectory.get().asFile)
        assertEquals(fixture.packageDigests(), task.packageDirectory.get().asFile.digests())
        val xcframework = task.xcframeworkDirectory.get().asFile.digests()
        assertEquals(
            fixture.xcframeworkDigests().keys + fixture.compatibilityPaths,
            xcframework.keys,
        )
        fixture.xcframeworkDigests().forEach { (path, digest) ->
            assertEquals(digest, xcframework.getValue(path), path)
        }
        fixture.compatibilityPaths.forEach { path ->
            assertEquals(fixture.compatibility.releaseDigest(), xcframework.getValue(path), path)
        }
    }

    @Test
    fun `task rejects stale work without deleting its marker`() = fixture().use { fixture ->
        val task = fixture.task()
        val marker = fixture.work.apply { mkdirs() }.resolve("caller-marker").apply {
            writeText("preserve\n")
        }

        assertFailsWith<IllegalStateException> { task.prepare() }

        assertTrue(marker.isFile)
        assertEquals("preserve\n", marker.readText())
    }
}

private fun AppleBinaryPackageContentFixture.task(): PrepareAppleValidationPackageInputsTask =
    ProjectBuilder.builder().withProjectDir(root.resolve("project").apply { mkdirs() }).build().tasks.create(
        "prepareAppleValidationPackageInputs",
        PrepareAppleValidationPackageInputsTask::class.java,
    ).also { task ->
        task.productDirectory.set(product)
        task.sdkVersion.set("0.2.0")
        task.sdkCompatibility.set(compatibility)
        task.workDirectory.set(work)
    }

private fun java.io.File.digests() =
    verifiedRegularFiles(this).mapValues { (_, file) -> file.releaseDigest() }

private fun fixture() = AppleBinaryPackageContentFixture()
