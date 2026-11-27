import java.io.File
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.time.LocalDateTime
import org.apache.commons.compress.archivers.zip.Zip64Mode
import org.apache.commons.compress.archivers.zip.ZipArchiveEntry
import org.apache.commons.compress.archivers.zip.ZipArchiveOutputStream
import org.gradle.api.internal.file.copy.CopyAction
import org.gradle.api.tasks.WorkResults
import org.gradle.api.tasks.bundling.Zip
import javax.inject.Inject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.ListProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.Optional
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations

internal fun deleteReleaseTree(file: File) {
    if (!Files.exists(file.toPath(), LinkOption.NOFOLLOW_LINKS)) return
    Files.walk(file.toPath()).use { paths ->
        paths.sorted(Comparator.reverseOrder()).forEach(Files::delete)
    }
}

internal fun withAppleArchivePolicy(policyFile: File, action: () -> Unit) {
    fun canonical(value: kotlinx.serialization.json.JsonElement): kotlinx.serialization.json.JsonElement = when (value) {
        is kotlinx.serialization.json.JsonObject -> kotlinx.serialization.json.JsonObject(
            value.toSortedMap().mapValues { canonical(it.value) })
        is kotlinx.serialization.json.JsonArray -> kotlinx.serialization.json.JsonArray(value.map(::canonical))
        else -> value
    }
    fun identity(file: File): Map<String, Any> {
        check(Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS) && file.length() > 0) { "Apple codec file must be regular and nonempty" }
        check(file.absoluteFile.normalize() == file.canonicalFile) { "Symbolic Apple codec input: $file" }
        return Files.readAttributes(file.toPath(), "unix:dev,ino,size,lastModifiedTime,ctime", LinkOption.NOFOLLOW_LINKS)
    }
    fun digest(value: String): String {
        check(Regex("sha256:[0-9a-f]{64}").matches(value)) { "Invalid Apple codec digest" }
        return value
    }
    val policyIdentity = identity(policyFile)
    check(policyFile.length() in 1..65536) { "Apple codec policy is oversized or empty" }
    val raw = policyFile.readText(Charsets.UTF_8)
    val policy = policyFile.readReleaseObject()
    check(raw == kotlinx.serialization.json.Json.encodeToString(
        kotlinx.serialization.json.JsonElement.serializer(), canonical(policy)) + "\n") {
        "Apple codec policy must use exact canonical JSON"
    }
    check(policy.keys == setOf("schemaVersion", "runner", "javaArchiveSha256", "javaRuntime", "javaFiles", "commonsCompress") &&
        policy.releaseInt("schemaVersion") == 1) { "Unsupported Apple codec policy" }
    digest(policy.releaseString("javaArchiveSha256")) // Independently verified image provenance; the selected files are checked below.
    val system = when (System.getProperty("os.name")) { "Linux" -> "Linux"; "Mac OS X" -> "macOS"; else -> error("Unsupported Apple codec host") }
    val arch = when (System.getProperty("os.arch")) { "amd64", "x86_64" -> "X64"; "aarch64", "arm64" -> "ARM64"; else -> error("Unsupported Apple codec architecture") }
    val runner = policy.releaseObject("runner")
    check(runner.keys == setOf("os", "arch") && runner.releaseString("os") == system && runner.releaseString("arch") == arch) {
        "Apple codec host differs from source policy"
    }
    val javaHome = File(System.getProperty("java.home")).canonicalFile
    val javaLauncher = javaHome.resolve("bin/java")
    check(File(ProcessHandle.current().info().command().orElseThrow()).canonicalFile == javaLauncher.canonicalFile) {
        "Apple codec Java home differs from the actual process launcher"
    }
    val javaFiles = policy.releaseArray("javaFiles").map { it as kotlinx.serialization.json.JsonObject }
    val paths = javaFiles.map { it.releaseString("relativePath") }
    val suffix = if (system == "Linux") ".so" else ".dylib"
    check(paths == paths.sorted().distinct() && paths.size == 7 &&
        paths.containsAll(listOf("bin/java", "lib/modules", "release")) &&
        paths.map { it.substringAfterLast('/') }.containsAll(listOf("libjava", "libjli", "libzip", "libjvm").map { it + suffix })) {
        "Apple codec policy must bind the exact Java and bundled compression files"
    }
    val held = linkedMapOf<File, Map<String, Any>>(policyFile to policyIdentity)
    val observedHashes = linkedMapOf<String, String>()
    javaFiles.forEach { record ->
        check(record.keys == setOf("relativePath", "bytes", "sha256")) { "Unexpected Apple runtime file fields" }
        val relative = record.releaseString("relativePath")
        check(relative.split('/').all { it.isNotEmpty() && it != "." && it != ".." } && '\\' !in relative) {
            "Unsafe Apple runtime file path"
        }
        val file = javaHome.resolve(relative)
        held[file] = identity(file)
        check(record.releaseLong("bytes") > 0 && file.length() == record.releaseLong("bytes")) { "Apple runtime file length differs" }
        val observed = "sha256:" + file.releaseDigest()
        check(observed == digest(record.releaseString("sha256"))) { "Apple runtime file differs: $relative" }
        observedHashes[relative] = observed
    }
    val actualRuntime = mapOf(
        "arch" to System.getProperty("os.arch"), "binarySha256" to observedHashes.getValue("bin/java"),
        "runtimeVersion" to System.getProperty("java.runtime.version"), "vendor" to System.getProperty("java.vendor"),
        "vendorVersion" to System.getProperty("java.vendor.version", ""), "vmName" to System.getProperty("java.vm.name"),
        "vmVersion" to System.getProperty("java.vm.version"),
    )
    val expectedRuntime = policy.releaseObject("javaRuntime")
    check(expectedRuntime.keys == actualRuntime.keys && actualRuntime.all { (key, value) -> expectedRuntime.releaseString(key) == value }) {
        "Apple Java identity differs from source policy"
    }
    val codec = policy.releaseObject("commonsCompress")
    check(codec.keys == setOf("version", "resources")) { "Unexpected Apple ZIP codec fields" }
    val codecClass = ZipArchiveOutputStream::class.java
    val origin = codecClass.protectionDomain.codeSource.location
    val codecFile = File(origin.toURI())
    held[codecFile] = identity(codecFile)
    val names = listOf("ZipArchiveEntry", "ZipArchiveOutputStream", "ZipUtil")
    names.forEach { name ->
        val type = Class.forName("org.apache.commons.compress.archivers.zip.$name", false, codecClass.classLoader)
        check(type.protectionDomain.codeSource.location == origin) { "Apple ZIP codec classes have mixed origins" }
    }
    val pom = "META-INF/maven/org.apache.commons/commons-compress/pom.properties"
    val required = (listOf(pom) + names.map { "org/apache/commons/compress/archivers/zip/$it.class" }).sorted()
    val resources = codec.releaseArray("resources").map { it as kotlinx.serialization.json.JsonObject }
    check(resources.map { it.releaseString("relativePath") } == required) { "Apple ZIP codec resource set differs" }
    resources.forEach { record ->
        check(record.keys == setOf("relativePath", "bytes", "sha256")) { "Unexpected Apple codec resource fields" }
        val name = record.releaseString("relativePath")
        val size = record.releaseLong("bytes")
        check(size in 1..1_048_576) { "Apple codec resource size is invalid" }
        val bytes = checkNotNull(codecClass.classLoader.getResourceAsStream(name)).use { it.readNBytes(size.toInt() + 1) }
        check(bytes.size.toLong() == size && "sha256:" + bytes.inputStream().releaseDigest() == digest(record.releaseString("sha256"))) {
            "Apple ZIP codec differs: $name"
        }
        if (name == pom) {
            val properties = java.util.Properties().apply { bytes.inputStream().use { load(it) } }
            check(properties.getProperty("groupId") == "org.apache.commons" && properties.getProperty("artifactId") == "commons-compress" &&
                properties.getProperty("version") == codec.releaseString("version")) { "Apple ZIP codec version differs" }
        }
    }
    fun unchanged() {
        check(held.all { (file, before) -> identity(file) == before } && policyFile.readText(Charsets.UTF_8) == raw) {
            "Apple codec inputs changed during package production"
        }
    }
    unchanged()
    try { action() } finally { unchanged() }
}

