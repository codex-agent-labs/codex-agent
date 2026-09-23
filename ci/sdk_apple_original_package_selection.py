"""Caller-owned original Apple package selection after authenticated reuse lookup.

The factory accepts only the reuse engine's authenticated envelope.  Original
plan, package and SDK-input uploads are then independently observed and captured
from their fixed jobs.  It returns the existing full semantic admission object;
no captured descriptor or transport record is treated as product authority.
"""

import os
from pathlib import Path
import sys

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse
from products.inventory import (
    git_product_versions, load_canonical_json_bytes, read_regular_file_bytes,
    require_exact_keys, require_integer, require_sha256,
    verified_zip_contents, write_canonical_json,
)
from products.registry import PhaseInstanceId
from products.restore import restore_object, verify_phase_shard
from products.reuse import _validate_envelope, _dependency_closure
from products.sdk_apple_package_admission import ApplePackageAdmission
from products.sdk_package import _require_capability_output_separate
from products.sdk_release_selection import sdk_runtime_source
from products.signing_isolation import require_no_signing_secret
from receipt import safe_extract
from sdk_apple_source import _original_upload
from sdk_apple_upload_locator import locate_original_apple_upload


_INSTANCE = PhaseInstanceId("sdk", "sdk-ios", "package", "ios")
_PLAN_JOB = "product-validation / plan"


