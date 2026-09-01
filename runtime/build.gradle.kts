import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.js.nodejs.NodeJsRootPlugin
import org.jetbrains.kotlin.gradle.targets.js.npm.NpmExtension
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsEnvSpec
import org.jetbrains.kotlin.gradle.targets.wasm.nodejs.WasmNodeJsRootPlugin
import org.jetbrains.kotlin.gradle.targets.wasm.npm.WasmNpmExtension

plugins {
    base
    alias(libs.plugins.kotlin.multiplatform) apply false
    alias(libs.plugins.maven.publish) apply false
}

group = "io.github.codex-agent-labs"
version = providers.gradleProperty("codexAgent.runtimeVersion").get()
layout.buildDirectory.set(file("build"))

extensions.extraProperties.apply {
    set("codexAgent.repositoryUrl", "https://github.com/codex-agent-labs/codex-agent")
    set("codexAgent.repositoryRoot", rootProject.projectDir.parentFile)
    set("codexAgent.contractVersion", providers.gradleProperty("codexAgent.contractVersion").get())
    set("codexAgent.runtimeVersion", version.toString())
}

subprojects {
    group = rootProject.group
    version = rootProject.version
}

val desktopRuntime = project(":codex-agent-runtime-desktop")
val requestedProduct = providers.gradleProperty("codexAgent.product")
val requestedComponent = providers.gradleProperty("codexAgent.component")
val requestedPhase = providers.gradleProperty("codexAgent.phase")
val runtimePhaseTasks = mapOf(
    ("macos-arm64" to "binary") to "writeMacosArm64RuntimeBinaryOutputManifest",
    ("macos-x64" to "binary") to "writeMacosX64RuntimeBinaryOutputManifest",
    ("linux-arm64" to "binary") to "writeLinuxArm64RuntimeBinaryOutputManifest",
    ("linux-x64" to "binary") to "writeLinuxX64RuntimeBinaryOutputManifest",
    ("windows-x64" to "binary") to "writeMingwX64RuntimeBinaryOutputManifest",
    ("jvm" to "binary") to "writeJvmRuntimeBinaryOutputManifest",
    ("node-js" to "binary") to "writeNodeJsRuntimeBinaryOutputManifest",
    ("node-wasm" to "binary") to "writeNodeWasmRuntimeBinaryOutputManifest",
    ("macos-arm64" to "package") to "writeMacosArm64RuntimePackageOutputManifest",
    ("macos-x64" to "package") to "writeMacosX64RuntimePackageOutputManifest",
    ("linux-arm64" to "package") to "writeLinuxArm64RuntimePackageOutputManifest",
    ("linux-x64" to "package") to "writeLinuxX64RuntimePackageOutputManifest",
    ("windows-x64" to "package") to "writeMingwX64RuntimePackageOutputManifest",
    ("jvm" to "package") to "writeJvmRuntimePackageOutputManifest",
    ("node-js" to "package") to "writeNodeJsRuntimePackageOutputManifest",
    ("node-wasm" to "package") to "writeNodeWasmRuntimePackageOutputManifest",
    ("macos-arm64" to "validation") to "writeMacosArm64RuntimeValidationOutputManifest",
    ("macos-x64" to "validation") to "writeMacosX64RuntimeValidationOutputManifest",
    ("linux-arm64" to "validation") to "writeLinuxArm64RuntimeValidationOutputManifest",
    ("linux-x64" to "validation") to "writeLinuxX64RuntimeValidationOutputManifest",
    ("windows-x64" to "validation") to "writeMingwX64RuntimeValidationOutputManifest",
    ("jvm" to "validation") to "writeJvmRuntimeValidationOutputManifest",
    ("node-js" to "validation") to "writeNodeJsRuntimeValidationOutputManifest",
    ("node-wasm" to "validation") to "writeNodeWasmRuntimeValidationOutputManifest",
    ("macos-arm64" to "metadata") to "writeMacosArm64RuntimeMetadataOutputManifest",
    ("macos-x64" to "metadata") to "writeMacosX64RuntimeMetadataOutputManifest",
    ("linux-arm64" to "metadata") to "writeLinuxArm64RuntimeMetadataOutputManifest",
    ("linux-x64" to "metadata") to "writeLinuxX64RuntimeMetadataOutputManifest",
    ("windows-x64" to "metadata") to "writeMingwX64RuntimeMetadataOutputManifest",
    ("jvm" to "metadata") to "writeJvmRuntimeMetadataOutputManifest",
    ("node-js" to "metadata") to "writeNodeJsRuntimeMetadataOutputManifest",
    ("node-wasm" to "metadata") to "writeNodeWasmRuntimeMetadataOutputManifest",
)
tasks.register("ciProductPhase") {
    group = "build"
    description = "Executes one exact Desktop Runtime component/phase lifecycle mapping."
    dependsOn(provider {
        check(requestedProduct.get() == "runtime") { "Standalone Runtime accepts only product=runtime" }
        val component = requestedComponent.get()
        val phase = requestedPhase.get()
        val target = providers.gradleProperty("codexAgent.target").get()
        check(target == component) { "Runtime target must match component: $component" }
        val taskName = runtimePhaseTasks[component to phase]
            ?: error("Unsupported Runtime phase: $component/$phase for target $target")
        desktopRuntime.tasks.named(taskName)
    })
}

tasks.register("verifyRuntime") {
    group = "verification"
    description = "Verifies the exact selected Desktop Runtime lifecycle through its metadata handoff."
    dependsOn(provider {
        val target = providers.gradleProperty("codexAgent.target").get()
        desktopRuntime.tasks.named(checkNotNull(runtimePhaseTasks[target to "metadata"]) {
            "Unsupported Runtime verification target: $target"
        })
    })
}

rootProject.plugins.withType<NodeJsRootPlugin> {
    rootProject.extensions.getByType(NpmExtension::class.java).lockFileDirectory.set(
        rootProject.layout.projectDirectory.dir("gradle/kotlin-js-store"),
    )
}
rootProject.plugins.withType<WasmNodeJsRootPlugin> {
    rootProject.extensions.getByType(WasmNpmExtension::class.java).lockFileDirectory.set(
        rootProject.layout.projectDirectory.dir("gradle/kotlin-js-store/wasm"),
    )
}
rootProject.plugins.withType<NodeJsRootPlugin> {
    rootProject.extensions.configure<NodeJsEnvSpec> { download.set(false) }
}
rootProject.plugins.withType<WasmNodeJsRootPlugin> {
    rootProject.extensions.configure<WasmNodeJsEnvSpec> { download.set(false) }
}
