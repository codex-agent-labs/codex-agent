import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class CrossLanguageNativeWrapperBindingEvidenceTest {
    private val releaseToolingJar = File(checkNotNull(System.getProperty("codexAgent.releaseToolingJar")))

    @Test
    fun `derives an exact universal receipt from compiler and executed evidence`() = withFixture { fixture ->
        val receipt = deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input())

        assertEquals(CrossLanguageBindingPhase.M9_CSHARP, receipt.phase)
        assertEquals(CrossLanguageBinding.CSHARP, receipt.language)
        assertEquals(fixture.members, receipt.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey))
        assertEquals(listOf("CSharp.Owner.First", "CSharp.Owner.Second"), receipt.publicSymbols)
        assertEquals(14, receipt.scenarioEvidence.size)
        assertTrue(receipt.scenarioEvidence.all { it.testIds == listOf("csharp.test.first", "csharp.test.second") })
        assertEquals(15, receipt.artifacts.size)
        assertEquals(
            listOf("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"),
            receipt.hostConsumerProofs.map(CrossLanguageBindingHostConsumerProof::classifier),
        )
        assertTrue(receipt.hostConsumerProofs.all {
            it.candidateCommit == fixture.candidateCommit && it.candidateTree == fixture.candidateTree
        })
        writeCrossLanguageBindingReceipt(fixture.receipt, receipt)
        assertEquals(receipt.toJson(), readCrossLanguageBindingReceipt(fixture.receipt).toJson())
    }

    @Test
    fun `cacheable task writes the receipt from an exact package directory`() = withFixture { fixture ->
        val task = ProjectBuilder.builder().withProjectDir(fixture.root).build().tasks.register(
            "nativeWrapperReceipt",
            GenerateCrossLanguageNativeWrapperBindingReceiptTask::class.java,
        ).get()
        task.phase.set(CrossLanguageBindingPhase.M9_CSHARP.name)
        task.language.set(CrossLanguageBinding.CSHARP.id)
        task.apiReport.set(fixture.input().apiReport)
        task.canonicalCoverageReceipt.set(fixture.input().canonicalCoverageReceipt)
        task.cAbiBootstrapEvidence.set(fixture.bootstrap)
        task.claims.set(fixture.claims)
        task.compilerEvidence.set(fixture.compiler)
        task.testProgram.set(fixture.program)
        task.testResults.set(fixture.results)
        task.packageArtifacts.set(fixture.packageDirectory)
        task.hostEvidenceDirectory.set(fixture.hostEvidenceDirectory)
        task.stagedCAbiSdks.set(fixture.stagedCAbiSdks)
        task.receipt.set(fixture.receipt)

        task.generate()

        assertEquals(CrossLanguageBinding.CSHARP, readCrossLanguageBindingReceipt(fixture.receipt).language)
    }

    @Test
    fun `aggregate clears every stale receipt and reports every missing language input`() {
        val root = createTempDirectory("native-wrapper-preflight").toFile()
        try {
            NodeRuntimeEvidenceFixture(root)
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"native-wrapper-preflight\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                plugins {
                    id("org.jetbrains.kotlin.multiplatform")
                    id("maven-publish")
                    id("codexagent.desktop-runtime")
                }
                group = "io.github.codex-agent-labs"
                version = "0.2.0"
                """.trimIndent(),
            )
            val languages = listOf("python", "csharp", "rust", "cpp", "dart")
            val receipts = languages.map { language ->
                root.resolve("build/reports/cross-language-api/bindings/$language-parity.json").apply {
                    parentFile.mkdirs()
                    writeText("stale passed receipt")
                }
            }

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withPluginClasspath()
                .withArguments("verifyNativeWrapperBindingParity", "--continue", "--stacktrace")
                .buildAndFail()

            assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":invalidateNativeWrapperBindingParityOutputs")?.outcome,
                result.output,
            )
            listOf("Python", "CSharp", "Rust", "Cpp", "Dart").forEach { language ->
                assertEquals(TaskOutcome.FAILED, result.task(":verify${language}BindingParity")?.outcome, result.output)
            }
            assertTrue(result.task(":verifyNativeWrapperBindingParity")?.outcome != TaskOutcome.SUCCESS)
            assertTrue(receipts.none(File::exists))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged CLI writes the same receipt and rejects stale evidence without Gradle`() =
        withFixture { fixture ->
            val arguments = arrayOf(
                "assemble-native-wrapper-binding-receipt",
                "--phase", CrossLanguageBindingPhase.M9_CSHARP.name,
                "--language", CrossLanguageBinding.CSHARP.id,
                "--api-report", fixture.input().apiReport.absolutePath,
                "--coverage-receipt", fixture.input().canonicalCoverageReceipt.absolutePath,
                "--c-abi-bootstrap", fixture.bootstrap.absolutePath,
                "--claims", fixture.claims.absolutePath,
                "--compiler-evidence", fixture.compiler.absolutePath,
                "--test-program", fixture.program.absolutePath,
                "--test-results", fixture.results.absolutePath,
                "--packages", fixture.packageDirectory.absolutePath,
                "--host-evidence", fixture.hostEvidenceDirectory.absolutePath,
                "--staged-c-abi-sdks", fixture.stagedCAbiSdks.absolutePath,
                "--output", fixture.receipt.absolutePath,
            )

            val passed = runReleaseTool(fixture.root, *arguments)
            assertEquals(0, passed.first, passed.second)
            assertEquals(
                deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input()).toJson(),
                readCrossLanguageBindingReceipt(fixture.receipt).toJson(),
            )

            val carried = fixture.root.resolve("carried.json")
            val advanced = runReleaseTool(
                fixture.root,
                "advance-cross-language-binding-receipt",
                "--phase", CrossLanguageBindingPhase.M9_RUST.name,
                "--source", fixture.receipt.absolutePath,
                "--output", carried.absolutePath,
            )
            assertEquals(0, advanced.first, advanced.second)
            assertEquals(CrossLanguageBindingPhase.M9_RUST, readCrossLanguageBindingReceipt(carried).phase)

            fixture.claims.writeText(fixture.claims.readText().replace(fixture.members.last(), "stale-capability"))
            val rejected = runReleaseTool(fixture.root, *arguments)
            assertTrue(rejected.first != 0, rejected.second)
            assertTrue("wrapper claims do not exactly match" in rejected.second, rejected.second)
            assertFalse(fixture.receipt.exists())
        }

    @Test
    fun `carries an exact earlier receipt into a later active phase without changing evidence`() =
        withFixture { fixture ->
            writeCrossLanguageBindingReceipt(
                fixture.receipt,
                deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input()),
            )
            val carried = fixture.root.resolve("carried.json")

            val advanced = advanceCrossLanguageBindingReceiptPhase(
                fixture.receipt,
                CrossLanguageBindingPhase.M9_RUST,
                carried,
            )

            assertEquals(CrossLanguageBindingPhase.M9_RUST, advanced.phase)
            assertEquals(
                readCrossLanguageBindingReceipt(fixture.receipt).copy(phase = CrossLanguageBindingPhase.M9_RUST),
                advanced,
            )
            assertFailsWith<IllegalStateException> {
                advanceCrossLanguageBindingReceiptPhase(
                    carried,
                    CrossLanguageBindingPhase.M9_PYTHON,
                    fixture.root.resolve("downgraded.json"),
                )
            }
            assertFailsWith<IllegalStateException> {
                advanceCrossLanguageBindingReceiptPhase(carried, CrossLanguageBindingPhase.M11, carried)
            }
        }

    @Test
    fun `rejects stale missing duplicate unexecuted uncompiled and incomplete scenario evidence`() =
        withFixture { fixture ->
            assertFailsWith<IllegalStateException> {
                deriveCrossLanguageNativeWrapperBindingReceipt(
                    fixture.input().copy(language = CrossLanguageBinding.C_ABI),
                )
            }
            assertFailsWith<IllegalStateException> {
                deriveCrossLanguageNativeWrapperBindingReceipt(
                    fixture.input().copy(phase = CrossLanguageBindingPhase.M9_PYTHON),
                )
            }
            val validClaims = fixture.claims.readText()
            val validCompiler = fixture.compiler.readText()
            val validTests = fixture.results.readText()
            val corruptions = listOf<() -> Unit>(
                { fixture.claims.writeText(validClaims.replace(fixture.members.last(), "stale-capability")) },
                { fixture.claims.writeText(validClaims.trimEnd().lines().dropLast(1).joinToString("\n", postfix = "\n")) },
                { fixture.claims.writeText(validClaims + validClaims.lineSequence().drop(1).first() + "\n") },
                { fixture.compiler.writeText(validCompiler.replace("CSharp.Owner.Second", "CSharp.Owner.Stale")) },
                { fixture.results.writeText(validTests.replace("csharp.test.second\tpassed", "csharp.test.second\tfailed")) },
                { fixture.claims.writeText(validClaims.replace(",value-conversion", "")) },
                { fixture.compiler.writeText(validCompiler + "compiler.extra\tCSharp.Owner.Extra\n") },
                { fixture.results.writeText(validTests + "csharp.test.extra\tpassed\n") },
                {
                    fixture.claims.writeText(validClaims.replace("cabi-fixture:canonical.second", "cabi-fixture:stale"))
                    fixture.compiler.writeText(validCompiler.replace("cabi-fixture:canonical.second", "cabi-fixture:stale"))
                },
                { fixture.writeBootstrap(failedTest = "canonical.second") },
            )
            corruptions.forEach { corrupt ->
                fixture.restore()
                corrupt()
                assertFailsWith<IllegalStateException> {
                    deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input())
                }
            }
        }

    @Test
    fun `parsers reject noncanonical rows wildcards unknown scenarios and unsafe files`() = withFixture { fixture ->
        val valid = fixture.claims.readText()
        listOf(
            valid.removeSuffix("\n"),
            valid.replace("\n", "\r\n"),
            valid.replace("CSharp.Owner.First", "CSharp.*"),
            valid.replace("async-success", "unknown-scenario"),
            valid.replace("csharp.test.first", "csharp.test.first,csharp.test.first"),
        ).forEach { contents ->
            fixture.claims.writeText(contents)
            assertFailsWith<IllegalStateException> { readCrossLanguageNativeWrapperClaims(fixture.claims) }
        }
        fixture.restore()
        val link = fixture.root.resolve("claims-link.tsv")
        java.nio.file.Files.createSymbolicLink(link.toPath(), fixture.claims.toPath())
        assertFailsWith<IllegalStateException> { readCrossLanguageNativeWrapperClaims(link) }
        fixture.packageArtifact.writeText("")
        assertFailsWith<IllegalStateException> {
            deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input())
        }
    }

    @Test
    fun `rejects incomplete stale mismatched or unsafe five-host evidence`() = withFixture { fixture ->
        val classifier = "linux-x64"
        val host = fixture.hostEvidenceDirectory.resolve("$classifier.tsv")
        val lane = fixture.hostEvidenceDirectory.resolve("$classifier-lane-receipt.json")
        val validHost = host.readText()
        val validLane = lane.readText()
        val corruptions = listOf<() -> Unit>(
            { host.delete() },
            { host.writeText(validHost.replace("\tpassed\n", "\tfailed\n")) },
            { host.writeText(validHost.replace(fixture.packageArtifact.releaseDigest(), "0".repeat(64))) },
            { host.writeText(validHost.replace(fixture.nativeLibrarySha256(classifier), "1".repeat(64))) },
            { lane.writeText(validLane.replace("\"arch\": \"X64\"", "\"arch\": \"ARM64\"")) },
            { lane.writeText(validLane.replace("\"dotnet\": \"fixture-dotnet\"", "\"dotnet\": \"unavailable\"")) },
            { lane.writeText(validLane.replace(fixture.candidateTree, "2".repeat(40))) },
            { lane.writeText(validLane.replace("cross-language-host-consumer", "stale-kind")) },
            { fixture.stagedCAbiSdks.resolve(classifier).resolve("lib/libcodex_agent.so").writeText("stale") },
        )
        corruptions.forEach { corrupt ->
            fixture.restore()
            corrupt()
            assertFailsWith<IllegalStateException> {
                deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input())
            }
        }
        fixture.restore()
        val link = fixture.root.resolve("host-link")
        java.nio.file.Files.createSymbolicLink(link.toPath(), fixture.hostEvidenceDirectory.toPath())
        assertFailsWith<IllegalStateException> {
            deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input().copy(hostEvidenceDirectory = link))
        }
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("native-wrapper-evidence").toFile()
        try {
            block(Fixture(root))
        } finally {
            root.deleteRecursively()
        }
    }

    private fun runReleaseTool(directory: File, vararg arguments: String): Pair<Int, String> {
        val java = File(System.getProperty("java.home"), "bin/java")
        val process = ProcessBuilder(java.absolutePath, "-jar", releaseToolingJar.absolutePath, *arguments)
            .directory(directory)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        return process.waitFor() to output
    }

    private class Fixture(val root: File) {
        private val canonical = CrossLanguageBindingCliFixture(root.resolve("canonical"))
        val members = canonical.members.sorted()
        val claims = root.resolve("claims.tsv")
        val compiler = root.resolve("compiler.tsv")
        val bootstrap = root.resolve("bootstrap.json")
        val program = root.resolve("tests.bin")
        val results = root.resolve("results.tsv")
        val packageDirectory = root.resolve("packages")
        val packageArtifact = packageDirectory.resolve("package.nupkg")
        val hostEvidenceDirectory = root.resolve("host-evidence")
        val stagedCAbiSdks = root.resolve("staged-c-abi-sdks")
        val receipt = root.resolve("csharp-parity.json")
        val candidateCommit = "c".repeat(40)
        val candidateTree = "d".repeat(40)
        private val scenarios = CrossLanguageBindingScenario.entries.map(CrossLanguageBindingScenario::id)
            .sorted().joinToString(",")

        init {
            program.writeText("compiled test program")
            packageDirectory.mkdirs()
            packageArtifact.writeText("package")
            restore()
        }

        fun restore() {
            claims.writeText(
                NATIVE_WRAPPER_CLAIM_HEADER + "\n" +
                    "${members[0]}\tCSharp.Owner.First\tcsharp.test.first\tc-header:codex_agent_first,cabi-fixture:canonical.first\t$scenarios\n" +
                    "${members[1]}\tCSharp.Owner.Second\tcsharp.test.second\tc-header:codex_agent_second,cabi-fixture:canonical.second\t$scenarios\n",
            )
            compiler.writeText(
                NATIVE_WRAPPER_COMPILER_HEADER + "\n" +
                    "c-header:codex_agent_first\tCSharp.Owner.First\n" +
                    "c-header:codex_agent_second\tCSharp.Owner.Second\n" +
                    "cabi-fixture:canonical.first\tCSharp.Owner.First\n" +
                    "cabi-fixture:canonical.second\tCSharp.Owner.Second\n",
            )
            results.writeText(
                NATIVE_WRAPPER_TEST_HEADER + "\n" +
                    "csharp.test.first\tpassed\n" +
                    "csharp.test.second\tpassed\n",
            )
            writeBootstrap()
            writeStagedCAbiSdks()
            writeHostEvidence()
        }

        fun nativeLibrarySha256(classifier: String): String {
            val spec = crossLanguageCAbiTargetSpecs.values.single {
                it.classifier.removePrefix("c-abi-") == classifier
            }
            return stagedCAbiSdks.resolve(classifier).resolve(spec.libraryPath).releaseDigest()
        }

        private fun writeStagedCAbiSdks() {
            stagedCAbiSdks.deleteRecursively()
            val targets = buildJsonArray {
                crossLanguageCAbiTargetSpecs.toSortedMap().forEach { (target, spec) ->
                    val classifier = spec.classifier.removePrefix("c-abi-")
                    val targetRoot = stagedCAbiSdks.resolve(classifier)
                    val library = targetRoot.resolve(spec.libraryPath).also { it.parentFile.mkdirs() }
                    val manifest = targetRoot.resolve("codex-agent-c-abi-manifest.json")
                    val evidence = targetRoot.resolve("codex-agent-c-abi-evidence.json")
                    library.writeText("native-$classifier")
                    targetRoot.resolve("include/codex_agent.h").apply {
                        parentFile.mkdirs()
                        writeText("header-$classifier")
                    }
                    targetRoot.resolve("LICENSE.txt").writeText("license-$classifier")
                    targetRoot.resolve("THIRD_PARTY_NOTICES.md").writeText("notice-$classifier")
                    if (spec.format == "elf") {
                        targetRoot.resolve("lib/${spec.loaderIdentity}").writeText("native-$classifier")
                    }
                    spec.importLibraryPaths.forEach { path ->
                        targetRoot.resolve(path).apply {
                            parentFile.mkdirs()
                            writeText("import-$classifier-$path")
                        }
                    }
                    manifest.writeText("manifest-$classifier")
                    evidence.writeText("evidence-$classifier")
                    add(buildJsonObject {
                        put("target", JsonPrimitive(target))
                        put("classifier", JsonPrimitive(classifier))
                        put("archiveSha256", JsonPrimitive("a".repeat(64)))
                        put("evidenceSha256", JsonPrimitive(evidence.releaseDigest()))
                        put("libraryPath", JsonPrimitive(spec.libraryPath))
                        put("librarySha256", JsonPrimitive(library.releaseDigest()))
                        put("manifestSha256", JsonPrimitive(manifest.releaseDigest()))
                    })
                }
            }
            stagedCAbiSdks.resolve("codex-agent-native-wrapper-sdks.json").atomicWriteJson(buildJsonObject {
                put("schemaVersion", JsonPrimitive(1))
                put("libraryVersion", JsonPrimitive("1.0.0"))
                put("producerCommit", JsonPrimitive(candidateCommit))
                put("producerTree", JsonPrimitive(candidateTree))
                put("targets", targets)
            })
        }

        private fun writeHostEvidence() {
            hostEvidenceDirectory.deleteRecursively()
            hostEvidenceDirectory.mkdirs()
            val packageId = "csharp-package/package.nupkg"
            val packageSha256 = packageArtifact.releaseDigest()
            crossLanguageCAbiTargetSpecs.values.sortedBy { it.classifier }.forEach { spec ->
                val classifier = spec.classifier.removePrefix("c-abi-")
                val host = hostEvidenceDirectory.resolve("$classifier.tsv")
                val testId = "csharp.host.$classifier.consumer"
                host.writeText(
                    NATIVE_WRAPPER_HOST_CONSUMER_HEADER + "\n" +
                        "$classifier\t$packageId\t$packageSha256\t${nativeLibrarySha256(classifier)}\t$testId\tpassed\n",
                )
                hostEvidenceDirectory.resolve("$classifier-lane-receipt.json").atomicWriteJson(buildJsonObject {
                    put("schemaVersion", JsonPrimitive(2))
                    put("repository", JsonPrimitive("codex-agent-labs/codex-agent"))
                    put("workflowPath", JsonPrimitive(".github/workflows/ci.yml"))
                    put("event", JsonPrimitive("pull_request"))
                    put("runId", JsonPrimitive(1))
                    put("runAttempt", JsonPrimitive(1))
                    put("pullRequest", JsonPrimitive(31))
                    put("baseCommit", JsonPrimitive("b".repeat(40)))
                    put("headCommit", JsonPrimitive(candidateCommit))
                    put("validationCommit", JsonPrimitive(candidateCommit))
                    put("validationTree", JsonPrimitive(candidateTree))
                    put("lane", JsonPrimitive("desktop-$classifier"))
                    put("artifactName", JsonPrimitive("codex-agent-ci-desktop-$classifier-$candidateTree"))
                    put("runner", buildJsonObject {
                        put("os", JsonPrimitive(spec.runnerOs))
                        put("arch", JsonPrimitive(spec.runnerArch))
                        put("image", JsonPrimitive("fixture-image"))
                        put("imageVersion", JsonPrimitive("fixture-version"))
                    })
                    put("toolchain", buildJsonObject {
                        put("dotnet", JsonPrimitive("fixture-dotnet"))
                        put("validationActions", JsonPrimitive("build,test"))
                    })
                    put("inputFiles", buildJsonObject {
                        put("production", JsonPrimitive("production-inputs.git-tree"))
                        put("test", JsonPrimitive("test-inputs.git-tree"))
                        put("metadata", JsonPrimitive("metadata-inputs.git-tree"))
                    })
                    put("artifacts", buildJsonArray {
                        add(buildJsonObject {
                            put("relativePath", JsonPrimitive(packageArtifact.name))
                            put("kind", JsonPrimitive("native-wrapper-package"))
                            put("bytes", JsonPrimitive(packageArtifact.length()))
                            put("sha256", JsonPrimitive(packageSha256))
                        })
                    })
                    put("evidence", buildJsonArray {
                        add(buildJsonObject {
                            put("relativePath", JsonPrimitive(host.name))
                            put("kind", JsonPrimitive("cross-language-host-consumer"))
                            put("sha256", JsonPrimitive(host.releaseDigest()))
                        })
                    })
                    put("result", JsonPrimitive("passed"))
                })
            }
        }

        fun writeBootstrap(failedTest: String? = null) {
            val tests = listOf("canonical.first", "canonical.second")
            bootstrap.atomicWriteJson(buildJsonObject {
                put("schemaVersion", JsonPrimitive(C_ABI_BOOTSTRAP_SCHEMA))
                put("protocol", JsonPrimitive(C_ABI_BOOTSTRAP_PROTOCOL))
                put("result", JsonPrimitive("observed"))
                put("milestone", JsonPrimitive("D104"))
                put("language", JsonPrimitive("c-abi"))
                put("canonical", buildJsonObject {
                    put("apiReportSha256", JsonPrimitive(canonical.apiReport.releaseDigest()))
                    put("coverageReceiptSha256", JsonPrimitive(canonical.coverageReceipt.releaseDigest()))
                    put("nativeTargetSha256", JsonPrimitive("a".repeat(64)))
                    put("capabilityCount", JsonPrimitive(members.size))
                    put("observedCapabilityCount", JsonPrimitive(members.size))
                    put("observedCapabilitySha256", JsonPrimitive(crossLanguageCAbiCapabilitySha256(members)))
                    put("observedCapabilityKeys", JsonArray(members.map(::JsonPrimitive)))
                    put("missingCapabilityKeys", JsonArray(emptyList()))
                })
                put("toolchain", buildJsonObject {
                    put("clang", JsonPrimitive("/usr/bin/clang"))
                    put("clangCpp", JsonPrimitive("/usr/bin/clang++"))
                    put("clangVersion", JsonPrimitive("clang fixture\nTarget: fixture"))
                    put("macosSdk", JsonPrimitive("/sdk"))
                })
                put("artifacts", buildJsonObject {
                    listOf(
                        "reviewedHeaderSha256", "cinteropDefinitionSha256", "exportPolicySha256",
                        "generatedHeaderSha256", "releaseLibrarySha256", "nativeTestExecutableSha256",
                        "nativeMainSourcesSha256", "nativeTestSourcesSha256", "nativeTestResultsSha256",
                    ).forEachIndexed { index, name -> put(name, JsonPrimitive(index.toString().repeat(64))) }
                    put("fileIdentity", JsonPrimitive("fixture-library"))
                    put("installName", JsonPrimitive("@rpath/libfixture.dylib"))
                })
                put("compilerConsumers", buildJsonArray {
                    add(buildJsonObject {
                        put("id", JsonPrimitive("fixture-consumer"))
                        put("sourceSha256", JsonPrimitive("b".repeat(64)))
                        put("artifactSha256", JsonPrimitive("c".repeat(64)))
                        put("executed", JsonPrimitive(true))
                    })
                })
                put("linkedPublicSymbols", JsonArray(listOf(
                    JsonPrimitive("codex_agent_first"),
                    JsonPrimitive("codex_agent_second"),
                )))
                put("nativeTests", buildJsonArray {
                    tests.forEach { test ->
                        add(buildJsonObject {
                            put("testId", JsonPrimitive(test))
                            put("status", JsonPrimitive(if (test == failedTest) "failed" else "passed"))
                        })
                    }
                })
                put("claims", buildJsonArray {
                    members.forEachIndexed { index, member ->
                        val symbol = if (index == 0) "codex_agent_first" else "codex_agent_second"
                        val test = tests[index]
                        add(buildJsonObject {
                            put("capabilityKey", JsonPrimitive(member))
                            put("headerReferences", JsonArray(listOf(JsonPrimitive(symbol))))
                            put("consumerReferences", JsonArray(listOf(JsonPrimitive(symbol))))
                            put("publicSymbols", JsonArray(listOf(JsonPrimitive(symbol))))
                            put("nativeTestIds", JsonArray(listOf(JsonPrimitive(test))))
                        })
                    }
                })
            })
        }

        fun input() = CrossLanguageNativeWrapperEvidenceInput(
            phase = CrossLanguageBindingPhase.M9_CSHARP,
            language = CrossLanguageBinding.CSHARP,
            apiReport = canonical.apiReport,
            canonicalCoverageReceipt = canonical.coverageReceipt,
            cAbiBootstrapEvidence = bootstrap,
            claims = claims,
            compilerEvidence = compiler,
            testProgram = program,
            testResults = results,
            packageArtifacts = nativeWrapperPackageArtifacts(CrossLanguageBinding.CSHARP, packageDirectory),
            hostEvidenceDirectory = hostEvidenceDirectory,
            stagedCAbiSdks = stagedCAbiSdks,
        )
    }
}
