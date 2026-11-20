"""Capture original native source bytes; do not infer proof or host authority."""

from pathlib import Path

from .sdk_apple_package_source import _capture_apple_sources


_NATIVE = "codex-agent-runtime-ios/native"
_SINGLE_FILES = (
    f"{_NATIVE}/patches/0001-uninitialized-in-process-host.patch",
    f"{_NATIVE}/patches/0002-locked-ios-bridge.patch",
    f"{_NATIVE}/patches/0003-pinned-ios-sqlite.patch",
    f"{_NATIVE}/sqlite/0001-ios-filesystem-probes.patch",
    f"{_NATIVE}/include/codex_agent_ios.h",
    f"{_NATIVE}/provenance.json",
)
_SOURCE_TREES = (f"{_NATIVE}/bridge",)


def capture_apple_native_sources(repository: Path, revision: str, output: Path) -> dict[str, str]:
    """Preserve the exact native-input allowlist and return existing Apple pins.

    Paths remain repository-relative for the existing Apple native-input digest.
    The caller authenticates revision selection, including compatibility of
    mixed original producers. Compiler-setting/provenance validation and native
    execution admission remain separate; no digest or proof is manufactured.
    """
    return _capture_apple_sources(repository, revision, output, _SINGLE_FILES, _SOURCE_TREES)
