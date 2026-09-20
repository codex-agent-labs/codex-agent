import java.io.File
import org.gradle.api.tasks.Delete
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension
import org.jetbrains.kotlin.gradle.plugin.mpp.apple.XCFramework
import org.jetbrains.kotlin.gradle.targets.native.tasks.KotlinNativeTest

private val codexRevision = "758ef40f50c1a458425c7cfbf1eb12cbc07af0b0"
private val codexArchiveSha256 = "6481974e9740023493eda1f240005cb1507d6969f79d6f6aa97092f967f3f0fc"
private val codexCargoLockSha256 = "0c32858e9c47d0acf82735c8620c96840a5381152eec63acad15d1acadb9edad"
private val resolvedCargoLockSha256 = layout.projectDirectory.file("native/provenance.json").asFile
    .readReleaseObject().releaseString("preparedCargoLockSha256")
private val libsqlite3SysVersion = "0.37.0"
private val libsqlite3SysArchiveSha256 = "b1f111c8c41e7c61a49cd34e44c7619462967221a6443b0ec299e0ac30cfb9b1"
private val expectedSqliteSourceSha256 = "9512509b1bccb7461f79bea8aad6280ae4699e925fa4804381b71f59e7efb0c5"
private val expectedPatchedSqliteSourceSha256 = "a0b50ae286c86c1890c2144641682820a42aa38021ad5fa9457d99c636f0d057"
private val pinnedRustToolchain = "1.95.0"
private val rustLibrary = "libcodex_agent_ios_bridge.a"
private val minimumIosVersion = "15.0"
private val expectedSwiftTestIdentifiers = listOf(
    "CodexAgentObservationTests/testBufferingCancellationAndDroppedStreamReleaseTheObservation()",
    "CodexAgentObservationTests/testCodexOperationErrorsExposeStructuredFailure()",
    "CodexAgentObservationTests/testObjectiveCConsumerExposesStructuredFailure()",
    "CodexAuthorizationBrowserTests/testGenericBrowserOpensTypedExternalURLAndCancelsPresentation()",
)
private val pinnedSqliteArchiveSha256 = "b1f111c8c41e7c61a49cd34e44c7619462967221a6443b0ec299e0ac30cfb9b1"
private val sqliteArchiveBytes = 5_295_554L
private val pinnedReleaseLto = "thin"
private val pinnedReleaseCodegenUnits = "8"
private val pinnedReleaseRustFlags = "-Cdebuginfo=0"
private val pinnedReleaseRustPathRemapPolicy = linkedMapOf(
    "releaseRustFlagsTransport" to "CARGO_ENCODED_RUSTFLAGS",
    "releaseRustPathRemapOrder" to "builderHome,cargoHome,rustSysroot,projectRoot,preparedCodexSource",
    "releaseRustBuilderHomePrefix" to "/codex-agent/builder-home",
    "releaseRustCargoHomePrefix" to "/codex-agent/cargo-home",
    "releaseRustSysrootPrefix" to "/codex-agent/rust-sysroot",
    "releaseRustProjectRootPrefix" to "/codex-agent/project",
    "releaseRustPreparedSourcePrefix" to "/codex-agent/prepared-source",
)
private val pinnedXcodeVersion = "26.6"
private val pinnedXcodeBuild = "17F113"
private val pinnedSwiftVersion = "6.3.3"

