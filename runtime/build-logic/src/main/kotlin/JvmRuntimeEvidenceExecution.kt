import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.util.concurrent.TimeUnit
import java.util.zip.ZipFile

internal data class JvmEvidenceProcessResult(
    val exitCode: Int,
    val output: String,
    val rawOutput: ByteArray = output.toByteArray(Charsets.UTF_8),
)

internal fun executeJvmRuntimeEvidence(
    candidateCommit: String,
    target: String,
    runnerOs: String,
    runnerArch: String,
    javaExecutable: String,
    distributionManifest: File,
    classifierArchive: File,
    compiledJvmTestRuntime: File,
    evidenceFile: File,
    runner: (List<String>, Map<String, String>) -> JvmEvidenceProcessResult = ::runJvmEvidenceProcess,
    testTask: String = jvmRuntimeEvidenceTestTask(target),
    executionFile: File = evidenceFile.resolveSibling("${evidenceFile.nameWithoutExtension}-execution.json"),
    testReport: File = evidenceFile.resolveSibling(jvmRuntimeEvidenceTestReportName(target)),
) {
    validateRuntimeEvidenceOutputs(listOf(evidenceFile, executionFile, testReport),
        listOf(distributionManifest, classifierArchive, compiledJvmTestRuntime))
    evidenceFile.delete()
    testReport.delete()
    executionFile.delete()
    check(candidateCommit.matches(Regex("[0-9a-f]{40}"))) { "JVM evidence commit is not immutable" }
    val expected = desktopRuntimeEvidenceTargets.getValue(target)
    check(runnerOs == expected.runnerOs && runnerArch == expected.runnerArch) {
        "JVM evidence runner does not match $target"
    }
    check(evidenceFile.name == jvmRuntimeEvidenceFileName(target)) { "JVM evidence filename mismatch" }
    check(javaExecutable.isNotBlank() && '\n' !in javaExecutable && '\r' !in javaExecutable) {
        "Java executable is invalid"
    }
    val classifier = inspectDesktopClassifier(
        target,
        readDesktopCodexManifest(distributionManifest),
        classifierArchive,
    )
    inspectJvmRuntimeRunnerArchive(compiledJvmTestRuntime)
    val executions = mutableListOf<RuntimeEvidenceProcessCapture>()
    fun capture(id: String, result: JvmEvidenceProcessResult) {
        executions += RuntimeEvidenceProcessCapture(id, result.exitCode, result.rawOutput.copyOf())
        writeRuntimeEvidenceExecution(executionFile, "jvm", target, DESKTOP_RUNTIME_TEST_CLASS, executions)
    }
    writeRuntimeEvidenceExecution(executionFile, "jvm", target, DESKTOP_RUNTIME_TEST_CLASS, executions)
    val temporary = Files.createTempDirectory("codex-agent-jvm-evidence-$target").toFile().canonicalFile
    try {
        val runtime = stageRuntimeBundleForEvidence(
            classifierArchive,
            target,
            classifier.classifier,
            classifier.archiveSha256,
            temporary.resolve("runtime"),
        )
        val runnerRoot = temporary.resolve("runner")
        extractJvmRunner(compiledJvmTestRuntime, runnerRoot)
        val separator = if (target == "mingwX64") ";" else ":"
        val classpath = "${runnerRoot.resolve("classes")}$separator${runnerRoot.resolve("lib/*")}"
        val baseCommand = listOf(javaExecutable, "-cp", classpath, JVM_RUNTIME_RUNNER_ENTRYPOINT)
        val environment = runtime.environment(target)
        val listing = runner(baseCommand + "--list-tests", environment)
        capture("discovery", listing)
        check(listing.exitCode == 0) { "JVM test discovery failed: ${listing.output}" }
        verifyJvmTestListing(listing.output)
        desktopRuntimeTestMethods.forEach { method ->
            val result = runner(
                baseCommand + "--run-test=$DESKTOP_RUNTIME_TEST_CLASS.$method",
                environment,
            )
            capture(method, result)
            check(result.exitCode == 0) { "JVM runtime test failed ($method): ${result.output}" }
        }
        val evidence = buildJvmRuntimeEvidence(JvmRuntimeEvidenceValues(
            candidateCommit,
            target,
            classifier,
            compiledJvmTestRuntime,
            testTask,
        ))
        writeRuntimeEvidenceTestReport(testReport, DESKTOP_RUNTIME_TEST_CLASS, desktopRuntimeTestMethods)
        verifyRuntimeEvidenceTestReport(testReport, DESKTOP_RUNTIME_TEST_CLASS, desktopRuntimeTestMethods)
        evidenceFile.atomicWriteJson(evidence)
    } catch (failure: Throwable) {
        evidenceFile.delete()
        testReport.delete()
        throw failure
    } finally {
        temporary.deleteRecursively()
    }
}

private fun extractJvmRunner(archive: File, destination: File) {
    val members = inspectJvmRuntimeRunnerArchive(archive)
    ZipFile(archive).use { zip ->
        members.forEach { name ->
            val output = destination.resolve(name)
            output.parentFile.mkdirs()
            zip.getInputStream(zip.getEntry(name)).use { input ->
                Files.copy(input, output.toPath(), REPLACE_EXISTING)
            }
        }
    }
}

internal fun verifyJvmTestListing(output: String) {
    val actual = output.replace("\r", "").lineSequence().filter(String::isNotBlank).toList()
    val expected = listOf("$DESKTOP_RUNTIME_TEST_CLASS.") + desktopRuntimeTestMethods.map { "  $it" }
    check(actual == expected) { "JVM test inventory is incomplete or unexpected" }
}

internal fun runJvmEvidenceProcess(
    command: List<String>,
    environment: Map<String, String>,
): JvmEvidenceProcessResult {
    val log = Files.createTempFile("jvm-runtime-evidence", ".log").toFile()
    return try {
        val process = ProcessBuilder(command)
            .redirectErrorStream(true)
            .redirectOutput(log)
            .apply { environment().putAll(environment) }
            .start()
        val completed = process.waitFor(5, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        val rawOutput = log.readBytes()
        JvmEvidenceProcessResult(if (completed) process.exitValue() else -1,
            rawOutput.toString(Charsets.UTF_8), rawOutput)
    } finally {
        log.delete()
    }
}
