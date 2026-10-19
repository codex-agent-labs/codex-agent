"""Retain original native SDK evidence; transport is never verifier authority."""

import argparse
from contextvars import ContextVar
from functools import wraps
import hashlib
import os
from pathlib import Path
import tempfile

from .contract_attestation import CONTRACT_EXECUTION_CLOSURE_DIRECTORY
from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, require_exact_keys, require_relative_path, require_regular_directory,
    _open_regular_file, _stat_identity, sha256_bytes, snapshot_regular_tree,
)
from .receipt import validate_phase_receipt
from .restore import memoized_file_inventory as regular_file_inventory, verification_scoped, verification_session
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_inputs import COMPATIBILITY_NAME, INVENTORY_NAME, REQUEST_NAME as INPUT_REQUEST_NAME, stage_sdk_inputs
from .sdk_package import _capture_validation_sources, _require_capability_output_separate
from .sdk_validation import (
    VerifiedSdkValidationProjection, decode_sdk_validation_records,
    sdk_validation_provider as _full_provider,
)
from .signatures import load_keyring, public_key_path
from runtime_reference_transport import count, measured


REQUEST_NAME = "sdk-validation-evidence.json"
_TREES = ("packageStage", "runtimeStages", "stagedSdks", "validationStage", "runtimeAuthorization")
_FILES = ("packageReceipt", "validationReceipt")
_SHARED_TREES = frozenset({"packageStage", "binaryStage", "runtimeStages", "stagedSdks"})
_LIMIT = 16 * 1024 * 1024
_COLLECTION = ContextVar("native_sdk_collection_admission", default=None)


def collection_admission_scope(operation):
    """Reuse full admission only in one private collection, never across runs."""
    @wraps(operation)
    def scoped(*args, **kwargs):
        if _COLLECTION.get() is not None:
            return operation(*args, **kwargs)
        cache = {}
        token = _COLLECTION.set(cache)
        try:
            with verification_session():
                return operation(*args, **kwargs)
        finally:
            _COLLECTION.reset(token)
            cache.clear()
    return scoped


def _admission_subject(root, record, repository, revision, tooling):
    def file(path):
        return sha256_bytes(read_regular_file_bytes(Path(path), max_bytes=128 * 1024**2,
                                                   reject_symlink_parents=True))

    complete = regular_file_inventory(root, allow_empty=True)

    def category(path):
        require_regular_directory(path, "SDK admission category")
        prefix = path.relative_to(root).as_posix() + "/"
        return [{**row, "relativePath": row["relativePath"][len(prefix):]}
                for row in complete if row["relativePath"].startswith(prefix)]

    trees = {name: category(record[name]) for name in (
        "packageStage", "validationStage", "runtimeStages", "stagedSdks", "runtimeAuthorization",
        *(("binaryStage",) if record["component"] == "csharp" else ()))}
    files = {name: file(record[name]) for name in ("packageReceipt", "validationReceipt",
        *(("binaryReceipt",) if record["component"] == "csharp" else ()))}
    # Bind complete signed K/R inputs; paths cannot escape this retained tree.
    inputs = record["compatibilityRequest"].parent
    trees["compatibilityInputs"] = category(inputs)
    _request_paths(record["compatibilityRequest"], within=inputs,
                   input_inventory=trees["compatibilityInputs"])
    files["compatibilityRequest"] = file(record["compatibilityRequest"])
    authority = {name: (None if tooling[name] is None else
        regular_file_inventory(Path(tooling[name]), allow_empty=True) if name in {"evidence", "keysDirectory"}
        else tooling[name] if name == "requiredTrustDomain" else file(tooling[name])) for name in tooling}
    # The fixed Kotlin gate also consumes these mutable checkout files.
    trees["verifierSources"] = regular_file_inventory(Path(repository) / "ci", allow_empty=True)
    if record["component"] == "cpp":
        files["cppVerifier"] = file(Path(repository) / "codex-agent-bindings/cpp/tools/verify_imported_package.py")
    return sha256_bytes(canonical_json_bytes(dict(
        repository=str(Path(repository).resolve(strict=True)), revision=revision,
        receipt=record["receiptSha256"], component=record["component"], target=record["target"],
        trees=trees, files=files, authority=authority)))


