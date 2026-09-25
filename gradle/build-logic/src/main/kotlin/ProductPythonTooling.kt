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

internal fun runProductPythonModule(module: String, arguments: List<String>): String {
    val selected = checkNotNull(productPythonResources[module]) { "Unsupported packaged product Python module: $module" }
    check(module != "cpp_package" || arguments.firstOrNull() == "verify-evidence") {
        "Packaged C++ tooling permits only imported evidence verification"
    }
    check(module != "receipt" || arguments.firstOrNull() in setOf("snapshot-tree", "verify-output-manifest")) {
        "Packaged receipt tooling permits only original snapshots and manifest verification"
    }
    return runPackagedProductPython(module, selected, arguments,
        script = if (module == "cpp_package") selected.single() else null)
}
