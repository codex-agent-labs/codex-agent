plugins {
    base
    alias(libs.plugins.android.kmp.library) apply false
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.kotlin.serialization) apply false
    alias(libs.plugins.maven.publish) apply false
    id("codexagent.contract-product") apply false
}

val contractVersion = file("gradle/release/versions/contract.txt").readText().trim()

allprojects {
    group = "io.github.codex-agent-labs"
    version = contractVersion
}

extra["codexAgent.repositoryUrl"] = "https://github.com/codex-agent-labs/codex-agent"

apply(plugin = "codexagent.contract-product")
