"""Capture one caller-bound Apple CI upload and run the existing full source gate.

This is transport composition, not producer or source authority.  The caller
chooses the official artifact identity and reviewed workflow revision; the
retained lane receipt chooses only the original attempt that must separately
pass the fixed CI observer.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import tempfile
from typing import Mapping

if __package__:
    from . import product_reuse
    from .receipt import INPUT_NAMES, safe_extract, validate_receipt
    from .products.contract_projection import VerifiedContractProjection
    from .products.inventory import (
        publish_regular_tree,
        read_regular_file_bytes,
        regular_file_inventory,
        require_sha256,
        require_string,
        sha256_bytes,
        snapshot_regular_tree,
        verified_zip_contents,
        write_canonical_json,
    )
    from .products.receipt import validate_producer
    from .products.sdk_apple_source import verify_sdk_apple_original_source
else:
    import product_reuse
    from receipt import INPUT_NAMES, safe_extract, validate_receipt
    from products.contract_projection import VerifiedContractProjection
    from products.inventory import (
        publish_regular_tree,
        read_regular_file_bytes,
        regular_file_inventory,
        require_sha256,
        require_string,
        sha256_bytes,
        snapshot_regular_tree,
        verified_zip_contents,
        write_canonical_json,
    )
    from products.receipt import validate_producer
    from products.sdk_apple_source import verify_sdk_apple_original_source


_JOB = "product-validation / apple / swift-tests"
_DISTRIBUTION = Path("payload/codex-agent-runtime-ios/build/apple-verified-distribution")
_EXECUTION = Path("payload/codex-agent-runtime-ios/build/apple-verified-distribution-execution")
_FILE_LIMIT = 16 * 1024 * 1024


def _read(path: Path) -> bytes:
    return read_regular_file_bytes(path, max_bytes=_FILE_LIMIT, reject_symlink_parents=True)


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _producer_from_receipt(receipt: Mapping[str, object]) -> dict[str, object]:
    return validate_producer({
        "repository": receipt["repository"],
        "workflowPath": receipt["workflowPath"],
        "commit": receipt["validationCommit"],
        "tree": receipt["validationTree"],
        "event": receipt["event"],
        "runId": receipt["runId"],
        "runAttempt": receipt["runAttempt"],
        "pullRequest": receipt["pullRequest"],
    }, "Apple source lane producer")


def capture_sdk_apple_original_ci(
    plan_path: Path,
    destination: Path,
    *,
    artifact_id: int,
    artifact_sha256: str,
    trusted_workflow_sha: str,
    contract_bundle: Path,
    contract_projection: VerifiedContractProjection,
    expected_distribution_proof: Path,
    expected_sdk_compatibility: Path,
    tooling_evidence: Path,
    tooling_public_key: Path,
    java_executable: Path,
    policy_revision: str,
    required_trust_domain: str,
    repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    token: str,
    tooling_keyring: Path | None = None,
    tooling_keys_directory: Path | None = None,
) -> dict[str, object]:
    """Authenticate transport and its original producer before retaining exact bytes."""
    if type(token) is not str or not token:
        raise ValueError("Apple source CI capture requires an observation token")
    artifact_sha256 = require_sha256(artifact_sha256, "Apple source upload digest")
    root = Path(repository_root or Path.cwd()).resolve(strict=True)
    plan_path = Path(plan_path)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Apple source CI destination must not exist")
    local_inputs = [
        plan_path,
        *(plan_path.parent / "inventories/ios-swift-tests" / name
          for name in INPUT_NAMES.values()),
        Path(contract_bundle),
        Path(expected_distribution_proof),
        Path(expected_sdk_compatibility),
        Path(tooling_evidence),
        Path(tooling_public_key),
        Path(java_executable),
        *(Path(value) for value in (tooling_keyring, tooling_keys_directory)
          if value is not None),
    ]
    requested_destination = Path(os.path.abspath(destination))
    resolved_destination = destination.parent.resolve(strict=False) / destination.name
    for source in local_inputs:
        requested = Path(os.path.abspath(source))
        resolved = source.resolve(strict=True)
        if _overlaps(requested, requested_destination) or \
                _overlaps(resolved, resolved_destination):
            raise ValueError("Apple source CI destination overlaps an input")
    prepared_destination = product_reuse._prepare_destination(destination, root)
    prepared_destination.rmdir()

    plan_bytes = _read(plan_path)
    inventory_sources = {
        name: plan_path.parent / "inventories/ios-swift-tests" / name
        for name in INPUT_NAMES.values()
    }
    inventory_bytes = {name: _read(path) for name, path in inventory_sources.items()}
    environment = dict(os.environ if environ is None else environ)

    with tempfile.TemporaryDirectory(prefix="sdk-apple-ci-") as temporary:
        private = Path(temporary).resolve()
        if any(_overlaps(private, source.resolve(strict=True)) for source in local_inputs):
            raise ValueError("Apple source CI private work overlaps an input")
        private_plan = private / "plan/impact-plan.json"
        private_plan.parent.mkdir()
        private_plan.write_bytes(plan_bytes)
        for name, contents in inventory_bytes.items():
            path = private_plan.parent / "inventories/ios-swift-tests" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        plan = product_reuse._validate_plan(private_plan, root)
        capture_producer = product_reuse._consumer(plan, environment)["producer"]
        observed = product_reuse._observe_ci_producer_jobs(
            {"apple": capture_producer}, jobs_by_phase={"apple": _JOB},
            trusted_workflow_sha=trusted_workflow_sha, token=token,
        )
        expected_name = f"codex-agent-ci-ios-swift-tests-{capture_producer['tree']}"
        artifact, raw = product_reuse._download_contract_ci_upload(
            artifact_id, artifact_sha256, expected_name,
            capture_producer, observed[0]["run"], token,
        )
        job = next(value for value in observed[0]["jobs"] if value.get("name") == _JOB)
        timestamps = [
            datetime.fromisoformat(
                require_string(value, "Apple source upload timestamp").replace("Z", "+00:00"),
            )
            for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))
        ]
        if any(value.utcoffset() != timedelta(0) for value in timestamps) or not (
            timestamps[0] <= timestamps[1] <= timestamps[2]
        ):
            raise ValueError("Apple source upload is outside its original job-attempt window")
        archive = private / "transport.zip"
        archive.write_bytes(raw)
        verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **product_reuse._CATALOG_ZIP_LIMITS,
        )
        lane = private / "lane"
        safe_extract(archive, lane)
        lane_before = regular_file_inventory(lane, allow_empty=True)
        receipt_path = lane / "lane-receipt.json"
        receipt_bytes = _read(receipt_path)
        receipt = validate_receipt(
            receipt_path, private_plan, lane, "ios-swift-tests", repository_root=root,
        )
        if receipt["artifactName"] != f"codex-agent-ci-ios-swift-tests-{receipt['validationTree']}":
            raise ValueError("Apple source lane receipt has the wrong artifact identity")
        original_producer = _producer_from_receipt(receipt)
        if original_producer == capture_producer:
            original_observed = observed
        else:
            original_observed = product_reuse._observe_ci_producer_jobs(
                {"apple": original_producer}, jobs_by_phase={"apple": _JOB},
                trusted_workflow_sha=trusted_workflow_sha, token=token,
            )

        verify_sdk_apple_original_source(
            repository=root,
            distribution_directory=lane / _DISTRIBUTION,
            execution_directory=lane / _EXECUTION,
            ios_swift_tests_root=lane,
            impact_plan=private_plan,
            expected_lane_receipt_sha256=sha256_bytes(receipt_bytes),
            expected_producer_commit=original_producer["commit"],
            expected_producer_tree=original_producer["tree"],
            expected_distribution_proof=Path(expected_distribution_proof),
            expected_sdk_compatibility=Path(expected_sdk_compatibility),
            contract_bundle=Path(contract_bundle),
            contract_projection=contract_projection,
            tooling_evidence=Path(tooling_evidence),
            tooling_public_key=Path(tooling_public_key),
            java_executable=Path(java_executable),
            policy_revision=policy_revision,
            required_trust_domain=required_trust_domain,
            tooling_keyring=tooling_keyring,
            tooling_keys_directory=tooling_keys_directory,
        )
        if regular_file_inventory(lane, allow_empty=True) != lane_before:
            raise ValueError("Captured Apple source lane changed during verification")
        if _read(plan_path) != plan_bytes or _read(private_plan) != plan_bytes or any(
            _read(inventory_sources[name]) != contents
            or _read(private_plan.parent / "inventories/ios-swift-tests" / name) != contents
            for name, contents in inventory_bytes.items()
        ):
            raise ValueError("Apple source plan changed during capture")

        output = private / "output"
        snapshot_regular_tree(lane, output / "lane", allow_empty=True)
        (output / "transport").mkdir()
        (output / "transport/upload.zip").write_bytes(raw)
        evidence: dict[str, object] = {
            "artifact": artifact,
            "captureProducer": capture_producer,
            "observed": observed,
            "originalProducer": original_producer,
            "originalObserved": original_observed,
        }
        write_canonical_json(output / "transport/original-apple-ci.json", evidence)
        if regular_file_inventory(lane, allow_empty=True) != lane_before:
            raise ValueError("Captured Apple source lane changed before publication")
        publish_regular_tree(output, prepared_destination, allow_empty=True)
    return evidence
