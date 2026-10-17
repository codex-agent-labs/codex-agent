"""Prepare original Contract evidence without secrets; sign pinned bytes offline.

The protected workflow runs ``prepare`` with a GitHub observation token and no
signing secrets, then ``sign`` with product/PGP secrets and no GitHub token.
Neither command changes the reusable Contract ZIP.
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

from product_release_context import verify_product_release_context
from product_reuse import _release_trust, capture_contract_ci_artifact, capture_contract_original_ci_phases
from products.contract_attestation import build_contract_attestation
from products.contract_phase10_inventory import capture_contract_phase10_inventory
from products.contract_phase10_maven import (
    produce_contract_phase10_maven_sidecars, verify_contract_phase10_maven,
)
from products.inventory import (
    canonical_json_bytes, load_canonical_json, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_sha256,
    require_semver, sha256_bytes, sha256_file, snapshot_regular_tree, write_canonical_json,
)
from products.signatures import load_keyring, private_key_bytes, require_active_release_key

_SECRETS = ("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", "SIGNING_IN_MEMORY_KEY",
            "SIGNING_IN_MEMORY_KEY_PASSWORD")
_TOKENS = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN")


def _no_environment_values(environment: Mapping[str, str], names: tuple[str, ...], stage: str) -> None:
    if any(environment.get(name) for name in names):
        raise ValueError(f"Contract Maven {stage} must not receive forbidden credentials")


def _no_overlap(destination: Path, *sources: Path) -> None:
    output = destination.resolve(strict=False)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Phase-10 Maven destination already exists")
    for source in sources:
        resolved = Path(source).resolve(strict=True)
        if output == resolved or output in resolved.parents or resolved in output.parents:
            raise ValueError("Contract Phase-10 Maven destination overlaps an input")


def prepare_contract_phase10_maven_handoff(
    repository_root: Path, destination: Path, *, trusted_source_sha: str,
    trusted_workflow_sha: str, artifact_id: int, artifact_sha256: str,
    transport_producer: Mapping[str, Any], contract_version: str,
    event_payload: dict[str, Any], environment: Mapping[str, str],
    pgp_public_key: Path, expected_pgp_key_sha256: str, token: str | None = None,
    release_handoffs: tuple[Path, ...] = (),
    trusted_contract_workflow_path: str | None = None,
    trusted_contract_binary_job: str | None = None,
    trusted_contract_continuation_job: str | None = None,
) -> dict[str, Any]:
    """Capture and authenticate original CI and public policy, without any private key."""
    _no_environment_values(environment, _SECRETS, "prepare")
    _no_environment_values(os.environ, _SECRETS, "prepare")
    repository_root, destination, pgp_public_key = map(
        Path, (repository_root, destination, pgp_public_key),
    )
    _no_overlap(destination, repository_root, pgp_public_key, *release_handoffs)
    require_semver(contract_version, "Contract version")
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Contract PGP key digest")
    key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                  reject_symlink_parents=True)
    if not key or sha256_bytes(key) != expected_pgp_key_sha256:
        raise ValueError("Contract PGP public key differs from the independent pin")
    child_policy = (trusted_contract_workflow_path, trusted_contract_binary_job,
                    trusted_contract_continuation_job)
    if any(value is None for value in child_policy) and any(value is not None for value in child_policy):
        raise ValueError("Contract child workflow path and both jobs must be pinned together")
    capture_policy = ({} if trusted_contract_workflow_path is None else {
        "trusted_workflow_path": trusted_contract_workflow_path,
        "trusted_job_name": trusted_contract_continuation_job,
    })
    original_policy = ({} if trusted_contract_workflow_path is None else {
        "trusted_workflows_by_phase": {phase: {
            "path": trusted_contract_workflow_path, "sha": trusted_workflow_sha,
        } for phase in ("binary", "package", "validation", "metadata")},
        "jobs_by_phase": {phase: (trusted_contract_binary_job if phase == "binary"
                               else trusted_contract_continuation_job)
                          for phase in ("binary", "package", "validation", "metadata")},
    })
    repository_root, producer, source_tree, expected_environment, reason = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha,
        trusted_workflow_sha=trusted_workflow_sha, transport_producer=transport_producer,
        event_payload=event_payload, environment=environment,
    )
    observation_token = token if token is not None else environment.get("GITHUB_TOKEN")
    if type(observation_token) is not str or not observation_token:
        raise ValueError("Contract Maven prepare requires a GitHub observation token")
    with tempfile.TemporaryDirectory(prefix="ct-p10-maven-prepare-") as temporary:
        root = Path(temporary).resolve()
        trust = _release_trust(repository_root, trusted_source_sha, root)
        if trust is None:
            raise ValueError("No active release product-signing key is configured")
        policy = load_keyring(trust.keyring, trust.keys)
        require_active_release_key(policy, trust.keys)
        capture = root / "current-upload"
        capture_contract_ci_artifact(
            capture, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            transport_producer=producer, trusted_workflow_sha=trusted_workflow_sha,
            contract_version=contract_version, token=observation_token, **capture_policy,
        )
        prepared = root / "prepared"
        originals = prepared / "original-evidence"
        capture_contract_original_ci_phases(
            capture, originals, contract_version=contract_version,
            trusted_workflow_sha=trusted_workflow_sha, token=observation_token,
            release_handoffs=release_handoffs,
            keyring=trust.keyring if release_handoffs else None,
            keys_directory=trust.keys if release_handoffs else None,
            **original_policy,
        )
        snapshot_regular_tree(root / "trust", prepared / "caller-policy")
        (prepared / "publication-pgp-public-key.asc").write_bytes(key)
        caller = {
            "schemaVersion": 1, "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason,
            "event": event_payload,
            "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")},
        }
        write_canonical_json(prepared / "caller.json", caller)
        selection = {
            "schemaVersion": 1, "contractVersion": contract_version,
            "pgpPublicKeySha256": expected_pgp_key_sha256,
            "preparedFiles": regular_file_inventory(prepared),
        }
        write_canonical_json(prepared / "preparation.json", selection)
        expected_files = regular_file_inventory(prepared)
        if (regular_file_inventory(root / "trust") != regular_file_inventory(prepared / "caller-policy")
                or read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                           reject_symlink_parents=True) != key
                or regular_file_inventory(prepared) != expected_files):
            raise ValueError("Contract Maven original evidence or public policy changed")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
        return selection


def sign_contract_phase10_maven_handoff(
    prepared: Path, destination: Path, *, expected_preparation_sha256: str,
    expected_pgp_key_sha256: str, signing_home: Path, signing_fingerprint: str,
    product_private_key: str, passphrase: str, environment: Mapping[str, str],
) -> dict[str, Any]:
    """Sign the already pinned local Contract bytes, without an observation token."""
    _no_environment_values(environment, _TOKENS, "sign")
    _no_environment_values(os.environ, _TOKENS, "sign")
    prepared, destination, signing_home = map(Path, (prepared, destination, signing_home))
    _no_overlap(destination, prepared, signing_home)
    if type(product_private_key) is not str or not product_private_key:
        raise ValueError("Protected Contract product signing key is unavailable")
    expected_preparation_sha256 = require_sha256(expected_preparation_sha256, "Contract preparation digest")
    expected_pgp_key_sha256 = require_sha256(expected_pgp_key_sha256, "Contract PGP key digest")
    selection_path = prepared / "preparation.json"
    selection_bytes = read_regular_file_bytes(selection_path, max_bytes=16 * 1024 * 1024,
                                              reject_symlink_parents=True)
    if sha256_bytes(selection_bytes) != expected_preparation_sha256:
        raise ValueError("Contract Maven preparation differs from independent pin")
    selection = load_canonical_json(selection_path)
    require_exact_keys(selection, {"schemaVersion", "contractVersion", "pgpPublicKeySha256",
                                   "preparedFiles"}, "Contract Maven preparation")
    if selection["schemaVersion"] != 1 or selection["pgpPublicKeySha256"] != expected_pgp_key_sha256:
        raise ValueError("Contract Maven preparation identity differs from protected policy")
    contract_version = require_semver(selection["contractVersion"], "Contract version")
    expected_files = selection["preparedFiles"]
    if type(expected_files) is not list or regular_file_inventory(prepared) != sorted([
        *expected_files,
        {"relativePath": "preparation.json", "bytes": len(selection_bytes),
         "sha256": sha256_bytes(selection_bytes)},
    ], key=lambda item: item["relativePath"]):
        raise ValueError("Contract Maven preparation inventory differs from its pin")
    pgp_public_key = prepared / "publication-pgp-public-key.asc"
    pgp_key = read_regular_file_bytes(pgp_public_key, max_bytes=1024 * 1024,
                                      reject_symlink_parents=True)
    if not pgp_key or sha256_bytes(pgp_key) != expected_pgp_key_sha256:
        raise ValueError("Contract PGP public key differs from protected pin")
    keyring = prepared / "caller-policy/product-signing-keys.json"
    keys = prepared / "caller-policy/keys"
    policy = load_keyring(keyring, keys)
    active, public_key = require_active_release_key(policy, keys)
    signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
    signing.update(active)
    originals = prepared / "original-evidence"
    authenticated = originals / "contract-input"
    closure = authenticated / "execution-closure"
    payload_path = authenticated / f"phases/metadata/stage/outputs/codex-agent-contract-{contract_version}.zip"
    with tempfile.TemporaryDirectory(prefix="ct-p10-maven-sign-") as temporary:
        root = Path(temporary).resolve()
        published = root / "published"
        release = published / "contract-release-evidence"
        release.mkdir(parents=True)
        snapshot_regular_tree(originals, release / "original-evidence")
        snapshot_regular_tree(prepared / "caller-policy", release / "caller-policy")
        (release / "caller.json").write_bytes(read_regular_file_bytes(
            prepared / "caller.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        retained = None
        for number in range(len([path for path in (originals / "release-handoffs").glob("*")
                                 if path.is_dir()]) if (originals / "release-handoffs").exists() else 0):
            candidate = originals / "release-handoffs" / str(number)
            if (regular_file_inventory(candidate / "execution-closure") == regular_file_inventory(closure)
                    and sha256_file(candidate / payload_path.name) == sha256_file(payload_path)):
                retained = candidate
                break
        if retained is not None:
            snapshot_regular_tree(retained, release / "contract-input")
        else:
            private = root / "product-private-key"
            private.touch(mode=0o600, exist_ok=False)
            private.write_bytes(private_key_bytes(product_private_key))
            build_contract_attestation(
                payload_path, closure / "receipts/metadata.json", signing, private, public_key,
                release / "contract-input", execution_closure=closure,
                keyring=keyring, keys_directory=keys, complete_handoff=True,
            )
        payload = release / "contract-input" / f"codex-agent-contract-{contract_version}.zip"
        record = capture_contract_phase10_inventory(
            release / "contract-input", keyring, keys, root / "verified-contract",
        )
        if record["contractVersion"] != contract_version:
            raise ValueError("Authenticated Contract version differs from requested version")
        signed = produce_contract_phase10_maven_sidecars(
            payload, published / "maven-sidecars", pgp_public_key,
            expected_pgp_key_sha256, signing_home, signing_fingerprint, passphrase,
        )
        if signed["contractVersion"] != contract_version or signed["payloadSha256"] != next(
            item["sha256"] for item in record["handoffFiles"]
            if item["relativePath"] == payload.name
        ):
            raise ValueError("Contract PGP signatures differ from the attested payload")
        (published / "publication-pgp-public-key.asc").write_bytes(pgp_key)
        control = {
            "schemaVersion": 1,
            "releaseCaller": load_canonical_json(prepared / "caller.json"),
            "releaseFiles": regular_file_inventory(release),
            "contractInventory": record, "mavenSidecars": signed,
        }
        write_canonical_json(published / "sidecar-selection.json", control)
        expected_output = regular_file_inventory(published)
        if (regular_file_inventory(prepared) != sorted([
            *expected_files,
            {"relativePath": "preparation.json", "bytes": len(selection_bytes),
             "sha256": sha256_bytes(selection_bytes)},
        ], key=lambda item: item["relativePath"])
                or verify_contract_phase10_maven(payload, published / "maven-sidecars",
                                                  pgp_public_key, expected_pgp_key_sha256) != signed
                or regular_file_inventory(published) != expected_output):
            raise ValueError("Contract Maven prepared or signed files changed before publication")
        publish_regular_tree(published, destination, expected_inventory=expected_output)
        return control


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    prepare = modes.add_parser("prepare")
    for name in ("repository-root", "destination", "trusted-source-sha", "trusted-workflow-sha",
                 "artifact-id", "artifact-sha256", "validation-tree", "contract-version",
                 "pgp-public-key", "expected-pgp-key-sha256"):
        prepare.add_argument(f"--{name}", required=True)
    for name in ("trusted-contract-workflow-path", "trusted-contract-binary-job",
                 "trusted-contract-continuation-job"):
        prepare.add_argument(f"--{name}")
    prepare.add_argument("--release-handoff", action="append", default=[])
    sign = modes.add_parser("sign")
    for name in ("prepared", "destination", "expected-preparation-sha256",
                 "expected-pgp-key-sha256", "signing-home", "signing-fingerprint"):
        sign.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        _no_environment_values(os.environ, _SECRETS, "prepare")
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            parser.error("GITHUB_EVENT_PATH is required")
        event_payload = load_json_bytes(read_regular_file_bytes(
            Path(event_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        ))
        if type(event_payload) is not dict:
            parser.error("Contract release event must be an object")
        event = os.environ.get("GITHUB_EVENT_NAME")
        producer = {
            "repository": os.environ.get("GITHUB_REPOSITORY"),
            "workflowPath": ".github/workflows/ci.yml",
            "commit": os.environ.get("GITHUB_SHA"), "tree": args.validation_tree,
            "event": event, "runId": int(os.environ["GITHUB_RUN_ID"]),
            "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
            "pullRequest": event_payload.get("number") if event == "pull_request" else None,
        }
        result = prepare_contract_phase10_maven_handoff(
            Path(args.repository_root), Path(args.destination),
            trusted_source_sha=args.trusted_source_sha,
            trusted_workflow_sha=args.trusted_workflow_sha,
            trusted_contract_workflow_path=args.trusted_contract_workflow_path,
            trusted_contract_binary_job=args.trusted_contract_binary_job,
            trusted_contract_continuation_job=args.trusted_contract_continuation_job,
            artifact_id=int(args.artifact_id), artifact_sha256=args.artifact_sha256,
            transport_producer=producer, contract_version=args.contract_version,
            event_payload=event_payload, environment=os.environ,
            pgp_public_key=Path(args.pgp_public_key),
            expected_pgp_key_sha256=args.expected_pgp_key_sha256,
            release_handoffs=tuple(map(Path, args.release_handoff)),
        )
        print(json.dumps({"preparationSha256": sha256_bytes(canonical_json_bytes(result))},
                         sort_keys=True, separators=(",", ":")))
    else:
        _no_environment_values(os.environ, _TOKENS, "sign")
        result = sign_contract_phase10_maven_handoff(
            Path(args.prepared), Path(args.destination),
            expected_preparation_sha256=args.expected_preparation_sha256,
            expected_pgp_key_sha256=args.expected_pgp_key_sha256,
            signing_home=Path(args.signing_home), signing_fingerprint=args.signing_fingerprint,
            product_private_key=os.environ.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", ""),
            passphrase=sys.stdin.read(), environment=os.environ,
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
