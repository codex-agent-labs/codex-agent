import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.Task
import org.gradle.testfixtures.ProjectBuilder

/** Imported-package integrity graph only; no tasks execute and no source or host trust is established. */
class IosSdkValidationPackageTasksTest {
    private val targets = listOf("ios-arm64", "ios-simulator-arm64")

    @Test
    fun `both validation targets snapshot and verify the exact original package before extraction`() {
        targets.forEach { target -> fixture { project ->
            val before = project.tasks.names.toSet()
            val source = project.layout.projectDirectory.dir("original-package")
            val compatibility = project.layout.projectDirectory.file("current/sdk-compatibility.json")
            val tree = "a".repeat(40)
            val prepared = project.registerIosSdkValidationPackageInputs(
                project.providers.provider { source },
                project.providers.provider { "0.8.0" },
                project.providers.provider { compatibility },
                project.providers.provider { tree },
                target,
            ).get()
            val snapshot = project.tasks.named(
                "snapshotSdkIosValidationPackage", SnapshotImportedProductStageTask::class.java,
            ).get()
            val verify = project.tasks.named(
                "verifySdkIosValidationPackage", VerifyImportedProductOutputManifestTask::class.java,
            ).get()
            val root = project.layout.buildDirectory.dir("imported-sdk-validation/$tree/$target").get().asFile
            val stage = root.resolve("package-stage")
            assertEquals(source.asFile, snapshot.sourceDirectory.get().asFile)
            assertEquals(stage, snapshot.outputDirectory.get().asFile)
            assertEquals(stage, verify.stageRoot.get().asFile)
            assertEquals(listOf("sdk", "sdk-ios", "package", "ios", "0.8.0"), listOf(
                verify.product.get(), verify.component.get(), verify.phase.get(),
                verify.target.get(), verify.productVersion.get(),
            ))
            assertEquals(stage.resolve("outputs/apple"), prepared.productDirectory.get().asFile)
            assertEquals("0.8.0", prepared.sdkVersion.get())
            assertEquals(compatibility.asFile, prepared.sdkCompatibility.get().asFile)
            assertEquals(root.resolve("extracted"), prepared.workDirectory.get().asFile)
            assertEquals(emptySet(), snapshot.taskDependencies.getDependencies(snapshot))
            assertEquals(setOf(snapshot), verify.taskDependencies.getDependencies(verify))
            assertEquals(setOf(verify), prepared.taskDependencies.getDependencies(prepared))
            // Exact closure also excludes compiler, linker, Cargo and legacy evidence producers.
            assertEquals(setOf(snapshot, verify, prepared), closure(prepared))
            assertEquals(setOf("snapshotSdkIosValidationPackage", "verifySdkIosValidationPackage",
                "prepareSdkIosValidationPackage"), project.tasks.names.toSet() - before)
            assertFalse(root.toPath().startsWith(source.asFile.toPath()))
            assertFalse(source.asFile.exists())
            assertFalse(prepared.workDirectory.get().asFile.exists())
        } }
    }

    @Test
    fun `device and simulator own separate snapshot and extraction roots even under one build directory`() {
        val root = createTempDirectory("ios-validation-target-roots-").toFile().canonicalFile
        try {
            val build = root.resolve("shared-build")
            val tree = "b".repeat(64)
            val owned = targets.map { target ->
                val project = ProjectBuilder.builder().withName(target)
                    .withProjectDir(root.resolve(target).apply { mkdirs() }).build()
                project.layout.buildDirectory.set(build)
                val prepared = project.registerIosSdkValidationPackageInputs(
                    project.providers.provider { project.layout.projectDirectory.dir("original-package") },
                    project.providers.provider { "0.8.0" },
                    project.providers.provider { project.layout.projectDirectory.file("sdk-compatibility.json") },
                    project.providers.provider { tree }, target,
                ).get()
                val snapshot = project.tasks.named(
                    "snapshotSdkIosValidationPackage", SnapshotImportedProductStageTask::class.java,
                ).get()
                listOf(snapshot.outputDirectory.get().asFile, prepared.workDirectory.get().asFile)
            }.flatten()
            assertEquals(targets.flatMap { target ->
                listOf("package-stage", "extracted").map { build.resolve("imported-sdk-validation/$tree/$target/$it") }
            }, owned)
            owned.forEachIndexed { index, first -> owned.drop(index + 1).forEach { second ->
                assertFalse(first.toPath().startsWith(second.toPath()) || second.toPath().startsWith(first.toPath()))
            } }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `invalid target or missing and malformed identities reject before registering tasks`() {
        listOf("target", "source", "compatibility", "missing-version", "version", "missing-tree", "tree").forEach { invalid ->
            fixture { project ->
                val source = project.objects.directoryProperty()
                if (invalid != "source") source.set(project.layout.projectDirectory.dir("original-package"))
                val compatibility = project.objects.fileProperty()
                if (invalid != "compatibility") compatibility.set(project.layout.projectDirectory.file("sdk-compatibility.json"))
                val version = project.objects.property(String::class.java)
                if (invalid != "missing-version") version.set(if (invalid == "version") "not-semver" else "0.8.0")
                val tree = project.objects.property(String::class.java)
                if (invalid != "missing-tree") tree.set(if (invalid == "tree") "../../original-package" else "a".repeat(40))
                val before = project.tasks.names.toSet()
                val error = assertFailsWith<IllegalStateException>(invalid) {
                    project.registerIosSdkValidationPackageInputs(source, version, compatibility, tree,
                        if (invalid == "target") "ios" else "ios-arm64")
                }
                assertTrue("Imported Apple validation requires" in error.message.orEmpty(), invalid)
                assertEquals(before, project.tasks.names.toSet(), invalid)
            }
        }
    }

    private fun closure(task: Task): Set<Task> = setOf(task) +
        task.taskDependencies.getDependencies(task).flatMap(::closure)

    private fun fixture(block: (Project) -> Unit) {
        val root = createTempDirectory("ios-validation-package-inputs-").toFile().canonicalFile
        try {
            block(ProjectBuilder.builder().withProjectDir(root).build())
        } finally {
            root.deleteRecursively()
        }
    }
}
