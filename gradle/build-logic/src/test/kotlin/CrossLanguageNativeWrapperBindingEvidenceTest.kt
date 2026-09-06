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
    fun `C++ rejects negative evidence before capability execution and preserves originals`() {
        val root = kotlin.io.path.createTempDirectory("cpp-capability-negative-gate-").toFile().canonicalFile
        try {
            val input = root.resolve("handoff").apply { mkdirs(); resolve("fixture").writeText("input") }
            val negatives = root.resolve("negatives").apply { mkdirs(); resolve("fixture").writeText("original") }
            val host = root.resolve("host/evidence/cpp").apply { mkdirs() }
            host.resolve("linux-x64.tsv").writeText(
                "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus\n" +
                    "linux-x64\tcpp-package/package.zip\t${"a".repeat(64)}\t${"b".repeat(64)}\tcpp-installed-host-lifecycle\tpassed\n",
            )
            host.resolve("toolchain.tsv").writeText("tool\tversion\ncmake\tfixture\ncppCompiler\tfixture\n")
            val source = root.resolve("codex-agent-bindings/cpp/tests/test_installed_package_tamper.py")
                .apply { parentFile.mkdirs(); writeText("original program fixture") }
            val reader = root.resolve("codex-agent-bindings/cpp/tools/verify_imported_package.py").apply {
                parentFile.mkdirs()
                writeText("""
                    import pathlib, sys
                    assert sys.argv[1] == 'verify-evidence'
                    assert pathlib.Path(sys.argv[sys.argv.index('--expected-test-program') + 1]).read_text() == 'original program fixture'
                    assert pathlib.Path(sys.argv[sys.argv.index('--evidence') + 1]).name == 'negatives'
                    pathlib.Path('reader-called').write_text('read-only fixture rejection')
                    raise SystemExit('synthetic negative evidence rejection')
                """.trimIndent())
            }
            val producer = root.resolve("producer.py").apply {
                writeText("from pathlib import Path\nPath('producer-called').write_text('must not run')\n")
            }
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            val output = root.resolve("build/capability")
            val task = project.tasks.create("cppCapabilities", NativeWrapperCapabilityEvidenceTask::class.java).apply {
                language.set("cpp")
                expectedClassifier.set("linux-x64")
                capabilityInputsDirectory.set(input)
                installedConsumerEvidence.set(root.resolve("host"))
                packageNegativeEvidenceDirectory.set(negatives)
                producerScript.set(producer)
                claims.set(source) // Command ordering fixture, not canonical claims/acceptance.
                producerSources.from(producer, reader, source)
                outputDirectory.set(output)
                repositoryRoot.set(root)
            }
            assertFailsWith<org.gradle.api.GradleException> { task.produce() }
            assertTrue(root.resolve("reader-called").isFile)
            assertFalse(root.resolve("producer-called").exists())
            assertFalse(output.exists())
            assertEquals("original", negatives.resolve("fixture").readText())
            assertEquals("original program fixture", source.readText())
        } finally {
            root.deleteRecursively()
        }
    }

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
    fun `capability verifier shares exact matching but never grants five-host closure`() = withFixture { fixture ->
        val receipt = deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input())
        val capabilities = fixture.verifyCapabilities()
        assertEquals(receipt.canonical, capabilities.canonical)
        assertEquals(receipt.scenarioEvidence, capabilities.scenarios)
        assertEquals(receipt.projectionClaims.map { it.capabilityKey }, capabilities.claims.map { it.capabilityKey })
        assertEquals(receipt.bindingTests.map { it.testId }, capabilities.testResults)
        fixture.hostEvidenceDirectory.resolve("linux-x64-lane-receipt.json").delete()
        assertEquals(capabilities, fixture.verifyCapabilities())
        assertFailsWith<IllegalStateException> { deriveCrossLanguageNativeWrapperBindingReceipt(fixture.input()) }
        assertFalse(fixture.receipt.exists())
        fixture.program.writeText("")
        assertFailsWith<IllegalStateException> { fixture.verifyCapabilities() }
    }

    @Test
    fun `packaged capability verifier emits no receipt and rejects incomplete proof`() = withFixture { fixture ->
        val arguments = arrayOf(
            "verify-native-wrapper-capability-evidence",
            "--language", "csharp",
            "--api-report", fixture.input().apiReport.absolutePath,
            "--coverage-receipt", fixture.input().canonicalCoverageReceipt.absolutePath,
            "--c-abi-bootstrap", fixture.bootstrap.absolutePath,
            "--claims", fixture.claims.absolutePath,
            "--compiler-evidence", fixture.compiler.absolutePath,
            "--test-program", fixture.program.absolutePath,
            "--test-results", fixture.results.absolutePath,
        )
        val original = verifiedRegularFiles(fixture.root).mapValues { (_, file) -> file.releaseDigest() }
        val passed = runReleaseTool(fixture.root, *arguments)
        assertEquals(0, passed.first, passed.second)
        assertEquals(original, verifiedRegularFiles(fixture.root).mapValues { (_, file) -> file.releaseDigest() })
        val illegalOutput = runReleaseTool(fixture.root, *arguments, "--output", fixture.receipt.absolutePath)
        assertTrue(illegalOutput.first != 0, illegalOutput.second)
        assertFalse(fixture.receipt.exists())
        fixture.results.writeText(fixture.results.readText().replace("\tpassed", "\tfailed"))
        val failed = runReleaseTool(fixture.root, *arguments)
        assertTrue(failed.first != 0, failed.second)
        assertTrue("did not pass" in failed.second, failed.second)
        assertFalse(fixture.receipt.exists())
    }

    @Test
    fun `imported capability task retains complete raw proof and clears failed output`() = withFixture { fixture ->
        // Synthetic compiler/host fixtures exercise the actual task and matcher,
        // not a real compiler execution or hosted capability acceptance.
        val root = fixture.root.canonicalFile
        val handoff = root.resolve("handoff").also(File::mkdirs)
        fun copy(source: File, path: String) = handoff.resolve(path).also {
            it.parentFile.mkdirs()
            source.copyTo(it)
        }
        copy(fixture.input().apiReport, "contract/canonical-api.json")
        copy(fixture.input().canonicalCoverageReceipt, "contract/canonical-coverage.json")
        copy(fixture.bootstrap, "bootstrap/bootstrap-evidence.json")
        val native = handoff.resolve("sdks/linux-x64/lib/libcodex_agent.so").apply {
            parentFile.mkdirs()
            writeText("synthetic native identity fixture")
        }
        handoff.resolve("receipts/sdk-package.json").apply {
            parentFile.mkdirs()
            atomicWriteJson(buildJsonObject {
                put("product", JsonPrimitive("sdk"))
                put("component", JsonPrimitive("csharp"))
                put("phase", JsonPrimitive("package"))
                put("target", JsonPrimitive("desktop"))
                put("outputs", buildJsonArray { add(buildJsonObject {
                    put("kind", JsonPrimitive("package"))
                    put("relativePath", JsonPrimitive("outputs/csharp/package.nupkg"))
                    put("sha256", JsonPrimitive("sha256:" + "a".repeat(64)))
                }) })
            })
        }
        val installed = root.resolve("installed/evidence/csharp").also(File::mkdirs)
        installed.resolve("linux-x64.tsv").writeText(
            "classifier\tpackageArtifactId\tpackageSha256\tnativeLibrarySha256\ttestId\tstatus\n" +
                "linux-x64\tcsharp-package/package.nupkg\t${"a".repeat(64)}\t${native.releaseDigest()}\t" +
                "csharp-installed-host-lifecycle\tpassed\n",
        )
        installed.resolve("toolchain.tsv").writeText("tool\tversion\ndotnet\tfixture\n")
        val script = root.resolve("producer.py").apply { writeText("""
            import pathlib, shutil, sys
            args = sys.argv[1:]
            def arg(name): return pathlib.Path(args[args.index(name) + 1])
            assert arg('--sdk-compatibility') == pathlib.Path('handoff/sdks/sdk-compatibility.json').absolute()
            assert arg('--native-library') == pathlib.Path('handoff/sdks/linux-x64/lib/libcodex_agent.so').absolute()
            assert arg('--dotnet').is_absolute()
            output = arg('--output')
            output.mkdir(parents=True)
            for source, target in [('compiler.tsv', 'compiler-evidence.tsv'),
                                   ('results.tsv', 'executed-tests.tsv'), ('tests.bin', 'test-program')]:
                shutil.copyfile(source, output / target)
            (output / 'auxiliary').mkdir()
            (output / 'auxiliary/raw.log').write_text('full raw fixture log\n')
            if pathlib.Path('tamper').exists():
                (arg('--canonical-api').parent / 'injected.txt').write_text('changed input')
        """.trimIndent() + "\n") }
        val project = ProjectBuilder.builder().withProjectDir(root).build()
        val output = root.resolve("build/capability")
        val task = project.tasks.create("capabilities", NativeWrapperCapabilityEvidenceTask::class.java).apply {
            language.set("csharp")
            expectedClassifier.set("linux-x64")
            dotnetExecutable.set(root.resolve("fixture-dotnet").absolutePath)
            capabilityInputsDirectory.set(handoff)
            installedConsumerEvidence.set(root.resolve("installed"))
            producerScript.set(script)
            claims.set(fixture.claims)
            producerSources.from(script, fixture.claims)
            outputDirectory.set(output)
            repositoryRoot.set(root)
        }
        task.produce()
        assertEquals(setOf("compiler-evidence.tsv", "executed-tests.tsv", "test-program", "auxiliary/raw.log"),
            verifiedRegularFiles(output).keys)
        assertEquals(fixture.compiler.readText(), output.resolve("compiler-evidence.tsv").readText())
        assertFalse(fixture.receipt.exists())
        val cli = runReleaseTool(root, "verify-native-wrapper-validation-evidence", "--language", "csharp",
            "--target", "linux-x64", "--capability-inputs", handoff.absolutePath,
            "--installed-evidence", root.resolve("installed").absolutePath,
            "--capability-evidence", output.absolutePath, "--claims", fixture.claims.absolutePath)
        assertEquals(0, cli.first, cli.second)
        // Orchestration fixture only: Python input authentication is tested separately
        // against signed product fixtures. A subprocess success alone must NOT admit
        // evidence; the packaged CLI still runs the real Kotlin matcher itself.
        val importedStage = root.resolve("imported-validation")
        root.resolve("installed").copyRecursively(importedStage.resolve("outputs/installed"))
        output.copyRecursively(importedStage.resolve("outputs/capability"))
        val validationReceipt = root.resolve("validation-receipt.json").apply { writeText("original fixture receipt\n") }
        val request = root.resolve("compatibility-request.json").apply { writeText("fixture request\n") }
        val inputVerifier = root.resolve("ci/products/sdk_package.py").apply {
            parentFile.mkdirs()
            root.resolve("ci/__init__.py").writeText("")
            parentFile.resolve("__init__.py").writeText("")
            writeText("""
                import pathlib, shutil, sys
                args = sys.argv[1:]
                def arg(name): return pathlib.Path(args[args.index(name) + 1])
                if args[0] == 'native-content':
                    sys.stdout.write('{"fixture":"deterministic content"}\n')
                    raise SystemExit(0)
                destination = arg('--validation-inputs-output')
                shutil.copytree('handoff', destination)
                shutil.copytree(arg('--validation-stage'), destination / 'validation')
                shutil.copyfile(arg('--validation-receipt'), destination / 'receipts/sdk-validation.json')
                (destination / 'validation-source').mkdir()
                shutil.copyfile('${fixture.claims.name}', destination / 'validation-source/capability-claims.tsv')
            """.trimIndent() + "\n")
        }
        val importArguments = arrayOf("verify-imported-native-wrapper-validation", "--repository", root.absolutePath,
            "--language", "csharp", "--target", "linux-x64", "--package-stage", handoff.absolutePath,
            "--package-receipt", handoff.resolve("receipts/sdk-package.json").absolutePath,
            "--compatibility-request", request.absolutePath, "--runtime-stages", handoff.absolutePath,
            "--staged-sdks", handoff.absolutePath, "--validation-stage", importedStage.absolutePath,
            "--validation-receipt", validationReceipt.absolutePath)
        val importedBefore = verifiedRegularFiles(importedStage).mapValues { it.value.releaseDigest() }
        val importedCli = runReleaseTool(root, *importArguments)
        assertEquals(0, importedCli.first, importedCli.second)
        assertEquals(importedBefore, verifiedRegularFiles(importedStage).mapValues { it.value.releaseDigest() })
        assertEquals("original fixture receipt\n", validationReceipt.readText())
        val content = root.resolve("content.json")
        val contentArguments = arrayOf("write-native-wrapper-validation-content", *importArguments.drop(1).toTypedArray(),
            "--content-output", content.absolutePath)
        val contentCli = runReleaseTool(root, *contentArguments)
        assertEquals(0, contentCli.first, contentCli.second)
        assertEquals("{\"fixture\":\"deterministic content\"}\n", content.readText())
        assertTrue(runReleaseTool(root, *contentArguments).first != 0, "Content must not overwrite finalized bytes")
        assertEquals("{\"fixture\":\"deterministic content\"}\n", content.readText())
        content.delete()
        listOf(handoff.resolve("unsafe-content.json").absolutePath,
            root.resolve("handoff/../unsafe-content.json").absolutePath).forEach { unsafe ->
            assertTrue(runReleaseTool(root, *contentArguments.dropLast(1).toTypedArray(), unsafe).first != 0)
        }
        assertFalse(root.resolve("unsafe-content.json").exists())
        assertFalse(handoff.resolve("unsafe-content.json").exists())
        val importedResults = importedStage.resolve("outputs/capability/executed-tests.tsv")
        importedResults.writeText(importedResults.readText().replace("\tpassed", "\tfailed"))
        assertTrue(runReleaseTool(root, *importArguments).first != 0, "Input success must not bypass full matcher")
        assertTrue(runReleaseTool(root, *contentArguments).first != 0, "Failed full matcher cannot publish content")
        assertFalse(content.exists())
        inputVerifier.writeText("# Successful process without authenticated private handoff\n")
        assertTrue(runReleaseTool(root, *importArguments).first != 0, "A success token must not admit an import")
        val originalHost = installed.resolve("linux-x64.tsv").readText()
        listOf("a".repeat(64), native.releaseDigest()).forEach { digest ->
            installed.resolve("linux-x64.tsv").writeText(originalHost.replace(digest, "e".repeat(64)))
            assertFailsWith<IllegalStateException> {
                verifyCrossLanguageNativeWrapperValidationEvidence(CrossLanguageBinding.CSHARP,
                    "linux-x64", handoff, root.resolve("installed"), output, fixture.claims)
            }
        }
        installed.resolve("linux-x64.tsv").writeText(originalHost)
        root.resolve("tamper").writeText("fixture mutation")
        assertFailsWith<IllegalStateException> { task.produce() }
        assertFalse(output.exists())
        root.resolve("tamper").delete()
        handoff.resolve("contract/injected.txt").delete()
        fixture.results.writeText(fixture.results.readText().replace("\tpassed", "\tfailed"))
        assertFailsWith<IllegalStateException> { task.produce() }
        assertFalse(output.exists())
        val sentinel = handoff.resolve("preserve").apply { writeText("original") }
        task.ownedBuildDirectory.set(root) // Permit the path; the input-overlap guard must still reject it.
        task.outputDirectory.set(handoff)
        assertFailsWith<IllegalStateException> { task.produce() }
        assertEquals("original", sentinel.readText())
        val link = root.resolve("build/link").toPath()
        java.nio.file.Files.createSymbolicLink(link, handoff.toPath())
        task.outputDirectory.set(link.resolve("unsafe-output").toFile())
        assertFailsWith<IllegalStateException> { task.produce() }
        assertFalse(handoff.resolve("unsafe-output").exists())
        assertEquals("original", sentinel.readText())
    }

    @Test
    fun `capability producer commands use imported resources for all five languages and targets`() {
        val handoff = File("handoff").absoluteFile
        nativeWrapperBindings.forEach { binding ->
            listOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64").forEach { target ->
                val command = nativeWrapperCapabilityCommand("python3", File("producer.py"), binding.id, target,
                    handoff, File("output"), File("dotnet").absolutePath, "dart", File("config.json"))
                assertTrue(handoff.resolve("sdks/sdk-compatibility.json").absolutePath in command)
                assertTrue(handoff.resolve("sdks/$target").absolutePath in command)
                assertEquals(binding == CrossLanguageBinding.CPP, "--classifier" in command)
                assertEquals(binding == CrossLanguageBinding.CSHARP, "--dotnet" in command)
                assertEquals(binding == CrossLanguageBinding.DART, "--package-config" in command)
                assertFalse(command.any { it.contains("runtime/build") })
            }
        }
        assertFailsWith<IllegalStateException> {
            nativeWrapperCapabilityCommand("python3", File("producer.py"), "csharp", "linux-x64", handoff, File("out"))
        }
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
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"native-wrapper-preflight\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                plugins {
                    id("codexagent.native-wrapper-sdk")
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
                assertFailsWith<IllegalStateException> { fixture.verifyCapabilities() }
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
        private val canonicalStagedCAbiSdks = root.resolve("canonical-staged-c-abi-sdks")
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

        fun verifyCapabilities(): CrossLanguageNativeWrapperCapabilityEvidence = input().let {
            verifyCrossLanguageNativeWrapperCapabilityEvidence(
                it.language, it.apiReport, it.canonicalCoverageReceipt, it.cAbiBootstrapEvidence,
                it.claims, it.compilerEvidence, it.testProgram, it.testResults,
            )
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
            if (!canonicalStagedCAbiSdks.isDirectory) {
                val fixture = CrossLanguageCAbiPackageEvidenceTest.Fixture()
                try {
                    val version = CrossLanguageCAbiPackageEvidenceTest.Fixture.VERSION
                    val archives = linkedMapOf<String, File>()
                    val evidence = linkedMapOf<String, File>()
                    crossLanguageCAbiTargetSpecs.values.forEach { spec ->
                        val archive = fixture.root.resolve(
                            crossLanguageCAbiArchiveFileName(version, spec.target),
                        )
                        val snapshot = fixture.packageArchive(spec, archive)
                        val proof = fixture.root.resolve(
                            crossLanguageCAbiPackageEvidenceFileName(spec.target),
                        )
                        fixture.writeEvidence(spec, archive, snapshot, proof)
                        archives[spec.target] = archive
                        evidence[spec.target] = proof
                    }
                    stageCrossLanguageNativeWrapperSdks(
                        CrossLanguageNativeWrapperSdkInput(
                            version,
                            version,
                            version,
                            candidateCommit,
                            candidateTree,
                            fixture.sdkCompatibility(),
                            archives,
                            evidence,
                            crossLanguageCAbiTargetSpecs.mapValues { (_, spec) -> fixture.reference(spec) },
                        ),
                        canonicalStagedCAbiSdks,
                    )
                } finally {
                    fixture.root.deleteRecursively()
                }
            }
            stagedCAbiSdks.deleteRecursively()
            check(canonicalStagedCAbiSdks.copyRecursively(stagedCAbiSdks)) {
                "could not restore canonical staged C ABI SDK fixture"
            }
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
