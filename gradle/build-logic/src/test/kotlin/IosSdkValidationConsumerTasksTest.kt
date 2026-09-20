import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import org.gradle.api.Project
import org.gradle.api.tasks.Delete
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.bundling.Zip
import org.gradle.kotlin.dsl.register
import org.gradle.testfixtures.ProjectBuilder

/** Task-graph wiring only; these tests execute no compiler, XCTest, or Apple tooling. */
class IosSdkValidationConsumerTasksTest {
    @Test
    fun `rewires validation consumers to exact package and Contract snapshots`() = fixture().use { fixture ->
        fixture.configure()

        val packageRoot = fixture.packageInputs.get().workDirectory.get().asFile.resolve("package")
        val xcframework = fixture.packageInputs.get().workDirectory.get().asFile.resolve("xcframework")
        assertEquals(xcframework, fixture.compiler.get().xcframeworkDirectory.get().asFile)
        assertEquals(xcframework, fixture.binding.get().xcframeworkDirectory.get().asFile)
        assertEquals(packageRoot, fixture.distribution.verifyCodexAgentSwiftAuthenticationTests
            .get().packageDirectory.get().asFile)
        listOf(fixture.compiler.get(), fixture.binding.get()).forEach { task ->
            val canonicalApi = when (task) {
                is AppleCompilerEvidenceTask -> task.canonicalApiReport.get().asFile
                is GenerateAppleBindingEvidenceTask -> task.canonicalApiReport.get().asFile
                else -> error("unexpected task")
            }
            val canonicalCoverage = when (task) {
                is AppleCompilerEvidenceTask -> task.canonicalCoverageReceipt.get().asFile
                is GenerateAppleBindingEvidenceTask -> task.canonicalCoverageReceipt.get().asFile
                else -> error("unexpected task")
            }
            assertEquals(fixture.canonicalApi, canonicalApi)
            assertEquals(fixture.canonicalCoverage, canonicalCoverage)
        }
    }

    @Test
    fun `exact dependencies retain invalidation and toolchain without product compilation`() =
        fixture().use { fixture ->
            fixture.configure()

            assertEquals(
                setOf("invalidateAppleEvidence", "verifyAppleToolchain", "prepareValidationPackage", "verifyContract"),
                fixture.compiler.get().dependencyNames(),
            )
            assertEquals(
                setOf("invalidateAppleEvidence", "verifyAppleToolchain", "prepareValidationPackage"),
                fixture.distribution.verifyCodexAgentSwiftAuthenticationTests.get().dependencyNames(),
            )
            assertEquals(
                setOf("invalidateAppleEvidence", "compilerEvidence", "swiftTests", "verifyContract",
                    "prepareValidationPackage"),
                fixture.binding.get().dependencyNames(),
            )
            listOf(fixture.compiler.get(), fixture.distribution.verifyCodexAgentSwiftAuthenticationTests.get(),
                fixture.binding.get()).forEach { task ->
                assertFalse(task.dependencyNames().any { it in fixture.productTaskNames })
            }
        }

    @Test
    fun `rewiring preserves existing evidence outputs`() = fixture().use { fixture ->
        val outputs = fixture.evidenceOutputs()

        fixture.configure()

        assertEquals(outputs, fixture.evidenceOutputs())
    }
}

private class IosSdkValidationConsumerFixture : AutoCloseable {
    val root = kotlin.io.path.createTempDirectory("ios-sdk-validation-consumers").toFile().canonicalFile
    val project: Project = ProjectBuilder.builder().withProjectDir(root).build()
    val canonicalApi = root.resolve("contract/canonical-api.json")
    val canonicalCoverage = root.resolve("contract/canonical-coverage.json")
    val productTaskNames = setOf(
        "stageCodexAgentAppleDistribution", "assembleCodexAgentReleaseXCFramework",
        "linkReleaseFrameworkIosArm64", "compileKotlinIosArm64",
    )
    private val productTasks = productTaskNames.map { project.tasks.register(it) }
    private val invalidate = project.tasks.register<Delete>("invalidateAppleEvidence")
    private val toolchain = project.tasks.register<VerifyAppleToolchainTask>("verifyAppleToolchain")
    val packageInputs = project.tasks.register<PrepareAppleValidationPackageInputsTask>(
        "prepareValidationPackage",
    ) {
        workDirectory.set(root.resolve("prepared"))
    }
    private val contractVerify = project.tasks.register<VerifyImportedProductOutputManifestTask>("verifyContract")
    private val contract = IosImportedContractEvidenceTasks(
        contractVerify,
        project.layout.file(project.providers.provider { canonicalApi }),
        project.layout.file(project.providers.provider { canonicalCoverage }),
    )
    val compiler = project.tasks.register<AppleCompilerEvidenceTask>("compilerEvidence") {
        dependsOn(productTasks)
        evidenceFile.set(root.resolve("evidence/compiler.json"))
    }
    private val swiftTests = project.tasks.register<VerifySwiftAuthenticationTestsTask>("swiftTests") {
        dependsOn(productTasks)
        summaryFile.set(root.resolve("evidence/xctest.json"))
        resultBundleDirectory.set(root.resolve("evidence/tests.xcresult"))
    }
    val binding = project.tasks.register<GenerateAppleBindingEvidenceTask>("bindingEvidence") {
        dependsOn(productTasks)
        evidenceFile.set(root.resolve("evidence/binding.json"))
        swiftReceiptFile.set(root.resolve("evidence/swift.json"))
        objectiveCReceiptFile.set(root.resolve("evidence/objective-c.json"))
    }
    val distribution = IosAppleDistributionTasks(
        project.layout.dir(project.providers.provider { root.resolve("distribution") }),
        project.layout.dir(project.providers.provider { root.resolve("release-xcframework") }),
        project.layout.projectDirectory.file("PrivacyInfo.xcprivacy"),
        null,
        project.tasks.register<PrepareCodexAgentReleaseXCFrameworkTask>("prepareReleaseXCFramework"),
        project.tasks.register<Zip>("packageAppleDistribution"),
        project.tasks.register<Exec>("verifySwiftPackage"),
        swiftTests,
        project.tasks.register<VerifyIosLicensePackagingTask>("verifyIosLicensePackaging"),
    )

    fun configure() = project.configureIosSdkValidationConsumers(
        packageInputs, contract, toolchain, invalidate, distribution, compiler, binding,
    )

    fun evidenceOutputs() = mapOf(
        "compiler" to compiler.get().evidenceFile.get().asFile,
        "xctest" to swiftTests.get().summaryFile.get().asFile,
        "xcresult" to swiftTests.get().resultBundleDirectory.get().asFile,
        "binding" to binding.get().evidenceFile.get().asFile,
        "swift" to binding.get().swiftReceiptFile.get().asFile,
        "objective-c" to binding.get().objectiveCReceiptFile.get().asFile,
    )

    override fun close() {
        root.deleteRecursively()
    }
}

private fun org.gradle.api.Task.dependencyNames() = taskDependencies.getDependencies(this).map { it.name }.toSet()

private fun fixture() = IosSdkValidationConsumerFixture()
