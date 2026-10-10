import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ImportedRuntimeVariantTaskTest {
    @Test
    fun `delegates exact private inputs and retains only producer product bytes`() = fixture { root, inputs, output ->
        val original = inputs.mapValues { it.value.readBytes().toList() }
        var captured: List<File> = emptyList()
        produceImportedRuntimeVariant("macos-arm64", inputs, output, root.resolve("build")) { command ->
            assertEquals(listOf("python3", "-m", "ci.products.runtime_variant"), command.take(3))
            val options = command.drop(3).chunked(2).associate { it[0] to File(it[1]) }
            assertEquals(inputs.keys.map { "--$it" }.toSet() + "--output-directory", options.keys)
            captured = inputs.map { (name, source) ->
                options.getValue("--$name").also { snapshot ->
                    assertTrue(snapshot.toPath().startsWith(root.resolve("build/tmp").toPath()))
                    assertFalse(snapshot.toPath().startsWith(output.toPath()))
                    assertEquals(source.name, snapshot.name)
                    assertEquals(source.readBytes().toList(), snapshot.readBytes().toList())
                }
            }
            assertEquals(output, options.getValue("--output-directory"))
            // Stub only the already-tested Python producer. This is not a real variant/host proof.
            output.resolve(bundleName).writeText("opaque fixture product bytes")
        }
        assertEquals(original, inputs.mapValues { it.value.readBytes().toList() })
        assertEquals(listOf(bundleName), output.listFiles()!!.map(File::getName))
        assertTrue(captured.all { !it.exists() })
        assertFalse(output.parentFile.resolve("output-manifest.json").exists())
    }

    @Test
    fun `invalid original input target and output scopes preserve prior stage`() = fixture { root, inputs, output ->
        val sentinel = output.resolve("previous").apply { parentFile.mkdirs(); writeText("preserved") }
        val manifest = output.parentFile.resolve("output-manifest.json").apply { writeText("prior manifest") }
        val run: (List<String>) -> Unit = { error("Producer must not execute") }
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("linux-x64", inputs, output, root.resolve("build"), run = run)
        }
        val original = inputs.getValue("binary-receipt").readBytes()
        inputs.getValue("binary-receipt").delete()
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", inputs, output, root.resolve("build"), run = run)
        }
        inputs.getValue("binary-receipt").writeBytes(original)
        val overlap = inputs + ("binary-receipt" to manifest)
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", overlap, output, root.resolve("build"), run = run)
        }
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", inputs, output, root.resolve("build"),
                protectedSources = listOf(manifest), run = run)
        }
        val temporarySentinel = root.resolve("build/tmp/preserved").apply {
            parentFile.mkdirs(); writeText("temporary workspace")
        }
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", inputs, root.resolve("build/tmp/outputs"),
                root.resolve("build"), run = run)
        }
        val link = root.resolve("build/link").toPath()
        Files.createSymbolicLink(link, output.parentFile.toPath())
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", inputs, link.resolve("../other/outputs").toFile(),
                root.resolve("build"), run = run)
        }
        assertEquals("preserved", sentinel.readText())
        assertEquals("prior manifest", manifest.readText())
        assertEquals("temporary workspace", temporarySentinel.readText())
    }

    @Test
    fun `symbolic child in previous stage preserves external and previous evidence`() = fixture { root, inputs, output ->
        val sentinel = output.resolve("previous").apply { parentFile.mkdirs(); writeText("prior") }
        val external = root.resolve("external/retained").apply { parentFile.mkdirs(); writeText("original") }
        Files.createSymbolicLink(output.resolve("symbolic").toPath(), external.parentFile.toPath())
        assertFailsWith<IllegalStateException> {
            produceImportedRuntimeVariant("macos-arm64", inputs, output, root.resolve("build")) {
                error("Producer must not execute")
            }
        }
        assertEquals("prior", sentinel.readText())
        assertEquals("original", external.readText())
        Files.delete(output.resolve("symbolic").toPath())
    }

    @Test
    fun `failure unexpected output and changed original clear stage but retain original evidence`() {
        for (mutation in listOf("failure", "extra", "source")) fixture { root, inputs, output ->
            val original = inputs.getValue("validation-receipt").readText()
            assertFailsWith<IllegalStateException> {
                produceImportedRuntimeVariant("macos-arm64", inputs, output, root.resolve("build")) {
                    output.resolve(bundleName).writeText("fixture bytes")
                    when (mutation) {
                        "failure" -> error("original producer rejection")
                        "extra" -> output.resolve("receipt.json").writeText("must remain external")
                        "source" -> inputs.getValue("validation-evidence").appendText("changed")
                    }
                }
            }
            assertFalse(output.parentFile.exists())
            assertEquals(original, inputs.getValue("validation-receipt").readText())
            assertEquals(emptyList(), root.resolve("build/tmp").listFiles()!!.toList())
        }
    }

    @Test
    fun `native metadata wiring imports originals with no live validation dependency`() {
        val repository = generateSequence(File(".").canonicalFile) { it.parentFile }
            .first { it.resolve("codex-agent-runtime-desktop/build.gradle.kts").isFile }
        val source = repository.resolve("codex-agent-runtime-desktop/build.gradle.kts").readText()
        val native = source.substringAfter("runtimeNativeMetadataComponents.forEach")
            .substringBefore("val runtimeAdapterMetadataComponents")
        assertTrue("tasks.register<ImportedRuntimeVariantTask>" in native)
        assertTrue("mapOf(\"runtime-variant\" to \"outputs\")" in native)
        assertFalse("tasks.named(validation" in native)
        assertFalse("dependsOn(" in native)
        assertFalse("validation-output-manifest.json" in native)
        listOf("Identity", "BinaryReceipt", "PackageReceipt", "ValidationReceipt", "CAbiArchive",
            "AppServerArchive", "ValidationEvidence").forEach { assertTrue("imported(\"$it\")" in native) }
    }

    private fun fixture(action: (File, Map<String, File>, File) -> Unit) {
        val root = createTempDirectory("runtime-variant-task-").toFile().canonicalFile
        try {
            val inputs = linkedMapOf<String, File>()
            listOf("identity", "binary-receipt", "package-receipt", "validation-receipt", "c-abi-archive",
                "app-server-archive", "validation-evidence", "distribution-manifest").forEach { name ->
                inputs[name] = root.resolve("inputs/$name/original-$name.json").apply {
                    parentFile.mkdirs()
                    writeText(if (name == "identity")
                        """{"target":"macos-arm64","componentId":"sha256:${"a".repeat(64)}"}"""
                    else "original $name bytes\n")
                }
            }
            action(root, inputs, root.resolve("build/product-stage/runtime/macos-arm64/metadata/outputs"))
        } finally {
            root.deleteRecursively()
        }
    }

    private val bundleName = "codex-agent-runtime-variant-macos-arm64-${"a".repeat(64)}.zip"
}
