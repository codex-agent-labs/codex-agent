import java.io.File
import org.gradle.api.Task
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.publish.PublishingExtension
import org.gradle.api.publish.maven.MavenPublication
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.TaskProvider
import org.gradle.api.tasks.bundling.Zip
import org.gradle.jvm.tasks.Jar
import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
import org.jetbrains.kotlin.gradle.dsl.KotlinMultiplatformExtension
import org.jetbrains.kotlin.gradle.targets.native.tasks.KotlinNativeTest

val desktopManifestFile = layout.projectDirectory.file("codex-app-server-distributions.json")
val desktopRuntimeCompatibilityVersion = providers.provider {
    runtimeCompatibilityVersion(project.version.toString())
}
extensions.extraProperties["codexAgent.runtimeCompatibilityVersion"] = desktopRuntimeCompatibilityVersion
val generateDesktopDistributionSource = tasks.register<GenerateDesktopDistributionSourceTask>(
    "generateDesktopDistributionSource",
) {
    manifestFile.set(desktopManifestFile)
    libraryVersion.set(desktopRuntimeCompatibilityVersion)
    outputDirectory.set(layout.buildDirectory.dir("generated/distributions/kotlin"))
}
val desktopManifest = readDesktopCodexManifest(desktopManifestFile.asFile)
val localArchiveDirectory = providers.gradleProperty("codexAgent.desktopArchiveDirectory")
val importedClassifierDirectory = providers.gradleProperty("codexAgent.desktopClassifierDirectory")
val importedRuntimeBinaryStage = providers.gradleProperty("codexAgent.runtimeBinaryStage").map(::file)
val importedRuntimePackageStage = providers.gradleProperty("codexAgent.runtimePackageStage").map(::file)
val importedRuntimeNativePackageStage = providers.gradleProperty("codexAgent.runtimeNativePackageStage").map(::file)
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
val mingwGnuImportLibrary = layout.buildDirectory.file(
    "bin/mingwX64/releaseShared/libcodex_agent.dll.a",
)
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
        libraryVersion.set(desktopRuntimeCompatibilityVersion)
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
            file(
                "$directory/codex-agent-runtime-desktop-${desktopRuntimeCompatibilityVersion.get()}-" +
                    "${distribution.classifier}.zip",
            )
        }))
        if (!importedClassifierDirectory.isPresent &&
            !importedRuntimeBinaryStage.isPresent &&
            !providers.gradleProperty("codexAgent.desktopSupervisorDirectory").isPresent &&
            distribution.target == hostTarget) {
            dependsOn(compileDesktopProcessSupervisor)
        }
        localArchive.set(layout.file(localArchiveDirectory.map { file("$it/${distribution.asset}") }))
        licenseFile.set(rootProject.layout.projectDirectory.file(
            "legal/openai-codex/openai-codex-LICENSE.txt",
        ))
        noticeFile.set(rootProject.layout.projectDirectory.file(
            "legal/openai-codex/openai-codex-NOTICE.txt",
        ))
        outputFile.set(layout.buildDirectory.file(desktopRuntimeCompatibilityVersion.map { version ->
            "distributions/codex-agent-runtime-desktop-$version-${distribution.classifier}.zip"
        }))
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
                target.name == "mingwX64" -> {
                    linkTaskProvider.configure {
                        outputs.file(mingwGnuImportLibrary)
                    }
                    linkerOpts(
                        "-Wl,--exclude-all-symbols",
                        "-Wl,--out-implib,${mingwGnuImportLibrary.get().asFile.absolutePath}",
                        exportPolicyFile.asFile.absolutePath,
                    )
                }
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
    commandLine(
        tool.get(), "/nologo", "/machine:x64", "/brepro",
        "/def:${definition.asFile.absolutePath}",
        "/out:${mingwMsvcImportLibrary.get().asFile.absolutePath}",
    )
    doFirst {
        outputs.files.singleFile.parentFile.mkdirs()
    }
}
val cAbiPackageTasks = crossLanguageCAbiTargetSpecs.mapValues { (target, spec) ->
    tasks.register<PackageCrossLanguageCAbiSdkTask>(
        "package${target.replaceFirstChar(Char::uppercase)}CAbiSdk",
    ) {
        group = "distribution"
        description = "Packages the verified ${spec.classifier} Desktop C ABI SDK."
        if (!importedRuntimeBinaryStage.isPresent) {
            dependsOn(if (target == "mingwX64") generateMingwX64MsvcImportLibrary else
                tasks.named("linkReleaseShared${target.replaceFirstChar(Char::uppercase)}"))
        }
        this.target.set(target)
        classifier.set(spec.classifier)
        libraryVersion.set(desktopRuntimeCompatibilityVersion)
        producerCommit.set(cAbiCandidateCommit)
        producerTree.set(cAbiCandidateTree)
        reviewedHeader.set(cAbiReviewedHeader)
        license.set(cAbiLicense)
        notice.set(cAbiNotice)
        library.set(cAbiReleaseLibrary(target))
        exportPolicy.set(cAbiExportPolicy(target))
        if (target == "mingwX64") {
            gnuImportLibrary.set(mingwGnuImportLibrary)
            msvcImportLibrary.set(mingwMsvcImportLibrary)
        }
        outputFile.set(layout.buildDirectory.file(desktopRuntimeCompatibilityVersion.map { version ->
            "distributions/${crossLanguageCAbiArchiveFileName(version, target)}"
        }))
    }
}
val runtimeNativeBinaryManifestTasks = desktopManifest.distributions.associate { distribution ->
    val target = distribution.target
    val title = target.replaceFirstChar(Char::uppercase)
    val component = crossLanguageCAbiTargetSpecs.getValue(target).classifier.removePrefix("c-abi-")
    val prepareAppServerArchive = tasks.register<PreparePinnedArchiveTask>(
        "prepare${title}AppServerArchive",
    ) {
        group = "distribution"
        description = "Prepares the pinned raw $component Codex app-server archive."
        sourceUrl.set(
            "https://github.com/openai/codex/releases/download/${desktopManifest.releaseTag}/${distribution.asset}",
        )
        expectedSha256.set(distribution.archiveSha256)
        localArchive.set(layout.file(localArchiveDirectory.map { file("$it/${distribution.asset}") }))
        outputFile.set(layout.buildDirectory.file("raw-app-server/$target/${distribution.asset}"))
    }
    val phaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/binary")
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val binarySupervisor = layout.file(supervisorDirectory.map { directory ->
        directory.resolve(target).resolve(distribution.supervisorExecutableName)
    })
    val stage = tasks.register<Sync>("stage${title}RuntimeBinaryOutputs") {
        group = "distribution"
        description = "Stages the exact raw $component Runtime binary outputs once."
        dependsOn(prepareAppServerArchive, "linkDebugTest$title")
        dependsOn(if (target == "mingwX64") generateMingwX64MsvcImportLibrary else
            tasks.named("linkReleaseShared$title"))
        if (!providers.gradleProperty("codexAgent.desktopSupervisorDirectory").isPresent) {
            dependsOn(compileDesktopProcessSupervisor)
        }
        into(phaseOutputs)
        from(layout.buildDirectory.dir("classes/kotlin/$target/main/klib/codex-agent-runtime-desktop")) {
            into("kmp-klib")
        }
        from(cAbiReleaseLibrary(target)) { into("c-abi/lib") }
        from(layout.buildDirectory.file("bin/$target/releaseShared/libcodex_agent_api.h")) {
            into("c-abi/compiler-header")
        }
        from(cAbiReviewedHeader) { into("c-abi/include") }
        from(cAbiExportPolicy(target)) { into("c-abi/export-policy") }
        if (target == "mingwX64") {
            from(mingwGnuImportLibrary) { into("c-abi/lib") }
            from(mingwMsvcImportLibrary) { into("c-abi/lib") }
        }
        from(binarySupervisor) { into("supervisor") }
        from(prepareAppServerArchive.flatMap { it.outputFile }) { into("app-server") }
        from(layout.buildDirectory.file(
            "bin/$target/debugTest/" + if (target == "mingwX64") "test.exe" else "test.kexe",
        )) { into("validation-runner") }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    val writeBinaryManifest = tasks.register<WriteProductOutputManifestTask>(
        "write${title}RuntimeBinaryOutputManifest",
    ) {
        group = "distribution"
        description = "Writes and verifies the exact raw $component Runtime binary manifest."
        dependsOn(stage)
        product.set("runtime")
        this.component.set(component)
        phase.set("binary")
        this.target.set(component)
        productVersion.set(project.version.toString())
        outputRoots.set(mapOf(
            "app-server" to "outputs/app-server",
            "c-abi" to "outputs/c-abi",
            "kmp-klib" to "outputs/kmp-klib",
            "supervisor" to "outputs/supervisor",
            "validation-runner" to "outputs/validation-runner",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
    }
    val importedBinarySnapshotRoot = layout.buildDirectory.dir(
        cAbiCandidateTree.map { "imported-runtime-binary-stages/$it/$component" },
    )
    val snapshotImportedBinary = tasks.register<SnapshotImportedProductStageTask>(
        "snapshotImported${title}RuntimeBinaryStage",
    ) {
        sourceDirectory.set(layout.dir(importedRuntimeBinaryStage))
        outputDirectory.set(importedBinarySnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verifyImportedBinaryManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImported${title}RuntimeBinaryOutputManifest",
    ) {
        group = "verification"
        description = "Verifies the imported raw $component Runtime binary manifest and complete tree."
        product.set("runtime")
        this.component.set(component)
        phase.set("binary")
        this.target.set(component)
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedBinary)
        stageRoot.set(importedBinarySnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    if (importedRuntimeBinaryStage.isPresent) {
        desktopPackageTasks.getValue(distribution).configure {
            dependsOn(verifyImportedBinaryManifest)
            localArchive.set(importedBinarySnapshotRoot.map {
                it.file("outputs/app-server/${distribution.asset}")
            })
            supervisorExecutable.set(importedBinarySnapshotRoot.map {
                it.file("outputs/supervisor/${distribution.supervisorExecutableName}")
            })
        }
        cAbiPackageTasks.getValue(target).configure {
            dependsOn(verifyImportedBinaryManifest)
            reviewedHeader.set(importedBinarySnapshotRoot.map {
                it.file("outputs/c-abi/include/codex_agent.h")
            })
            exportPolicy.set(importedBinarySnapshotRoot.map {
                it.file("outputs/c-abi/export-policy/${cAbiExportPolicy(target).asFile.name}")
            })
            library.set(importedBinarySnapshotRoot.map {
                it.file("outputs/c-abi/lib/${cAbiReleaseLibrary(target).get().asFile.name}")
            })
            if (target == "mingwX64") {
                gnuImportLibrary.set(importedBinarySnapshotRoot.map {
                    it.file("outputs/c-abi/lib/${mingwGnuImportLibrary.get().asFile.name}")
                })
                msvcImportLibrary.set(importedBinarySnapshotRoot.map {
                    it.file("outputs/c-abi/lib/${mingwMsvcImportLibrary.get().asFile.name}")
                })
            }
        }
    }
    val packagePhaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/package")
    val packagePhaseOutputs = packagePhaseRoot.map { it.dir("outputs") }
    val packageBinaryStageRoot = if (importedRuntimeBinaryStage.isPresent) {
        importedBinarySnapshotRoot
    } else {
        phaseRoot
    }
    val stagePackages = tasks.register<Sync>("stage${title}RuntimePackages") {
        group = "distribution"
        description = "Stages the exact $component Runtime packages once."
        dependsOn(desktopPackageTasks.getValue(distribution), cAbiPackageTasks.getValue(target))
        dependsOn(if (importedRuntimeBinaryStage.isPresent) verifyImportedBinaryManifest else writeBinaryManifest)
        into(packagePhaseOutputs)
        from(desktopPackageTasks.getValue(distribution).flatMap { it.outputFile }) { into("app-server") }
        from(cAbiPackageTasks.getValue(target).flatMap { it.outputFile }) { into("c-abi") }
        from(packageBinaryStageRoot.map { it.dir("outputs/validation-runner") }) {
            into("validation-runner")
        }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    tasks.register<WriteProductOutputManifestTask>("write${title}RuntimePackageOutputManifest") {
        group = "distribution"
        description = "Writes and verifies the exact $component Runtime package manifest."
        dependsOn(stagePackages)
        product.set("runtime")
        this.component.set(component)
        phase.set("package")
        this.target.set(component)
        productVersion.set(project.version.toString())
        outputRoots.set(mapOf(
            "app-server" to "outputs/app-server",
            "c-abi" to "outputs/c-abi",
            "validation-runner" to "outputs/validation-runner",
        ))
        outputsDirectory.set(packagePhaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(packagePhaseRoot)
        manifestFile.set(packagePhaseRoot.map { it.file("output-manifest.json") })
    }
    component to writeBinaryManifest
}
val cAbiArchiveFiles = crossLanguageCAbiTargetSpecs.mapValues { (target, _) ->
    if (importedClassifierDirectory.isPresent) {
        layout.file(importedClassifierDirectory.flatMap { directory ->
            desktopRuntimeCompatibilityVersion.map { version ->
                file("$directory/${crossLanguageCAbiArchiveFileName(version, target)}")
            }
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
    mustRunAfter(invalidateCAbiBootstrapEvidence)
}
rootProject.tasks.matching { it.name == "prepareContractInputs" }.configureEach {
    mustRunAfter(invalidateCAbiBootstrapEvidence)
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
        "src/nativeMain/kotlin/io/github/codex_agent_labs/codexagent/capi",
    ))
    nativeTestSources.set(layout.projectDirectory.dir(
        "src/nativeTest/kotlin/io/github/codex_agent_labs/codexagent/capi",
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
val jvmRuntimeBinaryPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/jvm/binary")
val jvmRuntimeBinaryOutputs = jvmRuntimeBinaryPhaseRoot.map { it.dir("outputs") }
val jvmRuntimeJar = tasks.named<Jar>("jvmJar")
val stageJvmRuntimeBinaryOutputs = tasks.register<Sync>("stageJvmRuntimeBinaryOutputs") {
    group = "distribution"
    description = "Stages the exact raw JVM Runtime binary outputs once."
    dependsOn(jvmRuntimeJar, packageJvmRuntimeEvidenceRunner)
    into(jvmRuntimeBinaryOutputs)
    from(jvmRuntimeJar.flatMap { it.archiveFile }) { into("adapter") }
    from(packageJvmRuntimeEvidenceRunner.flatMap { it.archiveFile }) { into("validation-runner") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val writeJvmRuntimeBinaryOutputManifest = tasks.register<WriteProductOutputManifestTask>(
    "writeJvmRuntimeBinaryOutputManifest",
) {
    group = "distribution"
    description = "Writes and verifies the exact raw JVM Runtime binary manifest."
    dependsOn(stageJvmRuntimeBinaryOutputs)
    product.set("runtime")
    component.set("jvm")
    phase.set("binary")
    target.set("jvm")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(jvmRuntimeBinaryOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(jvmRuntimeBinaryPhaseRoot)
    manifestFile.set(jvmRuntimeBinaryPhaseRoot.map { it.file("output-manifest.json") })
}
val importedJvmRuntimeBinarySnapshotRoot = layout.buildDirectory.dir(
    cAbiCandidateTree.map { "imported-runtime-binary-stages/$it/jvm" },
)
val snapshotImportedJvmRuntimeBinaryStage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedJvmRuntimeBinaryStage",
) {
    sourceDirectory.set(layout.dir(importedRuntimeBinaryStage))
    outputDirectory.set(importedJvmRuntimeBinarySnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val jvmRuntimeBinaryStageRoot = if (importedRuntimeBinaryStage.isPresent) {
    importedJvmRuntimeBinarySnapshotRoot
} else {
    jvmRuntimeBinaryPhaseRoot
}
val verifyImportedJvmRuntimeBinaryOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedJvmRuntimeBinaryOutputManifest",
) {
    group = "verification"
    description = "Verifies the imported raw JVM Runtime binary manifest and complete tree."
    product.set("runtime")
    component.set("jvm")
    phase.set("binary")
    target.set("jvm")
    productVersion.set(project.version.toString())
    dependsOn(snapshotImportedJvmRuntimeBinaryStage)
    stageRoot.set(importedJvmRuntimeBinarySnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val jvmRuntimePackagePhaseRoot = layout.buildDirectory.dir("product-stage/runtime/jvm/package")
val jvmRuntimePackageOutputs = jvmRuntimePackagePhaseRoot.map { it.dir("outputs") }
val stageJvmRuntimePackage = tasks.register<Sync>("stageJvmRuntimePackage") {
    group = "distribution"
    description = "Stages the exact JVM Runtime package from a verified binary stage."
    dependsOn(if (importedRuntimeBinaryStage.isPresent) {
        verifyImportedJvmRuntimeBinaryOutputManifest
    } else {
        writeJvmRuntimeBinaryOutputManifest
    })
    into(jvmRuntimePackageOutputs)
    from(jvmRuntimeBinaryStageRoot.map { it.dir("outputs/adapter") }) { into("adapter") }
    from(jvmRuntimeBinaryStageRoot.map { it.dir("outputs/validation-runner") }) {
        into("validation-runner")
    }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeJvmRuntimePackageOutputManifest") {
    group = "distribution"
    description = "Writes and verifies the exact JVM Runtime package manifest."
    dependsOn(stageJvmRuntimePackage)
    product.set("runtime")
    component.set("jvm")
    phase.set("package")
    target.set("jvm")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(jvmRuntimePackageOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(jvmRuntimePackagePhaseRoot)
    manifestFile.set(jvmRuntimePackagePhaseRoot.map { it.file("output-manifest.json") })
}
check(desktopManifest.distributions.map { it.target }.toSet() == desktopRuntimeEvidenceTargets.keys) {
    "Desktop evidence target set does not match the distribution manifest"
}
val requestedEvidenceTarget = providers.gradleProperty("codexAgent.desktopEvidenceTarget").orNull
requestedEvidenceTarget?.let { check(it in desktopRuntimeEvidenceTargets) { "Unknown desktop evidence target: $it" } }
val productPhaseEvidenceTarget = providers.gradleProperty("codexAgent.desktopEvidenceTarget").orElse(
    providers.gradleProperty("codexAgent.component").map { component ->
        crossLanguageCAbiTargetSpecs.entries.single {
            it.value.classifier.removePrefix("c-abi-") == component
        }.key
    },
)
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
        inputs.property("requestedTarget", productPhaseEvidenceTarget.orElse(""))
        inputs.property("expectedTarget", distribution.target)
        doLast {
            check(inputs.properties.getValue("requestedTarget") == inputs.properties.getValue("expectedTarget")) {
                "-PcodexAgent.desktopEvidenceTarget must equal ${distribution.target}"
            }
        }
    }
    val cAbiPackageEvidence = tasks.register<GenerateCrossLanguageCAbiPackageEvidenceTask>(
        "generate${targetTitle}CAbiPackageEvidence",
    ) {
        group = "verification"
        description = "Executes exact ${distribution.target} C ABI package and consumer evidence."
        dependsOn(validateEvidenceTarget)
        if (!importedClassifierDirectory.isPresent && !importedRuntimePackageStage.isPresent) {
            dependsOn(cAbiPackageTasks.getValue(distribution.target))
        }
        target.set(distribution.target)
        classifier.set(crossLanguageCAbiTargetSpecs.getValue(distribution.target).classifier)
        libraryVersion.set(desktopRuntimeCompatibilityVersion)
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
        tasks.withType<KotlinNativeTest>().matching { it.name == testTaskName }.configureEach {
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
                "io.github.codex_agent_labs.codexagent.appserver.runtime.DesktopCodexRuntimeTest.xml",
        ))
        evidenceFile.set(layout.buildDirectory.file(
            "reports/desktop-runtime-evidence/${desktopRuntimeEvidenceFileName(distribution.target)}",
        ))
    }
    val component = crossLanguageCAbiTargetSpecs.getValue(distribution.target).classifier.removePrefix("c-abi-")
    val localPackagePhaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/package")
    val importedPackageSnapshotRoot = layout.buildDirectory.dir(
        cAbiCandidateTree.map { "imported-runtime-package-stages/$it/$component" },
    )
    val snapshotImportedPackage = tasks.register<SnapshotImportedProductStageTask>(
        "snapshotImported${targetTitle}RuntimePackageStage",
    ) {
        sourceDirectory.set(layout.dir(importedRuntimePackageStage))
        outputDirectory.set(importedPackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val validationPackageRoot = if (importedRuntimePackageStage.isPresent) {
        importedPackageSnapshotRoot
    } else {
        localPackagePhaseRoot
    }
    val validationPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/validation")
    val validationPhaseOutputs = validationPhaseRoot.map { it.dir("outputs") }
    val importedNativeEvidenceFile = layout.buildDirectory.file(
        "reports/imported-desktop-runtime-evidence/${desktopRuntimeEvidenceFileName(distribution.target)}",
    )
    val importedNativeTestReport = layout.buildDirectory.file(
        "test-results/imported-desktop-runtime-evidence/TEST-${distribution.target}Test." +
            "$DESKTOP_RUNTIME_TEST_CLASS.xml",
    )
    val invalidateValidationOutputs = tasks.register<Delete>("invalidate${targetTitle}RuntimeValidationOutputs") {
        group = "verification"
        description = "Deletes stale $component Runtime validation evidence before package verification."
        delete(
            validationPhaseRoot,
            importedNativeEvidenceFile,
            importedNativeTestReport,
            cAbiPackageEvidence.flatMap { it.evidenceFile },
        )
    }
    val verifyImportedPackageManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImported${targetTitle}RuntimePackageOutputManifest",
    ) {
        group = "verification"
        description = "Verifies the imported $component Runtime package manifest and complete tree."
        dependsOn(invalidateValidationOutputs)
        product.set("runtime")
        this.component.set(component)
        phase.set("package")
        this.target.set(component)
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedPackage)
        stageRoot.set(importedPackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val packagePrerequisite: Any = if (importedRuntimePackageStage.isPresent) {
        verifyImportedPackageManifest
    } else {
        tasks.named("write${targetTitle}RuntimePackageOutputManifest")
    }
    cAbiPackageEvidence.configure {
        dependsOn(invalidateValidationOutputs, packagePrerequisite)
        packageFile.set(validationPackageRoot.zip(desktopRuntimeCompatibilityVersion) { root, version ->
            root.file("outputs/c-abi/${crossLanguageCAbiArchiveFileName(version, distribution.target)}")
        })
    }
    val importedNativeEvidence = tasks.register<ExecuteImportedNativeRuntimeEvidenceTask>(
        "executeImported${targetTitle}NativeRuntimeEvidence",
    ) {
        group = "verification"
        description = "Executes the $component native lifecycle from the exact staged Runtime package."
        dependsOn(invalidateValidationOutputs, packagePrerequisite)
        target.set(distribution.target)
        expectedCompatibilityVersion.set(desktopRuntimeCompatibilityVersion)
        candidateCommit.set(providers.gradleProperty("codexAgent.candidateCommit"))
        classifierArchive.set(validationPackageRoot.zip(desktopRuntimeCompatibilityVersion) { root, version ->
            root.file(
                "outputs/app-server/codex-agent-runtime-desktop-$version-${distribution.classifier}.zip",
            )
        })
        nativeTestExecutable.set(validationPackageRoot.map { root ->
            root.file(
                "outputs/validation-runner/" +
                    if (distribution.target == "mingwX64") "test.exe" else "test.kexe",
            )
        })
        distributionManifest.set(desktopManifestFile)
        evidenceFile.set(importedNativeEvidenceFile)
        testReport.set(importedNativeTestReport)
    }
    val stageValidation = tasks.register<Sync>("stage${targetTitle}RuntimeValidation") {
        group = "verification"
        description = "Stages the exact $component Runtime validation evidence once."
        dependsOn(cAbiPackageEvidence, importedNativeEvidence)
        into(validationPhaseOutputs)
        from(cAbiPackageEvidence.flatMap { it.evidenceFile }) { into("c-abi") }
        from(cAbiReviewedHeader) { into("c-abi-reference/include") }
        from(cAbiLicense) { into("c-abi-reference/legal") }
        from(cAbiNotice) { into("c-abi-reference/legal") }
        from(cAbiExportPolicy(distribution.target)) { into("c-abi-reference/export-policy") }
        from(cAbiConsumerSources) { into("c-abi-reference/consumer") }
        from(importedNativeEvidence.flatMap { it.evidenceFile }) { into("native") }
        from(importedNativeEvidence.flatMap { it.testReport }) { into("native") }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    tasks.register<WriteProductOutputManifestTask>("write${targetTitle}RuntimeValidationOutputManifest") {
        group = "verification"
        description = "Writes and verifies the exact $component Runtime validation manifest."
        dependsOn(stageValidation)
        product.set("runtime")
        this.component.set(component)
        phase.set("validation")
        this.target.set(component)
        productVersion.set(project.version.toString())
        outputRoots.set(mapOf(
            "c-abi" to "outputs/c-abi",
            "c-abi-reference" to "outputs/c-abi-reference",
            "native" to "outputs/native",
        ))
        outputsDirectory.set(validationPhaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(validationPhaseRoot)
        manifestFile.set(validationPhaseRoot.map { it.file("output-manifest.json") })
    }
}

val jvmValidationTarget = providers.provider {
    checkNotNull(hostTarget) { "JVM Runtime validation requires a supported desktop host" }
}
val jvmValidationComponent = jvmValidationTarget.map { target ->
    crossLanguageCAbiTargetSpecs.getValue(target).classifier.removePrefix("c-abi-")
}
val jvmValidationDistribution = jvmValidationTarget.map { target ->
    desktopManifest.distributions.single { it.target == target }
}
val importedJvmPackageSnapshotRoot = layout.buildDirectory.dir(
    cAbiCandidateTree.map { "imported-runtime-package-stages/$it/jvm" },
)
val snapshotImportedJvmRuntimePackage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedJvmRuntimePackageStage",
) {
    sourceDirectory.set(layout.dir(importedRuntimePackageStage))
    outputDirectory.set(importedJvmPackageSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val importedJvmNativePackageSnapshotRoot = layout.buildDirectory.dir(
    cAbiCandidateTree.zip(jvmValidationComponent) { tree, component ->
        "imported-runtime-native-package-stages/$tree/jvm/$component"
    },
)
val snapshotImportedJvmNativeRuntimePackage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedJvmNativeRuntimePackageStage",
) {
    sourceDirectory.set(layout.dir(importedRuntimeNativePackageStage))
    outputDirectory.set(importedJvmNativePackageSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val jvmValidationPackageRoot = if (importedRuntimePackageStage.isPresent) {
    importedJvmPackageSnapshotRoot
} else {
    layout.buildDirectory.dir("product-stage/runtime/jvm/package")
}
val jvmValidationNativePackageRoot = if (importedRuntimeNativePackageStage.isPresent) {
    importedJvmNativePackageSnapshotRoot
} else {
    layout.buildDirectory.dir(jvmValidationComponent.map { "product-stage/runtime/$it/package" })
}
val invalidateJvmRuntimeValidationOutputs = tasks.register<Delete>("invalidateJvmRuntimeValidationOutputs") {
    group = "verification"
    delete(
        layout.buildDirectory.dir("product-stage/runtime/jvm/validation"),
        layout.buildDirectory.dir("reports/imported-jvm-runtime-evidence"),
    )
}
val verifyImportedJvmRuntimePackageOutputManifest = tasks.register<VerifyImportedProductOutputManifestTask>(
    "verifyImportedJvmRuntimePackageOutputManifest",
) {
    dependsOn(invalidateJvmRuntimeValidationOutputs)
    product.set("runtime")
    component.set("jvm")
    phase.set("package")
    target.set("jvm")
    productVersion.set(project.version.toString())
    dependsOn(snapshotImportedJvmRuntimePackage)
    stageRoot.set(importedJvmPackageSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val verifyImportedJvmValidationNativePackageOutputManifest =
    tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImportedJvmValidationNativePackageOutputManifest",
    ) {
        dependsOn(invalidateJvmRuntimeValidationOutputs)
        product.set("runtime")
        component.set(jvmValidationComponent)
        phase.set("package")
        target.set(jvmValidationComponent)
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedJvmNativeRuntimePackage)
        stageRoot.set(importedJvmNativePackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
val jvmPackagePrerequisite: Any = if (importedRuntimePackageStage.isPresent) {
    verifyImportedJvmRuntimePackageOutputManifest
} else {
    tasks.named("writeJvmRuntimePackageOutputManifest")
}
val jvmNativePackagePrerequisite: Any = if (importedRuntimeNativePackageStage.isPresent) {
    verifyImportedJvmValidationNativePackageOutputManifest
} else {
    providers.provider {
        "write${jvmValidationTarget.get().replaceFirstChar(Char::uppercase)}RuntimePackageOutputManifest"
    }
}
val importedJvmRuntimeEvidence = tasks.register<RecordJvmRuntimeEvidenceTask>(
    "executeImportedJvmRuntimeEvidence",
) {
    group = "verification"
    description = "Executes JVM lifecycle evidence from exact staged JVM and native Runtime packages."
    dependsOn(invalidateJvmRuntimeValidationOutputs, jvmPackagePrerequisite, jvmNativePackagePrerequisite)
    candidateCommit.set(providers.gradleProperty("codexAgent.candidateCommit"))
    target.set(jvmValidationTarget)
    runnerOs.set(providers.environmentVariable("RUNNER_OS").orElse(
        jvmValidationTarget.map { desktopRuntimeEvidenceTargets.getValue(it).runnerOs },
    ))
    runnerArch.set(providers.environmentVariable("RUNNER_ARCH").orElse(
        jvmValidationTarget.map { desktopRuntimeEvidenceTargets.getValue(it).runnerArch },
    ))
    javaExecutable.set(providers.gradleProperty("codexAgent.javaExecutable").orElse("java"))
    testTask.set(IMPORTED_JVM_RUNTIME_EVIDENCE_TASK)
    distributionManifest.set(desktopManifestFile)
    classifierArchive.set(
        jvmValidationNativePackageRoot.zip(desktopRuntimeCompatibilityVersion) { root, version ->
            val distribution = jvmValidationDistribution.get()
            root.file(
                "outputs/app-server/codex-agent-runtime-desktop-$version-${distribution.classifier}.zip",
            )
        },
    )
    compiledJvmTestRuntime.set(jvmValidationPackageRoot.map { root ->
        root.file("outputs/validation-runner/$JVM_RUNTIME_RUNNER_ARCHIVE")
    })
    evidenceFile.set(layout.buildDirectory.file(jvmValidationTarget.map { target ->
        "reports/imported-jvm-runtime-evidence/${jvmRuntimeEvidenceFileName(target)}"
    }))
}
val jvmRuntimeValidationPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/jvm/validation")
val jvmRuntimeValidationOutputs = jvmRuntimeValidationPhaseRoot.map { it.dir("outputs") }
val stageJvmRuntimeValidation = tasks.register<Sync>("stageJvmRuntimeValidation") {
    group = "verification"
    dependsOn(importedJvmRuntimeEvidence)
    into(jvmRuntimeValidationOutputs)
    from(importedJvmRuntimeEvidence.flatMap { it.evidenceFile }) { into("jvm-evidence") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeJvmRuntimeValidationOutputManifest") {
    group = "verification"
    dependsOn(stageJvmRuntimeValidation)
    product.set("runtime")
    component.set("jvm")
    phase.set("validation")
    target.set(jvmValidationComponent)
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf("jvm-evidence" to "outputs/jvm-evidence"))
    outputsDirectory.set(jvmRuntimeValidationOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(jvmRuntimeValidationPhaseRoot)
    manifestFile.set(jvmRuntimeValidationPhaseRoot.map { it.file("output-manifest.json") })
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
