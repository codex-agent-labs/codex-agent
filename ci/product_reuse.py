#!/usr/bin/env python3
"""Resolve authenticated product reuse before any target job is created."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import os
import ntpath
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
from typing import Any, Mapping

from impact import validate_legacy_lane_projection, validate_remote_build_authorization
from receipt import safe_extract
from reuse import api_json, download_artifact, github_output, paginated_items, run_matches_pr
from products.aggregate import RUNTIME_EVIDENCE_TARGETS, RUNTIME_TARGETS, validate_product_index
from products.contract_attestation import (
    validate_contract_attestation, verify_contract_attestation, verify_contract_execution_closure,
)
from products.inventory import (
    canonical_json_bytes,
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    publish_regular_tree,
    read_regular_file_bytes,
    regular_file_inventory,
    require_array,
    require_boolean,
    require_exact_keys,
    require_integer,
    require_relative_path,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    sha256_file,
    snapshot_regular_tree,
    tree_entries,
    verify_regular_file_inventory,
    verified_zip_contents,
    write_canonical_json,
)
from products.registry import (
    NATIVE_TARGETS,
    PHASE_INSTANCE_IDS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_toolchain_profile,
    required_contract_components,
)
from products.index import _verify_index_receipt
from products.plan import (
    NOT_APPLICABLE_FLAGS_DIGEST,
    NOT_APPLICABLE_TOOLCHAIN_DIGEST,
    runtime_validation_dependencies,
    native_runtime_validation_dependencies,
    sdk_validation_dependencies,
)
from products.runtime_flags import load_runtime_binary_flags_bytes
from products.runtime_adapter_content import rebase_adapter_comparison_records
from products.sdk_validation import rebase_sdk_validation_records
from products.sdk_validation_inputs import load_sdk_validation_evidence, stage_sdk_validation_evidence
from products.adapter_runtime_inputs import load_adapter_runtime_evidence, stage_adapter_runtime_evidence
from products.runtime_evidence import (
    derive_authenticated_runtime_validation_projection,
    jvm_evidence_filename,
    node_evidence_filename,
)
from products.restore import (
    OBJECT_ZIP_LIMITS,
    PHASE_SHARD_KEYS,
    PHASE_SHARD_NAME,
    object_relative_path,
    restore_object,
    verify_carrier,
    verify_object,
    verify_phase_shard,
    write_carrier,
    finalize_phase_object,
)
from products.receipt import validate_producer, verify_output_manifest_identity
from products.reuse import (
    SOURCES, _dependency_closure, plan_reuse_wave,
    _native_comparison_records, _native_evidence_paths,
)
from products.native_runtime_inputs import load_native_runtime_evidence, stage_native_runtime_evidence
from products.selection import classify_paths
from products.signatures import load_keyring, public_key_for_metadata, public_key_path
from products.toolchain import load_toolchain_profile_bytes


_PLAN_KEYS = {
    "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
    "validationCommit", "validationTree", "mergeReady", "remoteBuildAuthorized",
    "remoteBuildAuthorizationReason", "androidEvidenceRequired", "fullRequested", "full",
    "unknownPaths", "changedPaths", "lanes",
}
_IDENTITY_KEYS = ("product", "component", "phase", "target")
_REUSE_RESULT_KEYS = {
    "schemaVersion", "result", "fullReuse", "phases", "matrices",
    "continuationRequirements",
}
_REUSE_PHASE_KEYS = {
    *_IDENTITY_KEYS, "buildKey", "state", "source", "transportSource",
    "receiptSha256", "objectSha256", "misses",
}
_WAVE_REQUEST_KEYS = {
    "schemaVersion", "requestType", "repository", "pullRequest", "repositoryRoot",
    "repositoryRevision", "artifactRoot", "requested", "versions", "phaseAuthorities",
    "contractEvidence", "runtimeValidationEvidence", "availableObjects", "catalogs",
}
_NATIVE_REQUEST_KEYS = {"nativeRuntimeEvidence", "nativeRuntimeComparisonEvidence"}
_ADAPTER_REQUEST_KEY = "adapterRuntimeComparisonEvidence"
_SDK_REQUEST_KEYS = {"sdkValidationEvidence"}
_VERSION_PATHS = {
    "contract": "gradle/release/versions/contract.txt",
    "runtime-release": "gradle/release/versions/runtime.txt",
    "sdk": "gradle/release/versions/sdk.txt",
}
_KEYRING_PATH = "gradle/release/product-signing-keys.json"
_KEYS_ROOT = "gradle/release/keys"
_PROFILE_ROOT = "gradle/release/toolchains/runtime"
_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_CATALOG_PREFIX = "codex-agent-product-catalog-v1-"
_CATALOG_LIMIT = 4 * 1024 * 1024 * 1024
_CATALOG_ZIP_LIMITS = {
    "max_archive_bytes": _CATALOG_LIMIT,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 8192,
    "max_entry_bytes": OBJECT_ZIP_LIMITS["max_archive_bytes"],
    "max_total_bytes": 4 * 1024 * 1024 * 1024,
    "max_compression_ratio": 200,
}


@dataclass(frozen=True, slots=True)
class ReleaseTrust:
    keyring: Path
    keys: Path


@dataclass(frozen=True, slots=True)
class Catalog:
    source: str
    index: dict[str, Any]
    index_sha256: str
    request: dict[str, Any]
    objects: Mapping[str, Path]
    contract_attestation: Path | None = None
    contract_attestation_signature: Path | None = None
    native_runtime_evidence: tuple[dict[str, Any], ...] = ()
    adapter_runtime_evidence: tuple[dict[str, Any], ...] = ()
    sdk_validation_evidence_root: Path | None = None


def _identity(value: Mapping[str, Any]) -> PhaseInstanceId:
    instance = PhaseInstanceId(*(value[key] for key in _IDENTITY_KEYS))
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError(f"Unknown product phase identity: {instance}")
    return instance


def _identity_record(instance: PhaseInstanceId) -> dict[str, str]:
    return {key: getattr(instance, key) for key in _IDENTITY_KEYS}


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _git_value(root: Path, *arguments: str) -> str:
    try:
        return subprocess.run(
            ("git", *arguments), cwd=root, check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("The checked-out Git identity is unavailable") from error


def _prepare_destination(destination: Path, repository_root: Path) -> Path:
    lexical_root = Path(os.path.abspath(repository_root))
    requested = Path(os.path.abspath(destination))
    try:
        relative = requested.relative_to(lexical_root)
    except ValueError as error:
        raise ValueError("Product reuse destination must remain inside the repository") from error
    if not relative.parts:
        raise ValueError("Product reuse destination must not be the repository root")
    trusted_root = lexical_root.resolve()
    current = trusted_root
    for part in relative.parts:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        reparse = getattr(metadata, "st_file_attributes", 0) & getattr(
            stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0,
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Product reuse destination has an unsafe parent")
    destination = trusted_root.joinpath(*relative.parts)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Product reuse destination must be absent or empty")
    destination.mkdir(parents=True, exist_ok=True)
    metadata = destination.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Product reuse destination has an unsafe parent")
    return destination


def _observe_tested_commit(
    run: Mapping[str, Any], *, api: str, repository: str, token: str,
    expected_commit: str, expected_tree: str, pull_request: int | None,
) -> dict[str, Any]:
    """Observe tested Git identity separately from the triggering workflow head."""
    if any(not isinstance(value, str) or _OID.fullmatch(value) is None
           for value in (expected_commit, expected_tree)):
        raise ValueError("Tested Git commit/tree identity is malformed")
    commit = api_json(f"{api}/repos/{repository}/git/commits/{expected_commit}", token)
    tree = commit.get("tree")
    if (commit.get("sha") != expected_commit or not isinstance(tree, dict)
            or tree.get("sha") != expected_tree):
        raise ValueError("Tested Git commit/tree differs from its original identity")
    if run.get("event") == "pull_request":
        requests = [value for value in require_array(run.get("pull_requests"), "Original CI pull requests")
                    if isinstance(value, dict) and value.get("number") == pull_request]
        if len(requests) != 1:
            raise ValueError("Original CI attempt has ambiguous pull-request identity")
        identities = []
        for field in ("base", "head"):
            value = requests[0].get(field)
            oid = value.get("sha") if isinstance(value, dict) else None
            if not isinstance(oid, str) or re.fullmatch(r"[0-9a-f]{40}", oid) is None:
                raise ValueError("Original CI attempt lacks exact pull-request base/head")
            identities.append(oid)
        parents = require_array(commit.get("parents"), "Tested merge parents")
        if ([value.get("sha") if isinstance(value, dict) else None for value in parents] != identities
                or run.get("head_sha") not in {identities[1], expected_commit}):
            raise ValueError("Tested merge does not bind the original CI pull-request base/head")
    elif run.get("event") != "merge_group" or run.get("head_sha") != expected_commit:
        raise ValueError("Merge-group attempt does not match its tested commit")
    return commit


def _same_pr_run(
    artifact: Mapping[str, Any], api: str, repository: str, pull_request: int, token: str,
    expected_commit: str, expected_tree: str, *, expected_attempt: int,
) -> dict[str, Any]:
    transport = artifact.get("workflow_run")
    if not isinstance(transport, dict):
        raise ValueError("Same-PR product catalog lacks workflow-run transport provenance")
    run_id = require_integer(transport.get("id"), "product catalog workflow run ID", 1)
    head_sha = require_string(transport.get("head_sha"), "product catalog workflow head SHA")
    if _OID.fullmatch(head_sha) is None:
        raise ValueError("Product catalog workflow head SHA is malformed")
    require_integer(expected_attempt, "product catalog original run attempt", 1)
    run_url = f"{api}/repos/{repository}/actions/runs/{run_id}/attempts/{expected_attempt}"
    run = api_json(run_url, token)
    if (
        require_integer(run.get("id"), "product catalog workflow run ID", 1) != run_id
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "pull_request"
        or run.get("path") != ".github/workflows/ci.yml"
        or run.get("head_sha") != head_sha
        or any(not isinstance(run.get(field), dict)
               or run[field].get("full_name") != repository or run[field].get("fork") is not False
               for field in ("repository", "head_repository"))
        or not run_matches_pr(run, pull_request)
    ):
        raise ValueError("Same-PR product catalog did not come from an allowed successful CI run")
    attempt = require_integer(run.get("run_attempt"), "product catalog workflow run attempt", 1)
    if attempt != expected_attempt:
        raise ValueError("Same-PR product catalog claims a different original CI attempt")
    tested_commit = _observe_tested_commit(
        run, api=api, repository=repository, token=token,
        expected_commit=expected_commit, expected_tree=expected_tree, pull_request=pull_request)
    return {"run": run, "testedCommit": tested_commit}


def verify_contract_producer_runs(
    producers: Mapping[str, Any], *, trusted_workflow_sha: str, token: str,
) -> list[dict[str, Any]]:
    """Observe exact original CI attempts, not whole-run success or signing authority.

    The protected caller supplies the reviewed workflow pin. This does not bind
    an uploaded artifact to these jobs: artifact/object/closure admission and
    protected signing policy must still pass before a private key is used.
    Returned API evidence stays external to reusable payloads and original receipts.
    """
    return _observe_contract_producer_runs(
        producers, phases=("binary", "package", "validation", "metadata"),
        trusted_workflow_sha=trusted_workflow_sha, token=token)


def _observe_contract_producer_runs(
    producers: Mapping[str, Any], *, phases: tuple[str, ...], trusted_workflow_sha: str, token: str,
) -> list[dict[str, Any]]:
    return _observe_ci_producer_jobs(
        producers, jobs_by_phase={phase: "product-validation / product-contracts" if phase == "binary"
                                 else "product-validation / contract-continuation" for phase in phases},
        trusted_workflow_sha=trusted_workflow_sha, token=token)


def _observe_ci_producer_jobs(
    producers, *, jobs_by_phase, trusted_workflow_sha, token,
) -> list[dict[str, Any]]:
    # Both callers choose fixed job names; transported data cannot select a job.
    require_exact_keys(producers, set(jobs_by_phase), "Contract phase producers")
    if not isinstance(trusted_workflow_sha, str) or re.fullmatch(r"[0-9a-f]{40}", trusted_workflow_sha) is None:
        raise ValueError("Contract producer admission requires a caller-pinned workflow SHA")
    repository = "codex-agent-labs/codex-agent"
    workflow = f"{repository}/.github/workflows/product-validation.yml@{trusted_workflow_sha}"
    attempts: dict[tuple[int, int], dict[str, Any]] = {}
    for phase in jobs_by_phase:
        producer = validate_producer(producers[phase], f"Contract {phase} producer")
        if (producer["repository"] != repository
                or producer["workflowPath"] != ".github/workflows/ci.yml"
                or producer["event"] not in {"pull_request", "merge_group"}):
            raise ValueError("Contract producer is not an eligible original CI producer")
        identity = producer["runId"], producer["runAttempt"]
        if identity in attempts and attempts[identity]["producer"] != producer:
            raise ValueError("Contract phases claim conflicting identities for one CI attempt")
        attempts.setdefault(identity, {"producer": producer, "phases": []})["phases"].append(phase)

    evidence = []
    for (run_id, attempt), original in sorted(attempts.items()):
        producer = original["producer"]
        url = f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}"
        run = api_json(url, token)
        if (require_integer(run.get("id"), "Contract original CI run ID", 1) != run_id
                or require_integer(run.get("run_attempt"), "Contract original CI attempt", 1) != attempt
                or run.get("path") != producer["workflowPath"]
                or run.get("event") != producer["event"]
                or run.get("status") not in {"in_progress", "completed"}
                or any(not isinstance(run.get(field), dict)
                       or run[field].get("full_name") != repository
                       or run[field].get("fork") is not False
                       for field in ("repository", "head_repository"))
                or producer["event"] == "pull_request" and not run_matches_pr(run, producer["pullRequest"])):
            raise ValueError("Contract original CI attempt does not match its producer")
        references = require_array(run.get("referenced_workflows"), "Contract original workflow references")
        selected = [value for value in references if isinstance(value, dict)
                    and isinstance(value.get("path"), str)
                    and value["path"].split("@", 1)[0] == workflow.split("@", 1)[0]]
        if (len(selected) != 1 or selected[0].get("path") != workflow
                or selected[0].get("sha") != trusted_workflow_sha):
            raise ValueError("Contract original CI attempt lacks the caller-pinned workflow")
        commit = _observe_tested_commit(
            run, api="https://api.github.com", repository=repository, token=token,
            expected_commit=producer["commit"], expected_tree=producer["tree"],
            pull_request=producer["pullRequest"])
        jobs = paginated_items(f"{url}/jobs", "jobs", token)
        if any(not isinstance(job, dict) for job in jobs):
            raise ValueError("Contract original CI jobs are malformed")
        names = {jobs_by_phase[phase] for phase in original["phases"]}
        for name in sorted(names):
            selected_jobs = [job for job in jobs if job.get("name") == name]
            if len(selected_jobs) != 1:
                raise ValueError("Contract original producer job is missing or ambiguous")
            job = selected_jobs[0]
            require_integer(job.get("id"), "Contract original producer job ID", 1)
            if (require_integer(job.get("run_id"), "Contract original producer job run", 1) != run_id
                    or job.get("head_sha") != run["head_sha"]
                    or job.get("status") != "completed" or job.get("conclusion") != "success"):
                raise ValueError("Contract original producer job did not succeed for its exact commit")
        evidence.append({"run": run, "testedCommit": commit, "jobs": jobs})
    return evidence


def _download_contract_ci_upload(
    artifact_id: int, artifact_sha256: str, expected_name: str,
    producer: Mapping[str, Any], observed_run: Mapping[str, Any], token: str,
) -> tuple[dict[str, Any], bytes]:
    require_integer(artifact_id, "Contract upload artifact ID", 1)
    require_sha256(artifact_sha256, "Contract upload artifact digest")
    repository = "codex-agent-labs/codex-agent"
    url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
    artifact = api_json(url, token)
    transport = artifact.get("workflow_run")
    if (require_integer(artifact.get("id"), "Contract uploaded artifact ID", 1) != artifact_id
            or artifact.get("digest") != artifact_sha256
            or artifact.get("expired") is not False
            or artifact.get("name") != expected_name
            or artifact.get("archive_download_url") != f"{url}/zip"
            or not isinstance(transport, dict)
            or require_integer(transport.get("id"), "Contract upload run ID", 1) != producer["runId"]
            or transport.get("head_sha") != observed_run["head_sha"]):
        raise ValueError("Contract uploaded artifact differs from the caller-bound transport identity")
    size = require_integer(artifact.get("size_in_bytes"), "Contract upload transport bytes", 1)
    if size > _CATALOG_LIMIT:
        raise ValueError("Contract uploaded artifact exceeds the transport limit")
    raw = download_artifact(artifact, token)
    if len(raw) != size or sha256_bytes(raw) != artifact_sha256:
        raise ValueError("Contract uploaded artifact bytes differ from the caller-bound identity")
    return artifact, raw


def _verify_contract_ci_capture(root: Path, contract_version: str, *, with_transport: bool = False):
    stage = root / "phases/metadata/stage"
    manifest = verify_output_manifest_identity(
        stage, "contract", "contract", "metadata", "common", contract_version)
    payload = stage / f"outputs/codex-agent-contract-{contract_version}.zip"
    closure = verify_contract_execution_closure(payload, root / "execution-closure")
    expected = {"phases/metadata/stage/output-manifest.json", payload.relative_to(root).as_posix(),
                "execution-closure/contract-execution-closure.json",
                *(f"execution-closure/{record['relativePath']}" for record in closure["files"])}
    if with_transport:
        expected.add("transport/ci-artifact.json")
        # This is retained transport, not a new authority: S626 binds its current
        # upload to caller-owned IDs; original phase admission below is independent.
        transport = require_exact_keys(
            _canonical_control(root / "transport/ci-artifact.json", "Retained Contract capture transport"),
            {"artifact", "captureProducer", "observed"}, "Retained Contract capture transport")
        validate_producer(transport["captureProducer"], "Retained Contract capture producer")
        if not isinstance(transport["artifact"], dict):
            raise ValueError("Retained Contract capture artifact must be an object")
        observations = require_array(transport["observed"], "Retained Contract capture observations")
        if len(observations) != 1:
            raise ValueError("Retained Contract capture must have one original capture observation")
        observation = require_exact_keys(observations[0], {"run", "testedCommit", "jobs"}, "Retained capture observation")
        if not isinstance(observation["run"], dict) or not isinstance(observation["testedCommit"], dict):
            raise ValueError("Retained capture run and tested commit must be objects")
        require_array(observation["jobs"], "Retained capture jobs")
    if {record["relativePath"] for record in regular_file_inventory(root)} != expected:
        raise ValueError("Contract uploaded artifact inventory is not exact")
    metadata = _canonical_control(root / "execution-closure/receipts/metadata.json", "Original Contract metadata receipt")
    if manifest["outputs"] != metadata["outputs"]:
        raise ValueError("Contract uploaded metadata stage differs from its original receipt")


def capture_contract_ci_artifact(
    destination: Path, *, artifact_id: int, artifact_sha256: str,
    transport_producer: Mapping[str, Any], trusted_workflow_sha: str,
    contract_version: str, token: str,
) -> dict[str, Any]:
    """Capture one caller-bound upload; this is not release-signing authorization.

    ID/digest must come from the successful capture job's upload outputs in the
    trusted caller, never from the artifact. Reused original receipts still need
    their own signed-index/original-CI admission before a release signature.
    """
    require_integer(artifact_id, "Contract upload artifact ID", 1)
    require_sha256(artifact_sha256, "Contract upload artifact digest")
    require_semver(contract_version, "Contract upload version")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract CI capture destination must not exist")
    observed = _observe_contract_producer_runs(
        {"metadata": transport_producer}, phases=("metadata",),
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    artifact, raw = _download_contract_ci_upload(
        artifact_id, artifact_sha256,
        f"codex-agent-contract-attestation-inputs-{transport_producer['tree']}",
        transport_producer, observed[0]["run"], token)
    with tempfile.TemporaryDirectory(prefix="contract-ci-capture-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "transport.zip"
        archive.write_bytes(raw)
        verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
        prepared = root / "captured"
        safe_extract(archive, prepared)
        _verify_contract_ci_capture(prepared, contract_version)
        evidence = {"artifact": artifact, "captureProducer": dict(transport_producer), "observed": observed}
        write_canonical_json(prepared / "transport/ci-artifact.json", evidence)
        publish_regular_tree(prepared, destination)
    return evidence


def capture_contract_original_ci_phases(
    capture_root: Path, destination: Path, *, contract_version: str,
    trusted_workflow_sha: str, token: str,
    release_handoffs: tuple[Path, ...] = (), keyring: Path | None = None,
    keys_directory: Path | None = None,
) -> dict[str, Any]:
    """Bind original CI or release-attested receipts; never authorize new signing."""
    require_semver(contract_version, "Original Contract version")
    if bool(release_handoffs) != (keyring is not None and keys_directory is not None) or \
            (keyring is None) != (keys_directory is None):
        raise ValueError("Retained release Contract handoffs require caller-owned keyring and keys only")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Original Contract CI destination must not exist")
    source = Path(capture_root)
    resolved_destination = destination.parent.resolve(strict=False) / destination.name
    for original in (source, *release_handoffs, *(path for path in (keyring, keys_directory) if path is not None)):
        resolved_source = Path(original).resolve(strict=True)
        if resolved_source == resolved_destination or resolved_source in resolved_destination.parents or resolved_destination in resolved_source.parents:
            raise ValueError("Original Contract CI capture source and destination must not overlap")
    phases = ("binary", "package", "validation", "metadata")
    with tempfile.TemporaryDirectory(prefix="contract-original-ci-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "captured"
        capture = prepared / "contract-input"
        snapshot_regular_tree(source, capture)
        _verify_contract_ci_capture(capture, contract_version, with_transport=True)
        originals = {phase: read_regular_file_bytes(capture / f"execution-closure/receipts/{phase}.json",
                     max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) for phase in phases}
        producers = {phase: load_canonical_json_bytes(raw)["producer"] for phase, raw in originals.items()}
        releases = {}
        if release_handoffs:
            policy = prepared / "release-policy"
            policy.mkdir()
            captured_keyring = policy / "keyring.json"
            captured_keyring.write_bytes(read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
            captured_keys = policy / "keys"
            captured_keys.mkdir()
            public_policy = load_keyring(captured_keyring, keys_directory)
            for record in ([public_policy["activeKey"]] if public_policy["activeKey"] else []) + public_policy["retiredKeys"]:
                key_id = record["keyId"]
                (captured_keys / f"{key_id}.pub").write_bytes(read_regular_file_bytes(
                    public_key_path(keys_directory, key_id), max_bytes=1024 * 1024, reject_symlink_parents=True))
            load_keyring(captured_keyring, captured_keys)
            for number, original in enumerate(release_handoffs):
                retained = prepared / "release-handoffs" / str(number)
                snapshot_regular_tree(original, retained)
                stem = f"codex-agent-contract-{contract_version}"
                payload = retained / f"{stem}.zip"
                closure = retained / "execution-closure"
                verify_contract_attestation(
                    payload, closure / "receipts/metadata.json",
                    retained / f"{stem}.attestation.json", retained / f"{stem}.attestation.sig",
                    retained / "public-key.pub", required_trust_domain="release",
                    keyring=captured_keyring, keys_directory=captured_keys)
                expected = {payload.name, "public-key.pub", f"{stem}.attestation.json", f"{stem}.attestation.sig",
                            "execution-closure/contract-execution-closure.json",
                            "execution-closure/execution/contract-execution.zip",
                            *(f"execution-closure/receipts/{phase}.json" for phase in phases)}
                if {record["relativePath"] for record in regular_file_inventory(retained)} != expected:
                    raise ValueError("Retained release Contract handoff inventory is not exact")
                matching = [phase for phase in phases if read_regular_file_bytes(
                    closure / f"receipts/{phase}.json", max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) == originals[phase]]
                if not matching:
                    raise ValueError("Retained release Contract handoff proves no requested original phase")
                for phase in matching:
                    releases.setdefault(phase, number)
        ci_phases = tuple(phase for phase in phases if phase not in releases)
        observed = _observe_contract_producer_runs(
            {phase: producers[phase] for phase in ci_phases}, phases=ci_phases,
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        attempts = {(value["run"]["id"], value["run"]["run_attempt"]): value for value in observed}
        inventories, artifacts = {}, {}
        for phase in ci_phases:
            producer = producers[phase]
            run_id = producer["runId"]
            if run_id not in inventories:
                inventories[run_id] = paginated_items(
                    f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{run_id}/artifacts", "artifacts", token)
            name = f"codex-agent-product-phase-contract-contract-{phase}-common-{producer['tree']}"
            candidates = [value for value in inventories[run_id] if isinstance(value, dict) and value.get("name") == name]
            if len(candidates) != 1:
                raise ValueError(f"Original Contract {phase} upload is missing or ambiguous")
            candidate = candidates[0]
            attempt = attempts[(run_id, producer["runAttempt"])]
            artifact, raw = _download_contract_ci_upload(
                candidate.get("id"), candidate.get("digest"), name, producer,
                attempt["run"], token)
            # Artifact run IDs do not distinguish attempts. Bind the upload to
            # the successful original job observed through its exact-attempt API.
            job_name = ("product-validation / product-contracts" if phase == "binary"
                        else "product-validation / contract-continuation")
            job = next(value for value in attempt["jobs"] if value.get("name") == job_name)
            timestamps = []
            for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at")):
                timestamp = datetime.fromisoformat(require_string(value, "Original Contract CI timestamp").replace("Z", "+00:00"))
                if timestamp.utcoffset() != timedelta(0):
                    raise ValueError("Original Contract CI timestamps must be UTC")
                timestamps.append(timestamp)
            if not timestamps[0] <= timestamps[1] <= timestamps[2]:
                raise ValueError("Original Contract upload is outside its original producer job window")
            archive = root / f"{phase}.zip"
            archive.write_bytes(raw)
            verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
            shard = prepared / "original-phases" / phase
            safe_extract(archive, shard)
            verified = verify_phase_shard(shard, PhaseInstanceId("contract", "contract", phase, "common"))
            if verified["receiptBytes"] != originals[phase]:
                raise ValueError(f"Original Contract {phase} upload differs from the retained phase receipt")
            artifacts[phase] = artifact
        evidence = {"observed": observed, "artifacts": artifacts,
                    "receiptSha256s": {phase: sha256_bytes(raw) for phase, raw in originals.items()}}
        if release_handoffs:
            evidence["releaseAttestations"] = releases
        write_canonical_json(prepared / "transport/original-ci-phases.json", evidence)
        publish_regular_tree(prepared, destination)
    return evidence


def _validate_plan(plan_path: Path, root: Path) -> dict[str, Any]:
    plan = require_exact_keys(
        load_json_bytes(plan_path.read_bytes()), _PLAN_KEYS, "impact plan",
    )
    if require_integer(plan["schemaVersion"], "impact plan.schemaVersion", 1) != 1:
        raise ValueError("Unsupported impact plan schemaVersion")
    validate_remote_build_authorization(plan)
    validate_legacy_lane_projection(plan, repository_root=root, plan_path=plan_path)
    commit = require_string(plan["validationCommit"], "impact plan.validationCommit")
    tree = require_string(plan["validationTree"], "impact plan.validationTree")
    if _OID.fullmatch(commit) is None or _OID.fullmatch(tree) is None:
        raise ValueError("Impact plan validation identity is malformed")
    if _git_value(root, "rev-parse", "HEAD^{commit}") != commit:
        raise ValueError("Checkout commit does not match the impact plan")
    if _git_value(root, "rev-parse", "HEAD^{tree}") != tree:
        raise ValueError("Checkout tree does not match the impact plan")
    return plan


def _requested(plan: Mapping[str, Any]) -> tuple[PhaseInstanceId, ...]:
    selection = classify_paths(plan["changedPaths"])
    if list(selection.unknown_paths) != plan["unknownPaths"]:
        raise ValueError("Impact plan unknown paths disagree with product selection")
    # Unknown paths already make classify_paths fail closed to every phase. Only the
    # explicit fullRequested flag may otherwise broaden the authoritative selection.
    return PHASE_INSTANCE_IDS if plan["fullRequested"] or selection.unknown_paths else selection.instances


def _versions(root: Path, revision: str) -> dict[str, str]:
    values = {
        name: require_semver(
            git_regular_blob_bytes(root, revision, path, max_bytes=256).decode("utf-8").strip(),
            f"{name} version",
        )
        for name, path in _VERSION_PATHS.items()
    }
    major, minor, _ = values["runtime-release"].split("-", 1)[0].split(".")
    values["runtime-compatibility"] = f"{major}.{minor}.0"
    return values


def _authorities(
    root: Path,
    revision: str,
    closure: tuple[PhaseInstanceId, ...],
) -> tuple[list[dict[str, Any]] | None, str | None]:
    paths = {path for path, _ in tree_entries(root, revision)}
    native_flags = None
    records = []
    for instance in closure:
        profile = required_toolchain_profile(instance)
        if profile is None:
            toolchain_digest = NOT_APPLICABLE_TOOLCHAIN_DIGEST
        else:
            profile_path = f"{_PROFILE_ROOT}/{profile}.json"
            if profile_path not in paths:
                return None, "toolchain-profile-unavailable"
            toolchain_digest = load_toolchain_profile_bytes(
                git_regular_blob_bytes(root, revision, profile_path, max_bytes=65_536),
                profile,
            ).digest
        if (
            instance.product == "runtime"
            and instance.component in NATIVE_TARGETS
            and instance.phase == "binary"
        ):
            if native_flags is None:
                native_flags = load_runtime_binary_flags_bytes(git_regular_blob_bytes(
                    root,
                    revision,
                    "codex-agent-runtime-desktop/native/c-api/binary-flags.json",
                    max_bytes=65_536,
                ))
            flags_digest = native_flags[instance.component].digest
        else:
            flags_digest = NOT_APPLICABLE_FLAGS_DIGEST
        records.append({
            **_identity_record(instance),
            "toolchainProfileDigest": toolchain_digest,
            "flagsDigest": flags_digest,
            "outputSchemaVersion": 1,
        })
    return records, None


def _release_trust(root: Path, revision: str, destination: Path) -> ReleaseTrust | None:
    paths = {path for path, _ in tree_entries(root, revision)}
    if _KEYRING_PATH not in paths:
        return None
    keyring_bytes = git_regular_blob_bytes(root, revision, _KEYRING_PATH, max_bytes=64 * 1024)
    keyring_value = require_exact_keys(
        load_canonical_json_bytes(keyring_bytes),
        {"schemaVersion", "namespace", "algorithm", "trustDomain", "activeKey", "retiredKeys"},
        "tracked product-signing keyring",
    )
    retired = require_array(keyring_value["retiredKeys"], "tracked product-signing keyring.retiredKeys")
    records = [record for record in (keyring_value["activeKey"], *retired) if record is not None]
    trust = destination / "trust"
    keys = trust / "keys"
    keys.mkdir(parents=True)
    keyring = trust / "product-signing-keys.json"
    keyring.write_bytes(keyring_bytes)
    for record in records:
        if type(record) is not dict or type(record.get("keyId")) is not str:
            raise ValueError("Tracked product-signing key record is malformed")
        relative = f"{_KEYS_ROOT}/{record['keyId']}.pub"
        (keys / f"{record['keyId']}.pub").write_bytes(
            git_regular_blob_bytes(root, revision, relative, max_bytes=64 * 1024),
        )
    load_keyring(keyring, keys)
    if not records:
        shutil.rmtree(trust)
        return None
    return ReleaseTrust(keyring, keys)


def _catalog_files(root: Path) -> set[str]:
    files: set[str] = set()
    for entry in root.rglob("*"):
        mode = entry.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError(f"Product catalog contains an unsafe entry: {entry}")
        if stat.S_ISREG(mode):
            files.add(entry.relative_to(root).as_posix())
    return files


def _materialize_catalog(
    source: str,
    artifact: Mapping[str, Any],
    token: str,
    destination: Path,
    repository: str,
    pull_request: int | None,
    release_trust: ReleaseTrust | None,
    workflow_run: Mapping[str, Any] | None = None,
    *, api: str | None = None,
) -> Catalog:
    artifact_id = require_integer(artifact.get("id"), "product catalog artifact.id", 1)
    root = destination / "catalogs" / source / str(artifact_id)
    root.mkdir(parents=True)
    archive = root / "transport.zip"
    archive.write_bytes(download_artifact(dict(artifact), token))
    verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
    extracted = root / "contents"
    safe_extract(archive, extracted)
    index_path = extracted / "product-index.json"
    signature_path = extracted / "product-index.sig"
    index_bytes = index_path.read_bytes()
    index = validate_product_index(load_canonical_json_bytes(index_bytes))
    if index["repository"] != repository:
        raise ValueError("Product catalog repository mismatch")
    expected_kind = {"stable": "stable", "promoted-main": "promoted-main", "same-pr": "pull-request"}[source]
    if index["context"]["kind"] != expected_kind:
        raise ValueError("Product catalog context mismatch")
    if source == "same-pr" and index["context"]["pullRequest"] != pull_request:
        raise ValueError("Product catalog pull-request context mismatch")
    if source == "same-pr":
        if workflow_run is None:
            if api is None:
                raise ValueError("Same-PR product catalog lacks verified workflow-run provenance")
            # Original claims select what to authenticate; they confer no authority.
            # Current-consumer commit/tree belong only to the subsequent key planner.
            workflow_run = _same_pr_run(
                artifact, api, repository, pull_request, token,
                index["producer"]["commit"], index["producer"]["tree"],
                expected_attempt=index["producer"]["runAttempt"])
        observed = require_exact_keys(workflow_run, {"run", "testedCommit"}, "Same-PR workflow observation")
        workflow_run = observed["run"]
        tested_commit = observed["testedCommit"]
        run_id = require_integer(workflow_run.get("id"), "product catalog workflow run ID", 1)
        run_attempt = require_integer(
            workflow_run.get("run_attempt"), "product catalog workflow run attempt", 1,
        )
        tested_sha = require_string(
            tested_commit.get("sha"), "product catalog tested commit SHA",
        )
        workflow_path = require_string(
            workflow_run.get("path"), "product catalog workflow path",
        )
        tested_tree = tested_commit.get("tree")
        tree = require_string(
            tested_tree.get("sha") if isinstance(tested_tree, dict) else None,
            "product catalog tested tree",
        )
        if (
            index["context"]["runId"] != run_id
            or index["producer"]["runId"] != run_id
            or index["context"]["runAttempt"] != run_attempt
            or index["producer"]["runAttempt"] != run_attempt
            or index["context"]["commit"] != tested_sha
            or index["producer"]["commit"] != tested_sha
            or index["context"]["tree"] != tree
            or index["producer"]["tree"] != tree
            or index["producer"]["workflowPath"] != workflow_path
        ):
            raise ValueError("Same-PR product catalog claims different workflow provenance")
        write_canonical_json(root / "workflow-provenance.json", observed)
    controls = {"product-index.json", "product-index.sig"}
    public_key: Path | None = None
    if source == "same-pr":
        public_key = extracted / "public-key.pub"
        controls.add("public-key.pub")
    objects: dict[str, Path] = {}
    expected_objects: dict[str, str] = {}
    for entry in index["entries"]:
        relative = object_relative_path(entry["buildKey"], entry["receiptSha256"])
        expected_objects[entry["buildKey"]] = relative
        path = extracted.joinpath(*PurePosixPath(relative).parts)
        if path.is_file() and not path.is_symlink():
            objects[entry["buildKey"]] = path
    contract_entries = [
        entry for entry in index["entries"]
        if (entry["product"], entry["component"], entry["phase"], entry["target"])
        == ("contract", "contract", "metadata", "common")
    ]
    if len(contract_entries) > 1:
        raise ValueError("Product catalog contains duplicate Contract metadata entries")
    contract_attestation = None
    contract_attestation_signature = None
    if contract_entries:
        version = contract_entries[0]["productVersion"]
        contract_attestation = extracted / f"codex-agent-contract-{version}.attestation.json"
        contract_attestation_signature = extracted / f"codex-agent-contract-{version}.attestation.sig"
        controls.update({contract_attestation.name, contract_attestation_signature.name})
        controls.update({"execution-closure/contract-execution-closure.json",
                         "execution-closure/execution/contract-execution.zip",
                         *(f"execution-closure/receipts/{phase}.json"
                           for phase in ("binary", "package", "validation", "metadata"))})
    actual = _catalog_files(extracted)
    native_root = extracted / "native-runtime-evidence"
    native_records = []
    if native_root.exists():
        native_records = _rebase_native_evidence_paths(
            load_native_runtime_evidence(native_root), native_root, destination, comparison=True)
        controls.update(f"native-runtime-evidence/{path}" for path in _catalog_files(native_root))
    adapter_root = extracted / "adapter-runtime-evidence"
    adapter_records = []
    if adapter_root.exists():
        adapter_records = rebase_adapter_comparison_records(
            load_adapter_runtime_evidence(adapter_root), adapter_root, destination)
        controls.update(f"adapter-runtime-evidence/{path}" for path in _catalog_files(adapter_root))
    sdk_root = extracted / "sdk-validation-evidence"
    if sdk_root.exists():
        sdk_records = load_sdk_validation_evidence(sdk_root)
        indexed = {(entry["receiptSha256"], entry["component"], entry["target"])
                   for entry in index["entries"] if entry["product"] == "sdk" and entry["phase"] == "validation"}
        if any((record["receiptSha256"], record["component"], record["target"]) not in indexed for record in sdk_records):
            raise ValueError("SDK catalog evidence lacks its exact indexed original validation receipt")
        controls.update(f"sdk-validation-evidence/{path}" for path in _catalog_files(sdk_root))
    else:
        sdk_root = None
    if not controls.issubset(actual) or not actual.issubset(controls | set(expected_objects.values())):
        raise ValueError("Product catalog file set is incomplete or unexpected")
    contract_public_key = None
    if contract_attestation is not None:
        attestation = validate_contract_attestation(load_canonical_json_bytes(
            read_regular_file_bytes(
                contract_attestation,
                max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True,
            ),
        ))
        if source == "same-pr":
            contract_public_key = public_key
        elif release_trust is not None:
            contract_public_key = public_key_for_metadata(
                attestation["signing"],
                load_keyring(release_trust.keyring, release_trust.keys),
                release_trust.keys,
                allow_retired=True,
            )
        closure_bytes = read_regular_file_bytes(
            extracted / "execution-closure/contract-execution-closure.json",
            max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        if sha256_bytes(closure_bytes) != attestation["executionClosureSha256"]:
            raise ValueError("Contract catalog closure differs from its original attestation")
        closure = require_exact_keys(load_canonical_json_bytes(closure_bytes),
            {"schemaVersion", "product", "contractVersion", "payload", "files"}, "Contract catalog execution closure")
        verify_regular_file_inventory(extracted / "execution-closure", sorted([
            *require_array(closure["files"], "Contract catalog execution closure files"),
            {"relativePath": "contract-execution-closure.json", "bytes": len(closure_bytes),
             "sha256": sha256_bytes(closure_bytes)},
        ], key=lambda record: record["relativePath"]), with_kind=False)
        entry = contract_entries[0]
        metadata_object = objects.get(entry["buildKey"])
        if metadata_object is not None:
            if contract_public_key is None:
                raise ValueError("Contract catalog lacks caller-owned attestation trust")
            with tempfile.TemporaryDirectory(prefix="contract-catalog-closure-") as temporary:
                stage = Path(temporary).resolve() / "stage"
                restored = restore_object(metadata_object, stage,
                    build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
                _verify_index_receipt(entry, {**restored, "receiptSha256": sha256_bytes(restored["receiptBytes"])})
                receipt = stage.parent / "metadata-receipt.json"
                receipt.write_bytes(restored["receiptBytes"])
                verify_contract_attestation(
                    stage / f"outputs/codex-agent-contract-{entry['productVersion']}.zip",
                    receipt, contract_attestation, contract_attestation_signature, contract_public_key,
                    required_trust_domain="development" if source == "same-pr" else "release",
                    keyring=release_trust.keyring if source != "same-pr" and release_trust else None,
                    keys_directory=release_trust.keys if source != "same-pr" and release_trust else None)
    request_objects = [{
        "buildKey": entry["buildKey"],
        "objectPath": _relative(destination, objects[entry["buildKey"]])
        if entry["buildKey"] in objects else None,
    } for entry in index["entries"]]
    request = {
        "manifest": _relative(destination, index_path),
        "signature": _relative(destination, signature_path),
        "publicKey": _relative(destination, public_key) if public_key is not None else None,
        "keyring": _relative(destination, release_trust.keyring)
        if source != "same-pr" and release_trust is not None else None,
        "keysDirectory": _relative(destination, release_trust.keys)
        if source != "same-pr" and release_trust is not None else None,
        "contractAttestation": _relative(destination, contract_attestation)
        if contract_attestation is not None else None,
        "contractAttestationSignature": _relative(destination, contract_attestation_signature)
        if contract_attestation_signature is not None else None,
        "contractPublicKey": _relative(destination, contract_public_key)
        if contract_public_key is not None else None,
        "objects": request_objects,
    }
    return Catalog(
        source,
        index,
        sha256_bytes(index_bytes),
        request,
        objects,
        contract_attestation,
        contract_attestation_signature,
        tuple(native_records),
        tuple(adapter_records),
        sdk_root,
    )


def _candidate_artifacts(
    artifacts: list[object], source: str, pull_request: int | None,
    versions: Mapping[str, str],
) -> list[dict[str, Any]]:
    suffix = {
        "stable": "stable-",
        "promoted-main": "promoted-main-",
        "same-pr": f"pull-request-{pull_request}-",
    }[source]
    prefix = _CATALOG_PREFIX + suffix
    stable_names = {
        f"{prefix}contract-{versions['contract']}",
        f"{prefix}runtime-{versions['runtime-release']}",
        f"{prefix}sdk-{versions['sdk']}",
    }
    candidates = []
    for value in artifacts:
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            continue
        matches = value["name"] in stable_names if source == "stable" else value["name"].startswith(prefix)
        if not matches:
            continue
        if type(value.get("expired")) is not bool:
            raise ValueError("Product catalog artifact expiration state is malformed")
        if value["expired"]:
            continue
        require_integer(value.get("id"), "product catalog artifact.id", 1)
        candidates.append(value)
    candidates.sort(key=lambda value: value["id"], reverse=True)
    if source != "stable":
        return candidates[:1]
    latest = {}
    for value in candidates:
        latest.setdefault(value["name"], value)
    return [latest[name] for name in sorted(latest)]


def _discover_catalogs(
    plan: Mapping[str, Any], destination: Path, release_trust: ReleaseTrust | None,
    environ: Mapping[str, str], versions: Mapping[str, str],
) -> list[Catalog]:
    token = environ.get("GITHUB_TOKEN")
    api = environ.get("GITHUB_API_URL")
    repository = environ.get("GITHUB_REPOSITORY")
    if not token or not api or not repository:
        return []
    if repository != plan["repository"]:
        raise ValueError("GitHub repository does not match the impact plan")
    artifacts = paginated_items(
        f"{api}/repos/{repository}/actions/artifacts", "artifacts", token,
    )
    result = []
    for source in ("stable", "promoted-main", "same-pr"):
        if source == "same-pr" and plan["pullRequest"] is None:
            continue
        if source != "same-pr" and release_trust is None:
            continue
        for artifact in _candidate_artifacts(artifacts, source, plan["pullRequest"], versions):
            result.append(_materialize_catalog(
                source, artifact, token, destination, repository, plan["pullRequest"], release_trust,
                api=api,
            ))
    return result


def _catalog_request(catalogs: list[Catalog]) -> dict[str, Any]:
    stable = sorted(
        (catalog.request for catalog in catalogs if catalog.source == "stable"),
        key=lambda value: value["manifest"],
    )
    return {
        "stable": stable,
        "promotedMain": next((c.request for c in catalogs if c.source == "promoted-main"), None),
        "samePr": next((c.request for c in catalogs if c.source == "same-pr"), None),
        "local": None,
    }


def _wave_request(
    plan: Mapping[str, Any], root: Path, destination: Path,
    requested: tuple[PhaseInstanceId, ...], versions: dict[str, str],
    authorities: list[dict[str, Any]], catalogs: list[Catalog],
    contract_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    closure = set(_dependency_closure(requested))
    request = {
        "schemaVersion": 1,
        "requestType": "reuse-wave",
        "repository": plan["repository"],
        "pullRequest": plan["pullRequest"],
        "repositoryRoot": str(root),
        "repositoryRevision": plan["validationCommit"],
        "artifactRoot": str(destination),
        "requested": [_identity_record(instance) for instance in requested],
        "versions": versions,
        "phaseAuthorities": [record for record in authorities if _identity(record) in closure],
        "contractEvidence": contract_evidence,
        "runtimeValidationEvidence": [],
        "availableObjects": [],
        "catalogs": _catalog_request(catalogs),
    }
    records = {}
    for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source)):
        for record in catalog.native_runtime_evidence:
            records.setdefault(record["receiptSha256"], record)
    if records:
        request["nativeRuntimeComparisonEvidence"] = [records[key] for key in sorted(records)]
    adapter_records = {}
    for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source)):
        for record in catalog.adapter_runtime_evidence:
            adapter_records.setdefault(record["receiptSha256"], record)
    if adapter_records:
        request[_ADAPTER_REQUEST_KEY] = [adapter_records[key] for key in sorted(adapter_records)]
    return request


def _catalog_for_phase(catalogs: list[Catalog], phase: Mapping[str, Any]) -> Catalog:
    transport = phase.get("transportSource")
    if not isinstance(transport, dict):
        raise ValueError("Reused product phase lacks transport provenance")
    for catalog in catalogs:
        if catalog.source == phase["source"] and catalog.index_sha256 == transport.get("indexSha256"):
            return catalog
    raise ValueError("Reused product phase does not identify a persisted catalog")


def _contract_evidence(
    plan: Mapping[str, Any], destination: Path, catalogs: list[Catalog],
    contract_result: Mapping[str, Any], release_trust: ReleaseTrust | None,
) -> dict[str, Any]:
    phase = next((
        value for value in contract_result["phases"]
        if (value["product"], value["component"], value["phase"], value["target"])
        == ("contract", "contract", "metadata", "common")
    ), None)
    if phase is None or phase["state"] != "reused":
        raise ValueError("Complete Contract reuse lacks its metadata phase")
    catalog = _catalog_for_phase(catalogs, phase)
    if catalog.contract_attestation is None or catalog.contract_attestation_signature is None:
        raise ValueError("Complete Contract reuse lacks its detached attestation")
    object_path = catalog.objects.get(phase["buildKey"])
    if object_path is None:
        raise ValueError("Complete Contract reuse lacks its persisted object")
    with tempfile.TemporaryDirectory(prefix="codex-agent-contract-evidence-") as temporary:
        stage = Path(temporary).resolve() / "stage"
        restored = restore_object(
            object_path, stage, build_key=phase["buildKey"],
            receipt_sha256=phase["receiptSha256"], object_sha256=phase["objectSha256"],
        )
        bundles = [output for output in restored["receipt"]["outputs"] if output["kind"] == "contract-bundle"]
        if len(bundles) != 1:
            raise ValueError("Contract metadata object has no unique Contract Bundle")
    attestation = validate_contract_attestation(load_canonical_json_bytes(
        read_regular_file_bytes(
            catalog.contract_attestation,
            max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        ),
    ))
    if catalog.source == "same-pr":
        public_key = destination / catalog.request["publicKey"]
        return {
            "attestation": _relative(destination, catalog.contract_attestation),
            "attestationSignature": _relative(
                destination, catalog.contract_attestation_signature,
            ),
            "publicKey": _relative(destination, public_key),
            "expectedTrustDomain": "development",
            "keyring": None,
            "keysDirectory": None,
        }
    if release_trust is None:
        raise ValueError("Release Contract reuse lacks tracked release trust")
    public_key = public_key_for_metadata(
        attestation["signing"], load_keyring(release_trust.keyring, release_trust.keys),
        release_trust.keys, allow_retired=True,
    )
    return {
        "attestation": _relative(destination, catalog.contract_attestation),
        "attestationSignature": _relative(
            destination, catalog.contract_attestation_signature,
        ),
        "publicKey": _relative(destination, public_key),
        "expectedTrustDomain": "release",
        "keyring": _relative(destination, release_trust.keyring),
        "keysDirectory": _relative(destination, release_trust.keys),
    }


def _validate_reuse_result(
    result: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...],
    *, require_complete: bool,
) -> tuple[dict[str, Any], tuple[PhaseInstanceId, ...], list[dict[str, Any]]]:
    result = require_exact_keys(result, _REUSE_RESULT_KEYS, "Reuse result")
    if require_integer(result["schemaVersion"], "Reuse result.schemaVersion", 1) != 1:
        raise ValueError("Unsupported reuse result schemaVersion")
    full_reuse = require_boolean(result["fullReuse"], "Reuse result.fullReuse")
    matrices = require_exact_keys(
        result["matrices"], {"contract", "runtime", "sdk"}, "Reuse result.matrices",
    )
    actual_matrices = {
        product: require_array(matrices[product], f"Reuse result.matrices.{product}")
        for product in ("contract", "runtime", "sdk")
    }
    closure = _dependency_closure(requested)
    phases = require_array(result["phases"], "Reuse result.phases")
    if len(phases) != len(closure):
        raise ValueError("Reuse result does not cover its exact dependency closure")
    actual = []
    selected: list[PhaseInstanceId] = []
    selected_phases = []
    expected_matrices = {"contract": [], "runtime": [], "sdk": []}
    for index, value in enumerate(phases):
        phase = require_exact_keys(value, _REUSE_PHASE_KEYS, f"Reuse result.phases[{index}]")
        instance = _identity(phase)
        actual.append(instance)
        misses = require_array(phase["misses"], f"Reuse result.phases[{index}].misses")
        miss_sources = []
        for miss_index, miss_value in enumerate(misses):
            miss = require_exact_keys(
                miss_value,
                {"source", "reason"},
                f"Reuse result.phases[{index}].misses[{miss_index}]",
            )
            if miss["source"] not in SOURCES:
                raise ValueError("Reuse result miss source is invalid")
            require_string(miss["reason"], "Reuse result miss reason")
            miss_sources.append(miss["source"])
        if phase.get("state") == "retained":
            if phase["source"] is not None or phase["transportSource"] is not None or misses:
                raise ValueError("Retained reuse phase contains transport evidence")
            for field in ("buildKey", "receiptSha256", "objectSha256"):
                require_sha256(phase[field], f"Reuse result.phases[{index}].{field}")
            selected.append(instance)
            selected_phases.append(phase)
            continue
        if phase.get("state") != "reused":
            if phase.get("state") not in {"build", "waiting"}:
                raise ValueError("Reuse result contains an unsupported phase state")
            if any(phase[field] is not None for field in (
                "source", "transportSource", "receiptSha256", "objectSha256",
            )):
                raise ValueError("Unresolved reuse phase contains materialized evidence")
            if phase["state"] == "waiting":
                if phase["buildKey"] is not None or misses:
                    raise ValueError("Waiting reuse phase contains planned evidence")
            else:
                build_key = require_sha256(
                    phase["buildKey"], f"Reuse result.phases[{index}].buildKey",
                )
                if miss_sources != list(SOURCES):
                    raise ValueError("Build reuse phase does not record every lookup miss")
                expected_matrices[instance.product].append({
                    **_identity_record(instance), "buildKey": build_key,
                })
            continue
        if phase.get("source") not in SOURCES:
            raise ValueError("Reuse result contains an unmaterialized phase")
        source_index = SOURCES.index(phase["source"])
        if miss_sources != list(SOURCES[:source_index]):
            raise ValueError("Reused product phase lookup misses are not source ordered")
        for field in ("buildKey", "receiptSha256", "objectSha256"):
            require_sha256(phase[field], f"Reuse result.phases[{index}].{field}")
        selected.append(instance)
        selected_phases.append(phase)
    if tuple(actual) != closure:
        raise ValueError("Reuse result phase order or identity is invalid")
    if actual_matrices != expected_matrices:
        raise ValueError("Reuse result matrices do not exactly match its build phases")
    selected_set = set(selected)
    if any(
        dependency not in selected_set
        for instance in selected
        for dependency in phase_instance_dependencies(instance)
    ):
        raise ValueError("Reused product phases are not dependency-closed")
    requirements = require_array(
        result["continuationRequirements"], "Reuse result.continuationRequirements",
    )
    requirement_instances = []
    phase_by_instance = {
        _identity(phase): phase for phase in phases
    }
    for index, value in enumerate(requirements):
        label = f"Reuse result.continuationRequirements[{index}]"
        requirement = require_exact_keys(
            value,
            {"kind", *_IDENTITY_KEYS, "dependencies"},
            label,
        )
        if requirement["kind"] not in {"runtime-validation-evidence", "native-runtime-validation-evidence", "sdk-validation-evidence"}:
            raise ValueError("Reuse continuation requirement kind is invalid")
        instance = _identity(requirement)
        if instance not in phase_by_instance:
            raise ValueError("Reuse continuation requirement is outside the dependency closure")
        dependencies = (native_runtime_validation_dependencies(instance)
                        if requirement["kind"] == "native-runtime-validation-evidence"
                        else sdk_validation_dependencies(instance) if requirement["kind"] == "sdk-validation-evidence"
                        else runtime_validation_dependencies(instance))
        if not dependencies:
            raise ValueError("Reuse continuation requirement is not applicable")
        if phase_by_instance[instance]["state"] != "waiting":
            raise ValueError("Reuse continuation requirement is not waiting")
        if require_array(requirement["dependencies"], f"{label}.dependencies") != [
            _identity_record(dependency) for dependency in dependencies
        ]:
            raise ValueError("Reuse continuation requirement dependencies are invalid")
        requirement_instances.append(instance)
    if requirement_instances != sorted(set(requirement_instances)):
        raise ValueError("Reuse continuation requirements must be sorted and unique")
    expected_requirements = [
        instance for instance in closure
        if phase_by_instance[instance]["state"] == "waiting"
        and (runtime_validation_dependencies(instance) or native_runtime_validation_dependencies(instance)
             or sdk_validation_dependencies(instance))
        and all(dependency in selected_set for dependency in phase_instance_dependencies(instance))
    ]
    if requirement_instances != expected_requirements:
        raise ValueError("Reuse continuation requirements do not match ready evidence-consuming phases")
    actually_complete = tuple(selected) == closure
    if (
        result["result"] != ("complete" if actually_complete else "build-required")
        or full_reuse is not actually_complete
    ):
        raise ValueError("Reuse result completion state contradicts its phases")
    if require_complete and not actually_complete:
        raise ValueError("Complete reuse result contains an unresolved phase")
    return dict(result), tuple(selected), selected_phases


def _write_reused_carrier(
    result: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...],
    catalogs: list[Catalog], destination: Path, consumer: Mapping[str, Any],
    *, require_complete: bool,
) -> bool:
    result, selected_instances, selected_phases = _validate_reuse_result(
        result, requested, require_complete=require_complete,
    )
    if any(phase["source"] == "local" for phase in selected_phases):
        raise ValueError("Discovery reuse result unexpectedly contains a local object")
    sources: dict[PhaseInstanceId, Path] = {}
    for instance, phase in zip(selected_instances, selected_phases, strict=True):
        catalog = _catalog_for_phase(catalogs, phase)
        object_path = catalog.objects.get(phase["buildKey"])
        if object_path is None:
            raise ValueError("Reuse result lacks a persisted object")
        verified = verify_object(
            object_path, build_key=phase["buildKey"],
            receipt_sha256=phase["receiptSha256"], object_sha256=phase["objectSha256"],
        )
        if _identity(verified["receipt"]) != instance:
            raise ValueError("Persisted product object identity disagrees with the reuse result")
        sources[instance] = object_path
    if not selected_instances:
        return False
    normalized = {
        "schemaVersion": 1,
        "result": "complete",
        "fullReuse": True,
        "phases": selected_phases,
        "matrices": {"contract": [], "runtime": [], "sdk": []},
    }
    write_carrier(destination, normalized, selected_instances, sources, consumer)
    return True


def _reverify_complete(
    result: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...],
    catalogs: list[Catalog], destination: Path, consumer: Mapping[str, Any],
) -> None:
    _write_reused_carrier(
        result, requested, catalogs, destination / "carrier", consumer, require_complete=True,
    )


def _consumer(plan: Mapping[str, Any], environ: Mapping[str, str]) -> dict[str, Any]:
    event = require_string(plan["event"], "impact plan.event")
    def positive_environment_integer(name: str) -> int:
        value = environ.get(name)
        if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
            raise ValueError(f"{name} must be a positive decimal integer")
        return int(value)
    return {
        "kind": "ci",
        "producer": {
            "repository": plan["repository"],
            "workflowPath": ".github/workflows/ci.yml",
            "commit": plan["validationCommit"],
            "tree": plan["validationTree"],
            "event": event,
            "runId": positive_environment_integer("GITHUB_RUN_ID"),
            "runAttempt": positive_environment_integer("GITHUB_RUN_ATTEMPT"),
            "pullRequest": plan["pullRequest"] if event == "pull_request" else None,
        },
    }


def _discovery_request(plan: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...]) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "requestType": "product-reuse-discovery",
        "repository": plan["repository"],
        "pullRequest": plan["pullRequest"],
        "repositoryRevision": plan["validationCommit"],
        "repositoryTree": plan["validationTree"],
        "requested": [_identity_record(instance) for instance in requested],
    }


def _write_ready_plans(destination: Path, plans: Mapping[PhaseInstanceId, Mapping[str, Any]]) -> None:
    if not plans:
        return
    root = destination / "phase-plans"
    root.mkdir()
    for instance, plan in sorted(plans.items()):
        if _identity(plan) != instance:
            raise ValueError("Ready phase plan identity is invalid")
        write_canonical_json(
            root / f"{instance.product}-{instance.component}-{instance.phase}-{instance.target}.json",
            plan,
        )


def _contract_ready_phase(plans: Mapping[PhaseInstanceId, Mapping[str, Any]]) -> str:
    phases = [
        instance.phase for instance in plans
        if instance.product == "contract" and instance.component == "contract" and instance.target == "common"
    ]
    if len(phases) > 1:
        raise ValueError("Contract reuse wave elected more than one ready phase")
    return phases[0] if phases else "none"


def _result(
    requested: tuple[PhaseInstanceId, ...], *, complete: bool, reason: str,
    reuse: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "result": "complete" if complete else "build-required",
        "reason": reason,
        "fullReuse": complete,
        "targetJobsRequired": not complete,
        "requested": [_identity_record(instance) for instance in requested],
        "reuse": reuse,
    }


def _finish(
    destination: Path, request: Mapping[str, Any], result: Mapping[str, Any],
    github_output_path: Path, *, contract_next_phase: str = "none",
    contract_reconciliation_required: bool = False,
) -> dict[str, Any]:
    write_canonical_json(destination / "request.json", request)
    write_canonical_json(destination / "result.json", result)
    github_output(github_output_path, {
        "full_reuse": result["fullReuse"],
        "target_jobs_required": result["targetJobsRequired"],
        "product_reuse_reason": result["reason"],
        "contract_next_phase": contract_next_phase,
        "contract_reconciliation_required": contract_reconciliation_required,
    })
    return dict(result)


def _canonical_control(path: Path, label: str) -> dict[str, Any]:
    try:
        value = load_canonical_json_bytes(read_regular_file_bytes(
            path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        ))
    except OSError as error:
        raise ValueError(f"{label} is missing or unsafe") from error
    if type(value) is not dict:
        raise ValueError(f"{label} must be an object")
    return value


def _rebase_catalog_paths(
    catalogs: Mapping[str, Any], source_root: Path, repository_root: Path,
) -> dict[str, Any]:
    value = require_exact_keys(
        catalogs, {"stable", "promotedMain", "samePr", "local"}, "Contract reuse catalogs",
    )
    if value["local"] is not None:
        raise ValueError("Contract workflow reconciliation does not accept a local catalog")

    def relative(member: Any, label: str) -> str | None:
        if member is None:
            return None
        path = source_root.joinpath(*PurePosixPath(require_relative_path(member, label)).parts)
        try:
            return path.relative_to(repository_root).as_posix()
        except ValueError as error:
            raise ValueError(f"{label} escapes the repository") from error

    def catalog(member: Any, label: str) -> dict[str, Any]:
        record = require_exact_keys(
            member,
            {
                "manifest", "signature", "publicKey", "keyring", "keysDirectory",
                "contractAttestation", "contractAttestationSignature", "contractPublicKey",
                "objects",
            },
            label,
        )
        objects = []
        for index, object_value in enumerate(require_array(record["objects"], f"{label}.objects")):
            object_label = f"{label}.objects[{index}]"
            item = require_exact_keys(object_value, {"buildKey", "objectPath"}, object_label)
            objects.append({
                "buildKey": item["buildKey"],
                "objectPath": relative(item["objectPath"], f"{object_label}.objectPath"),
            })
        return {
            "manifest": relative(record["manifest"], f"{label}.manifest"),
            "signature": relative(record["signature"], f"{label}.signature"),
            "publicKey": relative(record["publicKey"], f"{label}.publicKey"),
            "keyring": relative(record["keyring"], f"{label}.keyring"),
            "keysDirectory": relative(record["keysDirectory"], f"{label}.keysDirectory"),
            "contractAttestation": relative(
                record["contractAttestation"], f"{label}.contractAttestation",
            ),
            "contractAttestationSignature": relative(
                record["contractAttestationSignature"],
                f"{label}.contractAttestationSignature",
            ),
            "contractPublicKey": relative(
                record["contractPublicKey"], f"{label}.contractPublicKey",
            ),
            "objects": objects,
        }

    return {
        "stable": [
            catalog(member, f"Contract reuse catalogs.stable[{index}]")
            for index, member in enumerate(require_array(value["stable"], "Contract reuse catalogs.stable"))
        ],
        "promotedMain": None if value["promotedMain"] is None else catalog(
            value["promotedMain"], "Contract reuse catalogs.promotedMain",
        ),
        "samePr": None if value["samePr"] is None else catalog(
            value["samePr"], "Contract reuse catalogs.samePr",
        ),
        "local": None,
    }


def _catalog_object_sources(request: Mapping[str, Any]) -> dict[tuple[str, str, str], Path]:
    root = Path(request["artifactRoot"])
    catalogs = request["catalogs"]
    values = [
        *(('stable', member) for member in catalogs["stable"]),
        *((('promoted-main', catalogs["promotedMain"]),) if catalogs["promotedMain"] else ()),
        *((('same-pr', catalogs["samePr"]),) if catalogs["samePr"] else ()),
    ]
    result = {}
    for source, catalog in values:
        manifest_path = root.joinpath(*PurePosixPath(catalog["manifest"]).parts)
        manifest_bytes = read_regular_file_bytes(
            manifest_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )
        index_sha256 = sha256_bytes(manifest_bytes)
        for record in catalog["objects"]:
            if record["objectPath"] is not None:
                result[(source, index_sha256, record["buildKey"])] = root.joinpath(
                    *PurePosixPath(record["objectPath"]).parts,
                )
    return result


def _rebase_contract_evidence_paths(
    value: Mapping[str, Any] | None, source_root: Path, repository_root: Path,
) -> dict[str, Any] | None:
    if value is None:
        return None
    evidence = require_exact_keys(
        value,
        {
            "attestation", "attestationSignature", "publicKey", "expectedTrustDomain",
            "keyring", "keysDirectory",
        },
        "Runtime reuse Contract evidence",
    )

    def relative(member: Any, label: str) -> str | None:
        if member is None:
            return None
        path = source_root.joinpath(*PurePosixPath(require_relative_path(member, label)).parts)
        try:
            return path.relative_to(repository_root).as_posix()
        except ValueError as error:
            raise ValueError(f"{label} escapes the repository") from error

    return {
        "attestation": relative(evidence["attestation"], "Contract attestation"),
        "attestationSignature": relative(
            evidence["attestationSignature"], "Contract attestation signature",
        ),
        "publicKey": relative(evidence["publicKey"], "Contract public key"),
        "expectedTrustDomain": require_string(
            evidence["expectedTrustDomain"], "Contract expected trust domain",
        ),
        "keyring": relative(evidence["keyring"], "Contract keyring"),
        "keysDirectory": relative(evidence["keysDirectory"], "Contract keys directory"),
    }


def _rebase_native_evidence_paths(value, source_root: Path, repository_root: Path, *, comparison=False):
    """Relocate transport paths only; signatures and original receipts are untouched."""
    def relative(path):
        return None if path is None else Path(path).relative_to(repository_root).as_posix()

    def runtime(record):
        return {"target": record["target"],
                "phaseReceipts": {phase: relative(path) for phase, path in record["phaseReceipts"].items()},
                **{name: relative(path) for name, path in record.items() if name not in {"target", "phaseReceipts"}}}

    if comparison:
        return [{"receiptSha256": digest, "runtimeEvidence": runtime(r),
                 "contractEvidence": {name: path if name == "expectedTrustDomain" else relative(path)
                                      for name, path in k.items()}}
                for digest, (k, r) in _native_comparison_records(source_root, value).items()]
    records = [_native_evidence_paths(source_root, record)
               for record in require_array(value, "native Runtime evidence")]
    targets = [record["target"] for record in records]
    if targets != sorted(set(targets)):
        raise ValueError("Native Runtime evidence must be sorted and unique by target")
    return [runtime(record) for record in records]


def _rebase_native_request(request, source_root, artifact_root):
    if "sdkValidationTooling" in request:
        raise ValueError("Retained SDK evidence cannot supply current-invocation tooling authority")
    result = {key: _rebase_native_evidence_paths(request[key], source_root, artifact_root,
                                             comparison=key == "nativeRuntimeComparisonEvidence")
            for key in _NATIVE_REQUEST_KEYS if key in request}
    if _ADAPTER_REQUEST_KEY in request:
        result[_ADAPTER_REQUEST_KEY] = rebase_adapter_comparison_records(request[_ADAPTER_REQUEST_KEY], source_root, artifact_root)
    if "sdkValidationEvidence" in request:
        result["sdkValidationEvidence"] = rebase_sdk_validation_records(request["sdkValidationEvidence"], source_root, artifact_root)
    return result


def _wave_control(path, label):
    value = _canonical_control(path, label)
    return require_exact_keys(value, _WAVE_REQUEST_KEYS | (value.keys() & (_NATIVE_REQUEST_KEYS | {_ADAPTER_REQUEST_KEY} | _SDK_REQUEST_KEYS)), label)


def _relocated_wave_control(path, label, root):
    """Translate only original location tags, never original evidence bytes.

    Producer paths are not opened on this host. All artifact paths remain
    relative and the caller still replays Git, selection, receipts and trust.
    """
    value = _wave_control(path, label)
    original = value["repositoryRoot"]
    if (not isinstance(original, str) or not original
            or any(ord(character) < 32 or ord(character) == 127 for character in original)):
        raise ValueError(f"{label} has an invalid original repository root")
    windows = re.match(r"^[A-Za-z]:\\", original) is not None
    source = PureWindowsPath(original) if windows else PurePosixPath(original)
    if (not source.is_absolute() or str(source) != original or ".." in source.parts
            or source == type(source)(source.anchor)
            or (not windows and ("\\" in original or original.startswith("//")))):
        raise ValueError(f"{label} has a noncanonical original repository root")
    if value["artifactRoot"] != str(source / "build" / "product-reuse"):
        raise ValueError(f"{label} has an unexpected original artifact root")
    return {**value, "repositoryRoot": str(root), "artifactRoot": str(root / "build/product-reuse")}


def _plan_with_sdk_tooling(request, tooling, **kwargs):
    # Never serialize invocation authority into retained control or evidence.
    if "sdkValidationTooling" in request:
        raise ValueError("Retained SDK evidence cannot supply current-invocation tooling authority")
    invocation = dict(request)
    if tooling is not None:
        invocation["sdkValidationTooling"] = tooling
    return plan_reuse_wave(invocation, **kwargs)


def _capture_sdk_handoffs(evidence_roots, destination, artifact_root, *, repository, policy_revision, tooling):
    records = []
    for index, source in enumerate(evidence_roots):
        target = destination / str(index)
        captured = stage_sdk_validation_evidence(load_sdk_validation_evidence(source), source, target,
            repository=repository, policy_revision=policy_revision, tooling=tooling)
        records.extend(rebase_sdk_validation_records(captured, target, artifact_root))
    return records


def _retained_sdk_handoffs(state_root, artifact_root):
    path = state_root / "sdk-validation-evidence"
    if not path.exists():
        return []
    return [record for child in sorted(path.iterdir())
            for record in rebase_sdk_validation_records(load_sdk_validation_evidence(child), child, artifact_root)]


def _verify_discovery_sdk_records(request, discovery_root):
    retained = {}
    _merge_native_comparison_records(retained,
        _retained_sdk_handoffs(discovery_root, discovery_root), key="sdkValidationEvidence")
    if request.get("sdkValidationEvidence", []) != retained.get("sdkValidationEvidence", []):
        raise ValueError("SDK discovery request differs from its complete retained evidence carrier")


def _merge_native_comparison_records(request, records, *, key="nativeRuntimeComparisonEvidence"):
    originals = {record["receiptSha256"]: record
                 for record in request.get(key, [])}
    for record in records:
        originals.setdefault(record["receiptSha256"], record)
    if originals:
        request[key] = [originals[digest] for digest in sorted(originals)]


def _capture_native_handoffs(evidence_roots, destination, artifact_root, release_trust=None, *, adapter=False):
    load = load_adapter_runtime_evidence if adapter else load_native_runtime_evidence
    stage = stage_adapter_runtime_evidence if adapter else stage_native_runtime_evidence
    records = []
    for index, source in enumerate(evidence_roots):
        target = destination / str(index)
        captured = stage(load(source), source, target,
                    keyring=release_trust.keyring if release_trust else None,
                    keys_directory=release_trust.keys if release_trust else None)
        records.extend(rebase_adapter_comparison_records(captured, target, artifact_root) if adapter else
                       _rebase_native_evidence_paths(captured, target, artifact_root, comparison=True))
    return records


def _retained_native_handoffs(state_root, artifact_root, *, adapter=False):
    path = state_root / ("adapter-runtime-evidence" if adapter else "native-runtime-evidence")
    if not path.exists():
        return []
    records = []
    # Each directory is one immutable, independently captured handoff. The
    # exact request decoder and full K/R gate, not directory naming, grant trust.
    for child in sorted(path.iterdir()):
        records.extend(rebase_adapter_comparison_records(load_adapter_runtime_evidence(child), child, artifact_root)
                       if adapter else _rebase_native_evidence_paths(
                           load_native_runtime_evidence(child), child, artifact_root, comparison=True))
    return records


def _available_object_records(
    phases: Mapping[PhaseInstanceId, Mapping[str, Any]],
    sources: Mapping[PhaseInstanceId, Path],
    artifact_root: Path,
) -> list[dict[str, Any]]:
    records = []
    for instance, source in sorted(sources.items()):
        phase = phases[instance]
        try:
            relative = source.relative_to(artifact_root).as_posix()
        except ValueError as error:
            raise ValueError("Product reuse object escapes the artifact root") from error
        records.append({
            **_identity_record(instance),
            "buildKey": phase["buildKey"],
            "receiptSha256": phase["receiptSha256"],
            "objectSha256": phase["objectSha256"],
            "objectPath": relative,
        })
    return records


def _completed_contract_objects(plan, state, artifact_root, environment):
    contract = PhaseInstanceId("contract", "contract", "metadata", "common")
    result = _canonical_control(state / "contract-reuse-result.json", "Completed Contract result")
    _, selected, phases = _validate_reuse_result(result, (contract,), require_complete=True)
    carrier = verify_carrier(state / "carrier", selected, _consumer(plan, environment))
    phases_by_id = {_identity(phase): phase for phase in phases}
    sources = {}
    for record in carrier["objects"]:
        instance = _identity(record)
        if any(record[field] != phases_by_id[instance][field]
               for field in ("buildKey", "receiptSha256", "objectSha256")):
            raise ValueError("Initial Contract object differs from completed state")
        sources[instance] = state / "carrier" / object_relative_path(record["buildKey"], record["receiptSha256"])
    return _available_object_records(phases_by_id, sources, artifact_root), carrier["resolution"]["phases"]


def _runtime_report_output(
    metadata: PhaseInstanceId, dependency: PhaseInstanceId,
    stage: Path, receipt: Mapping[str, Any],
) -> Path:
    evidence_target = RUNTIME_EVIDENCE_TARGETS[dependency.target]
    if metadata.component == "jvm":
        expected = (
            "jvm-evidence",
            f"outputs/jvm-evidence/{jvm_evidence_filename(evidence_target)}",
        )
    elif metadata.component in {"node-js", "node-wasm"}:
        backend = "js" if metadata.component == "node-js" else "wasm"
        expected = (
            "node-evidence",
            f"outputs/node-evidence/{node_evidence_filename(evidence_target, backend)}",
        )
    else:
        candidates = []
        for output in receipt["outputs"]:
            if output["kind"] != "native" or not output["relativePath"].startswith("outputs/native/"):
                continue
            path = stage.joinpath(*PurePosixPath(output["relativePath"]).parts)
            try:
                report = load_canonical_json_bytes(read_regular_file_bytes(
                    path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
                ))
            except (OSError, ValueError):
                continue
            if isinstance(report, dict) and report.get("target") == evidence_target:
                candidates.append(path)
        if len(candidates) != 1:
            raise ValueError("Runtime native validation stage lacks one exact report output")
        return candidates[0]
    matches = [
        output for output in receipt["outputs"]
        if (output["kind"], output["relativePath"]) == expected
    ]
    if len(matches) != 1:
        raise ValueError("Runtime adapter validation stage lacks its exact report output")
    return stage.joinpath(*PurePosixPath(matches[0]["relativePath"]).parts)


def _materialize_runtime_validation_handoffs(
    closure: tuple[PhaseInstanceId, ...],
    phases: Mapping[PhaseInstanceId, Mapping[str, Any]],
    sources: Mapping[PhaseInstanceId, Path],
    destination: Path,
    artifact_root: Path,
) -> list[dict[str, Any]]:
    records = []
    for metadata in closure:
        dependencies = runtime_validation_dependencies(metadata)
        if not dependencies or any(dependency not in sources for dependency in dependencies):
            continue
        handoff = destination / f"{metadata.component}-{metadata.target}"
        receipts = {}
        reports = {}
        for dependency in dependencies:
            dependency_root = handoff / "validation" / f"{dependency.component}-{dependency.target}"
            restored = restore_object(
                sources[dependency],
                dependency_root / "stage",
                build_key=phases[dependency]["buildKey"],
                receipt_sha256=phases[dependency]["receiptSha256"],
                object_sha256=phases[dependency]["objectSha256"],
            )
            receipt_root = dependency_root / "receipt"
            receipt_root.mkdir()
            (receipt_root / "phase-receipt.json").write_bytes(restored["receiptBytes"])
            receipts[dependency.target] = restored["receipt"]
            reports[dependency.target] = _runtime_report_output(
                metadata, dependency, dependency_root / "stage", restored["receipt"],
            )
        ordered_targets = RUNTIME_TARGETS if metadata.component in {"jvm", "node-js", "node-wasm"} else (
            dependencies[0].target,
        )
        ordered_reports = [reports[target] for target in ordered_targets]
        projection = derive_authenticated_runtime_validation_projection(
            metadata.component,
            ordered_reports,
            [receipts[dependency.target] for dependency in dependencies],
        )
        write_canonical_json(handoff / "projection.json", projection)
        records.append({
            **_identity_record(metadata),
            "reports": [path.relative_to(artifact_root).as_posix() for path in ordered_reports],
        })
    return records


def advance_contract(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    shard_roots: list[Path], destination: Path,
    github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    github_output(github_output_path, {
        "contract_complete": False,
        "next_phase_required": False,
        "next_phase": "none",
    })
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    discovery_root = Path(os.path.abspath(discovery_root))
    state_root = discovery_root if state_root is None else Path(os.path.abspath(state_root))
    shard_roots = [Path(os.path.abspath(path)) for path in shard_roots]
    try:
        discovery_root.relative_to(root)
        state_root.relative_to(root)
        for shard_root in shard_roots:
            shard_root.relative_to(root)
    except ValueError as error:
        raise ValueError("Contract reconciliation inputs must remain inside the repository") from error
    plan = _validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
        raise ValueError("Contract reconciliation requires an authorized PR or merge-group run")
    environment = os.environ if environ is None else environ
    consumer = _consumer(plan, environment)
    producer = _canonical_control(discovery_root / "producer.json", "Contract producer")
    validate_producer(producer, "Contract producer")
    if producer != consumer["producer"]:
        raise ValueError("Contract producer does not match the current workflow run")

    request = _relocated_wave_control(discovery_root / "contract-reuse-request.json", "Contract reuse request", root)
    contract = PhaseInstanceId("contract", "contract", "metadata", "common")
    contract_closure = _dependency_closure((contract,))
    authorities, unavailable = _authorities(root, plan["validationCommit"], contract_closure)
    expected_fixed = {
        "schemaVersion": 1,
        "requestType": "reuse-wave",
        "repository": plan["repository"],
        "pullRequest": plan["pullRequest"],
        "repositoryRoot": str(root),
        "repositoryRevision": plan["validationCommit"],
        "requested": [_identity_record(contract)],
        "versions": _versions(root, plan["validationCommit"]),
        "phaseAuthorities": authorities,
        "contractEvidence": None,
        "runtimeValidationEvidence": [],
        "availableObjects": [],
    }
    if authorities is None:
        raise ValueError(unavailable or "Contract phase authority is unavailable")
    for field, expected in expected_fixed.items():
        if request[field] != expected:
            raise ValueError(f"Contract reuse request disagrees with current {field}")
    expected_artifact_root = root / "build/product-reuse"
    if request["artifactRoot"] != str(expected_artifact_root):
        raise ValueError("Contract reuse request has an unexpected original artifact root")
    _verify_discovery_sdk_records(request, discovery_root)

    rebased_request = dict(request)
    rebased_request["artifactRoot"] = str(root)
    rebased_request["catalogs"] = _rebase_catalog_paths(request["catalogs"], discovery_root, root)
    rebased_request.update(_rebase_native_request(request, discovery_root, root))
    replay_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain(plans: dict[PhaseInstanceId, dict[str, Any]], instance: PhaseInstanceId,
               value: dict[str, Any]) -> None:
        if instance in plans:
            raise ValueError(f"Duplicate Contract phase plan: {instance}")
        plans[instance] = value

    replay = _plan_with_sdk_tooling(
        rebased_request, sdk_validation_tooling,
        build_plan_consumer=lambda instance, value: retain(replay_plans, instance, value),
    )
    initial = _canonical_control(
        discovery_root / "contract-reuse-result.json", "Initial Contract reuse result",
    )
    if replay != initial:
        raise ValueError("Initial Contract reuse result is not reproducible from its authenticated request")
    prior = _canonical_control(
        state_root / "contract-reuse-result.json", "Contract reuse result",
    )
    _, prior_materialized, prior_phases = _validate_reuse_result(
        prior, (contract,), require_complete=False,
    )
    prior_by_instance = {_identity(phase): phase for phase in prior["phases"]}
    sources: dict[PhaseInstanceId, Path] = {}
    prior_carrier_phases: dict[PhaseInstanceId, dict[str, Any]] = {}
    carrier_root = state_root / ("carrier" if prior["fullReuse"] else "reused-carrier")
    if prior_materialized:
        verified_carrier = verify_carrier(carrier_root, prior_materialized, consumer)
        prior_carrier_phases = {
            _identity(phase): phase for phase in verified_carrier["resolution"]["phases"]
        }
        if any(
            any(prior_carrier_phases[instance][field] != prior_by_instance[instance][field]
                for field in (*_IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256"))
            for instance in prior_materialized
        ):
            raise ValueError("Prior Contract carrier disagrees with its reuse result")
        for record in verified_carrier["objects"]:
            instance = _identity(record)
            sources[instance] = carrier_root / object_relative_path(
                record["buildKey"], record["receiptSha256"],
            )
    elif carrier_root.exists() or carrier_root.is_symlink():
        raise ValueError("Unexpected prior Contract carrier")

    if state_root != discovery_root:
        state_request = dict(rebased_request)
        state_request["availableObjects"] = [{
            **_identity_record(instance),
            "buildKey": prior_by_instance[instance]["buildKey"],
            "receiptSha256": prior_by_instance[instance]["receiptSha256"],
            "objectSha256": prior_by_instance[instance]["objectSha256"],
            "objectPath": path.relative_to(root).as_posix(),
        } for instance, path in sorted(sources.items())]
        replay_plans = {}
        state_replay = _plan_with_sdk_tooling(
            state_request, sdk_validation_tooling,
            build_plan_consumer=lambda instance, value: retain(replay_plans, instance, value),
        )
        state_by_instance = {_identity(phase): phase for phase in state_replay["phases"]}
        if any(state_by_instance[instance]["state"] != "retained" for instance in prior_materialized):
            raise ValueError("A prior Contract carrier object was not retained by the recomputed plan")
        for instance in prior_materialized:
            state_by_instance[instance].update({
                key: prior_by_instance[instance][key]
                for key in ("state", "source", "transportSource", "misses")
            })
        if state_replay != prior:
            raise ValueError("Contract reuse state is not reproducible from its verified carrier")

    expected_builds = {
        _identity(phase): phase for phase in prior["phases"] if phase["state"] == "build"
    }
    shards = {}
    for shard_root in shard_roots:
        descriptor = require_exact_keys(
            _canonical_control(shard_root / PHASE_SHARD_NAME, "Contract phase shard"),
            PHASE_SHARD_KEYS,
            "Contract phase shard",
        )
        instance = _identity(descriptor)
        if instance in shards:
            raise ValueError(f"Duplicate Contract phase shard: {instance}")
        if instance not in expected_builds:
            raise ValueError(f"Unexpected Contract phase shard: {instance}")
        verified = verify_phase_shard(shard_root, instance)
        receipt = verified["receipt"]
        if (
            receipt["producer"] != producer
            or receipt["trustDomain"] != ("development" if plan["event"] == "pull_request" else "release")
            or receipt["productVersion"] != expected_fixed["versions"]["contract"]
            or receipt["buildKey"] != expected_builds[instance]["buildKey"]
            or replay_plans.get(instance, {}).get("buildKey") != receipt["buildKey"]
        ):
            raise ValueError("Contract phase shard does not match its elected plan and producer")
        shards[instance] = {
            **verified,
            "transportSource": {
                "kind": "phase-shard",
                "descriptorSha256": sha256_bytes(canonical_json_bytes(descriptor)),
                "producer": producer,
            },
        }
        sources[instance] = shard_root / verified["objectPath"]
    if set(shards) != set(expected_builds):
        raise ValueError("Contract phase shards do not exactly match the elected build wave")

    available = []
    for instance, path in sorted(sources.items()):
        phase = prior_by_instance.get(instance)
        verified = shards.get(instance)
        available.append({
            **_identity_record(instance),
            "buildKey": verified["buildKey"] if verified else phase["buildKey"],
            "receiptSha256": verified["receiptSha256"] if verified else phase["receiptSha256"],
            "objectSha256": verified["objectSha256"] if verified else phase["objectSha256"],
            "objectPath": path.relative_to(root).as_posix(),
        })
    advanced_request = dict(rebased_request)
    advanced_request["availableObjects"] = available
    ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
    advanced = _plan_with_sdk_tooling(
        advanced_request, sdk_validation_tooling,
        build_plan_consumer=lambda instance, value: retain(ready_plans, instance, value),
    )
    supplied = set(sources)
    advanced_by_instance = {_identity(phase): phase for phase in advanced["phases"]}
    if any(advanced_by_instance[instance]["state"] != "retained" for instance in supplied):
        raise ValueError("A supplied Contract object was not retained by the recomputed plan")

    advanced, selected, selected_phases = _validate_reuse_result(
        advanced, (contract,), require_complete=False,
    )
    remote_sources = _catalog_object_sources(rebased_request)
    for instance, phase in zip(selected, selected_phases, strict=True):
        if instance in sources:
            continue
        transport = phase["transportSource"]
        key = (phase["source"], transport["indexSha256"], phase["buildKey"])
        try:
            sources[instance] = remote_sources[key]
        except KeyError as error:
            raise ValueError("Advanced Contract reuse lacks its authenticated object") from error

    carrier_phases = []
    for instance, phase in zip(selected, selected_phases, strict=True):
        if instance in shards:
            misses = prior_by_instance[instance]["misses"]
            if [value["source"] for value in misses] != list(SOURCES):
                raise ValueError("Fresh Contract phase lacks its exact prior lookup misses")
            carrier_phases.append({
                **phase,
                "state": "reused",
                "source": "phase-shard",
                "transportSource": shards[instance]["transportSource"],
                "misses": misses,
            })
        elif instance in prior_carrier_phases:
            carrier_phases.append(prior_carrier_phases[instance])
        else:
            carrier_phases.append(phase)

    normalized = {
        "schemaVersion": 1,
        "result": "complete",
        "fullReuse": True,
        "phases": carrier_phases,
        "matrices": {"contract": [], "runtime": [], "sdk": []},
    }
    carrier_name = "carrier" if advanced["fullReuse"] else "reused-carrier"
    with tempfile.TemporaryDirectory(prefix="codex-agent-contract-advance-") as temporary:
        staged_destination = Path(temporary).resolve() / "result"
        staged_destination.mkdir()
        write_carrier(staged_destination / carrier_name, normalized, selected, sources, consumer)
        write_canonical_json(staged_destination / "contract-reuse-result.json", advanced)
        _write_ready_plans(staged_destination, ready_plans)
        # Current-consumer control is required to materialize completed state too;
        # it is external to every original product object and producer receipt.
        write_canonical_json(staged_destination / "producer.json", producer)
        publish_regular_tree(staged_destination, destination)
    github_output(github_output_path, {
        "contract_complete": advanced["fullReuse"],
        "next_phase_required": bool(ready_plans),
        "next_phase": _contract_ready_phase(ready_plans),
    })
    return advanced


def _retain_product_plan(
    plans: dict[PhaseInstanceId, dict[str, Any]],
    instance: PhaseInstanceId,
    value: dict[str, Any],
) -> None:
    if instance in plans:
        raise ValueError(f"Duplicate product phase plan: {instance}")
    plans[instance] = value


@dataclass(frozen=True)
class _VerifiedProductState:
    """Private replay context; never serialized or accepted as caller evidence."""
    plan: dict[str, Any]
    producer: dict[str, Any]
    consumer: dict[str, Any]
    requested: tuple[PhaseInstanceId, ...]
    closure: tuple[PhaseInstanceId, ...]
    expected_fixed: dict[str, Any]
    rebased_request: dict[str, Any]
    prior: dict[str, Any]
    prior_by_instance: dict[PhaseInstanceId, dict[str, Any]]
    sources: dict[PhaseInstanceId, Path]
    prior_carrier_phases: dict[PhaseInstanceId, dict[str, Any]]
    prior_ready_plans: dict[PhaseInstanceId, dict[str, Any]]


def _verified_product_state(
    plan_path: Path, discovery_root: Path, state_root: Path, root: Path,
    environment: Mapping[str, str], sdk_validation_tooling: Mapping[str, Any] | None,
) -> _VerifiedProductState:
    plan = _validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
        raise ValueError("Product continuation requires an authorized PR or merge-group run")
    consumer = _consumer(plan, environment)
    producer = _canonical_control(discovery_root / "producer.json", "Product producer")
    validate_producer(producer, "Product producer")
    if producer != consumer["producer"]:
        raise ValueError("Product producer does not match the current workflow run")

    request = _relocated_wave_control(discovery_root / "reuse-wave-request.json", "Reuse-wave request", root)
    requested = tuple(
        _identity(value)
        for value in require_array(request["requested"], "Reuse-wave request.requested")
    )
    if requested != tuple(sorted(set(requested))) or requested != _requested(plan):
        raise ValueError("Reuse-wave request does not match the current product selection")
    closure = _dependency_closure(requested)
    authorities, unavailable = _authorities(root, plan["validationCommit"], closure)
    if authorities is None:
        raise ValueError(unavailable or "Product phase authority is unavailable")
    initial_objects = []
    if request["availableObjects"]:
        supplied_objects = require_array(request["availableObjects"], "Initial availableObjects")
        supplied_ids = []
        for record in supplied_objects:
            require_exact_keys(record, set(_IDENTITY_KEYS) | {
                "buildKey", "receiptSha256", "objectSha256", "objectPath"}, "Initial availableObjects member")
            supplied_ids.append(_identity(record))
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        if tuple(supplied_ids) != _dependency_closure((contract,)):
            raise ValueError("Initial availableObjects must be the exact complete Contract closure")
        with tempfile.TemporaryDirectory(prefix="codex-agent-initial-contract-", dir=root) as temporary:
            verified = Path(temporary).resolve() / "verified"
            evidence = _capture_completed_contract_handoff(
                plan_path, discovery_root / "contract-state",
                discovery_root / "authenticated-contract/contract-input", verified,
                repository_root=root, environ=environment)
            if regular_file_inventory(verified) != regular_file_inventory(discovery_root / "authenticated-contract"):
                raise ValueError("Initial Contract evidence or public policy differs from tracked authority")
            expected_evidence = _rebase_contract_evidence_paths(
                evidence, discovery_root / "authenticated-contract", discovery_root)
            if request["contractEvidence"] != expected_evidence:
                raise ValueError("Initial Contract evidence paths do not identify the authenticated handoff")
        initial_objects, _ = _completed_contract_objects(
            plan, discovery_root / "contract-state", discovery_root, environment)
    expected_fixed = {
        "schemaVersion": 1,
        "requestType": "reuse-wave",
        "repository": plan["repository"],
        "pullRequest": plan["pullRequest"],
        "repositoryRoot": str(root),
        "repositoryRevision": plan["validationCommit"],
        "requested": [_identity_record(instance) for instance in requested],
        "versions": _versions(root, plan["validationCommit"]),
        "phaseAuthorities": authorities,
        "runtimeValidationEvidence": [],
        "availableObjects": initial_objects,
    }
    for field, expected in expected_fixed.items():
        if request[field] != expected:
            raise ValueError(f"Reuse-wave request disagrees with current {field}")
    if request["artifactRoot"] != str(root / "build/product-reuse"):
        raise ValueError("Reuse-wave request has an unexpected original artifact root")

    _verify_discovery_sdk_records(request, discovery_root)

    rebased_request = dict(request)
    rebased_request["artifactRoot"] = str(root)
    rebased_request["catalogs"] = _rebase_catalog_paths(request["catalogs"], discovery_root, root)
    rebased_request["contractEvidence"] = _rebase_contract_evidence_paths(
        request["contractEvidence"], discovery_root, root,
    )
    rebased_request["availableObjects"] = [{
        **record,
        "objectPath": (discovery_root / record["objectPath"]).relative_to(root).as_posix(),
    } for record in initial_objects]
    rebased_request.update(_rebase_native_request(request, discovery_root, root))

    replay_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
    replay = _plan_with_sdk_tooling(
        rebased_request, sdk_validation_tooling,
        build_plan_consumer=lambda instance, value: _retain_product_plan(replay_plans, instance, value),
    )
    initial = _canonical_control(discovery_root / "reuse-wave-result.json", "Initial reuse result")
    if replay != initial:
        raise ValueError("Initial reuse result is not reproducible from its authenticated request")

    prior = _canonical_control(state_root / "reuse-wave-result.json", "Reuse result")
    _, prior_materialized, _ = _validate_reuse_result(
        prior, requested, require_complete=False,
    )
    prior_by_instance = {_identity(phase): phase for phase in prior["phases"]}
    sources: dict[PhaseInstanceId, Path] = {}
    prior_carrier_phases: dict[PhaseInstanceId, dict[str, Any]] = {}
    carrier_name = "carrier" if prior["fullReuse"] else "reused-carrier"
    carrier_root = state_root / carrier_name
    if prior_materialized:
        carrier = verify_carrier(carrier_root, prior_materialized, consumer)
        prior_carrier_phases = {
            _identity(phase): phase for phase in carrier["resolution"]["phases"]
        }
        if any(
            any(prior_carrier_phases[instance][field] != prior_by_instance[instance][field]
                for field in (*_IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256"))
            for instance in prior_materialized
        ):
            raise ValueError("Prior product carrier disagrees with its reuse result")
        for record in carrier["objects"]:
            instance = _identity(record)
            sources[instance] = carrier_root / object_relative_path(
                record["buildKey"], record["receiptSha256"],
            )
    elif carrier_root.exists() or carrier_root.is_symlink():
        raise ValueError("Unexpected prior product carrier")

    prior_ready_plans = replay_plans
    if state_root != discovery_root:
        with tempfile.TemporaryDirectory(
            prefix="codex-agent-product-replay-", dir=root,
        ) as temporary:
            temporary_root = Path(temporary).resolve()
            phase_records = {
                instance: prior_by_instance[instance] for instance in sources
            }
            evidence = _materialize_runtime_validation_handoffs(
                closure, phase_records, sources,
                temporary_root / "runtime-validation-handoffs", root,
            )
            state_request = dict(rebased_request)
            state_request["availableObjects"] = _available_object_records(
                phase_records, sources, root,
            )
            state_request["runtimeValidationEvidence"] = evidence
            _merge_native_comparison_records(state_request, _retained_native_handoffs(state_root, root))
            _merge_native_comparison_records(state_request, _retained_native_handoffs(state_root, root, adapter=True),
                                             key=_ADAPTER_REQUEST_KEY)
            _merge_native_comparison_records(state_request, _retained_sdk_handoffs(state_root, root), key="sdkValidationEvidence")
            prior_ready_plans = {}
            state_replay = _plan_with_sdk_tooling(
                state_request, sdk_validation_tooling,
                build_plan_consumer=lambda instance, value: _retain_product_plan(
                    prior_ready_plans, instance, value,
                ),
            )
        state_by_instance = {_identity(phase): phase for phase in state_replay["phases"]}
        if any(state_by_instance[instance]["state"] != "retained" for instance in prior_materialized):
            raise ValueError("A prior carrier object was not retained by the recomputed plan")
        for instance in prior_materialized:
            state_by_instance[instance].update({
                key: prior_by_instance[instance][key]
                for key in ("state", "source", "transportSource", "misses")
            })
        if state_replay != prior:
            raise ValueError("Product reuse state is not reproducible from its verified carrier")

    return _VerifiedProductState(
        plan=plan,
        producer=producer,
        consumer=consumer,
        requested=requested,
        closure=closure,
        expected_fixed=expected_fixed,
        rebased_request=rebased_request,
        prior=prior,
        prior_by_instance=prior_by_instance,
        sources=sources,
        prior_carrier_phases=prior_carrier_phases,
        prior_ready_plans=prior_ready_plans,
    )


def inspect_products(
    plan_path: Path, discovery_root: Path, state_root: Path | None = None, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Re-elect ready plans before target setup without admitting new shards."""
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root = Path(os.path.abspath(discovery_root))
    state_root = discovery_root if state_root is None else Path(os.path.abspath(state_root))
    try:
        discovery_root.relative_to(root)
        state_root.relative_to(root)
    except ValueError as error:
        raise ValueError("Product inspection inputs must remain inside the repository") from error
    state = _verified_product_state(
        plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling)
    return {"result": state.prior,
            "readyPlans": [state.prior_ready_plans[instance] for instance in sorted(state.prior_ready_plans)]}


