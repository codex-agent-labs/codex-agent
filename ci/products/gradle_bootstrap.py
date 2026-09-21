"""Reject missing wrapper installations before offline workers can bootstrap online.

This checks Gradle's installed-cache fast path, not distribution authenticity or
network isolation. Toolchain admission must independently authenticate tool bytes.
"""

import hashlib
from pathlib import Path
import re

from .inventory import read_regular_file_bytes, require_regular_directory
from .toolchain import _properties


def require_preprovisioned_gradle(properties_bytes: bytes, environment) -> Path:
    properties = _properties(properties_bytes, "Original Gradle wrapper properties")
    for key, expected in {
        "distributionBase": "GRADLE_USER_HOME", "distributionPath": "wrapper/dists",
        "zipStoreBase": "GRADLE_USER_HOME", "zipStorePath": "wrapper/dists",
    }.items():
        if properties.get(key) != expected:
            raise ValueError("Offline worker requires the declared Gradle user-home wrapper layout")
    url = properties.get("distributionUrl", "").replace("\\:", ":")
    match = re.fullmatch(r"https://services\.gradle\.org/distributions/(gradle-([0-9]+(?:\.[0-9]+)+)-(?:bin|all)\.zip)", url)
    if match is None or re.fullmatch(r"[0-9a-f]{64}", properties.get("distributionSha256Sum", "")) is None:
        raise ValueError("Offline worker requires an exact pinned Gradle distribution")
    home = Path(environment.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    if not home.is_absolute() or home.resolve(strict=False) != home:
        raise ValueError("Offline Gradle user home must be absolute and non-symbolic")
    # This MD5 is Gradle PathAssembler's cache locator, never a security digest.
    number = int.from_bytes(hashlib.md5(url.encode("ascii"), usedforsecurity=False).digest(), "big")
    cache_key = ""
    while number:
        number, digit = divmod(number, 36)
        cache_key = "0123456789abcdefghijklmnopqrstuvwxyz"[digit] + cache_key
    archive, version = match.groups()
    cache = home / "wrapper/dists" / archive.removesuffix(".zip") / (cache_key or "0")
    require_regular_directory(cache, "Preprovisioned Gradle wrapper cache")
    marker = cache / (archive + ".ok")
    read_regular_file_bytes(marker, max_bytes=1024, reject_symlink_parents=True)
    directories = []
    for child in cache.iterdir():
        if child.is_symlink():
            raise ValueError("Offline Gradle cache contains a symbolic entry")
        if child.is_dir():
            directories.append(child)
    installation = cache / f"gradle-{version}"
    if directories != [installation]:
        raise ValueError("Offline Gradle cache must contain exactly its selected distribution")
    lib = installation / "lib"
    require_regular_directory(lib, "Preprovisioned Gradle libraries")
    launchers = list(lib.glob("gradle-launcher-*.jar"))
    if launchers != [lib / f"gradle-launcher-{version}.jar"]:
        raise ValueError("Offline Gradle distribution must contain its exact launcher")
    if not read_regular_file_bytes(launchers[0], max_bytes=128 * 1024 * 1024, reject_symlink_parents=True):
        raise ValueError("Offline Gradle launcher is empty")
    return installation
