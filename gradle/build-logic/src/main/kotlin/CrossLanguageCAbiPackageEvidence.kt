import java.io.BufferedOutputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.time.LocalDateTime
import java.util.concurrent.TimeUnit
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

const val CROSS_LANGUAGE_C_ABI_CURRENT = "1.12"
const val CROSS_LANGUAGE_C_ABI_MINIMUM = "1.0"
const val CROSS_LANGUAGE_C_ABI_ENCODED = "0x010c0000"
const val CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT = 777

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

val crossLanguageCAbiTargetSpecs: Map<String, CrossLanguageCAbiTargetSpec> = listOf(
    CrossLanguageCAbiTargetSpec(
        "macosArm64", "c-abi-macos-arm64", "macOS", "ARM64", "mach-o", "arm64",
        "lib/libcodex_agent.dylib", "@rpath/libcodex_agent.dylib",
    ),
    CrossLanguageCAbiTargetSpec(
        "macosX64", "c-abi-macos-x64", "macOS", "X64", "mach-o", "x86_64",
        "lib/libcodex_agent.dylib", "@rpath/libcodex_agent.dylib",
    ),
    CrossLanguageCAbiTargetSpec(
        "linuxArm64", "c-abi-linux-arm64", "Linux", "ARM64", "elf", "aarch64",
        "lib/libcodex_agent.so", "libcodex_agent.so.1",
    ),
    CrossLanguageCAbiTargetSpec(
        "linuxX64", "c-abi-linux-x64", "Linux", "X64", "elf", "x86_64",
        "lib/libcodex_agent.so", "libcodex_agent.so.1",
    ),
    CrossLanguageCAbiTargetSpec(
        "mingwX64", "c-abi-windows-x64", "Windows", "X64", "pe", "x86_64",
        "bin/codex_agent.dll", "codex_agent.dll",
        listOf("lib/libcodex_agent.dll.a", "lib/codex_agent.lib"),
    ),
).associateBy(CrossLanguageCAbiTargetSpec::target)

fun crossLanguageCAbiHostTarget(osName: String, osArch: String): String? {
    val os = osName.lowercase()
    val arch = osArch.lowercase()
    return when {
        "mac" in os && arch in setOf("aarch64", "arm64") -> "macosArm64"
        "mac" in os && arch in setOf("amd64", "x86_64") -> "macosX64"
        "linux" in os && arch in setOf("aarch64", "arm64") -> "linuxArm64"
        "linux" in os && arch in setOf("amd64", "x86_64") -> "linuxX64"
        "windows" in os && arch in setOf("amd64", "x86_64") -> "mingwX64"
        else -> null
    }
}

val crossLanguageCAbiCompileOnlyConsumers: Set<String> = setOf("codex_agent_lifecycle_compile.cpp")
val crossLanguageCAbiStrictConsumers: Set<String> = sortedSetOf(
    "codex_agent_abi_smoke.c",
    "codex_agent_authentication_configuration_values_compile.c",
    "codex_agent_configuration_values_compile.c",
    "codex_agent_conversation_aggregate_values_compile.c",
    "codex_agent_conversation_values_compile.c",
    "codex_agent_elicitation_behavior_values_compile.c",
    "codex_agent_elicitation_interaction_values_compile.c",
    "codex_agent_form_hook_values_compile.c",
    "codex_agent_header_smoke.cpp",
    "codex_agent_hook_catalog_values_compile.c",
    "codex_agent_integration_mcp_values_compile.c",
    "codex_agent_integration_state_values_compile.c",
    "codex_agent_integration_values_compile.c",
    "codex_agent_interaction_identity_compile.c",
    "codex_agent_invocation_auth_values_compile.c",
    "codex_agent_lifecycle_compile.c",
    "codex_agent_lifecycle_compile.cpp",
    "codex_agent_list_leaf_values_compile.c",
    "codex_agent_mcp_server_configuration_values_compile.c",
    "codex_agent_mcp_server_values_compile.c",
    "codex_agent_mcp_transport_values_compile.c",
    "codex_agent_ordinary_enums_compile.c",
    "codex_agent_progress_list_values_compile.c",
    "codex_agent_resource_list_values_compile.c",
    "codex_agent_resource_values_compile.c",
    "codex_agent_root_value_accessors_compile.c",
    "codex_agent_sealed_base_property_values_compile.c",
    "codex_agent_service_handles_compile.c",
    "codex_agent_state_flows_compile.c",
    "codex_agent_suspend_operations_compile.c",
)

val crossLanguageCAbiPackageProofIds: Map<String, String> = crossLanguageCAbiTargetSpecs.mapValues { (_, spec) ->
    "c-abi-package-${spec.classifier.removePrefix("c-abi-")}"
}

fun crossLanguageCAbiArchiveFileName(libraryVersion: String, target: String): String {
    val spec = crossLanguageCAbiTargetSpecs[target] ?: error("Unsupported C ABI package target: $target")
    return "codex-agent-runtime-desktop-$libraryVersion-${spec.classifier}.zip"
}

fun crossLanguageCAbiPackageEvidenceFileName(target: String): String {
    val proofId = crossLanguageCAbiPackageProofIds[target] ?: error("Unsupported C ABI package target: $target")
    return "$proofId.json"
}

fun crossLanguageCAbiRequiredToolIds(target: String): Set<String> =
    (crossLanguageCAbiTargetSpecs[target] ?: error("Unsupported C ABI package target: $target")).requiredToolIds()

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

fun crossLanguageCAbiExpectedSymbols(file: File): Set<String> {
    check(regularCAbiFile(file)) { "C ABI export policy is missing or symbolic: $file" }
    val symbols = C_ABI_SYMBOL.findAll(file.readText()).map { match ->
        match.groupValues[1].removePrefix("_")
    }.toCollection(sortedSetOf())
    check(symbols.size == CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT) {
        "C ABI export policy must contain exactly $CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT symbols, found ${symbols.size}"
    }
    return symbols
}

fun crossLanguageCAbiLinuxSymbolVersions(file: File): Map<String, String> {
    check(regularCAbiFile(file)) { "C ABI Linux export policy is missing or symbolic: $file" }
    var node: String? = null
    val assignments = linkedMapOf<String, String>()
    file.readLines().forEach { line ->
        val trimmed = line.trim()
        LINUX_VERSION_NODE.matchEntire(trimmed)?.let { match ->
            check(node == null) { "Nested C ABI Linux version node" }
            node = match.groupValues[1]
            return@forEach
        }
        if (trimmed.startsWith("}")) node = null
        val symbol = LINUX_VERSION_SYMBOL.matchEntire(trimmed)?.groupValues?.get(1)
        if (symbol != null) {
            val version = checkNotNull(node) { "C ABI Linux symbol is outside a version node: $symbol" }
            check(assignments.put(symbol, version) == null) { "Duplicate C ABI Linux symbol assignment: $symbol" }
        }
    }
    check(assignments.size == CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT &&
        assignments.keys == crossLanguageCAbiExpectedSymbols(file) &&
        assignments.values.toSet() == (0..12).mapTo(sortedSetOf()) { "CODEX_AGENT_1.$it" }) {
        "C ABI Linux export policy must assign every exact symbol to the 1.0-1.12 lineage"
    }
    return assignments.toSortedMap()
}

fun crossLanguageCAbiLinuxDynamicSymbolVersions(
    output: String,
    expectedVersions: Map<String, String>,
): Map<String, String> {
    val actualSymbols = normalizedCAbiSymbols(output)
    val assignments = linkedMapOf<String, String>()
    LINUX_DYNAMIC_VERSIONED_SYMBOL.findAll(output).forEach { match ->
        val symbol = match.groupValues[1].removePrefix("_")
        check(assignments.put(symbol, match.groupValues[2]) == null) {
            "Duplicate C ABI dynamic symbol version: $symbol"
        }
    }
    check(actualSymbols == expectedVersions.keys && assignments.toSortedMap() == expectedVersions.toSortedMap()) {
        "C ABI Linux dynamic symbols are missing, extra, duplicated, unversioned, or assigned to the wrong node"
    }
    return assignments.toSortedMap()
}

