"""Reconstruct fresh Core-14 caller inputs for Android without trusting its upload."""

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_core_metadata_bootstrap
from products.inventory import (canonical_json_bytes, load_canonical_json_bytes, load_json_bytes,
    read_regular_file_bytes, regular_file_inventory, require_integer, require_sha256, sha256_bytes)
from products.receipt import validate_phase_receipt
from products.signing_isolation import require_no_signing_secret
from sdk_facade_metadata_original import _context


def prepare(plan, discovery, before_state, worker_root, requests_root, destination, *,
        expected_metadata_build_key, expected_metadata_receipt_sha256,
        metadata_artifact_id, metadata_artifact_sha256, metadata_original_context,
        sdk_inputs_artifact_id, sdk_inputs_artifact_sha256, trusted_workflow_sha,
        sdk_validation_tooling, native_compiler_archives, keyring, keys_directory,
        repository_root, environ, token, sdk_apple_validation_policy=None):
    """Authenticate a current Core upload, then rebuild its independent raw policy.

    The downloaded tree is only a receipt candidate. The Core holder must
    authenticate its official upload before Android uses this policy.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    worker = root / "build/sdk-core-metadata-worker"
    if Path(worker_root).absolute() != worker or worker.resolve(strict=True) != worker:
        raise ValueError("Fresh Android Core upload requires the exact checkout worker path")
    require_integer(metadata_artifact_id, "Original Core metadata upload ID", 1)
    require_sha256(metadata_artifact_sha256, "Original Core metadata upload digest")
    require_sha256(expected_metadata_build_key, "Original Core metadata build key")
    require_sha256(expected_metadata_receipt_sha256, "Original Core metadata receipt digest")
    context = _context(metadata_original_context)
    if context["repositoryRoot"] != str(root):
        raise ValueError("Original Core metadata context belongs to another checkout")
    receipt_path = worker / "shard/phase-receipt.json"
    raw = read_regular_file_bytes(receipt_path, reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if (sha256_bytes(raw) != expected_metadata_receipt_sha256 or
            tuple(receipt[name] for name in ("product", "component", "phase", "target")) !=
            ("sdk", "sdk-core", "metadata", "common") or
            receipt["buildKey"] != expected_metadata_build_key):
        raise ValueError("Downloaded Core receipt differs from independent caller election")
    current = product_reuse._validate_plan(plan, root)
    if (current["remoteBuildAuthorized"] is not True or
            current["event"] not in {"pull_request", "merge_group"} or
            receipt["producer"] != product_reuse._consumer(current, environ)["producer"]):
        raise ValueError("Fresh Core receipt is not from the authorized current campaign")
    before = regular_file_inventory(worker, allow_empty=True)
    sdk_core_metadata_bootstrap.prepare(plan, discovery, before_state, requests_root,
        destination, expected_build_key=expected_metadata_build_key,
        sdk_inputs_artifact_id=sdk_inputs_artifact_id,
        sdk_inputs_artifact_sha256=sdk_inputs_artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha,
        sdk_validation_tooling=sdk_validation_tooling,
        native_compiler_archives=native_compiler_archives,
        keyring=keyring, keys_directory=keys_directory, repository_root=root,
        environ=environ, token=token, sdk_apple_validation_policy=sdk_apple_validation_policy)
    if (regular_file_inventory(worker, allow_empty=True) != before or
            read_regular_file_bytes(receipt_path, reject_symlink_parents=True) != raw):
        raise ValueError("Original Core worker changed during Android policy preparation")
    return {"metadataReceipt": str(receipt_path), "replayPolicy": str(destination),
            "originalContext": context, "metadataArtifactId": metadata_artifact_id,
            "metadataArtifactSha256": metadata_artifact_sha256}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "discovery", "before-state", "worker-root", "requests-root",
                 "destination", "sdk-validation-tooling", "keyring", "keys-directory",
                 "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("expected-metadata-build-key", "expected-metadata-receipt-sha256",
                 "metadata-artifact-sha256", "metadata-original-context",
                 "sdk-inputs-artifact-sha256", "trusted-workflow-sha"):
        parser.add_argument("--" + name, required=True)
    for name in ("metadata-artifact-id", "sdk-inputs-artifact-id"):
        parser.add_argument("--" + name, type=int, required=True)
    parser.add_argument("--sdk-apple-validation-policy", type=Path)
    parser.add_argument("--native-compiler-archive", action="append", default=[], metavar="TARGET=PATH")
    args = vars(parser.parse_args(argv))
    try:
        pairs = [value.split("=", 1) for value in args.pop("native_compiler_archive")]
        if (any(len(pair) != 2 or not pair[0] or not pair[1] for pair in pairs) or
                len({pair[0] for pair in pairs}) != len(pairs)):
            raise ValueError("Android Core native archives require unique TARGET=PATH values")
        raw_context = args.pop("metadata_original_context")
        context = load_json_bytes(raw_context.encode("utf-8"))
        if canonical_json_bytes(context).decode("utf-8").strip() != raw_context:
            raise ValueError("Original Core context output must be canonical JSON")
        args["metadata_original_context"] = context
        prepare(**args, native_compiler_archives={key: value for key, value in pairs},
            environ=os.environ, token=os.environ["GITHUB_TOKEN"])
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
