"""Deterministic Runtime aggregate payload and detached trust attestation."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
from typing import Any

from .aggregate import (
    RUNTIME_ADAPTERS,
    RUNTIME_TARGETS,
    validate_runtime_aggregate,
    validate_runtime_maven_inventory,
    verify_runtime_aggregate_artifacts,
)
from .contract_attestation import verify_contract_attestation
from .index import (
    _held_output_parent,
    _publish_output,
    _read_parent_file,
    _require_parent_identity,
)
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    publish_regular_tree,
    read_regular_file_bytes,
    regular_file_inventory,
    require_array,
    require_exact_keys,
    require_identifier,
    require_integer,
    require_regular_directory,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    write_canonical_json,
)
from .receipt import validate_phase_receipt
from .runtime_attestation import verify_runtime_variant_attestation
from .signatures import (
    load_keyring,
    public_key_for_metadata,
    sign_manifest,
    validate_signing_metadata,
    verify_manifest_signature,
)


_JSON_LIMIT = 16 * 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_VARIANT_PHASES = ("binary", "package", "validation", "metadata")


def _adapter_receipt_identities() -> list[tuple[str, str, str]]:
    return sorted([
        *(("jvm", phase, "jvm") for phase in ("binary", "package", "metadata")),
        *(("jvm", "validation", target) for target in RUNTIME_TARGETS),
        *(("node-js", phase, "node-js") for phase in ("binary", "package", "metadata")),
        *(("node-js", "validation", target) for target in (*RUNTIME_TARGETS, "node-js-binding")),
        *(("node-wasm", phase, "node-wasm") for phase in ("binary", "package", "metadata")),
        *(("node-wasm", "validation", target) for target in RUNTIME_TARGETS),
    ])


def _exact_target_mapping(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(RUNTIME_TARGETS):
        raise ValueError(f"{label} must contain exactly the five Runtime targets")
    return value


def _read_receipt(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(
        Path(path), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    if not contents:
        raise ValueError(f"{label} must not be empty")
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _safe_output_directory(path: Path) -> Path:
    root = require_regular_directory(
        Path(os.path.abspath(path)), "Runtime aggregate output directory",
    )
    for ancestor in (root, *root.parents):
        metadata = ancestor.lstat()
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Runtime aggregate output directory has an unsafe parent")
    return root


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


def _variant_inputs(
    *,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    required_variant_trust_domain: str,
    variant_validation_evidence: dict[str, Path] | None,
    variant_keyring: Path | None,
    variant_keys_directory: Path | None,
) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]],
    dict[str, dict[str, dict[str, Any]]],
]:
    for value, label in (
        (variant_bundles, "Runtime variant bundles"),
        (variant_phase_receipts, "Runtime variant phase receipts"),
        (variant_attestations, "Runtime variant attestations"),
        (variant_attestation_signatures, "Runtime variant attestation signatures"),
        (variant_public_keys, "Runtime variant public keys"),
    ):
        _exact_target_mapping(value, label)
    if variant_validation_evidence is not None:
        _exact_target_mapping(
            variant_validation_evidence, "Runtime variant validation evidence",
        )

    payload_records = []
    attestation_records = []
    manifests = {}
    receipts_by_target = {}
    for target in RUNTIME_TARGETS:
        paths = variant_phase_receipts[target]
        if type(paths) is not dict or set(paths) != set(_VARIANT_PHASES):
            raise ValueError(f"Runtime variant receipts must contain exactly four phases: {target}")
        manifest, receipts, attestation = verify_runtime_variant_attestation(
            Path(variant_bundles[target]),
            Path(paths["binary"]),
            Path(paths["package"]),
            Path(paths["validation"]),
            Path(paths["metadata"]),
            Path(variant_attestations[target]),
            Path(variant_attestation_signatures[target]),
            Path(variant_public_keys[target]),
            required_trust_domain=required_variant_trust_domain,
            validation_evidence=(
                None if variant_validation_evidence is None
                else Path(variant_validation_evidence[target])
            ),
            keyring=variant_keyring,
            keys_directory=variant_keys_directory,
        )
        if manifest["target"] != target or attestation["target"] != target:
            raise ValueError(f"Runtime variant target does not match its mapping: {target}")
        payload_record = {
            "target": target,
            "componentId": manifest["componentId"],
            "bundleSha256": attestation["payload"]["sha256"],
            "manifestSha256": attestation["manifestSha256"],
        }
        attestation_bytes = read_regular_file_bytes(
            Path(variant_attestations[target]),
            max_bytes=_JSON_LIMIT,
            reject_symlink_parents=True,
        )
        payload_records.append(payload_record)
        attestation_records.append({
            **payload_record,
            "variantAttestationSha256": sha256_bytes(attestation_bytes),
            "phaseReceipts": dict(attestation["phaseReceipts"]),
        })
        manifests[target] = manifest
        receipts_by_target[target] = receipts
    return payload_records, attestation_records, manifests, receipts_by_target


def _compatibility(
    manifests: dict[str, dict[str, Any]], runtime_compatibility: str,
) -> dict[str, Any]:
    first = manifests[RUNTIME_TARGETS[0]]
    contract_digest = first["contract"]["digest"]
    c_abi = first["cAbi"]
    app_server = first["appServer"]
    for target in RUNTIME_TARGETS:
        variant = manifests[target]
        if variant["runtimeCompatibilityVersion"] != runtime_compatibility:
            raise ValueError("Runtime variant compatibility version does not match the aggregate")
        if variant["contract"]["digest"] != contract_digest:
            raise ValueError("Runtime variants do not share one Contract digest")
        if variant["cAbi"] != c_abi:
            raise ValueError("Runtime variants do not share one C ABI policy")
        if variant["appServer"]["version"] != app_server["version"] or \
                variant["appServer"]["releaseTag"] != app_server["releaseTag"]:
            raise ValueError("Runtime variants do not share one app-server policy")
    return {
        "cAbiVersion": c_abi["version"],
        "minimumCAbiVersion": c_abi["minimumCompatibleVersion"],
        "identitySchema": c_abi["identitySchemaVersion"],
        "headerSha256": c_abi["headerSha256"],
        "symbolSetSha256": c_abi["symbolSetSha256"],
        "symbolCount": c_abi["symbolCount"],
        "appServerVersion": app_server["version"],
        "appServerReleaseTag": app_server["releaseTag"],
        "toolchainProfileDigests": {
            target: manifests[target]["toolchainProfile"]["digest"]
            for target in RUNTIME_TARGETS
        },
    }


def produce_runtime_aggregate(
    *,
    runtime_version: str,
    contract_payload: Path,
    contract_metadata_receipt: Path,
    contract_attestation: Path,
    contract_attestation_signature: Path,
    contract_public_key: Path,
    required_trust_domain: str,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    variant_validation_evidence: dict[str, Path],
    runtime_maven_files: list[dict[str, Any]],
    adapter_evidence: dict[str, Path],
    output_directory: Path,
    contract_keyring: Path | None = None,
    contract_keys_directory: Path | None = None,
    variant_keyring: Path | None = None,
    variant_keys_directory: Path | None = None,
) -> dict[str, Any]:
    """Authenticate content inputs and emit only one canonical aggregate manifest."""
    version = require_semver(runtime_version, "Runtime aggregate version")
    contract, _, _ = verify_contract_attestation(
        Path(contract_payload),
        Path(contract_metadata_receipt),
        Path(contract_attestation),
        Path(contract_attestation_signature),
        Path(contract_public_key),
        required_trust_domain=required_trust_domain,
        keyring=contract_keyring,
        keys_directory=contract_keys_directory,
    )
    payload_variants, _, manifests, _ = _variant_inputs(
        variant_bundles=variant_bundles,
        variant_phase_receipts=variant_phase_receipts,
        variant_attestations=variant_attestations,
        variant_attestation_signatures=variant_attestation_signatures,
        variant_public_keys=variant_public_keys,
        required_variant_trust_domain=required_trust_domain,
        variant_validation_evidence=variant_validation_evidence,
        variant_keyring=variant_keyring,
        variant_keys_directory=variant_keys_directory,
    )
    release = version.split("-", 1)[0].split(".")
    runtime_compatibility = f"{release[0]}.{release[1]}.0"
    compatibility = _compatibility(manifests, runtime_compatibility)
    if any(
        manifest["contract"]["digest"] != contract["contractDigest"]
        for manifest in manifests.values()
    ):
        raise ValueError("Runtime variants do not reference the authenticated Contract")

    maven_records = []
    maven_contents: dict[str, bytes] = {}
    for index, value in enumerate(require_array(runtime_maven_files, "Runtime Maven file inputs")):
        record = require_exact_keys(
            value, {"path", "role", "component", "file"},
            f"Runtime Maven file input[{index}]",
        )
        file_record = _file_record(
            Path(record["file"]), record["path"], record["role"],
            component=record["component"],
        )
        maven_records.append(file_record)
        maven_contents[file_record["path"]] = read_regular_file_bytes(
            Path(record["file"]), reject_symlink_parents=True,
        )
    maven_records.sort(key=lambda record: record["path"])
    validate_runtime_maven_inventory(maven_records, maven_contents)
    from .runtime_maven import validate_runtime_maven_publications
    validate_runtime_maven_publications(version, contract["contractVersion"], maven_records, maven_contents)
    if type(adapter_evidence) is not dict or set(adapter_evidence) != set(RUNTIME_ADAPTERS):
        raise ValueError("Runtime adapter evidence must contain exactly JVM, Node JS, and Node Wasm")
    adapter_records = sorted((
        _file_record(
            Path(adapter_evidence[target]), f"evidence/{target}.json", "adapter", target=target,
        )
        for target in RUNTIME_ADAPTERS
    ), key=lambda record: record["path"])
    aggregate = validate_runtime_aggregate({
        "schemaVersion": 1,
        "product": "runtime",
        "runtimeVersion": version,
        "runtimeCompatibilityVersion": runtime_compatibility,
        "contract": {
            "version": contract["contractVersion"],
            "digest": contract["contractDigest"],
        },
        "variants": payload_variants,
        "runtimeMavenFiles": maven_records,
        "adapterEvidence": adapter_records,
        "compatibility": compatibility,
    })
    manifest_bytes = canonical_json_bytes(aggregate)
    output = _safe_output_directory(Path(output_directory))
    manifest_name = f"codex-agent-runtime-{version}-manifest.json"
    with _held_output_parent(output) as (descriptor, held_output):
        expected = []
        if os.listdir(held_output if os.name == "nt" else descriptor):
            expected = [{"relativePath": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]}
                        for record in maven_records]
            if regular_file_inventory(output) != expected or any(
                    Path(record["file"]) != output / record["path"] for record in runtime_maven_files):
                raise ValueError("Runtime aggregate output directory must be empty or its exact staged Maven inventory")
        if not _publish_output(
            manifest_bytes, descriptor, held_output, manifest_name, max_bytes=_JSON_LIMIT,
        ):
            raise ValueError("Runtime aggregate manifest was concurrently published")
        if _read_parent_file(
            descriptor, held_output, manifest_name, max_bytes=_JSON_LIMIT,
        ) != manifest_bytes:
            raise ValueError("Published Runtime aggregate manifest changed")
        final_inventory = sorted([*expected, {"relativePath": manifest_name,
            "bytes": len(manifest_bytes), "sha256": sha256_bytes(manifest_bytes)}], key=lambda record: record["relativePath"])
        if regular_file_inventory(output) != final_inventory:
            raise ValueError("Runtime aggregate output directory contains unexpected entries")
        _require_parent_identity(descriptor, held_output)
    return {
        "manifest": aggregate,
        "manifestPath": output / manifest_name,
        "manifestSha256": sha256_bytes(manifest_bytes),
    }


def _adapter_receipt_closure(
    adapter_receipts: Any, runtime_compatibility: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    expected = _adapter_receipt_identities()
    values = require_array(adapter_receipts, "Runtime adapter receipt inputs")
    inputs = []
    identities = []
    for index, value in enumerate(values):
        record = require_exact_keys(
            value, {"component", "phase", "target", "receipt"},
            f"Runtime adapter receipt input[{index}]",
        )
        identity = (
            require_identifier(record["component"], f"Runtime adapter receipt input[{index}].component"),
            require_identifier(record["phase"], f"Runtime adapter receipt input[{index}].phase"),
            require_identifier(record["target"], f"Runtime adapter receipt input[{index}].target"),
        )
        if not isinstance(record["receipt"], (str, os.PathLike)) or not os.fspath(record["receipt"]):
            raise ValueError(f"Runtime adapter receipt input[{index}].receipt is invalid")
        receipt, contents = _read_receipt(
            Path(record["receipt"]), f"Runtime adapter receipt input[{index}]",
        )
        if (
            receipt["product"], receipt["component"], receipt["phase"], receipt["target"],
        ) != ("runtime", *identity):
            raise ValueError(f"Runtime adapter receipt input[{index}] identity mismatch")
        if receipt["inputs"]["versionIdentity"] != runtime_compatibility:
            raise ValueError(f"Runtime adapter receipt input[{index}] compatibility mismatch")
        identities.append(identity)
        inputs.append((receipt, contents))
    if identities != expected:
        raise ValueError("Runtime adapter receipts must be the exact sorted 25-record closure")
    return [
        {
            "component": component,
            "phase": phase,
            "target": target,
            "receiptSha256": sha256_bytes(contents),
        }
        for (component, phase, target), (_, contents) in zip(expected, inputs, strict=True)
    ], [receipt for receipt, _ in inputs]


def validate_runtime_aggregate_attestation(value: Any) -> dict[str, Any]:
    attestation = require_exact_keys(value, {
        "schemaVersion", "product", "runtimeVersion", "payload",
        "metadataReceiptSha256", "variants", "adapterReceipts", "signing",
    }, "Runtime aggregate attestation")
    if require_integer(
        attestation["schemaVersion"], "Runtime aggregate attestation.schemaVersion", 1,
    ) != 1:
        raise ValueError("Unsupported Runtime aggregate attestation schemaVersion")
    if attestation["product"] != "runtime":
        raise ValueError("Runtime aggregate attestation product must be runtime")
    version = require_semver(
        attestation["runtimeVersion"], "Runtime aggregate attestation.runtimeVersion",
    )
    payload = require_exact_keys(
        attestation["payload"], {"fileName", "bytes", "sha256"},
        "Runtime aggregate attestation.payload",
    )
    if require_string(
        payload["fileName"], "Runtime aggregate attestation.payload.fileName",
    ) != f"codex-agent-runtime-{version}-manifest.json":
        raise ValueError("Runtime aggregate attestation payload filename is invalid")
    require_integer(payload["bytes"], "Runtime aggregate attestation.payload.bytes", 1)
    require_sha256(payload["sha256"], "Runtime aggregate attestation.payload.sha256")
    require_sha256(
        attestation["metadataReceiptSha256"],
        "Runtime aggregate attestation.metadataReceiptSha256",
    )
    variants = require_array(attestation["variants"], "Runtime aggregate attestation.variants")
    if len(variants) != len(RUNTIME_TARGETS):
        raise ValueError("Runtime aggregate attestation requires exactly five variants")
    for index, record in enumerate(variants):
        item = require_exact_keys(record, {
            "target", "componentId", "bundleSha256", "manifestSha256",
            "variantAttestationSha256", "phaseReceipts",
        }, f"Runtime aggregate attestation.variants[{index}]")
        if item["target"] != RUNTIME_TARGETS[index]:
            raise ValueError("Runtime aggregate attestation variants are not exact and sorted")
        for field in (
            "componentId", "bundleSha256", "manifestSha256", "variantAttestationSha256",
        ):
            require_sha256(item[field], f"Runtime aggregate attestation variant {field}")
        receipts = require_exact_keys(
            item["phaseReceipts"], set(_VARIANT_PHASES),
            f"Runtime aggregate attestation.variants[{index}].phaseReceipts",
        )
        for phase in _VARIANT_PHASES:
            require_sha256(receipts[phase], f"Runtime aggregate attestation variant {phase}")
    adapter_receipts = require_array(
        attestation["adapterReceipts"], "Runtime aggregate attestation.adapterReceipts",
    )
    if len(adapter_receipts) != 25:
        raise ValueError("Runtime aggregate attestation requires exactly 25 adapter receipts")
    identities = []
    for index, record in enumerate(adapter_receipts):
        item = require_exact_keys(
            record, {"component", "phase", "target", "receiptSha256"},
            f"Runtime aggregate attestation.adapterReceipts[{index}]",
        )
        identity = tuple(require_identifier(
            item[field], f"Runtime aggregate attestation.adapterReceipts[{index}].{field}",
        ) for field in ("component", "phase", "target"))
        identities.append(identity)
        require_sha256(
            item["receiptSha256"],
            f"Runtime aggregate attestation.adapterReceipts[{index}].receiptSha256",
        )
    if identities != _adapter_receipt_identities():
        raise ValueError("Runtime aggregate attestation adapter receipts are not the exact closure")
    validate_signing_metadata(attestation["signing"])
    return attestation


def _aggregate_payload_identity(
    manifest: Path,
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    contents = read_regular_file_bytes(
        Path(manifest), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    aggregate = validate_runtime_aggregate(load_canonical_json_bytes(contents))
    if contents != canonical_json_bytes(aggregate):
        raise ValueError("Runtime aggregate manifest is not canonical")
    expected_name = f"codex-agent-runtime-{aggregate['runtimeVersion']}-manifest.json"
    if Path(manifest).name != expected_name:
        raise ValueError("Runtime aggregate manifest filename is invalid")
    return aggregate, contents, {
        "fileName": expected_name,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }


def _aggregate_bound_inputs(
    manifest: Path, metadata_receipt: Path,
) -> tuple[dict[str, Any], dict[str, Any], bytes, dict[str, Any]]:
    aggregate, _, payload = _aggregate_payload_identity(Path(manifest))
    receipt, receipt_bytes = _read_receipt(
        Path(metadata_receipt), "Runtime aggregate metadata receipt",
    )
    if (
        receipt["product"], receipt["component"], receipt["phase"], receipt["target"],
    ) != ("runtime", "runtime-aggregate", "metadata", "aggregate"):
        raise ValueError("Runtime aggregate attestation requires its metadata receipt")
    if (
        receipt["productVersion"] != aggregate["runtimeVersion"]
        or receipt["inputs"]["versionIdentity"] != aggregate["runtimeVersion"]
    ):
        raise ValueError("Runtime aggregate metadata receipt version mismatch")
    expected_output = {
        "kind": "runtime-aggregate",
        "relativePath": f"outputs/{payload['fileName']}",
        "bytes": payload["bytes"],
        "sha256": payload["sha256"],
    }
    expected_outputs = sorted([expected_output, *({
        "kind": "maven", "relativePath": f"outputs/{record['path']}",
        "bytes": record["bytes"], "sha256": record["sha256"],
    } for record in aggregate["runtimeMavenFiles"])], key=lambda record: record["relativePath"])
    if receipt["outputs"] != expected_outputs:
        raise ValueError("Runtime aggregate metadata receipt does not bind the exact payload")
    return aggregate, receipt, receipt_bytes, payload


def verify_runtime_aggregate_attestation(
    manifest: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    *,
    required_trust_domain: str,
    keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("Expected Runtime aggregate attestation trust domain is invalid")
    contents = read_regular_file_bytes(
        Path(attestation), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    public_key_bytes = read_regular_file_bytes(
        Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    value = validate_runtime_aggregate_attestation(load_canonical_json_bytes(contents))
    version = value["runtimeVersion"]
    stem = f"codex-agent-runtime-{version}.attestation"
    if Path(attestation).name != f"{stem}.json" or Path(signature).name != f"{stem}.sig":
        raise ValueError("Runtime aggregate attestation or signature filename is invalid")
    signing = validate_signing_metadata(value["signing"], trust_domain=required_trust_domain)
    aggregate, receipt, receipt_bytes, payload = _aggregate_bound_inputs(
        Path(manifest), Path(metadata_receipt),
    )
    if value["runtimeVersion"] != aggregate["runtimeVersion"] or value["payload"] != payload or \
            value["metadataReceiptSha256"] != sha256_bytes(receipt_bytes):
        raise ValueError("Runtime aggregate attestation does not bind its payload and receipt")
    attested_variants = [
        {key: record[key] for key in ("target", "componentId", "bundleSha256", "manifestSha256")}
        for record in value["variants"]
    ]
    if attested_variants != aggregate["variants"]:
        raise ValueError("Runtime aggregate attestation variant identities differ from its payload")
    if required_trust_domain == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Runtime aggregate attestation verification requires a keyring")
        trusted = public_key_for_metadata(
            signing, load_keyring(Path(keyring), Path(keys_directory)), Path(keys_directory),
            allow_retired=True,
        )
        if read_regular_file_bytes(trusted, reject_symlink_parents=True) != public_key_bytes:
            raise ValueError("Runtime aggregate attestation key does not match the keyring")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Runtime aggregate attestation rejects release keyring inputs")
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-attestation-verify-") as temporary:
        root = Path(temporary).resolve()
        snapshot = root / Path(attestation).name
        detached = root / Path(signature).name
        key = root / "runtime.pub"
        snapshot.write_bytes(contents)
        detached.write_bytes(signature_bytes)
        key.write_bytes(public_key_bytes)
        verify_manifest_signature(snapshot, detached, key, signing)
    return aggregate, receipt, value


def verify_runtime_aggregate_attestation_closure(
    aggregate: Any,
    attestation: Any,
    *,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    adapter_receipts: list[dict[str, Any]],
    required_variant_trust_domain: str,
    variant_validation_evidence: dict[str, Path] | None = None,
    variant_keyring: Path | None = None,
    variant_keys_directory: Path | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, dict[str, Any]]], list[dict[str, Any]]]:
    aggregate_value = validate_runtime_aggregate(aggregate)
    attestation_value = validate_runtime_aggregate_attestation(attestation)
    payload_records, variant_records, manifests, receipts = _variant_inputs(
        variant_bundles=variant_bundles,
        variant_phase_receipts=variant_phase_receipts,
        variant_attestations=variant_attestations,
        variant_attestation_signatures=variant_attestation_signatures,
        variant_public_keys=variant_public_keys,
        required_variant_trust_domain=required_variant_trust_domain,
        variant_validation_evidence=variant_validation_evidence,
        variant_keyring=variant_keyring,
        variant_keys_directory=variant_keys_directory,
    )
    if variant_records != attestation_value["variants"]:
        raise ValueError("Runtime aggregate variant closure differs from its payload or attestation")
    _require_aggregate_variant_content(aggregate_value, payload_records, manifests)
    records, values = _adapter_receipt_closure(
        adapter_receipts, aggregate_value["runtimeCompatibilityVersion"],
    )
    if records != attestation_value["adapterReceipts"]:
        raise ValueError("Runtime aggregate adapter receipt closure differs from its attestation")
    return manifests, receipts, values


def _require_aggregate_variant_content(aggregate_value, payload_records, manifests) -> None:
    if payload_records != aggregate_value["variants"]:
        raise ValueError("Runtime aggregate variant closure differs from its payload or attestation")
    if _compatibility(manifests, aggregate_value["runtimeCompatibilityVersion"]) != \
            aggregate_value["compatibility"]:
        raise ValueError("Runtime aggregate compatibility differs from its variants")
    if any(
        manifest["contract"]["digest"] != aggregate_value["contract"]["digest"]
        for manifest in manifests.values()
    ):
        raise ValueError("Runtime aggregate Contract digest differs from its variants")


def verify_runtime_aggregate_presigning_content(
    manifest: Path,
    metadata_receipt: Path,
    *,
    contract_payload: Path,
    contract_metadata_receipt: Path,
    contract_attestation: Path,
    contract_attestation_signature: Path,
    contract_public_key: Path,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    variant_validation_evidence: dict[str, Path],
    adapter_receipts: list[dict[str, Any]],
    adapter_report_files: dict[str, dict[str, Path]],
    runtime_maven_files: list[dict[str, Any]],
    adapter_evidence: dict[str, Path],
    required_trust_domain: str,
    contract_keyring: Path | None = None,
    contract_keys_directory: Path | None = None,
    variant_keyring: Path | None = None,
    variant_keys_directory: Path | None = None,
    adapter_contract_handoffs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Verify original aggregate semantics without its not-yet-created signature.

    Contract and all five variants still require their existing signatures. The
    protected caller supplies private original captures and independently admits
    original CI/release sources before signing-key access. This ordinary dict is
    not signed admission and never rebuilds or publishes product bytes.
    """
    from .aggregate import _verify_runtime_aggregate_semantics, _verified_adapter_contract_upstreams

    contract, contract_receipt, contract_attestation_value = verify_contract_attestation(
        Path(contract_payload), Path(contract_metadata_receipt), Path(contract_attestation),
        Path(contract_attestation_signature), Path(contract_public_key),
        required_trust_domain=required_trust_domain,
        keyring=contract_keyring, keys_directory=contract_keys_directory,
    )
    aggregate, aggregate_receipt, _, _ = _aggregate_bound_inputs(Path(manifest), Path(metadata_receipt))
    payload_records, _, variants, receipts = _variant_inputs(
        variant_bundles=variant_bundles, variant_phase_receipts=variant_phase_receipts,
        variant_attestations=variant_attestations, variant_attestation_signatures=variant_attestation_signatures,
        variant_public_keys=variant_public_keys, variant_validation_evidence=variant_validation_evidence,
        required_variant_trust_domain=required_trust_domain,
        variant_keyring=variant_keyring, variant_keys_directory=variant_keys_directory,
    )
    _require_aggregate_variant_content(aggregate, payload_records, variants)
    _, adapter_values = _adapter_receipt_closure(adapter_receipts, aggregate["runtimeCompatibilityVersion"])
    return _verify_runtime_aggregate_semantics(
        aggregate, aggregate_receipt, contract, contract_receipt, contract_attestation_value,
        variants, receipts, adapter_values, contract_metadata_receipt,
        adapter_report_files, runtime_maven_files, adapter_evidence,
        adapter_contract_upstreams=_verified_adapter_contract_upstreams(
            contract, contract_receipt, contract_attestation_value, adapter_values,
            adapter_contract_handoffs, required_trust_domain=required_trust_domain,
            keyring=contract_keyring, keys_directory=contract_keys_directory,
        ),
    )


