import java.io.File
import java.nio.file.Files
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

@DisableCachingByDefault(because = "Imported Runtime stages must be snapshotted and reverified on every invocation")
abstract class SnapshotImportedNativeWrapperRuntimeStagesTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val runtimeStageRoot: DirectoryProperty
    @get:Internal abstract val outputDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init { pythonExecutable.convention("python3") }
    @TaskAction
    fun snapshot() {
        val output = outputDirectory.get().asFile
        snapshotWithCanonicalProducer(
            processes, pythonExecutable.get(), repositoryRoot.get().asFile,
            runtimeStageRoot.get().asFile, output,
        )
        requireExactRuntimeStageTree(output)
    }
}

@DisableCachingByDefault(because = "Signed imported product inputs must be reauthenticated on every invocation")
abstract class GenerateNativeWrapperSdkCompatibilityTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val requestFile: RegularFileProperty
    @get:Internal abstract val outputFile: RegularFileProperty
    @get:OutputDirectory abstract val resourceDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init { pythonExecutable.convention("python3") }

    @TaskAction
    fun generate() {
        val resourceRoot = resourceDirectory.get().asFile
        val output = outputFile.get().asFile
        resourceRoot.deleteRecursively()
        output.parentFile.mkdirs()
        try {
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(
                    pythonExecutable.get(), "-m", "ci.products.sdk_compatibility",
                    "--request", requestFile.get().asFile.absolutePath,
                    "--output", output.absolutePath,
                )
            }
            check(regularCAbiFile(output)) { "SDK compatibility producer emitted no regular output" }
            check(resourceRoot.walkTopDown().filter(File::isFile).toList() == listOf(output)) {
                "SDK compatibility resource inventory is not exact"
            }
        } catch (error: Exception) {
            resourceRoot.deleteRecursively()
            throw error
        }
    }
}

private fun requireExactRuntimeStageTree(destinationRoot: File) {
    val expected = setOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")
    check(destinationRoot.list()?.toSet() == expected) { "Imported Runtime component inventory mismatch" }
    expected.forEach { component ->
        check(destinationRoot.resolve(component).list()?.toSet() == setOf("package", "validation")) {
            "Imported Runtime phase inventory mismatch: $component"
        }
        listOf("package", "validation").forEach { phase ->
            check(verifiedRegularFiles(destinationRoot.resolve("$component/$phase")).isNotEmpty()) {
                "Imported Runtime stage is empty: $component/$phase"
            }
        }
    }
}

@DisableCachingByDefault(because = "Original Runtime receipts and external attestations must be authenticated on every invocation")
abstract class StageCrossLanguageNativeWrapperSdksTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val runtimeProductVersion: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val compatibilityRequest: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val runtimeStageRoot: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkRuntimeRootPublicKey: RegularFileProperty
    @get:Internal abstract val outputDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init { pythonExecutable.convention("python3") }

    @TaskAction
    fun stage() {
        val sourceRoot = runtimeStageRoot.get().asFile
        val temporary = Files.createTempDirectory(
            outputDirectory.get().asFile.absoluteFile.parentFile.also(File::mkdirs).toPath(),
            ".native-wrapper-input-",
        ).toFile()
        try {
            val stageRoot = temporary.resolve("staged")
            snapshotWithCanonicalProducer(
                processes, pythonExecutable.get(), repositoryRoot.get().asFile, sourceRoot, stageRoot,
            )
            requireExactRuntimeStageTree(stageRoot)
            verifyRuntimeStageManifests(
                processes,
                pythonExecutable.get(),
                repositoryRoot.get().asFile,
                stageRoot,
                compatibilityRequest.get().asFile,
                sdkCompatibility.get().asFile,
                temporary.resolve("sdk-compatibility.json"),
            )
            stageCrossLanguageNativeWrapperSdks(nativeWrapperSdkInput(stageRoot), outputDirectory.get().asFile)
        } finally {
            temporary.deleteRecursively()
        }
    }

    private fun nativeWrapperSdkInput(stageRoot: File) = CrossLanguageNativeWrapperSdkInput(
        libraryVersion.get(), runtimeProductVersion.get(), sdkVersion.get(),
        producerCommit.get(), producerTree.get(), sdkCompatibility.get().asFile,
        sdkRuntimeRootPublicKey.get().asFile,
        crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
            val component = crossLanguageCAbiTargetSpecs.getValue(target).classifier.removePrefix("c-abi-")
            stageRoot.resolve(
                "$component/package/outputs/c-abi/${crossLanguageCAbiArchiveFileName(libraryVersion.get(), target)}",
            )
        },
        crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
            val component = crossLanguageCAbiTargetSpecs.getValue(target).classifier.removePrefix("c-abi-")
            stageRoot.resolve(
                "$component/validation/outputs/c-abi/${crossLanguageCAbiPackageEvidenceFileName(target)}",
            )
        },
        crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
            val component = crossLanguageCAbiTargetSpecs.getValue(target).classifier.removePrefix("c-abi-")
            val referenceRoot = stageRoot.resolve("$component/validation/outputs/c-abi-reference")
            CrossLanguageNativeWrapperSdkReferenceInput(
                referenceRoot.resolve("include/codex_agent.h"),
                referenceRoot.resolve("legal/LICENSE"),
                referenceRoot.resolve("legal/THIRD_PARTY_NOTICES.md"),
                referenceRoot.resolve("export-policy/" + when (target) {
                    "macosArm64", "macosX64" -> "macos.exports"
                    "linuxArm64", "linuxX64" -> "linux.map"
                    "mingwX64" -> "windows.def"
                    else -> error("Unsupported native wrapper C ABI target: $target")
                }),
                referenceRoot.resolve("consumer").listFiles()?.toList().orEmpty(),
            )
        },
    )
}

