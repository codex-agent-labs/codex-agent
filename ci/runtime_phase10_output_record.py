"""Verify a protected Runtime output record against official transport and bytes.

This release-only record is not a reusable product payload or hosted evidence
until the protected workflow retains its exact signed bytes.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.runtime_phase10_upload_locator import capture_observed_runtime_phase10_upload
from ci.runtime_phase11_bytes import forward_verified_runtime_phase10_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, snapshot_regular_tree,
)
from ci.products.signatures import (
    load_keyring, require_active_release_key, verify_manifest_signature,
)
from ci.products.signing_isolation import require_no_signing_secret


_PINS = {
    "expected_protected_inventory_sha256", "expected_sidecar_inventory_sha256",
    "expected_metadata_receipt_sha256", "expected_build_key",
    "expected_runtime_version", "expected_manifest_sha256",
    "expected_source_commit", "expected_source_tree", "expected_validation_tree",
    "expected_workflow_sha", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256",
}


def verify_signed_runtime_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    protected_output: Path, maven_sidecars: Path, pgp_public_key: Path,
    plan_path: Path, *, trusted_source_commit: str, trusted_workflow_sha: str,
    expected_pgp_key_sha256: str, token: str, environ=None,
) -> dict:
    """Authenticate an exact Phase-10 Runtime set, without signing or admission."""
    require_no_signing_secret(os.environ if environ is None else environ)
    require_no_signing_secret(os.environ)
    repository_root, protected_output, maven_sidecars = map(
        Path, (repository_root, protected_output, maven_sidecars),
    )
    record_bytes = read_regular_file_bytes(
        Path(record_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature_path), max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
        "schemaVersion", "product", "signing", "trustedSourceCommit",
        "officialUpload", "phase11Pins", "protectedFiles", "sidecarFiles",
    }, "Runtime Phase-10 output record")
    if require_integer(record["schemaVersion"], "Runtime output schemaVersion", 1) != 1 or \
            record["product"] != "runtime" or \
            record["trustedSourceCommit"] != trusted_source_commit:
        raise ValueError("Runtime Phase-10 output record source is not independently pinned")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Runtime Phase-10 trusted source must be a full Git object ID")
    pins = require_exact_keys(record["phase11Pins"], _PINS, "Runtime Phase-10 output pins")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Runtime PGP key digest",
            ):
        raise ValueError("Runtime Phase-10 output pins differ from independent authority")
    if pins["expected_source_tree"] != product_reuse._git_value(
        repository_root, "rev-parse", f"{trusted_source_commit}^{{tree}}",
    ):
        raise ValueError("Runtime Phase-10 source tree differs from trusted Git")
    if type(record["protectedFiles"]) is not list or not record["protectedFiles"] or \
            type(record["sidecarFiles"]) is not list or not record["sidecarFiles"]:
        raise ValueError("Runtime Phase-10 output inventories are empty")
    if pins["expected_protected_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(record["protectedFiles"]),
    ) or pins["expected_sidecar_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(record["sidecarFiles"]),
    ):
        raise ValueError("Runtime Phase-10 output inventory digest differs from record")

    with tempfile.TemporaryDirectory(prefix="rt-phase10-record-") as temporary:
        root = Path(temporary).resolve()
        trust = product_reuse._release_trust(repository_root, trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Runtime release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if record["signing"] != signing:
            raise ValueError("Runtime Phase-10 output record signer differs from source policy")
        pinned_record = root / "record.json"
        pinned_signature = root / "record.sig"
        pinned_record.write_bytes(record_bytes)
        pinned_signature.write_bytes(signature_bytes)
        verify_manifest_signature(pinned_record, pinned_signature, public, signing)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Runtime Phase-10 verifier policy differs from trusted Git")
        pgp_bytes = read_regular_file_bytes(
            Path(pgp_public_key), max_bytes=1024 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(pgp_bytes) != pins["expected_pgp_key_sha256"]:
            raise ValueError("Runtime Phase-10 PGP key differs from independent pin")
        pinned_pgp = root / "pgp-public-key.asc"
        pinned_pgp.write_bytes(pgp_bytes)
        pinned_sidecars = root / "maven-sidecars"
        snapshot_regular_tree(maven_sidecars, pinned_sidecars)
        if regular_file_inventory(pinned_sidecars) != record["sidecarFiles"]:
            raise ValueError("Runtime Phase-10 sidecars changed during capture")

        # Official capture retains its own original archive and transport
        # provenance; the signed record binds that observation to these bytes.
        capture = root / "official-upload"
        observation = capture_observed_runtime_phase10_upload(
            plan_path, repository_root, capture,
            trusted_workflow_sha=trusted_workflow_sha,
            expected_build_key=pins["expected_build_key"],
            expected_metadata_receipt_sha256=pins["expected_metadata_receipt_sha256"],
            token=token, environ=environ,
        )
        if record["officialUpload"] != observation or \
                pins["expected_validation_tree"] != observation["captureProducer"]["tree"]:
            raise ValueError("Runtime Phase-10 output record differs from official upload")
        if regular_file_inventory(capture / "original", allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(protected_output, allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(maven_sidecars) != record["sidecarFiles"]:
            raise ValueError("Runtime Phase-10 output record differs from selected bytes")
        require_no_signing_secret(os.environ if environ is None else environ)
        require_no_signing_secret(os.environ)
        forward_verified_runtime_phase10_bytes(
            capture / "original", pinned_sidecars, root / "verified",
            landed_repository=repository_root, keyring=trust.keyring,
            keys_directory=trust.keys, pgp_public_key=pinned_pgp, **pins,
        )
        if regular_file_inventory(protected_output, allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(maven_sidecars) != record["sidecarFiles"] or \
                read_regular_file_bytes(Path(pgp_public_key), max_bytes=1024 * 1024,
                                        reject_symlink_parents=True) != pgp_bytes or \
                read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != record_bytes or \
                read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                        reject_symlink_parents=True) != signature_bytes:
            raise ValueError("Runtime Phase-10 output or signed record changed during verification")
        require_no_signing_secret(os.environ if environ is None else environ)
        require_no_signing_secret(os.environ)
    return record
