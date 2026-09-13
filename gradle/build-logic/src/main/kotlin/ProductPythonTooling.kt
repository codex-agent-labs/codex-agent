import java.io.ByteArrayOutputStream
import java.nio.file.Files

private val productPythonAbiResources = listOf(
    "codex-agent-runtime-desktop/native/c-api/abi-contract.json",
    "codex-agent-runtime-desktop/native/c-api/exports/linux.map",
    "codex-agent-runtime-desktop/native/c-api/exports/macos.exports",
    "codex-agent-runtime-desktop/native/c-api/exports/windows.def",
)

internal val productPythonResources = mapOf(
    "receipt" to listOf("ci/products/receipt.py"),
    "test_results" to listOf("ci/products/test_results.py"),
    "runtime_evidence" to listOf("ci/products/runtime_evidence.py", "ci/products/test_results.py"),
    "c_abi" to (listOf("ci/products/c_abi.py") + productPythonAbiResources),
    "sdk_package" to (listOf(
        "aggregate", "c_abi", "contract", "contract_attestation", "contract_model",
        "contract_projection", "index", "plan", "receipt", "registry", "restore",
        "runtime_adapter_content", "runtime_adapter_validation", "runtime_aggregate",
        "runtime_attestation", "runtime_evidence", "runtime_flags", "runtime_identity",
        "sdk_compatibility", "sdk_inputs", "sdk_native", "sdk_package", "sdk_runtime_content", "sdk_validation",
        "selection", "signatures", "test_results", "toolchain",
    ).map { "ci/products/$it.py" } + "ci/native_wrappers.py" + productPythonAbiResources),
    "cpp_package" to listOf("codex-agent-bindings/cpp/tools/verify_imported_package.py"),
)

private object ProductPythonToolingMarker

internal fun runProductPythonModule(module: String, arguments: List<String>): String {
    val selected = checkNotNull(productPythonResources[module]) { "Unsupported packaged product Python module: $module" }
    check(module != "cpp_package" || arguments.firstOrNull() == "verify-evidence") {
        "Packaged C++ tooling permits only imported evidence verification"
    }
    check(module != "receipt" || arguments.firstOrNull() in setOf("snapshot-tree", "verify-output-manifest")) {
        "Packaged receipt tooling permits only original snapshots and manifest verification"
    }
    val root = Files.createTempDirectory("codex-agent-product-python-").toRealPath().toFile()
    try {
        val resources = listOf("ci/products/__init__.py", "ci/products/inventory.py") +
            selected
        resources.distinct().forEach { relative ->
            val resource = "python/$relative"
            val output = root.resolve(relative)
            output.parentFile.mkdirs()
            val input = ProductPythonToolingMarker::class.java.classLoader.getResourceAsStream(resource)
                ?: error("Packaged product Python resource is missing: $resource")
            input.use { source -> output.outputStream().use(source::copyTo) }
        }
        // A regular private package cannot fall through to another namespace portion.
        root.resolve("ci/__init__.py").writeText("")
        val captured = verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }
        val entry = if (module == "cpp_package")
            "runpy.run_path(sys.argv.pop(1), run_name='__main__')" else
            "runpy.run_module('ci.products.$module', run_name='__main__', alter_sys=True)"
        val bootstrap = "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); $entry"
        val script = if (module == "cpp_package") listOf(root.resolve(selected.single()).absolutePath) else emptyList()
        val output = ByteArrayOutputStream()
        // -I/-S exclude environment, cwd and site hooks; fresh extraction plus -B excludes stale bytecode.
        val process = ProcessBuilder(listOf("python3", "-I", "-S", "-B", "-c", bootstrap, root.absolutePath) + script + arguments)
            .directory(root)
            .redirectInput(ProcessBuilder.Redirect.PIPE)
            .redirectErrorStream(true)
            .apply {
                environment()["LC_ALL"] = "C"
                environment()["LANG"] = "C"
            }
            .start()
        process.inputStream.use { it.copyTo(output) }
        val exit = process.waitFor()
        val stdout = output.toString(Charsets.UTF_8.name())
        check(captured == verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }) {
            "Packaged product Python resources changed during execution"
        }
        check(exit == 0) { "ci.products.$module failed ($exit): ${stdout.trim()}" }
        return stdout
    } finally {
        // This is only the fresh private extraction owned by this invocation.
        Files.walk(root.toPath()).use { paths -> paths.sorted(Comparator.reverseOrder()).forEach(Files::delete) }
    }
}
