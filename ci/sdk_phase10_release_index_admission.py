"""Capture a later protected SDK index upload against the original 61-phase PR.

This no-secret handoff requires independent pins for both producers and every
uploaded byte. It does not authorize a dispatch or mint release trust itself.
"""

import argparse
import json
from pathlib import Path
import os
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as products
from ci.products.index import SignedProductIndex
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    snapshot_regular_tree, verified_zip_contents, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract
from ci.sdk_campaign_pinned_election import held_pinned_sdk_campaign_authority
from ci.sdk_campaign_release_issuer import (
    _release_key, add_sdk_release_replay_arguments,
    held_sdk_release_replay_options,
    verify_signed_sdk_release_index_against_official_replay,
)


_WORKFLOW = ".github/workflows/sdk-phase10-later-record.yml"
_JOB = "sdk-phase10-record / sdk-phase10-record"
_MEMBERS = {"product-index.json", "product-index.sig"}
_EVIDENCE_MEMBERS = {"authority-upload.zip", "sdk-campaign-authority.json",
    "authority-transport.json", "product-signing-keys.json",
    *(f"{kind}-{family}.json"
        for kind in ("election", "semantic")
        for family in ("core-android", "native", "apple-js"))}
_ZIP_LIMITS = {"require_sorted": False, "max_archive_bytes": 20 * 1024 * 1024,
               "max_central_directory_bytes": 64 * 1024, "max_members": 2,
               "max_entry_bytes": 16 * 1024 * 1024,
               "max_total_bytes": 17 * 1024 * 1024,
               "max_compression_ratio": 100}


