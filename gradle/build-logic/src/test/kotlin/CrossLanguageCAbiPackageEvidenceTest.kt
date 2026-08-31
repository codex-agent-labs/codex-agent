import java.io.File
import java.time.LocalDateTime
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.gradle.api.tasks.CacheableTask
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.work.DisableCachingByDefault

class CrossLanguageCAbiPackageEvidenceTest {
    @Test
    fun `desktop plugin wires exact five packages host proofs imports and publication classifiers`() {
        val wiring = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
        listOf(
            "package${'$'}{target.replaceFirstChar(Char::uppercase)}CAbiSdk",
            "generate${'$'}{targetTitle}CAbiPackageEvidence",
            "generateMingwX64MsvcImportLibrary",
            "generateCodexAgentCAbiScenarioProof",
            "codexAgent.candidateCommit",
            "codexAgent.candidateTree",
            "codexAgent.desktopClassifierDirectory",
            "val desktopRuntimeCompatibilityVersion = providers.provider {",
            "runtimeCompatibilityVersion(project.version.toString())",
            "crossLanguageCAbiArchiveFileName(version, target)",
            "crossLanguageCAbiPackageEvidenceFileName(distribution.target)",
            "tasks.register<GenerateCrossLanguageCAbiScenarioProofTask>",
            "native/c-api/include/codex_agent.h",
            "native/c-api/exports/macos.exports",
            "native/c-api/exports/linux.map",
            "native/c-api/exports/windows.def",
            "rootProject.layout.projectDirectory.file(\"LICENSE\")",
            "rootProject.layout.projectDirectory.file(\"THIRD_PARTY_NOTICES.md\")",
            "libcodex_agent.dll.a",
            "-Wl,--out-implib,${'$'}{mingwGnuImportLibrary.get().asFile.absolutePath}",
            "outputs.file(mingwGnuImportLibrary)",
            "/machine:x64",
            "/brepro",
            "cAbiToolDefaults(distribution.target)",
            "crossLanguageCAbiCompileOnlyConsumers.sorted()",
            "tasks.withType<KotlinNativeTest>().matching { it.name == testTaskName }.configureEach",
            "dependsOn(validateEvidenceTarget, testTaskName)",
            "val localCAbiRunner = hostTarget?.let(crossLanguageCAbiTargetSpecs::getValue)",
            ".orElse(localCAbiRunner?.runnerOs ?: \"unsupported\")",
            ".orElse(localCAbiRunner?.runnerArch ?: \"unsupported\")",
            "artifact(cAbiArchiveFiles.getValue(target))",
            "tasks.register<StageCrossLanguageNativeWrapperSdksTask>",
            "tasks.register<MaterializeCrossLanguageNativeWrapperPackageAssetsTask>",
            "codexAgent.nativeWrapperRuntimeStageRoot",
            "c-abi-reference",
            "native-wrapper-c-abi-sdks",
            "native-wrapper-package-assets",
            "prepareNativeWrapperPackageSources",
            "native-wrapper-package-sources/",
            "\"dart\" to (\"Dart\" to listOf(\"build/**\"",
        ).forEach { contract -> assertTrue(contract in wiring, "Missing desktop C ABI wiring: $contract") }
        assertEquals(1, Regex("artifact\\(cAbiArchiveFiles\\.getValue\\(target\\)\\)").findAll(wiring).count())
        assertTrue(
            "check(runnerOs.get() == spec.runnerOs && runnerArch.get() == spec.runnerArch)" in
                File("src/main/kotlin/CrossLanguageCAbiPackageEvidence.kt").readText(),
        )
        val cppCmake = File("../../codex-agent-runtime-desktop/bindings/cpp/CMakeLists.txt").readText()
        assertTrue("\"${'$'}{CodexAgent_C_SDK_ROOT}/LICENSE.txt\"" in cppCmake)
        assertFalse("../../../LICENSE" in cppCmake)
        assertFalse("tasks.named<KotlinNativeTest>(testTaskName)" in wiring)
        assertFalse("runtime-python" in wiring)
        assertFalse("libraryVersion.set(project.version" in wiring)
        assertFalse("crossLanguageCAbiArchiveFileName(project.version" in wiring)
        assertFalse("codex-agent-runtime-desktop-${'$'}{project.version" in wiring)
    }

    @Test
    fun `native wrapper Gradle task types are SDK owned`() {
        val runtimeSource = File("src/main/kotlin/CrossLanguageCAbiPackageEvidence.kt").readText()
        val sdkSource = File("src/main/kotlin/CrossLanguageNativeWrapperGradleTasks.kt").readText()
        listOf(
            "StageCrossLanguageNativeWrapperSdksTask",
            "MaterializeCrossLanguageNativeWrapperPackageAssetsTask",
        ).forEach { taskType ->
            val declaration = "abstract class $taskType"
            assertFalse(declaration in runtimeSource, "Runtime C ABI source still owns $taskType")
            assertTrue(declaration in sdkSource, "SDK Gradle source does not own $taskType")
        }
    }

