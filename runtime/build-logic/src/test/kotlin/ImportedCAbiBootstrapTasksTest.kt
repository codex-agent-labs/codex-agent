import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Report/task wiring fixtures only: no native product, compiler or hosted-runner evidence. */
class ImportedCAbiBootstrapTasksTest {
    @Test
    fun `workspace rejects symbolic parents and lexical aliases without touching sentinel`() {
        val root = createTempDirectory("c-abi-workspace-safety").toFile().canonicalFile
        try {
            val original = root.resolve("original").apply { mkdirs() }
            val outside = root.resolve("outside").apply { mkdirs() }
            val sentinel = outside.resolve("sentinel").apply { writeText("preserve") }
            val link = root.resolve("linked")
            Files.createSymbolicLink(link.toPath(), outside.toPath())
            val dangling = root.resolve("dangling")
            Files.createSymbolicLink(dangling.toPath(), root.resolve("missing").toPath())
            for (output in listOf(link.resolve("new"), link.resolve("../new"), dangling,
                                  original.resolve("new"), original, root, sentinel.resolve("new"))) {
                assertFailsWith<IllegalStateException> { requireVacantImportedCAbiWorkspace(output, original) }
                assertEquals("preserve", sentinel.readText())
            }
            val empty = root.resolve("empty").apply { mkdirs() }
            requireVacantImportedCAbiWorkspace(empty, original)
            empty.resolve("occupied").writeText("preserve")
            assertFailsWith<IllegalStateException> { requireVacantImportedCAbiWorkspace(empty, original) }
            assertEquals("preserve", empty.resolve("occupied").readText())
            requireVacantImportedCAbiWorkspace(root.resolve("safe/new"), original)
            assertFalse(root.resolve("safe").exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `exact task projection preserves original methods statuses and multiplicity`() {
        val suffix = "io.github.codex_agent_labs.codexagent.capi.Fixture#method[macosArm64]"
        val original = CanonicalTestStatus.entries.map { CanonicalTestResult("macosArm64Test.$suffix", it) }
        val imported = original.map { it.copy(testId = it.testId.replace("macosArm64Test.", "$IMPORTED_C_ABI_TEST_TASK.")) }
        assertEquals(original, canonicalCAbiNativeTests(imported, IMPORTED_C_ABI_TEST_TASK))
        assertEquals(original, canonicalCAbiNativeTests(original, "macosArm64Test"))
        for (foreign in listOf("other.$suffix", "macosArm64Test.$suffix",
                               "$IMPORTED_C_ABI_TEST_TASK.other.Fixture#method[macosArm64]",
                               "$IMPORTED_C_ABI_TEST_TASK.${suffix.replace("[macosArm64]", "[linuxX64]")}")) {
            assertFailsWith<IllegalStateException> {
                canonicalCAbiNativeTests(listOf(CanonicalTestResult(foreign, CanonicalTestStatus.PASSED)), IMPORTED_C_ABI_TEST_TASK)
            }
        }
        assertFailsWith<IllegalStateException> { canonicalCAbiNativeTests(imported, "inventedTest") }
    }

    @Test
    fun `existing native Gradle reporter runs imported executable without a compile edge`() {
        val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        val registration = "val nativeTest = tasks.register<KotlinNativeHostTest>" + source
            .substringAfter("val nativeTest = tasks.register<KotlinNativeHostTest>")
            .substringBefore("        generateCAbiBootstrapEvidence.configure {")
        check("executable(prepare.flatMap" in registration)
        val root = createTempDirectory("imported-c-abi-reporter").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"imported-c-abi-reporter-fixture\"\n")
            val executable = root.resolve("imported/test.kexe")
            executable.parentFile.mkdirs()
            executable.writeText("""
                #!/bin/sh
                printf '%s\n' "##teamcity[testSuiteStarted name='io.github.codex_agent_labs.codexagent.capi.Fixture']"
                printf '%s\n' "##teamcity[testStarted name='method']"
                printf '%s\n' "##teamcity[testFinished name='method']"
                printf '%s\n' "##teamcity[testSuiteFinished name='io.github.codex_agent_labs.codexagent.capi.Fixture']"
            """.trimIndent() + "\n")
            check(executable.setExecutable(true, false))
            val bytes = executable.readBytes().toList()
            root.resolve("build.gradle.kts").writeText("""
                import org.jetbrains.kotlin.gradle.targets.native.tasks.KotlinNativeHostTest
                plugins { id("org.jetbrains.kotlin.multiplatform") }
                kotlin { jvm() }
                val IMPORTED_C_ABI_TEST_TASK = "$IMPORTED_C_ABI_TEST_TASK"
                val importedBootstrapReports = layout.buildDirectory.dir("raw-junit")
                val prepare = tasks.register<PrepareImportedCAbiBootstrapTask>("prepareFixture") {
                    enabled = false // This fixture tests only the real report runner, not package authentication.
                    outputDirectory.set(layout.projectDirectory.dir("imported"))
                }
                $registration
            """.trimIndent())
            fun run() = GradleRunner.create().withProjectDir(root).withPluginClasspath().withArguments(
                IMPORTED_C_ABI_TEST_TASK, "--offline", "--configuration-cache", "--configuration-cache-problems=fail",
            ).build()
            val first = run()
            assertTrue(first.tasks.none { "compile" in it.path.lowercase() || "link" in it.path.lowercase() })
            val report = root.resolve("build/raw-junit").listFiles()!!.single { it.extension == "xml" }
            val raw = readCanonicalTestReport(report)
            assertEquals(listOf(CanonicalTestResult(
                "$IMPORTED_C_ABI_TEST_TASK.io.github.codex_agent_labs.codexagent.capi.Fixture#method[macosArm64]",
                CanonicalTestStatus.PASSED,
            )), raw)
            assertEquals("macosArm64Test.io.github.codex_agent_labs.codexagent.capi.Fixture#method[macosArm64]",
                canonicalCAbiNativeTests(raw, IMPORTED_C_ABI_TEST_TASK).single().testId)
            assertTrue("Reusing configuration cache." in run().output)
            assertEquals(bytes, executable.readBytes().toList())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `bootstrap imports compiled source closure and keeps validation reports external`() {
        val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        assertTrue("into(\"validation-runner/compiler-header\")" in source)
        assertTrue("into(\"validation-runner/source/nativeMain\")" in source)
        assertTrue("into(\"validation-runner/source/nativeTest\")" in source)
        assertTrue("if (!importedCAbiBootstrap)" in source)
        val imports = source.substringAfter("val importedBootstrapTest =").substringBefore("val stageValidation =")
        assertFalse("linkRelease" in imports || "dependsOn(\"macosArm64Test\")" in imports)
        assertTrue("nativeTestTaskName.set(IMPORTED_C_ABI_TEST_TASK)" in imports)
        assertTrue("outputs/validation-runner/source/nativeMain" in imports)
        assertTrue("outputs/validation-runner/source/nativeTest" in imports)
        val validation = source.substringAfter("val stageValidation =").substringBefore("val jvmValidationTarget =")
        assertTrue("from(generateCAbiBootstrapEvidence.flatMap { it.evidenceFile })" in validation)
        assertTrue("from(generateCAbiBootstrapEvidence.flatMap { it.bootstrapContentFile })" in validation)
        for (part in listOf("c-abi-bootstrap/native-junit", "c-abi-bootstrap/consumers", "c-abi-bootstrap/original-runner")) {
            assertTrue(part in validation, part)
        }
    }
}
