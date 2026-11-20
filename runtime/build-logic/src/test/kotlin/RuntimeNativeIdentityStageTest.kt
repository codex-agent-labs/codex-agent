import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner

/** Checks the real copy/input declaration, not native compilation or host acceptance. */
class RuntimeNativeIdentityStageTest {
    private val source = File("src/main/kotlin/codexagent.desktop-runtime.gradle.kts").readText()
    private val settings = File("../settings.gradle.kts").readText()
    private val nativeStage = source.substringAfter("val runtimeNativeBinaryManifestTasks =")
        .substringBefore("val importedBinarySnapshotRoot =")
    private val identityCopy = "val runtimeBinaryIdentity =" + nativeStage
        .substringAfter("val runtimeBinaryIdentity =")
        .substringBefore("from(layout.buildDirectory.dir(\"classes/kotlin/")
    private val targets = listOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")

    private fun fixture(root: File) {
        check(identityCopy.contains("inputs.file(runtimeBinaryIdentity)"))
        check(identityCopy.contains("from(runtimeBinaryIdentity) { into(\"identity\") }"))
        check(!identityCopy.contains("generate"))
        root.resolve("settings.gradle.kts").writeText("rootProject.name = \"native-identity-stage\"\n")
        root.resolve("other.bin").writeBytes(byteArrayOf(1, 2, 3))
        root.resolve("build.gradle.kts").writeText(
            """
            import java.io.File
            import org.gradle.api.tasks.PathSensitivity
            import org.gradle.api.tasks.Sync
            plugins { base }
            val verifiedContractDirectory = layout.dir(providers.gradleProperty("verifiedContractDirectory").map(::File))
            listOf(${targets.joinToString(", ") { "\"$it\"" }}).forEach { target ->
                tasks.register<Sync>("stage-" + target) {
                    into(layout.buildDirectory.dir("product-stage/runtime/" + target + "/binary/outputs"))
                    $identityCopy
                    // Keep a real source present to exercise required identity
                    // input validation instead of Gradle's empty-source shortcut.
                    from(layout.projectDirectory.file("other.bin")) { into("other") }
                }
            }
            """.trimIndent(),
        )
    }

    private fun runner(root: File, original: File) = GradleRunner.create().withProjectDir(root)
        .withArguments(targets.map { "stage-$it" } + listOf(
            "--offline", "--configuration-cache", "--configuration-cache-problems=fail",
            "-PverifiedContractDirectory=${original.absolutePath}",
        ))

    @Test
    fun `all native binary declarations retain one settings identity without regenerating it`() {
        assertTrue("desktopManifest.distributions.associate { distribution ->" in nativeStage)
        assertTrue("inputs.file(runtimeBinaryIdentity).withPropertyName(\"runtimeBinaryIdentity\")" in nativeStage)
        assertTrue("\"runtime-identity\" to \"outputs/identity\"" in nativeStage)
        assertEquals(1, Regex("from\\(runtimeBinaryIdentity\\)").findAll(nativeStage).count())
        assertTrue("verifiedContract.resolve(\"runtime-binary-identity.json\")" in settings)
        assertTrue("\"codexAgent.verifiedContractDirectory\",\n            verifiedContract.toFile()" in settings)
        assertFalse("runtime-binary-identity.json" in source.substringAfter("val importedBinarySnapshotRoot =")
            .substringBefore("val runtimeNativeBinaryManifestTasks ="))
    }

    @Test
    fun `copy preserves exact bytes across producer directory changes and requires original identity`() {
        val root = createTempDirectory("runtime-native-identity-stage-").toFile().canonicalFile
        try {
            fixture(root)
            // The fixture is explicitly not a valid Runtime identity envelope:
            // settings owns authentication; this test exercises copying only.
            val originalBytes = "{\"syntheticCopyFixture\":true}\n".toByteArray()
            val first = root.resolve("verified-original-run-a").apply { mkdir() }
            val second = root.resolve("verified-original-run-b").apply { mkdir() }
            listOf(first, second).forEach { directory ->
                directory.resolve("runtime-binary-identity.json").writeBytes(originalBytes)
            }
            for (directory in listOf(first, second)) {
                val result = runner(root, directory).build()
                assertTrue(result.tasks.none { "compile" in it.path || "link" in it.path || "generate" in it.path })
                targets.forEach { target ->
                    val copied = root.resolve("build/product-stage/runtime/$target/binary/outputs/identity")
                    assertEquals(listOf("runtime-binary-identity.json"), copied.listFiles()!!.map { it.name })
                    assertContentEquals(originalBytes, copied.resolve("runtime-binary-identity.json").readBytes())
                }
                assertContentEquals(originalBytes, directory.resolve("runtime-binary-identity.json").readBytes())
            }
            val missing = root.resolve("missing-original").apply { mkdir() }
            val failed = runner(root, missing).buildAndFail()
            assertTrue("runtimeBinaryIdentity" in failed.output)
            assertTrue("doesn't exist" in failed.output || "does not exist" in failed.output)
            assertTrue(failed.tasks.none { "compile" in it.path || "link" in it.path || "generate" in it.path })
            assertFalse(missing.resolve("runtime-binary-identity.json").exists())
            listOf(first, second).forEach { directory ->
                assertContentEquals(originalBytes, directory.resolve("runtime-binary-identity.json").readBytes())
            }
        } finally {
            root.deleteRecursively()
        }
    }
}
