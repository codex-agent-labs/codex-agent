import java.io.File
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
    val languageReceiptSha256: Map<CrossLanguageBinding, String>,
    val summary: CrossLanguageBindingAuditSummary,
    val obligations: List<CrossLanguageBindingAuditRecord>,
    val kotlinScenarios: List<CrossLanguageScenarioEvidence>,
    val errors: List<String>,
)

internal fun buildCrossLanguageBindingAudit(
    kotlinEvidence: CrossLanguageKotlinBindingEvidence,
    javaEvidence: CrossLanguageJavaBindingParityEvidence,
    languageReceiptSha256: Map<CrossLanguageBinding, String>,
): CrossLanguageBindingAudit {
    val phase = CrossLanguageBindingPhase.M7_5
    val capabilityKeys = kotlinEvidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
    val kotlinPublicSymbols = kotlinEvidence.capabilityClaims.map(KotlinBindingCapabilityClaim::publicSymbol)
    check(javaEvidence.projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey).sorted() ==
        capabilityKeys.sorted()) {
        "Java binding audit evidence does not match the canonical API"
    }
    check(languageReceiptSha256.keys == setOf(CrossLanguageBinding.KOTLIN, CrossLanguageBinding.JAVA) &&
        languageReceiptSha256.values.all(String::isExactSha256)) {
        "Binding audit requires exact Kotlin and Java receipt digests"
    }
    val parity = evaluateCrossLanguageBindingParity(
        CrossLanguageBindingParityInput(
            phase = phase,
            capabilityKeys = capabilityKeys,
            canonicalCoverageKeys = capabilityKeys,
            projectionClaims = javaEvidence.projectionClaims,
            publicSymbols = mapOf(
                CrossLanguageBinding.KOTLIN to kotlinPublicSymbols,
                CrossLanguageBinding.JAVA to javaEvidence.publicSymbols,
            ),
            bindingTests = kotlinEvidence.bindingTests + javaEvidence.bindingTests,
            scenarioEvidence = kotlinEvidence.scenarioEvidence + javaEvidence.scenarioEvidence,
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
        apiReportSha256 = kotlinEvidence.digests.apiReportSha256,
        canonicalCoverageSha256 = kotlinEvidence.digests.canonicalCoverageSha256,
        kotlinArtifactSha256 = kotlinEvidence.digests.artifactSha256,
        compiledTestsSha256 = kotlinEvidence.digests.compiledTestsSha256,
        testResultsSha256 = kotlinEvidence.digests.testResultsSha256,
        languageReceiptSha256 = languageReceiptSha256.toMap(),
        summary = obligations.summary(),
        obligations = obligations,
        kotlinScenarios = kotlinEvidence.scenarioEvidence,
        errors = errors,
    )
}

internal fun CrossLanguageBindingAudit.toJson(): JsonObject = buildJsonObject {
    put("schema", JsonPrimitive(2))
    put("result", JsonPrimitive(result))
    put("phase", JsonPrimitive(phase.name))
    put("apiReportSha256", JsonPrimitive(apiReportSha256))
    put("canonicalCoverageSha256", JsonPrimitive(canonicalCoverageSha256))
    put("kotlinArtifactSha256", JsonPrimitive(kotlinArtifactSha256))
    put("compiledTestsSha256", JsonPrimitive(compiledTestsSha256))
    put("testResultsSha256", JsonPrimitive(testResultsSha256))
    put("languageReceiptSha256", buildJsonObject {
        languageReceiptSha256.entries.sortedBy { it.key.id }.forEach { (language, digest) ->
            put(language.id, JsonPrimitive(digest))
        }
    })
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
    expectedKotlinEvidence: CrossLanguageKotlinBindingEvidence,
    expectedJavaEvidence: CrossLanguageJavaBindingParityEvidence,
    expectedLanguageReceiptSha256: Map<CrossLanguageBinding, String>,
): CrossLanguageBindingAudit {
    val expected = buildCrossLanguageBindingAudit(
        expectedKotlinEvidence,
        expectedJavaEvidence,
        expectedLanguageReceiptSha256,
    )
    check(auditFile.readReleaseObject() == expected.toJson()) {
        "Cross-language binding audit does not match freshly recomputed evidence"
    }
    return expected
}

private fun CrossLanguageBindingAuditSummary.toJson(): JsonObject = buildJsonObject {
    put("total", JsonPrimitive(total))
    put("active", JsonPrimitive(active))
    put("pending", JsonPrimitive(pending))
    put("excluded", JsonPrimitive(excluded))
    put("satisfied", JsonPrimitive(satisfied))
    put("missing", JsonPrimitive(missing))
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

private fun String.isExactSha256(): Boolean =
    length == 64 && all { it in '0'..'9' || it in 'a'..'f' }
