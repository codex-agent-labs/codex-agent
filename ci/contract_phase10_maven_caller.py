"""Add external Maven signatures to an authenticated Phase-10 Contract handoff.

The protected workflow owns its executable pin, environment approval, and PGP
secret. This caller reuses the existing original-CI/Contract attestation gate;
it never signs, repacks, or changes the reusable Contract ZIP.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contract_release import attest_contract_ci
from products.contract_phase10_inventory import capture_contract_phase10_inventory
from products.contract_phase10_maven import (
    produce_contract_phase10_maven_sidecars, verify_contract_phase10_maven,
)
from products.inventory import (
    canonical_json_bytes, load_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_sha256, sha256_bytes, write_canonical_json,
)


def produce_contract_phase10_maven_handoff(
    repository_root: Path, destination: Path, *, trusted_source_sha: str,
    trusted_workflow_sha: str, artifact_id: int, artifact_sha256: str,
    transport_producer: Mapping[str, Any], contract_version: str,
    event_payload: dict[str, Any], environment: Mapping[str, str],
    pgp_public_key: Path, expected_pgp_key_sha256: str, signing_home: Path,
    signing_fingerprint: str, passphrase: str, token: str | None = None,
    release_handoffs: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Authenticate the original first; emit separate immutable release and PGP trees."""
    repository_root, destination, pgp_public_key, signing_home = map(
        Path, (repository_root, destination, pgp_public_key, signing_home),
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Phase-10 Maven destination already exists")
    output = destination.resolve(strict=False)
    for source in (repository_root, pgp_public_key, signing_home, *release_handoffs):
        resolved = Path(source).resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Contract Phase-10 Maven destination overlaps an input")
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Contract PGP key digest")
    key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_pgp_key_sha256:
        raise ValueError("Contract PGP public key differs from the independent pin")

    with tempfile.TemporaryDirectory(prefix="ct-p10-maven-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        release = prepared / "contract-release-evidence"
        caller = attest_contract_ci(
            repository_root, release, trusted_source_sha=trusted_source_sha,
            trusted_workflow_sha=trusted_workflow_sha, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, transport_producer=transport_producer,
            contract_version=contract_version, event_payload=event_payload,
            environment=environment, token=token, release_handoffs=release_handoffs,
        )
        original_files = regular_file_inventory(release)
        captured = root / "verified-contract"
        record = capture_contract_phase10_inventory(
            release / "contract-input", release / "caller-policy/product-signing-keys.json",
            release / "caller-policy/keys", captured,
        )
        if record["contractVersion"] != contract_version:
            raise ValueError("Authenticated Contract version differs from requested version")
        payload = release / "contract-input" / f"codex-agent-contract-{contract_version}.zip"
        signed = produce_contract_phase10_maven_sidecars(
            payload, prepared / "maven-sidecars", pgp_public_key,
            expected_pgp_key_sha256, signing_home, signing_fingerprint, passphrase,
        )
        if signed["contractVersion"] != contract_version or signed["payloadSha256"] != next(
            item["sha256"] for item in record["handoffFiles"]
            if item["relativePath"] == payload.name
        ):
            raise ValueError("Contract PGP signatures differ from the attested payload")
        public = prepared / "publication-pgp-public-key.asc"
        public.write_bytes(key)
        if verify_contract_phase10_maven(
            payload, prepared / "maven-sidecars", public, expected_pgp_key_sha256,
        ) != signed:
            raise ValueError("Contract PGP sidecars differ from their signed inputs")
        control = {"schemaVersion": 1, "releaseCaller": caller,
                   "releaseFiles": original_files, "contractInventory": record,
                   "mavenSidecars": signed}
        control_path = prepared / "sidecar-selection.json"
        write_canonical_json(control_path, control)
        control_bytes = canonical_json_bytes(control)
        expected_files = regular_file_inventory(prepared)
        if (regular_file_inventory(release) != original_files
                or verify_contract_phase10_maven(
                    payload, prepared / "maven-sidecars", public, expected_pgp_key_sha256,
                ) != signed
                or read_regular_file_bytes(public, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or read_regular_file_bytes(control_path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != control_bytes
                or regular_file_inventory(prepared) != expected_files
                or read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key):
            raise ValueError("Contract release or PGP key changed before sidecar publication")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
        if (regular_file_inventory(destination) != expected_files
                or read_regular_file_bytes(destination / "publication-pgp-public-key.asc",
                                           max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or read_regular_file_bytes(destination / "sidecar-selection.json",
                                           max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != control_bytes):
            raise ValueError("Published Contract release/PGP files differ from verified bytes")
        return control


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository-root", "destination", "trusted-source-sha",
                 "trusted-workflow-sha", "artifact-id", "artifact-sha256",
                 "validation-tree", "contract-version", "pgp-public-key",
                 "expected-pgp-key-sha256", "signing-home", "signing-fingerprint"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--release-handoff", action="append", default=[])
    args = parser.parse_args(argv)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        parser.error("GITHUB_EVENT_PATH is required")
    payload = load_json_bytes(read_regular_file_bytes(
        Path(event_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    ))
    if type(payload) is not dict:
        parser.error("Contract release event must be an object")
    event = os.environ.get("GITHUB_EVENT_NAME")
    producer = {
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "workflowPath": ".github/workflows/ci.yml",
        "commit": os.environ.get("GITHUB_SHA"), "tree": args.validation_tree,
        "event": event, "runId": int(os.environ["GITHUB_RUN_ID"]),
        "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "pullRequest": payload.get("number") if event == "pull_request" else None,
    }
    result = produce_contract_phase10_maven_handoff(
        Path(args.repository_root), Path(args.destination),
        trusted_source_sha=args.trusted_source_sha,
        trusted_workflow_sha=args.trusted_workflow_sha,
        artifact_id=int(args.artifact_id), artifact_sha256=args.artifact_sha256,
        transport_producer=producer, contract_version=args.contract_version,
        event_payload=payload, environment=os.environ,
        pgp_public_key=Path(args.pgp_public_key),
        expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        signing_home=Path(args.signing_home), signing_fingerprint=args.signing_fingerprint,
        passphrase=sys.stdin.read(), release_handoffs=tuple(map(Path, args.release_handoff)),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
