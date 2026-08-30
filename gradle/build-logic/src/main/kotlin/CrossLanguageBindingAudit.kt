import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonElement
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
    val languageReceiptSha256: Map<CrossLanguageBinding, String>,
    val summary: CrossLanguageBindingAuditSummary,
    val obligations: List<CrossLanguageBindingAuditRecord>,
    val errors: List<String>,
)

internal val crossLanguageM8EvidenceFileNames = setOf(
    "canonical-api.json",
    "canonical-coverage.json",
    "kotlin-parity.json",
    "java-parity.json",
    "javascript-typescript-parity.json",
    "swift-parity.json",
    "objective-c-parity.json",
    "c-abi-parity.json",
    "binding-obligations-m8.json",
)

internal val crossLanguageM11EvidenceFileNames = setOf(
    "canonical-api.json",
    "canonical-coverage.json",
    "kotlin-parity.json",
    "java-parity.json",
    "javascript-typescript-parity.json",
    "swift-parity.json",
    "objective-c-parity.json",
    "c-abi-parity.json",
    "python-parity.json",
    "csharp-parity.json",
    "rust-parity.json",
    "cpp-parity.json",
    "dart-parity.json",
    "binding-obligations-m11.json",
)

internal fun verifyCompleteCrossLanguageM8Evidence(
    files: Map<String, File>,
): CrossLanguageBindingAudit = verifyCompleteCrossLanguageEvidence(
    files = files,
    phase = CrossLanguageBindingPhase.M8,
    expectedFileNames = crossLanguageM8EvidenceFileNames,
    auditFileName = "binding-obligations-m8.json",
    expectedSummary = CrossLanguageBindingAuditSummary(6_116, 3_324, 2_780, 12, 3_324, 0),
)

internal fun verifyCompleteCrossLanguageM11Evidence(
    files: Map<String, File>,
): CrossLanguageBindingAudit = verifyCompleteCrossLanguageEvidence(
    files = files,
    phase = CrossLanguageBindingPhase.M11,
    expectedFileNames = crossLanguageM11EvidenceFileNames,
    auditFileName = "binding-obligations-m11.json",
    expectedSummary = CrossLanguageBindingAuditSummary(6_116, 6_104, 0, 12, 6_104, 0),
)

private fun verifyCompleteCrossLanguageEvidence(
    files: Map<String, File>,
    phase: CrossLanguageBindingPhase,
    expectedFileNames: Set<String>,
    auditFileName: String,
    expectedSummary: CrossLanguageBindingAuditSummary,
): CrossLanguageBindingAudit {
    check(files.keys == expectedFileNames && files.size == expectedFileNames.size) {
        "Cross-language ${phase.name} evidence file set is incomplete or unexpected"
    }
    files.forEach { (name, file) ->
        check(file.name == name && file.isFile && !Files.isSymbolicLink(file.toPath())) {
            "Cross-language ${phase.name} evidence is missing, unsafe, or misnamed: $name"
        }
    }
    check(files.values.map { it.canonicalFile.parentFile }.toSet().size == 1) {
        "Cross-language ${phase.name} evidence must share one directory"
    }
    val apiReport = files.getValue("canonical-api.json")
    val coverageReceipt = files.getValue("canonical-coverage.json")
    val canonicalEvidence = readCrossLanguageCanonicalApiEvidence(apiReport, coverageReceipt)
    val receiptFiles = CrossLanguageBinding.entries.filter { it.isActive(phase) }
        .associateWith { language -> files.getValue("${language.id}-parity.json") }
    val receipts = readCrossLanguageBindingReceipts(receiptFiles)
    val receiptDigests = receiptFiles.mapValues { (_, file) -> file.releaseDigest() }
    val audit = readCrossLanguageBindingAudit(
        auditFile = files.getValue(auditFileName),
        phase = phase,
        capabilityKeys = canonicalEvidence.memberKeys,
        canonical = canonicalEvidence.canonical,
        receipts = receipts,
        expectedLanguageReceiptSha256 = receiptDigests,
    )
    check(audit.result == "complete" && audit.errors.isEmpty() && audit.summary == expectedSummary) {
        "Cross-language ${phase.name} evidence is not the complete accepted obligation matrix"
    }
    return audit
}

