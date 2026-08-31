import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

class ProductPublicationVersionFunctionalTest {
    @Test
    fun `unequal product authorities drive actual publication paths and dependencies`() {
        val root = createTempDirectory("product-publication-versions").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText(
                """
                rootProject.name = "product-version-fixture"
                include(
                    ":codex-agent-core",
                    ":codex-agent-runtime-desktop",
                    ":codex-agent-runtime-android",
                    ":codex-agent-runtime-ios",
                    ":tooling",
                )
                include(":tooling:protocol-generator")
                """.trimIndent() + "\n",
            )
            root.resolve("build.gradle.kts").writeText("plugins { id(\"codexagent.root-release\") }\n")
            writeVersions(root, "1.2.3", "2.3.4", "3.4.5")
            modules.forEach { (project, artifact) ->
                val directory = root.resolve(project.removePrefix(":"))
                directory.mkdirs()
                val dependency = if (project == ":codex-agent-core") "" else
                    "dependencies { api(project(\":codex-agent-core\")) }"
                directory.resolve("build.gradle.kts").writeText(
                    """
                    plugins { `java-library`; `maven-publish` }
                    $dependency
                    publishing {
                        publications {
                            create<MavenPublication>("maven") {
                                from(components["java"])
                                artifactId = "$artifact"
                            }
                        }
                        repositories.maven {
                            name = "FIXTURE"
                            url = rootProject.layout.buildDirectory.dir("fixture-maven").get().asFile.toURI()
                        }
                    }
                    """.trimIndent() + "\n",
                )
            }
            root.resolve("tooling/protocol-generator").mkdirs()

            val first = run(root)
            assertTrue("Configuration cache entry stored" in first)
            assertVersions(root, "1.2.3", "2.3.4", "3.4.5")
            assertDependencies(root, "1.2.3", "2.3.4", "3.4.5")
            val second = run(root)
            assertTrue("Reusing configuration cache" in second)

            writeVersions(root, "1.2.4", "2.3.4", "3.4.5")
            run(root)
            assertVersions(root, "1.2.4", "2.3.4", "3.4.5")
            assertDependencies(root, "1.2.4", "2.3.4", "3.4.5")

            writeVersions(root, "1.2.4", "2.3.5", "3.4.5")
            run(root)
            assertVersions(root, "1.2.4", "2.3.5", "3.4.5")

            writeVersions(root, "1.2.4", "2.3.5", "3.4.6")
            run(root)
            assertVersions(root, "1.2.4", "2.3.5", "3.4.6")
        } finally {
            root.deleteRecursively()
        }
    }

    private fun run(root: File): String = GradleRunner.create()
        .withProjectDir(root)
        .withPluginClasspath()
        .withArguments(
            modules.keys.map { "$it:publishMavenPublicationToFIXTURERepository" } + listOf(
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            ),
        )
        .build()
        .output

    private fun assertVersions(root: File, contract: String, runtime: String, sdk: String) {
        val versions = mapOf(
            "codex-agent" to contract,
            "codex-agent-runtime-desktop" to runtime,
            "codex-agent-runtime-android" to sdk,
            "codex-agent-runtime-ios" to sdk,
        )
        versions.forEach { (artifact, version) ->
            val path = maven(root).resolve("$artifact/$version/$artifact-$version.pom")
            assertTrue(path.isFile, path.path)
            assertTrue("<version>$version</version>" in path.readText(), path.path)
        }
        assertEquals(setOf("1.2.3", contract), versionDirectories(root, "codex-agent"))
        assertEquals(setOf("2.3.4", runtime), versionDirectories(root, "codex-agent-runtime-desktop"))
        assertEquals(setOf("3.4.5", sdk), versionDirectories(root, "codex-agent-runtime-android"))
        assertEquals(setOf("3.4.5", sdk), versionDirectories(root, "codex-agent-runtime-ios"))
    }

    private fun assertDependencies(root: File, contract: String, runtime: String, sdk: String) {
        mapOf(
            "codex-agent-runtime-desktop" to runtime,
            "codex-agent-runtime-android" to sdk,
            "codex-agent-runtime-ios" to sdk,
        ).forEach { (artifact, version) ->
            val pom = maven(root).resolve("$artifact/$version/$artifact-$version.pom").readText()
            assertTrue("<artifactId>codex-agent</artifactId>" in pom, artifact)
            assertTrue("<version>$contract</version>" in pom, artifact)
        }
    }

    private fun versionDirectories(root: File, artifact: String): Set<String> =
        maven(root).resolve(artifact).listFiles().orEmpty().filter(File::isDirectory).map(File::getName).toSet()

    private fun maven(root: File): File =
        root.resolve("build/fixture-maven/${CodexAgentBuild.MAVEN_GROUP.replace('.', '/')}")

    private fun writeVersions(root: File, contract: String, runtime: String, sdk: String) {
        val directory = root.resolve("gradle/release/versions").apply { mkdirs() }
        mapOf("contract.txt" to contract, "runtime.txt" to runtime, "sdk.txt" to sdk).forEach { (name, value) ->
            directory.resolve(name).writeText("$value\n")
        }
    }

    private companion object {
        val modules = linkedMapOf(
            ":codex-agent-core" to "codex-agent",
            ":codex-agent-runtime-desktop" to "codex-agent-runtime-desktop",
            ":codex-agent-runtime-android" to "codex-agent-runtime-android",
            ":codex-agent-runtime-ios" to "codex-agent-runtime-ios",
        )
    }
}
