import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

private val javaScriptEnumOwnerRenames = mapOf(
    "AgentApprovalPreset" to "CodexApprovalPreset",
    "AgentAuthenticationStatus" to "CodexAuthenticationStatus",
    "AgentConversationStatus" to "CodexConversationStatus",
    "AgentMessageRole" to "CodexMessageRole",
    "AgentWorkActivity" to "CodexWorkActivity",
)

@CacheableTask
abstract class GenerateJavaScriptEnumDeclarationsTask : DefaultTask() {
    @get:InputFile
    @get:PathSensitive(PathSensitivity.NONE)
    abstract val apiReport: RegularFileProperty

    @get:OutputFile
    abstract val declarationsFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val output = declarationsFile.get().asFile
        Files.deleteIfExists(output.toPath())
        output.atomicReplaceTextIfChanged(renderJavaScriptEnumDeclarations(apiReport.get().asFile))
    }
}

internal fun renderJavaScriptEnumDeclarations(report: File): String {
    readCrossLanguageApiMemberKeys(report) // Shared schema-2, canonical-byte, and safe-file gate.
    val root = releaseJson.parseToJsonElement(report.readText()) as JsonObject
    val declarations = (root.getValue("owners") as JsonArray).mapNotNull { value ->
        val owner = value as JsonObject
        val ownerName = (owner.getValue("name") as JsonPrimitive).content
        val entries = (owner.getValue("capabilities") as JsonArray).mapNotNull { capability ->
            parseJavaScriptEnumEntry((capability as JsonPrimitive).content, ownerName)
        }
        if (entries.isEmpty()) return@mapNotNull null

        val simpleName = ownerName.substringAfterLast('/')
        val exportName = javaScriptEnumOwnerRenames[simpleName] ?: simpleName
        check(exportName.isSafeJavaScriptEnumExportName()) {
            "Unsafe JavaScript/TypeScript enum export name $exportName from $ownerName"
        }
        val literals = entries.map { entry ->
            check(entry.isSafeCanonicalEnumEntry()) { "Unsafe canonical enum entry $entry for $ownerName" }
            entry.lowercase().also { literal ->
                check(literal.isLowerSnakeLiteral()) {
                    "Unsafe JavaScript/TypeScript enum literal $literal for $ownerName"
                }
            }
        }
        check(entries.size == entries.distinct().size) { "Duplicate canonical enum entries for $ownerName" }
        check(literals.size == literals.distinct().size) {
            "Colliding JavaScript/TypeScript enum literals for $ownerName"
        }
        JavaScriptEnumDeclaration(exportName, literals.sorted())
    }
    check(declarations.isNotEmpty()) { "Cross-language API report has no enum owners" }
    check(declarations.map(JavaScriptEnumDeclaration::name).distinct().size == declarations.size) {
        "Colliding JavaScript/TypeScript enum export names"
    }
    return declarations.sortedBy(JavaScriptEnumDeclaration::name).joinToString(separator = "\n", postfix = "\n") {
        declaration ->
        "export type ${declaration.name} = ${declaration.literals.joinToString(" | ") { "\"$it\"" }};"
    }
}

private data class JavaScriptEnumDeclaration(val name: String, val literals: List<String>)

private fun parseJavaScriptEnumEntry(capability: String, reportOwner: String): String? {
    val fields = capability.split('|')
    check(fields.size >= 5 && fields[0] == "common" && fields[1].startsWith("owner=") &&
        fields[2].startsWith("kind=") && fields[3].startsWith("abi=")
    ) { "Malformed canonical capability: $capability" }
    check(fields.drop(4).none { field ->
        field.startsWith("owner=") || field.startsWith("kind=") || field.startsWith("abi=")
    }) { "Mixed canonical capability identity fields: $capability" }

    val owner = fields[1].removePrefix("owner=")
    val kind = fields[2].removePrefix("kind=")
    val abi = fields[3].removePrefix("abi=")
    check(owner == reportOwner) { "Canonical capability/report owner mismatch: $capability" }
    check(kind in setOf("constructor", "enum-entry", "function", "object", "property")) {
        "Unsupported canonical capability kind $kind: $capability"
    }

    val name = if (kind == "object") "" else abi.substringAfterLast('.', missingDelimiterValue = "")
    check(if (kind == "object") abi == owner else name.isNotBlank() && abi.removeSuffix(".$name") == owner) {
        "Canonical capability ABI/owner mismatch: $capability"
    }
    when (kind) {
        "constructor", "function" -> check(fields.size == 8 && fields[4].isNotBlank() &&
            fields[5].startsWith("return=") && fields[5].removePrefix("return=").isNotBlank() &&
            fields[6] in setOf("suspend=false", "suspend=true") &&
            fields[7].startsWith("parameters=[") && fields[7].endsWith(']')
        ) { "Malformed canonical $kind capability: $capability" }
        "property" -> check(fields.size == 7 && fields[4].isNotBlank() &&
            fields[5] in setOf("propertyKind=VAL", "propertyKind=VAR") &&
            fields[6].startsWith("type=") && fields[6].removePrefix("type=").isNotBlank()
        ) { "Malformed canonical property capability: $capability" }
        "object" -> check(fields.size == 5 && fields[4] == "null[0]") {
            "Malformed canonical object capability: $capability"
        }
        "enum-entry" -> {
            check(fields.size == 5 && fields[4] == "null[0]") {
                "Malformed canonical enum-entry capability: $capability"
            }
            return name
        }
    }
    return null
}

private fun String.isSafeJavaScriptEnumExportName(): Boolean =
    isNotEmpty() && first() in 'A'..'Z' && all { it.isAsciiLetterOrDigit() }

private fun String.isSafeCanonicalEnumEntry(): Boolean =
    isNotEmpty() && first().isAsciiLetter() && all { it.isAsciiLetterOrDigit() || it == '_' }

private fun String.isLowerSnakeLiteral(): Boolean =
    isNotEmpty() && first() in 'a'..'z' && last() != '_' && "__" !in this &&
        all { it in 'a'..'z' || it in '0'..'9' || it == '_' }

private fun Char.isAsciiLetter(): Boolean = this in 'A'..'Z' || this in 'a'..'z'

private fun Char.isAsciiLetterOrDigit(): Boolean = isAsciiLetter() || this in '0'..'9'
