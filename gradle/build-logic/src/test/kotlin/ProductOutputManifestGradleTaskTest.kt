import java.io.File
import java.lang.reflect.InvocationTargetException
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.testfixtures.ProjectBuilder

class ProductOutputManifestGradleTaskTest {
    @Test
    fun `snapshot task delegates one immutable descriptor-relative copy to the canonical producer`() {
        val type = SnapshotImportedProductStageTask::class.java
        val source = type.getMethod("getSourceDirectory")
        assertNotNull(source.getAnnotation(InputDirectory::class.java))
        assertEquals(PathSensitivity.RELATIVE, source.getAnnotation(PathSensitive::class.java).value)
        assertNotNull(type.getMethod("getOutputDirectory").getAnnotation(Internal::class.java))
        assertNull(type.getMethod("getOutputDirectory").getAnnotation(OutputDirectory::class.java))
        assertNotNull(type.getMethod("getRepositoryRoot").getAnnotation(Internal::class.java))
        assertEquals(1, type.methods.count { it.getAnnotation(TaskAction::class.java) != null })

        val implementation = File("src/main/kotlin/ProductOutputManifestGradleTask.kt").readText()
        assertEquals(1, Regex("snapshot-tree").findAll(implementation).count())
        assertTrue("check(!destination.exists())" in implementation)
    }

    @Test
    fun `task properties declare exact relocatable inputs and non-overlapping output`() {
        val type = WriteProductOutputManifestTask::class.java
        listOf(
            "Product",
            "Component",
            "Phase",
            "Target",
            "ProductVersion",
            "PythonExecutable",
            "OutputRoots",
        ).forEach { property ->
            assertNotNull(type.getMethod("get$property").getAnnotation(Input::class.java), property)
        }
        listOf("RepositoryRoot", "StageRoot").forEach { property ->
            assertNotNull(type.getMethod("get$property").getAnnotation(Internal::class.java), property)
        }
        val outputs = type.getMethod("getOutputsDirectory")
        assertNotNull(outputs.getAnnotation(InputDirectory::class.java))
        assertEquals(
            PathSensitivity.RELATIVE,
            outputs.getAnnotation(PathSensitive::class.java).value,
        )
        assertNotNull(type.getMethod("getManifestFile").getAnnotation(OutputFile::class.java))
        assertEquals(1, type.methods.count { it.getAnnotation(TaskAction::class.java) != null })
    }

    @Test
    fun `import verifier declares external inputs and invokes the direct canonical boundary`() {
        val type = VerifyImportedProductOutputManifestTask::class.java
        listOf(
            "Product",
            "Component",
            "Phase",
            "Target",
            "ProductVersion",
            "PythonExecutable",
        ).forEach { property ->
            assertNotNull(type.getMethod("get$property").getAnnotation(Input::class.java), property)
        }
        val stage = type.getMethod("getStageRoot")
        assertNotNull(stage.getAnnotation(InputDirectory::class.java))
        assertEquals(PathSensitivity.RELATIVE, stage.getAnnotation(PathSensitive::class.java).value)
        val sources = type.getMethod("getProducerSources")
        assertNotNull(sources.getAnnotation(InputFiles::class.java))
        assertEquals(PathSensitivity.RELATIVE, sources.getAnnotation(PathSensitive::class.java).value)
        assertNotNull(type.getMethod("getRepositoryRoot").getAnnotation(Internal::class.java))
        assertEquals(1, type.methods.count { it.getAnnotation(TaskAction::class.java) != null })

        val source = File("src/main/kotlin/ProductOutputManifestGradleTask.kt").readText()
            .substringAfter("abstract class VerifyImportedProductOutputManifestTask")
        assertEquals(1, Regex("verify-output-manifest").findAll(source).count())
        assertTrue(
            "pythonExecutable.get(), \"-m\", \"ci.products\", \"receipt\", \"verify-output-manifest\"" in
                source,
        )
        assertFalse("write-output-manifest" in source)
    }

