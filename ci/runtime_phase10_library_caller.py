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
    canonical_json_bytes, load_canonical_json_bytes, public_key_fingerprint,
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_sha256, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.runtime_library_authorization import verified_runtime_libraries
from products.sdk_protected_runtime import _original_carrier
from products.sdk_runtime_root import (
    NAMESPACE, PRODUCT_PRINCIPAL, ROOT_NAMESPACE, ROOT_PRINCIPAL,
    _trusted_ssh_keygen, _verify_sshsig, issue_root_delegation,
    validate_root_delegation,
)
from products.signatures import load_keyring, require_active_release_key


_OBSERVATION_TOKENS = frozenset({
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
})
_ROOT_SECRET = "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"
_PRODUCT_SECRETS = frozenset({
    "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "SIGNING_IN_MEMORY_KEY",
    "SIGNING_IN_MEMORY_KEY_PASSWORD",
})


def _no_token() -> None:
    if _OBSERVATION_TOKENS & set(os.environ):
        raise ValueError("Runtime library signer must not receive an observation token")


def issue_authenticated_runtime_root_delegation(
    destination: Path, *, keyring: Path, keys_directory: Path,
    root_public_key: Path, expected_root_public_key_sha256: str,
    expected_keyring_sha256: str, expected_keys_inventory_sha256: str,
    root_private_key: Path,
) -> dict:
    """Root-only approval of an exact release keyring; no product key is needed."""
    _no_token()
    if _PRODUCT_SECRETS & set(os.environ):
        raise ValueError("Runtime root delegation must not receive a product signing secret")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime root delegation destination already exists")
    inputs = [Path(path).resolve(strict=True) for path in (
        keyring, keys_directory, root_public_key, root_private_key)]
    output = destination.resolve(strict=False)
    if any(output == path or output in path.parents or path in output.parents for path in inputs):
        raise ValueError("Runtime root delegation output overlaps an input")
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
    key_inventory = regular_file_inventory(keys_directory)
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096,
                                         reject_symlink_parents=True)
    if (sha256_bytes(keyring_bytes) != require_sha256(expected_keyring_sha256,
            "protected release keyring digest")
            or sha256_bytes(canonical_json_bytes(key_inventory)) != require_sha256(
                expected_keys_inventory_sha256, "protected release keys inventory")
            or sha256_bytes(root_bytes) != require_sha256(expected_root_public_key_sha256,
                "SDK-pinned root public key digest")):
        raise ValueError("Runtime root delegation inputs differ from independent pins")
    load_keyring(keyring, keys_directory)
    issue_root_delegation(keyring, keys_directory, root_public_key,
                          root_private_key, destination)
    inventory = regular_file_inventory(destination)
    if (read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
            reject_symlink_parents=True) != keyring_bytes
            or regular_file_inventory(keys_directory) != key_inventory
            or read_regular_file_bytes(root_public_key, max_bytes=4096,
                reject_symlink_parents=True) != root_bytes):
        raise ValueError("Runtime root delegation inputs changed during issuance")
    return {"files": inventory,
            "inventorySha256": sha256_bytes(canonical_json_bytes(inventory)),
            "rootPublicKeySha256": expected_root_public_key_sha256,
            "rootFingerprint": public_key_fingerprint(root_bytes)}


