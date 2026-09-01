import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

data class CrossLanguageCAbiTargetSpec(
    val target: String,
    val classifier: String,
    val runnerOs: String,
    val runnerArch: String,
    val format: String,
    val architecture: String,
    val libraryPath: String,
    val loaderIdentity: String,
    val importLibraryPaths: List<String> = emptyList(),
)

private data class CrossLanguageCAbiClientTarget(
    val spec: CrossLanguageCAbiTargetSpec,
    val component: String,
    val proofId: String,
    val evidenceFileName: String,
    val archiveFileNameTemplate: String,
    val versionIdentity: String,
    val requiredToolIds: Set<String>,
)

private data class CrossLanguageCAbiHostMapping(
    val osContains: String,
    val architectures: Set<String>,
    val target: String,
)

private data class CrossLanguageCAbiClientCatalog(
    val current: String,
    val minimum: String,
    val encoded: String,
    val publicSymbolCount: Int,
    val headerPath: String,
    val packageManifestPath: String,
    val stagedEvidencePath: String,
    val strictConsumers: Set<String>,
    val compileOnlyConsumers: Set<String>,
    val gnuConsumers: Set<String>,
    val hostMappings: List<CrossLanguageCAbiHostMapping>,
    val targets: Map<String, CrossLanguageCAbiClientTarget>,
)

private val cAbiClientJson = Json

private val crossLanguageCAbiClientCatalog: CrossLanguageCAbiClientCatalog by lazy {
    readCrossLanguageCAbiClientCatalog(runProductPythonModule("c_abi", listOf("describe")))
}

val CROSS_LANGUAGE_C_ABI_CURRENT: String get() = crossLanguageCAbiClientCatalog.current
val CROSS_LANGUAGE_C_ABI_MINIMUM: String get() = crossLanguageCAbiClientCatalog.minimum
val CROSS_LANGUAGE_C_ABI_ENCODED: String get() = crossLanguageCAbiClientCatalog.encoded
val CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT: Int get() = crossLanguageCAbiClientCatalog.publicSymbolCount
internal val C_ABI_PACKAGE_MANIFEST: String get() = crossLanguageCAbiClientCatalog.packageManifestPath
internal val C_ABI_HEADER_PATH: String get() = crossLanguageCAbiClientCatalog.headerPath
internal val C_ABI_GNU_CONSUMERS: Set<String> get() = crossLanguageCAbiClientCatalog.gnuConsumers

val crossLanguageCAbiTargetSpecs: Map<String, CrossLanguageCAbiTargetSpec> get() =
    crossLanguageCAbiClientCatalog.targets.mapValues { it.value.spec }
val crossLanguageCAbiCompileOnlyConsumers: Set<String> get() =
    crossLanguageCAbiClientCatalog.compileOnlyConsumers
val crossLanguageCAbiStrictConsumers: Set<String> get() = crossLanguageCAbiClientCatalog.strictConsumers
val crossLanguageCAbiPackageProofIds: Map<String, String> get() =
    crossLanguageCAbiClientCatalog.targets.mapValues { it.value.proofId }

fun crossLanguageCAbiHostTarget(osName: String, osArch: String): String? {
    val os = osName.lowercase()
    val arch = osArch.lowercase()
    return crossLanguageCAbiClientCatalog.hostMappings.firstOrNull { mapping ->
        mapping.osContains in os && arch in mapping.architectures
    }?.target
}

fun crossLanguageCAbiArchiveFileName(libraryVersion: String, target: String): String {
    val template = crossLanguageCAbiClientTarget(target).archiveFileNameTemplate
    return template.replace("{libraryVersion}", libraryVersion)
}

fun crossLanguageCAbiPackageEvidenceFileName(target: String): String =
    crossLanguageCAbiClientTarget(target).evidenceFileName

fun crossLanguageCAbiRequiredToolIds(target: String): Set<String> =
    crossLanguageCAbiClientTarget(target).requiredToolIds

internal fun CrossLanguageCAbiTargetSpec.expectedVersionIdentity(): String =
    crossLanguageCAbiClientTarget(target).also { client ->
        check(client.spec == this) { "C ABI package target specification mismatch: $target" }
    }.versionIdentity

