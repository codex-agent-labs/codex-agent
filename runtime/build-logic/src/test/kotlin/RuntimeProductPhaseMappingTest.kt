import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeProductPhaseMappingTest {
    private val rootBuild = File("../build.gradle.kts").readText()
    private val runtimePlugin = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val nodeBuild = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
    private val adapterMetadataInputs =
        File("src/main/kotlin/RuntimeAdapterMetadataInputsTask.kt").readText()
    private val pythonTooling = File("src/main/kotlin/RuntimeProductPythonTooling.kt").readText()

    @Test
    fun `binding validation settings select Node Contract and require imported package`() {
        val settings = File("../settings.gradle.kts").readText()
        assertTrue("val bindingValidation = values.getValue(\"codexAgent.target\") == \"node-js-binding\" &&" in settings)
        assertTrue("commandLineProperties[\"codexAgent.component\"] == \"node-js\" && requestedPhase == \"validation\"" in settings)
        assertTrue("bindingValidation -> \"node-js\"" in settings)
        assertTrue("adapterHostValidation -> checkNotNull(requestedComponent)" in settings)
        assertTrue("\"--required-component\", contractComponent," in settings)
        assertTrue("val nativePredecessorProperty = if (bindingValidation) {\n        \"codexAgent.runtimePackageStage\"" in settings)
        assertTrue("component == \"node-js\" && phase == \"validation\" && target == \"node-js-binding\"" in rootBuild)
    }

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
        val nativeMetadata = nodeBuild.substringAfter("val runtimeNativeMetadataComponents = linkedMapOf(")
            .substringBefore("val runtimeAdapterMetadataComponents")
        assertTrue("tasks.register<ImportedRuntimeVariantTask>" in nativeMetadata)
        assertTrue("mapOf(\"runtime-variant\" to \"outputs\")" in nativeMetadata)
        assertFalse("validation-output-manifest.json" in nativeMetadata)
        assertFalse("dependsOn(" in nativeMetadata)
        assertFalse("mustRunAfter(invalidate)" in nativeMetadata)
    }

    @Test
    fun `adapter metadata owns canonical projection and Maven outputs without product work`() {
        val metadata = nodeBuild.substringAfter("val runtimeAdapterMetadataComponents = linkedMapOf(")
            .substringBefore("mavenPublishing {")
        listOf("jvm", "node-js", "node-wasm").forEach { component ->
            assertTrue("\"$component\"" in metadata, component)
        }
        listOf(
            "providers.gradleProperty(\"codexAgent.runtimeValidationHandoff\")",
            "providers.gradleProperty(\"codexAgent.runtimeMavenRepository\")",
            "ValidateRuntimeAdapterMetadataInputsTask",
            "it.resolve(\"projection.json\")",
            "into(\"evidence\")",
            "rename { \"\$component.json\" }",
            "from(layout.dir(importedRuntimeMavenRepository)) { into(\"maven\") }",
            "\"adapter-evidence\" to \"outputs/evidence\"",
            "\"maven\" to \"outputs/maven\"",
        ).forEach { contract -> assertTrue(contract in nodeBuild, contract) }
        listOf(
            "validation-output-manifest.json",
            "validation-manifest",
            "writeJvmRuntimeValidationOutputManifest",
            "writeNodeJsRuntimeValidationOutputManifest",
            "writeNodeWasmRuntimeValidationOutputManifest",
            "publish",
            "compile",
            "link",
        ).forEach { legacy -> assertFalse(legacy in metadata, legacy) }
        listOf(
            "@get:Internal\n    abstract val validationHandoff",
            "@get:InputFile",
            "@get:Internal\n    abstract val mavenRepository",
            "generateSequence(normalized) { it.parent }",
            "verifyRuntimeAdapterProjection(adapter, projectionFile.toFile())",
        ).forEach { contract -> assertTrue(contract in adapterMetadataInputs, contract) }
        assertFalse("@get:InputDirectory" in adapterMetadataInputs)
        assertTrue(metadata.indexOf("val invalidate =") < metadata.indexOf("val verifyInputs ="))
        assertTrue("dependsOn(invalidate)" in metadata.substringAfter("val verifyInputs =")
            .substringBefore("val stage ="))
        assertTrue("dependsOn(verifyInputs)" in metadata.substringAfter("val stage =")
            .substringBefore("registerRuntimeOutputManifest("))
        listOf(
            "validate_runtime_adapter_projection",
            "canonical_json_bytes(projection) != contents",
            "reject_symlink_parents=True",
        ).forEach { contract -> assertTrue(contract in pythonTooling, contract) }
    }

    @Test
    fun `adapter raw validation manifests retain their canonical evidence kinds`() {
        assertTrue("\"jvm-evidence\" to \"outputs/jvm-evidence\"" in runtimePlugin)
        val jvmValidation = jvmValidation()
        listOf(jvmValidation, nodeValidation()).forEach { source ->
            assertTrue("\"execution\" to \"outputs/execution\"" in source)
            assertTrue("\"test-report\" to \"outputs/test-report\"" in source)
            assertTrue("it.executionFile" in source)
            assertTrue("it.testReport" in source)
        }
        val nodeValidation = nodeValidation()
        assertTrue("\"node-evidence\" to \"outputs/node-evidence\"" in nodeValidation)
        assertFalse("adapter-evidence" in nodeValidation)
        assertFalse("\"maven\" to" in nodeValidation)
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
