"""Build-free equal-tree aggregate catalog promotion from pinned caller code.

These context checks do not establish environment approval. The protected main
workflow owns that authority; this module neither activates a workflow nor builds
or re-signs Runtime products. Only the external product index is newly signed.
"""

import argparse
from pathlib import Path
import os
import sys
import tempfile

if __package__:
    # Match standalone CI entrypoints and their canonical products namespace.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import promote
import product_reuse as transport
from receipt import safe_extract
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory, require_sha256,
    sha256_bytes, sha256_file, snapshot_regular_tree, verified_zip_contents,
    write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.restore import object_relative_path, verify_phase_shard
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.sdk_package import _require_capability_output_separate
from products.sdk_protected_runtime import _original_carrier
from products.signatures import load_keyring, private_key_bytes, require_active_release_key
from products.signing_isolation import require_no_signing_secret


REPOSITORY = "codex-agent-labs/codex-agent"
JOB = "product-validation / runtime-aggregate-attestation"
_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
_OBSERVATION_TOKENS = frozenset({
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
})
_CAPTURE_SECRETS = frozenset({
    "SIGNING_IN_MEMORY_KEY", "SIGNING_IN_MEMORY_KEY_PASSWORD",
    "CODEX_AGENT_SDK_RUNTIME_ROOT_ED25519_PRIVATE_KEY",
})


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


