import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject

internal enum class CanonicalTestStatus { PASSED, SKIPPED, FAILED }

internal data class CanonicalTestResult(
    val testId: String,
    val status: CanonicalTestStatus,
)

internal fun readCanonicalTestResults(resultsDirectory: File): List<CanonicalTestResult> =
    readCanonicalTestResultsFromProductTooling(listOf("--directory", resultsDirectory.absolutePath), true)

internal fun readCanonicalTestReport(report: File): List<CanonicalTestResult> =
    readCanonicalTestResultsFromProductTooling(listOf("--report", report.absolutePath), false)

private fun readCanonicalTestResultsFromProductTooling(
    arguments: List<String>,
    requireSortedUnique: Boolean,
): List<CanonicalTestResult> {
    val root = releaseJson.parseToJsonElement(runProductPythonModule("test_results", arguments)).jsonObject
    check(root.keys == setOf("schemaVersion", "tests") && root.releaseInt("schemaVersion") == 1) {
        "Canonical test result projection schema is invalid"
    }
    val tests = (root["tests"] as? JsonArray ?: error("Canonical test result projection is missing tests"))
        .map { value ->
            val record = value as? JsonObject ?: error("Canonical test result projection record is invalid")
            check(record.keys == setOf("status", "testId")) {
                "Canonical test result projection record schema is invalid"
            }
            val testId = record.canonicalTestString("testId")
            check(testId.isNotBlank()) { "Canonical test result identity is empty" }
            CanonicalTestResult(
                testId,
                when (record.canonicalTestString("status")) {
                    "passed" -> CanonicalTestStatus.PASSED
                    "skipped" -> CanonicalTestStatus.SKIPPED
                    "failed" -> CanonicalTestStatus.FAILED
                    else -> error("Canonical test result status is invalid")
                },
            )
        }
    if (requireSortedUnique) {
        check(tests.map(CanonicalTestResult::testId).let { ids ->
            ids == ids.sorted() && ids.size == ids.toSet().size
        }) { "Canonical test result projection is not sorted and unique" }
    }
    return tests
}

private fun JsonObject.canonicalTestString(name: String): String {
    val primitive = this[name] as? JsonPrimitive ?: error("Canonical test result $name must be a string")
    check(primitive.isString) { "Canonical test result $name must be a string" }
    return primitive.contentOrNull ?: error("Canonical test result $name is missing")
}
