"""Native Gradle arguments from an already authenticated original phase closure.

This is translation, not admission, planning, toolchain observation or execution.
The worker owns authentication and the common Contract/version/candidate fields.
"""
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import re
from typing import Any

from products.inventory import require_exact_keys, require_semver, require_sha256
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId, required_toolchain_profile


_HOSTS = {
    "macos-arm64": ("macos-26", "macOS", "ARM64"),
    "macos-x64": ("macos-26-intel", "macOS", "X64"),
    "linux-arm64": ("ubuntu-24.04-arm", "Linux", "ARM64"),
    "linux-x64": ("ubuntu-24.04", "Linux", "X64"),
    "windows-x64": ("windows-2025", "Windows", "X64"),
}


def _native_plan(plan: dict[str, Any]) -> dict[str, Any]:
    value = require_exact_keys(plan, {
        "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
    }, "Native Runtime elected phase plan")
    component, phase = value["component"], value["phase"]
    if (type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["product"] != "runtime" or component not in NATIVE_TARGETS
            or value["target"] != component or phase not in ("binary", "package", "validation", "metadata")
            or type(value["inputs"]) is not dict):
        raise ValueError("Unsupported native Runtime phase plan identity or schema")
    instance = PhaseInstanceId("runtime", component, phase, component)
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError("Native Runtime phase is not in the product registry")
    require_sha256(value["buildKey"], "Native Runtime elected build key")
    return value


def route(plan: dict[str, Any]) -> dict[str, Any]:
    """Fixed worker topology, never an observation or permission to execute.

    Package/metadata consume imported bytes on Linux X64. Validation executes
    on the real target host. Linux Arm64 binary requires BOTH named producers;
    the supervisor descriptor is an unresolved prerequisite, not supplied proof.
    """
    value = _native_plan(plan)
    component, phase = value["component"], value["phase"]
    instance = PhaseInstanceId("runtime", component, phase, component)
    host = component if phase in {"binary", "validation"} else "linux-x64"
    role = "builder" if phase == "binary" else None
    supervisor = None
    if component == "linux-arm64" and phase == "binary":
        host, role = "linux-x64", "cross-builder"
        label, os_name, arch = _HOSTS["linux-arm64"]
        supervisor = {"runner": label, "runnerOs": os_name, "runnerArch": arch,
                      "producerRole": "supervisor-builder"}
    label, os_name, arch = _HOSTS[host]
    return {"runner": label, "runnerOs": os_name, "runnerArch": arch,
            "toolchainProfile": required_toolchain_profile(instance),
            "producerRole": role, "supervisor": supervisor}


def _path(value: Path, label: str) -> str:
    if not isinstance(value, Path) or not value.is_absolute() or Path(os.path.normpath(value)) != value:
        raise ValueError(f"{label} must be an absolute normalized Path")
    return str(value)


def properties(
    plan: dict[str, Any], *, plan_path: Path, revision: str,
    predecessor: Callable[[str, str, str], dict[str, Any]],
    output: Callable[[str, str, str, str], Path],
    report: Callable[[str, str], Path],
) -> dict[str, str]:
    """Map only existing native-specific properties; never supply source fallbacks.

    In particular, Linux Arm64 cross-production still requires its independently
    provided real Arm64 supervisor/toolchain. No such evidence is invented here.
    """
    value = _native_plan(plan)
    component, phase = value["component"], value["phase"]
    selected_plan = _path(plan_path, "Native Runtime elected plan path")
    if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
        raise ValueError("Native Runtime repository revision must be an exact Git object ID")

    def original(selected_phase: str) -> dict[str, Any]:
        record = require_exact_keys(predecessor(component, selected_phase, component),
                                    {"stage", "receiptPath", "receipt"}, "Original native Runtime predecessor")
        receipt = record["receipt"]
        if (type(receipt) is not dict or type(receipt.get("schemaVersion")) is not int
                or receipt.get("schemaVersion") != 1 or receipt.get("result") != "success"
                or (receipt.get("product"), receipt.get("component"), receipt.get("phase"), receipt.get("target"))
                != ("runtime", component, selected_phase, component)):
            raise ValueError("Original native Runtime predecessor receipt identity is invalid")
        require_semver(receipt.get("productVersion"), "Original native Runtime predecessor version")
        _path(record["stage"], "Original native Runtime predecessor stage")
        _path(record["receiptPath"], "Original native Runtime predecessor receipt path")
        return record

    if phase == "binary":
        return {
            "codexAgent.runtimeBinaryPlan": selected_plan,
            "codexAgent.runtimeBinaryFlagsDigest": require_sha256(
                value["inputs"].get("flagsDigest"), "Native Runtime elected flags digest"),
            "codexAgent.repositoryRevision": revision,
        }
    if phase in {"package", "validation"}:
        selected_phase = "binary" if phase == "package" else "package"
        record = original(selected_phase)
        prefix = "runtimeBinary" if phase == "package" else "runtimePackage"
        return {
            f"codexAgent.{prefix}Stage": str(record["stage"]),
            f"codexAgent.{prefix}Version": record["receipt"]["productVersion"],
        }

    originals = {selected_phase: original(selected_phase) for selected_phase in ("binary", "package", "validation")}
    return {
        "codexAgent.runtimeVariantIdentity": _path(
            output(component, "binary", component, "runtime-identity"), "Original native Runtime identity"),
        **{f"codexAgent.runtimeVariant{selected_phase.title()}Receipt": str(record["receiptPath"])
           for selected_phase, record in originals.items()},
        "codexAgent.runtimeVariantCAbiArchive": _path(
            output(component, "package", component, "c-abi"), "Original native C ABI archive"),
        "codexAgent.runtimeVariantAppServerArchive": _path(
            output(component, "package", component, "app-server"), "Original native app-server archive"),
        "codexAgent.runtimeVariantValidationEvidence": _path(
            report(component, component), "Original native validation report"),
    }