/** iOS package ZIP v1: sorted UTF-8 paths, fixed modes/time and DEFLATED level 9.
 * This is an explicit package-input change, not a claim to reproduce old Gradle ZIP headers.
 */
internal fun writeAppleSdkZip(files: Map<String, File>, archive: File) {
    check(files.isNotEmpty()) { "Apple package archive is empty" }
    requireApplePackagePathWithoutSymlinks(archive, "Apple ZIP output")
    val entries = files.toSortedMap()
    entries.forEach { (name, file) ->
        check(name.isNotEmpty() && '\\' !in name && name.split('/').all { it.isNotEmpty() && it != "." && it != ".." } &&
            name.none { it.code < 32 || it.code == 127 }) { "Unsafe Apple ZIP entry: $name" }
        requireApplePackagePathWithoutSymlinks(file, "Apple ZIP input")
        check(Files.isRegularFile(file.toPath(), LinkOption.NOFOLLOW_LINKS) && file.length() > 0) {
            "Apple ZIP input must be a nonempty regular file"
        }
        requireOriginalAppleSnapshotDisjoint(archive, listOf(file))
    }
    val directories = sortedSetOf<String>()
    entries.keys.forEach { name ->
        var parent = name.substringBeforeLast('/', "")
        while (parent.isNotEmpty()) {
            check(parent !in entries) { "Apple ZIP file/directory collision: $parent" }
            directories += "$parent/"
            parent = parent.substringBeforeLast('/', "")
        }
    }
    archive.parentFile.mkdirs()
    val temporary = Files.createTempFile(archive.parentFile.toPath(), ".apple-package-", ".zip")
    try {
        Files.newOutputStream(temporary).buffered().use { raw ->
            ZipArchiveOutputStream(raw).use { zip ->
                zip.setEncoding("UTF-8")
                zip.setUseLanguageEncodingFlag(true)
                zip.setCreateUnicodeExtraFields(ZipArchiveOutputStream.UnicodeExtraFieldPolicy.NEVER)
                zip.setFallbackToUTF8(true)
                zip.setUseZip64(Zip64Mode.AsNeeded)
                zip.setMethod(ZipArchiveOutputStream.DEFLATED)
                zip.setLevel(9)
                (directories + entries.keys).sorted().forEach { name ->
                    val file = entries[name]
                    val before = file?.let { Files.readAttributes(it.toPath(), java.nio.file.attribute.BasicFileAttributes::class.java,
                        LinkOption.NOFOLLOW_LINKS) }
                    val entry = ZipArchiveEntry(name).apply {
                        setTimeLocal(LocalDateTime.of(1980, 1, 1, 0, 0))
                        unixMode = if (file == null) 493 else 420 // 0755 / 0644, independent of umask.
                        size = before?.size() ?: 0L
                    }
                    zip.putArchiveEntry(entry)
                    if (file != null) {
                        val copied = file.inputStream().use { it.copyTo(zip) }
                        val after = Files.readAttributes(file.toPath(), java.nio.file.attribute.BasicFileAttributes::class.java,
                            LinkOption.NOFOLLOW_LINKS)
                        check(copied == before!!.size() && after.isRegularFile && before.size() == after.size() &&
                            before.fileKey() == after.fileKey() && before.lastModifiedTime() == after.lastModifiedTime()) {
                            "Apple ZIP input changed during encoding"
                        }
                    }
                    zip.closeArchiveEntry()
                }
            }
        }
        Files.move(temporary, archive.toPath(), StandardCopyOption.REPLACE_EXISTING)
    } finally {
        Files.deleteIfExists(temporary)
    }
}

