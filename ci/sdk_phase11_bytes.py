"""Verify and forward the exact Phase-10 SDK signed-index capture offline.

Independent S1048 pins and the landed-tree identity are caller inputs. This
forwards the campaign index and its evidence, not the 61 referenced phase objects.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci.receipt import safe_extract
from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_sha256, sha256_bytes, sha256_file, snapshot_regular_tree,
    verified_zip_contents,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.sdk_phase10_release_index_admission import _EVIDENCE_MEMBERS, _ZIP_LIMITS


def _inventory_digest(directory: Path) -> str:
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(directory)))


def _landed_tree(repository: Path) -> str:
    root = repository.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("SDK candidate checkout must be a directory")
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel", "HEAD^{tree}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError("SDK candidate checkout has no landed Git tree")
    lines = result.stdout.splitlines()
    if len(lines) != 2 or Path(lines[0]).resolve(strict=True) != root or not re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", lines[1],
    ):
        raise ValueError("SDK candidate checkout is not the exact Git root")
    return lines[1]


def forward_verified_sdk_phase10_bytes(
    protected_capture: Path, destination: Path, *, landed_repository: Path,
    expected_inventory_sha256: str, expected_index_sha256: str,
    expected_signature_sha256: str, expected_authority_sha256: str,
    expected_signed_upload_sha256: str, expected_authority_upload_sha256: str,
    expected_authority_transport_sha256: str, expected_keyring_sha256: str,
    expected_keys_inventory_sha256: str, expected_sdk_version: str,
    expected_source_commit: str, expected_source_tree: str,
    expected_validation_tree: str,
) -> dict:
    """Copy one independently pinned Phase-10 capture without signing or repacking."""
    require_no_signing_secret(os.environ)
    for label, digest in (
        ("capture inventory", expected_inventory_sha256),
        ("signed index", expected_index_sha256),
        ("index signature", expected_signature_sha256),
        ("campaign authority", expected_authority_sha256),
        ("signed upload", expected_signed_upload_sha256),
        ("authority upload", expected_authority_upload_sha256),
        ("authority transport", expected_authority_transport_sha256),
        ("keyring", expected_keyring_sha256),
        ("public keys inventory", expected_keys_inventory_sha256),
    ):
        require_sha256(digest, f"SDK Phase-10 {label}")
    for label, revision in (
        ("source commit", expected_source_commit),
        ("source tree", expected_source_tree),
        ("validation tree", expected_validation_tree),
    ):
        if type(revision) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", revision) is None:
            raise ValueError(f"SDK Phase-10 {label} must be a full Git object ID")
    source = Path(protected_capture).resolve(strict=True)
    destination = Path(destination)
    landed = Path(landed_repository).resolve(strict=True)
    output = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK candidate destination already exists")
    if any(output == path or output in path.parents or path in output.parents
           for path in (source, landed)):
        raise ValueError("SDK candidate destination overlaps a verified input")
    if _landed_tree(landed) != expected_validation_tree:
        raise ValueError("SDK candidate landed tree differs from Phase-10 validation")
    if _inventory_digest(source) != expected_inventory_sha256:
        raise ValueError("SDK Phase-10 capture differs from independently selected bytes")

    with tempfile.TemporaryDirectory(prefix="sdk-phase11-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        snapshot_regular_tree(source, prepared)
        if _inventory_digest(prepared) != expected_inventory_sha256:
            raise ValueError("SDK Phase-10 capture changed during candidate snapshot")
        pair = prepared / "signed-pair"
        evidence = prepared / "replay-evidence"
        keyring = evidence / "product-signing-keys.json"
        keys = evidence / "keys"
        authority_file = evidence / "sdk-campaign-authority.json"
        authority_transport = evidence / "authority-transport.json"
        signed_upload = prepared / "official-upload.zip"
        authority_upload = evidence / "authority-upload.zip"
        if ({row["relativePath"] for row in regular_file_inventory(prepared)} != {
                "official-upload.zip", "transport.json",
                "signed-pair/product-index.json", "signed-pair/product-index.sig",
                *(f"replay-evidence/{name}" for name in _EVIDENCE_MEMBERS),
                *(f"replay-evidence/keys/{row['relativePath']}"
                  for row in regular_file_inventory(keys)),
        }):
            raise ValueError("SDK Phase-10 capture has unexpected or missing files")
        for path, digest in (
            (pair / "product-index.json", expected_index_sha256),
            (pair / "product-index.sig", expected_signature_sha256),
            (authority_file, expected_authority_sha256),
            (signed_upload, expected_signed_upload_sha256),
            (authority_upload, expected_authority_upload_sha256),
            (authority_transport, expected_authority_transport_sha256),
            (keyring, expected_keyring_sha256),
        ):
            if sha256_file(path) != digest:
                raise ValueError(f"SDK Phase-10 {path.name} differs from independent approval")
        if _inventory_digest(keys) != expected_keys_inventory_sha256:
            raise ValueError("SDK Phase-10 public keys differ from independent approval")
        with held_pinned_sdk_campaign_authority(authority_file, expected_authority_sha256) as authority:
            original = authority["completedCatalogPin"]["producer"]
            if (original["commit"] != expected_source_commit
                    or original["tree"] != expected_source_tree
                    or original["tree"] != expected_validation_tree
                    or authority["sdkVersion"] != expected_sdk_version):
                raise ValueError("SDK authority differs from selected source or release identity")
            for kind in ("election", "semantic"):
                for family, digest in authority[f"{kind}Sha256"].items():
                    if sha256_file(evidence / f"{kind}-{family}.json") != digest:
                        raise ValueError("SDK Phase-10 policy differs from approved authority")
            index, raw = verify_release_product_index(
                SignedProductIndex(pair / "product-index.json", pair / "product-index.sig"),
                keyring_path=keyring, keys_directory=keys,
            )
            if (index["trustDomain"] != "release"
                    or index["producer"] != original
                    or index["repository"] != original["repository"]
                    or index["context"] != {"kind": "pull-request",
                        "pullRequest": original["pullRequest"],
                        **{name: original[name] for name in (
                            "commit", "tree", "runId", "runAttempt")}}
                    or {entry["productVersion"] for entry in index["entries"]} != {expected_sdk_version}
                    or sha256_bytes(raw) != expected_index_sha256):
                raise ValueError("SDK signed campaign index differs from approved authority")
            transport = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
                prepared / "transport.json", max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True)),
                {"schemaVersion", "originalProducer", "recordProducer", "recordObservation", "artifact"},
                "SDK signed-index transport")
            if (transport["schemaVersion"] != 1 or transport["originalProducer"] != original
                    or transport["artifact"].get("digest") != expected_signed_upload_sha256):
                raise ValueError("SDK signed-index transport differs from approved upload")
            authority_record = load_canonical_json_bytes(read_regular_file_bytes(
                authority_transport, max_bytes=1024 * 1024, reject_symlink_parents=True))
            if (authority_record["originalProducer"] != original
                    or authority_record["artifactSha256"] != expected_authority_upload_sha256
                    or authority_record["authoritySha256"] != expected_authority_sha256
                    or authority_record["authorityProducer"] == transport["recordProducer"]):
                raise ValueError("SDK authority transport differs from approved campaign")
            for archive, members, limit in (
                (signed_upload, {"product-index.json", "product-index.sig"}, _ZIP_LIMITS),
                (authority_upload, {"sdk-campaign-authority.json"}, {
                    "require_sorted": False, "max_archive_bytes": 2 * 1024 * 1024,
                    "max_central_directory_bytes": 16 * 1024, "max_members": 1,
                    "max_entry_bytes": 1024 * 1024, "max_total_bytes": 1024 * 1024,
                    "max_compression_ratio": 100,
                }),
            ):
                inventory, _, _ = verified_zip_contents(archive, retained_paths=(), **limit)
                if {row["relativePath"] for row in inventory} != members:
                    raise ValueError("SDK Phase-10 official upload has unexpected members")
                with tempfile.TemporaryDirectory(prefix="sdk-phase11-zip-") as extracted_root:
                    extracted = Path(extracted_root).resolve()
                    safe_extract(archive, extracted)
                    reference = pair if archive == signed_upload else evidence
                    if any(read_regular_file_bytes(extracted / name,
                            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
                            != read_regular_file_bytes(reference / name,
                                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
                           for name in members):
                        raise ValueError("SDK Phase-10 official upload differs from retained bytes")
        inventory = regular_file_inventory(prepared)
        if (_inventory_digest(source) != expected_inventory_sha256
                or _inventory_digest(prepared) != expected_inventory_sha256
                or _landed_tree(landed) != expected_validation_tree):
            raise ValueError("SDK Phase-10 candidate inputs changed during verification")
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, expected_inventory=inventory)
        return {"product": "sdk", "sdkVersion": expected_sdk_version,
                "indexSha256": expected_index_sha256,
                "signatureSha256": expected_signature_sha256,
                "phase10InventorySha256": expected_inventory_sha256,
                "candidateInventory": inventory}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("protected-capture", "destination", "landed-repository"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "expected-inventory-sha256", "expected-index-sha256",
        "expected-signature-sha256", "expected-authority-sha256",
        "expected-signed-upload-sha256", "expected-authority-upload-sha256",
        "expected-authority-transport-sha256", "expected-keyring-sha256",
        "expected-keys-inventory-sha256", "expected-sdk-version",
        "expected-source-commit", "expected-source-tree", "expected-validation-tree",
    ):
        parser.add_argument(f"--{name}", required=True)
    result = forward_verified_sdk_phase10_bytes(**vars(parser.parse_args(argv)))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
