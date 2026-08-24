internal enum class CrossLanguageBindingPhase {
    M7_5,
    M8,
    M9_PYTHON,
    M9_CSHARP,
    M9_RUST,
    M9_CPP,
    M9_DART,
    M11,
}

internal enum class CrossLanguageBinding(
    val id: String,
    private val activationPhase: CrossLanguageBindingPhase,
) {
    KOTLIN("kotlin", CrossLanguageBindingPhase.M7_5),
    JAVA("java", CrossLanguageBindingPhase.M7_5),
    SWIFT("swift", CrossLanguageBindingPhase.M7_5),
    OBJECTIVE_C("objective-c", CrossLanguageBindingPhase.M7_5),
    JAVASCRIPT_TYPESCRIPT("javascript-typescript", CrossLanguageBindingPhase.M7_5),
    C_ABI("c-abi", CrossLanguageBindingPhase.M8),
    PYTHON("python", CrossLanguageBindingPhase.M9_PYTHON),
    CSHARP("csharp", CrossLanguageBindingPhase.M9_CSHARP),
    RUST("rust", CrossLanguageBindingPhase.M9_RUST),
    CPP("c++", CrossLanguageBindingPhase.M9_CPP),
    DART("dart", CrossLanguageBindingPhase.M9_DART),
    ;

    fun isActive(phase: CrossLanguageBindingPhase): Boolean = phase.ordinal >= activationPhase.ordinal
}

/** Closed R757 projection scenarios. Additions deliberately create obligations for every active language. */
internal enum class CrossLanguageBindingScenario(val id: String) {
    ASYNC_SUCCESS("async-success"),
    ASYNC_FAILURE("async-failure"),
    CANCELLATION("cancellation"),
    STATE_CURRENT_VALUE("state-current-value"),
    STATE_SUBSEQUENT_VALUE("state-subsequent-value"),
    SUBSCRIPTION_CANCELLATION("subscription-cancellation"),
    TERMINAL_DELIVERY("terminal-delivery"),
    STRUCTURED_FAILURE("structured-failure"),
    IDENTITY("identity"),
    PARENT_CHILD_OWNERSHIP("parent-child-ownership"),
    REPEATED_CLOSE_DISPOSE("repeated-close-dispose"),
    NULLABILITY("nullability"),
    COLLECTION_IMMUTABILITY_ORDERING("collection-immutability-ordering"),
    VALUE_CONVERSION("value-conversion"),
}

internal enum class CrossLanguageBindingTestStatus { PASSED, SKIPPED, FAILED }

internal data class CrossLanguageBindingTestEvidence(
    val language: CrossLanguageBinding,
    val testId: String,
    val status: CrossLanguageBindingTestStatus,
)

internal data class CrossLanguageScenarioEvidence(
    val language: CrossLanguageBinding,
    val scenario: CrossLanguageBindingScenario,
    val testId: String,
)

internal data class CrossLanguageProjectionClaim(
    val capabilityKey: String,
    val language: CrossLanguageBinding,
    val publicSymbols: List<String>,
    val executedTests: List<String>,
    val sharedScenarios: List<CrossLanguageBindingScenario>,
)

internal data class CrossLanguageApplicabilityExclusion(
    val capabilityKey: String,
    val language: CrossLanguageBinding,
    val reason: String,
)

internal data class CrossLanguageBindingParityInput(
    val phase: CrossLanguageBindingPhase,
    val capabilityKeys: List<String>,
    val canonicalCoverageKeys: List<String>,
    val projectionClaims: List<CrossLanguageProjectionClaim>,
    val applicabilityExclusions: List<CrossLanguageApplicabilityExclusion> = emptyList(),
    val publicSymbols: Map<CrossLanguageBinding, List<String>>,
    val bindingTests: List<CrossLanguageBindingTestEvidence>,
    val scenarioEvidence: List<CrossLanguageScenarioEvidence>,
)

internal enum class CrossLanguageObligationStatus { SATISFIED, MISSING, EXCLUDED, PENDING }

internal data class CrossLanguageBindingObligation(
    val capabilityKey: String,
    val language: CrossLanguageBinding,
    val applicable: Boolean,
    val status: CrossLanguageObligationStatus,
)

internal data class CrossLanguageBindingParityReport(
    val phase: CrossLanguageBindingPhase,
    val obligations: List<CrossLanguageBindingObligation>,
    val errors: List<String>,
)

internal fun verifyCrossLanguageBindingParity(
    input: CrossLanguageBindingParityInput,
): CrossLanguageBindingParityReport = evaluateCrossLanguageBindingParity(input).also { report ->
    check(report.errors.isEmpty()) { report.errors.joinToString("\n") }
}

