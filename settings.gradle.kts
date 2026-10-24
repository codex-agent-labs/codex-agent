pluginManagement {
    includeBuild("gradle/build-logic")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

listOf(
    "codexAgent.authenticatedContractVersion",
    "codexAgent.authenticatedSdkComponent",
    "codexAgent.authenticatedAndroidEvidenceSdkVersion",
).forEach { name ->
    require(!providers.gradleProperty(name).isPresent) {
        "$name is reserved for verified settings state"
    }
}

val rootProjectProperties = gradle.startParameter.projectProperties
val appleExportBuildRootProperty = "codexAgent.appleExportBuildRoot"
if (providers.gradleProperty(appleExportBuildRootProperty).isPresent) {
    require(System.getProperty("org.gradle.project.$appleExportBuildRootProperty") == null &&
        System.getenv("ORG_GRADLE_PROJECT_$appleExportBuildRootProperty") == null) {
        "Apple export build root requires an explicit -P project property"
    }
    require(gradle.startParameter.taskNames == listOf(
        ":codex-agent-runtime-ios:exportCodexAgentIosVerifiedDistribution",
    ) && gradle.startParameter.includedBuilds.isEmpty()) {
        "Isolated Apple output layout is reserved for the single fresh export task"
    }
    val tree = rootProjectProperties["codexAgent.candidateTree"]
        ?: error("Isolated Apple export requires an explicit candidate tree")
    require(Regex("[0-9a-f]{40}").matches(tree)) { "Invalid Apple export candidate tree" }
    val repository = settingsDir.toPath().toRealPath()
    val expected = repository.resolve("build/apple-export/$tree")
    val supplied = java.nio.file.Path.of(
        rootProjectProperties[appleExportBuildRootProperty]
            ?: error("Missing explicit Apple export build root"),
    )
    require(supplied.isAbsolute && supplied.normalize() == supplied && supplied == expected) {
        "Apple export build root must be the exact repository-owned tree directory"
    }
    var ancestor: java.nio.file.Path? = supplied
    while (ancestor != null && ancestor.startsWith(repository)) {
        require(!java.nio.file.Files.isSymbolicLink(ancestor) &&
            (!java.nio.file.Files.exists(ancestor, java.nio.file.LinkOption.NOFOLLOW_LINKS) ||
                java.nio.file.Files.isDirectory(ancestor, java.nio.file.LinkOption.NOFOLLOW_LINKS))) {
            "Apple export build root has an unsafe parent"
        }
        ancestor = ancestor.parent
    }
    require(!java.nio.file.Files.exists(supplied, java.nio.file.LinkOption.NOFOLLOW_LINKS)) {
        "Apple export requires a fresh isolated build root"
    }
    val exportRoot = supplied.toFile()
    gradle.beforeProject(org.gradle.api.Action<org.gradle.api.Project> {
        if (path in setOf(":codex-agent-sdk", ":codex-agent-runtime-ios")) {
            layout.buildDirectory.set(exportRoot.resolve(name))
        }
    })
}
val sdkBinaryRequest = rootProjectProperties["codexAgent.product"] == "sdk" &&
    rootProjectProperties["codexAgent.phase"] == "binary"
val androidEvidenceProperties = listOf(
    "codexAgent.androidEvidencePackageStage",
    "codexAgent.androidEvidencePackageReceipt",
    "codexAgent.androidEvidenceBinaryStage",
    "codexAgent.androidEvidenceBinaryReceipt",
    "codexAgent.androidEvidenceCompatibilityRequest",
    "codexAgent.androidEvidenceBinaryContractEvidence",
)
val androidEvidenceRequest = androidEvidenceProperties.any(rootProjectProperties::containsKey)
var authenticatedSdkContractRepository: java.nio.file.Path? = null
var authenticatedAndroidEvidenceRepository: java.nio.file.Path? = null
if (sdkBinaryRequest || androidEvidenceRequest) {
    require(gradle.startParameter.includedBuilds.isEmpty()) {
        "Authenticated SDK inputs reject command-line composite build substitutions"
    }
    require(!sdkBinaryRequest || !androidEvidenceRequest) {
        "Android evidence import and SDK binary production must run separately"
    }
    if (androidEvidenceRequest) {
        require(androidEvidenceProperties.all(rootProjectProperties::containsKey) &&
            gradle.startParameter.taskNames.isNotEmpty() &&
            gradle.startParameter.taskNames.all {
                it in setOf(
                    ":tooling:android-runtime-evidence:assembleDebug",
                    ":tooling:android-runtime-evidence:assembleDebugAndroidTest",
                )
            }) {
            "Android evidence import requires complete inputs and only evidence APK tasks"
        }
    }
    val component = if (androidEvidenceRequest) "android-evidence" else
        rootProjectProperties["codexAgent.component"]
            ?: error("Missing mandatory explicit -P project property: codexAgent.component")
    val requiredComponents = when (component) {
        "sdk-core" -> listOf(
            "common", "android", "ios-arm64", "ios-simulator-arm64", "jvm",
            "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "node-js",
            "node-wasm", "windows-x64",
        )
        "sdk-android" -> listOf("android")
        "android-evidence" -> listOf("android")
        "sdk-ios" -> listOf("ios-arm64", "ios-simulator-arm64")
        "csharp" -> listOf("common")
        else -> error("Unsupported SDK binary component: $component")
    }
    val requiredProperties = listOf(
        "codexAgent.contractPayload",
        "codexAgent.contractMetadataReceipt",
        "codexAgent.contractAttestation",
        "codexAgent.contractAttestationSignature",
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
    val contractPayload = absoluteNormalizedPath("codexAgent.contractPayload")
    val contractMetadataReceipt = absoluteNormalizedPath("codexAgent.contractMetadataReceipt")
    val contractAttestation = absoluteNormalizedPath("codexAgent.contractAttestation")
    val contractAttestationSignature = absoluteNormalizedPath(
        "codexAgent.contractAttestationSignature",
    )
    val contractPublicKey = absoluteNormalizedPath("codexAgent.contractPublicKey")
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
        "python3", "-m", "ci.products.contract_attestation", "materialize",
        "--payload", contractPayload.toString(),
        "--metadata-receipt", contractMetadataReceipt.toString(),
        "--attestation", contractAttestation.toString(),
        "--signature", contractAttestationSignature.toString(),
        "--public-key", contractPublicKey.toString(),
        "--required-trust-domain", expectedTrustDomain,
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
        if (sdkBinaryRequest) {
            extensions.extraProperties.set("codexAgent.authenticatedSdkComponent", component)
        }
    })
    if (androidEvidenceRequest) {
        val inputs = androidEvidenceProperties.associateWith { name ->
            require(System.getProperty("org.gradle.project.$name") == null &&
                System.getenv("ORG_GRADLE_PROJECT_$name") == null) {
                "$name must be supplied only as an explicit -P project property"
            }
            val value = rootProjectProperties[name]?.takeIf(String::isNotBlank)
                ?: error("Missing mandatory explicit -P project property: $name")
            settingsDir.toPath().fileSystem.getPath(value).also { path ->
                require(path.isAbsolute && path.normalize() == path) {
                    "$name must be an absolute normalized path"
                }
            }
        }
        val verifiedAndroid = verifiedParent.resolve("android-evidence-${java.util.UUID.randomUUID()}")
        val command = mutableListOf(
            "python3", "-m", "ci.products.sdk_android_evidence_repository",
            "--repository", repositoryRoot.toString(),
            "--package-stage", inputs.getValue("codexAgent.androidEvidencePackageStage").toString(),
            "--package-receipt", inputs.getValue("codexAgent.androidEvidencePackageReceipt").toString(),
            "--binary-stage", inputs.getValue("codexAgent.androidEvidenceBinaryStage").toString(),
            "--binary-receipt", inputs.getValue("codexAgent.androidEvidenceBinaryReceipt").toString(),
            "--compatibility-request", inputs.getValue("codexAgent.androidEvidenceCompatibilityRequest").toString(),
            "--binary-contract-evidence", inputs.getValue("codexAgent.androidEvidenceBinaryContractEvidence").toString(),
            "--contract-payload", contractPayload.toString(),
            "--contract-metadata-receipt", contractMetadataReceipt.toString(),
            "--contract-attestation", contractAttestation.toString(),
            "--contract-attestation-signature", contractAttestationSignature.toString(),
            "--contract-public-key", contractPublicKey.toString(),
            "--destination", verifiedAndroid.toString(),
        )
        val version = providers.exec {
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
            commandLine(command)
        }.standardOutput.asText.get().trim()
        val sdkVersion = java.nio.file.Files.readString(
            repositoryRoot.resolve("gradle/release/versions/sdk.txt"), Charsets.US_ASCII,
        ).removeSuffix("\n")
        require(version == sdkVersion && sdkVersion.matches(semver)) {
            "Android evidence package version differs from this SDK source"
        }
        authenticatedAndroidEvidenceRepository = verifiedAndroid
        gradle.beforeProject(org.gradle.api.Action<org.gradle.api.Project> {
            extensions.extraProperties.set("codexAgent.authenticatedAndroidEvidenceSdkVersion", version)
        })
    }
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
                filter {
                    if (androidEvidenceRequest) {
                        includeModule("io.github.codex-agent-labs", "codex-agent-core")
                    } else {
                        includeGroup("io.github.codex-agent-labs")
                    }
                }
            }
            if (authenticatedAndroidEvidenceRepository != null) {
                exclusiveContent {
                    forRepository {
                        maven {
                            name = "AUTHENTICATED_SDK_ANDROID_EVIDENCE"
                            url = uri(authenticatedAndroidEvidenceRepository!!)
                        }
                    }
                    filter { includeModule("io.github.codex-agent-labs", "codex-agent-runtime-android") }
                }
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