internal fun CrossLanguageCAbiTargetSpec.requiredToolIds(): Set<String> =
    crossLanguageCAbiClientTarget(target).also { client ->
        check(client.spec == this) { "C ABI package target specification mismatch: $target" }
    }.requiredToolIds

fun portableVerifyCrossLanguageCAbiPackageEvidence(
    target: String,
    libraryVersion: String,
    producerCommit: String,
    producerTree: String,
    archive: File,
    evidence: File,
    reviewedHeader: File,
    license: File,
    notice: File,
    exportPolicy: File,
    consumerSources: List<File>,
): JsonObject = withPortableVerifiedCrossLanguageCAbiPackageEvidence(
    target,
    libraryVersion,
    producerCommit,
    producerTree,
    archive,
    evidence,
    reviewedHeader,
    license,
    notice,
    exportPolicy,
    consumerSources,
) { report, _, _ -> report }

internal fun <T> withPortableVerifiedCrossLanguageCAbiPackageEvidence(
    target: String,
    libraryVersion: String,
    producerCommit: String,
    producerTree: String,
    archive: File,
    evidence: File,
    reviewedHeader: File,
    license: File,
    notice: File,
    exportPolicy: File,
    consumerSources: List<File>,
    consume: (JsonObject, File, ByteArray) -> T,
): T {
    crossLanguageCAbiClientTarget(target)
    val temporary = Files.createTempDirectory("codex-agent-c-abi-client-$target-").toFile()
    return try {
        val verifiedRoot = temporary.resolve("sdk")
        val arguments = buildList {
            add("portable-verify")
            add("--target"); add(target)
            add("--library-version"); add(libraryVersion)
            add("--producer-commit"); add(producerCommit)
            add("--producer-tree"); add(producerTree)
            add("--archive"); add(archive.absolutePath)
            add("--evidence"); add(evidence.absolutePath)
            add("--reviewed-header"); add(reviewedHeader.absolutePath)
            add("--license"); add(license.absolutePath)
            add("--notice"); add(notice.absolutePath)
            add("--export-policy"); add(exportPolicy.absolutePath)
            consumerSources.sortedBy(File::getName).forEach { source ->
                add("--consumer-source"); add(source.absolutePath)
            }
            add("--output-directory"); add(verifiedRoot.absolutePath)
        }
        val report = parseCanonicalCAbiClientObject(
            runProductPythonModule("c_abi", arguments),
            "C ABI portable verification output",
        )
        check(verifiedRoot.isDirectory && !Files.isSymbolicLink(verifiedRoot.toPath())) {
            "Verified C ABI SDK directory is missing or symbolic: $target"
        }
        val stagedEvidence = verifiedRoot.resolve(crossLanguageCAbiClientCatalog.stagedEvidencePath)
        check(stagedEvidence.isFile && !Files.isSymbolicLink(stagedEvidence.toPath()) &&
            Files.mismatch(evidence.toPath(), stagedEvidence.toPath()) == -1L) {
            "Verified C ABI SDK evidence bytes differ: $target"
        }
        val evidenceBytes = stagedEvidence.readBytes()
        val immutableInventory = verifiedRegularFiles(verifiedRoot).mapValues { (_, file) -> file.releaseDigest() }
        val result = consume(report, verifiedRoot, evidenceBytes)
        check(verifiedRegularFiles(verifiedRoot).mapValues { (_, file) -> file.releaseDigest() } == immutableInventory) {
            "Verified C ABI SDK was mutated by its consumer: $target"
        }
        result
    } finally {
        temporary.deleteRecursively()
    }
}

internal fun checkIdentity(version: String, commit: String, tree: String) {
    check(version.matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?"))) {
        "C ABI package library version is invalid"
    }
    check(commit.matches(Regex("[0-9a-f]{40}"))) { "C ABI package producer commit is not immutable" }
    check(tree.matches(Regex("[0-9a-f]{40}"))) { "C ABI package producer tree is not immutable" }
}

