"""Sign only an independently prepared failed-SDK-catalog custody record.

The protected caller owns private-key custody and reviewed source selection;
this module performs no GitHub lookup and grants no SDK release admission.
Its CLI is not protected authority until a reviewed, approved workflow supplies
the source, record, keyring, and public-key inventory pins independently.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_sha256, sha256_bytes,
)
from ci.products.signatures import (
    private_key_bytes, require_active_release_key, sign_manifest, verify_manifest_signature,
)
from ci.sdk_catalog_custody import (
    PUBLIC_KEY, RECORD, SIGNATURE, _exact_inventory, _pinned_policy,
    validate_custody_record,
)


def sign_prepared_failed_sdk_catalog_custody(prepared_root, destination, *,
        expected_record_sha256, trusted_source_commit, keyring_path,
        keys_directory, expected_keyring_sha256,
        expected_keys_inventory_sha256, private_key):
    """Publish an immutable signed record/key pair from exact prepared bytes."""
    prepared_root = Path(prepared_root)
    before = regular_file_inventory(prepared_root)
    if {row["relativePath"] for row in before} != {RECORD, PUBLIC_KEY}:
        raise ValueError("Prepared SDK custody has an unexpected file layout")
    raw = read_regular_file_bytes(prepared_root / RECORD,
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(expected_record_sha256, "Independent custody record digest"):
        raise ValueError("Prepared SDK custody differs from independent record pin")
    record = validate_custody_record(load_canonical_json_bytes(raw))
    if (raw != canonical_json_bytes(record)
            or record["trustedSourceCommit"] != trusted_source_commit
            or record["keyringSha256"] != expected_keyring_sha256
            or record["keysInventorySha256"] != expected_keys_inventory_sha256):
        raise ValueError("Prepared SDK custody differs from reviewed signer policy")
    key = read_regular_file_bytes(prepared_root / PUBLIC_KEY,
        max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(key) != record["catalog"]["publicKeySha256"]:
        raise ValueError("Prepared SDK custody key differs from signed candidate")
    policy = _pinned_policy(keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256)
    active, signer = require_active_release_key(policy, keys_directory)
    signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
    signing.update(active)
    if record["signing"] != signing:
        raise ValueError("Prepared SDK custody does not name the active release signer")
    with tempfile.TemporaryDirectory(prefix="sdk-catalog-custody-sign-") as temporary:
        staged = Path(temporary).resolve() / "signed"
        staged.mkdir()
        (staged / RECORD).write_bytes(raw)
        (staged / PUBLIC_KEY).write_bytes(key)
        signature = sign_manifest(staged / RECORD, private_key, signing)
        if signature.name != SIGNATURE:
            raise ValueError("SDK custody signature path is unexpected")
        signature_bytes = read_regular_file_bytes(signature, max_bytes=64 * 1024,
            reject_symlink_parents=True)
        verify_manifest_signature(staged / RECORD, signature, signer, signing)
        if (regular_file_inventory(prepared_root) != before
                or read_regular_file_bytes(prepared_root / RECORD,
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != raw
                or read_regular_file_bytes(prepared_root / PUBLIC_KEY,
                    max_bytes=64 * 1024, reject_symlink_parents=True) != key):
            raise ValueError("Prepared SDK custody changed during protected signing")
        publish_regular_tree(staged, destination,
            expected_inventory=_exact_inventory({
                RECORD: raw, PUBLIC_KEY: key, SIGNATURE: signature_bytes}))
    return {"recordSha256": expected_record_sha256,
            "signatureSha256": sha256_bytes(read_regular_file_bytes(
                Path(destination) / SIGNATURE, max_bytes=64 * 1024,
                reject_symlink_parents=True))}


def main(argv=None) -> int:
    """Sign pinned bytes without an official-upload token or network lookup."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--prepared-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--expected-record-sha256", required=True)
    parser.add_argument("--trusted-source-commit", required=True)
    parser.add_argument("--keyring-path", type=Path, required=True)
    parser.add_argument("--keys-directory", type=Path, required=True)
    parser.add_argument("--expected-keyring-sha256", required=True)
    parser.add_argument("--expected-keys-inventory-sha256", required=True)
    args = parser.parse_args(argv)
    if any(name in os.environ for name in ("GITHUB_TOKEN", "GH_TOKEN", "ACTIONS_RUNTIME_TOKEN")):
        raise ValueError("Protected SDK custody signer must not receive GitHub tokens")
    secret = os.environ.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
    if type(secret) is not str or not secret:
        raise ValueError("Protected SDK custody signing key is unavailable")
    with tempfile.TemporaryDirectory(prefix="sdk-custody-key-") as temporary:
        private_key = Path(temporary) / "release-ed25519"
        descriptor = os.open(private_key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(private_key_bytes(secret))
        result = sign_prepared_failed_sdk_catalog_custody(
            args.prepared_root, args.destination,
            expected_record_sha256=args.expected_record_sha256,
            trusted_source_commit=args.trusted_source_commit,
            keyring_path=args.keyring_path, keys_directory=args.keys_directory,
            expected_keyring_sha256=args.expected_keyring_sha256,
            expected_keys_inventory_sha256=args.expected_keys_inventory_sha256,
            private_key=private_key)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
