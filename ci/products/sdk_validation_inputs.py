"""Retain original native SDK evidence; transport is never verifier authority."""

import argparse
import hashlib
import os
from pathlib import Path
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys, require_relative_path,
    _open_regular_file, _stat_identity, sha256_bytes, snapshot_regular_tree,
)
from .receipt import validate_phase_receipt
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME as INPUT_REQUEST_NAME, stage_sdk_inputs
from .sdk_package import _capture_validation_sources, _require_capability_output_separate
from .sdk_validation import decode_sdk_validation_records, sdk_validation_provider
from .signatures import load_keyring, public_key_path


REQUEST_NAME = "sdk-validation-evidence.json"
_TREES = ("packageStage", "runtimeStages", "stagedSdks", "validationStage")
_FILES = ("packageReceipt", "validationReceipt")
_LIMIT = 16 * 1024 * 1024


def _request_inventory(request, *, within=None):
    """Inventory only declared originals, never a key directory's private files."""
    arguments = load_sdk_compatibility_request(request)
    paths = set()

    def contained(path):
        if within is not None:
            require_relative_path(path.relative_to(within).as_posix(), "SDK retained input path")
        return path

    def visit(value):
        if isinstance(value, Path):
            paths.add(contained(value))
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)

    visit({key: value for key, value in arguments.items() if not key.endswith("_keys_directory")})
    for product in ("contract", "runtime"):
        directory = arguments[f"{product}_keys_directory"]
        if directory is not None:
            contained(directory)
            ring = load_keyring(arguments[f"{product}_keyring"], directory)
            for record in ([ring["activeKey"]] if ring["activeKey"] else []) + ring["retiredKeys"]:
                paths.add(public_key_path(directory, record["keyId"]))
    closure = arguments["contract_attestation"].parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
    contained(closure)
    paths.update(closure / item["relativePath"] for item in regular_file_inventory(closure, allow_empty=True))
    result = {}
    for path in paths:
        descriptor, before = _open_regular_file(path, "SDK original input", reject_symlink_parents=True)
        with os.fdopen(descriptor, "rb") as source:
            result[path] = "sha256:" + hashlib.file_digest(source, "sha256").hexdigest()
            if _stat_identity(before) != _stat_identity(os.fstat(source.fileno())):
                raise ValueError("SDK original input changed during inventory")
    return result


def load_sdk_validation_evidence(root: Path):
    """Check the exact retained layout and path confinement; grant no trust."""
    root = Path(root).absolute()
    records = load_canonical_json_bytes(read_regular_file_bytes(root / REQUEST_NAME,
        max_bytes=_LIMIT, reject_symlink_parents=True))
    decoded = decode_sdk_validation_records(root, records)
    expected = {REQUEST_NAME}
    for record in records:
        prefix = Path("originals") / record["receiptSha256"].removeprefix("sha256:")
        exact = {**{name: (prefix / name).as_posix() for name in (*_TREES, *_FILES)},
                 "compatibilityRequest": (prefix / "inputs" / INPUT_REQUEST_NAME).as_posix()}
        if any(record[name] != path for name, path in exact.items()):
            raise ValueError("SDK retained evidence paths differ from their original receipt layout")
        for name in _TREES:
            path = root / record[name]
            expected.update((path / item["relativePath"]).relative_to(root).as_posix()
                            for item in regular_file_inventory(path))
        expected.update(record[name] for name in _FILES)
        validation_bytes = read_regular_file_bytes(root / record["validationReceipt"], reject_symlink_parents=True)
        validation = validate_phase_receipt(load_canonical_json_bytes(validation_bytes))
        if (sha256_bytes(validation_bytes) != record["receiptSha256"] or
                (validation["product"], validation["component"], validation["phase"], validation["target"]) !=
                ("sdk", record["component"], "validation", record["target"])):
            raise ValueError("SDK retained validation receipt differs from record identity")
        inputs = root / prefix / "inputs"
        def relative_paths(value):
            if isinstance(value, dict):
                for member in value.values():
                    relative_paths(member)
            elif isinstance(value, str) and Path(value).is_absolute():
                raise ValueError("SDK retained request contains an absolute path")
        relative_paths(load_canonical_json_bytes(read_regular_file_bytes(root / record["compatibilityRequest"], max_bytes=_LIMIT)))
        inventory = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(inputs / INVENTORY_NAME,
            max_bytes=_LIMIT, reject_symlink_parents=True)), {"schemaVersion", "kind", "files"}, "SDK input inventory")
        if (type(inventory["schemaVersion"]) is not int or inventory["schemaVersion"] != 1 or
                inventory["kind"] != "sdk-inputs" or inventory["files"] !=
                regular_file_inventory(inputs, excluded_paths=(INVENTORY_NAME,), allow_empty=True)):
            raise ValueError("SDK retained compatibility inventory differs from original captured files")
        declared = _request_inventory(decoded[record["receiptSha256"]]["compatibilityRequest"], within=inputs)
        input_paths = {path.relative_to(inputs).as_posix() for path in declared} | {
            INPUT_REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME}
        if input_paths != {item["relativePath"] for item in regular_file_inventory(inputs, allow_empty=True)}:
            raise ValueError("SDK retained compatibility inputs contain undeclared files")
        expected.update((inputs / path).relative_to(root).as_posix() for path in input_paths)
        expected.add((prefix / "original-compatibility-request.json").as_posix())
        load_sdk_compatibility_request(root / prefix / "original-compatibility-request.json")
        source_names = {"capability-claims.tsv", "test-program-source"}
        if record["component"] == "cpp":
            source_names.add("test_installed_package_tamper.py")
        expected.update((prefix / "validation-source" / name).as_posix() for name in source_names)
    if expected != {item["relativePath"] for item in regular_file_inventory(root, allow_empty=True)}:
        raise ValueError("SDK validation carrier contains missing or unexpected files")
    return records


