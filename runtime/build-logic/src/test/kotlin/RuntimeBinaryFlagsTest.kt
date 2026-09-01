import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class RuntimeBinaryFlagsTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-desktop").isDirectory }
    private val authority = repository.resolve("codex-agent-runtime-desktop/native/c-api/binary-flags.json")

    @Test
    fun `packaged Python authority projects exact target digests and Gradle arguments`() {
        val records = readRuntimeBinaryFlags(runRuntimeProductPythonModule(
            "runtime_flags", listOf("describe-all", "--file", authority.absolutePath),
        ))
        assertEquals(
            listOf("linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64"),
            records.keys.toList(),
        )
        assertEquals(5, records.values.map { it.flagsDigest }.toSet().size)
        val output = repository.resolve("codex-agent-runtime-desktop/build")
        val windows = records.getValue("windows-x64")
        assertEquals(
            repository.resolve("codex-agent-runtime-desktop/native/c-api/exports/windows.def"),
            windows.roleFile("exportPolicy", repository, output),
        )
        assertEquals(
            listOf(
                "/nologo",
                "/machine:x64",
                "/brepro",
                "/def:${repository.resolve("codex-agent-runtime-desktop/native/c-api/exports/windows.def")}",
                "/out:${output.resolve("c-abi/mingwX64/codex_agent.lib")}",
            ),
            windows.resolvedMsvcOptions(repository, output),
        )
        assertTrue(windows.resolvedLinkerArguments(repository, output).none { "@role(" in it })
    }

    @Test
    fun `ABI cross-check rejects independently drifting macOS versions`() {
        val records = readRuntimeBinaryFlags(runRuntimeProductPythonModule(
            "runtime_flags", listOf("describe-all", "--file", authority.absolutePath),
        ))
        verifyRuntimeBinaryFlagsAgainstAbi(records, RuntimeAbiContract("1.13.0", "", "1.0.0", "", 1))
        verifyRuntimeBinaryFlagsAgainstPlan(
            records,
            "macos-arm64",
            records.getValue("macos-arm64").flagsDigest,
        )
        assertFailsWith<IllegalStateException> {
            verifyRuntimeBinaryFlagsAgainstAbi(records, RuntimeAbiContract("1.14.0", "", "1.0.0", "", 1))
        }
        assertFailsWith<IllegalStateException> {
            verifyRuntimeBinaryFlagsAgainstPlan(records, "macos-arm64", "sha256:" + "0".repeat(64))
        }
    }

    @Test
    fun `supervisor and desktop plugin contain no independent production flags`() {
        val supervisor = repository.resolve(
            "runtime/build-logic/src/main/kotlin/CompileDesktopProcessSupervisorTask.kt",
        ).readText()
        val plugin = repository.resolve(
            "runtime/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ).readText()
        listOf("-std=c11", "-D_POSIX_C_SOURCE=200809L", "\"/O2\"", "\"/W4\"", "\"/WX\"").forEach {
            assertTrue(it !in supervisor, "Supervisor task hard-codes Runtime binary flag: $it")
        }
        assertTrue("compilerArguments.get()" in supervisor)
        assertTrue("supervisorCompilerArguments" in plugin)
        assertTrue("codexAgentRuntimeBinaryFlagsDigest" in plugin)
        assertTrue("codexAgent.runtimeBinaryFlagsDigest" in plugin)
        assertTrue("verifyRuntimeBinaryFlagsAgainstPlan(" in plugin)
        assertTrue("inputs.file(runtimeBinaryFlagsFile)" !in plugin)
        val settings = repository.resolve("runtime/settings.gradle.kts").readText()
        assertTrue("must be supplied only as an explicit -P project property" in settings)
    }

    @Test
    fun `Kotlin projection and role resolution fail closed`() {
        assertFailsWith<IllegalStateException> { readRuntimeBinaryFlags("{}\n") }
        val workspace = createTempDirectory("runtime-binary-flags-").toFile().canonicalFile
        try {
            val repositoryRoot = workspace.resolve("repository").also(File::mkdirs)
            val outputRoot = workspace.resolve("output").also(File::mkdirs)
            val outside = workspace.resolve("outside.def").also { it.writeText("EXPORTS\n") }
            val escaping = RuntimeBinaryFlags(
                "windows-x64", emptyList(), emptyList(), emptyList(), emptyList(),
                mapOf("exportPolicy" to RuntimeBinaryFlagRole("exportPolicy", "repository", "../outside.def")),
                "sha256:" + "0".repeat(64),
            )
            assertFailsWith<IllegalStateException> {
                escaping.roleFile("exportPolicy", repositoryRoot, outputRoot)
            }
            val link = repositoryRoot.resolve("linked.def")
            try {
                Files.createSymbolicLink(link.toPath(), outside.toPath())
                val symbolic = escaping.copy(
                    roles = mapOf(
                        "exportPolicy" to RuntimeBinaryFlagRole("exportPolicy", "repository", "linked.def"),
                    ),
                )
                assertFailsWith<IllegalStateException> {
                    symbolic.roleFile("exportPolicy", repositoryRoot, outputRoot)
                }
            } catch (_: UnsupportedOperationException) {
                // The traversal check above remains mandatory where symbolic links are unavailable.
            }
        } finally {
            workspace.deleteRecursively()
        }
    }
}
