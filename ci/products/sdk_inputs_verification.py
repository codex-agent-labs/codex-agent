"""Verify retained S858 inputs under caller-owned policy, without restaging products."""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_regular_directory, require_relative_path,
    require_sha256, snapshot_regular_tree, verify_regular_file_inventory,
)
from .receipt import validate_phase_receipt
from .runtime_aggregate_handoff import _public_policy
from .sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility
from .sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME
from .sdk_package import _require_capability_output_separate
from .sdk_release_selection import (
    require_sdk_contract_version, require_sdk_release_selection, require_sdk_runtime_compatibility_policy,
)


@contextmanager
def verified_sdk_inputs(root: Path, *, keyring: Path, keys_directory: Path,
                        selection_repository_root: Path, selection_revision: str,
                        expected_contract_payload_sha256: str):
    """Yield verified private paths only while all original/captured bytes remain fixed.

    The inventory and transported public policy are not authority. Callers own
    selection of the upload, exact Git revision, public policy and Contract
    payload digest; this context reuses the existing signed compatibility gates.
    Publish copied results only after this context exits successfully.
    """
    expected = require_sha256(expected_contract_payload_sha256, "Expected Contract payload SHA-256")
    if any(value is None for value in (keyring, keys_directory, selection_repository_root, selection_revision)):
        raise ValueError("Verified SDK inputs require caller public policy and exact Git selection")
    root = Path(root).absolute()
    for path in (root, *root.parents):
        require_regular_directory(path, "SDK inputs ancestry")
    names = {"inputs", REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME}
    if {path.name for path in root.iterdir()} != names:
        raise ValueError("SDK inputs require the exact S858 root layout")
    before = regular_file_inventory(root)
    with tempfile.TemporaryDirectory(prefix="verified-sdk-inputs-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private, [root, Path(keyring), Path(keys_directory), Path(selection_repository_root)])
        captured, policy = private / "sdk-inputs", private / "policy"
        snapshot_regular_tree(root, captured)
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        inventory = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            captured / INVENTORY_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)),
            {"schemaVersion", "kind", "files"}, "SDK input inventory")
        if require_integer(inventory["schemaVersion"], "SDK input inventory schemaVersion", 1) != 1 or inventory["kind"] != "sdk-inputs":
            raise ValueError("Unsupported SDK input inventory")
        verify_regular_file_inventory(captured, inventory["files"], with_kind=False, excluded_paths=(INVENTORY_NAME,))

        def bind(value):
            if isinstance(value, Path):
                relative = require_relative_path(value.as_posix(), "Transported SDK request path")
                path = captured / relative
                if not path.resolve(strict=True).is_relative_to(captured):
                    raise ValueError("Transported SDK request path escapes captured inputs")
                return path
            if isinstance(value, dict):
                return {name: bind(member) for name, member in value.items()}
            return value

        arguments = bind(load_sdk_compatibility_request(captured / REQUEST_NAME, request_directory=Path(".")))
        if arguments["required_trust_domain"] != "release":
            raise ValueError("Verified SDK inputs require release trust")
        for product in ("contract", "runtime"):
            arguments[f"{product}_keyring"] = policy / "product-signing-keys.json"
            arguments[f"{product}_keys_directory"] = policy / "keys"
        recomputed = private / "recomputed"
        recomputed.mkdir()
        compatibility = produce_sdk_compatibility(output=recomputed / COMPATIBILITY_NAME, **arguments)
        if read_regular_file_bytes(recomputed / COMPATIBILITY_NAME, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != read_regular_file_bytes(
                captured / COMPATIBILITY_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True):
            raise ValueError("Original SDK compatibility differs from authenticated recomputation")
        require_sdk_release_selection(selection_repository_root, selection_revision,
            sdk_version=compatibility["sdkVersion"], runtime_version=compatibility["runtime"]["defaultRuntimeVersion"])
        require_sdk_contract_version(selection_repository_root, selection_revision,
                                     contract_version=compatibility["contract"]["version"])
        require_sdk_runtime_compatibility_policy(selection_repository_root, selection_revision,
            compatible_release_range=arguments["compatible_release_range"],
            compatible_runtime_compatibility_range=arguments["compatible_runtime_compatibility_range"])
        receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
            arguments["contract_metadata_receipt"], max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)))
        outputs = [record for record in receipt["outputs"] if record["kind"] == "contract-bundle"]
        if len(outputs) != 1 or outputs[0]["sha256"] != expected:
            raise ValueError("Authenticated SDK Contract payload differs from the selected Contract payload")

        def unchanged():
            if ({path.name for path in root.iterdir()} != names or {path.name for path in captured.iterdir()} != names
                    or regular_file_inventory(root) != before or regular_file_inventory(captured) != before
                    or regular_file_inventory(policy) != policy_inventory
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                           for name, path in policy_paths.items())):
                raise ValueError("Original or captured SDK inputs/policy changed during verification")

        unchanged()
        yield {"directory": captured, "arguments": arguments, "compatibility": compatibility}
        unchanged()
