import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS

/**
 * Replays caller-authenticated immutable private validation snapshots without granting receipt, producer, host,
 * or source authority.
 */
internal fun verifyAppleValidationBindingReplay(
    evidenceDirectory: File,
    productDirectory: File,
    sdkVersion: String,
    sdkCompatibility: File,
    canonicalApi: File,
    canonicalCoverage: File,
    consumerSourceDirectory: File,
    workDirectory: File,
) {
    val directoryInputs = listOf(evidenceDirectory, productDirectory, consumerSourceDirectory)
    val fileInputs = listOf(sdkCompatibility, canonicalApi, canonicalCoverage)
    (directoryInputs + fileInputs + workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "validation binding replay")
    }
    val evidence = evidenceDirectory.canonicalFile
    val product = productDirectory.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val api = canonicalApi.canonicalFile
    val coverage = canonicalCoverage.canonicalFile
    val consumers = consumerSourceDirectory.canonicalFile
    val work = workDirectory.canonicalFile
    check(directoryInputs.map(File::getCanonicalFile).all(File::isDirectory) &&
        fileInputs.map(File::getCanonicalFile).all { it.isFile && !Files.isSymbolicLink(it.toPath()) }) {
        "Apple validation binding replay input is missing or unsafe"
    }
    val canonicalDirectories = listOf(evidence, product, consumers)
    canonicalDirectories.indices.forEach { left ->
        (left + 1 until canonicalDirectories.size).forEach { right ->
            check(!canonicalDirectories[left].toPath().startsWith(canonicalDirectories[right].toPath()) &&
                !canonicalDirectories[right].toPath().startsWith(canonicalDirectories[left].toPath())) {
                "Apple validation binding replay directories overlap"
            }
        }
    }
    requireOriginalAppleSnapshotDisjoint(evidence, listOf(compatibility, api, coverage))
    requireOriginalAppleSnapshotDisjoint(work, directoryInputs + fileInputs)
    check(!Files.exists(work.toPath(), NOFOLLOW_LINKS)) {
        "Apple validation binding replay work directory must be fresh"
    }

    fun digests(root: File) = verifiedRegularFiles(root).mapValues { (_, file) -> file.releaseDigest() }
    val directoryDigests = mapOf(
        evidence to digests(evidence),
        product to digests(product),
        consumers to digests(consumers),
    )
    val fileDigests = fileInputs.map(File::getCanonicalFile).associateWith { file ->
        file.length() to file.releaseDigest()
    }
    val expectedConsumers = verifiedRegularFiles(consumers)
    check(expectedConsumers.keys == setOf(
        "CodexFailureSwiftConsumer.swift", "CodexFailureObjectiveCConsumer.m",
    ) && expectedConsumers.values.all { it.length() > 0L }) {
        "Apple validation binding replay consumer inventory differs"
    }

    try {
        val prepared = prepareAppleValidationPackageInputs(product, sdkVersion, compatibility, work)
        val preparedPackage = verifiedRegularFiles(prepared.packageDirectory)
        val preparedXCFramework = verifiedRegularFiles(prepared.xcframeworkDirectory)
        check(sameApplePackageFiles(
            preparedXCFramework, evidence.resolve("xcframework"), prepared.xcframeworkDirectory,
        )) { "Retained Apple validation XCFramework differs from the selected package" }
        listOf("xctest-package", "device-package").forEach { name ->
            check(sameApplePackageFiles(
                preparedPackage, evidence.resolve(name), prepared.packageDirectory,
            )) { "Retained Apple validation $name differs from the selected package" }
        }
        val retainedApi = evidence.resolve("canonical/canonical-api.json")
        val retainedCoverage = evidence.resolve("canonical/canonical-coverage.json")
        listOf(retainedApi, retainedCoverage).forEach {
            requireApplePackagePathWithoutSymlinks(it, "retained validation canonical input")
            check(it.isFile && !Files.isSymbolicLink(it.toPath())) {
                "Retained Apple validation canonical input is missing or unsafe"
            }
        }
        check(Files.mismatch(retainedApi.toPath(), api.toPath()) == -1L &&
            Files.mismatch(retainedCoverage.toPath(), coverage.toPath()) == -1L &&
            sameApplePackageFiles(expectedConsumers, evidence.resolve("consumer"), consumers)) {
            "Retained Apple validation canonical or consumer input differs from its caller expectation"
        }
        val canonical = readCrossLanguageCanonicalApiEvidence(api, coverage)
        verifyOriginalAppleBindingEvidence(
            canonical,
            evidence,
            evidence.resolve("reports/compiler-evidence.json"),
            evidence.resolve("reports/xctest-summary.json"),
            evidence.resolve("reports/binding-evidence.json"),
            evidence.resolve("reports/swift-parity.json"),
            evidence.resolve("reports/objective-c-parity.json"),
        )
    } finally {
        (directoryInputs + fileInputs).forEach {
            requireApplePackagePathWithoutSymlinks(it, "validation binding replay input recheck")
        }
        check(directoryDigests.all { (directory, expected) -> digests(directory) == expected } &&
            fileDigests.all { (file, expected) ->
                file.isFile && !Files.isSymbolicLink(file.toPath()) &&
                    file.length() == expected.first && file.releaseDigest() == expected.second
            }) { "Apple validation binding replay input changed during verification" }
    }
}
