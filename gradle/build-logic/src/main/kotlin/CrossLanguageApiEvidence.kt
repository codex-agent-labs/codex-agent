import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

internal data class CrossLanguageCanonicalApiEvidence(
    val memberKeys: List<String>,
    val canonical: CrossLanguageBindingCanonicalIdentity,
    val targetSha256: Map<String, String>,
    val compiledTestsSha256: String,
    val testResultsSha256: String,
    val coveredTestIds: Set<String>,
)

internal fun readCrossLanguageApiMemberKeys(report: File): List<String> =
    readCrossLanguageApiReportMemberKeys(report)

internal fun readCrossLanguageCanonicalApiEvidence(
    apiReport: File,
    canonicalCoverageReceipt: File,
): CrossLanguageCanonicalApiEvidence {
    val api = readCrossLanguageApiReport(apiReport)
    val memberKeys = api.memberKeys
    val apiReportSha256 = apiReport.releaseDigest()
    val coverage = canonicalCoverageReceipt.readCanonicalCrossLanguageObject("Canonical coverage receipt")
    coverage.requireExactKeys(
        "canonical coverage receipt",
        "schema", "result", "kotlinCompilerVersion", "canonicalTestTask", "apiReportSha256",
        "compiledTestsSha256", "testResultsSha256", "members", "claims",
    )
    check(coverage.exactInt("schema") == 1) { "Unsupported canonical coverage receipt schema" }
    check(coverage.exactString("result") == "passed") { "Canonical coverage receipt did not pass" }
    requireExactApiRecord(coverage.exactString("kotlinCompilerVersion"), "Canonical coverage Kotlin compiler")
    requireExactApiRecord(coverage.exactString("canonicalTestTask"), "Canonical coverage test task")
    check(coverage.exactSha256("apiReportSha256") == apiReportSha256) {
        "Canonical coverage API report digest mismatch"
    }
    val compiledTestsSha256 = coverage.exactSha256("compiledTestsSha256")
    val testResultsSha256 = coverage.exactSha256("testResultsSha256")

    val coveredMembers = coverage.exactStrings("members")
    requireUniqueApiRecords(coveredMembers, "Canonical coverage member")
    check(coveredMembers == memberKeys) { "Canonical coverage member/report mismatch" }
    val claims = coverage.exactArray("claims").map { value ->
        val claim = value.exactObject("canonical coverage claim")
        claim.requireExactKeys("canonical coverage claim", "testId", "members")
        val testId = claim.exactString("testId")
        val members = claim.exactStrings("members")
        requireExactApiRecord(testId, "Canonical coverage claim test")
        check(members.isNotEmpty()) { "Canonical coverage claim is empty: $testId" }
        requireUniqueApiRecords(members, "Canonical coverage claim member for $testId")
        testId to members
    }
    check(claims.isNotEmpty()) { "Canonical coverage claim inventory is empty" }
    requireUniqueApiRecords(claims.map(Pair<String, List<String>>::first), "Canonical coverage claim test")
    val memberSet = memberKeys.toSet()
    claims.flatMap(Pair<String, List<String>>::second).forEach { member ->
        check(member in memberSet) { "Stale canonical coverage claim member $member" }
    }
    val claimedMembers = claims.flatMap(Pair<String, List<String>>::second).toSet()
    check(claimedMembers == memberSet) {
        "Canonical coverage claim/member mismatch: missing=${(memberSet - claimedMembers).sorted()} " +
            "stale=${(claimedMembers - memberSet).sorted()}"
    }
    return CrossLanguageCanonicalApiEvidence(
        memberKeys = memberKeys,
        canonical = CrossLanguageBindingCanonicalIdentity(
            apiReportSha256 = apiReportSha256,
            coverageReceiptSha256 = canonicalCoverageReceipt.releaseDigest(),
        ),
        targetSha256 = api.targetSha256,
        compiledTestsSha256 = compiledTestsSha256,
        testResultsSha256 = testResultsSha256,
        coveredTestIds = claims.mapTo(linkedSetOf(), Pair<String, List<String>>::first),
    )
}

private data class CrossLanguageApiReportEvidence(
    val memberKeys: List<String>,
    val targetSha256: Map<String, String>,
)

private fun readCrossLanguageApiReportMemberKeys(report: File): List<String> =
    readCrossLanguageApiReport(report).memberKeys

