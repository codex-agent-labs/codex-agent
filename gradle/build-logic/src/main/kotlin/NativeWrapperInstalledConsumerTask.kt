import java.io.File
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
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

private val nativeWrapperInstalledConsumerLanguages =
    setOf("python", "csharp", "rust", "cpp", "dart")
private val nativeWrapperInstalledConsumerClassifiers =
    setOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")

/**
 * Runs one matching-host installed consumer and retains its raw local evidence.
 * The caller must authenticate the imported package receipt/source before scheduling this task;
 * this task does not mint a product-phase manifest, receipt, or parity claim.
 */
@DisableCachingByDefault(because = "Installed consumers must execute on the current host and toolchain")
abstract class NativeWrapperInstalledConsumerTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val language: Property<String>
    @get:Input abstract val expectedClassifier: Property<String>
    @get:Input abstract val offlineMode: Property<Boolean>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packagesDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stagedSdkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkVersionFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val consumerScript: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val consumerSources: ConfigurableFileCollection
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init {
        offlineMode.convention(project.gradle.startParameter.isOffline)
        pythonExecutable.convention("python3")
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun consume() {
        val output = outputDirectory.get().asFile
        output.deleteRecursively()
        try {
            val languageValue = language.get()
            check(languageValue in nativeWrapperInstalledConsumerLanguages) {
                "Unsupported native wrapper language: $languageValue"
            }
            val classifier = expectedClassifier.get()
            check(classifier in nativeWrapperInstalledConsumerClassifiers) {
                "Unsupported native wrapper target: $classifier"
            }
            val command = mutableListOf(
                pythonExecutable.get(), consumerScript.get().asFile.absolutePath, "consume-language",
                "--repository", repositoryRoot.get().asFile.absolutePath,
                "--packages", packagesDirectory.get().asFile.absolutePath,
                "--sdks", stagedSdkDirectory.get().asFile.absolutePath,
                "--output", output.absolutePath,
                "--sdk-version-file", sdkVersionFile.get().asFile.absolutePath,
                "--language", languageValue,
                "--expected-classifier", classifier,
            )
            if (offlineMode.get()) command += "--offline"
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(command)
            }
            requireExactNativeWrapperInstalledConsumerEvidence(output, languageValue, classifier)
        } catch (error: Exception) {
            output.deleteRecursively()
            throw error
        }
    }
}

internal fun requireExactNativeWrapperInstalledConsumerEvidence(
    output: File, language: String, expectedClassifier: String? = null,
) {
    check(language in nativeWrapperInstalledConsumerLanguages) {
        "Unsupported native wrapper language: $language"
    }
    val files = verifiedRegularFiles(output)
    val prefix = "evidence/$language/"
    val toolchainPath = "${prefix}toolchain.tsv"
    val hostPaths = files.keys.filter { path ->
        path.startsWith(prefix) && path.endsWith(".tsv") && path != toolchainPath
    }
    check(files.keys == hostPaths.toSet() + toolchainPath && hostPaths.size == 1) {
        "Installed native wrapper evidence inventory is not exact"
    }
    val classifier = hostPaths.single().removePrefix(prefix).removeSuffix(".tsv")
    check(classifier in nativeWrapperInstalledConsumerClassifiers) {
        "Installed native wrapper evidence classifier is invalid: $classifier"
    }
    check(expectedClassifier == null || classifier == expectedClassifier) {
        "Installed native wrapper evidence does not match requested target: $expectedClassifier"
    }
    val hostLines = exactNativeWrapperEvidenceLines(files.getValue(hostPaths.single()))
    check(hostLines.size == 2 && hostLines.first() ==
        "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus") {
        "Installed native wrapper host evidence schema is invalid"
    }
    val result = hostLines.last().split('\t')
    check(result.size == 6 && result[0] == classifier &&
        result[1].startsWith("$language-package/") &&
        result[2].matches(Regex("[0-9a-f]{64}")) &&
        result[3].matches(Regex("[0-9a-f]{64}")) &&
        result[4] == "$language-installed-host-lifecycle" && result[5] == "passed") {
        "Installed native wrapper host evidence result is invalid"
    }
    val toolchainLines = exactNativeWrapperEvidenceLines(files.getValue(toolchainPath))
    val tools = toolchainLines.drop(1)
    val toolNames = tools.map { it.substringBefore('\t') }
    val expectedTools = when (language) {
        "python" -> setOf("python")
        "csharp" -> setOf("dotnet")
        "rust" -> setOf("cargo", "rustc") +
            if (classifier == "windows-x64") emptySet() else setOf("rustFixtureCompiler")
        "cpp" -> setOf("cmake", "cppCompiler")
        "dart" -> setOf("dart")
        else -> error("Unsupported native wrapper language: $language")
    }
    check(toolchainLines.firstOrNull() == "tool\tversion" && tools.isNotEmpty() &&
        tools == tools.sorted() && toolNames.toSet() == expectedTools && toolNames.size == expectedTools.size &&
        tools.all { it.split('\t').let { columns ->
            columns.size == 2 && columns.all { column -> column.isNotBlank() }
        } }) {
        "Installed native wrapper toolchain evidence is invalid"
    }
}

private fun exactNativeWrapperEvidenceLines(file: File): List<String> {
    val contents = file.readText()
    check(contents.isNotEmpty() && contents.endsWith("\n") && '\r' !in contents) {
        "Installed native wrapper evidence is not canonical LF text"
    }
    return contents.removeSuffix("\n").split('\n')
}
