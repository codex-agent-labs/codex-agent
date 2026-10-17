"""Recover original Android metadata through its full validation replay.

The worker upload is transport, not host or product authority. Caller-owned
package, binary, S858, Contract, tooling, source and an independently
authenticated validation capture remain authoritative for the held replay.
"""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, run_git, sha256_bytes, snapshot_regular_tree,
    write_canonical_json,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_android_metadata import OUTPUT_KIND, OUTPUT_PATH, write_android_metadata_content
from products.sdk_android_validation_content import validate_android_validation_content
from products.sdk_package import _require_capability_output_separate
from products.selection import phase_git_inventory
from products.signing_isolation import require_no_signing_secret
from products import sdk_android_validation_phase as validation_phase
from sdk_android_original_validation import verified_retained_android_validation
from sdk_facade_capture import (
    capture_sdk_android_metadata_upload, verify_retained_sdk_phase_upload,
)


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_LIMIT = 512 * 1024 * 1024


def verify_completed_android_metadata(envelope, validation_envelopes, *, plan, discovery, state,
        artifact, trusted_workflow_sha, repository_root, environ, token, completed_frozen,
        sdk_validation_tooling, sdk_apple_validation_policy=None):
    """Admit the full original using qualified P/V, without expanding their trees.

    Share the collector's authenticated private archive and inventory. Compare
    every embedded predecessor byte with its qualified receipt/original; retain
    original worker, source, election and lifetime checks. No acceptance cache.
    """
    import zipfile
    from reuse_qualification import CompletedFrozenReuse
    from products.reuse import _validate_envelope
    from products.inventory import sha256_file
    from products.plan import _upstream_record
    from products.receipt import output_inventory_digest
    from products.sdk_android_validation_content import android_metadata_content
    from runtime_reference_archive import copy_reference_member
    from sdk_campaign_original_locator import fresh_sdk_worker_route, retained_core_origin

    if type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Android metadata requires concrete native predecessor authority")
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    identity, selected = _validate_envelope(envelope)
    validation_id = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
    package_id = PhaseInstanceId("sdk", "sdk-android", "package", "android")
    if identity != _INSTANCE or not isinstance(validation_envelopes, (list, tuple)) or len(validation_envelopes) != 1:
        raise ValueError("Android metadata requires its exact identity and one validation predecessor")
    supplied_id, supplied = _validate_envelope(validation_envelopes[0])
    if supplied_id != validation_id:
        raise ValueError("Android metadata requires its exact validation predecessor")
    receipt, raw = selected["receipt"], selected["receiptBytes"]
    elected = product_reuse._verified_product_state(Path(plan), Path(discovery), Path(state), root,
        environ, sdk_validation_tooling, requested_scope=(_INSTANCE,), completed_frozen=completed_frozen,
        sdk_original_workflow_sha=trusted_workflow_sha, sdk_apple_validation_policy=sdk_apple_validation_policy)
    ready = elected.prior_ready_plans.get(_INSTANCE)
    if ready is None or ready["buildKey"] != receipt["buildKey"]:
        raise ValueError("Android metadata is not elected with its exact key")
    consumer = product_reuse._consumer(elected.plan, environ)["producer"]
    completed_frozen.check_consumer({"kind": "ci", "producer": consumer})
    origin = None
    workflow = trusted_workflow_sha
    context = {"repositoryRoot": "/home/runner/work/codex-agent/codex-agent",
        "metadataRequest": "/home/runner/work/codex-agent/codex-agent/build/sdk-android-metadata-worker/metadata-request.json"}
    if receipt["producer"] != consumer:
        origin = retained_core_origin("metadata", receipt["buildKey"], consumer, component="sdk-android", target="android")
        if (origin is None or origin["producer"] != receipt["producer"]
                or origin["artifact_id"] != artifact["id"] or origin["artifact_sha256"] != artifact["digest"]
                or origin["receipt_sha256"] != selected["receiptSha256"] or origin["context"] != context):
            raise ValueError("Android metadata differs from its reviewed original")
        workflow = origin["workflow_sha"]
    native, originals = {}, {}
    for predecessor in (package_id, validation_id):
        row = elected.prior_by_instance[predecessor]
        qualified = completed_frozen.envelope(row)
        if qualified is None or row["state"] != "retained":
            raise ValueError("Android predecessor lacks exact native semantic qualification")
        if predecessor == validation_id and supplied != qualified:
            raise ValueError("Android validation differs from its native-qualified envelope")
        native[predecessor] = qualified
        _, originals[predecessor], _ = completed_frozen.observe_extended_sdk(row, producer=consumer, token=token)
    package, validation = native[package_id]["receipt"], native[validation_id]["receipt"]
    if (any(value["productVersion"] != receipt["productVersion"] for value in (package, validation))
            or [r for r in validation["inputs"]["upstreamArtifacts"] if
                (r["product"], r["component"], r["phase"]) == ("sdk", "sdk-android", "package")]
               != [_upstream_record(package)]):
        raise ValueError("Android metadata predecessor version or package lineage differs")
    artifact_bytes = canonical_json_bytes(artifact)
    binding = raw, selected["receiptSha256"], selected["objectSha256"]

    def unchanged():
        require_no_signing_secret(environ)
        completed_frozen.check_consumer({"kind": "ci", "producer": consumer})
        if (canonical_json_bytes(artifact) != artifact_bytes or canonical_json_bytes(selected["receipt"]) != raw
                or (selected["receiptBytes"], selected["receiptSha256"], selected["objectSha256"]) != binding
                or len(validation_envelopes) != 1 or _validate_envelope(validation_envelopes[0])[1] != native[validation_id]
                or any(completed_frozen.envelope(elected.prior_by_instance[i]) != v for i, v in native.items())):
            raise ValueError("Android metadata caller or native-qualified predecessors changed")

    unchanged()
    with tempfile.TemporaryDirectory(prefix="completed-android-metadata-") as temporary:
        private = Path(temporary).resolve()
        job, name = fresh_sdk_worker_route(_INSTANCE, receipt)
        observed = product_reuse._observe_ci_producer_jobs({"metadata": receipt["producer"]},
            jobs_by_phase={"metadata": job}, build_keys_by_phase={"metadata": receipt["buildKey"]}, token=token,
            trusted_workflows_by_phase={"metadata": {"path": ".github/workflows/sdk-android-metadata-validation.yml", "sha": workflow}})
        jobs = product_reuse._matching_ci_jobs(observed[0]["jobs"], job, expected_build_key=receipt["buildKey"])
        labels = jobs[0].get("labels") if len(jobs) == 1 else None
        if (type(labels) is not list or any(type(label) is not str for label in labels) or "ubuntu-24.04" not in labels
                or origin is not None and jobs[0].get("id") != origin["job_id"]):
            raise ValueError("Android metadata original lacks its fixed successful worker route")
        require_integer(jobs[0].get("runner_id"), "Original Android metadata runner", 1)
        archive = private / "metadata.zip"
        actual, _ = product_reuse._download_contract_ci_upload(artifact["id"], artifact["digest"], name,
            receipt["producer"], observed[0]["run"], token, destination=archive,
            upload_limit=product_reuse._IOS_PACKAGE_UPLOAD_LIMIT)
        product_reuse._require_artifact_job_window(observed[0], jobs[0]["name"], actual)
        records = product_reuse._core_metadata_upload_inventory(archive,
            {"bytes": actual["size_in_bytes"], "sha256": actual["digest"]}, _INSTANCE)
        index = {r["relativePath"]: r for r in records}
        with zipfile.ZipFile(archive) as zipped:
            names = tuple(info.filename.rstrip("/") for info in zipped.infolist())

        def inventory(prefix):
            return [{**r, "relativePath": r["relativePath"][len(prefix):]} for r in records if r["relativePath"].startswith(prefix)]

        def roots(prefix):
            return {n[len(prefix):].split("/", 1)[0] for n in names if n.startswith(prefix) and n != prefix.rstrip("/")}

        expected_roots = {"shard", "worker", "selection", "originals", "inputs", "metadata-request.json"}
        if "worker-dependency-seed" in roots(""):
            expected_roots.add("worker-dependency-seed")
        if (roots("") != expected_roots or any(n in index for n in expected_roots - {"metadata-request.json"})
                or roots("worker/") != {"execution.json", "gradle.log"}
                or roots("selection/") != {"impact-plan.json", "phase-plan.json", "producer.json"}
                or roots("originals/") != {"validation"}):
            raise ValueError("Android metadata original has an unexpected retained layout")
        original = private / "original"
        projection = []
        with zipfile.ZipFile(archive) as zipped:
            for row in records:
                path = row["relativePath"]
                if path.startswith(("shard/", "worker/", "selection/")) or path in {
                        "metadata-request.json", "inputs/producer.json", "inputs/phase-plan.json",
                        "inputs/sdk-sdk-android-validation-android/stage/" + validation_phase.OUTPUT_PATH}:
                    if row["bytes"] > _LIMIT:
                        raise ValueError("Android metadata control exceeds its reader bound")
                    copy_reference_member(zipped, path, original / path, row)
                    projection.append(row)
            for predecessor in (package_id, validation_id):
                value = native[predecessor]
                prefix = f"inputs/sdk-sdk-android-{predecessor.phase}-android/"
                manifest = canonical_json_bytes({"schemaVersion": 1, **{n: value["receipt"][n] for n in
                    ("product", "component", "phase", "target", "productVersion", "outputs")}})
                expected = sorted([{"relativePath": "output-manifest.json", "bytes": len(manifest), "sha256": sha256_bytes(manifest)},
                    *[{n: r[n] for n in ("relativePath", "bytes", "sha256")} for r in value["receipt"]["outputs"]]],
                    key=lambda r: r["relativePath"])
                if (roots(prefix) != {"stage", "phase-receipt.json"} or inventory(prefix + "stage/") != expected
                        or index[prefix + "phase-receipt.json"]["sha256"] != value["receiptSha256"]
                        or index[prefix + "phase-receipt.json"]["bytes"] != len(value["receiptBytes"])):
                    raise ValueError("Android retained predecessor differs from native-qualified bytes")
            member = index["originals/validation/transport.zip"]
            validation_artifact = originals[validation_id]
            if (member["sha256"] != validation_artifact["digest"]
                    or member["bytes"] != validation_artifact["size_in_bytes"]):
                raise ValueError("Embedded Android validation differs from its native-qualified original")
            nested = private / "validation.zip"
            copy_reference_member(zipped, member["relativePath"], nested, member)
            contents = product_reuse._core_metadata_upload_inventory(nested,
                {"sha256": member["sha256"], "bytes": member["bytes"]}, validation_id)
            if contents != inventory("originals/validation/original/"):
                raise ValueError("Embedded Android validation extraction differs from its full original ZIP")
            nested.unlink()
        if regular_file_inventory(original, allow_empty=True) != projection:
            raise ValueError("Android metadata controls changed during projection")
        for parent in ("selection", "inputs"):
            if (_json(original / parent / "producer.json") != receipt["producer"]
                    or _json(original / parent / "phase-plan.json") != {n: receipt[n] for n in PHASE_PLAN_KEYS}):
                raise ValueError("Android retained election differs from its receipt")
        shard = verify_phase_shard(original / "shard", _INSTANCE)
        if any(shard[n] != selected[n] for n in ("receiptBytes", "receiptSha256", "objectSha256")):
            raise ValueError("Android original shard differs from selected metadata")
        output = private / "metadata-stage"
        restore_object(original / "shard" / shard["objectPath"], output, build_key=receipt["buildKey"],
            receipt_sha256=selected["receiptSha256"], object_sha256=selected["objectSha256"])
        content = validate_android_validation_content(_json(original /
            ("inputs/sdk-sdk-android-validation-android/stage/" + validation_phase.OUTPUT_PATH)))
        if (len(validation["outputs"]) != 1 or validation["outputs"][0]["kind"] != validation_phase.OUTPUT_KIND
                or validation["outputs"][0]["relativePath"] != validation_phase.OUTPUT_PATH):
            raise ValueError("Android metadata requires exact singleton native-qualified validation content")
        expected = canonical_json_bytes(android_metadata_content(sdk_version=receipt["productVersion"],
            package_outputs_digest=output_inventory_digest(package["outputs"]),
            expected_release_aar_sha256=content["releaseAarSha256"],
            expected_bundled_runtime_sha256=content["bundledRuntimeSha256"], validation_content=content))
        manifest = verify_output_manifest_identity(output, "sdk", "sdk-android", "metadata", "android", receipt["productVersion"])
        if (manifest["outputs"] != receipt["outputs"] or len(manifest["outputs"]) != 1
                or manifest["outputs"][0]["kind"] != OUTPUT_KIND or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH
                or _read(output / OUTPUT_PATH) != expected):
            raise ValueError("Android metadata differs from the native-qualified deterministic join")
        historical = product_reuse._validate_plan(original / "selection/impact-plan.json", root,
                                                  expected_revision=receipt["producer"]["commit"])
        producer = receipt["producer"]
        if (historical["remoteBuildAuthorized"] is not True or historical["event"] not in {"pull_request", "merge_group"}
                or product_reuse._consumer(historical, {"GITHUB_RUN_ID": str(producer["runId"]),
                    "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"] != producer):
            raise ValueError("Android original historical plan is not authorized")
        _worker(original, receipt, _context(context), content)
        _replan(root, receipt, validation)
        if archive.stat().st_size != actual["size_in_bytes"] or sha256_file(archive) != actual["digest"]:
            raise ValueError("Original Android metadata archive changed while consumed")
        if regular_file_inventory(original, allow_empty=True) != projection:
            raise ValueError("Android metadata controls changed while consumed")
        unchanged()
    unchanged()


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _json(path):
    return load_canonical_json_bytes(_read(path))


def _original_posix_path(value, label):
    path = PurePosixPath(value) if type(value) is str and value else None
    if (path is None or PureWindowsPath(value).drive or not path.is_absolute()
            or ".." in path.parts or str(path) != value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError(f"{label} path is invalid")
    return value


def _context(value):
    value = require_exact_keys(
        value, {"repositoryRoot", "metadataRequest"},
        "Caller original Android metadata context")
    for name, path in value.items():
        _original_posix_path(path, f"Original Android metadata {name}")
    return value


def _result_view(value):
    value = require_exact_keys(value, {
        "stage", "receiptPath", "receiptBytes", "receipt", "original",
        "capture", "transport",
    }, "Original Android metadata result")
    return canonical_json_bytes({
        "stagePath": str(value["stage"]),
        "receiptPath": str(value["receiptPath"]),
        "originalPath": str(value["original"]),
        "capturePath": str(value["capture"]),
        "receiptBytes": (value["receiptBytes"].hex()
                         if isinstance(value["receiptBytes"], bytes)
                         else value["receiptBytes"]),
        "receipt": value["receipt"],
        "transport": value["transport"],
        "stageInventory": regular_file_inventory(value["stage"]),
        "captureInventory": regular_file_inventory(value["capture"], allow_empty=True),
    })


def _worker(original, receipt, context, validation_content):
    execution = require_exact_keys(_json(original / "worker/execution.json"), {
        "schemaVersion", "producer", "buildKey", "command", "workingDirectory",
        "returnCode", "launchError", "elapsedNs",
    }, "Original Android metadata execution")
    if (require_integer(execution["schemaVersion"], "Android metadata execution schema", 1) != 1
            or execution["producer"] != receipt["producer"]
            or execution["buildKey"] != receipt["buildKey"]
            or require_integer(execution["returnCode"], "Android metadata execution exit", 0) != 0
            or execution["launchError"] is not None
            or execution["workingDirectory"] != context["repositoryRoot"]):
        raise ValueError("Original Android metadata worker differs from its receipt or caller context")
    require_integer(execution["elapsedNs"], "Android metadata execution elapsed time", 0)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-android",
        "codexAgent.phase": "metadata", "codexAgent.target": "android",
        "codexAgent.candidateCommit": receipt["producer"]["commit"],
        "codexAgent.candidateTree": receipt["producer"]["tree"],
        "codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.sdkAndroidMetadataRequest": context["metadataRequest"],
    }
    expected = product_reuse._runtime_worker_command(
        PurePosixPath(context["repositoryRoot"]) / "gradlew", fields, {},
        build_directory=".", platform_name="posix")
    if execution["command"] != expected:
        raise ValueError("Original Android metadata worker differs from the fixed offline command")
    request = require_exact_keys(_json(original / "metadata-request.json"), {
        "sdkVersion", "packageStage", "packageReceipt", "validationStage",
        "validationReceipt", "releaseAarSha256", "bundledRuntimeSha256",
    }, "Original Android metadata request")
    if (request["sdkVersion"] != receipt["productVersion"]
            or request["releaseAarSha256"] != validation_content["releaseAarSha256"]
            or request["bundledRuntimeSha256"] != validation_content["bundledRuntimeSha256"]):
        raise ValueError("Original Android metadata request differs from verified validation")
    for name in ("packageStage", "packageReceipt", "validationStage", "validationReceipt"):
        _original_posix_path(request[name], "Original Android metadata input")


def _replan(root, receipt, validation_receipt):
    producer = receipt["producer"]
    commit = producer["commit"]
    try:
        if (run_git(root, "rev-parse", f"{commit}^{{commit}}").strip() != commit
                or run_git(root, "rev-parse", f"{commit}^{{tree}}").strip() != producer["tree"]):
            raise ValueError("Original Android metadata commit/tree differs from Git")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original Android metadata source is unavailable") from error
    versions = git_product_versions(root, commit)
    planned = plan_phase(
        _INSTANCE, inventory=phase_git_inventory(root, commit, _INSTANCE),
        versions=versions, upstream_receipts=[validation_receipt],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
    if (receipt["productVersion"] != versions["sdk"]
            or receipt["inputs"] != planned["inputs"]
            or receipt["buildKey"] != planned["buildKey"]):
        raise ValueError("Original Android metadata differs from its source/version/phase key")


def _same_stage(directory, stage, receipt_bytes, label):
    if (_read(directory / "phase-receipt.json") != receipt_bytes
            or regular_file_inventory(directory / "stage") != regular_file_inventory(stage)):
        raise ValueError(f"Original Android metadata {label} differs from verified originals")


@contextmanager
def verified_original_sdk_android_metadata(
        plan, metadata_receipt_path, *, artifact_id, artifact_sha256,
        validation_capture, package_stage, package_receipt, binary_stage,
        binary_receipt, compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        trusted_workflow_sha, tooling_evidence, tooling_public_key,
        java_executable, apkanalyzer_executable, policy_revision,
        required_trust_domain, repository_root, environ, token,
        tooling_keyring=None, tooling_keys_directory=None):
    """Observe one exact upload and hold the complete metadata replay."""
    with _verified_sdk_android_metadata(
            plan, metadata_receipt_path, metadata_capture=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, token=token,
            validation_capture=validation_capture,
            package_stage=package_stage, package_receipt=package_receipt,
            binary_stage=binary_stage, binary_receipt=binary_receipt,
            compatibility_request=compatibility_request,
            binary_contract_evidence=binary_contract_evidence,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            original_context=original_context,
            tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key,
            java_executable=java_executable,
            apkanalyzer_executable=apkanalyzer_executable,
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=repository_root, environ=environ,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def verified_retained_sdk_android_metadata(
        plan, metadata_receipt_path, *, metadata_capture, validation_capture,
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        tooling_evidence, tooling_public_key, java_executable,
        apkanalyzer_executable, policy_revision, required_trust_domain,
        repository_root, environ, tooling_keyring=None,
        tooling_keys_directory=None):
    """Replay a caller-authenticated retained carrier; it grants no trust."""
    with _verified_sdk_android_metadata(
            plan, metadata_receipt_path,
            metadata_capture=Path(metadata_capture),
            validation_capture=validation_capture,
            package_stage=package_stage, package_receipt=package_receipt,
            binary_stage=binary_stage, binary_receipt=binary_receipt,
            compatibility_request=compatibility_request,
            binary_contract_evidence=binary_contract_evidence,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            original_context=original_context,
            tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key,
            java_executable=java_executable,
            apkanalyzer_executable=apkanalyzer_executable,
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=repository_root, environ=environ,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as value:
        yield value


@contextmanager
def _verified_sdk_android_metadata(
        plan, metadata_receipt_path, *, metadata_capture,
        validation_capture, package_stage, package_receipt, binary_stage,
        binary_receipt, compatibility_request, binary_contract_evidence,
        trusted_source_commit, trusted_source_tree, original_context,
        tooling_evidence, tooling_public_key, java_executable,
        apkanalyzer_executable, policy_revision, required_trust_domain,
        repository_root, environ, tooling_keyring=None,
        tooling_keys_directory=None, artifact_id=None, artifact_sha256=None,
        trusted_workflow_sha=None, token=None):
    require_no_signing_secret(environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android metadata tooling keyring and directory must be paired")
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path = Path(plan).absolute(), Path(metadata_receipt_path).absolute()
    context = _context(original_context)
    trees = {
        "validationCapture": Path(validation_capture).absolute(),
        "package": Path(package_stage).absolute(),
        "binary": Path(binary_stage).absolute(),
        "tooling": Path(tooling_evidence).absolute(),
    }
    files = {
        "plan": plan, "receipt": receipt_path,
        "packageReceipt": Path(package_receipt).absolute(),
        "binaryReceipt": Path(binary_receipt).absolute(),
        "compatibilityRequest": Path(compatibility_request).absolute(),
        "toolingPublicKey": Path(tooling_public_key).absolute(),
        "java": Path(java_executable).absolute(),
        "apkanalyzer": Path(apkanalyzer_executable).absolute(),
    }
    contract_trees, contract_files = validation_phase._contract_sources(binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring).absolute()
        trees["toolingKeys"] = Path(tooling_keys_directory).absolute()
    if metadata_capture is not None:
        trees["retainedMetadata"] = metadata_capture.absolute()
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
            "sdk", "sdk-android", "metadata", "android"):
        raise ValueError("Android metadata recovery requires its exact selected receipt")
    before_trees = {name: regular_file_inventory(path, allow_empty=True)
                    for name, path in trees.items()}
    before_files = {name: _read(path) for name, path in files.items()}
    authority = lambda: canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "originalContext": _context(original_context),
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
    })
    authority_bytes = authority()
    retained = {}
    result = transport = None
    result_bytes = transport_bytes = None

    def unchanged():
        require_no_signing_secret(environ)
        if (authority() != authority_bytes or _read(receipt_path) != raw
                or canonical_json_bytes(receipt) != raw
                or any(regular_file_inventory(path, allow_empty=True) != before_trees[name]
                       for name, path in trees.items())
                or any(_read(path) != before_files[name] for name, path in files.items())
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in retained.items())
                or (transport is not None and canonical_json_bytes(transport) != transport_bytes)
                or (result is not None and _result_view(result) != result_bytes)):
            raise ValueError("Original Android metadata inputs, outputs or caller authority changed")

    with tempfile.TemporaryDirectory(prefix="original-android-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *trees.values(), *files.values()])
        selected = private / "metadata-receipt.json"
        selected.write_bytes(raw)
        try:
            unchanged()
            capture = private / "capture"
            if metadata_capture is None:
                transport = capture_sdk_android_metadata_upload(
                    plan, capture, metadata_receipt_path=selected,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=root, environ=environ, token=token)
            else:
                snapshot_regular_tree(metadata_capture, capture, allow_empty=True)
                if (regular_file_inventory(capture, allow_empty=True) !=
                        before_trees["retainedMetadata"]):
                    raise ValueError("Retained Android metadata changed during private capture")
                verify_retained_sdk_phase_upload(capture, raw)
                transport = _json(capture / "capture-transport.json")
            transport_bytes = canonical_json_bytes(transport)
            if (transport.get("captureProducer") != receipt["producer"]
                    or transport.get("metadataReceiptSha256") != sha256_bytes(raw)
                    or _read(capture / "capture-transport.json") != transport_bytes):
                raise ValueError("Android metadata transport differs from its selected receipt")
            retained[capture] = regular_file_inventory(capture, allow_empty=True)
            original = capture / "original"
            if ({path.name for path in original.iterdir()} !=
                    {"shard", "worker", "selection", "originals", "inputs",
                     "metadata-request.json"}
                    or {path.name for path in (original / "worker").iterdir()} !=
                    {"execution.json", "gradle.log"}
                    or {path.name for path in (original / "selection").iterdir()} !=
                    {"impact-plan.json", "phase-plan.json", "producer.json"}
                    or {path.name for path in (original / "originals").iterdir()} != {"validation"}):
                raise ValueError("Original Android metadata has an unexpected retained layout")
            shard = verify_phase_shard(original / "shard", _INSTANCE)
            stage = private / "stage"
            restored = restore_object(
                original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"],
                object_sha256=shard["objectSha256"])
            manifest = verify_output_manifest_identity(
                stage, "sdk", "sdk-android", "metadata", "android",
                receipt["productVersion"])
            if (shard["receiptBytes"] != raw or restored["receiptBytes"] != raw
                    or manifest["outputs"] != receipt["outputs"]
                    or len(manifest["outputs"]) != 1
                    or manifest["outputs"][0]["kind"] != OUTPUT_KIND
                    or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH):
                raise ValueError("Original Android metadata shard differs from its selected receipt")
            historical = product_reuse._validate_plan(
                original / "selection/impact-plan.json", root,
                expected_revision=receipt["producer"]["commit"])
            if (historical["remoteBuildAuthorized"] is not True
                    or historical["event"] not in {"pull_request", "merge_group"}):
                raise ValueError("Original Android metadata impact plan is not authorized")
            producer = product_reuse._consumer(historical, {
                "GITHUB_RUN_ID": str(receipt["producer"]["runId"]),
                "GITHUB_RUN_ATTEMPT": str(receipt["producer"]["runAttempt"]),
            })["producer"]
            if producer != receipt["producer"]:
                raise ValueError("Original Android metadata historical producer differs from its receipt")
            selection = original / "selection"
            if (_json(selection / "phase-plan.json") !=
                    {name: receipt[name] for name in PHASE_PLAN_KEYS}
                    or _json(selection / "producer.json") != receipt["producer"]):
                raise ValueError("Original Android metadata retained selection differs from its receipt")
            inputs = original / "inputs"
            if (_json(inputs / "phase-plan.json") !=
                    {name: receipt[name] for name in PHASE_PLAN_KEYS}
                    or _json(inputs / "producer.json") != receipt["producer"]):
                raise ValueError("Original Android metadata election differs from its receipt")
            validation_directory = inputs / "sdk-sdk-android-validation-android"
            validation_receipt_path = validation_directory / "phase-receipt.json"
            validation_raw = _read(validation_receipt_path)
            validation_receipt = validate_phase_receipt(load_canonical_json_bytes(validation_raw))
            if (tuple(validation_receipt[name] for name in
                      ("product", "component", "phase", "target")) !=
                    ("sdk", "sdk-android", "validation", "android")
                    or validation_receipt["productVersion"] != receipt["productVersion"]):
                raise ValueError("Original Android metadata validation has the wrong identity")
            common = dict(
                package_stage=trees["package"], package_receipt=files["packageReceipt"],
                binary_stage=trees["binary"], binary_receipt=files["binaryReceipt"],
                compatibility_request=files["compatibilityRequest"],
                binary_contract_evidence=binary_contract_evidence,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree,
                tooling_evidence=trees["tooling"], tooling_public_key=files["toolingPublicKey"],
                java_executable=files["java"], apkanalyzer_executable=files["apkanalyzer"],
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                repository_root=root, environ=environ, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            with verified_retained_android_validation(
                    plan, validation_receipt_path,
                    validation_capture=trees["validationCapture"], **common) as validation:
                _same_stage(validation_directory, validation["stage"],
                            validation["receiptBytes"], "validation")
                package_directory = inputs / "sdk-sdk-android-package-android"
                _same_stage(package_directory, trees["package"],
                            before_files["packageReceipt"], "package")
                if (validation["receiptBytes"] != validation_raw
                        or validation["receipt"] != validation_receipt
                        or regular_file_inventory(original / "originals/validation", allow_empty=True) !=
                           regular_file_inventory(validation["capture"], allow_empty=True)):
                    raise ValueError("Original Android metadata retained validation differs from full replay")
                validation_content = validate_android_validation_content(load_canonical_json_bytes(
                    _read(validation["stage"] / validation_phase.OUTPUT_PATH)))
                request = private / "expected-request.json"
                write_canonical_json(request, {
                    "sdkVersion": receipt["productVersion"],
                    "packageStage": str(trees["package"]),
                    "packageReceipt": str(files["packageReceipt"]),
                    "validationStage": str(validation["stage"]),
                    "validationReceipt": str(validation["receiptPath"]),
                    "releaseAarSha256": validation_content["releaseAarSha256"],
                    "bundledRuntimeSha256": validation_content["bundledRuntimeSha256"],
                })
                expected_path = private / "expected-content.json"
                expected = write_android_metadata_content(request, expected_path)
                _worker(original, receipt, context, validation_content)
                _replan(root, receipt, validation["receipt"])
                if (_read(stage / OUTPUT_PATH) != canonical_json_bytes(expected)
                        or _read(expected_path) != canonical_json_bytes(expected)):
                    raise ValueError("Original Android metadata content differs from full replay")
                retained[private] = regular_file_inventory(private, allow_empty=True)
                result = {"stage": stage, "receiptPath": selected,
                    "receiptBytes": raw, "receipt": receipt,
                    "original": original, "capture": capture, "transport": transport}
                result_bytes = _result_view(result)
                unchanged()
                yield result
                unchanged()
            unchanged()
        finally:
            unchanged()
            if _read(selected) != raw:
                raise ValueError("Selected original Android metadata receipt changed")