val nativeTasks = registerIosNativeTasks(
    IosNativeTaskConfiguration(
        codexRevision = codexRevision,
        codexArchiveSha256 = codexArchiveSha256,
        codexCargoLockSha256 = codexCargoLockSha256,
        resolvedCargoLockSha256 = resolvedCargoLockSha256,
        libsqlite3SysVersion = libsqlite3SysVersion,
        libsqlite3SysArchiveSha256 = libsqlite3SysArchiveSha256,
        expectedSqliteSourceSha256 = expectedSqliteSourceSha256,
        expectedPatchedSqliteSourceSha256 = expectedPatchedSqliteSourceSha256,
        pinnedRustToolchain = pinnedRustToolchain,
        pinnedRustSrcComponent = "required",
        rustLibrary = rustLibrary,
        minimumIosVersion = minimumIosVersion,
        pinnedSqliteArchiveSha256 = pinnedSqliteArchiveSha256,
        sqliteArchiveBytes = sqliteArchiveBytes,
        pinnedReleaseLto = pinnedReleaseLto,
        pinnedReleaseCodegenUnits = pinnedReleaseCodegenUnits,
        pinnedReleaseRustFlags = pinnedReleaseRustFlags,
        pinnedReleaseRustPathRemapPolicy = pinnedReleaseRustPathRemapPolicy,
    ),
)

val xcframework = XCFramework("CodexAgent")
val iosContractDependency: Any = if (rootProject.extra.has("codexAgent.authenticatedContractVersion")) {
    "${project.group}:codex-agent-core:${rootProject.extra["codexAgent.authenticatedContractVersion"]}"
} else {
    project(":codex-agent-core")
}
extensions.configure<KotlinMultiplatformExtension> {
    val device = iosArm64()
    val simulator = iosSimulatorArm64()
    listOf(device, simulator).forEach { target ->
        val rustTask = if (target == device) nativeTasks.prepareCodexAgentIosArm64RustSlice
            else nativeTasks.prepareCodexAgentIosSimulatorArm64RustSlice
        val rustArchive = if (target == device) nativeTasks.iosArm64RustArchive
            else nativeTasks.iosSimulatorArm64RustArchive
        target.compilations.getByName("main").cinterops.create("codexAgentIos") {
            defFile(layout.projectDirectory.file("src/nativeInterop/cinterop/codex_agent_ios.def"))
            includeDirs(layout.projectDirectory.dir("native/include"))
            extraOpts(
                "-libraryPath",
                rustArchive.get().asFile.parentFile.absolutePath,
                "-staticLibrary",
                rustLibrary,
            )
            tasks.named(interopProcessingTaskName).configure {
                dependsOn(rustTask)
                inputs.file(rustArchive)
            }
        }
        target.binaries.all {
            freeCompilerArgs +=
                "-Xoverride-konan-properties=osVersionMin.${target.konanTarget.name}=$minimumIosVersion"
        }
        target.binaries.framework {
            baseName = "CodexAgent"
            isStatic = true
            export(iosContractDependency)
            xcframework.add(this)
        }
    }
}

val iosRuntimeMetrics = layout.buildDirectory.file("reports/ios-release/runtime-metrics.json")
iosRuntimeMetrics.get().asFile.parentFile.mkdirs()
tasks.named<KotlinNativeTest>("iosSimulatorArm64Test") {
    val metricsFile = iosRuntimeMetrics.get().asFile
    environment("CODEX_AGENT_IOS_METRICS_PATH", metricsFile.absolutePath)
    environment("SIMCTL_CHILD_CODEX_AGENT_IOS_METRICS_PATH", metricsFile.absolutePath)
    outputs.file(metricsFile)
    doLast("verifyIosRuntimeMetrics") {
        check(metricsFile.isFile) { "iOS runtime metrics were not recorded" }
    }
}

