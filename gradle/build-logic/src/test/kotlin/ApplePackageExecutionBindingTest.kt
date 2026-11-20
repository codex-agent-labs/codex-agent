import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ApplePackageExecutionBindingTest {
    @Test
    fun `writes exact original input and lexical context binding without a verdict`() {
        Fixture().use { fixture ->
            val original = fixture.capture()
            writeApplePackageExecutionBinding(
                fixture.binding,
                fixture.context,
                original,
                fixture.product,
                fixture.binary,
                fixture.source,
                fixture.compatibility,
            )

            val binding = fixture.binding.readReleaseObject()
            assertEquals(setOf("schemaVersion", "context", "inputs"), binding.keys)
            assertEquals(1, binding.releaseInt("schemaVersion"))
            assertEquals(setOf(
                "scratchDirectory", "workDirectory", "sourceSnapshot", "binaryFrameworks", "developerDirectory",
            ), binding.releaseObject("context").keys)
            assertEquals(fixture.context.scratchDirectory.path,
                binding.releaseObject("context").releaseString("scratchDirectory"))
            assertEquals(setOf("product", "binary", "source", "compatibility"),
                binding.releaseObject("inputs").keys)
            assertFalse(fixture.binding.readText().contains("evidence", ignoreCase = true))
            assertFalse(fixture.binding.readText().contains("result", ignoreCase = true))
            assertEquals(original, fixture.capture())
        }
    }

    @Test
    fun `rejects changed originals before publication`() {
        listOf("product", "binary", "source", "compatibility").forEach { mutation ->
            Fixture().use { fixture ->
                val original = fixture.capture()
                when (mutation) {
                    "product" -> fixture.product.resolve("artifact.zip").appendText("changed")
                    "binary" -> fixture.binary.resolve("ios-arm64/CodexAgent.framework/CodexAgent")
                        .appendText("changed")
                    "source" -> fixture.source.resolve("Package.swift").appendText("changed")
                    "compatibility" -> fixture.compatibility.appendText("changed")
                }
                val failure = assertFailsWith<IllegalStateException>(mutation) {
                    writeApplePackageExecutionBinding(
                        fixture.binding,
                        fixture.context,
                        original,
                        fixture.product,
                        fixture.binary,
                        fixture.source,
                        fixture.compatibility,
                    )
                }
                assertTrue("input changed before binding" in failure.message.orEmpty())
                assertFalse(fixture.binding.exists())
            }
        }
    }

    @Test
    fun `rejects stale overlapping and symlink output without modifying it`() {
        Fixture().use { fixture ->
            val original = fixture.capture()
            fixture.binding.parentFile.mkdirs()
            fixture.binding.writeText("user-owned")
            assertFailsWith<IllegalStateException> {
                fixture.write(original, fixture.binding)
            }
            assertEquals("user-owned", fixture.binding.readText())
        }
        Fixture().use { fixture ->
            val original = fixture.capture()
            assertFailsWith<IllegalStateException> {
                fixture.write(original, fixture.source.resolve("binding.json"))
            }
        }
        Fixture().use { fixture ->
            val original = fixture.capture()
            val target = fixture.root.resolve("target").apply { mkdirs() }
            val link = fixture.root.resolve("link")
            Files.createSymbolicLink(link.toPath(), target.toPath())
            assertFailsWith<IllegalStateException> {
                fixture.write(original, link.resolve("binding.json"))
            }
            assertFalse(target.resolve("binding.json").exists())
        }
    }

    @Test
    fun `rejects context that does not name the captured source and binary roots`() {
        Fixture().use { fixture ->
            val original = fixture.capture()
            val unrelated = fixture.root.resolve("unrelated-source").apply {
                mkdirs(); resolve("Package.swift").writeText("unrelated")
            }
            val failure = assertFailsWith<IllegalStateException> {
                writeApplePackageExecutionBinding(
                    fixture.binding,
                    fixture.context.copy(sourceSnapshot = unrelated),
                    original,
                    fixture.product,
                    fixture.binary,
                    fixture.source,
                    fixture.compatibility,
                )
            }
            assertTrue("does not bind" in failure.message.orEmpty())
            assertFalse(fixture.binding.exists())
        }
    }

    @Test
    fun `rejects overlapping context roles`() {
        Fixture().use { fixture ->
            val original = fixture.capture()
            val failure = assertFailsWith<IllegalStateException> {
                writeApplePackageExecutionBinding(
                    fixture.binding,
                    fixture.context.copy(workDirectory = fixture.context.scratchDirectory),
                    original,
                    fixture.product,
                    fixture.binary,
                    fixture.source,
                    fixture.compatibility,
                )
            }
            assertTrue("context paths overlap" in failure.message.orEmpty())
            assertFalse(fixture.binding.exists())
        }
    }

    private class Fixture : AutoCloseable {
        val root = createTempDirectory("apple-package-binding-").toFile().canonicalFile
        val product = root.resolve("product").apply { mkdirs(); resolve("artifact.zip").writeText("product") }
        val binary = root.resolve("binary").apply {
            resolve("ios-arm64/CodexAgent.framework/CodexAgent").also {
                it.parentFile.mkdirs(); it.writeText("binary")
            }
        }
        val source = root.resolve("source").apply { mkdirs(); resolve("Package.swift").writeText("source") }
        val compatibility = root.resolve("sdk-compatibility.json").apply { writeText("compatibility") }
        val binding = root.resolve("transport/original-inputs.json")
        val context = ApplePackageExecutionContext(
            root.resolve("scratch").apply { mkdirs() },
            root.resolve("work").apply { mkdirs() },
            source,
            binary,
            root.resolve("developer").apply { mkdirs() },
        )

        fun capture() = captureApplePackageExecutionInputs(product, binary, source, compatibility)

        fun write(original: Map<String, Map<String, String>>, output: java.io.File) =
            writeApplePackageExecutionBinding(output, context, original, product, binary, source, compatibility)

        override fun close() = root.deleteRecursively().let { Unit }
    }
}
