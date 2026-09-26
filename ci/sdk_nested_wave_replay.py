"""Replay a completed failed nested SDK wave into a development-only cache.

This same-source-at-HEAD seam does not select a current run, grant release trust,
or accept incomplete SDK phases. The original failed attempt is selected by the
caller and independently checked against GitHub's run, job, and upload records.
"""

import os
from pathlib import Path
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from . import product_reuse as products
from .products.inventory import (
    canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, sha256_bytes,
)
from .products.receipt import validate_producer
from .products.sdk_package import _require_capability_output_separate
from .products.signing_isolation import require_no_signing_secret
from .sdk_campaign_partial_catalog_caller import stage_partial_sdk_catalog
from .sdk_nested_wave_locator import locate_failed_nested_sdk_wave


def replay_failed_nested_sdk_wave(plan_path, destination, *, producer, wave,
        trusted_workflow_sha, repository_root, environ, token):
    """Authenticate a prior failed attempt's completed phases and cache them.

    The prior attempt must have the same checked-out commit/tree. Historical
    cross-commit plan replay needs a separate Git-revision-aware shared reader.
    """
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    prior = validate_producer(producer)
    if (prior["event"] != "pull_request" or type(wave) is not int
            or wave not in range(11, 17)):
        raise ValueError("Nested SDK replay requires a prior PR wave 11–16")
    root = Path(repository_root).resolve(strict=True)
    plan_path = Path(plan_path).resolve(strict=True)
    destination = Path(destination).absolute()
    _require_capability_output_separate(destination, plan_path)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Nested SDK replay destination must not exist")
    original_plan = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True)
    plan = products._validate_plan(plan_path, root)
    if (plan["repository"] != prior["repository"]
            or plan["event"] != prior["event"]
            or plan["pullRequest"] != prior["pullRequest"]
            or plan["validationCommit"] != prior["commit"]
            or plan["validationTree"] != prior["tree"]):
        raise ValueError("Nested SDK replay requires the prior attempt at checkout HEAD")
    # This environment describes the independently selected historical attempt,
    # not the current runner. Only its two run fields differ from the caller's.
    original_environment = dict(environ)
    original_environment.update(GITHUB_RUN_ID=str(prior["runId"]),
        GITHUB_RUN_ATTEMPT=str(prior["runAttempt"]))
    if products._consumer(plan, original_environment)["producer"] != prior:
        raise ValueError("Nested SDK replay producer differs from the validated plan")
    selected = locate_failed_nested_sdk_wave(prior, wave=wave,
        trusted_workflow_sha=trusted_workflow_sha, token=token, environ=environ)
    with tempfile.TemporaryDirectory(prefix="sdk-nested-wave-replay-", dir=root) as temporary:
        captured = Path(temporary).resolve() / "state-upload"
        transport = products.capture_runtime_resume_upload(plan_path, captured,
            artifact_id=selected["artifact_id"],
            artifact_sha256=selected["artifact_sha256"],
            trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
            environ=original_environment, token=token, sdk_state_wave=wave)
        if (transport.get("captureProducer") != prior
                or transport.get("sdkStateWave") != wave
                or transport.get("artifact", {}).get("id") != selected["artifact_id"]
                or transport["artifact"].get("digest") != selected["artifact_sha256"]):
            raise ValueError("Nested SDK capture differs from the selected failed attempt")
        inventory = regular_file_inventory(captured, allow_empty=True)
        original = captured / "original"
        discovery = original / "product-resume-state"
        state = products._verified_product_state(
            original / "product-resume-inputs/plan/impact-plan.json", discovery,
            original / "runtime-state", root, original_environment, None,
            sdk_original_workflow_sha=trusted_workflow_sha)
        if state.producer != prior:
            raise ValueError("Nested SDK state differs from the selected failed producer")
        _require_capability_output_separate(destination, captured)
        prepared = Path(temporary) / "partial-catalog"
        result = stage_partial_sdk_catalog(state, prepared)
        prepared_inventory = regular_file_inventory(prepared)
        require_no_signing_secret(environ)
        require_no_signing_secret(os.environ)
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != original_plan
                or regular_file_inventory(captured, allow_empty=True) != inventory):
            raise ValueError("Nested SDK original changed during phase replay")
        publish_regular_tree(prepared, destination, expected_inventory=prepared_inventory)
        return {**result, "stateArtifactSha256": selected["artifact_sha256"],
                "stateTransportSha256": sha256_bytes(canonical_json_bytes(transport))}
