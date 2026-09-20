import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.file.Directory
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations
import org.gradle.work.DisableCachingByDefault

internal fun appleDeviceValidationCommand(workDirectory: File) = listOf(
    "/usr/bin/xcodebuild",
    "-project", "CodexAgentTestApp.xcodeproj",
    "-scheme", "CodexAgentTestApp",
    "-configuration", "Release",
    "-destination", "generic/platform=iOS",
    "-derivedDataPath", workDirectory.resolve("derived-data").absolutePath,
    "-archivePath", workDirectory.resolve("CodexAgentTestApp.xcarchive").absolutePath,
    "ARCHS=arm64",
    "CODE_SIGNING_ALLOWED=NO",
    "SKIP_INSTALL=NO",
    "clean",
    "archive",
)

/** Executes one device consumer over caller-authenticated package inputs; it grants no host authority. */
internal fun verifyAppleDeviceConsumer(
    testApplicationDirectory: File,
    packageDirectory: File,
    developerDirectory: File,
    workDirectory: File,
    processes: ExecOperations,
) {
    val inputs = listOf(testApplicationDirectory, packageDirectory)
    val paths = inputs + developerDirectory
    (paths + workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "device consumer")
    }
    val testApplication = testApplicationDirectory.canonicalFile
    val packageRoot = packageDirectory.canonicalFile
    val developer = developerDirectory.canonicalFile
    val work = workDirectory.canonicalFile
    check(testApplication.name == "CodexAgentTestApp" && packageRoot.name == "CodexAgentPackage" &&
        testApplication.parentFile == packageRoot.parentFile) {
        "Apple device consumer inputs must use the exact sibling layout"
    }
    check(developer.isDirectory && !Files.isSymbolicLink(developer.toPath())) {
        "Apple device consumer developer directory is missing or unsafe"
    }
    requireOriginalAppleSnapshotDisjoint(work, listOf(testApplication, packageRoot, developer))
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple device consumer work directory must be fresh"
    }
    fun inventory(root: File, label: String) = verifiedRegularFiles(root).also { files ->
        check(files.isNotEmpty() && files.values.all { it.length() > 0L }) {
            "Apple device consumer $label is empty or unsafe"
        }
    }
    fun digests(root: File, label: String) = inventory(root, label).mapValues { (_, file) -> file.releaseDigest() }
    val testDigests = digests(testApplication, "test application")
    val packageDigests = digests(packageRoot, "package")
    check("CodexAgentTestApp.xcodeproj/project.pbxproj" in testDigests && "Package.swift" in packageDigests) {
        "Apple device consumer required project or package manifest is missing"
    }

    try {
        processes.captureReleaseProcess(
            appleDeviceValidationCommand(work),
            workingDirectory = testApplication,
            environmentVariables = mapOf(
                "LC_ALL" to "C",
                "LANG" to "C",
                "DEVELOPER_DIR" to developer.absolutePath,
            ),
            captureDirectory = work.resolve("raw/xcodebuild"),
        )
        val archiveFiles = inventory(work.resolve("CodexAgentTestApp.xcarchive"), "archive")
        check(archiveFiles.values.all { it.length() > 0L }) {
            "Apple device consumer archive is empty"
        }
    } finally {
        paths.forEach { requireApplePackagePathWithoutSymlinks(it, "device consumer input recheck") }
        check(digests(testApplication, "test application recheck") == testDigests &&
            digests(packageRoot, "package recheck") == packageDigests && developer.isDirectory &&
            !Files.isSymbolicLink(developer.toPath())) {
            "Apple device consumer input changed during execution"
        }
    }
}

@DisableCachingByDefault(because = "The exact device consumer must execute on every selected Apple host")
abstract class VerifyAppleDeviceConsumerTask @Inject constructor(
    private val processes: ExecOperations,
) : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val testApplicationDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageDirectory: DirectoryProperty
    // The prerequisite verifies the live toolchain; do not fingerprint the entire Xcode installation.
    @get:Internal
    abstract val developerDirectory: DirectoryProperty
    @get:Input
    val developerDirectoryPath: String get() = developerDirectory.get().asFile.absolutePath
    @get:OutputDirectory abstract val workDirectory: DirectoryProperty

    @get:Internal
    val commandLine: List<String> get() = appleDeviceValidationCommand(workDirectory.get().asFile)

    @get:Internal
    val rawEvidenceDirectory: Provider<Directory> get() = workDirectory.dir("raw")

    @get:Internal
    val archiveDirectory: Provider<Directory> get() = workDirectory.dir("CodexAgentTestApp.xcarchive")

    init {
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun verify() {
        verifyAppleDeviceConsumer(
            testApplicationDirectory.get().asFile,
            packageDirectory.get().asFile,
            developerDirectory.get().asFile,
            workDirectory.get().asFile,
            processes,
        )
    }
}
