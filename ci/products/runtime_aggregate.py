"""Deterministically produce one development-signed Runtime aggregate."""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any

from .aggregate import (
    RUNTIME_ADAPTERS,
    RUNTIME_TARGETS,
    RUNTIME_VARIANT_ZIP_LIMITS,
    validate_runtime_aggregate,
    validate_runtime_variant,
    verify_runtime_aggregate_artifacts,
)
from .contract_model import verify_contract_bundle
from .inventory import (
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_array,
    require_exact_keys,
    require_regular_directory,
    require_semver,
    sha256_bytes,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import validate_phase_receipt
from .signatures import (
    sign_manifest,
    validate_signing_metadata,
    verify_manifest_signature,
)


_JSON_LIMIT = 16 * 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_VARIANT_MANIFEST = "runtime-variant-manifest.json"
_VARIANT_SIGNATURE = "runtime-variant-manifest.sig"


def _exact_target_mapping(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(RUNTIME_TARGETS):
        raise ValueError(f"{label} must contain exactly the five Runtime targets")
    return value


def _read_receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(
        Path(path), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _safe_empty_output(path: Path) -> Path:
    root = require_regular_directory(Path(os.path.abspath(path)), "Runtime aggregate output directory")
    for ancestor in (root, *root.parents):
        metadata = ancestor.lstat()
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Runtime aggregate output directory has an unsafe parent")
    if any(root.iterdir()):
        raise ValueError("Runtime aggregate output directory must be empty")
    return root


def _variant_input(bundle: Path) -> tuple[dict[str, Any], dict[str, Any], bytes]:
    _, contents, identity = verified_zip_contents(
        Path(bundle),
        **RUNTIME_VARIANT_ZIP_LIMITS,
        retained_paths={_VARIANT_MANIFEST, _VARIANT_SIGNATURE},
        max_retained_bytes=2 * 1024 * 1024,
    )
    if set(contents) != {_VARIANT_MANIFEST, _VARIANT_SIGNATURE}:
        raise ValueError(f"Runtime variant bundle lacks its signed manifest: {bundle}")
    manifest_bytes = contents[_VARIANT_MANIFEST]
    return validate_runtime_variant(load_canonical_json_bytes(manifest_bytes)), identity, manifest_bytes


def _file_record(path: Path, logical_path: str, role: str, **identity: str) -> dict[str, Any]:
    contents = read_regular_file_bytes(Path(path), reject_symlink_parents=True)
    if not contents:
        raise ValueError(f"Runtime aggregate input is empty: {path}")
    return {
        "path": logical_path,
        "role": role,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
        **identity,
    }


def produce_runtime_aggregate(
    *,
    runtime_version: str,
    contract_bundle: Path,
    contract_public_key: Path,
    required_trust_domain: str,
    variant_bundles: dict[str, Path],
    phase_receipts: dict[str, dict[str, Path]],
    metadata_receipts: dict[str, Path],
    validation_evidence: dict[str, Path],
    trusted_variant_keys: dict[str, Path],
    runtime_maven_files: list[dict[str, Any]],
    adapter_evidence: dict[str, Path],
    signing_metadata: Any,
    private_key: Path,
    public_key: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Validate exact product inputs, sign, and reverify one Runtime aggregate."""
    require_semver(runtime_version, "Runtime aggregate version")
    contract = verify_contract_bundle(
        Path(contract_bundle),
        Path(contract_public_key),
        expected_trust_domain=required_trust_domain,
    )
    signing = validate_signing_metadata(signing_metadata, trust_domain=required_trust_domain)
    output = _safe_empty_output(Path(output_directory))
    for value, label in (
        (variant_bundles, "Runtime variant bundles"),
        (phase_receipts, "Runtime phase receipts"),
        (metadata_receipts, "Runtime metadata receipts"),
        (validation_evidence, "Runtime validation evidence"),
        (trusted_variant_keys, "Runtime variant public keys"),
    ):
        _exact_target_mapping(value, label)
    if type(adapter_evidence) is not dict or set(adapter_evidence) != set(RUNTIME_ADAPTERS):
        raise ValueError("Runtime adapter evidence must contain exactly JVM, Node JS, and Node Wasm")

    release = runtime_version.split("-", 1)[0].split(".")
    runtime_compatibility = f"{release[0]}.{release[1]}.0"
    variants = []
    variant_values = {}
    for target in RUNTIME_TARGETS:
        variant, bundle_identity, manifest_bytes = _variant_input(Path(variant_bundles[target]))
        variant_values[target] = variant
        target_receipts = phase_receipts[target]
        if type(target_receipts) is not dict or set(target_receipts) != {
            "binary", "package", "validation",
        }:
            raise ValueError(f"Runtime phase receipts must contain exactly three phases: {target}")
        receipt_records = {}
        for phase in ("binary", "package", "validation"):
            receipt, contents = _read_receipt(
                Path(target_receipts[phase]),
            )
            receipt_records[phase] = {
                "sha256": sha256_bytes(contents),
                "producer": receipt["producer"],
            }
        metadata_receipt, metadata_bytes = _read_receipt(
            Path(metadata_receipts[target]),
        )
        variants.append({
            "target": target,
            "componentId": variant["componentId"],
            "bundleSha256": bundle_identity["sha256"],
            "manifestSha256": sha256_bytes(manifest_bytes),
            "receiptSha256": sha256_bytes(metadata_bytes),
            "phaseReceipts": receipt_records,
            "sourceRuntimeVersion": metadata_receipt["productVersion"],
            "producer": metadata_receipt["producer"],
        })

    first = variant_values[RUNTIME_TARGETS[0]]
    c_abi = first["cAbi"]
    compatibility = {
        "cAbiVersion": c_abi["version"],
        "minimumCAbiVersion": c_abi["minimumCompatibleVersion"],
        "identitySchema": c_abi["identitySchemaVersion"],
        "headerSha256": c_abi["headerSha256"],
        "symbolSetSha256": c_abi["symbolSetSha256"],
        "symbolCount": c_abi["symbolCount"],
        "appServerVersion": first["appServer"]["version"],
        "appServerReleaseTag": first["appServer"]["releaseTag"],
        "toolchainProfileDigests": {
            target: variant_values[target]["toolchainProfile"]["digest"]
            for target in RUNTIME_TARGETS
        },
    }

    maven_records = []
    for index, value in enumerate(require_array(runtime_maven_files, "Runtime Maven file inputs")):
        record = require_exact_keys(
            value, {"path", "role", "component", "file"}, f"Runtime Maven file input[{index}]",
        )
        maven_records.append(_file_record(
            Path(record["file"]), record["path"], record["role"], component=record["component"],
        ))
    maven_records.sort(key=lambda record: record["path"])
    adapter_records = sorted(
        (
            _file_record(
                Path(adapter_evidence[target]), f"evidence/{target}.json", "adapter", target=target,
            )
            for target in RUNTIME_ADAPTERS
        ),
        key=lambda record: record["path"],
    )
    aggregate = validate_runtime_aggregate({
        "schemaVersion": 1,
        "product": "runtime",
        "runtimeVersion": runtime_version,
        "runtimeCompatibilityVersion": runtime_compatibility,
        "contract": {
            "version": contract["contractVersion"],
            "digest": contract["contractDigest"],
        },
        "variants": variants,
        "runtimeMavenFiles": maven_records,
        "adapterEvidence": adapter_records,
        "compatibility": compatibility,
        "signing": signing,
    })

    manifest_path = output / f"codex-agent-runtime-{runtime_version}-manifest.json"
    signature_path = output / f"codex-agent-runtime-{runtime_version}-manifest.sig"
    try:
        read_regular_file_bytes(Path(private_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True)
        read_regular_file_bytes(Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True)
        write_canonical_json(manifest_path, aggregate)
        generated_signature = sign_manifest(manifest_path, Path(private_key), signing)
        if generated_signature != signature_path:
            raise ValueError("Runtime aggregate signature identity mismatch")
        verify_manifest_signature(manifest_path, signature_path, Path(public_key), signing)
        verified = verify_runtime_aggregate_artifacts(
            manifest_path,
            aggregate_signature=signature_path,
            aggregate_public_key=Path(public_key),
            contract_bundle=Path(contract_bundle),
            contract_public_key=Path(contract_public_key),
            variant_bundles=variant_bundles,
            metadata_receipts=metadata_receipts,
            phase_receipts=phase_receipts,
            validation_evidence=validation_evidence,
            trusted_public_keys=trusted_variant_keys,
            runtime_maven_files=[
                {**value, "file": os.fspath(value["file"])} for value in runtime_maven_files
            ],
            adapter_evidence=adapter_evidence,
            required_trust_domain=required_trust_domain,
        )
        if verified != aggregate:
            raise ValueError("Verified Runtime aggregate differs from the produced manifest")
    except Exception:
        manifest_path.unlink(missing_ok=True)
        signature_path.unlink(missing_ok=True)
        raise
    if sorted(path.name for path in output.iterdir()) != sorted((manifest_path.name, signature_path.name)):
        manifest_path.unlink(missing_ok=True)
        signature_path.unlink(missing_ok=True)
        raise ValueError("Runtime aggregate output directory contains unexpected entries")
    return {
        "manifest": aggregate,
        "manifestPath": manifest_path,
        "manifestSha256": sha256_bytes(manifest_path.read_bytes()),
        "signaturePath": signature_path,
        "signatureSha256": sha256_bytes(signature_path.read_bytes()),
    }
