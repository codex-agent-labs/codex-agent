#!/usr/bin/env python3
"""Protected caller composition; the workflow must execute independently pinned code.

Git/context checks here are sanity checks, not self-authentication of candidate
code or proof of environment approval. No downloaded input is executable.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import os
from pathlib import Path
import tempfile
from typing import Any

from product_release_context import verify_product_release_context
from product_reuse import (
    _release_trust, capture_contract_ci_artifact,
    capture_contract_original_ci_phases,
)
from products.contract_attestation import build_contract_attestation
from products.inventory import (
    load_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_semver, sha256_file, snapshot_regular_tree, write_canonical_json,
)
from products.signatures import load_keyring, require_active_release_key


def attest_contract_ci(
    repository_root: Path, destination: Path, *, trusted_source_sha: str,
    trusted_workflow_sha: str, artifact_id: int, artifact_sha256: str,
    transport_producer: Mapping[str, Any], contract_version: str,
    event_payload: dict[str, Any], environment: Mapping[str, str],
    token: str | None = None, release_handoffs: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Authenticate original bytes before key access; publish external evidence once."""
    require_semver(contract_version, "Contract release version")
    repository_root, producer, source_tree, expected_environment, reason = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    payload = event_payload
    destination = Path(os.path.abspath(destination))
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract caller destination must not exist")
    resolved_output = destination.parent.resolve(strict=False) / destination.name
    for original in (repository_root, *release_handoffs):
        source = Path(original).resolve(strict=True)
        if source == resolved_output or source in resolved_output.parents or resolved_output in source.parents:
            raise ValueError("Contract caller destination overlaps trusted source or release evidence")

    with tempfile.TemporaryDirectory(prefix="contract-release-caller-") as temporary:
        root = Path(temporary).resolve()
        trust = _release_trust(repository_root, trusted_source_sha, root)
        if trust is None:
            raise ValueError("No active release product-signing key is configured")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public_key = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if token is None:
            token = environment.get("GITHUB_TOKEN")
        if type(token) is not str or not token:
            raise ValueError("Contract caller requires a GitHub observation token")
        capture = root / "current-upload"
        capture_contract_ci_artifact(
            capture, artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            transport_producer=producer, trusted_workflow_sha=trusted_workflow_sha,
            contract_version=contract_version, token=token,
        )
        prepared = root / "prepared"
        originals = prepared / "original-evidence"
        capture_contract_original_ci_phases(
            capture, originals, contract_version=contract_version,
            trusted_workflow_sha=trusted_workflow_sha, token=token,
            release_handoffs=release_handoffs,
            keyring=trust.keyring if release_handoffs else None,
            keys_directory=trust.keys if release_handoffs else None,
        )
        authenticated = originals / "contract-input"
        closure = authenticated / "execution-closure"
        payload_path = authenticated / f"phases/metadata/stage/outputs/codex-agent-contract-{contract_version}.zip"
        retained = None
        for number in range(len(release_handoffs)):
            candidate = originals / "release-handoffs" / str(number)
            if regular_file_inventory(candidate / "execution-closure") == regular_file_inventory(closure) and \
                    sha256_file(candidate / payload_path.name) == sha256_file(payload_path):
                retained = candidate
                break
        if retained is not None:
            # S667 already authenticated this exact release envelope under the captured policy.
            snapshot_regular_tree(retained, prepared / "contract-input")
        else:
            secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
            if type(secret) is not str or not secret:
                raise ValueError("Protected Contract signing key is unavailable")
            private_key = root / "private-key"
            private_key.touch(mode=0o600, exist_ok=False)
            private_key.write_bytes(secret.encode("utf-8"))
            build_contract_attestation(
                payload_path, closure / "receipts/metadata.json", signing, private_key, public_key,
                prepared / "contract-input", execution_closure=closure,
                keyring=trust.keyring, keys_directory=trust.keys, complete_handoff=True,
            )
        # Public policy and current-caller provenance are external, never payload inputs.
        snapshot_regular_tree(root / "trust", prepared / "caller-policy")
        caller = {
            "schemaVersion": 1, "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason,
            "event": payload, "environment": {**expected_environment, "GITHUB_REF": environment.get("GITHUB_REF")},
        }
        write_canonical_json(prepared / "caller.json", caller)
        publish_regular_tree(prepared, destination)
    return caller


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--trusted-source-sha", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--validation-tree", required=True)
    parser.add_argument("--contract-version", required=True)
    parser.add_argument("--release-handoff", type=Path, action="append", default=[])
    arguments = parser.parse_args()
    payload = load_json_bytes(read_regular_file_bytes(
        Path(os.environ["GITHUB_EVENT_PATH"]), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    event = os.environ.get("GITHUB_EVENT_NAME")
    producer = {
        "repository": os.environ.get("GITHUB_REPOSITORY"), "workflowPath": ".github/workflows/ci.yml",
        "commit": os.environ.get("GITHUB_SHA"), "tree": arguments.validation_tree, "event": event,
        "runId": int(os.environ["GITHUB_RUN_ID"]), "runAttempt": int(os.environ["GITHUB_RUN_ATTEMPT"]),
        "pullRequest": payload.get("number") if event == "pull_request" else None,
    }
    attest_contract_ci(
        arguments.repository_root, arguments.destination, trusted_source_sha=arguments.trusted_source_sha,
        trusted_workflow_sha=arguments.trusted_workflow_sha, artifact_id=arguments.artifact_id,
        artifact_sha256=arguments.artifact_sha256, transport_producer=producer,
        contract_version=arguments.contract_version, event_payload=payload, environment=os.environ,
        release_handoffs=tuple(arguments.release_handoff),
    )


if __name__ == "__main__":
    main()
