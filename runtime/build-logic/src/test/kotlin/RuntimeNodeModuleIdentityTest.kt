import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class RuntimeNodeModuleIdentityTest {
    @Test
    fun `standalone root name does not change either Node compiler output module`() {
        val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        val targets = "    js {" + source.substringAfter("    js {")
            .substringBefore("    applyDefaultHierarchyTemplate {")
        check("wasmJs {" in targets)
        val root = createTempDirectory("runtime-node-module-identity").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"different-standalone-name\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
                import org.jetbrains.kotlin.gradle.targets.js.ir.KotlinJsIrTarget
                plugins { id("org.jetbrains.kotlin.multiplatform") }
                @OptIn(ExperimentalWasmDsl::class)
                kotlin {
                    $targets
                }
                val observedNames = kotlin.targets.withType<KotlinJsIrTarget>()
                    .associate { it.name to it.outputModuleName.get() }
                tasks.register("verifyNodeModuleNames") {
                    val actualNames = observedNames
                    doLast {
                        check(actualNames == mapOf(
                            "js" to "codex-agent-codex-agent-runtime-desktop",
                            "wasmJs" to "codex-agent-codex-agent-runtime-desktop",
                        )) { "Compiler module identity drift: " + actualNames }
                    }
                }
                """.trimIndent(),
            )
            val result = GradleRunner.create().withProjectDir(root).withPluginClasspath()
                .withArguments("verifyNodeModuleNames", "--offline", "--configuration-cache",
                    "--configuration-cache-problems=fail")
                .build()
            assertTrue(result.tasks.none { it.path.contains("compile", ignoreCase = true) })
        } finally {
            root.deleteRecursively()
        }
    }
}
