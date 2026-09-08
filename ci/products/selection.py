from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from pathlib import Path
import re
import subprocess
from typing import Iterable

from .inventory import file_inventory, git_file_inventory, tree_entries
from .registry import (
    COMPONENTS_BY_IDENTITY,
    NATIVE_BINDINGS,
    NATIVE_TARGETS,
    PHASE_ORDER,
    PHASE_INSTANCE_IDS,
    RUNTIME_COMPONENTS,
    SDK_COMPATIBILITY_COMPONENTS,
    PhaseId,
    PhaseInstanceId,
    phase_targets,
)


@dataclass(frozen=True, slots=True)
class PathSelection:
    """Product work selected by changed paths, kept separate from inventory inputs."""

    instances: tuple[PhaseInstanceId, ...]
    inventory_paths: tuple[str, ...]
    ignored_paths: tuple[str, ...]
    unknown_paths: tuple[str, ...]
    reuse_allowed: bool


ALL_INSTANCES = frozenset(PHASE_INSTANCE_IDS)
ALL_METADATA = frozenset(instance for instance in PHASE_INSTANCE_IDS if instance.phase == "metadata")
_GIT_OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
# The imported metadata join reruns these semantic gates without consumer/compiler
# producers. Existing planner/transport control-only exemptions remain unchanged.
_NATIVE_METADATA_VERIFIERS = frozenset({
    *(f"ci/products/{name}.py" for name in (
        "sdk_package", "sdk_inputs", "sdk_native", "sdk_compatibility", "sdk_runtime_content",
        "contract", "contract_model", "c_abi", "runtime_attestation", "runtime_aggregate",
        "runtime_variant", "runtime_identity", "runtime_evidence", "runtime_adapter_validation", "test_results",
    )),
    *(f"gradle/build-logic/src/main/kotlin/{name}.kt" for name in (
        "CrossLanguageNativeWrapperValidationEvidence", "CrossLanguageNativeWrapperBindingEvidence",
        "NativeWrapperInstalledConsumerTask", "CrossLanguageApiEvidence", "CrossLanguageCAbiBindingEvidence",
        "CrossLanguageBindingParity", "CrossLanguageCAbiClient",
        "ProductPythonTooling",
    )),
    "ci/native_wrappers.py",
    "gradle/build-logic/build.gradle.kts",
})
_DOC_FILES = frozenset({"README.md", "CONTRIBUTING.md", "SECURITY.md", "SUPPORT.md"})
_STATIC_ONLY_FILES = frozenset({".github/actionlint.yaml", ".github/dependabot.yml"})
_BINDING_VALIDATION_DIRECTORIES = frozenset({
    "consumer", "consumers", "example", "parity", "samples", "test", "tests", "tool",
})
_STATIC_TEST_PREFIXES = (
    "gradle/build-logic/src/test/",
    "runtime/build-logic/src/test/",
)
_CONTRACT_BUILD_INPUTS = frozenset({
    "codex-agent-core/build.gradle.kts",
    "codex-agent-core/gradle.lockfile",
})
_CONTRACT_INVENTORY_POLICIES = frozenset({
    "ci/lanes/contract-product.production.pathspec",
    "ci/lanes/contract-product.test.pathspec",
})
_CONTRACT_EVIDENCE_BUILD_LOGIC = frozenset({
    "CanonicalTestResultsClient.kt",
    "CrossLanguageApiCoverage.kt",
    "CrossLanguageApiDiscovery.kt",
    "CrossLanguageApiDiscoveryCli.kt",
    "CrossLanguageApiEvidence.kt",
    "CrossLanguageApiReportCodec.kt",
    "CrossLanguageApiTasks.kt",
    "CrossLanguageBindingParity.kt",
    "CrossLanguageBindingReceipt.kt",
    "CrossLanguageBindingTasks.kt",
    "CrossLanguageKotlinBindingEvidence.kt",
})
_RUNTIME_BUILD_INPUTS = frozenset({
    "codex-agent-runtime-desktop/build.gradle.kts",
    "codex-agent-runtime-desktop/gradle.lockfile",
    "runtime/build-logic/build.gradle.kts",
    "runtime/build-logic/gradle.lockfile",
    "runtime/build-logic/gradle/verification-metadata.xml",
    "runtime/build-logic/settings-gradle.lockfile",
    "runtime/build-logic/settings.gradle.kts",
    "runtime/build.gradle.kts",
    "runtime/gradle.properties",
    "runtime/gradle/verification-metadata.xml",
    "runtime/settings-gradle.lockfile",
    "runtime/settings.gradle.kts",
})
_METADATA_AUTHORITIES = frozenset({
    "ci/evidence.py",
    "ci/promote.py",
    "ci/receipt.py",
    "ci/reuse.py",
    "ci/stage.py",
    "ci/validation_reuse.py",
    "ci/products/__main__.py",
    "ci/products/aggregate.py",
    "ci/products/index.py",
    "ci/products/inventory.py",
    "ci/products/receipt.py",
    "ci/products/signatures.py",
    "gradle/build-logic/src/main/kotlin/CandidateCiProvenance.kt",
    "gradle/build-logic/src/main/kotlin/CandidateManifestValidation.kt",
    "gradle/build-logic/src/main/kotlin/CandidatePayloadTasks.kt",
    "gradle/build-logic/src/main/kotlin/CandidateRuntimeEvidence.kt",
    "gradle/build-logic/src/main/kotlin/CentralBundleTasks.kt",
    "gradle/build-logic/src/main/kotlin/CentralPortalHttp.kt",
    "gradle/build-logic/src/main/kotlin/CentralPortalRecord.kt",
    "gradle/build-logic/src/main/kotlin/CentralPortalTask.kt",
    "gradle/build-logic/src/main/kotlin/CentralPortalVerification.kt",
    "gradle/build-logic/src/main/kotlin/CodexReleaseDownload.kt",
    "gradle/build-logic/src/main/kotlin/MavenRepositoryTasks.kt",
    "gradle/build-logic/src/main/kotlin/PromotedCandidateTasks.kt",
    "gradle/build-logic/src/main/kotlin/ReleaseGradleProcess.kt",
    "gradle/build-logic/src/main/kotlin/ReleaseIo.kt",
    "gradle/build-logic/src/main/kotlin/ReleaseToolingCli.kt",
    "gradle/build-logic/src/main/kotlin/ReleaseToolingGradleTasks.kt",
    "gradle/build-logic/src/main/kotlin/RepositoryVerificationTasks.kt",
    "gradle/build-logic/src/main/kotlin/codexagent.root-release.gradle.kts",
    "gradle/release/product-signing-keys.json",
    "gradle/release/publication-approvals.json",
})
_RUNTIME_BUILD_LOGIC_JVM = frozenset({
    "JvmRuntimeEvidenceExecution.kt",
    "JvmRuntimeEvidenceModel.kt",
    "JvmRuntimeEvidenceRegistration.kt",
    "JvmRuntimeEvidenceTasks.kt",
})
_RUNTIME_BUILD_LOGIC_NODE = frozenset({
    "NodeRuntimeEvidenceExecution.kt",
    "NodeRuntimeEvidenceModel.kt",
    "NodeRuntimeEvidenceTasks.kt",
})
_RUNTIME_BUILD_LOGIC_NATIVE_VALIDATION = frozenset({
    "CrossLanguageCAbiBootstrapEvidence.kt",
    "DesktopClassifierInspection.kt",
    "DesktopRuntimeEvidenceGradleTasks.kt",
    "DesktopRuntimeEvidenceTasks.kt",
    "RuntimeBundleEvidence.kt",
})
_RUNTIME_BUILD_LOGIC_NATIVE_PACKAGE = frozenset({
    "CrossLanguageCAbiRuntimeProduction.kt",
    "DesktopRuntimePackageTask.kt",
    "DesktopRuntimeZipModes.kt",
    "RuntimeCAbiClient.kt",
})
_RUNTIME_BUILD_LOGIC_NATIVE_BINARY = frozenset({
    "CompileDesktopProcessSupervisorTask.kt",
    "GenerateRuntimeAbiSourceTask.kt",
    "PrepareRuntimePinnedArchiveTask.kt",
    "RuntimeBinaryFlags.kt",
    "RuntimeDownload.kt",
})
_RUNTIME_BUILD_LOGIC_SHARED_VALIDATION = frozenset({
    "RuntimeCanonicalApiProjection.kt",
    "RuntimeCanonicalTestResultsClient.kt",
    "RuntimeEvidenceClient.kt",
    "RuntimeReleaseIo.kt",
})
_ANDROID_VALIDATION_BUILD_LOGIC = frozenset({
    "AndroidRuntimeEvidenceFiles.kt",
    "AndroidRuntimeEvidenceIo.kt",
    "AndroidRuntimeEvidenceSupport.kt",
    "FirebaseAndroidRuntimeEvidenceIo.kt",
    "FirebaseAndroidRuntimeEvidenceModel.kt",
    "FirebaseAndroidRuntimeEvidenceTasks.kt",
    "ImportedAndroidReleaseAar.kt",
    "codexagent.android-runtime-evidence.gradle.kts",
})
_IOS_VALIDATION_BUILD_LOGIC = frozenset({
    "AppleCompilerEvidenceTask.kt",
    "AppleReleaseCheckTasks.kt",
    "AppleVerifiedDistributionModel.kt",
    "AppleVerifiedDistributionTasks.kt",
    "CandidateIosNativeEvidence.kt",
    "CrossLanguageAppleBindingEvidence.kt",
    "ImportedAppleFrameworkTasks.kt",
    "IosImportedContractEvidenceTasks.kt",
    "IosAppleReleaseVerificationTasks.kt",
    "IosPrivacyAuditTasks.kt",
    "IosPrivacyAuditVerification.kt",
    "IosPrivacyEvidence.kt",
    "IosPrivacyReviewBinding.kt",
    "IosPrivacyScanner.kt",
    "NativeReleaseVerificationTasks.kt",
    "PrivacyReleaseVerificationTasks.kt",
    "SwiftAuthenticationTestTask.kt",
    "SwiftPackageProofTask.kt",
})
_IOS_PACKAGE_BUILD_LOGIC = frozenset({
    "AppleDistributionFileTasks.kt",
    "IosAppleDistributionTasks.kt",
    "IosPrivacyArchive.kt",
    "IosPrivacyManifest.kt",
    "IosPrivacyPolicy.kt",
    "IosVerifiedDistributionRegistration.kt",
    "SwiftReleaseMetadataTasks.kt",
})
_IOS_BINARY_BUILD_LOGIC = frozenset({
    "AppleRustSliceModel.kt",
    "AppleRustSliceRegistration.kt",
    "AppleRustSliceTasks.kt",
    "IosNativeTaskModel.kt",
    "IosNativeTaskRegistration.kt",
    "IosRustToolchain.kt",
    "PinnedCargoTask.kt",
    "PrepareCodexIosSourceTask.kt",
    "PreparePinnedArchiveTask.kt",
    "codexagent.ios-runtime.gradle.kts",
})
_CONTROL_ONLY_FILES = frozenset({
    "ci/cache_seed.py",
    "ci/contract_release.py",
    "ci/impact.py",
    "ci/lane_selection.py",
    "ci/run-lane.sh",
    "ci/runner_identity.py",
    "ci/legacy_lanes.py",
    "ci/product_legacy.py",
    "ci/product_reuse.py",
    "ci/runtime_native_phase.py",
    "ci/runtime_supervisor.py",
    "ci/runtime_workflow.py",
    "ci/runtime_adapter_phase.py",
    "ci/products/contract_attestation.py",
    "ci/products/contract_projection.py",
    "ci/products/plan.py",
    "ci/products/registry.py",
    "ci/products/restore.py",
    "ci/products/reuse.py",
    "ci/products/native_runtime_inputs.py",
    "ci/products/runtime_adapter_content.py",
    "ci/products/adapter_runtime_inputs.py",
    "ci/products/tooling.py",
    "ci/products/tooling_local.py",
    "ci/products/sdk_validation.py",
    "ci/products/sdk_validation_inputs.py",
    "ci/products/selection.py",
    "ci/products/sdk_inputs.py",
    "ci/products/sdk_native.py",
    "ci/products/sdk_package.py",
})
_CONTROL_ONLY_PREFIXES = (
    ".github/actions/",
    ".github/workflows/",
    "ci/lanes/",
)
_MIGRATED_PRODUCT_PREFIXES = (
    "codex-agent-client/",
    "codex-agent-runtime-node/",
    "runtime-host-shared/",
)
_MIGRATED_BUILD_LOGIC_FILES = frozenset({
    "gradle/build-logic/src/main/kotlin/GenerateNodeDistributionSourceTask.kt",
    "gradle/build-logic/src/main/kotlin/codexagent.client-verification.gradle.kts",
    "gradle/build-logic/src/main/kotlin/codexagent.node-runtime.gradle.kts",
})
_RUNTIME_BINARY_FLAGS_PATH = "codex-agent-runtime-desktop/native/c-api/binary-flags.json"
_RUNTIME_TOOLCHAIN_PROFILE_PREFIX = "gradle/release/toolchains/runtime/"
_RUNTIME_TOOLCHAIN_PROFILE_PATHS = frozenset(
    f"{_RUNTIME_TOOLCHAIN_PROFILE_PREFIX}{target}.json" for target in NATIVE_TARGETS
)


