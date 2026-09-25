"""Join official nested Firebase artifacts to the existing full Android reader.

The validation worker upload is not authority for the two captures it embeds.
This context re-observes those artifacts with the existing fixed locators and
requires exact byte inventories while the existing semantic reader is held.
It mints no receipt, host token, or Firebase verdict.
"""

from contextlib import contextmanager
from pathlib import Path
import re
import tempfile

if __package__:
    from .products.inventory import (
        canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
        regular_file_inventory, require_integer, sha256_file,
    )
    from .products.receipt import validate_producer
    from .products.signing_isolation import require_no_signing_secret
    from .sdk_android_evidence_capture import capture_android_evidence
    from .sdk_android_firebase_capture import capture_android_firebase_evidence
    from .sdk_android_original_validation import verified_original_android_validation
else:
    from products.inventory import (
        canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
        regular_file_inventory, require_integer, sha256_file,
    )
    from products.receipt import validate_producer
    from products.signing_isolation import require_no_signing_secret
    from sdk_android_evidence_capture import capture_android_evidence
    from sdk_android_firebase_capture import capture_android_firebase_evidence
    from sdk_android_original_validation import verified_original_android_validation


_OID = re.compile(r"[0-9a-f]{40}")
_LIMIT = 16 * 1024 * 1024


def _read(path):
    return read_regular_file_bytes(
        Path(path), max_bytes=_LIMIT, reject_symlink_parents=True)


def _transport_identity(root):
    value = load_canonical_json_bytes(_read(Path(root) / "capture-transport.json"))
    fields = {"schemaVersion", "kind", "locator", "captureProducer", "laneReceiptSha256"}
    if value.get("kind") == "android-firebase-transport":
        fields.update(("inputBindingSha256", "linkedFinalCaptureSha256",
                       "linkedFinalLaneReceiptSha256"))
    return {name: value[name] for name in fields}


def _same_capture(retained, observed, label):
    retained, observed = Path(retained), Path(observed)
    if (sha256_file(retained / "original-upload.zip") !=
            sha256_file(observed / "original-upload.zip")
            or regular_file_inventory(retained / "original", allow_empty=True) !=
            regular_file_inventory(observed / "original", allow_empty=True)
            or regular_file_inventory(retained / "plan", allow_empty=True) !=
            regular_file_inventory(observed / "plan", allow_empty=True)
            or _transport_identity(retained) != _transport_identity(observed)):
        raise ValueError(f"Original Android {label} differs from its official artifact")


def _linked(final, protected, label):
    if (_read(final / "capture-transport.json") !=
            _read(protected / "linked-final/capture-transport.json")
            or _read(final / "original/lane-receipt.json") !=
            _read(protected / "linked-final/lane-receipt.json")):
        raise ValueError(f"Original Android {label} protected-to-final linkage changed")