private fun verifyRuntimeStageManifests(
    processes: ExecOperations,
    pythonExecutable: String,
    repositoryRoot: File,
    stageRoot: File,
    compatibilityRequest: File,
    expectedCompatibility: File,
    verifiedCompatibility: File,
) {
    processes.exec {
        workingDir(repositoryRoot)
        environment("PYTHONDONTWRITEBYTECODE", "1")
        commandLine(
            pythonExecutable, "-m", "ci.products.sdk_compatibility",
            "--request", compatibilityRequest.absolutePath,
            "--output", verifiedCompatibility.absolutePath,
            "--runtime-stage-root", stageRoot.absolutePath,
        )
    }
    check(regularCAbiFile(verifiedCompatibility) && regularCAbiFile(expectedCompatibility) &&
        verifiedCompatibility.readBytes().contentEquals(expectedCompatibility.readBytes())) {
        "Authenticated Runtime stages disagree with the selected SDK compatibility declaration"
    }
}

@CacheableTask
abstract class MaterializeCrossLanguageNativeWrapperPackageAssetsTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stagedSdkDirectory: ConfigurableFileCollection
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init { pythonExecutable.convention("python3") }

    @TaskAction
    fun materialize() {
        val roots = stagedSdkDirectory.files
        check(roots.size == 1) { "Native wrapper package assets require one staged SDK root" }
        val source = roots.single()
        val temporary = Files.createTempDirectory(
            outputDirectory.get().asFile.absoluteFile.parentFile.also(File::mkdirs).toPath(),
            ".native-wrapper-sdk-",
        ).toFile()
        try {
            val trusted = temporary.resolve("staged")
            snapshotWithCanonicalProducer(
                processes, pythonExecutable.get(), repositoryRoot.get().asFile, source, trusted,
            )
            materializeCrossLanguageNativeWrapperPackageAssets(trusted, outputDirectory.get().asFile)
        } finally {
            temporary.deleteRecursively()
        }
    }
}

@DisableCachingByDefault(because = "Language package tools and their verified profiles own reuse")
abstract class PackageNativeWrapperSdkTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val language: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourcesDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sdkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkVersionFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val packageScript: RegularFileProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    @TaskAction
    fun packageSdk() {
        val output = outputDirectory.get().asFile
        output.deleteRecursively()
        try {
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(
                    "python3", packageScript.get().asFile.absolutePath, "package",
                    "--sources", sourcesDirectory.get().asFile.parentFile.absolutePath,
                    "--sdks", sdkDirectory.get().asFile.absolutePath,
                    "--output", output.absolutePath,
                    "--sdk-version-file", sdkVersionFile.get().asFile.absolutePath,
                    "--language", language.get(),
                )
            }
        } catch (error: Exception) {
            output.deleteRecursively()
            throw error
        }
    }
}
