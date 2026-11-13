import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Exercises production guards and the real manifest verifier, not Runtime product acceptance. */
class RuntimeImportedBinaryVersionTest {
    private val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val repository = File("../..").canonicalFile
    private val nodeSource = repository.resolve("codex-agent-runtime-desktop/build.gradle.kts").readText()
    private val components = listOf(
        "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64", "jvm", "node-js", "node-wasm",
    )

    private fun fixture(root: File, extra: String = "") {
        val guard = "val importedRuntimeBinaryVersion =" + source
            .substringAfter("val importedRuntimeBinaryVersion =")
            .substringBefore("val importedRuntimePackageStage =")
        check("importedRuntimeBinaryVersion.get()" in guard)
        val identity = "internal val PRODUCT_SEMVER =" +
            File("src/main/kotlin/RuntimeEvidenceIdentity.kt").readText()
                .substringAfter("internal val PRODUCT_SEMVER =")
        check("fun runtimeCompatibilityVersion(releaseVersion: String)" in identity)
        root.resolve("settings.gradle.kts").writeText("rootProject.name = \"original-runtime-binary\"\n")
        root.resolve("build.gradle.kts").writeText(
            """
            import java.io.File
            import org.gradle.api.Project
            import org.gradle.api.file.Directory
            import org.gradle.api.file.FileCollection
            import org.gradle.api.provider.Provider
            import org.gradle.api.tasks.Exec
            import org.gradle.api.tasks.TaskProvider
            plugins { base }
            $identity
            val runtimeProductVersion = providers.provider { "0.2.9" }
            $guard
            tasks.register("checkGuard")
            $extra
            """.trimIndent(),
        )
    }

    private fun runner(root: File, properties: Map<String, String>, vararg tasks: String) =
        GradleRunner.create().withProjectDir(root).withArguments(
            tasks.toList() + listOf("--offline", "--configuration-cache", "--configuration-cache-problems=fail") +
                properties.map { (key, value) -> "-PcodexAgent.$key=$value" },
        )

