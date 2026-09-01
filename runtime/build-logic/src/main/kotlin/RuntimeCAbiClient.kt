import java.io.File
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import org.gradle.api.provider.ValueSource
import org.gradle.api.provider.ValueSourceParameters

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
    internal val versionIdentity: String,
    internal val toolIds: Set<String>,
    internal val proofId: String,
    internal val evidenceFileName: String,
    internal val archiveFileNameTemplate: String,
)

data class CrossLanguageCAbiPackageInput(
    val target: String,
    val classifier: String,
    val libraryVersion: String,
    val producerCommit: String,
    val producerTree: String,
    val reviewedHeader: File,
    val license: File,
    val notice: File,
    val library: File,
    val exportPolicy: File,
    val gnuImportLibrary: File? = null,
    val msvcImportLibrary: File? = null,
)

data class CrossLanguageCAbiPackageSnapshot(
    val target: String,
    val classifier: String,
    val archiveSha256: String,
    val headerSha256: String,
    val librarySha256: String,
    val publicSymbolsSha256: String,
    val members: Map<String, String>,
)

data class CrossLanguageCAbiConsumerProof(
    val source: String,
    val sourceSha256: String,
    val language: String,
    val compilerIdentitySha256: String,
    val compileOutputSha256: String,
    val artifactSha256: String,
    val linked: Boolean,
    val executed: Boolean,
    val exitCode: Int,
)

data class CrossLanguageCAbiEvidenceValues(
    val target: String,
    val classifier: String,
    val libraryVersion: String,
    val producerCommit: String,
    val producerTree: String,
    val runnerOs: String,
    val runnerArch: String,
    val archiveSha256: String,
    val headerSha256: String,
    val librarySha256: String,
    val publicSymbols: Set<String>,
    val publicSymbolVersions: Map<String, String>,
    val format: String,
    val architecture: String,
    val loaderIdentity: String,
    val versionIdentity: String,
    val importLibraries: Map<String, String>,
    val toolProofs: Map<String, String>,
    val consumers: List<CrossLanguageCAbiConsumerProof>,
    val gnuConsumers: List<CrossLanguageCAbiConsumerProof>,
)

data class CrossLanguageCAbiExportPolicy(
    val publicSymbols: Set<String>,
    val publicSymbolVersions: Map<String, String>,
)

data class RuntimeCAbiHostMapping(
    val osContains: String,
    val architectures: Set<String>,
    val target: String,
)

data class RuntimeCAbiCatalog(
    val current: String,
    val minimum: String,
    val encoded: String,
    val symbolCount: Int,
    val strictConsumers: Set<String>,
    val compileOnlyConsumers: Set<String>,
    val gnuConsumers: Set<String>,
    private val hostMappings: List<RuntimeCAbiHostMapping>,
    val targets: Map<String, CrossLanguageCAbiTargetSpec>,
) {
    fun hostTarget(osName: String, osArch: String): String? {
        val os = osName.lowercase()
        val arch = osArch.lowercase()
        return hostMappings.singleOrNull { it.osContains in os && arch in it.architectures }?.target
    }
}

abstract class RuntimeCAbiCatalogValueSource : ValueSource<String, ValueSourceParameters.None> {
    override fun obtain(): String = runRuntimeProductPythonModule("c_abi", listOf("describe"))
}

fun readRuntimeCAbiCatalog(output: String): RuntimeCAbiCatalog = parseRuntimeCAbiCatalog(output)

private val runtimeCAbiCatalog: RuntimeCAbiCatalog by lazy {
    parseRuntimeCAbiCatalog(runRuntimeProductPythonModule("c_abi", listOf("describe")))
}

val CROSS_LANGUAGE_C_ABI_CURRENT: String get() = runtimeCAbiCatalog.current
val CROSS_LANGUAGE_C_ABI_MINIMUM: String get() = runtimeCAbiCatalog.minimum
val CROSS_LANGUAGE_C_ABI_ENCODED: String get() = runtimeCAbiCatalog.encoded
val CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT: Int get() = runtimeCAbiCatalog.symbolCount

val crossLanguageCAbiTargetSpecs: Map<String, CrossLanguageCAbiTargetSpec>
    get() = runtimeCAbiCatalog.targets
val crossLanguageCAbiCompileOnlyConsumers: Set<String>
    get() = runtimeCAbiCatalog.compileOnlyConsumers
val crossLanguageCAbiStrictConsumers: Set<String>
    get() = runtimeCAbiCatalog.strictConsumers
