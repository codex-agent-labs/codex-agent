"""Recover original successful iOS binary transport, never semantic admission."""

from pathlib import Path
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_integer,
    require_regular_directory, require_sha256,
)
from products.registry import PhaseInstanceId
from products.restore import _stage_fingerprint, verify_phase_shard
from products.signing_isolation import require_no_signing_secret
from reuse import run_matches_pr
from runtime_reference_archive import open_reference_archive
from sdk_apple_upload_locator import locate_original_apple_upload


INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_RELATIVE = "sdk-ios/binary/ios"


def _require_prior(plan, consumer, prior):
    run = require_integer(prior.get("id"), "Prior SDK run ID", 1)
    attempt = require_integer(prior.get("run_attempt"), "Prior SDK attempt", 1)
    if (plan["repository"] != "codex-agent-labs/codex-agent" or plan["event"] != "pull_request"
            or plan["pullRequest"] is None
            or (run, attempt) >= (consumer["runId"], consumer["runAttempt"])
            or prior.get("event") != "pull_request" or prior.get("path") != ".github/workflows/ci.yml"
            or prior.get("status") != "completed" or prior.get("conclusion") not in {"failure", "cancelled"}
            or not run_matches_pr(prior, plan["pullRequest"])
            or any(type(prior.get(field)) is not dict
                   or prior[field].get("full_name") != plan["repository"]
                   or prior[field].get("fork") is not False
                   for field in ("repository", "head_repository"))):
        raise ValueError("Prior SDK binary is not an earlier failed canonical PR attempt")
    return run, attempt


def _record(capture, artifact_root):
    verified = verify_phase_shard(Path(capture) / "original/shard", INSTANCE)
    return {**products._identity_record(INSTANCE),
        **{name: verified[name] for name in ("buildKey", "receiptSha256", "objectSha256")},
        "objectPath": (Path(capture) / "original/shard" / verified["objectPath"])
            .relative_to(artifact_root).as_posix()}


