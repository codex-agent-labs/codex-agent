"""Read external Apple execution identity without granting upload or phase trust."""

from pathlib import Path
from typing import Any

from .inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_regular_directory, require_sha256, sha256_file,
)
from .receipt import validate_producer
from .sdk_apple_device_evidence import _original_directory


_KEYS = {
    "schemaVersion", "producer", "target", "packageArtifact", "binaryArtifact", "rustHost",
    "developerDirectory", "originalWorkingDirectory", "originalDeviceWorkDirectory",
    "originalTestApplicationDirectory", "evidenceSha256",
}
_LIMIT = 16 * 1024 * 1024


def verify_apple_validation_context(context_path: Path, *, producer: dict[str, Any], target: str,
        evidence_archive: Path, original_working_directory: str | None = None) -> dict[str, Any]:
    """Bind retained context to independent caller selections and exact archive bytes.

    The caller authenticates the complete outer upload and selected producer and
    target first. Historical path strings need not exist locally. Source,
    toolchain, execution semantics and admission require their separate gates;
    artifact locators in this ordinary returned dict are not authority.
    """
    expected_producer = canonical_json_bytes(validate_producer(producer))
    if type(target) is not str or target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Apple validation context requires an exact caller-selected iOS target")
    context_path, evidence_archive = Path(context_path), Path(evidence_archive).absolute()
    original = read_regular_file_bytes(context_path, max_bytes=_LIMIT, reject_symlink_parents=True)

    def archive_digest():
        for parent in evidence_archive.parents:
            require_regular_directory(parent, "Apple validation archive ancestry")
        return sha256_file(evidence_archive)

    digest = archive_digest()
    try:
        context = require_exact_keys(load_canonical_json_bytes(original), _KEYS, "Apple validation context")
        if require_integer(context["schemaVersion"], "Apple validation context schema", 1) != 1:
            raise ValueError("Unsupported Apple validation context schema")
        if (canonical_json_bytes(validate_producer(context["producer"])) != expected_producer
                or context["target"] != target):
            raise ValueError("Apple validation context differs from the selected producer or target")
        for name in ("packageArtifact", "binaryArtifact"):
            locator = require_exact_keys(context[name], {"artifactId", "artifactSha256"}, name)
            require_integer(locator["artifactId"], f"{name}.artifactId", 1)
            require_sha256(locator["artifactSha256"], f"{name}.artifactSha256")
        if context["rustHost"] != "aarch64-apple-darwin":
            raise ValueError("Apple validation context requires the fixed macOS ARM64 Rust host")
        paths = {}
        for name in ("developerDirectory", "originalWorkingDirectory", "originalDeviceWorkDirectory",
                     "originalTestApplicationDirectory"):
            paths[name] = _original_directory(context[name], name)
            if any(127 <= ord(character) <= 159 for character in context[name]):
                raise ValueError("Apple validation context path contains a control character")
        working = paths["originalWorkingDirectory"]
        if working.name != "codex-agent-runtime-ios":
            raise ValueError("Apple validation original working directory has the wrong module")
        execution = working / "build/imported-sdk-validation" / producer["tree"] / target
        if (paths["originalDeviceWorkDirectory"] != execution / "device-execution"
                or paths["originalTestApplicationDirectory"] != execution / "device-consumer/CodexAgentTestApp"):
            raise ValueError("Apple validation context does not use its exact target-owned execution paths")
        if original_working_directory is not None:
            expected_working = _original_directory(original_working_directory, "Expected original working directory")
            if str(expected_working) != context["originalWorkingDirectory"]:
                raise ValueError("Apple validation context differs from the independently selected working directory")
        if require_sha256(context["evidenceSha256"], "Apple validation evidence digest") != digest:
            raise ValueError("Apple validation context differs from its exact raw evidence archive")
        return context
    finally:
        if (read_regular_file_bytes(context_path, max_bytes=_LIMIT, reject_symlink_parents=True) != original
                or archive_digest() != digest
                or canonical_json_bytes(validate_producer(producer)) != expected_producer):
            raise ValueError("Apple validation context, archive or caller producer changed during verification")
