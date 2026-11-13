"""Prepare independently authenticated inputs for one Android validation worker.

This is caller policy, not Firebase execution or product admission. Historical
package/binary reuse stays fail-closed until it has separate original policy.
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
from impact import effective_pathspecs, inventory
from receipt import INPUT_NAMES
from products.inventory import (load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_sha256, canonical_json_bytes,
    snapshot_regular_tree, write_canonical_json, run_git)
from products.receipt import validate_phase_receipt, verify_output_manifest_identity
from products.registry import PhaseInstanceId
from products.restore import verification_scoped
from products.sdk_facade_inputs import _EVIDENCE_FIELDS
from products.sdk_inputs import REQUEST_NAME
from products.signing_isolation import require_no_signing_secret
from sdk_ios_package import _record
from sdk_phase import maven_consumed_predecessors
from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options


_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")
_PACKAGE = PhaseInstanceId("sdk", "sdk-android", "package", "android")
_VALIDATION = PhaseInstanceId("sdk", "sdk-android", "validation", "android")
_CONTRACT = PhaseInstanceId("contract", "contract", "metadata", "common")


def _stage_android_plan(root, plan, revision, destination):
    """Project only Android controls from authenticated Git, not a bulk plan download."""
    def source_unchanged():
        if run_git(root, "rev-parse", "HEAD").strip() != revision:
            raise ValueError("Android plan projection differs from its authenticated candidate")
        run_git(root, "diff", "--quiet", "HEAD", "--")

    source_unchanged()
    raw = read_regular_file_bytes(plan, reject_symlink_parents=True)
    destination.mkdir()
    (destination / "impact-plan.json").write_bytes(raw)
    target = destination / "inventories/android"
    target.mkdir(parents=True)
    for category, name in INPUT_NAMES.items():
        contents = inventory(root, revision, effective_pathspecs(root, "android", category)).encode("utf-8")
        original = plan.parent / "inventories/android" / name
        if (original.exists() or original.is_symlink()) and read_regular_file_bytes(
                original, reject_symlink_parents=True) != contents:
            raise ValueError("Android planned inventory differs from its authenticated Git inputs")
        (target / name).write_bytes(contents)
    source_unchanged()
    if read_regular_file_bytes(plan, reject_symlink_parents=True) != raw:
        raise ValueError("Android plan changed during projection")


@verification_scoped
def prepare(plan, discovery, state, destination, *, expected_build_key,
            sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
            keyring, keys_directory, repository_root, environ, token,
            sdk_validation_tooling, sdk_apple_validation_policy=None,
            sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None, retained_sdk_inputs_source=None,
            completed_frozen=None, phase="validation"):
    """Stage exact elected predecessors, release Contract and original S858 input."""
    require_no_signing_secret(environ)
    if phase not in ("validation", "metadata"):
        raise ValueError("Android caller policy requires validation or metadata")
    instance = PhaseInstanceId("sdk", "sdk-android", phase, "android")
    require_sha256(expected_build_key, "Android validation elected key")
    require_sha256(sdk_inputs_artifact_sha256, "Original S858 upload digest")
    if type(sdk_inputs_artifact_id) is not int or sdk_inputs_artifact_id < 1:
        raise ValueError("Android validation requires a positive original S858 upload ID")
    if sdk_validation_tooling is None:
        raise ValueError("Android validation requires caller-owned signed tooling policy")
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state, destination = map(lambda path: Path(path).absolute(),
                                               (plan, discovery, state, destination))
    product_reuse._product_materialization_paths(root, discovery, state,
                                                 root / "build/android-validation-policy-unused")
    tooling_sources = tuple(Path(sdk_validation_tooling[name]).absolute() for name in
        ("evidence", "publicKey", "javaExecutable", "keyring", "keysDirectory")
        if type(sdk_validation_tooling.get(name)) is str)
    sources = (plan, discovery, state, Path(keyring).absolute(),
               Path(keys_directory).absolute(), *tooling_sources)
    if (destination.resolve(strict=False) != destination or destination.exists()
            or destination.is_symlink() or destination == root
            or destination in root.parents
            or any(destination == source or destination in source.parents
                   or source in destination.parents for source in sources)):
        raise ValueError("Android validation policy needs a fresh, separate destination")
    policies = sdk_workflow._caller_policies(sdk_validation_tooling, sdk_apple_validation_policy,
        sdk_facade_metadata_admission=sdk_facade_metadata_admission,
        sdk_android_metadata_admission=sdk_android_metadata_admission)
    verified = product_reuse._verified_product_state(plan, discovery, state, root, environ,
        sdk_validation_tooling, requested_scope=(instance,), sdk_original_workflow_sha=trusted_workflow_sha,
        **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
        **{name: value for name, value in policies.items() if name != "sdk_validation_tooling"})
    elected = verified.prior_ready_plans.get(instance)
    if elected is None or elected["buildKey"] != expected_build_key:
        raise ValueError(f"Android {phase} is not ready with its exact elected key")
    if any(verified.prior_by_instance.get(phase, {}).get("state") != "retained"
           or phase not in verified.sources for phase in (_BINARY, _PACKAGE, _CONTRACT)):
        raise ValueError("Android validation requires same-campaign retained package, binary and Contract")
    evidence = verified.rebased_request.get("contractEvidence")
    if evidence is None or evidence.get("expectedTrustDomain") != "release":
        raise ValueError("Android validation requires selected release Contract evidence")
    before = {path: regular_file_inventory(path, allow_empty=True) for path in (discovery, state)}
    plan_bytes = read_regular_file_bytes(plan, reject_symlink_parents=True)

    def unchanged():
        require_no_signing_secret(environ)
        if (read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes or
                any(regular_file_inventory(path, allow_empty=True) != inventory
                    for path, inventory in before.items())):
            raise ValueError("Android validation original election changed")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sdk-android-validation-policy-", dir=root) as scratch:
        prepared = Path(scratch).resolve(strict=True) / "policy"
        prepared.mkdir()
        trust = product_reuse._release_trust(root, verified.plan["validationCommit"], prepared)
        if trust is None:
            raise ValueError("Android validation lacks Git-authoritative release trust")
        predecessors = prepared / "predecessors"
        if product_reuse._materialize_product_predecessors(
                verified, instance, predecessors, expected_build_key, root,
                materialized_scope=maven_consumed_predecessors(_VALIDATION)) != elected:
            raise ValueError("Android validation predecessor election changed")

        def original(product, component, phase, target):
            if ((product, component, target) != ("contract", "contract", "common") or
                    phase not in ("binary", "package", "validation", "metadata")):
                raise ValueError("Android validation requested an unrelated Contract original")
            directory = predecessors / "-".join((product, component, phase, target))
            receipt = directory / "phase-receipt.json"
            return _record({"stage": directory / "stage", "receiptPath": receipt,
                "receipt": load_canonical_json_bytes(read_regular_file_bytes(receipt,
                    reject_symlink_parents=True))},
                (product, component, phase, target), "Selected Contract original")[0]

        def one_output(record, kind):
            rows = [row for row in record["receipt"]["outputs"] if row["kind"] == kind]
            if len(rows) != 1:
                raise ValueError("Android validation requires one original Contract payload")
            return record["stage"] / rows[0]["relativePath"]

        _, contract_version, _, _, _ = product_reuse._capture_runtime_contract(
            root, evidence, original, one_output, prepared, trust)
        stem = "codex-agent-contract-" + contract_version
        contract_evidence = {
            "stageRoot": str(destination / "predecessors/contract-contract-metadata-common/stage"),
            "phaseReceipt": str(destination / "predecessors/contract-contract-metadata-common/phase-receipt.json"),
            "attestation": str(destination / "contract-input" / (stem + ".attestation.json")),
            "attestationSignature": str(destination / "contract-input" / (stem + ".attestation.sig")),
            "publicKey": str(destination / "contract-input/public-key.pub"),
            "expectedTrustDomain": "release",
            "keyring": str(destination / "trust/product-signing-keys.json"),
            "keysDirectory": str(destination / "trust/keys"),
        }
        if set(contract_evidence) != _EVIDENCE_FIELDS:
            raise ValueError("Android validation Contract evidence fields changed")
        for predecessor_phase in ("binary", "package"):
            directory = predecessors / f"sdk-sdk-android-{predecessor_phase}-android"
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
                directory / "phase-receipt.json", reject_symlink_parents=True)))
            if tuple(receipt[name] for name in ("product", "component", "phase", "target")) != (
                    "sdk", "sdk-android", predecessor_phase, "android"):
                raise ValueError("Android validation predecessor receipt has the wrong phase identity")
            manifest = verify_output_manifest_identity(directory / "stage", "sdk", "sdk-android",
                                                       predecessor_phase, "android", receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Android validation predecessor stage differs from its receipt")
        unchanged()
        with sdk_workflow.verified_inputs(plan, discovery, state,
                requested_scope=(instance,),
                artifact_id=sdk_inputs_artifact_id, artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory, repository_root=root, environ=environ,
                token=token, **policies,
                **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}),
                **({"retained_sdk_inputs_source": retained_sdk_inputs_source} if retained_sdk_inputs_source is not None else {})) as sdk_inputs:
            if {"product": "sdk", "component": "sdk-android", "phase": phase, "target": "android"} \
                    not in sdk_inputs["selection"]["consumers"]:
                raise ValueError(f"Original S858 selection does not include Android {phase}")
            compatibility = sdk_inputs["sdk"]["compatibility"]
            if (compatibility["sdkVersion"] != verified.expected_fixed["versions"]["sdk"] or
                    compatibility["contract"]["version"] != contract_version or
                    compatibility["runtime"]["defaultRuntimeVersion"] !=
                    verified.expected_fixed["versions"]["runtime-release"]):
                raise ValueError("Original S858 versions differ from selected Android validation products")
            snapshot_regular_tree(sdk_inputs["sdk"]["directory"], prepared / "sdk-inputs")
            unchanged()
        write_canonical_json(prepared / "binary-contract-evidence.json", contract_evidence)
        _stage_android_plan(root, plan, verified.plan["validationCommit"], prepared / "plan")
        unchanged()
        candidate = regular_file_inventory(prepared, allow_empty=True)
        empty_inventories = {"plan/inventories/android/" + name for name in INPUT_NAMES.values()}
        if any(row["bytes"] == 0 and row["relativePath"] not in empty_inventories for row in candidate):
            raise ValueError("Only verified Android lane inventories may be empty")
        publish_regular_tree(prepared, destination, expected_inventory=candidate, allow_empty=True)
        if regular_file_inventory(destination, allow_empty=True) != candidate:
            raise ValueError("Android validation caller policy differs from its private candidate")
    unchanged()
    return {
        "plan-path": str(destination / "plan/impact-plan.json"),
        "packageStage": str(destination / "predecessors/sdk-sdk-android-package-android/stage"),
        "packageReceipt": str(destination / "predecessors/sdk-sdk-android-package-android/phase-receipt.json"),
        "binaryStage": str(destination / "predecessors/sdk-sdk-android-binary-android/stage"),
        "binaryReceipt": str(destination / "predecessors/sdk-sdk-android-binary-android/phase-receipt.json"),
        "compatibilityRequest": str(destination / "sdk-inputs" / REQUEST_NAME),
        "binaryContractEvidence": str(destination / "binary-contract-evidence.json"),
    }


def main(argv=None):
    from reuse_qualification import add_completed_frozen_argument, completed_frozen_options
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "repository-root",
                 "keyring", "keys-directory", "sdk-validation-tooling"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("discovery-root", "state-root", "capture-destination"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--capture-artifact-id", type=int)
    parser.add_argument("--capture-artifact-sha256")
    parser.add_argument("--capture-state-wave", type=int, choices=range(6))
    parser.add_argument("--capture-sdk-state-wave", type=int, choices=range(1, 20))
    for name in ("expected-build-key", "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--sdk-inputs-artifact-id", type=int, required=True)
    parser.add_argument("--phase", choices=("validation", "metadata"), default="validation")
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--github-output", type=Path)
    add_metadata_admission_arguments(parser)
    add_completed_frozen_argument(parser)
    parser.add_argument("--retained-sdk-inputs-source", type=Path, default=argparse.SUPPRESS)
    args = vars(parser.parse_args(argv))
    args["discovery"] = args.pop("discovery_root")
    args["state"] = args.pop("state_root")
    output = args.pop("github_output")
    for name in ("sdk_validation_tooling", "sdk_apple_validation_policy"):
        if args[name] is not None:
            args[name] = product_reuse._canonical_control(args[name], "Android caller " + name)
    incoming = {name: args.pop("capture_" + name) for name in
                ("destination", "artifact_id", "artifact_sha256", "state_wave", "sdk_state_wave")}
    combined = any(value is not None for value in incoming.values())
    try:
        if combined:
            if (args["phase"] != "validation" or args["discovery"] is not None or args["state"] is not None
                    or any(incoming[name] is None for name in ("destination", "artifact_id", "artifact_sha256"))):
                raise ValueError("Android validation requires complete capture controls or existing state roots")
            runner_output = os.environ.get("GITHUB_OUTPUT")
            if output is None or not runner_output or Path(runner_output).absolute() != output.absolute():
                raise ValueError("Android capture output must be the runner-provided GITHUB_OUTPUT")
            capture, publication = incoming["destination"].resolve(), args["destination"].resolve()
            if capture == publication or capture in publication.parents or publication in capture.parents:
                raise ValueError("Android capture and publication destinations overlap")
            incoming["state_wave"] = incoming["state_wave"] or 0
        elif args["discovery"] is None or args["state"] is None:
            raise ValueError("Android policy requires both existing state roots")
        if "retained_sdk_inputs_source" in args:
            args["retained_sdk_inputs_source"] = product_reuse._canonical_control(
                args["retained_sdk_inputs_source"], "Caller retained SDK input source")
        with metadata_admission_options(args) as admissions, completed_frozen_options(args) as semantic:
            result = {}
            if combined:
                paths = sdk_workflow.capture(args["plan"], github_output_path=None, **incoming,
                    family="android-validation", repository_root=args["repository_root"],
                    trusted_workflow_sha=args["trusted_workflow_sha"],
                    sdk_validation_tooling=args["sdk_validation_tooling"],
                    sdk_apple_validation_policy=args["sdk_apple_validation_policy"],
                    **admissions, **semantic, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
                args.update(plan=paths["plan_path"], discovery=paths["discovery_root"], state=paths["state_root"])
                result.update({name: str(paths[name]) for name in
                               ("input_root", "plan_path", "discovery_root", "state_root")})
                result.update(sdk_matrix=canonical_json_bytes(paths["matrix"]).decode().strip(),
                              sdk_workers_required="true" if paths["matrix"]["include"] else "false")
            result.update(prepare(**args, **admissions, **semantic, environ=os.environ, token=os.environ["GITHUB_TOKEN"]))
        if output is None:
            for name, value in result.items():
                print(name + "=" + value)
        else:
            with output.open("a", encoding="utf-8") as stream:
                for name, value in result.items():
                    stream.write(name + "=" + value + "\n")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
