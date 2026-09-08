"""Native Gradle arguments from an already authenticated original phase closure.

This is translation, not admission, planning, toolchain observation or execution.
The worker owns authentication and the common Contract/version/candidate fields.
"""
from __future__ import annotations

from collections.abc import Callable
import argparse
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes,
    git_regular_blob_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory, require_semver, require_sha256, sha256_bytes,
)
from products.contract_projection import VerifiedContractProjection
from products.plan import attach_runtime_binary_identity
from products.registry import NATIVE_TARGETS, PHASE_INSTANCE_IDS, PhaseInstanceId, required_toolchain_profile
from products.runtime_identity import verify_runtime_binary_plan
from products.runtime_evidence import PRODUCT_RUNTIME_TARGETS, read_distribution_manifest
from products.receipt import compute_build_key, validate_receipt_inputs


_DISTRIBUTION_MANIFEST = "codex-agent-runtime-desktop/codex-app-server-distributions.json"
_PINNED_ARCHIVE_LIMIT = 512 * 1024 * 1024


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


def binary_plan(
    plan: dict[str, Any], *, repository_root: Path, revision: str,
    contract_projection: VerifiedContractProjection,
    verified_contract_manifest: dict[str, Any], runtime_version: str,
) -> dict[str, Any]:
    """Attach the existing identity without changing the elected receipt plan.

    The caller supplies the existing authenticated Contract projection/manifest.
    This does not observe a toolchain or supply Linux Arm64 supervisor evidence.
    """
    value = _native_plan(plan)
    if value["phase"] != "binary":
        raise ValueError("Runtime binary identity requires a native binary phase")
    instance = PhaseInstanceId("runtime", value["component"], "binary", value["target"])
    complete = attach_runtime_binary_identity(
        repository_root, revision, instance, value, contract_projection)
    verify_runtime_binary_plan(
        repository_root, revision, complete, verified_contract_manifest,
        expected_target=value["target"], expected_runtime_version=runtime_version,
        expected_flags_digest=value["inputs"].get("flagsDigest"))
    return complete


def archive_spec(plan: dict[str, Any], *, repository_root: Path, revision: str) -> dict[str, str]:
    """Return the elected Git-pinned download identity, not product admission."""
    value = _native_plan(plan)
    if value["phase"] != "binary":
        raise ValueError("Pinned app-server capture requires a native binary phase")
    if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
        raise ValueError("Pinned archive authority requires an exact Git object ID")
    inputs = validate_receipt_inputs(value["inputs"])
    if compute_build_key(product="runtime", component=value["component"], phase="binary",
                         target=value["target"], inputs=inputs) != value["buildKey"]:
        raise ValueError("Pinned archive plan build key differs from its canonical inputs")
    manifest_bytes = git_regular_blob_bytes(repository_root, revision, _DISTRIBUTION_MANIFEST,
                                            max_bytes=1024 * 1024)
    expected_record = {"relativePath": _DISTRIBUTION_MANIFEST, "bytes": len(manifest_bytes),
                       "sha256": sha256_bytes(manifest_bytes)}
    if expected_record not in inputs["inventory"]:
        raise ValueError("Pinned distribution manifest differs from the elected binary inputs")
    with tempfile.TemporaryDirectory(prefix="runtime-pinned-archive-") as temporary:
        private = Path(temporary).resolve()
        manifest_path = private / "distribution-manifest.json"
        manifest_path.write_bytes(manifest_bytes)
        manifest = read_distribution_manifest(manifest_path)
        selected = next(record for record in manifest.distributions
                        if PRODUCT_RUNTIME_TARGETS[record.target] == value["target"])
        if selected.classifier != f"app-server-{value['target']}":
            raise ValueError("Pinned app-server classifier differs from the selected native target")
        require_semver(manifest.version, "Pinned upstream release version")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", selected.asset) is None:
            raise ValueError("Pinned archive asset must be a safe URL path segment")
        return {"asset": selected.asset,
                "url": f"https://github.com/openai/codex/releases/download/{manifest.release_tag}/{selected.asset}",
                "sha256": f"sha256:{selected.archive_sha256}"}


def capture_archive(
    plan: dict[str, Any], *, repository_root: Path, revision: str,
    source: Path, destination: Path,
) -> Path:
    """Capture Git-pinned bytes without download, unpacking or product admission."""
    spec = archive_spec(plan, repository_root=repository_root, revision=revision)
    source, destination = Path(source), Path(destination)
    _path(source, "Pinned archive source")
    _path(destination, "Pinned archive destination")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Pinned archive destination must not exist")
    for parent in destination.parents:
        if parent.exists() or parent.is_symlink():
            require_regular_directory(parent, "Pinned archive destination ancestor")
    for left, right in ((source, destination), (source.resolve(strict=True), destination.resolve(strict=False))):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("Pinned archive capture overlaps its original input")
    with tempfile.TemporaryDirectory(prefix="runtime-pinned-archive-") as temporary:
        private = Path(temporary).resolve()
        contents = read_regular_file_bytes(source, max_bytes=_PINNED_ARCHIVE_LIMIT, reject_symlink_parents=True)
        if not contents or sha256_bytes(contents) != spec["sha256"]:
            raise ValueError("Pinned app-server archive SHA-256 mismatch")
        staged = private / "archive"
        staged.mkdir()
        (staged / spec["asset"]).write_bytes(contents)
        if read_regular_file_bytes(source, max_bytes=_PINNED_ARCHIVE_LIMIT, reject_symlink_parents=True) != contents:
            raise ValueError("Pinned app-server archive changed during capture")
        publish_regular_tree(staged, destination)
    return destination


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision only Git-pinned native Runtime upstream bytes")
    parser.add_argument("command", choices=("archive-spec", "capture-archive", "verify-archive"))
    parser.add_argument("--phase-plan", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args(argv)
    _path(args.phase_plan, "Native Runtime phase plan")
    plan = load_canonical_json_bytes(read_regular_file_bytes(
        args.phase_plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    spec = archive_spec(plan, repository_root=args.repository_root, revision=args.revision)
    directory = args.repository_root.resolve() / "build/runtime-upstream" / spec["sha256"].removeprefix("sha256:")
    archive = directory / spec["asset"]
    if any(character in str(directory) for character in "\r\n"):
        raise ValueError("Archive cache path cannot contain output delimiters")
    for parent in (directory, *directory.parents):
        if parent.exists() or parent.is_symlink():
            require_regular_directory(parent, "Pinned archive cache ancestor")
    if args.command == "archive-spec":
        if directory.exists() or directory.is_symlink():
            raise ValueError("Archive setup must not overwrite an existing cache directory")
        if args.github_output is not None:
            with args.github_output.open("a", encoding="utf-8") as stream:
                for key, value in {**spec, "directory": str(directory), "archive": str(archive)}.items():
                    stream.write(f"{key}={value}\n")
        sys.stdout.buffer.write(canonical_json_bytes(spec))
    elif args.command == "capture-archive":
        if args.source is None:
            parser.error("capture-archive requires --source")
        capture_archive(plan, repository_root=args.repository_root, revision=args.revision,
                        source=args.source, destination=directory)
    else:
        contents = read_regular_file_bytes(archive, max_bytes=_PINNED_ARCHIVE_LIMIT, reject_symlink_parents=True)
        if not contents or sha256_bytes(contents) != spec["sha256"]:
            raise ValueError("Pinned app-server archive SHA-256 mismatch")
        inventory = regular_file_inventory(directory)
        if len(inventory) != 1 or inventory[0]["relativePath"] != spec["asset"]:
            raise ValueError("Pinned archive cache must contain exactly the selected asset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
