"""Deterministic producer for one reusable Desktop Runtime variant bundle."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import tempfile
from typing import Any
import zipfile

from .aggregate import RUNTIME_VARIANT_ZIP_LIMITS, validate_runtime_variant
from .inventory import (
    canonical_json_bytes,
    load_canonical_json_bytes,
    read_regular_file_bytes,
    require_regular_directory,
    sha256_bytes,
    sha256_file,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import build_key_payload, output_inventory_digest, validate_phase_receipt
from .runtime_attestation import (
    derive_desktop_validation_projection,
    derive_runtime_component_attestation,
)
from .runtime_evidence import inspect_classifier, read_distribution_manifest
from .runtime_identity import validate_runtime_identity
from .signatures import (
    sign_manifest,
    validate_signing_metadata,
    verify_manifest_signature,
)


_JSON_LIMIT = 16 * 1024 * 1024
_EVIDENCE_LIMIT = 64 * 1024 * 1024
_MANIFEST_NAME = "runtime-variant-manifest.json"
_SIGNATURE_NAME = "runtime-variant-manifest.sig"
_RECEIPT_PATHS = {
    "binary": "evidence/binary-phase.json",
    "package": "evidence/package-phase.json",
    "validation": "evidence/validation-phase.json",
}


def _read_input(path: Path, label: str, *, max_bytes: int) -> bytes:
    contents = read_regular_file_bytes(
        Path(path), max_bytes=max_bytes, reject_symlink_parents=True,
    )
    if not contents:
        raise ValueError(f"{label} must not be empty")
    return contents


def _read_receipt(path: Path, phase: str) -> tuple[dict[str, Any], bytes]:
    contents = _read_input(Path(path), f"Runtime {phase} receipt", max_bytes=_JSON_LIMIT)
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _receipt_reference(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": receipt["product"],
        "component": receipt["component"],
        "phase": receipt["phase"],
        "target": receipt["target"],
        "buildKey": receipt["buildKey"],
        "outputsDigest": output_inventory_digest(receipt["outputs"]),
    }


def _phase_evidence(
    receipt: dict[str, Any], *, validation_evidence_digest: str | None = None,
) -> dict[str, Any]:
    payload = build_key_payload(
        product=receipt["product"],
        component=receipt["component"],
        phase=receipt["phase"],
        target=receipt["target"],
        inputs=receipt["inputs"],
    )
    result = {
        **payload,
        "buildKey": receipt["buildKey"],
    }
    if receipt["phase"] == "validation":
        if validation_evidence_digest is None:
            raise ValueError("Runtime validation phase requires deterministic evidence")
        result["validationEvidenceDigest"] = validation_evidence_digest
    else:
        result["outputInventoryDigest"] = output_inventory_digest(receipt["outputs"])
    return result


def _verified_zip_input(path: Path, label: str) -> tuple[bytes, dict[str, Any], list[dict[str, Any]]]:
    records, _, identity = verified_zip_contents(
        Path(path),
        **RUNTIME_VARIANT_ZIP_LIMITS,
        retained_paths=(),
        max_retained_bytes=0,
    )
    if not records:
        raise ValueError(f"{label} must contain at least one regular member")
    contents = _read_input(
        Path(path), label, max_bytes=RUNTIME_VARIANT_ZIP_LIMITS["max_archive_bytes"],
    )
    if len(contents) != identity["bytes"] or sha256_bytes(contents) != identity["sha256"]:
        raise ValueError(f"{label} changed after ZIP verification")
    return contents, identity, records


def _exact_output(
    receipt: dict[str, Any],
    identity: dict[str, Any],
    prefix: str,
    kind: str,
    label: str,
) -> dict[str, Any]:
    matches = [
        output for output in receipt["outputs"]
        if output["relativePath"].startswith(prefix)
        and output["kind"] == kind
        and output["bytes"] == identity["bytes"]
        and output["sha256"] == identity["sha256"]
    ]
    if len(matches) != 1:
        raise ValueError(f"{label} is not one exact package receipt output")
    return matches[0]


def _artifact(path: str, role: str, contents: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "role": role,
        "bytes": len(contents),
        "sha256": sha256_bytes(contents),
    }


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def _safe_output_directory(path: Path) -> Path:
    root = require_regular_directory(
        Path(os.path.abspath(path)), "Runtime variant output directory",
    )
    for ancestor in (root, *root.parents):
        metadata = ancestor.lstat()
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Runtime variant output directory has an unsafe parent")
    return root


def produce_runtime_variant(
    *,
    identity_envelope: Any,
    binary_receipt: Path,
    package_receipt: Path,
    validation_receipt: Path,
    c_abi_archive: Path,
    app_server_archive: Path,
    validation_evidence: Path,
    distribution_manifest: Path,
    signing_metadata: Any,
    private_key: Path,
    public_key: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Validate immutable phase outputs and emit one signed component-addressed ZIP."""
    identity = validate_runtime_identity(identity_envelope)
    signing = validate_signing_metadata(signing_metadata)
    target = identity["target"]
    output_root = _safe_output_directory(Path(output_directory))
    if any(output_root.iterdir()):
        raise ValueError("Runtime variant output directory must be empty")

    receipt_values: dict[str, dict[str, Any]] = {}
    for phase, path in (
        ("binary", binary_receipt),
        ("package", package_receipt),
        ("validation", validation_receipt),
    ):
        receipt_values[phase], _ = _read_receipt(Path(path), phase)

    source_version = receipt_values["binary"]["productVersion"]
    for phase in ("binary", "package", "validation"):
        receipt = receipt_values[phase]
        if (
            receipt["product"] != "runtime"
            or receipt["component"] != target
            or receipt["phase"] != phase
            or receipt["target"] != target
            or receipt["productVersion"] != source_version
            or receipt["inputs"]["versionIdentity"] != identity["runtimeCompatibilityVersion"]
            or receipt["trustDomain"] != signing["trustDomain"]
        ):
            raise ValueError(f"Runtime {phase} receipt identity does not match the Runtime variant")

    binary = receipt_values["binary"]
    package = receipt_values["package"]
    validation = receipt_values["validation"]
    contract_upstream = binary["inputs"]["upstreamArtifacts"]
    if len(contract_upstream) != 1 or (
        contract_upstream[0]["product"],
        contract_upstream[0]["component"],
        contract_upstream[0]["phase"],
        contract_upstream[0]["target"],
    ) != ("contract", "contract", "metadata", "common"):
        raise ValueError("Runtime binary receipt must have exactly one Contract metadata input")
    projection = contract_upstream[0].get("contractProjection")
    component_digests = {} if projection is None else {
        record["component"]: record["sha256"] for record in projection["componentDigests"]
    }
    if projection is None or (
        projection["contractDigest"] != identity["contract"]["digest"]
        or component_digests.get(target) != identity["contract"]["componentDigest"]
    ):
        raise ValueError("Runtime binary receipt Contract projection does not match Runtime identity")
    if binary["buildKey"] != identity["binaryBuildKey"]:
        raise ValueError("Runtime binary receipt build key does not match Runtime identity")
    if binary["inputs"]["toolchainProfileDigest"] != identity["toolchainProfile"]["digest"]:
        raise ValueError("Runtime binary receipt toolchain does not match Runtime identity")
    if package["inputs"]["upstreamArtifacts"] != [_receipt_reference(binary)]:
        raise ValueError("Runtime package receipt does not link exactly to the binary receipt")
    if validation["inputs"]["upstreamArtifacts"] != [_receipt_reference(package)]:
        raise ValueError("Runtime validation receipt does not link exactly to the package receipt")

    c_abi_bytes, c_abi_identity, c_abi_members = _verified_zip_input(
        Path(c_abi_archive), "Runtime C ABI archive",
    )
    app_server_bytes, app_server_identity, app_server_members = _verified_zip_input(
        Path(app_server_archive), "Runtime app-server archive",
    )
    if sum(
        member["relativePath"] == "include/codex_agent.h"
        and member["sha256"] == identity["cAbi"]["headerSha256"]
        for member in c_abi_members
    ) != 1:
        raise ValueError("Runtime C ABI archive does not contain the exact declared header")
    distribution = read_distribution_manifest(Path(distribution_manifest))
    evidence_target = {
        "macos-arm64": "macosArm64", "macos-x64": "macosX64",
        "linux-arm64": "linuxArm64", "linux-x64": "linuxX64", "windows-x64": "mingwX64",
    }[target]
    classifier = inspect_classifier(evidence_target, distribution, Path(app_server_archive))
    if (
        f"sha256:{classifier.binary_sha256}" != identity["appServer"]["binarySha256"]
        or classifier.library_version != identity["runtimeCompatibilityVersion"]
        or f"sha256:{classifier.archive_sha256}" != app_server_identity["sha256"]
        or distribution.version != identity["appServer"]["version"]
        or distribution.release_tag != identity["appServer"]["releaseTag"]
    ):
        raise ValueError("Runtime app-server archive identity mismatch")
    c_abi_output = _exact_output(
        package, c_abi_identity, "outputs/c-abi/", "c-abi", "Runtime C ABI archive",
    )
    app_server_output = _exact_output(
        package, app_server_identity, "outputs/app-server/", "app-server",
        "Runtime app-server archive",
    )
    if c_abi_output is app_server_output:
        raise ValueError("Runtime package receipt archive outputs must be distinct")

    validation_bytes = _read_input(
        Path(validation_evidence), "Runtime validation evidence", max_bytes=_EVIDENCE_LIMIT,
    )
    validation_outputs = [
        output for output in validation["outputs"]
        if output["relativePath"].startswith("outputs/native/")
        and output["kind"] == "native"
        and output["bytes"] == len(validation_bytes)
        and output["sha256"] == sha256_bytes(validation_bytes)
    ]
    if len(validation_outputs) != 1:
        raise ValueError("Runtime validation evidence is not the exact validation receipt output")
    validation_projection = derive_desktop_validation_projection(
        load_canonical_json_bytes(validation_bytes),
        identity_envelope=identity,
        expected_commit=validation["producer"]["commit"],
        classifier_archive_sha256=app_server_identity["sha256"],
    )
    validation_projection_bytes = canonical_json_bytes(validation_projection)
    phase_evidence = [
        _phase_evidence(
            receipt_values[phase],
            validation_evidence_digest=(
                sha256_bytes(validation_projection_bytes) if phase == "validation" else None
            ),
        )
        for phase in _RECEIPT_PATHS
    ]
    phase_evidence_bytes = {
        phase: canonical_json_bytes(value)
        for phase, value in zip(_RECEIPT_PATHS, phase_evidence, strict=True)
    }

    deterministic_members = {
        "app-server/codex-app-server.zip": ("app-server-archive", app_server_bytes),
        "c-abi/codex-agent-c.zip": ("c-abi-archive", c_abi_bytes),
        "evidence/validation.json": ("validation", validation_projection_bytes),
    }
    deterministic_artifacts = [
        _artifact(path, role, contents)
        for path, (role, contents) in sorted(deterministic_members.items())
    ]
    attestation = derive_runtime_component_attestation(
        identity, phase_evidence, deterministic_artifacts,
    )
    members = {
        **deterministic_members,
        _RECEIPT_PATHS["binary"]: ("binary-phase-evidence", phase_evidence_bytes["binary"]),
        _RECEIPT_PATHS["package"]: ("package-phase-evidence", phase_evidence_bytes["package"]),
        "evidence/provenance.json": (
            "provenance", attestation["componentProvenanceBytes"],
        ),
        "evidence/sbom.json": ("sbom", attestation["sbomBytes"]),
        _RECEIPT_PATHS["validation"]: (
            "validation-phase-evidence", phase_evidence_bytes["validation"],
        ),
    }
    if len(members) != 8:
        raise ValueError("Runtime variant artifact paths collide")
    artifacts = [
        _artifact(path, role, contents)
        for path, (role, contents) in sorted(members.items())
    ]
    manifest = validate_runtime_variant({
        "schemaVersion": 1,
        "product": "runtime",
        "componentId": identity["componentId"],
        "runtimeCompatibilityVersion": identity["runtimeCompatibilityVersion"],
        "target": target,
        "contract": {
            "digest": identity["contract"]["digest"],
            "componentDigest": identity["contract"]["componentDigest"],
        },
        "cAbi": identity["cAbi"],
        "appServer": identity["appServer"],
        "inputs": {
            "binaryBuildKey": binary["buildKey"],
            "binaryOutputInventoryDigest": output_inventory_digest(binary["outputs"]),
        },
        "innerArtifacts": artifacts,
        "toolchainProfile": identity["toolchainProfile"],
        "signing": signing,
    })
    bundle_name = (
        f"codex-agent-runtime-variant-{target}-"
        f"{identity['componentId'].removeprefix('sha256:')}.zip"
    )
    destination = output_root / bundle_name
    try:
        _read_input(Path(private_key), "Runtime signing private key", max_bytes=1024 * 1024)
        with tempfile.TemporaryDirectory(prefix=".runtime-variant-", dir=output_root) as temporary:
            stage = Path(temporary)
            manifest_path = stage / _MANIFEST_NAME
            write_canonical_json(manifest_path, manifest)
            signature_path = sign_manifest(manifest_path, Path(private_key), signing)
            verify_manifest_signature(manifest_path, signature_path, Path(public_key), signing)
            zip_members = {
                **{path: contents for path, (_, contents) in members.items()},
                _MANIFEST_NAME: canonical_json_bytes(manifest),
                _SIGNATURE_NAME: _read_input(
                    signature_path, "Runtime variant signature", max_bytes=1024 * 1024,
                ),
            }
            staged_bundle = stage / bundle_name
            with zipfile.ZipFile(
                staged_bundle, "w", compression=zipfile.ZIP_STORED, allowZip64=False,
            ) as archive:
                for path, contents in sorted(zip_members.items()):
                    archive.writestr(_zip_info(path), contents)
            verified_zip_contents(
                staged_bundle,
                **RUNTIME_VARIANT_ZIP_LIMITS,
                retained_paths=(),
                max_retained_bytes=0,
                canonical_stored=True,
            )
            os.replace(staged_bundle, destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    if sorted(path.name for path in output_root.iterdir()) != [bundle_name]:
        destination.unlink(missing_ok=True)
        raise ValueError("Runtime variant output directory contains unexpected entries")
    return {
        "bundlePath": destination,
        "bundleSha256": sha256_file(destination),
        "componentId": identity["componentId"],
        "manifestSha256": sha256_bytes(canonical_json_bytes(manifest)),
        "sourceRuntimeVersion": source_version,
        "target": target,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci.products.runtime_variant")
    parser.add_argument("--identity", required=True)
    parser.add_argument("--binary-receipt", required=True)
    parser.add_argument("--package-receipt", required=True)
    parser.add_argument("--validation-receipt", required=True)
    parser.add_argument("--c-abi-archive", required=True)
    parser.add_argument("--app-server-archive", required=True)
    parser.add_argument("--validation-evidence", required=True)
    parser.add_argument("--distribution-manifest", required=True)
    parser.add_argument("--signing-metadata", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--output-directory", required=True)
    arguments = parser.parse_args(argv)
    try:
        result = produce_runtime_variant(
            identity_envelope=load_canonical_json_bytes(_read_input(
                Path(arguments.identity), "Runtime identity", max_bytes=_JSON_LIMIT,
            )),
            binary_receipt=Path(arguments.binary_receipt),
            package_receipt=Path(arguments.package_receipt),
            validation_receipt=Path(arguments.validation_receipt),
            c_abi_archive=Path(arguments.c_abi_archive),
            app_server_archive=Path(arguments.app_server_archive),
            validation_evidence=Path(arguments.validation_evidence),
            distribution_manifest=Path(arguments.distribution_manifest),
            signing_metadata=load_canonical_json_bytes(_read_input(
                Path(arguments.signing_metadata), "Runtime signing metadata", max_bytes=_JSON_LIMIT,
            )),
            private_key=Path(arguments.private_key),
            public_key=Path(arguments.public_key),
            output_directory=Path(arguments.output_directory),
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(result["bundlePath"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
