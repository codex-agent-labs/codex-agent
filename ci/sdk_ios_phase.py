"""Translate authenticated iOS SDK package inputs to the existing Apple task.

The caller owns receipt/plan admission and common candidate identity. This
module neither maps ``ciProductPhase`` nor claims Apple host execution.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import re
from typing import Any

from products.inventory import read_regular_file_bytes, require_regular_directory, require_semver
from products.registry import PHASE_INSTANCE_IDS


TASK = ":codex-agent-runtime-ios:verifyTransportedCodexAgentIosSdkPackageClosure"
FRESH_EXPORT_TASK = ":codex-agent-runtime-ios:exportCodexAgentIosVerifiedDistribution"
_IDENTITY = ("sdk", "sdk-ios", "package", "ios")
_GIT_ID = re.compile(r"[0-9a-f]{40}")


def _identity(plan: Mapping[str, Any]) -> None:
    identity = tuple(plan.get(field) for field in ("product", "component", "phase", "target"))
    if identity != _IDENTITY or not any(
        identity == (item.product, item.component, item.phase, item.target)
        for item in PHASE_INSTANCE_IDS
    ):
        raise ValueError("Unsupported implemented iOS SDK phase identity")


def _directory(value: Path, label: str) -> str:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{label} must be an absolute normalized directory")
    require_regular_directory(value, label)
    if value.resolve(strict=True) != value:
        raise ValueError(f"{label} must be non-symbolic and normalized")
    return str(value)


def _request(value: Path, label: str = "SDK compatibility request") -> str:
    if not isinstance(value, Path) or not value.is_absolute():
        raise ValueError(f"{label} must be an absolute normalized file")
    contents = read_regular_file_bytes(
        value, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    if not contents or value.resolve(strict=True) != value:
        raise ValueError(f"{label} must be nonempty, non-symbolic and normalized")
    return str(value)


def properties(
    plan: Mapping[str, Any], *,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    verified_distribution: Path,
    native_evidence: Path,
    compatibility_request: Path,
    expected_sdk_compatibility: Path,
    expected_distribution_proof: Path,
) -> dict[str, str]:
    """Return only existing imported-package properties; ``TASK`` executes them."""
    _identity(plan)
    distribution = _directory(verified_distribution, "Original Apple verified distribution")
    native = _directory(native_evidence, "Original Apple native evidence")
    request = _request(compatibility_request)
    compatibility = _request(expected_sdk_compatibility, "Caller SDK compatibility")
    proof = _request(expected_distribution_proof, "Caller original Apple distribution proof")
    original = predecessor("contract", "contract", "binary", "common")
    receipt = original["receipt"]
    if tuple(receipt.get(field) for field in ("product", "component", "phase", "target")) != (
        "contract", "contract", "binary", "common",
    ):
        raise ValueError("iOS SDK predecessor receipt has the wrong identity")
    version = require_semver(receipt.get("productVersion"), "Original Contract version")
    contract = _directory(original["stage"], "Original Contract binary stage")
    return {
        "codexAgent.contractBinaryStage": contract,
        "codexAgent.contractVersion": version,
        "codexAgent.iosVerifiedDistributionDirectory": distribution,
        "codexAgent.iosNativeEvidenceDirectory": native,
        "codexAgent.sdkCompatibilityRequest": request,
        "codexAgent.iosExpectedSdkCompatibility": compatibility,
        "codexAgent.iosExpectedDistributionProof": proof,
    }


def fresh_export_properties(
    plan: Mapping[str, Any], *,
    predecessor: Callable[[str, str, str, str], Mapping[str, Any]],
    native_evidence: Path,
    compatibility_request: Path,
    candidate_commit: str,
    candidate_tree: str,
) -> dict[str, str]:
    """Route caller-authenticated originals to the existing fresh exporter.

    This translation grants neither Apple host execution nor signature trust.
    """
    _identity(plan)
    if any(not isinstance(value, str) or _GIT_ID.fullmatch(value) is None
           for value in (candidate_commit, candidate_tree)):
        raise ValueError("Fresh Apple producer commit/tree identity is invalid")
    native = _directory(native_evidence, "Original Apple native evidence")
    request = _request(compatibility_request)
    original = predecessor("contract", "contract", "binary", "common")
    receipt = original["receipt"]
    if tuple(receipt.get(field) for field in ("product", "component", "phase", "target")) != (
        "contract", "contract", "binary", "common",
    ):
        raise ValueError("iOS SDK predecessor receipt has the wrong identity")
    version = require_semver(receipt.get("productVersion"), "Original Contract version")
    contract = _directory(original["stage"], "Original Contract binary stage")
    return {
        "codexAgent.candidateCommit": candidate_commit,
        "codexAgent.candidateTree": candidate_tree,
        "codexAgent.iosContractBinaryStage": contract,
        "codexAgent.contractVersion": version,
        "codexAgent.iosNativeEvidenceDirectory": native,
        "codexAgent.sdkCompatibilityRequest": request,
    }
