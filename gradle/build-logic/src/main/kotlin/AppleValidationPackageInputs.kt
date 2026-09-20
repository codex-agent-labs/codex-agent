import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption

/**
 * Extracted package inputs from caller-authenticated artifacts. This comparison grants no
 * receipt, producer, host, compiler, XCTest, source, or replay authority.
 */
internal data class AppleValidationPackageInputs(
    val packageDirectory: File,
    val xcframeworkDirectory: File,
)

internal fun prepareAppleValidationPackageInputs(
    productDirectory: File,
    sdkVersion: String,
    sdkCompatibility: File,
    workDirectory: File,
): AppleValidationPackageInputs {
    check(PRODUCT_SEMVER.matches(sdkVersion)) { "Apple validation package version is invalid" }
    val inputs = listOf(productDirectory, sdkCompatibility)
    (inputs + workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "validation package input")
    }
    val product = productDirectory.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val work = workDirectory.canonicalFile
    check(product.isDirectory && compatibility.isFile && compatibility.length() > 0L &&
        !Files.isSymbolicLink(compatibility.toPath())) {
        "Apple validation package input is missing or unsafe"
    }
    requireOriginalAppleSnapshotDisjoint(work, listOf(product, compatibility))
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple validation package work directory must be fresh"
    }

    fun digests(files: Map<String, File>) = files.mapValues { (_, file) -> file.releaseDigest() }
    val productFiles = verifiedRegularFiles(product)
    check(productFiles.keys == appleVerifiedArtifactNames(sdkVersion) &&
        productFiles.values.all { it.length() > 0L }) {
        "Apple validation package product inventory mismatch"
    }
    val productDigests = digests(productFiles)
    val compatibilityBytes = compatibility.readBytes()

    val captured = work.resolve("captured")
    val capturedArtifacts = productFiles.mapValues { (name, source) ->
        copyVerified(source, captured.resolve(name))
    }
    val capturedCompatibility = copyVerified(
        compatibility,
        captured.resolve("sdk-compatibility.json"),
    )
    val swiftArchive = capturedArtifacts.getValue("CodexAgent-$sdkVersion.xcframework.zip")
    check(capturedArtifacts.getValue("CodexAgent-$sdkVersion.xcframework.zip.sha256").readBytes()
        .contentEquals("${swiftArchive.releaseDigest()}\n".toByteArray())) {
        "Apple validation package checksum is not exact"
    }
    val packageDirectory = work.resolve("CodexAgentPackage")
    val xcframeworkDirectory = work.resolve("xcframework")
    extractStrictAppleArchive(
        capturedArtifacts.getValue("CodexAgentPackage-$sdkVersion.zip"),
        packageDirectory,
        "",
    )
    extractStrictAppleArchive(swiftArchive, xcframeworkDirectory, "CodexAgent.xcframework/")
    verifyAppleSdkCompatibility(capturedArtifacts, sdkVersion, capturedCompatibility.releaseDigest())

    val compatibilityPaths = setOf("ios-arm64", "ios-arm64-simulator").map { slice ->
        "$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json"
    }.toSet()
    val standalone = verifiedRegularFiles(xcframeworkDirectory)
    val undecorated = standalone.filterKeys { it !in compatibilityPaths }
    val nested = verifiedRegularFiles(packageDirectory.resolve("CodexAgent.xcframework"))
    check(undecorated.isNotEmpty() && standalone.keys == undecorated.keys + compatibilityPaths &&
        nested.keys == undecorated.keys && nested.all { (path, file) ->
            Files.mismatch(file.toPath(), undecorated.getValue(path).toPath()) == -1L
        }) {
        "Apple validation package embedded XCFramework differs from its standalone artifact"
    }

    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "validation package input recheck") }
    check(verifiedRegularFiles(product).let {
        it.keys == productFiles.keys && digests(it) == productDigests
    } && compatibility.isFile && !Files.isSymbolicLink(compatibility.toPath()) &&
        compatibility.readBytes().contentEquals(compatibilityBytes) &&
        capturedArtifacts.all { (name, file) ->
            Files.mismatch(file.toPath(), productFiles.getValue(name).toPath()) == -1L
        } && Files.mismatch(capturedCompatibility.toPath(), compatibility.toPath()) == -1L) {
        "Apple validation package input changed during extraction"
    }
    return AppleValidationPackageInputs(packageDirectory, xcframeworkDirectory)
}
