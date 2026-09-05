import java.io.File
import java.nio.file.Files
import java.util.concurrent.TimeUnit
import java.util.zip.ZipFile
import javax.xml.XMLConstants
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult
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
import org.w3c.dom.Element

internal const val NODE_BINDING_RUNNER_ARCHIVE = "codex-agent-node-binding-validation-runner.zip"
internal const val NODE_BINDING_PROGRAM = "codex-agent-codex-agent-runtime-desktop-test.js"
internal val nodeBindingMethods = setOf(
    "projectsCanonicalLifecycleIdentityFailureAndOwnership",
    "abortsBeforeStartingAndStopsDisposedObservation",
    "mapsCanonicalCancellationAndRemovesAbortListener",
    "isolatesListenerFailureWhileOtherObserversAndCleanupContinue",
    "projectsAuthenticationStateMethodsIdentityAndDisposal",
    "mapsAuthenticationFailureAndAbortSignalCancellation",
)

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

private fun copyNodeBindingTree(source: File, destination: File, excludeNestedModules: Boolean = false) {
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

@DisableCachingByDefault(because = "Binding validation must execute the imported compiled tests")
abstract class ExecuteNodeBindingValidationTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val runnerArchive: RegularFileProperty
    @get:Input abstract val nodeExecutable: Property<String>
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun execute() = executeNodeBindingValidation(
        runnerArchive.get().asFile, nodeExecutable.get(), outputDirectory.get().asFile,
    )
}

internal fun executeNodeBindingValidation(archive: File, node: String, output: File) {
    output.deleteRecursively()
    val workspace = Files.createTempDirectory("node-binding-validation-").toFile()
    try {
        check(archive.length() in 1..(512L * 1024 * 1024)) { "Node binding archive exceeds bound" }
        val modes = readDesktopRuntimeUnixModes(archive)
        ZipFile(archive).use { zip ->
            val entries = zip.entries().asSequence().toList()
            check(entries.size in 1..16384 && entries.map { it.name }.toSet().size == entries.size &&
                entries.sumOf { it.size } <= 1024L * 1024 * 1024) { "Node binding archive inventory exceeds bound" }
            entries.forEach { entry ->
                val name = entry.name
                check(!entry.isDirectory && name.split('/').none { it.isEmpty() || it == "." || it == ".." } &&
                    '\\' !in name && ':' !in name && name.none { it.code < 32 || it.code == 127 } &&
                    modes[name] == 0x81a4 && entry.size in 0..(128L * 1024 * 1024) &&
                    (name.startsWith("program/") || name.startsWith("node_modules/") || name == "package-lock.json")) {
                    "Unsafe Node binding archive member: $name"
                }
                val target = workspace.resolve(name)
                target.parentFile.mkdirs()
                zip.getInputStream(entry).use { input -> target.outputStream().use { stream ->
                    val buffer = ByteArray(8192)
                    var copied = 0L
                    while (true) {
                        val count = input.read(buffer)
                        if (count < 0) break
                        copied += count
                        check(copied <= entry.size) { "Node binding member exceeds declared length: $name" }
                        stream.write(buffer, 0, count)
                    }
                } }
                check(target.length() == entry.size) { "Truncated Node binding archive member: $name" }
            }
        }
        fun run(arguments: List<String>): Pair<Int, String> {
            val log = workspace.resolve("process.log")
            val process = ProcessBuilder(listOf(node) + arguments).directory(workspace)
                .redirectErrorStream(true).redirectOutput(log).apply {
                    environment().remove("NODE_OPTIONS")
                    environment().remove("NODE_PATH")
                }.start()
            val completed = process.waitFor(5, TimeUnit.MINUTES)
            if (!completed) process.destroyForcibly().waitFor()
            return (if (completed) process.exitValue() else -1) to log.readText()
        }
        val (versionExit, version) = run(listOf("--version"))
        check(versionExit == 0 && version.trim() == "v$PINNED_NODE_VERSION") {
            "Node binding validation requires Node v$PINNED_NODE_VERSION"
        }
        val raw = workspace.resolve("mocha.xml")
        val (exit, log) = run(listOf(
            "node_modules/mocha/bin/_mocha", "--no-config", "--no-package", "--forbid-only", "--forbid-pending",
            "--require", "./node_modules/source-map-support/register.js",
            "--require", "./node_modules/kotlin-web-helpers/dist/kotlin-test-nodejs-runner.js",
            "--reporter", "xunit", "--reporter-options", "output=${raw.absolutePath}",
            "--grep", "^\\s*CodexNodeApiTest ", "--timeout", "120000", "program/$NODE_BINDING_PROGRAM",
        ))
        check(exit == 0) { "Imported Node binding tests failed ($exit): $log" }
        val document = secureDocumentBuilderFactory().newDocumentBuilder().parse(raw)
        val suite = document.documentElement
        check(suite.tagName == "testsuite" && suite.getAttribute("tests") == nodeBindingMethods.size.toString() &&
            listOf("failures", "errors", "skipped").all { suite.getAttribute(it) == "0" }) {
            "Node binding validation must execute every test without skips or failures"
        }
        val cases = suite.getElementsByTagName("testcase").let { nodes ->
            (0 until nodes.length).map { nodes.item(it) as Element }
        }
        check(cases.size == nodeBindingMethods.size && cases.map { it.getAttribute("name") }.toSet() == nodeBindingMethods &&
            cases.all { it.getAttribute("classname").trim() == "CodexNodeApiTest" &&
                it.getElementsByTagName("failure").length == 0 && it.getElementsByTagName("error").length == 0 &&
                it.getElementsByTagName("skipped").length == 0 }) { "Node binding test inventory differs" }
        // Preserve the raw Mocha report; only project its observed IDs to the
        // established Gradle naming convention used by the shared parity reader.
        val reports = output.resolve("test-report").also { it.mkdirs() }
        raw.copyTo(reports.resolve("raw-mocha.xml"))
        suite.setAttribute("name", "jsNodeTest.CodexNodeApiTest")
        cases.forEach {
            it.setAttribute("classname", "jsNodeTest.CodexNodeApiTest")
            it.setAttribute("name", it.getAttribute("name") + "[js, node]")
        }
        TransformerFactory.newInstance().apply {
            setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
            setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "")
        }.newTransformer().transform(DOMSource(document), StreamResult(
            reports.resolve("TEST-jsNodeTest.CodexNodeApiTest.xml"),
        ))
        copyNodeBindingTree(workspace.resolve("program"), output.resolve("test-program"))
    } finally {
        workspace.deleteRecursively()
    }
}
