import java.io.File
import java.time.LocalDateTime
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream
import kotlin.io.path.createTempDirectory
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray

internal const val NODE_EVIDENCE_COMMIT = "0123456789abcdef0123456789abcdef01234567"
internal val NODE_EVIDENCE_ARM_ENV = mapOf("RUNNER_OS" to "Linux", "RUNNER_ARCH" to "ARM64")

internal fun writeTestDesktopDistributionManifest(file: File, binarySha256: String): File = file.apply {
    atomicWriteJson(buildJsonObject {
        put("version", JsonPrimitive("0.145.0"))
        put("releaseTag", JsonPrimitive("rust-v0.145.0"))
        put("distributions", buildJsonArray {
            desktopRuntimeEvidenceTargets.forEach { (target, evidence) ->
                add(buildJsonObject {
                    put("target", JsonPrimitive(target))
                    put("classifier", JsonPrimitive(evidence.classifier))
                    put("asset", JsonPrimitive("$target.tar.gz"))
                    put("archiveSha256", JsonPrimitive("a".repeat(64)))
                    put("archiveEntry", JsonPrimitive("codex-app-server"))
                    put("binarySha256", JsonPrimitive(binarySha256))
                    put("executableName", JsonPrimitive(if (target == "mingwX64") "codex-app-server.exe" else "codex-app-server"))
                    put("supervisorExecutableName", JsonPrimitive(
                        if (target == "mingwX64") "codex-process-supervisor.exe" else "codex-process-supervisor",
                    ))
                })
            }
        })
    })
}

internal fun runtimeManifestFixture(
    libraryVersion: String,
    target: String,
    classifier: String,
    payload: Map<String, ByteArray>,
    executables: Set<String>,
): ByteArray = buildJsonObject {
    put("schemaVersion", 1)
    put("libraryVersion", libraryVersion)
    put("appServerVersion", "0.145.0")
    put("target", target)
    put("classifier", classifier)
    putJsonArray("members") {
        payload.forEach { (name, bytes) ->
            add(buildJsonObject {
                put("name", name)
                put("size", bytes.size)
                put("sha256", bytes.inputStream().releaseDigest())
                put("executable", name in executables)
            })
        }
    }
}.toString().encodeToByteArray()

internal fun assertRuntimeBundleEnvironment(environment: Map<String, String>, target: String) {
    assertEquals(
        setOf(
            RUNTIME_BUNDLE_DIRECTORY_ENV,
            RUNTIME_DATA_DIRECTORY_ENV,
            RUNTIME_WORKSPACE_ENV,
            "CODEX_HOME",
            "CODEX_SQLITE_HOME",
            "CODEX_AGENT_DESKTOP_TARGET",
        ),
        environment.keys,
    )
    assertEquals(target, environment["CODEX_AGENT_DESKTOP_TARGET"])
    val bundle = File(environment.getValue(RUNTIME_BUNDLE_DIRECTORY_ENV))
    assertTrue(bundle.isDirectory)
    val data = File(environment.getValue(RUNTIME_DATA_DIRECTORY_ENV))
    assertTrue(data.isDirectory)
    assertEquals(data.absolutePath, environment["CODEX_HOME"])
    assertEquals(data.absolutePath, environment["CODEX_SQLITE_HOME"])
    assertTrue(File(environment.getValue(RUNTIME_WORKSPACE_ENV)).isDirectory)
    assertTrue(
        bundle.resolve(
            "codex-agent-runtime-desktop-0.2.0-${desktopRuntimeEvidenceTargets.getValue(target).classifier}.zip",
        ).isFile,
    )
}

internal class NodeRuntimeEvidenceFixture(val root: File) {
    private val appServer = "official app server".encodeToByteArray()
    private val embeddedSupervisor = "embedded process supervisor".encodeToByteArray()
    val manifest = writeTestDesktopDistributionManifest(
        root.resolve("codex-app-server-distributions.json"),
        appServer.inputStream().releaseDigest(),
    )
    val compiled = root.resolve(NODE_RUNTIME_RUNNER_ARCHIVE).apply {
        nodeEvidenceWriteZip(linkedMapOf(
            NODE_RUNTIME_RUNNER_ENTRY to "compiled Node entry".encodeToByteArray(),
            "kotlin-kotlin-stdlib.js" to "compiled Kotlin dependency".encodeToByteArray(),
        ))
    }
    val compiledWasm = root.resolve(NODE_WASM_RUNTIME_RUNNER_ARCHIVE).apply {
        nodeEvidenceWriteZip(nodeWasmRuntimeRunnerEntries.associateWith { "compiled $it".encodeToByteArray() })
    }
    val classifiers = desktopRuntimeEvidenceTargets.mapValues { (target, spec) ->
        root.resolve("codex-agent-runtime-desktop-0.2.0-${spec.classifier}.zip").apply {
            val executable = if (target == "mingwX64") "codex-app-server.exe" else "codex-app-server"
            val supervisor = if (target == "mingwX64") {
                "codex-process-supervisor.exe"
            } else {
                "codex-process-supervisor"
            }
            val payload = linkedMapOf(
                executable to appServer,
                supervisor to embeddedSupervisor,
                "openai-codex-LICENSE.txt" to "license".encodeToByteArray(),
                "openai-codex-NOTICE.txt" to "notice".encodeToByteArray(),
            )
            nodeEvidenceWriteZip(payload + ("codex-runtime-manifest.json" to runtimeManifestFixture(
                "0.2.0", target, spec.classifier, payload, setOf(executable, supervisor),
            )))
        }
    }

