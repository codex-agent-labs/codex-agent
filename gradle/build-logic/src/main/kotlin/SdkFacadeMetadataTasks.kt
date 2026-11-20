import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import javax.inject.Inject
import kotlinx.serialization.json.JsonObject
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
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.register
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

/** Enumerate Gradle inputs only; the Python writer owns canonical and semantic validation. */
internal fun sdkFacadeMetadataInputFiles(request: File): List<File> {
    requireApplePackagePathWithoutSymlinks(request, "Core metadata caller request")
    val value = request.readReleaseObject()
    check(value.keys == setOf("sdkVersion", "packageStage", "packageReceipt", "contractDigest", "componentDigests", "validations")) {
        "Core metadata caller request has unexpected fields"
    }
    val validations = value["validations"] as? JsonObject ?: error("Core metadata validations must be an object")
    check(validations.keys == sdkFacadeConsumerCompileTasks.keys) { "Core metadata requires exactly eleven validation targets" }
    fun input(record: JsonObject, field: String): File {
        val text = record[field] as? JsonPrimitive ?: error("Core metadata input path must be a string")
        check(text.isString && text.content.isNotBlank()) { "Core metadata input path must be a nonempty string" }
        val file = File(text.content)
        requireApplePackagePathWithoutSymlinks(file, "Core metadata caller input")
        check(file.isAbsolute && file.toPath().normalize().toFile() == file && file.canonicalFile == file) {
            "Core metadata input path must be absolute, normalized and non-symbolic"
        }
        return file
    }
    return listOf(input(value, "packageStage"), input(value, "packageReceipt")) +
        sdkFacadeConsumerCompileTasks.keys.sorted().flatMap { target ->
            val record = validations[target] as? JsonObject ?: error("Core metadata validation record must be an object")
            check(record.keys == setOf("stageRoot", "phaseReceipt")) { "Core metadata validation record has unexpected fields" }
            listOf(input(record, "stageRoot"), input(record, "phaseReceipt"))
        }
}

/** Content projection only; the caller must authenticate all eleven original validations. */
@DisableCachingByDefault(because = "Projects fresh caller-authenticated Core metadata without granting admission")
abstract class WriteSdkFacadeMetadataContentTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val requestFile: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val callerInputs: ConfigurableFileCollection
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:Internal abstract val stageRoot: DirectoryProperty
    @get:OutputFile abstract val outputFile: RegularFileProperty

    init {
        pythonExecutable.convention("python3")
        outputs.upToDateWhen { false }
    }

    @get:Internal
    val commandLine: List<String> get() = listOf(
        pythonExecutable.get(), "-m", "ci.products.sdk_platform_metadata",
        "--request", requestFile.get().asFile.absolutePath,
        "--output", outputFile.get().asFile.absolutePath,
    )

    @TaskAction
    fun writeContent() {
        val stage = stageRoot.get().asFile
        requireApplePackagePathWithoutSymlinks(stage, "Core metadata stage")
        // Gradle creates OutputFile parents before task actions; only that empty skeleton is permitted.
        if (Files.exists(stage.toPath(), LinkOption.NOFOLLOW_LINKS)) {
            val allowed = setOf(stage.toPath(), stage.resolve("outputs").toPath(), stage.resolve("outputs/evidence").toPath())
            check(Files.walk(stage.toPath()).use { paths ->
                paths.allMatch { it in allowed && Files.isDirectory(it, LinkOption.NOFOLLOW_LINKS) }
            }) { "Core metadata stage must be fresh" }
        }
        check(outputFile.get().asFile == stage.resolve("outputs/evidence/facade-metadata.json")) {
            "Core metadata requires its exact singleton content path"
        }
        val request = requestFile.get().asFile
        requireApplePackagePathWithoutSymlinks(request, "Core metadata caller request")
        check(request.readReleaseObject()["sdkVersion"] == JsonPrimitive(sdkVersion.get())) {
            "Core metadata request differs from the elected SDK version"
        }
        val arguments = commandLine
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(arguments)
        }
    }
}

/** Imported-only join. Referenced inputs are supplied explicitly, never discovered from producer tasks. */
internal fun Project.registerSdkFacadeMetadataTasks(
    request: Provider<RegularFile>,
    sdkVersion: Provider<String>,
    referencedInputs: ConfigurableFileCollection,
): TaskProvider<WriteProductOutputManifestTask> {
    check(request.isPresent && sdkVersion.orNull?.let { PRODUCT_SEMVER.matches(it) } == true) {
        "Core metadata requires a caller request and exact SDK version"
    }
    val stage = rootProject.layout.buildDirectory.dir("product-stage/sdk/sdk-core/metadata/common")
    val sdk = sdkVersion
    val content = tasks.register<WriteSdkFacadeMetadataContentTask>("writeSdkCoreMetadataContent") {
        requestFile.set(request)
        this.sdkVersion.set(sdk)
        callerInputs.from(referencedInputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(stage)
        outputFile.set(stage.map { it.file("outputs/evidence/facade-metadata.json") })
    }
    return tasks.register<WriteProductOutputManifestTask>("writeSdkCoreMetadataOutputManifest") {
        dependsOn(content)
        product.set("sdk"); component.set("sdk-core"); phase.set("metadata"); target.set("common")
        productVersion.set(sdk)
        outputRoots.set(mapOf("sdk-facade-metadata-content" to "outputs/evidence"))
        expectedOutputPaths.set(listOf("outputs/evidence/facade-metadata.json"))
        outputsDirectory.set(stage.map { it.dir("outputs") })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(stage)
        manifestFile.set(stage.map { it.file("output-manifest.json") })
    }
}
