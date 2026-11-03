"""Deterministic Android validation and metadata content projections.

The caller must first authenticate the original package/AAR lineage and run the
complete protected Firebase semantic replay.  These ordinary dictionaries only
project those already-verified values; they grant no receipt, producer, source,
host, Firebase, tooling or reuse authority.
"""

from .inventory import (
    canonical_json_bytes, load_json_bytes, require_array, require_exact_keys,
    require_integer, require_semver, require_sha256,
)


ANDROID_RUNTIME_TEST_CLASS = (
    "io.github.codex_agent_labs.codexagent.app.runtime.bootstrap.RuntimeBootstrapDeviceTest"
)
ANDROID_RUNTIME_TESTS = (
    "javaHostLifecycleIsObservableAndIdempotentlyCloseable",
    "missingNonExecutableAndCorruptOverridesFailClosed",
    "successfulRuntimeInstallsCertificatePrivacyAndCleanupPolicies",
)


def validate_android_validation_content(value):
    """Validate exact deterministic shape, never original-execution authority."""
    value = require_exact_keys(value, {
        "schemaVersion", "kind", "component", "target", "sdkVersion",
        "packageOutputsDigest", "releaseAarSha256", "bundledRuntimeSha256",
        "testClassName", "executedTests", "result",
    }, "Android validation content")
    if (require_integer(value["schemaVersion"], "Android validation schema") != 1
            or value["kind"] != "sdk-android-validation-content"
            or value["component"] != "sdk-android" or value["target"] != "android"
            or value["testClassName"] != ANDROID_RUNTIME_TEST_CLASS
            or value["result"] != "passed"):
        raise ValueError("Android validation content identity is invalid")
    require_semver(value["sdkVersion"], "Android validation SDK version")
    for field in ("packageOutputsDigest", "releaseAarSha256", "bundledRuntimeSha256"):
        require_sha256(value[field], "Android validation " + field)
    if require_array(value["executedTests"], "Android validation executed tests") != \
            list(ANDROID_RUNTIME_TESTS):
        raise ValueError("Android validation content lacks the exact fixed Firebase tests")
    return load_json_bytes(canonical_json_bytes(value))


def android_validation_content(
    *, sdk_version, package_outputs_digest, release_aar_sha256,
    bundled_runtime_sha256,
):
    """Project values established by the full original Firebase/AAR gate."""
    return validate_android_validation_content({
        "schemaVersion": 1,
        "kind": "sdk-android-validation-content",
        "component": "sdk-android",
        "target": "android",
        "sdkVersion": require_semver(sdk_version, "Android validation SDK version"),
        "packageOutputsDigest": require_sha256(
            package_outputs_digest, "Android validation package outputs"),
        "releaseAarSha256": require_sha256(
            release_aar_sha256, "Android validation release AAR"),
        "bundledRuntimeSha256": require_sha256(
            bundled_runtime_sha256, "Android validation bundled Runtime"),
        "testClassName": ANDROID_RUNTIME_TEST_CLASS,
        "executedTests": list(ANDROID_RUNTIME_TESTS),
        "result": "passed",
    })


def validate_android_metadata_content(value):
    """Validate the single-target metadata join without admitting its input."""
    value = require_exact_keys(value, {
        "schemaVersion", "kind", "component", "sdkVersion",
        "packageOutputsDigest", "releaseAarSha256", "bundledRuntimeSha256",
        "validation",
    }, "Android metadata content")
    if (require_integer(value["schemaVersion"], "Android metadata schema") != 1
            or value["kind"] != "sdk-android-metadata-content"
            or value["component"] != "sdk-android"):
        raise ValueError("Android metadata content identity is invalid")
    version = require_semver(value["sdkVersion"], "Android metadata SDK version")
    package = require_sha256(value["packageOutputsDigest"], "Android metadata package outputs")
    aar = require_sha256(value["releaseAarSha256"], "Android metadata release AAR")
    runtime = require_sha256(value["bundledRuntimeSha256"], "Android metadata bundled Runtime")
    validation = validate_android_validation_content(value["validation"])
    if (validation["sdkVersion"] != version
            or validation["packageOutputsDigest"] != package
            or validation["releaseAarSha256"] != aar
            or validation["bundledRuntimeSha256"] != runtime):
        raise ValueError("Android metadata validation differs from its selected package/AAR identity")
    return load_json_bytes(canonical_json_bytes(value))


def android_metadata_content(
    *, sdk_version, package_outputs_digest, expected_release_aar_sha256,
    expected_bundled_runtime_sha256, validation_content,
):
    """Join independently expected package/AAR values to verified content."""
    return validate_android_metadata_content({
        "schemaVersion": 1,
        "kind": "sdk-android-metadata-content",
        "component": "sdk-android",
        "sdkVersion": require_semver(sdk_version, "Android metadata SDK version"),
        "packageOutputsDigest": require_sha256(
            package_outputs_digest, "Android metadata package outputs"),
        "releaseAarSha256": require_sha256(
            expected_release_aar_sha256, "Android metadata expected release AAR"),
        "bundledRuntimeSha256": require_sha256(
            expected_bundled_runtime_sha256, "Android metadata expected bundled Runtime"),
        "validation": validation_content,
    })
