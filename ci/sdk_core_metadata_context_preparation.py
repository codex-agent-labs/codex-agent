"""Prepare original Core-14 context on a non-secret runner after full replay.

The resulting unsigned external record is only candidate evidence. A separate
protected runner must independently capture this preparation and the original
upload, bind caller-pinned identities, and sign without executing replay code.
"""

import argparse
import os
from pathlib import Path
import tempfile

from .products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_integer, require_sha256, sha256_bytes,
    write_canonical_json,
)
from .products.receipt import validate_phase_receipt
from .products.registry import SDK_FACADE_TARGETS
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
    record_bytes = canonical_json_bytes(record)
    record_inventory = [{"relativePath": "original-context.json", "bytes": len(record_bytes),
                         "sha256": sha256_bytes(record_bytes)}]
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
        publish_regular_tree(prepared, destination, expected_inventory=record_inventory)
    return destination / "original-context.json", record_bytes


_CALLER_FIELDS = {"schemaVersion", "plan", "metadataReceiptPath", "expectedBuildKey",
    "expectedReceiptSha256", "artifactId", "artifactSha256", "originalContext", "validations",
    "contractDigest", "componentDigests", "toolingEvidence", "toolingPublicKey",
    "javaExecutable", "policyRevision", "requiredTrustDomain", "toolingKeyring",
    "toolingKeysDirectory"}


def prepare_from_caller_policy(caller_policy, destination, *, repository_root,
        trusted_workflow_sha, signing_keyring, signing_keys_directory, environ, token):
    """Consume an external caller policy, never the retained metadata request.

    The invoking workflow must construct the policy from independently selected
    worker outputs and original validation locators. This entry verifies those
    claims; mere possession of the policy does not grant release trust.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    source = Path(caller_policy).absolute()
    if (source.resolve(strict=True) != source or source == root or source.is_relative_to(root)):
        raise ValueError("Core context caller policy must be external and non-symbolic")
    raw = read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    policy = require_exact_keys(load_canonical_json_bytes(raw), _CALLER_FIELDS,
                                "Core context independent caller policy")
    if require_integer(policy["schemaVersion"], "Core caller policy schemaVersion", 1) != 1:
        raise ValueError("Unsupported Core context caller policy schema")
    for record in require_exact_keys(policy["validations"], SDK_FACADE_TARGETS,
                                     "Core context original validations").values():
        if type(record) is not dict or "captureRoot" in record:
            raise ValueError("Core context preparation requires original validation uploads")
    destination = Path(destination).absolute()
    _require_capability_output_separate(destination, [root, source, Path(policy["plan"]),
        Path(policy["metadataReceiptPath"]), Path(signing_keyring), Path(signing_keys_directory)])
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Core context preparation destination must be fresh and non-symbolic")
    with tempfile.TemporaryDirectory(prefix="core-original-context-entry-") as temporary:
        staged = Path(temporary).resolve() / "candidate"
        _, original_record_bytes = prepare_original_core_context(
            policy["plan"], policy["metadataReceiptPath"], staged,
            expected_build_key=policy["expectedBuildKey"],
            expected_receipt_sha256=policy["expectedReceiptSha256"],
            artifact_id=policy["artifactId"], artifact_sha256=policy["artifactSha256"],
            original_context=policy["originalContext"], validations=policy["validations"],
            contract_digest=policy["contractDigest"], component_digests=policy["componentDigests"],
            repository_root=root, environ=environ, token=token,
            trusted_workflow_sha=trusted_workflow_sha,
            tooling_evidence=policy["toolingEvidence"], tooling_public_key=policy["toolingPublicKey"],
            java_executable=policy["javaExecutable"], policy_revision=policy["policyRevision"],
            required_trust_domain=policy["requiredTrustDomain"],
            tooling_keyring=policy["toolingKeyring"],
            tooling_keys_directory=policy["toolingKeysDirectory"],
            signing_keyring=signing_keyring, signing_keys_directory=signing_keys_directory)
        require_no_signing_secret(environ)
        if read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != raw:
            raise ValueError("Core context caller policy changed during original replay")
        publish_regular_tree(staged, destination, expected_inventory=[{
            "relativePath": "original-context.json", "bytes": len(original_record_bytes),
            "sha256": sha256_bytes(original_record_bytes)}])
    return destination / "original-context.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("caller-policy", "destination", "repository-root", "signing-keyring",
                 "signing-keys-directory"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    args = vars(parser.parse_args(argv))
    try:
        require_no_signing_secret(os.environ)
        prepare_from_caller_policy(**args, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