def _from_phase(
    product: str,
    component: str,
    start: str,
    *,
    validation_targets: Iterable[str] | None = None,
) -> set[PhaseInstanceId]:
    spec = COMPONENTS_BY_IDENTITY[(product, component)]
    phases = spec.phases[spec.phases.index(start):]
    selected_targets = None if validation_targets is None else frozenset(validation_targets)
    selected: set[PhaseInstanceId] = set()
    for phase in phases:
        targets = phase_targets(PhaseId(product, component, phase))
        if phase == "validation" and selected_targets is not None:
            targets = tuple(target for target in targets if target in selected_targets)
        selected.update(PhaseInstanceId(product, component, phase, target) for target in targets)
    return selected


def _runtime(
    components: Iterable[str],
    start: str = "binary",
    *,
    validation_targets: Iterable[str] | None = None,
) -> set[PhaseInstanceId]:
    selected: set[PhaseInstanceId] = set()
    for component in components:
        selected.update(
            _from_phase(
                "runtime",
                component,
                start,
                validation_targets=validation_targets,
            )
        )
    selected.add(PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"))
    return selected


def _bindings(languages: Iterable[str]) -> set[PhaseInstanceId]:
    selected: set[PhaseInstanceId] = set()
    for language in languages:
        selected.update(_from_phase("sdk", language, "package"))
    return selected


def _contract() -> set[PhaseInstanceId]:
    return _from_phase("contract", "contract", "binary")


def _facade_validation(*targets: str) -> set[PhaseInstanceId]:
    return _from_phase("sdk", "sdk-core", "validation", validation_targets=targets)


def _is_prefix(path: str, prefix: str) -> bool:
    return path == prefix.removesuffix("/") or path.startswith(prefix)


def _normalized_paths(paths: Iterable[str]) -> tuple[str, ...]:
    if isinstance(paths, (str, bytes)):
        raise ValueError("Changed paths must be an iterable of POSIX relative paths")
    normalized = []
    for path in paths:
        if type(path) is not str or not path or path != path.strip() or any(
            ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in path
        ):
            raise ValueError("Changed path must be a canonical nonempty string")
        candidate = PurePosixPath(path)
        if (
            "\\" in path
            or candidate.is_absolute()
            or ".." in candidate.parts
            or "." in candidate.parts
            or candidate.as_posix() != path
        ):
            raise ValueError(f"Changed path is not a normalized POSIX relative path: {path}")
        normalized.append(path)
    if len(normalized) != len(set(normalized)):
        raise ValueError("Changed paths must be unique")
    return tuple(sorted(normalized))


def _binding_language(path: str) -> str | None:
    for language in (*NATIVE_BINDINGS, "javascript"):
        if _is_prefix(path, f"codex-agent-bindings/{language}/"):
            return language
        if language != "javascript" and _is_prefix(
            path,
            f"codex-agent-runtime-desktop/bindings/{language}/",
        ):
            return language
    if _is_prefix(path, "codex-agent-runtime-desktop/npm/"):
        return "javascript"
    return None


def _binding_validation_path(path: str, language: str) -> bool:
    roots = [f"codex-agent-bindings/{language}/"]
    if language == "javascript":
        roots.append("codex-agent-runtime-desktop/npm/")
    else:
        roots.append(f"codex-agent-runtime-desktop/bindings/{language}/")
    for root in roots:
        if path.startswith(root):
            return path[len(root):].split("/", 1)[0] in _BINDING_VALIDATION_DIRECTORIES
    return False


def _runtime_build_logic_selection(path: str) -> set[PhaseInstanceId] | None:
    if not (
        _is_prefix(path, "runtime/build-logic/src/main/")
        or _is_prefix(path, "gradle/build-logic/src/main/kotlin/")
    ):
        return None
    name = path.rsplit("/", 1)[-1]
    if path == "runtime/build-logic/src/main/kotlin/RuntimeReleaseIo.kt":
        return _runtime(RUNTIME_COMPONENTS)
    if name == "RuntimeEvidenceExecutionCapture.kt":
        return _runtime(("jvm", "node-js", "node-wasm"), "validation",
                        validation_targets=NATIVE_TARGETS) | _runtime(NATIVE_TARGETS, "validation")
    if name in _RUNTIME_BUILD_LOGIC_JVM:
        return _runtime(("jvm",), "validation")
    if name in _RUNTIME_BUILD_LOGIC_NODE:
        return _runtime(("node-js", "node-wasm"), "validation")
    if name == "NodeBindingValidationTask.kt":
        return _runtime(("node-js",))
    if name == "NodeBindingValidationExecution.kt":
        return _runtime(("node-js",), "validation", validation_targets=("node-js-binding",))
    if name == "LinuxArm64RuntimeEvidenceBundle.kt":
        return _runtime(NATIVE_TARGETS, "validation")
    if name == "ImportedCAbiBootstrapTasks.kt":
        return _runtime(("macos-arm64",), "validation")
    if name == "RuntimeAdapterMetadataInputsTask.kt":
        return _runtime(("jvm", "node-js", "node-wasm"), "metadata") | _runtime(("macos-arm64",), "validation")
    if name == "RuntimeAdapterMavenHandoff.kt":
        return _runtime(("jvm", "node-js", "node-wasm"))
    if name == "ImportedRuntimeVariantTask.kt":
        return _runtime(NATIVE_TARGETS, "metadata")
    if name in _RUNTIME_BUILD_LOGIC_NATIVE_VALIDATION:
        return _runtime(NATIVE_TARGETS, "validation")
    if name == "DesktopRuntimeZipModes.kt":
        return _runtime(NATIVE_TARGETS, "package") | _runtime(
            ("node-js",), "validation", validation_targets=("node-js-binding",),
        )
    if name in _RUNTIME_BUILD_LOGIC_NATIVE_PACKAGE:
        return _runtime(NATIVE_TARGETS, "package")
    if name in {"GenerateDesktopDistributionSourceTask.kt", "DesktopRuntimeModel.kt"}:
        return _runtime(RUNTIME_COMPONENTS)
    if name in _RUNTIME_BUILD_LOGIC_NATIVE_BINARY:
        return _runtime(NATIVE_TARGETS)
    if name in _RUNTIME_BUILD_LOGIC_SHARED_VALIDATION:
        return _runtime(RUNTIME_COMPONENTS, "validation")
    if name.startswith("Runtime") or name == "codexagent.desktop-runtime.gradle.kts":
        return _runtime(RUNTIME_COMPONENTS)
    return None


def _sdk_validation() -> set[PhaseInstanceId]:
    selected = _from_phase("sdk", "sdk-core", "validation")
    selected.update(_from_phase("sdk", "sdk-android", "validation"))
    selected.update(_from_phase("sdk", "sdk-ios", "validation"))
    for language in (*NATIVE_BINDINGS, "javascript"):
        selected.update(_from_phase("sdk", language, "validation"))
    return selected


def _native_metadata_owners(path: str) -> set[PhaseInstanceId]:
    languages = NATIVE_BINDINGS if path in _NATIVE_METADATA_VERIFIERS else (
        ("cpp",) if path == "codex-agent-bindings/cpp/tools/verify_imported_package.py" else ()
    )
    return {PhaseInstanceId("sdk", language, "metadata", "desktop") for language in languages}


def _control_selection(path: str) -> set[PhaseInstanceId] | None:
    if path in _CONTROL_ONLY_FILES:
        return set(ALL_INSTANCES)
    if _is_prefix(path, ".github/actions/run-ci-lane/") or path == ".github/workflows/ci.yml":
        return set(ALL_INSTANCES)
    if _is_prefix(path, ".github/actions/setup-kmp/"):
        return set(ALL_INSTANCES)
    if _is_prefix(path, ".github/actions/setup-msvc/"):
        return _runtime(("windows-x64",)) | _bindings(NATIVE_BINDINGS)
    if _is_prefix(path, ".github/actions/setup-sccache/"):
        return _from_phase("sdk", "sdk-ios", "binary")
    workflows = {
        ".github/workflows/android-runtime-evidence.yml": _from_phase(
            "sdk", "sdk-android", "validation"
        ),
        ".github/workflows/apple-runtime-evidence.yml": _from_phase(
            "sdk", "sdk-ios", "validation"
        ),
        ".github/workflows/desktop-runtime-evidence.yml": _runtime(RUNTIME_COMPONENTS),
        ".github/workflows/runtime-toolchain-capture.yml": _runtime(NATIVE_TARGETS),
        ".github/workflows/product-validation.yml": set(ALL_INSTANCES),
        ".github/workflows/promote.yml": set(ALL_METADATA),
        ".github/workflows/publish.yml": set(ALL_METADATA),
        ".github/workflows/release-candidate.yml": set(ALL_METADATA),
    }
    if path in workflows:
        return workflows[path]
    if not _is_prefix(path, "ci/lanes/"):
        return None
    name = path.removeprefix("ci/lanes/")
    parts = name.rsplit(".", 2)
    if len(parts) != 3:
        return None
    lane, kind, suffix = parts
    if suffix != "pathspec" or kind not in {"production", "test", "metadata"}:
        return None
    start = {"production": "binary", "test": "validation", "metadata": "metadata"}[kind]
    if lane.startswith("desktop-"):
        return _runtime((lane.removeprefix("desktop-"),), start)
    if lane in {"node-js", "node-wasm"}:
        return _runtime((lane,), start)
    if lane == "android":
        return _from_phase("sdk", "sdk-android", start)
    if lane.startswith("ios-"):
        return _from_phase("sdk", "sdk-ios", "validation" if kind == "test" else start)
    if lane.startswith("consumer-"):
        target = {
            "consumer-android": "android",
            "consumer-desktop": "jvm",
            "consumer-ios-device": "ios-arm64",
            "consumer-ios-simulator": "ios-simulator-arm64",
            "consumer-node-js": "node-js",
            "consumer-node-wasm": "node-wasm",
        }.get(lane)
        return _facade_validation(target) if target else _from_phase("sdk", "sdk-core", "validation")
    if lane.startswith("contract"):
        return _from_phase("contract", "contract", start)
    return set(ALL_INSTANCES)


def _is_control_only(path: str) -> bool:
    if path == "ci/products/sdk_runtime_content.py":
        return False  # Produces the native Mac bootstrap content sidecar.
    if path in {"ci/products/sdk_inputs.py", "ci/products/sdk_native.py", "ci/products/sdk_package.py"}:
        return False  # Also produces the authenticated native validation handoff.
    if path in _CONTRACT_INVENTORY_POLICIES:
        return False  # These exact policies are embedded in the Contract binary payload.
    return path in _CONTROL_ONLY_FILES or any(
        _is_prefix(path, prefix) for prefix in _CONTROL_ONLY_PREFIXES
    )


def _classify(path: str) -> set[PhaseInstanceId] | None:
    if path in _CONTRACT_INVENTORY_POLICIES:
        return _contract()
    if path in _MIGRATED_BUILD_LOGIC_FILES or any(
        _is_prefix(path, prefix) for prefix in _MIGRATED_PRODUCT_PREFIXES
    ):
        return set(ALL_INSTANCES)
    control = _control_selection(path)
    if control is not None:
        return control

    language = _binding_language(path)
    if language is not None:
        if path in {
            "codex-agent-bindings/python/tools/produce_sdk_validation_evidence.py",
            "codex-agent-bindings/csharp/tools/produce_sdk_validation_evidence.py",
            "codex-agent-bindings/rust/tools/produce_sdk_validation_evidence.py",
            "codex-agent-bindings/cpp/tools/produce_sdk_validation_evidence.py",
            "codex-agent-bindings/cpp/tools/verify_imported_package.py",
            "codex-agent-bindings/dart/tool/produce_sdk_validation_evidence.py",
        }:
            return _from_phase("sdk", language, "validation")
        if language == "javascript" and _binding_validation_path(path, language):
            return _from_phase("sdk", language, "validation")
        return _bindings((language,))

    if (
        _is_prefix(path, "codex-agent-runtime-desktop/native/c-api/include/")
        or _is_prefix(path, "codex-agent-runtime-desktop/native/c-api/exports/")
        or path == "codex-agent-runtime-desktop/native/c-api/abi-contract.json"
        or path == "codex-agent-runtime-desktop/src/nativeInterop/cinterop/codex_agent_c.def"
    ):
        return _runtime(NATIVE_TARGETS) | _bindings(NATIVE_BINDINGS)

    if path == "codex-agent-runtime-desktop/src/nativeInterop/cinterop/codex_desktop.def":
        return _runtime(NATIVE_TARGETS)

    if path == "codex-agent-runtime-desktop/native/include/codex_desktop_windows.h":
        return _runtime(("windows-x64",))
    if path == "codex-agent-runtime-desktop/native/include/codex_desktop_posix.h":
        return _runtime(tuple(target for target in NATIVE_TARGETS if target != "windows-x64"))
    if path == "codex-agent-runtime-desktop/native/include/codex_desktop.h":
        return _runtime(NATIVE_TARGETS)

    if _is_prefix(path, "codex-agent-runtime-desktop/native/c-api/consumer/"):
        return _runtime(NATIVE_TARGETS, "validation")

    if path == "codex-agent-runtime-desktop/codex-app-server-distributions.json":
        return _runtime(RUNTIME_COMPONENTS)

    if path in _METADATA_AUTHORITIES:
        if path in {
            "ci/products/aggregate.py", "ci/products/inventory.py",
            "gradle/build-logic/src/main/kotlin/ReleaseToolingCli.kt",
            "gradle/build-logic/src/main/kotlin/ReleaseIo.kt",
        }:
            consumers = set().union(*(
                _from_phase("sdk", language, "package" if path == "ci/products/inventory.py" else "validation")
                for language in NATIVE_BINDINGS
            ))
            contract = _contract() if path.endswith(("inventory.py", "ReleaseIo.kt")) else set()
            bootstrap = _runtime(("macos-arm64",), "validation") if path == "ci/products/inventory.py" else set()
            return set(ALL_METADATA) | consumers | contract | bootstrap
        if path in {
            "ci/products/__main__.py", "ci/products/receipt.py",
            "gradle/build-logic/src/main/kotlin/codexagent.root-release.gradle.kts",
        }:
            return set(ALL_METADATA) | _contract()
        if path == "gradle/build-logic/src/main/kotlin/MavenRepositoryTasks.kt":
            return set(ALL_METADATA).union(*(
                _from_phase("sdk", component, "binary")
                for component in ("sdk-core", "sdk-android", "sdk-ios")
            ))
        return set(ALL_METADATA)

    if path == "ci/products/contract_model.py":
        return _contract() | _runtime(("macos-arm64",), "validation").union(*(
            _from_phase("sdk", language, "package") for language in NATIVE_BINDINGS
        ))
    if path == "ci/products/contract.py":
        return _contract()
    if path == "ci/products/c_abi.py":
        return _runtime(NATIVE_TARGETS) | _bindings(NATIVE_BINDINGS)
    if path in {
        "ci/products/runtime_flags.py",
        "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
    }:
        return _runtime(NATIVE_TARGETS)
    if path == "ci/products/runtime_identity.py":
        return _runtime(NATIVE_TARGETS)
    if path == "ci/products/runtime_variant.py":
        return _runtime(NATIVE_TARGETS, "metadata") | _bindings(NATIVE_BINDINGS)
    if path == "ci/products/sdk_runtime_content.py":
        return _runtime(("macos-arm64",), "validation").union(*(
            _from_phase("sdk", language, "package") for language in NATIVE_BINDINGS
        ))
    if path == "ci/products/runtime_attestation.py":
        return _runtime(NATIVE_TARGETS, "metadata") | _bindings(
            ("sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript")
        )
    if path == "ci/products/runtime_aggregate.py":
        return _from_phase("runtime", "runtime-aggregate", "metadata")
    if path == "ci/products/runtime_adapter_validation.py":
        return _runtime(("jvm", "node-js", "node-wasm"), "validation",
                        validation_targets=NATIVE_TARGETS) | _classify("ci/products/sdk_runtime_content.py")
    if path == "ci/products/sdk_compatibility.py":
        selected = set()
        for component in ("sdk-core", "sdk-android", "sdk-ios", *NATIVE_BINDINGS, "javascript"):
            selected.update(_from_phase("sdk", component, "package"))
        return selected
    if path == "ci/products/sdk_maven.py":
        return set().union(*(
            _from_phase("sdk", component, "binary")
            for component in ("sdk-core", "sdk-android", "sdk-ios")
        ))
    if path == "ci/products/sdk_archive.py":
        return set().union(*(
            _from_phase("sdk", component, "package")
            for component in ("sdk-core", "sdk-android", "sdk-ios", "javascript")
        ))
    if path in {
        "ci/products/__init__.py",
        "ci/products/runtime_evidence.py",
        "ci/products/test_results.py",
    }:
        selected = _runtime(RUNTIME_COMPONENTS, "validation")
        if path != "ci/products/runtime_evidence.py":
            selected |= _contract()
        if path in {"ci/products/test_results.py", "ci/products/runtime_evidence.py"}:
            selected.update(set().union(*(
                _from_phase("sdk", language, "package") for language in NATIVE_BINDINGS
            )))
        return selected
    if path == "ci/native_wrappers.py":
        return _bindings(NATIVE_BINDINGS)

    if path == "ci/products/toolchain.py":
        # Production profiles are not tracked per target yet (S605). This one
        # shared authority therefore owns all five native binary lines.
        return _runtime(NATIVE_TARGETS)
    if path in _RUNTIME_TOOLCHAIN_PROFILE_PATHS:
        target = path.removeprefix(_RUNTIME_TOOLCHAIN_PROFILE_PREFIX).removesuffix(".json")
        return _runtime((target,))

    runtime_build_logic = _runtime_build_logic_selection(path)
    if runtime_build_logic is not None:
        return runtime_build_logic

    runtime_tests = {
        "jvmTest": ("jvm",),
        "jsTest": ("node-js",),
        "wasmJsTest": ("node-wasm",),
        "webTest": ("node-js", "node-wasm"),
        "nativeTest": NATIVE_TARGETS,
        "commonTest": RUNTIME_COMPONENTS,
        "desktopTest": (*NATIVE_TARGETS, "jvm"),
    }
    for source_set, components in runtime_tests.items():
        if _is_prefix(path, f"codex-agent-runtime-desktop/src/{source_set}/"):
            # JVM/native and Node JS stages contain compiled test runners.
            # Node Wasm still stages only its main-program validation runner.
            selected = _runtime(components, "validation")
            compiled_runners = tuple(component for component in components
                                     if component in (*NATIVE_TARGETS, "jvm", "node-js"))
            return selected | (_runtime(compiled_runners) if compiled_runners else set())

    runtime_sources = {
        "mingwMain": ("windows-x64",),
        "linuxMain": ("linux-arm64", "linux-x64"),
        "macosMain": ("macos-arm64", "macos-x64"),
        "nativeMain": NATIVE_TARGETS,
        "jvmMain": ("jvm",),
        "jsMain": ("node-js",),
        "wasmJsMain": ("node-wasm",),
        "webMain": ("node-js", "node-wasm"),
        "commonMain": RUNTIME_COMPONENTS,
        "desktopMain": RUNTIME_COMPONENTS,
    }
    for source_set, components in runtime_sources.items():
        if _is_prefix(path, f"codex-agent-runtime-desktop/src/{source_set}/"):
            return _runtime(components)
    if _is_prefix(path, "codex-agent-runtime-desktop/native/"):
        return _runtime(NATIVE_TARGETS)
    if path == "runtime/gradle/kotlin-js-store/package-lock.json":
        return _runtime(("node-js",))
    if path == "runtime/gradle/kotlin-js-store/wasm/package-lock.json":
        return _runtime(("node-wasm",))
    if path == "gradle/kotlin-js-store/package-lock.json":
        return _runtime(("node-js",))
    if path == "gradle/kotlin-js-store/wasm/package-lock.json":
        return _runtime(("node-wasm",))
    if path in _RUNTIME_BUILD_INPUTS:
        return _runtime(RUNTIME_COMPONENTS)

    if path in _CONTRACT_BUILD_INPUTS:
        return set(ALL_INSTANCES)
    if _is_prefix(path, "codex-agent-core/src/commonMain/") or _is_prefix(
        path,
        "codex-agent-core/protocol/",
    ):
        return set(ALL_INSTANCES)
    if _is_prefix(path, "codex-agent-core/src/commonTest/") or _is_prefix(
        path,
        "codex-agent-core/src/jvmTest/",
    ):
        # Compiled tests and their raw/semantic evidence are produced in binary.
        return _contract()
    if _is_prefix(path, "codex-agent-core/src/jvmMain/"):
        return _contract() | _runtime(("jvm",)) | _facade_validation("jvm")
    if _is_prefix(path, "codex-agent-core/src/jsMain/"):
        return (
            _contract()
            | _runtime(("node-js",))
            | _facade_validation("node-js")
            | _bindings(("javascript",))
        )
    if _is_prefix(path, "codex-agent-core/src/wasmJsMain/"):
        return _contract() | _runtime(("node-wasm",)) | _facade_validation("node-wasm")
    if _is_prefix(path, "codex-agent-core/src/androidMain/"):
        return _contract() | _from_phase("sdk", "sdk-android", "binary") | _facade_validation("android")
    if _is_prefix(path, "codex-agent-core/src/jvmAndAndroidMain/"):
        return (
            _contract()
            | _runtime(("jvm",))
            | _from_phase("sdk", "sdk-android", "binary")
            | _facade_validation("android", "jvm")
        )
    if _is_prefix(path, "codex-agent-core/src/nativeMain/"):
        return (
            _contract()
            | _runtime(NATIVE_TARGETS)
            | _facade_validation(
                "ios-arm64",
                "ios-simulator-arm64",
                "linux-arm64",
                "linux-x64",
                "macos-arm64",
                "macos-x64",
                "windows-x64",
            )
        )

    if _is_prefix(path, "codex-agent-sdk/"):
        return _from_phase("sdk", "sdk-core", "binary")
    if _is_prefix(path, "codex-agent-runtime-android/src/test/"):
        return _from_phase("sdk", "sdk-android", "validation")
    if _is_prefix(path, "codex-agent-runtime-android/"):
        return _from_phase("sdk", "sdk-android", "binary")
    if (
        _is_prefix(path, "codex-agent-runtime-ios/src/iosTest/")
        or _is_prefix(path, "codex-agent-runtime-ios/apple/CompilerEvidence/")
        or _is_prefix(path, "codex-agent-runtime-ios/apple/RemoteConsumer/")
        or _is_prefix(path, "codex-agent-runtime-ios/apple/TestApp/")
        or _is_prefix(path, "codex-agent-runtime-ios/apple/Tests/")
        or _is_prefix(path, "codex-agent-runtime-ios/native/bridge/src/tests/")
    ):
        return _from_phase("sdk", "sdk-ios", "validation")
    if _is_prefix(path, "codex-agent-runtime-ios/"):
        return _from_phase("sdk", "sdk-ios", "binary")

    if path == "gradle/release/sdk-default-runtime.txt":
        return set().union(
            _from_phase("sdk", "sdk-core", "package"),
            _from_phase("sdk", "sdk-android", "package"),
            _from_phase("sdk", "sdk-ios", "package"),
            _bindings((*NATIVE_BINDINGS, "javascript")),
        )
    if path == "gradle/release/versions/runtime.txt":
        return {PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")}
    if path == "gradle/release/versions/sdk.txt":
        return set().union(
            _from_phase("sdk", "sdk-core", "binary"),
            _from_phase("sdk", "sdk-android", "binary"),
            _from_phase("sdk", "sdk-ios", "binary"),
            _bindings((*NATIVE_BINDINGS, "javascript")),
        )
    if path == "gradle/release/versions/contract.txt":
        return set(ALL_INSTANCES)

    if path == "gradle.properties":
        return set().union(
            _from_phase("contract", "contract", "binary"),
            *(
                _from_phase("sdk", component, "binary")
                for component in ("sdk-core", "sdk-android", "sdk-ios")
            ),
            _bindings((*NATIVE_BINDINGS, "javascript")),
        )

    if _is_prefix(path, "tooling/android-runtime-evidence/"):
        return _from_phase("sdk", "sdk-android", "validation")
    if _is_prefix(path, "tooling/protocol-generator/src/test/"):
        return _from_phase("contract", "contract", "validation")
    if _is_prefix(path, "tooling/protocol-generator/"):
        return _contract()

    if _is_prefix(path, "gradle/release/contract-isolation-fixture/"):
        return _from_phase("contract", "contract", "validation")
    if _is_prefix(path, "gradle/release/kmp-consumer-template/"):
        return _sdk_validation()
    if _is_prefix(path, "gradle/release/sdk-facade-consumer-template/"):
        return _from_phase("sdk", "sdk-core", "validation")
    if path in {
        "gradle/release/privacy-data-flow-review.json",
        "gradle/release/privacy-required-reason-review.json",
    }:
        return _from_phase("sdk", "sdk-ios", "validation")
    if path == "gradle/release/ios-resource-policy.json":
        return _from_phase("sdk", "sdk-ios", "package")

    if path == "Package.swift":
        return _from_phase("sdk", "sdk-ios", "package")
    if path in {"build.gradle.kts", "settings-gradle.lockfile", "settings.gradle.kts"}:
        return {
            instance for instance in ALL_INSTANCES if instance.product != "runtime"
        }

    if path == ".gitattributes":
        return set(ALL_INSTANCES)

    if _is_prefix(path, "legal/openai-codex/") or path in {"LICENSE", "THIRD_PARTY_NOTICES.md"}:
        selected = _runtime(RUNTIME_COMPONENTS, "package")
        selected.update(_from_phase("sdk", "sdk-core", "package"))
        selected.update(_from_phase("sdk", "sdk-android", "package"))
        selected.update(_from_phase("sdk", "sdk-ios", "package"))
        selected.update(_bindings((*NATIVE_BINDINGS, "javascript")))
        return selected

    sdk_build_logic = {
        "codexagent.javascript-sdk.gradle.kts": _bindings(("javascript",)),
        "codexagent.native-wrapper-sdk.gradle.kts": _bindings(NATIVE_BINDINGS).union(*(
            _from_phase("sdk", component, "package")
            for component in ("sdk-core", "sdk-android", "sdk-ios")
        )),
        "codexagent.android-runtime-evidence.gradle.kts": _from_phase("sdk", "sdk-android", "binary"),
        "codexagent.ios-runtime.gradle.kts": _from_phase("sdk", "sdk-ios", "binary"),
    }
    if _is_prefix(path, "gradle/build-logic/src/main/kotlin/"):
        name = path.rsplit("/", 1)[-1]
        if name == "NativeWrapperMetadataContentTask.kt":
            return set().union(*(
                _from_phase("sdk", language, "metadata") for language in NATIVE_BINDINGS
            ))
        if name in _CONTRACT_EVIDENCE_BUILD_LOGIC:
            return _contract() | _sdk_validation()
        if name in {"VerifyProtocolSourceTask.kt", "codexagent.core-verification.gradle.kts"}:
            return _contract()
        if name in _ANDROID_VALIDATION_BUILD_LOGIC:
            return _from_phase("sdk", "sdk-android", "validation")
        if name in _IOS_VALIDATION_BUILD_LOGIC:
            return _from_phase("sdk", "sdk-ios", "validation")
        if name in _IOS_PACKAGE_BUILD_LOGIC:
            return _from_phase("sdk", "sdk-ios", "package")
        if name in _IOS_BINARY_BUILD_LOGIC:
            return _from_phase("sdk", "sdk-ios", "binary")
        if name.startswith("CrossLanguageJavaScript"):
            return _from_phase("sdk", "javascript", "validation")
        if name in {
            "CrossLanguageNativeWrapperSdkStaging.kt",
            "CrossLanguageNativeWrapperGradleTasks.kt",
            "CrossLanguageCAbiClient.kt",
        }:
            return _bindings(NATIVE_BINDINGS)
        if name.startswith("CrossLanguageNativeWrapper") or name in {
            "CrossLanguageCAbiBindingEvidence.kt",
            "NativeWrapperInstalledConsumerTask.kt",
            "NativeWrapperCapabilityEvidenceTask.kt",
        }:
            return set().union(*(
                _from_phase("sdk", language, "validation") for language in NATIVE_BINDINGS
            ))
        if name.startswith("CrossLanguage") or name in {
            "CanonicalTestResultsClient.kt",
            "VerifyImportedSdkBindingParityTask.kt",
        }:
            return _sdk_validation()
        if name == "SdkMavenPackageTask.kt":
            return set().union(*(
                _from_phase("sdk", component, "package")
                for component in ("sdk-core", "sdk-android", "sdk-ios", "javascript")
            ))
        if name in {
            "FacadePublicationContract.kt",
            "KmpConsumerVerificationTask.kt",
        }:
            return _from_phase("sdk", "sdk-core", "validation")
        if name in {
            "GenerateProtocolTask.kt",
            "codexagent.protocol-generator.gradle.kts",
        }:
            return _from_phase("contract", "contract", "validation")
        if name == "codexagent.contract-product.gradle.kts":
            return _contract().union(*(
                _from_phase("sdk", component, "binary")
                for component in ("sdk-core", "sdk-android", "sdk-ios")
            ))
        if name in {
            "CodexAgentBuild.kt",
            "ProductOutputManifestGradleTask.kt",
            "ProductPythonTooling.kt",
            "ProductVersions.kt",
            "ProductVersionIdentity.kt",
            "PrepareCodexRuntimeTask.kt",
            "codexagent.codex-runtime.gradle.kts",
        }:
            return set(ALL_INSTANCES)
        selected = sdk_build_logic.get(name)
        if selected is not None:
            return selected

    if path in {
        "gradle/build-logic/build.gradle.kts",
        "gradle/build-logic/settings.gradle.kts",
        "gradle/libs.versions.toml",
        "gradle/wrapper/gradle-wrapper.jar",
        "gradle/wrapper/gradle-wrapper.properties",
        "gradlew",
        "gradlew.bat",
    }:
        return set(ALL_INSTANCES)

    return None


def _direct_owners(path: str, selected: set[PhaseInstanceId]) -> set[PhaseInstanceId]:
    if path in {"gradle/build-logic/build.gradle.kts", "gradle/build-logic/settings.gradle.kts",
                "gradle/build-logic/src/main/kotlin/ProductPythonTooling.kt"}:
        # Standalone Runtime includes only runtime/build-logic; still plan broad reuse.
        selected = {instance for instance in selected if instance.product != "runtime"}
    if path in {"ci/products/sdk_inputs.py", "ci/products/sdk_native.py", "ci/products/sdk_package.py"}:
        return {instance for instance in selected if instance.product == "sdk"
                and instance.component in NATIVE_BINDINGS and instance.phase == "validation"}
    if (
        path in _CONTRACT_BUILD_INPUTS
        or path == "gradle/release/versions/contract.txt"
        or _is_prefix(path, "codex-agent-core/")
    ):
        selected = {instance for instance in selected if instance.product == "contract"}
    if path in _METADATA_AUTHORITIES:
        return selected

    direct: set[PhaseInstanceId] = set()
    if path in {"gradle/build-logic/build.gradle.kts",
                "gradle/build-logic/src/main/kotlin/ProductPythonTooling.kt"}:
        # Imported native validation executes packaged tooling even when its package is reused.
        direct.update(PhaseInstanceId("sdk", language, "validation", target)
                      for language in NATIVE_BINDINGS for target in NATIVE_TARGETS)
    if path == "codex-agent-runtime-desktop/codex-app-server-distributions.json":
        # Imported JVM/Node host validation reads this original source independently of binary reuse.
        direct.update(instance for instance in selected if instance.product == "runtime"
                      and instance.component in {"jvm", "node-js", "node-wasm"}
                      and instance.phase == "validation" and instance.target in NATIVE_TARGETS)
    if path in {"ci/products/sdk_runtime_content.py", "ci/products/contract_model.py",
                "ci/products/runtime_adapter_validation.py",
                "ci/products/test_results.py", "ci/products/runtime_evidence.py",
                "ci/products/runtime_variant.py", "ci/products/c_abi.py"}:
        # Both package planning and imported validation independently execute the full gate.
        direct.update(instance for instance in selected if instance.product == "sdk"
                      and instance.component in NATIVE_BINDINGS and instance.phase == "validation")
    if path == "ci/products/runtime_attestation.py":
        # Imported native validation authenticates original stages even on package reuse.
        direct.update(instance for instance in selected if instance.product == "sdk"
                      and instance.component in NATIVE_BINDINGS and instance.phase == "validation")
    if path in {
        "ci/native_wrappers.py",
        "codex-agent-bindings/cpp/CMakeLists.txt",
        "codex-agent-bindings/cpp/tools/generate_native_dispatch.py",
    }:
        direct.update(instance for instance in selected if instance.phase == "validation")
    language = _binding_language(path)
    if language in NATIVE_BINDINGS and _binding_validation_path(path, language):
        # Native packages ship their consumer/test sources; validation executes them too.
        direct.update(instance for instance in selected if instance.phase == "validation")
    if path == "runtime/build-logic/src/main/kotlin/NodeBindingValidationTask.kt":
        # Staging also owns the safe copy helper called by imported validation.
        direct.add(PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"))
    if path in {
        "runtime/build-logic/src/main/kotlin/RuntimeCAbiClient.kt",
        "runtime/build-logic/src/main/kotlin/CrossLanguageCAbiRuntimeProduction.kt",
    }:
        # Imported native validation executes these helpers even when package bytes are unchanged.
        direct.update(PhaseInstanceId("runtime", target, "validation", target) for target in NATIVE_TARGETS)
    if path == "runtime/build-logic/src/main/kotlin/RuntimeAdapterMetadataInputsTask.kt":
        direct.add(PhaseInstanceId("runtime", "macos-arm64", "validation", "macos-arm64"))
    if path == "runtime/build-logic/src/main/kotlin/RuntimeAdapterMavenHandoff.kt":
        # Metadata executes the imported publication producer independently of binary capture.
        direct.update(PhaseInstanceId("runtime", component, "metadata", component)
                      for component in ("jvm", "node-js", "node-wasm"))
    if path == "runtime/build-logic/src/main/kotlin/RuntimeReleaseIo.kt":
        # Checked-byte adapter staging hashes imports independently of validation.
        direct.update(instance for instance in selected if instance.phase == "validation")
        direct.update(PhaseInstanceId("runtime", component, "metadata", component)
                      for component in ("jvm", "node-js", "node-wasm"))
    if path in {"runtime/build-logic/src/main/kotlin/RuntimeProductPythonTooling.kt",
                "runtime/build-logic/src/main/kotlin/RuntimeReleaseIo.kt"}:
        # The isolated verifier hashes its capture in each independently imported phase.
        direct.update(PhaseInstanceId("runtime", component, "binary", component)
                      for component in RUNTIME_COMPONENTS)
        direct.update(PhaseInstanceId("runtime", target, "package", target) for target in NATIVE_TARGETS)
    if path == "runtime/build-logic/src/main/kotlin/RuntimeProductPythonTooling.kt":
        direct.update(PhaseInstanceId("runtime", target, "validation", target) for target in NATIVE_TARGETS)
        direct.update(PhaseInstanceId("runtime", component, "validation", target)
                      for component in ("jvm", "node-js", "node-wasm") for target in NATIVE_TARGETS)
        direct.update(PhaseInstanceId("runtime", component, "metadata", component)
                      for component in ("jvm", "node-js", "node-wasm"))
    components = {(instance.product, instance.component) for instance in selected}
    for product, component in components:
        members = {
            instance for instance in selected
            if (instance.product, instance.component) == (product, component)
        }
        earliest = min(PHASE_ORDER.index(instance.phase) for instance in members)
        direct.update(
            instance for instance in members if PHASE_ORDER.index(instance.phase) == earliest
        )
    if any(
        instance.product == "runtime" and instance.component != "runtime-aggregate"
        for instance in direct
    ):
        direct.discard(
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        )
    return direct


def phase_inventory_paths(
    repository_paths: Iterable[str],
    instance: PhaseInstanceId,
) -> tuple[str, ...]:
    """Return this phase's complete direct Git input paths, excluding successor inputs."""
    if instance not in ALL_INSTANCES:
        raise ValueError(f"Unknown product phase instance: {instance}")
    owned = []
    for path in _normalized_paths(repository_paths):
        if (
            path == _RUNTIME_BINARY_FLAGS_PATH
            or path in _RUNTIME_TOOLCHAIN_PROFILE_PATHS
            or path in _DOC_FILES
            or path in _STATIC_ONLY_FILES
            or _is_prefix(path, "docs/")
            or _is_prefix(path, "ci/tests/")
            or any(_is_prefix(path, prefix) for prefix in _STATIC_TEST_PREFIXES)
        ):
            continue
        selected = _classify(path)
        if selected is None:
            owned.append(path)
        elif not _is_control_only(path) and instance in (_direct_owners(path, selected) | _native_metadata_owners(path)):
            owned.append(path)
    return tuple(owned)


def phase_file_inventory(
    root: Path,
    repository_paths: Iterable[str],
    instance: PhaseInstanceId,
) -> list[dict[str, object]]:
    """Hash only the exact direct file inputs owned by one phase instance."""
    paths = tuple(repository_paths)
    return file_inventory(root, phase_inventory_paths(paths, instance))


def phase_git_inventory(
    root: Path,
    revision: str,
    instance: PhaseInstanceId,
) -> list[dict[str, object]]:
    """Derive and hash a phase's complete direct inputs from one exact Git tree."""
    if type(revision) is not str or _GIT_OBJECT_ID.fullmatch(revision) is None:
        raise ValueError("Repository revision must be an exact lowercase Git object ID")
    try:
        paths = tuple(path for path, _ in tree_entries(Path(root), revision))
        return git_file_inventory(root, revision, phase_inventory_paths(paths, instance))
    except subprocess.CalledProcessError as error:
        raise ValueError("Repository revision cannot be inventoried") from error


def classify_paths(paths: Iterable[str]) -> PathSelection:
    normalized = _normalized_paths(paths)
    selected: set[PhaseInstanceId] = set()
    inventory = []
    ignored = []
    unknown = []
    for path in normalized:
        if (
            path in _DOC_FILES
            or path in _STATIC_ONLY_FILES
            or _is_prefix(path, "docs/")
            or _is_prefix(path, "ci/tests/")
            or any(_is_prefix(path, prefix) for prefix in _STATIC_TEST_PREFIXES)
        ):
            ignored.append(path)
            continue
        owned = _classify(path)
        if owned is None:
            unknown.append(path)
            inventory.append(path)
            continue
        if not _is_control_only(path):
            inventory.append(path)
        selected.update(owned | _native_metadata_owners(path))
        if (PhaseInstanceId("contract", "contract", "binary", "common") in owned
                and not _is_prefix(path, "codex-agent-core/src/jsMain/")):
            # Coverage producers can change evidence without changing native
            # compatibility. Plan downstream keys; do not give them Contract source ownership.
            selected.update(_runtime(("macos-arm64",), "validation"))
            for component in SDK_COMPATIBILITY_COMPONENTS:
                selected.update(_from_phase("sdk", component, "package"))
    if unknown:
        selected = set(ALL_INSTANCES)
    return PathSelection(
        tuple(sorted(selected)),
        tuple(inventory),
        tuple(ignored),
        tuple(unknown),
        not unknown,
    )
