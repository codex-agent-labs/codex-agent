"""Recover current-key Contract phases from authenticated uploads without an index."""

from pathlib import Path
import argparse
import os
import tempfile

import product_reuse as transport
from products.contract_attestation import verify_contract_attestation, verify_contract_execution_closure
from products.inventory import (
    load_canonical_json_bytes, publish_regular_tree, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_semver, require_sha256, sha256_bytes, write_canonical_json,
)
from products.receipt import validate_producer
from products.registry import PhaseInstanceId
from products.restore import verify_phase_shard, write_carrier


PHASES = ("binary", "package", "validation", "metadata")
WORKFLOW = ".github/workflows/contract-validation.yml"
CONTINUATION = "product-validation / contract-validation / contract-continuation"
ATTESTATION = "product-validation / contract-validation / contract-attestation"


def _original_phase_workflows(capture, trusted_workflow_sha, token):
    workflows, attempts = {}, {}
    for phase in PHASES:
        receipt = load_canonical_json_bytes(read_regular_file_bytes(
            capture / f"execution-closure/receipts/{phase}.json", reject_symlink_parents=True))
        producer = validate_producer(receipt["producer"], "Original Contract producer hint")
        identity = producer["runId"], producer["runAttempt"]
        if identity not in attempts:
            run = transport.api_json(
                f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/"
                f"{identity[0]}/attempts/{identity[1]}", token)
            pin = transport._runtime_prior_workflow_sha(run, trusted_workflow_sha)
            if pin is None:
                raise ValueError("Original Contract phase lacks a reviewed producer workflow")
            transport._require_ci_workflow_reference(run,
                f"codex-agent-labs/codex-agent/{WORKFLOW}@{pin}", pin)
            attempts[identity] = pin
        workflows[phase] = {"path": WORKFLOW, "sha": attempts[identity]}
    return workflows


def _verify_current_keys(originals: Path, handoff: Path, expected_build_keys: dict) -> dict:
    if expected_build_keys is not None:
        require_exact_keys(expected_build_keys, set(PHASES), "Current Contract build keys")
    phases = {}
    for phase in PHASES:
        if expected_build_keys is not None:
            require_sha256(expected_build_keys[phase], f"Current Contract {phase} key")
        verified = verify_phase_shard(
            originals / "original-phases" / phase,
            PhaseInstanceId("contract", "contract", phase, "common"))
        original_receipt = read_regular_file_bytes(
            handoff / f"execution-closure/receipts/{phase}.json", reject_symlink_parents=True)
        if verified["receiptBytes"] != original_receipt:
            raise ValueError("Recovered Contract shard differs from the signed original receipt")
        if expected_build_keys is not None and verified["receipt"]["buildKey"] != expected_build_keys[phase]:
            raise ValueError(f"Recovered Contract {phase} differs from the current build key")
        phases[phase] = verified
    return phases


