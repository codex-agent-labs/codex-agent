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
val contractStage = contractProductRoot.map { it.dir("staging") }
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
    dependsOn(stageContractBundleInputs, deleteLegacyContractDevelopmentKey)
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
