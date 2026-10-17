"""Caller-bound Apple package verification through authenticated release tooling.

The caller authenticates the original distribution proof and S858 compatibility
independently. Neither these paths nor the returned inventory grant producer,
host, receipt, or reuse authority. No Maven output exception is defined here.
"""

import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any

from .inventory import (
    _is_reparse_point, _open_created_directory, _open_directory, _open_regular_file, _stat_identity,
    _validate_snapshot_source,
    read_regular_file_bytes, require_regular_directory, require_semver,
    snapshot_regular_tree,
)
from .restore import memoized_file_inventory as regular_file_inventory
from .tooling import verified_tooling_capture
from .sdk_apple_package_source import capture_apple_package_sources


def _apple_clone_operation():
    clone = (getattr(ctypes.CDLL(None, use_errno=True), "fclonefileat", None)
             if sys.platform == "darwin" else None)
    if clone is not None:
        clone.argtypes = (ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        clone.restype = ctypes.c_int
    return clone


def _clone_apple_file(source: int, destination: int, name: str, clone) -> None:
    metadata = os.fstat(source)
    if not stat.S_ISREG(metadata.st_mode) or _is_reparse_point(metadata):
        raise ValueError("Apple snapshot source is not a regular file")
    # Keep the byte-copy behavior for immutable/other special file flags.
    if metadata.st_flags:
        raise OSError(errno.ENOTSUP, "Flagged Apple input requires byte copy")
    # fclonefileat: held regular source, held private parent, exclusive leaf.
    # CLONE_NOOWNERCOPY; no directory cloning, hardlinks or trust from xattrs.
    if clone(source, destination, os.fsencode(name), 0x2) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), name)
    target = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=destination)
    try:
        copied = os.fstat(target)
        if (not stat.S_ISREG(copied.st_mode) or copied.st_nlink != 1
                or copied.st_size != metadata.st_size
                or (copied.st_dev, copied.st_ino) == (metadata.st_dev, metadata.st_ino)):
            raise ValueError("Apple snapshot clone is not an independent regular file")
        os.fchmod(target, stat.S_IMODE(metadata.st_mode))
    finally:
        os.close(target)
    if _stat_identity(os.fstat(source)) != _stat_identity(metadata):
        raise ValueError("Apple snapshot source changed during capture")


def copy_apple_file(source: Path, destination: Path) -> None:
    """Create an independent private file; the caller still verifies all bytes."""
    clone = _apple_clone_operation()
    if clone is None:
        # Existing portable rehydration path; the private tree is verified by the caller.
        with Path(source).open("rb") as original, Path(destination).open("xb") as output:
            shutil.copyfileobj(original, output, length=1024**2)
        return
    source_descriptor, before = _open_regular_file(source, "Apple input", reject_symlink_parents=True)
    parent = None
    try:
        parent = _open_directory(Path(destination).parent, "Apple private file parent")
        try:
            _clone_apple_file(source_descriptor, parent, Path(destination).name, clone)
        except OSError as error:
            if error.errno not in {errno.ENOTSUP, errno.EXDEV}:
                raise
            output = os.open(Path(destination).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                             stat.S_IMODE(before.st_mode), dir_fd=parent)
            with os.fdopen(output, "wb") as target, os.fdopen(source_descriptor, "rb", closefd=False) as original:
                shutil.copyfileobj(original, target, length=1024**2)
                if original.tell() != before.st_size:
                    raise ValueError("Apple input changed size during copy")
        if _stat_identity(os.fstat(source_descriptor)) != _stat_identity(before):
            raise ValueError("Apple input changed during copy")
    finally:
        os.close(source_descriptor)
        if parent is not None:
            os.close(parent)


