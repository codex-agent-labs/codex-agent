"""Assemble a Core14 preparation policy from current election and official uploads.

This is a non-secret caller input, not a signed attestation. The protected
signer must independently authenticate the eventual preparation transport.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from . import product_reuse
from .products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, sha256_file, write_canonical_json,
)
from .products.receipt import validate_phase_receipt
from .products.registry import PhaseInstanceId, SDK_FACADE_TARGETS
from .products.sdk_apple_validation_admission import apple_validation_policy_arguments
from .products.sdk_package import _require_capability_output_separate
from .products.signing_isolation import require_no_signing_secret
from .sdk_facade_metadata_original import _context
from .sdk_facade_original_inputs import _fresh_policy_sources
from .sdk_facade_upload_locator import locate_original_facade_upload
from .sdk_policy_snapshot import snapshot_policy_closure


_METADATA = PhaseInstanceId("sdk", "sdk-core", "metadata", "common")


def prepare_original_core_caller_policy(plan, discovery, state, bootstrap_policy,
        metadata_receipt, destination, *, expected_build_key, expected_receipt_sha256,
        metadata_artifact_id, metadata_artifact_sha256, original_context,
        trusted_workflow_sha, repository_root, environ, token,
        sdk_apple_validation_policy_path=None):
    """Publish only after the elected Core14 and all eleven uploads agree.

    The caller must source the Core14 pins from successful worker outputs and
    bootstrap policy from its own authenticated wave13 state, not a retained
    Core14 request. This function independently replays that state and observes
    each selected original upload before constructing the CLI input.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    plan, discovery, state = (Path(value).absolute() for value in (plan, discovery, state))
    bootstrap_policy, metadata_receipt, destination = (Path(value).absolute() for value in
        (bootstrap_policy, metadata_receipt, destination))
    discovery, state, _ = product_reuse._product_materialization_paths(
        root, discovery, state, root / "build/core-context-policy-unused")
    if (bootstrap_policy.resolve(strict=True) != bootstrap_policy or
            bootstrap_policy == root or bootstrap_policy.is_relative_to(root)):
        raise ValueError("Core bootstrap policy must be external and non-symbolic")
    apple_path = None if sdk_apple_validation_policy_path is None else Path(sdk_apple_validation_policy_path).absolute()
    if apple_path is not None and (apple_path.resolve(strict=True) != apple_path or
                                   apple_path == root or apple_path.is_relative_to(root)):
        raise ValueError("Core Apple validation policy must be external and non-symbolic")
    _require_capability_output_separate(destination, [root, plan, discovery, state,
        bootstrap_policy, metadata_receipt, *([apple_path] if apple_path is not None else [])])
    if destination.exists() or destination.is_symlink() or destination.resolve(strict=False) != destination:
        raise ValueError("Core caller policy destination must be fresh and non-symbolic")
    require_sha256(expected_build_key, "Selected Core metadata build key")
    require_sha256(expected_receipt_sha256, "Selected Core metadata receipt")
    require_integer(metadata_artifact_id, "Selected Core metadata upload ID", 1)
    require_sha256(metadata_artifact_sha256, "Selected Core metadata upload digest")
    context = _context(original_context)
    if context["repositoryRoot"] != str(root):
        raise ValueError("Core metadata context belongs to another checkout")
    inputs = {path: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True) for path in (plan, bootstrap_policy, metadata_receipt,
                                                  *([apple_path] if apple_path is not None else []))}
    raw_policy = inputs[bootstrap_policy]
    policy = load_canonical_json_bytes(raw_policy)
    apple_policy = None if apple_path is None else load_canonical_json_bytes(inputs[apple_path])
    if apple_policy is not None and type(apple_policy) is not dict:
        raise ValueError("Core Apple validation policy must be a canonical object")
    apple_policy_bytes = None if apple_policy is None else canonical_json_bytes(apple_policy)
    apple_closure = None if apple_path is None else snapshot_policy_closure("apple-validation", apple_path)
    if apple_policy is not None:
        _require_capability_output_separate(destination, [value for value in
            apple_validation_policy_arguments(apple_policy).values() if isinstance(value, Path)])
    source_files, source_trees = _fresh_policy_sources(policy)
    _require_capability_output_separate(destination, [*source_files, *source_trees])
    if (policy["plan"] != str(plan) or policy["toolingTrustDomain"] != "release"):
        raise ValueError("Core bootstrap policy differs from current release caller")
    source_trees.update({path: regular_file_inventory(path, allow_empty=True)
                         for path in (discovery, state)})
    context_bytes = canonical_json_bytes(context)
    selected_receipt = validate_phase_receipt(load_canonical_json_bytes(inputs[metadata_receipt]))
    if (sha256_bytes(inputs[metadata_receipt]) != expected_receipt_sha256 or
            tuple(selected_receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-core", "metadata", "common") or
            selected_receipt["buildKey"] != expected_build_key):
        raise ValueError("Core metadata receipt differs from successful caller outputs")

    def unchanged():
        require_no_signing_secret(environ)
        if (canonical_json_bytes(original_context) != context_bytes or
                (apple_policy is not None and canonical_json_bytes(apple_policy) != apple_policy_bytes) or
                any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != raw for path, raw in inputs.items()) or
                any(sha256_file(path, reject_symlink_parents=True) != digest
                    for path, digest in source_files.items()) or
                any(regular_file_inventory(path, allow_empty=True) != inventory
                    for path, inventory in source_trees.items()) or
                (apple_path is not None and
                 snapshot_policy_closure("apple-validation", apple_path) != apple_closure)):
            raise ValueError("Core caller election, source or receipt changed during observation")

    tooling = {"evidence": policy["toolingEvidence"], "publicKey": policy["toolingPublicKey"],
        "javaExecutable": policy["javaExecutable"], "requiredTrustDomain": policy["toolingTrustDomain"],
        "keyring": policy["toolingKeyring"], "keysDirectory": policy["toolingKeysDirectory"]}
    unchanged()
    elected = product_reuse._verified_product_state(plan, discovery, state, root, environ, tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"sdk_apple_validation_policy": apple_policy}
           if apple_policy is not None else {}))
    ready = elected.prior_ready_plans.get(_METADATA)
    if (ready is None or ready["buildKey"] != expected_build_key or
            selected_receipt["producer"] != elected.producer):
        raise ValueError("Core metadata is not current and ready with its exact original producer")
    unchanged()
    official = locate_original_facade_upload(metadata_receipt,
        expected_receipt_sha256=expected_receipt_sha256,
        trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ)
    if (official["artifact_id"] != metadata_artifact_id or
            official["artifact_sha256"] != metadata_artifact_sha256):
        raise ValueError("Core metadata official upload differs from successful worker outputs")
    unchanged()

    validations = {}
    for target in SDK_FACADE_TARGETS:
        instance = PhaseInstanceId("sdk", "sdk-core", "validation", target)
        selected = elected.prior_by_instance.get(instance)
        record = policy["validations"][target]
        receipt_path = Path(record["validationReceipt"])
        receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                                reject_symlink_parents=True)
        if (selected is None or selected["state"] != "retained" or instance not in elected.sources or
                sha256_bytes(receipt_bytes) != selected["receiptSha256"]):
            raise ValueError("Core original validation differs from authenticated wave13 state")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if (tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
                ("sdk", "sdk-core", "validation", target) or receipt["buildKey"] != selected["buildKey"]):
            raise ValueError("Core original validation receipt differs from elected target and key")
        unchanged()
        locator = locate_original_facade_upload(receipt_path,
            expected_receipt_sha256=selected["receiptSha256"],
            trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ)
        unchanged()
        validations[target] = {**record, "artifactId": locator["artifact_id"],
            "artifactSha256": locator["artifact_sha256"]}
    caller = {"schemaVersion": 1, "plan": str(plan), "metadataReceiptPath": str(metadata_receipt),
        "expectedBuildKey": expected_build_key, "expectedReceiptSha256": expected_receipt_sha256,
        "artifactId": metadata_artifact_id, "artifactSha256": metadata_artifact_sha256,
        "originalContext": context, "validations": validations,
        "contractDigest": policy["contractDigest"], "componentDigests": policy["componentDigests"],
        "toolingEvidence": policy["toolingEvidence"], "toolingPublicKey": policy["toolingPublicKey"],
        "javaExecutable": policy["javaExecutable"], "policyRevision": elected.plan["validationCommit"],
        "requiredTrustDomain": policy["toolingTrustDomain"], "toolingKeyring": policy["toolingKeyring"],
        "toolingKeysDirectory": policy["toolingKeysDirectory"]}
    caller_bytes = canonical_json_bytes(caller)
    with tempfile.TemporaryDirectory(prefix="core-context-caller-") as temporary:
        staged = Path(temporary).resolve() / "candidate"
        staged.mkdir()
        write_canonical_json(staged / "caller-policy.json", caller)
        unchanged()
        publish_regular_tree(staged, destination, expected_inventory=[{
            "relativePath": "caller-policy.json", "bytes": len(caller_bytes),
            "sha256": sha256_bytes(caller_bytes)}])
    return destination / "caller-policy.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery", "state", "bootstrap-policy", "metadata-receipt",
                 "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-build-key", "expected-receipt-sha256", "metadata-artifact-sha256",
                 "original-context", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--metadata-artifact-id", type=int, required=True)
    parser.add_argument("--sdk-apple-validation-policy", dest="sdk_apple_validation_policy_path", type=Path)
    args = vars(parser.parse_args(argv))
    try:
        require_no_signing_secret(os.environ)
        raw_context = args.pop("original_context")
        context = load_json_bytes(raw_context.encode("utf-8"))
        if canonical_json_bytes(context).decode("utf-8").strip() != raw_context:
            raise ValueError("Core metadata context output must be canonical JSON")
        args["original_context"] = context
        prepare_original_core_caller_policy(**args, environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