internal fun regularCAbiFile(file: File): Boolean =
    file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L

internal fun JsonObject.strictString(name: String): String {
    val primitive = getValue(name).jsonPrimitive
    check(primitive.isString) { "C ABI evidence field is not a string: $name" }
    return primitive.content
}

internal fun JsonObject.strictSha256(name: String): String = strictString(name).also {
    check(it.matches(Regex("[0-9a-f]{64}"))) { "C ABI evidence SHA-256 is invalid: $name" }
}

internal fun JsonObject.strictInt(name: String): Int {
    val primitive = getValue(name).jsonPrimitive
    check(!primitive.isString) { "C ABI evidence field is not an integer: $name" }
    return primitive.content.toInt()
}

internal fun JsonObject.strictArray(name: String): JsonArray = getValue(name).jsonArray

private fun crossLanguageCAbiClientTarget(target: String): CrossLanguageCAbiClientTarget =
    crossLanguageCAbiClientCatalog.targets[target] ?: error("Unsupported C ABI package target: $target")

private fun readCrossLanguageCAbiClientCatalog(contents: String): CrossLanguageCAbiClientCatalog {
    val root = parseCanonicalCAbiClientObject(contents, "C ABI catalog")
    root.requireCAbiClientKeys(setOf("schemaVersion", "abi", "paths", "consumers", "hostMappings", "targets"))
    check(root.cAbiClientInt("schemaVersion") == 1) { "C ABI catalog schema version mismatch" }

    val abi = root.cAbiClientObject("abi").also {
        it.requireCAbiClientKeys(setOf("current", "minimum", "encoded", "publicSymbolCount"))
    }
    val paths = root.cAbiClientObject("paths").also {
        it.requireCAbiClientKeys(setOf("header", "packageManifest", "stagedEvidence"))
    }
    val consumers = root.cAbiClientObject("consumers").also {
        it.requireCAbiClientKeys(setOf("strict", "compileOnly", "gnu"))
    }
    val strictConsumers = consumers.cAbiClientSortedStrings("strict")
    val compileOnlyConsumers = consumers.cAbiClientSortedStrings("compileOnly")
    val gnuConsumers = consumers.cAbiClientSortedStrings("gnu")
    check(strictConsumers.isNotEmpty() && compileOnlyConsumers.all(strictConsumers::contains) &&
        gnuConsumers.all(strictConsumers::contains)) {
        "C ABI catalog consumer inventory mismatch"
    }

    val hostMappings = root.cAbiClientArray("hostMappings").map { value ->
        val mapping = value.jsonObject.also {
            it.requireCAbiClientKeys(setOf("osContains", "architectures", "target"))
        }
        CrossLanguageCAbiHostMapping(
            mapping.cAbiClientString("osContains").also(::requireCAbiClientString),
            mapping.cAbiClientSortedStrings("architectures"),
            mapping.cAbiClientString("target").also(::requireCAbiClientString),
        )
    }
    val targetRecords = root.cAbiClientArray("targets")
    val targets = targetRecords.associate { value ->
        val record = value.jsonObject.also {
            it.requireCAbiClientKeys(setOf(
                "target", "component", "classifier", "runnerOs", "runnerArch", "format", "architecture",
                "libraryPath", "loaderIdentity", "importLibraryPaths", "proofId", "evidenceFileName",
                "archiveFileNameTemplate", "versionIdentity", "requiredToolIds",
            ))
        }
        val target = record.cAbiClientString("target").also(::requireCAbiClientString)
        target to CrossLanguageCAbiClientTarget(
            CrossLanguageCAbiTargetSpec(
                target,
                record.cAbiClientString("classifier").also(::requireCAbiClientString),
                record.cAbiClientString("runnerOs").also(::requireCAbiClientString),
                record.cAbiClientString("runnerArch").also(::requireCAbiClientString),
                record.cAbiClientString("format").also(::requireCAbiClientString),
                record.cAbiClientString("architecture").also(::requireCAbiClientString),
                record.cAbiClientString("libraryPath").also(::requireCAbiClientString),
                record.cAbiClientString("loaderIdentity").also(::requireCAbiClientString),
                record.cAbiClientStrings("importLibraryPaths", requireSorted = false),
            ),
            record.cAbiClientString("component").also(::requireCAbiClientString),
            record.cAbiClientString("proofId").also(::requireCAbiClientString),
            record.cAbiClientString("evidenceFileName").also(::requireCAbiClientString),
            record.cAbiClientString("archiveFileNameTemplate").also { template ->
                check(template.countOccurrences("{libraryVersion}") == 1) {
                    "C ABI catalog archive template mismatch: $target"
                }
            },
            record.cAbiClientString("versionIdentity").also(::requireCAbiClientString),
            record.cAbiClientSortedStrings("requiredToolIds"),
        )
    }
    check(targets.isNotEmpty() && targetRecords.size == targets.size &&
        targetRecords.map { it.jsonObject.cAbiClientString("target") } == targets.keys.sorted() &&
        hostMappings.size == targets.size && hostMappings.map { it.target }.toSet() == targets.keys) {
        "C ABI catalog target inventory mismatch"
    }
    return CrossLanguageCAbiClientCatalog(
        abi.cAbiClientString("current").also(::requireCAbiClientString),
        abi.cAbiClientString("minimum").also(::requireCAbiClientString),
        abi.cAbiClientString("encoded").also(::requireCAbiClientString),
        abi.cAbiClientInt("publicSymbolCount").also { check(it > 0) { "C ABI catalog symbol count is empty" } },
        paths.cAbiClientString("header").also(::requireCAbiClientString),
        paths.cAbiClientString("packageManifest").also(::requireCAbiClientString),
        paths.cAbiClientString("stagedEvidence").also(::requireCAbiClientString),
        strictConsumers,
        compileOnlyConsumers,
        gnuConsumers,
        hostMappings,
        targets.toSortedMap(),
    )
}

