import java.nio.file.Files
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

@DisableCachingByDefault(because = "Platform smoke evidence must execute for every immutable candidate")
abstract class RecordDesktopRuntimeEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val binarySha256: Property<String>
    @get:Input abstract val candidateCommit: Property<String>
    @get:Input abstract val runnerOs: Property<String>
    @get:Input abstract val runnerArch: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val classifierArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val distributionManifest: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val testReport: RegularFileProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun record() {
        val targetName = target.get()
        val commit = candidateCommit.get()
        check(commit.matches(Regex("[0-9a-f]{40}"))) { "Desktop evidence commit is not immutable" }
        verifyDesktopRuntimeTestReport(testReport.get().asFile, targetName)
        val expected = desktopRuntimeEvidenceTargets.getValue(targetName)
        check(classifier.get() == expected.classifier) { "Desktop evidence classifier mismatch" }
        check(runnerOs.get() == expected.runnerOs && runnerArch.get() == expected.runnerArch) {
            "Desktop evidence runner does not match $targetName"
        }
        val proof = inspectDesktopClassifier(
            targetName,
            readDesktopCodexManifest(distributionManifest.get().asFile),
            classifierArchive.get().asFile,
        )
        check(binarySha256.get() == proof.binarySha256) { "Desktop evidence App Server hash mismatch" }
        evidenceFile.get().asFile.atomicWriteJson(buildDesktopRuntimeEvidence(DesktopRuntimeEvidenceValues(
            commit,
            targetName,
            proof.binarySha256,
            proof.supervisorSha256,
            proof.archiveSha256,
        )))
    }
}

@DisableCachingByDefault(because = "Executes the imported native runtime lifecycle on the current host")
abstract class ExecuteImportedNativeRuntimeEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val expectedCompatibilityVersion: Property<String>
    @get:Input abstract val candidateCommit: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val classifierArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val nativeTestExecutable: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val distributionManifest: RegularFileProperty
    @get:OutputFile abstract val evidenceFile: RegularFileProperty
    @get:OutputFile abstract val testReport: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun execute() {
        val targetName = target.get()
        val commit = candidateCommit.get()
        check(commit.matches(Regex("[0-9a-f]{40}"))) { "Desktop evidence commit is not immutable" }
        check(crossLanguageCAbiHostTarget(System.getProperty("os.name"), System.getProperty("os.arch")) == targetName) {
            "Imported native runtime evidence target does not match the current host: $targetName"
        }
        val classifier = classifierArchive.get().asFile
        val proof = inspectDesktopClassifier(
            targetName,
            readDesktopCodexManifest(distributionManifest.get().asFile),
            classifier,
        )
        check(proof.libraryVersion == expectedCompatibilityVersion.get()) {
            "Imported native runtime compatibility version mismatch"
        }
        val sourceTest = nativeTestExecutable.get().asFile
        check(sourceTest.isFile && !Files.isSymbolicLink(sourceTest.toPath())) {
            "Imported native runtime test executable is missing or symbolic"
        }
        val runtimeRoot = Files.createTempDirectory("codex-agent-$targetName-platform-evidence").toFile()
        try {
            val test = runtimeRoot.resolve(sourceTest.name)
            Files.copy(sourceTest.toPath(), test.toPath())
            check(test.setExecutable(true, false)) {
                "Imported native runtime test executable could not be enabled"
            }
            val environment = stageRuntimeBundleForEvidence(
                classifier,
                targetName,
                desktopRuntimeEvidenceTargets.getValue(targetName).classifier,
                runtimeRoot,
            ).environment(targetName)
            val listing = runDesktopEvidenceProcess(listOf(test.absolutePath, "--ktest_list_tests"), environment)
            check(listing.exitCode == 0) { "Imported native test discovery failed: ${listing.output}" }
            val lines = listing.output.lineSequence().filter(String::isNotBlank).toList()
            val classIndex = lines.indexOf("$DESKTOP_RUNTIME_TEST_CLASS.")
            val tests = lines.drop(classIndex + 1).takeWhile { it.startsWith("  ") }.map(String::trim)
            check(classIndex >= 0 && tests.toSet() == desktopRuntimeTestMethods &&
                tests.size == desktopRuntimeTestMethods.size) {
                "Imported native test executable has an unexpected test set"
            }
            desktopRuntimeTestMethods.forEach { method ->
                val result = runDesktopEvidenceProcess(
                    listOf(
                        test.absolutePath,
                        "--ktest_filter=$DESKTOP_RUNTIME_TEST_CLASS.$method",
                        "--ktest_logger=SILENT",
                    ),
                    environment,
                )
                check(result.exitCode == 0) {
                    "Imported native desktop test failed ($method): ${result.output}"
                }
            }
        } finally {
            runtimeRoot.deleteRecursively()
        }
        val report = testReport.get().asFile
        report.parentFile.mkdirs()
        report.writeText(buildString {
            append("<testsuite tests=\"").append(desktopRuntimeTestMethods.size)
                .append("\" skipped=\"0\" failures=\"0\" errors=\"0\">\n")
            desktopRuntimeTestMethods.forEach { method ->
                append("  <testcase classname=\"").append(targetName).append("Test.")
                    .append(DESKTOP_RUNTIME_TEST_CLASS).append("\" name=\"")
                    .append(method).append("\"/>\n")
            }
            append("</testsuite>\n")
        })
        verifyDesktopRuntimeTestReport(report, targetName)
        evidenceFile.get().asFile.atomicWriteJson(buildDesktopRuntimeEvidence(DesktopRuntimeEvidenceValues(
            commit,
            targetName,
            proof.binarySha256,
            proof.supervisorSha256,
            proof.archiveSha256,
            path,
        )))
    }
}
