import java.nio.ByteBuffer
import java.nio.file.FileVisitResult
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.SimpleFileVisitor
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

@CacheableTask
abstract class GenerateRuntimeAbiSourceTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val runtimeBinaryPlan: RegularFileProperty

    @get:Input
    abstract val repositoryRevision: Property<String>

    @get:Input
    abstract val expectedTarget: Property<String>

    @get:Input
    abstract val runtimeVersion: Property<String>

    @get:Input
    abstract val expectedFlagsDigest: Property<String>

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val verifiedContractManifest: RegularFileProperty

    @get:Internal
    abstract val repositoryRoot: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val abiContractFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val reviewedHeaderFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val macosExportsFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val linuxMapFile: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val windowsDefFile: RegularFileProperty

    @get:OutputDirectory
    abstract val outputDirectory: DirectoryProperty

    private fun readUtf8(path: java.nio.file.Path): String {
        val bytes = Files.readAllBytes(path)
        check(bytes.size <= 64 * 1024) { "Verified Runtime identity envelope is too large" }
        return Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString()
    }

    private fun verifyRuntimeIdentity(contract: RuntimeAbiContract): String {
        val root = repositoryRoot.get().asFile.canonicalFile
        check(root.isDirectory) { "Runtime identity repository root is missing" }
        val revision = repositoryRevision.get()
        check(Regex("[0-9a-f]{40}|[0-9a-f]{64}").matches(revision)) {
            "Runtime identity repository revision must be an exact lowercase object ID"
        }
        val identityOutput = temporaryDir.resolve("runtime-identity.json").toPath()
        val log = temporaryDir.resolve("runtime-identity.log").toPath()
        Files.deleteIfExists(identityOutput)
        Files.deleteIfExists(log)
        try {
            val process = ProcessBuilder(
                "python3", "-m", "ci.products.runtime_identity",
                "--plan", runtimeBinaryPlan.get().asFile.absolutePath,
                "--repository-root", root.absolutePath,
                "--repository-revision", revision,
                "--verified-contract-manifest", verifiedContractManifest.get().asFile.absolutePath,
                "--expected-target", expectedTarget.get(),
                "--expected-runtime-version", runtimeVersion.get(),
                "--expected-flags-digest", expectedFlagsDigest.get(),
                "--output", identityOutput.toFile().absolutePath,
            )
                .directory(root)
                .redirectErrorStream(true)
                .redirectOutput(log.toFile())
                .apply {
                    environment().keys.removeIf { it.startsWith("PYTHON") }
                    environment()["PYTHONPATH"] = root.absolutePath
                    environment()["PYTHONDONTWRITEBYTECODE"] = "1"
                    environment()["PYTHONNOUSERSITE"] = "1"
                    environment()["PYTHONSAFEPATH"] = "1"
                    environment()["LC_ALL"] = "C"
                    environment()["LANG"] = "C"
                }
                .start()
            process.outputStream.close()
            val completed = process.waitFor(10, TimeUnit.MINUTES)
            if (!completed) process.destroyForcibly().waitFor()
            val diagnostic = if (Files.exists(log)) readUtf8(log).trim() else ""
            check(completed && process.exitValue() == 0) {
                "ci.products.runtime_identity failed " +
                    "(${if (completed) process.exitValue() else "timeout"}): $diagnostic"
            }
            check(Files.isRegularFile(identityOutput, LinkOption.NOFOLLOW_LINKS)) {
                "Verified Runtime identity envelope is missing or unsafe"
            }
            return validateRuntimeIdentityEnvelope(readUtf8(identityOutput), contract)
        } finally {
            Files.deleteIfExists(identityOutput)
            Files.deleteIfExists(log)
        }
    }

    private fun validateRuntimeIdentityEnvelope(output: String, contract: RuntimeAbiContract): String {
        val root = parseRuntimeCAbiCanonicalObject(output, "Runtime binary identity envelope")
        root.requireKeys(
            "schemaVersion", "binaryBuildKey", "runtimeCompatibilityVersion", "target",
            "contract", "cAbi", "appServer", "toolchainProfile", "componentId",
            "runtimeIdentityJson",
        )
        check(root.strictInt("schemaVersion") == 1) { "Runtime binary identity schemaVersion must be 1" }
        val sha256 = Regex("sha256:[0-9a-f]{64}")
        fun JsonObject.digest(name: String): String = strictString(name).also {
            check(sha256.matches(it)) { "Runtime binary identity $name must be a canonical SHA-256" }
        }
        val buildKey = root.digest("binaryBuildKey")
        val compatibility = root.strictString("runtimeCompatibilityVersion")
        check(Regex("(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.0").matches(compatibility)) {
            "Runtime binary compatibility version must be MAJOR.MINOR.0"
        }
        val target = root.strictString("target")
        check(target in setOf("macos-arm64", "macos-x64", "linux-arm64", "linux-x64", "windows-x64")) {
            "Runtime binary identity target is unsupported"
        }
        check(target == expectedTarget.get()) { "Runtime binary identity target differs from the requested target" }
        val contractIdentity = root.strictObject("contract").also {
            it.requireKeys("digest", "componentDigest")
            it.digest("digest")
            it.digest("componentDigest")
        }
        val cAbi = root.strictObject("cAbi").also {
            it.requireKeys(
                "version", "minimumCompatibleVersion", "identitySchemaVersion", "headerSha256",
                "symbolSetSha256", "symbolCount",
            )
            check(it.strictString("version") == contract.currentSemver) {
                "Runtime identity C ABI current version differs from the verified ABI contract"
            }
            check(it.strictString("minimumCompatibleVersion") == contract.minimumCompatibleSemver) {
                "Runtime identity C ABI minimum version differs from the verified ABI contract"
            }
            check(it.strictInt("identitySchemaVersion") == contract.runtimeIdentitySchemaVersion) {
                "Runtime identity schema differs from the verified ABI contract"
            }
            it.digest("headerSha256")
            it.digest("symbolSetSha256")
            check(it.strictInt("symbolCount") > 0) { "Runtime identity C ABI symbol count must be positive" }
        }
        val appServer = root.strictObject("appServer").also {
            it.requireKeys("version", "releaseTag", "binarySha256")
            val version = it.strictString("version")
            check(it.strictString("releaseTag") == "rust-v$version") {
                "Runtime identity app-server tag/version mismatch"
            }
            it.digest("binarySha256")
        }
        root.strictObject("toolchainProfile").also {
            it.requireKeys("id", "digest")
            check(it.strictString("id") == target) { "Runtime identity toolchain profile/target mismatch" }
            it.digest("digest")
        }
        val componentId = root.digest("componentId")
        val identityText = root.strictString("runtimeIdentityJson")
        check('\n' !in identityText && '\r' !in identityText) {
            "Runtime identity JSON must not contain a line terminator"
        }
        val identity = Json.parseToJsonElement(identityText) as? JsonObject
            ?: error("Runtime identity JSON must be an object")
        check(identity.toString() == identityText) { "Runtime identity JSON bytes are not canonical" }
        identity.requireKeys(
            "appServerVersion", "buildInputDigest", "cAbiVersion", "componentId",
            "contractComponentDigest", "contractDigest", "runtimeCompatibilityVersion",
            "schemaVersion", "target",
        )
        check(identity.strictString("appServerVersion") == appServer.strictString("version"))
        check(identity.strictString("buildInputDigest") == buildKey)
        check(identity.strictString("cAbiVersion") == cAbi.strictString("version"))
        check(identity.strictString("componentId") == componentId)
        check(identity.strictString("contractComponentDigest") == contractIdentity.strictString("componentDigest"))
        check(identity.strictString("contractDigest") == contractIdentity.strictString("digest"))
        check(identity.strictString("runtimeCompatibilityVersion") == compatibility)
        check(identity.strictInt("schemaVersion") == cAbi.strictInt("identitySchemaVersion"))
        check(identity.strictString("target") == target)
        return identityText
    }

    private fun deleteOutputTree(root: Path) {
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS)) return
        check(!Files.isSymbolicLink(root)) { "Runtime ABI generated output directory must not be symbolic" }
        Files.walkFileTree(
            root,
            object : SimpleFileVisitor<Path>() {
                override fun visitFile(file: Path, attributes: BasicFileAttributes): FileVisitResult {
                    Files.delete(file)
                    return FileVisitResult.CONTINUE
                }

                override fun postVisitDirectory(directory: Path, error: java.io.IOException?): FileVisitResult {
                    if (error != null) throw error
                    Files.delete(directory)
                    return FileVisitResult.CONTINUE
                }
            },
        )
    }

    @TaskAction
    fun generate() {
        val outputRoot = outputDirectory.get().asFile.toPath()
        val output = outputRoot.resolve(
            "io/github/codex_agent_labs/codexagent/capi/RuntimeAbi.generated.kt",
        ).toFile()
        deleteOutputTree(outputRoot)
        try {
            runRuntimeProductPythonModule(
            "c_abi",
            listOf(
                "verify-abi-contract",
                "--abi-contract", abiContractFile.get().asFile.absolutePath,
                "--header", reviewedHeaderFile.get().asFile.absolutePath,
                "--macos-exports", macosExportsFile.get().asFile.absolutePath,
                "--linux-map", linuxMapFile.get().asFile.absolutePath,
                "--windows-def", windowsDefFile.get().asFile.absolutePath,
            ),
        )
            val contract = readRuntimeAbiContract(
            runRuntimeProductPythonModule(
                "c_abi",
                listOf(
                    "describe-abi-contract",
                    "--abi-contract",
                    abiContractFile.get().asFile.absolutePath,
                ),
            ),
        )
            val runtimeIdentityJson = verifyRuntimeIdentity(contract)
            fun literal(encoded: String): String = "0x${encoded.removePrefix("0x").uppercase()}u"
            val source = buildString {
            appendLine("package io.github.codex_agent_labs.codexagent.capi")
            appendLine()
            appendLine(
                "internal const val GENERATED_ABI_VERSION_CURRENT: UInt = ${literal(contract.currentEncoded)}",
            )
            appendLine(
                "internal const val GENERATED_ABI_VERSION_MINIMUM_COMPATIBLE: UInt = " +
                    literal(contract.minimumCompatibleEncoded),
            )
            appendLine(
                "internal const val GENERATED_RUNTIME_IDENTITY_SCHEMA_VERSION: Int = " +
                    contract.runtimeIdentitySchemaVersion,
            )
            appendLine(
                "internal const val GENERATED_RUNTIME_IDENTITY_JSON: String = " +
                    JsonPrimitive(runtimeIdentityJson),
            )
            }
            output.parentFile.mkdirs()
            output.writeText(source, Charsets.UTF_8)
        } catch (error: Throwable) {
            deleteOutputTree(outputRoot)
            throw error
        }
    }
}
