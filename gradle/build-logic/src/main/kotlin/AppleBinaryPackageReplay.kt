import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption

/**
 * Exact package replay over caller-private authenticated inputs. The caller binds source policy,
 * original binary receipts, compatibility and actual toolchain identity; this grants no host/test trust.
 * This invokes assembly/packaging tools only, never a compiler or XCTest.
 */
internal fun verifyAppleBinaryPackageReplay(
    productDirectory: File,
    version: String,
    binaryFrameworks: File,
    sourceSnapshot: File,
    sdkCompatibility: File,
    workDirectory: File,
    forbiddenAbsolutePathPrefixes: List<String>,
    capture: (List<String>) -> String,
    scan: (List<String>) -> Pair<Int, String>,
) {
    check(PRODUCT_SEMVER.matches(version)) { "Apple binary package version is invalid" }
    val inputs = listOf(productDirectory, binaryFrameworks, sourceSnapshot, sdkCompatibility)
    (inputs + workDirectory).forEach { requireApplePackagePathWithoutSymlinks(it, "binary package replay") }
    requireOriginalAppleSnapshotDisjoint(workDirectory.canonicalFile, inputs)
    check(!Files.exists(workDirectory.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple binary package replay work must be fresh"
    }
    val productBefore = verifiedRegularFiles(productDirectory).mapValues { it.value.releaseDigest() }
    val binaryBefore = verifiedRegularFiles(binaryFrameworks).mapValues { it.value.releaseDigest() }
    check(binaryBefore.isNotEmpty() && binaryBefore.keys.all { path ->
        listOf("ios-arm64", "ios-simulator-arm64").any { path.startsWith("$it/CodexAgent.framework/") }
    }) { "Apple binary package replay requires exactly the two original framework trees" }
    check(sdkCompatibility.isFile && sdkCompatibility.length() > 0) { "Apple compatibility input is missing" }
    val compatibilityBefore = sdkCompatibility.releaseDigest()
    val apple = sourceSnapshot.resolve("codex-agent-runtime-ios/apple")
    val assembled = workDirectory.resolve("assembled/CodexAgent.xcframework")
    val release = workDirectory.resolve("release/CodexAgent.xcframework")
    val privacy = apple.resolve("Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy")
    val sourceInputs = AppleDistributionInputs(
        apple.resolve("Package.swift"), apple.resolve("Sources"), apple.resolve("Tests"), release,
        sourceSnapshot.resolve("LICENSE"), sourceSnapshot.resolve("THIRD_PARTY_NOTICES.md"),
        sourceSnapshot.resolve("legal/openai-codex/openai-codex-LICENSE.txt"),
        sourceSnapshot.resolve("legal/openai-codex/openai-codex-NOTICE.txt"),
        sdkCompatibility, apple.resolve("TestApp"),
    )
    val sourceFiles = listOf(sourceInputs.packageManifest, sourceInputs.license, sourceInputs.thirdPartyNotices,
        sourceInputs.codexLicense, sourceInputs.codexNotice, privacy)
    val sourceTrees = listOf(sourceInputs.sources, sourceInputs.tests, sourceInputs.testApplication)
    sourceFiles.forEach {
        requireApplePackagePathWithoutSymlinks(it, "binary package source")
        check(it.isFile && it.length() > 0) { "Apple binary package source is missing: $it" }
    }
    val sourceBefore = sourceFiles.associateWith { it.releaseDigest() }
    sourceTrees.forEach { requireApplePackagePathWithoutSymlinks(it, "binary package source tree") }
    val treesBefore = sourceTrees.associateWith { tree -> verifiedRegularFiles(tree).mapValues { it.value.releaseDigest() } }
    val device = binaryFrameworks.resolve("ios-arm64/CodexAgent.framework")
    val simulator = binaryFrameworks.resolve("ios-simulator-arm64/CodexAgent.framework")
    verifyImportedAppleFramework(device, "iPhoneOS", capture)
    verifyImportedAppleFramework(simulator, "iPhoneSimulator", capture)
    assembled.parentFile.mkdirs()
    capture(importedXCFrameworkAssemblyCommand(device, simulator, assembled))
    prepareAppleReleaseXCFramework(assembled, release, privacy, forbiddenAbsolutePathPrefixes, capture, scan)
    val distribution = workDirectory.resolve("distribution")
    stageAppleDistribution(sourceInputs, distribution)
    verifyAppleBinaryPackageArchives(productDirectory, version, distribution.resolve("CodexAgentPackage"),
        release, sdkCompatibility, workDirectory.resolve("comparison"))
    (inputs + sourceFiles + sourceTrees).forEach {
        requireApplePackagePathWithoutSymlinks(it, "binary package replay recheck")
    }
    check(verifiedRegularFiles(productDirectory).mapValues { it.value.releaseDigest() } == productBefore &&
        verifiedRegularFiles(binaryFrameworks).mapValues { it.value.releaseDigest() } == binaryBefore &&
        sdkCompatibility.releaseDigest() == compatibilityBefore &&
        sourceFiles.associateWith { it.releaseDigest() } == sourceBefore &&
        sourceTrees.associateWith { tree -> verifiedRegularFiles(tree).mapValues { it.value.releaseDigest() } } == treesBefore) {
        "Apple binary package replay input changed"
    }
}
