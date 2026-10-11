"""Recover original successful iOS binary/JS package transport, not semantic admission."""

from pathlib import Path
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    _is_windows, canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_integer,
    require_regular_directory, require_sha256, sha256_bytes,
)
from products.registry import PhaseInstanceId
from products.restore import _VERIFICATION_SESSION, _stage_fingerprint, verify_phase_shard
from products.verified_evidence import _source_identity
from products.signing_isolation import require_no_signing_secret
from reuse import run_matches_pr
from runtime_reference_archive import open_reference_archive
from sdk_apple_upload_locator import locate_original_apple_upload


INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_RELATIVE = "sdk-ios/binary/ios"
_JAVASCRIPT_PACKAGE = PhaseInstanceId("sdk", "javascript", "package", "node")
_JAVASCRIPT_RELATIVE = "javascript/package/node"


def _javascript_package_record(capture, artifact_root):
    verified = verify_phase_shard(Path(capture) / "original/shard", _JAVASCRIPT_PACKAGE)
    return {**products._identity_record(_JAVASCRIPT_PACKAGE),
        **{field: verified[field] for field in ("buildKey", "receiptSha256", "objectSha256")},
        "objectPath": (Path(capture) / "original/shard" / verified["objectPath"])
            .relative_to(artifact_root).as_posix()}


def _capture_javascript_package(prior, artifact, destination, *, plan, consumer_producer,
        build_key, trusted_workflow_sha, token):
    """Authenticate a fixed successful original worker, not its failed collector."""
    run, attempt = _require_prior(plan, consumer_producer, prior)
    destination.mkdir(parents=True)
    archive = destination / "transport.zip"
    # The demonstrated small upload uses the existing private immutable-byte
    # memo; fresh original source/job checks below remain mandatory on every use.
    artifact, raw_upload = products._download_contract_ci_upload(artifact["id"], artifact["digest"],
        artifact["name"], {"runId": run}, prior, token)
    archive.write_bytes(raw_upload)
    zipped, _, identity = products.verified_zip_contents(archive, retained_paths=(),
        allow_empty_members=True, **products._CATALOG_ZIP_LIMITS)
    if identity != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}:
        raise ValueError("Original JavaScript package upload identity changed")
    original = destination / "original"
    products.safe_extract(archive, original)
    verified = verify_phase_shard(original / "shard", _JAVASCRIPT_PACKAGE)
    receipt, raw = verified["receipt"], verified["receiptBytes"]
    producer = receipt["producer"]
    name = (f"codex-agent-sdk-worker-javascript-package-node-{build_key.removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{attempt}")
    if (receipt["buildKey"] != build_key or receipt["trustDomain"] != "development"
            or producer["runId"] != run or producer["runAttempt"] != attempt
            or producer["repository"] != plan["repository"] or producer["event"] != "pull_request"
            or producer["pullRequest"] != plan["pullRequest"] or artifact["name"] != name):
        raise ValueError("Original JavaScript package differs from its selected phase or producer")
    jobs = products.paginated_items(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{run}/attempts/{attempt}/jobs", "jobs", token)
    matching = products._matching_ci_jobs(jobs, "product-validation / sdk-javascript-package-node",
                                         expected_build_key=build_key)
    if len(matching) != 1:
        raise ValueError("Original JavaScript package job is missing or ambiguous")
    observed = products._observe_ci_producer_jobs({"package": producer},
        jobs_by_phase={"package": matching[0]["name"]}, trusted_workflow_sha=trusted_workflow_sha, token=token)
    products._require_artifact_job_window(observed[0], matching[0]["name"], artifact)
    transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                 "packageReceiptSha256": verified["receiptSha256"]}
    products.write_canonical_json(destination / "capture-transport.json", transport)
    if (products.sha256_file(archive) != artifact["digest"]
            or regular_file_inventory(original, allow_empty=True) != zipped
            or read_regular_file_bytes(original / "shard/phase-receipt.json") != raw):
        raise ValueError("Original JavaScript package capture changed during authentication")
    return receipt


