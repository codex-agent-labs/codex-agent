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
abstract class VerifyJavaBindingParityTask : DefaultTask() {
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

    @get:OutputFile
    abstract val receiptFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = receiptFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val report = apiReport.get().asFile
        val coverage = canonicalCoverageReceipt.get().asFile
        val canonicalEvidence = deriveCrossLanguageKotlinBindingEvidence(
            kotlinArtifact.get().asFile,
            report,
            coverage,
        )
        val javaEvidence = deriveVerifiedJavaBindingParityEvidence(
            canonicalEvidence,
            coreJvmJar.get().asFile,
            coreAndroidAar.get().asFile,
            desktopRuntimeJar.get().asFile,
            androidRuntimeAar.get().asFile,
            compiledJavaTests = compiledJavaTests.get().asFile,
            testResultsDirectory = testResults.get().asFile,
        )
        val receipt = buildJavaBindingParityReceipt(canonicalEvidence.digests, javaEvidence)
        output.atomicWriteJson(receipt)
        verifyJavaBindingParityReceipt(output.readReleaseObject(), receipt)
    }
}

internal fun deriveVerifiedJavaBindingParityEvidence(
    canonicalEvidence: CrossLanguageKotlinBindingEvidence,
    coreJvmJar: java.io.File,
    coreAndroidAar: java.io.File,
    desktopRuntimeJar: java.io.File,
    androidRuntimeAar: java.io.File,
    compiledJavaTests: java.io.File,
    testResultsDirectory: java.io.File,
): CrossLanguageJavaBindingParityEvidence {
    val capabilityKeys = canonicalEvidence.capabilityClaims.map(KotlinBindingCapabilityClaim::capabilityKey)
    val structuralEvidence = deriveCrossLanguageJavaBindingStructuralEvidence(
        capabilityKeys,
        coreJvmJar,
        coreAndroidAar,
        desktopRuntimeJar,
        androidRuntimeAar,
        javaBindingExceptionalAliases,
    )
    return deriveCrossLanguageJavaBindingParityEvidence(
        canonicalCapabilityKeys = capabilityKeys,
        canonicalCoverageKeys = capabilityKeys,
        structuralEvidence = structuralEvidence,
        compiledJavaTests = compiledJavaTests,
        testResultsDirectory = testResultsDirectory,
    )
}

internal fun buildJavaBindingParityReceipt(
    canonicalDigests: KotlinBindingDigestEvidence,
    evidence: CrossLanguageJavaBindingParityEvidence,
): JsonObject = buildJsonObject {
    put("schema", JsonPrimitive(1))
    put("result", JsonPrimitive("passed"))
    put("language", JsonPrimitive(CrossLanguageBinding.JAVA.id))
    put("phase", JsonPrimitive(CrossLanguageBindingPhase.M7_5.name))
    put("apiReportSha256", JsonPrimitive(canonicalDigests.apiReportSha256))
    put("canonicalCoverageSha256", JsonPrimitive(canonicalDigests.canonicalCoverageSha256))
    put("canonicalArtifactSha256", JsonPrimitive(canonicalDigests.artifactSha256))
    put("artifacts", buildJsonObject {
        val artifacts = evidence.digests.artifactDigests
        put("coreJvmJarSha256", JsonPrimitive(artifacts.coreJvmJarSha256))
        put("coreAndroidAarSha256", JsonPrimitive(artifacts.coreAndroidAarSha256))
        put("desktopRuntimeJarSha256", JsonPrimitive(artifacts.desktopRuntimeJarSha256))
        put("androidRuntimeAarSha256", JsonPrimitive(artifacts.androidRuntimeAarSha256))
    })
    put("compiledTestsSha256", JsonPrimitive(evidence.digests.compiledTestsSha256))
    put("testResultsSha256", JsonPrimitive(evidence.digests.testResultsSha256))
    put("summary", buildJsonObject {
        put("capabilities", JsonPrimitive(evidence.javaObligations.size))
        put("publicSymbols", JsonPrimitive(evidence.publicSymbols.size))
        put("tests", JsonPrimitive(evidence.bindingTests.size))
        put("scenarios", JsonPrimitive(evidence.scenarioEvidence.size))
    })
    put("tests", buildJsonArray {
        evidence.bindingTests.forEach { test -> add(JsonPrimitive(test.testId)) }
    })
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
    put("claims", buildJsonArray {
        evidence.projectionClaims.forEach { claim ->
            add(buildJsonObject {
                put("capabilityKey", JsonPrimitive(claim.capabilityKey))
                put("publicSymbols", buildJsonArray {
                    claim.publicSymbols.forEach { add(JsonPrimitive(it)) }
                })
            })
        }
    })
}

internal fun verifyJavaBindingParityReceipt(actual: JsonObject, expected: JsonObject) {
    check(actual == expected) { "Java binding parity receipt does not match freshly recomputed evidence" }
}
