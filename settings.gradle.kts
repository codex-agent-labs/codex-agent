pluginManagement {
    includeBuild("gradle/build-logic")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

val rootProjectProperties = gradle.startParameter.projectProperties
val sdkBinaryRequest = rootProjectProperties["codexAgent.product"] == "sdk" &&
    rootProjectProperties["codexAgent.phase"] == "binary"
var authenticatedSdkContractRepository: java.nio.file.Path? = null
if (sdkBinaryRequest) {
    require(gradle.startParameter.includedBuilds.isEmpty()) {
        "SDK binary production rejects command-line composite build substitutions"
    }
    val component = rootProjectProperties["codexAgent.component"]
        ?: error("Missing mandatory explicit -P project property: codexAgent.component")
    val requiredComponents = when (component) {
        "sdk-core" -> listOf(
            "common", "android", "ios-arm64", "ios-simulator-arm64", "jvm",
            "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "node-js",
            "node-wasm", "windows-x64",
        )
        "sdk-android" -> listOf("android")
        "sdk-ios" -> listOf("ios-arm64", "ios-simulator-arm64")
        else -> error("Unsupported SDK binary component: $component")
    }
    val requiredProperties = listOf(
        "codexAgent.contractRepository",
        "codexAgent.contractManifest",
        "codexAgent.contractPublicKey",
        "codexAgent.contractVersion",
    )
    val values = requiredProperties.associateWith { name ->
        require(System.getProperty("org.gradle.project.$name") == null &&
            System.getenv("ORG_GRADLE_PROJECT_$name") == null) {
            "$name must be supplied only as an explicit -P project property"
        }
        rootProjectProperties[name]?.takeIf(String::isNotBlank)
            ?: error("Missing mandatory explicit -P project property: $name")
    }
    fun absoluteNormalizedPath(name: String): java.nio.file.Path =
        settingsDir.toPath().fileSystem.getPath(values.getValue(name)).also { path ->
            require(path.isAbsolute && path.normalize() == path) {
                "$name must be an absolute normalized path"
            }
        }
    val contractRepository = absoluteNormalizedPath("codexAgent.contractRepository")
    val contractManifest = absoluteNormalizedPath("codexAgent.contractManifest")
    val contractPublicKey = absoluteNormalizedPath("codexAgent.contractPublicKey")
    require(contractManifest.fileName.toString() == "contract-manifest.json") {
        "codexAgent.contractManifest must name contract-manifest.json"
    }
    require(contractRepository == contractManifest.parent.resolve("maven")) {
        "codexAgent.contractRepository must be the manifest sibling named maven"
    }
    val versionBytes = java.nio.file.Files.readAllBytes(
        settingsDir.toPath().resolve("gradle/release/versions/contract.txt"),
    )
    require(versionBytes.isNotEmpty() && versionBytes.last() == '\n'.code.toByte() &&
        versionBytes.count { it == '\n'.code.toByte() } == 1) {
        "Contract version authority must contain one LF-terminated SemVer"
    }
    val contractVersion = versionBytes.dropLast(1).toByteArray().toString(Charsets.US_ASCII)
    val semver = Regex(
        "(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)" +
            "(?:-[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?",
    )
    require(semver.matches(contractVersion) && contractVersion == values.getValue("codexAgent.contractVersion")) {
        "Requested Contract version does not match gradle/release/versions/contract.txt"
    }

    val repositoryRoot = settingsDir.toPath().toRealPath()
    val verifiedParent = repositoryRoot.resolve(".gradle/verified-contracts")
    java.nio.file.Files.createDirectories(verifiedParent)
    require(java.nio.file.Files.isDirectory(verifiedParent, java.nio.file.LinkOption.NOFOLLOW_LINKS) &&
        !java.nio.file.Files.isSymbolicLink(verifiedParent) &&
        verifiedParent.toRealPath().startsWith(repositoryRoot)) {
        "SDK verified Contract directory is unsafe"
    }
    val verifiedContract = verifiedParent.resolve("sdk-${java.util.UUID.randomUUID()}")
    val expectedTrustDomain = if (System.getenv("GITHUB_ACTIONS") == "true") "release" else "development"
    val verifyCommand = mutableListOf(
        "python3", "-m", "ci.products.contract", "verify-directory",
        "--directory", contractManifest.parent.toString(),
        "--public-key", contractPublicKey.toString(),
        "--expected-trust-domain", expectedTrustDomain,
        "--expected-contract-version", contractVersion,
        "--output-directory", verifiedContract.toString(),
        "--reuse-output-directory",
    )
    requiredComponents.forEach { verifyCommand += listOf("--required-component", it) }
    if (expectedTrustDomain == "release") {
        verifyCommand += listOf(
            "--keyring", repositoryRoot.resolve("gradle/release/product-signing-keys.json").toString(),
            "--keys-directory", repositoryRoot.resolve("gradle/release/keys").toString(),
        )
    }
    providers.exec {
        workingDir(repositoryRoot.toFile())
        setEnvironment(environment.toMutableMap().apply {
            remove("PYTHONHOME")
            remove("PYTHONINSPECT")
            remove("PYTHONSTARTUP")
            put("PYTHONPATH", repositoryRoot.toString())
            put("PYTHONDONTWRITEBYTECODE", "1")
            put("PYTHONNOUSERSITE", "1")
            put("PYTHONSAFEPATH", "1")
            put("LC_ALL", "C")
            put("LANG", "C")
        })
        commandLine(verifyCommand)
    }.result.get().assertNormalExitValue()
    authenticatedSdkContractRepository = verifiedContract.resolve("maven")
    gradle.beforeProject(org.gradle.api.Action<org.gradle.api.Project> {
        extensions.extraProperties.set("codexAgent.authenticatedContractVersion", contractVersion)
        extensions.extraProperties.set("codexAgent.authenticatedSdkComponent", component)
    })
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        if (authenticatedSdkContractRepository != null) {
            exclusiveContent {
                forRepository {
                    maven {
                        name = "AUTHENTICATED_SDK_CONTRACT_BUNDLE"
                        url = uri(authenticatedSdkContractRepository!!)
                    }
                }
                filter { includeGroup("io.github.codex-agent-labs") }
            }
            google { content { excludeGroup("io.github.codex-agent-labs") } }
            mavenCentral { content { excludeGroup("io.github.codex-agent-labs") } }
        } else {
            google()
            mavenCentral()
        }
    }
}

rootProject.name = "codex-agent"

include(
    ":codex-agent-core",
    ":codex-agent-sdk",
    ":codex-agent-runtime-android",
    ":codex-agent-runtime-ios",
    ":tooling:android-runtime-evidence",
    ":tooling:protocol-generator",
)
