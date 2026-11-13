import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testfixtures.ProjectBuilder

class RuntimeAdapterMetadataInputsTaskTest {
    @Test
    fun `task conventions identify only the selected adapter metadata stage`() = fixture { value ->
        val project = ProjectBuilder.builder().withProjectDir(value.root.toFile()).build()
        val task = project.tasks.create("verifyInputs", ValidateRuntimeAdapterMetadataInputsTask::class.java)
        task.component.set("node-wasm")
        assertEquals(value.root.resolve("build"), task.ownedBuildDirectory.get().asFile.toPath())
        assertEquals(value.root.resolve("build/product-stage/runtime/node-wasm/metadata"),
            task.stageDirectory.get().asFile.toPath())
        assertEquals(value.root.resolve("build/product-stage/runtime/node-wasm/metadata/outputs"),
            task.outputDirectory.get().asFile.toPath())
    }

    @Test
    fun `valid disjoint inputs survive owned cleanup and semantic verifier receives captured projection`() = fixture { value ->
        val sibling = value.root.resolve("build/product-stage/runtime/node-js/metadata/preserved")
        Files.createDirectories(sibling.parent)
        Files.writeString(sibling, "sibling")
        var calls = 0
        value.verify { component, projection ->
            calls++
            assertEquals("jvm", component)
            assertEquals(value.stage.resolve("outputs/evidence/jvm.json").toFile(), projection)
            assertEquals("original projection", projection.readText())
            assertFalse(Files.exists(value.stage.resolve("output-manifest.json")))
        }
        assertEquals(1, calls)
        assertEquals("original projection", Files.readString(value.projection))
        assertEquals("external original evidence", Files.readString(value.handoff.resolve("original-receipt.json")))
        assertEquals("sibling", Files.readString(sibling))
        assertFalse(Files.exists(value.stage.resolve("outputs/maven")))
    }

    @Test
    fun `input output aliases and out of scope output preserve all originals`() {
        for (mutation in listOf("handoff-child", "handoff-parent", "handoff", "stage")) fixture { value ->
            val handoff = when (mutation) {
                "handoff-child" -> value.stage.resolve("original-handoff").also { Files.createDirectories(it) }
                "handoff-parent" -> value.root.resolve("build")
                "handoff" -> value.stage
                else -> value.handoff
            }
            val projection = handoff.resolve("projection.json")
            if (projection != value.projection) Files.writeString(projection, "original imported projection")
            val stage = if (mutation == "stage") value.root.resolve("inputs") else value.stage
            assertFailsWith<IllegalStateException> {
                verifyRuntimeAdapterMetadataInputs("jvm", handoff, projection, stage,
                    value.root.resolve("build")) { _, _ -> error("Verifier must not run") }
            }
            value.assertPreserved()
            assertTrue(Files.isRegularFile(projection))
        }
    }

    @Test
    fun `symbolic inputs output children and raw symbolic ancestry preserve evidence`() {
        for (mutation in listOf("input-child", "output-child", "parent", "parent-dotdot", "dangling")) fixture { value ->
            val external = value.root.resolve("external").also { Files.createDirectories(it) }
            val sentinel = external.resolve("original").also { Files.writeString(it, "external original") }
            val link = when (mutation) {
                "input-child" -> value.handoff.resolve("unsafe")
                "output-child" -> value.stage.resolve("unsafe")
                else -> value.root.resolve("linked-parent")
            }
            Files.createSymbolicLink(link, if (mutation == "dangling") value.root.resolve("absent") else external)
            try {
                val handoff = when (mutation) {
                    "parent", "dangling" -> link.resolve("repository")
                    "parent-dotdot" -> link.resolve("../inputs/handoff")
                    else -> value.handoff
                }
                assertFailsWith<IllegalStateException> {
                    verifyRuntimeAdapterMetadataInputs("jvm", handoff, handoff.resolve("projection.json"),
                        value.stage, value.root.resolve("build")) { _, _ -> error("Verifier must not run") }
                }
                value.assertPreserved()
                assertEquals("external original", Files.readString(sentinel))
            } finally {
                Files.delete(link)
            }
        }
    }

