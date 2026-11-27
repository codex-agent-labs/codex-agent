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
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

/**
 * Invokes the canonical Python metadata projection over caller-authenticated package and validation content.
 * This task does not authenticate receipts or grant product admission.
 */
@DisableCachingByDefault(because = "Projects fresh iOS SDK metadata without granting admission")
abstract class WriteIosSdkMetadataContentTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageStage: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val deviceValidation: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val simulatorValidation: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:OutputFile abstract val outputFile: RegularFileProperty

    init {
        pythonExecutable.convention("python3")
        outputs.upToDateWhen { false }
    }

    @get:Internal
    val commandLine: List<String> get() = listOf(
        pythonExecutable.get(), "-m", "ci.products.sdk_apple_metadata",
        "--sdk-version", sdkVersion.get(),
        "--package-stage", packageStage.get().asFile.absolutePath,
        "--device-validation", deviceValidation.get().asFile.absolutePath,
        "--simulator-validation", simulatorValidation.get().asFile.absolutePath,
        "--output", outputFile.get().asFile.absolutePath,
    )

    @TaskAction
    fun writeContent() {
        val arguments = commandLine
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(arguments)
        }
    }
}