fun packageCrossLanguageCAbiSdk(input: CrossLanguageCAbiPackageInput, output: File): CrossLanguageCAbiPackageSnapshot {
    val spec = checkedCAbiTarget(input.target, input.classifier)
    checkIdentity(input.libraryVersion, input.producerCommit, input.producerTree)
    listOf(input.reviewedHeader, input.license, input.notice, input.library, input.exportPolicy).forEach { file ->
        check(regularCAbiFile(file)) { "C ABI package input is missing or symbolic: $file" }
    }
    val symbols = crossLanguageCAbiExpectedSymbols(input.exportPolicy)
    check(headerSymbols(input.reviewedHeader) == symbols) { "Reviewed C ABI header/export policy symbol mismatch" }
    val payload = packagePayload(spec, input)
    val outputParent = output.absoluteFile.parentFile.also(File::mkdirs)
    val temporary = Files.createTempFile(outputParent.toPath(), ".${output.name}-", ".tmp").toFile()
    try {
        writeCAbiPackage(temporary, input, symbols, payload)
        patchDesktopRuntimeUnixModes(temporary, emptySet())
        val snapshot = inspectCrossLanguageCAbiPackage(temporary, input)
        try {
            Files.move(temporary.toPath(), output.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(temporary.toPath(), output.toPath(), StandardCopyOption.REPLACE_EXISTING)
        }
        return snapshot.copy(archiveSha256 = output.releaseDigest())
    } finally {
        temporary.delete()
    }
}

fun inspectCrossLanguageCAbiPackage(
    archiveFile: File,
    expected: CrossLanguageCAbiPackageInput,
): CrossLanguageCAbiPackageSnapshot {
    val spec = checkedCAbiTarget(expected.target, expected.classifier)
    checkIdentity(expected.libraryVersion, expected.producerCommit, expected.producerTree)
    val symbols = crossLanguageCAbiExpectedSymbols(expected.exportPolicy)
    check(headerSymbols(expected.reviewedHeader) == symbols) { "Reviewed C ABI header/export policy symbol mismatch" }
    val payload = packagePayload(spec, expected)
    val expectedPaths = payload.map(CAbiPackageMember::path).toSet() + C_ABI_PACKAGE_MANIFEST
    check(regularCAbiFile(archiveFile)) { "C ABI package is missing or symbolic: $archiveFile" }
    return ZipFile(archiveFile).use { archive ->
        val entries = archive.entries().asSequence().toList()
        val names = entries.map(ZipEntry::getName)
        check(names.size == names.distinct().size) { "C ABI package contains duplicate members" }
        check(names.toSet() == expectedPaths && entries.size == expectedPaths.size) {
            "C ABI package member set mismatch: expected=$expectedPaths actual=${names.toSet()}"
        }
        entries.forEach { entry ->
            check(!entry.isDirectory && safeCAbiPackagePath(entry.name)) { "Unsafe C ABI package member: ${entry.name}" }
            check(entry.method == ZipEntry.DEFLATED && entry.timeLocal == C_ABI_ZIP_EPOCH) {
                "C ABI package member encoding is not canonical: ${entry.name}"
            }
        }
        check(readDesktopRuntimeUnixModes(archiveFile) == expectedPaths.associateWith { C_ABI_FILE_MODE }) {
            "C ABI package Unix modes are not canonical"
        }
        fun bytes(path: String): ByteArray = archive.getInputStream(archive.getEntry(path)).use { it.readBytes() }
        val digests = payload.associate { member -> member.path to bytes(member.path).inputStream().releaseDigest() }
        payload.forEach { member ->
            check(digests.getValue(member.path) == member.file.releaseDigest()) {
                "C ABI package member digest mismatch: ${member.path}"
            }
        }
        if (spec.format == "elf") {
            check(bytes("lib/libcodex_agent.so").contentEquals(bytes("lib/libcodex_agent.so.1"))) {
                "Linux C ABI linker and SONAME entries must be byte-identical"
            }
        }
        val manifest = releaseJson.parseToJsonElement(bytes(C_ABI_PACKAGE_MANIFEST).decodeToString()).jsonObject
        verifyCAbiPackageManifest(manifest, expected, spec, symbols, payload, digests)
        verifyCanonicalCAbiPackageBytes(archiveFile, expected, symbols, payload)
        CrossLanguageCAbiPackageSnapshot(
            spec.target,
            spec.classifier,
            archiveFile.releaseDigest(),
            digests.getValue(C_ABI_HEADER_PATH),
            digests.getValue(spec.libraryPath),
            symbols.sortedNewlineSha256(),
            digests.toSortedMap(),
        )
    }
}

private fun verifyCanonicalCAbiPackageBytes(
    archiveFile: File,
    input: CrossLanguageCAbiPackageInput,
    symbols: Set<String>,
    payload: List<CAbiPackageMember>,
) {
    val canonical = Files.createTempFile("codex-agent-c-abi-canonical-", ".zip").toFile()
    try {
        writeCAbiPackage(canonical, input, symbols, payload)
        patchDesktopRuntimeUnixModes(canonical, emptySet())
        check(Files.mismatch(archiveFile.toPath(), canonical.toPath()) == -1L) {
            "C ABI package bytes are not canonical"
        }
    } finally {
        canonical.delete()
    }
}

fun buildCrossLanguageCAbiPackageEvidence(values: CrossLanguageCAbiEvidenceValues): JsonObject = buildJsonObject {
    val spec = checkedCAbiTarget(values.target, values.classifier)
    put("schemaVersion", 1)
    put("artifactId", crossLanguageCAbiPackageProofIds.getValue(spec.target))
    put("target", values.target)
    put("classifier", values.classifier)
    put("libraryVersion", values.libraryVersion)
    put("producerCommit", values.producerCommit)
    put("producerTree", values.producerTree)
    put("runnerOs", values.runnerOs)
    put("runnerArch", values.runnerArch)
    put("abiCurrent", CROSS_LANGUAGE_C_ABI_CURRENT)
    put("abiMinimum", CROSS_LANGUAGE_C_ABI_MINIMUM)
    put("abiEncoded", CROSS_LANGUAGE_C_ABI_ENCODED)
    put("archiveSha256", values.archiveSha256)
    put("headerSha256", values.headerSha256)
    put("libraryPath", spec.libraryPath)
    put("librarySha256", values.librarySha256)
    put("publicSymbolCount", values.publicSymbols.size)
    put("publicSymbolsSha256", values.publicSymbols.sortedNewlineSha256())
    put("publicSymbols", buildJsonArray { values.publicSymbols.sorted().forEach { add(JsonPrimitive(it)) } })
    put("publicSymbolVersions", buildJsonArray {
        values.publicSymbolVersions.toSortedMap().forEach { (symbol, version) ->
            add(buildJsonObject { put("symbol", symbol); put("version", version) })
        }
    })
    put("format", values.format)
    put("architecture", values.architecture)
    put("loaderIdentity", values.loaderIdentity)
    put("versionIdentity", values.versionIdentity)
    put("importLibraries", buildJsonArray {
        values.importLibraries.toSortedMap().forEach { (path, digest) ->
            add(buildJsonObject { put("path", path); put("sha256", digest) })
        }
    })
    put("tools", buildJsonArray {
        values.toolProofs.toSortedMap().forEach { (id, digest) ->
            add(buildJsonObject { put("id", id); put("outputSha256", digest) })
        }
    })
    put("consumers", buildJsonArray {
        values.consumers.sortedBy(CrossLanguageCAbiConsumerProof::source).forEach { proof ->
            add(buildJsonObject {
                put("source", proof.source)
                put("sourceSha256", proof.sourceSha256)
                put("language", proof.language)
                put("compilerIdentitySha256", proof.compilerIdentitySha256)
                put("compileOutputSha256", proof.compileOutputSha256)
                put("artifactSha256", proof.artifactSha256)
                put("linked", proof.linked)
                put("executed", proof.executed)
                put("exitCode", proof.exitCode)
            })
        }
    })
    put("gnuConsumers", buildJsonArray {
        values.gnuConsumers.sortedBy(CrossLanguageCAbiConsumerProof::source).forEach { proof ->
            add(cAbiConsumerProofJson(proof))
        }
    })
    put("result", "passed")
}

private fun cAbiConsumerProofJson(proof: CrossLanguageCAbiConsumerProof): JsonObject = buildJsonObject {
    put("source", proof.source)
    put("sourceSha256", proof.sourceSha256)
    put("language", proof.language)
    put("compilerIdentitySha256", proof.compilerIdentitySha256)
    put("compileOutputSha256", proof.compileOutputSha256)
    put("artifactSha256", proof.artifactSha256)
    put("linked", proof.linked)
    put("executed", proof.executed)
    put("exitCode", proof.exitCode)
}

fun verifyCrossLanguageCAbiPackageEvidence(
    report: JsonObject,
    archive: File,
    expected: CrossLanguageCAbiPackageInput,
    expectedRunnerOs: String,
    expectedRunnerArch: String,
    expectedConsumers: Map<String, String>,
) {
    val spec = checkedCAbiTarget(expected.target, expected.classifier)
    check(expectedConsumers.keys == crossLanguageCAbiStrictConsumers) {
        "C ABI strict consumer source inventory is incomplete or unexpected"
    }
    val packageSnapshot = inspectCrossLanguageCAbiPackage(archive, expected)
    val exactKeys = setOf(
        "schemaVersion", "artifactId", "target", "classifier", "libraryVersion", "producerCommit", "producerTree",
        "runnerOs", "runnerArch", "abiCurrent", "abiMinimum", "abiEncoded", "archiveSha256", "headerSha256",
        "libraryPath", "librarySha256", "publicSymbolCount", "publicSymbolsSha256", "publicSymbols",
        "publicSymbolVersions", "format", "architecture", "loaderIdentity", "versionIdentity", "importLibraries",
        "tools", "consumers", "gnuConsumers", "result",
    )
    check(report.keys == exactKeys && report.strictInt("schemaVersion") == 1) { "C ABI evidence schema mismatch" }
    check(report.strictString("artifactId") == crossLanguageCAbiPackageProofIds.getValue(spec.target)) {
        "C ABI evidence artifact identity mismatch"
    }
    check(report.strictString("target") == spec.target && report.strictString("classifier") == spec.classifier) {
        "C ABI evidence target/classifier mismatch"
    }
    check(report.strictString("libraryVersion") == expected.libraryVersion &&
        report.strictString("producerCommit") == expected.producerCommit &&
        report.strictString("producerTree") == expected.producerTree) {
        "C ABI evidence producer identity mismatch"
    }
    check(report.strictString("runnerOs") == expectedRunnerOs && report.strictString("runnerArch") == expectedRunnerArch &&
        expectedRunnerOs == spec.runnerOs && expectedRunnerArch == spec.runnerArch) {
        "C ABI evidence runner identity mismatch"
    }
    check(report.strictString("abiCurrent") == CROSS_LANGUAGE_C_ABI_CURRENT &&
        report.strictString("abiMinimum") == CROSS_LANGUAGE_C_ABI_MINIMUM &&
        report.strictString("abiEncoded") == CROSS_LANGUAGE_C_ABI_ENCODED) {
        "C ABI evidence ABI version mismatch"
    }
    check(report.strictString("archiveSha256") == packageSnapshot.archiveSha256 &&
        report.strictString("headerSha256") == packageSnapshot.headerSha256 &&
        report.strictString("libraryPath") == spec.libraryPath &&
        report.strictString("librarySha256") == packageSnapshot.librarySha256) {
        "C ABI evidence artifact digest mismatch"
    }
    val expectedSymbols = crossLanguageCAbiExpectedSymbols(expected.exportPolicy)
    val reportedSymbols = report.strictArray("publicSymbols").map { it.jsonPrimitive.content }.toList()
    check(reportedSymbols == reportedSymbols.sorted() && reportedSymbols.size == reportedSymbols.distinct().size &&
        reportedSymbols.toSet() == expectedSymbols &&
        report.strictInt("publicSymbolCount") == CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT &&
        report.strictString("publicSymbolsSha256") == expectedSymbols.sortedNewlineSha256()) {
        "C ABI evidence public symbol inventory mismatch"
    }
    val reportedVersions = report.strictArray("publicSymbolVersions").map { value ->
        val record = value.jsonObject
        check(record.keys == setOf("symbol", "version")) { "C ABI symbol-version evidence schema mismatch" }
        record.strictString("symbol") to record.strictString("version")
    }
    val expectedVersions = if (spec.format == "elf") crossLanguageCAbiLinuxSymbolVersions(expected.exportPolicy) else emptyMap()
    check(reportedVersions.size == expectedVersions.size && reportedVersions.map { it.first }.distinct().size ==
        reportedVersions.size && reportedVersions.map { it.first } == reportedVersions.map { it.first }.sorted() &&
        reportedVersions.toMap() == expectedVersions) {
        "C ABI evidence symbol-version assignments mismatch"
    }
    check(report.strictString("format") == spec.format && report.strictString("architecture") == spec.architecture &&
        report.strictString("loaderIdentity") == spec.loaderIdentity &&
        report.strictString("versionIdentity") == spec.expectedVersionIdentity()) {
        "C ABI evidence architecture/loader/version mismatch"
    }
    val imports = report.strictArray("importLibraries").map { value ->
        val record = value.jsonObject
        check(record.keys == setOf("path", "sha256")) { "C ABI import-library evidence schema mismatch" }
        record.strictString("path") to record.strictSha256("sha256")
    }
    check(imports.size == spec.importLibraryPaths.size && imports.map { it.first }.distinct().size == imports.size &&
        imports.map { it.first } == imports.map { it.first }.sorted() &&
        imports.map { it.first }.toSet() == spec.importLibraryPaths.toSet() &&
        imports.toMap().all { (path, digest) -> packageSnapshot.members[path] == digest }) {
        "C ABI evidence import-library mismatch"
    }
    val tools = report.strictArray("tools").map { value ->
        val record = value.jsonObject
        check(record.keys == setOf("id", "outputSha256")) { "C ABI tool evidence schema mismatch" }
        record.strictString("id") to record.strictSha256("outputSha256")
    }
    check(tools.size == spec.requiredToolIds().size && tools.map { it.first }.distinct().size == tools.size &&
        tools.map { it.first } == tools.map { it.first }.sorted() &&
        tools.map { it.first }.toSet() == spec.requiredToolIds()) {
        "C ABI tool evidence inventory mismatch"
    }
    val toolProofById = tools.toMap()
    val consumers = report.strictArray("consumers").map(::parseCAbiConsumerProof)
    check(consumers.map(CrossLanguageCAbiConsumerProof::source) ==
        consumers.map(CrossLanguageCAbiConsumerProof::source).sorted() &&
        consumers.map(CrossLanguageCAbiConsumerProof::source).toSet() == expectedConsumers.keys &&
        consumers.size == expectedConsumers.size) {
        "C ABI strict consumer evidence inventory mismatch"
    }
    consumers.forEach { proof ->
        val expectedLanguage = if (proof.source.endsWith(".cpp")) "c++17" else "c11"
        check(proof.source == File(proof.source).name && proof.sourceSha256 == expectedConsumers.getValue(proof.source) &&
            proof.language == expectedLanguage &&
            proof.compilerIdentitySha256 == toolProofById.getValue(if (expectedLanguage == "c++17") "cpp" else "c") &&
            proof.compileOutputSha256.isSha256() && proof.artifactSha256.isSha256() && proof.exitCode == 0 &&
            ((proof.linked && proof.executed) ||
                (!proof.linked && !proof.executed && proof.source in crossLanguageCAbiCompileOnlyConsumers))) {
            "C ABI strict consumer proof failed: ${proof.source}"
        }
    }
    check(consumers.filterNot(CrossLanguageCAbiConsumerProof::executed).map(CrossLanguageCAbiConsumerProof::source).toSet() ==
        expectedConsumers.keys.intersect(crossLanguageCAbiCompileOnlyConsumers)) {
        "C ABI strict consumer execution boundary mismatch"
    }
    val gnuConsumers = report.strictArray("gnuConsumers").map(::parseCAbiConsumerProof)
    val expectedGnu = if (spec.format == "pe") C_ABI_GNU_CONSUMERS else emptySet()
    check(gnuConsumers.map(CrossLanguageCAbiConsumerProof::source) ==
        gnuConsumers.map(CrossLanguageCAbiConsumerProof::source).sorted() &&
        gnuConsumers.map(CrossLanguageCAbiConsumerProof::source).toSet() == expectedGnu &&
        gnuConsumers.size == expectedGnu.size) {
        "C ABI GNU strict consumer evidence inventory mismatch"
    }
    gnuConsumers.forEach { proof ->
        val expectedLanguage = if (proof.source.endsWith(".cpp")) "c++17" else "c11"
        check(proof.sourceSha256 == expectedConsumers.getValue(proof.source) && proof.language == expectedLanguage &&
            proof.compilerIdentitySha256 == toolProofById.getValue(if (expectedLanguage == "c++17") "gnuCpp" else "gnuC") &&
            proof.compileOutputSha256.isSha256() &&
            proof.artifactSha256.isSha256() && proof.linked && proof.executed && proof.exitCode == 0) {
            "C ABI GNU strict consumer proof failed: ${proof.source}"
        }
    }
    check(report.strictString("result") == "passed") { "C ABI package evidence did not pass" }
}

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
): JsonObject {
    val spec = crossLanguageCAbiTargetSpecs[target] ?: error("Unsupported C ABI package target: $target")
    check(evidence.isFile && !Files.isSymbolicLink(evidence.toPath())) {
        "C ABI package evidence is missing, non-regular, or symbolic: $evidence"
    }
    val sources = consumerSources.sortedBy(File::getName)
    check(sources.all(::regularCAbiFile) && sources.map(File::getName).toSet() == crossLanguageCAbiStrictConsumers &&
        sources.size == crossLanguageCAbiStrictConsumers.size) {
        "C ABI strict consumer sources are missing or duplicated"
    }
    val temporary = Files.createTempDirectory("codex-agent-c-abi-portable-${spec.target}-").toFile()
    try {
        val root = temporary.resolve("sdk")
        extractCAbiPackage(archive, root)
        val input = extractedCAbiPackageInput(
            spec, libraryVersion, producerCommit, producerTree, reviewedHeader, license, notice, exportPolicy, root,
        )
        val contents = evidence.readText()
        val report = releaseJson.parseToJsonElement(contents).jsonObject
        check(contents == releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), report) + "\n") {
            "C ABI package evidence is not canonically encoded"
        }
        return report.also {
            verifyCrossLanguageCAbiPackageEvidence(
                it, archive, input, spec.runnerOs, spec.runnerArch,
                sources.associate { it.name to it.releaseDigest() },
            )
        }
    } finally {
        temporary.deleteRecursively()
    }
}

