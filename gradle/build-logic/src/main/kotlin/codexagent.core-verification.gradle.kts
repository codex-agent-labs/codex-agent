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
val invalidateCrossLanguageBindingParityOutputs = tasks.register<Delete>(
    "invalidateCrossLanguageBindingParityOutputs",
) {
    group = "verification"
    description = "Deletes stale binding parity outputs before their prerequisites execute."
    delete(
        canonicalCrossLanguageCoverageReceiptFile,
        crossLanguageBindingAuditFile,
        kotlinBindingParityReceiptFile,
    )
}
tasks.configureEach {
    if (name != invalidateCrossLanguageBindingParityOutputs.name) {
        mustRunAfter(invalidateCrossLanguageBindingParityOutputs)
    }
}
verifyCrossLanguageApiCoverage.configure {
    dependsOn(invalidateCrossLanguageBindingParityOutputs)
}

val auditCrossLanguageBindingParity = tasks.register<AuditCrossLanguageBindingParityTask>(
    "auditCrossLanguageBindingParity",
) {
    group = "verification"
    description = "Materializes every canonical API obligation for all eleven first-class languages."
    dependsOn(verifyCrossLanguageApiCoverage)
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    canonicalCoverageReceipt.set(
        verifyCrossLanguageApiCoverage.flatMap(VerifyCrossLanguageApiCoverageTask::receiptFile),
    )
    kotlinArtifact.set(layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    auditFile.set(crossLanguageBindingAuditFile)
}

val verifyKotlinBindingParity = tasks.register<VerifyKotlinBindingParityTask>("verifyKotlinBindingParity") {
    group = "verification"
    description = "Verifies canonical Kotlin artifact and shared projection behavior parity."
    dependsOn(auditCrossLanguageBindingParity)
    apiReport.set(discoverCrossLanguageApi.flatMap(DiscoverCrossLanguageApiTask::reportFile))
    canonicalCoverageReceipt.set(
        verifyCrossLanguageApiCoverage.flatMap(VerifyCrossLanguageApiCoverageTask::receiptFile),
    )
    kotlinArtifact.set(layout.buildDirectory.dir("classes/kotlin/jvm/main"))
    bindingAudit.set(auditCrossLanguageBindingParity.flatMap(AuditCrossLanguageBindingParityTask::auditFile))
    receiptFile.set(kotlinBindingParityReceiptFile)
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
    dependsOn(verifyProtocolSource, verifyCrossLanguageApiCoverage, verifyKotlinBindingParity)
}
