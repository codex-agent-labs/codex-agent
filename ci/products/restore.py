from __future__ import annotations

import argparse
import ctypes
import errno
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar, copy_context
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from functools import wraps
import hashlib
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import sys
import tempfile
import threading
from typing import Any
import zipfile

from .inventory import (
    PRODUCT_JSON_LIMIT,
    _directory_inventory,
    _is_windows,
    _is_reparse_point,
    _open_created_directory,
    _open_directory,
    _open_regular_file,
    _rename_directory_noreplace,
    _validate_snapshot_source,
    _stat_identity,
    _windows_directory_path,
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory as _uncached_file_inventory,
    require_array,
    require_boolean,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_relative_path,
    require_sha256,
    require_string,
    sha256_bytes,
    publish_regular_tree,
    require_sorted_unique_records,
    snapshot_regular_tree,
    validate_file_record,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import (
    OUTPUT_MANIFEST_NAME,
    validate_output_manifest,
    validate_phase_receipt,
    validate_producer,
    verify_output_manifest,
    write_phase_receipt,
)
from .registry import PHASE_INSTANCE_IDS, PhaseInstanceId


PHASE_RECEIPT_NAME = "phase-receipt.json"
STAGE_PREFIX = "stage/"
STAGE_MANIFEST_NAME = f"{STAGE_PREFIX}{OUTPUT_MANIFEST_NAME}"
OBJECT_ZIP_LIMITS = {
    # SDK-iOS binary stages contain two ~1.9 GB frameworks and two ~608 MB KLIBs.
    "max_archive_bytes": 8 * 1024 * 1024 * 1024,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 4096,
    "max_entry_bytes": 2 * 1024 * 1024 * 1024,
    "max_total_bytes": 8 * 1024 * 1024 * 1024,
    "max_compression_ratio": 200,
}
REMOTE_SOURCES = {"stable", "promoted-main", "same-pr"}
CARRIER_NAME = "carrier.json"
CARRIER_RESOLUTION_NAME = "resolution.json"
CARRIER_REFERENCES_NAME = "object-references.json"
CARRIER_RECORD_KEYS = {
    "product", "component", "phase", "target", "buildKey", "receiptSha256",
    "objectSha256", "transportSha256",
}
CARRIER_RESOLUTION_KEYS = {"schemaVersion", "result", "fullReuse", "phases", "matrices"}
CARRIER_PHASE_KEYS = {
    "product", "component", "phase", "target", "buildKey", "state", "source",
    "transportSource", "receiptSha256", "objectSha256", "misses",
}
PHASE_PLAN_KEYS = {
    "schemaVersion", "product", "component", "phase", "target", "buildKey", "inputs",
}
PHASE_SHARD_NAME = "phase-object.json"
PHASE_SHARD_KEYS = {
    "schemaVersion", "product", "component", "phase", "target", "buildKey",
    "receiptSha256", "objectSha256", "objectPath",
}


class CacheObjectError(ValueError):
    """An occupied cache object is malformed or does not match its qualified identity."""


_VERIFICATION_SESSION = ContextVar("product_verification_session", default=None)
_VERIFICATION_CACHE_BYTES = 4 * 1024 * 1024 * 1024


@contextmanager
def verification_session():
    """Private process custody, never a serialized assertion of trust.

    Only completed byte verification is memoized. Receipt SHA binds the exact
    original producer; all signature, policy and original-CI admission remains
    with the existing caller. Mutable source files are checked on every hit.
    """
    current = _VERIFICATION_SESSION.get()
    if current is not None:
        yield current
        return
    with tempfile.TemporaryDirectory(prefix="codex-agent-verified-objects-") as temporary:
        session = {"root": Path(temporary).resolve(), "objects": {}, "bytes": 0,
                   "stages": {}, "uploads": {}, "uploadBytes": 0, "limit": _VERIFICATION_CACHE_BYTES,
                   "lock": threading.RLock(), "hits": 0, "misses": 0}
        token = _VERIFICATION_SESSION.set(session)
        try:
            import reuse_qualification
            reuse_qualification.configure(session, os.environ)
            yield session
        finally:
            _VERIFICATION_SESSION.reset(token)


def verification_scoped(operation):
    @wraps(operation)
    def scoped(*args, **kwargs):
        with verification_session():
            return operation(*args, **kwargs)
    return scoped


def bounded_verify(operation, values):
    """Independent scans only; preserve order and propagate every failure."""
    values = tuple(values)
    if len(values) < 2:
        return [operation(value) for value in values]
    with ThreadPoolExecutor(max_workers=min(4, len(values))) as executor:
        futures = [executor.submit(copy_context().run, operation, value) for value in values]
        return [future.result() for future in futures]


def memoized_file_inventory(root, *, allow_empty=False, excluded_paths=()):
    """Reuse byte scans under private custody; never memoize authentication.

    Every phase/receipt/signature/provenance gate still checks these byte hashes
    against its own exact immutable identity. No disk cache marker is accepted.
    """
    session = None if _is_windows() else _VERIFICATION_SESSION.get()
    if session is None:
        return _uncached_file_inventory(root, allow_empty=allow_empty, excluded_paths=excluded_paths)
    excluded_paths = tuple(excluded_paths)
    before = _stage_fingerprint(Path(root))
    key = (before, allow_empty, excluded_paths)
    with session["lock"]:
        cached = session.setdefault("inventories", {}).get(key)
    records = (deepcopy(cached) if cached is not None else
               _uncached_file_inventory(root, allow_empty=allow_empty, excluded_paths=excluded_paths))
    if _stage_fingerprint(Path(root)) != before:
        raise ValueError("Verified byte inventory changed during reuse")
    if cached is None:
        with session["lock"]:
            # ponytail: bound metadata too; larger trees keep the full scanner.
            if session.get("inventoryMembers", 0) + len(before) <= 65_536:
                session["inventories"][key] = deepcopy(records)
                session["inventoryMembers"] = session.get("inventoryMembers", 0) + len(before)
    return records


regular_file_inventory = memoized_file_inventory


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
    elif kind == "phase-shard":
        source = require_exact_keys(
            source, {"kind", "descriptorSha256", "producer"}, "transport.source",
        )
        require_sha256(source["descriptorSha256"], "transport.source.descriptorSha256")
        validate_producer(source["producer"], "transport.source.producer")
    else:
        raise ValueError("transport.source.kind is unsupported")

    consumer = transport["consumer"]
    if type(consumer) is not dict:
        raise ValueError("transport.consumer must be an object")
    consumer_kind = require_identifier(consumer.get("kind"), "transport.consumer.kind")
    if consumer_kind == "ci":
        consumer = require_exact_keys(consumer, {"kind", "producer"}, "transport.consumer")
        validate_producer(consumer["producer"], "transport.consumer.producer")
        if consumer["producer"]["event"] == "local":
            raise ValueError("CI transport consumer requires a hosted producer")
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
        if phase["state"] != "reused" or phase["source"] not in REMOTE_SOURCES | {"local", "phase-shard"}:
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


@verification_scoped
def verify_carrier(
    root: Path,
    expected_instances: Any,
    consumer: Any,
    *, object_root: Path | None = None, selected_instances=None, completed_frozen=None,
) -> dict[str, Any]:
    """Verify a carrier, or explicitly return only a caller-selected object view.

    A selected view authenticates no other object. Full admission callers leave
    selected_instances unset. All carrier controls and path structure still check;
    a selected view may omit only unselected object bodies, never controls.
    """
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Carrier completion requires native semantic evidence")
        completed_frozen.check_consumer(consumer)
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Product carrier directory is missing or unsafe")
    expected = _carrier_expected_instances(expected_instances)
    selected = expected if selected_instances is None else _carrier_expected_instances(selected_instances)
    if not set(selected).issubset(expected):
        raise ValueError("Selected carrier view is outside its expected closure")
    before = _stage_fingerprint(root) if selected_instances is not None and not _is_windows() else None
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
    references = {}
    if (root / CARRIER_REFERENCES_NAME).exists() or (root / CARRIER_REFERENCES_NAME).is_symlink():
        if object_root is None:
            raise ValueError("Referenced carrier requires a caller-owned object root")
        references = require_exact_keys(load_canonical_json_bytes(_read_safe_regular(
            root / CARRIER_REFERENCES_NAME, max_bytes=PRODUCT_JSON_LIMIT)),
            {object_relative_path(record["buildKey"], record["receiptSha256"]) for record in records},
            "Product carrier object references")
        for path in references.values():
            require_relative_path(path, "Product carrier original object path")
        expected_paths.add(CARRIER_REFERENCES_NAME)
    def verify_member(pair):
        record, phase = pair
        for field in ("product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256"):
            if record[field] != phase[field]:
                raise ValueError("Product carrier object and resolution phase disagree")
        object_path = object_relative_path(record["buildKey"], record["receiptSha256"])
        transport_path = transport_relative_path(
            record["buildKey"], record["receiptSha256"], record["transportSha256"],
        )
        source = (Path(object_root) / references[object_path]) if references else root / object_path
        object_value = (completed_frozen.envelope(record)
                        if completed_frozen is not None and references else None)
        if object_value is None:
            object_value = verify_object(
                source,
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
        return {**record, "receipt": object_value["receipt"], "receiptBytes": object_value["receiptBytes"],
                **({"originalObjectPath": references[object_path]} if references else {})}
    optional_paths = set()
    for record in records:
        if not references:
            path = object_relative_path(record["buildKey"], record["receiptSha256"])
            expected_paths.add(path)
            if selected_instances is not None and _carrier_identity(record, 'Carrier object') not in selected:
                optional_paths.add(path)
        expected_paths.add(transport_relative_path(record["buildKey"], record["receiptSha256"], record["transportSha256"]))
    verified = bounded_verify(verify_member, (
        pair for pair in zip(records, phases, strict=True)
        if _carrier_identity(pair[0], "Selected carrier object") in selected))
    actual_paths = ({Path(path).relative_to(root).as_posix() for path, _ in before if Path(path).is_file()}
                    if before is not None else
                    {record["relativePath"] for record in regular_file_inventory(root)})
    if not expected_paths - optional_paths <= actual_paths <= expected_paths:
        raise ValueError("Product carrier file inventory is incomplete or unexpected")
    if before is not None and _stage_fingerprint(root) != before:
        raise ValueError("Selected carrier view changed during verification")
    if selected_instances is not None:
        # Return a visibly scoped control view, never a full-carrier admission.
        resolution = {**resolution, "phases": [phase for phase in phases
            if _carrier_identity(phase, "Selected carrier phase") in selected]}
        carrier = {**carrier, "objects": [record for record in records
            if _carrier_identity(record, "Selected carrier object") in selected],
            "resolutionSha256": sha256_bytes(canonical_json_bytes(resolution))}
    return {"carrier": carrier, "resolution": resolution, "objects": verified}


@verification_scoped
def write_carrier(
    destination: Path,
    resolution: Any,
    expected_instances: Any,
    sources: Mapping[PhaseInstanceId, Path],
    consumer: Any,
    *, object_root: Path | None = None, completed_frozen=None,
) -> dict[str, Any]:
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Carrier completion requires native semantic evidence")
        completed_frozen.check_consumer(consumer)
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
        records, references = [], {}
        for instance, phase in zip(expected, phases, strict=True):
            completed = (completed_frozen.envelope(phase)
                         if completed_frozen is not None and object_root is not None else None)
            with (nullcontext((None, completed)) if completed is not None else _verified_object_snapshot(
                Path(sources[instance]),
                build_key=phase["buildKey"],
                receipt_sha256=phase["receiptSha256"],
                object_sha256=phase["objectSha256"],
                require_snapshot=object_root is None,
            )) as (snapshot, verification):
                object_relative = object_relative_path(phase["buildKey"], phase["receiptSha256"])
                if object_root is None:
                    object_target = root / object_relative
                    object_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(snapshot, object_target)
                else:
                    references[object_relative] = require_relative_path(
                        Path(sources[instance]).relative_to(object_root).as_posix(),
                        "Product carrier original object path")
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
        if object_root is not None:
            write_canonical_json(root / CARRIER_REFERENCES_NAME, references)
        verify_carrier(root, expected, consumer, object_root=object_root,
                       **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))
        snapshot_regular_tree(root, destination)
    return verify_carrier(destination, expected, consumer, object_root=object_root,
                          **({"completed_frozen": completed_frozen} if completed_frozen is not None else {}))


@verification_scoped
def verify_phase_shard(root: Path, expected_instance: PhaseInstanceId, *, completed_frozen=None) -> dict[str, Any]:
    """Verify a body, or explicit native semantic completion of an absent frozen body.

    The latter keeps only exact descriptor/receipt controls. It never verifies
    present body bytes by inference; physical consumers still use restore_object.
    """
    if completed_frozen is not None:
        from reuse_qualification import CompletedFrozenReuse
        if type(completed_frozen) is not CompletedFrozenReuse:
            raise ValueError("Deferred shard requires native semantic evidence")
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Product phase shard directory is missing or unsafe")
    if not isinstance(expected_instance, PhaseInstanceId) or expected_instance not in PHASE_INSTANCE_IDS:
        raise ValueError("Expected product phase shard identity is invalid")
    descriptor_bytes = _read_safe_regular(root / PHASE_SHARD_NAME, max_bytes=PRODUCT_JSON_LIMIT)
    descriptor = require_exact_keys(
        load_canonical_json_bytes(descriptor_bytes),
        PHASE_SHARD_KEYS,
        "Product phase shard",
    )
    if require_integer(descriptor["schemaVersion"], "Product phase shard.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product phase shard schemaVersion")
    if _carrier_identity(descriptor, "Product phase shard") != expected_instance:
        raise ValueError("Product phase shard identity is invalid")
    build_key = require_sha256(descriptor["buildKey"], "Product phase shard.buildKey")
    receipt_sha256 = require_sha256(
        descriptor["receiptSha256"], "Product phase shard.receiptSha256",
    )
    object_sha256 = require_sha256(
        descriptor["objectSha256"], "Product phase shard.objectSha256",
    )
    object_path = object_relative_path(build_key, receipt_sha256)
    if require_relative_path(descriptor["objectPath"], "Product phase shard.objectPath") != object_path:
        raise ValueError("Product phase shard object path is invalid")
    receipt_bytes = _read_safe_regular(root / PHASE_RECEIPT_NAME, max_bytes=PRODUCT_JSON_LIMIT)
    if sha256_bytes(receipt_bytes) != receipt_sha256:
        raise ValueError("Product phase shard receipt digest is invalid")
    if (completed_frozen is not None and not (root / object_path).exists()
            and not (root / object_path).is_symlink()):
        completed = completed_frozen.envelope(descriptor, receipt_bytes)
        if completed is not None:
            expected_controls = sorted([
                {"relativePath": PHASE_SHARD_NAME, "bytes": len(descriptor_bytes), "sha256": sha256_bytes(descriptor_bytes)},
                {"relativePath": PHASE_RECEIPT_NAME, "bytes": len(receipt_bytes), "sha256": receipt_sha256}],
                key=lambda row: row["relativePath"])
            if regular_file_inventory(root) != expected_controls:
                raise ValueError("Deferred shard has unexpected controls or body content")
            return {**descriptor, "receipt": completed["receipt"], "receiptBytes": receipt_bytes}
    verified = verify_object(
        root / object_path,
        build_key=build_key,
        receipt_sha256=receipt_sha256,
        object_sha256=object_sha256,
    )
    if verified["receiptBytes"] != receipt_bytes or _carrier_identity(
        verified["receipt"], "Product phase shard receipt",
    ) != expected_instance:
        raise ValueError("Product phase shard receipt is invalid")
    expected_files = sorted((
        {
            "relativePath": PHASE_SHARD_NAME,
            "bytes": len(descriptor_bytes),
            "sha256": sha256_bytes(descriptor_bytes),
        },
        {
            "relativePath": PHASE_RECEIPT_NAME,
            "bytes": len(receipt_bytes),
            "sha256": receipt_sha256,
        },
        {
            "relativePath": object_path,
            "bytes": verified["objectBytes"],
            "sha256": object_sha256,
        },
    ), key=lambda record: record["relativePath"])
    if regular_file_inventory(root) != expected_files:
        raise ValueError("Product phase shard file inventory is incomplete or unexpected")
    if (
        _read_safe_regular(root / PHASE_SHARD_NAME, max_bytes=PRODUCT_JSON_LIMIT) != descriptor_bytes
        or _read_safe_regular(root / PHASE_RECEIPT_NAME, max_bytes=PRODUCT_JSON_LIMIT) != receipt_bytes
    ):
        raise ValueError("Product phase shard control files changed during verification")
    final_object = verify_object(
        root / object_path,
        build_key=build_key,
        receipt_sha256=receipt_sha256,
        object_sha256=object_sha256,
    )
    if (
        final_object["objectBytes"] != verified["objectBytes"]
        or final_object["receiptBytes"] != receipt_bytes
    ):
        raise ValueError("Product phase shard object changed during verification")
    return {**descriptor, "receipt": verified["receipt"], "receiptBytes": receipt_bytes}


def finalize_phase_object(
    *,
    stage_root: Path,
    phase_plan: Any,
    producer: Any,
    product_version: Any,
    trust_domain: Any,
    destination: Path,
) -> dict[str, Any]:
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Product phase shard destination must not exist")
    plan = require_exact_keys(phase_plan, PHASE_PLAN_KEYS, "Product phase plan")
    if require_integer(plan["schemaVersion"], "Product phase plan.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product phase plan schemaVersion")
    instance = _carrier_identity(plan, "Product phase plan")
    build_key = require_sha256(plan["buildKey"], "Product phase plan.buildKey")
    validate_producer(producer, "Product phase producer")
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-phase-") as temporary:
        root = Path(temporary).resolve() / "shard"
        root.mkdir()
        receipt = write_phase_receipt(
            stage_root,
            root,
            instance.product,
            instance.component,
            instance.phase,
            instance.target,
            product_version,
            build_key,
            plan["inputs"],
            producer,
            trust_domain,
        )
        stored = store_local_object(stage_root, root / PHASE_RECEIPT_NAME, root)
        if stored["status"] != "published":
            raise ValueError("Fresh product phase object was not newly published")
        descriptor = require_exact_keys({
            "schemaVersion": 1,
            "product": instance.product,
            "component": instance.component,
            "phase": instance.phase,
            "target": instance.target,
            "buildKey": build_key,
            "receiptSha256": stored["receiptSha256"],
            "objectSha256": stored["objectSha256"],
            "objectPath": object_relative_path(build_key, stored["receiptSha256"]),
        }, PHASE_SHARD_KEYS, "Product phase shard")
        write_canonical_json(root / PHASE_SHARD_NAME, descriptor)
        verified = verify_phase_shard(root, instance)
        if verified["receipt"] != receipt:
            raise ValueError("Product phase shard receipt changed during finalization")
        snapshot_regular_tree(root, destination)
    return verify_phase_shard(destination, instance)


# ---------------------------------------------------------------------------
# Phase 9.1 clone-first storage primitives. They live here (not in
# inventory.py, a phase input) and are used only by explicitly opted-in call
# sites. A clone is an independent copy-on-write file: never a hardlink or
# writable alias. Only "cannot clone" errors fall back to the verified byte copy.
_CLONE_UNSUPPORTED = frozenset({errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP), errno.EXDEV,
                                errno.ENOTTY, errno.ENOSYS, *((errno.EINVAL,) if sys.platform.startswith("linux") else ())})