data class CrossLanguageNativeWrapperSdkInput(
    val libraryVersion: String,
    val producerCommit: String,
    val producerTree: String,
    val archives: Map<String, File>,
    val evidence: Map<String, File>,
    val reviewedHeader: File,
    val license: File,
    val notice: File,
    val exportPolicies: Map<String, File>,
    val consumerSources: List<File>,
)

internal data class CrossLanguageNativeWrapperSdkRecord(
    val target: String,
    val classifier: String,
    val libraryPath: String,
    val librarySha256: String,
)

internal data class CrossLanguageNativeWrapperSdkIndex(
    val producerCommit: String,
    val producerTree: String,
    val records: Map<String, CrossLanguageNativeWrapperSdkRecord>,
)

fun stageCrossLanguageNativeWrapperSdks(
    input: CrossLanguageNativeWrapperSdkInput,
    outputDirectory: File,
) {
    val targets = crossLanguageCAbiTargetSpecs.keys
    check(input.archives.keys == targets && input.evidence.keys == targets && input.exportPolicies.keys == targets) {
        "Native wrapper C ABI SDK staging requires exactly all five targets"
    }
    check(!Files.isSymbolicLink(outputDirectory.toPath())) {
        "Native wrapper C ABI SDK staging output must not be a symlink"
    }
    val parent = outputDirectory.absoluteFile.parentFile.also(File::mkdirs)
    val temporary = Files.createTempDirectory(parent.toPath(), ".native-wrapper-sdks-").toFile()
    try {
        val staged = temporary.resolve("staged")
        val indexTargets = buildJsonArray {
            targets.sorted().forEach { target ->
                val spec = crossLanguageCAbiTargetSpecs.getValue(target)
                val archive = input.archives.getValue(target)
                val proof = input.evidence.getValue(target)
                val report = portableVerifyCrossLanguageCAbiPackageEvidence(
                    target,
                    input.libraryVersion,
                    input.producerCommit,
                    input.producerTree,
                    archive,
                    proof,
                    input.reviewedHeader,
                    input.license,
                    input.notice,
                    input.exportPolicies.getValue(target),
                    input.consumerSources,
                )
                val classifier = spec.classifier.removePrefix("c-abi-")
                val targetRoot = staged.resolve(classifier)
                extractCAbiPackage(archive, targetRoot)
                val manifest = targetRoot.resolve("codex-agent-c-abi-manifest.json")
                check(regularCAbiFile(manifest)) { "Staged native wrapper C ABI manifest is missing: $target" }
                Files.copy(
                    proof.toPath(),
                    targetRoot.resolve("codex-agent-c-abi-evidence.json").toPath(),
                    StandardCopyOption.REPLACE_EXISTING,
                )
                add(buildJsonObject {
                    put("target", target)
                    put("classifier", classifier)
                    put("archiveSha256", report.strictSha256("archiveSha256"))
                    put("evidenceSha256", proof.releaseDigest())
                    put("libraryPath", spec.libraryPath)
                    put("librarySha256", report.strictSha256("librarySha256"))
                    put("manifestSha256", manifest.releaseDigest())
                })
            }
        }
        staged.resolve("codex-agent-native-wrapper-sdks.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", 1)
            put("libraryVersion", input.libraryVersion)
            put("producerCommit", input.producerCommit)
            put("producerTree", input.producerTree)
            put("targets", indexTargets)
        })
        outputDirectory.deleteRecursively()
        try {
            Files.move(staged.toPath(), outputDirectory.toPath(), StandardCopyOption.ATOMIC_MOVE)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(staged.toPath(), outputDirectory.toPath())
        }
    } finally {
        temporary.deleteRecursively()
    }
}

