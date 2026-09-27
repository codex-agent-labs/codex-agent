import org.gradle.api.publish.PublishingExtension
import org.gradle.api.tasks.Sync

val contractVersionAuthority = layout.projectDirectory.file("gradle/release/versions/contract.txt")
providers.fileContents(contractVersionAuthority).asText.get()
val contractVersion = readProductVersion(contractVersionAuthority.asFile)
val core = project(":codex-agent-core")
check(core.group.toString() == CodexAgentBuild.MAVEN_GROUP && core.version.toString() == contractVersion) {
    "Contract product plugin requires the canonical Core coordinate and Contract version"
}

val contractProductRoot = layout.buildDirectory.dir("contract-product")
val contractPythonSources = files(
    "ci/products/__init__.py",
    "ci/products/__main__.py",
    "ci/products/contract.py",
    "ci/products/contract_model.py",
    "ci/products/inventory.py",
    "ci/products/zip_central_directory.py",
    "ci/products/receipt.py",
    "ci/products/test_results.py",
)
val contractMavenRepository = contractProductRoot.map { it.dir("maven-repository") }
core.pluginManager.withPlugin("maven-publish") {
    core.extensions.configure<PublishingExtension> {
        repositories.maven {
            name = "CONTRACT_BUNDLE_STAGING"
            url = contractMavenRepository.get().asFile.toURI()
        }
    }
}
val contractPublicationNames = listOf(
    "KotlinMultiplatform", "Android", "Jvm", "IosArm64", "IosSimulatorArm64", "MacosArm64",
    "MacosX64", "LinuxArm64", "LinuxX64", "MingwX64", "Js", "WasmJs",
)
val contractPublicationTaskNames = contractPublicationNames.map { publication ->
    "publish${publication}PublicationToCONTRACT_BUNDLE_STAGINGRepository"
}
val contractPublicationTasks = contractPublicationTaskNames.map { ":codex-agent-core:$it" }
val contractMetadataDirectory = contractProductRoot.map { it.dir("metadata") }
val prepareContractInputs = tasks.register<Exec>("prepareContractInputs") {
    group = "publishing"
    description = "Binds Contract evidence inventories to the selected content."
    outputs.dir(contractMetadataDirectory)
    outputs.upToDateWhen { false }
    environment("PYTHONDONTWRITEBYTECODE", "1")
    val arguments = mutableListOf(
        "python3", "-m", "ci.products.contract", "prepare",
        "--repository-root", layout.projectDirectory.asFile.absolutePath,
        "--output-directory", contractMetadataDirectory.get().asFile.absolutePath,
        "--revision", "HEAD",
    )
    commandLine(arguments)
}
tasks.configureEach {
    if (name != prepareContractInputs.name) {
        mustRunAfter(prepareContractInputs)
    }
}
core.tasks.configureEach {
    dependsOn(prepareContractInputs)
    mustRunAfter(prepareContractInputs)
}
val resetContractMavenRepository = tasks.register<Delete>("resetContractMavenRepository") {
    group = "publishing"
    description = "Removes stale Contract Maven files after the current inputs have been accepted."
    dependsOn(prepareContractInputs)
    delete(contractMavenRepository)
}
core.tasks.matching { it.name in contractPublicationTaskNames }.configureEach {
    dependsOn(resetContractMavenRepository)
}
val contractBinaryPhaseRoot = layout.buildDirectory.dir("product-stage/contract/contract/binary")
val contractStage = contractBinaryPhaseRoot.map { it.dir("outputs") }
val stageContractBundleInputs = tasks.register<Sync>("stageContractBundleInputs") {
    group = "publishing"
    description = "Stages the exact Contract Maven repository and canonical verification evidence."
    // Capture finalizes these copies; a selected binary invocation needs fresh raw inputs.
    outputs.upToDateWhen { false }
    dependsOn(contractPublicationTasks, prepareContractInputs)
    dependsOn(
        ":codex-agent-core:verifyKotlinBindingParity",
        ":codex-agent-core:verifyProtocolSource",
    )
    into(contractStage)
    from(contractMavenRepository) {
        include("${CodexAgentBuild.MAVEN_GROUP.replace('.', '/')}/codex-agent-core*/$contractVersion/**")
        into("maven")
    }
    from(core.layout.buildDirectory.file(
        "reports/cross-language-api/canonical-api.json",
    )) { into("evidence"); rename { "canonical-api.json" } }
    from(core.layout.buildDirectory.file(
        "reports/cross-language-api/canonical-coverage.json",
    )) { into("evidence"); rename { "canonical-coverage.json" } }
    from(core.layout.buildDirectory.file(
        "reports/cross-language-api/bindings/kotlin-parity.json",
    )) { into("evidence"); rename { "kotlin-parity.json" } }
    from(core.layout.buildDirectory.file(
        "reports/protocol/protocol-source-verification.json",
    )) { into("evidence"); rename { "protocol-source-verification.json" } }
    from(core.layout.projectDirectory.dir("protocol/schema")) {
        include(
            "codex_app_server_protocol.schemas.json",
            "codex_app_server_protocol.v2.schemas.json",
            "descriptors.json",
            "provenance.json",
        )
        into("evidence")
    }
    from(contractMetadataDirectory.map { it.dir("inventories") }) { into("inventories") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val captureContractExecutionEvidence = tasks.register<Exec>("captureContractExecutionEvidence") {
    dependsOn(stageContractBundleInputs)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    // The Python boundary atomically publishes raw evidence and finalizes fresh content copies.
    commandLine(
        "python3", "-m", "ci.products.contract", "capture-execution",
        "--staging-root", contractStage.get().asFile.absolutePath,
        "--compiled-tests", core.layout.buildDirectory.dir("classes/kotlin/jvm/test").get().asFile.absolutePath,
        "--test-results", core.layout.buildDirectory.dir("test-results/jvmTest").get().asFile.absolutePath,
    )
}
val writeContractBinaryOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeContractBinaryOutputManifest",
) {
    group = "publishing"
    description = "Writes and verifies the exact Contract binary-phase output manifest in place."
    dependsOn(captureContractExecutionEvidence)
    product.set("contract")
    component.set("contract")
    phase.set("binary")
    target.set("common")
    productVersion.set(contractVersion)
    outputRoots.set(mapOf(
        "maven" to "outputs/maven",
        "evidence" to "outputs/evidence",
        "inventory" to "outputs/inventories",
        "contract-execution" to "outputs/execution",
    ))
    outputsDirectory.set(contractStage)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractBinaryPhaseRoot)
    manifestFile.set(contractBinaryPhaseRoot.map { it.file("output-manifest.json") })
}
val importedContractBinaryStage = layout.dir(
    providers.gradleProperty("codexAgent.contractBinaryStageRoot").map(::file),
)
val importedContractBinarySnapshot = contractProductRoot.map { it.dir("imported/binary") }
val contractPackagePhaseRoot = layout.buildDirectory.dir("product-stage/contract/contract/package")
val contractPackageOutputs = contractPackagePhaseRoot.map { it.dir("outputs") }
val invalidateContractPackagePhase = tasks.register<Delete>("invalidateContractPackagePhase") {
    delete(importedContractBinarySnapshot, contractPackagePhaseRoot)
}
val snapshotImportedContractBinaryStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedContractBinaryStage",
) {
    dependsOn(invalidateContractPackagePhase)
    sourceDirectory.set(importedContractBinaryStage)
    outputDirectory.set(importedContractBinarySnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val verifyImportedContractBinaryOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedContractBinaryOutputManifest",
) {
    dependsOn(snapshotImportedContractBinaryStage)
    product.set("contract")
    component.set("contract")
    phase.set("binary")
    target.set("common")
    productVersion.set(contractVersion)
    stageRoot.set(importedContractBinarySnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val stageContractPackageFromImportedBinary = tasks.register<Sync>(
    "stageContractPackageFromImportedBinary",
) {
    dependsOn(verifyImportedContractBinaryOutputManifest)
    into(contractPackageOutputs)
    from(importedContractBinarySnapshot.map { it.dir("outputs") })
    exclude("execution/**")
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val writeContractPackageOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeContractPackageOutputManifest",
) {
    group = "publishing"
    description = "Stages the Contract package payload from one authenticated binary phase."
    dependsOn(stageContractPackageFromImportedBinary)
    product.set("contract")
    component.set("contract")
    phase.set("package")
    target.set("common")
    productVersion.set(contractVersion)
    outputRoots.set(mapOf(
        "maven" to "outputs/maven",
        "evidence" to "outputs/evidence",
        "inventory" to "outputs/inventories",
    ))
    outputsDirectory.set(contractPackageOutputs)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractPackagePhaseRoot)
    manifestFile.set(contractPackagePhaseRoot.map { it.file("output-manifest.json") })
}
val importedContractPackageStage = layout.dir(
    providers.gradleProperty("codexAgent.contractPackageStageRoot").map(::file),
)
val importedContractPackageSnapshot = contractProductRoot.map { it.dir("imported/package") }
val importedContractPackageReceipt = layout.file(
    providers.gradleProperty("codexAgent.contractPackageReceipt").map(::file),
)
val importedContractPackageReceiptSha256 = providers.gradleProperty(
    "codexAgent.contractPackageReceiptSha256",
)
val importedContractBinaryReceipt = layout.file(
    providers.gradleProperty("codexAgent.contractBinaryReceipt").map(::file),
)
val importedContractBinaryReceiptSha256 = providers.gradleProperty(
    "codexAgent.contractBinaryReceiptSha256",
)
val contractValidationPhaseRoot = layout.buildDirectory.dir("product-stage/contract/contract/validation")
val contractValidationOutputs = contractValidationPhaseRoot.map { it.dir("outputs") }
val contractValidationEvidence = contractValidationOutputs.map { it.dir("validation") }
val invalidateContractValidationPhase = tasks.register<Delete>("invalidateContractValidationPhase") {
    delete(importedContractPackageSnapshot, contractValidationPhaseRoot)
}
val snapshotImportedContractPackageStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedContractPackageStage",
) {
    dependsOn(invalidateContractValidationPhase)
    sourceDirectory.set(importedContractPackageStage)
    outputDirectory.set(importedContractPackageSnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val verifyImportedContractPackageOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedContractPackageOutputManifest",
) {
    dependsOn(snapshotImportedContractPackageStage)
    product.set("contract")
    component.set("contract")
    phase.set("package")
    target.set("common")
    productVersion.set(contractVersion)
    stageRoot.set(importedContractPackageSnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val stageContractValidationFromImportedPackage = tasks.register<Sync>(
    "stageContractValidationFromImportedPackage",
) {
    dependsOn(verifyImportedContractPackageOutputManifest)
    into(contractValidationOutputs)
    from(importedContractPackageSnapshot.map { it.dir("outputs") })
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val validateImportedContractPackage = tasks.register<Exec>("validateImportedContractPackage") {
    group = "verification"
    description = "Validates one authenticated Contract package and its exact predecessor receipts."
    dependsOn(stageContractValidationFromImportedPackage)
    inputs.file(importedContractPackageReceipt)
    inputs.file(importedContractBinaryReceipt)
    inputs.property("packageReceiptSha256", importedContractPackageReceiptSha256)
    inputs.property("binaryReceiptSha256", importedContractBinaryReceiptSha256)
    // Python publishes this directory atomically; Gradle must not pre-create it.
    // The phase output manifest inventories it after successful validation.
    environment("PYTHONDONTWRITEBYTECODE", "1")
    executable("python3")
    args("-m", "ci.products.contract", "validate-package", "--package-stage")
    args(importedContractPackageSnapshot.get().asFile.absolutePath)
    args("--package-receipt")
    args(importedContractPackageReceipt.get().asFile.absolutePath)
    args("--package-receipt-sha256", importedContractPackageReceiptSha256.get())
    args("--binary-receipt")
    args(importedContractBinaryReceipt.get().asFile.absolutePath)
    args("--binary-receipt-sha256", importedContractBinaryReceiptSha256.get())
    args("--output-directory")
    args(contractValidationEvidence.get().asFile.absolutePath)
    args("--contract-version", contractVersion)
}
val writeContractValidationOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeContractValidationOutputManifest",
) {
    group = "verification"
    description = "Stages the validated Contract payload and deterministic validation evidence."
    dependsOn(validateImportedContractPackage)
    product.set("contract")
    component.set("contract")
    phase.set("validation")
    target.set("common")
    productVersion.set(contractVersion)
    outputRoots.set(mapOf(
        "maven" to "outputs/maven",
        "evidence" to "outputs/evidence",
        "inventory" to "outputs/inventories",
        "validation" to "outputs/validation",
    ))
    outputsDirectory.set(contractValidationOutputs)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractValidationPhaseRoot)
    manifestFile.set(contractValidationPhaseRoot.map { it.file("output-manifest.json") })
}
val importedContractValidationStage = layout.dir(
    providers.gradleProperty("codexAgent.contractValidationStageRoot").map(::file),
)
val importedContractValidationSnapshot = contractProductRoot.map { it.dir("imported/validation") }
val contractMetadataPayload = contractProductRoot.map { it.dir("imported/metadata-payload") }
val contractMetadataPhaseRoot = layout.buildDirectory.dir("product-stage/contract/contract/metadata")
val contractMetadataOutputs = contractMetadataPhaseRoot.map { it.dir("outputs") }
val contractMetadataBundle = contractMetadataOutputs.map {
    it.file("codex-agent-contract-$contractVersion.zip")
}
val invalidateContractMetadataPhase = tasks.register<Delete>("invalidateContractMetadataPhase") {
    delete(importedContractValidationSnapshot, contractMetadataPayload, contractMetadataPhaseRoot)
}
val snapshotImportedContractValidationStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedContractValidationStage",
) {
    dependsOn(invalidateContractMetadataPhase)
    sourceDirectory.set(importedContractValidationStage)
    outputDirectory.set(importedContractValidationSnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val verifyImportedContractValidationOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedContractValidationOutputManifest",
) {
    dependsOn(snapshotImportedContractValidationStage)
    product.set("contract")
    component.set("contract")
    phase.set("validation")
    target.set("common")
    productVersion.set(contractVersion)
    stageRoot.set(importedContractValidationSnapshot)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
}
val stageContractMetadataPayload = tasks.register<Sync>("stageContractMetadataPayload") {
    dependsOn(verifyImportedContractValidationOutputManifest)
    into(contractMetadataPayload)
    from(importedContractValidationSnapshot.map { it.dir("outputs") }) {
        include("maven/**", "evidence/**", "inventories/**")
    }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val assembleContractMetadataPayload = tasks.register<Exec>("assembleContractMetadataPayload") {
    group = "publishing"
    description = "Builds the deterministic Contract payload from an authenticated validation stage."
    dependsOn(stageContractMetadataPayload)
    inputs.dir(contractMetadataPayload)
    inputs.property("contractVersion", contractVersion)
    outputs.file(contractMetadataBundle)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    commandLine(
        "python3", "-m", "ci.products.contract", "build",
        "--staging-root", contractMetadataPayload.get().asFile.absolutePath,
        "--output", contractMetadataBundle.get().asFile.absolutePath,
        "--contract-version", contractVersion,
    )
}
val writeContractMetadataOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeContractMetadataOutputManifest",
) {
    group = "publishing"
    description = "Stages the deterministic provenance-free Contract payload."
    dependsOn(assembleContractMetadataPayload)
    product.set("contract")
    component.set("contract")
    phase.set("metadata")
    target.set("common")
    productVersion.set(contractVersion)
    outputRoots.set(mapOf(
        "contract-bundle" to "outputs",
    ))
    outputsDirectory.set(contractMetadataOutputs)
    producerSources.from(contractPythonSources)
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractMetadataPhaseRoot)
    manifestFile.set(contractMetadataPhaseRoot.map { it.file("output-manifest.json") })
}
val requestedProduct = providers.gradleProperty("codexAgent.product")
val requestedComponent = providers.gradleProperty("codexAgent.component")
val requestedPhase = providers.gradleProperty("codexAgent.phase")
tasks.register("ciProductPhase") {
    group = "build"
    description = "Executes one exact product/component/phase lifecycle mapping."
    dependsOn(provider {
        val selection = Triple(requestedProduct.get(), requestedComponent.get(), requestedPhase.get())
        when (selection) {
            Triple("contract", "contract", "binary") -> writeContractBinaryOutputManifest
            Triple("contract", "contract", "package") -> writeContractPackageOutputManifest
            Triple("contract", "contract", "validation") -> writeContractValidationOutputManifest
            Triple("contract", "contract", "metadata") -> writeContractMetadataOutputManifest
            else -> if (selection.first == "sdk") tasks.named("sdkProductPhase")
                else error("Unsupported product phase: ${selection.first}/${selection.second}/${selection.third}")
        }
    })
}
val contractBundleDirectory = contractProductRoot.map { it.dir("bundle") }
val contractBundle = contractBundleDirectory.map { it.file("codex-agent-contract-$contractVersion.zip") }
val deleteLegacyContractDevelopmentKey = tasks.register<Delete>("deleteLegacyContractDevelopmentKey") {
    group = "verification"
    description = "Deletes signing material left by the pre-deterministic Contract lifecycle."
    dependsOn(prepareContractInputs)
    delete(contractProductRoot.map { it.dir("development-key") })
    delete(contractBundleDirectory.map { it.file("development-ed25519.pub") })
}
val localContractPayload = contractProductRoot.map { it.dir("local-payload") }
val stageLocalContractPayload = tasks.register<Sync>("stageLocalContractPayload") {
    dependsOn(writeContractBinaryOutputManifest)
    from(contractStage)
    into(localContractPayload)
    exclude("execution/**")
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val assembleContractBundle = tasks.register<Exec>("assembleContractBundle") {
    group = "publishing"
    description = "Builds the deterministic provenance-free Contract Bundle."
    dependsOn(stageLocalContractPayload, deleteLegacyContractDevelopmentKey)
    inputs.dir(localContractPayload)
    inputs.property("contractVersion", contractVersion)
    outputs.file(contractBundle)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    commandLine(
        "python3", "-m", "ci.products.contract", "build",
        "--staging-root", localContractPayload.get().asFile.absolutePath,
        "--output", contractBundle.get().asFile.absolutePath,
        "--contract-version", contractVersion,
    )
}
val verifyContractBundle = tasks.register<Exec>("verifyContractBundle") {
    group = "verification"
    description = "Verifies the exact deterministic Contract Bundle."
    dependsOn(assembleContractBundle)
    inputs.file(contractBundle)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    commandLine(
        "python3", "-m", "ci.products.contract", "verify",
        "--archive", contractBundle.get().asFile.absolutePath,
    )
}
tasks.register("verifyContract") {
    group = "verification"
    description = "Verifies the isolated Contract publication, behavior evidence, and deterministic bundle."
    dependsOn(verifyContractBundle)
}
