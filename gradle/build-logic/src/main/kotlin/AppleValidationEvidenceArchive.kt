import java.io.BufferedOutputStream
import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS
import java.nio.charset.StandardCharsets.UTF_8
import java.time.LocalDateTime
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipFile
import java.util.zip.ZipOutputStream

private val appleValidationEvidenceTimestamp = LocalDateTime.of(1980, 1, 1, 0, 0)

/**
 * Writes caller-selected validation evidence without granting it semantic, producer, or host authority.
 * The caller remains responsible for authenticating every supplied source.
 */
internal fun writeAppleValidationEvidenceArchive(roots: Map<String, File>, archive: File) {
    check(roots.isNotEmpty()) { "Apple validation evidence roots are empty" }
    val destination = archive.absoluteFile
    requireApplePackagePathWithoutSymlinks(destination, "validation evidence archive")
    check(!Files.exists(destination.toPath(), NOFOLLOW_LINKS)) {
        "Apple validation evidence archive already exists"
    }

    val namedRoots = roots.entries.sortedBy { it.key }.map { (name, source) ->
        requireSafeAppleValidationEvidencePath(name)
        requireApplePackagePathWithoutSymlinks(source, "validation evidence source")
        name to source.absoluteFile
    }
    requireDisjointAppleValidationEvidencePaths(namedRoots.map { it.second }, destination)
    namedRoots.indices.forEach { left ->
        (left + 1 until namedRoots.size).forEach { right ->
            check(!appleValidationEvidencePathContains(namedRoots[left].first, namedRoots[right].first) &&
                !appleValidationEvidencePathContains(namedRoots[right].first, namedRoots[left].first)) {
                "Apple validation evidence archive roots overlap: " +
                    "${namedRoots[left].first}, ${namedRoots[right].first}"
            }
        }
    }

    val sources = collectAppleValidationEvidenceSources(namedRoots)
    val expected = sources.mapValues { (_, source) -> source.length() to source.releaseDigest() }
    verifyAppleValidationEvidenceSources(namedRoots, sources, expected)

    val parent = destination.parentFile
    parent.mkdirs()
    check(parent.isDirectory) { "Apple validation evidence archive parent is missing" }
    requireApplePackagePathWithoutSymlinks(destination, "validation evidence archive")
    check(!Files.exists(destination.toPath(), NOFOLLOW_LINKS)) {
        "Apple validation evidence archive already exists"
    }
    val temporary = Files.createTempFile(parent.toPath(), ".${destination.name}-", ".tmp").toFile()
    try {
        ZipOutputStream(BufferedOutputStream(temporary.outputStream())).use { output ->
            output.setLevel(Deflater.BEST_COMPRESSION)
            sources.entries.sortedWith { left, right ->
                compareAppleValidationEvidenceNames(left.key, right.key)
            }.forEach { (name, source) ->
                output.putNextEntry(ZipEntry(name).apply { setTimeLocal(appleValidationEvidenceTimestamp) })
                source.inputStream().use { input -> input.copyTo(output) }
                output.closeEntry()
            }
        }
        verifyAppleValidationEvidenceArchive(temporary, expected)
        verifyAppleValidationEvidenceSources(namedRoots, sources, expected)
        requireApplePackagePathWithoutSymlinks(destination, "validation evidence archive")
        check(!Files.exists(destination.toPath(), NOFOLLOW_LINKS)) {
            "Apple validation evidence archive already exists"
        }
        Files.createLink(destination.toPath(), temporary.toPath())
        Files.delete(temporary.toPath())
        requireApplePackagePathWithoutSymlinks(destination, "validation evidence archive")
        check(Files.isRegularFile(destination.toPath(), NOFOLLOW_LINKS)) {
            "Apple validation evidence archive publication is unsafe"
        }
        verifyAppleValidationEvidenceArchive(destination, expected)
        verifyAppleValidationEvidenceSources(namedRoots, sources, expected)
    } finally {
        Files.deleteIfExists(temporary.toPath())
    }
}

