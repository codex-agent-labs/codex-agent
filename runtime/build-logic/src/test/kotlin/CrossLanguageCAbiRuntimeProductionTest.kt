import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import org.gradle.api.tasks.CacheableTask
import org.gradle.testfixtures.ProjectBuilder
import org.gradle.work.DisableCachingByDefault

class CrossLanguageCAbiRuntimeProductionTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-desktop").isDirectory }

    @Test
    fun `tool inspection and Runtime task declarations are Runtime owned`() {
        val removedSharedSource = repository.resolve(
            "gradle/product-build-support/src/main/kotlin/CrossLanguageCAbiPackageEvidence.kt",
        )
        val client = repository.resolve(
            "runtime/build-logic/src/main/kotlin/RuntimeCAbiClient.kt",
        ).readText()
        val runtime = repository.resolve(
            "runtime/build-logic/src/main/kotlin/CrossLanguageCAbiRuntimeProduction.kt",
        ).readText()
        assertFalse(removedSharedSource.exists(), "Obsolete shared C ABI implementation source still exists")
        listOf(
            "fun crossLanguageCAbiLinuxDynamicSymbolVersions",
            "abstract class PackageCrossLanguageCAbiSdkTask",
            "abstract class GenerateCrossLanguageCAbiPackageEvidenceTask",
            "abstract class VerifyCrossLanguageCAbiPackageEvidenceTask",
            "fun crossLanguageCAbiGnuImportSymbols",
        ).forEach { declaration ->
            assertFalse(declaration in client, "Runtime Python client incorrectly owns $declaration")
            assertTrue(declaration in runtime, "Runtime C ABI source does not own $declaration")
        }
        listOf(
            "abstract class RuntimeCAbiCatalogValueSource",
            "data class CrossLanguageCAbiPackageInput",
            "data class CrossLanguageCAbiConsumerProof",
            "fun packageCrossLanguageCAbiSdk",
            "fun inspectAndStageCrossLanguageCAbiPackage",
            "fun describeCrossLanguageCAbiExportPolicy",
            "fun buildCrossLanguageCAbiPackageEvidence",
            "fun verifyCrossLanguageCAbiPackageEvidence",
            "\"describe-export-policy\"",
            "\"--output-directory\"",
            "listOf(\"evidence-write\")",
            "listOf(\"evidence-verify\")",
        ).forEach { contract -> assertTrue(contract in client, "Missing Runtime C ABI Python client contract: $contract") }
        listOf("ZipFile", "ZipOutputStream", "verifyCAbiPackageManifest", "extractCAbiPackage").forEach { duplicate ->
            assertFalse(duplicate in client, "Runtime C ABI client duplicates Python package semantics: $duplicate")
        }
    }

    @Test
    fun `Python catalog parser preserves exact targets tools and consumer inventory`() {
        val catalog = readRuntimeCAbiCatalog(runRuntimeProductPythonModule("c_abi", listOf("describe")))
        assertEquals("1.12", catalog.current)
        assertEquals("1.0", catalog.minimum)
        assertEquals("0x010c0000", catalog.encoded)
        assertEquals(777, catalog.symbolCount)
        assertEquals(
            setOf("macosArm64", "macosX64", "linuxArm64", "linuxX64", "mingwX64"),
            catalog.targets.keys,
        )
        assertEquals(setOf("mach-o", "elf", "pe"), catalog.targets.values.map { it.format }.toSet())
        val unixTools = setOf("c", "cpp", "file", "architecture", "symbols", "loader", "versions")
        listOf("macosArm64", "macosX64", "linuxArm64", "linuxX64").forEach { target ->
            assertEquals(unixTools, catalog.targets.getValue(target).requiredToolIds(), target)
        }
        assertEquals(
            setOf("c", "cpp", "gnuC", "gnuCpp", "architecture", "symbols", "msvcImport", "gnuImport"),
            catalog.targets.getValue("mingwX64").requiredToolIds(),
        )
        val consumerDirectory = repository.resolve("codex-agent-runtime-desktop/native/c-api/consumer")
        val exactConsumers = consumerDirectory.listFiles().orEmpty()
            .filter { it.isFile && it.extension in setOf("c", "cpp") }
            .map(File::getName)
            .toSet()
        assertEquals(30, exactConsumers.size)
        assertEquals(exactConsumers, catalog.strictConsumers)
        assertEquals(setOf("codex_agent_lifecycle_compile.cpp"), catalog.compileOnlyConsumers)
        assertEquals(setOf("codex_agent_abi_smoke.c", "codex_agent_header_smoke.cpp"), catalog.gnuConsumers)
        assertEquals("macosArm64", catalog.hostTarget("Mac OS X", "aarch64"))
        assertEquals("linuxX64", catalog.hostTarget("Linux", "amd64"))
        assertEquals("mingwX64", catalog.hostTarget("Windows 11", "x86_64"))
        assertEquals(null, catalog.hostTarget("FreeBSD", "x86_64"))
        assertFailsWith<IllegalStateException> { readRuntimeCAbiCatalog("{}\n") }
        assertFailsWith<IllegalStateException> {
            readRuntimeCAbiCatalog(runRuntimeProductPythonModule("c_abi", listOf("describe")).trimEnd() + " \n")
        }
    }

    @Test
    fun `Python export policy projection preserves every symbol and Linux version assignment`() {
        val policies = mapOf(
            "mach-o" to repository.resolve("codex-agent-runtime-desktop/native/c-api/exports/macos.exports"),
            "elf" to repository.resolve("codex-agent-runtime-desktop/native/c-api/exports/linux.map"),
            "pe" to repository.resolve("codex-agent-runtime-desktop/native/c-api/exports/windows.def"),
        )
        policies.forEach { (format, file) ->
            val policy = describeCrossLanguageCAbiExportPolicy(file, format)
            assertEquals(777, policy.publicSymbols.size, format)
            if (format == "elf") {
                assertEquals(policy.publicSymbols, policy.publicSymbolVersions.keys)
                assertEquals((0..12).mapTo(sortedSetOf()) { "CODEX_AGENT_1.$it" },
                    policy.publicSymbolVersions.values.toSet())
            } else {
                assertTrue(policy.publicSymbolVersions.isEmpty(), format)
            }
        }
    }

    @Test
    fun `desktop plugin wires exact five packages host proofs imports and publication classifiers`() {
        val wiring = sequenceOf(
            repository.resolve("runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts"),
            repository.resolve("gradle/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts"),
        ).first(File::isFile).readText()
        listOf(
            "package${'$'}{target.replaceFirstChar(Char::uppercase)}CAbiSdk",
            "generate${'$'}{targetTitle}CAbiPackageEvidence",
            "generateMingwX64MsvcImportLibrary",
            "codexAgent.candidateCommit",
            "codexAgent.candidateTree",
            "codexAgent.desktopClassifierDirectory",
            "val desktopRuntimeCompatibilityVersion = providers.provider {",
            "runtimeCompatibilityVersion(project.version.toString())",
            "cAbiArchiveFileName(version, target)",
            "cAbiPackageEvidenceFileName(distribution.target)",
            "native/c-api/include/codex_agent.h",
            "native/c-api/exports/macos.exports",
            "native/c-api/exports/linux.map",
            "native/c-api/exports/windows.def",
            "repositoryRootFile.resolve(\"LICENSE\")",
            "repositoryRootFile.resolve(\"THIRD_PARTY_NOTICES.md\")",
            "libcodex_agent.dll.a",
            "-Wl,--out-implib,${'$'}{mingwGnuImportLibrary.get().asFile.absolutePath}",
            "outputs.file(mingwGnuImportLibrary)",
            "/machine:x64",
            "/brepro",
            "cAbiToolDefaults(distribution.target)",
            "cAbiCatalog.compileOnlyConsumers.sorted()",
            "tasks.withType<KotlinNativeTest>().matching { it.name == testTaskName }.configureEach",
            "dependsOn(validateEvidenceTarget, testTaskName)",
            "val localCAbiRunner = hostTarget?.let(cAbiTargetSpecs::getValue)",
            ".orElse(localCAbiRunner?.runnerOs ?: \"unsupported\")",
            ".orElse(localCAbiRunner?.runnerArch ?: \"unsupported\")",
            "artifact(cAbiArchiveFiles.getValue(target))",
            "c-abi-reference",
        ).forEach { contract -> assertTrue(contract in wiring, "Missing desktop C ABI wiring: $contract") }
        assertFalse("StageCrossLanguageNativeWrapperSdksTask" in wiring)
        assertFalse("MaterializeCrossLanguageNativeWrapperPackageAssetsTask" in wiring)
        assertEquals(1, Regex("artifact\\(cAbiArchiveFiles\\.getValue\\(target\\)\\)").findAll(wiring).count())
        assertTrue("check(runnerOs.get() == spec.runnerOs && runnerArch.get() == spec.runnerArch)" in
            repository.resolve("runtime/build-logic/src/main/kotlin/CrossLanguageCAbiRuntimeProduction.kt").readText())
        assertFalse("tasks.named<KotlinNativeTest>(testTaskName)" in wiring)
        assertFalse("runtime-python" in wiring)
        assertFalse("libraryVersion.set(project.version" in wiring)
        assertFalse("cAbiArchiveFileName(project.version" in wiring)
        assertFalse("codex-agent-runtime-desktop-${'$'}{project.version" in wiring)
        assertTrue("providers.of(RuntimeCAbiCatalogValueSource::class.java) {}.get()" in wiring)
        assertFalse("runRuntimeProductPythonModule(\"c_abi\", listOf(\"describe\"))" in wiring)
        assertFalse("crossLanguageCAbiTargetSpecs" in wiring)
        val projectWiring = repository.resolve("codex-agent-runtime-desktop/build.gradle.kts").readText()
        assertTrue("providers.of(RuntimeCAbiCatalogValueSource::class.java) {}.get()" in projectWiring)
        listOf(
            "crossLanguageCAbiHostTarget(",
            "crossLanguageCAbiTargetSpecs",
            "runRuntimeProductPythonModule(\"c_abi\", listOf(\"describe\"))",
        ).forEach { unsafe ->
            assertFalse(unsafe in projectWiring, "Desktop project configuration bypasses catalog ValueSource: $unsafe")
        }
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
    fun `raw ELF dynamic symbols require every exact symbol on its exact version node`() {
        val expected = sortedMapOf(
            "codex_agent_first" to "CODEX_AGENT_1.0",
            "codex_agent_second" to "CODEX_AGENT_1.12",
        )
        val raw = expected.entries.joinToString("\n") { (symbol, version) -> "00000000 T $symbol@@$version" }
        assertEquals(expected, crossLanguageCAbiLinuxDynamicSymbolVersions(raw, expected))
        assertFailsWith<IllegalStateException> {
            crossLanguageCAbiLinuxDynamicSymbolVersions(raw.replace("@@CODEX_AGENT_1.0", ""), expected)
        }
        assertFailsWith<IllegalStateException> {
            crossLanguageCAbiLinuxDynamicSymbolVersions(
                raw.replace("codex_agent_first@@CODEX_AGENT_1.0", "codex_agent_first@@CODEX_AGENT_1.12"),
                expected,
            )
        }
    }

    @Test
    fun `Runtime Gradle task cache boundaries match tool execution behavior`() {
        val task = ProjectBuilder.builder().build().tasks.register(
            "generateCAbiPackageEvidence",
            GenerateCrossLanguageCAbiPackageEvidenceTask::class.java,
        ).get()
        assertFalse(task.outputs.upToDateSpec.isSatisfiedBy(task))
        assertNotNull(PackageCrossLanguageCAbiSdkTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(VerifyCrossLanguageCAbiPackageEvidenceTask::class.java.getAnnotation(CacheableTask::class.java))
        assertNotNull(
            GenerateCrossLanguageCAbiPackageEvidenceTask::class.java.getAnnotation(DisableCachingByDefault::class.java),
        )
    }
}
