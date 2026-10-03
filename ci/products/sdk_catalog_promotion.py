"""Build-free SDK promoted-main catalog composition from protected originals.

This verifies content and release admission, not official upload or landed-tree
authority. The protected caller must pin and authenticate both transports first.
"""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import tempfile
from typing import Mapping

from ci.product_reuse import stage_release_catalog

from .index import (
    IndexEntrySource, SignedProductIndex, _mint_release_admission,
    build_product_index, verify_release_product_index, write_signed_product_index,
)
from .inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    require_exact_keys, require_sha256, sha256_bytes, sha256_file,
)
from .receipt import validate_phase_receipt, validate_producer
from .registry import PhaseInstanceId
from .restore import _snapshot_archive, object_relative_path, restore_object, verify_object
from .runtime_aggregate_handoff import _public_policy
from .sdk_campaign_index import verify_signed_sdk_campaign_originals
from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from .signatures import load_keyring, require_active_release_key


_PIN_FIELDS = {"buildKey", "receiptSha256", "objectSha256", "artifactPath", "producer"}
_OBSERVATION_TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN",
                       "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}


def stage_promoted_sdk_catalog(
    original_objects: Mapping[PhaseInstanceId, Path],
    phase_pins: Mapping[PhaseInstanceId, dict],
    signed_campaign: SignedProductIndex,
    destination: Path,
    *,
    repository: str,
    campaign_context: dict,
    expected_index_sha256: str,
    expected_signature_sha256: str,
    context: dict,
    producer: dict,
    keyring: Path,
    keys_directory: Path,
    private_key: Path,
) -> dict:
    """Re-index the exact admitted 62 objects, leaving original receipts intact.

    Pins and the signed pair must be independently elected protected inputs. A
    caller-supplied local path or this result does not prove an official upload.
    """
    if _OBSERVATION_TOKENS & os.environ.keys():
        raise ValueError("SDK catalog signer must not receive an observation token")
    if set(original_objects) != SDK_CAMPAIGN_INSTANCES or set(phase_pins) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("Promoted SDK catalog requires exactly 62 elected originals and pins")
    if not isinstance(signed_campaign, SignedProductIndex):
        raise ValueError("SDK campaign requires a signed product-index pair")
    current = validate_producer(producer)
    if context.get("kind") != "promoted-main" or current["event"] != "push":
        raise ValueError("SDK promotion requires a push promoted-main context")
    index_pin = require_sha256(expected_index_sha256, "Protected SDK index digest")
    signature_pin = require_sha256(expected_signature_sha256, "Protected SDK signature digest")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK catalog destination already exists")
    originals = [*map(Path, original_objects.values()), Path(signed_campaign.manifest),
                 Path(signed_campaign.signature), Path(keyring), Path(keys_directory), Path(private_key)]
    output = destination.resolve(strict=False)
    for path in originals:
        source = path.resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("SDK catalog output overlaps an original input")
    pin_bytes = canonical_json_bytes([
        {"instance": [instance.product, instance.component, instance.phase, instance.target],
         "pin": phase_pins[instance]} for instance in sorted(SDK_CAMPAIGN_INSTANCES)
    ])
    signed_bytes = read_regular_file_bytes(signed_campaign.manifest, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True)
    signature_bytes = read_regular_file_bytes(signed_campaign.signature, max_bytes=1024 * 1024,
                                              reject_symlink_parents=True)
    if sha256_bytes(signed_bytes) != index_pin or sha256_bytes(signature_bytes) != signature_pin:
        raise ValueError("SDK signed campaign differs from protected digest pins")

    with tempfile.TemporaryDirectory(prefix="promoted-sdk-catalog-") as temporary:
        root = Path(temporary).resolve()
        pair = root / "campaign"
        pair.mkdir()
        (pair / "product-index.json").write_bytes(signed_bytes)
        (pair / "product-index.sig").write_bytes(signature_bytes)
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, root / "policy")
        pinned_keyring = root / "policy/product-signing-keys.json"
        pinned_keys = root / "policy/keys"
        key_policy = load_keyring(pinned_keyring, pinned_keys)
        active, public_key = require_active_release_key(key_policy, pinned_keys)
        signing = {name: key_policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        campaign, raw = verify_release_product_index(
            SignedProductIndex(pair / "product-index.json", pair / "product-index.sig"),
            keyring_path=pinned_keyring, keys_directory=pinned_keys)
        if (raw != signed_bytes or campaign["repository"] != repository
                or campaign["context"] != campaign_context
                or campaign_context.get("kind") != "pull-request"):
            raise ValueError("SDK signed campaign differs from elected PR context")
        entries = {PhaseInstanceId(*(entry[field] for field in (
            "product", "component", "phase", "target"))): entry for entry in campaign["entries"]}
        if len(campaign["entries"]) != len(SDK_CAMPAIGN_INSTANCES) or set(entries) != SDK_CAMPAIGN_INSTANCES:
            raise ValueError("SDK signed campaign lacks an exact 62-phase index")

        captured = root / "catalog"
        captured.mkdir()
        sources, envelopes, archives, stages = {}, {}, {}, {}
        original_digests = {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            pin = require_exact_keys(phase_pins[instance], _PIN_FIELDS, "Protected SDK phase pin")
            entry = entries[instance]
            key = require_sha256(pin["buildKey"], "SDK build key")
            receipt_digest = require_sha256(pin["receiptSha256"], "SDK receipt digest")
            object_digest = require_sha256(pin["objectSha256"], "SDK object digest")
            if (entry["buildKey"] != key or entry["receiptSha256"] != receipt_digest
                    or entry["artifactName"] != pin["artifactPath"]):
                raise ValueError("SDK signed index differs from protected phase pin")
            archive = Path(original_objects[instance])
            object_path = captured / object_relative_path(key, receipt_digest)
            object_path.parent.mkdir(parents=True, exist_ok=True)
            if _snapshot_archive(archive, object_path)["sha256"] != object_digest:
                raise ValueError("SDK original object differs from protected object pin")
            verified = verify_object(object_path, build_key=key, receipt_sha256=receipt_digest,
                                     object_sha256=object_digest)
            receipt_bytes = verified["receiptBytes"]
            receipt = validate_phase_receipt(verified["receipt"])
            if (receipt["producer"] != validate_producer(pin["producer"])
                    or receipt["trustDomain"] != "development"
                    or tuple(receipt[field] for field in ("product", "component", "phase", "target"))
                    != (instance.product, instance.component, instance.phase, instance.target)):
                raise ValueError("SDK original producer or phase differs from protected pin")
            stage = root / "stages" / str(position)
            restored = restore_object(object_path, stage, build_key=key,
                                      receipt_sha256=receipt_digest, object_sha256=object_digest)
            if restored["receiptBytes"] != receipt_bytes:
                raise ValueError("SDK original receipt changed while restoring stage")
            sources[instance] = IndexEntrySource(receipt_bytes, pin["artifactPath"])
            envelopes[instance] = {name: verified[name] for name in (
                "receipt", "receiptBytes", "objectSha256")}
            envelopes[instance]["receiptSha256"] = receipt_digest
            archives[instance] = object_path
            stages[instance] = stage
            original_digests[instance] = object_digest

        verify_signed_sdk_campaign_originals(
            SignedProductIndex(pair / "product-index.json", pair / "product-index.sig"),
            repository=repository, context=campaign_context, keyring_path=pinned_keyring,
            keys_directory=pinned_keys, sources=sources, envelopes=envelopes,
            archives=archives, stages=stages)
        admitted = []
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            source = sources[instance]
            receipt = validate_phase_receipt(envelopes[instance]["receipt"])
            admitted.append(replace(source, release_admission=_mint_release_admission(
                source, receipt, source.receipt_bytes,
                (instance.product, instance.component, instance.phase, instance.target))))
        arguments = dict(repository=repository, context=context, producer=current,
                         trust_domain="release", signing=signing, stable_history=None)
        index = build_product_index(admitted, **arguments)

        def unchanged() -> None:
            if (canonical_json_bytes([{"instance": [instance.product, instance.component,
                    instance.phase, instance.target], "pin": phase_pins[instance]}
                    for instance in sorted(SDK_CAMPAIGN_INSTANCES)]) != pin_bytes
                    or read_regular_file_bytes(signed_campaign.manifest, max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True) != signed_bytes
                    or read_regular_file_bytes(signed_campaign.signature, max_bytes=1024 * 1024,
                                               reject_symlink_parents=True) != signature_bytes
                    or any(sha256_file(original_objects[instance], reject_symlink_parents=True)
                        != original_digests[instance] for instance in SDK_CAMPAIGN_INSTANCES)
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024,
                        reject_symlink_parents=True) != policy_bytes[name]
                        for name, path in policy_paths.items())):
                raise ValueError("SDK protected originals or signing policy changed")

        unchanged()
        write_signed_product_index(admitted, **arguments, private_key=private_key,
                                   public_key=public_key, manifest_path=captured / "product-index.json")
        stage_release_catalog(captured, root / "ready", repository=repository,
                              source="promoted-main", keyring=pinned_keyring,
                              keys_directory=pinned_keys)
        unchanged()
        publish_regular_tree(root / "ready", destination, allow_empty=True)
    return index