def capture_signed_sdk_phase10_index(plan_path, repository_root, destination, *,
        original_producer, expected_original_producer_sha256,
        record_producer, expected_record_producer_sha256,
        record_artifact_id, record_artifact_sha256,
        trusted_record_workflow_sha, expected_index_sha256,
        expected_signature_sha256, keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256,
        token, environ=None, **replay_options):
    """Publish exact official ZIP, signed pair and observation only after replay."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("SDK signed-index admission requires an observation token")
    original = validate_producer(dict(original_producer))
    record = validate_producer(dict(record_producer))
    if (sha256_bytes(canonical_json_bytes(original)) != require_sha256(
                expected_original_producer_sha256, "Protected SDK original producer digest")
            or sha256_bytes(canonical_json_bytes(record)) != require_sha256(
                expected_record_producer_sha256, "Protected SDK record producer digest")):
        raise ValueError("SDK producers differ from independently approved pins")
    if (original["repository"] != "codex-agent-labs/codex-agent"
            or original["workflowPath"] != ".github/workflows/ci.yml"
            or original["event"] != "pull_request"
            or record["repository"] != original["repository"]
            or record["workflowPath"] != ".github/workflows/ci.yml"
            or record["event"] != "workflow_dispatch"
            or record["runId"] == original["runId"]):
        raise ValueError("SDK signed-index admission requires distinct approved PR and dispatch producers")
    artifact_id = require_integer(record_artifact_id, "SDK signed-index artifact ID", 1)
    artifact_sha = require_sha256(record_artifact_sha256, "SDK signed-index artifact digest")
    index_pin = require_sha256(expected_index_sha256, "Protected SDK index digest")
    signature_pin = require_sha256(expected_signature_sha256, "Protected SDK signature digest")
    _release_key(keyring_path, keys_directory, expected_keyring_sha256,
        expected_keys_inventory_sha256)
    forbidden = {"producer", "context", "repository", "original_run_id",
                 "original_run_attempt", "keyring_path", "keys_directory",
                 "expected_keyring_sha256", "expected_keys_inventory_sha256",
                 "token", "environ"}
    if forbidden & set(replay_options):
        raise ValueError("SDK replay cannot replace independently pinned admission context")
    with held_pinned_sdk_campaign_authority(
            replay_options["authority_file"],
            replay_options["expected_authority_sha256"]) as authority:
        if authority["completedCatalogPin"]["producer"] != original:
            raise ValueError("SDK original producer differs from protected campaign authority")
    authority_dispatch = validate_producer(dict(replay_options["authority_producer"]))
    if (sha256_bytes(canonical_json_bytes(authority_dispatch)) != require_sha256(
            replay_options["expected_authority_producer_sha256"],
            "Protected SDK authority producer digest")
            or authority_dispatch["event"] != "workflow_dispatch"
            or authority_dispatch["repository"] != original["repository"]
            or authority_dispatch["workflowPath"] != ".github/workflows/ci.yml"
            or authority_dispatch["runId"] in {original["runId"], record["runId"]}):
        raise ValueError("SDK authority dispatch is not independently pinned and distinct")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK signed-index capture destination already exists")
    observed = products._observe_ci_producer_jobs(
        {"record": record}, jobs_by_phase={"record": _JOB},
        trusted_workflows_by_phase={"record": {
            "path": _WORKFLOW, "sha": trusted_record_workflow_sha,
        }}, token=token, allow_protected_dispatch=True,
        dispatch_authorization_job=None)[0]
    if (observed["run"].get("status") != "completed"
            or observed["run"].get("conclusion") != "success"):
        raise ValueError("SDK protected record dispatch did not complete successfully")
    name = (f"codex-agent-sdk-phase10-release-index-{original['tree']}"
            f"-attestation-{record['runId']}-attempt-{record['runAttempt']}")
    with tempfile.TemporaryDirectory(prefix="sdk-phase10-index-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "official-upload.zip"
        artifact, _ = products._download_contract_ci_upload(
            artifact_id, artifact_sha, name, record, observed["run"], token,
            destination=archive, max_bytes=_ZIP_LIMITS["max_archive_bytes"])
        products._require_artifact_job_window(observed, _JOB, artifact)
        inventory, _, _ = verified_zip_contents(
            archive, retained_paths=(), **_ZIP_LIMITS)
        if {row["relativePath"] for row in inventory} != _MEMBERS:
            raise ValueError("SDK signed-index upload has unexpected files")
        extracted = root / "extracted"
        safe_extract(archive, extracted)
        if regular_file_inventory(extracted) != inventory:
            raise ValueError("SDK signed-index extraction differs from official upload")
        index, raw = verify_signed_sdk_release_index_against_official_replay(
            SignedProductIndex(extracted / "product-index.json",
                               extracted / "product-index.sig"),
            plan_path, repository_root, expected_index_sha256=index_pin,
            expected_signature_sha256=signature_pin,
            keyring_path=keyring_path, keys_directory=keys_directory,
            expected_keyring_sha256=expected_keyring_sha256,
            expected_keys_inventory_sha256=expected_keys_inventory_sha256,
            repository=original["repository"], producer=original,
            context={"kind": "pull-request", "pullRequest": original["pullRequest"],
                     **{field: original[field] for field in (
                         "commit", "tree", "runId", "runAttempt")}},
            original_run_id=original["runId"],
            original_run_attempt=original["runAttempt"],
            token=token, environ=environment,
            evidence_destination=root / "replay-evidence", **replay_options)
        if raw != (extracted / "product-index.json").read_bytes():
            raise ValueError("SDK signed-index bytes changed after full replay")
        replay_inventory = regular_file_inventory(root / "replay-evidence")
        evidence_paths = {row["relativePath"] for row in replay_inventory}
        key_paths = {path for path in evidence_paths if path.startswith("keys/")}
        if (evidence_paths - key_paths != _EVIDENCE_MEMBERS
                or not key_paths
                or any(not path.endswith(".pub") for path in key_paths)):
            raise ValueError("SDK replay evidence lacks exact authority and policy bytes")
        captured = root / "captured"
        captured.mkdir()
        snapshot_regular_tree(extracted, captured / "signed-pair")
        snapshot_regular_tree(root / "replay-evidence",
            captured / "replay-evidence")
        (captured / "official-upload.zip").write_bytes(archive.read_bytes())
        write_canonical_json(captured / "transport.json", {
            "schemaVersion": 1, "originalProducer": original,
            "recordProducer": record, "recordObservation": observed,
            "artifact": artifact,
        })
        captured_inventory = regular_file_inventory(captured)
        original_keys = regular_file_inventory(Path(keys_directory))
        if (regular_file_inventory(extracted) != inventory
                or regular_file_inventory(captured / "signed-pair") != inventory
                or regular_file_inventory(captured / "replay-evidence") != replay_inventory
                or regular_file_inventory(captured / "replay-evidence/keys") != original_keys
                or sha256_bytes(canonical_json_bytes(original_keys)) !=
                    expected_keys_inventory_sha256
                or sha256_bytes(read_regular_file_bytes(keyring_path,
                    max_bytes=64 * 1024, reject_symlink_parents=True))
                    != expected_keyring_sha256
                or sha256_file(captured / "replay-evidence/product-signing-keys.json")
                    != expected_keyring_sha256
                or sha256_file(archive) != artifact_sha
                or sha256_file(captured / "official-upload.zip") != artifact_sha
                or sha256_file(captured / "signed-pair/product-index.json") != index_pin
                or sha256_file(captured / "signed-pair/product-index.sig") != signature_pin):
            raise ValueError("SDK signed-index originals changed before capture")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(captured, destination,
            expected_inventory=captured_inventory)
    return {"index": index, "indexSha256": index_pin,
            "signatureSha256": signature_pin, "artifactId": artifact_id,
            "artifactSha256": artifact_sha, "files": captured_inventory}


def main(argv=None):
    """No-secret later-run caller; approval pins come from protected inputs."""
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    add_sdk_release_replay_arguments(parser, require_keys_inventory=True)
    for name in ("destination", "original-producer", "record-producer"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--record-artifact-id", type=int, required=True)
    for name in ("expected-original-producer-sha256",
                 "expected-record-producer-sha256", "record-artifact-sha256",
                 "trusted-record-workflow-sha", "expected-index-sha256",
                 "expected-signature-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        require_no_signing_secret(os.environ)
        from ci.sdk_campaign_release_issuer import (
            _APPROVED_INDEX, _APPROVED_SIGNATURE, _approved_environment_digest,
        )
        if (require_sha256(args.expected_index_sha256, "Protected SDK index digest")
                != _approved_environment_digest(_APPROVED_INDEX)
                or require_sha256(args.expected_signature_sha256,
                    "Protected SDK signature digest")
                    != _approved_environment_digest(_APPROVED_SIGNATURE)):
            raise ValueError("SDK signed pair differs from protected approval")
        original_bytes = read_regular_file_bytes(args.original_producer,
            max_bytes=64 * 1024, reject_symlink_parents=True)
        record_bytes = read_regular_file_bytes(args.record_producer,
            max_bytes=64 * 1024, reject_symlink_parents=True)
        if (sha256_bytes(original_bytes) != require_sha256(
                args.expected_original_producer_sha256, "SDK original producer digest")
                or sha256_bytes(record_bytes) != require_sha256(
                    args.expected_record_producer_sha256, "SDK record producer digest")):
            raise ValueError("SDK producer files differ from independent approval")
        original = load_canonical_json_bytes(original_bytes)
        record = load_canonical_json_bytes(record_bytes)
        if args.destination.exists() or args.destination.is_symlink():
            raise ValueError("SDK signed-index destination already exists")
        with tempfile.TemporaryDirectory(prefix="sdk-index-admission-") as temporary:
            private = Path(temporary).resolve() / "captured"
            with held_sdk_release_replay_options(args) as selected:
                options = dict(selected)
                if options.pop("producer") != original or options.pop("repository") != original["repository"]:
                    raise ValueError("SDK original producer differs from protected campaign")
                options.pop("context")
                selected_run = options.pop("original_run_id"), options.pop("original_run_attempt")
                if selected_run not in ((None, None),
                                        (original["runId"], original["runAttempt"])):
                    raise ValueError("SDK original run differs from protected campaign")
                token = options.pop("token")
                environment = options.pop("environ")
                keyring = options.pop("keyring_path")
                keys = options.pop("keys_directory")
                keyring_pin = options.pop("expected_keyring_sha256")
                keys_inventory_pin = options.pop("expected_keys_inventory_sha256")
                result = capture_signed_sdk_phase10_index(
                    args.plan, args.repository_root, private,
                    original_producer=original,
                    expected_original_producer_sha256=args.expected_original_producer_sha256,
                    record_producer=record,
                    expected_record_producer_sha256=args.expected_record_producer_sha256,
                    record_artifact_id=args.record_artifact_id,
                    record_artifact_sha256=args.record_artifact_sha256,
                    trusted_record_workflow_sha=args.trusted_record_workflow_sha,
                    expected_index_sha256=args.expected_index_sha256,
                    expected_signature_sha256=args.expected_signature_sha256,
                    keyring_path=keyring, keys_directory=keys,
                    expected_keyring_sha256=keyring_pin,
                    expected_keys_inventory_sha256=keys_inventory_pin,
                    token=token, environ=environment, **options)
            if (read_regular_file_bytes(args.original_producer, max_bytes=64 * 1024,
                    reject_symlink_parents=True) != original_bytes
                    or read_regular_file_bytes(args.record_producer, max_bytes=64 * 1024,
                        reject_symlink_parents=True) != record_bytes):
                raise ValueError("SDK independently pinned producer files changed")
            require_no_signing_secret(os.environ)
            publish_regular_tree(private, args.destination,
                expected_inventory=result["files"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({"destination": str(args.destination),
        "artifactId": result["artifactId"], "artifactSha256": result["artifactSha256"],
        "indexSha256": result["indexSha256"],
        "signatureSha256": result["signatureSha256"]},
        sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
