import java.io.File
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.publish.PublishingExtension
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.bundling.Zip
import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension
import org.jetbrains.kotlin.gradle.targets.native.tasks.KotlinNativeTest

val desktopManifestFile = layout.projectDirectory.file("codex-app-server-distributions.json")
val generateDesktopDistributionSource = tasks.register<GenerateDesktopDistributionSourceTask>(
    "generateDesktopDistributionSource",
) {
    manifestFile.set(desktopManifestFile)
    libraryVersion.set(project.version.toString())
    outputDirectory.set(layout.buildDirectory.dir("generated/distributions/kotlin"))
}
val desktopManifest = readDesktopCodexManifest(desktopManifestFile.asFile)
val localArchiveDirectory = providers.gradleProperty("codexAgent.desktopArchiveDirectory")
val importedClassifierDirectory = providers.gradleProperty("codexAgent.desktopClassifierDirectory")
val supervisorDirectory = providers.gradleProperty("codexAgent.desktopSupervisorDirectory")
    .map(::file)
    .orElse(layout.buildDirectory.dir("supervisor").map { it.asFile })
val hostTarget = crossLanguageCAbiHostTarget(
    System.getProperty("os.name"),
    System.getProperty("os.arch"),
)
val localCAbiRunner = hostTarget?.let(crossLanguageCAbiTargetSpecs::getValue)
val hostSupervisorName = if (hostTarget == "mingwX64") {
    "codex-process-supervisor.exe"
} else {
    "codex-process-supervisor"
}
val compileDesktopProcessSupervisor = tasks.register<CompileDesktopProcessSupervisorTask>(
    "compileDesktopProcessSupervisor",
) {
    group = "distribution"
    description = "Compiles the process supervisor for the current desktop host."
    sourceFile.set(layout.projectDirectory.file("native/supervisor/codex_process_supervisor.c"))
    compiler.set(providers.gradleProperty("codexAgent.desktopSupervisorCompiler")
        .orElse(if (hostTarget == "mingwX64") "cl" else "cc"))
    windows.set(hostTarget == "mingwX64")
    outputFile.set(layout.buildDirectory.file("supervisor/${hostTarget ?: "unsupported"}/$hostSupervisorName"))
    enabled = hostTarget != null
}
val desktopPackageTasks = desktopManifest.distributions.associateWith { distribution ->
    tasks.register<PackageDesktopCodexRuntimeTask>(
        "package${distribution.target.replaceFirstChar(Char::uppercase)}AppServer",
    ) {
        group = "distribution"
        description = "Packages the verified ${distribution.target} Codex app server."
        releaseTag.set(desktopManifest.releaseTag)
        libraryVersion.set(project.version.toString())
        appServerVersion.set(desktopManifest.version)
        target.set(distribution.target)
        classifier.set(distribution.classifier)
        asset.set(distribution.asset)
        archiveSha256.set(distribution.archiveSha256)
        archiveEntry.set(distribution.archiveEntry)
        binarySha256.set(distribution.binarySha256)
        executableName.set(distribution.executableName)
        supervisorExecutableName.set(distribution.supervisorExecutableName)
        if (!importedClassifierDirectory.isPresent ||
            providers.gradleProperty("codexAgent.desktopSupervisorDirectory").isPresent) {
            supervisorExecutable.set(layout.file(supervisorDirectory.map { directory ->
                directory.resolve(distribution.target).resolve(distribution.supervisorExecutableName)
            }))
        }
        prebuiltPackage.set(layout.file(importedClassifierDirectory.map { directory ->
            file("$directory/codex-agent-runtime-desktop-${project.version}-${distribution.classifier}.zip")
        }))
        if (!importedClassifierDirectory.isPresent &&
            !providers.gradleProperty("codexAgent.desktopSupervisorDirectory").isPresent &&
            distribution.target == hostTarget) {
            dependsOn(compileDesktopProcessSupervisor)
        }
        localArchive.set(layout.file(localArchiveDirectory.map { file("$it/${distribution.asset}") }))
        licenseFile.set(rootProject.layout.projectDirectory.file(
            "codex-agent-runtime-android/src/main/assets/openai-codex-LICENSE.txt",
        ))
        noticeFile.set(rootProject.layout.projectDirectory.file(
            "codex-agent-runtime-android/src/main/assets/openai-codex-NOTICE.txt",
        ))
        outputFile.set(layout.buildDirectory.file(
            "distributions/codex-agent-runtime-desktop-${project.version}-${distribution.classifier}.zip",
        ))
    }
}
tasks.register("packageDesktopAppServers") {
    group = "distribution"
    description = "Packages all five verified Codex desktop app-server classifiers."
    dependsOn(desktopPackageTasks.values)
}

