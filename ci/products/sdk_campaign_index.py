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
from .inventory import sha256_bytes
from .registry import PhaseInstanceId
from .sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES, held_sdk_campaign_selection


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
