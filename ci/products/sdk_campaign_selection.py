"""Exact structural SDK campaign selection; semantic release admission comes later."""

from collections.abc import Mapping
from pathlib import Path

from .index import IndexEntrySource, _validated_entry_source
from .inventory import regular_file_inventory, sha256_bytes
from .receipt import verify_output_manifest_identity
from .registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from .restore import verify_object
from .reuse import _validate_envelope


SDK_CAMPAIGN_INSTANCES = frozenset(
    instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk"
)


def verify_sdk_campaign_selection(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    stages: Mapping[PhaseInstanceId, Path],
) -> dict[PhaseInstanceId, dict]:
    """Bind all 61 selected SDK receipts, objects and stages without granting trust.

    The protected caller must still authenticate retrieval/producer provenance and
    run every component's full semantic verifier before minting release admission.
    """
    for name, values in (("sources", sources), ("envelopes", envelopes),
                         ("archives", archives), ("stages", stages)):
        if not isinstance(values, Mapping) or set(values) != SDK_CAMPAIGN_INSTANCES:
            raise ValueError(f"SDK campaign {name} must contain every exact SDK phase instance")
    selected = {}
    versions = set()
    for instance in sorted(SDK_CAMPAIGN_INSTANCES):
        identity, envelope = _validate_envelope(envelopes[instance])
        if identity != instance:
            raise ValueError("SDK campaign envelope has the wrong phase identity")
        source = sources[instance]
        receipt, _, _ = _validated_entry_source(source)
        if source.release_admission is not None or source.receipt_bytes != envelope["receiptBytes"]:
            raise ValueError("SDK campaign source differs from the original selected receipt")
        versions.add(receipt["productVersion"])
        archive = Path(archives[instance])
        stage = Path(stages[instance])
        before = regular_file_inventory(stage)
        verified = verify_object(archive, build_key=receipt["buildKey"],
            receipt_sha256=sha256_bytes(source.receipt_bytes),
            object_sha256=envelope["objectSha256"])
        if verified["receiptBytes"] != source.receipt_bytes:
            raise ValueError("SDK campaign object differs from the original selected receipt")
        manifest = verify_output_manifest_identity(stage, instance.product,
            instance.component, instance.phase, instance.target, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"] or regular_file_inventory(stage) != before:
            raise ValueError("SDK campaign stage differs from the selected object and receipt")
        selected[instance] = receipt
    if len(versions) != 1:
        raise ValueError("SDK campaign phases must use one exact SDK version")
    return selected