def capture_retained_contract(
    destination: Path, *, plan: dict, consumer_producer: dict, original_producer: dict,
    expected_build_keys: dict | None = None, contract_version: str,
    inputs_artifact_id: int, inputs_artifact_sha256: str,
    handoff_artifact_id: int, handoff_artifact_sha256: str,
    trusted_workflow_sha: str, keyring: Path, keys_directory: Path, token: str,
) -> dict:
    """Caller supplies reviewed pins/current keys; original uploads supply bytes.

    Return paths to independently authenticated phase objects and the original
    release envelope. Current-consumer carrier assembly remains caller-owned.
    """
    consumer = validate_producer(consumer_producer, "Contract recovery consumer")
    original = validate_producer(original_producer, "Contract recovery original")
    if (plan.get("remoteBuildAuthorized") is not True or plan.get("event") != "pull_request"
            or plan.get("repository") != "codex-agent-labs/codex-agent"
            or consumer["event"] != "pull_request" or original["event"] != "pull_request"
            or consumer["repository"] != plan["repository"] or original["repository"] != plan["repository"]
            or consumer["commit"] != plan.get("validationCommit")
            or consumer["tree"] != plan.get("validationTree")
            or consumer["pullRequest"] != plan.get("pullRequest")
            or original["pullRequest"] != consumer["pullRequest"]
            or (original["runId"], original["runAttempt"]) >= (consumer["runId"], consumer["runAttempt"])):
        raise ValueError("Contract recovery requires an earlier producer of the same authorized PR")
    if expected_build_keys is not None:
        require_exact_keys(expected_build_keys, set(PHASES), "Current Contract build keys")
        for phase in PHASES:
            require_sha256(expected_build_keys[phase], f"Current Contract {phase} key")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Retained Contract destination already exists")
    with tempfile.TemporaryDirectory(prefix="contract-retained-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        prepared.mkdir()
        capture = prepared / "unsigned-inputs"
        transport.capture_contract_ci_artifact(
            capture, artifact_id=inputs_artifact_id, artifact_sha256=inputs_artifact_sha256,
            transport_producer=original, trusted_workflow_sha=trusted_workflow_sha,
            contract_version=contract_version, token=token,
            trusted_workflow_path=WORKFLOW, trusted_job_name=CONTINUATION)
        originals = prepared / "originals"
        transport.capture_contract_original_ci_phases(
            capture, originals, contract_version=contract_version,
            trusted_workflow_sha=trusted_workflow_sha, token=token,
            trusted_workflows_by_phase=_original_phase_workflows(capture, trusted_workflow_sha, token),
            jobs_by_phase={phase: ("product-validation / contract-validation / product-contracts"
                                   if phase == "binary" else CONTINUATION) for phase in PHASES})
        observed = transport._observe_ci_producer_jobs(
            {"attestation": original}, jobs_by_phase={"attestation": ATTESTATION}, token=token,
            trusted_workflows_by_phase={"attestation": {"path": WORKFLOW, "sha": trusted_workflow_sha}})
        artifact, raw = transport._download_contract_ci_upload(
            handoff_artifact_id, handoff_artifact_sha256,
            f"codex-agent-contract-release-handoff-{original['tree']}", original,
            observed[0]["run"], token)
        transport._require_artifact_job_window(observed[0], ATTESTATION, artifact)
        archive = root / "handoff.zip"
        archive.write_bytes(raw)
        zipped, _, _ = transport.verified_zip_contents(
            archive, retained_paths=(), **transport._CATALOG_ZIP_LIMITS)
        uploaded = prepared / "release-upload"
        transport.safe_extract(archive, uploaded)
        if regular_file_inventory(uploaded) != zipped:
            raise ValueError("Retained Contract release upload extraction changed")
        caller = require_exact_keys(load_canonical_json_bytes(read_regular_file_bytes(
            uploaded / "caller.json", reject_symlink_parents=True)),
            {"schemaVersion", "trustedSourceCommit", "trustedSourceTree", "trustedWorkflowSha",
             "transportProducer", "authorizationReason", "event", "environment"}, "Retained release caller")
        if (caller["schemaVersion"] != 1 or caller["transportProducer"] != original
                or caller["trustedWorkflowSha"] != trusted_workflow_sha):
            raise ValueError("Retained Contract release caller differs from its observed producer")
        handoff = uploaded / "contract-input"
        stem = f"codex-agent-contract-{contract_version}"
        payload = handoff / f"{stem}.zip"
        verify_contract_execution_closure(payload, handoff / "execution-closure")
        verify_contract_attestation(
            payload, handoff / "execution-closure/receipts/metadata.json",
            handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
            handoff / "public-key.pub", required_trust_domain="release",
            keyring=keyring, keys_directory=keys_directory)
        phases = _verify_current_keys(originals, handoff, expected_build_keys)
        observation = {"schemaVersion": 1, "consumer": consumer, "originalProducer": original,
                       "releaseArtifact": artifact, "releaseObserved": observed,
                       "buildKeys": dict(expected_build_keys) if expected_build_keys is not None else None}
        write_canonical_json(prepared / "recovery.json", observation)
        publish_regular_tree(prepared, destination, expected_inventory=regular_file_inventory(prepared))
    return {"originals": destination / "originals", "handoff": destination / "release-upload/contract-input",
            "phases": {phase: {**value, "objectPath":
                               destination / "originals/original-phases" / phase / value["objectPath"]}
                       for phase, value in phases.items()}, "observation": observation}


def replay_retained_contract(
    captured_root: Path, contract_request: dict, destination: Path, *,
    consumer: dict, keyring: Path, keys_directory: Path,
    sdk_validation_tooling=None, sdk_apple_validation_policy=None,
    allow_partial: bool = False,
) -> dict:
    """Recompute current keys against just-authenticated captured originals.

    The normal planner computes keys in dependency order using current Git
    inventories/authorities and verified predecessor bytes. Caller-owned trust
    authenticates every original receipt before a saved capture can be reused.
    """
    captured_root = Path(captured_root)
    instances = tuple(sorted(PhaseInstanceId("contract", "contract", phase, "common") for phase in PHASES))
    if contract_request["requested"] != [{"product": "contract", "component": "contract",
                                          "phase": "metadata", "target": "common"}]:
        raise ValueError("Retained Contract replay requires the exact Contract closure")
    request = dict(contract_request)
    if request["availableObjects"]:
        raise ValueError("Retained Contract replay requires no unrelated supplied objects")
    originals = captured_root / "originals"
    handoff = captured_root / "release-upload/contract-input"
    original_metadata = load_canonical_json_bytes(read_regular_file_bytes(
        handoff / "execution-closure/receipts/metadata.json", reject_symlink_parents=True))
    version = require_semver(original_metadata["productVersion"], "Retained Contract version")
    stem = f"codex-agent-contract-{version}"
    payload = handoff / f"{stem}.zip"
    verify_contract_execution_closure(payload, handoff / "execution-closure")
    verify_contract_attestation(
        payload, handoff / "execution-closure/receipts/metadata.json",
        handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
        handoff / "public-key.pub", required_trust_domain="release",
        keyring=keyring, keys_directory=keys_directory)
    verified = _verify_current_keys(originals, handoff, None)
    artifact_root = Path(request["artifactRoot"]).resolve(strict=True)
    sources, records = {}, []
    for instance in instances:
        phase = verified[instance.phase]
        source = originals / "original-phases" / instance.phase / phase["objectPath"]
        sources[instance] = source
        records.append({**transport._identity_record(instance),
                        **{field: phase[field] for field in ("buildKey", "receiptSha256", "objectSha256")},
                        "objectPath": source.resolve(strict=True).relative_to(artifact_root).as_posix()})
    request["availableObjects"] = records
    result = transport._plan_with_sdk_tooling(
        request, sdk_validation_tooling, apple_policy=sdk_apple_validation_policy)
    retained = [phase for phase in result["phases"] if phase["state"] == "retained"]
    retained_instances = tuple(transport._identity(phase) for phase in retained)
    retained_phases = {instance.phase for instance in retained_instances}
    prefix = set(PHASES[:len(retained_instances)])
    if (len(result["phases"]) != len(instances) or not retained
            or retained_phases != prefix
            or any(transport._identity(value) not in instances for value in result["phases"])
            or any(value["state"] not in {"retained", "build", "waiting"} for value in result["phases"])
            or (not allow_partial and (result["fullReuse"] is not True
                or result["matrices"] != {"contract": [], "runtime": [], "sdk": []}
                or len(retained) != len(instances)))):
        raise ValueError("Authenticated Contract originals do not match the current computed phase keys")
    # Exclude stale suffix objects from the saved request. Continuation replay
    # must see only the original phases actually admitted by current keys.
    request["availableObjects"] = [record for record in records
                                   if transport._identity(record) in retained_instances]
    ready_plans = {}
    if len(retained) != len(instances):
        result = transport._plan_with_sdk_tooling(
            request, sdk_validation_tooling, apple_policy=sdk_apple_validation_policy,
            build_plan_consumer=lambda instance, value: ready_plans.setdefault(instance, value))
        retained = [phase for phase in result["phases"] if phase["state"] == "retained"]
        if tuple(transport._identity(phase) for phase in retained) != retained_instances:
            raise ValueError("Current Contract replay changed its authenticated retained prefix")
    for phase in retained:
        original = verified[phase["phase"]]
        if any(phase[field] != original[field] for field in ("buildKey", "receiptSha256", "objectSha256")):
            raise ValueError("Current Contract replay selected a different original object")
    normalized = {**result, "result": "complete", "fullReuse": True,
        "matrices": {"contract": [], "runtime": [], "sdk": []},
        "phases": [{**phase, "state": "reused", "source": "phase-shard",
        "transportSource": {"kind": "phase-shard", "descriptorSha256": sha256_bytes(read_regular_file_bytes(
            originals / "original-phases" / phase["phase"] / transport.PHASE_SHARD_NAME,
            reject_symlink_parents=True)), "producer": verified[phase["phase"]]["receipt"]["producer"]}}
        for phase in retained]}
    # Carrier schemas deliberately exclude invocation-only planner fields.
    resolution = {key: normalized[key] for key in ("schemaVersion", "result", "fullReuse", "phases", "matrices")}
    write_carrier(destination, resolution, retained_instances,
                  {instance: sources[instance] for instance in retained_instances}, consumer)
    return {"request": request, "result": result, "resolution": resolution,
            "readyPlans": ready_plans}


def discover_retained_contract(
    destination: Path, *, plan: dict, consumer_producer: dict, contract_request: dict,
    trusted_workflow_sha: str, keyring: Path, keys_directory: Path, token: str,
    sdk_validation_tooling=None, sdk_apple_validation_policy=None,
) -> dict | None:
    """Authenticate a prior signed closure and retain its current-key prefix."""
    artifact_root = Path(contract_request["artifactRoot"]).resolve(strict=True)
    destination = Path(destination).absolute()
    destination.relative_to(artifact_root)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Retained Contract discovery destination already exists")
    # Unexpired authenticated originals must not age out merely because orchestration was retried.
    attempts = transport._prior_failed_pr_attempts(plan, consumer_producer, token)
    artifacts_by_run = {}
    for prior in attempts:
        pin = transport._runtime_prior_workflow_sha(prior, trusted_workflow_sha)
        if pin is None:
            continue
        run_id = prior["id"]
        if run_id not in artifacts_by_run:
            artifacts_by_run[run_id] = transport.paginated_items(
                f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run_id}/artifacts",
                "artifacts", token)
        artifacts = artifacts_by_run[run_id]
        candidates = sorted((artifact for artifact in artifacts if isinstance(artifact, dict)
            and artifact.get("expired") is False and isinstance(artifact.get("name"), str)
            and artifact["name"].startswith("codex-agent-contract-attestation-inputs-")),
            key=lambda artifact: artifact["id"], reverse=True)
        for candidate in candidates:
            tree = candidate["name"].removeprefix("codex-agent-contract-attestation-inputs-")
            handoffs = [artifact for artifact in artifacts if isinstance(artifact, dict)
                        and artifact.get("expired") is False
                        and artifact.get("name") == f"codex-agent-contract-release-handoff-{tree}"]
            if not handoffs:
                continue
            if len(handoffs) != 1:
                raise ValueError("Retained Contract release upload is ambiguous")
            with tempfile.TemporaryDirectory(prefix="contract-recovery-probe-", dir=artifact_root) as temporary:
                root = Path(temporary).resolve()
                archive = root / "inputs.zip"
                # Only an untrusted producer hint is read here; admission below
                # independently binds the original job, upload, receipts and objects.
                transport._download_contract_ci_upload(
                    candidate["id"], candidate["digest"], candidate["name"],
                    {"runId": run_id}, prior, token, destination=archive)
                _, contents, _ = transport.verified_zip_contents(
                    archive, retained_paths=("execution-closure/receipts/metadata.json",),
                    **transport._CATALOG_ZIP_LIMITS)
                receipt = load_canonical_json_bytes(contents["execution-closure/receipts/metadata.json"])
                original = validate_producer(receipt["producer"], "Retained Contract producer hint")
                if (original["runId"] != run_id or original["runAttempt"] != prior["run_attempt"]
                        or original["tree"] != tree
                        or receipt["productVersion"] != contract_request["versions"]["contract"]):
                    continue
                prepared = root / "selected"
                prepared.mkdir()
                capture_retained_contract(
                    prepared / "capture", plan=plan, consumer_producer=consumer_producer,
                    original_producer=original, contract_version=receipt["productVersion"],
                    inputs_artifact_id=candidate["id"], inputs_artifact_sha256=candidate["digest"],
                    handoff_artifact_id=handoffs[0]["id"], handoff_artifact_sha256=handoffs[0]["digest"],
                    trusted_workflow_sha=pin, keyring=keyring, keys_directory=keys_directory, token=token)
                try:
                    replay = replay_retained_contract(
                        prepared / "capture", contract_request, prepared / "carrier",
                        consumer={"kind": "ci", "producer": consumer_producer},
                        keyring=keyring, keys_directory=keys_directory,
                        sdk_validation_tooling=sdk_validation_tooling,
                        sdk_apple_validation_policy=sdk_apple_validation_policy,
                        allow_partial=True)
                except ValueError as error:
                    if str(error) != "Authenticated Contract originals do not match the current computed phase keys":
                        raise
                    continue
                request = dict(replay["request"])
                request["availableObjects"] = [{**record, "objectPath": (
                    destination / (artifact_root / record["objectPath"]).relative_to(prepared)
                ).relative_to(artifact_root).as_posix()} for record in request["availableObjects"]]
                selection = {"schemaVersion": 1, "producer": original,
                             "inputsArtifact": candidate, "releaseArtifact": handoffs[0],
                             "trustedWorkflowSha": pin}
                write_canonical_json(prepared / "selection.json", selection)
                publish_regular_tree(prepared, destination,
                                     expected_inventory=regular_file_inventory(prepared))
                return {**replay, "request": request, "carrier": destination / "carrier",
                        "capture": destination / "capture",
                        "handoff": destination / "capture/release-upload/contract-input",
                        "selection": selection}
    return None


