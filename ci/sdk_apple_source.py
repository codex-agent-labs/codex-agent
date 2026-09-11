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
import subprocess
import tempfile
from typing import Mapping

if __package__:
    from . import product_reuse
    from .receipt import INPUT_NAMES, safe_extract, validate_receipt
    from .products.contract_projection import VerifiedContractProjection
    from .products.inventory import (
        publish_regular_tree,
        git_regular_blob_bytes,
        load_json_bytes,
        read_regular_file_bytes,
        regular_file_inventory,
        require_exact_keys,
        require_sha256,
        require_string,
        sha256_bytes,
        snapshot_regular_tree,
        tree_entries,
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
        git_regular_blob_bytes,
        load_json_bytes,
        read_regular_file_bytes,
        regular_file_inventory,
        require_exact_keys,
        require_sha256,
        require_string,
        sha256_bytes,
        snapshot_regular_tree,
        tree_entries,
        verified_zip_contents,
        write_canonical_json,
    )
    from products.receipt import validate_producer
    from products.sdk_apple_source import verify_sdk_apple_original_source


_JOB = "product-validation / apple / swift-tests"
_PLAN_JOB = "product-validation / plan"
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


def _original_transport_producer(lane: Path, current: Mapping[str, object]):
    provenance = lane / "transport-provenance.json"
    if not provenance.exists():
        return None
    value = load_json_bytes(_read(provenance))
    selected = None
    while value is not None:
        value = require_exact_keys(
            value, {"schemaVersion", "source", "sourceTransportArtifactName", "previous"},
            "Apple source transport provenance",
        )
        if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1:
            raise ValueError("Unsupported Apple source transport provenance schema")
        source = require_exact_keys(value["source"], {
            "event", "runId", "runAttempt", "pullRequest", "validationCommit",
            "validationTree", "artifactName",
        }, "Apple source transport provenance source")
        name = require_string(
            value["sourceTransportArtifactName"], "Apple source transport artifact name",
        )
        if source["artifactName"] != name or name != (
            f"codex-agent-ci-ios-swift-tests-{source['validationTree']}"
        ):
            raise ValueError("Apple source transport provenance has the wrong artifact identity")
        selected = validate_producer({
            "repository": current["repository"],
            "workflowPath": current["workflowPath"],
            "commit": source["validationCommit"],
            "tree": source["validationTree"],
            "event": source["event"],
            "runId": source["runId"],
            "runAttempt": source["runAttempt"],
            "pullRequest": source["pullRequest"],
        }, "Apple original lane producer"), name
        value = value["previous"]
        if value is not None and type(value) is not dict:
            raise ValueError("Apple source transport provenance chain is malformed")
    return selected


def _job_window(observation, name: str, artifact: Mapping[str, object]) -> None:
    job = next(value for value in observation["jobs"] if value.get("name") == name)
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


