import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.Task
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.testkit.runner.GradleRunner

/** Provider/graph checks and existing publication parser only, not native compilation or original admission. */
class SdkFacadeValidationTasksTest {
    private val tree = "a".repeat(40)
    private val expectedTasks = linkedMapOf(
        "android" to "compileAndroidMain", "jvm" to "compileKotlinJvm",
        "ios-arm64" to "compileKotlinIosArm64", "ios-simulator-arm64" to "compileKotlinIosSimulatorArm64",
        "macos-arm64" to "compileKotlinMacosArm64", "macos-x64" to "compileKotlinMacosX64",
        "linux-arm64" to "compileKotlinLinuxArm64", "linux-x64" to "compileKotlinLinuxX64",
        "windows-x64" to "compileKotlinMingwX64", "node-js" to "compileKotlinJs", "node-wasm" to "compileKotlinWasmJs",
    )

    @Test
    fun `all eleven target graphs use only authenticated imports and fixed captured consumer`() {
        assertEquals(expectedTasks, sdkFacadeConsumerCompileTasks)
        expectedTasks.forEach { (target, taskName) -> fixture { project ->
            val before = project.tasks.names.toSet()
            val manifest = register(project, target)
            val prepare = project.tasks.named("prepareSdkCoreValidationInputs", PrepareSdkFacadeValidationInputsTask::class.java).get()
            val metadata = project.tasks.named("verifySdkCoreValidationPublicationMetadata", VerifyImportedSdkFacadePublicationMetadataTask::class.java).get()
            val consumer = project.tasks.named("verifySdkCoreValidationConsumer", VerifyStagedKmpConsumerTask::class.java).get()
            val content = project.tasks.named("writeSdkCoreValidationContent", WriteSdkFacadeValidationContentTask::class.java).get()
            val work = project.layout.buildDirectory.dir("imported-sdk-facade-validation/$tree/$target").get().asFile
            val stage = project.layout.buildDirectory.dir("product-stage/sdk/sdk-core/validation/$target").get().asFile
            val request = project.file("caller-request.json")
            assertEquals(emptySet(), prepare.taskDependencies.getDependencies(prepare))
            assertEquals(setOf(prepare), metadata.taskDependencies.getDependencies(metadata))
            assertEquals(setOf(metadata), consumer.taskDependencies.getDependencies(consumer))
            assertEquals(setOf(consumer), content.taskDependencies.getDependencies(content))
            assertEquals(setOf(content), manifest.taskDependencies.getDependencies(manifest))
            assertEquals(setOf(prepare, metadata, consumer, content, manifest), closure(manifest))
            assertEquals(closure(manifest).map { it.name }.toSet(), project.tasks.names.toSet() - before)
            assertEquals(listOf("python3", "-m", "ci.products.sdk_facade_inputs", "prepare", "--request", request.path,
                "--destination", work.resolve("inputs").path), prepare.commandLine)
            assertEquals(work.resolve("inputs/package-stage"), metadata.packageStage.get().asFile)
            assertEquals(listOf("0.8.1", "0.8.0", "1.2.3", "2.3.10"), listOf(metadata.sdkVersion.get(),
                metadata.runtimeVersion.get(), metadata.contractVersion.get(), metadata.kotlinVersion.get()))
            assertEquals(work.resolve("publication-metadata.json"), metadata.resultFile.get().asFile)
            assertEquals(work.resolve("inputs/maven-repository"), consumer.repositoryDirectory.get().asFile)
            assertEquals(work.resolve("inputs/maven-inventory.json"), consumer.mavenInventory.get().asFile)
            assertEquals(project.file("gradle/release/sdk-facade-consumer-template"), consumer.templateDirectory.get().asFile)
            assertEquals(project.file("gradlew"), consumer.gradleWrapper.get().asFile)
            assertEquals(target, consumer.targetName.get())
            assertEquals(listOf(taskName), consumer.buildTasks.get())
            assertEquals("/sdk", consumer.androidSdkDirectory.get())
            assertEquals(work.resolve("consumer"), consumer.consumerDirectory.get().asFile)
            assertEquals(work.resolve("execution"), consumer.executionCaptureDirectory.get().asFile)
            assertEquals(work.resolve("report.json"), consumer.resultFile.get().asFile)
            assertEquals(listOf("python3", "-m", "ci.products.sdk_facade_inputs", "content", "--request", request.path,
                "--inputs", work.resolve("inputs").path, "--evidence", work.resolve("execution").path,
                "--gradle-wrapper", project.file("gradlew").path, "--consumer-directory", work.resolve("consumer").path,
                "--output", stage.resolve("outputs/validation/facade-validation.json").path), content.commandLine)
            assertEquals(listOf("sdk", "sdk-core", "validation", target, "0.8.1"), listOf(manifest.product.get(),
                manifest.component.get(), manifest.phase.get(), manifest.target.get(), manifest.productVersion.get()))
            assertEquals(mapOf("sdk-facade-validation-content" to "outputs/validation"), manifest.outputRoots.get())
            assertEquals(listOf("outputs/validation/facade-validation.json"), manifest.expectedOutputPaths.get())
            assertEquals(stage, manifest.stageRoot.get().asFile)
            assertEquals(stage.resolve("output-manifest.json"), manifest.manifestFile.get().asFile)
            assertFalse(work.toPath().startsWith(stage.toPath()))
            assertFalse(work.exists())
            assertFalse(stage.exists())
        } }
    }

