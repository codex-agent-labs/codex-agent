import com.vanniktech.maven.publish.JavadocJar
import com.vanniktech.maven.publish.KotlinMultiplatform
import com.vanniktech.maven.publish.SourcesJar
import java.io.File
import java.util.zip.ZipFile
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.bundling.Zip
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsEnvSpec

plugins {
    alias(libs.plugins.kotlin.multiplatform)
    alias(libs.plugins.maven.publish)
    id("codexagent.desktop-runtime")
}

val codexAgentRepositoryUrl = rootProject.extra["codexAgent.repositoryUrl"].toString()
val repositoryRootFile = rootProject.extra["codexAgent.repositoryRoot"] as File
val productTooling = layout.dir(providers.provider { repositoryRootFile.resolve("ci/products") })
val repositoryRootDirectory = layout.dir(providers.provider { repositoryRootFile })
val runtimeProductTooling = files(productTooling)
val runtimeProductVersion = providers.provider { project.version.toString() }
val importedRuntimeValidationHandoff =
    providers.gradleProperty("codexAgent.runtimeValidationHandoff").map(::file)
val importedRuntimeMavenRepository =
    providers.gradleProperty("codexAgent.runtimeMavenRepository").map(::file)

kotlin {
    explicitApi()
    sourceSets {
        commonMain.dependencies {
            api("io.github.codex-agent-labs:codex-agent-core:${providers.gradleProperty("codexAgent.contractVersion").get()}")
            implementation(libs.kotlinx.coroutines.core)
            implementation(libs.okio)
        }
        commonTest.dependencies {
            implementation(kotlin("test"))
            implementation(libs.kotlinx.coroutines.test)
        }
        nativeTest.dependencies { implementation(kotlin("test")) }
        jvmTest.dependencies { implementation(kotlin("test")) }
        jsTest.dependencies { implementation(kotlin("test")) }
        wasmJsTest.dependencies { implementation(kotlin("test")) }
    }
}

rootProject.extensions.configure<NodeJsEnvSpec> { download.set(false) }
extensions.configure<NodeJsEnvSpec> { download.set(false) }
rootProject.extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }
extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }

