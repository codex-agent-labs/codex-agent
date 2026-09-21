"""Join an observed original Core upload to complete semantic/source/key replay.

Returned private paths live only inside the context. Official job/runner labels
bind the original upload, not hardware or compiler identity. Caller-owned package,
Contract and tooling policy remains mandatory; uploaded request/context records
cannot choose trust. No receipt is minted and no opaque host token is returned.
"""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_array, require_exact_keys, require_integer, require_regular_directory, sha256_bytes,
    snapshot_regular_tree,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_facade_inputs import _request, _sources
from products.sdk_facade_source import capture_facade_validation_sources
from products.sdk_facade_execution_observation import verify_facade_execution_observation
from products.sdk_facade_validation import _inventory, _original_path
from products.sdk_facade_validation_admission import _context, verify_sdk_facade_validation_original_content
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signing_isolation import require_no_signing_secret
from sdk_facade_capture import capture_sdk_facade_validation_upload, verify_retained_sdk_phase_upload
from sdk_phase import route


_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)


def _json(path):
    return load_canonical_json_bytes(_read(path))


def _execution_context(original, receipt, caller_request):
    context = require_exact_keys(_json(original / "context/execution-context.json"),
        {"schemaVersion", "target", "buildKey", "producer", "originalContext", "workerDirectory"},
        "Original Core execution context")
    if (require_integer(context["schemaVersion"], "Original Core context schema", 1) != 1
            or context["target"] != receipt["target"] or context["buildKey"] != receipt["buildKey"]
            or canonical_json_bytes(context["producer"]) != canonical_json_bytes(receipt["producer"])):
        raise ValueError("Original Core context differs from its selected receipt")
    process, _, original_root, _ = _context(context["originalContext"], receipt)
    windows = route(receipt)["runnerOs"] == "Windows"
    if bool(PureWindowsPath(original_root).drive) != windows:
        raise ValueError("Original Core path platform differs from its fixed target route")
    path_type = PureWindowsPath if windows else PurePosixPath
    root = path_type(original_root)
    worker = path_type(_original_path(context["workerDirectory"], "Original Core worker directory"))
    if root not in worker.parents:
        raise ValueError("Original Core worker directory must remain under its original checkout")
    work = root / "build/imported-sdk-facade-validation" / receipt["producer"]["tree"] / receipt["target"]
    stage = root / "build/product-stage/sdk/sdk-core/validation" / receipt["target"]
    if any(worker == output or worker in output.parents or output in worker.parents for output in (work, stage)):
        raise ValueError("Original Core worker directory overlaps its task-owned outputs")
    retained_request = require_exact_keys(_json(original / "worker/facade-request.json"),
                                         set(caller_request), "Original Core retained request")
    if (any(retained_request[name] != caller_request[name] for name in
            ("target", "sdkVersion", "runtimeVersion", "contractVersion"))
            or retained_request["repository"] != original_root):
        raise ValueError("Original Core request identity differs from authenticated caller inputs")
    record = require_exact_keys(_json(original / "worker/execution.json"),
        {"schemaVersion", "producer", "buildKey", "command", "returnCode", "launchError", "elapsedNs"},
        "Original Core worker execution")
    if (require_integer(record["schemaVersion"], "Core worker schema", 1) != 1
            or canonical_json_bytes(record["producer"]) != canonical_json_bytes(receipt["producer"])
            or record["buildKey"] != receipt["buildKey"]
            or require_integer(record["returnCode"], "Core worker exit code", 0) != 0
            or record["launchError"] is not None):
        raise ValueError("Original Core worker did not succeed for its exact receipt")
    require_integer(record["elapsedNs"], "Core worker elapsed time", 0)
    command = require_array(record["command"], "Original Core command")
    if any(type(argument) is not str for argument in command):
        raise ValueError("Original Core worker command must contain only strings")
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-core", "codexAgent.phase": "validation",
        "codexAgent.target": receipt["target"], "codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.candidateCommit": receipt["producer"]["commit"],
        "codexAgent.candidateTree": receipt["producer"]["tree"],
        "codexAgent.sdkFacadeValidationRequest": str(worker / "facade-request.json"),
    }
    environment = {}
    if windows:
        java = PureWindowsPath(process["javaExecutable"])
        if java.parent.name != "bin":
            raise ValueError("Original Core Java launcher must match JAVA_HOME/bin/java.exe")
        environment["JAVA_HOME"] = str(java.parent.parent)
    expected = product_reuse._runtime_worker_command(process["gradleWrapper"], fields, environment,
        build_directory=".", platform_name="nt" if windows else "posix")
    if command != expected:
        raise ValueError("Original Core worker differs from the exact fixed root command")
    read_regular_file_bytes(original / "worker/gradle.log", max_bytes=512 * 1024 * 1024,
                            reject_symlink_parents=True)
    return context["originalContext"]


