import java.nio.file.Files
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

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val kotlinReceipt: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val javaReceipt: RegularFileProperty

    @get:OutputFile
    abstract val auditFile: RegularFileProperty

    @TaskAction
    fun audit() {
        val kotlinReceiptFile = kotlinReceipt.get().asFile
        val javaReceiptFile = javaReceipt.get().asFile
        writeCrossLanguageBindingAudit(
            phase = CrossLanguageBindingPhase.M7_5,
            apiReport = apiReport.get().asFile,
            canonicalCoverageReceipt = canonicalCoverageReceipt.get().asFile,
            receiptFiles = mapOf(
                CrossLanguageBinding.KOTLIN to kotlinReceiptFile,
                CrossLanguageBinding.JAVA to javaReceiptFile,
            ),
            auditFile = auditFile.get().asFile,
        )
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

    @get:OutputFile
    abstract val receiptFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = receiptFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val report = apiReport.get().asFile
        val coverage = canonicalCoverageReceipt.get().asFile
        val artifact = kotlinArtifact.get().asFile
        val evidence = deriveCrossLanguageKotlinBindingEvidence(artifact, report, coverage)
        val receipt = buildKotlinBindingParityReceipt(evidence)
        writeCrossLanguageBindingReceipt(output, receipt)
        verifyKotlinBindingParityReceipt(readCrossLanguageBindingReceipt(output), receipt)
    }
}

internal fun buildKotlinBindingParityReceipt(
    evidence: CrossLanguageKotlinBindingEvidence,
): CrossLanguageBindingReceipt {
    val capabilityKeys = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
    check(capabilityKeys.isNotEmpty() && capabilityKeys.size == capabilityKeys.distinct().size) {
        "Kotlin binding capability inventory is empty or duplicated"
    }
    val publicSymbols = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::publicSymbol)
    check(publicSymbols == capabilityKeys) {
        "Kotlin binding public symbols must exactly match canonical capabilities"
    }
    check(evidence.bindingTests.all { it.status == CrossLanguageBindingTestStatus.PASSED }) {
        "Kotlin binding receipt requires passed tests"
    }
    return CrossLanguageBindingReceipt(
        phase = CrossLanguageBindingPhase.M7_5,
        language = CrossLanguageBinding.KOTLIN,
        canonical = CrossLanguageBindingCanonicalIdentity(
            evidence.digests.apiReportSha256,
            evidence.digests.canonicalCoverageSha256,
        ),
        artifacts = listOf(
            CrossLanguageBindingArtifactIdentity("kotlin-public-api", evidence.digests.artifactSha256),
        ),
        testProgramSha256 = evidence.digests.compiledTestsSha256,
        testResultsSha256 = evidence.digests.testResultsSha256,
        publicSymbols = publicSymbols,
        bindingTests = evidence.bindingTests,
        scenarioEvidence = evidence.scenarioEvidence,
        projectionClaims = emptyList(),
        applicabilityExclusions = emptyList(),
    )
}

internal fun verifyKotlinBindingParityReceipt(
    actual: CrossLanguageBindingReceipt,
    expected: CrossLanguageBindingReceipt,
) {
    check(actual.toJson() == expected.toJson()) {
        "Kotlin binding parity receipt does not match freshly recomputed evidence"
    }
}
