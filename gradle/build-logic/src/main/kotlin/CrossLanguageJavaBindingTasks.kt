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
        writeCrossLanguageBindingReceipt(output, receipt)
        verifyJavaBindingParityReceipt(readCrossLanguageBindingReceipt(output), receipt)
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
): CrossLanguageBindingReceipt {
    val artifacts = evidence.digests.artifactDigests
    return CrossLanguageBindingReceipt(
        phase = CrossLanguageBindingPhase.M8,
        language = CrossLanguageBinding.JAVA,
        canonical = CrossLanguageBindingCanonicalIdentity(
            apiReportSha256 = canonicalDigests.apiReportSha256,
            coverageReceiptSha256 = canonicalDigests.canonicalCoverageSha256,
        ),
        artifacts = listOf(
            CrossLanguageBindingArtifactIdentity(
                "android-runtime-aar",
                artifacts.androidRuntimeAarSha256,
            ),
            CrossLanguageBindingArtifactIdentity(
                "core-android-aar",
                artifacts.coreAndroidAarSha256,
            ),
            CrossLanguageBindingArtifactIdentity(
                "core-jvm-jar",
                artifacts.coreJvmJarSha256,
            ),
            CrossLanguageBindingArtifactIdentity(
                "desktop-runtime-jar",
                artifacts.desktopRuntimeJarSha256,
            ),
        ),
        testProgramSha256 = evidence.digests.compiledTestsSha256,
        testResultsSha256 = evidence.digests.testResultsSha256,
        publicSymbols = evidence.publicSymbols,
        bindingTests = evidence.bindingTests,
        scenarioEvidence = evidence.scenarioEvidence,
        projectionClaims = evidence.projectionClaims,
        applicabilityExclusions = emptyList(),
    )
}

internal fun verifyJavaBindingParityReceipt(
    actual: CrossLanguageBindingReceipt,
    expected: CrossLanguageBindingReceipt,
) {
    check(actual.toJson() == expected.toJson()) {
        "Java binding parity receipt does not match freshly recomputed evidence"
    }
}
