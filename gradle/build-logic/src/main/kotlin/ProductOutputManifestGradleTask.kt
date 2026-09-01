import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Paths
import java.nio.file.attribute.BasicFileAttributes
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

@DisableCachingByDefault(because = "Imported product stages must be snapshotted before verification")
abstract class SnapshotImportedProductStageTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sourceDirectory: DirectoryProperty
    @get:Internal abstract val outputDirectory: DirectoryProperty
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init { pythonExecutable.convention("python3") }

    @TaskAction
    fun snapshot() {
        snapshotWithCanonicalProducer(
            processes,
            pythonExecutable.get(),
            repositoryRoot.get().asFile,
            sourceDirectory.get().asFile,
            outputDirectory.get().asFile,
        )
    }
}

internal fun snapshotWithCanonicalProducer(
    processes: ExecOperations,
    pythonExecutable: String,
    repositoryRoot: File,
    source: File,
    destination: File,
) {
    check(!destination.exists()) { "Imported product snapshot destination is immutable: $destination" }
    processes.exec {
        workingDir(repositoryRoot)
        environment("PYTHONDONTWRITEBYTECODE", "1")
        commandLine(
            pythonExecutable, "-m", "ci.products", "receipt", "snapshot-tree",
            "--source", source.absolutePath,
            "--destination", destination.absolutePath,
        )
    }
}

@DisableCachingByDefault(because = "Verifies the complete freshly staged output tree in place")
abstract class WriteProductOutputManifestTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val product: Property<String>
    @get:Input abstract val component: Property<String>
    @get:Input abstract val phase: Property<String>
    @get:Input abstract val target: Property<String>
    @get:Input abstract val productVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:Input abstract val outputRoots: MapProperty<String, String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val outputsDirectory: DirectoryProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty
    @get:Internal abstract val stageRoot: DirectoryProperty
    @get:OutputFile abstract val manifestFile: RegularFileProperty

    init {
        pythonExecutable.convention("python3")
    }

    @TaskAction
    fun writeManifest() {
        val root = stageRoot.get().asFile.toPath().toAbsolutePath().normalize()
        val outputs = outputsDirectory.get().asFile.toPath().toAbsolutePath().normalize()
        val manifest = manifestFile.get().asFile.toPath().toAbsolutePath().normalize()
        check(outputs.parent == root && outputs.fileName.toString() == "outputs") {
            "Product outputs must be the stage root's outputs directory"
        }
        check(manifest.parent == root && manifest.fileName.toString() == "output-manifest.json") {
            "Product output manifest must be output-manifest.json in the stage root"
        }
        val rootAttributes = Files.readAttributes(
            root,
            BasicFileAttributes::class.java,
            LinkOption.NOFOLLOW_LINKS,
        )
        check(rootAttributes.isDirectory && !rootAttributes.isSymbolicLink && !rootAttributes.isOther) {
            "Product stage root must be a real directory"
        }
        outputRoots.get().values.forEach { value ->
            val path = Paths.get(value)
            check(!path.isAbsolute && '\\' !in value && path.normalize() == path &&
                (value == "outputs" || value.startsWith("outputs/"))) {
                "Product output roots must be normalized descendants of outputs/"
            }
        }
        Files.deleteIfExists(manifest)
        val arguments = mutableListOf(
            pythonExecutable.get(), "-m", "ci.products", "receipt", "write-output-manifest",
            "--root", root.toString(),
            "--product", product.get(),
            "--component", component.get(),
            "--phase", phase.get(),
            "--target", target.get(),
            "--product-version", productVersion.get(),
        )
        outputRoots.get().toSortedMap().forEach { (kind, path) ->
            arguments += listOf("--output-root", "$kind=$path")
        }
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(arguments)
        }
    }
}

@DisableCachingByDefault(because = "Imported product stages are external evidence and must be reverified")
abstract class VerifyImportedProductOutputManifestTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:Input abstract val product: Property<String>
    @get:Input abstract val component: Property<String>
    @get:Input abstract val phase: Property<String>
    @get:Input abstract val target: Property<String>
    @get:Input abstract val productVersion: Property<String>
    @get:Input abstract val pythonExecutable: Property<String>
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stageRoot: DirectoryProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    init {
        pythonExecutable.convention("python3")
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun verifyManifest() {
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(
                pythonExecutable.get(), "-m", "ci.products", "receipt", "verify-output-manifest",
                "--root", stageRoot.get().asFile.absolutePath,
                "--product", product.get(),
                "--component", component.get(),
                "--phase", phase.get(),
                "--target", target.get(),
                "--product-version", productVersion.get(),
            )
        }
    }
}
