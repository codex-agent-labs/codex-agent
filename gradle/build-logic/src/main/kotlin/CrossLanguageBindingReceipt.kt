import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.intOrNull

internal const val CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA = 4

internal data class CrossLanguageBindingArtifactIdentity(
    val id: String,
    val sha256: String,
)

internal data class CrossLanguageBindingHostConsumerProof(
    val classifier: String,
    val runnerOs: String,
    val runnerArch: String,
    val toolchainIdentitySha256: String,
    val packageArtifactId: String,
    val packageSha256: String,
    val nativeLibrarySha256: String,
    val testId: String,
    val status: CrossLanguageBindingTestStatus,
    val candidateCommit: String,
    val candidateTree: String,
)

internal data class CrossLanguageBindingReceipt(
    val phase: CrossLanguageBindingPhase,
    val language: CrossLanguageBinding,
    val canonical: CrossLanguageBindingCanonicalIdentity,
    val artifacts: List<CrossLanguageBindingArtifactIdentity>,
    val testProgramSha256: String,
    val testResultsSha256: String,
    val publicSymbols: List<String>,
    val bindingTests: List<CrossLanguageBindingTestEvidence>,
    val scenarioEvidence: List<CrossLanguageScenarioEvidence>,
    val projectionClaims: List<CrossLanguageProjectionClaim>,
    val applicabilityExclusions: List<CrossLanguageApplicabilityExclusion>,
    val hostConsumerProofs: List<CrossLanguageBindingHostConsumerProof> = emptyList(),
)

internal fun writeCrossLanguageBindingReceipt(
    file: File,
    receipt: CrossLanguageBindingReceipt,
) {
    file.atomicWriteJson(receipt.toJson())
    readCrossLanguageBindingReceipt(file)
}

internal fun readCrossLanguageBindingReceipt(file: File): CrossLanguageBindingReceipt {
    check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
        "Cross-language binding receipt is missing, non-regular, or a symlink: $file"
    }
    val contents = file.readText()
    val root = releaseJson.parseToJsonElement(contents) as? JsonObject
        ?: error("Cross-language binding receipt must be a JSON object")
    val receipt = root.toCrossLanguageBindingReceipt().normalized()
    check(contents == receipt.canonicalJson()) {
        "Cross-language binding receipt is not canonically encoded"
    }
    return receipt
}

internal fun readCrossLanguageBindingReceipts(
    receiptFiles: Map<CrossLanguageBinding, File>,
): Map<CrossLanguageBinding, CrossLanguageBindingReceipt> {
    check(receiptFiles.isNotEmpty()) { "Cross-language binding receipt file inventory is empty" }
    return CrossLanguageBinding.entries.filter(receiptFiles::containsKey).associateWith { expectedLanguage ->
        readCrossLanguageBindingReceipt(receiptFiles.getValue(expectedLanguage)).also { receipt ->
            check(receipt.language == expectedLanguage) {
                "${expectedLanguage.id} binding receipt file contains ${receipt.language.id} evidence"
            }
        }
    }
}

