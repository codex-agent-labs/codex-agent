from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import tempfile
from typing import Any
import zipfile

from .contract_model import CONTRACT_COMPONENTS, verify_contract_bundle
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_semver,
    sha256_bytes,
    sha256_file,
    snapshot_regular_tree,
)
from .receipt import validate_output_manifest, validate_phase_receipt, verify_output_manifest
from .signatures import load_keyring, public_key_for_metadata


PRODUCT_JSON_LIMIT = 16 * 1024 * 1024
PUBLIC_KEY_LIMIT = 1024 * 1024
_VERIFIED = object()


class VerifiedContractProjection:
    """Opaque value created only after Contract Bundle authentication."""

    __slots__ = ("_canonical", "_verified")

    def __init__(self, value: dict[str, Any], verified: object) -> None:
        if verified is not _VERIFIED:
            raise TypeError("Contract projections must be produced by verification")
        self._canonical = canonical_json_bytes(value)
        self._verified = verified

    def receipt_value(self) -> dict[str, Any]:
        if self._verified is not _VERIFIED:
            raise TypeError("Contract projection is not authenticated")
        return load_canonical_json_bytes(self._canonical)

    @property
    def components(self) -> tuple[str, ...]:
        return tuple(
            record["component"]
            for record in self.receipt_value()["componentDigests"]
        )


def _receipt_bytes(value: bytes | Path) -> bytes:
    if type(value) is bytes:
        if not value or len(value) > PRODUCT_JSON_LIMIT:
            raise ValueError("Contract metadata receipt size is outside the fixed bound")
        return value
    return read_regular_file_bytes(
        Path(value),
        max_bytes=PRODUCT_JSON_LIMIT,
        reject_symlink_parents=True,
    )


def _required_components(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ValueError("Required Contract components must be a nonempty iterable")
    components = tuple(values)
    if any(type(component) is not str or component not in CONTRACT_COMPONENTS for component in components):
        raise ValueError("Required Contract components contain an unsupported component")
    if not components or len(components) != len(set(components)):
        raise ValueError("Required Contract components must be nonempty and unique")
    return tuple(sorted(components))


def _manifest_bytes(archive: Path) -> bytes:
    with zipfile.ZipFile(archive) as source:
        try:
            member = source.getinfo("contract-manifest.json")
        except KeyError as error:
            raise ValueError("Authenticated Contract Bundle is missing its manifest") from error
        if member.file_size <= 0 or member.file_size > PRODUCT_JSON_LIMIT:
            raise ValueError("Authenticated Contract manifest size is outside the fixed bound")
        return source.read(member)


def verify_contract_component_projection(
    stage_root: Path,
    phase_receipt: bytes | Path,
    public_key: Path,
    *,
    expected_trust_domain: str,
    expected_contract_version: str,
    required_components: Iterable[str],
    keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> VerifiedContractProjection:
    """Derive target component digests only from authenticated Contract metadata."""
    if expected_trust_domain not in {"development", "release"}:
        raise ValueError("Expected Contract trust domain must be development or release")
    version = require_semver(expected_contract_version, "Expected Contract version")
    components = _required_components(required_components)
    if expected_trust_domain == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Contract projection requires a keyring and keys directory")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Contract projection must not receive release keyring inputs")

    receipt_bytes = _receipt_bytes(phase_receipt)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    if (
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
        receipt["productVersion"],
    ) != ("contract", "contract", "metadata", "common", version):
        raise ValueError("Contract metadata receipt identity is invalid")
    if receipt["trustDomain"] != expected_trust_domain:
        raise ValueError("Contract metadata receipt trust domain is invalid")

    public_key_bytes = read_regular_file_bytes(
        Path(public_key),
        max_bytes=PUBLIC_KEY_LIMIT,
        reject_symlink_parents=True,
    )
    with tempfile.TemporaryDirectory(prefix="codex-agent-contract-projection-") as temporary:
        temporary_root = Path(temporary).resolve()
        stage = temporary_root / "stage"
        snapshot_regular_tree(Path(stage_root), stage)
        trusted_key = temporary_root / "public-key.pub"
        trusted_key.write_bytes(public_key_bytes)

        output_manifest_bytes = read_regular_file_bytes(
            stage / "output-manifest.json",
            max_bytes=PRODUCT_JSON_LIMIT,
            reject_symlink_parents=True,
        )
        output_manifest = validate_output_manifest(
            load_canonical_json_bytes(output_manifest_bytes),
        )
        if (
            output_manifest["product"],
            output_manifest["component"],
            output_manifest["phase"],
            output_manifest["target"],
            output_manifest["productVersion"],
        ) != ("contract", "contract", "metadata", "common", version):
            raise ValueError("Contract metadata output manifest identity is invalid")
        verify_output_manifest(stage, output_manifest)
        if receipt["outputs"] != output_manifest["outputs"]:
            raise ValueError("Contract metadata receipt and output manifest disagree")

        bundles = [
            output
            for output in output_manifest["outputs"]
            if output["kind"] == "contract-bundle"
        ]
        if len(bundles) != 1:
            raise ValueError("Contract metadata must declare exactly one Contract Bundle")
        bundle = bundles[0]
        expected_path = f"outputs/codex-agent-contract-{version}.zip"
        if bundle["relativePath"] != expected_path:
            raise ValueError("Contract Bundle output path is invalid")
        archive = stage / expected_path
        if sha256_file(archive) != bundle["sha256"]:
            raise ValueError("Contract Bundle output digest is invalid")

        manifest = verify_contract_bundle(
            archive,
            trusted_key,
            expected_trust_domain=expected_trust_domain,
        )
        if manifest["contractVersion"] != version:
            raise ValueError("Contract manifest version does not match the expected Contract version")
        if manifest["producer"] != receipt["producer"]:
            raise ValueError("Contract manifest and metadata receipt producers differ")

        if expected_trust_domain == "release":
            assert keyring is not None and keys_directory is not None
            tracked_key = public_key_for_metadata(
                manifest["signing"],
                load_keyring(Path(keyring), Path(keys_directory)),
                Path(keys_directory),
                allow_retired=True,
            )
            if read_regular_file_bytes(
                tracked_key,
                max_bytes=PUBLIC_KEY_LIMIT,
                reject_symlink_parents=True,
            ) != public_key_bytes:
                raise ValueError("Supplied Contract public key does not match its tracked release key")

        manifest_bytes = _manifest_bytes(archive)
        if load_canonical_json_bytes(manifest_bytes) != manifest:
            raise ValueError("Authenticated Contract manifest bytes changed during projection")
        verify_output_manifest(stage, output_manifest)
        if sha256_file(archive) != bundle["sha256"]:
            raise ValueError("Contract Bundle changed during projection")

        return VerifiedContractProjection({
            "schemaVersion": 1,
            "receiptSha256": sha256_bytes(receipt_bytes),
            "bundlePath": expected_path,
            "bundleSha256": bundle["sha256"],
            "manifestSha256": sha256_bytes(manifest_bytes),
            "contractVersion": manifest["contractVersion"],
            "contractDigest": manifest["contractDigest"],
            "componentDigests": [
                {
                    "component": component,
                    "sha256": manifest["components"][component]["sha256"],
                }
                for component in components
            ],
        }, _VERIFIED)