/** Preserve the public Zip provider/archive properties while using the standalone encoder exactly once. */
@CacheableTask
abstract class CanonicalAppleZip : Zip() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val archivePolicy: RegularFileProperty

    init { archivePolicy.convention(project.rootProject.layout.projectDirectory.file("gradle/release/toolchains/sdk/ios-package.json")) }
    override fun createCopyAction(): CopyAction = CopyAction { stream ->
        val files = linkedMapOf<String, File>()
        stream.process { detail ->
            if (!detail.isDirectory) {
                val name = detail.relativePath.pathString
                check(files.put(name, detail.file) == null) { "Duplicate Apple ZIP entry: $name" }
            }
        }
        withAppleArchivePolicy(archivePolicy.get().asFile) { writeAppleSdkZip(files, archiveFile.get().asFile) }
        WorkResults.didWork(true)
    }
}

internal fun appleSdkArchiveEncoderIdentity(): String = listOf(
    ZipArchiveOutputStream::class.java.name,
    ZipArchiveOutputStream::class.java.`package`.implementationVersion ?: "unspecified",
    ZipArchiveOutputStream::class.java.protectionDomain.codeSource?.location?.toExternalForm() ?: "unavailable",
    System.getProperty("java.runtime.version"),
).joinToString("|")

/** Fixed producer over private, caller-authenticated inputs. This grants no receipt or host authority. */
object AppleSdkPackageMain {
    @JvmStatic fun main(arguments: Array<String>) {
        check(arguments.size == 11) { "Expected fixed Apple package arguments" }
        withAppleArchivePolicy(File(arguments[10])) { produce(arguments) }
    }

