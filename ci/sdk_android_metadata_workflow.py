"""Produce elected Android metadata after exact original validation replay.

A retained capture must come from an independently authenticated carrier; the
alternative observed mode re-observes the caller-selected official artifacts.
Neither capture grants authority: caller-owned package, binary, S858, Contract,
tooling and source policy remain mandatory. This controller executes no
Firebase work, compiles no product, and finalizes only after every original
check has exited.
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, git_product_versions, load_canonical_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_semver, require_sha256, run_git,
    publish_regular_tree, snapshot_regular_tree, write_canonical_json,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST, plan_phase
from products.receipt import validate_producer, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import PHASE_PLAN_KEYS, PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_android_metadata import (
    OUTPUT_KIND, OUTPUT_PATH, write_android_metadata_content,
)
from products.sdk_android_validation_content import validate_android_validation_content
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_inputs import stage_sdk_inputs
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.selection import phase_git_inventory
from products.signatures import load_keyring, public_key_path
from products.signing_isolation import require_no_signing_secret
from products import sdk_android_validation_phase as validation_phase


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "metadata", "android")
_VALIDATION = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _single_file(directory, label, *, allowed_directories=()):
    directory = Path(directory)
    entries = list(directory.iterdir())
    files = [path for path in entries if path.is_file() and not path.is_symlink()]
    directories = [path.name for path in entries if path.is_dir() and not path.is_symlink()]
    if (len(files) != 1 or sorted(directories) != sorted(allowed_directories)
            or len(entries) != len(files) + len(directories)):
        raise ValueError(f"{label} must contain exactly one regular file")
    return files[0]


def _retained_contract(root, required_trust_domain):
    contract = Path(root) / "originals/validation-inputs/contract"
    invocation = require_exact_keys(load_canonical_json_bytes(_read(
        Path(root) / "originals/validation-inputs/binary-contract-invocation.json")),
        {"stageRoot", "phaseReceipt", "attestation", "attestationSignature", "publicKey",
         "expectedTrustDomain", "keyring", "keysDirectory"},
        "Retained Android Contract invocation")
    if invocation["expectedTrustDomain"] != required_trust_domain:
        raise ValueError("Retained Android Contract trust differs from caller policy")
    for field in ("stageRoot", "phaseReceipt", "attestation", "attestationSignature", "publicKey"):
        if type(invocation[field]) is not str or not Path(invocation[field]).is_absolute():
            raise ValueError("Retained Android Contract invocation path is invalid")
    trust = contract / "trust"
    paired = invocation["keyring"] is not None and invocation["keysDirectory"] is not None
    if paired != trust.is_dir() or (invocation["keyring"] is None) != (invocation["keysDirectory"] is None):
        raise ValueError("Retained Android Contract public policy is incomplete")
    if paired and any(type(invocation[field]) is not str or not Path(invocation[field]).is_absolute()
                      for field in ("keyring", "keysDirectory")):
        raise ValueError("Retained Android Contract public policy path is invalid")
    keyring = None
    if paired:
        direct = [path for path in trust.iterdir() if path.name != "keys"]
        if len(direct) != 1 or not direct[0].is_file() or (trust / "keys").is_symlink():
            raise ValueError("Retained Android Contract keyring layout is invalid")
        keyring = direct[0]
    evidence = {
        "stageRoot": str(contract / "stage"),
        "phaseReceipt": str(contract / "phase-receipt.json"),
        "attestation": str(_single_file(contract / "auth/attestation", "Retained Contract attestation",
            allowed_directories=(validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY,))),
        "attestationSignature": str(_single_file(contract / "auth/signature", "Retained Contract signature")),
        "publicKey": str(_single_file(contract / "auth/public-key", "Retained Contract public key")),
        "expectedTrustDomain": required_trust_domain,
        "keyring": str(keyring) if paired else None,
        "keysDirectory": str(trust / "keys") if paired else None,
    }
    validation_phase._contract_sources(evidence)
    return evidence


def _compare_original_inputs(root, *, package_stage, package_receipt, binary_stage,
                             binary_receipt, compatibility_request, binary_contract_evidence):
    inputs = Path(root) / "inputs"
    selected = {
        "package": inputs / "sdk-sdk-android-package-android",
        "binary": inputs / "sdk-sdk-android-binary-android",
    }
    for name, stage, receipt in (
        ("package", Path(package_stage), Path(package_receipt)),
        ("binary", Path(binary_stage), Path(binary_receipt)),
    ):
        if (regular_file_inventory(selected[name] / "stage") != regular_file_inventory(stage)
                or _read(selected[name] / PHASE_RECEIPT_NAME) != _read(receipt)):
            raise ValueError(f"Retained Android {name} differs from caller-authenticated original")
    retained = Path(root) / "originals/validation-inputs"
    _read(retained / "original-compatibility-request.json")
    with tempfile.TemporaryDirectory(prefix="android-metadata-sdk-inputs-") as temporary:
        staged = Path(temporary).resolve() / "sdk-inputs"
        stage_sdk_inputs(Path(compatibility_request), staged,
                         request_directory=Path(compatibility_request).parent)
        if regular_file_inventory(staged) != regular_file_inventory(retained / "sdk-inputs"):
            raise ValueError("Retained Android S858 inputs differ from caller-authenticated inputs")
    expected_trees, expected_files = validation_phase._contract_sources(binary_contract_evidence)
    retained_trees, retained_files = validation_phase._contract_sources(
        _retained_contract(root, binary_contract_evidence["expectedTrustDomain"]))
    expected_public = {}
    if binary_contract_evidence["keyring"] is not None:
        ring = load_keyring(Path(binary_contract_evidence["keyring"]),
                            Path(binary_contract_evidence["keysDirectory"]))
        for record in ([ring["activeKey"]] if ring["activeKey"] else []) + ring["retiredKeys"]:
            path = public_key_path(Path(binary_contract_evidence["keysDirectory"]), record["keyId"])
            expected_public[path.name] = _read(path)
    retained_public = ({} if "contract/keys" not in retained_trees else {
        row["relativePath"]: _read(retained_trees["contract/keys"] / row["relativePath"])
        for row in regular_file_inventory(retained_trees["contract/keys"], allow_empty=True)
    })
    if (any(regular_file_inventory(retained_trees[name], allow_empty=True) !=
            regular_file_inventory(source, allow_empty=True) for name, source in expected_trees.items()
            if name != "contract/keys")
            or any(_read(retained_files[name]) != _read(source)
                   for name, source in expected_files.items())
            or retained_public != expected_public):
        raise ValueError("Retained Android Contract evidence differs from caller-authenticated original")


def _replan(repository, receipt, package):
    producer = validate_producer(receipt["producer"], "Original Android validation producer")
    try:
        if (run_git(repository, "rev-parse", f"{producer['commit']}^{{commit}}").strip() != producer["commit"]
                or run_git(repository, "rev-parse", f"{producer['commit']}^{{tree}}").strip() != producer["tree"]):
            raise ValueError("Original Android validation source differs from its producer")
    except subprocess.CalledProcessError as error:
        raise ValueError("Original Android validation source is unavailable") from error
    versions = git_product_versions(repository, producer["commit"])
    if versions["sdk"] != receipt["productVersion"]:
        raise ValueError("Original Android validation version differs from immutable Git source")
    expected = plan_phase(
        _VALIDATION, inventory=phase_git_inventory(repository, producer["commit"], _VALIDATION),
        versions=versions, upstream_receipts=[package],
        toolchain_profile_digest=NOT_APPLICABLE_TOOLCHAIN_DIGEST,
        flags_digest=NOT_APPLICABLE_FLAGS_DIGEST, output_schema_version=1,
    )
    if receipt["inputs"] != expected["inputs"] or receipt["buildKey"] != expected["buildKey"]:
        raise ValueError("Original Android validation key differs from immutable Git replan")


def _execute_metadata(plan, *, producer, sdk_version, request, repository_root,
                      destination, environ):
    selected = require_exact_keys(plan, PHASE_PLAN_KEYS, "Android metadata phase plan")
    if (require_integer(selected["schemaVersion"], "Android metadata plan schema", 1) != 1
            or tuple(selected[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-android", "metadata", "android")):
        raise ValueError("Unsupported Android metadata phase plan")
    require_sha256(selected["buildKey"], "Android metadata build key")
    current = validate_producer(producer, "Android metadata producer")
    version = require_semver(sdk_version, "Android metadata SDK version")
    request = Path(request).absolute()
    request_bytes = _read(request)
    root, destination = Path(repository_root).resolve(strict=True), Path(destination).absolute()
    stage = root / "build/product-stage/sdk/sdk-android/metadata/android"
    _require_capability_output_separate(destination, [stage, request])
    _require_capability_output_separate(stage, request)
    if any(path.exists() or path.is_symlink() for path in (destination, stage)):
        raise ValueError("Android metadata requires fresh diagnostics and product output")
    product_reuse._prepare_destination(stage, root).rmdir()
    environment, wrapper = product_reuse._runtime_worker_environment(root, current, destination, environ)
    destination = product_reuse._prepare_destination(destination, root)
    fields = {
        "codexAgent.product": "sdk", "codexAgent.component": "sdk-android",
        "codexAgent.phase": "metadata", "codexAgent.target": "android",
        "codexAgent.candidateCommit": current["commit"],
        "codexAgent.candidateTree": current["tree"], "codexAgent.sdkVersion": version,
        "codexAgent.sdkAndroidMetadataRequest": str(request),
    }

    def unchanged():
        product_reuse._runtime_worker_checkout(root, current)
        if _read(request) != request_bytes:
            raise ValueError("Android metadata request changed during execution")
        bytecode = destination / "python-bytecode"
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Android metadata private bytecode namespace was modified")

    unchanged()
    command = product_reuse._runtime_worker_command(wrapper, fields, environment, build_directory=".")
    if command.count("ciProductPhase") != 1:
        raise ValueError("Android metadata worker no longer runs the fixed product phase")
    started, return_code, launch_error = time.monotonic_ns(), None, None
    try:
        with (destination / "gradle.log").open("xb") as log:
            process = subprocess.run(command, cwd=root, env=environment, stdout=log,
                                     stderr=subprocess.STDOUT, check=False)
            return_code = process.returncode
    except OSError as error:
        launch_error = str(error)
        raise
    finally:
        write_canonical_json(destination / "execution.json", {
            "schemaVersion": 1, "producer": current, "buildKey": selected["buildKey"],
            "command": command, "workingDirectory": str(root), "returnCode": return_code,
            "launchError": launch_error, "elapsedNs": time.monotonic_ns() - started,
        })
        unchanged()
    if return_code != 0:
        raise ValueError(f"Android metadata failed with exit code {return_code}; see {destination / 'gradle.log'}")
    manifest = verify_output_manifest_identity(
        stage, "sdk", "sdk-android", "metadata", "android", version)
    if (len(manifest["outputs"]) != 1 or manifest["outputs"][0]["kind"] != OUTPUT_KIND
            or manifest["outputs"][0]["relativePath"] != OUTPUT_PATH):
        raise ValueError("Android metadata canonical output is missing or ambiguous")
    inventory = regular_file_inventory(stage)
    unchanged()
    return {"stage": stage, "content": stage / OUTPUT_PATH,
            "outputInventory": inventory, "diagnostics": destination}


def execute(plan, discovery, state, destination, *, expected_build_key,
            package_stage, package_receipt,
            binary_stage, binary_receipt, compatibility_request,
            binary_contract_evidence, trusted_source_commit, trusted_source_tree,
            tooling_evidence, tooling_public_key, java_executable,
            apkanalyzer_executable, policy_revision, required_trust_domain,
            repository_root, environ, tooling_keyring=None,
            tooling_keys_directory=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
            original_validation_capture=None, validation_artifact_id=None,
            validation_artifact_sha256=None, trusted_workflow_sha=None,
            trusted_android_workflow_sha=None, expected_original_run_id=None,
            expected_original_run_attempt=None, token=None):
    """Finalize metadata after selected original validation and full replay agree.

    Retained mode requires a caller-authenticated enclosing carrier and grants
    no hosted authority. Observed mode independently re-observes the validation
    worker plus both nested official Android/Firebase artifacts.
    """
    require_no_signing_secret(environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android metadata tooling keyring and directory must be paired")
    observed_values = (
        validation_artifact_id, validation_artifact_sha256,
        trusted_workflow_sha, trusted_android_workflow_sha,
        expected_original_run_id, expected_original_run_attempt,
    )
    retained_mode = original_validation_capture is not None
    observed_mode = all(value is not None for value in observed_values)
    if retained_mode == observed_mode or (any(
            value is not None for value in observed_values) and not observed_mode):
        raise ValueError("Android metadata requires exactly one complete original validation mode")
    if not retained_mode:
        require_integer(validation_artifact_id, "Original Android validation artifact ID", 1)
        require_sha256(validation_artifact_sha256, "Original Android validation artifact digest")
        require_integer(expected_original_run_id, "Original Android validation run ID", 1)
        require_integer(expected_original_run_attempt, "Original Android validation run attempt", 1)
        if type(token) is not str or not token:
            raise ValueError("Observed Android metadata admission requires an observation token")
    root = Path(repository_root).resolve(strict=True)
    plan = Path(plan).absolute()
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Android metadata destination must not exist")
    trees = {
        "discovery": discovery, "state": state,
        "package": Path(package_stage).absolute(), "binary": Path(binary_stage).absolute(),
        "tooling": Path(tooling_evidence).absolute(),
    }
    if retained_mode:
        trees["originalValidationCapture"] = Path(original_validation_capture).absolute()
    files = {
        "plan": plan, "packageReceipt": Path(package_receipt).absolute(),
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
    if sdk_apple_validation_policy is not None:
        for name, value in apple_validation_policy_arguments(sdk_apple_validation_policy).items():
            if isinstance(value, Path):
                (trees if value.is_dir() else files)["applePolicy/" + name] = value
    request_inventory = _request_inventory(files["compatibilityRequest"])
    _require_capability_output_separate(
        destination, [*trees.values(), *files.values(), *request_inventory])
    product_stage = root / "build/product-stage/sdk/sdk-android/metadata/android"
    _require_capability_output_separate(
        product_stage, [destination, *trees.values(), *files.values(), *request_inventory])
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    policy_before = canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree, "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
        "sdkAppleValidationPolicy": sdk_apple_validation_policy,
        "originalMode": {
            "retained": retained_mode,
            "validationArtifactId": validation_artifact_id,
            "validationArtifactSha256": validation_artifact_sha256,
            "trustedWorkflowSha": trusted_workflow_sha,
            "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
            "expectedOriginalRunId": expected_original_run_id,
            "expectedOriginalRunAttempt": expected_original_run_attempt,
        },
    })
    retained = {}
    bindings = {"ready": None, "producer": None, "materialized": None,
                "validation": None, "readyBytes": None, "producerBytes": None,
                "materializedBytes": None, "validationBytes": None}

    def unchanged():
        require_no_signing_secret(environ)
        if (any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(files["compatibilityRequest"]) != request_inventory
                or canonical_json_bytes({
                    "binaryContractEvidence": binary_contract_evidence,
                    "trustedSourceCommit": trusted_source_commit,
                    "trustedSourceTree": trusted_source_tree, "policyRevision": policy_revision,
                    "requiredTrustDomain": required_trust_domain,
                    "sdkAppleValidationPolicy": sdk_apple_validation_policy,
                    "originalMode": {
                        "retained": retained_mode,
                        "validationArtifactId": validation_artifact_id,
                        "validationArtifactSha256": validation_artifact_sha256,
                        "trustedWorkflowSha": trusted_workflow_sha,
                        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
                        "expectedOriginalRunId": expected_original_run_id,
                        "expectedOriginalRunAttempt": expected_original_run_attempt,
                    },
                }) != policy_before
                or (bindings["ready"] is not None and
                    canonical_json_bytes(bindings["ready"]) != bindings["readyBytes"])
                or (bindings["producer"] is not None and
                    canonical_json_bytes(bindings["producer"]) != bindings["producerBytes"])
                or (bindings["materialized"] is not None and
                    canonical_json_bytes(bindings["materialized"]) != bindings["materializedBytes"])
                or (bindings["validation"] is not None and
                    canonical_json_bytes(bindings["validation"]) != bindings["validationBytes"])
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in retained.items())):
            raise ValueError("Android metadata originals or caller policy changed")

    tooling = {
        "evidence": str(trees["tooling"]), "publicKey": str(files["toolingPublicKey"]),
        "javaExecutable": str(files["java"]), "requiredTrustDomain": required_trust_domain,
        "keyring": str(files["toolingKeyring"]) if tooling_keyring is not None else None,
        "keysDirectory": str(trees["toolingKeys"]) if tooling_keys_directory is not None else None,
    }
    apple = ({} if sdk_apple_validation_policy is None else
             {"sdk_apple_validation_policy": sdk_apple_validation_policy})
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    try:
        # Keep the whole selected flow under one lifetime guard.  In particular,
        # failures before publication must still recheck every caller-owned input.
        verified = product_reuse._verified_product_state(
            plan, discovery, state, root, environ, tooling, **apple, **admissions)
        ready = verified.prior_ready_plans.get(_INSTANCE)
        if ready is None or ready["buildKey"] != expected_build_key:
            raise ValueError("Android metadata is not ready with the elected build key")
        producer = validate_producer(verified.producer, "Elected Android metadata producer")
        version = verified.expected_fixed["versions"]["sdk"]
        ready_bytes, producer_bytes = canonical_json_bytes(ready), canonical_json_bytes(producer)
        bindings.update(ready=ready, producer=producer, readyBytes=ready_bytes,
                        producerBytes=producer_bytes)
        unchanged()
        destination = product_reuse._prepare_destination(destination, root)
        inputs = destination / "inputs"
        materialized = product_reuse.materialize_product_predecessors(
            plan, discovery, state, _INSTANCE, inputs, expected_build_key=expected_build_key,
            repository_root=root, environ=environ, sdk_validation_tooling=tooling,
            **apple, **admissions)
        materialized_bytes = canonical_json_bytes(materialized)
        bindings.update(materialized=materialized, materializedBytes=materialized_bytes)
        if materialized != ready or _read(inputs / "phase-plan.json") != ready_bytes:
            raise ValueError("Materialized Android metadata election differs from authenticated state")
        if canonical_json_bytes(product_reuse.validate_producer(product_reuse._canonical_control(
                inputs / "producer.json", "Elected Android metadata producer"))) != producer_bytes:
            raise ValueError("Materialized Android metadata producer differs from authenticated state")
        retained[inputs] = regular_file_inventory(inputs, allow_empty=True)
        selection = destination / "selection"
        selection.mkdir()
        (selection / "impact-plan.json").write_bytes(file_before["plan"])
        write_canonical_json(selection / "phase-plan.json", ready)
        write_canonical_json(selection / "producer.json", producer)
        if (_read(selection / "impact-plan.json") != file_before["plan"]
                or _read(selection / "phase-plan.json") != ready_bytes
                or _read(selection / "producer.json") != producer_bytes):
            raise ValueError("Retained Android metadata selection differs from authenticated election")
        retained[selection] = regular_file_inventory(selection)

        selected = inputs / "sdk-sdk-android-validation-android"
        selected_receipt_path = selected / PHASE_RECEIPT_NAME
        selected_bytes = _read(selected_receipt_path)
        validation = product_reuse.validate_phase_receipt(load_canonical_json_bytes(selected_bytes))
        bindings.update(validation=validation, validationBytes=selected_bytes)
        if (tuple(validation[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-android", "validation", "android")
                or validation["productVersion"] != version):
            raise ValueError("Android metadata selected validation identity or version is invalid")
        selected_manifest = verify_output_manifest_identity(
            selected / "stage", "sdk", "sdk-android", "validation", "android", version)
        if selected_manifest["outputs"] != validation["outputs"]:
            raise ValueError("Android metadata selected validation differs from its receipt")

        # Local imports avoid the reader cycle while both modes share one
        # downstream metadata production and finalization body.
        if __package__:
            from .sdk_android_original_validation import verified_retained_android_validation
            from .sdk_android_firebase_original import verified_original_android_firebase_validation
        else:
            from sdk_android_original_validation import verified_retained_android_validation
            from sdk_android_firebase_original import verified_original_android_firebase_validation
        common_original = dict(
            package_stage=trees["package"], package_receipt=files["packageReceipt"],
            binary_stage=trees["binary"], binary_receipt=files["binaryReceipt"],
            compatibility_request=files["compatibilityRequest"],
            binary_contract_evidence=binary_contract_evidence,
            trusted_source_commit=trusted_source_commit,
            trusted_source_tree=trusted_source_tree,
            tooling_evidence=trees["tooling"],
            tooling_public_key=files["toolingPublicKey"],
            java_executable=files["java"],
            apkanalyzer_executable=files["apkanalyzer"],
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            repository_root=root, environ=environ,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory,
        )
        if retained_mode:
            original_context = verified_retained_android_validation(
                plan, selected_receipt_path,
                validation_capture=trees["originalValidationCapture"],
                **common_original)
        else:
            original_context = verified_original_android_firebase_validation(
                plan, selected_receipt_path,
                validation_artifact_id=validation_artifact_id,
                validation_artifact_sha256=validation_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                expected_original_run_id=expected_original_run_id,
                expected_original_run_attempt=expected_original_run_attempt,
                token=token, **common_original)
        with tempfile.TemporaryDirectory(prefix="sdk-android-metadata-") as temporary:
            private = Path(temporary).resolve()
            with original_context as original:
                if (original["receiptBytes"] != selected_bytes
                        or canonical_json_bytes(original["receipt"]) != selected_bytes
                        or regular_file_inventory(original["stage"]) !=
                           regular_file_inventory(selected / "stage")):
                    raise ValueError("Verified Android validation differs from selected predecessor")
                validation_content = validate_android_validation_content(load_canonical_json_bytes(
                    _read(original["stage"] / validation_phase.OUTPUT_PATH)))
                request = destination / "metadata-request.json"
                write_canonical_json(request, {
                    "sdkVersion": version, "packageStage": str(trees["package"]),
                    "packageReceipt": str(files["packageReceipt"]),
                    "validationStage": str(selected / "stage"),
                    "validationReceipt": str(selected_receipt_path),
                    "releaseAarSha256": validation_content["releaseAarSha256"],
                    "bundledRuntimeSha256": validation_content["bundledRuntimeSha256"],
                })
                request_bytes = _read(request)
                expected_path = private / "expected-metadata.json"
                expected = write_android_metadata_content(request, expected_path)
                originals = destination / "originals/validation"
                original_inventory = regular_file_inventory(original["capture"], allow_empty=True)
                snapshot_regular_tree(original["capture"], originals, allow_empty=True)
                if regular_file_inventory(originals, allow_empty=True) != original_inventory:
                    raise ValueError("Original Android validation capture changed during snapshot")
                retained[originals] = original_inventory
                unchanged()
                result = _execute_metadata(
                    ready, producer=producer, sdk_version=version, request=request,
                    repository_root=root, destination=destination / "worker", environ=environ)
                if (_read(result["content"]) != canonical_json_bytes(expected)
                        or regular_file_inventory(result["stage"]) != result["outputInventory"]):
                    raise ValueError("Android metadata producer differs from verified originals")
                output_inventory = result["outputInventory"]
                diagnostics_inventory = regular_file_inventory(result["diagnostics"], allow_empty=True)
                unchanged()
        # No receipt exists until the verified original-reader context has exited.
        unchanged()
        if (regular_file_inventory(result["stage"]) != output_inventory
                or regular_file_inventory(result["diagnostics"], allow_empty=True) != diagnostics_inventory
                or _read(request) != request_bytes
                or _read(result["content"]) != canonical_json_bytes(expected)):
            raise ValueError("Android metadata output changed before finalization")
        product_reuse._runtime_worker_checkout(root, producer)
        trust = "development" if producer["event"] == "pull_request" else "release"
        with tempfile.TemporaryDirectory(prefix="sdk-android-metadata-candidate-") as temporary:
            candidate = Path(temporary).resolve() / "shard"
            finalized = product_reuse.finalize_phase_object(
                stage_root=result["stage"], phase_plan=ready, producer=producer,
                product_version=version, trust_domain=trust, destination=candidate)
            candidate_inventory = regular_file_inventory(candidate)
            if (verify_phase_shard(candidate, _INSTANCE) != finalized
                    or regular_file_inventory(result["stage"]) != output_inventory
                    or regular_file_inventory(result["diagnostics"], allow_empty=True) != diagnostics_inventory
                    or _read(request) != request_bytes
                    or _read(result["content"]) != canonical_json_bytes(expected)):
                raise ValueError("Android metadata candidate or output changed during finalization")
            unchanged()
            if regular_file_inventory(candidate) != candidate_inventory:
                raise ValueError("Android metadata private candidate changed before publication")
            publish_regular_tree(candidate, destination / "shard")
        if verify_phase_shard(destination / "shard", _INSTANCE) != finalized:
            raise ValueError("Published Android metadata shard differs from private candidate")
        unchanged()
        return {**result, "shard": finalized, "originals": destination / "originals"}
    finally:
        unchanged()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "plan", "destination", "package-stage", "package-receipt",
        "binary-stage", "binary-receipt", "compatibility-request", "binary-contract-evidence",
        "tooling-evidence", "tooling-public-key", "java-executable", "apkanalyzer-executable",
        "repository-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in ("expected-build-key", "trusted-source-commit", "trusted-source-tree", "policy-revision"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--original-validation-capture", type=Path)
    parser.add_argument("--validation-artifact-id", type=int)
    for name in ("validation-artifact-sha256", "trusted-workflow-sha", "trusted-android-workflow-sha"):
        parser.add_argument("--" + name)
    parser.add_argument("--expected-original-run-id", type=int)
    parser.add_argument("--expected-original-run-attempt", type=int)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Android metadata tooling keyring and directory must be paired")
    try:
        arguments["binary_contract_evidence"] = product_reuse._canonical_control(
            arguments["binary_contract_evidence"], "Caller Android binary Contract evidence")
        policy = arguments.pop("sdk_apple_validation_policy")
        if policy is not None:
            arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                policy, "Caller Apple validation policy")
        execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
