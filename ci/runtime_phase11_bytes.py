"""Offline Runtime candidate handoff: verify and forward Phase-10 bytes unchanged.

The caller must obtain every expected digest and Git identity from the accepted
S1048 record, independently of the transported output. This helper neither
establishes official upload/landed-tree authority nor publishes a release.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_semver, require_sha256,
    sha256_bytes, snapshot_regular_tree,
)
from products.registry import PhaseInstanceId
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_phase10_maven import verify_runtime_phase10_maven
from products.sdk_protected_runtime import _original_carrier


_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def _tree_digest(directory: Path, *, allow_empty: bool = False) -> str:
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(directory, allow_empty=allow_empty)))


def _landed_tree(repository: Path) -> str:
    root = repository.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Runtime candidate checkout must be a directory")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD^{tree}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError("Runtime candidate checkout has no landed Git tree")
    lines = result.stdout.splitlines()
    if len(lines) != 2 or Path(lines[0]).resolve(strict=True) != root or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", lines[1],
    ):
        raise ValueError("Runtime candidate checkout is not the exact Git root")
    return lines[1]


def forward_verified_runtime_phase10_bytes(
    protected_output: Path, maven_sidecars: Path, destination: Path, *, landed_repository: Path,
    expected_protected_inventory_sha256: str, expected_sidecar_inventory_sha256: str,
    expected_metadata_receipt_sha256: str, expected_build_key: str,
    expected_runtime_version: str, expected_manifest_sha256: str,
    expected_source_commit: str, expected_source_tree: str, expected_validation_tree: str,
    expected_workflow_sha: str,
    keyring: Path, expected_keyring_sha256: str, keys_directory: Path,
    expected_keys_inventory_sha256: str, pgp_public_key: Path,
    expected_pgp_key_sha256: str,
) -> dict:
    """Copy only a fully verified, independently pinned Runtime byte set.

    The result is an offline candidate input, not a publication or a new
    attestation. Output paths preserve every original relative file and byte.
    """
    protected_output, maven_sidecars, destination = map(
        Path, (protected_output, maven_sidecars, destination),
    )
    keyring, keys_directory, pgp_public_key = map(Path, (keyring, keys_directory, pgp_public_key))
    pins = {
        "protected output": (expected_protected_inventory_sha256, protected_output, True),
        "Maven sidecars": (expected_sidecar_inventory_sha256, maven_sidecars, False),
        "product keys": (expected_keys_inventory_sha256, keys_directory, False),
    }
    for label, (digest, _, _) in pins.items():
        require_sha256(digest, f"Phase-10 {label} inventory")
    for label, digest in (("metadata receipt", expected_metadata_receipt_sha256),
                          ("aggregate build key", expected_build_key),
                          ("aggregate manifest", expected_manifest_sha256),
                          ("product keyring", expected_keyring_sha256),
                          ("PGP public key", expected_pgp_key_sha256)):
        require_sha256(digest, f"Phase-10 {label}")
    require_semver(expected_runtime_version, "Phase-10 Runtime version")
    for label, revision in (("source commit", expected_source_commit),
                            ("source tree", expected_source_tree),
                            ("validation tree", expected_validation_tree),
                            ("workflow SHA", expected_workflow_sha)):
        if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
            raise ValueError(f"Phase-10 {label} must be a full Git object ID")
    if _landed_tree(Path(landed_repository)) != expected_validation_tree:
        raise ValueError("Runtime candidate landed tree differs from Phase-10 validation")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime candidate destination already exists")
    output = destination.resolve(strict=False)
    inputs = (protected_output, maven_sidecars, keyring, keys_directory, pgp_public_key)
    for source in inputs:
        resolved = source.resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Runtime candidate output overlaps an original input")
    if maven_sidecars.resolve(strict=True) == protected_output.resolve(strict=True) or \
            maven_sidecars.resolve(strict=True) in protected_output.resolve(strict=True).parents or \
            protected_output.resolve(strict=True) in maven_sidecars.resolve(strict=True).parents:
        raise ValueError("Runtime Phase-10 sidecars must be external to the protected output")
    for source in (keyring, keys_directory, pgp_public_key):
        resolved = source.resolve(strict=True)
        for transported in (protected_output, maven_sidecars):
            root = transported.resolve(strict=True)
            if resolved == root or resolved in root.parents or root in resolved.parents:
                raise ValueError("Runtime verifier policy must be external to transported output")

    for label, (digest, path, allow_empty) in pins.items():
        if _tree_digest(path, allow_empty=allow_empty) != digest:
            raise ValueError(f"Phase-10 {label} differs from independently selected bytes")
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=64 * 1024, reject_symlink_parents=True)
    pgp_bytes = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                        reject_symlink_parents=True)
    if sha256_bytes(keyring_bytes) != expected_keyring_sha256 or \
            sha256_bytes(pgp_bytes) != expected_pgp_key_sha256:
        raise ValueError("Phase-10 verifier key differs from independently selected bytes")

    with tempfile.TemporaryDirectory(prefix="rt-phase11-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        snapshot_regular_tree(protected_output, prepared / "runtime-release", allow_empty=True)
        snapshot_regular_tree(maven_sidecars, prepared / "maven-sidecars")
        snapshot_regular_tree(keys_directory, prepared / "product-policy/keys")
        (prepared / "product-policy/product-signing-keys.json").write_bytes(keyring_bytes)
        (prepared / "pgp-public-key.asc").write_bytes(pgp_bytes)
        for label, (digest, _, allow_empty) in pins.items():
            candidate_path = {
                "protected output": prepared / "runtime-release",
                "Maven sidecars": prepared / "maven-sidecars",
                "product keys": prepared / "product-policy/keys",
            }[label]
            if _tree_digest(candidate_path, allow_empty=allow_empty) != digest:
                raise ValueError(f"Phase-10 {label} changed during candidate capture")
        prepared_inventory = regular_file_inventory(prepared)
        copied = prepared / "runtime-release"
        caller = load_canonical_json_bytes(read_regular_file_bytes(
            copied / "caller.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        ))
        if type(caller) is not dict or any(caller.get(field) != expected for field, expected in (
            ("trustedSourceCommit", expected_source_commit),
            ("trustedSourceTree", expected_source_tree),
            ("trustedWorkflowSha", expected_workflow_sha),
        )):
            raise ValueError("Runtime Phase-10 caller provenance differs from selected context")
        carrier = _original_carrier(copied, expected_metadata_receipt_sha256, expected_build_key)
        with verified_runtime_aggregate_handoff(
            carrier, keyring=prepared / "product-policy/product-signing-keys.json",
            keys_directory=prepared / "product-policy/keys",
        ) as verified:
            original = verified["originalPhases"][_METADATA]
            manifest = Path(verified["indexInputs"]["manifest"])
            payload = Path(original["stage"]) / "outputs"
            if manifest.parent != payload:
                raise ValueError("Runtime Maven payload is not the original aggregate stage")
            maven = verify_runtime_phase10_maven(
                payload, manifest, prepared / "maven-sidecars", prepared / "pgp-public-key.asc",
                expected_pgp_key_sha256,
            )
            if (maven["runtimeVersion"] != expected_runtime_version
                    or maven["manifestSha256"] != expected_manifest_sha256):
                raise ValueError("Runtime Phase-10 release identity differs from selected manifest")
        for label, (digest, path, allow_empty) in pins.items():
            if _tree_digest(path, allow_empty=allow_empty) != digest:
                raise ValueError(f"Phase-10 {label} changed during candidate verification")
        if read_regular_file_bytes(keyring, max_bytes=64 * 1024, reject_symlink_parents=True) != keyring_bytes or \
                read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                        reject_symlink_parents=True) != pgp_bytes:
            raise ValueError("Phase-10 verifier key changed during candidate verification")
        if (regular_file_inventory(prepared) != prepared_inventory
                or read_regular_file_bytes(prepared / "product-policy/product-signing-keys.json",
                                           max_bytes=64 * 1024, reject_symlink_parents=True) != keyring_bytes
                or read_regular_file_bytes(prepared / "pgp-public-key.asc", max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != pgp_bytes):
            raise ValueError("Verified Runtime candidate bytes changed before publication")
        if _landed_tree(Path(landed_repository)) != expected_validation_tree:
            raise ValueError("Runtime candidate landed tree changed during verification")
        publish_regular_tree(prepared, destination, expected_inventory=prepared_inventory)
        return {"product": "runtime", "runtimeVersion": maven["runtimeVersion"],
                "manifestSha256": maven["manifestSha256"],
                "protectedInventorySha256": expected_protected_inventory_sha256,
                "sidecarInventorySha256": expected_sidecar_inventory_sha256,
                "candidateInventory": prepared_inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in (
        "protected-output", "maven-sidecars", "destination", "landed-repository",
        "keyring", "keys-directory", "pgp-public-key",
    ):
        parser.add_argument(f"--{option}", type=Path, required=True)
    for option in (
        "expected-protected-inventory-sha256", "expected-sidecar-inventory-sha256",
        "expected-metadata-receipt-sha256", "expected-build-key",
        "expected-runtime-version", "expected-manifest-sha256",
        "expected-source-commit", "expected-source-tree", "expected-validation-tree",
        "expected-workflow-sha", "expected-keyring-sha256",
        "expected-keys-inventory-sha256", "expected-pgp-key-sha256",
    ):
        parser.add_argument(f"--{option}", required=True)
    result = forward_verified_runtime_phase10_bytes(**vars(parser.parse_args(argv)))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
