"""Map authenticated Runtime adapter predecessors to existing Gradle inputs.

The caller owns original-state replay, receipt authentication and validation
handoff construction. These properties are not execution admission or proof.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from products.inventory import require_regular_directory, require_semver
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS, RUNTIME_ADAPTERS


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
    identity = tuple(plan.get(key) for key in ("product", "component", "phase", "target"))
    product, component, phase, target = identity
    if product != "runtime" or component not in RUNTIME_ADAPTERS or not any(
        identity == (item.product, item.component, item.phase, item.target)
        for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported Runtime adapter phase identity")
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
    result = imported(component, "package", component, "runtimePackage")
    if phase == "validation" and target in NATIVE_TARGETS:
        result.update(imported(target, "package", target, "runtimeNativePackage"))
    if phase == "metadata":
        result["codexAgent.runtimeValidationHandoff"] = handoff
    return result
