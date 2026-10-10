import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFails
import kotlin.test.assertTrue
import org.gradle.api.Project
import org.gradle.api.tasks.TaskProvider
import org.gradle.testfixtures.ProjectBuilder

/** Registration guard only; this is not Apple framework evidence. */
class IosImportedFrameworkPairRegistrationTest {
    @Test
    fun `device and simulator framework imports are all or neither`() {
        listOf(true to false, false to true).forEach { (device, simulator) ->
            fixture(device, simulator) { project, distribution, imported ->
                assertEquals(1, imported.size)
                imported.single().get()
                val failure = assertFails {
                    val prepare = distribution.prepareCodexAgentReleaseXCFramework.get()
                    prepare.taskDependencies.getDependencies(prepare)
                }
                assertTrue(
                    generateSequence(failure) { it.cause }.any {
                        it.message == "Imported Apple device and simulator frameworks must be supplied together"
                    },
                )
                assertTrue(project.tasks.findByName("assembleCodexAgentReleaseXCFrameworkFromImports") == null)
            }
        }
        fixture(false, false) { _, distribution, _ ->
            assertEquals(
                setOf("assembleCodexAgentReleaseXCFramework"),
                directDependencies(distribution),
            )
        }
        fixture(true, true) { _, distribution, _ ->
            assertEquals(
                setOf("assembleCodexAgentReleaseXCFrameworkFromImports"),
                directDependencies(distribution),
            )
        }
    }

    private fun directDependencies(distribution: IosAppleDistributionTasks): Set<String> {
        val prepare = distribution.prepareCodexAgentReleaseXCFramework.get()
        return prepare.taskDependencies.getDependencies(prepare).map { it.name }.toSet()
    }

    private fun fixture(
        device: Boolean,
        simulator: Boolean,
        block: (Project, IosAppleDistributionTasks, List<TaskProvider<ImportCodexAgentFrameworkTask>>) -> Unit,
    ) {
        val root = createTempDirectory("ios-framework-pair-").toFile().canonicalFile
        try {
            val project = ProjectBuilder.builder().withProjectDir(root).build()
            project.tasks.register("assembleCodexAgentReleaseXCFramework")
            val imports = listOfNotNull(
                if (device) project.tasks.register(
                    "importFixtureDeviceFramework", ImportCodexAgentFrameworkTask::class.java,
                ) else null,
                if (simulator) project.tasks.register(
                    "importFixtureSimulatorFramework", ImportCodexAgentFrameworkTask::class.java,
                ) else null,
            )
            val distribution = project.registerIosAppleDistributionTasks(
                emptyList(), "fixture", project.providers.provider { "fixture-toolchain" },
                imports.singleOrNull { it.name.contains("Device") },
                imports.singleOrNull { it.name.contains("Simulator") },
            )
            block(project, distribution, imports)
        } finally {
            root.deleteRecursively()
        }
    }
}
