"""Read caller-selected SDK policy; this does not authenticate Runtime evidence."""

from pathlib import Path
import re

from .inventory import git_regular_blob_bytes, require_semver


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
