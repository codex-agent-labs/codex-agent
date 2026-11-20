"""Map authenticated Runtime adapter predecessors and execute fixed package copies.

The caller owns original-state replay, receipt authentication and validation
handoff construction. These properties are not execution admission or proof.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import shutil
import subprocess
from typing import Any

from products.inventory import (
    git_regular_blob_bytes, require_regular_directory, require_semver, snapshot_regular_tree,
)
from products.plan import _runtime_compatibility_version
from products.receipt import verify_output_manifest_identity, write_output_manifest
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS, RUNTIME_ADAPTERS
from products.runtime_evidence import PINNED_NODE_VERSION


def _identity(plan: Mapping[str, Any]) -> tuple[str, str, str, str]:
    identity = tuple(plan.get(key) for key in ("product", "component", "phase", "target"))
    if identity[0] != "runtime" or identity[1] not in RUNTIME_ADAPTERS or not any(
        identity == (item.product, item.component, item.phase, item.target)
        for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported Runtime adapter phase identity")
    return identity


def route(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Select existing runner topology, not an observed runner or execution proof."""
    _, _, phase, target = _identity(plan)
    # Host validations execute the imported native package on its actual host.
    # Other adapter work, including JS binding validation, uses the portable lane.
    host = target if phase == "validation" and target in NATIVE_TARGETS else "linux-x64"
    runner, runner_os, runner_arch = {
        "linux-arm64": ("ubuntu-24.04-arm", "Linux", "ARM64"),
        "linux-x64": ("ubuntu-24.04", "Linux", "X64"),
        "macos-arm64": ("macos-26", "macOS", "ARM64"),
        "macos-x64": ("macos-26-intel", "macOS", "X64"),
        "windows-x64": ("windows-2025", "Windows", "X64"),
    }[host]
    # The registry assigns toolchain profiles only to native Runtime binary phases.
    return {"runner": runner, "runnerOs": runner_os, "runnerArch": runner_arch,
            "toolchainProfile": None, "producerRole": None, "supervisor": None}


def preflight(
    plan: Mapping[str, Any], *, repository_root: Path, environ: Mapping[str, str],
) -> dict[str, str]:
    """Observe required Node only; the shared worker owns host/environment checks.

The caller supplies the sanitized execution environment. The fixed observation
does not authenticate a compiler, assign a profile, or replace runtime tests.
"""
    _, component, phase, _ = _identity(plan)
    if component == "jvm" or phase not in {"binary", "validation"}:
        return {}
    executable = shutil.which("node", path=environ.get("PATH", ""))
    if executable is None:
        raise ValueError("Runtime adapter requires installed Node")
    node = Path(executable).resolve(strict=True)
    observed = subprocess.run(
        [str(node), "--version"], cwd=repository_root, env=dict(environ),
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
    )
    if observed.returncode != 0 or observed.stdout.decode("ascii").strip() != f"v{PINNED_NODE_VERSION}":
        raise ValueError(f"Runtime adapter requires exactly Node v{PINNED_NODE_VERSION}")
    return {"nodeExecutable": str(node), "nodeVersion": PINNED_NODE_VERSION}


def _directory(value: Path, label: str) -> str:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{label} must be an absolute normalized directory")
    require_regular_directory(value, label)
    if value.resolve(strict=True) != value:
        raise ValueError(f"{label} must be a non-symbolic normalized directory")
    return str(value)


