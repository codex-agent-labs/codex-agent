import java.io.File
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class CrossLanguageSupportMatrixTest {
    @Test
    fun `support matrix is the exact M11 binding and receipt inventory`() {
        val document = File("../../docs/SUPPORT_MATRIX.md").readText()
        val body = document.substringAfter("<!-- binding-support:start -->")
            .substringBefore("<!-- binding-support:end -->")
        val rows = body.lineSequence().mapNotNull { line ->
            Regex("""^\| `([^`]+)` \|.*\| `([^`]+-parity\.json)` \|$""")
                .matchEntire(line)
                ?.destructured
                ?.let { (language, receipt) -> language to receipt }
        }.toList()

        assertTrue(CrossLanguageBinding.entries.all { it.isActive(CrossLanguageBindingPhase.M11) })
        assertEquals(
            CrossLanguageBinding.entries.map { language ->
                language.id to "${language.id}-parity.json"
            },
            rows,
        )
        assertTrue("[language and platform support](docs/SUPPORT_MATRIX.md)" in File("../../README.md").readText())
        listOf(
            "python/consumer/lifecycle_example.py",
            "csharp/samples/CodexAgent.Consumer/Program.cs",
            "rust/consumer/src/bin/lifecycle_smoke.rs",
            "cpp/consumer/lifecycle_example.cpp",
            "dart/example/main.dart",
        ).forEach { path ->
            assertTrue(File("../../codex-agent-bindings/$path").isFile, path)
        }
    }
}