@CacheableTask
abstract class StageCrossLanguageNativeWrapperSdksTask : DefaultTask() {
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:InputFiles @get:PathSensitive(PathSensitivity.NONE) abstract val archives: ConfigurableFileCollection
    @get:InputFiles @get:PathSensitive(PathSensitivity.NONE) abstract val evidence: ConfigurableFileCollection
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val macosExportPolicy: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val linuxExportPolicy: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val windowsExportPolicy: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val consumerSources: ConfigurableFileCollection
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun stage() {
        val archiveByName = archives.files.associateBy(File::getName)
        val evidenceByName = evidence.files.associateBy(File::getName)
        check(archiveByName.size == archives.files.size && evidenceByName.size == evidence.files.size) {
            "Native wrapper C ABI SDK inputs contain duplicate file names"
        }
        stageCrossLanguageNativeWrapperSdks(
            CrossLanguageNativeWrapperSdkInput(
                libraryVersion.get(),
                producerCommit.get(),
                producerTree.get(),
                crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
                    archiveByName.getValue(crossLanguageCAbiArchiveFileName(libraryVersion.get(), target))
                }.also { check(it.size == archiveByName.size) { "Unexpected native wrapper C ABI SDK archive" } },
                crossLanguageCAbiTargetSpecs.keys.associateWith { target ->
                    evidenceByName.getValue(crossLanguageCAbiPackageEvidenceFileName(target))
                }.also { check(it.size == evidenceByName.size) { "Unexpected native wrapper C ABI SDK evidence" } },
                reviewedHeader.get().asFile,
                license.get().asFile,
                notice.get().asFile,
                crossLanguageCAbiTargetSpecs.mapValues { (_, spec) ->
                    when (spec.format) {
                        "mach-o" -> macosExportPolicy.get().asFile
                        "elf" -> linuxExportPolicy.get().asFile
                        "pe" -> windowsExportPolicy.get().asFile
                        else -> error("Unsupported native wrapper C ABI SDK format: ${spec.format}")
                    }
                },
                consumerSources.files.toList(),
            ),
            outputDirectory.get().asFile,
        )
    }
}

fun materializeCrossLanguageNativeWrapperPackageAssets(
    stagedSdkDirectory: File,
    outputDirectory: File,
) {
    val indexFile = stagedSdkDirectory.resolve("codex-agent-native-wrapper-sdks.json")
    val index = readCrossLanguageNativeWrapperSdkIndex(stagedSdkDirectory)
    check(!Files.isSymbolicLink(outputDirectory.toPath())) {
        "Native wrapper package asset output must not be a symlink"
    }
    val parent = outputDirectory.absoluteFile.parentFile.also(File::mkdirs)
    val temporary = Files.createTempDirectory(parent.toPath(), ".native-wrapper-package-assets-").toFile()
    try {
        val staged = temporary.resolve("staged")
        index.records.toSortedMap().forEach { (target, record) ->
            val spec = crossLanguageCAbiTargetSpecs.getValue(target)
            val classifier = record.classifier
            val source = stagedSdkDirectory.resolve(classifier)
            val library = source.resolve(spec.libraryPath)
            val manifest = source.resolve("codex-agent-c-abi-manifest.json")
            val evidence = source.resolve("codex-agent-c-abi-evidence.json")
            val packageClassifier = when (classifier) {
                "macos-arm64" -> "osx-arm64"
                "macos-x64" -> "osx-x64"
                "windows-x64" -> "win-x64"
                else -> classifier
            }
            val destinations = mapOf(
                "python/src/codex_agent/native/$classifier" to library.name,
                "csharp/native/$packageClassifier" to library.name,
                "rust/native/$packageClassifier" to library.name,
                "dart/lib/src/native/$classifier" to library.name,
            )
            destinations.forEach { (path, libraryName) ->
                val destination = staged.resolve(path).also(File::mkdirs)
                Files.copy(library.toPath(), destination.resolve(libraryName).toPath())
                Files.copy(manifest.toPath(), destination.resolve(manifest.name).toPath())
                Files.copy(evidence.toPath(), destination.resolve(evidence.name).toPath())
            }
            check(source.copyRecursively(staged.resolve("cpp/native/$classifier"))) {
                "Failed to stage the verified C SDK for the C++ $classifier package"
            }
        }
        Files.copy(indexFile.toPath(), staged.resolve(indexFile.name).toPath())
        outputDirectory.deleteRecursively()
        try {
            Files.move(staged.toPath(), outputDirectory.toPath(), StandardCopyOption.ATOMIC_MOVE)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(staged.toPath(), outputDirectory.toPath())
        }
    } finally {
        temporary.deleteRecursively()
    }
}