tasks.matching {
    it.name in setOf(
        "commonizeCInterop",
        "compileNativeMainKotlinMetadata",
        "compileAppleMainKotlinMetadata",
        "compileMacosMainKotlinMetadata",
        "compileLinuxMainKotlinMetadata",
    )
}.configureEach {
    notCompatibleWithConfigurationCache("Kotlin/Native commonization accesses project state at execution time")
}
@OptIn(ExperimentalWasmDsl::class)
extensions.configure<KotlinMultiplatformExtension> {
    jvmToolchain(17)
    jvm()
    val desktopTargets = listOf(macosArm64(), macosX64(), linuxArm64(), linuxX64(), mingwX64())
    js {
        nodejs()
        binaries.executable()
        generateTypeScriptDefinitions()
        compilerOptions {
            freeCompilerArgs.add("-Xes-long-as-bigint")
        }
    }
    wasmJs {
        nodejs()
        binaries.executable()
    }
    applyDefaultHierarchyTemplate {
        common {
            group("desktop") {
                withJvm()
                withNative()
            }
        }
    }
    sourceSets {
        getByName("nativeMain").dependsOn(getByName("desktopMain"))
        getByName("nativeTest").dependsOn(getByName("desktopTest"))
    }
    desktopTargets.forEach { target ->
        target.binaries.sharedLib {
            val exportPolicyFile = layout.projectDirectory.file(
                when {
                    target.name.startsWith("macos") -> "native/c-api/exports/macos.exports"
                    target.name.startsWith("linux") -> "native/c-api/exports/linux.map"
                    target.name == "mingwX64" -> "native/c-api/exports/windows.def"
                    else -> error("Unsupported Desktop C ABI target ${target.name}")
                },
            )
            linkTaskProvider.configure {
                inputs.file(exportPolicyFile)
                    .withPropertyName("codexAgentCAbiExportPolicy")
                    .withPathSensitivity(PathSensitivity.RELATIVE)
            }
            baseName = "codex_agent"
            when {
                target.name.startsWith("macos") -> linkerOpts(
                    "-Wl,-exported_symbols_list,${exportPolicyFile.asFile}",
                    "-Wl,-install_name,@rpath/libcodex_agent.dylib",
                    "-Wl,-compatibility_version,1.0.0",
                    "-Wl,-current_version,1.12.0",
                )
                target.name.startsWith("linux") -> linkerOpts(
                    "-Wl,--version-script,${exportPolicyFile.asFile}",
                    "-Wl,-soname,libcodex_agent.so.1",
                )
                target.name == "mingwX64" -> linkerOpts(
                    "-Wl,--exclude-all-symbols",
                    exportPolicyFile.asFile.absolutePath,
                )
            }
        }
        target.compilations.getByName("main").cinterops.create("codexDesktop") {
            defFile(layout.projectDirectory.file("src/nativeInterop/cinterop/codex_desktop.def"))
            includeDirs(layout.projectDirectory.dir("native/include"))
        }
        target.compilations.getByName("main").cinterops.create("codexAgentC") {
            defFile(layout.projectDirectory.file("src/nativeInterop/cinterop/codex_agent_c.def"))
            includeDirs(layout.projectDirectory.dir("native/c-api/include"))
        }
    }
    sourceSets.getByName("commonMain").kotlin.srcDir(generateDesktopDistributionSource)
}