private fun parseCanonicalCAbiClientObject(contents: String, label: String): JsonObject {
    val value = cAbiClientJson.parseToJsonElement(contents)
    val canonical = cAbiClientJson.encodeToString(JsonElement.serializer(), value) + "\n"
    check(contents == canonical) { "$label is not canonical JSON" }
    return value.jsonObject
}

private fun JsonObject.requireCAbiClientKeys(expected: Set<String>) {
    check(keys == expected) {
        "C ABI catalog fields differ: missing=${(expected - keys).sorted()} extra=${(keys - expected).sorted()}"
    }
}

private fun JsonObject.cAbiClientObject(name: String): JsonObject = getValue(name).jsonObject
private fun JsonObject.cAbiClientArray(name: String): JsonArray = getValue(name).jsonArray

private fun JsonObject.cAbiClientString(name: String): String {
    val primitive = getValue(name).jsonPrimitive
    check(primitive.isString) { "C ABI catalog field is not a string: $name" }
    return primitive.content
}

private fun JsonObject.cAbiClientInt(name: String): Int {
    val primitive = getValue(name).jsonPrimitive
    check(!primitive.isString) { "C ABI catalog field is not an integer: $name" }
    return primitive.content.toInt()
}

private fun JsonObject.cAbiClientSortedStrings(name: String): Set<String> {
    return cAbiClientStrings(name, requireSorted = true).toCollection(linkedSetOf())
}

private fun JsonObject.cAbiClientStrings(name: String, requireSorted: Boolean): List<String> {
    val values = cAbiClientArray(name).map { value ->
        value.jsonPrimitive.also { primitive ->
            check(primitive.isString) { "C ABI catalog array contains a non-string: $name" }
        }.content.also(::requireCAbiClientString)
    }
    check((!requireSorted || values == values.sorted()) && values.size == values.distinct().size) {
        "C ABI catalog array ordering or uniqueness is invalid: $name"
    }
    return values
}

private fun requireCAbiClientString(value: String) {
    check(value.isNotBlank() && value.none { it == '\u0000' || it == '\n' || it == '\r' }) {
        "C ABI catalog contains an invalid string"
    }
}

private fun String.countOccurrences(value: String): Int = windowed(value.length).count { it == value }