internal fun readCrossLanguageNativeWrapperSdkIndex(
    stagedSdkDirectory: File,
): CrossLanguageNativeWrapperSdkIndex {
    check(stagedSdkDirectory.isDirectory && !Files.isSymbolicLink(stagedSdkDirectory.toPath())) {
        "Native wrapper SDK staging root is missing or symbolic"
    }
    verifiedRegularFiles(stagedSdkDirectory)
    val indexFile = stagedSdkDirectory.resolve("codex-agent-native-wrapper-sdks.json")
    check(regularCAbiFile(indexFile)) { "Native wrapper SDK index is missing" }
    val contents = indexFile.readText()
    val root = releaseJson.parseToJsonElement(contents).jsonObject
    check(contents == releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), root) + "\n") {
        "Native wrapper SDK index is not canonically encoded"
    }
    check(root.keys == setOf("schemaVersion", "libraryVersion", "producerCommit", "producerTree", "targets") &&
        root.strictInt("schemaVersion") == 1) {
        "Native wrapper SDK index schema mismatch"
    }
    val version = root.strictString("libraryVersion")
    val commit = root.strictString("producerCommit")
    val tree = root.strictString("producerTree")
    checkIdentity(version, commit, tree)
    val elements = root.strictArray("targets")
    val records = elements.associateBy { it.jsonObject.strictString("target") }
    check(records.size == elements.size && records.keys == crossLanguageCAbiTargetSpecs.keys) {
        "Native wrapper SDK index target inventory mismatch"
    }
    return CrossLanguageNativeWrapperSdkIndex(
        producerCommit = commit,
        producerTree = tree,
        records = records.toSortedMap().mapValues { (target, element) ->
            val spec = crossLanguageCAbiTargetSpecs.getValue(target)
            val record = element.jsonObject
            check(record.keys == setOf(
                "target", "classifier", "archiveSha256", "evidenceSha256", "libraryPath", "librarySha256",
                "manifestSha256",
            ) && record.strictString("classifier") == spec.classifier.removePrefix("c-abi-") &&
                record.strictString("libraryPath") == spec.libraryPath) {
                "Native wrapper SDK target record mismatch: $target"
            }
            record.strictSha256("archiveSha256")
            val classifier = record.strictString("classifier")
            val source = stagedSdkDirectory.resolve(classifier)
            check(source.isDirectory && !Files.isSymbolicLink(source.toPath())) {
                "Native wrapper SDK classifier root is missing or symbolic: $target"
            }
            val library = source.resolve(spec.libraryPath)
            val manifest = source.resolve("codex-agent-c-abi-manifest.json")
            val evidence = source.resolve("codex-agent-c-abi-evidence.json")
            check(listOf(library, manifest, evidence).all(::regularCAbiFile)) {
                "Native wrapper SDK target payload is incomplete: $target"
            }
            val librarySha256 = record.strictSha256("librarySha256")
            check(library.releaseDigest() == librarySha256 &&
                manifest.releaseDigest() == record.strictSha256("manifestSha256") &&
                evidence.releaseDigest() == record.strictSha256("evidenceSha256")) {
                "Native wrapper SDK target hash mismatch: $target"
            }
            CrossLanguageNativeWrapperSdkRecord(target, classifier, spec.libraryPath, librarySha256)
        },
    )
}

@CacheableTask
abstract class MaterializeCrossLanguageNativeWrapperPackageAssetsTask : DefaultTask() {
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val stagedSdkDirectory: ConfigurableFileCollection
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun materialize() {
        val roots = stagedSdkDirectory.files
        check(roots.size == 1) { "Native wrapper package assets require one staged SDK root" }
        materializeCrossLanguageNativeWrapperPackageAssets(roots.single(), outputDirectory.get().asFile)
    }
}

@CacheableTask
abstract class PackageCrossLanguageCAbiSdkTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val library: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFile @get:org.gradle.api.tasks.Optional @get:PathSensitive(PathSensitivity.NONE)
    abstract val gnuImportLibrary: RegularFileProperty
    @get:InputFile @get:org.gradle.api.tasks.Optional @get:PathSensitive(PathSensitivity.NONE)
    abstract val msvcImportLibrary: RegularFileProperty
    @get:OutputFile abstract val outputFile: RegularFileProperty

    @TaskAction
    fun packageSdk() {
        packageCrossLanguageCAbiSdk(packageInput(), outputFile.get().asFile)
    }

    fun packageInput() = CrossLanguageCAbiPackageInput(
        target.get(), classifier.get(), libraryVersion.get(), producerCommit.get(), producerTree.get(),
        reviewedHeader.get().asFile, license.get().asFile, notice.get().asFile, library.get().asFile,
        exportPolicy.get().asFile, gnuImportLibrary.orNull?.asFile, msvcImportLibrary.orNull?.asFile,
    )
}

@DisableCachingByDefault(because = "Compiles, links, and executes strict C ABI consumers with the target runner toolchain")
abstract class GenerateCrossLanguageCAbiPackageEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:Input abstract val runnerOs: Property<String>
    @get:Input abstract val runnerArch: Property<String>
    @get:Input abstract val tools: MapProperty<String, String>
    @get:Input abstract val compileOnlyConsumers: ListProperty<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val consumerSources: ConfigurableFileCollection
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun generateEvidence() {
        evidenceFile.get().asFile.delete()
        val spec = checkedCAbiTarget(target.get(), classifier.get())
        checkIdentity(libraryVersion.get(), producerCommit.get(), producerTree.get())
        check(runnerOs.get() == spec.runnerOs && runnerArch.get() == spec.runnerArch) {
            "C ABI package evidence runner mismatch"
        }
        val toolMap = tools.get()
        check(toolMap.keys == spec.requiredToolIds() && toolMap.values.all(::safeToolExecutable)) {
            "C ABI package evidence tool inventory mismatch"
        }
        val sources = consumerSources.files.sortedBy(File::getName)
        check(sources.all(::regularCAbiFile) && sources.map(File::getName).toSet() == crossLanguageCAbiStrictConsumers &&
            sources.size == crossLanguageCAbiStrictConsumers.size) {
            "C ABI strict consumer sources are missing or duplicated"
        }
        val compileOnly = compileOnlyConsumers.get().toSet()
        check(compileOnly == sources.map(File::getName).toSet().intersect(crossLanguageCAbiCompileOnlyConsumers)) {
            "C ABI compile-only consumer inventory mismatch"
        }
        val temporary = Files.createTempDirectory("codex-agent-c-abi-${spec.target}-").toFile()
        try {
            val root = temporary.resolve("sdk")
            extractCAbiPackage(packageFile.get().asFile, root)
            val input = extractedCAbiPackageInput(
                spec, libraryVersion.get(), producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            val snapshot = inspectCrossLanguageCAbiPackage(packageFile.get().asFile, input)
            val toolProofs = linkedMapOf<String, String>()
            val inspection = inspectCAbiBinary(spec, root, toolMap, toolProofs, input.exportPolicy)
            val symbols = crossLanguageCAbiExpectedSymbols(input.exportPolicy)
            check(inspection.publicSymbols == symbols) { "C ABI packaged library export mismatch" }
            val consumers = executeCAbiConsumers(spec, root, sources, compileOnly, toolMap, temporary, toolProofs)
            val gnuConsumers = if (spec.format == "pe") {
                executeCAbiGnuConsumers(spec, root, sources, toolMap, temporary, toolProofs)
            } else {
                emptyList()
            }
            val report = buildCrossLanguageCAbiPackageEvidence(CrossLanguageCAbiEvidenceValues(
                spec.target, spec.classifier, input.libraryVersion, input.producerCommit, input.producerTree,
                runnerOs.get(), runnerArch.get(), snapshot.archiveSha256, snapshot.headerSha256,
                snapshot.librarySha256, inspection.publicSymbols, inspection.publicSymbolVersions,
                inspection.format, inspection.architecture,
                inspection.loaderIdentity, inspection.versionIdentity,
                spec.importLibraryPaths.associateWith { snapshot.members.getValue(it) }, toolProofs, consumers, gnuConsumers,
            ))
            verifyCrossLanguageCAbiPackageEvidence(
                report, packageFile.get().asFile, input, runnerOs.get(), runnerArch.get(),
                sources.associate { it.name to it.releaseDigest() },
            )
            evidenceFile.get().asFile.atomicWriteJson(report)
        } finally {
            temporary.deleteRecursively()
        }
    }
}