    @Test
    fun `missing or invalid controls reject before any tasks are registered`() {
        for (invalid in listOf("request", "target", "sdk", "runtime", "contract", "kotlin", "tree", "android")) fixture { project ->
            val request = project.objects.fileProperty()
            if (invalid != "request") request.set(project.file("caller-request.json"))
            fun value(name: String, valid: String) = project.providers.provider { if (invalid == name) "" else valid }
            val before = project.tasks.names.toSet()
            assertFailsWith<IllegalStateException>(invalid) {
                project.registerSdkFacadeValidationTasks(request, value("sdk", "0.8.1"), value("runtime", "0.8.0"),
                    value("contract", "1.2.3"), value("kotlin", "2.3.10"), value("tree", tree),
                    project.providers.provider { if (invalid == "android") "invalid\npath" else "/sdk" },
                    if (invalid == "target") "common" else "jvm")
            }
            assertEquals(before, project.tasks.names.toSet())
        }
    }

    @Test
    fun `request target and all elected versions must match before invoking Python`() = fixture { project ->
        register(project, "jvm")
        val prepare = project.tasks.named("prepareSdkCoreValidationInputs", PrepareSdkFacadeValidationInputsTask::class.java).get()
        val content = project.tasks.named("writeSdkCoreValidationContent", WriteSdkFacadeValidationContentTask::class.java).get()
        for (field in listOf("target", "sdkVersion", "runtimeVersion", "contractVersion")) {
            val values = linkedMapOf("target" to "jvm", "sdkVersion" to "0.8.1", "runtimeVersion" to "0.8.0", "contractVersion" to "1.2.3")
            values[field] = "wrong"
            project.file("caller-request.json").writeText(values.entries.joinToString(",", "{", "}") { "\"${it.key}\":\"${it.value}\"" })
            assertTrue(assertFailsWith<IllegalStateException> { prepare.prepare() }.message.orEmpty().contains("caller request differs"))
            assertTrue(assertFailsWith<IllegalStateException> { content.writeContent() }.message.orEmpty().contains("caller request differs"))
        }
    }

    @Test
    fun `imported Maven adapter rejects incorrect actual POM dependency using existing verifier`() = fixture { project ->
        register(project, "jvm")
        val task = project.tasks.named("verifySdkCoreValidationPublicationMetadata", VerifyImportedSdkFacadePublicationMetadataTask::class.java).get()
        val source = task.packageStage.get().asFile
        val group = CodexAgentBuild.MAVEN_GROUP
        for (artifact in facadePublicationSpecs.map { it.artifact } + "codex-agent-bom") {
            val path = source.resolve("outputs/maven/${group.replace('.', '/')}/$artifact/0.8.1").apply { mkdirs() }
            path.resolve("$artifact-0.8.1.pom").writeText("""
                <project><modelVersion>4.0.0</modelVersion><groupId>$group</groupId>
                <artifactId>$artifact</artifactId><version>0.8.1</version><dependencies>
                <dependency><groupId>$group</groupId><artifactId>codex-agent-core</artifactId>
                <version>9.9.9</version><scope>runtime</scope></dependency>
                </dependencies></project>
            """.trimIndent())
            path.resolve("$artifact-0.8.1.module").writeText("{}")
        }
        val before = verifiedRegularFiles(source).mapValues { it.value.releaseDigest() }
        val failure = assertFailsWith<IllegalStateException> { task.verify() }
        assertTrue("dependencies" in failure.message.orEmpty(), failure.message)
        assertEquals(before, verifiedRegularFiles(source).mapValues { it.value.releaseDigest() })
        assertFalse(task.resultFile.get().asFile.exists())
    }

    @Test
    fun `real product dispatch dry run selects imported facade graph without publications`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val scratch = createTempDirectory("facade-dispatch-").toFile().canonicalFile
        try {
            val request = scratch.resolve("request.json").apply { writeText("{}\n") }
            val result = GradleRunner.create().withProjectDir(repository).withArguments(
                "ciProductPhase", "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
                "-PcodexAgent.product=sdk", "-PcodexAgent.component=sdk-core", "-PcodexAgent.phase=validation",
                "-PcodexAgent.target=jvm", "-PcodexAgent.sdkVersion=0.8.1", "-PcodexAgent.candidateTree=$tree",
                "-PcodexAgent.sdkFacadeValidationRequest=${request.path}",
            ).build()
            val paths = result.output.lineSequence().filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                .map { it.removeSuffix(" SKIPPED") }.toList()
            assertEquals(listOf(":prepareSdkCoreValidationInputs", ":verifySdkCoreValidationPublicationMetadata",
                ":verifySdkCoreValidationConsumer", ":writeSdkCoreValidationContent",
                ":writeSdkCoreValidationOutputManifest", ":ciProductPhase"), paths, result.output)
            assertFalse(scratch.resolve("maven-repository").exists())
        } finally { scratch.deleteRecursively() }
    }

    private fun register(project: Project, target: String) = project.registerSdkFacadeValidationTasks(
        project.providers.provider { project.layout.projectDirectory.file("caller-request.json") },
        project.providers.provider { "0.8.1" }, project.providers.provider { "0.8.0" },
        project.providers.provider { "1.2.3" }, project.providers.provider { "2.3.10" },
        project.providers.provider { tree }, project.providers.provider { "/sdk" }, target,
    ).get()

    private fun closure(task: Task): Set<Task> = setOf(task) + task.taskDependencies.getDependencies(task).flatMap(::closure)

    private fun fixture(block: (Project) -> Unit) {
        val root = createTempDirectory("facade-validation-registration-").toFile().canonicalFile
        try { block(ProjectBuilder.builder().withProjectDir(root).build()) } finally { root.deleteRecursively() }
    }
}
