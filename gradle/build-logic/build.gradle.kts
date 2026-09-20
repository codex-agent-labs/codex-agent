import org.gradle.api.file.DuplicatesStrategy
import org.gradle.jvm.tasks.Jar
import org.gradle.api.tasks.testing.Test

plugins { `kotlin-dsl` }
repositories { google(); mavenCentral(); gradlePluginPortal() }
dependencies {
    implementation(libs.kotlinx.serialization.json)
    implementation("org.jetbrains.kotlin:kotlin-gradle-plugin:${libs.versions.kotlin.get()}")
    compileOnly("org.jetbrains.kotlin:kotlin-klib-abi-reader:${libs.versions.kotlin.get()}")
    implementation("org.jetbrains.kotlin:kotlin-metadata-jvm:${libs.versions.kotlin.get()}")
    implementation("com.android.tools.build:gradle:${libs.versions.agp.get()}")
    // Already used by AGP at runtime; expose its mode-aware ZIP reader to our compiler.
    implementation("org.apache.commons:commons-compress:1.27.1")
    testImplementation(gradleTestKit())
    testImplementation(kotlin("test-junit"))
    testImplementation("org.jetbrains.kotlin:kotlin-klib-abi-reader:${libs.versions.kotlin.get()}")
}
tasks.withType<Test>().configureEach { maxParallelForks = 2 }

tasks.processResources {
    from(layout.projectDirectory.dir("../../ci")) {
        include(
            "products/__init__.py",
            "products/inventory.py",
            "products/test_results.py",
            "products/runtime_evidence.py",
            "products/c_abi.py",
            "native_wrappers.py",
            "products/aggregate.py", "products/contract.py", "products/contract_attestation.py",
            "products/contract_model.py", "products/contract_projection.py", "products/index.py",
            "products/plan.py", "products/receipt.py", "products/registry.py", "products/restore.py",
            "products/runtime_adapter_content.py", "products/runtime_adapter_validation.py",
            "products/runtime_aggregate.py", "products/runtime_attestation.py", "products/runtime_flags.py",
            "products/runtime_identity.py", "products/sdk_compatibility.py", "products/sdk_inputs.py",
            "products/sdk_native.py", "products/sdk_package.py", "products/sdk_runtime_content.py", "products/sdk_validation.py",
            "products/selection.py", "products/signatures.py", "products/toolchain.py",
        )
        into("python/ci")
    }
    from(layout.projectDirectory.dir("../../codex-agent-runtime-desktop/native/c-api")) {
        include("abi-contract.json", "exports/linux.map", "exports/macos.exports", "exports/windows.def")
        into("python/codex-agent-runtime-desktop/native/c-api")
    }
    from(layout.projectDirectory.dir("../../codex-agent-bindings/cpp/tools")) {
        include("verify_imported_package.py")
        into("python/codex-agent-bindings/cpp/tools")
    }
}