@CacheableTask
abstract class VerifyCrossLanguageCAbiPackageEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:Input abstract val runnerOs: Property<String>
    @get:Input abstract val runnerArch: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val evidenceFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val consumerSources: ConfigurableFileCollection
    @get:OutputFile abstract val verifiedEvidenceFile: RegularFileProperty

    @TaskAction
    fun verifyEvidence() {
        verifiedEvidenceFile.get().asFile.delete()
        val sources = consumerSources.files
        check(sources.all(::regularCAbiFile) && sources.map(File::getName).toSet() == crossLanguageCAbiStrictConsumers &&
            sources.size == crossLanguageCAbiStrictConsumers.size) {
            "C ABI strict consumer sources are missing or duplicated"
        }
        val spec = checkedCAbiTarget(target.get(), classifier.get())
        val temporary = Files.createTempDirectory("codex-agent-c-abi-verify-${spec.target}-").toFile()
        try {
            val root = temporary.resolve("sdk")
            extractCAbiPackage(packageFile.get().asFile, root)
            val expected = extractedCAbiPackageInput(
                spec, libraryVersion.get(), producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            val report = evidenceFile.get().asFile.readReleaseObject()
            verifyCrossLanguageCAbiPackageEvidence(
                report, packageFile.get().asFile, expected,
                runnerOs.get(), runnerArch.get(), sources.associate { it.name to it.releaseDigest() },
            )
            verifiedEvidenceFile.get().asFile.atomicWriteJson(report)
        } finally {
            temporary.deleteRecursively()
        }
    }
}

private data class CAbiPackageMember(val path: String, val role: String, val file: File)
private data class CAbiBinaryInspection(
    val publicSymbols: Set<String>,
    val publicSymbolVersions: Map<String, String>,
    val format: String,
    val architecture: String,
    val loaderIdentity: String,
    val versionIdentity: String,
)

private fun extractedCAbiPackageInput(
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

private fun packagePayload(
    spec: CrossLanguageCAbiTargetSpec,
    input: CrossLanguageCAbiPackageInput,
): List<CAbiPackageMember> {
    val members = mutableListOf(
        CAbiPackageMember(C_ABI_HEADER_PATH, "header", input.reviewedHeader),
        CAbiPackageMember("LICENSE.txt", "license", input.license),
        CAbiPackageMember("THIRD_PARTY_NOTICES.md", "notice", input.notice),
        CAbiPackageMember(spec.libraryPath, "shared-library", input.library),
    )
    if (spec.format == "elf") {
        members += CAbiPackageMember("lib/${spec.loaderIdentity}", "soname-library", input.library)
    }
    if (spec.format == "pe") {
        val gnu = requireNotNull(input.gnuImportLibrary) { "Windows C ABI package requires a GNU import library" }
        val msvc = requireNotNull(input.msvcImportLibrary) { "Windows C ABI package requires an MSVC import library" }
        check(regularCAbiFile(gnu) && regularCAbiFile(msvc)) {
            "Windows C ABI package requires regular GNU and MSVC import libraries"
        }
        members += CAbiPackageMember(spec.importLibraryPaths[0], "gnu-import-library", gnu)
        members += CAbiPackageMember(spec.importLibraryPaths[1], "msvc-import-library", msvc)
    } else {
        check(input.gnuImportLibrary == null && input.msvcImportLibrary == null) {
            "Non-Windows C ABI package must not contain import libraries"
        }
    }
    check(members.map(CAbiPackageMember::path).all(::safeCAbiPackagePath) &&
        members.map(CAbiPackageMember::path).distinct().size == members.size) {
        "C ABI package payload paths are invalid"
    }
    return members.sortedBy(CAbiPackageMember::path)
}

private fun writeCAbiPackage(
    target: File,
    input: CrossLanguageCAbiPackageInput,
    symbols: Set<String>,
    payload: List<CAbiPackageMember>,
) {
    val manifest = cAbiPackageManifest(input, symbols, payload)
    ZipOutputStream(BufferedOutputStream(target.outputStream())).use { output ->
        output.setLevel(9)
        (payload.map { it.path to it.file.readBytes() } + (C_ABI_PACKAGE_MANIFEST to manifest))
            .sortedBy(Pair<String, ByteArray>::first)
            .forEach { (path, bytes) ->
                output.putNextEntry(ZipEntry(path).apply { setTimeLocal(C_ABI_ZIP_EPOCH) })
                output.write(bytes)
                output.closeEntry()
            }
    }
}

private fun cAbiPackageManifest(
    input: CrossLanguageCAbiPackageInput,
    symbols: Set<String>,
    payload: List<CAbiPackageMember>,
): ByteArray = (releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), buildJsonObject {
    put("schemaVersion", 1)
    put("libraryVersion", input.libraryVersion)
    put("target", input.target)
    put("classifier", input.classifier)
    put("producerCommit", input.producerCommit)
    put("producerTree", input.producerTree)
    put("abiCurrent", CROSS_LANGUAGE_C_ABI_CURRENT)
    put("abiMinimum", CROSS_LANGUAGE_C_ABI_MINIMUM)
    put("abiEncoded", CROSS_LANGUAGE_C_ABI_ENCODED)
    put("publicSymbolCount", symbols.size)
    put("publicSymbolsSha256", symbols.sortedNewlineSha256())
    put("exportPolicySha256", input.exportPolicy.releaseDigest())
    put("members", buildJsonArray {
        payload.forEach { member ->
            add(buildJsonObject {
                put("path", member.path)
                put("role", member.role)
                put("bytes", member.file.length())
                put("sha256", member.file.releaseDigest())
            })
        }
    })
}) + "\n").encodeToByteArray()

private fun verifyCAbiPackageManifest(
    manifest: JsonObject,
    expected: CrossLanguageCAbiPackageInput,
    spec: CrossLanguageCAbiTargetSpec,
    symbols: Set<String>,
    payload: List<CAbiPackageMember>,
    digests: Map<String, String>,
) {
    check(manifest.keys == setOf(
        "schemaVersion", "libraryVersion", "target", "classifier", "producerCommit", "producerTree", "abiCurrent",
        "abiMinimum", "abiEncoded", "publicSymbolCount", "publicSymbolsSha256", "exportPolicySha256", "members",
    ) && manifest.strictInt("schemaVersion") == 1) { "C ABI package manifest schema mismatch" }
    check(manifest.strictString("libraryVersion") == expected.libraryVersion &&
        manifest.strictString("target") == spec.target && manifest.strictString("classifier") == spec.classifier &&
        manifest.strictString("producerCommit") == expected.producerCommit &&
        manifest.strictString("producerTree") == expected.producerTree) {
        "C ABI package manifest producer identity mismatch"
    }
    check(manifest.strictString("abiCurrent") == CROSS_LANGUAGE_C_ABI_CURRENT &&
        manifest.strictString("abiMinimum") == CROSS_LANGUAGE_C_ABI_MINIMUM &&
        manifest.strictString("abiEncoded") == CROSS_LANGUAGE_C_ABI_ENCODED) {
        "C ABI package manifest ABI version mismatch"
    }
    check(manifest.strictInt("publicSymbolCount") == CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT &&
        manifest.strictString("publicSymbolsSha256") == symbols.sortedNewlineSha256() &&
        manifest.strictString("exportPolicySha256") == expected.exportPolicy.releaseDigest()) {
        "C ABI package manifest public symbol identity mismatch"
    }
    val members = manifest.strictArray("members").map { value ->
        val record = value.jsonObject
        check(record.keys == setOf("path", "role", "bytes", "sha256")) { "C ABI package member record schema mismatch" }
        val path = record.strictString("path")
        check(safeCAbiPackagePath(path)) { "Unsafe C ABI manifest member: $path" }
        Triple(path, record.strictString("role"), record.strictLong("bytes") to record.strictSha256("sha256"))
    }
    check(members.map { it.first } == members.map { it.first }.sorted() &&
        members.map { it.first }.toSet() == payload.map(CAbiPackageMember::path).toSet() &&
        members.all { (path, role, sizeDigest) ->
            val source = payload.single { it.path == path }
            role == source.role && sizeDigest.first == source.file.length() && sizeDigest.second == digests.getValue(path)
        }) { "C ABI package manifest member inventory mismatch" }
}

