import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Executes extracted production guards/cleanup only; not JVM product acceptance. */
class JvmImportedValidationContractTest {
    private val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()

    @Test
    fun `canonical JVM validation requires observed host and both original imported versions`() {
        val guard = source.substringAfter("val importedJvmPackageVersion =")
            .substringBefore("val jvmValidationDistribution =")
        check("if (canonicalJvmValidation)" in guard)
        val root = createTempDirectory("jvm-validation-guard").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"jvm-validation-guard\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                plugins { base }
                val jvmValidationComponent = providers.provider { "macos-arm64" }
                val importedRuntimePackageStage = providers.gradleProperty("codexAgent.runtimePackageStage").map(::file)
                val importedRuntimeNativePackageStage = providers.gradleProperty("codexAgent.runtimeNativePackageStage").map(::file)
                val importedJvmPackageVersion = $guard
                tasks.register("validationGuard")
                """.trimIndent(),
            )
            val properties = linkedMapOf(
                "product" to "runtime", "component" to "jvm", "phase" to "validation",
                "target" to "macos-arm64", "runtimeVersion" to "0.2.9",
                "runtimePackageStage" to "original-jvm-package", "runtimeNativePackageStage" to "original-native-package",
                "runtimePackageVersion" to "0.2.1", "runtimeNativePackageVersion" to "0.2.4",
            )
            fun runner(values: Map<String, String>) = GradleRunner.create().withProjectDir(root).withArguments(
                listOf("validationGuard", "--offline", "--configuration-cache", "--configuration-cache-problems=fail") +
                    values.map { (key, value) -> "-PcodexAgent.$key=$value" },
            )
            val positive = runner(properties).build()
            assertTrue(positive.tasks.none { "compile" in it.path.lowercase() || "link" in it.path.lowercase() })
            for (missing in listOf("runtimePackageStage", "runtimeNativePackageStage", "runtimePackageVersion",
                                   "runtimeNativePackageVersion")) {
                val failed = runner(properties - missing).buildAndFail()
                assertTrue("JVM Runtime validation requires" in failed.output, missing)
                assertTrue(failed.tasks.isEmpty())
            }
            val wrongHost = runner(properties + ("target" to "linux-x64")).buildAndFail()
            assertTrue("must match the observed desktop host" in wrongHost.output)
            assertTrue(wrongHost.tasks.isEmpty())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `JVM imported verifiers bind original versions and preserve existing evidence runner`() {
        val jvm = source.substringAfter("val jvmValidationTarget =")
            .substringBefore("pluginManager.withPlugin(\"maven-publish\")")
        val adapterVerifier = jvm.substringAfter("val verifyImportedJvmRuntimePackageOutputManifest =")
            .substringBefore("val verifyImportedJvmValidationNativePackageOutputManifest =")
        val nativeVerifier = jvm.substringAfter("val verifyImportedJvmValidationNativePackageOutputManifest =")
            .substringBefore("val jvmPackagePrerequisite:")
        assertTrue("importedJvmPackageVersion," in adapterVerifier)
        assertTrue("importedJvmNativePackageVersion," in nativeVerifier)
        assertFalse("runtimeProductVersion," in adapterVerifier || "runtimeProductVersion," in nativeVerifier)
        assertTrue("importedJvmNativePackageVersion.map(::runtimeCompatibilityVersion)" in jvm)
        assertTrue("jvmValidationNativePackageRoot.zip(jvmNativePackageCompatibilityVersion)" in jvm)
        assertTrue("dependsOn(invalidateJvmRuntimeValidationOutputs, jvmPackagePrerequisite, jvmNativePackagePrerequisite)" in jvm)
        assertTrue("compiledJvmTestRuntime.set(jvmValidationPackageRoot.map" in jvm)
        assertTrue("testTask.set(IMPORTED_JVM_RUNTIME_EVIDENCE_TASK)" in jvm)
        assertTrue("target.set(jvmValidationTarget)" in jvm)
        assertFalse("dependsOn(\"jvmTest\")" in jvm)
        assertTrue("snapshotImportedJvmRuntimePackage.configure { dependsOn(invalidateJvmRuntimeValidationOutputs) }" in jvm)
        assertTrue("snapshotImportedJvmNativeRuntimePackage.configure { dependsOn(invalidateJvmRuntimeValidationOutputs) }" in jvm)
    }

    @Test
    fun `host cleanup preserves sibling stages reports and snapshots on repeated invocation`() {
        val cleanup = "val jvmRuntimeValidationPhaseRoot =" + source
            .substringAfter("val jvmRuntimeValidationPhaseRoot =")
            .substringBefore("val verifyImportedJvmRuntimePackageOutputManifest =")
        val root = createTempDirectory("jvm-validation-cleanup").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"jvm-validation-cleanup\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                import org.gradle.api.tasks.Delete
                plugins { base }
                val jvmValidationComponent = providers.provider { "macos-arm64" }
                val importedJvmPackageSnapshotRoot = layout.buildDirectory.dir("imported-runtime-package-stages/tree/jvm/macos-arm64")
                val importedJvmNativePackageSnapshotRoot = layout.buildDirectory.dir("imported-runtime-native-package-stages/tree/jvm/macos-arm64")
                val snapshotImportedJvmRuntimePackage = tasks.register("adapterSnapshot")
                val snapshotImportedJvmNativeRuntimePackage = tasks.register("nativeSnapshot")
                $cleanup
                """.trimIndent(),
            )
            val prefixes = listOf(
                "product-stage/runtime/jvm/validation", "reports/imported-jvm-runtime-evidence",
                "imported-runtime-package-stages/tree/jvm", "imported-runtime-native-package-stages/tree/jvm",
            )
            repeat(2) {
                prefixes.forEach { prefix ->
                    for (host in listOf("macos-arm64", "linux-x64")) {
                        root.resolve("build/$prefix/$host/retained.txt").apply { parentFile.mkdirs(); writeText(host) }
                    }
                }
                GradleRunner.create().withProjectDir(root).withArguments(
                    "adapterSnapshot", "nativeSnapshot", "--offline", "--configuration-cache",
                    "--configuration-cache-problems=fail",
                ).build()
                prefixes.forEach { prefix ->
                    assertFalse(root.resolve("build/$prefix/macos-arm64").exists())
                    assertTrue(root.resolve("build/$prefix/linux-x64/retained.txt").isFile)
                }
            }
        } finally {
            root.deleteRecursively()
        }
    }
}
