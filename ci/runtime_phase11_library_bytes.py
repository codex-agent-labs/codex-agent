"""Offline verification and byte-exact forwarding of Runtime library evidence.

All pins come from an independently approved S1048 selection. This helper does
not observe a hosted run, authorize a candidate, or sign anything.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    canonical_json_bytes, public_key_fingerprint, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_sha256,
    sha256_bytes, snapshot_regular_tree,
)
from products.registry import NATIVE_TARGETS
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_protected_runtime import _original_carrier
from products.sdk_runtime_root import NAMESPACE, PRODUCT_PRINCIPAL, _verify_sshsig
from products.signatures import load_keyring, require_active_release_key
from products.signing_isolation import require_no_signing_secret
from runtime_phase10_library_caller import (
    _OBSERVATION_TOKENS, _PRODUCT_SECRETS, _ROOT_SECRET,
    _verify_pinned_delegation,
)


def _inventory_digest(directory: Path, *, allow_empty: bool = False) -> str:
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(directory, allow_empty=allow_empty)))


def _require_no_authority() -> None:
    require_no_signing_secret(os.environ)
    if (_OBSERVATION_TOKENS | _PRODUCT_SECRETS | {_ROOT_SECRET}) & set(os.environ):
        raise ValueError("Runtime Phase-11 library forwarder must not receive token or signing secret")


def forward_verified_runtime_library_bytes(
    protected_output: Path, root_delegation: Path, authorizations: Path,
    destination: Path, *, keyring: Path, keys_directory: Path, root_public_key: Path,
    expected_protected_inventory_sha256: str,
    expected_delegation_inventory_sha256: str,
    expected_authorizations_inventory_sha256: str,
    expected_keyring_sha256: str,
    expected_keys_inventory_sha256: str,
    expected_root_public_key_sha256: str,
    expected_metadata_receipt_sha256: str,
    expected_build_key: str,
) -> dict:
    """Verify exact five claims against signed originals; forward input bytes only."""
    _require_no_authority()
    protected_output, root_delegation, authorizations, destination, keyring, keys_directory, root_public_key = map(
        Path, (protected_output, root_delegation, authorizations, destination,
               keyring, keys_directory, root_public_key),
    )
    sources = (protected_output, root_delegation, authorizations, keyring,
               keys_directory, root_public_key)
    pins = {
        "protected output": (protected_output, expected_protected_inventory_sha256, True),
        "root delegation": (root_delegation, expected_delegation_inventory_sha256, False),
        "library authorizations": (authorizations, expected_authorizations_inventory_sha256, False),
        "release keys": (keys_directory, expected_keys_inventory_sha256, False),
    }
    for label, (_, digest, _) in pins.items():
        require_sha256(digest, f"S1048 {label} inventory")
    for label, digest in (
        ("keyring", expected_keyring_sha256),
        ("root public key", expected_root_public_key_sha256),
        ("metadata receipt", expected_metadata_receipt_sha256),
        ("aggregate build key", expected_build_key),
    ):
        require_sha256(digest, f"S1048 {label}")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime library destination already exists")
    output = destination.resolve(strict=False)
    resolved = [source.resolve(strict=True) for source in sources]
    if any(output == path or output in path.parents or path in output.parents for path in resolved):
        raise ValueError("Runtime library destination overlaps an input")
    if len(set(resolved)) != len(resolved):
        raise ValueError("Runtime library inputs must be distinct")
    for label, (directory, digest, allow_empty) in pins.items():
        if _inventory_digest(directory, allow_empty=allow_empty) != digest:
            raise ValueError(f"Runtime {label} differs from independent S1048 pin")
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096,
                                         reject_symlink_parents=True)
    if (sha256_bytes(keyring_bytes) != expected_keyring_sha256
            or sha256_bytes(root_bytes) != expected_root_public_key_sha256):
        raise ValueError("Runtime release keyring or root differs from independent S1048 pin")

    with tempfile.TemporaryDirectory(prefix="runtime-library-phase11-") as temporary:
        private = Path(temporary).resolve()
        original = private / "original"
        delegation = private / "delegation"
        libraries = private / "libraries"
        policy = private / "policy"
        snapshot_regular_tree(protected_output, original, allow_empty=True)
        snapshot_regular_tree(root_delegation, delegation)
        snapshot_regular_tree(authorizations, libraries)
        snapshot_regular_tree(keys_directory, policy / "keys")
        (policy / "release-keyring.json").write_bytes(keyring_bytes)
        (policy / "sdk-runtime-root.pub").write_bytes(root_bytes)
        for label, (directory, digest, allow_empty) in pins.items():
            captured = {"protected output": original, "root delegation": delegation,
                        "library authorizations": libraries, "release keys": policy / "keys"}[label]
            if _inventory_digest(captured, allow_empty=allow_empty) != digest:
                raise ValueError(f"Runtime {label} changed during capture")
        delegated_keyring, delegated_files = _verify_pinned_delegation(
            delegation, root_bytes=root_bytes,
            expected_inventory_sha256=expected_delegation_inventory_sha256)
        if delegated_keyring != keyring_bytes:
            raise ValueError("Runtime root delegation differs from selected release keyring")
        release_policy = load_keyring(policy / "release-keyring.json", policy / "keys")
        active, public_key = require_active_release_key(release_policy, policy / "keys")
        if public_key_fingerprint(root_bytes) == active["fingerprint"]:
            raise ValueError("Runtime root and release signer must be separate keys")
        records = ([active] if active is not None else []) + release_policy["retiredKeys"]
        expected_delegated_keys = {f"keys/{row['keyId']}.pub" for row in records}
        if {row["relativePath"] for row in delegated_files if row["relativePath"].startswith("keys/")} != expected_delegated_keys:
            raise ValueError("Runtime delegation release key set differs from selected policy")
        for row in records:
            name = f"{row['keyId']}.pub"
            if read_regular_file_bytes(delegation / "keys" / name) != read_regular_file_bytes(policy / "keys" / name):
                raise ValueError("Runtime delegation public key differs from selected policy")
        signing = {name: release_policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        release_public = read_regular_file_bytes(public_key, max_bytes=4096,
                                                 reject_symlink_parents=True)
        carrier = _original_carrier(original, expected_metadata_receipt_sha256, expected_build_key)
        with verified_runtime_aggregate_handoff(
            carrier, keyring=policy / "release-keyring.json", keys_directory=policy / "keys",
        ) as verified:
            projected = verified_runtime_libraries(verified, signing)
        if set(projected) != set(NATIVE_TARGETS):
            raise ValueError("Runtime library projection does not contain exactly five targets")
        expected_paths = set()
        for target in NATIVE_TARGETS:
            item = projected[target]
            library_path = libraries / target / item["fileName"]
            evidence = library_path.with_name(library_path.name + ".evidence")
            if read_regular_file_bytes(library_path, reject_symlink_parents=True) != item["library"]:
                raise ValueError(f"Runtime library differs from signed aggregate: {target}")
            expected_claim = canonical_json_bytes(item["claim"])
            claim = read_regular_file_bytes(evidence / "runtime-library-authorization.json",
                                            max_bytes=1024 * 1024, reject_symlink_parents=True)
            if claim != expected_claim:
                raise ValueError(f"Runtime claim differs from signed aggregate: {target}")
            signature = read_regular_file_bytes(evidence / "runtime-library-authorization.sig",
                                                max_bytes=1024 * 1024, reject_symlink_parents=True)
            _verify_sshsig(claim, signature, release_public,
                           namespace=NAMESPACE, principal=PRODUCT_PRINCIPAL)
            for row in delegated_files:
                relative = row["relativePath"]
                if read_regular_file_bytes(evidence / relative, reject_symlink_parents=True) != \
                        read_regular_file_bytes(delegation / relative, reject_symlink_parents=True):
                    raise ValueError(f"Runtime delegation differs inside claim evidence: {target}")
            prefix = f"{target}/{item['fileName']}"
            expected_paths.add(prefix)
            expected_paths.update({f"{prefix}.evidence/{row['relativePath']}" for row in delegated_files})
            expected_paths.update({f"{prefix}.evidence/runtime-library-authorization.json",
                                   f"{prefix}.evidence/runtime-library-authorization.sig"})
        if {row["relativePath"] for row in regular_file_inventory(libraries)} != expected_paths:
            raise ValueError("Runtime library evidence has extra or missing files")
        for label, (directory, digest, allow_empty) in pins.items():
            if _inventory_digest(directory, allow_empty=allow_empty) != digest:
                raise ValueError(f"Runtime {label} changed during verification")
        if (read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                    reject_symlink_parents=True) != keyring_bytes
                or read_regular_file_bytes(root_public_key, max_bytes=4096,
                                           reject_symlink_parents=True) != root_bytes):
            raise ValueError("Runtime verifier policy changed during verification")
        output_stage = private / "forwarded"
        snapshot_regular_tree(delegation, output_stage / "root-delegation")
        snapshot_regular_tree(libraries, output_stage / "library-authorizations")
        (output_stage / "sdk-runtime-root.pub").write_bytes(root_bytes)
        if (_inventory_digest(output_stage / "root-delegation") !=
                expected_delegation_inventory_sha256
                or _inventory_digest(output_stage / "library-authorizations") !=
                expected_authorizations_inventory_sha256
                or read_regular_file_bytes(output_stage / "sdk-runtime-root.pub",
                                           max_bytes=4096, reject_symlink_parents=True) != root_bytes):
            raise ValueError("Forwarded Runtime library evidence differs from independent S1048 pins")
        inventory = regular_file_inventory(output_stage)
        _require_no_authority()
        publish_regular_tree(output_stage, destination, expected_inventory=inventory)
        if regular_file_inventory(destination) != inventory:
            raise ValueError("Runtime library forwarding changed published bytes")
        return {"targets": list(NATIVE_TARGETS), "files": inventory,
                "delegationInventorySha256": expected_delegation_inventory_sha256,
                "authorizationsInventorySha256": expected_authorizations_inventory_sha256}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("protected-output", "root-delegation", "authorizations", "destination",
                 "keyring", "keys-directory", "root-public-key"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("expected-protected-inventory-sha256", "expected-delegation-inventory-sha256",
                 "expected-authorizations-inventory-sha256", "expected-keyring-sha256",
                 "expected-keys-inventory-sha256", "expected-root-public-key-sha256",
                 "expected-metadata-receipt-sha256", "expected-build-key"):
        parser.add_argument(f"--{name}", required=True)
    result = forward_verified_runtime_library_bytes(**vars(parser.parse_args(argv)))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
