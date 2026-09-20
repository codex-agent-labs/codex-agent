import java.io.File
import java.lang.reflect.Proxy
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Action
import org.gradle.process.ExecOperations
import org.gradle.process.ExecResult
import org.gradle.process.ExecSpec
import org.gradle.testfixtures.ProjectBuilder

class SdkFacadeOriginalExecutionTest {
    @Test
    fun `sibling capture location is lazy without requiring its own task completion`() = fixture { f ->
        val task = f.task { error("must not execute") }
        assertEquals(f.root.resolve("consumer-inputs"), task.consumerInputsCaptureDirectory.get().asFile)
        task.executionCaptureDirectory.set(f.root.resolve("relocated/execution"))
        assertEquals(f.root.resolve("relocated/consumer-inputs"), task.consumerInputsCaptureDirectory.get().asFile)
        task.executionCaptureDirectory.unset()
        assertFalse(task.consumerInputsCaptureDirectory.isPresent)
        assertFalse(f.root.resolve("consumer-inputs").exists())
        assertFalse(f.root.resolve("relocated").exists())
    }

    @Test
    fun `all fixed targets replay original inputs and full metadata without writing caller files`() = fixture { f ->
        for (target in sdkFacadeConsumerCompileTasks.keys) {
            f.prepare(target)
            val before = inventory(f.root)
            f.verify(target)
            assertEquals(before, inventory(f.root), target)
        }
    }

    @Test
    fun `Windows original context is lexical and shares the producer escaping generator`() = fixture { f ->
        val directory = "C:\\runner\\work\\execution"
        val android = "C:\\Android\\Sdk"
        f.prepare("windows-x64", directory, android)
        f.verify("windows-x64", directory, android)
        assertEquals("sdk.dir=C\\:\\\\Android\\\\Sdk\n", stagedConsumerLocalProperties(android))
        assertTrue(stagedConsumerExecutionCaptureScript("C:\\runner\\task-outcomes.json")
            .contains("C:\\\\runner\\\\task-outcomes.json"))
        f.prepare("windows-x64", "\\\\server\\share\\execution", android)
        f.verify("windows-x64", "\\\\server\\share\\execution", android)
    }

    @Test
    fun `changed template generated files inventory context and publication are rejected without rewrites`() {
        for (mutation in listOf("template", "local", "init", "extra", "missing", "package", "context", "sdk")) fixture { f ->
            f.prepare("jvm")
            when (mutation) {
                "template" -> f.consumer.resolve("src/commonMain/kotlin/Consumer.kt").appendText("changed")
                "local" -> f.consumer.resolve("local.properties").appendText("changed")
                "init" -> f.consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts").appendText("changed")
                "extra" -> f.consumer.resolve("extra.init.gradle.kts").writeText("unrequested")
                "missing" -> f.consumer.resolve("settings.gradle.kts").delete()
                "package" -> f.stage.resolve("outputs/maven/io/github/codex-agent-labs/codex-agent-jvm/3.4.5/codex-agent-jvm-3.4.5.pom").apply {
                    writeText(readText().replace("<version>1.2.3</version>", "<version>9.9.9</version>"))
                }
            }
            val before = inventory(f.root)
            assertFailsWith<IllegalStateException>(mutation) {
                f.verify("jvm", if (mutation == "context") "/different/execution" else "/original/execution",
                    if (mutation == "sdk") "/different/sdk" else "/original/sdk")
            }
            assertEquals(before, inventory(f.root), mutation)
        }
    }

    @Test
    fun `missing sources symbolic inputs and unsupported original paths fail closed`() = fixture { f ->
        f.prepare("jvm")
        for (path in listOf("relative", "/original/../execution", "/original//execution", "/original/execution/",
            "C:\\runner\\..\\execution", "C:/runner/execution", "/original/exec\nution")) {
            assertFailsWith<IllegalStateException>(path) { f.verify("jvm", path) }
        }
        assertFailsWith<IllegalStateException> { f.verify("unsupported") }
        val alias = f.root.resolve("alias")
        Files.createSymbolicLink(alias.toPath(), f.consumer.toPath())
        assertFailsWith<IllegalStateException> { f.verify("jvm", consumerInputs = alias) }
        f.template.resolve("src/commonMain/kotlin/Consumer.kt").delete()
        assertFailsWith<IllegalStateException> { f.verify("jvm") }
    }

    @Test
    fun `producer retains input-only sibling before process and leaves five-file execution layout unchanged`() = fixture { f ->
        val task = f.task {
            val captured = f.root.resolve("consumer-inputs")
            assertEquals(setOf("build.gradle.kts", "settings.gradle.kts", "src/commonMain/kotlin/Consumer.kt",
                "local.properties", ".codex-consumer-task-outcomes.init.gradle.kts"), verifiedRegularFiles(captured).keys)
            verifiedRegularFiles(captured).forEach { (relative, original) ->
                assertContentEquals(original.readBytes(), f.consumer.resolve(relative).readBytes())
            }
            f.consumer.resolve("build/generated.bin").apply { parentFile.mkdirs(); writeText("build output") }
        }
        task.verify()
        assertEquals(setOf("task-outcomes.json", "report.json", "process/execution.json", "process/stdout.bin",
            "process/stderr.bin"), verifiedRegularFiles(f.execution).keys)
        assertFalse(f.root.resolve("consumer-inputs/build").exists())
        assertTrue(f.root.resolve("consumer-inputs/local.properties").isFile)
    }

