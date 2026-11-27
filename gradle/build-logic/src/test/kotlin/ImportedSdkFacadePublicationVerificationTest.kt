import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.testfixtures.ProjectBuilder

/** Reuses the complete facade/BOM fixture; no publication, compiler, process or receipt authority. */
class ImportedSdkFacadePublicationVerificationTest {
    @Test
    fun `pure Maven adapter returns the exact existing verifier result and preserves all caller bytes`() = fixture { f ->
        val before = inventory(f.root)
        assertEquals(f.generated.verify(), verify(f))
        assertEquals(before, inventory(f.root))
        assertEquals(JsonPrimitive(12), verify(f)["publicationCount"])
        assertFalse(f.stage.resolve("facade").exists())
        assertFalse(f.stage.resolve("bom").exists())
    }

    @Test
    fun `original metadata dependency and version mutations are rejected without altering originals`() {
        for (case in listOf("pom", "module", "bom", "contract", "runtime", "kotlin")) fixture { f ->
            when (case) {
                "pom" -> f.maven("codex-agent-jvm", "pom").apply {
                    writeText(readText().replace("<version>1.2.3</version>", "<version>9.9.9</version>"))
                }
                "module" -> f.maven("codex-agent-jvm", "module").apply {
                    writeText(readText().replace("\"requires\":\"1.2.3\"", "\"requires\":\"9.9.9\""))
                }
                "bom" -> f.maven("codex-agent-bom", "pom").apply {
                    writeText(readText().replace("<version>2.3.4</version>", "<version>9.9.9</version>"))
                }
            }
            val before = inventory(f.root)
            assertFailsWith<IllegalStateException>(case) {
                verifyImportedSdkFacadePublicationMetadata(f.stage,
                    if (case == "contract") "9.9.9" else "1.2.3",
                    if (case == "runtime") "9.9.9" else "2.3.4", "3.4.5",
                    if (case == "kotlin") "9.9.9" else "2.2.20")
            }
            assertEquals(before, inventory(f.root), case)
        }
    }

    @Test
    fun `symbolic package and metadata reject without touching the linked input`() = fixture { f ->
        val alias = f.root.resolve("alias")
        Files.createSymbolicLink(alias.toPath(), f.stage.toPath())
        val before = inventory(f.stage)
        assertFailsWith<IllegalStateException> {
            verifyImportedSdkFacadePublicationMetadata(alias, "1.2.3", "2.3.4", "3.4.5", "2.2.20")
        }
        assertEquals(before, inventory(f.stage))
        val original = f.maven("codex-agent", "pom")
        val saved = f.root.resolve("original.pom")
        Files.move(original.toPath(), saved.toPath())
        Files.createSymbolicLink(original.toPath(), saved.toPath())
        val raw = saved.readBytes()
        assertFailsWith<IllegalStateException> { verify(f) }
        assertTrue(raw.contentEquals(saved.readBytes()))
        assertTrue(Files.isSymbolicLink(original.toPath()))
    }

    @Test
    fun `path traversal version cannot read beyond original package`() = fixture { f ->
        val before = inventory(f.root)
        assertFailsWith<IllegalStateException> {
            verifyImportedSdkFacadePublicationMetadata(f.stage, "1.2.3", "2.3.4", "../../outside", "2.2.20")
        }
        assertEquals(before, inventory(f.root))
    }

    @Test
    fun `delegating task cannot clobber existing report or write into original package`() = fixture { f ->
        val project = ProjectBuilder.builder().withProjectDir(f.root).build()
        val task = project.tasks.create("verifyImportedFacade", VerifyImportedSdkFacadePublicationMetadataTask::class.java).apply {
            packageStage.set(f.stage)
            sdkVersion.set("3.4.5"); contractVersion.set("1.2.3"); runtimeVersion.set("2.3.4")
            kotlinVersion.set("2.2.20"); forbiddenPath.set("")
        }
        val report = f.root.resolve("report.json").apply { writeText("caller-owned report\n") }
        task.resultFile.set(report)
        val before = inventory(f.root)
        assertFailsWith<IllegalStateException> { task.verify() }
        assertEquals(before, inventory(f.root))
        task.resultFile.set(f.stage.resolve("new-report.json"))
        assertFailsWith<IllegalStateException> { task.verify() }
        assertEquals(before, inventory(f.root))
        task.resultFile.set(f.root.resolve("fresh-report.json"))
        task.verify()
        assertEquals(verify(f), f.root.resolve("fresh-report.json").readReleaseObject())
        assertEquals("caller-owned report\n", report.readText())
    }

    private fun verify(f: Fixture) = verifyImportedSdkFacadePublicationMetadata(
        f.stage, "1.2.3", "2.3.4", "3.4.5", "2.2.20", f.root.absolutePath,
    )

    private fun inventory(root: File) = verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }

    private fun fixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("imported-facade-verifier-").toFile().canonicalFile
        try { block(Fixture(root)) } finally { root.deleteRecursively() }
    }

    private class Fixture(val root: File) {
        private val publications = root.resolve("generated")
        val generated = FacadePublicationContractTest.Fixture(publications)
        val stage = root.resolve("package-stage")
        fun maven(artifact: String, extension: String) = stage.resolve(
            "outputs/maven/io/github/codex-agent-labs/$artifact/3.4.5/$artifact-3.4.5.$extension")
        init {
            val sources = facadePublicationSpecs.map { it.artifact to "facade/${it.publication}" } +
                ("codex-agent-bom" to "bom")
            for ((artifact, source) in sources) for ((extension, name) in
                listOf("pom" to "pom-default.xml", "module" to "module.json")) {
                val destination = maven(artifact, extension)
                destination.parentFile.mkdirs()
                Files.copy(publications.resolve("$source/$name").toPath(), destination.toPath())
            }
            stage.resolve("unrelated-original.bin").writeBytes(byteArrayOf(0, -1, 10))
        }
    }
}
