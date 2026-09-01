import java.io.ByteArrayOutputStream
import java.nio.file.Files

private val productPythonResources = listOf(
    "ci/products/__init__.py",
    "ci/products/inventory.py",
    "ci/products/test_results.py",
    "ci/products/runtime_evidence.py",
    "ci/products/c_abi.py",
)

private val extractedProductPythonRoot: java.io.File by lazy {
    val root = Files.createTempDirectory("codex-agent-product-python-").toFile().also {
        it.deleteOnExit()
    }
    productPythonResources.forEach { relative ->
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

private object ProductPythonToolingMarker

internal fun runProductPythonModule(module: String, arguments: List<String>): String {
    check(module in setOf("runtime_evidence", "c_abi", "test_results")) {
        "Unsupported packaged product Python module: $module"
    }
    val output = ByteArrayOutputStream()
    val root = extractedProductPythonRoot
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
