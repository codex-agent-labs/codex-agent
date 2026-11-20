import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject

/**
 * Captures the four package replay inputs before native execution begins. The returned digests
 * have authority only when an outer original receipt authenticates them with the sibling raw
 * execution evidence.
 */
internal fun captureApplePackageExecutionInputs(
    productDirectory: File,
    binaryFrameworks: File,
    sourceSnapshot: File,
    sdkCompatibility: File,
): Map<String, Map<String, String>> {
    val inputs = listOf(productDirectory, binaryFrameworks, sourceSnapshot, sdkCompatibility)
    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "execution binding input") }
    val product = productDirectory.canonicalFile
    val binary = binaryFrameworks.canonicalFile
    val source = sourceSnapshot.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    check(listOf(product, binary, source).all(File::isDirectory) &&
        compatibility.isFile && compatibility.length() > 0L &&
        !Files.isSymbolicLink(compatibility.toPath())) {
        "Apple package execution binding input is missing or unsafe"
    }
    fun inventory(root: File): Map<String, String> {
        val files = verifiedRegularFiles(root)
        check(files.isNotEmpty()) { "Apple package execution binding input is empty" }
        return files.toSortedMap().mapValues { (_, file) -> file.releaseDigest() }
    }
    return linkedMapOf(
        "product" to inventory(product),
        "binary" to inventory(binary),
        "source" to inventory(source),
        "compatibility" to mapOf("sdk-compatibility.json" to compatibility.releaseDigest()),
    )
}

/**
 * Publishes the pre-execution input snapshot only after those originals still match. This file
 * deliberately contains neither the evidence digest nor a success, host, receipt, or verdict.
 * The outer transport must authenticate it together with the complete adjacent event directory.
 */
internal fun writeApplePackageExecutionBinding(
    bindingFile: File,
    context: ApplePackageExecutionContext,
    originalInputs: Map<String, Map<String, String>>,
    productDirectory: File,
    binaryFrameworks: File,
    sourceSnapshot: File,
    sdkCompatibility: File,
) {
    val suppliedInputs = listOf(productDirectory, binaryFrameworks, sourceSnapshot, sdkCompatibility)
    (suppliedInputs + bindingFile).forEach {
        requireApplePackagePathWithoutSymlinks(it, "execution binding")
    }
    val output = requireNormalizedAppleBindingPath(bindingFile, "output")
    val contextPaths = linkedMapOf(
        "scratchDirectory" to context.scratchDirectory,
        "workDirectory" to context.workDirectory,
        "sourceSnapshot" to context.sourceSnapshot,
        "binaryFrameworks" to context.binaryFrameworks,
        "developerDirectory" to context.developerDirectory,
    )
    contextPaths.forEach { (role, path) ->
        requireLexicalAppleBindingPath(path, role)
        requireApplePackagePathWithoutSymlinks(path, "execution context $role")
        check(requireNormalizedAppleBindingPath(path, role).isDirectory) {
            "Apple package execution context $role is missing"
        }
    }
    contextPaths.values.toList().forEachIndexed { index, left ->
        contextPaths.values.drop(index + 1).forEach { right ->
            check(!left.toPath().startsWith(right.toPath()) && !right.toPath().startsWith(left.toPath())) {
                "Apple package execution context paths overlap"
            }
        }
    }
    check(context.sourceSnapshot.canonicalFile == sourceSnapshot.canonicalFile &&
        context.binaryFrameworks.canonicalFile == binaryFrameworks.canonicalFile) {
        "Apple package execution context does not bind the supplied source and binary inputs"
    }
    requireOriginalAppleSnapshotDisjoint(output, suppliedInputs + contextPaths.values)
    check(!Files.exists(output.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple package execution binding output must be fresh"
    }
    val heldInputs = originalInputs.mapValues { (_, inventory) -> inventory.toMap() }
    requireApplePackageExecutionInputInventory(heldInputs)
    check(captureApplePackageExecutionInputs(
        productDirectory,
        binaryFrameworks,
        sourceSnapshot,
        sdkCompatibility,
    ) == heldInputs) { "Apple package execution input changed before binding" }

    val binding = buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("context", buildJsonObject {
            contextPaths.toSortedMap().forEach { (role, path) -> put(role, JsonPrimitive(path.path)) }
        })
        put("inputs", buildJsonObject {
            heldInputs.toSortedMap().forEach { (role, inventory) ->
                put(role, buildJsonObject {
                    inventory.toSortedMap().forEach { (path, digest) -> put(path, JsonPrimitive(digest)) }
                })
            }
        })
    }
    Files.createDirectories(output.parentFile.toPath())
    val temporary = Files.createTempFile(output.parentFile.toPath(), ".${output.name}-", ".tmp").toFile()
    try {
        temporary.atomicWriteJson(binding)
        check(captureApplePackageExecutionInputs(
            productDirectory,
            binaryFrameworks,
            sourceSnapshot,
            sdkCompatibility,
        ) == heldInputs && originalInputs == heldInputs) {
            "Apple package execution input changed before publication"
        }
        val expectedBytes = temporary.readBytes()
        Files.createLink(output.toPath(), temporary.toPath())
        check(output.readBytes().contentEquals(expectedBytes) && captureApplePackageExecutionInputs(
            productDirectory,
            binaryFrameworks,
            sourceSnapshot,
            sdkCompatibility,
        ) == heldInputs && originalInputs == heldInputs) {
            "Apple package execution binding changed during publication"
        }
    } finally {
        Files.deleteIfExists(temporary.toPath())
    }
}

private fun requireApplePackageExecutionInputInventory(inputs: Map<String, Map<String, String>>) {
    check(inputs.keys == setOf("product", "binary", "source", "compatibility") &&
        inputs.values.all { it.isNotEmpty() } &&
        inputs.getValue("compatibility").keys == setOf("sdk-compatibility.json") &&
        inputs.all { (_, inventory) -> inventory.all { (path, digest) ->
            path.isNotBlank() && !path.startsWith('/') && '\\' !in path &&
                path.split('/').none { it.isEmpty() || it == "." || it == ".." } &&
                digest.matches(Regex("[0-9a-f]{64}"))
        } }) {
        "Apple package execution input binding is invalid"
    }
}

private fun requireNormalizedAppleBindingPath(file: File, role: String): File {
    check(file.isAbsolute && file.toPath().normalize() == file.toPath() && file.canonicalFile == file) {
        "Apple package execution binding $role path must be absolute and normalized"
    }
    return file
}

private fun requireLexicalAppleBindingPath(file: File, role: String) {
    check(file.isAbsolute && file.path.startsWith('/') && '\\' !in file.path && '\u0000' !in file.path &&
        file.toPath().normalize() == file.toPath()) {
        "Apple package execution context $role path must be normalized POSIX"
    }
}
