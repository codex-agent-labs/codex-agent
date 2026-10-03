"""Join already-authenticated historical SDK uploads without electing new inputs."""

from contextlib import contextmanager
from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_regular_directory, sha256_bytes, snapshot_regular_tree,
)
from .registry import PhaseInstanceId
from .runtime_aggregate_handoff import _public_policy, verified_runtime_aggregate_handoff
from .sdk_inputs_verification import verified_sdk_inputs
from .sdk_package import _require_capability_output_separate
from .sdk_protected_runtime import _original_carrier
from .sdk_release_selection import (
    require_sdk_contract_version, require_sdk_release_selection,
    require_sdk_runtime_compatibility_policy,
)


@contextmanager
def verified_apple_original_inputs(capture_root: Path, *, expected_source: str,
        keyring: Path, keys_directory: Path, selection_repository_root: Path,
        selection_revision: str, expected_contract_payload_sha256: str):
    """Yield private SDK/Runtime paths during their joined verification lifetime.

    The caller must already authenticate the COMPLETE historical upload capture
    and independently supply its original source/revision, Contract payload and
    public policy. Transport records are preserved, not treated as authority.
    This performs no CI observation, election, signing or package admission.
    Consumers must publish only after successful context exit.
    """
    if expected_source not in ("released-default", "current-runtime"):
        raise ValueError("Original Apple inputs require an exact caller-selected source")
    if any(value is None for value in (keyring, keys_directory, selection_repository_root, selection_revision)):
        raise ValueError("Original Apple inputs require caller policy and exact original Git selection")
    original = Path(capture_root).absolute()
    for path in (original, *original.parents):
        require_regular_directory(path, "Original Apple input capture ancestry")
    before = regular_file_inventory(original, allow_empty=True)
    keyring_bytes = read_regular_file_bytes(keyring, max_bytes=64 * 1024, reject_symlink_parents=True)
    keys_before = regular_file_inventory(keys_directory, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="apple-original-inputs-") as temporary:
        private = Path(temporary).resolve()
        _require_capability_output_separate(private,
            [original, Path(keyring), Path(keys_directory), Path(selection_repository_root)])
        captured, policy = private / "capture", private / "policy"
        snapshot_regular_tree(original, captured, allow_empty=True)
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_before = regular_file_inventory(policy)

        def unchanged():
            for path in (original, *original.parents):
                require_regular_directory(path, "Original Apple input capture ancestry")
            if (regular_file_inventory(original, allow_empty=True) != before
                    or regular_file_inventory(captured, allow_empty=True) != before
                    or read_regular_file_bytes(keyring, max_bytes=64 * 1024, reject_symlink_parents=True) != keyring_bytes
                    or regular_file_inventory(keys_directory, allow_empty=True) != keys_before
                    or regular_file_inventory(policy) != policy_before
                    or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True) != policy_bytes[name]
                           for name, path in policy_paths.items())):
                raise ValueError("Original Apple input capture or caller policy changed during use")

        unchanged()
        try:
            uploaded = captured / "original"
            expected = ({"runtime-original", "current-contract", "sdk-inputs", "selection.json", "transport.json"}
                        if expected_source == "released-default" else {"runtime-capture", "sdk-inputs"})
            if {path.name for path in uploaded.iterdir()} != expected:
                raise ValueError("Original Apple SDK upload differs from the caller-selected source layout")
            with verified_sdk_inputs(uploaded / "sdk-inputs",
                    keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys",
                    selection_repository_root=selection_repository_root, selection_revision=selection_revision,
                    expected_contract_payload_sha256=expected_contract_payload_sha256) as sdk:
                arguments, compatibility = sdk["arguments"], sdk["compatibility"]
                # Keep original scalar selections independent of mutable yielded dictionaries.
                sdk_version = compatibility["sdkVersion"]
                runtime_version = compatibility["runtime"]["defaultRuntimeVersion"]
                contract_version = compatibility["contract"]["version"]
                release_range = arguments["compatible_release_range"]
                compatibility_range = arguments["compatible_runtime_compatibility_range"]
                raw = read_regular_file_bytes(arguments["runtime_metadata_receipt"])
                receipt = load_canonical_json_bytes(raw)
                carrier = (uploaded / "runtime-original" if expected_source == "released-default"
                           else uploaded / "runtime-capture/original")
                carrier = _original_carrier(carrier, sha256_bytes(raw), receipt["buildKey"])
                with verified_runtime_aggregate_handoff(carrier,
                        keyring=arguments["runtime_keyring"], keys_directory=arguments["runtime_keys_directory"]) as runtime:
                    if read_regular_file_bytes(runtime["indexInputs"]["attestation"]) != read_regular_file_bytes(
                            arguments["runtime_attestation"]):
                        raise ValueError("SDK inputs and raw Runtime carrier have different original attestations")
                    for product, component, target in (("contract", "contract", "common"),
                                                       ("runtime", "runtime-aggregate", "aggregate")):
                        identity = PhaseInstanceId(product, component, "metadata", target)
                        if runtime["receiptBytes"][identity] != read_regular_file_bytes(arguments[f"{product}_metadata_receipt"]):
                            raise ValueError("SDK inputs and raw Runtime carrier have different original receipts")
                    unchanged()
                    try:
                        yield {"sdk": sdk, "runtime": runtime}
                    finally:
                        require_sdk_release_selection(selection_repository_root, selection_revision,
                            sdk_version=sdk_version, runtime_version=runtime_version)
                        require_sdk_contract_version(selection_repository_root, selection_revision,
                                                     contract_version=contract_version)
                        require_sdk_runtime_compatibility_policy(selection_repository_root, selection_revision,
                            compatible_release_range=release_range,
                            compatible_runtime_compatibility_range=compatibility_range)
        finally:
            unchanged()
