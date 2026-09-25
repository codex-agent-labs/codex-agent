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
            val original = root.resolve("original-input.json").apply { writeText("original fixture bytes\n") }
            java.nio.file.Files.createSymbolicLink(root.resolve("symbolic-input.json").toPath(), original.toPath())
            java.nio.file.Files.createSymbolicLink(root.resolve("symbolic-parent").toPath(), root.toPath())
            root.resolve("build.gradle.kts").writeText("""
                import java.nio.file.Path
                val variantProperties = listOf("Identity", "BinaryReceipt", "PackageReceipt", "ValidationReceipt",
                    "CAbiArchive", "AppServerArchive", "ValidationEvidence").map { "codexAgent.runtimeVariant" + it }
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
                    variantProperties.forEach { commandLineProperties[it] = ${quote(original.path)} }
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
                        for (component in native) {
                            check(route(component, "metadata", component,
                                mapOf("codexAgent.runtimePackageStage" to null)) == component)
                        }
                        for (property in variantProperties) {
                            for (bad in listOf(null, "", "relative.json", ${quote(root.resolve("missing.json").path)},
                                ${quote(root.resolve("predecessor").path)}, ${quote(root.resolve("symbolic-input.json").path)},
                                ${quote(root.resolve("symbolic-parent/original-input.json").path)},
                                ${quote(root.resolve("predecessor/../original-input.json").path)})) {
                                check(runCatching { route("macos-arm64", "metadata", "macos-arm64",
                                    mapOf(property to bad)) }.isFailure) { property + ": " + bad }
                            }
                            val systemProperty = "org.gradle.project." + property
                            val previous = System.getProperty(systemProperty)
                            try {
                                System.setProperty(systemProperty, ${quote(original.path)})
                                check(runCatching { route("macos-arm64", "metadata", "macos-arm64") }.isFailure)
                            } finally {
                                if (previous == null) System.clearProperty(systemProperty) else System.setProperty(systemProperty, previous)
                            }
                        }
                        for (component in adapters) {
                            // Metadata consumes the original package/version,
                            // never an unrelated caller-supplied Maven tree.
                            check(route(component, "metadata", component,
                                mapOf("codexAgent.runtimePackageVersion" to "0.2.4")) == component)
                            check(route(component, "metadata", component,
                                mapOf("codexAgent.runtimePackageVersion" to "0.2.4-rc.1")) == component)
                            for (bad in listOf(null, "", "relative", ${quote(root.resolve("missing").path)},
                                ${quote(original.path)}, ${quote(root.resolve("symbolic-parent").path)},
                                ${quote(root.resolve("symbolic-parent/predecessor").path)},
                                ${quote(root.resolve("predecessor/../predecessor").path)})) {
                                check(runCatching { route(component, "metadata", component,
                                    mapOf("codexAgent.runtimePackageStage" to bad)) }.isFailure) {
                                    component + " metadata package stage: " + bad
                                }
                            }
                            for (bad in listOf(null, "", "latest", "0.2", "01.2.0", "0.2.4-01",
                                "0.2.4-rc.01", " 0.2.4", "0.2.4\n")) {
                                check(runCatching { route(component, "metadata", component,
                                    mapOf("codexAgent.runtimePackageVersion" to bad)) }.isFailure) {
                                    component + " metadata original version: " + bad
                                }
                            }
                            for (bad in listOf("", ${quote(root.resolve("predecessor").path)})) {
                                check(runCatching { route(component, "metadata", component,
                                    mapOf("codexAgent.runtimeMavenRepository" to bad)) }.isFailure) {
                                    component + " metadata must reject an external Maven tree"
                                }
                            }
                            for (property in listOf("runtimePackageStage", "runtimePackageVersion", "runtimeMavenRepository")) {
                                val systemProperty = "org.gradle.project.codexAgent." + property
                                val previous = System.getProperty(systemProperty)
                                try {
                                    System.setProperty(systemProperty, if (property == "runtimePackageVersion") "0.2.4"
                                        else ${quote(root.resolve("predecessor").path)})
                                    check(runCatching { route(component, "metadata", component) }.isFailure) {
                                        component + " metadata must reject system-property input: " + property
                                    }
                                } finally {
                                    if (previous == null) System.clearProperty(systemProperty) else System.setProperty(systemProperty, previous)
                                }
                            }
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
            java.nio.file.Files.deleteIfExists(root.resolve("symbolic-parent").toPath())
            java.nio.file.Files.deleteIfExists(root.resolve("symbolic-input.json").toPath())
            root.deleteRecursively()
        }
    }

    private fun quote(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"")
        .replace("\n", "\\n").replace("\r", "\\r").replace("$", "\\$") + "\""
}
