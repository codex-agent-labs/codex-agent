import java.io.File
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.artifacts.VersionCatalogsExtension
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
allprojects {
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
allprojects { group = CodexAgentBuild.MAVEN_GROUP }
applyProductVersions(rootProject, readProductVersions(rootProject))
val contractVersion = rootProject.extra["codexAgent.contractVersion"].toString()
val runtimeProductVersion = rootProject.extra["codexAgent.runtimeVersion"].toString()
val sdkProductVersion = rootProject.extra["codexAgent.sdkVersion"].toString()
val publicationKotlinVersion = rootProject.extensions.getByType<VersionCatalogsExtension>()
    .named("libs").findVersion("kotlin").get().requiredVersion
val sdkCoreProject = project(":codex-agent-core")
val sdkFacadeProject = project(":codex-agent-sdk")
val javaBindingParityReceiptFile = sdkCoreProject.layout.buildDirectory.file(
    "reports/cross-language-api/bindings/java-parity.json",
)
val invalidateJavaBindingParityOutput = sdkFacadeProject.tasks.register<Delete>(
    "invalidateJavaBindingParityOutput",
) {
    group = "verification"
    description = "Deletes stale Java parity evidence before SDK-owned prerequisites execute."
    delete(javaBindingParityReceiptFile)
}
val javaBindingInvalidationTaskNames = setOf(
    invalidateJavaBindingParityOutput.name,
    "invalidateJavaScriptTypeScriptBindingParityOutput",
    "invalidateCodexAgentAppleBindingEvidence",
    "invalidateCodexAgentCAbiBootstrapEvidence",
)
rootProject.allprojects {
    tasks.configureEach {
        if (name !in javaBindingInvalidationTaskNames) {
            mustRunAfter(invalidateJavaBindingParityOutput)
        }
    }
}
sdkCoreProject.tasks.register<VerifyJavaBindingParityTask>("verifyJavaBindingParity") {
    group = "verification"
    description = "Verifies SDK-owned Java parity in exact JVM, Android, and runtime artifacts."
    dependsOn(
        invalidateJavaBindingParityOutput,
        ":codex-agent-core:verifyCrossLanguageApiCoverage",
        ":codex-agent-core:jvmJar",
        ":codex-agent-core:bundleAndroidMainAar",
        ":codex-agent-runtime-desktop:jvmJar",
        ":codex-agent-runtime-android:bundleReleaseAar",
    )
    apiReport.set(sdkCoreProject.layout.buildDirectory.file(
        "reports/cross-language-api/canonical-api.json",
    ))
    canonicalCoverageReceipt.set(sdkCoreProject.layout.buildDirectory.file(
        "reports/cross-language-api/canonical-coverage.json",
    ))
    kotlinArtifact.set(sdkCoreProject.layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    coreJvmJar.set(sdkCoreProject.layout.buildDirectory.file(
        "libs/codex-agent-core-jvm-$contractVersion.jar",
    ))
    coreAndroidAar.set(sdkCoreProject.layout.buildDirectory.file("outputs/aar/codex-agent-core.aar"))
    desktopRuntimeJar.set(layout.projectDirectory.file(
        "codex-agent-runtime-desktop/build/libs/codex-agent-runtime-desktop-jvm-$runtimeProductVersion.jar",
    ))
    androidRuntimeAar.set(layout.projectDirectory.file(
        "codex-agent-runtime-android/build/outputs/aar/codex-agent-runtime-android-release.aar",
    ))
    compiledJavaTests.set(sdkCoreProject.layout.buildDirectory.dir("classes/java/jvmTest"))
    testResults.set(sdkCoreProject.layout.buildDirectory.dir("test-results/jvmTest"))
    receiptFile.set(javaBindingParityReceiptFile)
}
val sdkFacadeConsumerRoot = layout.buildDirectory.dir("sdk-facade-consumer")
val sdkFacadeConsumerMavenRepository = sdkFacadeConsumerRoot.map { it.dir("maven-repository") }
listOf(":codex-agent-core", ":codex-agent-sdk").forEach { projectPath ->
    project(projectPath) {
        pluginManager.withPlugin("maven-publish") {
            extensions.configure<PublishingExtension> {
                repositories.maven {
                    name = "SDK_FACADE_CONSUMER_STAGING"
                    url = sdkFacadeConsumerMavenRepository.get().asFile.toURI()
                }
            }
        }
    }
}
val sdkFacadePublicationNames = facadePublicationSpecs.map {
    it.publication.replaceFirstChar(Char::uppercase)
}
val sdkFacadeMetadataGenerationTasks = sdkFacadePublicationNames.flatMap { publication ->
    listOf(
        ":codex-agent-sdk:generatePomFileFor${publication}Publication",
        ":codex-agent-sdk:generateMetadataFileFor${publication}Publication",
    )
} + listOf(":generatePomFileForMavenPublication", ":generateMetadataFileForMavenPublication")
val verifySdkFacadePublicationMetadata = tasks.register<VerifySdkFacadePublicationMetadataTask>(
    "verifySdkFacadePublicationMetadata",
) {
    group = "verification"
    description = "Verifies every facade publication and the SDK BOM against independent product versions."
    dependsOn(sdkFacadeMetadataGenerationTasks)
    facadePublications.set(project(":codex-agent-sdk").layout.buildDirectory.dir("publications"))
    bomPublications.set(layout.buildDirectory.dir("publications/maven"))
    groupId.set(CodexAgentBuild.MAVEN_GROUP)
    contractVersion.set(rootProject.extra["codexAgent.contractVersion"].toString())
    runtimeVersion.set(runtimeProductVersion)
    sdkVersion.set(sdkProductVersion)
    kotlinVersion.set(publicationKotlinVersion)
    forbiddenPath.set(layout.projectDirectory.asFile.absolutePath)
    resultFile.set(layout.buildDirectory.file("reports/sdk/facade-publication-metadata.json"))
}
rootProject.extensions.extraProperties["codexAgent.repositoryUrl"] =
    "https://github.com/${CodexAgentBuild.REPOSITORY}"
registerRepositoryVerificationTasks(contractVersion, runtimeProductVersion, sdkProductVersion)
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
    layout.projectDirectory.file("legal/openai-codex/openai-codex-LICENSE.txt")
val desktopBundledNoticeFile =
    layout.projectDirectory.file("legal/openai-codex/openai-codex-NOTICE.txt")
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
    candidateContractVersion.set(contractVersion)
    candidateRuntimeVersion.set(runtimeProductVersion)
    candidateSdkVersion.set(sdkProductVersion)
    mavenRepository.set(signedMavenInput)
}
tasks.register<AssemblePromotedCandidateTask>("assemblePromotedCandidate") {
    group = "publishing"
    description = "Signs and inventories exact promoted bytes without compiling or testing production sources."
    promotedArtifactsDirectory.set(promotedArtifactsInput)
    signedMavenRepository.set(signedMavenInput)
    candidateContractVersion.set(contractVersion)
    candidateRuntimeVersion.set(runtimeProductVersion)
    candidateSdkVersion.set(sdkProductVersion)
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
val resetSdkFacadeConsumerMavenRepository = tasks.register<Delete>(
    "resetSdkFacadeConsumerMavenRepository",
) {
    delete(sdkFacadeConsumerMavenRepository)
}
val sdkFacadeConsumerPublicationTasks = listOf(":codex-agent-core", ":codex-agent-sdk").flatMap { projectPath ->
    sdkFacadePublicationNames.map { publication ->
        "$projectPath:publish${publication}PublicationToSDK_FACADE_CONSUMER_STAGINGRepository"
    }
}
listOf(":codex-agent-core", ":codex-agent-sdk").forEach { projectPath ->
    project(projectPath).tasks.matching {
        it.name.endsWith("PublicationToSDK_FACADE_CONSUMER_STAGINGRepository")
    }.configureEach {
        dependsOn(resetSdkFacadeConsumerMavenRepository)
        mustRunAfter(resetSdkFacadeConsumerMavenRepository)
    }
}
val sdkFacadeConsumerMavenInventory = sdkFacadeConsumerRoot.map { it.file("maven-inventory.json") }
val inventorySdkFacadeConsumerMavenRepository = tasks.register(
    "inventorySdkFacadeConsumerMavenRepository",
) {
    dependsOn(sdkFacadeConsumerPublicationTasks)
    inputs.dir(sdkFacadeConsumerMavenRepository)
    inputs.property("repositoryPath", sdkFacadeConsumerMavenRepository.map { it.asFile.absolutePath })
    inputs.property("groupId", CodexAgentBuild.MAVEN_GROUP)
    inputs.property("version", sdkProductVersion)
    inputs.property(
        "expectedArtifacts",
        facadePublicationSpecs.flatMap { listOf(it.artifact, it.coreArtifact) }.toSortedSet().joinToString(","),
    )
    outputs.file(sdkFacadeConsumerMavenInventory)
    doLast {
        val repository = File(inputs.properties.getValue("repositoryPath").toString())
        val groupId = inputs.properties.getValue("groupId").toString()
        val groupRoot = repository.resolve(groupId.replace('.', '/'))
        check(groupRoot.isDirectory) { "SDK facade consumer Maven group is missing" }
        val expectedArtifacts = inputs.properties.getValue("expectedArtifacts").toString().split(',').toSet()
        val actualArtifacts = groupRoot.listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet()
        check(actualArtifacts == expectedArtifacts) {
            "SDK facade consumer Maven artifacts mismatch: expected=$expectedArtifacts actual=$actualArtifacts"
        }
        val files = repository.walkTopDown().filter(File::isFile).sortedBy {
            it.relativeTo(repository).invariantSeparatorsPath
        }.toList()
        check(files.isNotEmpty()) { "SDK facade consumer Maven repository is empty" }
        outputs.files.singleFile.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("groupId", JsonPrimitive(groupId))
            put("version", JsonPrimitive(inputs.properties.getValue("version").toString()))
            put("target", JsonPrimitive("sdk-facade"))
            put("files", buildJsonArray {
                files.forEach { file ->
                    add(file.releaseRecord(file.relativeTo(repository).invariantSeparatorsPath))
                }
            })
        })
    }
}
val sdkFacadeConsumerBuildTasks = linkedMapOf(
    "android" to listOf("compileAndroidMain"),
    "jvm" to listOf("compileKotlinJvm"),
    "ios-arm64" to listOf("compileKotlinIosArm64"),
    "ios-simulator-arm64" to listOf("compileKotlinIosSimulatorArm64"),
    "macos-arm64" to listOf("compileKotlinMacosArm64"),
    "macos-x64" to listOf("compileKotlinMacosX64"),
    "linux-arm64" to listOf("compileKotlinLinuxArm64"),
    "linux-x64" to listOf("compileKotlinLinuxX64"),
    "windows-x64" to listOf("compileKotlinMingwX64"),
    "node-js" to listOf("compileKotlinJs"),
    "node-wasm" to listOf("compileKotlinWasmJs"),
)
val sdkFacadeConsumerTasks = sdkFacadeConsumerBuildTasks.mapValues { (target, buildTasks) ->
    tasks.register<VerifyStagedKmpConsumerTask>(
        "verifySdkFacadeConsumer${target.split('-').joinToString("") { it.replaceFirstChar(Char::uppercase) }}",
    ) {
        group = "verification"
        description = "Compiles the isolated $target SDK facade consumer without Runtime sources or artifacts."
        dependsOn(inventorySdkFacadeConsumerMavenRepository)
        repositoryDirectory.set(sdkFacadeConsumerMavenRepository)
        templateDirectory.set(layout.projectDirectory.dir("gradle/release/sdk-facade-consumer-template"))
        mavenInventory.set(sdkFacadeConsumerMavenInventory)
        gradleWrapper.set(layout.projectDirectory.file("gradlew"))
        sdkVersion.set(sdkProductVersion)
        runtimeVersion.set(runtimeProductVersion)
        androidSdkDirectory.set(rootAndroidSdkDirectory)
        targetName.set(target)
        this.buildTasks.set(buildTasks)
        consumerDirectory.set(sdkFacadeConsumerRoot.map { it.dir("consumer-$target") })
        resultFile.set(sdkFacadeConsumerRoot.map { it.file("reports/$target.json") })
    }
}
val verifySdkFacadeConsumers = tasks.register("verifySdkFacadeConsumers") {
    group = "verification"
    description = "Compiles all 11 isolated SDK facade target consumers from staged Maven artifacts."
    dependsOn(sdkFacadeConsumerTasks.values)
}
val importedSdkBindingEvidence = layout.dir(
    providers.gradleProperty(SDK_BINDING_EVIDENCE_DIRECTORY_PROPERTY).map(::file),
)
val importedSdkCanonicalApiReport = layout.file(
    providers.gradleProperty(SDK_CANONICAL_API_REPORT_PROPERTY).map(::file),
)
val importedSdkCanonicalCoverageReceipt = layout.file(
    providers.gradleProperty(SDK_CANONICAL_COVERAGE_RECEIPT_PROPERTY).map(::file),
)
val importedSdkBindingParityReport =
    layout.buildDirectory.file("reports/sdk/imported-binding-parity.json")
