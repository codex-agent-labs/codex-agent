import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

internal enum class CrossLanguageBindingObligationState(val id: String) {
    ACTIVE("active"),
    PENDING("pending"),
    EXCLUDED("excluded"),
}

internal data class CrossLanguageBindingAuditRecord(
    val capabilityKey: String,
    val language: CrossLanguageBinding,
    val applicable: Boolean,
    val obligationState: CrossLanguageBindingObligationState,
    val parityStatus: CrossLanguageObligationStatus,
    val exclusionReason: String?,
)

internal data class CrossLanguageBindingAuditSummary(
    val total: Int,
    val active: Int,
    val pending: Int,
    val excluded: Int,
    val satisfied: Int,
    val missing: Int,
)

internal data class CrossLanguageBindingAudit(
    val phase: CrossLanguageBindingPhase,
    val result: String,
    val apiReportSha256: String,
    val canonicalCoverageSha256: String,
    val kotlinArtifactSha256: String,
    val compiledTestsSha256: String,
    val testResultsSha256: String,
    val summary: CrossLanguageBindingAuditSummary,
    val obligations: List<CrossLanguageBindingAuditRecord>,
    val kotlinScenarios: List<CrossLanguageScenarioEvidence>,
    val errors: List<String>,
)

internal fun buildCrossLanguageBindingAudit(
    evidence: CrossLanguageKotlinBindingEvidence,
): CrossLanguageBindingAudit {
    val phase = CrossLanguageBindingPhase.M7_5
    val capabilityKeys = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
    val publicSymbols = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::publicSymbol)
    val parity = evaluateCrossLanguageBindingParity(
        CrossLanguageBindingParityInput(
            phase = phase,
            capabilityKeys = capabilityKeys,
            canonicalCoverageKeys = capabilityKeys,
            projectionClaims = emptyList(),
            publicSymbols = mapOf(CrossLanguageBinding.KOTLIN to publicSymbols),
            bindingTests = evidence.bindingTests,
            scenarioEvidence = evidence.scenarioEvidence,
        ),
    )
    check(parity.obligations.isNotEmpty()) { parity.errors.joinToString("\n") }
    val obligations = parity.obligations.map { obligation ->
        CrossLanguageBindingAuditRecord(
            capabilityKey = obligation.capabilityKey,
            language = obligation.language,
            applicable = obligation.applicable,
            obligationState = obligation.status.obligationState(),
            parityStatus = obligation.status,
            exclusionReason = null,
        )
    }
    check(obligations.size == capabilityKeys.size * CrossLanguageBinding.entries.size) {
        "Binding obligation matrix is incomplete"
    }
    val errors = parity.errors.distinct().sorted()
    return CrossLanguageBindingAudit(
        phase = phase,
        result = if (errors.isEmpty()) "complete" else "incomplete",
        apiReportSha256 = evidence.digests.apiReportSha256,
        canonicalCoverageSha256 = evidence.digests.canonicalCoverageSha256,
        kotlinArtifactSha256 = evidence.digests.artifactSha256,
        compiledTestsSha256 = evidence.digests.compiledTestsSha256,
        testResultsSha256 = evidence.digests.testResultsSha256,
        summary = obligations.summary(),
        obligations = obligations,
        kotlinScenarios = evidence.scenarioEvidence,
        errors = errors,
    )
}

internal fun CrossLanguageBindingAudit.toJson(): JsonObject = buildJsonObject {
    put("schema", JsonPrimitive(1))
    put("result", JsonPrimitive(result))
    put("phase", JsonPrimitive(phase.name))
    put("apiReportSha256", JsonPrimitive(apiReportSha256))
    put("canonicalCoverageSha256", JsonPrimitive(canonicalCoverageSha256))
    put("kotlinArtifactSha256", JsonPrimitive(kotlinArtifactSha256))
    put("compiledTestsSha256", JsonPrimitive(compiledTestsSha256))
    put("testResultsSha256", JsonPrimitive(testResultsSha256))
    put("summary", summary.toJson())
    put("obligations", buildJsonArray {
        obligations.forEach { obligation ->
            add(buildJsonObject {
                put("capabilityKey", JsonPrimitive(obligation.capabilityKey))
                put("language", JsonPrimitive(obligation.language.id))
                put("applicable", JsonPrimitive(obligation.applicable))
                put("obligationState", JsonPrimitive(obligation.obligationState.id))
                put("parityStatus", JsonPrimitive(obligation.parityStatus.name.lowercase()))
                obligation.exclusionReason?.let { put("exclusionReason", JsonPrimitive(it)) }
            })
        }
    })
    put("kotlinScenarios", buildJsonArray {
        kotlinScenarios.forEach { claim ->
            add(buildJsonObject {
                put("scenario", JsonPrimitive(claim.scenario.id))
                put("testIds", buildJsonArray { claim.testIds.forEach { add(JsonPrimitive(it)) } })
            })
        }
    })
    put("errors", buildJsonArray { errors.forEach { add(JsonPrimitive(it)) } })
}