val C_ABI_GNU_CONSUMERS: Set<String>
    get() = runtimeCAbiCatalog.gnuConsumers
val crossLanguageCAbiPackageProofIds: Map<String, String>
    get() = runtimeCAbiCatalog.targets.mapValues { (_, spec) -> spec.proofId }

fun crossLanguageCAbiHostTarget(osName: String, osArch: String): String? {
    return runtimeCAbiCatalog.hostTarget(osName, osArch)
}

fun crossLanguageCAbiArchiveFileName(libraryVersion: String, target: String): String =
    checkedCAbiTarget(target).archiveFileNameTemplate.replace("{libraryVersion}", libraryVersion)

fun crossLanguageCAbiPackageEvidenceFileName(target: String): String =
    checkedCAbiTarget(target).evidenceFileName

fun crossLanguageCAbiRequiredToolIds(target: String): Set<String> =
    checkedCAbiTarget(target).requiredToolIds()

fun describeCrossLanguageCAbiExportPolicy(
    exportPolicy: File,
    format: String,
): CrossLanguageCAbiExportPolicy {
    val root = parseRuntimeCAbiCanonicalObject(
        runRuntimeProductPythonModule(
            "c_abi",
            listOf(
                "describe-export-policy",
                "--export-policy", exportPolicy.absolutePath,
                "--format", format,
            ),
        ),
        "C ABI export policy",
    )
    root.requireKeys("schemaVersion", "format", "publicSymbols", "publicSymbolVersions")
    check(root.strictInt("schemaVersion") == 1 && root.strictString("format") == format) {
        "C ABI export policy identity mismatch"
    }
    val symbols = root.strictStringSet("publicSymbols")
    val versions = root.strictArray("publicSymbolVersions").mapIndexed { index, element ->
        val record = element as? JsonObject ?: error("C ABI publicSymbolVersions[$index] must be an object")
        record.requireKeys("symbol", "version")
        record.strictString("symbol") to record.strictString("version")
    }
    check(versions == versions.sortedBy { it.first } && versions.map { it.first }.distinct().size == versions.size) {
        "C ABI export policy version inventory is not sorted and unique"
    }
    return CrossLanguageCAbiExportPolicy(symbols, versions.toMap())
}

internal fun CrossLanguageCAbiTargetSpec.requiredToolIds(): Set<String> = toolIds

internal fun CrossLanguageCAbiTargetSpec.expectedVersionIdentity(): String = versionIdentity

internal fun checkedCAbiTarget(target: String, classifier: String? = null): CrossLanguageCAbiTargetSpec {
    val spec = runtimeCAbiCatalog.targets[target] ?: error("Unsupported C ABI package target: $target")
    check(classifier == null || classifier == spec.classifier) {
        "C ABI package target/classifier mismatch"
    }
    return spec
}

internal fun extractedCAbiPackageInput(
    spec: CrossLanguageCAbiTargetSpec,
    libraryVersion: String,
    producerCommit: String,
    producerTree: String,
    reviewedHeader: File,
    license: File,
    notice: File,
    exportPolicy: File,
    root: File,
) = CrossLanguageCAbiPackageInput(
    spec.target,
    spec.classifier,
    libraryVersion,
    producerCommit,
    producerTree,
    reviewedHeader,
    license,
    notice,
    root.resolve(spec.libraryPath),
    exportPolicy,
    spec.importLibraryPaths.getOrNull(0)?.let(root::resolve),
    spec.importLibraryPaths.getOrNull(1)?.let(root::resolve),
)

fun packageCrossLanguageCAbiSdk(
    input: CrossLanguageCAbiPackageInput,
    output: File,
): CrossLanguageCAbiPackageSnapshot {
    val result = runRuntimeProductPythonModule(
        "c_abi",
        listOf("package") + input.commandArguments() + listOf("--output", output.absolutePath),
    )
    return parseRuntimeCAbiPackageSnapshot(result)
}

fun inspectCrossLanguageCAbiPackage(
    archiveFile: File,
    expected: CrossLanguageCAbiPackageInput,
): CrossLanguageCAbiPackageSnapshot = parseRuntimeCAbiPackageSnapshot(
    runRuntimeProductPythonModule(
        "c_abi",
        listOf("inspect") + expected.commandArguments() + listOf("--archive", archiveFile.absolutePath),
    ),
)

