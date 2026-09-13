"""Compose the existing authenticated inputs, iOS package worker and full gate."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.contract_projection import verify_contract_component_projection
from products.inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
)
from products.registry import PhaseInstanceId
from products.restore import PHASE_RECEIPT_NAME, verify_phase_shard
from products.sdk_inputs import COMPATIBILITY_NAME, REQUEST_NAME
from products.sdk_package import verify_sdk_package_inputs
from sdk_apple_native import verified_sdk_apple_native_inputs
from sdk_apple_source import capture_sdk_apple_original_ci
from sdk_ios_package import execute as execute_package


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_DISTRIBUTION = Path("lane/payload/codex-agent-runtime-ios/build/apple-verified-distribution")


def execute(
    plan: Path, discovery: Path, state: Path, destination: Path, *,
    expected_build_key: str,
    sdk_inputs_artifact_id: int, sdk_inputs_artifact_sha256: str,
    apple_artifact_id: int, apple_artifact_sha256: str,
    native_uploads: dict, trusted_workflow_sha: str,
    keyring: Path, keys_directory: Path, expected_distribution_proof: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, repository_root: Path, environ: dict, token: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> dict:
    """Build and admit one elected package; publish only after all contexts close."""
    root = Path(repository_root).resolve(strict=True)
    discovery, state, destination = product_reuse._product_materialization_paths(
        root, discovery, state, destination,
    )
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK iOS package destination must not exist")

    with tempfile.TemporaryDirectory(prefix="sdk-ios-package-candidate-") as temporary:
        candidate = Path(temporary).resolve() / "shard"
        with sdk_workflow.verified_inputs(
            plan, discovery, state, artifact_id=sdk_inputs_artifact_id,
            artifact_sha256=sdk_inputs_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
            keys_directory=keys_directory, repository_root=root,
            environ=environ, token=token,
        ) as sdk_inputs:
            selection = sdk_inputs["selection"]
            selected = {"product": "sdk", "component": "sdk-ios", "phase": "package", "target": "ios"}
            if selected not in selection["consumers"]:
                raise ValueError("SDK iOS package is not selected")
            prepared = destination / "inputs"
            ready = product_reuse.materialize_product_predecessors(
                plan, discovery, state, _INSTANCE, prepared,
                expected_build_key=expected_build_key,
                repository_root=root, environ=environ,
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
            projection = verify_contract_component_projection(
                contract_metadata["stage"], contract_metadata["receiptPath"],
                arguments["contract_attestation"], arguments["contract_attestation_signature"],
                arguments["contract_public_key"], expected_trust_domain=arguments["required_trust_domain"],
                expected_contract_version=contract_metadata["receipt"]["productVersion"],
                required_components=("ios-arm64", "ios-simulator-arm64"),
                keyring=arguments["contract_keyring"], keys_directory=arguments["contract_keys_directory"],
            )
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package predecessors changed during Contract verification")
            compatibility = sdk_inputs["sdk"]["directory"] / COMPATIBILITY_NAME
            apple_source = destination / "apple-source"
            capture_sdk_apple_original_ci(
                plan, apple_source, artifact_id=apple_artifact_id,
                artifact_sha256=apple_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha,
                contract_bundle=arguments["contract_payload"], contract_projection=projection,
                expected_distribution_proof=expected_distribution_proof,
                expected_sdk_compatibility=compatibility,
                tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
                java_executable=java_executable, policy_revision=policy_revision,
                required_trust_domain=arguments["required_trust_domain"],
                repository_root=root, environ=environ, token=token,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
            )
            apple_inventory = regular_file_inventory(apple_source, allow_empty=True)
            if regular_file_inventory(prepared, allow_empty=True) != prepared_inventory:
                raise ValueError("SDK iOS package predecessors changed during Apple source verification")

            with verified_sdk_apple_native_inputs(
                plan, uploads=native_uploads, trusted_workflow_sha=trusted_workflow_sha,
                repository_root=root, environ=environ, token=token,
            ) as native:
                if native["producer"] != producer:
                    raise ValueError("SDK iOS native evidence differs from the elected producer")
                result = execute_package(
                    ready, producer=producer, sdk_version=selection["sdkVersion"],
                    current_contract=contract_binary, sdk_binary=sdk_binary,
                    verified_distribution=apple_source / _DISTRIBUTION,
                    native_evidence=native["directory"],
                    compatibility_request=sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                    expected_sdk_compatibility=compatibility,
                    expected_distribution_proof=expected_distribution_proof,
                    repository_root=root, destination=destination / "worker", environ=environ,
                )
                if (regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                        or regular_file_inventory(apple_source, allow_empty=True) != apple_inventory):
                    raise ValueError("SDK iOS package authenticated inputs changed during execution")
                trust = "development" if producer["event"] == "pull_request" else "release"
                finalized = product_reuse.finalize_phase_object(
                    stage_root=result["stage"], phase_plan=ready, producer=producer,
                    product_version=selection["sdkVersion"], trust_domain=trust,
                    destination=candidate,
                )
                apple_verification = {
                    "validation_evidence_directory": result["validationEvidence"],
                    "expected_sdk_compatibility": compatibility,
                    "expected_distribution_proof": Path(expected_distribution_proof),
                    "repository": root,
                    "tooling_evidence": Path(tooling_evidence),
                    "tooling_public_key": Path(tooling_public_key),
                    "java_executable": Path(java_executable),
                    "policy_revision": policy_revision,
                    "required_trust_domain": arguments["required_trust_domain"],
                    "tooling_keyring": tooling_keyring,
                    "tooling_keys_directory": tooling_keys_directory,
                }
                verified, raw = verify_sdk_package_inputs(
                    root, result["stage"], candidate / PHASE_RECEIPT_NAME,
                    sdk_inputs["sdk"]["directory"] / REQUEST_NAME,
                    binary_stage_root=sdk_binary["stage"],
                    binary_receipt_path=sdk_binary["receiptPath"],
                    binary_contract_evidence=contract_evidence,
                    apple_verification=apple_verification,
                )
                if (verified != finalized["receipt"] or raw != read_regular_file_bytes(
                        candidate / PHASE_RECEIPT_NAME)):
                    raise ValueError("SDK iOS package gate returned a different candidate receipt")
                candidate_inventory = regular_file_inventory(candidate)
            if (regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                    or regular_file_inventory(apple_source, allow_empty=True) != apple_inventory):
                raise ValueError("SDK iOS package authenticated inputs changed before publication")
        if (regular_file_inventory(prepared, allow_empty=True) != prepared_inventory
                or regular_file_inventory(apple_source, allow_empty=True) != apple_inventory):
            raise ValueError("SDK iOS package authenticated inputs changed after SDK verification")
        if (regular_file_inventory(result["stage"], allow_empty=True) != result["outputInventory"]
                or regular_file_inventory(result["validationEvidence"], allow_empty=True)
                != result["validationEvidenceInventory"]
                or regular_file_inventory(candidate) != candidate_inventory
                or verify_phase_shard(candidate, _INSTANCE) != finalized):
            raise ValueError("SDK iOS package candidate changed after admission")
        publish_regular_tree(candidate, destination / "shard")
    return verify_phase_shard(destination / "shard", _INSTANCE)
