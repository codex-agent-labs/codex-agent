import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.testfixtures.ProjectBuilder

class NativeWrapperRuntimeStageSnapshotTest {
    @Test
    fun `immutable destination is not precreated as a Gradle output directory`() {
        val getter = SnapshotImportedNativeWrapperRuntimeStagesTask::class.java.getMethod("getOutputDirectory")
        assertNotNull(getter.getAnnotation(Internal::class.java))
        assertNull(getter.getAnnotation(OutputDirectory::class.java))
    }

    @Test
    fun `snapshot consumes an immutable private copy of all ten imported phases`() {
        val root = Files.createTempDirectory(TEMP_ROOT, "native-wrapper-runtime-snapshot").toFile()
        try {
            val imported = root.resolve("imported").also(::writeTenStages)
            val output = root.resolve("snapshot")
            val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.register(
                "snapshotImportedRuntime",
                SnapshotImportedNativeWrapperRuntimeStagesTask::class.java,
            ).get()
            task.runtimeStageRoot.set(imported)
            task.outputDirectory.set(output)
            task.producerSources.from(REPOSITORY.resolve("ci/products"))
            task.repositoryRoot.set(REPOSITORY)

            task.snapshot()
            imported.resolve("macos-arm64/package/outputs/payload.txt").writeText("changed\n")

            assertEquals(
                "macos-arm64/package\n",
                output.resolve("macos-arm64/package/outputs/payload.txt").readText(),
            )
            assertEquals(
                COMPONENTS.flatMap { component -> PHASES.map { "$component/$it" } }.toSet(),
                output.walkTopDown().filter { it.isFile && it.name == "output-manifest.json" }
                    .map { it.parentFile.relativeTo(output).invariantSeparatorsPath }.toSet(),
            )
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `snapshot rejects symbolic container and intermediate directories`() {
        val root = Files.createTempDirectory(TEMP_ROOT, "native-wrapper-runtime-snapshot-symlink").toFile()
        try {
            val imported = root.resolve("imported").also(::writeTenStages)
            val symbolicRoot = root.resolve("symbolic-root")
            Files.createSymbolicLink(symbolicRoot.toPath(), imported.toPath())
            assertSnapshotFails(root.resolve("project-root"), symbolicRoot, root.resolve("output-root"))

            val unsafe = root.resolve("unsafe").also(::writeTenStages)
            unsafe.resolve("macos-arm64").deleteRecursively()
            Files.createSymbolicLink(
                unsafe.resolve("macos-arm64").toPath(),
                imported.resolve("macos-arm64").toPath(),
            )
            assertSnapshotFails(root.resolve("project-component"), unsafe, root.resolve("output-component"))
            assertFalse(root.resolve("output-component").exists())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun assertSnapshotFails(projectDir: java.io.File, input: java.io.File, output: java.io.File) {
        projectDir.mkdirs()
        val task = ProjectBuilder.builder().withProjectDir(projectDir).build().tasks.register(
            "snapshotImportedRuntime",
            SnapshotImportedNativeWrapperRuntimeStagesTask::class.java,
        ).get()
        task.runtimeStageRoot.set(input)
        task.outputDirectory.set(output)
        task.producerSources.from(REPOSITORY.resolve("ci/products"))
        task.repositoryRoot.set(REPOSITORY)
        assertFails { task.snapshot() }
        assertFalse(output.exists(), "unexpected snapshot output: ${output.walkTopDown().toList()}")
    }

    private fun writeTenStages(root: java.io.File) {
        COMPONENTS.forEach { component ->
            PHASES.forEach { phase ->
                root.resolve("$component/$phase/output-manifest.json").apply {
                    parentFile.mkdirs()
                    writeText("$component/$phase manifest\n")
                }
                root.resolve("$component/$phase/outputs/payload.txt").apply {
                    parentFile.mkdirs()
                    writeText("$component/$phase\n")
                }
            }
        }
        assertTrue(root.isDirectory)
    }

    private companion object {
        val COMPONENTS = listOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
        val PHASES = listOf("package", "validation")
        val REPOSITORY = java.io.File("../..").canonicalFile
        val TEMP_ROOT = java.nio.file.Path.of(
            if (System.getProperty("os.name").startsWith("Mac")) "/private/tmp"
            else System.getProperty("java.io.tmpdir"),
        )
    }
}