def stage_sdk_validation_evidence(records, source_root: Path, destination: Path, *,
                                  repository: Path, policy_revision: str, tooling):
    """Capture once, verify through the full existing gate, publish immutable bytes."""
    source_root, destination = Path(source_root).absolute(), Path(destination).absolute()
    if destination != Path(os.path.normpath(destination)):
        raise ValueError("SDK evidence destination must be normalized")
    originals = decode_sdk_validation_records(source_root, records)
    retained = (source_root / REQUEST_NAME).exists()
    if retained:
        _require_capability_output_separate(destination, source_root)
    if retained and load_sdk_validation_evidence(source_root) != records:
        raise ValueError("SDK source carrier differs from the requested complete originals")
    retained_inventory = regular_file_inventory(source_root, allow_empty=True) if retained else None
    before = {}
    for digest, record in originals.items():
        request = record["compatibilityRequest"]
        request_files = _request_inventory(request)
        _require_capability_output_separate(destination, [
            *(record[name] for name in (*_TREES, *_FILES, "compatibilityRequest")),
            *request_files,
        ])
        before[digest] = ({name: regular_file_inventory(record[name]) for name in _TREES},
                         {name: read_regular_file_bytes(record[name], max_bytes=_LIMIT, reject_symlink_parents=True)
                          for name in (*_FILES, "compatibilityRequest")}, request_files)
    with tempfile.TemporaryDirectory(prefix="sdk-validation-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()
        captured = []
        for digest, record in originals.items():
            prefix = Path("originals") / digest.removeprefix("sha256:")
            relocated = {name: record[name] for name in ("receiptSha256", "component", "target")}
            for name in _TREES:
                snapshot_regular_tree(record[name], root / prefix / name)
                relocated[name] = (prefix / name).as_posix()
                if regular_file_inventory(root / relocated[name]) != before[digest][0][name]:
                    raise ValueError("SDK original tree changed during capture")
            for name in _FILES:
                path = root / prefix / name
                path.write_bytes(before[digest][1][name])
                relocated[name] = (prefix / name).as_posix()
            original_request = root / prefix / "original-compatibility-request.json"
            original_request.write_bytes(read_regular_file_bytes(source_root / prefix / original_request.name,
                max_bytes=_LIMIT, reject_symlink_parents=True) if retained else before[digest][1]["compatibilityRequest"])
            current_request = root.parent / "current-request.json"
            current_request.write_bytes(before[digest][1]["compatibilityRequest"])
            stage_sdk_inputs(current_request, root / prefix / "inputs",
                             request_directory=record["compatibilityRequest"].parent)
            relocated["compatibilityRequest"] = (prefix / "inputs" / INPUT_REQUEST_NAME).as_posix()
            validation = validate_phase_receipt(load_canonical_json_bytes(before[digest][1]["validationReceipt"]))
            _capture_validation_sources(repository, validation, root / relocated["validationStage"], root / prefix)
            if retained and regular_file_inventory(source_root / prefix / "validation-source") != \
                    regular_file_inventory(root / prefix / "validation-source"):
                raise ValueError("Retained SDK validation source differs from its original Git evidence")
            captured.append(relocated)
        (root / REQUEST_NAME).write_bytes(canonical_json_bytes(captured))
        load_sdk_validation_evidence(root)
        captured_inventory = regular_file_inventory(root, allow_empty=True)
        provider = sdk_validation_provider(root, captured, repository=repository, policy_revision=policy_revision, tooling=tooling)
        for record in captured:
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(root / record["validationReceipt"])))
            provider({**receipt, "receiptSha256": record["receiptSha256"]})
        if regular_file_inventory(root, allow_empty=True) != captured_inventory:
            raise ValueError("Captured SDK evidence changed during full verification")
        for digest, record in originals.items():
            trees, files, inputs = before[digest]
            if (any(regular_file_inventory(record[name]) != trees[name] for name in _TREES) or
                    any(read_regular_file_bytes(record[name], reject_symlink_parents=True) != contents
                        for name, contents in files.items()) or _request_inventory(record["compatibilityRequest"]) != inputs):
                raise ValueError("Original SDK evidence changed before publication")
        load_sdk_validation_evidence(root)
        if retained and regular_file_inventory(source_root, allow_empty=True) != retained_inventory:
            raise ValueError("Retained original SDK carrier changed during capture")
        publish_regular_tree(root, destination)
    return captured


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("request", "source-root", "output", "repository", "tooling"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--policy-revision", required=True)
    args = parser.parse_args(argv)
    try:
        read = lambda path: load_canonical_json_bytes(read_regular_file_bytes(
            path, max_bytes=_LIMIT, reject_symlink_parents=True))
        stage_sdk_validation_evidence(read(args.request), args.source_root, args.output,
            repository=args.repository, policy_revision=args.policy_revision, tooling=read(args.tooling))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
