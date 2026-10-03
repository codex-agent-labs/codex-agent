"""Compare the captured native compiler subset with its immutable host archive pin.

An absent host checksum fails closed before archive parsing.
Schema 1 covers konan/lib/** and konan/konan.properties; schema 2 also binds the
compiler fingerprint and exact dependency selection from those pinned properties.
Neither comparison authenticates the complete installation or dependency bytes,
JDK, or hosted execution. Successful comparison grants none of those authorities.
The caller independently binds the original capture, host and policy revision.
"""

import hashlib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import tarfile
import tomllib
import zipfile

from .inventory import (
    _open_regular_file, _stat_identity, git_regular_blob_bytes, load_json_bytes,
    read_regular_file_bytes, require_array, require_exact_keys, require_integer, require_relative_path,
    require_regular_directory, require_semver, run_git,
)
from .restore import OBJECT_ZIP_LIMITS
from .sdk_facade_compiler_policy import _TOP, _TOOLS, compiler_observation_inventory
from .sdk_facade_validation import FACADE_CONSUMER_TASKS, _original_path
from .toolchain import (_expand_property, _metadata_checksum, _properties, _revision,
                       RUNTIME_VERIFICATION_METADATA, VERSION_CATALOG)


_LIMIT = 16 * 1024 * 1024
_ROUTES = {
    "macos-arm64": ("macos-arm64", "macos_arm64", "macos-aarch64", "macos_arm64"),
    "ios-arm64": ("macos-arm64", "macos_arm64", "macos-aarch64", "ios_arm64"),
    "ios-simulator-arm64": ("macos-arm64", "macos_arm64", "macos-aarch64", "ios_simulator_arm64"),
    "macos-x64": ("macos-x64", "macos_x64", "macos-x86_64", "macos_x64"),
    "linux-arm64": ("linux-x64", "linux_x64", "linux-x86_64", "linux_arm64"),
    "linux-x64": ("linux-x64", "linux_x64", "linux-x86_64", "linux_x64"),
    "windows-x64": ("windows-x64", "mingw_x64", "windows-x86_64", "mingw_x64"),
}
_TARGETS = set(_ROUTES)
# The pinned macOS ARM64 2.3.10 tar has 44,701 members / 853,156,366 payload
# bytes (largest member 80,644,391 bytes), plus 42,581 GNU longname headers
# (6,711,024 metadata bytes): 87,282 physical headers total. Unlike a product
# ZIP it includes platform caches. Keep all product size/ratio bounds, with
# separate finite logical-member and physical-header bounds.
_LIMITS = {**OBJECT_ZIP_LIMITS, "max_members": 65_536, "max_headers": 131_072}


def _archive_subset(stream, version, *, classifier="macos-aarch64", include_fingerprint=False, properties=None):
    if classifier == "windows-x86_64":
        return _zip_archive_subset(stream, version, classifier=classifier,
                                   include_fingerprint=include_fingerprint, properties=properties)
    prefix = f"kotlin-native-prebuilt-{classifier}-{version}"
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
                    retain = properties is not None and relative == "konan/konan.properties"
                    if retain and member.size > _LIMIT:
                        raise ValueError("Pinned native properties exceed the control limit")
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
                            if retain:
                                properties.extend(chunk)
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


