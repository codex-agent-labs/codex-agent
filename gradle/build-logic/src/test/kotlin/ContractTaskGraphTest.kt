import java.io.File
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue
import org.gradle.testkit.runner.GradleRunner
import org.gradle.testkit.runner.TaskOutcome

class ContractTaskGraphTest {
    @Test
    fun `Contract Maven reset preserves stale files on rejected inputs and runs once before publications`() {
        val root = createTempDirectory("contract-maven-reset").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"contract-maven-reset\"\n")
            root.resolve("contract-input.txt").writeText("dirty\n")
            root.resolve("build.gradle.kts").writeText(
                """
                val repository = layout.buildDirectory.dir("contract-product/maven-repository")
                val prepareContractInputs = tasks.register<Exec>("prepareContractInputs") {
                    inputs.file("contract-input.txt")
                    outputs.upToDateWhen { false }
                    commandLine(
                        "python3",
                        "-c",
                        "from pathlib import Path; assert Path('contract-input.txt').read_text().strip() == 'clean', 'dirty Contract input'",
                    )
                }
                val resetContractMavenRepository = tasks.register<Delete>("resetContractMavenRepository") {
                    dependsOn(prepareContractInputs)
                    delete(repository)
                }
                val publicationTaskNames = listOf(
                    "publishAlphaPublication", "publishBravoPublication", "publishCharliePublication",
                    "publishDeltaPublication", "publishEchoPublication", "publishFoxtrotPublication",
                    "publishGolfPublication", "publishHotelPublication", "publishIndiaPublication",
                    "publishJulietPublication", "publishKiloPublication", "publishLimaPublication",
                )
                publicationTaskNames.forEach { publicationTaskName ->
                    tasks.register<Exec>(publicationTaskName) {
                        commandLine(
                            "python3",
                            "-c",
                            "from pathlib import Path; import sys; root = Path(sys.argv[1]); " +
                                "assert not (root / 'fake/stale.txt').exists(); " +
                                "output = root / 'published' / (sys.argv[2] + '.txt'); " +
                                "output.parent.mkdir(parents=True, exist_ok=True); output.write_text('published')",
                            repository.get().asFile.absolutePath,
                            publicationTaskName,
                        )
                    }
                }
                tasks.matching { it.name in publicationTaskNames }.configureEach {
                    dependsOn(resetContractMavenRepository)
                }
                """.trimIndent() + "\n",
            )
            val stale = root.resolve("build/contract-product/maven-repository/fake/stale.txt")
            stale.parentFile.mkdirs()
            stale.writeText("must survive rejected preparation\n")
            val runner = GradleRunner.create().withProjectDir(root)

            val rejected = runner.withArguments(
                "pAP",
                "publishBravoPublication",
                "--continue",
                "--parallel",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            ).buildAndFail()
            assertTrue(rejected.task(":prepareContractInputs")?.outcome == TaskOutcome.FAILED)
            assertFalse(rejected.task(":resetContractMavenRepository")?.outcome.isSuccessful())
            assertTrue(stale.readText() == "must survive rejected preparation\n")
            assertFalse(rejected.task(":publishAlphaPublication")?.outcome.isSuccessful())
            assertFalse(rejected.task(":publishBravoPublication")?.outcome.isSuccessful())

            root.resolve("contract-input.txt").writeText("clean\n")
            val publicationTasks = listOf(
                "publishAlphaPublication", "publishBravoPublication", "publishCharliePublication",
                "publishDeltaPublication", "publishEchoPublication", "publishFoxtrotPublication",
                "publishGolfPublication", "publishHotelPublication", "publishIndiaPublication",
                "publishJulietPublication", "publishKiloPublication", "publishLimaPublication",
            )
            val cleanArguments = publicationTasks + listOf(
                "--parallel",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            )
            val accepted = runner.withArguments(cleanArguments).build()
            assertTrue(accepted.task(":resetContractMavenRepository")?.outcome == TaskOutcome.SUCCESS)
            assertTrue(accepted.output.countTaskExecutions("resetContractMavenRepository") == 1)
            assertFalse(stale.exists())
            for (publicationTask in publicationTasks) {
                assertTrue(accepted.task(":$publicationTask")?.outcome == TaskOutcome.SUCCESS)
                assertTrue(
                    root.resolve("build/contract-product/maven-repository/published/$publicationTask.txt").exists(),
                    publicationTask,
                )
            }

