import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.BasicFileAttributes
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
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

    @get:Internal
    abstract val stageDirectory: DirectoryProperty

    @get:Internal
    abstract val ownedBuildDirectory: DirectoryProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    init {
        ownedBuildDirectory.convention(project.layout.buildDirectory)
        stageDirectory.convention(ownedBuildDirectory.dir(component.map { "product-stage/runtime/$it/metadata" }))
        outputDirectory.convention(stageDirectory.dir("outputs"))
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun verify() {
        check(outputDirectory.get().asFile == stageDirectory.get().dir("outputs").asFile) {
            "Runtime adapter metadata outputs must belong to its owned stage"
        }
        verifyRuntimeAdapterMetadataInputs(
            component.get(), validationHandoff.get().asFile.toPath(), projection.get().asFile.toPath(),
            mavenRepository.get().asFile.toPath(), stageDirectory.get().asFile.toPath(),
            ownedBuildDirectory.get().asFile.toPath(),
        )
    }
}

internal fun verifyRuntimeAdapterMetadataInputs(
    adapter: String, handoff: Path, projectionFile: Path, maven: Path, stage: Path, ownedBuild: Path,
    verifyProjection: (String, java.io.File) -> Unit = ::verifyRuntimeAdapterProjection,
) {
    check(adapter in setOf("jvm", "node-js", "node-wasm")) {
        "Unsupported Runtime adapter metadata component: $adapter"
    }
    listOf(handoff, projectionFile, maven, stage, ownedBuild).forEach { path ->
        check(path.isAbsolute && path.normalize() == path) { "Runtime adapter metadata path must be absolute and normalized: $path" }
        // Inspect raw ancestry before any deletion, including dangling links.
        generateSequence(path.parent) { it.parent }.forEach { parent ->
            check(!Files.isSymbolicLink(parent) && (!Files.exists(parent, LinkOption.NOFOLLOW_LINKS) ||
                Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS))) {
                "Runtime adapter metadata path has an unsafe parent: $parent"
            }
        }
    }
    check(stage == ownedBuild.resolve("product-stage/runtime/$adapter/metadata")) {
        "Runtime adapter metadata output must be its exact task-owned stage"
    }
    check(projectionFile.parent == handoff && projectionFile.fileName.toString() == "projection.json") {
        "Runtime adapter projection must be the validation handoff's projection.json"
    }
    listOf(handoff, projectionFile, maven).forEach { input ->
        check(!input.startsWith(stage) && !stage.startsWith(input)) {
            "Runtime adapter metadata output overlaps an original input: $input"
        }
    }
    requireRegularRuntimeProductDirectory(handoff, "Runtime validation handoff")
    requireRegularRuntimeProductDirectory(maven, "Runtime Maven repository")
    check(Files.isRegularFile(projectionFile, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(projectionFile)) {
        "Runtime adapter projection must be a regular original file"
    }
    // Safety is distinct from semantic validity: empty real input directories
    // may fail below after invalidation, but links/special entries never may.
    listOf(handoff, maven, stage).forEach { root ->
        if (Files.exists(root, LinkOption.NOFOLLOW_LINKS)) {
            requireRegularRuntimeProductDirectory(root, "Runtime adapter metadata tree")
            Files.walk(root).use { entries ->
                entries.forEach { entry ->
                    check(!Files.isSymbolicLink(entry) && (Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS) ||
                        Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS))) {
                        "Runtime adapter metadata tree contains an unsafe entry: $entry"
                    }
                }
            }
        }
    }
    // Case aliases may be lexically disjoint even on the same filesystem.
    // Resolve missing output suffixes from the nearest existing safe ancestor.
    var existingStage = stage
    val missingNames = mutableListOf<Path>()
    while (!Files.exists(existingStage, LinkOption.NOFOLLOW_LINKS)) {
        missingNames.add(existingStage.fileName)
        existingStage = checkNotNull(existingStage.parent)
    }
    val realStage = missingNames.asReversed().fold(existingStage.toRealPath()) { parent, name -> parent.resolve(name) }
    listOf(handoff, projectionFile, maven).forEach { input ->
        val realInput = input.toRealPath()
        fun containsSameFile(descendant: Path, ancestor: Path): Boolean =
            Files.exists(ancestor, LinkOption.NOFOLLOW_LINKS) &&
                generateSequence(descendant) { it.parent }.any { path ->
                    Files.exists(path, LinkOption.NOFOLLOW_LINKS) && Files.isSameFile(path, ancestor)
                }
        check(!realInput.startsWith(realStage) && !realStage.startsWith(realInput) &&
            !containsSameFile(realInput, realStage) && !containsSameFile(realStage, realInput)) {
            "Runtime adapter metadata output overlaps a resolved original input: $input"
        }
    }
    // Files.walk never follows links. Only this known, disjoint stage is owned.
    if (Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) {
        Files.walk(stage).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
    try {
        fun originals(): Map<String, Path> {
            requireRegularRuntimeProductTree(maven, "Runtime Maven repository")
            val files = sortedMapOf("evidence/$adapter.json" to projectionFile)
            Files.walk(maven).use { entries ->
                entries.filter { Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) }.forEach { path ->
                    files["maven/" + maven.relativize(path).joinToString("/")] = path
                }
            }
            return files
        }
        fun inventory(files: Map<String, Path>): Map<String, Pair<Long, String>> = files.mapValues { (_, path) ->
            generateSequence(path.parent) { it.parent }.forEach { parent ->
                check(!Files.isSymbolicLink(parent) && Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS)) {
                    "Runtime adapter metadata file has an unsafe parent: $parent"
                }
            }
            check(Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(path)) {
                "Runtime adapter metadata file became unsafe: $path"
            }
            Files.size(path) to Files.newInputStream(path, LinkOption.NOFOLLOW_LINKS).use { it.releaseDigest() }
        }
        val files = originals()
        val before = inventory(files)
        val output = stage.resolve("outputs")
        files.forEach { (relative, source) ->
            val destination = output.resolve(relative)
            Files.createDirectories(destination.parent)
            Files.newInputStream(source, LinkOption.NOFOLLOW_LINKS).use { Files.copy(it, destination) }
        }
        fun stagedInventory(): Map<String, Pair<Long, String>> {
            requireRegularRuntimeProductTree(output, "Staged Runtime adapter metadata")
            val staged = sortedMapOf<String, Path>()
            Files.walk(output).use { entries ->
                entries.filter { Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) }.forEach { path ->
                    staged[output.relativize(path).joinToString("/")] = path
                }
            }
            return inventory(staged)
        }
        check(stagedInventory() == before) { "Runtime adapter metadata inputs changed during capture" }
        verifyProjection(adapter, output.resolve("evidence/$adapter.json").toFile())
        check(inventory(originals()) == before) { "Original Runtime adapter metadata inputs changed during verification" }
        check(stagedInventory() == before) { "Staged Runtime adapter metadata changed during verification" }
    } catch (error: Exception) {
        if (Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) {
            Files.walk(stage).use { entries -> entries.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
        }
        throw error
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
