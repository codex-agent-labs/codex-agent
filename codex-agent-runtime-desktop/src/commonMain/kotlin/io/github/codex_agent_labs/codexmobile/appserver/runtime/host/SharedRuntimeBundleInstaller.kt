package io.github.codex_agent_labs.codexmobile.appserver.runtime.host

import kotlin.random.Random
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import okio.Path.Companion.toPath

internal class SharedRuntimeBundleInstaller(
    bundleDirectory: String,
    dataDirectory: String,
    private val descriptor: RuntimeBundleDescriptor,
    private val files: ExternalHostFiles,
) {
    private val bundleDirectory = bundleDirectory
    private val dataDirectory = dataDirectory

    suspend fun install(): InstalledRuntime = installationLock.withLock {
        validateRuntimeBundleDescriptor(descriptor)
        require(files.isAbsolute(bundleDirectory) && files.isAbsolute(dataDirectory)) {
            "Runtime bundle and data directories must be absolute"
        }
        val bundleRoot = files.canonicalize(bundleDirectory)
        require(files.metadataOrNull(bundleRoot)?.let { it.directory && !it.symbolicLink } == true) {
            "Runtime bundle directory is unavailable"
        }
        val archivePath = files.joinPath(bundleRoot, archiveName())
        val archiveMetadata = files.metadataOrNull(archivePath)
        require(archiveMetadata?.let { it.regularFile && !it.symbolicLink } == true) {
            "Runtime bundle '${files.baseName(archivePath)}' is unavailable"
        }
        require(archiveMetadata.size in MIN_RUNTIME_ZIP_BYTES..MAX_RUNTIME_ARCHIVE_BYTES) {
            "Runtime ZIP size is invalid"
        }
        val archiveBytes = files.readFileSnapshot(archivePath, MAX_RUNTIME_ARCHIVE_BYTES)
        val zipMembers = inspectRuntimeZip(archiveBytes)
        val manifestMember = zipMembers.singleOrNull { it.name == RUNTIME_MANIFEST_NAME }
            ?: throw IllegalArgumentException("Runtime ZIP manifest is missing")
        require(manifestMember.size in 1..MAX_RUNTIME_MANIFEST_BYTES.toLong()) {
            "Runtime manifest size is invalid"
        }

        val archive = files.openRuntimeArchive(archiveBytes, zipMembers)
        var failure: Throwable? = null
        try {
            val manifestBytes = archive.read(manifestMember, MAX_RUNTIME_MANIFEST_BYTES.toLong())
            require(manifestBytes.size.toLong() == manifestMember.size) { "Runtime ZIP manifest is corrupt" }
            val manifest = parseRuntimeBundleManifest(manifestBytes)
            validateRuntimeBundleManifest(descriptor, manifest, zipMembers)
            installValidated(archive, manifest, manifestBytes)
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            closePreservingFailure(archive, failure)
        }
    }

    private fun installValidated(
        archive: RuntimeArchive,
        manifest: RuntimeBundleManifest,
        manifestBytes: ByteArray,
    ): InstalledRuntime {
        files.createDirectories(dataDirectory)
        val installationRoot = files.canonicalize(dataDirectory)
        require(files.metadataOrNull(installationRoot)?.let { it.directory && !it.symbolicLink } == true) {
            "Runtime data directory is unavailable"
        }
        val runtimesDirectory = managedDirectory(installationRoot, "runtimes")
        val versionDirectory = managedDirectory(runtimesDirectory, descriptor.libraryVersion)
        val installedDirectory = files.joinPath(versionDirectory, descriptor.target)

        if (validInstallation(installedDirectory, manifest, manifestBytes)) {
            cleanCompletedDebris(versionDirectory)
            return installedRuntime(installedDirectory, manifest)
        }
        cleanStaging(versionDirectory)

        val token = installToken()
        val staging = files.joinPath(versionDirectory, ".${descriptor.target}.staging-$token")
        val displaced = files.joinPath(versionDirectory, ".${descriptor.target}.corrupt-$token")
        require(files.metadataOrNull(staging) == null && files.metadataOrNull(displaced) == null) {
            "Runtime installation transaction already exists"
        }
        files.createDirectory(staging)
        requireSafeDirectory(staging)

        var failure: Throwable? = null
        try {
            files.writeNewFile(files.joinPath(staging, RUNTIME_MANIFEST_NAME), manifestBytes)
            manifest.members.forEach { member ->
                val target = files.joinPath(staging, member.name)
                archive.extract(member, target)
                val metadata = files.metadataOrNull(target)
                require(metadata?.let {
                    it.regularFile && !it.symbolicLink && it.size == member.size
                } == true && files.isCanonical(target) && files.sha256(target) == member.sha256) {
                    "Extracted runtime member '${member.name}' is corrupt"
                }
                if (member.executable) files.makeExecutable(target)
            }
            check(validInstallation(staging, manifest, manifestBytes)) { "Staged runtime validation failed" }

            val hadInstalled = files.metadataOrNull(installedDirectory) != null
            if (hadInstalled) {
                try {
                    files.move(installedDirectory, displaced)
                } catch (displacement: Throwable) {
                    val committed = try {
                        files.metadataOrNull(installedDirectory) == null &&
                            files.metadataOrNull(displaced) != null
                    } catch (probe: Throwable) {
                        displacement.addSuppressed(probe)
                        throw displacement
                    }
                    if (!committed) throw displacement
                }
            }
            try {
                files.move(staging, installedDirectory)
            } catch (promotion: Throwable) {
                try {
                    if (!validInstallation(installedDirectory, manifest, manifestBytes) &&
                        hadInstalled && files.metadataOrNull(installedDirectory) == null &&
                        files.metadataOrNull(displaced) != null) {
                        files.move(displaced, installedDirectory)
                    }
                } catch (recovery: Throwable) {
                    promotion.addSuppressed(recovery)
                }
                if (!validInstallation(installedDirectory, manifest, manifestBytes)) throw promotion
            }
            check(validInstallation(installedDirectory, manifest, manifestBytes)) {
                "Installed runtime validation failed"
            }
            cleanCompletedDebris(versionDirectory)
            return installedRuntime(installedDirectory, manifest)
        } catch (error: Throwable) {
            failure = error
            throw error
        } finally {
            deletePreservingFailure(staging, failure)
        }
    }

    private fun managedDirectory(parent: String, name: String): String {
        val directory = files.joinPath(parent, name)
        files.createDirectories(directory)
        requireSafeDirectory(directory)
        return directory
    }

    private fun requireSafeDirectory(directory: String) {
        require(files.metadataOrNull(directory)?.let { it.directory && !it.symbolicLink } == true &&
            files.isCanonical(directory)) { "Runtime installation directory is unsafe" }
    }

    private fun validInstallation(
        directory: String,
        manifest: RuntimeBundleManifest,
        manifestBytes: ByteArray,
    ): Boolean = runCatching {
        check(files.metadataOrNull(directory)?.let { it.directory && !it.symbolicLink } == true)
        check(files.isCanonical(directory))
        check(files.list(directory).toSet() ==
            manifest.members.map(RuntimeBundleMember::name).toSet() + RUNTIME_MANIFEST_NAME)
        val installedManifestPath = files.joinPath(directory, RUNTIME_MANIFEST_NAME)
        check(files.metadataOrNull(installedManifestPath)?.let {
            it.regularFile && !it.symbolicLink && it.size == manifestBytes.size.toLong()
        } == true)
        check(files.readFileSnapshot(installedManifestPath, manifestBytes.size.toLong()).contentEquals(manifestBytes))
        manifest.members.forEach { member ->
            val path = files.joinPath(directory, member.name)
            check(files.metadataOrNull(path)?.let {
                it.regularFile && !it.symbolicLink && it.size == member.size
            } == true)
            check(files.isCanonical(path) && files.sha256(path) == member.sha256)
            if (member.executable) files.makeExecutable(path)
        }
        true
    }.getOrDefault(false)

    private fun cleanStaging(versionDirectory: String) {
        files.list(versionDirectory)
            .filter { it.startsWith(".${descriptor.target}.staging-") }
            .forEach { files.deleteRecursively(files.joinPath(versionDirectory, it)) }
    }

    private fun cleanCompletedDebris(versionDirectory: String) {
        runCatching {
            files.list(versionDirectory)
                .filter {
                    it.startsWith(".${descriptor.target}.staging-") ||
                        it.startsWith(".${descriptor.target}.corrupt-")
                }
                .forEach { path -> runCatching { files.deleteRecursively(files.joinPath(versionDirectory, path)) } }
        }
    }

    private fun deletePreservingFailure(path: String, primary: Throwable?) {
        try {
            if (files.metadataOrNull(path) == null) return
            files.deleteRecursively(path)
        } catch (cleanup: Throwable) {
            if (primary == null) throw cleanup
            primary.addSuppressed(cleanup)
        }
    }

    private fun installedRuntime(directory: String, manifest: RuntimeBundleManifest) = InstalledRuntime(
        appServer = files.joinPath(directory, descriptor.appServerName).toPath(),
        supervisor = files.joinPath(directory, descriptor.supervisorName).toPath(),
        supervisorSha256 = manifest.members.single { it.name == descriptor.supervisorName }.sha256,
    )

    private fun archiveName(): String =
        "codex-agent-runtime-desktop-${descriptor.libraryVersion}-${descriptor.classifier}.zip"

    private companion object {
        // ponytail: one process-wide lock; add an OS lock if shared cross-process data roots are supported.
        val installationLock = Mutex()
    }
}

