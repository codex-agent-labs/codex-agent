"""Capture fixed validation consumer sources; the caller authenticates the Git revision."""

from pathlib import Path
import re
import tempfile

from .inventory import git_regular_blob_bytes, regular_file_inventory
from .sdk_apple_package_source import _capture_apple_sources, _immutable_tree


_CONSUMERS = (
    "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
    "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
)
_TEST_APPLICATION = ("codex-agent-runtime-ios/apple/TestApp",)
_SIMULATOR_POLICY = "gradle/build-logic/src/main/kotlin/IosAppleDistributionTasks.kt"
_RUNTIME_NAME = re.compile(r"iOS (?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))+")
_DEVICE_TYPE = re.compile(
    r"com\.apple\.CoreSimulator\.SimDeviceType\.[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*",
)


def read_apple_validation_simulator_policy(repository: Path, revision: str) -> dict[str, str]:
    """Read fixed simulator selectors from a caller-authenticated immutable Git object."""
    repository = Path(repository).resolve(strict=True)
    tree = _immutable_tree(repository, revision)
    raw = git_regular_blob_bytes(repository, tree, _SIMULATOR_POLICY, max_bytes=1024 * 1024)
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Apple validation simulator policy is not UTF-8") from error
    declarations = {
        "runtimeName": ("runtimeName", _RUNTIME_NAME),
        "deviceTypeIdentifier": ("deviceTypeIdentifier", _DEVICE_TYPE),
    }
    result = {}
    for key, (name, pattern) in declarations.items():
        occurrences = re.findall(rf'\b{re.escape(name)}\s*\.\s*set\s*\(', source)
        matches = re.findall(rf'^\s*{name}\.set\("([^"\r\n]+)"\)\s*$', source, re.MULTILINE)
        if len(occurrences) != 1 or len(matches) != 1 or pattern.fullmatch(matches[0]) is None:
            raise ValueError(
                f"Apple validation {name} declaration is missing, duplicated, or invalid",
            )
        result[key] = matches[0]
    return result


def capture_apple_validation_sources(repository: Path, revision: str, output: Path) -> dict[str, str]:
    """Preserve original consumer bytes/modes and return immutable toolchain expectations.

    Package sources, tests, declarations and provenance are not reconstructed or
    emitted here. This capture grants no source, signature or execution authority.
    """
    return _capture_apple_sources(repository, revision, output, _CONSUMERS, _TEST_APPLICATION)


def verify_apple_validation_sources(repository: Path, revision: str, evidence_root: Path) -> dict:
    """Bind retained consumer bytes to an explicit caller-authenticated Git revision.

    Only consumer/ and device-test-application/ are examined. Other retained raw
    evidence, including empty streams, is neither interpreted nor rewritten.
    Returned inventories and Git-pinned toolchain expectations do not establish
    receipt, execution, host or revision authority. The caller owns the broader
    immutable evidence lifetime.
    """
    root = Path(evidence_root)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise ValueError("Apple validation evidence root must be absolute, normalized and non-symbolic")
    retained = {
        "consumerInventory": root / "consumer",
        "testApplicationInventory": root / "device-test-application",
    }
    before = {name: regular_file_inventory(path) for name, path in retained.items()}
    with tempfile.TemporaryDirectory(prefix="sdk-apple-validation-source-") as temporary:
        captured = Path(temporary).resolve() / "source"
        expectations = capture_apple_validation_sources(repository, revision, captured)
        expected = {
            "consumerInventory": regular_file_inventory(captured / Path(_CONSUMERS[0]).parent),
            "testApplicationInventory": regular_file_inventory(captured / _TEST_APPLICATION[0]),
        }
        if before != expected:
            raise ValueError("Retained Apple validation sources differ from the selected immutable Git sources")
        if root.resolve(strict=True) != root or any(
            regular_file_inventory(path) != before[name] for name, path in retained.items()
        ):
            raise ValueError("Retained Apple validation sources changed during verification")
    return {**expected, "toolchain": expectations}
