"""Deterministic byte inventory for the two raw Apple framework slices.

This is comparison data only. The existing Gradle framework importer remains
responsible for native platform and architecture inspection.
"""

from collections.abc import Mapping
from pathlib import Path
import plistlib
from typing import Any

from .inventory import read_regular_file_bytes, regular_file_inventory


_TARGETS = (
    ("ios-arm64", "iPhoneOS"),
    ("ios-simulator-arm64", "iPhoneSimulator"),
)
_REQUIRED = {
    "CodexAgent",
    "Headers/CodexAgent.h",
    "Modules/module.modulemap",
    "Info.plist",
}
_PLIST_LIMIT = 16 * 1024 * 1024


def inspect_apple_frameworks(frameworks: Mapping[str, Path]) -> dict[str, Any]:
    """Return the complete two-slice inventory without granting authority."""
    if not isinstance(frameworks, Mapping) or set(frameworks) != {
            target for target, _ in _TARGETS}:
        raise ValueError("Apple framework inputs must contain the exact two targets")

    roots: dict[str, Path] = {}
    for target, _ in _TARGETS:
        value = frameworks[target]
        if not isinstance(value, Path) or not value.is_absolute() or value.name != "CodexAgent.framework":
            raise ValueError(f"Apple framework path is invalid for {target}")
        try:
            resolved = value.resolve(strict=True)
        except OSError as error:
            raise ValueError(f"Apple framework path is missing for {target}") from error
        if resolved != value:
            raise ValueError(f"Apple framework path must be normalized and non-symbolic for {target}")
        roots[target] = resolved
    left, right = (roots[target] for target, _ in _TARGETS)
    if left == right or left in right.parents or right in left.parents:
        raise ValueError("Apple framework inputs must not overlap")

    inventories = {target: regular_file_inventory(roots[target]) for target, _ in _TARGETS}
    for target, expected_platform in _TARGETS:
        files = {record["relativePath"] for record in inventories[target]}
        if not _REQUIRED <= files:
            raise ValueError(f"Apple framework is missing a required member for {target}")
        plist_bytes = read_regular_file_bytes(
            roots[target] / "Info.plist",
            max_bytes=_PLIST_LIMIT,
            reject_symlink_parents=True,
        )
        try:
            plist = plistlib.loads(plist_bytes)
        except (plistlib.InvalidFileException, ValueError) as error:
            raise ValueError(f"Apple framework Info.plist is invalid for {target}") from error
        if type(plist) is not dict or plist.get("CFBundleSupportedPlatforms") != [expected_platform]:
            raise ValueError(f"Apple framework platform is invalid for {target}")

    if any(regular_file_inventory(roots[target]) != inventories[target] for target, _ in _TARGETS):
        raise ValueError("Apple framework input changed during inventory")
    return {
        "schemaVersion": 1,
        "kind": "sdk-apple-framework-inventory",
        "targets": [
            {"target": target, "files": inventories[target]}
            for target, _ in _TARGETS
        ],
    }
