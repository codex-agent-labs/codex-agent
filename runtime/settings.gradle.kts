pluginManagement {
    val repositoryRoot = settingsDir.parentFile.toPath().toAbsolutePath().normalize()
    val requiredProperties = listOf(
        "codexAgent.contractRepository",
        "codexAgent.contractManifest",
        "codexAgent.contractPublicKey",
        "codexAgent.contractVersion",
        "codexAgent.runtimeVersion",
        "codexAgent.target",
    )
    val commandLineProperties = gradle.startParameter.projectProperties
    require(gradle.startParameter.includedBuilds.isEmpty()) {
        "Standalone Runtime rejects command-line composite build substitutions"
    }
    val values = requiredProperties.associateWith { name ->
        require(System.getProperty("org.gradle.project.$name") == null &&
            System.getenv("ORG_GRADLE_PROJECT_$name") == null) {
            "$name must be supplied only as an explicit -P project property"
        }
        commandLineProperties[name]?.takeIf(String::isNotBlank)
            ?: error("Missing mandatory explicit -P project property: $name")
    }
    fun absoluteNormalizedPath(name: String) = repositoryRoot.fileSystem.getPath(
        commandLineProperties[name] ?: values.getValue(name),
    ).also { path ->
        require(path.isAbsolute && path.normalize() == path) { "$name must be an absolute normalized path" }
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

    val runtimeVersionFile = repositoryRoot.resolve("gradle/release/versions/runtime.txt")
    require(java.nio.file.Files.isRegularFile(runtimeVersionFile) &&
        !java.nio.file.Files.isSymbolicLink(runtimeVersionFile)) {
        "Runtime version authority is missing or unsafe"
    }
    val runtimeVersionBytes = java.nio.file.Files.readAllBytes(runtimeVersionFile)
    require(runtimeVersionBytes.isNotEmpty() && runtimeVersionBytes.last() == '\n'.code.toByte() &&
        runtimeVersionBytes.count { it == '\n'.code.toByte() } == 1 &&
        runtimeVersionBytes.dropLast(1).asSequence().all { it.toInt() in 0x20..0x7e }) {
        "Runtime version authority must contain one LF-terminated SemVer"
    }
    val runtimeVersion = runtimeVersionBytes.dropLast(1).toByteArray().toString(Charsets.US_ASCII)
    val semver = Regex("(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?")
    require(semver.matches(runtimeVersion) && semver.matches(values.getValue("codexAgent.contractVersion")) &&
        semver.matches(values.getValue("codexAgent.runtimeVersion"))) {
        "Contract and Runtime versions must be strict SemVer"
    }
    require(runtimeVersion == values.getValue("codexAgent.runtimeVersion")) {
        "Requested Runtime version does not match gradle/release/versions/runtime.txt"
    }
    val runtimeTargets = setOf(
        "macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64", "jvm", "node-js", "node-wasm",
    )
    require(values.getValue("codexAgent.target") in runtimeTargets) {
        "Unsupported standalone Desktop Runtime target: ${values.getValue("codexAgent.target")}"
    }
    val nativeRuntimeTargets = runtimeTargets - setOf("jvm", "node-js", "node-wasm")
    val requestedPhase = commandLineProperties["codexAgent.phase"]
    if (values.getValue("codexAgent.target") in nativeRuntimeTargets &&
        (requestedPhase == null || requestedPhase == "binary")) {
        val binaryProperties = listOf(
            "codexAgent.runtimeBinaryFlagsDigest",
            "codexAgent.runtimeBinaryPlan",
            "codexAgent.repositoryRevision",
        )
        binaryProperties.forEach { name ->
            require(System.getProperty("org.gradle.project.$name") == null &&
                System.getenv("ORG_GRADLE_PROJECT_$name") == null) {
                "$name must be supplied only as an explicit -P project property"
            }
            require(commandLineProperties[name]?.isNotBlank() == true) {
                "Missing mandatory explicit -P project property: $name"
            }
        }
        require(commandLineProperties["codexAgent.runtimeBinaryFlagsDigest"]
            ?.matches(Regex("sha256:[0-9a-f]{64}")) == true) {
            "Missing or invalid mandatory explicit -P project property: codexAgent.runtimeBinaryFlagsDigest"
        }
        require(commandLineProperties["codexAgent.repositoryRevision"]
            ?.matches(Regex("[0-9a-f]{40}|[0-9a-f]{64}")) == true) {
            "Missing or invalid mandatory explicit -P project property: codexAgent.repositoryRevision"
        }
        val binaryPlan = absoluteNormalizedPath("codexAgent.runtimeBinaryPlan")
        require(java.nio.file.Files.isRegularFile(binaryPlan, java.nio.file.LinkOption.NOFOLLOW_LINKS) &&
            !java.nio.file.Files.isSymbolicLink(binaryPlan) && binaryPlan.toRealPath() == binaryPlan) {
            "codexAgent.runtimeBinaryPlan must be a regular non-symbolic file"
        }
    }
    val repositoryRealPath = repositoryRoot.toRealPath()
    fun trustedRuntimeDirectory(relative: String): java.nio.file.Path {
        val path = repositoryRoot.resolve(relative).normalize()
        require(
            path.startsWith(repositoryRoot) &&
                java.nio.file.Files.isDirectory(path, java.nio.file.LinkOption.NOFOLLOW_LINKS) &&
                !java.nio.file.Files.isSymbolicLink(path) &&
                path.toRealPath().startsWith(repositoryRealPath),
        ) { "Standalone Runtime source directory is missing, symbolic, or escapes the repository: $relative" }
        java.nio.file.Files.walkFileTree(
            path,
            object : java.nio.file.SimpleFileVisitor<java.nio.file.Path>() {
                override fun preVisitDirectory(
                    directory: java.nio.file.Path,
                    attributes: java.nio.file.attribute.BasicFileAttributes,
                ): java.nio.file.FileVisitResult {
                    require(!attributes.isSymbolicLink && !java.nio.file.Files.isSymbolicLink(directory) &&
                        directory.toRealPath().startsWith(repositoryRealPath)) {
                        "Standalone Runtime source directory is missing, symbolic, or escapes the repository: $relative"
                    }
                    return if (directory != path && directory.fileName.toString() in setOf("build", ".gradle")) {
                        java.nio.file.FileVisitResult.SKIP_SUBTREE
                    } else {
                        java.nio.file.FileVisitResult.CONTINUE
                    }
                }

                override fun visitFile(
                    file: java.nio.file.Path,
                    attributes: java.nio.file.attribute.BasicFileAttributes,
                ): java.nio.file.FileVisitResult {
                    require(!attributes.isSymbolicLink && !java.nio.file.Files.isSymbolicLink(file) &&
                        file.toRealPath().startsWith(repositoryRealPath)) {
                        "Standalone Runtime source directory is missing, symbolic, or escapes the repository: $relative"
                    }
                    return java.nio.file.FileVisitResult.CONTINUE
                }
            },
        )
        return path
    }
    val runtimeBuildLogic = trustedRuntimeDirectory("runtime/build-logic")
    val desktopRuntimeSources = trustedRuntimeDirectory("codex-agent-runtime-desktop")

    val expectedTrustDomain = if (System.getenv("GITHUB_ACTIONS") == "true") "release" else "development"
    val verifiedContractParent = settingsDir.resolve(".gradle/verified-contracts").toPath()
    java.nio.file.Files.createDirectories(verifiedContractParent)
    require(java.nio.file.Files.isDirectory(verifiedContractParent, java.nio.file.LinkOption.NOFOLLOW_LINKS) &&
        !java.nio.file.Files.isSymbolicLink(verifiedContractParent) &&
        verifiedContractParent.toRealPath().startsWith(repositoryRealPath)) {
        "Standalone Runtime verified Contract directory is unsafe"
    }
    val verifiedContract = verifiedContractParent.resolve("contract-${java.util.UUID.randomUUID()}")
    val verifyCommand = mutableListOf(
        "python3", "-m", "ci.products.contract", "verify-directory",
        "--directory", contractManifest.parent.toString(),
        "--public-key", contractPublicKey.toString(),
        "--expected-trust-domain", expectedTrustDomain,
        "--expected-contract-version", values.getValue("codexAgent.contractVersion"),
        "--required-component", "common",
        "--required-component", values.getValue("codexAgent.target"),
        "--output-directory", verifiedContract.toString(),
        "--reuse-output-directory",
    )
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

    val verifiedContractManifest = verifiedContract.resolve("contract-manifest.json")
    require(java.nio.file.Files.isRegularFile(
        verifiedContractManifest,
        java.nio.file.LinkOption.NOFOLLOW_LINKS,
    ) && !java.nio.file.Files.isSymbolicLink(verifiedContractManifest)) {
        "Authenticated Contract snapshot is missing its manifest"
    }

    if (values.getValue("codexAgent.target") in nativeRuntimeTargets &&
        (requestedPhase == null || requestedPhase == "binary")) {
        val identityOutput = verifiedContract.resolve("runtime-binary-identity.json")
        val identityCommand = listOf(
            "python3", "-m", "ci.products.runtime_identity",
            "--plan", absoluteNormalizedPath("codexAgent.runtimeBinaryPlan").toString(),
            "--repository-root", repositoryRoot.toString(),
            "--repository-revision", commandLineProperties.getValue("codexAgent.repositoryRevision"),
            "--verified-contract-manifest", verifiedContractManifest.toString(),
            "--expected-target", values.getValue("codexAgent.target"),
            "--expected-runtime-version", values.getValue("codexAgent.runtimeVersion"),
            "--expected-flags-digest",
            commandLineProperties.getValue("codexAgent.runtimeBinaryFlagsDigest"),
            "--output", identityOutput.toString(),
        )
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
            commandLine(identityCommand)
        }.result.get().assertNormalExitValue()
    }

    settings.extensions.extraProperties.set("codexAgent.verifiedContractValues", values)
    settings.extensions.extraProperties.set("codexAgent.verifiedRepositoryRoot", repositoryRoot)
    settings.extensions.extraProperties.set("codexAgent.verifiedContractRepository", verifiedContract.resolve("maven"))
    settings.extensions.extraProperties.set("codexAgent.verifiedDesktopRuntimeSources", desktopRuntimeSources)
    gradle.beforeProject(org.gradle.api.Action<org.gradle.api.Project> {
        extensions.extraProperties.set(
            "codexAgent.verifiedContractManifest",
            verifiedContractManifest.toFile(),
        )
    })
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
    includeBuild(runtimeBuildLogic.toFile())
}

@Suppress("UNCHECKED_CAST")
val values = settings.extensions.extraProperties.get("codexAgent.verifiedContractValues") as Map<String, String>
val repositoryRoot = settings.extensions.extraProperties.get("codexAgent.verifiedRepositoryRoot") as java.nio.file.Path
val contractRepository =
    settings.extensions.extraProperties.get("codexAgent.verifiedContractRepository") as java.nio.file.Path

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        exclusiveContent {
            forRepository {
                maven {
                    name = "AUTHENTICATED_CONTRACT_BUNDLE"
                    url = uri(contractRepository)
                }
            }
            filter { includeGroup("io.github.codex-agent-labs") }
        }
        mavenCentral {
            content { excludeGroup("io.github.codex-agent-labs") }
        }
    }
    versionCatalogs {
        create("libs") { from(files(repositoryRoot.resolve("gradle/libs.versions.toml"))) }
    }
}

rootProject.name = "codex-agent-runtime"
include(":codex-agent-runtime-desktop")
project(":codex-agent-runtime-desktop").projectDir =
    (settings.extensions.extraProperties.get("codexAgent.verifiedDesktopRuntimeSources") as java.nio.file.Path).toFile()
