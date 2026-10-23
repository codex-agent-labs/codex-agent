"""Recover original successful iOS binary/JS transport, not semantic admission."""

from pathlib import Path
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
from products.inventory import (
    _is_windows, canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_integer,
    require_regular_directory, require_sha256, sha256_bytes,
)
from products.registry import PhaseInstanceId
from sdk_phase import (
    COMPACT_REPLAY_INSTANCES, FULL_ORIGINAL_REPLAY_INSTANCES, SDK_FAMILY_INSTANCES,
    completed_recovery_folder,
)
from products.restore import (
    _VERIFICATION_SESSION, _stage_fingerprint, verify_phase_shard, PHASE_SHARD_NAME,
    memoized_file_inventory as regular_file_inventory,
)
from products.verified_evidence import _source_identity
from products.signing_isolation import require_no_signing_secret
from reuse import run_matches_pr
from runtime_reference_archive import open_reference_archive
from sdk_apple_upload_locator import locate_original_apple_upload


INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")
_RELATIVE = "sdk-ios/binary/ios"
_JAVASCRIPT_PACKAGE = PhaseInstanceId("sdk", "javascript", "package", "node")
_JAVASCRIPT_RELATIVE = "javascript/package/node"


def _ios_instance(phase):
    if phase not in {"binary", "package"}:
        raise ValueError("Unsupported successful original iOS recovery phase")
    return PhaseInstanceId("sdk", "sdk-ios", phase, "ios")


def _capture_ios_original(phase, plan_path, capture, selected, **options):
    if phase == "binary":
        return products.capture_sdk_ios_binary_upload(plan_path, capture,
            binary_receipt_path=selected, compact_recovery=True, **options)
    return products.capture_sdk_ios_package_upload(plan_path, capture,
        package_receipt_path=selected, compact_recovery=True, **options)


def _javascript_instance(phase, component="javascript", target=None):
    # Keep legacy default targets; newer compact readers require exact targets.
    if target is None:
        native_package = PhaseInstanceId("sdk", component, phase, "desktop")
        target = ("desktop" if native_package in SDK_FAMILY_INSTANCES["native-package"]
                  else {"javascript": "node", "csharp": "desktop"}.get(component))
    instance = PhaseInstanceId("sdk", component, phase, target)
    if instance not in COMPACT_REPLAY_INSTANCES:
        raise ValueError("Unsupported SDK original recovery phase")
    return instance


