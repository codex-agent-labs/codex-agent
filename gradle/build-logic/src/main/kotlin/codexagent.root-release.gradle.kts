import java.io.File
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.publish.PublishingExtension
val candidateCommitValue = providers.gradleProperty("codexAgent.candidateCommit")
val candidateReleaseTag = providers.gradleProperty("codexAgent.releaseTag")
val candidatePathCommit = candidateCommitValue.orElse("UNBOUND")
val candidateRoot = layout.buildDirectory.dir(candidatePathCommit.map { "protected-candidate/$it" })
val candidateReports = candidateRoot.map { it.dir("reports") }
val importedMavenRepository = providers.gradleProperty("codexAgent.mavenRepositoryDirectory")
val centralStagingDirectory = layout.dir(importedMavenRepository.map(::file))
    .orElse(candidateRoot.map { it.dir("maven-repository") })
val stagedConsumerTargets = listOf(
    "common", "android", "desktop", "ios-device", "ios-simulator", "node-js", "node-wasm",
)
val stagedConsumerRepositoryNames = stagedConsumerTargets.associateWith { target ->
    "CONSUMER_${target.replace('-', '_').uppercase()}_STAGING"
}
val stagedConsumerRepositories = stagedConsumerTargets.associateWith { target ->
    if (importedMavenRepository.isPresent) centralStagingDirectory else candidateRoot.map { root ->
        if (target == "common") root.dir("payload/maven") else root.dir("consumer-maven/$target")
    }
}
subprojects {
    pluginManager.withPlugin("maven-publish") {
        extensions.configure<PublishingExtension> {
            repositories.maven {
                name = "CENTRAL_STAGING"
                url = centralStagingDirectory.get().asFile.toURI()
            }
            if (!importedMavenRepository.isPresent) {
                stagedConsumerTargets.forEach { target ->
                    repositories.maven {
                        name = stagedConsumerRepositoryNames.getValue(target)
                        url = stagedConsumerRepositories.getValue(target).get().asFile.toURI()
                    }
                }
            }
        }
    }
}
allprojects {
    group = CodexAgentBuild.MAVEN_GROUP
    version = "0.2.0"
}
rootProject.extensions.extraProperties["codexAgent.repositoryUrl"] =
    "https://github.com/${CodexAgentBuild.REPOSITORY}"
registerRepositoryVerificationTasks()
tasks.register<VerifyReleaseMetadataTask>("verifyReleaseMetadata") {
    group = "verification"
    projectVersion.set(project.version.toString())
    releaseTag.set(providers.gradleProperty("codexAgent.releaseTag").orElse("v${project.version}"))
    swiftPackageManifest.set(layout.projectDirectory.file("Package.swift"))
    remoteConsumerManifest.set(layout.projectDirectory.file("codex-agent-runtime-ios/apple/RemoteConsumer/Package.swift"))
}
val publicationApprovals = layout.projectDirectory.file("gradle/release/publication-approvals.json")
val privacyManifestFile = layout.projectDirectory.file(
    "codex-agent-runtime-ios/apple/Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy",
)
val privacyDataFlowReviewFile = layout.projectDirectory.file("gradle/release/privacy-data-flow-review.json")
val iosResourcePolicyFile = layout.projectDirectory.file("gradle/release/ios-resource-policy.json")
val privacyRequiredReasonReviewTemplate = layout.projectDirectory.file("gradle/release/privacy-required-reason-review.json")
val privacyRequiredReasonReviewOverride =
    layout.file(providers.gradleProperty("codexAgent.privacyRequiredReasonReview").map { File(it) })
val desktopDistributionManifestFile =
    layout.projectDirectory.file("codex-agent-runtime-desktop/codex-app-server-distributions.json")
val desktopBundledLicenseFile =
    layout.projectDirectory.file("codex-agent-runtime-android/src/main/assets/openai-codex-LICENSE.txt")
val desktopBundledNoticeFile =
    layout.projectDirectory.file("codex-agent-runtime-android/src/main/assets/openai-codex-NOTICE.txt")
