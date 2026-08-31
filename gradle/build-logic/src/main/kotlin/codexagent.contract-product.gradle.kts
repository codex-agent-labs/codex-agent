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
val contractProducerEvent = providers.gradleProperty("codexAgent.producerEvent")
    .orElse(providers.environmentVariable("GITHUB_EVENT_NAME"))
    .orElse("workflow_dispatch")
val contractProducerRunId = providers.gradleProperty("codexAgent.producerRunId")
    .orElse(providers.environmentVariable("GITHUB_RUN_ID"))
    .orElse("1")
val contractProducerRunAttempt = providers.gradleProperty("codexAgent.producerRunAttempt")
    .orElse(providers.environmentVariable("GITHUB_RUN_ATTEMPT"))
    .orElse("1")
val contractProducerPullRequest = providers.gradleProperty("codexAgent.pullRequest")
val contractProducerWorkflowPath = providers.gradleProperty("codexAgent.producerWorkflowPath")
    .orElse(".github/workflows/product-validation.yml")
val contractMetadataDirectory = contractProductRoot.map { it.dir("metadata") }
val prepareContractInputs = tasks.register<Exec>("prepareContractInputs") {
    group = "publishing"
    description = "Binds Contract evidence inventories and producer identity to the current Git tree."
    inputs.property("producerEvent", contractProducerEvent)
    inputs.property("producerRunId", contractProducerRunId)
    inputs.property("producerRunAttempt", contractProducerRunAttempt)
    inputs.property("producerPullRequest", contractProducerPullRequest.orElse(""))
    inputs.property("producerWorkflowPath", contractProducerWorkflowPath)
    outputs.dir(contractMetadataDirectory)
    outputs.upToDateWhen { false }
    environment("PYTHONDONTWRITEBYTECODE", "1")
    val arguments = mutableListOf(
        "python3", "-m", "ci.products.contract", "prepare",
        "--repository-root", layout.projectDirectory.asFile.absolutePath,
        "--output-directory", contractMetadataDirectory.get().asFile.absolutePath,
        "--revision", "HEAD",
        "--repository", CodexAgentBuild.REPOSITORY,
        "--workflow-path", contractProducerWorkflowPath.get(),
        "--event", contractProducerEvent.get(),
        "--run-id", contractProducerRunId.get(),
        "--run-attempt", contractProducerRunAttempt.get(),
    )
    if (contractProducerEvent.get() == "pull_request") {
        arguments += listOf("--pull-request", contractProducerPullRequest.get())
    }
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
val writeContractBinaryOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeContractBinaryOutputManifest",
) {
    group = "publishing"
    description = "Writes and verifies the exact Contract binary-phase output manifest in place."
    dependsOn(stageContractBundleInputs)
    product.set("contract")
    component.set("contract")
    phase.set("binary")
    target.set("common")
    productVersion.set(contractVersion)
    outputRoots.set(mapOf(
        "maven" to "outputs/maven",
        "evidence" to "outputs/evidence",
        "inventory" to "outputs/inventories",
    ))
    outputsDirectory.set(contractStage)
    producerSources.from(layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractBinaryPhaseRoot)
    manifestFile.set(contractBinaryPhaseRoot.map { it.file("output-manifest.json") })
}
val requestedProduct = providers.gradleProperty("codexAgent.product")
val requestedComponent = providers.gradleProperty("codexAgent.component")
val requestedPhase = providers.gradleProperty("codexAgent.phase")
val desktopRuntime = providers.provider {
    checkNotNull(findProject(":codex-agent-runtime-desktop")) {
        "Runtime and SDK product phases require :codex-agent-runtime-desktop"
    }
}
val sdk = providers.provider {
    checkNotNull(findProject(":codex-agent-sdk")) {
        "SDK product phases require :codex-agent-sdk"
    }
}
tasks.register("ciProductPhase") {
    group = "build"
    description = "Executes one exact product/component/phase lifecycle mapping."
    dependsOn(provider {
        val selection = Triple(requestedProduct.get(), requestedComponent.get(), requestedPhase.get())
        when (selection) {
            Triple("contract", "contract", "binary") -> writeContractBinaryOutputManifest
            Triple("runtime", "macos-arm64", "binary") ->
                desktopRuntime.get().tasks.named("writeMacosArm64RuntimeBinaryOutputManifest")
            Triple("runtime", "macos-x64", "binary") ->
                desktopRuntime.get().tasks.named("writeMacosX64RuntimeBinaryOutputManifest")
            Triple("runtime", "linux-arm64", "binary") ->
                desktopRuntime.get().tasks.named("writeLinuxArm64RuntimeBinaryOutputManifest")
            Triple("runtime", "linux-x64", "binary") ->
                desktopRuntime.get().tasks.named("writeLinuxX64RuntimeBinaryOutputManifest")
            Triple("runtime", "windows-x64", "binary") ->
                desktopRuntime.get().tasks.named("writeMingwX64RuntimeBinaryOutputManifest")
            Triple("runtime", "jvm", "binary") ->
                desktopRuntime.get().tasks.named("writeJvmRuntimeBinaryOutputManifest")
            Triple("runtime", "node-js", "binary") ->
                desktopRuntime.get().tasks.named("writeNodeJsRuntimeBinaryOutputManifest")
            Triple("runtime", "node-wasm", "binary") ->
                desktopRuntime.get().tasks.named("writeNodeWasmRuntimeBinaryOutputManifest")
            Triple("runtime", "macos-arm64", "package") ->
                desktopRuntime.get().tasks.named("writeMacosArm64RuntimePackageOutputManifest")
            Triple("runtime", "macos-x64", "package") ->
                desktopRuntime.get().tasks.named("writeMacosX64RuntimePackageOutputManifest")
            Triple("runtime", "linux-arm64", "package") ->
                desktopRuntime.get().tasks.named("writeLinuxArm64RuntimePackageOutputManifest")
            Triple("runtime", "linux-x64", "package") ->
                desktopRuntime.get().tasks.named("writeLinuxX64RuntimePackageOutputManifest")
            Triple("runtime", "windows-x64", "package") ->
                desktopRuntime.get().tasks.named("writeMingwX64RuntimePackageOutputManifest")
            Triple("runtime", "jvm", "package") ->
                desktopRuntime.get().tasks.named("writeJvmRuntimePackageOutputManifest")
            Triple("runtime", "node-js", "package") ->
                desktopRuntime.get().tasks.named("writeNodeJsRuntimePackageOutputManifest")
            Triple("runtime", "node-wasm", "package") ->
                desktopRuntime.get().tasks.named("writeNodeWasmRuntimePackageOutputManifest")
            Triple("runtime", "macos-arm64", "validation") ->
                desktopRuntime.get().tasks.named("writeMacosArm64RuntimeValidationOutputManifest")
            Triple("runtime", "macos-x64", "validation") ->
                desktopRuntime.get().tasks.named("writeMacosX64RuntimeValidationOutputManifest")
            Triple("runtime", "linux-arm64", "validation") ->
                desktopRuntime.get().tasks.named("writeLinuxArm64RuntimeValidationOutputManifest")
            Triple("runtime", "linux-x64", "validation") ->
                desktopRuntime.get().tasks.named("writeLinuxX64RuntimeValidationOutputManifest")
            Triple("runtime", "windows-x64", "validation") ->
                desktopRuntime.get().tasks.named("writeMingwX64RuntimeValidationOutputManifest")
            Triple("runtime", "jvm", "validation") ->
                desktopRuntime.get().tasks.named("writeJvmRuntimeValidationOutputManifest")
            Triple("runtime", "node-js", "validation") ->
                desktopRuntime.get().tasks.named("writeNodeJsRuntimeValidationOutputManifest")
            Triple("runtime", "node-wasm", "validation") ->
                desktopRuntime.get().tasks.named("writeNodeWasmRuntimeValidationOutputManifest")
            Triple("sdk", "javascript", "package") ->
                sdk.get().tasks.named("writeJavaScriptSdkPackageOutputManifest")
            Triple("sdk", "python", "package") ->
                sdk.get().tasks.named("writePythonNativeWrapperSdkPackageOutputManifest")
            Triple("sdk", "csharp", "package") ->
                sdk.get().tasks.named("writeCSharpNativeWrapperSdkPackageOutputManifest")
            Triple("sdk", "rust", "package") ->
                sdk.get().tasks.named("writeRustNativeWrapperSdkPackageOutputManifest")
            Triple("sdk", "cpp", "package") ->
                sdk.get().tasks.named("writeCppNativeWrapperSdkPackageOutputManifest")
            Triple("sdk", "dart", "package") ->
                sdk.get().tasks.named("writeDartNativeWrapperSdkPackageOutputManifest")
            else -> error("Unsupported product phase: ${selection.first}/${selection.second}/${selection.third}")
        }
    })
}
val contractBundleDirectory = contractProductRoot.map { it.dir("bundle") }
val contractBundle = contractBundleDirectory.map { it.file("codex-agent-contract-$contractVersion.zip") }
val contractDevelopmentPublicKey = contractBundleDirectory.map { it.file("development-ed25519.pub") }
val deleteLegacyContractDevelopmentKey = tasks.register<Delete>("deleteLegacyContractDevelopmentKey") {
    group = "verification"
    description = "Deletes private development signing material left by the pre-ephemeral lifecycle."
    dependsOn(prepareContractInputs)
    delete(contractProductRoot.map { it.dir("development-key") })
}
val assembleContractBundle = tasks.register<Exec>("assembleContractBundle") {
    group = "publishing"
    description = "Builds and verifies the Contract Bundle with an ephemeral development private key."
    dependsOn(writeContractBinaryOutputManifest, deleteLegacyContractDevelopmentKey)
    inputs.dir(contractStage)
    inputs.file(contractMetadataDirectory.map { it.file("producer.json") })
    inputs.property("contractVersion", contractVersion)
    outputs.dir(contractBundleDirectory)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    commandLine(
        "python3", "-m", "ci.products.contract", "development-build",
        "--staging-root", contractStage.get().asFile.absolutePath,
        "--output-directory", contractBundleDirectory.get().asFile.absolutePath,
        "--contract-version", contractVersion,
        "--producer", contractMetadataDirectory.get().file("producer.json").asFile.absolutePath,
    )
}
val verifyContractBundle = tasks.register<Exec>("verifyContractBundle") {
    group = "verification"
    description = "Verifies the exact development-signed Contract Bundle."
    dependsOn(assembleContractBundle)
    inputs.file(contractBundle)
    inputs.file(contractDevelopmentPublicKey)
    environment("PYTHONDONTWRITEBYTECODE", "1")
    commandLine(
        "python3", "-m", "ci.products.contract", "verify",
        "--archive", contractBundle.get().asFile.absolutePath,
        "--public-key", contractDevelopmentPublicKey.get().asFile.absolutePath,
    )
}
tasks.register("verifyContract") {
    group = "verification"
    description = "Verifies the isolated Contract publication, behavior evidence, and signed bundle."
    dependsOn(verifyContractBundle)
}
