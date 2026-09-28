import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.Task
import org.gradle.api.Project
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ValueSource
import org.gradle.api.provider.ValueSourceParameters
import org.gradle.api.tasks.Exec
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskProvider
import org.gradle.kotlin.dsl.register
import org.jetbrains.kotlin.gradle.plugin.mpp.KotlinNativeTarget

private val runtimeBinaryFlagTargets = listOf(
    "linux-arm64", "linux-x64", "macos-arm64", "macos-x64", "windows-x64",
)
private val runtimeBinaryRoleToken = Regex("@role\\(([A-Za-z][A-Za-z0-9]*)\\)")

data class RuntimeBinaryFlagRole(val name: String, val base: String, val relativePath: String)

data class RuntimeBinaryMsvcOption(val name: String, val value: String?)

data class RuntimeBinaryFlags(
    val target: String,
    val compilerArguments: List<String>,
    val supervisorCompilerArguments: List<String>,
    val linkerArguments: List<String>,
    val msvcImportLibraryOptions: List<RuntimeBinaryMsvcOption>,
    val roles: Map<String, RuntimeBinaryFlagRole>,
    val flagsDigest: String,
) {
    fun roleFile(name: String, repositoryRoot: File, outputRoot: File): File {
        val role = roles.getValue(name)
        val base = when (role.base) {
            "repository" -> repositoryRoot
            "output" -> outputRoot
            else -> error("Unsupported Runtime binary flag role base: ${role.base}")
        }.canonicalFile
        val unresolved = base.resolve(role.relativePath)
        var member = base.toPath()
        role.relativePath.split('/').forEach { segment ->
            member = member.resolve(segment)
            check(!Files.isSymbolicLink(member)) { "Runtime binary flag role contains a symbolic path: $name" }
        }
        val resolved = unresolved.canonicalFile
        check(resolved.toPath().startsWith(base.toPath())) { "Runtime binary flag role escapes its base: $name" }
        if (role.base == "repository") {
            check(resolved.isFile) {
                "Runtime binary flag repository role is not a regular nonsymbolic file: $name"
            }
        }
        return resolved
    }

    fun resolve(value: String, repositoryRoot: File, outputRoot: File): String {
        val resolved = runtimeBinaryRoleToken.replace(value) { match ->
            roleFile(match.groupValues[1], repositoryRoot, outputRoot).absolutePath
        }
        check("@role(" !in resolved) { "Unresolved Runtime binary flag role: $value" }
        return resolved
    }

    fun resolvedLinkerArguments(repositoryRoot: File, outputRoot: File): List<String> =
        linkerArguments.map { resolve(it, repositoryRoot, outputRoot) }

    fun resolvedMsvcOptions(repositoryRoot: File, outputRoot: File): List<String> =
        msvcImportLibraryOptions.map { option ->
            "/${option.name}" + (option.value?.let { ":${resolve(it, repositoryRoot, outputRoot)}" } ?: "")
        }
}

interface RuntimeBinaryFlagsValueSourceParameters : ValueSourceParameters {
    val flagsFile: RegularFileProperty
}

abstract class RuntimeBinaryFlagsValueSource : ValueSource<String, RuntimeBinaryFlagsValueSourceParameters> {
    override fun obtain(): String = runRuntimeProductPythonModule(
        "runtime_flags",
        listOf("describe-all", "--file", parameters.flagsFile.get().asFile.absolutePath),
    )
}

