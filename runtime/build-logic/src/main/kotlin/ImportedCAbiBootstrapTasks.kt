import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

internal const val IMPORTED_C_ABI_TEST_TASK = "testImportedMacosArm64CAbi"

internal fun requireVacantImportedCAbiWorkspace(output: File, stage: File) {
    // Inspect lexical ancestors before normalization can erase a symbolic `link/..`.
    generateSequence(output.toPath().toAbsolutePath()) { it.parent }.forEach { path ->
        check(!Files.isSymbolicLink(path) &&
            (!Files.exists(path, LinkOption.NOFOLLOW_LINKS) || Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS))) {
            "Imported C ABI workspace has an unsafe parent: $path"
        }
    }
    val destination = output.toPath().toAbsolutePath().normalize()
    val original = stage.toPath().toAbsolutePath().normalize()
    check(!destination.startsWith(original) && !original.startsWith(destination)) {
        "Imported C ABI execution workspace overlaps its original stage"
    }
    if (Files.exists(output.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        Files.newDirectoryStream(output.toPath()).use { entries ->
            check(!entries.iterator().hasNext()) { "Imported C ABI execution workspace is not empty" }
        }
    }
}

/** This projection changes only the known Gradle task prefix, never the executed test set. */
internal fun canonicalCAbiNativeTests(
    tests: List<CanonicalTestResult>,
    taskName: String,
): List<CanonicalTestResult> {
    check(taskName in setOf("macosArm64Test", IMPORTED_C_ABI_TEST_TASK)) {
        "Unexpected C ABI Native test producer task"
    }
    val prefix = "$taskName.io.github.codex_agent_labs.codexagent.capi."
    return tests.map { test ->
        check(test.testId.startsWith(prefix) && test.testId.endsWith("[macosArm64]")) {
            "C ABI Native report has a foreign task, package or target identity: ${test.testId}"
        }
        test.copy(testId = "macosArm64Test." + test.testId.removePrefix("$taskName."))
    }
}

/** Extract only a previously verified package; never compile, repackage, or mutate its stage. */
@DisableCachingByDefault(because = "Rechecks imported C ABI bytes before each native execution")
abstract class PrepareImportedCAbiBootstrapTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageStage: DirectoryProperty
    @get:Input abstract val compatibilityVersion: Property<String>
    @get:Input abstract val producerCommit: Property<String>
    @get:Input abstract val producerTree: Property<String>
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    init { outputs.upToDateWhen { false } }

    @TaskAction
    fun prepare() {
        check(crossLanguageCAbiHostTarget(System.getProperty("os.name"), System.getProperty("os.arch")) == "macosArm64") {
            "Imported C ABI bootstrap requires a macOS Arm64 host"
        }
        val stage = packageStage.get().asFile
        requireRegularRuntimeProductTree(stage.toPath(), "Imported C ABI bootstrap package")
        val runner = stage.resolve("outputs/validation-runner")
        listOf("test.kexe", "compiler-header/libcodex_agent_api.h").forEach { name ->
            check(runner.resolve(name).isFile) { "Imported C ABI bootstrap artifact is missing: $name" }
        }
        listOf("nativeMain", "nativeTest").forEach { source ->
            requireRegularRuntimeProductTree(runner.resolve("source/$source").toPath(), "Original C ABI $source sources")
        }
        val output = outputDirectory.get().asFile
        requireVacantImportedCAbiWorkspace(output, stage)
        val reference = stage.resolve("outputs/c-abi-reference")
        inspectAndStageCrossLanguageCAbiPackage(
            stage.resolve("outputs/c-abi/${crossLanguageCAbiArchiveFileName(compatibilityVersion.get(), "macosArm64")}"),
            "macosArm64", "c-abi-macos-arm64", compatibilityVersion.get(), producerCommit.get(), producerTree.get(),
            reference.resolve("include/codex_agent.h"), reference.resolve("legal/LICENSE"),
            reference.resolve("legal/THIRD_PARTY_NOTICES.md"), reference.resolve("export-policy/macos.exports"),
            output.resolve("sdk"),
        )
        val executable = output.resolve("test.kexe")
        Files.copy(runner.resolve("test.kexe").toPath(), executable.toPath())
        check(executable.setExecutable(true, false)) { "Cannot execute the private imported native test runner" }
    }
}
