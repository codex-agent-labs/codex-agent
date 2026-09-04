"""Package raw SDK Maven artifacts with the authenticated compatibility resource."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

from .inventory import read_regular_file_bytes, require_regular_directory


RESOURCE = "META-INF/codex-agent/sdk-compatibility.json"
KLIB_RESOURCE = f"default/resources/{RESOURCE}"
COMPONENT_CARRIERS = {
    "sdk-core": {
        "codex-agent": ("jar", RESOURCE),
        "codex-agent-android": ("aar", RESOURCE),
        "codex-agent-iosarm64": ("klib", KLIB_RESOURCE),
        "codex-agent-iossimulatorarm64": ("klib", KLIB_RESOURCE),
        "codex-agent-js": ("klib", KLIB_RESOURCE),
        "codex-agent-jvm": ("jar", RESOURCE),
        "codex-agent-linuxarm64": ("klib", KLIB_RESOURCE),
        "codex-agent-linuxx64": ("klib", KLIB_RESOURCE),
        "codex-agent-macosarm64": ("klib", KLIB_RESOURCE),
        "codex-agent-macosx64": ("klib", KLIB_RESOURCE),
        "codex-agent-mingwx64": ("klib", KLIB_RESOURCE),
        "codex-agent-wasm-js": ("klib", KLIB_RESOURCE),
    },
    "sdk-android": {"codex-agent-runtime-android": ("aar", RESOURCE)},
    "sdk-ios": {
        "codex-agent-runtime-ios": ("jar", RESOURCE),
        "codex-agent-runtime-ios-iosarm64": ("klib", KLIB_RESOURCE),
        "codex-agent-runtime-ios-iossimulatorarm64": ("klib", KLIB_RESOURCE),
    },
}
COMPONENT_ARTIFACTS = {
    component: set(carriers) | ({"codex-agent-bom"} if component == "sdk-core" else set())
    for component, carriers in COMPONENT_CARRIERS.items()
}
CHECKSUMS = {".md5": "md5", ".sha1": "sha1", ".sha256": "sha256", ".sha512": "sha512"}


def _digest(contents: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, contents).hexdigest()


def _zip_members(contents: bytes, label: str) -> dict[str, tuple[bytes, int, int]]:
    members: dict[str, tuple[bytes, int, int]] = {}
    seen: set[str] = set()
    with tempfile.TemporaryFile() as temporary:
        temporary.write(contents)
        temporary.seek(0)
        with zipfile.ZipFile(temporary) as archive:
            for entry in archive.infolist():
                name = entry.filename
                path = PurePosixPath(name)
                mode = entry.external_attr >> 16
                normalized = str(path) + ("/" if entry.is_dir() else "")
                file_type = stat.S_IFMT(mode)
                if (normalized in seen or normalized != name or
                        any(ord(character) < 32 or ord(character) == 127 for character in name) or
                        "\\" in name or path.is_absolute() or ".." in path.parts or
                        stat.S_ISLNK(mode) or file_type not in {0, stat.S_IFREG, stat.S_IFDIR}):
                    raise ValueError(f"unsafe or duplicate {label} member: {name}")
                seen.add(normalized)
                if not entry.is_dir():
                    members[name] = (archive.read(entry), mode or (stat.S_IFREG | 0o644), entry.compress_type)
    return members


def _write_zip(members: dict[str, tuple[bytes, int, int]]) -> bytes:
    with tempfile.TemporaryFile() as temporary:
        with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
            for name, (contents, mode, compression) in sorted(members.items()):
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = mode << 16
                entry.compress_type = compression
                archive.writestr(entry, contents, compress_type=compression, compresslevel=9)
        temporary.seek(0)
        return temporary.read()


def _inject_archive(archive: Path, kind: str, path: str, compatibility: bytes) -> None:
    members = _zip_members(read_regular_file_bytes(archive, reject_symlink_parents=True), archive.name)
    if kind == "aar":
        if any(PurePosixPath(name).name == "sdk-compatibility.json" for name in members):
            raise ValueError(f"raw Android binary already contains SDK compatibility: {archive.name}")
        classes = members.get("classes.jar")
        if classes is None:
            raise ValueError(f"Android archive lacks classes.jar: {archive.name}")
        nested = _zip_members(classes[0], f"{archive.name}!/classes.jar")
        if path in nested or any(PurePosixPath(name).name == "sdk-compatibility.json" for name in nested):
            raise ValueError(f"raw Android binary already contains SDK compatibility: {archive.name}")
        nested[path] = (compatibility, stat.S_IFREG | 0o644, zipfile.ZIP_DEFLATED)
        members["classes.jar"] = (_write_zip(nested), classes[1], classes[2])
    else:
        if path in members or any(PurePosixPath(name).name == "sdk-compatibility.json" for name in members):
            raise ValueError(f"raw SDK binary already contains compatibility: {archive.name}")
        members[path] = (compatibility, stat.S_IFREG | 0o644, zipfile.ZIP_DEFLATED)
    archive.write_bytes(_write_zip(members))


def _verify_archive(archive: Path, kind: str, path: str, compatibility: bytes) -> None:
    members = _zip_members(read_regular_file_bytes(archive, reject_symlink_parents=True), archive.name)
    if kind == "aar":
        if any(PurePosixPath(name).name == "sdk-compatibility.json" for name in members):
            raise ValueError(f"SDK compatibility archive inventory mismatch: {archive.name}")
        classes = members.get("classes.jar")
        if classes is None:
            raise ValueError(f"Android archive lacks classes.jar: {archive.name}")
        members = _zip_members(classes[0], f"{archive.name}!/classes.jar")
    declarations = {name: value[0] for name, value in members.items()
                    if PurePosixPath(name).name == "sdk-compatibility.json"}
    if declarations != {path: compatibility}:
        raise ValueError(f"SDK compatibility archive inventory mismatch: {archive.name}")


def _update_module_metadata(repository: Path, changed: dict[str, bytes]) -> None:
    def update(value: object, archive_name: str, contents: bytes) -> int:
        if not isinstance(value, dict) or not isinstance(value.get("variants"), list):
            raise ValueError("Gradle module metadata has no variants array")
        referenced = 0
        for variant in value["variants"]:
            if not isinstance(variant, dict):
                raise ValueError("Gradle module metadata variant is not an object")
            files = variant.get("files")
            if files is None:
                continue
            if not isinstance(files, list) or any(not isinstance(record, dict) for record in files):
                raise ValueError("Gradle module metadata files are malformed")
            for record in files:
                if record.get("name") != archive_name or record.get("url") != archive_name:
                    continue
                if not set(("size", *CHECKSUMS.values())).issubset(record):
                    raise ValueError("Gradle module metadata carrier record is incomplete")
                record["size"] = len(contents)
                for algorithm in CHECKSUMS.values():
                    record[algorithm] = _digest(contents, algorithm)
                referenced += 1
        return referenced

    for archive_relative, contents in sorted(changed.items()):
        archive = repository.joinpath(*PurePosixPath(archive_relative).parts)
        archive_name = archive.name
        matches = sorted(path for path in repository.rglob(archive_name) if path.is_file())
        if matches != [archive]:
            raise ValueError(f"packaged SDK artifact path is missing or ambiguous: {archive_relative}")
        module = archive.with_name(archive.name.removesuffix(archive.suffix) + ".module")
        if module.is_symlink() or not module.is_file():
            raise ValueError(f"exact owning Gradle module metadata is missing: {module}")
        value = json.loads(module.read_text(encoding="utf-8"))
        referenced = update(value, archive_name, contents)
        module.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if referenced == 0:
            raise ValueError(f"packaged SDK artifact is absent from its exact Gradle module metadata: {archive_name}")


def _refresh_checksums(repository: Path) -> None:
    for sidecar in sorted(path for path in repository.rglob("*") if path.is_file() and
                          any(path.name.endswith(suffix) for suffix in CHECKSUMS)):
        suffix, algorithm = next((suffix, algorithm) for suffix, algorithm in CHECKSUMS.items()
                                 if sidecar.name.endswith(suffix))
        primary = sidecar.with_name(sidecar.name.removesuffix(suffix))
        if not primary.is_file() or primary.is_symlink():
            raise ValueError(f"Maven checksum has no regular primary: {sidecar}")
        sidecar.write_text(_digest(primary.read_bytes(), algorithm) + "\n", encoding="ascii")


def package_sdk_maven(
    source: Path,
    output: Path,
    compatibility_file: Path,
    group_id: str,
    version: str,
    component: str,
) -> None:
    carriers = COMPONENT_CARRIERS.get(component)
    if carriers is None:
        raise ValueError(f"unsupported SDK Maven component: {component}")
    source = require_regular_directory(source, "SDK binary Maven repository")
    compatibility = read_regular_file_bytes(
        compatibility_file, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    if compatibility_file.name != "sdk-compatibility.json":
        raise ValueError("SDK compatibility input has the wrong name")
    if output.exists() or output.is_symlink():
        raise ValueError(f"SDK Maven package output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, output, symlinks=True)
    try:
        if any(path.is_symlink() for path in output.rglob("*")):
            raise ValueError("SDK binary Maven repository contains a symbolic path")
        if any(path.is_file() and path.name.endswith(".asc") for path in output.rglob("*")):
            raise ValueError("SDK binary Maven repository must be unsigned before packaging")
        group = output / group_id.replace(".", "/")
        group_entries = list(group.iterdir()) if group.is_dir() and not group.is_symlink() else []
        if (not group_entries or any(not path.is_dir() or path.is_symlink() for path in group_entries) or
                {path.name for path in group_entries} != COMPONENT_ARTIFACTS[component]):
            raise ValueError(f"SDK binary Maven artifact inventory mismatch: {component}")
        changed: dict[str, bytes] = {}
        for artifact, (kind, resource_path) in carriers.items():
            archive = group / artifact / version / f"{artifact}-{version}.{kind}"
            if not archive.is_file() or archive.is_symlink():
                raise ValueError(f"SDK binary carrier is missing: {archive.relative_to(output)}")
            _inject_archive(archive, kind, resource_path, compatibility)
            _verify_archive(archive, kind, resource_path, compatibility)
            changed[archive.relative_to(output).as_posix()] = archive.read_bytes()
        _update_module_metadata(output, changed)
        _refresh_checksums(output)
    except Exception:
        shutil.rmtree(output)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compatibility", type=Path, required=True)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--component", choices=tuple(COMPONENT_CARRIERS), required=True)
    args = parser.parse_args(argv)
    package_sdk_maven(
        args.source.resolve(), args.output.resolve(), args.compatibility.resolve(),
        args.group_id, args.version, args.component,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