private fun inspectCAbiBinary(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    tools: Map<String, String>,
    toolProofs: MutableMap<String, String>,
    exportPolicy: File,
): CAbiBinaryInspection {
    val library = root.resolve(spec.libraryPath)
    fun inspect(id: String, vararg arguments: String): String = runCAbiProcess(listOf(tools.getValue(id), *arguments)).also {
        toolProofs[id] = it.normalized(root).sha256()
    }
    return when (spec.format) {
        "mach-o" -> {
            val file = inspect("file", library.absolutePath)
            val architecture = inspect("architecture", "-archs", library.absolutePath).trim()
            val exports = normalizedCAbiSymbols(inspect("symbols", "-gU", library.absolutePath))
            val installName = inspect("loader", "-D", library.absolutePath).lineSequence().map(String::trim)
                .firstOrNull { it.startsWith("@rpath/") }.orEmpty()
            val versions = inspect("versions", "-L", library.absolutePath)
            check("Mach-O 64-bit" in file && architecture == spec.architecture) { "C ABI Mach-O architecture mismatch" }
            check(installName == spec.loaderIdentity && "compatibility version 1.0.0, current version 1.12.0" in versions) {
                "C ABI Mach-O loader/version mismatch"
            }
            CAbiBinaryInspection(exports, emptyMap(), spec.format, architecture, installName, spec.expectedVersionIdentity())
        }
        "elf" -> {
            val file = inspect("file", library.absolutePath)
            val headers = inspect("architecture", "-h", library.absolutePath)
            val rawSymbols = inspect("symbols", "-D", "--defined-only", library.absolutePath)
            val exports = normalizedCAbiSymbols(rawSymbols)
            val symbolVersions = crossLanguageCAbiLinuxDynamicSymbolVersions(
                rawSymbols, crossLanguageCAbiLinuxSymbolVersions(exportPolicy),
            )
            val loader = inspect("loader", "-d", library.absolutePath)
            val versions = inspect("versions", "--version-info", library.absolutePath)
            val expectedMachine = if (spec.architecture == "aarch64") "AArch64" else "Advanced Micro Devices X86-64"
            check("ELF 64-bit" in file && Regex("Machine:\\s+${Regex.escape(expectedMachine)}").containsMatchIn(headers)) {
                "C ABI ELF architecture mismatch"
            }
            check(Regex("SONAME.*\\[${Regex.escape(spec.loaderIdentity)}]").containsMatchIn(loader)) {
                "C ABI ELF SONAME mismatch"
            }
            val nodes = Regex("CODEX_AGENT_1\\.(\\d+)").findAll(versions).map { it.groupValues[1].toInt() }.toSet()
            check(nodes == (0..12).toSet()) { "C ABI ELF version-node lineage mismatch" }
            CAbiBinaryInspection(
                exports, symbolVersions, spec.format, spec.architecture, spec.loaderIdentity, spec.expectedVersionIdentity(),
            )
        }
        "pe" -> {
            val headers = inspect("architecture", "/headers", library.absolutePath)
            val exports = normalizedCAbiSymbols(inspect("symbols", "/exports", library.absolutePath))
            val msvc = root.resolve(spec.importLibraryPaths[1])
            val gnu = root.resolve(spec.importLibraryPaths[0])
            val msvcListing = inspect("msvcImport", "/list", msvc.absolutePath)
            val gnuSymbols = crossLanguageCAbiGnuImportSymbols(
                inspect("gnuImport", "-g", "--defined-only", gnu.absolutePath),
            )
            check("machine (x64)" in headers.lowercase() || "8664" in headers.lowercase()) {
                "C ABI PE architecture mismatch"
            }
            check(msvcListing.isNotBlank() && gnuSymbols == exports) { "C ABI Windows import-library closure mismatch" }
            CAbiBinaryInspection(exports, emptyMap(), spec.format, spec.architecture, spec.loaderIdentity, spec.expectedVersionIdentity())
        }
        else -> error("Unsupported C ABI package format: ${spec.format}")
    }
}

private fun executeCAbiConsumers(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    sources: List<File>,
    compileOnly: Set<String>,
    tools: Map<String, String>,
    temporary: File,
    toolProofs: MutableMap<String, String>,
): List<CrossLanguageCAbiConsumerProof> {
    val include = root.resolve("include")
    val libraryDirectory = root.resolve(spec.libraryPath).parentFile
    val executableDirectory = temporary.resolve("consumers").also(File::mkdirs)
    val environment = when (spec.format) {
        "mach-o" -> mapOf("DYLD_LIBRARY_PATH" to libraryDirectory.absolutePath)
        "elf" -> mapOf("LD_LIBRARY_PATH" to libraryDirectory.absolutePath)
        else -> mapOf("PATH" to root.resolve("bin").absolutePath + File.pathSeparator + System.getenv("PATH").orEmpty())
    }
    return sources.map { source ->
        val cpp = source.extension.lowercase() in setOf("cc", "cpp", "cxx")
        val language = if (cpp) "c++17" else "c11"
        val compilerId = if (cpp) "cpp" else "c"
        val compiler = tools.getValue(compilerId)
        val msvcStandard = if (cpp) listOf("/std:c++17", "/permissive-") else listOf("/std:c11")
        val linked = source.name !in compileOnly
        val artifact = executableDirectory.resolve(source.nameWithoutExtension + when {
            !linked && spec.format == "pe" -> ".obj"
            !linked -> ".o"
            spec.format == "pe" -> ".exe"
            else -> ""
        })
        val command = when {
            spec.format == "pe" && !linked -> listOf(
                compiler, "/nologo", "/W4", "/WX", if (cpp) "/TP" else "/TC", *msvcStandard.toTypedArray(),
                "/I${include.absolutePath}",
                source.absolutePath, "/c", "/Fo:${artifact.absolutePath}",
            )
            spec.format == "pe" -> listOf(
                compiler, "/nologo", "/W4", "/WX", if (cpp) "/TP" else "/TC", *msvcStandard.toTypedArray(),
                "/I${include.absolutePath}",
                source.absolutePath, "/Fe:${artifact.absolutePath}", "/link", "/LIBPATH:${root.resolve("lib").absolutePath}",
                "codex_agent.lib",
            )
            !linked -> listOf(
                compiler, if (cpp) "-std=c++17" else "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I${include.absolutePath}", source.absolutePath, "-c", "-o", artifact.absolutePath,
            )
            else -> listOf(
                compiler, if (cpp) "-std=c++17" else "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I${include.absolutePath}", source.absolutePath, "-L${libraryDirectory.absolutePath}", "-lcodex_agent",
                "-Wl,-rpath,${libraryDirectory.absolutePath}", "-o", artifact.absolutePath,
            )
        }
        val compilerIdentity = runCAbiProcess(
            if (spec.format == "pe") listOf(compiler) else listOf(compiler, "--version"),
            allowedExitCodes = if (spec.format == "pe") setOf(0, 2) else setOf(0),
        ).normalized(temporary)
        toolProofs[compilerId] = compilerIdentity.sha256()
        val compileOutput = runCAbiProcess(command).normalized(temporary)
        check(artifact.isFile) { "C ABI strict consumer did not produce an artifact: ${source.name}" }
        val executed = linked
        if (executed) runCAbiProcess(listOf(artifact.absolutePath), environment)
        CrossLanguageCAbiConsumerProof(
            source.name, source.releaseDigest(), language, compilerIdentity.sha256(), compileOutput.sha256(),
            artifact.releaseDigest(), linked = linked, executed = executed, exitCode = 0,
        )
    }
}

private fun executeCAbiGnuConsumers(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    sources: List<File>,
    tools: Map<String, String>,
    temporary: File,
    toolProofs: MutableMap<String, String>,
): List<CrossLanguageCAbiConsumerProof> {
    check(spec.format == "pe") { "GNU C ABI consumer proof is Windows-only" }
    val selected = sources.filter { it.name in C_ABI_GNU_CONSUMERS }.sortedBy(File::getName)
    check(selected.map(File::getName).toSet() == C_ABI_GNU_CONSUMERS) {
        "C ABI GNU strict consumer sources are incomplete"
    }
    val include = root.resolve("include")
    val gnuImportLibrary = root.resolve("lib/libcodex_agent.dll.a")
    check(regularCAbiFile(gnuImportLibrary)) { "Packaged GNU C ABI import library is missing" }
    val output = temporary.resolve("gnu-consumers").also(File::mkdirs)
    val environment = mapOf(
        "PATH" to root.resolve("bin").absolutePath + File.pathSeparator + System.getenv("PATH").orEmpty(),
    )
    return selected.map { source ->
        val cpp = source.extension.lowercase() == "cpp"
        val compilerId = if (cpp) "gnuCpp" else "gnuC"
        val compiler = tools.getValue(compilerId)
        val artifact = output.resolve("${source.nameWithoutExtension}-gnu.exe")
        val compilerIdentity = runCAbiProcess(listOf(compiler, "--version")).normalized(temporary)
        toolProofs[compilerId] = compilerIdentity.sha256()
        val compileOutput = runCAbiProcess(listOf(
            compiler,
            if (cpp) "-std=c++17" else "-std=c11",
            "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I${include.absolutePath}",
            source.absolutePath,
            gnuImportLibrary.absolutePath,
            "-o", artifact.absolutePath,
        )).normalized(temporary)
        check(artifact.isFile) { "C ABI GNU strict consumer did not link: ${source.name}" }
        runCAbiProcess(listOf(artifact.absolutePath), environment)
        CrossLanguageCAbiConsumerProof(
            source.name,
            source.releaseDigest(),
            if (cpp) "c++17" else "c11",
            compilerIdentity.sha256(),
            compileOutput.sha256(),
            artifact.releaseDigest(),
            linked = true,
            executed = true,
            exitCode = 0,
        )
    }
}

