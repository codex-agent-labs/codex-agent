"""Prepare a current-campaign Core consumer request from authenticated originals.

This is caller policy, not hosted execution or validation admission. The
existing Core validation controller still runs the installed consumer and its
complete original replay. Historical package/Contract selection is unsupported
until an independent original policy is supplied for it.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_workflow
from products.inventory import (load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_sha256,
    snapshot_regular_tree, write_canonical_json)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from products.sdk_facade_inputs import _request
from products.sdk_facade_validation_admission import _native_archive_path
from products.sdk_inputs import REQUEST_NAME
from products.signing_isolation import require_no_signing_secret
from sdk_ios_package import _record
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_BINARY = PhaseInstanceId("sdk", "sdk-core", "binary", "common")
_PACKAGE = PhaseInstanceId("sdk", "sdk-core", "package", "common")
_CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


def prepare(plan, discovery, state, destination, *, target, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            native_compiler_archive=None, sdk_validation_tooling=None,
            sdk_apple_validation_policy=None, sdk_facade_metadata_admission=None,
            sdk_android_metadata_admission=None):
    """Write an exact facade request; never read authority from a retained request."""
    require_no_signing_secret(environ)
    if target not in SDK_FACADE_TARGETS:
        raise ValueError("Core validation requires a supported target")
    archive = _native_archive_path(target, native_compiler_archive)
    if archive is not None and target not in ("macos-arm64", "ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Core native validation has no reviewed archive policy for this host")
    require_sha256(expected_build_key, "Core validation elected key")
    require_sha256(sdk_inputs_artifact_sha256, "Original S858 upload digest")
    if type(sdk_inputs_artifact_id) is not int or sdk_inputs_artifact_id < 1:
        raise ValueError("Core validation requires a positive original S858 upload ID")
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state, destination = map(lambda path: Path(path).absolute(),
                                               (plan, discovery, state, destination))
    product_reuse._product_materialization_paths(root, discovery, state,
                                                 root / "build/core-validation-policy-unused")
    if (destination == root or root not in destination.parents or
            destination.resolve(strict=False) != destination or
            destination.exists() or destination.is_symlink()):
        raise ValueError("Core validation policy needs a fresh checkout-owned destination")

    instance = PhaseInstanceId("sdk", "sdk-core", "validation", target)
    policies = sdk_workflow._caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
        sdk_validation_tooling, sdk_original_workflow_sha=trusted_workflow_sha,
        **{name: value for name, value in policies.items() if name != "sdk_validation_tooling"})
    elected = verified.prior_ready_plans.get(instance)
    if elected is None or elected["buildKey"] != expected_build_key:
        raise ValueError("Core validation is not ready with its exact elected key")
    if any(verified.prior_by_instance.get(phase, {}).get("state") != "retained"
           or phase not in verified.sources for phase in (_BINARY, _PACKAGE, _CONTRACT)):
        raise ValueError("Core validation requires same-campaign retained package, binary and Contract")
    evidence = verified.rebased_request.get("contractEvidence")
    if evidence is None or evidence.get("expectedTrustDomain") != "release":
        raise ValueError("Core validation requires selected release Contract evidence")
    before = {path: regular_file_inventory(path, allow_empty=True) for path in (discovery, state)}
    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)

    def unchanged():
        require_no_signing_secret(environ)
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes or
                any(regular_file_inventory(path, allow_empty=True) != inventory
                    for path, inventory in before.items())):
            raise ValueError("Core validation original election changed")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-core-validation-policy-", dir=destination.parent) as scratch:
        prepared = Path(scratch).resolve(strict=True) / "policy"
        prepared.mkdir()
        trust = product_reuse._release_trust(root, verified.plan["validationCommit"], prepared)
        if trust is None:
            raise ValueError("Core validation lacks Git-authoritative release trust")
        predecessors = prepared / "predecessors"
        ready = product_reuse._materialize_product_predecessors(
            verified, instance, predecessors, expected_build_key, root)
        if ready != elected:
            raise ValueError("Core validation predecessor election changed")

        def original(product, component, phase, source_target):
            if (product, component, source_target) != ("contract", "contract", "common"):
                raise ValueError("Core validation requested an unrelated Contract original")
            directory = predecessors / "-".join((product, component, phase, source_target))
            receipt = directory / "phase-receipt.json"
            return _record({"stage": directory / "stage", "receiptPath": receipt,
                "receipt": load_canonical_json_bytes(read_regular_file_bytes(receipt,
                    reject_symlink_parents=True))},
                (product, component, phase, source_target), "Selected Contract original")[0]

        def one_output(record, kind):
            rows = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
            if len(rows) != 1:
                raise ValueError("Core validation requires one original Contract payload")
            return record["stage"] / rows[0]["relativePath"]

        contract, contract_version, handoff, _ = product_reuse._capture_runtime_contract(
            root, evidence, original, one_output, prepared, trust)
        stem = "codex-agent-contract-" + contract_version
        contract_evidence = {
            "stageRoot": str(contract["stage"]), "phaseReceipt": str(contract["receiptPath"]),
            "attestation": str(handoff / (stem + ".attestation.json")),
            "attestationSignature": str(handoff / (stem + ".attestation.sig")),
            "publicKey": str(handoff / "public-key.pub"), "expectedTrustDomain": "release",
            "keyring": str(trust.keyring), "keysDirectory": str(trust.keys),
        }
        package = predecessors / "sdk-sdk-core-package-common"
        binary = predecessors / "sdk-sdk-core-binary-common"
        for phase, path in (("package", package), ("binary", binary)):
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
                path / "phase-receipt.json", reject_symlink_parents=True)))
            manifest = verify_output_manifest_identity(path / "stage", "sdk", "sdk-core", phase,
                                                       "common", receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Core validation predecessor stage differs from its receipt")

        unchanged()
        with sdk_workflow.verified_inputs(plan, discovery, state,
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root, environ=environ,
                token=token, **policies) as sdk_inputs:
            if {"product": "sdk", "component": "sdk-core", "phase": "validation", "target": target} not in \
                    sdk_inputs["selection"]["consumers"]:
                raise ValueError("Original S858 selection does not include Core validation target")
            compatibility = sdk_inputs["sdk"]["compatibility"]
            if (compatibility["sdkVersion"] != verified.expected_fixed["versions"]["sdk"] or
                    compatibility["contract"]["version"] != contract_version or
                    compatibility["runtime"]["defaultRuntimeVersion"] !=
                    verified.expected_fixed["versions"]["runtime-release"]):
                raise ValueError("Original S858 versions differ from selected Core validation products")
            snapshot_regular_tree(sdk_inputs["sdk"]["directory"], prepared / "sdk-inputs")
            unchanged()
        request = {
            "target": target,
            "sdkVersion": verified.expected_fixed["versions"]["sdk"],
            "runtimeVersion": verified.expected_fixed["versions"]["runtime-release"],
            "contractVersion": contract_version, "repository": str(root),
            "packageStage": str(destination / "predecessors/sdk-sdk-core-package-common/stage"),
            "packageReceipt": str(destination / "predecessors/sdk-sdk-core-package-common/phase-receipt.json"),
            "binaryStage": str(destination / "predecessors/sdk-sdk-core-binary-common/stage"),
            "binaryReceipt": str(destination / "predecessors/sdk-sdk-core-binary-common/phase-receipt.json"),
            "compatibilityRequest": str(destination / "sdk-inputs" / REQUEST_NAME),
            "binaryContractEvidence": {**contract_evidence,
                "stageRoot": str(destination / "predecessors/contract-contract-metadata-common/stage"),
                "phaseReceipt": str(destination / "predecessors/contract-contract-metadata-common/phase-receipt.json"),
                "attestation": str(destination / "contract-input" / (stem + ".attestation.json")),
                "attestationSignature": str(destination / "contract-input" / (stem + ".attestation.sig")),
                "publicKey": str(destination / "contract-input/public-key.pub"),
                "keyring": str(destination / "trust/product-signing-keys.json"),
                "keysDirectory": str(destination / "trust/keys")},
        }
        request["validationContractEvidence"] = dict(request["binaryContractEvidence"])
        write_canonical_json(prepared / "facade-request.json", request)
        unchanged()
        publish_regular_tree(prepared, destination)
    unchanged()
    value, _ = _request(destination / "facade-request.json")
    if value != request:
        raise ValueError("Core validation caller request changed during publication")
    return {"facadeRequest": str(destination / "facade-request.json"),
            "nativeCompilerArchive": str(archive) if archive is not None else None,
            "target": target, "buildKey": expected_build_key}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root",
                 "keyring", "keys-directory"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("target", "expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--native-compiler-archive", type=Path)
    parser.add_argument("--sdk-validation-tooling", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    add_metadata_admission_arguments(parser)
    args = vars(parser.parse_args(argv))
    for name, replacement in (("discovery_root", "discovery"), ("state_root", "state")):
        args[replacement] = args.pop(name)
    for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
        if args[name] is not None:
            args[name] = product_reuse._canonical_control(args[name], "Core caller " + name)
    try:
        with metadata_admission_options(args) as admissions:
            prepare(**args, **admissions, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
