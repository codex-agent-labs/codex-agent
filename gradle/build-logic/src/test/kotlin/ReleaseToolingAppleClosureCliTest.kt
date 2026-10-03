import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** CLI routing checks only; the delegated Apple verifier has its own complete synthetic closure tests. */
class ReleaseToolingAppleClosureCliTest {
    @Test
    fun `original package replay requires original binding and event authority without output override`() {
        val values = linkedMapOf("evidence-directory" to "unused", "product-directory" to "unused",
            "version" to "0.8.0", "binary-frameworks" to "unused", "source-snapshot" to "unused",
            "sdk-compatibility" to "unused", "work-directory" to "unused", "execution-binding-file" to "unused",
            "expected-binding-sha256" to "sha256:${"a".repeat(64)}", "expected-execution-files" to "unused",
            "xcode-version" to "26.6", "xcode-build" to "17F113", "swift-version" to "6.3.3")
        val args = arrayOf("verify-original-apple-package-execution",
            *values.flatMap { (key, value) -> listOf("--$key", value) }.toTypedArray())
        values.keys.forEach { missing ->
            val failure = assertFailsWith<IllegalStateException> { runReleaseTooling(args.withoutOption(missing)) }
            assertTrue("Unexpected release-tooling options" in failure.message.orEmpty())
        }
        val failure = assertFailsWith<IllegalStateException> {
            runReleaseTooling(args + arrayOf("--success-output", "unused"))
        }
        assertTrue("Unexpected release-tooling options" in failure.message.orEmpty())
    }

    @Test
    fun `simulator replay requires independent caller pins and forbids output overrides`() {
        val values = linkedMapOf("evidence-directory" to "missing",
            "expected-runtime-name" to "iOS 26.5",
            "expected-device-type-identifier" to "com.apple.CoreSimulator.SimDeviceType.iPhone-17",
            "original-working-directory" to "/original/checkout")
        val args = arrayOf("verify-original-apple-simulator-execution",
            *values.flatMap { (key, value) -> listOf("--$key", value) }.toTypedArray())
        values.keys.forEach { missing ->
            val failure = assertFailsWith<IllegalStateException> { runReleaseTooling(args.withoutOption(missing)) }
            assertTrue("Unexpected release-tooling options" in failure.message.orEmpty())
        }
        val failure = assertFailsWith<IllegalStateException> {
            runReleaseTooling(args + arrayOf("--success-output", "unused"))
        }
        assertTrue("Unexpected release-tooling options" in failure.message.orEmpty())
    }

    @Test
    fun `package evidence capture requires explicit external destination and no success override`() {
        val values = linkedMapOf("product-directory" to "missing", "version" to "0.8.0",
            "binary-frameworks" to "missing", "source-snapshot" to "missing",
            "sdk-compatibility" to "missing", "work-directory" to "missing",
            "developer-directory" to "missing", "xcode-version" to "26.6",
            "xcode-build" to "17F113", "swift-version" to "6.3.3",
            "execution-evidence-directory" to "missing", "execution-binding-file" to "missing")
        val args = arrayOf("capture-apple-binary-package-evidence",
            *values.flatMap { (key, value) -> listOf("--$key", value) }.toTypedArray())
        values.keys.forEach { missing ->
            val error = assertFailsWith<IllegalStateException> { runReleaseTooling(args.withoutOption(missing)) }
            assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
        }
        val error = assertFailsWith<IllegalStateException> { runReleaseTooling(args) }
        assertTrue("Apple binary package tooling input is missing" in error.message.orEmpty())
        assertFailsWith<IllegalStateException> { runReleaseTooling(args + arrayOf("--success-output", "missing")) }
    }

    @Test
    fun `selected validation binding replay requires every independent input and accepts no output override`() {
        val values = linkedMapOf("evidence-directory" to "unused", "product-directory" to "unused",
            "version" to "0.8.0", "sdk-compatibility" to "unused", "canonical-api" to "unused",
            "canonical-coverage" to "unused", "consumer-source-directory" to "unused", "work-directory" to "unused")
        val args = arrayOf("verify-apple-validation-binding-content",
            *values.flatMap { (key, value) -> listOf("--$key", value) }.toTypedArray())
        values.keys.forEach { missing ->
            val error = assertFailsWith<IllegalStateException> { runReleaseTooling(args.withoutOption(missing)) }
            assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
        }
        val error = assertFailsWith<IllegalStateException> {
            runReleaseTooling(args + arrayOf("--success-output", "unused"))
        }
        assertTrue("Unexpected release-tooling options" in error.message.orEmpty())
    }

    @Test
    fun `binary replay requires complete caller inputs and packaged command fails before native tools`() {
        val root = createTempDirectory("apple-binary-cli-").toFile().canonicalFile
        try {
            val values = linkedMapOf("product-directory" to root.resolve("missing-product").path,
                "version" to "0.8.0", "binary-frameworks" to root.resolve("missing-binary").path,
                "source-snapshot" to root.resolve("missing-source").path,
                "sdk-compatibility" to root.resolve("missing-compatibility").path,
                "work-directory" to root.resolve("work").path,
                "developer-directory" to root.resolve("missing-developer").path,
                "xcode-version" to "26.6", "xcode-build" to "17F113", "swift-version" to "6.3.3")
            val args = arrayOf("verify-apple-binary-package", *values.flatMap { (key, value) -> listOf("--$key", value) }.toTypedArray())
            values.keys.forEach { missing ->
                val failure = assertFailsWith<IllegalStateException> { runReleaseTooling(args.withoutOption(missing)) }
                assertTrue("Unexpected release-tooling options" in failure.message.orEmpty())
            }
            assertFailsWith<IllegalStateException> { runReleaseTooling(args + arrayOf("--success-output", "unused")) }
            val java = java.io.File(System.getProperty("java.home"), "bin/java")
            val jar = checkNotNull(System.getProperty("codexAgent.releaseToolingJar"))
            val process = ProcessBuilder(listOf(java.path, "-jar", jar) + args).directory(root)
                .redirectErrorStream(true).start()
            process.outputStream.close()
            val output = process.inputStream.bufferedReader().use { it.readText() }
            assertTrue(process.waitFor() != 0, output)
            assertTrue("Apple binary package tooling input is missing" in output, output)
            assertEquals(emptyList(), root.listFiles()!!.toList())
        } finally {
            root.deleteRecursively()
        }
    }

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
