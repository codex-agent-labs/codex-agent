"""Translate authenticated SDK predecessors into existing artifact-only inputs.

Only JavaScript package/validation currently have routes here. The caller owns
full original receipt/plan/Contract/Runtime authentication and common versions.
This module does not turn an embedded compatibility declaration into trust.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from products.inventory import read_regular_file_bytes, require_regular_directory, require_semver
from products.registry import PHASE_INSTANCE_IDS


def _identity(plan: Mapping[str, Any]) -> tuple[str, str, str, str]:
    identity = tuple(plan.get(field) for field in ("product", "component", "phase", "target"))
    if identity not in (("sdk", "javascript", "package", "node"), ("sdk", "javascript", "validation", "node")) or not any(
        identity == (item.product, item.component, item.phase, item.target) for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported implemented SDK phase identity")
    return identity


def route(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return the existing portable runner, not an observed host or toolchain."""
    _identity(plan)
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
    _, _, phase, _ = _identity(plan)
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