    @Test
    fun `missing original projection fails before deleting old stage`() = fixture { value ->
        Files.delete(value.projection)
        assertFailsWith<IllegalStateException> {
            value.verify { _, _ -> error("Verifier must not run") }
        }
        assertEquals("prior manifest", Files.readString(value.stage.resolve("output-manifest.json")))
        assertEquals("external original evidence", Files.readString(value.handoff.resolve("original-receipt.json")))
    }

    @Test
    fun `case insensitive input aliases preserve originals before existing or absent stage cleanup`() {
        for (mutation in listOf("equal", "ancestor", "descendant", "absent-stage")) fixture { value ->
            val buildAlias = value.root.resolve("BUILD")
            if (!Files.exists(buildAlias)) {
                // This filesystem has distinct names, so no case alias exists.
                // The conditional is not evidence of a case-insensitive host run.
                assertTrue(Files.isDirectory(value.root.resolve("build")))
                value.assertPreserved()
                return@fixture
            }
            assertTrue(Files.isSameFile(buildAlias, value.root.resolve("build")))
            val stageAlias = buildAlias.resolve("product-stage/runtime/jvm/metadata")
            val handoff = when (mutation) {
                "equal" -> stageAlias
                "descendant" -> stageAlias.resolve("imported-handoff").also { Files.createDirectories(it) }
                else -> buildAlias
            }
            val original = value.root.resolve("build/original-input").also { Files.writeString(it, "original") }
            if (mutation == "absent-stage") {
                Files.walk(value.stage).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
            }
            val projection = handoff.resolve("projection.json").also { Files.writeString(it, "original aliased projection") }
            val failure = assertFailsWith<IllegalStateException> {
                verifyRuntimeAdapterMetadataInputs("jvm", handoff, projection,
                    value.stage, value.root.resolve("build")) { _, _ -> error("Verifier must not run") }
            }
            assertTrue("resolved original input" in failure.message.orEmpty(), failure.message)
            assertEquals("original", Files.readString(original))
            if (mutation == "absent-stage") {
                assertFalse(Files.exists(value.stage))
                assertEquals("original projection", Files.readString(value.projection))
            } else {
                value.assertPreserved()
            }
        }
    }

    @Test
    fun `nonoverlapping semantic failures still remove stale output`() {
        for (mutation in listOf("empty-projection", "projection")) fixture { value ->
            if (mutation == "empty-projection") Files.writeString(value.projection, "")
            var calls = 0
            assertFailsWith<IllegalStateException> {
                value.verify { _, _ ->
                    calls++
                    error("Synthetic semantic rejection, not product verification")
                }
            }
            assertFalse(Files.exists(value.stage))
            assertEquals(if (mutation == "projection") 1 else 0, calls)
            assertEquals(if (mutation == "projection") "original projection" else "", Files.readString(value.projection))
            assertEquals("external original evidence", Files.readString(value.handoff.resolve("original-receipt.json")))
        }
    }

    @Test
    fun `original or staged mutations reject success and remove partial metadata`() {
        for (mutation in listOf("projection", "staged", "extra-staged")) fixture { value ->
            val failure = assertFailsWith<IllegalStateException> {
                value.verify { _, captured ->
                    when (mutation) {
                        "projection" -> Files.writeString(value.projection, "changed original")
                        "staged" -> captured.writeText("changed captured bytes")
                        "extra-staged" -> Files.writeString(value.stage.resolve("outputs/extra.json"), "undeclared bytes")
                    }
                }
            }
            assertTrue("changed during verification" in failure.message.orEmpty(), failure.message)
            assertFalse(Files.exists(value.stage))
            assertTrue(Files.isRegularFile(value.projection))
            assertEquals("external original evidence", Files.readString(value.handoff.resolve("original-receipt.json")))
        }
    }

