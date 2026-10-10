"""Replay original native SDK metadata through the sole planner and full gate.

This establishes original Git/key/content binding, not observed CI/host provenance
or release authority. No serialized caller projection can replace a verified one.
"""

from pathlib import Path
import subprocess
import tempfile

from .inventory import (
    git_product_versions, git_regular_blob_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    run_git, snapshot_regular_tree,
)
from .plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from .receipt import validate_phase_receipt
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from .sdk_native_metadata import _inventory, verify_sdk_native_metadata_content
from .sdk_package import _require_capability_output_separate
from .sdk_validation import VerifiedSdkValidationProjection
from .selection import phase_git_inventory


_LIMIT = 16 * 1024 * 1024


def verify_sdk_native_metadata_admission(
    *, repository: Path, component: str, metadata_stage: Path, metadata_receipt: Path,
    package_stage: Path, package_receipt: Path, compatibility_request: Path,
    runtime_stages: Path, staged_sdks: Path, validation_stages: Path, validation_receipts: Path,
    sdk_validation_projections: tuple[VerifiedSdkValidationProjection, ...],
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict, bytes]:
    """Return the original receipt only after exact source, plan and content replay.

    Projections are the existing opaque per-host results already required by
    metadata planning. Their receipt/package binding is checked by plan_phase;
    this entry never constructs a projection from the metadata JSON itself.
    """
    if component not in NATIVE_BINDINGS:
        raise ValueError("Native SDK metadata admission requires an exact language")
    repository = Path(repository)
    trees = {"metadata_stage": Path(metadata_stage), "package_stage": Path(package_stage),
             "runtime_stages": Path(runtime_stages), "staged_sdks": Path(staged_sdks),
             "validation_stages": Path(validation_stages), "validation_receipts": Path(validation_receipts)}
    before = {name: _inventory(path) for name, path in trees.items()}
    paths = {"metadata_receipt": Path(metadata_receipt), "package_receipt": Path(package_receipt)}
    raw = {name: read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
           for name, path in paths.items()}
    metadata = validate_phase_receipt(load_canonical_json_bytes(raw["metadata_receipt"]))
    instance = PhaseInstanceId("sdk", component, "metadata", "desktop")
    if tuple(metadata[field] for field in ("product", "component", "phase", "target")) != (
            instance.product, instance.component, instance.phase, instance.target):
        raise ValueError("Native SDK metadata receipt differs from the requested identity")
    commit, tree = metadata["producer"]["commit"], metadata["producer"]["tree"]
    try:
        actual_commit = run_git(repository, "rev-parse", f"{commit}^{{commit}}").strip()
        actual_tree = run_git(repository, "rev-parse", f"{commit}^{{tree}}").strip()
    except subprocess.CalledProcessError as error:
        raise ValueError("Native SDK metadata original source commit is unavailable") from error
    if actual_commit != commit or actual_tree != tree:
        raise ValueError("Native SDK metadata original commit/tree differs from Git history")
    if git_regular_blob_bytes(repository, commit, "gradle/release/versions/sdk.txt", max_bytes=256) != \
            (metadata["productVersion"] + "\n").encode("utf-8"):
        raise ValueError("Native SDK metadata version differs from its original source version")
    versions = git_product_versions(repository, commit)
    with tempfile.TemporaryDirectory(prefix="sdk-metadata-admission-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [repository, *trees.values(), *paths.values(),
            Path(compatibility_request), Path(tooling_evidence), Path(tooling_public_key), Path(java_executable),
            *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)])
        captured = {}
        for name, source in trees.items():
            destination = private / name
            snapshot_regular_tree(source, destination)
            if _inventory(destination) != before[name]:
                raise ValueError("Native SDK metadata inputs changed during admission capture")
            captured[name] = destination
        for name, contents in raw.items():
            captured[name] = private / f"{name}.json"
            captured[name].write_bytes(contents)
        upstream = [validate_phase_receipt(load_canonical_json_bytes(raw["package_receipt"]))]
        for target in sorted(NATIVE_TARGETS):
            upstream.append(validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
                captured["validation_receipts"] / f"{target}.json", max_bytes=_LIMIT,
                reject_symlink_parents=True))))
        planned = plan_phase(instance, inventory=phase_git_inventory(repository, commit, instance),
            versions=versions, upstream_receipts=upstream,
            toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
            flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
            sdk_validation_projections=sdk_validation_projections)
        if metadata["inputs"] != planned["inputs"] or metadata["buildKey"] != planned["buildKey"]:
            raise ValueError("Native SDK metadata inputs/build key differ from its original authenticated plan")
        verified, verified_bytes = verify_sdk_native_metadata_content(
            repository=repository, component=component, **captured,
            compatibility_request=compatibility_request, tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)
        if verified_bytes != raw["metadata_receipt"] or verified != metadata:
            raise ValueError("Native SDK metadata full gate returned a different original receipt")
        for name, source in trees.items():
            if _inventory(source) != before[name] or _inventory(captured[name]) != before[name]:
                raise ValueError("Original or captured native SDK metadata changed during admission")
        for name, source in paths.items():
            if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw[name]
                   for path in (source, captured[name])):
                raise ValueError("Original or captured native SDK metadata receipt changed during admission")
    return metadata, raw["metadata_receipt"]
