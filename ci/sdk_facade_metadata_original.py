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
from sdk_facade_metadata_inputs import _records, _view, _native_archives, verified_facade_metadata_inputs


_INSTANCE = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


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
        _layout(retained, {"stage", "phase-receipt.json"} if target == "package" else {"stage", "phase-receipt.json", "capture"})
        selected = original / "inputs" / ("sdk-sdk-core-package-common" if target == "package" else
                                          f"sdk-sdk-core-validation-{target}")
        for parent in (retained, selected):
            if (_read(parent / "phase-receipt.json") != value["receiptBytes"]
                    or _inventory(parent / "stage") != _inventory(value["stage"])):
                raise ValueError("Original metadata retained predecessor differs from full original replay")
        if target != "package":
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
            _layout(original, {"shard", "worker", "selection", "originals", "inputs"})
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