val verifyAppleToolchain = registerAppleToolchainVerificationTask(
    pinnedXcodeVersion,
    pinnedXcodeBuild,
    pinnedSwiftVersion,
)
val binaryPackageMode = usesAppleBinaryPackageInputs()
val importedValidationMode = usesAppleSdkValidationInputs()
val validationPackageInputs = if (importedValidationMode) registerIosSdkValidationPackageInputs(
    layout.dir(providers.gradleProperty("codexAgent.iosValidationPackageStage").map(::file)),
    providers.gradleProperty("codexAgent.sdkVersion"),
    layout.file(providers.gradleProperty("codexAgent.sdkCompatibilityFile").map(::file)),
    providers.gradleProperty("codexAgent.candidateTree"),
    providers.gradleProperty("codexAgent.target").get(),
) else null
val packageBinarySnapshot = if (binaryPackageMode) project(":codex-agent-sdk").layout.buildDirectory.dir(
    providers.gradleProperty("codexAgent.candidateTree").map { "imported-sdk-binary-stages/$it/sdk-ios" },
) else null
val importedDeviceFrameworkPath = if (binaryPackageMode) checkNotNull(packageBinarySnapshot).map {
    it.dir("outputs/apple-binary/ios-arm64/CodexAgent.framework").asFile.path
} else providers.gradleProperty("codexAgent.iosDeviceFrameworkDirectory")
val importedSimulatorFrameworkPath = if (binaryPackageMode) checkNotNull(packageBinarySnapshot).map {
    it.dir("outputs/apple-binary/ios-simulator-arm64/CodexAgent.framework").asFile.path
} else providers.gradleProperty("codexAgent.iosSimulatorFrameworkDirectory")
val importedDeviceFramework = importedDeviceFrameworkPath.orNull?.let {
    tasks.register<ImportCodexAgentFrameworkTask>("importCodexAgentIosDeviceFramework") {
        if (binaryPackageMode) dependsOn(":codex-agent-sdk:verifyImportedSdkIosBinaryStage")
        frameworkDirectory.set(layout.dir(providers.provider { file(it) }))
        platformName.set("iphoneos")
        importedFrameworkDirectory.set(layout.buildDirectory.dir("imported-frameworks/device/CodexAgent.framework"))
    }
}
val importedSimulatorFramework = importedSimulatorFrameworkPath.orNull?.let {
    tasks.register<ImportCodexAgentFrameworkTask>("importCodexAgentIosSimulatorFramework") {
        if (binaryPackageMode) dependsOn(":codex-agent-sdk:verifyImportedSdkIosBinaryStage")
        frameworkDirectory.set(layout.dir(providers.provider { file(it) }))
        platformName.set("iphonesimulator")
        importedFrameworkDirectory.set(layout.buildDirectory.dir("imported-frameworks/simulator/CodexAgent.framework"))
    }
}
tasks.register<VerifyIosFreeDiskSpaceTask>("preflightIosRuntime") {
    group = "verification"
    description = "Requires enough free disk and the pinned Apple toolchain before the full iOS gate."
    dependsOn(verifyAppleToolchain)
    minimumFreeGiB.set(
        providers.gradleProperty("codexAgent.iosMinimumFreeDiskGiB").map { value -> value.toLong() }.orElse(40L),
    )
    workspaceDirectory.set(rootProject.layout.projectDirectory)
    reportFile.set(layout.buildDirectory.file("reports/ios-development/preflight.json"))
}
tasks.register<VerifySwiftSimulatorCompilationTask>("verifyCodexAgentSwiftSimulatorCompilation") {
    group = "verification"
    description = "Compiles the Swift package and tests against only the simulator framework."
    dependsOn(verifyAppleToolchain)
    if (importedSimulatorFramework != null) dependsOn(importedSimulatorFramework)
    else dependsOn("linkDebugFrameworkIosSimulatorArm64")
    packageManifest.set(layout.projectDirectory.file("apple/Package.swift"))
    sourcesDirectory.set(layout.projectDirectory.dir("apple/Sources"))
    testsDirectory.set(layout.projectDirectory.dir("apple/Tests"))
    simulatorFrameworkDirectory.set(
        importedSimulatorFramework?.flatMap { it.importedFrameworkDirectory }
            ?: layout.buildDirectory.dir("bin/iosSimulatorArm64/debugFramework/CodexAgent.framework"),
    )
    this.expectedXcodeVersion.set(pinnedXcodeVersion)
    this.expectedXcodeBuild.set(pinnedXcodeBuild)
    this.expectedSwiftVersion.set(pinnedSwiftVersion)
    derivedDataDirectory.set(layout.buildDirectory.dir("swift-simulator-compilation-derived-data"))
    compiledProductsDirectory.set(layout.buildDirectory.dir("swift-simulator-compilation-products"))
    reportFile.set(layout.buildDirectory.file("reports/ios-development/swift-simulator-compilation.json"))
}
val appleDistributionTasks = registerIosAppleDistributionTasks(
    expectedSwiftTestIdentifiers,
    pinnedRustToolchain,
    nativeTasks.appleFrameworkToolchainIdentity,
    importedDeviceFramework,
    importedSimulatorFramework,
)
val appleCompilerMinimumIosVersion = minimumIosVersion
val appleCompilerEvidenceFile =
    layout.buildDirectory.file("reports/cross-language-api/apple/compiler-evidence.json")
