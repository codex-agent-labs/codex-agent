"""Join SDK candidate packages to independently approved K/R/S identities.

This is an offline semantic check after official custody and exact-byte Phase-11
forwarding. It does not authenticate those transports or approve publication.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import sys
import zipfile
from urllib.parse import quote

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci.sdk_candidate_admission import candidate_object_root, verify_sdk_candidate_join
from ci.sdk_completion import verify_completed_parity_archive
from ci.products.aggregate import validate_sdk_compatibility
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_integer, require_semver, require_sha256,
    sha256_bytes, sha256_file,
)
from ci.products.registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from ci.products.restore import (
    _verified_object_snapshot, memoized_file_inventory as regular_file_inventory,
    object_relative_path, verification_scoped,
)
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
_PARITY_PINS = {"archiveSha256", "archiveBytes", "phaseIdentitiesSha256"}


# Fixed, reviewed public products/targets. Only the literal binary URL/checksum
# may vary. No Swift evaluation: computed values, comments hiding declarations,
# extra targets or conditional syntax require an explicit source-contract review.
_PUBLIC_SWIFT_STRUCTURE = "sha256:8c1a2cd0051e80b7f307d088ec249031cdfc164bfd0e065e62de8a2f792957c2"
_PUBLIC_SWIFT_BINARY = re.compile(
    rb'\.binaryTarget\(\s*name:\s*"CodexAgent",\s*'
    rb'url:\s*"([^"\\\r\n]+)",\s*checksum:\s*"([0-9a-f]{64})"\s*\)')


def verify_public_swift_declaration(raw: bytes, receipt: dict, *, sdk_version: str) -> dict:
    """Pure declaration check only: no source, receipt or public-release authority.

    Both callers separately bind raw to the exact P input and current source.
    The complete join / live native owner authenticates the supplied P receipt.
    """
    require_semver(sdk_version, "Public Swift SDK version")
    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024:
        raise ValueError("Public Swift manifest exceeds its fixed source bound")
    matches = list(_PUBLIC_SWIFT_BINARY.finditer(raw))
    if len(matches) != 1:
        raise ValueError("Public Swift manifest requires one unambiguous literal binary target")
    match = matches[0]
    structure = raw[:match.start()] + b"<CodexAgent binary target>" + raw[match.end():]
    if sha256_bytes(structure) != _PUBLIC_SWIFT_STRUCTURE:
        raise ValueError("Public Swift manifest differs from the reviewed public structure")
    if ([receipt.get(name) for name in ("product", "component", "phase", "target")] !=
            ["sdk", "sdk-ios", "package", "ios"] or receipt["productVersion"] != sdk_version):
        raise ValueError("Public Swift manifest requires the exact SDK iOS package")
    name = f"CodexAgent-{sdk_version}.xcframework.zip"
    archive = [row for row in receipt["outputs"] if row["relativePath"] == "outputs/apple/" + name]
    checksum = [row for row in receipt["outputs"] if row["relativePath"] == "outputs/apple/" + name + ".sha256"]
    if len(archive) != 1 or len(checksum) != 1:
        raise ValueError("Public Swift package lacks unique archive/checksum records")
    archive, checksum = archive[0], checksum[0]
    digest = require_sha256(archive["sha256"], "Public Swift archive").removeprefix("sha256:")
    if (archive["kind"] != "apple" or checksum["kind"] != "apple"
            or type(archive["bytes"]) is not int or archive["bytes"] <= 0
            or type(checksum["bytes"]) is not int or checksum["bytes"] != 65
            or checksum["sha256"] != sha256_bytes((digest + "\n").encode("ascii"))):
        raise ValueError("Public Swift package checksum record differs from the exact archive")
    tag = "sdk/v" + sdk_version
    url = "https://github.com/codex-agent-labs/codex-agent/releases/download/" + quote(tag, safe="") + "/" + name
    if match.group(1) != url.encode("ascii") or match.group(2) != digest.encode("ascii"):
        raise ValueError("Public Swift manifest differs from the planned SDK URL/checksum")
    return {"manifestSha256": sha256_bytes(raw), "releaseTag": tag, "assetUrl": url,
            "packageBuildKey": receipt["buildKey"],
            "packageReceiptSha256": sha256_bytes(canonical_json_bytes(receipt)),
            "archive": archive, "checksum": checksum}


def verify_candidate_public_swift_source(repository: Path, receipt: dict, *,
        expected_commit: str, expected_tree: str, sdk_version: str) -> dict:
    """Bind landed public metadata to an already authenticated iOS P receipt.

    This consumes no archive/member and grants no receipt authority. The normal
    forwarder's complete join supplies this exact receipt within its live session.
    """
    from ci.sdk_catalog_promotion_caller import _landed_commit
    from ci.sdk_phase11_bytes import _landed_tree

    require_semver(sdk_version, "Public Swift SDK version")
    if any(type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None
           for value in (expected_commit, expected_tree)):
        raise ValueError("Public Swift source requires exact approved commit/tree")
    if (_landed_commit(repository) != expected_commit or _landed_tree(repository) != expected_tree):
        raise ValueError("Public Swift source differs from approved landed commit/tree")
    raw = git_regular_blob_bytes(repository, expected_commit, "Package.swift", max_bytes=16 * 1024)
    if read_regular_file_bytes(repository / "Package.swift", max_bytes=16 * 1024,
                               reject_symlink_parents=True) != raw:
        raise ValueError("Public Swift source is not the landed Git blob")
    row = {"relativePath": "Package.swift", "bytes": len(raw), "sha256": sha256_bytes(raw)}
    if [item for item in receipt["inputs"]["inventory"] if item["relativePath"] == "Package.swift"] != [row]:
        raise ValueError("Public Swift source differs from its authenticated package input")
    declaration = verify_public_swift_declaration(raw, receipt, sdk_version=sdk_version)
    if (_landed_commit(repository) != expected_commit or _landed_tree(repository) != expected_tree
            or read_regular_file_bytes(repository / "Package.swift", max_bytes=16 * 1024,
                                       reject_symlink_parents=True) != raw):
        raise ValueError("Public Swift source changed during the candidate join")
    return {"sourceCommit": expected_commit, "sourceTree": expected_tree, **declaration}


def _selection(value: dict) -> tuple[dict, dict, dict]:
    selected = require_exact_keys(value, {"schemaVersion", "joinPins", "dependencies", "parity"},
                                  "SDK candidate semantic selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 2:
        raise ValueError("Unsupported SDK candidate semantic selection schema")
    pins = require_exact_keys(selected["joinPins"], _JOIN, "SDK candidate join pins")
    dependencies = require_exact_keys(selected["dependencies"], _DEPENDENCIES,
                                      "SDK candidate dependency pins")
    for field in ("contractVersion", "runtimeVersion"):
        require_semver(dependencies[field], f"SDK candidate {field}")
    for field in ("contractDigest", "runtimeManifestSha256", "sdkCompatibilitySha256"):
        require_sha256(dependencies[field], f"SDK candidate {field}")
    parity = require_exact_keys(selected["parity"], _PARITY_PINS, "SDK candidate Phase-10 parity pins")
    require_integer(parity["archiveBytes"], "SDK candidate parity archive bytes", 1)
    for field in ("archiveSha256", "phaseIdentitiesSha256"):
        require_sha256(parity[field], "SDK candidate parity " + field)
    return pins, dependencies, parity


def verify_candidate_sdk_parity(archive, phase_identities, parity_pins, entries, object_pins):
    """Join prevalidated parity to exact original SDK objects without re-execution.

    The protected caller must independently approve the Phase-10 archive and
    complete phase-set digests, and authenticate the signed SDK index/object pins
    before calling. This is a content join, not a transport/signing authority.
    Original schema-6 mixed-producer receipts remain byte-identical; they are not
    routed through the legacy schema-4 single-producer writer or reader.
    """
    raw = read_regular_file_bytes(phase_identities, max_bytes=512 * 1024,
                                  reject_symlink_parents=True)
    if sha256_bytes(raw) != parity_pins["phaseIdentitiesSha256"]:
        raise ValueError("SDK candidate parity phase selection differs from S1048 approval")
    phases = require_array(load_canonical_json_bytes(raw), "SDK candidate parity phases")
    selected = {}
    for row in phases:
        if type(row) is not dict:
            raise ValueError("SDK candidate parity phase must be an object")
        identity = PhaseInstanceId(*(row.get(field) for field in
                                     ("product", "component", "phase", "target")))
        if identity not in PHASE_INSTANCE_IDS or identity in selected:
            raise ValueError("SDK candidate parity phase set is unknown or duplicated")
        for name in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(row.get(name), "SDK candidate parity " + name)
        selected[identity] = row
    sdk = {item for item in PHASE_INSTANCE_IDS if item.product == "sdk"}
    if set(selected) != set(PHASE_INSTANCE_IDS) or set(entries) != sdk or set(object_pins) != sdk:
        raise ValueError("SDK candidate parity lacks the exact complete product/SDK phase set")
    for identity in sdk:
        original = selected[identity]
        if (any(original[field] != entries[identity][field] for field in ("buildKey", "receiptSha256"))
                or any(original[field] != object_pins[identity][field]
                       for field in ("buildKey", "receiptSha256", "objectSha256"))):
            raise ValueError("SDK candidate parity differs from the exact signed SDK campaign objects")
    return verify_completed_parity_archive(archive, expected_phases=phases,
        expected_bytes=parity_pins["archiveBytes"], expected_sha256=parity_pins["archiveSha256"])


def _package_compatibility(archive: Path, entry: dict, object_sha256: str, sdk_version: str) -> bytes:
    """Read only the consumed member from an exact, fully verified object."""
    with _verified_object_snapshot(archive, build_key=entry["buildKey"],
            receipt_sha256=entry["receiptSha256"], object_sha256=object_sha256) as (snapshot, verified):
        receipt = verified["receipt"]
        outputs = [item for item in receipt["outputs"]
                   if item["relativePath"] == _RESOURCE and item["kind"] == "evidence"]
        if (len(outputs) != 1 or receipt["productVersion"] != sdk_version
                or any(receipt[field] != entry[field]
                       for field in ("product", "component", "phase", "target"))):
            raise ValueError("SDK candidate Maven package lacks exact compatibility evidence")
        size = outputs[0]["bytes"]
        if not 0 < size <= 16 * 1024 * 1024:
            raise ValueError("SDK candidate compatibility exceeds its size bound")
        with zipfile.ZipFile(snapshot) as zipped, zipped.open("stage/" + _RESOURCE) as member:
            raw = member.read(size + 1)
        if len(raw) != size or sha256_bytes(raw) != outputs[0]["sha256"]:
            raise ValueError("SDK candidate compatibility differs from original package receipt")
        return raw


@verification_scoped
def verify_sdk_candidate_semantics(promoted_catalog: Path, forwarded_objects: Path,
                                   forwarded_maven: Path, selection: dict, *,
                                   parity_archive: Path, parity_phase_identities: Path,
                                   use_promoted_objects: bool = False) -> dict:
    """Require exact original package resources to name selected Contract/Runtime."""
    require_no_signing_secret(os.environ)
    pins, dependencies, parity_pins = _selection(selection)
    joined = verify_sdk_candidate_join(
        promoted_catalog, forwarded_objects, forwarded_maven,
        use_promoted_objects=use_promoted_objects, **pins)
    object_root = candidate_object_root(promoted_catalog, forwarded_objects, use_promoted_objects)
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
    raw_pins = read_regular_file_bytes(Path(forwarded_objects) / "object-pins.json",
                                      max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw_pins) != pins["expected_object_pins_sha256"]:
        raise ValueError("SDK candidate object pins changed after authenticated join")
    objects = {PhaseInstanceId(*(row[field] for field in ("product", "component", "phase", "target"))): row
               for row in load_canonical_json_bytes(raw_pins)["objects"]}
    parity = verify_candidate_sdk_parity(parity_archive, parity_phase_identities,
                                         parity_pins, entries, objects)
    if not _PACKAGES <= entries.keys():
        raise ValueError("SDK candidate lacks the three exact Maven package objects")
    originals = regular_file_inventory(forwarded_objects)
    catalog_files = regular_file_inventory(promoted_catalog) if use_promoted_objects else None
    contents = []
    for instance in sorted(_PACKAGES):
        entry = entries[instance]
        archive = object_root / object_relative_path(entry["buildKey"], entry["receiptSha256"])
        contents.append(_package_compatibility(archive, entry, objects[instance]["objectSha256"],
                                               pins["expected_sdk_version"]))
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
    if (regular_file_inventory(forwarded_objects) != originals
            or use_promoted_objects and regular_file_inventory(promoted_catalog) != catalog_files):
        raise ValueError("SDK candidate original objects changed during semantic join")
    return {**joined, "admitted": False, "contractDigest": dependencies["contractDigest"],
            "runtimeManifestSha256": dependencies["runtimeManifestSha256"],
            "sdkCompatibilitySha256": dependencies["sdkCompatibilitySha256"],
            "parity": parity}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--use-promoted-objects", action="store_true")
    for name in ("promoted-catalog", "forwarded-objects", "forwarded-maven", "selection",
                 "parity-archive", "parity-phase-identities"):
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
        load_canonical_json_bytes(raw), parity_archive=args.parity_archive,
        parity_phase_identities=args.parity_phase_identities,
        use_promoted_objects=args.use_promoted_objects)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
