import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class RepositoryVerificationTasksTest {
    @Test
    fun `repository verification consumes only required imported product evidence`() {
        val source = File("src/main/kotlin/RepositoryVerificationTasks.kt").readText()
        val repositoryTask = source.substringBefore("tasks.register(\"verifyIosRuntime\")")
        for (property in listOf(
            "codexAgent.repositoryContractEvidenceDirectory",
            "codexAgent.repositoryRuntimeEvidenceDirectory",
            "codexAgent.repositorySdkEvidenceDirectory",
            "codexAgent.repositoryTrustDomain",
        )) {
            assertTrue(property in source, property)
        }
        assertTrue("dependsOn(invalidate)" in repositoryTask)
        assertTrue("PYTHONDONTWRITEBYTECODE" in repositoryTask)
        assertTrue("ci.products.aggregate\", \"verify-repository" in repositoryTask)
        assertFalse("repositoryVerificationTaskPaths" in source)
        assertFalse("includedBuild(\"build-logic\")" in repositoryTask)
        for (forbidden in listOf(
            ":codex-agent-core:",
            ":codex-agent-runtime-desktop:",
            ":codex-agent-runtime-android:",
            ":tooling:",
            "verifyContract",
            "verifyRuntime",
            "verifySdk",
            "gradle.startParameter",
            "onlyIf",
            ".orElse(",
        )) {
            assertFalse(forbidden in repositoryTask, forbidden)
        }
        assertTrue(":codex-agent-runtime-ios:verifyIosRuntime" in source)
    }

    @Test
    fun `missing evidence deletes stale success across continue cache reuse and abbreviation`() {
        withFixture { root, report ->
            report.parentFile.mkdirs()
            report.writeText("stale passed report\n")
            val runner = runner(root)

            val first = runner.withArguments(arguments("verifyRepo")).buildAndFail()
            assertEquals(
                TaskOutcome.SUCCESS,
                first.task(":invalidateImportedRepositoryEvidenceOutput")?.outcome,
                first.output,
            )
            assertEquals(TaskOutcome.FAILED, first.task(":verifyRepository")?.outcome)
            assertFalse(report.exists())
            report.writeText("stale passed report\n")

            val reused = runner.withArguments(arguments("verifyRepo", "--continue", "--parallel")).buildAndFail()
            assertTrue("Reusing configuration cache." in reused.output, reused.output)
            assertEquals(
                TaskOutcome.SUCCESS,
                reused.task(":invalidateImportedRepositoryEvidenceOutput")?.outcome,
            )
            assertEquals(TaskOutcome.FAILED, reused.task(":verifyRepository")?.outcome)
            assertFalse(report.exists())
            assertEquals(
                setOf(":invalidateImportedRepositoryEvidenceOutput", ":verifyRepository"),
                reused.tasks.map { it.path }.toSet(),
            )
        }
    }

    @Test
    fun `valid independent evidence produces one aggregate without product tasks`() {
        withFixture { root, report ->
            generateEvidence(root)
            val properties = listOf(
                "-PcodexAgent.repositoryContractEvidenceDirectory=${root.resolve("evidence/contract")}",
                "-PcodexAgent.repositoryRuntimeEvidenceDirectory=${root.resolve("evidence/runtime")}",
                "-PcodexAgent.repositorySdkEvidenceDirectory=${root.resolve("evidence/sdk")}",
                "-PcodexAgent.repositoryTrustDomain=development",
            )
            val first = runner(root).withArguments(arguments("verifyRepository") + properties).build()
            assertEquals(TaskOutcome.SUCCESS, first.task(":verifyRepository")?.outcome, first.output)
            assertTrue(report.isFile)
            val contents = report.readText()
            assertTrue("\"result\":\"passed\"" in contents)
            assertTrue("\"productVersion\":\"1.2.3\"" in contents)
            assertTrue("\"productVersion\":\"2.3.4\"" in contents)
            assertTrue("\"productVersion\":\"3.4.5\"" in contents)
            assertEquals(
                setOf(":invalidateImportedRepositoryEvidenceOutput", ":verifyRepository"),
                first.tasks.map { it.path }.toSet(),
            )

            val second = runner(root).withArguments(arguments("verifyRepo") + properties).build()
            assertEquals(TaskOutcome.SUCCESS, second.task(":verifyRepository")?.outcome)
            val reused = runner(root).withArguments(arguments("verifyRepo") + properties).build()
            assertTrue("Reusing configuration cache." in reused.output, reused.output)
            assertEquals(TaskOutcome.SUCCESS, reused.task(":verifyRepository")?.outcome)
        }
    }

    private fun withFixture(block: (File, File) -> Unit) {
        val root = createTempDirectory("repository-verification").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"repository-verification\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                plugins { id("codexagent.codex-runtime") }
                registerRepositoryVerificationTasks("1.2.3", "2.3.4", "3.4.5")
                """.trimIndent() + "\n",
            )
            val source = repositoryRoot.resolve("ci/products")
            assertTrue(source.copyRecursively(root.resolve("ci/products"), overwrite = true))
            block(root, root.resolve("build/reports/repository/imported-product-evidence.json"))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun generateEvidence(root: File) {
        val builder = ProcessBuilder(
            "python3",
            "-c",
            "from pathlib import Path; from ci.tests.test_products import repository_evidence_fixture; " +
                "repository_evidence_fixture(Path(__import__('sys').argv[1]))",
            root.resolve("evidence").absolutePath,
        )
            .directory(repositoryRoot)
            .redirectErrorStream(true)
        builder.environment()["PYTHONDONTWRITEBYTECODE"] = "1"
        val process = builder.start()
        val output = process.inputStream.bufferedReader().readText()
        assertEquals(0, process.waitFor(), output)
    }

    private fun runner(root: File) = GradleRunner.create()
        .withProjectDir(root)
        .withPluginClasspath()

    private fun arguments(vararg tasks: String) = tasks.toList() + listOf(
        "--configuration-cache",
        "--configuration-cache-problems=fail",
        "--console=plain",
        "--stacktrace",
    )

    private companion object {
        val repositoryRoot = File("../..").canonicalFile
    }
}
