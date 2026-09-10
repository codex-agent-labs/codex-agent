import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** CLI routing checks only; the delegated Apple verifier has its own complete synthetic closure tests. */
class ReleaseToolingAppleClosureCliTest {
    @Test
    fun `original Apple replay cannot omit caller authority or accept a success output`() {
        val args = arrayOf("verify-original-apple-execution",
            "--distribution-directory", "unused", "--execution-directory", "unused",
            "--expected-distribution-proof", "unused", "--expected-sdk-compatibility", "unused")
        for (missing in listOf("expected-distribution-proof", "expected-sdk-compatibility")) {
            val error = assertFailsWith<IllegalStateException> {
                runReleaseTooling(args.withoutOption(missing))
            }
            assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
        }
        val error = assertFailsWith<IllegalStateException> {
            runReleaseTooling(args + arrayOf("--success-output", "unused"))
        }
        assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
    }

    @Test
    fun `caller-bound Apple command requires both expectations and rejects output options`() = fixture().use { fixture ->
        listOf("expected-sdk-compatibility", "expected-distribution-proof").forEach { missing ->
            val error = assertFailsWith<IllegalStateException>(missing) {
                runReleaseTooling(fixture.arguments().withoutOption(missing))
            }
            assertTrue("Unexpected release-tooling options" in error.message.orEmpty(), missing)
            assertEquals("preserved", fixture.work.resolve("sentinel").readText(), missing)
        }

        val error = assertFailsWith<IllegalStateException> {
            runReleaseTooling(fixture.arguments() + arrayOf("--success-output", fixture.root.resolve("success").path))
        }
        assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
        assertEquals("preserved", fixture.work.resolve("sentinel").readText())
    }

    @Test
    fun `complete Apple command delegates both caller-bound files to the existing verifier`() = fixture().use { fixture ->
        listOf(fixture.expectedCompatibility, fixture.expectedProof).forEach { missing ->
            val bytes = missing.readBytes()
            assertTrue(missing.delete())
            val error = assertFailsWith<IllegalStateException>(missing.name) { runReleaseTooling(fixture.arguments()) }
            assertTrue("caller expectation is missing or unsafe" in error.message.orEmpty(), error.message)
            missing.writeBytes(bytes)
        }

        val error = assertFailsWith<IllegalStateException> { runReleaseTooling(fixture.arguments()) }
        assertTrue("Transported Apple SDK product inventory mismatch" in error.message.orEmpty(), error.message)
        assertEquals("compatibility", fixture.expectedCompatibility.readText())
        assertEquals("proof", fixture.expectedProof.readText())
        assertEquals("preserved", fixture.work.resolve("sentinel").readText())
    }
}

private class ReleaseToolingAppleClosureCliFixture : AutoCloseable {
    val root = createTempDirectory("release-tooling-apple-closure").toFile().canonicalFile
    private val product = root.resolve("product").apply { mkdirs() }
    private val evidence = root.resolve("validation-evidence").apply { mkdirs() }
    private val owned = root.resolve("owned").apply { mkdirs() }
    val work = owned.resolve("work").apply { mkdirs(); resolve("sentinel").writeText("preserved") }
    val expectedCompatibility = root.resolve("sdk-compatibility.json").apply { writeText("compatibility") }
    val expectedProof = root.resolve("verified-distribution-proof.json").apply { writeText("proof") }

    fun arguments() = arrayOf(
        "verify-transported-apple-sdk-package-closure",
        "--product-directory", product.path,
        "--validation-evidence-directory", evidence.path,
        "--version", "0.2.0",
        "--owned-build-directory", owned.path,
        "--work-directory", work.path,
        "--expected-sdk-compatibility", expectedCompatibility.path,
        "--expected-distribution-proof", expectedProof.path,
    )

    override fun close() { root.deleteRecursively() }
}

private fun fixture() = ReleaseToolingAppleClosureCliFixture()

private fun Array<String>.withoutOption(name: String): Array<String> {
    val index = indexOf("--$name")
    check(index >= 0)
    return filterIndexed { itemIndex, _ -> itemIndex != index && itemIndex != index + 1 }.toTypedArray()
}