val promotedArtifactsInput = layout.dir(
    providers.gradleProperty("codexAgent.promotedArtifactsDirectory").map(::file),
)
val signedMavenInput = layout.dir(
    providers.gradleProperty("codexAgent.signedMavenRepository").map(::file),
)
tasks.register<StagePromotedMavenPrimariesTask>("stagePromotedMavenPrimaries") {
    group = "publishing"
    description = "Forwards each canonical promoted Maven primary without rebuilding it."
    promotedArtifactsDirectory.set(promotedArtifactsInput)
    candidateCommit.set(candidateCommitValue)
    candidateVersion.set(project.version.toString())
    mavenRepository.set(signedMavenInput)
}
tasks.register<AssemblePromotedCandidateTask>("assemblePromotedCandidate") {
    group = "publishing"
    description = "Signs and inventories exact promoted bytes without compiling or testing production sources."
    promotedArtifactsDirectory.set(promotedArtifactsInput)
    signedMavenRepository.set(signedMavenInput)
    candidateVersion.set(project.version.toString())
    releaseTag.set(candidateReleaseTag)
    candidateCommit.set(candidateCommitValue)
    candidateTree.set(providers.gradleProperty("codexAgent.candidateTree"))
    promotionRunId.set(providers.gradleProperty("codexAgent.promotionRunId").map(String::toLong))
    promotionRunAttempt.set(providers.gradleProperty("codexAgent.promotionRunAttempt").map(String::toInt))
    approvalsFile.set(publicationApprovals)
    privacyManifest.set(privacyManifestFile)
    privacyDataFlowReview.set(privacyDataFlowReviewFile)
    privacyReviewTemplate.set(privacyRequiredReasonReviewTemplate)
    iosResourcePolicy.set(iosResourcePolicyFile)
    packageSwift.set(layout.projectDirectory.file("Package.swift"))
    remoteConsumerManifest.set(layout.projectDirectory.file("codex-agent-runtime-ios/apple/RemoteConsumer/Package.swift"))
    desktopDistributionManifest.set(desktopDistributionManifestFile)
    desktopBundledLicense.set(desktopBundledLicenseFile)
    desktopBundledNotice.set(desktopBundledNoticeFile)
    releaseTooling.set(layout.file(providers.gradleProperty("codexAgent.releaseTooling").map(::file)))
    repositoryDirectory.set(layout.projectDirectory)
    payloadDirectory.set(candidateRoot.map { it.dir("payload") })
}
tasks.register<VerifyPublicationReadinessTask>("verifyPublicationReadiness") {
    group = "verification"
    approvalsFile.set(publicationApprovals)
    privacyManifest.set(privacyManifestFile)
    privacyInventory.set(privacyDataFlowReviewFile)
    desktopDistributionManifest.set(desktopDistributionManifestFile)
    desktopBundledLicense.set(desktopBundledLicenseFile)
    desktopBundledNotice.set(desktopBundledNoticeFile)
}
val rootLocalProperties = layout.projectDirectory.file("local.properties")
val rootAndroidSdkDirectory = providers.environmentVariable("ANDROID_HOME").orElse(
    providers.fileContents(rootLocalProperties).asText.map { contents ->
        contents.lineSequence().single { it.startsWith("sdk.dir=") }.substringAfter('=')
    },
)
fun publicationTask(module: String, publication: String, target: String) =
    ":$module:publish${publication}PublicationTo${stagedConsumerRepositoryNames.getValue(target)}Repository"
