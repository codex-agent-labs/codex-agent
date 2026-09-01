internal const val ANDROID_RUNTIME_TEST_CLASS =
    "io.github.codex_agent_labs.codexagent.app.runtime.bootstrap.RuntimeBootstrapDeviceTest"
internal const val APK_RUNTIME_ENTRY = "lib/arm64-v8a/libcodex_app_server.so"
internal const val AAR_RUNTIME_ENTRY = "jni/arm64-v8a/libcodex_app_server.so"

internal val REQUIRED_ANDROID_RUNTIME_TESTS = setOf(
    "javaHostLifecycleIsObservableAndIdempotentlyCloseable",
    "missingNonExecutableAndCorruptOverridesFailClosed",
    "successfulRuntimeInstallsCertificatePrivacyAndCleanupPolicies",
)

internal data class AndroidManifestIdentity(
    val applicationId: String,
    val instrumentationTargetPackage: String,
)