fun inspectAndStageCrossLanguageCAbiPackage(
    archiveFile: File,
    target: String,
    classifier: String,
    libraryVersion: String,
    producerCommit: String,
    producerTree: String,
    reviewedHeader: File,
    license: File,
    notice: File,
    exportPolicy: File,
    outputDirectory: File,
): CrossLanguageCAbiPackageSnapshot = parseRuntimeCAbiPackageSnapshot(
    runRuntimeProductPythonModule(
        "c_abi",
        listOf(
            "inspect",
            "--target", target,
            "--classifier", classifier,
            "--library-version", libraryVersion,
            "--producer-commit", producerCommit,
            "--producer-tree", producerTree,
            "--reviewed-header", reviewedHeader.absolutePath,
            "--license", license.absolutePath,
            "--notice", notice.absolutePath,
            "--export-policy", exportPolicy.absolutePath,
            "--archive", archiveFile.absolutePath,
            "--output-directory", outputDirectory.absolutePath,
        ),
    ),
)

fun buildCrossLanguageCAbiPackageEvidence(
    values: CrossLanguageCAbiEvidenceValues,
    archive: File,
    expected: CrossLanguageCAbiPackageInput,
    consumerSources: List<File>,
    output: File,
): JsonObject = withRuntimeCAbiTemporaryDirectory("evidence-write") { temporary ->
    val valuesFile = temporary.resolve("values.json")
    valuesFile.writeText(canonicalRuntimeCAbiEvidenceValues(values).toString() + "\n")
    val canonicalOutput = runRuntimeProductPythonModule(
        "c_abi",
        listOf("evidence-write") + expected.commandArguments() + listOf(
            "--archive", archive.absolutePath,
            "--expected-runner-os", values.runnerOs,
            "--expected-runner-arch", values.runnerArch,
        ) + consumerSources.sortedBy(File::getName).flatMap {
            listOf("--consumer-source", it.absolutePath)
        } + listOf("--values", valuesFile.absolutePath, "--output", output.absolutePath),
    )
    check(regularCAbiFile(output)) { "C ABI package evidence output is missing" }
    parseRuntimeCAbiCanonicalObject(canonicalOutput, "C ABI package evidence")
}

fun verifyCrossLanguageCAbiPackageEvidence(
    evidence: File,
    archive: File,
    expected: CrossLanguageCAbiPackageInput,
    expectedRunnerOs: String,
    expectedRunnerArch: String,
    consumerSources: List<File>,
    verifiedEvidence: File,
): JsonObject {
    val output = runRuntimeProductPythonModule(
        "c_abi",
        listOf("evidence-verify") + expected.commandArguments() + listOf(
            "--archive", archive.absolutePath,
            "--expected-runner-os", expectedRunnerOs,
            "--expected-runner-arch", expectedRunnerArch,
        ) + consumerSources.sortedBy(File::getName).flatMap {
            listOf("--consumer-source", it.absolutePath)
        } + listOf("--evidence", evidence.absolutePath),
    )
    val report = parseRuntimeCAbiCanonicalObject(output, "C ABI package evidence")
    verifiedEvidence.atomicWriteRuntimeCAbiBytes(evidence.readBytes())
    return report
}

internal fun regularCAbiFile(file: File): Boolean =
    file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L

internal fun String.sha256(): String = encodeToByteArray().inputStream().releaseDigest()

internal val C_ABI_SYMBOL = Regex("(?<![A-Za-z0-9_])(_?codex_agent_[A-Za-z0-9_]+)(?![A-Za-z0-9_])")

private fun CrossLanguageCAbiPackageInput.commandArguments(): List<String> = buildList {
    addAll(listOf(
        "--target", target,
        "--classifier", classifier,
        "--library-version", libraryVersion,
        "--producer-commit", producerCommit,
        "--producer-tree", producerTree,
        "--reviewed-header", reviewedHeader.absolutePath,
        "--license", license.absolutePath,
        "--notice", notice.absolutePath,
        "--library", library.absolutePath,
        "--export-policy", exportPolicy.absolutePath,
    ))
    gnuImportLibrary?.let { addAll(listOf("--gnu-import-library", it.absolutePath)) }
    msvcImportLibrary?.let { addAll(listOf("--msvc-import-library", it.absolutePath)) }
}

private inline fun <T> withRuntimeCAbiTemporaryDirectory(label: String, action: (File) -> T): T {
    val temporary = Files.createTempDirectory("codex-agent-runtime-c-abi-$label-").toFile()
    return try {
        action(temporary)
    } finally {
        temporary.deleteRecursively()
    }
}

