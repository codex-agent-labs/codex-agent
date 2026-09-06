import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlin.test.assertEquals
import kotlin.test.assertContentEquals
import kotlin.test.assertFalse
import java.util.Base64
import org.gradle.testfixtures.ProjectBuilder
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

class DesktopRuntimeEvidenceTasksTest {
    @Test
    fun `imported native task declares and stages an independently invalidated raw capture`() = withDirectory { root ->
        val project = ProjectBuilder.builder().withProjectDir(root).build()
        val task = project.tasks.create("nativeEvidence", ExecuteImportedNativeRuntimeEvidenceTask::class.java)
        val evidence = root.resolve("desktop-runtime-linuxX64.json")
        task.evidenceFile.set(evidence)
        assertEquals(root.resolve("desktop-runtime-linuxX64-execution.json"), task.executionFile.get().asFile)
        val plugin = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        val native = plugin.substringAfter("val importedNativeExecutionFile =").substringBefore("val jvmValidationTarget =")
        assertTrue("importedNativeExecutionFile," in native)
        assertTrue("executionFile.set(layout.file(importedNativeExecutionFile))" in native)
        assertTrue("from(importedNativeEvidence.flatMap { it.executionFile }) { into(\"execution\") }" in native)
        assertTrue("\"execution\" to \"outputs/execution\"" in native)
    }

    @Test
    fun `all native targets capture discovery and four exact returned process outputs losslessly`() = withDirectory { root ->
        val test = root.resolve("test.kexe").apply { writeText("synthetic runner") }
        val raw = byteArrayOf(0, -1, 13, 10)
        desktopRuntimeEvidenceTargets.keys.forEach { target ->
            val capture = root.resolve("$target.json")
            val commands = mutableListOf<List<String>>()
            executeDesktopRuntimeEvidenceTests(target, test, mapOf("declared" to "environment"), capture) { command, env ->
                commands += command
                assertEquals(mapOf("declared" to "environment"), env)
                if (commands.size == 1) DesktopEvidenceProcessResult(0, nativeListing())
                else DesktopEvidenceProcessResult(0, "decoded output is not the byte authority", raw)
            }
            val records = capture.readReleaseObject().releaseArray("executions").map { it as kotlinx.serialization.json.JsonObject }
            assertEquals(listOf("discovery") + desktopRuntimeTestMethods, records.map { it.releaseString("id") })
            assertEquals(5, commands.size)
            records.drop(1).forEach { assertContentEquals(raw, Base64.getDecoder().decode(it.releaseString("outputBase64"))) }
            desktopRuntimeTestMethods.forEachIndexed { index, method ->
                assertEquals(listOf(test.absolutePath, "--ktest_filter=$DESKTOP_RUNTIME_TEST_CLASS.$method",
                    "--ktest_logger=SILENT"), commands[index + 1])
            }
        }
    }

    @Test
    fun `native failures preserve only actually returned processes and never run later methods`() = withDirectory { root ->
        val test = root.resolve("test.kexe").apply { writeText("synthetic runner") }
        for (failureAt in 0..4) {
            val output = root.resolve("failed-$failureAt.json")
            var calls = 0
            assertFailsWith<IllegalStateException> {
                executeDesktopRuntimeEvidenceTests("linuxX64", test, emptyMap(), output) { _, _ ->
                    val index = calls++
                    if (index == failureAt) DesktopEvidenceProcessResult(9, "failure", byteArrayOf(-1, 0))
                    else DesktopEvidenceProcessResult(0, if (index == 0) nativeListing() else "")
                }
            }
            val records = output.readReleaseObject().releaseArray("executions").map { it as kotlinx.serialization.json.JsonObject }
            assertEquals(failureAt + 1, calls)
            assertEquals(calls, records.size)
            assertEquals(9, records.last().releaseInt("exitCode"))
            assertContentEquals(byteArrayOf(-1, 0), Base64.getDecoder().decode(records.last().releaseString("outputBase64")))
        }
        val timedOut = root.resolve("timeout.json")
        assertFailsWith<IllegalStateException> {
            executeDesktopRuntimeEvidenceTests("linuxX64", test, emptyMap(), timedOut) { _, _ ->
                DesktopEvidenceProcessResult(0, nativeListing(), byteArrayOf(1), timedOut = true)
            }
        }
        assertEquals(1, timedOut.readReleaseObject().releaseArray("executions").size)
        val source = File("src/main/kotlin/LinuxArm64RuntimeEvidenceBundle.kt").readText()
        val runner = source.substringAfter("internal fun runDesktopEvidenceProcess(").substringBefore("fun main(")
        assertTrue("val bytes = log.readBytes()" in runner)
        assertFalse("log.readText()" in runner)
    }