    fun runnerArchive(runtimeBackend: String) =
        if (runtimeBackend == NODE_RUNTIME_JS_BACKEND) compiled else compiledWasm

    fun evidence(target: String, runtimeBackend: String = NODE_RUNTIME_JS_BACKEND) =
        root.resolve(nodeRuntimeEvidenceFileName(target, runtimeBackend))

    fun report(target: String, runtimeBackend: String = NODE_RUNTIME_JS_BACKEND) =
        root.resolve(nodeRuntimeTestReportFileName(target, runtimeBackend))

    fun record(
        target: String,
        runtimeBackend: String = NODE_RUNTIME_JS_BACKEND,
        runner: (List<String>, Map<String, String>) -> NodeEvidenceProcessResult = { command, _ ->
            successfulNodeEvidenceResult(command)
        },
    ) {
        val expected = desktopRuntimeEvidenceTargets.getValue(target)
        executeNodeRuntimeEvidence(
            NODE_EVIDENCE_COMMIT,
            target,
            runtimeBackend,
            expected.runnerOs,
            expected.runnerArch,
            "node",
            manifest,
            classifiers.getValue(target),
            runnerArchive(runtimeBackend),
            evidence(target, runtimeBackend),
            report(target, runtimeBackend),
            runner = runner,
        )
    }

    fun recordAll(runtimeBackend: String = NODE_RUNTIME_JS_BACKEND) =
        desktopRuntimeEvidenceTargets.keys.forEach { record(it, runtimeBackend) }

    fun validate(
        runtimeBackend: String = NODE_RUNTIME_JS_BACKEND,
        evidenceFiles: List<File> = desktopRuntimeEvidenceTargets.keys.map { evidence(it, runtimeBackend) },
        classifierFiles: List<File> = classifiers.values.toList(),
        compiledFile: File = runnerArchive(runtimeBackend),
    ) = validateNodeRuntimeEvidence(
        evidenceFiles,
        NODE_EVIDENCE_COMMIT,
        runtimeBackend,
        manifest,
        classifierFiles,
        compiledFile,
    )
}

internal fun withNodeRuntimeEvidenceFixture(block: (NodeRuntimeEvidenceFixture) -> Unit) {
    val root = createTempDirectory("node-runtime-evidence").toFile()
    try { block(NodeRuntimeEvidenceFixture(root)) } finally { root.deleteRecursively() }
}

internal fun exactNodeEvidenceListing() = buildString {
    append(NODE_RUNTIME_TEST_CLASS).append(".\n")
    nodeRuntimeTestMethods.forEach { append("  ").append(it).append('\n') }
}

internal fun successfulNodeEvidenceResult(command: List<String>) = when (command.last()) {
    "--version" -> NodeEvidenceProcessResult(0, "v$PINNED_NODE_VERSION\n")
    "--list-tests" -> NodeEvidenceProcessResult(0, exactNodeEvidenceListing())
    else -> NodeEvidenceProcessResult(0, "")
}

internal fun File.nodeEvidenceZipEntries(): LinkedHashMap<String, ByteArray> = ZipFile(this).use { zip ->
    linkedMapOf<String, ByteArray>().apply {
        zip.entries().asSequence().forEach { entry ->
            put(entry.name, zip.getInputStream(entry).use { it.readBytes() })
        }
    }
}

internal fun File.nodeEvidenceWriteZip(entries: Map<String, ByteArray>) =
    ZipOutputStream(outputStream()).use { zip ->
        entries.forEach { (name, bytes) ->
            zip.putNextEntry(ZipEntry(name).apply {
                setTimeLocal(LocalDateTime.of(1980, 1, 1, 0, 0))
            })
            zip.write(bytes)
            zip.closeEntry()
        }
    }
