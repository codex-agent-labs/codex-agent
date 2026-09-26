"""Verify a protected Contract output record against official transport and bytes.

The release workflow must supply the trusted source/workflow and PGP pins
independently. This reader neither signs nor grants authority to a local ZIP.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.contract_phase10_upload_locator import observe_contract_phase10_upload
from ci.contract_phase11_bytes import forward_verified_contract_phase10_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes,
)
from ci.products.signatures import (
    load_keyring, require_active_release_key, verify_manifest_signature,
)


_PINS = {
    "expected_inventory_sha256", "expected_contract_version",
    "expected_payload_sha256", "expected_metadata_build_key",
    "expected_source_commit", "expected_source_tree",
    "expected_validation_tree", "expected_workflow_sha",
    "expected_caller_sha256", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256",
}


def verify_signed_contract_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    protected_output: Path, plan_path: Path, *, trusted_source_commit: str,
    trusted_workflow_sha: str, trusted_workflow_path: str,
    trusted_job_name: str, expected_pgp_key_sha256: str,
    artifact_id: int, artifact_sha256: str, token: str, environ=None,
) -> dict:
    """Require an independently pinned signer, official upload, and exact files.

    The record and signature are separate release-only control bytes. The
    returned record is suitable as an S1048 Contract handoff only after the
    protected workflow also retains their exact bytes and digest.
    """
    repository_root, protected_output = Path(repository_root), Path(protected_output)
    record_bytes = read_regular_file_bytes(
        Path(record_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature_path), max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
        "schemaVersion", "product", "signing", "trustedSourceCommit",
        "officialUpload", "phase11Pins", "outputFiles",
    }, "Contract Phase-10 output record")
    if require_integer(record["schemaVersion"], "Contract output schemaVersion", 1) != 1 or \
            record["product"] != "contract" or \
            record["trustedSourceCommit"] != trusted_source_commit:
        raise ValueError("Contract Phase-10 output record source is not independently pinned")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Contract Phase-10 trusted source must be a full Git object ID")
    pins = require_exact_keys(record["phase11Pins"], _PINS, "Contract Phase-10 output pins")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Contract PGP key digest",
            ):
        raise ValueError("Contract Phase-10 output pins differ from independent authority")
    if pins["expected_source_tree"] != product_reuse._git_value(
        repository_root, "rev-parse", f"{trusted_source_commit}^{{tree}}",
    ):
        raise ValueError("Contract Phase-10 source tree differs from trusted Git")
    if type(record["outputFiles"]) is not list or not record["outputFiles"]:
        raise ValueError("Contract Phase-10 output inventory is empty")
    inventory_digest = sha256_bytes(canonical_json_bytes(record["outputFiles"]))
    if pins["expected_inventory_sha256"] != inventory_digest:
        raise ValueError("Contract Phase-10 output inventory digest differs from record")

    # Git at the independently supplied source revision, not the transported
    # output, supplies the release verifier policy.
    with tempfile.TemporaryDirectory(prefix="ct-phase10-record-") as temporary:
        root = Path(temporary).resolve()
        trust = product_reuse._release_trust(repository_root, trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Contract release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if record["signing"] != signing:
            raise ValueError("Contract Phase-10 output record signer differs from source policy")
        verify_manifest_signature(Path(record_path), Path(signature_path), public, signing)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Contract Phase-10 output verifier policy differs from trusted Git")

        # The locator verifies the official run/job/upload, rather than
        # trusting transport facts copied into this record.
        observation = observe_contract_phase10_upload(
            plan_path, repository_root, protected_output,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            token=token, environ=environ,
        )
        if record["officialUpload"] != observation or \
                pins["expected_validation_tree"] != observation["producer"]["tree"]:
            raise ValueError("Contract Phase-10 output record differs from official upload")
        if regular_file_inventory(protected_output) != record["outputFiles"] or \
                observation["inventorySha256"] != inventory_digest:
            raise ValueError("Contract Phase-10 output record differs from uploaded bytes")
        forward_verified_contract_phase10_bytes(
            protected_output, root / "verified", landed_repository=repository_root, **pins,
        )
        if regular_file_inventory(protected_output) != record["outputFiles"] or \
                read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != record_bytes or \
                read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                        reject_symlink_parents=True) != signature_bytes:
            raise ValueError("Contract Phase-10 output or signed record changed during verification")
    return record
