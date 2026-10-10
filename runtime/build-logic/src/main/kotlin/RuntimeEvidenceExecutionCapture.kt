import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.util.Base64
import java.util.Locale
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

internal data class RuntimeEvidenceProcessCapture(val id: String, val exitCode: Int, val output: ByteArray)

private val runtimeEvidenceLanguageOverrides = setOf(
    "NODE_OPTIONS", "NODE_PATH", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS",
)
private val runtimeEvidenceDeclaredLoaderPaths = setOf("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
private fun isRuntimeEvidenceOverride(name: String): Boolean {
    val key = name.uppercase(Locale.ROOT)
    return key in runtimeEvidenceLanguageOverrides || key.startsWith("LD_") || key.startsWith("DYLD_")
}

internal fun ProcessBuilder.useRuntimeEvidenceEnvironment(declared: Map<String, String>): ProcessBuilder = apply {
    check(declared.keys.none {
        isRuntimeEvidenceOverride(it) && it.uppercase(Locale.ROOT) !in runtimeEvidenceDeclaredLoaderPaths
    }) {
        "Runtime evidence environment contains an execution override"
    }
    environment().keys.filter(::isRuntimeEvidenceOverride).toList().forEach(environment()::remove)
    environment().putAll(declared)
}

internal fun validateRuntimeEvidenceOutputs(outputs: List<File>, inputs: List<File>) {
    val paths = outputs.map { it.toPath().toAbsolutePath() }
    fun sameFile(first: java.nio.file.Path, second: java.nio.file.Path): Boolean =
        first.toFile().canonicalFile == second.toFile().canonicalFile ||
            (Files.exists(first) && Files.exists(second) && Files.isSameFile(first, second))
    paths.forEachIndexed { index, output ->
        check(paths.take(index).none { sameFile(it, output) }) { "Runtime evidence outputs must be distinct" }
    }
    paths.forEach { output ->
        check(output == output.normalize()) { "Runtime evidence output path must be normalized" }
        generateSequence(output) { it.parent }.forEach { path ->
            check(!Files.isSymbolicLink(path)) { "Runtime evidence output has a symbolic ancestor" }
            if (Files.exists(path, NOFOLLOW_LINKS)) {
                check(if (path == output) Files.isRegularFile(path, NOFOLLOW_LINKS)
                      else Files.isDirectory(path, NOFOLLOW_LINKS)) { "Runtime evidence output path is not regular" }
            }
        }
        check(inputs.none { sameFile(it.toPath().toAbsolutePath().normalize(), output) }) {
            "Runtime evidence output overlaps an imported input"
        }
    }
}

/** Raw external execution evidence, not a deterministic product manifest or admission token. */
internal fun writeRuntimeEvidenceExecution(
    file: File,
    component: String,
    target: String,
    testClass: String,
    executions: List<RuntimeEvidenceProcessCapture>,
) {
    check(target in desktopRuntimeEvidenceTargets) { "Unknown adapter execution target" }
    check(component in setOf("jvm", "node-js", "node-wasm") ||
        component == desktopRuntimeEvidenceTargets.getValue(target).classifier.removePrefix("app-server-")) {
        "Unknown or mismatched Runtime execution component"
    }
    check(executions.map { it.id }.distinct().size == executions.size) { "Duplicate execution capture" }
    file.atomicWriteJson(buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("component", JsonPrimitive(component))
        put("target", JsonPrimitive(target))
        put("testClass", JsonPrimitive(testClass))
        put("executions", buildJsonArray {
            executions.forEach { execution ->
                add(buildJsonObject {
                    put("id", JsonPrimitive(execution.id))
                    put("exitCode", JsonPrimitive(execution.exitCode))
                    put("outputBase64", JsonPrimitive(Base64.getEncoder().encodeToString(execution.output)))
                })
            }
        })
    })
}

internal fun writeRuntimeEvidenceTestReport(file: File, testClass: String, methods: Set<String>) {
    // These are reviewed class/method identifiers, never arbitrary XML text.
    check(testClass.matches(Regex("[A-Za-z0-9_.]+")) && methods.isNotEmpty() &&
        methods.all { it.matches(Regex("[A-Za-z0-9_]+")) }) { "Invalid runtime test identifiers" }
    file.parentFile.mkdirs()
    file.writeText(buildString {
        append("<testsuite tests=\"").append(methods.size)
            .append("\" skipped=\"0\" failures=\"0\" errors=\"0\">\n")
        methods.forEach { method ->
            append("  <testcase classname=\"").append(testClass)
                .append("\" name=\"").append(method).append("\"/>\n")
        }
        append("</testsuite>\n")
    })
}

internal fun verifyRuntimeEvidenceTestReport(file: File, testClass: String, methods: Set<String>) {
    val suite = secureDocumentBuilderFactory(namespaceAware = true).newDocumentBuilder().parse(file).documentElement
    check(suite.tagName == "testsuite") { "Runtime test report has no testsuite root" }
    check(suite.getAttribute("tests").toInt() == methods.size &&
        suite.getAttribute("skipped").toInt() == 0 && suite.getAttribute("failures").toInt() == 0 &&
        suite.getAttribute("errors").toInt() == 0) {
        "Runtime smoke must run every exact test without skips or failures"
    }
    val cases = suite.getElementsByTagName("testcase").let { nodes ->
        (0 until nodes.length).map { nodes.item(it) as org.w3c.dom.Element }
    }
    check(cases.size == methods.size &&
        cases.map { it.getAttribute("classname") }.toSet() == setOf(testClass) &&
        cases.map { it.getAttribute("name") }.toSet() == methods) {
        "Runtime test class or method inventory mismatch"
    }
    check(suite.getElementsByTagName("failure").length == 0 &&
        suite.getElementsByTagName("error").length == 0 &&
        suite.getElementsByTagName("skipped").length == 0) {
        "Runtime test report contains a non-passing case"
    }
}
