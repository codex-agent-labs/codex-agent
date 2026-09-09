"""Caller-bound Apple package verification through authenticated release tooling.

The caller authenticates the original distribution proof and S858 compatibility
independently. Neither these paths nor the returned inventory grant producer,
host, receipt, or reuse authority. No Maven output exception is defined here.
"""

import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .inventory import (
    read_regular_file_bytes, regular_file_inventory, require_regular_directory, require_semver,
    snapshot_regular_tree,
)
from .tooling import verified_tooling_capture


def _input_inventory(path: Path, *, allow_empty: bool):
    for ancestor in (path.absolute(), *path.absolute().parents):
        require_regular_directory(ancestor, "Apple SDK input ancestry")
    return regular_file_inventory(path, allow_empty=allow_empty)


def verify_sdk_apple_package_content(
    *, product_directory: Path, validation_evidence_directory: Path, sdk_version: str,
    expected_sdk_compatibility: Path, expected_distribution_proof: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Return exact original product inventory only after the fixed full gate.

    Java and the Git policy revision are trusted caller inputs, not imported
    record fields. Empty original diagnostics remain external evidence; product
    files and the two caller expectations must be nonempty.
    """
    require_semver(sdk_version, "Apple SDK version")
    if (type(policy_revision) is not str or len(policy_revision) != 40
            or any(character not in "0123456789abcdef" for character in policy_revision)):
        raise ValueError("Apple SDK verification requires an exact trusted Git policy revision")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("Apple SDK verification requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    sources = {"product": Path(product_directory), "validation": Path(validation_evidence_directory)}
    left, right = (source.resolve() for source in sources.values())
    if left == right or left in right.parents or right in left.parents:
        raise ValueError("Apple SDK product and external validation inputs must not overlap")
    before = {name: _input_inventory(source, allow_empty=name == "validation")
              for name, source in sources.items()}
    expected_paths = {"sdk-compatibility.json": Path(expected_sdk_compatibility),
                      "verified-distribution-proof.json": Path(expected_distribution_proof)}
    expected_bytes = {name: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                                   reject_symlink_parents=True)
                      for name, path in expected_paths.items()}
    if not all(expected_bytes.values()):
        raise ValueError("Apple SDK caller expectations must be nonempty")
    with tempfile.TemporaryDirectory(prefix="sdk-apple-verification-") as temporary:
        root = Path(temporary).resolve()
        for source in (*sources.values(), *expected_paths.values(), java_executable,
                       Path(tooling_evidence), Path(tooling_public_key),
                       *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)):
            source = source.resolve()
            if source == root or source in root.parents or root in source.parents:
                raise ValueError("Apple SDK private verification work overlaps an original input")
        for name, source in sources.items():
            snapshot_regular_tree(source, root / name, allow_empty=name == "validation")
            if _input_inventory(root / name, allow_empty=name == "validation") != before[name]:
                raise ValueError("Apple SDK original input changed during capture")
        expected = root / "expected"
        expected.mkdir()
        for name, data in expected_bytes.items():
            (expected / name).write_bytes(data)
        with verified_tooling_capture(
            tooling_evidence, repository, tooling_public_key,
            required_trust_domain=required_trust_domain, keyring=tooling_keyring,
            keys_directory=tooling_keys_directory, policy_revision=policy_revision,
        ) as jar:
            arguments = {
                "product-directory": root / "product",
                "validation-evidence-directory": root / "validation",
                "version": sdk_version,
                "owned-build-directory": root / "owned",
                "work-directory": root / "owned/work",
                "expected-sdk-compatibility": expected / "sdk-compatibility.json",
                "expected-distribution-proof": expected / "verified-distribution-proof.json",
            }
            command = [str(java_executable), "-jar", str(jar),
                       "verify-transported-apple-sdk-package-closure"]
            command += [part for key, value in arguments.items() for part in (f"--{key}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
            }}
            subprocess.run(command, cwd=root, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for name, source in sources.items():
            if any(_input_inventory(path, allow_empty=name == "validation") != before[name]
                   for path in (source, root / name)):
                raise ValueError("Original or captured Apple SDK input changed during verification")
        for name, source in expected_paths.items():
            if any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != expected_bytes[name]
                   for path in (source, expected / name)):
                raise ValueError("Original or captured Apple SDK expectation changed during verification")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during Apple SDK verification")
    return before["product"]