private fun File.atomicWriteRuntimeCAbiBytes(contents: ByteArray) {
    parentFile.mkdirs()
    val temporary = Files.createTempFile(parentFile.toPath(), ".$name-", ".tmp")
    try {
        Files.write(temporary, contents)
        try {
            Files.move(temporary, toPath(), ATOMIC_MOVE, REPLACE_EXISTING)
        } catch (_: AtomicMoveNotSupportedException) {
            Files.move(temporary, toPath(), REPLACE_EXISTING)
        }
    } finally {
        Files.deleteIfExists(temporary)
    }
}

private fun canonicalRuntimeCAbiEvidenceValues(values: CrossLanguageCAbiEvidenceValues): JsonObject = buildJsonObject {
    put("architecture", values.architecture)
    put("archiveSha256", values.archiveSha256)
    put("classifier", values.classifier)
    put("consumers", buildJsonArray {
        values.consumers.sortedBy(CrossLanguageCAbiConsumerProof::source).forEach { add(canonicalConsumerProof(it)) }
    })
    put("format", values.format)
    put("gnuConsumers", buildJsonArray {
        values.gnuConsumers.sortedBy(CrossLanguageCAbiConsumerProof::source).forEach { add(canonicalConsumerProof(it)) }
    })
    put("headerSha256", values.headerSha256)
    put("importLibraries", buildJsonArray {
        values.importLibraries.toSortedMap().forEach { (path, digest) ->
            add(buildJsonObject { put("path", path); put("sha256", digest) })
        }
    })
    put("librarySha256", values.librarySha256)
    put("libraryVersion", values.libraryVersion)
    put("loaderIdentity", values.loaderIdentity)
    put("producerCommit", values.producerCommit)
    put("producerTree", values.producerTree)
    put("publicSymbolVersions", buildJsonArray {
        values.publicSymbolVersions.toSortedMap().forEach { (symbol, version) ->
            add(buildJsonObject { put("symbol", symbol); put("version", version) })
        }
    })
    put("publicSymbols", buildJsonArray { values.publicSymbols.sorted().forEach { add(JsonPrimitive(it)) } })
    put("runnerArch", values.runnerArch)
    put("runnerOs", values.runnerOs)
    put("schemaVersion", 1)
    put("target", values.target)
    put("toolProofs", buildJsonArray {
        values.toolProofs.toSortedMap().forEach { (id, digest) ->
            add(buildJsonObject { put("id", id); put("outputSha256", digest) })
        }
    })
    put("versionIdentity", values.versionIdentity)
}

private fun canonicalConsumerProof(proof: CrossLanguageCAbiConsumerProof): JsonObject = buildJsonObject {
    put("artifactSha256", proof.artifactSha256)
    put("compileOutputSha256", proof.compileOutputSha256)
    put("compilerIdentitySha256", proof.compilerIdentitySha256)
    put("executed", proof.executed)
    put("exitCode", proof.exitCode)
    put("language", proof.language)
    put("linked", proof.linked)
    put("source", proof.source)
    put("sourceSha256", proof.sourceSha256)
}

private fun parseRuntimeCAbiCatalog(output: String): RuntimeCAbiCatalog {
    val root = parseRuntimeCAbiCanonicalObject(output, "C ABI catalog")
    root.requireKeys("schemaVersion", "abi", "paths", "consumers", "hostMappings", "targets")
    check(root.strictInt("schemaVersion") == 1) { "C ABI catalog schemaVersion must be 1" }
    val abi = root.strictObject("abi").also {
        it.requireKeys("current", "minimum", "encoded", "publicSymbolCount")
    }
    root.strictObject("paths").requireKeys("header", "packageManifest", "stagedEvidence")
    val consumers = root.strictObject("consumers").also {
        it.requireKeys("strict", "compileOnly", "gnu")
    }
    val mappings = root.strictArray("hostMappings").mapIndexed { index, element ->
        val record = element as? JsonObject ?: error("C ABI hostMappings[$index] must be an object")
        record.requireKeys("osContains", "architectures", "target")
        RuntimeCAbiHostMapping(
            record.strictString("osContains"),
            record.strictStringSet("architectures"),
            record.strictString("target"),
        )
    }
    val targetList = root.strictArray("targets").mapIndexed { index, element ->
        val record = element as? JsonObject ?: error("C ABI targets[$index] must be an object")
        record.requireKeys(
            "target", "component", "classifier", "runnerOs", "runnerArch", "format", "architecture",
            "libraryPath", "loaderIdentity", "importLibraryPaths", "proofId", "evidenceFileName",
            "archiveFileNameTemplate", "versionIdentity", "requiredToolIds",
        )
        CrossLanguageCAbiTargetSpec(
            record.strictString("target"),
            record.strictString("classifier"),
            record.strictString("runnerOs"),
            record.strictString("runnerArch"),
            record.strictString("format"),
            record.strictString("architecture"),
            record.strictString("libraryPath"),
            record.strictString("loaderIdentity"),
            record.strictStringList("importLibraryPaths"),
            record.strictString("versionIdentity"),
            record.strictStringSet("requiredToolIds"),
            record.strictString("proofId"),
            record.strictString("evidenceFileName"),
            record.strictString("archiveFileNameTemplate"),
        )
    }
    check(targetList.map(CrossLanguageCAbiTargetSpec::target).distinct().size == targetList.size) {
        "C ABI catalog target inventory contains duplicates"
    }
    return RuntimeCAbiCatalog(
        abi.strictString("current"),
        abi.strictString("minimum"),
        abi.strictString("encoded"),
        abi.strictInt("publicSymbolCount"),
        consumers.strictStringSet("strict"),
        consumers.strictStringSet("compileOnly"),
        consumers.strictStringSet("gnu"),
        mappings,
        targetList.associateBy(CrossLanguageCAbiTargetSpec::target),
    )
}

