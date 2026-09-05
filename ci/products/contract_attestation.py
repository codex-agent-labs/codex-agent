"""Detached trust attestation for one immutable Contract payload."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile
from typing import Any

from .contract_model import verify_contract_bundle, verify_extracted_contract_directory
from .inventory import (
    load_canonical_json_bytes,
    load_canonical_json,
    publish_regular_tree,
    read_regular_file_bytes,
    regular_file_inventory,
    require_array,
    require_exact_keys,
    require_integer,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    snapshot_regular_tree,
    verify_regular_file_inventory,
    verified_zip_contents,
    write_canonical_json,
)
from .receipt import validate_phase_receipt, write_output_manifest
from .signatures import (
    load_keyring,
    public_key_for_metadata,
    sign_manifest,
    validate_signing_metadata,
    verify_manifest_signature,
)


_JSON_LIMIT = 16 * 1024 * 1024
_PAYLOAD_LIMIT = 512 * 1024 * 1024
_CLOSURE_MANIFEST = "contract-execution-closure.json"
CONTRACT_EXECUTION_CLOSURE_DIRECTORY = "execution-closure"
_CLOSURE_ARCHIVE = "execution/contract-execution.zip"
_CLOSURE_RECEIPTS = {phase: f"receipts/{phase}.json" for phase in ("binary", "package", "validation", "metadata")}


def _verify_execution_closure_inputs(payload: Path, evidence: Path) -> dict[str, Any]:
    from .contract import _read_contract_receipt, _receipt_reference, validate_contract_package_stage
    from .contract_projection import verify_contract_execution_projection

    _, _, manifest, payload_identity, _ = _bound_inputs(payload, evidence / _CLOSURE_RECEIPTS["metadata"])
    version = manifest["contractVersion"]
    receipts = {}
    digests = {}
    for phase, relative in _CLOSURE_RECEIPTS.items():
        contents = read_regular_file_bytes(evidence / relative, max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
        digests[phase] = sha256_bytes(contents)
        receipts[phase], _ = _read_contract_receipt(evidence / relative, digests[phase], phase, version)
    if receipts["binary"]["inputs"]["upstreamArtifacts"]:
        raise ValueError("Contract binary receipt must have no upstream product")
    repository = receipts["metadata"]["producer"]["repository"]
    if any(receipt["producer"]["repository"] != repository for receipt in receipts.values()):
        raise ValueError("Contract closure original producer repositories differ")
    for phase, predecessor in (("validation", "package"), ("metadata", "validation")):
        if receipts[phase]["inputs"]["upstreamArtifacts"] != [_receipt_reference(receipts[predecessor])]:
            raise ValueError(f"Contract {phase} receipt does not bind its original {predecessor} receipt")

    with tempfile.TemporaryDirectory(prefix="contract-closure-validation-") as temporary:
        root = Path(temporary).resolve()
        binary = root / "binary"
        _, contents, payload_digest = verified_zip_contents(
            payload, canonical_stored=True, max_archive_bytes=_PAYLOAD_LIMIT,
            max_total_bytes=1024 * 1024 * 1024, max_members=4096,
        )
        if payload_digest != {field: payload_identity[field] for field in ("bytes", "sha256")}:
            raise ValueError("Contract closure payload changed during verification")
        for relative, contents_bytes in contents.items():
            if relative == "contract-manifest.json":
                continue
            target = binary / "outputs" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents_bytes)
        raw = read_regular_file_bytes(evidence / _CLOSURE_ARCHIVE, max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True)
        archive = binary / "outputs" / _CLOSURE_ARCHIVE
        archive.parent.mkdir(parents=True)
        archive.write_bytes(raw)
        output_roots = {"maven": "outputs/maven", "evidence": "outputs/evidence", "inventory": "outputs/inventories"}
        write_output_manifest(binary, "contract", "contract", "binary", "common", version, {
            **output_roots, "contract-execution": "outputs/execution",
        })
        verify_contract_execution_projection(
            binary, evidence / _CLOSURE_RECEIPTS["binary"], expected_receipt_sha256=digests["binary"],
        )
        package = root / "package"
        for name in ("maven", "evidence", "inventories"):
            snapshot_regular_tree(binary / "outputs" / name, package / "outputs" / name)
        write_output_manifest(package, "contract", "contract", "package", "common", version, output_roots)
        validation = root / "validation"
        validate_contract_package_stage(
            package, evidence / _CLOSURE_RECEIPTS["package"], digests["package"],
            evidence / _CLOSURE_RECEIPTS["binary"], digests["binary"], validation, version,
        )
        expected = receipts["package"]["outputs"] + [
            {**record, "kind": "validation", "relativePath": "outputs/validation/" + record["relativePath"]}
            for record in regular_file_inventory(validation)
        ]
        if receipts["validation"]["outputs"] != sorted(expected, key=lambda record: record["relativePath"]):
            raise ValueError("Contract validation receipt differs from the verified payload and report")
    files = regular_file_inventory(evidence)
    if {record["relativePath"] for record in files} != {_CLOSURE_ARCHIVE, *_CLOSURE_RECEIPTS.values()}:
        raise ValueError("Contract execution closure file inventory is not exact")
    return {
        "schemaVersion": 1, "product": "contract", "contractVersion": version,
        "payload": payload_identity, "files": files,
    }


def capture_contract_execution_closure(
    payload: Path, phase_receipts: dict[str, Path], execution_archive: Path, output_directory: Path,
) -> dict[str, Any]:
    require_exact_keys(phase_receipts, set(_CLOSURE_RECEIPTS), "Contract closure receipt paths")
    with tempfile.TemporaryDirectory(prefix="contract-closure-capture-") as temporary:
        root = Path(temporary).resolve()
        snapshot_payload = root / Path(payload).name
        snapshot_payload.write_bytes(read_regular_file_bytes(payload, max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True))
        prepared = root / "evidence"
        for phase, relative in _CLOSURE_RECEIPTS.items():
            path = prepared / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(read_regular_file_bytes(phase_receipts[phase], max_bytes=_JSON_LIMIT, reject_symlink_parents=True))
        archive = prepared / _CLOSURE_ARCHIVE
        archive.parent.mkdir(parents=True)
        archive.write_bytes(read_regular_file_bytes(execution_archive, max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True))
        value = _verify_execution_closure_inputs(snapshot_payload, prepared)
        write_canonical_json(prepared / _CLOSURE_MANIFEST, value)
        publish_regular_tree(prepared, output_directory)
    return value


def verify_contract_execution_closure(payload: Path, evidence_directory: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="contract-closure-verify-") as temporary:
        root = Path(temporary).resolve()
        evidence = root / "evidence"
        snapshot_regular_tree(evidence_directory, evidence)
        manifest_path = evidence / _CLOSURE_MANIFEST
        contents = read_regular_file_bytes(manifest_path, max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
        value = require_exact_keys(load_canonical_json_bytes(contents), {
            "schemaVersion", "product", "contractVersion", "payload", "files",
        }, "Contract execution closure")
        if require_integer(value["schemaVersion"], "Contract execution closure schema", 1) != 1:
            raise ValueError("Unsupported Contract execution closure schema")
        inventory = [*require_array(value["files"], "Contract execution closure files"), {"relativePath": _CLOSURE_MANIFEST, "bytes": len(contents), "sha256": sha256_bytes(contents)}]
        verify_regular_file_inventory(evidence, sorted(inventory, key=lambda record: record["relativePath"]), with_kind=False)
        manifest_path.unlink()  # Private snapshot only; retained evidence is immutable.
        snapshot_payload = root / Path(payload).name
        snapshot_payload.write_bytes(read_regular_file_bytes(payload, max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True))
        if value != _verify_execution_closure_inputs(snapshot_payload, evidence):
            raise ValueError("Contract execution closure does not bind its exact evidence and payload")
    return value


def validate_contract_attestation(value: Any) -> dict[str, Any]:
    attestation = require_exact_keys(
        value,
        {
            "schemaVersion",
            "product",
            "contractVersion",
            "payload",
            "manifestSha256",
            "metadataReceiptSha256",
            "executionClosureSha256",
            "signing",
        },
        "Contract attestation",
    )
    if require_integer(attestation["schemaVersion"], "Contract attestation.schemaVersion", 1) != 2:
        raise ValueError("Unsupported Contract attestation schemaVersion")
    if attestation["product"] != "contract":
        raise ValueError("Contract attestation product must be contract")
    version = require_semver(attestation["contractVersion"], "Contract attestation.contractVersion")
    payload = require_exact_keys(
        attestation["payload"], {"fileName", "bytes", "sha256"}, "Contract attestation.payload",
    )
    if require_string(payload["fileName"], "Contract attestation.payload.fileName") != \
            f"codex-agent-contract-{version}.zip":
        raise ValueError("Contract attestation payload filename does not match its version")
    require_integer(payload["bytes"], "Contract attestation.payload.bytes", 1)
    require_sha256(payload["sha256"], "Contract attestation.payload.sha256")
    require_sha256(attestation["manifestSha256"], "Contract attestation.manifestSha256")
    require_sha256(
        attestation["metadataReceiptSha256"], "Contract attestation.metadataReceiptSha256",
    )
    require_sha256(attestation["executionClosureSha256"], "Contract attestation.executionClosureSha256")
    validate_signing_metadata(attestation["signing"])
    return attestation


def _metadata_receipt(path: Path) -> tuple[dict[str, Any], bytes]:
    contents = read_regular_file_bytes(
        Path(path), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    return validate_phase_receipt(load_canonical_json_bytes(contents)), contents


def _payload_identity(path: Path, version: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    expected_name = f"codex-agent-contract-{version}.zip"
    if Path(path).name != expected_name:
        raise ValueError("Contract payload filename does not match its metadata receipt")
    payload_bytes = read_regular_file_bytes(
        Path(path), max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True,
    )
    with tempfile.TemporaryDirectory(prefix="contract-payload-snapshot-") as temporary:
        snapshot = Path(temporary) / expected_name
        snapshot.write_bytes(payload_bytes)
        _, retained, archive = verified_zip_contents(
            snapshot,
            max_archive_bytes=_PAYLOAD_LIMIT,
            max_central_directory_bytes=32 * 1024 * 1024,
            max_members=4096,
            max_entry_bytes=256 * 1024 * 1024,
            max_total_bytes=1024 * 1024 * 1024,
            max_compression_ratio=200,
            retained_paths=("contract-manifest.json",),
            max_retained_bytes=_JSON_LIMIT,
            canonical_stored=True,
        )
        try:
            manifest_bytes = retained["contract-manifest.json"]
        except KeyError as error:
            raise ValueError("Contract payload is missing contract-manifest.json") from error
        manifest = verify_contract_bundle(snapshot)
        if manifest["contractVersion"] != version:
            raise ValueError("Contract payload manifest identity does not match its metadata receipt")
        return manifest, {
            "fileName": expected_name,
            "bytes": archive["bytes"],
            "sha256": archive["sha256"],
        }, sha256_bytes(manifest_bytes)


def _bound_inputs(payload_path: Path, receipt_path: Path) -> tuple[
    dict[str, Any], bytes, dict[str, Any], dict[str, Any], str
]:
    receipt, receipt_bytes = _metadata_receipt(receipt_path)
    if (
        receipt["product"],
        receipt["component"],
        receipt["phase"],
        receipt["target"],
    ) != ("contract", "contract", "metadata", "common"):
        raise ValueError("Contract attestation requires a Contract metadata receipt")
    version = receipt["productVersion"]
    manifest, payload, manifest_sha256 = _payload_identity(payload_path, version)
    expected_output = {
        "kind": "contract-bundle",
        "relativePath": f"outputs/{payload['fileName']}",
        "bytes": payload["bytes"],
        "sha256": payload["sha256"],
    }
    if receipt["outputs"] != [expected_output]:
        raise ValueError("Contract metadata receipt does not bind the exact payload")
    return receipt, receipt_bytes, manifest, payload, manifest_sha256


def _bound_execution_inputs(payload: Path, metadata_receipt: Path, execution_closure: Path):
    """Bind one private snapshot; never rebuild or rewrite producer evidence."""
    with tempfile.TemporaryDirectory(prefix="contract-attestation-inputs-") as temporary:
        root = Path(temporary).resolve()
        snapshot_payload = root / Path(payload).name
        snapshot_payload.write_bytes(read_regular_file_bytes(payload, max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True))
        receipt_bytes = read_regular_file_bytes(metadata_receipt, max_bytes=_JSON_LIMIT, reject_symlink_parents=True)
        snapshot_receipt = root / "metadata-receipt.json"
        snapshot_receipt.write_bytes(receipt_bytes)
        closure = root / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        snapshot_regular_tree(execution_closure, closure)
        if read_regular_file_bytes(closure / _CLOSURE_RECEIPTS["metadata"], max_bytes=_JSON_LIMIT) != receipt_bytes:
            raise ValueError("Contract execution closure metadata receipt differs from the supplied receipt")
        bound = _bound_inputs(snapshot_payload, snapshot_receipt)
        verify_contract_execution_closure(snapshot_payload, closure)
        digest = sha256_bytes(read_regular_file_bytes(closure / _CLOSURE_MANIFEST, max_bytes=_JSON_LIMIT))
    return (*bound, digest)


def verify_contract_attestation(
    payload: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    *,
    required_trust_domain: str,
    keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if type(required_trust_domain) is not str or \
            required_trust_domain not in {"development", "release"}:
        raise ValueError("Expected Contract attestation trust domain is invalid")
    contents = read_regular_file_bytes(
        Path(attestation), max_bytes=_JSON_LIMIT, reject_symlink_parents=True,
    )
    signature_contents = read_regular_file_bytes(
        Path(signature), max_bytes=1024 * 1024, reject_symlink_parents=True,
    )
    public_key_contents = read_regular_file_bytes(
        Path(public_key), max_bytes=1024 * 1024, reject_symlink_parents=True,
    )
    value = validate_contract_attestation(load_canonical_json_bytes(contents))
    version = value["contractVersion"]
    expected_attestation = f"codex-agent-contract-{version}.attestation.json"
    expected_signature = f"codex-agent-contract-{version}.attestation.sig"
    if Path(attestation).name != expected_attestation or Path(signature).name != expected_signature:
        raise ValueError("Contract attestation or signature filename is invalid")
    signing = validate_signing_metadata(value["signing"], trust_domain=required_trust_domain)
    receipt, receipt_bytes, manifest, payload_identity, manifest_sha256, closure_digest = _bound_execution_inputs(
        Path(payload), Path(metadata_receipt), Path(attestation).parent / CONTRACT_EXECUTION_CLOSURE_DIRECTORY,
    )
    if receipt["productVersion"] != version:
        raise ValueError("Contract metadata receipt version does not match its attestation")
    expected = {
        "schemaVersion": 2,
        "product": "contract",
        "contractVersion": version,
        "payload": payload_identity,
        "manifestSha256": manifest_sha256,
        "metadataReceiptSha256": sha256_bytes(receipt_bytes),
        "executionClosureSha256": closure_digest,
        "signing": signing,
    }
    if value != expected:
        raise ValueError("Contract attestation does not bind its exact payload and metadata receipt")
    if required_trust_domain == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Contract attestation verification requires a keyring")
        trusted_key = public_key_for_metadata(
            signing, load_keyring(Path(keyring), Path(keys_directory)), Path(keys_directory),
            allow_retired=True,
        )
        if read_regular_file_bytes(trusted_key, reject_symlink_parents=True) != public_key_contents:
            raise ValueError("Contract attestation public key does not match the release keyring")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Contract attestation verification rejects release keyring inputs")
    with tempfile.TemporaryDirectory(prefix="contract-attestation-snapshot-") as temporary:
        root = Path(temporary).resolve()
        snapshot_attestation = root / expected_attestation
        snapshot_signature = root / expected_signature
        snapshot_public_key = root / "contract.pub"
        snapshot_attestation.write_bytes(contents)
        snapshot_signature.write_bytes(signature_contents)
        snapshot_public_key.write_bytes(public_key_contents)
        verify_manifest_signature(
            snapshot_attestation, snapshot_signature, snapshot_public_key, signing,
        )
    return manifest, receipt, value


def build_contract_attestation(
    payload: Path,
    metadata_receipt: Path,
    signing_metadata: Any,
    private_key: Path,
    public_key: Path,
    output_directory: Path,
    *,
    execution_closure: Path,
    keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> dict[str, Any]:
    signing = validate_signing_metadata(signing_metadata)
    if signing["trustDomain"] == "release":
        if keyring is None or keys_directory is None:
            raise ValueError("Release Contract attestation creation requires the active keyring")
        trusted_key = public_key_for_metadata(
            signing,
            load_keyring(Path(keyring), Path(keys_directory)),
            Path(keys_directory),
            allow_retired=False,
        )
        if read_regular_file_bytes(trusted_key, reject_symlink_parents=True) != \
                read_regular_file_bytes(Path(public_key), reject_symlink_parents=True):
            raise ValueError("Contract attestation public key is not the active release key")
    elif keyring is not None or keys_directory is not None:
        raise ValueError("Development Contract attestation creation rejects release keyring inputs")
    output = Path(output_directory)
    with tempfile.TemporaryDirectory(prefix="contract-attestation-") as temporary:
        prepared = Path(temporary).resolve() / "attestation"
        prepared.mkdir()
        closure = prepared / CONTRACT_EXECUTION_CLOSURE_DIRECTORY
        snapshot_regular_tree(execution_closure, closure)
        receipt, receipt_bytes, _, payload_identity, manifest_sha256, closure_digest = _bound_execution_inputs(
            Path(payload), Path(metadata_receipt), closure,
        )
        value = validate_contract_attestation({
            "schemaVersion": 2,
            "product": "contract",
            "contractVersion": receipt["productVersion"],
            "payload": payload_identity,
            "manifestSha256": manifest_sha256,
            "metadataReceiptSha256": sha256_bytes(receipt_bytes),
            "executionClosureSha256": closure_digest,
            "signing": signing,
        })
        stem = f"codex-agent-contract-{receipt['productVersion']}.attestation"
        attestation = prepared / f"{stem}.json"
        write_canonical_json(attestation, value)
        signature = sign_manifest(attestation, Path(private_key), signing)
        verify_contract_attestation(
            Path(payload),
            Path(metadata_receipt),
            attestation,
            signature,
            Path(public_key),
            required_trust_domain=signing["trustDomain"],
            keyring=keyring,
            keys_directory=keys_directory,
        )
        publish_regular_tree(prepared, output)
    return value


def materialize_contract_payload(
    payload: Path,
    metadata_receipt: Path,
    attestation: Path,
    signature: Path,
    public_key: Path,
    output_directory: Path,
    *,
    required_trust_domain: str,
    expected_contract_version: str,
    required_components: tuple[str, ...],
    keyring: Path | None = None,
    keys_directory: Path | None = None,
    reuse_output_directory: bool = False,
) -> dict[str, Any]:
    """Authenticate one payload and publish its exact verified content tree."""
    manifest, _, value = verify_contract_attestation(
        payload,
        metadata_receipt,
        attestation,
        signature,
        public_key,
        required_trust_domain=required_trust_domain,
        keyring=keyring,
        keys_directory=keys_directory,
    )
    version = require_semver(expected_contract_version, "Expected Contract version")
    if manifest["contractVersion"] != version:
        raise ValueError("Contract payload version does not match the expected Contract version")
    payload_bytes = read_regular_file_bytes(
        Path(payload), max_bytes=_PAYLOAD_LIMIT, reject_symlink_parents=True,
    )
    if len(payload_bytes) != value["payload"]["bytes"] or \
            sha256_bytes(payload_bytes) != value["payload"]["sha256"]:
        raise ValueError("Contract payload changed after attestation verification")
    output = Path(output_directory)
    with tempfile.TemporaryDirectory(prefix="contract-payload-materialize-") as temporary:
        root = Path(temporary).resolve()
        snapshot = root / value["payload"]["fileName"]
        snapshot.write_bytes(payload_bytes)
        _, contents, identity = verified_zip_contents(
            snapshot,
            max_archive_bytes=_PAYLOAD_LIMIT,
            max_central_directory_bytes=32 * 1024 * 1024,
            max_members=4096,
            max_entry_bytes=256 * 1024 * 1024,
            max_total_bytes=1024 * 1024 * 1024,
            max_compression_ratio=200,
            canonical_stored=True,
        )
        if identity != {
            "bytes": value["payload"]["bytes"],
            "sha256": value["payload"]["sha256"],
        }:
            raise ValueError("Contract payload snapshot identity differs from its attestation")
        if verify_contract_bundle(snapshot) != manifest:
            raise ValueError("Contract payload manifest changed after attestation verification")
        staged = root / "contents"
        for relative, member in contents.items():
            target = staged.joinpath(*relative.split("/"))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(member)
        verify_extracted_contract_directory(
            staged,
            expected_contract_version=version,
            required_components=required_components,
            output_directory=output,
            reuse_output_directory=reuse_output_directory,
        )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m ci.products.contract_attestation",
        description="Build or verify a detached Contract payload attestation",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    capture_closure = commands.add_parser("capture-closure")
    capture_closure.add_argument("--payload", type=Path, required=True)
    capture_closure.add_argument("--execution-archive", type=Path, required=True)
    capture_closure.add_argument("--output-directory", type=Path, required=True)
    for phase in _CLOSURE_RECEIPTS:
        capture_closure.add_argument(f"--{phase}-receipt", type=Path, required=True)
    verify_closure = commands.add_parser("verify-closure")
    verify_closure.add_argument("--payload", type=Path, required=True)
    verify_closure.add_argument("--evidence-directory", type=Path, required=True)
    build = commands.add_parser("build")
    verify = commands.add_parser("verify")
    materialize = commands.add_parser("materialize")
    for command in (build, verify, materialize):
        command.add_argument("--payload", type=Path, required=True)
        command.add_argument("--metadata-receipt", type=Path, required=True)
        command.add_argument("--public-key", type=Path, required=True)
        command.add_argument("--keyring", type=Path)
        command.add_argument("--keys-directory", type=Path)
    build.add_argument("--signing-metadata", type=Path, required=True)
    build.add_argument("--execution-closure", type=Path, required=True)
    build.add_argument("--private-key", type=Path, required=True)
    build.add_argument("--output-directory", type=Path, required=True)
    verify.add_argument("--attestation", type=Path, required=True)
    verify.add_argument("--signature", type=Path, required=True)
    verify.add_argument(
        "--required-trust-domain", choices=("development", "release"), required=True,
    )
    materialize.add_argument("--attestation", type=Path, required=True)
    materialize.add_argument("--signature", type=Path, required=True)
    materialize.add_argument(
        "--required-trust-domain", choices=("development", "release"), required=True,
    )
    materialize.add_argument("--expected-contract-version", required=True)
    materialize.add_argument("--required-component", action="append", default=[])
    materialize.add_argument("--output-directory", type=Path, required=True)
    materialize.add_argument("--reuse-output-directory", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.command == "capture-closure":
        capture_contract_execution_closure(
            arguments.payload, {phase: getattr(arguments, f"{phase}_receipt") for phase in _CLOSURE_RECEIPTS},
            arguments.execution_archive, arguments.output_directory,
        )
        return 0
    if arguments.command == "verify-closure":
        verify_contract_execution_closure(arguments.payload, arguments.evidence_directory)
        return 0
    if arguments.command == "build":
        build_contract_attestation(
            arguments.payload,
            arguments.metadata_receipt,
            load_canonical_json(arguments.signing_metadata),
            arguments.private_key,
            arguments.public_key,
            arguments.output_directory,
            execution_closure=arguments.execution_closure,
            keyring=arguments.keyring,
            keys_directory=arguments.keys_directory,
        )
    elif arguments.command == "verify":
        verify_contract_attestation(
            arguments.payload,
            arguments.metadata_receipt,
            arguments.attestation,
            arguments.signature,
            arguments.public_key,
            required_trust_domain=arguments.required_trust_domain,
            keyring=arguments.keyring,
            keys_directory=arguments.keys_directory,
        )
    else:
        materialize_contract_payload(
            arguments.payload,
            arguments.metadata_receipt,
            arguments.attestation,
            arguments.signature,
            arguments.public_key,
            arguments.output_directory,
            required_trust_domain=arguments.required_trust_domain,
            expected_contract_version=arguments.expected_contract_version,
            required_components=tuple(arguments.required_component),
            keyring=arguments.keyring,
            keys_directory=arguments.keys_directory,
            reuse_output_directory=arguments.reuse_output_directory,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
