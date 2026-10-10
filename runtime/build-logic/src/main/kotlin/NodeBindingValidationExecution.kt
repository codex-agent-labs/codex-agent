import java.io.File
import java.nio.file.Files
import java.util.concurrent.TimeUnit
import java.util.zip.ZipFile
import javax.xml.XMLConstants
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault
import org.w3c.dom.Element

internal val nodeBindingMethods = setOf(
    "projectsCanonicalLifecycleIdentityFailureAndOwnership",
    "abortsBeforeStartingAndStopsDisposedObservation",
    "mapsCanonicalCancellationAndRemovesAbortListener",
    "isolatesListenerFailureWhileOtherObserversAndCleanupContinue",
    "projectsAuthenticationStateMethodsIdentityAndDisposal",
    "mapsAuthenticationFailureAndAbortSignalCancellation",
)

@DisableCachingByDefault(because = "Binding validation must execute the imported compiled tests")
abstract class ExecuteNodeBindingValidationTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val runnerArchive: RegularFileProperty
    @get:Input abstract val nodeExecutable: Property<String>
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty
    @get:OutputFile abstract val rawReportFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction fun execute() = executeNodeBindingValidation(
        runnerArchive.get().asFile, nodeExecutable.get(), outputDirectory.get().asFile,
        rawReportFile.get().asFile,
    )
}

internal fun executeNodeBindingValidation(archive: File, node: String, output: File, rawReportFile: File) {
    output.deleteRecursively()
    rawReportFile.delete()
    val workspace = Files.createTempDirectory("node-binding-validation-").toFile()
    try {
        check(archive.length() in 1..(512L * 1024 * 1024)) { "Node binding archive exceeds bound" }
        val modes = readDesktopRuntimeUnixModes(archive)
        ZipFile(archive).use { zip ->
            val entries = zip.entries().asSequence().toList()
            check(entries.size in 1..16384 && entries.map { it.name.removeSuffix("/") }.toSet().size == entries.size &&
                entries.sumOf { it.size } <= 1024L * 1024 * 1024) { "Node binding archive inventory exceeds bound" }
            entries.forEach { entry ->
                val name = entry.name
                requireNodeBindingArchiveMember(name, entry.isDirectory, entry.size, modes[name])
                if (entry.isDirectory) return@forEach
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
                .redirectErrorStream(true).redirectOutput(log)
                .useRuntimeEvidenceEnvironment(emptyMap()).start()
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
        // Mocha's raw timestamp, durations and extraction paths are execution
        // evidence, not reusable product bytes.
        rawReportFile.parentFile.mkdirs()
        raw.copyTo(rawReportFile)
        val reports = output.resolve("test-report").also { it.mkdirs() }
        val canonical = secureDocumentBuilderFactory().newDocumentBuilder().newDocument()
        val canonicalSuite = canonical.createElement("testsuite")
        canonicalSuite.setAttribute("name", "jsNodeTest.CodexNodeApiTest")
        canonicalSuite.setAttribute("tests", nodeBindingMethods.size.toString())
        canonicalSuite.setAttribute("failures", "0")
        canonicalSuite.setAttribute("errors", "0")
        canonicalSuite.setAttribute("skipped", "0")
        canonical.appendChild(canonicalSuite)
        cases.map { it.getAttribute("name") }.sorted().forEach { name ->
            canonicalSuite.appendChild(canonical.createElement("testcase").apply {
                setAttribute("classname", "jsNodeTest.CodexNodeApiTest")
                setAttribute("name", "$name[js, node]")
            })
        }
        TransformerFactory.newInstance().apply {
            setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "")
            setAttribute(XMLConstants.ACCESS_EXTERNAL_STYLESHEET, "")
        }.newTransformer().transform(DOMSource(canonical), StreamResult(
            reports.resolve("TEST-jsNodeTest.CodexNodeApiTest.xml"),
        ))
        copyNodeBindingTree(workspace.resolve("program"), output.resolve("test-program"))
    } finally {
        workspace.deleteRecursively()
    }
}

internal fun requireNodeBindingArchiveMember(name: String, directory: Boolean, size: Long, mode: Int?) {
    val path = if (directory) name.removeSuffix("/") else name
    check(path.split('/').none { it.isEmpty() || it == "." || it == ".." } &&
        '\\' !in path && ':' !in path && path.none { it.code < 32 || it.code == 127 } &&
        if (directory) {
            name.endsWith('/') && mode == 0x41ed && size == 0L &&
                (path == "program" || path == "node_modules" ||
                    path.startsWith("program/") || path.startsWith("node_modules/"))
        } else {
            mode == 0x81a4 && size in 0..(128L * 1024 * 1024) &&
                (path.startsWith("program/") || path.startsWith("node_modules/") || path == "package-lock.json")
        }) { "Unsafe Node binding archive member: $name" }
}