    private fun produce(arguments: Array<String>) {
        val version = arguments[0]
        check(PRODUCT_SEMVER.matches(version)) { "Invalid Apple package version" }
        val binary = File(arguments[1])
        val source = File(arguments[2])
        val compatibility = File(arguments[3])
        val work = File(arguments[4])
        val output = File(arguments[5])
        val developer = File(arguments[6])
        val inputs = listOf(binary, source, compatibility, developer)
        (inputs + work + output).forEach { requireApplePackagePathWithoutSymlinks(it, "standalone Apple package") }
        check(binary.isDirectory && source.isDirectory && compatibility.isFile && developer.isDirectory) {
            "Standalone Apple package input is missing"
        }
        requireOriginalAppleSnapshotDisjoint(work, inputs + output)
        requireOriginalAppleSnapshotDisjoint(output, inputs)
        check(!work.exists() && !output.exists()) { "Standalone Apple package outputs must be fresh" }
        check(work.mkdirs() && output.mkdirs()) { "Cannot create Apple package outputs" }
        val environment = mapOf("PATH" to "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL" to "C", "LANG" to "C",
            "HOME" to work.path, "TMPDIR" to work.path, "DEVELOPER_DIR" to developer.canonicalPath)
        fun run(command: List<String>): Pair<Int, String> {
            check(command.first() in setOf("/usr/bin/xcodebuild", "/usr/bin/xcrun", "/usr/bin/plutil", "/usr/bin/grep")) {
                "Unsupported Apple packaging tool"
            }
            val log = work.resolve("tool-output.txt")
            val process = ProcessBuilder(command).directory(work).redirectErrorStream(true).redirectOutput(log).apply {
                environment().clear()
                environment().putAll(environment)
            }.start()
            process.outputStream.close()
            val code = process.waitFor()
            val text = log.readText()
            println("Apple packaging command: ${command.joinToString(" ")} exit=$code")
            print(text)
            return code to text
        }
        fun capture(command: List<String>): String {
            val (code, text) = run(command)
            return requireSuccessfulReleaseProcess(command, code, text, "")
        }
        fun toolchain() = verifyAppleToolchainOutput(capture(listOf("/usr/bin/xcodebuild", "-version")),
            capture(listOf("/usr/bin/xcrun", "swift", "--version")), arguments[7], arguments[8], arguments[9])
        toolchain()
        val device = binary.resolve("ios-arm64/CodexAgent.framework")
        val simulator = binary.resolve("ios-simulator-arm64/CodexAgent.framework")
        verifyImportedAppleFramework(device, "iPhoneOS", ::capture)
        verifyImportedAppleFramework(simulator, "iPhoneSimulator", ::capture)
        val release = work.resolve("CodexAgent.xcframework")
        capture(importedXCFrameworkAssemblyCommand(device, simulator, release))
        val apple = source.resolve("codex-agent-runtime-ios/apple")
        normalizeAppleReleaseXCFramework(release, apple.resolve("Sources/CodexAgentAuthentication/PrivacyInfo.xcprivacy"),
            listOf(work.canonicalPath, source.canonicalPath), ::capture, ::run)
        val packageFiles = linkedMapOf<String, File>()
        fun addTree(tree: File, prefix: String) = verifiedRegularFiles(tree).forEach { (name, file) ->
            check(packageFiles.put("$prefix/$name", file) == null) { "Duplicate Apple package source" }
        }
        addTree(apple.resolve("Sources"), "Sources")
        addTree(apple.resolve("Tests"), "Tests")
        addTree(release, "CodexAgent.xcframework")
        packageFiles.putAll(mapOf("Package.swift" to apple.resolve("Package.swift"), "LICENSE.txt" to source.resolve("LICENSE"),
            "THIRD_PARTY_NOTICES.md" to source.resolve("THIRD_PARTY_NOTICES.md"),
            "openai-codex-LICENSE.txt" to source.resolve("legal/openai-codex/openai-codex-LICENSE.txt"),
            "openai-codex-NOTICE.txt" to source.resolve("legal/openai-codex/openai-codex-NOTICE.txt"),
            "META-INF/codex-agent/sdk-compatibility.json" to compatibility))
        val swiftFiles = verifiedRegularFiles(release).mapKeys { "CodexAgent.xcframework/${it.key}" }.toMutableMap()
        listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
            check(swiftFiles.put("CodexAgent.xcframework/$slice/CodexAgent.framework/META-INF/codex-agent/sdk-compatibility.json",
                compatibility) == null) { "Apple framework was already decorated" }
        }
        println("Apple archive encoder: ${appleSdkArchiveEncoderIdentity()}")
        writeAppleSdkZip(packageFiles, output.resolve("CodexAgentPackage-$version.zip"))
        val swiftArchive = output.resolve("CodexAgent-$version.xcframework.zip")
        writeAppleSdkZip(swiftFiles, swiftArchive)
        Files.writeString(output.resolve("${swiftArchive.name}.sha256").toPath(), "${swiftArchive.releaseDigest()}\n",
            StandardOpenOption.CREATE_NEW)
        verifyAppleSdkCompatibility(verifiedRegularFiles(output), version, compatibility.releaseDigest())
        toolchain()
    }
}

