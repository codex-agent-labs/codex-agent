"""Compose existing SDK candidate custody and offline gates; never build or sign.

The protected workflow supplies independently approved S1048 controls before
executing this pinned source. One catalog serves all62 objects; the Runtime
input is only the original five-library upload, not aggregate/variant bundles.
"""

from __future__ import annotations

import argparse
from inspect import signature
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci import product_reuse, sdk_candidate_catalog as custody
from ci import sdk_candidate_maven_transport as maven
from ci.sdk_candidate_admission import _SECRETS, _TOKENS
from ci.sdk_candidate_join import join_sdk_candidate
from ci.sdk_candidate_semantics import _selection as semantic_selection
from ci.sdk_catalog_promotion_caller import (
    _index_carrier_pins, _landed_commit, _object_pins, capture_official_sdk_phase10_index,
)
from ci.sdk_phase11_bytes import _landed_tree, forward_verified_sdk_phase10_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_semver, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.restore import bounded_verify, memoized_file_inventory, verification_session
from ci.products.runtime_library_authorization import _LIBRARY_PATHS
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


def _read(path, limit=64 * 1024):
    return read_regular_file_bytes(path, max_bytes=limit, reject_symlink_parents=True)


def _timed(item):
    name, operation = item
    start = time.monotonic_ns()
    result = operation()
    return {"input": name, "elapsedNs": time.monotonic_ns() - start, "result": result}


def _selection(value):
    selected = require_exact_keys(value, {"schemaVersion", "trustedSourceCommit", "landedCommit",
        "catalog", "index", "maven", "mavenCaptureInventorySha256", "parity", "runtime", "join"},
        "SDK candidate workflow selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate workflow selection")
    for name in ("trustedSourceCommit", "landedCommit"):
        if type(selected[name]) is not str or re.fullmatch(r"[0-9a-f]{40}", selected[name]) is None:
            raise ValueError("SDK candidate requires exact Git commits")
    catalog = custody._selection(selected["catalog"])
    parity = custody._parity_selection(selected["parity"])
    custody._runtime_selection(selected["runtime"])
    mvn = maven._selection(selected["maven"])
    index = require_exact_keys(selected["index"], {"producer", "carrierPins", "handoffPins"},
                               "SDK candidate index selection")
    carrier = _index_carrier_pins(index["carrierPins"], index["producer"])
    # Use the forwarder's exact interface, not a second handoff schema.
    handoff = require_exact_keys(index["handoffPins"], set(signature(
        forward_verified_sdk_phase10_bytes).parameters) - {
            "protected_capture", "destination", "landed_repository"}, "SDK candidate index handoff")
    join = require_exact_keys(selected["join"], {"schemaVersion", "sdk", "runtime"}, "SDK candidate join")
    if type(join["schemaVersion"]) is not int or join["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate join")
    pins, _, parity_pins = semantic_selection(join["sdk"])
    runtime = require_exact_keys(join["runtime"], {"inventorySha256", "rootPublicKeySha256"},
                                 "SDK candidate Runtime forwarding")
    for fields in (handoff, pins):
        for key, item in fields.items():
            if key.endswith("_sha256"):
                require_sha256(item, key)
            elif key == "expected_sdk_version":
                require_semver(item, key)
            elif type(item) is not str or re.fullmatch(r"[0-9a-f]{40}", item) is None:
                raise ValueError("SDK candidate requires exact Git identities")
    for key, digest in runtime.items():
        require_sha256(digest, key)
    require_sha256(selected["mavenCaptureInventorySha256"], "SDK candidate Maven capture")
    equalities = [
        (catalog["inventorySha256"], pins["expected_promoted_inventory_sha256"]),
        (catalog["indexSha256"], pins["expected_promoted_index_sha256"]),
        (catalog["signatureSha256"], pins["expected_promoted_signature_sha256"]),
        (handoff["expected_index_sha256"], pins["expected_phase10_index_sha256"]),
        (handoff["expected_signature_sha256"], pins["expected_phase10_signature_sha256"]),
        (carrier["captureInventorySha256"], handoff["expected_inventory_sha256"]),
        (index["producer"], mvn["producer"]),
        (carrier["trustedWorkflowSha"], mvn["trustedWorkflowSha"]),
        (mvn["signedInventorySha256"], pins["expected_maven_inventory_sha256"]),
        (mvn["phase11Pins"]["expected_signed_index_sha256"], handoff["expected_index_sha256"]),
        (handoff["expected_source_tree"], pins["expected_validation_tree"]),
        (catalog["producer"]["commit"], selected["landedCommit"]),
        (catalog["producer"]["tree"], pins["expected_validation_tree"]),
        (parity["artifactSha256"], parity_pins["archiveSha256"]),
        (parity["artifactBytes"], parity_pins["archiveBytes"]),
        (parity["phaseIdentitiesSha256"], parity_pins["phaseIdentitiesSha256"]),
    ]
    equalities.extend((handoff[key], pins[key]) for key in (
        "expected_sdk_version", "expected_validation_tree", "expected_keyring_sha256",
        "expected_keys_inventory_sha256"))
    equalities.extend((handoff[key], mvn["phase11Pins"][key]) for key in (
        "expected_sdk_version", "expected_source_commit", "expected_source_tree", "expected_validation_tree"))
    if any(left != right for left, right in equalities):
        raise ValueError("SDK candidate independent selections disagree")
    return selected


