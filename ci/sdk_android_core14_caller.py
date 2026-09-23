"""Hold independently authenticated Core wave 14 while checking Android wave 15.

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
from products.inventory import (canonical_json_bytes, git_regular_blob_bytes, load_canonical_json_bytes,
    read_regular_file_bytes, require_sha256, sha256_file)
from products.registry import PhaseInstanceId
from products.sdk_facade_metadata_admission import FacadeMetadataAdmission
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties
from reuse import github_output
from sdk_core_metadata_same_campaign import held_same_campaign_core_metadata_policy


_BINARY = PhaseInstanceId("sdk", "sdk-android", "binary", "android")


def with_core14(plan, discovery, before_state, after_state, metadata_receipt,
        *, expected_build_key, expected_metadata_build_key, expected_metadata_receipt_sha256,
        replay_policy, original_context, trusted_workflow_sha, repository_root,
        android_runtime_archive, token, environ=None, destination=None,
        sdk_apple_validation_policy=None):
    """Preflight or execute Android binary under one live Core admission.

    ``destination=None`` performs the pre-setup check. A destination executes
    the existing Android binary controller. Both calls independently replay
    Core's official original upload and all eleven validation originals.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    root = Path(repository_root).resolve(strict=True)
    archive = Path(android_runtime_archive)
    if not archive.is_absolute() or archive.resolve(strict=True) != archive:
        raise ValueError("Android binary archive must be an independent normalized file")
    require_sha256(expected_build_key, "Android binary build key")
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
        verified = product_reuse._verified_product_state(plan, discovery, after_state,
            root, environment, tooling, sdk_original_workflow_sha=trusted_workflow_sha,
            sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_facade_metadata_admission=admission)
        ready = verified.prior_ready_plans.get(_BINARY)
        if ready is None or ready["buildKey"] != expected_build_key:
            raise ValueError("Android binary differs from the Core-admitted election")
        properties = _properties(git_regular_blob_bytes(root, verified.plan["validationCommit"],
            "gradle.properties", max_bytes=1024 * 1024), "Original Android archive pins")
        if sha256_file(archive, reject_symlink_parents=True) != require_sha256(
                "sha256:" + properties["codexAgent.codexArchiveSha256"],
                "Original Android archive pin"):
            raise ValueError("Android archive differs from the immutable candidate Git pin")
        if destination is None:
            return ready
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
    arguments = vars(parser.parse_args(argv))
    mode = arguments.pop("mode")
    output = arguments.pop("github_output")
    arguments["discovery"] = arguments.pop("discovery_root")
    arguments["before_state"] = arguments.pop("before_state_root")
    arguments["after_state"] = arguments.pop("after_state_root")
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
