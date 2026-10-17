import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption
import org.gradle.api.DefaultTask
import org.gradle.api.file.DirectoryProperty
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.InputFile
import org.gradle.api.tasks.Internal
import org.gradle.api.tasks.LocalState
import org.gradle.api.tasks.OutputDirectory
import org.gradle.api.tasks.PathSensitive
import org.gradle.api.tasks.PathSensitivity
import org.gradle.api.tasks.TaskAction

/** Stages trusted fresh Gradle package outputs; this task grants no source, host, receipt, or test authority. */
@CacheableTask
abstract class StageAppleBinaryPackageArtifactsTask : DefaultTask() {
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val applePackageArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val swiftPackageArchive: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val swiftPackageChecksum: RegularFileProperty
    @get:InputFile @get:PathSensitive(PathSensitivity.NONE)
    abstract val sdkCompatibility: RegularFileProperty
    @get:Input abstract val version: Property<String>
    @get:Internal abstract val ownedBuildDirectory: DirectoryProperty
    @get:LocalState abstract val workDirectory: DirectoryProperty
    @get:OutputDirectory abstract val outputDirectory: DirectoryProperty

    @TaskAction
    fun stage() = stageAppleBinaryPackageArtifacts(
        applePackageArchive.get().asFile,
        swiftPackageArchive.get().asFile,
        swiftPackageChecksum.get().asFile,
        sdkCompatibility.get().asFile,
        version.get(),
        ownedBuildDirectory.get().asFile,
        workDirectory.get().asFile,
        outputDirectory.get().asFile,
    )
}

internal fun stageAppleBinaryPackageArtifacts(
    applePackageArchive: File,
    swiftPackageArchive: File,
    swiftPackageChecksum: File,
    sdkCompatibility: File,
    version: String,
    ownedBuildDirectory: File,
    workDirectory: File,
    outputDirectory: File,
) {
    check(PRODUCT_SEMVER.matches(version)) { "Apple binary package version is invalid" }
    val inputs = listOf(
        applePackageArchive,
        swiftPackageArchive,
        swiftPackageChecksum,
        sdkCompatibility,
    )
    inputs.forEach { requireApplePackagePathWithoutSymlinks(it, "binary package input") }
    listOf(ownedBuildDirectory, workDirectory, outputDirectory).forEach {
        requireApplePackagePathWithoutSymlinks(it, "binary package owned")
    }
    val applePackage = applePackageArchive.canonicalFile
    val swiftPackage = swiftPackageArchive.canonicalFile
    val checksum = swiftPackageChecksum.canonicalFile
    val compatibility = sdkCompatibility.canonicalFile
    val canonicalInputs = listOf(applePackage, swiftPackage, checksum, compatibility)
    check(canonicalInputs.map { it.toPath() }.toSet().size == canonicalInputs.size &&
        canonicalInputs.all { it.isFile && it.length() > 0L && !Files.isSymbolicLink(it.toPath()) }) {
        "Apple binary package inputs must be distinct nonempty regular files"
    }
    check(applePackage.name == "CodexAgentPackage-$version.zip" &&
        swiftPackage.name == "CodexAgent-$version.xcframework.zip" &&
        checksum.name == "CodexAgent-$version.xcframework.zip.sha256") {
        "Apple binary package input filenames are invalid"
    }

    val owned = ownedBuildDirectory.canonicalFile
    val work = workDirectory.canonicalFile
    val output = outputDirectory.canonicalFile
    check(!owned.exists() || owned.isDirectory) {
        "Apple binary package owned build path is not a directory: $owned"
    }
    listOf(work, output).forEach { destination ->
        check(destination.toPath() != owned.toPath() && destination.toPath().startsWith(owned.toPath())) {
            "Apple binary package output is outside its owned build directory: $destination"
        }
        check(!Files.exists(destination.toPath(), LinkOption.NOFOLLOW_LINKS) ||
            !Files.isSymbolicLink(destination.toPath())) {
            "Apple binary package output is a symbolic link: $destination"
        }
        canonicalInputs.forEach { input ->
            check(!destination.toPath().startsWith(input.toPath()) &&
                !input.toPath().startsWith(destination.toPath())) {
                "Apple binary package output overlaps an input: $destination"
            }
        }
    }
    check(!work.toPath().startsWith(output.toPath()) && !output.toPath().startsWith(work.toPath())) {
        "Apple binary package work and output directories overlap"
    }

    owned.mkdirs()
    deleteReleaseTree(work)
    val captured = work.resolve("captured").apply { mkdirs() }
    val artifacts = linkedMapOf(
        applePackage.name to copyVerified(applePackage, captured.resolve(applePackage.name)),
        swiftPackage.name to copyVerified(swiftPackage, captured.resolve(swiftPackage.name)),
        checksum.name to copyVerified(checksum, captured.resolve(checksum.name)),
    )
    val capturedCompatibility = copyVerified(compatibility, captured.resolve("sdk-compatibility.json"))
    val capturedSwift = artifacts.getValue(swiftPackage.name)
    val capturedChecksum = artifacts.getValue(checksum.name)
    val snapshots = listOf(
        artifacts.getValue(applePackage.name),
        capturedSwift,
        capturedChecksum,
        capturedCompatibility,
    )
    fun inputsUnchanged(): Boolean {
        canonicalInputs.forEach { input ->
            requireApplePackagePathWithoutSymlinks(input, "binary package input recheck")
        }
        return canonicalInputs.zip(snapshots).all { (source, snapshot) ->
            source.isFile && source.length() > 0L && !Files.isSymbolicLink(source.toPath()) &&
                Files.mismatch(source.toPath(), snapshot.toPath()) == -1L
        }
    }
    check(capturedChecksum.readBytes().contentEquals("${capturedSwift.releaseDigest()}\n".toByteArray())) {
        "Apple binary package checksum is not exact"
    }
    verifyAppleSdkCompatibility(artifacts, version, capturedCompatibility.releaseDigest())
    check(inputsUnchanged()) {
        "Apple binary package input changed during verification"
    }

    deleteReleaseTree(output)
    output.mkdirs()
    artifacts.forEach { (name, source) -> copyVerified(source, output.resolve(name)) }
    val published = verifiedRegularFiles(output)
    check(published.keys == artifacts.keys && published.all { (name, file) ->
        Files.mismatch(file.toPath(), artifacts.getValue(name).toPath()) == -1L
    }) { "Apple binary package staged output changed" }
    check(inputsUnchanged()) {
        "Apple binary package input changed during publication"
    }
    deleteReleaseTree(work)
}