def capture_promotable_runtime_aggregate_catalog(repository_root, candidate_root, destination, *,
        trusted_source_sha, trusted_workflow_sha, trusted_promotion_workflow_sha,
        final_commit, expected_validation_tree, expected_build_key,
        expected_receipt_sha256, expected_object_sha256, expected_original_commit,
        expected_original_run_id, expected_original_run_attempt, expected_upload_artifact_id,
        expected_upload_sha256, expected_carrier_inventory_sha256,
        expected_attestation_sha256, expected_signature_sha256,
        event_payload, environment, token):
    """Authenticate an original equal-tree upload without any signing secret.

    The protected caller supplies source/workflow pins and the exact S1048
    validated tree, original producer/upload, metadata key/receipt/object and
    signed-carrier digests. Original receipts,
    object ZIP and complete signed carrier remain byte-identical; the current
    authenticated upload and promotion context are retained outside the catalog.
    """
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    if _CAPTURE_SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("Runtime catalog capture must not receive signing secrets")
    for value in (trusted_source_sha, trusted_workflow_sha, trusted_promotion_workflow_sha, final_commit):
        promote.require_oid(value, "promotion caller pin")
    trusted, source_tree = _checkout(repository_root, trusted_source_sha)
    candidate, final_tree = _checkout(candidate_root, final_commit)
    promote.require_oid(expected_validation_tree, "S1048 validated tree")
    selected_key = require_sha256(expected_build_key, "S1048 aggregate metadata build key")
    selected_receipt = require_sha256(expected_receipt_sha256, "S1048 aggregate metadata receipt")
    selected_object = require_sha256(expected_object_sha256, "S1048 aggregate metadata object")
    selected_original_commit = promote.require_oid(expected_original_commit, "S1048 original commit")
    selected_run_id = promote.positive_int(expected_original_run_id, "S1048 original run")
    selected_run_attempt = promote.positive_int(expected_original_run_attempt, "S1048 original attempt")
    selected_upload_id = promote.positive_int(expected_upload_artifact_id, "S1048 upload artifact")
    selected_upload = require_sha256(expected_upload_sha256, "S1048 upload")
    selected_carrier = require_sha256(expected_carrier_inventory_sha256, "S1048 carrier inventory")
    selected_attestation = require_sha256(expected_attestation_sha256, "S1048 aggregate attestation")
    selected_signature = require_sha256(expected_signature_sha256, "S1048 aggregate signature")
    if final_tree != expected_validation_tree:
        raise ValueError("Promotion landed tree differs from the S1048 validated tree")
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
        original = {"repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
            "event": "merge_group", "commit": selected_original_commit,
            "tree": final_tree, "pullRequest": None,
            "runId": selected_run_id, "runAttempt": selected_run_attempt}
        observed = transport._observe_ci_producer_jobs({"aggregate": original},
            jobs_by_phase={"aggregate": JOB}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        run = observed[0]["run"]
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise ValueError("Promotion requires a completed successful original CI attempt")
        name = f"codex-agent-runtime-aggregate-release-handoff-{final_tree}-attempt-{original['runAttempt']}"
        listed = promote.artifacts_for_run("https://api.github.com", REPOSITORY, original["runId"], token)
        if name not in listed:
            raise ValueError("Original equal-tree CI has no aggregate release upload")
        if listed[name].get("id") != selected_upload_id or listed[name].get("digest") != selected_upload:
            raise ValueError("Original aggregate upload differs from S1048 selection")
        artifact, raw = transport._download_contract_ci_upload(selected_upload_id, selected_upload,
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
        if (key, digest) != (selected_key, selected_receipt):
            raise ValueError("Original aggregate identity differs from S1048 selection")
        carrier = _original_carrier(uploaded, digest, key)
        unsigned = prepared / "unsigned"
        with verified_runtime_aggregate_handoff(carrier, keyring=trust.keyring, keys_directory=trust.keys) as verified:
            carrier_inventory = verified["inventory"]
            if sha256_bytes(canonical_json_bytes(carrier_inventory)) != selected_carrier:
                raise ValueError("Original aggregate carrier differs from S1048 selection")
            if (sha256_file(verified["indexInputs"]["attestation"]) != selected_attestation
                    or sha256_file(verified["indexInputs"]["signature"]) != selected_signature):
                raise ValueError("Original aggregate attestation/signature differs from S1048 selection")
            if sha256_bytes(verified["receiptBytes"][_METADATA]) != digest or verified["receipts"][_METADATA]["buildKey"] != key:
                raise ValueError("Signed aggregate differs from the original selected receipt/key")
            shard = verified["directory"] / "original-evidence/phases/runtime-aggregate-metadata-aggregate/original/shard"
            value = verify_phase_shard(shard, _METADATA)
            if value["receiptBytes"] != verified["receiptBytes"][_METADATA]:
                raise ValueError("Original aggregate object differs from the signed receipt")
            relative = object_relative_path(key, digest)
            if sha256_file(shard / relative) != selected_object:
                raise ValueError("Original aggregate object differs from S1048 selection")
            output = unsigned / relative
            output.parent.mkdir(parents=True)
            output.write_bytes(read_regular_file_bytes(shard / relative))
            release = unsigned / "runtime-aggregate-release-evidence"
            handoff = f"handoffs/{digest.removeprefix('sha256:')}"
            snapshot_regular_tree(verified["directory"], release / handoff, allow_empty=True)
            if regular_file_inventory(release / handoff, allow_empty=True) != carrier_inventory:
                raise ValueError("Copied aggregate carrier differs from S1048 selection")
            write_canonical_json(release / "runtime-aggregate-release-evidence.json",
                                 [{"receiptSha256": digest, "handoffRoot": handoff}])

        def unchanged():
            if (_checkout(trusted, trusted_source_sha)[1] != source_tree
                    or _checkout(candidate, final_commit)[1] != final_tree
                    or regular_file_inventory(prepared / "trust") != policy_before
                    or regular_file_inventory(uploaded, allow_empty=True) != inventory
                    or sha256_file(archive) != selected_upload
                    or sha256_file(unsigned / object_relative_path(key, digest)) != selected_object
                    or regular_file_inventory(release / handoff, allow_empty=True) != carrier_inventory):
                raise ValueError("Promotion original inputs changed before publication")

        unchanged()
        write_canonical_json(evidence / "transport.json", {"artifact": artifact, "observed": observed,
            "captureProducer": original, "aggregateBuildKey": key, "aggregateReceiptSha256": digest,
            "aggregateObjectSha256": selected_object, "carrierInventorySha256": selected_carrier,
            "aggregateAttestationSha256": selected_attestation,
            "aggregateSignatureSha256": selected_signature})
        write_canonical_json(prepared / "caller.json", {"schemaVersion": 1, "producer": producer,
            "trustedSourceCommit": trusted_source_sha, "trustedSourceTree": source_tree,
            "trustedWorkflowSha": trusted_workflow_sha, "trustedPromotionWorkflowSha": trusted_promotion_workflow_sha,
            "environment": expected, "event": event_payload, "aggregateBuildKey": key,
            "aggregateReceiptSha256": digest, "aggregateObjectSha256": selected_object,
            "validatedTree": expected_validation_tree,
            "originalProducer": original, "originalUploadArtifactId": selected_upload_id,
            "originalUploadSha256": selected_upload, "carrierInventorySha256": selected_carrier,
            "aggregateAttestationSha256": selected_attestation,
            "aggregateSignatureSha256": selected_signature})
        unchanged()
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return {"captureInventorySha256": sha256_bytes(canonical_json_bytes(
        regular_file_inventory(destination, allow_empty=True))), "producer": producer}


def sign_promoted_runtime_aggregate_catalog(repository_root, candidate_root, capture_root,
        destination, *, trusted_source_sha, trusted_workflow_sha,
        trusted_promotion_workflow_sha, final_commit, expected_validation_tree,
        expected_build_key, expected_receipt_sha256, expected_object_sha256,
        expected_original_commit, expected_original_run_id,
        expected_original_run_attempt, expected_upload_artifact_id,
        expected_upload_sha256, expected_carrier_inventory_sha256,
        expected_attestation_sha256, expected_signature_sha256,
        expected_capture_inventory_sha256, event_payload, environment):
    """Sign only an independently pinned, reverified token-free capture."""
    if _OBSERVATION_TOKENS & (set(environment) | set(os.environ)):
        raise ValueError("Runtime catalog signer must not receive an observation token")
    if _CAPTURE_SECRETS & (set(environment) | set(os.environ)):
        raise ValueError("Runtime catalog signer must not receive other signing secrets")
    expected_capture = require_sha256(expected_capture_inventory_sha256,
                                      "Approved Runtime capture inventory")
    for value in (trusted_source_sha, trusted_workflow_sha,
                  trusted_promotion_workflow_sha, final_commit, expected_validation_tree,
                  expected_original_commit):
        promote.require_oid(value, "Runtime promotion signer pin")
    for value in (expected_build_key, expected_receipt_sha256, expected_object_sha256,
                  expected_upload_sha256, expected_carrier_inventory_sha256,
                  expected_attestation_sha256, expected_signature_sha256):
        require_sha256(value, "Runtime promotion signer pin")
    original_run = promote.positive_int(expected_original_run_id, "Original run")
    original_attempt = promote.positive_int(expected_original_run_attempt, "Original attempt")
    upload_id = promote.positive_int(expected_upload_artifact_id, "Original upload")
    trusted, source_tree = _checkout(repository_root, trusted_source_sha)
    candidate, final_tree = _checkout(candidate_root, final_commit)
    if final_tree != expected_validation_tree or trusted == candidate or \
            trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Runtime signer checkouts differ from approved distinct source/tree")
    capture_root, destination = Path(capture_root).absolute(), Path(destination).absolute()
    if capture_root != Path(os.path.normpath(capture_root)) or \
            destination != Path(os.path.normpath(destination)):
        raise ValueError("Runtime signer paths must be normalized")
    _require_capability_output_separate(destination, [trusted, candidate, capture_root])
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime signed catalog destination already exists")
    original_files = regular_file_inventory(capture_root, allow_empty=True)
    if sha256_bytes(canonical_json_bytes(original_files)) != expected_capture:
        raise ValueError("Runtime capture differs from independently approved inventory")
    if {item.name for item in capture_root.iterdir()} != {
            "caller.json", "original-evidence", "trust", "unsigned"}:
        raise ValueError("Runtime capture has unexpected roots")
    expected_environment = {
        "GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPOSITORY,
        "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": final_commit,
        "GITHUB_REF": "refs/heads/main", "GITHUB_REF_PROTECTED": "true",
        "GITHUB_WORKFLOW_REF": f"{REPOSITORY}/.github/workflows/promote.yml@refs/heads/main",
        "GITHUB_WORKFLOW_SHA": trusted_promotion_workflow_sha,
    }
    if any(environment.get(name) != value for name, value in expected_environment.items()):
        raise ValueError("Runtime signer requires protected-main promotion context")
    for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        value = environment.get(name)
        if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or \
                str(int(value)) != value or int(value) < 1:
            raise ValueError("Runtime signer run/attempt is invalid")
        expected_environment[name] = value
    producer = {"repository": REPOSITORY, "workflowPath": ".github/workflows/promote.yml",
        "event": "push", "commit": final_commit, "tree": final_tree,
        "pullRequest": None, "runId": int(expected_environment["GITHUB_RUN_ID"]),
        "runAttempt": int(expected_environment["GITHUB_RUN_ATTEMPT"])}
    original = {"repository": REPOSITORY, "workflowPath": ".github/workflows/ci.yml",
        "event": "merge_group", "commit": expected_original_commit, "tree": final_tree,
        "pullRequest": None, "runId": original_run, "runAttempt": original_attempt}
    if not isinstance(event_payload, dict) or event_payload.get("repository", {}).get(
            "full_name") != REPOSITORY or event_payload.get("ref") != "refs/heads/main" or \
            event_payload.get("after") != final_commit or event_payload.get("deleted") is not False:
        raise ValueError("Runtime signer event differs from approved protected push")
    with tempfile.TemporaryDirectory(prefix="runtime-catalog-sign-") as temporary:
        private = Path(temporary).resolve()
        captured = private / "capture"
        snapshot_regular_tree(capture_root, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != original_files:
            raise ValueError("Runtime capture changed during signer snapshot")
        trusted_policy = transport._release_trust(trusted, trusted_source_sha, private / "policy")
        if trusted_policy is None or regular_file_inventory(trusted_policy.keyring.parent) != \
                regular_file_inventory(captured / "trust"):
            raise ValueError("Runtime captured policy differs from reviewed Git policy")
        require_active_release_key(load_keyring(trusted_policy.keyring, trusted_policy.keys),
                                   trusted_policy.keys)
        caller = _json(captured / "caller.json")
        require_exact_keys(caller, {"schemaVersion", "producer", "trustedSourceCommit",
            "trustedSourceTree", "trustedWorkflowSha", "trustedPromotionWorkflowSha",
            "environment", "event", "aggregateBuildKey", "aggregateReceiptSha256",
            "aggregateObjectSha256", "validatedTree", "originalProducer",
            "originalUploadArtifactId", "originalUploadSha256", "carrierInventorySha256",
            "aggregateAttestationSha256", "aggregateSignatureSha256"}, "Runtime capture caller")
        if (caller["schemaVersion"] != 1 or caller["producer"] != producer
                or caller["trustedSourceCommit"] != trusted_source_sha
                or caller["trustedSourceTree"] != source_tree
                or caller["trustedWorkflowSha"] != trusted_workflow_sha
                or caller["trustedPromotionWorkflowSha"] != trusted_promotion_workflow_sha
                or caller["environment"] != expected_environment or caller["event"] != event_payload
                or caller["aggregateBuildKey"] != expected_build_key
                or caller["aggregateReceiptSha256"] != expected_receipt_sha256
                or caller["aggregateObjectSha256"] != expected_object_sha256
                or caller["validatedTree"] != final_tree or caller["originalProducer"] != original
                or caller["originalUploadArtifactId"] != upload_id
                or caller["originalUploadSha256"] != expected_upload_sha256
                or caller["carrierInventorySha256"] != expected_carrier_inventory_sha256
                or caller["aggregateAttestationSha256"] != expected_attestation_sha256
                or caller["aggregateSignatureSha256"] != expected_signature_sha256):
            raise ValueError("Runtime capture caller differs from independent signer pins")
        evidence = captured / "original-evidence"
        archive = evidence / "upload.zip"
        if sha256_file(archive) != expected_upload_sha256:
            raise ValueError("Runtime original upload differs from S1048 pin")
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(),
            allow_empty_members=True, **transport._CATALOG_ZIP_LIMITS)
        uploaded = evidence / "original"
        if regular_file_inventory(uploaded, allow_empty=True) != zipped:
            raise ValueError("Runtime captured original differs from its pinned archive")
        transport_record = _json(evidence / "transport.json")
        if (transport_record.get("captureProducer") != original
                or transport_record.get("artifact", {}).get("id") != upload_id
                or transport_record.get("artifact", {}).get("digest") != expected_upload_sha256
                or transport_record.get("aggregateBuildKey") != expected_build_key
                or transport_record.get("aggregateReceiptSha256") != expected_receipt_sha256
                or transport_record.get("aggregateObjectSha256") != expected_object_sha256
                or transport_record.get("carrierInventorySha256") != expected_carrier_inventory_sha256
                or transport_record.get("aggregateAttestationSha256") != expected_attestation_sha256
                or transport_record.get("aggregateSignatureSha256") != expected_signature_sha256):
            raise ValueError("Runtime capture transport differs from approved original")
        original_caller = _json(uploaded / "caller.json")
        selected = _json(uploaded / "selected-inputs/selection.json")
        if (original_caller.get("transportProducer") != original
                or original_caller.get("trustedWorkflowSha") != trusted_workflow_sha
                or original_caller.get("metadataReceiptSha256") != expected_receipt_sha256
                or selected.get("producer") != original
                or selected.get("metadata", {}).get("buildKey") != expected_build_key
                or selected.get("metadata", {}).get("receiptSha256") != expected_receipt_sha256):
            raise ValueError("Runtime original caller differs from approved producer")
        carrier = _original_carrier(uploaded, expected_receipt_sha256, expected_build_key)
        relative = object_relative_path(expected_build_key, expected_receipt_sha256)
        with verified_runtime_aggregate_handoff(carrier, keyring=trusted_policy.keyring,
                keys_directory=trusted_policy.keys) as verified:
            if (sha256_bytes(canonical_json_bytes(verified["inventory"])) !=
                    expected_carrier_inventory_sha256
                    or sha256_file(verified["indexInputs"]["attestation"]) !=
                    expected_attestation_sha256
                    or sha256_file(verified["indexInputs"]["signature"]) !=
                    expected_signature_sha256
                    or sha256_bytes(verified["receiptBytes"][_METADATA]) !=
                    expected_receipt_sha256
                    or verified["receipts"][_METADATA]["buildKey"] != expected_build_key
                    or regular_file_inventory(captured / "unsigned/runtime-aggregate-release-evidence/handoffs"
                                              / expected_receipt_sha256.removeprefix("sha256:"),
                                              allow_empty=True) != verified["inventory"]):
                raise ValueError("Runtime capture carrier differs from approved signed original")
            shard = verified["directory"] / "original-evidence/phases/runtime-aggregate-metadata-aggregate/original/shard"
            if (verify_phase_shard(shard, _METADATA)["receiptBytes"] !=
                    verified["receiptBytes"][_METADATA]
                    or sha256_file(shard / relative) != expected_object_sha256
                    or sha256_file(captured / "unsigned" / relative) != expected_object_sha256):
                raise ValueError("Runtime capture object differs from approved original")
        if regular_file_inventory(captured, allow_empty=True) != original_files or \
                regular_file_inventory(capture_root, allow_empty=True) != original_files:
            raise ValueError("Runtime capture changed before signing")
        secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
        if not isinstance(secret, str) or not secret:
            raise ValueError("Runtime signer requires the protected release key")
        private_key = private / "signing-key"
        private_key.touch(mode=0o600, exist_ok=False)
        private_key.write_bytes(private_key_bytes(secret))
        context = {"kind": "promoted-main", "commit": final_commit, "tree": final_tree,
            "promotionRunId": producer["runId"], "promotionRunAttempt": producer["runAttempt"]}
        index = transport.stage_promoted_aggregate_catalog(captured / "unsigned",
            private / "catalog", expected_build_key=expected_build_key,
            expected_receipt_sha256=expected_receipt_sha256, repository=REPOSITORY,
            context=context, producer=producer, keyring=trusted_policy.keyring,
            keys_directory=trusted_policy.keys, private_key=private_key)
        prepared = private / "ready"
        prepared.mkdir()
        for name in ("caller.json", "original-evidence", "trust"):
            source = captured / name
            if source.is_dir():
                snapshot_regular_tree(source, prepared / name, allow_empty=True)
            else:
                (prepared / name).write_bytes(read_regular_file_bytes(source))
        snapshot_regular_tree(private / "catalog", prepared / "catalog", allow_empty=True)
        ready_files = regular_file_inventory(prepared, allow_empty=True)
        if (regular_file_inventory(capture_root, allow_empty=True) != original_files
                or regular_file_inventory(captured, allow_empty=True) != original_files
                or sha256_bytes(canonical_json_bytes(original_files)) != expected_capture
                or _checkout(trusted, trusted_source_sha)[1] != source_tree
                or _checkout(candidate, final_commit)[1] != final_tree):
            raise ValueError("Runtime original capture changed before publication")
        _require_capability_output_separate(destination, [trusted, candidate, capture_root])
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=ready_files)
    return index


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("capture", allow_abbrev=False)
    signing = commands.add_parser("sign", allow_abbrev=False)
    for selected in (command, signing):
        for name in ("repository-root", "candidate-root", "destination"):
            selected.add_argument(f"--{name}", type=Path, required=True)
        for name in ("trusted-source-sha", "trusted-workflow-sha", "trusted-promotion-workflow-sha", "final-commit"):
            selected.add_argument(f"--{name}", required=True)
        for name in ("expected-validation-tree", "expected-build-key", "expected-receipt-sha256",
                     "expected-object-sha256", "expected-original-commit", "expected-upload-sha256",
                     "expected-carrier-inventory-sha256", "expected-attestation-sha256", "expected-signature-sha256"):
            selected.add_argument(f"--{name}", required=True)
        for name in ("expected-original-run-id", "expected-original-run-attempt", "expected-upload-artifact-id"):
            selected.add_argument(f"--{name}", type=int, required=True)
    signing.add_argument("--capture-root", type=Path, required=True)
    signing.add_argument("--expected-capture-inventory-sha256", required=True)
    args = parser.parse_args(argv)
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        parser.error("GITHUB_EVENT_PATH is required")
    try:
        event = load_json_bytes(read_regular_file_bytes(
            Path(event_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        if not isinstance(event, dict):
            raise ValueError("Event must be an object")
    except (OSError, ValueError):
        parser.error("GITHUB_EVENT_PATH must name a safe regular JSON event object")
    common = dict(
        trusted_source_sha=args.trusted_source_sha, trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_promotion_workflow_sha=args.trusted_promotion_workflow_sha, final_commit=args.final_commit,
        expected_validation_tree=args.expected_validation_tree, expected_build_key=args.expected_build_key,
        expected_receipt_sha256=args.expected_receipt_sha256, expected_object_sha256=args.expected_object_sha256,
        expected_original_commit=args.expected_original_commit,
        expected_original_run_id=args.expected_original_run_id,
        expected_original_run_attempt=args.expected_original_run_attempt,
        expected_upload_artifact_id=args.expected_upload_artifact_id,
        expected_upload_sha256=args.expected_upload_sha256,
        expected_carrier_inventory_sha256=args.expected_carrier_inventory_sha256,
        expected_attestation_sha256=args.expected_attestation_sha256,
        expected_signature_sha256=args.expected_signature_sha256,
        event_payload=event, environment=os.environ)
    if args.command == "capture":
        result = capture_promotable_runtime_aggregate_catalog(
            args.repository_root, args.candidate_root, args.destination,
            token=os.environ.get("GITHUB_TOKEN"), **common)
        print(canonical_json_bytes(result).decode().strip())
    else:
        sign_promoted_runtime_aggregate_catalog(
            args.repository_root, args.candidate_root, args.capture_root,
            args.destination, expected_capture_inventory_sha256=args.expected_capture_inventory_sha256,
            **common)


if __name__ == "__main__":
    main()
