import org.gradle.api.Project
import org.gradle.api.file.Directory
import org.gradle.api.file.RegularFile
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.register

/** Integrity-only input graph; the caller authenticates original receipts and owns fresh outputs. */
internal fun Project.registerIosSdkValidationPackageInputs(
    source: Provider<Directory>,
    version: Provider<String>,
    compatibility: Provider<RegularFile>,
    candidateTree: Provider<String>,
    validationTarget: String,
): TaskProvider<PrepareAppleValidationPackageInputsTask> {
    check(validationTarget in setOf("ios-arm64", "ios-simulator-arm64")) {
        "Imported Apple validation requires an exact iOS target"
    }
    check(source.isPresent && compatibility.isPresent) {
        "Imported Apple validation requires package and authenticated compatibility inputs"
    }
    val expectedVersion = version.orNull
    check(expectedVersion != null && PRODUCT_SEMVER.matches(expectedVersion)) {
        "Imported Apple validation requires an exact SDK version"
    }
    val tree = candidateTree.orNull
    check(tree != null && tree.matches(Regex("[0-9a-f]{40}|[0-9a-f]{64}"))) {
        "Imported Apple validation requires an exact candidate tree"
    }
    val root = layout.buildDirectory.dir("imported-sdk-validation/$tree/$validationTarget")
    val snapshotRoot = root.map { it.dir("package-stage") }
    val snapshot = tasks.register<SnapshotImportedProductStageTask>("snapshotSdkIosValidationPackage") {
        sourceDirectory.set(source)
        outputDirectory.set(snapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    val verify = tasks.register<VerifyImportedProductOutputManifestTask>("verifySdkIosValidationPackage") {
        dependsOn(snapshot)
        product.set("sdk")
        component.set("sdk-ios")
        phase.set("package")
        target.set("ios")
        productVersion.set(expectedVersion)
        stageRoot.set(snapshotRoot)
        producerSources.from(rootProject.layout.projectDirectory.dir("ci/products"))
        repositoryRoot.set(rootProject.layout.projectDirectory)
    }
    return tasks.register<PrepareAppleValidationPackageInputsTask>("prepareSdkIosValidationPackage") {
        dependsOn(verify)
        productDirectory.set(snapshotRoot.map { it.dir("outputs/apple") })
        sdkVersion.set(expectedVersion)
        sdkCompatibility.set(compatibility)
        workDirectory.set(root.map { it.dir("extracted") })
    }
}
