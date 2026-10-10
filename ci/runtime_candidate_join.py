"""Offline Runtime candidate join from separately approved official captures.

The token-only observers must have retained the catalog/record, original
aggregate, and original Maven uploads first. This reader never treats custody
metadata as trust: independent S1048 pins, Git public policy, signed bytes,
and the existing deep exact-byte forwarder must all agree.
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
from ci.runtime_candidate_transport import validate_selection
from ci.runtime_phase11_bytes import _landed_tree, forward_verified_runtime_phase10_bytes
from ci.products.index import SignedProductIndex, verify_release_product_index
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    publish_regular_tree, regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    sha256_bytes, sha256_file, verified_zip_contents,
)
from ci.products.runtime_aggregate_inputs import load_runtime_aggregate_release_evidence
from ci.products.sdk_protected_runtime import _original_carrier
from ci.products.signatures import load_keyring, require_active_release_key, verify_manifest_signature
from ci.products.signing_isolation import require_no_signing_secret


_PIN_FIELDS = {"phase11Pins", "transportInventorySha256", "aggregateCaptureInventorySha256",
               "sidecarCaptureInventorySha256", "aggregateArtifactId", "aggregateArtifactSha256",
               "sidecarArtifactId", "sidecarArtifactSha256", "originalPlanSha256",
               "planArtifactId", "planArtifactSha256", "aggregateWorkflowSha", "sidecarWorkflowSha"}
_PHASE11_FIELDS = {"expected_protected_inventory_sha256", "expected_sidecar_inventory_sha256",
    "expected_metadata_receipt_sha256", "expected_build_key", "expected_runtime_version",
    "expected_manifest_sha256", "expected_source_commit", "expected_source_tree",
    "expected_validation_tree", "expected_workflow_sha", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256"}
_TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
           "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}
_SECRETS = {"SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD",
            "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY"}


def _json(path: Path) -> dict:
    value = load_canonical_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    if type(value) is not dict:
        raise ValueError("Runtime candidate control must be a canonical object")
    return value


def _digest_tree(path: Path, *, allow_empty=False) -> str:
    return sha256_bytes(canonical_json_bytes(regular_file_inventory(path, allow_empty=allow_empty)))


def _capture(capture: Path, expected_inventory: str, artifact_id: int, artifact_sha: str,
             expected_plan_sha: str, expected_producer: dict, label: str) -> dict:
    if _digest_tree(capture, allow_empty=True) != expected_inventory:
        raise ValueError(f"Runtime {label} capture differs from independent S1048 inventory")
    if {item.name for item in capture.iterdir()} != {
            "plan", "original", "transport.zip", "capture-transport.json"}:
        raise ValueError(f"Runtime {label} capture has unexpected roots")
    control = _json(capture / "capture-transport.json")
    require_exact_keys(control, {"artifact", "captureProducer", "observed",
        "aggregateBuildKey", "aggregateReceiptSha256"} if label == "aggregate" else {
        "artifact", "producer", "observation", "trustedWorkflowPath", "trustedWorkflowSha",
        "trustedJobName", "planArtifactId", "planArtifactSha256", "planSha256", "sidecarFiles"},
        f"Runtime {label} capture transport")
    archive = capture / "transport.zip"
    if (control.get("artifact", {}).get("id") != artifact_id
            or control.get("artifact", {}).get("digest") != artifact_sha
            or control.get("captureProducer", control.get("producer")) != expected_producer
            or sha256_file(archive) != artifact_sha
            or sha256_file(capture / "plan/impact-plan.json") != expected_plan_sha):
        raise ValueError(f"Runtime {label} capture differs from selected original upload")
    zipped, _, _ = verified_zip_contents(archive, retained_paths=(),
        allow_empty_members=True, **transport._CATALOG_ZIP_LIMITS)
    if regular_file_inventory(capture / "original", allow_empty=True) != zipped:
        raise ValueError(f"Runtime {label} extraction differs from pinned ZIP")
    return control


def join_runtime_candidate(selection: dict, pins: dict, transports: Path,
                           aggregate_capture: Path, sidecar_capture: Path,
                           trusted_repository: Path, validation_repository: Path,
                           landed_repository: Path,
                           pgp_public_key: Path, destination: Path, *,
                           expected_selection_sha256: str, expected_pins_sha256: str) -> dict:
    """Join signed Runtime identities and forward exact Phase-10 bytes, offline."""
    require_no_signing_secret(os.environ)
    if (_TOKENS | _SECRETS) & os.environ.keys():
        raise ValueError("Runtime candidate semantic join must not receive token or signing secret")
    selected_digest = require_sha256(expected_selection_sha256, "Runtime approved selection")
    pins_digest = require_sha256(expected_pins_sha256, "Runtime approved join pins")
    if (sha256_bytes(canonical_json_bytes(selection)) != selected_digest
            or sha256_bytes(canonical_json_bytes(pins)) != pins_digest):
        raise ValueError("Runtime candidate controls differ from independent S1048 approval")
    catalog_pin, phase10 = validate_selection(selection)
    pins = require_exact_keys(pins, _PIN_FIELDS, "Runtime candidate join pins")
    phase11 = require_exact_keys(pins["phase11Pins"], _PHASE11_FIELDS,
                                 "Runtime candidate Phase-11 pins")
    for name in _PIN_FIELDS - {"phase11Pins", "aggregateArtifactId", "sidecarArtifactId",
                               "planArtifactId",
                               "aggregateWorkflowSha", "sidecarWorkflowSha"}:
        require_sha256(pins[name], f"Runtime candidate {name}")
    for name in _PHASE11_FIELDS - {"expected_runtime_version", "expected_source_commit",
                                   "expected_source_tree", "expected_validation_tree",
                                   "expected_workflow_sha"}:
        require_sha256(phase11[name], f"Runtime candidate {name}")
    for name in ("aggregateArtifactId", "sidecarArtifactId", "planArtifactId"):
        require_integer(pins[name], f"Runtime candidate {name}", 1)
    for name in ("aggregateWorkflowSha", "sidecarWorkflowSha"):
        if type(pins[name]) is not str or re.fullmatch(r"[0-9a-f]{40}", pins[name]) is None:
            raise ValueError(f"Runtime candidate {name} must be an exact workflow SHA")
    original = phase10["originalProducer"]
    if (phase11["expected_validation_tree"] != original["tree"]
            or phase11["expected_validation_tree"] != catalog_pin["producer"]["tree"]
            or phase11["expected_workflow_sha"] != pins["aggregateWorkflowSha"]
            or len({pins["planArtifactId"], pins["aggregateArtifactId"],
                    pins["sidecarArtifactId"], catalog_pin["artifactId"],
                    phase10["artifactId"]}) != 5):
        raise ValueError("Runtime candidate approved original identities are inconsistent")
    paths = [Path(path) for path in (transports, aggregate_capture, sidecar_capture,
              trusted_repository, validation_repository, landed_repository, pgp_public_key)]
    (transports, aggregate_capture, sidecar_capture, trusted_repository,
     validation_repository, landed_repository, pgp_public_key) = paths
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime candidate destination already exists")
    output = destination.resolve(strict=False)
    for source in paths:
        resolved = source.resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Runtime candidate output overlaps an authority input")
    if _digest_tree(transports) != pins["transportInventorySha256"]:
        raise ValueError("Runtime candidate custody differs from S1048 approval")
    if {item.name for item in transports.iterdir()} != {
            "catalog.zip", "catalog", "phase10-record.zip", "phase10-record", "transport.json"}:
        raise ValueError("Runtime candidate custody has unexpected roots")
    custody = require_exact_keys(_json(transports / "transport.json"),
        {"schemaVersion", "selectionSha256", "routes"}, "Runtime candidate custody")
    if custody["schemaVersion"] != 1 or custody["selectionSha256"] != selected_digest:
        raise ValueError("Runtime candidate custody names a different S1048 selection")
    routes = require_exact_keys(custody["routes"], {"catalog", "phase10-record"},
                                "Runtime candidate official routes")
    for label, selected in (("catalog", catalog_pin), ("phase10-record", phase10)):
        route = routes[label]
        if (route.get("producer") != selected["producer" if label == "catalog" else "recordProducer"]
                or route.get("artifact", {}).get("id") != selected["artifactId"]
                or route.get("artifact", {}).get("digest") != selected["artifactSha256"]
                or sha256_file(transports / f"{label}.zip") != selected["artifactSha256"]
                or regular_file_inventory(transports / label) != route.get("files")):
            raise ValueError("Runtime candidate custody differs from official selected upload")
        zipped, _, _ = verified_zip_contents(transports / f"{label}.zip",
            retained_paths=(), allow_empty_members=True, **transport._CATALOG_ZIP_LIMITS)
        expected_paths = ({"record.json", "record.sig"} if label == "phase10-record"
            else {"caller.json", "catalog/product-index.json", "catalog/product-index.sig"})
        paths = {row["relativePath"] for row in zipped}
        wrong_layout = (paths != expected_paths if label == "phase10-record" else
            not expected_paths <= paths or any(path.split("/", 1)[0] not in {
                "caller.json", "catalog", "original-evidence", "trust"} for path in paths))
        if zipped != route["files"] or wrong_layout:
            raise ValueError("Runtime candidate custody extraction differs from official ZIP")
    if _digest_tree(transports / "catalog") != catalog_pin["inventorySha256"]:
        raise ValueError("Runtime promoted catalog inventory differs from S1048 approval")
    if (sha256_file(transports / "catalog/catalog/product-index.json") != catalog_pin["indexSha256"]
            or sha256_file(transports / "catalog/catalog/product-index.sig") != catalog_pin["signatureSha256"]
            or sha256_file(transports / "phase10-record/record.json") != phase10["recordSha256"]
            or sha256_file(transports / "phase10-record/record.sig") != phase10["signatureSha256"]):
        raise ValueError("Runtime candidate signed bytes differ from S1048 approval")
    aggregate = _capture(aggregate_capture, pins["aggregateCaptureInventorySha256"],
        pins["aggregateArtifactId"], pins["aggregateArtifactSha256"],
        pins["originalPlanSha256"], original, "aggregate")
    sidecar = _capture(sidecar_capture, pins["sidecarCaptureInventorySha256"],
        pins["sidecarArtifactId"], pins["sidecarArtifactSha256"],
        pins["originalPlanSha256"], original, "Maven sidecar")
    if (aggregate.get("aggregateBuildKey") != phase11["expected_build_key"]
            or aggregate.get("aggregateReceiptSha256") != phase11["expected_metadata_receipt_sha256"]
            or sidecar.get("trustedWorkflowSha") != pins["sidecarWorkflowSha"]
            or sidecar.get("trustedWorkflowPath") != ".github/workflows/runtime-phase10-maven.yml"
            or sidecar.get("planArtifactId") != pins["planArtifactId"]
            or sidecar.get("planArtifactSha256") != pins["planArtifactSha256"]
            or sidecar.get("planSha256") != pins["originalPlanSha256"]
            or sidecar.get("sidecarFiles") != regular_file_inventory(sidecar_capture / "original")
            or read_regular_file_bytes(aggregate_capture / "plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) !=
                read_regular_file_bytes(sidecar_capture / "plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)):
        raise ValueError("Runtime candidate original captures disagree")
    original_plan = transport._validate_plan(aggregate_capture / "plan/impact-plan.json",
                                             validation_repository,
                                             expected_revision=original["commit"])
    if (original_plan["remoteBuildAuthorized"] is not True
            or transport._consumer(original_plan, {"GITHUB_RUN_ID": str(original["runId"]),
                "GITHUB_RUN_ATTEMPT": str(original["runAttempt"])})["producer"] != original):
        raise ValueError("Runtime candidate original plan differs from S1048 producer")
    with tempfile.TemporaryDirectory(prefix="runtime-candidate-join-") as temporary:
        root = Path(temporary).resolve()
        trust = transport._release_trust(trusted_repository,
                                         phase11["expected_source_commit"], root / "trust")
        landed_trust = transport._release_trust(landed_repository, "HEAD", root / "landed-policy")
        if (trust is None or landed_trust is None
                or regular_file_inventory(trust.keyring.parent) !=
                   regular_file_inventory(landed_trust.keyring.parent)
                or sha256_file(trust.keyring) != phase11["expected_keyring_sha256"]
                or _digest_tree(trust.keys) != phase11["expected_keys_inventory_sha256"]
                or sha256_file(pgp_public_key) != phase11["expected_pgp_key_sha256"]):
            raise ValueError("Runtime candidate public policy differs from trusted source/landed Git")
        if transport._git_value(trusted_repository, "rev-parse",
                f"{phase11['expected_source_commit']}^{{tree}}") != phase11["expected_source_tree"]:
            raise ValueError("Runtime candidate trusted source tree differs from S1048 pin")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        record_path = transports / "phase10-record/record.json"
        record = require_exact_keys(_json(record_path), {
            "schemaVersion", "product", "signing", "trustedSourceCommit", "officialUpload",
            "phase11Pins", "protectedFiles", "sidecarFiles"}, "Runtime signed Phase-10 record")
        if (record["schemaVersion"] != 1 or record["product"] != "runtime"
                or record["signing"] != signing
                or record["trustedSourceCommit"] != phase11["expected_source_commit"]
                or record["phase11Pins"] != phase11
                or record["officialUpload"] != aggregate
                or regular_file_inventory(aggregate_capture / "original", allow_empty=True) !=
                    record["protectedFiles"]
                or regular_file_inventory(sidecar_capture / "original") != record["sidecarFiles"]):
            raise ValueError("Runtime signed Phase-10 record differs from original captures")
        verify_manifest_signature(record_path, transports / "phase10-record/record.sig",
                                  public, signing)
        catalog = transports / "catalog/catalog"
        index, _ = verify_release_product_index(
            SignedProductIndex(catalog / "product-index.json", catalog / "product-index.sig"),
            keyring_path=trust.keyring, keys_directory=trust.keys)
        if (index["repository"] != original["repository"]
                or index["producer"] != catalog_pin["producer"]
                or index["trustDomain"] != "release"
                or index["context"]["kind"] != "promoted-main"
                or index["context"]["tree"] != original["tree"]
                or len(index["entries"]) != 1):
            raise ValueError("Runtime signed catalog differs from promoted original")
        entry = index["entries"][0]
        if (tuple(entry[name] for name in ("product", "component", "phase", "target")) !=
                ("runtime", "runtime-aggregate", "metadata", "aggregate")
                or entry["buildKey"] != phase11["expected_build_key"]
                or entry["receiptSha256"] != phase11["expected_metadata_receipt_sha256"]
                or entry["artifactSha256"] != phase11["expected_manifest_sha256"]
                or entry["productVersion"] != phase11["expected_runtime_version"]):
            raise ValueError("Runtime catalog metadata differs from signed Phase-10 release")
        evidence = catalog / "runtime-aggregate-release-evidence"
        records = load_runtime_aggregate_release_evidence(evidence)
        if len(records) != 1 or records[0]["receiptSha256"] != entry["receiptSha256"]:
            raise ValueError("Runtime catalog lacks exact original aggregate carrier")
        carrier = evidence / records[0]["handoffRoot"]
        original_carrier = _original_carrier(aggregate_capture / "original",
            entry["receiptSha256"], entry["buildKey"])
        if regular_file_inventory(carrier, allow_empty=True) != \
                regular_file_inventory(original_carrier, allow_empty=True):
            raise ValueError("Runtime catalog and Phase-10 aggregate carriers differ")
        promotion_caller = _json(transports / "catalog/caller.json")
        if (promotion_caller.get("producer") != catalog_pin["producer"]
                or promotion_caller.get("originalProducer") != original
                or promotion_caller.get("validatedTree") != original["tree"]
                or promotion_caller.get("aggregateBuildKey") != entry["buildKey"]
                or promotion_caller.get("aggregateReceiptSha256") != entry["receiptSha256"]
                or promotion_caller.get("originalUploadArtifactId") != pins["aggregateArtifactId"]
                or promotion_caller.get("originalUploadSha256") != pins["aggregateArtifactSha256"]
                or promotion_caller.get("trustedWorkflowSha") != pins["aggregateWorkflowSha"]):
            raise ValueError("Runtime promoted caller differs from original Phase-10 custody")
        transport.stage_release_catalog(catalog, root / "verified-catalog",
            repository=original["repository"], source="promoted-main",
            keyring=trust.keyring, keys_directory=trust.keys)
        # The forwarder repeats full aggregate signature/closure and PGP Maven
        # verification under the caller-pinned policy, then atomically copies.
        candidate = root / "candidate"
        result = forward_verified_runtime_phase10_bytes(
            aggregate_capture / "original", sidecar_capture / "original", candidate,
            landed_repository=landed_repository, keyring=trust.keyring,
            keys_directory=trust.keys, pgp_public_key=pgp_public_key, **phase11)
        ready = regular_file_inventory(candidate)
        source_again = transport._release_trust(trusted_repository,
            phase11["expected_source_commit"], root / "source-again")
        landed_again = transport._release_trust(landed_repository, "HEAD", root / "landed-again")
        if (source_again is None or landed_again is None
                or regular_file_inventory(source_again.keyring.parent) !=
                   regular_file_inventory(trust.keyring.parent)
                or regular_file_inventory(landed_again.keyring.parent) !=
                   regular_file_inventory(trust.keyring.parent)
                or _landed_tree(landed_repository) != phase11["expected_validation_tree"]
                or transport._git_value(validation_repository, "rev-parse", "HEAD") != original["commit"]
                or _digest_tree(transports) != pins["transportInventorySha256"]
                or _digest_tree(aggregate_capture, allow_empty=True) != pins["aggregateCaptureInventorySha256"]
                or _digest_tree(sidecar_capture, allow_empty=True) != pins["sidecarCaptureInventorySha256"]
                or sha256_file(pgp_public_key) != phase11["expected_pgp_key_sha256"]
                or regular_file_inventory(candidate) != ready):
            raise ValueError("Runtime candidate authority changed before final publication")
        require_no_signing_secret(os.environ)
        if (_TOKENS | _SECRETS) & os.environ.keys():
            raise ValueError("Runtime candidate join acquired token or signing secret")
        publish_regular_tree(candidate, destination, expected_inventory=ready)
    return {"catalogIndexSha256": catalog_pin["indexSha256"],
            "signedRecordSha256": phase10["recordSha256"], "candidate": result}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("selection", "pins", "transports", "aggregate-capture", "sidecar-capture",
                 "trusted-repository", "validation-repository", "landed-repository",
                 "pgp-public-key", "destination"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--expected-pins-sha256", required=True)
    args = parser.parse_args(argv)
    selected = read_regular_file_bytes(args.selection, max_bytes=64 * 1024,
                                       reject_symlink_parents=True)
    approved = read_regular_file_bytes(args.pins, max_bytes=64 * 1024,
                                       reject_symlink_parents=True)
    if (sha256_bytes(selected) != require_sha256(args.expected_selection_sha256,
            "Runtime approved selection")
            or sha256_bytes(approved) != require_sha256(args.expected_pins_sha256,
            "Runtime approved join pins")):
        raise ValueError("Runtime candidate controls differ from S1048 approval")
    result = join_runtime_candidate(load_canonical_json_bytes(selected),
        load_canonical_json_bytes(approved), args.transports, args.aggregate_capture,
        args.sidecar_capture, args.trusted_repository, args.validation_repository,
        args.landed_repository,
        args.pgp_public_key, args.destination,
        expected_selection_sha256=args.expected_selection_sha256,
        expected_pins_sha256=args.expected_pins_sha256)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
