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
        )
        into("python/ci")
    }
}

val releaseToolingRuntime by configurations.creating {
    isCanBeConsumed = false
    isCanBeResolved = true
    isTransitive = true
}
dependencies.add(releaseToolingRuntime.name, libs.kotlinx.serialization.json)
val releaseToolingClasses = listOf(
    "AndroidRuntimeEvidenceFilesKt",
    "AndroidRuntimeEvidenceSupportKt",
    "AppleArtifactMetrics",
    "AppleNativeTestCommand",
    "AppleNativeTestsIdentity",
    "AppleReleaseCheckTasksKt",
    "AppleRustEvidenceIdentity",
    "AppleRustSliceModelKt",
    "AppleRustSliceSpec",
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
    "CrossLanguageNativeWrapperClaim",
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
    "PrivacyReleaseVerificationTasksKt",
    "ProductVersions",
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
                dependency.name.startsWith("kotlinx-serialization-json-jvm-")
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