fun readRuntimeBinaryFlags(output: String): Map<String, RuntimeBinaryFlags> {
    val root = parseRuntimeCAbiCanonicalObject(output, "Runtime binary flags")
    root.requireKeys("schemaVersion", "targets")
    check(root.strictInt("schemaVersion") == 1) { "Runtime binary flags schemaVersion must be 1" }
    val records = root.strictArray("targets").mapIndexed { index, element ->
        val record = element as? JsonObject ?: error("Runtime binary flags targets[$index] must be an object")
        record.requireKeys(
            "schemaVersion", "target", "compilerArguments", "supervisorCompilerArguments", "linkerArguments",
            "msvcImportLibraryOptions", "roles", "flagsDigest",
        )
        check(record.strictInt("schemaVersion") == 1) { "Runtime binary flags target schemaVersion must be 1" }
        val target = record.strictString("target")
        val roles = record.strictArray("roles").mapIndexed { roleIndex, roleElement ->
            val role = roleElement as? JsonObject
                ?: error("Runtime binary flags $target roles[$roleIndex] must be an object")
            role.requireKeys("base", "name", "relativePath")
            RuntimeBinaryFlagRole(
                role.strictString("name"),
                role.strictString("base"),
                role.strictString("relativePath"),
            )
        }
        check(roles.map { it.name } == roles.map { it.name }.sorted() && roles.map { it.name }.distinct().size == roles.size) {
            "Runtime binary flags $target roles must be sorted and unique"
        }
        val msvc = record.strictArray("msvcImportLibraryOptions").mapIndexed { optionIndex, optionElement ->
            val option = optionElement as? JsonObject
                ?: error("Runtime binary flags $target msvcImportLibraryOptions[$optionIndex] must be an object")
            option.requireKeys("name", "value")
            val value = option.getValue("value")
            RuntimeBinaryMsvcOption(
                option.strictString("name"),
                when (value) {
                    JsonNull -> null
                    is JsonPrimitive -> {
                        check(value.isString) { "Runtime binary flags MSVC option value must be a string or null" }
                        value.content
                    }
                    else -> error("Runtime binary flags MSVC option value must be a string or null")
                },
            )
        }
        RuntimeBinaryFlags(
            target,
            record.strictStringList("compilerArguments"),
            record.strictStringList("supervisorCompilerArguments"),
            record.strictStringList("linkerArguments"),
            msvc,
            roles.associateBy { it.name },
            record.strictString("flagsDigest"),
        )
    }
    check(records.map { it.target } == runtimeBinaryFlagTargets) {
        "Runtime binary flags must contain the exact sorted five-target set"
    }
    return records.associateBy { it.target }
}

fun verifyRuntimeBinaryFlagsAgainstAbi(
    records: Map<String, RuntimeBinaryFlags>,
    contract: RuntimeAbiContract,
) {
    check(records.keys == runtimeBinaryFlagTargets.toSet()) { "Runtime binary flags target inventory mismatch" }
    records.values.forEach { check(it.compilerArguments.isEmpty()) { "Runtime compiler flags are not yet supported" } }
    listOf("macos-arm64", "macos-x64").forEach { target ->
        val arguments = records.getValue(target).linkerArguments
        check("-Wl,-compatibility_version,${contract.minimumCompatibleSemver}" in arguments)
        check("-Wl,-current_version,${contract.currentSemver}" in arguments)
    }
}

fun verifyRuntimeBinaryFlagsAgainstPlan(
    records: Map<String, RuntimeBinaryFlags>,
    target: String,
    expectedDigest: String,
) {
    check(Regex("sha256:[0-9a-f]{64}").matches(expectedDigest)) {
        "Planned Runtime binary flags digest is invalid"
    }
    check(records.getValue(target).flagsDigest == expectedDigest) {
        "Checked-out Runtime binary flags do not match the planned digest for $target"
    }
}

