import java.nio.file.Files
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
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

internal const val SDK_BINDING_EVIDENCE_DIRECTORY_PROPERTY =
    "codexAgent.sdkBindingEvidenceDirectory"

@CacheableTask
abstract class VerifyImportedSdkBindingParityTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalApiReport: RegularFileProperty

    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val canonicalCoverageReceipt: RegularFileProperty

    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val evidenceDirectory: DirectoryProperty

    @get:OutputFile
    abstract val resultFile: RegularFileProperty

    @TaskAction
    fun verify() {
        Files.deleteIfExists(resultFile.get().asFile.toPath())
        val directory = evidenceDirectory.get().asFile
        val files = verifiedRegularFiles(directory)
        check(files.keys == crossLanguageM11EvidenceFileNames) {
            "Imported SDK binding evidence file set is incomplete or unexpected"
        }
        val audit = verifyCompleteCrossLanguageM11Evidence(files)
        check(audit.apiReportSha256 == canonicalApiReport.get().asFile.releaseDigest()) {
            "Imported SDK binding API identity does not match the current Contract"
        }
        check(audit.canonicalCoverageSha256 == canonicalCoverageReceipt.get().asFile.releaseDigest()) {
            "Imported SDK binding coverage identity does not match the current Contract"
        }
        check(audit.summary.total % CrossLanguageBinding.entries.size == 0) {
            "Imported SDK binding obligation count is not divisible by the language count"
        }
        resultFile.get().asFile.atomicWriteJson(buildJsonObject {
            put("schemaVersion", JsonPrimitive(1))
            put("result", JsonPrimitive("passed"))
            put("phase", JsonPrimitive(CrossLanguageBindingPhase.M11.name))
            put("capabilityCount", JsonPrimitive(audit.summary.total / CrossLanguageBinding.entries.size))
            put("languageCount", JsonPrimitive(CrossLanguageBinding.entries.size))
            put("scenarioCount", JsonPrimitive(CrossLanguageBindingScenario.entries.size))
            put("canonicalApiSha256", JsonPrimitive(audit.apiReportSha256))
            put("canonicalCoverageSha256", JsonPrimitive(audit.canonicalCoverageSha256))
            put("active", JsonPrimitive(audit.summary.active))
            put("pending", JsonPrimitive(audit.summary.pending))
            put("excluded", JsonPrimitive(audit.summary.excluded))
            put("satisfied", JsonPrimitive(audit.summary.satisfied))
            put("missing", JsonPrimitive(audit.summary.missing))
            put("evidenceFiles", buildJsonArray {
                files.toSortedMap().forEach { (name, file) -> add(file.releaseRecord(name)) }
            })
        })
    }
}
