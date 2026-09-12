"""Read caller-selected SDK policy; this does not authenticate Runtime evidence."""

from pathlib import Path
import re
from typing import Iterable

from .aggregate import _compatible_range
from .inventory import git_regular_blob_bytes, load_canonical_json_bytes, require_exact_keys, require_semver
from .registry import PhaseInstanceId, phase_instance_dependencies


def sdk_runtime_source(repository_root: Path, revision: str, *, instances: Iterable[PhaseInstanceId],
                       runtime_version: str, sdk_version: str) -> str | None:
    """Choose the dependency route for an existing closure, without granting trust.

    Nonconsuming closures need no SDK policy. A matching current Runtime keeps
    the existing fresh/current route; a different default requires the released
    original selection gate downstream, never a newest-version lookup.
    """
    if not any(instance.product == "sdk" and any(dependency.product == "runtime"
               for dependency in phase_instance_dependencies(instance)) for instance in instances):
        return None
    selected = read_sdk_release_selection(repository_root, revision)
    read_sdk_runtime_compatibility_policy(repository_root, revision)
    if require_semver(sdk_version, "Selected SDK version") != selected["sdkVersion"]:
        raise ValueError("Selected SDK version differs from the original SDK release selection")
    current = require_semver(runtime_version, "Current Runtime version")
    return "released-default" if current != selected["defaultRuntimeVersion"] else None


def read_sdk_release_selection(repository_root: Path, revision: str) -> dict[str, str]:
    """Read the two original regular Git blobs, never mutable checkout policy."""
    if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("SDK release selection requires an exact Git revision")
    selection = {}
    for field, path in (
        ("sdkVersion", "gradle/release/versions/sdk.txt"),
        ("defaultRuntimeVersion", "gradle/release/sdk-default-runtime.txt"),
    ):
        raw = git_regular_blob_bytes(Path(repository_root), revision, path, max_bytes=256)
        # Match ProductVersions.kt's authority file policy, including its LF.
        if (not raw.endswith(b"\n") or raw.count(b"\n") != 1
                or not all(0x21 <= byte <= 0x7e for byte in raw[:-1])):
            raise ValueError(f"SDK release selection {field} must be one visible ASCII SemVer line with LF")
        selection[field] = require_semver(raw[:-1].decode("ascii"), f"SDK release selection {field}")
    if "-" in selection["defaultRuntimeVersion"]:
        raise ValueError("SDK default Runtime must be a stable release")
    return selection


def require_sdk_release_selection(repository_root: Path, revision: str, *,
                                  sdk_version: str, runtime_version: str) -> dict[str, str]:
    """Compare caller SDK and already-authenticated aggregate versions to policy.

    The caller owns revision selection and full aggregate authentication. This
    ordinary result neither grants trust nor chooses compatibility ranges.
    """
    selection = read_sdk_release_selection(repository_root, revision)
    if require_semver(sdk_version, "Selected SDK version") != selection["sdkVersion"]:
        raise ValueError("Selected SDK version differs from the original SDK release selection")
    if require_semver(runtime_version, "Authenticated aggregate Runtime version") != selection["defaultRuntimeVersion"]:
        raise ValueError("Authenticated aggregate Runtime version differs from the SDK selected default")
    return selection


def read_sdk_runtime_compatibility_policy(repository_root: Path, revision: str) -> dict[str, str]:
    """Read mandatory original range policy alongside the selected stable default."""
    selected = read_sdk_release_selection(repository_root, revision)
    fields = ("compatibleReleaseRange", "compatibleRuntimeCompatibilityRange")
    policy = require_exact_keys(load_canonical_json_bytes(git_regular_blob_bytes(
        Path(repository_root), revision, "gradle/release/sdk-runtime-compatibility.json", max_bytes=4096)),
        set(fields), "SDK Runtime compatibility policy")
    bounds = {field: _compatible_range(policy[field], f"SDK Runtime compatibility policy.{field}")
              for field in fields}
    default = tuple(int(part) for part in selected["defaultRuntimeVersion"].split("."))
    for field in fields:
        if not bounds[field][0] <= default < bounds[field][1]:
            raise ValueError(f"SDK selected default Runtime is outside {field}")
    compatibility = (*default[:2], 0)
    lower, upper = bounds["compatibleRuntimeCompatibilityRange"]
    if not lower <= compatibility < upper:
        raise ValueError("SDK selected Runtime compatibility identity is outside compatibleRuntimeCompatibilityRange")
    return policy


def require_sdk_runtime_compatibility_policy(repository_root: Path, revision: str, *,
                                           compatible_release_range: str,
                                           compatible_runtime_compatibility_range: str) -> dict[str, str]:
    """Require explicit caller ranges to equal the original Git policy, without defaults."""
    policy = read_sdk_runtime_compatibility_policy(repository_root, revision)
    if (compatible_release_range != policy["compatibleReleaseRange"]
            or compatible_runtime_compatibility_range != policy["compatibleRuntimeCompatibilityRange"]):
        raise ValueError("Caller SDK Runtime ranges differ from the original Git compatibility policy")
    return policy