    private fun nativeListing() = buildString {
        append(DESKTOP_RUNTIME_TEST_CLASS).append(".\n")
        desktopRuntimeTestMethods.forEach { append("  ").append(it).append('\n') }
    }

    @Test
    fun `record task is owned by desktop runtime evidence build logic`() {
        val taskType = "RecordDesktopRuntimeEvidenceTask"
        val desktopRuntime = File("src/main/kotlin/DesktopRuntimeEvidenceGradleTasks.kt").readText()

        assertTrue(taskType in desktopRuntime)
    }

    @Test
    fun `test report requires the exact class and four exact methods`() = withDirectory { root ->
        val report = root.resolve("TEST-desktop.xml")
        writeReport(report)
        verifyDesktopRuntimeTestReport(report, TARGET)

        writeReport(report, desktopRuntimeTestMethods - "rejectsWrongTargetChecksum" + "unexpected")
        assertFailsWith<IllegalStateException> { verifyDesktopRuntimeTestReport(report, TARGET) }
        writeReport(report, className = DESKTOP_RUNTIME_TEST_CLASS)
        assertFailsWith<IllegalStateException> { verifyDesktopRuntimeTestReport(report, TARGET) }
        writeReport(report, className = "wrongTest.$DESKTOP_RUNTIME_TEST_CLASS")
        assertFailsWith<IllegalStateException> { verifyDesktopRuntimeTestReport(report, TARGET) }
        writeReport(report)
        report.writeText(report.readText().replaceFirst("${TARGET}Test.", "wrongTest."))
        assertFailsWith<IllegalStateException> { verifyDesktopRuntimeTestReport(report, TARGET) }
    }

    @Test
    fun `five evidence files bind commit pinned binaries and Maven classifiers`() = withDirectory { root ->
        val commit = "a".repeat(40)
        val binary = "b".repeat(64)
        val archive = "c".repeat(64)
        val supervisor = "d".repeat(64)
        val manifest = writeTestDesktopDistributionManifest(root.resolve("desktop.json"), binary)
        val evidence = desktopRuntimeEvidenceTargets.keys.map { target ->
            root.resolve(desktopRuntimeEvidenceFileName(target)).apply {
                atomicWriteJson(buildDesktopRuntimeEvidence(
                    DesktopRuntimeEvidenceValues(commit, target, binary, supervisor, archive),
                ))
            }
        }
        val inventory = root.resolve("maven.json").apply { atomicWriteJson(buildJsonObject {
            put("files", buildJsonArray { desktopRuntimeEvidenceTargets.values.forEach { target ->
                add(buildJsonObject {
                    put("path", JsonPrimitive(
                        "io/github/codex-agent-labs/codex-agent-runtime-desktop/0.2.0/" +
                            "codex-agent-runtime-desktop-0.2.0-${target.classifier}.zip",
                    ))
                    put("sha256", JsonPrimitive(archive))
                })
            } })
        }) }

        assertTrue(validateDesktopRuntimeEvidence(evidence, commit, "0.2.0", inventory, manifest).isEmpty())
        evidence.first().writeText(evidence.first().readText().replace(binary, "d".repeat(64)))
        assertTrue(validateDesktopRuntimeEvidence(evidence, commit, "0.2.0", inventory, manifest).isNotEmpty())
    }

    private fun writeReport(
        file: File,
        methods: Set<String> = desktopRuntimeTestMethods,
        className: String = "${TARGET}Test.$DESKTOP_RUNTIME_TEST_CLASS",
    ) {
        file.writeText(buildString {
            append("<testsuite tests=\"").append(methods.size)
                .append("\" skipped=\"0\" failures=\"0\" errors=\"0\">")
            methods.forEach { method ->
                append("<testcase classname=\"").append(className).append("\" name=\"")
                    .append(method).append("[fixture]\"/>")
            }
            append("</testsuite>")
        })
    }

    private fun withDirectory(block: (File) -> Unit) {
        val root = createTempDirectory("desktop-evidence").toFile().canonicalFile
        try { block(root) } finally { root.deleteRecursively() }
    }

    private companion object { const val TARGET = "macosArm64" }
}
