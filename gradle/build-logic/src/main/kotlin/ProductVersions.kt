import java.io.File
import java.nio.charset.StandardCharsets.US_ASCII
import java.nio.file.Files
import org.gradle.api.Project

internal data class ProductVersions(
    val contract: String,
    val runtime: String,
    val sdk: String,
)

internal fun readProductVersions(repository: File): ProductVersions {
    val versions = repository.resolve("gradle/release/versions")
    return ProductVersions(
        contract = readProductVersion(versions.resolve("contract.txt")),
        runtime = readProductVersion(versions.resolve("runtime.txt")),
        sdk = readProductVersion(versions.resolve("sdk.txt")),
    )
}

internal fun readProductVersions(root: Project): ProductVersions {
    val repository = root.layout.projectDirectory.asFile
    listOf("contract.txt", "runtime.txt", "sdk.txt").forEach { name ->
        root.providers.fileContents(
            root.layout.projectDirectory.file("gradle/release/versions/$name"),
        ).asText.get()
    }
    return readProductVersions(repository)
}

internal fun applyProductVersions(root: Project, versions: ProductVersions) {
    check(root == root.rootProject) { "Product versions must be applied from the root project" }
    root.version = versions.sdk
    root.project(":codex-agent-core").version = versions.contract
    root.project(":codex-agent-runtime-desktop").version = versions.runtime
    listOf(":codex-agent-runtime-android", ":codex-agent-runtime-ios").forEach { path ->
        root.project(path).version = versions.sdk
    }
    root.extensions.extraProperties.apply {
        set("codexAgent.contractVersion", versions.contract)
        set("codexAgent.runtimeVersion", versions.runtime)
        set("codexAgent.sdkVersion", versions.sdk)
    }
}

private val STRICT_SEMVER = Regex(
    "(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)" +
        "(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)" +
        "(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?" +
        "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?",
)

internal fun readProductVersion(file: File): String {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "Product version authority is missing or unsafe: $file"
    }
    val bytes = file.readBytes()
    check(bytes.isNotEmpty() && bytes.last() == '\n'.code.toByte()) {
        "Product version authority must end with one LF: $file"
    }
    check(bytes.count { it == '\n'.code.toByte() } == 1) {
        "Product version authority must contain exactly one line: $file"
    }
    check(bytes.dropLast(1).all { it.toInt() and 0xff in 0x21..0x7e }) {
        "Product version authority must contain only visible ASCII SemVer bytes: $file"
    }
    val version = String(bytes, 0, bytes.size - 1, US_ASCII)
    check(STRICT_SEMVER.matches(version)) { "Invalid product SemVer in $file: $version" }
    check('+' !in version) {
        "Product version policy forbids build metadata in $file: $version"
    }
    return version
}

internal fun runtimeCompatibilityVersion(releaseVersion: String): String {
    check(STRICT_SEMVER.matches(releaseVersion) && '+' !in releaseVersion) {
        "Runtime compatibility requires canonical SemVer without build metadata: $releaseVersion"
    }
    val (major, minor) = releaseVersion.substringBefore('-').split('.').take(2)
    return "$major.$minor.0"
}
