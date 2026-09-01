import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.tasks.CacheableTask
import org.gradle.testfixtures.ProjectBuilder

class GenerateRuntimeAbiSourceTaskTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("runtime/settings.gradle.kts").isFile }
    private val contract = repository.resolve("codex-agent-runtime-desktop/native/c-api/abi-contract.json")
    private val cAbiRoot = repository.resolve("codex-agent-runtime-desktop/native/c-api")

    private val digestA = "sha256:" + "a".repeat(64)
    private val digestB = "sha256:" + "b".repeat(64)
    private val digestC = "sha256:" + "c".repeat(64)

    private fun identityJson(componentId: String = digestC): String =
        """{"appServerVersion":"0.149.0","buildInputDigest":"$digestA","cAbiVersion":"1.13.0","componentId":"$componentId","contractComponentDigest":"$digestB","contractDigest":"$digestA","runtimeCompatibilityVersion":"0.2.0","schemaVersion":1,"target":"macos-arm64"}"""

    private fun envelope(runtimeIdentity: String = identityJson()): String =
        """{"appServer":{"binarySha256":"$digestC","releaseTag":"rust-v0.149.0","version":"0.149.0"},"binaryBuildKey":"$digestA","cAbi":{"headerSha256":"$digestA","identitySchemaVersion":1,"minimumCompatibleVersion":"1.0.0","symbolCount":778,"symbolSetSha256":"$digestB","version":"1.13.0"},"componentId":"$digestC","contract":{"componentDigest":"$digestB","digest":"$digestA"},"runtimeCompatibilityVersion":"0.2.0","runtimeIdentityJson":${JsonPrimitive(runtimeIdentity)},"schemaVersion":1,"target":"macos-arm64","toolchainProfile":{"digest":"$digestA","id":"macos-arm64"}}""" + "\n"

    private fun syntheticRepository(root: File, identityEnvelope: String): File {
        val products = root.resolve("ci/products").also(File::mkdirs)
        root.resolve("ci/__init__.py").writeText("")
        products.resolve("__init__.py").writeText("")
        products.resolve("fixture.json").writeText(identityEnvelope)
        products.resolve("runtime_identity.py").writeText(
            """
            import argparse
            from pathlib import Path
            parser = argparse.ArgumentParser()
            parser.add_argument("--plan", required=True)
            parser.add_argument("--repository-root", required=True)
            parser.add_argument("--repository-revision", required=True)
            parser.add_argument("--verified-contract-manifest", required=True)
            parser.add_argument("--expected-target", required=True)
            parser.add_argument("--expected-runtime-version", required=True)
            parser.add_argument("--expected-flags-digest", required=True)
            parser.add_argument("--output", required=True)
            arguments = parser.parse_args()
            root = Path(arguments.repository_root).resolve()
            assert root == Path.cwd().resolve()
            assert arguments.repository_revision == "${"1".repeat(40)}"
            assert arguments.expected_target == "macos-arm64"
            assert arguments.expected_runtime_version == "0.2.0"
            assert arguments.expected_flags_digest == "$digestA"
            Path(arguments.plan).read_bytes()
            Path(arguments.verified_contract_manifest).read_bytes()
            Path(arguments.output).write_bytes(Path(__file__).with_name("fixture.json").read_bytes())
            """.trimIndent() + "\n",
        )
        return root
    }

    @Test
    fun `generates exact deterministic Runtime ABI constants through Python authority`() {
        val root = createTempDirectory("runtime-abi-source").toFile()
        try {
            val syntheticRepository = syntheticRepository(root.resolve("repository"), envelope())
            val plan = root.resolve("plan.json").apply { writeText("{}\n") }
            val verifiedManifest = root.resolve("contract-manifest.json").apply { writeText("{}\n") }
            val tasks = ProjectBuilder.builder().withProjectDir(root).build().tasks
            fun generate(name: String, directory: File) = tasks.register(
                name,
                GenerateRuntimeAbiSourceTask::class.java,
            ).get().apply {
                runtimeBinaryPlan.set(plan)
                repositoryRevision.set("1".repeat(40))
                expectedTarget.set("macos-arm64")
                runtimeVersion.set("0.2.0")
                expectedFlagsDigest.set(digestA)
                verifiedContractManifest.set(verifiedManifest)
                repositoryRoot.set(syntheticRepository)
                abiContractFile.set(contract)
                reviewedHeaderFile.set(cAbiRoot.resolve("include/codex_agent.h"))
                macosExportsFile.set(cAbiRoot.resolve("exports/macos.exports"))
                linuxMapFile.set(cAbiRoot.resolve("exports/linux.map"))
                windowsDefFile.set(cAbiRoot.resolve("exports/windows.def"))
                outputDirectory.set(directory)
                generate()
            }

            val first = root.resolve("first")
            val second = root.resolve("second")
            first.resolve("Extra.kt").apply {
                parentFile.mkdirs()
                writeText("stale")
            }
            generate("generateFirst", first)
            generate("generateSecond", second)
            val expected = """
                package io.github.codex_agent_labs.codexagent.capi

                internal const val GENERATED_ABI_VERSION_CURRENT: UInt = 0x010D0000u
                internal const val GENERATED_ABI_VERSION_MINIMUM_COMPATIBLE: UInt = 0x01000000u
                internal const val GENERATED_RUNTIME_IDENTITY_SCHEMA_VERSION: Int = 1
                internal const val GENERATED_RUNTIME_IDENTITY_JSON: String = ${JsonPrimitive(identityJson())}
            """.trimIndent() + "\n"
            val firstSource = first.walkTopDown().single(File::isFile)
            val secondSource = second.walkTopDown().single(File::isFile)
            assertEquals(expected, firstSource.readText())
            assertContentEquals(firstSource.readBytes(), secondSource.readBytes())
            assertEquals(1, first.walkTopDown().count(File::isFile))
            assertNotNull(GenerateRuntimeAbiSourceTask::class.java.getAnnotation(CacheableTask::class.java))
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `rejects a Python envelope whose embedded identity is inconsistent`() {
        val root = createTempDirectory("runtime-abi-source-invalid").toFile()
        try {
            val invalid = identityJson(componentId = digestB)
            val syntheticRepository = syntheticRepository(root.resolve("repository"), envelope(invalid))
            val task = ProjectBuilder.builder().withProjectDir(root).build().tasks.register(
                "generateInvalid",
                GenerateRuntimeAbiSourceTask::class.java,
            ).get().apply {
                runtimeBinaryPlan.set(root.resolve("plan.json").apply { writeText("{}\n") })
                repositoryRevision.set("1".repeat(40))
                expectedTarget.set("macos-arm64")
                runtimeVersion.set("0.2.0")
                expectedFlagsDigest.set(digestA)
                verifiedContractManifest.set(root.resolve("manifest.json").apply { writeText("{}\n") })
                repositoryRoot.set(syntheticRepository)
                abiContractFile.set(contract)
                reviewedHeaderFile.set(cAbiRoot.resolve("include/codex_agent.h"))
                macosExportsFile.set(cAbiRoot.resolve("exports/macos.exports"))
                linuxMapFile.set(cAbiRoot.resolve("exports/linux.map"))
                windowsDefFile.set(cAbiRoot.resolve("exports/windows.def"))
                outputDirectory.set(root.resolve("generated"))
            }
            val stale = root.resolve(
                "generated/io/github/codex_agent_labs/codexagent/capi/RuntimeAbi.generated.kt",
            ).apply {
                parentFile.mkdirs()
                writeText("stale")
            }
            assertFailsWith<IllegalStateException> { task.generate() }
            assertFalse(stale.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `desktop plugin wires authority into native source and linker`() {
        val wiring = repository.resolve(
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ).readText()
        val settings = repository.resolve("runtime/settings.gradle.kts").readText()
        assertTrue("parameters.abiContractFile.set(runtimeAbiContractFile)" in wiring)
        assertTrue("runtimeBinaryPlan.set(" in wiring)
        assertTrue("providers.gradleProperty(\"codexAgent.runtimeBinaryPlan\")" in wiring)
        assertTrue("repositoryRevision.set(providers.gradleProperty(\"codexAgent.repositoryRevision\"))" in wiring)
        assertTrue("expectedTarget.set(providers.gradleProperty(\"codexAgent.target\"))" in wiring)
        assertTrue("runtimeVersion.set(runtimeProductVersion)" in wiring)
        assertTrue("expectedFlagsDigest.set(providers.gradleProperty(\"codexAgent.runtimeBinaryFlagsDigest\"))" in wiring)
        assertTrue("verifiedContractManifest.set(" in wiring)
        assertTrue("rootProject.extra[\"codexAgent.verifiedContractManifest\"]" in wiring)
        assertFalse("verifiedContractManifest.set(\n        layout.file(providers.gradleProperty(\"codexAgent.contractManifest\")" in wiring)
        assertTrue("repositoryRoot.set(repositoryRootDirectory)" in wiring)
        assertTrue("reviewedHeaderFile.set(runtimeAbiHeaderFile)" in wiring)
        assertTrue("macosExportsFile.set(runtimeAbiMacosExportsFile)" in wiring)
        assertTrue("linuxMapFile.set(runtimeAbiLinuxMapFile)" in wiring)
        assertTrue("windowsDefFile.set(runtimeAbiWindowsDefFile)" in wiring)
        assertTrue("sourceSets.getByName(\"nativeMain\").kotlin.srcDir(generateRuntimeAbiSource)" in wiring)
        assertFalse("tasks.withType<PackageCrossLanguageCAbiSdkTask>().configureEach" in wiring)
        assertTrue("python3\", \"-m\", \"ci.products.runtime_identity\"" in settings)
        assertTrue(settings.indexOf("ci.products.runtime_identity") < settings.indexOf("includeBuild(runtimeBuildLogic.toFile())"))
        assertTrue("\"--verified-contract-manifest\", verifiedContractManifest.toString()" in settings)
        assertTrue("binaryPlan.toRealPath() == binaryPlan" in settings)
    }
}
