pluginManagement {
    includeBuild("gradle/build-logic")
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "codex-agent"

include(
    ":codex-agent-core",
    ":codex-agent-runtime-android",
    ":codex-agent-runtime-desktop",
    ":codex-agent-runtime-ios",
    ":tooling:android-runtime-evidence",
    ":tooling:protocol-generator",
)