internal fun evaluateCrossLanguageBindingParity(
    input: CrossLanguageBindingParityInput,
): CrossLanguageBindingParityReport {
    val coverageErrors = mutableListOf<String>()
    validateExactKeys("canonical capability", input.capabilityKeys, requireNonEmpty = true, coverageErrors)
    validateExactKeys("canonical coverage", input.canonicalCoverageKeys, requireNonEmpty = false, coverageErrors)

    val capabilityKeys = input.capabilityKeys.filter(String::isExactRecord).toSet()
    val coverageKeys = input.canonicalCoverageKeys.filter(String::isExactRecord).toSet()
    (capabilityKeys - coverageKeys).sorted().forEach {
        coverageErrors += "Missing canonical coverage for $it"
    }
    (coverageKeys - capabilityKeys).sorted().forEach {
        coverageErrors += "Stale canonical coverage key $it"
    }
    if (coverageErrors.isNotEmpty()) {
        return CrossLanguageBindingParityReport(input.phase, emptyList(), coverageErrors.sorted())
    }

    val errors = mutableListOf<String>()
    val activeLanguages = CrossLanguageBinding.entries.filter { it.isActive(input.phase) }.toSet()

    input.publicSymbols.forEach { (language, symbols) ->
        validateExactKeys("${language.id} public symbol", symbols, requireNonEmpty = false, errors)
    }

    val testRecords = input.bindingTests.groupBy { it.language to it.testId }
    input.bindingTests.forEach { evidence ->
        if (evidence.testId.isBlank()) errors += "Blank ${evidence.language.id} binding test id"
        if (evidence.testId.contains('*')) errors += "Wildcard ${evidence.language.id} binding test id ${evidence.testId}"
    }
    testRecords.filterValues { it.size > 1 }.keys.forEach { (language, testId) ->
        errors += "Duplicate ${language.id} binding test evidence $testId"
    }
    val passedTests = testRecords.mapNotNullTo(mutableSetOf()) { (key, records) ->
        key.takeIf { records.size == 1 && records.single().status == CrossLanguageBindingTestStatus.PASSED && key.second.isExactRecord() }
    }

    val scenarioRecords = input.scenarioEvidence.groupBy { it.language to it.scenario }
    scenarioRecords.filterValues { it.size > 1 }.keys.forEach { (language, scenario) ->
        errors += "Duplicate ${language.id} scenario evidence ${scenario.id}"
    }
    input.scenarioEvidence.forEach { evidence ->
        if (evidence.testId.isBlank()) errors += "Blank ${evidence.language.id} scenario test id for ${evidence.scenario.id}"
        if (evidence.testId.contains('*')) {
            errors += "Wildcard ${evidence.language.id} scenario test id ${evidence.testId}"
        }
        if (evidence.language to evidence.testId !in passedTests) {
            errors += "Unknown or non-passed ${evidence.language.id} scenario test ${evidence.testId} for ${evidence.scenario.id}"
        }
    }
    val validScenarioEvidence = scenarioRecords.mapNotNullTo(mutableSetOf()) { (key, records) ->
        val record = records.singleOrNull()
        key.takeIf { record != null && record.language to record.testId in passedTests }
    }
    activeLanguages.forEach { language ->
        CrossLanguageBindingScenario.entries.forEach { scenario ->
            if (language to scenario !in validScenarioEvidence) {
                errors += "Missing ${language.id} shared scenario evidence ${scenario.id}"
            }
        }
    }

    val claimRecords = input.projectionClaims.groupBy { it.capabilityKey to it.language }
    claimRecords.filterValues { it.size > 1 }.keys.forEach { (capability, language) ->
        errors += "Duplicate projection claim ${language.id}:$capability"
    }
    input.projectionClaims.forEach { claim ->
        when {
            claim.capabilityKey.isBlank() -> errors += "Blank ${claim.language.id} projection capability key"
            claim.capabilityKey.contains('*') -> errors += "Wildcard ${claim.language.id} projection capability key ${claim.capabilityKey}"
            claim.capabilityKey !in capabilityKeys -> errors += "Stale projection claim ${claim.language.id}:${claim.capabilityKey}"
        }
        validateExactKeys("${claim.language.id} claim public symbol", claim.publicSymbols, true, errors)
        validateExactKeys("${claim.language.id} claim test", claim.executedTests, true, errors)
        if (claim.sharedScenarios.isEmpty()) {
            errors += "${claim.language.id}:${claim.capabilityKey} has no shared scenario"
        }
        duplicateValues(claim.sharedScenarios).forEach {
            errors += "Duplicate ${claim.language.id} claim scenario ${it.id}"
        }
        claim.publicSymbols.forEach { symbol ->
            if (symbol !in input.publicSymbols[claim.language].orEmpty()) {
                errors += "Unknown ${claim.language.id} public symbol $symbol"
            }
        }
        claim.executedTests.forEach { testId ->
            if (claim.language to testId !in passedTests) {
                errors += "Unknown or non-passed ${claim.language.id} binding test $testId"
            }
        }
        claim.sharedScenarios.forEach { scenario ->
            if (claim.language to scenario !in validScenarioEvidence) {
                errors += "Missing ${claim.language.id} claim scenario evidence ${scenario.id}"
            }
        }
    }

    val exclusionRecords = input.applicabilityExclusions.groupBy { it.capabilityKey to it.language }
    exclusionRecords.filterValues { it.size > 1 }.keys.forEach { (capability, language) ->
        errors += "Duplicate applicability exclusion ${language.id}:$capability"
    }
    input.applicabilityExclusions.forEach { exclusion ->
        val pair = exclusion.capabilityKey to exclusion.language
        when {
            exclusion.capabilityKey.isBlank() -> errors += "Blank applicability exclusion capability key"
            exclusion.capabilityKey.contains('*') -> errors += "Wildcard applicability exclusion capability key ${exclusion.capabilityKey}"
            exclusion.capabilityKey !in capabilityKeys -> errors += "Stale applicability exclusion ${exclusion.language.id}:${exclusion.capabilityKey}"
        }
        when {
            exclusion.reason.isBlank() -> errors += "Blank applicability exclusion reason ${exclusion.language.id}:${exclusion.capabilityKey}"
            exclusion.reason.contains('*') -> errors += "Wildcard applicability exclusion reason ${exclusion.language.id}:${exclusion.capabilityKey}"
            exclusion.reason.normalizedExclusionReason() in genericExclusionReasons -> {
                errors += "Broad applicability exclusion reason ${exclusion.language.id}:${exclusion.capabilityKey}"
            }
        }
        if (exclusion.language !in activeLanguages) {
            errors += "Applicability exclusion targets an inactive language ${exclusion.language.id}:${exclusion.capabilityKey}"
        }
        if (pair in claimRecords) {
            errors += "Projection claim conflicts with applicability exclusion ${exclusion.language.id}:${exclusion.capabilityKey}"
        }
    }

    val validClaims = claimRecords.mapNotNullTo(mutableSetOf()) { (pair, records) ->
        val claim = records.singleOrNull()
        pair.takeIf {
            claim != null &&
                claim.capabilityKey in capabilityKeys &&
                claim.publicSymbols.isNotEmpty() &&
                claim.publicSymbols.all { it.isExactRecord() && it in input.publicSymbols[claim.language].orEmpty() } &&
                claim.executedTests.isNotEmpty() &&
                claim.executedTests.all { claim.language to it in passedTests } &&
                claim.sharedScenarios.isNotEmpty() &&
                claim.sharedScenarios.all { claim.language to it in validScenarioEvidence }
        }
    }
    val validExclusions = exclusionRecords.mapNotNullTo(mutableSetOf()) { (pair, records) ->
        val exclusion = records.singleOrNull()
        pair.takeIf {
            exclusion != null &&
                exclusion.capabilityKey in capabilityKeys &&
                exclusion.language in activeLanguages &&
                exclusion.reason.isNarrowExclusionReason() &&
                pair !in claimRecords
        }
    }

    val obligations = capabilityKeys.sorted().flatMap { capability ->
        CrossLanguageBinding.entries.map { language ->
            val pair = capability to language
            val excluded = pair in validExclusions
            val status = when {
                language !in activeLanguages -> CrossLanguageObligationStatus.PENDING
                excluded -> CrossLanguageObligationStatus.EXCLUDED
                language == CrossLanguageBinding.KOTLIN -> CrossLanguageObligationStatus.SATISFIED
                pair in validClaims -> CrossLanguageObligationStatus.SATISFIED
                else -> CrossLanguageObligationStatus.MISSING
            }
            if (status == CrossLanguageObligationStatus.MISSING) {
                errors += "Missing active binding projection ${language.id}:$capability"
            }
            CrossLanguageBindingObligation(capability, language, applicable = !excluded, status)
        }
    }

    return CrossLanguageBindingParityReport(input.phase, obligations, errors.distinct().sorted())
}