internal fun readCrossLanguageBindingAudit(
    auditFile: File,
    expectedEvidence: CrossLanguageKotlinBindingEvidence,
): CrossLanguageBindingAudit {
    val expectedAudit = buildCrossLanguageBindingAudit(expectedEvidence)
    val root = auditFile.readReleaseObject()
    check(root.keys == setOf(
        "schema", "result", "phase", "apiReportSha256", "canonicalCoverageSha256",
        "kotlinArtifactSha256", "compiledTestsSha256", "testResultsSha256", "summary",
        "obligations", "kotlinScenarios", "errors",
    )) { "Invalid cross-language binding audit shape" }
    check(root.releaseInt("schema") == 1) { "Unsupported cross-language binding audit schema" }
    val result = root.releaseString("result")
    check(result in setOf("complete", "incomplete")) { "Invalid cross-language binding audit result" }
    val phaseName = root.releaseString("phase")
    val phase = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phaseName }
        ?: error("Unknown cross-language binding phase: $phaseName")
    check(root.releaseString("apiReportSha256") == expectedAudit.apiReportSha256) {
        "Cross-language binding audit API report digest mismatch"
    }
    check(root.releaseString("canonicalCoverageSha256") == expectedAudit.canonicalCoverageSha256) {
        "Cross-language binding audit coverage digest mismatch"
    }
    check(root.releaseString("kotlinArtifactSha256") == expectedAudit.kotlinArtifactSha256) {
        "Cross-language binding audit Kotlin artifact digest mismatch"
    }
    val obligations = root.releaseArray("obligations").map { value ->
        (value as? JsonObject)?.bindingAuditRecord() ?: error("Invalid cross-language binding audit obligation")
    }
    check(obligations.all { obligation ->
        when (obligation.obligationState) {
            CrossLanguageBindingObligationState.PENDING -> {
                obligation.parityStatus == CrossLanguageObligationStatus.PENDING
            }
            CrossLanguageBindingObligationState.EXCLUDED -> {
                obligation.parityStatus == CrossLanguageObligationStatus.EXCLUDED
            }
            CrossLanguageBindingObligationState.ACTIVE -> {
                obligation.parityStatus in setOf(
                    CrossLanguageObligationStatus.SATISFIED,
                    CrossLanguageObligationStatus.MISSING,
                )
            }
        }
    }) { "Cross-language binding audit phase/parity status mismatch" }
    val scenarios = root.releaseArray("kotlinScenarios").map { value ->
        val record = value as? JsonObject ?: error("Invalid Kotlin binding scenario audit record")
        check(record.keys == setOf("scenario", "testIds")) { "Invalid Kotlin binding scenario audit shape" }
        val scenarioId = record.releaseString("scenario")
        val scenario = CrossLanguageBindingScenario.entries.singleOrNull { it.id == scenarioId }
            ?: error("Unknown Kotlin binding scenario: $scenarioId")
        val testIds = record.releaseArray("testIds").exactStrings("Kotlin binding scenario test")
        check(testIds.isNotEmpty()) { "Kotlin binding scenario has no tests: $scenarioId" }
        CrossLanguageScenarioEvidence(CrossLanguageBinding.KOTLIN, scenario, testIds)
    }
    check(scenarios.map(CrossLanguageScenarioEvidence::scenario) == CrossLanguageBindingScenario.entries) {
        "Kotlin binding scenario audit is incomplete or non-canonical"
    }
    val errors = root.releaseArray("errors").exactStrings("Cross-language binding audit error")
    check(errors == errors.distinct().sorted()) { "Cross-language binding audit errors are not canonical" }
    check((errors.isEmpty() && result == "complete") || (errors.isNotEmpty() && result == "incomplete")) {
        "Cross-language binding audit result/error mismatch"
    }
    val summary = root.releaseObject("summary").bindingAuditSummary()
    check(summary == obligations.summary()) { "Cross-language binding audit summary mismatch" }
    val audit = CrossLanguageBindingAudit(
        phase = phase,
        result = result,
        apiReportSha256 = expectedAudit.apiReportSha256,
        canonicalCoverageSha256 = expectedAudit.canonicalCoverageSha256,
        kotlinArtifactSha256 = expectedAudit.kotlinArtifactSha256,
        compiledTestsSha256 = root.exactBindingSha256("compiledTestsSha256"),
        testResultsSha256 = root.exactBindingSha256("testResultsSha256"),
        summary = summary,
        obligations = obligations,
        kotlinScenarios = scenarios,
        errors = errors,
    )
    check(audit == expectedAudit) {
        "Cross-language binding audit does not match freshly recomputed evidence"
    }
    return audit
}