val cAbiCandidateCommit = providers.gradleProperty("codexAgent.candidateCommit")
val cAbiCandidateTree = providers.gradleProperty("codexAgent.candidateTree")
val cAbiReviewedHeader = layout.projectDirectory.file("native/c-api/include/codex_agent.h")
val cAbiLicense = rootProject.layout.projectDirectory.file("LICENSE")
val cAbiNotice = rootProject.layout.projectDirectory.file("THIRD_PARTY_NOTICES.md")
fun cAbiExportPolicy(target: String) = layout.projectDirectory.file(
    when {
        target.startsWith("macos") -> "native/c-api/exports/macos.exports"
        target.startsWith("linux") -> "native/c-api/exports/linux.map"
        target == "mingwX64" -> "native/c-api/exports/windows.def"
        else -> error("Unsupported C ABI package target: $target")
    },
)
fun cAbiReleaseLibrary(target: String) = layout.buildDirectory.file(
    "bin/$target/releaseShared/" + when {
        target.startsWith("macos") -> "libcodex_agent.dylib"
        target.startsWith("linux") -> "libcodex_agent.so"
        target == "mingwX64" -> "codex_agent.dll"
        else -> error("Unsupported C ABI package target: $target")
    },
)
val mingwMsvcImportLibrary = layout.buildDirectory.file("c-abi/mingwX64/codex_agent.lib")
val generateMingwX64MsvcImportLibrary = tasks.register<Exec>("generateMingwX64MsvcImportLibrary") {
    group = "distribution"
    description = "Generates the reviewed Windows C ABI MSVC import library."
    dependsOn("linkReleaseSharedMingwX64")
    val definition = cAbiExportPolicy("mingwX64")
    val tool = providers.gradleProperty("codexAgent.cAbiTool.msvcImport").orElse("lib")
    inputs.file(definition).withPathSensitivity(PathSensitivity.RELATIVE)
    inputs.property("tool", tool)
    outputs.file(mingwMsvcImportLibrary)
    outputs.upToDateWhen { false }
    doFirst {
        mingwMsvcImportLibrary.get().asFile.parentFile.mkdirs()
        commandLine(
            tool.get(), "/nologo", "/machine:x64", "/brepro",
            "/def:${definition.asFile.absolutePath}",
            "/out:${mingwMsvcImportLibrary.get().asFile.absolutePath}",
        )
    }
}
val cAbiPackageTasks = crossLanguageCAbiTargetSpecs.mapValues { (target, spec) ->
    tasks.register<PackageCrossLanguageCAbiSdkTask>(
        "package${target.replaceFirstChar(Char::uppercase)}CAbiSdk",
    ) {
        group = "distribution"
        description = "Packages the verified ${spec.classifier} Desktop C ABI SDK."
        dependsOn(if (target == "mingwX64") generateMingwX64MsvcImportLibrary else
            tasks.named("linkReleaseShared${target.replaceFirstChar(Char::uppercase)}"))
        this.target.set(target)
        classifier.set(spec.classifier)
        libraryVersion.set(project.version.toString())
        producerCommit.set(cAbiCandidateCommit)
        producerTree.set(cAbiCandidateTree)
        reviewedHeader.set(cAbiReviewedHeader)
        license.set(cAbiLicense)
        notice.set(cAbiNotice)
        library.set(cAbiReleaseLibrary(target))
        exportPolicy.set(cAbiExportPolicy(target))
        if (target == "mingwX64") {
            gnuImportLibrary.set(layout.buildDirectory.file(
                "bin/mingwX64/releaseShared/libcodex_agent.dll.a",
            ))
            msvcImportLibrary.set(mingwMsvcImportLibrary)
        }
        outputFile.set(layout.buildDirectory.file(
            "distributions/${crossLanguageCAbiArchiveFileName(project.version.toString(), target)}",
        ))
    }
}
val cAbiArchiveFiles = crossLanguageCAbiTargetSpecs.mapValues { (target, _) ->
    if (importedClassifierDirectory.isPresent) {
        layout.file(importedClassifierDirectory.map { directory ->
            file("$directory/${crossLanguageCAbiArchiveFileName(project.version.toString(), target)}")
        })
    } else {
        cAbiPackageTasks.getValue(target).flatMap { it.outputFile }
    }
}
tasks.register("packageDesktopCAbiSdks") {
    group = "distribution"
    description = "Packages all five Desktop C ABI SDK classifiers."
    dependsOn(cAbiPackageTasks.values)
}

val cAbiBootstrapEvidenceFile =
    layout.buildDirectory.file("reports/cross-language-api/c-abi/bootstrap-evidence.json")