def _clone_apple_directory(source: int, destination: int, clone, *, allow_empty: bool) -> None:
    before = os.fstat(source)
    names = sorted(os.listdir(source))
    for name in names:
        metadata = os.stat(name, dir_fd=source, follow_symlinks=False)
        directory = stat.S_ISDIR(metadata.st_mode)
        if (_is_reparse_point(metadata) or not (directory or stat.S_ISREG(metadata.st_mode))
                or (not directory and not allow_empty and metadata.st_size == 0)):
            raise ValueError("Apple snapshot source contains an unsafe or empty entry")
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        descriptor = os.open(name, flags | (os.O_DIRECTORY if directory else 0), dir_fd=source)
        try:
            if _stat_identity(os.fstat(descriptor)) != _stat_identity(metadata):
                raise ValueError("Apple snapshot source changed while opening")
            if directory:
                target = _open_created_directory(
                    destination, name, stat.S_IMODE(metadata.st_mode), "Apple snapshot directory")
                try:
                    _clone_apple_directory(descriptor, target, clone, allow_empty=allow_empty)
                    os.fchmod(target, stat.S_IMODE(metadata.st_mode))
                finally:
                    os.close(target)
            else:
                _clone_apple_file(descriptor, destination, name, clone)
            if _stat_identity(os.fstat(descriptor)) != _stat_identity(metadata):
                raise ValueError("Apple snapshot source changed during capture")
        finally:
            os.close(descriptor)
    if _stat_identity(before) != _stat_identity(os.fstat(source)) or names != sorted(os.listdir(source)):
        raise ValueError("Apple snapshot source directory changed during capture")


