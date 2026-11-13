import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse

class RuntimeEvidenceEnvironmentTest {
    @Test
    fun `evidence processes strip ambient execution overrides but retain declared runtime paths`() {
        val process = ProcessBuilder("unused")
        val environment = process.environment()
        listOf(
            "NODE_OPTIONS", "Node_Path", "JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS",
            "LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES",
            "DYLD_FRAMEWORK_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
        ).forEach { environment[it] = "untrusted" }
        environment["PATH"] = "ordinary-host-path"

        process.useRuntimeEvidenceEnvironment(mapOf("CODEX_HOME" to "declared-runtime-home"))

        assertFalse(environment.values.contains("untrusted"))
        assertEquals("ordinary-host-path", environment["PATH"])
        assertEquals("declared-runtime-home", environment["CODEX_HOME"])
    }

    @Test
    fun `declared C ABI loader paths replace ambient paths`() {
        val process = ProcessBuilder("unused")
        process.environment()["LD_LIBRARY_PATH"] = "ambient-linux-library"
        process.environment()["DYLD_LIBRARY_PATH"] = "ambient-macos-library"

        process.useRuntimeEvidenceEnvironment(mapOf(
            "LD_LIBRARY_PATH" to "/verified/linux/library",
            "DYLD_LIBRARY_PATH" to "/verified/macos/library",
        ))

        assertEquals("/verified/linux/library", process.environment()["LD_LIBRARY_PATH"])
        assertEquals("/verified/macos/library", process.environment()["DYLD_LIBRARY_PATH"])
    }

    @Test
    fun `declared execution override is rejected before changing process environment`() {
        val process = ProcessBuilder("unused")
        process.environment()["PATH"] = "unchanged"
        assertFailsWith<IllegalStateException> {
            process.useRuntimeEvidenceEnvironment(mapOf("node_options" to "--require=untrusted"))
        }
        assertFailsWith<IllegalStateException> {
            process.useRuntimeEvidenceEnvironment(mapOf("LD_PRELOAD" to "untrusted.so"))
        }
        assertFailsWith<IllegalStateException> {
            process.useRuntimeEvidenceEnvironment(mapOf("LD_AUDIT" to "untrusted.so"))
        }
        assertFailsWith<IllegalStateException> {
            process.useRuntimeEvidenceEnvironment(mapOf("DYLD_FRAMEWORK_PATH" to "untrusted"))
        }
        assertEquals("unchanged", process.environment()["PATH"])
    }
}