def _runtime_worker_instance(instance):
    return instance.product == "runtime" and instance.component != "runtime-aggregate"


def runtime_worker_matrix(
    plan_path: Path, discovery_root: Path, state_root: Path | None = None, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Route only authenticated ready standalone phases, never the cheap aggregate.

    These rows elect jobs, not observed hosts or permission to skip the worker's
    own replay, requested-key check, toolchain observation or supervisor proof.
    """
    inspected = inspect_products(
        plan_path, discovery_root, state_root, repository_root=repository_root,
        environ=environ, sdk_validation_tooling=sdk_validation_tooling)
    from runtime_adapter_phase import route as adapter_route
    from runtime_native_phase import route as native_route

    rows = []
    for plan in inspected["readyPlans"]:
        instance = _identity(plan)
        if not _runtime_worker_instance(instance):
            continue
        route = (native_route if instance.component in NATIVE_TARGETS else adapter_route)(plan)
        profile = required_toolchain_profile(instance)
        digest = require_sha256(plan["inputs"]["toolchainProfileDigest"], "Elected toolchain profile digest")
        if route["toolchainProfile"] != profile or (profile is None and digest != NOT_APPLICABLE_TOOLCHAIN_DIGEST):
            raise ValueError("Runtime worker route differs from its elected toolchain authority")
        rows.append({**_identity_record(instance), "buildKey": plan["buildKey"],
                     "toolchainProfileDigest": digest, **route})
    return {"include": rows}


def _product_materialization_paths(root, discovery_root, state_root, destination):
    discovery_root = Path(os.path.abspath(discovery_root))
    state_root = discovery_root if state_root is None else Path(os.path.abspath(state_root))
    destination = Path(os.path.abspath(destination))
    for source in (discovery_root, state_root):
        try:
            source.relative_to(root)
        except ValueError as error:
            raise ValueError("Product materialization inputs must remain inside the repository") from error
        # Check real file identities before creating anything, including case aliases.
        if any(parent.exists() and parent.samefile(source)
               for parent in (destination, *destination.parents)) or (
            destination.exists() and any(destination.samefile(parent)
                                         for parent in (source, *source.parents))
        ):
            raise ValueError("Product materialization destination overlaps original state")
    return discovery_root, state_root, destination


def _materialize_product_predecessors(state, instance, destination, expected_build_key, root):
    expected_build_key = require_sha256(expected_build_key, "Expected elected build key")
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError("Unknown product phase instance")
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Product phase is not ready with the expected elected build key")
    dependencies = tuple(dependency for dependency in _dependency_closure((instance,))
                         if dependency != instance)
    if any(dependency not in state.sources for dependency in dependencies):
        raise ValueError("Elected product phase lacks an authenticated original predecessor")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-inputs-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "inputs"
        prepared.mkdir()
        for dependency in dependencies:
            record = state.prior_carrier_phases[dependency]
            name = "-".join((dependency.product, dependency.component, dependency.phase, dependency.target))
            predecessor = prepared / name
            predecessor.mkdir()
            restored = restore_object(
                state.sources[dependency], predecessor / "stage",
                build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                object_sha256=record["objectSha256"],
            )
            (predecessor / "phase-receipt.json").write_bytes(restored["receiptBytes"])
        write_canonical_json(prepared / "phase-plan.json", ready)
        write_canonical_json(prepared / "producer.json", state.producer)
        publish_regular_tree(prepared, destination)
    return ready


def materialize_product_predecessors(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    instance: PhaseInstanceId, destination: Path, *, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Restore the full original closure, not new evidence or execution authority."""
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)
    state = _verified_product_state(
        plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling)
    return _materialize_product_predecessors(state, instance, destination, expected_build_key, root)


