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
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

@DisableCachingByDefault(because = "Authenticated imported SDK binaries must be repackaged from exact inputs")
abstract class PackageSdkMavenArtifactsTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val binaryMavenRepository: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:Input abstract val component: Property<String>
    @get:Input abstract val groupId: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun packageArtifacts() {
        val output = outputDirectory.get().asFile
        output.deleteRecursively()
        try {
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(
                    "python3", "-m", "ci.products.sdk_maven",
                    "--source", binaryMavenRepository.get().asFile.absolutePath,
                    "--output", output.absolutePath,
                    "--compatibility", sdkCompatibility.get().asFile.absolutePath,
                    "--group-id", groupId.get(),
                    "--version", sdkVersion.get(),
                    "--component", component.get(),
                )
            }
        } catch (error: Exception) {
            output.deleteRecursively()
            throw error
        }
    }
}

@DisableCachingByDefault(because = "Verifies an already-built npm archive against its exact SDK declaration")
abstract class VerifyNpmSdkCompatibilityArchiveTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val archiveFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:Input abstract val sdkVersion: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:OutputFile abstract val reportFile: RegularFileProperty

    @TaskAction
    fun verifyArchive() {
        val report = reportFile.get().asFile
        report.delete()
        try {
            processes.exec {
                workingDir(repositoryRoot.get().asFile)
                environment("PYTHONDONTWRITEBYTECODE", "1")
                commandLine(
                    "python3", "-m", "ci.products.sdk_archive",
                    "--version", sdkVersion.get(),
                    "--archive", archiveFile.get().asFile.absolutePath,
                    "--compatibility", sdkCompatibility.get().asFile.absolutePath,
                    "--output", report.absolutePath,
                )
            }
        } catch (error: Exception) {
            report.delete()
            throw error
        }
    }
}
