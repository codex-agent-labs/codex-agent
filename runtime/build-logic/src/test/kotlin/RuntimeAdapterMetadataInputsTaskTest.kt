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
    }

    @Test
    fun `valid disjoint inputs survive owned cleanup and semantic verifier receives originals`() = fixture { value ->
        val sibling = value.root.resolve("build/product-stage/runtime/node-js/metadata/preserved")
        Files.createDirectories(sibling.parent)
        Files.writeString(sibling, "sibling")
        var calls = 0
        value.verify { component, projection ->
            calls++
            assertEquals("jvm", component)
            assertEquals(value.projection.toFile(), projection)
            assertFalse(Files.exists(value.stage))
        }
        assertEquals(1, calls)
        assertEquals("original projection", Files.readString(value.projection))
        assertEquals("original Maven bytes", Files.readString(value.maven.resolve("artifact.jar")))
        assertEquals("sibling", Files.readString(sibling))
    }

    @Test
    fun `input output aliases and out of scope output preserve all originals`() {
        for (mutation in listOf("maven-child", "maven-parent", "handoff", "stage")) fixture { value ->
            val maven = when (mutation) {
                "maven-child" -> value.stage.resolve("original-maven").also { Files.createDirectories(it) }
                "maven-parent" -> value.root.resolve("build")
                else -> value.maven
            }
            val handoff = if (mutation == "handoff") value.stage else value.handoff
            val projection = handoff.resolve("projection.json")
            if (projection != value.projection) Files.writeString(projection, "original imported projection")
            val stage = if (mutation == "stage") value.root.resolve("inputs") else value.stage
            assertFailsWith<IllegalStateException> {
                verifyRuntimeAdapterMetadataInputs("jvm", handoff, projection, maven, stage,
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
                "input-child" -> value.maven.resolve("unsafe")
                "output-child" -> value.stage.resolve("unsafe")
                else -> value.root.resolve("linked-parent")
            }
            Files.createSymbolicLink(link, if (mutation == "dangling") value.root.resolve("absent") else external)
            try {
                val maven = when (mutation) {
                    "parent", "dangling" -> link.resolve("repository")
                    "parent-dotdot" -> link.resolve("../inputs/maven")
                    else -> value.maven
                }
                assertFailsWith<IllegalStateException> {
                    verifyRuntimeAdapterMetadataInputs("jvm", value.handoff, value.projection, maven,
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
        assertEquals("original Maven bytes", Files.readString(value.maven.resolve("artifact.jar")))
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
            val maven = when (mutation) {
                "equal" -> stageAlias
                "descendant" -> stageAlias.resolve("imported-maven").also { Files.createDirectories(it) }
                else -> buildAlias
            }
            val original = value.root.resolve("build/original-input").also { Files.writeString(it, "original") }
            if (mutation == "absent-stage") {
                Files.walk(value.stage).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
            }
            val failure = assertFailsWith<IllegalStateException> {
                verifyRuntimeAdapterMetadataInputs("jvm", value.handoff, value.projection, maven,
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
        for (mutation in listOf("empty-maven", "projection")) fixture { value ->
            if (mutation == "empty-maven") Files.delete(value.maven.resolve("artifact.jar"))
            var calls = 0
            assertFailsWith<IllegalStateException> {
                value.verify { _, _ ->
                    calls++
                    error("Synthetic semantic rejection, not product verification")
                }
            }
            assertFalse(Files.exists(value.stage))
            assertEquals(if (mutation == "projection") 1 else 0, calls)
            assertEquals("original projection", Files.readString(value.projection))
            assertTrue(Files.isDirectory(value.maven))
        }
    }

    private fun fixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("runtime-adapter-metadata-inputs-").toFile().canonicalFile.toPath()
        try {
            block(Fixture(root))
        } finally {
            Files.walk(root).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        }
    }

    private class Fixture(val root: Path) {
        val handoff = root.resolve("inputs/handoff")
        val projection = handoff.resolve("projection.json")
        val maven = root.resolve("inputs/maven")
        val stage = root.resolve("build/product-stage/runtime/jvm/metadata")

        init {
            listOf(handoff, maven, stage).forEach { Files.createDirectories(it) }
            Files.writeString(projection, "original projection")
            Files.writeString(maven.resolve("artifact.jar"), "original Maven bytes")
            Files.writeString(stage.resolve("output-manifest.json"), "prior manifest")
        }

        fun verify(verifier: (String, File) -> Unit) = verifyRuntimeAdapterMetadataInputs(
            "jvm", handoff, projection, maven, stage, root.resolve("build"), verifier,
        )

        fun assertPreserved() {
            assertEquals("prior manifest", Files.readString(stage.resolve("output-manifest.json")))
            assertEquals("original projection", Files.readString(projection))
            assertEquals("original Maven bytes", Files.readString(maven.resolve("artifact.jar")))
        }
    }
}
