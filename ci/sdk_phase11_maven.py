"""Build-free forwarding of the exact Phase-10 SDK Maven signed handoff.

Official upload custody and these independent S1048 pins are caller inputs. This
helper neither elects a hosted upload nor regenerates sidecars or signatures.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_semver,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.sdk_phase10_maven_caller import _SECRETS, verify_sdk_phase10_maven_handoff
from ci.sdk_phase11_bytes import _landed_tree


def forward_verified_sdk_phase10_maven(
    signed: Path, destination: Path, *, landed_repository: Path,
    expected_signed_inventory_sha256: str, expected_preparation_sha256: str,
    expected_control_sha256: str, expected_pgp_key_sha256: str,
    expected_signed_index_sha256: str, expected_sdk_version: str,
    expected_source_commit: str, expected_source_tree: str,
    expected_validation_tree: str,
) -> dict:
    """Preserve every signed handoff byte only after exact offline admission."""
    require_no_signing_secret(os.environ)
    if _SECRETS & set(os.environ):
        raise ValueError("SDK Maven candidate must not receive a signing secret")
    if {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
            "ACTIONS_ID_TOKEN_REQUEST_TOKEN"} & set(os.environ):
        raise ValueError("SDK Maven candidate must not receive an observation token")
    for label, value in (
        ("signed handoff inventory", expected_signed_inventory_sha256),
        ("preparation", expected_preparation_sha256),
        ("control", expected_control_sha256),
        ("PGP public key", expected_pgp_key_sha256),
        ("signed index", expected_signed_index_sha256),
    ):
        require_sha256(value, "SDK Phase-10 " + label)
    require_semver(expected_sdk_version, "SDK Phase-10 SDK version")
    for label, value in (
        ("source commit", expected_source_commit),
        ("source tree", expected_source_tree),
        ("validation tree", expected_validation_tree),
    ):
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
            raise ValueError("SDK Phase-10 " + label + " must be a full Git object ID")
    if expected_source_tree != expected_validation_tree:
        raise ValueError("SDK signed Maven source tree differs from Phase-10 validation")
    signed = Path(signed).resolve(strict=True)
    landed = Path(landed_repository).resolve(strict=True)
    destination = Path(destination)
    output = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Maven candidate destination already exists")
    if any(output == path or output in path.parents or path in output.parents
           for path in (signed, landed)):
        raise ValueError("SDK Maven candidate output overlaps a protected input")
    if _landed_tree(landed) != expected_validation_tree:
        raise ValueError("SDK Maven candidate landed tree differs from Phase-10 validation")
    original = regular_file_inventory(signed)
    if sha256_bytes(canonical_json_bytes(original)) != expected_signed_inventory_sha256:
        raise ValueError("SDK Maven signed handoff differs from independent S1048 inventory")
    admitted = verify_sdk_phase10_maven_handoff(signed,
        expected_preparation_sha256=expected_preparation_sha256,
        expected_control_sha256=expected_control_sha256,
        expected_pgp_key_sha256=expected_pgp_key_sha256)
    if (admitted["signedFilesSha256"] != expected_signed_inventory_sha256
            or admitted["signedIndexSha256"] != expected_signed_index_sha256
            or len(admitted["uploadSources"]) != 3
            or {row["component"] for row in admitted["uploadSources"]}
                != {"sdk-core", "sdk-android", "sdk-ios"}):
        raise ValueError("SDK Maven signed handoff differs from selected three-package release")
    raw_index = read_regular_file_bytes(signed / "custody/campaign/product-index.json",
                                        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw_index) != expected_signed_index_sha256:
        raise ValueError("SDK Maven signed index differs from independent S1048 digest")
    index = load_canonical_json_bytes(raw_index)
    context = index["context"]
    if (context.get("kind") != "pull-request"
            or context.get("commit") != expected_source_commit
            or context.get("tree") != expected_source_tree
            or {entry["productVersion"] for entry in index["entries"]}
                != {expected_sdk_version}):
        raise ValueError("SDK Maven signed index differs from approved source or SDK release")
    with tempfile.TemporaryDirectory(prefix="sdk-phase11-maven-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        snapshot_regular_tree(signed, prepared)
        if (regular_file_inventory(prepared) != original
                or regular_file_inventory(signed) != original
                or _landed_tree(landed) != expected_validation_tree):
            raise ValueError("SDK Maven originals changed before exact-byte forwarding")
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, expected_inventory=original)
    return {"product": "sdk", "sdkVersion": expected_sdk_version,
            "signedIndexSha256": expected_signed_index_sha256,
            "signedInventorySha256": expected_signed_inventory_sha256,
            "uploadSources": admitted["uploadSources"], "files": original}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("signed", "destination", "landed-repository"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-signed-inventory-sha256", "expected-preparation-sha256",
                 "expected-control-sha256", "expected-pgp-key-sha256",
                 "expected-signed-index-sha256", "expected-sdk-version",
                 "expected-source-commit", "expected-source-tree",
                 "expected-validation-tree"):
        parser.add_argument("--" + name, required=True)
    options = vars(parser.parse_args(argv))
    try:
        result = forward_verified_sdk_phase10_maven(**options)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
