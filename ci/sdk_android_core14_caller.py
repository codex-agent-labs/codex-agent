"""Hold independently authenticated Core wave 14 for Android waves 15–16.

The caller owns both original SDK state transports and the Core receipt/policy.
Nothing from the temporary Core descriptor is exported to another process.
"""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_maven_binary_workflow
import sdk_maven_package_workflow
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_integer, require_sha256, sha256_file)
from products.registry import PhaseInstanceId
from products.sdk_facade_metadata_admission import FacadeMetadataAdmission
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties
from reuse import github_output
from sdk_core_metadata_same_campaign import held_same_campaign_core_metadata_policy


_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")
_PACKAGE = PhaseInstanceId("sdk", "sdk-android", "package", "android")


def with_core14(plan, discovery, before_state, after_state, metadata_receipt,
        *, expected_build_key, expected_metadata_build_key, expected_metadata_receipt_sha256,
        replay_policy, original_context, trusted_workflow_sha, repository_root,
        android_runtime_archive, token, environ=None, destination=None,
        sdk_apple_validation_policy=None, phase="binary", selected_state=None,
        sdk_inputs_artifact_id=None, sdk_inputs_artifact_sha256=None,
        binary_artifact_id=None, binary_artifact_sha256=None,
        binary_contract_evidence=None, binary_original_context=None,
        keyring=None, keys_directory=None):
    """Preflight or execute an Android Maven phase under one live Core admission.

    ``destination=None`` performs the pre-setup check. A destination executes
    the existing Android binary or package controller. Both calls independently replay
    Core's official original upload and all eleven validation originals.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    root = Path(repository_root).resolve(strict=True)
    archive = Path(android_runtime_archive)
    if not archive.is_absolute() or archive.resolve(strict=True) != archive:
        raise ValueError("Android archive must be an independent normalized file")
    if phase not in ("binary", "package"):
        raise ValueError("Android Core14 caller requires binary or package")
    if phase == "binary" and selected_state is not None:
        raise ValueError("Android binary must elect directly from Core wave 14")
    if phase == "package" and selected_state is None:
        raise ValueError("Android package requires its separate wave 15 state")
    package_inputs = (sdk_inputs_artifact_id, sdk_inputs_artifact_sha256,
        binary_artifact_id, binary_artifact_sha256, binary_contract_evidence,
        binary_original_context, keyring, keys_directory)
    if (phase == "binary" and any(value is not None for value in package_inputs)) or (
            phase == "package" and any(value is None for value in package_inputs)):
        raise ValueError("Android package requires all independent S858 and binary inputs")
    if phase == "package":
        require_integer(sdk_inputs_artifact_id, "Android package S858 upload ID", 1)
        require_sha256(sdk_inputs_artifact_sha256, "Android package S858 upload digest")
        require_integer(binary_artifact_id, "Android package original binary upload ID", 1)
        require_sha256(binary_artifact_sha256, "Android package original binary upload digest")
    require_sha256(expected_build_key, "Android Maven build key")
    phase_state = after_state if selected_state is None else selected_state
    with held_same_campaign_core_metadata_policy(
            plan, discovery, before_state, after_state, metadata_receipt,
            expected_build_key=expected_metadata_build_key,
            expected_receipt_sha256=expected_metadata_receipt_sha256,
            replay_policy=replay_policy, original_context=original_context,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
            environ=environment, token=token,
            sdk_apple_validation_policy=sdk_apple_validation_policy) as descriptor:
        selected = load_canonical_json_bytes(read_regular_file_bytes(
            descriptor, reject_symlink_parents=True))
        admission = FacadeMetadataAdmission(selected["evidenceRoot"], selected["records"],
            repository=root, policy_revision=product_reuse._validate_plan(plan, root)["validationCommit"],
            policy=selected["policy"])
        tooling = {"evidence": selected["policy"]["toolingEvidence"],
            "publicKey": selected["policy"]["toolingPublicKey"],
            "javaExecutable": selected["policy"]["javaExecutable"],
            "requiredTrustDomain": selected["policy"]["toolingTrustDomain"],
            "keyring": selected["policy"]["toolingKeyring"],
            "keysDirectory": selected["policy"]["toolingKeysDirectory"]}
        verified = product_reuse._verified_product_state(plan, discovery, phase_state,
            root, environment, tooling, sdk_original_workflow_sha=trusted_workflow_sha,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=admission)
        ready = verified.prior_ready_plans.get(_BINARY if phase == "binary" else _PACKAGE)
        if ready is None or ready["buildKey"] != expected_build_key:
            raise ValueError("Android Maven phase differs from the Core-admitted election")
        properties = _properties(git_regular_blob_bytes(root, verified.plan["validationCommit"],
            "gradle.properties", max_bytes=1024 * 1024), "Original Android archive pins")
        if sha256_file(archive, reject_symlink_parents=True) != require_sha256(
                "sha256:" + properties["codexAgent.codexArchiveSha256"],
                "Original Android archive pin"):
            raise ValueError("Android archive differs from the immutable candidate Git pin")
        if destination is None:
            return ready
        if phase == "package":
            return sdk_maven_package_workflow.execute(plan, discovery, phase_state, destination,
                component="sdk-android", expected_build_key=expected_build_key,
                sdk_inputs_artifact_id=sdk_inputs_artifact_id,
                sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
                trusted_workflow_sha=trusted_workflow_sha, keyring=keyring,
                keys_directory=keys_directory,
                binary_contract_evidence=binary_contract_evidence,
                binary_original_context=binary_original_context,
                repository_root=root, environ=environment, token=token,
                binary_artifact_id=binary_artifact_id,
                binary_artifact_sha256=binary_artifact_sha256,
                android_runtime_archive=archive, sdk_validation_tooling=tooling,
                sdk_apple_validation_policy=sdk_apple_validation_policy,
                sdk_facade_metadata_admission=admission)
        return sdk_maven_binary_workflow.execute(plan, discovery, after_state, destination,
            component="sdk-android", expected_build_key=expected_build_key,
            repository_root=root, environ=environment,
            trusted_workflow_sha=trusted_workflow_sha,
            android_runtime_archive=archive, sdk_validation_tooling=tooling,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=admission)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("preflight", "execute"))
    parser.add_argument("--phase", choices=("binary", "package"), default="binary")
    for name in ("plan", "discovery-root", "before-state-root", "after-state-root",
                 "metadata-receipt", "replay-policy", "original-context", "repository-root",
                 "android-runtime-archive"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-build-key", "expected-metadata-build-key",
                 "expected-metadata-receipt-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    for name in ("selected-state-root", "binary-contract-evidence", "binary-original-context",
                 "keyring", "keys-directory"):
        parser.add_argument("--" + name, type=Path)
    for name in ("sdk-inputs-artifact-id", "binary-artifact-id"):
        parser.add_argument("--" + name, type=int)
    for name in ("sdk-inputs-artifact-sha256", "binary-artifact-sha256"):
        parser.add_argument("--" + name)
    arguments = vars(parser.parse_args(argv))
    mode = arguments.pop("mode")
    output = arguments.pop("github_output")
    arguments["discovery"] = arguments.pop("discovery_root")
    arguments["before_state"] = arguments.pop("before_state_root")
    arguments["after_state"] = arguments.pop("after_state_root")
    arguments["selected_state"] = arguments.pop("selected_state_root")
    if (mode == "preflight") != (arguments["destination"] is None):
        parser.error("preflight requires no destination; execute requires a destination")
    if mode == "execute" and output is not None:
        parser.error("execution cannot publish a new caller authority")
    try:
        arguments["replay_policy"] = load_canonical_json_bytes(read_regular_file_bytes(
            arguments["replay_policy"], reject_symlink_parents=True))
        arguments["original_context"] = load_canonical_json_bytes(read_regular_file_bytes(
            arguments["original_context"], reject_symlink_parents=True))
        if arguments["sdk_apple_validation_policy"] is not None:
            arguments["sdk_apple_validation_policy"] = load_canonical_json_bytes(
                read_regular_file_bytes(arguments["sdk_apple_validation_policy"],
                    reject_symlink_parents=True))
        for name in ("binary_contract_evidence", "binary_original_context"):
            if arguments[name] is not None:
                arguments[name] = load_canonical_json_bytes(read_regular_file_bytes(
                    arguments[name], reject_symlink_parents=True))
        ready = with_core14(**arguments, token=os.environ["GITHUB_TOKEN"], environ=os.environ)
        if mode == "preflight":
            row = {name: ready[name] for name in ("product", "component", "phase", "target", "buildKey")}
            row.update(runner="ubuntu-24.04", runnerOs="Linux", runnerArch="X64")
            github_output(output, {"sdk_matrix": canonical_json_bytes({"include": [row]}).decode().strip(),
                "sdk_workers_required": True})
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
