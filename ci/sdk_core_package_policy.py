"""Prepare independent same-campaign Core package caller policy.

The protected caller supplies wave 11's successful official binary upload and
invocation context. Neither fact is recovered from the retained binary object.
This module restores only the authenticated Contract metadata predecessor;
the existing package reader still authenticates and replays the binary upload.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.contract_attestation import verify_contract_attestation
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_file, write_canonical_json,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import restore_object
from products.sdk_facade_inputs import _EVIDENCE_FIELDS
from products.signing_isolation import require_no_signing_secret
from sdk_maven_original import _context
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_BINARY = PhaseInstanceId("sdk", "sdk-core", "binary", "common")
_PACKAGE = PhaseInstanceId("sdk", "sdk-core", "package", "common")
_CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


def prepare(plan, discovery, state, destination, *, expected_build_key,
            binary_artifact_id, binary_artifact_sha256, binary_original_context,
            trusted_workflow_sha, repository_root, environ,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Write external policy for the caller-supplied wave 11 binary upload."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = Path(plan).absolute(), Path(discovery).absolute(), Path(state).absolute()
    destination = Path(destination).absolute()
    if (destination == root or root in destination.parents or
            destination.resolve(strict=False) != destination or
            destination.exists() or destination.is_symlink()):
        raise ValueError("Core package caller policy requires a fresh external destination")
    product_reuse._product_materialization_paths(root, discovery, state, root / "build/core-policy-unused")
    require_sha256(expected_build_key, "Core package elected key")
    require_integer(binary_artifact_id, "Current Core binary upload ID", 1)
    require_sha256(binary_artifact_sha256, "Current Core binary upload digest")
    if not isinstance(trusted_workflow_sha, str) or len(trusted_workflow_sha) != 40 or any(
            character not in "0123456789abcdef" for character in trusted_workflow_sha):
        raise ValueError("Core package requires the exact reviewed workflow SHA")
    if type(binary_original_context) is not str:
        raise ValueError("Core binary original context must be canonical JSON")
    context = json.loads(binary_original_context)
    if canonical_json_bytes(context).decode().strip() != binary_original_context:
        raise ValueError("Core binary original context is not canonical")
    _context(context, "binary")

    source_inventories = {path: regular_file_inventory(path, allow_empty=True)
                          for path in (discovery, state)}
    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)
    verified = product_reuse._verified_product_state(
        plan, discovery, state, root, environ, sdk_validation_tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy}
           if sdk_apple_validation_policy is not None else {}),
        **({"sdk_facade_metadata_admission": sdk_facade_metadata_admission}
           if sdk_facade_metadata_admission is not None else {}),
        **({"sdk_android_metadata_admission": sdk_android_metadata_admission}
           if sdk_android_metadata_admission is not None else {}),
    )
    ready = verified.prior_ready_plans.get(_PACKAGE)
    binary = verified.prior_by_instance.get(_BINARY)
    if (ready is None or ready["buildKey"] != expected_build_key or
            binary is None or binary["state"] != "retained" or
            _BINARY not in verified.sources or _CONTRACT not in verified.sources or
            _CONTRACT not in verified.prior_carrier_phases):
        raise ValueError("Core package requires a retained binary and authenticated Contract")
    source = verified.rebased_request.get("contractEvidence")
    if source is None or source["expectedTrustDomain"] != "release":
        raise ValueError("Core package requires the authenticated release Contract")
    source = require_exact_keys(source, _EVIDENCE_FIELDS - {"stageRoot", "phaseReceipt"},
                                "Current Contract release evidence")
    handoff = discovery / "authenticated-contract/contract-input"
    evidence_paths = {name: root / source[name] for name in
                      ("attestation", "attestationSignature", "publicKey", "keyring", "keysDirectory")}
    if any(source[name] is None for name in evidence_paths):
        raise ValueError("Core package requires complete release Contract policy")
    if any(path.resolve(strict=True) != path for path in evidence_paths.values()):
        raise ValueError("Core package Contract evidence paths must be normalized")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-core-package-policy-", dir=destination.parent) as temporary:
        private = Path(temporary).resolve(strict=True)
        prepared = private / "policy"
        prepared.mkdir()
        contract_root = prepared / "contract-metadata"
        contract_root.mkdir()
        carrier = verified.prior_carrier_phases[_CONTRACT]
        restored = restore_object(
            verified.sources[_CONTRACT], contract_root / "stage",
            build_key=carrier["buildKey"], receipt_sha256=carrier["receiptSha256"],
            object_sha256=carrier["objectSha256"],
        )
        receipt_path = contract_root / "phase-receipt.json"
        receipt_path.write_bytes(restored["receiptBytes"])
        receipt = validate_phase_receipt(load_canonical_json_bytes(restored["receiptBytes"]))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                "contract", "contract", "metadata", "common"):
            raise ValueError("Current Contract object is not metadata")
        manifest = verify_output_manifest_identity(contract_root / "stage", "contract", "contract",
                                                    "metadata", "common", receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("Current Contract stage differs from its original receipt")
        stem = "codex-agent-contract-" + receipt["productVersion"]
        payload = handoff / (stem + ".zip")
        bundles = [row for row in receipt["outputs"] if row["kind"] == "contract-bundle"]
        if len(bundles) != 1 or sha256_file(contract_root / "stage" / bundles[0]["relativePath"]) != sha256_file(payload):
            raise ValueError("Current Contract metadata differs from its authenticated payload")
        if read_regular_file_bytes(handoff / "execution-closure/receipts/metadata.json") != restored["receiptBytes"]:
            raise ValueError("Current Contract metadata differs from its signed execution closure")
        verify_contract_attestation(payload, receipt_path, evidence_paths["attestation"],
            evidence_paths["attestationSignature"], evidence_paths["publicKey"],
            required_trust_domain="release", keyring=evidence_paths["keyring"],
            keys_directory=evidence_paths["keysDirectory"])
        evidence = {**{name: str(path) for name, path in evidence_paths.items()},
            "stageRoot": str(destination / "contract-metadata/stage"),
            "phaseReceipt": str(destination / "contract-metadata/phase-receipt.json"),
            "expectedTrustDomain": "release"}
        write_canonical_json(prepared / "binary-contract-evidence.json", evidence)
        write_canonical_json(prepared / "binary-original-context.json", context)
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes or
                any(regular_file_inventory(path, allow_empty=True) != before
                    for path, before in source_inventories.items())):
            raise ValueError("Core package current plan or authenticated state changed")
        publish_regular_tree(prepared, destination)
    return {"binary-contract-evidence": str(destination / "binary-contract-evidence.json"),
            "binary-original-context": str(destination / "binary-original-context.json")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-build-key", "binary-artifact-sha256", "binary-original-context",
                 "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--binary-artifact-id", type=int, required=True)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--github-output", type=Path)
    add_metadata_admission_arguments(parser)
    args = vars(parser.parse_args(argv))
    args["plan"] = args.pop("plan")
    args["discovery"] = args.pop("discovery_root")
    args["state"] = args.pop("state_root")
    output = args.pop("github_output")
    for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
        path = args[name]
        if path is not None:
            args[name] = product_reuse._canonical_control(path, "Caller " + name)
    try:
        with metadata_admission_options(args) as admissions:
            result = prepare(**args, **admissions, environ=os.environ)
        if output is not None:
            with output.open("a", encoding="utf-8") as stream:
                for name, path in result.items():
                    stream.write(name + "=" + path + "\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
