"""Hold original Core/Android Maven content, source and signed-input replay.

Observed upload routing is not hardware/compiler admission. Retained mode needs
an independently authenticated enclosing carrier. Original invocation paths and
trust policy come from the caller, never uploaded invocation/keyring records.
The producer did not record cwd: an exact command comparison is not a cwd proof.
"""

from contextlib import contextmanager
from pathlib import Path, PurePosixPath, PureWindowsPath
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, git_regular_blob_bytes,
    load_canonical_json_bytes, read_regular_file_bytes, require_exact_keys,
    require_integer, require_semver, require_sha256, sha256_file, snapshot_regular_tree,
)
from products.plan import _contract_projection_from_request
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, restore_object, verify_phase_shard
from products.sdk_apple_original_inputs import verified_apple_original_inputs
from products.sdk_facade_inputs import _EVIDENCE_FIELDS, _path
from products.sdk_facade_validation import _inventory, _original_path
from products.sdk_inputs import REQUEST_NAME
from products.sdk_maven import verify_sdk_maven_binary_content
from products.sdk_package import _require_capability_output_separate, _verify_plan, verify_sdk_package_inputs
from products.sdk_release_selection import sdk_runtime_source
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties
from sdk_facade_capture import capture_sdk_maven_upload, verify_retained_sdk_phase_upload
from sdk_ios_package import _record


_TARGETS = {"sdk-core": "common", "sdk-android": "android"}
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _json(path):
    return load_canonical_json_bytes(_read(path))


def _layout(path, names):
    _inventory(path, allow_empty=True)
    if {item.name for item in path.iterdir()} != set(names):
        raise ValueError("Original Maven upload has an unexpected layout")


def _context(value, phase):
    require_exact_keys(value, {"repositoryRoot", "workerRoot"} |
                       ({"compatibilityRequest"} if phase == "package" else set()), "Caller Maven original context")
    for name, path in value.items():
        _original_path(path, "Original Maven " + name)
        if PureWindowsPath(path).drive or not PurePosixPath(path).is_absolute():
            raise ValueError("Original Maven context requires normalized POSIX paths")
    if PurePosixPath(value["repositoryRoot"]) not in PurePosixPath(value["workerRoot"]).parents:
        raise ValueError("Original Maven worker must be inside its caller-bound checkout")
    return value


def _predecessor(inputs, product, component, phase, target):
    directory = inputs / "-".join((product, component, phase, target))
    path = directory / "phase-receipt.json"
    return _record({"stage": directory / "stage", "receiptPath": path, "receipt": _json(path)},
                   (product, component, phase, target), "Original Maven predecessor")[0]


def _same_record(record, stage, receipt):
    if (_read(record["receiptPath"]) != _read(receipt) or
            _inventory(record["stage"]) != _inventory(stage)):
        raise ValueError("Original Maven predecessor differs from caller-authenticated input")