    @Test
    fun `task writes and verifies the exact canonical complete staged tree`() {
        withFixture { fixture ->
            val library = fixture.write("outputs/c-abi/libcodex_agent.dylib", "library")
            val supervisor = fixture.write(
                "outputs/supervisor/codex-process-supervisor",
                "supervisor",
            )
            val task = fixture.task(
                mapOf(
                    "c-abi-library" to "outputs/c-abi",
                    "supervisor" to "outputs/supervisor",
                ),
            )

            execute(task)

            val expected = """
                {"component":"macos-arm64","outputs":[{"bytes":${library.length()},"kind":"c-abi-library","relativePath":"outputs/c-abi/libcodex_agent.dylib","sha256":"sha256:${library.releaseDigest()}"},{"bytes":${supervisor.length()},"kind":"supervisor","relativePath":"outputs/supervisor/codex-process-supervisor","sha256":"sha256:${supervisor.releaseDigest()}"}],"phase":"binary","product":"runtime","productVersion":"1.2.3","schemaVersion":1,"target":"macos-arm64"}
            """.trimIndent() + "\n"
            assertEquals(expected, fixture.manifest.readText())
            assertEquals(
                listOf(
                    "output-manifest.json",
                    "outputs/c-abi/libcodex_agent.dylib",
                    "outputs/supervisor/codex-process-supervisor",
                ),
                fixture.stage.walkTopDown()
                    .filter(File::isFile)
                    .map { it.relativeTo(fixture.stage).invariantSeparatorsPath }
                    .sorted()
                    .toList(),
            )

            execute(task)
            assertEquals(expected, fixture.manifest.readText())
        }
    }

    @Test
    fun `import verifier accepts a canonical stage without changing any byte`() {
        withFixture { fixture ->
            fixture.write("outputs/binary/value.bin", "value")
            execute(fixture.task(mapOf("binary" to "outputs/binary")))
            val before = fixture.snapshot()

            execute(fixture.verifyTask())

            assertEquals(before, fixture.snapshot())
        }
    }

    @Test
    fun `import verifier rejects every wrong identity without changing any byte`() {
        withFixture { fixture ->
            fixture.write("outputs/binary/value.bin", "value")
            execute(fixture.task(mapOf("binary" to "outputs/binary")))
            val before = fixture.snapshot()
            val mutations = listOf<(VerifyImportedProductOutputManifestTask) -> Unit>(
                { it.product.set("sdk") },
                { it.component.set("linux-x64") },
                { it.phase.set("package") },
                { it.target.set("linux-x64") },
                { it.productVersion.set("9.9.9") },
            )

            mutations.forEach { mutate ->
                val task = fixture.verifyTask().also(mutate)
                assertFails { execute(task) }
                assertEquals(before, fixture.snapshot())
            }
        }
    }

    @Test
    fun `import verifier rejects extra and tampered trees without changing any byte`() {
        listOf<(Fixture) -> Unit>(
            { it.write("outputs/unexpected/extra.bin", "extra") },
            { it.write("outputs/binary/value.bin", "tampered") },
        ).forEach { mutate ->
            withFixture { fixture ->
                fixture.write("outputs/binary/value.bin", "value")
                execute(fixture.task(mapOf("binary" to "outputs/binary")))
                mutate(fixture)
                val before = fixture.snapshot()

                assertFails { execute(fixture.verifyTask()) }
                assertEquals(before, fixture.snapshot())
            }
        }
    }

    @Test
    fun `undeclared output fails closed and deletes stale manifest`() {
        withFixture { fixture ->
            fixture.write("outputs/binary/value.bin", "value")
            fixture.write("outputs/unexpected/extra.bin", "extra")
            fixture.manifest.writeText("stale success\n")

            assertFails {
                execute(fixture.task(mapOf("binary" to "outputs/binary")))
            }
            assertFalse(fixture.manifest.exists())
        }
    }