internal fun validateRuntimeBundleDescriptor(descriptor: RuntimeBundleDescriptor) {
    listOf(descriptor.libraryVersion, descriptor.appServerVersion, descriptor.target, descriptor.classifier)
        .forEach { identity ->
            require(identity != "." && identity != ".." && identity.matches(Regex("[A-Za-z0-9._-]+"))) {
                "Runtime identity is invalid"
            }
        }
    require(descriptor.appServerName.isSafeRuntimeMemberName() &&
        descriptor.supervisorName.isSafeRuntimeMemberName() &&
        descriptor.appServerName != descriptor.supervisorName) { "Runtime executable names are invalid" }
    require(descriptor.appServerSha256.matches(Regex("[0-9a-f]{64}"))) {
        "Runtime App Server checksum is invalid"
    }
}

internal fun validateRuntimeBundleManifest(
    descriptor: RuntimeBundleDescriptor,
    manifest: RuntimeBundleManifest,
    zipMembers: List<RuntimeZipMember>,
) {
    require(manifest.libraryVersion == descriptor.libraryVersion &&
        manifest.appServerVersion == descriptor.appServerVersion &&
        manifest.target == descriptor.target && manifest.classifier == descriptor.classifier) {
        "Runtime manifest identity does not match the current target"
    }
    val expectedNames = setOf(
        descriptor.appServerName,
        descriptor.supervisorName,
        RUNTIME_LICENSE_NAME,
        RUNTIME_NOTICE_NAME,
    )
    require(expectedNames.size == 4 && manifest.members.size == 4 &&
        manifest.members.map(RuntimeBundleMember::name).toSet() == expectedNames) {
        "Runtime manifest member set is invalid"
    }
    require(zipMembers.size == 5 &&
        zipMembers.map(RuntimeZipMember::name).toSet() == expectedNames + RUNTIME_MANIFEST_NAME) {
        "Runtime ZIP has missing or extra members"
    }
    val zipSizes = zipMembers.associate { it.name to it.size }
    manifest.members.forEach { member ->
        require(member.name.isSafeRuntimeMemberName() && member.size > 0 &&
            member.sha256.matches(Regex("[0-9a-f]{64}")) && zipSizes[member.name] == member.size) {
            "Runtime manifest member '${member.name}' is invalid"
        }
    }
    require(manifest.members.single { it.name == descriptor.appServerName }.sha256 ==
        descriptor.appServerSha256) { "Runtime manifest App Server checksum is invalid" }
    require(manifest.members.filter(RuntimeBundleMember::executable).map(RuntimeBundleMember::name).toSet() ==
        setOf(descriptor.appServerName, descriptor.supervisorName)) {
        "Runtime manifest executable set is invalid"
    }
}

private fun installToken(): String = Random.nextLong().toString().replace('-', '0')

private fun closePreservingFailure(archive: RuntimeArchive, primary: Throwable?) {
    try {
        archive.close()
    } catch (cleanup: Throwable) {
        if (primary == null) throw cleanup
        primary.addSuppressed(cleanup)
    }
}

private const val MIN_RUNTIME_ZIP_BYTES = 22L