val releaseToolingRuntime by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
    isTransitive = true
}
dependencies.add(releaseToolingRuntime.name, libs.kotlinx.serialization.json)
dependencies.add(releaseToolingRuntime.name, configurations["implementation"].dependencies.single {
    it.group == "org.apache.commons" && it.name == "commons-compress"
})
val releaseToolingClasses = listOf(
    "ImportedSdkFacadePublicationVerificationKt",
    "SdkFacadeOriginalExecutionKt",
    "FacadePublicationContractKt",
    "FacadePublicationSpec",
    "PublicationDependency",
    "AndroidRuntimeEvidenceFilesKt",
    "AndroidRuntimeEvidenceSupportKt",
    "AppleArtifactMetrics",
    "AppleOriginalExecutionVerificationKt",
    "AppleBinaryPackageContentKt",
    "AppleBinaryPackageReplayKt",
    "OriginalAppleCompilerSliceReplay",
    "AppleCompilerEvidenceTaskKt",
    "AppleCompilerSymbol",
    "AppleCompilerReference",
    "ExpectedAppleCompilerSymbol",
    "AppleOrdinaryType",
    "AppleOrdinaryParameter",
    "AppleOrdinaryProperty",
    "AppleOrdinaryEnum",
    "AppleOrdinaryValue",
    "AppleOrdinaryCapability",
    "AppleCompilerSlice",
    "InspectedAppleCompilerSlice",
    "AppleBindingInputDigests",
    "AppleBindingTargetDigests",
    "AppleCompilerClaim",
    "CrossLanguageAppleBindingEvidenceKt",
    "SwiftAuthenticationTestTaskKt",
    "SwiftTestSummary",
    "SwiftTestCaseResult",
    "SimulatorSelection",
    "SimulatorStatus",
    "AppleDistributionFileTasksKt",
    "AppleDistributionInputs",
    "AppleNativeTestCommand",
    "AppleNativeTestsIdentity",
    "AppleReleaseCheckTasksKt",
    "AppleRustEvidenceIdentity",
    "AppleRustSliceModelKt",
    "AppleRustSliceSpec",
    "AppleVerifiedDistributionVerificationKt",
    "AppleVerifiedDistributionModelKt",
    "AppleVerifiedDistributionIdentity",
    "AppleVerifiedDistributionInventory",
    "BoundProducedEvidence",
    "BoundRuntimeEvidence",
    "CandidateCiProvenanceKt",
    "CandidateIosNativeEvidenceKt",
    "CandidateManifestValidationKt",
    "CandidatePayloadTasksKt",
    "CandidateRuntimeEvidenceKt",
    "CentralBundleTasksKt",
    "CentralDeployment",
    "CentralExpectedFile",
    "CentralIdentity",
    "CentralPortalHttpKt",
    "CentralPortalRecordKt",
    "CentralPortalRequest",
    "CentralPortalResponse",
    "CentralPortalTaskKt",
    "CentralPortalVerificationKt",
    "CrossLanguageApiEvidenceKt",
    "CrossLanguageApiReportEvidence",
    "CrossLanguageApplicabilityExclusion",
    "CrossLanguageBinding",
    "CrossLanguageBindingArtifactIdentity",
    "CrossLanguageBindingAudit",
    "CrossLanguageBindingAuditKt",
    "CrossLanguageBindingAuditRecord",
    "CrossLanguageBindingAuditSummary",
    "CrossLanguageBindingCanonicalIdentity",
    "CrossLanguageBindingHostConsumerProof",
    "CrossLanguageBindingObligation",
    "CrossLanguageBindingObligationState",
    "CrossLanguageBindingParityInput",
    "CrossLanguageBindingParityKt",
    "CrossLanguageBindingParityReport",
    "CrossLanguageBindingPhase",
    "CrossLanguageBindingReceipt",
    "CrossLanguageBindingReceiptKt",
    "CrossLanguageBindingScenario",
    "CrossLanguageBindingTestEvidence",
    "CrossLanguageBindingTestStatus",
    "CrossLanguageJavaScriptBindingEvidenceKt",
    "CrossLanguageJavaScriptBindingEvidence",
    "CrossLanguageJavaScriptBindingFiles",
    "CrossLanguageJavaScriptMetadataEvidenceKt",
    "CrossLanguageJavaScriptStagedMetadataKt",
    "CanonicalJavaScriptMemberKind",
    "CanonicalTestResultsClientKt",
    "CanonicalTestResult",
    "CanonicalTestStatus",
    "CanonicalJavaScriptMember",
    "CanonicalJavaScriptPropertyKind",
    "CanonicalJavaScriptParameter",
    "JavaScriptPackedArtifact",
    "JavaScriptPackedPublicApiEvidence",
    "JavaScriptBindingScenarioMapping",
    "JavaScriptPublicSymbolKind",
    "JavaScriptPublicSymbol",
    "JavaScriptParameter",
    "JavaScriptSignature",
    "JavaScriptProjectionCandidate",
    "JavaScriptProjection",
    "JavaScriptObjectLiteralProjection",
    "CrossLanguageCanonicalApiEvidence",
    "CrossLanguageCAbiBindingEvidenceInput",
    "CrossLanguageCAbiBindingEvidenceKt",
    "CrossLanguageCAbiClientKt",
    "CrossLanguageCAbiClientCatalog",
    "CrossLanguageCAbiClientTarget",
    "CrossLanguageCAbiHostMapping",
    "CrossLanguageCAbiScenarioMapping",
    "CrossLanguageCAbiScenarioProof",
    "CrossLanguageCAbiTargetSpec",
    "CrossLanguageObligationStatus",
    "CrossLanguageProjectionClaim",
    "CrossLanguageScenarioEvidence",
    "CrossLanguageNativeWrapperBindingEvidenceKt",
    "CrossLanguageNativeWrapperValidationEvidenceKt",
    "NativeWrapperInstalledConsumerTaskKt",
    "CrossLanguageNativeWrapperClaim",
    "CrossLanguageNativeWrapperCapabilityEvidence",
    "CrossLanguageNativeWrapperCompilerEvidence",
    "CrossLanguageNativeWrapperEvidenceInput",
    "CrossLanguageNativeWrapperHostConsumerEvidence",
    "CrossLanguageNativeWrapperLaneIdentity",
    "CrossLanguageNativeWrapperSdkStagingKt",
    "CrossLanguageNativeWrapperSdkIndex",
    "CrossLanguageNativeWrapperSdkRecord",
    "DeploymentTargetRecord",
    "DesktopCodexDistributionSpec",
    "DesktopCodexManifest",
    "DesktopRuntimeEvidenceTarget",
    "FirebaseAndroidEvidenceValues",
    "FirebaseAndroidRuntimeEvidenceModelKt",
    "FirebaseTestMatrix",
    "IosPrivacyAuditVerificationKt",
    "ImportedAppleFrameworkTasksKt",
    "IosPrivacyCategory",
    "IosPrivacyHit",
    "IosPrivacyPolicy",
    "IosPrivacyPolicyKt",
    "IosPrivacyReviewBindingKt",
    "IosPrivacySignals",
    "JdkCentralPortalSender",
    "KmpConsumerVerificationTaskKt",
    "MavenArtifactSpec",
    "MavenProduct",
    "MavenRepositoryTasksKt",
    "NativeWrapperSdkCompatibility",
    "PrivacyReleaseVerificationTasksKt",
    "ProductVersions",
    "ProductVersionIdentityKt",
    "ProductPythonToolingKt",
    "ProductPythonToolingMarker",
    "PromotedCandidateInputs",
    "PromotedCandidateTasksKt",
    "PromotedIosEvidence",
    "PromotedLane",
    "PromotedRuntimeEvidence",
    "PromotedRustProof",
    "ReleaseIoKt",
    "ReleaseToolingArguments",
    "ReleaseToolingCliKt",
    "RuntimeEvidenceClientKt",
    "ReviewedPrivacyApi",
    "TransportProducerIdentity",
    "TransportedRuntimeEvidence",
    "CAbiBindingBootstrapClaim",
    "CAbiBindingBootstrapEvidence",
    "CAbiBindingBootstrapTest",
)
val releaseToolingJar = tasks.register<Jar>("releaseToolingJar") {
    group = "build"
    description = "Packages the no-Gradle release CLI used by candidate and publication runners."
    dependsOn(tasks.named("classes"))
    archiveFileName.set("codex-agent-release-tooling.jar")
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    manifest.attributes["Main-Class"] = "ReleaseToolingCliKt"
    from(sourceSets.main.get().output) {
        include(releaseToolingClasses.flatMap { listOf("$it.class", "${it}\$*.class") })
        exclude("ProductVersionsKt.class")
    }
    from(layout.buildDirectory.dir("resources/main")) { include("python/**") }
    from(provider {
        releaseToolingRuntime.filter { dependency ->
            dependency.name.startsWith("kotlin-stdlib-") ||
                dependency.name.startsWith("kotlinx-serialization-core-jvm-") ||
                dependency.name.startsWith("kotlinx-serialization-json-jvm-") ||
                dependency.name.startsWith("commons-compress-") ||
                dependency.name.startsWith("commons-io-") ||
                dependency.name.startsWith("commons-codec-") ||
                dependency.name.startsWith("commons-lang3-")
        }.map(::zipTree)
    })
    exclude(
        "META-INF/*.SF", "META-INF/*.DSA", "META-INF/*.RSA", "META-INF/gradle-plugins/**",
        "gradle/**", "Codexagent_*",
    )
}
tasks.withType<Test>().configureEach {
    dependsOn(releaseToolingJar)
    systemProperty("codexAgent.releaseToolingJar", releaseToolingJar.flatMap { it.archiveFile }.get().asFile)
}
