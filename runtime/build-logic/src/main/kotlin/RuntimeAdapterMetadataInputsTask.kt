import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.attribute.BasicFileAttributes
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

abstract class ValidateRuntimeAdapterMetadataInputsTask : DefaultTask() {
    @get:Input
    abstract val component: Property<String>

    @get:Internal
    abstract val validationHandoff: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val projection: RegularFileProperty

    @get:Internal
    abstract val mavenRepository: DirectoryProperty

    @TaskAction
    fun verify() {
        val adapter = component.get()
        check(adapter in setOf("jvm", "node-js", "node-wasm")) {
            "Unsupported Runtime adapter metadata component: $adapter"
        }
        val handoff = validationHandoff.get().asFile.toPath().toAbsolutePath().normalize()
        val projectionFile = projection.get().asFile.toPath().toAbsolutePath().normalize()
        check(projectionFile.parent == handoff && projectionFile.fileName.toString() == "projection.json") {
            "Runtime adapter projection must be the validation handoff's projection.json"
        }
        requireRegularRuntimeProductDirectory(handoff, "Runtime validation handoff")
        requireRegularRuntimeProductTree(
            mavenRepository.get().asFile.toPath().toAbsolutePath().normalize(),
            "Runtime Maven repository",
        )
        verifyRuntimeAdapterProjection(adapter, projectionFile.toFile())
    }
}

internal fun requireRegularRuntimeProductDirectory(root: java.nio.file.Path, label: String) {
    val attributes = Files.readAttributes(
        root,
        BasicFileAttributes::class.java,
        LinkOption.NOFOLLOW_LINKS,
    )
    check(attributes.isDirectory && !attributes.isSymbolicLink && !attributes.isOther) {
        "$label must be a real directory"
    }
}

internal fun requireRegularRuntimeProductTree(root: java.nio.file.Path, label: String) {
    val normalized = root.toAbsolutePath().normalize()
    generateSequence(normalized) { it.parent }.forEach { path ->
        val attributes = Files.readAttributes(
            path,
            BasicFileAttributes::class.java,
            LinkOption.NOFOLLOW_LINKS,
        )
        check(attributes.isDirectory && !attributes.isSymbolicLink && !attributes.isOther) {
            "$label has an unsafe parent: $path"
        }
    }
    var files = 0
    Files.walk(normalized).use { entries ->
        entries.forEach { entry ->
            val attributes = Files.readAttributes(
                entry,
                BasicFileAttributes::class.java,
                LinkOption.NOFOLLOW_LINKS,
            )
            check(!attributes.isSymbolicLink && !attributes.isOther &&
                (attributes.isDirectory || attributes.isRegularFile)) {
                "$label contains an unsafe entry: $entry"
            }
            if (attributes.isRegularFile) {
                check(attributes.size() > 0L) { "$label contains an empty file: $entry" }
                files += 1
            }
        }
    }
    check(files > 0) { "$label must contain at least one regular file" }
}