def replay_prior_ios_binary(capture_root, artifact_root, *, plan, consumer_producer,
        trusted_workflow_sha, token, environ):
    """Fresh original CI observation plus exact retained whole-upload verification.

    Original capture/receipt bytes are not rewritten. Returned records contain
    content identity only; current retrieval observation is not product identity.
    Package selection still owns the independent native/source/toolchain gates.
    """
    require_no_signing_secret(environ)
    root = Path(capture_root)
    if not root.exists() and not root.is_symlink():
        return []
    require_regular_directory(root, "Prior SDK captures")
    capture = root / _RELATIVE
    # This deliberately supports one demonstrated capability, not arbitrary SDK uploads.
    parent = root
    for name in _RELATIVE.split("/"):
        if sorted(path.name for path in parent.iterdir()) != [name]:
            raise ValueError("Prior SDK recovery has an unexpected capture family")
        parent /= name
        require_regular_directory(parent, "Prior SDK capture family")
    fingerprint = _stage_fingerprint(root)
    receipt_path = capture / "original/shard/phase-receipt.json"
    raw = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024**2, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    producer = receipt["producer"]
    prior = products.api_json(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{producer['runId']}/attempts/{producer['runAttempt']}", token)
    _require_prior(plan, consumer_producer, prior)
    workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Prior SDK binary lacks a reviewed original workflow")
    locator = locate_original_apple_upload(receipt_path, trusted_workflow_sha=workflow,
        token=token, environ=environ)
    # Fresh locator independently observes original successful job, source and upload window.
    # Existing verifier hashes the complete retained outer archive and exact materialization.
    products.verify_retained_sdk_ios_upload(capture, raw)
    transport = products._canonical_control(capture / "capture-transport.json", "Prior SDK transport")
    if (locator["artifact_id"] != transport["artifact"].get("id")
            or locator["artifact_sha256"] != transport["artifact"].get("digest")
            or receipt["trustDomain"] != "development" or producer["event"] != "pull_request"
            or producer["pullRequest"] != plan["pullRequest"]):
        raise ValueError("Prior SDK retained upload differs from freshly observed original")
    record = _record(capture, Path(artifact_root))
    if (_stage_fingerprint(root) != fingerprint
            or read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != raw):
        raise ValueError("Prior SDK original capture changed during readmission")
    require_no_signing_secret(environ)
    return [record]


def capture_prior_ios_binary(plan_path, plan, consumer_producer, build_key, destination,
        artifact_root, *, repository_root, environ, trusted_workflow_sha, token, attempts=None):
    """Search all permitted attempts, authenticate originals, reject key conflicts."""
    require_no_signing_secret(environ)
    require_sha256(build_key, "Current elected iOS binary key")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Prior SDK capture destination must not exist")
    attempts = (products._prior_failed_pr_attempts(plan, consumer_producer, token)
                if attempts is None else attempts)
    prefix = f"codex-agent-sdk-worker-sdk-ios-binary-ios-{build_key.removeprefix('sha256:')}-"
    found = []
    with tempfile.TemporaryDirectory(prefix="sdk-ios-pr-recovery-") as temporary:
        scratch = Path(temporary).resolve()
        for prior in attempts:
            run, attempt = _require_prior(plan, consumer_producer, prior)
            workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
            if workflow is None:
                continue
            artifacts = products.paginated_items(
                f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/artifacts", "artifacts", token)
            suffix = f"-attempt-{attempt}"
            matching = [value for value in artifacts if type(value) is dict
                and type(value.get("name")) is str and value["name"].startswith(prefix)
                and value["name"].endswith(suffix)]
            if len(matching) > 1:
                raise ValueError("Prior SDK exact-key upload is ambiguous")
            if not matching or matching[0].get("expired") is True:
                continue
            listed = matching[0]
            if listed.get("expired") is not False:
                raise ValueError("Prior SDK expiration state is malformed")
            match = re.fullmatch(re.escape(prefix) + r"([0-9a-f]{40})" + re.escape(suffix), listed["name"])
            if match is None:
                raise ValueError("Prior SDK exact-key upload name is malformed")
            jobs = products.paginated_items(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
                f"{run}/attempts/{attempt}/jobs", "jobs", token)
            jobs = products._matching_ci_jobs(jobs, "product-validation / sdk-sdk-ios-binary-ios",
                                              expected_build_key=build_key)
            if len(jobs) != 1:
                raise ValueError("Prior SDK exact-key job is missing or ambiguous")
            job = jobs[0]
            if (job.get("run_id") != run or job.get("head_sha") != prior.get("head_sha")
                    or job.get("status") != "completed"):
                raise ValueError("Prior SDK binary job differs from its original attempt")
            if job.get("conclusion") in {"failure", "cancelled", "skipped"}:
                continue
            if job.get("conclusion") != "success":
                raise ValueError("Prior SDK binary job has an invalid conclusion")
            artifact = products._contract_ci_upload_metadata(listed.get("id"), listed.get("digest"),
                listed["name"], {"runId": run}, prior, token)
            products._require_artifact_job_window({"jobs": [job]}, job["name"], artifact)
            # Discovery is untrusted until the existing full capture independently re-observes
            # and verifies the complete upload against the official outer digest.
            with open_reference_archive(artifact, token) as (archive, _stream):
                entry = archive.getinfo("shard/phase-receipt.json")
                if entry.is_dir() or entry.file_size > 16 * 1024**2:
                    raise ValueError("Prior SDK discovery receipt exceeds its bound")
                raw = archive.read(entry)
            receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
            original = receipt["producer"]
            if (products._identity(receipt) != INSTANCE or receipt["buildKey"] != build_key
                    or original["tree"] != match[1] or original["runId"] != run
                    or original["runAttempt"] != attempt or original["pullRequest"] != plan["pullRequest"]
                    or receipt["trustDomain"] != "development"):
                raise ValueError("Prior SDK discovery receipt differs from its exact selected phase")
            selected = scratch / f"{run}-{attempt}.json"
            selected.write_bytes(raw)
            capture = scratch / f"{run}-{attempt}"
            products.capture_sdk_ios_binary_upload(plan_path, capture, binary_receipt_path=selected,
                artifact_id=artifact["id"], artifact_sha256=artifact["digest"],
                trusted_workflow_sha=workflow, repository_root=repository_root, environ=environ, token=token)
            verified = verify_phase_shard(capture / "original/shard", INSTANCE)
            if verified["receiptBytes"] != raw:
                raise ValueError("Prior SDK captured original differs from discovery")
            found.append((capture, verified["receipt"]))
        if not found:
            return []
        if any(receipt["outputs"] != found[0][1]["outputs"] for _, receipt in found[1:]):
            raise ValueError("Prior SDK exact build key has conflicting output inventories")
        source = found[0][0]  # Original producer stays unchanged, even across equivalent attempts.
        target = destination / _RELATIVE
        inventory = regular_file_inventory(source, allow_empty=True)
        publish_regular_tree(source, target, allow_empty=True, expected_inventory=inventory)
        require_no_signing_secret(environ)
        return [_record(target, Path(artifact_root))]
