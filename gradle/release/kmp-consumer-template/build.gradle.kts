@file:OptIn(org.jetbrains.kotlin.gradle.ExperimentalWasmDsl::class)

import com.android.build.api.dsl.KotlinMultiplatformAndroidLibraryTarget
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsEnvSpec

plugins {
    kotlin("multiplatform") version "2.3.10"
    id("com.android.kotlin.multiplatform.library") version "9.2.1" apply false
}

val codexAgentSdkVersion = providers.gradleProperty("codexAgent.sdkVersion").get()
val codexAgentRuntimeVersion = providers.gradleProperty("codexAgent.runtimeVersion").get()
val consumerTarget = providers.gradleProperty("codexAgent.consumerTarget").get()
check(consumerTarget in setOf(
    "common", "android", "desktop", "ios-device", "ios-simulator", "node-js", "node-wasm",
)) { "Unsupported staged consumer target: $consumerTarget" }
if (consumerTarget == "android") pluginManager.apply("com.android.kotlin.multiplatform.library")

kotlin {
    when (consumerTarget) {
        "common" -> jvm()
        "android" -> (targets.getByName("android") as KotlinMultiplatformAndroidLibraryTarget).apply {
            namespace = "io.github.codex_agent_labs.codexagent.stagedconsumer"
            compileSdk = 37
            minSdk = 26
            withJava()
        }
        "desktop" -> {
            val desktopJvm = jvm()
            desktopJvm.compilations.getByName("main").defaultSourceSet {
                kotlin.srcDir("src/desktopMain/kotlin")
            }
            macosArm64()
            macosX64()
            linuxArm64()
            linuxX64()
            mingwX64()
        }
        "ios-device" -> iosArm64().binaries.framework { baseName = "StagedConsumer" }
        "ios-simulator" -> iosSimulatorArm64().binaries.framework { baseName = "StagedConsumer" }
        "node-js" -> js { nodejs() }
        "node-wasm" -> wasmJs { nodejs() }
    }

    sourceSets {
        commonMain.dependencies {
            implementation("io.github.codex-agent-labs:codex-agent:$codexAgentSdkVersion")
        }
        when (consumerTarget) {
            "common" -> Unit
            "android" -> androidMain.dependencies {
                implementation("io.github.codex-agent-labs:codex-agent-runtime-android:$codexAgentSdkVersion")
            }
            "desktop" -> {
                jvmMain {
                    dependencies {
                        implementation("io.github.codex-agent-labs:codex-agent-runtime-desktop-jvm:$codexAgentRuntimeVersion")
                    }
                }
                listOf(macosMain, linuxMain, mingwX64Main).forEach { sourceSet ->
                    sourceSet.configure {
                        kotlin.srcDir("src/desktopMain/kotlin")
                        dependencies {
                            implementation("io.github.codex-agent-labs:codex-agent-runtime-desktop:$codexAgentRuntimeVersion")
                        }
                    }
                }
            }
            "ios-device", "ios-simulator" -> iosMain.dependencies {
                implementation("io.github.codex-agent-labs:codex-agent-runtime-ios:$codexAgentSdkVersion")
            }
            "node-js" -> jsMain.dependencies {
                implementation("io.github.codex-agent-labs:codex-agent-runtime-desktop:$codexAgentRuntimeVersion")
            }
            "node-wasm" -> wasmJsMain {
                kotlin.srcDir("src/jsMain/kotlin")
                dependencies {
                    implementation("io.github.codex-agent-labs:codex-agent-runtime-desktop:$codexAgentRuntimeVersion")
                }
            }
        }
    }
}

if (consumerTarget == "desktop") {
    val compileDesktopJava = tasks.named<JavaCompile>("compileJvmMainJava") {
        source("src/desktopMain/java")
    }
    tasks.register<JavaExec>("runDesktopJavaConsumer") {
        dependsOn("jvmMainClasses")
        classpath(
            compileDesktopJava.flatMap { it.destinationDirectory },
            layout.buildDirectory.dir("classes/kotlin/jvm/main"),
            configurations.named("jvmRuntimeClasspath"),
        )
        mainClass.set("io.github.codex_agent_labs.codexagent.stagedconsumer.DesktopJavaConsumer")
    }
}

if (consumerTarget == "node-js") extensions.configure<NodeJsEnvSpec> { download.set(false) }
if (consumerTarget == "node-wasm") extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }
