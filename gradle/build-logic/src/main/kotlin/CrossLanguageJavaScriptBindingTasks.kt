import java.nio.file.Files
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

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
