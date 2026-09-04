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
    producerSources.from(layout.projectDirectory.dir("ci/products"))
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
    producerSources.from(layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(layout.projectDirectory)
}
val stageContractPackageFromImportedBinary = tasks.register<Sync>(
    "stageContractPackageFromImportedBinary",
) {
    dependsOn(verifyImportedContractBinaryOutputManifest)
    into(contractPackageOutputs)
    from(importedContractBinarySnapshot.map { it.dir("outputs") })
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
    producerSources.from(layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(layout.projectDirectory)
    stageRoot.set(contractPackagePhaseRoot)
    manifestFile.set(contractPackagePhaseRoot.map { it.file("output-manifest.json") })
}
val sdk = providers.provider {
    checkNotNull(findProject(":codex-agent-sdk")) {
        "SDK product phases require :codex-agent-sdk"
    }
}
val sdkFacade = project(":codex-agent-sdk")
val sdkAndroid = project(":codex-agent-runtime-android")
val sdkIos = project(":codex-agent-runtime-ios")

fun registerSdkBinaryPhase(
    component: String,
    title: String,
    target: String,
    repositoryName: String,
    publishingProjects: List<Project>,
    publicationTaskPaths: List<String>,
): TaskProvider<WriteProductOutputManifestTask> {
    val phaseRoot = layout.buildDirectory.dir("product-stage/sdk/$component/binary")
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val mavenRepository = phaseOutputs.map { it.dir("maven") }
    val evidenceDirectory = phaseOutputs.map { it.dir("evidence") }
    publishingProjects.forEach { publishingProject ->
        publishingProject.pluginManager.withPlugin("maven-publish") {
            publishingProject.extensions.configure<PublishingExtension> {
                repositories.maven {
                    name = repositoryName
                    url = mavenRepository.get().asFile.toURI()
                }
            }
        }
    }
    val reset = tasks.register<Delete>("reset${title}BinaryPhase") {
        delete(phaseRoot)
    }
    publicationTaskPaths.forEach { path ->
        val publishingProject = project(path.substringBeforeLast(':').ifEmpty { ":" })
        publishingProject.tasks.matching { it.name == path.substringAfterLast(':') }.configureEach {
            dependsOn(reset)
        }
    }
    val verify = tasks.register<VerifySdkBinaryMavenRepositoryTask>("verify${title}BinaryMavenRepository") {
        dependsOn(publicationTaskPaths)
        repository.set(mavenRepository)
        groupId.set(CodexAgentBuild.MAVEN_GROUP)
        sdkVersion.set(rootProject.extra["codexAgent.sdkVersion"].toString())
        this.component.set(component)
        inventory.set(evidenceDirectory.map { it.file("maven-primary-inventory.json") })
    }
    return tasks.register<WriteProductOutputManifestTask>("write${title}BinaryOutputManifest") {
        group = "publishing"
        description = "Stages the exact Contract-only $component Maven binary outputs."
        dependsOn(verify)
        product.set("sdk")
        this.component.set(component)
        phase.set("binary")
        this.target.set(target)
        productVersion.set(rootProject.extra["codexAgent.sdkVersion"].toString())
        outputRoots.set(mapOf(
            "maven" to "outputs/maven",
            "evidence" to "outputs/evidence",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
    }
}

val authenticatedSdkComponent = rootProject.extra.properties["codexAgent.authenticatedSdkComponent"] as String?
val writeSdkCoreBinaryOutputManifest = if (authenticatedSdkComponent == "sdk-core") {
    registerSdkBinaryPhase(
        component = "sdk-core",
        title = "SdkCore",
        target = "common",
        repositoryName = "SDK_CORE_BINARY_STAGING",
        publishingProjects = listOf(rootProject, sdkFacade),
        publicationTaskPaths = listOf(":publishMavenPublicationToSDK_CORE_BINARY_STAGINGRepository") +
            contractPublicationNames.map {
                ":codex-agent-sdk:publish${it}PublicationToSDK_CORE_BINARY_STAGINGRepository"
            },
    )
} else null
val writeSdkAndroidBinaryOutputManifest = if (authenticatedSdkComponent == "sdk-android") {
    registerSdkBinaryPhase(
        component = "sdk-android",
        title = "SdkAndroid",
        target = "android",
        repositoryName = "SDK_ANDROID_BINARY_STAGING",
        publishingProjects = listOf(sdkAndroid),
        publicationTaskPaths = listOf(
            ":codex-agent-runtime-android:publishMavenPublicationToSDK_ANDROID_BINARY_STAGINGRepository",
        ),
    )
} else null
val writeSdkIosBinaryOutputManifest = if (authenticatedSdkComponent == "sdk-ios") {
    registerSdkBinaryPhase(
        component = "sdk-ios",
        title = "SdkIos",
        target = "ios",
        repositoryName = "SDK_IOS_BINARY_STAGING",
        publishingProjects = listOf(sdkIos),
        publicationTaskPaths = listOf("KotlinMultiplatform", "IosArm64", "IosSimulatorArm64").map {
            ":codex-agent-runtime-ios:publish${it}PublicationToSDK_IOS_BINARY_STAGINGRepository"
        },
    )
} else null
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
            Triple("sdk", "sdk-core", "binary") -> checkNotNull(writeSdkCoreBinaryOutputManifest) {
                "SDK Core binary producer was not authenticated during settings evaluation"
            }
            Triple("sdk", "sdk-core", "package") ->
                sdk.get().tasks.named("writeSdkCorePackageOutputManifest")
            Triple("sdk", "sdk-android", "binary") -> checkNotNull(writeSdkAndroidBinaryOutputManifest) {
                "SDK Android binary producer was not authenticated during settings evaluation"
            }
            Triple("sdk", "sdk-android", "package") ->
                sdk.get().tasks.named("writeSdkAndroidPackageOutputManifest")
            Triple("sdk", "sdk-ios", "binary") -> checkNotNull(writeSdkIosBinaryOutputManifest) {
                "SDK iOS binary producer was not authenticated during settings evaluation"
            }
            Triple("sdk", "sdk-ios", "package") ->
                sdk.get().tasks.named("writeSdkIosPackageOutputManifest")
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
