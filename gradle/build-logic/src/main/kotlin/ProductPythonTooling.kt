import java.io.ByteArrayOutputStream
import java.nio.file.Files

private val productPythonResources = mapOf(
    "test_results" to listOf("ci/products/test_results.py"),
    "runtime_evidence" to listOf("ci/products/runtime_evidence.py", "ci/products/test_results.py"),
    "c_abi" to listOf(
        "ci/products/c_abi.py",
        "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
        "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
        "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
        "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
    ),
)

private val extractedProductPythonRoots = mutableMapOf<String, java.io.File>()

private fun extractedProductPythonRoot(module: String): java.io.File = synchronized(extractedProductPythonRoots) {
    extractedProductPythonRoots.getOrPut(module) {
        val root = Files.createTempDirectory("codex-agent-product-python-").toFile().also {
            it.deleteOnExit()
        }
        val resources = listOf("ci/products/__init__.py", "ci/products/inventory.py") +
            checkNotNull(productPythonResources[module]) { "Unsupported packaged product Python module: $module" }
        resources.forEach { relative ->
            val resource = "python/$relative"
            val output = root.resolve(relative)
            output.parentFile.mkdirs()
            val input = ProductPythonToolingMarker::class.java.classLoader.getResourceAsStream(resource)
                ?: error("Packaged product Python resource is missing: $resource")
            input.use { source -> output.outputStream().use(source::copyTo) }
            output.deleteOnExit()
        }
        root
    }
}

private object ProductPythonToolingMarker

internal fun runProductPythonModule(module: String, arguments: List<String>): String {
    val output = ByteArrayOutputStream()
    val root = extractedProductPythonRoot(module)
    val process = ProcessBuilder(listOf("python3", "-m", "ci.products.$module") + arguments)
        .directory(root)
        .redirectInput(ProcessBuilder.Redirect.PIPE)
        .redirectErrorStream(true)
        .apply {
            environment()["PYTHONPATH"] = root.absolutePath
            environment()["PYTHONDONTWRITEBYTECODE"] = "1"
            environment()["LC_ALL"] = "C"
            environment()["LANG"] = "C"
        }
        .start()
    process.inputStream.use { it.copyTo(output) }
    val exit = process.waitFor()
    val stdout = output.toString(Charsets.UTF_8.name())
    check(exit == 0) { "ci.products.$module failed ($exit): ${stdout.trim()}" }
    return stdout
}
