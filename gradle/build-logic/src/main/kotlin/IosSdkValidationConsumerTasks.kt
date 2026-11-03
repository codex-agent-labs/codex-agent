import java.io.File
import org.gradle.api.Project
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.TaskProvider

/**
 * Reuses caller-authenticated package and Contract snapshots for compiler/XCTest validation.
 * This rewiring grants no source, receipt, host, or product-build authority.
 */
internal fun Project.configureIosSdkValidationConsumers(
    packageInputs: TaskProvider<PrepareAppleValidationPackageInputsTask>,
    contractEvidence: IosImportedContractEvidenceTasks,
    verifyAppleToolchain: TaskProvider<VerifyAppleToolchainTask>,
    invalidateEvidence: TaskProvider<Delete>,
    distribution: IosAppleDistributionTasks,
    compilerEvidence: TaskProvider<AppleCompilerEvidenceTask>,
    bindingEvidence: TaskProvider<GenerateAppleBindingEvidenceTask>,
) {
    // Keep this provider free of Kotlin build-script references when Gradle serializes it.
    val developer = layout.dir(providers.environmentVariable("DEVELOPER_DIR").map { File(it) })
    tasks.withType(VerifyAppleDeviceConsumerTask::class.java).configureEach {
        developerDirectory.set(developer)
    }
    val swiftTests = distribution.verifyCodexAgentSwiftAuthenticationTests
    compilerEvidence.configure {
        setDependsOn(listOf(invalidateEvidence, verifyAppleToolchain, packageInputs, contractEvidence.verify))
        xcframeworkDirectory.set(packageInputs.flatMap { it.xcframeworkDirectory })
        canonicalApiReport.set(contractEvidence.canonicalApi)
        canonicalCoverageReceipt.set(contractEvidence.canonicalCoverage)
    }
    swiftTests.configure {
        setDependsOn(listOf(invalidateEvidence, verifyAppleToolchain, packageInputs))
        packageDirectory.set(packageInputs.flatMap { it.packageDirectory })
    }
    bindingEvidence.configure {
        setDependsOn(listOf(invalidateEvidence, compilerEvidence, swiftTests, contractEvidence.verify))
        xcframeworkDirectory.set(packageInputs.flatMap { it.xcframeworkDirectory })
        canonicalApiReport.set(contractEvidence.canonicalApi)
        canonicalCoverageReceipt.set(contractEvidence.canonicalCoverage)
    }
}