    @Test
    fun `canonical packages require explicit original binary inputs and compatible strict version`() {
        val root = createTempDirectory("runtime-binary-version-guard").toFile().canonicalFile
        try {
            fixture(root)
            val properties = mapOf(
                "product" to "runtime", "phase" to "package", "component" to "jvm", "target" to "jvm",
                "runtimeBinaryStage" to root.resolve("original").absolutePath, "runtimeBinaryVersion" to "0.2.0",
            )
            assertTrue(runner(root, properties, "checkGuard").build().tasks.none { "compile" in it.path })
            for ((key, message) in listOf(
                "runtimeBinaryStage" to "requires explicit -PcodexAgent.runtimeBinaryStage",
                "runtimeBinaryVersion" to "requires explicit -PcodexAgent.runtimeBinaryVersion",
            )) {
                for (values in listOf(properties - key, properties + (key to ""))) {
                    val result = runner(root, values, "checkGuard").buildAndFail()
                    assertTrue(message in result.output)
                    assertTrue(result.tasks.isEmpty())
                }
            }
            for ((version, message) in listOf(
                "0.3.0" to "current Runtime compatibility line",
                "0.2.0+run.1" to "canonical SemVer without build metadata",
                " 0.2.0" to "canonical SemVer without build metadata",
            )) {
                val result = runner(root, properties + ("runtimeBinaryVersion" to version), "checkGuard").buildAndFail()
                assertTrue(message in result.output)
                assertTrue(result.tasks.isEmpty())
            }
            // Unrelated artifact-only phases must not acquire a binary-input prerequisite.
            runner(root, mapOf("product" to "runtime", "phase" to "metadata"), "checkGuard").build()
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `all eight original binary manifests bind supplied version and exact unchanged inventory`() {
        val root = createTempDirectory("runtime-original-binary-manifest").toFile().canonicalFile
        try {
            val registration = File("src/main/kotlin/RuntimeProductStageRegistration.kt").readText()
            val environment = "private fun Exec.useTrustedRuntimePython" + registration
                .substringAfter("private fun Exec.useTrustedRuntimePython")
                .substringBefore("abstract class ValidateRuntimeEvidenceTargetTask")
            val verifier = "fun Project.registerRuntimeOutputVerification(" + registration
                .substringAfter("fun Project.registerRuntimeOutputVerification(")
            check("\"--product-version\", version.get()" in verifier)
            val declarations = components.mapIndexed { index, component ->
                """
                registerRuntimeOutputVerification(
                    "verifyOriginal$index", tasks.named("checkGuard"), providers.provider { "$component" },
                    "binary", providers.provider { "$component" }, importedRuntimeBinaryVersion,
                    layout.projectDirectory.dir("original/$component").let { providers.provider { it } },
                    files(), File("${repository.invariantSeparatorsPath}"),
                )
                """.trimIndent()
            }.joinToString("\n")
            fixture(root, "$environment\n$verifier\n$declarations")
            components.forEach { component ->
                val stage = root.resolve("original/$component")
                stage.resolve("outputs/adapter/value.bin").apply {
                    parentFile.mkdirs()
                    writeText("synthetic original $component bytes\n")
                }
                val process = ProcessBuilder(
                    "python3", "-B", "-m", "ci.products", "receipt", "write-output-manifest",
                    "--root", stage.absolutePath, "--product", "runtime", "--component", component,
                    "--phase", "binary", "--target", component, "--product-version", "0.2.0",
                    "--output-root", "adapter=outputs/adapter",
                ).directory(repository).redirectErrorStream(true).start()
                val output = process.inputStream.bufferedReader().readText()
                assertEquals(0, process.waitFor(), output)
            }
            val originals = root.resolve("original").walkTopDown().filter(File::isFile)
                .associate { it to it.readBytes() }
            val properties = mapOf(
                "product" to "runtime", "phase" to "package", "runtimeBinaryVersion" to "0.2.0",
                "runtimeBinaryStage" to root.resolve("original").absolutePath,
            )
            val tasks = components.indices.map { "verifyOriginal$it" }.toTypedArray()
            val success = runner(root, properties, *tasks).build()
            assertEquals(8, success.tasks.count { it.path.startsWith(":verifyOriginal") })
            val wrongVersion = runner(root, properties + ("runtimeBinaryVersion" to "0.2.1"), *tasks).buildAndFail()
            assertTrue("Output manifest productVersion does not match the expected identity" in wrongVersion.output)
            originals.forEach { (file, bytes) -> assertContentEquals(bytes, file.readBytes()) }
            val mutated = root.resolve("original/node-js/outputs/adapter/value.bin")
            mutated.appendText("changed content\n")
            val wrongBytes = runner(root, properties, "verifyOriginal6").buildAndFail()
            assertTrue("Declared file inventory does not match the complete regular-file tree" in wrongBytes.output)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `native JVM and Node imported verifiers use original version while writers retain current version`() {
        val native = source.substringAfter("val verifyImportedBinaryManifest =")
            .substringBefore("val packagedRuntimeLibrary")
            .substringBefore(").also")
        val jvm = source.substringAfter("val verifyImportedJvmRuntimeBinaryOutputManifest =")
            .substringBefore(").also")
        val js = nodeSource.substringAfter("val verifyImportedNodeJsRuntimeBinaryOutputManifest =")
            .substringBefore(").also")
        val wasm = nodeSource.substringAfter("val verifyImportedNodeWasmRuntimeBinaryOutputManifest =")
            .substringBefore(").also")
        for (call in listOf(native, jvm, js, wasm)) {
            assertTrue("registerRuntimeOutputVerification(" in call)
            assertTrue("importedRuntimeBinaryVersion," in call)
            assertFalse("runtimeProductVersion," in call)
        }
        assertTrue("project.extra[\"codexAgent.runtimeBinaryVersion\"] as Provider<String>" in nodeSource)
        for (script in listOf(source, nodeSource)) {
            val writers = script.split("registerRuntimeOutputManifest(").drop(1)
            assertTrue(writers.isNotEmpty())
            writers.forEach { writer ->
                val arguments = writer.substringBefore("runtimeProductTooling,")
                assertTrue("runtimeProductVersion," in arguments)
                assertFalse("importedRuntimeBinaryVersion," in arguments)
            }
        }
    }
}
