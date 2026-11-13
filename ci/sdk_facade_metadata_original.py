"""Recover original Core metadata through observed transport and eleven full gates.

Caller policy supplies original invocation paths independently of worker JSON.
Official job labels bind transport routing, not hardware/compiler authority.
Private paths live only through the context; no receipt or host token is minted.
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
    read_regular_file_bytes, require_exact_keys, require_integer,
    require_regular_directory, run_git, sha256_bytes, sha256_file, snapshot_regular_tree,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_facade_inputs import _request, _sources
from products.sdk_facade_validation import _inventory, _original_path
from products.sdk_package import _require_capability_output_separate
from products.sdk_platform_metadata import OUTPUT_KIND, OUTPUT_PATH
from products.sdk_validation_inputs import _request_inventory
from products.selection import phase_git_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import capture_sdk_facade_metadata_upload, verify_retained_sdk_phase_upload
from sdk_facade_metadata_inputs import (
    _records, _view, _native_archives, _validation_original_reference, verified_facade_metadata_inputs,
)


_INSTANCE = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


def verify_completed_facade_metadata(envelope, validation_envelopes, *, plan, discovery, state,
        bootstrap, caller, trusted_workflow_sha, repository_root, environ, token,
        completed_frozen, sdk_validation_tooling, sdk_apple_validation_policy=None):
    """Join native-qualified predecessors without expanding their old carriers.

    The complete metadata ZIP is still authenticated. Each validation reference
    is matched to its freshly observed native-qualified original. Legacy embedded
    ZIPs retain their full inventory comparison with the retained extraction.
    At most one legacy nested ZIP and independently verified stages occupy scratch.
    No semantic success is cached: staged replay performs these checks again.
    """
    import zipfile
    from reuse_qualification import CompletedFrozenReuse
    from products.reuse import _validate_envelope
    from products.inventory import regular_file_inventory, write_canonical_json
    from products.sdk_platform_metadata import write_facade_metadata_content
    from runtime_reference_archive import copy_reference_member
    from sdk_campaign_original_locator import retained_core_origin
    from sdk_facade_capture import _capture_route, _METADATA_WORKFLOW_PATH
    from sdk_facade_original_inputs import _fresh_policy_sources

    if type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Core metadata requires concrete native predecessor authority")
    require_exact_keys(caller, {"buildKey", "receiptSha256", "artifactId", "artifactSha256",
        "originalContext", "sdkInputsArtifactId", "sdkInputsArtifactSha256", "toolingPolicy"}, "Completed Core caller")
    if not isinstance(validation_envelopes, (list, tuple)):
        raise ValueError("Completed Core predecessors must be an explicit sequence")
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    instance, selected = _validate_envelope(envelope)
    if instance != _INSTANCE:
        raise ValueError("Completed Core join requires its exact metadata identity")
    receipt, raw = selected["receipt"], selected["receiptBytes"]
    if receipt["buildKey"] != caller["buildKey"] or selected["receiptSha256"] != caller["receiptSha256"]:
        raise ValueError("Completed Core metadata differs from caller selection")
    context = _context(caller["originalContext"])
    policy_bytes, caller_bytes = canonical_json_bytes(bootstrap), canonical_json_bytes(caller)
    files, trees = _fresh_policy_sources(bootstrap)
    elected = product_reuse._verified_product_state(Path(plan), Path(discovery), Path(state), root,
        environ, sdk_validation_tooling, requested_scope=(_INSTANCE,), completed_frozen=completed_frozen,
        sdk_original_workflow_sha=trusted_workflow_sha, sdk_apple_validation_policy=sdk_apple_validation_policy)
    ready = elected.prior_ready_plans.get(_INSTANCE)
    if ready is None or ready["buildKey"] != receipt["buildKey"]:
        raise ValueError("Completed Core metadata is not elected with its exact key")
    consumer = product_reuse._consumer(elected.plan, environ)["producer"]
    completed_frozen.check_consumer({"kind": "ci", "producer": consumer})
    workflow, origin = trusted_workflow_sha, None
    if receipt["producer"] != consumer:
        origin = retained_core_origin("metadata", receipt["buildKey"], consumer)
        if (origin is None or origin["producer"] != receipt["producer"]
                or origin["artifact_id"] != caller["artifactId"]
                or origin["artifact_sha256"] != caller["artifactSha256"]
                or origin["receipt_sha256"] != selected["receiptSha256"] or origin["context"] != context):
            raise ValueError("Completed Core metadata differs from its reviewed original")
        workflow = origin["workflow_sha"]

    supplied = {}
    for value in validation_envelopes:
        identity, value = _validate_envelope(value)
        if identity in supplied:
            raise ValueError("Completed Core validations must be unique")
        supplied[identity] = value
    expected_ids = {PhaseInstanceId("sdk", "sdk-core", "validation", t) for t in SDK_FACADE_TARGETS}
    if set(supplied) != expected_ids:
        raise ValueError("Completed Core metadata requires all eleven validations")
    package_id = PhaseInstanceId("sdk", "sdk-core", "package", "common")
    native, originals = {}, {}
    for identity in sorted(expected_ids | {package_id}):
        row = elected.prior_by_instance[identity]
        qualified = completed_frozen.envelope(row)
        if qualified is None or row["state"] != "retained":
            raise ValueError("Core predecessor lacks exact native semantic qualification")
        if identity in supplied and supplied[identity] != qualified:
            raise ValueError("Core predecessor differs from its native-qualified envelope")
        native[identity] = qualified
        _, original, _ = completed_frozen.observe_extended_sdk(row, producer=consumer, token=token)
        originals[identity] = original
    binding = raw, selected["receiptSha256"], selected["objectSha256"]
    predecessor_ids = tuple(map(id, validation_envelopes))
    stage_sources, private_stages = {}, {}

    def unchanged():
        require_no_signing_secret(environ)
        completed_frozen.check_consumer({"kind": "ci", "producer": consumer})
        if (canonical_json_bytes(bootstrap) != policy_bytes or canonical_json_bytes(caller) != caller_bytes
                or (selected["receiptBytes"], selected["receiptSha256"], selected["objectSha256"]) != binding
                or canonical_json_bytes(selected["receipt"]) != raw
                or any(sha256_file(path, reject_symlink_parents=True) != digest for path, digest in files.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in trees.items())):
            raise ValueError("Completed Core metadata caller or inputs changed")
        for identity, value in native.items():
            if completed_frozen.envelope(elected.prior_by_instance[identity]) != value:
                raise ValueError("Completed Core predecessor authority changed")
        if (tuple(map(id, validation_envelopes)) != predecessor_ids
                or {_validate_envelope(v)[0]: _validate_envelope(v)[1] for v in validation_envelopes}
                   != {identity: native[identity] for identity in expected_ids}
                or any(regular_file_inventory(path) != before for path, before in stage_sources.items())
                or any(regular_file_inventory(path) != before for path, before in private_stages.items())):
            raise ValueError("Completed Core selected predecessors changed")

    unchanged()
    with tempfile.TemporaryDirectory(prefix="completed-core-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *files, *trees])
        stages, receipt_paths = {}, {}
        first, _ = _request(Path(bootstrap["validations"][SDK_FACADE_TARGETS[0]]["facadeRequest"]))
        for target, identity in [("package", package_id), *((t, PhaseInstanceId("sdk", "sdk-core", "validation", t)) for t in SDK_FACADE_TARGETS)]:
            source_receipt = Path(first["packageReceipt"] if target == "package" else bootstrap["validations"][target]["validationReceipt"])
            source_stage = Path(first["packageStage"]) if target == "package" else source_receipt.parent / "stage"
            stage_sources[source_stage] = regular_file_inventory(source_stage)
            value = native[identity]
            if _read(source_receipt) != value["receiptBytes"]:
                raise ValueError("Completed Core stage receipt differs from native authority")
            stage = private / "predecessors" / target / "stage"
            snapshot_regular_tree(source_stage, stage)
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", identity.phase,
                                                       identity.target, value["receipt"]["productVersion"])
            if manifest["outputs"] != value["receipt"]["outputs"]:
                raise ValueError("Completed Core stage differs from native-qualified outputs")
            receipt_path = stage.parent / "phase-receipt.json"
            receipt_path.write_bytes(value["receiptBytes"])
            stages[target], receipt_paths[target] = stage, receipt_path
            private_stages[stage.parent] = regular_file_inventory(stage.parent)
        request = private / "request.json"
        write_canonical_json(request, {"sdkVersion": receipt["productVersion"],
            "packageStage": str(stages["package"]), "packageReceipt": str(receipt_paths["package"]),
            "contractDigest": bootstrap["contractDigest"], "componentDigests": bootstrap["componentDigests"],
            "validations": {t: {"stageRoot": str(stages[t]), "phaseReceipt": str(receipt_paths[t])} for t in SDK_FACADE_TARGETS}})
        expected_content = canonical_json_bytes(write_facade_metadata_content(request, private / "expected.json"))
        _, runner, _, job, name, _ = _capture_route(receipt, "facade-metadata")
        observed = product_reuse._observe_ci_producer_jobs({"facade-metadata": receipt["producer"]},
            jobs_by_phase={"facade-metadata": job}, build_keys_by_phase={"facade-metadata": receipt["buildKey"]},
            token=token, trusted_workflows_by_phase={"facade-metadata": {"path": _METADATA_WORKFLOW_PATH, "sha": workflow}})
        jobs = product_reuse._matching_ci_jobs(observed[0]["jobs"], job, expected_build_key=receipt["buildKey"])
        labels = jobs[0].get("labels") if len(jobs) == 1 else None
        if (type(labels) is not list or any(type(label) is not str for label in labels) or runner not in labels
                or origin is not None and jobs[0].get("id") != origin["job_id"]):
            raise ValueError("Completed Core original lacks its fixed successful worker route")
        require_integer(jobs[0].get("runner_id"), "Original Core metadata runner", 1)
        archive = private / "metadata.zip"
        artifact, _ = product_reuse._download_contract_ci_upload(caller["artifactId"], caller["artifactSha256"],
            name, receipt["producer"], observed[0]["run"], token, destination=archive,
            upload_limit=product_reuse._IOS_PACKAGE_UPLOAD_LIMIT)
        product_reuse._require_artifact_job_window(observed[0], jobs[0]["name"], artifact)
        records = product_reuse._core_metadata_upload_inventory(archive,
            {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}, _INSTANCE)
        index = {r["relativePath"]: r for r in records}
        with zipfile.ZipFile(archive) as zipped:
            names = tuple(info.filename.rstrip("/") for info in zipped.infolist())

        def inventory(prefix):
            return [{**r, "relativePath": r["relativePath"][len(prefix):]} for r in records if r["relativePath"].startswith(prefix)]

        def roots(prefix):
            return {name[len(prefix):].split("/", 1)[0] for name in names if name.startswith(prefix) and name != prefix.rstrip("/")}

        expected_roots = {"shard", "worker", "selection", "originals", "inputs"}
        if "worker-dependency-seed" in roots(""):
            expected_roots.add("worker-dependency-seed")
        if (roots("") != expected_roots or any(name in index for name in expected_roots)
                or roots("worker/") != {"execution.json", "gradle.log"}
                or roots("selection/") != {"impact-plan.json", "phase-plan.json", "producer.json"}
                or roots("originals/") != {"package", "validations", "metadata-request.json"}
                or roots("originals/validations/") != set(SDK_FACADE_TARGETS)):
            raise ValueError("Completed Core original has an unexpected retained layout")
        projected = private / "original"
        projection = []
        with zipfile.ZipFile(archive) as zipped:
            for row in records:
                name = row["relativePath"]
                if name.startswith(("shard/", "worker/", "selection/")) or name in {
                        "originals/metadata-request.json", "inputs/producer.json", "inputs/phase-plan.json"}:
                    if row["bytes"] > 512 * 1024 * 1024:
                        raise ValueError("Core metadata control exceeds its original reader bound")
                    copy_reference_member(zipped, name, projected / name, row)
                    projection.append(row)
            for target, identity in [("package", package_id), *((t, PhaseInstanceId("sdk", "sdk-core", "validation", t)) for t in SDK_FACADE_TARGETS)]:
                prefix = "originals/package/" if target == "package" else f"originals/validations/{target}/"
                referenced = target != "package" and "original-reference.json" in roots(prefix)
                expected = {"stage", "phase-receipt.json"}
                if target != "package":
                    expected.add("original-reference.json" if referenced else "capture")
                if roots(prefix) != expected:
                    raise ValueError("Completed Core retained predecessor layout differs")
                selected_prefix = "inputs/sdk-sdk-core-package-common/" if target == "package" else f"inputs/sdk-sdk-core-validation-{target}/"
                for parent in (prefix, selected_prefix):
                    if (inventory(parent + "stage/") != regular_file_inventory(stages[target])
                            or index[parent + "phase-receipt.json"]["sha256"] != native[identity]["receiptSha256"]
                            or index[parent + "phase-receipt.json"]["bytes"] != len(native[identity]["receiptBytes"])):
                        raise ValueError("Completed Core retained predecessor differs from native-qualified bytes")
                if referenced:
                    name = prefix + "original-reference.json"
                    expected = canonical_json_bytes(_validation_original_reference(
                        native[identity]["receiptBytes"], originals[identity]))
                    if index.get(name) != {"relativePath": name, "bytes": len(expected), "sha256": sha256_bytes(expected)}:
                        raise ValueError("Core original reference differs from its native-qualified original")
                elif target != "package":
                    member = index[prefix + "capture/transport.zip"]
                    original = originals[identity]
                    if member["sha256"] != original["digest"] or member["bytes"] != original["size_in_bytes"]:
                        raise ValueError("Embedded Core validation differs from its native-qualified original")
                    nested = private / "validation.zip"
                    copy_reference_member(zipped, member["relativePath"], nested, member)
                    try:
                        contents = product_reuse._core_metadata_upload_inventory(nested,
                            {"sha256": member["sha256"], "bytes": member["bytes"]}, identity)
                        if contents != inventory(prefix + "capture/original/"):
                            raise ValueError("Embedded Core validation extraction differs from its full original ZIP")
                    finally:
                        nested.unlink()
        if regular_file_inventory(projected, allow_empty=True) != projection:
            raise ValueError("Completed Core original controls changed during projection")
        for parent in ("selection", "inputs"):
            if (_json(projected / parent / "producer.json") != receipt["producer"]
                    or _json(projected / parent / "phase-plan.json") != {n: receipt[n] for n in PHASE_PLAN_KEYS}):
                raise ValueError("Completed Core retained election differs from its receipt")
        shard = verify_phase_shard(projected / "shard", _INSTANCE)
        if any(shard[n] != selected[n] for n in ("receiptBytes", "receiptSha256", "objectSha256")):
            raise ValueError("Completed Core original shard differs from selected metadata")
        output = private / "metadata-stage"
        restore_object(projected / "shard" / shard["objectPath"], output, build_key=receipt["buildKey"],
            receipt_sha256=selected["receiptSha256"], object_sha256=selected["objectSha256"])
        manifest = verify_output_manifest_identity(output, "sdk", "sdk-core", "metadata", "common", receipt["productVersion"])
        if (manifest["outputs"] != receipt["outputs"] or len(manifest["outputs"]) != 1
                or manifest["outputs"][0]["kind"] != OUTPUT_KIND or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH
                or _read(output / OUTPUT_PATH) != expected_content):
            raise ValueError("Completed Core metadata differs from the native-qualified deterministic join")
        historical = product_reuse._validate_plan(projected / "selection/impact-plan.json", root,
                                                 expected_revision=receipt["producer"]["commit"])
        producer = receipt["producer"]
        if (historical["remoteBuildAuthorized"] is not True or historical["event"] not in {"pull_request", "merge_group"}
                or product_reuse._consumer(historical, {"GITHUB_RUN_ID": str(producer["runId"]),
                    "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"] != producer):
            raise ValueError("Completed Core original historical plan is not authorized")
        _worker(projected, receipt, context, bootstrap["contractDigest"], bootstrap["componentDigests"])
        _replan(root, receipt, {t: native[PhaseInstanceId("sdk", "sdk-core", "validation", t)] for t in SDK_FACADE_TARGETS})
        if archive.stat().st_size != artifact["size_in_bytes"] or sha256_file(archive) != artifact["digest"]:
            raise ValueError("Original Core metadata archive changed while consumed")
        if regular_file_inventory(projected, allow_empty=True) != projection:
            raise ValueError("Completed Core original controls changed while consumed")
        unchanged()
    private_stages.clear()
    unchanged()


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=512 * 1024 * 1024, reject_symlink_parents=True)


def _json(path):
    return load_canonical_json_bytes(_read(path))


def _layout(directory, names):
    require_regular_directory(directory, "Original Core metadata directory")
    if {path.name for path in directory.iterdir()} != set(names):
        raise ValueError("Original Core metadata has an unexpected retained layout")


def _context(value):
    require_exact_keys(value, {"repositoryRoot", "metadataRequest"}, "Caller original metadata context")
    for name, path in value.items():
        _original_path(path, "Original metadata " + name)
        if PureWindowsPath(path).drive or not PurePosixPath(path).is_absolute():
            raise ValueError("Original Core metadata requires exact POSIX invocation paths")
    return value


def _worker(original, receipt, context, contract_digest, component_digests):
    record = require_exact_keys(_json(original / "worker/execution.json"),
        {"schemaVersion", "producer", "buildKey", "command", "workingDirectory", "returnCode", "launchError", "elapsedNs"},
        "Original Core metadata execution")
    if (require_integer(record["schemaVersion"], "Metadata execution schema", 1) != 1
            or record["producer"] != receipt["producer"] or record["buildKey"] != receipt["buildKey"]
            or require_integer(record["returnCode"], "Metadata execution exit", 0) != 0
            or record["launchError"] is not None or record["workingDirectory"] != context["repositoryRoot"]):
        raise ValueError("Original Core metadata worker differs from its receipt or caller context")
    require_integer(record["elapsedNs"], "Metadata execution elapsed time", 0)
    fields = {"codexAgent.product": "sdk", "codexAgent.component": "sdk-core", "codexAgent.phase": "metadata",
        "codexAgent.target": "common", "codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.candidateCommit": receipt["producer"]["commit"], "codexAgent.candidateTree": receipt["producer"]["tree"],
        "codexAgent.sdkFacadeMetadataRequest": context["metadataRequest"]}
    expected = product_reuse._runtime_worker_command(PurePosixPath(context["repositoryRoot"]) / "gradlew",
        fields, {}, build_directory=".", platform_name="posix")
    if record["command"] != expected:
        raise ValueError("Original Core metadata worker differs from the fixed offline command")
    request = require_exact_keys(_json(original / "originals/metadata-request.json"),
        {"sdkVersion", "packageStage", "packageReceipt", "contractDigest", "componentDigests", "validations"},
        "Original metadata invocation request")
    if (request["sdkVersion"] != receipt["productVersion"] or request["contractDigest"] != contract_digest
            or request["componentDigests"] != component_digests):
        raise ValueError("Original metadata request differs from independent caller identity")
    paths = [request["packageStage"], request["packageReceipt"]]
    for row in require_exact_keys(request["validations"], SDK_FACADE_TARGETS, "Original metadata validations").values():
        require_exact_keys(row, {"stageRoot", "phaseReceipt"}, "Original metadata validation input")
        paths.extend(row.values())
    for path in paths:
        _original_path(path, "Original metadata input path")
        if PureWindowsPath(path).drive:
            raise ValueError("Original metadata input paths must be POSIX")


def _replan(root, receipt, validations):
    producer = receipt["producer"]
    commit = producer["commit"]
    try:
        if (run_git(root, "rev-parse", f"{commit}^{{commit}}").strip() != commit
                or run_git(root, "rev-parse", f"{commit}^{{tree}}").strip() != producer["tree"]):
            raise ValueError("Original Core metadata commit/tree differs from Git")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original Core metadata source is unavailable") from error
    versions = git_product_versions(root, commit)
    planned = plan_phase(_INSTANCE, inventory=phase_git_inventory(root, commit, _INSTANCE), versions=versions,
        upstream_receipts=[validations[target]["receipt"] for target in SDK_FACADE_TARGETS],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
    if (receipt["productVersion"] != versions["sdk"] or receipt["inputs"] != planned["inputs"]
            or receipt["buildKey"] != planned["buildKey"]):
        raise ValueError("Original Core metadata differs from its original source/version/phase key")


def _retained(original, held, receipt):
    originals = original / "originals"
    _layout(originals, {"package", "validations", "metadata-request.json"})
    _layout(originals / "validations", SDK_FACADE_TARGETS)
    for target, value in {"package": held["package"], **held["validations"]}.items():
        retained = originals / "package" if target == "package" else originals / "validations" / target
        referenced = target != "package" and (retained / "original-reference.json").exists()
        expected = {"stage", "phase-receipt.json"}
        if target != "package":
            expected.add("original-reference.json" if referenced else "capture")
        _layout(retained, expected)
        selected = original / "inputs" / ("sdk-sdk-core-package-common" if target == "package" else
                                          f"sdk-sdk-core-validation-{target}")
        for parent in (retained, selected):
            if (_read(parent / "phase-receipt.json") != value["receiptBytes"]
                    or _inventory(parent / "stage") != _inventory(value["stage"])):
                raise ValueError("Original metadata retained predecessor differs from full original replay")
        if referenced:
            expected = canonical_json_bytes(_validation_original_reference(value["receiptBytes"], value["transport"]["artifact"]))
            if _read(retained / "original-reference.json") != expected:
                raise ValueError("Core original reference differs from full original replay")
        elif target != "package":
            # Observations and current capture plans can legitimately change;
            # the original ZIP and complete extracted payload cannot.
            if (sha256_file(retained / "capture/transport.zip") != sha256_file(value["capture"] / "transport.zip")
                    or _inventory(retained / "capture/original", allow_empty=True) !=
                       _inventory(value["original"], allow_empty=True)):
                raise ValueError("Original metadata validation capture differs from original upload bytes")
    for parent in (original / "selection", original / "inputs"):
        if (_json(parent / "producer.json") != receipt["producer"]
                or _json(parent / "phase-plan.json") != {name: receipt[name] for name in PHASE_PLAN_KEYS}):
            raise ValueError("Original metadata retained election differs from its receipt")


@contextmanager
def verified_original_sdk_facade_metadata(plan, metadata_receipt_path, *, artifact_id, artifact_sha256,
        validations, contract_digest, component_digests, original_context, repository_root, environ, token,
        trusted_workflow_sha, tooling_evidence, tooling_public_key, java_executable, policy_revision,
        required_trust_domain, tooling_keyring=None, tooling_keys_directory=None):
    """Hold original metadata and all eleven full replays; never rebuild products.

    Original invocation context and all trust inputs are independently supplied
    caller policy, not authority recovered from uploaded request/worker records.
    """
    with _verified_sdk_facade_metadata(plan, metadata_receipt_path, capture_root=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, validations=validations,
            contract_digest=contract_digest, component_digests=component_digests, original_context=original_context,
            repository_root=repository_root, environ=environ, token=token, trusted_workflow_sha=trusted_workflow_sha,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as result:
        yield result


@contextmanager
def verified_retained_sdk_facade_metadata(plan, metadata_receipt_path, *, capture_root,
        validations, contract_digest, component_digests, original_context, repository_root, environ,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None):
    """Hold full offline replay inside independently authenticated caller carriers.

    All eleven validations must also use retained captureRoot records. Neither
    private copies nor stored transport observations authenticate themselves.
    Original invocation context, native archives and tooling policy remain
    independent caller inputs, never recovered from retained metadata paths.
    """
    with _verified_sdk_facade_metadata(plan, metadata_receipt_path, capture_root=Path(capture_root),
            validations=validations, contract_digest=contract_digest, component_digests=component_digests,
            original_context=original_context, repository_root=repository_root, environ=environ,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory) as result:
        yield result


@contextmanager
def _verified_sdk_facade_metadata(plan, metadata_receipt_path, *, capture_root,
        validations, contract_digest, component_digests, original_context, repository_root, environ,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring, tooling_keys_directory, artifact_id=None, artifact_sha256=None,
        token=None, trusted_workflow_sha=None):
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path = Path(plan), Path(metadata_receipt_path)
    context = _context(original_context)
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != ("sdk", "sdk-core", "metadata", "common"):
        raise ValueError("Core metadata recovery requires its exact selected receipt")
    records = _records(validations)
    if capture_root is not None and any("captureRoot" not in record for record in records.values()):
        raise ValueError("Retained Core metadata requires all eleven caller-authenticated retained validations")
    archives = _native_archives(records)
    files = {plan, receipt_path, Path(tooling_public_key), Path(java_executable)}
    trees = {Path(tooling_evidence)}
    if capture_root is not None:
        if not capture_root.is_absolute() or capture_root.resolve(strict=True) != capture_root:
            raise ValueError("Retained Core metadata capture must be absolute, normalized and non-symbolic")
        trees.add(capture_root)
        trees.update(Path(record["captureRoot"]) for record in records.values())
    compatibility = {}
    for record in records.values():
        path = Path(record["facadeRequest"])
        request, _ = _request(path)
        _, request_trees, request_files = _sources(request)
        trees.update(request_trees.values())
        files.update(request_files.values())
        files.update((path, Path(record["validationReceipt"])))
        compatibility[Path(request["compatibilityRequest"])] = _request_inventory(Path(request["compatibilityRequest"]))
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Core metadata tooling keyring and keys must be paired")
    if tooling_keyring is not None:
        files.add(Path(tooling_keyring))
        trees.add(Path(tooling_keys_directory))
    before_files = {path: _read(path) for path in files}
    before_trees = {path: _inventory(path, allow_empty=True) for path in trees}
    def policy():
        return canonical_json_bytes({"validations": _records(validations), "context": _context(original_context),
            "contractDigest": contract_digest, "componentDigests": component_digests})
    before_policy = policy()
    retained = {}
    result = result_before = transport = transport_before = None
    def unchanged():
        require_no_signing_secret(environ)
        if (policy() != before_policy or canonical_json_bytes(receipt) != raw or _read(receipt_path) != raw
                or _native_archives(records) != archives
                or any(_read(path) != value for path, value in before_files.items())
                or any(_inventory(path, allow_empty=True) != value for path, value in before_trees.items())
                or any(_request_inventory(path) != value for path, value in compatibility.items())
                or any(_inventory(path, allow_empty=True) != value for path, value in retained.items())
                or (transport is not None and canonical_json_bytes(transport) != transport_before)
                or (result is not None and _view(result) != result_before)):
            raise ValueError("Original Core metadata inputs, outputs or caller authority changed")
    with tempfile.TemporaryDirectory(prefix="original-core-metadata-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *files, *trees, *compatibility, *archives])
        selected = private / "selected-receipt.json"
        selected.write_bytes(raw)
        try:
            unchanged()
            capture = private / "capture"
            if capture_root is None:
                transport = capture_sdk_facade_metadata_upload(plan, capture, metadata_receipt_path=selected,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=root, environ=environ, token=token)
            else:
                snapshot_regular_tree(capture_root, capture, allow_empty=True)
                if _inventory(capture, allow_empty=True) != before_trees[capture_root]:
                    raise ValueError("Retained Core metadata capture changed during snapshot")
                verify_retained_sdk_phase_upload(capture, raw)
                transport = _json(capture / "capture-transport.json")
            transport_before = canonical_json_bytes(transport)
            if (transport["metadataReceiptSha256"] != sha256_bytes(raw) or transport["captureProducer"] != receipt["producer"]
                    or _read(capture / "capture-transport.json") != canonical_json_bytes(transport)):
                raise ValueError("Original metadata capture differs from the selected receipt")
            retained[capture] = _inventory(capture, allow_empty=True)
            original = capture / "original"
            roots = {"shard", "worker", "selection", "originals", "inputs"}
            if (original / "worker-dependency-seed").exists():
                require_regular_directory(original / "worker-dependency-seed", "SDK dependency seed diagnostics")
                roots.add("worker-dependency-seed")
            _layout(original, roots)
            _layout(original / "worker", {"execution.json", "gradle.log"})
            _layout(original / "selection", {"impact-plan.json", "phase-plan.json", "producer.json"})
            shard = verify_phase_shard(original / "shard", _INSTANCE)
            stage = private / "stage"
            restored = restore_object(original / "shard" / shard["objectPath"], stage, build_key=shard["buildKey"],
                receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", "metadata", "common", receipt["productVersion"])
            if (shard["receiptBytes"] != raw or restored["receiptBytes"] != raw or manifest["outputs"] != receipt["outputs"]):
                raise ValueError("Original metadata shard/stage differs from the selected receipt")
            producer = receipt["producer"]
            historical = product_reuse._validate_plan(original / "selection/impact-plan.json", root, expected_revision=producer["commit"])
            if historical["remoteBuildAuthorized"] is not True or historical["event"] not in {"pull_request", "merge_group"}:
                raise ValueError("Original metadata impact plan is not authorized")
            consumer = product_reuse._consumer(historical, {"GITHUB_RUN_ID": str(producer["runId"]),
                "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"]
            if consumer != producer:
                raise ValueError("Original metadata historical producer differs from its receipt")
            _worker(original, receipt, context, contract_digest, component_digests)
            retained[private] = _inventory(private, allow_empty=True)
            with verified_facade_metadata_inputs(plan=plan, validations=validations, contract_digest=contract_digest,
                    component_digests=component_digests, repository_root=root, environ=environ, token=token,
                    trusted_workflow_sha=trusted_workflow_sha, tooling_evidence=tooling_evidence,
                    tooling_public_key=tooling_public_key, java_executable=java_executable, policy_revision=policy_revision,
                    required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                    tooling_keys_directory=tooling_keys_directory) as held:
                _retained(original, held, receipt)
                _replan(root, receipt, held["validations"])
                if (held["package"]["receipt"]["productVersion"] != receipt["productVersion"]
                        or len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != OUTPUT_KIND
                        or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH
                        or _read(stage / OUTPUT_PATH) != held["expectedContentBytes"]
                        or canonical_json_bytes(held["expectedContent"]) != held["expectedContentBytes"]):
                    raise ValueError("Original Core metadata content differs from the complete original join")
                result = {"stage": stage, "receiptPath": selected, "receiptBytes": raw, "receipt": receipt,
                    "original": original, "capture": capture, "transport": transport}
                result_before = _view(result)
                unchanged()
                yield result
                unchanged()
            unchanged()
        finally:
            unchanged()
            if _read(selected) != raw:
                raise ValueError("Original Core metadata private receipt changed")
