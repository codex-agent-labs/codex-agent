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
from .sdk_apple_package_source import capture_apple_package_sources


def _input_inventory(path: Path, *, allow_empty: bool):
    for ancestor in (path.absolute(), *path.absolute().parents):
        require_regular_directory(ancestor, "Apple SDK input ancestry")
    return regular_file_inventory(path, allow_empty=allow_empty)


def _verify_sdk_apple_with_tooling(
    *, sources: dict[str, tuple[Path, bool]], expected_paths: dict[str, Path],
    command_name: str, argument_builder,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if (type(policy_revision) is not str or len(policy_revision) != 40
            or any(character not in "0123456789abcdef" for character in policy_revision)):
        raise ValueError("Apple SDK verification requires an exact trusted Git policy revision")
    java_executable = Path(java_executable)
    if not java_executable.is_absolute() or java_executable.name not in {"java", "java.exe"}:
        raise ValueError("Apple SDK verification requires an explicit trusted Java executable")
    java_bytes = read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                                         reject_symlink_parents=True)
    normalized_sources = {name: (Path(source), allow_empty)
                          for name, (source, allow_empty) in sources.items()}
    resolved = [source.resolve() for source, _ in normalized_sources.values()]
    if any(left == right or left in right.parents or right in left.parents
           for index, left in enumerate(resolved) for right in resolved[index + 1:]):
        raise ValueError("Apple SDK source inputs must not overlap")
    before = {name: _input_inventory(source, allow_empty=allow_empty)
              for name, (source, allow_empty) in normalized_sources.items()}
    expected_paths = {name: Path(path) for name, path in expected_paths.items()}
    expected_bytes = {name: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                                   reject_symlink_parents=True)
                      for name, path in expected_paths.items()}
    if not all(expected_bytes.values()):
        raise ValueError("Apple SDK caller expectations must be nonempty")
    with tempfile.TemporaryDirectory(prefix="sdk-apple-verification-") as temporary:
        root = Path(temporary).resolve()
        for source in (*(source for source, _ in normalized_sources.values()), *expected_paths.values(), java_executable,
                       Path(tooling_evidence), Path(tooling_public_key),
                       *(Path(path) for path in (tooling_keyring, tooling_keys_directory) if path is not None)):
            source = source.resolve()
            if source == root or source in root.parents or root in source.parents:
                raise ValueError("Apple SDK private verification work overlaps an original input")
        private_sources = {}
        for name, (source, allow_empty) in normalized_sources.items():
            private_sources[name] = root / name
            snapshot_regular_tree(source, private_sources[name], allow_empty=allow_empty)
            if _input_inventory(private_sources[name], allow_empty=allow_empty) != before[name]:
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
            private_expected = {name: expected / name for name in expected_paths}
            arguments = argument_builder(private_sources, private_expected, root)
            command = [str(java_executable), "-jar", str(jar), command_name]
            command += [part for key, value in arguments.items() for part in (f"--{key}", str(value))]
            environment = {key: value for key, value in os.environ.items() if key in {
                "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL",
            }}
            subprocess.run(command, cwd=root, env=environment, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for name, (source, allow_empty) in normalized_sources.items():
            if any(_input_inventory(path, allow_empty=allow_empty) != before[name]
                   for path in (source, private_sources[name])):
                raise ValueError("Original or captured Apple SDK input changed during verification")
        for name, source in expected_paths.items():
            if any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != expected_bytes[name]
                   for path in (source, expected / name)):
                raise ValueError("Original or captured Apple SDK expectation changed during verification")
    if read_regular_file_bytes(java_executable, max_bytes=128 * 1024 * 1024,
                               reject_symlink_parents=True) != java_bytes:
        raise ValueError("Trusted Java executable changed during Apple SDK verification")
    return before


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
    expected_paths = {
        "sdk-compatibility.json": Path(expected_sdk_compatibility),
        "verified-distribution-proof.json": Path(expected_distribution_proof),
    }
    before = _verify_sdk_apple_with_tooling(
        sources={"product": (Path(product_directory), False),
                 "validation": (Path(validation_evidence_directory), True)},
        expected_paths=expected_paths,
        command_name="verify-transported-apple-sdk-package-closure",
        argument_builder=lambda private, expected, root: {
            "product-directory": private["product"],
            "validation-evidence-directory": private["validation"],
            "version": sdk_version,
            "owned-build-directory": root / "owned",
            "work-directory": root / "owned/work",
            "expected-sdk-compatibility": expected["sdk-compatibility.json"],
            "expected-distribution-proof": expected["verified-distribution-proof.json"],
        },
        repository=repository, tooling_evidence=tooling_evidence,
        tooling_public_key=tooling_public_key, java_executable=java_executable,
        policy_revision=policy_revision, required_trust_domain=required_trust_domain,
        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
    )
    return before["product"]


