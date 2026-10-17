import java.io.File
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

/** Lossless transport only; phase admission must replay the retained original evidence. */
@DisableCachingByDefault(because = "Original execution evidence must be captured for each selected validation")
abstract class ArchiveAppleValidationEvidenceTask : DefaultTask() {
    @get:Input abstract val sourceLayout: MapProperty<String, String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val evidenceInputs: ConfigurableFileCollection
    @get:OutputFile abstract val archiveFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun archive() {
        val sources = sourceLayout.get().mapValues { (_, path) -> File(path) }
        check(sources.values.map { it.canonicalFile }.toSet() ==
            evidenceInputs.files.map { it.canonicalFile }.toSet()) {
            "Apple validation archive inputs differ from the declared layout"
        }
        writeAppleValidationEvidenceArchive(sources, archiveFile.get().asFile)
    }
}
