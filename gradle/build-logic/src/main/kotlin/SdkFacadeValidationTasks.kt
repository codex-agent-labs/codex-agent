import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import javax.inject.Inject
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.DefaultTask
import org.gradle.api.Project
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFile
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.register
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

private fun requireFacadeRequestIdentity(request: File, target: String, sdk: String, runtime: String, contract: String) {
    requireApplePackagePathWithoutSymlinks(request, "facade caller request")
    val value = request.readReleaseObject()
    check(value["target"] == JsonPrimitive(target) && value["sdkVersion"] == JsonPrimitive(sdk) &&
        value["runtimeVersion"] == JsonPrimitive(runtime) && value["contractVersion"] == JsonPrimitive(contract)) {
        "Facade caller request differs from the elected target or versions"
    }
}

/** Full imported-input checks remain in the existing Python gate, not this task registration. */
@DisableCachingByDefault(because = "Authenticates fresh caller-owned facade inputs")
abstract class PrepareSdkFacadeValidationInputsTask @Inject constructor(private val processes: ExecOperations) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val requestFile: RegularFileProperty
    @get:Input abstract val targetName: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val runtimeVersion: Property<String>
    @get:Input abstract val contractVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    init { pythonExecutable.convention("python3"); outputs.upToDateWhen { false } }

    @get:Internal val commandLine: List<String> get() = listOf(
        pythonExecutable.get(), "-m", "ci.products.sdk_facade_inputs", "prepare",
        "--request", requestFile.get().asFile.absolutePath,
        "--destination", outputDirectory.get().asFile.absolutePath,
    )

    @TaskAction fun prepare() {
        requireFacadeRequestIdentity(requestFile.get().asFile, targetName.get(), sdkVersion.get(), runtimeVersion.get(), contractVersion.get())
        val arguments = commandLine
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(arguments)
        }
    }
}

/** Replays the same caller request and raw consumer evidence before deterministic projection. */
@DisableCachingByDefault(because = "Replays original facade inputs and execution before projection")
abstract class WriteSdkFacadeValidationContentTask @Inject constructor(private val processes: ExecOperations) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val requestFile: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val inputsDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val evidenceDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val gradleWrapper: RegularFileProperty
    @get:Optional @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val javaExecutable: RegularFileProperty
    @get:Internal abstract val consumerDirectory: DirectoryProperty
    @get:Input abstract val targetName: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val runtimeVersion: Property<String>
    @get:Input abstract val contractVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:OutputFile abstract val outputFile: RegularFileProperty

    init { pythonExecutable.convention("python3"); outputs.upToDateWhen { false } }

    @get:Internal val commandLine: List<String> get() = listOf(
        pythonExecutable.get(), "-m", "ci.products.sdk_facade_inputs", "content",
        "--request", requestFile.get().asFile.absolutePath,
        "--inputs", inputsDirectory.get().asFile.absolutePath,
        "--evidence", evidenceDirectory.get().asFile.absolutePath,
        "--gradle-wrapper", gradleWrapper.get().asFile.absolutePath,
        "--consumer-directory", consumerDirectory.get().asFile.absolutePath,
        "--output", outputFile.get().asFile.absolutePath,
    ) + javaExecutable.orNull?.let { listOf("--java-executable", it.asFile.absolutePath) }.orEmpty()

    @TaskAction fun writeContent() {
        requireFacadeRequestIdentity(requestFile.get().asFile, targetName.get(), sdkVersion.get(), runtimeVersion.get(), contractVersion.get())
        val arguments = commandLine
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(arguments)
        }
    }
}

/** Adapts imported Maven filenames only; all dependency semantics use the existing full verifier. */
@DisableCachingByDefault(because = "Verifies freshly authenticated imported facade publication metadata")
abstract class VerifyImportedSdkFacadePublicationMetadataTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val packageStage: DirectoryProperty
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val runtimeVersion: Property<String>
    @get:Input abstract val contractVersion: Property<String>
    @get:Input abstract val kotlinVersion: Property<String>
    @get:Input abstract val forbiddenPath: Property<String>
    @get:OutputFile abstract val resultFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun verify() {
        val source = packageStage.get().asFile
        val report = resultFile.get().asFile
        requireApplePackagePathWithoutSymlinks(source, "facade package")
        requireApplePackagePathWithoutSymlinks(report, "facade metadata report")
        requireOriginalAppleSnapshotDisjoint(report, listOf(source))
        check(!Files.exists(report.toPath(), LinkOption.NOFOLLOW_LINKS)) { "Facade metadata report must be fresh" }
        val result = verifyImportedSdkFacadePublicationMetadata(source, contractVersion.get(), runtimeVersion.get(),
            sdkVersion.get(), kotlinVersion.get(), forbiddenPath.get())
        requireApplePackagePathWithoutSymlinks(report, "facade metadata report")
        check(!Files.exists(report.toPath(), LinkOption.NOFOLLOW_LINKS)) { "Facade metadata report must be fresh" }
        report.atomicWriteJson(result)
    }
}

