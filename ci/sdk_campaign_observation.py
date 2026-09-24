"""Hold the exact SDK originals from one independently observed state upload.

The state upload is current-run transport, not the producer of reused phases.
Original receipts and replay records remain separate. This grants no semantic
or release admission and deliberately does not choose index artifact paths.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    canonical_json_bytes, read_regular_file_bytes, regular_file_inventory,
    sha256_bytes, sha256_file,
)
from products.receipt import verify_output_manifest_identity
from products.restore import restore_object, verify_object
from products.sdk_campaign_selection import SDK_CAMPAIGN_INSTANCES
from products.signing_isolation import require_no_signing_secret


@dataclass(frozen=True)
class ObservedSdkOriginal:
    receipt_bytes: bytes
    replay_record_canonical: bytes
    object_path: Path
    stage_path: Path


@contextmanager
def held_sdk_campaign_observation(plan_path, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, state_wave=0, sdk_state_wave=None,
        repository_root, environ, token,
        sdk_validation_tooling=None, sdk_apple_validation_policy=None,
        sdk_facade_metadata_admission=None,
        sdk_android_metadata_admission=None):
    """Observe one official state upload, then hold all 61 original object bytes.

    The caller still owns the exact terminal state locator and all semantic
    policies. Its release signer must independently authenticate this transport,
    each original producer/retrieval route, and full family replay.
    """
    require_no_signing_secret(environ)
    root = Path(repository_root).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="sdk-campaign-observation-", dir=root) as temporary:
        private = Path(temporary).resolve()
        captured = private / "state-upload"
        transport = product_reuse.capture_runtime_resume_upload(
            Path(plan_path), captured, artifact_id=artifact_id,
            artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
            sdk_state_wave=sdk_state_wave, state_wave=state_wave, repository_root=root,
            environ=environ, token=token)
        transport_bytes = read_regular_file_bytes(captured / "capture-transport.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        if canonical_json_bytes(transport) != transport_bytes:
            raise ValueError("Observed SDK transport differs from its original capture")
        captured_inventory = regular_file_inventory(captured, allow_empty=True)
        original = captured / "original"
        discovery = original / "product-resume-state"
        state_root = original / "runtime-state" if state_wave or sdk_state_wave is not None else discovery
        original_plan = original / "product-resume-inputs/plan/impact-plan.json"
        state = product_reuse._verified_product_state(
            original_plan, discovery, state_root, root, environ,
            sdk_validation_tooling, sdk_apple_validation_policy=sdk_apple_validation_policy,
            sdk_original_workflow_sha=trusted_workflow_sha,
            sdk_facade_metadata_admission=sdk_facade_metadata_admission,
            sdk_android_metadata_admission=sdk_android_metadata_admission)
        if not SDK_CAMPAIGN_INSTANCES <= set(state.prior_by_instance):
            raise ValueError("Observed SDK state lacks the exact 61-phase campaign")
        if not SDK_CAMPAIGN_INSTANCES <= set(state.sources) or not SDK_CAMPAIGN_INSTANCES <= set(state.prior_carrier_phases):
            raise ValueError("Observed SDK carrier lacks an original phase object")
        observations = {}
        archive_digests = {}
        for position, instance in enumerate(sorted(SDK_CAMPAIGN_INSTANCES)):
            replay = state.prior_by_instance[instance]
            carrier = state.prior_carrier_phases[instance]
            if replay["state"] not in {"retained", "reused"}:
                raise ValueError("Observed SDK phase is not complete")
            if any(replay[field] != carrier[field] for field in (
                    "product", "component", "phase", "target", "buildKey", "receiptSha256", "objectSha256")):
                raise ValueError("Observed SDK carrier differs from its original replay record")
            archive = Path(state.sources[instance])
            verified = verify_object(archive, build_key=carrier["buildKey"],
                receipt_sha256=carrier["receiptSha256"], object_sha256=carrier["objectSha256"])
            archive_digests[instance] = carrier["objectSha256"]
            stage = private / "stages" / str(position)
            restored = restore_object(archive, stage, build_key=carrier["buildKey"],
                receipt_sha256=carrier["receiptSha256"], object_sha256=carrier["objectSha256"])
            receipt = verified["receipt"]
            if (restored["receiptBytes"] != verified["receiptBytes"]
                    or sha256_bytes(verified["receiptBytes"]) != carrier["receiptSha256"]):
                raise ValueError("Observed SDK object differs from its original receipt")
            manifest = verify_output_manifest_identity(stage, instance.product,
                instance.component, instance.phase, instance.target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Observed SDK stage differs from its original receipt")
            observations[instance] = ObservedSdkOriginal(
                verified["receiptBytes"], canonical_json_bytes(replay), archive, stage)
        if regular_file_inventory(captured, allow_empty=True) != captured_inventory:
            raise ValueError("Observed SDK transport changed during original replay")
        stage_inventories = {instance: regular_file_inventory(value.stage_path)
                             for instance, value in observations.items()}
        require_no_signing_secret(environ)
        try:
            yield transport_bytes, MappingProxyType(observations)
        finally:
            require_no_signing_secret(environ)
            if (regular_file_inventory(captured, allow_empty=True) != captured_inventory
                    or read_regular_file_bytes(captured / "capture-transport.json",
                        max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != transport_bytes
                    or any(sha256_file(value.object_path) != archive_digests[instance]
                           for instance, value in observations.items())
                    or any(regular_file_inventory(value.stage_path) != stage_inventories[instance]
                           for instance, value in observations.items())):
                raise ValueError("Observed SDK campaign changed during replay")
