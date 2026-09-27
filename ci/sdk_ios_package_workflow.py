"""Compose the existing authenticated inputs, iOS package worker and full gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
)
from products.sdk_apple_package_execution import build_apple_package_execution_context
from products.registry import PhaseInstanceId
from products.restore import PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import REQUEST_NAME
from products.sdk_package import verify_sdk_package_inputs
from sdk_ios_package import execute as execute_package


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")


def execute(
    plan: Path, discovery: Path, state: Path, destination: Path, *,
    expected_build_key: str,
    sdk_inputs_artifact_id: int, sdk_inputs_artifact_sha256: str,
    trusted_workflow_sha: str,
    keyring: Path, keys_directory: Path, developer_directory: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, repository_root: Path, environ: dict, token: str,
    required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
    sdk_apple_validation_policy=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict:
    """Build and admit one elected package; publish only after all contexts close."""
    root = Path(repository_root).resolve(strict=True)
    developer_directory = Path(developer_directory)
    if (not developer_directory.is_absolute() or not developer_directory.is_dir()
            or developer_directory.resolve(strict=True) != developer_directory):
        raise ValueError("Apple Developer directory must be absolute, normalized and non-symbolic")
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination,
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS package destination must not exist")
    plan_bytes = read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)

    tooling = {"evidence": str(Path(tooling_evidence).absolute()),
        "publicKey": str(Path(tooling_public_key).absolute()),
        "javaExecutable": str(Path(java_executable).absolute()),
        "requiredTrustDomain": required_trust_domain,
        "keyring": str(Path(tooling_keyring).absolute()) if tooling_keyring is not None else None,
        "keysDirectory": str(Path(tooling_keys_directory).absolute()) if tooling_keys_directory is not None else None}
    apple = ({} if sdk_apple_validation_policy is None else
             {"sdk_apple_validation_policy": sdk_apple_validation_policy})
    admissions = {name: value for name, value in (
        ("sdk_facade_metadata_admission", sdk_facade_metadata_admission),
        ("sdk_android_metadata_admission", sdk_android_metadata_admission),
    ) if value is not None}
    with tempfile.TemporaryDirectory(prefix="sdk-ios-package-candidate-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        with sdk_workflow.verified_inputs(
            plan, discovery, state, artifact_id=sdk_inputs_artifact_id,
            artifact_sha256=sdk_inputs_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
            keys_directory=keys_directory, repository_root=root,
            environ=environ, token=token, sdk_validation_tooling=tooling,
            **apple, **admissions,
        ) as sdk_inputs:
            selection = sdk_inputs["selection"]
            selected = {"product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios"}
            if selected not in selection["consumers"]:
                raise ValueError("SDK iOS package is not selected")
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(
                plan, discovery, state, _INSTANCE, prepared,
                expected_build_key=expected_build_key,
                repository_root=root, environ=environ, sdk_validation_tooling=tooling,
                sdk_original_workflow_sha=trusted_workflow_sha,
                **apple, **admissions,
            )
            prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
            producer = product_reuse.validate_producer(product_reuse._canonical_control(
                prepared / "producer.json", "Elected SDK iOS package producer",
            ))

            def original(product, component, phase, target):
                directory = prepared / "-".join((product, component, phase, target))
                receipt_path = directory / PHASE_RECEIPT_NAME
                receipt = product_reuse.validate_phase_receipt(product_reuse._canonical_control(
                    receipt_path, "Original SDK iOS package predecessor",
                ))
                if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                    product, component, phase, target,
                ):
                    raise ValueError("SDK iOS package predecessor has the wrong identity")
                manifest = product_reuse.verify_output_manifest_identity(
                    directory / "stage", product, component, phase, target, receipt["productVersion"],
                )
                if manifest["outputs"] != receipt["outputs"]:
                    raise ValueError("SDK iOS package predecessor differs from its original receipt")
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

            contract_metadata = original("contract", "contract", "metadata", "common")
            contract_binary = original("contract", "contract", "binary", "common")
            sdk_binary = original("sdk", "sdk-ios", "binary", "ios")
            arguments = sdk_inputs["sdk"]["arguments"]
            read_regular_file_bytes(
                arguments["contract_payload"], max_bytes=512 * 1024 * 1024,
                reject_symlink_parents=True,
            )
            if read_regular_file_bytes(contract_metadata["receiptPath"]) != read_regular_file_bytes(
                    arguments["contract_metadata_receipt"]):
                raise ValueError("Current Contract predecessor differs from authenticated SDK inputs")
            contract_evidence = {
                "stageRoot": str(contract_metadata["stage"]),
                "phaseReceipt": str(contract_metadata["receiptPath"]),
                "attestation": str(arguments["contract_attestation"]),
                "attestationSignature": str(arguments["contract_attestation_signature"]),
                "publicKey": str(arguments["contract_public_key"]),
                "expectedTrustDomain": arguments["required_trust_domain"],
                "keyring": str(arguments["contract_keyring"]) if arguments["contract_keyring"] else None,
                "keysDirectory": str(arguments["contract_keys_directory"])
                if arguments["contract_keys_directory"] else None,
            }
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package predecessors changed during Contract verification")
            result = execute_package(
                ready, producer=producer, sdk_version=selection["sdkVersion"],
                current_contract=contract_binary, sdk_binary=sdk_binary,
                compatibility_request=sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                repository_root=root, destination=destination / "worker",
                environ={**environ, "DEVELOPER_DIR": str(developer_directory)},
            )
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package authenticated inputs changed during execution")
            trust = "development" if producer["event"] == "pull_request" else "release"
            finalized = product_reuse.finalize_phase_object(
                stage_root=result["stage"], phase_plan=ready, producer=producer,
                product_version=selection["sdkVersion"], trust_domain=trust,
                destination=candidate,
            )
            apple_verification = {
                "developer_directory": Path(developer_directory),
                "repository": root,
                "tooling_evidence": Path(tooling_evidence),
                "tooling_public_key": Path(tooling_public_key),
                "java_executable": Path(java_executable),
                "policy_revision": policy_revision,
                "required_trust_domain": required_trust_domain,
                "tooling_keyring": tooling_keyring,
                "tooling_keys_directory": tooling_keys_directory,
            }
            verified, raw = verify_sdk_package_inputs(
                root, result["stage"], candidate / PHASE_RECEIPT_NAME,
                sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                binary_stage_root=sdk_binary["stage"],
                binary_receipt_path=sdk_binary["receiptPath"],
                binary_contract_evidence=contract_evidence,
                apple_binary_verification=apple_verification,
                apple_execution_capture_directory=destination / "package-execution",
            )
            if (verified != finalized["receipt"] or raw != read_regular_file_bytes(
                    candidate / PHASE_RECEIPT_NAME)):
                raise ValueError("SDK iOS package gate returned a different candidate receipt")
            execution_context = build_apple_package_execution_context(
                capture_directory=destination / "package-execution",
                package_receipt=candidate / PHASE_RECEIPT_NAME,
                binary_receipt=sdk_binary["receiptPath"],
                contract_binary_receipt=contract_binary["receiptPath"],
                contract_metadata_receipt=contract_metadata["receiptPath"],
                producer=producer,
                sdk_compatibility=result["stage"] / "outputs/evidence/sdk-compatibility.json",
                sdk_inputs_artifact_id=sdk_inputs_artifact_id,
                sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
            )
            context_bytes = canonical_json_bytes(execution_context)
            context_path = destination / "apple-package-execution.json"
            with context_path.open("xb") as context_file:
                context_file.write(context_bytes)
            if read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
                raise ValueError("SDK iOS package original plan changed during verification")
            retained_plan = destination / "original-plan/impact-plan.json"
            retained_plan.parent.mkdir()
            with retained_plan.open("xb") as plan_file:
                plan_file.write(plan_bytes)
            candidate_inventory = regular_file_inventory(candidate)
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package authenticated inputs changed before publication")
        if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
            raise ValueError("SDK iOS package authenticated inputs changed after SDK verification")
        if (regular_file_inventory(result["stage"], allow_empty=True) != result["outputInventory"]
                or regular_file_inventory(candidate) != candidate_inventory
                or verify_phase_shard(candidate, _INSTANCE) != finalized):
            raise ValueError("SDK iOS package candidate changed after admission")
        if (regular_file_inventory(destination / "package-execution", allow_empty=True) != execution_context["captureFiles"]
                or read_regular_file_bytes(context_path, reject_symlink_parents=True) != context_bytes):
            raise ValueError("SDK iOS package original execution capture changed before publication")
        if (read_regular_file_bytes(Path(plan), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(retained_plan, reject_symlink_parents=True) != plan_bytes):
            raise ValueError("SDK iOS package original plan changed before publication")
        publish_regular_tree(candidate, destination / "shard")
    return finalized


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "plan", "destination", "keyring", "keys-directory",
        "developer-directory", "tooling-evidence", "tooling-public-key",
        "java-executable", "repository-root",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--discovery-root", dest="discovery", type=Path, required=True)
    parser.add_argument("--state-root", dest="state", type=Path, required=True)
    parser.add_argument("--expected-build-key", required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--sdk-inputs-artifact-sha256", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--policy-revision", required=True)
    parser.add_argument("--required-trust-domain", choices=("development", "release"), required=True)
    parser.add_argument("--tooling-keyring", type=Path)
    parser.add_argument("--tooling-keys-directory", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    arguments = vars(parser.parse_args(argv))
    if (arguments["tooling_keyring"] is None) != (arguments["tooling_keys_directory"] is None):
        parser.error("Apple tooling keyring and keys directory must be supplied together")
    try:
        with metadata_admission_options(arguments) as admissions:
            apple_policy = arguments.pop("sdk_apple_validation_policy")
            if apple_policy is not None:
                arguments["sdk_apple_validation_policy"] = product_reuse._canonical_control(
                    apple_policy, "Caller Apple validation policy")
            execute(**arguments, environ=os.environ,
                    token=os.environ.get("GITHUB_TOKEN", ""), **admissions)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