    @Test
    fun `target and classifier inventory is exact`() {
        assertEquals(
            mapOf(
                "macosArm64" to "c-abi-macos-arm64",
                "macosX64" to "c-abi-macos-x64",
                "linuxArm64" to "c-abi-linux-arm64",
                "linuxX64" to "c-abi-linux-x64",
                "mingwX64" to "c-abi-windows-x64",
            ),
            crossLanguageCAbiTargetSpecs.mapValues { it.value.classifier },
        )
        assertEquals(setOf("mach-o", "elf", "pe"), crossLanguageCAbiTargetSpecs.values.map { it.format }.toSet())
        assertEquals("macosArm64", crossLanguageCAbiHostTarget("Mac OS X", "aarch64"))
        assertEquals("macosArm64", crossLanguageCAbiHostTarget("macOS", "arm64"))
        assertEquals("macosX64", crossLanguageCAbiHostTarget("Mac OS X", "x86_64"))
        assertEquals("linuxArm64", crossLanguageCAbiHostTarget("Linux", "aarch64"))
        assertEquals("linuxX64", crossLanguageCAbiHostTarget("Linux", "amd64"))
        assertEquals("mingwX64", crossLanguageCAbiHostTarget("Windows 11", "x86_64"))
        assertEquals(null, crossLanguageCAbiHostTarget("FreeBSD", "x86_64"))
        assertEquals(null, crossLanguageCAbiHostTarget("Mac OS X", "riscv64"))
        assertEquals(setOf("codex_agent_lifecycle_compile.cpp"), crossLanguageCAbiCompileOnlyConsumers)
        assertEquals(30, crossLanguageCAbiStrictConsumers.size)
        assertEquals(
            setOf(
                "c-abi-package-macos-arm64",
                "c-abi-package-macos-x64",
                "c-abi-package-linux-arm64",
                "c-abi-package-linux-x64",
                "c-abi-package-windows-x64",
            ),
            crossLanguageCAbiPackageProofIds.values.toSet(),
        )
        assertEquals(
            "codex-agent-runtime-desktop-0.2.0-c-abi-windows-x64.zip",
            crossLanguageCAbiArchiveFileName("0.2.0", "mingwX64"),
        )
        assertEquals("c-abi-package-linux-arm64.json", crossLanguageCAbiPackageEvidenceFileName("linuxArm64"))
        assertEquals(
            setOf("c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport"),
            crossLanguageCAbiRequiredToolIds("mingwX64"),
        )
        assertEquals(CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT, Fixture().symbols.size)
        assertEquals("1.12", CROSS_LANGUAGE_C_ABI_CURRENT)
        assertEquals("1.0", CROSS_LANGUAGE_C_ABI_MINIMUM)
        assertEquals("0x010c0000", CROSS_LANGUAGE_C_ABI_ENCODED)
    }

    @Test
    fun `GNU import symbols exclude thunks and linker metadata without hiding exact extras`() {
        val listing = """
            00000000 T codex_agent_host_create
            00000000 T __imp_codex_agent_host_create
            00000000 I \u007fcodex_agent_NULL_THUNK_DATA
                     U __NULL_IMPORT_DESCRIPTOR
            00000000 T _codex_agent_host_destroy
            00000000 T codex_agent_unreviewed_extra
        """.trimIndent() + "\n00000000\tD\tcodex_agent_unreviewed_data"

        assertEquals(
            setOf(
                "codex_agent_host_create", "codex_agent_host_destroy", "codex_agent_unreviewed_data",
                "codex_agent_unreviewed_extra",
            ),
            crossLanguageCAbiGnuImportSymbols(listing),
        )
    }

