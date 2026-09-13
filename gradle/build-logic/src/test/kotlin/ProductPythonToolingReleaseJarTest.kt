import java.io.File
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith

class ProductPythonToolingReleaseJarTest {
    private val releaseToolingJar = File(checkNotNull(System.getProperty("codexAgent.releaseToolingJar")))

    @Test
    fun `fat jar inspects a Runtime manifest using only its exact packaged Python closure`() {
        val root = createTempDirectory("release-tooling-python").toFile()
        try {
            val jar = releaseToolingJar.copyTo(root.resolve("release-tooling.jar"))
            assertEquals((productPythonResources.values.flatten() +
                listOf("ci/products/__init__.py", "ci/products/inventory.py"))
                .map { "python/$it" }.toSet(), jar.pythonProductResources())

            val manifest = root.resolve("runtime-manifest.json").apply { writeText(runtimeManifest()) }
            val hostilePython = root.resolve("hostile-python/ci/products").apply { mkdirs() }
            val fallbackMarker = root.resolve("repository-source-fallback-ran")
            hostilePython.resolve("runtime_evidence.py").writeText(
                "from pathlib import Path\nPath(${fallbackMarker.absolutePath.quotePython()}).write_text('used')\n",
            )
            hostilePython.parentFile.parentFile.resolve("sitecustomize.py").writeText(
                "from pathlib import Path\nPath(${fallbackMarker.absolutePath.quotePython()}).write_text('site')\n",
            )

            val java = File(System.getProperty("java.home"), "bin/${if (isWindows()) "java.exe" else "java"}")
            val process = ProcessBuilder(
                java.absolutePath,
                "-jar",
                jar.absolutePath,
                "inspect-runtime-manifest",
                "--manifest",
                manifest.absolutePath,
            )
                .directory(root)
                .redirectErrorStream(true)
                .apply {
                    environment()["PYTHONPATH"] = hostilePython.parentFile.parentFile.absolutePath
                    environment()["PYTHONHOME"] = root.resolve("not-a-python-installation").absolutePath
                    environment()["PYTHONPYCACHEPREFIX"] = root.resolve("hostile-cache").absolutePath
                }
                .start()
            val output = process.inputStream.bufferedReader().use { it.readText() }
            val exit = process.waitFor()

            assertFalse(
                "Unknown release-tooling command" in output,
                "releaseToolingJar has no public inspect-runtime-manifest seam that reaches packaged " +
                    "ci.products.runtime_evidence inspect-manifest: $output",
            )
            assertEquals(0, exit, output)
            assertEquals("0.149.0 rust-v0.149.0 5", output.trim())
            assertFalse(fallbackMarker.exists(), "release tooling loaded Python outside its fat JAR")
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged native import closure and fixed cpp verifier require no checkout scripts`() {
        assertTrue("verify-native" in runProductPythonModule("sdk_package", listOf("--help")))
        assertTrue("--expected-test-program" in runProductPythonModule("cpp_package", listOf("verify-evidence", "--help")))
        assertFailsWith<IllegalStateException> { runProductPythonModule("cpp_package", listOf("--help")) }
        assertFailsWith<IllegalStateException> { runProductPythonModule("arbitrary", emptyList()) }
        assertTrue("--source" in runProductPythonModule("receipt", listOf("snapshot-tree", "--help")))
        assertTrue("--product-version" in runProductPythonModule("receipt", listOf("verify-output-manifest", "--help")))
        listOf("--help", "write-phase-receipt", "write-output-manifest").forEach { command ->
            assertFailsWith<IllegalStateException> { runProductPythonModule("receipt", listOf(command)) }
        }
    }

    private fun File.pythonProductResources(): Set<String> = ZipFile(this).use { archive ->
        archive.entries().asSequence()
            .filter { !it.isDirectory && it.name.startsWith("python/") }
            .map { it.name }
            .toSet()
    }

    private fun runtimeManifest(): String {
        val digest = "0".repeat(64)
        val distributions = RUNTIME_TARGETS.joinToString(",") { target ->
            """{"target":"$target","classifier":"app-server-$target","asset":"$target.zip","archiveSha256":"$digest","archiveEntry":"server-$target","binarySha256":"$digest","executableName":"server","supervisorExecutableName":"supervisor"}"""
        }
        return """{"version":"0.149.0","releaseTag":"rust-v0.149.0","distributions":[$distributions]}""" + "\n"
    }

    private fun String.quotePython() = "'" + replace("\\", "\\\\").replace("'", "\\'") + "'"

    private fun isWindows() = System.getProperty("os.name").startsWith("Windows")

    private companion object {
        val RUNTIME_TARGETS = listOf("macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64")
    }
}
