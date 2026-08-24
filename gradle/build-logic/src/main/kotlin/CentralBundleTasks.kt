import java.io.BufferedOutputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.time.LocalDateTime
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

private val centralChecksumSuffixes = listOf(".md5", ".sha1", ".sha256", ".sha512")
internal const val CENTRAL_PORTAL_UPLOAD_LIMIT_BYTES = 1_000_000_000L
internal const val CENTRAL_MAIN_SHARD = "main"
internal val centralBundleShardNames = listOf(CENTRAL_MAIN_SHARD, "ios-arm64", "ios-simulator-arm64")

internal fun centralExclusion(file: File): String? = when {
    file.name == "maven-metadata.xml" || file.name.startsWith("maven-metadata.xml.") ->
        "repository metadata is not part of a Central deployment"
    centralChecksumSuffixes.any { file.name.endsWith(".asc$it") } ->
        "signature checksum is not part of a Central deployment"
    else -> null
}

internal fun buildCentralBundles(
    repository: File,
    mavenInventory: File,
    outputDirectory: File,
    version: String,
    report: File,
    maximumBytes: Long = CENTRAL_PORTAL_UPLOAD_LIMIT_BYTES,
): List<File> {
    check(repository.isDirectory) { "Maven staging repository is missing" }
    check(mavenInventory.isFile) { "Maven inventory is missing" }
    val files = repository.walkTopDown().filter(File::isFile)
        .sortedBy { it.relativeTo(repository).invariantSeparatorsPath }
        .toList()
    check(files.isNotEmpty()) { "Maven staging repository is empty" }
    val included = files.filter { centralExclusion(it) == null }
    check(included.isNotEmpty()) { "Central deployment bundles would be empty" }
    val grouped = included.groupBy { centralBundleShard(it.relativeTo(repository).invariantSeparatorsPath) }
    check(grouped.keys == centralBundleShardNames.toSet()) { "Central deployment shard set is incomplete" }

    val bundles = centralBundleShardNames.map { shard ->
        val bundle = outputDirectory.resolve(centralBundleFileName(version, shard))
        val entries = writeCentralBundle(repository, grouped.getValue(shard), bundle)
        check(bundle.length() < maximumBytes) {
            "Central $shard bundle must remain below $maximumBytes bytes: ${bundle.length()}"
        }
        Triple(shard, bundle, entries)
    }
    report.atomicWriteJson(buildJsonObject {
        put("schemaVersion", JsonPrimitive(3))
        put("artifactCount", JsonPrimitive(files.size))
        put("includedArtifactCount", JsonPrimitive(included.size))
        put("artifacts", buildJsonArray {
            files.forEach { file ->
                val relative = file.relativeTo(repository).invariantSeparatorsPath
                val exclusion = centralExclusion(file)
                add(buildJsonObject {
                    put("path", JsonPrimitive(relative))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                    put("included", JsonPrimitive(exclusion == null))
                    if (exclusion == null) put("shard", JsonPrimitive(centralBundleShard(relative)))
                    else put("exclusionReason", JsonPrimitive(exclusion))
                })
            }
        })
        put("bundles", buildJsonArray {
            bundles.forEach { (shard, bundle, entries) ->
                add(buildJsonObject {
                    put("shard", JsonPrimitive(shard))
                    bundle.releaseRecord().forEach { (key, value) -> put(key, value) }
                    put("entryCount", JsonPrimitive(entries.size))
                    put("entries", buildJsonArray { entries.forEach(::add) })
                })
            }
        })
        put("mavenInventorySha256", JsonPrimitive(mavenInventory.releaseDigest()))
        put("centralPortalUploadLimitBytes", JsonPrimitive(maximumBytes))
        put("allBundlesBelowCentralPortalUploadLimit", JsonPrimitive(true))
    })
    return bundles.map { it.second }
}

internal fun centralBundleFileName(version: String, shard: String) = "codex-agent-$version-central-$shard.zip"

internal fun centralBundleShard(relative: String): String {
    val group = CodexAgentBuild.MAVEN_GROUP.replace('.', '/')
    return when {
        relative.startsWith("$group/codex-agent-runtime-ios-iosarm64/") -> "ios-arm64"
        relative.startsWith("$group/codex-agent-runtime-ios-iossimulatorarm64/") -> "ios-simulator-arm64"
        else -> CENTRAL_MAIN_SHARD
    }
}

private fun writeCentralBundle(repository: File, included: List<File>, bundle: File): List<JsonObject> {
    val canonicalRepository = repository.canonicalFile
    check(!bundle.canonicalFile.toPath().startsWith(canonicalRepository.toPath())) {
        "Central output bundle must be outside the staged repository"
    }
    bundle.parentFile.mkdirs()
    val temporary = Files.createTempFile(bundle.parentFile.toPath(), ".${bundle.name}-", ".tmp").toFile()
    ZipOutputStream(BufferedOutputStream(temporary.outputStream())).use { output ->
        output.setLevel(Deflater.BEST_SPEED)
        included.forEach { file ->
            val relative = file.relativeTo(repository).invariantSeparatorsPath
            val entry = ZipEntry(relative).apply { setTimeLocal(LocalDateTime.of(1980, 1, 1, 0, 0)) }
            output.putNextEntry(entry)
            file.inputStream().use { it.copyTo(output) }
            output.closeEntry()
        }
    }
    Files.move(temporary.toPath(), bundle.toPath(), REPLACE_EXISTING)
    return ZipFile(bundle).use { archive ->
        val values = mutableListOf<java.util.zip.ZipEntry>()
        val enumeration = archive.entries()
        while (enumeration.hasMoreElements()) values += enumeration.nextElement()
        values.filterNot { it.isDirectory }.map { entry ->
            buildJsonObject {
                put("path", JsonPrimitive(entry.name))
                put("bytes", JsonPrimitive(entry.size))
                put("compressedBytes", JsonPrimitive(entry.compressedSize))
                put("crc32", JsonPrimitive("%08x".format(entry.crc)))
            }
        }
    }
}