def _count(name: str, amount: int = 1) -> None:
    counter = sys.modules.get("runtime_reference_transport")
    if counter is not None:
        counter.count(name, amount)


def _native_clone_operation():
    """Return clone(source_fd, parent_fd, name, mode) or None (Windows/unsupported)."""
    if _is_windows():
        return None
    if sys.platform == "darwin":
        function = getattr(ctypes.CDLL(None, use_errno=True), "fclonefileat", None)
        if function is None:
            return None
        function.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        function.restype = ctypes.c_int

        def clone(source: int, parent: int, name: str, _mode: int) -> None:
            # Flush pending writes first: a clone of unflushed data under capacity
            # pressure diverged in run 44833963449. A full disk now fails here.
            os.fsync(source)
            # CLONE_NOOWNERCOPY; fclonefileat never replaces an existing leaf.
            if function(source, parent, os.fsencode(name), 0x2) != 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), name)

        return clone
    if sys.platform.startswith("linux"):
        import fcntl
        operation = getattr(fcntl, "FICLONE", None)
        if operation is None:
            return None

        def clone(source: int, parent: int, name: str, mode: int) -> None:
            target = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            try:
                try:
                    fcntl.ioctl(target, operation, source)
                except OSError:
                    held = os.fstat(target)
                    named = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                        raise ValueError("Clone destination changed before fallback")
                    os.unlink(name, dir_fd=parent)
                    raise
            finally:
                os.close(target)

        return clone
    return None


