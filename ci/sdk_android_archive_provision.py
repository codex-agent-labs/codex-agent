"""Provision the Git-pinned Android Codex archive before the elected worker.

The archive hash and version come only from the authenticated candidate Git
blob. Gradle remains responsible for archive structure and binary verification.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (git_regular_blob_bytes,
    read_regular_file_bytes, require_regular_directory, require_semver,
    require_sha256, sha256_file)
from products.signing_isolation import require_no_signing_secret
from products.toolchain import _properties


_ASSET = "codex-app-server-aarch64-unknown-linux-musl"
_MAX_ARCHIVE_BYTES = 512 * 1024 * 1024


def _github_https(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443) or
            parsed.hostname not in {"github.com", "githubusercontent.com"} and
            not (parsed.hostname or "").endswith(".githubusercontent.com")):
        raise ValueError("Android Codex archive redirect must stay on GitHub HTTPS")


class _GithubRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        _github_https(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _open_archive(url):
    return build_opener(_GithubRedirect()).open(Request(url), timeout=30)


def _publish_archive(archive, destination):
    """Link one checked staging inode into a fresh name, removing only our inode on failure."""
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(archive.parent, directory_flags)
    try:
        destination_fd = os.open(destination.parent, directory_flags)
        try:
            source = os.stat(archive.name, dir_fd=source_fd, follow_symlinks=False)
            if not stat.S_ISREG(source.st_mode):
                raise ValueError("Android Codex staging archive is not a regular file")
            parent = os.fstat(destination_fd)
            if os.stat(destination.parent, follow_symlinks=False).st_ino != parent.st_ino or \
                    os.stat(destination.parent, follow_symlinks=False).st_dev != parent.st_dev:
                raise ValueError("Android archive destination parent changed")
            try:
                os.link(archive.name, destination.name, src_dir_fd=source_fd,
                        dst_dir_fd=destination_fd, follow_symlinks=False)
                published = os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
                named_parent = os.stat(destination.parent, follow_symlinks=False)
                if ((published.st_dev, published.st_ino) != (source.st_dev, source.st_ino) or
                        (named_parent.st_dev, named_parent.st_ino) != (parent.st_dev, parent.st_ino)):
                    raise ValueError("Android archive destination changed during publication")
            except BaseException:
                try:
                    current = os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if (current.st_dev, current.st_ino) == (source.st_dev, source.st_ino):
                        os.unlink(destination.name, dir_fd=destination_fd)
                raise
        finally:
            try:
                os.close(destination_fd)
            except OSError:
                pass  # Closing a held directory must not turn a published file into a failed result.
    finally:
        try:
            os.close(source_fd)
        except OSError:
            pass


def provision(plan_path, destination, *, repository_root):
    """Return a fresh externally published archive path, or publish nothing."""
    require_no_signing_secret(os.environ)
    root = Path(repository_root).resolve(strict=True)
    plan_path, destination = Path(plan_path), Path(destination)
    if (not plan_path.is_absolute() or not destination.is_absolute() or
            plan_path.resolve(strict=True) != plan_path or
            destination.parent.resolve(strict=True) != destination.parent or
            destination == root or root in destination.parents or
            destination.exists() or destination.is_symlink()):
        raise ValueError("Android archive requires an external fresh normalized destination and plan")
    require_regular_directory(destination.parent, "Android archive destination parent")
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
    plan = product_reuse._validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True:
        raise ValueError("Android archive requires an authorized product plan")
    pins = _properties(git_regular_blob_bytes(root, plan["validationCommit"],
        "gradle.properties", max_bytes=1024 * 1024), "Git-pinned Android Codex runtime")
    version = require_semver(pins["codexAgent.codexVersion"], "Git-pinned Codex version")
    if re.fullmatch(r"[0-9A-Za-z.-]+", version) is None:
        raise ValueError("Git-pinned Codex version is not a safe release tag")
    archive_sha256 = require_sha256("sha256:" + pins["codexAgent.codexArchiveSha256"],
                                    "Git-pinned Codex archive digest")
    require_sha256("sha256:" + pins["codexAgent.codexBinarySha256"],
                   "Git-pinned Codex binary digest")
    if read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                               reject_symlink_parents=True) != plan_bytes:
        raise ValueError("Android archive plan changed before download")
    url = f"https://github.com/openai/codex/releases/download/rust-v{version}/{_ASSET}.tar.gz"
    _github_https(url)
    published = False
    try:
        with tempfile.TemporaryDirectory(prefix="android-codex-", dir=destination.parent,
                                         ignore_cleanup_errors=True) as temporary:
            stage = Path(temporary)
            archive = stage / f"{_ASSET}.tar.gz"
            digest = hashlib.sha256()
            count = 0
            with _open_archive(url) as response:
                if response.status != 200:
                    raise ValueError("Android Codex archive download did not return HTTP 200")
                _github_https(response.geturl())
                with archive.open("xb") as target:
                    while chunk := response.read(1024 * 1024):
                        count += len(chunk)
                        if count > _MAX_ARCHIVE_BYTES:
                            raise ValueError("Android Codex archive exceeds the pinned size limit")
                        target.write(chunk)
                        digest.update(chunk)
            if not count or "sha256:" + digest.hexdigest() != archive_sha256 or \
                    sha256_file(archive, reject_symlink_parents=True) != archive_sha256:
                raise ValueError("Downloaded Android Codex archive differs from the Git pin")
            if read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != plan_bytes:
                raise ValueError("Android archive plan changed during download")
            if product_reuse._validate_plan(plan_path, root) != plan:
                raise ValueError("Android archive candidate changed during download")
            require_no_signing_secret(os.environ)
            _publish_archive(archive, destination)
            published = True
    except OSError:
        if not published:
            raise
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ("plan", "destination", "repository-root"):
        parser.add_argument("--" + name, type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        print(provision(arguments.plan, arguments.destination,
                        repository_root=arguments.repository_root))
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