private fun readCrossLanguageApiReport(report: File): CrossLanguageApiReportEvidence {
    val root = report.readCanonicalCrossLanguageObject("Cross-language API report")
    root.requireExactKeys(
        "cross-language API report",
        "schema", "libraryUniqueName", "markerAnnotation", "signatureVersion", "boundaryTypes",
        "memberExclusionAnnotation", "excludedReachableTypes", "excludedMemberKeys",
        "dataClassMetadataAvailable", "dataClassNames", "owners", "targets",
    )
    check(root.exactInt("schema") == 1) { "Unsupported cross-language API report schema" }
    requireExactApiRecord(root.exactString("libraryUniqueName"), "Cross-language API library")
    requireExactApiRecord(root.exactString("markerAnnotation"), "Cross-language API marker")
    check(root.exactInt("signatureVersion") == 2) { "Unsupported cross-language API signature version" }
    root.exactBoolean("dataClassMetadataAvailable")
    listOf("boundaryTypes", "excludedReachableTypes", "excludedMemberKeys", "dataClassNames").forEach { name ->
        requireUniqueApiRecords(root.exactStrings(name), "Cross-language API $name")
    }
    requireExactApiRecord(root.exactString("memberExclusionAnnotation"), "Cross-language API member exclusion")

    val owners = root.exactArray("owners").map { ownerValue ->
        val owner = ownerValue.exactObject("API owner")
        owner.requireExactKeys("cross-language API owner", "name", "members")
        val name = owner.exactString("name")
        val members = owner.exactStrings("members")
        requireExactApiRecord(name, "Cross-language API owner")
        requireUniqueApiRecords(members, "Cross-language API member")
        name to members
    }
    requireUniqueApiRecords(owners.map(Pair<String, List<String>>::first), "Cross-language API owner")
    val members = owners.flatMap(Pair<String, List<String>>::second)
    requireUniqueApiRecords(members, "Cross-language API member")
    check(members.isNotEmpty()) { "Cross-language API report is empty" }

    val targets = root.exactArray("targets").associate { targetValue ->
        val target = targetValue.exactObject("API target")
        target.requireExactKeys("cross-language API target", "kind", "sha256")
        val kind = target.exactString("kind")
        requireExactApiRecord(kind, "Cross-language API target")
        kind to target.exactSha256("sha256")
    }
    check(targets.size == root.exactArray("targets").size) { "Cross-language API targets are duplicated" }
    check(targets.keys == setOf("native", "wasm", "jvm-classes")) {
        "Cross-language API target inventory is incomplete"
    }
    return CrossLanguageApiReportEvidence(members.sorted(), targets)
}

private fun File.readCanonicalCrossLanguageObject(label: String): JsonObject {
    check(isFile && !Files.isSymbolicLink(toPath())) { "$label is missing, non-regular, or a symlink: $this" }
    val contents = readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject ?: error("$label must be a JSON object")
    check(contents == releaseJson.encodeToString(JsonElement.serializer(), root) + "\n") {
        "$label is not canonically encoded"
    }
    return root
}

private fun JsonObject.requireExactKeys(label: String, vararg expected: String) {
    check(keys == expected.toSet()) {
        "Invalid $label keys: expected=${expected.sorted()} actual=${keys.sorted()}"
    }
}

private fun JsonObject.exactString(name: String): String {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON string: $name")
    check(primitive.isString) { "JSON field $name must be a string" }
    return primitive.contentOrNull ?: error("Missing JSON string: $name")
}

private fun JsonObject.exactInt(name: String): Int {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON integer: $name")
    check(!primitive.isString) { "JSON field $name must be an integer" }
    return primitive.intOrNull ?: error("Missing JSON integer: $name")
}

private fun JsonObject.exactBoolean(name: String): Boolean {
    val primitive = this[name] as? JsonPrimitive ?: error("Missing JSON boolean: $name")
    check(!primitive.isString) { "JSON field $name must be a boolean" }
    return primitive.booleanOrNull ?: error("Missing JSON boolean: $name")
}

private fun JsonObject.exactArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing JSON array: $name")

private fun JsonObject.exactStrings(name: String): List<String> = exactArray(name).map { value ->
    val primitive = value as? JsonPrimitive ?: error("$name must contain only strings")
    check(primitive.isString) { "$name must contain only strings" }
    primitive.content
}

private fun JsonElement.exactObject(label: String): JsonObject = this as? JsonObject
    ?: error("Cross-language $label must be a JSON object")

private fun JsonObject.exactSha256(name: String): String = exactString(name).also { digest ->
    check(digest.length == 64 && digest.all { it in '0'..'9' || it in 'a'..'f' }) {
        "$name is not an exact SHA-256"
    }
}

private fun requireUniqueApiRecords(values: List<String>, label: String) {
    values.forEach { requireExactApiRecord(it, label) }
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it != 1 }.keys.sorted()
    check(duplicates.isEmpty()) { "$label identities are duplicated: $duplicates" }
}

private fun requireExactApiRecord(value: String, label: String) {
    check(value.isNotBlank() && value == value.trim() && '*' !in value && value.none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $value"
    }
}