def verify_sdk_apple_original_execution(
    *, distribution_directory: Path, execution_directory: Path,
    expected_sdk_compatibility: Path, expected_distribution_proof: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Replay original Apple observations; the caller authenticates their source identity."""
    expected_paths = {
        "sdk-compatibility.json": Path(expected_sdk_compatibility),
        "verified-distribution-proof.json": Path(expected_distribution_proof),
    }
    _verify_sdk_apple_with_tooling(
        sources={"distribution": (Path(distribution_directory), False),
                 "execution": (Path(execution_directory), True)},
        expected_paths=expected_paths,
        command_name="verify-original-apple-execution",
        argument_builder=lambda private, expected, _root: {
            "distribution-directory": private["distribution"],
            "execution-directory": private["execution"],
            "expected-distribution-proof": expected["verified-distribution-proof.json"],
            "expected-sdk-compatibility": expected["sdk-compatibility.json"],
        },
        repository=repository, tooling_evidence=tooling_evidence,
        tooling_public_key=tooling_public_key, java_executable=java_executable,
        policy_revision=policy_revision, required_trust_domain=required_trust_domain,
        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
    )


def verify_sdk_apple_binary_package_content(
    *, product_directory: Path, binary_frameworks: Path, sdk_version: str,
    expected_sdk_compatibility: Path, source_revision: str, developer_directory: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Replay on a matching Apple host; caller authenticates original receipts and source election.

    Source bytes and toolchain expectations come from immutable Git, never the
    mutable checkout. This returns content inventory, not compiler/test proof.
    """
    require_semver(sdk_version, "Apple SDK version")
    developer = Path(developer_directory)
    if not developer.is_absolute() or developer.resolve(strict=True) != developer:
        raise ValueError("Apple replay requires an explicit normalized developer directory")
    for ancestor in (developer, *developer.parents):
        require_regular_directory(ancestor, "Apple developer directory ancestry")
    with tempfile.TemporaryDirectory(prefix="sdk-apple-package-source-") as temporary:
        source = Path(temporary).resolve() / "source"
        toolchain = capture_apple_package_sources(Path(repository), source_revision, source)
        before = _verify_sdk_apple_with_tooling(
            sources={"product": (Path(product_directory), False),
                     "binary": (Path(binary_frameworks), False), "source": (source, False)},
            expected_paths={"sdk-compatibility.json": Path(expected_sdk_compatibility)},
            command_name="verify-apple-binary-package",
            argument_builder=lambda private, expected, root: {
                "product-directory": private["product"], "version": sdk_version,
                "binary-frameworks": private["binary"], "source-snapshot": private["source"],
                "sdk-compatibility": expected["sdk-compatibility.json"],
                "work-directory": root / "replay", "developer-directory": developer,
                "xcode-version": toolchain["xcodeVersion"], "xcode-build": toolchain["xcodeBuild"],
                "swift-version": toolchain["swiftVersion"],
            },
            repository=repository, tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
        )
    for ancestor in (developer, *developer.parents):
        require_regular_directory(ancestor, "Apple developer directory recheck")
    return before["product"]