internal fun writeCompleteCrossLanguageBindingAudit(
    phase: CrossLanguageBindingPhase,
    apiReport: File,
    canonicalCoverageReceipt: File,
    receiptDirectory: File,
    auditFile: File,
): CrossLanguageBindingAudit {
    Files.deleteIfExists(auditFile.toPath())
    check(receiptDirectory.isDirectory && !Files.isSymbolicLink(receiptDirectory.toPath())) {
        "Cross-language binding receipt directory is missing or a symlink: $receiptDirectory"
    }
    val activeLanguages = CrossLanguageBinding.entries.filter { it.isActive(phase) }
    val receiptFiles = activeLanguages.associateWith { language ->
        receiptDirectory.resolve("${language.id}-parity.json")
    }
    val entries = receiptDirectory.listFiles()?.toList()
        ?: error("Cross-language binding receipt directory cannot be listed: $receiptDirectory")
    check(entries.all { it.isFile && !Files.isSymbolicLink(it.toPath()) } &&
        entries.map(File::getName).toSet() == receiptFiles.values.map(File::getName).toSet() &&
        entries.size == receiptFiles.size) {
        "Cross-language binding receipt file set does not match active phase ${phase.name}"
    }
    val audit = writeCrossLanguageBindingAudit(
        phase,
        apiReport,
        canonicalCoverageReceipt,
        receiptFiles,
        auditFile,
    )
    check(audit.errors.isEmpty() && audit.result == "complete") {
        audit.errors.joinToString("\n").ifEmpty { "Cross-language binding audit did not complete" }
    }
    return audit
}

internal fun writeCrossLanguageBindingAudit(
    phase: CrossLanguageBindingPhase,
    apiReport: File,
    canonicalCoverageReceipt: File,
    receiptFiles: Map<CrossLanguageBinding, File>,
    auditFile: File,
): CrossLanguageBindingAudit {
    Files.deleteIfExists(auditFile.toPath())
    val canonicalEvidence = readCrossLanguageCanonicalApiEvidence(apiReport, canonicalCoverageReceipt)
    val receipts = readCrossLanguageBindingReceipts(receiptFiles)
    val receiptDigests = receiptFiles.mapValues { (_, file) -> file.releaseDigest() }
    val audit = buildCrossLanguageBindingAudit(
        phase = phase,
        capabilityKeys = canonicalEvidence.memberKeys,
        canonical = canonicalEvidence.canonical,
        receipts = receipts,
        languageReceiptSha256 = receiptDigests,
    )
    auditFile.atomicWriteJson(audit.toJson())
    return readCrossLanguageBindingAudit(
        auditFile = auditFile,
        phase = phase,
        capabilityKeys = canonicalEvidence.memberKeys,
        canonical = canonicalEvidence.canonical,
        receipts = receipts,
        expectedLanguageReceiptSha256 = receiptDigests,
    )
}

