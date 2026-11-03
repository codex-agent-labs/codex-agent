import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PromotedMavenOwnershipTest {
    @Test
    fun `matching duplicate primaries are accepted and only owner bytes are forwarded`() = withFixture { fixture ->
        val owners = canonicalPromotedMavenOwners()
        val expectedPrimaryPaths = expectedMavenPrimaryPaths(VERSIONS)
        assertEquals(EXPECTED_OWNERS, owners)
        assertEquals(38, owners.size)
        assertEquals(220, expectedPrimaryPaths.size)
        assertEquals(EXPECTED_OWNERS.keys, expectedPrimaryPaths.mapTo(sortedSetOf()) { it.substringBefore('/') })
        assertEquals("common", owners.getValue("codex-agent"))
        assertEquals("common", owners.getValue("codex-agent-jvm"))
        assertEquals("common", owners.getValue("codex-agent-core"))
        assertEquals("common", owners.getValue("codex-agent-core-jvm"))
        assertEquals("common", owners.getValue("codex-agent-bom"))
        assertEquals("android", owners.getValue("codex-agent-core-android"))
        assertEquals("desktop", owners.getValue("codex-agent-core-macosarm64"))
        assertEquals("ios-device", owners.getValue("codex-agent-runtime-ios"))
        assertEquals("desktop", owners.getValue("codex-agent-runtime-desktop"))
        assertEquals("node-js", owners.getValue("codex-agent-runtime-desktop-js"))
        assertEquals("node-wasm", owners.getValue("codex-agent-runtime-desktop-wasm-js"))

        val sharedPaths = listOf(
            "$GROUP_PATH/codex-agent/${VERSIONS.sdk}/codex-agent-${VERSIONS.sdk}.jar",
            "$GROUP_PATH/codex-agent-core/${VERSIONS.contract}/codex-agent-core-${VERSIONS.contract}.jar",
        )
        sharedPaths.forEach { sharedPath ->
            fixture.repositories.getValue("common").resolve(sharedPath).copyTo(
                fixture.repositories.getValue("android").resolve(sharedPath).apply { parentFile.mkdirs() },
            )
        }
        stageCanonicalPromotedMavenPrimaries(fixture.promoted, COMMIT, VERSIONS, fixture.output)

        sharedPaths.forEach { sharedPath ->
            assertEquals("common:$sharedPath", fixture.output.resolve(sharedPath).readText())
        }
        val expected = expectedPrimaryPaths.mapTo(sortedSetOf()) { "$GROUP_PATH/$it" }
        assertEquals(
            expected,
            fixture.output.walkTopDown().filter(File::isFile)
                .mapTo(sortedSetOf()) { it.relativeTo(fixture.output).invariantSeparatorsPath },
        )
    }

    @Test
    fun `duplicate canonical ownership is rejected instead of comparing output bytes`() {
        val conflicting = promotedMavenArtifactOwnership.mapValuesTo(linkedMapOf()) { it.value.toSet() }
        conflicting["android"] = conflicting.getValue("android") + "codex-agent"
        val failure = assertFailsWith<IllegalStateException> { canonicalPromotedMavenOwners(conflicting) }
        assertTrue(failure.message.orEmpty().contains("Duplicate canonical Maven ownership"))
    }

    @Test
    fun `divergent ordinary and classifier duplicate primaries are rejected before staging`() {
        listOf(
            "android" to "$GROUP_PATH/codex-agent/${VERSIONS.sdk}/codex-agent-${VERSIONS.sdk}.module",
            "android" to "$GROUP_PATH/codex-agent-core/${VERSIONS.contract}/" +
                "codex-agent-core-${VERSIONS.contract}.module",
            "node-js" to "$GROUP_PATH/codex-agent-runtime-desktop/${VERSIONS.runtime}/" +
                "codex-agent-runtime-desktop-${VERSIONS.runtime}-app-server-linux-x64.zip",
        ).forEach { (target, relative) -> withFixture { fixture ->
            fixture.repositories.getValue(target).resolve(relative).apply {
                parentFile.mkdirs()
                writeText("divergent $target primary")
            }
            val failure = assertFailsWith<IllegalStateException> {
                stageCanonicalPromotedMavenPrimaries(fixture.promoted, COMMIT, VERSIONS, fixture.output)
            }
            assertTrue(failure.message.orEmpty().contains(relative))
            assertFalse(fixture.output.exists())
        } }
    }

    @Test
    fun `primary under another product version is rejected before staging`() {
        listOf(
            Triple("codex-agent-core", VERSIONS.contract, VERSIONS.sdk),
            Triple("codex-agent-runtime-desktop", VERSIONS.runtime, VERSIONS.sdk),
            Triple("codex-agent-runtime-android", VERSIONS.sdk, VERSIONS.runtime),
        ).forEach { (artifactId, expectedVersion, wrongVersion) -> withFixture { fixture ->
            val owner = EXPECTED_OWNERS.getValue(artifactId)
            val expectedPath = "$GROUP_PATH/$artifactId/$expectedVersion/$artifactId-$expectedVersion.pom"
            val wrongPath = "$GROUP_PATH/$artifactId/$wrongVersion/$artifactId-$wrongVersion.pom"
            val expected = fixture.repositories.getValue(owner).resolve(expectedPath)
            expected.copyTo(
                fixture.repositories.getValue(owner).resolve(wrongPath).apply { parentFile.mkdirs() },
            )

            assertFailsWith<IllegalStateException> {
                stageCanonicalPromotedMavenPrimaries(fixture.promoted, COMMIT, VERSIONS, fixture.output)
            }
            assertFalse(fixture.output.exists())
        } }

        withFixture { fixture ->
            val artifactId = "codex-agent-core"
            val wrongPath = "$GROUP_PATH/$artifactId/${VERSIONS.sdk}/$artifactId-${VERSIONS.sdk}.pom"
            fixture.repositories.getValue("android").resolve(wrongPath).apply {
                parentFile.mkdirs()
                writeText("android:$wrongPath")
            }

            assertFailsWith<IllegalStateException> {
                stageCanonicalPromotedMavenPrimaries(fixture.promoted, COMMIT, VERSIONS, fixture.output)
            }
            assertFalse(fixture.output.exists())
        }
    }

    @Test
    fun `candidate uses packaged parity verification before signing without shell comparison`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve(".github/workflows/release-candidate.yml").isFile }
        val workflow = repository.resolve(".github/workflows/release-candidate.yml").readText()
        assertTrue("java -jar \"${'$'}RELEASE_TOOL\" stage-promoted-maven" in workflow)
        assertTrue(workflow.indexOf("stage-promoted-maven") < workflow.indexOf("gpg --batch --import"))
        assertFalse(Regex("(?m)\\bcmp(?:\\s|$)").containsMatchIn(workflow))
    }

    private fun withFixture(block: (Fixture) -> Unit) {
        val root = createTempDirectory("promoted-maven-ownership").toFile()
        try { block(Fixture(root)) } finally { root.deleteRecursively() }
    }

    private class Fixture(root: File) {
        val promoted = root.resolve("promoted")
        val output = root.resolve("canonical")
        val repositories = EXPECTED_OWNERS.values.toSortedSet().associateWith { target ->
            promoted.resolve("codex-agent-promoted-consumer-$target-$COMMIT/payload/maven").apply { mkdirs() }
        }

        init {
            expectedMavenPrimaryPaths(VERSIONS).forEach { relative ->
                val artifactId = relative.substringBefore('/')
                val owner = EXPECTED_OWNERS.getValue(artifactId)
                val path = "$GROUP_PATH/$relative"
                repositories.getValue(owner).resolve(path).apply {
                    parentFile.mkdirs()
                    writeText("$owner:$path")
                }
            }
            repositories.values.forEach { repository ->
                repository.resolve("$GROUP_PATH/maven-metadata.xml").apply {
                    parentFile.mkdirs()
                    writeText("verification-only metadata")
                }
            }
        }
    }

    companion object {
        private val VERSIONS = ProductVersions(contract = "1.2.3", runtime = "2.3.4", sdk = "3.4.5")
        private const val COMMIT = "0123456789abcdef0123456789abcdef01234567"
        private val GROUP_PATH = CodexAgentBuild.MAVEN_GROUP.replace('.', '/')
        private val EXPECTED_OWNERS = mapOf(
            "codex-agent" to "common",
            "codex-agent-jvm" to "common",
            "codex-agent-core" to "common",
            "codex-agent-core-jvm" to "common",
            "codex-agent-bom" to "common",
            "codex-agent-android" to "android",
            "codex-agent-core-android" to "android",
            "codex-agent-runtime-android" to "android",
            "codex-agent-linuxarm64" to "desktop",
            "codex-agent-linuxx64" to "desktop",
            "codex-agent-macosarm64" to "desktop",
            "codex-agent-macosx64" to "desktop",
            "codex-agent-mingwx64" to "desktop",
            "codex-agent-core-linuxarm64" to "desktop",
            "codex-agent-core-linuxx64" to "desktop",
            "codex-agent-core-macosarm64" to "desktop",
            "codex-agent-core-macosx64" to "desktop",
            "codex-agent-core-mingwx64" to "desktop",
            "codex-agent-runtime-desktop" to "desktop",
            "codex-agent-runtime-desktop-jvm" to "desktop",
            "codex-agent-runtime-desktop-linuxarm64" to "desktop",
            "codex-agent-runtime-desktop-linuxx64" to "desktop",
            "codex-agent-runtime-desktop-macosarm64" to "desktop",
            "codex-agent-runtime-desktop-macosx64" to "desktop",
            "codex-agent-runtime-desktop-mingwx64" to "desktop",
            "codex-agent-iosarm64" to "ios-device",
            "codex-agent-core-iosarm64" to "ios-device",
            "codex-agent-runtime-ios" to "ios-device",
            "codex-agent-runtime-ios-iosarm64" to "ios-device",
            "codex-agent-iossimulatorarm64" to "ios-simulator",
            "codex-agent-core-iossimulatorarm64" to "ios-simulator",
            "codex-agent-runtime-ios-iossimulatorarm64" to "ios-simulator",
            "codex-agent-js" to "node-js",
            "codex-agent-core-js" to "node-js",
            "codex-agent-runtime-desktop-js" to "node-js",
            "codex-agent-wasm-js" to "node-wasm",
            "codex-agent-core-wasm-js" to "node-wasm",
            "codex-agent-runtime-desktop-wasm-js" to "node-wasm",
        )
    }
}
