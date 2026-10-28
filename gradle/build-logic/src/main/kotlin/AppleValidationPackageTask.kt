import org.gradle.api.DefaultTask
import org.gradle.api.file.Directory
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

/** Extracts caller-authenticated package artifacts; it grants no receipt or provenance authority. */
@DisableCachingByDefault(because = "Validation must recheck each original Apple package invocation")
abstract class PrepareAppleValidationPackageInputsTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.NONE)
    abstract val productDirectory: DirectoryProperty
    @get:Input abstract val sdkVersion: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:OutputDirectory abstract val workDirectory: DirectoryProperty

    @get:Internal
    val packageDirectory: Provider<Directory> get() = workDirectory.dir("CodexAgentPackage")

    @get:Internal
    val xcframeworkDirectory: Provider<Directory> get() = workDirectory.dir("xcframework")

    init {
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun prepare() {
        prepareAppleValidationPackageInputs(
            productDirectory.get().asFile,
            sdkVersion.get(),
            sdkCompatibility.get().asFile,
            workDirectory.get().asFile,
        )
    }
}