def _snapshot_apple_tree(source: Path, destination: Path, *, allow_empty: bool = False) -> None:
    """Private copies with the caller's unchanged before/after byte inventories.

    APFS clones avoid rewriting large payloads while preserving independent files.
    Other hosts/filesystems retain the frozen descriptor-based byte-copy path.
    """
    clone = _apple_clone_operation()
    if clone is None:
        snapshot_regular_tree(source, destination, allow_empty=allow_empty)
        return
    source, destination = (Path(os.path.abspath(path)) for path in (source, destination))
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Apple snapshot source and destination must not overlap")
    source_descriptor = _open_directory(source, "Apple snapshot source")
    parent = target = None
    fallback = False
    try:
        _validate_snapshot_source(source_descriptor, allow_empty=allow_empty)
        parent = _open_directory(destination.parent, "Apple snapshot parent", create=True)
        try:
            target = _open_created_directory(parent, destination.name, 0o700, "Apple snapshot root")
        except FileExistsError as error:
            raise ValueError("Apple snapshot destination must not exist") from error
        try:
            _clone_apple_directory(source_descriptor, target, clone, allow_empty=allow_empty)
        except OSError as error:
            if error.errno not in {errno.ENOTSUP, errno.EXDEV}:
                raise
            held = os.fstat(target)
            named = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
            if (held.st_dev, held.st_ino) != (named.st_dev, named.st_ino):
                raise ValueError("Apple snapshot destination changed before fallback") from error
            os.close(target)
            target = None
            shutil.rmtree(destination.name, dir_fd=parent)
            fallback = True
    finally:
        os.close(source_descriptor)
        if target is not None:
            os.close(target)
        if parent is not None:
            os.close(parent)
    if fallback:
        snapshot_regular_tree(source, destination, allow_empty=allow_empty)


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
            _snapshot_apple_tree(source, private_sources[name], allow_empty=allow_empty)
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
            try:
                subprocess.run(command, cwd=root, env=environment, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as failure:
                if failure.stderr:
                    message = failure.stderr.decode('utf-8', errors='replace') if isinstance(failure.stderr, bytes) else failure.stderr
                    print(message, file=sys.stderr, end='')
                raise
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


def verify_sdk_apple_validation_binding_content(
    *, product_directory: Path, evidence_directory: Path, sdk_version: str,
    expected_sdk_compatibility: Path, canonical_api: Path, canonical_coverage: Path,
    consumer_source_directory: Path,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Replay selected package/binding content using authenticated tooling.

    The caller authenticates the original receipt, Contract and consumer source
    identities. Device/source/toolchain gates and phase admission remain separate.
    No product or acceptance token is emitted by this content check.
    """
    require_semver(sdk_version, "Apple SDK version")
    _verify_sdk_apple_with_tooling(
        sources={"product": (Path(product_directory), False),
                 "evidence": (Path(evidence_directory), True),
                 "consumers": (Path(consumer_source_directory), False)},
        expected_paths={"sdk-compatibility.json": Path(expected_sdk_compatibility),
                        "canonical-api.json": Path(canonical_api),
                        "canonical-coverage.json": Path(canonical_coverage)},
        command_name="verify-apple-validation-binding-content",
        argument_builder=lambda private, expected, root: {
            "product-directory": private["product"], "evidence-directory": private["evidence"],
            "consumer-source-directory": private["consumers"], "version": sdk_version,
            "sdk-compatibility": expected["sdk-compatibility.json"],
            "canonical-api": expected["canonical-api.json"],
            "canonical-coverage": expected["canonical-coverage.json"],
            "work-directory": root / "work",
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
    execution_capture_directory: Path | None = None,
) -> list[dict[str, Any]]:
    """Replay on a matching Apple host; caller authenticates original receipts and source election.

    Source bytes and toolchain expectations come from immutable Git, never the
    mutable checkout. This returns content inventory, not compiler/test proof.
    Optional capture retains external events plus their original input binding;
    the caller must authenticate both through one original execution receipt.
    """
    require_semver(sdk_version, "Apple SDK version")
    developer = Path(developer_directory)
    if not developer.is_absolute() or developer.resolve(strict=True) != developer:
        raise ValueError("Apple replay requires an explicit normalized developer directory")
    for ancestor in (developer, *developer.parents):
        require_regular_directory(ancestor, "Apple developer directory ancestry")
    capture = Path(execution_capture_directory) if execution_capture_directory is not None else None
    if capture is not None:
        if not capture.is_absolute() or capture.resolve() != capture or capture.exists():
            raise ValueError("Apple package execution capture must be fresh and normalized")
        for ancestor in capture.parents:
            require_regular_directory(ancestor, "Apple package capture ancestry")
        originals = (product_directory, binary_frameworks, expected_sdk_compatibility,
                     developer, tooling_evidence, tooling_public_key, java_executable,
                     *(path for path in (tooling_keyring, tooling_keys_directory) if path is not None))
        for original in originals:
            original = Path(original).resolve()
            if capture == original or capture in original.parents or original in capture.parents:
                raise ValueError("Apple package execution capture overlaps an original input")
    with tempfile.TemporaryDirectory(prefix="sdk-apple-package-source-") as temporary:
        source = Path(temporary).resolve() / "source"
        toolchain = capture_apple_package_sources(Path(repository), source_revision, source)
        def arguments(private, expected, root):
            values = {
                "product-directory": private["product"], "version": sdk_version,
                "binary-frameworks": private["binary"], "source-snapshot": private["source"],
                "sdk-compatibility": expected["sdk-compatibility.json"],
                "work-directory": root / "replay", "developer-directory": developer,
                "xcode-version": toolchain["xcodeVersion"], "xcode-build": toolchain["xcodeBuild"],
                "swift-version": toolchain["swiftVersion"],
            }
            if capture is not None:
                for original in (root, source):
                    if capture == original or capture in original.parents or original in capture.parents:
                        raise ValueError("Apple package execution capture overlaps private work")
                capture.mkdir()
                values.update({"execution-evidence-directory": capture / "events",
                               "execution-binding-file": capture / "input-binding.json"})
            return values
        before = _verify_sdk_apple_with_tooling(
            sources={"product": (Path(product_directory), False),
                     "binary": (Path(binary_frameworks), False), "source": (source, False)},
            expected_paths={"sdk-compatibility.json": Path(expected_sdk_compatibility)},
            command_name="capture-apple-binary-package-evidence" if capture is not None else "verify-apple-binary-package",
            argument_builder=arguments,
            repository=repository, tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
            java_executable=java_executable, policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
        )
    for ancestor in (developer, *developer.parents):
        require_regular_directory(ancestor, "Apple developer directory recheck")
    if capture is not None:
        inventory = _input_inventory(capture, allow_empty=True)
        if (not any(record["relativePath"].startswith("events/") for record in inventory)
                or {record["relativePath"].split("/")[0] for record in inventory} != {"events", "input-binding.json"}
                or not read_regular_file_bytes(capture / "input-binding.json", max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True)):
            raise ValueError("Apple package execution capture is incomplete")
    return before["product"]
