"""Fetch a Git-pinned host Kotlin/Native archive for Core validation.

Absent host checksums fail before download. The fetched file is external caller
evidence, never a product payload or a substitute for full original admission.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile
import tomllib

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (git_regular_blob_bytes, read_regular_file_bytes,
    require_regular_directory, require_semver, sha256_file)
from products.signing_isolation import require_no_signing_secret
from products.toolchain import (_metadata_checksum, RUNTIME_VERIFICATION_METADATA,
                                VERSION_CATALOG)
from sdk_android_archive_provision import (
    _publish_archive, _fetch_pinned_archive, _github_https, _open_archive,
)


_SUFFIXES = {
    "macos-arm64": "macos-aarch64", "ios-arm64": "macos-aarch64",
    "ios-simulator-arm64": "macos-aarch64", "macos-x64": "macos-x86_64",
    "linux-arm64": "linux-x86_64", "linux-x64": "linux-x86_64",
    "windows-x64": "windows-x86_64",
}
_TARGETS = set(_SUFFIXES)
_RELEASE_ROOT = "https://github.com/JetBrains/kotlin/releases/download"
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def provision(plan_path, target, destination, *, repository_root):
    """Publish fresh external archive bytes only after immutable-Git pin checks."""
    require_no_signing_secret(os.environ)
    if target not in _TARGETS:
        raise ValueError("Core native archive has no supported host route for this target")
    root = Path(repository_root).resolve(strict=True)
    plan_path, destination = Path(plan_path), Path(destination)
    if (not plan_path.is_absolute() or not destination.is_absolute()
            or plan_path.resolve(strict=True) != plan_path
            or destination.parent.resolve(strict=True) != destination.parent
            or destination == root or root in destination.parents
            or destination.exists() or destination.is_symlink()):
        raise ValueError("Core native archive requires an external fresh normalized destination and plan")
    require_regular_directory(destination.parent, "Core native archive destination parent")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    plan = product_reuse._validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True:
        raise ValueError("Core native archive requires an authorized product plan")
    revision = plan["validationCommit"]
    sources = {
        name: git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024)
        for name in (VERSION_CATALOG, RUNTIME_VERIFICATION_METADATA)
    }
    catalog = tomllib.loads(sources[VERSION_CATALOG].decode("utf-8", errors="strict"))
    version = require_semver(catalog.get("versions", {}).get("kotlin"), "Git-pinned Kotlin version")
    extension = "zip" if target == "windows-x64" else "tar.gz"
    name = f"kotlin-native-prebuilt-{version}-{_SUFFIXES[target]}.{extension}"
    expected = _metadata_checksum(sources[RUNTIME_VERIFICATION_METADATA], name)
    url = f"{_RELEASE_ROOT}/v{version}/{name}"
    _github_https(url)
    if read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                               reject_symlink_parents=True) != plan_bytes:
        raise ValueError("Core native archive plan changed before download")
    with tempfile.TemporaryDirectory(prefix="core-native-", dir=destination.parent,
                                     ignore_cleanup_errors=True) as temporary:
        archive = Path(temporary) / name
        _fetch_pinned_archive(url, archive, expected, _MAX_ARCHIVE_BYTES,
                              _open_archive, _github_https)
        if sha256_file(archive, reject_symlink_parents=True) != expected:
            raise ValueError("Core native archive differs from the immutable Git pin")
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != plan_bytes
                or product_reuse._validate_plan(plan_path, root) != plan
                or any(git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024) != data
                       for name, data in sources.items())):
            raise ValueError("Core native archive plan or policy changed during download")
        require_no_signing_secret(os.environ)
        _publish_archive(archive, destination)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "target", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path if name != "target" else str, required=True)
    arguments = parser.parse_args(argv)
    try:
        print(provision(arguments.plan, arguments.target, arguments.destination,
                        repository_root=arguments.repository_root))
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