val stagedConsumerPublicationTasks = mapOf(
    "common" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "common"),
        publicationTask("codex-agent-core", "Jvm", "common"),
    ),
    "android" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "android"),
        publicationTask("codex-agent-core", "Android", "android"),
        publicationTask("codex-agent-runtime-android", "Maven", "android"),
    ),
    "desktop" to listOf("KotlinMultiplatform", "Jvm", "MacosArm64", "MacosX64", "LinuxArm64", "LinuxX64", "MingwX64")
        .flatMap { publication -> listOf(
            publicationTask("codex-agent-core", publication, "desktop"),
            publicationTask("codex-agent-runtime-desktop", publication, "desktop"),
        ) },
    "ios-device" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "ios-device"),
        publicationTask("codex-agent-core", "IosArm64", "ios-device"),
        publicationTask("codex-agent-runtime-ios", "KotlinMultiplatform", "ios-device"),
        publicationTask("codex-agent-runtime-ios", "IosArm64", "ios-device"),
    ),
    "ios-simulator" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "ios-simulator"),
        publicationTask("codex-agent-core", "IosSimulatorArm64", "ios-simulator"),
        publicationTask("codex-agent-runtime-ios", "KotlinMultiplatform", "ios-simulator"),
        publicationTask("codex-agent-runtime-ios", "IosSimulatorArm64", "ios-simulator"),
    ),
    "node-js" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "node-js"),
        publicationTask("codex-agent-core", "Js", "node-js"),
        publicationTask("codex-agent-runtime-desktop", "KotlinMultiplatform", "node-js"),
        publicationTask("codex-agent-runtime-desktop", "Js", "node-js"),
    ),
    "node-wasm" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "node-wasm"),
        publicationTask("codex-agent-core", "WasmJs", "node-wasm"),
        publicationTask("codex-agent-runtime-desktop", "KotlinMultiplatform", "node-wasm"),
        publicationTask("codex-agent-runtime-desktop", "WasmJs", "node-wasm"),
    ),
)
val stagedConsumerGroupId = project.group.toString()
val stagedConsumerVersion = project.version.toString()
val stagedConsumerTasks = linkedMapOf(
    "common" to "verifyStagedKmpConsumerCommon",
    "android" to "verifyStagedKmpConsumerAndroid",
    "desktop" to "verifyStagedKmpConsumerDesktop",
    "ios-device" to "verifyStagedKmpConsumerIosDevice",
    "ios-simulator" to "verifyStagedKmpConsumerIosSimulator",
    "node-js" to "verifyStagedKmpConsumerNodeJs",
    "node-wasm" to "verifyStagedKmpConsumerNodeWasm",
).mapValues { (target, taskName) ->
    val repository = stagedConsumerRepositories.getValue(target)
    val targetInventory = candidateReports.map { it.file("maven-inventory-$target.json") }
    val inventoryTask = tasks.register("inventory${target.split('-').joinToString("") {
        it.replaceFirstChar(Char::uppercase)
    }}ConsumerMavenRepository") {
        if (!importedMavenRepository.isPresent) {
            dependsOn(stagedConsumerPublicationTasks.getValue(target))
        }
        inputs.dir(repository)
        inputs.property("repositoryPath", repository.map { it.asFile.absolutePath })
        inputs.property("groupId", stagedConsumerGroupId)
        inputs.property("version", stagedConsumerVersion)
        inputs.property("target", target)
        outputs.file(targetInventory)
        doLast {
            val root = File(inputs.properties.getValue("repositoryPath").toString())
            val inventoryTarget = inputs.properties.getValue("target").toString()
            check(root.isDirectory) { "Staged $inventoryTarget Maven repository is missing" }
            val files = root.walkTopDown().filter(File::isFile).sortedBy {
                it.relativeTo(root).invariantSeparatorsPath
            }.toList()
            check(files.isNotEmpty()) { "Staged $inventoryTarget Maven repository is empty" }
            outputs.files.singleFile.atomicWriteJson(buildJsonObject {
                put("schemaVersion", JsonPrimitive(1))
                put("groupId", JsonPrimitive(inputs.properties.getValue("groupId").toString()))
                put("version", JsonPrimitive(inputs.properties.getValue("version").toString()))
                put("target", JsonPrimitive(inventoryTarget))
                put("files", buildJsonArray {
                    files.forEach { file -> add(file.releaseRecord(file.relativeTo(root).invariantSeparatorsPath)) }
                })
            })
        }
    }
    tasks.register<VerifyStagedKmpConsumerTask>(taskName) {
        group = "verification"
        description = "Builds the isolated $target consumer from CENTRAL_STAGING only."
        dependsOn(inventoryTask)
        repositoryDirectory.set(repository)
        templateDirectory.set(layout.projectDirectory.dir("gradle/release/kmp-consumer-template"))
        mavenInventory.set(targetInventory)
        gradleWrapper.set(layout.projectDirectory.file("gradlew"))
        projectVersion.set(project.version.toString())
        androidSdkDirectory.set(rootAndroidSdkDirectory)
        targetName.set(target)
        buildTasks.set(stagedConsumerBuildTasks.getValue(target))
        consumerDirectory.set(candidateRoot.map { it.dir("clean-consumer-$target") })
        resultFile.set(candidateReports.map { it.file("kmp-consumer-$target.json") })
    }
}
tasks.register<VerifyCandidatePayloadTask>("verifyCandidatePayload") {
    githubOutputFile.set(providers.gradleProperty("codexAgent.githubOutputFile").map(layout.projectDirectory::file))
    group = "verification"
    description = "Verifies every transported candidate byte and repository policy binding."
    manifestFile.set(layout.file(providers.gradleProperty("codexAgent.candidateManifest").map(::file)))
    payloadDirectory.set(layout.dir(providers.gradleProperty("codexAgent.candidatePayload").map(::file)))
    expectedVersion.set(project.version.toString())
    expectedTag.set(candidateReleaseTag)
    expectedCommit.set(candidateCommitValue)
    approvalsFile.set(publicationApprovals)
    privacyManifest.set(privacyManifestFile)
    privacyDataFlowReview.set(privacyDataFlowReviewFile)
    iosResourcePolicy.set(iosResourcePolicyFile)
    privacyReviewTemplate.set(privacyRequiredReasonReviewTemplate)
    privacyReviews.set(privacyRequiredReasonReviewOverride)
    packageSwift.set(layout.projectDirectory.file("Package.swift"))
    desktopDistributionManifest.set(desktopDistributionManifestFile)
    desktopBundledLicense.set(desktopBundledLicenseFile)
    desktopBundledNotice.set(desktopBundledNoticeFile)
    outputFile.set(layout.buildDirectory.file("reports/release-candidate/payload-verification.json"))
}

tasks.register<VerifyPublicSwiftResolutionTask>("verifyPublicSwiftResolution") {
    group = "verification"
    description = "Verifies the public Swift asset bytes and clean SwiftPM resolution."
    assetUrl.set(
        "https://github.com/${CodexAgentBuild.REPOSITORY}/releases/download/v${project.version}/" +
            "CodexAgent-${project.version}.xcframework.zip",
    )
    candidateManifest.set(layout.file(providers.gradleProperty("codexAgent.candidateManifest").map(::file)))
    consumerDirectory.set(layout.projectDirectory.dir("codex-agent-runtime-ios/apple/RemoteConsumer"))
    derivedDataDirectory.set(layout.buildDirectory.dir("public-swift-derived-data"))
    packagesDirectory.set(layout.buildDirectory.dir("public-swift-packages"))
    outputFile.set(layout.buildDirectory.file("reports/release-candidate/public-swift-resolution.json"))
}

registerCentralPortalTasks()
