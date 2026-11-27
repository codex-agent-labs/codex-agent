import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption.REPLACE_EXISTING
import java.util.concurrent.TimeUnit
import java.util.zip.ZipFile

internal data class NodeEvidenceProcessResult(
    val exitCode: Int,
    val output: String,
    val rawOutput: ByteArray = output.toByteArray(Charsets.UTF_8),
)

internal fun executeNodeRuntimeEvidence(
    candidateCommit: String,
    target: String,
    runtimeBackend: String,
    runnerOs: String,
    runnerArch: String,
    nodeExecutable: String,
    distributionManifest: File,
    classifierArchive: File,
    compiledNodeTestRuntime: File,
    evidenceFile: File,
    testReport: File,
    runner: (List<String>, Map<String, String>) -> NodeEvidenceProcessResult = ::runNodeEvidenceProcess,
    executionFile: File = evidenceFile.resolveSibling("${evidenceFile.nameWithoutExtension}-execution.json"),
) {
    validateRuntimeEvidenceOutputs(
        listOf(evidenceFile, executionFile, testReport),
        listOf(distributionManifest, classifierArchive, compiledNodeTestRuntime),
    )
    evidenceFile.delete()
    testReport.delete()
    executionFile.delete()
    check(candidateCommit.matches(Regex("[0-9a-f]{40}"))) { "Node evidence commit is not immutable" }
    requireNodeRuntimeBackend(runtimeBackend)
    val expected = desktopRuntimeEvidenceTargets.getValue(target)
    check(runnerOs == expected.runnerOs && runnerArch == expected.runnerArch) {
        "Node evidence runner does not match $target"
    }
    check(evidenceFile.name == nodeRuntimeEvidenceFileName(target, runtimeBackend)) {
        "Node evidence filename mismatch"
    }
    check(testReport.name == nodeRuntimeTestReportFileName(target, runtimeBackend)) {
        "Node test report filename mismatch"
    }
    check(nodeExecutable.isNotBlank() && '\n' !in nodeExecutable && '\r' !in nodeExecutable) {
        "Node executable is invalid"
    }
    inspectNodeRuntimeRunnerArchive(compiledNodeTestRuntime, runtimeBackend)

    val manifest = readDesktopCodexManifest(distributionManifest)
    val classifier = inspectNodeClassifier(target, manifest, classifierArchive)
    val captures = mutableListOf<RuntimeEvidenceProcessCapture>()
    fun saveCaptures() = writeRuntimeEvidenceExecution(
        executionFile, "node-$runtimeBackend", target, NODE_RUNTIME_TEST_CLASS, captures,
    )
    fun capture(id: String, command: List<String>, environment: Map<String, String>): NodeEvidenceProcessResult {
        val result = runner(command, environment)
        captures += RuntimeEvidenceProcessCapture(id, result.exitCode, result.rawOutput.copyOf())
        saveCaptures()
        return result
    }
    saveCaptures()
    val version = capture("version", listOf(nodeExecutable, "--version"), emptyMap())
    check(version.exitCode == 0 && version.output.trim().replace("\r", "") == "v$PINNED_NODE_VERSION") {
        "Node evidence requires exactly Node v$PINNED_NODE_VERSION"
    }

    val temporary = Files.createTempDirectory("codex-agent-node-evidence-$runtimeBackend-$target")
        .toFile().canonicalFile
    try {
        val runtime = stageRuntimeBundleForEvidence(
            classifierArchive,
            target,
            classifier.classifier,
            classifier.archiveSha256,
            temporary.resolve("runtime"),
        )
        val runnerEntry = extractNodeRuntimeRunner(
            compiledNodeTestRuntime,
            runtimeBackend,
            temporary.resolve("runner"),
        )
        val environment = runtime.environment(target)
        val listing = capture(
            "discovery",
            listOf(nodeExecutable, runnerEntry.absolutePath, "--list-tests"),
            environment,
        )
        check(listing.exitCode == 0) { "Node test discovery failed: ${listing.output}" }
        verifyNodeTestListing(listing.output)
        nodeRuntimeTestMethods.forEach { method ->
            val result = capture(
                method,
                listOf(
                    nodeExecutable,
                    runnerEntry.absolutePath,
                    "--run-test=$NODE_RUNTIME_TEST_CLASS.$method",
                ),
                environment,
            )
            check(result.exitCode == 0) { "Node runtime test failed ($method): ${result.output}" }
        }
        val evidence = buildNodeRuntimeEvidence(NodeRuntimeEvidenceValues(
            candidateCommit,
            target,
            runtimeBackend,
            classifier,
            compiledNodeTestRuntime,
        ))
        writeNodeRuntimeTestReport(testReport)
        verifyNodeRuntimeTestReport(testReport)
        evidenceFile.atomicWriteJson(evidence)
    } catch (error: Throwable) {
        evidenceFile.delete()
        testReport.delete()
        throw error
    } finally {
        temporary.deleteRecursively()
    }
}

private fun extractNodeRuntimeRunner(archive: File, runtimeBackend: String, destination: File): File {
    val members = inspectNodeRuntimeRunnerArchive(archive, runtimeBackend)
    destination.mkdirs()
    ZipFile(archive).use { zip ->
        members.forEach { name ->
            zip.getInputStream(zip.getEntry(name)).use { input ->
                Files.copy(input, destination.resolve(name).toPath(), REPLACE_EXISTING)
            }
        }
    }
    return destination.resolve(nodeRuntimeRunnerEntry(runtimeBackend))
}

internal fun verifyNodeTestListing(output: String) {
    val actual = output.replace("\r", "").lineSequence().filter(String::isNotBlank).toList()
    val expected = listOf("$NODE_RUNTIME_TEST_CLASS.") + nodeRuntimeTestMethods.map { "  $it" }
    check(actual == expected) { "Node test inventory is incomplete or unexpected" }
}

internal fun verifyNodeRuntimeTestReport(file: File) {
    verifyRuntimeEvidenceTestReport(file, NODE_RUNTIME_TEST_CLASS, nodeRuntimeTestMethods)
}

private fun writeNodeRuntimeTestReport(file: File) {
    writeRuntimeEvidenceTestReport(file, NODE_RUNTIME_TEST_CLASS, nodeRuntimeTestMethods)
}

internal fun runNodeEvidenceProcess(
    command: List<String>,
    environment: Map<String, String>,
): NodeEvidenceProcessResult {
    val log = Files.createTempFile("node-runtime-evidence", ".log").toFile()
    return try {
        val process = ProcessBuilder(command)
            .redirectErrorStream(true)
            .redirectOutput(log)
            .useRuntimeEvidenceEnvironment(environment)
            .start()
        val completed = process.waitFor(5, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        val raw = log.readBytes()
        NodeEvidenceProcessResult(if (completed) process.exitValue() else -1, raw.toString(Charsets.UTF_8), raw)
    } finally {
        log.delete()
    }
}
