@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import com.android.build.api.dsl.KotlinMultiplatformAndroidLibraryTarget
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsEnvSpec

plugins {
    kotlin("multiplatform") version "2.3.10"
    id("com.android.kotlin.multiplatform.library") version "9.2.1" apply false
}

val codexAgentSdkVersion = providers.gradleProperty("codexAgent.sdkVersion").get()
val consumerTarget = providers.gradleProperty("codexAgent.consumerTarget").get()
check(consumerTarget in setOf(
    "android",
    "jvm",
    "ios-arm64",
    "ios-simulator-arm64",
    "macos-arm64",
    "macos-x64",
    "linux-arm64",
    "linux-x64",
    "windows-x64",
    "node-js",
    "node-wasm",
)) { "Unsupported SDK facade consumer target: $consumerTarget" }

if (consumerTarget == "android") pluginManager.apply("com.android.kotlin.multiplatform.library")

kotlin {
    when (consumerTarget) {
        "android" -> (targets.getByName("android") as KotlinMultiplatformAndroidLibraryTarget).apply {
            namespace = "io.github.codex_agent_labs.codexagent.sdkfacadeconsumer"
            compileSdk = 37
            minSdk = 26
        }
        "jvm" -> jvm()
        "ios-arm64" -> iosArm64()
        "ios-simulator-arm64" -> iosSimulatorArm64()
        "macos-arm64" -> macosArm64()
        "macos-x64" -> macosX64()
        "linux-arm64" -> linuxArm64()
        "linux-x64" -> linuxX64()
        "windows-x64" -> mingwX64()
        "node-js" -> js { nodejs() }
        "node-wasm" -> wasmJs { nodejs() }
    }

    sourceSets {
        commonMain.dependencies {
            implementation("io.github.codex-agent-labs:codex-agent:$codexAgentSdkVersion")
        }
    }
}

if (consumerTarget == "node-js") extensions.configure<NodeJsEnvSpec> { download.set(false) }
if (consumerTarget == "node-wasm") extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }
