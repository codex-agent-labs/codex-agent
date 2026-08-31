import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import org.gradle.testfixtures.ProjectBuilder

class ProductVersionOwnershipTest {
    @Test
    fun `each version file changes only its owning projects`() {
        val repository = createTempDirectory("product-versions").toFile()
        try {
            writeVersions(repository, ProductVersions("1.2.3", "2.3.4", "3.4.5"))
            val baseline = configuredVersions(repository)
            assertEquals(
                mapOf(
                    ":" to "3.4.5",
                    ":codex-agent-core" to "1.2.3",
                    ":codex-agent-runtime-desktop" to "2.3.4",
                    ":codex-agent-runtime-android" to "3.4.5",
                    ":codex-agent-runtime-ios" to "3.4.5",
                    ":tooling" to "unspecified",
                    ":tooling:protocol-generator" to "unspecified",
                ),
                baseline,
            )

            listOf(
                Triple("contract.txt", "1.2.4", setOf(":codex-agent-core")),
                Triple("runtime.txt", "2.3.5", setOf(":codex-agent-runtime-desktop")),
                Triple(
                    "sdk.txt",
                    "3.4.6",
                    setOf(":", ":codex-agent-runtime-android", ":codex-agent-runtime-ios"),
                ),
            ).forEach { (fileName, version, expectedChanged) ->
                writeVersions(repository, ProductVersions("1.2.3", "2.3.4", "3.4.5"))
                repository.resolve("gradle/release/versions/$fileName").writeText("$version\n")
                val changed = configuredVersions(repository).filter { (path, value) -> baseline[path] != value }.keys
                assertEquals(expectedChanged, changed, fileName)
            }
        } finally {
            repository.deleteRecursively()
        }
    }

    @Test
    fun `root publishes the exact three version identities`() {
        val root = projectGraph()
        val versions = ProductVersions("1.0.0", "2.0.0", "3.0.0")
        applyProductVersions(root, versions)
        val identities = root.extensions.extraProperties
        assertEquals(versions.contract, identities.get("codexAgent.contractVersion"))
        assertEquals(versions.runtime, identities.get("codexAgent.runtimeVersion"))
        assertEquals(versions.sdk, identities.get("codexAgent.sdkVersion"))
    }

    private fun configuredVersions(repository: File): Map<String, String> {
        val root = projectGraph()
        applyProductVersions(root, readProductVersions(repository))
        return root.allprojects.associate { it.path to it.version.toString() }.toSortedMap()
    }

    private fun projectGraph() = ProjectBuilder.builder().withName("codex-agent").build().also { root ->
        listOf(
            "codex-agent-core",
            "codex-agent-runtime-android",
            "codex-agent-runtime-desktop",
            "codex-agent-runtime-ios",
            "tooling",
        ).forEach { name -> ProjectBuilder.builder().withName(name).withParent(root).build() }
        ProjectBuilder.builder().withName("protocol-generator").withParent(root.project(":tooling")).build()
    }

    private fun writeVersions(repository: File, versions: ProductVersions) {
        repository.resolve("gradle/release/versions").mkdirs()
        mapOf(
            "contract.txt" to versions.contract,
            "runtime.txt" to versions.runtime,
            "sdk.txt" to versions.sdk,
        ).forEach { (name, version) ->
            repository.resolve("gradle/release/versions/$name").writeText("$version\n")
        }
    }
}