    @Test
    fun `producer guards stale overlap and symbolic retained inputs before cleanup and launch`() {
        for (mode in listOf("stale", "overlap", "symbolic")) fixture { f ->
            val task = f.task { error("must not execute") }
            f.consumer.mkdirs()
            val sentinel = f.consumer.resolve("sentinel").apply { writeText("original") }
            val captured = f.root.resolve("consumer-inputs")
            when (mode) {
                "stale" -> captured.mkdirs()
                "overlap" -> task.consumerInputsCaptureDirectory.set(f.template)
                "symbolic" -> Files.createSymbolicLink(captured.toPath(), f.template.toPath())
            }
            assertFailsWith<IllegalStateException>(mode) { task.verify() }
            assertEquals("original", sentinel.readText())
            assertFalse(f.execution.exists())
        }
    }

    @Test
    fun `failed or mutated execution keeps inputs and raw failure but removes success reports`() {
        for (mode in listOf("failure", "retained", "working")) fixture { f ->
            val task = f.task {
                when (mode) {
                    "failure" -> error("original process failed")
                    "retained" -> f.root.resolve("consumer-inputs/settings.gradle.kts").appendText("changed")
                    "working" -> f.consumer.resolve("settings.gradle.kts").appendText("changed")
                }
            }
            assertFailsWith<IllegalStateException>(mode) { task.verify() }
            assertTrue(f.root.resolve("consumer-inputs/local.properties").isFile)
            assertTrue(f.execution.resolve("process/execution.json").isFile)
            assertFalse(f.execution.resolve("report.json").exists())
            assertFalse(f.root.resolve("report.json").exists())
        }
    }

    private fun inventory(root: File) = verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }

    private fun fixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("facade-original-").toFile().canonicalFile
        try { block(Fixture(root)) } finally { root.deleteRecursively() }
    }

    private class Fixture(val root: File) {
        val source = root.resolve("source")
        val template = source.resolve("gradle/release/sdk-facade-consumer-template")
        val consumer = root.resolve("consumer")
        val stage = root.resolve("package-stage")
        val execution = root.resolve("execution")
        init {
            mapOf("build.gradle.kts" to "plugins {}\n", "settings.gradle.kts" to "rootProject.name = \"fixture\"\n",
                "src/commonMain/kotlin/Consumer.kt" to "fun consumer() = Unit\n").forEach { (path, text) ->
                template.resolve(path).apply { parentFile.mkdirs(); writeText(text) }
            }
            val generated = root.resolve("generated")
            FacadePublicationContractTest.Fixture(generated)
            val publications = facadePublicationSpecs.map { it.artifact to "facade/${it.publication}" } +
                ("codex-agent-bom" to "bom")
            publications.forEach { (artifact, directory) ->
                listOf("pom-default.xml" to "pom", "module.json" to "module").forEach { (name, extension) ->
                    generated.resolve("$directory/$name").copyTo(stage.resolve(
                        "outputs/maven/io/github/codex-agent-labs/$artifact/3.4.5/$artifact-3.4.5.$extension"
                    ).also { it.parentFile.mkdirs() })
                }
            }
        }

        fun prepare(target: String, original: String = "/original/execution", android: String = "/original/sdk") {
            prepareStagedConsumer(template, consumer, android)
            val separator = if (original.startsWith('/')) "/" else "\\"
            consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts").writeText(
                stagedConsumerOutcomeInitScript(listOf(sdkFacadeConsumerCompileTasks.getValue(target))) +
                    stagedConsumerExecutionCaptureScript(original + separator + "task-outcomes.json"))
        }

        fun verify(target: String, original: String = "/original/execution", android: String = "/original/sdk",
                   consumerInputs: File = consumer) = verifyOriginalSdkFacadeConsumerInputs(
            source, consumerInputs, stage, target, "1.2.3", "2.3.4", "3.4.5", "2.2.20", original, android)

        fun task(onProcess: () -> Unit): VerifyStagedKmpConsumerTask {
            val processes = Proxy.newProxyInstance(ExecOperations::class.java.classLoader,
                arrayOf(ExecOperations::class.java)) { _, method, arguments ->
                check(method.name == "exec")
                var workingDirectory = root
                val spec = Proxy.newProxyInstance(ExecSpec::class.java.classLoader,
                    arrayOf(ExecSpec::class.java)) { _, call, values ->
                    when (call.name) {
                        "workingDir", "setWorkingDir" -> { workingDirectory = values!![0] as File; null }
                        "getWorkingDir" -> workingDirectory
                        else -> null
                    }
                } as ExecSpec
                @Suppress("UNCHECKED_CAST")
                (arguments!![0] as Action<ExecSpec>).execute(spec)
                onProcess()
                Proxy.newProxyInstance(ExecResult::class.java.classLoader, arrayOf(ExecResult::class.java)) { proxy, call, _ ->
                    when (call.name) {
                        "getExitValue" -> 0
                        "assertNormalExitValue" -> proxy
                        else -> error("Unexpected result call: ${call.name}")
                    }
                } as ExecResult
            } as ExecOperations
            return ProjectBuilder.builder().withProjectDir(root).build().tasks.create(
                "consumer", VerifyStagedKmpConsumerTask::class.java, processes).apply {
                repositoryDirectory.set(stage)
                templateDirectory.set(template)
                mavenInventory.set(root.resolve("inventory.json").apply {
                    writeText("{\"groupId\":\"io.github.codex-agent-labs\"}")
                })
                gradleWrapper.set(root.resolve("gradlew").apply { writeText("original wrapper") })
                sdkVersion.set("3.4.5"); runtimeVersion.set("2.3.4")
                androidSdkDirectory.set("/original/sdk"); targetName.set("jvm")
                buildTasks.set(listOf("compileKotlinJvm"))
                consumerDirectory.set(consumer); resultFile.set(root.resolve("report.json"))
                executionCaptureDirectory.set(execution)
            }
        }
    }
}