def sdk_validation_provider(root, records, *, repository, policy_revision, tooling):
    ordinary = _full_provider(root, records, repository=repository, policy_revision=policy_revision, tooling=tooling)
    cache = _COLLECTION.get()
    if ordinary is None or cache is None:
        return ordinary
    decoded = decode_sdk_validation_records(root, records)
    raw = {row["receiptSha256"]: row for row in records}

    @measured
    def verify_sdk_collection_admission(entry, _verified_object=None):
        if _COLLECTION.get() is not cache:
            raise ValueError("SDK admission proof is outside its private collection lifetime")
        record = decoded.get(entry["receiptSha256"])
        if record is None:
            raise ValueError("SDK admission lacks the exact original receipt")
        key = _admission_subject(root, record, repository, policy_revision, tooling)
        proof = cache.get(key)
        if proof is None:
            # Fresh on a miss: the underlying per-receipt memo cannot hide mutation.
            proof = _full_provider(root, [raw[entry["receiptSha256"]]], repository=repository,
                policy_revision=policy_revision, tooling=tooling)(entry, _verified_object)
            if type(proof) is not VerifiedSdkValidationProjection:
                raise TypeError("SDK admission requires the complete executable gate")
            count("nativeSdkFullAdmissions")
        else:
            count("nativeSdkAdmissionReuses")
        proof.output_inventory(entry["receiptSha256"], entry["outputs"], identity=entry)
        if _admission_subject(root, record, repository, policy_revision, tooling) != key:
            raise ValueError("SDK evidence or verifier authority changed during admission")
        if len(cache) < 25:
            cache[key] = proof
        return proof
    return verify_sdk_collection_admission


def _record_paths(record):
    return (_TREES + (("binaryStage",) if record["component"] == "csharp" else ()),
            _FILES + (("binaryReceipt",) if record["component"] == "csharp" else ()))


def _retained_path(name, target):
    return {"binaryStage": "csharp-binary/stage", "binaryReceipt": "csharp-binary/phase-receipt.json",
            "runtimeAuthorization": f"runtime-authorization/{target}"}.get(name, name)


def _shared_path(name, inventory):
    return Path("shared") / name / sha256_bytes(canonical_json_bytes(inventory)).removeprefix("sha256:")


def _request_paths(request, *, within=None, input_inventory=None):
    """Enumerate declared originals; the caller still authenticates their bytes."""
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
    if input_inventory is None:
        paths.update(closure / item["relativePath"] for item in regular_file_inventory(closure, allow_empty=True))
    else:
        # These bytes already belong to the caller's complete retained inventory.
        # This helper only enumerates paths; it never confers authenticity.
        require_regular_directory(closure, "SDK retained Contract closure")
        prefix = closure.relative_to(within).as_posix() + "/"
        paths.update(within / item["relativePath"] for item in input_inventory
                     if item["relativePath"].startswith(prefix))
    return paths


def _request_inventory(request, *, within=None):
    """Inventory only declared originals, never a key directory's private files."""
    result = {}
    for path in _request_paths(request, within=within):
        descriptor, before = _open_regular_file(path, "SDK original input", reject_symlink_parents=True)
        with os.fdopen(descriptor, "rb") as source:
            result[path] = "sha256:" + hashlib.file_digest(source, "sha256").hexdigest()
            if _stat_identity(before) != _stat_identity(os.fstat(source.fileno())):
                raise ValueError("SDK original input changed during inventory")
    return result


