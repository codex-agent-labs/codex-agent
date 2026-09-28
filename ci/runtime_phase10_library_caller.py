"""Issue external direct-library trust from the signed original Runtime closure.

This is a local protected-caller seam. It never compiles or repacks reusable
Contract, Runtime variant, or aggregate payloads.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from products.inventory import (
    public_key_fingerprint, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_sha256, sha256_bytes, snapshot_regular_tree,
    write_canonical_json,
)
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_protected_runtime import _original_carrier
from products.sdk_runtime_root import (
    NAMESPACE, PRODUCT_PRINCIPAL, _trusted_ssh_keygen, _verify_sshsig,
    issue_root_delegation,
)
from products.signatures import load_keyring, require_active_release_key


_OBSERVATION_TOKENS = frozenset({
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
})


def produce_authenticated_runtime_libraries(
    protected_output: Path,
    destination: Path,
    *,
    expected_metadata_receipt_sha256: str,
    expected_build_key: str,
    keyring: Path,
    keys_directory: Path,
    root_public_key: Path,
    expected_root_fingerprint: str,
    root_private_key: Path,
    release_private_key: Path,
) -> dict:
    """Sign five exact library claims only inside the full signed handoff gate."""
    if _OBSERVATION_TOKENS & set(os.environ):
        raise ValueError("Runtime library signer must not receive an observation token")
    protected_output, destination = Path(protected_output), Path(destination)
    expected_metadata_receipt_sha256 = require_sha256(
        expected_metadata_receipt_sha256, "Original Runtime metadata receipt",
    )
    expected_build_key = require_sha256(expected_build_key, "Original Runtime aggregate build key")
    expected_root_fingerprint = require_sha256(expected_root_fingerprint, "SDK-pinned root fingerprint")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime library authorization destination already exists")
    resolved_output = destination.resolve(strict=False)
    resolved_original = protected_output.resolve(strict=True)
    for source in (protected_output, keyring, keys_directory, root_public_key):
        resolved = Path(source).resolve(strict=True)
        if resolved_output == resolved or resolved_output in resolved.parents or resolved in resolved_output.parents:
            raise ValueError("Runtime library authorization output overlaps an input")
        if source != protected_output and (resolved == resolved_original
                                           or resolved in resolved_original.parents
                                           or resolved_original in resolved.parents):
            raise ValueError("Runtime library authorization policy must be external to transported output")
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True)
    if public_key_fingerprint(root_bytes) != expected_root_fingerprint:
        raise ValueError("SDK-pinned Runtime root fingerprint differs from caller pin")
    before = regular_file_inventory(protected_output, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="rt-p10-library-caller-") as temporary:
        private = Path(temporary).resolve()
        pinned_root = private / "sdk-runtime-root.pub"
        pinned_root.write_bytes(root_bytes)
        captured = private / "protected-output"
        snapshot_regular_tree(protected_output, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Runtime protected output changed during capture")
        carrier = _original_carrier(captured, expected_metadata_receipt_sha256, expected_build_key)
        output = private / "libraries"
        with verified_runtime_aggregate_handoff(
            carrier, keyring=keyring, keys_directory=keys_directory,
        ) as verified:
            captured_keyring = verified["indexInputs"]["keyring"]
            captured_keys = verified["indexInputs"]["keys_directory"]
            policy = load_keyring(captured_keyring, captured_keys)
            active, public_key = require_active_release_key(policy, captured_keys)
            if expected_root_fingerprint == active["fingerprint"]:
                raise ValueError("SDK Runtime root and release signer must be separate keys")
            signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
            signing.update(active)
            libraries = verified_runtime_libraries(verified, signing)
            root_secret = Path(root_private_key).resolve(strict=True)
            release_secret = Path(release_private_key).resolve(strict=True)
            if root_secret == release_secret:
                raise ValueError("SDK Runtime root and release signer must be separate keys")
            for secret in (root_secret, release_secret):
                if (resolved_output == secret or resolved_output in secret.parents
                        or secret in resolved_output.parents or secret == resolved_original
                        or secret in resolved_original.parents or resolved_original in secret.parents):
                    raise ValueError("Runtime library authorization output/transport overlaps a signer key")
            delegation = private / "delegation"
            issue_root_delegation(captured_keyring, captured_keys, pinned_root, root_private_key, delegation)
            for target, item in libraries.items():
                library = output / target / item["fileName"]
                library.parent.mkdir(parents=True)
                library.write_bytes(item["library"])
                if sha256_bytes(library.read_bytes()) != item["claim"]["runtimeLibrarySha256"]:
                    raise ValueError(f"Runtime library bytes changed during release staging: {target}")
                evidence = library.with_name(library.name + ".evidence")
                snapshot_regular_tree(delegation, evidence)
                claim = evidence / "runtime-library-authorization.json"
                write_canonical_json(claim, item["claim"])
                try:
                    subprocess.run(
                        [_trusted_ssh_keygen(), "-Y", "sign", "-f", str(release_private_key),
                         "-n", NAMESPACE, str(claim)],
                        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                    )
                except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                    raise ValueError("Runtime direct-library authorization signing failed") from error
                generated = Path(f"{claim}.sig")
                signature = evidence / "runtime-library-authorization.sig"
                signature_bytes = read_regular_file_bytes(generated, max_bytes=1024 * 1024,
                                                          reject_symlink_parents=True)
                _verify_sshsig(claim.read_bytes(), signature_bytes,
                               read_regular_file_bytes(public_key, max_bytes=4096, reject_symlink_parents=True),
                               namespace=NAMESPACE, principal=PRODUCT_PRINCIPAL)
                generated.replace(signature)
        if (regular_file_inventory(protected_output, allow_empty=True) != before
                or regular_file_inventory(captured, allow_empty=True) != before
                or read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True) != root_bytes):
            raise ValueError("Runtime protected original changed during library authorization")
        inventory = regular_file_inventory(output)
        publish_regular_tree(output, destination, expected_inventory=inventory)
        if regular_file_inventory(destination) != inventory or \
                regular_file_inventory(protected_output, allow_empty=True) != before:
            raise ValueError("Runtime library authorization changed during publication")
        return {"files": inventory, "rootFingerprint": expected_root_fingerprint,
                "runtimeVersion": verified["manifest"]["runtimeVersion"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue external Runtime library evidence from a signed original")
    for name in ("protected-output", "destination", "expected-metadata-receipt-sha256",
                 "expected-build-key", "keyring", "keys-directory", "root-public-key",
                 "expected-root-fingerprint", "root-private-key", "release-private-key"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    result = produce_authenticated_runtime_libraries(
        Path(args.protected_output), Path(args.destination),
        expected_metadata_receipt_sha256=args.expected_metadata_receipt_sha256,
        expected_build_key=args.expected_build_key,
        keyring=Path(args.keyring), keys_directory=Path(args.keys_directory),
        root_public_key=Path(args.root_public_key), expected_root_fingerprint=args.expected_root_fingerprint,
        root_private_key=Path(args.root_private_key), release_private_key=Path(args.release_private_key),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
