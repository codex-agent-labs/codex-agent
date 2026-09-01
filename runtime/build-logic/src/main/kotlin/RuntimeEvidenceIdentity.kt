internal const val CODEX_AGENT_MAVEN_GROUP = "io.github.codex-agent-labs"
internal const val LINUX_ARM64_RUNTIME_EVIDENCE_TASK = ":build-logic:executeLinuxArm64RuntimeEvidenceBundle"

internal val PRODUCT_SEMVER = Regex(
    "(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)\\.(?:0|[1-9][0-9]*)" +
        "(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)" +
        "(?:\\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?" +
        "(?:\\+[0-9A-Za-z-]+(?:\\.[0-9A-Za-z-]+)*)?",
)

internal fun runtimeCompatibilityVersion(releaseVersion: String): String {
    check(PRODUCT_SEMVER.matches(releaseVersion) && '+' !in releaseVersion) {
        "Runtime compatibility requires canonical SemVer without build metadata: $releaseVersion"
    }
    val (major, minor) = releaseVersion.substringBefore('-').split('.').take(2)
    return "$major.$minor.0"
}
