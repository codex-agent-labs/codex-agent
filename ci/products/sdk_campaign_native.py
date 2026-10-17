"""Compose the existing native SDK gates over one captured campaign selection.

This is a semantic family boundary, not provenance or release admission. The
caller supplies authenticated compatibility, Runtime, tooling, and selected
product objects; no authority is minted here.
"""

from collections.abc import Mapping
from pathlib import Path
import tempfile

from .index import IndexEntrySource, _validated_entry_source
from .inventory import read_regular_file_bytes, regular_file_inventory, sha256_bytes, snapshot_regular_tree
from .receipt import verify_output_manifest_identity
from .registry import NATIVE_BINDINGS, NATIVE_TARGETS, PhaseInstanceId
from .sdk_native_metadata_admission import verify_sdk_native_metadata_admission
from .sdk_package import verify_sdk_package_inputs
from .sdk_validation import VerifiedSdkValidationProjection, verify_sdk_validation_projection


NATIVE_CAMPAIGN_INSTANCES = frozenset(
    PhaseInstanceId("sdk", component, phase, target)
    for component in NATIVE_BINDINGS
    for phase, targets in (("package", ("desktop",)),
                           ("validation", NATIVE_TARGETS),
                           ("metadata", ("desktop",)))
    for target in targets
) | {PhaseInstanceId("sdk", "csharp", "binary", "desktop")}


def verify_sdk_campaign_native(
    *, repository: Path,
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    stages: Mapping[PhaseInstanceId, Path],
    compatibility_request: Path, runtime_stages: Path, staged_sdks: Path,
    tooling_evidence: Path, tooling_public_key: Path, java_executable: Path,
    policy_revision: str, required_trust_domain: str,
    tooling_keyring: Path | None = None, tooling_keys_directory: Path | None = None,
) -> tuple[dict[PhaseInstanceId, tuple[dict, bytes]], dict[PhaseInstanceId, VerifiedSdkValidationProjection]]:
    """Verify one C# binary, five packages, 25 host validations, and five metadata phases.

    The caller must first bind selected objects to their source/envelopes and
    authenticate every upstream path and tooling policy. Returned host values
    are the opaque projections from the full original validation verifier.
    """
    if (not isinstance(sources, Mapping) or not isinstance(stages, Mapping)
            or set(sources) != NATIVE_CAMPAIGN_INSTANCES
            or set(stages) != NATIVE_CAMPAIGN_INSTANCES):
        raise ValueError("Native SDK campaign requires its exact 36 phase instances")

    originals = {}
    inventories = {}
    source_paths = {}
    original_sources = {}
    versions = set()
    for instance in sorted(NATIVE_CAMPAIGN_INSTANCES):
        source = sources[instance]
        receipt, _, _ = _validated_entry_source(source)
        if source.release_admission is not None or tuple(receipt[field] for field in (
                "product", "component", "phase", "target")) != (
                instance.product, instance.component, instance.phase, instance.target):
            raise ValueError("Native SDK source has admission or the wrong phase identity")
        versions.add(receipt["productVersion"])
        original = source.receipt_bytes
        stage = Path(stages[instance])
        before = regular_file_inventory(stage)
        manifest = verify_output_manifest_identity(stage, instance.product, instance.component,
            instance.phase, instance.target, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"] or regular_file_inventory(stage) != before:
            raise ValueError("Native SDK stage differs from its original receipt")
        originals[instance] = (receipt, original)
        inventories[instance] = before
        source_paths[instance] = stage
        original_sources[instance] = source
    if len(versions) != 1:
        raise ValueError("Native SDK campaign requires one exact SDK version")

    verified_receipts = {}
    projections = {}
    tooling = dict(repository=repository, compatibility_request=compatibility_request,
        runtime_stages=runtime_stages, staged_sdks=staged_sdks,
        tooling_evidence=tooling_evidence, tooling_public_key=tooling_public_key,
        java_executable=java_executable, policy_revision=policy_revision,
        required_trust_domain=required_trust_domain, tooling_keyring=tooling_keyring,
        tooling_keys_directory=tooling_keys_directory)
    with tempfile.TemporaryDirectory(prefix="sdk-native-campaign-") as temporary:
        private = Path(temporary).resolve()
        captured = {}
        receipt_paths = {}
        for instance in sorted(NATIVE_CAMPAIGN_INSTANCES):
            stage = private / instance.component / instance.phase / instance.target
            snapshot_regular_tree(source_paths[instance], stage)
            if regular_file_inventory(stage) != inventories[instance]:
                raise ValueError("Native SDK stage changed during capture")
            receipt_path = private / "receipts" / instance.component / instance.phase / f"{instance.target}.json"
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt_path.write_bytes(originals[instance][1])
            captured[instance], receipt_paths[instance] = stage, receipt_path

        for component in NATIVE_BINDINGS:
            package = PhaseInstanceId("sdk", component, "package", "desktop")
            metadata = PhaseInstanceId("sdk", component, "metadata", "desktop")
            binary = PhaseInstanceId("sdk", "csharp", "binary", "desktop")
            binary_inputs = ({"binary_stage_root": captured[binary],
                              "binary_receipt_path": receipt_paths[binary]}
                             if component == "csharp" else {})
            value = verify_sdk_package_inputs(repository, captured[package], receipt_paths[package],
                compatibility_request, runtime_stage_root=runtime_stages, staged_sdks=staged_sdks,
                **binary_inputs)
            if value != originals[package]:
                raise ValueError("Native SDK package verifier returned another original receipt")
            verified_receipts[package] = value
            if component == "csharp":
                verified_receipts[binary] = originals[binary]

            validation_root = private / component / "validation"
            validation_receipt_root = private / "receipts" / component / "validation"
            host_projections = []
            for target in sorted(NATIVE_TARGETS):
                instance = PhaseInstanceId("sdk", component, "validation", target)
                proof = verify_sdk_validation_projection(component=component, target=target,
                    package_stage=captured[package], package_receipt=receipt_paths[package],
                    validation_stage=captured[instance], validation_receipt=receipt_paths[instance],
                    **tooling)
                receipt, raw = originals[instance]
                proof.output_inventory(sha256_bytes(raw), receipt["outputs"], identity=receipt)
                projections[instance] = proof
                verified_receipts[instance] = (receipt, raw)
                host_projections.append(proof)
            value = verify_sdk_native_metadata_admission(component=component,
                metadata_stage=captured[metadata], metadata_receipt=receipt_paths[metadata],
                package_stage=captured[package], package_receipt=receipt_paths[package],
                validation_stages=validation_root, validation_receipts=validation_receipt_root,
                sdk_validation_projections=tuple(host_projections), **tooling)
            if value != originals[metadata]:
                raise ValueError("Native SDK metadata verifier returned another original receipt")
            verified_receipts[metadata] = value

        for instance in sorted(NATIVE_CAMPAIGN_INSTANCES):
            if (sources[instance] != original_sources[instance]
                    or Path(stages[instance]) != source_paths[instance]
                    or regular_file_inventory(source_paths[instance]) != inventories[instance]
                    or regular_file_inventory(captured[instance]) != inventories[instance]
                    or read_regular_file_bytes(receipt_paths[instance], reject_symlink_parents=True)
                    != originals[instance][1]):
                raise ValueError("Native SDK original or captured inputs changed during verification")
    return verified_receipts, projections
