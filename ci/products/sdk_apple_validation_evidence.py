"""Verify raw Apple validation ZIP inventory, not evidence meaning or authenticity."""

from collections.abc import Iterator
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

if __package__ == "products":  # Script entry points in ci/ use this namespace.
    from receipt import safe_extract
else:
    from ..receipt import safe_extract
from .inventory import (
    _open_regular_file, _stat_identity, load_canonical_json_bytes, require_exact_keys,
    require_integer, require_relative_path, require_sha256, require_sorted_unique_records,
    validate_file_record, verified_zip_contents,
)
from .restore import OBJECT_ZIP_LIMITS, _snapshot_archive, memoized_file_inventory as regular_file_inventory


REFERENCE_NAME = "apple-validation-references.json"
_LOGICAL_BYTES = 32 * 1024**3


def _roots(expected_roots: tuple[str, ...]) -> tuple[str, ...]:
    if type(expected_roots) is not tuple or not expected_roots:
        raise ValueError("Apple validation evidence requires a nonempty tuple of roots")
    roots = tuple(require_relative_path(root, "Apple validation evidence root") for root in expected_roots)
    if any("/" in root or root == REFERENCE_NAME for root in roots) or len(roots) != len(set(roots)):
        raise ValueError("Apple validation evidence roots must be unique top-level prefixes")
    return roots


def _verified_archive(
    archive: Path, roots: tuple[str, ...],
) -> tuple[list[dict[str, object]], dict[str, object], list[dict[str, object]]]:
    records, retained, identity = verified_zip_contents(
        archive, retained_paths=(REFERENCE_NAME,), max_retained_bytes=16 * 1024**2,
        allow_empty_members=True, require_sorted=True,
        **OBJECT_ZIP_LIMITS,
    )
    references = []
    if REFERENCE_NAME in retained:
        control = require_exact_keys(load_canonical_json_bytes(retained[REFERENCE_NAME]),
                                     {"schemaVersion", "references"}, "Apple validation references")
        if require_integer(control["schemaVersion"], "Apple reference schema", 1) != 1:
            raise ValueError("Unsupported Apple validation reference schema")
        references = require_sorted_unique_records(control["references"], "Apple validation references")
        records = [record for record in records if record["relativePath"] != REFERENCE_NAME]
        physical = {record["relativePath"]: record for record in records}
        if not references or len(records) + len(references) > OBJECT_ZIP_LIMITS["max_members"] - 1:
            raise ValueError("Apple validation logical inventory exceeds its member bound")
        for reference in references:
            require_exact_keys(reference, {"relativePath", "sourcePath", "bytes", "sha256"},
                               "Apple validation reference")
            record = {key: reference[key] for key in ("relativePath", "bytes", "sha256")}
            validate_file_record(record, "Apple validation reference", with_kind=False)
            source = require_relative_path(reference["sourcePath"], "Apple validation reference source")
            if (record["relativePath"] in physical or source not in physical
                    or any(record[key] != physical[source][key] for key in ("bytes", "sha256"))):
                raise ValueError("Apple validation reference differs from its physical member")
            records.append(record)
        records.sort(key=lambda record: record["relativePath"])
        if sum(record["bytes"] for record in records) > _LOGICAL_BYTES:
            raise ValueError("Apple validation logical inventory exceeds its byte bound")
    paths = {record["relativePath"] for record in records}
    actual = set()
    for record in records:
        path = record["relativePath"]
        root, separator, _ = path.partition("/")
        parents = path.split("/")[:-1]
        if not separator or any("/".join(parents[:i + 1]) in paths for i in range(len(parents))):
            raise ValueError("Apple validation evidence member must be below a root prefix")
        actual.add(root)
    if actual != set(roots):
        raise ValueError("Apple validation evidence archive has missing or extra roots")
    return records, identity, references


def _require_unchanged_archive(path: Path, identity: dict[str, object]) -> None:
    """Identical full ZIP bytes imply the already verified member inventory."""
    descriptor, before = _open_regular_file(path, "Apple validation archive", reject_symlink_parents=True)
    try:
        if before.st_size != identity["bytes"]:
            raise ValueError("Apple validation archive size changed")
        digest = hashlib.sha256()
        remaining = before.st_size
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            while remaining:
                chunk = source.read(min(1024**2, remaining))
                if not chunk:
                    raise ValueError("Apple validation archive was truncated")
                digest.update(chunk)
                remaining -= len(chunk)
            if source.read(1) or _stat_identity(os.fstat(descriptor)) != _stat_identity(before):
                raise ValueError("Apple validation archive changed while hashing")
        if "sha256:" + digest.hexdigest() != identity["sha256"]:
            raise ValueError("Apple validation archive digest changed")
    finally:
        os.close(descriptor)


def verify_apple_validation_evidence_archive(
    archive: Path, expected_roots: tuple[str, ...],
) -> list[dict[str, object]]:
    """Require exactly the caller's nonempty root inventories, preserving empty streams.

    The outer original phase receipt must bind the archive digest. This reader
    grants no semantic, source, run, signature or Apple host authority.
    Physical ZIP limits remain unchanged. Direct size/SHA references reconstruct
    duplicate files within a separately bounded 32 GiB logical inventory.
    """
    return _verified_archive(Path(archive), _roots(expected_roots))[0]


@contextmanager
def verified_apple_validation_archive(
    archive: Path, *, expected_sha256: str, expected_roots: tuple[str, ...],
) -> Iterator[Path]:
    """Yield a private raw-evidence tree bound to caller-owned digest and roots.

    This context verifies transport bytes and inventory only. It grants no
    semantic, source, execution, signature, receipt, or Apple-host authority.
    """
    digest = require_sha256(expected_sha256, "Expected Apple validation evidence digest")
    roots = _roots(expected_roots)
    original = Path(archive)
    with tempfile.TemporaryDirectory(prefix="sdk-apple-validation-archive-") as temporary:
        private = Path(temporary).resolve()
        snapshot = private / "archive.zip"
        extracted = private / "evidence"
        try:
            identity = _snapshot_archive(original, snapshot)
            if identity["sha256"] != digest:
                raise ValueError("Apple validation evidence archive digest differs from the expected digest")
            records, snapshot_identity, references = _verified_archive(snapshot, roots)
            if snapshot_identity != identity:
                raise ValueError("Apple validation evidence private archive changed after snapshot")
            safe_extract(snapshot, extracted)
            if references:
                (extracted / REFERENCE_NAME).unlink()
                for reference in references:
                    target = extracted / reference["relativePath"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with (extracted / reference["sourcePath"]).open("rb") as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output, length=1024**2)
            inventory = regular_file_inventory(extracted, allow_empty=True)
            if inventory != records:
                raise ValueError("Extracted Apple validation evidence inventory differs from the archive")
        except OSError as error:
            raise ValueError("Apple validation evidence archive is missing or malformed") from error

        def unchanged() -> None:
            try:
                _require_unchanged_archive(original, identity)
                _require_unchanged_archive(snapshot, identity)
                extracted_inventory = regular_file_inventory(extracted, allow_empty=True)
            except OSError as error:
                raise ValueError("Apple validation evidence changed during verification") from error
            if extracted_inventory != inventory:
                raise ValueError("Apple validation evidence changed during verification")

        unchanged()
        try:
            yield extracted
        finally:
            unchanged()
