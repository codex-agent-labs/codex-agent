"""Recover original Apple validation and replay its existing complete content gate.

This reader re-plans original inputs but does not grant election or release
admission. Original receipts and externally authenticated execution bytes are
never rewritten.
"""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import sys
import os
import tempfile
import subprocess

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_array, require_exact_keys, require_integer, require_regular_directory, run_git, sha256_file,
    snapshot_regular_tree, publish_regular_tree, require_sha256, sha256_bytes, write_canonical_json,
    verified_zip_contents,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_apple_content import _input_inventory
from products.sdk_apple_device_evidence import _original_directory
from products.sdk_apple_validation_context import verify_apple_validation_context
from products.sdk_apple_validation_execution import verify_apple_validation_stage
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from products.selection import phase_git_inventory
from sdk_ios_original_binary import verified_original_ios_binary, verified_retained_ios_binary
from sdk_ios_original_package import (
    verified_original_ios_package, verified_retained_ios_package, verified_completed_ios_package,
)


_LIMIT = 16 * 1024 * 1024


def validation_recovery_origin(phase):
    """One reviewed raw production candidate; never a receipt or admission.

    ponytail: recover the known successful production, not all historical jobs.
    Additional candidates require explicit review and the same complete replay.
    """
    if (phase.get("product"), phase.get("component"), phase.get("phase"),
            phase.get("target"), phase.get("buildKey")) != (
            "sdk", "sdk-ios", "validation", "ios-simulator-arm64",
            "sha256:e7958fc10f983e5ddc41714a80587eacf8cd9ccd715b1829873113fd606917b7"):
        return None
    return {"schemaVersion": 1, "artifactId": 11887642828,
        "artifactSha256": "sha256:1fcabf764b6704874b128cf7920a73450c738105fbb53e03a992c23626f0ec1d",
        "jobId": 115797844805, "workflowSha": "d465d7c7bbc488ae3eefaee3e4319a67780ae3c3",
        "producer": {"repository": "codex-agent-labs/codex-agent", "workflowPath": ".github/workflows/ci.yml",
            "commit": "ab0dbd1924a6307a1dcf75dfeeca522cb84d216c",
            "tree": "94ad174c3467edbb7c4bb43a78afb0a76710fda1", "event": "pull_request",
            "runId": 38546591891, "runAttempt": 1, "pullRequest": 31}}


def observe_validation_recovery(plan, consumer, phase, origin, *, repository_root, token):
    """Freshly authenticate the failed original; do not promote its job outcome."""
    from sdk_ios_binary_recovery import _require_prior
    from sdk_handoff import _ensure_observed_sdk_commit
    expected = validation_recovery_origin(phase)
    if expected is None or canonical_json_bytes(origin) != canonical_json_bytes(expected):
        raise ValueError("Apple validation recovery differs from its independently selected origin")
    producer = product_reuse.validate_producer(origin["producer"])
    prior = product_reuse._original_ci_run(producer, token)
    run, attempt = _require_prior(plan, consumer, prior)
    if (run, attempt) != (producer["runId"], producer["runAttempt"]):
        raise ValueError("Apple validation recovery differs from its exact original attempt")
    workflow = "codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@" + origin["workflowSha"]
    product_reuse._require_ci_workflow_reference(prior, workflow, origin["workflowSha"])
    instance = PhaseInstanceId("sdk", "sdk-ios", "validation", phase["target"])
    name = (product_reuse._worker_artifact_prefix("sdk", instance) + phase["buildKey"][7:]
            + "-" + producer["tree"] + f"-attempt-{attempt}")
    artifact = product_reuse._contract_ci_upload_metadata(
        origin["artifactId"], origin["artifactSha256"], name, producer, prior, token)
    url = f"https://api.github.com/repos/{producer['repository']}/actions/runs/{run}/attempts/{attempt}/jobs"
    jobs = product_reuse._matching_ci_jobs(product_reuse.paginated_items(url, "jobs", token),
        "product-validation / sdk-sdk-ios-validation-" + phase["target"], expected_build_key=phase["buildKey"])
    if (len(jobs) != 1 or jobs[0].get("id") != origin["jobId"]
            or jobs[0].get("status") != "completed" or jobs[0].get("conclusion") != "failure"
            or jobs[0].get("run_id") != run or jobs[0].get("head_sha") != prior["head_sha"]):
        raise ValueError("Apple validation recovery differs from its original failed job")
    product_reuse._require_artifact_job_window({"jobs": jobs}, jobs[0]["name"], artifact)
    product_reuse._observe_tested_commit(prior, api="https://api.github.com", repository=producer["repository"],
        token=token, expected_commit=producer["commit"], expected_tree=producer["tree"],
        pull_request=producer["pullRequest"])
    _ensure_observed_sdk_commit(repository_root, producer, token)
    return artifact, prior


