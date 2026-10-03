import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class DesktopClassifierImportFunctionalTest {
    @Test
    fun `prebuilt classifier does not require a loose supervisor`() {
        val project = createTempDirectory("desktop-classifier-import").toFile()
        try {
            val fixture = NodeRuntimeEvidenceFixture(project)
            val classifier = fixture.classifiers.getValue("linuxArm64")
            patchDesktopRuntimeUnixModes(
                classifier,
                setOf("codex-app-server", "codex-process-supervisor"),
            )
            project.resolve("legal/openai-codex/openai-codex-LICENSE.txt")
                .apply { parentFile.mkdirs() }
                .writeText("license")
            project.resolve("legal/openai-codex/openai-codex-NOTICE.txt")
                .writeText("notice")
            val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
                .first { it.resolve("runtime/settings.gradle.kts").isFile }
            listOf("abi-contract.json", "binary-flags.json").forEach { name ->
                repository.resolve("codex-agent-runtime-desktop/native/c-api/$name")
                    .copyTo(project.resolve("native/c-api/$name").apply { parentFile.mkdirs() })
            }
            listOf("linux.map", "macos.exports", "windows.def").forEach { name ->
                val path = "codex-agent-runtime-desktop/native/c-api/exports/$name"
                repository.resolve(path).copyTo(project.resolve(path).apply { parentFile.mkdirs() })
            }
            project.resolve("settings.gradle.kts").writeText("rootProject.name = \"test\"\n")
            project.resolve("build.gradle.kts").writeText(
                """
                plugins {
                    id("org.jetbrains.kotlin.multiplatform")
                    id("maven-publish")
                }
                group = "io.github.codex-agent-labs"
                version = "0.2.1"
                extensions.extraProperties["codexAgent.repositoryRoot"] = projectDir
                apply(plugin = "codexagent.desktop-runtime")
                """.trimIndent(),
            )

            val result = GradleRunner.create()
                .withProjectDir(project)
                .withPluginClasspath()
                .withArguments(
                    "generateDesktopDistributionSource",
                    "packageLinuxArm64AppServer",
                    "-PcodexAgent.desktopClassifierDirectory=${project.absolutePath}",
                    "-PcodexAgent.target=jvm",
                    "--no-configuration-cache",
                    "--stacktrace",
                )
                .build()

            assertEquals(TaskOutcome.SUCCESS, result.task(":generateDesktopDistributionSource")?.outcome)
            assertEquals(TaskOutcome.SUCCESS, result.task(":packageLinuxArm64AppServer")?.outcome)
            assertFalse(project.resolve("build/supervisor/linuxArm64/codex-process-supervisor").exists())
            assertContentEquals(
                classifier.readBytes(),
                project.resolve(
                    "build/distributions/codex-agent-runtime-desktop-0.2.0-app-server-linux-arm64.zip",
                ).readBytes(),
            )
            val generated = project.resolve(
                "build/generated/distributions/kotlin/io/github/codex_agent_labs/codexagent/" +
                    "appserver/runtime/DesktopCodexDistribution.generated.kt",
            ).readText()
            assertTrue("libraryVersion = \"0.2.0\"" in generated)
            assertFalse("0.2.1" in generated)
        } finally {
            project.deleteRecursively()
        }
    }
}
