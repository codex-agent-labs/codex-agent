"""Bind a retained successful XCTest destination to its ready simulator record."""

from pathlib import Path
import re

from .inventory import (
    file_inventory, load_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_array, require_boolean, require_exact_keys, require_integer, require_object, require_string,
)


_REPORT = "reports/simulator-devices.json"
_MARKER = "successful-attempt.json"
_DESTINATION = "platform=iOS Simulator,id="


def _read(path: Path):
    return load_json_bytes(read_regular_file_bytes(
        path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    ))


def verify_apple_simulator_evidence(
    evidence_root: Path, *, expected_runtime_identifier: str, expected_device_type_identifier: str,
) -> dict[str, list]:
    """Return unchanged evidence inventories, not simulator or host admission.

    Caller pins must be independently authenticated. The producer retains its
    final ready-device listing, but not runtime-name mapping, boot commands or
    disappeared-device retry observations. These cannot be replayed here. The
    existing full XCTest gate still owns complete command/cwd/environment,
    previous attempts and test-result verification.
    """
    for value, prefix in ((expected_runtime_identifier, "com.apple.CoreSimulator.SimRuntime."),
                          (expected_device_type_identifier, "com.apple.CoreSimulator.SimDeviceType.")):
        value = require_string(value, "Expected simulator identifier")
        if not value.startswith(prefix) or re.fullmatch(r"[A-Za-z0-9.-]+", value[len(prefix):]) is None:
            raise ValueError("Expected simulator identifier is invalid")
    root = Path(evidence_root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Simulator evidence root must be absolute, normalized and non-symbolic")
    raw = root / "xctest-raw"
    before = {"simulatorReport": file_inventory(root, [_REPORT]),
              "xctestRaw": regular_file_inventory(raw, allow_empty=True)}
    marker = require_exact_keys(_read(raw / _MARKER), {"schemaVersion", "attempt"}, "XCTest successful attempt")
    attempt = require_integer(marker["attempt"], "XCTest attempt")
    if require_integer(marker["schemaVersion"], "XCTest marker schema", 1) != 1 or attempt not in (0, 1):
        raise ValueError("XCTest successful attempt is invalid")
    execution = require_exact_keys(_read(raw / f"attempt-{attempt}/xcodebuild/execution.json"),
        {"schemaVersion", "command", "workingDirectory", "environment", "exitCode"}, "XCTest execution")
    command = [require_string(value, "XCTest command argument")
               for value in require_array(execution["command"], "XCTest command")]
    if (require_integer(execution["schemaVersion"], "XCTest execution schema", 1) != 1
            or require_integer(execution["exitCode"], "XCTest exit code") != 0
            or not command or command[0] != "xcodebuild" or command.count("-destination") != 1):
        raise ValueError("XCTest requires one successful xcodebuild destination")
    index = command.index("-destination") + 1
    if index == len(command) or not command[index].startswith(_DESTINATION):
        raise ValueError("XCTest simulator destination is invalid")
    udid = command[index][len(_DESTINATION):]
    if re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", udid) is None:
        raise ValueError("XCTest simulator destination must name an exact UDID")

    # simctl has OS-version-dependent optional fields; validate required fields
    # without imposing an invented exact schema on Apple's device listing.
    report = require_object(_read(root / _REPORT), "Simulator report")
    runtimes = require_object(report.get("devices"), "Simulator devices")
    seen = set()
    selected = None
    for runtime, devices in runtimes.items():
        require_string(runtime, "Simulator runtime")
        for value in require_array(devices, "Simulator runtime devices"):
            device = require_object(value, "Simulator device")
            identifier = require_string(device.get("udid"), "Simulator device UDID")
            if identifier.lower() in seen:
                raise ValueError("Simulator listing contains a duplicate UDID")
            seen.add(identifier.lower())
            if identifier == udid:
                if runtime != expected_runtime_identifier:
                    raise ValueError("XCTest simulator belongs to a different runtime")
                selected = device
    if selected is None:
        raise ValueError("XCTest destination is absent from the retained simulator listing")
    if (not require_boolean(selected.get("isAvailable"), "Selected simulator availability")
            or require_string(selected.get("state"), "Selected simulator state") != "Booted"
            or require_string(selected.get("deviceTypeIdentifier"), "Selected simulator type") !=
            expected_device_type_identifier):
        raise ValueError("Selected simulator is not the available Booted caller-pinned device type")
    if (file_inventory(root, [_REPORT]) != before["simulatorReport"]
            or regular_file_inventory(raw, allow_empty=True) != before["xctestRaw"]):
        raise ValueError("Simulator evidence changed during verification")
    return before
