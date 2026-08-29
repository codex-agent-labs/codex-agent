import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject

private data class MavenArtifactSpec(val artifactId: String, val suffixes: List<String>)

private val mavenArtifactSpecs = listOf(
    MavenArtifactSpec("codex-agent", listOf("-javadoc.jar", "-kotlin-tooling-metadata.json", "-sources.jar", ".jar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-android", listOf("-javadoc.jar", "-sources.jar", ".aar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-iosarm64", listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-iossimulatorarm64", listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-jvm", listOf("-javadoc.jar", "-sources.jar", ".jar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-linuxarm64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-linuxx64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-macosarm64", listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-macosx64", listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-mingwx64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-wasm-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-android", listOf("-javadoc.jar", "-sources.jar", ".aar", ".module", ".pom")),
    MavenArtifactSpec(
        "codex-agent-runtime-desktop",
        listOf(
            "-app-server-linux-arm64.zip",
            "-app-server-linux-x64.zip",
            "-app-server-macos-arm64.zip",
            "-app-server-macos-x64.zip",
            "-app-server-windows-x64.zip",
            "-c-abi-linux-arm64.zip",
            "-c-abi-linux-x64.zip",
            "-c-abi-macos-arm64.zip",
            "-c-abi-macos-x64.zip",
            "-c-abi-windows-x64.zip",
            "-javadoc.jar",
            "-kotlin-tooling-metadata.json",
            "-sources.jar",
            ".jar",
            ".module",
            ".pom",
        ),
    ),
    MavenArtifactSpec("codex-agent-runtime-desktop-jvm", listOf("-javadoc.jar", "-sources.jar", ".jar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-linuxarm64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-linuxx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-macosarm64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-macosx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-mingwx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-ios", listOf("-javadoc.jar", "-kotlin-tooling-metadata.json", "-sources.jar", ".jar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-ios-iosarm64", listOf("-cinterop-codexAgentIos.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-ios-iossimulatorarm64", listOf("-cinterop-codexAgentIos.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-wasm-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom")),
)

private val checksumAlgorithms = linkedMapOf(
    ".md5" to "MD5",
    ".sha1" to "SHA-1",
    ".sha256" to "SHA-256",
    ".sha512" to "SHA-512",
)

internal fun expectedMavenPrimaryPaths(version: String): Set<String> = mavenArtifactSpecs.flatMap { spec ->
    spec.suffixes.map { suffix ->
        "${spec.artifactId}/$version/${spec.artifactId}-$version$suffix"
    }
}.toSortedSet()

internal fun verifyMavenRepository(
    repository: File,
    groupId: String,
    version: String,
    requireSignatures: Boolean,
    inventory: File,
) {
    check(groupId == CodexAgentBuild.MAVEN_GROUP) { "Unexpected Maven group: $groupId" }
    val groupPath = groupId.replace('.', '/')
    val groupRoot = repository.resolve(groupPath)
    check(groupRoot.isDirectory) { "Maven group is missing: $groupId" }
    val expectedIds = mavenArtifactSpecs.mapTo(sortedSetOf(), MavenArtifactSpec::artifactId)
    val actualIds = groupRoot.listFiles().orEmpty().filter(File::isDirectory).mapTo(sortedSetOf(), File::getName)
    check(actualIds == expectedIds) { "Maven publication set mismatch: expected=$expectedIds actual=$actualIds" }

    val expectedPrimary = expectedMavenPrimaryPaths(version)
    val actualPrimary = actualIds.flatMap { artifactId ->
        val versionDirectory = groupRoot.resolve("$artifactId/$version")
        check(versionDirectory.isDirectory) { "$artifactId version $version is missing" }
        versionDirectory.listFiles().orEmpty().filter { it.isFile && !it.isMavenSidecar() }.map {
            it.relativeTo(groupRoot).invariantSeparatorsPath
        }
    }.toSortedSet()
    check(actualPrimary == expectedPrimary) {
        "Maven primary artifact set mismatch: expected=$expectedPrimary actual=$actualPrimary"
    }

    val expectedRootPrimary = expectedPrimary.mapTo(sortedSetOf()) { "$groupPath/$it" }
    expectedRootPrimary.forEach { relative ->
        val primary = repository.resolve(relative)
        checksumAlgorithms.forEach { (suffix, algorithm) ->
            val checksum = primary.releaseDigest(algorithm)
            primary.resolveSibling(primary.name + suffix).writeText("$checksum\n")
        }
        checksumAlgorithms.forEach { (suffix, algorithm) ->
            val sidecar = primary.resolveSibling(primary.name + suffix)
            check(sidecar.readText().trim() == primary.releaseDigest(algorithm)) {
                "${sidecar.name} does not match ${primary.name}"
            }
        }
        if (requireSignatures) {
            check(primary.resolveSibling(primary.name + ".asc").isFile) { "${primary.name}.asc is missing" }
        }
        if (primary.extension == "pom") verifyGplPom(primary)
    }

    check(!inventory.canonicalFile.toPath().startsWith(repository.canonicalFile.toPath())) {
        "Maven inventory must be outside the staged repository"
    }
    val expectedFiles = expectedRootPrimary.flatMapTo(sortedSetOf()) { primary ->
        buildList {
            add(primary)
            checksumAlgorithms.keys.forEach { add(primary + it) }
            if (requireSignatures) add("$primary.asc")
        }
    }
    val actualFiles = Files.walk(repository.toPath()).use { paths ->
        paths.filter(Files::isRegularFile).filter {
            centralExclusion(it.toFile()) == null
        }.map {
            repository.toPath().relativize(it).toString().replace(File.separatorChar, '/')
        }.toList().toSortedSet()
    }
    check(actualFiles == expectedFiles) {
        "Maven regular-file set mismatch: expected=$expectedFiles actual=$actualFiles"
    }
    val files = expectedFiles.map(repository::resolve)
    inventory.atomicWriteJson(buildJsonObject {
        put("schemaVersion", JsonPrimitive(3))
        put("groupId", JsonPrimitive(groupId))
        put("version", JsonPrimitive(version))
        put("artifactIds", buildJsonArray { expectedIds.forEach { add(JsonPrimitive(it)) } })
        put("primaryArtifactCount", JsonPrimitive(expectedRootPrimary.size))
        put("signaturesRequired", JsonPrimitive(requireSignatures))
        put("files", buildJsonArray {
            files.forEach { file ->
                val relative = file.relativeTo(repository).invariantSeparatorsPath
                add(buildJsonObject {
                    put("path", JsonPrimitive(relative))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                })
            }
        })
    })
}

private fun File.isMavenSidecar(): Boolean = name.endsWith(".asc") || checksumAlgorithms.keys.any(name::endsWith)

private fun verifyGplPom(pom: File) {
    val factory = secureDocumentBuilderFactory(namespaceAware = true)
    val licenses = factory.newDocumentBuilder().parse(pom).getElementsByTagNameNS("*", "license")
    val valid = (0 until licenses.length).map { licenses.item(it) }.any { license ->
        fun value(name: String): String = (license as org.w3c.dom.Element)
            .getElementsByTagNameNS("*", name).item(0)?.textContent.orEmpty().trim()
        value("name") == "GNU General Public License v3.0 or later" &&
            value("url") == "https://www.gnu.org/licenses/gpl-3.0.txt" &&
            value("distribution") == "repo"
    }
    check(valid) { "Maven POM has missing or changed licence metadata: ${pom.name}" }
}