def _worker(original, receipt, context, contract_version, archive_name):
    _layout(original / "worker", {"execution.json", "gradle.log"})
    execution = require_exact_keys(_json(original / "worker/execution.json"),
        {"schemaVersion", "producer", "buildKey", "command", "returnCode", "launchError", "elapsedNs"},
        "Original Maven execution")
    if (require_integer(execution["schemaVersion"], "Maven execution schema", 1) != 1
            or execution["producer"] != receipt["producer"] or execution["buildKey"] != receipt["buildKey"]
            or require_integer(execution["returnCode"], "Maven execution exit", 0) != 0
            or execution["launchError"] is not None):
        raise ValueError("Original Maven execution differs from its successful selected phase")
    require_integer(execution["elapsedNs"], "Maven execution elapsed time", 0)
    fields = {"codexAgent." + name: receipt[name] for name in ("product", "component", "phase", "target")}
    fields.update({"codexAgent.sdkVersion": receipt["productVersion"],
        "codexAgent.candidateCommit": receipt["producer"]["commit"],
        "codexAgent.candidateTree": receipt["producer"]["tree"]})
    worker = PurePosixPath(context["workerRoot"])
    if receipt["phase"] == "binary":
        handoff = worker / "inputs/contract-input"
        stem = "codex-agent-contract-" + contract_version
        fields.update({"codexAgent.contractVersion": contract_version,
            "codexAgent.contractMetadataReceipt": str(worker / "inputs/predecessors/contract-contract-metadata-common/phase-receipt.json"),
            "codexAgent.contractPayload": str(handoff / (stem + ".zip")),
            "codexAgent.contractAttestation": str(handoff / (stem + ".attestation.json")),
            "codexAgent.contractAttestationSignature": str(handoff / (stem + ".attestation.sig")),
            "codexAgent.contractPublicKey": str(handoff / "public-key.pub")})
        if archive_name is not None:
            fields["codexAgent.codexArchiveFile"] = str(worker / "android-original" / archive_name)
    else:
        property_name = "sdkCoreBinaryStageRoot" if receipt["component"] == "sdk-core" else "sdkAndroidBinaryStageRoot"
        fields["codexAgent." + property_name] = str(worker / "inputs" /
            f"sdk-{receipt['component']}-binary-{receipt['target']}" / "stage")
        fields["codexAgent.sdkCompatibilityRequest"] = context["compatibilityRequest"]
    expected = product_reuse._runtime_worker_command(PurePosixPath(context["repositoryRoot"]) / "gradlew",
        fields, {}, build_directory=".", platform_name="posix")
    if execution["command"] != expected:
        raise ValueError("Original Maven execution differs from the fixed offline command")


def _contract(original, receipt, evidence):
    """Compare retained originals; only the independent evidence supplies trust."""
    if receipt["phase"] == "binary":
        inputs = original / "inputs/predecessors"
        metadata = _predecessor(inputs, "contract", "contract", "metadata", "common")
        _same_record(metadata, Path(evidence["stageRoot"]), Path(evidence["phaseReceipt"]))
        version = metadata["receipt"]["productVersion"]
        stem = "codex-agent-contract-" + version
        handoff = original / "inputs/contract-input"
        for name, filename in (("attestation", stem + ".attestation.json"),
                               ("attestationSignature", stem + ".attestation.sig"), ("publicKey", "public-key.pub")):
            if _read(handoff / filename) != _read(evidence[name]):
                raise ValueError("Original Maven Contract handoff differs from caller proof")
        bundles = [row for row in metadata["receipt"]["outputs"] if row["kind"] == "contract-bundle"]
        if len(bundles) != 1 or _read(handoff / (stem + ".zip")) != _read(metadata["stage"] / bundles[0]["relativePath"]):
            raise ValueError("Original Maven Contract payload differs from its metadata")
        for phase in ("binary", "package", "validation", "metadata"):
            selected = _predecessor(inputs, "contract", "contract", phase, "common")
            if _read(selected["receiptPath"]) != _read(handoff / "execution-closure/receipts" / (phase + ".json")):
                raise ValueError("Original Maven Contract closure rewrites a predecessor receipt")
    else:
        retained = original / "binary-contract-original"
        invocation = require_exact_keys(_json(retained / "invocation.json"), _EVIDENCE_FIELDS,
                                        "Retained original binary Contract invocation")
        if invocation["expectedTrustDomain"] != evidence["expectedTrustDomain"]:
            raise ValueError("Retained Maven Contract differs from caller trust domain")
        if _inventory(retained / "stage") != _inventory(Path(evidence["stageRoot"])):
            raise ValueError("Retained Maven binary Contract stage differs from caller proof")
        for name in ("phaseReceipt", "attestation", "attestationSignature", "publicKey"):
            _original_path(invocation[name], "Retained Contract path")
            if _read(retained / "evidence" / PurePosixPath(invocation[name]).name) != _read(evidence[name]):
                raise ValueError("Retained Maven binary Contract differs from caller proof")
        handoff = retained / "evidence"
        version = _json(evidence["phaseReceipt"])["productVersion"]
    if _inventory(handoff / "execution-closure", allow_empty=True) != _inventory(
            Path(evidence["attestation"]).parent / "execution-closure", allow_empty=True):
        raise ValueError("Original Maven Contract execution closure differs from caller proof")
    return version


