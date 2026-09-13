"""Compose SDK handoff routes from the existing authenticated product replay."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_handoff
from products.inventory import read_regular_file_bytes


def stage(plan, discovery, state, destination, *, keyring, keys_directory,
          repository_root, environ, token, trusted_workflow_sha=None, artifact_id=None,
          artifact_sha256=None, expected_build_key=None, expected_metadata_receipt_sha256=None):
    """Delegate source selection and both destination policies, never grant trust."""
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    validated = product_reuse._validate_plan(plan, repository_root)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ, include_sdk_selection=True)
    selection = inspected.get("sdkInputSelection")
    if not isinstance(selection, dict):
        raise ValueError("SDK workflow requires selected SDK consumer work")
    if read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
        raise ValueError("SDK workflow plan changed during inspection")
    if selection.get("source") == "released-default":
        return product_reuse.materialize_sdk_default_inputs(plan, discovery, state, destination,
            keyring=keyring, keys_directory=keys_directory, repository_root=repository_root, environ=environ)
    if selection.get("source") != "current-runtime":
        raise ValueError("SDK workflow has an unsupported replayed Runtime source")
    if any(value is None for value in (trusted_workflow_sha, artifact_id, artifact_sha256,
                                      expected_build_key, expected_metadata_receipt_sha256)):
        raise ValueError("Current Runtime SDK handoff requires complete authenticated upload identity")
    return sdk_handoff.capture_sdk_handoff(plan, destination,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        expected_build_key=expected_build_key, expected_metadata_receipt_sha256=expected_metadata_receipt_sha256,
        sdk_version=selection["sdkVersion"], compatible_release_range=selection["compatibleReleaseRange"],
        compatible_runtime_compatibility_range=selection["compatibleRuntimeCompatibilityRange"],
        expected_contract_payload_sha256=selection["contractPayloadSha256"],
        keyring=keyring, keys_directory=keys_directory, selection_repository_root=repository_root,
        selection_revision=validated["validationCommit"], repository_root=repository_root, environ=environ, token=token)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "discovery-root", "state-root", "destination", "keyring", "keys-directory", "repository-root"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int)
    for name in ("trusted-workflow-sha", "artifact-sha256", "expected-build-key", "expected-metadata-receipt-sha256"):
        parser.add_argument(f"--{name}")
    arguments = vars(parser.parse_args(argv))
    plan, discovery, state, destination = (arguments.pop(name) for name in ("plan", "discovery_root", "state_root", "destination"))
    try:
        stage(plan, discovery, state, destination, **arguments,
              environ=os.environ, token=os.environ.get("GITHUB_TOKEN", ""))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
