import java.io.File
import java.nio.file.Files
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

class AppleReleaseCheckTasksTest {
    @Test
    fun `iOS preflight requires a positive 40 GiB disk budget`() {
        val gibibyte = 1024L * 1024L * 1024L
        assertEquals(40L * gibibyte, requireIosFreeDiskSpace(40L * gibibyte, 40))
        assertFailsWith<IllegalArgumentException> { requireIosFreeDiskSpace(40L * gibibyte, 0) }
        assertFailsWith<IllegalStateException> { requireIosFreeDiskSpace(39L * gibibyte, 40) }
    }

    @Test
    fun `toolchain output is checked without shell parsing`() {
        verifyAppleToolchainOutput(
            "Xcode 16.4\nBuild version 16F6\n",
            "Apple Swift version 6.1.2 effective-5.10\n",
            "16.4",
            "16F6",
            "6.1.2",
        )
        assertFailsWith<IllegalStateException> {
            verifyAppleToolchainOutput("Xcode 16.3", "Apple Swift version 6.1.2", "16.4", "16F6", "6.1.2")
        }
        listOf(
            "Apple Swift version 6.1.20 effective-5.10",
            "Apple Swift version 6.1.2beta effective-5.10",
            "Swift version 6.1.2",
            "Apple Swift version 6.1.2\nApple Swift version 6.1.3",
        ).forEach { swift ->
            assertFailsWith<IllegalStateException> {
                verifyAppleToolchainOutput(
                    "Xcode 16.4\nBuild version 16F6", swift, "16.4", "16F6", "6.1.2",
                )
            }
        }
        assertFailsWith<IllegalArgumentException> {
            verifyAppleToolchainOutput(
                "Xcode 16.4\nBuild version 16F6", "Apple Swift version 6.1.2", "16.4", "16F6", "6.1.2beta",
            )
        }
    }

    @Test
    fun `otool deployment records retain Rust sysroot exception`() {
        val records = parseDeploymentTargets(
            """
            archive(CodexAgent.framework.o):
                  cmd LC_BUILD_VERSION
             platform 2
                minos 15.0
            archive(std-abc.o):
                  cmd LC_BUILD_VERSION
             platform 2
                minos 14.0
            """.trimIndent(),
        )
        assertEquals(2, records.size)
        verifyDeploymentTargets(records, 2, "15.0")
        assertFailsWith<IllegalStateException> { verifyDeploymentTargets(records, 7, "15.0") }
    }

    @Test
    fun `artifact metrics use JDK recursive file aggregation and JSON budgets`() {
        val root = createTempDirectory("apple-metrics").toFile()
        try {
            val archive = root.resolve("archive.zip").apply { writeBytes(ByteArray(3)) }
            val device = root.resolve("CodexAgent").apply { writeBytes(ByteArray(5)) }
            val app = root.resolve("App.app").apply { mkdirs() }
            app.resolve("one").writeBytes(ByteArray(7))
            app.resolve("nested/two").apply { parentFile.mkdirs(); writeBytes(ByteArray(11)) }
            val policy = root.resolve("policy.json").apply { atomicWriteJson(buildJsonObject {
                put("artifactBytes", buildJsonObject {
                    put("compressedXcframeworkMaximum", JsonPrimitive(3))
                    put("deviceFrameworkMaximum", JsonPrimitive(5))
                    put("sampleAppInstallMaximum", JsonPrimitive(18))
                })
            }) }
            val metrics = measureAppleArtifacts(archive, device, app)
            assertEquals(AppleArtifactMetrics(3, 5, 18), metrics)
            verifyAppleArtifactBudgets(metrics, policy)
            policy.writeText(policy.readText().replace(": 18", ": 17"))
            assertFailsWith<IllegalStateException> { verifyAppleArtifactBudgets(metrics, policy) }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `live release tasks contain no compound shell implementation`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("gradle/build-logic/src/main/kotlin/IosAppleReleaseVerificationTasks.kt").isFile }
        val sources = linkedMapOf<String, String>()
        listOf(repository.resolve("gradle/build-logic/src/main/kotlin").toPath()).forEach { sourceRoot ->
            Files.walk(sourceRoot).use { paths ->
                paths.filter {
                    Files.isRegularFile(it) &&
                        (it.fileName.toString().endsWith(".kt") || it.fileName.toString().endsWith(".kts"))
                }
                    .sorted().forEach {
                        sources[sourceRoot.relativize(it).toString().replace(File.separatorChar, '/')] =
                            Files.readString(it)
                    }
                }
        }
        val source = sources.values.joinToString("\n")
        listOf(
            "/bin/bash", "\"bash\", \"-c\"", "\"sh\", \"-c\"",
            "\"jq\"", "\"find\"", "\"awk\"", "\"stat\"",
        ).forEach { forbidden ->
            assertFalse(forbidden in source, forbidden)
        }
        val productPythonOwners = mapOf(
            "RepositoryVerificationTasks.kt" to listOf(
                "\"python3\", \"-m\", \"ci.products.aggregate\"",
            ),
            "codexagent.contract-product.gradle.kts" to listOf(
                "\"python3\", \"-m\", \"ci.products.contract\"",
                "executable(\"python3\")\n    args(\"-m\", \"ci.products.contract\", \"validate-package\"",
            ),
            "ProductOutputManifestGradleTask.kt" to listOf(
                "pythonExecutable.convention(\"python3\")",
            ),
            "ProductPythonTooling.kt" to listOf(
                "ProcessBuilder(listOf(\"python3\", \"-m\", \"ci.products.\$module\") + arguments)",
            ),
            "CrossLanguageNativeWrapperGradleTasks.kt" to listOf(
                "pythonExecutable.convention(\"python3\")",
                "\"python3\", packageScript.get().asFile.absolutePath, \"package\"",
            ),
            "CrossLanguageNativeWrapperValidationEvidence.kt" to listOf(
                "ProcessBuilder(listOf(\"python3\", \"-E\", \"-s\", \"-B\") + arguments)",
                "ProcessBuilder(\"python3\", \"-E\", \"-s\", \"-B\", \"-m\", " +
                    "\"ci.products.sdk_package\", \"native-metadata\"",
            ),
            "MavenRepositoryTasks.kt" to listOf(
                "\"python3\", \"-m\", \"ci.products.sdk_maven\", \"--verify-only\"",
            ),
            "NativeWrapperCapabilityEvidenceTask.kt" to listOf(
                "pythonExecutable.convention(\"python3\")",
            ),
            "NativeWrapperInstalledConsumerTask.kt" to listOf(
                "pythonExecutable.convention(\"python3\")",
            ),
            "SdkMavenPackageTask.kt" to listOf(
                "\"python3\", \"-m\", \"ci.products.sdk_maven\"",
                "\"python3\", \"-m\", \"ci.products.sdk_archive\"",
            ),
        )
        val nonProductPythonSource = sources
            .filterKeys { it !in productPythonOwners }
            .values.joinToString("\n")
        assertFalse("python3" in nonProductPythonSource)
        productPythonOwners.forEach { (owner, invocations) ->
            val productSource = requireNotNull(sources[owner])
            var remaining = productSource
            invocations.forEach { invocation ->
                assertTrue(invocation in remaining, owner)
                remaining = remaining.replace(invocation, "")
            }
            assertFalse("python3" in remaining, owner)
        }
        assertFalse("commandLine(\"python\"" in source)
        assertFalse("executable(\"python\"" in source)
        assertTrue("VerifyIosReleaseBudgetsTask" in source)
        assertTrue("xcodebuild" in source && "/usr/bin/xcrun" in source)
    }
}