internal fun extractCAbiPackage(archiveFile: File, root: File) {
    val canonicalRoot = root.canonicalFile.also(File::mkdirs)
    ZipFile(archiveFile).use { archive ->
        archive.entries().asSequence().forEach { entry ->
            check(!entry.isDirectory && safeCAbiPackagePath(entry.name)) { "Unsafe C ABI package extraction member" }
            val output = canonicalRoot.resolve(entry.name).canonicalFile
            check(output.toPath().startsWith(canonicalRoot.toPath())) { "C ABI package extraction escaped its root" }
            output.parentFile.mkdirs()
            archive.getInputStream(entry).use { input -> Files.copy(input, output.toPath()) }
        }
    }
}

private fun runCAbiProcess(
    command: List<String>,
    environment: Map<String, String> = emptyMap(),
    allowedExitCodes: Set<Int> = setOf(0),
): String {
    check(command.isNotEmpty() && command.all { '\u0000' !in it }) { "Invalid C ABI evidence command" }
    val log = Files.createTempFile("codex-agent-c-abi-process-", ".log").toFile()
    return try {
        val process = ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log).apply {
            environment().putAll(environment)
        }.start()
        val completed = process.waitFor(5, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        val exit = if (completed) process.exitValue() else -1
        val output = log.readText()
        check(exit in allowedExitCodes) { "C ABI evidence command failed ($exit): ${command.first()}\n$output" }
        output
    } finally {
        log.delete()
    }
}

private fun parseCAbiConsumerProof(value: kotlinx.serialization.json.JsonElement): CrossLanguageCAbiConsumerProof {
    val record = value.jsonObject
    check(record.keys == setOf(
        "source", "sourceSha256", "language", "compilerIdentitySha256", "compileOutputSha256",
        "artifactSha256", "linked", "executed", "exitCode",
    )) { "C ABI strict consumer evidence schema mismatch" }
    return CrossLanguageCAbiConsumerProof(
        record.strictString("source"), record.strictSha256("sourceSha256"), record.strictString("language"),
        record.strictSha256("compilerIdentitySha256"), record.strictSha256("compileOutputSha256"),
        record.strictSha256("artifactSha256"), record.strictBoolean("linked"), record.strictBoolean("executed"),
        record.strictInt("exitCode"),
    )
}

private fun checkedCAbiTarget(target: String, classifier: String): CrossLanguageCAbiTargetSpec {
    check(crossLanguageCAbiTargetSpecs.keys == setOf("macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64")) {
        "C ABI package target inventory drift"
    }
    val spec = crossLanguageCAbiTargetSpecs[target] ?: error("Unsupported C ABI package target: $target")
    check(classifier == spec.classifier) { "C ABI package target/classifier mismatch" }
    return spec
}

private fun checkIdentity(version: String, commit: String, tree: String) {
    check(version.matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?"))) {
        "C ABI package library version is invalid"
    }
    check(commit.matches(Regex("[0-9a-f]{40}"))) { "C ABI package producer commit is not immutable" }
    check(tree.matches(Regex("[0-9a-f]{40}"))) { "C ABI package producer tree is not immutable" }
}

private fun CrossLanguageCAbiTargetSpec.expectedVersionIdentity(): String = when (format) {
    "mach-o" -> "compatibility=1.0.0,current=1.12.0"
    "elf" -> (0..12).joinToString(",") { "CODEX_AGENT_1.$it" }
    else -> "abi=1.12"
}

private fun CrossLanguageCAbiTargetSpec.requiredToolIds(): Set<String> = when (format) {
    "mach-o" -> setOf("c", "cpp", "file", "architecture", "symbols", "loader", "versions")
    "elf" -> setOf("c", "cpp", "file", "architecture", "symbols", "loader", "versions")
    else -> setOf("c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport")
}

private fun headerSymbols(header: File): Set<String> = Regex("\\b(codex_agent_[A-Za-z0-9_]+)\\s*\\(")
    .findAll(header.readText()).map { it.groupValues[1] }.toCollection(sortedSetOf())

private fun normalizedCAbiSymbols(output: String): Set<String> = C_ABI_SYMBOL.findAll(output).map { match ->
    match.groupValues[1].removePrefix("_").substringBefore('@')
}.filter { it.startsWith("codex_agent_") }.toCollection(sortedSetOf())

internal fun crossLanguageCAbiGnuImportSymbols(output: String): Set<String> = output.lineSequence().mapNotNull { line ->
    C_ABI_SYMBOL.matchEntire(line.trim().takeLastWhile { !it.isWhitespace() })?.groupValues?.get(1)?.removePrefix("_")
}.toCollection(sortedSetOf())

private fun safeCAbiPackagePath(path: String): Boolean {
    if (path.isBlank() || path.startsWith('/') || path.startsWith('\\') || '\\' in path || ':' in path) return false
    val parts = path.split('/')
    return parts.none { it.isBlank() || it == "." || it == ".." } && File(path).invariantSeparatorsPath == path
}

private fun safeToolExecutable(value: String): Boolean = value.isNotBlank() && '\n' !in value && '\r' !in value && '\u0000' !in value
private fun regularCAbiFile(file: File): Boolean = file.isFile && !Files.isSymbolicLink(file.toPath()) && file.length() > 0L

private fun String.normalized(root: File): String = replace(root.absolutePath, "<WORK>").replace("\\", "/")
private fun String.sha256(): String = encodeToByteArray().inputStream().releaseDigest()
private fun Set<String>.sortedNewlineSha256(): String = sorted().joinToString(separator = "", transform = { "$it\n" }).sha256()
private fun String.isSha256(): Boolean = matches(Regex("[0-9a-f]{64}"))

private fun JsonObject.strictString(name: String): String {
    val primitive = getValue(name).jsonPrimitive
    check(primitive.isString) { "C ABI evidence field is not a string: $name" }
    return primitive.content
}

private fun JsonObject.strictSha256(name: String): String = strictString(name).also {
    check(it.isSha256()) { "C ABI evidence SHA-256 is invalid: $name" }
}

private fun JsonObject.strictInt(name: String): Int {
    val primitive = getValue(name).jsonPrimitive
    check(!primitive.isString) { "C ABI evidence field is not an integer: $name" }
    return primitive.content.toInt()
}

private fun JsonObject.strictLong(name: String): Long {
    val primitive = getValue(name).jsonPrimitive
    check(!primitive.isString) { "C ABI evidence field is not an integer: $name" }
    return primitive.content.toLong()
}

private fun JsonObject.strictBoolean(name: String): Boolean {
    val primitive = getValue(name).jsonPrimitive
    check(!primitive.isString && primitive.content in setOf("true", "false")) {
        "C ABI evidence field is not a boolean: $name"
    }
    return primitive.content.toBooleanStrict()
}

private fun JsonObject.strictArray(name: String): JsonArray = getValue(name).jsonArray

private val C_ABI_SYMBOL = Regex("(?<![A-Za-z0-9_])(_?codex_agent_[A-Za-z0-9_]+)(?![A-Za-z0-9_])")
private val LINUX_VERSION_NODE = Regex("^(CODEX_AGENT_1\\.\\d+) \\{$")
private val LINUX_VERSION_SYMBOL = Regex("^(codex_agent_[A-Za-z0-9_]+);$")
private val LINUX_DYNAMIC_VERSIONED_SYMBOL =
    Regex("(?<![A-Za-z0-9_])(_?codex_agent_[A-Za-z0-9_]+)@@(CODEX_AGENT_1\\.\\d+)(?![A-Za-z0-9_.])")
private val C_ABI_ZIP_EPOCH: LocalDateTime = LocalDateTime.of(1980, 1, 1, 0, 0)
private const val C_ABI_PACKAGE_MANIFEST = "codex-agent-c-abi-manifest.json"
private const val C_ABI_HEADER_PATH = "include/codex_agent.h"
private const val C_ABI_FILE_MODE = 0x81a4
private val C_ABI_GNU_CONSUMERS = setOf("codex_agent_abi_smoke.c", "codex_agent_header_smoke.cpp")