internal fun CrossLanguageBindingReceipt.toJson(): JsonObject {
    val receipt = normalized()
    return buildJsonObject {
        put("schema", JsonPrimitive(CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA))
        put("result", JsonPrimitive("passed"))
        put("phase", JsonPrimitive(receipt.phase.name))
        put("language", JsonPrimitive(receipt.language.id))
        put("canonical", buildJsonObject {
            put("apiReportSha256", JsonPrimitive(receipt.canonical.apiReportSha256))
            put("coverageReceiptSha256", JsonPrimitive(receipt.canonical.coverageReceiptSha256))
        })
        put("artifacts", buildJsonArray {
            receipt.artifacts.forEach { artifact ->
                add(buildJsonObject {
                    put("id", JsonPrimitive(artifact.id))
                    put("sha256", JsonPrimitive(artifact.sha256))
                })
            }
        })
        put("hostConsumerProofs", buildJsonArray {
            receipt.hostConsumerProofs.forEach { proof ->
                add(buildJsonObject {
                    put("classifier", JsonPrimitive(proof.classifier))
                    put("runnerOs", JsonPrimitive(proof.runnerOs))
                    put("runnerArch", JsonPrimitive(proof.runnerArch))
                    put("toolchainIdentitySha256", JsonPrimitive(proof.toolchainIdentitySha256))
                    put("packageArtifactId", JsonPrimitive(proof.packageArtifactId))
                    put("packageSha256", JsonPrimitive(proof.packageSha256))
                    put("nativeLibrarySha256", JsonPrimitive(proof.nativeLibrarySha256))
                    put("testId", JsonPrimitive(proof.testId))
                    put("status", JsonPrimitive(proof.status.name.lowercase()))
                    put("candidateCommit", JsonPrimitive(proof.candidateCommit))
                    put("candidateTree", JsonPrimitive(proof.candidateTree))
                })
            }
        })
        put("testProgramSha256", JsonPrimitive(receipt.testProgramSha256))
        put("testResultsSha256", JsonPrimitive(receipt.testResultsSha256))
        put("publicSymbols", receipt.publicSymbols.toJsonArray())
        put("tests", buildJsonArray {
            receipt.bindingTests.forEach { test ->
                add(buildJsonObject {
                    put("id", JsonPrimitive(test.testId))
                    put("status", JsonPrimitive(test.status.name.lowercase()))
                })
            }
        })
        put("scenarios", buildJsonArray {
            receipt.scenarioEvidence.forEach { scenario ->
                add(buildJsonObject {
                    put("id", JsonPrimitive(scenario.scenario.id))
                    put("testIds", scenario.testIds.toJsonArray())
                })
            }
        })
        put("claims", buildJsonArray {
            receipt.projectionClaims.forEach { claim ->
                add(buildJsonObject {
                    put("capabilityKey", JsonPrimitive(claim.capabilityKey))
                    put("publicSymbols", claim.publicSymbols.toJsonArray())
                    put("executedTests", claim.executedTests.toJsonArray())
                    put("sharedScenarios", claim.sharedScenarios.map(CrossLanguageBindingScenario::id).toJsonArray())
                })
            }
        })
        put("exclusions", buildJsonArray {
            receipt.applicabilityExclusions.forEach { exclusion ->
                add(buildJsonObject {
                    put("capabilityKey", JsonPrimitive(exclusion.capabilityKey))
                    put("reason", JsonPrimitive(exclusion.reason))
                })
            }
        })
    }
}