val appleBindingEvidenceFile =
    layout.buildDirectory.file("reports/cross-language-api/apple/binding-evidence.json")
val swiftBindingReceiptFile =
    layout.buildDirectory.file("reports/cross-language-api/bindings/swift-parity.json")
val objectiveCBindingReceiptFile =
    layout.buildDirectory.file("reports/cross-language-api/bindings/objective-c-parity.json")
val invalidateAppleBindingEvidence = tasks.register<Delete>("invalidateCodexAgentAppleBindingEvidence") {
    group = "verification"
    description = "Deletes partial Apple binding evidence and receipts before their prerequisites run."
    delete(appleBindingEvidenceFile, swiftBindingReceiptFile, objectiveCBindingReceiptFile)
}
tasks.configureEach {
    if (name != invalidateAppleBindingEvidence.name) {
        mustRunAfter(invalidateAppleBindingEvidence)
    }
}
project(":codex-agent-core").tasks.matching {
    it.name == "invalidateCrossLanguageBindingParityOutputs"
}.configureEach {
    mustRunAfter(invalidateAppleBindingEvidence)
}
rootProject.tasks.matching { it.name == "prepareContractInputs" }.configureEach {
    mustRunAfter(invalidateAppleBindingEvidence)
}
val appleCompilerEvidence = tasks.register<AppleCompilerEvidenceTask>("generateCodexAgentAppleCompilerEvidence") {
    group = "verification"
    description = "Extracts compiler-authored Swift and Objective-C evidence for the CodexFailure slice."
    dependsOn(
        invalidateAppleBindingEvidence,
        verifyAppleToolchain,
        appleDistributionTasks.prepareCodexAgentReleaseXCFramework,
        ":codex-agent-core:verifyCrossLanguageApiCoverage",
    )
    xcframeworkDirectory.set(appleDistributionTasks.releaseXCFrameworkDirectory)
    canonicalApiReport.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    canonicalCoverageReceipt.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json",
    ))
    swiftConsumer.set(layout.projectDirectory.file("apple/CompilerEvidence/CodexFailureSwiftConsumer.swift"))
    objectiveCConsumer.set(layout.projectDirectory.file("apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m"))
    minimumIosVersion.set(appleCompilerMinimumIosVersion)
    expectedXcodeVersion.set(pinnedXcodeVersion)
    expectedXcodeBuild.set(pinnedXcodeBuild)
    expectedSwiftVersion.set(pinnedSwiftVersion)
    evidenceFile.set(appleCompilerEvidenceFile)
}
appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests.configure {
    dependsOn(invalidateAppleBindingEvidence)
}
val appleBindingEvidence = tasks.register<GenerateAppleBindingEvidenceTask>(
    "generateCodexAgentAppleBindingEvidence",
) {
    group = "verification"
    description = "Matches Apple bindings and emits independently verified Swift and Objective-C receipts."
    dependsOn(
        invalidateAppleBindingEvidence,
        appleCompilerEvidence,
        appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests,
        ":codex-agent-core:verifyCrossLanguageApiCoverage",
    )
    canonicalApiReport.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    canonicalCoverageReceipt.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json",
    ))
    compilerEvidence.set(appleCompilerEvidence.flatMap(AppleCompilerEvidenceTask::evidenceFile))
    xcframeworkDirectory.set(appleDistributionTasks.releaseXCFrameworkDirectory)
    swiftConsumer.set(layout.projectDirectory.file("apple/CompilerEvidence/CodexFailureSwiftConsumer.swift"))
    objectiveCConsumer.set(layout.projectDirectory.file("apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m"))
    xctestEvidence.set(
        appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests.flatMap(
            VerifySwiftAuthenticationTestsTask::summaryFile,
        ),
    )
    xcresultDirectory.set(
        appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests.flatMap(
            VerifySwiftAuthenticationTestsTask::resultBundleDirectory,
        ),
    )
    xctestPackageDirectory.set(
        appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests.flatMap(
            VerifySwiftAuthenticationTestsTask::packageDirectory,
        ),
    )
    evidenceFile.set(appleBindingEvidenceFile)
    swiftReceiptFile.set(swiftBindingReceiptFile)
    objectiveCReceiptFile.set(objectiveCBindingReceiptFile)
}
val appleReleaseTasks = registerIosAppleReleaseVerificationTasks(
    appleDistributionTasks,
    minimumIosVersion,
    pinnedRustToolchain,
)
val sharedContractStagePath = providers.gradleProperty("codexAgent.contractBinaryStage")
val freshAppleContractStagePath = providers.gradleProperty("codexAgent.iosContractBinaryStage")
val importedContractVersion = providers.gradleProperty("codexAgent.contractVersion")
private val verifiedDistributionTasks = registerIosVerifiedDistributionTasks(
    appleDistributionTasks,
    appleReleaseTasks,
    iosRuntimeMetrics,
    appleCompilerEvidence,
    appleBindingEvidence,
)
val importedAppleXCFramework = verifiedDistributionTasks.importedXCFramework
check(importedAppleXCFramework == null || !freshAppleContractStagePath.isPresent) {
    "codexAgent.iosContractBinaryStage is only valid for fresh Apple distribution production"
}
val selectedContractStagePath = if (importedAppleXCFramework != null || importedValidationMode) {
    sharedContractStagePath
} else {
    freshAppleContractStagePath
}
private val importedContractEvidence = if (selectedContractStagePath.isPresent) {
    registerIosImportedContractEvidenceTasks(
        layout.dir(selectedContractStagePath.map(::file)),
        importedContractVersion,
        providers.gradleProperty("codexAgent.candidateTree"),
        invalidateAppleBindingEvidence,
    )
} else null
if (importedAppleXCFramework != null) {
    check(importedContractEvidence != null) {
        "Imported Apple evidence requires codexAgent.contractBinaryStage and codexAgent.contractVersion"
    }
    tasks.named<StageCodexAgentAppleDistributionTask>("stageCodexAgentAppleDistribution") {
        setDependsOn(listOf(importedAppleXCFramework))
        xcframeworkDirectory.set(importedAppleXCFramework.flatMap { it.xcframeworkDirectory })
    }
}
importedContractEvidence?.let { contractEvidence ->
    val frameworkDependency = importedAppleXCFramework ?:
        appleDistributionTasks.prepareCodexAgentReleaseXCFramework
    appleCompilerEvidence.configure {
        setDependsOn(listOf(
            invalidateAppleBindingEvidence,
            verifyAppleToolchain,
            frameworkDependency,
            contractEvidence.verify,
        ))
        importedAppleXCFramework?.let { imported ->
            xcframeworkDirectory.set(imported.flatMap { it.xcframeworkDirectory })
        }
        canonicalApiReport.set(contractEvidence.canonicalApi)
        canonicalCoverageReceipt.set(contractEvidence.canonicalCoverage)
    }
    appleBindingEvidence.configure {
        setDependsOn(listOf(
            invalidateAppleBindingEvidence,
            appleCompilerEvidence,
            appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests,
            contractEvidence.verify,
        ))
        importedAppleXCFramework?.let { imported ->
            xcframeworkDirectory.set(imported.flatMap { it.xcframeworkDirectory })
        }
        canonicalApiReport.set(contractEvidence.canonicalApi)
        canonicalCoverageReceipt.set(contractEvidence.canonicalCoverage)
    }
    invalidateAppleBindingEvidence.configure {
        delete(appleCompilerEvidenceFile)
    }
}

