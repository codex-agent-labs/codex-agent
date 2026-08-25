import java.io.File
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.jsonObject

class CentralBundleTasksTest {
    @Test
    fun `bundles keep complete iOS modules in deterministic portal-sized shards`() = withFixture { fixture ->
        val group = CodexAgentBuild.MAVEN_GROUP.replace('.', '/')
        val paths = listOf(
            "$group/codex-agent-client/0.2.0/client.pom",
            "$group/codex-agent-runtime-ios-iosarm64/0.2.0/device.klib",
            "$group/codex-agent-runtime-ios-iosarm64/0.2.0/device.pom",
            "$group/codex-agent-runtime-ios-iossimulatorarm64/0.2.0/simulator.klib",
            "$group/codex-agent-runtime-ios-iossimulatorarm64/0.2.0/simulator.pom",
        )
        paths.forEach { fixture.repository.resolve(it).write(it) }
        fixture.repository.resolve("maven-metadata.xml").write("metadata")

        val bundles = buildCentralBundles(
            fixture.repository, fixture.inventory, fixture.root.resolve("bundles"), "0.2.0",
            fixture.reportA, 1_000_000,
        )

        assertEquals(
            listOf(
                "codex-agent-0.2.0-central-main.zip",
                "codex-agent-0.2.0-central-ios-arm64.zip",
                "codex-agent-0.2.0-central-ios-simulator-arm64.zip",
            ),
            bundles.map(File::getName),
        )
        val expected = mapOf(
            CENTRAL_MAIN_SHARD to setOf(paths[0]),
            "ios-arm64" to setOf(paths[1], paths[2]),
            "ios-simulator-arm64" to setOf(paths[3], paths[4]),
        )
        bundles.forEach { bundle ->
            val shard = bundle.name.removePrefix("codex-agent-0.2.0-central-").removeSuffix(".zip")
            ZipFile(bundle).use { zip ->
                assertEquals(expected.getValue(shard), zip.entries().toList().filterNot { it.isDirectory }
                    .map { it.name }.toSet())
            }
        }
        val report = fixture.reportA.readReleaseObject()
        assertTrue(report.releaseBoolean("allBundlesBelowCentralPortalUploadLimit"))
        assertEquals(expected.keys, report.releaseArray("bundles").map {
            it.jsonObject.releaseString("shard")
        }.toSet())
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val directory = createTempDirectory("central-bundle").toFile()
        try { block(Fixture(directory)) } finally { directory.deleteRecursively() }
    }

    private data class Fixture(val root: File) {
        val repository = root.resolve("repository").apply { mkdirs() }
        val inventory = root.resolve("maven.json").apply { writeText("{}") }
        val reportA = root.resolve("a.json")
    }
}

private fun File.write(value: String) { parentFile.mkdirs(); writeText(value) }
private fun <T> java.util.Enumeration<T>.toList(): List<T> = buildList { while (hasMoreElements()) add(nextElement()) }
