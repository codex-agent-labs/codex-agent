"""Compose a promoted Contract catalog from four caller-elected originals.

This is an offline byte/receipt closure, not an S1048 election or an official
upload observer. The protected caller must independently authenticate every
phase pin and its original upload before invoking it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from typing import Mapping

from ci.product_reuse import stage_release_catalog
from ci.products.contract_attestation import verify_contract_attestation
from ci.products.index import (
    IndexEntrySource, build_product_index, release_attested_contract_admission,
    write_signed_product_index,
)
from ci.products.runtime_aggregate_handoff import _public_policy
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from ci.products.receipt import validate_phase_receipt
from ci.products.restore import object_relative_path, verify_object
from ci.products.signatures import load_keyring, require_active_release_key


_PHASES = ("binary", "package", "validation", "metadata")
_PIN_FIELDS = {"buildKey", "receiptSha256", "objectSha256", "artifactPath", "producer"}


def stage_promoted_contract_catalog(
    handoff: Path, phase_objects: Mapping[str, Path], phase_pins: Mapping[str, dict],
    destination: Path, *, repository: str, context: dict, producer: dict,
    keyring: Path, keys_directory: Path, private_key: Path,
) -> dict:
    """Sign only a new index; copy exact original objects and attestation bytes.

    ``phase_pins`` is independent protected S1048 input, never read from a
    downloaded object or reconstructed from the attested closure. Its producer
    field preserves the selected original receipt producer. This function does
    not establish which official upload supplied an object.
    """
    if set(phase_objects) != set(_PHASES) or set(phase_pins) != set(_PHASES):
        raise ValueError("Promoted Contract catalog requires exactly four elected phases")
    if context.get("kind") != "promoted-main":
        raise ValueError("Contract catalog requires promoted-main context")
    destination = Path(destination).absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract catalog destination already exists")
    originals = [Path(handoff), Path(keyring), Path(keys_directory), Path(private_key),
                 *(Path(path) for path in phase_objects.values())]
    output = destination.resolve(strict=False)
    for path in originals:
        source = path.resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("Contract catalog output overlaps an original input")
    handoff_before = regular_file_inventory(handoff)
    object_before = {phase: read_regular_file_bytes(Path(phase_objects[phase]),
        max_bytes=1024 * 1024 * 1024, reject_symlink_parents=True) for phase in _PHASES}
    keyring_before = read_regular_file_bytes(Path(keyring), max_bytes=16 * 1024 * 1024,
                                             reject_symlink_parents=True)
    keys_before = regular_file_inventory(keys_directory)
    pins_before = canonical_json_bytes(dict(phase_pins))

    with tempfile.TemporaryDirectory(prefix="promoted-contract-catalog-") as temporary:
        root = Path(temporary).resolve()
        captured = root / "catalog"
        captured.mkdir()
        retained = root / "handoff"
        snapshot_regular_tree(handoff, retained)
        if regular_file_inventory(retained) != handoff_before:
            raise ValueError("Contract release handoff changed during capture")
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, root / "policy")
        pinned_keyring = root / "policy/product-signing-keys.json"
        pinned_keys = root / "policy/keys"
        key_policy = load_keyring(pinned_keyring, pinned_keys)
        active, public_key = require_active_release_key(key_policy, pinned_keys)
        signing = {name: key_policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        names = [row["relativePath"] for row in handoff_before if row["relativePath"].endswith(".attestation.json")]
        if len(names) != 1 or "/" in names[0]:
            raise ValueError("Contract handoff must contain one root attestation")
        stem = names[0].removesuffix(".attestation.json")
        expected_handoff = {f"{stem}.zip", f"{stem}.attestation.json",
            f"{stem}.attestation.sig", "public-key.pub",
            "execution-closure/contract-execution-closure.json",
            "execution-closure/execution/contract-execution.zip",
            *(f"execution-closure/receipts/{phase}.json" for phase in _PHASES)}
        if {item["relativePath"] for item in handoff_before} != expected_handoff:
            raise ValueError("Contract release handoff has missing or unexpected bytes")
        payload = retained / f"{stem}.zip"
        metadata_receipt = retained / "execution-closure/receipts/metadata.json"
        attestation = retained / f"{stem}.attestation.json"
        signature = retained / f"{stem}.attestation.sig"
        _, verified_metadata, _ = verify_contract_attestation(
            payload, metadata_receipt, attestation, signature,
            retained / "public-key.pub", required_trust_domain="release",
            keyring=pinned_keyring, keys_directory=pinned_keys,
        )
        # The complete signed closure verifies all four receipts, not just the
        # metadata receipt. The original handoff is not re-signed or repacked.
        snapshot_regular_tree(retained / "execution-closure", captured / "execution-closure")
        (captured / attestation.name).write_bytes(read_regular_file_bytes(attestation))
        (captured / signature.name).write_bytes(read_regular_file_bytes(signature))
        sources = []
        for phase in _PHASES:
            pin = require_exact_keys(phase_pins[phase], _PIN_FIELDS, f"Contract {phase} S1048 pin")
            key = require_sha256(pin["buildKey"], f"Contract {phase} build key")
            digest = require_sha256(pin["receiptSha256"], f"Contract {phase} receipt")
            object_digest = require_sha256(pin["objectSha256"], f"Contract {phase} object")
            original_receipt = read_regular_file_bytes(
                retained / f"execution-closure/receipts/{phase}.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
            )
            receipt = validate_phase_receipt(load_canonical_json_bytes(original_receipt))
            if (receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) != \
                    ("contract", "contract", phase, "common") or \
                    receipt["buildKey"] != key or sha256_bytes(original_receipt) != digest or \
                    receipt["producer"] != pin["producer"] or receipt["productVersion"] != verified_metadata["productVersion"]:
                raise ValueError(f"Contract {phase} original receipt differs from S1048 pin")
            if not isinstance(pin["artifactPath"], str) or sum(
                    item["relativePath"] == pin["artifactPath"] for item in receipt["outputs"]) != 1:
                raise ValueError(f"Contract {phase} distinguished output differs from original receipt")
            target = captured / object_relative_path(key, digest)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(object_before[phase])
            verified = verify_object(target, build_key=key, receipt_sha256=digest,
                                     object_sha256=object_digest)
            if verified["receiptBytes"] != original_receipt:
                raise ValueError(f"Contract {phase} object rewrites its original receipt")
            source = IndexEntrySource(original_receipt, pin["artifactPath"])
            if receipt["trustDomain"] == "development":
                source = replace(source, release_admission=release_attested_contract_admission(
                    source, payload=payload, metadata_receipt=metadata_receipt,
                    attestation=attestation, signature=signature,
                    public_key=retained / "public-key.pub", keyring=pinned_keyring,
                    keys_directory=pinned_keys,
                ))
            sources.append(source)
        arguments = dict(repository=repository, context=context, producer=producer,
                         trust_domain="release", signing=signing, stable_history=None)
        index = build_product_index(sources, **arguments)

        def unchanged() -> None:
            if (regular_file_inventory(handoff) != handoff_before
                    or any(read_regular_file_bytes(Path(phase_objects[phase]),
                        max_bytes=1024 * 1024 * 1024, reject_symlink_parents=True) != object_before[phase]
                        for phase in _PHASES)
                    or read_regular_file_bytes(Path(keyring), max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True) != keyring_before
                    or regular_file_inventory(keys_directory) != keys_before
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024,
                        reject_symlink_parents=True) != policy_bytes[name]
                        for name, path in policy_paths.items())
                    or canonical_json_bytes(dict(phase_pins)) != pins_before):
                raise ValueError("Contract originals or protected selection changed")

        unchanged()
        write_signed_product_index(sources, **arguments, private_key=private_key,
            public_key=public_key, manifest_path=captured / "product-index.json")
        stage_release_catalog(captured, root / "ready", repository=repository,
            source="promoted-main", keyring=pinned_keyring, keys_directory=pinned_keys)
        unchanged()
        publish_regular_tree(root / "ready", destination, allow_empty=True)
    return index
