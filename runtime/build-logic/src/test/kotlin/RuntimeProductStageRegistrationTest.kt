import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.BuildResult
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class RuntimeProductStageRegistrationTest {
    @Test
    fun `target validation is configuration-cache serializable`() = withFixture { fixture ->
        assertEquals(TaskOutcome.SUCCESS, fixture.run("validateRuntimeTarget").task(":validateRuntimeTarget")?.outcome)
        val second = fixture.run("validateRuntimeTarget")
        assertTrue("Reusing configuration cache." in second.output)
        assertEquals(TaskOutcome.SUCCESS, second.task(":validateRuntimeTarget")?.outcome)
    }

    @Test
    fun `canonical stage commands reuse configuration and always reverify imported bytes`() = withFixture { fixture ->
        val first = fixture.run("verifyRuntimeOutputManifest")
        assertEquals(TaskOutcome.SUCCESS, first.task(":snapshotRuntimeStage")?.outcome)
        assertEquals(TaskOutcome.SUCCESS, first.task(":writeRuntimeOutputManifest")?.outcome)
        assertEquals(TaskOutcome.SUCCESS, first.task(":verifyRuntimeOutputManifest")?.outcome)
        listOf(
            "python3 -m ci.products receipt snapshot-tree",
            "python3 -m ci.products receipt write-output-manifest",
            "python3 -m ci.products receipt verify-output-manifest",
        ).forEach { command -> assertTrue(command in first.output, command) }

        val payload = fixture.stage.resolve("outputs/binary/value.bin")
        val expected = """
            {"component":"macos-arm64","outputs":[{"bytes":${payload.length()},"kind":"binary","relativePath":"outputs/binary/value.bin","sha256":"sha256:${payload.sha256()}"}],"phase":"binary","product":"runtime","productVersion":"0.2.0","schemaVersion":1,"target":"macos-arm64"}
        """.trimIndent() + "\n"
        assertEquals(expected, fixture.manifest.readText())
        assertFalse(fixture.root.resolve("output-manifest.json").exists())
        assertFalse(fixture.root.resolve("stage/outputs/output-manifest.json").exists())

        assertTrue(fixture.root.resolve("build/imported").deleteRecursively())
        val second = fixture.run("verifyRuntimeOutputManifest")
        assertTrue("Reusing configuration cache." in second.output)
        assertEquals(TaskOutcome.SUCCESS, second.task(":snapshotRuntimeStage")?.outcome)
        assertEquals(TaskOutcome.UP_TO_DATE, second.task(":writeRuntimeOutputManifest")?.outcome)
        assertEquals(TaskOutcome.SUCCESS, second.task(":verifyRuntimeOutputManifest")?.outcome)
    }

    @Test
    fun `snapshot mutation reruns and rejects its existing immutable destination`() {
        listOf("unchanged", "source", "destination").forEach { mutation ->
            withFixture { fixture ->
                assertEquals(
                    TaskOutcome.SUCCESS,
                    fixture.run("snapshotRuntimeStage").task(":snapshotRuntimeStage")?.outcome,
                )
                val destination = fixture.root.resolve("build/imported/value.txt")
                val accepted = destination.readBytes()
                when (mutation) {
                    "source" -> fixture.root.resolve("source/value.txt").writeText("changed source\n")
                    "destination" -> destination.writeText("changed destination\n")
                }

                val rejected = fixture.runAndFail("snapshotRuntimeStage")
                assertEquals(TaskOutcome.FAILED, rejected.task(":snapshotRuntimeStage")?.outcome)
                assertTrue("Imported Runtime snapshot destination is immutable" in rejected.output)
                when (mutation) {
                    "destination" -> assertEquals("changed destination\n", destination.readText())
                    else -> assertContentEquals(accepted, destination.readBytes())
                }
            }
        }
    }

    @Test
    fun `manifest registration rejects containment normalization and unsafe stage roots before mutation`() =
        withFixture { fixture ->
            fixture.manifest.writeText("stale manifest must survive\n")
            val wrongOutputs = fixture.runAndFail("writeWrongOutputsDirectoryManifest")
            assertTrue("Runtime outputs must be the stage root's outputs directory" in wrongOutputs.output)
            assertEquals("stale manifest must survive\n", fixture.manifest.readText())

            fixture.stage.resolve("payload").mkdirs()
            fixture.stage.resolve("payload/value.bin").writeText("outside\n")
            val outside = fixture.runAndFail("writeOutsideOutputRootManifest")
            assertTrue("Runtime output roots must be normalized descendants of outputs/" in outside.output)
            assertEquals("stale manifest must survive\n", fixture.manifest.readText())

            val nonNormalized = fixture.runAndFail("writeNonNormalizedOutputRootManifest")
            assertTrue("Runtime output roots must be normalized descendants of outputs/" in nonNormalized.output)
            assertEquals("stale manifest must survive\n", fixture.manifest.readText())

            val realStage = fixture.root.resolve("unsafe-real-stage").apply {
                resolve("outputs/binary").mkdirs()
                resolve("outputs/binary/value.bin").writeText("unsafe\n")
            }
            Files.createSymbolicLink(fixture.root.resolve("symlink-stage").toPath(), realStage.toPath())
            val symlink = fixture.runAndFail("writeSymlinkStageManifest")
            assertTrue("Runtime stage root must be a real directory" in symlink.output)
            assertFalse(realStage.resolve("output-manifest.json").exists())
        }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("runtime-product-stage-registration").toFile()
        try {
            block(Fixture(root))
        } finally {
            root.deleteRecursively()
        }
    }

    private class Fixture(val root: File) {
        val stage = root.resolve("stage")
        val manifest = stage.resolve("output-manifest.json")

        init {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"runtime-stage-test\"\n")
            root.resolve("source").mkdirs()
            root.resolve("source/value.txt").writeText("source\n")
            stage.resolve("outputs/binary").mkdirs()
            stage.resolve("outputs/binary/value.bin").writeText("value\n")
            root.resolve("other/outputs").mkdirs()
            root.resolve("other/outputs/value.bin").writeText("other\n")
            copyProductTooling(root.resolve("ci/products"))
            installBuildLogic()
            root.resolve("build.gradle.kts").writeText("plugins { id(\"runtime-stage-fixture\") }\n")
        }

        fun run(task: String): BuildResult = runner(task).build()

        fun runAndFail(task: String): BuildResult = runner(task).buildAndFail()

        private fun runner(task: String) = GradleRunner.create()
            .withProjectDir(root)
            .withArguments(
                task,
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--info",
                "--stacktrace",
            )

        companion object {
            private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) {
                it.parentFile
            }.first { it.resolve("runtime/build-logic").isDirectory && it.resolve("ci/products").isDirectory }

            private fun copyProductTooling(target: File) {
                target.mkdirs()
                repository.resolve("ci/products").listFiles().orEmpty()
                    .filter { it.isFile && it.extension == "py" }
                    .forEach { source -> source.copyTo(target.resolve(source.name)) }
            }

            private val FIXTURE_PLUGIN = """
                import org.gradle.api.Plugin
                import org.gradle.api.Project
                import org.gradle.api.file.Directory
                import org.gradle.api.provider.Provider

                class RuntimeStageFixturePlugin : Plugin<Project> {
                    override fun apply(project: Project) {
                        with(project) {
                            pluginManager.apply("base")
                            fun directory(path: String): Provider<Directory> = objects.directoryProperty().apply {
                                set(layout.projectDirectory.dir(path))
                            }
                            val component = objects.property(String::class.java).apply { set("macos-arm64") }
                            val version = objects.property(String::class.java).apply { set("0.2.0") }
                            val tooling = files(layout.projectDirectory.dir("ci/products"))
                            val fixtureDependency = tasks.register("fixtureDependency")
                            registerRuntimeEvidenceTargetValidation(
                                "validateRuntimeTarget", "macos-arm64", "macos-arm64",
                            )
                            val snapshot = registerRuntimeStageSnapshot(
                                "snapshotRuntimeStage", directory("source"), layout.buildDirectory.dir("imported"),
                                tooling, projectDir,
                            )
                            val manifest = registerRuntimeOutputManifest(
                                "writeRuntimeOutputManifest", snapshot, component, "binary", component, version,
                                mapOf("binary" to "outputs/binary"), directory("stage/outputs"), directory("stage"),
                                tooling, projectDir,
                            )
                            registerRuntimeOutputVerification(
                                "verifyRuntimeOutputManifest", manifest, component, "binary", component, version,
                                directory("stage"), tooling, projectDir,
                            )
                            registerRuntimeOutputManifest(
                                "writeWrongOutputsDirectoryManifest", fixtureDependency, component, "binary", component,
                                version,
                                mapOf("binary" to "outputs/binary"), directory("other/outputs"), directory("stage"),
                                tooling, projectDir,
                            )
                            registerRuntimeOutputManifest(
                                "writeOutsideOutputRootManifest", fixtureDependency, component, "binary", component,
                                version,
                                mapOf("binary" to "payload"), directory("stage/outputs"), directory("stage"),
                                tooling, projectDir,
                            )
                            registerRuntimeOutputManifest(
                                "writeNonNormalizedOutputRootManifest", fixtureDependency, component, "binary", component,
                                version, mapOf("binary" to "outputs/../payload"), directory("stage/outputs"),
                                directory("stage"), tooling, projectDir,
                            )
                            registerRuntimeOutputManifest(
                                "writeSymlinkStageManifest", fixtureDependency, component, "binary", component, version,
                                mapOf("binary" to "outputs/binary"), directory("symlink-stage/outputs"),
                                directory("symlink-stage"), tooling, projectDir,
                            )
                        }
                    }
                }
            """.trimIndent() + "\n"
        }

        private fun installBuildLogic() {
            val buildLogic = root.resolve("buildSrc")
            val sources = buildLogic.resolve("src/main/kotlin").apply { mkdirs() }
            repository.resolve("runtime/build-logic/src/main/kotlin/RuntimeProductStageRegistration.kt")
                .copyTo(sources.resolve("RuntimeProductStageRegistration.kt"))
            sources.resolve("RuntimeStageFixturePlugin.kt").writeText(FIXTURE_PLUGIN)
            buildLogic.resolve("settings.gradle.kts").writeText("rootProject.name = \"runtime-stage-fixture\"\n")
            buildLogic.resolve("build.gradle.kts").writeText(
                """
                    plugins {
                        `kotlin-dsl`
                        `java-gradle-plugin`
                    }
                    repositories {
                        mavenCentral()
                        gradlePluginPortal()
                    }
                    gradlePlugin {
                        plugins {
                            create("runtimeStageFixture") {
                                id = "runtime-stage-fixture"
                                implementationClass = "RuntimeStageFixturePlugin"
                            }
                        }
                    }
                """.trimIndent() + "\n",
            )
        }
    }

    private fun File.sha256(): String = MessageDigest.getInstance("SHA-256")
        .digest(readBytes())
        .joinToString("") { byte -> "%02x".format(byte) }
}
