"""Exact structural SDK campaign selection; semantic release admission comes later."""

from contextlib import contextmanager
from copy import deepcopy
from collections.abc import Mapping
from pathlib import Path
import tempfile
from types import MappingProxyType

from .index import IndexEntrySource, _validated_entry_source
from .inventory import regular_file_inventory, sha256_bytes
from .receipt import verify_output_manifest_identity
from .registry import PHASE_INSTANCE_IDS, PhaseInstanceId
from .restore import restore_object, verify_object
from .reuse import _validate_envelope


SDK_CAMPAIGN_INSTANCES = frozenset(
    instance for instance in PHASE_INSTANCE_IDS if instance.product == "sdk"
)


def verify_sdk_campaign_objects(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
) -> dict[PhaseInstanceId, dict]:
    """Bind all 61 original SDK receipts and objects for content-only reuse.

    This is not stage, semantic, transport, producer, or release admission.
    """
    for name, values in (("sources", sources), ("envelopes", envelopes), ("archives", archives)):
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
        verified = verify_object(archive, build_key=receipt["buildKey"],
            receipt_sha256=sha256_bytes(source.receipt_bytes),
            object_sha256=envelope["objectSha256"])
        if verified["receiptBytes"] != source.receipt_bytes:
            raise ValueError("SDK campaign object differs from the original selected receipt")
        selected[instance] = receipt
    if len(versions) != 1:
        raise ValueError("SDK campaign phases must use one exact SDK version")
    return selected


def verify_sdk_campaign_selection(
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    stages: Mapping[PhaseInstanceId, Path],
) -> dict[PhaseInstanceId, dict]:
    """Bind all 61 selected receipts, objects and stages without release trust."""
    selected = verify_sdk_campaign_objects(sources, envelopes, archives)
    if not isinstance(stages, Mapping) or set(stages) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK campaign stages must contain every exact SDK phase instance")
    for instance, receipt in selected.items():
        stage = Path(stages[instance])
        before = regular_file_inventory(stage)
        manifest = verify_output_manifest_identity(stage, instance.product,
            instance.component, instance.phase, instance.target, receipt["productVersion"])
        if manifest["outputs"] != receipt["outputs"] or regular_file_inventory(stage) != before:
            raise ValueError("SDK campaign stage differs from the selected object and receipt")
    return selected


@contextmanager
def held_sdk_campaign_selection(sources, envelopes, archives, stages):
    """Yield private exact-object stages while checking the whole selection on exit.

    This holds content, not producer/transport authority or release admission.
    The protected caller must perform those checks and use these private stages
    for every family gate before signing inside this context.
    """
    selected = verify_sdk_campaign_selection(sources, envelopes, archives, stages)
    selected_before = deepcopy(selected)
    source_before = dict(sources)
    envelope_before = deepcopy(dict(envelopes))
    archive_before = {instance: Path(path) for instance, path in archives.items()}
    stage_before = {instance: Path(path) for instance, path in stages.items()}
    private_envelopes = deepcopy(envelope_before)
    with tempfile.TemporaryDirectory(prefix="sdk-campaign-held-") as temporary:
        root = Path(temporary).resolve()
        private_stages = {}
        inventories = {}
        original_inventories = {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            destination = root / str(position)
            receipt = selected[instance]
            restored = restore_object(archive_before[instance], destination,
                build_key=receipt["buildKey"],
                receipt_sha256=sha256_bytes(source_before[instance].receipt_bytes),
                object_sha256=envelope_before[instance]["objectSha256"])
            if restored["receiptBytes"] != source_before[instance].receipt_bytes:
                raise ValueError("Held SDK object differs from selected original receipt")
            original_inventory = regular_file_inventory(stage_before[instance])
            private_inventory = regular_file_inventory(destination)
            if private_inventory != original_inventory:
                raise ValueError("Held SDK stage differs from selected original stage")
            private_stages[instance] = destination
            inventories[instance] = private_inventory
            original_inventories[instance] = original_inventory
        private_receipts = deepcopy(selected_before)
        held = (MappingProxyType(source_before), MappingProxyType(private_envelopes),
                MappingProxyType(private_stages), MappingProxyType(private_receipts))
        try:
            yield held
        finally:
            if (dict(sources) != source_before or dict(envelopes) != envelope_before
                    or {instance: Path(path) for instance, path in archives.items()} != archive_before
                    or {instance: Path(path) for instance, path in stages.items()} != stage_before
                    or private_envelopes != envelope_before or private_receipts != selected_before
                    or any(regular_file_inventory(stage_before[instance]) != original_inventories[instance]
                           for instance in SDK_CAMPAIGN_INSTANCES)
                    or any(regular_file_inventory(private_stages[instance]) != inventories[instance]
                           for instance in SDK_CAMPAIGN_INSTANCES)):
                raise ValueError("Held SDK campaign selection changed during full verification")
            if verify_sdk_campaign_selection(sources, envelopes, archives, stages) != selected_before:
                raise ValueError("Held SDK campaign original selection changed during full verification")
