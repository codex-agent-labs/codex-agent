"""Prepare original Core-14 context on a non-secret runner after full replay.

The resulting unsigned external record is only candidate evidence. A separate
protected runner must independently capture this preparation and the original
upload, bind caller-pinned identities, and sign without executing replay code.
"""

from pathlib import Path
import tempfile

from .products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_integer, require_sha256, sha256_bytes,
    write_canonical_json,
)
from .products.receipt import validate_phase_receipt
from .products.sdk_package import _require_capability_output_separate
from .products.signing_isolation import require_no_signing_secret
from .products.signatures import (
    load_keyring, require_active_release_key, validate_signing_metadata,
)
from .sdk_facade_metadata_original import _context, verified_original_sdk_facade_metadata


def prepare_original_core_context(plan, metadata_receipt_path, destination, *,
        expected_build_key, expected_receipt_sha256, artifact_id, artifact_sha256,
        original_context, validations, contract_digest, component_digests,
        repository_root, environ, token, trusted_workflow_sha, tooling_evidence,
        tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring, tooling_keys_directory, signing_keyring, signing_keys_directory):
    """Publish unsigned context only after the full original reader exits cleanly.

    ``original_context`` and upload pins must be independent caller inputs,
    never values recovered from the retained worker upload. The original reader
    checks the official successful job/upload, fixed worker command, source key,
    and all eleven validation originals before this record is published.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Prepared Core context destination must be fresh and non-symbolic")
    _require_capability_output_separate(destination, [root, Path(plan), Path(metadata_receipt_path),
        Path(signing_keyring), Path(signing_keys_directory)])
    require_sha256(expected_build_key, "Selected Core metadata build key")
    require_sha256(expected_receipt_sha256, "Selected Core metadata receipt digest")
    require_integer(artifact_id, "Selected Core metadata upload ID", 1)
    require_sha256(artifact_sha256, "Selected Core metadata upload digest")
    context_bytes = canonical_json_bytes(_context(original_context))
    context = _context(load_canonical_json_bytes(context_bytes))
    keyring = load_keyring(Path(signing_keyring), Path(signing_keys_directory))
    active, public_key = require_active_release_key(keyring, Path(signing_keys_directory))
    signing = validate_signing_metadata({name: keyring[name] for name in
        ("algorithm", "namespace", "trustDomain")} | active, trust_domain="release")
    keyring_bytes = read_regular_file_bytes(Path(signing_keyring), reject_symlink_parents=True)
    public_key_bytes = read_regular_file_bytes(public_key, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(Path(metadata_receipt_path),
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-core", "metadata", "common") or
            receipt["buildKey"] != expected_build_key or
            sha256_bytes(receipt_bytes) != expected_receipt_sha256):
        raise ValueError("Core context preparation receipt differs from independent selection")
    with verified_original_sdk_facade_metadata(plan, metadata_receipt_path,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            validations=validations, contract_digest=contract_digest,
            component_digests=component_digests, original_context=context,
            repository_root=root, environ=environ, token=token,
            trusted_workflow_sha=trusted_workflow_sha,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as verified:
        if (verified["receiptBytes"] != receipt_bytes or
                canonical_json_bytes(context) != context_bytes or
                verified["transport"]["artifact"].get("id") != artifact_id or
                verified["transport"]["artifact"].get("digest") != artifact_sha256):
            raise ValueError("Core context preparation differs from selected receipt/upload")
    # The reader's exit performs another full input/capture check. No candidate
    # evidence is emitted if that final check fails.
    record = {"schemaVersion": 1, "kind": "sdk-core-metadata-original-context",
        "buildKey": expected_build_key, "receiptSha256": expected_receipt_sha256,
        "artifactId": artifact_id, "artifactSha256": artifact_sha256,
        "producer": receipt["producer"], "originalContext": context, "signing": signing}
    with tempfile.TemporaryDirectory(prefix="core-original-context-prepare-") as temporary:
        prepared = Path(temporary).resolve() / "unsigned"
        prepared.mkdir()
        manifest = prepared / "original-context.json"
        write_canonical_json(manifest, record)
        if (read_regular_file_bytes(Path(metadata_receipt_path), max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != receipt_bytes or
                canonical_json_bytes(original_context) != context_bytes or
                read_regular_file_bytes(Path(signing_keyring), reject_symlink_parents=True) != keyring_bytes or
                read_regular_file_bytes(public_key, reject_symlink_parents=True) != public_key_bytes):
            raise ValueError("Core context preparation caller trust or inputs changed")
        publish_regular_tree(prepared, destination)
    return destination / "original-context.json"