private fun JsonObject.bindingAuditRecord(): CrossLanguageBindingAuditRecord {
    check(keys == setOf("capabilityKey", "language", "applicable", "obligationState", "parityStatus") ||
        keys == setOf(
            "capabilityKey", "language", "applicable", "obligationState", "parityStatus", "exclusionReason",
        )) { "Invalid cross-language binding audit obligation shape" }
    val languageId = releaseString("language")
    val language = CrossLanguageBinding.entries.singleOrNull { it.id == languageId }
        ?: error("Unknown cross-language binding language: $languageId")
    val obligationStateId = releaseString("obligationState")
    val obligationState = CrossLanguageBindingObligationState.entries.singleOrNull { it.id == obligationStateId }
        ?: error("Unknown cross-language binding obligation state: $obligationStateId")
    val parityStatusName = releaseString("parityStatus")
    val parityStatus = CrossLanguageObligationStatus.entries.singleOrNull {
        it.name.lowercase() == parityStatusName
    } ?: error("Unknown cross-language binding parity status: $parityStatusName")
    val applicable = releaseBoolean("applicable")
    val exclusionReason = releaseStringOrNull("exclusionReason")
    check(applicable == (exclusionReason == null)) { "Binding applicability/exclusion reason mismatch" }
    return CrossLanguageBindingAuditRecord(
        capabilityKey = releaseString("capabilityKey"),
        language = language,
        applicable = applicable,
        obligationState = obligationState,
        parityStatus = parityStatus,
        exclusionReason = exclusionReason,
    )
}

private fun CrossLanguageBindingAuditSummary.toJson(): JsonObject = buildJsonObject {
    put("total", JsonPrimitive(total))
    put("active", JsonPrimitive(active))
    put("pending", JsonPrimitive(pending))
    put("excluded", JsonPrimitive(excluded))
    put("satisfied", JsonPrimitive(satisfied))
    put("missing", JsonPrimitive(missing))
}

private fun JsonObject.bindingAuditSummary(): CrossLanguageBindingAuditSummary {
    check(keys == setOf("total", "active", "pending", "excluded", "satisfied", "missing")) {
        "Invalid cross-language binding audit summary shape"
    }
    return CrossLanguageBindingAuditSummary(
        total = releaseInt("total"),
        active = releaseInt("active"),
        pending = releaseInt("pending"),
        excluded = releaseInt("excluded"),
        satisfied = releaseInt("satisfied"),
        missing = releaseInt("missing"),
    )
}

private fun List<CrossLanguageBindingAuditRecord>.summary(): CrossLanguageBindingAuditSummary =
    CrossLanguageBindingAuditSummary(
        total = size,
        active = count { it.obligationState == CrossLanguageBindingObligationState.ACTIVE },
        pending = count { it.obligationState == CrossLanguageBindingObligationState.PENDING },
        excluded = count { it.obligationState == CrossLanguageBindingObligationState.EXCLUDED },
        satisfied = count { it.parityStatus == CrossLanguageObligationStatus.SATISFIED },
        missing = count { it.parityStatus == CrossLanguageObligationStatus.MISSING },
    )

private fun CrossLanguageObligationStatus.obligationState(): CrossLanguageBindingObligationState = when (this) {
    CrossLanguageObligationStatus.SATISFIED,
    CrossLanguageObligationStatus.MISSING -> CrossLanguageBindingObligationState.ACTIVE
    CrossLanguageObligationStatus.PENDING -> CrossLanguageBindingObligationState.PENDING
    CrossLanguageObligationStatus.EXCLUDED -> CrossLanguageBindingObligationState.EXCLUDED
}

private fun JsonArray.exactStrings(label: String): List<String> = map { value ->
    (value as? JsonPrimitive)?.content ?: error("Invalid $label")
}.also { values ->
    check(values.none { it.isBlank() || '*' in it }) { "$label is blank or wildcard" }
    check(values.size == values.distinct().size) { "$label identities are duplicated" }
}

private fun JsonObject.exactBindingSha256(name: String): String = releaseString(name).also { digest ->
    check(digest.length == 64 && digest.all { it in '0'..'9' || it in 'a'..'f' }) {
        "Cross-language binding audit $name is not an exact SHA-256"
    }
}
