"""Forward five verified original native signatures to the aggregate executor.

This is a layout translation, not current-state/source admission. The executor
still binds these signatures to its elected original bundles and phase receipts.
No payload is rebuilt, signed, or published by this module.
"""

from pathlib import Path
import tempfile

from .inventory import (
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_regular_directory, sha256_bytes,
)
from .registry import NATIVE_TARGETS
from .runtime_aggregate_handoff import _public_policy
from .runtime_attestation import read_runtime_variant_handoff
from .sdk_package import _require_capability_output_separate


def stage_runtime_variant_trust(handoffs: dict[str, Path], destination: Path, *,
                                keyring: Path, keys_directory: Path) -> Path:
    """Atomically publish the executor's exact fifteen original detached files.

Only explicitly supplied caller policy authenticates the complete nine-file
inputs. Retired valid keys remain usable through the existing release reader.
"""
    require_exact_keys(handoffs, set(NATIVE_TARGETS), "Runtime variant handoffs")
    originals = {target: Path(handoffs[target]) for target in NATIVE_TARGETS}
    destination = Path(destination).absolute()
    inputs = [*originals.values(), *(Path(path) for path in (keyring, keys_directory) if path is not None)]

    def output_safe():
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("Runtime variant trust output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "Runtime variant trust output ancestry")
        if destination.exists():
            raise ValueError("Runtime variant trust output must not exist")
        _require_capability_output_separate(destination, inputs)

    output_safe()
    with tempfile.TemporaryDirectory(prefix="runtime-variant-trust-") as temporary:
        private = Path(temporary).resolve()
        policy = private / "policy"
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        staged = private / "variant-trust"
        inventories, expected = {}, []
        for target, source in originals.items():
            # The existing reader captures all nine bounded originals privately
            # and returns verified bytes, never mutable source paths to reread.
            verified = read_runtime_variant_handoff(source, target=target,
                keyring=policy / "product-signing-keys.json", keys_directory=policy / "keys")
            inventories[target] = [{"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)}
                                   for name, raw in sorted(verified["files"].items())]
            stem = Path(verified["attestation"]["payload"]["fileName"]).stem
            for name in (f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub"):
                raw = verified["files"][name]
                relative = f"{target}/{name}"
                path = staged / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                expected.append({"relativePath": relative, "bytes": len(raw), "sha256": sha256_bytes(raw)})
        if (any(regular_file_inventory(originals[target]) != inventory
                for target, inventory in inventories.items())
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in policy_paths.items())
                or regular_file_inventory(staged) != sorted(expected, key=lambda item: item["relativePath"])):
            raise ValueError("Runtime variant originals, caller policy, or staged bytes changed before publication")
        output_safe()
        publish_regular_tree(staged, destination)
    return destination