val invalidateImportedSdkBindingParityOutput = sdkFacadeProject.tasks.register<Delete>(
    "invalidateImportedSdkBindingParityOutput",
) {
    group = "verification"
    description = "Deletes stale imported SDK binding parity output before input validation."
    delete(importedSdkBindingParityReport)
}
rootProject.tasks.matching { it.name == "prepareContractInputs" }.configureEach {
    mustRunAfter(invalidateImportedSdkBindingParityOutput)
}
val verifyImportedSdkBindingParity = tasks.register<VerifyImportedSdkBindingParityTask>(
    "verifyImportedSdkBindingParity",
) {
    group = "verification"
    description = "Verifies the exact imported M11 evidence for all 11 first-class SDK languages."
    dependsOn(invalidateImportedSdkBindingParityOutput)
    canonicalApiReport.set(importedSdkCanonicalApiReport)
    canonicalCoverageReceipt.set(importedSdkCanonicalCoverageReceipt)
    evidenceDirectory.set(importedSdkBindingEvidence)
    resultFile.set(importedSdkBindingParityReport)
}
val verifySdkBindingParity = tasks.register("verifySdkBindingParity") {
    group = "verification"
    description = "Verifies exact imported cross-language SDK parity without rebuilding product owners."
    dependsOn(verifyImportedSdkBindingParity)
}
verifySdkFacadePublicationMetadata.configure { dependsOn(verifySdkBindingParity) }
verifySdkFacadeConsumers.configure { dependsOn(verifySdkBindingParity) }
tasks.register("verifySdk") {
    group = "verification"
    description = "Verifies the SDK facade and exact imported cross-language parity evidence."
    dependsOn(
        verifySdkFacadePublicationMetadata,
        verifySdkFacadeConsumers,
        verifySdkBindingParity,
    )
}
fun publicationTask(module: String, publication: String, target: String) =
    ":$module:publish${publication}PublicationTo${stagedConsumerRepositoryNames.getValue(target)}Repository"