@contextmanager
def verified_original_sdk_facade_validation(
    plan, validation_receipt_path, *, artifact_id, artifact_sha256, trusted_workflow_sha,
    facade_request, repository_root, environ, token, tooling_evidence, tooling_public_key,
    java_executable, policy_revision, required_trust_domain,
    tooling_keyring=None, tooling_keys_directory=None,
):
    """Hold the selected observed upload and all original inputs through use.

    The current plan authorizes capture; the retained original impact plan is
    independently validated at its receipt commit. Caller facade_request supplies
    authenticated current replay paths/policy, never retained original paths.
    """
    with _verified_sdk_facade_validation(plan, validation_receipt_path, capture_root=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            facade_request=facade_request, repository_root=repository_root, environ=environ, token=token,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as result:
        yield result


@contextmanager
def verified_retained_sdk_facade_validation(
    plan, validation_receipt_path, *, capture_root, facade_request, repository_root, environ,
    tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
    tooling_keyring=None, tooling_keys_directory=None,
):
    """Replay a complete caller-authenticated retained capture without network.

    The caller must independently authenticate the enclosing carrier. Stored
    transport observations are consistency records, not fresh official proof.
    Current caller facade_request/tooling policy remains mandatory and is never
    recovered from the capture. All live-reader semantic/source gates are shared.
    """
    with _verified_sdk_facade_validation(plan, validation_receipt_path, capture_root=Path(capture_root),
            facade_request=facade_request, repository_root=repository_root, environ=environ,
            tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision,
            required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory) as result:
        yield result


@contextmanager
def _verified_sdk_facade_validation(
    plan, validation_receipt_path, *, capture_root, facade_request, repository_root, environ,
    tooling_evidence, tooling_public_key, java_executable, policy_revision, required_trust_domain,
    tooling_keyring, tooling_keys_directory, artifact_id=None, artifact_sha256=None,
    trusted_workflow_sha=None, token=None,
):
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, receipt_path, request_path = map(Path, (plan, validation_receipt_path, facade_request))
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if ((receipt["product"], receipt["component"], receipt["phase"]) != ("sdk", "sdk-core", "validation")
            or receipt["target"] not in SDK_FACADE_TARGETS):
        raise ValueError("Original Core validation requires its exact selected receipt")
    value, request_bytes = _request(request_path)
    if (value["target"] != receipt["target"] or value["sdkVersion"] != receipt["productVersion"]
            or Path(value["repository"]) != root):
        raise ValueError("Core caller request differs from the selected validation identity")
    _, trees, files = _sources(value)
    if capture_root is not None:
        trees["retainedCapture"] = capture_root
    trees["tooling"] = Path(tooling_evidence)
    files.update({"plan": plan, "receipt": receipt_path, "request": request_path,
                  "toolingPublicKey": Path(tooling_public_key), "java": Path(java_executable)})
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring)
    if tooling_keys_directory is not None:
        trees["toolingKeysDirectory"] = Path(tooling_keys_directory)
    before_trees = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    before_files = {name: read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
        reject_symlink_parents=True) for name, path in files.items()}
    compatibility = _request_inventory(Path(value["compatibilityRequest"]))
    captured = {}
    result = result_bytes = transport = transport_bytes = None

    def view(record):
        return canonical_json_bytes({key: str(member) if isinstance(member, Path) else
            member.hex() if isinstance(member, bytes) else member for key, member in record.items()})

    def unchanged():
        require_no_signing_secret(environ)
        if (_read(receipt_path) != raw or canonical_json_bytes(receipt) != raw or _read(request_path) != request_bytes
                or any(_inventory(path, allow_empty=True) != before_trees[name] for name, path in trees.items())
                or any(read_regular_file_bytes(path, max_bytes=128 * 1024 * 1024,
                    reject_symlink_parents=True) != before_files[name] for name, path in files.items())
                or _request_inventory(Path(value["compatibilityRequest"])) != compatibility
                or any(_inventory(path, allow_empty=True) != inventory for path, inventory in captured.items())
                or (transport is not None and canonical_json_bytes(transport) != transport_bytes)
                or (result is not None and view(result) != result_bytes)):
            raise ValueError("Original Core validation inputs changed during recovery")

    with tempfile.TemporaryDirectory(prefix="original-core-validation-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *trees.values(), *files.values(), *compatibility])
        selected = private / "selected-receipt.json"
        selected.write_bytes(raw)
        try:
            unchanged()
            capture = private / "capture"
            if capture_root is None:
                transport = capture_sdk_facade_validation_upload(plan, capture, validation_receipt_path=selected,
                    artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=root, environ=environ, token=token)
            else:
                snapshot_regular_tree(capture_root, capture, allow_empty=True)
                if _inventory(capture, allow_empty=True) != before_trees["retainedCapture"]:
                    raise ValueError("Original Core retained capture changed during snapshot")
                verify_retained_sdk_phase_upload(capture, raw)
                transport = _json(capture / "capture-transport.json")
            transport_bytes = canonical_json_bytes(transport)
            if (transport["validationReceiptSha256"] != sha256_bytes(raw)
                    or canonical_json_bytes(transport["captureProducer"]) != canonical_json_bytes(receipt["producer"])
                    or _read(capture / "capture-transport.json") != transport_bytes):
                raise ValueError("Core observed capture differs from the selected original receipt")
            captured[capture] = _inventory(capture, allow_empty=True)
            original = capture / "original"
            layouts = {
                original: {"shard", "worker", "selection", "context", "retained-execution", "inputs", "originals"},
                original / "worker": {"execution.json", "gradle.log", "facade-request.json", "source", "host-observation"},
                original / "selection": {"impact-plan.json", "phase-plan.json", "producer.json"},
                original / "context": {"execution-context.json"},
                original / "retained-execution": {"inputs", "consumer", "consumer-inputs", "execution",
                                                     "publication-metadata.json", "report.json", "compiler-inputs.json"},
            }
            for directory, names in layouts.items():
                require_regular_directory(directory, "Original Core retained directory")
                if {path.name for path in directory.iterdir()} != names:
                    raise ValueError("Original Core upload has an unexpected retained layout")
            for name in layouts[original]:
                require_regular_directory(original / name, "Original Core retained root")
            instance = PhaseInstanceId("sdk", "sdk-core", "validation", receipt["target"])
            shard = verify_phase_shard(original / "shard", instance)
            stage = private / "stage"
            restored = restore_object(original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
            if shard["receiptBytes"] != raw or restored["receiptBytes"] != raw:
                raise ValueError("Original Core upload differs from its selected receipt")
            manifest = verify_output_manifest_identity(stage, "sdk", "sdk-core", "validation",
                                                       receipt["target"], receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Original Core stage differs from its exact receipt")
            captured[stage] = _inventory(stage)
            selection = original / "selection"
            producer = receipt["producer"]
            validated = product_reuse._validate_plan(selection / "impact-plan.json", root,
                                                     expected_revision=producer["commit"])
            if validated["remoteBuildAuthorized"] is not True or validated["event"] not in {"pull_request", "merge_group"}:
                raise ValueError("Original Core impact plan is not authorized")
            observed = product_reuse._consumer(validated, {"GITHUB_RUN_ID": str(producer["runId"]),
                                                         "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])})["producer"]
            if (canonical_json_bytes(observed) != canonical_json_bytes(producer)
                    or canonical_json_bytes(_json(selection / "producer.json")) != canonical_json_bytes(producer)
                    or canonical_json_bytes(_json(selection / "phase-plan.json")) !=
                       canonical_json_bytes({name: receipt[name] for name in PHASE_PLAN_KEYS})):
                raise ValueError("Original Core selection differs from its receipt and producer")
            context = _execution_context(original, receipt, value)
            verify_facade_execution_observation(original / "worker/host-observation",
                repository=root, producer=producer, target=receipt["target"],
                original_repository_root=context["repositoryRoot"],
                original_java_executable=context.get("javaExecutable"))
            source = private / "immutable-source"
            source_record = capture_facade_validation_sources(root, producer["commit"], source)
            if (source_record["tree"] != producer["tree"] or _inventory(source) != source_record["files"]
                    or _inventory(original / "worker/source") != source_record["files"]):
                raise ValueError("Original Core retained source differs from immutable Git")
            captured[source] = source_record["files"]
            work = original / "retained-execution"
            verified, verified_bytes = verify_sdk_facade_validation_original_content(
                repository=root, validation_stage=stage, validation_receipt=selected,
                facade_request=request_path, prepared_inputs=work / "inputs", execution_directory=work / "execution",
                consumer_inputs=work / "consumer-inputs", compiler_inputs=work / "compiler-inputs.json", original_context=context,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            if verified_bytes != raw or canonical_json_bytes(verified) != raw or _read(selected) != raw:
                raise ValueError("Core full replay returned a different original receipt")
            unchanged()
            result = {"stage": stage, "receiptPath": selected, "receiptBytes": raw, "receipt": receipt,
                      "original": original, "capture": capture, "transport": transport}
            result_bytes = view(result)
            yield result
        finally:
            unchanged()
            if _read(selected) != raw:
                raise ValueError("Core selected private receipt changed during recovery")
