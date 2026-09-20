"""Protected Apple evidence signing after independently authenticated preparation.

Run from independently pinned source on a fresh protected runner. Candidate Git
is data only. This controller never executes Apple replay/tooling.
Environment approval remains workflow-owned, not inferred from this function.
"""

from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from product_release_context import verify_product_release_context
from product_reuse import _validate_plan, _consumer, _release_trust, capture_sdk_ios_validation_upload
from runtime_aggregate_release import _destination
from sdk_apple_preparation_capture import capture_apple_signing_preparation
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_integer, require_sha256, sha256_bytes, snapshot_regular_tree, write_canonical_json,
)
from products.sdk_apple_validation_attestation import (
    ATTESTATION_NAME, derive_apple_validation_attestation, verified_prepared_apple_validation,
)
from products.sdk_apple_validation_inputs import capture_sdk_apple_validation_evidence
from products.signatures import load_keyring, require_active_release_key, sign_manifest, verify_manifest_signature


def attest_prepared_apple_validation_ci(repository_root, candidate_root, plan_path,
        validation_receipt_path, destination, *, target, expected_receipt_sha256,
        artifact_id, artifact_sha256, preparation_artifact_id, preparation_artifact_sha256,
        trusted_source_sha, trusted_workflow_sha, transport_producer, event_payload, environment, token):
    """Sign exact prepared capture bytes; never build, replay, or reissue receipts."""
    if target not in ("ios-arm64", "ios-simulator-arm64"):
        raise ValueError("Protected Apple signing requires an exact validation target")
    for digest in (expected_receipt_sha256, artifact_sha256, preparation_artifact_sha256):
        require_sha256(digest, "Protected Apple selected digest")
    for identifier in (artifact_id, preparation_artifact_id):
        require_integer(identifier, "Protected Apple artifact ID", 1)
    if type(token) is not str or not token:
        raise ValueError("Protected Apple signing requires an observation token")
    event_bytes = canonical_json_bytes(event_payload)
    trusted, producer, source_tree, expected_environment, reason = verify_product_release_context(
        repository_root, trusted_source_sha=trusted_source_sha, trusted_workflow_sha=trusted_workflow_sha,
        transport_producer=transport_producer, event_payload=event_payload, environment=environment)
    candidate = Path(candidate_root).resolve(strict=True)
    if trusted == candidate or trusted in candidate.parents or candidate in trusted.parents:
        raise ValueError("Apple signing requires separate trusted and candidate checkouts")
    protected = (trusted, candidate, Path(plan_path), Path(validation_receipt_path))
    output = _destination(destination, protected)
    files = {"plan": Path(plan_path), "receipt": Path(validation_receipt_path)}
    originals = {name: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
                 for name, path in files.items()}
    if sha256_bytes(originals["receipt"]) != expected_receipt_sha256:
        raise ValueError("Apple signing receipt differs from caller-selected digest")
    with tempfile.TemporaryDirectory(prefix="apple-prepared-release-") as temporary:
        root = Path(temporary).resolve()
        plan_path, receipt_path = root / "impact-plan.json", root / "receipt.json"
        plan_path.write_bytes(originals["plan"])
        receipt_path.write_bytes(originals["receipt"])
        plan = _validate_plan(plan_path, candidate)
        if (plan["remoteBuildAuthorized"] is not True or plan["event"] not in {"pull_request", "merge_group"}
                or _consumer(plan, environment)["producer"] != producer):
            raise ValueError("Apple signing plan differs from protected caller context")
        prepared, original = root / "preparation-transport", root / "validation-transport"
        capture_apple_signing_preparation(plan_path, prepared, target=target,
            artifact_id=preparation_artifact_id, artifact_sha256=preparation_artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate, environ=environment, token=token)
        capture_sdk_ios_validation_upload(plan_path, original, validation_receipt_path=receipt_path,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            trusted_workflow_sha=trusted_workflow_sha, repository_root=candidate, environ=environment, token=token)
        baselines = {path: regular_file_inventory(path, allow_empty=True) for path in (prepared, original)}

        def unchanged():
            if (canonical_json_bytes(event_payload) != event_bytes
                    or any(environment.get(name) != value for name, value in expected_environment.items())
                    or any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != originals[name] for name, path in files.items())
                    or read_regular_file_bytes(plan_path) != originals["plan"]
                    or read_regular_file_bytes(receipt_path) != originals["receipt"]
                    or any(regular_file_inventory(path, allow_empty=True) != before
                           for path, before in baselines.items())):
                raise ValueError("Protected Apple original inputs changed during signing")

        unchanged()
        result = root / "result"
        entry = root / "entry"
        with verified_prepared_apple_validation(prepared / "original", original,
                plan=plan_path, receipt_path=receipt_path, target=target,
                expected_receipt_sha256=expected_receipt_sha256,
                artifact_id=artifact_id, artifact_sha256=artifact_sha256) as verified:
            trust = _release_trust(trusted, trusted_source_sha, root / "policy")
            if trust is None:
                raise ValueError("Apple signing requires pinned release key policy")
            baselines[root / "policy"] = regular_file_inventory(root / "policy", allow_empty=True)
            policy = load_keyring(trust.keyring, trust.keys)
            active, public_key = require_active_release_key(policy, trust.keys)
            signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
            signing.update(active)
            snapshot_regular_tree(verified["capture"], entry / "capture", allow_empty=True)
            if regular_file_inventory(entry / "capture", allow_empty=True) != \
                    regular_file_inventory(verified["capture"], allow_empty=True):
                raise ValueError("Apple evidence capture changed during signing copy")
            attestation = derive_apple_validation_attestation(entry / "capture", verified["receiptBytes"], signing)
            manifest = entry / ATTESTATION_NAME
            write_canonical_json(manifest, attestation)
            unchanged()
            secret = environment.get("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY")
            if type(secret) is not str or not secret:
                raise ValueError("Protected Apple signing key is unavailable")
            private_key = root / "private-key"
            private_key.touch(mode=0o600, exist_ok=False)
            private_key.write_bytes(secret.encode("utf-8"))
            signature = sign_manifest(manifest, private_key, signing)
            verify_manifest_signature(manifest, signature, public_key, signing)
            if read_regular_file_bytes(manifest) != canonical_json_bytes(attestation):
                raise ValueError("Apple attestation changed during signing")
            baselines[entry] = regular_file_inventory(entry, allow_empty=True)
            capture_sdk_apple_validation_evidence([entry], result / "sdk-apple-validation-evidence")
            baselines[result / "sdk-apple-validation-evidence"] = regular_file_inventory(
                result / "sdk-apple-validation-evidence", allow_empty=True)
            unchanged()
        # Nothing reaches the caller until the immutable binding context exits.
        unchanged()
        for source, name in ((prepared, "preparation-transport"), (original, "validation-transport"),
                             (root / "policy", "caller-policy")):
            snapshot_regular_tree(source, result / name, allow_empty=True)
            if regular_file_inventory(result / name, allow_empty=True) != baselines[source]:
                raise ValueError("Apple signing provenance changed during forwarding")
        caller = {"schemaVersion": 1, "target": target, "trustedSourceCommit": trusted_source_sha,
            "trustedSourceTree": source_tree, "trustedWorkflowSha": trusted_workflow_sha,
            "transportProducer": producer, "authorizationReason": reason,
            "event": load_canonical_json_bytes(event_bytes),
            "receiptSha256": expected_receipt_sha256,
            "preparationArtifact": {"artifactId": preparation_artifact_id, "artifactSha256": preparation_artifact_sha256},
            "originalArtifact": {"artifactId": artifact_id, "artifactSha256": artifact_sha256}}
        write_canonical_json(result / "caller.json", caller)
        unchanged()
        _destination(output, protected)
        publish_regular_tree(result, output, allow_empty=True)
    return caller
