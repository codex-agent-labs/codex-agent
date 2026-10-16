"""Shared SDK routing declarations and artifact-only input translation.

Register workflow addresses once in SDK_FAMILY_ROUTES. Checkpoint support must
retain its existing family verifier and bounded transport format before enabling
the checkpoint flag. Physical input scopes never reduce dependency authentication.
This module does no I/O and grants no producer, signature or semantic authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from products.inventory import read_regular_file_bytes, require_regular_directory, require_semver
from products.registry import NATIVE_BINDINGS, NATIVE_TARGETS, PHASE_INSTANCE_IDS, SDK_FACADE_TARGETS, PhaseInstanceId


@dataclass(frozen=True, slots=True)
class SdkFamilyRoute:
    """Reviewed workflow addresses only; this record grants no admission."""

    family: str
    wave: int
    predecessor: str
    election: str
    workers: str
    child: str | None = None
    parent: str | None = None
    checkpoint: bool = False

    @property
    def stage(self):
        return self.family.removeprefix("native-")

    @property
    def collector(self):
        return f"sdk-collect-{self.wave}"

    @property
    def collector_job(self):
        prefix = "product-validation / " + (self.parent + " / " if self.parent else "")
        return prefix + self.collector

    @property
    def workflow_path(self):
        return f".github/workflows/{self.child or 'product-validation'}.yml"


# Wave numbers are immutable upload identities, not execution order. Checkpoint
# support is deliberately explicit: a routing row never enables a new verifier.
SDK_FAMILY_ROUTES = (
    SdkFamilyRoute("csharp-binary", 19, "sdk-javascript-metadata-result", "sdk-csharp-binary-plan", "sdk-csharp-binary"),
    SdkFamilyRoute("native-package", 4, "sdk-csharp-binary-result", "sdk-native-plan", "sdk-native-workers"),
    SdkFamilyRoute("ios-package", 5, "sdk-native-packages", "sdk-ios-package-plan", "sdk-ios-package"),
    SdkFamilyRoute("javascript-metadata", 6, "sdk-javascript", "sdk-javascript-metadata-plan", "sdk-javascript-metadata"),
    SdkFamilyRoute("native-validation", 7, "sdk-ios-packages", "sdk-native-validation-plan", "sdk-native-validation"),
    SdkFamilyRoute("native-metadata", 8, "sdk-native-validation-result", "sdk-native-metadata-plan", "sdk-native-metadata"),
    SdkFamilyRoute("ios-validation", 9, "sdk-native-result", "sdk-native-result", "sdk-ios-validation", checkpoint=True),
    SdkFamilyRoute("ios-metadata", 10, "sdk-ios-validation-result", "sdk-ios-metadata-plan", "sdk-ios-metadata", checkpoint=True),
    SdkFamilyRoute("core-binary", 11, "sdk-ios-metadata-result", "sdk-core-binary-plan", "sdk-core-binary",
                   "sdk-core-binary-validation", "sdk-core-binary-wave", True),
    SdkFamilyRoute("core-package", 12, "sdk-core-binary-wave", "sdk-core-package-plan", "sdk-core-package",
                   "sdk-core-package-validation", "sdk-core-package-wave", True),
    SdkFamilyRoute("core-validation", 13, "sdk-core-package-wave", "sdk-core-validation-plan", "sdk-core-validation",
                   "sdk-core-validation", "sdk-core-validation-wave", True),
    SdkFamilyRoute("core-metadata", 14, "sdk-core-validation-wave", "sdk-core-metadata-plan", "sdk-core-metadata",
                   "sdk-core-metadata-validation", "sdk-core-metadata-wave", True),
    SdkFamilyRoute("android-binary", 15, "sdk-core-metadata-wave", "sdk-android-binary-plan", "sdk-android-binary",
                   "sdk-android-binary-validation", "sdk-android-binary-result", True),
    SdkFamilyRoute("android-package", 16, "sdk-android-binary-result", "sdk-android-package-plan", "sdk-android-package",
                   "sdk-android-package-validation", "sdk-android-package-result", True),
    SdkFamilyRoute("android-validation", 17, "sdk-android-package-result", "sdk-android-validation-plan", "sdk-android-validation",
                   "sdk-android-validation", "sdk-android-validation-result"),
    SdkFamilyRoute("android-metadata", 18, "sdk-android-validation-result", "sdk-android-metadata-plan", "sdk-android-metadata",
                   "sdk-android-metadata-validation", "sdk-android-metadata-result"),
)


def _family_instances(family):
    component, phase = family.rsplit("-", 1)
    components = NATIVE_BINDINGS if component == "native" else (
        "sdk-" + component if component in {"core", "android", "ios"} else component,)
    return tuple(item for item in PHASE_INSTANCE_IDS
                 if item.product == "sdk" and item.component in components and item.phase == phase)


SDK_FAMILY_INSTANCES = {row.family: frozenset(_family_instances(row.family)) for row in SDK_FAMILY_ROUTES}
CHECKPOINT_ROUTES = {row.collector_job: row for row in SDK_FAMILY_ROUTES if row.checkpoint}
LEGACY_REPLAY_INSTANCES = tuple(PhaseInstanceId("sdk", "javascript", phase, "node")
    for phase in ("package", "validation", "metadata")) + (PhaseInstanceId("sdk", "csharp", "binary", "desktop"),)
COMPACT_REPLAY_INSTANCES = LEGACY_REPLAY_INSTANCES + tuple(
    instance for row in SDK_FAMILY_ROUTES if row.checkpoint for instance in sorted(SDK_FAMILY_INSTANCES[row.family]))


def completed_recovery_folder(instance):
    """Preserve existing on-disk controls and their exact recovery readers."""
    if instance == PhaseInstanceId("sdk", "sdk-ios", "package", "ios"):
        return "prior-failed-sdk-ios-package"
    if instance not in COMPACT_REPLAY_INSTANCES:
        raise ValueError("Unsupported completed SDK recovery phase")
    if instance.component == "javascript":
        return "prior-failed-sdk-javascript" + ("" if instance.phase == "package" else "-" + instance.phase)
    if instance == PhaseInstanceId("sdk", "csharp", "binary", "desktop"):
        return "prior-failed-sdk-csharp"
    return f"prior-completed-{instance.component}-{instance.phase}-{instance.target}"


def maven_consumed_predecessors(instance, *, validation_target=None):
    """Physical inputs only; callers must authenticate the full dependency closure."""
    package = instance in {PhaseInstanceId("sdk", "sdk-core", "package", "common"),
                          PhaseInstanceId("sdk", "sdk-android", "package", "android")}
    validation = instance in SDK_FAMILY_INSTANCES["core-validation"]
    metadata = instance == PhaseInstanceId("sdk", "sdk-core", "metadata", "common")
    if (not (package or validation or metadata)
            or metadata and validation_target is not None and validation_target not in SDK_FACADE_TARGETS
            or not metadata and validation_target is not None):
        raise ValueError("Unsupported Maven consumed-input scope")
    contract = tuple(PhaseInstanceId("contract", "contract", phase, "common")
                     for phase in ("binary", "package", "validation", "metadata"))
    target = "android" if instance.component == "sdk-android" else "common"
    phases = ("binary",) if package else ("binary", "package")
    validations = (SDK_FACADE_TARGETS if validation_target is None else (validation_target,)) if metadata else ()
    return contract + tuple(PhaseInstanceId("sdk", instance.component, phase, target) for phase in phases) + tuple(
        PhaseInstanceId("sdk", "sdk-core", "validation", target) for target in validations)


def _identity(plan: Mapping[str, Any]) -> tuple[str, str, str, str]:
    identity = tuple(plan.get(field) for field in ("product", "component", "phase", "target"))
    supported = (("sdk", "javascript", "package", "node"), ("sdk", "javascript", "validation", "node"),
                 *(("sdk", "sdk-core", "validation", target) for target in SDK_FACADE_TARGETS))
    if identity not in supported or not any(
        identity == (item.product, item.component, item.phase, item.target) for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported implemented SDK phase identity")
    return identity


def route(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the existing portable runner, not an observed host or toolchain."""
    _, component, _, target = _identity(plan)
    if component == "sdk-core":
        from runtime_adapter_phase import route as adapter_route
        host = target if target in NATIVE_TARGETS else "linux-x64"
        if target.startswith("ios-"):
            host = "macos-arm64"
        elif target == "linux-arm64":
            host = "linux-x64"
        return adapter_route({"product": "runtime", "component": "jvm", "phase": "validation", "target": host})
    return {"runner": "ubuntu-24.04", "runnerOs": "Linux", "runnerArch": "X64",
            "toolchainProfile": None, "producerRole": None, "supervisor": None}


