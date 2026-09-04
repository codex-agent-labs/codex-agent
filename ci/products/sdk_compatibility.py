"""Produce the canonical SDK compatibility declaration from attested products."""

from __future__ import annotations

import argparse
from pathlib import Path
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
from .contract_attestation import verify_contract_attestation
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    read_regular_file_bytes,
    require_exact_keys,
    require_integer,
    require_regular_directory,
    require_string,
    sha256_bytes,
    verified_zip_contents,
)
from .index import (
    _held_output_parent,
    _publish_output,
    _read_parent_file,
    _require_parent_identity,
)
from .runtime_attestation import verify_runtime_variant_attestation
from .runtime_aggregate import verify_runtime_aggregate_attestation
from .receipt import validate_phase_receipt, verify_output_manifest_identity


_JSON_LIMIT = 16 * 1024 * 1024
_MANIFEST_NAME = "runtime-variant-manifest.json"
_LIBRARY_PATHS = {
    spec.classifier.removeprefix("c-abi-"): spec.library_path
    for spec in TARGET_SPECS.values()
}


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
    phase_receipts: dict[str, Path],
    attestation: Path,
    attestation_signature: Path,
    public_key: Path,
    aggregate_attestation_record: dict[str, Any],
    required_trust_domain: str,
    runtime_keyring: Path | None,
    runtime_keys_directory: Path | None,
    runtime_stage_root: Path | None = None,
) -> dict[str, Any]:
    aggregate_record = next(record for record in aggregate["variants"] if record["target"] == target)
    expected_name = (
        f"codex-agent-runtime-variant-{target}-"
        f"{aggregate_record['componentId'].removeprefix('sha256:')}.zip"
    )
    if Path(bundle).name != expected_name:
        raise ValueError(f"Runtime variant bundle identity mismatch: {target}")

    variant, _, variant_attestation = verify_runtime_variant_attestation(
        Path(bundle),
        Path(phase_receipts["binary"]),
        Path(phase_receipts["package"]),
        Path(phase_receipts["validation"]),
        Path(phase_receipts["metadata"]),
        Path(attestation),
        Path(attestation_signature),
        Path(public_key),
        required_trust_domain=required_trust_domain,
        keyring=runtime_keyring,
        keys_directory=runtime_keys_directory,
    )
    attestation_bytes = read_regular_file_bytes(
        Path(attestation), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    if aggregate_attestation_record != {
        "target": target,
        "componentId": variant["componentId"],
        "bundleSha256": variant_attestation["payload"]["sha256"],
        "manifestSha256": variant_attestation["manifestSha256"],
        "variantAttestationSha256": sha256_bytes(attestation_bytes),
        "phaseReceipts": dict(variant_attestation["phaseReceipts"]),
    }:
        raise ValueError(
            f"Runtime variant differs from the authenticated aggregate attestation: {target}"
        )
    if runtime_stage_root is not None:
        _verify_runtime_stages(runtime_stage_root, target, phase_receipts, variant_attestation)
    c_abi = next(
        artifact for artifact in variant["innerArtifacts"] if artifact["role"] == "c-abi-archive"
    )
    records, contents, bundle_identity = verified_zip_contents(
        Path(bundle),
        **RUNTIME_VARIANT_ZIP_LIMITS,
        retained_paths={_MANIFEST_NAME, c_abi["path"]},
        max_retained_bytes=RUNTIME_VARIANT_ZIP_LIMITS["max_entry_bytes"] + _JSON_LIMIT,
        canonical_stored=True,
    )
    if bundle_identity["sha256"] != aggregate_record["bundleSha256"]:
        raise ValueError(f"Runtime variant bundle digest mismatch: {target}")
    if set(contents) != {_MANIFEST_NAME, c_abi["path"]}:
        raise ValueError(f"Runtime variant bundle lacks deterministic inputs: {target}")
    manifest_bytes = contents[_MANIFEST_NAME]
    if sha256_bytes(manifest_bytes) != aggregate_record["manifestSha256"]:
        raise ValueError(f"Runtime variant manifest digest mismatch: {target}")
    if validate_runtime_variant(load_canonical_json_bytes(manifest_bytes)) != variant:
        raise ValueError(f"Runtime variant changed after attestation verification: {target}")

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
    if set(inventory) != {_MANIFEST_NAME} | set(declared) or any(
        inventory[path] != record for path, record in declared.items()
    ):
        raise ValueError(f"Runtime variant bundle inventory mismatch: {target}")
    c_abi_bytes = contents[c_abi["path"]]
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


def _verify_runtime_stages(
    root: Path,
    target: str,
    phase_receipts: dict[str, Path],
    authenticated_attestation: dict[str, Any],
) -> None:
    """Bind imported raw stages to the already-authenticated original receipts."""
    for phase in ("package", "validation"):
        receipt_bytes = read_regular_file_bytes(
            phase_receipts[phase], max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
        )
        if sha256_bytes(receipt_bytes) != authenticated_attestation["phaseReceipts"][phase]:
            raise ValueError(f"Runtime original {phase} receipt changed: {target}")
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if (receipt["product"], receipt["component"], receipt["phase"], receipt["target"]) != (
            "runtime", target, phase, target,
        ):
            raise ValueError(f"Runtime original {phase} receipt identity mismatch: {target}")
        stage = root / target / phase
        manifest = verify_output_manifest_identity(
            stage, "runtime", target, phase, target, receipt["productVersion"],
        )
        if manifest["outputs"] != receipt["outputs"]:
            raise ValueError(f"Runtime {phase} stage differs from authenticated receipt: {target}")
        if phase == "validation":
            spec = next(spec for spec in TARGET_SPECS.values()
                        if spec.classifier.removeprefix("c-abi-") == target)
            proof_path = f"outputs/c-abi/c-abi-package-{target}.json"
            if not any(output["kind"] == "c-abi" and output["relativePath"] == proof_path
                       for output in receipt["outputs"]):
                raise ValueError(f"Runtime C ABI evidence output identity mismatch: {target}")
            # Raw C ABI evidence retains its original legacy encoding. Its exact
            # bytes are receipt-bound; portable-verify checks its full semantics.
            proof = load_json_bytes(read_regular_file_bytes(
                stage / proof_path,
                max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
            ))
            if (type(proof) is not dict
                    or proof.get("producerCommit") != receipt["producer"]["commit"]
                    or proof.get("producerTree") != receipt["producer"]["tree"]
                    or proof.get("target") != spec.target):
                raise ValueError(f"Runtime C ABI evidence original producer mismatch: {target}")


def produce_sdk_compatibility(
    *,
    sdk_version: str,
    compatible_release_range: str,
    compatible_runtime_compatibility_range: str,
    contract_payload: Path,
    contract_metadata_receipt: Path,
    contract_attestation: Path,
    contract_attestation_signature: Path,
    contract_public_key: Path,
    runtime_manifest: Path,
    runtime_metadata_receipt: Path,
    runtime_attestation: Path,
    runtime_attestation_signature: Path,
    runtime_public_key: Path,
    variant_bundles: dict[str, Path],
    variant_phase_receipts: dict[str, dict[str, Path]],
    variant_attestations: dict[str, Path],
    variant_attestation_signatures: dict[str, Path],
    variant_public_keys: dict[str, Path],
    required_trust_domain: str,
    output: Path,
    contract_keyring: Path | None = None,
    contract_keys_directory: Path | None = None,
    runtime_keyring: Path | None = None,
    runtime_keys_directory: Path | None = None,
    runtime_stage_root: Path | None = None,
) -> dict[str, Any]:
    """Verify the selected embedded products and emit one canonical declaration."""
    if runtime_stage_root is not None:
        runtime_stage_root = require_regular_directory(runtime_stage_root, "Runtime stage root")
        if {entry.name for entry in runtime_stage_root.iterdir()} != set(RUNTIME_TARGETS):
            raise ValueError("Runtime stage root requires exactly five targets")
        for target in RUNTIME_TARGETS:
            stage = require_regular_directory(runtime_stage_root / target, "Runtime target stage")
            if {entry.name for entry in stage.iterdir()} != {"package", "validation"}:
                raise ValueError(f"Runtime stage phase inventory mismatch: {target}")
    if required_trust_domain not in {"development", "release"}:
        raise ValueError("SDK compatibility trust domain is invalid")
    optional_pairs = (
        (contract_keyring, contract_keys_directory, "Contract"),
        (runtime_keyring, runtime_keys_directory, "Runtime"),
    )
    if any((first is None) != (second is None) for first, second, _ in optional_pairs):
        raise ValueError("SDK compatibility keyring and keys-directory inputs must be paired")
    if required_trust_domain == "release" and any(
        first is None for first, _, _ in optional_pairs
    ):
        raise ValueError("Release SDK compatibility requires Contract and Runtime keyrings")
    if required_trust_domain == "development" and any(
        first is not None for first, _, _ in optional_pairs
    ):
        raise ValueError("Development SDK compatibility rejects release keyring inputs")

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
    aggregate, _, aggregate_attestation = verify_runtime_aggregate_attestation(
        Path(runtime_manifest),
        Path(runtime_metadata_receipt),
        Path(runtime_attestation),
        Path(runtime_attestation_signature),
        Path(runtime_public_key),
        required_trust_domain=required_trust_domain,
        keyring=runtime_keyring,
        keys_directory=runtime_keys_directory,
    )
    aggregate_bytes = read_regular_file_bytes(
        Path(runtime_manifest), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    if aggregate_bytes != canonical_json_bytes(aggregate) or \
            validate_runtime_aggregate(load_canonical_json_bytes(aggregate_bytes)) != aggregate:
        raise ValueError("Runtime aggregate changed after attestation verification")
    if Path(runtime_manifest).name != f"codex-agent-runtime-{aggregate['runtimeVersion']}-manifest.json":
        raise ValueError("Runtime aggregate manifest identity mismatch")
    if aggregate["contract"] != {
        "version": contract["contractVersion"], "digest": contract["contractDigest"],
    }:
        raise ValueError("Runtime aggregate does not reference the authenticated Contract")
    aggregate_attestation_records = {
        record["target"]: record for record in aggregate_attestation["variants"]
    }
    for mapping, label in (
        (variant_bundles, "Runtime variant bundles"),
        (variant_phase_receipts, "Runtime variant phase receipts"),
        (variant_attestations, "Runtime variant attestations"),
        (variant_attestation_signatures, "Runtime variant attestation signatures"),
        (variant_public_keys, "Runtime variant public keys"),
    ):
        if type(mapping) is not dict or set(mapping) != set(RUNTIME_TARGETS):
            raise ValueError(f"{label} must contain exactly five Runtime targets")
    for target, receipts in variant_phase_receipts.items():
        if type(receipts) is not dict or set(receipts) != {
            "binary", "package", "validation", "metadata",
        }:
            raise ValueError(
                f"Runtime variant phase receipts must contain exactly four phases: {target}"
            )

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
                    phase_receipts=variant_phase_receipts[target],
                    attestation=Path(variant_attestations[target]),
                    attestation_signature=Path(variant_attestation_signatures[target]),
                    public_key=Path(variant_public_keys[target]),
                    aggregate_attestation_record=aggregate_attestation_records[target],
                    required_trust_domain=required_trust_domain,
                    runtime_keyring=runtime_keyring,
                    runtime_keys_directory=runtime_keys_directory,
                    runtime_stage_root=runtime_stage_root,
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
    contents = canonical_json_bytes(validated)
    with _held_output_parent(destination.parent) as (descriptor, parent):
        if not _publish_output(
            contents, descriptor, parent, destination.name, max_bytes=_JSON_LIMIT,
        ):
            raise ValueError("SDK compatibility was concurrently published")
        if _read_parent_file(
            descriptor, parent, destination.name, max_bytes=_JSON_LIMIT,
        ) != contents:
            raise ValueError("Published SDK compatibility changed")
        _require_parent_identity(descriptor, parent)
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


def _phase_path_mapping(
    value: Any, label: str, request_directory: Path,
) -> dict[str, dict[str, Path]]:
    mapping = require_exact_keys(value, RUNTIME_TARGETS, label)
    phases = {"binary", "package", "validation", "metadata"}
    return {
        target: {
            phase: _request_path(
                receipts[phase], f"{label}.{target}.{phase}", request_directory,
            )
            for phase in sorted(phases)
        }
        for target in sorted(RUNTIME_TARGETS)
        for receipts in [require_exact_keys(mapping[target], phases, f"{label}.{target}")]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.sdk_compatibility")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--runtime-stage-root")
    arguments = parser.parse_args(argv)
    try:
        request_path = Path(arguments.request)
        raw_request = load_canonical_json_bytes(read_regular_file_bytes(
                request_path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
            ))
        optional_fields = {
            "contractKeyring", "contractKeysDirectory",
            "runtimeKeyring", "runtimeKeysDirectory",
        }
        present_optional_fields = (
            set(raw_request) & optional_fields if type(raw_request) is dict else set()
        )
        request = require_exact_keys(
            raw_request,
            {
                "schemaVersion",
                "sdkVersion",
                "compatibleReleaseRange",
                "compatibleRuntimeCompatibilityRange",
                "contractPayload",
                "contractMetadataReceipt",
                "contractAttestation",
                "contractAttestationSignature",
                "contractPublicKey",
                "runtimeManifest",
                "runtimeMetadataReceipt",
                "runtimeAttestation",
                "runtimeAttestationSignature",
                "runtimePublicKey",
                "variantBundles",
                "variantPhaseReceipts",
                "variantAttestations",
                "variantAttestationSignatures",
                "variantPublicKeys",
                "requiredTrustDomain",
            } | present_optional_fields,
            "SDK compatibility request",
        )
        for pair, label in (
            ({"contractKeyring", "contractKeysDirectory"}, "Contract"),
            ({"runtimeKeyring", "runtimeKeysDirectory"}, "Runtime"),
        ):
            if present_optional_fields & pair not in (set(), pair):
                raise ValueError(
                    f"SDK compatibility request {label} keyring and keys directory "
                    "must be supplied together"
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
            contract_payload=_request_path(
                request["contractPayload"],
                "SDK compatibility request.contractPayload",
                request_directory,
            ),
            contract_metadata_receipt=_request_path(
                request["contractMetadataReceipt"],
                "SDK compatibility request.contractMetadataReceipt",
                request_directory,
            ),
            contract_attestation=_request_path(
                request["contractAttestation"],
                "SDK compatibility request.contractAttestation",
                request_directory,
            ),
            contract_attestation_signature=_request_path(
                request["contractAttestationSignature"],
                "SDK compatibility request.contractAttestationSignature",
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
            runtime_metadata_receipt=_request_path(
                request["runtimeMetadataReceipt"],
                "SDK compatibility request.runtimeMetadataReceipt",
                request_directory,
            ),
            runtime_attestation=_request_path(
                request["runtimeAttestation"],
                "SDK compatibility request.runtimeAttestation",
                request_directory,
            ),
            runtime_attestation_signature=_request_path(
                request["runtimeAttestationSignature"],
                "SDK compatibility request.runtimeAttestationSignature",
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
            variant_phase_receipts=_phase_path_mapping(
                request["variantPhaseReceipts"],
                "SDK compatibility request.variantPhaseReceipts",
                request_directory,
            ),
            variant_attestations=_path_mapping(
                request["variantAttestations"],
                "SDK compatibility request.variantAttestations",
                request_directory,
            ),
            variant_attestation_signatures=_path_mapping(
                request["variantAttestationSignatures"],
                "SDK compatibility request.variantAttestationSignatures",
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
            runtime_stage_root=(Path(arguments.runtime_stage_root)
                                if arguments.runtime_stage_root else None),
            contract_keyring=(
                _request_path(
                    request["contractKeyring"],
                    "SDK compatibility request.contractKeyring",
                    request_directory,
                )
                if "contractKeyring" in request else None
            ),
            contract_keys_directory=(
                _request_path(
                    request["contractKeysDirectory"],
                    "SDK compatibility request.contractKeysDirectory",
                    request_directory,
                )
                if "contractKeysDirectory" in request else None
            ),
            runtime_keyring=(
                _request_path(
                    request["runtimeKeyring"],
                    "SDK compatibility request.runtimeKeyring",
                    request_directory,
                )
                if "runtimeKeyring" in request else None
            ),
            runtime_keys_directory=(
                _request_path(
                    request["runtimeKeysDirectory"],
                    "SDK compatibility request.runtimeKeysDirectory",
                    request_directory,
                )
                if "runtimeKeysDirectory" in request else None
            ),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