val cAbiBootstrapConsumerOutput = layout.buildDirectory.dir("c-abi-bootstrap/consumers")
val invalidateCAbiBootstrapEvidence = tasks.register<Delete>(
    "invalidateCodexAgentCAbiBootstrapEvidence",
) {
    group = "verification"
    description = "Deletes stale observed C ABI bootstrap evidence before prerequisites execute."
    delete(cAbiBootstrapEvidenceFile, cAbiBootstrapConsumerOutput)
}
tasks.configureEach {
    if (name !in setOf(
            invalidateCAbiBootstrapEvidence.name,
            "invalidateJavaScriptTypeScriptBindingParityOutput",
        )
    ) {
        mustRunAfter(invalidateCAbiBootstrapEvidence)
    }
}
rootProject.findProject(":codex-agent-core")?.tasks?.matching {
    it.name == "invalidateCrossLanguageBindingParityOutputs"
}?.configureEach {
    dependsOn(invalidateCAbiBootstrapEvidence)
}
val generateCAbiBootstrapEvidence =
    tasks.register<GenerateCAbiBootstrapEvidenceTask>("generateCodexAgentCAbiBootstrapEvidence") {
    group = "verification"
    description = "Emits observed macOS Arm64 evidence for the finite C ABI bootstrap slice."
    dependsOn(
        invalidateCAbiBootstrapEvidence,
        ":codex-agent-core:verifyCrossLanguageApiCoverage",
        "linkReleaseSharedMacosArm64",
        "macosArm64Test",
    )
    canonicalApiReport.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-api.json",
    ))
    canonicalCoverageReceipt.set(rootProject.layout.projectDirectory.file(
        "codex-agent-core/build/reports/cross-language-api/canonical-coverage.json",
    ))
    reviewedHeader.set(layout.projectDirectory.file("native/c-api/include/codex_agent.h"))
    cinteropDefinition.set(layout.projectDirectory.file("src/nativeInterop/cinterop/codex_agent_c.def"))
    exportPolicy.set(layout.projectDirectory.file("native/c-api/exports/macos.exports"))
    foundationCConsumer.set(layout.projectDirectory.file("native/c-api/consumer/codex_agent_abi_smoke.c"))
    foundationCppConsumer.set(layout.projectDirectory.file("native/c-api/consumer/codex_agent_header_smoke.cpp"))
    lifecycleCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_lifecycle_compile.c"),
    )
    lifecycleCppConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_lifecycle_compile.cpp"),
    )
    conversationValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_conversation_values_compile.c"),
    )
    configurationValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_configuration_values_compile.c"),
    )
    resourceValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_resource_values_compile.c"),
    )
    ordinaryEnumsCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_ordinary_enums_compile.c"),
    )
    formHookValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_form_hook_values_compile.c"),
    )
    invocationAuthValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_invocation_auth_values_compile.c"),
    )
    progressListValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_progress_list_values_compile.c"),
    )
    resourceListValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_resource_list_values_compile.c"),
    )
    listLeafValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_list_leaf_values_compile.c"),
    )
    mcpTransportValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_mcp_transport_values_compile.c"),
    )
    integrationValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_integration_values_compile.c"),
    )
    mcpServerValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_mcp_server_values_compile.c"),
    )
    mcpServerConfigurationValuesCConsumer.set(
        layout.projectDirectory.file(
            "native/c-api/consumer/codex_agent_mcp_server_configuration_values_compile.c",
        ),
    )
    integrationMcpValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_integration_mcp_values_compile.c"),
    )
    conversationAggregateValuesCConsumer.set(
        layout.projectDirectory.file(
            "native/c-api/consumer/codex_agent_conversation_aggregate_values_compile.c",
        ),
    )
    elicitationInteractionValuesCConsumer.set(
        layout.projectDirectory.file(
            "native/c-api/consumer/codex_agent_elicitation_interaction_values_compile.c",
        ),
    )
    hookCatalogValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_hook_catalog_values_compile.c"),
    )
    integrationStateValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_integration_state_values_compile.c"),
    )
    authenticationConfigurationValuesCConsumer.set(
        layout.projectDirectory.file(
            "native/c-api/consumer/codex_agent_authentication_configuration_values_compile.c",
        ),
    )
    elicitationBehaviorValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_elicitation_behavior_values_compile.c"),
    )
    sealedBasePropertyValuesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_sealed_base_property_values_compile.c"),
    )
    rootValueAccessorsCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_root_value_accessors_compile.c"),
    )
    serviceHandlesCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_service_handles_compile.c"),
    )
    suspendOperationsCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_suspend_operations_compile.c"),
    )
    stateFlowsCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_state_flows_compile.c"),
    )
    interactionIdentityCConsumer.set(
        layout.projectDirectory.file("native/c-api/consumer/codex_agent_interaction_identity_compile.c"),
    )
    releaseLibrary.set(layout.buildDirectory.file("bin/macosArm64/releaseShared/libcodex_agent.dylib"))
    generatedHeader.set(layout.buildDirectory.file("bin/macosArm64/releaseShared/libcodex_agent_api.h"))
    nativeTestExecutable.set(layout.buildDirectory.file("bin/macosArm64/debugTest/test.kexe"))
    nativeTestResults.set(layout.buildDirectory.dir("test-results/macosArm64Test"))
    nativeMainSources.set(layout.projectDirectory.dir(
        "src/nativeMain/kotlin/io/github/codex_agent_labs/codexmobile/capi",
    ))
    nativeTestSources.set(layout.projectDirectory.dir(
        "src/nativeTest/kotlin/io/github/codex_agent_labs/codexmobile/capi",
    ))
    consumerOutputDirectory.set(cAbiBootstrapConsumerOutput)
    evidenceFile.set(cAbiBootstrapEvidenceFile)
}
val cAbiScenarioProofFile =
    layout.buildDirectory.file("reports/cross-language-api/c-abi/c-abi-scenarios.json")