def _zip_archive_subset(stream, version, *, classifier, include_fingerprint, properties):
    prefix = f"kotlin-native-prebuilt-{classifier}-{version}"
    archive_bytes = os.fstat(stream.fileno()).st_size
    tail_size = min(archive_bytes, 22 + 65_535)
    stream.seek(archive_bytes - tail_size)
    tail = stream.read(tail_size)
    eocd = tail.rfind(b"PK\x05\x06")
    if eocd < 0 or eocd + 22 > len(tail) or eocd + 22 + int.from_bytes(tail[eocd + 20:eocd + 22], "little") != len(tail):
        raise ValueError("Native ZIP end-of-central-directory is malformed")
    members = int.from_bytes(tail[eocd + 10:eocd + 12], "little")
    central_bytes = int.from_bytes(tail[eocd + 12:eocd + 16], "little")
    if (members == 0xFFFF or central_bytes == 0xFFFFFFFF
            or members > _LIMITS["max_members"]
            or central_bytes > _LIMITS["max_central_directory_bytes"]):
        raise ValueError("Native archive exceeds bounded archive limits")
    stream.seek(0)
    seen, files, directories, selected = set(), set(), set(), {}
    total = 0
    try:
        with zipfile.ZipFile(stream) as archive:
            entries = archive.infolist()
            if len(entries) != members:
                raise ValueError("Native ZIP central-directory member count differs")
            for entry in entries:
                name = entry.orig_filename
                directory = entry.is_dir()
                if (name != entry.filename or bool(entry.external_attr & 0x10) != directory
                        or entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError("Native ZIP has unsafe member metadata")
                name = require_relative_path(name[:-1] if directory else name, "Native ZIP member")
                path = PurePosixPath(name)
                mode = stat.S_IFMT((entry.external_attr >> 16) & 0xFFFF)
                if (name in seen or path.parts[0] != prefix
                        or mode not in ((0, stat.S_IFDIR) if directory else (0, stat.S_IFREG))
                        or (directory and entry.file_size != 0)):
                    raise ValueError("Native ZIP has duplicate, foreign or unsafe members")
                if any(parent.as_posix() in files for parent in path.parents):
                    raise ValueError("Native ZIP file overlaps a member directory")
                if not directory and name in directories:
                    raise ValueError("Native ZIP file overlaps a member directory")
                total += entry.file_size
                if (entry.file_size > _LIMITS["max_entry_bytes"]
                        or total > _LIMITS["max_total_bytes"]
                        or total > archive_bytes * _LIMITS["max_compression_ratio"]
                        or entry.file_size > max(entry.compress_size, 1) * _LIMITS["max_compression_ratio"]):
                    raise ValueError("Native archive exceeds bounded archive limits")
                seen.add(name)
                directories.update(parent.as_posix() for parent in path.parents)
                (directories if directory else files).add(name)
                relative = path.relative_to(prefix).as_posix()
                if not directory and (relative == "konan/konan.properties" or relative.startswith("konan/lib/")
                                      or include_fingerprint and relative == "konan/compiler.fingerprint"):
                    retain = properties is not None and relative == "konan/konan.properties"
                    if retain and entry.file_size > _LIMIT:
                        raise ValueError("Pinned native properties exceed the control limit")
                    digest, size = hashlib.sha256(), 0
                    with archive.open(entry) as source:
                        while chunk := source.read(1024 * 1024):
                            size += len(chunk)
                            if size > entry.file_size:
                                raise ValueError("Native ZIP selected member exceeds declared size")
                            digest.update(chunk)
                            if retain:
                                properties.extend(chunk)
                    if size != entry.file_size:
                        raise ValueError("Native ZIP selected member is truncated")
                    selected[relative] = {"bytes": size, "sha256": digest.hexdigest()}
    except (zipfile.BadZipFile, EOFError) as error:
        raise ValueError("Native compiler ZIP is malformed") from error
    if ("konan/konan.properties" not in selected
            or "konan/lib/kotlin-native-compiler-embeddable.jar" not in selected
            or include_fingerprint and "konan/compiler.fingerprint" not in selected):
        raise ValueError("Pinned native archive lacks the selected compiler subset")
    return selected


def _dependency_selection(selection, contents, observed):
    """Authenticate names from pinned properties, NOT dependency file bytes.

    Full Kotlin replay owns exact link/subtree semantics and task argument
    binding. These properties authenticate only which dependency roots belong
    to the selected distribution's default configuration.
    """
    properties = _properties(contents, "Pinned native properties")
    host, target = selection["host"], selection["target"]
    data = _original_path(selection["dataDirectory"], "Original native data directory")
    directory = _original_path(selection["dependenciesDirectory"], "Original native dependencies directory")
    windows = bool(PureWindowsPath(data).drive)
    if windows != (host == "mingw_x64"):
        raise ValueError("Native dependency path differs from its host platform")
    path = PureWindowsPath(data) if windows else PurePosixPath(data)
    if directory != str(path / "dependencies"):
        raise ValueError("Native dependency directory differs from its selected data directory")
    keys = [f"llvmHome.{host}", f"libffiDir.{host}"]
    expected = set()
    for key in keys:
        name = _expand_property(properties, key)
        if re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None or name in {".", ".."}:
            raise ValueError("Pinned native compiler dependency is not a supported named root")
        expected.add(name)
    # KGP's hostTargetList uses the host-target suffix (host alone for a native
    # host target). The reviewed archive has no generic dependencies fallback.
    # Fail closed if a future pinned distribution introduces one.
    if "dependencies" in properties:
        raise ValueError("Generic native dependency configuration is unsupported")
    suffix = target if host == target else f"{host}-{target}"
    key = "dependencies." + suffix
    if key in properties:
        for name in _expand_property(properties, key).split():
            if re.fullmatch(r"[A-Za-z0-9_.-]+", name) is None or name in {".", ".."}:
                raise ValueError("Pinned target dependency is not a supported named root")
            expected.add(name)
    names = []
    for record in require_array(selection["dependencies"], "Selected native dependencies"):
        record = require_exact_keys(record, {"name", "root", "inventory", "symlinks"},
                                    "Selected native dependency")
        name = record["name"]
        root = str(path / "dependencies" / name)
        if type(name) is not str or name not in expected or record["root"] != root:
            raise ValueError("Selected native dependency differs from the pinned property selection")
        rows = compiler_observation_inventory(record["inventory"], observed=observed)
        if any(not row["path"].startswith(root + ("\\" if windows else "/")) for row in rows):
            raise ValueError("Selected native dependency inventory escapes its named root")
        require_array(record["symlinks"], "Selected native symbolic links")
        names.append(name)
    if names != sorted(expected):
        raise ValueError("Selected native dependencies differ from the exact pinned property selection")


def verify_facade_native_compiler_artifacts(*, repository, policy_revision,
        compiler_inputs, native_archive, expected_host) -> None:
    """Compare selected native bytes only; never execute tools or read old paths."""
    if expected_host not in {route[0] for route in _ROUTES.values()}:
        raise ValueError("Native compiler archive policy requires an explicitly selected native host")
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
    if type(target) is not str or target not in _TARGETS or _ROUTES[target][0] != expected_host:
        raise ValueError("Native compiler observation target differs from the supported host route")
    if (schema not in {1, 2}
            or value["family"] != "native" or value["task"] != FACADE_CONSUMER_TASKS[target]
            or value["taskClass"] != "org.jetbrains.kotlin.gradle.tasks.KotlinNativeCompile"):
        raise ValueError("Native compiler observation differs from the fixed task family")
    home = _original_path(value["nativeHome"], "Original selected native distribution")
    windows = expected_host == "windows-x64"
    if bool(PureWindowsPath(home).drive) != windows:
        raise ValueError("Native compiler home path differs from its host platform")
    path = PureWindowsPath(home) if windows else PurePosixPath(home)
    if not path.is_absolute():
        raise ValueError("Native compiler home must be an original absolute path")
    tools = require_exact_keys(value["tools"], _TOOLS, "Native compiler tool inventories")
    observed = {}
    native = compiler_observation_inventory(tools["native"], observed=observed)
    compiler = compiler_observation_inventory(tools["compiler"], observed=observed)
    main = str(path / "konan/lib/kotlin-native-compiler-embeddable.jar")
    if len(compiler) != 1 or compiler[0]["path"] != main:
        raise ValueError("Native compiler artifact differs from the selected original distribution")
    selected = {}
    for row in native:
        if not row["path"].startswith(home + ("\\" if windows else "/")):
            raise ValueError("Observed native inventory escapes the selected distribution")
        selected[row["path"][len(home) + 1:].replace("\\", "/")] = {key: row[key] for key in ("bytes", "sha256")}
    if schema == 2:
        selection = require_exact_keys(value["nativeSelection"],
            {"dataDirectory", "dependenciesDirectory", "host", "target", "fingerprint", "dependencies"},
            "Native selected tool context")
        if (selection["host"] != _ROUTES[target][1] or selection["target"] != _ROUTES[target][3]):
            raise ValueError("Native selected tool context differs from its host/target route")
        fingerprint = compiler_observation_inventory(selection["fingerprint"], observed=observed)
        if len(fingerprint) != 1 or fingerprint[0]["path"] != str(path / "konan/compiler.fingerprint"):
            raise ValueError("Native compiler fingerprint differs from its selected distribution")
        selected["konan/compiler.fingerprint"] = {key: fingerprint[0][key] for key in ("bytes", "sha256")}
        # Dependency names are bound below after reading the pinned properties;
        # full original replay still owns link semantics and provenance.
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
            extension = "zip" if windows else "tar.gz"
            name = f"kotlin-native-prebuilt-{version}-{_ROUTES[target][2]}.{extension}"
            expected = _metadata_checksum(sources[RUNTIME_VERIFICATION_METADATA], name)
            actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("Caller native archive differs from the immutable artifact pin")
            stream.seek(0)
            properties = bytearray()
            classifier = _ROUTES[target][2]
            options = {"classifier": classifier} if classifier != "macos-aarch64" else {}
            expected_subset = (_archive_subset(stream, version, include_fingerprint=True, properties=properties, **options) if schema == 2
                               else _archive_subset(stream, version, **options))
            if selected != expected_subset:
                raise ValueError("Observed native compiler subset differs from the pinned archive")
            if schema == 2:
                _dependency_selection(selection, bytes(properties), observed)
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
