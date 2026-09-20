"""Verify raw Apple validation ZIP inventory, not evidence meaning or authenticity."""

from pathlib import Path

from .inventory import require_relative_path, verified_zip_contents
from .restore import OBJECT_ZIP_LIMITS


def verify_apple_validation_evidence_archive(
    archive: Path, expected_roots: tuple[str, ...],
) -> list[dict[str, object]]:
    """Require exactly the caller's nonempty root inventories, preserving empty streams.

    The outer original phase receipt must bind the archive digest. This reader
    grants no semantic, source, run, signature or Apple host authority.
    It inherits OBJECT_ZIP_LIMITS from phase-object transport (including the
    2 GiB total/archive bounds); oversized raw evidence fails, never truncates.
    """
    if type(expected_roots) is not tuple or not expected_roots:
        raise ValueError("Apple validation evidence requires a nonempty tuple of roots")
    roots = [require_relative_path(root, "Apple validation evidence root") for root in expected_roots]
    if any("/" in root for root in roots) or len(roots) != len(set(roots)):
        raise ValueError("Apple validation evidence roots must be unique top-level prefixes")
    records, _, _ = verified_zip_contents(
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
    return records
