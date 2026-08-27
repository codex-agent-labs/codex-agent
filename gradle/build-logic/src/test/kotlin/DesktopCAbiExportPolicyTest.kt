import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class DesktopCAbiExportPolicyTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("gradle/build-logic").isDirectory }

    @Test
    fun `all native C ABI targets have exact export and loader policy`() {
        val exports = repository.resolve("codex-agent-runtime-desktop/native/c-api/exports")
        assertEquals(
            listOf(
                "_codex_agent_abi_is_compatible",
                "_codex_agent_abi_version",
                "_codex_agent_context_create",
                "_codex_agent_context_destroy",
            ),
            exports.resolve("macos.exports").readLines(),
        )
        assertEquals(
            """CODEX_AGENT_1.0 {
    global:
        codex_agent_abi_is_compatible;
        codex_agent_abi_version;
        codex_agent_context_create;
        codex_agent_context_destroy;
    local:
        *;
};
""",
            exports.resolve("linux.map").readText(),
        )
        assertEquals(
            """LIBRARY codex_agent.dll
EXPORTS
    codex_agent_abi_is_compatible
    codex_agent_abi_version
    codex_agent_context_create
    codex_agent_context_destroy
""",
            exports.resolve("windows.def").readText(),
        )

        val plugin = repository.resolve(
            "gradle/build-logic/src/main/kotlin/codexagent.desktop-runtime.gradle.kts",
        ).readText()
        listOf(
            "target.name.startsWith(\"macos\")",
            "-Wl,-exported_symbols_list,",
            "-Wl,-install_name,@rpath/libcodex_agent.dylib",
            "-Wl,-compatibility_version,1.0.0",
            "-Wl,-current_version,1.0.0",
            "target.name.startsWith(\"linux\")",
            "-Wl,--version-script,",
            "-Wl,-soname,libcodex_agent.so.1",
            "target.name == \"mingwX64\"",
            "-Wl,--exclude-all-symbols",
            "native/c-api/exports/windows.def",
            "linkTaskProvider.configure",
            "inputs.file(exportPolicyFile)",
            ".withPropertyName(\"codexAgentCAbiExportPolicy\")",
            ".withPathSensitivity(PathSensitivity.RELATIVE)",
        ).forEach { expected ->
            assertTrue(expected in plugin, expected)
        }
    }
}