validationPackageInputs?.let { packageInputs ->
    val validationConsumers = layout.dir(
        providers.gradleProperty("codexAgent.iosValidationCompilerConsumersDirectory").map(::file),
    )
    appleCompilerEvidence.configure {
        swiftConsumer.set(validationConsumers.map { it.file("CodexFailureSwiftConsumer.swift") })
        objectiveCConsumer.set(validationConsumers.map { it.file("CodexFailureObjectiveCConsumer.m") })
    }
    appleBindingEvidence.configure {
        swiftConsumer.set(validationConsumers.map { it.file("CodexFailureSwiftConsumer.swift") })
        objectiveCConsumer.set(validationConsumers.map { it.file("CodexFailureObjectiveCConsumer.m") })
    }
    val deviceInputs = tasks.register<StageAppleValidationDeviceInputsTask>("stageSdkIosValidationDeviceInputs") {
        dependsOn(packageInputs)
        packageDirectory.set(packageInputs.flatMap { it.packageDirectory })
        testApplicationDirectory.set(layout.dir(
            providers.gradleProperty("codexAgent.iosValidationTestApplicationDirectory").map(::file),
        ))
        workDirectory.set(layout.buildDirectory.dir(
            "imported-sdk-validation/${providers.gradleProperty("codexAgent.candidateTree").get()}/" +
                "${providers.gradleProperty("codexAgent.target").get()}/device-consumer",
        ))
    }
    appleDistributionTasks.verifyCodexAgentSwiftPackage.configure {
        setDependsOn(listOf(invalidateAppleBindingEvidence, verifyAppleToolchain, deviceInputs))
        workingDir(deviceInputs.flatMap { it.stagedTestApplicationDirectory })
    }
    val deviceConsumer = tasks.register<VerifyAppleDeviceConsumerTask>("verifySdkIosDeviceConsumer") {
        dependsOn(invalidateAppleBindingEvidence, verifyAppleToolchain, deviceInputs)
        developerDirectory.set(layout.dir(providers.environmentVariable("DEVELOPER_DIR").map(::file)))
        testApplicationDirectory.set(deviceInputs.flatMap { it.stagedTestApplicationDirectory })
        packageDirectory.set(deviceInputs.flatMap { it.stagedPackageDirectory })
        workDirectory.set(layout.buildDirectory.dir(
            "imported-sdk-validation/${providers.gradleProperty("codexAgent.candidateTree").get()}/" +
                "${providers.gradleProperty("codexAgent.target").get()}/device-execution",
        ))
    }
    configureIosSdkValidationConsumers(
        packageInputs,
        checkNotNull(importedContractEvidence),
        verifyAppleToolchain,
        invalidateAppleBindingEvidence,
        appleDistributionTasks,
        appleCompilerEvidence,
        appleBindingEvidence,
    )
    val validationTarget = providers.gradleProperty("codexAgent.target").get()
    val executionEnvelope = layout.buildDirectory.dir(
        "imported-sdk-validation/${providers.gradleProperty("codexAgent.candidateTree").get()}/" +
            "$validationTarget/execution-envelope",
    )
    val swiftTests = appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests
    val evidenceLayout = providers.provider {
        val compiler = appleCompilerEvidence.get()
        val binding = appleBindingEvidence.get()
        val tests = swiftTests.get()
        val device = deviceConsumer.get()
        mapOf(
            "canonical/canonical-api.json" to binding.canonicalApiReport.get().asFile.path,
            "canonical/canonical-coverage.json" to binding.canonicalCoverageReceipt.get().asFile.path,
            "consumer/CodexFailureSwiftConsumer.swift" to binding.swiftConsumer.get().asFile.path,
            "consumer/CodexFailureObjectiveCConsumer.m" to binding.objectiveCConsumer.get().asFile.path,
            "reports/compiler-evidence.json" to compiler.evidenceFile.get().asFile.path,
            "reports/binding-evidence.json" to binding.evidenceFile.get().asFile.path,
            "reports/swift-parity.json" to binding.swiftReceiptFile.get().asFile.path,
            "reports/objective-c-parity.json" to binding.objectiveCReceiptFile.get().asFile.path,
            "reports/xctest-summary.json" to tests.summaryFile.get().asFile.path,
            "reports/simulator-devices.json" to tests.simulatorDevicesFile.get().asFile.path,
            "compiler-raw" to compiler.rawEvidenceDirectory.get().asFile.path,
            "xcframework" to binding.xcframeworkDirectory.get().asFile.path,
            "xctest-raw" to tests.rawEvidenceDirectory.get().asFile.path,
            "simulator-raw" to tests.simulatorRawEvidenceDirectory.get().asFile.path,
            "xcresult" to tests.resultBundleDirectory.get().asFile.path,
            "xctest-package" to tests.packageDirectory.get().asFile.path,
            "xctest-products" to tests.derivedDataDirectory.dir("Build/Products").get().asFile.path,
            "device-raw" to device.rawEvidenceDirectory.get().asFile.path,
            "device-archive" to device.archiveDirectory.get().asFile.path,
            "device-test-application" to device.testApplicationDirectory.get().asFile.path,
            "device-package" to device.packageDirectory.get().asFile.path,
            "toolchain" to verifyAppleToolchain.get().reportDirectory.get().asFile.path,
        )
    }
    val archiveValidation = tasks.register<ArchiveAppleValidationEvidenceTask>("archiveSdkIosValidationEvidence") {
        dependsOn(appleBindingEvidence, deviceConsumer)
        sourceLayout.set(evidenceLayout)
        evidenceInputs.from(evidenceLayout.map { it.values.map(::file) })
        archiveFile.set(executionEnvelope.map { it.file("apple-validation-evidence.zip") })
    }
    val validationStage = rootProject.layout.buildDirectory.dir("product-stage/sdk/sdk-ios/validation")
    val validationContent = tasks.register<WriteAppleValidationContentTask>("writeSdkIosValidationContent") {
        dependsOn(archiveValidation)
        target.set(validationTarget)
        sdkVersion.set(providers.gradleProperty("codexAgent.sdkVersion"))
        packageStage.set(tasks.named<SnapshotImportedProductStageTask>("snapshotSdkIosValidationPackage")
            .flatMap { it.outputDirectory })
        sdkCompatibility.set(packageInputs.flatMap { it.sdkCompatibility })
        canonicalApi.set(appleBindingEvidence.flatMap { it.canonicalApiReport })
        canonicalCoverage.set(appleBindingEvidence.flatMap { it.canonicalCoverageReceipt })
        swiftReceipt.set(appleBindingEvidence.flatMap { it.swiftReceiptFile })
        objectiveCReceipt.set(appleBindingEvidence.flatMap { it.objectiveCReceiptFile })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        outputFile.set(validationStage.map { it.file("outputs/validation/apple-validation.json") })
    }
    tasks.register<WriteProductOutputManifestTask>("writeSdkIosValidationOutputManifest") {
        dependsOn(validationContent)
        product.set("sdk")
        component.set("sdk-ios")
        phase.set("validation")
        target.set(validationTarget)
        productVersion.set(providers.gradleProperty("codexAgent.sdkVersion"))
        outputRoots.set(mapOf("apple-validation-content" to "outputs/validation"))
        expectedOutputPaths.set(listOf("outputs/validation/apple-validation.json"))
        outputsDirectory.set(validationStage.map { it.dir("outputs") })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(validationStage)
        manifestFile.set(validationStage.map { it.file("output-manifest.json") })
    }
}

