import java.io.File
import java.nio.file.Files
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.LocalState
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal fun verifyJavaScriptNpmPackInventory(packageDirectory: File, report: String) {
    val expected = verifiedRegularFiles(packageDirectory)
    check("META-INF/codex-agent/sdk-compatibility.json" in expected) {
        "Staged npm package is missing its SDK compatibility declaration"
    }
    val packages = releaseJson.parseToJsonElement(report) as? JsonArray
        ?: error("npm pack inventory is not an array")
    val packed = packages.singleOrNull() as? JsonObject
        ?: error("npm pack must report exactly one package")
    val manifest = packageDirectory.resolve("package.json").readReleaseObject()
    listOf("name", "version").forEach { field ->
        check(packed.releaseString(field) == manifest.releaseString(field)) {
            "npm pack $field differs from the staged package"
        }
    }
    val files = packed.releaseArray("files").map { it as? JsonObject ?: error("Invalid npm pack file") }
    val paths = files.map { it.releaseString("path") }
    check(paths.size == paths.toSet().size && paths.toSet() == expected.keys) {
        "npm pack file inventory differs from the exact staged package"
    }
    files.forEach { file ->
        check(file.releaseLong("size") == expected.getValue(file.releaseString("path")).length()) {
            "npm pack file length differs from the staged package"
        }
    }
}

@DisableCachingByDefault(because = "Rechecks the local npm pack inventory without producing another archive")
abstract class VerifyJavaScriptNpmPackInventoryTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageDirectory: DirectoryProperty

    @get:LocalState abstract val cacheDirectory: DirectoryProperty

    @TaskAction fun verify() {
        val directory = packageDirectory.get().asFile
        val report = processes.captureReleaseProcess(
            listOf("npm", "pack", "--dry-run", "--json", "--ignore-scripts", "--offline"),
            directory,
            mapOf("npm_config_cache" to cacheDirectory.get().asFile.absolutePath),
        )
        verifyJavaScriptNpmPackInventory(directory, report)
    }
}

@CacheableTask
abstract class VerifyJavaScriptTypeScriptBindingParityTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val coverage: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val packedApiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NAME_ONLY)
    abstract val npmTarball: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val installedPackage: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packedConsumerProgram: DirectoryProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val compiledJsNodeTestProgram: DirectoryProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val packedJUnit: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val jsNodeJUnit: RegularFileProperty

    @get:OutputFile
    abstract val receiptFile: RegularFileProperty

    @TaskAction
    fun verify() {
        val output = receiptFile.get().asFile
        Files.deleteIfExists(output.toPath())
        val receipt = buildJavaScriptTypeScriptBindingReceipt(
            CrossLanguageJavaScriptBindingFiles(
                apiReport = apiReport.get().asFile,
                canonicalCoverageReceipt = coverage.get().asFile,
                packedPublicApiReport = packedApiReport.get().asFile,
                npmTarball = npmTarball.get().asFile,
                installedPackageDirectory = installedPackage.get().asFile,
                consumerSourceDirectory = packedConsumerProgram.get().asFile,
                compiledJsNodeTestProgramDirectory = compiledJsNodeTestProgram.get().asFile,
                packedJUnitReport = packedJUnit.get().asFile,
                jsNodeJUnitReport = jsNodeJUnit.get().asFile,
            ),
        )
        writeCrossLanguageBindingReceipt(output, receipt)
        check(readCrossLanguageBindingReceipt(output).toJson() == receipt.toJson()) {
            "JavaScript/TypeScript binding parity receipt does not match freshly recomputed evidence"
        }
    }
}