def prepare_runtime_phase(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    instance: PhaseInstanceId, destination: Path, *, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Prepare original worker inputs; never execute or grant hosted acceptance."""
    if instance not in PHASE_INSTANCE_IDS or instance.product != "runtime" or instance.component == "runtime-aggregate":
        raise ValueError("Unsupported Runtime worker phase")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)
    state = _verified_product_state(
        plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling)
    return _prepare_runtime_phase(state, instance, destination, expected_build_key, root)[0]


def _prepare_runtime_phase(state, instance, destination, expected_build_key, root):
    evidence = state.rebased_request["contractEvidence"]
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("Runtime worker requires authenticated release Contract evidence")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-worker-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "worker"
        prepared.mkdir()
        trust = _release_trust(root, state.plan["validationCommit"], prepared)
        if trust is None:
            raise ValueError("Runtime worker requires Git-authoritative release policy")
        inputs = prepared / "predecessors"
        ready = _materialize_product_predecessors(state, instance, inputs, expected_build_key, root)

        def original(product, component, phase, target):
            dependency = PhaseInstanceId(product, component, phase, target)
            if dependency == instance or dependency not in _dependency_closure((instance,)):
                raise ValueError("Runtime worker requested an unrelated predecessor")
            directory = inputs / "-".join((product, component, phase, target))
            receipt_path = directory / "phase-receipt.json"
            receipt = _canonical_control(receipt_path, "Original worker receipt")
            manifest = verify_output_manifest_identity(
                directory / "stage", product, component, phase, target, receipt["productVersion"])
            if manifest["outputs"] != receipt["outputs"]:
                raise ValueError("Runtime worker predecessor differs from its original receipt")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        def predecessor(component, phase, target):
            return original("runtime", component, phase, target)

        def one_output(value, kind):
            outputs = [record for record in value["receipt"]["outputs"] if record["kind"] == kind]
            if len(outputs) != 1:
                raise ValueError(f"Runtime worker requires one exact original {kind} output")
            return value["stage"] / outputs[0]["relativePath"]

        contract = original("contract", "contract", "metadata", "common")
        version = contract["receipt"]["productVersion"]
        stem = f"codex-agent-contract-{version}"
        handoff = prepared / "contract-input"
        handoff.mkdir()
        for source, name, limit in (
            (one_output(contract, "contract-bundle"), f"{stem}.zip", 512 * 1024 * 1024),
            (root / evidence["attestation"], f"{stem}.attestation.json", 16 * 1024 * 1024),
            (root / evidence["attestationSignature"], f"{stem}.attestation.sig", 1024 * 1024),
            (root / evidence["publicKey"], "public-key.pub", 1024 * 1024),
        ):
            (handoff / name).write_bytes(read_regular_file_bytes(
                source, max_bytes=limit, reject_symlink_parents=True))
        snapshot_regular_tree((root / evidence["attestation"]).parent / "execution-closure",
                              handoff / "execution-closure")
        for phase in ("binary", "package", "validation", "metadata"):
            retained = original("contract", "contract", phase, "common")["receiptPath"]
            if read_regular_file_bytes(retained) != read_regular_file_bytes(
                    handoff / f"execution-closure/receipts/{phase}.json"):
                raise ValueError("Runtime worker Contract closure rewrites an original receipt")
        manifest, _, _ = verify_contract_attestation(
            handoff / f"{stem}.zip", contract["receiptPath"],
            handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
            handoff / "public-key.pub", required_trust_domain="release",
            keyring=trust.keyring, keys_directory=trust.keys)
        properties = {
            **{f"codexAgent.{key}": value for key, value in _identity_record(instance).items()},
            "codexAgent.contractVersion": version,
            "codexAgent.runtimeVersion": state.expected_fixed["versions"]["runtime-release"],
            "codexAgent.candidateCommit": state.producer["commit"],
            "codexAgent.candidateTree": state.producer["tree"],
            "codexAgent.contractPayload": str(handoff / f"{stem}.zip"),
            "codexAgent.contractMetadataReceipt": str(contract["receiptPath"]),
            "codexAgent.contractAttestation": str(handoff / f"{stem}.attestation.json"),
            "codexAgent.contractAttestationSignature": str(handoff / f"{stem}.attestation.sig"),
            "codexAgent.contractPublicKey": str(handoff / "public-key.pub"),
        }
        if instance.component == "runtime-aggregate":
            specific = {}  # Aggregate imports all publication stages after closure collection.
        elif instance.component in NATIVE_TARGETS:
            from runtime_native_phase import properties as native_properties
            binary_plan_path = inputs / "phase-plan.json"
            if instance.phase == "binary":
                from products.contract_projection import verify_contract_component_projection
                from runtime_native_phase import binary_plan
                projection = verify_contract_component_projection(
                    contract["stage"], contract["receiptPath"],
                    handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
                    handoff / "public-key.pub", expected_trust_domain="release",
                    expected_contract_version=version, required_components=required_contract_components(instance),
                    keyring=trust.keyring, keys_directory=trust.keys)
                binary_plan_path = prepared / "runtime-binary-plan.json"
                write_canonical_json(binary_plan_path, binary_plan(
                    ready, repository_root=root, revision=state.producer["commit"],
                    contract_projection=projection, verified_contract_manifest=manifest,
                    runtime_version=state.expected_fixed["versions"]["runtime-release"]))

            def report(component, target):
                dependency = PhaseInstanceId("runtime", component, "validation", target)
                value = predecessor(component, "validation", target)
                return _runtime_report_output(instance, dependency, value["stage"], value["receipt"])

            specific = native_properties(
                ready, plan_path=binary_plan_path, revision=state.producer["commit"],
                predecessor=predecessor,
                output=lambda component, phase, target, kind: one_output(predecessor(component, phase, target), kind),
                report=report)
        else:
            from runtime_adapter_phase import properties as adapter_properties
            validation_handoff = None
            if instance.phase == "metadata":
                _materialize_runtime_validation_handoffs(
                    (instance,), state.prior_by_instance, state.sources,
                    prepared / "runtime-validation", root)
                validation_handoff = prepared / f"runtime-validation/{instance.component}-{instance.target}"
            specific = adapter_properties(ready, predecessor=predecessor, validation_handoff=validation_handoff)
        if properties.keys() & specific.keys():
            raise ValueError("Runtime family properties override common verified identity")
        properties.update(specific)
        properties = {
            key: str(destination / Path(value).relative_to(prepared))
            if value.startswith(str(prepared) + os.sep) else value
            for key, value in properties.items()
        }
        write_canonical_json(prepared / "gradle-properties.json", properties)
        publish_regular_tree(prepared, destination)
    return properties, manifest


def _runtime_worker_checkout(root, producer):
    if (_git_value(root, "rev-parse", "HEAD") != producer["commit"]
            or _git_value(root, "rev-parse", "HEAD^{tree}") != producer["tree"]
            or _git_value(root, "diff", "--name-only", "HEAD")):
        raise ValueError("Runtime worker requires the exact unchanged tracked checkout")
    untracked = _git_value(root, "ls-files", "--others", "--",
                          "runtime", "codex-agent-runtime-desktop", "ci", "gradle", "legal", "build-logic",
                          ":(glob)**/*.py", ":(glob)**/*.pyc", ":(glob)**/*.pyo",
                          "sitecustomize", "usercustomize", ":(glob)sitecustomize.*", ":(glob)usercustomize.*",
                          ":(exclude).codex/**", ":(exclude)**/build/**",
                          ":(exclude)**/.gradle/**", ":(exclude)**/__pycache__/**")
    if untracked:
        raise ValueError("Runtime worker rejects untracked source or build policy")


def _runtime_worker_command(wrapper, properties, environment):
    command = [str(wrapper), "--offline", "--no-daemon", "--configuration-cache",
               "--configuration-cache-problems=fail", "-p", "runtime", "ciProductPhase",
               *(f"-P{key}={value}" for key, value in sorted(properties.items()))]
    if os.name == "nt":
        java_home = environment.get("JAVA_HOME", "")
        if not ntpath.isabs(java_home):
            raise ValueError("Windows Runtime worker requires absolute JAVA_HOME")
        # Use the exact launcher used by gradlew.bat, without a command shell.
        command = [ntpath.join(java_home, "bin", "java.exe"), "-Xmx64m", "-Xms64m",
                   "-Dorg.gradle.appname=gradlew", "-jar",
                   ntpath.join(ntpath.dirname(str(wrapper)), "gradle", "wrapper", "gradle-wrapper.jar"),
                   *command[1:]]
    return command


def _runtime_worker_environment(root, producer, destination, environ):
    environment = dict(environ)
    _runtime_worker_checkout(root, producer)
    for name in environment:
        if (name.startswith("ORG_GRADLE_PROJECT_") or name in {
                "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JAVA_OPTS",
                "GRADLE_OPTS", "NODE_OPTIONS"}) and environment[name]:
            raise ValueError(f"Runtime worker rejects injected execution option: {name}")
    gradle_home = Path(environment.get("GRADLE_USER_HOME", str(Path.home() / ".gradle")))
    if not gradle_home.is_absolute():
        raise ValueError("Runtime worker Gradle user home must be absolute")
    for name in ("init.gradle", "init.gradle.kts", "init.d", "gradle.properties"):
        path = gradle_home / name
        if path.exists() or path.is_symlink():
            raise ValueError("Runtime worker rejects external Gradle initialization/properties")
    environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                        "PYTHONSAFEPATH": "1", "PYTHONPATH": str(root),
                        "PYTHONPYCACHEPREFIX": str(destination / "python-bytecode"),
                        "npm_config_offline": "true", "npm_config_audit": "false", "npm_config_fund": "false"})
    for name in ("PYTHONHOME", "PYTHONINSPECT", "PYTHONSTARTUP"):
        environment.pop(name, None)
    wrapper = root / ("gradlew.bat" if os.name == "nt" else "gradlew")
    if read_regular_file_bytes(wrapper, reject_symlink_parents=True) != git_regular_blob_bytes(
            root, producer["commit"], wrapper.name, max_bytes=64 * 1024):
        raise ValueError("Runtime worker wrapper differs from its exact Git source")
    if os.name == "nt":
        launcher = "gradle/wrapper/gradle-wrapper.jar"
        if read_regular_file_bytes(root / launcher, reject_symlink_parents=True) != git_regular_blob_bytes(
                root, producer["commit"], launcher, max_bytes=1024 * 1024):
            raise ValueError("Runtime worker launcher differs from its exact Git source")
    return environment, wrapper


def execute_runtime_supervisor(
    plan_path: Path, discovery_root: Path, state_root: Path | None, destination: Path, *,
    expected_build_key: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from native_wrappers import host_classifier
    from runtime_supervisor import execute_supervisor

    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime supervisor worker destination must not exist")
    environment = dict(os.environ if environ is None else environ)
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling)
    instance = PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Runtime supervisor is not ready with the expected elected build key")
    if host_classifier() != "linux-arm64":
        raise ValueError("Runtime supervisor requires the actual Linux ARM64 host")
    _runtime_worker_environment(root, state.producer, destination / "supervisor-diagnostics", environment)
    properties, manifest = _prepare_runtime_phase(state, instance, destination / "inputs", expected_build_key, root)
    full_plan = _canonical_control(Path(properties["codexAgent.runtimeBinaryPlan"]), "Prepared supervisor binary plan")
    if canonical_json_bytes({key: value for key, value in full_plan.items() if key != "runtimeBinaryIdentity"}) != canonical_json_bytes(ready):
        raise ValueError("Prepared supervisor plan differs from the original elected plan")
    return execute_supervisor(
        repository_root=root, producer=state.producer, properties=properties, phase_plan=full_plan,
        contract_manifest=manifest, runtime_version=state.expected_fixed["versions"]["runtime-release"],
        destination=destination / "supervisor", environ=environment)


def execute_runtime_phase(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    instance: PhaseInstanceId, destination: Path, *, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    supervisor_upload: Mapping[str, Any] | None = None,
    app_server_archive: Path | None = None,
) -> dict[str, Any]:
    """Execute the fixed phase, retaining diagnostics separately from its shard.

    No imported result, command or success callback can finalize a phase here.
    A failed process keeps inputs/logs for diagnosis and never creates a shard.
    """
    from native_wrappers import HOSTS, host_classifier
    from runtime_native_phase import route as native_route
    from runtime_adapter_phase import route as adapter_route, preflight as adapter_preflight

    if instance not in PHASE_INSTANCE_IDS or instance.product != "runtime" or instance.component == "runtime-aggregate":
        raise ValueError("Unsupported Runtime worker phase")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime execution destination must not exist")
    environment = dict(os.environ if environ is None else environ)
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling)
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Runtime worker is not ready with the expected elected build key")
    route = (native_route if instance.component in NATIVE_TARGETS else adapter_route)(ready)
    host = host_classifier()
    if HOSTS[host][2:4] != (route["runnerOs"], route["runnerArch"]):
        raise ValueError("Runtime worker actual host differs from its elected route")
    if route["supervisor"] is not None and supervisor_upload is None:
        raise ValueError("Linux Arm64 binary requires the independent authenticated supervisor handoff")
    if route["supervisor"] is None and supervisor_upload is not None:
        raise ValueError("Supervisor upload is only valid for Linux Arm64 binary production")
    needs_archive = instance.component in NATIVE_TARGETS and instance.phase == "binary"
    if needs_archive and app_server_archive is None:
        raise ValueError("Native binary requires a pinned app-server archive")
    if not needs_archive and app_server_archive is not None:
        raise ValueError("App-server archive is only valid for native binary production")
    environment, wrapper = _runtime_worker_environment(root, state.producer, destination, environment)
    stage = root / f"codex-agent-runtime-desktop/build/product-stage/runtime/{instance.component}/{instance.phase}"
    if instance.phase == "validation" and instance.component not in NATIVE_TARGETS:
        stage /= instance.target
    if stage == destination or stage in destination.parents or destination in stage.parents:
        raise ValueError("Runtime worker evidence and product stage must not overlap")
    if stage.exists() or stage.is_symlink():
        raise ValueError("Runtime worker refuses a pre-existing output stage")
    # Validate every existing parent without erasing any previous product bytes.
    _prepare_destination(stage, root).rmdir()
    observation = {} if instance.component in NATIVE_TARGETS else adapter_preflight(
        ready, repository_root=root, environ=environment)
    properties, manifest = _prepare_runtime_phase(state, instance, destination / "inputs", expected_build_key, root)
    if app_server_archive is not None:
        from runtime_native_phase import capture_archive
        properties["codexAgent.desktopArchiveDirectory"] = str(capture_archive(
            ready, repository_root=root, revision=state.producer["commit"],
            source=app_server_archive, destination=destination / "inputs/app-server-archive"))
    if supervisor_upload is not None:
        from runtime_supervisor import verify_supervisor_handoff
        upload = require_exact_keys(supervisor_upload, {"artifactId", "artifactSha256", "trustedWorkflowSha"},
                                    "Caller-bound supervisor upload")
        captured = destination / "inputs/supervisor-upload"
        transport = capture_runtime_supervisor_upload(
            plan_path, captured, artifact_id=upload["artifactId"], artifact_sha256=upload["artifactSha256"],
            expected_build_key=ready["buildKey"], trusted_workflow_sha=upload["trustedWorkflowSha"],
            repository_root=root, environ=environment, token=environment.get("GITHUB_TOKEN", ""))
        if canonical_json_bytes(transport["captureProducer"]) != canonical_json_bytes(state.producer):
            raise ValueError("Supervisor transport differs from the current elected producer")
        full_plan = _canonical_control(Path(properties["codexAgent.runtimeBinaryPlan"]), "Prepared binary plan")
        if canonical_json_bytes({key: value for key, value in full_plan.items() if key != "runtimeBinaryIdentity"}) != canonical_json_bytes(ready):
            raise ValueError("Prepared binary plan differs from the original elected plan")
        verify_supervisor_handoff(
            captured / "original", repository_root=root, revision=state.producer["commit"],
            phase_plan=full_plan, contract_manifest=manifest, producer=state.producer,
            runtime_version=state.expected_fixed["versions"]["runtime-release"])
        properties["codexAgent.desktopSupervisorDirectory"] = str(captured / "original")
    input_inventory = regular_file_inventory(destination / "inputs", allow_empty=True)
    _runtime_worker_checkout(root, state.producer)
    if stage.exists() or stage.is_symlink():
        raise ValueError("Runtime worker output stage appeared before execution")
    command = _runtime_worker_command(wrapper, properties, environment)
    started = time.monotonic_ns()
    with (destination / "gradle.log").open("xb") as log:
        completed = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    write_canonical_json(destination / "execution.json", {
        "schemaVersion": 1, "producer": state.producer, "buildKey": ready["buildKey"],
        "command": command, "host": host, "observations": observation,
        "returnCode": completed.returncode, "elapsedNs": time.monotonic_ns() - started,
    })
    if completed.returncode != 0:
        raise ValueError(f"Runtime phase failed with exit code {completed.returncode}; see {destination / 'gradle.log'}")
    _runtime_worker_checkout(root, state.producer)
    if (destination / "python-bytecode").exists() or (destination / "python-bytecode").is_symlink():
        raise ValueError("Runtime worker private Python bytecode namespace was modified")
    if input_inventory != regular_file_inventory(destination / "inputs", allow_empty=True):
        raise ValueError("Runtime worker inputs changed during execution")
    return finalize_phase_object(
        stage_root=stage, phase_plan=ready, producer=state.producer,
        product_version=state.expected_fixed["versions"]["runtime-release"],
        trust_domain="development" if state.plan["event"] == "pull_request" else "release",
        destination=destination / "shard")


def execute_runtime_aggregate(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    destination: Path, *, expected_build_key: str, variant_trust_root: Path,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce deterministic metadata from originals; never sign or rebuild inputs."""
    from runtime_aggregate_phase import collect_inputs, collect_maven_outputs
    from products.runtime_aggregate import produce_runtime_aggregate
    from products.receipt import write_output_manifest

    instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    # The caller's detached evidence is an original input too, not writable output.
    _product_materialization_paths(root, variant_trust_root, variant_trust_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime aggregate destination must not exist")
    environment = dict(os.environ if environ is None else environ)
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling)
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Runtime aggregate is not ready with the expected elected build key")
    _runtime_worker_checkout(root, state.producer)
    properties, _ = _prepare_runtime_phase(state, instance, destination / "inputs", expected_build_key, root)
    inputs = destination / "inputs"

    def predecessor(component, phase, target):
        directory = inputs / "predecessors" / f"runtime-{component}-{phase}-{target}"
        receipt_path = directory / "phase-receipt.json"
        return {"stage": directory / "stage", "receiptPath": receipt_path,
                "receipt": _canonical_control(receipt_path, "Original aggregate predecessor")}

    trust_root = inputs / "variant-trust"
    snapshot_regular_tree(variant_trust_root, trust_root)
    before = regular_file_inventory(inputs, allow_empty=True)
    records = collect_inputs(ready, predecessor)
    if before != regular_file_inventory(inputs, allow_empty=True):
        raise ValueError("Runtime aggregate original inputs changed during translation")
    expected = set()
    detached = {name: {} for name in ("variant_attestations", "variant_attestation_signatures", "variant_public_keys")}
    for target, bundle in records["variant_bundles"].items():
        for field, filename in (("variant_attestations", f"{bundle.stem}.attestation.json"),
                                ("variant_attestation_signatures", f"{bundle.stem}.attestation.sig"),
                                ("variant_public_keys", "public-key.pub")):
            relative = f"{target}/{filename}"
            expected.add(relative)
            detached[field][target] = trust_root / relative
    if {record["relativePath"] for record in regular_file_inventory(trust_root)} != expected:
        raise ValueError("Runtime aggregate requires exactly five detached variant trust closures")
    trust = _release_trust(root, state.producer["commit"], destination / "release-policy")
    if trust is None:
        raise ValueError("Runtime aggregate requires Git-authoritative release policy")
    policy_before = regular_file_inventory(destination / "release-policy")
    contract = {name: Path(properties[f"codexAgent.{property_name}"]) for name, property_name in (
        ("contract_payload", "contractPayload"), ("contract_metadata_receipt", "contractMetadataReceipt"),
        ("contract_attestation", "contractAttestation"), ("contract_attestation_signature", "contractAttestationSignature"),
        ("contract_public_key", "contractPublicKey"))}
    stage = root / "codex-agent-runtime-desktop/build/product-stage/runtime/runtime-aggregate/metadata"
    if stage == destination or stage in destination.parents or destination in stage.parents:
        raise ValueError("Runtime aggregate stage overlaps its original inputs/diagnostics")
    if stage.exists() or stage.is_symlink():
        raise ValueError("Runtime aggregate refuses a pre-existing output stage")
    _prepare_destination(stage, root).rmdir()
    version = state.expected_fixed["versions"]["runtime-release"]
    for component, original in records.pop("publication_inputs").items():
        properties[f"codexAgent.runtimeMavenStage.{component}"] = str(original["stage"])
        properties[f"codexAgent.runtimeMavenVersion.{component}"] = original["version"]
    environment, wrapper = _runtime_worker_environment(root, state.producer, destination, environment)
    command = _runtime_worker_command(wrapper, properties, environment)
    started = time.monotonic_ns()
    with (destination / "gradle.log").open("xb") as log:
        completed = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False)
    write_canonical_json(destination / "execution.json", {
        "schemaVersion": 1, "producer": state.producer, "buildKey": ready["buildKey"],
        "command": command, "returnCode": completed.returncode,
        "elapsedNs": time.monotonic_ns() - started,
    })
    if completed.returncode != 0:
        raise ValueError(f"Runtime aggregate Maven publication failed with exit code {completed.returncode}; see gradle.log")
    _runtime_worker_checkout(root, state.producer)
    if (destination / "python-bytecode").exists() or (destination / "python-bytecode").is_symlink():
        raise ValueError("Runtime aggregate private Python bytecode namespace was modified")
    if policy_before != regular_file_inventory(destination / "release-policy"):
        raise ValueError("Runtime aggregate release policy changed during Maven publication")
    if before != regular_file_inventory(inputs, allow_empty=True):
        raise ValueError("Runtime aggregate original inputs changed during Maven publication")
    records["runtime_maven_files"], verified_maven_outputs = collect_maven_outputs(
        stage, version, properties["codexAgent.contractVersion"], predecessor)
    produced = produce_runtime_aggregate(
        runtime_version=version, **contract, **detached,
        **{name: value for name, value in records.items() if name not in {"adapter_receipts", "adapter_report_files"}},
        required_trust_domain="release", output_directory=stage / "outputs",
        contract_keyring=trust.keyring, contract_keys_directory=trust.keys,
        variant_keyring=trust.keyring, variant_keys_directory=trust.keys)
    _runtime_worker_checkout(root, state.producer)
    if before != regular_file_inventory(inputs, allow_empty=True):
        raise ValueError("Runtime aggregate original inputs changed during production")
    if policy_before != regular_file_inventory(destination / "release-policy"):
        raise ValueError("Runtime aggregate release policy changed during production")
    manifest_bytes = canonical_json_bytes(produced["manifest"])
    expected_outputs = sorted([*verified_maven_outputs, {
        "kind": "runtime-aggregate", "relativePath": f"outputs/codex-agent-runtime-{version}-manifest.json",
        "bytes": len(manifest_bytes), "sha256": sha256_bytes(manifest_bytes),
    }], key=lambda record: record["relativePath"])
    if sorted([{"kind": "maven", "relativePath": f"outputs/{record['path']}",
                "bytes": record["bytes"], "sha256": record["sha256"]}
               for record in produced["manifest"]["runtimeMavenFiles"]],
              key=lambda record: record["relativePath"]) != verified_maven_outputs:
        raise ValueError("Runtime aggregate Maven manifest changed after original-primary verification")
    final_manifest = write_output_manifest(stage, "runtime", "runtime-aggregate", "metadata", "aggregate", version,
                          {"runtime-aggregate": f"outputs/codex-agent-runtime-{version}-manifest.json",
                           "maven": "outputs/maven"})
    if final_manifest["outputs"] != expected_outputs:
        raise ValueError("Runtime aggregate staged bytes changed after original-primary verification")
    return finalize_phase_object(
        stage_root=stage, phase_plan=ready, producer=state.producer, product_version=version,
        trust_domain="development" if state.plan["event"] == "pull_request" else "release",
        destination=destination / "shard")