    @Test
    fun `malformed output root fails before deleting the manifest`() {
        withFixture { fixture ->
            fixture.write("outputs/binary/value.bin", "value")
            fixture.manifest.writeText("stale success\n")

            assertFails {
                execute(fixture.task(mapOf("binary" to "../outputs/binary")))
            }
            assertEquals("stale success\n", fixture.manifest.readText())
        }
    }

    @Test
    fun `output root outside normalized outputs fails before deleting the manifest`() {
        withFixture { fixture ->
            fixture.write("payload/files/value.bin", "value")
            fixture.manifest.writeText("stale success\n")

            assertFails {
                execute(fixture.task(mapOf("binary" to "payload/files")))
            }
            assertEquals("stale success\n", fixture.manifest.readText())
        }
    }

    @Test
    fun `manifest outside the stage fails without deleting the victim`() {
        withFixture { fixture ->
            fixture.write("outputs/binary/value.bin", "value")
            val victim = fixture.root.resolve("victim/output-manifest.json").apply {
                parentFile.mkdirs()
                writeText("must survive\n")
            }

            assertFails {
                execute(fixture.task(mapOf("binary" to "outputs/binary"), victim))
            }
            assertEquals("must survive\n", victim.readText())
        }
    }

    private fun execute(task: WriteProductOutputManifestTask) {
        execute(task, WriteProductOutputManifestTask::class.java)
    }

    private fun execute(task: VerifyImportedProductOutputManifestTask) {
        execute(task, VerifyImportedProductOutputManifestTask::class.java)
    }

    private fun execute(task: Any, type: Class<*>) {
        val action = type.methods.single {
            it.getAnnotation(TaskAction::class.java) != null
        }
        try {
            action.invoke(task)
        } catch (error: InvocationTargetException) {
            throw error.targetException
        }
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("product-output-manifest-task").toFile()
        try {
            block(Fixture(root))
        } finally {
            root.deleteRecursively()
        }
    }

    private class Fixture(val root: File) {
        val stage = root.resolve("stage").apply(File::mkdirs)
        val outputs = stage.resolve("outputs").apply(File::mkdirs)
        val manifest = stage.resolve("output-manifest.json")
        private val project = ProjectBuilder.builder()
            .withProjectDir(root.resolve("project").apply(File::mkdirs))
            .build()

        fun task(
            outputRoots: Map<String, String>,
            manifestFile: File = manifest,
        ): WriteProductOutputManifestTask =
            project.tasks.create(
                "writeProductOutputManifest${project.tasks.size}",
                WriteProductOutputManifestTask::class.java,
            ).apply {
                product.set("runtime")
                component.set("macos-arm64")
                phase.set("binary")
                target.set("macos-arm64")
                productVersion.set("1.2.3")
                pythonExecutable.set("python3")
                this.outputRoots.set(outputRoots)
                repositoryRoot.set(REPOSITORY_ROOT)
                stageRoot.set(stage)
                outputsDirectory.set(this@Fixture.outputs)
                this.manifestFile.set(manifestFile)
            }

        fun verifyTask(): VerifyImportedProductOutputManifestTask =
            project.tasks.create(
                "verifyImportedProductOutputManifest${project.tasks.size}",
                VerifyImportedProductOutputManifestTask::class.java,
            ).apply {
                product.set("runtime")
                component.set("macos-arm64")
                phase.set("binary")
                target.set("macos-arm64")
                productVersion.set("1.2.3")
                pythonExecutable.set("python3")
                stageRoot.set(stage)
                producerSources.from(REPOSITORY_ROOT.resolve("ci/products"))
                repositoryRoot.set(REPOSITORY_ROOT)
            }

        fun write(relative: String, contents: String): File = stage.resolve(relative).apply {
            parentFile.mkdirs()
            writeText(contents)
        }

        fun snapshot(): Map<String, List<Byte>> = stage.walkTopDown()
            .filter(File::isFile)
            .associate { file ->
                file.relativeTo(stage).invariantSeparatorsPath to file.readBytes().toList()
            }
    }

    private companion object {
        val REPOSITORY_ROOT: File = File("../..").canonicalFile
    }
}
