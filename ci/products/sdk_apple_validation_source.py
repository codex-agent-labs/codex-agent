"""Capture fixed validation consumer sources; the caller authenticates the Git revision."""

from pathlib import Path
import tempfile

from .inventory import regular_file_inventory
from .sdk_apple_package_source import _capture_apple_sources


_CONSUMERS = (
    "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureSwiftConsumer.swift",
    "codex-agent-runtime-ios/apple/CompilerEvidence/CodexFailureObjectiveCConsumer.m",
)
_TEST_APPLICATION = ("codex-agent-runtime-ios/apple/TestApp",)


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
