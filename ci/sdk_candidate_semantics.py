"""Join SDK candidate packages to independently approved K/R/S identities.

This is an offline semantic check after official custody and exact-byte Phase-11
forwarding. It does not authenticate those transports or approve publication.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.sdk_candidate_admission import verify_sdk_candidate_join
from ci.products.aggregate import validate_sdk_compatibility
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_semver, require_sha256, sha256_bytes, sha256_file,
)
from ci.products.registry import PhaseInstanceId
from ci.products.restore import object_relative_path, restore_object
from ci.products.signing_isolation import require_no_signing_secret


_JOIN = {"expected_promoted_inventory_sha256", "expected_promoted_index_sha256",
         "expected_promoted_signature_sha256", "expected_phase10_index_sha256",
         "expected_phase10_signature_sha256", "expected_keyring_sha256",
         "expected_keys_inventory_sha256", "expected_object_pins_sha256",
         "expected_maven_inventory_sha256", "expected_sdk_version",
         "expected_validation_tree"}
_DEPENDENCIES = {"contractVersion", "contractDigest", "runtimeVersion",
                 "runtimeManifestSha256", "sdkCompatibilitySha256"}
_PACKAGES = {
    PhaseInstanceId("sdk", "sdk-core", "package", "common"),
    PhaseInstanceId("sdk", "sdk-android", "package", "android"),
    PhaseInstanceId("sdk", "sdk-ios", "package", "ios"),
}
_RESOURCE = "outputs/evidence/sdk-compatibility.json"


def _selection(value: dict) -> tuple[dict, dict]:
    selected = require_exact_keys(value, {"schemaVersion", "joinPins", "dependencies"},
                                  "SDK candidate semantic selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate semantic selection schema")
    pins = require_exact_keys(selected["joinPins"], _JOIN, "SDK candidate join pins")
    dependencies = require_exact_keys(selected["dependencies"], _DEPENDENCIES,
                                      "SDK candidate dependency pins")
    for field in ("contractVersion", "runtimeVersion"):
        require_semver(dependencies[field], f"SDK candidate {field}")
    for field in ("contractDigest", "runtimeManifestSha256", "sdkCompatibilitySha256"):
        require_sha256(dependencies[field], f"SDK candidate {field}")
    return pins, dependencies


def verify_sdk_candidate_semantics(promoted_catalog: Path, forwarded_objects: Path,
                                   forwarded_maven: Path, selection: dict) -> dict:
    """Require exact original package resources to name selected Contract/Runtime."""
    require_no_signing_secret(os.environ)
    pins, dependencies = _selection(selection)
    joined = verify_sdk_candidate_join(
        promoted_catalog, forwarded_objects, forwarded_maven, **pins)
    campaign = Path(forwarded_objects) / "signed-campaign"
    evidence = campaign / "replay-evidence"
    index, raw_index = verify_release_product_index(
        SignedProductIndex(campaign / "signed-pair/product-index.json",
                           campaign / "signed-pair/product-index.sig"),
        keyring_path=evidence / "product-signing-keys.json",
        keys_directory=evidence / "keys")
    if (sha256_bytes(raw_index) != pins["expected_phase10_index_sha256"]
            or sha256_file(campaign / "signed-pair/product-index.sig") !=
                pins["expected_phase10_signature_sha256"]):
        raise ValueError("SDK candidate semantic index differs from S1048 approval")
    entries = {PhaseInstanceId(*(entry[field] for field in (
        "product", "component", "phase", "target"))): entry
        for entry in index["entries"]}
    if not _PACKAGES <= entries.keys():
        raise ValueError("SDK candidate lacks the three exact Maven package objects")
    originals = regular_file_inventory(forwarded_objects)
    contents = []
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-semantics-") as temporary:
        root = Path(temporary).resolve()
        for instance in sorted(_PACKAGES):
            entry = entries[instance]
            archive = (Path(forwarded_objects) / "objects" /
                       object_relative_path(entry["buildKey"], entry["receiptSha256"]))
            stage = root / instance.component
            restored = restore_object(archive, stage,
                build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
            receipt = restored["receipt"]
            evidence_outputs = [item for item in receipt["outputs"]
                if item["relativePath"] == _RESOURCE and item["kind"] == "evidence"]
            if (len(evidence_outputs) != 1 or receipt["productVersion"] != pins["expected_sdk_version"]
                    or receipt["phase"] != "package" or receipt["component"] != instance.component
                    or receipt["target"] != instance.target):
                raise ValueError("SDK candidate Maven package lacks exact compatibility evidence")
            raw = read_regular_file_bytes(stage / _RESOURCE, max_bytes=16 * 1024 * 1024,
                                          reject_symlink_parents=True)
            if sha256_bytes(raw) != evidence_outputs[0]["sha256"]:
                raise ValueError("SDK candidate compatibility differs from original package receipt")
            contents.append(raw)
    if (len(set(contents)) != 1
            or sha256_bytes(contents[0]) != dependencies["sdkCompatibilitySha256"]):
        raise ValueError("SDK candidate packages differ from approved compatibility bytes")
    compatibility = validate_sdk_compatibility(load_canonical_json_bytes(contents[0]))
    if (compatibility["sdkVersion"] != pins["expected_sdk_version"]
            or compatibility["contract"] != {
                "version": dependencies["contractVersion"],
                "digest": dependencies["contractDigest"]}
            or compatibility["runtime"]["requiredContractDigest"] != dependencies["contractDigest"]
            or compatibility["runtime"]["defaultRuntimeVersion"] != dependencies["runtimeVersion"]
            or compatibility["runtime"]["defaultManifestSha256"] !=
                dependencies["runtimeManifestSha256"]):
        raise ValueError("SDK candidate K/R/S dependency identity differs from approval")
    if regular_file_inventory(forwarded_objects) != originals:
        raise ValueError("SDK candidate original objects changed during semantic join")
    return {**joined, "admitted": False, "contractDigest": dependencies["contractDigest"],
            "runtimeManifestSha256": dependencies["runtimeManifestSha256"],
            "sdkCompatibilitySha256": dependencies["sdkCompatibilitySha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("promoted-catalog", "forwarded-objects", "forwarded-maven", "selection"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    args = parser.parse_args(argv)
    raw = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(args.expected_selection_sha256,
            "independent SDK semantic selection"):
        raise ValueError("SDK candidate semantic selection differs from S1048 approval")
    result = verify_sdk_candidate_semantics(
        args.promoted_catalog, args.forwarded_objects, args.forwarded_maven,
        load_canonical_json_bytes(raw))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
