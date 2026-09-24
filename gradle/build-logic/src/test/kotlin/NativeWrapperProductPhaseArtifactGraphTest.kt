import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class NativeWrapperProductPhaseArtifactGraphTest {
    @Test
    fun `imported validation SDKs keep original verifiers without restaging producers`() {
        val property = sdk.substringAfter("val importedNativeWrapperStagedSdks =")
            .substringBefore("val nativeWrapperRuntimeSnapshotRoot =")
        assertTrue("\"codexAgent.nativeWrapperStagedSdkRoot\"" in property)
        assertTrue(".map(::file)" in property)
        assertFalse(".orElse(" in property)
        val installed = sdk.substringAfter("val nativeWrapperInstalledConsumerTasks =")
            .substringBefore("val nativeWrapperCapabilityEvidenceTasks =")
        assertTrue("dependsOn(snapshot)" in installed)
        val consumer = installed.substringAfter("tasks.register<NativeWrapperInstalledConsumerTask>")
        val beforeBranch = consumer.substringBefore("if (importedNativeWrapperStagedSdks.isPresent)")
        assertTrue("dependsOn(verify)" in beforeBranch)
        val branch = consumer.substringAfter("if (importedNativeWrapperStagedSdks.isPresent) {")
        val imported = branch.substringBefore("} else {")
        val default = branch.substringAfter("} else {").substringBefore("this.language.set(language)")
        assertTrue("dependsOn(snapshotImportedNativeWrapperRuntimeStages)" in imported)
        assertTrue("stagedSdkDirectory.set(layout.dir(importedNativeWrapperStagedSdks))" in imported)
        assertTrue("dependsOn(stageNativeWrapperCAbiSdks)" in default)
        assertTrue("stagedSdkDirectory.set(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory })" in default)
        val afterBranch = consumer.substringAfter("this.language.set(language)")
        for (forbidden in listOf("stageNativeWrapperCAbiSdks", "generateNativeWrapperSdkCompatibility")) {
            assertFalse(forbidden in beforeBranch, forbidden)
            assertFalse(forbidden in imported, forbidden)
            assertFalse(forbidden in afterBranch, forbidden)
        }
        for (binding in listOf(
            "packageStageDirectory.set(importedSnapshot)",
            "packageReceipt.set(rootProject.layout.file(providers.gradleProperty(\"codexAgent.sdkPackageReceipt\").map(::file)))",
            "compatibilityRequest.set(layout.file(nativeWrapperSdkCompatibilityRequest))",
            "runtimeStageDirectory.set(nativeWrapperRuntimeSnapshotRoot)",
            "expectedClassifier.set(providers.gradleProperty(\"codexAgent.target\"))",
        )) assertTrue(binding in afterBranch, binding)
        val capability = sdk.substringAfter("val nativeWrapperCapabilityEvidenceTasks =")
            .substringBefore("nativeWrapperLanguageSpecs.forEach")
        assertTrue("val authenticated = nativeWrapperInstalledConsumerTasks.getValue(language)" in capability)
        assertTrue("dependsOn(authenticated)" in capability)
    }

    @Test
    fun `native validation stages once and writes manifest only after complete existing producers`() {
        val installed = sdk.substringAfter("val nativeWrapperInstalledConsumerTasks =")
            .substringBefore("val nativeWrapperCapabilityEvidenceTasks =")
        val capability = sdk.substringAfter("val nativeWrapperCapabilityEvidenceTasks =")
            .substringBefore("nativeWrapperLanguageSpecs.forEach")
        val manifest = sdk.substringAfter("nativeWrapperLanguageSpecs.forEach")
            .substringBefore("val nativeWrapperReleaseDirectory =")
        assertTrue("product-stage/sdk/\$language/validation" in installed)
        assertTrue("outputs/installed" in installed)
        assertTrue("delete(importedSnapshot, validationStage)" in installed)
        assertTrue("outputs/package-negatives" in installed)
        assertTrue("outputs/capability" in capability)
        assertTrue("authenticated.flatMap { it.packageNegativeEvidenceDirectory }" in capability)
        assertTrue("tasks.register<WriteProductOutputManifestTask>" in manifest)
        assertTrue("dependsOn(nativeWrapperCapabilityEvidenceTasks.getValue(language))" in manifest)
        for (root in listOf("installed", "capability", "package-negatives")) {
            assertTrue("\"native-wrapper-$root\" to \"outputs/$root\"" in manifest)
        }
        assertTrue("if (language == \"cpp\")" in manifest)
        assertTrue("target.set(providers.gradleProperty(\"codexAgent.target\"))" in manifest)
        assertTrue("productVersion.set(nativeWrapperSdkVersion)" in manifest)
        assertFalse("Sync" in manifest)
        assertFalse("copy" in manifest)
        val task = File("src/main/kotlin/NativeWrapperCapabilityEvidenceTask.kt").readText()
        assertTrue("\"verify-evidence\"" in task)
        assertTrue("--expected-test-program" in task)
        assertTrue("dartPackageConfig.orNull?.asFile, negatives" in task)
        assertTrue(task.indexOf("val before = capabilityInputInventory(inputs)") < task.indexOf("\"verify-evidence\""))
        assertTrue(task.indexOf("\"verify-evidence\"") < task.indexOf("val command = nativeWrapperCapabilityCommand("))
        assertTrue("before == capabilityInputInventory(inputs)" in task)
    }

    private val desktop = File("../../runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts")
        .readText()
    private val sdk = File("src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts").readText()
    private val sdkProduct = File("src/main/kotlin/codexagent.sdk-product.gradle.kts").readText()
    private val nativeWrapperTasks = File("src/main/kotlin/CrossLanguageNativeWrapperGradleTasks.kt").readText()

    @Test
    fun `native wrapper package phases require the exact imported Runtime artifact closure`() {
        val start = "val nativeWrapperRuntimeStageRoot ="
        val end = "val nativeWrapperReleaseDirectory ="
        assertFalse(start in desktop, "Desktop Runtime still registers SDK wrapper tasks")
        assertTrue(start in sdk, "Missing SDK-owned native-wrapper Runtime artifact seam")
        val seam = sdk.substringAfter(start).substringBefore(end)

        assertTrue("providers.gradleProperty(\"codexAgent.nativeWrapperRuntimeStageRoot\")" in seam)
        assertTrue(".map(::file)" in seam)
        assertTrue("snapshotImportedNativeWrapperRuntimeStages" in seam)
        assertTrue("dependsOn(snapshotImportedNativeWrapperRuntimeStages, generateNativeWrapperSdkCompatibility)" in seam)
        assertFalse(".orElse(" in seam, "Imported native-wrapper Runtime stages must not fall back locally")
        listOf(
            "stageNativeWrapperCAbiSdks",
            "compatibilityRequest.set(layout.file(nativeWrapperSdkCompatibilityRequest))",
        ).forEach { contract -> assertTrue(contract in seam, contract) }
        assertFalse("productVersion.set(nativeWrapperRuntimeVersion)" in seam,
            "Original phase versions must come from authenticated receipts, not current aggregate")
        assertTrue("runtimeProductVersion.set(nativeWrapperRuntimeVersion)" in seam)
        assertTrue("nativeWrapperRuntimeVersion.map(::runtimeCompatibilityVersion)" in seam)
        val privateSnapshot = nativeWrapperTasks.substringAfter("fun stage() {")
            .substringBefore("private fun nativeWrapperSdkInput")
        val snapshot = privateSnapshot.indexOf("snapshotWithCanonicalProducer(")
        val verification = privateSnapshot.indexOf("verifyRuntimeStageManifests(")
        val consumption = privateSnapshot.indexOf("stageCrossLanguageNativeWrapperSdks(")
        assertTrue(snapshot >= 0 && snapshot < verification && verification < consumption)
        assertTrue("\"ci.products.sdk_compatibility\"" in nativeWrapperTasks)
        assertTrue("\"--runtime-stage-root\"" in nativeWrapperTasks)
        assertTrue("verifiedCompatibility.readBytes().contentEquals(expectedCompatibility.readBytes())" in nativeWrapperTasks)
        assertEquals(1, Regex("private fun verifyRuntimeStageManifests").findAll(nativeWrapperTasks).count())
        listOf(
            "cAbiArchiveFiles",
            "importedCAbiEvidenceDirectory",
            "cAbiReviewedHeader",
            "cAbiLicense",
            "cAbiNotice",
            "cAbiExportPolicy",
            "cAbiConsumerSources",
            "cAbiPackageTasks",
        ).forEach { forbidden ->
            assertFalse(forbidden in seam, "Native-wrapper SDK seam still reads Runtime-owned input: $forbidden")
        }

        mapOf(
            "python" to "Python",
            "csharp" to "CSharp",
            "rust" to "Rust",
            "cpp" to "Cpp",
            "dart" to "Dart",
        ).forEach { (language, title) ->
            listOf(
                "stage${title}NativeWrapperSdkPackagePhase",
                "write${title}NativeWrapperSdkPackageOutputManifest",
                "product-stage/sdk/$language/package",
            ).forEach { value -> assertTrue(value in seam, value) }
        }
        listOf(
            "product.set(\"sdk\")",
            "phase.set(\"package\")",
            "target.set(\"desktop\")",
            "productVersion.set(nativeWrapperSdkVersion)",
            "\"evidence\" to \"outputs/evidence\"",
            "\"package\" to \"outputs/\$language\"",
            "tasks.register<PackageNativeWrapperSdkTask>(stageTaskName)",
            "this.language.set(language)",
            "dependsOn(nativeWrapperPackageSourceTasks.getValue(language), stageNativeWrapperCAbiSdks)",
            "sourcesDirectory.set(layout.buildDirectory.dir(\"native-wrapper-package-sources/\$language\"))",
        ).forEach { value -> assertTrue(value in seam, value) }
        assertTrue("tasks.register<Sync>(\"stage\${evidenceTitle}Evidence\")" in seam)
        assertTrue("include(\"sdk-compatibility.json\")" in seam)
        assertFalse("include(\"codex-agent-native-wrapper-sdks.json\"" in seam)
        assertFalse("dependsOn(prepareNativeWrapperPackageSources, stageNativeWrapperCAbiSdks)" in seam)
        assertFalse("layout.buildDirectory.dir(\"product-stage/sdk/\$language/package\")" in
            sdk.substringAfter("val invalidateNativeWrapperProductPhaseOutputs =").substringBefore(
                "val nativeWrapperRuntimeSnapshotRoot =",
            ))
    }

    @Test
    fun `ciProductPhase maps every native wrapper package component exactly`() {
        val mapping = sdkProduct.substringAfter("tasks.register(\"sdkProductPhase\")")
        mapOf(
            "python" to "Python",
            "csharp" to "CSharp",
            "rust" to "Rust",
            "cpp" to "Cpp",
            "dart" to "Dart",
        ).forEach { (language, title) ->
            assertTrue(
                "Triple(\"sdk\", \"$language\", \"package\")" in mapping,
                "Missing SDK package route for $language",
            )
            assertEquals(
                1,
                Regex.escape("write${title}NativeWrapperSdkPackageOutputManifest")
                    .toRegex().findAll(mapping).count(),
                language,
            )
            assertTrue(
                "sdk.get().tasks.named(\"write${title}NativeWrapperSdkPackageOutputManifest\")" in mapping,
                language,
            )
            assertFalse(
                "desktopRuntime.get().tasks.named(\"write${title}NativeWrapperSdkPackageOutputManifest\")" in mapping,
                language,
            )
        }
    }

    @Test
    fun `all five native wrapper package dry runs contain imported consumers only`() {
        val importedStages = createTempDirectory("native-wrapper-runtime-stages").toFile()
        try {
            val manifestTasks = listOf("Python", "CSharp", "Rust", "Cpp", "Dart").map { title ->
                ":codex-agent-sdk:write${title}NativeWrapperSdkPackageOutputManifest"
            }
            val result = GradleRunner.create()
                .withProjectDir(repositoryRoot)
                .withArguments(
                    *manifestTasks.toTypedArray(),
                    "-PcodexAgent.nativeWrapperRuntimeStageRoot=${importedStages.absolutePath}",
                    "-PcodexAgent.candidateCommit=${"a".repeat(40)}",
                    "-PcodexAgent.candidateTree=${"b".repeat(40)}",
                    "--dry-run",
                    "--console=plain",
                    "--stacktrace",
                )
                .build()
            val paths = Regex("^(:[^ ]+) SKIPPED$", setOf(RegexOption.MULTILINE))
                .findAll(result.output)
                .map { it.groupValues[1] }
                .toSet()

            manifestTasks.forEach { assertTrue(it in paths, it) }
            assertTrue(":codex-agent-sdk:generateNativeWrapperSdkCompatibility" in paths)
            listOf("Python", "CSharp", "Rust", "Cpp", "Dart").forEach { title ->
                assertTrue(":codex-agent-sdk:prepare${title}NativeWrapperPackageSource" in paths)
                assertTrue(":codex-agent-sdk:stage${title}NativeWrapperSdkPackagePhase" in paths)
                assertTrue(":codex-agent-sdk:stage${title}NativeWrapperSdkPackageEvidence" in paths)
            }
            assertTrue(":codex-agent-sdk:stageNativeWrapperCAbiSdks" in paths)
            assertTrue(":codex-agent-sdk:snapshotImportedNativeWrapperRuntimeStages" in paths)
            assertTrue(":codex-agent-sdk:materializeNativeWrapperPackageAssets" in paths)

            val forbiddenTaskNames = listOf(
                Regex("^(compile|link|package|generate|record|execute).+", RegexOption.IGNORE_CASE),
                Regex("^write.+Runtime(Binary|Package|Validation)OutputManifest$"),
                Regex("^stage.+Runtime(Binary|Packages|Package|Validation).*$"),
            )
            val forbidden = paths.filter { path ->
                val name = path.substringAfterLast(':')
                name != "generateNativeWrapperSdkCompatibility" &&
                    forbiddenTaskNames.any { it.matches(name) }
            }
            assertTrue(forbidden.isEmpty(), "Runtime producer tasks are reachable: $forbidden")
            assertTrue(paths.none { it.startsWith(":codex-agent-core:") }, paths.toString())
            assertTrue(paths.none { it.startsWith(":codex-agent-runtime-desktop:") }, paths.toString())
        } finally {
            importedStages.deleteRecursively()
        }
    }

    @Test
    fun `SDK Maven package invalidates stale outputs before an imported binary failure`() {
        val temporary = createTempDirectory("missing-sdk-binary-stage").toFile()
        val missing = temporary.resolve("absent")
        val phaseRoot = repositoryRoot.resolve("codex-agent-sdk/build/product-stage/sdk/sdk-core/package")
        phaseRoot.resolve("outputs/maven/stale").apply {
            parentFile.mkdirs()
            writeText("stale")
        }
        phaseRoot.resolve("output-manifest.json").writeText("stale")
        try {
            GradleRunner.create()
                .withProjectDir(repositoryRoot)
                .withArguments(
                    "ciProductPhase",
                    "-PcodexAgent.product=sdk",
                    "-PcodexAgent.component=sdk-core",
                    "-PcodexAgent.phase=package",
                    "-PcodexAgent.sdkCoreBinaryStageRoot=${missing.absolutePath}",
                    "-PcodexAgent.candidateCommit=${"a".repeat(40)}",
                    "-PcodexAgent.candidateTree=${"c".repeat(40)}",
                    "--console=plain",
                    "--stacktrace",
                )
                .buildAndFail()
            assertFalse(phaseRoot.exists(), "Stale SDK package output survived an upstream failure")
        } finally {
            phaseRoot.deleteRecursively()
            temporary.deleteRecursively()
        }
    }

    private companion object {
        val repositoryRoot = File("../..").canonicalFile
    }
}