val packageNodeRuntimeEvidenceRunner = tasks.register<Zip>(
    "packageNodeRuntimeEvidenceRunner",
) {
    group = "distribution"
    description = "Packages the compiled standalone Node runtime evidence runner."
    dependsOn("jsProductionExecutableCompileSync")
    from(layout.buildDirectory.dir("compileSync/js/main/productionExecutable/kotlin")) {
        include("*.js")
    }
    archiveFileName.set("codex-agent-node-runtime-evidence-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    entryCompression = ZipEntryCompression.STORED
    doLast {
        ZipFile(archiveFile.get().asFile).use { zip ->
            val members = zip.entries().asSequence().toList()
            check(members.isNotEmpty() && members.none { it.isDirectory } &&
                members.map { it.name }.toSet().size == members.size &&
                members.all { it.name == File(it.name).name && it.name.endsWith(".js") && it.size > 0 } &&
                members.any { it.name == "codex-agent-codex-agent-runtime-desktop.js" }) {
                "Node evidence runner package has an incomplete or unsafe CommonJS module set"
            }
        }
    }
}

val nodeWasmRunnerBaseName = "codex-agent-codex-agent-runtime-desktop"
val nodeWasmRunnerMembers = setOf(
    "$nodeWasmRunnerBaseName.mjs",
    "$nodeWasmRunnerBaseName.uninstantiated.mjs",
    "$nodeWasmRunnerBaseName.wasm",
    "custom-formatters.js",
)
val packageNodeWasmRuntimeEvidenceRunner = tasks.register<Zip>(
    "packageNodeWasmRuntimeEvidenceRunner",
) {
    group = "distribution"
    description = "Packages the unoptimized standalone Kotlin/Wasm Node evidence runner."
    dependsOn("wasmJsDevelopmentExecutableCompileSync")
    from(layout.buildDirectory.dir("compileSync/wasmJs/main/developmentExecutable/kotlin")) {
        include(nodeWasmRunnerMembers)
    }
    archiveFileName.set("codex-agent-node-wasm-runtime-evidence-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    entryCompression = ZipEntryCompression.STORED
    doLast {
        ZipFile(archiveFile.get().asFile).use { zip ->
            val members = zip.entries().asSequence().toList()
            val expectedMembers = setOf(
                "codex-agent-codex-agent-runtime-desktop.mjs",
                "codex-agent-codex-agent-runtime-desktop.uninstantiated.mjs",
                "codex-agent-codex-agent-runtime-desktop.wasm",
                "custom-formatters.js",
            )
            check(
                members.none { it.isDirectory } &&
                    members.map { it.name }.toSet() == expectedMembers &&
                    members.all { it.name == File(it.name).name && it.size > 0 }
            ) { "Node Wasm evidence runner package has an incomplete or unsafe module set" }
        }
    }
}

val stageNodeBindingValidationRunner = tasks.register<StageNodeBindingValidationRunnerTask>(
    "stageNodeBindingValidationRunner",
) {
    dependsOn(
        "jsTestTestDevelopmentExecutableCompileSync",
        rootProject.tasks.named("kotlinNpmInstall"),
        rootProject.tasks.named("kotlinStorePackageLock"),
    )
    compiledProgram.set(layout.buildDirectory.dir("compileSync/js/test/testDevelopmentExecutable/kotlin"))
    nodeModules.set(rootProject.layout.buildDirectory.dir("js/node_modules"))
    npmLock.set(rootProject.layout.projectDirectory.file("gradle/kotlin-js-store/package-lock.json"))
    outputDirectory.set(layout.buildDirectory.dir("node-binding-validation-runner"))
}
val packageNodeBindingValidationRunner = tasks.register<Zip>("packageNodeBindingValidationRunner") {
    dependsOn(stageNodeBindingValidationRunner)
    from(stageNodeBindingValidationRunner.flatMap { it.outputDirectory })
    archiveFileName.set("codex-agent-node-binding-validation-runner.zip")
    destinationDirectory.set(layout.buildDirectory.dir("distributions"))
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
    includeEmptyDirs = false
    entryCompression = ZipEntryCompression.STORED
    filePermissions { unix("0644") }
}

val nodeJsRuntimeBinaryPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/node-js/binary")
val nodeJsRuntimeBinaryOutputs = nodeJsRuntimeBinaryPhaseRoot.map { it.dir("outputs") }
val stageNodeJsRuntimeBinaryOutputs = tasks.register<Sync>("stageNodeJsRuntimeBinaryOutputs") {
    group = "distribution"
    description = "Stages the exact raw Node JS Runtime binary outputs once."
    dependsOn("jsProductionExecutableCompileSync", packageNodeRuntimeEvidenceRunner, packageNodeBindingValidationRunner)
    into(nodeJsRuntimeBinaryOutputs)
    from(layout.buildDirectory.dir("compileSync/js/main/productionExecutable/kotlin")) {
        include("*.js", "*.js.map", "*.d.ts")
        into("adapter")
    }
    from(packageNodeRuntimeEvidenceRunner.flatMap { it.archiveFile }) { into("validation-runner") }
    from(packageNodeBindingValidationRunner.flatMap { it.archiveFile }) { into("binding-test-runner") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val writeNodeJsRuntimeBinaryOutputManifest =
    registerRuntimeOutputManifest(
        "writeNodeJsRuntimeBinaryOutputManifest",
        stageNodeJsRuntimeBinaryOutputs,
        providers.provider { "node-js" },
        "binary",
        providers.provider { "node-js" },
        runtimeProductVersion,
        mapOf(
            "adapter" to "outputs/adapter",
            "validation-runner" to "outputs/validation-runner",
            "binding-test-runner" to "outputs/binding-test-runner",
        ),
        nodeJsRuntimeBinaryOutputs,
        nodeJsRuntimeBinaryPhaseRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).also { task -> task.configure {
    group = "distribution"
    description = "Writes and verifies the exact raw Node JS Runtime binary manifest."
} }

val nodeWasmRuntimeBinaryPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/node-wasm/binary")
val nodeWasmRuntimeBinaryOutputs = nodeWasmRuntimeBinaryPhaseRoot.map { it.dir("outputs") }
val stageNodeWasmRuntimeBinaryOutputs = tasks.register<Sync>("stageNodeWasmRuntimeBinaryOutputs") {
    group = "distribution"
    description = "Stages the exact raw Node Wasm Runtime binary outputs once."
    dependsOn("wasmJsDevelopmentExecutableCompileSync", packageNodeWasmRuntimeEvidenceRunner)
    into(nodeWasmRuntimeBinaryOutputs)
    from(layout.buildDirectory.dir("compileSync/wasmJs/main/developmentExecutable/kotlin")) {
        include(nodeWasmRunnerMembers)
        into("adapter")
    }
    from(packageNodeWasmRuntimeEvidenceRunner.flatMap { it.archiveFile }) { into("validation-runner") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val writeNodeWasmRuntimeBinaryOutputManifest =
    registerRuntimeOutputManifest(
        "writeNodeWasmRuntimeBinaryOutputManifest",
        stageNodeWasmRuntimeBinaryOutputs,
        providers.provider { "node-wasm" },
        "binary",
        providers.provider { "node-wasm" },
        runtimeProductVersion,
        mapOf(
            "adapter" to "outputs/adapter",
            "validation-runner" to "outputs/validation-runner",
        ),
        nodeWasmRuntimeBinaryOutputs,
        nodeWasmRuntimeBinaryPhaseRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).also { task -> task.configure {
    group = "distribution"
    description = "Writes and verifies the exact raw Node Wasm Runtime binary manifest."
} }

val importedNodeRuntimeBinaryStage = providers.gradleProperty("codexAgent.runtimeBinaryStage").map(::file)
val nodeCandidateTree = providers.gradleProperty("codexAgent.candidateTree")

fun registerImportedNodeBinarySnapshot(component: String, title: String) =
    layout.buildDirectory.dir(nodeCandidateTree.map { "imported-runtime-binary-stages/$it/$component" }).let { root ->
        root to registerRuntimeStageSnapshot(
            "snapshotImported${title}RuntimeBinaryStage",
            layout.dir(importedNodeRuntimeBinaryStage),
            root,
            runtimeProductTooling,
            repositoryRootFile,
        )
    }

val (importedNodeJsRuntimeBinarySnapshotRoot, snapshotImportedNodeJsRuntimeBinaryStage) =
    registerImportedNodeBinarySnapshot("node-js", "NodeJs")

val verifyImportedNodeJsRuntimeBinaryOutputManifest =
    registerRuntimeOutputVerification(
        "verifyImportedNodeJsRuntimeBinaryOutputManifest",
        snapshotImportedNodeJsRuntimeBinaryStage,
        providers.provider { "node-js" },
        "binary",
        providers.provider { "node-js" },
        runtimeProductVersion,
        importedNodeJsRuntimeBinarySnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).also { task -> task.configure {
        group = "verification"
        description = "Verifies the imported raw Node JS Runtime binary manifest and complete tree."
    } }
val nodeJsPackageInput = if (importedNodeRuntimeBinaryStage.isPresent) {
    importedNodeJsRuntimeBinarySnapshotRoot
} else {
    nodeJsRuntimeBinaryPhaseRoot
}
val nodeJsRuntimePackagePhaseRoot = layout.buildDirectory.dir("product-stage/runtime/node-js/package")
val nodeJsRuntimePackageOutputs = nodeJsRuntimePackagePhaseRoot.map { it.dir("outputs") }
val stageNodeJsRuntimePackage = tasks.register<Sync>("stageNodeJsRuntimePackage") {
    group = "distribution"
    description = "Stages the exact Node JS Runtime package from a verified binary stage."
    dependsOn(if (importedNodeRuntimeBinaryStage.isPresent) {
        verifyImportedNodeJsRuntimeBinaryOutputManifest
    } else {
        writeNodeJsRuntimeBinaryOutputManifest
    })
    into(nodeJsRuntimePackageOutputs)
    from(nodeJsPackageInput.map { it.dir("outputs/adapter") }) { into("adapter") }
    from(nodeJsPackageInput.map { it.dir("outputs/validation-runner") }) {
        into("validation-runner")
    }
    from(nodeJsPackageInput.map { it.dir("outputs/binding-test-runner") }) {
        into("binding-test-runner")
    }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
registerRuntimeOutputManifest(
    "writeNodeJsRuntimePackageOutputManifest",
    stageNodeJsRuntimePackage,
    providers.provider { "node-js" },
    "package",
    providers.provider { "node-js" },
    runtimeProductVersion,
    mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
        "binding-test-runner" to "outputs/binding-test-runner",
    ),
    nodeJsRuntimePackageOutputs,
    nodeJsRuntimePackagePhaseRoot,
    runtimeProductTooling,
    repositoryRootFile,
).configure {
    group = "distribution"
    description = "Writes and verifies the exact Node JS Runtime package manifest."
}

val (importedNodeWasmRuntimeBinarySnapshotRoot, snapshotImportedNodeWasmRuntimeBinaryStage) =
    registerImportedNodeBinarySnapshot("node-wasm", "NodeWasm")
val verifyImportedNodeWasmRuntimeBinaryOutputManifest =
    registerRuntimeOutputVerification(
        "verifyImportedNodeWasmRuntimeBinaryOutputManifest",
        snapshotImportedNodeWasmRuntimeBinaryStage,
        providers.provider { "node-wasm" },
        "binary",
        providers.provider { "node-wasm" },
        runtimeProductVersion,
        importedNodeWasmRuntimeBinarySnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).also { task -> task.configure {
        group = "verification"
        description = "Verifies the imported raw Node Wasm Runtime binary manifest and complete tree."
    } }
val nodeWasmPackageInput = if (importedNodeRuntimeBinaryStage.isPresent) {
    importedNodeWasmRuntimeBinarySnapshotRoot
} else {
    nodeWasmRuntimeBinaryPhaseRoot
}
val nodeWasmRuntimePackagePhaseRoot = layout.buildDirectory.dir("product-stage/runtime/node-wasm/package")
val nodeWasmRuntimePackageOutputs = nodeWasmRuntimePackagePhaseRoot.map { it.dir("outputs") }
val stageNodeWasmRuntimePackage = tasks.register<Sync>("stageNodeWasmRuntimePackage") {
    group = "distribution"
    description = "Stages the exact Node Wasm Runtime package from a verified binary stage."
    dependsOn(if (importedNodeRuntimeBinaryStage.isPresent) {
        verifyImportedNodeWasmRuntimeBinaryOutputManifest
    } else {
        writeNodeWasmRuntimeBinaryOutputManifest
    })
    into(nodeWasmRuntimePackageOutputs)
    from(nodeWasmPackageInput.map { it.dir("outputs/adapter") }) { into("adapter") }
    from(nodeWasmPackageInput.map { it.dir("outputs/validation-runner") }) {
        into("validation-runner")
    }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
registerRuntimeOutputManifest(
    "writeNodeWasmRuntimePackageOutputManifest",
    stageNodeWasmRuntimePackage,
    providers.provider { "node-wasm" },
    "package",
    providers.provider { "node-wasm" },
    runtimeProductVersion,
    mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ),
    nodeWasmRuntimePackageOutputs,
    nodeWasmRuntimePackagePhaseRoot,
    runtimeProductTooling,
    repositoryRootFile,
).configure {
    group = "distribution"
    description = "Writes and verifies the exact Node Wasm Runtime package manifest."
}

val importedNodeRuntimePackageStage = providers.gradleProperty("codexAgent.runtimePackageStage").map(::file)
val importedNodeRuntimeNativePackageStage =
    providers.gradleProperty("codexAgent.runtimeNativePackageStage").map(::file)
val nodeCAbiCatalog = readRuntimeCAbiCatalog(
    providers.of(RuntimeCAbiCatalogValueSource::class.java) {}.get(),
)
val nodeValidationTarget = checkNotNull(nodeCAbiCatalog.hostTarget(
    System.getProperty("os.name"),
    System.getProperty("os.arch"),
)) { "Node Runtime validation requires a supported desktop host" }
val nodeValidationTargetTitle = nodeValidationTarget.replaceFirstChar(Char::uppercase)
val nodeValidationComponent =
    nodeCAbiCatalog.targets.getValue(nodeValidationTarget).classifier.removePrefix("c-abi-")
if (providers.gradleProperty("codexAgent.product").orNull == "runtime" &&
    providers.gradleProperty("codexAgent.component").orNull in setOf("node-js", "node-wasm") &&
    providers.gradleProperty("codexAgent.phase").orNull == "validation" &&
    providers.gradleProperty("codexAgent.target").orNull != "node-js-binding") {
    check(providers.gradleProperty("codexAgent.target").get() == nodeValidationComponent) {
        "Node Runtime validation target must match the actual host: $nodeValidationComponent"
    }
}
val nodeValidationManifestFile = layout.projectDirectory.file("codex-app-server-distributions.json")
val nodeValidationDistribution = readDesktopCodexManifest(nodeValidationManifestFile.asFile)
    .distributions.single { it.target == nodeValidationTarget }
@Suppress("UNCHECKED_CAST")
val nodeValidationCompatibilityVersion =
    project.extra["codexAgent.runtimeCompatibilityVersion"] as Provider<String>
fun registerNodeRuntimeValidation(
    component: String,
    runnerArchiveName: String,
    localPackageRoot: Provider<Directory>,
    localPackageTaskName: String,
    evidenceTaskPrefix: String,
) {
    val title = component.split('-').joinToString("") { it.replaceFirstChar(Char::uppercase) }
    val importedPackageSnapshotRoot = layout.buildDirectory.dir(
        nodeCandidateTree.map { "imported-runtime-package-stages/$it/$component/$nodeValidationComponent" },
    )
    val importedNodeNativePackageSnapshotRoot = layout.buildDirectory.dir(
        nodeCandidateTree.map {
            "imported-runtime-native-package-stages/$it/$component/$nodeValidationComponent"
        },
    )
    val snapshotImportedNodeNativeRuntimePackage = registerRuntimeStageSnapshot(
        "snapshotImported${title}NativeRuntimePackageStage",
        layout.dir(importedNodeRuntimeNativePackageStage),
        importedNodeNativePackageSnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    )
    val nodeValidationNativePackageRoot = if (importedNodeRuntimeNativePackageStage.isPresent) {
        importedNodeNativePackageSnapshotRoot
    } else {
        layout.buildDirectory.dir("product-stage/runtime/$nodeValidationComponent/package")
    }
    val snapshotImportedPackage = registerRuntimeStageSnapshot(
        "snapshotImported${title}RuntimePackageStage",
        layout.dir(importedNodeRuntimePackageStage),
        importedPackageSnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    )
    val packageRoot = if (importedNodeRuntimePackageStage.isPresent) {
        importedPackageSnapshotRoot
    } else {
        localPackageRoot
    }
    val phaseRoot = layout.buildDirectory.dir(
        "product-stage/runtime/$component/validation/$nodeValidationComponent",
    )
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val evidenceTask = tasks.named<RecordNodeRuntimeEvidenceTask>(
        "$evidenceTaskPrefix${nodeValidationTargetTitle}Test",
    )
    val invalidate = tasks.register<Delete>("invalidate${title}RuntimeValidationOutputs") {
        group = "verification"
        delete(
            phaseRoot,
            importedPackageSnapshotRoot,
            importedNodeNativePackageSnapshotRoot,
            evidenceTask.flatMap { it.evidenceFile },
            evidenceTask.flatMap { it.testReport },
            evidenceTask.flatMap { it.executionFile },
        )
    }
    snapshotImportedPackage.configure { dependsOn(invalidate) }
    snapshotImportedNodeNativeRuntimePackage.configure { dependsOn(invalidate) }
    val verifyPackage = registerRuntimeOutputVerification(
        "verifyImported${title}RuntimePackageOutputManifest",
        listOf(invalidate, snapshotImportedPackage),
        providers.provider { component },
        "package",
        providers.provider { component },
        providers.gradleProperty("codexAgent.runtimePackageVersion"),
        importedPackageSnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    )
    val verifyNativePackage = registerRuntimeOutputVerification(
        "verifyImported${title}ValidationNativePackageOutputManifest",
        listOf(invalidate, snapshotImportedNodeNativeRuntimePackage),
        providers.provider { nodeValidationComponent },
        "package",
        providers.provider { nodeValidationComponent },
        providers.gradleProperty("codexAgent.runtimeNativePackageVersion"),
        importedNodeNativePackageSnapshotRoot,
        runtimeProductTooling,
        repositoryRootFile,
    )
    val packagePrerequisite: Any = if (importedNodeRuntimePackageStage.isPresent) {
        verifyPackage
    } else {
        localPackageTaskName
    }
    val nativePackagePrerequisite: Any = if (importedNodeRuntimeNativePackageStage.isPresent) {
        verifyNativePackage
    } else {
        "write${nodeValidationTargetTitle}RuntimePackageOutputManifest"
    }
    val nativePackageCompatibilityVersion = if (importedNodeRuntimeNativePackageStage.isPresent) {
        providers.gradleProperty("codexAgent.runtimeNativePackageVersion").map(::runtimeCompatibilityVersion)
    } else {
        nodeValidationCompatibilityVersion
    }
    val nativePackageClassifier = nodeValidationDistribution.classifier
    evidenceTask.configure {
        dependsOn(invalidate, packagePrerequisite, nativePackagePrerequisite)
        classifierArchive.set(
            nodeValidationNativePackageRoot.zip(nativePackageCompatibilityVersion) { root, version ->
                root.file(
                    "outputs/app-server/codex-agent-runtime-desktop-$version-" +
                        "$nativePackageClassifier.zip",
                )
            },
        )
        compiledNodeTestRuntime.set(packageRoot.map { root ->
            root.file("outputs/validation-runner/$runnerArchiveName")
        })
    }
    val stage = tasks.register<Sync>("stage${title}RuntimeValidation") {
        group = "verification"
        dependsOn(evidenceTask)
        into(phaseOutputs)
        from(evidenceTask.flatMap { it.evidenceFile }) { into("node-evidence") }
        from(evidenceTask.flatMap { it.testReport }) { into("test-report") }
        from(evidenceTask.flatMap { it.executionFile }) { into("execution") }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    registerRuntimeOutputManifest(
        "write${title}RuntimeValidationOutputManifest",
        stage,
        providers.provider { component },
        "validation",
        providers.provider { nodeValidationComponent },
        runtimeProductVersion,
        mapOf(
            "node-evidence" to "outputs/node-evidence",
            "test-report" to "outputs/test-report",
            "execution" to "outputs/execution",
        ),
        phaseOutputs,
        phaseRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).configure {
        group = "verification"
    }
}

registerNodeRuntimeValidation(
    "node-js",
    "codex-agent-node-runtime-evidence-runner.zip",
    nodeJsRuntimePackagePhaseRoot,
    "writeNodeJsRuntimePackageOutputManifest",
    "nodeRuntime",
)
registerNodeRuntimeValidation(
    "node-wasm",
    "codex-agent-node-wasm-runtime-evidence-runner.zip",
    nodeWasmRuntimePackagePhaseRoot,
    "writeNodeWasmRuntimePackageOutputManifest",
    "nodeWasmRuntime",
)

val nodeJsBindingValidationRoot =
    layout.buildDirectory.dir("product-stage/runtime/node-js/validation/node-js-binding")
val nodeJsBindingValidationOutputs = nodeJsBindingValidationRoot.map { it.dir("outputs") }
val importedNodeBindingPackageRoot = layout.buildDirectory.dir(
    nodeCandidateTree.map { "imported-runtime-package-stages/$it/node-js-binding" },
)
val invalidateNodeJsBindingValidation = tasks.register<Delete>("invalidateNodeJsBindingValidation") {
    delete(nodeJsBindingValidationRoot, importedNodeBindingPackageRoot)
    delete(layout.buildDirectory.dir("node-binding-validation-results"))
}
val snapshotNodeBindingPackage = registerRuntimeStageSnapshot(
    "snapshotNodeBindingRuntimePackage", layout.dir(importedNodeRuntimePackageStage),
    importedNodeBindingPackageRoot, runtimeProductTooling, repositoryRootFile,
).also { it.configure { dependsOn(invalidateNodeJsBindingValidation) } }
val verifyNodeBindingPackage = registerRuntimeOutputVerification(
    "verifyNodeBindingRuntimePackage", snapshotNodeBindingPackage,
    providers.provider { "node-js" }, "package", providers.provider { "node-js" },
    providers.gradleProperty("codexAgent.runtimePackageVersion"),
    importedNodeBindingPackageRoot, runtimeProductTooling, repositoryRootFile,
)
val executeNodeBindingValidation = tasks.register<ExecuteNodeBindingValidationTask>("executeNodeBindingValidation") {
    dependsOn(invalidateNodeJsBindingValidation)
    val packageRoot = if (importedNodeRuntimePackageStage.isPresent) {
        dependsOn(verifyNodeBindingPackage)
        importedNodeBindingPackageRoot
    } else {
        dependsOn("writeNodeJsRuntimePackageOutputManifest")
        nodeJsRuntimePackagePhaseRoot
    }
    runnerArchive.set(packageRoot.map {
        it.file("outputs/binding-test-runner/codex-agent-node-binding-validation-runner.zip")
    })
    nodeExecutable.set(providers.gradleProperty("codexAgent.nodeExecutable").orElse("node"))
    outputDirectory.set(layout.buildDirectory.dir("node-binding-validation-results"))
}
val stageNodeJsBindingValidation = tasks.register<Sync>("stageNodeJsBindingValidation") {
    group = "verification"
    description = "Stages the exact compiler-backed Node binding behavior evidence for SDK parity."
    dependsOn(executeNodeBindingValidation)
    into(nodeJsBindingValidationOutputs)
    from(executeNodeBindingValidation.flatMap { it.outputDirectory })
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
registerRuntimeOutputManifest(
    "writeNodeJsBindingValidationOutputManifest",
    stageNodeJsBindingValidation,
    providers.provider { "node-js" },
    "validation",
    providers.provider { "node-js-binding" },
    runtimeProductVersion,
    mapOf(
        "test-program" to "outputs/test-program",
        "test-report" to "outputs/test-report",
    ),
    nodeJsBindingValidationOutputs,
    nodeJsBindingValidationRoot,
    runtimeProductTooling,
    repositoryRootFile,
).configure {
    group = "verification"
    description = "Writes and verifies the exact Node binding validation handoff manifest."
}

val runtimeNativeMetadataComponents = linkedMapOf(
    "macos-arm64" to "MacosArm64",
    "macos-x64" to "MacosX64",
    "linux-arm64" to "LinuxArm64",
    "linux-x64" to "LinuxX64",
    "windows-x64" to "MingwX64",
)
runtimeNativeMetadataComponents.forEach { (component, title) ->
    val phaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/metadata")
    val outputsRoot = phaseRoot.map { it.dir("outputs") }
    val stage = tasks.register<ImportedRuntimeVariantTask>("stage${title}RuntimeMetadata") {
        group = "verification"
        description = "Produces the reusable $component variant from original imported phase evidence."
        fun imported(name: String) = layout.file(providers.gradleProperty("codexAgent.runtimeVariant$name").map(::file))
        this.component.set(component)
        identity.set(imported("Identity"))
        binaryReceipt.set(imported("BinaryReceipt"))
        packageReceipt.set(imported("PackageReceipt"))
        validationReceipt.set(imported("ValidationReceipt"))
        cAbiArchive.set(imported("CAbiArchive"))
        appServerArchive.set(imported("AppServerArchive"))
        validationEvidence.set(imported("ValidationEvidence"))
        distributionManifest.set(layout.projectDirectory.file("codex-app-server-distributions.json"))
        producerSources.from(runtimeProductTooling)
        repositoryRoot.set(repositoryRootDirectory)
        outputDirectory.set(outputsRoot)
        // No validation/compiler dependency: Python verifies the exact original
        // receipts, archive members and raw report before deriving product content.
    }
    registerRuntimeOutputManifest(
        "write${title}RuntimeMetadataOutputManifest",
        stage,
        providers.provider { component },
        "metadata",
        providers.provider { component },
        runtimeProductVersion,
        mapOf("runtime-variant" to "outputs"),
        outputsRoot,
        phaseRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).configure {
        group = "verification"
        description = "Writes the exact $component Runtime variant output manifest."
    }
}

val runtimeAdapterMetadataComponents = linkedMapOf(
    "jvm" to "Jvm",
    "node-js" to "NodeJs",
    "node-wasm" to "NodeWasm",
)
runtimeAdapterMetadataComponents.forEach { (component, title) ->
    val phaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/metadata")
    val outputsRoot = phaseRoot.map { it.dir("outputs") }
    val projection = layout.file(importedRuntimeValidationHandoff.map {
        it.resolve("projection.json")
    })
    val invalidate = tasks.register<Delete>("invalidate${title}RuntimeMetadataOutputs") {
        group = "verification"
        delete(phaseRoot)
    }
    val verifyInputs = tasks.register<ValidateRuntimeAdapterMetadataInputsTask>(
        "verify${title}RuntimeMetadataInputs",
    ) {
        group = "verification"
        description = "Verifies the authenticated $component projection and prebuilt Runtime Maven inputs."
        dependsOn(invalidate)
        this.component.set(component)
        validationHandoff.set(layout.dir(importedRuntimeValidationHandoff))
        this.projection.set(projection)
        mavenRepository.set(layout.dir(importedRuntimeMavenRepository))
    }
    val stage = tasks.register<Sync>("stage${title}RuntimeMetadata") {
        group = "verification"
        description = "Stages the authenticated $component projection and prebuilt Runtime Maven bytes."
        dependsOn(verifyInputs)
        into(outputsRoot)
        from(projection) {
            into("evidence")
            rename { "$component.json" }
        }
        from(layout.dir(importedRuntimeMavenRepository)) { into("maven") }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    registerRuntimeOutputManifest(
        "write${title}RuntimeMetadataOutputManifest",
        stage,
        providers.provider { component },
        "metadata",
        providers.provider { component },
        runtimeProductVersion,
        mapOf(
            "adapter-evidence" to "outputs/evidence",
            "maven" to "outputs/maven",
        ),
        outputsRoot,
        phaseRoot,
        runtimeProductTooling,
        repositoryRootFile,
    ).configure {
        group = "verification"
        description = "Writes the exact $component Runtime metadata handoff manifest."
    }
}

mavenPublishing {
    configure(
        KotlinMultiplatform(
            javadocJar = JavadocJar.Empty(),
            sourcesJar = SourcesJar.Sources(),
        ),
    )
    coordinates(project.group.toString(), "codex-agent-runtime-desktop", project.version.toString())
    if (
        providers.gradleProperty("signingInMemoryKey").isPresent ||
        providers.gradleProperty("signing.secretKeyRingFile").isPresent
    ) {
        signAllPublications()
    }
    pom {
        name.set("Codex Agent Runtime for Desktop")
        description.set("JVM, Native, and Node desktop process runtime for the Codex App Server.")
        inceptionYear.set("2026")
        url.set(codexAgentRepositoryUrl)
        licenses {
            license {
                name.set("GNU General Public License v3.0 or later")
                url.set("https://www.gnu.org/licenses/gpl-3.0.txt")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("ciurlaro")
                name.set("Cesare Iurlaro")
                url.set("https://github.com/ciurlaro")
            }
        }
        scm {
            url.set(codexAgentRepositoryUrl)
            connection.set("scm:git:$codexAgentRepositoryUrl.git")
            developerConnection.set("scm:git:ssh://git@github.com/${codexAgentRepositoryUrl.substringAfter("github.com/")}.git")
        }
    }
}

dependencyLocking {
    lockAllConfigurations()
}
