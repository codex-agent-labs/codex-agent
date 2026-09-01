"""Produce the canonical SDK compatibility declaration from signed products."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import tempfile
from typing import Any

from .aggregate import (
    RUNTIME_TARGETS,
    RUNTIME_VARIANT_ZIP_LIMITS,
    validate_runtime_aggregate,
    validate_runtime_variant,
    validate_sdk_compatibility,
)
from .c_abi import TARGET_SPECS
from .contract_model import validate_contract_manifest
from .inventory import (
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_exact_keys,
    require_integer,
    require_regular_directory,
    require_string,
    sha256_bytes,
    verified_zip_contents,
    write_canonical_json,
)
from .signatures import verify_manifest_signature


_JSON_LIMIT = 16 * 1024 * 1024
_SIGNATURE_LIMIT = 1024 * 1024
_MANIFEST_NAME = "runtime-variant-manifest.json"
_SIGNATURE_NAME = "runtime-variant-manifest.sig"
_LIBRARY_PATHS = {
    spec.classifier.removeprefix("c-abi-"): spec.library_path
    for spec in TARGET_SPECS.values()
}


def _authenticated_manifest(
    manifest: Path,
    signature: Path,
    public_key: Path,
    validator: Any,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    manifest_bytes = read_regular_file_bytes(
        Path(manifest), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    public_key_bytes = read_regular_file_bytes(
        Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
    )
    value = validator(load_canonical_json_bytes(manifest_bytes))
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-compatibility-") as temporary:
        root = Path(temporary).resolve()
        manifest_snapshot = root / "manifest.json"
        signature_snapshot = root / "manifest.sig"
        public_key_snapshot = root / "public-key.pub"
        manifest_snapshot.write_bytes(manifest_bytes)
        signature_snapshot.write_bytes(signature_bytes)
        public_key_snapshot.write_bytes(public_key_bytes)
        verify_manifest_signature(
            manifest_snapshot, signature_snapshot, public_key_snapshot, value["signing"],
        )
    if not manifest_bytes:
        raise ValueError(f"{label} must not be empty")
    return value, manifest_bytes


def _version_in_range(version: str, expression: str) -> bool:
    lower, upper = expression.split(" ")
    parsed = tuple(int(part) for part in version.split("-", 1)[0].split("."))
    return tuple(int(part) for part in lower.removeprefix(">=").split(".")) <= parsed < tuple(
        int(part) for part in upper.removeprefix("<").split(".")
    )


def _variant_record(
    *,
    target: str,
    aggregate: dict[str, Any],
    contract: dict[str, Any],
    bundle: Path,
    public_key: Path,
    required_trust_domain: str,
) -> dict[str, Any]:
    aggregate_record = next(record for record in aggregate["variants"] if record["target"] == target)
    expected_name = (
        f"codex-agent-runtime-variant-{target}-"
        f"{aggregate_record['componentId'].removeprefix('sha256:')}.zip"
    )
    if Path(bundle).name != expected_name:
        raise ValueError(f"Runtime variant bundle identity mismatch: {target}")

    records, contents, bundle_identity = verified_zip_contents(
        Path(bundle),
        **RUNTIME_VARIANT_ZIP_LIMITS,
        retained_paths={_MANIFEST_NAME, _SIGNATURE_NAME},
        max_retained_bytes=2 * 1024 * 1024,
    )
    if bundle_identity["sha256"] != aggregate_record["bundleSha256"]:
        raise ValueError(f"Runtime variant bundle digest mismatch: {target}")
    if set(contents) != {_MANIFEST_NAME, _SIGNATURE_NAME}:
        raise ValueError(f"Runtime variant bundle lacks signed manifest: {target}")
    manifest_bytes = contents[_MANIFEST_NAME]
    if sha256_bytes(manifest_bytes) != aggregate_record["manifestSha256"]:
        raise ValueError(f"Runtime variant manifest digest mismatch: {target}")
    variant = validate_runtime_variant(load_canonical_json_bytes(manifest_bytes))
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-variant-") as temporary:
        root = Path(temporary).resolve()
        manifest_snapshot = root / _MANIFEST_NAME
        signature_snapshot = root / _SIGNATURE_NAME
        public_key_snapshot = root / "public-key.pub"
        manifest_snapshot.write_bytes(manifest_bytes)
        signature_snapshot.write_bytes(contents[_SIGNATURE_NAME])
        public_key_snapshot.write_bytes(read_regular_file_bytes(
            Path(public_key), max_bytes=_SIGNATURE_LIMIT, reject_symlink_parents=True,
        ))
        verify_manifest_signature(
            manifest_snapshot, signature_snapshot, public_key_snapshot, variant["signing"],
        )
    if variant["signing"]["trustDomain"] != required_trust_domain:
        raise ValueError(f"Runtime variant trust domain mismatch: {target}")

    expected_c_abi = {
        "version": aggregate["compatibility"]["cAbiVersion"],
        "minimumCompatibleVersion": aggregate["compatibility"]["minimumCAbiVersion"],
        "identitySchemaVersion": aggregate["compatibility"]["identitySchema"],
        "headerSha256": aggregate["compatibility"]["headerSha256"],
        "symbolSetSha256": aggregate["compatibility"]["symbolSetSha256"],
        "symbolCount": aggregate["compatibility"]["symbolCount"],
    }
    if (
        variant["target"] != target
        or variant["componentId"] != aggregate_record["componentId"]
        or variant["runtimeCompatibilityVersion"] != aggregate["runtimeCompatibilityVersion"]
        or variant["contract"] != {
            "digest": contract["contractDigest"],
            "componentDigest": contract["components"][target]["sha256"],
        }
        or variant["cAbi"] != expected_c_abi
        or variant["appServer"]["version"] != aggregate["compatibility"]["appServerVersion"]
        or variant["appServer"]["releaseTag"] != aggregate["compatibility"]["appServerReleaseTag"]
        or variant["toolchainProfile"] != {
            "id": target,
            "digest": aggregate["compatibility"]["toolchainProfileDigests"][target],
        }
    ):
        raise ValueError(f"Runtime variant disagrees with authenticated products: {target}")

    declared = {
        artifact["path"]: {
            "relativePath": artifact["path"],
            "bytes": artifact["bytes"],
            "sha256": artifact["sha256"],
        }
        for artifact in variant["innerArtifacts"]
    }
    inventory = {record["relativePath"]: record for record in records}
    if set(inventory) != {_MANIFEST_NAME, _SIGNATURE_NAME} | set(declared) or any(
        inventory[path] != record for path, record in declared.items()
    ):
        raise ValueError(f"Runtime variant bundle inventory mismatch: {target}")
    c_abi = next(
        artifact for artifact in variant["innerArtifacts"] if artifact["role"] == "c-abi-archive"
    )
    repeated_records, repeated_contents, repeated_identity = verified_zip_contents(
        Path(bundle),
        **RUNTIME_VARIANT_ZIP_LIMITS,
        retained_paths={c_abi["path"]},
        max_retained_bytes=RUNTIME_VARIANT_ZIP_LIMITS["max_entry_bytes"],
    )
    if repeated_records != records or repeated_identity != bundle_identity:
        raise ValueError(f"Runtime variant bundle changed during verification: {target}")
    c_abi_bytes = repeated_contents[c_abi["path"]]
    if len(c_abi_bytes) != c_abi["bytes"] or sha256_bytes(c_abi_bytes) != c_abi["sha256"]:
        raise ValueError(f"Runtime C ABI archive digest mismatch: {target}")
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-c-abi-") as temporary:
        archive = Path(temporary) / "c-abi.zip"
        archive.write_bytes(c_abi_bytes)
        _, library_contents, _ = verified_zip_contents(
            archive,
            **RUNTIME_VARIANT_ZIP_LIMITS,
            retained_paths={_LIBRARY_PATHS[target]},
            max_retained_bytes=RUNTIME_VARIANT_ZIP_LIMITS["max_entry_bytes"],
        )
    if set(library_contents) != {_LIBRARY_PATHS[target]}:
        raise ValueError(f"Runtime C ABI archive lacks its target library: {target}")
    return {
        "target": target,
        "componentId": variant["componentId"],
        "bundleSha256": bundle_identity["sha256"],
        "manifestSha256": sha256_bytes(manifest_bytes),
        "runtimeLibrarySha256": sha256_bytes(library_contents[_LIBRARY_PATHS[target]]),
    }


def produce_sdk_compatibility(
    *,
    sdk_version: str,
    compatible_release_range: str,
    compatible_runtime_compatibility_range: str,
    contract_manifest: Path,
    contract_signature: Path,
    contract_public_key: Path,
    runtime_manifest: Path,
    runtime_signature: Path,
    runtime_public_key: Path,
    variant_bundles: dict[str, Path],
    variant_public_keys: dict[str, Path],
    required_trust_domain: str,
    output: Path,
) -> dict[str, Any]:
    """Verify the selected embedded products and emit one canonical declaration."""
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("SDK compatibility trust domain is invalid")
    if Path(contract_manifest).name != "contract-manifest.json" or Path(contract_signature).name != \
            "contract-manifest.sig":
        raise ValueError("Contract manifest or signature identity mismatch")
    contract, _ = _authenticated_manifest(
        Path(contract_manifest), Path(contract_signature), Path(contract_public_key),
        validate_contract_manifest, "Contract manifest",
    )
    aggregate, aggregate_bytes = _authenticated_manifest(
        Path(runtime_manifest), Path(runtime_signature), Path(runtime_public_key),
        validate_runtime_aggregate, "Runtime aggregate",
    )
    if Path(runtime_manifest).name != f"codex-agent-runtime-{aggregate['runtimeVersion']}-manifest.json" or \
            Path(runtime_signature).name != f"codex-agent-runtime-{aggregate['runtimeVersion']}-manifest.sig":
        raise ValueError("Runtime aggregate manifest or signature identity mismatch")
    if contract["signing"]["trustDomain"] != required_trust_domain or \
            aggregate["signing"]["trustDomain"] != required_trust_domain:
        raise ValueError("SDK compatibility input trust domain mismatch")
    if aggregate["contract"] != {
        "version": contract["contractVersion"], "digest": contract["contractDigest"],
    }:
        raise ValueError("Runtime aggregate does not reference the authenticated Contract")
    for mapping, label in (
        (variant_bundles, "Runtime variant bundles"),
        (variant_public_keys, "Runtime variant public keys"),
    ):
        if type(mapping) is not dict or set(mapping) != set(RUNTIME_TARGETS):
            raise ValueError(f"{label} must contain exactly five Runtime targets")

    current_abi = tuple(int(part) for part in aggregate["compatibility"]["cAbiVersion"].split("."))
    compatibility = {
        "schemaVersion": 1,
        "sdkVersion": sdk_version,
        "contract": {
            "version": contract["contractVersion"],
            "digest": contract["contractDigest"],
        },
        "runtime": {
            "compatibleReleaseRange": compatible_release_range,
            "compatibleRuntimeCompatibilityRange": compatible_runtime_compatibility_range,
            "requiredIdentitySchema": aggregate["compatibility"]["identitySchema"],
            "requiredContractDigest": contract["contractDigest"],
            "requiredAbiMajor": current_abi[0],
            "minimumAbiMinor": current_abi[1],
            "defaultRuntimeVersion": aggregate["runtimeVersion"],
            "defaultManifestSha256": sha256_bytes(aggregate_bytes),
            "embeddedVariants": [
                _variant_record(
                    target=target,
                    aggregate=aggregate,
                    contract=contract,
                    bundle=Path(variant_bundles[target]),
                    public_key=Path(variant_public_keys[target]),
                    required_trust_domain=required_trust_domain,
                )
                for target in sorted(RUNTIME_TARGETS)
            ],
        },
        "platformRuntime": {
            "android": {"owner": "sdk", "desktopRuntimeApplicable": False},
            "ios": {"owner": "sdk", "desktopRuntimeApplicable": False},
        },
    }
    validated = validate_sdk_compatibility(compatibility)
    if not _version_in_range(
        aggregate["runtimeCompatibilityVersion"], compatible_runtime_compatibility_range,
    ):
        raise ValueError("Default Runtime compatibility version is outside its compatible range")

    destination = Path(output)
    if destination.name != "sdk-compatibility.json":
        raise ValueError("SDK compatibility output must be named sdk-compatibility.json")
    parent = require_regular_directory(destination.parent, "SDK compatibility output directory")
    for ancestor in (parent, *parent.parents):
        metadata = ancestor.lstat()
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse:
            raise ValueError("SDK compatibility output directory has an unsafe parent")
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK compatibility output already exists")
    try:
        write_canonical_json(destination, validated)
        if validate_sdk_compatibility(load_canonical_json_bytes(
            read_regular_file_bytes(destination, reject_symlink_parents=True),
        )) != validated:
            raise ValueError("Stored SDK compatibility differs from its validated value")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return validated


def _request_path(value: Any, label: str, request_directory: Path) -> Path:
    text = require_string(value, label)
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
        raise ValueError(f"{label} contains a control character")
    path = Path(text)
    if ".." in path.parts:
        raise ValueError(f"{label} contains parent traversal")
    return path if path.is_absolute() else request_directory / path


def _path_mapping(value: Any, label: str, request_directory: Path) -> dict[str, Path]:
    mapping = require_exact_keys(value, RUNTIME_TARGETS, label)
    return {
        target: _request_path(mapping[target], f"{label}.{target}", request_directory)
        for target in sorted(RUNTIME_TARGETS)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.sdk_compatibility")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args(argv)
    try:
        request_path = Path(arguments.request)
        request = require_exact_keys(
            load_canonical_json_bytes(read_regular_file_bytes(
                request_path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
            )),
            {
                "schemaVersion",
                "sdkVersion",
                "compatibleReleaseRange",
                "compatibleRuntimeCompatibilityRange",
                "contractManifest",
                "contractSignature",
                "contractPublicKey",
                "runtimeManifest",
                "runtimeSignature",
                "runtimePublicKey",
                "variantBundles",
                "variantPublicKeys",
                "requiredTrustDomain",
            },
            "SDK compatibility request",
        )
        if require_integer(
            request["schemaVersion"], "SDK compatibility request.schemaVersion", 1,
        ) != 1:
            raise ValueError("Unsupported SDK compatibility request schemaVersion")
        request_directory = request_path.parent
        produce_sdk_compatibility(
            sdk_version=require_string(
                request["sdkVersion"], "SDK compatibility request.sdkVersion",
            ),
            compatible_release_range=require_string(
                request["compatibleReleaseRange"],
                "SDK compatibility request.compatibleReleaseRange",
            ),
            compatible_runtime_compatibility_range=require_string(
                request["compatibleRuntimeCompatibilityRange"],
                "SDK compatibility request.compatibleRuntimeCompatibilityRange",
            ),
            contract_manifest=_request_path(
                request["contractManifest"],
                "SDK compatibility request.contractManifest",
                request_directory,
            ),
            contract_signature=_request_path(
                request["contractSignature"],
                "SDK compatibility request.contractSignature",
                request_directory,
            ),
            contract_public_key=_request_path(
                request["contractPublicKey"],
                "SDK compatibility request.contractPublicKey",
                request_directory,
            ),
            runtime_manifest=_request_path(
                request["runtimeManifest"],
                "SDK compatibility request.runtimeManifest",
                request_directory,
            ),
            runtime_signature=_request_path(
                request["runtimeSignature"],
                "SDK compatibility request.runtimeSignature",
                request_directory,
            ),
            runtime_public_key=_request_path(
                request["runtimePublicKey"],
                "SDK compatibility request.runtimePublicKey",
                request_directory,
            ),
            variant_bundles=_path_mapping(
                request["variantBundles"],
                "SDK compatibility request.variantBundles",
                request_directory,
            ),
            variant_public_keys=_path_mapping(
                request["variantPublicKeys"],
                "SDK compatibility request.variantPublicKeys",
                request_directory,
            ),
            required_trust_domain=require_string(
                request["requiredTrustDomain"],
                "SDK compatibility request.requiredTrustDomain",
            ),
            output=Path(arguments.output),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
