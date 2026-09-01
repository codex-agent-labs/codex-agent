import java.io.ByteArrayOutputStream
import java.io.File
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
): String {
    val output = ByteArrayOutputStream()
    val errors = ByteArrayOutputStream()
    val result = exec {
        commandLine(command)
        workingDirectory?.let(::workingDir)
        environment(environmentVariables)
        standardOutput = output
        errorOutput = errors
        isIgnoreExitValue = true
    }
    return requireSuccessfulReleaseProcess(
        command,
        result.exitValue,
        output.toString(Charsets.UTF_8.name()),
        errors.toString(Charsets.UTF_8.name()),
    )
}
