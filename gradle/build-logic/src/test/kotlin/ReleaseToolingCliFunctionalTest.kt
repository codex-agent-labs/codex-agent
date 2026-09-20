import java.io.File
import java.util.zip.ZipFile
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ReleaseToolingCliFunctionalTest {
    private val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
        .first { it.resolve(".github/workflows/release-candidate.yml").isFile }
    private val jar = File(checkNotNull(System.getProperty("codexAgent.releaseToolingJar")))

    @Test
    fun `packaged Firebase verifier replays protected evidence without Gradle`() {
        val root = createTempDirectory("release-tooling-firebase-").toFile().canonicalFile
        try {
            val schema = Regex("(?m)^LANE_RECEIPT_SCHEMA_VERSION = ([1-9][0-9]*)$")
                .findAll(repository.resolve("ci/receipt.py").readText()).single().groupValues[1].toInt()
            val fixture = FirebaseAndroidOriginalEvidenceTest.Fixture(root, schema)
            // Fixture-only manifest decoder; this proves packaged replay, not real APK/host execution.
            val analyzer = root.resolve("apkanalyzer-fixture").apply {
                writeText("""
                    #!/bin/sh
                    test "${'$'}1" = manifest && test "${'$'}2" = print || exit 7
                    case "${'$'}3" in
                      */$FIREBASE_APPLICATION_APK) printf '%s\n' '<manifest package="$FIREBASE_APPLICATION_ID"/>' ;;
                      */$FIREBASE_TEST_APK) printf '%s\n' '<manifest package="$FIREBASE_TEST_APPLICATION_ID"><instrumentation android:targetPackage="$FIREBASE_APPLICATION_ID"/></manifest>' ;;
                      *) exit 8 ;;
                    esac
                """.trimIndent() + "\n")
                check(setExecutable(true))
            }
            val args = arrayOf("verify-original-firebase-android-evidence",
                "--evidence-directory", fixture.evidence.absolutePath,
                "--protected-observation-directory", fixture.observation.absolutePath,
                "--expected-release-aar", fixture.expectedAar.absolutePath,
                "--candidate-commit", FirebaseAndroidOriginalEvidenceTest.CANDIDATE_COMMIT,
                "--candidate-tree", FirebaseAndroidOriginalEvidenceTest.CANDIDATE_TREE,
                "--trusted-source-commit", FirebaseAndroidOriginalEvidenceTest.SOURCE_COMMIT,
                "--trusted-source-tree", FirebaseAndroidOriginalEvidenceTest.SOURCE_TREE,
                "--apkanalyzer-executable", analyzer.absolutePath)
            val before = verifiedRegularFiles(root).mapValues { it.value.releaseDigest() }
            val passed = runTool(root, *args)
            assertEquals(0, passed.first, passed.second)
            assertEquals(before, verifiedRegularFiles(root).mapValues { it.value.releaseDigest() })
            fixture.expectedAar.appendText("different authenticated binary")
            val failed = runTool(root, *args)
            assertTrue(failed.first != 0, failed.second)
            assertTrue("differs from its authenticated binary" in failed.second, failed.second)
            assertFalse("NoClassDefFoundError" in failed.second || "ClassNotFoundException" in failed.second)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged facade verifier replays complete imported metadata without Gradle`() {
        val root = createTempDirectory("release-tooling-facade-").toFile().canonicalFile
        try {
            FacadePublicationContractTest.Fixture(root)
            val stage = root.resolve("stage")
            val maven = stage.resolve("outputs/maven/${CodexAgentBuild.MAVEN_GROUP.replace('.', '/')}")
            val publications = facadePublicationSpecs.map { it.artifact to "facade/${it.publication}" } +
                ("codex-agent-bom" to "bom")
            publications.forEach { (artifact, directory) ->
                listOf("pom-default.xml" to "pom", "module.json" to "module").forEach { (name, extension) ->
                    root.resolve("$directory/$name").copyTo(
                        maven.resolve("$artifact/3.4.5/$artifact-3.4.5.$extension").also { it.parentFile.mkdirs() },
                    )
                }
            }
            val before = verifiedRegularFiles(stage).mapValues { it.value.releaseDigest() }
            val (exit, output) = runTool(root, "verify-imported-sdk-facade-publications",
                "--package-stage", stage.absolutePath, "--contract-version", "1.2.3",
                "--runtime-version", "2.3.4", "--sdk-version", "3.4.5",
                "--kotlin-version", "2.2.20", "--forbidden-path", root.absolutePath)
            assertEquals(0, exit, output)
            assertEquals(before, verifiedRegularFiles(stage).mapValues { it.value.releaseDigest() })
            val source = root.resolve("source")
            val template = source.resolve("gradle/release/sdk-facade-consumer-template")
            repository.resolve("gradle/release/sdk-facade-consumer-template").copyRecursively(template)
            val consumer = root.resolve("consumer-inputs")
            prepareStagedConsumer(template, consumer, "")
            consumer.resolve(".codex-consumer-task-outcomes.init.gradle.kts").writeText(
                stagedConsumerOutcomeInitScript(listOf("compileKotlinJvm")) +
                    stagedConsumerExecutionCaptureScript("/original/execution/task-outcomes.json"))
            val (replayExit, replayOutput) = runTool(root, "verify-original-sdk-facade-consumer-inputs",
                "--source-snapshot", source.absolutePath, "--consumer-inputs", consumer.absolutePath,
                "--package-stage", stage.absolutePath, "--target", "jvm",
                "--contract-version", "1.2.3", "--runtime-version", "2.3.4", "--sdk-version", "3.4.5",
                "--kotlin-version", "2.2.20", "--original-execution-directory", "/original/execution",
                "--android-sdk-directory", "", "--forbidden-path", root.absolutePath)
            assertEquals(0, replayExit, replayOutput)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged release tool runs without Gradle from an empty directory`() {
        val workingDirectory = createTempDirectory("release-tooling-cli").toFile()
        try {
            val (exit, output) = runTool(workingDirectory, "self-check")
            assertEquals(0, exit, output)
            assertEquals("codex-agent release tooling is ready", output.trim())
            assertTrue(workingDirectory.listFiles().isNullOrEmpty())
            val (facadeExit, facadeOutput) = runTool(
                workingDirectory, "verify-imported-sdk-facade-publications",
                "--package-stage", workingDirectory.resolve("missing-facade").absolutePath,
                "--contract-version", "0.8.0", "--runtime-version", "0.8.0",
                "--sdk-version", "0.8.0", "--kotlin-version", "2.3.10",
                "--forbidden-path", workingDirectory.absolutePath,
            )
            assertTrue(facadeExit != 0, facadeOutput)
            assertFalse("NoClassDefFoundError" in facadeOutput || "ClassNotFoundException" in facadeOutput)
            assertFalse(workingDirectory.resolve("missing-facade").exists())
            val (centralExit, centralOutput) = runTool(
                workingDirectory,
                "central-prepare",
                "--bundle", workingDirectory.resolve("missing.zip").absolutePath,
                "--candidate", workingDirectory.resolve("missing.json").absolutePath,
                "--record", workingDirectory.resolve("record.json").absolutePath,
                "--allow-new-upload", "true",
            )
            assertTrue(centralExit != 0)
            assertTrue("Central bundle and candidate manifest must be files" in centralOutput)
            assertFalse("NoClassDefFoundError" in centralOutput || "ClassNotFoundException" in centralOutput)
            assertTrue(jar.length() in 1..8_000_000)
            ZipFile(jar).use { archive ->
                val entries = archive.entries().asSequence().map { it.name }.toList()
                assertTrue("ReleaseToolingCliKt.class" in entries)
                assertTrue("ProductVersions.class" in entries)
                assertTrue("ProductVersionIdentityKt.class" in entries)
                assertTrue("NativeWrapperSdkCompatibility.class" in entries)
                assertFalse("ProductVersionsKt.class" in entries)
                assertFalse("ReleaseToolingGradleTasksKt.class" in entries)
                assertFalse("CrossLanguageNativeWrapperGradleTasksKt.class" in entries)
                listOf(
                    "GenerateCrossLanguageCAbiScenarioProofTask",
                    "PackageCrossLanguageCAbiSdkTask",
                    "GenerateCrossLanguageCAbiPackageEvidenceTask",
                    "VerifyCrossLanguageCAbiPackageEvidenceTask",
                    "GenerateCrossLanguageNativeWrapperBindingReceiptTask",
                    "AdvanceCrossLanguageBindingReceiptPhaseTask",
                ).forEach { task -> assertFalse(entries.any { it.startsWith(task) }, task) }
                assertFalse(entries.any { it.startsWith("org/gradle/") || it.startsWith("com/android/") })
                assertFalse(entries.any { it.startsWith("gradle/kotlin/dsl/") })
            }
            val jdepsName = if (System.getProperty("os.name").startsWith("Windows")) "jdeps.exe" else "jdeps"
            val jdeps = File(System.getProperty("java.home"), "bin/$jdepsName")
            // Commons Compress carries optional non-ZIP codecs. Our Apple reader
            // rejects every method except STORED/DEFLATED before opening a member.
            // Account for those exact codec families first: never ignore a missing
            // first-party class, ZIP dependency, Gradle API, or unknown dependency.
            val missing = ProcessBuilder(jdeps.absolutePath, "--missing-deps", jar.absolutePath)
                .redirectErrorStream(true).start()
            val missingOutput = missing.inputStream.bufferedReader().use { it.readText() }
            assertEquals(0, missing.waitFor(), missingOutput)
            val optionalCodecs = mapOf(
                "org.apache.commons.compress.archivers.sevenz." to "org.tukaani.xz.",
                "org.apache.commons.compress.compressors.lzma." to "org.tukaani.xz.",
                "org.apache.commons.compress.compressors.xz." to "org.tukaani.xz.",
                "org.apache.commons.compress.compressors.brotli." to "org.brotli.dec.",
                "org.apache.commons.compress.compressors.zstandard." to "com.github.luben.zstd.",
                "org.apache.commons.compress.harmony.pack200." to "org.objectweb.asm.",
            )
            missingOutput.lineSequence().filter { it.startsWith("   ") }.forEach { line ->
                val dependency = checkNotNull(Regex("\\s+(\\S+)\\s+->\\s+(\\S+)\\s+not found").matchEntire(line)) { line }
                assertTrue(optionalCodecs.any { (owner, target) ->
                    dependency.groupValues[1].startsWith(owner) && dependency.groupValues[2].startsWith(target)
                }, "Unexpected standalone dependency: $line")
            }
            val modules = ProcessBuilder(jdeps.absolutePath, "--ignore-missing-deps", "--print-module-deps", jar.absolutePath)
                .redirectErrorStream(true)
                .start()
            val moduleOutput = modules.inputStream.bufferedReader().use { it.readText() }
            assertEquals(0, modules.waitFor(), moduleOutput)
            assertEquals("java.base,java.desktop,java.logging,java.net.http", moduleOutput.trim())
        } finally {
            workingDirectory.deleteRecursively()
        }
    }

    @Test
    fun `packaged tool stages canonical Maven bytes from a fresh directory`() {
        val root = createTempDirectory("release-tooling-maven").toFile()
        try {
            val commit = "0123456789abcdef0123456789abcdef01234567"
            val versions = ProductVersions(contract = "1.2.3", runtime = "2.3.4", sdk = "3.4.5")
            val promoted = root.resolve("promoted")
            val output = root.resolve("output")
            val repositories = promotedMavenArtifactOwnership.keys.associateWith { target ->
                promoted.resolve("codex-agent-promoted-consumer-$target-$commit/payload/maven").apply { mkdirs() }
            }
            val owners = canonicalPromotedMavenOwners()
            val group = CodexAgentBuild.MAVEN_GROUP.replace('.', '/')
            val primaryPaths = expectedMavenPrimaryPaths(versions)
            assertEquals(38, owners.size)
            assertEquals(220, primaryPaths.size)
            assertTrue(primaryPaths.containsAll(setOf(
                "codex-agent-core-jvm/${versions.contract}/codex-agent-core-jvm-${versions.contract}.jar",
                "codex-agent-runtime-desktop/${versions.runtime}/" +
                    "codex-agent-runtime-desktop-${versions.runtime}-c-abi-linux-x64.zip",
                "codex-agent-bom/${versions.sdk}/codex-agent-bom-${versions.sdk}.pom",
                "codex-agent/${versions.sdk}/codex-agent-${versions.sdk}.jar",
                "codex-agent-runtime-android/${versions.sdk}/codex-agent-runtime-android-${versions.sdk}.aar",
                "codex-agent-runtime-ios-iosarm64/${versions.sdk}/" +
                    "codex-agent-runtime-ios-iosarm64-${versions.sdk}.klib",
            )))
            primaryPaths.forEach { relative ->
                val source = repositories.getValue(owners.getValue(relative.substringBefore('/')))
                    .resolve("$group/$relative")
                source.parentFile.mkdirs()
                source.writeText(relative)
                source.resolveSibling(source.name + ".sha256").writeText("verification-only checksum")
            }
            val result = runTool(
                root,
                "stage-promoted-maven",
                "--promoted", promoted.absolutePath,
                "--commit", commit,
                "--contract-version", versions.contract,
                "--runtime-version", versions.runtime,
                "--sdk-version", versions.sdk,
                "--output", output.absolutePath,
            )
            assertEquals(0, result.first, result.second)
            assertEquals(220, output.walkTopDown().count(File::isFile))

            val wrongOutput = root.resolve("wrong-output")
            val swapped = runTool(
                root,
                "stage-promoted-maven",
                "--promoted", promoted.absolutePath,
                "--commit", commit,
                "--contract-version", versions.runtime,
                "--runtime-version", versions.contract,
                "--sdk-version", versions.sdk,
                "--output", wrongOutput.absolutePath,
            )
            assertTrue(swapped.first != 0, swapped.second)
            assertTrue(!wrongOutput.exists() || wrongOutput.listFiles().isNullOrEmpty())
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged tool runs the exact binding audit without Gradle and fails incomplete parity`() {
        val root = createTempDirectory("release-tooling-binding-audit").toFile()
        try {
            val fixture = CrossLanguageBindingCliFixture(root)
            val passed = runTool(root, *fixture.cliArguments())
            assertEquals(0, passed.first, passed.second)
            assertEquals("complete", fixture.output.readReleaseObject().releaseString("result"))
            assertFalse("NoClassDefFoundError" in passed.second || "ClassNotFoundException" in passed.second)

            val invalidPhaseArguments = fixture.cliArguments().also { arguments ->
                arguments[arguments.indexOf("--phase") + 1] = "UNKNOWN"
            }
            val invalidPhase = runTool(root, *invalidPhaseArguments)
            assertTrue(invalidPhase.first != 0, invalidPhase.second)
            assertTrue("Unknown cross-language binding phase" in invalidPhase.second)
            assertFalse(fixture.output.exists())

            fixture.writeReceipt(
                CrossLanguageBinding.JAVASCRIPT_TYPESCRIPT,
                claimedMembers = fixture.members.dropLast(1),
            )
            val failed = runTool(root, *fixture.cliArguments())
            assertTrue(failed.first != 0, failed.second)
            assertTrue("Missing active binding projection javascript-typescript:" in failed.second)
            assertEquals("incomplete", fixture.output.readReleaseObject().releaseString("result"))
            assertFalse("NoClassDefFoundError" in failed.second || "ClassNotFoundException" in failed.second)
        } finally {
            root.deleteRecursively()
        }
    }

    @Test
    fun `packaged tool exposes every protected workflow command`() {
        val workingDirectory = createTempDirectory("release-tooling-commands").toFile()
        try {
            listOf(
                "verify-original-firebase-android-evidence",
                "assemble-c-abi-binding-receipt",
                "assemble-native-wrapper-binding-receipt",
                "advance-cross-language-binding-receipt",
                "audit-cross-language-bindings",
                "stage-promoted-maven",
                "assemble-promoted-candidate",
                "verify-candidate",
                "central-prepare",
                "central-await",
                "central-release",
            ).forEach { command ->
                val (exit, output) = runTool(workingDirectory, command)
                assertTrue(exit != 0, command)
                assertTrue("Unexpected release-tooling options" in output, "$command: $output")
                assertFalse("NoClassDefFoundError" in output || "ClassNotFoundException" in output, command)
                assertFalse("Unknown release-tooling command" in output, command)
            }
        } finally {
            workingDirectory.deleteRecursively()
        }
    }

    @Test
    fun `candidate and publication execute only the receipt-bound packaged tool`() {
        val candidate = repository.resolve(".github/workflows/release-candidate.yml").readText()
        val publication = repository.resolve(".github/workflows/publish.yml").readText()
        listOf(candidate, publication).forEach { workflow ->
            assertFalse("./gradlew" in workflow)
            assertFalse("kotlinc" in workflow || "javac" in workflow)
            assertTrue("java -jar \"\$RELEASE_TOOL\"" in workflow)
        }
        assertTrue(candidate.indexOf("expected_sha256") < candidate.indexOf("java -jar \"\$RELEASE_TOOL\""))
        assertTrue(publication.indexOf("release_tool_sha256") < publication.indexOf("java -jar \"\$RELEASE_TOOL\""))
        assertTrue("assemble-promoted-candidate" in candidate)
        assertTrue("verify-candidate" in publication)
        listOf("central-prepare", "central-await", "central-release").forEach {
            assertTrue(it in publication)
        }
    }

    @Test
    fun `manifest carries the exact tool and portable alone owns runtime runner primaries`() {
        val promoted = repository.resolve(
            "gradle/build-logic/src/main/kotlin/PromotedCandidateTasks.kt",
        ).readText()
        val manifest = repository.resolve(
            "gradle/build-logic/src/main/kotlin/CandidateManifestValidation.kt",
        ).readText()
        val driver = repository.resolve("ci/run-lane.sh").readText()
        val staging = repository.resolve("ci/stage.py").readText()
        assertTrue("put(\"releaseTooling\", releaseTooling.releaseRecord())" in promoted)
        assertTrue("\"releaseTooling\" to RELEASE_TOOLING_FILE_NAME" in manifest)
        assertTrue("val nodeRunnerSource = portable.one(\"node-js-runner\")" in promoted)
        assertTrue("val nodeWasmRunnerSource = portable.one(\"node-wasm-runner\")" in promoted)
        assertFalse("lanes.getValue(\"node-js\").one(\"node-js-runner\")" in promoted)
        assertFalse("lanes.getValue(\"node-wasm\").one(\"node-wasm-runner\")" in promoted)
        listOf(
            "packageJvmRuntimeEvidenceRunner",
            "packageNodeRuntimeEvidenceRunner",
            "packageNodeWasmRuntimeEvidenceRunner",
        ).forEach { task -> assertEquals(1, Regex(Regex.escape(task)).findAll(driver).count(), task) }
        assertFalse(":codex-agent-sdk:verifyJavaScriptTypeScriptBindingParity" in driver)
        assertTrue("uses: ./.github/actions/sdk-javascript-worker" in
            repository.resolve(".github/workflows/product-validation.yml").readText())
        assertTrue("python3 -B -m ci.sdk_workflow javascript" in
            repository.resolve(".github/actions/sdk-javascript-worker/action.yml").readText())
        assertTrue("writeJavaScriptSdkValidationOutputManifest" in
            repository.resolve("gradle/build-logic/src/main/kotlin/codexagent.contract-product.gradle.kts").readText())
        assertTrue("dependsOn(verifyImportedJavaScriptSdkCompatibility, verifyJavaScriptTypeScriptBindingParity)" in
            repository.resolve("gradle/build-logic/src/main/kotlin/codexagent.javascript-sdk.gradle.kts").readText())
        assertTrue(":codex-agent-runtime-desktop:wasmJsNodeTest" in driver)
        val portable = driver.substringAfter("  portable)").substringBefore("  android)")
        val nodeWasm = driver.substringAfter("  node-wasm)").substringBefore("  desktop-macos-arm64)")
        val runtimeDriver = driver.substringAfter("runtime_gradle() {").substringBefore("\n}")
        assertTrue("./gradlew -p runtime" in runtimeDriver)
        listOf(
            "codexAgent.contractPayload",
            "codexAgent.contractMetadataReceipt",
            "codexAgent.contractAttestation",
            "codexAgent.contractAttestationSignature",
            "codexAgent.contractPublicKey",
            "codexAgent.contractVersion",
            "codexAgent.runtimeVersion",
            "codexAgent.target",
        ).forEach { property ->
            assertEquals(1, Regex(Regex.escape("-P$property=")).findAll(runtimeDriver).count(), property)
        }
        assertTrue("runtime_gradle jvm" in portable)
        assertTrue("runtime_gradle node-js" in portable)
        assertTrue("runtime_gradle node-wasm" in nodeWasm)
        assertFalse(Regex("\\./gradlew[^\\n]*:codex-agent-runtime-desktop").containsMatchIn(driver))
        listOf(
            "codex-agent-jvm-runtime-evidence-runner.zip",
            "codex-agent-node-runtime-evidence-runner.zip",
            "codex-agent-node-wasm-runtime-evidence-runner.zip",
        ).forEach { archive -> assertEquals(1, Regex(Regex.escape(archive)).findAll(staging).count(), archive) }
    }

    private fun runTool(directory: File, vararg arguments: String): Pair<Int, String> {
        val java = File(System.getProperty("java.home"), "bin/java")
        val process = ProcessBuilder(java.absolutePath, "-jar", jar.absolutePath, *arguments)
            .directory(directory)
            .redirectErrorStream(true)
            .start()
        val output = process.inputStream.bufferedReader().use { it.readText() }
        return process.waitFor() to output
    }
}
