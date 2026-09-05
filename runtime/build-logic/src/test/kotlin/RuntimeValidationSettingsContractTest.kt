import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class RuntimeValidationSettingsContractTest {
    @Test
    fun `settings admit exactly registry routes and require original artifact inputs`() {
        val repository = File("../..").canonicalFile
        val settings = File("../settings.gradle.kts").readText()
        val boundary = "val runtimeTargets =" + settings.substringAfter("    val runtimeTargets =")
            .substringBefore("    if (values.getValue(\"codexAgent.target\") in nativeRuntimeTargets &&")
        val semver = settings.lineSequence().single { it.trimStart().startsWith("val semver =") }
        val process = ProcessBuilder("python3", "-c", """
            from ci.products.registry import PHASE_INSTANCE_IDS
            for i in PHASE_INSTANCE_IDS:
                if i.product == 'runtime' and i.component != 'runtime-aggregate':
                    print('/'.join((i.component, i.phase, i.target)))
        """.trimIndent()).directory(repository).redirectErrorStream(true).start()
        val registry = process.inputStream.bufferedReader().readText()
        check(process.waitFor() == 0) { registry }
        val root = createTempDirectory("runtime-settings-matrix-").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"runtime-settings-matrix\"\n")
            root.resolve("predecessor").mkdir()
            root.resolve("build.gradle.kts").writeText("""
                import java.nio.file.Path
                fun route(component: String, phase: String, target: String, change: Map<String, String?> = emptyMap()): String {
                    val commandLineProperties = mutableMapOf(
                        "codexAgent.product" to "runtime", "codexAgent.component" to component,
                        "codexAgent.phase" to phase, "codexAgent.target" to target,
                        "codexAgent.runtimeBinaryStage" to ${quote(root.resolve("predecessor").path)},
                        "codexAgent.runtimePackageStage" to ${quote(root.resolve("predecessor").path)},
                        "codexAgent.runtimeNativePackageStage" to ${quote(root.resolve("predecessor").path)},
                        "codexAgent.runtimePackageVersion" to "0.2.4",
                        "codexAgent.runtimeNativePackageVersion" to "0.2.1",
                    )
                    change.forEach { (name, value) -> if (value == null) commandLineProperties.remove(name) else commandLineProperties[name] = value }
                    val values = mapOf("codexAgent.target" to target)
                    fun absoluteNormalizedPath(name: String): Path = Path.of(commandLineProperties.getValue(name)).also {
                        require(it.isAbsolute && it.normalize() == it)
                    }
                    $semver
                    $boundary
                    return contractComponent
                }
                tasks.register("verify") {
                    doLast {
                        val expected = ${quote(registry)}.trim().lines().toSet()
                        val native = listOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
                        val adapters = listOf("jvm", "node-js", "node-wasm")
                        var accepted = 0
                        for (component in native + adapters) for (phase in listOf("binary", "package", "validation", "metadata")) {
                            for (target in native + adapters + "node-js-binding") {
                                val identity = listOf(component, phase, target).joinToString("/")
                                val result = runCatching { route(component, phase, target) }
                                check(result.isSuccess == (identity in expected)) { identity + ": " + result }
                                if (result.isSuccess) {
                                    check(result.getOrThrow() == component) { identity }
                                    accepted++
                                }
                            }
                        }
                        check(accepted == expected.size)
                        for (component in adapters) {
                            for (missing in listOf("runtimePackageStage", "runtimeNativePackageStage", "runtimePackageVersion", "runtimeNativePackageVersion")) {
                                check(runCatching { route(component, "validation", "macos-arm64", mapOf("codexAgent." + missing to null)) }.isFailure)
                            }
                            for (bad in listOf("", "latest", "0.2", "01.2.0")) {
                                check(runCatching { route(component, "validation", "macos-arm64", mapOf("codexAgent.runtimePackageVersion" to bad)) }.isFailure)
                            }
                            check(runCatching { route(component, "validation", "macos-arm64", mapOf("codexAgent.runtimeNativePackageStage" to "relative")) }.isFailure)
                        }
                        check(runCatching { route("node-js", "validation", "node-js-binding", mapOf("codexAgent.runtimePackageVersion" to null)) }.isFailure)
                        check(runCatching { route("jvm", "validation", "macos-arm64", mapOf("codexAgent.product" to "sdk")) }.isFailure)
                        println("Exact registry settings matrix passed: " + accepted)
                    }
                }
            """.trimIndent() + "\n")
            val result = GradleRunner.create().withProjectDir(root)
                .withArguments("verify", "--offline", "--console=plain", "--no-configuration-cache").build()
            assertTrue("Exact registry settings matrix passed:" in result.output, result.output)
            assertTrue("verifyCommand += listOf(\"--required-component\", requestedTarget)" in settings)
        } finally {
            root.deleteRecursively()
        }
    }

    private fun quote(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
        .replace("\n", "\\n").replace("\r", "\\r").replace("$", "\\$") + "\""
}
