import java.io.File
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

/** Artifact comparison fixtures only; they grant no receipt, producer, host, or replay authority. */
class AppleValidationPackageInputsTest {
    @Test
    fun `extracts exact authenticated package inputs without changing originals`() = fixture().use { fixture ->
        val before = fixture.inputDigests()

        val result = fixture.prepare()

        assertEquals(before, fixture.inputDigests())
        assertEquals(fixture.packageDigests(), result.packageDirectory.digests())
        assertEquals(
            fixture.xcframeworkDigests().keys + fixture.compatibilityPaths,
            result.xcframeworkDirectory.digests().keys,
        )
        fixture.xcframeworkDigests().forEach { (path, digest) ->
            assertEquals(digest, result.xcframeworkDirectory.digests().getValue(path), path)
        }
    }

    @Test
    fun `rejects embedded framework drift and nonexact compatibility decoration`() {
        listOf("embedded", "missing", "extra", "drift").forEach { mutation ->
            fixture().use { fixture ->
                when (mutation) {
                    "embedded" -> fixture.writePackageArchive(overrides = mapOf(
                        "CodexAgent.xcframework/${fixture.pathFor("native")}" to "changed\n".toByteArray(),
                    ))
                    "missing" -> fixture.writeSwiftArchive(omitted = setOf(fixture.compatibilityPaths.last()))
                    "extra" -> fixture.writeSwiftArchive(extras = mapOf(
                        "CodexAgent.xcframework/unexpected/sdk-compatibility.json" to
                            fixture.compatibility.readBytes(),
                    ))
                    else -> fixture.writeSwiftArchive(overrides = mapOf(
                        fixture.compatibilityPaths.last() to "changed\n".toByteArray(),
                    ))
                }

                assertFailsWith<IllegalStateException>(mutation) { fixture.prepare() }
            }
        }
    }

    @Test
    fun `rejects malformed inventory checksum archive and work paths`() {
        fixture().use { fixture ->
            fixture.product.resolve("extra").writeText("extra")
            assertFailsWith<IllegalStateException> { fixture.prepare() }
        }
        fixture().use { fixture ->
            fixture.product.resolve("CodexAgent-0.2.0.xcframework.zip.sha256").writeText("0".repeat(64))
            assertFailsWith<IllegalStateException> { fixture.prepare() }
        }
        fixture().use { fixture ->
            fixture.writePackageArchive(extras = mapOf("../escape" to "unsafe\n".toByteArray()))
            assertFailsWith<IllegalStateException> { fixture.prepare() }
            assertEquals(false, fixture.root.resolve("escape").exists())
        }
        fixture().use { fixture ->
            fixture.work.mkdirs()
            assertFailsWith<IllegalStateException> { fixture.prepare() }
        }
        fixture().use { fixture ->
            assertFailsWith<IllegalStateException> { fixture.prepare(work = fixture.product.resolve("work")) }
        }
    }

    @Test
    fun `rejects symbolic compatibility inputs without changing originals`() = fixture().use { fixture ->
        val before = fixture.inputDigests()
        val parent = fixture.root.resolve("compatibility-link").toPath()
        Files.createSymbolicLink(parent, fixture.compatibility.parentFile.toPath())

        assertFailsWith<IllegalStateException> {
            fixture.prepare(compatibility = parent.resolve(fixture.compatibility.name).toFile())
        }
        assertEquals(before, fixture.inputDigests())
    }
}

private fun AppleBinaryPackageContentFixture.prepare(
    compatibility: File = this.compatibility,
    work: File = this.work,
) = prepareAppleValidationPackageInputs(product, "0.2.0", compatibility, work)

private fun File.digests() = verifiedRegularFiles(this).mapValues { (_, file) -> file.releaseDigest() }

private fun fixture() = AppleBinaryPackageContentFixture()
