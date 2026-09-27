"""External protected custody for a failed SDK catalog's development key.

The signed record is transport policy, not SDK release admission. Preparation
observes one exact official failed upload without access to a signing secret;
the separate signer only signs already prepared, caller-pinned bytes.
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
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes,
)
from ci.products.receipt import validate_producer
from ci.products.signatures import (
    load_keyring, public_key_for_metadata, verify_manifest_signature,
)


RECORD = "sdk-failed-catalog-custody.json"
SIGNATURE = "sdk-failed-catalog-custody.sig"
PUBLIC_KEY = "public-key.pub"
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _exact_inventory(files):
    return [{"relativePath": name, "bytes": len(value), "sha256": sha256_bytes(value)}
            for name, value in sorted(files.items())]


def validate_custody_record(value):
    from ci.sdk_campaign_original_locator import require_failed_sdk_partial_catalog_route

    record = require_exact_keys(value, {
        "schemaVersion", "kind", "scope", "producer", "catalog", "reviewedRoute",
        "signing", "trustedSourceCommit", "keyringSha256", "keysInventorySha256",
    }, "Failed SDK catalog custody record")
    if (require_integer(record["schemaVersion"], "Custody schemaVersion", 1) != 1
            or record["kind"] != "sdk-failed-catalog-custody"
            or record["scope"] != "development-cache-only"):
        raise ValueError("Failed SDK custody has unsupported identity or scope")
    producer = validate_producer(record["producer"])
    if producer["event"] != "pull_request":
        raise ValueError("Failed SDK custody requires a pull-request producer")
    catalog = require_exact_keys(record["catalog"], {
        "artifactId", "artifactSha256", "artifactName", "indexSha256", "publicKeySha256",
    }, "Failed SDK custody catalog")
    require_integer(catalog["artifactId"], "Custody artifact ID", 1)
    for name in ("artifactSha256", "indexSha256", "publicKeySha256"):
        require_sha256(catalog[name], f"Custody {name}")
    route = require_exact_keys(record["reviewedRoute"], {
        "workflowPath", "workflowSha", "jobName",
    }, "Failed SDK custody route")
    if (type(route["workflowPath"]) is not str or not route["workflowPath"]
            or type(route["jobName"]) is not str or not route["jobName"]):
        raise ValueError("Failed SDK custody route is incomplete")
    if type(route["workflowSha"]) is not str or _SOURCE_SHA.fullmatch(route["workflowSha"]) is None:
        raise ValueError("Custody reviewed workflow needs a full Git SHA")
    require_failed_sdk_partial_catalog_route(
        producer, catalog["artifactName"], route["workflowPath"], route["jobName"])
    if type(record["trustedSourceCommit"]) is not str or \
            _SOURCE_SHA.fullmatch(record["trustedSourceCommit"]) is None:
        raise ValueError("Failed SDK custody needs a full reviewed source commit")
    require_sha256(record["keyringSha256"], "Custody keyring digest")
    require_sha256(record["keysInventorySha256"], "Custody keys inventory digest")
    from ci.products.signatures import require_release_signing_metadata
    require_release_signing_metadata(record["signing"])
    return record


def _pinned_policy(keyring_path, keys_directory, expected_keyring_sha256,
                   expected_keys_inventory_sha256):
    keyring_bytes = read_regular_file_bytes(
        keyring_path, max_bytes=64 * 1024, reject_symlink_parents=True)
    if sha256_bytes(keyring_bytes) != require_sha256(
            expected_keyring_sha256, "Independent custody keyring digest"):
        raise ValueError("Custody keyring differs from independent policy")
    inventory = regular_file_inventory(keys_directory)
    if sha256_bytes(canonical_json_bytes(inventory)) != require_sha256(
            expected_keys_inventory_sha256, "Independent custody keys inventory digest"):
        raise ValueError("Custody public keys differ from independent policy")
    return load_keyring(keyring_path, keys_directory)


def prepare_failed_sdk_catalog_custody(*, producer, artifact_id, artifact_sha256,
        trusted_workflow_sha, trusted_workflow_path, trusted_job_name,
        trusted_source_commit, keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256,
        token, destination):
    """Inspect one caller-pinned official failed upload, then prepare unsigned policy."""
    from ci.sdk_campaign_original_locator import inspect_failed_sdk_partial_catalog_for_custody, products
    from ci.products.signatures import require_active_release_key
    from ci.products.signing_isolation import require_no_signing_secret

    require_no_signing_secret(os.environ)
    producer = validate_producer(producer)
    artifact_id = require_integer(artifact_id, "Independent catalog artifact ID", 1)
    artifact_sha256 = require_sha256(artifact_sha256, "Independent catalog artifact digest")
    if type(trusted_workflow_sha) is not str or _SOURCE_SHA.fullmatch(trusted_workflow_sha) is None:
        raise ValueError("Custody preparation requires a full reviewed workflow SHA")
    if type(token) is not str or not token:
        raise ValueError("Custody preparation requires an official observation token")
    if type(trusted_source_commit) is not str or _SOURCE_SHA.fullmatch(trusted_source_commit) is None:
        raise ValueError("Custody preparation requires a full reviewed source commit")
    policy = _pinned_policy(keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256)
    active, _ = require_active_release_key(policy, keys_directory)
    signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
    signing.update(active)
    url = (f"https://api.github.com/repos/{producer['repository']}/actions/artifacts/"
           f"{artifact_id}")
    artifact = products.api_json(url, token)
    if (not isinstance(artifact, dict) or artifact.get("id") != artifact_id
            or artifact.get("digest") != artifact_sha256):
        raise ValueError("Custody upload differs from caller-pinned official identity")
    with tempfile.TemporaryDirectory(prefix="sdk-catalog-custody-") as temporary:
        root = Path(temporary).resolve()
        catalog, _ = inspect_failed_sdk_partial_catalog_for_custody(artifact, root,
            producer=producer, repository=producer["repository"],
            pull_request=producer["pullRequest"],
            expected_artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name, token=token)
        extracted = root / "catalogs/same-pr" / str(artifact_id) / "contents"
        key = read_regular_file_bytes(extracted / PUBLIC_KEY, max_bytes=64 * 1024,
            reject_symlink_parents=True)
        index_bytes = read_regular_file_bytes(extracted / "product-index.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        if catalog.index != load_canonical_json_bytes(index_bytes):
            raise ValueError("Custody catalog index changed after official verification")
        record = validate_custody_record({
            "schemaVersion": 1, "kind": "sdk-failed-catalog-custody",
            "scope": "development-cache-only", "producer": producer,
            "catalog": {"artifactId": artifact_id, "artifactSha256": artifact_sha256,
                "artifactName": artifact["name"], "indexSha256": sha256_bytes(index_bytes),
                "publicKeySha256": sha256_bytes(key)},
            "reviewedRoute": {"workflowPath": trusted_workflow_path,
                "workflowSha": trusted_workflow_sha, "jobName": trusted_job_name},
            "signing": signing, "trustedSourceCommit": trusted_source_commit,
            "keyringSha256": expected_keyring_sha256,
            "keysInventorySha256": expected_keys_inventory_sha256,
        })
        prepared = root / "prepared"
        prepared.mkdir()
        record_bytes = canonical_json_bytes(record)
        (prepared / RECORD).write_bytes(record_bytes)
        (prepared / PUBLIC_KEY).write_bytes(key)
        if read_regular_file_bytes(extracted / PUBLIC_KEY, max_bytes=64 * 1024,
                                   reject_symlink_parents=True) != key or \
                read_regular_file_bytes(extracted / "product-index.json",
                                        max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != index_bytes:
            raise ValueError("Custody source changed before preparation")
        publish_regular_tree(prepared, destination,
            expected_inventory=_exact_inventory({RECORD: record_bytes, PUBLIC_KEY: key}))
    return record


def verify_failed_sdk_catalog_custody(custody_root, *, producer, artifact_id,
        artifact_sha256, trusted_workflow_sha, trusted_workflow_path,
        trusted_job_name, trusted_source_commit, keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256):
    """Return a held policy key only after independent release-key verification."""
    root = Path(custody_root)
    inventory = regular_file_inventory(root)
    if {row["relativePath"] for row in inventory} != {RECORD, SIGNATURE, PUBLIC_KEY}:
        raise ValueError("Failed SDK custody must contain exactly its signed record and key")
    raw = read_regular_file_bytes(root / RECORD, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    record = validate_custody_record(load_canonical_json_bytes(raw))
    if (raw != canonical_json_bytes(record) or record["producer"] != validate_producer(producer)
            or record["catalog"]["artifactId"] != require_integer(artifact_id, "Independent artifact ID", 1)
            or record["catalog"]["artifactSha256"] != require_sha256(
                artifact_sha256, "Independent artifact digest")
            or record["reviewedRoute"] != {"workflowPath": trusted_workflow_path,
                "workflowSha": trusted_workflow_sha, "jobName": trusted_job_name}
            or record["trustedSourceCommit"] != trusted_source_commit
            or record["keyringSha256"] != expected_keyring_sha256
            or record["keysInventorySha256"] != expected_keys_inventory_sha256):
        raise ValueError("Failed SDK custody differs from independent selection")
    policy = _pinned_policy(keyring_path, keys_directory,
        expected_keyring_sha256, expected_keys_inventory_sha256)
    signer = public_key_for_metadata(record["signing"], policy, keys_directory,
        allow_retired=True)
    verify_manifest_signature(root / RECORD, root / SIGNATURE, signer, record["signing"])
    key_path = root / PUBLIC_KEY
    if sha256_bytes(read_regular_file_bytes(key_path, max_bytes=64 * 1024,
            reject_symlink_parents=True)) != record["catalog"]["publicKeySha256"]:
        raise ValueError("Failed SDK custody key differs from signed record")
    return {"publicKey": key_path, "publicKeySha256": record["catalog"]["publicKeySha256"],
            "catalogArtifactName": record["catalog"]["artifactName"],
            "catalogIndexSha256": record["catalog"]["indexSha256"]}


def main(argv=None) -> int:
    """Local transport interface; protected source/pins are caller authorities."""
    from ci.products.signing_isolation import require_no_signing_secret

    require_no_signing_secret(os.environ)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify"):
        selected = commands.add_parser(command, allow_abbrev=False)
        selected.add_argument("--producer", type=Path, required=True)
        selected.add_argument("--expected-producer-sha256", required=True)
        selected.add_argument("--artifact-id", type=int, required=True)
        selected.add_argument("--artifact-sha256", required=True)
        selected.add_argument("--trusted-workflow-sha", required=True)
        selected.add_argument("--trusted-workflow-path", required=True)
        selected.add_argument("--trusted-job-name", required=True)
        selected.add_argument("--trusted-source-commit", required=True)
        selected.add_argument("--keyring-path", type=Path, required=True)
        selected.add_argument("--keys-directory", type=Path, required=True)
        selected.add_argument("--expected-keyring-sha256", required=True)
        selected.add_argument("--expected-keys-inventory-sha256", required=True)
        selected.add_argument("--destination" if command == "prepare" else "--custody-root",
                              type=Path, required=True)
    args = parser.parse_args(argv)
    producer_bytes = read_regular_file_bytes(args.producer, max_bytes=64 * 1024,
        reject_symlink_parents=True)
    if sha256_bytes(producer_bytes) != require_sha256(
            args.expected_producer_sha256, "Independent SDK producer digest"):
        raise ValueError("SDK custody producer differs from independent pin")
    producer = validate_producer(load_canonical_json_bytes(producer_bytes))
    if producer_bytes != canonical_json_bytes(producer):
        raise ValueError("SDK custody producer must be canonical")
    common = dict(producer=producer, artifact_id=args.artifact_id,
        artifact_sha256=args.artifact_sha256,
        trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_workflow_path=args.trusted_workflow_path,
        trusted_job_name=args.trusted_job_name,
        trusted_source_commit=args.trusted_source_commit,
        keyring_path=args.keyring_path, keys_directory=args.keys_directory,
        expected_keyring_sha256=args.expected_keyring_sha256,
        expected_keys_inventory_sha256=args.expected_keys_inventory_sha256)
    if args.command == "prepare":
        result = prepare_failed_sdk_catalog_custody(**common,
            token=os.environ["GITHUB_TOKEN"], destination=args.destination)
    else:
        result = verify_failed_sdk_catalog_custody(args.custody_root, **common)
        result = {**result, "publicKey": str(result["publicKey"])}
    require_no_signing_secret(os.environ)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