private fun JsonObject.toCrossLanguageBindingReceipt(): CrossLanguageBindingReceipt {
    requireKeys(
        "receipt",
        "schema", "result", "phase", "language", "canonical", "artifacts", "hostConsumerProofs",
        "testProgramSha256", "testResultsSha256", "publicSymbols", "tests", "scenarios",
        "claims", "exclusions",
    )
    check(exactInt("schema") == CROSS_LANGUAGE_BINDING_RECEIPT_SCHEMA) {
        "Unsupported cross-language binding receipt schema"
    }
    check(exactString("result") == "passed") { "Cross-language binding receipt did not pass" }
    val phaseName = exactString("phase")
    val phase = CrossLanguageBindingPhase.entries.singleOrNull { it.name == phaseName }
        ?: error("Unknown cross-language binding phase: $phaseName")
    val languageId = exactString("language")
    val language = CrossLanguageBinding.entries.singleOrNull { it.id == languageId }
        ?: error("Unknown cross-language binding language: $languageId")
    val canonicalObject = exactObject("canonical").also {
        it.requireKeys("canonical identity", "apiReportSha256", "coverageReceiptSha256")
    }
    val hostConsumerProofs = exactArray("hostConsumerProofs").map { value ->
        val proof = value.exactObject("binding host consumer proof")
        proof.requireKeys(
            "binding host consumer proof",
            "classifier", "runnerOs", "runnerArch", "toolchainIdentitySha256", "packageArtifactId",
            "packageSha256", "nativeLibrarySha256", "testId", "status", "candidateCommit", "candidateTree",
        )
        val statusId = proof.exactString("status")
        val status = CrossLanguageBindingTestStatus.entries.singleOrNull {
            it.name.lowercase() == statusId
        } ?: error("Unknown cross-language binding host consumer status: $statusId")
        CrossLanguageBindingHostConsumerProof(
            classifier = proof.exactString("classifier"),
            runnerOs = proof.exactString("runnerOs"),
            runnerArch = proof.exactString("runnerArch"),
            toolchainIdentitySha256 = proof.exactString("toolchainIdentitySha256"),
            packageArtifactId = proof.exactString("packageArtifactId"),
            packageSha256 = proof.exactString("packageSha256"),
            nativeLibrarySha256 = proof.exactString("nativeLibrarySha256"),
            testId = proof.exactString("testId"),
            status = status,
            candidateCommit = proof.exactString("candidateCommit"),
            candidateTree = proof.exactString("candidateTree"),
        )
    }
    val tests = exactArray("tests").map { value ->
        val test = value.exactObject("binding test")
        test.requireKeys("binding test", "id", "status")
        val statusId = test.exactString("status")
        val status = CrossLanguageBindingTestStatus.entries.singleOrNull {
            it.name.lowercase() == statusId
        } ?: error("Unknown cross-language binding test status: $statusId")
        CrossLanguageBindingTestEvidence(language, test.exactString("id"), status)
    }
    val scenarios = exactArray("scenarios").map { value ->
        val scenario = value.exactObject("binding scenario")
        scenario.requireKeys("binding scenario", "id", "testIds")
        val scenarioId = scenario.exactString("id")
        val scenarioType = CrossLanguageBindingScenario.entries.singleOrNull { it.id == scenarioId }
            ?: error("Unknown cross-language binding scenario: $scenarioId")
        CrossLanguageScenarioEvidence(language, scenarioType, scenario.exactStrings("testIds"))
    }
    val claims = exactArray("claims").map { value ->
        val claim = value.exactObject("binding claim")
        claim.requireKeys(
            "binding claim", "capabilityKey", "publicSymbols", "executedTests", "sharedScenarios",
        )
        CrossLanguageProjectionClaim(
            capabilityKey = claim.exactString("capabilityKey"),
            language = language,
            publicSymbols = claim.exactStrings("publicSymbols"),
            executedTests = claim.exactStrings("executedTests"),
            sharedScenarios = claim.exactStrings("sharedScenarios").map { scenarioId ->
                CrossLanguageBindingScenario.entries.singleOrNull { it.id == scenarioId }
                    ?: error("Unknown cross-language binding claim scenario: $scenarioId")
            },
        )
    }
    val exclusions = exactArray("exclusions").map { value ->
        val exclusion = value.exactObject("binding exclusion")
        exclusion.requireKeys("binding exclusion", "capabilityKey", "reason")
        CrossLanguageApplicabilityExclusion(
            exclusion.exactString("capabilityKey"),
            language,
            exclusion.exactString("reason"),
        )
    }
    return CrossLanguageBindingReceipt(
        phase = phase,
        language = language,
        canonical = CrossLanguageBindingCanonicalIdentity(
            canonicalObject.exactString("apiReportSha256"),
            canonicalObject.exactString("coverageReceiptSha256"),
        ),
        artifacts = exactArray("artifacts").map { value ->
            val artifact = value.exactObject("binding artifact")
            artifact.requireKeys("binding artifact", "id", "sha256")
            CrossLanguageBindingArtifactIdentity(
                artifact.exactString("id"),
                artifact.exactString("sha256"),
            )
        },
        testProgramSha256 = exactString("testProgramSha256"),
        testResultsSha256 = exactString("testResultsSha256"),
        publicSymbols = exactStrings("publicSymbols"),
        bindingTests = tests,
        scenarioEvidence = scenarios,
        projectionClaims = claims,
        applicabilityExclusions = exclusions,
        hostConsumerProofs = hostConsumerProofs,
    )
}

