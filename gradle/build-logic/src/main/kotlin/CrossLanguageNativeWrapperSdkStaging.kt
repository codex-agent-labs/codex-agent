import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

data class CrossLanguageNativeWrapperSdkInput(
    val libraryVersion: String,
    val producerCommit: String,
    val producerTree: String,
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

fun stageCrossLanguageNativeWrapperSdks(
    input: CrossLanguageNativeWrapperSdkInput,
    outputDirectory: File,
) {
    val targets = crossLanguageCAbiTargetSpecs.keys
    check(input.archives.keys == targets && input.evidence.keys == targets && input.references.keys == targets) {
        "Native wrapper C ABI SDK staging requires exactly all five targets"
    }
    check(!outputDirectory.exists()) { "Native wrapper C ABI SDK output is immutable: $outputDirectory" }
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
        staged.resolve("codex-agent-native-wrapper-sdks.json").atomicWriteJson(buildJsonObject {
            put("schemaVersion", 1)
            put("libraryVersion", input.libraryVersion)
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
