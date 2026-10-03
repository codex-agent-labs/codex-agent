import org.gradle.api.Project
import org.gradle.api.file.Directory
import org.gradle.api.file.RegularFile
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.TaskProvider
import org.gradle.api.tasks.bundling.Zip
import org.gradle.kotlin.dsl.named
import org.gradle.kotlin.dsl.register

data class IosAppleDistributionTasks(
    val appleDistributionDirectory: Provider<Directory>,
    val releaseXCFrameworkDirectory: Provider<Directory>,
    val privacyManifestFile: RegularFile,
    val sdkCompatibilityFile: Provider<RegularFile>?,
    val prepareCodexAgentReleaseXCFramework: TaskProvider<PrepareCodexAgentReleaseXCFrameworkTask>,
    val packageCodexAgentAppleDistribution: TaskProvider<Zip>,
    val verifyCodexAgentSwiftPackage: TaskProvider<Exec>,
    val verifyCodexAgentSwiftAuthenticationTests: TaskProvider<VerifySwiftAuthenticationTestsTask>,
    val verifyIosLicensePackaging: TaskProvider<VerifyIosLicensePackagingTask>,
)

internal fun requirePairedAppleFrameworkImports(device: Boolean, simulator: Boolean) {
    check(device == simulator) {
        "Imported Apple device and simulator frameworks must be supplied together"
    }
}

internal fun Project.usesAppleBinaryPackageInputs(): Boolean {
    val mode = providers.gradleProperty("codexAgent.iosPackageFromBinary").orNull ?: return false
    check(mode == "true" &&
        providers.gradleProperty("codexAgent.product").orNull == "sdk" &&
        providers.gradleProperty("codexAgent.component").orNull == "sdk-ios" &&
        providers.gradleProperty("codexAgent.phase").orNull == "package" &&
        providers.gradleProperty("codexAgent.target").orNull == "ios") {
        "Apple binary package mode requires the exact SDK iOS package phase"
    }
    listOf("codexAgent.sdkIosBinaryStageRoot", "codexAgent.sdkCompatibilityRequest").forEach {
        check(!providers.gradleProperty(it).orNull.isNullOrBlank()) { "Apple binary package mode requires $it" }
    }
    listOf(
        IOS_VERIFIED_DISTRIBUTION_PROPERTY, "codexAgent.iosExpectedDistributionProof",
        "codexAgent.iosExpectedSdkCompatibility", "codexAgent.iosNativeEvidenceDirectory",
        "codexAgent.iosDeviceFrameworkDirectory", "codexAgent.iosSimulatorFrameworkDirectory",
    ).forEach {
        check(!providers.gradleProperty(it).isPresent) { "Apple binary package mode rejects override $it" }
    }
    check(!providers.environmentVariable("CODEX_AGENT_IMPORTED_SWIFT_ZIP").isPresent) {
        "Apple binary package mode rejects imported Swift ZIP override"
    }
    return true
}

