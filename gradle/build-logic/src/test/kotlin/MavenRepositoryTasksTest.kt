import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class MavenRepositoryTasksTest {
    @Test
    fun `exact signed publication passes`() = withRepository { repository, inventory ->
        writeExactRepository(repository, signed = true)
        verifyMavenRepository(repository, GROUP, VERSIONS, true, inventory)
        val report = inventory.readReleaseObject()
        assertEquals(
            setOf(
                "schemaVersion",
                "groupId",
                "contractVersion",
                "runtimeVersion",
                "sdkVersion",
                "artifactIds",
                "primaryArtifactCount",
                "signaturesRequired",
                "files",
            ),
            report.keys,
        )
        assertEquals(4, report.releaseInt("schemaVersion"))
        assertEquals(GROUP, report.releaseString("groupId"))
        assertEquals(VERSIONS.contract, report.releaseString("contractVersion"))
        assertEquals(VERSIONS.runtime, report.releaseString("runtimeVersion"))
        assertEquals(VERSIONS.sdk, report.releaseString("sdkVersion"))
        assertEquals(220, report.releaseInt("primaryArtifactCount"))
        assertEquals(38, report.releaseArray("artifactIds").size)
        val primaryPaths = expectedMavenPrimaryPaths(VERSIONS)
        assertEquals(220, primaryPaths.size)
        assertEquals(65, primaryPaths.count { it.substringBefore('/').startsWith("codex-agent-core") })
        assertEquals(63, primaryPaths.count {
            it.substringBefore('/').startsWith("codex-agent-runtime-desktop")
        })
        assertEquals(92, primaryPaths.count {
            val artifactId = it.substringBefore('/')
            !artifactId.startsWith("codex-agent-core") &&
                !artifactId.startsWith("codex-agent-runtime-desktop")
        })
        assertTrue(primaryPaths.filter { it.substringBefore('/').startsWith("codex-agent-core") }
            .all { "/${VERSIONS.contract}/" in it })
        assertTrue(primaryPaths.filter { it.substringBefore('/').startsWith("codex-agent-runtime-desktop") }
            .all { "/${VERSIONS.runtime}/" in it })
        assertTrue(primaryPaths.filter {
            val artifactId = it.substringBefore('/')
            !artifactId.startsWith("codex-agent-core") &&
                !artifactId.startsWith("codex-agent-runtime-desktop")
        }.all { "/${VERSIONS.sdk}/" in it })
        assertEquals(
            setOf(
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-c-abi-linux-arm64.zip",
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-c-abi-linux-x64.zip",
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-c-abi-macos-arm64.zip",
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-c-abi-macos-x64.zip",
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-c-abi-windows-x64.zip",
            ),
            primaryPaths.filter { "-c-abi-" in it }.map { it.substringAfterLast('/') }.toSet(),
        )
        primaryPaths.forEach { relative ->
            val primary = repository.resolve("io/github/codex-agent-labs/$relative")
            assertEquals(primary.releaseDigest("MD5"), primary.resolveSibling(primary.name + ".md5").readText().trim())
            assertEquals(primary.releaseDigest("SHA-512"), primary.resolveSibling(primary.name + ".sha512").readText().trim())
        }
    }

    @Test
    fun `Gradle transport metadata is excluded from verification and inventory`() =
        withRepository { repository, inventory ->
            writeExactRepository(repository, signed = true)
            val coordinate = repository.resolve("io/github/codex-agent-labs/codex-agent")
            coordinate.resolve("maven-metadata.xml").writeText("<metadata/>")
            coordinate.resolve("maven-metadata.xml.sha256").writeText("0".repeat(64))
            val primary = coordinate.resolve("${VERSIONS.sdk}/codex-agent-${VERSIONS.sdk}.jar")
            primary.resolveSibling(primary.name + ".asc.sha256").writeText("0".repeat(64))

            verifyMavenRepository(repository, GROUP, VERSIONS, true, inventory)

            val inventoryText = inventory.readText()
            assertTrue(!inventoryText.contains("maven-metadata.xml"))
            assertTrue(!inventoryText.contains(".asc.sha256"))
        }

    @Test
    fun `missing module or target binary is rejected`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        val group = repository.resolve("io/github/codex-agent-labs")
        listOf(
            "codex-agent/${VERSIONS.sdk}/codex-agent-${VERSIONS.sdk}.module",
            "codex-agent-runtime-android/${VERSIONS.sdk}/" +
                "codex-agent-runtime-android-${VERSIONS.sdk}.aar",
            "codex-agent-core-jvm/${VERSIONS.contract}/codex-agent-core-jvm-${VERSIONS.contract}.jar",
            "codex-agent-bom/${VERSIONS.sdk}/codex-agent-bom-${VERSIONS.sdk}.pom",
            "codex-agent-bom/${VERSIONS.sdk}/codex-agent-bom-${VERSIONS.sdk}.module",
        ).forEach { relative ->
            val file = group.resolve(relative)
            val bytes = file.readBytes()
            file.delete()
            assertFailsWith<IllegalStateException> {
                verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
            }
            file.writeBytes(bytes)
        }
    }

    @Test
    fun `product primaries under the wrong owner version are rejected`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        val group = repository.resolve("io/github/codex-agent-labs")
        listOf(
            Triple("codex-agent-core", VERSIONS.contract, VERSIONS.sdk),
            Triple("codex-agent-runtime-desktop", VERSIONS.runtime, VERSIONS.sdk),
            Triple("codex-agent-bom", VERSIONS.sdk, VERSIONS.contract),
        ).forEach { (artifactId, correctVersion, wrongVersion) ->
            val fileName = "$artifactId-$correctVersion.pom"
            val correct = group.resolve("$artifactId/$correctVersion/$fileName")
            val bytes = correct.readBytes()
            val wrong = group.resolve("$artifactId/$wrongVersion/$artifactId-$wrongVersion.pom").apply {
                parentFile.mkdirs()
                writeBytes(bytes)
            }
            assertFailsWith<IllegalStateException> {
                verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
            }
            assertTrue(wrong.delete())
            assertTrue(wrong.parentFile.delete())
        }
    }

    @Test
    fun `unexpected coordinate or primary artifact is rejected`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        val group = repository.resolve("io/github/codex-agent-labs")
        group.resolve("unexpected/0.2.0/unexpected-0.2.0.jar").apply { parentFile.mkdirs(); writeText("x") }
        assertFailsWith<IllegalStateException> {
            verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
        }
    }

    @Test
    fun `arbitrary Maven sidecar is rejected`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        val primary = repository.resolve(
            "io/github/codex-agent-labs/${expectedMavenPrimaryPaths(VERSIONS).first()}",
        )
        primary.resolveSibling(primary.name + ".unexpected.sha256").writeText("0".repeat(64))
        assertFailsWith<IllegalStateException> {
            verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
        }
    }

    @Test
    fun `regular file outside the publication set is rejected`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        repository.resolve("outside.txt").apply { parentFile.mkdirs(); writeText("outside") }
        assertFailsWith<IllegalStateException> {
            verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
        }
    }

    @Test
    fun `every primary artifact requires a signature when enabled`() = withRepository { repository, inventory ->
        writeExactRepository(repository, signed = true)
        val primary = repository.resolve(
            "io/github/codex-agent-labs/${expectedMavenPrimaryPaths(VERSIONS).first()}",
        )
        primary.resolveSibling(primary.name + ".asc").delete()
        val failure = assertFailsWith<IllegalStateException> {
            verifyMavenRepository(repository, GROUP, VERSIONS, true, inventory)
        }
        assertTrue(failure.message.orEmpty().contains(".asc is missing"))
    }

    @Test
    fun `every POM requires exact GPL metadata`() = withRepository { repository, inventory ->
        writeExactRepository(repository)
        val pom = repository.resolve(
            "io/github/codex-agent-labs/codex-agent/${VERSIONS.sdk}/codex-agent-${VERSIONS.sdk}.pom",
        )
        pom.writeText(pom.readText().replace("distribution>repo", "distribution>manual"))
        val failure = assertFailsWith<IllegalStateException> {
            verifyMavenRepository(repository, GROUP, VERSIONS, false, inventory)
        }
        assertTrue(failure.message.orEmpty().contains("licence"))
    }

    private fun withRepository(block: (File, File) -> Unit) {
        val directory = createTempDirectory("maven-release").toFile()
        try { block(directory.resolve("repository"), directory.resolve("inventory.json")) } finally { directory.deleteRecursively() }
    }

    private fun writeExactRepository(repository: File, signed: Boolean = false) {
        val group = repository.resolve("io/github/codex-agent-labs")
        expectedMavenPrimaryPaths(VERSIONS).forEach { relative ->
            group.resolve(relative).apply {
                parentFile.mkdirs()
                writeText(if (extension == "pom") validPom else relative)
                if (signed) resolveSibling(name + ".asc").writeText("signature")
            }
        }
    }

    companion object {
        private const val GROUP = "io.github.codex-agent-labs"
        private val VERSIONS = ProductVersions(contract = "1.2.3", runtime = "2.3.4", sdk = "3.4.5")
        private const val validPom = """
            <project xmlns="http://maven.apache.org/POM/4.0.0"><licenses><license>
            <name>GNU General Public License v3.0 or later</name>
            <url>https://www.gnu.org/licenses/gpl-3.0.txt</url><distribution>repo</distribution>
            </license></licenses></project>
        """
    }
}