def _verify_pinned_delegation(directory: Path, *, root_bytes: bytes,
                              expected_inventory_sha256: str) -> tuple[bytes, list[dict]]:
    inventory = regular_file_inventory(directory)
    if sha256_bytes(canonical_json_bytes(inventory)) != require_sha256(
            expected_inventory_sha256, "protected Runtime delegation inventory"):
        raise ValueError("Runtime root delegation differs from independent inventory pin")
    keyring = directory / "release-keyring.json"
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=1024 * 1024,
                                            reject_symlink_parents=True)
    policy = load_keyring(keyring, directory / "keys")
    records = ([policy["activeKey"]] if policy["activeKey"] is not None else []) + policy["retiredKeys"]
    expected = {"release-keyring.json", "root-delegation.json", "root-delegation.sig"} | {
        f"keys/{row['keyId']}.pub" for row in records}
    if {row["relativePath"] for row in inventory} != expected:
        raise ValueError("Runtime root delegation has extra or missing files")
    manifest = read_regular_file_bytes(directory / "root-delegation.json",
                                       max_bytes=1024 * 1024, reject_symlink_parents=True)
    delegation = validate_root_delegation(load_canonical_json_bytes(manifest))
    if (delegation["rootFingerprint"] != public_key_fingerprint(root_bytes)
            or delegation["keyringSha256"] != sha256_bytes(keyring_bytes)):
        raise ValueError("Runtime root delegation differs from SDK root or release keyring")
    signature = read_regular_file_bytes(directory / "root-delegation.sig",
                                        max_bytes=1024 * 1024, reject_symlink_parents=True)
    _verify_sshsig(manifest, signature, root_bytes,
                   namespace=ROOT_NAMESPACE, principal=ROOT_PRINCIPAL)
    if regular_file_inventory(directory) != inventory:
        raise ValueError("Runtime root delegation changed during verification")
    return keyring_bytes, inventory


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
    expected_root_public_key_sha256: str,
    root_delegation: Path,
    expected_delegation_inventory_sha256: str,
    release_private_key: Path,
) -> dict:
    """Sign five claims from a pinned root delegation and signed original handoff."""
    _no_token()
    if _ROOT_SECRET in os.environ:
        raise ValueError("Runtime release signer must not receive the SDK root secret")
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
    for source in (protected_output, keyring, keys_directory, root_public_key, root_delegation):
        resolved = Path(source).resolve(strict=True)
        if resolved_output == resolved or resolved_output in resolved.parents or resolved in resolved_output.parents:
            raise ValueError("Runtime library authorization output overlaps an input")
        if source != protected_output and (resolved == resolved_original
                                           or resolved in resolved_original.parents
                                           or resolved_original in resolved.parents):
            raise ValueError("Runtime library authorization policy must be external to transported output")
    root_bytes = read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True)
    if (public_key_fingerprint(root_bytes) != expected_root_fingerprint
            or sha256_bytes(root_bytes) != require_sha256(
                expected_root_public_key_sha256, "SDK-pinned root public key digest")):
        raise ValueError("SDK-pinned Runtime root public key differs from caller pin")
    delegation_before = regular_file_inventory(root_delegation)
    if sha256_bytes(canonical_json_bytes(delegation_before)) != require_sha256(
            expected_delegation_inventory_sha256, "protected Runtime delegation inventory"):
        raise ValueError("Runtime root delegation differs from independent inventory pin")
    before = regular_file_inventory(protected_output, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="rt-p10-library-caller-") as temporary:
        private = Path(temporary).resolve()
        delegation = private / "delegation"
        snapshot_regular_tree(root_delegation, delegation)
        delegated_keyring, delegated_inventory = _verify_pinned_delegation(
            delegation, root_bytes=root_bytes,
            expected_inventory_sha256=expected_delegation_inventory_sha256)
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
            if (delegated_keyring != read_regular_file_bytes(captured_keyring,
                    max_bytes=1024 * 1024, reject_symlink_parents=True)
                    or regular_file_inventory(delegation / "keys") !=
                        regular_file_inventory(captured_keys)):
                raise ValueError("Runtime root delegation differs from original release key policy")
            if expected_root_fingerprint == active["fingerprint"]:
                raise ValueError("SDK Runtime root and release signer must be separate keys")
            signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
            signing.update(active)
            libraries = verified_runtime_libraries(verified, signing)
            release_secret = Path(release_private_key).resolve(strict=True)
            if (resolved_output == release_secret or resolved_output in release_secret.parents
                    or release_secret in resolved_output.parents or release_secret == resolved_original
                    or release_secret in resolved_original.parents or resolved_original in release_secret.parents):
                raise ValueError("Runtime library authorization output/transport overlaps a signer key")
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
                or read_regular_file_bytes(root_public_key, max_bytes=4096, reject_symlink_parents=True) != root_bytes
                or regular_file_inventory(root_delegation) != delegation_before
                or regular_file_inventory(delegation) != delegated_inventory):
            raise ValueError("Runtime protected original changed during library authorization")
        inventory = regular_file_inventory(output)
        publish_regular_tree(output, destination, expected_inventory=inventory)
        if regular_file_inventory(destination) != inventory or \
                regular_file_inventory(protected_output, allow_empty=True) != before:
            raise ValueError("Runtime library authorization changed during publication")
        return {"files": inventory, "rootFingerprint": expected_root_fingerprint,
                "rootPublicKeySha256": expected_root_public_key_sha256,
                "delegationInventorySha256": expected_delegation_inventory_sha256,
                "runtimeVersion": verified["manifest"]["runtimeVersion"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue split Runtime root and release evidence")
    modes = parser.add_subparsers(dest="mode", required=True)
    delegate = modes.add_parser("delegate")
    for name in ("destination", "keyring", "keys-directory", "root-public-key",
                 "expected-root-public-key-sha256", "expected-keyring-sha256",
                 "expected-keys-inventory-sha256", "root-private-key"):
        delegate.add_argument(f"--{name}", required=True)
    authorize = modes.add_parser("authorize")
    for name in ("protected-output", "destination", "expected-metadata-receipt-sha256",
                 "expected-build-key", "keyring", "keys-directory", "root-public-key",
                 "expected-root-fingerprint", "expected-root-public-key-sha256",
                 "root-delegation", "expected-delegation-inventory-sha256", "release-private-key"):
        authorize.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    if args.mode == "delegate":
        result = issue_authenticated_runtime_root_delegation(
            Path(args.destination), keyring=Path(args.keyring),
            keys_directory=Path(args.keys_directory), root_public_key=Path(args.root_public_key),
            expected_root_public_key_sha256=args.expected_root_public_key_sha256,
            expected_keyring_sha256=args.expected_keyring_sha256,
            expected_keys_inventory_sha256=args.expected_keys_inventory_sha256,
            root_private_key=Path(args.root_private_key),
        )
    else:
        result = produce_authenticated_runtime_libraries(
            Path(args.protected_output), Path(args.destination),
            expected_metadata_receipt_sha256=args.expected_metadata_receipt_sha256,
            expected_build_key=args.expected_build_key,
            keyring=Path(args.keyring), keys_directory=Path(args.keys_directory),
            root_public_key=Path(args.root_public_key),
            expected_root_fingerprint=args.expected_root_fingerprint,
            expected_root_public_key_sha256=args.expected_root_public_key_sha256,
            root_delegation=Path(args.root_delegation),
            expected_delegation_inventory_sha256=args.expected_delegation_inventory_sha256,
            release_private_key=Path(args.release_private_key),
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
