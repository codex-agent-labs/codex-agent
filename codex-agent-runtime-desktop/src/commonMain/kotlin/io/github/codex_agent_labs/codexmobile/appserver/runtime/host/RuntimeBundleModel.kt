package io.github.codex_agent_labs.codexmobile.appserver.runtime.host

import okio.Path

/**
 * The compiled distribution pins the App Server hash. Once the caller verifies
 * the signed Maven classifier (or independently authenticates those exact
 * bytes) and protects the bundle directory from writes, that delivery
 * authenticates the supervisor and legal files; the installer itself verifies
 * no signature. The internal manifest binds and re-verifies those members.
 */
internal data class RuntimeBundleDescriptor(
    val libraryVersion: String,
    val appServerVersion: String,
    val target: String,
    val classifier: String,
    val appServerName: String,
    val appServerSha256: String,
    val supervisorName: String,
)

internal data class InstalledRuntime(
    val appServer: Path,
    val supervisor: Path,
    val supervisorSha256: String,
)