class OriginalApplePackageSelector:
    """Produce concrete admission from one authenticated post-lookup envelope.

    The caller owns a fresh external scratch directory for the entire reuse-wave
    call and supplies only current, independently pinned workflow/tooling policy.
    All files remain external evidence and must outlive admission.verify().
    """

    def __init__(self, scratch_root, *, repository_root, trusted_workflow_sha,
            keyring, keys_directory, tooling_evidence, tooling_public_key,
            java_executable, policy_revision, required_trust_domain,
            environ, token, tooling_keyring=None, tooling_keys_directory=None):
        self._repository = Path(repository_root).resolve(strict=True)
        self._scratch = Path(scratch_root).resolve(strict=True)
        _require_capability_output_separate(self._scratch, self._repository)
        if not self._scratch.is_dir() or not token:
            raise ValueError("Apple package selection needs fresh external scratch and observation token")
        self._workflow_sha = trusted_workflow_sha
        self._environ = environ
        self._token = token
        self._policy = dict(repository_root=self._repository, keyring=keyring,
            keys_directory=keys_directory, tooling_evidence=tooling_evidence,
            tooling_public_key=tooling_public_key, java_executable=java_executable,
            policy_revision=policy_revision, required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring, tooling_keys_directory=tooling_keys_directory)

    def __call__(self, envelope):
        require_no_signing_secret(os.environ)
        require_no_signing_secret(self._environ)
        instance, selected = _validate_envelope(envelope)
        if instance != _INSTANCE:
            raise ValueError("Original Apple selector requires an authenticated iOS package envelope")
        raw = selected["receiptBytes"]
        receipt = selected["receipt"]
        producer = receipt["producer"]
        if producer["repository"] != "codex-agent-labs/codex-agent" or producer["event"] not in (
                "pull_request", "merge_group"):
            raise ValueError("Original Apple package requires its hosted repository producer")
        destination = self._scratch / selected["receiptSha256"].removeprefix("sha256:")
        destination.mkdir(mode=0o700)
        selected_receipt = destination / "selected-receipt.json"
        selected_receipt.write_bytes(raw)

        observations = product_reuse._observe_ci_producer_jobs(
            {"plan": producer}, jobs_by_phase={"plan": _PLAN_JOB},
            trusted_workflow_sha=self._workflow_sha, token=self._token)
        artifacts = product_reuse.paginated_items(
            f"https://api.github.com/repos/{producer['repository']}/actions/runs/{producer['runId']}/artifacts",
            "artifacts", self._token)
        artifact, plan_zip = _original_upload(
            name=f"codex-agent-ci-plan-{producer['tree']}", producer=producer,
            observation=observations[0], job=_PLAN_JOB, artifacts=artifacts, token=self._token)
        plan_archive = destination / "original-plan-upload.zip"
        plan_archive.write_bytes(plan_zip)
        verified_zip_contents(plan_archive, retained_paths=(), allow_empty_members=True,
                              **product_reuse._CATALOG_ZIP_LIMITS)
        plan_root = destination / "original-plan-upload"
        safe_extract(plan_archive, plan_root)
        plan = plan_root / "impact-plan.json"
        validated = product_reuse._validate_plan(plan, self._repository,
                                                  expected_revision=producer["commit"])
        original_environment = {"GITHUB_RUN_ID": str(producer["runId"]),
                                "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])}
        if (validated.get("remoteBuildAuthorized") is not True
                or validated.get("event") == "workflow_dispatch"
                or product_reuse._consumer(validated, original_environment)["producer"] != producer):
            raise ValueError("Original Apple plan differs from its selected package producer")
        write_canonical_json(destination / "original-plan-transport.json", {
            "artifact": artifact, "producer": producer, "observed": observations,
        })

        locator = locate_original_apple_upload(selected_receipt,
            trusted_workflow_sha=self._workflow_sha, token=self._token,
            environ=self._environ)
        package_capture = destination / "package-capture"
        product_reuse.capture_sdk_ios_package_upload(plan, package_capture,
            package_receipt_path=selected_receipt,
            artifact_id=locator["artifact_id"], artifact_sha256=locator["artifact_sha256"],
            trusted_workflow_sha=self._workflow_sha, repository_root=self._repository,
            environ=self._environ, token=self._token)
        shard = verify_phase_shard(package_capture / "original/shard", _INSTANCE)
        if (shard["receiptBytes"] != raw or shard["receiptSha256"] != selected["receiptSha256"]
                or shard["objectSha256"] != selected["objectSha256"]):
            raise ValueError("Official Apple package upload differs from the authenticated selected object")

        # The captured descriptor supplies only an upload locator claim.  The
        # separate S858 capture re-observes the fixed original job and digest.
        descriptor = load_canonical_json_bytes(read_regular_file_bytes(
            package_capture / "original/apple-package-execution.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        if type(descriptor) is not dict:
            raise ValueError("Original Apple package execution descriptor is invalid")
        hint = require_exact_keys(descriptor.get("sdkInputsArtifact"),
                                  {"artifactId", "artifactSha256"}, "Original S858 locator hint")
        sdk_artifact_id = require_integer(hint["artifactId"], "Original S858 artifact ID", 1)
        sdk_artifact_digest = require_sha256(hint["artifactSha256"], "Original S858 artifact digest")
        versions = git_product_versions(self._repository, producer["commit"])
        if versions["sdk"] != receipt["productVersion"]:
            raise ValueError("Original Apple package differs from its Git SDK version")
        source = sdk_runtime_source(self._repository, producer["commit"],
            instances=_dependency_closure((_INSTANCE,)), runtime_version=versions["runtime-release"],
            sdk_version=versions["sdk"]) or "current-runtime"
        sdk_capture = destination / "sdk-capture"
        product_reuse.capture_sdk_inputs_upload(plan, sdk_capture,
            artifact_id=sdk_artifact_id, artifact_sha256=sdk_artifact_digest,
            trusted_workflow_sha=self._workflow_sha, expected_source=source,
            repository_root=self._repository, environ=self._environ, token=self._token,
            original_package_receipt_path=selected_receipt)
        selected_stage = destination / "selected-stage"
        restored = restore_object(package_capture / "original/shard" / shard["objectPath"],
            selected_stage, build_key=shard["buildKey"],
            receipt_sha256=shard["receiptSha256"], object_sha256=shard["objectSha256"])
        if restored["receiptBytes"] != raw:
            raise ValueError("Restored Apple package differs from the authenticated selected receipt")
        require_no_signing_secret(os.environ)
        require_no_signing_secret(self._environ)
        if read_regular_file_bytes(selected_receipt, reject_symlink_parents=True) != raw:
            raise ValueError("Selected Apple receipt changed during original capture")
        return ApplePackageAdmission([{
            "receiptSha256": selected["receiptSha256"], "selectedStage": selected_stage,
            "selectedReceipt": selected_receipt, "plan": plan,
            "packageCapture": package_capture, "sdkCapture": sdk_capture,
        }], **self._policy)
