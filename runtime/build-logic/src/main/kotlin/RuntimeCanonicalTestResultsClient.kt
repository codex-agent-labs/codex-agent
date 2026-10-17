import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

internal enum class CanonicalTestStatus { PASSED, SKIPPED, FAILED }

internal data class CanonicalTestResult(
    val testId: String,
    val status: CanonicalTestStatus,
)

internal fun readCanonicalTestResults(resultsDirectory: File): List<CanonicalTestResult> =
    parseRuntimeCanonicalTestResults(
        runRuntimeProductPythonModule(
            "test_results",
            listOf("--directory", resultsDirectory.absolutePath),
        ),
    )

internal fun readCanonicalTestReport(report: File): List<CanonicalTestResult> =
    parseRuntimeCanonicalTestResults(
        runRuntimeProductPythonModule(
            "test_results",
            listOf("--report", report.absolutePath),
        ),
    )

internal fun parseRuntimeCanonicalTestResults(output: String): List<CanonicalTestResult> {
    check(output.endsWith('\n') && output.count { it == '\n' } == 1 && '\r' !in output) {
        "Canonical test-result projection must be one LF-terminated JSON line"
    }
    val root = Json.parseToJsonElement(output).let { value ->
        value as? JsonObject ?: error("Canonical test-result projection must be an object")
    }
    check(root.keys == setOf("schemaVersion", "tests")) {
        "Canonical test-result projection schema fields mismatch"
    }
    val schema = root.getValue("schemaVersion") as? JsonPrimitive
        ?: error("Canonical test-result schemaVersion must be an integer")
    check(!schema.isString && schema.intOrNull == 1) {
        "Canonical test-result projection schemaVersion must be 1"
    }
    val tests = root.getValue("tests") as? JsonArray
        ?: error("Canonical test-result projection tests must be an array")
    val results = tests.mapIndexed { index, value ->
        val record = value as? JsonObject
            ?: error("Canonical test-result projection tests[$index] must be an object")
        check(record.keys == setOf("status", "testId")) {
            "Canonical test-result projection tests[$index] schema fields mismatch"
        }
        fun string(name: String): String {
            val primitive = record.getValue(name) as? JsonPrimitive
                ?: error("Canonical test-result projection tests[$index].$name must be a string")
            check(primitive.isString) {
                "Canonical test-result projection tests[$index].$name must be a string"
            }
            return primitive.contentOrNull
                ?: error("Canonical test-result projection tests[$index].$name is missing")
        }
        val testId = string("testId")
        check(testId.isNotBlank() && testId.none { it.code < 0x20 || it.code == 0x7f }) {
            "Canonical test-result projection tests[$index].testId is invalid"
        }
        val status = when (val valueStatus = string("status")) {
            "passed" -> CanonicalTestStatus.PASSED
            "skipped" -> CanonicalTestStatus.SKIPPED
            "failed" -> CanonicalTestStatus.FAILED
            else -> error("Canonical test-result projection tests[$index].status is invalid: $valueStatus")
        }
        CanonicalTestResult(testId, status)
    }
    val canonical = buildJsonObject {
        put("schemaVersion", 1)
        putJsonArray("tests") {
            results.forEach { result ->
                add(buildJsonObject {
                    put("status", result.status.name.lowercase())
                    put("testId", result.testId)
                })
            }
        }
    }.toString() + "\n"
    check(output == canonical) { "Canonical test-result projection bytes are not canonical" }
    return results
}
