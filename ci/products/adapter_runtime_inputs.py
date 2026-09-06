"""Transport original adapter K/R evidence; never product or release authority."""

import argparse
import os
from pathlib import Path
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_relative_path,
    snapshot_regular_tree,
)
from .receipt import validate_phase_receipt
from .runtime_adapter_content import (
    adapter_comparison_provider, decode_adapter_comparison_records,
    map_adapter_comparison_record,
)
from .sdk_inputs import _copy_file
from .signatures import load_keyring, public_key_path


REQUEST_NAME = "adapter-runtime-evidence.json"
_STAGES = ("adapter_package_stage", "native_package_stage", "validation_stage")


def _public_keys(keyring: Path, directory: Path) -> list[Path]:
    ring = load_keyring(keyring, directory)
    keys = ([ring["activeKey"]] if ring["activeKey"] else []) + ring["retiredKeys"]
    return [public_key_path(directory, key["keyId"]) for key in keys]


def _key_directories(inputs) -> dict[Path, Path]:
    result = {}
    for product in ("contract", "aggregate", "variant"):
        directory, keyring = inputs.get(f"{product}_keys_directory"), inputs.get(f"{product}_keyring")
        if directory is not None:
            if keyring is None or directory in result and result[directory] != keyring:
                raise ValueError("Adapter public key directory lacks one exact declared keyring")
            result[directory] = keyring
    return result


def load_adapter_runtime_evidence(root: Path) -> list[dict]:
    """Read an exact carrier inventory, without authenticating or issuing a token."""
    root = Path(root)
    records = load_canonical_json_bytes(read_regular_file_bytes(
        root / REQUEST_NAME, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    decoded = decode_adapter_comparison_records(root, records)
    expected = {REQUEST_NAME}
    for record in records:
        arguments = decoded[record["receiptSha256"]]
        directories = {arguments[name] for name in _STAGES}
        keys = _key_directories(arguments["aggregate_inputs"])

        def declared(value):
            path = root / require_relative_path(value, "Adapter carrier path")
            if path in directories:
                expected.update((path / item["relativePath"]).relative_to(root).as_posix()
                                for item in regular_file_inventory(path))
            elif path in keys:
                expected.update(key.relative_to(root).as_posix() for key in _public_keys(keys[path], path))
            else:
                expected.add(path.relative_to(root).as_posix())
            return value

        map_adapter_comparison_record(record, declared)
        closure = arguments["aggregate_inputs"]["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        expected.update((closure / item["relativePath"]).relative_to(root).as_posix()
                        for item in regular_file_inventory(closure, allow_empty=True))
    # Original Contract raw execution logs may be empty; staged product files above may not.
    if expected != {item["relativePath"] for item in regular_file_inventory(root, allow_empty=True)}:
        raise ValueError("Adapter Runtime handoff contains missing or unexpected files")
    return records


def stage_adapter_runtime_evidence(records, source_root: Path, destination: Path, *,
                                   keyring: Path | None = None, keys_directory: Path | None = None) -> list[dict]:
    """Snapshot declared originals, authenticate the complete capture, publish once."""
    source_root, destination = Path(source_root).absolute(), Path(destination).absolute()
    if destination != Path(os.path.normpath(destination)):
        raise ValueError("Adapter evidence destination must be normalized")
    if (keyring is None) != (keys_directory is None):
        raise ValueError("Adapter release capture requires both caller-pinned trust paths")
    decode_adapter_comparison_records(source_root, records)
    originals = []
    for record in records:
        original = map_adapter_comparison_record(record, lambda value:
            source_root / require_relative_path(value, "Adapter original path"))
        inputs = original["aggregateInputs"]
        if inputs["required_trust_domain"] == "release":
            if keyring is None:
                raise ValueError("Release adapter handoff requires caller-pinned product keys")
            inputs.update({f"{product}_{suffix}": Path(value).absolute()
                           for product in ("contract", "aggregate", "variant")
                           for suffix, value in (("keyring", keyring), ("keys_directory", keys_directory))})

        def disjoint(path):
            for source, output in ((path, destination), (path.resolve(strict=False), destination.resolve(strict=False))):
                if source == output or source in output.parents or output in source.parents:
                    raise ValueError("Adapter evidence destination overlaps original inputs")
            return path

        map_adapter_comparison_record(original, disjoint)
        for attestation in (inputs["contract_attestation"], inputs["aggregate_attestation"],
                            *inputs["variant_attestations"].values()):
            disjoint(attestation.parent)
        originals.append(original)

    with tempfile.TemporaryDirectory(prefix="adapter-runtime-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()
        files, trees, public_directories = {}, {}, {}
        closure_pairs = set()
        relocated = []
        for original in originals:
            prefix = Path("originals") / original["receiptSha256"].removeprefix("sha256:")
            directories = {original[name] for name in ("adapterPackageStage", "nativePackageStage", "validationStage")}
            keys = _key_directories(original["aggregateInputs"])

            def capture(source):
                if source in directories:
                    if source not in trees:
                        path = prefix / "stages" / str(len(trees)) / source.name
                        snapshot_regular_tree(source, root / path)
                        trees[source] = path
                    return trees[source].as_posix()
                if source in keys:
                    pair = (source, keys[source])
                    if pair not in public_directories:
                        path = prefix / "public-keys" / str(len(public_directories))
                        (root / path).mkdir(parents=True)
                        for key in _public_keys(keys[source], source):
                            _copy_file(key, root / path / key.name)
                        public_directories[pair] = path
                    return public_directories[pair].as_posix()
                if source not in files:
                    name = require_relative_path(source.name, "Adapter original basename")
                    path = prefix / "files" / str(len(files)) / name
                    _copy_file(source, root / path, max_bytes=1024 * 1024 * 1024)
                    files[source] = path
                return files[source].as_posix()

            captured = map_adapter_comparison_record(original, capture)
            source_closure = original["aggregateInputs"]["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
            destination_closure = Path(captured["aggregateInputs"]["contract_attestation"]).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
            pair = (source_closure, destination_closure)
            if pair not in closure_pairs:
                snapshot_regular_tree(source_closure, root / destination_closure)
                closure_pairs.add(pair)
            relocated.append(captured)

        provider = adapter_comparison_provider(root, relocated, keyring=keyring, keys_directory=keys_directory)
        captured_arguments = decode_adapter_comparison_records(root, relocated)
        for record in relocated:
            arguments = captured_arguments[record["receiptSha256"]]
            paths = [member["receipt"] for member in arguments["aggregate_inputs"]["adapter_receipts"]
                     if (member["component"], member["phase"], member["target"]) ==
                     (record["component"], "validation", record["target"])]
            if len(paths) != 1:
                raise ValueError("Adapter capture lacks one exact original host validation receipt")
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(
                paths[0], max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)))
            provider({**receipt, "receiptSha256": record["receiptSha256"]}, None).output_inventory(
                record["receiptSha256"], receipt["outputs"], identity=receipt)
        (root / REQUEST_NAME).write_bytes(canonical_json_bytes(relocated))
        load_adapter_runtime_evidence(root)
        publish_regular_tree(root, destination)
    return relocated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keyring", type=Path)
    parser.add_argument("--keys-directory", type=Path)
    args = parser.parse_args(argv)
    try:
        records = load_canonical_json_bytes(read_regular_file_bytes(
            args.request, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        stage_adapter_runtime_evidence(records, args.source_root, args.output,
                                      keyring=args.keyring, keys_directory=args.keys_directory)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
