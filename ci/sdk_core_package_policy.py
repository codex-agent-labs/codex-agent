"""Prepare independent Core package caller policy.

The caller supplies a current successful upload, or concrete native completion
selects the independently reviewed original. Uploaded invocation data never
grants caller authority. Restore only the Contract bytes needed for full release
verification; the package reader still authenticates the original binary upload.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

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
from products.restore import verification_scoped
from products.sdk_facade_inputs import _EVIDENCE_FIELDS
from products.signing_isolation import require_no_signing_secret
from sdk_maven_original import _context
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options
from reuse_qualification import CompletedFrozenReuse, add_completed_frozen_argument, completed_frozen_options
from sdk_campaign_original_locator import locate_retained_core_binary_upload


_BINARY = PhaseInstanceId("sdk", "sdk-core", "binary", "common")
_PACKAGE = PhaseInstanceId("sdk", "sdk-core", "package", "common")
_CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


@verification_scoped
def prepare(plan, discovery, state, destination, *, expected_build_key,
            binary_artifact_id=None, binary_artifact_sha256=None, binary_original_context=None,
            trusted_workflow_sha, repository_root, environ,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, completed_frozen=None):
    """Write external policy for a current or native-completed original binary."""
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
    supplied = tuple(value is not None for value in
                     (binary_artifact_id, binary_artifact_sha256, binary_original_context))
    if any(supplied) != all(supplied):
        raise ValueError("Core binary upload and original context must be supplied together")
    if not any(supplied) and type(completed_frozen) is not CompletedFrozenReuse:
        raise ValueError("Retained Core binary requires concrete native completion")
    if not isinstance(trusted_workflow_sha, str) or len(trusted_workflow_sha) != 40 or any(
            character not in "0123456789abcdef" for character in trusted_workflow_sha):
        raise ValueError("Core package requires the exact reviewed workflow SHA")
    if all(supplied):
        require_integer(binary_artifact_id, "Current Core binary upload ID", 1)
        require_sha256(binary_artifact_sha256, "Current Core binary upload digest")
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
        requested_scope=(_PACKAGE,),
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
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
    if not any(supplied):
        envelope = completed_frozen.envelope(verified.prior_carrier_phases[_BINARY])
        if envelope is None:
            raise ValueError("Core binary lacks exact native completion")
        origin = locate_retained_core_binary_upload(plan, root,
            expected_build_key=binary["buildKey"], token=environ.get("GITHUB_TOKEN", ""), environ=environ)
        if origin is None or envelope["receipt"]["producer"] != origin["producer"]:
            raise ValueError("Native Core binary differs from its independently reviewed original")
        binary_artifact_id, binary_artifact_sha256 = origin["artifact_id"], origin["artifact_sha256"]
        context = origin["context"]
        _context(context, "binary")
    source = verified.rebased_request.get("contractEvidence")
    if source is None or source["expectedTrustDomain"] != "release":
        raise ValueError("Core package requires the authenticated release Contract")
    source = require_exact_keys(source, _EVIDENCE_FIELDS - {"stageRoot", "phaseReceipt"},
                                "Current Contract release evidence")
    handoff = discovery / "authenticated-contract/contract-input"
    evidence_names = ("attestation", "attestationSignature", "publicKey", "keyring", "keysDirectory")
    if any(source[name] is None for name in evidence_names):
        raise ValueError("Core package requires complete release Contract policy")
    evidence_paths = {name: root / source[name] for name in evidence_names}
    if any(path.resolve(strict=True) != path for path in evidence_paths.values()):
        raise ValueError("Core package Contract evidence paths must be normalized")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-core-package-policy-", dir=destination.parent) as temporary:
        private = Path(temporary).resolve(strict=True)
        prepared = private / "policy"
        prepared.mkdir()
        restored = product_reuse._restore_product_objects(verified, (_CONTRACT,), prepared)[_CONTRACT]
        contract_root = prepared / "contract-contract-metadata-common"
        receipt_path = contract_root / "phase-receipt.json"
        receipt = validate_phase_receipt(load_canonical_json_bytes(restored["receiptBytes"]))
        if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                "contract", "contract", "metadata", "common"):
            raise ValueError("Current Contract object is not metadata")
        manifest = verify_output_manifest_identity(contract_root / "stage", "contract", "contract",
                                                    "metadata", "common", receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError("Current Contract stage differs from its original receipt")
        if (handoff / "contract-manifest.json").exists():
            if type(completed_frozen) is not CompletedFrozenReuse:
                raise ValueError("Deferred Contract requires concrete native completion")
            completed_frozen.verify_contract_handoff(handoff,
                keyring=evidence_paths["keyring"], keys_directory=evidence_paths["keysDirectory"])
            contract_binary = PhaseInstanceId("contract", "contract", "binary", "common")
            binary_predecessors = private / "binary-predecessors"
            binary_predecessors.mkdir()
            product_reuse._restore_product_objects(verified, (contract_binary,), binary_predecessors)

            def original(product, component, phase, target):
                instance = PhaseInstanceId(product, component, phase, target)
                parent = binary_predecessors if phase == "binary" else prepared
                directory = parent / "-".join((product, component, phase, target))
                receipt_path = (directory / "phase-receipt.json" if phase in ("binary", "metadata")
                                else handoff / f"execution-closure/receipts/{phase}.json")
                envelope = completed_frozen.envelope(verified.prior_carrier_phases[instance],
                    read_regular_file_bytes(receipt_path, reject_symlink_parents=True))
                if envelope is None:
                    raise ValueError("Deferred Contract predecessor lacks exact native completion")
                return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": envelope["receipt"]}

            def one_output(record, kind):
                rows = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
                if len(rows) != 1:
                    raise ValueError("Core package requires one original Contract output")
                return record["stage"] / rows[0]["relativePath"]

            _, _, handoff, _, _ = product_reuse._capture_runtime_contract(root, source, original,
                one_output, prepared, SimpleNamespace(keyring=evidence_paths["keyring"], keys=evidence_paths["keysDirectory"]))
            for name in ("attestation", "attestationSignature", "publicKey"):
                evidence_paths[name] = handoff / evidence_paths[name].name
        stem = "codex-agent-contract-" + receipt["productVersion"]
        payload = handoff / (stem + ".zip")
        bundles = [row for row in receipt["outputs"] if row["kind"] == "contract-bundle"]
        if len(bundles) != 1 or sha256_file(contract_root / "stage" / bundles[0]["relativePath"]) != sha256_file(payload):
            raise ValueError("Current Contract metadata differs from its authenticated payload")
        if read_regular_file_bytes(handoff / "execution-closure/receipts/metadata.json") != restored["receiptBytes"]:
            raise ValueError("Current Contract metadata differs from its signed execution closure")
        if handoff != prepared / "contract-input":
            verify_contract_attestation(payload, receipt_path, evidence_paths["attestation"],
                evidence_paths["attestationSignature"], evidence_paths["publicKey"],
                required_trust_domain="release", keyring=evidence_paths["keyring"],
                keys_directory=evidence_paths["keysDirectory"])
        evidence_paths = {name: destination / path.relative_to(prepared) if prepared in path.parents else path
                          for name, path in evidence_paths.items()}
        evidence = {**{name: str(path) for name, path in evidence_paths.items()},
            "stageRoot": str(destination / contract_root.name / "stage"),
            "phaseReceipt": str(destination / contract_root.name / "phase-receipt.json"),
            "expectedTrustDomain": "release"}
        write_canonical_json(prepared / "binary-contract-evidence.json", evidence)
        write_canonical_json(prepared / "binary-original-context.json", context)
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes or
                any(regular_file_inventory(path, allow_empty=True) != before
                    for path, before in source_inventories.items())):
            raise ValueError("Core package current plan or authenticated state changed")
        publish_regular_tree(prepared, destination)
    return {"binary-artifact-id": str(binary_artifact_id), "binary-artifact-sha256": binary_artifact_sha256,
            "binary-contract-evidence": str(destination / "binary-contract-evidence.json"),
            "binary-original-context": str(destination / "binary-original-context.json")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-build-key", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    for name in ("binary-artifact-sha256", "binary-original-context"):
        parser.add_argument("--" + name)
    parser.add_argument("--binary-artifact-id", type=int)
    for name in ("sdk-validation-tooling", "sdk-apple-validation-policy"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--github-output", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
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
        with metadata_admission_options(args) as admissions, completed_frozen_options(args) as native:
            result = prepare(**args, **admissions, **native, environ=os.environ)
        if output is not None:
            with output.open("a", encoding="utf-8") as stream:
                for name, path in result.items():
                    stream.write(name + "=" + path + "\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