private fun CrossLanguageBindingReceipt.normalized(): CrossLanguageBindingReceipt {
    requireSha256(canonical.apiReportSha256, "canonical API report")
    requireSha256(canonical.coverageReceiptSha256, "canonical coverage receipt")
    requireSha256(testProgramSha256, "binding test program")
    requireSha256(testResultsSha256, "binding test results")
    check(artifacts.isNotEmpty()) { "Cross-language binding artifact inventory is empty" }
    requireUnique(artifacts.map(CrossLanguageBindingArtifactIdentity::id), "binding artifact")
    artifacts.forEach { artifact ->
        requireExactRecord(artifact.id, "binding artifact")
        requireSha256(artifact.sha256, "binding artifact ${artifact.id}")
    }
    val artifactDigests = artifacts.associate { it.id to it.sha256 }
    val expectedHostProofs = crossLanguageCAbiTargetSpecs.values.associateBy {
        it.classifier.removePrefix("c-abi-")
    }
    val nativeWrapper = language in nativeWrapperBindings
    if (nativeWrapper) {
        check(language.isActive(phase)) { "Native wrapper host proof language is inactive at ${phase.name}" }
        check(hostConsumerProofs.map(CrossLanguageBindingHostConsumerProof::classifier).toSet() ==
            expectedHostProofs.keys && hostConsumerProofs.size == expectedHostProofs.size) {
            "Native wrapper receipt requires the exact five host consumer proofs"
        }
    } else check(hostConsumerProofs.isEmpty()) {
        "Non-native binding receipt must not carry host consumer proofs"
    }
    requireUnique(hostConsumerProofs.map(CrossLanguageBindingHostConsumerProof::classifier), "host classifier")
    requireUnique(hostConsumerProofs.map(CrossLanguageBindingHostConsumerProof::testId), "host consumer test")
    hostConsumerProofs.forEach { proof ->
        val spec = expectedHostProofs[proof.classifier]
            ?: error("Unsupported native wrapper host classifier: ${proof.classifier}")
        check(proof.runnerOs == spec.runnerOs && proof.runnerArch == spec.runnerArch) {
            "Native wrapper host runner identity mismatch for ${proof.classifier}"
        }
        requireSha256(proof.toolchainIdentitySha256, "host toolchain identity ${proof.classifier}")
        requireExactRecord(proof.packageArtifactId, "host package artifact ${proof.classifier}")
        requireSha256(proof.packageSha256, "host package ${proof.classifier}")
        requireSha256(proof.nativeLibrarySha256, "host native library ${proof.classifier}")
        requireExactRecord(proof.testId, "host consumer test ${proof.classifier}")
        check(proof.status == CrossLanguageBindingTestStatus.PASSED) {
            "Native wrapper host consumer did not pass for ${proof.classifier}"
        }
        requireGitOid(proof.candidateCommit, "host candidate commit ${proof.classifier}")
        requireGitOid(proof.candidateTree, "host candidate tree ${proof.classifier}")
        check(artifactDigests[proof.packageArtifactId] == proof.packageSha256) {
            "Native wrapper host package artifact mismatch for ${proof.classifier}"
        }
    }
    check(hostConsumerProofs.map { it.candidateCommit }.distinct().size <= 1 &&
        hostConsumerProofs.map { it.candidateTree }.distinct().size <= 1) {
        "Native wrapper host proofs mix candidate identities"
    }
    requireUnique(publicSymbols, "binding public symbol")
    publicSymbols.forEach { requireExactRecord(it, "binding public symbol") }

    bindingTests.forEach { test ->
        check(test.language == language) { "Binding test language does not match receipt language" }
        requireExactRecord(test.testId, "binding test")
    }
    requireUnique(bindingTests.map(CrossLanguageBindingTestEvidence::testId), "binding test")
    val testIds = bindingTests.mapTo(mutableSetOf(), CrossLanguageBindingTestEvidence::testId)

    scenarioEvidence.forEach { scenario ->
        check(scenario.language == language) { "Binding scenario language does not match receipt language" }
        check(scenario.testIds.isNotEmpty()) { "Binding scenario ${scenario.scenario.id} has no tests" }
        requireUnique(scenario.testIds, "binding scenario test ${scenario.scenario.id}")
        scenario.testIds.forEach { testId ->
            requireExactRecord(testId, "binding scenario test ${scenario.scenario.id}")
            check(testId in testIds) {
                "Binding scenario ${scenario.scenario.id} references stale test $testId"
            }
        }
    }
    requireUnique(scenarioEvidence.map(CrossLanguageScenarioEvidence::scenario), "binding scenario")
    check(scenarioEvidence.map(CrossLanguageScenarioEvidence::scenario).toSet() ==
        CrossLanguageBindingScenario.entries.toSet()) {
        "Cross-language binding receipt requires the exact shared scenario inventory"
    }
    val scenarios = scenarioEvidence.mapTo(mutableSetOf(), CrossLanguageScenarioEvidence::scenario)
    val symbols = publicSymbols.toSet()

    projectionClaims.forEach { claim ->
        check(claim.language == language) { "Binding claim language does not match receipt language" }
        requireExactRecord(claim.capabilityKey, "binding claim capability")
        check(claim.publicSymbols.isNotEmpty()) { "Binding claim ${claim.capabilityKey} has no public symbols" }
        requireUnique(claim.publicSymbols, "binding claim public symbol ${claim.capabilityKey}")
        claim.publicSymbols.forEach { symbol ->
            requireExactRecord(symbol, "binding claim public symbol ${claim.capabilityKey}")
            check(symbol in symbols) { "Binding claim ${claim.capabilityKey} references stale public symbol $symbol" }
        }
        check(claim.executedTests.isNotEmpty()) { "Binding claim ${claim.capabilityKey} has no tests" }
        requireUnique(claim.executedTests, "binding claim test ${claim.capabilityKey}")
        claim.executedTests.forEach { testId ->
            requireExactRecord(testId, "binding claim test ${claim.capabilityKey}")
            check(testId in testIds) { "Binding claim ${claim.capabilityKey} references stale test $testId" }
        }
        check(claim.sharedScenarios.isNotEmpty()) { "Binding claim ${claim.capabilityKey} has no scenarios" }
        requireUnique(claim.sharedScenarios, "binding claim scenario ${claim.capabilityKey}")
        claim.sharedScenarios.forEach { scenario ->
            check(scenario in scenarios) {
                "Binding claim ${claim.capabilityKey} references stale scenario ${scenario.id}"
            }
        }
    }
    requireUnique(projectionClaims.map(CrossLanguageProjectionClaim::capabilityKey), "binding claim capability")

    applicabilityExclusions.forEach { exclusion ->
        check(exclusion.language == language) { "Binding exclusion language does not match receipt language" }
        requireExactRecord(exclusion.capabilityKey, "binding exclusion capability")
        requireExactReason(exclusion.reason, exclusion.capabilityKey)
    }
    requireUnique(
        applicabilityExclusions.map(CrossLanguageApplicabilityExclusion::capabilityKey),
        "binding exclusion capability",
    )
    val conflicts = projectionClaims.mapTo(mutableSetOf(), CrossLanguageProjectionClaim::capabilityKey)
        .intersect(applicabilityExclusions.mapTo(mutableSetOf(), CrossLanguageApplicabilityExclusion::capabilityKey))
    check(conflicts.isEmpty()) { "Binding claims conflict with exclusions: ${conflicts.sorted()}" }
    if (language == CrossLanguageBinding.KOTLIN) {
        check(projectionClaims.isEmpty() && applicabilityExclusions.isEmpty()) {
            "Kotlin binding receipt must not carry projection claims or exclusions"
        }
    } else check(projectionClaims.isNotEmpty() || applicabilityExclusions.isNotEmpty()) {
        "Non-Kotlin binding receipt has no claims or exclusions"
    }

    return copy(
        artifacts = artifacts.sortedBy(CrossLanguageBindingArtifactIdentity::id),
        publicSymbols = publicSymbols.sorted(),
        bindingTests = bindingTests.sortedBy(CrossLanguageBindingTestEvidence::testId),
        scenarioEvidence = scenarioEvidence.map { it.copy(testIds = it.testIds.sorted()) }
            .sortedBy { it.scenario.id },
        projectionClaims = projectionClaims.map { claim ->
            claim.copy(
                publicSymbols = claim.publicSymbols.sorted(),
                executedTests = claim.executedTests.sorted(),
                sharedScenarios = claim.sharedScenarios.sortedBy(CrossLanguageBindingScenario::id),
            )
        }.sortedBy(CrossLanguageProjectionClaim::capabilityKey),
        applicabilityExclusions = applicabilityExclusions.sortedBy(
            CrossLanguageApplicabilityExclusion::capabilityKey,
        ),
        hostConsumerProofs = hostConsumerProofs.sortedBy(CrossLanguageBindingHostConsumerProof::classifier),
    )
}

