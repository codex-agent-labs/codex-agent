"""Prepare independent same-campaign Android package caller policy.

The protected caller supplies wave 15's successful official binary upload,
original invocation context and Codex archive. Retained binary bytes supply
none of those authorities; the package reader still replays the upload.
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
    canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_semver, require_sha256,
    sha256_file, write_canonical_json,
)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import restore_object
from products.sdk_facade_inputs import _EVIDENCE_FIELDS
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties
from sdk_maven_original import _context
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")
_PACKAGE = PhaseInstanceId("sdk", "sdk-android", "package", "android")
_CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


def prepare(plan, discovery, state, destination, *, expected_build_key,
            binary_artifact_id, binary_artifact_sha256, binary_original_context,
            android_runtime_archive, trusted_workflow_sha, repository_root, environ,
            sdk_validation_tooling=None, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None):
    """Write external Contract/context policy for the caller's wave 15 upload."""
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = Path(plan).absolute(), Path(discovery).absolute(), Path(state).absolute()
    destination = Path(destination).absolute()
    archive = Path(android_runtime_archive)
    if (destination == root or root in destination.parents or
            destination.resolve(strict=False) != destination or
            destination.exists() or destination.is_symlink()):
        raise ValueError("Android package caller policy requires a fresh external destination")
    product_reuse._product_materialization_paths(root, discovery, state, root / "build/android-policy-unused")
    if (not archive.is_absolute() or archive.resolve(strict=True) != archive or
            archive == root or root in archive.parents or
            archive == destination or destination in archive.parents):
        raise ValueError("Android package archive must be a separate normalized caller file")
    require_sha256(expected_build_key, "Android package elected key")
    require_integer(binary_artifact_id, "Current Android binary upload ID", 1)
    require_sha256(binary_artifact_sha256, "Current Android binary upload digest")
    if (not isinstance(trusted_workflow_sha, str) or len(trusted_workflow_sha) != 40 or
            any(character not in "0123456789abcdef" for character in trusted_workflow_sha)):
        raise ValueError("Android package requires the exact reviewed workflow SHA")
    if type(binary_original_context) is not str:
        raise ValueError("Android binary original context must be canonical JSON")
    context = json.loads(binary_original_context)
    if canonical_json_bytes(context).decode().strip() != binary_original_context:
        raise ValueError("Android binary original context is not canonical")
    _context(context, "binary")
    if context["repositoryRoot"] != str(root) or context["workerRoot"] != str(root / "build/sdk-android-maven-worker"):
        raise ValueError("Android binary context differs from this same-campaign worker")

    source_inventories = {path: regular_file_inventory(path, allow_empty=True)
                          for path in (discovery, state)}
    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)
    archive_digest = sha256_file(archive, reject_symlink_parents=True)
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
        raise ValueError("Android package requires a retained binary and authenticated Contract")
    properties = _properties(git_regular_blob_bytes(root, verified.plan["validationCommit"],
        "gradle.properties", max_bytes=1024 * 1024), "Original Android runtime pins")
    require_semver(properties["codexAgent.codexVersion"], "Original Android runtime version")
    if archive_digest != require_sha256("sha256:" + properties["codexAgent.codexArchiveSha256"],
            "Original Android archive pin"):
        raise ValueError("Android package archive differs from immutable candidate Git pin")
    source = verified.rebased_request.get("contractEvidence")
    if source is None or source["expectedTrustDomain"] != "release":
        raise ValueError("Android package requires the authenticated release Contract")
    source = require_exact_keys(source, _EVIDENCE_FIELDS - {"stageRoot", "phaseReceipt"},
                                "Current Contract release evidence")
    handoff = discovery / "authenticated-contract/contract-input"
    evidence_paths = {name: root / source[name] for name in
                      ("attestation", "attestationSignature", "publicKey", "keyring", "keysDirectory")}
    if any(source[name] is None for name in evidence_paths):
        raise ValueError("Android package requires complete release Contract policy")
    if any(path.resolve(strict=True) != path for path in evidence_paths.values()):
        raise ValueError("Android package Contract evidence paths must be normalized")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-android-package-policy-", dir=destination.parent) as temporary:
        prepared = Path(temporary).resolve(strict=True) / "policy"
        prepared.mkdir()
        contract_root = prepared / "contract-metadata"
        contract_root.mkdir()
        carrier = verified.prior_carrier_phases[_CONTRACT]
        restored = restore_object(verified.sources[_CONTRACT], contract_root / "stage",
            build_key=carrier["buildKey"], receipt_sha256=carrier["receiptSha256"],
            object_sha256=carrier["objectSha256"])
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
                sha256_file(archive, reject_symlink_parents=True) != archive_digest or
                any(regular_file_inventory(path, allow_empty=True) != before
                    for path, before in source_inventories.items())):
            raise ValueError("Android package caller inputs or authenticated state changed")
        publish_regular_tree(prepared, destination)
    return {"binary-contract-evidence": str(destination / "binary-contract-evidence.json"),
            "binary-original-context": str(destination / "binary-original-context.json"),
            "android-runtime-archive": str(archive)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery-root", "state-root", "destination", "repository-root",
                 "android-runtime-archive"):
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
