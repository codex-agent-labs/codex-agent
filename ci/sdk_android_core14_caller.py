"""Hold independently authenticated Core wave 14 for Android waves 15–16.

The caller owns both original SDK state transports and the Core receipt/policy.
Nothing from the temporary Core descriptor is exported to another process.
"""

import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_maven_binary_workflow
import sdk_maven_package_workflow
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_integer, require_sha256, sha256_bytes, sha256_file)
from products.receipt import validate_phase_receipt
from products.registry import PhaseInstanceId
from products.reuse import RemoteCatalog, _remote_catalog
from products.sdk_facade_inputs import _path
from products.sdk_facade_metadata_admission import FacadeMetadataAdmission
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties
from reuse import github_output
from sdk_core_metadata_same_campaign import held_same_campaign_core_metadata_policy
from sdk_facade_original_inputs import held_original_facade_metadata_policy


_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")
_PACKAGE = PhaseInstanceId("sdk", "sdk-android", "package", "android")


def with_core14(plan, discovery, before_state, after_state, metadata_receipt,
        *, expected_build_key, expected_metadata_build_key, expected_metadata_receipt_sha256,
        expected_metadata_artifact_id=None, expected_metadata_artifact_sha256=None,
        replay_policy, original_context, trusted_workflow_sha, repository_root,
        android_runtime_archive, token, environ=None, destination=None,
        sdk_apple_validation_policy=None, phase="binary", selected_state=None,
        sdk_inputs_artifact_id=None, sdk_inputs_artifact_sha256=None,
        binary_artifact_id=None, binary_artifact_sha256=None,
        binary_contract_evidence=None, binary_original_context=None,
        keyring=None, keys_directory=None, reused_catalog=None, reused_catalog_root=None,
        reused_catalog_source=None, reused_receipt_sha256=None):
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
    reused = any(value is not None for value in
        (reused_catalog, reused_catalog_root, reused_catalog_source, reused_receipt_sha256))
    if reused:
        if (type(reused_catalog) is not RemoteCatalog or reused_catalog_root is None or
                reused_catalog_source not in ("same-pr", "stable", "promoted-main") or
                not isinstance(reused_receipt_sha256, dict) or
                reused_receipt_sha256.get("common") != expected_metadata_receipt_sha256):
            raise ValueError("Reused Core metadata requires an independent catalog and twelve pinned receipts")
        carrier = _path(str(reused_catalog_root), "Reused Core carrier root")
        trust = tuple(_path(str(path), "Reused Core caller trust") for path in
            (reused_catalog.public_key, reused_catalog.keyring, reused_catalog.keys_directory)
            if path is not None)
        if any(path == carrier or carrier in path.parents for path in trust):
            raise ValueError("Reused Core caller trust must be independent of its carrier")
        raw = read_regular_file_bytes(metadata_receipt, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if (sha256_bytes(raw) != expected_metadata_receipt_sha256 or
                tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-core", "metadata", "common") or
                receipt["buildKey"] != expected_metadata_build_key):
            raise ValueError("Reused Core metadata receipt differs from caller election")
        held = held_original_facade_metadata_policy(plan, catalog=reused_catalog,
            catalog_source=reused_catalog_source, metadata_receipt_path=metadata_receipt,
            expected_receipt_sha256=reused_receipt_sha256,
            replay_policy={**replay_policy, "originalContext": original_context},
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root, token=token)
    else:
        require_integer(expected_metadata_artifact_id, "Fresh Core metadata upload ID", 1)
        require_sha256(expected_metadata_artifact_sha256, "Fresh Core metadata upload digest")
        held = held_same_campaign_core_metadata_policy(
            plan, discovery, before_state, after_state, metadata_receipt,
            expected_build_key=expected_metadata_build_key,
            expected_receipt_sha256=expected_metadata_receipt_sha256,
            expected_artifact_id=expected_metadata_artifact_id,
            expected_artifact_sha256=expected_metadata_artifact_sha256,
            replay_policy=replay_policy, original_context=original_context,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
            environ=environment, token=token,
            sdk_apple_validation_policy=sdk_apple_validation_policy)
    with held as descriptor:
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
        if reused:
            metadata = verified.prior_by_instance.get(PhaseInstanceId("sdk", "sdk-core", "metadata", "common"))
            if (metadata is None or metadata["state"] != "reused" or
                    metadata["source"] != reused_catalog_source or
                    not isinstance(metadata["transportSource"], dict) or
                    metadata["transportSource"]["indexSha256"] != sha256_file(
                        reused_catalog.manifest, reject_symlink_parents=True) or
                    metadata["buildKey"] != expected_metadata_build_key or
                    metadata["receiptSha256"] != expected_metadata_receipt_sha256):
                raise ValueError("Android Core metadata differs from the signed reused election")
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
    parser.add_argument("--expected-metadata-artifact-id", type=int)
    parser.add_argument("--expected-metadata-artifact-sha256")
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
    for name in ("reused-catalog", "reused-catalog-root", "reused-receipt-sha256",
                 "reused-public-key", "reused-keyring", "reused-keys-directory"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--reused-catalog-source", choices=("same-pr", "stable", "promoted-main"))
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
        replay_control, context_control = arguments["replay_policy"], arguments["original_context"]
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
        if any(arguments[name] is not None for name in
               ("reused_catalog", "reused_catalog_root", "reused_catalog_source",
                "reused_receipt_sha256", "reused_public_key", "reused_keyring",
                "reused_keys_directory")):
            if any(arguments[name] is None for name in
                   ("reused_catalog", "reused_catalog_root", "reused_catalog_source",
                    "reused_receipt_sha256")):
                raise ValueError("Reused Core metadata requires catalog, root, source and twelve receipt digests")
            carrier = _path(str(arguments["reused_catalog_root"]), "Android caller catalog root")
            repository = _path(str(arguments["repository_root"]), "Android caller repository")
            controls = tuple(_path(str(path), "Android independent caller input") for path in
                (arguments["reused_catalog"], arguments["reused_receipt_sha256"],
                 replay_control, context_control))
            trust = tuple(_path(str(arguments[name]), "Android independent trust input")
                          for name in ("reused_public_key", "reused_keyring",
                                       "reused_keys_directory") if arguments[name] is not None)
            if any(path == carrier or carrier in path.parents for path in (*controls, *trust)) or any(
                    path == repository or repository in path.parents for path in controls):
                raise ValueError("Reused Core caller controls and trust must be independent of retained carriers")
            catalog = _remote_catalog(arguments["reused_catalog_root"],
                load_canonical_json_bytes(read_regular_file_bytes(
                    arguments["reused_catalog"], reject_symlink_parents=True)),
                "Android caller catalog")
            arguments.pop("reused_catalog")
            if any(getattr(catalog, name) is not None for name in
                   ("public_key", "keyring", "keys_directory", "contract_attestation",
                    "contract_attestation_signature", "contract_public_key")):
                raise ValueError("Reused Core catalog cannot supply caller trust")
            if arguments["reused_catalog_source"] == "same-pr":
                if (arguments["reused_public_key"] is None or
                        arguments["reused_keyring"] is not None or
                        arguments["reused_keys_directory"] is not None):
                    raise ValueError("Same-PR reused Core requires an external public key")
            elif (arguments["reused_public_key"] is not None or
                    arguments["reused_keyring"] is None or
                    arguments["reused_keys_directory"] is None):
                raise ValueError("Release reused Core requires an external keyring and keys directory")
            arguments["reused_catalog"] = replace(catalog,
                public_key=arguments.pop("reused_public_key"),
                keyring=arguments.pop("reused_keyring"),
                keys_directory=arguments.pop("reused_keys_directory"))
            arguments["reused_receipt_sha256"] = load_canonical_json_bytes(read_regular_file_bytes(
                arguments["reused_receipt_sha256"], reject_symlink_parents=True))
        else:
            for name in ("reused_public_key", "reused_keyring",
                         "reused_keys_directory"):
                arguments.pop(name)
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