internal fun copyReleaseTree(source: File, target: File) {
    check(source.isDirectory) { "Distribution source directory is missing: $source" }
    val sourcePath = source.toPath()
    Files.walk(sourcePath).use { stream ->
        stream.sorted(compareBy { sourcePath.relativize(it).nameCount }).forEach { path ->
            val destination = target.toPath().resolve(sourcePath.relativize(path))
            when {
                Files.isSymbolicLink(path) -> {
                    Files.createDirectories(destination.parent)
                    Files.deleteIfExists(destination)
                    Files.createSymbolicLink(destination, Files.readSymbolicLink(path))
                }
                Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS) -> Files.createDirectories(destination)
                else -> {
                    Files.createDirectories(destination.parent)
                    Files.copy(path, destination, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES)
                }
            }
        }
    }
}

private fun copyReleaseFile(source: File, target: File) {
    check(source.isFile) { "Distribution source file is missing: $source" }
    Files.createDirectories(target.toPath().parent)
    Files.copy(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.COPY_ATTRIBUTES)
}

internal data class AppleDistributionInputs(
    val packageManifest: File,
    val sources: File,
    val tests: File,
    val xcframework: File,
    val license: File,
    val thirdPartyNotices: File,
    val codexLicense: File,
    val codexNotice: File,
    val sdkCompatibility: File?,
    val testApplication: File,
)

internal fun stageAppleDistribution(inputs: AppleDistributionInputs, distribution: File) {
    deleteReleaseTree(distribution)
    val packageDirectory = distribution.resolve("CodexAgentPackage")
    Files.createDirectories(packageDirectory.toPath())
    copyReleaseFile(inputs.packageManifest, packageDirectory.resolve("Package.swift"))
    copyReleaseTree(inputs.sources, packageDirectory.resolve("Sources"))
    copyReleaseTree(inputs.tests, packageDirectory.resolve("Tests"))
    copyReleaseTree(inputs.xcframework, packageDirectory.resolve("CodexAgent.xcframework"))
    copyReleaseFile(inputs.license, packageDirectory.resolve("LICENSE.txt"))
    copyReleaseFile(inputs.thirdPartyNotices, packageDirectory.resolve("THIRD_PARTY_NOTICES.md"))
    copyReleaseFile(inputs.codexLicense, packageDirectory.resolve("openai-codex-LICENSE.txt"))
    copyReleaseFile(inputs.codexNotice, packageDirectory.resolve("openai-codex-NOTICE.txt"))
    inputs.sdkCompatibility?.let {
        copyReleaseFile(it, packageDirectory.resolve("META-INF/codex-agent/sdk-compatibility.json"))
    }
    copyReleaseTree(inputs.testApplication, distribution.resolve("CodexAgentTestApp"))
}

