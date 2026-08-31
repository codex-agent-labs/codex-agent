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
            project.resolve("settings.gradle.kts").writeText("rootProject.name = \"test\"\n")
            project.resolve("build.gradle.kts").writeText(
                """
                plugins {
                    id("org.jetbrains.kotlin.multiplatform")
                    id("maven-publish")
                    id("codexagent.desktop-runtime")
                }
                group = "io.github.codex-agent-labs"
                version = "0.2.1"
                """.trimIndent(),
            )

            val result = GradleRunner.create()
                .withProjectDir(project)
                .withPluginClasspath()
                .withArguments(
                    "generateDesktopDistributionSource",
                    "packageLinuxArm64AppServer",
                    "-PcodexAgent.desktopClassifierDirectory=${project.absolutePath}",
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
