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

/** Content-only projection; the outer caller still authenticates the complete original execution. */
@DisableCachingByDefault(because = "Projects fresh Apple validation evidence without granting admission")
abstract class WriteAppleValidationContentTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageStage: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalApi: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverage: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val swiftReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val objectiveCReceipt: RegularFileProperty
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
        pythonExecutable.get(), "-m", "ci.products.sdk_apple_validation_content",
        "--target", target.get(), "--sdk-version", sdkVersion.get(),
        "--package-stage", packageStage.get().asFile.absolutePath,
        "--sdk-compatibility", sdkCompatibility.get().asFile.absolutePath,
        "--canonical-api", canonicalApi.get().asFile.absolutePath,
        "--canonical-coverage", canonicalCoverage.get().asFile.absolutePath,
        "--swift-receipt", swiftReceipt.get().asFile.absolutePath,
        "--objective-c-receipt", objectiveCReceipt.get().asFile.absolutePath,
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
