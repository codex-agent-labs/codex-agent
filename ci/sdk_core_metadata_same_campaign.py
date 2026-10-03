"""Hold same-campaign Core metadata admission without inventing a catalog.

The selected receipt is caller-pinned; its upload is re-observed through the
official API. Eleven independently captured original validations are replayed
by the existing Core reader. This grants no host or compiler attestation.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256, sha256_bytes)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.restore import verify_phase_shard
from products.sdk_facade_metadata_admission import FacadeMetadataAdmission
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import capture_sdk_facade_metadata_upload
from sdk_facade_metadata_original import _context
from sdk_facade_metadata_policy import write_facade_metadata_policy
from sdk_facade_original_inputs import held_fresh_facade_metadata_policy
from sdk_facade_upload_locator import locate_original_facade_upload


_METADATA = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


@contextmanager
def held_same_campaign_core_metadata_policy(plan, discovery, before_state, after_state,
        metadata_receipt_path, *, expected_build_key, expected_receipt_sha256,
        expected_artifact_id, expected_artifact_sha256, replay_policy, original_context,
        trusted_workflow_sha, repository_root,
        environ, token, sdk_apple_validation_policy=None):
    """Yield a temporary concrete admission descriptor for Android wave 15.

    The protected caller pins both state uploads and the metadata receipt.
    The descriptor must be consumed while this context holds all originals.
    Retained metadata and a fresh worker's records=[] descriptor are never
    accepted as their own authority.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    discovery, after_state, _ = product_reuse._product_materialization_paths(
        root, Path(discovery), Path(after_state), root / "build/same-campaign-core-unused")
    receipt_path = Path(metadata_receipt_path).absolute()
    if receipt_path.resolve(strict=True) != receipt_path:
        raise ValueError("Core metadata caller receipt must be normalized and non-symbolic")
    require_sha256(expected_receipt_sha256, "Same-campaign Core metadata receipt")
    require_integer(expected_artifact_id, "Same-campaign Core metadata upload ID", 1)
    require_sha256(expected_artifact_sha256, "Same-campaign Core metadata upload digest")
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != expected_receipt_sha256:
        raise ValueError("Core metadata receipt differs from caller selection")
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-core", "metadata", "common") or receipt["buildKey"] != expected_build_key):
        raise ValueError("Core metadata receipt differs from elected phase")
    context = _context(original_context)
    state_inventory = regular_file_inventory(after_state, allow_empty=True)

    with held_fresh_facade_metadata_policy(plan, discovery, before_state,
            expected_build_key=expected_build_key, replay_policy=replay_policy,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
            environ=environ, token=token,
            sdk_apple_validation_policy=sdk_apple_validation_policy) as fresh_path:
        fresh = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(fresh_path,
            reject_symlink_parents=True)), {"evidenceRoot", "records", "policy"},
            "Fresh Core metadata descriptor")
        if fresh["records"] != []:
            raise ValueError("Fresh Core metadata descriptor cannot certify reuse")
        evidence = Path(fresh_path).parent
        if Path(fresh["evidenceRoot"]) != evidence / "evidence":
            raise ValueError("Fresh Core metadata capture root differs from its held original")
        locator = locate_original_facade_upload(receipt_path,
            expected_receipt_sha256=expected_receipt_sha256,
            trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ)
        if (locator["artifact_id"] != expected_artifact_id or
                locator["artifact_sha256"] != expected_artifact_sha256):
            raise ValueError("Original Core metadata upload differs from successful worker pins")
        metadata_capture = evidence / "common"
        capture_sdk_facade_metadata_upload(plan, metadata_capture,
            metadata_receipt_path=receipt_path, artifact_id=locator["artifact_id"],
            artifact_sha256=locator["artifact_sha256"], trusted_workflow_sha=trusted_workflow_sha,
            repository_root=root, environ=environ, token=token)
        metadata_envelope = verify_phase_shard(metadata_capture / "original/shard", _METADATA)
        if (metadata_envelope["receiptBytes"] != raw or
                metadata_envelope["receiptSha256"] != expected_receipt_sha256):
            raise ValueError("Official Core metadata upload differs from selected receipt")
        validations, records = [], [{"receiptSha256": expected_receipt_sha256,
                                      "captureRoot": "common"}]
        for target in SDK_FACADE_TARGETS:
            selected = fresh["policy"]["validations"][target]
            capture = evidence / "evidence" / target
            if Path(selected["captureRoot"]) != capture:
                raise ValueError("Core validation capture differs from its held original")
            envelope = verify_phase_shard(capture / "original/shard",
                PhaseInstanceId("sdk", "sdk-core", "validation", target))
            if envelope["receiptBytes"] != read_regular_file_bytes(
                    Path(selected["validationReceipt"]), reject_symlink_parents=True):
                raise ValueError("Core validation capture differs from caller receipt")
            validations.append(envelope)
            records.append({"receiptSha256": envelope["receiptSha256"],
                            "captureRoot": f"evidence/{target}"})
        records.sort(key=lambda value: value["receiptSha256"])
        policy = {**fresh["policy"], "originalContext": context}
        with tempfile.TemporaryDirectory(prefix="same-campaign-core-metadata-") as temporary:
            descriptor = Path(temporary).resolve() / "policy.json"
            write_facade_metadata_policy(plan, descriptor, evidence_root=evidence,
                records=records, policy=policy, metadata_envelope={key: metadata_envelope[key]
                    for key in ("receipt", "receiptBytes", "receiptSha256", "objectSha256")},
                validation_envelopes=[{key: envelope[key] for key in
                    ("receipt", "receiptBytes", "receiptSha256", "objectSha256")}
                    for envelope in validations], repository_root=root)
            admission = FacadeMetadataAdmission(evidence, records, repository=root,
                policy_revision=receipt["producer"]["commit"], policy=policy)
            verified = product_reuse._verified_product_state(plan, discovery, after_state,
                root, environ, {"evidence": policy["toolingEvidence"],
                    "publicKey": policy["toolingPublicKey"],
                    "javaExecutable": policy["javaExecutable"],
                    "requiredTrustDomain": policy["toolingTrustDomain"],
                    "keyring": policy["toolingKeyring"],
                    "keysDirectory": policy["toolingKeysDirectory"]},
                sdk_original_workflow_sha=trusted_workflow_sha,
                sdk_apple_validation_policy=sdk_apple_validation_policy,
                sdk_facade_metadata_admission=admission)
            selected = verified.prior_by_instance.get(_METADATA)
            if (selected is None or receipt["producer"] != verified.producer or
                    selected["state"] != "retained" or selected["source"] is not None
                    or selected["transportSource"] is not None or
                    selected["buildKey"] != expected_build_key or
                    selected["receiptSha256"] != expected_receipt_sha256 or
                    selected["objectSha256"] != metadata_envelope["objectSha256"]):
                raise ValueError("Completed Core metadata state differs from original upload")
            capture_inventory = regular_file_inventory(evidence, allow_empty=True)
            descriptor_bytes = read_regular_file_bytes(descriptor, reject_symlink_parents=True)
            if regular_file_inventory(after_state, allow_empty=True) != state_inventory:
                raise ValueError("Completed Core metadata state changed before admission")
            try:
                yield descriptor
            finally:
                if (regular_file_inventory(evidence, allow_empty=True) != capture_inventory or
                        regular_file_inventory(after_state, allow_empty=True) != state_inventory or
                        read_regular_file_bytes(descriptor, reject_symlink_parents=True) != descriptor_bytes or
                        read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != raw):
                    raise ValueError("Same-campaign Core metadata authority changed while held")
