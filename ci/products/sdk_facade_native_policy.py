"""Compare the captured native compiler subset with one immutable archive pin.

Only macOS ARM64 has a reviewed archive in the existing verification metadata.
Schema 1 covers konan/lib/** and konan/konan.properties; schema 2 also binds the
compiler fingerprint. Neither comparison authenticates the complete installation, LLVM/libffi/sysroot dependencies,
JDK, or hosted execution. Successful comparison grants none of those authorities.
The caller independently binds the original capture, host and policy revision.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tarfile
import tomllib

from .inventory import (
    _open_regular_file, _stat_identity, git_regular_blob_bytes, load_json_bytes,
    read_regular_file_bytes, require_exact_keys, require_integer, require_relative_path,
    require_regular_directory, require_semver, run_git,
)
from .restore import OBJECT_ZIP_LIMITS
from .sdk_facade_compiler_policy import _TOP, _TOOLS, compiler_observation_inventory
from .sdk_facade_validation import FACADE_CONSUMER_TASKS, _original_path
from .toolchain import _metadata_checksum, _revision, RUNTIME_VERIFICATION_METADATA, VERSION_CATALOG


_LIMIT = 16 * 1024 * 1024
_TARGETS = {"macos-arm64", "ios-arm64", "ios-simulator-arm64"}
# The pinned macOS ARM64 2.3.10 tar has 44,701 members / 853,156,366 payload
# bytes (largest member 80,644,391 bytes), plus 42,581 GNU longname headers
# (6,711,024 metadata bytes): 87,282 physical headers total. Unlike a product
# ZIP it includes platform caches. Keep all product size/ratio bounds, with
# separate finite logical-member and physical-header bounds.
_LIMITS = {**OBJECT_ZIP_LIMITS, "max_members": 65_536, "max_headers": 131_072}


def _archive_subset(stream, version, *, include_fingerprint=False):
    prefix = f"kotlin-native-prebuilt-macos-aarch64-{version}"
    archive_bytes = os.fstat(stream.fileno()).st_size
    headers, total = 0, 0

    class BoundedTarInfo(tarfile.TarInfo):
        def _proc_member(self, archive):
            nonlocal headers, total
            # Guard before tarfile reads extended-header payloads. Newer Python
            # versions bypass public frombuf when parsing stream headers.
            member = self
            headers += 1
            total += member.size
            if (headers > _LIMITS["max_headers"] or member.size < 0
                    or member.size > _LIMITS["max_entry_bytes"]
                    or total > _LIMITS["max_total_bytes"]
                    or total > archive_bytes * _LIMITS["max_compression_ratio"]):
                raise ValueError("Native archive exceeds bounded archive limits")
            if member.type in (tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.GNUTYPE_LONGNAME,
                               tarfile.GNUTYPE_LONGLINK, tarfile.SOLARIS_XHDTYPE):
                if member.size > _LIMITS["max_central_directory_bytes"]:
                    raise ValueError("Native archive control metadata exceeds inherited limits")
            elif not (member.isfile() or member.isdir()) or member.type == tarfile.GNUTYPE_SPARSE:
                raise ValueError("Native archive has unsafe member type")
            return super()._proc_member(archive)

    seen, files, directories, selected = set(), set(), set(), {}
    payload_total = 0
    try:
        with tarfile.open(fileobj=stream, mode="r|gz", tarinfo=BoundedTarInfo) as archive:
            for member in archive:
                payload_total += member.size
                if (len(seen) + 1 > _LIMITS["max_members"]
                        or member.size < 0 or member.size > _LIMITS["max_entry_bytes"]
                        or payload_total > _LIMITS["max_total_bytes"]
                        or payload_total > archive_bytes * _LIMITS["max_compression_ratio"]):
                    raise ValueError("Native archive exceeds bounded archive limits")
                name = require_relative_path(member.name, "Native archive member")
                path = PurePosixPath(name)
                if (name in seen or path.parts[0] != prefix
                        or not (member.isfile() or member.isdir())
                        or member.issparse()):
                    raise ValueError("Native archive has duplicate, foreign or unsafe members")
                if any(parent.as_posix() in files for parent in path.parents):
                    raise ValueError("Native archive file overlaps a member directory")
                if member.isfile() and name in directories:
                    raise ValueError("Native archive file overlaps a member directory")
                seen.add(name)
                directories.update(parent.as_posix() for parent in path.parents)
                (directories if member.isdir() else files).add(name)
                relative = path.relative_to(prefix).as_posix()
                if member.isfile() and (relative == "konan/konan.properties" or relative.startswith("konan/lib/")
                        or include_fingerprint and relative == "konan/compiler.fingerprint"):
                    source = archive.extractfile(member)
                    if source is None:
                        raise ValueError("Native archive selected member lacks its payload")
                    digest, size = hashlib.sha256(), 0
                    with source:
                        while chunk := source.read(1024 * 1024):
                            digest.update(chunk)
                            size += len(chunk)
                            if size > member.size:
                                raise ValueError("Native archive selected member exceeds declared size")
                    if size != member.size:
                        raise ValueError("Native archive selected member is truncated")
                    selected[relative] = {"bytes": size, "sha256": digest.hexdigest()}
    except (tarfile.TarError, EOFError) as error:
        raise ValueError("Native compiler archive is malformed") from error
    if ("konan/konan.properties" not in selected
            or "konan/lib/kotlin-native-compiler-embeddable.jar" not in selected
            or include_fingerprint and "konan/compiler.fingerprint" not in selected):
        raise ValueError("Pinned native archive lacks the selected compiler subset")
    return selected


def verify_facade_native_compiler_artifacts(*, repository, policy_revision,
        compiler_inputs, native_archive, expected_host) -> None:
    """Compare selected native bytes only; never execute tools or read old paths."""
    if expected_host != "macos-arm64":
        raise ValueError("Native compiler archive policy supports only explicitly selected macos-arm64")
    revision = _revision(policy_revision)
    root = Path(repository)
    require_regular_directory(root, "Native compiler policy repository")
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Native compiler policy repository must be absolute and normalized")
    observation_path = Path(compiler_inputs)
    raw = read_regular_file_bytes(observation_path, max_bytes=_LIMIT, reject_symlink_parents=True)
    value = load_json_bytes(raw)
    schema = require_integer(value.get("schemaVersion") if type(value) is dict else None,
                             "Native compiler observation schema", 1)
    value = require_exact_keys(value, _TOP | ({"nativeSelection"} if schema == 2 else set()),
                               "Native compiler observation")
    target = value["target"]
    if type(target) is not str or target not in _TARGETS:
        raise ValueError("Native compiler observation target differs from the supported host route")
    if (schema not in {1, 2}
            or value["family"] != "native" or value["task"] != FACADE_CONSUMER_TASKS[target]
            or value["taskClass"] != "org.jetbrains.kotlin.gradle.tasks.KotlinNativeCompile"):
        raise ValueError("Native compiler observation differs from the fixed task family")
    home = _original_path(value["nativeHome"], "Original selected native distribution")
    if PureWindowsPath(home).drive or not PurePosixPath(home).is_absolute():
        raise ValueError("macOS native compiler home must be an original POSIX path")
    tools = require_exact_keys(value["tools"], _TOOLS, "Native compiler tool inventories")
    observed = {}
    native = compiler_observation_inventory(tools["native"], observed=observed)
    compiler = compiler_observation_inventory(tools["compiler"], observed=observed)
    main = home + "/konan/lib/kotlin-native-compiler-embeddable.jar"
    if len(compiler) != 1 or compiler[0]["path"] != main:
        raise ValueError("Native compiler artifact differs from the selected original distribution")
    selected = {}
    for row in native:
        if not row["path"].startswith(home + "/"):
            raise ValueError("Observed native inventory escapes the selected distribution")
        selected[row["path"][len(home) + 1:]] = {key: row[key] for key in ("bytes", "sha256")}
    if schema == 2:
        selection = require_exact_keys(value["nativeSelection"],
            {"dataDirectory", "dependenciesDirectory", "host", "target", "fingerprint", "dependencies"},
            "Native selected tool context")
        if selection["host"] != "macos_arm64" or selection["target"] != target.replace("-", "_"):
            raise ValueError("Native selected tool context differs from its host/target route")
        fingerprint = compiler_observation_inventory(selection["fingerprint"], observed=observed)
        if len(fingerprint) != 1 or fingerprint[0]["path"] != home + "/konan/compiler.fingerprint":
            raise ValueError("Native compiler fingerprint differs from its selected distribution")
        selected["konan/compiler.fingerprint"] = {key: fingerprint[0][key] for key in ("bytes", "sha256")}
        # Full original replay owns dependency-root/link semantics and provenance;
        # this partial archive policy authenticates distribution members only.
    sources = {}
    actual = None
    descriptor, before = _open_regular_file(Path(native_archive), "Caller native archive", reject_symlink_parents=True)
    with os.fdopen(descriptor, "rb") as stream:
        if before.st_size <= 0 or before.st_size > _LIMITS["max_archive_bytes"]:
            raise ValueError("Native archive exceeds bounded archive limits")
        try:
            if run_git(root, "rev-parse", f"{revision}^{{commit}}").strip() != revision:
                raise ValueError("Native compiler policy revision is not the exact commit")
            for name in (VERSION_CATALOG, RUNTIME_VERIFICATION_METADATA):
                sources[name] = git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024)
            catalog = tomllib.loads(sources[VERSION_CATALOG].decode("utf-8", errors="strict"))
            version = require_semver(catalog.get("versions", {}).get("kotlin"), "Policy Kotlin version")
            if value["kotlinVersion"] != version:
                raise ValueError("Observed native compiler version differs from immutable policy")
            name = f"kotlin-native-prebuilt-{version}-macos-aarch64.tar.gz"
            expected = _metadata_checksum(sources[RUNTIME_VERIFICATION_METADATA], name)
            actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("Caller native archive differs from the immutable artifact pin")
            stream.seek(0)
            expected_subset = (_archive_subset(stream, version, include_fingerprint=True) if schema == 2
                               else _archive_subset(stream, version))
            if selected != expected_subset:
                raise ValueError("Observed native compiler subset differs from the pinned archive")
        finally:
            stream.seek(0)
            final_digest = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            current, current_stat = _open_regular_file(Path(native_archive), "Caller native archive", reject_symlink_parents=True)
            os.close(current)
            if (_stat_identity(before) != _stat_identity(os.fstat(stream.fileno()))
                    or _stat_identity(before) != _stat_identity(current_stat)
                    or (actual is not None and final_digest != actual)
                    or read_regular_file_bytes(observation_path, max_bytes=_LIMIT, reject_symlink_parents=True) != raw
                    or any(git_regular_blob_bytes(root, revision, name, max_bytes=4 * 1024 * 1024) != data
                           for name, data in sources.items())):
                raise ValueError("Native compiler archive, observation or immutable policy changed")
