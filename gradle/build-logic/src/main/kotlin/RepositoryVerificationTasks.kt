import java.nio.file.Files
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.Project
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.kotlin.dsl.register
import org.gradle.process.ExecOperations

internal const val REPOSITORY_CONTRACT_EVIDENCE_DIRECTORY_PROPERTY =
    "codexAgent.repositoryContractEvidenceDirectory"
internal const val REPOSITORY_RUNTIME_EVIDENCE_DIRECTORY_PROPERTY =
    "codexAgent.repositoryRuntimeEvidenceDirectory"
internal const val REPOSITORY_SDK_EVIDENCE_DIRECTORY_PROPERTY =
    "codexAgent.repositorySdkEvidenceDirectory"
internal const val REPOSITORY_TRUST_DOMAIN_PROPERTY = "codexAgent.repositoryTrustDomain"

abstract class VerifyImportedRepositoryEvidenceTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val contractEvidenceDirectory: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val runtimeEvidenceDirectory: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val sdkEvidenceDirectory: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val productModulesDirectory: DirectoryProperty

    @get:Input
    abstract val contractVersion: Property<String>

    @get:Input
    abstract val runtimeVersion: Property<String>

    @get:Input
    abstract val sdkVersion: Property<String>

    @get:Input
    abstract val trustDomain: Property<String>

    @get:OutputFile
    abstract val resultFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = resultFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val modules = productModulesDirectory.get().asFile
        check(modules.name == "products" && modules.parentFile.name == "ci") {
            "Repository product verifier modules must be supplied as ci/products"
        }
        processes.exec {
            workingDir(modules.parentFile.parentFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(
                "python3", "-m", "ci.products.aggregate", "verify-repository",
                "--contract-evidence", contractEvidenceDirectory.get().asFile.absolutePath,
                "--runtime-evidence", runtimeEvidenceDirectory.get().asFile.absolutePath,
                "--sdk-evidence", sdkEvidenceDirectory.get().asFile.absolutePath,
                "--contract-version", contractVersion.get(),
                "--runtime-version", runtimeVersion.get(),
                "--sdk-version", sdkVersion.get(),
                "--trust-domain", trustDomain.get(),
                "--output", output.absolutePath,
            )
        }
        check(output.isFile) { "Repository evidence verifier did not produce its report" }
    }
}

fun Project.registerRepositoryVerificationTasks(
    contractVersion: String,
    runtimeVersion: String,
    sdkVersion: String,
) {
    val result = layout.buildDirectory.file("reports/repository/imported-product-evidence.json")
    val invalidate = tasks.register<Delete>("invalidateImportedRepositoryEvidenceOutput") {
        delete(result)
    }
    tasks.register<VerifyImportedRepositoryEvidenceTask>("verifyRepository") {
        group = "verification"
        description = "Verifies imported Contract, Runtime, and SDK product evidence without running product tasks."
        dependsOn(invalidate)
        contractEvidenceDirectory.set(layout.dir(
            providers.gradleProperty(REPOSITORY_CONTRACT_EVIDENCE_DIRECTORY_PROPERTY).map(::file),
        ))
        runtimeEvidenceDirectory.set(layout.dir(
            providers.gradleProperty(REPOSITORY_RUNTIME_EVIDENCE_DIRECTORY_PROPERTY).map(::file),
        ))
        sdkEvidenceDirectory.set(layout.dir(
            providers.gradleProperty(REPOSITORY_SDK_EVIDENCE_DIRECTORY_PROPERTY).map(::file),
        ))
        productModulesDirectory.set(layout.projectDirectory.dir("ci/products"))
        this.contractVersion.set(contractVersion)
        this.runtimeVersion.set(runtimeVersion)
        this.sdkVersion.set(sdkVersion)
        trustDomain.set(providers.gradleProperty(REPOSITORY_TRUST_DOMAIN_PROPERTY))
        resultFile.set(result)
    }
    tasks.register("verifyIosRuntime") {
        group = "verification"
        description = "Runs portable iOS runtime and Apple binding verification; distributed CI owns complete M8 parity."
        dependsOn(":codex-agent-runtime-ios:verifyIosRuntime")
    }
}
