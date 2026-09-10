import java.io.ByteArrayOutputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.process.ExecOperations

internal fun requireSuccessfulReleaseProcess(
    command: List<String>,
    exitCode: Int,
    output: String,
    errors: String,
): String {
    val details = listOf(output.trim(), errors.trim()).filter(String::isNotEmpty).joinToString("\n")
    check(exitCode == 0) { "${command.joinToString(" ")} failed ($exitCode): $details" }
    return output
}

internal fun ExecOperations.captureReleaseProcess(
    command: List<String>,
    workingDirectory: File? = null,
    environmentVariables: Map<String, String> = mapOf("LC_ALL" to "C", "LANG" to "C"),
    captureDirectory: File? = null,
): String {
    captureDirectory?.let { directory ->
        requireApplePackagePathWithoutSymlinks(directory, "raw process capture")
        check(!Files.exists(directory.toPath(), LinkOption.NOFOLLOW_LINKS)) {
            "Release process capture must be fresh: $directory"
        }
    }
    val output = ByteArrayOutputStream()
    val errors = ByteArrayOutputStream()
    var actualWorkingDirectory: File? = null
    val result = try { exec {
        commandLine(command)
        workingDirectory?.let(::workingDir)
        actualWorkingDirectory = workingDir
        environment(environmentVariables)
        standardOutput = output
        errorOutput = errors
        isIgnoreExitValue = true
    } } catch (failure: Throwable) {
        captureDirectory?.let {
            writeReleaseProcessCapture(it, command, actualWorkingDirectory, environmentVariables, null,
                output.toByteArray(), errors.toByteArray())
        }
        throw failure
    }
    captureDirectory?.let {
        writeReleaseProcessCapture(it, command, actualWorkingDirectory, environmentVariables, result.exitValue,
            output.toByteArray(), errors.toByteArray())
    }
    return requireSuccessfulReleaseProcess(
        command,
        result.exitValue,
        output.toString(Charsets.UTF_8.name()),
        errors.toString(Charsets.UTF_8.name()),
    )
}

internal fun writeReleaseProcessCapture(
    directory: File, command: List<String>, workingDirectory: File?, environment: Map<String, String>,
    exitCode: Int?, output: ByteArray, errors: ByteArray,
) {
    requireApplePackagePathWithoutSymlinks(directory, "raw process capture")
    check(!Files.exists(directory.toPath(), LinkOption.NOFOLLOW_LINKS)) { "Release process capture must be fresh" }
    Files.createDirectories(directory.toPath().parent)
    Files.createDirectory(directory.toPath())
    directory.resolve("stdout.bin").writeBytes(output)
    directory.resolve("stderr.bin").writeBytes(errors)
    directory.resolve("execution.json").atomicWriteJson(buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("command", buildJsonArray { command.forEach { add(JsonPrimitive(it)) } })
        // Null means ExecSpec configuration failed before its actual working directory was observed.
        put("workingDirectory", workingDirectory?.let { JsonPrimitive(it.absolutePath) } ?: JsonNull)
        put("environment", buildJsonObject {
            environment.toSortedMap().forEach { (name, value) -> put(name, JsonPrimitive(value)) }
        })
        put("exitCode", exitCode?.let(::JsonPrimitive) ?: JsonNull)
    })
}