fun rootPublicationTask(publication: String, target: String) =
    ":publish${publication}PublicationTo${stagedConsumerRepositoryNames.getValue(target)}Repository"
val stagedConsumerPublicationTasks = mapOf(
    "common" to listOf(
        rootPublicationTask("Maven", "common"),
        publicationTask("codex-agent-core", "KotlinMultiplatform", "common"),
        publicationTask("codex-agent-core", "Jvm", "common"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "common"),
        publicationTask("codex-agent-sdk", "Jvm", "common"),
    ),
    "android" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "android"),
        publicationTask("codex-agent-core", "Android", "android"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "android"),
        publicationTask("codex-agent-sdk", "Android", "android"),
        publicationTask("codex-agent-runtime-android", "Maven", "android"),
    ),
    "desktop" to listOf("KotlinMultiplatform", "Jvm", "MacosArm64", "MacosX64", "LinuxArm64", "LinuxX64", "MingwX64")
        .flatMap { publication -> listOf(
            publicationTask("codex-agent-core", publication, "desktop"),
            publicationTask("codex-agent-sdk", publication, "desktop"),
            publicationTask("codex-agent-runtime-desktop", publication, "desktop"),
        ) },
    "ios-device" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "ios-device"),
        publicationTask("codex-agent-core", "IosArm64", "ios-device"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "ios-device"),
        publicationTask("codex-agent-sdk", "IosArm64", "ios-device"),
        publicationTask("codex-agent-runtime-ios", "KotlinMultiplatform", "ios-device"),
        publicationTask("codex-agent-runtime-ios", "IosArm64", "ios-device"),
    ),
    "ios-simulator" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "ios-simulator"),
        publicationTask("codex-agent-core", "IosSimulatorArm64", "ios-simulator"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "ios-simulator"),
        publicationTask("codex-agent-sdk", "IosSimulatorArm64", "ios-simulator"),
        publicationTask("codex-agent-runtime-ios", "KotlinMultiplatform", "ios-simulator"),
        publicationTask("codex-agent-runtime-ios", "IosSimulatorArm64", "ios-simulator"),
    ),
    "node-js" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "node-js"),
        publicationTask("codex-agent-core", "Js", "node-js"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "node-js"),
        publicationTask("codex-agent-sdk", "Js", "node-js"),
        publicationTask("codex-agent-runtime-desktop", "KotlinMultiplatform", "node-js"),
        publicationTask("codex-agent-runtime-desktop", "Js", "node-js"),
    ),
    "node-wasm" to listOf(
        publicationTask("codex-agent-core", "KotlinMultiplatform", "node-wasm"),
        publicationTask("codex-agent-core", "WasmJs", "node-wasm"),
        publicationTask("codex-agent-sdk", "KotlinMultiplatform", "node-wasm"),
        publicationTask("codex-agent-sdk", "WasmJs", "node-wasm"),
        publicationTask("codex-agent-runtime-desktop", "KotlinMultiplatform", "node-wasm"),
        publicationTask("codex-agent-runtime-desktop", "WasmJs", "node-wasm"),
    ),
)
val stagedConsumerGroupId = project.group.toString()
val stagedConsumerContractVersion = contractVersion
val stagedConsumerRuntimeVersion = runtimeProductVersion
val stagedConsumerSdkVersion = sdkProductVersion
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
        inputs.property("contractVersion", stagedConsumerContractVersion)
        inputs.property("runtimeVersion", stagedConsumerRuntimeVersion)
        inputs.property("sdkVersion", stagedConsumerSdkVersion)
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
                put("contractVersion", JsonPrimitive(inputs.properties.getValue("contractVersion").toString()))
                put("runtimeVersion", JsonPrimitive(inputs.properties.getValue("runtimeVersion").toString()))
                put("sdkVersion", JsonPrimitive(inputs.properties.getValue("sdkVersion").toString()))
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
        sdkVersion.set(project.version.toString())
        runtimeVersion.set(rootProject.extra["codexAgent.runtimeVersion"].toString())
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
    expectedContractVersion.set(contractVersion)
    expectedRuntimeVersion.set(runtimeProductVersion)
    expectedSdkVersion.set(sdkProductVersion)
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
