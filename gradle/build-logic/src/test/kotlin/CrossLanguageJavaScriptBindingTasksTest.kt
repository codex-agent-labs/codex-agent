import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class CrossLanguageJavaScriptBindingTasksTest {
    @Test
    fun `task declares the exact cacheable file evidence bundle`() = withTask { task, files ->
        val taskType = VerifyJavaScriptTypeScriptBindingParityTask::class.java
        assertNotNull(taskType.getAnnotation(CacheableTask::class.java))
        listOf(
            "ApiReport", "Coverage", "PackedApiReport", "NpmTarball", "PackedJUnit", "JsNodeJUnit",
        ).forEach { property ->
            assertNotNull(taskType.getMethod("get$property").getAnnotation(InputFile::class.java), property)
        }
        assertEquals(
            PathSensitivity.NAME_ONLY,
            taskType.getMethod("getNpmTarball").getAnnotation(PathSensitive::class.java).value,
        )
        listOf(
            "InstalledPackage",
            "PackedConsumerProgram",
            "CompiledJsNodeTestProgram",
        ).forEach { property ->
            assertNotNull(taskType.getMethod("get$property").getAnnotation(InputDirectory::class.java), property)
        }
        assertNotNull(taskType.getMethod("getReceiptFile").getAnnotation(OutputFile::class.java))
        assertTrue(task.apiReport.get().asFile == files.getValue("api-report.json"))
        assertTrue(task.coverage.get().asFile == files.getValue("coverage.json"))
        assertTrue(task.packedApiReport.get().asFile == files.getValue("packed-api.json"))
        assertTrue(task.npmTarball.get().asFile == files.getValue("package.tgz"))
        assertTrue(task.installedPackage.get().asFile == files.getValue("installed-package"))
        assertTrue(task.packedConsumerProgram.get().asFile == files.getValue("packed-consumer"))
        assertTrue(task.compiledJsNodeTestProgram.get().asFile == files.getValue("compiled-js-tests"))
        assertTrue(task.packedJUnit.get().asFile == files.getValue("packed-tests.xml"))
        assertTrue(task.jsNodeJUnit.get().asFile == files.getValue("js-node-tests.xml"))
        assertTrue(task.receiptFile.get().asFile == files.getValue("javascript-typescript-parity.json"))
    }

    @Test
    fun `failed evidence validation deletes a stale receipt first`() = withTask { task, files ->
        val stale = files.getValue("javascript-typescript-parity.json").apply { writeText("stale passed receipt") }

        assertFails { task.verify() }

        assertFalse(stale.exists())
    }

    @Test
    fun `transitive core prerequisite failure deletes a stale receipt first`() {
        val root = createTempDirectory("javascript-binding-preflight").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("""
                rootProject.name = "javascript-binding-preflight"
                include(":core", ":desktop")
            """.trimIndent())
            root.resolve("core").mkdirs()
            root.resolve("core/build.gradle.kts").writeText("""
                plugins { base }
                val preflight = tasks.register<Delete>("invalidateCrossLanguageBindingParityOutputs")
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                val failingPrerequisite = tasks.register("failingCanonicalTest") {
                    doLast { throw GradleException("intentional canonical prerequisite failure") }
                }
                tasks.register("verifyCrossLanguageApiCoverage") {
                    dependsOn(preflight, failingPrerequisite)
                }
            """.trimIndent())
            root.resolve("desktop").mkdirs()
            root.resolve("desktop/build.gradle.kts").writeText("""
                plugins { base }
                val receipt = layout.buildDirectory.file(
                    "reports/cross-language-api/bindings/javascript-typescript-parity.json",
                )
                val preflight = tasks.register<Delete>("invalidateJavaScriptTypeScriptBindingParityOutput") {
                    delete(receipt)
                }
                tasks.configureEach {
                    if (name != preflight.name) mustRunAfter(preflight)
                }
                project(":core").tasks.matching {
                    it.name == "invalidateCrossLanguageBindingParityOutputs"
                }.configureEach {
                    dependsOn(preflight)
                }
                tasks.register("verifyJavaScriptTypeScriptBindingParity") {
                    dependsOn(preflight, ":core:verifyCrossLanguageApiCoverage")
                }
            """.trimIndent())
            val stale = root.resolve(
                "desktop/build/reports/cross-language-api/bindings/javascript-typescript-parity.json",
            ).apply {
                parentFile.mkdirs()
                writeText("stale passed receipt")
            }

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(":desktop:verifyJavaScriptTypeScriptBindingParity", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":desktop:invalidateJavaScriptTypeScriptBindingParityOutput")?.outcome,
                result.output,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":core:failingCanonicalTest")?.outcome)
            assertTrue("intentional canonical prerequisite failure" in result.output)
            assertFalse(stale.exists())
            val wiring = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
            listOf(
                "tasks.configureEach",
                "mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)",
                "it.name == \"invalidateCrossLanguageBindingParityOutputs\"",
                "dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput)",
            ).forEach { contract ->
                assertTrue(contract in wiring, "Missing JavaScript/TypeScript preflight contract: $contract")
            }
        } finally {
            root.deleteRecursively()
        }
    }

    private fun withTask(block: (VerifyJavaScriptTypeScriptBindingParityTask, Map<String, File>) -> Unit) {
        val root = createTempDirectory("javascript-binding-task").toFile()
        try {
            val names = listOf(
                "api-report.json",
                "coverage.json",
                "packed-api.json",
                "package.tgz",
                "installed-package",
                "packed-consumer",
                "compiled-js-tests",
                "packed-tests.xml",
                "js-node-tests.xml",
                "javascript-typescript-parity.json",
            )
            val files = names.associateWith(root::resolve)
            listOf("installed-package", "packed-consumer", "compiled-js-tests").forEach {
                files.getValue(it).mkdirs()
            }
            listOf(
                "api-report.json",
                "coverage.json",
                "packed-api.json",
                "package.tgz",
                "packed-tests.xml",
                "js-node-tests.xml",
            ).forEach {
                files.getValue(it).writeText("invalid")
            }
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create(
                "verifyJavaScriptTypeScriptBindingParity",
                VerifyJavaScriptTypeScriptBindingParityTask::class.java,
            ).apply {
                apiReport.set(files.getValue("api-report.json"))
                coverage.set(files.getValue("coverage.json"))
                packedApiReport.set(files.getValue("packed-api.json"))
                npmTarball.set(files.getValue("package.tgz"))
                installedPackage.set(files.getValue("installed-package"))
                packedConsumerProgram.set(files.getValue("packed-consumer"))
                compiledJsNodeTestProgram.set(files.getValue("compiled-js-tests"))
                packedJUnit.set(files.getValue("packed-tests.xml"))
                jsNodeJUnit.set(files.getValue("js-node-tests.xml"))
                receiptFile.set(files.getValue("javascript-typescript-parity.json"))
            }
            block(task, files)
        } finally {
            root.deleteRecursively()
        }
    }
}
