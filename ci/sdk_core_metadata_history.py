"""Verify an independently signed original Core metadata invocation context.

The protected signer must inspect the successful worker outputs and official
upload before issuing this external record. This reader cannot make a retained
worker ZIP authoritative merely by finding the same paths inside it.
"""

from pathlib import Path
import tempfile

from .products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_sha256, sha256_bytes,
)
from .products.receipt import validate_phase_receipt
from .products.signatures import (
    load_keyring, public_key_for_metadata, verify_manifest_signature,
)
from .sdk_facade_metadata_original import _context


def verify_signed_original_core_context(manifest_path, signature_path, receipt_path, *,
        expected_build_key, expected_receipt_sha256, expected_artifact_id,
        expected_artifact_sha256, keyring_path, keys_directory):
    """Return signed historical paths only for the exact selected Core receipt.

    Artifact ID/digest must come from independent official-upload selection;
    this record does not itself verify a hosting-service observation.
    """
    manifest_path = Path(manifest_path)
    raw = read_regular_file_bytes(manifest_path, max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    record = require_exact_keys(load_canonical_json_bytes(raw), {
        "schemaVersion", "kind", "buildKey", "receiptSha256", "artifactId",
        "artifactSha256", "producer", "originalContext", "signing",
    }, "Signed original Core metadata context")
    if (require_integer(record["schemaVersion"], "Core context schemaVersion", 1) != 1
            or record["kind"] != "sdk-core-metadata-original-context"):
        raise ValueError("Unsupported signed original Core metadata context")
    require_sha256(expected_receipt_sha256, "Selected Core metadata receipt digest")
    require_sha256(expected_artifact_sha256, "Selected Core metadata upload digest")
    require_integer(expected_artifact_id, "Selected Core metadata upload ID", 1)
    receipt_raw = read_regular_file_bytes(Path(receipt_path), max_bytes=16 * 1024 * 1024,
                                          reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_raw))
    if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-core", "metadata", "common")
            or receipt["buildKey"] != expected_build_key
            or sha256_bytes(receipt_raw) != expected_receipt_sha256
            or record["buildKey"] != expected_build_key
            or record["receiptSha256"] != expected_receipt_sha256
            or record["artifactId"] != expected_artifact_id
            or record["artifactSha256"] != expected_artifact_sha256
            or record["producer"] != receipt["producer"]):
        raise ValueError("Signed original Core context differs from selected receipt/upload")
    context = _context(record["originalContext"])
    keyring = load_keyring(Path(keyring_path), Path(keys_directory))
    public_key = public_key_for_metadata(record["signing"], keyring,
                                          Path(keys_directory), allow_retired=True)
    signature = read_regular_file_bytes(Path(signature_path), max_bytes=1024 * 1024,
                                        reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="core-context-verify-") as temporary:
        snapshot = Path(temporary) / "original-context.json"
        detached = Path(temporary) / "original-context.sig"
        snapshot.write_bytes(raw)
        detached.write_bytes(signature)
        verify_manifest_signature(snapshot, detached, public_key, record["signing"])
    return context