    @Test
    fun `repeated staging verifies fresh bytes and removes only prior owned output`() = fixture { value ->
        val observed = mutableListOf<String>()
        val verify: (String, File) -> Unit = { _, captured -> observed += captured.readText() }
        value.verify(verify)
        Files.writeString(value.stage.resolve("output-manifest.json"), "prior manifest")
        Files.writeString(value.stage.resolve("outputs/obsolete.json"), "old bytes")
        Files.writeString(value.projection, "new original projection")
        value.verify(verify)
        assertEquals(listOf("original projection", "new original projection"), observed)
        assertFalse(Files.exists(value.stage.resolve("output-manifest.json")))
        assertFalse(Files.exists(value.stage.resolve("outputs/obsolete.json")))
        assertEquals("new original projection", Files.readString(value.stage.resolve("outputs/evidence/jvm.json")))
        assertFalse(Files.exists(value.stage.resolve("outputs/maven")))
    }

    @Test
    fun `all adapters emit only unchanged projection bytes across repeated staging`() {
        for (adapter in listOf("jvm", "node-js", "node-wasm")) fixture(adapter) { value ->
            val obsoleteMaven = value.stage.resolve("outputs/maven/obsolete.jar")
            Files.createDirectories(obsoleteMaven.parent)
            Files.writeString(obsoleteMaven, "prior exact-release publication must not survive")
            val originals = listOf(value.projection, value.handoff.resolve("original-receipt.json"))
                .associateWith { Files.readAllBytes(it).toList() }
            fun inventory(): Map<String, List<Byte>> = Files.walk(value.stage).use { entries ->
                entries.filter { Files.isRegularFile(it) }.toList().associate { path ->
                    value.stage.relativize(path).joinToString("/") to Files.readAllBytes(path).toList()
                }
            }
            var calls = 0
            val verify: (String, File) -> Unit = { component, captured ->
                calls++
                assertEquals(adapter, component)
                assertEquals("original projection", captured.readText())
            }
            value.verify(verify)
            val first = inventory()
            assertEquals(setOf("outputs/evidence/$adapter.json"), first.keys)
            value.verify(verify)
            assertEquals(first, inventory())
            assertEquals(2, calls)
            originals.forEach { (path, bytes) -> assertEquals(bytes, Files.readAllBytes(path).toList()) }
            assertFalse(Files.exists(obsoleteMaven))
        }
    }

    private fun fixture(adapter: String = "jvm", block: (Fixture) -> Unit) {
        val root = createTempDirectory("runtime-adapter-metadata-inputs-").toFile().canonicalFile.toPath()
        try {
            block(Fixture(root, adapter))
        } finally {
            Files.walk(root).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        }
    }

    private class Fixture(val root: Path, val adapter: String) {
        val handoff = root.resolve("inputs/handoff")
        val projection = handoff.resolve("projection.json")
        val stage = root.resolve("build/product-stage/runtime/$adapter/metadata")

        init {
            listOf(handoff, stage).forEach { Files.createDirectories(it) }
            Files.writeString(projection, "original projection")
            Files.writeString(handoff.resolve("original-receipt.json"), "external original evidence")
            Files.writeString(stage.resolve("output-manifest.json"), "prior manifest")
        }

        fun verify(verifier: (String, File) -> Unit) = verifyRuntimeAdapterMetadataInputs(
            adapter, handoff, projection, stage, root.resolve("build"), verifier,
        )

        fun assertPreserved() {
            assertEquals("prior manifest", Files.readString(stage.resolve("output-manifest.json")))
            assertEquals("original projection", Files.readString(projection))
            assertEquals("external original evidence", Files.readString(handoff.resolve("original-receipt.json")))
        }
    }
}
