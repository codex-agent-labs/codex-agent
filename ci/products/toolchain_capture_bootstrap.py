"""Prepare only checksum-pinned tools for a cold protected identity capture."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
from urllib.request import urlopen

from .inventory import git_regular_blob_bytes, require_regular_directory, sha256_file, write_canonical_json
from .sdk_facade_native_policy import _archive_subset
from .toolchain import (
    HOSTS, PROFILE_SHAPES, RUNTIME_VERIFICATION_METADATA, TARGETS, VERSION_CATALOG,
    _metadata_checksum, _revision,
)


MAVEN = "https://repo.maven.apache.org/maven2/org/jetbrains/kotlin"


def _require_safe_directory_chain(path: Path) -> None:
    for directory in reversed((path, *path.parents)):
        if os.path.lexists(directory):
            require_regular_directory(directory, "Kotlin/Native data path")


def _pinned_file(url: str, destination: Path, expected: str, source: Path | None) -> None:
    if destination.exists() or destination.is_symlink():
        raise ValueError("Capture input destination must be fresh")
    stream = source.open("rb") if source is not None else urlopen(url, timeout=120)
    with stream, destination.open("xb") as output:
        if source is None and stream.status != 200:
            raise ValueError("Official capture input did not return HTTP 200")
        size = 0
        while block := stream.read(1024 * 1024):
            size += len(block)
            if size > 2 * 1024 * 1024 * 1024:
                raise ValueError("Capture input exceeds its bounded download limit")
            output.write(block)
    if sha256_file(destination) != expected:
        raise ValueError("Capture input differs from its exact Git-pinned SHA-256")


def prepare(
    repository_root: Path, repository_revision: str, profile_id: str, output_dir: Path,
    konan_data_dir: Path, *, plugin_source: Path | None = None, archive_source: Path | None = None,
) -> dict[str, str]:
    """Resolve checked-in immutable artifacts before any compiler extraction."""
    root = repository_root.resolve(strict=True)
    revision = _revision(repository_revision)
    roles = PROFILE_SHAPES.get(profile_id)
    if roles is None:
        raise ValueError("Unsupported native capture profile")
    runner_os = os.environ.get("RUNNER_OS")
    runner_arch = os.environ.get("RUNNER_ARCH")
    host = HOSTS.get((runner_os, runner_arch))
    role = "cross-builder" if profile_id == "linux-arm64" else "builder"
    if host is None or (role, runner_os, runner_arch) not in roles:
        raise ValueError("Capture input host does not match its selected profile")
    catalog = tomllib.loads(git_regular_blob_bytes(
        root, revision, VERSION_CATALOG, max_bytes=4 * 1024 * 1024,
    ).decode("utf-8"))
    version = catalog["versions"]["kotlin"]
    if version != "2.3.10":
        raise ValueError("Capture bootstrap needs reviewed Kotlin/Native artifact routing")
    metadata = git_regular_blob_bytes(
        root, revision, RUNTIME_VERIFICATION_METADATA, max_bytes=4 * 1024 * 1024,
    )
    classifier = host[1]
    extension = "zip" if runner_os == "Windows" else "tar.gz"
    archive_name = f"kotlin-native-prebuilt-{version}-{classifier}.{extension}"
    plugin_name = f"kotlin-gradle-plugin-{version}-gradle813.jar"
    output_dir = output_dir.absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise ValueError("Capture input directory must be fresh")
    konan_data_dir = konan_data_dir.absolute()
    _require_safe_directory_chain(konan_data_dir)
    output_dir.mkdir(parents=True)
    konan_data_dir.mkdir(parents=True, exist_ok=True)
    _require_safe_directory_chain(konan_data_dir)
    dependencies = konan_data_dir / "dependencies"
    if os.path.lexists(dependencies):
        require_regular_directory(dependencies, "Kotlin/Native dependency root")
    plugin = output_dir / plugin_name
    archive = output_dir / archive_name
    _pinned_file(
        f"{MAVEN}/kotlin-gradle-plugin/{version}/{plugin_name}", plugin,
        _metadata_checksum(metadata, plugin_name), plugin_source,
    )
    _pinned_file(
        f"{MAVEN}/kotlin-native-prebuilt/{version}/{archive_name}", archive,
        _metadata_checksum(metadata, archive_name), archive_source,
    )
    with archive.open("rb") as stream:
        _archive_subset(stream, version, classifier=classifier, include_fingerprint=True)
    prefix = f"kotlin-native-prebuilt-{classifier}-{version}"
    compiler = konan_data_dir / prefix
    if compiler.exists() or compiler.is_symlink():
        raise ValueError("Capture compiler installation must be fresh")
    with tempfile.TemporaryDirectory(prefix=".toolchain-capture-", dir=konan_data_dir) as temporary:
        extracted = Path(temporary)
        shutil.unpack_archive(archive, extracted, format="zip" if extension == "zip" else "gztar")
        staged = extracted / prefix
        if not staged.is_dir() or staged.is_symlink():
            raise ValueError("Pinned archive lacks its expected compiler root")
        staged.rename(compiler)
    konanc = compiler / "bin" / ("konanc.bat" if runner_os == "Windows" else "konanc")
    if not konanc.is_file() or konanc.is_symlink():
        raise ValueError("Pinned compiler lacks its dependency-only launcher")
    subprocess.run(
        (str(konanc), "-target", TARGETS[profile_id], "-Xcheck-dependencies"),
        check=True, env={**os.environ, "KONAN_DATA_DIR": str(konan_data_dir)},
    )
    paths = {
        "archive": str(archive), "compiler": str(compiler), "konanDataDir": str(konan_data_dir),
        "konanTarget": TARGETS[profile_id], "plugin": str(plugin),
    }
    write_canonical_json(output_dir / "paths.json", paths)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("repository-root", "repository-revision", "profile-id", "output-dir", "konan-data-dir"):
        parser.add_argument("--" + name, required=True)
    arguments = parser.parse_args(argv)
    try:
        prepare(Path(arguments.repository_root), arguments.repository_revision, arguments.profile_id,
                Path(arguments.output_dir), Path(arguments.konan_data_dir))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
