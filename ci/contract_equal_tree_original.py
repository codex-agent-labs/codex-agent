"""Capture one release-attested Contract upload from exact equal-tree CI.

The protected main caller supplies the reviewed executable/workflow pins and
environment approval. This locator checks that context and the official
selected run/job/upload; it does not sign, promote, or publish product bytes.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import promote
import product_reuse as transport
from receipt import safe_extract
from runtime_catalog_promotion import _checkout
from products.contract_phase10_inventory import capture_contract_phase10_inventory
from products.inventory import (
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_semver, require_sha256, sha256_bytes, sha256_file, verified_zip_contents,
    write_canonical_json,
)
from products.sdk_package import _require_capability_output_separate


REPOSITORY = "codex-agent-labs/codex-agent"
JOB = "product-validation / contract-attestation"


def capture_equal_tree_contract_original(
    repository_root: Path, candidate_root: Path, destination: Path, *,
    trusted_source_sha: str, trusted_workflow_sha: str,
    trusted_promotion_workflow_sha: str, final_commit: str,
    event_payload: dict, environment: dict, token: str,
) -> dict:
    """Retain original bytes only after protected equal-tree upload admission.

    Environment approval itself remains workflow-owned. The returned carrier
    is external evidence, never a new reusable Contract payload or signature.
    """
    for value in (trusted_source_sha, trusted_workflow_sha,
                  trusted_promotion_workflow_sha, final_commit):
        promote.require_oid(value, "Contract promotion caller pin")
    trusted, trusted_tree = _checkout(repository_root, trusted_source_sha)
    candidate, final_tree = _checkout(candidate_root, final_commit)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Contract promotion executable and candidate checkouts must be disjoint")
    expected = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": final_commit,
        "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/promote.yml@refs/heads/main",
        "GITHUB_WORKFLOW_SHA": trusted_promotion_workflow_sha,
    }
    if any(environment.get(name) != value for name, value in expected.items()):
        raise ValueError("Contract original selection requires pinned protected-main push context")
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        raw = environment.get(name)
        if type(raw) is not str or not raw.isascii() or not raw.isdecimal() or \
                str(int(raw)) != raw or int(raw) < 1:
            raise ValueError("Contract promotion run/attempt must be an exact positive integer")
        expected[name] = raw
    if (type(event_payload) is not dict or type(event_payload.get("repository")) is not dict
            or event_payload["repository"].get("full_name") != REPOSITORY
            or event_payload.get("ref") != "refs/heads/main"
            or event_payload.get("after") != final_commit
            or event_payload.get("deleted") is not False):
        raise ValueError("Contract promotion push payload differs from the final candidate")
    if type(token) is not str or not token:
        raise ValueError("Contract original selection requires an observation token")
    raw_version = git_regular_blob_bytes(candidate, final_commit,
                                         "gradle/release/versions/contract.txt", max_bytes=256)
    if raw_version.count(b"\n") != 1 or not raw_version.endswith(b"\n"):
        raise ValueError("Landed Contract version must be one SemVer line with LF")
    version = require_semver(raw_version[:-1].decode("ascii"), "Landed Contract version")
    destination = Path(destination).absolute()
    if destination != Path(os.path.normpath(destination)):
        raise ValueError("Contract original destination must be normalized")

    def output_safe() -> None:
        _require_capability_output_separate(destination, [trusted, candidate])
        if destination.exists() or destination.is_symlink():
            raise ValueError("Contract original destination must not exist")

    output_safe()
    with tempfile.TemporaryDirectory(prefix="contract-equal-tree-original-") as temporary:
        root = Path(temporary).resolve()
        source_trust = transport._release_trust(trusted, trusted_source_sha, root / "source-policy")
        candidate_trust = transport._release_trust(candidate, final_commit, root / "candidate-policy")
        if source_trust is None or candidate_trust is None or \
                regular_file_inventory(source_trust.keyring.parent) != regular_file_inventory(candidate_trust.keyring.parent):
            raise ValueError("Contract release keyring differs between executable and landed tree")
        policy_inventory = regular_file_inventory(source_trust.keyring.parent)

        selected = promote.selected_validation_run("https://api.github.com", REPOSITORY, final_tree, token)
        producer = {"repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
                    "event": "merge_group", "commit": promote.require_oid(selected.get("head_sha"), "validated commit"),
                    "tree": final_tree, "pullRequest": None,
                    "runId": promote.positive_int(selected.get("id"), "validated run"),
                    "runAttempt": promote.positive_int(selected.get("run_attempt"), "validated attempt")}
        observed = transport._observe_ci_producer_jobs(
            {"attestation": producer}, jobs_by_phase={"attestation": JOB},
            trusted_workflow_sha=trusted_workflow_sha, token=token,
        )
        run = observed[0]["run"]
        if run.get("status") != "completed" or run.get("conclusion") != "success" or \
                selected.get("conclusion") != "success":
            raise ValueError("Contract original CI attempt is not successful")
        name = f"codex-agent-contract-release-handoff-{final_tree}"
        listed = promote.artifacts_for_run("https://api.github.com", REPOSITORY, producer["runId"], token)
        if name not in listed:
            raise ValueError("Equal-tree CI has no Contract release handoff upload")
        artifact, raw = transport._download_contract_ci_upload(
            listed[name]["id"], require_sha256(listed[name].get("digest"), "Contract upload digest"),
            name, producer, run, token,
        )
        transport._require_artifact_job_window(observed[0], JOB, artifact)

        prepared = root / "prepared"
        evidence = prepared / "original-evidence"
        evidence.mkdir(parents=True)
        archive = evidence / "upload.zip"
        archive.write_bytes(raw)
        inventory, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True, **transport._CATALOG_ZIP_LIMITS,
        )
        uploaded = evidence / "upload"
        safe_extract(archive, uploaded)
        if regular_file_inventory(uploaded, allow_empty=True) != inventory:
            raise ValueError("Contract original upload extraction differs from its archive")
        caller = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            uploaded / "caller.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )), {"schemaVersion", "trustedSourceCommit", "trustedSourceTree", "trustedWorkflowSha",
             "transportProducer", "authorizationReason", "event", "environment"},
            "Original Contract release caller")
        if caller["schemaVersion"] != 1 or caller["trustedSourceCommit"] != trusted_source_sha or \
                caller["trustedSourceTree"] != trusted_tree or \
                caller["trustedWorkflowSha"] != trusted_workflow_sha or \
                caller["transportProducer"] != producer:
            raise ValueError("Original Contract release caller differs from observed equal-tree CI")
        uploaded_policy = uploaded / "caller-policy"
        if regular_file_inventory(uploaded_policy) != policy_inventory:
            raise ValueError("Original Contract release caller keyring differs from trusted Git")
        captured = prepared / "contract-record"
        record = capture_contract_phase10_inventory(
            uploaded / "contract-input", source_trust.keyring, source_trust.keys, captured,
        )
        if record["contractVersion"] != version:
            raise ValueError("Original Contract version differs from the landed tree")
        selection = {"schemaVersion": 1, "finalCommit": final_commit, "finalTree": final_tree,
                     "trustedSourceCommit": trusted_source_sha, "trustedSourceTree": trusted_tree,
                     "trustedWorkflowSha": trusted_workflow_sha,
                     "trustedPromotionWorkflowSha": trusted_promotion_workflow_sha,
                     "originalProducer": producer, "artifact": artifact,
                     "contractVersion": version, "handoffInventory": record}
        write_canonical_json(prepared / "selection.json", selection)
        observations = {
            "selectedValidationRun": selected, "originalAttempt": observed,
            "promotionRunId": int(expected["GITHUB_RUN_ID"]),
            "promotionRunAttempt": int(expected["GITHUB_RUN_ATTEMPT"]),
            "promotionEvent": event_payload, "promotionEnvironment": expected,
        }
        write_canonical_json(prepared / "observations.json", observations)
        selection_bytes = canonical_json_bytes(selection)
        observations_bytes = canonical_json_bytes(observations)
        record_bytes = canonical_json_bytes(record)
        expected_inventory = sorted([
            {"relativePath": "original-evidence/upload.zip", "bytes": len(raw),
             "sha256": artifact["digest"]},
            *({**item, "relativePath": f"original-evidence/upload/{item['relativePath']}"}
              for item in inventory),
            *({**item, "relativePath": f"contract-record/handoff/{item['relativePath']}"}
              for item in record["handoffFiles"]),
            *({**item, "relativePath": f"contract-record/policy/keys/{item['relativePath']}"}
              for item in record["verifierKeys"]),
            {"relativePath": "contract-record/policy/keyring.json", **record["verifierKeyring"]},
            {"relativePath": "contract-record/inventory.json", "bytes": len(record_bytes),
             "sha256": sha256_bytes(record_bytes)},
            {"relativePath": "selection.json", "bytes": len(selection_bytes),
             "sha256": sha256_bytes(selection_bytes)},
            {"relativePath": "observations.json", "bytes": len(observations_bytes),
             "sha256": sha256_bytes(observations_bytes)},
        ], key=lambda item: item["relativePath"])
        if (_checkout(trusted, trusted_source_sha)[1] != trusted_tree
                or _checkout(candidate, final_commit)[1] != final_tree
                or regular_file_inventory(source_trust.keyring.parent) != policy_inventory
                or regular_file_inventory(uploaded, allow_empty=True) != inventory
                or sha256_file(archive) != artifact["digest"]
                or regular_file_inventory(prepared, allow_empty=True) != expected_inventory):
            raise ValueError("Contract equal-tree original changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True,
                             expected_inventory=expected_inventory)
    return selection


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository-root", "candidate-root", "destination"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("trusted-source-sha", "trusted-workflow-sha",
                 "trusted-promotion-workflow-sha", "final-commit"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        parser.error("GITHUB_EVENT_PATH is required")
    try:
        event = load_json_bytes(read_regular_file_bytes(
            Path(event_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        if type(event) is not dict:
            raise ValueError("Push event must be a JSON object")
    except (OSError, ValueError):
        parser.error("GITHUB_EVENT_PATH must name a safe regular JSON event object")
    capture_equal_tree_contract_original(
        args.repository_root, args.candidate_root, args.destination,
        trusted_source_sha=args.trusted_source_sha,
        trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_promotion_workflow_sha=args.trusted_promotion_workflow_sha,
        final_commit=args.final_commit, event_payload=event,
        environment=os.environ, token=os.environ.get("GITHUB_TOKEN"),
    )


if __name__ == "__main__":
    main()
