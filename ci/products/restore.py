from __future__ import annotations

import argparse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import sys
import tempfile
from typing import Any
import zipfile

from .inventory import (
    _is_windows,
    _open_directory,
    _open_regular_file,
    _stat_identity,
    _windows_directory_path,
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_array,
    require_boolean,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_relative_path,
    require_sha256,
    require_string,
    sha256_bytes,
    snapshot_regular_tree,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import (
    OUTPUT_MANIFEST_NAME,
    validate_output_manifest,
    validate_phase_receipt,
    validate_producer,
    verify_output_manifest,
)
from .registry import PHASE_INSTANCE_IDS, PhaseInstanceId


PHASE_RECEIPT_NAME = "phase-receipt.json"
STAGE_PREFIX = "stage/"
STAGE_MANIFEST_NAME = f"{STAGE_PREFIX}{OUTPUT_MANIFEST_NAME}"
OBJECT_ZIP_LIMITS = {
    "max_archive_bytes": 512 * 1024 * 1024,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 4096,
    "max_entry_bytes": 256 * 1024 * 1024,
    "max_total_bytes": 1024 * 1024 * 1024,
    "max_compression_ratio": 200,
}
PRODUCT_JSON_LIMIT = 16 * 1024 * 1024
REMOTE_SOURCES = {"stable", "promoted-main", "same-pr"}
CARRIER_NAME = "carrier.json"
CARRIER_RESOLUTION_NAME = "resolution.json"
CARRIER_RECORD_KEYS = {
    "product", "component", "phase", "target", "buildKey", "receiptSha256",
    "objectSha256", "transportSha256",
}
CARRIER_RESOLUTION_KEYS = {"schemaVersion", "result", "fullReuse", "phases", "matrices"}
CARRIER_PHASE_KEYS = {
    "product", "component", "phase", "target", "buildKey", "state", "source",
    "transportSource", "receiptSha256", "objectSha256", "misses",
}


class CacheObjectError(ValueError):
    """An occupied cache object is malformed or does not match its qualified identity."""


def _open_safe_regular(path: Path, label: str) -> tuple[int, os.stat_result]:
    if _is_windows():
        _windows_directory_path(Path(path).parent, f"{label} parent")
        return _open_regular_file(path, label)
    return _open_regular_file(path, label, reject_symlink_parents=True)


def _read_safe_regular(path: Path, *, max_bytes: int | None = None) -> bytes:
    if _is_windows():
        _windows_directory_path(Path(path).parent, "File parent")
        return read_regular_file_bytes(path, max_bytes=max_bytes)
    return read_regular_file_bytes(path, max_bytes=max_bytes, reject_symlink_parents=True)


def _absolute(path: Any, label: str) -> Path:
    result = Path(path)
    if not result.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return Path(os.path.abspath(result))


def native_cache_root(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    override = environment.get("CODEX_AGENT_PRODUCT_CACHE")
    if override is not None:
        return _absolute(override, "CODEX_AGENT_PRODUCT_CACHE")

    home_path = _absolute(Path.home() if home is None else home, "Cache home")
    current_platform = sys.platform if platform is None else platform
    if current_platform == "darwin":
        base = home_path / "Library" / "Caches"
    elif current_platform == "win32":
        configured = environment.get("LOCALAPPDATA")
        base = _absolute(configured, "LOCALAPPDATA") if configured is not None else home_path / "AppData" / "Local"
    else:
        configured = environment.get("XDG_CACHE_HOME")
        base = _absolute(configured, "XDG_CACHE_HOME") if configured is not None else home_path / ".cache"
    return base / "codex-agent" / "products"


def _digest_hex(value: Any, label: str) -> str:
    return require_sha256(value, label)[len("sha256:"):]


def object_relative_path(build_key: Any, receipt_sha256: Any) -> str:
    return (
        f"v1/objects/sha256/{_digest_hex(build_key, 'build key')}/"
        f"{_digest_hex(receipt_sha256, 'receipt SHA-256')}.zip"
    )


def transport_relative_path(build_key: Any, receipt_sha256: Any, transport_sha256: Any) -> str:
    return (
        f"v1/transports/sha256/{_digest_hex(build_key, 'build key')}/"
        f"{_digest_hex(receipt_sha256, 'receipt SHA-256')}/"
        f"{_digest_hex(transport_sha256, 'transport SHA-256')}.json"
    )


def _repository(value: Any, label: str) -> str:
    repository = require_relative_path(value, label)
    if repository.count("/") != 1:
        raise ValueError(f"{label} must be an owner/repository pair")
    return repository


def _oid(value: Any, label: str) -> str:
    oid = require_string(value, label)
    if len(oid) != 40 or any(character not in "0123456789abcdef" for character in oid):
        raise ValueError(f"{label} must be 40 lowercase hexadecimal characters")
    return oid


def validate_transport(value: Any) -> dict[str, Any]:
    transport = require_exact_keys(
        value,
        {"schemaVersion", "buildKey", "receiptSha256", "objectSha256", "source", "consumer"},
        "transport",
    )
    if require_integer(transport["schemaVersion"], "transport.schemaVersion", 1) != 1:
        raise ValueError("Unsupported transport schemaVersion")
    build_key = require_sha256(transport["buildKey"], "transport.buildKey")
    receipt_sha256 = require_sha256(transport["receiptSha256"], "transport.receiptSha256")
    require_sha256(transport["objectSha256"], "transport.objectSha256")

    source = transport["source"]
    if type(source) is not dict:
        raise ValueError("transport.source must be an object")
    kind = require_identifier(source.get("kind"), "transport.source.kind")
    if kind in REMOTE_SOURCES:
        source = require_exact_keys(
            source,
            {"kind", "indexSha256", "artifactName", "artifactSha256"},
            "transport.source",
        )
        require_sha256(source["indexSha256"], "transport.source.indexSha256")
        require_relative_path(source["artifactName"], "transport.source.artifactName")
        require_sha256(source["artifactSha256"], "transport.source.artifactSha256")
    elif kind == "local":
        source = require_exact_keys(source, {"kind", "cacheRelativePath"}, "transport.source")
        expected = object_relative_path(build_key, receipt_sha256)
        if require_relative_path(source["cacheRelativePath"], "transport.source.cacheRelativePath") != expected:
            raise ValueError("Local transport cacheRelativePath does not match its receipt-qualified object")
    else:
        raise ValueError("transport.source.kind is unsupported")

    consumer = transport["consumer"]
    if type(consumer) is not dict:
        raise ValueError("transport.consumer must be an object")
    consumer_kind = require_identifier(consumer.get("kind"), "transport.consumer.kind")
    if consumer_kind == "ci":
        consumer = require_exact_keys(consumer, {"kind", "producer"}, "transport.consumer")
        validate_producer(consumer["producer"], "transport.consumer.producer")
    elif consumer_kind == "local":
        consumer = require_exact_keys(
            consumer,
            {"kind", "repository", "commit", "tree"},
            "transport.consumer",
        )
        _repository(consumer["repository"], "transport.consumer.repository")
        _oid(consumer["commit"], "transport.consumer.commit")
        _oid(consumer["tree"], "transport.consumer.tree")
    else:
        raise ValueError("transport.consumer.kind is unsupported")
    return transport


def _carrier_identity(value: Mapping[str, Any], label: str) -> PhaseInstanceId:
    instance = PhaseInstanceId(*(
        require_identifier(value[field], f"{label}.{field}")
        for field in ("product", "component", "phase", "target")
    ))
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"{label} is not a registered product phase")
    return instance


def validate_carrier(value: Any) -> dict[str, Any]:
    carrier = require_exact_keys(
        value, {"schemaVersion", "resolutionSha256", "objects"}, "Product carrier",
    )
    if require_integer(carrier["schemaVersion"], "Product carrier.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product carrier schemaVersion")
    require_sha256(carrier["resolutionSha256"], "Product carrier.resolutionSha256")
    records = require_array(carrier["objects"], "Product carrier.objects")
    identities = []
    for index, value in enumerate(records):
        label = f"Product carrier.objects[{index}]"
        record = require_exact_keys(value, CARRIER_RECORD_KEYS, label)
        identities.append(_carrier_identity(record, label))
        for field in ("buildKey", "receiptSha256", "objectSha256", "transportSha256"):
            require_sha256(record[field], f"{label}.{field}")
    if not records or identities != sorted(set(identities)):
        raise ValueError("Product carrier objects must be nonempty, sorted, and unique")
    return carrier


def _validate_carrier_resolution(
    value: Any,
    expected_instances: tuple[PhaseInstanceId, ...],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    resolution = require_exact_keys(value, CARRIER_RESOLUTION_KEYS, "Product carrier resolution")
    if require_integer(
        resolution["schemaVersion"], "Product carrier resolution.schemaVersion", 1,
    ) != 1 or resolution["result"] != "complete" or require_boolean(
        resolution["fullReuse"], "Product carrier resolution.fullReuse",
    ) is not True:
        raise ValueError("Product carrier resolution is not a complete reuse result")
    matrices = require_exact_keys(
        resolution["matrices"], {"contract", "runtime", "sdk"},
        "Product carrier resolution.matrices",
    )
    if any(require_array(matrices[name], f"Product carrier resolution.matrices.{name}") for name in matrices):
        raise ValueError("Complete product carrier resolution must have empty build matrices")
    phases = []
    identities = []
    for index, value in enumerate(require_array(
        resolution["phases"], "Product carrier resolution.phases",
    )):
        label = f"Product carrier resolution.phases[{index}]"
        phase = require_exact_keys(value, CARRIER_PHASE_KEYS, label)
        instance = _carrier_identity(phase, label)
        identities.append(instance)
        if phase["state"] != "reused" or phase["source"] not in REMOTE_SOURCES | {"local"}:
            raise ValueError("Product carrier resolution contains a non-reused phase")
        if not isinstance(phase["transportSource"], dict) or phase["transportSource"].get("kind") != phase["source"]:
            raise ValueError("Product carrier resolution source and transport disagree")
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(phase[field], f"{label}.{field}")
        require_array(phase["misses"], f"{label}.misses")
        phases.append(phase)
    if tuple(identities) != expected_instances:
        raise ValueError("Product carrier resolution does not match the exact expected phase closure")
    return resolution, phases


def _carrier_expected_instances(values: Any) -> tuple[PhaseInstanceId, ...]:
    instances = tuple(values)
    if not instances or any(
        not isinstance(instance, PhaseInstanceId) or instance not in PHASE_INSTANCE_IDS
        for instance in instances
    ) or instances != tuple(sorted(set(instances))):
        raise ValueError("Expected product carrier phases must be nonempty, sorted, and unique")
    return instances


def verify_carrier(
    root: Path,
    expected_instances: Any,
    consumer: Any,
) -> dict[str, Any]:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Product carrier directory is missing or unsafe")
    expected = _carrier_expected_instances(expected_instances)
    carrier_bytes = _read_safe_regular(root / CARRIER_NAME, max_bytes=PRODUCT_JSON_LIMIT)
    resolution_bytes = _read_safe_regular(
        root / CARRIER_RESOLUTION_NAME, max_bytes=PRODUCT_JSON_LIMIT,
    )
    carrier = validate_carrier(load_canonical_json_bytes(carrier_bytes))
    if carrier["resolutionSha256"] != sha256_bytes(resolution_bytes):
        raise ValueError("Product carrier resolution digest is invalid")
    resolution, phases = _validate_carrier_resolution(
        load_canonical_json_bytes(resolution_bytes), expected,
    )
    records = carrier["objects"]
    if tuple(_carrier_identity(record, "Product carrier object") for record in records) != expected:
        raise ValueError("Product carrier objects do not match the exact expected phase closure")
    expected_consumer = validate_transport({
        "schemaVersion": 1,
        "buildKey": records[0]["buildKey"],
        "receiptSha256": records[0]["receiptSha256"],
        "objectSha256": records[0]["objectSha256"],
        "source": phases[0]["transportSource"],
        "consumer": consumer,
    })["consumer"]
    expected_paths = {CARRIER_NAME, CARRIER_RESOLUTION_NAME}
    verified = []
    for record, phase in zip(records, phases, strict=True):
        for field in ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256"):
            if record[field] != phase[field]:
                raise ValueError("Product carrier object and resolution phase disagree")
        object_path = object_relative_path(record["buildKey"], record["receiptSha256"])
        transport_path = transport_relative_path(
            record["buildKey"], record["receiptSha256"], record["transportSha256"],
        )
        expected_paths.update((object_path, transport_path))
        object_value = verify_object(
            root / object_path,
            build_key=record["buildKey"],
            receipt_sha256=record["receiptSha256"],
            object_sha256=record["objectSha256"],
        )
        if _carrier_identity(object_value["receipt"], "Product carrier receipt") != _carrier_identity(
            record, "Product carrier object",
        ):
            raise ValueError("Product carrier receipt identity is invalid")
        transport_bytes = _read_safe_regular(root / transport_path, max_bytes=PRODUCT_JSON_LIMIT)
        if sha256_bytes(transport_bytes) != record["transportSha256"]:
            raise ValueError("Product carrier transport digest is invalid")
        transport = validate_transport(load_canonical_json_bytes(transport_bytes))
        if (
            transport["buildKey"] != record["buildKey"]
            or transport["receiptSha256"] != record["receiptSha256"]
            or transport["objectSha256"] != record["objectSha256"]
            or transport["source"] != phase["transportSource"]
            or transport["consumer"] != expected_consumer
        ):
            raise ValueError("Product carrier transport does not match its resolution or consumer")
        verified.append({**record, "receipt": object_value["receipt"], "receiptBytes": object_value["receiptBytes"]})
    actual_paths = {record["relativePath"] for record in regular_file_inventory(root)}
    if actual_paths != expected_paths:
        raise ValueError("Product carrier file inventory is incomplete or unexpected")
    return {"carrier": carrier, "resolution": resolution, "objects": verified}


def write_carrier(
    destination: Path,
    resolution: Any,
    expected_instances: Any,
    sources: Mapping[PhaseInstanceId, Path],
    consumer: Any,
) -> dict[str, Any]:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Product carrier destination must not exist")
    expected = _carrier_expected_instances(expected_instances)
    resolution_value, phases = _validate_carrier_resolution(resolution, expected)
    if not isinstance(sources, Mapping) or set(sources) != set(expected):
        raise ValueError("Product carrier sources must exactly match the expected phase closure")
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-carrier-") as temporary:
        root = Path(temporary).resolve() / "carrier"
        root.mkdir()
        resolution_bytes = canonical_json_bytes(resolution_value)
        (root / CARRIER_RESOLUTION_NAME).write_bytes(resolution_bytes)
        records = []
        for instance, phase in zip(expected, phases, strict=True):
            with _verified_object_snapshot(
                Path(sources[instance]),
                build_key=phase["buildKey"],
                receipt_sha256=phase["receiptSha256"],
                object_sha256=phase["objectSha256"],
            ) as (snapshot, verification):
                object_relative = object_relative_path(phase["buildKey"], phase["receiptSha256"])
                object_target = root / object_relative
                object_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(snapshot, object_target)
                if _carrier_identity(verification["receipt"], "Product carrier source receipt") != instance:
                    raise ValueError("Product carrier source receipt identity is invalid")
            transport = validate_transport({
                "schemaVersion": 1,
                "buildKey": phase["buildKey"],
                "receiptSha256": phase["receiptSha256"],
                "objectSha256": phase["objectSha256"],
                "source": phase["transportSource"],
                "consumer": consumer,
            })
            transport_bytes = canonical_json_bytes(transport)
            transport_sha256 = sha256_bytes(transport_bytes)
            transport_target = root / transport_relative_path(
                phase["buildKey"], phase["receiptSha256"], transport_sha256,
            )
            transport_target.parent.mkdir(parents=True, exist_ok=True)
            transport_target.write_bytes(transport_bytes)
            records.append({
                "product": instance.product,
                "component": instance.component,
                "phase": instance.phase,
                "target": instance.target,
                "buildKey": phase["buildKey"],
                "receiptSha256": phase["receiptSha256"],
                "objectSha256": phase["objectSha256"],
                "transportSha256": transport_sha256,
            })
        carrier = validate_carrier({
            "schemaVersion": 1,
            "resolutionSha256": sha256_bytes(resolution_bytes),
            "objects": records,
        })
        write_canonical_json(root / CARRIER_NAME, carrier)
        verify_carrier(root, expected, consumer)
        snapshot_regular_tree(root, destination)
    return verify_carrier(destination, expected, consumer)


def _snapshot_archive(source: Path, destination: Path) -> dict[str, Any]:
    descriptor, before = _open_safe_regular(Path(source), "Product cache object")
    output_descriptor: int | None = None
    try:
        if before.st_size <= 0 or before.st_size > OBJECT_ZIP_LIMITS["max_archive_bytes"]:
            raise ValueError("Product cache object size is outside the fixed bound")
        output_descriptor = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        digest = hashlib.sha256()
        remaining = before.st_size
        with (
            os.fdopen(descriptor, "rb", closefd=False) as input_file,
            os.fdopen(output_descriptor, "wb", closefd=False) as output,
        ):
            while remaining:
                chunk = input_file.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Product cache object was truncated")
                output.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
            if input_file.read(1) or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
                raise ValueError("Product cache object changed while being snapshotted")
            output.flush()
            os.fsync(output_descriptor)
        return {"bytes": before.st_size, "sha256": f"sha256:{digest.hexdigest()}"}
    finally:
        os.close(descriptor)
        if output_descriptor is not None:
            os.close(output_descriptor)


def _validate_receipt_manifest(receipt: dict[str, Any], manifest: dict[str, Any]) -> None:
    for field in ("product", "component", "phase", "target", "productVersion"):
        if receipt[field] != manifest[field]:
            raise ValueError(f"Product receipt and output manifest disagree on {field}")
    if receipt["outputs"] != manifest["outputs"]:
        raise ValueError("Product receipt and output manifest declare different outputs")


def _verify_snapshot(
    archive: Path,
    *,
    build_key: Any,
    receipt_sha256: Any,
    object_identity: dict[str, Any],
    object_sha256: Any | None,
) -> dict[str, Any]:
    expected_build_key = require_sha256(build_key, "expected build key")
    expected_receipt_sha256 = require_sha256(receipt_sha256, "expected receipt SHA-256")
    if object_sha256 is not None and require_sha256(object_sha256, "expected object SHA-256") != object_identity["sha256"]:
        raise ValueError("Product cache object SHA-256 does not match the expected transport identity")

    records, retained, verified_identity = verified_zip_contents(
        archive,
        **OBJECT_ZIP_LIMITS,
        retained_paths={PHASE_RECEIPT_NAME, STAGE_MANIFEST_NAME},
        max_retained_bytes=2 * PRODUCT_JSON_LIMIT,
    )
    if verified_identity != object_identity:
        raise ValueError("Product cache object changed after its bounded snapshot")
    try:
        receipt_bytes = retained[PHASE_RECEIPT_NAME]
        manifest_bytes = retained[STAGE_MANIFEST_NAME]
    except KeyError as error:
        raise ValueError("Product cache object is missing its receipt or output manifest") from error
    if len(receipt_bytes) > PRODUCT_JSON_LIMIT or len(manifest_bytes) > PRODUCT_JSON_LIMIT:
        raise ValueError("Product cache object JSON exceeds the fixed bound")
    if sha256_bytes(receipt_bytes) != expected_receipt_sha256:
        raise ValueError("Product cache object receipt digest does not match its qualified path")
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    manifest = validate_output_manifest(load_canonical_json_bytes(manifest_bytes))
    if receipt["buildKey"] != expected_build_key:
        raise ValueError("Product cache object buildKey does not match its qualified path")
    _validate_receipt_manifest(receipt, manifest)

    expected_records = [
        {
            "relativePath": PHASE_RECEIPT_NAME,
            "bytes": len(receipt_bytes),
            "sha256": expected_receipt_sha256,
        },
        {
            "relativePath": STAGE_MANIFEST_NAME,
            "bytes": len(manifest_bytes),
            "sha256": sha256_bytes(manifest_bytes),
        },
        *[
            {
                "relativePath": f"{STAGE_PREFIX}{output['relativePath']}",
                "bytes": output["bytes"],
                "sha256": output["sha256"],
            }
            for output in manifest["outputs"]
        ],
    ]
    expected_records.sort(key=lambda record: record["relativePath"])
    if records != expected_records:
        raise ValueError("Product cache object does not have the exact receipt-qualified allow-list")
    return {
        "receipt": receipt,
        "receiptBytes": receipt_bytes,
        "manifest": manifest,
        "objectSha256": object_identity["sha256"],
        "objectBytes": object_identity["bytes"],
    }


@contextmanager
def _verified_object_snapshot(
    archive: Path,
    *,
    build_key: Any,
    receipt_sha256: Any,
    object_sha256: Any | None,
) -> Iterator[tuple[Path, dict[str, Any]]]:
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-object-") as temporary:
        snapshot = Path(temporary).resolve() / "object.zip"
        try:
            identity = _snapshot_archive(Path(archive), snapshot)
            verification = _verify_snapshot(
                snapshot,
                build_key=build_key,
                receipt_sha256=receipt_sha256,
                object_identity=identity,
                object_sha256=object_sha256,
            )
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise CacheObjectError(str(error)) from error
        yield snapshot, verification


def verify_object(
    archive: Path,
    *,
    build_key: Any,
    receipt_sha256: Any,
    object_sha256: Any | None = None,
) -> dict[str, Any]:
    with _verified_object_snapshot(
        archive,
        build_key=build_key,
        receipt_sha256=receipt_sha256,
        object_sha256=object_sha256,
    ) as (_, verification):
        return verification


def _extract_verified_stage(archive: Path, verification: dict[str, Any], stage: Path) -> None:
    expected = {
        f"{STAGE_PREFIX}{output['relativePath']}": output
        for output in verification["manifest"]["outputs"]
    }
    expected[STAGE_MANIFEST_NAME] = {
        "relativePath": OUTPUT_MANIFEST_NAME,
        "bytes": len(canonical_json_bytes(verification["manifest"])),
        "sha256": sha256_bytes(canonical_json_bytes(verification["manifest"])),
    }
    stage.mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            if member.filename == PHASE_RECEIPT_NAME:
                continue
            record = expected[member.filename]
            relative = member.filename[len(STAGE_PREFIX):]
            target = stage.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            digest = hashlib.sha256()
            size = 0
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
                0o644,
            )
            try:
                with source.open(member) as input_file, os.fdopen(descriptor, "wb", closefd=False) as output:
                    while chunk := input_file.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                    output.flush()
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
            if size != record["bytes"] or f"sha256:{digest.hexdigest()}" != record["sha256"]:
                raise CacheObjectError(f"Product cache member changed during restore: {member.filename}")
    verify_output_manifest(stage, verification["manifest"])


def restore_object(
    archive: Path,
    destination: Path,
    *,
    build_key: Any,
    receipt_sha256: Any,
    object_sha256: Any | None = None,
) -> dict[str, Any]:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"Product restore destination must not exist: {destination}")
    with _verified_object_snapshot(
        archive,
        build_key=build_key,
        receipt_sha256=receipt_sha256,
        object_sha256=object_sha256,
    ) as (snapshot, verification), tempfile.TemporaryDirectory(
        prefix="codex-agent-product-stage-",
    ) as temporary:
        stage = Path(temporary).resolve() / "stage"
        _extract_verified_stage(snapshot, verification, stage)
        snapshot_regular_tree(stage, destination)
        return {
            "receipt": verification["receipt"],
            "receiptBytes": verification["receiptBytes"],
            "objectSha256": verification["objectSha256"],
        }