tasks.register<GenerateCrossLanguageCAbiScenarioProofTask>("generateCodexAgentCAbiScenarioProof") {
    group = "verification"
    description = "Emits the exact14-scenario C ABI behavior proof from observed Native evidence."
    dependsOn(generateCAbiBootstrapEvidence)
    bootstrapEvidence.set(cAbiBootstrapEvidenceFile)
    proofFile.set(cAbiScenarioProofFile)
}

val nodeRuntimeEvidenceRunnerArchive = layout.file(
    providers.gradleProperty("codexAgent.nodeRuntimeEvidenceRunnerArchive").map(::File),
)
val nodeWasmRuntimeEvidenceRunnerArchive = layout.file(
    providers.gradleProperty("codexAgent.nodeWasmRuntimeEvidenceRunnerArchive").map(::File),
)
val nodeClassifierArchive = layout.file(
    providers.gradleProperty("codexAgent.nodeClassifierArchive").map(::File),
)
val nodeEvidenceRunners = listOf(
    Triple("nodeRuntime", "js", nodeRuntimeEvidenceRunnerArchive),
    Triple("nodeWasmRuntime", "wasm", nodeWasmRuntimeEvidenceRunnerArchive),
)
desktopManifest.distributions.forEach { distribution ->
    nodeEvidenceRunners.forEach { (taskPrefix, backend, runnerArchive) ->
        tasks.register<RecordNodeRuntimeEvidenceTask>(
            "$taskPrefix${distribution.target.replaceFirstChar(Char::uppercase)}Test",
        ) {
            group = "verification"
            description = "Runs the exact ${distribution.target} Node $backend App Server lifecycle evidence."
            candidateCommit.set(providers.gradleProperty("codexAgent.candidateCommit"))
            target.set(distribution.target)
            runtimeBackend.set(backend)
            runnerOs.set(providers.environmentVariable("RUNNER_OS"))
            runnerArch.set(providers.environmentVariable("RUNNER_ARCH"))
            nodeExecutable.set(providers.gradleProperty("codexAgent.nodeExecutable").orElse("node"))
            distributionManifest.set(desktopManifestFile)
            classifierArchive.set(nodeClassifierArchive)
            compiledNodeTestRuntime.set(runnerArchive)
            evidenceFile.set(layout.buildDirectory.file(
                "reports/node-runtime-evidence/${nodeRuntimeEvidenceFileName(distribution.target, backend)}",
            ))
            testReport.set(layout.buildDirectory.file(
                "test-results/node-runtime-evidence/${nodeRuntimeTestReportFileName(distribution.target, backend)}",
            ))
        }
    }
}

