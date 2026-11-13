import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

/** Product bytes only; original receipts and execution evidence remain external. */
@DisableCachingByDefault(because = "Revalidates original imported variant inputs before staging")
abstract class ImportedRuntimeVariantTask @Inject constructor(private val processes: ExecOperations) : DefaultTask() {
    @get:Input abstract val component: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val identity: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val binaryReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val validationReceipt: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val cAbiArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val appServerArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val validationEvidence: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val distributionManifest: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    init {
        ownedBuildDirectory.convention(project.layout.buildDirectory)
        outputs.upToDateWhen { false }
    }

    @TaskAction fun produce() {
        val repository = repositoryRoot.get().asFile
        produceImportedRuntimeVariant(component.get(), linkedMapOf(
            "identity" to identity.get().asFile,
            "binary-receipt" to binaryReceipt.get().asFile,
            "package-receipt" to packageReceipt.get().asFile,
            "validation-receipt" to validationReceipt.get().asFile,
            "c-abi-archive" to cAbiArchive.get().asFile,
            "app-server-archive" to appServerArchive.get().asFile,
            "validation-evidence" to validationEvidence.get().asFile,
            "distribution-manifest" to distributionManifest.get().asFile,
        ), outputDirectory.get().asFile, ownedBuildDirectory.get().asFile, producerSources.files) { command ->
            processes.exec {
                workingDir(repository)
                setEnvironment(environment.toMutableMap().apply {
                    remove("PYTHONHOME"); remove("PYTHONINSPECT"); remove("PYTHONSTARTUP")
                    put("PYTHONPATH", repository.absolutePath)
                    put("PYTHONDONTWRITEBYTECODE", "1"); put("PYTHONNOUSERSITE", "1")
                    put("PYTHONSAFEPATH", "1"); put("LC_ALL", "C"); put("LANG", "C")
                })
                commandLine(command)
            }.assertNormalExitValue()
        }
    }
}

private val importedVariantInputs = setOf(
    "identity", "binary-receipt", "package-receipt", "validation-receipt", "c-abi-archive",
    "app-server-archive", "validation-evidence", "distribution-manifest",
)

private fun requireImportedVariantParents(path: Path) {
    // Inspect the original path before normalization, including symbolic/../ paths.
    generateSequence(path.toAbsolutePath()) { it.parent }.forEach { ancestor ->
        check(!Files.isSymbolicLink(ancestor) && (!Files.exists(ancestor, LinkOption.NOFOLLOW_LINKS) ||
            Files.isDirectory(ancestor, LinkOption.NOFOLLOW_LINKS))) { "Unsafe Runtime variant directory: $ancestor" }
    }
}

private fun deleteImportedVariantWorkspace(path: Path) {
    if (!Files.exists(path, LinkOption.NOFOLLOW_LINKS)) return
    // Files.walk does not follow symbolic links, including failed-producer leftovers.
    Files.walk(path).use { entries ->
        entries.sorted(Comparator.reverseOrder()).forEach(Files::delete)
    }
}

