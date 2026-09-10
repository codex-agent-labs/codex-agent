import org.gradle.api.Project
import org.gradle.api.file.RegularFile
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.named
import org.gradle.kotlin.dsl.register

internal data class IosVerifiedDistributionTasks(
    val validateImported: TaskProvider<ImportAppleVerifiedDistributionTask>?,
    val importedXCFramework: TaskProvider<ImportVerifiedCodexAgentXCFrameworkTask>?,
    val importedSdkPackageArtifacts: TaskProvider<StageImportedAppleSdkPackageArtifactsTask>?,
)

internal fun Project.registerIosVerifiedDistributionTasks(
    distribution: IosAppleDistributionTasks,
    release: IosAppleReleaseVerificationTasks,
    runtimeMetrics: Provider<RegularFile>,
    appleCompilerEvidence: TaskProvider<AppleCompilerEvidenceTask>,
    appleBindingEvidence: TaskProvider<GenerateAppleBindingEvidenceTask>,
): IosVerifiedDistributionTasks {
    val candidateCommit = providers.gradleProperty("codexAgent.candidateCommit")
    val nativeEvidencePath = providers.gradleProperty("codexAgent.iosNativeEvidenceDirectory")
    val nativeEvidence = layout.dir(nativeEvidencePath.map(rootProject::file))
    val nativeReceipt = layout.buildDirectory.file("imported-rust/ios-native-evidence.json")
    val provenance = layout.projectDirectory.file("native/provenance.json")
    val packageSwift = rootProject.layout.projectDirectory.file("Package.swift")
    val xcode = layout.buildDirectory.file("reports/ios-release/toolchain/xcode.txt")
    val swift = layout.buildDirectory.file("reports/ios-release/toolchain/swift.txt")
    val reportFiles = files(
        release.verifyIosReleaseBudgets.flatMap { it.reportFile },
        release.verifyIosDeploymentTargets.flatMap { it.reportFile },
        distribution.verifyIosLicensePackaging.flatMap { it.reportFile },
        runtimeMetrics,
        release.verifyIosPrivacyManifest.flatMap { it.auditFile },
        release.verifyIosPrivacyManifest.flatMap { it.evidenceFile },
        release.verifyIosPrivacyManifest.flatMap { it.policyFile },
        release.verifyIosPrivacyManifest.flatMap { it.reviewFile },
        distribution.verifyCodexAgentSwiftAuthenticationTests.flatMap { it.summaryFile },
        layout.buildDirectory.file("reports/cross-language-api/apple/compiler-evidence.json"),
        layout.buildDirectory.file("reports/cross-language-api/apple/binding-evidence.json"),
        layout.buildDirectory.file("reports/cross-language-api/bindings/swift-parity.json"),
        layout.buildDirectory.file("reports/cross-language-api/bindings/objective-c-parity.json"),
    )
    val importedPath = providers.gradleProperty(IOS_VERIFIED_DISTRIBUTION_PROPERTY)
    val expectedSdkCompatibilityPath = providers.gradleProperty(
        "codexAgent.iosExpectedSdkCompatibility",
    )
    val expectedDistributionProofPath = providers.gradleProperty(
        "codexAgent.iosExpectedDistributionProof",
    )
    check(expectedSdkCompatibilityPath.isPresent == expectedDistributionProofPath.isPresent) {
        "Imported Apple SDK caller expectations must be supplied together"
    }
    tasks.register<ExportAppleVerifiedDistributionTask>("exportCodexAgentIosVerifiedDistribution") {
        dependsOn("verifyIosRuntime", "validateImportedCodexAgentIosNativeEvidence")
        this.candidateCommit.set(candidateCommit)
        version.set(project.version.toString())
        freshSemanticVerification.set(importedPath.map { false }.orElse(true))
        applePackageArchive.set(distribution.packageCodexAgentAppleDistribution.flatMap { it.archiveFile })
        swiftPackageArchive.set(release.packageCodexAgentSwiftPackageBinary.flatMap { it.archiveFile })
        swiftPackageChecksum.set(release.generateCodexAgentSwiftPackageChecksum.flatMap { it.outputFile })
        privacyReviewFile.set(release.verifyIosPrivacyManifest.flatMap { it.reviewFile })
        this.reportFiles.from(reportFiles)
        xcodeVersionFile.set(xcode); swiftVersionFile.set(swift)
        nativeEvidenceDirectory.set(nativeEvidence); nativeEvidenceReceipt.set(nativeReceipt)
        nativeProvenance.set(provenance); this.packageSwift.set(packageSwift)
        distribution.sdkCompatibilityFile?.let { sdkCompatibility.set(it) }
        if (distribution.sdkCompatibilityFile == null) {
            sdkCompatibility.set(providers.provider<RegularFile> {
                error("Original Apple export requires authenticated codexAgent.sdkCompatibilityRequest inputs")
            })
        }
        canonicalApiReport.set(appleBindingEvidence.flatMap { it.canonicalApiReport })
        canonicalCoverageReceipt.set(appleBindingEvidence.flatMap { it.canonicalCoverageReceipt })
        swiftConsumer.set(appleBindingEvidence.flatMap { it.swiftConsumer })
        objectiveCConsumer.set(appleBindingEvidence.flatMap { it.objectiveCConsumer })
        compilerRawDirectory.set(appleCompilerEvidence.flatMap { it.rawEvidenceDirectory })
        xcframeworkDirectory.set(appleBindingEvidence.flatMap { it.xcframeworkDirectory })
        xcresultDirectory.set(appleBindingEvidence.flatMap { it.xcresultDirectory })
        xctestPackageDirectory.set(appleBindingEvidence.flatMap { it.xctestPackageDirectory })
        xctestProductsDirectory.set(distribution.verifyCodexAgentSwiftAuthenticationTests.flatMap {
            it.derivedDataDirectory.dir("Build/Products")
        })
        repositoryDirectory.set(rootProject.layout.projectDirectory)
        canonicalBuildDirectory.set(layout.buildDirectory)
        outputDirectory.set(layout.buildDirectory.dir("apple-verified-distribution"))
        executionDirectory.set(layout.buildDirectory.dir("apple-verified-distribution-execution"))
    }
    if (!importedPath.isPresent) return IosVerifiedDistributionTasks(null, null, null)
    val validate = tasks.register<ImportAppleVerifiedDistributionTask>(
        "validateImportedCodexAgentIosVerifiedDistribution",
    ) {
        dependsOn("verifyAppleToolchain", "validateImportedCodexAgentIosNativeEvidence")
        if (distribution.sdkCompatibilityFile != null) {
            dependsOn(":codex-agent-sdk:generateNativeWrapperSdkCompatibility")
        }
        this.candidateCommit.set(candidateCommit)
        version.set(project.version.toString())
        evidenceDirectory.set(layout.dir(importedPath.map(rootProject::file)))
        nativeEvidenceDirectory.set(nativeEvidence); nativeEvidenceReceipt.set(nativeReceipt)
        nativeProvenance.set(provenance); this.packageSwift.set(packageSwift)
        distribution.sdkCompatibilityFile?.let { sdkCompatibility.set(it) }
        currentXcodeVersionFile.set(xcode); currentSwiftVersionFile.set(swift)
        repositoryDirectory.set(rootProject.layout.projectDirectory)
        canonicalBuildDirectory.set(layout.buildDirectory)
        verificationReceipt.set(layout.buildDirectory.file(
            "imported-verified-apple/verified-distribution-receipt.json",
        ))
    }
    distribution.packageCodexAgentAppleDistribution.configure {
        setDependsOn(listOf(validate)); onlyIf { false }
    }
    release.packageCodexAgentSwiftPackageBinary.configure {
        setDependsOn(listOf(validate)); onlyIf { false }
    }
    release.generateCodexAgentSwiftPackageChecksum.configure { setDependsOn(listOf(validate)) }
    val xcframework = tasks.register<ImportVerifiedCodexAgentXCFrameworkTask>(
        "importCodexAgentVerifiedXCFramework",
    ) {
        dependsOn(validate)
        evidenceDirectory.set(layout.dir(importedPath.map(rootProject::file)))
        verificationReceipt.set(validate.flatMap { it.verificationReceipt })
        version.set(project.version.toString())
        xcframeworkDirectory.set(layout.buildDirectory.dir(
            "imported-verified-apple/CodexAgent.xcframework",
        ))
    }
    val swiftPackage = tasks.register<ImportVerifiedCodexAgentSwiftPackageTask>(
        "importCodexAgentVerifiedSwiftPackage",
    ) {
        dependsOn(validate)
        evidenceDirectory.set(layout.dir(importedPath.map(rootProject::file)))
        verificationReceipt.set(validate.flatMap { it.verificationReceipt })
        version.set(project.version.toString())
        packageDirectory.set(layout.buildDirectory.dir(
            "imported-verified-apple/consumer/CodexAgentPackage",
        ))
    }
    val sdkPackageArtifactRoot = layout.buildDirectory.dir(
        "imported-verified-apple/sdk-package-artifact-task",
    )
    val sdkPackageArtifacts = tasks.register<StageImportedAppleSdkPackageArtifactsTask>(
        "stageImportedCodexAgentIosSdkPackageArtifacts",
    ) {
        dependsOn(validate)
        evidenceDirectory.set(layout.dir(importedPath.map(rootProject::file)))
        verificationReceipt.set(validate.flatMap { it.verificationReceipt })
        distribution.sdkCompatibilityFile?.let { sdkCompatibility.set(it) }
        nativeEvidenceDirectory.set(nativeEvidence)
        nativeEvidenceReceipt.set(nativeReceipt)
        version.set(project.version.toString())
        ownedBuildDirectory.set(sdkPackageArtifactRoot)
        workDirectory.set(sdkPackageArtifactRoot.map { it.dir("work") })
        outputDirectory.set(sdkPackageArtifactRoot.map { it.dir("outputs") })
        validationEvidenceDirectory.set(sdkPackageArtifactRoot.map { it.dir("validation-evidence") })
    }
    tasks.register<VerifyTransportedAppleSdkPackageClosureTask>(
        "verifyTransportedCodexAgentIosSdkPackageClosure",
    ) {
        dependsOn(sdkPackageArtifacts)
        productDirectory.set(sdkPackageArtifacts.flatMap { it.outputDirectory })
        validationEvidenceDirectory.set(sdkPackageArtifacts.flatMap { it.validationEvidenceDirectory })
        version.set(project.version.toString())
        ownedBuildDirectory.set(sdkPackageArtifactRoot)
        workDirectory.set(sdkPackageArtifactRoot.map { it.dir("transported-verification-work") })
        if (expectedSdkCompatibilityPath.isPresent) {
            expectedSdkCompatibility.set(layout.file(expectedSdkCompatibilityPath.map(rootProject::file)))
            expectedDistributionProof.set(layout.file(expectedDistributionProofPath.map(rootProject::file)))
        }
    }
    tasks.named<StageCodexAgentAppleDistributionTask>("stageCodexAgentAppleDistribution") {
        // The original package is imported; checkout Sources/Tests must never reconstruct it.
        onlyIf { false }
    }
    distribution.verifyCodexAgentSwiftAuthenticationTests.configure {
        dependsOn(swiftPackage)
        packageDirectory.set(swiftPackage.flatMap { it.packageDirectory })
    }
    distribution.verifyIosLicensePackaging.configure {
        dependsOn(swiftPackage)
        packageDirectory.set(swiftPackage.flatMap { it.packageDirectory })
    }
    val consumerDirectory = layout.buildDirectory.dir("imported-verified-apple/consumer/CodexAgentTestApp")
    val stageConsumer = tasks.register<Sync>("stageImportedAppleTestApplication") {
        dependsOn(swiftPackage)
        // TestApp is an explicit local consumer fixture, outside the unchanged imported SDK.
        from(layout.projectDirectory.dir("apple/TestApp"))
        into(consumerDirectory)
        includeEmptyDirs = false
        duplicatesStrategy = org.gradle.api.file.DuplicatesStrategy.FAIL
    }
    distribution.verifyCodexAgentSwiftPackage.configure {
        dependsOn(stageConsumer)
        workingDir(consumerDirectory)
    }
    return IosVerifiedDistributionTasks(validate, xcframework, sdkPackageArtifacts)
}
