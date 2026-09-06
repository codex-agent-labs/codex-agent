import java.io.File
import java.io.InputStream
import java.nio.charset.CharacterCodingException
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeProductPythonToolingTest {
    @Test
    fun `existing packaged modules retain their entrypoints and strict allowlist`() {
        assertTrue("targets" in runRuntimeProductPythonModule("c_abi", listOf("describe")))
        assertTrue("inspect-manifest" in runRuntimeProductPythonModule("runtime_evidence", listOf("--help")))
        assertFailsWith<IllegalStateException> { runRuntimeProductPythonModule("contract", emptyList()) }
    }

    @Test
    fun `each invocation uses a fresh regular package and isolated interpreter`() {
        val roots = (1..2).map {
            File(runRuntimeProductPythonModule("runtime_evidence", listOf("with spaces", "é"), resources("""
                from pathlib import Path
                import ci, sys
                assert sys.flags.isolated == 1
                assert sys.flags.ignore_environment == 1
                assert sys.flags.no_site == 1
                assert sys.flags.no_user_site == 1
                assert sys.flags.dont_write_bytecode == 1
                assert 'site' not in sys.modules
                root = Path(__file__).resolve().parents[2]
                assert Path(ci.__file__) == root / 'ci/__init__.py'
                assert sys.path[0] == str(root)
                assert sys.argv[1:] == ['with spaces', 'é']
                print(root)
            """.trimIndent())).trim())
        }
        assertTrue(roots[0] != roots[1])
        roots.forEach { assertFalse(it.exists(), "Private extraction survived its invocation: $it") }
    }

    @Test
    fun `successful subprocess cannot alter its retained source or add unchecked bytecode`() = withDirectory { root ->
        val mutations = listOf(
            "Path(__file__).write_bytes(Path(__file__).read_bytes() + b'\\n# changed')",
            """
                import py_compile
                py_compile.compile(__file__, doraise=True,
                    invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
            """.trimIndent(),
            "Path(__file__).parent.joinpath('unexpected-empty-directory').mkdir()",
        )
        mutations.forEachIndexed { index, mutation ->
            val marker = root.resolve("captured-$index")
            val failure = assertFailsWith<IllegalStateException> {
                runRuntimeProductPythonModule("runtime_evidence", listOf(marker.absolutePath), resources("""
                    from pathlib import Path
                    import sys
                    Path(sys.argv[1]).write_text(str(Path(__file__).resolve().parents[2]))
                """.trimIndent() + "\n" + mutation + "\nprint('success')\n"))
            }
            assertTrue("resources changed during execution" in checkNotNull(failure.message))
            assertFalse(File(marker.readText()).exists(), "Rejected private extraction was not removed")
        }
    }

    @Test
    fun `nonzero process and malformed UTF8 retain failure behavior and clean private source`() = withDirectory { root ->
        val marker = root.resolve("captured")
        val prefix = """
            from pathlib import Path
            import sys, os
            Path(sys.argv[1]).write_text(str(Path(__file__).resolve().parents[2]))
        """.trimIndent() + "\n"
        val failure = assertFailsWith<IllegalStateException> {
            runRuntimeProductPythonModule("runtime_evidence", listOf(marker.absolutePath),
                resources(prefix + "print('actual failure'); sys.exit(7)\n"))
        }
        assertTrue("failed (7): actual failure" in checkNotNull(failure.message))
        assertFalse(File(marker.readText()).exists())
        assertFailsWith<CharacterCodingException> {
            runRuntimeProductPythonModule("runtime_evidence", listOf(marker.absolutePath),
                resources(prefix + "os.write(1, b'\\xff')\n"))
        }
        assertFalse(File(marker.readText()).exists())
    }

    @Test
    fun `missing packaged resource cannot fall through to checkout or ambient Python`() {
        val failure = assertFailsWith<IllegalStateException> {
            runRuntimeProductPythonModule("runtime_evidence", listOf("--help")) { null }
        }
        assertEquals("Packaged Runtime product Python resource is missing: python/ci/products/__init__.py",
            failure.message)
    }

    private fun resources(script: String): (String) -> InputStream? = { name ->
        if (name == "python/ci/products/runtime_evidence.py") script.byteInputStream(Charsets.UTF_8)
        else javaClass.classLoader.getResourceAsStream(name)
    }

    private fun withDirectory(block: (File) -> Unit) {
        val root = createTempDirectory("runtime-python-tooling-test-").toFile().canonicalFile
        try { block(root) } finally { root.deleteRecursively() }
    }
}