internal fun buildCrossLanguageBindingAudit(
    phase: CrossLanguageBindingPhase,
    capabilityKeys: List<String>,
    canonical: CrossLanguageBindingCanonicalIdentity,
    receipts: Map<CrossLanguageBinding, CrossLanguageBindingReceipt>,
    languageReceiptSha256: Map<CrossLanguageBinding, String>,
): CrossLanguageBindingAudit {
    check(receipts.isNotEmpty() && CrossLanguageBinding.KOTLIN in receipts) {
        "Binding audit requires a canonical Kotlin receipt"
    }
    check(receipts.keys == languageReceiptSha256.keys &&
        languageReceiptSha256.values.all(String::isExactSha256)) {
        "Binding audit receipt identities are missing or malformed"
    }
    receipts.forEach { (language, receipt) ->
        receipt.toJson() // Validate direct producer values through the universal receipt contract.
        check(receipt.language == language) { "Binding audit receipt language mismatch for ${language.id}" }
        check(receipt.phase == phase) { "Binding audit receipt phase mismatch for ${language.id}" }
        check(language.isActive(phase)) { "Binding audit contains inactive language ${language.id}" }
        check(receipt.canonical == canonical) {
            "Binding audit canonical identity mismatch for ${language.id}"
        }
    }
    check(receipts.getValue(CrossLanguageBinding.KOTLIN).publicSymbols.sorted() == capabilityKeys.sorted()) {
        "Kotlin binding audit receipt does not match the canonical API"
    }

    val exclusions = receipts.values.flatMap(CrossLanguageBindingReceipt::applicabilityExclusions)
        .associateBy { it.capabilityKey to it.language }
    val parity = evaluateCrossLanguageBindingParity(
        CrossLanguageBindingParityInput(
            phase = phase,
            capabilityKeys = capabilityKeys,
            canonicalCoverageKeys = capabilityKeys,
            projectionClaims = receipts.values.flatMap(CrossLanguageBindingReceipt::projectionClaims),
            applicabilityExclusions = exclusions.values.toList(),
            publicSymbols = receipts.mapValues { it.value.publicSymbols },
            bindingTests = receipts.values.flatMap(CrossLanguageBindingReceipt::bindingTests),
            scenarioEvidence = receipts.values.flatMap(CrossLanguageBindingReceipt::scenarioEvidence),
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
            exclusionReason = exclusions[obligation.capabilityKey to obligation.language]?.reason,
        )
    }
    check(obligations.size == capabilityKeys.size * CrossLanguageBinding.entries.size) {
        "Binding obligation matrix is incomplete"
    }
    val errors = parity.errors.distinct().sorted()
    return CrossLanguageBindingAudit(
        phase = phase,
        result = if (errors.isEmpty()) "complete" else "incomplete",
        apiReportSha256 = canonical.apiReportSha256,
        canonicalCoverageSha256 = canonical.coverageReceiptSha256,
        languageReceiptSha256 = languageReceiptSha256.toMap(),
        summary = obligations.summary(),
        obligations = obligations,
        errors = errors,
    )
}

internal fun CrossLanguageBindingAudit.toJson(): JsonObject = buildJsonObject {
    put("schema", JsonPrimitive(3))
    put("result", JsonPrimitive(result))
    put("phase", JsonPrimitive(phase.name))
    put("apiReportSha256", JsonPrimitive(apiReportSha256))
    put("canonicalCoverageSha256", JsonPrimitive(canonicalCoverageSha256))
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
    put("errors", buildJsonArray { errors.forEach { add(JsonPrimitive(it)) } })
}

internal fun readCrossLanguageBindingAudit(
    auditFile: File,
    phase: CrossLanguageBindingPhase,
    capabilityKeys: List<String>,
    canonical: CrossLanguageBindingCanonicalIdentity,
    receipts: Map<CrossLanguageBinding, CrossLanguageBindingReceipt>,
    expectedLanguageReceiptSha256: Map<CrossLanguageBinding, String>,
): CrossLanguageBindingAudit {
    val expected = buildCrossLanguageBindingAudit(
        phase,
        capabilityKeys,
        canonical,
        receipts,
        expectedLanguageReceiptSha256,
    )
    check(auditFile.isFile && !Files.isSymbolicLink(auditFile.toPath())) {
        "Cross-language binding audit is missing, non-regular, or a symlink: $auditFile"
    }
    val contents = auditFile.readText()
    val actual = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("Cross-language binding audit must be a JSON object")
    check(actual == expected.toJson() && contents == expected.canonicalJson()) {
        "Cross-language binding audit does not match canonical freshly recomputed evidence"
    }
    return expected
}

private fun CrossLanguageBindingAudit.canonicalJson(): String =
    releaseJson.encodeToString(JsonElement.serializer(), toJson()) + "\n"

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
