import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

/** External raw evidence only. The dependency authenticates inputs; no phase/host receipt is minted here. */
@DisableCachingByDefault(because = "Capability suites must execute on the actual consumer host")
abstract class NativeWrapperCapabilityEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val language: Property<String>
    @get:Input abstract val expectedClassifier: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:Input @get:Optional abstract val dotnetExecutable: Property<String>
    @get:Input @get:Optional abstract val dartExecutable: Property<String>
    @get:InputFile @get:Optional @get:PathSensitive(PathSensitivity.NONE)
    abstract val dartPackageConfig: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val capabilityInputsDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val installedConsumerEvidence: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val producerScript: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val claims: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val producerSources: ConfigurableFileCollection
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init {
        pythonExecutable.convention("python3")
        ownedBuildDirectory.convention(project.layout.buildDirectory)
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun produce() {
        val output = outputDirectory.get().asFile
        val destination = output.toPath().toAbsolutePath().normalize()
        val owned = ownedBuildDirectory.get().asFile.toPath().toAbsolutePath().normalize()
        generateSequence(output.toPath().toAbsolutePath()) { it.parent }.forEach { path ->
            check(!Files.isSymbolicLink(path) && (!Files.exists(path, LinkOption.NOFOLLOW_LINKS) ||
                Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))) { "Unsafe capability output: $path" }
        }
        check(destination != owned && destination.startsWith(owned)) { "Unowned capability output: $output" }
        val handoff = capabilityInputsDirectory.get().asFile
        val host = installedConsumerEvidence.get().asFile
        val inputs = listOf(handoff, host, producerScript.get().asFile, claims.get().asFile) +
            producerSources.files + listOfNotNull(dartPackageConfig.orNull?.asFile)
        inputs.forEach { file ->
            val path = file.canonicalFile.toPath()
            check(!destination.startsWith(path) && !path.startsWith(destination)) {
                "Capability output overlaps an input: $file"
            }
        }
        output.deleteRecursively()
        try {
            val binding = nativeWrapperBindings.single { it.id == language.get() }
            val classifier = expectedClassifier.get()
            requireExactNativeWrapperInstalledConsumerEvidence(host, binding.id, classifier)
            val before = capabilityInputInventory(inputs)
            val command = nativeWrapperCapabilityCommand(
                pythonExecutable.get(), producerScript.get().asFile, binding.id, classifier,
                handoff, output, dotnetExecutable.orNull, dartExecutable.orNull, dartPackageConfig.orNull?.asFile,
            )
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(command)
            }
            // Keep the complete raw directory (including language auxiliaries); the existing
            // matcher alone owns compiler/reference/executed-test/scenario semantics.
            check(verifiedRegularFiles(output).isNotEmpty()) { "Capability producer output is empty" }
            verifyCrossLanguageNativeWrapperCapabilityEvidence(
                binding, handoff.resolve("contract/canonical-api.json"),
                handoff.resolve("contract/canonical-coverage.json"),
                handoff.resolve("bootstrap/bootstrap-evidence.json"), claims.get().asFile,
                output.resolve("compiler-evidence.tsv"), output.resolve("test-program"),
                output.resolve("executed-tests.tsv"),
            )
            check(before == capabilityInputInventory(inputs)) { "Capability inputs changed during validation" }
        } catch (error: Exception) {
            output.deleteRecursively()
            throw error
        }
    }
}

private fun capabilityInputInventory(inputs: List<File>): Map<String, String> = buildMap {
    inputs.forEach { input ->
        if (input.isDirectory) {
            verifiedRegularFiles(input).values.forEach { file -> put(file.absolutePath, file.releaseDigest()) }
        } else {
            check(input.isFile && !Files.isSymbolicLink(input.toPath())) { "Missing capability input: $input" }
            put(input.absolutePath, input.releaseDigest())
        }
    }
}

internal fun nativeWrapperCapabilityCommand(
    python: String, script: File, language: String, classifier: String, handoff: File, output: File,
    dotnet: String? = null, dart: String? = null, dartPackageConfig: File? = null,
): List<String> {
    check(nativeWrapperBindings.any { it.id == language }) { "Unsupported capability language: $language" }
    val library = when (classifier) {
        "macos-arm64", "macos-x64" -> "lib/libcodex_agent.dylib"
        "linux-arm64", "linux-x64" -> "lib/libcodex_agent.so"
        "windows-x64" -> "bin/codex_agent.dll"
        else -> error("Unsupported capability target: $classifier")
    }
    val sdk = handoff.resolve("sdks/$classifier")
    return buildList {
        addAll(listOf(python, script.absolutePath,
            "--canonical-api", handoff.resolve("contract/canonical-api.json").absolutePath,
            "--c-abi-bootstrap", handoff.resolve("bootstrap/bootstrap-evidence.json").absolutePath,
            "--sdk-compatibility", handoff.resolve("sdks/sdk-compatibility.json").absolutePath,
            "--c-sdk-root", sdk.absolutePath, "--native-library", sdk.resolve(library).absolutePath,
            "--output", output.absolutePath))
        if (language == "cpp") addAll(listOf("--classifier", classifier))
        if (language == "csharp") {
            check(!dotnet.isNullOrBlank() && File(dotnet).isAbsolute) { "C# requires an explicit absolute dotnet executable" }
            addAll(listOf("--dotnet", dotnet))
        }
        if (language == "dart") {
            if (dart != null) addAll(listOf("--dart-executable", dart))
            if (dartPackageConfig != null) addAll(listOf("--package-config", dartPackageConfig.absolutePath))
        }
    }
}
