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
    private val currentContractVersion = repository.resolve("gradle/release/versions/contract.txt").readText().trim()
    private val currentRuntimeVersion = repository.resolve("gradle/release/versions/runtime.txt").readText().trim()
    private val runtimePythonClosure = setOf(
        "ci/impact.py",
        "ci/products/__main__.py",
        "ci/products/__init__.py",
        "ci/products/c_abi.py",
        "ci/products/contract.py",
        "ci/products/contract_attestation.py",
        "ci/products/contract_projection.py",
        "ci/products/contract_model.py",
        "ci/products/inventory.py",
        "ci/products/receipt.py",
        "ci/products/registry.py",
        "ci/products/runtime_evidence.py",
        "ci/products/runtime_flags.py",
        "ci/products/runtime_identity.py",
        "ci/products/selection.py",
        "ci/products/signatures.py",
        "ci/products/test_results.py",
        "ci/products/toolchain.py",
    )

    @Test
    fun `standalone Runtime rejects hostile Contract inputs before build logic`() {
        val workspace = createTempDirectory("runtime-isolation").toFile().canonicalFile
        try {
            val base = workspace.resolve("base")
            copyRuntimeClosure(base)
            assertIsolatedClosure(base)

            val signing = workspace.resolve("signing")
            val contract = workspace.resolve("contract")
            createSignedContract(signing, contract)
            val publicKey = signing.resolve("key/development-ed25519.pub")
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
                mutatePayload(directory, "truncate-manifest")
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
                mutatePayload(directory, "wrong-component", target)
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
                mutatePayload(directory, "extra")
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "missing-contract-file", "complete allow-list",
            ) { directory ->
                mutatePayload(directory, "missing")
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "empty-contract-file", "empty or truncated member",
            ) { directory ->
                mutatePayload(directory, "empty")
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "symlink-contract-file", "not canonical",
            ) { directory ->
                mutatePayload(directory, "symlink")
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "missing-execution-archive", "inventory",
            ) { directory ->
                check(directory.resolve("attestation/execution-closure/execution/contract-execution.zip").delete())
            }
            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "tampered-original-binary-receipt", "inventory",
            ) { directory ->
                directory.resolve("attestation/execution-closure/receipts/binary.json").appendText(" ")
            }

            rejectedBeforeBuildLogic(
                workspace, base, contract, publicKey, target,
                "source-escape", "source directory is missing, symbolic, or escapes",
                verifyContractOnMismatch = false,
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
                verifyContractOnMismatch = false,
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
        } finally {
            workspace.deleteRecursively()
        }
    }

    @Test
    fun `standalone Runtime authenticates genuine Contract and requires artifact-only Runtime predecessors`() {
        val workspace = createTempDirectory("runtime-isolation-genuine").toFile().canonicalFile
        try {
            val base = workspace.resolve("base")
            copyRuntimeClosure(base, currentRuntimeVersion)
            assertIsolatedClosure(base)
            val target = currentHostTarget()
            val positive = workspace.resolve("positive")
            copyTree(base, positive)
            val positiveContract = positive.resolve("inputs/contract")
            val positiveSigning = positive.resolve("inputs/signing")
            createRealContract(positiveSigning, positiveContract)
            val positiveKey = positiveSigning.resolve("key/development-ed25519.pub")
            val testKit = existingGradleUserHome()
            val projects = runner(
                positive,
                positiveContract,
                positiveKey,
                target,
                testKit,
                "projects",
                currentContractVersion,
            ).build()
            assertAccepted(projects, ":projects")
            assertTrue("Project ':codex-agent-runtime-desktop'" in projects.output)
            rejectedBeforeRuntimeCompilation(
                workspace,
                base,
                positiveContract,
                positiveKey,
                target,
                testKit,
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
                positiveContract,
                positiveKey,
                target,
                testKit,
                "project-repository-fallback",
                "repositories over project repositories",
            ) { fixture ->
                fixture.resolve("codex-agent-runtime-desktop/build.gradle.kts")
                    .appendText("\nrepositories { mavenCentral() }\n")
            }
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
                currentContractVersion,
            ).build()
            assertAccepted(reusedProjects, ":projects")
            assertTrue("Reusing configuration cache." in reusedProjects.output)
            assertEquals(
                verifiedSnapshots,
                positive.resolve("runtime/.gradle/verified-contracts")
                    .listFiles().orEmpty().map(File::getName).toSet(),
            )

            val payload = contractPayload(positiveContract)
            val payloadBytes = payload.readBytes()
            try {
                payload.writeBytes(payloadBytes + byteArrayOf(' '.code.toByte()))
                val rejectedContractMutation = runner(
                    positive, positiveContract, positiveKey, target, testKit, "projects", currentContractVersion,
                ).buildAndFail()
                assertTrue(
                    rejectedContractMutation.tasks.none { it.path.startsWith(":codex-agent-runtime-desktop:compile") },
                )
                val contractFailure = contractVerifierFailure(positiveContract, positiveKey, target, currentContractVersion)
                assertTrue("end-of-central-directory record is malformed" in contractFailure, contractFailure)
            } finally {
                payload.writeBytes(payloadBytes)
            }

            val publicKeyBytes = positiveKey.readBytes()
            try {
                val differentValidKey = publicKeyBytes.copyOf().also { key ->
                    val changedIndex = key.indexOfLast { it != '='.code.toByte() && it != '\n'.code.toByte() }
                    key[changedIndex] = if (key[changedIndex] == 'A'.code.toByte()) 'B'.code.toByte() else 'A'.code.toByte()
                }
                positiveKey.writeBytes(differentValidKey)
                val rejectedKeyMutation = runner(
                    positive, positiveContract, positiveKey, target, testKit, "projects", currentContractVersion,
                ).buildAndFail()
                assertTrue(
                    rejectedKeyMutation.tasks.none { it.path.startsWith(":codex-agent-runtime-desktop:compile") },
                )
                val keyFailure = contractVerifierFailure(positiveContract, positiveKey, target, currentContractVersion)
                assertTrue("fingerprint mismatch" in keyFailure, keyFailure)
            } finally {
                positiveKey.writeBytes(publicKeyBytes)
            }

            // No original native Runtime phase receipts/archives exist in this isolated fixture.
            // Prove metadata refuses missing explicit original inputs without compiling;
            // real variant acceptance remains an integration proof over finalized product stages.
            val verification = runner(
                positive,
                positiveContract,
                positiveKey,
                target,
                testKit,
                "verifyRuntime",
                currentContractVersion,
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
            ).buildAndFail()
            assertTrue(
                "Missing mandatory explicit -P project property: codexAgent.runtimeVariantIdentity" in verification.output,
                verification.output,
            )
            assertTrue(
                verification.tasks.none { task ->
                    val name = task.path.substringAfterLast(':')
                    task.path.startsWith(":codex-agent-runtime-desktop:") &&
                        (name.startsWith("compile") || name.startsWith("cinterop") ||
                            name.startsWith("link") || name == "verifyRuntimeProducerToolchain")
                },
                "Missing imported variant inputs reached Runtime compilation: ${verification.tasks.map { it.path }}",
            )
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
        verifyContractOnMismatch: Boolean = true,
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
            assertTrue(extraArguments.isEmpty() && verifyContractOnMismatch,
                "$name did not fail for the expected reason:\n${result.output}")
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
        testKit: File,
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
            testKit,
            "projects",
            currentContractVersion,
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
        // Configuration-only fixture calls never execute native compilation; the
        // real identity plan is exercised by GenerateRuntimeAbiSourceTask tests.
        val unusedBinaryPlan = fixture.resolve("inputs/runtime-binary-plan-unused.json").apply {
            parentFile.mkdirs()
            if (!exists()) writeText("{}\n")
        }
        val artifactBase = contractPayload(contract).name.removeSuffix(".zip")
        val arguments = mutableListOf(
            task,
            "--offline",
            "-PcodexAgent.contractPayload=${contractPayload(contract).absolutePath}",
            "-PcodexAgent.contractMetadataReceipt=${contract.resolve("phase-receipt.json").absolutePath}",
            "-PcodexAgent.contractAttestation=${contract.resolve("attestation/$artifactBase.attestation.json").absolutePath}",
            "-PcodexAgent.contractAttestationSignature=${contract.resolve("attestation/$artifactBase.attestation.sig").absolutePath}",
            "-PcodexAgent.contractPublicKey=${publicKey.absolutePath}",
            "-PcodexAgent.contractVersion=$contractVersion",
            "-PcodexAgent.runtimeVersion=${fixture.resolve("gradle/release/versions/runtime.txt").readText().trim()}",
            "-PcodexAgent.target=$target",
            "-PcodexAgent.runtimeBinaryFlagsDigest=${runtimeBinaryFlagsDigest(target)}",
            "-PcodexAgent.runtimeBinaryPlan=${unusedBinaryPlan.absolutePath}",
            "-PcodexAgent.repositoryRevision=${"0".repeat(40)}",
            "-PcodexAgent.phase=metadata",
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

    private fun existingGradleUserHome(): File {
        val configured = System.getProperty("gradle.user.home")
            ?.takeIf(String::isNotBlank)
            ?.let(::File)
            ?: File(System.getProperty("user.home"), ".gradle")
        return configured.canonicalFile.also {
            check(it.isDirectory) { "Existing offline Gradle user home is unavailable: $it" }
        }
    }

    private fun runtimeBinaryFlagsDigest(target: String): String = readRuntimeBinaryFlags(
        runRuntimeProductPythonModule(
            "runtime_flags",
            listOf(
                "describe-all",
                "--file",
                repository.resolve("codex-agent-runtime-desktop/native/c-api/binary-flags.json").absolutePath,
            ),
        ),
    ).getValue(target).flagsDigest

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

    private fun copyRuntimeClosure(fixture: File, runtimeVersion: String = "0.2.0") {
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
        // The copied release authority must match this isolated fixture's requested Runtime version.
        fixture.resolve("gradle/release/versions/runtime.txt").writeText("$runtimeVersion\n")
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
        val verificationMetadata = fixture.resolve("runtime/gradle/verification-metadata.xml").readText()
        listOf(
            "codex-agent-core",
            "codex-agent-core-js",
            "codex-agent-core-jvm",
            "codex-agent-core-linuxarm64",
            "codex-agent-core-linuxx64",
            "codex-agent-core-macosarm64",
            "codex-agent-core-macosx64",
            "codex-agent-core-mingwx64",
            "codex-agent-core-wasm-js",
        ).forEach { module ->
            assertTrue(
                "<trust group=\"io.github.codex-agent-labs\" name=\"$module\" " in verificationMetadata,
                "Authenticated Contract module is not narrowly trusted: $module",
            )
        }
        assertFalse(
            "<component group=\"io.github.codex-agent-labs\"" in verificationMetadata,
            "Authenticated Contract bytes must not be duplicated in static dependency checksums",
        )
    }

    private fun createSignedContract(signing: File, contract: File) {
        runPython(
            """
            import shutil, sys
            from pathlib import Path
            from ci.products.contract_attestation import build_contract_attestation, capture_contract_execution_closure
            from ci.products.signatures import generate_development_key
            from ci.tests.test_contract_execution_closure import execution_closure_fixture
            root, contract = map(lambda value: Path(value).resolve(), sys.argv[1:])
            contract.mkdir(parents=True)
            private_key, public_key, metadata = generate_development_key(root / "key")
            generate_development_key(root / "wrong-key")
            original_payload, receipts, archive = execution_closure_fixture(root / "synthetic-source")
            payload = contract / original_payload.name
            receipt = contract / "phase-receipt.json"
            shutil.copyfile(original_payload, payload)
            shutil.copyfile(receipts["metadata"], receipt)
            closure = root / "execution-closure"
            capture_contract_execution_closure(payload, receipts, archive, closure)
            build_contract_attestation(
                payload, receipt, metadata, private_key, public_key, contract / "attestation",
                execution_closure=closure,
            )
            """.trimIndent(),
            signing.absolutePath,
            contract.absolutePath,
        )
    }

    private fun createRealContract(signing: File, contract: File) {
        val source = System.getenv("CODEX_AGENT_RUNTIME_TEST_CONTRACT_INPUT")
            ?.takeIf(String::isNotBlank)?.let(::File)
        check(source != null && source.isDirectory) {
            "Runtime isolation requires CODEX_AGENT_RUNTIME_TEST_CONTRACT_INPUT containing an existing " +
                "codex-agent-contract-$currentContractVersion.zip and execution-closure/ with all four original receipts and " +
                "raw execution evidence; it never builds or repairs Contract inputs"
        }
        runPython(
            """
            import sys
            from pathlib import Path
            from ci.products.contract_attestation import build_contract_attestation
            from ci.products.inventory import read_regular_file_bytes, snapshot_regular_tree
            from ci.products.signatures import generate_development_key
            source, root, contract = map(lambda value: Path(value).resolve(), sys.argv[1:4])
            version = sys.argv[4]
            contract.mkdir(parents=True)
            payload = contract / f"codex-agent-contract-{version}.zip"
            payload.write_bytes(read_regular_file_bytes(source / payload.name, reject_symlink_parents=True))
            closure = root / "execution-closure"
            snapshot_regular_tree(source / "execution-closure", closure)
            receipt = contract / "phase-receipt.json"
            receipt.write_bytes(read_regular_file_bytes(closure / "receipts/metadata.json", reject_symlink_parents=True))
            private_key, public_key, metadata = generate_development_key(root / "key")
            build_contract_attestation(
                payload, receipt, metadata, private_key, public_key, contract / "attestation",
                execution_closure=closure,
            )
            """.trimIndent(),
            source.absolutePath,
            signing.absolutePath,
            contract.absolutePath,
            currentContractVersion,
        )
    }

    private fun mutatePayload(contract: File, mutation: String, target: String = "") {
        runPython(
            """
            import json, stat, sys
            from pathlib import Path
            from ci.products.inventory import canonical_json_bytes
            from ci.tests.test_contract_bundle import ARCHIVE_NAME, _write_zip, _zip_entries
            contract, mutation, target = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
            archive = contract / ARCHIVE_NAME
            entries = _zip_entries(archive)
            if mutation == "missing":
                entries = [entry for entry in entries if entry[0] != "evidence/canonical-api.json"]
            elif mutation == "extra":
                entries.append(("evidence/unlisted.json", b"{}\n", (stat.S_IFREG | 0o644) << 16))
            elif mutation == "empty":
                entries = [(path, b"" if path == "evidence/canonical-api.json" else contents, mode)
                           for path, contents, mode in entries]
            elif mutation == "symlink":
                entries = [(path, contents, (stat.S_IFLNK | 0o777) << 16)
                           if path == "evidence/canonical-api.json" else (path, contents, mode)
                           for path, contents, mode in entries]
            else:
                manifest = json.loads(next(contents for path, contents, _ in entries
                                           if path == "contract-manifest.json"))
                if mutation == "wrong-component":
                    manifest["components"][target]["sha256"] = "sha256:" + "0" * 64
                    replacement = canonical_json_bytes(manifest)
                elif mutation == "truncate-manifest":
                    replacement = canonical_json_bytes(manifest)[:-1]
                else:
                    raise ValueError(f"unknown mutation: {mutation}")
                entries = [(path, replacement if path == "contract-manifest.json" else contents, mode)
                           for path, contents, mode in entries]
            _write_zip(archive, sorted(entries, key=lambda entry: entry[0]))
            """.trimIndent(),
            contract.absolutePath,
            mutation,
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

    private fun contractPayload(contract: File): File {
        val payloads = contract.listFiles().orEmpty().filter {
            it.name.startsWith("codex-agent-contract-") && it.name.endsWith(".zip")
        }
        check(payloads.size == 1) { "Runtime isolation requires exactly one Contract payload" }
        return payloads.single()
    }

    private fun contractVerifierFailure(
        contract: File,
        publicKey: File,
        target: String,
        contractVersion: String,
    ): String {
        val outputDirectory = contract.parentFile.resolve("verifier-${System.nanoTime()}")
        val artifactBase = contractPayload(contract).name.removeSuffix(".zip")
        val process = ProcessBuilder(
            "python3", "-m", "ci.products.contract_attestation", "materialize",
            "--payload", contractPayload(contract).absolutePath,
            "--metadata-receipt", contract.resolve("phase-receipt.json").absolutePath,
            "--attestation", contract.resolve(
                "attestation/$artifactBase.attestation.json",
            ).absolutePath,
            "--signature", contract.resolve(
                "attestation/$artifactBase.attestation.sig",
            ).absolutePath,
            "--public-key", publicKey.absolutePath,
            "--required-trust-domain", "development",
            "--expected-contract-version", contractVersion,
            "--required-component", "common",
            "--required-component", target,
            "--output-directory", outputDirectory.absolutePath,
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