@contextmanager
def verified_validation_recovery(plan, consumer, phase, origin, archive, *, package,
        repository_root, token, download=False):
    """Authenticate raw origin and fixed execution before the separate full content gate.

    Retain the outer ZIP once. Extract only consumed members privately; a failed
    original still grants no successful-phase, host or semantic authority.
    """
    artifact, prior = observe_validation_recovery(plan, consumer, phase, origin,
        repository_root=repository_root, token=token)
    origin_bytes, phase_bytes = canonical_json_bytes(origin), canonical_json_bytes(phase)
    archive = Path(archive)
    if download:
        if archive.exists() or archive.is_symlink():
            raise ValueError("Apple validation recovery download destination already exists")
        product_reuse._reuse_contract_ci_upload(artifact, origin["producer"], prior, token,
            destination=archive, limit=product_reuse._ios_upload_zip_limits("validation")["max_archive_bytes"],
            artifact_sha256=origin["artifactSha256"], size=artifact["size_in_bytes"])
    zipped, _, identity = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
        **product_reuse._ios_upload_zip_limits("validation"))
    if identity != {"bytes": artifact["size_in_bytes"], "sha256": origin["artifactSha256"]}:
        raise ValueError("Apple validation recovery archive differs from its authenticated original")
    names = {"selection/impact-plan.json", "selection/phase-plan.json", "selection/producer.json",
        "context/execution-context.json", "worker/execution.json", "worker/gradle.log",
        "originals/completed/package-receipt.json", "originals/completed/completed-package.json",
        "execution/apple-validation-evidence.zip"}
    if {row["relativePath"] for row in zipped
            if not row["relativePath"].startswith("worker-dependency-seed/")} != names:
        raise ValueError("Apple validation recovery original has an unexpected layout")
    with tempfile.TemporaryDirectory(prefix="apple-validation-production-") as temporary:
        original = Path(temporary).resolve() / "original"
        product_reuse._extract_runtime_original_projection(archive,
            [row for row in zipped if row["relativePath"] in names], original)
        before = regular_file_inventory(original, allow_empty=True)

        def unchanged():
            if (sha256_file(archive) != origin["artifactSha256"]
                    or regular_file_inventory(original, allow_empty=True) != before
                    or canonical_json_bytes(origin) != origin_bytes or canonical_json_bytes(phase) != phase_bytes):
                raise ValueError("Apple validation recovery originals changed during replay")

        try:
            producer = origin["producer"]
            selected = product_reuse._validate_plan(original / "selection/impact-plan.json",
                repository_root, expected_revision=producer["commit"])
            observed = product_reuse._consumer(selected,
                {"GITHUB_RUN_ID": str(producer["runId"]), "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"]
            if (selected["remoteBuildAuthorized"] is not True or selected["event"] != "pull_request"
                    or observed != producer or _json(original / "selection/producer.json") != producer
                    or canonical_json_bytes(_json(original / "selection/phase-plan.json")) != phase_bytes):
                raise ValueError("Apple validation recovery changes original source, selection or inputs")
            for name in ("completed-package.json", "package-receipt.json"):
                if read_regular_file_bytes(original / "originals/completed" / name, max_bytes=_LIMIT,
                        reject_symlink_parents=True) != read_regular_file_bytes(
                        package["completedCapture"] / name, max_bytes=_LIMIT, reject_symlink_parents=True):
                    raise ValueError("Apple validation recovery differs from the authenticated predecessor closure")
            evidence = original / "execution/apple-validation-evidence.zip"
            context = verify_apple_validation_context(original / "context/execution-context.json",
                producer=producer, target=phase["target"], evidence_archive=evidence)
            if any(context[name] != package[name] for name in ("packageArtifact", "binaryArtifact")):
                raise ValueError("Apple validation recovery changes original predecessor locators")
            # This is a selector for existing process/source checks, never a receipt.
            execution_identity = {**phase, "producer": producer, "productVersion": package["receipt"]["productVersion"]}
            contract = _json(package["original"] / "inputs/contract-contract-binary-common/phase-receipt.json")
            _worker(original, execution_identity, context, contract["productVersion"])
            instance = PhaseInstanceId("sdk", "sdk-ios", "validation", phase["target"])
            _replan(repository_root, instance, execution_identity, package["receipt"])
            _replan(repository_root, instance, {**execution_identity, "producer": consumer}, package["receipt"])
            unchanged()
            yield {"original": original, "context": context, "evidenceArchive": evidence,
                   "producer": producer}
        finally:
            unchanged()


def prepare_ios_validation_signing_inputs(plan, validation_receipt_path, destination, *,
        target, expected_receipt_sha256, artifact_id, artifact_sha256, trusted_workflow_sha,
        keyring, keys_directory, repository_root, environ, token,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None, retained_sdk_inputs_source=None, completed_frozen=None):
    """Preserve fully replayed originals on a non-secret runner, without signing.

    This unsigned preparation is not authority. A protected consumer must
    independently authenticate its fixed preparation job/upload and original
    validation upload before issuing a detached signature over these exact bytes.
    """
    require_no_signing_secret(environ)
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple preparation requires an exact validation target")
    require_sha256(expected_receipt_sha256, "Selected Apple validation receipt")
    require_integer(artifact_id, "Original Apple validation artifact ID", 1)
    require_sha256(artifact_sha256, "Original Apple validation artifact digest")
    if required_trust_domain != "release" or tooling_keyring is None or tooling_keys_directory is None:
        raise ValueError("Apple signing preparation requires release-trust replay tooling")
    plan, receipt_path, output = Path(plan), Path(validation_receipt_path), Path(destination).absolute()
    inputs = [Path(value) for value in (plan, receipt_path, repository_root, keyring, keys_directory,
        tooling_evidence, tooling_public_key, java_executable, tooling_keyring, tooling_keys_directory)]

    def output_safe():
        _require_capability_output_separate(output, inputs)
        if output.exists() or output.is_symlink():
            raise ValueError("Apple preparation destination must not exist")
        for ancestor in output.parents:
            if ancestor.exists() or ancestor.is_symlink():
                require_regular_directory(ancestor, "Apple preparation output ancestry")

    output_safe()
    raw = read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    plan_bytes = read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True)
    if (sha256_bytes(raw) != expected_receipt_sha256
            or (receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) !=
               ("sdk", "sdk-ios", "validation", target)):
        raise ValueError("Apple preparation differs from selected validation receipt")

    def unchanged():
        require_no_signing_secret(environ)
        if (read_regular_file_bytes(receipt_path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                or read_regular_file_bytes(plan, max_bytes=_LIMIT, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("Apple preparation selected inputs changed during use")

    with tempfile.TemporaryDirectory(prefix="apple-signing-preparation-") as temporary:
        prepared = Path(temporary).resolve() / "prepared"
        captured = prepared / "capture"
        with verified_original_ios_validation(plan, receipt_path, artifact_id=artifact_id,
                artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                keyring=keyring, keys_directory=keys_directory, repository_root=repository_root,
                environ=environ, token=token, tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, java_executable=java_executable,
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
                **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
                   if retained_sdk_inputs_source is not None else {}),
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as verified:
            unchanged()
            if verified["receiptBytes"] != raw or canonical_json_bytes(verified["receipt"]) != raw:
                raise ValueError("Apple preparation replay returned a different original receipt")
            inventory = _input_inventory(verified["capture"], allow_empty=True)
            snapshot_regular_tree(verified["capture"], captured, allow_empty=True)
            if (_input_inventory(captured, allow_empty=True) != inventory
                    or _input_inventory(verified["capture"], allow_empty=True) != inventory
                    or read_regular_file_bytes(captured / "original/shard/phase-receipt.json",
                        max_bytes=_LIMIT, reject_symlink_parents=True) != raw):
                raise ValueError("Apple preparation changed the original validation capture")
        # Publish only after every original-reader context-exit check succeeds.
        unchanged()
        if _input_inventory(captured, allow_empty=True) != inventory:
            raise ValueError("Apple preparation capture changed after replay")
        record = {"schemaVersion": 1, "target": target, "receiptSha256": expected_receipt_sha256,
            "captureDigest": sha256_bytes(canonical_json_bytes(inventory)),
            "planSha256": sha256_bytes(plan_bytes), "producer": receipt["producer"],
            "originalArtifact": {"artifactId": artifact_id, "artifactSha256": artifact_sha256}}
        write_canonical_json(prepared / "preparation.json", record)
        unchanged()
        if _input_inventory(captured, allow_empty=True) != inventory:
            raise ValueError("Apple preparation capture changed before publication")
        output_safe()
        publish_regular_tree(prepared, output, allow_empty=True)
    return record


def _json(path):
    return load_canonical_json_bytes(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True))


def _replan(root, instance, receipt, package):
    commit, tree = receipt["producer"]["commit"], receipt["producer"]["tree"]
    try:
        if (run_git(root, "rev-parse", f"{commit}^{{commit}}").strip() != commit
                or run_git(root, "rev-parse", f"{commit}^{{tree}}").strip() != tree):
            raise ValueError("Original Apple validation source differs from its producer")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original Apple validation source is unavailable") from error
    versions = git_product_versions(root, commit)
    if versions["sdk"] != receipt["productVersion"]:
        raise ValueError("Original Apple validation version differs from its Git source")
    expected = plan_phase(instance, inventory=phase_git_inventory(root, commit, instance), versions=versions,
        upstream_receipts=[package], toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1)
    if receipt["inputs"] != expected["inputs"] or receipt["buildKey"] != expected["buildKey"]:
        raise ValueError("Original Apple validation inputs/build key differ from its authenticated original plan")


def _worker(original, receipt, context, contract_version):
    """Check the existing fixed process record, not infer source authority from argv."""
    record = require_exact_keys(_json(original / "worker/execution.json"),
        {"schemaVersion", "producer", "buildKey", "command", "returnCode", "launchError", "elapsedNs"},
        "Original Apple validation worker")
    if (require_integer(record["schemaVersion"], "Worker schema", 1) != 1
            or canonical_json_bytes(record["producer"]) != canonical_json_bytes(receipt["producer"])
            or record["buildKey"] != receipt["buildKey"]
            or type(record["returnCode"]) is not int or record["returnCode"] != 0
            or record["launchError"] is not None):
        raise ValueError("Original Apple validation worker differs from its successful producer")
    require_integer(record["elapsedNs"], "Worker elapsed time", 0)
    command = require_array(record["command"], "Original Apple validation command")
    if any(type(value) is not str for value in command):
        raise ValueError("Original Apple validation command must contain strings")
    fields = {}
    for argument in command[8:]:
        if not argument.startswith("-P") or "=" not in argument:
            raise ValueError("Original Apple validation command has an unexpected argument")
        name, value = argument[2:].split("=", 1)
        if name in fields:
            raise ValueError("Original Apple validation command repeats a property")
        fields[name] = value
    expected = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-ios", "codexAgent.phase": "validation",
        "codexAgent.target": receipt["target"], "codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.contractVersion": contract_version, "codexAgent.candidateTree": receipt["producer"]["tree"],
        "codexAgent.candidateCommit": receipt["producer"]["commit"],
    }
    paths = {"codexAgent.iosValidationPackageStage", "codexAgent.contractBinaryStage",
             "codexAgent.sdkCompatibilityFile", "codexAgent.iosValidationTestApplicationDirectory",
             "codexAgent.iosValidationCompilerConsumersDirectory"}
    require_exact_keys(fields, set(expected) | paths, "Original Apple validation command properties")
    if any(fields[name] != value for name, value in expected.items()):
        raise ValueError("Original Apple validation command differs from its selected identity")
    for name in paths:
        _original_directory(fields[name], "Original Apple validation input path")
    wrapper = Path(context["originalWorkingDirectory"]).parent / "gradlew"
    if command != product_reuse._runtime_worker_command(wrapper, fields, {}, build_directory="."):
        raise ValueError("Original Apple validation did not run the fixed root product command")
    read_regular_file_bytes(original / "worker/gradle.log", max_bytes=512 * 1024 * 1024,
                            reject_symlink_parents=True)


@contextmanager
def verified_original_ios_validation(plan, validation_receipt_path, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token,
        tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
        tooling_keyring=None, tooling_keys_directory=None, retained_sdk_inputs_source=None, completed_frozen=None):
    with _verified_ios_validation(plan, validation_receipt_path, validation_capture=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root, environ=environ, token=token,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
            **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
               if retained_sdk_inputs_source is not None else {}),
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as value:
        yield value


@contextmanager
def verified_retained_ios_validation(plan, validation_receipt_path, *, validation_capture,
        keyring, keys_directory, repository_root, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
        retained_sdk_inputs_source=None, completed_frozen=None):
    """Replay complete retained content; caller authenticates its enclosing carrier.

    This never turns recorded observations into transport authority or rewrites
    producer evidence. Legacy captures replay their package/native history.
    Compact captures require independent native completion and exact consumed
    objects. Both paths retain the same complete new validation gate.
    """
    with _verified_ios_validation(plan, validation_receipt_path, validation_capture=Path(validation_capture),
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
            **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
               if retained_sdk_inputs_source is not None else {}),
            **({"completed_frozen": completed_frozen} if completed_frozen is not None else {})) as value:
        yield value


