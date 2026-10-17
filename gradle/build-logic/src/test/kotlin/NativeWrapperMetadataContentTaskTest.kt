import java.io.Closeable
import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.work.DisableCachingByDefault

/** Typed-task/preflight checks only; the existing CLI tests exercise the full matcher. */
class NativeWrapperMetadataContentTaskTest {
    @Test
    fun `task declares imported inputs without producer dependencies or cache admission`() = fixture().use { fixture ->
        val type = NativeWrapperMetadataContentTask::class.java
        assertTrue(type.isAnnotationPresent(DisableCachingByDefault::class.java))
        listOf("PackageStageDirectory", "RuntimeStageDirectory", "StagedSdkDirectory",
            "ValidationStagesDirectory", "ValidationReceiptsDirectory").forEach { property ->
            assertTrue(type.getMethod("get$property").isAnnotationPresent(InputDirectory::class.java))
        }
        listOf("PackageReceipt", "CompatibilityRequest").forEach { property ->
            assertTrue(type.getMethod("get$property").isAnnotationPresent(InputFile::class.java))
        }
        assertTrue(type.getMethod("getVerifierSources").isAnnotationPresent(InputFiles::class.java))
        assertTrue(type.getMethod("getContentOutput").isAnnotationPresent(OutputFile::class.java))
        assertTrue(fixture.task.taskDependencies.getDependencies(fixture.task).isEmpty())
        val source = File("src/main/kotlin/NativeWrapperMetadataContentTask.kt").readText()
        assertTrue("outputs.upToDateWhen { false }" in source)
        assertTrue("writeImportedNativeWrapperMetadataContent(" in source)
        assertFalse("delete" in source.substringAfter("fun verifyAndWrite()"))
    }

    @Test
    fun `fresh output delegates to the existing exact five host gate`() = fixture().use { fixture ->
        val failure = assertFailsWith<IllegalStateException> { fixture.task.verifyAndWrite() }
        assertTrue(failure.message.orEmpty().contains("exactly five host stages"))
        assertFalse(fixture.output.exists())
        assertEquals("original package receipt\n", fixture.receipt.readText())
    }

    @Test
    fun `existing output and missing parent are never altered`() = fixture().use { fixture ->
        fixture.output.writeText("previous result\n")
        assertFailsWith<IllegalStateException> { fixture.task.verifyAndWrite() }
        assertEquals("previous result\n", fixture.output.readText())
        val missing = fixture.root.resolve("build/missing/content.json")
        fixture.task.contentOutput.set(missing)
        assertFailsWith<IllegalStateException> { fixture.task.verifyAndWrite() }
        assertFalse(missing.parentFile.exists())
        assertEquals("previous result\n", fixture.output.readText())
    }

    @Test
    fun `unowned overlapping and symbolic outputs preserve originals`() = fixture().use { fixture ->
        val candidates = listOf(fixture.root.resolve("unowned.json") to "Unowned",
            fixture.root.resolve("build") to "Unowned",
            fixture.task.packageStageDirectory.get().asFile.resolve("content.json") to "overlaps",
            fixture.verifier to "overlaps")
        candidates.forEach { (candidate, reason) ->
            fixture.task.contentOutput.set(candidate)
            val failure = assertFailsWith<IllegalStateException> { fixture.task.verifyAndWrite() }
            assertTrue(failure.message.orEmpty().contains(reason), failure.message)
        }
        val alias = fixture.root.resolve("build/alias")
        Files.createSymbolicLink(alias.toPath(), fixture.stages.toPath())
        fixture.task.contentOutput.set(alias.resolve("content.json"))
        assertFailsWith<IllegalStateException> { fixture.task.verifyAndWrite() }
        assertFalse(fixture.stages.resolve("content.json").exists())
        assertEquals("trusted verifier fixture\n", fixture.verifier.readText())
        assertEquals("original package receipt\n", fixture.receipt.readText())
    }

    private fun fixture(): Fixture {
        val root = createTempDirectory("native-metadata-task-").toRealPath().toFile()
        val project = ProjectBuilder.builder().withProjectDir(root).build()
        val build = root.resolve("build").apply { mkdir() }
        val stages = build.resolve("imported-stages").apply { mkdir() }
        val receipt = stages.resolve("package-receipt.json").apply { writeText("original package receipt\n") }
        val request = stages.resolve("request.json").apply { writeText("original request\n") }
        root.resolve("ci").mkdir()
        val verifier = build.resolve("verifier.py").apply { writeText("trusted verifier fixture\n") }
        fun directory(name: String) = stages.resolve(name).apply { mkdir() }
        val output = build.resolve("content.json")
        val task = project.tasks.create("nativeMetadata", NativeWrapperMetadataContentTask::class.java).apply {
            language.set("python")
            sdkVersion.set("0.2.0")
            repositoryRoot.set(root)
            ownedBuildDirectory.set(build)
            packageStageDirectory.set(directory("package"))
            packageReceipt.set(receipt)
            compatibilityRequest.set(request)
            runtimeStageDirectory.set(directory("runtime"))
            stagedSdkDirectory.set(directory("sdks"))
            validationStagesDirectory.set(directory("validations"))
            validationReceiptsDirectory.set(directory("receipts"))
            verifierSources.from(verifier)
            contentOutput.set(output)
        }
        return Fixture(root, stages, receipt, verifier, output, task)
    }

    private data class Fixture(
        val root: File, val stages: File, val receipt: File, val verifier: File,
        val output: File, val task: NativeWrapperMetadataContentTask,
    ) : Closeable {
        override fun close() { root.deleteRecursively() }
    }
}
