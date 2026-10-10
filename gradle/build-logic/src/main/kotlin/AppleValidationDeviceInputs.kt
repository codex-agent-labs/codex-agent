import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import org.gradle.api.DefaultTask
import org.gradle.api.file.Directory
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.provider.Provider
import org.gradle.api.tasks.InputDirectory
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction
import org.gradle.work.DisableCachingByDefault

/** Copied caller-authenticated sources; this grants no source, receipt, host, or compiler authority. */
internal data class AppleValidationDeviceInputs(
    val testApplicationDirectory: File,
    val packageDirectory: File,
)

internal fun stageAppleValidationDeviceInputs(
    testApplicationDirectory: File,
    packageDirectory: File,
    workDirectory: File,
): AppleValidationDeviceInputs {
    val inputs = listOf(testApplicationDirectory, packageDirectory)
    (inputs + workDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "validation device input")
    }
    val testApplication = testApplicationDirectory.canonicalFile
    val packageRoot = packageDirectory.canonicalFile
    val work = workDirectory.canonicalFile
    check(testApplication.isDirectory && packageRoot.isDirectory) {
        "Apple validation device input is missing or unsafe"
    }
    check(!testApplication.toPath().startsWith(packageRoot.toPath()) &&
        !packageRoot.toPath().startsWith(testApplication.toPath())) {
        "Apple validation device inputs overlap"
    }
    requireOriginalAppleSnapshotDisjoint(work, listOf(testApplication, packageRoot))
    check(!Files.exists(work.toPath(), LinkOption.NOFOLLOW_LINKS)) {
        "Apple validation device work directory must be fresh"
    }

    fun inventory(root: File, label: String): Map<String, File> = verifiedRegularFiles(root).also { files ->
        check(files.isNotEmpty() && files.values.all { it.length() > 0L }) {
            "Apple validation device $label contains an empty or missing file"
        }
    }
    fun digests(files: Map<String, File>) = files.mapValues { (_, file) -> file.releaseDigest() }
    val testFiles = inventory(testApplication, "test application")
    val packageFiles = inventory(packageRoot, "package")
    check(testFiles["CodexAgentTestApp.xcodeproj/project.pbxproj"]?.length()?.let { it > 0L } == true) {
        "Apple validation device Xcode project is missing"
    }
    check(packageFiles["Package.swift"]?.length()?.let { it > 0L } == true) {
        "Apple validation device Package.swift is missing"
    }
    val testDigests = digests(testFiles)
    val packageDigests = digests(packageFiles)
    val stagedTestApplication = work.resolve("CodexAgentTestApp")
    val stagedPackage = work.resolve("CodexAgentPackage")
    testFiles.forEach { (path, source) -> copyVerified(source, stagedTestApplication.resolve(path)) }
    packageFiles.forEach { (path, source) -> copyVerified(source, stagedPackage.resolve(path)) }

    val copiedTestFiles = verifiedRegularFiles(stagedTestApplication)
    val copiedPackageFiles = verifiedRegularFiles(stagedPackage)
    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "validation device input recheck") }
    check(digests(copiedTestFiles) == testDigests && digests(copiedPackageFiles) == packageDigests &&
        digests(inventory(testApplication, "test application recheck")) == testDigests &&
        digests(inventory(packageRoot, "package recheck")) == packageDigests) {
        "Apple validation device input changed while staging"
    }
    return AppleValidationDeviceInputs(stagedTestApplication, stagedPackage)
}

@DisableCachingByDefault(because = "Validation must restage each authenticated Apple consumer invocation")
abstract class StageAppleValidationDeviceInputsTask : DefaultTask() {
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val testApplicationDirectory: DirectoryProperty
    @get:InputDirectory @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val packageDirectory: DirectoryProperty
    @get:OutputDirectory abstract val workDirectory: DirectoryProperty

    @get:Internal
    val stagedTestApplicationDirectory: Provider<Directory> get() = workDirectory.dir("CodexAgentTestApp")

    @get:Internal
    val stagedPackageDirectory: Provider<Directory> get() = workDirectory.dir("CodexAgentPackage")

    init {
        outputs.upToDateWhen { false }
    }

    @TaskAction
    fun stage() {
        stageAppleValidationDeviceInputs(
            testApplicationDirectory.get().asFile,
            packageDirectory.get().asFile,
            workDirectory.get().asFile,
        )
    }
}