@contextmanager
def verified_original_android_firebase_validation(
        plan, validation_receipt_path, *, validation_artifact_id,
        validation_artifact_sha256, trusted_workflow_sha,
        trusted_android_workflow_sha, expected_original_run_id,
        expected_original_run_attempt, package_stage, package_receipt,
        binary_stage, binary_receipt, compatibility_request,
        binary_contract_evidence, trusted_source_commit, trusted_source_tree,
        tooling_evidence, tooling_public_key, java_executable,
        apkanalyzer_executable, policy_revision, required_trust_domain,
        repository_root, environ, token, tooling_keyring=None,
        tooling_keys_directory=None, trusted_workflow_path=None,
        trusted_job_name=None):
    """Hold official nested captures and the complete existing semantic replay.

    The caller independently selects every workflow/source pin and the original
    run identity. Only PR/merge-group routes admitted by the existing locators
    are supported; protected workflow-dispatch approval remains fail-closed.
    """
    require_no_signing_secret(environ)
    if (trusted_workflow_path is None) != (trusted_job_name is None):
        raise ValueError("Original Android validation workflow path and job must be pinned together")
    pins = (trusted_workflow_sha, trusted_android_workflow_sha,
            trusted_source_commit, trusted_source_tree)
    if any(type(value) is not str or _OID.fullmatch(value) is None for value in pins):
        raise ValueError("Original Android Firebase admission requires exact caller Git pins")
    run_id = require_integer(expected_original_run_id, "Original Android run ID", 1)
    attempt = require_integer(expected_original_run_attempt, "Original Android run attempt", 1)
    if type(token) is not str or not token:
        raise ValueError("Original Android Firebase admission requires an observation token")
    authority = canonical_json_bytes({
        "trustedWorkflowSha": trusted_workflow_sha,
        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
        "trustedSourceCommit": trusted_source_commit,
        "trustedSourceTree": trusted_source_tree,
        "trustedWorkflowPath": trusted_workflow_path,
        "trustedJobName": trusted_job_name,
        "runId": run_id, "runAttempt": attempt,
    })
    root = Path(repository_root).resolve(strict=True)
    reader_arguments = dict(
        artifact_id=validation_artifact_id,
        artifact_sha256=validation_artifact_sha256,
        trusted_workflow_sha=trusted_workflow_sha,
        package_stage=package_stage, package_receipt=package_receipt,
        binary_stage=binary_stage, binary_receipt=binary_receipt,
        compatibility_request=compatibility_request,
        binary_contract_evidence=binary_contract_evidence,
        trusted_source_commit=trusted_source_commit,
        trusted_source_tree=trusted_source_tree,
        tooling_evidence=tooling_evidence,
        tooling_public_key=tooling_public_key,
        java_executable=java_executable,
        apkanalyzer_executable=apkanalyzer_executable,
        policy_revision=policy_revision,
        required_trust_domain=required_trust_domain,
        repository_root=root, environ=environ, token=token,
        tooling_keyring=tooling_keyring,
        tooling_keys_directory=tooling_keys_directory,
        trusted_workflow_path=trusted_workflow_path,
        trusted_job_name=trusted_job_name,
    )
    with verified_original_android_validation(
            plan, validation_receipt_path, **reader_arguments) as held:
        producer = validate_producer(
            held["receipt"]["producer"], "Original Android validation producer")
        if (producer["runId"] != run_id or producer["runAttempt"] != attempt):
            raise ValueError("Original Android validation differs from the caller-selected run")
        original = Path(held["original"])
        retained_final = original / "originals/final"
        retained_protected = original / "originals/protected"
        retained_before = {
            "final": regular_file_inventory(retained_final, allow_empty=True),
            "protected": regular_file_inventory(retained_protected, allow_empty=True),
        }
        _linked(retained_final, retained_protected, "retained")
        historical_plan = retained_final / "plan/impact-plan.json"
        if _read(historical_plan) != _read(retained_protected / "plan/impact-plan.json"):
            raise ValueError("Original Android nested captures selected different plans")
        historical_environment = dict(environ)
        historical_environment.update({
            "GITHUB_RUN_ID": str(run_id),
            "GITHUB_RUN_ATTEMPT": str(attempt),
        })
        with tempfile.TemporaryDirectory(prefix="original-android-firebase-") as temporary:
            private = Path(temporary).resolve()
            observed_final, observed_protected = private / "final", private / "protected"
            capture_android_evidence(
                historical_plan, root, observed_final,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                environ=historical_environment, token=token, expected_revision=producer["commit"])
            capture_android_firebase_evidence(
                historical_plan, root, observed_final, observed_protected,
                trusted_workflow_sha=trusted_workflow_sha,
                trusted_android_workflow_sha=trusted_android_workflow_sha,
                trusted_source_commit=trusted_source_commit,
                trusted_source_tree=trusted_source_tree,
                environ=historical_environment, token=token, expected_revision=producer["commit"])
            _same_capture(retained_final, observed_final, "final capture")
            _same_capture(retained_protected, observed_protected, "protected capture")
            _linked(observed_final, observed_protected, "official")
            observed_before = {
                "final": regular_file_inventory(observed_final, allow_empty=True),
                "protected": regular_file_inventory(observed_protected, allow_empty=True),
            }

            def unchanged():
                require_no_signing_secret(environ)
                if (canonical_json_bytes({
                        "trustedWorkflowSha": trusted_workflow_sha,
                        "trustedAndroidWorkflowSha": trusted_android_workflow_sha,
                        "trustedSourceCommit": trusted_source_commit,
                        "trustedSourceTree": trusted_source_tree,
                        "trustedWorkflowPath": trusted_workflow_path,
                        "trustedJobName": trusted_job_name,
                        "runId": run_id, "runAttempt": attempt,
                    }) != authority
                        or regular_file_inventory(retained_final, allow_empty=True) != retained_before["final"]
                        or regular_file_inventory(retained_protected, allow_empty=True) != retained_before["protected"]
                        or regular_file_inventory(observed_final, allow_empty=True) != observed_before["final"]
                        or regular_file_inventory(observed_protected, allow_empty=True) != observed_before["protected"]):
                    raise ValueError("Original Android official Firebase evidence changed")
                _same_capture(retained_final, observed_final, "final capture")
                _same_capture(retained_protected, observed_protected, "protected capture")
                _linked(retained_final, retained_protected, "retained")
                _linked(observed_final, observed_protected, "official")

            try:
                unchanged()
                yield held
            finally:
                unchanged()
