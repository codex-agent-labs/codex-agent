import java.io.File
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.Sync
val npmEntryModule = "codex-agent-codex-agent-runtime-desktop"
val npmPackageName = "@codex-agent-labs" + "/codex-agent"
val npmVersion = rootProject.extra["codexAgent.sdkVersion"].toString()
val npmContractVersion = rootProject.extra["codexAgent.contractVersion"].toString()
val npmOffline = gradle.startParameter.isOffline
val npmSourceDirectory = rootProject.layout.projectDirectory.dir("codex-agent-bindings/javascript/package")
val npmConsumerSourceDirectory = rootProject.layout.projectDirectory.dir("codex-agent-bindings/javascript/consumer")
val importedNpmContractBinaryStage = providers.gradleProperty("codexAgent.contractBinaryStage").map(::file)
val importedNpmRuntimePackageStage = providers.gradleProperty("codexAgent.runtimePackageStage").map(::file)
val importedNpmRuntimeValidationStage =
    providers.gradleProperty("codexAgent.runtimeBindingValidationStage").map(::file)
val importedNpmSdkPackageStage = providers.gradleProperty("codexAgent.sdkPackageStageRoot").map(::file)
val npmCandidateTree = providers.gradleProperty("codexAgent.candidateTree")
val npmRuntimeVersion = providers.gradleProperty("codexAgent.runtimePackageVersion")
val npmRuntimeBindingVersion = providers.gradleProperty("codexAgent.runtimeBindingValidationVersion")
val npmSdkCompatibility = tasks.named<GenerateNativeWrapperSdkCompatibilityTask>(
    "generateNativeWrapperSdkCompatibility",
)
val importedNpmContractSnapshotRoot = layout.buildDirectory.dir(
    npmCandidateTree.map { "imported-sdk-product-stages/$it/contract" },
)
val snapshotImportedNpmContractBinaryStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedNpmContractBinaryStage",
) {
    sourceDirectory.set(layout.dir(importedNpmContractBinaryStage))
    outputDirectory.set(importedNpmContractSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val importedNpmRuntimeSnapshotRoot = layout.buildDirectory.dir(
    npmCandidateTree.map { "imported-sdk-product-stages/$it/node-js" },
)
val snapshotImportedNpmRuntimePackageStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedNpmRuntimePackageStage",
) {
    sourceDirectory.set(layout.dir(importedNpmRuntimePackageStage))
    outputDirectory.set(importedNpmRuntimeSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val importedNpmRuntimeValidationSnapshotRoot = layout.buildDirectory.dir(
    npmCandidateTree.map { "imported-sdk-product-stages/$it/node-js-binding-validation" },
)
val snapshotImportedNpmRuntimeValidationStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedNpmRuntimeValidationStage",
) {
    sourceDirectory.set(layout.dir(importedNpmRuntimeValidationStage))
    outputDirectory.set(importedNpmRuntimeValidationSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val npmCompiledDirectory = importedNpmRuntimeSnapshotRoot.map { it.dir("outputs/adapter") }
val npmGeneratedDeclaration = npmCompiledDirectory.map { it.file("$npmEntryModule.d.ts") }
val npmReviewedDeclaration = npmSourceDirectory.file("index.d.ts")
val crossLanguageApiReport =
    importedNpmContractSnapshotRoot.map { it.file("outputs/evidence/canonical-api.json") }
val npmGeneratedEnumDeclarations =
    layout.buildDirectory.file("generated/cross-language-js/canonical-enums.d.ts")
val npmDeclarationReport = layout.buildDirectory.file("reports/npm/generated-index.d.ts")
val npmStageDirectory = layout.buildDirectory.dir("npm/package")
val npmConsumerDirectory = layout.buildDirectory.dir("npm/consumer")
val npmConsumerCacheDirectory = layout.buildDirectory.dir("npm/cache")
val npmPublicApiReport = layout.buildDirectory.file("npm/consumer/public-api.json")
val npmPackedTestReport = layout.buildDirectory.file("npm/consumer/packed-tests.xml")
val npmCompilerExecution = layout.buildDirectory.file("npm/consumer/typescript-execution.json")
val npmConsumerExecution = layout.buildDirectory.file("npm/consumer/packed-consumer-execution.json")
val javaScriptBindingParityReceipt =
    layout.buildDirectory.file("reports/cross-language-api/bindings/javascript-typescript-parity.json")
val invalidateJavaScriptTypeScriptBindingParityOutput = tasks.register<Delete>(
    "invalidateJavaScriptTypeScriptBindingParityOutput",
) {
    group = "verification"
    description = "Deletes stale JavaScript/TypeScript parity output before its prerequisites execute."
    delete(javaScriptBindingParityReceipt)
}
val verifyImportedNpmContractBinaryOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedNpmContractBinaryOutputManifest",
) {
    product.set("contract")
    component.set("contract")
    phase.set("binary")
    target.set("common")
    productVersion.set(npmContractVersion)
    dependsOn(snapshotImportedNpmContractBinaryStage)
    stageRoot.set(importedNpmContractSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val verifyImportedNpmRuntimePackageOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedNpmRuntimePackageOutputManifest",
) {
    product.set("runtime")
    component.set("node-js")
    phase.set("package")
    target.set("node-js")
    productVersion.set(npmRuntimeVersion)
    dependsOn(snapshotImportedNpmRuntimePackageStage)
    stageRoot.set(importedNpmRuntimeSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val verifyImportedNpmRuntimeValidationOutputManifest =
    tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImportedNpmRuntimeValidationOutputManifest",
    ) {
        product.set("runtime")
        component.set("node-js")
        phase.set("validation")
        target.set("node-js-binding")
        productVersion.set(npmRuntimeBindingVersion)
        dependsOn(snapshotImportedNpmRuntimeValidationStage)
        stageRoot.set(importedNpmRuntimeValidationSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }

val generateJavaScriptEnumDeclarations = tasks.register<GenerateJavaScriptEnumDeclarationsTask>(
    "generateJavaScriptEnumDeclarations",
) {
    dependsOn(verifyImportedNpmContractBinaryOutputManifest)
    apiReport.set(crossLanguageApiReport)
    declarationsFile.set(npmGeneratedEnumDeclarations)
}

val verifyNpmDeclarationGolden = tasks.register("verifyNpmDeclarationGolden") {
    group = "verification"
    description = "Verifies the reviewed Node SDK declaration against the Kotlin compiler output."
    dependsOn(generateJavaScriptEnumDeclarations)
    dependsOn(verifyImportedNpmRuntimePackageOutputManifest)
    inputs.file(npmGeneratedDeclaration)
    inputs.file(npmReviewedDeclaration)
    inputs.file(npmGeneratedEnumDeclarations)
    outputs.file(npmDeclarationReport)
    doLast {
        val declarations = inputs.files.files.associateBy(File::getName)
        verifyJavaScriptDeclarationGolden(declarations.getValue("codex-agent-codex-agent-runtime-desktop.d.ts"),
            declarations.getValue("index.d.ts"), declarations.getValue("canonical-enums.d.ts"),
            outputs.files.singleFile)
    }
}

val npmArchivePolicy = rootProject.layout.projectDirectory.file("gradle/release/toolchains/sdk/javascript.json")
val stageNpmPackage = tasks.register<StageJavaScriptSdkPackageTask>("stageNpmPackage") {
    archivePolicyFile.set(npmArchivePolicy)
    group = "distribution"
    description = "Stages the deterministic Node-only JavaScript and TypeScript SDK."
    dependsOn(verifyNpmDeclarationGolden, npmSdkCompatibility)
    compiledDirectory.set(npmCompiledDirectory)
    sourceDirectory.set(npmSourceDirectory)
    licenseFile.set(rootProject.layout.projectDirectory.file("LICENSE"))
    noticesFile.set(rootProject.layout.projectDirectory.file("THIRD_PARTY_NOTICES.md"))
    compatibilityFile.set(npmSdkCompatibility.flatMap { it.outputFile })
    sdkVersion.set(npmVersion)
    destinationDirectory.set(npmStageDirectory)
}

val packageNpm = tasks.register<PackageJavaScriptSdkTask>("packageNpm") {
    archivePolicyFile.set(npmArchivePolicy)
    group = "distribution"
    description = "Packages the deterministic Node-only JavaScript and TypeScript SDK."
    dependsOn(stageNpmPackage)
    stageDirectory.set(npmStageDirectory)
    archiveFile.set(layout.buildDirectory.file("distributions/codex-agent-$npmVersion.tgz"))
}

val npmArchiveFile = layout.buildDirectory.file("distributions/codex-agent-$npmVersion.tgz")
val npmSdkCompatibilityArchiveReport =
    layout.buildDirectory.file("reports/npm/sdk-compatibility-archive.json")
val verifyNpmSdkCompatibilityArchive = tasks.register<VerifyNpmSdkCompatibilityArchiveTask>(
    "verifyNpmSdkCompatibilityArchive",
) {
    group = "verification"
    description = "Verifies the exact SDK compatibility declaration in the final npm archive."
    dependsOn(packageNpm, npmSdkCompatibility)
    archiveFile.set(npmArchiveFile)
    sdkVersion.set(npmVersion)
    sdkCompatibility.set(npmSdkCompatibility.flatMap { it.outputFile })
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    reportFile.set(npmSdkCompatibilityArchiveReport)
}
val javascriptSdkPackagePhaseRoot = layout.buildDirectory.dir("product-stage/sdk/javascript/package")
val javascriptSdkPackagePhaseOutputs = javascriptSdkPackagePhaseRoot.map { it.dir("outputs") }
val stageJavaScriptSdkPackagePhase = tasks.register<Sync>("stageJavaScriptSdkPackagePhase") {
    group = "distribution"
    dependsOn(verifyNpmSdkCompatibilityArchive)
    into(javascriptSdkPackagePhaseOutputs)
    from(npmArchiveFile) { into("package") }
    from(npmSdkCompatibilityArchiveReport) { into("evidence") }
    from(npmSdkCompatibility.flatMap { it.outputFile }) { into("evidence") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeJavaScriptSdkPackageOutputManifest") {
    group = "distribution"
    dependsOn(stageJavaScriptSdkPackagePhase)
    product.set("sdk")
    component.set("javascript")
    phase.set("package")
    target.set("node")
    productVersion.set(npmVersion)
    outputRoots.set(mapOf(
        "evidence" to "outputs/evidence",
        "package" to "outputs/package",
    ))
    outputsDirectory.set(javascriptSdkPackagePhaseOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(javascriptSdkPackagePhaseRoot)
    manifestFile.set(javascriptSdkPackagePhaseRoot.map { it.file("output-manifest.json") })
}

val verifyNpmPackDryRun = tasks.register<VerifyJavaScriptNpmPackInventoryTask>("verifyNpmPackDryRun") {
    group = "verification"
    description = "Validates npm's exact public file inventory without creating another archive."
    dependsOn(stageNpmPackage)
    packageDirectory.set(npmStageDirectory)
    cacheDirectory.set(npmConsumerCacheDirectory)
}

val javascriptSdkValidationPhaseRoot = layout.buildDirectory.dir("product-stage/sdk/javascript/validation")
val importedNpmSdkSnapshotRoot = layout.buildDirectory.dir(
    npmCandidateTree.map { "imported-sdk-product-stages/$it/javascript-package" },
)
val invalidateJavaScriptSdkValidationOutputs = tasks.register<Delete>("invalidateJavaScriptSdkValidationOutputs") {
    delete(javascriptSdkValidationPhaseRoot, importedNpmSdkSnapshotRoot,
        importedNpmContractSnapshotRoot, importedNpmRuntimeValidationSnapshotRoot,
        npmPublicApiReport, npmPackedTestReport, npmCompilerExecution, npmConsumerExecution)
}
if (importedNpmSdkPackageStage.isPresent) {
    snapshotImportedNpmContractBinaryStage.configure { dependsOn(invalidateJavaScriptSdkValidationOutputs) }
    snapshotImportedNpmRuntimeValidationStage.configure { dependsOn(invalidateJavaScriptSdkValidationOutputs) }
}
val snapshotImportedJavaScriptSdkPackage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedJavaScriptSdkPackage",
) {
    dependsOn(invalidateJavaScriptSdkValidationOutputs)
    sourceDirectory.set(layout.dir(importedNpmSdkPackageStage))
    outputDirectory.set(importedNpmSdkSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val verifyImportedJavaScriptSdkPackage = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedJavaScriptSdkPackage",
) {
    dependsOn(snapshotImportedJavaScriptSdkPackage)
    product.set("sdk")
    component.set("javascript")
    phase.set("package")
    target.set("node")
    productVersion.set(npmVersion)
    stageRoot.set(importedNpmSdkSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val importedNpmSdkArchive = importedNpmSdkSnapshotRoot.map {
    it.file("outputs/package/codex-agent-$npmVersion.tgz")
}
val verifyImportedJavaScriptSdkCompatibility = tasks.register<VerifyNpmSdkCompatibilityArchiveTask>(
    "verifyImportedJavaScriptSdkCompatibility",
) {
    dependsOn(verifyImportedJavaScriptSdkPackage)
    archiveFile.set(importedNpmSdkArchive)
    sdkVersion.set(npmVersion)
    sdkCompatibility.set(importedNpmSdkSnapshotRoot.map { it.file("outputs/evidence/sdk-compatibility.json") })
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    reportFile.set(layout.buildDirectory.file("reports/npm/imported-sdk-compatibility-archive.json"))
}
val npmConsumerArchive = if (importedNpmSdkPackageStage.isPresent) importedNpmSdkArchive else npmArchiveFile

val preparePackedNpmConsumer = tasks.register<Sync>("preparePackedNpmConsumer") {
    group = "verification"
    description = "Prepares an isolated consumer for the packed Node SDK."
    if (importedNpmSdkPackageStage.isPresent) dependsOn(invalidateJavaScriptSdkValidationOutputs)
    duplicatesStrategy = DuplicatesStrategy.FAIL
    from(npmConsumerSourceDirectory)
    into(npmConsumerDirectory)
}

val npmCiPackedConsumer = tasks.register<Exec>("npmCiPackedConsumer") {
    group = "verification"
    description = "Installs the pinned TypeScript toolchain for the isolated npm consumer."
    dependsOn(preparePackedNpmConsumer)
    workingDir(npmConsumerDirectory)
    if (npmOffline) environment("npm_config_offline", "true")
    environment("npm_config_engine_strict", "true")
    environment("npm_config_cache", npmConsumerCacheDirectory.get().asFile.absolutePath)
    commandLine("npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund")
}

val installPackedNpmSdk = tasks.register<Exec>("installPackedNpmSdk") {
    group = "verification"
    description = "Installs the exact generated SDK tarball into the isolated npm consumer."
    dependsOn(npmCiPackedConsumer)
    if (importedNpmSdkPackageStage.isPresent) {
        dependsOn(verifyImportedJavaScriptSdkCompatibility)
    } else {
        dependsOn(packageNpm, verifyNpmPackDryRun)
    }
    workingDir(npmConsumerDirectory)
    inputs.file(npmConsumerArchive)
    if (npmOffline) environment("npm_config_offline", "true")
    environment("npm_config_engine_strict", "true")
    environment("npm_config_cache", npmConsumerCacheDirectory.get().asFile.absolutePath)
    commandLine(
        "npm",
        "install",
        "--no-save",
        "--package-lock=false",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        npmConsumerArchive.get().asFile.absolutePath,
    )
}

val verifyPackedNpmConsumers = tasks.register<Exec>("verifyPackedNpmConsumers") {
    group = "verification"
    description = "Type-checks and executes CJS/ESM consumers against the exact SDK tarball."
    dependsOn(installPackedNpmSdk)
    workingDir(npmConsumerDirectory)
    inputs.file(npmConsumerArchive)
    inputs.files(npmConsumerSourceDirectory.asFileTree)
    outputs.files(npmPublicApiReport, npmPackedTestReport, npmCompilerExecution, npmConsumerExecution)
    environment("CODEX_AGENT_NPM_TARBALL", npmConsumerArchive.get().asFile.absolutePath)
    environment(
        "CODEX_AGENT_EXPECTED_DEFAULT_RUNTIME_VERSION",
        rootProject.extra["codexAgent.sdkDefaultRuntimeVersion"].toString(),
    )
    commandLine("node", "verify.mjs")
    doFirst {
        outputs.files.forEach(File::delete)
    }
    doLast {
        val publicApi = outputs.files.single { it.name == "public-api.json" }
        val junit = outputs.files.single { it.name == "packed-tests.xml" }
        verifyJavaScriptConsumerExecutions(publicApi.parentFile)
        val publicApiText = publicApi.takeIf(File::isFile)?.readText().orEmpty()
        check(publicApi.isFile && publicApi.length() > 0 &&
            publicApiText.startsWith("{\n    \"schema\": 2,") && publicApiText.endsWith("}\n") &&
            "\"referencedSymbols\": [" in publicApiText) {
            "Packed npm compiler API report is missing or malformed"
        }
        val testReport = junit.takeIf(File::isFile)?.readText().orEmpty()
        check(testReport.isNotBlank() &&
            !Regex("""<(failure|error|skipped)\b""").containsMatchIn(testReport)) {
            "Packed npm JUnit evidence is missing, failed, or skipped"
        }
        listOf(
            "cjs exposes the exact Node-only SDK surface",
            "cjs projects lifecycle state failure cleanup and terminal delivery",
            "cjs maps AbortSignal cancellation without starting",
            "esm exposes the same runtime values as CommonJS",
            "typescript compiler discovers the exact installed public API",
        ).forEach { testId ->
            check(testId in testReport) { "Packed npm JUnit evidence did not execute: $testId" }
        }
    }
}

verifyPackedNpmConsumers.configure { dependsOn(invalidateJavaScriptTypeScriptBindingParityOutput) }
tasks.configureEach {
    if (name != invalidateJavaScriptTypeScriptBindingParityOutput.name) {
        mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)
    }
}
rootProject.tasks.matching { it.name == "prepareContractInputs" }.configureEach {
    mustRunAfter(invalidateJavaScriptTypeScriptBindingParityOutput)
}
val verifyJavaScriptTypeScriptBindingParity =
    tasks.register<VerifyJavaScriptTypeScriptBindingParityTask>("verifyJavaScriptTypeScriptBindingParity") {
    group = "verification"
    description = "Verifies the exact packed JavaScript/TypeScript API and shared projection behavior parity."
    dependsOn(
        invalidateJavaScriptTypeScriptBindingParityOutput,
        verifyImportedNpmContractBinaryOutputManifest,
        verifyImportedNpmRuntimeValidationOutputManifest,
        verifyPackedNpmConsumers,
    )
    apiReport.set(importedNpmContractSnapshotRoot.map {
        it.file("outputs/evidence/canonical-api.json")
    })
    coverage.set(importedNpmContractSnapshotRoot.map {
        it.file("outputs/evidence/canonical-coverage.json")
    })
    packedApiReport.set(npmPublicApiReport)
    npmTarball.set(npmConsumerArchive)
    installedPackage.set(npmConsumerDirectory.map {
        it.dir("node_modules/$npmPackageName")
    })
    packedConsumerProgram.set(npmConsumerSourceDirectory)
    compiledJsNodeTestProgram.set(
        importedNpmRuntimeValidationSnapshotRoot.map { it.dir("outputs/test-program") },
    )
    packedJUnit.set(npmPackedTestReport)
    jsNodeJUnit.set(importedNpmRuntimeValidationSnapshotRoot.map {
        it.file("outputs/test-report/TEST-jsNodeTest.CodexNodeApiTest.xml")
    })
    receiptFile.set(javaScriptBindingParityReceipt)
}

val javascriptSdkValidationOutputs = javascriptSdkValidationPhaseRoot.map { it.dir("outputs") }
val stageJavaScriptSdkValidationPhase = tasks.register<Sync>("stageJavaScriptSdkValidationPhase") {
    group = "verification"
    // Product validation requires the imported package even if a legacy direct
    // parity invocation is allowed to produce its local package first.
    dependsOn(verifyImportedJavaScriptSdkCompatibility, verifyJavaScriptTypeScriptBindingParity)
    into(javascriptSdkValidationOutputs)
    from(javaScriptBindingParityReceipt) { into("binding-evidence") }
    from(npmPublicApiReport) { into("compiler-evidence") }
    from(npmPackedTestReport) { into("test-report") }
    from(listOf(npmCompilerExecution, npmConsumerExecution)) { into("execution") }
    from(npmConsumerSourceDirectory) { into("test-program") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeJavaScriptSdkValidationOutputManifest") {
    group = "verification"
    dependsOn(provider {
        check(importedNpmSdkPackageStage.isPresent) {
            "SDK JavaScript validation requires codexAgent.sdkPackageStageRoot"
        }
        stageJavaScriptSdkValidationPhase
    })
    product.set("sdk")
    component.set("javascript")
    phase.set("validation")
    target.set("node")
    productVersion.set(npmVersion)
    outputRoots.set(mapOf(
        "binding-evidence" to "outputs/binding-evidence",
        "compiler-evidence" to "outputs/compiler-evidence",
        "test-report" to "outputs/test-report",
        "execution" to "outputs/execution",
        "test-program" to "outputs/test-program",
    ))
    outputsDirectory.set(javascriptSdkValidationOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(javascriptSdkValidationPhaseRoot)
    manifestFile.set(javascriptSdkValidationPhaseRoot.map { it.file("output-manifest.json") })
}

// Metadata consumes only originals. These snapshots deliberately do not share
// the validation producer's invalidation/npm installation task graph.
fun registerJavaScriptMetadataInput(
    name: String,
    inputProduct: String,
    inputComponent: String,
    inputPhase: String,
    inputTarget: String,
    stageProperty: String,
    version: org.gradle.api.provider.Provider<String>,
): Pair<org.gradle.api.provider.Provider<org.gradle.api.file.Directory>,
    org.gradle.api.tasks.TaskProvider<VerifyImportedProductOutputManifestTask>> {
    val snapshot = layout.buildDirectory.dir(npmCandidateTree.map {
        "imported-sdk-product-stages/$it/javascript-metadata/$name"
    })
    val capture = tasks.register<SnapshotImportedProductStageTask>("snapshotJavaScriptMetadata$name") {
        sourceDirectory.set(layout.dir(providers.gradleProperty(stageProperty).map(::file)))
        outputDirectory.set(snapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verify = tasks.register<VerifyImportedProductOutputManifestTask>("verifyJavaScriptMetadata$name") {
        dependsOn(capture)
        product.set(inputProduct)
        component.set(inputComponent)
        phase.set(inputPhase)
        target.set(inputTarget)
        productVersion.set(version)
        stageRoot.set(snapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    return snapshot to verify
}

val (javascriptMetadataContract, verifyJavaScriptMetadataContract) = registerJavaScriptMetadataInput(
    "Contract", "contract", "contract", "binary", "common", "codexAgent.contractBinaryStage",
    providers.provider { npmContractVersion },
)
val (javascriptMetadataRuntime, verifyJavaScriptMetadataRuntime) = registerJavaScriptMetadataInput(
    "Runtime", "runtime", "node-js", "validation", "node-js-binding",
    "codexAgent.runtimeBindingValidationStage", npmRuntimeBindingVersion,
)
val (javascriptMetadataPackage, verifyJavaScriptMetadataPackage) = registerJavaScriptMetadataInput(
    "Package", "sdk", "javascript", "package", "node", "codexAgent.sdkPackageStageRoot",
    providers.provider { npmVersion },
)
val (javascriptMetadataValidation, verifyJavaScriptMetadataValidation) = registerJavaScriptMetadataInput(
    "Validation", "sdk", "javascript", "validation", "node", "codexAgent.sdkValidationStageRoot",
    providers.provider { npmVersion },
)
val javascriptMetadataArchive = javascriptMetadataPackage.map {
    it.file("outputs/package/codex-agent-$npmVersion.tgz")
}
val verifyJavaScriptMetadataArchive = tasks.register<VerifyNpmSdkCompatibilityArchiveTask>(
    "verifyJavaScriptMetadataArchive",
) {
    dependsOn(verifyJavaScriptMetadataPackage)
    archiveFile.set(javascriptMetadataArchive)
    sdkVersion.set(npmVersion)
    sdkCompatibility.set(javascriptMetadataPackage.map { it.file("outputs/evidence/sdk-compatibility.json") })
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    reportFile.set(layout.buildDirectory.file("reports/npm/metadata-sdk-compatibility-archive.json"))
}
val javascriptMetadataInstalledPackage = layout.buildDirectory.dir("javascript-metadata/installed-package")
val restoreJavaScriptMetadataPackage = tasks.register<RestoreJavaScriptMetadataPackageTask>(
    "restoreJavaScriptMetadataPackage",
) {
    // Validate all archive members before writing only the four matcher files.
    dependsOn(verifyJavaScriptMetadataArchive)
    archiveFile.set(javascriptMetadataArchive)
    destinationDirectory.set(javascriptMetadataInstalledPackage)
}
val javascriptSdkMetadataPhaseRoot = layout.buildDirectory.dir("product-stage/sdk/javascript/metadata")
val javascriptSdkMetadataOutputs = javascriptSdkMetadataPhaseRoot.map { it.dir("outputs") }
val javascriptMetadataReceipt = layout.buildDirectory.file(
    "reports/javascript-metadata/javascript-typescript-parity.json",
)
val replayJavaScriptSdkMetadata = tasks.register<ReplayJavaScriptMetadataTask>("replayJavaScriptSdkMetadata") {
    dependsOn(verifyJavaScriptMetadataContract, verifyJavaScriptMetadataRuntime,
        verifyJavaScriptMetadataValidation, restoreJavaScriptMetadataPackage)
    apiReport.set(javascriptMetadataContract.map { it.file("outputs/evidence/canonical-api.json") })
    coverage.set(javascriptMetadataContract.map { it.file("outputs/evidence/canonical-coverage.json") })
    packedApiReport.set(javascriptMetadataValidation.map { it.file("outputs/compiler-evidence/public-api.json") })
    npmTarball.set(javascriptMetadataArchive)
    installedPackage.set(javascriptMetadataInstalledPackage)
    packedConsumerProgram.set(javascriptMetadataValidation.map { it.dir("outputs/test-program") })
    compiledJsNodeTestProgram.set(javascriptMetadataRuntime.map { it.dir("outputs/test-program") })
    packedJUnit.set(javascriptMetadataValidation.map { it.file("outputs/test-report/packed-tests.xml") })
    jsNodeJUnit.set(javascriptMetadataRuntime.map {
        it.file("outputs/test-report/TEST-jsNodeTest.CodexNodeApiTest.xml")
    })
    executionDirectory.set(javascriptMetadataValidation.map { it.dir("outputs/execution") })
    originalConsumerDirectory.set(providers.gradleProperty("codexAgent.sdkOriginalConsumerDirectory"))
    originalBindingReceipt.set(javascriptMetadataValidation.map {
        it.file("outputs/binding-evidence/javascript-typescript-parity.json")
    })
    receiptFile.set(javascriptMetadataReceipt)
}
val stageJavaScriptSdkMetadataPhase = tasks.register<Sync>("stageJavaScriptSdkMetadataPhase") {
    dependsOn(replayJavaScriptSdkMetadata)
    into(javascriptSdkMetadataOutputs)
    from(javascriptMetadataReceipt) { into("binding-evidence") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeJavaScriptSdkMetadataOutputManifest") {
    dependsOn(stageJavaScriptSdkMetadataPhase)
    product.set("sdk")
    component.set("javascript")
    phase.set("metadata")
    target.set("node")
    productVersion.set(npmVersion)
    outputRoots.set(mapOf("binding-evidence" to "outputs/binding-evidence"))
    outputsDirectory.set(javascriptSdkMetadataOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(javascriptSdkMetadataPhaseRoot)
    manifestFile.set(javascriptSdkMetadataPhaseRoot.map { it.file("output-manifest.json") })
}
