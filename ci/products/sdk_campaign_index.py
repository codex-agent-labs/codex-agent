"""Bind a signed SDK campaign index to its exact selected originals.

This verifies index membership and original bytes, not semantic release admission.
The protected signer must establish every component's release proof before signing.
"""

from collections.abc import Mapping
from pathlib import Path

from .index import (
    IndexEntrySource, SignedProductIndex, _verify_index_receipt,
    verify_release_product_index,
)
from .aggregate import validate_product_index
from .inventory import sha256_bytes
from .registry import PhaseInstanceId
from .restore import verify_object
from .sdk_campaign_selection import (
    SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection, verify_sdk_campaign_objects,
)


def verify_release_sdk_campaign_objects(index: dict, objects: Mapping[str, Path], *,
                                        repository: str) -> dict[PhaseInstanceId, dict]:
    """Bind a previously verified, release-signed promoted index to all 62 originals.

    The caller must authenticate the index signature and object transport first.
    Original development receipts remain unchanged; the release signature is the
    separate admission authority. Stable SDK catalogs are not yet produced.
    """
    index = validate_product_index(index)
    if (index["repository"] != repository or index["trustDomain"] != "release"
            or index["context"]["kind"] != "promoted-main"):
        raise ValueError("SDK original catalog requires release-signed promoted-main authority")
    entries = {PhaseInstanceId(*(entry[field] for field in (
        "product", "component", "phase", "target"))): entry for entry in index["entries"]}
    if len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES) or set(entries) != SDK_CAMPAIGN_INSTANCES:
        raise ValueError("SDK release catalog must index every exact SDK campaign phase")
    if len({entry["productVersion"] for entry in index["entries"]}) != 1:
        raise ValueError("SDK release catalog phases must have one SDK version")
    if not isinstance(objects, Mapping) or set(objects) != {entry["buildKey"] for entry in entries.values()}:
        raise ValueError("SDK release catalog lacks the exact indexed original objects")

    sources, envelopes, archives = {}, {}, {}
    for instance, entry in entries.items():
        archive = Path(objects[entry["buildKey"]])
        verified = verify_object(archive, build_key=entry["buildKey"],
                                 receipt_sha256=entry["receiptSha256"])
        envelope = {name: verified[name] for name in (
            "receipt", "receiptBytes", "objectSha256")}
        envelope["receiptSha256"] = entry["receiptSha256"]
        receipt = envelope["receipt"]
        if (receipt["trustDomain"] != "development"
                or receipt["producer"]["repository"] != repository):
            raise ValueError("SDK release catalog original has incompatible provenance or trust")
        _verify_index_receipt(entry, envelope)
        artifacts = [output for output in receipt["outputs"]
                     if output["relativePath"] == entry["artifactName"]]
        if len(artifacts) != 1 or artifacts[0]["sha256"] != entry["artifactSha256"]:
            raise ValueError("SDK release catalog artifact differs from indexed original")
        sources[instance] = IndexEntrySource(envelope["receiptBytes"], entry["artifactName"])
        envelopes[instance] = envelope
        archives[instance] = archive
    verify_sdk_campaign_objects(sources, envelopes, archives)
    return envelopes


def verify_signed_sdk_campaign_originals(
    index_source: SignedProductIndex, *, repository: str, context: dict,
    keyring_path: Path, keys_directory: Path,
    sources: Mapping[PhaseInstanceId, IndexEntrySource],
    envelopes: Mapping[PhaseInstanceId, dict],
    archives: Mapping[PhaseInstanceId, Path],
    stages: Mapping[PhaseInstanceId, Path],
) -> tuple[dict, bytes]:
    """Authenticate the release-signed PR index and all 62 original phase objects."""
    index, raw = verify_release_product_index(
        index_source, keyring_path=keyring_path, keys_directory=keys_directory,
    )
    if (index["repository"] != repository or index["context"] != context
            or index["context"]["kind"] != "pull-request"
            or index["trustDomain"] != "release"):
        raise ValueError("SDK campaign index has the wrong release context")
    with held_sdk_campaign_selection(sources, envelopes, archives, stages) as (
        originals, held_envelopes, _, receipts,
    ):
        entries = {
            PhaseInstanceId(*(entry[field] for field in (
                "product", "component", "phase", "target",
            ))): entry for entry in index["entries"]
        }
        if len(index["entries"]) != len(SDK_CAMPAIGN_INSTANCES) or set(entries) != SDK_CAMPAIGN_INSTANCES:
            raise ValueError("SDK campaign index does not contain every exact phase")
        for instance, entry in entries.items():
            original = originals[instance]
            receipt = receipts[instance]
            if receipt["trustDomain"] != "development":
                raise ValueError("SDK campaign original receipt must retain development trust")
            if receipt["producer"]["repository"] != repository:
                raise ValueError("SDK campaign original receipt belongs to another repository")
            producer = receipt["producer"]
            if producer["event"] != "push" and not (
                producer["event"] == "pull_request"
                and producer["pullRequest"] == context["pullRequest"]
            ):
                raise ValueError("SDK campaign original receipt belongs to another producer context")
            _verify_index_receipt(entry, held_envelopes[instance])
            artifact = next(
                (output for output in receipt["outputs"]
                 if output["relativePath"] == original.artifact_path), None,
            )
            if (entry["receiptSha256"] != sha256_bytes(original.receipt_bytes)
                    or artifact is None or entry["artifactName"] != original.artifact_path
                    or entry["artifactSha256"] != artifact["sha256"]):
                raise ValueError("SDK campaign index differs from the selected original artifact")
    return index, raw
