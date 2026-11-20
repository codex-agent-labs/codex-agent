"""Capture the three SDK Maven package objects against a protected campaign index.

This is a no-secret, token-bearing custody step. The signed all-62 index is the
prior protected release/semantic decision; this module does not repeat host,
compiler, Firebase, or Apple execution proof and grants no signing authority.
Only the separately pinned same-PR original uploads and their exact object
bytes are retained for a later token-free signer. Promoted-main `push` objects
require a distinct stable-index original reader; this entrypoint rejects them.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.products.index import SignedProductIndex, _verify_index_receipt, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_integer, require_sha256, sha256_bytes,
    snapshot_regular_tree, publish_regular_tree, write_canonical_json,
)
from ci.products.receipt import validate_phase_receipt, validate_producer
from ci.products.registry import PhaseInstanceId
from ci.products.restore import restore_object, verify_phase_shard
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signing_isolation import require_no_signing_secret
from ci.sdk_facade_capture import capture_sdk_maven_upload


_PACKAGES = {
    PhaseInstanceId("sdk", "sdk-core", "package", "common"),
    PhaseInstanceId("sdk", "sdk-android", "package", "android"),
    PhaseInstanceId("sdk", "sdk-ios", "package", "ios"),
}
_SELECTION = {"plan", "repositoryRoot", "receipt", "receiptSha256", "producer",
              "producerSha256", "artifactId", "artifactSha256", "trustedWorkflowSha"}


def capture_sdk_phase10_maven_campaign(
    signed_index: SignedProductIndex, destination: Path, *,
    expected_index_sha256: str, expected_signature_sha256: str,
    keyring_path: Path, keys_directory: Path, expected_keyring_sha256: str,
    expected_keys_inventory_sha256: str,
    selections: dict[PhaseInstanceId, dict], token: str,
) -> dict:
    """Bind official original uploads to exact signed package receipts/objects.

    Each selection is protected caller input, not discovered from an upload.
    A successful result is custody/content evidence only. The prior protected
    all-62 signer, not this function, established semantic release admission.
    """
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token or set(selections) != _PACKAGES:
        raise ValueError("SDK Maven custody requires a token and exact three package selections")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Maven custody destination already exists")
    input_paths = [Path(value) for value in (
        signed_index.manifest, signed_index.signature, keyring_path, keys_directory,
        *(selection[name] for selection in selections.values()
          for name in ("plan", "repositoryRoot", "receipt") if name in selection),
    )]
    output = destination.resolve(strict=False)
    if any(output == path.resolve(strict=True) or
           output in path.resolve(strict=True).parents or
           path.resolve(strict=True) in output.parents for path in input_paths):
        raise ValueError("SDK Maven custody output overlaps a verified input")
    pins = {
        "index": require_sha256(expected_index_sha256, "SDK campaign index digest"),
        "signature": require_sha256(expected_signature_sha256, "SDK campaign signature digest"),
        "keyring": require_sha256(expected_keyring_sha256, "SDK keyring digest"),
        "keys": require_sha256(expected_keys_inventory_sha256, "SDK keys inventory digest"),
    }
    signed_index = SignedProductIndex(Path(signed_index.manifest), Path(signed_index.signature))
    keyring_path, keys_directory = Path(keyring_path), Path(keys_directory)
    raw_index = read_regular_file_bytes(signed_index.manifest, reject_symlink_parents=True)
    raw_signature = read_regular_file_bytes(signed_index.signature, reject_symlink_parents=True)
    keyring_bytes = read_regular_file_bytes(keyring_path, reject_symlink_parents=True)
    keys_inventory = regular_file_inventory(keys_directory)
    if (sha256_bytes(raw_index) != pins["index"] or
            sha256_bytes(raw_signature) != pins["signature"] or
            sha256_bytes(keyring_bytes) != pins["keyring"] or
            sha256_bytes(canonical_json_bytes(keys_inventory)) != pins["keys"]):
        raise ValueError("SDK campaign signature or verifier policy differs from protected pins")
    index, verified_bytes = verify_release_product_index(
        signed_index, keyring_path=keyring_path, keys_directory=keys_directory)
    entries = {PhaseInstanceId(*(entry[field] for field in
        ("product", "component", "phase", "target"))): entry for entry in index["entries"]}
    if (verified_bytes != raw_index or index["repository"] != "codex-agent-labs/codex-agent"
            or index["trustDomain"] != "release" or index["context"]["kind"] != "pull-request"
            or len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES)
            or set(entries) != SDK_CAMPAIGN_INSTANCES
            or len({entry["productVersion"] for entry in index["entries"]}) != 1):
        raise ValueError("SDK Maven custody requires the exact release-signed all-62 PR campaign")
    with tempfile.TemporaryDirectory(prefix="sdk-phase10-maven-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "custody"
        prepared.mkdir()
        policy = prepared / "campaign"
        policy.mkdir()
        (policy / "product-index.json").write_bytes(raw_index)
        (policy / "product-index.sig").write_bytes(raw_signature)
        (policy / "product-signing-keys.json").write_bytes(keyring_bytes)
        snapshot_regular_tree(keys_directory, policy / "keys")
        records = []
        inputs = {}
        approvals = {}
        for instance in sorted(_PACKAGES):
            selected = selections[instance]
            if type(selected) is not dict or set(selected) != _SELECTION:
                raise ValueError("SDK Maven package selection lacks exact protected fields")
            approvals[instance] = canonical_json_bytes(selected)
            receipt_path, plan, source_root = (Path(selected[name]) for name in
                ("receipt", "plan", "repositoryRoot"))
            raw_receipt = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
            receipt_pin = require_sha256(selected["receiptSha256"], "SDK original receipt digest")
            producer_pin = require_sha256(selected["producerSha256"], "SDK original producer digest")
            producer = validate_producer(selected["producer"])
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw_receipt))
            if (sha256_bytes(raw_receipt) != receipt_pin or receipt_pin != entries[instance]["receiptSha256"]
                    or sha256_bytes(canonical_json_bytes(producer)) != producer_pin
                    or receipt["producer"] != producer
                    or tuple(receipt[field] for field in ("product", "component", "phase", "target")) !=
                       (instance.product, instance.component, instance.phase, instance.target)
                    or producer["repository"] != index["repository"]
                    or producer["event"] != "pull_request"
                    or producer["pullRequest"] != index["context"]["pullRequest"]):
                raise ValueError("SDK original package differs from protected receipt/producer")
            validated_plan = product_reuse._validate_plan(
                plan, source_root, expected_revision=producer["commit"])
            if (validated_plan["remoteBuildAuthorized"] is not True
                    or validated_plan["event"] != "pull_request"
                    or validate_producer(product_reuse._consumer(validated_plan, {},
                        original_run_id=producer["runId"],
                        original_run_attempt=producer["runAttempt"])["producer"]) != producer):
                raise ValueError("SDK original plan differs from protected package producer")
            artifact_id = require_integer(selected["artifactId"], "SDK original artifact ID", 1)
            artifact_sha = require_sha256(selected["artifactSha256"], "SDK original artifact digest")
            workflow_sha = selected["trustedWorkflowSha"]
            if type(workflow_sha) is not str or len(workflow_sha) != 40 or any(
                    char not in "0123456789abcdef" for char in workflow_sha):
                raise ValueError("SDK original workflow SHA is invalid")
            before = {"receipt": raw_receipt,
                      "plan": read_regular_file_bytes(plan, reject_symlink_parents=True)}
            component_root = prepared / instance.component
            component_root.mkdir()
            capture = component_root / "capture"
            if instance.component == "sdk-ios":
                observed = product_reuse.capture_sdk_ios_package_upload(
                    plan, capture, package_receipt_path=receipt_path,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha,
                    trusted_workflow_sha=workflow_sha, repository_root=source_root,
                    environ={}, token=token)
            else:
                observed = capture_sdk_maven_upload(
                    plan, capture, receipt_path=receipt_path,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha,
                    trusted_workflow_sha=workflow_sha, repository_root=source_root,
                    environ={}, token=token)
            if (observed["artifact"]["id"] != artifact_id or
                    observed["artifact"]["digest"] != artifact_sha or
                    observed["captureProducer"] != producer):
                raise ValueError("SDK official package transport differs from independent pins")
            shard = verify_phase_shard(capture / "original/shard", instance)
            if shard["receiptBytes"] != raw_receipt:
                raise ValueError("SDK original package shard rewrites the signed receipt")
            _verify_index_receipt(entries[instance], {
                "receipt": shard["receipt"], "receiptSha256": shard["receiptSha256"]})
            stage = component_root / "stage"
            restored = restore_object(capture / "original/shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"],
                object_sha256=shard["objectSha256"])
            if restored["receiptBytes"] != raw_receipt:
                raise ValueError("SDK restored package differs from original receipt")
            (component_root / "phase-receipt.json").write_bytes(raw_receipt)
            records.append({"component": instance.component, "target": instance.target,
                "receiptSha256": receipt_pin, "objectSha256": shard["objectSha256"],
                "artifactId": artifact_id, "artifactSha256": artifact_sha,
                "producerSha256": producer_pin, "stageFiles": regular_file_inventory(stage)})
            inputs[instance] = (receipt_path, plan, before)
        write_canonical_json(prepared / "custody.json", {
            "schemaVersion": 1, "product": "sdk", "signedIndexSha256": pins["index"],
            "signedIndexSignatureSha256": pins["signature"], "packages": records})
        inventory = regular_file_inventory(prepared, allow_empty=True)
        if (read_regular_file_bytes(signed_index.manifest, reject_symlink_parents=True) != raw_index
                or read_regular_file_bytes(signed_index.signature, reject_symlink_parents=True) != raw_signature
                or read_regular_file_bytes(keyring_path, reject_symlink_parents=True) != keyring_bytes
                or regular_file_inventory(keys_directory) != keys_inventory
                or any(read_regular_file_bytes(receipt, reject_symlink_parents=True) != before["receipt"]
                       or read_regular_file_bytes(plan, reject_symlink_parents=True) != before["plan"]
                       for receipt, plan, before in inputs.values())
                or set(selections) != _PACKAGES
                or any(canonical_json_bytes(selections[instance]) != approved
                       for instance, approved in approvals.items())
                or regular_file_inventory(prepared, allow_empty=True) != inventory):
            raise ValueError("SDK Maven original or verifier input changed during custody")
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, allow_empty=True,
                             expected_inventory=inventory)
    return {"product": "sdk", "signedIndexSha256": pins["index"],
            "packages": records, "files": inventory}