private fun parseRuntimeCAbiPackageSnapshot(output: String): CrossLanguageCAbiPackageSnapshot {
    val root = parseRuntimeCAbiCanonicalObject(output, "C ABI package snapshot")
    root.requireKeys(
        "schemaVersion", "target", "classifier", "archiveSha256", "headerSha256", "librarySha256",
        "publicSymbolsSha256", "members",
    )
    check(root.strictInt("schemaVersion") == 1) { "C ABI package snapshot schemaVersion must be 1" }
    val members = root.strictArray("members").mapIndexed { index, element ->
        val record = element as? JsonObject ?: error("C ABI package members[$index] must be an object")
        record.requireKeys("path", "sha256")
        record.strictString("path") to record.strictString("sha256")
    }
    check(members.map { it.first }.distinct().size == members.size) {
        "C ABI package snapshot members contain duplicates"
    }
    return CrossLanguageCAbiPackageSnapshot(
        root.strictString("target"),
        root.strictString("classifier"),
        root.strictString("archiveSha256"),
        root.strictString("headerSha256"),
        root.strictString("librarySha256"),
        root.strictString("publicSymbolsSha256"),
        members.toMap(),
    )
}

private fun parseRuntimeCAbiCanonicalObject(output: String, label: String): JsonObject {
    check(output.endsWith('\n') && output.count { it == '\n' } == 1 && '\r' !in output) {
        "$label must be one LF-terminated canonical JSON line"
    }
    val root = Json.parseToJsonElement(output) as? JsonObject ?: error("$label must be an object")
    check(root.toString() + "\n" == output) { "$label bytes are not canonical" }
    return root
}

private fun JsonObject.requireKeys(vararg expected: String) {
    check(keys == expected.toSet()) { "C ABI projection schema fields mismatch" }
}

private fun JsonObject.strictObject(name: String): JsonObject =
    getValue(name) as? JsonObject ?: error("C ABI projection $name must be an object")

private fun JsonObject.strictArray(name: String): JsonArray =
    getValue(name) as? JsonArray ?: error("C ABI projection $name must be an array")

private fun JsonObject.strictString(name: String): String {
    val value = getValue(name) as? JsonPrimitive ?: error("C ABI projection $name must be a string")
    check(value.isString) { "C ABI projection $name must be a string" }
    return value.contentOrNull ?: error("C ABI projection $name is missing")
}

private fun JsonObject.strictInt(name: String): Int {
    val value = getValue(name) as? JsonPrimitive ?: error("C ABI projection $name must be an integer")
    check(!value.isString) { "C ABI projection $name must be an integer" }
    return value.intOrNull ?: error("C ABI projection $name must be an integer")
}

private fun JsonObject.strictStringList(name: String): List<String> = strictArray(name).mapIndexed { index, element ->
    val primitive = element as? JsonPrimitive ?: error("C ABI projection $name[$index] must be a string")
    check(primitive.isString) { "C ABI projection $name[$index] must be a string" }
    primitive.contentOrNull ?: error("C ABI projection $name[$index] is missing")
}

private fun JsonObject.strictStringSet(name: String): Set<String> {
    val values = strictStringList(name)
    check(values == values.sorted() && values.distinct().size == values.size) {
        "C ABI projection $name must be sorted and unique"
    }
    return values.toSet()
}
