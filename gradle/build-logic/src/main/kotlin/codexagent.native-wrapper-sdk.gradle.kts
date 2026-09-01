import org.gradle.api.Task
import org.gradle.api.file.DuplicatesStrategy
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.Sync
import org.gradle.api.tasks.TaskProvider

val nativeWrapperRuntimeStageRoot = providers.gradleProperty("codexAgent.nativeWrapperRuntimeStageRoot")
    .map(::file)
val nativeWrapperRuntimeVersion = providers.provider {
    rootProject.extra["codexAgent.sdkDefaultRuntimeVersion"].toString()
}
val nativeWrapperRuntimeCompatibilityVersion = nativeWrapperRuntimeVersion.map(::runtimeCompatibilityVersion)
val nativeWrapperSdkVersion = providers.provider {
    rootProject.extra["codexAgent.sdkVersion"].toString()
}
val nativeWrapperCandidateCommit = providers.gradleProperty("codexAgent.candidateCommit")
val nativeWrapperCandidateTree = providers.gradleProperty("codexAgent.candidateTree")
val nativeWrapperSdkCompatibilityRequest = providers.gradleProperty(
    "codexAgent.sdkCompatibilityRequest",
).map(::file)
val nativeWrapperRuntimeManifestTaskNames = linkedMapOf(
    ("macos-arm64" to "package") to "verifyImportedNativeWrapperMacosArm64RuntimePackageOutputManifest",
    ("macos-arm64" to "validation") to "verifyImportedNativeWrapperMacosArm64RuntimeValidationOutputManifest",
    ("macos-x64" to "package") to "verifyImportedNativeWrapperMacosX64RuntimePackageOutputManifest",
    ("macos-x64" to "validation") to "verifyImportedNativeWrapperMacosX64RuntimeValidationOutputManifest",
    ("linux-arm64" to "package") to "verifyImportedNativeWrapperLinuxArm64RuntimePackageOutputManifest",
    ("linux-arm64" to "validation") to "verifyImportedNativeWrapperLinuxArm64RuntimeValidationOutputManifest",
    ("linux-x64" to "package") to "verifyImportedNativeWrapperLinuxX64RuntimePackageOutputManifest",
    ("linux-x64" to "validation") to "verifyImportedNativeWrapperLinuxX64RuntimeValidationOutputManifest",
    ("windows-x64" to "package") to "verifyImportedNativeWrapperWindowsX64RuntimePackageOutputManifest",
    ("windows-x64" to "validation") to "verifyImportedNativeWrapperWindowsX64RuntimeValidationOutputManifest",
)
val invalidateNativeWrapperProductPhaseOutputs = tasks.register<Delete>(
    "invalidateNativeWrapperProductPhaseOutputs",
) {
    group = "verification"
    description = "Deletes stale native-wrapper SDK outputs before imported Runtime verification."
    delete(
        layout.buildDirectory.dir("native-wrapper-package-sources"),
        listOf("python", "csharp", "rust", "cpp", "dart").map { language ->
            layout.buildDirectory.dir("product-stage/sdk/$language/package")
        },
    )
}
val nativeWrapperRuntimeSnapshotRoot = layout.buildDirectory.dir(
    nativeWrapperCandidateTree.map { "imported-native-wrapper-runtime-stages/$it" },
)
val snapshotImportedNativeWrapperRuntimeStages =
    tasks.register<SnapshotImportedNativeWrapperRuntimeStagesTask>(
        "snapshotImportedNativeWrapperRuntimeStages",
    ) {
        group = "verification"
        description = "Snapshots the exact imported Runtime package/validation stages before verification."
        dependsOn(invalidateNativeWrapperProductPhaseOutputs)
        runtimeStageRoot.set(layout.dir(nativeWrapperRuntimeStageRoot))
        outputDirectory.set(nativeWrapperRuntimeSnapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
val nativeWrapperRuntimeManifestVerifiers = nativeWrapperRuntimeManifestTaskNames.map { (identity, taskName) ->
    val (component, productPhase) = identity
    tasks.register<VerifyImportedProductOutputManifestTask>(taskName) {
        group = "verification"
        description = "Verifies the imported $component Runtime $productPhase stage for SDK wrappers."
        dependsOn(snapshotImportedNativeWrapperRuntimeStages)
        product.set("runtime")
        this.component.set(component)
        phase.set(productPhase)
        target.set(component)
        productVersion.set(nativeWrapperRuntimeVersion)
        stageRoot.set(nativeWrapperRuntimeSnapshotRoot.map { it.dir("$component/$productPhase") })
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
}
val generateNativeWrapperSdkCompatibility =
    tasks.register<GenerateNativeWrapperSdkCompatibilityTask>(
        "generateNativeWrapperSdkCompatibility",
    ) {
        group = "distribution"
        description = "Authenticates Contract and Runtime products and generates the shared SDK policy."
        requestFile.set(layout.file(nativeWrapperSdkCompatibilityRequest))
        outputFile.set(layout.buildDirectory.file(
            nativeWrapperCandidateTree.map { "sdk-compatibility/$it/sdk-compatibility.json" },
        ))
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
val stageNativeWrapperCAbiSdks = tasks.register<StageCrossLanguageNativeWrapperSdksTask>(
    "stageNativeWrapperCAbiSdks",
) {
    group = "distribution"
    description = "Verifies and stages five imported Runtime C ABI SDKs for SDK-owned native wrappers."
    dependsOn(nativeWrapperRuntimeManifestVerifiers, generateNativeWrapperSdkCompatibility)
    libraryVersion.set(nativeWrapperRuntimeCompatibilityVersion)
    runtimeProductVersion.set(nativeWrapperRuntimeVersion)
    sdkVersion.set(nativeWrapperSdkVersion)
    sdkCompatibility.set(generateNativeWrapperSdkCompatibility.flatMap { it.outputFile })
    producerCommit.set(nativeWrapperCandidateCommit)
    producerTree.set(nativeWrapperCandidateTree)
    runtimeStageRoot.set(nativeWrapperRuntimeSnapshotRoot)
    outputDirectory.set(layout.buildDirectory.dir(
        nativeWrapperCandidateTree.map { "native-wrapper-c-abi-sdks/$it" },
    ))
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}

val materializeNativeWrapperPackageAssets = tasks.register<MaterializeCrossLanguageNativeWrapperPackageAssetsTask>(
    "materializeNativeWrapperPackageAssets",
) {
    group = "distribution"
    description = "Maps the verified C ABI SDK bytes into the five native-wrapper package layouts."
    dependsOn(stageNativeWrapperCAbiSdks)
    stagedSdkDirectory.from(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory })
    outputDirectory.set(layout.buildDirectory.dir(
        nativeWrapperCandidateTree.map { "native-wrapper-package-assets/$it" },
    ))
    producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
    repositoryRoot.set(rootProject.layout.projectDirectory)
}

val nativeWrapperBindingRoot = rootProject.layout.projectDirectory.dir("codex-agent-bindings")
val nativeWrapperLanguageSpecs = linkedMapOf(
    "python" to ("Python" to listOf("build/**", "dist/**", "**/__pycache__/**", "**/*.egg-info/**")),
    "csharp" to ("CSharp" to listOf("artifacts/**", "**/bin/**", "**/obj/**")),
    "rust" to ("Rust" to listOf("target/**", "consumer/target/**")),
    "cpp" to ("Cpp" to listOf("build*/**", "consumer/build*/**")),
    "dart" to ("Dart" to listOf("build/**", ".dart_tool/**", ".pub/**", "doc/**")),
)
val nativeWrapperDevelopmentCompatibilityFixtures = mapOf(
    "python" to "src/codex_agent/native/sdk-compatibility.json",
    "csharp" to "native/sdk-compatibility.json",
    "rust" to "native/sdk-compatibility.json",
    "dart" to "lib/src/native/sdk-compatibility.json",
)
val nativeWrapperPackageSourceTasks = nativeWrapperLanguageSpecs.mapValues { (language, identity) ->
    val (title, excluded) = identity
    tasks.register<Sync>("prepare${title}NativeWrapperPackageSource") {
        group = "distribution"
        description = "Prepares the $language wrapper package source with verified native SDK bytes."
        dependsOn(materializeNativeWrapperPackageAssets)
        duplicatesStrategy = DuplicatesStrategy.FAIL
        from(nativeWrapperBindingRoot.dir(language)) {
            exclude(excluded + listOfNotNull(nativeWrapperDevelopmentCompatibilityFixtures[language]))
        }
        from(materializeNativeWrapperPackageAssets.flatMap { it.outputDirectory.dir(language) })
        into(layout.buildDirectory.dir("native-wrapper-package-sources/$language"))
    }
}
val nativeWrapperSdkPackageTaskNames = linkedMapOf(
    "python" to Triple(
        "stagePythonNativeWrapperSdkPackagePhase",
        "writePythonNativeWrapperSdkPackageOutputManifest",
        "product-stage/sdk/python/package",
    ),
    "csharp" to Triple(
        "stageCSharpNativeWrapperSdkPackagePhase",
        "writeCSharpNativeWrapperSdkPackageOutputManifest",
        "product-stage/sdk/csharp/package",
    ),
    "rust" to Triple(
        "stageRustNativeWrapperSdkPackagePhase",
        "writeRustNativeWrapperSdkPackageOutputManifest",
        "product-stage/sdk/rust/package",
    ),
    "cpp" to Triple(
        "stageCppNativeWrapperSdkPackagePhase",
        "writeCppNativeWrapperSdkPackageOutputManifest",
        "product-stage/sdk/cpp/package",
    ),
    "dart" to Triple(
        "stageDartNativeWrapperSdkPackagePhase",
        "writeDartNativeWrapperSdkPackageOutputManifest",
        "product-stage/sdk/dart/package",
    ),
)
val nativeWrapperSdkPackageManifestTasks = nativeWrapperSdkPackageTaskNames.mapValues { (language, names) ->
    val (stageTaskName, manifestTaskName, phasePath) = names
    val phaseRoot = layout.buildDirectory.dir(phasePath)
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val stage = tasks.register<Sync>(stageTaskName) {
        group = "distribution"
        description = "Stages the exact $language SDK wrapper package inputs once."
        dependsOn(nativeWrapperPackageSourceTasks.getValue(language))
        into(phaseOutputs)
        from(nativeWrapperPackageSourceTasks.getValue(language)) { into("package-source") }
        from(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory }) { into("runtime-sdks") }
        includeEmptyDirs = false
        duplicatesStrategy = DuplicatesStrategy.FAIL
    }
    tasks.register<WriteProductOutputManifestTask>(manifestTaskName) {
        group = "distribution"
        description = "Writes and verifies the exact $language SDK package manifest."
        dependsOn(stage)
        product.set("sdk")
        component.set(language)
        phase.set("package")
        target.set("desktop")
        productVersion.set(nativeWrapperSdkVersion)
        outputRoots.set(mapOf(
            "package-source" to "outputs/package-source",
            "runtime-sdks" to "outputs/runtime-sdks",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
    }
}
tasks.register("prepareNativeWrapperPackageSources") {
    group = "distribution"
    description = "Prepares all native wrapper package sources from the verified five-host SDK staging."
    dependsOn(nativeWrapperPackageSourceTasks.values)
}

val nativeWrapperReleaseDirectory = providers.gradleProperty("codexAgent.nativeWrapperReleaseDirectory")
    .map(::file)
val nativeWrapperHostEvidenceDirectory = providers.gradleProperty(
    "codexAgent.nativeWrapperHostEvidenceDirectory",
).map(::file)
val nativeWrapperApiReport = providers.gradleProperty("codexAgent.nativeWrapperApiReport").map(::file)
val nativeWrapperCoverageReceipt = providers.gradleProperty(
    "codexAgent.nativeWrapperCoverageReceipt",
).map(::file)
val nativeWrapperBootstrapEvidence = providers.gradleProperty(
    "codexAgent.nativeWrapperBootstrapEvidence",
).map(::file)
val nativeWrapperBindingSpecs = listOf(
    Triple("Python", "python", "M9_PYTHON"),
    Triple("CSharp", "csharp", "M9_CSHARP"),
    Triple("Rust", "rust", "M9_RUST"),
    Triple("Cpp", "cpp", "M9_CPP"),
    Triple("Dart", "dart", "M9_DART"),
)
val nativeWrapperReceiptFiles = nativeWrapperBindingSpecs.associate { (_, language, _) ->
    language to layout.buildDirectory.file(
        "reports/cross-language-api/bindings/$language-parity.json",
    )
}
val invalidateNativeWrapperBindingParityOutputs = tasks.register<Delete>(
    "invalidateNativeWrapperBindingParityOutputs",
) {
    group = "verification"
    description = "Deletes all stale native-wrapper parity receipts before evidence verification."
    delete(nativeWrapperReceiptFiles.values)
}
val nativeWrapperReceiptTasks: Map<String, TaskProvider<out Task>> = nativeWrapperBindingSpecs.associate {
    (title, language, phase) ->
    language to tasks.register<GenerateCrossLanguageNativeWrapperBindingReceiptTask>(
        "verify${title}BindingParity",
    ) {
        group = "verification"
        description = "Verifies exact compiler, behavior, package, and five-host $language binding parity."
        dependsOn(invalidateNativeWrapperBindingParityOutputs)
        this.phase.set(phase)
        this.language.set(language)
        apiReport.set(layout.file(nativeWrapperApiReport))
        canonicalCoverageReceipt.set(layout.file(nativeWrapperCoverageReceipt))
        cAbiBootstrapEvidence.set(layout.file(nativeWrapperBootstrapEvidence))
        claims.set(nativeWrapperBindingRoot.file("$language/parity/capability-claims.tsv"))
        compilerEvidence.set(layout.file(nativeWrapperReleaseDirectory.map {
            it.resolve("evidence/$language/compiler-evidence.tsv")
        }))
        testProgram.set(layout.file(nativeWrapperReleaseDirectory.map {
            it.resolve("evidence/$language/test-program")
        }))
        testResults.set(layout.file(nativeWrapperReleaseDirectory.map {
            it.resolve("evidence/$language/executed-tests.tsv")
        }))
        packageArtifacts.set(layout.dir(nativeWrapperReleaseDirectory.map { it.resolve("packages/$language") }))
        hostEvidenceDirectory.set(layout.dir(nativeWrapperHostEvidenceDirectory.map { it.resolve(language) }))
        stagedCAbiSdks.set(layout.dir(nativeWrapperReleaseDirectory.map { it.resolve("sdks") }))
        receipt.set(nativeWrapperReceiptFiles.getValue(language))
    }
}
tasks.register("verifyNativeWrapperBindingParity") {
    group = "verification"
    description = "Verifies all five native-wrapper language projections from authoritative evidence."
    dependsOn(nativeWrapperReceiptTasks.values)
}