def collect_runtime_workers(
    plan_path: Path, discovery_root: Path, state_root: Path | None, destination: Path, *,
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect every elected Runtime row; failed siblings cannot erase originals.

    This external report is not receipt authority. advance_products verifies
    successful original shards again and enforces its exact elected partition.
    """
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime collection destination must not exist")
    environment = os.environ if environ is None else environ
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling)
    producer = state.producer
    selected = [(instance, ready) for instance, ready in sorted(state.prior_ready_plans.items())
                if _runtime_worker_instance(instance)]
    observed, artifacts, jobs = [], [], []
    if selected:
        observed = _observe_ci_producer_jobs(
            {"resume": producer}, jobs_by_phase={"resume": "product-validation / product-resume"},
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        jobs = observed[0]["jobs"]
        artifacts = paginated_items(
            f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{producer['runId']}/artifacts",
            "artifacts", token)
    for instance, _ready in selected:
        name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
        if any(job.get("name") == name and job.get("status") != "completed" for job in jobs):
            raise ValueError("An elected Runtime worker is still running; collect after all siblings finish")
    _prepare_destination(destination, root).rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-collection-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "collection"
        prepared.mkdir()
        rows = []
        for instance, ready in selected:
            name = f"{instance.component}-{instance.phase}-{instance.target}"
            job_name = f"product-validation / runtime-{name}"
            artifact_name = (f"codex-agent-runtime-worker-{name}-{ready['buildKey'].removeprefix('sha256:')}-"
                             f"{producer['tree']}-attempt-{producer['runAttempt']}")
            row = {**_identity_record(instance), "buildKey": ready["buildKey"],
                   "jobName": job_name, "artifactName": artifact_name, "result": "failure", "reason": None,
                   "artifact": None, "originalDirectory": None, "shardDirectory": None}
            rows.append(row)
            try:
                matching_jobs = [job for job in jobs if job.get("name") == job_name]
                if len(matching_jobs) != 1:
                    raise ValueError("Runtime worker job is missing or ambiguous")
                job = matching_jobs[0]
                require_integer(job.get("id"), "Runtime worker job ID", 1)
                if (require_integer(job.get("run_id"), "Runtime worker job run", 1) != producer["runId"]
                        or job.get("head_sha") != observed[0]["run"]["head_sha"]):
                    raise ValueError("Runtime worker job differs from the original producer")
                candidates = [item for item in artifacts if isinstance(item, dict) and item.get("name") == artifact_name]
                if len(candidates) != 1:
                    raise ValueError("Runtime worker upload is missing or ambiguous")
                candidate = candidates[0]
                artifact, raw = _download_contract_ci_upload(
                    candidate.get("id"), candidate.get("digest"), artifact_name, producer, observed[0]["run"], token)
                timestamps = [datetime.fromisoformat(require_string(value, "Runtime worker timestamp").replace("Z", "+00:00"))
                              for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
                if (any(value.utcoffset() != timedelta(0) for value in timestamps)
                        or not timestamps[0] <= timestamps[1] <= timestamps[2]):
                    raise ValueError("Runtime upload is outside its original job-attempt window")
                row["artifact"] = artifact
                retained = prepared / "rows" / name
                retained.mkdir(parents=True)
                archive = retained / "transport.zip"
                archive.write_bytes(raw)
                verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                original = retained / "original"
                safe_extract(archive, original)
                row["originalDirectory"] = original.relative_to(prepared).as_posix()
                if job.get("conclusion") != "success":
                    raise ValueError("Runtime worker job did not succeed; original diagnostics retained")
                verified = verify_phase_shard(original / "shard", instance)
                receipt = verified["receipt"]
                if (receipt["producer"] != producer or receipt["buildKey"] != ready["buildKey"]
                        or receipt["productVersion"] != state.expected_fixed["versions"]["runtime-release"]
                        or receipt["trustDomain"] != ("development" if state.plan["event"] == "pull_request" else "release")):
                    raise ValueError("Runtime worker shard differs from its elected plan and producer")
                row.update(result="success", reason="verified-original-shard",
                           shardDirectory=(original / "shard").relative_to(prepared).as_posix())
            except (ValueError, OSError) as error:
                row["reason"] = str(error)
        result = {"schemaVersion": 1, "producer": producer, "observed": observed, "rows": rows}
        write_canonical_json(prepared / "collection.json", result)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return result


def advance_products(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    shard_roots: list[Path], destination: Path,
    github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    native_evidence_roots: tuple[Path, ...] = (),
    adapter_evidence_roots: tuple[Path, ...] = (),
    sdk_evidence_roots: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    failed_instances: tuple[PhaseInstanceId, ...] = (),
    runtime_workers_only: bool = False,
) -> dict[str, Any]:
    github_output(github_output_path, {
        "full_reuse": False,
        "target_jobs_required": True,
        "product_reuse_reason": "not-evaluated",
        "runtime_evidence_required": False,
        "wave_failed": True,
    })
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    discovery_root = Path(os.path.abspath(discovery_root))
    state_root = discovery_root if state_root is None else Path(os.path.abspath(state_root))
    shard_roots = [Path(os.path.abspath(path)) for path in shard_roots]
    try:
        discovery_root.relative_to(root)
        state_root.relative_to(root)
        for shard_root in shard_roots:
            shard_root.relative_to(root)
    except ValueError as error:
        raise ValueError("Product continuation inputs must remain inside the repository") from error

    state = _verified_product_state(
        plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling)
    plan = state.plan
    producer = state.producer
    consumer = state.consumer
    requested = state.requested
    closure = state.closure
    expected_fixed = state.expected_fixed
    rebased_request = state.rebased_request
    prior = state.prior
    prior_by_instance = state.prior_by_instance
    sources = state.sources
    prior_carrier_phases = state.prior_carrier_phases
    prior_ready_plans = state.prior_ready_plans

    expected_builds = {
        _identity(phase): phase for phase in prior["phases"] if phase["state"] == "build"
    }
    if type(runtime_workers_only) is not bool:
        raise ValueError("Runtime worker collection scope must be boolean")
    if runtime_workers_only:
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if _runtime_worker_instance(instance)}
    if (any(type(instance) is not PhaseInstanceId for instance in failed_instances)
            or len(set(failed_instances)) != len(failed_instances)
            or not set(failed_instances) <= set(expected_builds)):
        raise ValueError("Failed phase identities must be distinct elected build phases")
    failed = set(failed_instances)
    shards = {}
    for shard_root in shard_roots:
        descriptor = require_exact_keys(
            _canonical_control(shard_root / PHASE_SHARD_NAME, "Product phase shard"),
            PHASE_SHARD_KEYS,
            "Product phase shard",
        )
        instance = _identity(descriptor)
        if instance in shards:
            raise ValueError(f"Duplicate product phase shard: {instance}")
        if instance not in expected_builds:
            raise ValueError(f"Unexpected product phase shard: {instance}")
        verified = verify_phase_shard(shard_root, instance)
        receipt = verified["receipt"]
        expected_version = expected_fixed["versions"][
            "runtime-release" if instance.product == "runtime" else instance.product
        ]
        if (
            receipt["producer"] != producer
            or receipt["trustDomain"] != (
                "development" if plan["event"] == "pull_request" else "release"
            )
            or receipt["productVersion"] != expected_version
            or receipt["buildKey"] != expected_builds[instance]["buildKey"]
            or prior_ready_plans.get(instance, {}).get("buildKey") != receipt["buildKey"]
        ):
            raise ValueError("Product phase shard does not match its elected plan and producer")
        shards[instance] = {
            **verified,
            "transportSource": {
                "kind": "phase-shard",
                "descriptorSha256": sha256_bytes(canonical_json_bytes(descriptor)),
                "producer": producer,
            },
        }
        sources[instance] = shard_root / verified["objectPath"]
    if set(shards) & failed or set(shards) | failed != set(expected_builds):
        raise ValueError("Product phase shards and failures do not exactly partition the elected build wave")

    phase_records = {
        instance: (
            shards[instance] if instance in shards else prior_by_instance[instance]
        )
        for instance in sources
    }
    with tempfile.TemporaryDirectory(
        prefix="codex-agent-product-advance-", dir=root,
    ) as temporary:
        temporary_root = Path(temporary).resolve()
        evidence = _materialize_runtime_validation_handoffs(
            closure, phase_records, sources,
            temporary_root / "runtime-validation-handoffs", root,
        )
        advanced_request = dict(rebased_request)
        advanced_request["availableObjects"] = _available_object_records(
            phase_records, sources, root,
        )
        advanced_request["runtimeValidationEvidence"] = evidence
        native_destination = temporary_root / "result/native-runtime-evidence"
        prior_native = state_root / "native-runtime-evidence"
        if prior_native.exists():
            snapshot_regular_tree(prior_native, native_destination)
        offset = len(list(native_destination.iterdir())) if native_destination.exists() else 0
        native_trust = _release_trust(root, plan["validationCommit"], temporary_root) if native_evidence_roots else None
        for index, source in enumerate(native_evidence_roots, offset):
            target = native_destination / str(index)
            stage_native_runtime_evidence(load_native_runtime_evidence(source), source, target,
                    keyring=native_trust.keyring if native_trust else None,
                    keys_directory=native_trust.keys if native_trust else None)
        retained_native = _retained_native_handoffs(temporary_root / "result", root)
        _merge_native_comparison_records(advanced_request, retained_native)
        adapter_destination = temporary_root / "result/adapter-runtime-evidence"
        prior_adapter = state_root / "adapter-runtime-evidence"
        if prior_adapter.exists():
            snapshot_regular_tree(prior_adapter, adapter_destination)
        adapter_offset = len(list(adapter_destination.iterdir())) if adapter_destination.exists() else 0
        adapter_trust = _release_trust(root, plan["validationCommit"], temporary_root / "adapter-trust") if adapter_evidence_roots else None
        for index, source in enumerate(adapter_evidence_roots, adapter_offset):
            stage_adapter_runtime_evidence(load_adapter_runtime_evidence(source), source, adapter_destination / str(index),
                keyring=adapter_trust.keyring if adapter_trust else None,
                keys_directory=adapter_trust.keys if adapter_trust else None)
        retained_adapter = _retained_native_handoffs(temporary_root / "result", root, adapter=True)
        _merge_native_comparison_records(advanced_request, retained_adapter, key=_ADAPTER_REQUEST_KEY)
        sdk_destination = temporary_root / "result/sdk-validation-evidence"
        prior_sdk = state_root / "sdk-validation-evidence"
        if prior_sdk.exists():
            snapshot_regular_tree(prior_sdk, sdk_destination)
        sdk_offset = len(list(sdk_destination.iterdir())) if sdk_destination.exists() else 0
        for index, source in enumerate(sdk_evidence_roots, sdk_offset):
            stage_sdk_validation_evidence(load_sdk_validation_evidence(source), source, sdk_destination / str(index),
                repository=root, policy_revision=plan["validationCommit"], tooling=sdk_validation_tooling)
        retained_sdk = _retained_sdk_handoffs(temporary_root / "result", root)
        _merge_native_comparison_records(advanced_request, retained_sdk, key="sdkValidationEvidence")
        ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
        advanced = _plan_with_sdk_tooling(
            advanced_request, sdk_validation_tooling,
            build_plan_consumer=lambda instance, value: _retain_product_plan(ready_plans, instance, value),
        )
        supplied = set(sources)
        advanced_by_instance = {_identity(phase): phase for phase in advanced["phases"]}
        if any(advanced_by_instance[instance]["state"] != "retained" for instance in supplied):
            raise ValueError("A supplied product object was not retained by the recomputed plan")
        advanced, selected, selected_phases = _validate_reuse_result(
            advanced, requested, require_complete=False,
        )
        remote_sources = _catalog_object_sources(rebased_request)
        for instance, phase in zip(selected, selected_phases, strict=True):
            if instance in sources:
                continue
            transport = phase["transportSource"]
            key = (phase["source"], transport["indexSha256"], phase["buildKey"])
            try:
                sources[instance] = remote_sources[key]
            except KeyError as error:
                raise ValueError("Advanced product reuse lacks its authenticated object") from error

        carrier_phases = []
        for instance, phase in zip(selected, selected_phases, strict=True):
            if instance in shards:
                carrier_phases.append({
                    **phase,
                    "state": "reused",
                    "source": "phase-shard",
                    "transportSource": shards[instance]["transportSource"],
                    "misses": prior_by_instance[instance]["misses"],
                })
            elif instance in prior_carrier_phases:
                carrier_phases.append(prior_carrier_phases[instance])
            else:
                carrier_phases.append(phase)
        normalized = {
            "schemaVersion": 1,
            "result": "complete",
            "fullReuse": True,
            "phases": carrier_phases,
            "matrices": {"contract": [], "runtime": [], "sdk": []},
        }
        final_carrier_name = "carrier" if advanced["fullReuse"] else "reused-carrier"
        staged_destination = temporary_root / "result"
        staged_destination.mkdir(exist_ok=True)
        if selected:
            write_carrier(
                staged_destination / final_carrier_name,
                normalized,
                selected,
                sources,
                consumer,
            )
        staged_evidence = _materialize_runtime_validation_handoffs(
            closure,
            {instance: phase for instance, phase in zip(selected, selected_phases, strict=True)},
            sources,
            staged_destination / "runtime-validation-handoffs",
            staged_destination,
        )
        staged_prefix = staged_destination.relative_to(root).as_posix()
        staged_request = dict(rebased_request)
        _merge_native_comparison_records(staged_request, retained_native)
        _merge_native_comparison_records(staged_request, retained_adapter, key=_ADAPTER_REQUEST_KEY)
        _merge_native_comparison_records(staged_request, retained_sdk, key="sdkValidationEvidence")
        staged_request["runtimeValidationEvidence"] = [{
            **record,
            "reports": [f"{staged_prefix}/{path}" for path in record["reports"]],
        } for record in staged_evidence]
        staged_request["availableObjects"] = [{
            **_identity_record(instance),
            "buildKey": phase["buildKey"],
            "receiptSha256": phase["receiptSha256"],
            "objectSha256": phase["objectSha256"],
            "objectPath": (
                f"{staged_prefix}/{final_carrier_name}/"
                f"{object_relative_path(phase['buildKey'], phase['receiptSha256'])}"
            ),
        } for instance, phase in zip(selected, selected_phases, strict=True)]
        staged_replay = _plan_with_sdk_tooling(staged_request, sdk_validation_tooling)
        staged_by_instance = {_identity(phase): phase for phase in staged_replay["phases"]}
        for instance in selected:
            staged_by_instance[instance].update({
                key: advanced_by_instance[instance][key]
                for key in ("state", "source", "transportSource", "misses")
            })
        if staged_replay != advanced:
            raise ValueError("Staged product continuation is not reproducible")

        destination_prefix = destination.relative_to(root).as_posix()
        final_request = dict(staged_request)
        if {"nativeRuntimeComparisonEvidence", _ADAPTER_REQUEST_KEY, "sdkValidationEvidence"} & final_request.keys():
            # Move only paths inside this staged transport. Original discovery
            # catalogs remain at their separately retained discovery paths.
            def relocated_native(value):
                if isinstance(value, dict):
                    return {key: relocated_native(member) for key, member in value.items()}
                if isinstance(value, list):
                    return [relocated_native(member) for member in value]
                if isinstance(value, str) and value.startswith(staged_prefix + "/"):
                    return destination_prefix + value[len(staged_prefix):]
                return value
            for key in ("nativeRuntimeComparisonEvidence", _ADAPTER_REQUEST_KEY, "sdkValidationEvidence"):
                if key in final_request:
                    final_request[key] = relocated_native(final_request[key])
        final_request["runtimeValidationEvidence"] = [{
            **record,
            "reports": [
                path.replace(f"{staged_prefix}/", f"{destination_prefix}/", 1)
                for path in record["reports"]
            ],
        } for record in staged_request["runtimeValidationEvidence"]]
        final_request["availableObjects"] = [{
            **record,
            "objectPath": record["objectPath"].replace(
                f"{staged_prefix}/", f"{destination_prefix}/", 1,
            ),
        } for record in staged_request["availableObjects"]]
        write_canonical_json(staged_destination / "reuse-wave-request.json", final_request)
        write_canonical_json(staged_destination / "reuse-wave-result.json", advanced)
        if failed:
            # Caller-reported failures are diagnostics, never success evidence or
            # a replacement for an original phase receipt. Replay ignores them.
            write_canonical_json(staged_destination / "wave-failures.json", {
                "schemaVersion": 1, "producer": producer,
                "failedPhases": [{**_identity_record(instance),
                                  "buildKey": expected_builds[instance]["buildKey"]}
                                 for instance in sorted(failed)],
            })
        _write_ready_plans(staged_destination, ready_plans)
        if ready_plans:
            write_canonical_json(staged_destination / "producer.json", producer)
        publish_regular_tree(staged_destination, destination)
    github_output(github_output_path, {
        "full_reuse": advanced["fullReuse"],
        "target_jobs_required": not advanced["fullReuse"],
        "product_reuse_reason": (
            "verified-full-reuse" if advanced["fullReuse"] else "product-build-required"
        ),
        "runtime_evidence_required": bool(advanced["continuationRequirements"]),
        "wave_failed": bool(failed),
    })
    return advanced


def materialize_contract(
    plan_path: Path, state_root: Path, phase: str, destination: Path, *,
    with_receipt: bool = False,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if phase not in {"binary", "package", "validation", "metadata"}:
        raise ValueError("Contract materialization phase is unsupported")
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    state_root = Path(os.path.abspath(state_root))
    try:
        state_root.relative_to(root)
    except ValueError as error:
        raise ValueError("Contract materialization state must remain inside the repository") from error
    plan = _validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
        raise ValueError("Contract materialization requires an authorized PR or merge-group run")
    consumer = _consumer(plan, os.environ if environ is None else environ)
    producer = _canonical_control(state_root / "producer.json", "Contract producer")
    validate_producer(producer, "Contract producer")
    if producer != consumer["producer"]:
        raise ValueError("Contract producer does not match the current workflow run")
    result = _canonical_control(
        state_root / "contract-reuse-result.json", "Contract reuse result",
    )
    contract = PhaseInstanceId("contract", "contract", "metadata", "common")
    _, materialized, _ = _validate_reuse_result(result, (contract,), require_complete=False)
    requested = PhaseInstanceId("contract", "contract", phase, "common")
    if requested not in materialized:
        raise ValueError("Requested Contract phase is not materialized in the current state")
    carrier_name = "carrier" if result["fullReuse"] else "reused-carrier"
    carrier_root = state_root / carrier_name
    carrier = verify_carrier(carrier_root, materialized, consumer)
    result_by_instance = {_identity(value): value for value in result["phases"]}
    carrier_by_instance = {_identity(value): value for value in carrier["objects"]}
    if any(
        any(carrier_by_instance[instance][field] != result_by_instance[instance][field]
            for field in (*_IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256"))
        for instance in materialized
    ):
        raise ValueError("Contract materialization carrier disagrees with its reuse result")
    record = next(value for value in carrier["objects"] if _identity(value) == requested)
    object_path = carrier_root / object_relative_path(
        record["buildKey"], record["receiptSha256"],
    )
    if not with_receipt:
        return restore_object(
            object_path,
            destination,
            build_key=record["buildKey"],
            receipt_sha256=record["receiptSha256"],
            object_sha256=record["objectSha256"],
        )
    with tempfile.TemporaryDirectory(
        prefix="codex-agent-contract-handoff-", dir=root,
    ) as temporary:
        prepared = Path(temporary).resolve() / "handoff"
        prepared.mkdir()
        restored = restore_object(
            object_path,
            prepared / "stage",
            build_key=record["buildKey"],
            receipt_sha256=record["receiptSha256"],
            object_sha256=record["objectSha256"],
        )
        receipt = prepared / "receipt"
        receipt.mkdir()
        (receipt / "phase-receipt.json").write_bytes(restored["receiptBytes"])
        publish_regular_tree(prepared, destination)
        return restored


def capture_runtime_supervisor_upload(
    plan_path: Path, destination: Path, *, artifact_id: int, artifact_sha256: str,
    expected_build_key: str, trusted_workflow_sha: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    token: str,
) -> dict[str, Any]:
    """Capture the fixed producer job's upload, not a caller-authored success claim.

    Caller-owned job outputs supply ID/digest/key. This transport evidence alone
    cannot admit a supervisor: the worker must independently verify its complete
    content against the authenticated elected binary plan before using it.
    """
    require_integer(artifact_id, "Runtime supervisor artifact ID", 1)
    require_sha256(artifact_sha256, "Runtime supervisor artifact digest")
    require_sha256(expected_build_key, "Runtime supervisor elected build key")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    plan = _validate_plan(plan_path, root)
    if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
        raise ValueError("Runtime supervisor capture requires an authorized PR or merge-group run")
    producer = _consumer(plan, os.environ if environ is None else environ)["producer"]
    if Path(destination).exists() or Path(destination).is_symlink():
        raise ValueError("Runtime supervisor capture destination must not exist")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    observed = _observe_ci_producer_jobs(
        {"supervisor": producer},
        jobs_by_phase={"supervisor": "product-validation / runtime-linux-arm64-supervisor"},
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    artifact, raw = _download_contract_ci_upload(
        artifact_id, artifact_sha256,
        f"codex-agent-runtime-supervisor-linux-arm64-{expected_build_key.removeprefix('sha256:')}-{producer['tree']}",
        producer, observed[0]["run"], token)
    with tempfile.TemporaryDirectory(prefix="codex-agent-supervisor-capture-", dir=root) as temporary:
        private = Path(temporary).resolve()
        archive = private / "transport.zip"
        archive.write_bytes(raw)
        verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        prepared = private / "captured"
        safe_extract(archive, prepared / "original")
        evidence = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                    "buildKey": expected_build_key}
        write_canonical_json(prepared / "capture-transport.json", evidence)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return evidence


def capture_runtime_resume_upload(
    plan_path: Path, destination: Path, *, artifact_id: int, artifact_sha256: str,
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str, state_wave: int = 0,
) -> dict[str, Any]:
    """Retain the exact resumed upload; full product replay grants admission."""
    require_integer(artifact_id, "Runtime resume artifact ID", 1)
    if type(state_wave) is not int or not 0 <= state_wave <= 4:
        raise ValueError("Runtime state wave must be an integer from zero through four")
    require_sha256(artifact_sha256, "Runtime resume artifact digest")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime resume capture destination must not exist")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-resume-", dir=root) as temporary:
        private = Path(temporary).resolve()
        plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("Runtime resume capture requires an authorized PR or merge-group run")
        producer = _consumer(plan, os.environ if environ is None else environ)["producer"]
        job_name = "product-validation / product-resume" if state_wave == 0 else f"product-validation / runtime-collect-{state_wave}"
        artifact_name = (f"codex-agent-product-resume-{producer['tree']}" if state_wave == 0 else
                         f"codex-agent-runtime-wave-{state_wave}-state-{producer['tree']}-attempt-{producer['runAttempt']}")
        observed = _observe_ci_producer_jobs(
            {"resume": producer}, jobs_by_phase={"resume": job_name},
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        artifact, raw = _download_contract_ci_upload(
            artifact_id, artifact_sha256, artifact_name,
            producer, observed[0]["run"], token)
        archive = private / "transport.zip"
        archive.write_bytes(raw)
        verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        prepared = private / "captured"
        original = prepared / "original"
        safe_extract(archive, original)
        expected_roots = {"product-resume-inputs", "product-resume-state"} | ({"runtime-state"} if state_wave else set())
        if ({member.name for member in original.iterdir()} != expected_roots
                or any(not member.is_dir() for member in original.iterdir())):
            raise ValueError("Runtime resume upload requires its exact original directories")
        if read_regular_file_bytes(original / "product-resume-inputs/plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Runtime resume upload plan differs from the validated original plan")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed}
        if state_wave:
            transport["stateWave"] = state_wave
        write_canonical_json(prepared / "capture-transport.json", transport)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return transport


def capture_product_resume_inputs(
    plan_path: Path, destination: Path, *, uploads: Mapping[str, Any],
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str,
) -> dict[str, Any]:
    """Capture exact caller-selected uploads; payload trust is verified on resume."""
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    require_exact_keys(uploads, {"plan", "state", "release"}, "Product resume uploads")
    for name, record in uploads.items():
        require_exact_keys(record, {"artifactId", "artifactSha256"}, f"Product resume {name}")
        require_integer(record["artifactId"], f"Product resume {name} artifact ID", 1)
        require_sha256(record["artifactSha256"], f"Product resume {name} artifact digest")
    if len({record["artifactId"] for record in uploads.values()}) != 3:
        raise ValueError("Product resume upload IDs must be distinct")
    with tempfile.TemporaryDirectory(prefix="codex-agent-resume-capture-", dir=root) as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                            reject_symlink_parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("Product resume capture requires an authorized PR or merge-group run")
        producer = _consumer(plan, os.environ if environ is None else environ)["producer"]
        observed = _observe_contract_producer_runs(
            {"metadata": producer}, phases=("metadata",),
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        prepared = private / "result"
        prepared.mkdir()
        artifacts = {}
        for name, prefix in (("plan", "ci-plan"), ("state", "contract-phase-state"),
                             ("release", "contract-release-handoff")):
            record = uploads[name]
            artifact, raw = _download_contract_ci_upload(
                record["artifactId"], record["artifactSha256"],
                f"codex-agent-{prefix}-{producer['tree']}", producer, observed[0]["run"], token)
            archive = private / f"{name}.zip"
            archive.write_bytes(raw)
            verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
            safe_extract(archive, prepared / name)
            artifacts[name] = artifact
        if read_regular_file_bytes(prepared / "plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Captured product plan differs from the validated original plan")
        transport = {"artifacts": artifacts, "captureProducer": producer, "observed": observed}
        write_canonical_json(prepared / "capture-transport.json", transport)
        publish_regular_tree(prepared, destination)
    return transport


def _capture_completed_contract_handoff(
    plan_path: Path, state_root: Path, handoff_root: Path, destination: Path, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Bind a release envelope to exact original state; never reissue its receipts."""
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    for source in (Path(state_root), Path(handoff_root), Path(plan_path)):
        source = source.resolve(strict=True)
        output = destination.resolve(strict=False)
        if source == output or source in output.parents or output in source.parents:
            raise ValueError("Contract handoff destination overlaps original input")
    with tempfile.TemporaryDirectory(prefix="codex-agent-contract-resume-", dir=root) as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(read_regular_file_bytes(
            plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        plan = _validate_plan(captured_plan, root)
        prepared = private / "result"
        prepared.mkdir()
        trust = _release_trust(root, plan["validationCommit"], prepared)
        if trust is None:
            raise ValueError("Completed Contract handoff requires tracked release trust")
        state = private / "state"
        snapshot_regular_tree(state_root, state)
        result = _canonical_control(state / "contract-reuse-result.json", "Completed Contract result")
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        _validate_reuse_result(result, (contract,), require_complete=True)
        handoff = prepared / "contract-input"
        snapshot_regular_tree(handoff_root, handoff)
        phases = ("binary", "package", "validation", "metadata")
        originals = {}
        for phase in phases:
            originals[phase] = materialize_contract(
                captured_plan, state, phase, private / phase, with_receipt=True,
                repository_root=root, environ=environ)
            raw = read_regular_file_bytes(handoff / f"execution-closure/receipts/{phase}.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
            if raw != originals[phase]["receiptBytes"]:
                raise ValueError(f"Signed Contract {phase} receipt differs from completed original state")
        version = originals["metadata"]["receipt"]["productVersion"]
        stem = f"codex-agent-contract-{version}"
        payload = handoff / f"{stem}.zip"
        expected = {f"{stem}.zip", f"{stem}.attestation.json", f"{stem}.attestation.sig", "public-key.pub",
                    "execution-closure/contract-execution-closure.json",
                    "execution-closure/execution/contract-execution.zip",
                    *(f"execution-closure/receipts/{phase}.json" for phase in phases)}
        if {record["relativePath"] for record in regular_file_inventory(handoff)} != expected:
            raise ValueError("Completed Contract release handoff inventory is not exact")
        for original, retained in (
            (private / f"metadata/stage/outputs/{stem}.zip", payload),
            (private / "binary/stage/outputs/execution/contract-execution.zip",
             handoff / "execution-closure/execution/contract-execution.zip"),
        ):
            if sha256_file(original) != sha256_file(retained):
                raise ValueError("Signed Contract payload or execution archive differs from original state")
        verify_contract_attestation(
            payload, handoff / "execution-closure/receipts/metadata.json",
            handoff / f"{stem}.attestation.json", handoff / f"{stem}.attestation.sig",
            handoff / "public-key.pub", required_trust_domain="release",
            keyring=trust.keyring, keys_directory=trust.keys)
        evidence = {
            "attestation": f"contract-input/{stem}.attestation.json",
            "attestationSignature": f"contract-input/{stem}.attestation.sig",
            "publicKey": "contract-input/public-key.pub", "expectedTrustDomain": "release",
            "keyring": _relative(prepared, trust.keyring), "keysDirectory": _relative(prepared, trust.keys),
        }
        publish_regular_tree(prepared, destination)
    return evidence


def resume_products(
    plan_path: Path, discovery_root: Path, state_root: Path, contract_handoff: Path,
    destination: Path, github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resume the original discovery after Contract signing, with no new lookup."""
    github_output(github_output_path, {"full_reuse": False, "target_jobs_required": True,
                                      "product_reuse_reason": "not-evaluated"})
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    destination.rmdir()
    root = supplied_root.resolve()
    environment = os.environ if environ is None else environ
    for original in (plan_path, discovery_root, state_root, contract_handoff):
        source, output = Path(original).resolve(strict=True), destination.resolve(strict=False)
        if source == output or source in output.parents or output in source.parents:
            raise ValueError("Product resume destination overlaps original input")
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-resume-", dir=root) as temporary:
        private = Path(temporary).resolve()
        prepared = private / "result"
        prepared.mkdir()
        captured_plan = private / "impact-plan.json"
        captured_plan.write_bytes(read_regular_file_bytes(
            plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True))
        plan = _validate_plan(captured_plan, root)
        snapshot_regular_tree(discovery_root, prepared / "discovery")
        snapshot_regular_tree(state_root, prepared / "contract-state")
        complete = advance_contract(
            captured_plan, prepared / "discovery", prepared / "contract-state", [],
            private / "replayed-contract", private / "contract-outputs",
            repository_root=root, environ=environment, sdk_validation_tooling=sdk_validation_tooling)
        if complete["fullReuse"] is not True:
            raise ValueError("Product resume requires complete original Contract phases")
        evidence_root = prepared / "authenticated-contract"
        evidence = _capture_completed_contract_handoff(
            captured_plan, prepared / "contract-state", contract_handoff, evidence_root,
            repository_root=root, environ=environment)
        contract_request = _wave_control(
            prepared / "discovery/contract-reuse-request.json", "Original Contract request")
        requested = _requested(plan)
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        if contract not in _dependency_closure(requested):
            raise ValueError("Product resume selection has no Contract dependency")
        authorities, unavailable = _authorities(root, plan["validationCommit"], _dependency_closure(requested))
        if authorities is None:
            raise ValueError(unavailable or "Product phase authority is unavailable")
        wave = _wave_request(
            plan, root, prepared, requested, _versions(root, plan["validationCommit"]), authorities, [],
            _rebase_contract_evidence_paths(evidence, evidence_root, prepared))
        wave["catalogs"] = _rebase_catalog_paths(contract_request["catalogs"], prepared / "discovery", prepared)
        wave.update(_rebase_native_request(contract_request, prepared / "discovery", prepared))
        initial_objects, original_phases = _completed_contract_objects(
            plan, prepared / "contract-state", prepared, environment)
        wave["availableObjects"] = initial_objects
        ready_plans = {}

        def retain(instance, phase_plan):
            if instance in ready_plans:
                raise ValueError("Product resume elected a duplicate ready phase")
            ready_plans[instance] = phase_plan

        reuse = _plan_with_sdk_tooling(wave, sdk_validation_tooling, build_plan_consumer=retain)
        _, selected, phases = _validate_reuse_result(reuse, requested, require_complete=False)
        by_id = {_identity(phase): phase for phase in phases}
        originals = {_identity(phase): phase for phase in original_phases}
        if any(by_id.get(instance, {}).get("state") != "retained" for instance in originals):
            raise ValueError("Product resume did not retain every authenticated Contract object")
        sources = {_identity(record): prepared / record["objectPath"] for record in initial_objects}
        remote_sources = _catalog_object_sources(wave)
        for instance in selected:
            if instance not in sources:
                phase = by_id[instance]
                sources[instance] = remote_sources[(phase["source"], phase["transportSource"]["indexSha256"], phase["buildKey"])]
        normalized = {"schemaVersion": 1, "result": "complete", "fullReuse": True,
                      "phases": [originals.get(instance, by_id[instance]) for instance in selected],
                      "matrices": {"contract": [], "runtime": [], "sdk": []}}
        write_carrier(prepared / ("carrier" if reuse["fullReuse"] else "reused-carrier"),
                      normalized, selected, sources, _consumer(plan, environment))
        _write_ready_plans(prepared, ready_plans)
        # This fixed logical root is the existing relocatable discovery protocol;
        # consumers rebase only relative transport paths to their private capture.
        wave["artifactRoot"] = str(root / "build/product-reuse")
        write_canonical_json(prepared / "reuse-wave-request.json", wave)
        write_canonical_json(prepared / "reuse-wave-result.json", reuse)
        write_canonical_json(prepared / "producer.json", _consumer(plan, environment)["producer"])
        result = _result(requested, complete=reuse["fullReuse"],
                         reason="verified-full-reuse" if reuse["fullReuse"] else "product-build-required", reuse=reuse)
        write_canonical_json(prepared / "request.json", _discovery_request(plan, requested))
        write_canonical_json(prepared / "result.json", result)
        publish_regular_tree(prepared, destination)
    github_output(github_output_path, {"full_reuse": result["fullReuse"],
        "target_jobs_required": result["targetJobsRequired"], "product_reuse_reason": result["reason"]})
    return result


def discover(
    plan_path: Path, destination: Path, github_output_path: Path, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    native_evidence_roots: tuple[Path, ...] = (),
    adapter_evidence_roots: tuple[Path, ...] = (),
    sdk_evidence_roots: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    # A failing adapter must never make a missing output look like permission to skip work.
    github_output(github_output_path, {
        "full_reuse": False,
        "target_jobs_required": True,
        "product_reuse_reason": "not-evaluated",
        "contract_next_phase": "none",
        "contract_reconciliation_required": False,
    })
    supplied_root = Path(__file__).resolve().parents[1] if repository_root is None else repository_root
    destination = _prepare_destination(destination, supplied_root)
    root = supplied_root.resolve()
    plan = _validate_plan(plan_path, root)
    requested = _requested(plan)
    request = _discovery_request(plan, requested)
    if not requested:
        return _finish(destination, request, _result(
            requested, complete=True, reason="no-product-work",
        ), github_output_path)
    if plan["event"] == "workflow_dispatch":
        return _finish(destination, request, _result(
            requested, complete=False, reason="workflow-dispatch-reuse-disabled",
        ), github_output_path)
    if plan["remoteBuildAuthorized"] is not True:
        return _finish(destination, request, _result(
            requested, complete=False, reason="remote-build-unauthorized",
        ), github_output_path)

    closure = _dependency_closure(requested)
    versions = _versions(root, plan["validationCommit"])
    environment = os.environ if environ is None else environ
    trust = _release_trust(root, plan["validationCommit"], destination)
    catalogs = _discover_catalogs(plan, destination, trust, environment, versions)
    native_records = _capture_native_handoffs(
        native_evidence_roots, destination / "native-runtime-evidence", destination, trust)
    adapter_records = _capture_native_handoffs(
        adapter_evidence_roots, destination / "adapter-runtime-evidence", destination, trust, adapter=True)
    catalog_sdk_roots = tuple(catalog.sdk_validation_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.sdk_validation_evidence_root is not None)
    sdk_records = _capture_sdk_handoffs((*catalog_sdk_roots, *sdk_evidence_roots), destination / "sdk-validation-evidence", destination,
        repository=root, policy_revision=plan["validationCommit"], tooling=sdk_validation_tooling)

    contract_evidence = None
    contract = PhaseInstanceId("contract", "contract", "metadata", "common")
    if contract in closure:
        contract_closure = _dependency_closure((contract,))
        contract_authorities, unavailable = _authorities(
            root, plan["validationCommit"], contract_closure,
        )
        if contract_authorities is None:
            raise ValueError(unavailable or "Contract phase authority is unavailable")
        contract_request = _wave_request(
            plan, root, destination, (contract,), versions, contract_authorities, catalogs, None,
        )
        _merge_native_comparison_records(contract_request, native_records)
        _merge_native_comparison_records(contract_request, adapter_records, key=_ADAPTER_REQUEST_KEY)
        _merge_native_comparison_records(contract_request, sdk_records, key="sdkValidationEvidence")
        write_canonical_json(destination / "contract-reuse-request.json", contract_request)
        contract_ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
        contract_result = _plan_with_sdk_tooling(
            contract_request, sdk_validation_tooling,
            build_plan_consumer=lambda instance, phase_plan: contract_ready_plans.setdefault(
                instance, phase_plan,
            ),
        )
        write_canonical_json(destination / "contract-reuse-result.json", contract_result)
        if contract_result["fullReuse"] is not True:
            if any(phase.get("state") == "reused" for phase in contract_result["phases"]):
                _write_reused_carrier(
                    contract_result,
                    (contract,),
                    catalogs,
                    destination / "reused-carrier",
                    _consumer(plan, environment),
                    require_complete=False,
                )
            _write_ready_plans(destination, contract_ready_plans)
            if contract_ready_plans:
                write_canonical_json(
                    destination / "producer.json", _consumer(plan, environment)["producer"],
                )
            write_canonical_json(destination / "reuse-wave-result.json", contract_result)
            return _finish(destination, request, _result(
                requested, complete=False, reason="product-build-required", reuse=contract_result,
            ), github_output_path,
                contract_next_phase=_contract_ready_phase(contract_ready_plans),
                contract_reconciliation_required=True,
            )
        contract_evidence = _contract_evidence(
            plan, destination, catalogs, contract_result, trust,
        )

    authorities, unavailable = _authorities(root, plan["validationCommit"], closure)
    if authorities is None:
        return _finish(destination, request, _result(
            requested, complete=False, reason=unavailable or "phase-authority-unavailable",
        ), github_output_path)

    wave_request = _wave_request(
        plan, root, destination, requested, versions, authorities, catalogs, contract_evidence,
    )
    _merge_native_comparison_records(wave_request, native_records)
    _merge_native_comparison_records(wave_request, adapter_records, key=_ADAPTER_REQUEST_KEY)
    _merge_native_comparison_records(wave_request, sdk_records, key="sdkValidationEvidence")
    write_canonical_json(destination / "reuse-wave-request.json", wave_request)
    ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain_ready_plan(instance: PhaseInstanceId, phase_plan: dict[str, Any]) -> None:
        if instance in ready_plans:
            raise ValueError(f"Duplicate ready phase plan: {instance}")
        ready_plans[instance] = phase_plan

    reuse = _plan_with_sdk_tooling(wave_request, sdk_validation_tooling, build_plan_consumer=retain_ready_plan)
    _write_ready_plans(destination, ready_plans)
    # Evidence-only waits still need original workflow control provenance when
    # advance-products resumes them; an empty build matrix must not lose it.
    write_canonical_json(destination / "producer.json", _consumer(plan, environment)["producer"])
    write_canonical_json(destination / "reuse-wave-result.json", reuse)
    matrices = reuse.get("matrices")
    complete = (
        reuse.get("result") == "complete"
        and reuse.get("fullReuse") is True
        and isinstance(matrices, dict)
        and set(matrices) == {"contract", "runtime", "sdk"}
        and all(value == [] for value in matrices.values())
    )
    if complete:
        _reverify_complete(reuse, requested, catalogs, destination, _consumer(plan, environment))
    elif any(phase.get("state") == "reused" for phase in reuse["phases"]):
        _write_reused_carrier(
            reuse,
            requested,
            catalogs,
            destination / "reused-carrier",
            _consumer(plan, environment),
            require_complete=False,
        )
    return _finish(destination, request, _result(
        requested,
        complete=complete,
        reason="verified-full-reuse" if complete else "product-build-required",
        reuse=reuse,
    ), github_output_path)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="python3 ci/product_reuse.py")
    commands = result.add_subparsers(dest="command", required=True)
    discover_command = commands.add_parser("discover")
    discover_command.add_argument("--plan", type=Path, required=True)
    discover_command.add_argument("--destination", type=Path, required=True)
    discover_command.add_argument("--handoff", type=Path)
    discover_command.add_argument("--native-runtime-evidence", type=Path, action="append", default=[])
    discover_command.add_argument("--adapter-runtime-evidence", type=Path, action="append", default=[])
    discover_command.add_argument("--github-output", type=Path, required=True)
    advance_command = commands.add_parser("advance-contract")
    advance_command.add_argument("--plan", type=Path, required=True)
    advance_command.add_argument("--discovery-root", type=Path, required=True)
    advance_command.add_argument("--state-root", type=Path)
    advance_command.add_argument("--phase-shard", type=Path, action="append", default=[])
    advance_command.add_argument("--destination", type=Path, required=True)
    advance_command.add_argument("--github-output", type=Path, required=True)
    advance_command.add_argument("--sdk-validation-tooling", type=Path,
                                 help="Current caller-owned tooling policy JSON, never a retained request field")
    products_command = commands.add_parser("advance-products")
    products_command.add_argument("--plan", type=Path, required=True)
    products_command.add_argument("--discovery-root", type=Path, required=True)
    products_command.add_argument("--state-root", type=Path)
    products_command.add_argument("--phase-shard", type=Path, action="append", default=[])
    products_command.add_argument("--failed-phase", nargs=4, action="append", default=[],
                                  metavar=("PRODUCT", "COMPONENT", "PHASE", "TARGET"),
                                  help="Reported failed worker; never admitted as successful evidence")
    products_command.add_argument("--runtime-workers-only", action="store_true",
                                  help="Collect exactly the elected standalone Runtime rows; leave other families ready")
    products_command.add_argument("--destination", type=Path, required=True)
    products_command.add_argument("--github-output", type=Path, required=True)
    products_command.add_argument("--native-runtime-evidence", type=Path, action="append", default=[])
    products_command.add_argument("--adapter-runtime-evidence", type=Path, action="append", default=[])
    resume_command = commands.add_parser("resume-products")
    for name in ("plan", "discovery-root", "state-root", "contract-handoff", "destination", "github-output"):
        resume_command.add_argument(f"--{name}", type=Path, required=True)
    resume_command.add_argument("--sdk-validation-tooling", type=Path,
                               help="Current caller-owned tooling policy JSON, never a retained request field")
    resume_capture = commands.add_parser("capture-product-resume-inputs")
    resume_capture.add_argument("--plan", type=Path, required=True)
    resume_capture.add_argument("--destination", type=Path, required=True)
    resume_capture.add_argument("--trusted-workflow-sha", required=True)
    for name in ("plan", "state", "release"):
        resume_capture.add_argument(f"--{name}-artifact-id", type=int, required=True)
        resume_capture.add_argument(f"--{name}-artifact-sha256", required=True)
    supervisor_capture = commands.add_parser("capture-runtime-supervisor-upload")
    for name in ("plan", "destination"):
        supervisor_capture.add_argument(f"--{name}", type=Path, required=True)
    supervisor_capture.add_argument("--artifact-id", type=int, required=True)
    for name in ("artifact-sha256", "expected-build-key", "trusted-workflow-sha"):
        supervisor_capture.add_argument(f"--{name}", required=True)
    runtime_resume_capture = commands.add_parser("capture-runtime-resume-upload")
    for name in ("plan", "destination"):
        runtime_resume_capture.add_argument(f"--{name}", type=Path, required=True)
    runtime_resume_capture.add_argument("--artifact-id", type=int, required=True)
    runtime_resume_capture.add_argument("--state-wave", type=int, default=0)
    for name in ("artifact-sha256", "trusted-workflow-sha"):
        runtime_resume_capture.add_argument(f"--{name}", required=True)
    runtime_collection = commands.add_parser("collect-runtime-workers")
    for name in ("plan", "discovery-root", "destination"):
        runtime_collection.add_argument(f"--{name}", type=Path, required=True)
    runtime_collection.add_argument("--state-root", type=Path)
    runtime_collection.add_argument("--trusted-workflow-sha", required=True)
    runtime_collection.add_argument("--sdk-validation-tooling", type=Path)
    supervisor_execute = commands.add_parser("execute-runtime-supervisor")
    for name in ("plan", "discovery-root", "destination"):
        supervisor_execute.add_argument(f"--{name}", type=Path, required=True)
    supervisor_execute.add_argument("--state-root", type=Path)
    supervisor_execute.add_argument("--expected-build-key", required=True)
    supervisor_execute.add_argument("--sdk-validation-tooling", type=Path)
    aggregate_execute = commands.add_parser("execute-runtime-aggregate")
    for name in ("plan", "discovery-root", "destination", "variant-trust-root"):
        aggregate_execute.add_argument(f"--{name}", type=Path, required=True)
    aggregate_execute.add_argument("--state-root", type=Path)
    aggregate_execute.add_argument("--expected-build-key", required=True)
    aggregate_execute.add_argument("--sdk-validation-tooling", type=Path)
    for command in (discover_command, products_command):
        command.add_argument("--sdk-validation-evidence", type=Path, action="append", default=[])
        command.add_argument("--sdk-validation-tooling", type=Path,
                             help="Current caller-owned tooling policy JSON, never a retained request field")
    materialize_command = commands.add_parser("materialize-contract")
    materialize_command.add_argument("--plan", type=Path, required=True)
    materialize_command.add_argument("--state-root", type=Path, required=True)
    materialize_command.add_argument("--phase", required=True)
    materialize_command.add_argument("--destination", type=Path, required=True)
    materialize_command.add_argument("--with-receipt", action="store_true")
    matrix_command = commands.add_parser("runtime-worker-matrix")
    for argument in ("plan", "discovery-root", "github-output"):
        matrix_command.add_argument(f"--{argument}", type=Path, required=True)
    matrix_command.add_argument("--state-root", type=Path)
    matrix_command.add_argument("--sdk-validation-tooling", type=Path)
    for name in ("materialize-product-predecessors", "prepare-runtime-phase", "execute-runtime-phase"):
        predecessors_command = commands.add_parser(name)
        for argument in ("plan", "discovery-root", "destination"):
            predecessors_command.add_argument(f"--{argument}", type=Path, required=True)
        predecessors_command.add_argument("--state-root", type=Path)
        for argument in (*_IDENTITY_KEYS, "expected-build-key"):
            predecessors_command.add_argument(f"--{argument}", required=True)
        predecessors_command.add_argument("--sdk-validation-tooling", type=Path,
                                          help="Current caller-owned tooling policy JSON")
        if name == "execute-runtime-phase":
            predecessors_command.add_argument("--app-server-archive", type=Path,
                                              help="Existing native binary archive; verified against exact Git policy")
            predecessors_command.add_argument("--supervisor-artifact-id", type=int)
            predecessors_command.add_argument("--supervisor-artifact-sha256")
            predecessors_command.add_argument("--supervisor-trusted-workflow-sha")
    capture_command = commands.add_parser("capture-contract-ci")
    capture_command.add_argument("--destination", type=Path, required=True)
    capture_command.add_argument("--artifact-id", type=int, required=True)
    capture_command.add_argument("--artifact-sha256", required=True,
                                 help="sha256:-prefixed digest from the trusted upload action output")
    capture_command.add_argument("--transport-producer", type=Path, required=True,
                                 help="Current trusted caller producer, never a downloaded receipt")
    capture_command.add_argument("--trusted-workflow-sha", required=True)
    capture_command.add_argument("--contract-version", required=True)
    originals_command = commands.add_parser("capture-contract-original-ci")
    originals_command.add_argument("--capture-root", type=Path, required=True)
    originals_command.add_argument("--destination", type=Path, required=True)
    originals_command.add_argument("--contract-version", required=True)
    originals_command.add_argument("--trusted-workflow-sha", required=True)
    originals_command.add_argument("--release-handoff", type=Path, action="append", default=[])
    originals_command.add_argument("--keyring", type=Path)
    originals_command.add_argument("--keys-directory", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        tooling = None
        if getattr(arguments, "sdk_validation_tooling", None) is not None:
            tooling = _canonical_control(arguments.sdk_validation_tooling, "Caller SDK tooling policy")
        if arguments.command == "discover":
            discover(arguments.plan, arguments.destination, arguments.github_output,
                     native_evidence_roots=tuple(arguments.native_runtime_evidence),
                     adapter_evidence_roots=tuple(arguments.adapter_runtime_evidence),
                     sdk_evidence_roots=tuple(arguments.sdk_validation_evidence), sdk_validation_tooling=tooling)
            if arguments.handoff is not None:
                publish_regular_tree(arguments.destination, arguments.handoff)
        elif arguments.command == "advance-contract":
            advance_contract(
                arguments.plan,
                arguments.discovery_root,
                arguments.state_root,
                arguments.phase_shard,
                arguments.destination,
                arguments.github_output,
                sdk_validation_tooling=tooling,
            )
        elif arguments.command == "advance-products":
            advance_products(
                arguments.plan,
                arguments.discovery_root,
                arguments.state_root,
                arguments.phase_shard,
                arguments.destination,
                arguments.github_output,
                native_evidence_roots=tuple(arguments.native_runtime_evidence),
                adapter_evidence_roots=tuple(arguments.adapter_runtime_evidence),
                sdk_evidence_roots=tuple(arguments.sdk_validation_evidence), sdk_validation_tooling=tooling,
                failed_instances=tuple(PhaseInstanceId(*value) for value in arguments.failed_phase),
                **({"runtime_workers_only": True} if arguments.runtime_workers_only else {}),
            )
        elif arguments.command == "collect-runtime-workers":
            collect_runtime_workers(
                arguments.plan, arguments.discovery_root, arguments.state_root, arguments.destination,
                trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""),
                sdk_validation_tooling=tooling)
        elif arguments.command == "runtime-worker-matrix":
            github_output(arguments.github_output, {"runtime_matrix": '{"include":[]}', "runtime_workers_required": False})
            matrix = runtime_worker_matrix(
                arguments.plan, arguments.discovery_root, arguments.state_root,
                sdk_validation_tooling=tooling)
            github_output(arguments.github_output, {"runtime_matrix": canonical_json_bytes(matrix).decode("utf-8").strip(),
                                                   "runtime_workers_required": bool(matrix["include"])})
        elif arguments.command == "capture-contract-ci":
            capture_contract_ci_artifact(
                arguments.destination, artifact_id=arguments.artifact_id,
                artifact_sha256=arguments.artifact_sha256,
                transport_producer=_canonical_control(arguments.transport_producer, "Caller capture producer"),
                trusted_workflow_sha=arguments.trusted_workflow_sha,
                contract_version=arguments.contract_version, token=os.environ.get("GITHUB_TOKEN", ""))
        elif arguments.command == "execute-runtime-supervisor":
            execute_runtime_supervisor(
                arguments.plan, arguments.discovery_root, arguments.state_root, arguments.destination,
                expected_build_key=arguments.expected_build_key, sdk_validation_tooling=tooling)
        elif arguments.command == "capture-runtime-supervisor-upload":
            capture_runtime_supervisor_upload(
                arguments.plan, arguments.destination, artifact_id=arguments.artifact_id,
                artifact_sha256=arguments.artifact_sha256, expected_build_key=arguments.expected_build_key,
                trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""))
        elif arguments.command == "capture-runtime-resume-upload":
            capture_runtime_resume_upload(
                arguments.plan, arguments.destination, artifact_id=arguments.artifact_id,
                artifact_sha256=arguments.artifact_sha256,
                trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""),
                **({"state_wave": arguments.state_wave} if arguments.state_wave else {}))
        elif arguments.command == "capture-product-resume-inputs":
            capture_product_resume_inputs(
                arguments.plan, arguments.destination,
                uploads={name: {"artifactId": getattr(arguments, f"{name}_artifact_id"),
                                "artifactSha256": getattr(arguments, f"{name}_artifact_sha256")}
                         for name in ("plan", "state", "release")},
                trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""))
        elif arguments.command == "resume-products":
            resume_products(
                arguments.plan, arguments.discovery_root, arguments.state_root,
                arguments.contract_handoff, arguments.destination, arguments.github_output,
                sdk_validation_tooling=tooling)
        elif arguments.command == "execute-runtime-aggregate":
            execute_runtime_aggregate(
                arguments.plan, arguments.discovery_root, arguments.state_root,
                arguments.destination, expected_build_key=arguments.expected_build_key,
                variant_trust_root=arguments.variant_trust_root, sdk_validation_tooling=tooling)
        elif arguments.command in {"materialize-product-predecessors", "prepare-runtime-phase", "execute-runtime-phase"}:
            operation = {"materialize-product-predecessors": materialize_product_predecessors,
                         "prepare-runtime-phase": prepare_runtime_phase,
                         "execute-runtime-phase": execute_runtime_phase}[arguments.command]
            additional = {}
            if arguments.command == "execute-runtime-phase":
                if arguments.app_server_archive is not None:
                    additional["app_server_archive"] = arguments.app_server_archive
                values = (arguments.supervisor_artifact_id, arguments.supervisor_artifact_sha256,
                          arguments.supervisor_trusted_workflow_sha)
                if any(value is not None for value in values):
                    if any(value is None for value in values):
                        raise ValueError("All three caller-bound supervisor upload arguments are required")
                    additional["supervisor_upload"] = dict(zip(
                        ("artifactId", "artifactSha256", "trustedWorkflowSha"), values))
            operation(
                arguments.plan, arguments.discovery_root, arguments.state_root,
                PhaseInstanceId(arguments.product, arguments.component, arguments.phase, arguments.target),
                arguments.destination, expected_build_key=arguments.expected_build_key,
                sdk_validation_tooling=tooling, **additional)
        elif arguments.command == "capture-contract-original-ci":
            capture_contract_original_ci_phases(
                arguments.capture_root, arguments.destination, contract_version=arguments.contract_version,
                trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""),
                release_handoffs=tuple(arguments.release_handoff),
                keyring=arguments.keyring, keys_directory=arguments.keys_directory)
        else:
            materialize_contract(
                arguments.plan,
                arguments.state_root,
                arguments.phase,
                arguments.destination,
                with_receipt=arguments.with_receipt,
            )
    except (OSError, ValueError) as error:
        parser().error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