private fun CrossLanguageBindingReceipt.canonicalJson(): String =
    releaseJson.encodeToString(JsonElement.serializer(), toJson()) + "\n"

private fun Iterable<String>.toJsonArray(): JsonArray = buildJsonArray {
    this@toJsonArray.forEach { add(JsonPrimitive(it)) }
}

private fun JsonObject.requireKeys(label: String, vararg expected: String) {
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

private fun JsonObject.exactArray(name: String): JsonArray = this[name] as? JsonArray
    ?: error("Missing JSON array: $name")

private fun JsonObject.exactObject(name: String): JsonObject = this[name] as? JsonObject
    ?: error("Missing JSON object: $name")

private fun JsonElement.exactObject(label: String): JsonObject = this as? JsonObject
    ?: error("Cross-language $label must be a JSON object")

private fun JsonObject.exactStrings(name: String): List<String> = exactArray(name).map { value ->
    val primitive = value as? JsonPrimitive ?: error("$name must contain only strings")
    check(primitive.isString) { "$name must contain only strings" }
    primitive.content
}

private fun requireSha256(value: String, label: String) {
    check(value.length == 64 && value.all { it in '0'..'9' || it in 'a'..'f' }) {
        "$label SHA-256 is not exact"
    }
}

private fun requireGitOid(value: String, label: String) {
    check(value.length == 40 && value.all { it in '0'..'9' || it in 'a'..'f' }) {
        "$label is not an exact Git object ID"
    }
}

private fun requireExactRecord(value: String, label: String) {
    check(value.isNotBlank() && value == value.trim() && '*' !in value && value.none(Char::isISOControl)) {
        "$label is blank, wildcarded, or malformed: $value"
    }
}

private fun requireExactReason(reason: String, capabilityKey: String) {
    check(reason.isNotBlank() && reason == reason.trim() && '*' !in reason && reason.none(Char::isISOControl)) {
        "Binding exclusion reason is blank, wildcarded, or malformed for $capabilityKey"
    }
}

private fun <T> requireUnique(values: List<T>, label: String) {
    val duplicates = values.groupingBy { it }.eachCount().filterValues { it > 1 }.keys
    check(duplicates.isEmpty()) { "$label records are duplicated: $duplicates" }
}