// Artifact-only iOS metadata registration. Original receipt/source admission is caller-owned.
if (providers.gradleProperty("codexAgent.product").orNull == "sdk" &&
    providers.gradleProperty("codexAgent.component").orNull == "sdk-ios" &&
    providers.gradleProperty("codexAgent.phase").orNull == "metadata" &&
    providers.gradleProperty("codexAgent.target").orNull == "ios"
) {
    listOf("codexAgent.sdkVersion", "codexAgent.iosMetadataPackageStage",
        "codexAgent.iosMetadataDeviceValidationContent", "codexAgent.iosMetadataSimulatorValidationContent",
    ).forEach { property ->
        check(!providers.gradleProperty(property).orNull.isNullOrBlank()) {
            "Imported iOS metadata requires $property"
        }
    }
    val metadataStage = rootProject.layout.buildDirectory.dir("product-stage/sdk/sdk-ios/metadata")
    val metadataContent = tasks.register<WriteIosSdkMetadataContentTask>("writeSdkIosMetadataContent") {
        sdkVersion.set(providers.gradleProperty("codexAgent.sdkVersion"))
        packageStage.set(layout.dir(providers.gradleProperty("codexAgent.iosMetadataPackageStage").map(::file)))
        deviceValidation.set(layout.file(
            providers.gradleProperty("codexAgent.iosMetadataDeviceValidationContent").map(::file),
        ))
        simulatorValidation.set(layout.file(
            providers.gradleProperty("codexAgent.iosMetadataSimulatorValidationContent").map(::file),
        ))
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        outputFile.set(metadataStage.map { it.file("outputs/evidence/apple-metadata.json") })
    }
    tasks.register<WriteProductOutputManifestTask>("writeSdkIosMetadataOutputManifest") {
        dependsOn(metadataContent)
        product.set("sdk")
        component.set("sdk-ios")
        phase.set("metadata")
        target.set("ios")
        productVersion.set(providers.gradleProperty("codexAgent.sdkVersion"))
        outputRoots.set(mapOf("apple-metadata-content" to "outputs/evidence"))
        expectedOutputPaths.set(listOf("outputs/evidence/apple-metadata.json"))
        outputsDirectory.set(metadataStage.map { it.dir("outputs") })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(metadataStage)
        manifestFile.set(metadataStage.map { it.file("output-manifest.json") })
    }
}

tasks.register("verifyIosRuntime") {
    group = "verification"
    description = "Builds and tests the embedded iOS runtime and clean Swift Package consumer."
    dependsOn(appleBindingEvidence)
    val imported = verifiedDistributionTasks.validateImported
    if (imported != null) dependsOn(imported) else {
        if (!providers.gradleProperty("codexAgent.iosNativeEvidenceDirectory").isPresent) {
            dependsOn(nativeTasks.testCodexIosBridge, nativeTasks.testCodexIosDirectToolMode)
        }
        dependsOn(
            verifyAppleToolchain,
            "compileKotlinIosArm64",
            "iosSimulatorArm64Test",
            appleDistributionTasks.packageCodexAgentAppleDistribution,
            appleReleaseTasks.verifyCodexAgentRemoteSwiftPackage,
            appleDistributionTasks.verifyCodexAgentSwiftPackage,
            appleDistributionTasks.verifyCodexAgentSwiftAuthenticationTests,
            appleReleaseTasks.verifyIosDeploymentTargets,
            appleDistributionTasks.verifyIosLicensePackaging,
            appleReleaseTasks.verifyIosPrivacyManifest,
            appleReleaseTasks.verifyIosReleaseBudgets,
        )
    }
}
