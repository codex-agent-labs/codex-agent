"""Verify raw Apple validation ZIP inventory, not evidence meaning or authenticity."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import tempfile

if __package__ == "products":  # Script entry points in ci/ use this namespace.
    from receipt import safe_extract
else:
    from ..receipt import safe_extract
from .inventory import regular_file_inventory, require_relative_path, require_sha256, verified_zip_contents
from .restore import OBJECT_ZIP_LIMITS, _snapshot_archive


def _roots(expected_roots: tuple[str, ...]) -> tuple[str, ...]:
    if type(expected_roots) is not tuple or not expected_roots:
        raise ValueError("Apple validation evidence requires a nonempty tuple of roots")
    roots = tuple(require_relative_path(root, "Apple validation evidence root") for root in expected_roots)
    if any("/" in root for root in roots) or len(roots) != len(set(roots)):
        raise ValueError("Apple validation evidence roots must be unique top-level prefixes")
    return roots


def _verified_archive(
    archive: Path, roots: tuple[str, ...],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    records, _, identity = verified_zip_contents(
        archive, retained_paths=(), allow_empty_members=True, require_sorted=True,
        **OBJECT_ZIP_LIMITS,
    )
    actual = set()
    for record in records:
        root, separator, _ = record["relativePath"].partition("/")
        if not separator:
            raise ValueError("Apple validation evidence member must be below a root prefix")
        actual.add(root)
    if actual != set(roots):
        raise ValueError("Apple validation evidence archive has missing or extra roots")
    return records, identity


def verify_apple_validation_evidence_archive(
    archive: Path, expected_roots: tuple[str, ...],
) -> list[dict[str, object]]:
    """Require exactly the caller's nonempty root inventories, preserving empty streams.

    The outer original phase receipt must bind the archive digest. This reader
    grants no semantic, source, run, signature or Apple host authority.
    It inherits OBJECT_ZIP_LIMITS from phase-object transport (including the
    2 GiB total/archive bounds); oversized raw evidence fails, never truncates.
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
            records, snapshot_identity = _verified_archive(snapshot, roots)
            if snapshot_identity != identity:
                raise ValueError("Apple validation evidence private archive changed after snapshot")
            safe_extract(snapshot, extracted)
            inventory = regular_file_inventory(extracted, allow_empty=True)
            if inventory != records:
                raise ValueError("Extracted Apple validation evidence inventory differs from the archive")
        except OSError as error:
            raise ValueError("Apple validation evidence archive is missing or malformed") from error

        def unchanged() -> None:
            try:
                current_records, current_identity = _verified_archive(original, roots)
                private_records, private_identity = _verified_archive(snapshot, roots)
                extracted_inventory = regular_file_inventory(extracted, allow_empty=True)
            except OSError as error:
                raise ValueError("Apple validation evidence changed during verification") from error
            if (current_records != records or current_identity != identity
                    or private_records != records or private_identity != identity
                    or extracted_inventory != inventory):
                raise ValueError("Apple validation evidence changed during verification")

        unchanged()
        try:
            yield extracted
        finally:
            unchanged()
