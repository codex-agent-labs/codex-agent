"""Protected, local-only signer for an already prepared Contract output record.

Workflow environment approval and the independent record digest are caller
authorities. This process never imports official-upload or product-build code.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes,
)
from ci.products.signatures import (
    load_keyring, private_key_bytes, public_key_path, require_active_release_key,
    sign_manifest, verify_manifest_signature,
)


_KEYRING = "gradle/release/product-signing-keys.json"
_KEYS = "gradle/release/keys"
_SECRET = "CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"


def sign_prepared_contract_phase10_record(
    prepared_record: Path, repository_root: Path, *,
    trusted_source_commit: str, expected_record_sha256: str,
    environ=None,
) -> dict:
    """Sign only an independently pinned record with its source-pinned key."""
    environment = os.environ if environ is None else environ
    secret = environment.get(_SECRET)
    if type(secret) is not str or not secret:
        raise ValueError("Protected Contract release signing key is unavailable")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Contract signer source must be a full Git object ID")
    expected_record_sha256 = require_sha256(
        expected_record_sha256, "independently prepared Contract record digest",
    )
    prepared_record = Path(prepared_record)
    record_bytes = read_regular_file_bytes(
        prepared_record, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    if sha256_bytes(record_bytes) != expected_record_sha256:
        raise ValueError("Contract signer record differs from independent preparation")
    published_signature = prepared_record.with_suffix(".sig")
    if published_signature.exists() or published_signature.is_symlink():
        raise ValueError("Contract signer signature already exists")
    record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
        "schemaVersion", "product", "signing", "trustedSourceCommit",
        "officialUpload", "phase11Pins", "outputFiles",
    }, "Contract Phase-10 output record")
    if require_integer(record["schemaVersion"], "Contract record schemaVersion", 1) != 1 or \
            record["product"] != "contract" or \
            record["trustedSourceCommit"] != trusted_source_commit:
        raise ValueError("Contract signer record differs from pinned product/source")
    with tempfile.TemporaryDirectory(prefix="ct-phase10-sign-") as temporary:
        private_root = Path(temporary).resolve()
        keyring_bytes = git_regular_blob_bytes(
            repository_root, trusted_source_commit, _KEYRING, max_bytes=64 * 1024,
        )
        keyring = load_canonical_json_bytes(keyring_bytes)
        if type(keyring) is not dict:
            raise ValueError("Contract signer source keyring is invalid")
        records = [entry for entry in (keyring.get("activeKey"), *keyring.get("retiredKeys", []))
                   if entry is not None]
        keys = private_root / "keys"
        keys.mkdir()
        for entry in records:
            key_id = entry.get("keyId") if type(entry) is dict else None
            target = public_key_path(keys, key_id)
            target.write_bytes(git_regular_blob_bytes(
                repository_root, trusted_source_commit,
                f"{_KEYS}/{target.name}", max_bytes=64 * 1024,
            ))
        keyring_path = private_root / "product-signing-keys.json"
        keyring_path.write_bytes(keyring_bytes)
        policy = load_keyring(keyring_path, keys)
        active, public = require_active_release_key(policy, keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        pins = record["phase11Pins"]
        if record["signing"] != signing or type(pins) is not dict or \
                pins.get("expected_source_commit") != trusted_source_commit or \
                pins.get("expected_keyring_sha256") != sha256_bytes(keyring_bytes) or \
                pins.get("expected_keys_inventory_sha256") != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(keys)),
                ):
            raise ValueError("Contract signer record differs from trusted source key policy")
        private = private_root / "release-ed25519"
        descriptor = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            output.write(private_key_bytes(secret))
        snapshot = private_root / "record.json"
        snapshot.write_bytes(record_bytes)
        signature = sign_manifest(snapshot, private, signing)
        verify_manifest_signature(snapshot, signature, public, signing)
        if read_regular_file_bytes(prepared_record, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != record_bytes:
            raise ValueError("Contract record changed during protected signing")
        signature_bytes = read_regular_file_bytes(
            signature, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        # Keep the private key outside the prepared tree. Publish the checked
        # signature atomically and without replacing an earlier signature.
        with tempfile.TemporaryDirectory(prefix=".ct-record-sig-", dir=prepared_record.parent) as staged_dir:
            staged = Path(staged_dir) / "record.sig"
            staged.write_bytes(signature_bytes)
            if read_regular_file_bytes(prepared_record, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != record_bytes:
                raise ValueError("Contract record changed before signature publication")
            os.link(staged, published_signature)
        if (read_regular_file_bytes(prepared_record, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != record_bytes
                or read_regular_file_bytes(published_signature, max_bytes=64 * 1024,
                                           reject_symlink_parents=True) != signature_bytes):
            raise ValueError("Contract record or detached signature changed after signing")
    return {"recordSha256": expected_record_sha256,
            "signatureSha256": sha256_bytes(signature_bytes)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--prepared-record", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--trusted-source-commit", required=True)
    parser.add_argument("--expected-record-sha256", required=True)
    args = parser.parse_args(argv)
    result = sign_prepared_contract_phase10_record(
        args.prepared_record, args.repository_root,
        trusted_source_commit=args.trusted_source_commit,
        expected_record_sha256=args.expected_record_sha256,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
