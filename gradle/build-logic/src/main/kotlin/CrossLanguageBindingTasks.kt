import java.nio.file.Files
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

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val coreJvmJar: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val coreAndroidAar: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val desktopRuntimeJar: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val androidRuntimeAar: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compiledJavaTests: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val testResults: DirectoryProperty

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
        val output = auditFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val kotlinEvidence = deriveCrossLanguageKotlinBindingEvidence(
            kotlinArtifact.get().asFile,
            apiReport.get().asFile,
            canonicalCoverageReceipt.get().asFile,
        )
        val javaEvidence = deriveVerifiedJavaBindingParityEvidence(
            kotlinEvidence,
            coreJvmJar.get().asFile,
            coreAndroidAar.get().asFile,
            desktopRuntimeJar.get().asFile,
            androidRuntimeAar.get().asFile,
            compiledJavaTests.get().asFile,
            testResults.get().asFile,
        )
        val kotlinReceiptFile = kotlinReceipt.get().asFile
        val javaReceiptFile = javaReceipt.get().asFile
        verifyKotlinBindingParityReceipt(
            kotlinReceiptFile.readReleaseObject(),
            buildKotlinBindingParityReceipt(kotlinEvidence),
        )
        verifyJavaBindingParityReceipt(
            javaReceiptFile.readReleaseObject(),
            buildJavaBindingParityReceipt(kotlinEvidence.digests, javaEvidence),
        )
        val receiptDigests = mapOf(
            CrossLanguageBinding.KOTLIN to kotlinReceiptFile.releaseDigest(),
            CrossLanguageBinding.JAVA to javaReceiptFile.releaseDigest(),
        )
        val audit = buildCrossLanguageBindingAudit(kotlinEvidence, javaEvidence, receiptDigests)
        output.atomicWriteJson(audit.toJson())
        readCrossLanguageBindingAudit(output, kotlinEvidence, javaEvidence, receiptDigests)
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
        output.atomicWriteJson(receipt)
        verifyKotlinBindingParityReceipt(output.readReleaseObject(), receipt)
    }
}

internal fun buildKotlinBindingParityReceipt(
    evidence: CrossLanguageKotlinBindingEvidence,
): JsonObject = buildJsonObject {
    val capabilityKeys = evidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
    check(capabilityKeys.isNotEmpty() && capabilityKeys.size == capabilityKeys.distinct().size) {
        "Kotlin binding capability inventory is empty or duplicated"
    }
    put("schema", JsonPrimitive(2))
    put("result", JsonPrimitive("passed"))
    put("language", JsonPrimitive(CrossLanguageBinding.KOTLIN.id))
    put("phase", JsonPrimitive(CrossLanguageBindingPhase.M7_5.name))
    put("apiReportSha256", JsonPrimitive(evidence.digests.apiReportSha256))
    put("canonicalCoverageSha256", JsonPrimitive(evidence.digests.canonicalCoverageSha256))
    put("publicArtifactSha256", JsonPrimitive(evidence.digests.artifactSha256))
    put("compiledTestsSha256", JsonPrimitive(evidence.digests.compiledTestsSha256))
    put("testResultsSha256", JsonPrimitive(evidence.digests.testResultsSha256))
    put("capabilityCount", JsonPrimitive(capabilityKeys.size))
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
}

internal fun verifyKotlinBindingParityReceipt(actual: JsonObject, expected: JsonObject) {
    check(actual == expected) { "Kotlin binding parity receipt does not match freshly recomputed evidence" }
}
