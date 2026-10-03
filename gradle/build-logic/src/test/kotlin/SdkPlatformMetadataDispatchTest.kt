import java.io.File
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlin.io.path.createTempDirectory
import kotlin.test.Test
import kotlin.test.assertEquals
import org.gradle.testkit.runner.GradleRunner

/** Real root graph/configuration only: no metadata writer or product compiler runs. */
class SdkPlatformMetadataDispatchTest {
    @Test
    fun `real platform metadata dispatch has only imported content and manifest tasks`() {
        val repository = generateSequence(File(System.getProperty("user.dir")).canonicalFile) { it.parentFile }
            .first { it.resolve("settings.gradle.kts").isFile && it.resolve("codex-agent-runtime-ios").isDirectory }
        val scratch = createTempDirectory("platform-metadata-dispatch-").toFile().canonicalFile
        try {
            for ((component, title, target) in listOf(
                Triple("sdk-core", "Core", "common"), Triple("sdk-android", "Android", "android"),
            )) {
                val common = mapOf(
                    "sdkVersion" to JsonPrimitive("0.8.0"),
                    "packageStage" to JsonPrimitive(scratch.resolve("package").path),
                    "packageReceipt" to JsonPrimitive(scratch.resolve("package.json").path),
                )
                val fields = if (component == "sdk-core") mapOf(
                    "contractDigest" to JsonPrimitive("sha256:" + "a".repeat(64)),
                    "componentDigests" to JsonObject(emptyMap()),
                    "validations" to JsonObject(sdkFacadeConsumerCompileTasks.keys.associateWith { host ->
                        JsonObject(mapOf(
                            "stageRoot" to JsonPrimitive(scratch.resolve("$host/stage").path),
                            "phaseReceipt" to JsonPrimitive(scratch.resolve("$host/receipt.json").path),
                        ))
                    }),
                ) else mapOf(
                    "validationStage" to JsonPrimitive(scratch.resolve("validation").path),
                    "validationReceipt" to JsonPrimitive(scratch.resolve("validation.json").path),
                    "releaseAarSha256" to JsonPrimitive("sha256:" + "a".repeat(64)),
                    "bundledRuntimeSha256" to JsonPrimitive("sha256:" + "b".repeat(64)),
                )
                val request = scratch.resolve("$component.json").apply { writeText(JsonObject(common + fields).toString()) }
                val property = if (component == "sdk-core") "sdkFacadeMetadataRequest" else "sdkAndroidMetadataRequest"
                val result = GradleRunner.create().withProjectDir(repository).withArguments(
                    "ciProductPhase", "--dry-run", "--offline", "--no-configuration-cache", "--console=plain",
                    "-PcodexAgent.product=sdk", "-PcodexAgent.component=$component", "-PcodexAgent.phase=metadata",
                    "-PcodexAgent.target=$target", "-PcodexAgent.sdkVersion=0.8.0",
                    "-PcodexAgent.$property=${request.path}",
                ).build()
                val paths = result.output.lineSequence().filter { it.startsWith(":") && it.endsWith(" SKIPPED") }
                    .map { it.removeSuffix(" SKIPPED") }.toList()
                assertEquals(listOf(":writeSdk${title}MetadataContent", ":writeSdk${title}MetadataOutputManifest",
                    ":sdkProductPhase", ":ciProductPhase"), paths, result.output)
            }
        } finally {
            scratch.deleteRecursively()
        }
    }
}
