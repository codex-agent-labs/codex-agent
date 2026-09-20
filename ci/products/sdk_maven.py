"""Package raw SDK Maven artifacts with the authenticated compatibility resource."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any
import zipfile
import xml.etree.ElementTree as ET

from .inventory import (
    SEMVER,
    _open_regular_file,
    _stat_identity,
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    read_regular_file_bytes,
    regular_file_inventory,
    require_regular_directory,
    snapshot_regular_tree,
)
from .receipt import validate_phase_receipt, verify_output_manifest_identity
from .registry import PUBLISHED_COORDINATES, PhaseId, phase_targets
from .sdk_archive import validate_sdk_compatibility_bytes


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
ROOT_ARTIFACTS = {
    component: PUBLISHED_COORDINATES[("sdk", component)].split(":", 1)[1]
    for component in COMPONENT_CARRIERS
}
MAVEN_GROUPS = {
    component: PUBLISHED_COORDINATES[("sdk", component)].split(":", 1)[0]
    for component in COMPONENT_CARRIERS
}
_TOOLING_METADATA = {"codex-agent", "codex-agent-runtime-ios"}
_NATIVE_METADATA = {
    "codex-agent-iosarm64",
    "codex-agent-iossimulatorarm64",
    "codex-agent-macosarm64",
    "codex-agent-macosx64",
    "codex-agent-runtime-ios-iosarm64",
    "codex-agent-runtime-ios-iossimulatorarm64",
}
_CINTEROP = {
    "codex-agent-runtime-ios-iosarm64": "-cinterop-codexAgentIos.klib",
    "codex-agent-runtime-ios-iossimulatorarm64": "-cinterop-codexAgentIos.klib",
}
_NATIVE_TARGET = {
    "codex-agent-iosarm64": "ios_arm64",
    "codex-agent-iossimulatorarm64": "ios_simulator_arm64",
    "codex-agent-linuxarm64": "linux_arm64",
    "codex-agent-linuxx64": "linux_x64",
    "codex-agent-macosarm64": "macos_arm64",
    "codex-agent-macosx64": "macos_x64",
    "codex-agent-mingwx64": "mingw_x64",
    "codex-agent-runtime-ios-iosarm64": "ios_arm64",
    "codex-agent-runtime-ios-iossimulatorarm64": "ios_simulator_arm64",
}


def _artifact_suffixes(component: str, artifact: str) -> tuple[str, ...]:
    carrier = COMPONENT_CARRIERS[component].get(artifact)
    if carrier is None:
        return (".module", ".pom")
    suffixes = ["-javadoc.jar", "-sources.jar", f".{carrier[0]}", ".module", ".pom"]
    if artifact in _TOOLING_METADATA:
        suffixes.insert(1, "-kotlin-tooling-metadata.json")
    if artifact in _NATIVE_METADATA:
        suffixes.insert(1, "-metadata.jar")
    if artifact in _CINTEROP:
        suffixes.insert(0, _CINTEROP[artifact])
    return tuple(suffixes)


COMPONENT_PRIMARY_SUFFIXES = {
    component: {
        artifact: _artifact_suffixes(component, artifact)
        for artifact in sorted(COMPONENT_ARTIFACTS[component])
    }
    for component in COMPONENT_CARRIERS
}
_POM_NAMESPACE = "http://maven.apache.org/POM/4.0.0"


def _digest(contents: bytes, algorithm: str) -> str:
    return hashlib.new(algorithm, contents).hexdigest()


def _file_identity(path: Path, *, retain_contents: bool) -> tuple[bytes | None, int, dict[str, str]]:
    descriptor, before = _open_regular_file(
        path, "SDK Maven primary", reject_symlink_parents=True,
    )
    try:
        digests = {algorithm: hashlib.new(algorithm) for algorithm in CHECKSUMS.values()}
        chunks = [] if retain_contents else None
        remaining = before.st_size
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            while remaining:
                chunk = source.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                if chunks is not None:
                    chunks.append(chunk)
                for digest in digests.values():
                    digest.update(chunk)
                remaining -= len(chunk)
            grew = bool(source.read(1))
        if remaining or grew or _stat_identity(before) != _stat_identity(os.fstat(descriptor)):
            raise ValueError(f"SDK Maven primary changed during verification: {path}")
        return (
            b"".join(chunks) if chunks is not None else None,
            before.st_size,
            {algorithm: digest.hexdigest() for algorithm, digest in digests.items()},
        )
    finally:
        os.close(descriptor)


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
    validate_sdk_compatibility_bytes(compatibility)
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
    validate_sdk_compatibility_bytes(compatibility)
    declarations = {name: value[0] for name, value in members.items()
                    if PurePosixPath(name).name == "sdk-compatibility.json"}
    if declarations != {path: compatibility}:
        raise ValueError(f"SDK compatibility archive inventory mismatch: {archive.name}")


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not an object")
    return value


def _verify_pom(contents: bytes, group_id: str, artifact: str, version: str) -> None:
    try:
        text = contents.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError(f"Maven POM is not UTF-8: {artifact}") from error
    lowered = text.lower()
    declaration = lowered.split("?>", 1)[0] if lowered.startswith("<?xml") else ""
    if (text.startswith("\ufeff") or "<!doctype" in lowered or "<!entity" in lowered or
            ("encoding=" in declaration and
             'encoding="utf-8"' not in declaration and "encoding='utf-8'" not in declaration)):
        raise ValueError(f"Maven POM contains a forbidden declaration: {artifact}")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"Maven POM is malformed: {artifact}") from error
    if root.tag != f"{{{_POM_NAMESPACE}}}project":
        raise ValueError(f"Maven POM has the wrong project namespace: {artifact}")
    child_names = {
        child.tag.rsplit("}", 1)[-1]
        for child in root
        if isinstance(child.tag, str)
    }
    forbidden = {
        "parent", "profiles", "repositories", "pluginRepositories",
        "distributionManagement", "relocation",
    }
    resolution_override = child_names & forbidden
    if resolution_override or (artifact != "codex-agent-bom" and "dependencyManagement" in child_names):
        name = sorted(resolution_override or {"dependencyManagement"})[0]
        raise ValueError(f"Maven POM contains unsupported resolution semantics <{name}>: {artifact}")
    expected = {
        "modelVersion": "4.0.0",
        "groupId": group_id,
        "artifactId": artifact,
        "version": version,
    }
    for field, identity in expected.items():
        tag = f"{{{_POM_NAMESPACE}}}{field}"
        matches = [child for child in root if child.tag == tag]
        conflicting = [
            child for child in root
            if isinstance(child.tag, str) and child.tag.rsplit("}", 1)[-1] == field and child.tag != tag
        ]
        if len(matches) != 1 or conflicting or list(matches[0]) or (matches[0].text or "").strip() != identity:
            raise ValueError(f"Maven POM {field} does not match its publication identity: {artifact}")


def _module_owner(component: str, artifact: str) -> str:
    if artifact == "codex-agent-bom":
        return artifact
    return ROOT_ARTIFACTS[component]


def _verify_module(
    contents: bytes,
    group_id: str,
    version: str,
    component: str,
    artifact: str,
    primaries: dict[str, tuple[int, dict[str, str]]],
) -> None:
    module = _object(load_json_bytes(contents), f"Gradle module metadata for {artifact}")
    if set(module) != {"formatVersion", "component", "createdBy", "variants"}:
        raise ValueError(f"Gradle module metadata has the wrong top-level schema: {artifact}")
    if module.get("formatVersion") != "1.1":
        raise ValueError(f"Gradle module metadata format is unsupported: {artifact}")
    created_by = _object(module.get("createdBy"), f"Gradle module createdBy for {artifact}")
    gradle = _object(created_by.get("gradle"), f"Gradle module createdBy.gradle for {artifact}")
    if (set(created_by) != {"gradle"} or set(gradle) != {"version"} or
            not isinstance(gradle["version"], str) or not gradle["version"]):
        raise ValueError(f"Gradle module createdBy contains unsupported execution identity: {artifact}")
    owner = _module_owner(component, artifact)
    identity = _object(module.get("component"), f"Gradle module component for {artifact}")
    expected_identity: dict[str, object] = {
        "group": group_id,
        "module": owner,
        "version": version,
        "attributes": {"org.gradle.status": "release"},
    }
    if owner != artifact:
        expected_identity["url"] = f"../../{owner}/{version}/{owner}-{version}.module"
    if identity != expected_identity:
        raise ValueError(f"Gradle module component identity does not match its publication owner: {artifact}")

    variants = module.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ValueError(f"Gradle module metadata has no variants array: {artifact}")
    names: set[str] = set()
    referenced_files: set[str] = set()
    referenced_targets: set[str] = set()
    expected_targets = (
        COMPONENT_ARTIFACTS[component] - {artifact, "codex-agent-bom"}
        if artifact == ROOT_ARTIFACTS[component]
        else set()
    )
    referenceable = {
        name for name in primaries
        if not name.endswith((".module", ".pom", "-javadoc.jar", "-kotlin-tooling-metadata.json"))
    }
    for index, value in enumerate(variants):
        variant = _object(value, f"Gradle module variant {artifact}[{index}]")
        name = variant.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValueError(f"Gradle module variant names are missing or duplicate: {artifact}")
        names.add(name)
        files = variant.get("files", [])
        if not isinstance(files, list):
            raise ValueError(f"Gradle module variant files are malformed: {artifact}")
        variant_urls: set[str] = set()
        for file_index, file_value in enumerate(files):
            record = _object(file_value, f"Gradle module file {artifact}[{index}][{file_index}]")
            if set(record) != {"name", "url", "size", *CHECKSUMS.values()}:
                raise ValueError(f"Gradle module file record has the wrong schema: {artifact}")
            display_name = record["name"]
            url = record["url"]
            if (not isinstance(display_name, str) or not display_name or
                    PurePosixPath(display_name).name != display_name or "\\" in display_name or
                    not isinstance(url, str) or url not in referenceable or url in variant_urls):
                raise ValueError(f"Gradle module file reference is invalid or duplicate: {artifact}")
            variant_urls.add(url)
            referenced_files.add(url)
            size, digests = primaries[url]
            if type(record["size"]) is not int or record["size"] != size:
                raise ValueError(f"Gradle module file size does not match its primary: {artifact}/{url}")
            for algorithm in CHECKSUMS.values():
                if record[algorithm] != digests[algorithm]:
                    raise ValueError(f"Gradle module file digest does not match its primary: {artifact}/{url}")
        if files and artifact in _NATIVE_TARGET:
            attributes = _object(variant.get("attributes"), f"Gradle module attributes for {artifact}")
            if attributes.get("org.jetbrains.kotlin.native.target") != _NATIVE_TARGET[artifact]:
                raise ValueError(f"Gradle module native target does not match its publication: {artifact}")

        available = variant.get("available-at")
        if available is not None:
            target = _object(available, f"Gradle module target reference for {artifact}")
            target_module = target.get("module")
            if not isinstance(target_module, str) or target_module not in expected_targets:
                raise ValueError(f"Gradle module target reference is not registry-owned: {artifact}")
            expected_target = {
                "url": f"../../{target_module}/{version}/{target_module}-{version}.module",
                "group": group_id,
                "module": target_module,
                "version": version,
            }
            if target != expected_target:
                raise ValueError(f"Gradle module target reference has conflicting identity: {artifact}")
            referenced_targets.add(target_module)
    if referenced_files != referenceable:
        raise ValueError(f"Gradle module primary references are incomplete or unknown: {artifact}")
    if referenced_targets != expected_targets:
        raise ValueError(f"Gradle module target references are incomplete: {artifact}")


def verify_sdk_maven_repository(
    source: Path,
    group_id: str,
    version: str,
    component: str,
) -> None:
    suffixes = COMPONENT_PRIMARY_SUFFIXES.get(component)
    if suffixes is None:
        raise ValueError(f"unsupported SDK Maven component: {component}")
    if group_id != MAVEN_GROUPS[component]:
        raise ValueError(f"unexpected SDK Maven group: {group_id}")
    if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
        raise ValueError(f"invalid SDK Maven version: {version}")
    source = require_regular_directory(source, "SDK binary Maven repository")
    inventory = regular_file_inventory(source)
    actual = {record["relativePath"] for record in inventory}
    if any(PurePosixPath(path).name.startswith("maven-metadata.xml") for path in actual):
        raise ValueError("SDK binary Maven repository contains mutable discovery metadata")

    group_path = group_id.replace(".", "/")
    primary_paths = {
        f"{group_path}/{artifact}/{version}/{artifact}-{version}{suffix}"
        for artifact, artifact_suffixes in suffixes.items()
        for suffix in artifact_suffixes
    }
    expected = primary_paths | {
        primary + checksum_suffix
        for primary in primary_paths
        for checksum_suffix in CHECKSUMS
    }
    if actual != expected:
        raise ValueError(f"SDK binary Maven file inventory mismatch: {component}")

    group = source.joinpath(*group_path.split("/"))
    group_entries = list(group.iterdir()) if group.is_dir() and not group.is_symlink() else []
    if ({path.name for path in group_entries} != set(suffixes) or
            any(not path.is_dir() or path.is_symlink() for path in group_entries)):
        raise ValueError(f"SDK binary Maven artifact inventory mismatch: {component}")
    for artifact in suffixes:
        artifact_entries = list((group / artifact).iterdir())
        if (len(artifact_entries) != 1 or artifact_entries[0].name != version or
                not artifact_entries[0].is_dir() or artifact_entries[0].is_symlink()):
            raise ValueError(f"SDK binary Maven version inventory mismatch: {artifact}")

    identities: dict[str, tuple[int, dict[str, str]]] = {}
    metadata_contents: dict[str, bytes] = {}
    for relative in sorted(primary_paths):
        retain_contents = relative.endswith((".pom", ".module"))
        primary, size, digests = _file_identity(
            source.joinpath(*PurePosixPath(relative).parts), retain_contents=retain_contents,
        )
        if size == 0:
            raise ValueError(f"SDK binary Maven primary is empty: {relative}")
        identities[relative] = (size, digests)
        if primary is not None:
            metadata_contents[relative] = primary
        for suffix, algorithm in CHECKSUMS.items():
            checksum = read_regular_file_bytes(
                source.joinpath(*PurePosixPath(relative + suffix).parts),
                reject_symlink_parents=True,
            )
            if checksum != (digests[algorithm] + "\n").encode("ascii"):
                raise ValueError(f"SDK binary Maven checksum is noncanonical or mismatched: {relative}{suffix}")

    for artifact, artifact_suffixes in suffixes.items():
        prefix = f"{group_path}/{artifact}/{version}/{artifact}-{version}"
        artifact_primaries = {
            PurePosixPath(path).name: value
            for path, value in identities.items()
            if path.startswith(prefix)
        }
        pom_path = f"{prefix}.pom"
        module_path = f"{prefix}.module"
        _verify_pom(metadata_contents[pom_path], group_id, artifact, version)
        _verify_module(
            metadata_contents[module_path],
            group_id, version, component, artifact, artifact_primaries,
        )


def verify_packaged_sdk_maven_repository(
    source: Path,
    compatibility_file: Path,
    group_id: str,
    product_version: str,
    component: str,
) -> None:
    """Verify final Maven coordinates and every compatibility-bearing carrier."""
    carriers = COMPONENT_CARRIERS.get(component)
    if carriers is None:
        raise ValueError(f"unsupported SDK Maven component: {component}")
    compatibility_file = Path(compatibility_file)
    if compatibility_file.name != "sdk-compatibility.json":
        raise ValueError("SDK compatibility input has the wrong name")
    compatibility = read_regular_file_bytes(
        compatibility_file, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    declaration = validate_sdk_compatibility_bytes(compatibility)
    if declaration["sdkVersion"] != product_version:
        raise ValueError("SDK compatibility version does not match the Maven product version")

    source = Path(source)
    verify_sdk_maven_repository(source, group_id, product_version, component)
    group = source.joinpath(*group_id.split("."))
    for artifact, (kind, resource_path) in carriers.items():
        archive = group / artifact / product_version / f"{artifact}-{product_version}.{kind}"
        _verify_archive(archive, kind, resource_path, compatibility)


_APPLE_VERIFICATION_KEYS = {
    "validation_evidence_directory", "expected_sdk_compatibility", "expected_distribution_proof",
    "repository", "tooling_evidence", "tooling_public_key", "java_executable", "policy_revision",
    "required_trust_domain", "tooling_keyring", "tooling_keys_directory",
}
_APPLE_BINARY_VERIFICATION_KEYS = (_APPLE_VERIFICATION_KEYS - {
    "validation_evidence_directory", "expected_sdk_compatibility", "expected_distribution_proof",
}) | {"developer_directory"}
_APPLE_ORIGINAL_VERIFICATION_KEYS = (_APPLE_BINARY_VERIFICATION_KEYS - {"developer_directory"}) | {
    "evidence_directory", "execution_binding_file", "expected_binding_sha256", "expected_execution_files",
}


def _verify_sdk_maven_stage_inventory(stage: Path, receipt: dict[str, Any], phase: str) -> None:
    """Validate original stage identity and required evidence before reading it.

    This structural preflight alone grants no Maven or Apple semantic admission.
    """
    component = receipt["component"]
    if (receipt["product"] != "sdk" or receipt["phase"] != phase or
            component not in COMPONENT_CARRIERS or
            receipt["target"] not in phase_targets(PhaseId("sdk", component, phase))):
        raise ValueError(f"SDK Maven verification requires an exact Maven {phase} phase")
    manifest = verify_output_manifest_identity(
        stage, "sdk", component, phase, receipt["target"], receipt["productVersion"],
    )
    if manifest["outputs"] != receipt["outputs"]:
        raise ValueError("SDK Maven receipt and stage output inventories differ")
    evidence_name = "maven-primary-inventory.json" if phase == "binary" else "sdk-compatibility.json"
    evidence = [record for record in receipt["outputs"] if record["kind"] == "evidence"]
    if len(evidence) != 1 or evidence[0]["relativePath"] != f"outputs/evidence/{evidence_name}":
        raise ValueError(f"SDK Maven {phase} output kinds or paths are invalid")


def _verify_sdk_maven_stage(
    stage: Path, receipt: dict[str, Any], phase: str, *,
    apple_verification: dict[str, Any] | None = None, authenticated_compatibility: bytes | None = None,
    apple_binary_verification: dict[str, Any] | None = None, binary_stage: Path | None = None,
    apple_execution_capture_directory: Path | None = None,
    apple_original_verification: dict[str, Any] | None = None,
) -> None:
    _verify_sdk_maven_stage_inventory(stage, receipt, phase)
    component = receipt["component"]
    if apple_execution_capture_directory is not None and apple_binary_verification is None:
        raise ValueError("Apple execution capture requires binary package verification")
    apple_outputs = []
    if component == "sdk-ios" and phase == "binary":
        from .sdk_apple_framework import inspect_apple_frameworks

        framework_root = stage / "outputs/apple-binary"
        inventory = inspect_apple_frameworks({
            target: framework_root / target / "CodexAgent.framework"
            for target in ("ios-arm64", "ios-simulator-arm64")
        })
        files = sorted([
            {**record, "relativePath": f"{entry['target']}/CodexAgent.framework/{record['relativePath']}"}
            for entry in inventory["targets"] for record in entry["files"]
        ], key=lambda record: record["relativePath"])
        if files != regular_file_inventory(framework_root):
            raise ValueError("Apple binary inventory contains files outside the exact framework pair")
        apple_outputs = [{**record, "kind": "apple-binary",
                          "relativePath": f"outputs/apple-binary/{record['relativePath']}"}
                         for record in files]
        if [record for record in receipt["outputs"] if record["kind"] == "apple-binary"] != apple_outputs:
            raise ValueError("Apple binary files differ from exact receipt outputs")
    if sum(value is not None for value in (apple_verification, apple_binary_verification, apple_original_verification)) > 1:
        raise ValueError("Apple package verification modes are mutually exclusive")
    if any(value is not None for value in (apple_verification, apple_binary_verification, apple_original_verification)):
        options = (apple_original_verification if apple_original_verification is not None else
                   apple_verification if apple_verification is not None else apple_binary_verification)
        expected_keys = (_APPLE_ORIGINAL_VERIFICATION_KEYS if apple_original_verification is not None else
                         _APPLE_VERIFICATION_KEYS if apple_verification is not None else _APPLE_BINARY_VERIFICATION_KEYS)
        if ((receipt["product"], component, phase, receipt["target"]) != ("sdk", "sdk-ios", "package", "ios") or
                type(options) is not dict or set(options) != expected_keys):
            raise ValueError("Apple verification requires exact sdk-ios package identity and complete caller inputs")
        if authenticated_compatibility is None:
            raise ValueError("Apple verification requires authenticated SDK compatibility")
        expected_path = Path(apple_verification["expected_sdk_compatibility"]) if apple_verification is not None else None
        expected_bytes = (read_regular_file_bytes(expected_path, max_bytes=16 * 1024 * 1024,
                                                  reject_symlink_parents=True)
                          if expected_path is not None else authenticated_compatibility)
        if expected_bytes != authenticated_compatibility:
            raise ValueError("Apple caller compatibility differs from authenticated SDK compatibility")
        from .sdk_apple_content import verify_sdk_apple_package_content, verify_sdk_apple_binary_package_content

        # The fixed authenticated tooling gate, not a generic extra-output allowlist.
        with tempfile.TemporaryDirectory(prefix="sdk-apple-compatibility-") as temporary:
            captured_compatibility = Path(temporary).resolve() / "sdk-compatibility.json"
            captured_compatibility.write_bytes(expected_bytes)
            if apple_binary_verification is not None or apple_original_verification is not None:
                if binary_stage is None:
                    raise ValueError("Apple binary package verification requires its original binary predecessor")
                gate = verify_sdk_apple_binary_package_content
                if apple_original_verification is not None:
                    from .sdk_apple_package_replay import verify_sdk_apple_original_package_content
                    gate = verify_sdk_apple_original_package_content
                inventory = gate(
                    product_directory=stage / "outputs/apple", sdk_version=receipt["productVersion"],
                    binary_frameworks=binary_stage / "outputs/apple-binary",
                    source_revision=receipt["producer"]["commit"], expected_sdk_compatibility=captured_compatibility,
                    **({"execution_capture_directory": apple_execution_capture_directory}
                       if apple_execution_capture_directory is not None else {}),
                    **options,
                )
            else:
                inventory = verify_sdk_apple_package_content(
                    product_directory=stage / "outputs/apple", sdk_version=receipt["productVersion"],
                    **{**apple_verification, "expected_sdk_compatibility": captured_compatibility},
                )
            if read_regular_file_bytes(captured_compatibility, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != expected_bytes:
                raise ValueError("Captured Apple compatibility changed during verification")
        version = receipt["productVersion"]
        expected_names = {f"CodexAgentPackage-{version}.zip", f"CodexAgent-{version}.xcframework.zip",
                          f"CodexAgent-{version}.xcframework.zip.sha256"}
        if (len(inventory) != 3 or {record["relativePath"] for record in inventory} != expected_names or
                inventory != regular_file_inventory(stage / "outputs/apple")):
            raise ValueError("Apple gate inventory differs from exact original SDK package files")
        apple_outputs = [{**record, "kind": "apple", "relativePath": f"outputs/apple/{record['relativePath']}"}
                         for record in inventory]
        if [record for record in receipt["outputs"] if record["kind"] == "apple"] != apple_outputs:
            raise ValueError("Apple package files differ from exact receipt outputs")
        if expected_path is not None and read_regular_file_bytes(expected_path, max_bytes=16 * 1024 * 1024,
                                   reject_symlink_parents=True) != expected_bytes:
            raise ValueError("Apple caller compatibility changed during verification")
    evidence = [record for record in receipt["outputs"] if record["kind"] == "evidence"]
    if any(record["kind"] != "maven" or not record["relativePath"].startswith("outputs/maven/")
           for record in receipt["outputs"] if record not in evidence and record not in apple_outputs):
        raise ValueError(f"SDK Maven {phase} output kinds or paths are invalid")


def verify_packaged_sdk_maven_phase(
    stage_root: Path, receipt_path: Path, compatibility_request: Path,
    *, apple_verification: dict[str, Any] | None = None,
    apple_binary_verification: dict[str, Any] | None = None,
    binary_stage_root: Path | None = None, binary_receipt_path: Path | None = None,
    apple_execution_capture_directory: Path | None = None,
    apple_original_verification: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Verify final-stage semantics; not upstream execution or release admission.

    Return the original receipt and its unchanged canonical bytes. Authenticating
    the selected binary predecessor and planned upstream closure remains the
    caller's responsibility; a self-consistent receipt alone cannot prove them.
    Apple outputs require either complete legacy caller verification or the
    original binary predecessor plus the strict replay policy. Omitting both
    preserves the strict Maven-only stage contract.
    """
    # The compatibility producer imports Maven-independent archive authorities.
    from .sdk_compatibility import load_sdk_compatibility_request, produce_sdk_compatibility

    if sum(value is not None for value in (apple_verification, apple_binary_verification, apple_original_verification)) > 1:
        raise ValueError("Apple package verification modes are mutually exclusive")
    if apple_binary_verification is not None or apple_original_verification is not None:
        if apple_verification is not None or binary_stage_root is None or binary_receipt_path is None:
            raise ValueError("Apple binary verification requires only its complete original binary inputs")
    elif binary_stage_root is not None or binary_receipt_path is not None:
        raise ValueError("Unexpected Apple binary inputs without binary verification")
    if apple_execution_capture_directory is not None:
        if apple_binary_verification is None:
            raise ValueError("Apple execution capture requires binary package verification")
        from .sdk_package import _require_capability_output_separate
        _require_capability_output_separate(Path(apple_execution_capture_directory), tuple(map(Path, (
            stage_root, receipt_path, compatibility_request, binary_stage_root, binary_receipt_path,
        ))))

    stage_root, receipt_path, compatibility_request = map(
        Path, (stage_root, receipt_path, compatibility_request),
    )
    receipt_bytes = read_regular_file_bytes(
        receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    request_bytes = read_regular_file_bytes(
        compatibility_request, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    original_inventory = regular_file_inventory(stage_root)
    with tempfile.TemporaryDirectory(prefix="sdk-maven-phase-verification-") as temporary:
        private = Path(temporary).resolve()
        stage = private / "stage"
        snapshot_regular_tree(stage_root, stage)
        if regular_file_inventory(stage) != original_inventory:
            raise ValueError("SDK Maven stage changed during snapshot")
        (private / "phase-receipt.json").write_bytes(receipt_bytes)
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        component = receipt["component"]
        _verify_sdk_maven_stage_inventory(stage, receipt, "package")
        evidence_path = "outputs/evidence/sdk-compatibility.json"

        private_request = private / "sdk-compatibility-request.json"
        private_request.write_bytes(request_bytes)
        arguments = load_sdk_compatibility_request(
            private_request, request_directory=compatibility_request.parent,
        )
        authenticated = private / "sdk-compatibility.json"
        declaration = produce_sdk_compatibility(output=authenticated, **arguments)
        if declaration["sdkVersion"] != receipt["productVersion"]:
            raise ValueError("Authenticated SDK compatibility version differs from package receipt")
        if authenticated.read_bytes() != (stage / evidence_path).read_bytes():
            raise ValueError("SDK Maven evidence differs from authenticated compatibility")
        if apple_binary_verification is not None or apple_original_verification is not None:
            verify_sdk_maven_binary_predecessor(
                binary_stage_root, binary_receipt_path, stage, private / "phase-receipt.json", authenticated,
                apple_binary_verification=apple_binary_verification,
                apple_original_verification=apple_original_verification,
                **({"apple_execution_capture_directory": apple_execution_capture_directory}
                   if apple_execution_capture_directory is not None else {}),
            )
        else:
            _verify_sdk_maven_stage(stage, receipt, "package", apple_verification=apple_verification,
                                   authenticated_compatibility=authenticated.read_bytes())
        verify_packaged_sdk_maven_repository(
            stage / "outputs/maven", authenticated,
            MAVEN_GROUPS[component], receipt["productVersion"], component,
        )
        if (regular_file_inventory(stage_root) != original_inventory or
                regular_file_inventory(stage) != original_inventory or
                read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != receipt_bytes or
                read_regular_file_bytes(compatibility_request, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != request_bytes):
            raise ValueError("SDK Maven verification inputs changed during verification")
        return receipt, receipt_bytes


def verify_sdk_maven_binary_content(stage: Path, identity: dict[str, Any]) -> None:
    """Verify existing binary content rules, not producer or receipt authority."""
    stage = Path(stage)
    original = regular_file_inventory(stage)
    identity_bytes = canonical_json_bytes(identity)
    _verify_sdk_maven_stage(stage, identity, "binary")
    component, version = identity["component"], identity["productVersion"]
    raw_maven = stage / "outputs/maven"
    verify_sdk_maven_repository(raw_maven, MAVEN_GROUPS[component], version, component)
    # Existing Gradle primary-inventory authority; preserve its field/format rules.
    primaries = [record for record in regular_file_inventory(raw_maven)
                 if not any(record["relativePath"].endswith(suffix) for suffix in CHECKSUMS)]
    expected_evidence = {
        "schemaVersion": 1, "product": "sdk", "component": component,
        "groupId": MAVEN_GROUPS[component], "sdkVersion": version,
        "artifactIds": sorted(COMPONENT_ARTIFACTS[component]),
        "primaryArtifactCount": len(primaries),
        "files": [{"path": record["relativePath"], "bytes": record["bytes"],
                   "sha256": record["sha256"].removeprefix("sha256:")} for record in primaries],
    }
    evidence = load_json_bytes(read_regular_file_bytes(
        stage / "outputs/evidence/maven-primary-inventory.json",
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
    if canonical_json_bytes(evidence) != canonical_json_bytes(expected_evidence):
        raise ValueError("SDK Maven binary primary inventory differs from its exact artifacts")
    if regular_file_inventory(stage) != original or canonical_json_bytes(identity) != identity_bytes:
        raise ValueError("SDK Maven binary content changed during verification")


def verify_sdk_maven_binary_predecessor(
    binary_stage_root: Path,
    binary_receipt_path: Path,
    package_stage_root: Path,
    package_receipt_path: Path,
    compatibility_file: Path,
    *, apple_verification: dict[str, Any] | None = None,
    apple_binary_verification: dict[str, Any] | None = None,
    apple_execution_capture_directory: Path | None = None,
    apple_original_verification: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    """Prove exact Maven transformation plus optional imported Apple closure.

    The caller authenticates compatibility and planned upstream inputs. Replay
    uses the existing Python archive/metadata transformation in private storage.
    Optional binary Apple replay additionally uses authenticated matching-host
    assembly/packaging tools, never compilation or XCTest. Neither mode rewrites
    original evidence or substitutes for host execution/provenance admission.
    """
    stages = {"binary": Path(binary_stage_root), "package": Path(package_stage_root)}
    receipt_paths = {"binary": Path(binary_receipt_path), "package": Path(package_receipt_path)}
    compatibility_file = Path(compatibility_file)
    if apple_execution_capture_directory is not None:
        if apple_binary_verification is None:
            raise ValueError("Apple execution capture requires binary package verification")
        from .sdk_package import _require_capability_output_separate
        _require_capability_output_separate(Path(apple_execution_capture_directory), (
            *stages.values(), *receipt_paths.values(), compatibility_file,
        ))
    if compatibility_file.name != "sdk-compatibility.json":
        raise ValueError("SDK compatibility input has the wrong name")
    receipt_bytes = {
        phase: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        for phase, path in receipt_paths.items()
    }
    compatibility = read_regular_file_bytes(
        compatibility_file, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    original_inventories = {phase: regular_file_inventory(path) for phase, path in stages.items()}
    with tempfile.TemporaryDirectory(prefix="sdk-maven-predecessor-verification-") as temporary:
        private = Path(temporary).resolve()
        receipts = {}
        for phase, source in stages.items():
            snapshot_regular_tree(source, private / phase)
            if regular_file_inventory(private / phase) != original_inventories[phase]:
                raise ValueError(f"SDK Maven {phase} stage changed during snapshot")
            receipts[phase] = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes[phase]))
            if phase == "binary":
                verify_sdk_maven_binary_content(private / phase, receipts[phase])
        binary, package = receipts["binary"], receipts["package"]
        if any(binary[field] != package[field] for field in ("component", "target", "productVersion")):
            raise ValueError("SDK Maven binary predecessor and package identities differ")
        component, version = binary["component"], binary["productVersion"]
        _verify_sdk_maven_stage(private / "package", package, "package",
                               apple_verification=apple_verification, authenticated_compatibility=compatibility,
                               apple_binary_verification=apple_binary_verification, binary_stage=private / "binary",
                               apple_original_verification=apple_original_verification,
                               apple_execution_capture_directory=apple_execution_capture_directory)
        raw_maven = private / "binary/outputs/maven"
        private_compatibility = private / "sdk-compatibility.json"
        private_compatibility.write_bytes(compatibility)
        if (private / "package/outputs/evidence/sdk-compatibility.json").read_bytes() != compatibility:
            raise ValueError("SDK Maven package evidence differs from supplied compatibility")
        replay = private / "replayed-maven"
        package_sdk_maven(raw_maven, replay, private_compatibility, MAVEN_GROUPS[component], version, component)
        if regular_file_inventory(replay) != regular_file_inventory(private / "package/outputs/maven"):
            raise ValueError("SDK Maven package differs from its exact binary predecessor transformation")
        if (any(regular_file_inventory(path) != original_inventories[phase] for phase, path in stages.items()) or
                any(regular_file_inventory(private / phase) != original_inventories[phase] for phase in stages) or
                any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True) != receipt_bytes[phase]
                    for phase, path in receipt_paths.items()) or
                read_regular_file_bytes(compatibility_file, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != compatibility):
            raise ValueError("SDK Maven predecessor inputs changed during verification")
        return binary, receipt_bytes["binary"]


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
                if record.get("url") != archive_name:
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
        value = load_json_bytes(read_regular_file_bytes(module, reject_symlink_parents=True))
        referenced = update(value, archive_name, contents)
        module.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if referenced == 0:
            raise ValueError(f"packaged SDK artifact is absent from its exact Gradle module metadata: {archive_name}")


def _refresh_checksums(repository: Path) -> None:
    primaries: dict[Path, dict[str, str]] = {}
    for sidecar in sorted(path for path in repository.rglob("*") if path.is_file() and
                          any(path.name.endswith(suffix) for suffix in CHECKSUMS)):
        suffix, algorithm = next((suffix, algorithm) for suffix, algorithm in CHECKSUMS.items()
                                 if sidecar.name.endswith(suffix))
        primary = sidecar.with_name(sidecar.name.removesuffix(suffix))
        if primary not in primaries:
            if not primary.is_file() or primary.is_symlink():
                raise ValueError(f"Maven checksum has no regular primary: {sidecar}")
            _, _, primaries[primary] = _file_identity(primary, retain_contents=False)
        sidecar.write_text(primaries[primary][algorithm] + "\n", encoding="ascii")


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
    declaration = validate_sdk_compatibility_bytes(compatibility)
    if declaration["sdkVersion"] != version:
        raise ValueError("SDK compatibility version does not match the Maven package version")
    if compatibility_file.name != "sdk-compatibility.json":
        raise ValueError("SDK compatibility input has the wrong name")
    verify_sdk_maven_repository(source, group_id, version, component)
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
            changed[archive.relative_to(output).as_posix()] = archive.read_bytes()
        _update_module_metadata(output, changed)
        _refresh_checksums(output)
        verify_packaged_sdk_maven_repository(
            output, compatibility_file, group_id, version, component,
        )
    except Exception:
        shutil.rmtree(output)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compatibility", type=Path)
    parser.add_argument("--group-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--component", choices=tuple(COMPONENT_CARRIERS), required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        if args.output is not None or args.compatibility is not None:
            parser.error("--output and --compatibility are not accepted with --verify-only")
        verify_sdk_maven_repository(args.source, args.group_id, args.version, args.component)
        return 0
    if args.output is None or args.compatibility is None:
        parser.error("--output and --compatibility are required for packaging")
    package_sdk_maven(
        args.source, args.output, args.compatibility,
        args.group_id, args.version, args.component,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
