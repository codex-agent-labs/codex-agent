import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Paths
import java.nio.file.attribute.BasicFileAttributes
import org.gradle.api.Project
import org.gradle.api.DefaultTask
import org.gradle.api.file.Directory
import org.gradle.api.file.FileCollection
import org.gradle.api.provider.Property
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.TaskProvider

private fun Exec.useTrustedRuntimePython(repositoryRoot: File) {
    workingDir(repositoryRoot)
    setEnvironment(environment.toMutableMap().apply {
        remove("PYTHONHOME")
        remove("PYTHONINSPECT")
        remove("PYTHONSTARTUP")
        put("PYTHONPATH", repositoryRoot.absolutePath)
        put("PYTHONDONTWRITEBYTECODE", "1")
        put("PYTHONNOUSERSITE", "1")
        put("PYTHONSAFEPATH", "1")
        put("LC_ALL", "C")
        put("LANG", "C")
    })
}

abstract class ValidateRuntimeEvidenceTargetTask : DefaultTask() {
    @get:Input
    abstract val requestedTarget: Property<String>

    @get:Input
    abstract val expectedTarget: Property<String>

    @TaskAction
    fun validate() {
        check(requestedTarget.get() == expectedTarget.get()) {
            "-PcodexAgent.desktopEvidenceTarget must equal ${expectedTarget.get()}"
        }
    }
}

fun Project.registerRuntimeEvidenceTargetValidation(
    name: String,
    requested: String,
    expected: String,
): TaskProvider<ValidateRuntimeEvidenceTargetTask> =
    tasks.register(name, ValidateRuntimeEvidenceTargetTask::class.java) {
        requestedTarget.set(requested)
        expectedTarget.set(expected)
    }

fun Project.registerRuntimeStageSnapshot(
    name: String,
    source: Provider<Directory>,
    destination: Provider<Directory>,
    tooling: FileCollection,
    repositoryRoot: File,
): TaskProvider<Exec> = tasks.register(name, Exec::class.java) {
    inputs.dir(source)
    inputs.files(tooling)
    outputs.upToDateWhen { false }
    useTrustedRuntimePython(repositoryRoot)
    doFirst {
        check(!destination.get().asFile.exists()) {
            "Imported Runtime snapshot destination is immutable: ${destination.get().asFile}"
        }
        commandLine(
            "python3", "-m", "ci.products", "receipt", "snapshot-tree",
            "--source", source.get().asFile.absolutePath,
            "--destination", destination.get().asFile.absolutePath,
        )
    }
}

fun Project.registerRuntimeOutputManifest(
    name: String,
    dependency: Any,
    component: Provider<String>,
    phase: String,
    target: Provider<String>,
    version: Provider<String>,
    outputRoots: Map<String, String>,
    outputsDirectory: Provider<Directory>,
    stageRoot: Provider<Directory>,
    tooling: FileCollection,
    repositoryRoot: File,
): TaskProvider<Exec> = tasks.register(name, Exec::class.java) {
    dependsOn(dependency)
    inputs.property("product", "runtime")
    inputs.property("component", component)
    inputs.property("phase", phase)
    inputs.property("target", target)
    inputs.property("productVersion", version)
    inputs.property("outputRoots", outputRoots)
    inputs.dir(outputsDirectory)
    inputs.files(tooling)
    outputs.file(stageRoot.map { it.file("output-manifest.json") })
    useTrustedRuntimePython(repositoryRoot)
    doFirst {
        val root = stageRoot.get().asFile.toPath().toAbsolutePath().normalize()
        val outputs = outputsDirectory.get().asFile.toPath().toAbsolutePath().normalize()
        val manifest = root.resolve("output-manifest.json")
        check(outputs.parent == root && outputs.fileName.toString() == "outputs") {
            "Runtime outputs must be the stage root's outputs directory"
        }
        val rootAttributes = Files.readAttributes(
            root,
            BasicFileAttributes::class.java,
            LinkOption.NOFOLLOW_LINKS,
        )
        check(rootAttributes.isDirectory && !rootAttributes.isSymbolicLink && !rootAttributes.isOther) {
            "Runtime stage root must be a real directory"
        }
        outputRoots.values.forEach { value ->
            val path = Paths.get(value)
            check(!path.isAbsolute && '\\' !in value && path.normalize() == path &&
                (value == "outputs" || value.startsWith("outputs/"))) {
                "Runtime output roots must be normalized descendants of outputs/"
            }
        }
        Files.deleteIfExists(manifest)
        val arguments = mutableListOf(
            "python3", "-m", "ci.products", "receipt", "write-output-manifest",
            "--root", stageRoot.get().asFile.absolutePath,
            "--product", "runtime",
            "--component", component.get(),
            "--phase", phase,
            "--target", target.get(),
            "--product-version", version.get(),
        )
        outputRoots.toSortedMap().forEach { (kind, path) ->
            arguments += listOf("--output-root", "$kind=$path")
        }
        commandLine(arguments)
    }
}

fun Project.registerRuntimeOutputVerification(
    name: String,
    dependency: Any,
    component: Provider<String>,
    phase: String,
    target: Provider<String>,
    version: Provider<String>,
    stageRoot: Provider<Directory>,
    tooling: FileCollection,
    repositoryRoot: File,
): TaskProvider<Exec> = tasks.register(name, Exec::class.java) {
    dependsOn(dependency)
    inputs.property("product", "runtime")
    inputs.property("component", component)
    inputs.property("phase", phase)
    inputs.property("target", target)
    inputs.property("productVersion", version)
    inputs.dir(stageRoot)
    inputs.files(tooling)
    outputs.upToDateWhen { false }
    useTrustedRuntimePython(repositoryRoot)
    doFirst {
        commandLine(
            "python3", "-m", "ci.products", "receipt", "verify-output-manifest",
            "--root", stageRoot.get().asFile.absolutePath,
            "--product", "runtime",
            "--component", component.get(),
            "--phase", phase,
            "--target", target.get(),
            "--product-version", version.get(),
        )
    }
}
