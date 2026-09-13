"""Forward fixed protected Runtime outputs to S858, preserving external history.

The caller authenticates its selected metadata receipt/key and chooses the
public policy. Unsigned wrapper/control records never supply that authority.
The caller must also authenticate the complete original protected upload;
current wrapper provenance remains opaque, externally retained evidence here.
"""

import os
from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_regular_directory,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .receipt import validate_phase_receipt
from .runtime_aggregate_handoff import _public_policy
from .runtime_sdk_handoff import stage_runtime_sdk_handoff
from .sdk_package import _require_capability_output_separate


def _json(path):
    return load_canonical_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))


def _original_carrier(root, expected_digest, expected_key):
    if (root / "retained-release").exists():
        names = {path.name for path in root.iterdir()}
        required = {"caller.json", "selected-inputs", "trust", "retained-release"}
        if names not in (required, required | {"selected-state-transport"}):
            raise ValueError("Protected retained Runtime output has an unexpected layout")
        caller = require_exact_keys(_json(root / "caller.json"), {
            "schemaVersion", "target", "trustedSourceCommit", "trustedSourceTree",
            "trustedWorkflowSha", "transportProducer", "authorizationReason", "event",
            "environment", "metadataReceiptSha256", "releaseDirectory",
        }, "Retained Runtime caller")
        if (type(caller["schemaVersion"]) is not int or caller["schemaVersion"] != 1
                or caller["target"] != "aggregate" or caller["releaseDirectory"] != "retained-release"
                or caller["metadataReceiptSha256"] != expected_digest):
            raise ValueError("Protected retained Runtime caller differs from the selected original")
        for name in names - {"caller.json"}:
            require_regular_directory(root / name, "Protected retained Runtime directory")
        selected = _json(root / "selected-inputs/selection.json")
        if (not isinstance(selected, dict) or selected.get("target") != "aggregate"
                or not isinstance(selected.get("metadata"), dict)
                or selected["metadata"].get("buildKey") != expected_key
                or selected["metadata"].get("receiptSha256") != expected_digest):
            raise ValueError("Protected retained Runtime selection differs from caller-selected metadata")
        # This is a fixed path, never the transported releaseDirectory value.
        root = root / "retained-release"
    raw = read_regular_file_bytes(root / "aggregate-input/metadata-receipt.json",
                                  max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    if sha256_bytes(raw) != expected_digest:
        raise ValueError("Protected Runtime receipt differs from caller-selected original bytes")
    receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
    if (tuple(receipt[name] for name in ("product", "component", "phase", "target"))
            != ("runtime", "runtime-aggregate", "metadata", "aggregate")
            or receipt["buildKey"] != expected_key):
        raise ValueError("Protected Runtime receipt differs from caller-selected aggregate key")
    return root


def stage_protected_runtime_sdk_inputs(
    protected_output: Path, destination: Path, *, expected_metadata_receipt_sha256: str,
    expected_build_key: str, sdk_version: str, compatible_release_range: str,
    compatible_runtime_compatibility_range: str, keyring: Path, keys_directory: Path,
    selection_repository_root: Path, selection_revision: str,
    expected_contract_payload_sha256: str | None = None,
) -> dict:
    """Stage SDK files separately from exact fresh or retained protected history.

    Full original authentication and SDK Git-policy checks remain in the existing
    bridge. The result is its ordinary inventory, not a new admission token.
    """
    digest = require_sha256(expected_metadata_receipt_sha256, "Caller-selected aggregate receipt")
    key = require_sha256(expected_build_key, "Caller-selected aggregate key")
    if expected_contract_payload_sha256 is not None:
        require_sha256(expected_contract_payload_sha256, "Expected Contract payload SHA-256")
    if any(value is None for value in (keyring, keys_directory, selection_repository_root, selection_revision)):
        raise ValueError("Protected Runtime SDK forwarding requires caller policy and exact Git selection")
    original, destination = Path(protected_output).absolute(), Path(destination).absolute()
    selection_repository_root = Path(selection_repository_root).absolute()
    if any(path != Path(os.path.normpath(path)) for path in (original, destination, selection_repository_root)):
        raise ValueError("Protected Runtime SDK paths must be normalized")
    for path in (original, *original.parents):
        require_regular_directory(path, "Protected Runtime output ancestry")
    inputs = [original, Path(keyring), Path(keys_directory), selection_repository_root]

    def output_safe():
        _require_capability_output_separate(destination, inputs)
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("Protected Runtime SDK output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "Protected Runtime SDK output ancestry")
        if destination.exists():
            raise ValueError("Protected Runtime SDK destination must not exist")

    output_safe()
    before = regular_file_inventory(original, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="sdk-protected-runtime-") as temporary:
        private = Path(temporary).resolve()
        prepared = private / "output"
        captured = prepared / "runtime-release"
        snapshot_regular_tree(original, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Protected Runtime output changed during capture")
        policy = private / "policy"
        paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        carrier = _original_carrier(captured, digest, key)
        result = stage_runtime_sdk_handoff(carrier, prepared / "sdk-inputs",
            sdk_version=sdk_version, compatible_release_range=compatible_release_range,
            compatible_runtime_compatibility_range=compatible_runtime_compatibility_range,
            keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys",
            selection_repository_root=selection_repository_root, selection_revision=selection_revision,
            **({"expected_contract_payload_sha256": expected_contract_payload_sha256}
               if expected_contract_payload_sha256 is not None else {}))
        # All nested verification contexts have exited before external publication.
        regular_file_inventory(prepared / "sdk-inputs")  # SDK product/input files remain nonempty.
        if (regular_file_inventory(original, allow_empty=True) != before
                or regular_file_inventory(captured, allow_empty=True) != before
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in paths.items())):
            raise ValueError("Protected Runtime originals or caller policy changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    return result
