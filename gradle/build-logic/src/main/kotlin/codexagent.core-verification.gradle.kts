val pinnedProtocolSchema = layout.projectDirectory.file(
    "protocol/schema/codex_app_server_protocol.v2.schemas.json",
)
val pinnedCompleteProtocolSchema = layout.projectDirectory.file(
    "protocol/schema/codex_app_server_protocol.schemas.json",
)
val protocolProvenance = layout.projectDirectory.file("protocol/schema/provenance.json")
val crossLanguageKotlinVersion = extensions
    .getByType<org.gradle.api.artifacts.VersionCatalogsExtension>()
    .named("libs")
    .findVersion("kotlin")
    .get()
    .requiredVersion

val crossLanguageHostTarget = run {
    val os = System.getProperty("os.name").lowercase()
    val arch = System.getProperty("os.arch").lowercase()
    when {
        "mac" in os && arch in setOf("aarch64", "arm64") -> "macosArm64" to "MacosArm64"
        "mac" in os -> "macosX64" to "MacosX64"
        "linux" in os && arch in setOf("aarch64", "arm64") -> "linuxArm64" to "LinuxArm64"
        "linux" in os -> "linuxX64" to "LinuxX64"
        "win" in os && arch !in setOf("aarch64", "arm64") -> "mingwX64" to "MingwX64"
        else -> error("Unsupported host for cross-language API discovery: $os/$arch")
    }
}

