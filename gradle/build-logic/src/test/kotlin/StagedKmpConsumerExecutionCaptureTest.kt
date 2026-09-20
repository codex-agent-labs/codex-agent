import java.io.File
import java.io.OutputStream
import java.lang.reflect.Proxy
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.Action
import org.gradle.process.ExecOperations
import org.gradle.process.ExecResult
import org.gradle.process.ExecSpec
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.testkit.runner.GradleRunner

/** Process mocks test transport only; the tiny TestKit fixture observes Gradle task states, not KMP compilation. */
class StagedKmpConsumerExecutionCaptureTest {
    @Test
    fun `optional capture retains exact command raw bytes and unchanged report`() = fixture { f ->
        f.task.verify()
        val execution = f.capture.resolve("process/execution.json").readReleaseObject()
        assertEquals(JsonArray((listOf(f.wrapper.path) + stagedConsumerArguments(f.consumer, f.repository,
            "0.8.1", "0.8.0", "common", listOf("compileKotlinJvm"),
            f.consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts"))).map(::JsonPrimitive)), execution["command"])
        assertEquals(JsonPrimitive(f.consumer.path), execution["workingDirectory"])
        assertEquals(JsonObject(emptyMap()), execution["environment"])
        assertEquals(JsonPrimitive(0), execution["exitCode"])
        assertContentEquals(f.stdout, f.capture.resolve("process/stdout.bin").readBytes())
        assertContentEquals(f.stderr, f.capture.resolve("process/stderr.bin").readBytes())
        assertContentEquals(f.report.readBytes(), f.capture.resolve("report.json").readBytes())
        assertEquals(setOf("schemaVersion", "result", "sdkVersion", "runtimeVersion", "repository",
            "mavenGroup", "target", "tasks"), f.report.readReleaseObject().keys)
        assertEquals(JsonPrimitive(6), f.report.readReleaseObject()["schemaVersion"])
        assertEquals(setOf("process", "report.json", "task-outcomes.json"), f.capture.list()!!.toSet())
        assertTrue("codexCapturedOutcomes" in f.consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts").readText())
    }

    @Test
    fun `omitted property preserves legacy exec and report without raw capture`() = fixture { f ->
        f.task.executionCaptureDirectory.unset()
        f.task.verify()
        assertTrue(f.report.isFile)
        assertFalse(f.capture.exists())
        assertFalse(f.consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts").readText().contains("codexCapturedOutcomes"))
        assertEquals(1, f.calls)
    }

    @Test
    fun `nonzero and launch failures retain raw logs but no stale success report`() {
        for (launch in listOf(false, true)) fixture { f ->
            f.report.writeText("stale success")
            f.exit = 7
            f.launchFailure = launch
            assertFailsWith<IllegalStateException> { f.task.verify() }
            assertFalse(f.report.exists())
            assertFalse(f.capture.resolve("report.json").exists())
            assertContentEquals(f.stdout, f.capture.resolve("process/stdout.bin").readBytes())
            assertContentEquals(f.stderr, f.capture.resolve("process/stderr.bin").readBytes())
            assertEquals(if (launch) JsonNull else JsonPrimitive(7),
                f.capture.resolve("process/execution.json").readReleaseObject()["exitCode"])
            assertEquals(JsonArray(emptyList()), f.capture.resolve("task-outcomes.json").readReleaseObject()["tasks"])
        }
    }

    @Test
    fun `overlap stale and symbolic capture reject before consumer cleanup or process`() {
        for (invalid in listOf("source", "consumer", "result", "existing", "symbolic")) fixture { f ->
            f.consumer.mkdirs()
            val sentinel = f.consumer.resolve("sentinel").apply { writeText("unchanged") }
            when (invalid) {
                "source" -> f.task.executionCaptureDirectory.set(f.template.resolve("capture"))
                "consumer" -> f.task.executionCaptureDirectory.set(f.consumer)
                "result" -> f.task.executionCaptureDirectory.set(f.report.parentFile)
                "existing" -> f.capture.mkdirs()
                "symbolic" -> Files.createSymbolicLink(f.capture.toPath(), f.template.toPath())
            }
            assertFailsWith<IllegalStateException> { f.task.verify() }
            assertEquals(0, f.calls)
            assertEquals("unchanged", sentinel.readText())
        }
    }

    @Test
    fun `changed original inputs reject without publishing success and retain process bytes`() = fixture { f ->
        f.afterProcess = { f.template.resolve("settings.gradle.kts").appendText("changed") }
        assertFailsWith<IllegalStateException> { f.task.verify() }
        assertFalse(f.report.exists())
        assertFalse(f.capture.resolve("report.json").exists())
        assertContentEquals(f.stdout, f.capture.resolve("process/stdout.bin").readBytes())
    }

    @Test
    fun `actual Gradle recorder retains executed up to date skipped and failed requested states`() {
        val root = createTempDirectory("kmp-outcome-capture-").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"capture-fixture\"\n")
            root.resolve("build.gradle.kts").writeText("""
                tasks.register("compiled") {
                    val proof = layout.buildDirectory.file("proof.txt")
                    outputs.file(proof)
                    doLast { proof.get().asFile.apply { parentFile.mkdirs(); writeText("compiled") } }
                }
                tasks.register("skipped") { onlyIf { false } }
                tasks.register("failed") { doLast { error("original failure") } }
            """.trimIndent())
            val outcomes = root.resolve("task-\$outcomes.json")
            val script = root.resolve("capture.init.gradle.kts")
            fun execute(tasks: List<String>, failure: Boolean): List<JsonObject> {
                outcomes.writeText("{\"schemaVersion\":1,\"tasks\":[]}\n")
                script.writeText(stagedConsumerOutcomeInitScript(tasks) + stagedConsumerExecutionCaptureScript(outcomes))
                val runner = GradleRunner.create().withProjectDir(root).withArguments(tasks + listOf(
                    stagedConsumerOutcomeTask, "--init-script", script.path, "--offline", "--no-configuration-cache", "--console=plain"))
                if (failure) runner.buildAndFail() else runner.build()
                return (outcomes.readReleaseObject().getValue("tasks") as JsonArray).map { it as JsonObject }
            }
            val first = execute(listOf("compiled"), false).single()
            assertEquals(JsonPrimitive(true), first["didWork"])
            assertEquals(JsonNull, first["failure"])
            assertEquals(JsonPrimitive(true), execute(listOf("compiled"), false).single()["upToDate"])
            val skipped = execute(listOf("compiled", "skipped"), true)
            assertEquals(listOf(JsonPrimitive("compiled"), JsonPrimitive("skipped")), skipped.map { it["task"] })
            assertEquals(JsonPrimitive(true), skipped.last()["skipped"])
            assertEquals(JsonPrimitive(false), skipped.last()["didWork"])
            val failed = execute(listOf("failed", "compiled"), true)
            assertEquals(1, failed.size)
            assertEquals(JsonPrimitive("failed"), failed.single()["task"])
            assertTrue(failed.single()["failure"] != JsonNull)
            assertEquals(setOf("task", "didWork", "upToDate", "skipped", "skipMessage", "failure"), first.keys)
        } finally { root.deleteRecursively() }
    }

    private fun fixture(block: (CaptureFixture) -> Unit) {
        val root = createTempDirectory("kmp-execution-capture-").toFile().canonicalFile
        try { block(CaptureFixture(root)) } finally { root.deleteRecursively() }
    }
}

private class CaptureFixture(root: File) {
    val template = root.resolve("template").apply { mkdirs(); resolve("settings.gradle.kts").writeText("source") }
    val repository = root.resolve("maven").apply { mkdirs(); resolve("artifact.jar").writeText("artifact") }
    val wrapper = root.resolve("gradlew").apply { writeText("original wrapper") }
    val consumer = root.resolve("consumer")
    val capture = root.resolve("capture")
    val report = root.resolve("report.json")
    val stdout = byteArrayOf(0, -1, 10)
    val stderr = byteArrayOf(10, -2, 0)
    var exit = 0
    var launchFailure = false
    var calls = 0
    var afterProcess: () -> Unit = {}
    private val processes = Proxy.newProxyInstance(ExecOperations::class.java.classLoader,
        arrayOf(ExecOperations::class.java)) { _, method, arguments ->
        check(method.name == "exec")
        calls++
        var output: OutputStream? = null
        var errors: OutputStream? = null
        var directory = root
        val spec = Proxy.newProxyInstance(ExecSpec::class.java.classLoader,
            arrayOf(ExecSpec::class.java)) specHandler@ { _, call, values ->
            when (call.name) {
                "workingDir", "setWorkingDir" -> directory = values!![0] as File
                "getWorkingDir" -> return@specHandler directory
                "setStandardOutput" -> output = values!![0] as OutputStream
                "setErrorOutput" -> errors = values!![0] as OutputStream
            }
            null
        } as ExecSpec
        @Suppress("UNCHECKED_CAST")
        (arguments!![0] as Action<ExecSpec>).execute(spec)
        output?.write(stdout)
        errors?.write(stderr)
        afterProcess()
        if (launchFailure) error("original launch failure")
        Proxy.newProxyInstance(ExecResult::class.java.classLoader, arrayOf(ExecResult::class.java)) resultHandler@ { proxy, call, _ ->
            when (call.name) {
                "getExitValue" -> exit
                "assertNormalExitValue" -> { check(exit == 0); proxy }
                else -> error("Unexpected result call: " + call.name)
            }
        } as ExecResult
    } as ExecOperations
    private val project = ProjectBuilder.builder().withProjectDir(root).build()
    val task = project.tasks.create("verifyConsumer", VerifyStagedKmpConsumerTask::class.java, processes).apply {
        repositoryDirectory.set(repository)
        templateDirectory.set(template)
        mavenInventory.set(root.resolve("inventory.json").apply { writeText("{\"groupId\":\"io.github.codex-agent-labs\"}") })
        gradleWrapper.set(wrapper)
        sdkVersion.set("0.8.1")
        runtimeVersion.set("0.8.0")
        androidSdkDirectory.set("/sdk")
        targetName.set("common")
        buildTasks.set(listOf("compileKotlinJvm"))
        consumerDirectory.set(consumer)
        resultFile.set(report)
        executionCaptureDirectory.set(capture)
    }
}