fun Project.registerRuntimeProducerToolchainObserver(
    runtimeBinaryFlags: Map<String, RuntimeBinaryFlags>,
): TaskProvider<out Task>? {
    val requestedRuntimeTarget = providers.gradleProperty("codexAgent.target").get()
    val requestedRuntimePhase = providers.gradleProperty("codexAgent.phase").orNull
    if (requestedRuntimeTarget in runtimeBinaryFlags) {
        when (requestedRuntimePhase) {
            "package" -> require(providers.gradleProperty("codexAgent.runtimeBinaryStage").isPresent) {
                "Native Runtime package phase requires codexAgent.runtimeBinaryStage"
            }
            "validation" -> require(providers.gradleProperty("codexAgent.runtimePackageStage").isPresent) {
                "Native Runtime $requestedRuntimePhase phase requires codexAgent.runtimePackageStage"
            }
        }
    }
    if (requestedRuntimeTarget in runtimeBinaryFlags) {
        require(gradle.startParameter.excludedTaskNames.isEmpty()) {
            "Native Runtime binary producer verification rejects excluded tasks"
        }
    }
    if (requestedRuntimeTarget in runtimeBinaryFlags &&
        (requestedRuntimePhase == null || requestedRuntimePhase == "binary")
    ) {
        verifyRuntimeBinaryFlagsAgainstPlan(
            runtimeBinaryFlags,
            requestedRuntimeTarget,
            providers.gradleProperty("codexAgent.runtimeBinaryFlagsDigest").get(),
        )
    }
    val repositoryRootFile = rootProject.extensions.extraProperties.get("codexAgent.repositoryRoot") as File
    val verifiedContractManifestFile = layout.file(providers.provider {
        rootProject.extensions.extraProperties.get("codexAgent.verifiedContractManifest") as File
    })
    val runtimeProductVersion = providers.provider { version.toString() }
    return if (requestedRuntimeTarget in runtimeBinaryFlags &&
        (requestedRuntimePhase == null || requestedRuntimePhase == "binary")
    ) {
        val runnerOs = when {
            System.getProperty("os.name") == "Mac OS X" -> "macOS"
            System.getProperty("os.name") == "Linux" -> "Linux"
            System.getProperty("os.name").startsWith("Windows") -> "Windows"
            else -> error("Unsupported Runtime producer operating system: ${System.getProperty("os.name")}")
        }
        val runnerArch = when (System.getProperty("os.arch")) {
            "aarch64", "arm64" -> "ARM64"
            "amd64", "x86_64" -> "X64"
            else -> error("Unsupported Runtime producer architecture: ${System.getProperty("os.arch")}")
        }
        val supervisorOnly = requestedRuntimePhase == null &&
            gradle.startParameter.taskNames.size == 1 &&
            gradle.startParameter.taskNames.single().substringAfterLast(':') ==
            "compileDesktopProcessSupervisor"
        val producerRole = when {
            requestedRuntimeTarget == "linux-arm64" && supervisorOnly -> "supervisor-builder"
            requestedRuntimeTarget == "linux-arm64" -> "cross-builder"
            else -> "builder"
        }
        tasks.register<Exec>("verifyRuntimeProducerToolchain") {
            group = "verification"
            description = "Observes and verifies the actual Runtime binary producer before compilation."
            val output = layout.buildDirectory.file(
                "toolchain-verification/$requestedRuntimeTarget-$producerRole.json",
            )
            inputs.file(providers.gradleProperty("codexAgent.runtimeBinaryPlan").map(::File))
                .withPathSensitivity(PathSensitivity.NONE)
            inputs.file(verifiedContractManifestFile).withPathSensitivity(PathSensitivity.NONE)
            inputs.property("repositoryRevision", providers.gradleProperty("codexAgent.repositoryRevision"))
            inputs.property("runtimeVersion", runtimeProductVersion)
            inputs.property("runtimeBinaryFlagsDigest", providers.gradleProperty("codexAgent.runtimeBinaryFlagsDigest"))
            inputs.property("runnerOs", runnerOs)
            inputs.property("runnerArch", runnerArch)
            inputs.property("producerRole", producerRole)
            outputs.file(output)
            outputs.upToDateWhen { false }
            workingDir(repositoryRootFile)
            environment(environment.toMutableMap().apply {
                remove("PYTHONHOME")
                remove("PYTHONINSPECT")
                remove("PYTHONSTARTUP")
                put("PYTHONPATH", repositoryRootFile.absolutePath)
                put("PYTHONDONTWRITEBYTECODE", "1")
                put("PYTHONNOUSERSITE", "1")
                put("PYTHONSAFEPATH", "1")
                put("LC_ALL", "C")
                put("LANG", "C")
                put("RUNNER_OS", runnerOs)
                put("RUNNER_ARCH", runnerArch)
            })
            val command = mutableListOf(
                "python3", "-m", "ci.products.toolchain", "verify-producer",
                "--repository-root", repositoryRootFile.absolutePath,
                "--repository-revision", providers.gradleProperty("codexAgent.repositoryRevision").get(),
                "--profile-id", requestedRuntimeTarget,
                "--producer-role", producerRole,
                "--target", requestedRuntimeTarget,
                "--gradle-user-home", gradle.gradleUserHomeDir.absolutePath,
                "--binary-plan", providers.gradleProperty("codexAgent.runtimeBinaryPlan").get(),
                "--verified-contract-manifest", verifiedContractManifestFile.get().asFile.absolutePath,
                "--expected-runtime-version", runtimeProductVersion.get(),
                "--expected-flags-digest", providers.gradleProperty("codexAgent.runtimeBinaryFlagsDigest").get(),
                "--output", output.get().asFile.absolutePath,
            )
            providers.gradleProperty("codexAgent.desktopSupervisorCompiler").orNull?.let {
                command += listOf("--supervisor-compiler", it)
            }
            providers.gradleProperty("codexAgent.kotlinPluginJar").orNull?.let {
                command += listOf("--kotlin-plugin-jar", it)
            }
            providers.gradleProperty("codexAgent.nativeArchive").orNull?.let {
                command += listOf("--native-archive", it)
            }
            commandLine(command)
        }
    } else if (requestedRuntimeTarget in runtimeBinaryFlags) {
        tasks.register("verifyRuntimeProducerToolchain") {
            group = "verification"
            description = "Rejects Runtime product compilation during an artifact-only phase."
            doLast {
                error("Native Runtime product compilation requires the binary phase, not an explicit artifact-only phase")
            }
        }
    } else {
        null
    }
}

fun KotlinNativeTarget.verifyRuntimeProducerBeforeCompilation(verification: TaskProvider<out Task>?) {
    compilations.configureEach {
        compileTaskProvider.configure {
            verification?.let { dependsOn(it) }
        }
    }
}
