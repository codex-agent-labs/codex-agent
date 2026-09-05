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
import org.junit.Assume.assumeTrue

class CrossLanguageJavaScriptBindingTasksTest {
    @Test
    fun `native npm preserves the staged compatibility resource without producing an archive`() {
        assumeTrue(
            "Native npm inventory fixture requires CODEX_AGENT_TEST_NPM_INVENTORY=1; a skip is not package acceptance",
            System.getenv("CODEX_AGENT_TEST_NPM_INVENTORY") == "1",
        )
        val root = createTempDirectory("javascript-native-npm-inventory").toFile()
        try {
            val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
                .first { it.resolve("codex-agent-bindings/javascript/package/package.json.template").isFile }
            val sources = repository.resolve("codex-agent-bindings/javascript/package")
            val staged = root.resolve("package").apply { mkdirs() }
            listOf("index.cjs", "index.mjs", "index.d.ts", "README.md").forEach { name ->
                sources.resolve(name).copyTo(staged.resolve(name))
            }
            listOf("LICENSE", "THIRD_PARTY_NOTICES.md").forEach { name ->
                repository.resolve(name).copyTo(staged.resolve(name))
            }
            val manifest = staged.resolve("package.json")
            val manifestContents = sources.resolve("package.json.template").readText().replace("@VERSION@", "0.2.0")
            manifest.writeText(manifestContents)
            // File-selection fixture only: no compiled Runtime or authenticated package evidence.
            staged.resolve("dist").mkdirs()
            staged.resolve("dist/runtime.js").writeText("module.exports = {};\n")
            staged.resolve("dist/runtime.js.map").writeText("{}\n")
            val compatibilityPath = "META-INF/codex-agent/sdk-compatibility.json"
            staged.resolve(compatibilityPath).apply { parentFile.mkdirs(); writeText("{}\n") }
            val before = verifiedRegularFiles(staged).mapValues { it.value.releaseDigest() }
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val task = project.tasks.create("verifyNpmInventory", VerifyJavaScriptNpmPackInventoryTask::class.java).apply {
                packageDirectory.set(staged)
                cacheDirectory.set(root.resolve("npm-cache"))
            }
            task.verify()
            val omitted = manifestContents.replace(",\n    \"$compatibilityPath\"", "")
            check(omitted != manifestContents) { "Tracked compatibility allow-list seam changed" }
            manifest.writeText(omitted)
            val failure = assertFails { task.verify() }
            assertTrue("npm pack file inventory differs" in failure.message.orEmpty(), failure.toString())
            manifest.writeText(manifestContents)
            task.verify()
            assertEquals(before, verifiedRegularFiles(staged).mapValues { it.value.releaseDigest() })
            assertFalse(root.walkTopDown().any { it.isFile && it.extension == "tgz" })
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `npm inventory includes compatibility and exactly matches staged package`() {
        val root = createTempDirectory("javascript-npm-inventory").toFile()
        try {
            root.resolve("package.json").writeText("""{"name":"@codex-agent-labs/codex-agent","version":"0.2.0"}""")
            root.resolve("index.cjs").writeText("module.exports = {};\n")
            val compatibilityPath = "META-INF/codex-agent/sdk-compatibility.json"
            val compatibility = root.resolve(compatibilityPath).apply {
                parentFile.mkdirs()
                writeText("{}\n")
            }
            val files = verifiedRegularFiles(root).map { (path, file) ->
                """{"path":"$path","size":${file.length()}}"""
            }
            fun report(records: List<String>) =
                """[{"name":"@codex-agent-labs/codex-agent","version":"0.2.0","files":[${records.joinToString(",")}]}]"""
            verifyJavaScriptNpmPackInventory(root, report(files))
            listOf(
                files.filterNot { compatibilityPath in it },
                files + """{"path":"extra","size":1}""",
                files + files.first(),
                files.map { if (compatibilityPath in it) it.replace("\"size\":3", "\"size\":4") else it },
            ).forEach { invalid -> assertFails { verifyJavaScriptNpmPackInventory(root, report(invalid)) } }
            assertFails { verifyJavaScriptNpmPackInventory(root, report(files).replace("0.2.0", "0.2.1")) }
            assertFails { verifyJavaScriptNpmPackInventory(root, "[]") }
            compatibility.delete()
            assertFails {
                verifyJavaScriptNpmPackInventory(root, report(files.filterNot { compatibilityPath in it }))
            }
            val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
                .first { it.resolve("codex-agent-bindings/javascript/package/package.json.template").isFile }
            val template = repository.resolve("codex-agent-bindings/javascript/package/package.json.template")
                .readReleaseObject()
            assertEquals(1, template.releaseArray("files").count { it.toString() == "\"$compatibilityPath\"" })
        } finally {
            root.deleteRecursively()
        }
    }

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
    fun `transitive imported prerequisite failure deletes a stale receipt first`() {
        val root = createTempDirectory("javascript-binding-preflight").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("""
                rootProject.name = "javascript-binding-preflight"
                include(":sdk")
            """.trimIndent())
            root.resolve("sdk").mkdirs()
            root.resolve("sdk/build.gradle.kts").writeText("""
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
                val failingPrerequisite = tasks.register("verifyImportedRuntimeManifest") {
                    doLast { throw GradleException("intentional imported manifest failure") }
                }
                tasks.register("verifyJavaScriptTypeScriptBindingParity") {
                    dependsOn(preflight, failingPrerequisite)
                }
            """.trimIndent())
            val stale = root.resolve(
                "sdk/build/reports/cross-language-api/bindings/javascript-typescript-parity.json",
            ).apply {
                parentFile.mkdirs()
                writeText("stale passed receipt")
            }

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(":sdk:verifyJavaScriptTypeScriptBindingParity", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":sdk:invalidateJavaScriptTypeScriptBindingParityOutput")?.outcome,
                result.output,
            )
            assertEquals(TaskOutcome.FAILED, result.task(":sdk:verifyImportedRuntimeManifest")?.outcome)
            assertTrue("intentional imported manifest failure" in result.output)
            assertFalse(stale.exists())
            val wiring = File("src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText()
            listOf(
                "tasks.configureEach",
                "mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)",
                "rootProject.tasks.matching { it.name == \"prepareContractInputs\" }",
                "verifyImportedNpmContractBinaryOutputManifest",
                "verifyImportedNpmRuntimePackageOutputManifest",
                "verifyImportedNpmRuntimeValidationOutputManifest",
                "dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput)",
            ).forEach { contract ->
                assertTrue(contract in wiring, "Missing JavaScript/TypeScript preflight contract: $contract")
            }
            assertFalse(":codex-agent-core:" in wiring)
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
