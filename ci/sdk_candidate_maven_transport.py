"""Observe the official SDK Phase-10 Maven upload, then forward exact bytes offline.

The observer receives only a GitHub read token; the forwarder receives neither
tokens nor signing secrets. Both require the same independently approved S1048
selection. Neither elects a release or substitutes for SDK candidate admission.
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

from ci import product_reuse as transport
from ci.receipt import safe_extract
from ci.sdk_phase11_maven import forward_verified_sdk_phase10_maven
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret


_REPOSITORY = "codex-agent-labs/codex-agent"
_WORKFLOW = ".github/workflows/sdk-phase10-maven-sidecars.yml"
_JOB = "sdk-phase10-maven-sidecars / sdk-phase10-maven-sidecars"
_SELECTION = {"schemaVersion", "producer", "trustedWorkflowSha", "artifactId",
              "artifactSha256", "artifactSize", "signedInventorySha256", "phase11Pins"}
_PHASE11 = {"expected_signed_inventory_sha256", "expected_preparation_sha256",
            "expected_control_sha256", "expected_pgp_key_sha256",
            "expected_signed_index_sha256", "expected_sdk_version",
            "expected_source_commit", "expected_source_tree",
            "expected_validation_tree"}
_TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN",
           "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
_SECRETS = {"SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD",
            "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"}


def _selection(value: dict) -> dict:
    selected = require_exact_keys(value, _SELECTION, "SDK candidate Maven selection")
    if type(selected["schemaVersion"]) is not int or selected["schemaVersion"] != 1:
        raise ValueError("Unsupported SDK candidate Maven selection schema")
    producer = validate_producer(selected["producer"])
    if (producer["repository"] != _REPOSITORY
            or producer["workflowPath"] != ".github/workflows/ci.yml"
            or producer["event"] != "workflow_dispatch" or producer["pullRequest"] is not None):
        raise ValueError("SDK candidate Maven requires fixed protected dispatch producer")
    if (type(selected["trustedWorkflowSha"]) is not str or
            re.fullmatch(r"[0-9a-f]{40}", selected["trustedWorkflowSha"]) is None):
        raise ValueError("SDK candidate Maven child workflow must be commit-pinned")
    require_integer(selected["artifactId"], "SDK Maven upload ID", 1)
    require_integer(selected["artifactSize"], "SDK Maven upload bytes", 1)
    for field in ("artifactSha256", "signedInventorySha256"):
        require_sha256(selected[field], f"SDK candidate Maven {field}")
    pins = require_exact_keys(selected["phase11Pins"], _PHASE11,
                              "SDK candidate Maven Phase-11 pins")
    for field in _PHASE11 - {"expected_sdk_version", "expected_source_commit",
                             "expected_source_tree", "expected_validation_tree"}:
        require_sha256(pins[field], f"SDK candidate Maven {field}")
    for field in ("expected_source_commit", "expected_source_tree",
                  "expected_validation_tree"):
        if type(pins[field]) is not str or re.fullmatch(r"[0-9a-f]{40}", pins[field]) is None:
            raise ValueError(f"SDK candidate Maven {field} requires exact Git identity")
    if (pins["expected_signed_inventory_sha256"] != selected["signedInventorySha256"]
            or pins["expected_source_tree"] != pins["expected_validation_tree"]):
        raise ValueError("SDK candidate Maven upload and Phase-11 identities disagree")
    return selected


def _load(path: Path, expected_sha256: str) -> dict:
    raw = read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != require_sha256(expected_sha256,
            "independent SDK candidate Maven selection"):
        raise ValueError("SDK candidate Maven selection differs from S1048 approval")
    return _selection(load_canonical_json_bytes(raw))


def _name(selected: dict) -> str:
    producer = selected["producer"]
    return ("codex-agent-sdk-phase10-maven-record-"
            f"{selected['phase11Pins']['expected_validation_tree']}-attestation-"
            f"{producer['runId']}-attempt-{producer['runAttempt']}")


def capture_sdk_candidate_maven(selected: dict, destination: Path, *, token: str,
                                environ=None) -> dict:
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if _SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("SDK Maven observer must not receive signing secrets")
    selected = _selection(selected)
    if type(token) is not str or not token:
        raise ValueError("SDK Maven observer requires an observation token")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Maven official capture destination already exists")
    producer = selected["producer"]
    observed = transport._observe_ci_producer_jobs(
        {"maven": producer}, jobs_by_phase={"maven": _JOB},
        trusted_workflows_by_phase={"maven": {
            "path": _WORKFLOW, "sha": selected["trustedWorkflowSha"]}},
        token=token, allow_protected_dispatch=True,
        dispatch_authorization_job=None)[0]
    if (observed["run"].get("status") != "completed"
            or observed["run"].get("conclusion") != "success"):
        raise ValueError("SDK Maven official Phase-10 dispatch did not succeed")
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-maven-observe-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        prepared.mkdir()
        archive = prepared / "official-upload.zip"
        artifact, _ = transport._download_contract_ci_upload(
            selected["artifactId"], selected["artifactSha256"], _name(selected),
            producer, observed["run"], token, destination=archive)
        transport._require_artifact_job_window(observed, _JOB, artifact)
        if (artifact.get("size_in_bytes") != selected["artifactSize"]
                or archive.stat().st_size != selected["artifactSize"]):
            raise ValueError("SDK Maven official upload size differs from S1048 approval")
        listing, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **transport._CATALOG_ZIP_LIMITS)
        signed = prepared / "signed"
        safe_extract(archive, signed)
        if (regular_file_inventory(signed) != listing
                or sha256_bytes(canonical_json_bytes(listing)) !=
                    selected["signedInventorySha256"]):
            raise ValueError("SDK Maven official signed handoff differs from S1048 inventory")
        write_canonical_json(prepared / "transport.json", {
            "schemaVersion": 1, "producer": producer,
            "trustedWorkflowSha": selected["trustedWorkflowSha"],
            "artifact": artifact, "observed": observed, "signedFiles": listing,
            "selectionSha256": sha256_bytes(canonical_json_bytes(selected)),
        })
        inventory = regular_file_inventory(prepared)
        if (sha256_file(archive) != selected["artifactSha256"]
                or regular_file_inventory(signed) != listing):
            raise ValueError("SDK Maven official signed handoff changed during capture")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        if _SECRETS & (set(environment) | set(os.environ)):
            raise ValueError("SDK Maven observer acquired a signing secret")
        publish_regular_tree(prepared, destination, expected_inventory=inventory)
    return {"admitted": False, "artifactId": selected["artifactId"],
            "artifactSha256": selected["artifactSha256"],
            "captureInventorySha256": sha256_bytes(canonical_json_bytes(inventory))}


def forward_sdk_candidate_maven(capture: Path, landed_repository: Path,
                                destination: Path, selected: dict, *,
                                expected_capture_inventory_sha256: str) -> dict:
    require_no_signing_secret(os.environ)
    if (_TOKENS | _SECRETS) & os.environ.keys():
        raise ValueError("SDK Maven candidate forwarder must not receive token or signing secret")
    selected = _selection(selected)
    capture = Path(capture).resolve(strict=True)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Maven candidate output already exists")
    output = destination.resolve(strict=False)
    landed = Path(landed_repository).resolve(strict=True)
    if any(output == source or output in source.parents or source in output.parents
           for source in (capture, landed)):
        raise ValueError("SDK Maven candidate output overlaps an authority input")
    expected = require_sha256(expected_capture_inventory_sha256,
                              "SDK Maven official capture inventory")
    before = regular_file_inventory(capture)
    if (sha256_bytes(canonical_json_bytes(before)) != expected
            or {item.name for item in capture.iterdir()} != {
                "official-upload.zip", "signed", "transport.json"}):
        raise ValueError("SDK Maven capture differs from S1048 approved inventory")
    transport_record = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
        capture / "transport.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)), {"schemaVersion", "producer", "trustedWorkflowSha",
        "artifact", "observed", "signedFiles", "selectionSha256"},
        "SDK Maven official transport")
    if (transport_record["schemaVersion"] != 1
            or transport_record["producer"] != selected["producer"]
            or transport_record["trustedWorkflowSha"] != selected["trustedWorkflowSha"]
            or transport_record["selectionSha256"] != sha256_bytes(canonical_json_bytes(selected))
            or transport_record["artifact"].get("id") != selected["artifactId"]
            or transport_record["artifact"].get("digest") != selected["artifactSha256"]
            or transport_record["artifact"].get("name") != _name(selected)
            or transport_record["artifact"].get("size_in_bytes") != selected["artifactSize"]
            or sha256_file(capture / "official-upload.zip") != selected["artifactSha256"]):
        raise ValueError("SDK Maven capture differs from independently selected official upload")
    listing, _, _ = verified_zip_contents(capture / "official-upload.zip",
        retained_paths=(), allow_empty_members=True, **transport._CATALOG_ZIP_LIMITS)
    if (listing != transport_record["signedFiles"]
            or regular_file_inventory(capture / "signed") != listing
            or sha256_bytes(canonical_json_bytes(listing)) != selected["signedInventorySha256"]):
        raise ValueError("SDK Maven captured signed bytes differ from official ZIP")
    with tempfile.TemporaryDirectory(prefix="sdk-candidate-maven-forward-") as temporary:
        prepared = Path(temporary).resolve() / "candidate"
        result = forward_verified_sdk_phase10_maven(
            capture / "signed", prepared, landed_repository=landed,
            **selected["phase11Pins"])
        ready = regular_file_inventory(prepared)
        if (ready != listing or regular_file_inventory(capture) != before
                or sha256_file(capture / "official-upload.zip") != selected["artifactSha256"]):
            raise ValueError("SDK Maven official upload changed before exact-byte forwarding")
        require_no_signing_secret(os.environ)
        if (_TOKENS | _SECRETS) & os.environ.keys():
            raise ValueError("SDK Maven candidate acquired token or signing secret")
        publish_regular_tree(prepared, destination, expected_inventory=ready)
    return {**result, "admitted": False, "officialArtifactId": selected["artifactId"],
            "officialArtifactSha256": selected["artifactSha256"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", allow_abbrev=False)
    forward = commands.add_parser("forward", allow_abbrev=False)
    for command in (capture, forward):
        command.add_argument("--selection", type=Path, required=True)
        command.add_argument("--expected-selection-sha256", required=True)
        command.add_argument("--destination", type=Path, required=True)
    forward.add_argument("--capture", type=Path, required=True)
    forward.add_argument("--landed-repository", type=Path, required=True)
    forward.add_argument("--expected-capture-inventory-sha256", required=True)
    args = parser.parse_args(argv)
    selected = _load(args.selection, args.expected_selection_sha256)
    if args.command == "capture":
        result = capture_sdk_candidate_maven(
            selected, args.destination, token=os.environ["GITHUB_TOKEN"])
    else:
        result = forward_sdk_candidate_maven(
            args.capture, args.landed_repository, args.destination, selected,
            expected_capture_inventory_sha256=args.expected_capture_inventory_sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
