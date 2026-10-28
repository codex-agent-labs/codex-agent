import org.gradle.api.Action
import org.gradle.api.DefaultTask
import org.gradle.api.Project
import org.gradle.api.Task
import org.gradle.api.file.RegularFile
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.TaskProvider

internal const val IMPORTED_ANDROID_RELEASE_AAR_PROPERTY = "codexAgent.importedAndroidReleaseAar"

private val ANDROID_RELEASE_PUBLICATION_CONFIGURATIONS = listOf(
    "releaseVariantReleaseApiPublication",
    "releaseVariantReleaseRuntimePublication",
)

@CacheableTask
abstract class VerifyImportedAndroidReleaseAarTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val releaseAar: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val firebaseEvidence: RegularFileProperty
    @get:Input abstract val candidateCommit: Property<String>
    @get:Input abstract val pinnedRuntimeSha256: Property<String>
    @get:OutputFile abstract val verificationFile: RegularFileProperty

    @TaskAction
    fun verify() = verificationFile.get().asFile.atomicWriteJson(verifyImportedAndroidReleaseAar(
        releaseAar.get().asFile,
        firebaseEvidence.get().asFile,
        candidateCommit.get(),
        pinnedRuntimeSha256.get(),
    ))
}

internal fun Project.replaceAndroidReleaseComponentAar(
    importedAar: Provider<RegularFile>,
    validationTask: TaskProvider<out Task>,
) {
    ANDROID_RELEASE_PUBLICATION_CONFIGURATIONS.forEach { name ->
        val outgoing = configurations.getByName(name).outgoing
        val primaryAars = outgoing.artifacts.filter { it.extension == "aar" && it.classifier == null }
        check(primaryAars.size == 1) { "$name must contain exactly one primary Android AAR artifact" }
        primaryAars.forEach(outgoing.artifacts::remove)
        outgoing.artifact(importedAar, Action {
            type = "aar"
            extension = "aar"
            builtBy(validationTask)
        })
    }
}
