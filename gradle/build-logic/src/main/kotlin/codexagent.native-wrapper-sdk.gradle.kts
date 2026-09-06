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
val importedNativeWrapperSdkPackageStage = providers.gradleProperty(
    "codexAgent.sdkPackageStageRoot",
).map(::file)
val nativeWrapperRuntimeSnapshotRoot = layout.buildDirectory.dir(
    nativeWrapperCandidateTree.map { "imported-native-wrapper-runtime-stages/$it" },
)
val invalidateNativeWrapperProductPhaseOutputs = tasks.register<Delete>(
    "invalidateNativeWrapperProductPhaseOutputs",
) {
    group = "verification"
    description = "Deletes stale native-wrapper SDK outputs before imported Runtime verification."
    delete(nativeWrapperRuntimeSnapshotRoot)
    delete(layout.buildDirectory.dir(nativeWrapperCandidateTree.map { "native-wrapper-c-abi-sdks/$it" }))
    delete(layout.buildDirectory.dir(nativeWrapperCandidateTree.map { "native-wrapper-package-assets/$it" }))
}
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
val generateNativeWrapperSdkCompatibility =
    tasks.register<GenerateNativeWrapperSdkCompatibilityTask>(
        "generateNativeWrapperSdkCompatibility",
    ) {
        group = "distribution"
        description = "Authenticates Contract and Runtime products and generates the shared SDK policy."
        requestFile.set(layout.file(nativeWrapperSdkCompatibilityRequest))
        resourceDirectory.set(layout.buildDirectory.dir(
            nativeWrapperCandidateTree.map { "sdk-compatibility/$it" },
        ))
        outputFile.set(resourceDirectory.file("META-INF/codex-agent/sdk-compatibility.json"))
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
val sdkMavenPackageSpecs = linkedMapOf(
    "sdk-core" to Triple("SdkCore", "common", "codexAgent.sdkCoreBinaryStageRoot"),
    "sdk-android" to Triple("SdkAndroid", "android", "codexAgent.sdkAndroidBinaryStageRoot"),
    "sdk-ios" to Triple("SdkIos", "ios", "codexAgent.sdkIosBinaryStageRoot"),
)
val sdkMavenPackageManifestTasks = sdkMavenPackageSpecs.mapValues { (component, spec) ->
    val (title, target, property) = spec
    val imported = layout.dir(providers.gradleProperty(property).map(::file))
    val snapshot = layout.buildDirectory.dir(
        nativeWrapperCandidateTree.map { "imported-sdk-binary-stages/$it/$component" },
    )
    val reset = tasks.register<Delete>("resetImported${title}BinaryStage") { delete(snapshot) }
    val snapshotTask = tasks.register<SnapshotImportedProductStageTask>("snapshotImported${title}BinaryStage") {
        dependsOn(reset)
        sourceDirectory.set(imported)
        outputDirectory.set(snapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verify = tasks.register<VerifyImportedProductOutputManifestTask>("verifyImported${title}BinaryStage") {
        dependsOn(snapshotTask)
        product.set("sdk")
        this.component.set(component)
        phase.set("binary")
        this.target.set(target)
        productVersion.set(nativeWrapperSdkVersion)
        stageRoot.set(snapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val phaseRoot = layout.buildDirectory.dir("product-stage/sdk/$component/package")
    val phaseOutputs = phaseRoot.map { it.dir("outputs") }
    val invalidate = tasks.register<Delete>("invalidate${title}PackagePhase") {
        delete(phaseRoot)
    }
    snapshotTask.configure { dependsOn(invalidate) }
    generateNativeWrapperSdkCompatibility.configure { mustRunAfter(invalidate) }
    val stage = tasks.register<PackageSdkMavenArtifactsTask>("stage${title}PackagePhase") {
        dependsOn(verify, generateNativeWrapperSdkCompatibility)
        binaryMavenRepository.set(snapshot.map { it.dir("outputs/maven") })
        sdkCompatibility.set(generateNativeWrapperSdkCompatibility.flatMap { it.outputFile })
        this.component.set(component)
        groupId.set(project.group.toString())
        sdkVersion.set(nativeWrapperSdkVersion)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        outputDirectory.set(phaseOutputs.map { it.dir("maven") })
    }
    val evidence = tasks.register<Sync>("stage${title}PackageEvidence") {
        dependsOn(stage)
        from(generateNativeWrapperSdkCompatibility.flatMap { it.outputFile })
        into(phaseOutputs.map { it.dir("evidence") })
    }
    tasks.register<WriteProductOutputManifestTask>("write${title}PackageOutputManifest") {
        dependsOn(evidence)
        product.set("sdk")
        this.component.set(component)
        phase.set("package")
        this.target.set(target)
        productVersion.set(nativeWrapperSdkVersion)
        outputRoots.set(mapOf(
            "evidence" to "outputs/evidence",
            "maven" to "outputs/maven",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
    }
}
val stageNativeWrapperCAbiSdks = tasks.register<StageCrossLanguageNativeWrapperSdksTask>(
    "stageNativeWrapperCAbiSdks",
) {
    group = "distribution"
    description = "Verifies and stages five imported Runtime C ABI SDKs for SDK-owned native wrappers."
    dependsOn(snapshotImportedNativeWrapperRuntimeStages, generateNativeWrapperSdkCompatibility)
    libraryVersion.set(nativeWrapperRuntimeCompatibilityVersion)
    runtimeProductVersion.set(nativeWrapperRuntimeVersion)
    sdkVersion.set(nativeWrapperSdkVersion)
    sdkCompatibility.set(generateNativeWrapperSdkCompatibility.flatMap { it.outputFile })
    compatibilityRequest.set(layout.file(nativeWrapperSdkCompatibilityRequest))
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
val prepareNativeWrapperPackageSources = tasks.register("prepareNativeWrapperPackageSources") {
    group = "distribution"
    description = "Prepares all native wrapper package sources from the verified five-host SDK staging."
    dependsOn(nativeWrapperPackageSourceTasks.values)
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
    val stage = tasks.register<PackageNativeWrapperSdkTask>(stageTaskName) {
        group = "distribution"
        description = "Builds the exact reproducible $language SDK package from verified Runtime inputs."
        dependsOn(nativeWrapperPackageSourceTasks.getValue(language), stageNativeWrapperCAbiSdks)
        this.language.set(language)
        sourcesDirectory.set(layout.buildDirectory.dir("native-wrapper-package-sources/$language"))
        sdkDirectory.set(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory })
        sdkVersionFile.set(rootProject.layout.projectDirectory.file("gradle/release/versions/sdk.txt"))
        packageScript.set(rootProject.layout.projectDirectory.file("ci/native_wrappers.py"))
        outputDirectory.set(phaseOutputs)
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val evidenceTitle = manifestTaskName.removePrefix("write").removeSuffix("OutputManifest")
    val evidence = tasks.register<Sync>("stage${evidenceTitle}Evidence") {
        dependsOn(stage)
        from(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory }) {
            include("sdk-compatibility.json")
        }
        into(phaseOutputs.map { it.dir("evidence") })
    }
    tasks.register<WriteProductOutputManifestTask>(manifestTaskName) {
        group = "distribution"
        description = "Writes and verifies the exact $language SDK package manifest."
        dependsOn(evidence)
        product.set("sdk")
        component.set(language)
        phase.set("package")
        target.set("desktop")
        productVersion.set(nativeWrapperSdkVersion)
        outputRoots.set(mapOf(
            "evidence" to "outputs/evidence",
            "package" to "outputs/$language",
        ))
        outputsDirectory.set(phaseOutputs)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
        stageRoot.set(phaseRoot)
        manifestFile.set(phaseRoot.map { it.file("output-manifest.json") })
    }
}

// The snapshot verifier checks integrity; the typed consumer authenticates its
// original package receipt and complete input plan before running any SDK tool.
val nativeWrapperInstalledConsumerTasks = nativeWrapperLanguageSpecs.mapValues { (language, identity) ->
    val (title, excluded) = identity
    val importedSnapshot = layout.buildDirectory.dir(
        nativeWrapperCandidateTree.map { "imported-sdk-product-stages/$it/$language-package" },
    )
    val evidence = layout.buildDirectory.dir(
        nativeWrapperCandidateTree.map { "reports/native-wrapper-installed-consumer/$it/$language" },
    )
    val invalidate = tasks.register<Delete>("invalidate${title}NativeWrapperInstalledConsumer") {
        delete(importedSnapshot, evidence)
        delete(layout.buildDirectory.dir(nativeWrapperCandidateTree.map { "native-wrapper-capability-inputs/$it/$language" }))
        delete(layout.buildDirectory.dir(nativeWrapperCandidateTree.map { "reports/native-wrapper-capability/$it/$language" }))
    }
    snapshotImportedNativeWrapperRuntimeStages.configure { mustRunAfter(invalidate) }
    generateNativeWrapperSdkCompatibility.configure { mustRunAfter(invalidate) }
    val snapshot = tasks.register<SnapshotImportedProductStageTask>(
        "snapshotImported${title}NativeWrapperSdkPackage",
    ) {
        dependsOn(invalidate)
        sourceDirectory.set(layout.dir(importedNativeWrapperSdkPackageStage))
        outputDirectory.set(importedSnapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verify = tasks.register<VerifyImportedProductOutputManifestTask>(
        "verifyImported${title}NativeWrapperSdkPackage",
    ) {
        dependsOn(snapshot)
        product.set("sdk")
        component.set(language)
        phase.set("package")
        target.set("desktop")
        productVersion.set(nativeWrapperSdkVersion)
        stageRoot.set(importedSnapshot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    tasks.register<NativeWrapperInstalledConsumerTask>("verify${title}NativeWrapperInstalledConsumer") {
        group = "verification"
        description = "Authenticates original package inputs and executes the matching-host $language consumer."
        dependsOn(verify, stageNativeWrapperCAbiSdks)
        this.language.set(language)
        expectedClassifier.set(providers.gradleProperty("codexAgent.target"))
        offlineMode.set(gradle.startParameter.isOffline)
        packageStageDirectory.set(importedSnapshot)
        packageReceipt.set(rootProject.layout.file(providers.gradleProperty("codexAgent.sdkPackageReceipt").map(::file)))
        compatibilityRequest.set(layout.file(nativeWrapperSdkCompatibilityRequest))
        runtimeStageDirectory.set(nativeWrapperRuntimeSnapshotRoot)
        verifierSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        stagedSdkDirectory.set(stageNativeWrapperCAbiSdks.flatMap { it.outputDirectory })
        sdkVersionFile.set(rootProject.layout.projectDirectory.file("gradle/release/versions/sdk.txt"))
        consumerScript.set(rootProject.layout.projectDirectory.file("ci/native_wrappers.py"))
        consumerSources.from(nativeWrapperBindingRoot.dir(language).asFileTree.matching { exclude(excluded) })
        outputDirectory.set(evidence)
        capabilityInputsDirectory.set(layout.buildDirectory.dir(
            nativeWrapperCandidateTree.map { "native-wrapper-capability-inputs/$it/$language" },
        ))
        if (language == "cpp") packageNegativeEvidenceDirectory.set(layout.buildDirectory.dir(
            nativeWrapperCandidateTree.map { "native-wrapper-package-negatives/$it/$language" },
        ))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
}

val nativeWrapperCapabilityEvidenceTasks = nativeWrapperLanguageSpecs.mapValues { (language, identity) ->
    val (title, excluded) = identity
    val authenticated = nativeWrapperInstalledConsumerTasks.getValue(language)
    tasks.register<NativeWrapperCapabilityEvidenceTask>("verify${title}NativeWrapperCapabilityEvidence") {
        group = "verification"
        description = "Runs and verifies full $language capability evidence from authenticated imported inputs."
        dependsOn(authenticated)
        this.language.set(language)
        expectedClassifier.set(providers.gradleProperty("codexAgent.target"))
        capabilityInputsDirectory.set(authenticated.flatMap { it.capabilityInputsDirectory })
        installedConsumerEvidence.set(authenticated.flatMap { it.outputDirectory })
        producerScript.set(nativeWrapperBindingRoot.file(
            "$language/${if (language == "dart") "tool" else "tools"}/produce_sdk_validation_evidence.py",
        ))
        claims.set(nativeWrapperBindingRoot.file("$language/parity/capability-claims.tsv"))
        producerSources.from(nativeWrapperBindingRoot.dir(language).asFileTree.matching { exclude(excluded) })
        if (language == "csharp") producerSources.from(
            nativeWrapperBindingRoot.dir("csharp/src/CodexAgent/obj").asFileTree.matching { include("*") },
            nativeWrapperBindingRoot.dir("csharp/tests/CodexAgent.Tests/obj").asFileTree.matching { include("*") },
        )
        dotnetExecutable.set(providers.gradleProperty("codexAgent.dotnetExecutable"))
        dartExecutable.set(providers.gradleProperty("codexAgent.dartExecutable"))
        dartPackageConfig.set(layout.file(providers.gradleProperty("codexAgent.dartPackageConfig").map(::file)))
        outputDirectory.set(layout.buildDirectory.dir(
            nativeWrapperCandidateTree.map { "reports/native-wrapper-capability/$it/$language" },
        ))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
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
