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


def load_canonical_json_bytes(contents: bytes) -> Any:
    if type(contents) is not bytes:
        raise TypeError("Canonical product JSON input must be bytes")
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
    if canonical_json_bytes(value) != contents:
        raise ValueError("Product JSON bytes are not canonical")
    return value


def load_canonical_json(path: Path) -> Any:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Canonical product JSON is missing or unsafe: {path}")
    return load_canonical_json_bytes(path.read_bytes())


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


def sha256_file(path: Path) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Digest input is missing or unsafe: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


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
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Inventory root is missing or unsafe: {root}")
    excluded = {require_relative_path(path, "excluded inventory path") for path in excluded_paths}
    files: list[Path] = []
    for current, directories, names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in sorted(directories):
            path = current_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise ValueError(f"Inventory contains an unsafe directory: {path}")
        for name in sorted(names):
            path = current_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise ValueError(f"Inventory contains an unsafe file: {path}")
            if path.relative_to(root).as_posix() not in excluded:
                files.append(path)
    records = []
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = require_relative_path(path.relative_to(root).as_posix(), "inventory path")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"Inventory contains an empty file: {relative}")
        record: dict[str, Any] = {
            "relativePath": relative,
            "bytes": size,
            "sha256": sha256_file(path),
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
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file():
        raise ValueError(f"ZIP archive is missing or unsafe: {archive}")
    records: list[dict[str, Any]] = []
    paths: set[str] = set()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
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
            contents = source.read(entry)
            if not contents:
                raise ValueError(f"ZIP archive contains an empty member: {path}")
            paths.add(path)
            records.append({"relativePath": path, "bytes": len(contents), "sha256": sha256_bytes(contents)})
    if [record["relativePath"] for record in records] != sorted(paths):
        raise ValueError("ZIP archive members are not in canonical sorted order")
    return records


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
