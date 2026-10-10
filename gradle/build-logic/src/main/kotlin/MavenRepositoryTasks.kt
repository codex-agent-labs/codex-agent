import java.io.File
import java.nio.file.Files
import javax.inject.Inject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.ConfigurableFileCollection
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFiles
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault
import org.gradle.process.ExecOperations

private enum class MavenProduct { CONTRACT, RUNTIME, SDK }

private data class MavenArtifactSpec(
    val artifactId: String,
    val suffixes: List<String>,
    val product: MavenProduct = MavenProduct.SDK,
)

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
    MavenArtifactSpec(
        "codex-agent-bom", listOf(".module", ".pom"),
    ),
    MavenArtifactSpec(
        "codex-agent-core",
        listOf("-javadoc.jar", "-kotlin-tooling-metadata.json", "-sources.jar", ".jar", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-android", listOf("-javadoc.jar", "-sources.jar", ".aar", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-iosarm64",
        listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-iossimulatorarm64",
        listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-jvm", listOf("-javadoc.jar", "-sources.jar", ".jar", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-linuxarm64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-linuxx64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-macosarm64",
        listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-macosx64",
        listOf("-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-mingwx64", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
    MavenArtifactSpec(
        "codex-agent-core-wasm-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"),
        MavenProduct.CONTRACT,
    ),
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
        ), MavenProduct.RUNTIME,
    ),
    MavenArtifactSpec("codex-agent-runtime-desktop-jvm", listOf("-javadoc.jar", "-sources.jar", ".jar", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-linuxarm64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-linuxx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-macosarm64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-macosx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-mingwx64", listOf("-cinterop-codexDesktop.klib", "-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-ios", listOf("-javadoc.jar", "-kotlin-tooling-metadata.json", "-sources.jar", ".jar", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-ios-iosarm64", listOf("-cinterop-codexAgentIos.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-ios-iossimulatorarm64", listOf("-cinterop-codexAgentIos.klib", "-javadoc.jar", "-metadata.jar", "-sources.jar", ".klib", ".module", ".pom")),
    MavenArtifactSpec("codex-agent-runtime-desktop-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
    MavenArtifactSpec("codex-agent-runtime-desktop-wasm-js", listOf("-javadoc.jar", "-sources.jar", ".klib", ".module", ".pom"), MavenProduct.RUNTIME),
)

private val sdkBinaryArtifactIds = mapOf(
    "sdk-core" to setOf(
        "codex-agent", "codex-agent-android", "codex-agent-iosarm64",
        "codex-agent-iossimulatorarm64", "codex-agent-js", "codex-agent-jvm",
        "codex-agent-linuxarm64", "codex-agent-linuxx64", "codex-agent-macosarm64",
        "codex-agent-macosx64", "codex-agent-mingwx64", "codex-agent-wasm-js",
        "codex-agent-bom",
    ),
    "sdk-android" to setOf("codex-agent-runtime-android"),
    "sdk-ios" to setOf(
        "codex-agent-runtime-ios", "codex-agent-runtime-ios-iosarm64",
        "codex-agent-runtime-ios-iossimulatorarm64",
    ),
)

internal val checksumAlgorithms = linkedMapOf(
    ".md5" to "MD5",
    ".sha1" to "SHA-1",
    ".sha256" to "SHA-256",
    ".sha512" to "SHA-512",
)

internal fun mavenArtifactVersion(artifactId: String, versions: ProductVersions): String =
    when (mavenArtifactSpecs.single { it.artifactId == artifactId }.product) {
        MavenProduct.CONTRACT -> versions.contract
        MavenProduct.RUNTIME -> versions.runtime
        MavenProduct.SDK -> versions.sdk
    }

internal fun expectedMavenPrimaryPaths(versions: ProductVersions): Set<String> = mavenArtifactSpecs.flatMap { spec ->
    val version = mavenArtifactVersion(spec.artifactId, versions)
    spec.suffixes.map { suffix ->
        "${spec.artifactId}/$version/${spec.artifactId}-$version$suffix"
    }
}.toSortedSet()

internal fun expectedSdkBinaryMavenPrimaryPaths(component: String, sdkVersion: String): Set<String> {
    val artifactIds = sdkBinaryArtifactIds[component]
        ?: error("Unsupported SDK Maven binary component: $component")
    return mavenArtifactSpecs.filter { it.artifactId in artifactIds }.flatMap { spec ->
        check(spec.product == MavenProduct.SDK) { "SDK binary component contains a non-SDK artifact" }
        spec.suffixes.map { suffix ->
            "${spec.artifactId}/$sdkVersion/${spec.artifactId}-$sdkVersion$suffix"
        }
    }.toSortedSet()
}

internal fun finalizeFreshSdkBinaryMavenRepository(
    repository: File,
    groupId: String,
    sdkVersion: String,
    component: String,
) {
    check(groupId == CodexAgentBuild.MAVEN_GROUP) { "Unexpected Maven group: $groupId" }
    val groupPath = groupId.replace('.', '/')
    val primaries = expectedSdkBinaryMavenPrimaryPaths(component, sdkVersion)
        .mapTo(sortedSetOf()) { "$groupPath/$it" }
    val metadata = sdkBinaryArtifactIds.getValue(component).mapTo(sortedSetOf()) {
        "$groupPath/$it/maven-metadata.xml"
    }
    val files = verifiedRegularFiles(repository)
    val hasMetadata = files.keys.any { it.substringAfterLast('/').startsWith("maven-metadata.xml") }
    val rawPrimaries = primaries + if (hasMetadata) metadata else emptySet()
    val expected = rawPrimaries.flatMapTo(sortedSetOf()) { primary ->
        listOf(primary) + checksumAlgorithms.keys.map { primary + it }
    }
    check(files.keys == expected) { "Fresh SDK Maven file set mismatch" }
    // Validate the entire fresh publication before removing only its discovery metadata.
    rawPrimaries.forEach { primary ->
        checksumAlgorithms.forEach { (suffix, algorithm) ->
            val digest = files.getValue(primary).releaseDigest(algorithm)
            check(files.getValue(primary + suffix).readText() in setOf(digest, "$digest\n")) {
                "Fresh SDK Maven checksum mismatch: $primary$suffix"
            }
        }
    }
    if (hasMetadata) metadata.forEach { primary ->
        (listOf(primary) + checksumAlgorithms.keys.map { primary + it }).forEach { path ->
            check(files.getValue(path).delete()) { "Cannot remove fresh SDK discovery metadata: $path" }
        }
    }
    primaries.forEach { primary ->
        checksumAlgorithms.forEach { (suffix, algorithm) ->
            files.getValue(primary + suffix).writeText(files.getValue(primary).releaseDigest(algorithm) + "\n")
        }
    }
}

internal fun verifySdkBinaryMavenRepository(
    repository: File,
    groupId: String,
    sdkVersion: String,
    component: String,
    inventory: File,
) {
    check(groupId == CodexAgentBuild.MAVEN_GROUP) { "Unexpected Maven group: $groupId" }
    val expectedPrimary = expectedSdkBinaryMavenPrimaryPaths(component, sdkVersion)
    val expectedIds = expectedPrimary.mapTo(sortedSetOf()) { it.substringBefore('/') }
    check(expectedIds == sdkBinaryArtifactIds.getValue(component).toSortedSet()) {
        "SDK Maven artifact authority is incomplete: $component"
    }
    val groupPath = groupId.replace('.', '/')
    val groupRoot = repository.resolve(groupPath)
    check(groupRoot.isDirectory) { "SDK Maven group is missing: $groupId" }
    val actualIds = groupRoot.listFiles().orEmpty().filter(File::isDirectory)
        .mapTo(sortedSetOf(), File::getName)
    check(actualIds == expectedIds) {
        "SDK Maven publication set mismatch: expected=$expectedIds actual=$actualIds"
    }

    val files = verifiedRegularFiles(repository)
    val expectedRootPrimary = expectedPrimary.mapTo(sortedSetOf()) { "$groupPath/$it" }
    val expectedPrimaryChecksums = expectedRootPrimary.flatMapTo(sortedSetOf()) { primary ->
        checksumAlgorithms.keys.map { suffix -> primary + suffix }
    }
    val expectedFiles = (expectedRootPrimary + expectedPrimaryChecksums).toSortedSet()
    val actualPaths = files.keys.toSortedSet()
    check(actualPaths == expectedFiles) {
        "SDK Maven file set mismatch: expected=$expectedFiles actual=$actualPaths"
    }
    expectedRootPrimary.forEach { relative ->
        val primary = files.getValue(relative)
        checksumAlgorithms.forEach { (suffix, algorithm) ->
            check(files.getValue(relative + suffix).readText() == primary.releaseDigest(algorithm) + "\n") {
                "SDK Maven checksum does not match its primary: $relative$suffix"
            }
        }
        if (relative.endsWith(".pom")) verifyGplPom(primary)
    }

    check(!inventory.canonicalFile.toPath().startsWith(repository.canonicalFile.toPath())) {
        "SDK Maven inventory must be outside the staged repository"
    }
    inventory.atomicWriteJson(buildJsonObject {
        put("schemaVersion", JsonPrimitive(1))
        put("product", JsonPrimitive("sdk"))
        put("component", JsonPrimitive(component))
        put("groupId", JsonPrimitive(groupId))
        put("sdkVersion", JsonPrimitive(sdkVersion))
        put("artifactIds", buildJsonArray { expectedIds.forEach { add(JsonPrimitive(it)) } })
        put("primaryArtifactCount", JsonPrimitive(expectedRootPrimary.size))
        put("files", buildJsonArray {
            expectedRootPrimary.forEach { relative ->
                val file = files.getValue(relative)
                add(buildJsonObject {
                    put("path", JsonPrimitive(relative))
                    put("bytes", JsonPrimitive(file.length()))
                    put("sha256", JsonPrimitive(file.releaseDigest()))
                })
            }
        })
    })
}

@DisableCachingByDefault(because = "Verifies a freshly published SDK Maven repository in place")
abstract class VerifySdkBinaryMavenRepositoryTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val repository: DirectoryProperty
    @get:Input abstract val groupId: Property<String>
    @get:Input abstract val sdkVersion: Property<String>
    @get:Input abstract val component: Property<String>
    @get:OutputFile abstract val inventory: RegularFileProperty
    @get:InputFiles @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val producerSources: ConfigurableFileCollection
    @get:Internal abstract val repositoryRoot: DirectoryProperty

    @TaskAction
    fun verify() {
        val directory = repository.get().asFile
        inventory.get().asFile.delete()
        finalizeFreshSdkBinaryMavenRepository(directory, groupId.get(), sdkVersion.get(), component.get())
        processes.exec {
            workingDir(repositoryRoot.get().asFile)
            environment("PYTHONDONTWRITEBYTECODE", "1")
            commandLine(
                "python3", "-m", "ci.products.sdk_maven", "--verify-only",
                "--source", directory.absolutePath,
                "--group-id", groupId.get(), "--version", sdkVersion.get(),
                "--component", component.get(),
            )
        }
        verifySdkBinaryMavenRepository(directory, groupId.get(), sdkVersion.get(), component.get(), inventory.get().asFile)
    }
}

internal fun verifyMavenRepository(
    repository: File,
    groupId: String,
    versions: ProductVersions,
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

    val expectedPrimary = expectedMavenPrimaryPaths(versions)
    val actualPrimary = actualIds.flatMap { artifactId ->
        val version = mavenArtifactVersion(artifactId, versions)
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
        put("schemaVersion", JsonPrimitive(4))
        put("groupId", JsonPrimitive(groupId))
        put("contractVersion", JsonPrimitive(versions.contract))
        put("runtimeVersion", JsonPrimitive(versions.runtime))
        put("sdkVersion", JsonPrimitive(versions.sdk))
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
