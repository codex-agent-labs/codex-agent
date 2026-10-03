"""Bind retained Apple toolchain observations to independently selected pins.

No tool is invoked. This narrow replay does not authenticate the caller's pins,
producer, source or host, and does not replace the full compiler evidence gate.
"""

from pathlib import Path
import re

from .inventory import (
    file_inventory, load_json_bytes, read_regular_file_bytes, regular_file_inventory,
    require_exact_keys, require_integer, require_object, require_string,
)
from .sdk_apple_device_evidence import _original_directory
from .sdk_apple_package_source import _BUILD, _NUMERIC_VERSION


_COMMANDS = {
    "xcode": ["/usr/bin/xcodebuild", "-version"],
    "swift": ["/usr/bin/xcrun", "swift", "--version"],
    "clang": ["/usr/bin/xcrun", "clang", "--version"],
}
_REPORT = "reports/compiler-evidence.json"


def _read(path: Path) -> bytes:
    return read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)


def _text(path: Path) -> str:
    try:
        return _read(path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("Apple toolchain output is not strict UTF-8") from error


def _versions(xcode: str, swift: str, expected: dict[str, str]) -> None:
    # Same version/banner interpretation as verifyAppleToolchainOutput. Reject
    # contradictory duplicate Xcode lines as well as multiple Swift banners.
    lines = re.split(r"\r\n|\n|\r", xcode)
    if ([line for line in lines if line.startswith("Xcode ")] != ["Xcode " + expected["xcodeVersion"]]
            or [line for line in lines if line.startswith("Build version ")] !=
            ["Build version " + expected["xcodeBuild"]]):
        raise ValueError("Apple toolchain Xcode version/build differs from caller pins")
    banners = [line for line in re.split(r"\r\n|\n|\r", swift) if line.startswith("Apple Swift version ")]
    match = re.fullmatch(r"Apple Swift version ([0-9]+(?:\.[0-9]+)*)(?:\s+.*)?", banners[0]) \
        if len(banners) == 1 else None
    if match is None or match.group(1) != expected["swiftVersion"]:
        raise ValueError("Apple toolchain Swift version differs from caller pins")


def verify_apple_toolchain_evidence(
    evidence_root: Path, *, expected_toolchain: dict[str, str], original_working_directory: str,
) -> dict[str, list]:
    """Return unchanged original inventories after fixed toolchain replay.

    expected_toolchain must come from the immutable source capture's pinned
    xcodeVersion/xcodeBuild/swiftVersion, never from the compiler report itself.
    The original working directory is caller-bound producer data, not a path on
    this machine. Successful captureReleaseProcess records ExecSpec's actual
    directory even when its optional workingDirectory argument was omitted.
    Retained task text has no separate execution record; compiler raw records
    provide the fixed-command checks. Neither establishes hosted execution.
    """
    expected = dict(require_exact_keys(expected_toolchain,
        {"xcodeVersion", "xcodeBuild", "swiftVersion"}, "Expected Apple toolchain"))
    for field, pattern in (("xcodeVersion", _NUMERIC_VERSION), ("xcodeBuild", _BUILD),
                           ("swiftVersion", _NUMERIC_VERSION)):
        if pattern.fullmatch(require_string(expected[field], field)) is None:
            raise ValueError(f"Invalid expected Apple toolchain {field}")
    working_directory = str(_original_directory(original_working_directory, "Original compiler working directory"))
    root = Path(evidence_root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Apple toolchain evidence root must be absolute, normalized and non-symbolic")
    directories = {name: root / name for name in ("toolchain", "compiler-raw/toolchain")}
    before = {name: regular_file_inventory(path, allow_empty=name == "compiler-raw/toolchain")
              for name, path in directories.items()}
    before["compiler-report"] = file_inventory(root, [_REPORT])
    if {row["relativePath"] for row in before["toolchain"]} != {"xcode.txt", "swift.txt"}:
        raise ValueError("Retained Apple toolchain inventory changed")
    if {row["relativePath"] for row in before["compiler-raw/toolchain"]} != {
            f"{tool}/{file}" for tool in _COMMANDS for file in ("execution.json", "stdout.bin", "stderr.bin")}:
        raise ValueError("Original compiler toolchain inventory changed")

    report = require_object(load_json_bytes(_read(root / _REPORT)), "Compiler report")
    toolchain = require_exact_keys(report.get("toolchain"), {*expected, "clangVersion"}, "Compiler toolchain")
    if any(toolchain[field] != value for field, value in expected.items()):
        raise ValueError("Compiler report toolchain differs from caller pins")
    outputs = {}
    for tool, command in _COMMANDS.items():
        directory = directories["compiler-raw/toolchain"] / tool
        execution = require_exact_keys(load_json_bytes(_read(directory / "execution.json")),
            {"schemaVersion", "command", "workingDirectory", "environment", "exitCode"}, "Toolchain execution")
        if (require_integer(execution["schemaVersion"], "Toolchain execution schema", 1) != 1
                or require_integer(execution["exitCode"], "Toolchain execution exit code") != 0
                or execution["command"] != command
                or execution["workingDirectory"] != working_directory
                or execution["environment"] != {"LC_ALL": "C", "LANG": "C"}):
            raise ValueError("Original toolchain execution is not the exact successful caller-bound command")
        outputs[tool] = _text(directory / "stdout.bin")
    _versions(outputs["xcode"], outputs["swift"], expected)
    _versions(_text(directories["toolchain"] / "xcode.txt"),
              _text(directories["toolchain"] / "swift.txt"), expected)
    clang = re.split(r"\r\n|\n|\r", outputs["clang"])[0]
    if not clang.startswith("Apple clang version ") or clang != toolchain["clangVersion"]:
        raise ValueError("Compiler report Clang identity differs from raw output")

    if (any(regular_file_inventory(path, allow_empty=name == "compiler-raw/toolchain") != before[name]
            for name, path in directories.items()) or file_inventory(root, [_REPORT]) != before["compiler-report"]):
        raise ValueError("Original Apple toolchain evidence changed during replay")
    return before