val discoverCrossLanguageApi = tasks.register<DiscoverCrossLanguageApiTask>("discoverCrossLanguageApi") {
    group = "verification"
    description = "Derives the canonical binding API from pinned Kotlin compiler metadata."
    dependsOn("compileKotlin${crossLanguageHostTarget.second}", "compileKotlinWasmJs", "compileKotlinJvm")
    val readerRuntime = configurations.detachedConfiguration(
        dependencies.create("org.jetbrains.kotlin:kotlin-klib-abi-reader:$crossLanguageKotlinVersion"),
    )
    toolClasspath.from(
        readerRuntime,
        files(CrossLanguageApiReport::class.java.protectionDomain.codeSource.location.toURI()),
    )
    nativeKlib.set(layout.buildDirectory.dir(
        "classes/kotlin/${crossLanguageHostTarget.first}/main/klib/${project.name}",
    ))
    wasmKlib.set(layout.buildDirectory.dir("classes/kotlin/wasmJs/main"))
    jvmClasses.set(layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    markerAnnotation.set("io.github.codex_agent_labs.codexmobile.agent.CodexBindingApi")
    allowedBoundaryTypes.set(listOf(
        "io.github.codex_agent_labs.codexmobile.agent.CodexPlatform",
        "io.github.codex_agent_labs.codexmobile.agent.CodexWorkspaceSelection",
    ))
    reportFile.set(layout.buildDirectory.file("reports/cross-language-api/canonical-api.json"))
}

val canonicalCrossLanguageCoverageReceiptFile =
    layout.buildDirectory.file("reports/cross-language-api/canonical-coverage.json")
val verifyCrossLanguageApiCoverage = tasks.register<VerifyCrossLanguageApiCoverageTask>(
    "verifyCrossLanguageApiCoverage",
) {
    group = "verification"
    description = "Requires every canonical binding API member to have successful behavior coverage."
    dependsOn(discoverCrossLanguageApi, "jvmTest")
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    compiledTests.set(layout.buildDirectory.dir("classes/kotlin/jvm/test"))
    testResults.set(layout.buildDirectory.dir("test-results/jvmTest"))
    kotlinCompilerVersion.set(crossLanguageKotlinVersion)
    canonicalTestTask.set(":codex-agent-core:jvmTest")
    receiptFile.set(canonicalCrossLanguageCoverageReceiptFile)
}

val crossLanguageBindingAuditFile =
    layout.buildDirectory.file("reports/cross-language-api/binding-obligations-m7_5.json")
val kotlinBindingParityReceiptFile =
    layout.buildDirectory.file("reports/cross-language-api/bindings/kotlin-parity.json")
val javaBindingParityReceiptFile =
    layout.buildDirectory.file("reports/cross-language-api/bindings/java-parity.json")
val javaScriptTypeScriptBindingParityReceiptFile = rootProject.layout.projectDirectory.file(
    "codex-agent-runtime-desktop/build/reports/cross-language-api/bindings/" +
        "javascript-typescript-parity.json",
)
val swiftBindingParityReceiptFile = rootProject.layout.projectDirectory.file(
    "codex-agent-runtime-ios/build/reports/cross-language-api/bindings/swift-parity.json",
)
val objectiveCBindingParityReceiptFile = rootProject.layout.projectDirectory.file(
    "codex-agent-runtime-ios/build/reports/cross-language-api/bindings/objective-c-parity.json",
)
val invalidateCrossLanguageBindingParityOutputs = tasks.register<Delete>(
    "invalidateCrossLanguageBindingParityOutputs",
) {
    group = "verification"
    description = "Deletes stale binding parity outputs before their prerequisites execute."
    delete(
        canonicalCrossLanguageCoverageReceiptFile,
        crossLanguageBindingAuditFile,
        kotlinBindingParityReceiptFile,
        javaBindingParityReceiptFile,
    )
}
val crossLanguageInvalidationTaskNames = setOf(
    invalidateCrossLanguageBindingParityOutputs.name,
    "invalidateJavaScriptTypeScriptBindingParityOutput",
    "invalidateCodexAgentAppleBindingEvidence",
    "invalidateCodexAgentCAbiBootstrapEvidence",
)
rootProject.allprojects {
    tasks.configureEach {
        if (name !in crossLanguageInvalidationTaskNames) {
            mustRunAfter(invalidateCrossLanguageBindingParityOutputs)
        }
    }
}
verifyCrossLanguageApiCoverage.configure {
    dependsOn(invalidateCrossLanguageBindingParityOutputs)
}

val verifyKotlinBindingParity = tasks.register<VerifyKotlinBindingParityTask>("verifyKotlinBindingParity") {
    group = "verification"
    description = "Verifies canonical Kotlin artifact and shared projection behavior parity."
    dependsOn(verifyCrossLanguageApiCoverage)
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    canonicalCoverageReceipt.set(
        verifyCrossLanguageApiCoverage.flatMap(VerifyCrossLanguageApiCoverageTask::receiptFile),
    )
    kotlinArtifact.set(layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    receiptFile.set(kotlinBindingParityReceiptFile)
}

val javaBindingVersion = project.version.toString()
val javaBindingCoreJvmJar = layout.buildDirectory.file("libs/codex-agent-core-jvm-$javaBindingVersion.jar")
val javaBindingCoreAndroidAar = layout.buildDirectory.file("outputs/aar/codex-agent-core.aar")
val javaBindingDesktopRuntimeJar = rootProject.layout.projectDirectory.file(
    "codex-agent-runtime-desktop/build/libs/codex-agent-runtime-desktop-jvm-$javaBindingVersion.jar",
)
val javaBindingAndroidRuntimeAar = rootProject.layout.projectDirectory.file(
    "codex-agent-runtime-android/build/outputs/aar/codex-agent-runtime-android-release.aar",
)
val javaBindingCompiledTests = layout.buildDirectory.dir("classes/java/jvmTest")
val javaBindingTestResults = layout.buildDirectory.dir("test-results/jvmTest")
val verifyJavaBindingParity = tasks.register<VerifyJavaBindingParityTask>("verifyJavaBindingParity") {
    group = "verification"
    description = "Verifies Java API parity in exact JVM, Android, and runtime artifacts."
    dependsOn(
        verifyCrossLanguageApiCoverage,
        "jvmJar",
        "bundleAndroidMainAar",
        ":codex-agent-runtime-desktop:jvmJar",
        ":codex-agent-runtime-android:bundleReleaseAar",
    )
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    canonicalCoverageReceipt.set(
        verifyCrossLanguageApiCoverage.flatMap(VerifyCrossLanguageApiCoverageTask::receiptFile),
    )
    kotlinArtifact.set(layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    coreJvmJar.set(javaBindingCoreJvmJar)
    coreAndroidAar.set(javaBindingCoreAndroidAar)
    desktopRuntimeJar.set(javaBindingDesktopRuntimeJar)
    androidRuntimeAar.set(javaBindingAndroidRuntimeAar)
    compiledJavaTests.set(javaBindingCompiledTests)
    testResults.set(javaBindingTestResults)
    receiptFile.set(javaBindingParityReceiptFile)
}

val auditCrossLanguageBindingParity = tasks.register<AuditCrossLanguageBindingParityTask>(
    "auditCrossLanguageBindingParity",
) {
    group = "verification"
    description = "Recomputes the authoritative active-language obligation audit from verified language receipts."
    dependsOn(
        verifyKotlinBindingParity,
        verifyJavaBindingParity,
        ":codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity",
        ":codex-agent-runtime-ios:generateCodexAgentAppleBindingEvidence",
    )
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    canonicalCoverageReceipt.set(
        verifyCrossLanguageApiCoverage.flatMap(VerifyCrossLanguageApiCoverageTask::receiptFile),
    )
    kotlinReceipt.set(verifyKotlinBindingParity.flatMap(VerifyKotlinBindingParityTask::receiptFile))
    javaReceipt.set(verifyJavaBindingParity.flatMap(VerifyJavaBindingParityTask::receiptFile))
    javaScriptTypeScriptReceipt.set(javaScriptTypeScriptBindingParityReceiptFile)
    swiftReceipt.set(swiftBindingParityReceiptFile)
    objectiveCReceipt.set(objectiveCBindingParityReceiptFile)
    auditFile.set(crossLanguageBindingAuditFile)
}

val verifyProtocolSource = tasks.register<VerifyProtocolSourceTask>("verifyProtocolSource") {
    protocolSchema.set(pinnedProtocolSchema)
    completeProtocolSchema.set(pinnedCompleteProtocolSchema)
    provenance.set(protocolProvenance)
    descriptor.set(layout.projectDirectory.file("protocol/schema/descriptors.json"))
    generatedSources.set(
        layout.projectDirectory.dir(
            "src/commonMain/kotlin/io/github/codex_agent_labs/codexmobile/appserver/protocol/generated",
        ),
    )
    expectedSchemaSha256.set("9b3de71a5a2ffc980b792a18aa8f8dec3f85f48829560222a0264fe494b679a9")
    expectedCompleteSchemaSha256.set("02a4c63a638fdae4a5f6c3ad32a41a377b642c66f3abc84f6fc47c7f3d6074df")
}

tasks.register("updateProtocol") {
    group = "protocol"
    description = "Regenerates the pinned protocol from exact Codex sources."
    dependsOn(":tooling:protocol-generator:generateProtocol")
}

tasks.named("check").configure {
    dependsOn(
        verifyProtocolSource,
        verifyKotlinBindingParity,
        verifyJavaBindingParity,
        ":codex-agent-runtime-desktop:verifyJavaScriptTypeScriptBindingParity",
    )
}
