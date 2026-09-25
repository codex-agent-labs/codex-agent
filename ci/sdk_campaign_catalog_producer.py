"""Hold all 61 authenticated SDK originals for a no-secret campaign replay.

The protected caller selects the pins independently of the captured state and
runs the full SDK semantic verifier inside this context. This is neither a
release admission nor a signed catalog producer.
"""

from collections.abc import Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ci.sdk_campaign_observation import ObservedSdkOriginal
from ci.sdk_campaign_original_worker import held_fresh_sdk_worker_upload
from ci.sdk_campaign_reused_original import held_reused_sdk_original
from products.inventory import load_canonical_json_bytes, require_integer, require_sha256
from products.registry import PhaseInstanceId
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


@dataclass(frozen=True, slots=True)
class FreshSdkOriginalPin:
    receipt_sha256: str
    artifact_id: int
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class ReusedSdkOriginalPin:
    receipt_sha256: str
    original_artifact_id: int
    original_artifact_sha256: str
    catalog_artifact_id: int
    catalog_artifact_sha256: str
    catalog_public_key: Path
    catalog_public_key_sha256: str
    pull_request: int


@contextmanager
def held_sdk_campaign_original_uploads(observations, current_transport_bytes, pins, *,
        trusted_workflow_sha, token, environ):
    """Hold exact original uploads across the caller's all-family semantic replay.

    The 61 pins must come from protected, independent policy/official discovery;
    deriving them from observations or replay records defeats this boundary.
    """
    require_no_signing_secret(environ)
    if (not isinstance(observations, Mapping) or not isinstance(pins, Mapping)
            or set(observations) != SDK_CAMPAIGN_INSTANCES
            or set(pins) != SDK_CAMPAIGN_INSTANCES
            or type(current_transport_bytes) is not bytes):
        raise ValueError("SDK original uploads require the exact 61 observed phases and pins")
    for instance in SDK_CAMPAIGN_INSTANCES:
        original, pin = observations[instance], pins[instance]
        if not isinstance(instance, PhaseInstanceId) or not isinstance(original, ObservedSdkOriginal):
            raise ValueError("SDK original upload has an invalid phase or observation")
        replay = load_canonical_json_bytes(original.replay_record_canonical)
        if not isinstance(replay, dict):
            raise ValueError("SDK original replay record is invalid")
        if replay.get("state") == "retained" and replay.get("source") is None:
            if type(pin) is not FreshSdkOriginalPin:
                raise ValueError("Retained SDK original requires a fresh upload pin")
            require_sha256(pin.receipt_sha256, "Fresh SDK receipt pin")
            require_sha256(pin.artifact_sha256, "Fresh SDK artifact pin")
            require_integer(pin.artifact_id, "Fresh SDK artifact ID", 1)
        elif replay.get("state") == "reused" and replay.get("source") == "same-pr":
            if type(pin) is not ReusedSdkOriginalPin:
                raise ValueError("Reused SDK original requires a same-PR catalog pin")
            for label, digest in (("Reused SDK receipt", pin.receipt_sha256),
                                  ("Reused SDK original artifact", pin.original_artifact_sha256),
                                  ("Reused SDK catalog artifact", pin.catalog_artifact_sha256),
                                  ("Reused SDK catalog key", pin.catalog_public_key_sha256)):
                require_sha256(digest, label)
            for label, value in (("Reused SDK original artifact ID", pin.original_artifact_id),
                                 ("Reused SDK catalog artifact ID", pin.catalog_artifact_id),
                                 ("Reused SDK pull request", pin.pull_request)):
                require_integer(value, label, 1)
            if not isinstance(pin.catalog_public_key, Path):
                raise ValueError("Reused SDK catalog key requires an independent path")
        else:
            raise ValueError("SDK original upload has no authenticated retained/same-PR route")

    held = {}
    with ExitStack() as stack:
        for instance in sorted(SDK_CAMPAIGN_INSTANCES):
            original, pin = observations[instance], pins[instance]
            if type(pin) is FreshSdkOriginalPin:
                evidence, _ = stack.enter_context(held_fresh_sdk_worker_upload(
                    instance, original, current_transport_bytes,
                    expected_receipt_sha256=pin.receipt_sha256,
                    artifact_id=pin.artifact_id, artifact_sha256=pin.artifact_sha256,
                    trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ))
            else:
                evidence, _ = stack.enter_context(held_reused_sdk_original(
                    instance, original, current_transport_bytes,
                    expected_receipt_sha256=pin.receipt_sha256,
                    original_artifact_id=pin.original_artifact_id,
                    original_artifact_sha256=pin.original_artifact_sha256,
                    catalog_artifact_id=pin.catalog_artifact_id,
                    catalog_artifact_sha256=pin.catalog_artifact_sha256,
                    catalog_public_key=pin.catalog_public_key,
                    expected_public_key_sha256=pin.catalog_public_key_sha256,
                    pull_request=pin.pull_request,
                    trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ))
            held[instance] = evidence
        require_no_signing_secret(environ)
        try:
            yield MappingProxyType(held)
        finally:
            require_no_signing_secret(environ)
