import org.gradle.api.Project
import org.gradle.api.file.Directory
import org.gradle.api.file.RegularFile
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.register

internal data class IosImportedContractEvidenceTasks(
    val verify: TaskProvider<VerifyImportedProductOutputManifestTask>,
    val canonicalApi: Provider<RegularFile>,
    val canonicalCoverage: Provider<RegularFile>,
)

/** Stage identity/integrity only; original Contract receipt/attestation admission remains external. */
internal fun Project.registerIosImportedContractEvidenceTasks(
    source: Provider<Directory>,
    version: Provider<String>,
    candidateTree: Provider<String>,
    invalidateEvidence: TaskProvider<Delete>,
): IosImportedContractEvidenceTasks {
    check(source.isPresent) { "Imported Apple evidence requires codexAgent.contractBinaryStage" }
    val expectedVersion = version.orNull
    check(expectedVersion != null && PRODUCT_SEMVER.matches(expectedVersion)) {
        "Imported Apple evidence requires an exact codexAgent.contractVersion"
    }
    val tree = candidateTree.orNull
    check(tree != null && tree.matches(Regex("[0-9a-f]{40}|[0-9a-f]{64}"))) {
        "Imported Apple evidence requires an exact codexAgent.candidateTree"
    }
    val snapshotRoot = layout.buildDirectory.dir("imported-apple-contract-evidence/$tree/contract")
    val reset = tasks.register<Delete>("resetImportedAppleContractEvidence") {
        dependsOn(invalidateEvidence)
        delete(snapshotRoot)
    }
    val snapshot = tasks.register<SnapshotImportedProductStageTask>("snapshotImportedAppleContractEvidence") {
        dependsOn(reset)
        sourceDirectory.set(source)
        outputDirectory.set(snapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verify = tasks.register<VerifyImportedProductOutputManifestTask>("verifyImportedAppleContractEvidence") {
        dependsOn(snapshot)
        product.set("contract")
        component.set("contract")
        phase.set("binary")
        target.set("common")
        productVersion.set(expectedVersion)
        stageRoot.set(snapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    return IosImportedContractEvidenceTasks(
        verify,
        snapshotRoot.map { it.file("outputs/evidence/canonical-api.json") },
        snapshotRoot.map { it.file("outputs/evidence/canonical-coverage.json") },
    )
}