def capture_forwarded_handoff(
    destination: Path, *, artifact_id: int, artifact_sha256: str, transport_producer: dict,
    trusted_workflow_sha: str, contract_version: str, keyring: Path, keys_directory: Path, token: str,
) -> None:
    """Authenticate a current continuation upload containing a prior signed envelope."""
    producer = validate_producer(transport_producer, "Forwarded Contract producer")
    observed = transport._observe_ci_producer_jobs(
        {"forward": producer}, jobs_by_phase={"forward": CONTINUATION}, token=token,
        trusted_workflows_by_phase={"forward": {"path": WORKFLOW, "sha": trusted_workflow_sha}})
    artifact, raw = transport._download_contract_ci_upload(
        artifact_id, artifact_sha256, f"codex-agent-contract-forwarded-handoff-{producer['tree']}",
        producer, observed[0]["run"], token)
    transport._require_artifact_job_window(observed[0], CONTINUATION, artifact)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Forwarded Contract destination already exists")
    with tempfile.TemporaryDirectory(prefix="contract-forwarded-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "upload.zip"
        archive.write_bytes(raw)
        inventory, _, _ = transport.verified_zip_contents(
            archive, retained_paths=(), **transport._CATALOG_ZIP_LIMITS)
        prepared = root / "handoff"
        transport.safe_extract(archive, prepared)
        if regular_file_inventory(prepared) != inventory:
            raise ValueError("Forwarded Contract extraction changed")
        stem = f"codex-agent-contract-{contract_version}"
        closure = verify_contract_execution_closure(prepared / f"{stem}.zip", prepared / "execution-closure")
        expected = {f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub",
                    "execution-closure/contract-execution-closure.json",
                    *(f"execution-closure/{record['relativePath']}" for record in closure["files"])}
        if {record["relativePath"] for record in inventory} != expected:
            raise ValueError("Forwarded Contract handoff inventory is not exact")
        verify_contract_attestation(
            prepared / f"{stem}.zip", prepared / "execution-closure/receipts/metadata.json",
            prepared / f"{stem}.attestation.json", prepared / f"{stem}.attestation.sig",
            prepared / "public-key.pub", required_trust_domain="release",
            keyring=keyring, keys_directory=keys_directory)
        publish_regular_tree(prepared, destination, expected_inventory=inventory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture-forwarded-handoff",))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--artifact-id", type=int, required=True)
    parser.add_argument("--artifact-sha256", required=True)
    parser.add_argument("--transport-producer", required=True)
    parser.add_argument("--trusted-workflow-sha", required=True)
    parser.add_argument("--contract-version", required=True)
    parser.add_argument("--keyring", type=Path, required=True)
    parser.add_argument("--keys-directory", type=Path, required=True)
    arguments = parser.parse_args()
    producer = load_canonical_json_bytes((arguments.transport_producer + "\n").encode())
    capture_forwarded_handoff(
        arguments.destination, artifact_id=arguments.artifact_id,
        artifact_sha256=arguments.artifact_sha256, transport_producer=producer,
        trusted_workflow_sha=arguments.trusted_workflow_sha, contract_version=arguments.contract_version,
        keyring=arguments.keyring, keys_directory=arguments.keys_directory, token=os.environ["GITHUB_TOKEN"])


if __name__ == "__main__":
    main()
