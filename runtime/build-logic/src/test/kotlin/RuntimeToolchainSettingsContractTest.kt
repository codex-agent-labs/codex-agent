import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class RuntimeToolchainSettingsContractTest {
    private val settings = File("../settings.gradle.kts").readText()
    private val plugin = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()

    @Test
    fun `native binary observes its actual producer before every compiler path`() {
        val observer = plugin.substringAfter("val verifyRuntimeProducerToolchain =")
            .substringBefore("private val cAbiTargetSpecs =")
        listOf(
            "requestedRuntimeTarget in runtimeBinaryFlags",
            "requestedRuntimePhase == null || requestedRuntimePhase == \"binary\"",
            "System.getProperty(\"os.name\")",
            "System.getProperty(\"os.arch\")",
            "tasks.register<Exec>(\"verifyRuntimeProducerToolchain\")",
            "outputs.upToDateWhen { false }",
            "\"python3\", \"-m\", \"ci.products.toolchain\", \"verify-producer\"",
            "\"--repository-root\"",
            "\"--repository-revision\"",
            "\"--profile-id\"",
            "\"--producer-role\"",
            "\"--target\"",
            "\"--gradle-user-home\"",
            "\"--binary-plan\"",
            "\"--verified-contract-manifest\"",
            "\"--expected-runtime-version\"",
            "\"--expected-flags-digest\"",
            "\"--output\"",
            "put(\"RUNNER_OS\", runnerOs)",
            "put(\"RUNNER_ARCH\", runnerArch)",
        ).forEach { contract -> assertTrue(contract in observer, contract) }
        assertFalse("System.getenv(\"RUNNER_OS\")" in observer)
        assertFalse("System.getenv(\"RUNNER_ARCH\")" in observer)
        val binaryAdmission = plugin.substringAfter("private val requestedRuntimePhase =")
            .substringBefore("val verifyRuntimeProducerToolchain =")
        listOf(
            "gradle.startParameter.excludedTaskNames.isEmpty()",
            "Native Runtime binary producer verification rejects excluded tasks",
        ).forEach { contract -> assertTrue(contract in binaryAdmission, contract) }

        val abiGenerator = plugin.substringAfter("generateRuntimeAbiSource.configure {")
            .substringBefore("private val cAbiTargetSpecs =")
        val supervisor = plugin.substringAfter("val compileDesktopProcessSupervisor =")
            .substringBefore("val desktopPackageTasks =")
        val nativeTargets = plugin.substringAfter("desktopTargets.forEach { target ->")
            .substringBefore("sourceSets.getByName(\"commonMain\")")
        assertTrue("verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in abiGenerator)
        assertTrue("verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in supervisor)
        assertTrue(
            "linkTaskProvider.configure {\n                verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in
                nativeTargets,
        )
        assertTrue(
            nativeTargets.lineSequence().count {
                "verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in it
            } == 3,
            "Native link and both C interop compiler paths must depend on producer verification",
        )
        assertTrue("sourceSets.getByName(\"nativeMain\").kotlin.srcDir(generateRuntimeAbiSource)" in plugin)

        val nativeCommonization = plugin.substringAfter("tasks.matching {\n    it.name in setOf(")
            .substringBefore("@OptIn(ExperimentalWasmDsl::class)")
        listOf(
            "commonizeCInterop",
            "compileNativeMainKotlinMetadata",
            "compileAppleMainKotlinMetadata",
            "compileMacosMainKotlinMetadata",
            "compileLinuxMainKotlinMetadata",
        ).forEach { taskName -> assertTrue("\"$taskName\"" in nativeCommonization, taskName) }
        assertTrue(
            "verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in nativeCommonization,
            "Native commonization and metadata compiler paths must depend on producer verification",
        )
    }

    @Test
    fun `Linux ARM supervisor role is confined to the explicit supervisor-only invocation`() {
        val observer = plugin.substringAfter("val verifyRuntimeProducerToolchain =")
            .substringBefore("private val cAbiTargetSpecs =")
        listOf(
            "requestedRuntimePhase == null",
            "gradle.startParameter.taskNames.size == 1",
            "gradle.startParameter.taskNames.single().substringAfterLast(':')",
            "\"compileDesktopProcessSupervisor\"",
            "requestedRuntimeTarget == \"linux-arm64\" && supervisorOnly -> \"supervisor-builder\"",
            "requestedRuntimeTarget == \"linux-arm64\" -> \"cross-builder\"",
            "else -> \"builder\"",
        ).forEach { contract -> assertTrue(contract in observer, contract) }
    }

    @Test
    fun `every native phase rejects task exclusions before its compiler guard can be removed`() {
        val guard = plugin.substringBefore("    verifyRuntimeBinaryFlagsAgainstPlan(")
            .substringAfterLast("if (requestedRuntimeTarget in runtimeBinaryFlags) {")
            .substringBefore("\n}")
        assertTrue("gradle.startParameter.excludedTaskNames.isEmpty()" in guard)
        assertFalse("requestedRuntimePhase" in guard)

        val root = createTempDirectory("runtime-excluded-observer").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText(
                """
                val requestedRuntimeTarget = "macos-arm64"
                val runtimeBinaryFlags = setOf("macos-arm64")
                if (requestedRuntimeTarget in runtimeBinaryFlags) {
                $guard
                }
                rootProject.name = "excluded-runtime-observer"
                """.trimIndent() + "\n",
            )
            listOf("binary", "package", "validation", "metadata").forEach { phase ->
                val result = GradleRunner.create()
                    .withProjectDir(root)
                    .withArguments(
                        "help", "-PcodexAgent.phase=$phase", "-x", "verifyRuntimeProducerToolchain",
                        "--offline", "--stacktrace",
                    )
                    .buildAndFail()
                assertTrue(
                    "Native Runtime binary producer verification rejects excluded tasks" in result.output,
                    result.output,
                )
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `artifact-only compiler guard rejects direct production without evaluating toolchain inputs`() {
        val rejection = plugin.substringAfter("} else if (requestedRuntimeTarget in runtimeBinaryFlags) {")
            .substringBefore("} else {\n    null\n}")
        assertTrue("tasks.register(\"verifyRuntimeProducerToolchain\")" in rejection)
        listOf("providers.", "System.", "Exec", "commandLine", "runtimeBinaryPlan").forEach {
            assertFalse(it in rejection, "Artifact-only rejection must not evaluate $it")
        }
        val supervisorEdge = plugin.substringAfter("val compileDesktopProcessSupervisor =")
            .substringBefore("val desktopPackageTasks =")
            .lineSequence().single { "verifyRuntimeProducerToolchain?.let { dependsOn(it) }" in it }
        val root = createTempDirectory("runtime-artifact-only-compiler-guard").toFile().canonicalFile
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"artifact-only-guard\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                val verifyRuntimeProducerToolchain = $rejection
                tasks.register("compileDesktopProcessSupervisor") {
                    $supervisorEdge
                    doLast { error("COMPILER_MUST_NOT_RUN") }
                }
                tasks.register("artifactOnly")
                tasks.register("validationCConsumer")
                """.trimIndent() + "\n",
            )
            val admitted = GradleRunner.create().withProjectDir(root)
                .withArguments("artifactOnly", "validationCConsumer", "--offline", "--stacktrace")
                .build()
            assertFalse(":verifyRuntimeProducerToolchain" in admitted.output, admitted.output)
            val rejected = GradleRunner.create().withProjectDir(root)
                .withArguments("compileDesktopProcessSupervisor", "--offline", "--stacktrace")
                .buildAndFail()
            assertTrue("Native Runtime product compilation requires the binary phase" in rejected.output)
            assertFalse("COMPILER_MUST_NOT_RUN" in rejected.output, rejected.output)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `observer consumes the same admitted plan and remains outside product payload`() {
        listOf(
            "codexAgent.runtimeBinaryFlagsDigest",
            "codexAgent.runtimeBinaryPlan",
            "codexAgent.repositoryRevision",
            "ci.products.runtime_identity",
            "--verified-contract-manifest",
        ).forEach { contract -> assertTrue(contract in settings, contract) }
        val observer = plugin.substringAfter("val verifyRuntimeProducerToolchain =")
            .substringBefore("private val cAbiTargetSpecs =")
        assertTrue("verifiedContractManifestFile" in observer)
        assertTrue("toolchain-verification/" in observer)

        val nativeBinaryStage = plugin.substringAfter(
            "val stage = tasks.register<Sync>(\"stage\${title}RuntimeBinaryOutputs\")",
        )
            .substringBefore("val writeBinaryManifest =")
        assertFalse("toolchain-verification" in nativeBinaryStage)
        assertFalse("verifyRuntimeProducerToolchain" in nativeBinaryStage)
    }

    @Test
    fun `native artifact-only phases reject absent predecessors before project configuration`() {
        val boundary = "val nativePredecessorProperty =" + settings
            .substringAfter("    val nativePredecessorProperty =")
            .substringBefore(
                "    if (values.getValue(\"codexAgent.target\") in nativeRuntimeTargets &&",
            )
        val pluginGuard = plugin.substringAfter("private val requestedRuntimePhase =")
            .substringBefore(
                "if (requestedRuntimeTarget in runtimeBinaryFlags && " +
                    "(requestedRuntimePhase == null || requestedRuntimePhase == \"binary\"))",
            )
        listOf(
            "\"package\" -> require(importedRuntimeBinaryStage.isPresent)",
            "\"validation\" -> require(importedRuntimePackageStage.isPresent)",
        ).forEach { contract -> assertTrue(contract in pluginGuard, contract) }
        assertFalse("\"metadata\" -> require(importedRuntimePackageStage.isPresent)" in pluginGuard)
        assertFalse("\"validation\", \"metadata\"" in pluginGuard)
        assertTrue(
            plugin.indexOf("private val requestedRuntimePhase =") <
                plugin.indexOf("extensions.configure<KotlinMultiplatformExtension>"),
        )

        mapOf(
            "package" to "codexAgent.runtimeBinaryStage",
            "validation" to "codexAgent.runtimePackageStage",
            "metadata" to "codexAgent.runtimeVariantIdentity",
        ).forEach { (phase, predecessor) ->
            val root = createTempDirectory("runtime-$phase-predecessor").toFile().canonicalFile
            try {
                val configured = root.resolve("project-configured")
                root.resolve("settings.gradle.kts").writeText(
                    """
                    val values = mapOf("codexAgent.target" to "macos-arm64")
                    val nativeRuntimeTargets = setOf("macos-arm64")
                    val commandLineProperties = gradle.startParameter.projectProperties
                    val requestedPhase = commandLineProperties["codexAgent.phase"]
                    val requestedProduct = "runtime"
                    val requestedComponent = "macos-arm64"
                    val requestedTarget = "macos-arm64"
                    val bindingValidation = false
                    val adapterHostValidation = false
                    val semver = Regex("[0-9]+\\.[0-9]+\\.[0-9]+")
                    fun absoluteNormalizedPath(name: String) = file(commandLineProperties.getValue(name)).toPath()
                    $boundary
                    java.io.File(${quote(configured.absolutePath)}).writeText("configured")
                    rootProject.name = "missing-native-predecessor"
                    """.trimIndent() + "\n",
                )
                val environment = System.getenv().toMutableMap().apply {
                    remove("ORG_GRADLE_PROJECT_$predecessor")
                }
                val result = GradleRunner.create()
                    .withProjectDir(root)
                    .withEnvironment(environment)
                    .withArguments(
                        "help", "-PcodexAgent.phase=$phase", "--offline", "--no-configuration-cache",
                        "--stacktrace",
                    )
                    .buildAndFail()
                assertTrue(
                    "Missing mandatory explicit -P project property: $predecessor" in result.output,
                    result.output,
                )
                assertFalse(configured.exists(), "$phase configured the project without $predecessor")
            } finally {
                root.deleteRecursively()
            }
        }
    }

    private fun quote(value: String) = "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
}
