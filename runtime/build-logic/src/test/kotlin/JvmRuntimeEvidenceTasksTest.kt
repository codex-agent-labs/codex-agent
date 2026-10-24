import java.io.File
import java.time.LocalDateTime
import java.util.Base64
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertContentEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.gradle.testfixtures.ProjectBuilder

class JvmRuntimeEvidenceTasksTest {
    @Test
    fun `capture retains exact returned bytes and discovery then every actual method`() = withFixture { fixture ->
        val target = "linuxX64"
        val listingBytes = exactListing().replace("\n", "\r\n").toByteArray(Charsets.UTF_8)
        val binaryOutput = byteArrayOf(0xff.toByte(), 0, 13, 10, 0xc3.toByte())
        var methodIndex = 0
        fixture.record(target) { command, _ ->
            if (command.last() == "--list-tests") {
                JvmEvidenceProcessResult(0, listingBytes.toString(Charsets.UTF_8), listingBytes)
            } else {
                val bytes = if (methodIndex++ == 0) binaryOutput else byteArrayOf()
                JvmEvidenceProcessResult(0, bytes.toString(Charsets.UTF_8), bytes)
            }
        }
        val raw = fixture.execution(target).readReleaseObject()
        assertEquals(setOf("schemaVersion", "component", "target", "testClass", "executions"), raw.keys)
        assertEquals("jvm", raw.releaseString("component"))
        assertEquals(target, raw.releaseString("target"))
        assertEquals(DESKTOP_RUNTIME_TEST_CLASS, raw.releaseString("testClass"))
        val executions = raw.getValue("executions").jsonArray.map { it.jsonObject }
        assertEquals(listOf("discovery") + desktopRuntimeTestMethods, executions.map { it.releaseString("id") })
        assertEquals(5, executions.size)
        assertTrue(executions.all { it.getValue("exitCode").jsonPrimitive.content == "0" })
        assertContentEquals(listingBytes, Base64.getDecoder().decode(executions[0].releaseString("outputBase64")))
        assertContentEquals(binaryOutput, Base64.getDecoder().decode(executions[1].releaseString("outputBase64")))
        executions.drop(2).forEach { assertEquals("", it.getValue("outputBase64").jsonPrimitive.content) }
        verifyRuntimeEvidenceTestReport(fixture.testReport(target), DESKTOP_RUNTIME_TEST_CLASS, desktopRuntimeTestMethods)
        assertTrue(fixture.evidence(target).isFile)
        assertContentEquals("unchanged call".toByteArray(Charsets.UTF_8), JvmEvidenceProcessResult(0, "unchanged call").rawOutput)
    }

    @Test
    fun `failure retains only returned processes and clears stale success reports`() = withFixture { fixture ->
        val target = "linuxX64"
        fixture.record(target)
        assertTrue(fixture.testReport(target).isFile)
        val failedBytes = byteArrayOf(0xfe.toByte(), 0, 10)
        var calls = 0
        assertFailsWith<IllegalStateException> {
            fixture.record(target) { command, _ ->
                calls++
                when {
                    command.last() == "--list-tests" -> JvmEvidenceProcessResult(0, exactListing())
                    calls == 2 -> JvmEvidenceProcessResult(0, "first passed")
                    else -> JvmEvidenceProcessResult(7, "failed", failedBytes)
                }
            }
        }
        val executions = fixture.execution(target).readReleaseObject().getValue("executions").jsonArray.map { it.jsonObject }
        assertEquals(3, calls)
        assertEquals(listOf("discovery") + desktopRuntimeTestMethods.take(2), executions.map { it.releaseString("id") })
        assertEquals("7", executions.last().getValue("exitCode").jsonPrimitive.content)
        assertContentEquals(failedBytes, Base64.getDecoder().decode(executions.last().releaseString("outputBase64")))
        assertFalse(fixture.evidence(target).exists())
        assertFalse(fixture.testReport(target).exists())
        assertFailsWith<IllegalStateException> {
            fixture.record(target) { _, _ -> error("process did not return") }
        }
        assertEquals(0, fixture.execution(target).readReleaseObject().getValue("executions").jsonArray.size)
        assertFalse(fixture.evidence(target).exists())
        assertFalse(fixture.testReport(target).exists())
    }

    @Test
    fun `invalid discovery is captured before exact inventory rejection`() = withFixture { fixture ->
        for ((exitCode, listing) in listOf(0 to (exactListing() + "  extra\n"), 9 to "discovery failed\n")) {
            var calls = 0
            assertFailsWith<IllegalStateException> {
                fixture.record("linuxX64") { _, _ ->
                    calls++
                    JvmEvidenceProcessResult(exitCode, listing)
                }
            }
            val executions = fixture.execution("linuxX64").readReleaseObject().getValue("executions").jsonArray
            assertEquals(1, calls)
            assertEquals(1, executions.size)
            assertEquals("discovery", executions.single().jsonObject.releaseString("id"))
            assertEquals(exitCode.toString(), executions.single().jsonObject.getValue("exitCode").jsonPrimitive.content)
            assertContentEquals(listing.toByteArray(Charsets.UTF_8),
                Base64.getDecoder().decode(executions.single().jsonObject.releaseString("outputBase64")))
            assertFalse(fixture.evidence("linuxX64").exists())
            assertFalse(fixture.testReport("linuxX64").exists())
        }
    }

