"""Compose SDK handoff routes from the existing authenticated product replay."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
import sdk_handoff
from products.inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory, sha256_bytes,
)
from products.registry import PhaseInstanceId
from products.runtime_aggregate_handoff import verified_runtime_aggregate_handoff
from products.sdk_inputs_verification import verified_sdk_inputs
from products.sdk_protected_runtime import _original_carrier


def _selection(plan, discovery, state, repository_root, environ):
    plan_bytes = read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    validated = product_reuse._validate_plan(plan, repository_root)
    inspected = product_reuse.inspect_products(plan, discovery, state,
        repository_root=repository_root, environ=environ, include_sdk_selection=True)
    selection = inspected.get("sdkInputSelection")
    if not isinstance(selection, dict):
        raise ValueError("SDK workflow requires selected SDK consumer work")
    if read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
        raise ValueError("SDK workflow plan changed during inspection")
    return validated, selection, plan_bytes


def stage(plan, discovery, state, destination, *, keyring, keys_directory,
          repository_root, environ, token, trusted_workflow_sha=None, artifact_id=None,
          artifact_sha256=None, expected_build_key=None, expected_metadata_receipt_sha256=None):
    """Delegate source selection and both destination policies, never grant trust."""
    validated, selection, _ = _selection(plan, discovery, state, repository_root, environ)
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


@contextmanager
def verified_inputs(plan, discovery, state, *, artifact_id, artifact_sha256,
                    trusted_workflow_sha, keyring, keys_directory, repository_root, environ, token):
    """Keep upload, SDK policy and raw Runtime originals verified through consumer use.

    Returned paths expire on exit. Consumers must finish using them inside the
    context and admit their outputs only after its final checks succeed. The
    Runtime carrier's Contract receipts remain its originals, not replacements
    for the current candidate's independently selected Contract predecessors.
    """
    validated, selection, plan_bytes = _selection(plan, discovery, state, repository_root, environ)
    with tempfile.TemporaryDirectory(prefix="sdk-consumer-inputs-") as temporary:
        capture = Path(temporary).resolve() / "capture"
        product_reuse.capture_sdk_inputs_upload(plan, capture, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            expected_source=selection["source"], repository_root=repository_root, environ=environ, token=token)
        inventory = regular_file_inventory(capture, allow_empty=True)

        def unchanged():
            if (regular_file_inventory(capture, allow_empty=True) != inventory
                    or read_regular_file_bytes(plan, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes):
                raise ValueError("SDK consumer original plan or captured upload changed during use")

        with verified_sdk_inputs(capture / "original/sdk-inputs", keyring=keyring, keys_directory=keys_directory,
                selection_repository_root=repository_root, selection_revision=validated["validationCommit"],
                expected_contract_payload_sha256=selection["contractPayloadSha256"]) as sdk:
            arguments = sdk["arguments"]
            raw = read_regular_file_bytes(arguments["runtime_metadata_receipt"])
            receipt = load_canonical_json_bytes(raw)
            carrier = (capture / "original/runtime-original" if selection["source"] == "released-default"
                       else capture / "original/runtime-capture/original")
            carrier = _original_carrier(carrier, sha256_bytes(raw), receipt["buildKey"])
            with verified_runtime_aggregate_handoff(carrier, keyring=arguments["runtime_keyring"],
                    keys_directory=arguments["runtime_keys_directory"]) as runtime:
                if read_regular_file_bytes(runtime["indexInputs"]["attestation"]) != read_regular_file_bytes(
                        arguments["runtime_attestation"]):
                    raise ValueError("SDK inputs and raw Runtime carrier have different original attestations")
                for product, component, target in (("contract", "contract", "common"),
                                                    ("runtime", "runtime-aggregate", "aggregate")):
                    identity = PhaseInstanceId(product, component, "metadata", target)
                    if runtime["receiptBytes"][identity] != read_regular_file_bytes(arguments[f"{product}_metadata_receipt"]):
                        raise ValueError("SDK inputs and raw Runtime carrier have different original receipts")
                unchanged()
                yield {"selection": selection, "capture": capture, "sdk": sdk, "runtime": runtime}
        unchanged()


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
