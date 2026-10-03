"""Join independently selected SDK Phase-10 and promoted bytes without rebuilding.

The protected caller must authenticate official uploads and run the existing
Phase-11 exact-byte forwarders first. This reader cannot elect an S1048 pin.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_semver, require_sha256,
    sha256_bytes, sha256_file,
)
from ci.products.restore import object_relative_path
from ci.products.sdk_campaign_index import verify_release_sdk_campaign_objects
from ci.products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from ci.products.signing_isolation import require_no_signing_secret
from ci.products.registry import PhaseInstanceId


_REPOSITORY = "codex-agent-labs/codex-agent"
_TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN",
           "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
_SECRETS = {"SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD",
            "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"}
_OBJECT_PIN_FIELDS = {"product", "component", "phase", "target", "buildKey",
                      "receiptSha256", "objectSha256", "relativePath"}


def verify_sdk_candidate_join(
    promoted_catalog: Path, forwarded_objects: Path, forwarded_maven: Path, *,
    expected_promoted_inventory_sha256: str, expected_promoted_index_sha256: str,
    expected_promoted_signature_sha256: str, expected_phase10_index_sha256: str,
    expected_phase10_signature_sha256: str, expected_keyring_sha256: str,
    expected_keys_inventory_sha256: str, expected_object_pins_sha256: str,
    expected_maven_inventory_sha256: str, expected_sdk_version: str,
    expected_validation_tree: str,
) -> dict:
    """Require one exact 62-object identity across promoted, campaign and Maven."""
    require_no_signing_secret(os.environ)
    if _SECRETS & os.environ.keys():
        raise ValueError("SDK candidate join must not receive a signing secret")
    if _TOKENS & os.environ.keys():
        raise ValueError("SDK candidate join must not receive an observation token")
    pins = {
        "promoted inventory": expected_promoted_inventory_sha256,
        "promoted index": expected_promoted_index_sha256,
        "promoted signature": expected_promoted_signature_sha256,
        "Phase-10 index": expected_phase10_index_sha256,
        "Phase-10 signature": expected_phase10_signature_sha256,
        "keyring": expected_keyring_sha256,
        "public keys": expected_keys_inventory_sha256,
        "object pins": expected_object_pins_sha256,
        "Maven inventory": expected_maven_inventory_sha256,
    }
    for label, digest in pins.items():
        require_sha256(digest, f"SDK candidate {label}")
    require_semver(expected_sdk_version, "SDK candidate version")
    if (type(expected_validation_tree) is not str or len(expected_validation_tree) != 40
            or any(c not in "0123456789abcdef" for c in expected_validation_tree)):
        raise ValueError("SDK candidate requires an exact validated Git tree")
    promoted_catalog = Path(promoted_catalog)
    forwarded_objects = Path(forwarded_objects)
    forwarded_maven = Path(forwarded_maven)
    promoted_files = regular_file_inventory(promoted_catalog)
    objects_files = regular_file_inventory(forwarded_objects)
    maven_files = regular_file_inventory(forwarded_maven)
    if (sha256_bytes(canonical_json_bytes(promoted_files)) != expected_promoted_inventory_sha256
            or sha256_bytes(canonical_json_bytes(maven_files)) != expected_maven_inventory_sha256):
        raise ValueError("SDK candidate input differs from independent S1048 inventory")
    campaign = forwarded_objects / "signed-campaign"
    evidence = campaign / "replay-evidence"
    keyring = evidence / "product-signing-keys.json"
    keys = evidence / "keys"
    if (sha256_file(keyring) != expected_keyring_sha256
            or sha256_bytes(canonical_json_bytes(regular_file_inventory(keys)))
                != expected_keys_inventory_sha256):
        raise ValueError("SDK candidate public-key policy differs from S1048 approval")
    maven_policy = forwarded_maven / "custody/campaign"
    if (sha256_file(maven_policy / "product-signing-keys.json")
            != expected_keyring_sha256
            or regular_file_inventory(maven_policy / "keys") != regular_file_inventory(keys)):
        raise ValueError("SDK Maven custody public-key policy differs from Phase-10 campaign")
    promoted_pair = SignedProductIndex(promoted_catalog / "product-index.json",
                                       promoted_catalog / "product-index.sig")
    campaign_pair = SignedProductIndex(campaign / "signed-pair/product-index.json",
                                       campaign / "signed-pair/product-index.sig")
    for pair, index_digest, signature_digest in (
        (promoted_pair, expected_promoted_index_sha256, expected_promoted_signature_sha256),
        (campaign_pair, expected_phase10_index_sha256, expected_phase10_signature_sha256),
    ):
        if sha256_file(pair.manifest) != index_digest or sha256_file(pair.signature) != signature_digest:
            raise ValueError("SDK candidate signed index differs from S1048 approval")
    promoted, _ = verify_release_product_index(promoted_pair, keyring_path=keyring,
                                                keys_directory=keys)
    original, _ = verify_release_product_index(campaign_pair, keyring_path=keyring,
                                                keys_directory=keys)
    if (promoted["repository"] != _REPOSITORY or original["repository"] != _REPOSITORY
            or promoted["trustDomain"] != "release" or original["trustDomain"] != "release"
            or promoted["context"]["kind"] != "promoted-main"
            or original["context"]["kind"] != "pull-request"
            or promoted["context"]["tree"] != expected_validation_tree
            or original["context"]["tree"] != expected_validation_tree
            or promoted["entries"] != original["entries"]
            or len(promoted["entries"]) != len(SDK_CAMPAIGN_INSTANCES)
            or {entry["productVersion"] for entry in promoted["entries"]}
                != {expected_sdk_version}):
        raise ValueError("SDK promoted catalog and Phase-10 campaign differ")
    entries = {PhaseInstanceId(*(entry[field] for field in (
        "product", "component", "phase", "target"))): entry
        for entry in promoted["entries"]}
    if set(entries) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK candidate lacks the exact 62 campaign phases")
    pin_path = forwarded_objects / "object-pins.json"
    raw_pins = read_regular_file_bytes(pin_path, max_bytes=64 * 1024,
                                       reject_symlink_parents=True)
    if sha256_bytes(raw_pins) != expected_object_pins_sha256:
        raise ValueError("SDK candidate object pins differ from S1048 approval")
    selected = require_exact_keys(load_canonical_json_bytes(raw_pins),
                                  {"schemaVersion", "signedIndexSha256", "objects"},
                                  "SDK candidate object pins")
    if (type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1
            or selected["signedIndexSha256"] != expected_phase10_index_sha256
            or type(selected["objects"]) is not list
            or len(selected["objects"]) != len(SDK_CAMPAIGN_INSTANCES)):
        raise ValueError("SDK candidate object pins lack exact campaign identity")
    expected_objects = []
    object_paths = {}
    seen_instances = set()
    for row in selected["objects"]:
        row = require_exact_keys(row, _OBJECT_PIN_FIELDS, "SDK candidate object pin")
        instance = PhaseInstanceId(*(row[field] for field in (
            "product", "component", "phase", "target")))
        if instance not in entries or instance in seen_instances:
            raise ValueError("SDK candidate object pins contain an unknown or duplicate phase")
        seen_instances.add(instance)
        entry = entries[instance]
        if (any(row[field] != entry[field] for field in (
                "product", "component", "phase", "target", "buildKey", "receiptSha256"))
                or row["relativePath"] != object_relative_path(
                    entry["buildKey"], entry["receiptSha256"])):
            raise ValueError("SDK candidate object pin differs from signed campaign")
        require_sha256(row["objectSha256"], "SDK candidate object digest")
        relative = row["relativePath"]
        source = forwarded_objects / "objects" / relative
        promoted_source = promoted_catalog / relative
        if (sha256_file(source) != row["objectSha256"]
                or sha256_file(promoted_source) != row["objectSha256"]):
            raise ValueError("SDK candidate original object differs across releases")
        object_paths[entry["buildKey"]] = promoted_source
        expected_objects.append({"relativePath": relative, "bytes": source.stat().st_size,
                                 "sha256": row["objectSha256"]})
    expected_objects.sort(key=lambda row: row["relativePath"])
    if (regular_file_inventory(forwarded_objects / "objects") != expected_objects
            or {row["relativePath"] for row in promoted_files}
                != {"product-index.json", "product-index.sig", *(row["relativePath"]
                    for row in expected_objects)}):
        raise ValueError("SDK candidate original object inventory is incomplete")
    verify_release_sdk_campaign_objects(promoted, object_paths, repository=_REPOSITORY)
    if (sha256_file(forwarded_maven / "custody/campaign/product-index.json")
            != expected_phase10_index_sha256
            or sha256_file(forwarded_maven / "custody/campaign/product-index.sig")
                != expected_phase10_signature_sha256):
        raise ValueError("SDK Maven handoff names a different signed campaign")
    if (regular_file_inventory(promoted_catalog) != promoted_files
            or regular_file_inventory(forwarded_objects) != objects_files
            or regular_file_inventory(forwarded_maven) != maven_files):
        raise ValueError("SDK candidate inputs changed during admission")
    return {"product": "sdk", "sdkVersion": expected_sdk_version,
            "validationTree": expected_validation_tree,
            "promotedIndexSha256": expected_promoted_index_sha256,
            "phase10IndexSha256": expected_phase10_index_sha256,
            "originalObjectCount": len(expected_objects)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("promoted-catalog", "forwarded-objects", "forwarded-maven"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("promoted-inventory-sha256", "promoted-index-sha256",
                 "promoted-signature-sha256", "phase10-index-sha256",
                 "phase10-signature-sha256", "keyring-sha256",
                 "keys-inventory-sha256", "object-pins-sha256",
                 "maven-inventory-sha256", "sdk-version", "validation-tree"):
        parser.add_argument("--expected-" + name, required=True)
    result = verify_sdk_candidate_join(**vars(parser.parse_args(argv)))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
