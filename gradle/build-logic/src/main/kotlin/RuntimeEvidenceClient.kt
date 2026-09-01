import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject

data class DesktopRuntimeEvidenceTarget(
    val classifier: String,
    val runnerOs: String,
    val runnerArch: String,
)

val desktopRuntimeEvidenceTargets = linkedMapOf(
    "macosArm64" to DesktopRuntimeEvidenceTarget("app-server-macos-arm64", "macOS", "ARM64"),
    "macosX64" to DesktopRuntimeEvidenceTarget("app-server-macos-x64", "macOS", "X64"),
    "linuxArm64" to DesktopRuntimeEvidenceTarget("app-server-linux-arm64", "Linux", "ARM64"),
    "linuxX64" to DesktopRuntimeEvidenceTarget("app-server-linux-x64", "Linux", "X64"),
    "mingwX64" to DesktopRuntimeEvidenceTarget("app-server-windows-x64", "Windows", "X64"),
)

internal const val JVM_RUNTIME_RUNNER_ARCHIVE = "codex-agent-jvm-runtime-evidence-runner.zip"
internal const val NODE_RUNTIME_JS_BACKEND = "js"
internal const val NODE_RUNTIME_WASM_BACKEND = "wasm"
internal const val NODE_RUNTIME_RUNNER_ARCHIVE = "codex-agent-node-runtime-evidence-runner.zip"
internal const val NODE_WASM_RUNTIME_RUNNER_ARCHIVE = "codex-agent-node-wasm-runtime-evidence-runner.zip"

fun desktopRuntimeEvidenceFileName(target: String) = "desktop-runtime-$target.json"
fun jvmRuntimeEvidenceFileName(target: String) = "jvm-runtime-$target.json"
fun nodeRuntimeEvidenceFileName(target: String, runtimeBackend: String = NODE_RUNTIME_JS_BACKEND): String {
    check(runtimeBackend in setOf(NODE_RUNTIME_JS_BACKEND, NODE_RUNTIME_WASM_BACKEND)) {
        "Unsupported Node runtime backend: $runtimeBackend"
    }
    return if (runtimeBackend == NODE_RUNTIME_JS_BACKEND) {
        "node-runtime-$target.json"
    } else {
        "node-wasm-runtime-$target.json"
    }
}

data class DesktopCodexManifest(
    val version: String,
    val releaseTag: String,
    val distributions: List<DesktopCodexDistributionSpec>,
)

data class DesktopCodexDistributionSpec(
    val target: String,
    val classifier: String,
    val asset: String,
    val archiveSha256: String,
    val archiveEntry: String,
    val binarySha256: String,
    val executableName: String,
    val supervisorExecutableName: String,
)

fun readDesktopCodexManifest(file: File): DesktopCodexManifest {
    val root = releaseJson.parseToJsonElement(
        runProductPythonModule("runtime_evidence", listOf("inspect-manifest", "--manifest", file.absolutePath)),
    ).jsonObject
    check(root.keys == setOf("schemaVersion", "version", "releaseTag", "distributions") &&
        root.releaseInt("schemaVersion") == 1) {
        "Desktop distribution projection schema is invalid"
    }
    val distributions = (root["distributions"] as? JsonArray
        ?: error("Desktop distribution projection is missing distributions")).map { value ->
        val record = value as? JsonObject ?: error("Desktop distribution projection record is invalid")
        check(record.keys == setOf(
            "target", "classifier", "asset", "archiveSha256", "archiveEntry", "binarySha256",
            "executableName", "supervisorExecutableName",
        )) { "Desktop distribution projection record schema is invalid" }
        DesktopCodexDistributionSpec(
            record.runtimeEvidenceString("target"),
            record.runtimeEvidenceString("classifier"),
            record.runtimeEvidenceString("asset"),
            record.runtimeEvidenceString("archiveSha256"),
            record.runtimeEvidenceString("archiveEntry"),
            record.runtimeEvidenceString("binarySha256"),
            record.runtimeEvidenceString("executableName"),
            record.runtimeEvidenceString("supervisorExecutableName"),
        )
    }
    return DesktopCodexManifest(
        root.runtimeEvidenceString("version"),
        root.runtimeEvidenceString("releaseTag"),
        distributions,
    )
}

internal fun validateDesktopRuntimeEvidence(
    files: List<File>,
    expectedCommits: Map<String, String>,
    version: String? = null,
    mavenInventory: File? = null,
    distributionManifest: File? = null,
    classifierArchives: List<File> = emptyList(),
): List<String> = validateRuntimeEvidenceCommand(buildList {
    add("validate-desktop")
    addRuntimeEvidenceInputs(files, expectedCommits)
    if (version != null || mavenInventory != null) {
        check(version != null && mavenInventory != null) {
            "Desktop Runtime validation version and Maven inventory must be supplied together"
        }
        addAll(listOf("--version", version, "--maven-inventory", mavenInventory.absolutePath))
    }
    distributionManifest?.let { addAll(listOf("--manifest", it.absolutePath)) }
    classifierArchives.forEach { addAll(listOf("--classifier", it.absolutePath)) }
})

internal fun validateJvmRuntimeEvidence(
    files: List<File>,
    expectedCommits: Map<String, String>,
    distributionManifest: File,
    classifierArchives: List<File>,
    compiledJvmTestRuntime: File,
): List<String> = validateRuntimeEvidenceCommand(buildList {
    add("validate-jvm")
    addRuntimeEvidenceInputs(files, expectedCommits)
    addAll(listOf("--manifest", distributionManifest.absolutePath))
    classifierArchives.forEach { addAll(listOf("--classifier", it.absolutePath)) }
    addAll(listOf("--runner", compiledJvmTestRuntime.absolutePath))
})

internal fun validateNodeRuntimeEvidence(
    files: List<File>,
    expectedCommits: Map<String, String>,
    runtimeBackend: String,
    distributionManifest: File,
    classifierArchives: List<File>,
    compiledNodeTestRuntime: File,
): List<String> = validateRuntimeEvidenceCommand(buildList {
    add("validate-node")
    addRuntimeEvidenceInputs(files, expectedCommits)
    addAll(listOf("--backend", runtimeBackend, "--manifest", distributionManifest.absolutePath))
    classifierArchives.forEach { addAll(listOf("--classifier", it.absolutePath)) }
    addAll(listOf("--runner", compiledNodeTestRuntime.absolutePath))
})

private fun MutableList<String>.addRuntimeEvidenceInputs(
    files: List<File>,
    expectedCommits: Map<String, String>,
) {
    expectedCommits.toSortedMap().forEach { (target, commit) ->
        addAll(listOf("--expected-commit", "$target=$commit"))
    }
    files.sortedBy(File::getName).forEach { addAll(listOf("--evidence", it.absolutePath)) }
}

private fun validateRuntimeEvidenceCommand(arguments: List<String>): List<String> = runCatching {
    val result = releaseJson.parseToJsonElement(runProductPythonModule("runtime_evidence", arguments)).jsonObject
    check(result.keys == setOf("schemaVersion", "command", "result") &&
        result.releaseInt("schemaVersion") == 1 && result.releaseString("result") == "passed") {
        "Runtime evidence verifier result schema is invalid"
    }
}.exceptionOrNull()?.let { listOf(it.message ?: "Runtime evidence verification failed") }.orEmpty()

private fun JsonObject.runtimeEvidenceString(name: String): String {
    val primitive = this[name] as? JsonPrimitive ?: error("Desktop distribution $name must be a string")
    check(primitive.isString) { "Desktop distribution $name must be a string" }
    return primitive.content
}
