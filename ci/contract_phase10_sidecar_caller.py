"""Sign Contract Maven primaries only from an official equal-tree release handoff.

The protected workflow supplies independent executable/workflow and PGP pins,
environment approval, and the signing key. This caller retains the original
upload and sidecars separately; it does not grant those authorities itself.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract_equal_tree_original import capture_equal_tree_contract_original
from products.contract_phase10_inventory import verify_contract_phase10_inventory
from products.contract_phase10_maven import (
    produce_contract_phase10_maven_sidecars, verify_contract_phase10_maven,
)
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes,
    publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_sha256, sha256_bytes, snapshot_regular_tree,
    write_canonical_json,
)


def produce_authenticated_contract_maven_sidecars(
    repository_root: Path, candidate_root: Path, destination: Path, *,
    trusted_source_sha: str, trusted_workflow_sha: str,
    trusted_promotion_workflow_sha: str, final_commit: str,
    event_payload: dict, environment: dict, token: str,
    pgp_public_key: Path, expected_pgp_key_sha256: str,
    signing_home: Path, signing_fingerprint: str, passphrase: str,
    trusted_workflow_path: str | None = None, trusted_job_name: str | None = None,
) -> dict:
    """Capture the signed official original before private-key use."""
    repository_root, candidate_root, destination, pgp_public_key, signing_home = map(
        Path, (repository_root, candidate_root, destination, pgp_public_key, signing_home),
    )
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Contract PGP key digest")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Maven sidecar destination already exists")
    output = destination.resolve(strict=False)
    for source in (repository_root, candidate_root, pgp_public_key, signing_home):
        resolved = source.resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Contract Maven sidecar destination overlaps an input")
    key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_pgp_key_sha256:
        raise ValueError("Contract PGP public key differs from the independent pin")

    with tempfile.TemporaryDirectory(prefix="ct-p10-caller-") as temporary:
        root = Path(temporary).resolve()
        original = root / "original"
        selection = capture_equal_tree_contract_original(
            repository_root, candidate_root, original,
            trusted_source_sha=trusted_source_sha,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name,
            trusted_promotion_workflow_sha=trusted_promotion_workflow_sha,
            final_commit=final_commit, event_payload=event_payload,
            environment=environment, token=token,
        )
        if load_canonical_json_bytes(read_regular_file_bytes(
            original / "selection.json", max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        )) != selection:
            raise ValueError("Contract original selection differs from its retained control")
        record = verify_contract_phase10_inventory(original / "contract-record")
        if selection["handoffInventory"] != record or \
                selection["contractVersion"] != record["contractVersion"]:
            raise ValueError("Contract original selection differs from its signed handoff")
        original_files = regular_file_inventory(original, allow_empty=True)
        prepared = root / "prepared"
        snapshot_regular_tree(original, prepared / "original", allow_empty=True)
        if regular_file_inventory(prepared / "original", allow_empty=True) != original_files:
            raise ValueError("Contract original changed during retained capture")
        payload = (prepared / "original/contract-record/handoff" /
                   f"codex-agent-contract-{record['contractVersion']}.zip")
        sidecars = prepared / "maven-sidecars"
        signed = produce_contract_phase10_maven_sidecars(
            payload, sidecars, pgp_public_key, expected_pgp_key_sha256,
            signing_home, signing_fingerprint, passphrase,
        )
        if signed["contractVersion"] != record["contractVersion"] or \
                signed["payloadSha256"] != next(item["sha256"] for item in record["handoffFiles"]
                                                      if item["relativePath"] == payload.name):
            raise ValueError("Contract Maven signatures differ from selected original payload")
        public = prepared / "publication-pgp-public-key.asc"
        public.write_bytes(key)
        if verify_contract_phase10_maven(payload, sidecars, public, expected_pgp_key_sha256) != signed:
            raise ValueError("Retained Contract Maven sidecars differ from signed originals")
        control = {
            "schemaVersion": 1, "originalSelection": selection,
            "mavenSidecars": signed,
        }
        write_canonical_json(prepared / "sidecar-selection.json", control)
        control_bytes = canonical_json_bytes(control)
        prepared_files = regular_file_inventory(prepared)
        if (regular_file_inventory(original, allow_empty=True) != original_files
                or regular_file_inventory(prepared / "original", allow_empty=True) != original_files
                or verify_contract_phase10_inventory(prepared / "original/contract-record") != record
                or verify_contract_phase10_maven(
                    payload, sidecars, public, expected_pgp_key_sha256,
                ) != signed
                or read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or read_regular_file_bytes(public, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or read_regular_file_bytes(prepared / "sidecar-selection.json",
                                           max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != control_bytes
                or regular_file_inventory(prepared) != prepared_files):
            raise ValueError("Contract original or PGP key changed during signing")
        publish_regular_tree(prepared, destination, expected_inventory=prepared_files)
        if (regular_file_inventory(destination) != prepared_files
                or read_regular_file_bytes(destination / "publication-pgp-public-key.asc",
                                           max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or read_regular_file_bytes(destination / "sidecar-selection.json",
                                           max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != control_bytes):
            raise ValueError("Published Contract sidecars differ from verified bytes")
        return {"originalSelection": selection, "mavenSidecars": signed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository-root", "candidate-root", "destination", "trusted-source-sha",
                 "trusted-workflow-sha", "trusted-promotion-workflow-sha", "final-commit",
                 "pgp-public-key", "expected-pgp-key-sha256", "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--trusted-workflow-path")
    parser.add_argument("--trusted-job-name")
    args = parser.parse_args(argv)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        parser.error("GITHUB_EVENT_PATH is required")
    try:
        event = load_json_bytes(read_regular_file_bytes(
            Path(event_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        ))
        if type(event) is not dict:
            raise ValueError("Contract promotion event must be an object")
    except (OSError, ValueError):
        parser.error("GITHUB_EVENT_PATH must name a safe regular JSON object")
    result = produce_authenticated_contract_maven_sidecars(
        Path(args.repository_root), Path(args.candidate_root), Path(args.destination),
        trusted_source_sha=args.trusted_source_sha,
        trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_workflow_path=args.trusted_workflow_path,
        trusted_job_name=args.trusted_job_name,
        trusted_promotion_workflow_sha=args.trusted_promotion_workflow_sha,
        final_commit=args.final_commit, event_payload=event,
        environment=os.environ, token=os.environ.get("GITHUB_TOKEN"),
        pgp_public_key=Path(args.pgp_public_key),
        expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        signing_home=Path(args.signing_home), signing_fingerprint=args.signing_fingerprint,
        passphrase=sys.stdin.read(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
