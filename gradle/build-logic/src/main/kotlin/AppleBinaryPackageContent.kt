import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption

/**
 * Compares caller-authenticated private snapshots. This grants no receipt, producer, host,
 * compiler, XCTest, source, or replay authority.
 */
internal fun verifyAppleBinaryPackageArchives(
    productDirectory: File,
    version: String,
    expectedPackageDirectory: File,
    expectedXCFrameworkDirectory: File,
    sdkCompatibility: File,
    workDirectory: File,
) {
    check(PRODUCT_SEMVER.matches(version)) { "Apple binary package content version is invalid" }
    val inputPaths = listOf(
        productDirectory,
        expectedPackageDirectory,
        expectedXCFrameworkDirectory,
        sdkCompatibility,
    )
    inputPaths.forEach { requireApplePackagePathWithoutSymlinks(it, "binary package content input") }
    requireApplePackagePathWithoutSymlinks(workDirectory, "binary package content work")

    val product = productDirectory.canonicalFile
    val expectedPackage = expectedPackageDirectory.canonicalFile
    val expectedXCFramework = expectedXCFrameworkDirectory.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val work = workDirectory.canonicalFile
    check(compatibility.isFile && compatibility.length() > 0L &&
        !Files.isSymbolicLink(compatibility.toPath())) {
        "Apple binary package compatibility input is missing or unsafe"
    }
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple binary package content work directory already exists"
    }
    listOf(product, expectedPackage, expectedXCFramework, compatibility).forEach { input ->
        check(!work.toPath().startsWith(input.toPath()) && !input.toPath().startsWith(work.toPath())) {
            "Apple binary package content work overlaps an input"
        }
    }

    val productFiles = verifiedRegularFiles(product)
    val packageFiles = verifiedRegularFiles(expectedPackage)
    val xcframeworkFiles = verifiedRegularFiles(expectedXCFramework)
    check(productFiles.keys == appleVerifiedArtifactNames(version)) {
        "Apple binary package product inventory mismatch"
    }
    check(packageFiles.isNotEmpty() && xcframeworkFiles.isNotEmpty()) {
        "Apple binary package expected content is empty"
    }
    val compatibilityPaths = listOf("ios-arm64", "ios-arm64-simulator").map { slice ->
        "$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json"
    }
    check(xcframeworkFiles.keys.intersect(compatibilityPaths.toSet()).isEmpty()) {
        "Apple binary package expected XCFramework is already decorated"
    }

    fun digests(files: Map<String, File>) = files.mapValues { (_, file) -> file.releaseDigest() }
    val productDigests = digests(productFiles)
    val packageDigests = digests(packageFiles)
    val xcframeworkDigests = digests(xcframeworkFiles)
    val compatibilityBytes = compatibility.readBytes()
    val compatibilityDigest = compatibility.releaseDigest()
    val swiftArchive = productFiles.getValue("CodexAgent-$version.xcframework.zip")
    val checksum = productFiles.getValue("CodexAgent-$version.xcframework.zip.sha256")
    check(checksum.readBytes().contentEquals("${swiftArchive.releaseDigest()}\n".toByteArray())) {
        "Apple binary package checksum is not exact"
    }

    val extractedPackage = work.resolve("package")
    val extractedXCFramework = work.resolve("xcframework")
    extractStrictAppleArchive(
        productFiles.getValue("CodexAgentPackage-$version.zip"),
        extractedPackage,
        "",
    )
    extractStrictAppleArchive(swiftArchive, extractedXCFramework, "CodexAgent.xcframework/")
    verifyAppleSdkCompatibility(productFiles, version, compatibilityDigest)

    val actualPackage = verifiedRegularFiles(extractedPackage)
    check(actualPackage.keys == packageFiles.keys && packageFiles.all { (path, expected) ->
        Files.mismatch(expected.toPath(), actualPackage.getValue(path).toPath()) == -1L
    }) { "Apple binary package archive content mismatch" }

    val actualXCFramework = verifiedRegularFiles(extractedXCFramework)
    check(actualXCFramework.keys == xcframeworkFiles.keys + compatibilityPaths &&
        xcframeworkFiles.all { (path, expected) ->
            Files.mismatch(expected.toPath(), actualXCFramework.getValue(path).toPath()) == -1L
        } && compatibilityPaths.all { path ->
            Files.mismatch(compatibility.toPath(), actualXCFramework.getValue(path).toPath()) == -1L
        }) { "Apple binary XCFramework archive content mismatch" }

    inputPaths.forEach { requireApplePackagePathWithoutSymlinks(it, "binary package content input recheck") }
    check(verifiedRegularFiles(product).let { it.keys == productFiles.keys && digests(it) == productDigests } &&
        verifiedRegularFiles(expectedPackage).let { it.keys == packageFiles.keys && digests(it) == packageDigests } &&
        verifiedRegularFiles(expectedXCFramework).let {
            it.keys == xcframeworkFiles.keys && digests(it) == xcframeworkDigests
        } && compatibility.isFile && !Files.isSymbolicLink(compatibility.toPath()) &&
        compatibility.readBytes().contentEquals(compatibilityBytes)) {
        "Apple binary package content input changed during verification"
    }
}
