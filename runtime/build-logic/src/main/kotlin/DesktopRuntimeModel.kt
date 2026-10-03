import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

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
    val root = Json.parseToJsonElement(file.readText()).jsonObject
    fun kotlinx.serialization.json.JsonObject.string(name: String) = getValue(name).jsonPrimitive.content
    val distributions = root.getValue("distributions").jsonArray.map { value ->
        val entry = value.jsonObject
        DesktopCodexDistributionSpec(
            target = entry.string("target"),
            classifier = entry.string("classifier"),
            asset = entry.string("asset"),
            archiveSha256 = entry.string("archiveSha256"),
            archiveEntry = entry.string("archiveEntry"),
            binarySha256 = entry.string("binarySha256"),
            executableName = entry.string("executableName"),
            supervisorExecutableName = entry.string("supervisorExecutableName"),
        )
    }
    val manifest = DesktopCodexManifest(root.string("version"), root.string("releaseTag"), distributions)
    check(manifest.releaseTag == "rust-v${manifest.version}") { "Desktop release tag/version mismatch" }
    check(distributions.size == 5 && distributions.map { it.target }.toSet().size == 5) {
        "Desktop distribution manifest must contain five unique targets"
    }
    check(distributions.map { it.classifier }.toSet().size == 5) {
        "Desktop distribution classifiers must be unique"
    }
    distributions.forEach { distribution ->
        check(distribution.archiveSha256.matches(Regex("[0-9a-f]{64}"))) {
            "${distribution.target} archive SHA-256 is invalid"
        }
        check(distribution.binarySha256.matches(Regex("[0-9a-f]{64}"))) {
            "${distribution.target} binary SHA-256 is invalid"
        }
        check(distribution.archiveEntry == File(distribution.archiveEntry).name) {
            "${distribution.target} archive entry must be at the archive root"
        }
        check(distribution.supervisorExecutableName == File(distribution.supervisorExecutableName).name) {
            "${distribution.target} supervisor executable must be at the archive root"
        }
    }
    return manifest
}