def _private_original_repository(
    source: Path, destination: Path, revision: str, policy_revision: str,
) -> Path:
    try:
        subprocess.run(
            ["git", "init", "--quiet", str(destination)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(destination), "fetch", "--quiet", "--no-tags", str(source),
             revision, policy_revision],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        subprocess.run(
            ["git", "-C", str(destination), "update-ref", "HEAD", revision],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("Apple original Git plan replay could not capture its repository") from error
    paths = [path for path, _ in tree_entries(source, revision) if path.startswith("ci/lanes/")]
    if not paths:
        raise ValueError("Apple original Git plan has no lane policy")
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git_regular_blob_bytes(source, revision, relative, max_bytes=_FILE_LIMIT))
    return destination


def _original_upload(
    *, name: str, producer, observation, job: str, artifacts, token: str,
):
    selected = [value for value in artifacts if isinstance(value, dict) and value.get("name") == name]
    if len(selected) != 1:
        raise ValueError("Apple original CI upload is missing or ambiguous")
    candidate = selected[0]
    artifact, raw = product_reuse._download_contract_ci_upload(
        candidate.get("id"), candidate.get("digest"), name,
        producer, observation["run"], token,
    )
    _job_window(observation, job, artifact)
    return artifact, raw


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
        _job_window(observed[0], _JOB, artifact)
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
        current_receipt_producer = _producer_from_receipt(receipt)
        transport = _original_transport_producer(lane, current_receipt_producer)
        original_artifacts = None
        original_plan_archive = None
        original_lane_archive = None
        original_plan_root = None
        source_lane = lane
        source_plan = private_plan
        source_repository = root
        if transport is None:
            original_producer = current_receipt_producer
            original_observed = observed if original_producer == capture_producer else (
                product_reuse._observe_ci_producer_jobs(
                    {"apple": original_producer}, jobs_by_phase={"apple": _JOB},
                    trusted_workflow_sha=trusted_workflow_sha, token=token,
                )
            )
        else:
            original_producer, original_name = transport
            original_observed = product_reuse._observe_ci_producer_jobs(
                {"apple": original_producer, "plan": original_producer},
                jobs_by_phase={"apple": _JOB, "plan": _PLAN_JOB},
                trusted_workflow_sha=trusted_workflow_sha, token=token,
            )
            original_observation = original_observed[0]
            original_run = original_producer["runId"]
            artifacts = product_reuse.paginated_items(
                f"https://api.github.com/repos/{original_producer['repository']}"
                f"/actions/runs/{original_run}/artifacts",
                "artifacts", token,
            )
            original_plan_name = f"codex-agent-ci-plan-{original_producer['tree']}"
            original_lane_artifact, original_lane_raw = _original_upload(
                name=original_name, producer=original_producer, observation=original_observation,
                job=_JOB, artifacts=artifacts, token=token,
            )
            original_plan_artifact, original_plan_raw = _original_upload(
                name=original_plan_name, producer=original_producer,
                observation=original_observation, job=_PLAN_JOB, artifacts=artifacts, token=token,
            )
            original_artifacts = {
                "lane": original_lane_artifact,
                "plan": original_plan_artifact,
            }
            original_lane_archive = private / "original-lane-upload.zip"
            original_lane_archive.write_bytes(original_lane_raw)
            verified_zip_contents(
                original_lane_archive, retained_paths=(), allow_empty_members=True,
                **product_reuse._CATALOG_ZIP_LIMITS,
            )
            source_lane = private / "original-lane"
            safe_extract(original_lane_archive, source_lane)
            original_plan_archive = private / "original-plan-upload.zip"
            original_plan_archive.write_bytes(original_plan_raw)
            verified_zip_contents(
                original_plan_archive, retained_paths=(), allow_empty_members=True,
                **product_reuse._CATALOG_ZIP_LIMITS,
            )
            original_plan_root = private / "original-plan"
            safe_extract(original_plan_archive, original_plan_root)
            source_plan = original_plan_root / "impact-plan.json"
            source_repository = _private_original_repository(
                root, private / "original-repository", original_producer["commit"], policy_revision,
            )
            original_plan = product_reuse._validate_plan(source_plan, source_repository)
            if (original_plan["repository"], original_plan["event"],
                    original_plan["validationCommit"], original_plan["validationTree"],
                    original_plan["pullRequest"]) != (
                    original_producer["repository"], original_producer["event"],
                    original_producer["commit"], original_producer["tree"],
                    original_producer["pullRequest"]):
                raise ValueError("Apple original plan differs from its observed producer")
            original_receipt_path = source_lane / "lane-receipt.json"
            original_receipt = validate_receipt(
                original_receipt_path, source_plan, source_lane, "ios-swift-tests",
                repository_root=source_repository,
            )
            if _producer_from_receipt(original_receipt) != original_producer:
                raise ValueError("Apple original lane receipt differs from its observed producer")
            if original_receipt["artifactName"] != original_name:
                raise ValueError("Apple original lane receipt differs from its upload identity")
            receipt_bytes = _read(original_receipt_path)

        source_lane_before = regular_file_inventory(source_lane, allow_empty=True)
        source_plan_before = regular_file_inventory(source_plan.parent, allow_empty=True)

        verify_sdk_apple_original_source(
            repository=source_repository,
            distribution_directory=source_lane / _DISTRIBUTION,
            execution_directory=source_lane / _EXECUTION,
            ios_swift_tests_root=source_lane,
            impact_plan=source_plan,
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
        if (regular_file_inventory(lane, allow_empty=True) != lane_before
                or regular_file_inventory(source_lane, allow_empty=True) != source_lane_before
                or regular_file_inventory(source_plan.parent, allow_empty=True) != source_plan_before):
            raise ValueError("Captured Apple source lane or original plan changed during verification")
        if _read(plan_path) != plan_bytes or _read(private_plan) != plan_bytes or any(
            _read(inventory_sources[name]) != contents
            or _read(private_plan.parent / "inventories/ios-swift-tests" / name) != contents
            for name, contents in inventory_bytes.items()
        ):
            raise ValueError("Apple source plan changed during capture")

        output = private / "output"
        snapshot_regular_tree(source_lane, output / "lane", allow_empty=True)
        (output / "transport").mkdir()
        (output / "transport/upload.zip").write_bytes(raw)
        evidence: dict[str, object] = {
            "artifact": artifact,
            "captureProducer": capture_producer,
            "observed": observed,
            "originalProducer": original_producer,
            "originalObserved": original_observed,
        }
        if original_artifacts is not None:
            evidence["originalArtifacts"] = original_artifacts
            snapshot_regular_tree(lane, output / "transport/current-lane", allow_empty=True)
            snapshot_regular_tree(original_plan_root, output / "original-plan", allow_empty=True)
            (output / "transport/original-lane-upload.zip").write_bytes(
                original_lane_archive.read_bytes(),
            )
            (output / "transport/original-plan-upload.zip").write_bytes(
                original_plan_archive.read_bytes(),
            )
            if regular_file_inventory(output / "original-plan", allow_empty=True) != source_plan_before:
                raise ValueError("Published Apple original plan differs from its verified input")
            if regular_file_inventory(
                output / "transport/current-lane", allow_empty=True,
            ) != lane_before:
                raise ValueError("Published Apple current lane differs from its verified input")
        write_canonical_json(output / "transport/original-apple-ci.json", evidence)
        if (regular_file_inventory(lane, allow_empty=True) != lane_before
                or regular_file_inventory(source_lane, allow_empty=True) != source_lane_before
                or regular_file_inventory(source_plan.parent, allow_empty=True) != source_plan_before):
            raise ValueError("Captured Apple source lane or original plan changed before publication")
        if regular_file_inventory(output / "lane", allow_empty=True) != source_lane_before:
            raise ValueError("Published Apple source lane differs from its verified input")
        publish_regular_tree(output, prepared_destination, allow_empty=True)
    return evidence
