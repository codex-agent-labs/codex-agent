import java.nio.file.Files
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
import org.gradle.work.DisableCachingByDefault

/** Full imported five-host semantic verification, not a receipt or hosted trust capability.
 * The caller owns lifecycle invalidation; this task never deletes or overwrites an output.
 */
@DisableCachingByDefault(because = "The imported original evidence must pass the full verification gate")
abstract class NativeWrapperMetadataContentTask : DefaultTask() {
    @get:Input abstract val language: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageStageDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val packageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val compatibilityRequest: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val runtimeStageDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stagedSdkDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val validationStagesDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val validationReceiptsDirectory: DirectoryProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val verifierSources: ConfigurableFileCollection
    @get:OutputFile abstract val contentOutput: RegularFileProperty
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty

    init {
        ownedBuildDirectory.convention(project.layout.buildDirectory)
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun verifyAndWrite() {
        val output = contentOutput.get().asFile
        val destination = output.toPath().toAbsolutePath().normalize()
        val owned = ownedBuildDirectory.get().asFile.toPath().toAbsolutePath().normalize()
        check(destination != owned && destination.startsWith(owned)) { "Unowned native metadata output: $output" }
        val binding = nativeWrapperBindings.singleOrNull { it.id == language.get() }
            ?: error("Unsupported native metadata language")
        val verifiers = verifierSources.files
        check(verifiers.isNotEmpty()) { "Native metadata verifier sources are required" }
        verifiers.forEach { source ->
            generateSequence(source.toPath().toAbsolutePath()) { it.parent }.forEach { path ->
                check(!Files.isSymbolicLink(path)) { "Symbolic native metadata verifier source: $path" }
            }
            check(source.isFile) { "Missing native metadata verifier source: $source" }
            val path = source.toPath().toRealPath()
            check(!destination.startsWith(path) && !path.startsWith(destination)) {
                "Native metadata output overlaps a verifier source"
            }
        }
        // The existing gate owns exact five-target/input containment, full imported
        // authentication and matching, canonical joining, and fresh-file publication.
        writeImportedNativeWrapperMetadataContent(
            repositoryRoot.get().asFile, binding, packageStageDirectory.get().asFile,
            packageReceipt.get().asFile, compatibilityRequest.get().asFile,
            runtimeStageDirectory.get().asFile, stagedSdkDirectory.get().asFile,
            validationStagesDirectory.get().asFile, validationReceiptsDirectory.get().asFile, output, sdkVersion.get(),
        )
    }
}
