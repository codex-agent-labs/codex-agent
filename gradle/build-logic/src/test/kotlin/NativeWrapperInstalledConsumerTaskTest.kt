import java.io.Closeable
import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.work.DisableCachingByDefault

class NativeWrapperInstalledConsumerTaskTest {
    @Test
    fun `task executes one offline language and retains only exact raw evidence`() {
        fixture().use { fixture ->
            val task = fixture.task("python", offline = true)
            task.consume()

            val files = verifiedRegularFiles(fixture.output)
            assertEquals(
                setOf("evidence/python/linux-x64.tsv", "evidence/python/toolchain.tsv"),
                files.keys,
            )
            assertTrue("--offline" in files.getValue("evidence/python/toolchain.tsv").readText())
            assertFalse(fixture.output.resolve("receipt.json").exists())
        }
    }

    @Test
    fun `task fails closed and deletes malformed or stale evidence`() {
        fixture().use { fixture ->
            fixture.output.mkdirs()
            fixture.output.resolve("stale.tsv").writeText("stale\n")
            fixture.script.writeText(fakeConsumerScript(malformed = true))
            assertFailsWith<IllegalStateException> { fixture.task("python", offline = false).consume() }
            assertFalse(fixture.output.exists())

            fixture.script.writeText(fakeConsumerScript(malformed = false))
            assertFailsWith<IllegalStateException> { fixture.task("javascript", offline = true).consume() }
            assertFalse(fixture.output.exists())
        }
    }

    @Test
    fun `raw tool identity inventory is exact for every language`() {
        val expected = mapOf(
            "python" to listOf("python"),
            "csharp" to listOf("dotnet"),
            "rust" to listOf("cargo", "rustFixtureCompiler", "rustc"),
            "cpp" to listOf("cmake", "cppCompiler"),
            "dart" to listOf("dart"),
        )
        expected.forEach { (language, tools) ->
            val output = createTempDirectory("native-wrapper-$language-evidence").toFile()
            try {
                writeSyntheticEvidence(output, language, tools)
                requireExactNativeWrapperInstalledConsumerEvidence(output, language)
                writeSyntheticEvidence(output, language, tools + "unexpected")
                assertFailsWith<IllegalStateException>(language) {
                    requireExactNativeWrapperInstalledConsumerEvidence(output, language)
                }
            } finally {
                output.deleteRecursively()
            }
        }
    }

    @Test
    fun `registration verifies imported integrity and keeps product phase closure external`() {
        val source = File("src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts").readText()
        val seam = source.substringAfter("val nativeWrapperInstalledConsumerTasks =")
            .substringBefore("val nativeWrapperReleaseDirectory =")
        listOf(
            "providers.gradleProperty(\n    \"codexAgent.sdkPackageStageRoot\"",
            "tasks.register<SnapshotImportedProductStageTask>",
            "tasks.register<VerifyImportedProductOutputManifestTask>",
            "product.set(\"sdk\")",
            "phase.set(\"package\")",
            "target.set(\"desktop\")",
            "dependsOn(verify, stageNativeWrapperCAbiSdks)",
            "tasks.register<NativeWrapperInstalledConsumerTask>",
            "offlineMode.set(gradle.startParameter.isOffline)",
            "snapshotImportedNativeWrapperRuntimeStages.configure { mustRunAfter(invalidate) }",
            "generateNativeWrapperSdkCompatibility.configure { mustRunAfter(invalidate) }",
        ).forEach { assertTrue(it in source, it) }
        assertFalse("WriteProductOutputManifestTask" in seam)
        assertFalse("GenerateCrossLanguageNativeWrapperBindingReceiptTask" in seam)
        assertFalse("consume" in seam && "--plan" in seam)

        val type = NativeWrapperInstalledConsumerTask::class.java
        assertTrue(type.isAnnotationPresent(DisableCachingByDefault::class.java))
        assertTrue(type.getMethod("getPackagesDirectory").isAnnotationPresent(InputDirectory::class.java))
        assertTrue(type.getMethod("getStagedSdkDirectory").isAnnotationPresent(InputDirectory::class.java))
        assertTrue(type.getMethod("getOutputDirectory").isAnnotationPresent(OutputDirectory::class.java))
    }

    private fun fixture(): Fixture {
        val root = createTempDirectory("native-wrapper-installed-consumer").toFile()
        val project = ProjectBuilder.builder().withProjectDir(root.resolve("project").also(File::mkdirs)).build()
        val packages = root.resolve("packages").also(File::mkdirs)
        val sdks = root.resolve("sdks").also(File::mkdirs)
        val version = root.resolve("sdk.txt").apply { writeText("0.2.0\n") }
        val script = root.resolve("consumer.py").apply { writeText(fakeConsumerScript(malformed = false)) }
        return Fixture(root, project, packages, sdks, version, script, root.resolve("output"))
    }

    // These fake-script/TSV fixtures exercise command wiring and fail-closed parsing only;
    // they are not real installed-host, compiler, behavior, or parity results.
    private fun fakeConsumerScript(malformed: Boolean): String {
        val malformedLiteral = if (malformed) "True" else "False"
        return """
        import pathlib, sys
        args = sys.argv[1:]
        assert args[0] == "consume-language"
        assert "--plan" not in args
        language = args[args.index("--language") + 1]
        output = pathlib.Path(args[args.index("--output") + 1]) / "evidence" / language
        output.mkdir(parents=True)
        (output / "linux-x64.tsv").write_text(
            "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus\n"
            + "linux-x64\t%s-package/package.zip\t%s\t%s\t%s-installed-host-lifecycle\tpassed\n"
              % (language, "a" * 64, "b" * 64, language)
        )
        (output / "toolchain.tsv").write_text(
            "tool\tversion\npython\tfixture;" + ("--offline" if "--offline" in args else "online") + "\n"
            + ("unexpected\tunsafe\n" if $malformedLiteral else "")
        )
        """.trimIndent() + "\n"
    }

    private fun writeSyntheticEvidence(output: File, language: String, tools: List<String>) {
        val directory = output.resolve("evidence/$language").also(File::mkdirs)
        directory.resolve("linux-x64.tsv").writeText(
            "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus\n" +
                "linux-x64\t$language-package/package.zip\t${"a".repeat(64)}\t${"b".repeat(64)}\t" +
                "$language-installed-host-lifecycle\tpassed\n",
        )
        directory.resolve("toolchain.tsv").writeText(
            "tool\tversion\n" + tools.sorted().joinToString("") { "$it\tfixture\n" },
        )
    }

    private data class Fixture(
        val root: File,
        val project: Project,
        val packages: File,
        val sdks: File,
        val version: File,
        val script: File,
        val output: File,
    ) : Closeable {
        fun task(language: String, offline: Boolean): NativeWrapperInstalledConsumerTask =
            project.tasks.create(
                "consume${project.tasks.names.size}",
                NativeWrapperInstalledConsumerTask::class.java,
            ).apply {
                this.language.set(language)
                offlineMode.set(offline)
                packagesDirectory.set(packages)
                stagedSdkDirectory.set(sdks)
                sdkVersionFile.set(version)
                consumerScript.set(script)
                consumerSources.from(script)
                outputDirectory.set(output)
                repositoryRoot.set(project.layout.projectDirectory)
            }

        override fun close() {
            root.deleteRecursively()
        }
    }
}
