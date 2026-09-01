import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeProductPhaseMappingTest {
    private val rootBuild = File("../build.gradle.kts").readText()
    private val runtimePlugin = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val nodeBuild = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()

    @Test
    fun `standalone lifecycle maps every exact Runtime phase and verification target`() {
        val mapping = rootBuild.substringAfter("val runtimePhaseTasks = mapOf(")
            .substringBefore("\ntasks.register(\"ciProductPhase\")")
        val actual = Regex("""\("([^"]+)" to "([^"]+)"\) to "([^"]+)"""")
            .findAll(mapping)
            .associate { match ->
                (match.groupValues[1] to match.groupValues[2]) to match.groupValues[3]
            }
        val componentTitles = linkedMapOf(
            "macos-arm64" to "MacosArm64",
            "macos-x64" to "MacosX64",
            "linux-arm64" to "LinuxArm64",
            "linux-x64" to "LinuxX64",
            "windows-x64" to "MingwX64",
            "jvm" to "Jvm",
            "node-js" to "NodeJs",
            "node-wasm" to "NodeWasm",
        )
        val expected = buildMap {
            componentTitles.forEach { (component, title) ->
                listOf("binary", "package", "validation", "metadata").forEach { phase ->
                    put(
                        component to phase,
                        "write${title}Runtime${phase.replaceFirstChar(Char::uppercase)}OutputManifest",
                    )
                }
            }
        }

        assertEquals(expected, actual)
        listOf(
            "check(requestedProduct.get() == \"runtime\")",
            "check(target == component)",
            "error(\"Unsupported Runtime phase:",
            "tasks.register(\"verifyRuntime\")",
            "runtimePhaseTasks[target to \"metadata\"]",
        ).forEach { contract -> assertTrue(contract in rootBuild, contract) }
        listOf("orNull", "orElse", "onlyIf", "enabled = false").forEach { fallback ->
            assertFalse(fallback in mapping, fallback)
        }
    }

    @Test
    fun `mapped output manifests preserve binary to package to validation artifact edges`() {
        listOf(
            "\"write\${title}RuntimeBinaryOutputManifest\"",
            "\"write\${title}RuntimePackageOutputManifest\"",
            "\"write\${targetTitle}RuntimeValidationOutputManifest\"",
            "\"writeJvmRuntimeBinaryOutputManifest\"",
            "\"writeJvmRuntimePackageOutputManifest\"",
            "\"writeJvmRuntimeValidationOutputManifest\"",
        ).forEach { task -> assertTrue(task in runtimePlugin, task) }
        listOf(
            "\"writeNodeJsRuntimeBinaryOutputManifest\"",
            "\"writeNodeJsRuntimePackageOutputManifest\"",
            "\"writeNodeWasmRuntimeBinaryOutputManifest\"",
            "\"writeNodeWasmRuntimePackageOutputManifest\"",
            "\"write\${title}RuntimeValidationOutputManifest\"",
        ).forEach { task -> assertTrue(task in nodeBuild, task) }

        assertTrue(
            "dependsOn(if (importedRuntimeBinaryStage.isPresent) verifyImportedBinaryManifest " +
                "else writeBinaryManifest)" in runtimePlugin,
        )
        assertTrue("dependsOn(invalidateValidationOutputs, packagePrerequisite)" in runtimePlugin)
        assertTrue("writeJvmRuntimeBinaryOutputManifest" in jvmPackage())
        assertTrue("dependsOn(invalidateJvmRuntimeValidationOutputs" in jvmValidation())
        assertTrue("writeNodeJsRuntimeBinaryOutputManifest" in nodeJsPackage())
        assertTrue("writeNodeWasmRuntimeBinaryOutputManifest" in nodeWasmPackage())
        assertTrue("dependsOn(invalidate, packagePrerequisite, nativePackagePrerequisite)" in nodeValidation())
        assertTrue("val runtimeValidationManifestTasks = linkedMapOf(" in nodeBuild)
        assertTrue("validation-output-manifest.json" in nodeBuild)
        assertTrue("mustRunAfter(invalidate)" in nodeBuild)
    }

    private fun jvmPackage() = runtimePlugin.substringAfter("val stageJvmRuntimePackage =")
        .substringBefore("check(desktopManifest.distributions")

    private fun jvmValidation() = runtimePlugin.substringAfter("val importedJvmPackageSnapshotRoot =")
        .substringBefore("pluginManager.withPlugin(\"maven-publish\")")

    private fun nodeJsPackage() = nodeBuild.substringAfter("val stageNodeJsRuntimePackage =")
        .substringBefore("val nodeWasmRuntimePackagePhaseRoot =")

    private fun nodeWasmPackage() = nodeBuild.substringAfter("val stageNodeWasmRuntimePackage =")
        .substringBefore("mavenPublishing {")

    private fun nodeValidation() = nodeBuild.substringAfter("fun registerNodeRuntimeValidation(")
        .substringBefore("val nodeJsBindingValidationRoot =")
}
