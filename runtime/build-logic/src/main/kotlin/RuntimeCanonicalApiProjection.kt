import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import org.gradle.process.ExecOperations

internal data class RuntimeCanonicalApiIdentity(
    val apiReportSha256: String,
    val coverageReceiptSha256: String,
)

internal data class RuntimeCanonicalApiProjection(
    val memberKeys: List<String>,
    val canonical: RuntimeCanonicalApiIdentity,
    val targetSha256: Map<String, String>,
)

internal fun verifiedRuntimeCanonicalApiProjection(
    processes: ExecOperations,
    repositoryRoot: File,
    contractDirectory: File,
    publicKey: File,
    contractVersion: String,
    requiredComponent: String,
): RuntimeCanonicalApiProjection {
    val trustDomain = if (System.getenv("GITHUB_ACTIONS") == "true") "release" else "development"
    val command = mutableListOf(
        "python3", "-m", "ci.products.contract", "verify-directory",
        "--directory", contractDirectory.absolutePath,
        "--public-key", publicKey.absolutePath,
        "--expected-trust-domain", trustDomain,
        "--expected-contract-version", contractVersion,
        "--required-component", "common",
        "--required-component", requiredComponent,
        "--print-canonical-api",
    )
    if (trustDomain == "release") {
        command += listOf(
            "--keyring", repositoryRoot.resolve("gradle/release/product-signing-keys.json").absolutePath,
            "--keys-directory", repositoryRoot.resolve("gradle/release/keys").absolutePath,
        )
    }
    val root = releaseJson.parseToJsonElement(
        processes.captureRuntimeProcess(
            command,
            repositoryRoot,
            mapOf(
                "LC_ALL" to "C",
                "LANG" to "C",
                "PYTHONPATH" to repositoryRoot.absolutePath,
                "PYTHONDONTWRITEBYTECODE" to "1",
                "PYTHONNOUSERSITE" to "1",
                "PYTHONSAFEPATH" to "1",
            ),
            setOf("PYTHONHOME", "PYTHONINSPECT", "PYTHONSTARTUP"),
        ),
    ).jsonObject
    check(root.keys == setOf(
        "schemaVersion", "memberKeys", "canonical", "targetSha256", "compiledTestsSha256",
        "testResultsSha256", "coveredTestIds",
    ) && root.releaseInt("schemaVersion") == 1) {
        "Verified Contract canonical API projection schema is invalid"
    }
    val memberKeys = root.runtimeProjectionStrings("memberKeys")
    check(memberKeys.size == 556 && memberKeys == memberKeys.sorted() && memberKeys.size == memberKeys.toSet().size) {
        "Verified Contract canonical API projection is incomplete"
    }
    val canonical = root.releaseObject("canonical")
    check(canonical.keys == setOf("apiReportSha256", "coverageReceiptSha256")) {
        "Verified Contract canonical identity schema is invalid"
    }
    val targets = root.releaseObject("targetSha256")
    check(targets.keys == setOf("native", "wasm", "jvm-classes")) {
        "Verified Contract target identity is incomplete"
    }
    fun exactSha256(value: String, label: String) = value.also {
        check(it.matches(Regex("[0-9a-f]{64}"))) { "$label is not an exact SHA-256" }
    }
    exactSha256(root.releaseString("compiledTestsSha256"), "Compiled tests digest")
    exactSha256(root.releaseString("testResultsSha256"), "Test results digest")
    val covered = root.runtimeProjectionStrings("coveredTestIds")
    check(covered.isNotEmpty() && covered == covered.sorted() && covered.size == covered.toSet().size) {
        "Verified Contract covered-test inventory is invalid"
    }
    return RuntimeCanonicalApiProjection(
        memberKeys,
        RuntimeCanonicalApiIdentity(
            exactSha256(canonical.releaseString("apiReportSha256"), "API report digest"),
            exactSha256(canonical.releaseString("coverageReceiptSha256"), "Coverage receipt digest"),
        ),
        targets.mapValues { (kind, value) ->
            val primitive = value as? JsonPrimitive ?: error("Contract target $kind digest must be a string")
            check(primitive.isString) { "Contract target $kind digest must be a string" }
            exactSha256(primitive.contentOrNull ?: error("Missing Contract target $kind digest"), "$kind digest")
        },
    )
}

private fun JsonObject.runtimeProjectionStrings(name: String): List<String> =
    (getValue(name) as? JsonArray ?: error("Verified Contract $name must be an array")).map { value ->
        val primitive = value as? JsonPrimitive ?: error("Verified Contract $name must contain strings")
        check(primitive.isString) { "Verified Contract $name must contain strings" }
        primitive.content
    }

internal fun File.runtimeEvidenceTreeDigest(): String {
    check(isDirectory) { "Runtime evidence input directory is missing: $this" }
    val files = walkTopDown().onEnter { directory ->
        check(!Files.isSymbolicLink(directory.toPath())) { "Runtime evidence input contains a symlink: $directory" }
        true
    }.filter { file ->
        check(!Files.isSymbolicLink(file.toPath())) { "Runtime evidence input contains a symlink: $file" }
        file.isFile
    }.sortedBy { it.relativeTo(this).invariantSeparatorsPath }.toList()
    check(files.isNotEmpty()) { "Runtime evidence input directory is empty: $this" }
    val digest = MessageDigest.getInstance("SHA-256")
    files.forEach { file ->
        digest.update(file.relativeTo(this).invariantSeparatorsPath.encodeToByteArray())
        digest.update(byteArrayOf(0))
        file.inputStream().use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
    }
    return digest.digest().joinToString("") { "%02x".format(it.toInt() and 0xff) }
}
