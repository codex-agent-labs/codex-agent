import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class NativeWrapperProductPhaseArtifactGraphTest {
    private val desktop = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val sdk = File("src/main/kotlin/codexagent.native-wrapper-sdk.gradle.kts").readText()
    private val contract = File("src/main/kotlin/codexagent.contract-product.gradle.kts").readText()
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
        assertTrue("dependsOn(snapshotImportedNativeWrapperRuntimeStages)" in seam)
        assertFalse(".orElse(" in seam, "Imported native-wrapper Runtime stages must not fall back locally")
        listOf(
            "macos-arm64" to "MacosArm64",
            "macos-x64" to "MacosX64",
            "linux-arm64" to "LinuxArm64",
            "linux-x64" to "LinuxX64",
            "windows-x64" to "WindowsX64",
        ).forEach { (component, title) ->
            assertTrue("(\"$component\" to \"package\")" in seam, component)
            assertTrue("(\"$component\" to \"validation\")" in seam, component)
            for (phase in listOf("Package", "Validation")) {
                assertTrue(
                    "verifyImportedNativeWrapper${title}Runtime${phase}OutputManifest" in seam,
                    "$component/$phase",
                )
            }
        }
        assertEquals(1, Regex("tasks\\.register<VerifyImportedProductOutputManifestTask>").findAll(seam).count())
        assertEquals(10, Regex("to \"verifyImportedNativeWrapper").findAll(seam).count())
        assertTrue("nativeWrapperRuntimeManifestTaskNames.map" in seam)
        listOf(
            "product.set(\"runtime\")",
            "phase.set(productPhase)",
            "productVersion.set(nativeWrapperRuntimeVersion)",
            "stageNativeWrapperCAbiSdks",
            "dependsOn(nativeWrapperRuntimeManifestVerifiers)",
        ).forEach { contract -> assertTrue(contract in seam, contract) }
        assertTrue("runtimeProductVersion.set(nativeWrapperRuntimeVersion)" in seam)
        assertTrue("nativeWrapperRuntimeVersion.map(::runtimeCompatibilityVersion)" in seam)
        val privateSnapshot = nativeWrapperTasks.substringAfter("fun stage() {")
            .substringBefore("private fun nativeWrapperSdkInput")
        val snapshot = privateSnapshot.indexOf("snapshotWithCanonicalProducer(")
        val verification = privateSnapshot.indexOf("verifyRuntimeStageManifests(")
        val consumption = privateSnapshot.indexOf("stageCrossLanguageNativeWrapperSdks(")
        assertTrue(snapshot >= 0 && snapshot < verification && verification < consumption)
        assertTrue("verify-output-manifest" in nativeWrapperTasks)
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
            "\"package-source\" to \"outputs/package-source\"",
            "\"runtime-sdks\" to \"outputs/runtime-sdks\"",
        ).forEach { value -> assertTrue(value in seam, value) }
    }

    @Test
    fun `ciProductPhase maps every native wrapper package component exactly`() {
        val mapping = contract.substringAfter("val requestedProduct =")
            .substringBefore("val contractBundleDirectory =")
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
            listOf(
                "MacosArm64", "MacosX64", "LinuxArm64", "LinuxX64", "WindowsX64",
            ).forEach { title ->
                for (phase in listOf("Package", "Validation")) {
                    val verifier =
                        ":codex-agent-sdk:verifyImportedNativeWrapper${title}Runtime${phase}OutputManifest"
                    assertTrue(verifier in paths, verifier)
                }
            }
            listOf("Python", "CSharp", "Rust", "Cpp", "Dart").forEach { title ->
                assertTrue(":codex-agent-sdk:prepare${title}NativeWrapperPackageSource" in paths)
                assertTrue(":codex-agent-sdk:stage${title}NativeWrapperSdkPackagePhase" in paths)
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
                forbiddenTaskNames.any { it.matches(name) }
            }
            assertTrue(forbidden.isEmpty(), "Runtime producer tasks are reachable: $forbidden")
            assertTrue(paths.none { it.startsWith(":codex-agent-core:") }, paths.toString())
            assertTrue(paths.none { it.startsWith(":codex-agent-runtime-desktop:") }, paths.toString())
        } finally {
            importedStages.deleteRecursively()
        }
    }

    private companion object {
        val repositoryRoot = File("../..").canonicalFile
    }
}