    @Test
    fun `typed task conventions follow original evidence file and selected target`() = withFixture { fixture ->
        val project = ProjectBuilder.builder().withProjectDir(fixture.root).build()
        val task = project.tasks.create("captureJvm", RecordJvmRuntimeEvidenceTask::class.java)
        task.target.set("linuxX64")
        task.evidenceFile.set(fixture.evidence("linuxX64"))
        assertEquals(fixture.execution("linuxX64"), task.executionFile.get().asFile)
        assertEquals(fixture.testReport("linuxX64"), task.testReport.get().asFile)
        assertEquals(setOf(fixture.evidence("linuxX64"), fixture.execution("linuxX64"), fixture.testReport("linuxX64")),
            task.outputs.files.files)
    }

    @Test
    fun `new capture outputs cannot overwrite original imports`() = withFixture { fixture ->
        val original = fixture.runner.readBytes()
        assertFailsWith<IllegalStateException> {
            executeJvmRuntimeEvidence(COMMIT, "linuxX64", "Linux", "X64", "java", fixture.manifest,
                fixture.classifiers.getValue("linuxX64"), fixture.runner, fixture.evidence("linuxX64"),
                runner = { _, _ -> error("must not execute") }, executionFile = fixture.runner)
        }
        assertContentEquals(original, fixture.runner.readBytes())
    }

    @Test
    fun `exact five records bind one runner and both classifier executables`() = withFixture { fixture ->
        val commands = mutableMapOf<String, MutableList<List<String>>>()
        desktopRuntimeEvidenceTargets.keys.forEach { target ->
            fixture.record(target) { command, environment ->
                commands.getOrPut(target, ::mutableListOf) += command
                assertRuntimeBundleEnvironment(environment, target)
                if (command.last() == "--list-tests") JvmEvidenceProcessResult(0, exactListing())
                else JvmEvidenceProcessResult(0, "")
            }
        }

        assertTrue(fixture.validate().isEmpty())
        assertTrue(commands.values.all { commandsForTarget -> commandsForTarget.size == 5 })
        desktopRuntimeEvidenceTargets.forEach { (target, expected) ->
            val record = fixture.evidence(target).readReleaseObject()
            val proof = inspectDesktopClassifier(target, readDesktopCodexManifest(fixture.manifest),
                fixture.classifiers.getValue(target))
            assertEquals(expected.classifier, record.releaseString("classifier"))
            assertEquals(jvmRuntimeEvidenceTestTask(target), record.releaseString("testTask"))
            assertEquals(proof.archiveSha256, record.releaseString("classifierArchiveSha256"))
            assertEquals(proof.binarySha256, record.releaseString("appServerBinarySha256"))
            assertEquals(proof.supervisorSha256, record.releaseString("supervisorBinarySha256"))
            assertEquals(fixture.runner.releaseDigest(), record.releaseString("compiledJvmTestRuntimeSha256"))
        }
        val arm = fixture.evidence("linuxArm64")
        val renamed = arm.readReleaseObject().toMutableMap()
        renamed["classifierArchiveFileName"] = JsonPrimitive("app-server-linux-arm64.zip")
        arm.atomicWriteJson(JsonObject(renamed))
        assertTrue(fixture.validate().isEmpty())
        renamed["classifierArchiveFileName"] = JsonPrimitive("../app-server-linux-arm64.zip")
        arm.atomicWriteJson(JsonObject(renamed))
        assertTrue(fixture.validate().isNotEmpty())
    }

    @Test
    fun `verification rejects tampered evidence classifier and runner`() = withFixture { fixture ->
        fixture.recordAll()
        val evidence = fixture.evidence("linuxX64")
        val originalEvidence = evidence.readBytes()
        val values = evidence.readReleaseObject().toMutableMap()
        values["supervisorBinarySha256"] = JsonPrimitive("f".repeat(64))
        evidence.atomicWriteJson(JsonObject(values))
        assertTrue(fixture.validate().isNotEmpty())
        evidence.writeBytes(originalEvidence)

        val classifier = fixture.classifiers.getValue("linuxX64")
        classifier.appendText("tampered")
        assertTrue(fixture.validate().isNotEmpty())
        fixture.writeClassifier("linuxX64")

        val runner = fixture.runner.readBytes()
        fixture.runner.appendText("tampered")
        assertTrue(fixture.validate().isNotEmpty())
        fixture.runner.writeBytes(runner)
        assertTrue(fixture.validate(evidenceFiles = desktopRuntimeEvidenceTargets.keys.map(fixture::evidence).dropLast(1))
            .isNotEmpty())
    }

