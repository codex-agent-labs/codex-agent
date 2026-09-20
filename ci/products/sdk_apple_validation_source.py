"""Capture fixed validation consumer sources; the caller authenticates the Git revision."""

from pathlib import Path

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