@contextmanager
def _verified_ios_validation(plan, validation_receipt_path, *, validation_capture,
        keyring, keys_directory, repository_root, tooling_evidence, tooling_public_key,
        java_executable, policy_revision, required_trust_domain, tooling_keyring=None, tooling_keys_directory=None,
        artifact_id=None, artifact_sha256=None, trusted_workflow_sha=None, environ=None, token=None,
        retained_sdk_inputs_source=None, completed_frozen=None):
    """Yield privately restored originals only inside all authenticated input lifetimes."""
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path = Path(plan), Path(validation_receipt_path)
    files = {"plan": plan, "receipt": receipt_path, "keyring": Path(keyring),
             "tooling-public-key": Path(tooling_public_key), "java": Path(java_executable)}
    if tooling_keyring is not None:
        files["tooling-keyring"] = Path(tooling_keyring)
    directories = {"keys": Path(keys_directory), "tooling": Path(tooling_evidence)}
    if validation_capture is not None:
        directories["retained-validation"] = validation_capture
    if tooling_keys_directory is not None:
        directories["tooling-keys"] = Path(tooling_keys_directory)
    before_files = {name: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                                                  reject_symlink_parents=True) for name, path in files.items()}
    before_dirs = {name: _input_inventory(path, allow_empty=True) for name, path in directories.items()}
    raw = before_files["receipt"]
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    target = receipt["target"]
    if ((receipt["product"], receipt["component"], receipt["phase"]) != ("sdk", "sdk-ios", "validation")
            or target not in ("ios-arm64", "ios-simulator-arm64")):
        raise ValueError("Original Apple validation requires an exact target validation receipt")
    producer = receipt["producer"]
    captured = {}

    def unchanged():
        if (canonical_json_bytes(receipt) != raw
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) != before_files[name] for name, path in files.items())
                or any(_input_inventory(path, allow_empty=True) != before_dirs[name]
                       for name, path in directories.items())
                or any(_input_inventory(path, allow_empty=True) != inventory for path, inventory in captured.items())):
            raise ValueError("Original Apple validation inputs changed during recovery")

    with tempfile.TemporaryDirectory(prefix="original-ios-validation-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *files.values(), *directories.values()])
        selected_receipt = private / "validation-receipt.json"
        selected_receipt.write_bytes(raw)
        try:
            capture = private / "capture"
            if validation_capture is None:
                product_reuse.capture_sdk_ios_validation_upload(plan, capture, validation_receipt_path=selected_receipt,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=root, environ=environ, token=token)
            else:
                snapshot_regular_tree(validation_capture, capture, allow_empty=True)
                if _input_inventory(capture, allow_empty=True) != before_dirs["retained-validation"]:
                    raise ValueError("Retained Apple validation changed during private capture")
                product_reuse.verify_retained_sdk_ios_upload(capture, raw)
                if _input_inventory(capture, allow_empty=True) != before_dirs["retained-validation"]:
                    raise ValueError("Retained Apple validation changed during archive verification")
            captured[capture] = _input_inventory(capture, allow_empty=True)
            original = capture / "original"
            compact = (original / "originals/completed").exists()
            recovery = (original / "recovery").exists()
            if compact and completed_frozen is None:
                raise ValueError("Compact Apple validation requires independently authenticated native completion")
            if recovery and not compact:
                raise ValueError("Recovered Apple validation requires its native predecessor closure")
            layouts = {
                original: ({"selection", "originals", "recovery", "shard"} if recovery else
                           {"selection", "originals", "worker", "execution", "context", "shard"}),
                original / "selection": {"impact-plan.json", "phase-plan.json", "producer.json"},
                original / "originals": {"completed"} if compact else {"package", "sdk", "binary", "native"},
                **({original / "recovery": {"origin.json", "production-worker.zip", "replay.json"}} if recovery else {
                    original / "worker": {"execution.json", "gradle.log"},
                    original / "execution": {"apple-validation-evidence.zip"},
                    original / "context": {"execution-context.json"}}),
            }
            for directory, names in layouts.items():
                require_regular_directory(directory, "Original Apple validation directory")
                if {path.name for path in directory.iterdir()} != names:
                    raise ValueError("Original Apple validation upload has an unexpected layout")
            instance = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
            shard = verify_phase_shard(original / "shard", instance)
            stage = private / "stage"
            restored = restore_object(original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
            if shard["receiptBytes"] != raw or restored["receiptBytes"] != raw:
                raise ValueError("Original Apple validation shard differs from the selected receipt")
            captured[stage] = _input_inventory(stage, allow_empty=False)
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-ios", "validation", target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Original Apple validation stage differs from its receipt")
            selection = original / "selection"
            validated = product_reuse._validate_plan(selection / "impact-plan.json", root,
                                                     expected_revision=producer["commit"])
            if validated["remoteBuildAuthorized"] is not True or validated["event"] == "workflow_dispatch":
                raise ValueError("Original Apple validation impact plan is not authorized")
            observed = product_reuse._consumer(validated, {"GITHUB_RUN_ID": str(producer["runId"]),
                                                         "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"]
            if (canonical_json_bytes(observed) != canonical_json_bytes(producer)
                    or canonical_json_bytes(_json(selection / "producer.json")) != canonical_json_bytes(producer)
                    or canonical_json_bytes(_json(selection / "phase-plan.json")) !=
                       canonical_json_bytes({name: receipt[name] for name in PHASE_PLAN_KEYS})):
                raise ValueError("Original Apple validation selection differs from its producer or receipt")
            archive = original / "execution/apple-validation-evidence.zip"
            context = (None if recovery else verify_apple_validation_context(original / "context/execution-context.json",
                producer=producer, target=target, evidence_archive=archive))
            tooling = dict(tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)

            def compare_capture(name, recovered):
                retained = original / "originals" / name
                if (sha256_file(retained / "transport.zip") != sha256_file(Path(recovered) / "transport.zip")
                        or _input_inventory(retained / "original", allow_empty=True) !=
                           _input_inventory(Path(recovered) / "original", allow_empty=True)):
                    raise ValueError(f"Recovered Apple {name} originals differ from the validation capture")

            with ExitStack() as stack:
                if compact:
                    package_path = original / "originals/completed/package-receipt.json"
                    package_bytes = read_regular_file_bytes(package_path, max_bytes=_LIMIT, reject_symlink_parents=True)
                    package = stack.enter_context(verified_completed_ios_package(plan, package_path,
                        completed_frozen=completed_frozen, repository_root=root,
                        environ=os.environ if environ is None else environ,
                        token=os.environ.get("GITHUB_TOKEN", "") if token is None else token,
                        trusted_workflow_sha=trusted_workflow_sha, retained=original / "originals/completed"))
                    if not recovery and any(package[name] != context[name] for name in ("packageArtifact", "binaryArtifact")):
                        raise ValueError("Compact Apple validation changes its native predecessor locators")
                else:
                    package_path = original / "originals/package/original/shard/phase-receipt.json"
                    package_bytes = read_regular_file_bytes(package_path, max_bytes=_LIMIT, reject_symlink_parents=True)
                    if validation_capture is not None:
                        for name in ("package", "binary"):
                            artifact = _json(original / "originals" / name / "capture-transport.json")["artifact"]
                            locator = context[f"{name}Artifact"]
                            if (artifact.get("id"), artifact.get("digest")) != (locator["artifactId"], locator["artifactSha256"]):
                                raise ValueError("Retained Apple predecessor differs from its original validation locator")
                    package_context = (verified_original_ios_package(plan, package_path,
                            artifact_id=context["packageArtifact"]["artifactId"],
                            artifact_sha256=context["packageArtifact"]["artifactSha256"],
                            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring, keys_directory=keys_directory,
                            repository_root=root, environ=environ, token=token, **tooling,
                            **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
                               if retained_sdk_inputs_source is not None else {})) if validation_capture is None else
                        verified_retained_ios_package(plan, package_path,
                            package_capture=original / "originals/package", sdk_capture=original / "originals/sdk",
                            keyring=keyring, keys_directory=keys_directory, repository_root=root, **tooling,
                            **({"retained_sdk_inputs_source": retained_sdk_inputs_source}
                               if retained_sdk_inputs_source is not None else {})))
                    package = stack.enter_context(package_context)
                    if (package["receiptBytes"] != package_bytes or canonical_json_bytes(package["receipt"]) != package_bytes
                            or package["receipt"]["productVersion"] != receipt["productVersion"]):
                        raise ValueError("Original Apple validation differs from its exact package predecessor")
                    compare_capture("package", package["packageCapture"])
                    compare_capture("sdk", package["sdkCapture"])
                    binary = package["original"] / "inputs/sdk-sdk-ios-binary-ios"
                    binary_receipt = binary / "phase-receipt.json"
                    binary_bytes = read_regular_file_bytes(binary_receipt, max_bytes=_LIMIT, reject_symlink_parents=True)
                    binary_context = (verified_original_ios_binary(plan, binary_receipt,
                            artifact_id=context["binaryArtifact"]["artifactId"],
                            artifact_sha256=context["binaryArtifact"]["artifactSha256"],
                            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, environ=environ, token=token,
                            rust_host=context["rustHost"], **tooling) if validation_capture is None else
                        verified_retained_ios_binary(plan, binary_receipt, binary_capture=original / "originals/binary",
                            repository_root=root, rust_host=context["rustHost"], **tooling))
                    binary_inputs = stack.enter_context(binary_context)
                    if (binary_inputs["receiptBytes"] != binary_bytes
                            or regular_file_inventory(binary_inputs["stage"]) != regular_file_inventory(binary / "stage")):
                        raise ValueError("Original Apple binary differs from the package predecessor")
                    compare_capture("binary", binary_inputs["binaryCapture"])
                    retained_native = original / "originals/native"
                    native = binary_inputs["native"]["captureRoot"]
                    for subtree in ("archives", "lanes", "native-evidence", "plan"):
                        if _input_inventory(retained_native / subtree, allow_empty=True) != _input_inventory(native / subtree, allow_empty=True):
                            raise ValueError("Recovered native originals differ from the validation capture")
                    if _json(retained_native / "native-transport.json")["receiptSha256s"] != binary_inputs["native"]["transport"]["receiptSha256s"]:
                        raise ValueError("Recovered native receipts differ from the validation capture")
                if (package["receiptBytes"] != package_bytes or canonical_json_bytes(package["receipt"]) != package_bytes
                        or package["receipt"]["productVersion"] != receipt["productVersion"]):
                    raise ValueError("Original Apple validation differs from its exact package predecessor")
                contract = package["original"] / "inputs/contract-contract-binary-common"
                contract_receipt = validate_phase_receipt(_json(contract / "phase-receipt.json"))
                execution_producer = producer
                if recovery:
                    origin = _json(original / "recovery/origin.json")
                    expected_replay = {"schemaVersion": 1, "producer": producer, "buildKey": receipt["buildKey"],
                        "originSha256": sha256_bytes(canonical_json_bytes(origin))}
                    if canonical_json_bytes(_json(original / "recovery/replay.json")) != canonical_json_bytes(expected_replay):
                        raise ValueError("Apple validation recovery record differs from its actual verification producer")
                    recovered = stack.enter_context(verified_validation_recovery(validated, producer,
                        {name: receipt[name] for name in PHASE_PLAN_KEYS}, origin,
                        original / "recovery/production-worker.zip", package=package, repository_root=root,
                        token=os.environ.get("GITHUB_TOKEN", "") if token is None else token))
                    archive, context = recovered["evidenceArchive"], recovered["context"]
                    execution_producer = recovered["producer"]
                else:
                    _worker(original, receipt, context, contract_receipt["productVersion"])
                _replan(root, instance, receipt, package["receipt"])
                context_bytes = canonical_json_bytes(context)
                unchanged()
                verify_apple_validation_stage(validation_stage=stage, target=target,
                    sdk_version=receipt["productVersion"], package_stage=package["stage"],
                    package_receipt=package["receipt"], sdk_compatibility=package["sdk"]["directory"] / "sdk-compatibility.json",
                    contract_digest=package["sdk"]["compatibility"]["contract"]["digest"],
                    canonical_api=contract / "stage/outputs/evidence/canonical-api.json",
                    canonical_coverage=contract / "stage/outputs/evidence/canonical-coverage.json",
                    evidence_archive=archive, context=context, repository=root, source_revision=execution_producer["commit"], **tooling)
                unchanged()
                if canonical_json_bytes(context) != context_bytes:
                    raise ValueError("Original Apple validation context changed during replay")
                yield {"stage": stage, "receiptPath": selected_receipt, "receiptBytes": raw,
                       "receipt": receipt, "original": original, "capture": capture,
                       "package": package}
        finally:
            unchanged()
            if read_regular_file_bytes(selected_receipt) != raw:
                raise ValueError("Selected original Apple validation receipt changed during recovery")
