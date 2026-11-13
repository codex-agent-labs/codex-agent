"""Materialize a verified SDK Android Maven repository for the evidence app."""

from __future__ import annotations

import argparse
from pathlib import Path
import tempfile

from .inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, snapshot_regular_tree,
)
from .registry import PhaseInstanceId
from .sdk_compatibility import load_sdk_compatibility_request
from .sdk_package import verify_sdk_package_inputs


def materialize_android_evidence_repository(
    repository: Path, package_stage: Path, package_receipt: Path,
    binary_stage: Path, binary_receipt: Path, compatibility_request: Path,
    binary_contract_evidence: Path, contract_payload: Path,
    contract_metadata_receipt: Path, contract_attestation: Path,
    contract_attestation_signature: Path, contract_public_key: Path,
    destination: Path,
) -> str:
    """Verify the original product chain before exposing its Maven bytes."""
    repository = Path(repository).resolve(strict=True)
    paths = [Path(value) for value in (
        package_stage, package_receipt, binary_stage, binary_receipt,
        compatibility_request, binary_contract_evidence, contract_payload,
        contract_metadata_receipt, contract_attestation,
        contract_attestation_signature, contract_public_key,
    )]
    if any(not path.is_absolute() or path.resolve(strict=True) != path for path in paths):
        raise ValueError("Android evidence inputs must be absolute normalized regular paths")
    destination = Path(destination)
    output = destination.resolve(strict=False)
    if (not destination.is_absolute() or output != destination or destination.exists()
            or destination.is_symlink() or any(
                output == source or output in source.parents or source in output.parents
                for source in paths)):
        raise ValueError("Android evidence Maven destination must be fresh and separate")
    request = load_sdk_compatibility_request(compatibility_request)
    contract_paths = (
        ("contract_payload", contract_payload),
        ("contract_metadata_receipt", contract_metadata_receipt),
        ("contract_attestation", contract_attestation),
        ("contract_attestation_signature", contract_attestation_signature),
        ("contract_public_key", contract_public_key),
    )
    if any(request[name] != path for name, path in contract_paths):
        raise ValueError("Android evidence request differs from the settings-authenticated Contract")
    evidence = load_canonical_json_bytes(read_regular_file_bytes(
        binary_contract_evidence, reject_symlink_parents=True))
    if type(evidence) is not dict:
        raise ValueError("Android evidence Contract policy must be a canonical object")
    stage_before = regular_file_inventory(package_stage)
    binary_before = regular_file_inventory(binary_stage)
    receipt_before = read_regular_file_bytes(package_receipt, reject_symlink_parents=True)
    binary_receipt_before = read_regular_file_bytes(binary_receipt, reject_symlink_parents=True)
    receipt, original = verify_sdk_package_inputs(
        repository, package_stage, package_receipt, compatibility_request,
        binary_stage_root=binary_stage, binary_receipt_path=binary_receipt,
        binary_contract_evidence=evidence,
    )
    if (PhaseInstanceId(*(receipt[name] for name in (
            "product", "component", "phase", "target"))) !=
            PhaseInstanceId("sdk", "sdk-android", "package", "android")
            or original != receipt_before or receipt["productVersion"] != request["sdk_version"]):
        raise ValueError("Android evidence requires the exact selected SDK Android package")
    source = package_stage / "outputs/maven"
    source_before = regular_file_inventory(source)
    with tempfile.TemporaryDirectory(prefix="sdk-android-evidence-maven-") as temporary:
        private = Path(temporary).resolve() / "maven"
        snapshot_regular_tree(source, private)
        if (regular_file_inventory(private) != source_before
                or regular_file_inventory(source) != source_before
                or regular_file_inventory(package_stage) != stage_before
                or regular_file_inventory(binary_stage) != binary_before
                or read_regular_file_bytes(package_receipt, reject_symlink_parents=True) != receipt_before
                or read_regular_file_bytes(binary_receipt, reject_symlink_parents=True) != binary_receipt_before):
            raise ValueError("Android evidence package inputs changed before repository publication")
        publish_regular_tree(private, destination, expected_inventory=source_before)
    return receipt["productVersion"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in (
        "repository", "package-stage", "package-receipt", "binary-stage",
        "binary-receipt", "compatibility-request", "binary-contract-evidence",
        "contract-payload", "contract-metadata-receipt", "contract-attestation",
        "contract-attestation-signature", "contract-public-key", "destination",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    args = vars(parser.parse_args(argv))
    print(materialize_android_evidence_repository(**{
        name.replace("-", "_"): value for name, value in args.items()
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
