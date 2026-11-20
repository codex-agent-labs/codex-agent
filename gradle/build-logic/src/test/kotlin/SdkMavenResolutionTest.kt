import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class SdkMavenResolutionTest {
    @Test
    fun `finalized SDK repository resolves an exact version without discovery metadata`() {
        // Resolution-only fixture: placeholder payloads are not product artifact evidence.
        val root = createTempDirectory("sdk-maven-resolution").toFile()
        try {
            val repository = root.resolve("repository")
            writeRepository(repository)
            finalizeFreshSdkBinaryMavenRepository(repository, GROUP, VERSION, COMPONENT)
            verifySdkBinaryMavenRepository(
                repository, GROUP, VERSION, COMPONENT, root.resolve("inventory.json"),
            )
            assertTrue(repository.walkTopDown().none { it.name.startsWith("maven-metadata.xml") })

            val consumer = root.resolve("consumer").apply { mkdir() }
            consumer.resolve("settings.gradle").writeText("rootProject.name = 'sdk-resolution-fixture'\n")
            consumer.resolve("build.gradle").writeText(
                """
                repositories { maven { url = uri('${repository.toURI()}') } }
                configurations { sdk }
                dependencies { add('sdk', '$GROUP:$ROOT_ARTIFACT:$VERSION') }
                tasks.register('resolveSdk') {
                    doLast {
                        def actual = configurations.sdk.resolve()*.name.toSorted()
                        def expected = [
                            '$ROOT_ARTIFACT-$VERSION.jar',
                            '${LEAF_ARTIFACTS[0]}-$VERSION.klib',
                            '${LEAF_ARTIFACTS[1]}-$VERSION.klib',
                        ].toSorted()
                        if (actual != expected) throw new GradleException("unexpected fixture closure: ${'$'}actual")
                        def coordinates = configurations.sdk.incoming.resolutionResult.allComponents
                            .findAll { it.id instanceof org.gradle.api.artifacts.component.ModuleComponentIdentifier }
                            .collect { it.moduleVersion?.toString() }.findAll { it != null }.toSorted()
                        def expectedCoordinates = [
                            '$GROUP:$ROOT_ARTIFACT:$VERSION',
                            '$GROUP:${LEAF_ARTIFACTS[0]}:$VERSION',
                            '$GROUP:${LEAF_ARTIFACTS[1]}:$VERSION',
                        ].toSorted()
                        if (coordinates != expectedCoordinates) {
                            throw new GradleException("unexpected fixture coordinates: ${'$'}coordinates")
                        }
                        println('exact-version SDK fixture resolved without discovery metadata')
                    }
                }
                """.trimIndent(),
            )

            val result = GradleRunner.create()
                .withProjectDir(consumer)
                .withTestKitDir(root.resolve("test-kit"))
                .withArguments("resolveSdk", "--offline", "--stacktrace", "--console=plain")
                .build()
            assertTrue("exact-version SDK fixture resolved without discovery metadata" in result.output)
        } finally {
            root.deleteRecursively()
        }
    }

    private fun writeRepository(repository: File) {
        val group = repository.resolve(GROUP.replace('.', '/'))
        expectedSdkBinaryMavenPrimaryPaths(COMPONENT, VERSION).forEach { relative ->
            val artifactId = relative.substringBefore('/')
            val primary = group.resolve(relative).apply { parentFile.mkdirs() }
            primary.writeText(when {
                relative.endsWith(".pom") -> pom(artifactId)
                relative.endsWith(".module") -> module(artifactId)
                else -> "fixture-only:$relative\n"
            })
        }
        expectedSdkBinaryMavenPrimaryPaths(COMPONENT, VERSION).forEach { relative ->
            val primary = group.resolve(relative)
            checksumAlgorithms.forEach { (suffix, algorithm) ->
                primary.resolveSibling(primary.name + suffix).writeText(primary.releaseDigest(algorithm))
            }
        }
        (listOf(ROOT_ARTIFACT) + LEAF_ARTIFACTS).forEach { artifactId ->
            val metadata = group.resolve("$artifactId/maven-metadata.xml")
            metadata.writeText(
                "<metadata><groupId>$GROUP</groupId><artifactId>$artifactId</artifactId>" +
                    "<versioning><latest>$VERSION</latest><release>$VERSION</release>" +
                    "<versions><version>$VERSION</version></versions>" +
                    "<lastUpdated>20260905000000</lastUpdated></versioning></metadata>\n",
            )
            checksumAlgorithms.forEach { (suffix, algorithm) ->
                metadata.resolveSibling(metadata.name + suffix).writeText(metadata.releaseDigest(algorithm))
            }
        }
    }

    private fun pom(artifactId: String): String {
        val dependencies = if (artifactId == ROOT_ARTIFACT) LEAF_ARTIFACTS.joinToString("") {
            "<dependency><groupId>$GROUP</groupId><artifactId>$it</artifactId>" +
                "<version>$VERSION</version><type>klib</type></dependency>"
        } else ""
        return """
            <?xml version="1.0" encoding="UTF-8"?>
            <project xmlns="http://maven.apache.org/POM/4.0.0">
              <modelVersion>4.0.0</modelVersion><groupId>$GROUP</groupId>
              <artifactId>$artifactId</artifactId><version>$VERSION</version>
              <packaging>${if (artifactId == ROOT_ARTIFACT) "jar" else "klib"}</packaging>
              <licenses><license><name>GNU General Public License v3.0 or later</name>
                <url>https://www.gnu.org/licenses/gpl-3.0.txt</url><distribution>repo</distribution>
              </license></licenses><dependencies>$dependencies</dependencies>
            </project>
            <!-- do_not_remove: published-with-gradle-metadata -->
        """.trimIndent() + "\n"
    }

    private fun module(artifactId: String): String {
        val artifact = "$artifactId-$VERSION.${if (artifactId == ROOT_ARTIFACT) "jar" else "klib"}"
        val dependencies = if (artifactId == ROOT_ARTIFACT) LEAF_ARTIFACTS.joinToString(",") {
            "{\"group\":\"$GROUP\",\"module\":\"$it\",\"version\":{\"requires\":\"$VERSION\"}}"
        } else ""
        return """{"formatVersion":"1.1","component":{"group":"$GROUP","module":"$artifactId","version":"$VERSION"},"createdBy":{"gradle":{"version":"8.0"}},"variants":[{"name":"runtime","attributes":{"org.gradle.category":"library","org.gradle.usage":"java-runtime"},"dependencies":[$dependencies],"files":[{"name":"$artifact","url":"$artifact"}]}]}""" + "\n"
    }

    private companion object {
        const val GROUP = "io.github.codex-agent-labs"
        const val VERSION = "3.4.5"
        const val COMPONENT = "sdk-ios"
        const val ROOT_ARTIFACT = "codex-agent-runtime-ios"
        val LEAF_ARTIFACTS = listOf(
            "codex-agent-runtime-ios-iosarm64",
            "codex-agent-runtime-ios-iossimulatorarm64",
        )
    }
}
