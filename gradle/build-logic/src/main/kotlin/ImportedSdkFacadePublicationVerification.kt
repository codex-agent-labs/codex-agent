import java.io.File
import java.nio.file.Files
import kotlinx.serialization.json.JsonObject

/**
 * Pure imported-byte adaptation to the existing facade/BOM dependency verifier.
 * The caller authenticates this original package and the supplied version policy.
 * No compiler, Gradle API, process, source publication or receipt authority is used.
 * Only a fresh private temporary directory is written, then removed on every exit.
 */
internal fun verifyImportedSdkFacadePublicationMetadata(
    packageStage: File,
    contractVersion: String,
    runtimeVersion: String,
    sdkVersion: String,
    kotlinVersion: String,
    forbiddenPath: String = "",
): JsonObject {
    requireApplePackagePathWithoutSymlinks(packageStage, "facade package")
    fun inventory(): Map<String, String> {
        requireApplePackagePathWithoutSymlinks(packageStage, "facade package")
        return verifiedRegularFiles(packageStage).mapValues { (_, file) -> file.releaseDigest() }
    }
    val before = inventory()
    val temporary = Files.createTempDirectory("imported-facade-publications-").toFile()
    try {
        requireOriginalAppleSnapshotDisjoint(temporary, listOf(packageStage))
        val group = CodexAgentBuild.MAVEN_GROUP
        val maven = packageStage.resolve("outputs/maven/${group.replace('.', '/')}")
        val publications = facadePublicationSpecs.map { it.artifact to "facade/${it.publication}" } +
            ("codex-agent-bom" to "bom")
        publications.forEach { (artifact, destination) ->
            listOf("pom" to "pom-default.xml", "module" to "module.json").forEach { (extension, name) ->
                val original = maven.resolve("$artifact/$sdkVersion/$artifact-$sdkVersion.$extension")
                check(original.toPath() == original.toPath().normalize() &&
                    original.toPath().startsWith(maven.toPath())) { "Facade metadata path escapes its original package" }
                requireApplePackagePathWithoutSymlinks(original, "facade publication metadata")
                val copied = temporary.resolve("$destination/$name")
                copied.parentFile.mkdirs()
                Files.copy(original.toPath(), copied.toPath())
                check(original.releaseDigest() == copied.releaseDigest()) { "Facade metadata changed during capture" }
            }
        }
        val result = verifyFacadePublicationContract(temporary.resolve("facade"), temporary.resolve("bom"),
            group, contractVersion, runtimeVersion, sdkVersion, kotlinVersion, forbiddenPath)
        check(inventory() == before) { "Imported facade package changed during metadata verification" }
        return result
    } finally {
        temporary.deleteRecursively()
        check(inventory() == before) { "Imported facade package changed during metadata verification" }
    }
}
