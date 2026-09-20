"""Replay the fixed device archive trace and its independently bound inputs."""

from pathlib import Path, PurePosixPath

from .inventory import (
    load_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_sorted_unique_records,
    require_string, validate_file_record,
)


def _original_directory(value, label):
    value = require_string(value, label)
    path = PurePosixPath(value)
    if (not path.is_absolute() or str(path) != value or ".." in path.parts
            or value.startswith("//") or "\\" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError(f"{label} must be an exact absolute original POSIX path")
    return path


def _expected_inventory(value, label):
    records = require_sorted_unique_records(value, label)
    if not records:
        raise ValueError(f"{label} must be nonempty")
    return [dict(validate_file_record(record, label, with_kind=False)) for record in records]


def verify_apple_device_evidence(
    evidence_root: Path, *, original_work_directory: str,
    original_test_application_directory: str, developer_directory: str,
    expected_test_application_inventory: list, expected_package_inventory: list,
) -> dict[str, list]:
    """Return original inventories only after exact trace/input replay.

    Original path strings describe the authenticated producer, not this machine.
    Expected inventories must come from independently authenticated inputs. The
    archive check matches the producer's nonempty regular-file requirement; it
    does not inspect Mach-O content or establish source, Contract or host trust.
    Returned raw inventories are external evidence, not deterministic products.
    """
    work = _original_directory(original_work_directory, "Original device work directory")
    application = _original_directory(original_test_application_directory, "Original test application")
    developer = _original_directory(developer_directory, "Original Developer directory")
    if application.name != "CodexAgentTestApp":
        raise ValueError("Original device test application must use the fixed sibling layout")
    for original in (application, application.parent / "CodexAgentPackage", developer):
        if work == original or work in original.parents or original in work.parents:
            raise ValueError("Original device work directory overlaps an input")
    expected_application = _expected_inventory(expected_test_application_inventory, "Expected test application")
    expected_package = _expected_inventory(expected_package_inventory, "Expected package")
    root = Path(evidence_root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Device evidence root must be absolute, normalized and non-symbolic")
    directories = {name: root / name for name in (
        "device-raw", "device-archive", "device-test-application", "device-package",
    )}
    before = {name: regular_file_inventory(path, allow_empty=name == "device-raw")
              for name, path in directories.items()}
    if {record["relativePath"] for record in before["device-raw"]} != {
            "xcodebuild/execution.json", "xcodebuild/stdout.bin", "xcodebuild/stderr.bin"}:
        raise ValueError("Device raw evidence must contain the exact process triplet")
    if (before["device-test-application"] != expected_application
            or before["device-package"] != expected_package):
        raise ValueError("Retained device inputs differ from independently authenticated inventories")
    if ("CodexAgentTestApp.xcodeproj/project.pbxproj" not in
            {record["relativePath"] for record in expected_application}
            or "Package.swift" not in {record["relativePath"] for record in expected_package}
            or not before["device-archive"]):
        raise ValueError("Device archive or required consumer input is missing")

    execution = require_exact_keys(load_json_bytes(read_regular_file_bytes(
        directories["device-raw"] / "xcodebuild/execution.json",
        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )), {"schemaVersion", "command", "workingDirectory", "environment", "exitCode"}, "Device execution")
    command = [
        "/usr/bin/xcodebuild", "-project", "CodexAgentTestApp.xcodeproj",
        "-scheme", "CodexAgentTestApp", "-configuration", "Release",
        "-destination", "generic/platform=iOS", "-derivedDataPath", str(work / "derived-data"),
        "-archivePath", str(work / "CodexAgentTestApp.xcarchive"),
        "ARCHS=arm64", "CODE_SIGNING_ALLOWED=NO", "SKIP_INSTALL=NO", "clean", "archive",
    ]
    if (require_integer(execution["schemaVersion"], "Device execution schema", 1) != 1
            or require_integer(execution["exitCode"], "Device execution exit code") != 0
            or execution["command"] != command
            or execution["workingDirectory"] != str(application)
            or execution["environment"] != {"LC_ALL": "C", "LANG": "C", "DEVELOPER_DIR": str(developer)}):
        raise ValueError("Device execution differs from its exact successful caller-bound command")
    if any(regular_file_inventory(path, allow_empty=name == "device-raw") != before[name]
           for name, path in directories.items()):
        raise ValueError("Device evidence changed during replay")
    return before
