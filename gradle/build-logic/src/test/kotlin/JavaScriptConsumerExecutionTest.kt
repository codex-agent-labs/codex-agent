import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFails
import kotlin.test.assertTrue
import kotlinx.serialization.json.*

class JavaScriptConsumerExecutionTest {
    @Test
    fun `exact installed compiler and consumer records preserve binary and empty streams`() = fixture { root ->
        verifyJavaScriptConsumerExecutions(root)
        val plugin = File("src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText()
        assertTrue("verifyJavaScriptConsumerExecutions(publicApi.parentFile)" in plugin)
        assertTrue("from(listOf(npmCompilerExecution, npmConsumerExecution)) { into(\"execution\") }" in plugin)
        assertTrue("\"execution\" to \"outputs/execution\"" in plugin)
    }

    @Test
    fun `missing failed malformed and substituted executions fail closed`() = fixture { root ->
        val file = root.resolve("typescript-execution.json")
        val original = file.readText()
        listOf(
            original.replace("\"exitCode\":0", "\"exitCode\":1"),
            original.replace("\"exitCode\":0", "\"exitCode\":false"),
            original.replace("\"schemaVersion\":1", "\"schemaVersion\":1.0"),
            original.replace("\"schemaVersion\":1", "\"schemaVersion\":1,\"schemaVersion\":1"),
            original.replace("\"stdoutBase64\":\"\"", "\"stdoutBase64\":\"Zh==\""),
            original.replace("--noEmit", "--build"),
            original.replace("node_modules/typescript/bin/tsc", "untrusted/tsc"),
            original.replace("/observed/node", "/different/node"),
            original + "\n",
        ).forEach { mutation ->
            file.writeText(mutation)
            assertFails { verifyJavaScriptConsumerExecutions(root) }
        }
        file.delete()
        assertFails { verifyJavaScriptConsumerExecutions(root) }
    }

    private fun fixture(action: (File) -> Unit) {
        val root = createTempDirectory("javascript-execution-").toFile().canonicalFile
        try {
            listOf("typescript-execution.json", "packed-consumer-execution.json").forEach { name ->
                val arguments = if (name == "typescript-execution.json") {
                    listOf(root.resolve("node_modules/typescript/bin/tsc").absolutePath, "--noEmit")
                } else {
                    listOf("--test", "--test-reporter=junit", "--test-reporter-destination=packed-tests.xml", "smoke.cjs", "smoke.mjs")
                }
                val value = buildJsonObject {
                    put("command", JsonArray((listOf("/observed/node") + arguments).map(::JsonPrimitive)))
                    put("exitCode", 0)
                    put("schemaVersion", 1)
                    put("stderrBase64", "/wANCg==")
                    put("stdoutBase64", "")
                }
                root.resolve(name).writeText(Json.encodeToString(JsonElement.serializer(), value) + "\n")
            }
            action(root)
        } finally { root.deleteRecursively() }
    }
}