def capture_prior_javascript_package(plan, consumer_producer, build_key, destination, artifact_root,
        *, trusted_workflow_sha, token, environ, attempts=None):
    """Recover only the demonstrated exact-key JS package from successful workers."""
    require_no_signing_secret(environ)
    context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
    require_sha256(build_key, "Current JavaScript package build key")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Prior JavaScript recovery destination must not exist")
    attempts = products._prior_failed_pr_attempts(plan, consumer_producer, token) if attempts is None else attempts
    prefix = f"codex-agent-sdk-worker-javascript-package-node-{build_key.removeprefix('sha256:')}-"
    found = []
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-pr-recovery-") as temporary:
        private = Path(temporary).resolve()
        for prior in attempts:
            run, attempt = _require_prior(plan, consumer_producer, prior)
            workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
            if workflow is None:
                continue
            uploads = products.paginated_items(
                f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/artifacts", "artifacts", token)
            suffix = f"-attempt-{attempt}"
            candidates = [row for row in uploads if type(row) is dict and type(row.get("name")) is str
                and row["name"].startswith(prefix) and row["name"].endswith(suffix)]
            if len(candidates) > 1:
                raise ValueError("Prior JavaScript package upload is ambiguous")
            if not candidates or candidates[0].get("expired") is True:
                continue
            artifact = candidates[0]
            if artifact.get("expired") is not False:
                raise ValueError("Prior JavaScript package expiration is malformed")
            if re.fullmatch(re.escape(prefix) + r"[0-9a-f]{40}" + re.escape(suffix), artifact["name"]) is None:
                raise ValueError("Prior JavaScript package upload name is malformed")
            jobs = products.paginated_items(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
                f"{run}/attempts/{attempt}/jobs", "jobs", token)
            jobs = products._matching_ci_jobs(jobs, "product-validation / sdk-javascript-package-node",
                                              expected_build_key=build_key)
            if len(jobs) != 1:
                raise ValueError("Prior JavaScript package job is missing or ambiguous")
            if jobs[0].get("conclusion") in {"failure", "cancelled", "skipped"}:
                continue
            if (jobs[0].get("status") != "completed" or jobs[0].get("conclusion") != "success"
                    or jobs[0].get("run_id") != run or jobs[0].get("head_sha") != prior.get("head_sha")):
                raise ValueError("Prior JavaScript package job differs from its original successful attempt")
            source = private / f"{run}-{attempt}"
            receipt = _capture_javascript_package(prior, artifact, source, plan=plan,
                consumer_producer=consumer_producer, build_key=build_key,
                trusted_workflow_sha=workflow, token=token)
            found.append((source, receipt))
        if not found:
            return []
        if any(receipt["outputs"] != found[0][1]["outputs"] for _, receipt in found[1:]):
            raise ValueError("Prior JavaScript exact build key has conflicting output inventories")
        source = found[0][0]
        inventory = regular_file_inventory(source, allow_empty=True)
        target = destination / _JAVASCRIPT_RELATIVE
        if canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != context:
            raise ValueError("JavaScript recovery caller changed during capture")
        publish_regular_tree(source, target, allow_empty=True, expected_inventory=inventory)
        require_no_signing_secret(environ)
        return [_javascript_package_record(target, Path(artifact_root))]


def replay_prior_javascript_package(capture_root, artifact_root, *, plan, consumer_producer,
        trusted_workflow_sha, token, environ):
    """Freshly authenticate the small original upload; never admit failed state ZIPs."""
    require_no_signing_secret(environ)
    context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
    root = Path(capture_root)
    if not root.exists() and not root.is_symlink():
        return []
    require_regular_directory(root, "Prior JavaScript package recovery")
    parent = root
    for name in _JAVASCRIPT_RELATIVE.split("/"):
        if sorted(path.name for path in parent.iterdir()) != [name]:
            raise ValueError("Prior JavaScript capture has an unexpected family")
        parent /= name
        require_regular_directory(parent, "Prior JavaScript capture family")
    fingerprint = _stage_fingerprint(root)
    inventory = regular_file_inventory(parent, allow_empty=True)
    raw = read_regular_file_bytes(parent / "original/shard/phase-receipt.json",
                                 max_bytes=16 * 1024**2, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    if products._identity(receipt) != _JAVASCRIPT_PACKAGE:
        raise ValueError("Prior JavaScript recovery requires its exact package receipt")
    producer = receipt["producer"]
    prior = products.api_json(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{producer['runId']}/attempts/{producer['runAttempt']}", token)
    _require_prior(plan, consumer_producer, prior)
    workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Prior JavaScript package lacks its reviewed original workflow")
    transport = require_exact_keys(products._canonical_control(parent / "capture-transport.json", "Prior JS transport"),
        {"artifact", "captureProducer", "observed", "packageReceiptSha256"}, "Prior JS transport")
    if transport["captureProducer"] != producer or transport["packageReceiptSha256"] != sha256_bytes(raw):
        raise ValueError("Prior JavaScript transport changes its original receipt or producer")
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-replay-") as temporary:
        fresh = Path(temporary).resolve() / "capture"
        _capture_javascript_package(prior, transport["artifact"], fresh, plan=plan,
            consumer_producer=consumer_producer, build_key=receipt["buildKey"],
            trusted_workflow_sha=workflow, token=token)
        observed = products._canonical_control(fresh / "capture-transport.json", "Fresh JS transport")
        if (any(observed["artifact"].get(field) != transport["artifact"].get(field)
                for field in ("id", "name", "digest", "size_in_bytes", "created_at", "archive_download_url", "workflow_run"))
                or [row for row in regular_file_inventory(fresh, allow_empty=True)
             if row["relativePath"] != "capture-transport.json"] !=
                [row for row in inventory if row["relativePath"] != "capture-transport.json"]):
            raise ValueError("Prior JavaScript capture differs from its authenticated original upload")
    record = _javascript_package_record(parent, Path(artifact_root))
    if (_stage_fingerprint(root) != fingerprint or regular_file_inventory(parent, allow_empty=True) != inventory
            or canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != context):
        raise ValueError("Prior JavaScript original changed during readmission")
    require_no_signing_secret(environ)
    return [record]


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


def replay_prior_ios_binary(capture_root, artifact_root, *, plan_path, repository_root,
        plan, consumer_producer, trusted_workflow_sha, token, environ):
    """Reauthenticate compact custody against its fully verified original upload.

    Original capture/receipt bytes are not rewritten. Returned records contain
    content identity only; current retrieval observation is not product identity.
    Package selection still owns the independent native/source/toolchain gates.
    Only a completed whole-upload comparison in this private process session can
    avoid downloading it again; live provenance and compact bytes are rechecked.
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
    if sorted(path.name for path in capture.iterdir()) != ["capture-transport.json", "original"]:
        raise ValueError("Prior SDK compact capture has an unexpected member")
    require_regular_directory(capture / "original", "Prior SDK compact original")
    if sorted(path.name for path in (capture / "original").iterdir()) != ["shard"]:
        raise ValueError("Prior SDK compact original has an unexpected member")
    inventory = regular_file_inventory(capture)
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024**2, reject_symlink_parents=True)
    candidate = Path(repository_root).resolve(strict=True)
    if products._validate_plan(Path(plan_path), candidate) != plan or plan["remoteBuildAuthorized"] is not True:
        raise ValueError("Prior SDK recovery plan differs from its authorized caller")
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
    transport = require_exact_keys(products._canonical_control(
        capture / "capture-transport.json", "Prior SDK transport"),
        {"artifact", "captureProducer", "observed", "binaryReceiptSha256"}, "Prior SDK transport")
    if (locator["artifact_id"] != transport["artifact"].get("id")
            or locator["artifact_sha256"] != transport["artifact"].get("digest")
            or transport["captureProducer"] != producer
            or transport["binaryReceiptSha256"] != sha256_bytes(raw)
            or receipt["trustDomain"] != "development" or producer["event"] != "pull_request"
            or producer["pullRequest"] != plan["pullRequest"]):
        raise ValueError("Prior SDK retained upload differs from freshly observed original")
    artifact_fields = ("id", "name", "digest", "size_in_bytes", "created_at",
                       "archive_download_url", "workflow_run")
    current = products._contract_ci_upload_metadata(locator["artifact_id"], locator["artifact_sha256"],
        transport["artifact"]["name"], producer, prior, token)
    if any(current.get(field) != transport["artifact"].get(field) for field in artifact_fields):
        raise ValueError("Prior SDK retained upload metadata changed")
    # A disk descriptor is never authority. Seal only a successful full-original
    # comparison, after all exit checks. No evidence or trust crosses processes.
    session = None if _is_windows() else _VERIFICATION_SESSION.get()
    policy = _source_identity() if session is not None else None
    context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer,
        "transport": transport, "workflow": workflow, "callerWorkflow": trusted_workflow_sha})
    key = (str(candidate), policy, sha256_bytes(plan_bytes), sha256_bytes(context))
    inventory_digest = sha256_bytes(canonical_json_bytes(inventory))
    expected = None
    if session is not None:
        with session["lock"]:
            expected = session.get("sdkIosOriginals", {}).get(key)
    if expected is not None:
        if inventory_digest != expected:
            raise ValueError("Prior SDK compact shard differs from its authenticated original upload")
    else:
        with tempfile.TemporaryDirectory(prefix="sdk-ios-compact-replay-") as temporary:
            private = Path(temporary).resolve()
            selected = private / "selected-receipt.json"
            selected.write_bytes(raw)
            fresh = private / "capture"
            fresh_transport = products.capture_sdk_ios_binary_upload(plan_path, fresh,
                binary_receipt_path=selected, **locator, trusted_workflow_sha=workflow,
                repository_root=repository_root, environ=environ, token=token, compact_recovery=True)
            if (fresh_transport["captureProducer"] != transport["captureProducer"]
                    or fresh_transport["binaryReceiptSha256"] != transport["binaryReceiptSha256"]
                    or any(fresh_transport["artifact"].get(field) != transport["artifact"].get(field)
                           for field in artifact_fields)
                    or regular_file_inventory(fresh / "original/shard") !=
                       regular_file_inventory(capture / "original/shard")):
                raise ValueError("Prior SDK compact shard differs from its authenticated original upload")
    record = _record(capture, Path(artifact_root))
    if (_stage_fingerprint(root) != fingerprint
            or regular_file_inventory(capture) != inventory
            or read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != raw
            or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
            or canonical_json_bytes({"plan": plan, "consumer": consumer_producer,
                "transport": transport, "workflow": workflow, "callerWorkflow": trusted_workflow_sha}) != context
            or (session is not None and _source_identity() != policy)):
        raise ValueError("Prior SDK original capture changed during readmission")
    require_no_signing_secret(environ)
    if session is not None and expected is None:
        with session["lock"]:
            originals = session.setdefault("sdkIosOriginals", {})
            # One demonstrated capability; bound metadata if a caller changes policy repeatedly.
            if len(originals) < 8:
                originals[key] = inventory_digest
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
                trusted_workflow_sha=workflow, repository_root=repository_root, environ=environ,
                token=token, compact_recovery=True)
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
        fingerprint = _stage_fingerprint(source)
        inventory = regular_file_inventory(source)
        if _stage_fingerprint(source) != fingerprint:
            raise ValueError("Prior SDK original changed during compact publication")
        publish_regular_tree(source, target, expected_inventory=inventory)
        require_no_signing_secret(environ)
        return [_record(target, Path(artifact_root))]
