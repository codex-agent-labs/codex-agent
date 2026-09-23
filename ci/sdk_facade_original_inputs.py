"""Hold official original Core carriers while the existing strict selector replays them.

The caller independently authenticates the signed catalog, original receipt
digests and replay policy. This module neither elects product work nor turns
runner labels into native compiler/toolchain proof.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile

from ci.products.inventory import (canonical_json_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, sha256_bytes)
from ci.products.registry import SDK_FACADE_TARGETS
from ci.products.signing_isolation import require_no_signing_secret
from ci.sdk_facade_capture import (capture_sdk_facade_metadata_upload,
    capture_sdk_facade_validation_upload)
from ci.sdk_facade_metadata_selection import write_selected_facade_metadata_policy
from ci.sdk_facade_upload_locator import locate_original_facade_upload


@contextmanager
def held_original_facade_metadata_policy(plan, *, catalog, catalog_source,
        metadata_receipt_path, expected_receipt_sha256, replay_policy,
        trusted_workflow_sha, repository_root, token):
    """Yield a temporary descriptor after all twelve official captures and replay.

    `expected_receipt_sha256` is the caller-authenticated mapping for `common`
    plus all eleven targets. `replay_policy` is the independent Core metadata
    policy without captureRoot fields; this function fills only those paths.
    Consumers must use the descriptor inside the context and rerun the concrete
    metadata admission. Original producers remain exactly as in the receipts.
    """
    require_no_signing_secret(os.environ)
    root = Path(repository_root).resolve(strict=True)
    expected = require_exact_keys(expected_receipt_sha256,
        {"common", *SDK_FACADE_TARGETS}, "Caller-selected Core original receipts")
    for digest in expected.values():
        require_sha256(digest, "Caller-selected Core original receipt")
    policy_bytes = canonical_json_bytes(replay_policy)
    policy = load_canonical_json_bytes(policy_bytes)
    validations = require_exact_keys(policy["validations"], SDK_FACADE_TARGETS,
                                   "Core original validation policy")
    if any("captureRoot" in value for value in validations.values()):
        raise ValueError("Core original capture paths must come from official capture")
    paths = {"common": Path(metadata_receipt_path), **{
        target: Path(validations[target]["validationReceipt"]) for target in SDK_FACADE_TARGETS}}
    originals = {}
    for target, path in paths.items():
        raw = read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                      reject_symlink_parents=True)
        if sha256_bytes(raw) != expected[target]:
            raise ValueError("Core original receipt differs from independent selection")
        originals[target] = raw
    expected_bytes = canonical_json_bytes(expected)

    def unchanged():
        require_no_signing_secret(os.environ)
        if (canonical_json_bytes(expected_receipt_sha256) != expected_bytes
                or canonical_json_bytes(replay_policy) != policy_bytes
                or any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                       reject_symlink_parents=True) != originals[target]
                       for target, path in paths.items())):
            raise ValueError("Core caller-selected originals or policy changed")

    unchanged()
    with tempfile.TemporaryDirectory(prefix="core-original-inputs-") as temporary:
        private = Path(temporary).resolve(strict=True)
        if private == root or root in private.parents:
            raise ValueError("Core original scratch must remain outside the source repository")
        evidence = private / "evidence"
        evidence.mkdir()
        for target in (*SDK_FACADE_TARGETS, "common"):
            unchanged()
            path = paths[target]
            locator = locate_original_facade_upload(path,
                expected_receipt_sha256=expected[target],
                trusted_workflow_sha=trusted_workflow_sha, token=token)
            unchanged()
            arguments = dict(artifact_id=locator["artifact_id"],
                artifact_sha256=locator["artifact_sha256"],
                trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, token=token)
            capture = evidence / target
            if target == "common":
                capture_sdk_facade_metadata_upload(plan, capture,
                    metadata_receipt_path=path, **arguments)
            else:
                capture_sdk_facade_validation_upload(plan, capture,
                    validation_receipt_path=path, **arguments)
            unchanged()
            if target != "common":
                policy["validations"][target]["captureRoot"] = str(capture)
        records = sorted(({"receiptSha256": expected[target], "captureRoot": target}
                          for target in ("common", *SDK_FACADE_TARGETS)),
                         key=lambda record: record["receiptSha256"])
        descriptor = private / "policy.json"
        write_selected_facade_metadata_policy(plan, descriptor, catalog=catalog,
            catalog_source=catalog_source, metadata_receipt_path=paths["common"],
            evidence_root=evidence, records=records, policy=policy,
            repository_root=root)
        before = regular_file_inventory(evidence, allow_empty=True)
        descriptor_bytes = read_regular_file_bytes(descriptor, reject_symlink_parents=True)
        unchanged()
        try:
            yield descriptor
        finally:
            unchanged()
            if (regular_file_inventory(evidence, allow_empty=True) != before
                    or read_regular_file_bytes(descriptor, reject_symlink_parents=True) != descriptor_bytes):
                raise ValueError("Core original carriers or descriptor changed while held")