@verification_scoped
def load_sdk_validation_evidence(root: Path):
    """Check the exact retained layout and path confinement; grant no trust."""
    root = Path(root).absolute()
    records = load_canonical_json_bytes(read_regular_file_bytes(root / REQUEST_NAME,
        max_bytes=_LIMIT, reject_symlink_parents=True))
    decoded = decode_sdk_validation_records(root, records)
    complete_inventory = regular_file_inventory(root, allow_empty=True)
    expected = {REQUEST_NAME}
    inventories, checked_inputs = {}, set()

    def inventory(path, *, allow_empty=False):
        key = path, allow_empty
        if key not in inventories:
            require_regular_directory(path, "SDK retained category")
            prefix = path.relative_to(root).as_posix() + "/"
            inventories[key] = [{**row, "relativePath": row["relativePath"][len(prefix):]}
                                for row in complete_inventory if row["relativePath"].startswith(prefix)]
            if not allow_empty and any(row["bytes"] == 0 for row in inventories[key]):
                raise ValueError("SDK retained category contains an empty file")
        return inventories[key]

    for record in records:
        trees, files = _record_paths(record)
        prefix = Path("originals") / record["receiptSha256"].removeprefix("sha256:")
        exact = {**{name: (prefix / _retained_path(name, record["target"])).as_posix() for name in (*trees, *files)},
                 "compatibilityRequest": (prefix / "inputs" / INPUT_REQUEST_NAME).as_posix()}
        for name in _SHARED_TREES & set(trees):
            if record[name].startswith("shared/"):
                exact[name] = _shared_path(name, inventory(root / record[name])).as_posix()
        inputs = (root / record["compatibilityRequest"]).parent
        if record["compatibilityRequest"].startswith("shared/"):
            exact["compatibilityRequest"] = (_shared_path("inputs", inventory(inputs, allow_empty=True)) / INPUT_REQUEST_NAME).as_posix()
        if any(record[name] != path for name, path in exact.items()):
            raise ValueError("SDK retained evidence paths differ from their original receipt layout")
        for name in trees:
            path = root / record[name]
            expected.update((path / item["relativePath"]).relative_to(root).as_posix()
                            for item in inventory(path))
        expected.update(record[name] for name in files)
        validation_bytes = read_regular_file_bytes(root / record["validationReceipt"], reject_symlink_parents=True)
        validation = validate_phase_receipt(load_canonical_json_bytes(validation_bytes))
        if (sha256_bytes(validation_bytes) != record["receiptSha256"] or
                (validation["product"], validation["component"], validation["phase"], validation["target"]) !=
                ("sdk", record["component"], "validation", record["target"])):
            raise ValueError("SDK retained validation receipt differs from record identity")
        def relative_paths(value):
            if isinstance(value, dict):
                for member in value.values():
                    relative_paths(member)
            elif isinstance(value, str) and Path(value).is_absolute():
                raise ValueError("SDK retained request contains an absolute path")
        if inputs not in checked_inputs:
            relative_paths(load_canonical_json_bytes(read_regular_file_bytes(root / record["compatibilityRequest"], max_bytes=_LIMIT)))
            declared_inventory = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(inputs / INVENTORY_NAME,
                max_bytes=_LIMIT, reject_symlink_parents=True)), {"schemaVersion", "kind", "files"}, "SDK input inventory")
            if (type(declared_inventory["schemaVersion"]) is not int or declared_inventory["schemaVersion"] != 1 or
                    declared_inventory["kind"] != "sdk-inputs" or declared_inventory["files"] !=
                    [row for row in inventory(inputs, allow_empty=True) if row["relativePath"] != INVENTORY_NAME]):
                raise ValueError("SDK retained compatibility inventory differs from original captured files")
            # complete_inventory already hashed these exact files. This check
            # needs their declared paths, not another scan of every K/R payload.
            declared = _request_paths(decoded[record["receiptSha256"]]["compatibilityRequest"], within=inputs,
                                      input_inventory=inventory(inputs, allow_empty=True))
            input_paths = {path.relative_to(inputs).as_posix() for path in declared} | {
                INPUT_REQUEST_NAME, COMPATIBILITY_NAME, INVENTORY_NAME}
            if input_paths != {item["relativePath"] for item in inventory(inputs, allow_empty=True)}:
                raise ValueError("SDK retained compatibility inputs contain undeclared files")
            expected.update((inputs / path).relative_to(root).as_posix() for path in input_paths)
            checked_inputs.add(inputs)
        expected.add((prefix / "original-compatibility-request.json").as_posix())
        load_sdk_compatibility_request(root / prefix / "original-compatibility-request.json")
        source_names = {"capability-claims.tsv", "test-program-source"}
        if record["component"] == "cpp":
            source_names.add("test_installed_package_tamper.py")
        expected.update((prefix / "validation-source" / name).as_posix() for name in source_names)
    if expected != {item["relativePath"] for item in complete_inventory}:
        raise ValueError("SDK validation carrier contains missing or unexpected files")
    if complete_inventory != regular_file_inventory(root, allow_empty=True):
        raise ValueError("SDK validation carrier changed during inspection")
    return records


