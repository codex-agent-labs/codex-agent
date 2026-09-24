import org.gradle.api.publish.PublishingExtension

val contractVersion = rootProject.extra["codexAgent.contractVersion"].toString()
val contractPublicationNames = listOf(
    "KotlinMultiplatform", "Android", "Jvm", "IosArm64", "IosSimulatorArm64", "MacosArm64",
    "MacosX64", "LinuxArm64", "LinuxX64", "MingwX64", "Js", "WasmJs",
)
val sdk = providers.provider {
    checkNotNull(findProject(":codex-agent-sdk")) {
        "SDK product phases require :codex-agent-sdk"
    }
}

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
        producerSources.from(layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(layout.projectDirectory)
    }
    val appleFrameworks = if (component == "sdk-ios") {
        val ios = project(":codex-agent-runtime-ios")
        listOf(
            Triple("IosArm64", "ios-arm64", "iphoneos"),
            Triple("IosSimulatorArm64", "ios-simulator-arm64", "iphonesimulator"),
        ).map { (targetName, targetId, platform) ->
            tasks.register<ImportCodexAgentFrameworkTask>("stageSdk${targetName}BinaryFramework") {
                dependsOn(reset, ":codex-agent-runtime-ios:linkReleaseFramework$targetName")
                frameworkDirectory.set(ios.layout.buildDirectory.dir(
                    "bin/${targetName.replaceFirstChar(Char::lowercase)}/releaseFramework/CodexAgent.framework",
                ))
                platformName.set(platform)
                importedFrameworkDirectory.set(phaseOutputs.map {
                    it.dir("apple-binary/$targetId/CodexAgent.framework")
                })
            }
        }
    } else emptyList()
    return tasks.register<WriteProductOutputManifestTask>("write${title}BinaryOutputManifest") {
        group = "publishing"
        description = "Stages the exact Contract-only $component binary outputs."
        dependsOn(verify, appleFrameworks)
        product.set("sdk")
        this.component.set(component)
        phase.set("binary")
        this.target.set(target)
        productVersion.set(rootProject.extra["codexAgent.sdkVersion"].toString())
        outputRoots.set(mapOf(
            "maven" to "outputs/maven",
            "evidence" to "outputs/evidence",
        ) + if (component == "sdk-ios") mapOf("apple-binary" to "outputs/apple-binary") else emptyMap())
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
        publishingProjects = listOf(rootProject, project(":codex-agent-sdk")),
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
        publishingProjects = listOf(project(":codex-agent-runtime-android")),
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
        publishingProjects = listOf(project(":codex-agent-runtime-ios")),
        publicationTaskPaths = listOf("KotlinMultiplatform", "IosArm64", "IosSimulatorArm64").map {
            ":codex-agent-runtime-ios:publish${it}PublicationToSDK_IOS_BINARY_STAGINGRepository"
        },
    )
} else null
val requestedProduct = providers.gradleProperty("codexAgent.product")
val requestedComponent = providers.gradleProperty("codexAgent.component")
val requestedPhase = providers.gradleProperty("codexAgent.phase")
val writeSdkCoreValidationOutputManifest = if (
    requestedProduct.orNull == "sdk" && requestedComponent.orNull == "sdk-core" &&
    requestedPhase.orNull == "validation"
) {
    listOf("codexAgent.target", "codexAgent.sdkFacadeValidationRequest",
        "codexAgent.sdkVersion", "codexAgent.candidateTree").forEach { property ->
        check(!providers.gradleProperty(property).orNull.isNullOrBlank()) {
            "Imported SDK facade validation requires $property"
        }
    }
    registerSdkFacadeValidationTasks(
        request = layout.file(providers.gradleProperty("codexAgent.sdkFacadeValidationRequest").map(::file)),
        sdkVersion = providers.gradleProperty("codexAgent.sdkVersion"),
        contractVersion = providers.provider { contractVersion },
        kotlinVersion = providers.provider {
            extensions.getByType<org.gradle.api.artifacts.VersionCatalogsExtension>()
                .named("libs").findVersion("kotlin").get().requiredVersion
        },
        runtimeVersion = providers.provider { rootProject.extra["codexAgent.sdkDefaultRuntimeVersion"].toString() },
        candidateTree = providers.gradleProperty("codexAgent.candidateTree"),
        androidSdkDirectory = providers.environmentVariable("ANDROID_HOME").orElse(
            providers.environmentVariable("ANDROID_SDK_ROOT")).orElse(
            providers.fileContents(layout.projectDirectory.file("local.properties")).asText.map { contents ->
                java.util.Properties().apply { load(contents.reader()) }.getProperty("sdk.dir", "")
            }).orElse(""),
        validationTarget = providers.gradleProperty("codexAgent.target").get(),
    )
} else null
val writeSdkCoreMetadataOutputManifest = if (
    requestedProduct.orNull == "sdk" && requestedComponent.orNull == "sdk-core" &&
    requestedPhase.orNull == "metadata"
) {
    check(providers.gradleProperty("codexAgent.target").orNull == "common") {
        "SDK facade metadata requires the exact common target"
    }
    val request = layout.file(providers.gradleProperty("codexAgent.sdkFacadeMetadataRequest").map(::file))
    registerSdkFacadeMetadataTasks(
        request = request,
        sdkVersion = providers.gradleProperty("codexAgent.sdkVersion"),
        referencedInputs = files(request.map { sdkFacadeMetadataInputFiles(it.asFile) }),
    )
} else null
val writeSdkAndroidMetadataOutputManifest = if (
    requestedProduct.orNull == "sdk" && requestedComponent.orNull == "sdk-android" &&
    requestedPhase.orNull == "metadata"
) {
    check(providers.gradleProperty("codexAgent.target").orNull == "android") {
        "SDK Android metadata requires the exact android target"
    }
    val request = layout.file(providers.gradleProperty("codexAgent.sdkAndroidMetadataRequest").map(::file))
    registerSdkAndroidMetadataTasks(
        request = request,
        sdkVersion = providers.gradleProperty("codexAgent.sdkVersion"),
        referencedInputs = files(request.map { sdkAndroidMetadataInputFiles(it.asFile) }),
    )
} else null