    @Test
    fun `execution rejects identity inventory and failing lifecycle cases before writing evidence`() =
        withFixture { fixture ->
            assertFailsWith<IllegalStateException> {
                fixture.record("linuxX64", runnerOs = "macOS") { _, _ -> error("must not run") }
            }
            assertFailsWith<IllegalStateException> {
                fixture.record("linuxX64") { command, _ ->
                    if (command.last() == "--list-tests") JvmEvidenceProcessResult(0, exactListing() + "  extra\n")
                    else JvmEvidenceProcessResult(0, "")
                }
            }
            assertFailsWith<IllegalStateException> {
                fixture.record("linuxX64") { command, _ ->
                    if (command.last() == "--list-tests") JvmEvidenceProcessResult(0, exactListing())
                    else JvmEvidenceProcessResult(1, "failed")
                }
            }
            assertTrue(!fixture.evidence("linuxX64").exists())
        }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("jvm-runtime-evidence").toFile().canonicalFile
        try { block(Fixture(root)) } finally { root.deleteRecursively() }
    }

    private class Fixture(val root: File) {
        private val appServer = "official app server".encodeToByteArray()
        private val supervisor = "process supervisor".encodeToByteArray()
        val manifest = writeTestDesktopDistributionManifest(root.resolve("distributions.json"),
            appServer.inputStream().releaseDigest())
        val runner = root.resolve(JVM_RUNTIME_RUNNER_ARCHIVE).apply {
            writeZip(linkedMapOf(
                "classes/${JVM_RUNTIME_RUNNER_ENTRYPOINT.replace('.', '/')}.class" to "main".encodeToByteArray(),
                "lib/kotlin-stdlib.jar" to "stdlib".encodeToByteArray(),
            ))
        }
        val classifiers = desktopRuntimeEvidenceTargets.mapValues { (target, expected) ->
            root.resolve("codex-agent-runtime-desktop-0.2.0-${expected.classifier}.zip")
                .also { writeClassifier(target, it) }
        }

        fun evidence(target: String) = root.resolve(jvmRuntimeEvidenceFileName(target))
        fun execution(target: String) = root.resolve("${evidence(target).nameWithoutExtension}-execution.json")
        fun testReport(target: String) = root.resolve(jvmRuntimeEvidenceTestReportName(target))
        fun recordAll() = desktopRuntimeEvidenceTargets.keys.forEach(::record)
        fun record(
            target: String,
            runnerOs: String = desktopRuntimeEvidenceTargets.getValue(target).runnerOs,
            process: (List<String>, Map<String, String>) -> JvmEvidenceProcessResult = { command, _ ->
                if (command.last() == "--list-tests") JvmEvidenceProcessResult(0, exactListing())
                else JvmEvidenceProcessResult(0, "")
            },
        ) = executeJvmRuntimeEvidence(
            COMMIT, target, runnerOs, desktopRuntimeEvidenceTargets.getValue(target).runnerArch,
            "java", manifest, classifiers.getValue(target), runner, evidence(target), runner = process,
        )

        fun validate(
            evidenceFiles: List<File> = desktopRuntimeEvidenceTargets.keys.map(::evidence),
        ) = validateJvmRuntimeEvidence(evidenceFiles, COMMIT, manifest, classifiers.values.toList(), runner)

        fun writeClassifier(target: String) = writeClassifier(target, classifiers.getValue(target))
        private fun writeClassifier(target: String, output: File) {
            val executable = if (target == "mingwX64") "codex-app-server.exe" else "codex-app-server"
            val supervisorExecutable = if (target == "mingwX64") {
                "codex-process-supervisor.exe"
            } else {
                "codex-process-supervisor"
            }
            val payload = linkedMapOf(
                executable to appServer,
                supervisorExecutable to supervisor,
                "openai-codex-LICENSE.txt" to "license".encodeToByteArray(),
                "openai-codex-NOTICE.txt" to "notice".encodeToByteArray(),
            )
            output.writeZip(payload + ("codex-runtime-manifest.json" to runtimeManifestFixture(
                "0.2.0",
                target,
                desktopRuntimeEvidenceTargets.getValue(target).classifier,
                payload,
                setOf(executable, supervisorExecutable),
            )))
        }
    }

    private companion object {
        const val COMMIT = "0123456789abcdef0123456789abcdef01234567"
        fun exactListing() = buildString {
            append(DESKTOP_RUNTIME_TEST_CLASS).append(".\n")
            desktopRuntimeTestMethods.forEach { append("  ").append(it).append('\n') }
        }
    }
}

private fun File.writeZip(entries: Map<String, ByteArray>) = ZipOutputStream(outputStream()).use { zip ->
    entries.forEach { (name, bytes) ->
        zip.putNextEntry(ZipEntry(name).apply { setTimeLocal(LocalDateTime.of(1980, 1, 1, 0, 0)) })
        zip.write(bytes)
        zip.closeEntry()
    }
}