    @Test
    fun `five target SDK packages are deterministic exact and self verifying`() = withFixture { fixture ->
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val input = fixture.input(spec)
            val first = fixture.root.resolve("${spec.target}-first.zip")
            val second = fixture.root.resolve("${spec.target}-second.zip")
            val firstSnapshot = packageCrossLanguageCAbiSdk(input, first)
            val secondSnapshot = packageCrossLanguageCAbiSdk(input, second)

            assertTrue(first.readBytes().contentEquals(second.readBytes()), spec.target)
            assertEquals(firstSnapshot, secondSnapshot)
            assertEquals(fixture.header.releaseDigest(), firstSnapshot.headerSha256)
            assertEquals(fixture.library(spec).releaseDigest(), firstSnapshot.librarySha256)
            assertEquals(fixture.expectedMembers(spec), zipNames(first))
            assertEquals(fixture.expectedMembers(spec).associateWith { 0x81a4 }, readDesktopRuntimeUnixModes(first))
            assertEquals(firstSnapshot, inspectCrossLanguageCAbiPackage(first, input))
        }
    }

    @Test
    fun `package rejects identity header platform and archive mutations`() = withFixture { fixture ->
        val spec = crossLanguageCAbiTargetSpecs.getValue("linuxX64")
        val input = fixture.input(spec)
        val archive = fixture.root.resolve("linux.zip")
        packageCrossLanguageCAbiSdk(input, archive)

        val cases = listOf(
            "classifier" to { inspectCrossLanguageCAbiPackage(archive, input.copy(classifier = "c-abi-linux-arm64")) },
            "commit" to { inspectCrossLanguageCAbiPackage(archive, input.copy(producerCommit = "a".repeat(39))) },
            "tree" to { inspectCrossLanguageCAbiPackage(archive, input.copy(producerTree = "b".repeat(39))) },
            "version" to { inspectCrossLanguageCAbiPackage(archive, input.copy(libraryVersion = "latest")) },
        )
        cases.forEach { (name, action) ->
            assertFailsWith<IllegalStateException>(name) { action() }
        }

        fixture.header.appendText("CODEX_AGENT_API void CODEX_AGENT_CALL codex_agent_unreviewed(void);\n")
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(archive, input) }
        fixture.writeHeader()

        val tampered = fixture.root.resolve("tampered.zip")
        rewriteZip(archive, tampered, replacements = mapOf(spec.libraryPath to "tampered".encodeToByteArray()))
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(tampered, input) }

        val missing = fixture.root.resolve("missing.zip")
        rewriteZip(archive, missing, drop = setOf("LICENSE.txt"))
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(missing, input) }

        val extra = fixture.root.resolve("extra.zip")
        rewriteZip(archive, extra, additions = mapOf("extra.txt" to byteArrayOf(1)))
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(extra, input) }

        val unsafe = fixture.root.resolve("unsafe.zip")
        rewriteZip(archive, unsafe, additions = mapOf("../escape" to byteArrayOf(1)))
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(unsafe, input) }

        val staleTimestamp = fixture.root.resolve("timestamp.zip")
        rewriteZip(archive, staleTimestamp, timestamp = LocalDateTime.of(2026, 1, 1, 0, 0))
        assertFailsWith<IllegalStateException> { inspectCrossLanguageCAbiPackage(staleTimestamp, input) }
        Unit
    }

    @Test
    fun `windows package requires and binds both import libraries`() = withFixture { fixture ->
        val spec = crossLanguageCAbiTargetSpecs.getValue("mingwX64")
        val input = fixture.input(spec)
        assertFailsWith<IllegalArgumentException> {
            packageCrossLanguageCAbiSdk(input.copy(gnuImportLibrary = null), fixture.root.resolve("missing-gnu.zip"))
        }
        assertFailsWith<IllegalArgumentException> {
            packageCrossLanguageCAbiSdk(input.copy(msvcImportLibrary = null), fixture.root.resolve("missing-msvc.zip"))
        }
        val archive = fixture.root.resolve("windows.zip")
        val snapshot = packageCrossLanguageCAbiSdk(input, archive)
        assertEquals(fixture.gnuImport.releaseDigest(), snapshot.members.getValue("lib/libcodex_agent.dll.a"))
        assertEquals(fixture.msvcImport.releaseDigest(), snapshot.members.getValue("lib/codex_agent.lib"))
    }

    @Test
    fun `proof binds exact package symbols runner tools consumers and ABI`() = withFixture { fixture ->
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val input = fixture.input(spec)
            val archive = fixture.root.resolve("proof-${spec.target}.zip")
            val snapshot = packageCrossLanguageCAbiSdk(input, archive)
            val consumers = fixture.consumerDigests()
            val report = fixture.evidence(spec, snapshot)

            verifyCrossLanguageCAbiPackageEvidence(
                report, archive, input, spec.runnerOs, spec.runnerArch, consumers,
            )
            val evidence = fixture.root.resolve("portable-${spec.target}.json").apply { atomicWriteJson(report) }
            assertEquals(
                report,
                portableVerifyCrossLanguageCAbiPackageEvidence(
                    spec.target,
                    input.libraryVersion,
                    input.producerCommit,
                    input.producerTree,
                    archive,
                    evidence,
                    fixture.header,
                    fixture.license,
                    fixture.notice,
                    input.exportPolicy,
                    fixture.consumers.values.toList(),
                ),
            )
        }
    }

    @Test
    fun `wrapper SDK staging verifies and extracts exactly all five package proofs`() = withFixture { fixture ->
        val archives = linkedMapOf<String, File>()
        val evidence = linkedMapOf<String, File>()
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val archive = fixture.root.resolve(crossLanguageCAbiArchiveFileName("0.2.0", spec.target))
            val snapshot = packageCrossLanguageCAbiSdk(fixture.input(spec), archive)
            val proof = fixture.root.resolve(crossLanguageCAbiPackageEvidenceFileName(spec.target)).apply {
                atomicWriteJson(fixture.evidence(spec, snapshot))
            }
            archives[spec.target] = archive
            evidence[spec.target] = proof
        }
        val output = fixture.root.resolve("wrapper-sdks")
        val input = CrossLanguageNativeWrapperSdkInput(
            "0.2.0",
            "a".repeat(40),
            "b".repeat(40),
            archives,
            evidence,
            crossLanguageCAbiTargetSpecs.mapValues { (_, spec) ->
                CrossLanguageNativeWrapperSdkReferenceInput(
                    reviewedHeader = fixture.header,
                    license = fixture.license,
                    notice = fixture.notice,
                    exportPolicy = if (spec.format == "elf") fixture.linuxPolicy else fixture.policy,
                    consumerSources = fixture.consumers.values.toList(),
                )
            },
        )

        stageCrossLanguageNativeWrapperSdks(input, output)

        val index = output.resolve("codex-agent-native-wrapper-sdks.json").readReleaseObject()
        assertEquals(1, index.getValue("schemaVersion").jsonPrimitive.content.toInt())
        assertEquals(5, index.getValue("targets").jsonArray.size)
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val targetRoot = output.resolve(spec.classifier.removePrefix("c-abi-"))
            assertEquals(fixture.library(spec).releaseDigest(), targetRoot.resolve(spec.libraryPath).releaseDigest())
            assertEquals(fixture.license.releaseDigest(), targetRoot.resolve("LICENSE.txt").releaseDigest())
            assertTrue(targetRoot.resolve("codex-agent-c-abi-manifest.json").isFile)
            assertEquals(
                evidence.getValue(spec.target).readText(),
                targetRoot.resolve("codex-agent-c-abi-evidence.json").readText(),
            )
        }

        val packageAssets = fixture.root.resolve("wrapper-package-assets")
        materializeCrossLanguageNativeWrapperPackageAssets(output, packageAssets)
        crossLanguageCAbiTargetSpecs.values.forEach { spec ->
            val classifier = spec.classifier.removePrefix("c-abi-")
            val packageClassifier = when (classifier) {
                "macos-arm64" -> "osx-arm64"
                "macos-x64" -> "osx-x64"
                "windows-x64" -> "win-x64"
                else -> classifier
            }
            val libraryName = File(spec.libraryPath).name
            listOf(
                packageAssets.resolve("python/src/codex_agent/native/$classifier"),
                packageAssets.resolve("csharp/native/$packageClassifier"),
                packageAssets.resolve("rust/native/$packageClassifier"),
                packageAssets.resolve("dart/lib/src/native/$classifier"),
            ).forEach { destination ->
                assertEquals(fixture.library(spec).releaseDigest(), destination.resolve(libraryName).releaseDigest())
                assertTrue(destination.resolve("codex-agent-c-abi-manifest.json").isFile)
                assertEquals(
                    evidence.getValue(spec.target).readText(),
                    destination.resolve("codex-agent-c-abi-evidence.json").readText(),
                )
            }
            val cppSdk = packageAssets.resolve("cpp/native/$classifier")
            assertEquals(fixture.library(spec).releaseDigest(), cppSdk.resolve(spec.libraryPath).releaseDigest())
            assertTrue(cppSdk.resolve("include/codex_agent.h").isFile)
            assertTrue(cppSdk.resolve("codex-agent-c-abi-manifest.json").isFile)
            assertEquals(
                evidence.getValue(spec.target).readText(),
                cppSdk.resolve("codex-agent-c-abi-evidence.json").readText(),
            )
        }
        assertEquals(
            output.resolve("codex-agent-native-wrapper-sdks.json").readText(),
            packageAssets.resolve("codex-agent-native-wrapper-sdks.json").readText(),
        )

        output.resolve("macos-arm64/unexpected.txt").writeText("unexpected\n")
        assertFailsWith<IllegalStateException> {
            materializeCrossLanguageNativeWrapperPackageAssets(
                output,
                fixture.root.resolve("unexpected-assets"),
            )
        }
        assertFailsWith<IllegalStateException> { stageCrossLanguageNativeWrapperSdks(input, output) }
        output.deleteRecursively()
        stageCrossLanguageNativeWrapperSdks(input, output)

        assertFailsWith<IllegalStateException> {
            stageCrossLanguageNativeWrapperSdks(
                input.copy(archives = input.archives - "linuxArm64"),
                fixture.root.resolve("missing-target"),
            )
        }
        val stale = fixture.root.resolve("stale-evidence.json").apply {
            atomicWriteJson(evidence.getValue("macosArm64").readReleaseObject().with(
                "archiveSha256",
                JsonPrimitive("0".repeat(64)),
            ))
        }
        assertFailsWith<IllegalStateException> {
            stageCrossLanguageNativeWrapperSdks(
                input.copy(evidence = input.evidence + ("macosArm64" to stale)),
                fixture.root.resolve("stale-proof"),
            )
        }
        val selfAssertedProducer = fixture.root.resolve("self-asserted-producer.json").apply {
            atomicWriteJson(evidence.getValue("macosArm64").readReleaseObject().with(
                "producerCommit",
                JsonPrimitive("c".repeat(40)),
            ))
        }
        assertFailsWith<IllegalStateException> {
            stageCrossLanguageNativeWrapperSdks(
                input.copy(evidence = input.evidence + ("macosArm64" to selfAssertedProducer)),
                fixture.root.resolve("self-asserted-producer"),
            )
        }
        output.resolve("macos-arm64/lib/libcodex_agent.dylib").appendText("tampered")
        assertFailsWith<IllegalStateException> {
            materializeCrossLanguageNativeWrapperPackageAssets(output, fixture.root.resolve("tampered-assets"))
        }
        assertFailsWith<IllegalStateException> { stageCrossLanguageNativeWrapperSdks(input, output) }
        output.deleteRecursively()
        stageCrossLanguageNativeWrapperSdks(input, output)
        output.resolve("macos-arm64/codex-agent-c-abi-manifest.json").appendText("tampered")
        assertFailsWith<IllegalStateException> {
            materializeCrossLanguageNativeWrapperPackageAssets(
                output,
                fixture.root.resolve("tampered-manifest-assets"),
            )
        }
        Unit
    }

    @Test
    fun `proof rejects stale tampered missing extra and unexecuted dimensions`() = withFixture { fixture ->
        val spec = crossLanguageCAbiTargetSpecs.getValue("macosArm64")
        val input = fixture.input(spec)
        val archive = fixture.root.resolve("evidence.zip")
        val snapshot = packageCrossLanguageCAbiSdk(input, archive)
        val valid = fixture.evidence(spec, snapshot)
        val consumers = fixture.consumerDigests()
        fun verify(report: JsonObject) = verifyCrossLanguageCAbiPackageEvidence(
            report, archive, input, spec.runnerOs, spec.runnerArch, consumers,
        )
        verify(valid)

        val cases = listOf(
            "extra field" to JsonObject(valid + ("extra" to JsonPrimitive(true))),
            "missing field" to JsonObject(valid - "result"),
            "wrong artifact ID" to valid.with("artifactId", JsonPrimitive("c-abi-package-other")),
            "stale commit" to valid.with("producerCommit", JsonPrimitive("c".repeat(40))),
            "stale tree" to valid.with("producerTree", JsonPrimitive("d".repeat(40))),
            "wrong runner OS" to valid.with("runnerOs", JsonPrimitive("Linux")),
            "wrong runner architecture" to valid.with("runnerArch", JsonPrimitive("X64")),
            "wrong ABI" to valid.with("abiCurrent", JsonPrimitive("1.11")),
            "wrong archive" to valid.with("archiveSha256", JsonPrimitive("0".repeat(64))),
            "wrong header" to valid.with("headerSha256", JsonPrimitive("1".repeat(64))),
            "wrong library" to valid.with("librarySha256", JsonPrimitive("2".repeat(64))),
            "wrong format" to valid.with("format", JsonPrimitive("elf")),
            "wrong architecture" to valid.with("architecture", JsonPrimitive("x86_64")),
            "wrong loader" to valid.with("loaderIdentity", JsonPrimitive("/tmp/libcodex_agent.dylib")),
            "wrong version" to valid.with("versionIdentity", JsonPrimitive("current=1.11.0")),
            "missing symbol" to valid.with("publicSymbols", JsonArray(valid.getValue("publicSymbols").jsonArray.dropLast(1))),
            "wrong symbol count" to valid.with("publicSymbolCount", JsonPrimitive(776)),
            "unexpected symbol version" to valid.with("publicSymbolVersions", JsonArray(listOf(JsonObject(mapOf(
                "symbol" to JsonPrimitive(fixture.symbols.first()),
                "version" to JsonPrimitive("CODEX_AGENT_1.0"),
            ))))),
            "missing tool" to valid.with("tools", JsonArray(valid.getValue("tools").jsonArray.dropLast(1))),
            "missing consumer" to valid.with("consumers", JsonArray(emptyList())),
            "unsafe consumer" to valid.mapFirstConsumer { it.with("source", JsonPrimitive("../strict.c")) },
            "stale consumer source" to valid.mapFirstConsumer { it.with("sourceSha256", JsonPrimitive("3".repeat(64))) },
            "wrong consumer language" to valid.mapFirstConsumer { it.with("language", JsonPrimitive("c++17")) },
            "wrong C++ consumer language" to valid.mapConsumerNamed("codex_agent_header_smoke.cpp") {
                it.with("language", JsonPrimitive("c11"))
            },
            "not linked" to valid.mapFirstConsumer { it.with("linked", JsonPrimitive(false)) },
            "not executed" to valid.mapFirstConsumer { it.with("executed", JsonPrimitive(false)) },
            "failed" to valid.mapFirstConsumer { it.with("exitCode", JsonPrimitive(1)) },
        )
        cases.forEach { (name, report) ->
            val failure = assertFailsWith<IllegalStateException>(name) { verify(report) }
            assertTrue(failure.message.orEmpty().contains("C ABI"), "$name: ${failure.message}")
        }
    }

    @Test
    fun `proof rejects import library mutation independently`() = withFixture { fixture ->
        val spec = crossLanguageCAbiTargetSpecs.getValue("mingwX64")
        val input = fixture.input(spec)
        val archive = fixture.root.resolve("windows-proof.zip")
        val snapshot = packageCrossLanguageCAbiSdk(input, archive)
        val valid = fixture.evidence(spec, snapshot)
        val imports = valid.getValue("importLibraries").jsonArray
        val first = imports.first().jsonObject.with("sha256", JsonPrimitive("f".repeat(64)))
        val mutated = valid.with("importLibraries", JsonArray(listOf(first) + imports.drop(1)))
        assertFailsWith<IllegalStateException> {
            verifyCrossLanguageCAbiPackageEvidence(
                mutated, archive, input, spec.runnerOs, spec.runnerArch,
                fixture.consumerDigests(),
            )
        }
        assertFailsWith<IllegalStateException> {
            verifyCrossLanguageCAbiPackageEvidence(
                valid.with("gnuConsumers", JsonArray(valid.getValue("gnuConsumers").jsonArray.dropLast(1))),
                archive, input, spec.runnerOs, spec.runnerArch, fixture.consumerDigests(),
            )
        }
        assertFailsWith<IllegalStateException> {
            verifyCrossLanguageCAbiPackageEvidence(
                valid.mapFirstGnuConsumer { it.with("executed", JsonPrimitive(false)) },
                archive, input, spec.runnerOs, spec.runnerArch, fixture.consumerDigests(),
            )
        }
        Unit
    }

    @Test
    fun `ELF policy and raw dynamic symbols require every exact symbol on its exact version node`() =
        withFixture { fixture ->
            val expected = crossLanguageCAbiLinuxSymbolVersions(fixture.linuxPolicy)
            val raw = expected.entries.joinToString("\n") { (symbol, version) -> "00000000 T $symbol@@$version" }
            assertEquals(expected, crossLanguageCAbiLinuxDynamicSymbolVersions(raw, expected))

            val first = expected.entries.first()
            assertFailsWith<IllegalStateException> {
                crossLanguageCAbiLinuxDynamicSymbolVersions(
                    raw.replace("${first.key}@@${first.value}", first.key), expected,
                )
            }
            assertFailsWith<IllegalStateException> {
                crossLanguageCAbiLinuxDynamicSymbolVersions(
                    raw.replace("${first.key}@@${first.value}", "${first.key}@@CODEX_AGENT_1.12"), expected,
                )
            }
            val spec = crossLanguageCAbiTargetSpecs.getValue("linuxX64")
            val input = fixture.input(spec)
            val archive = fixture.root.resolve("linux-version-proof.zip")
            val snapshot = packageCrossLanguageCAbiSdk(input, archive)
            val valid = fixture.evidence(spec, snapshot)
            val versionRecords = valid.getValue("publicSymbolVersions").jsonArray
            val wrongRecord = versionRecords.first().jsonObject.with("version", JsonPrimitive("CODEX_AGENT_1.12"))
            assertFailsWith<IllegalStateException> {
                verifyCrossLanguageCAbiPackageEvidence(
                    valid.with("publicSymbolVersions", JsonArray(listOf(wrongRecord) + versionRecords.drop(1))),
                    archive, input, spec.runnerOs, spec.runnerArch, fixture.consumerDigests(),
                )
            }
            Unit
        }

    @Test
    fun `tool execution evidence task can never become up to date`() {
        val task = ProjectBuilder.builder().build().tasks.register(
            "generateCAbiPackageEvidence",
            GenerateCrossLanguageCAbiPackageEvidenceTask::class.java,
        ).get()
        assertFalse(task.outputs.upToDateSpec.isSatisfiedBy(task))
    }

    @Test
    fun `Gradle task cache boundaries match filesystem and toolchain behavior`() {
        assertNotNull(PackageCrossLanguageCAbiSdkTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(VerifyCrossLanguageCAbiPackageEvidenceTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(StageCrossLanguageNativeWrapperSdksTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(
            MaterializeCrossLanguageNativeWrapperPackageAssetsTask::class.java.getAnnotation(CacheableTask::class.java),
        )
        assertNotNull(
            GenerateCrossLanguageCAbiPackageEvidenceTask::class.java.getAnnotation(DisableCachingByDefault::class.java),
        )
    }

    class Fixture {
        val root = createTempDirectory("c-abi-package-evidence").toFile()
        val symbols = (0 until CROSS_LANGUAGE_C_ABI_SYMBOL_COUNT).map { "codex_agent_symbol_${it.toString().padStart(3, '0')}" }
        val header = root.resolve("codex_agent.h")
        val policy = root.resolve("macos.exports")
        val linuxPolicy = root.resolve("linux.map")
        val license = root.resolve("LICENSE")
        val notice = root.resolve("THIRD_PARTY_NOTICES.md")
        val gnuImport = root.resolve("libcodex_agent.dll.a")
        val msvcImport = root.resolve("codex_agent.lib")
        val consumers = crossLanguageCAbiStrictConsumers.associateWith(root::resolve)

        init {
            writeHeader()
            policy.writeText(symbols.joinToString("\n", postfix = "\n") { "_$it" })
            linuxPolicy.writeText((0..12).joinToString("\n\n", postfix = "\n") { node ->
                val inherited = if (node == 0) ";" else " CODEX_AGENT_1.${node - 1};"
                buildString {
                    appendLine("CODEX_AGENT_1.$node {")
                    appendLine("    global:")
                    symbols.filterIndexed { index, _ -> index % 13 == node }.forEach { symbol ->
                        appendLine("        $symbol;")
                    }
                    append("}$inherited")
                }
            })
            license.writeText("GPL-3.0-only\n")
            notice.writeText("Notices\n")
            gnuImport.writeText("gnu import\n")
            msvcImport.writeText("msvc import\n")
            consumers.forEach { (name, file) -> file.writeText("/* $name */\n") }
        }

        fun writeHeader() {
            header.writeText(symbols.joinToString("\n", postfix = "\n") {
                "CODEX_AGENT_API void CODEX_AGENT_CALL $it(void);"
            })
        }

        fun library(spec: CrossLanguageCAbiTargetSpec): File = root.resolve("${spec.target}-library").apply {
            if (!isFile) writeText("${spec.format}:${spec.architecture}:${spec.loaderIdentity}\n")
        }

        fun input(spec: CrossLanguageCAbiTargetSpec) = CrossLanguageCAbiPackageInput(
            spec.target,
            spec.classifier,
            "0.2.0",
            "a".repeat(40),
            "b".repeat(40),
            header,
            license,
            notice,
            library(spec),
            if (spec.format == "elf") linuxPolicy else policy,
            gnuImport.takeIf { spec.format == "pe" },
            msvcImport.takeIf { spec.format == "pe" },
        )

        fun expectedMembers(spec: CrossLanguageCAbiTargetSpec): Set<String> = buildSet {
            add("codex-agent-c-abi-manifest.json")
            add("include/codex_agent.h")
            add("LICENSE.txt")
            add("THIRD_PARTY_NOTICES.md")
            add(spec.libraryPath)
            if (spec.format == "elf") add("lib/${spec.loaderIdentity}")
            addAll(spec.importLibraryPaths)
        }

        fun consumerDigests(): Map<String, String> = consumers.mapValues { it.value.releaseDigest() }

        fun evidence(
            spec: CrossLanguageCAbiTargetSpec,
            snapshot: CrossLanguageCAbiPackageSnapshot,
        ): JsonObject {
            val tools = when (spec.format) {
                "pe" -> setOf("c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport")
                else -> setOf("c", "cpp", "file", "architecture", "symbols", "loader", "versions")
            }.associateWith { it.encodeToByteArray().inputStream().releaseDigest() }
            val version = when (spec.format) {
                "mach-o" -> "compatibility=1.0.0,current=1.12.0"
                "elf" -> (0..12).joinToString(",") { "CODEX_AGENT_1.$it" }
                else -> "abi=1.12"
            }
            val proofs = consumers.map { (name, source) ->
                val compileOnly = name in crossLanguageCAbiCompileOnlyConsumers
                CrossLanguageCAbiConsumerProof(
                    name,
                    source.releaseDigest(),
                    if (name.endsWith(".cpp")) "c++17" else "c11",
                    tools.getValue(if (name.endsWith(".cpp")) "cpp" else "c"),
                    "5".repeat(64),
                    "6".repeat(64),
                    linked = !compileOnly,
                    executed = !compileOnly,
                    exitCode = 0,
                )
            }
            val gnuProofs = if (spec.format == "pe") {
                proofs.filter { it.source in setOf("codex_agent_abi_smoke.c", "codex_agent_header_smoke.cpp") }
                    .map { proof ->
                        proof.copy(
                            compilerIdentitySha256 = tools.getValue(
                                if (proof.source.endsWith(".cpp")) "gnuCpp" else "gnuC",
                            ),
                            linked = true,
                            executed = true,
                        )
                    }
            } else {
                emptyList()
            }
            val symbolVersions = if (spec.format == "elf") crossLanguageCAbiLinuxSymbolVersions(linuxPolicy) else emptyMap()
            return buildCrossLanguageCAbiPackageEvidence(CrossLanguageCAbiEvidenceValues(
                spec.target,
                spec.classifier,
                "0.2.0",
                "a".repeat(40),
                "b".repeat(40),
                spec.runnerOs,
                spec.runnerArch,
                snapshot.archiveSha256,
                snapshot.headerSha256,
                snapshot.librarySha256,
                symbols.toSet(),
                symbolVersions,
                spec.format,
                spec.architecture,
                spec.loaderIdentity,
                version,
                spec.importLibraryPaths.associateWith(snapshot.members::getValue),
                tools,
                proofs,
                gnuProofs,
            ))
        }
    }
}

private inline fun <T> withFixture(block: (CrossLanguageCAbiPackageEvidenceTest.Fixture) -> T): T {
    val fixture = CrossLanguageCAbiPackageEvidenceTest.Fixture()
    return try {
        block(fixture)
    } finally {
        fixture.root.deleteRecursively()
    }
}

private fun zipNames(file: File): Set<String> = ZipFile(file).use { archive ->
    archive.entries().asSequence().map(ZipEntry::getName).toSet()
}

private fun rewriteZip(
    source: File,
    target: File,
    replacements: Map<String, ByteArray> = emptyMap(),
    drop: Set<String> = emptySet(),
    additions: Map<String, ByteArray> = emptyMap(),
    timestamp: LocalDateTime = LocalDateTime.of(1980, 1, 1, 0, 0),
) {
    val members = ZipFile(source).use { archive ->
        archive.entries().asSequence().filterNot { it.name in drop }.associate { entry ->
            entry.name to (replacements[entry.name]
                ?: archive.getInputStream(entry).use { it.readBytes() })
        }
    } + additions
    ZipOutputStream(target.outputStream()).use { output ->
        members.toSortedMap().forEach { (name, bytes) ->
            output.putNextEntry(ZipEntry(name).apply { setTimeLocal(timestamp) })
            output.write(bytes)
            output.closeEntry()
        }
    }
    patchDesktopRuntimeUnixModes(target, emptySet())
}

private fun JsonObject.with(name: String, value: kotlinx.serialization.json.JsonElement): JsonObject =
    JsonObject(this + (name to value))

private fun JsonObject.mapFirstConsumer(transform: (JsonObject) -> JsonObject): JsonObject = with(
    "consumers",
    JsonArray(getValue("consumers").jsonArray.mapIndexed { index, value ->
        if (index == 0) transform(value.jsonObject) else value
    }),
)

private fun JsonObject.mapFirstGnuConsumer(transform: (JsonObject) -> JsonObject): JsonObject = with(
    "gnuConsumers",
    JsonArray(getValue("gnuConsumers").jsonArray.mapIndexed { index, value ->
        if (index == 0) transform(value.jsonObject) else value
    }),
)

private fun JsonObject.mapConsumerNamed(
    source: String,
    transform: (JsonObject) -> JsonObject,
): JsonObject = with(
    "consumers",
    JsonArray(getValue("consumers").jsonArray.map { value ->
        if (value.jsonObject.getValue("source").jsonPrimitive.content == source) transform(value.jsonObject) else value
    }),
)
