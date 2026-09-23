"""Compose elected Android validation from existing authenticated gates.

This controller does not execute Firebase, mint host trust, sign content, or
grant family admission.  Caller-supplied originals and both official captures
remain external authority that the existing full gates must authenticate.
"""

import argparse
import os
from pathlib import Path
import tempfile

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    publish_regular_tree, regular_file_inventory, snapshot_regular_tree, write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.sdk_apple_validation_admission import apple_validation_policy_arguments
from products.sdk_inputs import stage_sdk_inputs
from products.sdk_package import _require_capability_output_separate
from products.sdk_validation_inputs import _request_inventory
from products.signatures import load_keyring, public_key_path
from products.signing_isolation import require_no_signing_secret
from sdk_android_evidence_capture import capture_android_evidence
from sdk_android_firebase_capture import capture_android_firebase_evidence
from products import sdk_android_validation_phase as validation_phase


_INSTANCE = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_STABLE_PRODUCER_FIELDS = (
    "repository", "workflowPath", "commit", "tree", "event", "pullRequest",
)
_LIMIT = 512 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _retain_original_inputs(request, evidence, destination):
    """Retain public replay inputs; caller authentication remains external."""
    original_request = destination / "original-compatibility-request.json"
    original_request.parent.mkdir(parents=True)
    original_request.write_bytes(_read(request))
    stage_sdk_inputs(original_request, destination / "sdk-inputs",
                     request_directory=Path(request).parent)
    if _read(original_request) != _read(request):
        raise ValueError("Retained Android compatibility request differs from its exact original")

    trees, files = validation_phase._contract_sources(evidence)
    captured = {
        "stageRoot": destination / "contract/stage",
        "phaseReceipt": destination / "contract/phase-receipt.json",
        "attestation": destination / "contract/auth/attestation" / Path(evidence["attestation"]).name,
        "attestationSignature": destination / "contract/auth/signature" /
            Path(evidence["attestationSignature"]).name,
        "publicKey": destination / "contract/auth/public-key" / Path(evidence["publicKey"]).name,
    }
    snapshot_regular_tree(trees["contract/stage"], captured["stageRoot"], allow_empty=True)
    snapshot_regular_tree(trees["contract/closure"],
        captured["attestation"].parent / validation_phase.CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
        allow_empty=True)
    for field in ("phaseReceipt", "attestation", "attestationSignature", "publicKey"):
        source, target = files["contract/" + field], captured[field]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_read(source))
    public_keys = {}
    if evidence["keyring"] is not None:
        captured["keyring"] = destination / "contract/trust" / Path(evidence["keyring"]).name
        captured["keyring"].parent.mkdir(parents=True)
        captured["keyring"].write_bytes(_read(files["contract/keyring"]))
        keyring = load_keyring(captured["keyring"], Path(evidence["keysDirectory"]))
        keys = destination / "contract/trust/keys"
        keys.mkdir(parents=True)
        for record in ([keyring["activeKey"]] if keyring["activeKey"] else []) + keyring["retiredKeys"]:
            source = public_key_path(Path(evidence["keysDirectory"]), record["keyId"])
            public_keys[source] = _read(source)
            (keys / source.name).write_bytes(public_keys[source])
        captured["keysDirectory"] = keys
    relocated = {name: (value if name == "expectedTrustDomain" or value is None else str(captured[name]))
                 for name, value in evidence.items()}
    retained_trees, retained_files = validation_phase._contract_sources(relocated)
    if (any(regular_file_inventory(retained_trees[name], allow_empty=True) !=
            regular_file_inventory(source, allow_empty=True) for name, source in trees.items()
            if name != "contract/keys")
            or any(_read(retained_files[name]) != _read(source) for name, source in files.items())
            or any(_read(source) != raw or _read(captured["keysDirectory"] / source.name) != raw
                   for source, raw in public_keys.items())):
        raise ValueError("Retained Android Contract evidence differs from its exact original")
    write_canonical_json(destination / "binary-contract-invocation.json", relocated)


