import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.BuildResult
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class RuntimeIsolationFixtureTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first {
            it.resolve("runtime/settings.gradle.kts").isFile &&
                it.resolve("codex-agent-runtime-desktop").isDirectory
        }
    private val runtimePythonClosure = setOf(
        "ci/impact.py",
        "ci/products/__main__.py",
        "ci/products/__init__.py",
        "ci/products/c_abi.py",
        "ci/products/contract.py",
        "ci/products/contract_model.py",
        "ci/products/inventory.py",
        "ci/products/receipt.py",
        "ci/products/runtime_evidence.py",
        "ci/products/signatures.py",
        "ci/products/test_results.py",
    )

    @Test
    fun `standalone Runtime verifies from an authenticated artifact-only Contract boundary`() {
        val workspace = createTempDirectory("runtime-isolation").toFile().canonicalFile
        try {
            val base = workspace.resolve("base")
            copyRuntimeClosure(base)
            assertIsolatedClosure(base)

            val signing = workspace.resolve("signing")
            val contract = workspace.resolve("contract")
            createSignedContract(signing, contract)
            val publicKey = signing.resolve("key/development-ed25519.pub")
            val privateKey = signing.resolve("key/development-ed25519")
            val wrongPublicKey = signing.resolve("wrong-key/development-ed25519.pub")
            val target = currentHostTarget()

            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "tampered-manifest",
                "canonical",
            ) { directory ->
                val manifest = directory.resolve("contract-manifest.json")
                manifest.writeBytes(manifest.readBytes().dropLast(1).toByteArray())
            }
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                wrongPublicKey,
                target,
                "wrong-key",
                "fingerprint mismatch",
            )
            val linkedKeyParent = workspace.resolve("linked-key-parent")
            java.nio.file.Files.createSymbolicLink(linkedKeyParent.toPath(), publicKey.parentFile.toPath())
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                linkedKeyParent.resolve(publicKey.name),
                target,
                "symlinked-key-parent",
                "unsafe directory",
            )
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "wrong-version",
                "expected Contract version",
                contractVersion = "0.2.1",
            )
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "wrong-target-component",
                "Contract component $target digest mismatch",
            ) { directory ->
                resignWithWrongTargetComponent(directory, privateKey, target)
            }
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "extra-contract-file",
                "complete allow-list",
            ) { directory ->
                directory.resolve("evidence/unlisted.json").writeText("{}\n")
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "missing-contract-file", "complete allow-list",
            ) { directory ->
                directory.resolve("evidence/canonical-api.json").delete()
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "empty-contract-file", "unsafe or empty entry",
            ) { directory ->
                directory.resolve("evidence/canonical-api.json").writeBytes(byteArrayOf())
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "symlink-contract-file", "unsafe",
            ) { directory ->
                val evidence = directory.resolve("evidence/canonical-api.json")
                val outside = workspace.resolve("outside-canonical-api.json").apply { writeText("{}\n") }
                evidence.delete()
                java.nio.file.Files.createSymbolicLink(evidence.toPath(), outside.toPath())
            }

            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "source-escape", "source directory is missing, symbolic, or escapes",
                mutateFixture = { fixture ->
                    val sources = fixture.resolve("codex-agent-runtime-desktop")
                    val outside = workspace.resolve("outside-runtime-sources")
                    copyTree(sources, outside)
                    sources.deleteRecursively()
                    java.nio.file.Files.createSymbolicLink(sources.toPath(), outside.toPath())
                },
            )
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "nested-source-escape", "source directory is missing, symbolic, or escapes",
                mutateFixture = { fixture ->
                    val sources = fixture.resolve("codex-agent-runtime-desktop/src/commonMain")
                    val outside = workspace.resolve("outside-common-main")
                    copyTree(sources, outside)
                    sources.deleteRecursively()
                    java.nio.file.Files.createSymbolicLink(sources.toPath(), outside.toPath())
                },
            )

            val includedBuild = workspace.resolve("substitution").apply {
                mkdirs()
                resolve("settings.gradle.kts").writeText("rootProject.name = \"substitution\"\n")
                resolve("build.gradle.kts").writeText("\n")
            }
            rejectedBeforeBuildLogic(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "include-build-substitution",
                "rejects command-line composite build substitutions",
                extraArguments = listOf("--include-build", includedBuild.absolutePath),
            )

            rejectedBeforeRuntimeCompilation(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "project-core-dependency",
                "Project with path ':codex-agent-core' could not be found",
            ) { fixture ->
                val build = fixture.resolve("codex-agent-runtime-desktop/build.gradle.kts")
                val original = build.readText()
                val mutated = original.replace(
                    "api(\"io.github.codex-agent-labs:codex-agent-core:\${providers.gradleProperty(\"codexAgent.contractVersion\").get()}\")",
                    "api(project(\":codex-agent-core\"))",
                )
                check(mutated != original) { "Runtime fixture Core dependency seam changed" }
                build.writeText(mutated)
            }
            rejectedBeforeRuntimeCompilation(
                workspace,
                base,
                contract,
                publicKey,
                target,
                "project-repository-fallback",
                "repositories over project repositories",
            ) { fixture ->
                fixture.resolve("codex-agent-runtime-desktop/build.gradle.kts")
                    .appendText("\nrepositories { mavenCentral() }\n")
            }

            val positive = workspace.resolve("positive")
            copyTree(base, positive)
            val positiveContract = positive.resolve("inputs/contract")
            val positiveKey = positive.resolve("inputs/development-ed25519.pub")
            createRealContract(positiveContract, positiveKey)
            val testKit = workspace.resolve("test-kit")
            val projects = runner(
                positive,
                positiveContract,
                positiveKey,
                target,
                testKit,
                "projects",
            ).build()
            assertAccepted(projects, ":projects")
            assertTrue("Project ':codex-agent-runtime-desktop'" in projects.output)
            val verifiedSnapshots = positive.resolve("runtime/.gradle/verified-contracts")
                .listFiles().orEmpty().map(File::getName).toSet()
            assertEquals(1, verifiedSnapshots.size)
            val reusedProjects = runner(
                positive,
                positiveContract,
                positiveKey,
                target,
                testKit,
                "projects",
            ).build()
            assertAccepted(reusedProjects, ":projects")
            assertTrue("Reusing configuration cache." in reusedProjects.output)
            assertEquals(
                verifiedSnapshots,
                positive.resolve("runtime/.gradle/verified-contracts")
                    .listFiles().orEmpty().map(File::getName).toSet(),
            )

            val canonicalApi = positiveContract.resolve("evidence/canonical-api.json")
            val canonicalApiBytes = canonicalApi.readBytes()
            try {
                canonicalApi.writeBytes(canonicalApiBytes + byteArrayOf(' '.code.toByte()))
                val rejectedContractMutation = runner(
                    positive, positiveContract, positiveKey, target, testKit, "projects",
                ).buildAndFail()
                assertTrue(
                    rejectedContractMutation.tasks.none { it.path.startsWith(":codex-agent-runtime-desktop:compile") },
                )
                val contractFailure = contractVerifierFailure(positiveContract, positiveKey, target, "0.2.0")
                assertTrue("declared file bytes or digest differ" in contractFailure, contractFailure)
            } finally {
                canonicalApi.writeBytes(canonicalApiBytes)
            }

            val publicKeyBytes = positiveKey.readBytes()
            try {
                val differentValidKey = publicKeyBytes.copyOf().also { key ->
                    val changedIndex = key.indexOfLast { it != '='.code.toByte() && it != '\n'.code.toByte() }
                    key[changedIndex] = if (key[changedIndex] == 'A'.code.toByte()) 'B'.code.toByte() else 'A'.code.toByte()
                }
                positiveKey.writeBytes(differentValidKey)
                val rejectedKeyMutation = runner(
                    positive, positiveContract, positiveKey, target, testKit, "projects",
                ).buildAndFail()
                assertTrue(
                    rejectedKeyMutation.tasks.none { it.path.startsWith(":codex-agent-runtime-desktop:compile") },
                )
                val keyFailure = contractVerifierFailure(positiveContract, positiveKey, target, "0.2.0")
                assertTrue("fingerprint mismatch" in keyFailure, keyFailure)
            } finally {
                positiveKey.writeBytes(publicKeyBytes)
            }

            val verification = runner(
                positive,
                positiveContract,
                positiveKey,
                target,
                testKit,
                "verifyRuntime",
                "0.2.0",
                mapOf(
                    "PYTHONPATH" to workspace.resolve("hostile-python").apply {
                        mkdirs()
                        resolve("sitecustomize.py").writeText(
                            "from pathlib import Path\nPath(r'${workspace.resolve("hostile-python-ran").absolutePath}').write_text('ran')\n",
                        )
                    }.absolutePath,
                    "PYTHONHOME" to workspace.resolve("hostile-python-home").absolutePath,
                    "PYTHONINSPECT" to "1",
                    "PYTHONSTARTUP" to workspace.resolve("hostile-startup.py").apply {
                        writeText("raise RuntimeError('hostile startup executed')\n")
                    }.absolutePath,
                ),
                "-PcodexAgent.product=runtime",
                "-PcodexAgent.component=$target",
                "-PcodexAgent.phase=metadata",
                "-PcodexAgent.candidateCommit=0123456789abcdef0123456789abcdef01234567",
                "-PcodexAgent.candidateTree=89abcdef0123456789abcdef0123456789abcdef",
            ).build()
            assertAccepted(verification, ":verifyRuntime")
            assertFalse(workspace.resolve("hostile-python-ran").exists(), "Hostile Python startup code executed")
        } finally {
            workspace.deleteRecursively()
        }
    }

    private fun rejectedBeforeBuildLogic(
        workspace: File,
        base: File,
        sourceContract: File,
        publicKey: File,
        target: String,
        name: String,
        expectedFailure: String,
        contractVersion: String = "0.2.0",
        extraArguments: List<String> = emptyList(),
        mutateFixture: (File) -> Unit = {},
        mutate: (File) -> Unit = {},
    ) {
        val fixture = workspace.resolve("negative-$name")
        copyTree(base, fixture)
        mutateFixture(fixture)
        val contract = workspace.resolve("negative-$name-contract")
        copyTree(sourceContract, contract)
        mutate(contract)
        val additionalArguments = extraArguments.toTypedArray()
        val result = runner(
            fixture,
            contract,
            publicKey,
            target,
            workspace.resolve("negative-test-kit"),
            "projects",
            contractVersion,
            emptyMap(),
            *additionalArguments,
        ).buildAndFail()
        if (expectedFailure !in result.output) {
            assertTrue(extraArguments.isEmpty(), "$name did not fail for the expected reason:\n${result.output}")
            val verifierFailure = contractVerifierFailure(contract, publicKey, target, contractVersion)
            assertTrue(
                expectedFailure in verifierFailure,
                "$name did not fail canonical verification for the expected reason:\n$verifierFailure",
            )
        }
        assertTrue(
            result.tasks.none { it.path.endsWith(":compileKotlin") || it.path.endsWith(":compileJava") },
            "$name compiled build logic before rejecting the Contract: ${result.tasks.map { it.path }}",
        )
        assertFalse(
            fixture.resolve("runtime/build-logic/build").exists(),
            "$name created standalone Runtime build-logic outputs before rejection",
        )
    }

    private fun rejectedBeforeRuntimeCompilation(
        workspace: File,
        base: File,
        sourceContract: File,
        publicKey: File,
        target: String,
        name: String,
        expectedFailure: String,
        mutateFixture: (File) -> Unit,
    ) {
        val fixture = workspace.resolve("negative-$name")
        copyTree(base, fixture)
        mutateFixture(fixture)
        val contract = workspace.resolve("negative-$name-contract")
        copyTree(sourceContract, contract)
        val result = runner(
            fixture,
            contract,
            publicKey,
            target,
            workspace.resolve("negative-test-kit"),
            "projects",
        ).buildAndFail()
        assertTrue(expectedFailure in result.output, "$name did not fail for the expected reason:\n${result.output}")
        assertTrue(
            result.tasks.none { it.path.startsWith(":codex-agent-runtime-desktop:compile") },
            "$name compiled Runtime source before rejection: ${result.tasks.map { it.path }}",
        )
    }

    private fun runner(
        fixture: File,
        contract: File,
        publicKey: File,
        target: String,
        testKit: File,
        task: String,
        contractVersion: String = "0.2.0",
        environmentOverrides: Map<String, String> = emptyMap(),
        vararg additionalArguments: String,
    ): GradleRunner {
        val arguments = mutableListOf(
            task,
            "-PcodexAgent.contractRepository=${contract.resolve("maven").absolutePath}",
            "-PcodexAgent.contractManifest=${contract.resolve("contract-manifest.json").absolutePath}",
            "-PcodexAgent.contractPublicKey=${publicKey.absolutePath}",
            "-PcodexAgent.contractVersion=$contractVersion",
            "-PcodexAgent.runtimeVersion=0.2.0",
            "-PcodexAgent.target=$target",
            "--configuration-cache",
            "--configuration-cache-problems=fail",
            "--stacktrace",
        )
        arguments += additionalArguments
        val environment = System.getenv().toMutableMap().apply {
            remove("GITHUB_ACTIONS")
            remove("PYTHONPATH")
            put("PYTHONDONTWRITEBYTECODE", "1")
            put("RUNNER_OS", runnerOs(target))
            put("RUNNER_ARCH", runnerArch(target))
            putAll(environmentOverrides)
        }
        return GradleRunner.create()
            .withProjectDir(fixture.resolve("runtime"))
            .withTestKitDir(testKit)
            .withEnvironment(environment)
            .withArguments(arguments)
    }

    private fun assertAccepted(result: BuildResult, task: String) {
        assertTrue(
            result.task(task)?.outcome in setOf(
                TaskOutcome.SUCCESS,
                TaskOutcome.FROM_CACHE,
                TaskOutcome.UP_TO_DATE,
            ),
            "$task did not complete successfully",
        )
    }

    private fun copyRuntimeClosure(fixture: File) {
        listOf(
            "runtime/settings.gradle.kts",
            "runtime/build.gradle.kts",
            "runtime/gradle.properties",
            "runtime/settings-gradle.lockfile",
            "runtime/gradle/verification-metadata.xml",
            "runtime/gradle/kotlin-js-store/package-lock.json",
            "runtime/gradle/kotlin-js-store/wasm/package-lock.json",
            "runtime/build-logic/settings.gradle.kts",
            "runtime/build-logic/settings-gradle.lockfile",
            "runtime/build-logic/build.gradle.kts",
            "runtime/build-logic/gradle.lockfile",
            "runtime/build-logic/gradle/verification-metadata.xml",
            "codex-agent-runtime-desktop/build.gradle.kts",
            "codex-agent-runtime-desktop/gradle.lockfile",
            "codex-agent-runtime-desktop/codex-app-server-distributions.json",
            "gradle/libs.versions.toml",
            "gradle/release/versions/runtime.txt",
            "legal/openai-codex/openai-codex-LICENSE.txt",
            "legal/openai-codex/openai-codex-NOTICE.txt",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ).forEach { copyFile(it, fixture) }
        listOf(
            "runtime/build-logic/src/main",
            "codex-agent-runtime-desktop/src",
            "codex-agent-runtime-desktop/native",
        ).forEach { copyDirectory(it, fixture) }
        runtimePythonClosure.sorted().forEach { copyFile(it, fixture) }
    }

    private fun assertIsolatedClosure(fixture: File) {
        listOf(
            "settings.gradle.kts",
            "build.gradle.kts",
            "gradle/build-logic",
            "codex-agent-core",
            "codex-agent-sdk",
            "codex-agent-bindings",
            "codex-agent-runtime-android",
            "codex-agent-runtime-ios",
        ).forEach { forbidden -> assertFalse(fixture.resolve(forbidden).exists(), forbidden) }
        assertFalse(
            fixture.resolve("gradle/product-build-support/src/main/kotlin").exists(),
            "Standalone Runtime fixture must not source executable root product-build-support Kotlin",
        )
        assertFalse(
            "../../gradle/product-build-support/src/main/kotlin" in
                fixture.resolve("runtime/build-logic/build.gradle.kts").readText(),
            "Standalone Runtime build logic must be dependency-closed",
        )
        val expectedBuildLogic = repository.resolve("runtime/build-logic/src/main").regularFiles()
        val copiedBuildLogic = fixture.resolve("runtime/build-logic/src/main").regularFiles()
        assertTrue(expectedBuildLogic == copiedBuildLogic, "Runtime build-logic closure differs: $copiedBuildLogic")
        assertEquals(
            runtimePythonClosure.mapTo(sortedSetOf()) { it.removePrefix("ci/") },
            fixture.resolve("ci").regularFiles().toSortedSet(),
            "Standalone Runtime Python closure differs",
        )
    }

    private fun createSignedContract(signing: File, extracted: File) {
        runPython(
            """
            import sys, zipfile
            from pathlib import Path
            from ci.products.contract import build_contract_bundle
            from ci.products.signatures import generate_development_key
            from ci.tests.test_contract_bundle import PRODUCER, VERSION, _write_staging
            root = Path(sys.argv[1]).resolve()
            extracted = Path(sys.argv[2]).resolve()
            private_key, public_key, metadata = generate_development_key(root / "key")
            generate_development_key(root / "wrong-key")
            staging = root / "staging"
            _write_staging(staging)
            archive = root / f"codex-agent-contract-{VERSION}.zip"
            build_contract_bundle(staging, archive, VERSION, PRODUCER, private_key, public_key, metadata)
            with zipfile.ZipFile(archive) as source:
                source.extractall(extracted)
            """.trimIndent(),
            signing.absolutePath,
            extracted.absolutePath,
        )
    }

    private fun createRealContract(extracted: File, publicKey: File) {
        val bundleRoot = repository.resolve("build/contract-product/bundle")
        val archive = bundleRoot.resolve("codex-agent-contract-0.2.0.zip")
        val sourceKey = bundleRoot.resolve("development-ed25519.pub")
        if (!archive.isFile || !sourceKey.isFile) {
            val process = ProcessBuilder(
                repository.resolve("gradlew").absolutePath,
                "assembleContractBundle",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            ).directory(repository).redirectErrorStream(true).start()
            val output = process.inputStream.bufferedReader().use { it.readText() }
            check(process.waitFor() == 0) { "Real Contract Bundle build failed:\n$output" }
        }
        runPython(
            """
            import sys, zipfile
            from pathlib import Path
            from ci.products.contract import verify_contract_bundle
            archive, public_key, output = map(lambda value: Path(value).resolve(), sys.argv[1:])
            verify_contract_bundle(archive, public_key, expected_trust_domain="development")
            with zipfile.ZipFile(archive) as source:
                source.extractall(output)
            """.trimIndent(),
            archive.canonicalPath,
            sourceKey.canonicalPath,
            extracted.canonicalPath,
        )
        publicKey.parentFile.mkdirs()
        sourceKey.copyTo(publicKey)
    }

    private fun resignWithWrongTargetComponent(contract: File, privateKey: File, target: String) {
        runPython(
            """
            import sys
            from pathlib import Path
            from ci.products.inventory import load_canonical_json, write_canonical_json
            from ci.products.signatures import sign_manifest
            root, private_key, target = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
            manifest_path = root / "contract-manifest.json"
            manifest = load_canonical_json(manifest_path)
            manifest["components"][target]["sha256"] = "sha256:" + "0" * 64
            write_canonical_json(manifest_path, manifest)
            (root / "contract-manifest.sig").unlink()
            sign_manifest(manifest_path, private_key, manifest["signing"])
            """.trimIndent(),
            contract.absolutePath,
            privateKey.absolutePath,
            target,
        )
    }

    private fun runPython(script: String, vararg arguments: String) {
        val process = ProcessBuilder(listOf("python3", "-c", script, *arguments))
            .directory(repository)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        check(process.waitFor() == 0) { "Contract fixture preparation failed:\n$output" }
    }

    private fun contractVerifierFailure(
        contract: File,
        publicKey: File,
        target: String,
        contractVersion: String,
    ): String {
        val process = ProcessBuilder(
            "python3", "-m", "ci.products.contract", "verify-directory",
            "--directory", contract.absolutePath,
            "--public-key", publicKey.absolutePath,
            "--expected-trust-domain", "development",
            "--expected-contract-version", contractVersion,
            "--required-component", "common",
            "--required-component", target,
        ).directory(repository).redirectErrorStream(true).start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        check(process.waitFor() != 0) { "Mutated Contract unexpectedly passed canonical verification" }
        return output
    }

    private fun currentHostTarget(): String {
        val os = System.getProperty("os.name").lowercase()
        val arch = System.getProperty("os.arch").lowercase()
        val arm = arch in setOf("aarch64", "arm64")
        return when {
            os.contains("mac") && arm -> "macos-arm64"
            os.contains("mac") -> "macos-x64"
            os.contains("linux") && arm -> "linux-arm64"
            os.contains("linux") -> "linux-x64"
            os.contains("windows") -> "windows-x64"
            else -> error("Unsupported standalone Runtime fixture host: $os/$arch")
        }
    }

    private fun runnerOs(target: String) = when {
        target.startsWith("macos-") -> "macOS"
        target.startsWith("linux-") -> "Linux"
        target == "windows-x64" -> "Windows"
        else -> error("Unsupported Runtime target: $target")
    }

    private fun runnerArch(target: String) = if (target.endsWith("arm64")) "ARM64" else "X64"

    private fun copyFile(path: String, fixture: File) {
        val source = repository.resolve(path)
        check(source.isFile && !java.nio.file.Files.isSymbolicLink(source.toPath())) { "Unsafe input: $path" }
        fixture.resolve(path).also { target ->
            target.parentFile.mkdirs()
            source.copyTo(target)
        }
    }

    private fun copyDirectory(path: String, fixture: File) =
        copyTree(repository.resolve(path), fixture.resolve(path))

    private fun copyTree(source: File, target: File) {
        check(source.isDirectory && !java.nio.file.Files.isSymbolicLink(source.toPath())) { "Unsafe tree: $source" }
        source.walkTopDown().forEach { entry ->
            check(!java.nio.file.Files.isSymbolicLink(entry.toPath())) { "Symlinked fixture input: $entry" }
            val destination = target.resolve(entry.relativeTo(source).path)
            if (entry.isDirectory) destination.mkdirs() else entry.copyTo(destination)
        }
    }

    private fun File.regularFiles(): Set<String> = walkTopDown()
        .filter(File::isFile)
        .map { it.relativeTo(this).invariantSeparatorsPath }
        .toSet()
}