internal fun sortedAvailableLibraries(json: String): String {
    val libraries = releaseJson.parseToJsonElement(json) as? JsonArray
        ?: error("XCFramework AvailableLibraries is not a JSON array")
    return JsonArray(libraries.sortedBy {
        (it as? JsonObject ?: error("XCFramework library is not an object")).releaseString("LibraryIdentifier")
    }).toString()
}

internal fun libtoolNormalizeCommand(archive: File, normalized: File) = listOf(
    "/usr/bin/xcrun", "libtool", "-static", "-D", "-no_warning_for_no_symbols",
    archive.absolutePath, "-o", normalized.absolutePath,
)

internal fun stripReleaseArchiveCommand(archive: File, stripped: File) = listOf(
    "/usr/bin/xcrun", "strip", "-S", "-x", "-o", stripped.absolutePath, archive.absolutePath,
)

internal fun pathPrefixScanCommand(archive: File, prefixes: List<String>) =
    listOf("/usr/bin/grep", "-a", "-F", "-q") + prefixes.flatMap { listOf("-e", it) } + archive.absolutePath

internal fun verifyPathPrefixScan(exitValue: Int, archive: File, prefixes: List<String>, stderr: String) {
    check(exitValue == 1) {
        if (exitValue == 0) {
            "Release archive ${archive.name} contains a machine-specific path from $prefixes"
        } else {
            "Failed to scan ${archive.name} for machine-specific paths: $stderr"
        }
    }
}

internal fun verifyPrivacyPlacement(xcframework: File, privacyManifest: File) {
    listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
        val packaged = xcframework.resolve("$slice/CodexAgent.framework/PrivacyInfo.xcprivacy")
        check(packaged.isFile && Files.mismatch(privacyManifest.toPath(), packaged.toPath()) == -1L) {
            "Privacy manifest is missing or changed in $slice"
        }
    }
}

internal fun verifyPackagedLicenses(
    sourceToPackaged: List<Pair<File, File>>,
    buildScript: File,
): String {
    sourceToPackaged.forEach { (source, packaged) ->
        check(source.isFile && packaged.isFile && Files.mismatch(source.toPath(), packaged.toPath()) == -1L) {
            "Packaged license differs from ${source.name}"
        }
    }
    check("GNU General Public License v3.0 or later" in buildScript.readText()) {
        "iOS publication is missing GPL metadata"
    }
    return sourceToPackaged.joinToString(separator = "", transform = { (_, packaged) ->
        "${packaged.releaseDigest()}  ${packaged.absolutePath}\n"
    })
}

private fun moveReleaseFile(source: File, target: File) {
    try {
        Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE)
    } catch (_: AtomicMoveNotSupportedException) {
        Files.move(source.toPath(), target.toPath(), StandardCopyOption.REPLACE_EXISTING)
    }
}

/** Caller owns private input/output isolation and trusted toolchain identity; this is only the shared transform. */
internal fun prepareAppleReleaseXCFramework(
    assembled: File,
    release: File,
    privacyManifest: File,
    forbiddenAbsolutePathPrefixes: List<String>,
    capture: (List<String>) -> String,
    scan: (List<String>) -> Pair<Int, String>,
) {
    deleteReleaseTree(release)
    copyReleaseTree(assembled, release)
    normalizeAppleReleaseXCFramework(release, privacyManifest, forbiddenAbsolutePathPrefixes, capture, scan)
}

