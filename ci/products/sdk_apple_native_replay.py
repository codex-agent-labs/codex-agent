"""Replay original Apple native content without granting producer or host authority."""

from pathlib import Path
import tempfile
from typing import Any

from .inventory import require_exact_keys
from .receipt import validate_producer
from .sdk_apple_content import _input_inventory, _verify_sdk_apple_with_tooling
from .sdk_apple_native_source import capture_apple_native_sources


_LANES = {"ios-native-tests", "ios-rust-device", "ios-rust-simulator"}
_EVIDENCE_FILES = {
    "native-tests-proof.json", "codex-agent-ios-arm64.a",
    "codex-agent-ios-arm64-proof.json", "codex-agent-ios-simulator-arm64.a",
    "codex-agent-ios-simulator-arm64-proof.json",
}
_TOOLCHAIN_FILES = {
    "codex-agent-ios-arm64-toolchain.json", "codex-agent-ios-simulator-arm64-toolchain.json",
}


def verify_sdk_apple_original_native_content(
    *, evidence_directory: Path, toolchain_directory: Path,
    original_producers: dict[str, dict[str, Any]], source_revision: str, rust_host: str,
    repository: Path, tooling_evidence: Path, tooling_public_key: Path,
    java_executable: Path, policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> None:
    """Check private original bytes using the existing full native/toolchain gate.

    The caller authenticates each original lane producer and the expected Rust
    host independently of the supplied proofs. Source revision is the selected
    SDK binary producer's revision, shared even when lane producers differ.
    This content check neither observes CI nor grants source, host, receipt or
    phase admission authority. No expectations are inferred from proof JSON.
    """
    require_exact_keys(original_producers, _LANES, "Original Apple native producers")
    producers = {lane: dict(validate_producer(original_producers[lane], lane)) for lane in sorted(_LANES)}
    if type(rust_host) is not str or rust_host not in {"aarch64-apple-darwin", "x86_64-apple-darwin"}:
        raise ValueError("Expected original Rust host must be a supported caller-selected Apple host")
    originals = {"evidence": Path(evidence_directory), "toolchain": Path(toolchain_directory)}
    baseline = {name: _input_inventory(path, allow_empty=False) for name, path in originals.items()}
    for name, expected in (("evidence", _EVIDENCE_FILES), ("toolchain", _TOOLCHAIN_FILES)):
        if {row["relativePath"] for row in baseline[name]} != expected:
            raise ValueError(f"Original Apple native {name} must contain exactly its fixed files")

    def unchanged():
        require_exact_keys(original_producers, _LANES, "Original Apple native producers")
        for lane in _LANES:
            validate_producer(original_producers[lane], lane)
        if original_producers != producers:
            raise ValueError("Original Apple native producer expectations changed during verification")
        if any(_input_inventory(path, allow_empty=False) != baseline[name]
               for name, path in originals.items()):
            raise ValueError("Original Apple native input changed during verification")

    try:
        with tempfile.TemporaryDirectory(prefix="sdk-apple-native-source-") as temporary:
            root = Path(temporary).resolve()
            for path in (*originals.values(), Path(repository), Path(tooling_evidence),
                         Path(tooling_public_key), Path(java_executable),
                         *(Path(p) for p in (tooling_keyring, tooling_keys_directory) if p is not None)):
                path = path.resolve()
                if path == root or path in root.parents or root in path.parents:
                    raise ValueError("Apple native source capture overlaps an original input")
            source = root / "source"
            pins = capture_apple_native_sources(Path(repository), source_revision, source)
            unchanged()
            _verify_sdk_apple_with_tooling(
                sources={"evidence": (originals["evidence"], False), "source": (source, False),
                         "toolchain": (originals["toolchain"], False)},
                expected_paths={}, command_name="verify-original-apple-native-evidence",
                argument_builder=lambda private, _expected, _root: {
                    "evidence-directory": private["evidence"], "source-snapshot": private["source"],
                    "toolchain-directory": private["toolchain"], "rust-host": rust_host,
                    "xcode-version": pins["xcodeVersion"], "xcode-build": pins["xcodeBuild"],
                    "swift-version": pins["swiftVersion"],
                    "device-commit": producers["ios-rust-device"]["commit"],
                    "device-tree": producers["ios-rust-device"]["tree"],
                    "simulator-commit": producers["ios-rust-simulator"]["commit"],
                    "simulator-tree": producers["ios-rust-simulator"]["tree"],
                    "tests-commit": producers["ios-native-tests"]["commit"],
                    "tests-tree": producers["ios-native-tests"]["tree"],
                },
                repository=repository, tooling_evidence=tooling_evidence,
                tooling_public_key=tooling_public_key, java_executable=java_executable,
                policy_revision=policy_revision, required_trust_domain=required_trust_domain,
                tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory,
            )
    finally:
        unchanged()
