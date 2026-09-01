import java.io.File
import java.nio.file.Files
import java.util.concurrent.TimeUnit
import org.gradle.api.DefaultTask
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.MapProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

fun crossLanguageCAbiLinuxDynamicSymbolVersions(
    output: String,
    expectedVersions: Map<String, String>,
): Map<String, String> {
    val actualSymbols = normalizedCAbiSymbols(output)
    val assignments = linkedMapOf<String, String>()
    LINUX_DYNAMIC_VERSIONED_SYMBOL.findAll(output).forEach { match ->
        val symbol = match.groupValues[1].removePrefix("_")
        check(assignments.put(symbol, match.groupValues[2]) == null) {
            "Duplicate C ABI dynamic symbol version: $symbol"
        }
    }
    check(actualSymbols == expectedVersions.keys && assignments.toSortedMap() == expectedVersions.toSortedMap()) {
        "C ABI Linux dynamic symbols are missing, extra, duplicated, unversioned, or assigned to the wrong node"
    }
    return assignments.toSortedMap()
}


@CacheableTask
abstract class PackageCrossLanguageCAbiSdkTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val library: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFile @get:org.gradle.api.tasks.Optional @get:PathSensitive(PathSensitivity.NONE)
    abstract val gnuImportLibrary: RegularFileProperty
    @get:InputFile @get:org.gradle.api.tasks.Optional @get:PathSensitive(PathSensitivity.NONE)
    abstract val msvcImportLibrary: RegularFileProperty
    @get:OutputFile abstract val outputFile: RegularFileProperty

    @TaskAction
    fun packageSdk() {
        packageCrossLanguageCAbiSdk(packageInput(), outputFile.get().asFile)
    }

    fun packageInput() = CrossLanguageCAbiPackageInput(
        target.get(), classifier.get(), libraryVersion.get(), producerCommit.get(), producerTree.get(),
        reviewedHeader.get().asFile, license.get().asFile, notice.get().asFile, library.get().asFile,
        exportPolicy.get().asFile, gnuImportLibrary.orNull?.asFile, msvcImportLibrary.orNull?.asFile,
    )
}