def properties(
    plan: Mapping[str, Any], *,
    predecessor: Callable[[str, str, str], Mapping[str, Any]],
    validation_handoff: Path | None = None,
) -> dict[str, str]:
    """Return adapter-specific properties only, without reading product bytes.

``predecessor`` returns the original authenticated stage, receiptPath and
receipt; the receipt identity is checked here only to catch incorrect routing.
``validation_handoff`` must be the caller's already-validated, derived handoff,
not a caller-selected Maven repository or an unverified projection.
"""
    _, component, phase, target = _identity(plan)
    if phase == "metadata":
        if validation_handoff is None:
            raise ValueError("Runtime adapter metadata requires its validated handoff")
        handoff = _directory(validation_handoff, "Runtime validation handoff")
    elif validation_handoff is not None:
        raise ValueError("Runtime validation handoff is only a metadata input")

    def imported(owner: str, source_phase: str, source_target: str, prefix: str) -> dict[str, str]:
        original = predecessor(owner, source_phase, source_target)
        receipt = original["receipt"]
        if tuple(receipt.get(key) for key in ("product", "component", "phase", "target")) != (
            "runtime", owner, source_phase, source_target,
        ):
            raise ValueError("Runtime adapter predecessor receipt has the wrong identity")
        return {
            f"codexAgent.{prefix}Stage": _directory(original["stage"], "Original Runtime stage"),
            f"codexAgent.{prefix}Version": require_semver(receipt["productVersion"], "Original Runtime version"),
        }

    if phase == "binary":
        return {}
    if phase == "package":
        return imported(component, "binary", component, "runtimeBinary")
    if phase == "metadata":
        return {"codexAgent.runtimeValidationHandoff": handoff}
    result = imported(component, "package", component, "runtimePackage")
    if phase == "validation" and target in NATIVE_TARGETS:
        result.update(imported(target, "package", target, "runtimeNativePackage"))
    return result


def _package_inputs(plan, properties, *, repository_root, revision, verified_contract_manifest):
    """Check routing of the caller's authenticated Contract and private B snapshot.

    This is not an admission API. The owning worker keeps original receipt,
    source and input lifetime checks around execution and finalization.
    """
    identity = tuple(plan.get(key) for key in ("product", "component", "phase", "target"))
    if identity not in {(i.product, i.component, i.phase, i.target) for i in PHASE_INSTANCE_IDS
                        if i.product == "runtime" and i.phase == "package"}:
        raise ValueError("Runtime package requires an exact registered package identity")
    if tuple(properties.get("codexAgent." + key) for key in
             ("product", "component", "phase", "target")) != identity:
        raise ValueError("Runtime package properties differ from its elected identity")
    if properties.get("codexAgent.candidateCommit") != revision:
        raise ValueError("Runtime package candidate differs from its exact source")
    version = require_semver(properties["codexAgent.runtimeVersion"], "Runtime version")
    if git_regular_blob_bytes(repository_root, revision, "gradle/release/versions/runtime.txt",
                              max_bytes=1024) != (version + "\n").encode("ascii"):
        raise ValueError("Runtime package version differs from its Git authority")
    manifest = verified_contract_manifest
    if (manifest["contractVersion"] != properties["codexAgent.contractVersion"]
            or any(part not in manifest["components"] for part in ("common", identity[1]))):
        raise ValueError("Runtime package requires its exact Contract version and components")
    previous = require_semver(properties["codexAgent.runtimeBinaryVersion"], "Original Runtime version")
    if "+" in version or "+" in previous:
        raise ValueError("Runtime compatibility versions must not contain build metadata")
    compatibility = _runtime_compatibility_version(version)
    if _runtime_compatibility_version(previous) != compatibility:
        raise ValueError("Original Runtime binary is outside the current compatibility line")
    original = Path(_directory(Path(properties["codexAgent.runtimeBinaryStage"]), "Original Runtime binary"))
    verify_output_manifest_identity(original, "runtime", identity[1], "binary", identity[1], previous)
    return identity[1], version, compatibility, original, previous


def _fresh_package_stage(stage_root):
    stage = Path(stage_root)
    if not stage.is_absolute() or stage.resolve(strict=False) != stage:
        raise ValueError("Runtime package output must be an absolute normalized path")
    stage.mkdir(parents=True, exist_ok=False)
    return stage


def execute_package(plan, properties, *, repository_root, revision, stage_root,
                    verified_contract_manifest):
    """Copy only the fixed package roots from an authenticated adapter B stage."""
    _identity(plan)
    component, version, _, original, previous = _package_inputs(
        plan, properties, repository_root=repository_root, revision=revision,
        verified_contract_manifest=verified_contract_manifest)
    stage = _fresh_package_stage(stage_root)
    kinds = ("adapter", "publication", "validation-runner")
    if component == "node-js":
        kinds += ("binding-test-runner",)
    roots = {kind: "outputs/" + kind for kind in kinds}
    for relative in roots.values():
        snapshot_regular_tree(original / relative, stage / relative)
    verify_output_manifest_identity(original, "runtime", component, "binary", component, previous)
    write_output_manifest(stage, "runtime", component, "package", component, version, roots)
    return {"command": [], "returnCode": 0}
