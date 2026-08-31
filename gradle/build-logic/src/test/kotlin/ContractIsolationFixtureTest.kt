import java.io.File
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class ContractIsolationFixtureTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-core").isDirectory }

    private val contractBuildLogicSourceFiles = listOf(
        "CodexAgentBuild.kt",
        "CrossLanguageApiCoverage.kt",
        "CrossLanguageApiDiscovery.kt",
        "CrossLanguageApiDiscoveryCli.kt",
        "CrossLanguageApiEvidence.kt",
        "CrossLanguageApiReportCodec.kt",
        "CrossLanguageApiTasks.kt",
        "CrossLanguageBindingAudit.kt",
        "CrossLanguageBindingParity.kt",
        "CrossLanguageBindingReceipt.kt",
        "CrossLanguageBindingTasks.kt",
        "CrossLanguageCAbiPackageEvidence.kt",
        "CrossLanguageKotlinBindingEvidence.kt",
        "DesktopRuntimeZipModes.kt",
        "ProductOutputManifestGradleTask.kt",
        "ProductVersions.kt",
        "ReleaseIo.kt",
        "VerifyProtocolSourceTask.kt",
        "codexagent.contract-product.gradle.kts",
        "codexagent.core-verification.gradle.kts",
    )

    @Test
    fun `Contract production inputs cover the exact compiler closure`() {
        val matchers = repository.resolve("ci/lanes/contract-product.production.pathspec")
            .readLines()
            .filter { it.isNotBlank() && !it.startsWith('#') }
            .map { pattern ->
                repository.toPath().fileSystem.getPathMatcher(
                    "glob:${pattern.replace('/', File.separatorChar)}",
                )
            }
        val missing = contractBuildLogicSourceFiles.map { source ->
            "gradle/build-logic/src/main/kotlin/$source"
        }.filterNot { relative ->
            val path = repository.toPath().fileSystem.getPath(relative.replace('/', File.separatorChar))
            matchers.any { it.matches(path) }
        }
        assertTrue(missing.isEmpty(), "Contract compiler inputs missing from production pathspec: $missing")
    }

    @Test
    fun `explicit Contract build logic closure compiles alone`() {
        val fixture = createTempDirectory("contract-build-logic").toFile()
        try {
            copyContractBuildLogic(fixture)
            val result = GradleRunner.create()
                .withProjectDir(fixture.resolve("gradle/build-logic"))
                .withArguments(
                    "compileKotlin",
                    "--configuration-cache",
                    "--configuration-cache-problems=fail",
                    "--stacktrace",
                )
                .build()
            assertTrue(
                result.task(":compileKotlin")?.outcome in setOf(
                    TaskOutcome.SUCCESS,
                    TaskOutcome.FROM_CACHE,
                    TaskOutcome.UP_TO_DATE,
                ),
            )
        } finally {
            fixture.deleteRecursively()
        }
    }

    @Test
    fun `copied Contract publishes and proves canonical behavior without downstream sources`() {
        val fixture = createTempDirectory("contract-isolation").toFile()
        try {
            copyDirectory("gradle/release/contract-isolation-fixture", fixture)
            copyFile("gradle/release/versions/contract.txt", fixture)
            copyContractBuildLogic(fixture)
            copyFile("codex-agent-core/build.gradle.kts", fixture)
            copyFile("codex-agent-core/gradle.lockfile", fixture)
            copyDirectory("codex-agent-core/src", fixture)
            copyDirectory("codex-agent-core/protocol", fixture)
            copyFile(".gitattributes", fixture)
            copyFile(".github/workflows/product-validation.yml", fixture)
            copyFile("gradlew", fixture)
            copyFile("gradlew.bat", fixture)
            copyFile("settings-gradle.lockfile", fixture)
            copyDirectory("gradle/wrapper", fixture)
            copyFile("ci/impact.py", fixture)
            copyDirectory("ci/products", fixture)
            copyFile("ci/lanes/contract-product.production.pathspec", fixture)
            copyFile("ci/lanes/contract-product.test.pathspec", fixture)
            copyFile("ci/tests/test_contract_bundle.py", fixture)
            copyFile("ci/tests/test_contract_output_containment.py", fixture)
            copyFile("ci/tests/test_products.py", fixture)

            listOf(
                "codex-agent-sdk",
                "codex-agent-runtime-android",
                "codex-agent-runtime-desktop",
                "codex-agent-runtime-ios",
                "codex-agent-bindings",
                "tooling",
            ).forEach { assertFalse(fixture.resolve(it).exists(), it) }
            assertFalse(
                "codexAgent.runtimeVersion" in fixture.resolve("build.gradle.kts").readText(),
                "Contract isolation must not define a Runtime version",
            )
            val copiedBuildLogicSources = fixture.resolve("gradle/build-logic/src/main/kotlin")
                .walkTopDown()
                .filter(File::isFile)
                .map { it.relativeTo(fixture.resolve("gradle/build-logic/src/main/kotlin")).invariantSeparatorsPath }
                .toSet()
            assertEquals(
                contractBuildLogicSourceFiles.toSet(),
                copiedBuildLogicSources,
                "Contract fixture build logic must be the exact dependency-closed allow-list",
            )

            runGit(fixture, "init")
            runGit(fixture, "config", "user.name", "Contract Isolation Fixture")
            runGit(fixture, "config", "user.email", "contract-isolation@example.invalid")
            runGit(fixture, "config", "commit.gpgsign", "false")
            runGit(fixture, "add", ".")
            runGit(fixture, "commit", "-m", "fixture")
            assertTrue(runGit(fixture, "status", "--porcelain").isBlank())

            val legacyPrivateKey =
                fixture.resolve("build/contract-product/development-key/development-ed25519")
            legacyPrivateKey.parentFile.mkdirs()
            legacyPrivateKey.writeText("must be deleted\n")
            val staleMavenFile =
                fixture.resolve("build/contract-product/maven-repository/stale-before-reset.txt")
            staleMavenFile.parentFile.mkdirs()
            staleMavenFile.writeText("must be deleted by accepted preparation\n")

            val result = GradleRunner.create()
                .withProjectDir(fixture)
                .withArguments(
                    "verifyContract",
                    "--configuration-cache",
                    "--configuration-cache-problems=fail",
                    "--stacktrace",
                )
                .build()

            val contractPublications = listOf(
                "KotlinMultiplatform",
                "Android",
                "Jvm",
                "IosArm64",
                "IosSimulatorArm64",
                "MacosArm64",
                "MacosX64",
                "LinuxArm64",
                "LinuxX64",
                "MingwX64",
                "Js",
                "WasmJs",
            ).map { publication ->
                ":codex-agent-core:publish${publication}PublicationToCONTRACT_BUNDLE_STAGINGRepository"
            }
            val lifecycleAndEvidence = listOf(
                ":prepareContractInputs",
                ":stageContractBundleInputs",
                ":deleteLegacyContractDevelopmentKey",
                ":assembleContractBundle",
                ":verifyContractBundle",
                ":verifyContract",
                ":codex-agent-core:discoverCrossLanguageApi",
                ":codex-agent-core:verifyProtocolSource",
                ":codex-agent-core:verifyCrossLanguageApiCoverage",
                ":codex-agent-core:verifyKotlinBindingParity",
            )
            (contractPublications + lifecycleAndEvidence).forEach { task ->
                assertTrue(result.task(task)?.outcome in setOf(TaskOutcome.SUCCESS, TaskOutcome.FROM_CACHE), task)
            }
            assertEquals(TaskOutcome.SUCCESS, result.task(":resetContractMavenRepository")?.outcome)
            assertFalse(staleMavenFile.exists())
            val stagedGroup = fixture.resolve(
                "build/contract-product/maven-repository/io/github/codex-agent-labs",
            )
            facadePublicationSpecs.map { it.coreArtifact }.forEach { artifact ->
                val versionDirectory = stagedGroup.resolve("$artifact/0.2.0")
                assertTrue(versionDirectory.isDirectory, versionDirectory.path)
                assertTrue(
                    versionDirectory.listFiles().orEmpty().any { it.isFile && it.extension == "pom" },
                    "Missing POM for $artifact",
                )
            }

            val report = fixture.resolve("codex-agent-core/build/reports/cross-language-api/canonical-api.json")
            val coverage = fixture.resolve("codex-agent-core/build/reports/cross-language-api/canonical-coverage.json")
            assertEquals(556, readCrossLanguageCanonicalApiEvidence(report, coverage).memberKeys.size)
            assertEquals(
                CrossLanguageBinding.KOTLIN,
                readCrossLanguageBindingReceipt(
                    fixture.resolve("codex-agent-core/build/reports/cross-language-api/bindings/kotlin-parity.json"),
                ).language,
            )

            val bundle = fixture.resolve("build/contract-product/bundle/codex-agent-contract-0.2.0.zip")
            assertTrue(bundle.isFile)
            assertTrue(fixture.resolve("build/contract-product/bundle/development-ed25519.pub").isFile)
            assertFalse(fixture.walkTopDown().any { it.name == "development-ed25519" })
            ZipFile(bundle).use { archive ->
                val entry = assertNotNull(archive.getEntry("contract-manifest.json"))
                val manifest = archive.getInputStream(entry).bufferedReader().use { reader ->
                    Json.parseToJsonElement(reader.readText()).jsonObject
                }
                assertEquals(556, manifest.getValue("capabilityCount").jsonPrimitive.int)
                assertEquals(
                    "development",
                    manifest.getValue("signing").jsonObject.getValue("trustDomain").jsonPrimitive.content,
                )
            }

            val dirtyInput = fixture.resolve("codex-agent-core/src/commonMain/kotlin")
                .walkTopDown()
                .first { it.isFile && it.extension == "kt" }
            val dirtyRelativePath = dirtyInput.relativeTo(fixture).invariantSeparatorsPath
            val cleanInput = dirtyInput.readBytes()
            legacyPrivateKey.parentFile.mkdirs()
            legacyPrivateKey.writeText("must survive failed preparation\n")
            staleMavenFile.parentFile.mkdirs()
            staleMavenFile.writeText("must survive failed preparation\n")
            dirtyInput.appendText("\n// dirty Contract input for fail-closed fixture\n")
            val successfulOutcomes = setOf(
                TaskOutcome.SUCCESS,
                TaskOutcome.FROM_CACHE,
                TaskOutcome.UP_TO_DATE,
                TaskOutcome.NO_SOURCE,
            )
            val lifecycleTasks = setOf(
                ":stageContractBundleInputs",
                ":deleteLegacyContractDevelopmentKey",
                ":assembleContractBundle",
                ":verifyContractBundle",
                ":verifyContract",
            )
            try {
                listOf(
                    "verifyContract",
                    "verifyContract",
                    "vCB",
                    ":codex-agent-core:compileKotlinJvm",
                    ":codex-agent-c:vKBP",
                    ":codex-agent-c:publishJvmPublicationToCONTRACT_BUNDLE_STAGINGRepository",
                    "deleteLegacyContractDevelopmentKey",
                ).forEachIndexed { index, selector ->
                    val arguments = mutableListOf(
                        selector,
                        "--continue",
                        "--configuration-cache",
                        "--configuration-cache-problems=fail",
                        "--stacktrace",
                    )
                    if (selector == ":codex-agent-core:compileKotlinJvm") arguments += "--parallel"
                    val rejected = GradleRunner.create()
                        .withProjectDir(fixture)
                        .withArguments(arguments)
                        .buildAndFail()
                    assertTrue(
                        "Contract input worktree does not match the requested revision" in rejected.output,
                        selector,
                    )
                    assertTrue(dirtyRelativePath in rejected.output, selector)
                    assertTrue(
                        rejected.task(":prepareContractInputs")?.outcome == TaskOutcome.FAILED,
                        selector,
                    )
                    assertTrue(
                        rejected.task(":resetContractMavenRepository")?.outcome !in successfulOutcomes,
                        selector,
                    )
                    if (index < 2) assertTrue("Reusing configuration cache." in rejected.output, selector)
                    assertTrue(
                        rejected.tasks.none { task ->
                            task.outcome in successfulOutcomes && (
                                task.path.startsWith(":codex-agent-core:") ||
                                    task.path in lifecycleTasks
                                )
                        },
                        "Contract/Core task executed after failed preparation for $selector",
                    )
                    assertTrue(legacyPrivateKey.readText() == "must survive failed preparation\n", selector)
                    assertTrue(staleMavenFile.readText() == "must survive failed preparation\n", selector)
                }
            } finally {
                dirtyInput.writeBytes(cleanInput)
            }
            assertTrue(runGit(fixture, "diff", "--exit-code", "HEAD", "--", dirtyRelativePath).isBlank())

            val cleanup = GradleRunner.create()
                .withProjectDir(fixture)
                .withArguments(
                    "deleteLegacyContractDevelopmentKey",
                    "--configuration-cache",
                    "--configuration-cache-problems=fail",
                    "--stacktrace",
                )
                .build()
            assertTrue(
                cleanup.task(":deleteLegacyContractDevelopmentKey")?.outcome == TaskOutcome.SUCCESS,
            )
            assertFalse(legacyPrivateKey.exists())

            val forbiddenTaskPrefixes = listOf(
                ":codex-agent-sdk:",
                ":codex-agent-runtime-",
                ":codex-agent-bindings:",
                ":tooling:",
            )
            val forbiddenTasks = result.tasks.map { it.path }.filter { path ->
                forbiddenTaskPrefixes.any(path::startsWith)
            }
            assertTrue(forbiddenTasks.isEmpty(), "Executed downstream tasks: $forbiddenTasks")
            val forbiddenContractTasks = setOf(
                ":codex-agent-core:verifyJavaBindingParity",
                ":codex-agent-core:invalidateJavaScriptTypeScriptBindingParityOutput",
                ":codex-agent-core:invalidateCodexAgentAppleBindingEvidence",
                ":codex-agent-core:invalidateCodexAgentCAbiBootstrapEvidence",
            )
            assertTrue(
                result.tasks.none { it.path in forbiddenContractTasks },
                "Executed non-Contract parity tasks: ${result.tasks.map { it.path }.filter { it in forbiddenContractTasks }}",
            )
        } finally {
            fixture.deleteRecursively()
        }
    }

    private fun copyFile(path: String, fixture: File) {
        val source = repository.resolve(path)
        val target = fixture.resolve(path)
        target.parentFile.mkdirs()
        source.copyTo(target)
    }

    private fun copyContractBuildLogic(fixture: File) {
        copyFile("gradle/libs.versions.toml", fixture)
        copyFile("gradle/build-logic/build.gradle.kts", fixture)
        copyFile("gradle/build-logic/settings.gradle.kts", fixture)
        contractBuildLogicSourceFiles.forEach { fileName ->
            copyFile("gradle/build-logic/src/main/kotlin/$fileName", fixture)
        }
    }

    private fun copyDirectory(path: String, fixture: File) {
        val source = repository.resolve(path)
        val target = if (path == "gradle/release/contract-isolation-fixture") fixture else fixture.resolve(path)
        check(source.copyRecursively(target)) { "Could not copy $path" }
    }

    private fun runGit(repository: File, vararg arguments: String): String {
        val process = ProcessBuilder(listOf("git", *arguments))
            .directory(repository)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        check(process.waitFor() == 0) { "git ${arguments.joinToString(" ")} failed:\n$output" }
        return output.trim()
    }
}
