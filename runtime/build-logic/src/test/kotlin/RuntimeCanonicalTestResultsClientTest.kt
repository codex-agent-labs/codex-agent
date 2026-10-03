import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class RuntimeCanonicalTestResultsClientTest {
    @Test
    fun `packaged Python tooling rejects modules outside the Runtime allowlist before extraction`() {
        val failure = assertFailsWith<IllegalStateException> {
            runRuntimeProductPythonModule("contract", emptyList())
        }
        assertTrue("Unsupported packaged Runtime product Python module" in failure.message.orEmpty())
    }

    @Test
    fun `parses the exact schema one status projection`() {
        val results = parseRuntimeCanonicalTestResults(
            """{"schemaVersion":1,"tests":[{"status":"passed","testId":"A#one"},{"status":"skipped","testId":"B#two"},{"status":"failed","testId":"C#three"}]}""" + "\n",
        )
        assertEquals(
            listOf(
                CanonicalTestResult("A#one", CanonicalTestStatus.PASSED),
                CanonicalTestResult("B#two", CanonicalTestStatus.SKIPPED),
                CanonicalTestResult("C#three", CanonicalTestStatus.FAILED),
            ),
            results,
        )
    }

    @Test
    fun `rejects framing schema type identity and status mutations`() {
        val mutations = listOf(
            "{}\n",
            """{"schemaVersion":2,"tests":[]}""" + "\n",
            """{"schemaVersion":"1","tests":[]}""" + "\n",
            """{"schemaVersion":1,"tests":{},"unexpected":true}""" + "\n",
            """{"schemaVersion":1,"tests":[{"status":"passed"}]}""" + "\n",
            """{"schemaVersion":1,"tests":[{"status":"unknown","testId":"A#one"}]}""" + "\n",
            """{"schemaVersion":1,"tests":[{"status":"passed","testId":""}]}""" + "\n",
            """{"tests":[],"schemaVersion":1}""" + "\n",
            """{ "schemaVersion":1,"tests":[]}""" + "\n",
            """{"schemaVersion":1,"tests":[]}""",
            """{"schemaVersion":1,"tests":[]}""" + "\n\n",
        )
        mutations.forEach { mutation ->
            val failure = assertFailsWith<IllegalStateException>(mutation) {
                parseRuntimeCanonicalTestResults(mutation)
            }
            assertTrue(failure.message.orEmpty().isNotBlank())
        }
    }
}
