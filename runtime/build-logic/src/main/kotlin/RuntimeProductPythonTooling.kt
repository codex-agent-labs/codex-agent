import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
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

private val extractedRuntimeProductPythonRoot: java.io.File by lazy {
    val root = Files.createTempDirectory("codex-agent-runtime-product-python-").toFile().also {
        it.deleteOnExit()
    }
    root.resolve("ci").also {
        check(it.mkdir()) { "Could not create packaged Runtime Python ci directory" }
        it.deleteOnExit()
    }
    root.resolve("ci/products").also {
        check(it.mkdir()) { "Could not create packaged Runtime Python products directory" }
        it.deleteOnExit()
    }
    runtimeProductPythonResources.forEach { relative ->
        val resource = "python/$relative"
        val output = root.resolve(relative)
        check(output.parentFile.isDirectory || output.parentFile.mkdirs()) {
            "Could not create packaged Runtime product resource directory: ${output.parentFile}"
        }
        val input = RuntimeProductPythonToolingMarker::class.java.classLoader.getResourceAsStream(resource)
            ?: error("Packaged Runtime product Python resource is missing: $resource")
        input.use { source ->
            Files.newOutputStream(output.toPath(), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE).use {
                source.copyTo(it)
            }
        }
        output.deleteOnExit()
    }
    root
}

internal fun runRuntimeProductPythonModule(module: String, arguments: List<String>): String {
    check(module in runtimeProductPythonModules) {
        "Unsupported packaged Runtime product Python module: $module"
    }
    val root = extractedRuntimeProductPythonRoot
    val log = Files.createTempFile("codex-agent-runtime-product-python-", ".log")
    try {
        val process = ProcessBuilder(listOf("python3", "-m", "ci.products.$module") + arguments)
            .directory(root)
            .redirectErrorStream(true)
            .redirectOutput(log.toFile())
            .apply {
                environment().remove("PYTHONHOME")
                environment().remove("PYTHONINSPECT")
                environment().remove("PYTHONSTARTUP")
                environment()["PYTHONPATH"] = root.absolutePath
                environment()["PYTHONDONTWRITEBYTECODE"] = "1"
                environment()["PYTHONNOUSERSITE"] = "1"
                environment()["PYTHONSAFEPATH"] = "1"
                environment()["LC_ALL"] = "C"
                environment()["LANG"] = "C"
            }
            .start()
        process.outputStream.close()
        val completed = process.waitFor(10, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        val text = Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(Files.readAllBytes(log)))
            .toString()
        check(completed && process.exitValue() == 0) {
            "ci.products.$module failed (${if (completed) process.exitValue() else "timeout"}): ${text.trim()}"
        }
        return text
    } finally {
        Files.deleteIfExists(log)
    }
}
