"""Replay all three original JavaScript SDK phases, without granting release trust."""

from pathlib import Path

from .inventory import canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes, regular_file_inventory
from .registry import PhaseInstanceId
from .reuse import _validate_envelope
from .sdk_javascript_metadata_admission import verify_sdk_javascript_metadata_admission
from .sdk_javascript_validation_phase import verify_sdk_javascript_validation_phase
from .sdk_package import verify_sdk_package_inputs


_LIMIT = 16 * 1024 * 1024


def verify_campaign_javascript(
    *, repository: Path, compatibility_request: Path,
    package_envelope: dict, package_stage: Path, package_receipt: Path,
    validation_envelope: dict, validation_stage: Path, validation_receipt: Path,
    metadata_envelope: dict, metadata_stage: Path, metadata_receipt: Path,
    contract_stage: Path, contract_receipt: Path,
    runtime_package_stage: Path, runtime_package_receipt: Path,
    runtime_validation_stage: Path, runtime_validation_receipt: Path,
    original_consumer_directory: Path, tooling_evidence: Path,
    tooling_public_key: Path, java_executable: Path, policy_revision: str,
    required_trust_domain: str, tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
) -> dict[str, bytes]:
    """Return unchanged original receipt bytes only after every full phase gate.

    The protected caller separately authenticates selected immutable objects,
    Contract/Runtime predecessors, hosted producer and current transport.
    """
    selected = {
        "package": (package_envelope, Path(package_receipt)),
        "validation": (validation_envelope, Path(validation_receipt)),
        "metadata": (metadata_envelope, Path(metadata_receipt)),
    }
    originals = {}
    frozen = {}
    bindings = {}
    versions = set()
    stages = {"package": Path(package_stage), "validation": Path(validation_stage),
              "metadata": Path(metadata_stage)}
    stage_before = {phase: regular_file_inventory(path) for phase, path in stages.items()}
    for phase, (envelope, path) in selected.items():
        instance, value = _validate_envelope(envelope)
        if instance != PhaseInstanceId("sdk", "javascript", phase, "node"):
            raise ValueError("JavaScript campaign selected the wrong phase identity")
        raw = read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True)
        if raw != value["receiptBytes"]:
            raise ValueError("JavaScript campaign selected receipt differs from its original file")
        originals[phase] = raw
        frozen[phase] = load_canonical_json_bytes(raw)
        bindings[phase] = (raw, value["receiptSha256"], value["objectSha256"],
                           canonical_json_bytes(value["receipt"]))
        versions.add(value["receipt"]["productVersion"])
    if len(versions) != 1:
        raise ValueError("JavaScript campaign phases must use one exact SDK version")

    def unchanged():
        for phase, (envelope, _) in selected.items():
            identity, value = _validate_envelope(envelope)
            current = (value["receiptBytes"], value["receiptSha256"], value["objectSha256"],
                       canonical_json_bytes(value["receipt"]))
            if identity != PhaseInstanceId("sdk", "javascript", phase, "node") or current != bindings[phase]:
                raise ValueError("JavaScript campaign selected envelope changed during full replay")

    package, raw = verify_sdk_package_inputs(repository, package_stage, package_receipt,
        compatibility_request, runtime_package_stage=runtime_package_stage,
        runtime_package_receipt=runtime_package_receipt)
    if raw != originals["package"] or package != frozen["package"]:
        raise ValueError("JavaScript campaign full package gate changed the selected receipt")
    unchanged()
    common = dict(repository=repository, contract_stage=contract_stage,
        contract_receipt=contract_receipt, package_stage=package_stage,
        package_receipt=package_receipt, validation_stage=validation_stage,
        validation_receipt=validation_receipt,
        runtime_validation_stage=runtime_validation_stage,
        runtime_validation_receipt=runtime_validation_receipt,
        original_consumer_directory=original_consumer_directory,
        tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
        java_executable=java_executable, policy_revision=policy_revision,
        required_trust_domain=required_trust_domain,
        tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)
    validation, raw = verify_sdk_javascript_validation_phase(**common)
    if raw != originals["validation"] or validation != frozen["validation"]:
        raise ValueError("JavaScript campaign full validation gate changed the selected receipt")
    unchanged()
    metadata, raw = verify_sdk_javascript_metadata_admission(**common,
        metadata_stage=metadata_stage, metadata_receipt=metadata_receipt)
    if raw != originals["metadata"] or metadata != frozen["metadata"]:
        raise ValueError("JavaScript campaign full metadata gate changed the selected receipt")
    unchanged()
    if any(read_regular_file_bytes(path, max_bytes=_LIMIT, reject_symlink_parents=True) != originals[phase]
           for phase, (_, path) in selected.items()):
        raise ValueError("JavaScript campaign original receipt changed during full replay")
    if any(regular_file_inventory(path) != stage_before[phase] for phase, path in stages.items()):
        raise ValueError("JavaScript campaign original stage changed during full replay")
    return originals
