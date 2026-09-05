import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

internal const val NODE_BINDING_RUNNER_ARCHIVE = "codex-agent-node-binding-validation-runner.zip"
internal const val NODE_BINDING_PROGRAM = "codex-agent-codex-agent-runtime-desktop-test.js"

@DisableCachingByDefault(because = "The product binary receipt owns the compiled program and pinned harness")
abstract class StageNodeBindingValidationRunnerTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compiledProgram: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val nodeModules: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val npmLock: RegularFileProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    @TaskAction fun stage() = stageNodeBindingRunner(
        compiledProgram.get().asFile, nodeModules.get().asFile,
        npmLock.get().asFile, outputDirectory.get().asFile,
    )
}

internal fun stageNodeBindingRunner(program: File, modules: File, lock: File, output: File) {
    val packages = lock.readReleaseObject().getValue("packages").jsonObject
    val root = modules.absoluteFile.normalize()
    val selected = linkedSetOf<File>()
    fun resolve(owner: File, name: String): File {
        check(name.matches(Regex("(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+"))) {
            "Unsafe Node harness dependency: $name"
        }
        var cursor = owner
        while (cursor.toPath().startsWith(root.parentFile.toPath())) {
            val candidate = cursor.resolve("node_modules/$name")
            if (candidate.isDirectory) return candidate
            cursor = cursor.parentFile ?: break
        }
        error("Pinned Node harness dependency is missing: $name")
    }
    fun visit(directory: File) {
        check(directory.toPath().startsWith(root.toPath()) && !Files.isSymbolicLink(directory.toPath())) {
            "Node harness dependency escapes its installed root"
        }
        if (!selected.add(directory)) return
        val manifest = directory.resolve("package.json").readReleaseObject()
        val key = directory.relativeTo(root.parentFile).invariantSeparatorsPath
        val pinned = packages[key] as? JsonObject ?: error("Node harness dependency is absent from lock: $key")
        check(pinned["link"] == null && pinned.getValue("version") == manifest.getValue("version")) {
            "Node harness installed dependency differs from lock: $key"
        }
        val dependencies = (manifest["dependencies"] as? JsonObject).orEmpty()
        dependencies.keys.sorted().forEach { visit(resolve(directory, it)) }
    }
    listOf("mocha", "kotlin-web-helpers", "source-map-support").forEach {
        visit(resolve(root.parentFile, it))
    }
    check(program.resolve(NODE_BINDING_PROGRAM).isFile) { "Compiled Node binding test entry is missing" }
    output.deleteRecursively()
    output.mkdirs()
    copyNodeBindingTree(program, output.resolve("program"))
    selected.forEach { directory ->
        copyNodeBindingTree(directory, output.resolve(directory.relativeTo(root.parentFile).path), excludeNestedModules = true)
    }
    lock.copyTo(output.resolve("package-lock.json"))
}

internal fun copyNodeBindingTree(source: File, destination: File, excludeNestedModules: Boolean = false) {
    check(source.isDirectory && !Files.isSymbolicLink(source.toPath())) { "Unsafe Node binding tree: $source" }
    source.walkTopDown().onEnter { directory ->
        check(!Files.isSymbolicLink(directory.toPath())) { "Symbolic Node binding directory: $directory" }
        !excludeNestedModules || directory == source || directory.name != "node_modules"
    }.forEach { file ->
        check(!Files.isSymbolicLink(file.toPath()) && (file.isFile || file.isDirectory)) {
            "Unsafe Node binding entry: $file"
        }
        if (file.isFile) {
            val target = destination.resolve(file.relativeTo(source).path)
            target.parentFile.mkdirs()
            file.copyTo(target)
        }
    }
}