def _write_object(stage: Path, receipt_bytes: bytes, output: Path) -> None:
    manifest = validate_output_manifest(
        load_canonical_json_bytes(read_regular_file_bytes(stage / OUTPUT_MANIFEST_NAME)),
    )
    members = [PHASE_RECEIPT_NAME, STAGE_MANIFEST_NAME, *[
        f"{STAGE_PREFIX}{record['relativePath']}" for record in manifest["outputs"]
    ]]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            if name == PHASE_RECEIPT_NAME:
                archive.writestr(info, receipt_bytes)
                continue
            relative = name[len(STAGE_PREFIX):]
            with (stage / relative).open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)
    descriptor = os.open(output, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _files_equal(left: Path, right: Path) -> bool:
    left_descriptor, left_stat = _open_safe_regular(left, "Immutable candidate")
    right_descriptor: int | None = None
    try:
        right_descriptor, right_stat = _open_safe_regular(right, "Immutable entry")
        if left_stat.st_size != right_stat.st_size:
            return False
        with (
            os.fdopen(left_descriptor, "rb", closefd=False) as left_file,
            os.fdopen(right_descriptor, "rb", closefd=False) as right_file,
        ):
            while chunk := left_file.read(1024 * 1024):
                if chunk != right_file.read(len(chunk)):
                    return False
            if right_file.read(1):
                return False
        return (
            _stat_identity(left_stat) == _stat_identity(os.fstat(left_descriptor))
            and _stat_identity(right_stat) == _stat_identity(os.fstat(right_descriptor))
        )
    finally:
        os.close(left_descriptor)
        if right_descriptor is not None:
            os.close(right_descriptor)


def _copy_to_descriptor(source: Path, destination: int) -> None:
    source_descriptor, before = _open_safe_regular(source, "Immutable candidate")
    try:
        with (
            os.fdopen(source_descriptor, "rb", closefd=False) as input_file,
            os.fdopen(destination, "wb", closefd=False) as output,
        ):
            remaining = before.st_size
            while remaining:
                chunk = input_file.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Immutable candidate was truncated")
                output.write(chunk)
                remaining -= len(chunk)
            if input_file.read(1) or _stat_identity(before) != _stat_identity(os.fstat(source_descriptor)):
                raise ValueError("Immutable candidate changed during publication")
            output.flush()
            os.fsync(destination)
    finally:
        os.close(source_descriptor)


def _publish_no_replace(source: Path, target: Path) -> bool:
    if _is_windows():
        parent = _windows_directory_path(target.parent, "Immutable cache parent", create=True)
        descriptor, name = tempfile.mkstemp(prefix=f".{target.name}-", dir=parent)
        temporary = Path(name)
        try:
            _copy_to_descriptor(source, descriptor)
            os.close(descriptor)
            descriptor = -1
            temporary.chmod(0o444)
            try:
                os.link(temporary, target)
                return True
            except FileExistsError:
                return False
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)

    parent = _open_directory(target.parent, "Immutable cache parent", create=True)
    temporary_name = f".{target.name}-{secrets.token_hex(16)}"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
            dir_fd=parent,
        )
        _copy_to_descriptor(source, descriptor)
        os.fchmod(descriptor, 0o444)
        os.close(descriptor)
        descriptor = None
        try:
            os.link(
                temporary_name,
                target.name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
            return True
        except FileExistsError:
            return False
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def store_local_object(stage_root: Path, receipt_path: Path, cache_root: Path) -> dict[str, Any]:
    cache_root = _absolute(cache_root, "Product cache root")
    stage_root = Path(stage_root)
    receipt_path = Path(receipt_path)
    receipt_bytes = _read_safe_regular(receipt_path, max_bytes=PRODUCT_JSON_LIMIT)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    receipt_sha256 = sha256_bytes(receipt_bytes)
    manifest = verify_output_manifest(
        stage_root,
        load_canonical_json_bytes(read_regular_file_bytes(stage_root / OUTPUT_MANIFEST_NAME)),
    )
    _validate_receipt_manifest(receipt, manifest)
    target = cache_root / object_relative_path(receipt["buildKey"], receipt_sha256)

    with tempfile.TemporaryDirectory(prefix="codex-agent-product-store-") as temporary:
        temporary_root = Path(temporary).resolve()
        snapshot = temporary_root / "stage"
        snapshot_regular_tree(stage_root, snapshot)
        verify_output_manifest(snapshot, manifest)
        candidate = temporary_root / "object.zip"
        _write_object(snapshot, receipt_bytes, candidate)
        verification = verify_object(
            candidate,
            build_key=receipt["buildKey"],
            receipt_sha256=receipt_sha256,
        )
        if _read_safe_regular(receipt_path, max_bytes=PRODUCT_JSON_LIMIT) != receipt_bytes:
            raise ValueError("Phase receipt changed during cache object assembly")
        verify_output_manifest(stage_root, manifest)
        published = _publish_no_replace(candidate, target)
        status = "published"
        if not published:
            try:
                existing = verify_object(
                    target,
                    build_key=receipt["buildKey"],
                    receipt_sha256=receipt_sha256,
                )
            except CacheObjectError:
                status = "local-corrupt"
            else:
                if not _files_equal(candidate, target):
                    raise ValueError("Immutable product cache entry conflicts with a valid existing object")
                if existing["objectSha256"] != verification["objectSha256"]:
                    raise ValueError("Immutable product cache entry digest conflict")
                status = "existing"
        return {
            "status": status,
            "path": target,
            "buildKey": receipt["buildKey"],
            "receiptSha256": receipt_sha256,
            "objectSha256": verification["objectSha256"],
        }


def restore_local_object(
    cache_root: Path,
    build_key: Any,
    receipt_sha256: Any,
    destination: Path,
) -> dict[str, Any]:
    cache_root = _absolute(cache_root, "Product cache root")
    relative = object_relative_path(build_key, receipt_sha256)
    archive = cache_root / relative
    try:
        archive.lstat()
    except FileNotFoundError:
        return {"status": "miss", "reason": "local-missing", "path": archive}
    try:
        result = restore_object(
            archive,
            destination,
            build_key=build_key,
            receipt_sha256=receipt_sha256,
        )
    except CacheObjectError:
        return {"status": "miss", "reason": "local-corrupt", "path": archive}
    return {"status": "hit", "reason": "local-hit", "path": archive, **result}


def write_transport(cache_root: Path, value: Any) -> dict[str, Any]:
    cache_root = _absolute(cache_root, "Product cache root")
    transport = validate_transport(value)
    contents = canonical_json_bytes(transport)
    digest = sha256_bytes(contents)
    target = cache_root / transport_relative_path(
        transport["buildKey"],
        transport["receiptSha256"],
        digest,
    )
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-transport-") as temporary:
        candidate = Path(temporary).resolve() / "transport.json"
        candidate.write_bytes(contents)
        published = _publish_no_replace(candidate, target)
        if not published and not _files_equal(candidate, target):
            raise ValueError("Immutable product transport entry conflicts with existing bytes")
    return {"status": "published" if published else "existing", "path": target, "sha256": digest}


def _remove_output(path: str) -> None:
    if path == "-":
        return
    output = Path(path)
    try:
        metadata = output.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISREG(metadata.st_mode):
        output.unlink()


def _write_output(path: str, value: Any) -> None:
    if path == "-":
        sys.stdout.buffer.write(canonical_json_bytes(value))
    else:
        write_canonical_json(Path(path), value)


def _selected_cache_root(value: str | None) -> Path:
    return native_cache_root() if value is None else _absolute(value, "Product cache root")


def _cache_relative(cache_root: Path, path: Path) -> str:
    return Path(path).relative_to(cache_root).as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products restore")
    commands = parser.add_subparsers(dest="command", required=True)

    store = commands.add_parser("store-local")
    store.add_argument("--stage-root", required=True)
    store.add_argument("--receipt", required=True)
    store.add_argument("--cache-root")
    store.add_argument("--output", required=True)

    restore = commands.add_parser("restore-local")
    restore.add_argument("--build-key", required=True)
    restore.add_argument("--receipt-sha256", required=True)
    restore.add_argument("--destination", required=True)
    restore.add_argument("--cache-root")
    restore.add_argument("--output", required=True)

    transport = commands.add_parser("write-transport")
    transport.add_argument("--request", required=True)
    transport.add_argument("--cache-root")
    transport.add_argument("--output", required=True)

    arguments = parser.parse_args(argv)
    try:
        cache_root = _selected_cache_root(arguments.cache_root)
        if arguments.command == "store-local":
            result = store_local_object(
                Path(arguments.stage_root),
                Path(arguments.receipt),
                cache_root,
            )
            output = {
                "schemaVersion": 1,
                "status": result["status"],
                "cacheRelativePath": _cache_relative(cache_root, result["path"]),
                "buildKey": result["buildKey"],
                "receiptSha256": result["receiptSha256"],
                "objectSha256": result["objectSha256"],
            }
        elif arguments.command == "restore-local":
            result = restore_local_object(
                cache_root,
                arguments.build_key,
                arguments.receipt_sha256,
                Path(arguments.destination),
            )
            output = {
                "schemaVersion": 1,
                "status": result["status"],
                "reason": result["reason"],
                "cacheRelativePath": _cache_relative(cache_root, result["path"]),
                "buildKey": require_sha256(arguments.build_key, "build key"),
                "receiptSha256": require_sha256(
                    arguments.receipt_sha256,
                    "receipt SHA-256",
                ),
            }
            if result["status"] == "hit":
                output.update({
                    "objectSha256": result["objectSha256"],
                    "receipt": result["receipt"],
                })
        else:
            request = load_canonical_json_bytes(
                read_regular_file_bytes(
                    Path(arguments.request),
                    max_bytes=PRODUCT_JSON_LIMIT,
                    reject_symlink_parents=True,
                ),
            )
            result = write_transport(cache_root, request)
            output = {
                "schemaVersion": 1,
                "status": result["status"],
                "cacheRelativePath": _cache_relative(cache_root, result["path"]),
                "sha256": result["sha256"],
            }
        _write_output(arguments.output, output)
    except ValueError as error:
        _remove_output(arguments.output)
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
