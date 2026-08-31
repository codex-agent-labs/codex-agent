from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import tempfile
from typing import Any, Iterable, NoReturn
import zipfile


SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
)


def _reject_number(value: str) -> NoReturn:
    raise ValueError(f"Product JSON forbids floating-point values: {value}")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"Product JSON contains duplicate key: {key}")
        value[key] = member
    return value


def _validate_json_value(value: Any, location: str = "$") -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        raise ValueError(f"Product JSON forbids floating-point value at {location}")
    if type(value) is list:
        for index, member in enumerate(value):
            _validate_json_value(member, f"{location}[{index}]")
        return
    if type(value) is dict:
        for key, member in value.items():
            if type(key) is not str:
                raise ValueError(f"Product JSON key at {location} is not a string")
            _validate_json_value(member, f"{location}.{key}")
        return
    raise ValueError(f"Unsupported product JSON value at {location}: {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def load_json_bytes(contents: bytes) -> Any:
    if type(contents) is not bytes:
        raise TypeError("Product JSON input must be bytes")
    try:
        text = contents.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Product JSON is not canonical UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except json.JSONDecodeError as error:
        raise ValueError("Product JSON is malformed") from error
    _validate_json_value(value)
    return value


def load_canonical_json_bytes(contents: bytes) -> Any:
    value = load_json_bytes(contents)
    if canonical_json_bytes(value) != contents:
        raise ValueError("Product JSON bytes are not canonical")
    return value


def load_canonical_json(path: Path) -> Any:
    return load_canonical_json_bytes(read_regular_file_bytes(path))


def load_json(path: Path) -> Any:
    return load_json_bytes(read_regular_file_bytes(path))


def write_canonical_json(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    contents = canonical_json_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def sha256_bytes(contents: bytes) -> str:
    return f"sha256:{hashlib.sha256(contents).hexdigest()}"


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _is_reparse_point(value: os.stat_result) -> bool:
    return bool(
        getattr(value, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _open_regular_file(path: Path, label: str) -> tuple[int, os.stat_result]:
    path = Path(path)
    try:
        path_stat = path.lstat()
        if stat.S_ISLNK(path_stat.st_mode) or _is_reparse_point(path_stat) or not stat.S_ISREG(path_stat.st_mode):
            raise ValueError(f"{label} is missing or unsafe: {path}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened_stat = os.fstat(descriptor)
        if not stat.S_ISREG(opened_stat.st_mode) or (
            path_stat.st_dev, path_stat.st_ino
        ) != (opened_stat.st_dev, opened_stat.st_ino):
            os.close(descriptor)
            raise ValueError(f"{label} changed while opening: {path}")
        return descriptor, opened_stat
    except ValueError:
        raise
    except OSError as error:
        raise ValueError(f"{label} is missing or unsafe: {path}") from error


def read_regular_file_bytes(path: Path, *, max_bytes: int | None = None) -> bytes:
    path = Path(path)
    descriptor, before = _open_regular_file(path, "File")
    try:
        if max_bytes is not None and before.st_size > max_bytes:
            raise ValueError(f"File is too large: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            contents = source.read(before.st_size + 1)
        after = os.fstat(descriptor)
        if _stat_identity(before) != _stat_identity(after) or len(contents) != before.st_size:
            raise ValueError(f"File changed during verification: {path}")
        return contents
    except OSError as error:
        raise ValueError(f"File is missing or unsafe: {path}") from error
    finally:
        os.close(descriptor)


def _regular_file_digest(path: Path) -> tuple[int, str]:
    path = Path(path)
    descriptor, before = _open_regular_file(path, "Digest input")
    try:
        digest = hashlib.sha256()
        remaining = before.st_size
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                digest.update(chunk)
                remaining -= len(chunk)
            grew = bool(source.read(1))
        after = os.fstat(descriptor)
        if remaining or grew or _stat_identity(before) != _stat_identity(after):
            raise ValueError(f"Digest input changed during verification: {path}")
        return before.st_size, f"sha256:{digest.hexdigest()}"
    except OSError as error:
        raise ValueError(f"Digest input is missing or unsafe: {path}") from error
    finally:
        os.close(descriptor)


def sha256_file(path: Path) -> str:
    return _regular_file_digest(path)[1]


def require_sha256(value: Any, label: str) -> str:
    if type(value) is not str or SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be sha256: plus 64 lowercase hexadecimal characters")
    return value


def require_identifier(value: Any, label: str) -> str:
    if type(value) is not str or IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} is not a canonical identifier")
    return value


def require_semver(value: Any, label: str) -> str:
    if type(value) is not str or SEMVER.fullmatch(value) is None:
        raise ValueError(f"{label} is not canonical SemVer without build metadata")
    return value


def require_string(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def require_boolean(value: Any, label: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{label} must be a boolean")
    return value


def require_integer(value: Any, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def require_object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def require_array(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{label} must be an array")
    return value


def require_exact_keys(value: Any, keys: Iterable[str], label: str) -> dict[str, Any]:
    obj = require_object(value, label)
    expected = set(keys)
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise ValueError(f"{label} fields are invalid; missing={missing}, extra={extra}")
    return obj


def require_relative_path(value: Any, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty relative POSIX path")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError(f"{label} contains a control character")
    if "\\" in value or ":" in value or value.startswith("/"):
        raise ValueError(f"{label} is not a relative POSIX path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"{label} is not normalized")
    if str(PurePosixPath(value)) != value:
        raise ValueError(f"{label} is not normalized")
    return value


def validate_file_record(value: Any, label: str, *, with_kind: bool) -> dict[str, Any]:
    keys = {"relativePath", "bytes", "sha256"}
    if with_kind:
        keys.add("kind")
    record = require_exact_keys(value, keys, label)
    if with_kind:
        require_identifier(record["kind"], f"{label}.kind")
    require_relative_path(record["relativePath"], f"{label}.relativePath")
    require_integer(record["bytes"], f"{label}.bytes", minimum=1)
    require_sha256(record["sha256"], f"{label}.sha256")
    return record


def require_sorted_unique_records(records: Any, label: str, *, path_field: str = "relativePath") -> list[Any]:
    values = require_array(records, label)
    paths = [require_relative_path(require_object(value, f"{label}[]").get(path_field), f"{label}[].{path_field}")
             for value in values]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise ValueError(f"{label} must be sorted by {path_field} with no duplicates")
    return values


def regular_file_inventory(
    root: Path,
    *,
    kind: str | None = None,
    excluded_paths: Iterable[str] = (),
) -> list[dict[str, Any]]:
    root = Path(root)
    try:
        root_stat = root.lstat()
    except OSError as error:
        raise ValueError(f"Inventory root is missing or unsafe: {root}") from error
    if stat.S_ISLNK(root_stat.st_mode) or _is_reparse_point(root_stat) or not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError(f"Inventory root is missing or unsafe: {root}")
    excluded = {require_relative_path(path, "excluded inventory path") for path in excluded_paths}
    files: list[Path] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in sorted(directories):
            path = current_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata) or not stat.S_ISDIR(metadata.st_mode):
                raise ValueError(f"Inventory contains an unsafe directory: {path}")
        for name in sorted(names):
            path = current_path / name
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse_point(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"Inventory contains an unsafe file: {path}")
            if path.relative_to(root).as_posix() not in excluded:
                files.append(path)
    records = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = require_relative_path(path.relative_to(root).as_posix(), "inventory path")
        size, digest = _regular_file_digest(path)
        if size <= 0:
            raise ValueError(f"Inventory contains an empty file: {relative}")
        record: dict[str, Any] = {
            "relativePath": relative,
            "bytes": size,
            "sha256": digest,
        }
        if kind is not None:
            record["kind"] = require_identifier(kind, "inventory kind")
        records.append(record)
    return records


def verify_regular_file_inventory(
    root: Path,
    records: Any,
    *,
    with_kind: bool,
    excluded_paths: Iterable[str] = (),
) -> None:
    values = require_sorted_unique_records(records, "file inventory")
    for index, record in enumerate(values):
        validate_file_record(record, f"file inventory[{index}]", with_kind=with_kind)
    actual = regular_file_inventory(root, excluded_paths=excluded_paths)
    expected = [
        {key: value for key, value in record.items() if key != "kind"}
        for record in values
    ]
    if actual != expected:
        raise ValueError("Declared file inventory does not match the complete regular-file tree")


def verified_zip_inventory(archive: Path) -> list[dict[str, Any]]:
    records, _, _ = verified_zip_contents(archive, retained_paths=())
    return records


def verified_zip_contents(
    archive: Path,
    *,
    max_archive_bytes: int | None = None,
    max_central_directory_bytes: int | None = None,
    max_members: int | None = None,
    max_entry_bytes: int | None = None,
    max_total_bytes: int | None = None,
    max_compression_ratio: int | None = None,
    retained_paths: Iterable[str] | None = None,
    max_retained_bytes: int | None = None,
    canonical_stored: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, bytes], dict[str, Any]]:
    archive = Path(archive)
    records: list[dict[str, Any]] = []
    contents_by_path: dict[str, bytes] = {}
    paths: set[str] = set()
    retained = None if retained_paths is None else {
        require_relative_path(path, "retained ZIP member path") for path in retained_paths
    }
    if canonical_stored and retained is not None:
        raise ValueError("Canonical ZIP verification must retain every member")
    retained_bytes = 0
    descriptor, archive_stat = _open_regular_file(archive, "ZIP archive")
    try:
        if max_archive_bytes is not None and archive_stat.st_size > max_archive_bytes:
            raise ValueError("ZIP archive is too large")
        with os.fdopen(descriptor, "rb", closefd=False) as raw, tempfile.TemporaryFile() as snapshot:
            archive_digest = hashlib.sha256()
            remaining = archive_stat.st_size
            while remaining:
                chunk = raw.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("ZIP archive was truncated during verification")
                archive_digest.update(chunk)
                snapshot.write(chunk)
                remaining -= len(chunk)
            if raw.read(1) or _stat_identity(archive_stat) != _stat_identity(os.fstat(descriptor)):
                raise ValueError("ZIP archive changed during verification")
            snapshot.seek(0)
            if max_members is not None or max_central_directory_bytes is not None:
                tail_size = min(archive_stat.st_size, 22 + 65_535)
                snapshot.seek(archive_stat.st_size - tail_size)
                tail = snapshot.read(tail_size)
                eocd = tail.rfind(b"PK\x05\x06")
                if eocd < 0 or eocd + 22 > len(tail):
                    raise ValueError("ZIP archive has no valid end-of-central-directory record")
                comment_size = int.from_bytes(tail[eocd + 20:eocd + 22], "little")
                if eocd + 22 + comment_size != len(tail):
                    raise ValueError("ZIP archive end-of-central-directory record is malformed")
                member_count = int.from_bytes(tail[eocd + 10:eocd + 12], "little")
                central_size = int.from_bytes(tail[eocd + 12:eocd + 16], "little")
                if member_count == 0xFFFF or central_size == 0xFFFFFFFF:
                    raise ValueError("Limited ZIP verification does not accept ZIP64 archives")
                if max_members is not None and member_count > max_members:
                    raise ValueError("ZIP archive contains too many members")
                if max_central_directory_bytes is not None and central_size > max_central_directory_bytes:
                    raise ValueError("ZIP archive central directory is too large")
                snapshot.seek(0)
            with zipfile.ZipFile(snapshot) as source:
                entries = source.infolist()
                if max_members is not None and len(entries) > max_members:
                    raise ValueError("ZIP archive contains too many members")
                if canonical_stored and source.comment:
                    raise ValueError("Canonical ZIP archive must not have a comment")
                total = 0
                for entry in entries:
                    if max_entry_bytes is not None and entry.file_size > max_entry_bytes:
                        raise ValueError(f"ZIP member is too large: {entry.filename}")
                    total += entry.file_size
                    if max_total_bytes is not None and total > max_total_bytes:
                        raise ValueError("ZIP archive uncompressed size is too large")
                    if max_compression_ratio is not None and entry.file_size > 0:
                        compressed = max(entry.compress_size, 1)
                        if entry.file_size > compressed * max_compression_ratio:
                            raise ValueError(f"ZIP member compression ratio is too large: {entry.filename}")
                    if canonical_stored and (
                        entry.date_time != (1980, 1, 1, 0, 0, 0) or
                        entry.compress_type != zipfile.ZIP_STORED or
                        entry.extra or
                        entry.comment or
                        entry.create_system != 3 or
                        entry.create_version != 20 or
                        entry.extract_version != 20 or
                        entry.flag_bits != 0 or
                        entry.internal_attr != 0 or
                        entry.volume != 0 or
                        ((entry.external_attr >> 16) & 0xFFFF) != (stat.S_IFREG | 0o644)
                    ):
                        raise ValueError(f"ZIP member metadata is not canonical: {entry.filename}")
                    if entry.orig_filename != entry.filename:
                        raise ValueError("ZIP member name contains a NUL or was normalized by the ZIP reader")
                    if entry.is_dir():
                        raise ValueError(f"ZIP archive contains an explicit directory entry: {entry.filename}")
                    path = require_relative_path(entry.orig_filename, "ZIP member path")
                    if path in paths:
                        raise ValueError(f"ZIP archive contains duplicate member: {path}")
                    if any("/".join(path.split("/")[:index]) in paths for index in range(1, len(path.split("/")))):
                        raise ValueError(f"ZIP member descends from a file: {path}")
                    mode = (entry.external_attr >> 16) & 0xFFFF
                    file_type = stat.S_IFMT(mode)
                    if file_type not in (0, stat.S_IFREG):
                        raise ValueError(f"ZIP archive contains a symlink or special member: {path}")
                    if entry.flag_bits & 0x1:
                        raise ValueError(f"ZIP archive contains an encrypted member: {path}")
                    digest = hashlib.sha256()
                    member_bytes = 0
                    retained_member = bytearray() if retained is None or path in retained else None
                    with source.open(entry, "r") as member:
                        while chunk := member.read(1024 * 1024):
                            member_bytes += len(chunk)
                            if member_bytes > entry.file_size or (
                                max_entry_bytes is not None and member_bytes > max_entry_bytes
                            ):
                                raise ValueError(f"ZIP member expands beyond its declared limit: {path}")
                            digest.update(chunk)
                            if retained_member is not None:
                                retained_bytes += len(chunk)
                                if max_retained_bytes is not None and retained_bytes > max_retained_bytes:
                                    raise ValueError("Retained ZIP member contents are too large")
                                retained_member.extend(chunk)
                    if member_bytes != entry.file_size or not member_bytes:
                        raise ValueError(f"ZIP archive contains an empty or truncated member: {path}")
                    paths.add(path)
                    if retained_member is not None:
                        contents_by_path[path] = bytes(retained_member)
                    records.append({
                        "relativePath": path,
                        "bytes": member_bytes,
                        "sha256": f"sha256:{digest.hexdigest()}",
                    })
            if canonical_stored:
                with tempfile.TemporaryFile() as expected:
                    with zipfile.ZipFile(expected, "w", compression=zipfile.ZIP_STORED) as canonical:
                        for record in records:
                            path = record["relativePath"]
                            info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                            info.compress_type = zipfile.ZIP_STORED
                            info.create_system = 3
                            info.external_attr = (stat.S_IFREG | 0o644) << 16
                            canonical.writestr(info, contents_by_path[path])
                    snapshot.seek(0)
                    expected.seek(0)
                    while actual_chunk := snapshot.read(1024 * 1024):
                        if actual_chunk != expected.read(len(actual_chunk)):
                            raise ValueError("Canonical ZIP archive bytes do not match the canonical encoding")
                    if expected.read(1):
                        raise ValueError("Canonical ZIP archive bytes do not match the canonical encoding")
            final_stat = os.fstat(descriptor)
            if _stat_identity(archive_stat) != _stat_identity(final_stat):
                raise ValueError("ZIP archive changed during verification")
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f"ZIP archive is malformed or unsafe: {archive}") from error
    finally:
        os.close(descriptor)
    if [record["relativePath"] for record in records] != sorted(paths):
        raise ValueError("ZIP archive members are not in canonical sorted order")
    return records, contents_by_path, {
        "bytes": archive_stat.st_size,
        "sha256": f"sha256:{archive_digest.hexdigest()}",
    }


def public_key_fingerprint(public_key: bytes) -> str:
    try:
        line = public_key.decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Ed25519 public key is not ASCII") from error
    match = re.fullmatch(r"ssh-ed25519 ([A-Za-z0-9+/]+={0,2})\n", line)
    if match is None:
        raise ValueError("Ed25519 public key must be exactly 'ssh-ed25519 <base64>\\n'")
    try:
        blob = base64.b64decode(match.group(1), validate=True)
    except ValueError as error:
        raise ValueError("Ed25519 public key base64 is invalid") from error
    algorithm = b"ssh-ed25519"
    if blob != struct.pack(">I", len(algorithm)) + algorithm + struct.pack(">I", 32) + blob[-32:]:
        raise ValueError("Ed25519 public key blob is not an RFC4253 Ed25519 key")
    return sha256_bytes(blob)
