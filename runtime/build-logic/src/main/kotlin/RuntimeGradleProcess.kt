import java.io.ByteArrayOutputStream
import java.io.File
import org.gradle.process.ExecOperations

internal fun ExecOperations.captureRuntimeProcess(
    command: List<String>,
    workingDirectory: File? = null,
    environmentVariables: Map<String, String> = mapOf("LC_ALL" to "C", "LANG" to "C"),
    removedEnvironmentVariables: Set<String> = emptySet(),
): String {
    val output = ByteArrayOutputStream()
    val errors = ByteArrayOutputStream()
    val result = exec {
        commandLine(command)
        workingDirectory?.let(::workingDir)
        setEnvironment(environment.toMutableMap().apply {
            removedEnvironmentVariables.forEach(::remove)
            putAll(environmentVariables)
        })
        standardOutput = output
        errorOutput = errors
        isIgnoreExitValue = true
    }
    val standardOutput = output.toString(Charsets.UTF_8.name())
    val details = listOf(standardOutput.trim(), errors.toString(Charsets.UTF_8.name()).trim())
        .filter(String::isNotEmpty)
        .joinToString("\n")
    check(result.exitValue == 0) { "${command.joinToString(" ")} failed (${result.exitValue}): $details" }
    return standardOutput
}
