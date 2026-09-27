"""Forward 61 exact SDK phase objects only with independent Phase-10 object pins.

The signed campaign index omits enclosing object-ZIP digests. The caller must
provide an S1048-approved canonical pin file and its independent SHA-256; this
module cannot infer either from the signed index or claim hosted custody.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci.sdk_phase11_bytes import forward_verified_sdk_phase10_bytes, _landed_tree
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, require_string, sha256_bytes, snapshot_regular_tree,
)
from ci.products.registry import PhaseInstanceId
from ci.products.restore import object_relative_path, verify_object
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signing_isolation import require_no_signing_secret


_PIN_KEYS = {"schemaVersion", "signedIndexSha256", "objects"}
_OBJECT_KEYS = {"product", "component", "phase", "target", "buildKey",
                "receiptSha256", "objectSha256", "relativePath"}


def forward_verified_sdk_phase10_objects(
    protected_capture: Path, objects_root: Path, object_pins: Path,
    destination: Path, *, expected_object_pins_sha256: str,
    **index_handoff_pins,
) -> dict:
    """Atomically forward original object ZIPs and the already-verified index capture."""
    import os
    require_no_signing_secret(os.environ)
    pins_sha = require_sha256(expected_object_pins_sha256,
                              "SDK Phase-10 object pin file")
    pins_path = Path(object_pins).resolve(strict=True)
    objects = Path(objects_root).resolve(strict=True)
    capture = Path(protected_capture).resolve(strict=True)
    destination = Path(destination)
    output = destination.resolve(strict=False)
    landed = Path(index_handoff_pins["landed_repository"]).resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK object candidate destination already exists")
    if any(output == path or output in path.parents or path in output.parents
           for path in (pins_path, objects, capture, landed)):
        raise ValueError("SDK object candidate destination overlaps a verified input")
    raw_pins = read_regular_file_bytes(pins_path, max_bytes=64 * 1024,
                                       reject_symlink_parents=True)
    if sha256_bytes(raw_pins) != pins_sha:
        raise ValueError("SDK object pins differ from independent S1048 approval")
    pins = require_exact_keys(load_canonical_json_bytes(raw_pins), _PIN_KEYS,
                              "SDK Phase-10 object pins")
    if (type(pins["schemaVersion"]) is not int or pins["schemaVersion"] != 1
            or pins["signedIndexSha256"] != require_sha256(
                index_handoff_pins["expected_index_sha256"], "SDK signed index digest")):
        raise ValueError("SDK object pins target another signed campaign index")
    rows = pins["objects"]
    if type(rows) is not list or len(rows) != len(SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK object pins require every exact 61-phase object")
    selected = {}
    order = []
    for row in rows:
        row = require_exact_keys(row, _OBJECT_KEYS, "SDK Phase-10 object pin")
        instance = PhaseInstanceId(*(require_string(row[field], f"SDK object {field}") for field in (
            "product", "component", "phase", "target")))
        if instance not in SDK_CAMPAIGN_INSTANCES or instance in selected:
            raise ValueError("SDK object pins contain an unknown or duplicate phase")
        if (row["relativePath"] != object_relative_path(
                row["buildKey"], row["receiptSha256"])):
            raise ValueError("SDK object pin path differs from immutable phase identity")
        require_sha256(row["objectSha256"], "SDK phase object digest")
        selected[instance] = row
        order.append(instance)
    if order != sorted(SDK_CAMPAIGN_INSTANCES):
        raise ValueError("SDK object pins must be sorted by exact phase identity")

    with tempfile.TemporaryDirectory(prefix="sdk-phase11-objects-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        prepared.mkdir()
        index_capture = prepared / "signed-campaign"
        forward_verified_sdk_phase10_bytes(capture, index_capture,
                                           **index_handoff_pins)
        evidence = index_capture / "replay-evidence"
        index, _ = verify_release_product_index(SignedProductIndex(
            index_capture / "signed-pair/product-index.json",
            index_capture / "signed-pair/product-index.sig"),
            keyring_path=evidence / "product-signing-keys.json",
            keys_directory=evidence / "keys")
        entries = {PhaseInstanceId(*(entry[field] for field in (
            "product", "component", "phase", "target"))): entry
            for entry in index["entries"]}
        if (len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES)
                or set(entries) != SDK_CAMPAIGN_INSTANCES):
            raise ValueError("SDK signed campaign index lacks exact 61-phase membership")
        expected_files = []
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            row, entry = selected[instance], entries[instance]
            if any(row[field] != entry[field] for field in (
                    "product", "component", "phase", "target", "buildKey", "receiptSha256")):
                raise ValueError("SDK object pin differs from signed receipt identity")
            archive = objects / row["relativePath"]
            verified = verify_object(archive, build_key=entry["buildKey"],
                receipt_sha256=entry["receiptSha256"],
                object_sha256=row["objectSha256"])
            receipt = verified["receipt"]
            if (receipt["outputs"] != entry["outputs"]
                    or receipt["productVersion"] != entry["productVersion"]
                    or sha256_bytes(verified["receiptBytes"]) != entry["receiptSha256"]):
                raise ValueError("SDK object differs from signed output and receipt identity")
            expected_files.append({"relativePath": row["relativePath"],
                "bytes": verified["objectBytes"], "sha256": row["objectSha256"]})
        expected_files.sort(key=lambda record: record["relativePath"])
        if regular_file_inventory(objects) != expected_files:
            raise ValueError("SDK object source differs from exact 61-object inventory")
        snapshot_regular_tree(objects, prepared / "objects")
        if regular_file_inventory(prepared / "objects") != expected_files:
            raise ValueError("SDK phase objects changed during candidate capture")
        (prepared / "object-pins.json").write_bytes(raw_pins)
        prepared_inventory = regular_file_inventory(prepared)
        if (read_regular_file_bytes(pins_path, max_bytes=64 * 1024,
                reject_symlink_parents=True) != raw_pins
                or regular_file_inventory(objects) != expected_files
                or _landed_tree(landed) != index_handoff_pins["expected_validation_tree"]):
            raise ValueError("SDK candidate inputs changed before publication")
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination,
                             expected_inventory=prepared_inventory)
        return {"product": "sdk", "objectCount": len(expected_files),
                "signedIndexSha256": pins["signedIndexSha256"],
                "objectPinsSha256": pins_sha,
                "candidateInventory": prepared_inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("protected-capture", "objects-root", "object-pins",
                 "destination", "landed-repository"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "expected-object-pins-sha256", "expected-inventory-sha256",
        "expected-index-sha256", "expected-signature-sha256",
        "expected-authority-sha256", "expected-signed-upload-sha256",
        "expected-authority-upload-sha256", "expected-authority-transport-sha256",
        "expected-keyring-sha256", "expected-keys-inventory-sha256",
        "expected-sdk-version", "expected-source-commit", "expected-source-tree",
        "expected-validation-tree",
    ):
        parser.add_argument(f"--{name}", required=True)
    options = vars(parser.parse_args(argv))
    result = forward_verified_sdk_phase10_objects(
        options.pop("protected_capture"), options.pop("objects_root"),
        options.pop("object_pins"), options.pop("destination"),
        expected_object_pins_sha256=options.pop("expected_object_pins_sha256"),
        **options,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
