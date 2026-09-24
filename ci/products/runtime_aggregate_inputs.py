"""Transport complete original aggregate release carriers, never product trust.

The descriptor locates bytes only. Staging authenticates each complete direct
carrier with the existing reader and caller-pinned policy; loading or rebasing
the descriptor is not signature, current-state, or original CI admission.
"""

import os
from pathlib import Path
import tempfile

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_array,
    require_exact_keys, require_relative_path, require_regular_directory,
    require_sha256, sha256_bytes, snapshot_regular_tree,
)
from .registry import PhaseInstanceId
from .runtime_aggregate_handoff import _public_policy, verified_runtime_aggregate_handoff
from .sdk_package import _require_capability_output_separate


REQUEST_NAME = "runtime-aggregate-release-evidence.json"
_METADATA = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")


def _records(records):
    result, roots, digests = [], [], []
    for record in require_array(records, "Runtime aggregate release records"):
        value = require_exact_keys(record, {"receiptSha256", "handoffRoot"}, "Runtime aggregate release record")
        digest = require_sha256(value["receiptSha256"], "Runtime aggregate original receipt")
        relative = require_relative_path(value["handoffRoot"], "Runtime aggregate handoff root")
        path = Path(relative)
        if path.parts[0] == REQUEST_NAME or any(
                path == other or path in other.parents or other in path.parents for other in roots):
            raise ValueError("Runtime aggregate handoff roots overlap")
        roots.append(path)
        digests.append(digest)
        result.append({"receiptSha256": digest, "handoffRoot": relative})
    if digests != sorted(set(digests)):
        raise ValueError("Runtime aggregate release records must be sorted and unique by original receipt")
    return result


def _absolute(path):
    path = Path(path).absolute()
    if path != Path(os.path.normpath(path)):
        raise ValueError("Runtime aggregate transport roots must be normalized")
    return path


def load_runtime_aggregate_release_evidence(root: Path) -> list[dict]:
    """Validate descriptor/path/outer inventory only; this returns no proof."""
    root = _absolute(root)
    for path in (root, *root.parents):
        require_regular_directory(path, "Runtime aggregate transport ancestry")
    records = _records(load_canonical_json_bytes(read_regular_file_bytes(
        root / REQUEST_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)))
    expected = {REQUEST_NAME}
    for record in records:
        source = root / record["handoffRoot"]
        expected.update((source / item["relativePath"]).relative_to(root).as_posix()
                        for item in regular_file_inventory(source, allow_empty=True))
    if expected != {item["relativePath"] for item in regular_file_inventory(root, allow_empty=True)}:
        raise ValueError("Runtime aggregate transport contains missing or unexpected files")
    return records


def rebase_runtime_aggregate_release_records(records, source_root: Path, artifact_root: Path) -> list[dict]:
    """Translate validated explicit paths; do not discover or authenticate."""
    source_root, artifact_root = _absolute(source_root), _absolute(artifact_root)
    return _records([{**record, "handoffRoot": (source_root / record["handoffRoot"])
                     .relative_to(artifact_root).as_posix()} for record in _records(records)])


def stage_runtime_aggregate_release_evidence(records, source_root: Path, destination: Path, *,
                                            keyring: Path, keys_directory: Path) -> list[dict]:
    """Capture full verified originals unchanged and publish a fresh carrier."""
    records = _records(records)
    source_root, destination = _absolute(source_root), _absolute(destination)
    sources = {record["receiptSha256"]: source_root / record["handoffRoot"] for record in records}
    inputs = [*sources.values(), source_root / REQUEST_NAME,
              *(Path(path) for path in (keyring, keys_directory) if path is not None)]

    def output_safe():
        for path in (destination, *destination.parents):
            if path.is_symlink():
                raise ValueError("Runtime aggregate transport output has symbolic ancestry")
            if path.exists():
                require_regular_directory(path, "Runtime aggregate transport output ancestry")
        if destination.exists():
            raise ValueError("Runtime aggregate transport output must not exist")
        _require_capability_output_separate(destination, inputs)

    output_safe()
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-release-inputs-") as temporary:
        private = Path(temporary).resolve()
        policy = private / "policy"
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        captured = private / "evidence"
        captured.mkdir()
        relocated, inventories = [], {}
        for digest, source in sources.items():
            relative = f"handoffs/{digest.removeprefix('sha256:')}"
            with verified_runtime_aggregate_handoff(source, keyring=policy / "product-signing-keys.json",
                                                   keys_directory=policy / "keys") as verified:
                if sha256_bytes(verified["receiptBytes"][_METADATA]) != digest:
                    raise ValueError("Runtime aggregate release record differs from its original metadata receipt")
                snapshot_regular_tree(verified["directory"], captured / relative, allow_empty=True)
                if regular_file_inventory(captured / relative, allow_empty=True) != verified["inventory"]:
                    raise ValueError("Runtime aggregate release changed during capture")
                inventories[digest] = verified["inventory"]
            relocated.append({"receiptSha256": digest, "handoffRoot": relative})
        descriptor_bytes = canonical_json_bytes(relocated)
        (captured / REQUEST_NAME).write_bytes(descriptor_bytes)
        load_runtime_aggregate_release_evidence(captured)
        expected_files = [
            *({**record, "relativePath": f"handoffs/{digest[7:]}/{record['relativePath']}"}
              for digest, inventory in inventories.items() for record in inventory),
            {"relativePath": REQUEST_NAME, "bytes": len(descriptor_bytes),
             "sha256": sha256_bytes(descriptor_bytes)},
        ]
        expected_files.sort(key=lambda record: record["relativePath"])
        if (any(regular_file_inventory(source, allow_empty=True) != inventories[digest]
                or regular_file_inventory(captured / f"handoffs/{digest[7:]}", allow_empty=True) != inventories[digest]
                for digest, source in sources.items())
                or regular_file_inventory(captured, allow_empty=True) != expected_files
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in policy_paths.items())):
            raise ValueError("Runtime aggregate originals or caller policy changed before publication")
        output_safe()
        publish_regular_tree(captured, destination, allow_empty=True,
                             expected_inventory=expected_files)
    return relocated


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keyring", type=Path, required=True)
    parser.add_argument("--keys-directory", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        records = load_canonical_json_bytes(read_regular_file_bytes(
            arguments.request, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        stage_runtime_aggregate_release_evidence(records, arguments.source_root, arguments.output,
            keyring=arguments.keyring, keys_directory=arguments.keys_directory)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    # The full retained reader uses existing CI callers in the products.*
    # namespace. Preserve their opaque identity types for module-mode entry.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from products.runtime_aggregate_inputs import main
    raise SystemExit(main())
