import java.io.File
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class RuntimeJvmArtifactIdentityTest {
    @Test
    fun `raw JVM artifact reuses compatibility identity while Maven keeps exact release names`() {
        val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        val registration = source.substringAfter("val stageJvmRuntimeBinaryOutputs = ")
            .substringBefore("\nval writeJvmRuntimeBinaryOutputManifest =")
        check(registration.startsWith("tasks.register<Sync>"))
        val root = createTempDirectory("runtime-jvm-artifact-identity").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"runtime-jvm-identity\"\n")
            root.resolve("inputs").mkdir()
            root.resolve("inputs/value.bin").writeText("unchanged adapter and runner bytes\n")
            root.resolve("build.gradle.kts").writeText(
                """
                import org.gradle.api.tasks.Sync
                import org.gradle.api.tasks.bundling.Zip
                import org.gradle.jvm.tasks.Jar
                plugins { base }
                version = providers.gradleProperty("releaseVersion").get()
                val desktopRuntimeCompatibilityVersion = providers.gradleProperty("compatibilityVersion")
                val jvmRuntimeBinaryOutputs = layout.buildDirectory.dir("stage/outputs")
                val jvmRuntimeJar = tasks.register<Jar>("jvmJar") {
                    archiveBaseName.set("codex-agent-runtime-desktop-jvm")
                    archiveVersion.set(project.version.toString())
                    destinationDirectory.set(layout.buildDirectory.dir("libs"))
                    from("inputs")
                }
                val packageJvmRuntimeEvidenceRunner = tasks.register<Zip>("packageJvmRuntimeEvidenceRunner") {
                    archiveFileName.set("codex-agent-jvm-runtime-evidence-runner.zip")
                    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
                    from("inputs")
                }
                $registration
                """.trimIndent(),
            )
            val staged = root.resolve("build/stage/outputs")
            var original: Map<String, ByteArray>? = null
            for ((version, compatibility) in listOf("0.2.0" to "0.2.0", "0.2.1" to "0.2.0")) {
                val result = GradleRunner.create()
                    .withProjectDir(root)
                    .withArguments(
                        "stageJvmRuntimeBinaryOutputs", "--offline", "--configuration-cache",
                        "--configuration-cache-problems=fail", "-PreleaseVersion=$version",
                        "-PcompatibilityVersion=$compatibility",
                    )
                    .build()
                assertTrue(result.tasks.none { it.path.substringAfterLast(':').startsWith("compile") })
                val mavenJar = root.resolve("build/libs/codex-agent-runtime-desktop-jvm-$version.jar")
                assertTrue(mavenJar.isFile, "Maven-facing artifact must retain its exact release filename")
                val rawJar = staged.resolve("adapter/codex-agent-runtime-desktop-jvm-$compatibility.jar")
                assertContentEquals(mavenJar.readBytes(), rawJar.readBytes())
                ZipFile(rawJar).use { archive ->
                    assertContentEquals(root.resolve("inputs/value.bin").readBytes(),
                        archive.getInputStream(archive.getEntry("value.bin")).use { it.readBytes() })
                }
                val inventory = staged.walkTopDown().filter(File::isFile)
                    .associate { it.relativeTo(staged).invariantSeparatorsPath to it.readBytes() }
                assertEquals(setOf(
                    "adapter/codex-agent-runtime-desktop-jvm-0.2.0.jar",
                    "validation-runner/codex-agent-jvm-runtime-evidence-runner.zip",
                ), inventory.keys)
                original?.let { expected ->
                    expected.forEach { (path, bytes) -> assertContentEquals(bytes, inventory.getValue(path), path) }
                }
                original = inventory
            }
            assertTrue(root.resolve("build/libs/codex-agent-runtime-desktop-jvm-0.2.0.jar").isFile)
        } finally {
            root.deleteRecursively()
        }
    }
}