def execute(
    plan: Path, discovery: Path, state: Path, destination: Path, *,
    expected_build_key: str,
    package_stage: Path, package_receipt: Path,
    binary_stage: Path, binary_receipt: Path,
    compatibility_request: Path, binary_contract_evidence: dict,
    trusted_workflow_sha: str, trusted_android_workflow_sha: str,
    trusted_source_commit: str, trusted_source_tree: str,
    tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, apkanalyzer_executable: Path,
    policy_revision: str, required_trust_domain: str,
    repository_root: Path, environ: dict, token: str,
    tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
    sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None,
    sdk_android_metadata_admission=None,
) -> dict:
    """Finalize one elected Android validation only after all original checks."""
    require_no_signing_secret(environ)
    if (tooling_keyring is None) != (tooling_keys_directory is None):
        raise ValueError("Android tooling keyring and directory must be supplied together")
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK Android validation destination must not exist")

    plan = Path(plan).absolute()
    package_stage, binary_stage = Path(package_stage).absolute(), Path(binary_stage).absolute()
    package_receipt, binary_receipt = Path(package_receipt).absolute(), Path(binary_receipt).absolute()
    compatibility_request = Path(compatibility_request).absolute()
    tooling_evidence, tooling_public_key = Path(tooling_evidence).absolute(), Path(tooling_public_key).absolute()
    java_executable, apkanalyzer_executable = Path(java_executable).absolute(), Path(apkanalyzer_executable).absolute()
    plan_bytes = _read(plan)
    trees = {"discovery": discovery, "state": state, "package": package_stage,
             "binary": binary_stage, "tooling": tooling_evidence}
    files = {"packageReceipt": package_receipt, "binaryReceipt": binary_receipt,
             "compatibilityRequest": compatibility_request,
             "toolingPublicKey": tooling_public_key, "java": java_executable,
             "apkanalyzer": apkanalyzer_executable}
    contract_trees, contract_files = validation_phase._contract_sources(binary_contract_evidence)
    trees.update(contract_trees)
    files.update(contract_files)
    if sdk_apple_validation_policy is not None:
        for name, path in apple_validation_policy_arguments(sdk_apple_validation_policy).items():
            if isinstance(path, Path):
                (trees if path.is_dir() else files)["applePolicy/" + name] = path
    if tooling_keyring is not None:
        files["toolingKeyring"] = Path(tooling_keyring)
        trees["toolingKeysDirectory"] = Path(tooling_keys_directory)
    compatibility_before = _request_inventory(compatibility_request)
    _require_capability_output_separate(
        destination, [plan, compatibility_request, *compatibility_before,
                      *trees.values(), *files.values()])
    tree_before = {name: regular_file_inventory(path, allow_empty=True)
                   for name, path in trees.items()}
    file_before = {name: _read(path) for name, path in files.items()}
    policy_before = canonical_json_bytes({
        "binaryContractEvidence": binary_contract_evidence,
        "trustedWorkflowSha": trusted_workflow_sha,
        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "policyRevision": policy_revision,
        "requiredTrustDomain": required_trust_domain,
        "sdkAppleValidationPolicy": sdk_apple_validation_policy,
    })
    retained = {}
    selected_inventory = None
    stage = destination / "stage"
    stage_inventory = None
    ready = producer = version = manifest = None

    def unchanged():
        require_no_signing_secret(environ)
        if (_read(plan) != plan_bytes
                or canonical_json_bytes({
                    "binaryContractEvidence": binary_contract_evidence,
                    "trustedWorkflowSha": trusted_workflow_sha,
                    "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
                    "trustedSourceCommit": trusted_source_commit,
                    "trustedSourceTree": trusted_source_tree,
                    "policyRevision": policy_revision,
                    "requiredTrustDomain": required_trust_domain,
                    "sdkAppleValidationPolicy": sdk_apple_validation_policy,
                }) != policy_before
                or any(regular_file_inventory(path, allow_empty=True) != tree_before[name]
                       for name, path in trees.items())
                or any(_read(path) != file_before[name] for name, path in files.items())
                or _request_inventory(compatibility_request) != compatibility_before
                or any(regular_file_inventory(path, allow_empty=True) != inventory
                       for path, inventory in retained.items())
                or (selected_inventory is not None and
                    regular_file_inventory(destination / "inputs", allow_empty=True) != selected_inventory)
                or (ready is not None and canonical_json_bytes(ready) !=
                    _read(destination / "inputs/phase-plan.json"))
                or (producer is not None and canonical_json_bytes(producer) !=
                    _read(destination / "inputs/producer.json"))
                or (stage_inventory is not None and
                    regular_file_inventory(stage) != stage_inventory)):
            raise ValueError("SDK Android validation original inputs or retained evidence changed")

    tooling = {
        "evidence": str(tooling_evidence), "publicKey": str(tooling_public_key),
        "javaExecutable": str(java_executable), "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None,
    }
    apple = ({} if sdk_apple_validation_policy is None else
             {"sdk_apple_validation_policy": sdk_apple_validation_policy})
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    destination = product_reuse._prepare_destination(destination, root)
    ready = product_reuse.materialize_product_predecessors(
        plan, discovery, state, _INSTANCE, destination / "inputs",
        expected_build_key=expected_build_key, repository_root=root, environ=environ,
        sdk_validation_tooling=tooling, sdk_original_workflow_sha=trusted_workflow_sha,
        **apple, **admissions)
    selected_inventory = regular_file_inventory(destination / "inputs", allow_empty=True)
    producer = product_reuse.validate_producer(product_reuse._canonical_control(
        destination / "inputs/producer.json", "Elected Android validation producer"))
    if _read(destination / "inputs/phase-plan.json") != canonical_json_bytes(ready):
        raise ValueError("Android validation retained election differs from its selected plan")

    def selected(phase):
        directory = destination / f"inputs/sdk-sdk-android-{phase}-android"
        receipt_path = directory / "phase-receipt.json"
        raw = _read(receipt_path)
        receipt = product_reuse.validate_phase_receipt(load_canonical_json_bytes(raw))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                "sdk", "sdk-android", phase, "android"):
            raise ValueError("Android validation selected predecessor identity is invalid")
        manifest_value = product_reuse.verify_output_manifest_identity(
            directory / "stage", "sdk", "sdk-android", phase, "android", receipt["productVersion"])
        if manifest_value["outputs"] != receipt["outputs"]:
            raise ValueError("Android validation selected predecessor differs from its receipt")
        return directory / "stage", receipt, raw

    selected_package_stage, selected_package, selected_package_bytes = selected("package")
    selected_binary_stage, selected_binary, selected_binary_bytes = selected("binary")
    package = product_reuse.validate_phase_receipt(load_canonical_json_bytes(file_before["packageReceipt"]))
    binary = product_reuse.validate_phase_receipt(load_canonical_json_bytes(file_before["binaryReceipt"]))
    if (file_before["packageReceipt"] != selected_package_bytes
            or file_before["binaryReceipt"] != selected_binary_bytes
            or regular_file_inventory(package_stage) != regular_file_inventory(selected_package_stage)
            or regular_file_inventory(binary_stage) != regular_file_inventory(selected_binary_stage)):
        raise ValueError("Android caller package or binary differs from its elected original predecessor")
    if package != selected_package or binary != selected_binary:
        raise ValueError("Android caller package or binary receipt differs from its elected original")
    original_producer = product_reuse.validate_producer(binary["producer"], "Android binary original producer")
    if any(producer[field] != original_producer[field] for field in _STABLE_PRODUCER_FIELDS):
        raise ValueError("Android current capture and binary original select different candidate identities")
    version = package["productVersion"]
    if binary["productVersion"] != version:
        raise ValueError("Android selected package and binary versions differ")
    unchanged()

    try:
        with tempfile.TemporaryDirectory(prefix="sdk-android-validation-captures-") as temporary:
            private = Path(temporary).resolve()
            private_final, private_protected = private / "final", private / "protected"
            final_transport = capture_android_evidence(
                plan, root, private_final, trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                environ=environ, token=token)
            if final_transport.get("captureProducer") != producer:
                raise ValueError("Android final capture differs from the elected producer")
            protected_transport = capture_android_firebase_evidence(
                plan, root, private_final, private_protected,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree, environ=environ, token=token)
            if protected_transport.get("captureProducer") != producer:
                raise ValueError("Android protected capture differs from the elected producer")
            private_inventories = {
                "final": regular_file_inventory(private_final, allow_empty=True),
                "protected": regular_file_inventory(private_protected, allow_empty=True),
            }
            originals = destination / "originals"
            for name, source in (("final", private_final), ("protected", private_protected)):
                target = originals / name
                snapshot_regular_tree(source, target, allow_empty=True)
                if regular_file_inventory(target, allow_empty=True) != private_inventories[name]:
                    raise ValueError("Android retained capture differs from its exact private original")
                retained[target] = private_inventories[name]
            _retain_original_inputs(compatibility_request, binary_contract_evidence,
                                    originals / "validation-inputs")
            retained[originals] = regular_file_inventory(originals, allow_empty=True)
            unchanged()
            manifest = validation_phase.produce_sdk_android_validation_phase(
                repository=root, package_stage=package_stage, package_receipt=package_receipt,
                binary_stage=binary_stage, binary_receipt=binary_receipt,
                compatibility_request=compatibility_request,
                binary_contract_evidence=binary_contract_evidence,
                final_capture=private_final, protected_capture=private_protected,
                expected_capture_producer=producer,
                expected_original_producer=original_producer,
                trusted_source_commit=trusted_source_commit, trusted_source_tree=trusted_source_tree,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, apkanalyzer_executable=apkanalyzer_executable,
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                destination=stage, tooling_keyring=tooling_keyring,
                tooling_keys_directory=tooling_keys_directory)
            stage_inventory = regular_file_inventory(stage)
            if (regular_file_inventory(private_final, allow_empty=True) != private_inventories["final"]
                    or regular_file_inventory(private_protected, allow_empty=True) != private_inventories["protected"]):
                raise ValueError("Android private captures changed during full validation")
            unchanged()
    finally:
        unchanged()

    product_reuse._runtime_worker_checkout(root, producer)
    trust = "development" if producer["event"] == "pull_request" else "release"
    try:
        with tempfile.TemporaryDirectory(prefix="sdk-android-validation-candidate-") as temporary:
            candidate = Path(temporary).resolve() / "shard"
            shard = product_reuse.finalize_phase_object(
                stage_root=stage, phase_plan=ready, producer=producer,
                product_version=version, trust_domain=trust, destination=candidate)
            inventory = regular_file_inventory(candidate)
            if product_reuse.verify_phase_shard(candidate, _INSTANCE) != shard:
                raise ValueError("Android validation candidate differs from its finalized shard")
            unchanged()
            if regular_file_inventory(candidate) != inventory:
                raise ValueError("Android validation candidate changed before publication")
            publish_regular_tree(candidate, destination / "shard")
        if product_reuse.verify_phase_shard(destination / "shard", _INSTANCE) != shard:
            raise ValueError("Published Android validation shard differs from its private candidate")
    finally:
        unchanged()
    return {"stage": stage, "manifest": manifest, "shard": shard,
            "originals": destination / "originals"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "plan", "destination",
        "package-stage", "package-receipt", "binary-stage", "binary-receipt",
        "compatibility-request", "binary-contract-evidence", "tooling-evidence",
        "tooling-public-key", "java-executable", "apkanalyzer-executable",
        "repository-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    for name in (
        "expected-build-key", "trusted-workflow-sha", "trusted-android-workflow-sha",
        "trusted-source-commit", "trusted-source-tree", "policy-revision",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Android tooling keyring and directory must be supplied together")
    try:
        with metadata_admission_options(arguments) as admissions:
            arguments["binary_contract_evidence"] = product_reuse._canonical_control(
                arguments["binary_contract_evidence"], "Caller Android binary Contract evidence")
            apple = arguments.pop("sdk_apple_validation_policy")
            if apple is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                    apple, "Caller Apple validation policy")
            execute(**arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""),
                    **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
