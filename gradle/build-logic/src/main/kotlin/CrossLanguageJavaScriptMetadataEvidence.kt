import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption.ATOMIC_MOVE
import java.util.zip.GZIPInputStream
import kotlinx.serialization.json.JsonElement
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream

/** Restore only matcher primaries, never install or execute the npm archive. */
internal fun restoreJavaScriptMetadataPackage(archive: File, destination: File) {
    check(archive.isFile && archive.length() in 1..(1024L * 1024 * 1024) &&
        generateSequence(archive) { it.parentFile }.none { Files.isSymbolicLink(it.toPath()) }) {
        "JavaScript metadata archive is missing or unsafe"
    }
    fun destinationAvailable() = (!destination.exists() ||
        (destination.isDirectory && destination.list()?.isEmpty() == true)) &&
        generateSequence(destination) { it.parentFile }.none { Files.isSymbolicLink(it.toPath()) }
    check(destinationAvailable() &&
        !archive.canonicalFile.toPath().startsWith(destination.canonicalFile.toPath()) &&
        !destination.canonicalFile.toPath().startsWith(archive.canonicalFile.toPath())) {
        "JavaScript metadata package destination is occupied or overlaps its original"
    }
    val original = archive.readBytes()
    val required = setOf("package/index.cjs", "package/index.d.ts", "package/index.mjs", "package/package.json")
    val retained = sortedMapOf<String, ByteArray>()
    val seen = mutableSetOf<String>()
    TarArchiveInputStream(GZIPInputStream(original.inputStream())).use { input ->
        while (true) {
            val entry = input.nextEntry ?: break
            val name = entry.name
            val parts = name.removeSuffix("/").split('/')
            check(name.isNotEmpty() && !name.startsWith('/') && '\\' !in name &&
                name.none { it.code < 32 || it.code == 127 } &&
                parts.none { it.isEmpty() || it == "." || it == ".." || ':' in it } &&
                seen.add(name.removeSuffix("/")) && !entry.isSymbolicLink && !entry.isLink &&
                (entry.isFile || entry.isDirectory) && (entry.isDirectory || !name.endsWith('/'))) {
                "JavaScript metadata archive contains an unsafe or duplicate member: $name"
            }
            if (name in required) {
                check(entry.isFile && entry.size in 1..(64L * 1024 * 1024)) {
                    "JavaScript metadata primary is not a bounded regular file: $name"
                }
                val bytes = input.readNBytes(entry.size.toInt())
                check(bytes.size.toLong() == entry.size) { "Truncated JavaScript metadata primary: $name" }
                retained[name.removePrefix("package/")] = bytes
            }
        }
    }
    check(retained.keys == required.map { it.removePrefix("package/") }.toSet()) {
        "JavaScript metadata archive lacks its exact four matcher primaries"
    }
    check(archive.readBytes().contentEquals(original)) { "JavaScript metadata archive changed during capture" }
    destination.parentFile.mkdirs()
    val temporary = Files.createTempDirectory(destination.parentFile.toPath(), ".javascript-metadata-")
    try {
        retained.forEach { (name, bytes) -> Files.write(temporary.resolve(name), bytes) }
        check(destinationAvailable()) { "JavaScript metadata destination became occupied during capture" }
        // Gradle precreates @OutputDirectory. Atomic directory rename accepts
        // its empty directory, but cannot replace a file or nonempty directory.
        Files.move(temporary, destination.toPath(), ATOMIC_MOVE)
    } finally {
        if (Files.exists(temporary)) {
            retained.keys.forEach { Files.deleteIfExists(temporary.resolve(it)) }
            Files.deleteIfExists(temporary)
        }
    }
}

/** Content replay only: the caller authenticates the original stages and source
 * checkout, including [originalConsumerDirectory]. This grants no CI authority.
 * Raw executions remain external; the returned existing schema-3 projection is
 * independent of original checkout paths, run identity and JUnit timings.
 */
internal fun replayJavaScriptMetadata(
    files: CrossLanguageJavaScriptBindingFiles,
    executionDirectory: File,
    originalConsumerDirectory: File,
    originalBindingReceipt: File,
): CrossLanguageBindingReceipt {
    val inputs = listOf(files.apiReport, files.canonicalCoverageReceipt,
        files.packedPublicApiReport, files.npmTarball, files.packedJUnitReport,
        files.jsNodeJUnitReport, originalBindingReceipt)
    val directories = listOf(files.installedPackageDirectory, files.consumerSourceDirectory,
        files.compiledJsNodeTestProgramDirectory, executionDirectory)
    fun inventory(): List<String> = inputs.map { file ->
        check(file.isFile && !Files.isSymbolicLink(file.toPath())) {
            "JavaScript metadata original input is missing or symbolic: $file"
        }
        file.releaseDigest()
    } + directories.map { it.crossLanguageTreeDigest() }
    val before = inventory()
    check(executionDirectory.listFiles()?.map(File::getName)?.sorted() ==
        listOf("packed-consumer-execution.json", "typescript-execution.json")) {
        "JavaScript metadata requires exactly the two original consumer executions"
    }
    verifyJavaScriptConsumerExecutions(executionDirectory, originalConsumerDirectory)
    val original = originalBindingReceipt.readBytes()
    val receipt = buildJavaScriptTypeScriptBindingReceipt(files)
    val reconstructed = (releaseJson.encodeToString(JsonElement.serializer(), receipt.toJson()) + "\n")
        .toByteArray(Charsets.UTF_8)
    check(original.contentEquals(reconstructed)) {
        "Original JavaScript parity receipt differs from complete metadata replay"
    }
    check(before == inventory()) { "JavaScript metadata original inputs changed during replay" }
    return receipt
}