val jvmTestRuntimeClasspath = configurations.named("jvmTestRuntimeClasspath")
val packageJvmRuntimeEvidenceRunner = tasks.register<Zip>("packageJvmRuntimeEvidenceRunner") {
    group = "distribution"
    description = "Packages the portable JVM runtime evidence runner."
    dependsOn("jvmTestClasses")
    archiveFileName.set("codex-agent-jvm-runtime-evidence-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    from(layout.buildDirectory.dir("classes/kotlin/jvm/main")) { into("classes") }
    from(layout.buildDirectory.dir("classes/kotlin/jvm/test")) { into("classes") }
    from(layout.buildDirectory.dir("processedResources/jvm/main")) { into("classes") }
    from(layout.buildDirectory.dir("processedResources/jvm/test")) { into("classes") }
    from(jvmTestRuntimeClasspath.map { files -> files.filter { it.isDirectory } }) { into("classes") }
    from(jvmTestRuntimeClasspath.map { files -> files.filter { it.isFile } }) { into("lib") }
}
check(desktopManifest.distributions.map { it.target }.toSet() == desktopRuntimeEvidenceTargets.keys) {
    "Desktop evidence target set does not match the distribution manifest"
}
val requestedEvidenceTarget = providers.gradleProperty("codexAgent.desktopEvidenceTarget").orNull
requestedEvidenceTarget?.let { check(it in desktopRuntimeEvidenceTargets) { "Unknown desktop evidence target: $it" } }
val cAbiConsumerSources = layout.projectDirectory.dir("native/c-api/consumer").asFileTree.matching {
    include("*.c", "*.cpp")
}
fun cAbiToolDefaults(target: String): Map<String, String> = when {
    target.startsWith("macos") -> mapOf(
        "c" to "clang", "cpp" to "clang++", "file" to "file", "architecture" to "lipo",
        "symbols" to "nm", "loader" to "otool", "versions" to "otool",
    )
    target.startsWith("linux") -> mapOf(
        "c" to "cc", "cpp" to "c++", "file" to "file", "architecture" to "readelf",
        "symbols" to "nm", "loader" to "readelf", "versions" to "readelf",
    )
    target == "mingwX64" -> mapOf(
        "c" to "cl", "cpp" to "cl", "gnuC" to "gcc", "gnuCpp" to "g++",
        "architecture" to "dumpbin", "symbols" to "dumpbin", "msvcImport" to "lib",
        "gnuImport" to "nm",
    )
    else -> error("Unsupported C ABI evidence target: $target")
}
desktopManifest.distributions.forEach { distribution ->
    val packageTask = desktopPackageTasks.getValue(distribution)
    val targetTitle = distribution.target.replaceFirstChar(Char::uppercase)
    val validateEvidenceTarget = tasks.register("validate${targetTitle}DesktopEvidenceTarget") {
        inputs.property("requestedTarget", providers.gradleProperty("codexAgent.desktopEvidenceTarget").orElse(""))
        inputs.property("expectedTarget", distribution.target)
        doLast {
            check(inputs.properties.getValue("requestedTarget") == inputs.properties.getValue("expectedTarget")) {
                "-PcodexAgent.desktopEvidenceTarget must equal ${distribution.target}"
            }
        }
    }
    tasks.register<GenerateCrossLanguageCAbiPackageEvidenceTask>(
        "generate${targetTitle}CAbiPackageEvidence",
    ) {
        group = "verification"
        description = "Executes exact ${distribution.target} C ABI package and consumer evidence."
        dependsOn(validateEvidenceTarget)
        if (!importedClassifierDirectory.isPresent) dependsOn(cAbiPackageTasks.getValue(distribution.target))
        target.set(distribution.target)
        classifier.set(crossLanguageCAbiTargetSpecs.getValue(distribution.target).classifier)
        libraryVersion.set(project.version.toString())
        producerCommit.set(cAbiCandidateCommit)
        producerTree.set(cAbiCandidateTree)
        runnerOs.set(providers.environmentVariable("RUNNER_OS")
            .orElse(localCAbiRunner?.runnerOs ?: "unsupported"))
        runnerArch.set(providers.environmentVariable("RUNNER_ARCH")
            .orElse(localCAbiRunner?.runnerArch ?: "unsupported"))
        cAbiToolDefaults(distribution.target).forEach { (id, executable) ->
            tools.put(id, providers.gradleProperty("codexAgent.cAbiTool.$id").orElse(executable))
        }
        compileOnlyConsumers.set(crossLanguageCAbiCompileOnlyConsumers.sorted())
        packageFile.set(cAbiArchiveFiles.getValue(distribution.target))
        reviewedHeader.set(cAbiReviewedHeader)
        license.set(cAbiLicense)
        notice.set(cAbiNotice)
        exportPolicy.set(cAbiExportPolicy(distribution.target))
        consumerSources.from(cAbiConsumerSources)
        evidenceFile.set(layout.buildDirectory.file(
            "reports/cross-language-api/c-abi/packages/" +
                crossLanguageCAbiPackageEvidenceFileName(distribution.target),
        ))
    }
    registerJvmRuntimeEvidenceTask(
        distribution,
        packageTask,
        validateEvidenceTarget,
        packageJvmRuntimeEvidenceRunner,
        layout.projectDirectory.file("codex-app-server-distributions.json"),
    )
    val testTaskName = "${distribution.target}Test"
    if (requestedEvidenceTarget == distribution.target) {
        val evidenceRoot = layout.buildDirectory.dir("desktop-runtime-evidence/${distribution.target}")
        tasks.named<KotlinNativeTest>(testTaskName) {
            dependsOn(packageTask)
            environment(
                RUNTIME_BUNDLE_DIRECTORY_ENV,
                packageTask.flatMap { it.outputFile }.get().asFile.parentFile.absolutePath,
            )
            environment(RUNTIME_DATA_DIRECTORY_ENV, evidenceRoot.get().dir("data").asFile.absolutePath)
            environment(RUNTIME_WORKSPACE_ENV, evidenceRoot.get().dir("workspace").asFile.absolutePath)
            doFirst {
                evidenceRoot.get().dir("data").asFile.mkdirs()
                evidenceRoot.get().dir("workspace").asFile.mkdirs()
            }
            outputs.upToDateWhen { false }
        }
    }
    tasks.matching { it.name == testTaskName }.configureEach { mustRunAfter(validateEvidenceTarget) }
    tasks.register<RecordDesktopRuntimeEvidenceTask>("record${targetTitle}DesktopRuntimeEvidence") {
        group = "verification"
        description = "Runs and records the ${distribution.target} official app-server lifecycle smoke."
        dependsOn(validateEvidenceTarget, testTaskName)
        target.set(distribution.target)
        classifier.set(distribution.classifier)
        binarySha256.set(distribution.binarySha256)
        candidateCommit.set(providers.gradleProperty("codexAgent.candidateCommit"))
        runnerOs.set(providers.environmentVariable("RUNNER_OS"))
        runnerArch.set(providers.environmentVariable("RUNNER_ARCH"))
        classifierArchive.set(packageTask.flatMap { it.outputFile })
        distributionManifest.set(layout.projectDirectory.file("codex-app-server-distributions.json"))
        testReport.set(layout.buildDirectory.file(
            "test-results/${distribution.target}Test/TEST-${distribution.target}Test." +
                "io.github.codex_agent_labs.codexmobile.appserver.runtime.DesktopCodexRuntimeTest.xml",
        ))
        evidenceFile.set(layout.buildDirectory.file(
            "reports/desktop-runtime-evidence/${desktopRuntimeEvidenceFileName(distribution.target)}",
        ))
    }
}

pluginManager.withPlugin("maven-publish") {
    extensions.configure<PublishingExtension> {
        publications.withType(MavenPublication::class.java).configureEach {
            if (name == "kotlinMultiplatform") {
                desktopPackageTasks.forEach { (distribution, packageTask) ->
                    artifact(packageTask.flatMap { it.outputFile }) {
                        classifier = distribution.classifier
                        extension = "zip"
                        builtBy(packageTask)
                    }
                }
                crossLanguageCAbiTargetSpecs.forEach { (target, spec) ->
                    artifact(cAbiArchiveFiles.getValue(target)) {
                        classifier = spec.classifier
                        extension = "zip"
                        if (!importedClassifierDirectory.isPresent) builtBy(cAbiPackageTasks.getValue(target))
                    }
                }
            }
        }
    }
}