@DisableCachingByDefault(because = "Compiles, links, and executes strict C ABI consumers with the target runner toolchain")
abstract class GenerateCrossLanguageCAbiPackageEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:Input abstract val runnerOs: Property<String>
    @get:Input abstract val runnerArch: Property<String>
    @get:Input abstract val tools: MapProperty<String, String>
    @get:Input abstract val compileOnlyConsumers: ListProperty<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val consumerSources: ConfigurableFileCollection
    @get:OutputFile abstract val evidenceFile: RegularFileProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun generateEvidence() {
        evidenceFile.get().asFile.delete()
        val spec = checkedCAbiTarget(target.get(), classifier.get())
        check(runnerOs.get() == spec.runnerOs && runnerArch.get() == spec.runnerArch) {
            "C ABI package evidence runner mismatch"
        }
        val toolMap = tools.get()
        check(toolMap.keys == spec.requiredToolIds() && toolMap.values.all(::safeToolExecutable)) {
            "C ABI package evidence tool inventory mismatch"
        }
        val sources = consumerSources.files.sortedBy(File::getName)
        check(sources.all(::regularCAbiFile) && sources.map(File::getName).toSet() == crossLanguageCAbiStrictConsumers &&
            sources.size == crossLanguageCAbiStrictConsumers.size) {
            "C ABI strict consumer sources are missing or duplicated"
        }
        val compileOnly = compileOnlyConsumers.get().toSet()
        check(compileOnly == sources.map(File::getName).toSet().intersect(crossLanguageCAbiCompileOnlyConsumers)) {
            "C ABI compile-only consumer inventory mismatch"
        }
        val temporary = Files.createTempDirectory("codex-agent-c-abi-${spec.target}-").toFile()
        try {
            val root = temporary.resolve("sdk")
            val snapshot = inspectAndStageCrossLanguageCAbiPackage(
                packageFile.get().asFile, spec.target, spec.classifier, libraryVersion.get(),
                producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            val input = extractedCAbiPackageInput(
                spec, libraryVersion.get(), producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            val policy = describeCrossLanguageCAbiExportPolicy(input.exportPolicy, spec.format)
            val toolProofs = linkedMapOf<String, String>()
            val inspection = inspectCAbiBinary(spec, root, toolMap, toolProofs, policy)
            val consumers = executeCAbiConsumers(spec, root, sources, compileOnly, toolMap, temporary, toolProofs)
            val gnuConsumers = if (spec.format == "pe") {
                executeCAbiGnuConsumers(spec, root, sources, toolMap, temporary, toolProofs)
            } else {
                emptyList()
            }
            buildCrossLanguageCAbiPackageEvidence(CrossLanguageCAbiEvidenceValues(
                spec.target, spec.classifier, input.libraryVersion, input.producerCommit, input.producerTree,
                runnerOs.get(), runnerArch.get(), snapshot.archiveSha256, snapshot.headerSha256,
                snapshot.librarySha256, inspection.publicSymbols, inspection.publicSymbolVersions,
                inspection.format, inspection.architecture,
                inspection.loaderIdentity, inspection.versionIdentity,
                spec.importLibraryPaths.associateWith { snapshot.members.getValue(it) }, toolProofs,
                consumers, gnuConsumers,
            ),
                packageFile.get().asFile, input, sources, evidenceFile.get().asFile,
            )
        } finally {
            temporary.deleteRecursively()
        }
    }
}

@CacheableTask
abstract class VerifyCrossLanguageCAbiPackageEvidenceTask : DefaultTask() {
    @get:Input abstract val target: Property<String>
    @get:Input abstract val classifier: Property<String>
    @get:Input abstract val libraryVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:Input abstract val runnerOs: Property<String>
    @get:Input abstract val runnerArch: Property<String>
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val packageFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val evidenceFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val reviewedHeader: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val license: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val notice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val exportPolicy: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE) abstract val consumerSources: ConfigurableFileCollection
    @get:OutputFile abstract val verifiedEvidenceFile: RegularFileProperty

    @TaskAction
    fun verifyEvidence() {
        verifiedEvidenceFile.get().asFile.delete()
        val sources = consumerSources.files
        check(sources.all(::regularCAbiFile) && sources.map(File::getName).toSet() == crossLanguageCAbiStrictConsumers &&
            sources.size == crossLanguageCAbiStrictConsumers.size) {
            "C ABI strict consumer sources are missing or duplicated"
        }
        val spec = checkedCAbiTarget(target.get(), classifier.get())
        val temporary = Files.createTempDirectory("codex-agent-c-abi-verify-${spec.target}-").toFile()
        try {
            val root = temporary.resolve("sdk")
            inspectAndStageCrossLanguageCAbiPackage(
                packageFile.get().asFile, spec.target, spec.classifier, libraryVersion.get(),
                producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            val expected = extractedCAbiPackageInput(
                spec, libraryVersion.get(), producerCommit.get(), producerTree.get(), reviewedHeader.get().asFile,
                license.get().asFile, notice.get().asFile, exportPolicy.get().asFile, root,
            )
            verifyCrossLanguageCAbiPackageEvidence(
                evidenceFile.get().asFile, packageFile.get().asFile, expected,
                runnerOs.get(), runnerArch.get(), sources.toList(), verifiedEvidenceFile.get().asFile,
            )
        } finally {
            temporary.deleteRecursively()
        }
    }
}


private data class CAbiBinaryInspection(
    val publicSymbols: Set<String>,
    val publicSymbolVersions: Map<String, String>,
    val format: String,
    val architecture: String,
    val loaderIdentity: String,
    val versionIdentity: String,
)


private fun inspectCAbiBinary(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    tools: Map<String, String>,
    toolProofs: MutableMap<String, String>,
    policy: CrossLanguageCAbiExportPolicy,
): CAbiBinaryInspection {
    val library = root.resolve(spec.libraryPath)
    fun inspect(id: String, vararg arguments: String): String = runCAbiProcess(listOf(tools.getValue(id), *arguments)).also {
        toolProofs[id] = it.normalized(root).sha256()
    }
    return when (spec.format) {
        "mach-o" -> {
            val file = inspect("file", library.absolutePath)
            val architecture = inspect("architecture", "-archs", library.absolutePath).trim()
            val exports = normalizedCAbiSymbols(inspect("symbols", "-gU", library.absolutePath))
            val installName = inspect("loader", "-D", library.absolutePath).lineSequence().map(String::trim)
                .firstOrNull { it.startsWith("@rpath/") }.orEmpty()
            val versions = inspect("versions", "-L", library.absolutePath)
            check("Mach-O 64-bit" in file && architecture == spec.architecture) { "C ABI Mach-O architecture mismatch" }
            check(installName == spec.loaderIdentity && spec.expectedMachOLoaderVersion() in versions) {
                "C ABI Mach-O loader/version mismatch"
            }
            check(exports == policy.publicSymbols && policy.publicSymbolVersions.isEmpty()) {
                "C ABI packaged library export mismatch"
            }
            CAbiBinaryInspection(exports, emptyMap(), spec.format, architecture, installName, spec.expectedVersionIdentity())
        }
        "elf" -> {
            val file = inspect("file", library.absolutePath)
            val headers = inspect("architecture", "-h", library.absolutePath)
            val rawSymbols = inspect("symbols", "-D", "--defined-only", library.absolutePath)
            val exports = normalizedCAbiSymbols(rawSymbols)
            val symbolVersions = crossLanguageCAbiLinuxDynamicSymbolVersions(
                rawSymbols, policy.publicSymbolVersions,
            )
            val loader = inspect("loader", "-d", library.absolutePath)
            val versions = inspect("versions", "--version-info", library.absolutePath)
            val expectedMachine = if (spec.architecture == "aarch64") "AArch64" else "Advanced Micro Devices X86-64"
            check("ELF 64-bit" in file && Regex("Machine:\\s+${Regex.escape(expectedMachine)}").containsMatchIn(headers)) {
                "C ABI ELF architecture mismatch"
            }
            check(Regex("SONAME.*\\[${Regex.escape(spec.loaderIdentity)}]").containsMatchIn(loader)) {
                "C ABI ELF SONAME mismatch"
            }
            val nodes = Regex("CODEX_AGENT_[0-9]+\\.[0-9]+").findAll(versions).map { it.value }.toSet()
            check(nodes == policy.publicSymbolVersions.values.toSet()) { "C ABI ELF version-node lineage mismatch" }
            check(exports == policy.publicSymbols) { "C ABI packaged library export mismatch" }
            CAbiBinaryInspection(
                exports, symbolVersions, spec.format, spec.architecture, spec.loaderIdentity, spec.expectedVersionIdentity(),
            )
        }
        "pe" -> {
            val headers = inspect("architecture", "/headers", library.absolutePath)
            val exports = normalizedCAbiSymbols(inspect("symbols", "/exports", library.absolutePath))
            val msvc = root.resolve(spec.importLibraryPaths[1])
            val gnu = root.resolve(spec.importLibraryPaths[0])
            val msvcListing = inspect("msvcImport", "/list", msvc.absolutePath)
            val gnuSymbols = crossLanguageCAbiGnuImportSymbols(
                inspect("gnuImport", "-g", "--defined-only", gnu.absolutePath),
            )
            check("machine (x64)" in headers.lowercase() || "8664" in headers.lowercase()) {
                "C ABI PE architecture mismatch"
            }
            check(msvcListing.isNotBlank() && gnuSymbols == exports) { "C ABI Windows import-library closure mismatch" }
            check(exports == policy.publicSymbols && policy.publicSymbolVersions.isEmpty()) {
                "C ABI packaged library export mismatch"
            }
            CAbiBinaryInspection(exports, emptyMap(), spec.format, spec.architecture, spec.loaderIdentity, spec.expectedVersionIdentity())
        }
        else -> error("Unsupported C ABI package format: ${spec.format}")
    }
}

private fun executeCAbiConsumers(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    sources: List<File>,
    compileOnly: Set<String>,
    tools: Map<String, String>,
    temporary: File,
    toolProofs: MutableMap<String, String>,
): List<CrossLanguageCAbiConsumerProof> {
    val include = root.resolve("include")
    val libraryDirectory = root.resolve(spec.libraryPath).parentFile
    val executableDirectory = temporary.resolve("consumers").also(File::mkdirs)
    val environment = when (spec.format) {
        "mach-o" -> mapOf("DYLD_LIBRARY_PATH" to libraryDirectory.absolutePath)
        "elf" -> mapOf("LD_LIBRARY_PATH" to libraryDirectory.absolutePath)
        else -> mapOf("PATH" to root.resolve("bin").absolutePath + File.pathSeparator + System.getenv("PATH").orEmpty())
    }
    return sources.map { source ->
        val cpp = source.extension.lowercase() in setOf("cc", "cpp", "cxx")
        val language = if (cpp) "c++17" else "c11"
        val compilerId = if (cpp) "cpp" else "c"
        val compiler = tools.getValue(compilerId)
        val msvcStandard = if (cpp) listOf("/std:c++17", "/permissive-") else listOf("/std:c11")
        val linked = source.name !in compileOnly
        val artifact = executableDirectory.resolve(source.nameWithoutExtension + when {
            !linked && spec.format == "pe" -> ".obj"
            !linked -> ".o"
            spec.format == "pe" -> ".exe"
            else -> ""
        })
        val command = when {
            spec.format == "pe" && !linked -> listOf(
                compiler, "/nologo", "/W4", "/WX", if (cpp) "/TP" else "/TC", *msvcStandard.toTypedArray(),
                "/I${include.absolutePath}",
                source.absolutePath, "/c", "/Fo:${artifact.absolutePath}",
            )
            spec.format == "pe" -> listOf(
                compiler, "/nologo", "/W4", "/WX", if (cpp) "/TP" else "/TC", *msvcStandard.toTypedArray(),
                "/I${include.absolutePath}",
                source.absolutePath, "/Fe:${artifact.absolutePath}", "/link", "/LIBPATH:${root.resolve("lib").absolutePath}",
                "codex_agent.lib",
            )
            !linked -> listOf(
                compiler, if (cpp) "-std=c++17" else "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I${include.absolutePath}", source.absolutePath, "-c", "-o", artifact.absolutePath,
            )
            else -> listOf(
                compiler, if (cpp) "-std=c++17" else "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
                "-I${include.absolutePath}", source.absolutePath, "-L${libraryDirectory.absolutePath}", "-lcodex_agent",
                "-Wl,-rpath,${libraryDirectory.absolutePath}", "-o", artifact.absolutePath,
            )
        }
        val compilerIdentity = runCAbiProcess(
            if (spec.format == "pe") listOf(compiler) else listOf(compiler, "--version"),
            allowedExitCodes = if (spec.format == "pe") setOf(0, 2) else setOf(0),
        ).normalized(temporary)
        toolProofs[compilerId] = compilerIdentity.sha256()
        val compileOutput = runCAbiProcess(command).normalized(temporary)
        check(artifact.isFile) { "C ABI strict consumer did not produce an artifact: ${source.name}" }
        val executed = linked
        if (executed) runCAbiProcess(listOf(artifact.absolutePath), environment)
        CrossLanguageCAbiConsumerProof(
            source.name, source.releaseDigest(), language, compilerIdentity.sha256(), compileOutput.sha256(),
            artifact.releaseDigest(), linked = linked, executed = executed, exitCode = 0,
        )
    }
}

private fun executeCAbiGnuConsumers(
    spec: CrossLanguageCAbiTargetSpec,
    root: File,
    sources: List<File>,
    tools: Map<String, String>,
    temporary: File,
    toolProofs: MutableMap<String, String>,
): List<CrossLanguageCAbiConsumerProof> {
    check(spec.format == "pe") { "GNU C ABI consumer proof is Windows-only" }
    val selected = sources.filter { it.name in C_ABI_GNU_CONSUMERS }.sortedBy(File::getName)
    check(selected.map(File::getName).toSet() == C_ABI_GNU_CONSUMERS) {
        "C ABI GNU strict consumer sources are incomplete"
    }
    val include = root.resolve("include")
    val gnuImportLibrary = root.resolve("lib/libcodex_agent.dll.a")
    check(regularCAbiFile(gnuImportLibrary)) { "Packaged GNU C ABI import library is missing" }
    val output = temporary.resolve("gnu-consumers").also(File::mkdirs)
    val environment = mapOf(
        "PATH" to root.resolve("bin").absolutePath + File.pathSeparator + System.getenv("PATH").orEmpty(),
    )
    return selected.map { source ->
        val cpp = source.extension.lowercase() == "cpp"
        val compilerId = if (cpp) "gnuCpp" else "gnuC"
        val compiler = tools.getValue(compilerId)
        val artifact = output.resolve("${source.nameWithoutExtension}-gnu.exe")
        val compilerIdentity = runCAbiProcess(listOf(compiler, "--version")).normalized(temporary)
        toolProofs[compilerId] = compilerIdentity.sha256()
        val compileOutput = runCAbiProcess(listOf(
            compiler,
            if (cpp) "-std=c++17" else "-std=c11",
            "-Wall", "-Wextra", "-Werror", "-pedantic",
            "-I${include.absolutePath}",
            source.absolutePath,
            gnuImportLibrary.absolutePath,
            "-o", artifact.absolutePath,
        )).normalized(temporary)
        check(artifact.isFile) { "C ABI GNU strict consumer did not link: ${source.name}" }
        runCAbiProcess(listOf(artifact.absolutePath), environment)
        CrossLanguageCAbiConsumerProof(
            source.name,
            source.releaseDigest(),
            if (cpp) "c++17" else "c11",
            compilerIdentity.sha256(),
            compileOutput.sha256(),
            artifact.releaseDigest(),
            linked = true,
            executed = true,
            exitCode = 0,
        )
    }
}


private fun runCAbiProcess(
    command: List<String>,
    environment: Map<String, String> = emptyMap(),
    allowedExitCodes: Set<Int> = setOf(0),
): String {
    check(command.isNotEmpty() && command.all { '\u0000' !in it }) { "Invalid C ABI evidence command" }
    val log = Files.createTempFile("codex-agent-c-abi-process-", ".log").toFile()
    return try {
        val process = ProcessBuilder(command).redirectErrorStream(true).redirectOutput(log).apply {
            environment().putAll(environment)
        }.start()
        val completed = process.waitFor(5, TimeUnit.MINUTES)
        if (!completed) process.destroyForcibly().waitFor()
        val exit = if (completed) process.exitValue() else -1
        val output = log.readText()
        check(exit in allowedExitCodes) { "C ABI evidence command failed ($exit): ${command.first()}\n$output" }
        output
    } finally {
        log.delete()
    }
}


private fun normalizedCAbiSymbols(output: String): Set<String> = C_ABI_SYMBOL.findAll(output).map { match ->
    match.groupValues[1].removePrefix("_").substringBefore('@')
}.filter { it.startsWith("codex_agent_") }.toCollection(sortedSetOf())

internal fun crossLanguageCAbiGnuImportSymbols(output: String): Set<String> = output.lineSequence().mapNotNull { line ->
    C_ABI_SYMBOL.matchEntire(line.trim().takeLastWhile { !it.isWhitespace() })?.groupValues?.get(1)?.removePrefix("_")
}.toCollection(sortedSetOf())


private fun safeToolExecutable(value: String): Boolean = value.isNotBlank() && '\n' !in value && '\r' !in value && '\u0000' !in value

private fun String.normalized(root: File): String = replace(root.absolutePath, "<WORK>").replace("\\", "/")

private val LINUX_DYNAMIC_VERSIONED_SYMBOL =
    Regex("(?<![A-Za-z0-9_])(_?codex_agent_[A-Za-z0-9_]+)@@(CODEX_AGENT_1\\.\\d+)(?![A-Za-z0-9_.])")
