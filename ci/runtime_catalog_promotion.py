"""Build-free equal-tree aggregate catalog promotion from pinned caller code.

These context checks do not establish environment approval. The protected main
workflow owns that authority; this module neither activates a workflow nor builds
or re-signs Runtime products. Only the external product index is newly signed.
"""

from pathlib import Path
import os
import tempfile

import promote
import product_reuse as transport
from receipt import safe_extract
from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_regular_directory, require_sha256,
    sha256_bytes, sha256_file, snapshot_regular_tree, verified_zip_contents,
    write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.restore import object_relative_path, verify_phase_shard
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.sdk_package import _require_capability_output_separate
from products.sdk_protected_runtime import _original_carrier
from products.signatures import load_keyring, require_active_release_key


REPOSITORY = "codex-agent-labs/codex-agent"
JOB = "product-validation / runtime-aggregate-attestation"
_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def _json(path):
    value = load_canonical_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    if not isinstance(value, dict):
        raise ValueError("Promotion original control must be an object")
    return value


def _checkout(root, commit):
    root = Path(root).absolute()
    if root != Path(os.path.normpath(root)):
        raise ValueError("Promotion checkout must be normalized")
    for path in (root, *root.parents):
        require_regular_directory(path, "Promotion checkout ancestry")
    root = root.resolve(strict=True)
    if transport._git_value(root, "rev-parse", "HEAD") != commit:
        raise ValueError("Promotion checkout differs from its immutable commit pin")
    if transport._git_value(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Promotion checkout has modified tracked files")
    return root, transport._git_value(root, "rev-parse", "HEAD^{tree}")


def promote_runtime_aggregate_catalog(repository_root, candidate_root, destination, *,
        trusted_source_sha, trusted_workflow_sha, trusted_promotion_workflow_sha,
        final_commit, event_payload, environment, token):
    """Authenticate an original equal-tree upload and publish an external catalog.

    The independently pinned caller supplies all three pins. Original receipts,
    object ZIP and complete signed carrier remain byte-identical; the current
    authenticated upload and promotion context are retained outside the catalog.
    """
    for value in (trusted_source_sha, trusted_workflow_sha, trusted_promotion_workflow_sha, final_commit):
        promote.require_oid(value, "promotion caller pin")
    trusted, source_tree = _checkout(repository_root, trusted_source_sha)
    candidate, final_tree = _checkout(candidate_root, final_commit)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Promotion executable and candidate checkouts must be disjoint")
    expected = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": final_commit,
        "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/promote.yml@refs/heads/main",
        "GITHUB_WORKFLOW_SHA": trusted_promotion_workflow_sha,
    }
    if any(environment.get(name) != value for name, value in expected.items()):
        raise ValueError("Promotion requires the pinned protected-main push context")
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = environment.get(name)
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or str(int(value)) != value or int(value) < 1:
            raise ValueError("Promotion run/attempt must be an exact positive integer")
        expected[name] = value
    if (not isinstance(event_payload, dict)
            or not isinstance(event_payload.get("repository"), dict)
            or event_payload["repository"].get("full_name") != REPOSITORY
            or event_payload.get("ref") != "refs/heads/main"
            or event_payload.get("after") != final_commit or event_payload.get("deleted") is not False):
        raise ValueError("Promotion push payload differs from the final candidate")
    if not isinstance(token, str) or not token:
        raise ValueError("Promotion requires an original-upload observation token")
    producer = {"repository": REPOSITORY, "workflowPath": ".github/workflows/promote.yml",
        "event": "push", "commit": final_commit, "tree": final_tree, "pullRequest": None,
        "runId": int(expected["GITHUB_RUN_ID"]), "runAttempt": int(expected["GITHUB_RUN_ATTEMPT"])}
    destination = Path(destination).absolute()
    if destination != Path(os.path.normpath(destination)):
        raise ValueError("Promotion destination must be normalized")

    def output_safe():
        _require_capability_output_separate(destination, [trusted, candidate])
        for path in (destination, *destination.parents):
            if path.exists() or path.is_symlink():
                require_regular_directory(path, "Promotion output ancestry")
        if destination.exists():
            raise ValueError("Promotion destination must not exist")

    output_safe()
    with tempfile.TemporaryDirectory(prefix="runtime-catalog-promotion-") as temporary:
        private = Path(temporary).resolve()
        prepared = private / "output"
        trust = transport._release_trust(trusted, trusted_source_sha, prepared)
        if trust is None:
            raise ValueError("Promotion has no caller-pinned release policy")
        require_active_release_key(load_keyring(trust.keyring, trust.keys), trust.keys)
        policy_before = regular_file_inventory(prepared / "trust")
        selected = promote.selected_validation_run("https://api.github.com", REPOSITORY, final_tree, token)
        original = {"repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "event": "merge_group", "commit": promote.require_oid(selected.get("head_sha"), "original tested commit"),
            "tree": final_tree, "pullRequest": None,
            "runId": promote.positive_int(selected.get("id"), "original run"),
            "runAttempt": promote.positive_int(selected.get("run_attempt"), "original attempt")}
        observed = transport._observe_ci_producer_jobs({"aggregate": original},
            jobs_by_phase={"aggregate": JOB}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        run = observed[0]["run"]
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ValueError("Promotion requires a completed successful original CI attempt")
        name = f"codex-agent-runtime-aggregate-release-handoff-{final_tree}-attempt-{original['runAttempt']}"
        listed = promote.artifacts_for_run("https://api.github.com", REPOSITORY, original["runId"], token)
        if name not in listed:
            raise ValueError("Original equal-tree CI has no aggregate release upload")
        artifact, raw = transport._download_contract_ci_upload(listed[name]["id"], listed[name].get("digest"),
            name, original, run, token)
        transport._require_artifact_job_window(observed[0], JOB, artifact)
        evidence = prepared / "original-evidence"
        evidence.mkdir()
        archive = evidence / "upload.zip"
        archive.write_bytes(raw)
        inventory, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                               **transport._CATALOG_ZIP_LIMITS)
        uploaded = evidence / "original"
        safe_extract(archive, uploaded)
        if regular_file_inventory(uploaded, allow_empty=True) != inventory:
            raise ValueError("Original aggregate upload extraction differs from its archive")
        caller = _json(uploaded / "caller.json")
        if (caller.get("transportProducer") != original or caller.get("target") != "aggregate"
                or caller.get("trustedWorkflowSha") != trusted_workflow_sha):
            raise ValueError("Aggregate caller differs from its observed original upload")
        digest = require_sha256(caller.get("metadataReceiptSha256"), "Observed selected aggregate receipt")
        selection = _json(uploaded / "selected-inputs/selection.json")
        metadata = selection.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Original aggregate selection lacks exact metadata identity")
        key = require_sha256(metadata.get("buildKey"), "Observed selected aggregate key")
        if selection.get("producer") != original or metadata.get("receiptSha256") != digest:
            raise ValueError("Original aggregate selection differs from its observed caller")
        carrier = _original_carrier(uploaded, digest, key)
        unsigned = private / "unsigned"
        with verified_runtime_aggregate_handoff(carrier, keyring=trust.keyring, keys_directory=trust.keys) as verified:
            if sha256_bytes(verified["receiptBytes"][_METADATA]) != digest or verified["receipts"][_METADATA]["buildKey"] != key:
                raise ValueError("Signed aggregate differs from the original selected receipt/key")
            shard = verified["directory"] / "original-evidence/phases/runtime-aggregate-metadata-aggregate/original/shard"
            value = verify_phase_shard(shard, _METADATA)
            if value["receiptBytes"] != verified["receiptBytes"][_METADATA]:
                raise ValueError("Original aggregate object differs from the signed receipt")
            relative = object_relative_path(key, digest)
            output = unsigned / relative
            output.parent.mkdir(parents=True)
            output.write_bytes(read_regular_file_bytes(shard / relative))
            release = unsigned / "runtime-aggregate-release-evidence"
            handoff = f"handoffs/{digest.removeprefix('sha256:')}"
            snapshot_regular_tree(verified["directory"], release / handoff, allow_empty=True)
            write_canonical_json(release / "runtime-aggregate-release-evidence.json",
                                 [{"receiptSha256": digest, "handoffRoot": handoff}])

        def unchanged():
            if (_checkout(trusted, trusted_source_sha)[1] != source_tree
                    or _checkout(candidate, final_commit)[1] != final_tree
                    or regular_file_inventory(prepared / "trust") != policy_before
                    or regular_file_inventory(uploaded, allow_empty=True) != inventory
                    or sha256_file(archive) != artifact["digest"]):
                raise ValueError("Promotion original inputs changed before publication")

        unchanged()
        secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
        if not isinstance(secret, str) or not secret:
            raise ValueError("Promotion requires the protected release signing key")
        private_key = private / "signing-key"
        private_key.touch(mode=0o600, exist_ok=False)
        private_key.write_bytes(secret.encode("utf-8"))
        context = {"kind": "promoted-main", "commit": final_commit, "tree": final_tree,
            "promotionRunId": producer["runId"], "promotionRunAttempt": producer["runAttempt"]}
        index = transport.stage_promoted_aggregate_catalog(unsigned, prepared / "catalog",
            expected_build_key=key, expected_receipt_sha256=digest, repository=REPOSITORY,
            context=context, producer=producer, keyring=trust.keyring, keys_directory=trust.keys, private_key=private_key)
        write_canonical_json(evidence / "transport.json", {"artifact": artifact, "observed": observed,
            "captureProducer": original, "aggregateBuildKey": key, "aggregateReceiptSha256": digest})
        write_canonical_json(prepared / "caller.json", {"schemaVersion": 1, "producer": producer,
            "trustedSourceCommit": trusted_source_sha, "trustedSourceTree": source_tree,
            "trustedWorkflowSha": trusted_workflow_sha, "trustedPromotionWorkflowSha": trusted_promotion_workflow_sha,
            "environment": expected, "event": event_payload, "aggregateBuildKey": key,
            "aggregateReceiptSha256": digest})
        unchanged()
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return index
