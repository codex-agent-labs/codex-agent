"""Offline Contract candidate input: verify and forward exact Phase-10 bytes.

All expected identities and digests must come from independently accepted S1048
evidence. This helper does not establish official upload or landed-tree authority.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.contract_phase10_inventory import capture_contract_phase10_inventory
from products.contract_phase10_maven import verify_contract_phase10_maven
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_semver, require_sha256, sha256_bytes, snapshot_regular_tree,
)


_CONTROL = {"schemaVersion", "releaseCaller", "releaseFiles", "contractInventory", "mavenSidecars"}


def _inventory_digest(directory: Path) -> str:
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(directory)))


def _landed_tree(repository: Path) -> str:
    root = repository.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Contract candidate checkout must be a directory")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD^{tree}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError("Contract candidate checkout has no landed Git tree")
    lines = result.stdout.splitlines()
    if len(lines) != 2 or Path(lines[0]).resolve(strict=True) != root or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", lines[1],
    ):
        raise ValueError("Contract candidate checkout is not the exact Git root")
    return lines[1]


def forward_verified_contract_phase10_bytes(
    protected_output: Path, destination: Path, *, landed_repository: Path,
    expected_inventory_sha256: str, expected_contract_version: str,
    expected_payload_sha256: str, expected_metadata_build_key: str,
    expected_source_commit: str, expected_source_tree: str,
    expected_validation_tree: str,
    expected_workflow_sha: str, expected_caller_sha256: str,
    expected_keyring_sha256: str, expected_keys_inventory_sha256: str,
    expected_pgp_key_sha256: str,
) -> dict:
    """Copy a fully verified Phase-10 tree without rebuilding or re-signing it."""
    protected_output, destination = Path(protected_output), Path(destination)
    for name, digest in (
        ("output inventory", expected_inventory_sha256),
        ("Contract payload", expected_payload_sha256),
        ("metadata build key", expected_metadata_build_key),
        ("caller", expected_caller_sha256),
        ("product keyring", expected_keyring_sha256),
        ("product keys inventory", expected_keys_inventory_sha256),
        ("PGP public key", expected_pgp_key_sha256),
    ):
        require_sha256(digest, f"Contract Phase-10 {name}")
    require_semver(expected_contract_version, "Contract Phase-10 version")
    for name, value in (
        ("source commit", expected_source_commit),
        ("source tree", expected_source_tree),
        ("validation tree", expected_validation_tree),
        ("workflow SHA", expected_workflow_sha),
    ):
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
            raise ValueError(f"Contract Phase-10 {name} must be a full Git object ID")
    if _landed_tree(Path(landed_repository)) != expected_validation_tree:
        raise ValueError("Contract candidate landed tree differs from Phase-10 validation")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract candidate destination already exists")
    source = protected_output.resolve(strict=True)
    landed_root = Path(landed_repository).resolve(strict=True)
    output = destination.resolve(strict=False)
    for input_root in (source, landed_root):
        if output == input_root or output in input_root.parents or input_root in output.parents:
            raise ValueError("Contract candidate destination overlaps a verified input")
    if _inventory_digest(source) != expected_inventory_sha256:
        raise ValueError("Contract Phase-10 output differs from independently selected bytes")

    with tempfile.TemporaryDirectory(prefix="ct-phase11-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        snapshot_regular_tree(source, prepared)
        if _inventory_digest(prepared) != expected_inventory_sha256:
            raise ValueError("Contract Phase-10 output changed during candidate capture")
        release = prepared / "contract-release-evidence"
        policy = release / "caller-policy"
        handoff = release / "contract-input"
        keyring = policy / "product-signing-keys.json"
        keys = policy / "keys"
        pgp = prepared / "publication-pgp-public-key.asc"
        caller_bytes = read_regular_file_bytes(release / "caller.json", max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True)
        if sha256_bytes(caller_bytes) != expected_caller_sha256:
            raise ValueError("Contract Phase-10 caller differs from selected provenance")
        caller = load_canonical_json_bytes(caller_bytes)
        if type(caller) is not dict or any(caller.get(name) != expected for name, expected in (
            ("trustedSourceCommit", expected_source_commit),
            ("trustedSourceTree", expected_source_tree),
            ("trustedWorkflowSha", expected_workflow_sha),
        )) or type(caller.get("transportProducer")) is not dict or \
                caller["transportProducer"].get("tree") != expected_validation_tree:
            raise ValueError("Contract Phase-10 caller differs from selected source context")
        keyring_bytes = read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024,
                                                reject_symlink_parents=True)
        pgp_bytes = read_regular_file_bytes(pgp, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
        if (sha256_bytes(keyring_bytes) != expected_keyring_sha256
                or _inventory_digest(keys) != expected_keys_inventory_sha256
                or sha256_bytes(pgp_bytes) != expected_pgp_key_sha256):
            raise ValueError("Contract Phase-10 verifier keys differ from selected bytes")
        control = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            prepared / "sidecar-selection.json", max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        )), _CONTROL, "Contract Phase-10 sidecar selection")
        if (control["schemaVersion"] != 1 or control["releaseCaller"] != caller
                or control["releaseFiles"] != regular_file_inventory(release)):
            raise ValueError("Contract Phase-10 sidecar selection differs from release evidence")
        with tempfile.TemporaryDirectory(prefix="ct-phase11-verify-") as verification:
            record = capture_contract_phase10_inventory(
                handoff, keyring, keys, Path(verification).resolve(strict=True) / "contract-inventory",
            )
        if (control["contractInventory"] != record
                or record["contractVersion"] != expected_contract_version
                or record["metadataBuildKey"] != expected_metadata_build_key
                or regular_file_inventory(keys) != record["verifierKeys"]):
            raise ValueError("Contract Phase-10 inventory differs from selected release identity")
        payload = handoff / f"codex-agent-contract-{expected_contract_version}.zip"
        maven = verify_contract_phase10_maven(
            payload, prepared / "maven-sidecars", pgp, expected_pgp_key_sha256,
        )
        if (control["mavenSidecars"] != maven
                or maven["payloadSha256"] != expected_payload_sha256):
            raise ValueError("Contract Phase-10 Maven sidecars differ from selected payload")
        expected_paths = {
            "sidecar-selection.json", "publication-pgp-public-key.asc",
            *(f"contract-release-evidence/{row['relativePath']}" for row in control["releaseFiles"]),
            *(f"maven-sidecars/{row['relativePath']}" for row in maven["sidecarFiles"]),
        }
        if {row["relativePath"] for row in regular_file_inventory(prepared)} != expected_paths:
            raise ValueError("Contract Phase-10 output has unexpected candidate files")
        pinned_inventory = regular_file_inventory(prepared)
        if (_inventory_digest(source) != expected_inventory_sha256
                or sha256_bytes(canonical_json_bytes(pinned_inventory)) != expected_inventory_sha256
                or _landed_tree(Path(landed_repository)) != expected_validation_tree):
            raise ValueError("Contract Phase-10 bytes changed during candidate verification")
        publish_regular_tree(prepared, destination, expected_inventory=pinned_inventory)
        return {"product": "contract", "contractVersion": expected_contract_version,
                "payloadSha256": expected_payload_sha256,
                "metadataBuildKey": expected_metadata_build_key,
                "phase10InventorySha256": expected_inventory_sha256,
                "candidateInventory": pinned_inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("protected-output", "destination", "landed-repository"):
        parser.add_argument(f"--{option}", type=Path, required=True)
    for option in (
        "expected-inventory-sha256", "expected-contract-version",
        "expected-payload-sha256", "expected-metadata-build-key",
        "expected-source-commit", "expected-source-tree",
        "expected-validation-tree", "expected-workflow-sha",
        "expected-caller-sha256", "expected-keyring-sha256",
        "expected-keys-inventory-sha256", "expected-pgp-key-sha256",
    ):
        parser.add_argument(f"--{option}", required=True)
    result = forward_verified_contract_phase10_bytes(**vars(parser.parse_args(argv)))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