internal fun produceImportedRuntimeVariant(
    component: String, inputs: Map<String, File>, output: File, ownedBuild: File,
    protectedSources: Collection<File> = emptyList(),
    run: (List<String>) -> Unit,
) {
    check(component in setOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")) {
        "Unsupported Runtime variant component: $component"
    }
    check(inputs.keys == importedVariantInputs) { "Runtime variant requires its exact original inputs" }
    requireImportedVariantParents(output.toPath())
    requireImportedVariantParents(ownedBuild.toPath())
    val destination = output.toPath().toAbsolutePath().normalize()
    val owned = ownedBuild.toPath().toAbsolutePath().normalize()
    val stage = destination.parent
    check(destination.fileName.toString() == "outputs" &&
        stage == owned.resolve("product-stage/runtime/$component/metadata")) {
        "Runtime variant output must be a task-owned stage outputs directory"
    }
    protectedSources.forEach { source ->
        val path = source.canonicalFile.toPath()
        check(!path.startsWith(stage) && !stage.startsWith(path)) {
            "Runtime variant output overlaps producer sources: $source"
        }
    }
    if (Files.exists(stage, LinkOption.NOFOLLOW_LINKS)) {
        Files.walk(stage).use { entries ->
            entries.forEach { entry ->
                check(!Files.isSymbolicLink(entry) && (Files.isDirectory(entry, LinkOption.NOFOLLOW_LINKS) ||
                    Files.isRegularFile(entry, LinkOption.NOFOLLOW_LINKS))) {
                    "Runtime variant prior stage contains an unsafe entry: $entry"
                }
            }
        }
    }
    inputs.values.forEach { input ->
        requireImportedVariantParents(input.toPath().toAbsolutePath().parent)
        check(Files.isRegularFile(input.toPath(), LinkOption.NOFOLLOW_LINKS) &&
            !Files.isSymbolicLink(input.toPath()) && input.length() > 0) { "Missing regular Runtime variant input: $input" }
        val path = input.toPath().toAbsolutePath().normalize()
        check(!path.startsWith(stage) && !stage.startsWith(path)) { "Runtime variant output overlaps an input: $input" }
    }
    val identity = inputs.getValue("identity").readReleaseObject()
    check(identity.releaseString("target") == component) { "Runtime variant identity target differs from requested component" }
    val componentId = identity.releaseString("componentId")
    check(componentId.matches(Regex("sha256:[0-9a-f]{64}"))) { "Runtime variant component identity is invalid" }
    val expectedName = "codex-agent-runtime-variant-$component-${componentId.removePrefix("sha256:")}.zip"
    val before = inputs.mapValues { (_, file) -> file.length() to file.releaseDigest() }
    val temporaryParent = owned.resolve("tmp")
    requireImportedVariantParents(temporaryParent)
    Files.createDirectories(temporaryParent)
    val temporary = Files.createTempDirectory(temporaryParent, "imported-runtime-variant-").toFile()
    try {
        val captured = inputs.mapValues { (name, input) ->
            temporary.resolve("$name/${input.name}").also { copy ->
                copy.parentFile.mkdirs()
                Files.copy(input.toPath(), copy.toPath())
                check((copy.length() to copy.releaseDigest()) == before.getValue(name)) {
                    "Runtime variant input changed during capture: $name"
                }
            }
        }
        // Only after all original inputs have passed preflight/capture may stale stage bytes be removed.
        deleteImportedVariantWorkspace(stage)
        Files.createDirectories(destination)
        try {
            run(listOf("python3", "-m", "ci.products.runtime_variant") +
                captured.flatMap { (name, file) -> listOf("--$name", file.absolutePath) } +
                listOf("--output-directory", destination.toString()))
            check(output.listFiles()?.map(File::getName) == listOf(expectedName)) {
                "Runtime metadata must contain only the exact variant ZIP"
            }
            val bundle = output.resolve(expectedName)
            check(!Files.isSymbolicLink(bundle.toPath()) && bundle.isFile && bundle.length() > 0) {
                "Runtime variant producer did not emit a regular nonempty ZIP"
            }
            inputs.values.forEach { input ->
                requireImportedVariantParents(input.toPath().toAbsolutePath().parent)
                check(Files.isRegularFile(input.toPath(), LinkOption.NOFOLLOW_LINKS) &&
                    !Files.isSymbolicLink(input.toPath())) { "Original Runtime variant input became unsafe: $input" }
            }
            check(inputs.mapValues { (_, file) -> file.length() to file.releaseDigest() } == before) {
                "Original Runtime variant inputs changed during production"
            }
        } catch (error: Exception) {
            deleteImportedVariantWorkspace(stage)
            throw error
        }
    } finally {
        deleteImportedVariantWorkspace(temporary.toPath())
    }
}