def _javascript_package_record(capture, artifact_root, phase="package", *, component="javascript", target=None, completed_frozen=None):
    instance = _javascript_instance(phase, component, target)
    verified = verify_phase_shard(Path(capture) / "original/shard", instance,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
    return {**products._identity_record(instance),
        **{field: verified[field] for field in ("buildKey", "receiptSha256", "objectSha256")},
        "objectPath": (Path(capture) / "original/shard" / verified["objectPath"])
            .relative_to(artifact_root).as_posix()}


def _capture_javascript_package(prior, artifact, destination, *, plan, consumer_producer,
        build_key, trusted_workflow_sha, token, phase="package", component="javascript", repository_root=None):
    """Authenticate a fixed successful original worker, not its failed collector."""
    instance = _javascript_instance(phase, component)
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
    verified = verify_phase_shard(original / "shard", instance)
    receipt, raw = verified["receipt"], verified["receiptBytes"]
    producer = receipt["producer"]
    name = (products._worker_artifact_prefix("sdk", instance) + f"{build_key.removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{attempt}")
    if (receipt["buildKey"] != build_key or receipt["trustDomain"] != "development"
            or producer["runId"] != run or producer["runAttempt"] != attempt
            or producer["repository"] != plan["repository"] or producer["event"] != "pull_request"
            or producer["pullRequest"] != plan["pullRequest"] or artifact["name"] != name):
        raise ValueError("Original JavaScript package differs from its selected phase or producer")
    jobs = products.paginated_items(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{run}/attempts/{attempt}/jobs", "jobs", token)
    matching = products._matching_ci_jobs(jobs, f"product-validation / sdk-{component}-{phase}-{instance.target}",
                                         expected_build_key=build_key)
    if len(matching) != 1:
        raise ValueError("Original JavaScript package job is missing or ambiguous")
    observed = products._observe_ci_producer_jobs({phase: producer},
        jobs_by_phase={phase: matching[0]["name"]}, trusted_workflow_sha=trusted_workflow_sha, token=token)
    products._require_artifact_job_window(observed[0], matching[0]["name"], artifact)
    transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                 f"{phase}ReceiptSha256": verified["receiptSha256"]}
    products.write_canonical_json(destination / "capture-transport.json", transport)
    if (products.sha256_file(archive) != artifact["digest"]
            or regular_file_inventory(original, allow_empty=True) != zipped
            or read_regular_file_bytes(original / "shard/phase-receipt.json") != raw):
        raise ValueError("Original JavaScript package capture changed during authentication")
    if repository_root is not None:
        from sdk_handoff import _ensure_observed_sdk_commit
        _ensure_observed_sdk_commit(repository_root, producer, token)
    return receipt


def capture_prior_javascript_package(plan, consumer_producer, build_key, destination, artifact_root,
        *, trusted_workflow_sha, token, environ, attempts=None,
        artifacts_by_run=None, jobs_by_attempt=None, phase="package", component="javascript", repository_root=None):
    """Recover an exact-key JS phase from successful original workers."""
    instance = _javascript_instance(phase, component)
    require_no_signing_secret(environ)
    context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
    require_sha256(build_key, "Current JavaScript package build key")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Prior JavaScript recovery destination must not exist")
    attempts = products._prior_failed_pr_attempts(plan, consumer_producer, token) if attempts is None else attempts
    prefix = products._worker_artifact_prefix("sdk", instance) + build_key.removeprefix("sha256:") + "-"
    artifacts_by_run = {} if artifacts_by_run is None else artifacts_by_run
    jobs_by_attempt = {} if jobs_by_attempt is None else jobs_by_attempt
    found = []
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-pr-recovery-") as temporary:
        private = Path(temporary).resolve()
        for prior in attempts:
            run, attempt = _require_prior(plan, consumer_producer, prior)
            workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
            if workflow is None:
                continue
            if run not in artifacts_by_run:
                artifacts_by_run[run] = products.paginated_items(
                    f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/artifacts", "artifacts", token)
            uploads = artifacts_by_run[run]
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
            if (run, attempt) not in jobs_by_attempt:
                jobs_by_attempt[run, attempt] = products.paginated_items(
                    f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/attempts/{attempt}/jobs",
                    "jobs", token)
            jobs = jobs_by_attempt[run, attempt]
            jobs = products._matching_ci_jobs(jobs, f"product-validation / sdk-{component}-{phase}-{instance.target}",
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
                trusted_workflow_sha=workflow, token=token, repository_root=repository_root,
                **({"component": component} if component != "javascript" else {}),
                **({"phase": phase} if phase != "package" else {}))
            found.append((source, receipt))
        if not found:
            return []
        if any(receipt["outputs"] != found[0][1]["outputs"] for _, receipt in found[1:]):
            raise ValueError("Prior JavaScript exact build key has conflicting output inventories")
        source = found[0][0]
        inventory = regular_file_inventory(source, allow_empty=True)
        target = destination / f"{component}/{phase}/{instance.target}"
        if canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != context:
            raise ValueError("JavaScript recovery caller changed during capture")
        publish_regular_tree(source, target, allow_empty=True, expected_inventory=inventory)
        require_no_signing_secret(environ)
        return [_javascript_package_record(target, Path(artifact_root), phase, component=component)]


def replay_prior_javascript_package(capture_root, artifact_root, *, plan, consumer_producer,
        trusted_workflow_sha, token, environ, phase="package", component="javascript", target=None, completed_frozen=None,
        repository_root=None):
    """Freshly authenticate the small original upload; never admit failed state ZIPs."""
    require_no_signing_secret(environ)
    context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
    root = Path(capture_root)
    if not root.exists() and not root.is_symlink():
        return []
    require_regular_directory(root, "Prior JavaScript package recovery")
    parent = root
    instance = _javascript_instance(phase, component, target)
    for name in f"{component}/{phase}/{instance.target}".split("/"):
        if sorted(path.name for path in parent.iterdir()) != [name]:
            raise ValueError("Prior JavaScript capture has an unexpected family")
        parent /= name
        require_regular_directory(parent, "Prior JavaScript capture family")
    fingerprint = _stage_fingerprint(root)
    inventory = regular_file_inventory(parent, allow_empty=True)
    raw = read_regular_file_bytes(parent / "original/shard/phase-receipt.json",
                                 max_bytes=16 * 1024**2, reject_symlink_parents=True)
    receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
    if products._identity(receipt) != instance:
        raise ValueError("Prior JavaScript recovery requires its exact package receipt")
    producer = receipt["producer"]
    transport = require_exact_keys(products._canonical_control(parent / "capture-transport.json", "Prior JS transport"),
        {"artifact", "captureProducer", "observed", f"{phase}ReceiptSha256"}, "Prior JS transport")
    if transport["captureProducer"] != producer or transport[f"{phase}ReceiptSha256"] != sha256_bytes(raw):
        raise ValueError("Prior JavaScript transport changes its original receipt or producer")
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Completed SDK replay requires concrete native authority")
        extension = completed_frozen.sdk_extension()
        if (extension is not None and instance in completed_frozen.completed_phases()
                and instance in {products._identity(row) for row in extension["spec"]["completedPhases"]}):
            record = _javascript_package_record(parent, Path(artifact_root), phase,
                component=component, target=target, completed_frozen=completed_frozen)
            completed_frozen.envelope(record, raw)
            _, artifact, _ = completed_frozen.observe_extended_sdk(record, producer=consumer_producer, token=token)
            if (any(artifact.get(field) != transport["artifact"].get(field) for field in (
                    "id", "name", "digest", "size_in_bytes", "created_at", "archive_download_url", "workflow_run"))
                    or {row["relativePath"] for row in inventory} != {
                        "capture-transport.json", "original/shard/phase-receipt.json", "original/shard/" + PHASE_SHARD_NAME}
                    or _stage_fingerprint(root) != fingerprint or regular_file_inventory(parent, allow_empty=True) != inventory
                    or canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != context):
                raise ValueError("Completed SDK controls changed during native readmission")
            require_no_signing_secret(environ)
            return [record]
    if instance not in FULL_ORIGINAL_REPLAY_INSTANCES:
        raise ValueError("Completed iOS/Core controls require exact native authority")
    prior = products.api_json(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{producer['runId']}/attempts/{producer['runAttempt']}", token)
    _require_prior(plan, consumer_producer, prior)
    workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Prior JavaScript package lacks its reviewed original workflow")
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-replay-") as temporary:
        fresh = Path(temporary).resolve() / "capture"
        _capture_javascript_package(prior, transport["artifact"], fresh, plan=plan,
            consumer_producer=consumer_producer, build_key=receipt["buildKey"],
            trusted_workflow_sha=workflow, token=token, repository_root=repository_root,
            **({"component": component} if component != "javascript" else {}),
            **({"phase": phase} if phase != "package" else {}))
        observed = products._canonical_control(fresh / "capture-transport.json", "Fresh JS transport")
        if (any(observed["artifact"].get(field) != transport["artifact"].get(field)
                for field in ("id", "name", "digest", "size_in_bytes", "created_at", "archive_download_url", "workflow_run"))
                or [row for row in regular_file_inventory(fresh, allow_empty=True)
             if row["relativePath"] != "capture-transport.json"] !=
                [row for row in inventory if row["relativePath"] != "capture-transport.json"]):
            raise ValueError("Prior JavaScript capture differs from its authenticated original upload")
    record = _javascript_package_record(parent, Path(artifact_root), phase, component=component)
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


def _record(capture, artifact_root, *, completed_frozen=None, phase="binary"):
    instance = _ios_instance(phase)
    verified = verify_phase_shard(Path(capture) / "original/shard", instance,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
    return {**products._identity_record(instance),
        **{name: verified[name] for name in ("buildKey", "receiptSha256", "objectSha256")},
        "objectPath": (Path(capture) / "original/shard" / verified["objectPath"])
            .relative_to(artifact_root).as_posix()}


def replay_prior_ios_binary(capture_root, artifact_root, *, plan_path, repository_root,
        plan, consumer_producer, trusted_workflow_sha, token, environ, completed_frozen=None, phase="binary"):
    """Reauthenticate compact custody against its fully verified original upload.

    Original capture/receipt bytes are not rewritten. Returned records contain
    content identity only; current retrieval observation is not product identity.
    Package selection still owns the independent native/source/toolchain gates.
    Concrete native completion can route its exact qualified controls without a
    body. Otherwise only a completed whole-upload comparison in this private
    process avoids another download; live provenance and compact bytes are rechecked.
    """
    require_no_signing_secret(environ)
    instance = _ios_instance(phase)
    relative = f"sdk-ios/{phase}/ios"
    root = Path(capture_root)
    if not root.exists() and not root.is_symlink():
        return []
    require_regular_directory(root, "Prior SDK captures")
    capture = root / relative
    # This deliberately supports one demonstrated capability, not arbitrary SDK uploads.
    parent = root
    for name in relative.split("/"):
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
    transport = require_exact_keys(products._canonical_control(
        capture / "capture-transport.json", "Prior SDK transport"),
        {"artifact", "captureProducer", "observed", f"{phase}ReceiptSha256"}, "Prior SDK transport")
    if (transport["captureProducer"] != producer
            or transport[f"{phase}ReceiptSha256"] != sha256_bytes(raw)
            or receipt["trustDomain"] != "development" or producer["event"] != "pull_request"
            or producer["pullRequest"] != plan["pullRequest"]):
        raise ValueError("Prior SDK retained upload differs from freshly observed original")
    artifact_fields = ("id", "name", "digest", "size_in_bytes", "created_at",
                       "archive_download_url", "workflow_run")
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Completed SDK replay requires concrete native authority")
        if instance in completed_frozen.completed_phases():
            if any(plan.get(field) != consumer_producer.get(field) for field in ("repository", "event", "pullRequest")):
                raise ValueError("Completed SDK plan differs from its current consumer")
            context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
            record = _record(capture, Path(artifact_root), completed_frozen=completed_frozen, phase=phase)
            completed_frozen.envelope(record, raw)
            _, original_artifact, _ = (completed_frozen.observe_sdk(
                plan=plan, producer=consumer_producer, token=token) if phase == "binary" else
                completed_frozen.observe_extended_sdk(record, producer=consumer_producer, token=token))
            if (any(original_artifact.get(field) != transport["artifact"].get(field) for field in artifact_fields)
                    or {row["relativePath"] for row in inventory} != {
                        "capture-transport.json", "original/shard/phase-receipt.json", "original/shard/" + PHASE_SHARD_NAME}
                    or _stage_fingerprint(root) != fingerprint or regular_file_inventory(capture) != inventory
                    or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
                    or canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != context):
                raise ValueError("Completed SDK controls or original identity changed during replay")
            require_no_signing_secret(environ)
            return [record]
    prior = products.api_json(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
        f"{producer['runId']}/attempts/{producer['runAttempt']}", token)
    _require_prior(plan, consumer_producer, prior)
    workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Prior SDK binary lacks a reviewed original workflow")
    locator = locate_original_apple_upload(receipt_path, trusted_workflow_sha=workflow,
        token=token, environ=environ)
    if (locator["artifact_id"] != transport["artifact"].get("id")
            or locator["artifact_sha256"] != transport["artifact"].get("digest")):
        raise ValueError("Prior SDK retained upload differs from freshly observed original")
    current = products._contract_ci_upload_metadata(locator["artifact_id"], locator["artifact_sha256"],
        transport["artifact"]["name"], producer, prior, token,
        **({"upload_limit": products._IOS_PACKAGE_UPLOAD_LIMIT} if phase == "package" else {}))
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
            fresh_transport = _capture_ios_original(phase, plan_path, fresh, selected,
                **locator, trusted_workflow_sha=workflow,
                repository_root=repository_root, environ=environ, token=token)
            if (fresh_transport["captureProducer"] != transport["captureProducer"]
                    or fresh_transport[f"{phase}ReceiptSha256"] != transport[f"{phase}ReceiptSha256"]
                    or any(fresh_transport["artifact"].get(field) != transport["artifact"].get(field)
                           for field in artifact_fields)
                    or regular_file_inventory(fresh / "original/shard") !=
                       regular_file_inventory(capture / "original/shard")):
                raise ValueError("Prior SDK compact shard differs from its authenticated original upload")
    record = _record(capture, Path(artifact_root), **({"phase": phase} if phase != "binary" else {}))
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


def capture_completed_ios_binary(destination, artifact_root, *, completed_frozen, plan, producer, token):
    """Create only ordinary shard controls after distinct native completion admission."""
    from reuse_qualification import CompletedFrozenReuse
    from products.restore import object_relative_path, PHASE_SHARD_NAME, PHASE_RECEIPT_NAME
    from products.inventory import write_canonical_json
    if type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Completed SDK capture requires concrete native authority")
    sdk = completed_frozen.sdk_original()
    if sdk is None or products._identity(sdk["spec"]["completedPhase"]) not in completed_frozen.completed_phases():
        return []
    _, artifact, observed = completed_frozen.observe_sdk(plan=plan, producer=producer, token=token)
    record = sdk["spec"]["completedPhase"]
    envelope = completed_frozen.envelope(record)
    capture = Path(destination) / _RELATIVE
    shard = capture / "original/shard"
    shard.mkdir(parents=True, exist_ok=False)
    write_canonical_json(shard / PHASE_SHARD_NAME, {"schemaVersion": 1, **record,
        "objectPath": object_relative_path(record["buildKey"], record["receiptSha256"])})
    (shard / PHASE_RECEIPT_NAME).write_bytes(envelope["receiptBytes"])
    write_canonical_json(capture / "capture-transport.json", {"artifact": artifact,
        "captureProducer": envelope["receipt"]["producer"], "observed": observed,
        "binaryReceiptSha256": record["receiptSha256"]})
    return [_record(capture, Path(artifact_root), completed_frozen=completed_frozen)]


def capture_completed_javascript(destination, artifact_root, *, completed_frozen, producer, token):
    """Publish only controls for supported, independently completed SDK originals."""
    from reuse_qualification import CompletedFrozenReuse
    from products.restore import object_relative_path, PHASE_RECEIPT_NAME
    if type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Completed SDK capture requires concrete native authority")
    extension = completed_frozen.sdk_extension()
    if extension is None:
        return []
    def capture_one(selected):
        ios_package = products._identity(selected) == _ios_instance("package")
        instance = (_ios_instance("package") if ios_package else
                    _javascript_instance(selected["phase"], selected["component"], selected["target"]))
        if products._identity(selected) != instance:
            raise ValueError("Completed SDK capture changes its supported scope")
        record = {field: selected[field] for field in (
            "product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")}
        envelope = completed_frozen.envelope(record)
        _, artifact, observed = completed_frozen.observe_extended_sdk(record, producer=producer, token=token)
        folder = completed_recovery_folder(instance)
        capture = Path(destination) / folder / f"{instance.component}/{instance.phase}/{instance.target}"
        shard = capture / "original/shard"
        shard.mkdir(parents=True, exist_ok=False)
        products.write_canonical_json(shard / PHASE_SHARD_NAME, {"schemaVersion": 1, **record,
            "objectPath": object_relative_path(record["buildKey"], record["receiptSha256"])})
        (shard / PHASE_RECEIPT_NAME).write_bytes(envelope["receiptBytes"])
        products.write_canonical_json(capture / "capture-transport.json", {"artifact": artifact,
            "captureProducer": envelope["receipt"]["producer"], "observed": observed,
            f"{instance.phase}ReceiptSha256": record["receiptSha256"]})
        return (_record(capture, Path(artifact_root), phase="package", completed_frozen=completed_frozen)
            if ios_package else _javascript_package_record(capture, Path(artifact_root), instance.phase,
                component=instance.component, target=instance.target, completed_frozen=completed_frozen))
    from products.restore import bounded_verify
    selected = [row for row in extension["spec"]["completedPhases"]
        if products._identity(row) in completed_frozen.completed_phases()]
    if not selected:
        return []
    completed_frozen.check_consumer({"kind": "ci", "producer": producer})
    originals = {products._identity(row): row for row in extension["spec"]["originals"]}
    sources = [{"receipt": completed_frozen.envelope(row)["receipt"],
                "artifactId": originals[products._identity(row)]["artifactId"]} for row in selected]
    source = extension["spec"]["source"]
    sources.append({"receipt": {"producer": source["producer"]}, "artifactId": source["artifactId"]})
    with products._ci_observation_batch(tuple(str(producer[field]) for field in ("runId", "runAttempt"))):
        products._prime_runtime_artifact_metadata(sources, token)
        return bounded_verify(capture_one, selected)


def capture_prior_ios_binary(plan_path, plan, consumer_producer, build_key, destination,
        artifact_root, *, repository_root, environ, trusted_workflow_sha, token, attempts=None,
        artifacts_by_run=None, jobs_by_attempt=None, phase="binary"):
    """Search all permitted attempts, authenticate originals, reject key conflicts."""
    require_no_signing_secret(environ)
    instance = _ios_instance(phase)
    relative = f"sdk-ios/{phase}/ios"
    require_sha256(build_key, "Current elected iOS binary key")
    session = None if _is_windows() else _VERIFICATION_SESSION.get()
    policy = _source_identity() if session is not None else None
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024**2,
        reject_symlink_parents=True) if session is not None else None
    caller = canonical_json_bytes({"plan": plan, "consumer": consumer_producer})
    if session is not None and (products._validate_plan(Path(plan_path), Path(repository_root)) != plan
                                or plan["remoteBuildAuthorized"] is not True):
        raise ValueError("Prior SDK recovery plan differs from its authorized caller")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Prior SDK capture destination must not exist")
    attempts = (products._prior_failed_pr_attempts(plan, consumer_producer, token)
                if attempts is None else attempts)
    prefix = f"codex-agent-sdk-worker-sdk-ios-{phase}-ios-{build_key.removeprefix('sha256:')}-"
    artifacts_by_run = {} if artifacts_by_run is None else artifacts_by_run
    jobs_by_attempt = {} if jobs_by_attempt is None else jobs_by_attempt
    found = []
    with tempfile.TemporaryDirectory(prefix="sdk-ios-pr-recovery-") as temporary:
        scratch = Path(temporary).resolve()
        for prior in attempts:
            run, attempt = _require_prior(plan, consumer_producer, prior)
            workflow = products._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
            if workflow is None:
                continue
            if run not in artifacts_by_run:
                artifacts_by_run[run] = products.paginated_items(
                    f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/artifacts", "artifacts", token)
            artifacts = artifacts_by_run[run]
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
            if (run, attempt) not in jobs_by_attempt:
                jobs_by_attempt[run, attempt] = products.paginated_items(
                    f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run}/attempts/{attempt}/jobs",
                    "jobs", token)
            jobs = jobs_by_attempt[run, attempt]
            jobs = products._matching_ci_jobs(jobs, f"product-validation / sdk-sdk-ios-{phase}-ios",
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
                listed["name"], {"runId": run}, prior, token,
                **({"upload_limit": products._IOS_PACKAGE_UPLOAD_LIMIT} if phase == "package" else {}))
            products._require_artifact_job_window({"jobs": [job]}, job["name"], artifact)
            # Discovery is untrusted until the existing full capture independently re-observes
            # and verifies the complete upload against the official outer digest.
            with open_reference_archive(artifact, token,
                    **({"max_bytes": products._IOS_PACKAGE_UPLOAD_LIMIT} if phase == "package" else {})) as (archive, _stream):
                entry = archive.getinfo("shard/phase-receipt.json")
                if entry.is_dir() or entry.file_size > 16 * 1024**2:
                    raise ValueError("Prior SDK discovery receipt exceeds its bound")
                raw = archive.read(entry)
            receipt = products.validate_phase_receipt(load_canonical_json_bytes(raw))
            original = receipt["producer"]
            if (products._identity(receipt) != instance or receipt["buildKey"] != build_key
                    or original["tree"] != match[1] or original["runId"] != run
                    or original["runAttempt"] != attempt or original["pullRequest"] != plan["pullRequest"]
                    or receipt["trustDomain"] != "development"):
                raise ValueError("Prior SDK discovery receipt differs from its exact selected phase")
            selected = scratch / f"{run}-{attempt}.json"
            selected.write_bytes(raw)
            capture = scratch / f"{run}-{attempt}"
            _capture_ios_original(phase, plan_path, capture, selected,
                artifact_id=artifact["id"], artifact_sha256=artifact["digest"],
                trusted_workflow_sha=workflow, repository_root=repository_root, environ=environ,
                token=token)
            verified = verify_phase_shard(capture / "original/shard", instance)
            if verified["receiptBytes"] != raw:
                raise ValueError("Prior SDK captured original differs from discovery")
            found.append((capture, verified["receipt"], workflow))
        if not found:
            return []
        if any(receipt["outputs"] != found[0][1]["outputs"] for _, receipt, _ in found[1:]):
            raise ValueError("Prior SDK exact build key has conflicting output inventories")
        source = found[0][0]  # Original producer stays unchanged, even across equivalent attempts.
        target = destination / relative
        fingerprint = _stage_fingerprint(source)
        inventory = regular_file_inventory(source)
        if _stage_fingerprint(source) != fingerprint:
            raise ValueError("Prior SDK original changed during compact publication")
        publish_regular_tree(source, target, expected_inventory=inventory)
        published = _stage_fingerprint(target)
        record = _record(target, Path(artifact_root), **({"phase": phase} if phase != "binary" else {}))
        require_no_signing_secret(environ)
        if session is not None:
            transport = products._canonical_control(target / "capture-transport.json", "Prior SDK transport")
            context = canonical_json_bytes({"plan": plan, "consumer": consumer_producer,
                "transport": transport, "workflow": found[0][2], "callerWorkflow": trusted_workflow_sha})
            if (regular_file_inventory(target) != inventory or _stage_fingerprint(target) != published
                    or read_regular_file_bytes(plan_path, reject_symlink_parents=True) != plan_bytes
                    or canonical_json_bytes({"plan": plan, "consumer": consumer_producer}) != caller
                    or _source_identity() != policy):
                raise ValueError("Prior SDK original capture changed before completing its session")
            key = (str(Path(repository_root).resolve(strict=True)), policy,
                   sha256_bytes(plan_bytes), sha256_bytes(context))
            # Same completed whole-upload proof as replay; no disk or cross-process authority.
            digest = sha256_bytes(canonical_json_bytes(inventory))
            with session["lock"]:
                originals = session.setdefault("sdkIosOriginals", {})
                if key in originals and originals[key] != digest:
                    raise ValueError("Prior SDK original conflicts with completed session custody")
                if len(originals) < 8:
                    originals[key] = digest
        return [record]