private val genericExclusionReasons = setOf(
    "n/a",
    "na",
    "not applicable",
    "does not apply",
    "not supported",
    "unsupported",
    "not needed",
    "other",
    "platform specific",
    "platform-specific",
    "platform limitation",
    "language specific",
    "language-specific",
    "language limitation",
    "not available",
    "all",
    "any",
)

private fun String.isExactRecord(): Boolean = isNotBlank() && '*' !in this

private fun String.isNarrowExclusionReason(): Boolean =
    isNotBlank() && '*' !in this && normalizedExclusionReason() !in genericExclusionReasons

private fun String.normalizedExclusionReason(): String =
    trim().lowercase().trimEnd('.', '!', ':', ';')

private fun validateExactKeys(
    label: String,
    values: List<String>,
    requireNonEmpty: Boolean,
    errors: MutableList<String>,
) {
    if (requireNonEmpty && values.isEmpty()) errors += "$label inventory is empty"
    values.forEach { value ->
        if (value.isBlank()) errors += "Blank $label"
        if (value.contains('*')) errors += "Wildcard $label $value"
    }
    duplicateValues(values).forEach { errors += "Duplicate $label $it" }
}

private fun <T> duplicateValues(values: List<T>): Set<T> =
    values.groupingBy { it }.eachCount().filterValues { it > 1 }.keys