fun Project.registerIosAppleDistributionTasks(
    expectedSwiftTestIdentifiers: List<String>,
    pinnedRustToolchain: String,
    appleFrameworkToolchainIdentity: Provider<String>,
    importedDeviceFramework: TaskProvider<ImportCodexAgentFrameworkTask>?,
    importedSimulatorFramework: TaskProvider<ImportCodexAgentFrameworkTask>?,
): IosAppleDistributionTasks {
    val appleDistributionDirectory = layout.buildDirectory.dir("apple-distribution")
    val assembledXCFrameworkDirectory = layout.buildDirectory.dir("XCFrameworks/release/CodexAgent.xcframework")
    val releaseXCFrameworkDirectory = layout.buildDirectory.dir("release-xcframework/CodexAgent.xcframework")
    val privacyManifestFile = layout.projectDirectory.file("apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy")
    val licenseFile = rootProject.layout.projectDirectory.file("LICENSE")
    val thirdPartyNotices = rootProject.layout.projectDirectory.file("THIRD_PARTY_NOTICES.md")
    val codexLicense = rootProject.layout.projectDirectory.file(
        "legal/openai-codex/openai-codex-LICENSE.txt",
    )
    val codexNotice = rootProject.layout.projectDirectory.file(
        "legal/openai-codex/openai-codex-NOTICE.txt",
    )
    val sdkCompatibility = if (providers.gradleProperty("codexAgent.sdkCompatibilityRequest").isPresent) {
        project(":codex-agent-sdk").layout.buildDirectory.file(
            providers.gradleProperty("codexAgent.candidateTree").map {
                "sdk-compatibility/$it/META-INF/codex-agent/sdk-compatibility.json"
            },
        )
    } else {
        null
    }

    val assembleDependency: Any = when {
        importedDeviceFramework != null && importedSimulatorFramework != null ->
            tasks.register<AssembleImportedCodexAgentXCFrameworkTask>("assembleCodexAgentReleaseXCFrameworkFromImports") {
                dependsOn(importedDeviceFramework, importedSimulatorFramework)
                deviceFrameworkDirectory.set(importedDeviceFramework.flatMap { it.importedFrameworkDirectory })
                simulatorFrameworkDirectory.set(importedSimulatorFramework.flatMap { it.importedFrameworkDirectory })
                appleToolchainIdentity.set(appleFrameworkToolchainIdentity)
                xcframeworkDirectory.set(assembledXCFrameworkDirectory)
            }
        importedDeviceFramework == null && importedSimulatorFramework == null ->
            "assembleCodexAgentReleaseXCFramework"
        else -> providers.provider {
            requirePairedAppleFrameworkImports(
                importedDeviceFramework != null,
                importedSimulatorFramework != null,
            )
            "assembleCodexAgentReleaseXCFramework"
        }
    }
    val prepareCodexAgentReleaseXCFramework =
        tasks.register<PrepareCodexAgentReleaseXCFrameworkTask>("prepareCodexAgentReleaseXCFramework") {
            dependsOn(assembleDependency)
            this.assembledXCFrameworkDirectory.set(assembledXCFrameworkDirectory)
            privacyManifest.set(privacyManifestFile)
            forbiddenAbsolutePathPrefixes.set(iosReleaseAbsolutePathPrefixes(pinnedRustToolchain))
            appleToolchainIdentity.set(appleFrameworkToolchainIdentity)
            this.releaseXCFrameworkDirectory.set(releaseXCFrameworkDirectory)
        }

    val stageCodexAgentAppleDistribution =
        tasks.register<StageCodexAgentAppleDistributionTask>("stageCodexAgentAppleDistribution") {
            dependsOn(prepareCodexAgentReleaseXCFramework)
            if (sdkCompatibility != null) {
                dependsOn(":codex-agent-sdk:generateNativeWrapperSdkCompatibility")
                this.sdkCompatibility.set(sdkCompatibility)
            }
            packageManifest.set(layout.projectDirectory.file("apple/Package.swift"))
            sourcesDirectory.set(layout.projectDirectory.dir("apple/Sources"))
            testsDirectory.set(layout.projectDirectory.dir("apple/Tests"))
            xcframeworkDirectory.set(releaseXCFrameworkDirectory)
            this.licenseFile.set(licenseFile)
            this.thirdPartyNotices.set(thirdPartyNotices)
            this.codexLicense.set(codexLicense)
            this.codexNotice.set(codexNotice)
            testApplication.set(layout.projectDirectory.dir("apple/TestApp"))
            distributionDirectory.set(appleDistributionDirectory)
        }

    val verifyCodexAgentSwiftPackage = tasks.register<Exec>("verifyCodexAgentSwiftPackage") {
        dependsOn(stageCodexAgentAppleDistribution)
        workingDir(appleDistributionDirectory.map { it.dir("CodexAgentTestApp") })
        commandLine(
            "xcodebuild",
            "-project", "CodexAgentTestApp.xcodeproj",
            "-scheme", "CodexAgentTestApp",
            "-configuration", "Release",
            "-destination", "generic/platform=iOS",
            "-derivedDataPath", layout.buildDirectory.dir("swift-consumer-derived-data").get().asFile.absolutePath,
            "-archivePath", layout.buildDirectory.file("CodexAgentTestApp.xcarchive").get().asFile.absolutePath,
            "ARCHS=arm64",
            "CODE_SIGNING_ALLOWED=NO",
            "SKIP_INSTALL=NO",
            "clean",
            "archive",
        )
    }

    val verifyCodexAgentSwiftAuthenticationTests =
        tasks.register<VerifySwiftAuthenticationTestsTask>("verifyCodexAgentSwiftAuthenticationTests") {
            dependsOn(stageCodexAgentAppleDistribution)
            packageDirectory.set(appleDistributionDirectory.map { it.dir("CodexAgentPackage") })
            providers.environmentVariable("CODEX_AGENT_SWIFT_COMPILATION_DIRECTORY").orNull?.let {
                compiledProductsDirectory.set(layout.dir(providers.provider { file(it) }))
            }
            runtimeName.set("iOS 26.5")
            deviceTypeIdentifier.set("com.apple.CoreSimulator.SimDeviceType.iPhone-17")
            this.expectedTestIdentifiers.set(expectedSwiftTestIdentifiers)
            derivedDataDirectory.set(layout.buildDirectory.dir("swift-simulator-compilation-derived-data"))
            simulatorDevicesFile.set(layout.buildDirectory.file("simulator-devices.json"))
            resultBundleDirectory.set(layout.buildDirectory.dir("swift-authentication-tests.xcresult"))
            summaryFile.set(layout.buildDirectory.file("swift-authentication-tests-summary.json"))
        }

    val packageCodexAgentAppleDistribution = tasks.register<Zip>("packageCodexAgentAppleDistribution") {
        dependsOn(stageCodexAgentAppleDistribution)
        archiveFileName.set("CodexAgentPackage-${project.version}.zip")
        destinationDirectory.set(layout.buildDirectory.dir("distributions"))
        isPreserveFileTimestamps = false
        isReproducibleFileOrder = true
        from(appleDistributionDirectory.map { it.dir("CodexAgentPackage") })
    }

    val verifyIosLicensePackaging = tasks.register<VerifyIosLicensePackagingTask>("verifyIosLicensePackaging") {
        dependsOn(stageCodexAgentAppleDistribution)
        packageDirectory.set(appleDistributionDirectory.map { it.dir("CodexAgentPackage") })
        this.licenseFile.set(licenseFile)
        this.thirdPartyNotices.set(thirdPartyNotices)
        this.codexLicense.set(codexLicense)
        this.codexNotice.set(codexNotice)
        buildScript.set(layout.projectDirectory.file("build.gradle.kts"))
        reportFile.set(layout.buildDirectory.file("reports/ios-release/license-packaging.txt"))
    }

    return IosAppleDistributionTasks(
        appleDistributionDirectory,
        releaseXCFrameworkDirectory,
        privacyManifestFile,
        sdkCompatibility,
        prepareCodexAgentReleaseXCFramework,
        packageCodexAgentAppleDistribution,
        verifyCodexAgentSwiftPackage,
        verifyCodexAgentSwiftAuthenticationTests,
        verifyIosLicensePackaging,
    )
}