def _clone_regular_file(source: int, metadata: os.stat_result, parent: int, name: str, mode: int) -> bool:
    """Exclusive independent clone of a held source; False means "byte-copy instead"."""
    clone = _native_clone_operation()
    if clone is None or getattr(metadata, "st_flags", 0) or not stat.S_ISREG(metadata.st_mode):
        return False
    try:
        clone(source, parent, name, mode)
    except OSError as error:
        if error.errno in _CLONE_UNSUPPORTED:
            _count("cloneFallbacks")
            return False
        raise
    if _stat_identity(os.fstat(source)) != _stat_identity(metadata):
        raise ValueError(f"Clone source changed during capture: {name}")
    target = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0), dir_fd=parent)
    try:
        copied = os.fstat(target)
        if (not stat.S_ISREG(copied.st_mode) or copied.st_nlink != 1 or copied.st_size != metadata.st_size
                or (copied.st_dev, copied.st_ino) == (metadata.st_dev, metadata.st_ino)):
            raise ValueError(f"Native clone is not an independent regular file: {name}")
        os.fchmod(target, mode)
    finally:
        os.close(target)
    return True


def _clone_directory_descriptor(source: int, destination: int, *, allow_empty: bool = False) -> None:
    """inventory._copy_directory_descriptor with clone-first files; same guards."""
    before = os.fstat(source)
    names = sorted(os.listdir(source))
    for name in names:
        metadata = os.stat(name, dir_fd=source, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata):
            raise ValueError(f"Snapshot source contains an unsafe entry: {name}")
        if stat.S_ISDIR(metadata.st_mode):
            child = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                            dir_fd=source)
            try:
                target = _open_created_directory(destination, name, stat.S_IMODE(metadata.st_mode),
                                                 "Snapshot destination directory")
                try:
                    opened = os.fstat(child)
                    if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
                        raise ValueError(f"Snapshot directory changed while opening: {name}")
                    _clone_directory_descriptor(child, target, allow_empty=allow_empty)
                    os.fchmod(target, stat.S_IMODE(metadata.st_mode))
                finally:
                    os.close(target)
            finally:
                os.close(child)
        elif stat.S_ISREG(metadata.st_mode) and (allow_empty or metadata.st_size > 0):
            file_descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=source)
            try:
                opened = os.fstat(file_descriptor)
                if (metadata.st_dev, metadata.st_ino) != (opened.st_dev, opened.st_ino):
                    raise ValueError(f"Snapshot file changed while opening: {name}")
                if _clone_regular_file(file_descriptor, opened, destination, name, stat.S_IMODE(metadata.st_mode)):
                    _count("treeCloneFiles")
                    _count("treeCloneBytes", opened.st_size)
                    continue
                output_descriptor = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                            stat.S_IMODE(metadata.st_mode), dir_fd=destination)
                _count("treeCopyFiles")
                _count("treeCopyBytes", opened.st_size)
                try:
                    with (os.fdopen(file_descriptor, "rb", closefd=False) as input_file,
                          os.fdopen(output_descriptor, "wb", closefd=False) as output):
                        remaining = opened.st_size
                        while remaining:
                            chunk = input_file.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError(f"Snapshot file was truncated: {name}")
                            output.write(chunk)
                            remaining -= len(chunk)
                        if input_file.read(1) or _stat_identity(opened) != _stat_identity(os.fstat(file_descriptor)):
                            raise ValueError(f"Snapshot file changed while reading: {name}")
                        output.flush()
                        os.fchmod(output_descriptor, stat.S_IMODE(metadata.st_mode))
                finally:
                    os.close(output_descriptor)
            finally:
                os.close(file_descriptor)
        else:
            raise ValueError(f"Snapshot source contains an unsafe or empty entry: {name}")
    if _stat_identity(before) != _stat_identity(os.fstat(source)) or names != sorted(os.listdir(source)):
        raise ValueError("Snapshot source directory changed while copying")


