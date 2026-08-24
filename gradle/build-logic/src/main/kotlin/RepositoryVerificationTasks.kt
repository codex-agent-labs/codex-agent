import org.gradle.api.Project
import org.gradle.kotlin.dsl.register

internal val repositoryVerificationTaskPaths = listOf(
    ":codex-agent-core:jvmTest",
    ":codex-agent-core:auditCrossLanguageBindingParity",
    ":codex-agent-core:compileAndroidMain",
    ":codex-agent-core:compileKotlinJs",
    ":codex-agent-core:compileKotlinWasmJs",
    ":codex-agent-core:compileKotlinMacosArm64",
    ":codex-agent-core:compileKotlinMacosX64",
    ":codex-agent-core:compileKotlinLinuxArm64",
    ":codex-agent-core:compileKotlinLinuxX64",
    ":codex-agent-core:compileKotlinMingwX64",
    ":codex-agent-core:verifyProtocolSource",
    ":codex-agent-runtime-android:testDebugUnitTest",
    ":codex-agent-runtime-android:lintRelease",
    ":codex-agent-runtime-android:assembleRelease",
    ":codex-agent-runtime-desktop:jvmTest",
    ":codex-agent-runtime-desktop:macosArm64Test",
    ":codex-agent-runtime-desktop:compileKotlinMacosX64",
    ":codex-agent-runtime-desktop:compileKotlinLinuxArm64",
    ":codex-agent-runtime-desktop:compileKotlinLinuxX64",
    ":codex-agent-runtime-desktop:compileKotlinMingwX64",
    ":codex-agent-runtime-desktop:jsNodeTest",
    ":codex-agent-runtime-desktop:wasmJsNodeTest",
    ":tooling:protocol-generator:test",
)

fun Project.registerRepositoryVerificationTasks() {
    tasks.register("verifyRepository") {
        group = "verification"
        description = "Runs all client compilations, desktop/Android runtime checks, protocol, and build-logic checks."
        dependsOn(
            repositoryVerificationTaskPaths,
            gradle.includedBuild("build-logic").task(":test"),
        )
    }
    tasks.register("verifyIosRuntime") {
        group = "verification"
        description = "Runs the embedded iOS runtime, XCFramework, and Swift consumer gates on macOS."
        dependsOn(":codex-agent-runtime-ios:verifyIosRuntime")
    }
}
