import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ProductPhaseMappingContractTest {
    private val contract = File("src/main/kotlin/codexagent.contract-product.gradle.kts").readText()
    private val desktop = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val javascript = File("src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText()
    private val nativeWrappers = File("src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts").readText()
    private val node = File("../../codex-agent-runtime-desktop/build.gradle.kts").readText()
    private val manifestTask = File("src/main/kotlin/ProductOutputManifestGradleTask.kt").readText()

    @Test
    fun root_lifecycle_maps_the_exact_initial_Contract_and_Runtime_phases() {
        val mapping = between(contract, "val requestedProduct =", "val contractBundleDirectory =")
        val expected = linkedMapOf(
            Triple("contract", "contract", "binary") to "writeContractBinaryOutputManifest",
            Triple("runtime", "macos-arm64", "binary") to
                "writeMacosArm64RuntimeBinaryOutputManifest",
            Triple("runtime", "macos-x64", "binary") to
                "writeMacosX64RuntimeBinaryOutputManifest",
            Triple("runtime", "linux-arm64", "binary") to
                "writeLinuxArm64RuntimeBinaryOutputManifest",
            Triple("runtime", "linux-x64", "binary") to
                "writeLinuxX64RuntimeBinaryOutputManifest",
            Triple("runtime", "windows-x64", "binary") to
                "writeMingwX64RuntimeBinaryOutputManifest",
            Triple("runtime", "jvm", "binary") to "writeJvmRuntimeBinaryOutputManifest",
            Triple("runtime", "node-js", "binary") to "writeNodeJsRuntimeBinaryOutputManifest",
            Triple("runtime", "node-wasm", "binary") to "writeNodeWasmRuntimeBinaryOutputManifest",
            Triple("runtime", "macos-arm64", "package") to
                "writeMacosArm64RuntimePackageOutputManifest",
            Triple("runtime", "macos-x64", "package") to
                "writeMacosX64RuntimePackageOutputManifest",
            Triple("runtime", "linux-arm64", "package") to
                "writeLinuxArm64RuntimePackageOutputManifest",
            Triple("runtime", "linux-x64", "package") to
                "writeLinuxX64RuntimePackageOutputManifest",
            Triple("runtime", "windows-x64", "package") to
                "writeMingwX64RuntimePackageOutputManifest",
            Triple("runtime", "jvm", "package") to "writeJvmRuntimePackageOutputManifest",
            Triple("runtime", "node-js", "package") to "writeNodeJsRuntimePackageOutputManifest",
            Triple("runtime", "node-wasm", "package") to
                "writeNodeWasmRuntimePackageOutputManifest",
            Triple("runtime", "macos-arm64", "validation") to
                "writeMacosArm64RuntimeValidationOutputManifest",
            Triple("runtime", "macos-x64", "validation") to
                "writeMacosX64RuntimeValidationOutputManifest",
            Triple("runtime", "linux-arm64", "validation") to
                "writeLinuxArm64RuntimeValidationOutputManifest",
            Triple("runtime", "linux-x64", "validation") to
                "writeLinuxX64RuntimeValidationOutputManifest",
            Triple("runtime", "windows-x64", "validation") to
                "writeMingwX64RuntimeValidationOutputManifest",
            Triple("runtime", "jvm", "validation") to "writeJvmRuntimeValidationOutputManifest",
            Triple("runtime", "node-js", "validation") to
                "writeNodeJsRuntimeValidationOutputManifest",
            Triple("runtime", "node-wasm", "validation") to
                "writeNodeWasmRuntimeValidationOutputManifest",
            Triple("sdk", "javascript", "package") to
                "writeJavaScriptSdkPackageOutputManifest",
            Triple("sdk", "python", "package") to
                "writePythonNativeWrapperSdkPackageOutputManifest",
            Triple("sdk", "csharp", "package") to
                "writeCSharpNativeWrapperSdkPackageOutputManifest",
            Triple("sdk", "rust", "package") to
                "writeRustNativeWrapperSdkPackageOutputManifest",
            Triple("sdk", "cpp", "package") to
                "writeCppNativeWrapperSdkPackageOutputManifest",
            Triple("sdk", "dart", "package") to
                "writeDartNativeWrapperSdkPackageOutputManifest",
        )

        assertEquals(expected.size, Regex("""Triple\("""").findAll(mapping).count())
        expected.forEach { (selection, task) ->
            val key = "Triple(\"" + selection.first + "\", \"" + selection.second +
                "\", \"" + selection.third + "\")"
            assertTrue(key in mapping, "Missing product phase selection: $key")
            assertEquals(1, Regex(Regex.escape(task)).findAll(mapping).count(), task)
        }
        assertEquals(1, Regex("""tasks\.register\("ciProductPhase"\)""").findAll(mapping).count())
        assertTrue("requestedProduct.get()" in mapping)
        assertTrue("requestedComponent.get()" in mapping)
        assertTrue("requestedPhase.get()" in mapping)
        assertTrue("else -> error(\"Unsupported product phase:" in mapping)
        listOf("orNull", "orElse", "onlyIf", "enabled = false").forEach { fallback ->
            assertFalse(fallback in mapping, fallback)
        }
    }

    @Test
    fun every_mapped_stage_uses_the_one_output_manifest_task_type() {
        assertTrue(
            "val writeContractBinaryOutputManifest = tasks.register<WriteProductOutputManifestTask>(" in
                contract,
        )
        val native = nativePhases()
        assertEquals(
            2,
            Regex("tasks\\.register<WriteProductOutputManifestTask>").findAll(native).count(),
        )
        assertTrue(
            "val writeJvmRuntimeBinaryOutputManifest = tasks.register<WriteProductOutputManifestTask>(" in
                desktop,
        )
        assertTrue(
            "tasks.register<WriteProductOutputManifestTask>(\"writeJvmRuntimePackageOutputManifest\")" in
                desktop,
        )
        assertTrue(
            "tasks.register<WriteProductOutputManifestTask>(\"writeJvmRuntimeValidationOutputManifest\")" in
                desktop,
        )
        assertTrue(
            "tasks.register<WriteProductOutputManifestTask>(" +
                "\"write\${targetTitle}RuntimeValidationOutputManifest\")" in nativeValidation(),
        )
        listOf(
            "writeNodeJsRuntimeBinaryOutputManifest",
            "writeNodeWasmRuntimeBinaryOutputManifest",
            "writeNodeJsRuntimePackageOutputManifest",
            "writeNodeWasmRuntimePackageOutputManifest",
        )
            .forEach { task ->
                assertTrue(
                    "tasks.register<WriteProductOutputManifestTask>(\"$task\")" in node,
                    task,
                )
            }
        assertTrue(
            "tasks.register<WriteProductOutputManifestTask>(" +
                "\"write\${title}RuntimeValidationOutputManifest\")" in nodeValidation(),
        )
        assertTrue(
            "tasks.register<WriteProductOutputManifestTask>(" +
                "\"writeJavaScriptSdkPackageOutputManifest\")" in javascriptPackage(),
        )
        assertEquals(
            1,
            Regex("tasks\\.register<WriteProductOutputManifestTask>").findAll(nativeWrapperPackage()).count(),
        )
        assertEquals(1, Regex("abstract class WriteProductOutputManifestTask").findAll(manifestTask).count())
    }

    @Test
    fun native_stages_declare_the_exact_raw_and_packaged_output_families() {
        val native = nativePhases()
        val binary = native.substringBefore("val packagePhaseRoot =")
        val packages = native.substringAfter("val packagePhaseRoot =")
        assertEquals(
            mapOf(
                "app-server" to "outputs/app-server",
                "c-abi" to "outputs/c-abi",
                "kmp-klib" to "outputs/kmp-klib",
                "supervisor" to "outputs/supervisor",
                "validation-runner" to "outputs/validation-runner",
            ),
            outputRoots(binary),
        )
        listOf("app-server", "c-abi", "kmp-klib", "supervisor", "validation-runner")
            .forEach { root ->
                assertTrue("into(\"$root" in binary, "Native binary stage does not populate $root")
            }
        assertEquals(
            mapOf(
                "app-server" to "outputs/app-server",
                "c-abi" to "outputs/c-abi",
                "validation-runner" to "outputs/validation-runner",
            ),
            outputRoots(packages),
        )
        listOf("app-server", "c-abi", "validation-runner").forEach { root ->
            assertTrue("into(\"$root\")" in packages, "Native package stage does not populate $root")
        }
        assertTrue("desktopManifest.distributions.associate" in native)
        assertTrue("crossLanguageCAbiTargetSpecs.getValue(target)" in native)
    }

    @Test
    fun native_binary_stage_uses_the_requested_target_supervisor_and_imported_stages_are_snapshotted() {
        val native = nativePhases()
        val binary = native.substringBefore("val packagePhaseRoot =")
        assertTrue("directory.resolve(target).resolve(distribution.supervisorExecutableName)" in binary)
        assertTrue("if (!providers.gradleProperty(\"codexAgent.desktopSupervisorDirectory\").isPresent)" in binary)
        assertTrue("dependsOn(compileDesktopProcessSupervisor)" in binary)
        assertTrue("from(binarySupervisor) { into(\"supervisor\") }" in binary)
        assertFalse("from(compileDesktopProcessSupervisor.flatMap { it.outputFile })" in binary)
        assertTrue("tasks.register<SnapshotImportedProductStageTask>" in binary)
        assertTrue("stageRoot.set(importedBinarySnapshotRoot)" in binary)
        assertTrue("packageBinaryStageRoot = if (importedRuntimeBinaryStage.isPresent)" in native)
    }

    @Test
    fun JVM_and_Node_binary_and_package_stages_declare_only_adapter_and_validation_runner() {
        val expected = mapOf(
            "adapter" to "outputs/adapter",
            "validation-runner" to "outputs/validation-runner",
        )
        val stages = listOf(
            between(
                desktop,
                "val stageJvmRuntimeBinaryOutputs =",
                "val jvmRuntimePackagePhaseRoot =",
            ) to "writeJvmRuntimeBinaryOutputManifest",
            between(
                desktop,
                "val stageJvmRuntimePackage =",
                "check(desktopManifest.distributions",
            ) to "writeJvmRuntimePackageOutputManifest",
            between(node, "val stageNodeJsRuntimeBinaryOutputs =", "val nodeWasmRuntimeBinaryPhaseRoot =") to
                "writeNodeJsRuntimeBinaryOutputManifest",
            between(node, "val stageNodeWasmRuntimeBinaryOutputs =", "val nodeJsRuntimePackagePhaseRoot =") to
                "writeNodeWasmRuntimeBinaryOutputManifest",
            between(node, "val stageNodeJsRuntimePackage =", "val nodeWasmRuntimePackagePhaseRoot =") to
                "writeNodeJsRuntimePackageOutputManifest",
            between(node, "val stageNodeWasmRuntimePackage =", "mavenPublishing {") to
                "writeNodeWasmRuntimePackageOutputManifest",
        )
        stages.forEach { (stage, task) ->
            assertEquals(expected, outputRoots(stage), task)
            assertTrue("into(\"adapter\")" in stage, task)
            assertTrue("into(\"validation-runner\")" in stage, task)
            assertTrue("tasks.register<WriteProductOutputManifestTask>(" in stage, task)
        }
    }

    @Test
    fun native_validation_stages_declare_only_C_ABI_and_native_evidence() {
        val validation = nativeValidation()
        assertEquals(
            mapOf(
                "c-abi" to "outputs/c-abi",
                "c-abi-reference" to "outputs/c-abi-reference",
                "native" to "outputs/native",
            ),
            outputRoots(validation),
        )
        listOf("c-abi", "c-abi-reference", "native").forEach { root ->
            assertTrue("into(\"$root" in validation, "Native validation does not populate $root")
        }
        assertTrue("phase.set(\"validation\")" in validation)
        assertTrue("dependsOn(cAbiPackageEvidence, importedNativeEvidence)" in validation)

        val handoff = nativeValidationHandoff()
        val packageInputs = between(
            handoff,
            "cAbiPackageEvidence.configure {",
            "val stageValidation =",
        )
        assertEquals(
            2,
            Regex("""validationPackageRoot\.zip\(desktopRuntimeCompatibilityVersion\)""")
                .findAll(packageInputs).count(),
        )
        assertTrue(
            "root.file(\"outputs/c-abi/" +
                "\${crossLanguageCAbiArchiveFileName(version, distribution.target)}\")" in packageInputs,
        )
        assertTrue(
            "\"outputs/app-server/codex-agent-runtime-desktop-\$version-" +
                "\${distribution.classifier}.zip\"," in packageInputs,
        )
        assertFalse("project.version" in packageInputs)
    }

    @Test
    fun mapped_native_validation_derives_legacy_target_from_component_but_accepts_explicit_target() {
        val targetRouting = between(
            desktop,
            "val requestedEvidenceTarget =",
            "val cAbiConsumerSources =",
        )
        assertTrue(
            "providers.gradleProperty(\"codexAgent.desktopEvidenceTarget\").orElse(" in targetRouting,
        )
        assertTrue(
            "requestedEvidenceTarget?.let { check(it in desktopRuntimeEvidenceTargets)" in targetRouting,
        )
        assertTrue(
            "providers.gradleProperty(\"codexAgent.component\").map { component ->" in targetRouting,
        )
        assertTrue("crossLanguageCAbiTargetSpecs.entries.single" in targetRouting)
        assertTrue(
            "it.value.classifier.removePrefix(\"c-abi-\") == component" in targetRouting,
        )
        assertTrue(
            "inputs.property(\"requestedTarget\", productPhaseEvidenceTarget.orElse(\"\"))" in
                nativeValidationHandoff(),
        )
    }

    @Test
    fun JVM_validation_verifies_both_packages_and_stages_only_JVM_evidence() {
        val validation = jvmValidation()
        assertEquals(
            mapOf("jvm-evidence" to "outputs/jvm-evidence"),
            outputRoots(validation),
        )
        assertTrue("into(\"jvm-evidence\")" in validation)
        assertTrue(
            "val jvmValidationPackageRoot = if (importedRuntimePackageStage.isPresent)" in validation,
        )
        assertTrue(
            "val jvmValidationNativePackageRoot = if (importedRuntimeNativePackageStage.isPresent)" in
                validation,
        )
        assertTrue("imported-runtime-native-package-stages/\$tree/jvm/\$component" in validation)
        listOf(
            "verifyImportedJvmRuntimePackageOutputManifest",
            "verifyImportedJvmValidationNativePackageOutputManifest",
        ).forEach { task ->
            assertTrue(task in validation, task)
        }
        assertEquals(
            2,
            Regex("tasks\\.register<VerifyImportedProductOutputManifestTask>").findAll(validation).count(),
        )
        assertTrue("stageRoot.set(importedJvmPackageSnapshotRoot)" in validation)
        assertTrue("stageRoot.set(importedJvmNativePackageSnapshotRoot)" in validation)
        assertEquals(2, Regex("tasks\\.register<SnapshotImportedProductStageTask>").findAll(validation).count())
        assertTrue(
            "tasks.register<Delete>(\"invalidateJvmRuntimeValidationOutputs\")" in validation,
        )
        assertTrue("dependsOn(invalidateJvmRuntimeValidationOutputs)" in validation)
        assertTrue(
            "tasks.register<RecordJvmRuntimeEvidenceTask>(" in validation &&
                "\"executeImportedJvmRuntimeEvidence\"" in validation,
        )
        assertTrue(
            "dependsOn(invalidateJvmRuntimeValidationOutputs, jvmPackagePrerequisite, " +
                "jvmNativePackagePrerequisite)" in validation,
        )
    }

    @Test
    fun Node_validation_reuses_existing_executors_and_stages_evidence_and_report() {
        val validation = nodeValidation()
        assertEquals(
            mapOf(
                "node-evidence" to "outputs/node-evidence",
                "test-report" to "outputs/test-report",
            ),
            outputRoots(validation),
        )
        listOf("node-evidence", "test-report").forEach { root ->
            assertTrue("into(\"$root\")" in validation, root)
        }
        assertTrue("providers.gradleProperty(\"codexAgent.runtimePackageStage\")" in validation)
        assertTrue(
            "providers.gradleProperty(\"codexAgent.runtimeNativePackageStage\")" in validation,
        )
        assertTrue("val packageRoot = if (importedNodeRuntimePackageStage.isPresent)" in validation)
        assertTrue(
            "val nodeValidationNativePackageRoot = if (importedNodeRuntimeNativePackageStage.isPresent)" in
                validation,
        )
        assertEquals(
            2,
            Regex("tasks\\.register<VerifyImportedProductOutputManifestTask>").findAll(validation).count(),
        )
        assertTrue("stageRoot.set(importedPackageSnapshotRoot)" in validation)
        assertTrue("stageRoot.set(importedNodeNativePackageSnapshotRoot)" in validation)
        assertTrue(
            "tasks.register<Delete>(\"invalidate\${title}RuntimeValidationOutputs\")" in validation,
        )
        assertTrue("tasks.named<RecordNodeRuntimeEvidenceTask>(" in validation)
        assertTrue(
            "dependsOn(invalidate, packagePrerequisite, nativePackagePrerequisite)" in validation,
        )
        assertTrue("evidenceTask.flatMap { it.evidenceFile }" in validation)
        assertTrue("evidenceTask.flatMap { it.testReport }" in validation)
        assertEquals(
            2,
            Regex("^registerNodeRuntimeValidation\\(", RegexOption.MULTILINE)
                .findAll(validation).count(),
        )
        listOf("\"node-js\"", "\"node-wasm\"").forEach { component ->
            assertTrue(component in validation, component)
        }
        assertTrue("val nodeValidationSnapshotOwner = providers.gradleProperty(\"codexAgent.component\")" in validation)
        assertTrue("imported-runtime-native-package-stages/\$tree/\$owner/\$nodeValidationComponent" in validation)
    }

    @Test
    fun JavaScript_package_consumes_verified_Contract_and_Runtime_artifacts_only() {
        val imported = javascriptImportedHandoff()
        assertEquals(
            3,
            Regex("tasks\\.register<VerifyImportedProductOutputManifestTask>")
                .findAll(imported).count(),
        )
        val contractManifest = between(
            imported,
            "val verifyImportedNpmContractBinaryOutputManifest =",
            "val verifyImportedNpmRuntimePackageOutputManifest =",
        )
        listOf(
            "product.set(\"contract\")",
            "component.set(\"contract\")",
            "phase.set(\"binary\")",
            "target.set(\"common\")",
            "stageRoot.set(importedNpmContractSnapshotRoot)",
        ).forEach { contract -> assertTrue(contract in contractManifest, contract) }

        val runtimeManifest = between(
            imported,
            "val verifyImportedNpmRuntimePackageOutputManifest =",
            "val verifyImportedNpmRuntimeValidationOutputManifest =",
        )
        val behaviorManifest = between(
            imported,
            "val verifyImportedNpmRuntimeValidationOutputManifest =",
            "val generateJavaScriptEnumDeclarations =",
        )
        listOf(
            "product.set(\"runtime\")",
            "component.set(\"node-js\")",
            "phase.set(\"package\")",
            "target.set(\"node-js\")",
            "stageRoot.set(importedNpmRuntimeSnapshotRoot)",
        ).forEach { contract -> assertTrue(contract in runtimeManifest, contract) }
        listOf(
            "product.set(\"runtime\")",
            "component.set(\"node-js-binding\")",
            "phase.set(\"validation\")",
            "target.set(\"node-js\")",
            "stageRoot.set(importedNpmRuntimeValidationSnapshotRoot)",
        ).forEach { contract -> assertTrue(contract in behaviorManifest, contract) }

        assertTrue("it.file(\"outputs/evidence/canonical-api.json\")" in imported)
        assertTrue("it.dir(\"outputs/adapter\")" in imported)
        assertTrue("dependsOn(verifyImportedNpmContractBinaryOutputManifest)" in imported)
        assertTrue("dependsOn(verifyImportedNpmRuntimePackageOutputManifest)" in imported)
        assertTrue("verifyImportedNpmRuntimeValidationOutputManifest" in imported)
        assertFalse(":codex-agent-core:" in imported)
        assertFalse("jsProductionExecutableCompileSync" in imported)

        val sdkPackage = javascriptPackage()
        assertEquals(mapOf("package" to "outputs/package"), outputRoots(sdkPackage))
        assertEquals(
            1,
            Regex("tasks\\.register<WriteProductOutputManifestTask>").findAll(sdkPackage).count(),
        )
        assertTrue("dependsOn(packageNpm)" in sdkPackage)
        assertTrue("from(npmArchiveFile) { into(\"package\") }" in sdkPackage)
        listOf(
            "product.set(\"sdk\")",
            "component.set(\"javascript\")",
            "phase.set(\"package\")",
            "target.set(\"node\")",
        ).forEach { contract -> assertTrue(contract in sdkPackage, contract) }
    }

    @Test
    fun initial_product_phase_seam_contains_no_deferred_planner_cache_key_or_receipt_logic() {
        val seam = listOf(
            between(contract, "val writeContractBinaryOutputManifest =", "val contractBundleDirectory ="),
            nativePhases(),
            between(
                desktop,
                "val jvmRuntimeBinaryPhaseRoot =",
                "check(desktopManifest.distributions",
            ),
            between(node, "val nodeJsRuntimeBinaryPhaseRoot =", "mavenPublishing {"),
            nativeValidation(),
            jvmValidation(),
            nodeValidation(),
            javascriptImportedHandoff(),
            javascriptPackage(),
            nativeWrapperPackage(),
            manifestTask,
        ).joinToString("\n")
        listOf(
            "buildKey",
            "computeBuildKey",
            "write-phase-receipt",
            "PhaseReceipt",
            "phaseReceipt",
            "receiptFile",
            "ci.products.plan",
            "ci.products.restore",
            "ProductPlan",
            "ProductRegistry",
            "productCache",
            "cacheKey",
            "artifactLookup",
        ).forEach { forbidden ->
            assertFalse(forbidden in seam, "Product phase seam introduced deferred logic: $forbidden")
        }
    }

    private fun nativePhases(): String = between(
        desktop,
        "val runtimeNativeBinaryManifestTasks =",
        "val cAbiArchiveFiles =",
    )

    private fun nativeValidation(): String = between(
        desktop,
        "val validationPhaseRoot =",
        "val jvmValidationTarget =",
    )

    private fun nativeValidationHandoff(): String = between(
        desktop,
        "val productPhaseEvidenceTarget =",
        "val jvmValidationTarget =",
    )

    private fun jvmValidation(): String = between(
        desktop,
        "val jvmValidationTarget =",
        "pluginManager.withPlugin(\"maven-publish\")",
    )

    private fun nativeWrapperPackage(): String = between(
        nativeWrappers,
        "val nativeWrapperRuntimeStageRoot =",
        "val nativeWrapperReleaseDirectory =",
    )

    private fun nodeValidation(): String = between(
        node,
        "val importedNodeRuntimePackageStage =",
        "mavenPublishing {",
    )

    private fun javascriptImportedHandoff(): String = between(
        javascript,
        "val importedNpmContractBinaryStage =",
        "inputs.file(npmGeneratedDeclaration)",
    )

    private fun javascriptPackage(): String = between(
        javascript,
        "val javascriptSdkPackagePhaseRoot =",
        "val verifyNpmPackDryRun =",
    )

    private fun between(source: String, start: String, end: String): String {
        assertTrue(start in source, "Missing source marker: $start")
        val tail = source.substringAfter(start)
        assertTrue(end in tail, "Missing source marker after $start: $end")
        return tail.substringBefore(end)
    }

    private fun outputRoots(source: String): Map<String, String> {
        assertTrue("outputRoots.set(mapOf(" in source, "Missing outputRoots declaration")
        val values = source.substringAfter("outputRoots.set(mapOf(").substringBefore("))")
        return Regex("\"([^\"]+)\" to \"([^\"]+)\"").findAll(values).associate { match ->
            match.groupValues[1] to match.groupValues[2]
        }
    }
}
