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