def _check_sources(selected, trusted, landed):
    tree = selected["join"]["sdk"]["joinPins"]["expected_validation_tree"]
    for path, commit in ((trusted, selected["trustedSourceCommit"]), (landed, selected["landedCommit"])):
        if _landed_commit(path) != commit or _landed_tree(path) != tree:
            raise ValueError("SDK candidate checkout differs from approved commit/tree")
        if subprocess.check_output(["git", "-C", str(path), "status", "--porcelain",
                                    "--untracked-files=no"], timeout=30):
            raise ValueError("SDK candidate checkout has tracked edits")


def capture(selected, workspace, landed, *, token):
    """Fresh official custody, concurrent independent inputs, one SDK catalog."""
    require_no_signing_secret(os.environ)
    if _SECRETS & os.environ.keys():
        raise ValueError("SDK candidate capture must not receive signing secrets")
    workspace.mkdir()  # Never overwrite a previous/partial capture.
    scratch, output = workspace / "capture", workspace / "candidate"
    scratch.mkdir()
    output.mkdir()
    (output / "parity").mkdir()
    index = selected["index"]
    operations = {
        "catalog": lambda: custody.capture_sdk_candidate_catalog(selected["catalog"], output / "catalog", token=token),
        "index": lambda: capture_official_sdk_phase10_index(index["producer"], index["carrierPins"],
            scratch / "index", landed_repository=landed, index_handoff_pins=index["handoffPins"],
            token=token, environ=os.environ),
        "maven": lambda: maven.capture_sdk_candidate_maven(selected["maven"], scratch / "maven", token=token),
        "parity": lambda: custody.capture_sdk_candidate_parity(selected["parity"],
            output / "parity/original.zip", output / "parity/controls", token=token),
        "runtime": lambda: custody.capture_sdk_candidate_runtime(selected["runtime"],
            scratch / "runtime.zip", scratch / "runtime-controls", token=token),
    }
    with verification_session(), product_reuse._ci_observation_batch(
            (os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_RUN_ATTEMPT")), share_nested=True):
        return bounded_verify(_timed, operations.items())


def _forward_runtime(selected, archive, landed, destination):
    """Extract the consumed libraries once; copy only the tiny root delegation."""
    files, _, identity = verified_zip_contents(archive, retained_paths=(),
        max_archive_bytes=custody._RUNTIME_LIMIT, max_members=512,
        max_entry_bytes=128 * 1024 * 1024, max_total_bytes=custody._RUNTIME_LIMIT, require_sorted=False)
    runtime = selected["runtime"]
    if (identity != {"bytes": runtime["artifactBytes"], "sha256": runtime["artifactSha256"]}
            or sha256_bytes(canonical_json_bytes(files)) != runtime["inventorySha256"]):
        raise ValueError("SDK candidate Runtime archive differs from approved upload")
    destination.mkdir()
    libraries = destination / "library-authorizations"
    safe_extract(archive, libraries)
    if memoized_file_inventory(libraries) != files:
        raise ValueError("SDK candidate Runtime extraction differs from approved inventory")
    root = _read(landed / "gradle/release/keys/sdk-runtime-root.pub", 4096)
    if sha256_bytes(root) != selected["join"]["runtime"]["rootPublicKeySha256"]:
        raise ValueError("SDK candidate root differs from independent approval")
    (destination / "sdk-runtime-root.pub").write_bytes(root)
    target = next(iter(_LIBRARY_PATHS))
    evidence = libraries / target / (Path(_LIBRARY_PATHS[target]).name + ".evidence")
    for row in memoized_file_inventory(evidence):
        if row["relativePath"] in {"runtime-library-authorization.json", "runtime-library-authorization.sig"}:
            continue
        path = destination / "root-delegation" / row["relativePath"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_read(evidence / row["relativePath"], 1024 * 1024))
    if sha256_file(archive, reject_symlink_parents=True) != runtime["artifactSha256"]:
        raise ValueError("SDK candidate Runtime archive changed during forwarding")


def forward(selected, workspace, landed, object_pins):
    """Token-free exact-byte forwarding followed by complete, unscoped admission."""
    require_no_signing_secret(os.environ)
    if (_TOKENS | _SECRETS) & os.environ.keys():
        raise ValueError("SDK candidate forwarding must not receive token or signing secret")
    scratch, output = workspace / "capture", workspace / "candidate"
    controls = output / "objects-control"
    controls.mkdir()
    (controls / "object-pins.json").write_bytes(object_pins)
    with verification_session():
        timings = bounded_verify(_timed, {
            "maven": lambda: maven.forward_sdk_candidate_maven(scratch / "maven", landed,
                output / "maven", selected["maven"],
                expected_capture_inventory_sha256=selected["mavenCaptureInventorySha256"]),
            "index": lambda: forward_verified_sdk_phase10_bytes(scratch / "index/phase10",
                controls / "signed-campaign", landed_repository=landed, **selected["index"]["handoffPins"]),
            "runtime": lambda: _forward_runtime(selected, scratch / "runtime.zip", landed, output / "runtime"),
        }.items())
        started = time.monotonic_ns()
        result = join_sdk_candidate(output / "catalog", controls, output / "maven", output / "runtime",
            selected["join"], parity_archive=output / "parity/original.zip",
            parity_phase_identities=output / "parity/controls/original-phase-identities.json",
            use_promoted_objects=True)
        join_elapsed = time.monotonic_ns() - started
        evidence = output / "evidence"
        evidence.mkdir(exist_ok=True)
        for name, path in (("index-transport", "index/transport.json"),
                           ("maven-transport", "maven/transport.json"),
                           ("runtime-transport", "runtime-controls/transport.json"),
                           ("runtime-library-inventory", "runtime-controls/library-inventory.json")):
            (evidence / (name + ".json")).write_bytes(_read(scratch / path, 16 * 1024 * 1024))
        return {**result, "forwarding": timings, "joinElapsedNs": join_elapsed}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("command", choices=("capture", "forward"))
    for name in ("selection", "object-pins", "workspace", "trusted-repository", "landed-repository"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    args = parser.parse_args(argv)
    started = time.monotonic_ns()
    raw = _read(args.selection)
    if sha256_bytes(raw) != require_sha256(args.expected_selection_sha256, "SDK candidate selection"):
        raise ValueError("SDK candidate workflow differs from independent S1048 selection")
    selected = _selection(load_canonical_json_bytes(raw))
    pins = selected["join"]["sdk"]["joinPins"]
    object_pins, _ = _object_pins(args.object_pins, pins["expected_object_pins_sha256"],
                                  pins["expected_phase10_index_sha256"])
    _check_sources(selected, args.trusted_repository, args.landed_repository)
    output = args.workspace.resolve(strict=False)
    for source in (args.selection, args.object_pins, args.trusted_repository, args.landed_repository):
        source = source.resolve(strict=True)
        if output == source or output in source.parents or source in output.parents:
            raise ValueError("SDK candidate workspace overlaps authority input")
    result = (capture(selected, args.workspace, args.landed_repository, token=os.environ["GITHUB_TOKEN"])
              if args.command == "capture" else
              forward(selected, args.workspace, args.landed_repository, object_pins))
    _check_sources(selected, args.trusted_repository, args.landed_repository)
    if _read(args.selection) != raw or _read(args.object_pins) != object_pins:
        raise ValueError("SDK candidate approved controls changed during execution")
    evidence = args.workspace / "candidate/evidence"
    evidence.mkdir(exist_ok=True)
    # External execution evidence only; no reusable product bytes are rewritten.
    record = {"schemaVersion": 1, "command": args.command, "selectionSha256": sha256_bytes(raw),
              "elapsedNs": time.monotonic_ns() - started, "result": result}
    write_canonical_json(evidence / (args.command + ".json"), record)
    (evidence / "selection.json").write_bytes(raw)
    print(json.dumps(record, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
