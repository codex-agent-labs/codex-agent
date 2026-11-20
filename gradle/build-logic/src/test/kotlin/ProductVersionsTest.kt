import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ProductVersionsTest {
    @Test
    fun `reader accepts exact SemVer authority bytes`() = withVersionFile("0.2.0\n") { file ->
        assertEquals("0.2.0", readProductVersion(file))
    }

    @Test
    fun `reader accepts prerelease identifiers and rejects build metadata`() {
        withVersionFile("1.2.3-rc.1\n") { file ->
            assertEquals("1.2.3-rc.1", readProductVersion(file))
        }
        withVersionFile("1.2.3+build.7\n") { file ->
            assertFailsWith<IllegalStateException> { readProductVersion(file) }
        }
    }

    @Test
    fun `runtime compatibility line ignores only aggregate patch and prerelease identity`() {
        assertEquals("0.2.0", runtimeCompatibilityVersion("0.2.0"))
        assertEquals("0.2.0", runtimeCompatibilityVersion("0.2.1"))
        assertEquals("0.2.0", runtimeCompatibilityVersion("0.2.1-rc.1"))
        assertEquals("0.3.0", runtimeCompatibilityVersion("0.3.0"))
        for (invalid in listOf("0.2", "v0.2.1", "0.2.1+build")) {
            assertFailsWith<IllegalStateException>(invalid) { runtimeCompatibilityVersion(invalid) }
        }
    }

    @Test
    fun `reader rejects noncanonical file bytes`() {
        listOf(
            "0.2.0",
            "0.2.0\n\n",
            "0.2.0\r\n",
            " 0.2.0\n",
            "0.2.0 \n",
            "0.2.0\t\n",
            "0.2.0\n1.0.0\n",
        ).forEach { contents ->
            withVersionFile(contents) { file ->
                assertFailsWith<IllegalStateException>(contents.toByteArray().contentToString()) {
                    readProductVersion(file)
                }
            }
        }
    }

    @Test
    fun `reader rejects prefixes leading zeros and malformed identifiers`() {
        listOf(
            "v0.2.0",
            "01.2.3",
            "1.02.3",
            "1.2.03",
            "1.2",
            "1.2.3-",
            "1.2.3-01",
            "1.2.3-alpha..1",
            "1.2.3+",
            "1.2.3+build..1",
            "1.2.3_alpha",
        ).forEach { version ->
            withVersionFile("$version\n") { file ->
                assertFailsWith<IllegalStateException>(version) { readProductVersion(file) }
            }
        }
    }

    @Test
    fun `reader rejects missing unsafe empty and non ASCII authorities`() {
        val root = createTempDirectory("product-version-authority").toFile()
        try {
            assertFailsWith<IllegalStateException> { readProductVersion(root.resolve("missing.txt")) }
            assertFailsWith<IllegalStateException> { readProductVersion(root) }
            assertFailsWith<IllegalStateException> {
                readProductVersion(root.resolve("empty.txt").apply { writeBytes(byteArrayOf()) })
            }
            assertFailsWith<IllegalStateException> {
                readProductVersion(root.resolve("unicode.txt").apply {
                    writeBytes(byteArrayOf('1'.code.toByte(), '.'.code.toByte(), '0'.code.toByte(), '.'.code.toByte(),
                        '0'.code.toByte(), '-'.code.toByte(), 0xc3.toByte(), 0xa9.toByte(), '\n'.code.toByte()))
                })
            }
            val target = root.resolve("target.txt").apply { writeText("0.2.0\n") }
            val link = root.resolve("link.txt")
            runCatching { Files.createSymbolicLink(link.toPath(), target.toPath()) }.getOrNull()?.let {
                assertFailsWith<IllegalStateException> { readProductVersion(link) }
            }
        } finally {
            root.deleteRecursively()
        }
    }

    private fun withVersionFile(contents: String, block: (File) -> Unit) {
        val root = createTempDirectory("product-version").toFile()
        try {
            block(root.resolve("version.txt").apply { writeBytes(contents.toByteArray()) })
        } finally {
            root.deleteRecursively()
        }
    }
}
