import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

data class CrossLanguageNativeWrapperSdkInput(
    val libraryVersion: String,
    val runtimeProductVersion: String,
    val sdkVersion: String,
    val producerCommit: String,
    val producerTree: String,
    val sdkCompatibility: File,
    val archives: Map<String, File>,
    val evidence: Map<String, File>,
    val references: Map<String, CrossLanguageNativeWrapperSdkReferenceInput>,
)

data class CrossLanguageNativeWrapperSdkReferenceInput(
    val reviewedHeader: File,
    val license: File,
    val notice: File,
    val exportPolicy: File,
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

private data class NativeWrapperSdkCompatibility(
    val bytes: ByteArray,
    val runtimeLibraryDigests: Map<String, String>,
)

private fun JsonElement.hasCanonicalKeyOrder(): Boolean = when (this) {
    is JsonObject -> keys.toList() == keys.sorted() && values.all(JsonElement::hasCanonicalKeyOrder)
    is JsonArray -> all(JsonElement::hasCanonicalKeyOrder)
    else -> true
}

private fun JsonObject.strictProductSha256(name: String): String = strictString(name).also {
    check(it.matches(Regex("sha256:[0-9a-f]{64}"))) {
        "SDK compatibility SHA-256 is invalid: $name"
    }
}

private fun stableSemverParts(value: String, label: String): List<Int> {
    check(PRODUCT_SEMVER.matches(value) && '-' !in value && '+' !in value) {
        "$label must be a stable SemVer"
    }
    return value.split('.').map(String::toInt)
}

private fun compatibleRangeBounds(value: String, label: String): Pair<List<Int>, List<Int>> {
    val parts = value.split(' ')
    check(parts.size == 2 && parts[0].startsWith(">=") && parts[1].startsWith("<") &&
        !parts[1].startsWith("<=")) {
        "$label must use exact '>=MAJOR.MINOR.PATCH <MAJOR.MINOR.PATCH' syntax"
    }
    val lower = stableSemverParts(parts[0].removePrefix(">="), "$label lower bound")
    val upper = stableSemverParts(parts[1].removePrefix("<"), "$label upper bound")
    check(compareValuesBy(lower, upper, { it[0] }, { it[1] }, { it[2] }) < 0) {
        "$label lower bound must precede its upper bound"
    }
    return lower to upper
}

private fun readNativeWrapperSdkCompatibility(
    file: File,
    sdkVersion: String,
    runtimeProductVersion: String,
): NativeWrapperSdkCompatibility {
    check(regularCAbiFile(file)) { "SDK compatibility declaration is missing or symbolic" }
    val bytes = file.readBytes()
    val contents = bytes.decodeToString()
    val root = releaseJson.parseToJsonElement(contents).jsonObject
    check(root.hasCanonicalKeyOrder() && contents == kotlinx.serialization.json.Json.encodeToString(
        kotlinx.serialization.json.JsonElement.serializer(), root,
    ) + "\n") { "SDK compatibility declaration is not canonically encoded" }
    check(root.keys == setOf("schemaVersion", "sdkVersion", "contract", "runtime", "platformRuntime") &&
        root.strictInt("schemaVersion") == 1 && root.strictString("sdkVersion") == sdkVersion) {
        "SDK compatibility declaration identity mismatch"
    }
    checkIdentity(sdkVersion, "0".repeat(40), "0".repeat(40))
    val contract = root.getValue("contract").jsonObject
    check(contract.keys == setOf("version", "digest")) {
        "SDK compatibility Contract schema mismatch"
    }
    checkIdentity(contract.strictString("version"), "0".repeat(40), "0".repeat(40))
    val contractDigest = contract.strictProductSha256("digest")
    val runtime = root.getValue("runtime").jsonObject
    check(runtime.keys == setOf(
        "compatibleReleaseRange", "compatibleRuntimeCompatibilityRange", "requiredIdentitySchema",
        "requiredContractDigest", "requiredAbiMajor", "minimumAbiMinor", "defaultRuntimeVersion",
        "defaultManifestSha256", "embeddedVariants",
    ) && runtime.strictString("defaultRuntimeVersion") == runtimeProductVersion) {
        "SDK compatibility Runtime identity mismatch"
    }
    checkIdentity(runtimeProductVersion, "0".repeat(40), "0".repeat(40))
    val releaseBounds = compatibleRangeBounds(
        runtime.strictString("compatibleReleaseRange"),
        "SDK compatibility Runtime release range",
    )
    val compatibilityBounds = compatibleRangeBounds(
        runtime.strictString("compatibleRuntimeCompatibilityRange"),
        "SDK compatibility Runtime compatibility range",
    )
    val selectedRuntime = stableSemverParts(runtimeProductVersion, "SDK default Runtime")
    check(
        compareValuesBy(selectedRuntime, releaseBounds.first, { it[0] }, { it[1] }, { it[2] }) >= 0 &&
            compareValuesBy(selectedRuntime, releaseBounds.second, { it[0] }, { it[1] }, { it[2] }) < 0,
    ) { "SDK default Runtime is outside its compatible release range" }
    val selectedCompatibility = stableSemverParts(
        runtimeCompatibilityVersion(runtimeProductVersion), "SDK default Runtime compatibility",
    )
    check(
        compareValuesBy(selectedCompatibility, compatibilityBounds.first, { it[0] }, { it[1] }, { it[2] }) >= 0 &&
            compareValuesBy(selectedCompatibility, compatibilityBounds.second, { it[0] }, { it[1] }, { it[2] }) < 0,
    ) { "SDK default Runtime compatibility is outside its compatible range" }
    check(runtime.strictInt("requiredIdentitySchema") == 1 &&
        runtime.strictInt("requiredAbiMajor") == 1 && runtime.strictInt("minimumAbiMinor") == 13) {
        "SDK compatibility Runtime identity or ABI policy mismatch"
    }
    check(runtime.strictProductSha256("requiredContractDigest") == contractDigest) {
        "SDK compatibility required Contract digest mismatch"
    }
    runtime.strictProductSha256("defaultManifestSha256")
    val expectedTargets = crossLanguageCAbiTargetSpecs.values
        .map { it.classifier.removePrefix("c-abi-") }
        .sorted()
    val variants = runtime.strictArray("embeddedVariants").map { value ->
        value.jsonObject.also { record ->
            check(record.keys == setOf(
                "target", "componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256",
            )) { "SDK compatibility embedded variant schema mismatch" }
            listOf("componentId", "bundleSha256", "manifestSha256", "runtimeLibrarySha256")
                .forEach(record::strictProductSha256)
        }
    }
    check(variants.map { it.strictString("target") } == expectedTargets) {
        "SDK compatibility must declare the exact five sorted Runtime targets"
    }
    check(variants.map { it.strictProductSha256("componentId") }.toSet().size == variants.size) {
        "SDK compatibility embedded component IDs must be unique"
    }
    check(variants.map { it.strictProductSha256("manifestSha256") }.toSet().size == variants.size) {
        "SDK compatibility embedded manifest digests must be unique"
    }
    val platforms = root.getValue("platformRuntime").jsonObject
    check(platforms.keys == setOf("android", "ios") && platforms.all { (_, value) ->
        value.jsonObject.let { record ->
            record.keys == setOf("owner", "desktopRuntimeApplicable") &&
                record.strictString("owner") == "sdk" &&
                record.getValue("desktopRuntimeApplicable").toString() == "false"
        }
    }) { "SDK compatibility platform Runtime ownership mismatch" }
    return NativeWrapperSdkCompatibility(
        bytes,
        variants.associate {
            it.strictString("target") to
                it.strictProductSha256("runtimeLibrarySha256").removePrefix("sha256:")
        },
    )
}

fun stageCrossLanguageNativeWrapperSdks(
    input: CrossLanguageNativeWrapperSdkInput,
    outputDirectory: File,
) {
    val targets = crossLanguageCAbiTargetSpecs.keys
    check(input.archives.keys == targets && input.evidence.keys == targets && input.references.keys == targets) {
        "Native wrapper C ABI SDK staging requires exactly all five targets"
    }
    check(!outputDirectory.exists()) { "Native wrapper C ABI SDK output is immutable: $outputDirectory" }
    val compatibility = readNativeWrapperSdkCompatibility(
        input.sdkCompatibility, input.sdkVersion, input.runtimeProductVersion,
    )
    val parent = outputDirectory.absoluteFile.parentFile.also(File::mkdirs)
    val temporary = Files.createTempDirectory(parent.toPath(), ".native-wrapper-sdks-").toFile()
    try {
        val staged = temporary.resolve("staged")
        val indexTargets = buildJsonArray {
            targets.sorted().forEach { target ->
                val spec = crossLanguageCAbiTargetSpecs.getValue(target)
                val archive = input.archives.getValue(target)
                val proof = input.evidence.getValue(target)
                check(regularCAbiFile(proof)) {
                    "Imported native wrapper C ABI evidence is missing or symbolic: $target"
                }
                checkIdentity(input.libraryVersion, input.producerCommit, input.producerTree)
                val reference = input.references.getValue(target)
                withPortableVerifiedCrossLanguageCAbiPackageEvidence(
                    target,
                    input.libraryVersion,
                    input.producerCommit,
                    input.producerTree,
                    archive,
                    proof,
                    reference.reviewedHeader,
                    reference.license,
                    reference.notice,
                    reference.exportPolicy,
                    reference.consumerSources,
                ) { report, verifiedRoot, evidenceBytes ->
                    val classifier = spec.classifier.removePrefix("c-abi-")
                    check(report.strictSha256("librarySha256") ==
                        compatibility.runtimeLibraryDigests.getValue(classifier)) {
                        "SDK compatibility Runtime library digest mismatch: $target"
                    }
                    val targetRoot = staged.resolve(classifier)
                    check(verifiedRoot.copyRecursively(targetRoot)) {
                        "Failed to retain the verified native wrapper C ABI SDK: $target"
                    }
                    val manifest = targetRoot.resolve("codex-agent-c-abi-manifest.json")
                    check(regularCAbiFile(manifest)) { "Staged native wrapper C ABI manifest is missing: $target" }
                    targetRoot.resolve("codex-agent-c-abi-evidence.json").writeBytes(evidenceBytes)
                    add(buildJsonObject {
                        put("target", target)
                        put("classifier", classifier)
                        put("archiveSha256", report.strictSha256("archiveSha256"))
                        put("evidenceSha256", evidenceBytes.inputStream().releaseDigest())
                        put("libraryPath", spec.libraryPath)
                        put("librarySha256", report.strictSha256("librarySha256"))
                        put("manifestSha256", manifest.releaseDigest())
                    })
                }
            }
        }
        staged.resolve("sdk-compatibility.json").writeBytes(compatibility.bytes)
        staged.resolve("codex-agent-native-wrapper-sdks.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", 1)
            put("libraryVersion", input.libraryVersion)
            put("runtimeProductVersion", input.runtimeProductVersion)
            put("sdkVersion", input.sdkVersion)
            put("sdkCompatibilitySha256", input.sdkCompatibility.releaseDigest())
            put("producerCommit", input.producerCommit)
            put("producerTree", input.producerTree)
            put("targets", indexTargets)
        })
        try {
            Files.move(staged.toPath(), outputDirectory.toPath(), StandardCopyOption.ATOMIC_MOVE)
        } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
            Files.move(staged.toPath(), outputDirectory.toPath())
        }
    } finally {
        temporary.deleteRecursively()
    }
}
fun materializeCrossLanguageNativeWrapperPackageAssets(
    stagedSdkDirectory: File,
    outputDirectory: File,
) {
    val indexFile = stagedSdkDirectory.resolve("codex-agent-native-wrapper-sdks.json")
    val index = readCrossLanguageNativeWrapperSdkIndex(stagedSdkDirectory)
    check(!outputDirectory.exists()) { "Native wrapper package asset output is immutable: $outputDirectory" }
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
            val cppCompatibility = staged.resolve(
                "cpp/native/$classifier/share/CodexAgent/native/sdk-compatibility.json",
            )
            cppCompatibility.parentFile.mkdirs()
            Files.copy(stagedSdkDirectory.resolve("sdk-compatibility.json").toPath(), cppCompatibility.toPath())
        }
        val compatibilityDestinations = listOf(
            "python/src/codex_agent/native/sdk-compatibility.json",
            "csharp/native/sdk-compatibility.json",
            "rust/native/sdk-compatibility.json",
            "dart/lib/src/native/sdk-compatibility.json",
        )
        compatibilityDestinations.forEach { path ->
            val destination = staged.resolve(path)
            destination.parentFile.mkdirs()
            Files.copy(stagedSdkDirectory.resolve("sdk-compatibility.json").toPath(), destination.toPath())
        }
        Files.copy(indexFile.toPath(), staged.resolve(indexFile.name).toPath())
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
    val stagedFiles = verifiedRegularFiles(stagedSdkDirectory)
    val expectedFiles = buildSet {
        add("codex-agent-native-wrapper-sdks.json")
        add("sdk-compatibility.json")
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val classifier = spec.classifier.removePrefix("c-abi-")
            listOf(
                C_ABI_HEADER_PATH,
                "LICENSE.txt",
                "THIRD_PARTY_NOTICES.md",
                spec.libraryPath,
                C_ABI_PACKAGE_MANIFEST,
                "codex-agent-c-abi-evidence.json",
            ).forEach { add("$classifier/$it") }
            if (spec.format == "elf") add("$classifier/lib/${spec.loaderIdentity}")
            spec.importLibraryPaths.forEach { add("$classifier/$it") }
        }
    }
    check(stagedFiles.keys == expectedFiles) {
        "Native wrapper SDK staging inventory is incomplete or unexpected"
    }
    val indexFile = stagedSdkDirectory.resolve("codex-agent-native-wrapper-sdks.json")
    check(regularCAbiFile(indexFile)) { "Native wrapper SDK index is missing" }
    val contents = indexFile.readText()
    val root = releaseJson.parseToJsonElement(contents).jsonObject
    check(contents == releaseJson.encodeToString(kotlinx.serialization.json.JsonElement.serializer(), root) + "\n") {
        "Native wrapper SDK index is not canonically encoded"
    }
    check(root.keys == setOf(
        "schemaVersion", "libraryVersion", "runtimeProductVersion", "sdkVersion",
        "sdkCompatibilitySha256", "producerCommit", "producerTree", "targets",
    ) &&
        root.strictInt("schemaVersion") == 1) {
        "Native wrapper SDK index schema mismatch"
    }
    val version = root.strictString("libraryVersion")
    val commit = root.strictString("producerCommit")
    val tree = root.strictString("producerTree")
    checkIdentity(version, commit, tree)
    val compatibilityFile = stagedSdkDirectory.resolve("sdk-compatibility.json")
    val compatibility = readNativeWrapperSdkCompatibility(
        compatibilityFile,
        root.strictString("sdkVersion"),
        root.strictString("runtimeProductVersion"),
    )
    check(compatibilityFile.releaseDigest() == root.strictSha256("sdkCompatibilitySha256")) {
        "Staged SDK compatibility declaration hash mismatch"
    }
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
                compatibility.runtimeLibraryDigests.getValue(classifier) == librarySha256 &&
                manifest.releaseDigest() == record.strictSha256("manifestSha256") &&
                evidence.releaseDigest() == record.strictSha256("evidenceSha256")) {
                "Native wrapper SDK target hash mismatch: $target"
            }
            CrossLanguageNativeWrapperSdkRecord(target, classifier, spec.libraryPath, librarySha256)
        },
    )
}