/** Normalize an already-private assembly in place; the original frameworks are never modified. */
internal fun normalizeAppleReleaseXCFramework(
    release: File,
    privacyManifest: File,
    forbiddenAbsolutePathPrefixes: List<String>,
    capture: (List<String>) -> String,
    scan: (List<String>) -> Pair<Int, String>,
) {
    listOf("ios-arm64", "ios-arm64-simulator").forEach { slice ->
        val framework = release.resolve("$slice/CodexAgent.framework")
        copyReleaseFile(privacyManifest, framework.resolve("PrivacyInfo.xcprivacy"))
        val archive = framework.resolve("CodexAgent")
        val stripped = framework.resolve("CodexAgent.stripped")
        val normalized = framework.resolve("CodexAgent.normalized")
        Files.deleteIfExists(stripped.toPath())
        Files.deleteIfExists(normalized.toPath())
        try {
            capture(stripReleaseArchiveCommand(archive, stripped))
            capture(libtoolNormalizeCommand(stripped, normalized))
            moveReleaseFile(normalized, archive)
            val (exitValue, stderr) = scan(pathPrefixScanCommand(archive, forbiddenAbsolutePathPrefixes))
            verifyPathPrefixScan(
                exitValue,
                archive,
                forbiddenAbsolutePathPrefixes,
                stderr,
            )
        } finally {
            Files.deleteIfExists(stripped.toPath())
            Files.deleteIfExists(normalized.toPath())
        }
    }
    verifyPrivacyPlacement(release, privacyManifest)
    val infoPlist = release.resolve("Info.plist")
    val libraries = capture(
        listOf("/usr/bin/plutil", "-extract", "AvailableLibraries", "json", "-o", "-", infoPlist.absolutePath),
    )
    capture(
        listOf(
            "/usr/bin/plutil", "-replace", "AvailableLibraries", "-json",
            sortedAvailableLibraries(libraries), infoPlist.absolutePath,
        ),
    )
}

@CacheableTask
abstract class PrepareCodexAgentReleaseXCFrameworkTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val assembledXCFrameworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val privacyManifest: RegularFileProperty
    @get:org.gradle.api.tasks.Input abstract val forbiddenAbsolutePathPrefixes: ListProperty<String>
    @get:org.gradle.api.tasks.Input abstract val appleToolchainIdentity: Property<String>
    @get:OutputDirectory abstract val releaseXCFrameworkDirectory: DirectoryProperty

    @TaskAction fun prepare() = prepareAppleReleaseXCFramework(
        assembledXCFrameworkDirectory.get().asFile,
        releaseXCFrameworkDirectory.get().asFile,
        privacyManifest.get().asFile,
        forbiddenAbsolutePathPrefixes.get(),
        capture = { processes.captureReleaseProcess(it) },
        scan = { command ->
            val stderr = java.io.ByteArrayOutputStream()
            val result = processes.exec {
                commandLine(command)
                environment("LC_ALL", "C")
                standardOutput = java.io.ByteArrayOutputStream()
                errorOutput = stderr
                isIgnoreExitValue = true
            }
            result.exitValue to stderr.toString()
        },
    )
}

@CacheableTask
abstract class StageCodexAgentAppleDistributionTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val packageManifest: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val sourcesDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val testsDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val xcframeworkDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val licenseFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val thirdPartyNotices: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val codexLicense: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val codexNotice: RegularFileProperty
    @get:Optional @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val testApplication: DirectoryProperty
    @get:OutputDirectory abstract val distributionDirectory: DirectoryProperty

    @TaskAction fun stage() = stageAppleDistribution(
        AppleDistributionInputs(
            packageManifest.get().asFile, sourcesDirectory.get().asFile, testsDirectory.get().asFile,
            xcframeworkDirectory.get().asFile, licenseFile.get().asFile, thirdPartyNotices.get().asFile,
            codexLicense.get().asFile, codexNotice.get().asFile,
            sdkCompatibility.orNull?.asFile, testApplication.get().asFile,
        ),
        distributionDirectory.get().asFile,
    )
}

@CacheableTask
abstract class VerifyIosLicensePackagingTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE) abstract val packageDirectory: DirectoryProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val licenseFile: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val thirdPartyNotices: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val codexLicense: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE) abstract val codexNotice: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.RELATIVE) abstract val buildScript: RegularFileProperty
    @get:OutputFile abstract val reportFile: RegularFileProperty

    @TaskAction fun verify() {
        val packageRoot = packageDirectory.get().asFile
        val report = verifyPackagedLicenses(
            listOf(
                licenseFile.get().asFile to packageRoot.resolve("LICENSE.txt"),
                thirdPartyNotices.get().asFile to packageRoot.resolve("THIRD_PARTY_NOTICES.md"),
                codexLicense.get().asFile to packageRoot.resolve("openai-codex-LICENSE.txt"),
                codexNotice.get().asFile to packageRoot.resolve("openai-codex-NOTICE.txt"),
            ),
            buildScript.get().asFile,
        )
        reportFile.get().asFile.apply {
            Files.createDirectories(toPath().parent)
            Files.writeString(toPath(), report, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING)
        }
    }
}
