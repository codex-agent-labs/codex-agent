"""Compose authenticated protected-upload capture with the existing S858 bridge.

The caller selects upload, metadata, workflow and SDK Git policy identities.
This command neither elects them nor chooses compatibility ranges or signs.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    # Use the same products namespace as the established standalone CI entrypoints.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_regular_directory, snapshot_regular_tree,
)
from products.runtime_aggregate_handoff import _public_policy
from products.sdk_package import _require_capability_output_separate
from products.sdk_protected_runtime import stage_protected_runtime_sdk_inputs
from products.sdk_release_selection import read_sdk_release_selection, require_sdk_runtime_compatibility_policy


def capture_sdk_handoff(
    plan_path: Path, destination: Path, *, artifact_id: int, artifact_sha256: str,
    trusted_workflow_sha: str, expected_build_key: str, expected_metadata_receipt_sha256: str,
    sdk_version: str, compatible_release_range: str, compatible_runtime_compatibility_range: str,
    keyring: Path, keys_directory: Path, selection_repository_root: Path, selection_revision: str,
    repository_root: Path | None = None, environ=None, token: str,
) -> dict:
    """Publish original upload evidence and SDK inputs only after both gates exit."""
    repository = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    selection = Path(selection_repository_root).absolute()
    plan, destination = Path(plan_path).absolute(), Path(destination).absolute()
    originals = [repository, selection, plan, Path(keyring), Path(keys_directory)]

    def output_safe():
        _require_capability_output_separate(destination, originals)
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("SDK handoff output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "SDK handoff output ancestry")
        if destination.exists():
            raise ValueError("SDK handoff destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    selected_policy = read_sdk_release_selection(selection, selection_revision)
    selected_ranges = require_sdk_runtime_compatibility_policy(selection, selection_revision,
        compatible_release_range=compatible_release_range,
        compatible_runtime_compatibility_range=compatible_runtime_compatibility_range)
    environment = dict(os.environ if environ is None else environ)
    with tempfile.TemporaryDirectory(prefix="sdk-handoff-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, originals)
        policy = private / "policy"
        paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        prepared = private / "output"
        capture = prepared / "runtime-capture"
        product_reuse.capture_runtime_aggregate_release_upload(plan, capture,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
            repository_root=repository, environ=environment, token=token)
        if read_regular_file_bytes(capture / "plan/impact-plan.json", reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Captured SDK handoff plan differs from its original bytes")
        capture_inventory = regular_file_inventory(capture, allow_empty=True)
        forwarded = private / "forwarded"
        result = stage_protected_runtime_sdk_inputs(capture / "original", forwarded,
            expected_metadata_receipt_sha256=expected_metadata_receipt_sha256, expected_build_key=expected_build_key,
            sdk_version=sdk_version, compatible_release_range=compatible_release_range,
            compatible_runtime_compatibility_range=compatible_runtime_compatibility_range,
            keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys",
            selection_repository_root=selection, selection_revision=selection_revision)
        # The complete original wrapper is already retained in runtime-capture;
        # avoid duplicating its potentially large history in the final artifact.
        sdk_inventory = regular_file_inventory(forwarded / "sdk-inputs")
        snapshot_regular_tree(forwarded / "sdk-inputs", prepared / "sdk-inputs")
        if (regular_file_inventory(capture, allow_empty=True) != capture_inventory
                or regular_file_inventory(forwarded / "sdk-inputs") != sdk_inventory
                or regular_file_inventory(prepared / "sdk-inputs") != sdk_inventory
                or read_regular_file_bytes(plan, reject_symlink_parents=True) != plan_bytes
                or read_sdk_release_selection(selection, selection_revision) != selected_policy
                or require_sdk_runtime_compatibility_policy(selection, selection_revision,
                    compatible_release_range=compatible_release_range,
                    compatible_runtime_compatibility_range=compatible_runtime_compatibility_range) != selected_ranges
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in paths.items())):
            raise ValueError("SDK handoff inputs or caller policy changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "destination", "repository-root", "selection-repository-root", "keyring", "keys-directory"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    for name in ("artifact-sha256", "trusted-workflow-sha", "expected-build-key", "expected-metadata-receipt-sha256",
                 "sdk-version", "compatible-release-range", "compatible-runtime-compatibility-range", "selection-revision"):
        parser.add_argument(f"--{name}", required=True)
    arguments = vars(parser.parse_args(argv))
    plan, destination = arguments.pop("plan"), arguments.pop("destination")
    try:
        capture_sdk_handoff(plan, destination, **arguments, environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