def build_runtime_aggregate_attestation(
    manifest: Path,
    metadata_receipt: Path,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    variant_validation_evidence: dict[str, Path],
    adapter_receipts: list[dict[str, Any]],
    signing_metadata: Any,
    private_key: Path,
    public_key: Path,
    output_directory: Path,
    *,
    required_variant_trust_domain: str,
    contract_payload: Path,
    contract_metadata_receipt: Path,
    contract_attestation: Path,
    contract_attestation_signature: Path,
    contract_public_key: Path,
    adapter_report_files: dict[str, dict[str, Path]],
    runtime_maven_files: list[dict[str, Any]],
    adapter_evidence: dict[str, Path],
    keyring: Path | None = None,
    keys_directory: Path | None = None,
    contract_keyring: Path | None = None,
    contract_keys_directory: Path | None = None,
    variant_keyring: Path | None = None,
    variant_keys_directory: Path | None = None,
    adapter_contract_handoffs: dict[str, Path] | None = None,
) -> dict[str, Any]:
    signing = validate_signing_metadata(signing_metadata)
    if signing["trustDomain"] == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Runtime aggregate attestation creation requires a keyring")
        trusted = public_key_for_metadata(
            signing, load_keyring(Path(keyring), Path(keys_directory)), Path(keys_directory),
            allow_retired=False,
        )
        if read_regular_file_bytes(trusted, reject_symlink_parents=True) != \
                read_regular_file_bytes(Path(public_key), reject_symlink_parents=True):
            raise ValueError("Runtime aggregate public key is not the active release key")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Runtime aggregate attestation creation rejects keyring inputs")
    aggregate, _, receipt_bytes, payload = _aggregate_bound_inputs(
        Path(manifest), Path(metadata_receipt),
    )
    _, variant_records, _, _ = _variant_inputs(
        variant_bundles=variant_bundles,
        variant_phase_receipts=variant_phase_receipts,
        variant_attestations=variant_attestations,
        variant_attestation_signatures=variant_attestation_signatures,
        variant_public_keys=variant_public_keys,
        required_variant_trust_domain=required_variant_trust_domain,
        variant_validation_evidence=variant_validation_evidence,
        variant_keyring=variant_keyring,
        variant_keys_directory=variant_keys_directory,
    )
    adapter_records, _ = _adapter_receipt_closure(
        adapter_receipts, aggregate["runtimeCompatibilityVersion"],
    )
    value = validate_runtime_aggregate_attestation({
        "schemaVersion": 1,
        "product": "runtime",
        "runtimeVersion": aggregate["runtimeVersion"],
        "payload": payload,
        "metadataReceiptSha256": sha256_bytes(receipt_bytes),
        "variants": variant_records,
        "adapterReceipts": adapter_records,
        "signing": signing,
    })
    if [
        {key: record[key] for key in ("target", "componentId", "bundleSha256", "manifestSha256")}
        for record in variant_records
    ] != aggregate["variants"]:
        raise ValueError("Runtime aggregate variants differ from the authenticated inputs")
    with tempfile.TemporaryDirectory(prefix="runtime-aggregate-attestation-build-") as temporary:
        prepared = Path(temporary).resolve() / "attestation"
        prepared.mkdir()
        stem = f"codex-agent-runtime-{aggregate['runtimeVersion']}.attestation"
        attestation_path = prepared / f"{stem}.json"
        write_canonical_json(attestation_path, value)
        verify_runtime_aggregate_presigning_content(
            Path(manifest), Path(metadata_receipt),
            contract_payload=Path(contract_payload), contract_metadata_receipt=Path(contract_metadata_receipt),
            contract_attestation=Path(contract_attestation),
            contract_attestation_signature=Path(contract_attestation_signature),
            contract_public_key=Path(contract_public_key), variant_bundles=variant_bundles,
            variant_phase_receipts=variant_phase_receipts, variant_attestations=variant_attestations,
            variant_attestation_signatures=variant_attestation_signatures, variant_public_keys=variant_public_keys,
            variant_validation_evidence=variant_validation_evidence, adapter_receipts=adapter_receipts,
            adapter_report_files=adapter_report_files, runtime_maven_files=runtime_maven_files,
            adapter_evidence=adapter_evidence, required_trust_domain=signing["trustDomain"],
            contract_keyring=contract_keyring, contract_keys_directory=contract_keys_directory,
            variant_keyring=variant_keyring, variant_keys_directory=variant_keys_directory,
            adapter_contract_handoffs=adapter_contract_handoffs,
        )
        signature = sign_manifest(attestation_path, Path(private_key), signing)
        prepared_inventory = regular_file_inventory(prepared)
        verify_runtime_aggregate_artifacts(
            Path(manifest),
            aggregate_metadata_receipt=Path(metadata_receipt),
            aggregate_attestation=attestation_path,
            aggregate_attestation_signature=signature,
            aggregate_public_key=Path(public_key),
            contract_payload=Path(contract_payload),
            contract_metadata_receipt=Path(contract_metadata_receipt),
            contract_attestation=Path(contract_attestation),
            contract_attestation_signature=Path(contract_attestation_signature),
            contract_public_key=Path(contract_public_key),
            variant_bundles=variant_bundles,
            variant_phase_receipts=variant_phase_receipts,
            variant_attestations=variant_attestations,
            variant_attestation_signatures=variant_attestation_signatures,
            variant_public_keys=variant_public_keys,
            variant_validation_evidence=variant_validation_evidence,
            adapter_receipts=adapter_receipts,
            adapter_report_files=adapter_report_files,
            runtime_maven_files=runtime_maven_files,
            adapter_evidence=adapter_evidence,
            required_trust_domain=signing["trustDomain"],
            contract_keyring=contract_keyring,
            contract_keys_directory=contract_keys_directory,
            aggregate_keyring=keyring,
            adapter_contract_handoffs=adapter_contract_handoffs,
            aggregate_keys_directory=keys_directory,
            variant_keyring=variant_keyring,
            variant_keys_directory=variant_keys_directory,
        )
        if regular_file_inventory(prepared) != prepared_inventory:
            raise ValueError("Runtime aggregate attestation changed during verification")
        publish_regular_tree(prepared, Path(output_directory),
                             expected_inventory=prepared_inventory)
    return value