def _directory(value: Path) -> str:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError("Original SDK predecessor stage must be an absolute normalized directory")
    require_regular_directory(value, "Original SDK predecessor stage")
    if value.resolve(strict=True) != value:
        raise ValueError("Original SDK predecessor stage must be non-symbolic and normalized")
    return str(value)


def properties(
    plan: Mapping[str, Any], *,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    compatibility_request: Path | None = None,
) -> dict[str, str]:
    """Map only consumed properties, using original independent Runtime versions.

``predecessor`` returns the caller-authenticated original stage/receiptPath/
receipt. Identity checks here catch misrouting; no second receipt gate exists.
Only package executes the compatibility request producer. Imported validation
consumes its original SDK archive and embedded policy after caller admission.
"""
    _, component, phase, _ = _identity(plan)
    if component != "javascript":
        raise ValueError("Core validation requires its authenticated facade request, not JavaScript properties")
    if phase == "package":
        path = compatibility_request
        if not isinstance(path, Path) or not path.is_absolute():
            raise ValueError("SDK package requires its authenticated absolute compatibility request")
        if not read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True):
            raise ValueError("SDK compatibility request must not be empty")
        if path.resolve(strict=True) != path:
            raise ValueError("SDK compatibility request must be normalized")
    elif compatibility_request is not None:
        raise ValueError("SDK imported validation does not consume a compatibility request")

    def original(product: str, component: str, source_phase: str, target: str):
        value = predecessor(product, component, source_phase, target)
        receipt = value["receipt"]
        if tuple(receipt.get(field) for field in ("product", "component", "phase", "target")) != (
            product, component, source_phase, target,
        ):
            raise ValueError("SDK predecessor receipt has the wrong identity")
        version = require_semver(receipt["productVersion"], "Original SDK predecessor version")
        return _directory(value["stage"]), version

    contract, _ = original("contract", "contract", "binary", "common")
    result = {"codexAgent.contractBinaryStage": contract}
    if phase == "package":
        stage, version = original("runtime", "node-js", "package", "node-js")
        result.update({"codexAgent.runtimePackageStage": stage, "codexAgent.runtimePackageVersion": version,
                       "codexAgent.sdkCompatibilityRequest": str(compatibility_request)})
    else:
        stage, version = original("runtime", "node-js", "validation", "node-js-binding")
        package, _ = original("sdk", "javascript", "package", "node")
        result.update({"codexAgent.runtimeBindingValidationStage": stage,
                       "codexAgent.runtimeBindingValidationVersion": version,
                       "codexAgent.sdkPackageStageRoot": package})
    return result