@verification_scoped
@measured
def append_shared_sdk_validation_evidence(source_root: Path, destination: Path):
    """Compact private collected carriers; this grants no semantic authority.

    Only identical complete category inventories share storage. The caller owns
    the unpublished destination and must validate it before publishing it.
    """
    records = load_sdk_validation_evidence(source_root)
    before = regular_file_inventory(source_root, allow_empty=True)
    _require_capability_output_separate(destination, source_root)
    destination.mkdir(parents=True, exist_ok=True)
    require_regular_directory(destination, "Private shared SDK carrier")
    request = destination / REQUEST_NAME
    existing = load_canonical_json_bytes(read_regular_file_bytes(request, max_bytes=_LIMIT,
        reject_symlink_parents=True)) if request.exists() else []
    decoded = decode_sdk_validation_records(destination, existing)
    for record in records:
        if record["receiptSha256"] in decoded:
            raise ValueError("Duplicate original SDK validation during collection")
        prefix = Path("originals") / record["receiptSha256"].removeprefix("sha256:")
        moved = dict(record)
        trees, files = _record_paths(record)
        for name in (*trees, "inputs"):
            source = (source_root / record["compatibilityRequest"]).parent if name == "inputs" else source_root / record[name]
            source_prefix = source.relative_to(source_root).as_posix() + "/"
            expected = [{**row, "relativePath": row["relativePath"][len(source_prefix):]}
                        for row in before if row["relativePath"].startswith(source_prefix)]
            relative = (_shared_path(name, expected) if name in _SHARED_TREES or name == "inputs"
                        else prefix / _retained_path(name, record["target"]))
            target = destination / relative
            if target.exists() or target.is_symlink():
                # The final complete carrier check hashes each shared category
                # once, including its content-addressed path. No cached verdict.
                require_regular_directory(target, "Private shared SDK category")
            else:
                snapshot_regular_tree(source, target, allow_empty=True)
            moved["compatibilityRequest" if name == "inputs" else name] = (
                relative / INPUT_REQUEST_NAME if name == "inputs" else relative).as_posix()
        for name in files:
            target = destination / record[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(read_regular_file_bytes(source_root / record[name], max_bytes=_LIMIT, reject_symlink_parents=True))
        with (destination / prefix / "original-compatibility-request.json").open("xb") as output:
            output.write(read_regular_file_bytes(source_root / prefix / "original-compatibility-request.json", max_bytes=_LIMIT))
        snapshot_regular_tree(source_root / prefix / "validation-source", destination / prefix / "validation-source")
        existing.append(moved)
    if regular_file_inventory(source_root, allow_empty=True) != before:
        raise ValueError("Original SDK carrier changed during compaction")
    request.write_bytes(canonical_json_bytes(sorted(existing, key=lambda row: row["receiptSha256"])))


@measured
def _stage_shared_sdk_validation_evidence(records, source_root, destination, *, repository, policy_revision, tooling):
    """Snapshot an already-retained carrier once; run the full executable gate."""
    if load_sdk_validation_evidence(source_root) != records:
        raise ValueError("SDK source carrier differs from the requested complete originals")
    before = regular_file_inventory(source_root, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="sdk-shared-validation-inputs-") as temporary:
        private = Path(temporary).resolve()
        root = private / "handoff"
        snapshot_regular_tree(source_root, root, allow_empty=True)
        if regular_file_inventory(root, allow_empty=True) != before:
            raise ValueError("Shared SDK carrier changed during capture")
        provider = sdk_validation_provider(root, records, repository=repository, policy_revision=policy_revision, tooling=tooling)
        for record in records:
            receipt = validate_phase_receipt(load_canonical_json_bytes(read_regular_file_bytes(root / record["validationReceipt"])))
            prefix = Path("originals") / record["receiptSha256"].removeprefix("sha256:")
            sources = private / prefix
            sources.mkdir(parents=True)
            _capture_validation_sources(repository, receipt, root / record["validationStage"], sources)
            if regular_file_inventory(sources / "validation-source") != regular_file_inventory(root / prefix / "validation-source"):
                raise ValueError("Retained SDK validation source differs from its original Git evidence")
            provider({**receipt, "receiptSha256": record["receiptSha256"]})
        if (regular_file_inventory(root, allow_empty=True) != before or
                regular_file_inventory(source_root, allow_empty=True) != before):
            raise ValueError("Shared SDK evidence changed during full verification")
        load_sdk_validation_evidence(root)
        publish_regular_tree(root, destination, allow_empty=True)
    return records


@verification_scoped
@measured
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
        # Shared and legacy carriers obey the same retained schema. Rebuilding
        # SDK inputs here repeats product/signature work and creates copies;
        # the existing retained gate checks source, signatures and semantics.
        return _stage_shared_sdk_validation_evidence(records, source_root, destination,
            repository=repository, policy_revision=policy_revision, tooling=tooling)
    before = {}
    for digest, record in originals.items():
        trees, files = _record_paths(record)
        request = record["compatibilityRequest"]
        request_files = _request_inventory(request)
        _require_capability_output_separate(destination, [
            *(record[name] for name in (*trees, *files, "compatibilityRequest")),
            *request_files,
        ])
        before[digest] = ({name: regular_file_inventory(record[name]) for name in trees},
                         {name: read_regular_file_bytes(record[name], max_bytes=_LIMIT, reject_symlink_parents=True)
                          for name in (*files, "compatibilityRequest")}, request_files)
    with tempfile.TemporaryDirectory(prefix="sdk-validation-inputs-") as temporary:
        root = Path(temporary).resolve() / "handoff"
        root.mkdir()
        captured = []
        for digest, record in originals.items():
            trees, files = _record_paths(record)
            prefix = Path("originals") / digest.removeprefix("sha256:")
            relocated = {name: record[name] for name in ("receiptSha256", "component", "target")}
            for name in trees:
                snapshot_regular_tree(record[name], root / prefix / _retained_path(name, record["target"]))
                relocated[name] = (prefix / _retained_path(name, record["target"])).as_posix()
                if regular_file_inventory(root / relocated[name]) != before[digest][0][name]:
                    raise ValueError("SDK original tree changed during capture")
            for name in files:
                path = root / prefix / _retained_path(name, record["target"])
                path.write_bytes(before[digest][1][name])
                relocated[name] = (prefix / _retained_path(name, record["target"])).as_posix()
            original_request = root / prefix / "original-compatibility-request.json"
            original_request.write_bytes(before[digest][1]["compatibilityRequest"])
            current_request = root.parent / "current-request.json"
            current_request.write_bytes(before[digest][1]["compatibilityRequest"])
            stage_sdk_inputs(current_request, root / prefix / "inputs",
                             request_directory=record["compatibilityRequest"].parent)
            relocated["compatibilityRequest"] = (prefix / "inputs" / INPUT_REQUEST_NAME).as_posix()
            validation = validate_phase_receipt(load_canonical_json_bytes(before[digest][1]["validationReceipt"]))
            _capture_validation_sources(repository, validation, root / relocated["validationStage"], root / prefix)
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
            if (any(regular_file_inventory(record[name]) != trees[name] for name in trees) or
                    any(read_regular_file_bytes(record[name], reject_symlink_parents=True) != contents
                        for name, contents in files.items()) or _request_inventory(record["compatibilityRequest"]) != inputs):
                raise ValueError("Original SDK evidence changed before publication")
        load_sdk_validation_evidence(root)
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
