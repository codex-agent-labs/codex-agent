import java.io.File
import kotlinx.serialization.json.JsonPrimitive

internal val sdkFacadeConsumerCompileTasks = linkedMapOf(
    "android" to "compileAndroidMain", "jvm" to "compileKotlinJvm",
    "ios-arm64" to "compileKotlinIosArm64", "ios-simulator-arm64" to "compileKotlinIosSimulatorArm64",
    "macos-arm64" to "compileKotlinMacosArm64", "macos-x64" to "compileKotlinMacosX64",
    "linux-arm64" to "compileKotlinLinuxArm64", "linux-x64" to "compileKotlinLinuxX64",
    "windows-x64" to "compileKotlinMingwX64", "node-js" to "compileKotlinJs",
    "node-wasm" to "compileKotlinWasmJs",
)

internal val stagedConsumerBuildTasks = linkedMapOf(
    "common" to listOf("compileKotlinJvm"),
    "android" to listOf("compileAndroidMain", "compileAndroidMainJavaWithJavac"),
    "desktop" to listOf(
        "compileKotlinJvm", "compileJvmMainJava", "runDesktopJavaConsumer",
        "compileKotlinMacosArm64", "compileKotlinMacosX64",
        "compileKotlinLinuxArm64", "compileKotlinLinuxX64", "compileKotlinMingwX64",
    ),
    "ios-device" to listOf("linkDebugFrameworkIosArm64"),
    "ios-simulator" to listOf("linkDebugFrameworkIosSimulatorArm64"),
    "node-js" to listOf("compileKotlinJs"),
    "node-wasm" to listOf("compileKotlinWasmJs"),
)

internal const val stagedConsumerOutcomeTask = "verifyCodexStagedConsumerTaskOutcomes"

internal fun stagedConsumerCommand(wrapper: File, arguments: List<String>, javaExecutable: File? = null): List<String> {
    if (wrapper.name != "gradlew.bat") {
        check(javaExecutable == null) { "POSIX consumer rejects a Windows Java launcher" }
        return listOf(wrapper.absolutePath) + arguments
    }
    val java = checkNotNull(javaExecutable) { "Windows consumer requires an explicit Java launcher" }
    check(java.isAbsolute && java.name == "java.exe") { "Windows consumer Java launcher is invalid" }
    return listOf(java.absolutePath, "-Xmx64m", "-Xms64m", "-Dorg.gradle.appname=gradlew", "-jar",
        wrapper.parentFile.resolve("gradle/wrapper/gradle-wrapper.jar").absolutePath) + arguments
}

internal fun stagedConsumerOutcomeInitScript(buildTasks: List<String>): String {
    check(buildTasks.isNotEmpty()) { "Staged consumer build task set is empty" }
    check(buildTasks.distinct().size == buildTasks.size) { "Staged consumer build tasks contain duplicates" }
    check(buildTasks.all { it.matches(Regex("[A-Za-z0-9_-]+")) }) { "Staged consumer build task name is invalid" }
    val required = buildTasks.joinToString(", ") { "\"$it\"" }
    return """
        val requiredCodexConsumerTasks = listOf($required)
        gradle.projectsEvaluated {
            rootProject.tasks.register("$stagedConsumerOutcomeTask") {
                mustRunAfter(*requiredCodexConsumerTasks.toTypedArray())
                doLast {
                    val unproved = requiredCodexConsumerTasks.filter { taskName ->
                        val state = rootProject.tasks.getByName(taskName).state
                        !state.didWork && !state.upToDate
                    }
                    check(unproved.isEmpty()) {
                        "Staged consumer tasks did not execute or prove up-to-date: " +
                            unproved.joinToString()
                    }
                }
            }
        }
    """.trimIndent() + "\n"
}

internal fun stagedConsumerArguments(
    consumer: File,
    repository: File,
    sdkVersion: String,
    runtimeVersion: String,
    target: String,
    buildTasks: List<String>,
    outcomeInitScript: File? = null,
): List<String> = listOf(
    "-p", consumer.absolutePath,
    "--offline",
    "--no-daemon",
    "--no-configuration-cache",
    "-PCENTRAL_STAGING=${repository.absolutePath}",
    "-PcodexAgent.sdkVersion=$sdkVersion",
    "-PcodexAgent.runtimeVersion=$runtimeVersion",
    "-PcodexAgent.consumerTarget=$target",
) + outcomeInitScript?.let { listOf("--init-script", it.absolutePath) }.orEmpty() +
    buildTasks + outcomeInitScript?.let { listOf(stagedConsumerOutcomeTask) }.orEmpty()

internal fun prepareStagedConsumer(template: File, consumer: File, androidSdk: String) {
    check(template.isDirectory) { "KMP consumer template is missing" }
    val properties = stagedConsumerLocalProperties(androidSdk)
    consumer.deleteRecursively()
    check(template.copyRecursively(consumer, overwrite = true)) { "Failed to copy KMP consumer template" }
    consumer.resolve("local.properties").writeText(properties)
}

internal fun stagedConsumerLocalProperties(androidSdk: String): String {
    check('\n' !in androidSdk && '\r' !in androidSdk) { "Android SDK path is invalid" }
    val escaped = androidSdk.replace("\\", "\\\\").replace(":", "\\:")
    return "sdk.dir=$escaped\n"
}

/** Appends observations to the existing outcome check; it does not redefine success. */
internal fun stagedConsumerExecutionCaptureScript(outcomes: File): String =
    stagedConsumerExecutionCaptureScript(outcomes.absolutePath)

/** A lexical original path also works when Windows evidence is replayed on another host. */
internal fun stagedConsumerExecutionCaptureScript(outcomes: String): String = """
    val codexCapturedOutcomes = linkedMapOf<String, Map<String, Any?>>()
    val codexOutcomeFile = java.io.File(${JsonPrimitive(outcomes).toString().replace("$", "\\$")})
    gradle.taskGraph.afterTask(object : org.gradle.api.Action<org.gradle.api.Task> {
        override fun execute(task: org.gradle.api.Task) {
            val state = task.state
            if (task.project == gradle.rootProject && task.name in requiredCodexConsumerTasks) {
                codexCapturedOutcomes[task.name] = linkedMapOf(
                    "task" to task.name, "didWork" to state.didWork, "upToDate" to state.upToDate,
                    "skipped" to state.skipped, "skipMessage" to state.skipMessage,
                    "failure" to state.failure?.toString(),
                )
                val content = groovy.json.JsonOutput.toJson(linkedMapOf(
                    "schemaVersion" to 1,
                    "tasks" to requiredCodexConsumerTasks.mapNotNull { codexCapturedOutcomes[it] },
                )) + "\n"
                var current: java.io.File? = codexOutcomeFile
                while (current != null) {
                    check(!java.nio.file.Files.isSymbolicLink(current.toPath())) { "KMP outcome capture became symbolic" }
                    current = current.parentFile
                }
                java.nio.file.Files.newByteChannel(codexOutcomeFile.toPath(),
                    java.nio.file.StandardOpenOption.WRITE, java.nio.file.StandardOpenOption.TRUNCATE_EXISTING,
                    java.nio.file.LinkOption.NOFOLLOW_LINKS).use { channel ->
                    val bytes = java.nio.ByteBuffer.wrap(content.toByteArray(Charsets.UTF_8))
                    while (bytes.hasRemaining()) channel.write(bytes)
                }
            }
        }
    })
""".trimIndent() + "\n"
