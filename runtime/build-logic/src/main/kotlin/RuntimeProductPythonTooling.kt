import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardOpenOption
import java.util.concurrent.TimeUnit

private val runtimeProductPythonResources = listOf(
    "ci/products/__init__.py",
    "ci/products/inventory.py",
    "ci/products/test_results.py",
    "ci/products/runtime_evidence.py",
    "ci/products/c_abi.py",
    "ci/products/runtime_flags.py",
    "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
    "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
    "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
    "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
)

private val runtimeProductPythonModules = setOf("runtime_evidence", "c_abi", "runtime_flags", "test_results")

private object RuntimeProductPythonToolingMarker

internal fun runRuntimeProductPythonModule(
    module: String, arguments: List<String>,
    resource: (String) -> java.io.InputStream? =
        { RuntimeProductPythonToolingMarker::class.java.classLoader.getResourceAsStream(it) },
): String {
    check(module in runtimeProductPythonModules) {
        "Unsupported packaged Runtime product Python module: $module"
    }
    return runRuntimeProductPython(
        "ci.products.$module",
        "runpy.run_module('ci.products.$module', run_name='__main__', alter_sys=True)",
        arguments,
        resource,
    )
}

internal fun verifyRuntimeAdapterProjection(component: String, projection: java.io.File) {
    check(component in setOf("jvm", "node-js", "node-wasm")) {
        "Unsupported Runtime adapter projection: $component"
    }
    runRuntimeProductPython(
        "Runtime adapter projection verifier",
        """
from pathlib import Path
import sys
from ci.products.inventory import canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes
from ci.products.runtime_evidence import validate_runtime_adapter_projection

contents = read_regular_file_bytes(
    Path(sys.argv[2]), max_bytes=64 * 1024 * 1024, reject_symlink_parents=True
)
projection = validate_runtime_adapter_projection(load_canonical_json_bytes(contents))
if projection["component"] != sys.argv[1]:
    raise ValueError("Runtime adapter projection component mismatch")
if canonical_json_bytes(projection) != contents:
    raise ValueError("Runtime adapter projection is not canonical JSON")
            """.trimIndent(),
        listOf(component, projection.absolutePath),
    )
}

private fun runtimePythonInventory(root: java.io.File): Map<String, String> =
    Files.walk(root.toPath()).use { paths ->
        paths.toList().associate { path ->
            check(!Files.isSymbolicLink(path)) { "Packaged Runtime Python resource is symbolic: $path" }
            val identity = when {
                Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) -> "directory"
                Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) -> path.toFile().releaseDigest()
                else -> error("Packaged Runtime Python resource is not regular: $path")
            }
            root.toPath().relativize(path).toString() to identity
        }
    }

private fun runRuntimeProductPython(
    label: String, entry: String, arguments: List<String>,
    resource: (String) -> java.io.InputStream? =
        { RuntimeProductPythonToolingMarker::class.java.classLoader.getResourceAsStream(it) },
): String {
    val root = Files.createTempDirectory("codex-agent-runtime-product-python-").toRealPath().toFile()
    var log: java.nio.file.Path? = null
    try {
        runtimeProductPythonResources.forEach { relative ->
            val name = "python/$relative"
            val output = root.resolve(relative)
            Files.createDirectories(output.parentFile.toPath())
            val input = resource(name) ?: error("Packaged Runtime product Python resource is missing: $name")
            input.use { source ->
                Files.newOutputStream(output.toPath(), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE).use {
                    source.copyTo(it)
                }
            }
        }
        // A regular private package cannot resolve an ambient namespace portion.
        Files.write(root.resolve("ci/__init__.py").toPath(), byteArrayOf(), StandardOpenOption.CREATE_NEW)
        val captured = runtimePythonInventory(root)
        val processLog = Files.createTempFile("codex-agent-runtime-product-python-", ".log").also { log = it }
        val bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1));\n$entry"
        val command = listOf("python3", "-I", "-S", "-B", "-c", bootstrap, root.absolutePath) + arguments
        val process = ProcessBuilder(command)
            .directory(root)
            .redirectErrorStream(true)
            .redirectOutput(processLog.toFile())
            .apply {
                environment()["LC_ALL"] = "C"
                environment()["LANG"] = "C"
            }
            .start()
        process.outputStream.close()
        val completed = process.waitFor(10, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        check(captured == runtimePythonInventory(root)) {
            "Packaged Runtime Python resources changed during execution"
        }
        val text = Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(Files.readAllBytes(processLog)))
            .toString()
        check(completed && process.exitValue() == 0) {
            "$label failed (${if (completed) process.exitValue() else "timeout"}): ${text.trim()}"
        }
        return text
    } finally {
        log?.let(Files::deleteIfExists)
        // Only this invocation's private extraction; Files.walk never follows links.
        Files.walk(root.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