            stale.parentFile.mkdirs()
            stale.writeText("stale again\n")
            val reused = runner.withArguments(cleanArguments).build()
            assertTrue("Reusing configuration cache." in reused.output)
            assertTrue(reused.task(":resetContractMavenRepository")?.outcome == TaskOutcome.SUCCESS)
            assertTrue(reused.output.countTaskExecutions("resetContractMavenRepository") == 1)
            assertFalse(stale.exists())
        } finally {
            root.deleteRecursively()
        }
    }

    private fun TaskOutcome?.isSuccessful(): Boolean = this in setOf(
        TaskOutcome.SUCCESS,
        TaskOutcome.FROM_CACHE,
        TaskOutcome.UP_TO_DATE,
        TaskOutcome.NO_SOURCE,
    )

    private fun String.countTaskExecutions(taskName: String): Int =
        lineSequence().count { it.startsWith("> Task :$taskName") }

    @Test
    fun `failed preparation precedes and suppresses every producer`() {
        val root = createTempDirectory("contract-task-graph").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"contract-task-graph\"\n")
            root.resolve("build.gradle.kts").writeText(
                """
                val prepareContractInputs = tasks.register("prepareContractInputs") {
                    doLast { error("dirty Contract input") }
                }
                listOf("compileContract", "publishContract", "produceEvidence").forEach { name ->
                    tasks.register(name) {
                        doLast { file("${'$'}name.executed").writeText("unexpected\n") }
                    }
                }
                tasks.configureEach {
                    if (name != "prepareContractInputs") {
                        dependsOn(prepareContractInputs)
                        mustRunAfter(prepareContractInputs)
                    }
                }
                tasks.register("verifyContract") {
                    dependsOn("compileContract", "publishContract", "produceEvidence")
                }
                """.trimIndent() + "\n",
            )

            val result = GradleRunner.create()
                .withProjectDir(root)
                .withArguments(
                    "verifyContract",
                    "--continue",
                    "--parallel",
                    "--configuration-cache",
                    "--configuration-cache-problems=fail",
                    "--stacktrace",
                )
                .buildAndFail()

            assertTrue(result.task(":prepareContractInputs")?.outcome == TaskOutcome.FAILED)
            for (producer in listOf("compileContract", "publishContract", "produceEvidence")) {
                assertNotEquals(TaskOutcome.SUCCESS, result.task(":$producer")?.outcome)
                assertFalse(root.resolve("$producer.executed").exists())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `normal to continue configuration cache transition cannot bypass preparation`() {
        val root = createTempDirectory("contract-task-graph-continue").toFile()
        try {
            root.resolve("settings.gradle.kts").writeText("rootProject.name = \"contract-task-graph\"\n")
            root.resolve("contract-input.txt").writeText("clean\n")
            root.resolve("build.gradle.kts").writeText(
                """
                val prepareContractInputs = tasks.register<Exec>("prepareContractInputs") {
                    inputs.file("contract-input.txt")
                    outputs.upToDateWhen { false }
                    commandLine(
                        "python3",
                        "-c",
                        "from pathlib import Path; assert Path('contract-input.txt').read_text().strip() == 'clean', 'dirty Contract input'",
                    )
                }
                tasks.register<Exec>("compileContract") {
                    commandLine(
                        "python3",
                        "-c",
                        "from pathlib import Path; Path('compile.executed').write_text('executed')",
                    )
                }
                tasks.configureEach {
                    if (name != "prepareContractInputs") {
                        dependsOn(prepareContractInputs)
                        mustRunAfter(prepareContractInputs)
                    }
                }
                tasks.register<Exec>("verifyContract") {
                    dependsOn("compileContract")
                    commandLine(
                        "python3",
                        "-c",
                        "from pathlib import Path; Path('verify.executed').write_text('executed')",
                    )
                }
                """.trimIndent() + "\n",
            )

            val runner = GradleRunner.create()
                .withProjectDir(root)
            val primed = runner.withArguments(
                "verifyContract",
                "--configuration-cache",
                "--configuration-cache-problems=fail",
                "--stacktrace",
            ).build()
            assertTrue(primed.task(":verifyContract")?.outcome == TaskOutcome.SUCCESS)
            assertTrue(root.resolve("compile.executed").delete())
            assertTrue(root.resolve("verify.executed").delete())
            root.resolve("contract-input.txt").writeText("dirty\n")

            repeat(2) {
                val rejected = runner.withArguments(
                    "verifyContract",
                    "--continue",
                    "--configuration-cache",
                    "--configuration-cache-problems=fail",
                    "--stacktrace",
                ).buildAndFail()
                assertTrue("Reusing configuration cache." in rejected.output)
                assertTrue("dirty Contract input" in rejected.output)
                assertTrue(rejected.task(":prepareContractInputs")?.outcome == TaskOutcome.FAILED)
                for (task in listOf("compileContract", "verifyContract")) {
                    assertFalse(
                        rejected.task(":$task")?.outcome in setOf(
                            TaskOutcome.SUCCESS,
                            TaskOutcome.FROM_CACHE,
                            TaskOutcome.UP_TO_DATE,
                            TaskOutcome.NO_SOURCE,
                        ),
                        task,
                    )
                }
                assertFalse(root.resolve("compile.executed").exists())
                assertFalse(root.resolve("verify.executed").exists())
            }
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `production wiring binds every Contract producer to preparation`() {
        val source = File("src/main/kotlin/codexagent.contract-product.gradle.kts").readText()
        val coreVerification = File("src/main/kotlin/codexagent.core-verification.gradle.kts").readText()
        assertTrue("contractPublicationNames.map" in source)
        for (producer in listOf(
            "discoverCrossLanguageApi",
            "verifyCrossLanguageApiCoverage",
            "verifyKotlinBindingParity",
            "verifyProtocolSource",
        )) {
            assertTrue("\"$producer\"" in coreVerification, producer)
        }
        assertFalse("gradle.startParameter.isContinueOnFailure" in source)
        assertFalse("RejectContinueTask" in source)
        assertFalse("enforceContractFailFast" in source)
        assertFalse(File("src/main/kotlin/RejectContinueTask.kt").exists())
        assertTrue("core.tasks.configureEach {\n    dependsOn(prepareContractInputs)" in source)
        assertTrue("mustRunAfter(prepareContractInputs)" in source)
        val mavenReset = source
            .substringAfter("tasks.register<Delete>(\"resetContractMavenRepository\")")
            .substringBefore("val contractStage")
        assertTrue("dependsOn(prepareContractInputs)" in mavenReset)
        assertTrue("delete(contractMavenRepository)" in mavenReset)
        assertTrue("core.tasks.matching { it.name in contractPublicationTaskNames }.configureEach" in mavenReset)
        assertTrue("dependsOn(resetContractMavenRepository)" in mavenReset)
        val legacyCleanup = source
            .substringAfter("tasks.register<Delete>(\"deleteLegacyContractDevelopmentKey\")")
            .substringBefore("val assembleContractBundle")
        assertTrue("dependsOn(prepareContractInputs)" in legacyCleanup)
        val verifyContract = source.substringAfter("tasks.register(\"verifyContract\")")
        assertTrue("dependsOn(verifyContractBundle)" in verifyContract)
        for (forbidden in listOf("check", "verifyJavaBindingParity", "JavaScript", "runtime")) {
            assertFalse(forbidden in verifyContract, forbidden)
        }
        assertFalse("allprojects" in source)
        assertTrue("\"prepareContractInputs\"" in coreVerification)
        assertFalse("enforceContractFailFast" in coreVerification)
        assertFalse("rootProject.allprojects" in coreVerification)
        for (forbidden in listOf(
            "VerifyJavaBindingParityTask",
            "verifyJavaBindingParity",
            "codexAgent.runtimeVersion",
            "codex-agent-runtime",
            "invalidateJavaScriptTypeScriptBindingParityOutput",
            "invalidateCodexAgentAppleBindingEvidence",
            "invalidateCodexAgentCAbiBootstrapEvidence",
        )) {
            assertFalse(forbidden in coreVerification, forbidden)
        }
        val coreCheck = coreVerification.substringAfter("afterEvaluate {")
        assertTrue("tasks.named(\"check\").configure" in coreCheck)
        assertTrue("setDependsOn(listOf(" in coreCheck)
        assertTrue("verifyProtocolSource" in coreCheck)
        assertTrue("verifyKotlinBindingParity" in coreCheck)
        assertFalse("Java" in coreCheck)
        assertFalse("JavaScript" in coreCheck)
        assertFalse("runtime" in coreCheck)
        assertFalse(
            "RejectContinueTask.kt" in File("../../ci/lanes/contract-product.production.pathspec").readText(),
        )
        val rootBuild = File("../../build.gradle.kts").readText()
        assertTrue("id(\"codexagent.contract-product\") apply false" in rootBuild)
        assertTrue("apply(plugin = \"codexagent.contract-product\")" in rootBuild)

        val isolationTest = File("src/test/kotlin/ContractIsolationFixtureTest.kt").readText()
        val isolationBuild = File("../../gradle/release/contract-isolation-fixture/build.gradle.kts").readText()
        assertFalse("copyDirectory(\"gradle/build-logic/src/main\"" in isolationTest)
        assertFalse("codexAgent.runtimeVersion" in isolationBuild)
        for (forbiddenFile in listOf(
            "CrossLanguageJavaBindingParityEvidence.kt",
            "CrossLanguageJavaBindingTasks.kt",
            "CrossLanguageJavaScriptBindingTasks.kt",
            "AppleCompilerEvidenceTask.kt",
            "CrossLanguageCAbiBootstrapEvidence.kt",
            "CrossLanguageNativeWrapperBindingEvidence.kt",
        )) {
            assertFalse("\"$forbiddenFile\"" in isolationTest, forbiddenFile)
        }
    }
}
