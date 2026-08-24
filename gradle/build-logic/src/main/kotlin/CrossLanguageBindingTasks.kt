import java.nio.file.Files
import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class AuditCrossLanguageBindingParityTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val kotlinArtifact: DirectoryProperty

    @get:OutputFile
    abstract val auditFile: RegularFileProperty

    @TaskAction
    fun audit() {
        val output = auditFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val evidence = deriveCrossLanguageKotlinBindingEvidence(
            kotlinArtifact.get().asFile,
            apiReport.get().asFile,
            canonicalCoverageReceipt.get().asFile,
        )
        output.atomicWriteJson(buildCrossLanguageBindingAudit(evidence).toJson())
    }
}

@CacheableTask
abstract class VerifyKotlinBindingParityTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val kotlinArtifact: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val bindingAudit: RegularFileProperty

    @get:OutputFile
    abstract val receiptFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = receiptFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val report = apiReport.get().asFile
        val coverage = canonicalCoverageReceipt.get().asFile
        val artifact = kotlinArtifact.get().asFile
        val audit = bindingAudit.get().asFile
        val evidence = deriveCrossLanguageKotlinBindingEvidence(artifact, report, coverage)
        val memberKeys = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
        val verifiedAudit = readCrossLanguageBindingAudit(
            auditFile = audit,
            expectedEvidence = evidence,
        )
        check(verifiedAudit.phase == CrossLanguageBindingPhase.M7_5) {
            "Kotlin binding parity requires the M7.5 obligation phase"
        }
        check(verifiedAudit.compiledTestsSha256 == evidence.digests.compiledTestsSha256 &&
            verifiedAudit.testResultsSha256 == evidence.digests.testResultsSha256) {
            "Kotlin binding parity test evidence digest mismatch"
        }
        check(verifiedAudit.kotlinScenarios == evidence.scenarioEvidence) {
            "Kotlin binding scenario evidence mismatch"
        }
        val kotlinObligations = verifiedAudit.obligations.filter {
            it.language == CrossLanguageBinding.KOTLIN
        }
        check(kotlinObligations.size == memberKeys.size && kotlinObligations.all {
            it.applicable &&
                it.obligationState == CrossLanguageBindingObligationState.ACTIVE &&
                it.parityStatus == CrossLanguageObligationStatus.SATISFIED
        }) { "Kotlin binding obligations are incomplete" }
        output.atomicWriteJson(buildJsonObject {
            put("schema", JsonPrimitive(1))
            put("result", JsonPrimitive("passed"))
            put("language", JsonPrimitive(CrossLanguageBinding.KOTLIN.id))
            put("phase", JsonPrimitive(CrossLanguageBindingPhase.M7_5.name))
            put("apiReportSha256", JsonPrimitive(evidence.digests.apiReportSha256))
            put("canonicalCoverageSha256", JsonPrimitive(evidence.digests.canonicalCoverageSha256))
            put("bindingAuditSha256", JsonPrimitive(audit.releaseDigest()))
            put("publicArtifactSha256", JsonPrimitive(evidence.digests.artifactSha256))
            put("compiledTestsSha256", JsonPrimitive(evidence.digests.compiledTestsSha256))
            put("testResultsSha256", JsonPrimitive(evidence.digests.testResultsSha256))
            put("capabilityCount", JsonPrimitive(kotlinObligations.size))
            put("scenarios", buildJsonArray {
                evidence.scenarioEvidence.forEach { scenario ->
                    add(buildJsonObject {
                        put("id", JsonPrimitive(scenario.scenario.id))
                        put("testIds", buildJsonArray {
                            scenario.testIds.forEach { add(JsonPrimitive(it)) }
                        })
                    })
                }
            })
        })
        verifyKotlinBindingParityReceipt(
            receipt = output,
            expectedApiReportSha256 = evidence.digests.apiReportSha256,
            expectedCanonicalCoverageSha256 = evidence.digests.canonicalCoverageSha256,
            expectedBindingAuditSha256 = audit.releaseDigest(),
            expectedPublicArtifactSha256 = evidence.digests.artifactSha256,
            expectedCompiledTestsSha256 = evidence.digests.compiledTestsSha256,
            expectedTestResultsSha256 = evidence.digests.testResultsSha256,
            expectedCapabilityCount = kotlinObligations.size,
            expectedScenarioEvidence = evidence.scenarioEvidence,
        )
    }
}

internal fun verifyKotlinBindingParityReceipt(
    receipt: File,
    expectedApiReportSha256: String,
    expectedCanonicalCoverageSha256: String,
    expectedBindingAuditSha256: String,
    expectedPublicArtifactSha256: String,
    expectedCompiledTestsSha256: String,
    expectedTestResultsSha256: String,
    expectedCapabilityCount: Int,
    expectedScenarioEvidence: List<CrossLanguageScenarioEvidence>,
) {
    val root = receipt.readReleaseObject()
    check(root.keys == setOf(
        "schema", "result", "language", "phase", "apiReportSha256", "canonicalCoverageSha256",
        "bindingAuditSha256", "publicArtifactSha256", "compiledTestsSha256", "testResultsSha256",
        "capabilityCount", "scenarios",
    )) { "Invalid Kotlin binding parity receipt shape" }
    check(root.releaseInt("schema") == 1 && root.releaseString("result") == "passed") {
        "Kotlin binding parity receipt did not pass"
    }
    check(root.releaseString("language") == CrossLanguageBinding.KOTLIN.id &&
        root.releaseString("phase") == CrossLanguageBindingPhase.M7_5.name) {
        "Kotlin binding parity receipt identity mismatch"
    }
    mapOf(
        "apiReportSha256" to expectedApiReportSha256,
        "canonicalCoverageSha256" to expectedCanonicalCoverageSha256,
        "bindingAuditSha256" to expectedBindingAuditSha256,
        "publicArtifactSha256" to expectedPublicArtifactSha256,
        "compiledTestsSha256" to expectedCompiledTestsSha256,
        "testResultsSha256" to expectedTestResultsSha256,
    ).forEach { (name, expected) ->
        check(expected.length == 64 && root.releaseString(name) == expected) {
            "Kotlin binding parity receipt $name mismatch"
        }
    }
    check(root.releaseInt("capabilityCount") == expectedCapabilityCount && expectedCapabilityCount > 0) {
        "Kotlin binding parity capability count mismatch"
    }
    val scenarios = root.releaseArray("scenarios").map { value ->
        val record = value as? JsonObject ?: error("Invalid Kotlin binding parity scenario")
        check(record.keys == setOf("id", "testIds")) { "Invalid Kotlin binding parity scenario shape" }
        val id = record.releaseString("id")
        val scenario = CrossLanguageBindingScenario.entries.singleOrNull { it.id == id }
            ?: error("Unknown Kotlin binding parity scenario: $id")
        val testIds = record.releaseArray("testIds").map { testId ->
            (testId as? JsonPrimitive)?.content ?: error("Invalid Kotlin binding parity scenario test")
        }
        check(testIds.isNotEmpty() && testIds.none { it.isBlank() || '*' in it } &&
            testIds.size == testIds.distinct().size) {
            "Invalid Kotlin binding parity scenario tests: $id"
        }
        CrossLanguageScenarioEvidence(CrossLanguageBinding.KOTLIN, scenario, testIds)
    }
    check(scenarios == expectedScenarioEvidence) {
        "Kotlin binding parity scenario/test evidence mismatch"
    }
}