@contextmanager
def verified_original_maven_phase(plan, receipt_path, *, artifact_id, artifact_sha256, trusted_workflow_sha,
        binary_contract_evidence, original_context, repository_root, environ, token,
        keyring=None, keys_directory=None, android_runtime_archive=None):
    with _verified_maven_phase(plan, receipt_path, capture_root=None,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            binary_contract_evidence=binary_contract_evidence, original_context=original_context,
            repository_root=repository_root, environ=environ, token=token,
            keyring=keyring, keys_directory=keys_directory, android_runtime_archive=android_runtime_archive) as result:
        yield result


@contextmanager
def verified_retained_maven_phase(plan, receipt_path, *, capture_root, binary_contract_evidence,
        original_context, repository_root, environ, keyring=None, keys_directory=None, android_runtime_archive=None):
    """Caller authenticates the complete retained carrier; transport JSON cannot."""
    with _verified_maven_phase(plan, receipt_path, capture_root=Path(capture_root),
            binary_contract_evidence=binary_contract_evidence, original_context=original_context,
            repository_root=repository_root, environ=environ, keyring=keyring, keys_directory=keys_directory,
            android_runtime_archive=android_runtime_archive) as result:
        yield result


@contextmanager
def _verified_maven_phase(plan, receipt_path, *, capture_root, binary_contract_evidence, original_context,
        repository_root, environ, keyring, keys_directory, android_runtime_archive,
        artifact_id=None, artifact_sha256=None, trusted_workflow_sha=None, token=None):
    require_no_signing_secret(environ)
    root, plan, receipt_path = Path(repository_root).resolve(strict=True), Path(plan), Path(receipt_path)
    raw = _read(receipt_path)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    component, phase, target = (receipt[name] for name in ("component", "phase", "target"))
    if (receipt["product"] != "sdk" or component not in _TARGETS or target != _TARGETS[component]
            or phase not in ("binary", "package")):
        raise ValueError("Original Maven reader requires Core/Android binary or package")
    if ((phase == "package") != (keyring is not None and keys_directory is not None)
            or (keyring is None) != (keys_directory is None)
            or (android_runtime_archive is not None) != (component == "sdk-android" and phase == "binary")):
        raise ValueError("Original Maven phase requires its exact caller policy and archive inputs")
    context = _context(original_context, phase)
    evidence = require_exact_keys(binary_contract_evidence, _EVIDENCE_FIELDS, "Caller original binary Contract")
    if (evidence["expectedTrustDomain"] not in {"development", "release"}
            or (phase == "binary" and evidence["expectedTrustDomain"] != "release")
            or (evidence["keyring"] is None) != (evidence["keysDirectory"] is None)):
        raise ValueError("Original Maven Contract requires independent exact trust policy")
    trees = {"contractStage": Path(_path(evidence["stageRoot"], "Caller Contract stage")),
        "contractClosure": Path(_path(evidence["attestation"], "Caller Contract attestation")).parent / "execution-closure"}
    files = {"plan": plan, "receipt": receipt_path}
    for name in ("phaseReceipt", "attestation", "attestationSignature", "publicKey", "keyring"):
        if evidence[name] is not None:
            files["contract/" + name] = Path(_path(evidence[name], "Caller Contract " + name))
    if evidence["keysDirectory"] is not None:
        trees["contractKeys"] = Path(_path(evidence["keysDirectory"], "Caller Contract keys"))
    if keyring is not None:
        files["sdkKeyring"], trees["sdkKeys"] = Path(keyring), Path(keys_directory)
    if capture_root is not None:
        trees["capture"] = capture_root
    if android_runtime_archive is not None:
        files["archive"] = Path(android_runtime_archive)
    files_before = {name: _read(path) for name, path in files.items()}
    trees_before = {name: _inventory(path, allow_empty=True) for name, path in trees.items()}
    policy_bytes = canonical_json_bytes({"context": context, "contract": evidence})
    retained, result = {}, None
    result_bytes = None

    def view(value):
        return canonical_json_bytes({name: str(member) if isinstance(member, Path) else
            member.hex() if isinstance(member, bytes) else member for name, member in value.items()})

    def unchanged():
        require_no_signing_secret(environ)
        if (_read(receipt_path) != raw or canonical_json_bytes(receipt) != raw
                or canonical_json_bytes({"context": original_context, "contract": binary_contract_evidence}) != policy_bytes
                or any(_read(path) != files_before[name] for name, path in files.items())
                or any(_inventory(path, allow_empty=True) != trees_before[name] for name, path in trees.items())
                or any(_inventory(path, allow_empty=True) != before for path, before in retained.items())
                or result is not None and view(result) != result_bytes):
            raise ValueError("Original Maven inputs, caller policy or held evidence changed")

    with tempfile.TemporaryDirectory(prefix="original-maven-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, *files.values(), *trees.values()])
        selected = private / "phase-receipt.json"
        selected.write_bytes(raw)
        try:
            unchanged()
            capture = private / "capture"
            if capture_root is None:
                capture_sdk_maven_upload(plan, capture, receipt_path=selected, artifact_id=artifact_id,
                    artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
                    repository_root=root, environ=environ, token=token)
            else:
                snapshot_regular_tree(capture_root, capture, allow_empty=True)
                if _inventory(capture, allow_empty=True) != trees_before["capture"]:
                    raise ValueError("Original Maven capture changed during snapshot")
            verify_retained_sdk_phase_upload(capture, raw)
            retained[capture] = _inventory(capture, allow_empty=True)
            original = capture / "original"
            names = {"inputs", "selection", "worker", "shard"}
            names.update({"sdk-inputs-original", "binary-contract-original"} if phase == "package" else
                         {"android-original"} if component == "sdk-android" else set())
            _layout(original, names)
            instance = PhaseInstanceId("sdk", component, phase, target)
            shard = verify_phase_shard(original / "shard", instance)
            stage = private / "stage"
            restored = restore_object(original / "shard" / shard["objectPath"], stage,
                build_key=shard["buildKey"], receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
            if shard["receiptBytes"] != raw or restored["receiptBytes"] != raw:
                raise ValueError("Original Maven shard differs from selected receipt")
            history = original / "selection/impact-plan.json"
            historical = product_reuse._validate_plan(history, root, expected_revision=receipt["producer"]["commit"])
            if (historical["remoteBuildAuthorized"] is not True or historical["event"] not in ("pull_request", "merge_group")
                    or product_reuse._consumer(historical, {"GITHUB_RUN_ID": str(receipt["producer"]["runId"]),
                        "GITHUB_RUN_ATTEMPT": str(receipt["producer"]["runAttempt"])})["producer"] != receipt["producer"]):
                raise ValueError("Original Maven historical plan differs from its authorized producer")
            inputs = original / ("inputs/predecessors" if phase == "binary" else "inputs")
            for directory in (original / "selection", inputs):
                if (_json(directory / "phase-plan.json") != {name: receipt[name] for name in PHASE_PLAN_KEYS}
                        or _json(directory / "producer.json") != receipt["producer"]):
                    raise ValueError("Original Maven retained election differs from its receipt")
            contract_version = _contract(original, receipt, evidence)
            archive_name = None
            if android_runtime_archive is not None:
                archive_name = Path(android_runtime_archive).name
                _layout(original / "android-original", {archive_name})
                if _read(original / "android-original" / archive_name) != files_before["archive"]:
                    raise ValueError("Original Android archive differs from caller input")
                properties = _properties(git_regular_blob_bytes(root, receipt["producer"]["commit"],
                    "gradle.properties", max_bytes=1024 * 1024), "Original Android runtime pins")
                require_semver(properties["codexAgent.codexVersion"], "Original Android runtime version")
                pinned = require_sha256("sha256:" + properties["codexAgent.codexArchiveSha256"], "Original Android archive pin")
                if sha256_file(files["archive"]) != pinned:
                    raise ValueError("Original Android archive differs from immutable Git pin")
                # No claim about compiler execution or extraction/bundled binary
                # semantics: those require the separate original native gate.
            _worker(original, receipt, context, contract_version, archive_name)
            retained[private] = _inventory(private, allow_empty=True)
            versions = git_product_versions(root, receipt["producer"]["commit"])
            result = {"stage": stage, "receiptPath": selected, "receiptBytes": raw,
                "receipt": receipt, "original": original, "capture": capture}
            result_bytes = view(result)
            if phase == "binary":
                projection = _contract_projection_from_request(instance, versions, evidence)
                _verify_plan(root, receipt, versions, [_json(evidence["phaseReceipt"])], projection)
                verify_sdk_maven_binary_content(stage, receipt)
                unchanged()
                yield result
                unchanged()
            else:
                binary = _predecessor(inputs, "sdk", component, "binary", target)
                current_contract = _predecessor(inputs, "contract", "contract", "metadata", "common")
                bundles = [row for row in current_contract["receipt"]["outputs"] if row["kind"] == "contract-bundle"]
                if len(bundles) != 1:
                    raise ValueError("Original Maven package needs exactly one Contract payload")
                source = sdk_runtime_source(root, receipt["producer"]["commit"],
                    instances=product_reuse._dependency_closure((instance,)),
                    runtime_version=versions["runtime-release"], sdk_version=versions["sdk"]) or "current-runtime"
                sdk_capture = original / "sdk-inputs-original"
                transport = require_exact_keys(_json(sdk_capture / "capture-transport.json"),
                    {"artifact", "captureProducer", "observed", "sdkRuntimeSource"}, "Original SDK inputs transport")
                product_reuse._verify_retained_sdk_upload_archive(sdk_capture, transport["artifact"])
                producer = receipt["producer"]
                if (transport["captureProducer"] != producer or transport["sdkRuntimeSource"] != source
                        or transport["artifact"].get("name") !=
                           f"codex-agent-sdk-inputs-{producer['tree']}-attempt-{producer['runAttempt']}"
                        or _read(sdk_capture / "plan/impact-plan.json") != _read(history)):
                    raise ValueError("Original Maven SDK inputs differ from original producer/plan")
                with verified_apple_original_inputs(sdk_capture, expected_source=source, keyring=Path(keyring),
                        keys_directory=Path(keys_directory), selection_repository_root=root,
                        selection_revision=producer["commit"], expected_contract_payload_sha256=bundles[0]["sha256"]) as joined:
                    arguments = joined["sdk"]["arguments"]
                    if _read(current_contract["receiptPath"]) != _read(arguments["contract_metadata_receipt"]):
                        raise ValueError("Original Maven current Contract differs from signed SDK inputs")
                    for contract_phase in ("binary", "package", "validation", "metadata"):
                        record = _predecessor(inputs, "contract", "contract", contract_phase, "common")
                        if _read(record["receiptPath"]) != _read(arguments["contract_attestation"].parent /
                                "execution-closure/receipts" / (contract_phase + ".json")):
                            raise ValueError("Original Maven current Contract differs from signed execution closure")
                    verified, verified_bytes = verify_sdk_package_inputs(root, stage, selected,
                        joined["sdk"]["directory"] / REQUEST_NAME, binary_stage_root=binary["stage"],
                        binary_receipt_path=binary["receiptPath"], binary_contract_evidence=evidence)
                    if verified != receipt or verified_bytes != raw:
                        raise ValueError("Original Maven full package gate returned a different receipt")
                    unchanged()
                    yield result
                    unchanged()
                unchanged()
        finally:
            unchanged()
            if _read(selected) != raw:
                raise ValueError("Original Maven selected receipt changed")