def _require_disjoint(source: Path, destination: Path) -> tuple[Path, Path]:
    source = Path(os.path.abspath(source))
    destination = Path(os.path.abspath(destination))
    resolved_source = source.resolve(strict=True)
    resolved_destination = destination.parent.resolve(strict=False) / destination.name
    for left, right in ((source, destination), (resolved_source, resolved_destination)):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("Snapshot source and destination must not overlap")
    return source, destination


def clone_snapshot_regular_tree(source: Path, destination: Path, *, allow_empty: bool = False) -> None:
    """``snapshot_regular_tree`` with clone-first files; identical result and guards."""
    if _native_clone_operation() is None:
        snapshot_regular_tree(source, destination, allow_empty=allow_empty)
        return
    source, destination = _require_disjoint(source, destination)
    source_descriptor = _open_directory(source, "Snapshot source")
    parent_descriptor: int | None = None
    destination_descriptor: int | None = None
    try:
        _validate_snapshot_source(source_descriptor, allow_empty=allow_empty)
        parent_descriptor = _open_directory(destination.parent, "Snapshot destination", create=True)
        try:
            destination_descriptor = _open_created_directory(parent_descriptor, destination.name, 0o700,
                                                             "Snapshot destination")
        except FileExistsError as error:
            raise ValueError(f"Snapshot destination must not exist: {destination}") from error
        _clone_directory_descriptor(source_descriptor, destination_descriptor, allow_empty=allow_empty)
    finally:
        os.close(source_descriptor)
        if destination_descriptor is not None:
            os.close(destination_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def clone_publish_regular_tree(
    source: Path, destination: Path, *, allow_empty: bool = False,
    expected_inventory: list[dict[str, Any]] | None = None,
) -> None:
    """``publish_regular_tree`` with clone-first files.

    Staged contents are fully re-hashed against the source and the pinned
    inventory before the atomic no-replace rename, exactly as the original.
    """
    if _native_clone_operation() is None:
        publish_regular_tree(source, destination, allow_empty=allow_empty, expected_inventory=expected_inventory)
        return
    expected = None
    if expected_inventory is not None:
        records = require_sorted_unique_records(expected_inventory, "pinned inventory")
        for index, record in enumerate(records):
            validate_file_record(record, f"pinned inventory[{index}]", with_kind=False, allow_empty=allow_empty)
        expected = tuple((record["relativePath"], record["bytes"], record["sha256"]) for record in records)
    source, destination = _require_disjoint(source, destination)
    source_descriptor = _open_directory(source, "Snapshot source")
    parent_descriptor: int | None = None
    staged_descriptor: int | None = None
    staged_name: str | None = None
    try:
        source_inventory = _directory_inventory(source_descriptor, allow_empty=allow_empty)
        parent_descriptor = _open_directory(destination.parent, "Snapshot destination", create=True)
        try:
            os.stat(destination.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"Snapshot destination must not exist: {destination}")
        while staged_descriptor is None:
            staged_name = f".{destination.name}-snapshot-{secrets.token_hex(12)}"
            try:
                staged_descriptor = _open_created_directory(parent_descriptor, staged_name, 0o700,
                                                            "Snapshot staging directory")
            except FileExistsError:
                continue
        _clone_directory_descriptor(source_descriptor, staged_descriptor, allow_empty=allow_empty)
        staged_inventory = _directory_inventory(staged_descriptor, allow_empty=allow_empty)
        if _directory_inventory(source_descriptor, allow_empty=allow_empty) != source_inventory:
            raise ValueError("Snapshot source contents changed during publication")
        if staged_inventory != source_inventory:
            raise ValueError("Snapshot staged contents do not match the source")
        if expected is not None and tuple(sorted(
            (relative, size, digest)
            for relative, kind, _mode, size, digest in staged_inventory if kind == "file"
        )) != expected:
            raise ValueError("Snapshot staged contents do not match the pinned inventory")
        named = os.stat(staged_name, dir_fd=parent_descriptor, follow_symlinks=False)
        if _stat_identity(named) != _stat_identity(os.fstat(staged_descriptor)):
            raise ValueError("Snapshot staging directory changed before publication")
        parent_named = os.stat(destination.parent, follow_symlinks=False)
        if (stat.S_ISLNK(parent_named.st_mode) or _is_reparse_point(parent_named)
                or _stat_identity(parent_named) != _stat_identity(os.fstat(parent_descriptor))):
            raise ValueError("Snapshot destination parent changed before publication")
        try:
            os.stat(destination.name, dir_fd=parent_descriptor, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError(f"Snapshot destination must not exist: {destination}")
        try:
            _rename_directory_noreplace(staged_name, destination.name, parent_descriptor)
        except FileExistsError as error:
            raise ValueError("Snapshot destination appeared during publication") from error
        published_named = os.stat(destination.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if _stat_identity(published_named) != _stat_identity(os.fstat(staged_descriptor)):
            raise ValueError("Snapshot staging directory changed during publication")
        if _directory_inventory(staged_descriptor, allow_empty=allow_empty) != staged_inventory:
            raise ValueError("Snapshot contents changed during publication")
    finally:
        os.close(source_descriptor)
        if staged_descriptor is not None:
            # Retain failed staging diagnostics rather than delete by name.
            os.close(staged_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _clone_archive_snapshot(descriptor: int, before: os.stat_result, destination: Path) -> dict[str, Any] | None:
    """Clone-first private object snapshot; hash the clone, not the mutable source.

    Returns None when cloning is unsupported so the existing byte copy runs.
    """
    if _is_windows():
        return None
    parent = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not _clone_regular_file(descriptor, before, parent, destination.name, 0o600):
            return None
        snapshot = os.open(destination.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent)
    finally:
        os.close(parent)
    try:
        digest = hashlib.sha256()
        remaining = before.st_size
        with os.fdopen(snapshot, "rb", closefd=False) as input_file:
            while remaining:
                chunk = input_file.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Product cache object snapshot was truncated")
                digest.update(chunk)
                remaining -= len(chunk)
            if input_file.read(1) or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
                raise ValueError("Product cache object changed while being snapshotted")
    finally:
        os.close(snapshot)
    return {"bytes": before.st_size, "sha256": f"sha256:{digest.hexdigest()}"}


def _snapshot_archive(source: Path, destination: Path) -> dict[str, Any]:
    descriptor, before = _open_safe_regular(Path(source), "Product cache object")
    output_descriptor: int | None = None
    try:
        if before.st_size <= 0 or before.st_size > OBJECT_ZIP_LIMITS["max_archive_bytes"]:
            raise ValueError("Product cache object size is outside the fixed bound")
        cloned = _clone_archive_snapshot(descriptor, before, Path(destination))
        if cloned is not None:
            return cloned
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
    require_snapshot: bool = True,
) -> Iterator[tuple[Path | None, dict[str, Any]]]:
    session = None if _is_windows() else _VERIFICATION_SESSION.get()
    # A missing transport digest cannot identify an immutable object in advance.
    if session is not None and object_sha256 is not None:
        key = (require_sha256(build_key, "expected build key"),
               require_sha256(receipt_sha256, "expected receipt SHA-256"),
               require_sha256(object_sha256, "expected object SHA-256"))
        try:
            descriptor, before = _open_safe_regular(Path(archive), "Product cache object")
            try:
                identity = _stat_identity(before)
                source_key = (str(Path(archive).absolute()), identity, key)
                with session["lock"]:
                    cached = session["objects"].get(source_key)
                    proof = (session.get("objectProofs", {}).get(key)
                             if source_key in session.get("objectSources", {}) else None)
                if cached is None and not require_snapshot and proof is not None:
                    # Only return verified metadata. Any payload consumer still
                    # obtains a private snapshot and checks every byte's hash.
                    if _stat_identity(os.fstat(descriptor)) != identity:
                        raise CacheObjectError("Product cache object changed before metadata reuse")
                    session["hits"] += 1
                    yield None, deepcopy(proof)
                    if _stat_identity(os.fstat(descriptor)) != identity:
                        raise CacheObjectError("Product cache object changed during metadata reuse")
                    return
                if cached is not None:
                    snapshot, verification, snapshot_identity = cached
                    private_descriptor, private_stat = _open_safe_regular(snapshot, "Verified object snapshot")
                    os.close(private_descriptor)
                    if (_stat_identity(private_stat) != snapshot_identity
                            or _stat_identity(os.fstat(descriptor)) != identity):
                        raise CacheObjectError("Verified object custody changed")
                    session["hits"] += 1
                    yield snapshot, deepcopy(verification)
                    if _stat_identity(os.fstat(descriptor)) != identity:
                        raise CacheObjectError("Product cache object changed during cached verification")
                    private_descriptor, private_stat = _open_safe_regular(snapshot, "Verified object snapshot")
                    os.close(private_descriptor)
                    if _stat_identity(private_stat) != snapshot_identity:
                        raise CacheObjectError("Verified object custody changed during reuse")
                    return
            finally:
                os.close(descriptor)
        except (OSError, ValueError) as error:
            raise CacheObjectError(str(error)) from error
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-object-") as temporary:
        snapshot = Path(temporary).resolve() / "object.zip"
        try:
            identity = _snapshot_archive(Path(archive), snapshot)
            verification = None
            if session is not None and object_sha256 is not None:
                if identity["sha256"] != key[2]:
                    raise ValueError("Product cache object SHA-256 does not match the expected transport identity")
                with session["lock"]:
                    verification = deepcopy(session.get("objectProofs", {}).get(key))
                if verification is not None and verification["objectBytes"] != identity["bytes"]:
                    raise ValueError("Product cache object size differs from completed verification")
            if verification is None:
                verification = _verify_snapshot(
                    snapshot,
                    build_key=build_key,
                    receipt_sha256=receipt_sha256,
                    object_identity=identity,
                    object_sha256=object_sha256,
                )
                if session is not None and object_sha256 is not None:
                    size = len(verification["receiptBytes"]) + len(canonical_json_bytes(verification["manifest"]))
                    with session["lock"]:
                        proofs = session.setdefault("objectProofs", {})
                        used = session.get("objectProofBytes", 0)
                        # ponytail: 128 proofs/32 MiB encoded metadata; overflow verifies fully.
                        if key not in proofs and len(proofs) < 128 and used + size <= 2 * PRODUCT_JSON_LIMIT:
                            proofs[key] = deepcopy(verification)
                            session["objectProofBytes"] = used + size
            if session is not None and object_sha256 is not None:
                with session["lock"]:
                    sources = session.setdefault("objectSources", {})
                    if key in session.get("objectProofs", {}) and len(sources) < 4096:
                        sources[source_key] = key
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise CacheObjectError(str(error)) from error
        if session is not None and object_sha256 is not None:
            session["misses"] += 1
            # A newly seen alias has already passed its own complete byte hash.
            # Share retained custody by exact identity instead of charging it twice.
            with session["lock"]:
                equivalent = next((value for (_, _, candidate), value in session["objects"].items()
                                   if candidate == key), None)
                if equivalent is not None and len(session["objects"]) < 4096:
                    session["objects"][source_key] = equivalent
                elif (len(session["objects"]) < 4096
                      and session["bytes"] + identity["bytes"] <= _VERIFICATION_CACHE_BYTES):
                    retained = session["root"] / (secrets.token_hex(16) + ".zip")
                    shutil.move(snapshot, retained)
                    retained.chmod(0o400)
                    session["bytes"] += identity["bytes"]
                    session["objects"][source_key] = (
                        retained, deepcopy(verification), _stat_identity(retained.stat()))
                    snapshot = retained
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
        require_snapshot=False,
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
        session = None if _is_windows() else _VERIFICATION_SESSION.get()
        key = (verification["objectSha256"], receipt_sha256,
               canonical_json_bytes(verification["receipt"]["producer"]))
        cached = None if session is None else session["stages"].get(key)
        if cached is not None:
            stage, fingerprint = cached
            if _stage_fingerprint(stage) != fingerprint:
                raise CacheObjectError("Verified stage custody changed")
        else:
            _extract_verified_stage(snapshot, verification, stage)
            size = sum(record["bytes"] for record in verification["manifest"]["outputs"])
            if session is not None:
                with session["lock"]:
                    if session["bytes"] + size <= _VERIFICATION_CACHE_BYTES:
                        retained = session["root"] / secrets.token_hex(16)
                        shutil.move(stage, retained)
                        stage = retained
                        fingerprint = _stage_fingerprint(stage)
                        session["stages"][key] = (stage, fingerprint)
                        session["bytes"] += size
        # Clone-first: the verified stage and the caller's copy share extents.
        clone_snapshot_regular_tree(stage, destination)
        if cached is not None and _stage_fingerprint(stage) != fingerprint:
            raise CacheObjectError("Verified stage changed during restore")
        return {
            "receipt": verification["receipt"],
            "receiptBytes": verification["receiptBytes"],
            "objectSha256": verification["objectSha256"],
        }


def _stage_fingerprint(root):
    """Guard private, already-verified extraction custody without rehashing it."""
    if not _is_windows():
        anchor = _open_directory(root, "Verified stage directory")
        def fail(error):
            raise error
        walk = os.fwalk(".", topdown=True, onerror=fail, follow_symlinks=False, dir_fd=anchor)
        result = []
        before = _stat_identity(os.fstat(anchor))
        try:
            for current, directories, files, parent in walk:
                directories.sort()
                entries = [(".", True), *((name, True) for name in directories),
                           *((name, False) for name in sorted(files))]
                for name, directory in entries:
                    metadata = os.stat(name, dir_fd=parent, follow_symlinks=False)
                    if (_is_reparse_point(metadata)
                            or not (stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode))):
                        raise ValueError("Verified stage contains an unsafe entry")
                    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                    if directory:
                        flags |= getattr(os, "O_DIRECTORY", 0)
                    descriptor = os.open(name, flags, dir_fd=parent)
                    try:
                        opened = os.fstat(descriptor)
                        if _is_reparse_point(opened) or _stat_identity(opened) != _stat_identity(metadata):
                            raise ValueError("Verified stage entry changed while opening")
                        result.append((str(Path(root) / current / name), _stat_identity(opened)))
                    finally:
                        os.close(descriptor)
            current = _open_directory(root, "Verified stage directory")
            try:
                if (_stat_identity(os.fstat(current)) != before
                        or _stat_identity(os.fstat(anchor)) != before):
                    raise ValueError("Verified stage directory changed during fingerprint")
            finally:
                os.close(current)
            return tuple(result)
        except OSError as error:
            raise ValueError("Verified stage tree is missing or unsafe") from error
        finally:
            walk.close()
            os.close(anchor)
    from .index import _held_output_parent, _require_parent_identity
    def fail(error):
        raise error
    result = []
    # Windows directory handles need CreateFileW, not POSIX os.open on a drive.
    with _held_output_parent(Path(root)) as (anchor, absolute):
        before = _stat_identity(os.fstat(anchor))
        for current, directories, files in os.walk(absolute, onerror=fail, followlinks=False):
            directories.sort()
            for path in (Path(current), *(Path(current) / name for name in directories)):
                with _held_output_parent(path) as (descriptor, parent):
                    result.append((str(path), _stat_identity(os.fstat(descriptor))))
                    _require_parent_identity(descriptor, parent)
            for name in sorted(files):
                path = Path(current) / name
                descriptor, metadata = _open_safe_regular(path, "Verified stage file")
                os.close(descriptor)
                result.append((str(path), _stat_identity(metadata)))
        _require_parent_identity(anchor, absolute)
        if _stat_identity(os.fstat(anchor)) != before:
            raise ValueError("Verified stage directory changed during fingerprint")
    return tuple(result)


def _write_object(stage: Path, receipt_bytes: bytes, output: Path) -> None:
    manifest = validate_output_manifest(
        load_canonical_json_bytes(read_regular_file_bytes(
            stage / OUTPUT_MANIFEST_NAME, max_bytes=PRODUCT_JSON_LIMIT,
        )),
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
    descriptor = os.open(output, os.O_WRONLY | getattr(os, "O_BINARY", 0))
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
                os.rename(temporary, target)  # Windows rejects an existing target atomically.
            except FileExistsError:
                return False
            return True
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary.exists():
                temporary.chmod(0o666)  # Windows cannot delete a read-only file.
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
        load_canonical_json_bytes(read_regular_file_bytes(
            stage_root / OUTPUT_MANIFEST_NAME, max_bytes=PRODUCT_JSON_LIMIT,
        )),
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
    if __package__ == "ci.products":
        # CLI and qualification must share the canonical session/capability modules.
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from products.restore import main as restore_main
        return restore_main(argv)
    parser = argparse.ArgumentParser(prog="python3 -m ci.products restore")
    commands = parser.add_subparsers(dest="command", required=True)

    store = commands.add_parser("store-local")
    store.add_argument("--stage-root", required=True)
    store.add_argument("--receipt", required=True)
    store.add_argument("--cache-root")
    store.add_argument("--output", required=True)

    phase = commands.add_parser("store-phase")
    phase.add_argument("--stage-root", required=True)
    phase.add_argument("--phase-plan", required=True)
    phase.add_argument("--producer", required=True)
    phase.add_argument("--product-version", required=True)
    phase.add_argument("--trust-domain", required=True)
    phase.add_argument("--destination", required=True)

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
        if arguments.command == "store-phase":
            finalize_phase_object(
                stage_root=Path(arguments.stage_root),
                phase_plan=load_canonical_json_bytes(_read_safe_regular(
                    Path(arguments.phase_plan), max_bytes=PRODUCT_JSON_LIMIT,
                )),
                producer=load_canonical_json_bytes(_read_safe_regular(
                    Path(arguments.producer), max_bytes=PRODUCT_JSON_LIMIT,
                )),
                product_version=arguments.product_version,
                trust_domain=arguments.trust_domain,
                destination=Path(arguments.destination),
            )
            return 0
        elif arguments.command == "store-local":
            cache_root = _selected_cache_root(arguments.cache_root)
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
            cache_root = _selected_cache_root(arguments.cache_root)
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
            cache_root = _selected_cache_root(arguments.cache_root)
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
        if hasattr(arguments, "output"):
            _remove_output(arguments.output)
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
