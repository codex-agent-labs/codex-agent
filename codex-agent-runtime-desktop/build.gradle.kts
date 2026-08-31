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

kotlin {
    explicitApi()
    sourceSets {
        commonMain.dependencies {
            api(project(":codex-agent-core"))
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

val nodeJsRuntimeBinaryPhaseRoot = layout.buildDirectory.dir("product-stage/runtime/node-js/binary")
val nodeJsRuntimeBinaryOutputs = nodeJsRuntimeBinaryPhaseRoot.map { it.dir("outputs") }
val stageNodeJsRuntimeBinaryOutputs = tasks.register<Sync>("stageNodeJsRuntimeBinaryOutputs") {
    group = "distribution"
    description = "Stages the exact raw Node JS Runtime binary outputs once."
    dependsOn("jsProductionExecutableCompileSync", packageNodeRuntimeEvidenceRunner)
    into(nodeJsRuntimeBinaryOutputs)
    from(layout.buildDirectory.dir("compileSync/js/main/productionExecutable/kotlin")) {
        include("*.js", "*.js.map", "*.d.ts")
        into("adapter")
    }
    from(packageNodeRuntimeEvidenceRunner.flatMap { it.archiveFile }) { into("validation-runner") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
val writeNodeJsRuntimeBinaryOutputManifest =
    tasks.register<WriteProductOutputManifestTask>("writeNodeJsRuntimeBinaryOutputManifest") {
    group = "distribution"
    description = "Writes and verifies the exact raw Node JS Runtime binary manifest."
    dependsOn(stageNodeJsRuntimeBinaryOutputs)
    product.set("runtime")
    component.set("node-js")
    phase.set("binary")
    target.set("node-js")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(nodeJsRuntimeBinaryOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(nodeJsRuntimeBinaryPhaseRoot)
    manifestFile.set(nodeJsRuntimeBinaryPhaseRoot.map { it.file("output-manifest.json") })
}

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
    tasks.register<WriteProductOutputManifestTask>("writeNodeWasmRuntimeBinaryOutputManifest") {
    group = "distribution"
    description = "Writes and verifies the exact raw Node Wasm Runtime binary manifest."
    dependsOn(stageNodeWasmRuntimeBinaryOutputs)
    product.set("runtime")
    component.set("node-wasm")
    phase.set("binary")
    target.set("node-wasm")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(nodeWasmRuntimeBinaryOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(nodeWasmRuntimeBinaryPhaseRoot)
    manifestFile.set(nodeWasmRuntimeBinaryPhaseRoot.map { it.file("output-manifest.json") })
}

val importedNodeRuntimeBinaryStage = providers.gradleProperty("codexAgent.runtimeBinaryStage").map(::file)
val nodeCandidateTree = providers.gradleProperty("codexAgent.candidateTree")

fun registerImportedNodeBinarySnapshot(component: String, title: String) =
    layout.buildDirectory.dir(nodeCandidateTree.map { "imported-runtime-binary-stages/$it/$component" }).let { root ->
        root to tasks.register<SnapshotImportedProductStageTask>(
            "snapshotImported${title}RuntimeBinaryStage",
        ) {
            sourceDirectory.set(layout.dir(importedNodeRuntimeBinaryStage))
            outputDirectory.set(root)
            producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
            repositoryRoot.set(rootProject.layout.projectDirectory)
        }
    }

val (importedNodeJsRuntimeBinarySnapshotRoot, snapshotImportedNodeJsRuntimeBinaryStage) =
    registerImportedNodeBinarySnapshot("node-js", "NodeJs")

val verifyImportedNodeJsRuntimeBinaryOutputManifest =
    tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImportedNodeJsRuntimeBinaryOutputManifest",
    ) {
        group = "verification"
        description = "Verifies the imported raw Node JS Runtime binary manifest and complete tree."
        product.set("runtime")
        component.set("node-js")
        phase.set("binary")
        target.set("node-js")
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedNodeJsRuntimeBinaryStage)
        stageRoot.set(importedNodeJsRuntimeBinarySnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
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
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeNodeJsRuntimePackageOutputManifest") {
    group = "distribution"
    description = "Writes and verifies the exact Node JS Runtime package manifest."
    dependsOn(stageNodeJsRuntimePackage)
    product.set("runtime")
    component.set("node-js")
    phase.set("package")
    target.set("node-js")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(nodeJsRuntimePackageOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(nodeJsRuntimePackagePhaseRoot)
    manifestFile.set(nodeJsRuntimePackagePhaseRoot.map { it.file("output-manifest.json") })
}

val (importedNodeWasmRuntimeBinarySnapshotRoot, snapshotImportedNodeWasmRuntimeBinaryStage) =
    registerImportedNodeBinarySnapshot("node-wasm", "NodeWasm")
val verifyImportedNodeWasmRuntimeBinaryOutputManifest =
    tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImportedNodeWasmRuntimeBinaryOutputManifest",
    ) {
        group = "verification"
        description = "Verifies the imported raw Node Wasm Runtime binary manifest and complete tree."
        product.set("runtime")
        component.set("node-wasm")
        phase.set("binary")
        target.set("node-wasm")
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedNodeWasmRuntimeBinaryStage)
        stageRoot.set(importedNodeWasmRuntimeBinarySnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
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
tasks.register<WriteProductOutputManifestTask>("writeNodeWasmRuntimePackageOutputManifest") {
    group = "distribution"
    description = "Writes and verifies the exact Node Wasm Runtime package manifest."
    dependsOn(stageNodeWasmRuntimePackage)
    product.set("runtime")
    component.set("node-wasm")
    phase.set("package")
    target.set("node-wasm")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "adapter" to "outputs/adapter",
        "validation-runner" to "outputs/validation-runner",
    ))
    outputsDirectory.set(nodeWasmRuntimePackageOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(nodeWasmRuntimePackagePhaseRoot)
    manifestFile.set(nodeWasmRuntimePackagePhaseRoot.map { it.file("output-manifest.json") })
}

val importedNodeRuntimePackageStage = providers.gradleProperty("codexAgent.runtimePackageStage").map(::file)
val importedNodeRuntimeNativePackageStage =
    providers.gradleProperty("codexAgent.runtimeNativePackageStage").map(::file)
val nodeValidationTarget = checkNotNull(crossLanguageCAbiHostTarget(
    System.getProperty("os.name"),
    System.getProperty("os.arch"),
)) { "Node Runtime validation requires a supported desktop host" }
val nodeValidationTargetTitle = nodeValidationTarget.replaceFirstChar(Char::uppercase)
val nodeValidationComponent =
    crossLanguageCAbiTargetSpecs.getValue(nodeValidationTarget).classifier.removePrefix("c-abi-")
val nodeValidationManifestFile = layout.projectDirectory.file("codex-app-server-distributions.json")
val nodeValidationDistribution = readDesktopCodexManifest(nodeValidationManifestFile.asFile)
    .distributions.single { it.target == nodeValidationTarget }
@Suppress("UNCHECKED_CAST")
val nodeValidationCompatibilityVersion =
    project.extra["codexAgent.runtimeCompatibilityVersion"] as Provider<String>
val nodeValidationSnapshotOwner = providers.gradleProperty("codexAgent.component")
    .map { component ->
        check(component == "node-js" || component == "node-wasm") {
            "Node Runtime validation component must be node-js or node-wasm"
        }
        component
    }
    .orElse("node")
val importedNodeNativePackageSnapshotRoot = layout.buildDirectory.dir(
    nodeCandidateTree.zip(nodeValidationSnapshotOwner) { tree, owner ->
        "imported-runtime-native-package-stages/$tree/$owner/$nodeValidationComponent"
    },
)
val snapshotImportedNodeNativeRuntimePackage = tasks.register<SnapshotImportedProductStageTask>(
    "snapshotImportedNodeNativeRuntimePackageStage",
) {
    sourceDirectory.set(layout.dir(importedNodeRuntimeNativePackageStage))
    outputDirectory.set(importedNodeNativePackageSnapshotRoot)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}
val nodeValidationNativePackageRoot = if (importedNodeRuntimeNativePackageStage.isPresent) {
    importedNodeNativePackageSnapshotRoot
} else {
    layout.buildDirectory.dir("product-stage/runtime/$nodeValidationComponent/package")
}

fun registerNodeRuntimeValidation(
    component: String,
    runnerArchiveName: String,
    localPackageRoot: Provider<Directory>,
    localPackageTaskName: String,
    evidenceTaskPrefix: String,
) {
    val title = component.split('-').joinToString("") { it.replaceFirstChar(Char::uppercase) }
    val importedPackageSnapshotRoot = layout.buildDirectory.dir(
        nodeCandidateTree.map { "imported-runtime-package-stages/$it/$component" },
    )
    val snapshotImportedPackage = tasks.register<SnapshotImportedProductStageTask>(
        "snapshotImported${title}RuntimePackageStage",
    ) {
        sourceDirectory.set(layout.dir(importedNodeRuntimePackageStage))
        outputDirectory.set(importedPackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val packageRoot = if (importedNodeRuntimePackageStage.isPresent) {
        importedPackageSnapshotRoot
    } else {
        localPackageRoot
    }
    val phaseRoot = layout.buildDirectory.dir("product-stage/runtime/$component/validation")
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val evidenceTask = tasks.named<RecordNodeRuntimeEvidenceTask>(
        "$evidenceTaskPrefix${nodeValidationTargetTitle}Test",
    )
    val invalidate = tasks.register<Delete>("invalidate${title}RuntimeValidationOutputs") {
        group = "verification"
        delete(
            phaseRoot,
            evidenceTask.flatMap { it.evidenceFile },
            evidenceTask.flatMap { it.testReport },
        )
    }
    val verifyPackage = tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImported${title}RuntimePackageOutputManifest",
    ) {
        dependsOn(invalidate)
        product.set("runtime")
        this.component.set(component)
        phase.set("package")
        target.set(component)
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedPackage)
        stageRoot.set(importedPackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verifyNativePackage = tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImported${title}ValidationNativePackageOutputManifest",
    ) {
        dependsOn(invalidate)
        product.set("runtime")
        this.component.set(nodeValidationComponent)
        phase.set("package")
        target.set(nodeValidationComponent)
        productVersion.set(project.version.toString())
        dependsOn(snapshotImportedNodeNativeRuntimePackage)
        stageRoot.set(importedNodeNativePackageSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
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
    evidenceTask.configure {
        dependsOn(invalidate, packagePrerequisite, nativePackagePrerequisite)
        classifierArchive.set(
            nodeValidationNativePackageRoot.zip(nodeValidationCompatibilityVersion) { root, version ->
                root.file(
                    "outputs/app-server/codex-agent-runtime-desktop-$version-" +
                        "${nodeValidationDistribution.classifier}.zip",
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
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    tasks.register<WriteProductOutputManifestTask>("write${title}RuntimeValidationOutputManifest") {
        group = "verification"
        dependsOn(stage)
        product.set("runtime")
        this.component.set(component)
        phase.set("validation")
        target.set(nodeValidationComponent)
        productVersion.set(project.version.toString())
        outputRoots.set(mapOf(
            "node-evidence" to "outputs/node-evidence",
            "test-report" to "outputs/test-report",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
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
    layout.buildDirectory.dir("product-stage/runtime/node-js-binding/validation")
val nodeJsBindingValidationOutputs = nodeJsBindingValidationRoot.map { it.dir("outputs") }
val stageNodeJsBindingValidation = tasks.register<Sync>("stageNodeJsBindingValidation") {
    group = "verification"
    description = "Stages the exact compiler-backed Node binding behavior evidence for SDK parity."
    dependsOn("jsNodeTest")
    into(nodeJsBindingValidationOutputs)
    from(layout.buildDirectory.dir("compileSync/js/test/testDevelopmentExecutable/kotlin")) {
        into("test-program")
    }
    from(layout.buildDirectory.file(
        "test-results/jsNodeTest/TEST-jsNodeTest.CodexNodeApiTest.xml",
    )) { into("test-report") }
    includeEmptyDirs = false
    duplicatesStrategy = DuplicatesStrategy.FAIL
}
tasks.register<WriteProductOutputManifestTask>("writeNodeJsBindingValidationOutputManifest") {
    group = "verification"
    description = "Writes and verifies the exact Node binding validation handoff manifest."
    dependsOn(stageNodeJsBindingValidation)
    product.set("runtime")
    component.set("node-js-binding")
    phase.set("validation")
    target.set("node-js")
    productVersion.set(project.version.toString())
    outputRoots.set(mapOf(
        "test-program" to "outputs/test-program",
        "test-report" to "outputs/test-report",
    ))
    outputsDirectory.set(nodeJsBindingValidationOutputs)
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
    stageRoot.set(nodeJsBindingValidationRoot)
    manifestFile.set(nodeJsBindingValidationRoot.map { it.file("output-manifest.json") })
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
