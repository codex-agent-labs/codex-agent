"""Capture exact release-attested Contract bytes as external Phase-10 evidence.

This records an already-authenticated handoff; it neither signs product bytes
nor establishes protected-run, publication, or landed-tree authority. The
protected caller must pin these captured inventory/keyring bytes against its
trusted Git and Phase-10 control, not treat this helper as standalone trust.
"""

from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any

from .contract_attestation import verify_contract_attestation
from .inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, sha256_bytes,
    snapshot_regular_tree, write_canonical_json,
)
from .signatures import load_keyring, public_key_path


_PHASES = ("binary", "package", "validation", "metadata")


def _handoff_stem(files: list[dict[str, Any]]) -> str:
    names = [record["relativePath"] for record in files
             if record["relativePath"].endswith(".attestation.json")]
    if len(names) != 1 or "/" in names[0] or not names[0].startswith("codex-agent-contract-"):
        raise ValueError("Contract handoff must contain one root attestation")
    stem = names[0].removesuffix(".attestation.json")
    expected = {f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig",
                "public-key.pub", "execution-closure/contract-execution-closure.json",
                "execution-closure/execution/contract-execution.zip",
                *(f"execution-closure/receipts/{phase}.json" for phase in _PHASES)}
    if {record["relativePath"] for record in files} != expected:
        raise ValueError("Contract Phase-10 handoff file inventory is not exact")
    return stem


def capture_contract_phase10_inventory(
    handoff: Path, keyring: Path, keys_directory: Path, destination: Path,
) -> dict[str, Any]:
    """Verify and retain one exact Contract handoff and its verifier key bytes.

    The protected caller must independently authenticate the source upload,
    pin the captured inventory and keyring to trusted Git/Phase-10 control,
    and bind its validation tree. This snapshot is not that authorization.
    """
    handoff, keyring, keys_directory, destination = map(
        Path, (handoff, keyring, keys_directory, destination),
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Phase-10 inventory destination must not exist")
    output = destination.resolve(strict=False)
    for source in (handoff, keyring, keys_directory):
        resolved = source.resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Contract Phase-10 inventory output overlaps an input")

    with tempfile.TemporaryDirectory(prefix="contract-phase10-inventory-") as temporary:
        prepared = Path(temporary).resolve() / "evidence"
        original_handoff = regular_file_inventory(handoff)
        captured = prepared / "handoff"
        snapshot_regular_tree(handoff, captured)
        if regular_file_inventory(captured) != original_handoff:
            raise ValueError("Captured Contract handoff differs from its original inventory")
        keyring_bytes = read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        policy = load_keyring(keyring, keys_directory)
        captured_keyring = prepared / "policy/keyring.json"
        captured_keyring.parent.mkdir(parents=True)
        captured_keyring.write_bytes(keyring_bytes)
        captured_keys = prepared / "policy/keys"
        captured_keys.mkdir()
        records = ([policy["activeKey"]] if policy["activeKey"] else []) + policy["retiredKeys"]
        original_keys = {}
        for record in records:
            source = public_key_path(keys_directory, record["keyId"])
            raw = read_regular_file_bytes(source, max_bytes=1024 * 1024, reject_symlink_parents=True)
            original_keys[record["keyId"]] = raw
            (captured_keys / f"{record['keyId']}.pub").write_bytes(raw)
        if load_keyring(captured_keyring, captured_keys) != policy:
            raise ValueError("Captured Contract verifier policy differs from its source")

        stem = _handoff_stem(original_handoff)
        _, receipt, attestation = verify_contract_attestation(
            captured / f"{stem}.zip", captured / "execution-closure/receipts/metadata.json",
            captured / f"{stem}.attestation.json", captured / f"{stem}.attestation.sig",
            captured / "public-key.pub", required_trust_domain="release",
            keyring=captured_keyring, keys_directory=captured_keys,
        )
        record = {
            "schemaVersion": 1,
            "product": "contract",
            "contractVersion": attestation["contractVersion"],
            "metadataBuildKey": receipt["buildKey"],
            "handoffFiles": regular_file_inventory(captured),
            "verifierKeyring": {"bytes": len(keyring_bytes), "sha256": sha256_bytes(keyring_bytes)},
            "verifierKeys": regular_file_inventory(captured_keys),
        }
        write_canonical_json(prepared / "inventory.json", record)
        if (regular_file_inventory(handoff) != original_handoff
                or read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != keyring_bytes
                or any(read_regular_file_bytes(public_key_path(keys_directory, key_id),
                                                max_bytes=1024 * 1024,
                                                reject_symlink_parents=True) != raw
                       for key_id, raw in original_keys.items())):
            raise ValueError("Contract Phase-10 inventory inputs changed during capture")
        publish_regular_tree(prepared, destination)
    return record


def verify_contract_phase10_inventory(directory: Path) -> dict[str, Any]:
    """Recheck every retained byte against the recorded and signed identities."""
    directory = Path(directory)
    value = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
        directory / "inventory.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True,
    )), {"schemaVersion", "product", "contractVersion", "metadataBuildKey", "handoffFiles",
         "verifierKeyring", "verifierKeys"}, "Contract Phase-10 inventory")
    if value["schemaVersion"] != 1 or value["product"] != "contract":
        raise ValueError("Contract Phase-10 inventory identity is invalid")
    handoff = directory / "handoff"
    policy = directory / "policy"
    if regular_file_inventory(handoff) != value["handoffFiles"] or \
            regular_file_inventory(policy / "keys") != value["verifierKeys"]:
        raise ValueError("Contract Phase-10 inventory files changed")
    keyring_bytes = read_regular_file_bytes(policy / "keyring.json", max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
    if {"bytes": len(keyring_bytes), "sha256": sha256_bytes(keyring_bytes)} != value["verifierKeyring"]:
        raise ValueError("Contract Phase-10 verifier keyring changed")
    stem = _handoff_stem(value["handoffFiles"])
    key_policy = load_keyring(policy / "keyring.json", policy / "keys")
    records = ([key_policy["activeKey"]] if key_policy["activeKey"] else []) + key_policy["retiredKeys"]
    if {record["relativePath"] for record in value["verifierKeys"]} != \
            {f"{record['keyId']}.pub" for record in records}:
        raise ValueError("Contract Phase-10 verifier key inventory is not exact")
    _, receipt, attestation = verify_contract_attestation(
        handoff / f"{stem}.zip", handoff / "execution-closure/receipts/metadata.json",
        handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
        handoff / "public-key.pub",
        required_trust_domain="release", keyring=policy / "keyring.json",
        keys_directory=policy / "keys",
    )
    if value["contractVersion"] != attestation["contractVersion"] or \
            value["metadataBuildKey"] != receipt["buildKey"]:
        raise ValueError("Contract Phase-10 inventory differs from its attested receipt")
    if {record["relativePath"] for record in regular_file_inventory(directory)} != {
        "inventory.json", "policy/keyring.json", *(f"policy/keys/{record['relativePath']}"
                                                 for record in value["verifierKeys"]),
        *(f"handoff/{record['relativePath']}" for record in value["handoffFiles"]),
    }:
        raise ValueError("Contract Phase-10 inventory has extra files")
    return value