/** Imported-only graph. The caller supplies authenticated original receipts/policy in request. */
internal fun Project.registerSdkFacadeValidationTasks(
    request: Provider<RegularFile>,
    sdkVersion: Provider<String>,
    runtimeVersion: Provider<String>,
    contractVersion: Provider<String>,
    kotlinVersion: Provider<String>,
    candidateTree: Provider<String>,
    androidSdkDirectory: Provider<String>,
    validationTarget: String,
): TaskProvider<WriteProductOutputManifestTask> {
    check(validationTarget in sdkFacadeConsumerCompileTasks && request.isPresent) {
        "Imported facade validation requires an exact target and caller request"
    }
    check(listOf(sdkVersion.orNull, runtimeVersion.orNull, contractVersion.orNull).all { it != null && PRODUCT_SEMVER.matches(it) } &&
        !kotlinVersion.orNull.isNullOrBlank()) {
        "Imported facade validation requires exact product and Kotlin versions"
    }
    val tree = candidateTree.orNull
    check(tree != null && tree.matches(Regex("[0-9a-f]{40}|[0-9a-f]{64}"))) {
        "Imported facade validation requires an exact candidate tree"
    }
    check(androidSdkDirectory.isPresent && androidSdkDirectory.get().none { it == '\r' || it == '\n' }) {
        "Imported facade validation requires a valid Android SDK location"
    }
    val work = layout.buildDirectory.dir("imported-sdk-facade-validation/$tree/$validationTarget")
    val stage = layout.buildDirectory.dir("product-stage/sdk/sdk-core/validation/$validationTarget")
    val imported = work.map { it.dir("inputs") }
    val consumerRoot = work.map { it.dir("consumer") }
    val evidence = work.map { it.dir("execution") }
    val windowsHost = System.getProperty("os.name").startsWith("Windows")
    val wrapper = rootProject.layout.projectDirectory.file(if (windowsHost) "gradlew.bat" else "gradlew")
    val javaLauncher = if (windowsHost) rootProject.layout.file(providers.systemProperty("java.home").map {
        File(it, "bin/java.exe")
    }) else null
    val sdk = sdkVersion
    val runtime = runtimeVersion
    val contract = contractVersion
    val kotlin = kotlinVersion
    val android = androidSdkDirectory
    val prepare = tasks.register<PrepareSdkFacadeValidationInputsTask>("prepareSdkCoreValidationInputs") {
        requestFile.set(request)
        targetName.set(validationTarget)
        this.sdkVersion.set(sdk)
        this.runtimeVersion.set(runtime)
        this.contractVersion.set(contract)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        outputDirectory.set(imported)
    }
    val publicationMetadata = tasks.register<VerifyImportedSdkFacadePublicationMetadataTask>("verifySdkCoreValidationPublicationMetadata") {
        dependsOn(prepare)
        packageStage.set(imported.map { it.dir("package-stage") })
        this.sdkVersion.set(sdk)
        this.runtimeVersion.set(runtime)
        this.contractVersion.set(contract)
        this.kotlinVersion.set(kotlin)
        forbiddenPath.set(rootProject.projectDir.absolutePath)
        resultFile.set(work.map { it.file("publication-metadata.json") })
    }
    val consumer = tasks.register<VerifyStagedKmpConsumerTask>("verifySdkCoreValidationConsumer") {
        dependsOn(publicationMetadata)
        repositoryDirectory.set(imported.map { it.dir("maven-repository") })
        templateDirectory.set(rootProject.layout.projectDirectory.dir("gradle/release/sdk-facade-consumer-template"))
        mavenInventory.set(imported.map { it.file("maven-inventory.json") })
        gradleWrapper.set(wrapper)
        javaLauncher?.let { javaExecutable.set(it) }
        this.sdkVersion.set(sdk)
        this.runtimeVersion.set(runtime)
        this.androidSdkDirectory.set(android)
        targetName.set(validationTarget)
        buildTasks.set(listOf(sdkFacadeConsumerCompileTasks.getValue(validationTarget)))
        consumerDirectory.set(consumerRoot)
        resultFile.set(work.map { it.file("report.json") })
        executionCaptureDirectory.set(evidence)
    }
    val content = tasks.register<WriteSdkFacadeValidationContentTask>("writeSdkCoreValidationContent") {
        dependsOn(consumer)
        requestFile.set(request)
        targetName.set(validationTarget)
        this.sdkVersion.set(sdk)
        this.runtimeVersion.set(runtime)
        this.contractVersion.set(contract)
        inputsDirectory.set(imported)
        evidenceDirectory.set(evidence)
        gradleWrapper.set(wrapper)
        javaLauncher?.let { javaExecutable.set(it) }
        consumerDirectory.set(consumerRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        outputFile.set(stage.map { it.file("outputs/validation/facade-validation.json") })
    }
    return tasks.register<WriteProductOutputManifestTask>("writeSdkCoreValidationOutputManifest") {
        dependsOn(content)
        product.set("sdk"); component.set("sdk-core"); phase.set("validation"); target.set(validationTarget)
        productVersion.set(sdkVersion)
        outputRoots.set(mapOf("sdk-facade-validation-content" to "outputs/validation"))
        expectedOutputPaths.set(listOf("outputs/validation/facade-validation.json"))
        outputsDirectory.set(stage.map { it.dir("outputs") })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(stage)
        manifestFile.set(stage.map { it.file("output-manifest.json") })
    }
}