private fun collectAppleValidationEvidenceSources(namedRoots: List<Pair<String, File>>): Map<String, File> {
    val sources = linkedMapOf<String, File>()
    namedRoots.forEach { (name, source) ->
        requireApplePackagePathWithoutSymlinks(source, "validation evidence source")
        val sourcePath = source.toPath()
        when {
            Files.isRegularFile(sourcePath, NOFOLLOW_LINKS) -> addAppleValidationEvidenceSource(sources, name, source)
            Files.isDirectory(sourcePath, NOFOLLOW_LINKS) -> {
                val files = verifiedRegularFiles(source).toSortedMap()
                check(files.isNotEmpty()) { "Apple validation evidence directory is empty: $name" }
                files.forEach { (relative, file) ->
                    addAppleValidationEvidenceSource(sources, "$name/$relative", file)
                }
            }
            else -> error("Apple validation evidence source is missing or unsafe: $source")
        }
    }
    return sources
}

private fun addAppleValidationEvidenceSource(sources: MutableMap<String, File>, name: String, source: File) {
    requireSafeAppleValidationEvidencePath(name)
    check(sources.put(name, source) == null) { "Duplicate Apple validation evidence archive member: $name" }
}

private fun requireSafeAppleValidationEvidencePath(path: String) {
    check(path.isNotEmpty() && !path.startsWith('/') && '\\' !in path &&
        path.split('/').all { component ->
            component.isNotEmpty() && component != "." && component != ".." &&
                component.none { it.isISOControl() || it == ':' } &&
                String(component.toByteArray(UTF_8), UTF_8) == component
        }) {
        "Unsafe Apple validation evidence archive path: $path"
    }
}

private fun appleValidationEvidencePathContains(parent: String, child: String) =
    child == parent || child.startsWith("$parent/")

private fun requireDisjointAppleValidationEvidencePaths(sources: List<File>, archive: File) {
    val sourcePaths = sources.map(File::getCanonicalFile).map(File::toPath)
    sourcePaths.indices.forEach { left ->
        (left + 1 until sourcePaths.size).forEach { right ->
            check(!sourcePaths[left].startsWith(sourcePaths[right]) &&
                !sourcePaths[right].startsWith(sourcePaths[left])) {
                "Apple validation evidence sources overlap"
            }
        }
    }
    val output = archive.canonicalFile.toPath()
    check(sourcePaths.none { source -> output.startsWith(source) || source.startsWith(output) }) {
        "Apple validation evidence archive overlaps a source"
    }
}

private fun verifyAppleValidationEvidenceSources(
    namedRoots: List<Pair<String, File>>,
    sources: Map<String, File>,
    expected: Map<String, Pair<Long, String>>,
) {
    val current = collectAppleValidationEvidenceSources(namedRoots)
    check(sources.keys == expected.keys && current.keys == sources.keys && sources.all { (name, source) ->
        requireApplePackagePathWithoutSymlinks(source, "validation evidence source recheck")
        current.getValue(name).canonicalFile == source.canonicalFile &&
            Files.isRegularFile(source.toPath(), NOFOLLOW_LINKS) &&
            source.length() == expected.getValue(name).first &&
            source.releaseDigest() == expected.getValue(name).second
    }) { "Apple validation evidence sources changed while archiving" }
}

private fun verifyAppleValidationEvidenceArchive(archive: File, expected: Map<String, Pair<Long, String>>) {
    ZipFile(archive).use { zip ->
        val entries = buildList {
            val values = zip.entries()
            while (values.hasMoreElements()) add(values.nextElement())
        }
        check(entries.map { it.name } == expected.keys.sortedWith { left, right ->
            compareAppleValidationEvidenceNames(left, right)
        } &&
            entries.none { it.isDirectory }) {
            "Apple validation evidence archive inventory differs"
        }
        entries.forEach { entry ->
            val record = expected.getValue(entry.name)
            check(entry.size == record.first && zip.getInputStream(entry).use { it.releaseDigest() } == record.second) {
                "Apple validation evidence archive member differs: ${entry.name}"
            }
        }
    }
}

private fun compareAppleValidationEvidenceNames(left: String, right: String): Int {
    val leftBytes = left.toByteArray(UTF_8)
    val rightBytes = right.toByteArray(UTF_8)
    repeat(minOf(leftBytes.size, rightBytes.size)) { index ->
        val difference = (leftBytes[index].toInt() and 0xff) - (rightBytes[index].toInt() and 0xff)
        if (difference != 0) return difference
    }
    return leftBytes.size - rightBytes.size
}
