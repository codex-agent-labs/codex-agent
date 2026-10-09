#!/usr/bin/env python3
"""Resolve authenticated product reuse before any target job is created."""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
import os
import ntpath
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping
import urllib.error
import zipfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from sdk_metadata_policy import add_metadata_admission_arguments, metadata_admission_options

from impact import validate_legacy_lane_projection, validate_remote_build_authorization
from receipt import safe_extract
from reuse import api_json, download_artifact, download_artifact_to_file, github_output, paginated_items, run_matches_pr


def _retry_github_get(operation):
    """Retry transient recovery GETs; every attempt retains full authentication."""
    @wraps(operation)
    def retry(*args, **kwargs):
        for attempt in range(4):
            try:
                return operation(*args, **kwargs)
            except (urllib.error.URLError, TimeoutError) as error:
                transient = (isinstance(error, TimeoutError)
                    or isinstance(error, urllib.error.HTTPError) and error.code in {502, 503, 504}
                    or isinstance(error, urllib.error.URLError) and isinstance(error.reason, socket.gaierror))
                if attempt == 3 or not transient:
                    raise
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                time.sleep(2 ** attempt)
    return retry


api_json = _retry_github_get(api_json)
paginated_items = _retry_github_get(paginated_items)
download_artifact = _retry_github_get(download_artifact)
download_artifact_to_file = _retry_github_get(download_artifact_to_file)
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
    git_product_versions,
    regular_file_inventory,
    require_array,
    require_boolean,
    require_exact_keys,
    require_integer,
    require_object,
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
    NATIVE_BINDINGS,
    NATIVE_TARGETS,
    RUNTIME_COMPONENTS,
    SDK_FACADE_TARGETS,
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
    javascript_validation_dependencies,
)
from products.runtime_flags import load_runtime_binary_flags_bytes
from products.sdk_dotnet_toolchain import load_sdk_dotnet_profile_bytes
from products.runtime_adapter_content import rebase_adapter_comparison_records
from products.sdk_validation import rebase_sdk_validation_records
from products.sdk_release_selection import sdk_runtime_source
from products.sdk_validation_inputs import load_sdk_validation_evidence, stage_sdk_validation_evidence
from products.sdk_apple_validation_inputs import (
    capture_sdk_apple_validation_evidence, load_sdk_apple_validation_evidence, rebase_sdk_apple_validation_records,
)
from products.inventory import require_regular_directory
from products.adapter_runtime_inputs import load_adapter_runtime_evidence, stage_adapter_runtime_evidence
from products.runtime_evidence import (
    derive_authenticated_runtime_validation_projection,
    jvm_evidence_filename,
    node_evidence_filename,
)
from products.restore import (
    memoized_file_inventory as regular_file_inventory,
    verification_scoped,
    verification_session,
    OBJECT_ZIP_LIMITS,
    PHASE_PLAN_KEYS,
    PHASE_RECEIPT_NAME,
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
from products.receipt import validate_phase_receipt, validate_producer, verify_output_manifest_identity
from products.reuse import (
    SOURCES, _dependency_closure, plan_reuse_wave,
    _native_comparison_records, _native_evidence_paths,
)
from products.native_runtime_inputs import load_native_runtime_evidence, stage_native_runtime_evidence
from products.runtime_aggregate_inputs import (
    load_runtime_aggregate_release_evidence, stage_runtime_aggregate_release_evidence,
    rebase_runtime_aggregate_release_records,
)
from products.selection import classify_paths
from products.signatures import load_keyring, public_key_for_metadata, public_key_path
from products.toolchain import load_toolchain_profile_bytes


_PLAN_KEYS = {
    "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
    "validationCommit", "validationTree", "mergeReady", "remoteBuildAuthorized",
    "remoteBuildAuthorizationReason", "androidEvidenceRequired", "fullRequested", "full",
    "unknownPaths", "changedPaths", "lanes",
}
_PRIOR_RUNTIME_WORKFLOW_SHA = "88f04b8d9b1d3cd7b362d7ea2e3924cf5de3e8b0"
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
_AGGREGATE_REQUEST_KEY = "runtimeAggregateReleaseEvidence"
_RECOVERABLE_RUNTIME_COMPONENTS = (*RUNTIME_COMPONENTS, "runtime-aggregate")
_SDK_REQUEST_KEYS = {"sdkValidationEvidence", "sdkAppleValidationEvidence", "sdkRuntimeSource"}
_KEYRING_PATH = "gradle/release/product-signing-keys.json"
_KEYS_ROOT = "gradle/release/keys"
_PROFILE_ROOT = "gradle/release/toolchains/runtime"
_OID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
_CATALOG_PREFIX = "codex-agent-product-catalog-v1-"
_INLINE_UPLOAD_LIMIT = 4 * 1024 * 1024 * 1024
_CATALOG_LIMIT = 16 * 1024 * 1024 * 1024
_CATALOG_ZIP_LIMITS = {
    # Actions uploads are external transport, not canonical product payloads.
    "require_sorted": False,
    "max_archive_bytes": _CATALOG_LIMIT,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 16_384,
    "max_entry_bytes": OBJECT_ZIP_LIMITS["max_archive_bytes"],
    "max_total_bytes": _CATALOG_LIMIT,
    "max_compression_ratio": 200,
}
_APPLE_UPLOAD_LIMIT = 8 * 1024 * 1024 * 1024
_APPLE_UPLOAD_ZIP_LIMITS = {
    **_CATALOG_ZIP_LIMITS,
    "max_archive_bytes": _APPLE_UPLOAD_LIMIT,
    "max_entry_bytes": _APPLE_UPLOAD_LIMIT,
    "max_total_bytes": _APPLE_UPLOAD_LIMIT,
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
    runtime_aggregate_evidence_root: Path | None = None
    sdk_apple_validation_evidence_root: Path | None = None
    sdk_maven_evidence_root: Path | None = None
    sdk_metadata_evidence_root: Path | None = None
    immutable_upload: Mapping[str, Any] | None = None


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
    allow_dispatch: bool = False,
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
        trigger_head = run.get("head_sha")
        if not isinstance(trigger_head, str) or _OID.fullmatch(trigger_head) is None:
            raise ValueError("Original CI attempt lacks exact triggering head")
        # GitHub updates a historical run's pull_requests[].head.sha when the
        # PR moves; run.head_sha retains the head that triggered this attempt.
        original_head = trigger_head if trigger_head != expected_commit else identities[1]
        if [value.get("sha") if isinstance(value, dict) else None for value in parents] != [
            identities[0], original_head,
        ]:
            raise ValueError("Tested merge does not bind the original CI pull-request base/head")
    elif (run.get("event") not in ({"merge_group", "workflow_dispatch"} if allow_dispatch else {"merge_group"})
          or run.get("head_sha") != expected_commit):
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


def _prior_failed_pr_attempts(
    plan: Mapping[str, Any], producer: Mapping[str, Any], token: str,
    *, api: str = "https://api.github.com", required_artifact_prefixes: tuple[str, ...] = (),
    limit: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """List prior interrupted PR attempts; their phase uploads still need admission."""
    if plan["event"] != "pull_request" or plan["pullRequest"] is None:
        return ()
    repository = plan["repository"]
    if repository != "codex-agent-labs/codex-agent":
        raise ValueError("Prior PR recovery requires the canonical repository")
    current_run = require_integer(producer["runId"], "Current product run ID", 1)
    current_attempt = require_integer(producer["runAttempt"], "Current product run attempt", 1)
    prefix = f"{api}/repos/{repository}/actions/runs"
    artifact_lists: dict[int, list[Any]] = {}

    def eligible(run: Mapping[str, Any], run_id: int, attempt: int) -> bool:
        return (
            require_integer(run.get("id"), "Prior product run ID", 1) == run_id
            and require_integer(run.get("run_attempt"), "Prior product run attempt", 1) == attempt
            and run.get("event") == "pull_request"
            and run.get("path") == ".github/workflows/ci.yml"
            and run.get("status") == "completed"
            and run.get("conclusion") in {"failure", "cancelled"}
            and run_matches_pr(run, plan["pullRequest"])
            and all(isinstance(run.get(field), dict)
                    and run[field].get("full_name") == repository
                    and run[field].get("fork") is False
            for field in ("repository", "head_repository"))
        )

    def has_required_artifact(run_id: int, attempt: int) -> bool:
        if not required_artifact_prefixes:
            return True
        if run_id not in artifact_lists:
            artifact_lists[run_id] = paginated_items(
                f"{prefix}/{run_id}/artifacts", "artifacts", token)
        artifacts = artifact_lists[run_id]
        return any(isinstance(artifact, dict) and artifact.get("expired") is False
                   and isinstance(artifact.get("name"), str)
                   and artifact["name"].startswith(required_artifact_prefixes)
                   and artifact["name"].endswith(f"-attempt-{attempt}")
                   for artifact in artifacts)

    matches = []
    if current_attempt > 1:
        for attempt in range(current_attempt - 1, 0, -1):
            previous = api_json(f"{prefix}/{current_run}/attempts/{attempt}", token)
            if previous.get("conclusion") not in {"failure", "cancelled"}:
                continue
            if not eligible(previous, current_run, attempt):
                raise ValueError("Prior failed PR attempt differs from the current run")
            if has_required_artifact(current_run, attempt):
                matches.append(previous)
                if limit is not None and len(matches) == limit:
                    return tuple(matches)

    runs = paginated_items(
        f"{prefix}?event=pull_request&status=completed",
        "workflow_runs", token)
    candidates = [run for run in runs if isinstance(run, dict)
                  and type(run.get("id")) is int and 0 < run["id"] < current_run
                  and run.get("path") == ".github/workflows/ci.yml"
                  and run.get("conclusion") in {"failure", "cancelled"}
                  and run_matches_pr(run, plan["pullRequest"])]
    for selected in sorted(candidates, key=lambda run: run["id"], reverse=True):
        latest_attempt = require_integer(selected.get("run_attempt"), "Prior product run attempt", 1)
        for attempt in range(latest_attempt, 0, -1):
            original = api_json(f"{prefix}/{selected['id']}/attempts/{attempt}", token)
            if original.get("conclusion") not in {"failure", "cancelled"}:
                continue
            if not eligible(original, selected["id"], attempt):
                raise ValueError("Prior failed PR attempt differs from its official workflow listing")
            if has_required_artifact(selected["id"], attempt):
                matches.append(original)
                if limit is not None and len(matches) == limit:
                    return tuple(matches)
    return tuple(matches)


def _prior_failed_pr_attempt(
    plan: Mapping[str, Any], producer: Mapping[str, Any], token: str,
    *, api: str = "https://api.github.com", required_artifact_prefixes: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Retain the single-attempt selector for unrelated legacy callers."""
    attempts = _prior_failed_pr_attempts(
        plan, producer, token, api=api, required_artifact_prefixes=required_artifact_prefixes,
        limit=1)
    return attempts[0] if attempts else None


def verify_contract_producer_runs(
    producers: Mapping[str, Any], *, token: str, trusted_workflow_sha: str | None = None,
    trusted_workflows_by_phase: Mapping[str, Any] | None = None,
    jobs_by_phase: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Observe exact original CI attempts, not whole-run success or signing authority.

    The protected caller supplies reviewed workflow pins and fixed job names.
    This does not bind an upload to the jobs: artifact/object/closure admission
    and protected signing policy must still pass before a private key is used.
    Returned API evidence stays external to reusable payloads and original receipts.
    """
    return _observe_contract_producer_runs(
        producers, phases=("binary", "package", "validation", "metadata"),
        trusted_workflow_sha=trusted_workflow_sha,
        trusted_workflows_by_phase=trusted_workflows_by_phase,
        jobs_by_phase=jobs_by_phase, token=token)


def _observe_contract_producer_runs(
    producers: Mapping[str, Any], *, phases: tuple[str, ...], token: str,
    trusted_workflow_sha: str | None = None,
    trusted_workflows_by_phase: Mapping[str, Any] | None = None,
    jobs_by_phase: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    if jobs_by_phase is None:
        jobs_by_phase = {phase: "product-validation / product-contracts" if phase == "binary"
                         else "product-validation / contract-continuation" for phase in phases}
    return _observe_ci_producer_jobs(
        producers, jobs_by_phase=jobs_by_phase, trusted_workflow_sha=trusted_workflow_sha,
        trusted_workflows_by_phase=trusted_workflows_by_phase, token=token)


def _require_ci_workflow_reference(run, workflow, sha):
    references = require_array(run.get("referenced_workflows"), "Contract original workflow references")
    selected = [value for value in references if isinstance(value, dict)
                and isinstance(value.get("path"), str)
                and value["path"].split("@", 1)[0] == workflow.split("@", 1)[0]]
    protected_path = workflow.split("@", 1)[0] + "@reuse-authority"
    if (len(selected) != 1 or selected[0].get("sha") != sha
            or not (selected[0].get("path") == workflow
                    or selected[0].get("path") == protected_path
                    and selected[0].get("ref") == "refs/heads/reuse-authority")):
        raise ValueError("Contract original CI attempt lacks the caller-pinned workflow")


def _runtime_prior_workflow_sha(run, current_sha):
    # Prior genuine phases retain their original reviewed workflow authority after a pin rotation.
    for sha in dict.fromkeys((current_sha, _PRIOR_RUNTIME_WORKFLOW_SHA,
                             "91b7a372429014f791c731aabb2adcb017a41f16",
                             "d7b4f066d75b00b29dfdc10c768641e3e6d9c93b",
                             "822578a948aa83e972b572121958343eefe5c1d0",
                             "084542245fba5fca34be4ad52e8113ac3f701f16",
                             "cec458a479c0556d39aa6a75b18311500ce66d71",
                             "b4148a6320d3dfe8bfb556c6327937c6b304cf4c",
                             "9be996a3269c324ad1beae37a06ff65219e69806",
                             "8a1c2a0c9a9ee1f3c5629d2d77278580f48a489c")):
        try:
            _require_ci_workflow_reference(run,
                f"codex-agent-labs/codex-agent/.github/workflows/product-validation.yml@{sha}", sha)
            return sha
        except ValueError:
            continue
    return None


def _matching_ci_jobs(jobs, name, *, expected_build_key=None):
    names = {name}
    if expected_build_key is not None:
        require_sha256(expected_build_key, "Caller-pinned SDK worker build key")
        names.add(f"{name} ({expected_build_key}, ...")
    matrix_name = re.compile(
        re.escape(name) + r" \(contracts, (?:true|false), (?:true|false), (?:true|false)\)"
    ) if name in {
        "product-validation / product-contracts",
        "product-validation / contract-validation / product-contracts",
    } else None
    return [job for job in jobs if job.get("name") in names or (
        matrix_name is not None and type(job.get("name")) is str
        and matrix_name.fullmatch(job["name"]) is not None
    )]


def _observe_ci_producer_jobs(
    producers, *, jobs_by_phase, token, trusted_workflow_sha=None,
    trusted_workflows_by_phase=None, allow_protected_dispatch=False,
    dispatch_authorization_job="product-validation / dispatch-authorization",
) -> list[dict[str, Any]]:
    # Callers choose fixed jobs and workflow references; transported data selects neither.
    require_exact_keys(producers, set(jobs_by_phase), "Contract phase producers")
    for phase, job in jobs_by_phase.items():
        if type(job) is not str or not job:
            raise ValueError(f"Contract {phase} producer job must be caller-pinned text")
    if (trusted_workflow_sha is None) == (trusted_workflows_by_phase is None):
        raise ValueError("Contract producer admission requires exactly one caller-owned workflow policy")
    if dispatch_authorization_job is None:
        if not allow_protected_dispatch or trusted_workflows_by_phase is None:
            raise ValueError("Protected dispatch without the validation authorization job requires exact child workflow pins")
    elif type(dispatch_authorization_job) is not str or not dispatch_authorization_job:
        raise ValueError("Dispatch authorization job must be pinned text")
    repository = "codex-agent-labs/codex-agent"
    if trusted_workflows_by_phase is None:
        trusted_workflows_by_phase = {phase: {
            "path": ".github/workflows/product-validation.yml", "sha": trusted_workflow_sha,
        } for phase in jobs_by_phase}
    require_exact_keys(trusted_workflows_by_phase, set(jobs_by_phase), "Contract trusted workflow phases")
    workflows = {}
    for phase, policy in trusted_workflows_by_phase.items():
        require_exact_keys(policy, {"path", "sha"}, f"Contract {phase} trusted workflow")
        path, sha = policy["path"], policy["sha"]
        if (not isinstance(path, str) or re.fullmatch(r"\.github/workflows/[a-z0-9-]+\.yml", path) is None
                or not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{40}", sha) is None):
            raise ValueError("Contract producer admission requires exact caller-pinned workflow paths and SHAs")
        workflows[phase] = f"{repository}/{path}@{sha}", sha
    attempts: dict[tuple[int, int], dict[str, Any]] = {}
    for phase in jobs_by_phase:
        producer = validate_producer(producers[phase], f"Contract {phase} producer")
        if (producer["repository"] != repository
                or producer["workflowPath"] != ".github/workflows/ci.yml"
                or producer["event"] not in ({"pull_request", "merge_group", "workflow_dispatch"}
                    if allow_protected_dispatch else {"pull_request", "merge_group"})):
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
        # A completed original uploader, checked below, is authoritative; the
        # enclosing run status can briefly regress while new jobs are queued.
        if (require_integer(run.get("id"), "Contract original CI run ID", 1) != run_id
                or require_integer(run.get("run_attempt"), "Contract original CI attempt", 1) != attempt
                or run.get("path") != producer["workflowPath"]
                or run.get("event") != producer["event"]
                or any(not isinstance(run.get(field), dict)
                       or run[field].get("full_name") != repository
                       or run[field].get("fork") is not False
                       for field in ("repository", "head_repository"))
                or producer["event"] == "pull_request" and not run_matches_pr(run, producer["pullRequest"])):
            raise ValueError("Contract original CI attempt does not match its producer")
        for phase in original["phases"]:
            workflow, sha = workflows[phase]
            _require_ci_workflow_reference(run, workflow, sha)
        commit = _observe_tested_commit(
            run, api="https://api.github.com", repository=repository, token=token,
            expected_commit=producer["commit"], expected_tree=producer["tree"],
            pull_request=producer["pullRequest"], allow_dispatch=allow_protected_dispatch)
        jobs = paginated_items(f"{url}/jobs", "jobs", token)
        if any(not isinstance(job, dict) for job in jobs):
            raise ValueError("Contract original CI jobs are malformed")
        names = {jobs_by_phase[phase] for phase in original["phases"]}
        if producer["event"] == "workflow_dispatch" and dispatch_authorization_job is not None:
            names.add(dispatch_authorization_job)
        for name in sorted(names):
            selected_jobs = _matching_ci_jobs(jobs, name)
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


def _require_artifact_job_window(observation, job_name, artifact):
    """Bind an upload to its observed original attempt, never just its run."""
    jobs = _matching_ci_jobs(observation["jobs"], job_name)
    if len(jobs) != 1:
        raise ValueError("Upload producer job is missing or ambiguous")
    job = jobs[0]
    timestamps = [datetime.fromisoformat(require_string(value, "Original upload timestamp").replace("Z", "+00:00"))
                  for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
    if any(value.utcoffset() != timedelta(0) for value in timestamps) or not timestamps[0] <= timestamps[1] <= timestamps[2]:
        raise ValueError("Upload is outside its original job-attempt window")


@verification_scoped
def _download_contract_ci_upload(
    artifact_id: int, artifact_sha256: str, expected_name: str,
    producer: Mapping[str, Any], observed_run: Mapping[str, Any], token: str,
    *, destination: Path | None = None, max_bytes: int | None = None,
) -> tuple[dict[str, Any], bytes | Path]:
    artifact = _contract_ci_upload_metadata(artifact_id, artifact_sha256, expected_name,
        producer, observed_run, token)
    size = require_integer(artifact.get("size_in_bytes"), "Contract upload transport bytes", 1)
    limit = _CATALOG_LIMIT if destination is not None else _INLINE_UPLOAD_LIMIT
    if max_bytes is not None:
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Contract upload transport limit must be positive")
        limit = min(limit, max_bytes)
    if size > limit:
        raise ValueError("Contract uploaded artifact exceeds the transport limit")
    return _reuse_contract_ci_upload(artifact, producer, observed_run, token,
        destination=destination, limit=limit, artifact_sha256=artifact_sha256, size=size)


def _contract_ci_upload_metadata(artifact_id, artifact_sha256, expected_name, producer, observed_run, token):
    """Fresh source authentication, distinct from verifying selected body bytes."""
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
    return artifact


def _reuse_contract_ci_upload(artifact, producer, observed_run, token, *, destination, limit,
                              artifact_sha256, size):
    # Metadata and original-job authentication are mandatory on every call.
    # Only fully hashed private bytes are reused; this is never an admission.
    with verification_session() as session:
        if artifact["name"].startswith(("codex-agent-runtime-worker-", "codex-agent-runtime-aggregate-release-handoff-")):
            with session["lock"]:
                session["runtimeColdArchiveBytes"] = session.get("runtimeColdArchiveBytes", 0) + size
        provenance = canonical_json_bytes({
            "producer": dict(producer),
            "run": {name: observed_run.get(name) for name in
                    ("id", "run_attempt", "head_sha", "path", "event", "referenced_workflows")},
            "artifact": {name: artifact.get(name) for name in
                         ("id", "name", "digest", "size_in_bytes", "created_at", "workflow_run")},
        })
        cached = session["uploads"].get(provenance)
        if cached is not None:
            raw = cached
            if destination is not None:
                # Exact immutable bytes; no re-download or mutable disk marker.
                with destination.open("xb") as output:
                    output.write(raw)
                if sha256_file(destination) != artifact_sha256:
                    raise ValueError("Cached Contract upload copy differs from its immutable identity")
                return artifact, destination
            return artifact, raw
        result = _download_contract_ci_upload_bytes(artifact, token, destination, limit, artifact_sha256, size)
        # ponytail: small immutable uploads only; larger transport stays streamed.
        if destination is None and type(result[1]) is bytes and size <= 64 * 1024 * 1024:
            with session["lock"]:
                if (session["bytes"] + size <= session["limit"]
                        and session["uploadBytes"] + size <= 256 * 1024 * 1024):
                    session["uploads"][provenance] = result[1]
                    session["bytes"] += size
                    session["uploadBytes"] += size
        return result


def _download_contract_ci_upload_bytes(artifact, token, destination, limit, artifact_sha256, size):
    if destination is not None:
        download_artifact_to_file(artifact, token, destination, max_bytes=limit)
        if destination.stat().st_size != size or sha256_file(destination) != artifact_sha256:
            raise ValueError("Contract uploaded artifact bytes differ from the caller-bound identity")
        body = destination
    else:
        body = download_artifact(artifact, token)
        if len(body) != size or sha256_bytes(body) != artifact_sha256:
            raise ValueError("Contract uploaded artifact bytes differ from the caller-bound identity")
    from products.restore import _VERIFICATION_SESSION
    session = _VERIFICATION_SESSION.get()
    if session is not None:
        with session["lock"]:
            session["downloadedArtifactBytes"] = session.get("downloadedArtifactBytes", 0) + size
            session["downloadedArtifactCount"] = session.get("downloadedArtifactCount", 0) + 1
    return artifact, body


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
    trusted_workflow_path: str | None = None, trusted_job_name: str | None = None,
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
    if (trusted_workflow_path is None) != (trusted_job_name is None):
        raise ValueError("Contract CI workflow path and job must be pinned together")
    selected_job = "product-validation / contract-continuation" if trusted_job_name is None else trusted_job_name
    policy = ({"trusted_workflow_sha": trusted_workflow_sha} if trusted_workflow_path is None else
              {"trusted_workflows_by_phase": {"metadata": {
                  "path": trusted_workflow_path, "sha": trusted_workflow_sha,
              }}, "jobs_by_phase": {"metadata": selected_job}})
    observed = _observe_contract_producer_runs(
        {"metadata": transport_producer}, phases=("metadata",),
        token=token, **policy)
    artifact, raw = _download_contract_ci_upload(
        artifact_id, artifact_sha256,
        f"codex-agent-contract-attestation-inputs-{transport_producer['tree']}",
        transport_producer, observed[0]["run"], token)
    _require_artifact_job_window(observed[0], selected_job, artifact)
    with tempfile.TemporaryDirectory(prefix="contract-ci-capture-") as temporary:
        root = Path(temporary).resolve()
        archive = root / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
        prepared = root / "captured"
        safe_extract(archive, prepared)
        if regular_file_inventory(prepared) != zipped:
            raise ValueError("Contract CI extraction differs from its exact original archive")
        _verify_contract_ci_capture(prepared, contract_version)
        evidence = {"artifact": artifact, "captureProducer": dict(transport_producer), "observed": observed}
        write_canonical_json(prepared / "transport/ci-artifact.json", evidence)
        evidence_bytes = canonical_json_bytes(evidence)
        expected_files = sorted([
            *zipped,
            {"relativePath": "transport/ci-artifact.json", "bytes": len(evidence_bytes),
             "sha256": sha256_bytes(evidence_bytes)},
        ], key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared) != expected_files:
            raise ValueError("Contract CI capture changed before publication")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return evidence


@verification_scoped
def capture_contract_original_ci_phases(
    capture_root: Path, destination: Path, *, contract_version: str,
    trusted_workflow_sha: str, token: str,
    release_handoffs: tuple[Path, ...] = (), keyring: Path | None = None,
    keys_directory: Path | None = None,
    trusted_workflows_by_phase: Mapping[str, Any] | None = None,
    jobs_by_phase: Mapping[str, str] | None = None,
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
        capture_files = regular_file_inventory(source)
        snapshot_regular_tree(source, capture)
        if regular_file_inventory(capture) != capture_files:
            raise ValueError("Original Contract capture changed during source copy")
        _verify_contract_ci_capture(capture, contract_version, with_transport=True)
        originals = {phase: read_regular_file_bytes(capture / f"execution-closure/receipts/{phase}.json",
                     max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) for phase in phases}
        producers = {phase: load_canonical_json_bytes(raw)["producer"] for phase, raw in originals.items()}
        releases = {}
        release_files = {}
        policy_files = []
        if release_handoffs:
            policy = prepared / "release-policy"
            policy.mkdir()
            captured_keyring = policy / "keyring.json"
            keyring_bytes = read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
            captured_keyring.write_bytes(keyring_bytes)
            policy_files = [{"relativePath": "keyring.json", "bytes": len(keyring_bytes),
                             "sha256": sha256_bytes(keyring_bytes)}]
            captured_keys = policy / "keys"
            captured_keys.mkdir()
            public_policy = load_keyring(captured_keyring, keys_directory)
            for record in ([public_policy["activeKey"]] if public_policy["activeKey"] else []) + public_policy["retiredKeys"]:
                key_id = record["keyId"]
                public_bytes = read_regular_file_bytes(public_key_path(keys_directory, key_id),
                                                       max_bytes=1024 * 1024, reject_symlink_parents=True)
                (captured_keys / f"{key_id}.pub").write_bytes(public_bytes)
                policy_files.append({"relativePath": f"keys/{key_id}.pub", "bytes": len(public_bytes),
                                     "sha256": sha256_bytes(public_bytes)})
            policy_files.sort(key=lambda value: value["relativePath"])
            if regular_file_inventory(policy) != policy_files:
                raise ValueError("Contract release policy differs from caller-owned bytes")
            load_keyring(captured_keyring, captured_keys)
            if regular_file_inventory(policy) != policy_files:
                raise ValueError("Contract release policy differs from caller-owned bytes")
            for number, original in enumerate(release_handoffs):
                retained = prepared / "release-handoffs" / str(number)
                release_files[number] = regular_file_inventory(original)
                snapshot_regular_tree(original, retained)
                if regular_file_inventory(retained) != release_files[number]:
                    raise ValueError("Retained Contract handoff changed during source copy")
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
        if (trusted_workflows_by_phase is None) != (jobs_by_phase is None):
            raise ValueError("Contract original workflow paths and jobs must be pinned together")
        if trusted_workflows_by_phase is None:
            policy = {"trusted_workflow_sha": trusted_workflow_sha}
            selected_jobs = {phase: "product-validation / product-contracts" if phase == "binary"
                             else "product-validation / contract-continuation" for phase in ci_phases}
        else:
            require_exact_keys(trusted_workflows_by_phase, set(phases), "Contract original workflow phases")
            require_exact_keys(jobs_by_phase, set(phases), "Contract original workflow jobs")
            policy = {"trusted_workflows_by_phase": {
                phase: trusted_workflows_by_phase[phase] for phase in ci_phases
            }, "jobs_by_phase": {phase: jobs_by_phase[phase] for phase in ci_phases}}
            selected_jobs = jobs_by_phase
        observed = _observe_contract_producer_runs(
            {phase: producers[phase] for phase in ci_phases}, phases=ci_phases,
            token=token, **policy)
        attempts = {(value["run"]["id"], value["run"]["run_attempt"]): value for value in observed}
        inventories, artifacts, shard_files = {}, {}, {}
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
            job_name = selected_jobs[phase]
            _require_artifact_job_window(attempt, job_name, artifact)
            archive = root / f"{phase}.zip"
            archive.write_bytes(raw)
            zipped, _, _ = verified_zip_contents(archive, retained_paths=(), **_CATALOG_ZIP_LIMITS)
            shard = prepared / "original-phases" / phase
            safe_extract(archive, shard)
            if regular_file_inventory(shard) != zipped:
                raise ValueError("Original Contract phase differs from its exact upload")
            verified = verify_phase_shard(shard, PhaseInstanceId("contract", "contract", phase, "common"))
            if verified["receiptBytes"] != originals[phase]:
                raise ValueError(f"Original Contract {phase} upload differs from the retained phase receipt")
            artifacts[phase] = artifact
            shard_files[phase] = zipped
        evidence = {"observed": observed, "artifacts": artifacts,
                    "receiptSha256s": {phase: sha256_bytes(raw) for phase, raw in originals.items()}}
        if release_handoffs:
            evidence["releaseAttestations"] = releases
        write_canonical_json(prepared / "transport/original-ci-phases.json", evidence)
        evidence_bytes = canonical_json_bytes(evidence)
        expected_files = [
            *({**record, "relativePath": f"contract-input/{record['relativePath']}"} for record in capture_files),
            *({**record, "relativePath": f"release-policy/{record['relativePath']}"} for record in policy_files),
            *({**record, "relativePath": f"release-handoffs/{number}/{record['relativePath']}"}
              for number, records in release_files.items() for record in records),
            *({**record, "relativePath": f"original-phases/{phase}/{record['relativePath']}"}
              for phase, records in shard_files.items() for record in records),
            {"relativePath": "transport/original-ci-phases.json", "bytes": len(evidence_bytes),
             "sha256": sha256_bytes(evidence_bytes)},
        ]
        expected_files.sort(key=lambda record: record["relativePath"])
        if (regular_file_inventory(source) != capture_files
                or any(regular_file_inventory(original) != release_files[number]
                       for number, original in enumerate(release_handoffs))
                or regular_file_inventory(prepared) != expected_files):
            raise ValueError("Original Contract capture changed before publication")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return evidence


def _extract_runtime_original_projection(archive, zipped, destination):
    """Full archive authentication is already complete; copy only consumed bytes."""
    from products.inventory import _open_regular_file
    from products.restore import _stat_identity
    from runtime_reference_archive import copy_reference_member
    descriptor, before = _open_regular_file(archive, "Authenticated original Runtime archive",
                                            reject_symlink_parents=True)
    projected = [row for row in zipped if not row["relativePath"].startswith("inputs/")]
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as source, zipfile.ZipFile(source) as original:
            for row in projected:
                copy_reference_member(original, row["relativePath"], destination / row["relativePath"], row)
        if (_stat_identity(before) != _stat_identity(os.fstat(descriptor))
                or regular_file_inventory(destination, allow_empty=True) != projected):
            raise ValueError("Original Runtime projection changed during extraction")
    finally:
        os.close(descriptor)


@verification_scoped
def capture_runtime_original_ci_phases(
    phase_receipts: Mapping[str, Path], destination: Path, *, target: str,
    trusted_workflow_sha: str, token: str,
    release_handoffs: tuple[Path, ...] = (), keyring: Path | None = None,
    keys_directory: Path | None = None,
    original_instance: PhaseInstanceId | None = None,
    recovery_projection: bool = False,
    original_archives: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Bind original receipts to CI or retained release trust, never new signing."""
    if bool(release_handoffs) != (keyring is not None and keys_directory is not None) or \
            (keyring is None) != (keys_directory is None):
        raise ValueError("Retained Runtime handoffs require caller-owned keyring and keys only")
    all_phases = ("binary", "package", "validation", "metadata")
    phases = tuple(phase for phase in all_phases if phase in phase_receipts)
    if not phases or release_handoffs and phases != all_phases:
        raise ValueError("Original Runtime phases must be nonempty; release requires all four")
    require_exact_keys(phase_receipts, set(phases), "Original Runtime phase receipts")
    if (target not in _RECOVERABLE_RUNTIME_COMPONENTS or release_handoffs and target not in NATIVE_TARGETS
            or target == "runtime-aggregate" and original_instance != PhaseInstanceId(
                "runtime", "runtime-aggregate", "metadata", "aggregate")):
        raise ValueError("Original Runtime capture requires a supported component")
    instances = {phase: PhaseInstanceId("runtime", target, phase, target) for phase in phases}
    if original_instance is not None:
        if (len(phases) != 1 or original_instance.product != "runtime"
                or original_instance.component != target or original_instance.phase != phases[0]
                or original_instance not in PHASE_INSTANCE_IDS):
            raise ValueError("Original Runtime phase override has the wrong identity")
        instances[phases[0]] = original_instance
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Original Runtime CI destination must not exist")
    resolved_output = destination.parent.resolve(strict=False) / destination.name
    for source in (*release_handoffs, *(path for path in (keyring, keys_directory) if path is not None)):
        resolved_source = Path(source).resolve(strict=True)
        if resolved_source == resolved_output or resolved_source in resolved_output.parents or resolved_output in resolved_source.parents:
            raise ValueError("Original Runtime CI destination overlaps release evidence or policy")
    originals, receipts = {}, {}
    for phase in phases:
        source = Path(phase_receipts[phase])
        resolved_source = source.resolve(strict=True)
        if resolved_source == resolved_output or resolved_output in resolved_source.parents:
            raise ValueError("Original Runtime CI destination overlaps an input")
        raw = read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        if _identity(receipt) != instances[phase]:
            raise ValueError("Original Runtime receipt has the wrong phase identity")
        originals[phase], receipts[phase] = raw, receipt
    with tempfile.TemporaryDirectory(prefix="runtime-original-ci-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "captured"
        releases = {}
        release_files = {}
        policy_files = []
        if release_handoffs:
            from products.runtime_attestation import read_runtime_variant_handoff
            policy = prepared / "release-policy"
            policy.mkdir(parents=True)
            captured_keyring = policy / "keyring.json"
            keyring_bytes = read_regular_file_bytes(keyring, max_bytes=16 * 1024 * 1024,
                                                    reject_symlink_parents=True)
            captured_keyring.write_bytes(keyring_bytes)
            policy_files = [{"relativePath": "keyring.json", "bytes": len(keyring_bytes),
                             "sha256": sha256_bytes(keyring_bytes)}]
            captured_keys = policy / "keys"
            captured_keys.mkdir()
            public_policy = load_keyring(captured_keyring, keys_directory)
            for record in ([public_policy["activeKey"]] if public_policy["activeKey"] else []) + public_policy["retiredKeys"]:
                key_id = record["keyId"]
                public_bytes = read_regular_file_bytes(public_key_path(keys_directory, key_id),
                                                       max_bytes=1024 * 1024, reject_symlink_parents=True)
                (captured_keys / f"{key_id}.pub").write_bytes(public_bytes)
                policy_files.append({"relativePath": f"keys/{key_id}.pub", "bytes": len(public_bytes),
                                     "sha256": sha256_bytes(public_bytes)})
            policy_files.sort(key=lambda value: value["relativePath"])
            if regular_file_inventory(policy) != policy_files:
                raise ValueError("Runtime release policy differs from caller-owned bytes")
            load_keyring(captured_keyring, captured_keys)
            if regular_file_inventory(policy) != policy_files:
                raise ValueError("Runtime release policy differs from caller-owned bytes")
            for number, original in enumerate(release_handoffs):
                retained = prepared / "release-handoffs" / str(number)
                release_files[number] = regular_file_inventory(original, allow_empty=True)
                snapshot_regular_tree(original, retained)
                if regular_file_inventory(retained, allow_empty=True) != release_files[number]:
                    raise ValueError("Retained Runtime handoff changed during source copy")
                verified = read_runtime_variant_handoff(retained, target=target,
                    keyring=captured_keyring, keys_directory=captured_keys)
                matching = [phase for phase in phases if verified["receiptBytes"][phase] == originals[phase]]
                if not matching:
                    raise ValueError("Retained Runtime handoff proves no requested original phase")
                for phase in matching:
                    releases.setdefault(phase, number)
        ci_phases = tuple(phase for phase in phases if phase not in releases)
        if ci_phases and (type(token) is not str or not token):
            raise ValueError("Original Runtime CI observation requires a token for uncovered phases")
        jobs = {phase: f"product-validation / runtime-{target}-{phase}-{instances[phase].target}"
                for phase in ci_phases}
        original_workflows, workflow_policies = {}, {}
        for phase in ci_phases:
            producer = receipts[phase]["producer"]
            identity = producer["runId"], producer["runAttempt"]
            if identity not in original_workflows:
                original_run = api_json(
                    f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/"
                    f"{identity[0]}/attempts/{identity[1]}", token)
                original_workflows[identity] = _runtime_prior_workflow_sha(original_run, trusted_workflow_sha)
            original_sha = original_workflows[identity]
            if original_sha is None:
                raise ValueError("Original Runtime phase lacks a reviewed producer workflow")
            workflow_policies[phase] = {"path": ".github/workflows/product-validation.yml", "sha": original_sha}
        observed = _observe_ci_producer_jobs(
            {phase: receipts[phase]["producer"] for phase in ci_phases}, jobs_by_phase=jobs,
            trusted_workflows_by_phase=workflow_policies, token=token)
        attempts = {(value["run"]["id"], value["run"]["run_attempt"]): value for value in observed}
        inventories, artifacts, phase_files, original_files = {}, {}, {}, {}
        completed_originals = []
        pending_original_bytes = pending_original_members = 0
        for phase in ci_phases:
            receipt = receipts[phase]
            producer = receipt["producer"]
            run_id = producer["runId"]
            if run_id not in inventories:
                inventories[run_id] = paginated_items(
                    f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{run_id}/artifacts",
                    "artifacts", token)
            name = (f"codex-agent-runtime-worker-{target}-{phase}-{instances[phase].target}-"
                    f"{receipt['buildKey'].removeprefix('sha256:')}-{producer['tree']}-attempt-{producer['runAttempt']}")
            candidates = [item for item in inventories[run_id] if isinstance(item, dict) and item.get("name") == name]
            if len(candidates) != 1:
                raise ValueError("Original Runtime upload is missing or ambiguous")
            attempt = attempts[(run_id, producer["runAttempt"])]
            candidate = candidates[0]
            artifact = _contract_ci_upload_metadata(
                candidate.get("id"), candidate.get("digest"), name, producer, attempt["run"], token)
            job = next(value for value in attempt["jobs"] if value.get("name") == jobs[phase])
            timestamps = [datetime.fromisoformat(require_string(value, "Original Runtime CI timestamp").replace("Z", "+00:00"))
                          for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
            if any(value.utcoffset() != timedelta(0) for value in timestamps) or not timestamps[0] <= timestamps[1] <= timestamps[2]:
                raise ValueError("Original Runtime upload is outside its original job-attempt window")
            from products.verified_evidence import runtime_original_cache
            persistent = runtime_original_cache() if recovery_projection else None
            from products.restore import _is_windows, _stage_fingerprint
            session = None
            if recovery_projection and not _is_windows():
                # The enclosing public operation owns this session. There is no
                # serialized memo or external cache marker to accept as trust.
                from products.restore import _VERIFICATION_SESSION
                session = _VERIFICATION_SESSION.get()
            cache_key = canonical_json_bytes({"receiptSha256": sha256_bytes(originals[phase]),
                "workflow": workflow_policies[phase],
                "origin": _runtime_capture_identity({"observed": [attempt], "artifacts": {phase: artifact}},
                                                     instances[phase])})
            memo = session.setdefault("originalCaptures", {}) if session is not None else {}
            cached = memo.get(cache_key)
            if cached is not None and not cached[0].exists() and not cached[0].is_symlink():
                # A containing temporary operation may have ended. Missing
                # custody is a cache miss; replaced existing custody fails below.
                del memo[cache_key]
                cached = None
            if cached is not None:
                source, fingerprint, zipped_bytes, object_sha256 = cached
                if _stage_fingerprint(source) != fingerprint:
                    raise ValueError("Private verified original Runtime capture changed")
                zipped = load_canonical_json_bytes(zipped_bytes)
                projected = [record for record in zipped if not record["relativePath"].startswith("inputs/")]
                projected_root = prepared / "phases" / phase / "original"
                snapshot_regular_tree(source, projected_root, allow_empty=True)
                if (_stage_fingerprint(source) != fingerprint
                        or regular_file_inventory(projected_root, allow_empty=True) != projected
                        or _canonical_control(projected_root / "shard" / PHASE_SHARD_NAME,
                            "Reused original Runtime shard")["objectSha256"] != object_sha256):
                    raise ValueError("Reused original Runtime capture differs from its immutable identity")
                original_files[phase] = zipped
                artifacts[phase] = artifact
                phase_files[phase] = [{**record, "relativePath": f"phases/{phase}/original/{record['relativePath']}"}
                                     for record in projected]
                continue
            locator = _runtime_original_locator(artifact, workflow_policies[phase]["sha"], instances[phase], job)
            completed = persistent.read(locator) if persistent is not None else None
            retained = (root / "original-uploads" if recovery_projection else prepared) / "phases" / phase
            retained.mkdir(parents=True)
            archive = retained / "transport.zip"
            candidate = None
            qualified_projection = False
            if completed is None and session is not None:
                # Only this process's freshly authenticated reference envelope
                # can supply a projection. No restored marker is admission.
                qualified = _qualified_original_projection(locator)
                if qualified is not None:
                    source, fingerprint, zipped, policy = qualified
                    candidate = source, fingerprint, zipped
                    qualified_projection = True
            if completed is None and session is not None and original_archives is not None and phase in original_archives:
                candidate_key = (str(original_archives[phase].resolve()), artifact["id"], artifact["digest"],
                    sha256_bytes(originals[phase]), workflow_policies[phase]["sha"], canonical_json_bytes(producer))
                if candidate is None:
                    candidate = session.setdefault("runtimeCandidates", {}).pop(candidate_key, None)
            if completed is not None:
                if canonical_json_bytes(completed["receipt"]) != originals[phase]:
                    raise ValueError("Cached original Runtime receipt/provenance differs from the requested original")
                original = prepared / "phases" / phase / "original"
                persistent.materialize(completed, original)
                zipped = completed["originalFiles"]
            elif candidate is not None:
                original, fingerprint, zipped = candidate
                if _stage_fingerprint(original.parent) != fingerprint:
                    raise ValueError("Private verified Runtime upload candidate changed")
            elif original_archives is not None and phase in original_archives:
                # The candidate bytes are rehashed against this freshly observed
                # official upload. Preserve the full authentication gate while
                # avoiding its immediate second network download.
                from runtime_reference_transport import _copy_exact
                _copy_exact(original_archives[phase], archive, {"bytes": artifact["size_in_bytes"],
                                                               "sha256": artifact["digest"]})
            elif artifact["size_in_bytes"] > 64 * 1024 * 1024:
                _reuse_contract_ci_upload(artifact, producer, attempt["run"], token, destination=archive,
                    limit=_CATALOG_LIMIT, artifact_sha256=artifact["digest"], size=artifact["size_in_bytes"])
            else:
                _, raw = _reuse_contract_ci_upload(artifact, producer, attempt["run"], token, destination=None,
                    limit=_INLINE_UPLOAD_LIMIT, artifact_sha256=artifact["digest"], size=artifact["size_in_bytes"])
                archive.write_bytes(raw)
            if candidate is None and completed is None:
                zipped, _, archive_verified = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                if archive_verified != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}:
                    raise ValueError("Original Runtime archive changed after full source authentication")
                original = retained / "original"
                if recovery_projection:
                    _extract_runtime_original_projection(archive, zipped, original)
                else:
                    safe_extract(archive, original)
                    if regular_file_inventory(original, allow_empty=True) != zipped:
                        raise ValueError("Original Runtime phase differs from its exact upload")
            verified = verify_phase_shard(original / "shard", instances[phase])
            if verified["receiptBytes"] != originals[phase]:
                raise ValueError("Original Runtime upload differs from the requested original receipt")
            if completed is not None and verified["objectSha256"] != completed["objectSha256"]:
                raise ValueError("Cached original Runtime object differs from completed verification")
            if recovery_projection:
                # Full original upload authentication precedes this transport-only
                # projection. Receipts/objects/raw proof stay byte-identical;
                # duplicated predecessor inputs and enclosing ZIP stay upstream.
                original_files[phase] = zipped
                projected = [record for record in zipped
                             if not record["relativePath"].startswith("inputs/")]
                projected_root = prepared / "phases" / phase / "original"
                for record in ([] if completed is not None else projected):
                    output = projected_root / record["relativePath"]
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(original / record["relativePath"], output)
                if regular_file_inventory(projected_root, allow_empty=True) != projected:
                    raise ValueError("Original Runtime recovery projection changed during copy")
                if persistent is not None and completed is None and not qualified_projection:
                    persistent.record_verified(locator, projected_root, zipped, verified["receipt"],
                                               verified["objectSha256"])
                if candidate is not None and _stage_fingerprint(original.parent) != fingerprint:
                    raise ValueError("Private verified Runtime upload candidate changed during projection")
                if session is not None:
                    zipped_bytes = canonical_json_bytes(zipped)
                    metadata_bytes = len(zipped_bytes) + len(cache_key)
                    members = len(_stage_fingerprint(projected_root))
                    if (session["bytes"] + pending_original_bytes + metadata_bytes <= session["limit"]
                            and session.get("originalCaptureMembers", 0) + pending_original_members + members <= 65_536):
                        completed_originals.append((cache_key, phase, zipped_bytes,
                                                    verified["objectSha256"], members))
                        pending_original_bytes += metadata_bytes
                        pending_original_members += members
            artifacts[phase] = artifact
            phase_files[phase] = [
                *([] if recovery_projection else [{"relativePath": f"phases/{phase}/transport.zip",
                    "bytes": archive.stat().st_size, "sha256": artifact["digest"]}]),
                *({**record, "relativePath": f"phases/{phase}/original/{record['relativePath']}"}
                  for record in (projected if recovery_projection else zipped)),
            ]
        evidence = {"target": target, "observed": observed, "artifacts": artifacts,
                    "receiptSha256s": {phase: sha256_bytes(raw) for phase, raw in originals.items()}}
        if release_handoffs:
            evidence["releaseAttestations"] = releases
        if recovery_projection:
            evidence["recoveryProjection"] = {"schemaVersion": 1, "originalFiles": original_files}
        write_canonical_json(prepared / "transport/original-ci-phases.json", evidence)
        evidence_bytes = canonical_json_bytes(evidence)
        expected_files = [
            *({**record, "relativePath": f"release-policy/{record['relativePath']}"} for record in policy_files),
            *({**record, "relativePath": f"release-handoffs/{number}/{record['relativePath']}"}
              for number, records in release_files.items() for record in records),
            *(record for records in phase_files.values() for record in records),
            {"relativePath": "transport/original-ci-phases.json", "bytes": len(evidence_bytes),
             "sha256": sha256_bytes(evidence_bytes)},
        ]
        expected_files.sort(key=lambda record: record["relativePath"])
        if (any(read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != originals[phase]
                for phase, path in phase_receipts.items())
                or any(regular_file_inventory(original, allow_empty=True) != release_files[number]
                       for number, original in enumerate(release_handoffs))
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("Original Runtime capture changed before publication")
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
        if completed_originals:
            for cache_key, phase, zipped_bytes, object_sha, members in completed_originals:
                # ponytail: cache metadata over verified published custody, not
                # another multi-GB copy. Every hit still authenticates original CI.
                source = destination / "phases" / phase / "original"
                fingerprint = _stage_fingerprint(source)
                projected = [row for row in load_canonical_json_bytes(zipped_bytes)
                             if not row["relativePath"].startswith("inputs/")]
                if (regular_file_inventory(source, allow_empty=True) != projected
                        or _stage_fingerprint(source) != fingerprint):
                    raise ValueError("Published original Runtime custody changed before verification caching")
                memo[cache_key] = (source, fingerprint, zipped_bytes, object_sha)
                session["bytes"] += len(zipped_bytes) + len(cache_key)
                session["originalCaptureMembers"] = session.get("originalCaptureMembers", 0) + members
    return evidence


def _runtime_original_locator(artifact, workflow_sha, instance, job):
    """Fresh authenticated upload/workflow/job locator, before consulting cache."""
    return {"instance": _identity_record(instance), "workflowSha": workflow_sha,
            "artifact": {name: artifact.get(name) for name in
                ("id", "name", "digest", "size_in_bytes", "created_at", "workflow_run")},
            "job": {name: job.get(name) for name in
                ("id", "name", "run_id", "head_sha", "status", "conclusion", "started_at", "completed_at")}}


def _retarget_runtime_original_captures(source, destination):
    """Move private verification metadata only after an exact custody copy."""
    from products.restore import _VERIFICATION_SESSION, _stage_fingerprint
    session = _VERIFICATION_SESSION.get()
    if session is None:
        return
    source, destination = Path(source).resolve(), Path(destination).resolve()
    memo = session.get("originalCaptures", {})
    for key, (path, fingerprint, zipped_bytes, object_sha) in tuple(memo.items()):
        if not path.is_relative_to(source):
            continue
        target = destination / path.relative_to(source)
        target_fingerprint = _stage_fingerprint(target)
        if (_stage_fingerprint(path) != fingerprint
                or regular_file_inventory(path, allow_empty=True) !=
                   regular_file_inventory(target, allow_empty=True)
                or _stage_fingerprint(path) != fingerprint
                or _stage_fingerprint(target) != target_fingerprint):
            raise ValueError("Private original Runtime custody changed during publication")
        memo[key] = (target, target_fingerprint, zipped_bytes, object_sha)


@verification_scoped
def capture_prior_failed_runtime_phases(
    plan: Mapping[str, Any], producer: Mapping[str, Any],
    requested: Mapping[PhaseInstanceId, str], destination: Path,
    *, trusted_workflow_sha: str, token: str,
    attempts: tuple[dict[str, Any], ...] | None = None,
    artifacts_by_run: dict[int, list[Any]] | None = None,
    jobs_by_attempt: dict[tuple[int, int], list[Any]] | None = None,
) -> dict[PhaseInstanceId, dict[str, Any]]:
    """Recover exact-key successful native phases from independently authenticated PR attempts."""
    if not requested:
        return {}
    if (plan["event"] != "pull_request" or plan["repository"] != "codex-agent-labs/codex-agent"
            or plan["pullRequest"] is None):
        raise ValueError("Prior Runtime recovery requires the canonical PR")
    destination = Path(destination)
    if destination.exists():
        require_regular_directory(destination, "Prior Runtime capture destination")
    elif destination.is_symlink():
        raise ValueError("Prior Runtime capture destination is unsafe")
    attempts = attempts if attempts is not None else _prior_failed_pr_attempts(plan, producer, token)
    artifacts_by_run = artifacts_by_run if artifacts_by_run is not None else {}
    jobs_by_attempt = jobs_by_attempt if jobs_by_attempt is not None else {}
    current_run = require_integer(producer["runId"], "Current Runtime run ID", 1)
    current_attempt = require_integer(producer["runAttempt"], "Current Runtime attempt", 1)
    captured = {}
    with tempfile.TemporaryDirectory(prefix="runtime-pr-recovery-") as temporary:
        scratch_root = Path(temporary).resolve()
        for instance, build_key in sorted(requested.items()):
            if (instance.product != "runtime" or instance.component not in _RECOVERABLE_RUNTIME_COMPONENTS
                    or instance not in PHASE_INSTANCE_IDS):
                raise ValueError("Prior Runtime recovery has an invalid phase identity")
            require_sha256(build_key, "Prior Runtime exact build key")
            output = destination / instance.component / instance.phase / instance.target
            if output.exists() or output.is_symlink():
                raise ValueError("Prior Runtime phase capture already exists")
            prefix = (f"codex-agent-runtime-worker-{instance.component}-{instance.phase}-"
                      f"{instance.target}-{build_key.removeprefix('sha256:')}-")
            found = []
            for prior in attempts:
                run_id = require_integer(prior.get("id"), "Prior Runtime run ID", 1)
                attempt = require_integer(prior.get("run_attempt"), "Prior Runtime attempt", 1)
                if (run_id > current_run or run_id == current_run and attempt >= current_attempt
                        or prior.get("event") != "pull_request"
                        or prior.get("path") != ".github/workflows/ci.yml"
                        or prior.get("status") != "completed"
                        or prior.get("conclusion") not in {"failure", "cancelled"}
                        or not run_matches_pr(prior, plan["pullRequest"])
                        or any(not isinstance(prior.get(field), dict)
                               or prior[field].get("full_name") != plan["repository"]
                               or prior[field].get("fork") is not False
                               for field in ("repository", "head_repository"))):
                    raise ValueError("Prior Runtime candidate is not an earlier failed PR attempt")
                original_workflow_sha = _runtime_prior_workflow_sha(prior, trusted_workflow_sha)
                if original_workflow_sha is None:
                    continue  # A different reviewed workflow is not an admitted original producer.
                if run_id not in artifacts_by_run:
                    artifacts_by_run[run_id] = paginated_items(
                        f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{run_id}/artifacts",
                        "artifacts", token)
                suffix = f"-attempt-{attempt}"
                matching = [value for value in artifacts_by_run[run_id] if isinstance(value, dict)
                            and isinstance(value.get("name"), str)
                            and value["name"].startswith(prefix) and value["name"].endswith(suffix)]
                if len(matching) > 1:
                    raise ValueError("Prior Runtime exact-key phase upload is ambiguous")
                if not matching:
                    continue
                artifact = matching[0]
                if artifact.get("expired") is True:
                    continue
                if artifact.get("expired") is not False:
                    raise ValueError("Prior Runtime phase expiration state is malformed")
                key = (run_id, attempt)
                if key not in jobs_by_attempt:
                    jobs_by_attempt[key] = paginated_items(
                        f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{run_id}/attempts/{attempt}/jobs",
                        "jobs", token)
                job_name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
                jobs = _matching_ci_jobs(jobs_by_attempt[key], job_name)
                if len(jobs) != 1:
                    raise ValueError("Prior Runtime exact-key producer job is missing or ambiguous")
                job = jobs[0]
                require_integer(job.get("id"), "Prior Runtime phase job ID", 1)
                if (job.get("run_id") != run_id or job.get("head_sha") != prior.get("head_sha")
                        or job.get("status") != "completed"):
                    raise ValueError("Prior Runtime phase producer differs from its selected attempt")
                if job.get("conclusion") in {"failure", "cancelled", "skipped"}:
                    continue  # Partial diagnostic uploads are never reusable.
                if job.get("conclusion") != "success":
                    raise ValueError("Prior Runtime phase producer conclusion is invalid")
                name = artifact["name"]
                match = re.fullmatch(re.escape(prefix) + r"([0-9a-f]{40})" + re.escape(suffix), name)
                if match is None:
                    raise ValueError("Prior Runtime exact-key phase upload name is malformed")
                scratch = scratch_root / instance.component / instance.phase / instance.target / str(run_id) / str(attempt)
                scratch.mkdir(parents=True)
                archive = scratch / "transport.zip"
                artifact = _contract_ci_upload_metadata(artifact.get("id"), artifact.get("digest"), name,
                    {"runId": run_id}, prior, token)
                _require_artifact_job_window({"jobs": [job]}, job_name, artifact)
                from products.verified_evidence import runtime_original_cache
                persistent = runtime_original_cache()
                locator = _runtime_original_locator(artifact, original_workflow_sha, instance, job)
                completed = persistent.read(locator) if persistent is not None else None
                from products.restore import _stat_identity
                shard = scratch / "original/shard"
                qualified = _qualified_original_projection(locator) if completed is None else None
                if qualified is not None:
                    source, _fingerprint, zipped, _policy = qualified
                    verified = verify_phase_shard(source / "shard", instance)
                    receipt = verified["receipt"]
                    shard.mkdir(parents=True)
                    from runtime_reference_transport import _copy_exact
                    _copy_exact(source / "shard" / PHASE_RECEIPT_NAME, shard / PHASE_RECEIPT_NAME,
                          next(row for row in zipped if row["relativePath"] == "shard/" + PHASE_RECEIPT_NAME))
                elif completed is not None:
                    # Discovery needs only the previously authenticated receipt
                    # for collision comparison. Selected admission still reads
                    # and verifies the exact object/proof through the full caller.
                    member = next(row for row in completed["originalFiles"]
                                  if row["relativePath"] == "shard/" + PHASE_RECEIPT_NAME)
                    persistent.copy_member(completed, member["relativePath"], shard / PHASE_RECEIPT_NAME, member)
                    receipt = validate_phase_receipt(_canonical_control(shard / PHASE_RECEIPT_NAME,
                                                                        "Cached original discovery receipt"))
                    if receipt != completed["receipt"] or _identity(receipt) != instance:
                        raise ValueError("Cached original Runtime receipt differs from completed verification")
                    zipped = completed["originalFiles"]
                else:
                    artifact, _ = _download_contract_ci_upload(artifact["id"], artifact["digest"], name,
                        {"runId": run_id}, prior, token, destination=archive)
                    _require_artifact_job_window({"jobs": [job]}, job_name, artifact)
                    archive_identity = _stat_identity(archive.stat())
                    zipped, _, archive_verified = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                    if archive_verified != {"bytes": artifact["size_in_bytes"], "sha256": artifact["digest"]}:
                        raise ValueError("Original Runtime candidate archive differs from its authenticated upload")
                    _extract_runtime_original_projection(archive, zipped, scratch / "original")
                    verified = verify_phase_shard(shard, instance)
                    receipt = verified["receipt"]
                original = receipt["producer"]
                if (receipt["buildKey"] != build_key or original["tree"] != match[1]
                        or original["runId"] != run_id or original["runAttempt"] != attempt
                        or original["pullRequest"] != plan["pullRequest"]):
                    raise ValueError("Prior Runtime shard differs from its selected attempt")
                from products.restore import _VERIFICATION_SESSION, _stage_fingerprint, _is_windows
                session = None if _is_windows() else _VERIFICATION_SESSION.get()
                if session is not None and completed is None and qualified is None:
                    candidates = session.setdefault("runtimeCandidates", {})
                    # ponytail: immediate handoff only, bounded metadata; no
                    # extra retained body or serialized verification assertion.
                    if len(candidates) < 16 and sum(len(value[2]) for value in candidates.values()) + len(zipped) <= 65_536:
                        if regular_file_inventory(scratch / "original", allow_empty=True) != [
                                row for row in zipped if not row["relativePath"].startswith("inputs/")]:
                            raise ValueError("Original Runtime candidate extraction differs from its authenticated upload")
                        if _stat_identity(archive.stat()) != archive_identity:
                            raise ValueError("Original Runtime candidate archive changed during verification")
                        candidate_key = (str(archive.resolve()), artifact["id"], artifact["digest"],
                            sha256_bytes(verified["receiptBytes"]), original_workflow_sha, canonical_json_bytes(original))
                        candidates[candidate_key] = (scratch / "original", _stage_fingerprint(scratch), zipped)
                found.append((receipt, shard / PHASE_RECEIPT_NAME, original_workflow_sha))
            if not found:
                continue
            if any(receipt["outputs"] != found[0][0]["outputs"] for receipt, _, _ in found[1:]):
                raise ValueError(f"Prior Runtime exact build key has conflicting output inventories: "
                                 f"{instance} key={found[0][0]['buildKey']}")
            receipt_path, original_workflow_sha = found[0][1:]  # Preserve the chosen original producer.
            captured[instance] = capture_runtime_original_ci_phases(
                {instance.phase: receipt_path}, output, target=instance.component,
                trusted_workflow_sha=original_workflow_sha, token=token, original_instance=instance,
                recovery_projection=True, original_archives={instance.phase:
                    receipt_path.parent.parent.parent / "transport.zip"})
            # Only this phase's independently verified candidate trees are scratch;
            # keep original uploads upstream and the authenticated compact capture.
            shutil.rmtree(scratch_root / instance.component / instance.phase / instance.target)
            if session is not None:
                # Discard unchosen equivalent candidates with their scratch.
                prefix = str(scratch_root / instance.component / instance.phase / instance.target) + os.sep
                for key in tuple(session.get("runtimeCandidates", {})):
                    if key[0].startswith(prefix):
                        del session["runtimeCandidates"][key]
    return captured


def _runtime_capture_identity(observation: Mapping[str, Any], instance: PhaseInstanceId) -> dict[str, Any]:
    """Compare authenticated original identity, not mutable GitHub API snapshots."""
    job_name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
    observed = []
    for attempt in observation["observed"]:
        jobs = _matching_ci_jobs(attempt["jobs"], job_name)
        if len(jobs) != 1:
            raise ValueError("Prior Runtime observation lacks its exact original job")
        run = attempt["run"]
        observed.append({
            "run": {field: run.get(field) for field in
                    ("id", "run_attempt", "head_sha", "path", "event", "referenced_workflows")},
            "repositories": {field: {key: run[field].get(key) for key in ("full_name", "fork")}
                             for field in ("repository", "head_repository")},
            "testedCommit": attempt["testedCommit"],
            "job": {field: jobs[0].get(field) for field in
                    ("id", "name", "run_id", "head_sha", "status", "conclusion", "started_at", "completed_at")},
        })
    return {**observation, "observed": observed,
            "artifacts": {phase: {field: artifact.get(field) for field in
                ("id", "name", "digest", "size_in_bytes", "created_at", "archive_download_url", "workflow_run")}
                for phase, artifact in observation["artifacts"].items()}}


def _prior_failed_runtime_objects(
    capture_root: Path, artifact_root: Path, *, trusted_workflow_sha: str | None = None,
    token: str | None = None, plan: Mapping[str, Any] | None = None,
    consumer_producer: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Read captured originals; optionally re-admit them from their original CI."""
    if not capture_root.exists() and not capture_root.is_symlink():
        return []
    require_regular_directory(capture_root, "Prior failed Runtime captures")
    if (plan is None) != (consumer_producer is None):
        raise ValueError("Prior Runtime recheck requires both plan and consumer producer")
    if plan is not None and (not token or plan["repository"] != "codex-agent-labs/codex-agent"
                             or plan["event"] != "pull_request"):
        raise ValueError("Prior Runtime recheck requires the canonical PR and token")
    targets = sorted(capture_root.iterdir())
    if not targets:
        raise ValueError("Prior failed Runtime capture is empty")
    records = []
    with tempfile.TemporaryDirectory(prefix="runtime-pr-recheck-") as temporary:
        for member in targets:
            if member.name not in _RECOVERABLE_RUNTIME_COMPONENTS:
                raise ValueError("Prior failed Runtime capture has an unexpected component")
            require_regular_directory(member, "Prior failed Runtime component")
            phases = tuple(sorted(path.name for path in member.iterdir()))
            if not phases or any(phase not in ("binary", "package", "validation", "metadata")
                                 for phase in phases):
                raise ValueError("Prior failed Runtime capture has an unexpected phase")
            for phase in phases:
                phase_root = member / phase
                require_regular_directory(phase_root, "Prior failed Runtime phase")
                for captured in sorted(phase_root.iterdir()):
                    instance = PhaseInstanceId("runtime", member.name, phase, captured.name)
                    if instance not in PHASE_INSTANCE_IDS:
                        raise ValueError("Prior failed Runtime capture has an unexpected target")
                    require_regular_directory(captured, "Prior failed Runtime target")
                    shard = captured / "phases" / phase / "original/shard"
                    verified = verify_phase_shard(shard, instance)
                    receipt = verified["receipt"]
                    producer = receipt["producer"]
                    if (receipt["trustDomain"] != "development" or producer["event"] != "pull_request"
                            or (plan is not None and producer["pullRequest"] != plan["pullRequest"])):
                        raise ValueError("Prior failed Runtime receipt is not an original PR phase")
                    if plan is not None:
                        run_id = producer["runId"]
                        attempt = producer["runAttempt"]
                        if (run_id > consumer_producer["runId"] or
                                run_id == consumer_producer["runId"] and attempt >= consumer_producer["runAttempt"]):
                            raise ValueError("Prior failed Runtime producer is not earlier than its consumer")
                        official = api_json(
                            f"https://api.github.com/repos/{plan['repository']}/actions/runs/{run_id}/attempts/{attempt}",
                            token)
                        if (official.get("id") != run_id or official.get("run_attempt") != attempt
                                or official.get("event") != "pull_request"
                                or official.get("path") != ".github/workflows/ci.yml"
                                or official.get("status") != "completed"
                                or official.get("conclusion") not in {"failure", "cancelled"}
                                or not run_matches_pr(official, plan["pullRequest"])
                                or any(not isinstance(official.get(field), dict)
                                       or official[field].get("full_name") != plan["repository"]
                                       or official[field].get("fork") is not False
                                       for field in ("repository", "head_repository"))):
                            raise ValueError("Prior failed Runtime producer differs from official CI")
                    if trusted_workflow_sha is not None:
                        if not token:
                            raise ValueError("Prior failed Runtime recheck requires a token")
                        original_workflow_sha = (trusted_workflow_sha if plan is None else
                                                 _runtime_prior_workflow_sha(official, trusted_workflow_sha))
                        if original_workflow_sha is None:
                            raise ValueError("Prior failed Runtime producer lacks a reviewed workflow")
                        observation = _canonical_control(captured / "transport/original-ci-phases.json",
                                                         "Prior Runtime original observation")
                        with tempfile.TemporaryDirectory(prefix="phase-", dir=temporary) as phase_temporary:
                            replay = Path(phase_temporary).resolve(strict=True) / "capture"
                            fresh_observation = capture_runtime_original_ci_phases(
                                {phase: shard / PHASE_RECEIPT_NAME}, replay, target=member.name,
                                trusted_workflow_sha=original_workflow_sha, token=token,
                                original_instance=instance,
                                recovery_projection="recoveryProjection" in observation)
                            observation_path = "transport/original-ci-phases.json"
                            replay_files = [record for record in regular_file_inventory(replay, allow_empty=True)
                                            if record["relativePath"] != observation_path]
                            original_files = [record for record in regular_file_inventory(captured, allow_empty=True)
                                              if record["relativePath"] != observation_path]
                            # Keep the original snapshot unchanged. Fresh original-job/
                            # upload authentication above is mandatory; incidental run
                            # and unrelated-job observations are not product identity.
                            if (replay_files != original_files or
                                    _runtime_capture_identity(fresh_observation, instance) !=
                                    _runtime_capture_identity(observation, instance)):
                                raise ValueError("Prior failed Runtime capture differs from original CI")
                            _retarget_runtime_original_captures(replay, captured)
                    descriptor = _canonical_control(shard / PHASE_SHARD_NAME, "Prior failed Runtime shard")
                    records.append({
                        **_identity_record(instance),
                        "buildKey": descriptor["buildKey"],
                        "receiptSha256": descriptor["receiptSha256"],
                        "objectSha256": descriptor["objectSha256"],
                        "objectPath": (shard / descriptor["objectPath"]).relative_to(artifact_root).as_posix(),
                    })
    return records


def _elected_prior_runtime_records(
    records: list[dict[str, Any]], selected: tuple[PhaseInstanceId, ...],
    phases: Mapping[PhaseInstanceId, Mapping[str, Any]],
) -> dict[PhaseInstanceId, dict[str, Any]]:
    """Use a captured shard only when the planner retained that exact object."""
    return {instance: record for record in records
            if (instance := _identity(record)) in selected
            and phases[instance]["state"] == "retained"
            and all(phases[instance][field] == record[field]
                    for field in ("buildKey", "receiptSha256", "objectSha256"))}


def _validate_plan(plan_path: Path, root: Path, *, expected_revision: str | None = None) -> dict[str, Any]:
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
    revision = "HEAD"
    if expected_revision is not None:
        if (type(expected_revision) is not str or _OID.fullmatch(expected_revision) is None
                or expected_revision != commit):
            raise ValueError("Original impact plan does not match the selected revision")
        revision = expected_revision
    if _git_value(root, "rev-parse", f"{revision}^{{commit}}") != commit:
        raise ValueError("Checkout commit does not match the impact plan")
    if _git_value(root, "rev-parse", f"{revision}^{{tree}}") != tree:
        raise ValueError("Checkout tree does not match the impact plan")
    return plan


def _requested(plan: Mapping[str, Any]) -> tuple[PhaseInstanceId, ...]:
    selection = classify_paths(plan["changedPaths"])
    if list(selection.unknown_paths) != plan["unknownPaths"]:
        raise ValueError("Impact plan unknown paths disagree with product selection")
    # Unknown paths already make classify_paths fail closed to every phase. Only the
    # explicit fullRequested flag may otherwise broaden the authoritative selection.
    return PHASE_INSTANCE_IDS if plan["fullRequested"] or selection.unknown_paths else selection.instances


_versions = git_product_versions


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
            profile_path = ("gradle/release/toolchains/sdk/csharp.json" if profile == "sdk-csharp"
                            else f"{_PROFILE_ROOT}/{profile}.json")
            if profile_path not in paths:
                return None, "toolchain-profile-unavailable"
            profile_bytes = git_regular_blob_bytes(root, revision, profile_path, max_bytes=65_536)
            toolchain_digest = (load_sdk_dotnet_profile_bytes(profile_bytes).digest
                                if profile == "sdk-csharp" else
                                load_toolchain_profile_bytes(profile_bytes, profile).digest)
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


def _release_trust(root: Path, revision: str, destination: Path, *, original_inventory=None) -> ReleaseTrust | None:
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
    pinned = [{"relativePath": "trust/product-signing-keys.json", "bytes": len(keyring_bytes),
               "sha256": sha256_bytes(keyring_bytes)}]
    for record in records:
        if type(record) is not dict or type(record.get("keyId")) is not str:
            raise ValueError("Tracked product-signing key record is malformed")
        relative = f"{_KEYS_ROOT}/{record['keyId']}.pub"
        raw = git_regular_blob_bytes(root, revision, relative, max_bytes=64 * 1024)
        (keys / f"{record['keyId']}.pub").write_bytes(raw)
        pinned.append({"relativePath": f"trust/keys/{record['keyId']}.pub",
                       "bytes": len(raw), "sha256": sha256_bytes(raw)})
    load_keyring(keyring, keys)
    if not records:
        shutil.rmtree(trust)
        return None
    if original_inventory is not None:
        original_inventory.extend(pinned)
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
    download_artifact_to_file(dict(artifact), token, archive, max_bytes=_CATALOG_LIMIT)
    verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
    extracted = root / "contents"
    safe_extract(archive, extracted)
    return _read_catalog_directory(source, extracted, destination, release_trust,
        repository=repository, pull_request=pull_request, provenance_root=root,
        artifact=artifact, token=token, workflow_run=workflow_run, api=api)


def _read_catalog_directory(source, extracted, destination, release_trust, *, repository,
                            pull_request=None, provenance_root=None, artifact=None, token=None,
                            workflow_run=None, api=None):
    """Shared exact catalog layout; transport observation remains caller-owned."""
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
        write_canonical_json(provenance_root / "workflow-provenance.json", observed)
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
    apple_root = extracted / "sdk-apple-validation-evidence"
    if apple_root.exists() or apple_root.is_symlink():
        apple_records = load_sdk_apple_validation_evidence(apple_root)
        indexed = {(entry["receiptSha256"], entry["target"]) for entry in index["entries"]
                   if (entry["product"], entry["component"], entry["phase"]) == ("sdk", "sdk-ios", "validation")}
        if any((record["receiptSha256"], record["target"]) not in indexed for record in apple_records):
            raise ValueError("Apple catalog evidence lacks its exact indexed original validation receipt")
        controls.update(f"sdk-apple-validation-evidence/{path}" for path in _catalog_files(apple_root))
    else:
        apple_root = None
    maven_root = extracted / "sdk-maven-evidence"
    if maven_root.exists() or maven_root.is_symlink():
        from sdk_maven_evidence import load_sdk_maven_evidence
        maven_records = load_sdk_maven_evidence(maven_root)
        indexed = {(entry["receiptSha256"], entry["component"], entry["phase"], entry["target"])
                   for entry in index["entries"] if entry["product"] == "sdk"}
        if any((record["receiptSha256"], record["component"], record["phase"], record["target"])
               not in indexed for record in maven_records):
            raise ValueError("Maven catalog evidence lacks its exact indexed original receipt")
        controls.update(f"sdk-maven-evidence/{path}" for path in _catalog_files(maven_root))
    else:
        maven_root = None
    metadata_root = extracted / "sdk-metadata-evidence"
    if metadata_root.exists() or metadata_root.is_symlink():
        from sdk_metadata_evidence import load_sdk_metadata_evidence
        metadata_records = load_sdk_metadata_evidence(metadata_root)
        indexed = {(entry["receiptSha256"], entry["component"], entry["phase"], entry["target"])
                   for entry in index["entries"] if entry["product"] == "sdk"}
        if any((record["receiptSha256"], record["component"], record["phase"], record["target"])
               not in indexed for record in metadata_records):
            raise ValueError("Metadata catalog evidence lacks its exact indexed original receipt")
        controls.update(f"sdk-metadata-evidence/{path}" for path in _catalog_files(metadata_root))
    else:
        metadata_root = None
    aggregate_root = extracted / "runtime-aggregate-release-evidence"
    if aggregate_root.exists():
        aggregate_records = load_runtime_aggregate_release_evidence(aggregate_root)
        indexed = {entry["receiptSha256"] for entry in index["entries"]
                   if _identity(entry) == PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")}
        if any(record["receiptSha256"] not in indexed for record in aggregate_records):
            raise ValueError("Aggregate catalog evidence lacks its exact indexed original metadata receipt")
        controls.update(f"runtime-aggregate-release-evidence/{path}" for path in _catalog_files(aggregate_root))
    else:
        aggregate_root = None
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
        aggregate_root,
        apple_root,
        maven_root,
        metadata_root,
        dict(artifact) if artifact is not None else None,
    )


def stage_release_catalog(source_root, destination, *, repository, source, keyring, keys_directory):
    """Emit complete original catalog bytes; never build products or sign indexes."""
    from products.index import SignedProductIndex, verify_release_product_index
    from products.runtime_aggregate_handoff import _public_policy, verified_runtime_aggregate_handoff
    from products.sdk_package import _require_capability_output_separate

    if source not in {"stable", "promoted-main"}:
        raise ValueError("Release catalog assembly requires stable or promoted-main context")
    source_root, destination = Path(source_root).absolute(), Path(destination).absolute()
    originals = [source_root, Path(keyring), Path(keys_directory)]
    _require_capability_output_separate(destination, originals)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Release catalog destination must not exist")
    before = regular_file_inventory(source_root, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="product-catalog-stage-") as temporary:
        private = Path(temporary).resolve()
        policy = private / "policy"
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        trust = ReleaseTrust(policy / "product-signing-keys.json", policy / "keys")
        captured = private / "catalog"
        snapshot_regular_tree(source_root, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Release catalog changed during capture")
        index, _ = verify_release_product_index(
            SignedProductIndex(captured / "product-index.json", captured / "product-index.sig"),
            keyring_path=trust.keyring, keys_directory=trust.keys)
        if index["trustDomain"] != "release":
            raise ValueError("Release catalog requires release-trust index bytes")
        catalog = _read_catalog_directory(source, captured, private, trust, repository=repository)
        if set(catalog.objects) != {entry["buildKey"] for entry in index["entries"]}:
            raise ValueError("Emitted catalog requires every indexed original object")
        envelopes = {}
        for entry in index["entries"]:
            verified = verify_object(catalog.objects[entry["buildKey"]],
                build_key=entry["buildKey"], receipt_sha256=entry["receiptSha256"])
            envelope = {**verified, "receiptSha256": entry["receiptSha256"]}
            _verify_index_receipt(entry, envelope)
            envelopes[entry["receiptSha256"]] = envelope
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        required = {entry["receiptSha256"] for entry in index["entries"] if _identity(entry) == aggregate}
        evidence = catalog.runtime_aggregate_evidence_root
        records = load_runtime_aggregate_release_evidence(evidence) if evidence is not None else []
        if {record["receiptSha256"] for record in records} != required:
            raise ValueError("Emitted aggregate metadata requires its complete original release carrier")
        for record in records:
            with verified_runtime_aggregate_handoff(evidence / record["handoffRoot"],
                    keyring=trust.keyring, keys_directory=trust.keys) as verified:
                if verified["receiptBytes"][aggregate] != envelopes[record["receiptSha256"]]["receiptBytes"]:
                    raise ValueError("Catalog aggregate carrier differs from its indexed original receipt")
        if (regular_file_inventory(source_root, allow_empty=True) != before
                or regular_file_inventory(captured, allow_empty=True) != before
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in policy_paths.items())):
            raise ValueError("Catalog originals or caller policy changed before publication")
        _require_capability_output_separate(destination, originals)
        publish_regular_tree(captured, destination, allow_empty=True)
    return index


def stage_promoted_aggregate_catalog(source_root, destination, *, expected_build_key,
        expected_receipt_sha256, repository, context, producer, keyring, keys_directory, private_key):
    """Compose an admitted aggregate index and exact catalog, never product bytes.

    Promotion authorization and the elected key/receipt remain caller-owned.
    This local primitive does not authorize a run or manufacture hosted evidence.
    """
    from dataclasses import replace
    from products.index import IndexEntrySource, build_product_index, release_attested_runtime_aggregate_admission, write_signed_product_index
    from products.runtime_aggregate_handoff import _public_policy, verified_runtime_aggregate_handoff
    from products.signatures import load_keyring, require_active_release_key
    from products.sdk_package import _require_capability_output_separate

    if context.get("kind") != "promoted-main":
        raise ValueError("Aggregate catalog creation requires promoted-main context")
    key = require_sha256(expected_build_key, "Elected aggregate build key")
    receipt_digest = require_sha256(expected_receipt_sha256, "Elected aggregate receipt")
    source_root, destination = Path(source_root).absolute(), Path(destination).absolute()
    originals = [source_root, Path(keyring), Path(keys_directory), Path(private_key)]
    _require_capability_output_separate(destination, originals)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Promoted aggregate catalog destination must not exist")
    before = regular_file_inventory(source_root, allow_empty=True)
    with tempfile.TemporaryDirectory(prefix="promoted-aggregate-catalog-") as temporary:
        root = Path(temporary).resolve()
        policy = root / "policy"
        policy_paths, policy_bytes = _public_policy(keyring, keys_directory, policy)
        policy_inventory = regular_file_inventory(policy)
        pinned, keys = policy / "product-signing-keys.json", policy / "keys"
        captured = root / "originals"
        snapshot_regular_tree(source_root, captured, allow_empty=True)
        if regular_file_inventory(captured, allow_empty=True) != before:
            raise ValueError("Aggregate catalog originals changed during capture")
        evidence = captured / "runtime-aggregate-release-evidence"
        records = load_runtime_aggregate_release_evidence(evidence)
        if len(records) != 1 or records[0]["receiptSha256"] != receipt_digest:
            raise ValueError("Aggregate catalog requires the exact elected original release carrier")
        instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        with verified_runtime_aggregate_handoff(evidence / records[0]["handoffRoot"],
                keyring=pinned, keys_directory=keys) as verified:
            raw, receipt = verified["receiptBytes"][instance], verified["receipts"][instance]
            if sha256_bytes(raw) != receipt_digest or receipt["buildKey"] != key:
                raise ValueError("Aggregate carrier differs from elected original receipt/key")
            manifest = verified["indexInputs"]["manifest"]
            outputs = [record["relativePath"] for record in receipt["outputs"]
                       if Path(record["relativePath"]).name == manifest.name]
            if len(outputs) != 1:
                raise ValueError("Aggregate manifest must identify exactly one original output")
            entry = IndexEntrySource(raw, outputs[0])
            if receipt["trustDomain"] == "development":
                entry = replace(entry, release_admission=release_attested_runtime_aggregate_admission(
                    entry, **verified["indexInputs"]))
            sources = [entry]
            envelope = verify_object(captured / object_relative_path(key, receipt_digest),
                build_key=key, receipt_sha256=receipt_digest)
            if envelope["receiptBytes"] != raw:
                raise ValueError("Aggregate object changes its original receipt")
            expected_files = {object_relative_path(key, receipt_digest)} | {
                (Path("runtime-aggregate-release-evidence") / record["relativePath"]).as_posix()
                for record in regular_file_inventory(evidence, allow_empty=True)}
            if {record["relativePath"] for record in before} != expected_files:
                raise ValueError("Unsigned aggregate catalog has missing or unexpected original files")
            public_policy = load_keyring(pinned, keys)
            active, public_key = require_active_release_key(public_policy, keys)
            signing = {name: public_policy[name] for name in ("algorithm", "namespace", "trustDomain")}
            signing.update(active)
            arguments = dict(repository=repository, context=context, producer=producer,
                trust_domain="release", signing=signing, stable_history=None)
            index = build_product_index(sources, **arguments)
            _verify_index_receipt(index["entries"][0], {**envelope, "receiptSha256": receipt_digest})
        # All full-reader exit checks precede signing. Only new external index
        # bytes are written; original object and complete carrier stay unchanged.
        if regular_file_inventory(source_root, allow_empty=True) != before:
            raise ValueError("Aggregate catalog originals changed before index signing")
        write_signed_product_index(sources, **arguments, private_key=Path(private_key),
            public_key=public_key, manifest_path=captured / "product-index.json")
        stage_release_catalog(captured, root / "ready", repository=repository,
            source="promoted-main", keyring=pinned, keys_directory=keys)
        if (regular_file_inventory(source_root, allow_empty=True) != before
                or regular_file_inventory(policy) != policy_inventory
                or any(read_regular_file_bytes(path, max_bytes=64 * 1024, reject_symlink_parents=True)
                       != policy_bytes[name] for name, path in policy_paths.items())):
            raise ValueError("Aggregate originals or caller policy changed before catalog publication")
        _require_capability_output_separate(destination, originals)
        publish_regular_tree(root / "ready", destination, allow_empty=True)
    return index


def _candidate_artifacts(
    artifacts: list[object], source: str, pull_request: int | None,
    versions: Mapping[str, str], *, sdk_default_runtime_version: str | None = None,
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
    if sdk_default_runtime_version is not None:
        default = require_semver(sdk_default_runtime_version, "SDK default Runtime discovery version")
        if "-" in default:
            raise ValueError("SDK default Runtime discovery requires a stable release")
        stable_names.add(f"{prefix}runtime-{default}")
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
    repository_root: Path | None = None,
    tooling_candidate_runs: list[int] | None = None,
) -> list[Catalog]:
    token = environ.get("GITHUB_TOKEN")
    api = environ.get("GITHUB_API_URL")
    repository = environ.get("GITHUB_REPOSITORY")
    if not token or not api or not repository:
        return []
    if repository != plan["repository"]:
        raise ValueError("GitHub repository does not match the impact plan")
    sdk_default = None
    if repository_root is not None and any(
        instance.product == "sdk"
        and any(dependency.product == "runtime" for dependency in phase_instance_dependencies(instance))
        for instance in _dependency_closure(_requested(plan))
    ):
        from products.sdk_release_selection import read_sdk_release_selection, read_sdk_runtime_compatibility_policy
        selected = read_sdk_release_selection(repository_root, plan["validationCommit"])
        read_sdk_runtime_compatibility_policy(repository_root, plan["validationCommit"])
        sdk_default = selected["defaultRuntimeVersion"]
    artifacts = paginated_items(
        f"{api}/repos/{repository}/actions/artifacts", "artifacts", token,
    )
    if tooling_candidate_runs is not None:
        from tooling_discovery import candidate_run_ids
        tooling_candidate_runs.extend(candidate_run_ids(artifacts))
    result = []
    for source in ("stable", "promoted-main", "same-pr"):
        if source == "same-pr" and plan["pullRequest"] is None:
            continue
        if source != "same-pr" and release_trust is None:
            continue
        for artifact in _candidate_artifacts(artifacts, source, plan["pullRequest"], versions,
                                            sdk_default_runtime_version=sdk_default):
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
    source = sdk_runtime_source(root, plan["validationCommit"], instances=_dependency_closure(requested),
                                runtime_version=versions["runtime-release"], sdk_version=versions["sdk"])
    closure = set(_dependency_closure(requested, sdk_runtime_external=source is not None))
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
    if source is not None:
        request["sdkRuntimeSource"] = source
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
    *, require_complete: bool, sdk_runtime_external: bool = False,
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
    closure = _dependency_closure(requested, sdk_runtime_external=require_boolean(
        sdk_runtime_external, "Reuse result SDK Runtime source selection"))
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
        if not (sdk_runtime_external and instance.product == "sdk" and dependency.product == "runtime")
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
        if requirement["kind"] not in {"runtime-validation-evidence", "native-runtime-validation-evidence", "sdk-validation-evidence",
                                        "sdk-javascript-validation-evidence"}:
            raise ValueError("Reuse continuation requirement kind is invalid")
        instance = _identity(requirement)
        if instance not in phase_by_instance:
            raise ValueError("Reuse continuation requirement is outside the dependency closure")
        dependencies = (native_runtime_validation_dependencies(instance)
                        if requirement["kind"] == "native-runtime-validation-evidence"
                        else sdk_validation_dependencies(instance) if requirement["kind"] == "sdk-validation-evidence"
                        else javascript_validation_dependencies(instance) if requirement["kind"] == "sdk-javascript-validation-evidence"
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
             or sdk_validation_dependencies(instance) or javascript_validation_dependencies(instance))
        and all(dependency in selected_set or (
            sdk_runtime_external and instance.product == "sdk" and dependency.product == "runtime")
            for dependency in phase_instance_dependencies(instance))
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
    *, require_complete: bool, sdk_runtime_external: bool = False, object_root: Path | None = None,
) -> bool:
    result, selected_instances, selected_phases = _validate_reuse_result(
        result, requested, require_complete=require_complete, sdk_runtime_external=sdk_runtime_external,
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
    write_carrier(destination, normalized, selected_instances, sources, consumer,
                  **({"object_root": object_root} if object_root is not None else {}))
    return True


def _reverify_complete(
    result: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...],
    catalogs: list[Catalog], destination: Path, consumer: Mapping[str, Any],
    *, sdk_runtime_external: bool = False,
) -> None:
    # There is no product successor for a complete selection. Re-authentication
    # remains in the planner; do not reconstruct product bytes merely to upload
    # a second copy of the already immutable evidence.
    _, selected, phases = _validate_reuse_result(
        result, requested, require_complete=True, sdk_runtime_external=sdk_runtime_external)
    references, indexes = [], {}
    for instance, phase in zip(selected, phases, strict=True):
        catalog = _catalog_for_phase(catalogs, phase)
        original = catalog.objects.get(phase["buildKey"])
        if original is None:
            raise ValueError("Complete reuse lacks its original immutable object")
        verified = verify_object(original, build_key=phase["buildKey"],
            receipt_sha256=phase["receiptSha256"], object_sha256=phase["objectSha256"])
        if _identity(verified["receipt"]) != instance:
            raise ValueError("Complete reuse reference changes its original phase identity")
        manifest = destination / catalog.request["manifest"]
        indexes[catalog.index_sha256] = {"index": catalog.index,
                                       "immutableUpload": catalog.immutable_upload}
        references.append({**phase, "originalReceipt": verified["receipt"],
            "indexSha256": catalog.index_sha256,
            "objectPath": original.relative_to(manifest.parent).as_posix()})
    # This record is a locator, never an admission or cached trust assertion.
    write_canonical_json(destination / "reuse-references.json", {
        "schemaVersion": 1, "consumer": consumer, "indexes": indexes, "phases": references})


def _publish_discovery_handoff(destination: Path, handoff: Path) -> None:
    result = _canonical_control(destination / "result.json", "Product discovery result")
    if result["fullReuse"] is not True:
        publish_regular_tree(destination, handoff, allow_empty=True)
        return
    if result["targetJobsRequired"] is not False or result["reason"] not in {"verified-full-reuse", "no-product-work"}:
        raise ValueError("Complete discovery handoff has inconsistent successor selection")
    # Only controls needed by the merge gate travel with the plan. Incomplete
    # selections keep the existing complete input protocol for their consumers.
    with tempfile.TemporaryDirectory(prefix="product-reference-handoff-") as temporary:
        prepared = Path(temporary).resolve()
        names = (("request.json", "result.json") if result["reason"] == "no-product-work" else
                 ("request.json", "result.json", "reuse-wave-result.json", "reuse-references.json"))
        for name in names:
            raw = read_regular_file_bytes(destination / name, max_bytes=16 * 1024 * 1024,
                                         reject_symlink_parents=True)
            (prepared / name).write_bytes(raw)
        publish_regular_tree(prepared, handoff)


def _consumer(plan: Mapping[str, Any], environ: Mapping[str, str], *,
              original_run_id: int | None = None,
              original_run_attempt: int | None = None) -> dict[str, Any]:
    event = require_string(plan["event"], "impact plan.event")
    def positive_environment_integer(name: str) -> int:
        value = environ.get(name)
        if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
            raise ValueError(f"{name} must be a positive decimal integer")
        return int(value)
    if (original_run_id is None) != (original_run_attempt is None):
        raise ValueError("Original CI run and attempt must be supplied together")
    run_id = (positive_environment_integer("GITHUB_RUN_ID") if original_run_id is None else
              require_integer(original_run_id, "Original CI run ID", 1))
    run_attempt = (positive_environment_integer("GITHUB_RUN_ATTEMPT") if original_run_attempt is None else
                   require_integer(original_run_attempt, "Original CI run attempt", 1))
    return {
        "kind": "ci",
        "producer": {
            "repository": plan["repository"],
            "workflowPath": ".github/workflows/ci.yml",
            "commit": plan["validationCommit"],
            "tree": plan["validationTree"],
            "event": event,
            "runId": run_id,
            "runAttempt": run_attempt,
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
    if {"sdkValidationTooling", "sdkAppleValidationPolicy"} & request.keys():
        raise ValueError("Retained SDK evidence cannot supply current-invocation tooling authority")
    result = {key: _rebase_native_evidence_paths(request[key], source_root, artifact_root,
                                             comparison=key == "nativeRuntimeComparisonEvidence")
            for key in _NATIVE_REQUEST_KEYS if key in request}
    if _ADAPTER_REQUEST_KEY in request:
        result[_ADAPTER_REQUEST_KEY] = rebase_adapter_comparison_records(request[_ADAPTER_REQUEST_KEY], source_root, artifact_root)
    if "sdkValidationEvidence" in request:
        result["sdkValidationEvidence"] = rebase_sdk_validation_records(request["sdkValidationEvidence"], source_root, artifact_root)
    if "sdkAppleValidationEvidence" in request:
        result["sdkAppleValidationEvidence"] = rebase_sdk_apple_validation_records(
            request["sdkAppleValidationEvidence"], source_root, artifact_root)
    if _AGGREGATE_REQUEST_KEY in request:
        result[_AGGREGATE_REQUEST_KEY] = rebase_runtime_aggregate_release_records(
            request[_AGGREGATE_REQUEST_KEY], source_root, artifact_root)
    return result


def _wave_control(path, label):
    value = _canonical_control(path, label)
    value = require_exact_keys(value, _WAVE_REQUEST_KEYS | (value.keys() & (_NATIVE_REQUEST_KEYS | {_ADAPTER_REQUEST_KEY, _AGGREGATE_REQUEST_KEY} | _SDK_REQUEST_KEYS)), label)
    if "sdkRuntimeSource" in value and value["sdkRuntimeSource"] != "released-default":
        raise ValueError("Unsupported SDK Runtime dependency source")
    return value


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


def _metadata_admissions(facade, android):
    """Forward caller-owned verifier objects only; never serialize authority."""
    return {name: value for name, value in (
        ("sdk_facade_metadata_admission", facade),
        ("sdk_android_metadata_admission", android)) if value is not None}


def _apple_package_origin(plan_path, root, workflow_sha, environment):
    if workflow_sha is None:
        return None
    if type(workflow_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", workflow_sha) is None:
        raise ValueError("Apple package original workflow requires an exact caller pin")
    return {"plan_path": plan_path, "repository_root": root,
            "trusted_workflow_sha": workflow_sha, "environ": environment,
            "token": environment.get("GITHUB_TOKEN", "")}


def _javascript_projection_provider(request, tooling, original_context):
    """Authenticate the original upload/cwd before deriving a metadata key view."""
    if (tooling is None or original_context is None or not any(
            javascript_validation_dependencies(_identity(value)) for value in request.get("requested", []))):
        return None
    from products.sdk_javascript_validation_phase import verify_sdk_javascript_validation_projection

    policy = require_exact_keys(tooling,
        {"evidence", "publicKey", "javaExecutable", "requiredTrustDomain", "keyring", "keysDirectory"},
        "JavaScript caller tooling policy")
    arguments = {name: (None if policy[field] is None and field in {"keyring", "keysDirectory"}
                       else Path(require_string(policy[field], f"JavaScript tooling {field}")))
                 for field, name in (("evidence", "tooling_evidence"), ("publicKey", "tooling_public_key"),
                     ("javaExecutable", "java_executable"), ("keyring", "tooling_keyring"),
                     ("keysDirectory", "tooling_keys_directory"))}
    if any(path is not None and not path.is_absolute() for path in arguments.values()):
        raise ValueError("JavaScript tooling paths must be absolute caller inputs")
    objects = {_identity(record): record for record in request["availableObjects"]}
    artifact_root = Path(request["artifactRoot"])
    proofs = {}

    def verify(instance, originals):
        if not javascript_validation_dependencies(instance) or len(originals) != 4:
            raise ValueError("JavaScript projection requires its exact metadata input family")
        selected = {_identity(value["receipt"]): value for value in originals}
        records = [objects.get(_identity(value["receipt"])) for value in originals]
        if any(record is None for record in records):
            return None
        for record, original in zip(records, originals, strict=True):
            if any(record[field] != original[field] for field in ("receiptSha256", "objectSha256")) or \
                    record["buildKey"] != original["receipt"]["buildKey"]:
                raise ValueError("JavaScript selected object differs from its authenticated original")
        validation = selected[PhaseInstanceId("sdk", "javascript", "validation", "node")]
        if validation["receipt"]["producer"]["event"] == "local":
            return None  # Local proofs require their own explicit, observed caller context.
        key = tuple((value["receiptSha256"], value["objectSha256"]) for value in originals)
        if key not in proofs:
            with tempfile.TemporaryDirectory(prefix="sdk-javascript-key-proof-") as temporary:
                private = Path(temporary).resolve()
                (private / "stages").mkdir()
                stages, receipts = {}, {}
                for index, (record, original) in enumerate(zip(records, originals, strict=True)):
                    identity = _identity(original["receipt"])
                    stages[identity] = private / "stages" / str(index)
                    restored = restore_object(artifact_root / require_relative_path(record["objectPath"], "JS original object"),
                        stages[identity], build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
                        object_sha256=record["objectSha256"])
                    if restored["receiptBytes"] != original["receiptBytes"]:
                        raise ValueError("JavaScript restored input differs from its selected original")
                    receipts[identity] = private / f"receipt-{index}.json"
                    receipts[identity].write_bytes(original["receiptBytes"])
                validation_id = PhaseInstanceId("sdk", "javascript", "validation", "node")
                from sdk_javascript_validation_locator import locate_javascript_validation_upload
                locator = locate_javascript_validation_upload(receipts[validation_id],
                    trusted_workflow_sha=original_context["trusted_workflow_sha"], token=original_context["token"])
                transport = capture_sdk_javascript_validation_upload(original_context["plan_path"], private / "upload",
                    validation_receipt_path=receipts[validation_id], **locator,
                    trusted_workflow_sha=original_context["trusted_workflow_sha"],
                    repository_root=original_context["repository_root"], environ=original_context["environ"],
                    token=original_context["token"])
                inputs = {}
                for name, identity in (("contract", PhaseInstanceId("contract", "contract", "binary", "common")),
                        ("package", PhaseInstanceId("sdk", "javascript", "package", "node")),
                        ("validation", validation_id),
                        ("runtime_validation", PhaseInstanceId("runtime", "node-js", "validation", "node-js-binding"))):
                    inputs[f"{name}_stage"], inputs[f"{name}_receipt"] = stages[identity], receipts[identity]
                proofs[key] = verify_sdk_javascript_validation_projection(**inputs, **arguments,
                    original_consumer_directory=Path(transport["originalConsumerDirectory"]),
                    # Deliberate original-source readmission, after observed
                    # job/upload authentication; never a tooling-error fallback.
                    repository=original_context["repository_root"],
                    policy_revision=validation["receipt"]["producer"]["commit"],
                    required_trust_domain=policy["requiredTrustDomain"])
        return proofs[key]

    return verify


def _plan_with_sdk_tooling(request, tooling, *, apple_policy=None, apple_package_origin=None, **kwargs):
    # Never serialize invocation authority into retained control or evidence.
    if {"sdkValidationTooling", "sdkAppleValidationPolicy"} & request.keys():
        raise ValueError("Retained SDK evidence cannot supply current-invocation tooling authority")
    invocation = dict(request)
    if tooling is not None:
        invocation["sdkValidationTooling"] = tooling
    if "sdkAppleValidationEvidence" in request:
        if apple_policy is None:
            raise ValueError("Retained Apple evidence requires caller-owned validation policy")
        invocation["sdkAppleValidationPolicy"] = apple_policy
    needs_package = (apple_package_origin is not None and apple_policy is not None
        and PhaseInstanceId("sdk", "sdk-ios", "package", "ios") in _dependency_closure(
            tuple(_identity(value) for value in request["requested"])))
    if apple_package_origin is not None and needs_package and apple_policy is not None:
        from sdk_apple_original_package_selection import caller_original_apple_package_selector
        current_plan = Path(apple_package_origin["plan_path"])
        current_plan_bytes = read_regular_file_bytes(current_plan, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True)
        policy_plan = Path(apple_policy["plan"])
        if read_regular_file_bytes(policy_plan, max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True) != current_plan_bytes:
            raise ValueError("Apple package caller policy differs from the current product plan")
        context = caller_original_apple_package_selector(
            policy_plan, apple_policy,
            repository_root=apple_package_origin["repository_root"],
            trusted_workflow_sha=apple_package_origin["trusted_workflow_sha"],
            environ=apple_package_origin["environ"], token=apple_package_origin["token"])
    else:
        context = nullcontext(None)
    with context as factory:
        if "sdk_javascript_validation_projection_provider" not in kwargs:
            javascript_provider = _javascript_projection_provider(request, tooling, apple_package_origin)
            if javascript_provider is not None:
                kwargs["sdk_javascript_validation_projection_provider"] = javascript_provider
        result = plan_reuse_wave(invocation,
            **({"sdk_apple_package_admission_factory": factory} if factory is not None else {}), **kwargs)
    if apple_package_origin is not None and needs_package and apple_policy is not None:
        if read_regular_file_bytes(current_plan, max_bytes=16 * 1024 * 1024,
                reject_symlink_parents=True) != current_plan_bytes:
            raise ValueError("Current product plan changed during Apple package admission")
    return result


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


def _retained_apple_handoffs(state_root, artifact_root):
    path = state_root / "sdk-apple-validation-evidence"
    if not path.exists() and not path.is_symlink():
        return []
    require_regular_directory(path, "Retained Apple evidence carriers")
    for parent in path.absolute().parents:
        require_regular_directory(parent, "Retained Apple evidence ancestry")
    return [record for child in sorted(path.iterdir())
            for record in rebase_sdk_apple_validation_records(load_sdk_apple_validation_evidence(child), child, artifact_root)]


def _capture_apple_handoffs(evidence_roots, destination, artifact_root):
    # Structural transport only. The planner's mandatory full gate grants admission.
    offset = len(list(destination.iterdir())) if destination.exists() else 0
    records = []
    for index, source in enumerate(evidence_roots, offset):
        original = load_sdk_apple_validation_evidence(source)
        target = destination / str(index)
        captured = capture_sdk_apple_validation_evidence(
            [source / record["evidenceRoot"] for record in original], target)
        records.extend(rebase_sdk_apple_validation_records(captured, target, artifact_root))
    return records


def _capture_maven_handoffs(evidence_roots, destination):
    """Lossless external storage only; never adds planner or host admission."""
    from sdk_maven_evidence import load_sdk_maven_evidence
    offset = len(list(destination.iterdir())) if destination.exists() else 0
    for index, source in enumerate(evidence_roots, offset):
        source = Path(source)
        before = regular_file_inventory(source, allow_empty=True)
        records = load_sdk_maven_evidence(source)
        target = destination / str(index)
        snapshot_regular_tree(source, target, allow_empty=True)
        if (load_sdk_maven_evidence(target) != records
                or regular_file_inventory(target, allow_empty=True) != before
                or regular_file_inventory(source, allow_empty=True) != before):
            raise ValueError("Maven evidence carrier changed during retention")


def _capture_metadata_handoffs(evidence_roots, destination):
    """Preserve complete metadata transport; caller replay policy stays separate."""
    from sdk_metadata_evidence import load_sdk_metadata_evidence
    offset = len(list(destination.iterdir())) if destination.exists() else 0
    for index, source in enumerate(evidence_roots, offset):
        source = Path(source)
        before = regular_file_inventory(source, allow_empty=True)
        records = load_sdk_metadata_evidence(source)
        target = destination / str(index)
        snapshot_regular_tree(source, target, allow_empty=True)
        if (load_sdk_metadata_evidence(target) != records
                or regular_file_inventory(target, allow_empty=True) != before
                or regular_file_inventory(source, allow_empty=True) != before):
            raise ValueError("Metadata evidence carrier changed during retention")


def _verify_discovery_sdk_records(request, discovery_root):
    apple = {}
    _merge_native_comparison_records(apple,
        _retained_apple_handoffs(discovery_root, discovery_root), key="sdkAppleValidationEvidence")
    _merge_native_comparison_records(apple,
        _retained_apple_handoffs(discovery_root / "discovery", discovery_root), key="sdkAppleValidationEvidence")
    if request.get("sdkAppleValidationEvidence", []) != apple.get("sdkAppleValidationEvidence", []):
        raise ValueError("Apple discovery request differs from its complete retained evidence carrier")
    retained = {}
    _merge_native_comparison_records(retained,
        _retained_sdk_handoffs(discovery_root, discovery_root), key="sdkValidationEvidence")
    if request.get("sdkValidationEvidence", []) != retained.get("sdkValidationEvidence", []):
        raise ValueError("SDK discovery request differs from its complete retained evidence carrier")
    retained = {}
    _merge_native_comparison_records(retained,
        _retained_aggregate_handoffs(discovery_root, discovery_root), key=_AGGREGATE_REQUEST_KEY)
    _merge_native_comparison_records(retained,
        _retained_aggregate_handoffs(discovery_root / "discovery", discovery_root), key=_AGGREGATE_REQUEST_KEY)
    if request.get(_AGGREGATE_REQUEST_KEY, []) != retained.get(_AGGREGATE_REQUEST_KEY, []):
        raise ValueError("Aggregate discovery request differs from its complete retained evidence carrier")


def _retained_aggregate_handoffs(state_root, artifact_root):
    path = state_root / "runtime-aggregate-release-evidence"
    if not path.exists():
        return []
    return [record for child in sorted(path.iterdir())
            for record in rebase_runtime_aggregate_release_records(
                load_runtime_aggregate_release_evidence(child), child, artifact_root)]


def _capture_aggregate_handoffs(evidence_roots, destination, artifact_root, trust):
    records = []
    offset = len(list(destination.iterdir())) if destination.exists() else 0
    for index, source in enumerate(evidence_roots, offset):
        target = destination / str(index)
        captured = stage_runtime_aggregate_release_evidence(
            load_runtime_aggregate_release_evidence(source), source, target,
            keyring=trust.keyring if trust else None, keys_directory=trust.keys if trust else None)
        records.extend(rebase_runtime_aggregate_release_records(captured, target, artifact_root))
    return records


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
    carrier = verify_carrier(state / "carrier", selected, _consumer(plan, environment), object_root=state)
    phases_by_id = {_identity(phase): phase for phase in phases}
    sources = {}
    for record in carrier["objects"]:
        instance = _identity(record)
        if any(record[field] != phases_by_id[instance][field]
               for field in ("buildKey", "receiptSha256", "objectSha256")):
            raise ValueError("Initial Contract object differs from completed state")
        sources[instance] = (state / record["originalObjectPath"] if "originalObjectPath" in record else
            state / "carrier" / object_relative_path(record["buildKey"], record["receiptSha256"]))
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
                report = load_json_bytes(read_regular_file_bytes(
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
    original_inventory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    records = []
    for metadata in closure:
        dependencies = runtime_validation_dependencies(metadata)
        if not dependencies or any(dependency not in sources for dependency in dependencies):
            continue
        handoff = destination / f"{metadata.component}-{metadata.target}"
        receipts = {}
        reports = {}
        handoff_inventory = []
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
            if original_inventory is not None:
                prefix = f"{metadata.component}-{metadata.target}/validation/{dependency.component}-{dependency.target}"
                receipt = restored["receipt"]
                manifest = {"schemaVersion": 1, **{field: receipt[field] for field in
                    ("product", "component", "phase", "target", "productVersion", "outputs")}}
                manifest_bytes, receipt_bytes = canonical_json_bytes(manifest), restored["receiptBytes"]
                handoff_inventory.extend([
                    *({"relativePath": f"{prefix}/stage/{record['relativePath']}",
                       "bytes": record["bytes"], "sha256": record["sha256"]} for record in receipt["outputs"]),
                    {"relativePath": f"{prefix}/stage/output-manifest.json", "bytes": len(manifest_bytes),
                     "sha256": sha256_bytes(manifest_bytes)},
                    {"relativePath": f"{prefix}/receipt/phase-receipt.json", "bytes": len(receipt_bytes),
                     "sha256": sha256_bytes(receipt_bytes)},
                ])
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
        if original_inventory is not None:
            projection_bytes = canonical_json_bytes(projection)
            handoff_inventory.append({"relativePath": f"{metadata.component}-{metadata.target}/projection.json",
                                      "bytes": len(projection_bytes), "sha256": sha256_bytes(projection_bytes)})
            original_inventory.extend(handoff_inventory)
        records.append({
            **_identity_record(metadata),
            "reports": [path.relative_to(artifact_root).as_posix() for path in ordered_reports],
        })
    return records


def _initial_runtime_validation_handoffs(closure, objects, object_root, destination, artifact_root):
    phases = {_identity(record): record for record in objects}
    sources = {instance: object_root / record["objectPath"] for instance, record in phases.items()}
    return _materialize_runtime_validation_handoffs(
        closure, phases, sources, destination, artifact_root,
    )


def advance_contract(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    shard_roots: list[Path], destination: Path,
    github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
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
    if request["availableObjects"]:
        from contract_retained_recovery import replay_retained_contract
        with tempfile.TemporaryDirectory(prefix="contract-retained-recheck-", dir=root) as temporary:
            private = Path(temporary).resolve()
            trust = _release_trust(root, plan["validationCommit"], private)
            if trust is None:
                raise ValueError("Retained Contract replay requires tracked release trust")
            current_request = {**request, "artifactRoot": str(discovery_root), "availableObjects": []}
            rechecked = replay_retained_contract(
                discovery_root / "retained-contract/capture", current_request, private / "carrier",
                consumer=consumer, keyring=trust.keyring, keys_directory=trust.keys,
                sdk_validation_tooling=sdk_validation_tooling,
                sdk_apple_validation_policy=sdk_apple_validation_policy, allow_partial=True)
            initial = _canonical_control(discovery_root / "contract-reuse-result.json", "Retained Contract result")
            if (rechecked["request"]["availableObjects"] != request["availableObjects"]
                    or rechecked["result"] != initial):
                raise ValueError("Retained Contract request differs from its authenticated current replay")
            expected_fixed["availableObjects"] = rechecked["request"]["availableObjects"]
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
    rebased_request["availableObjects"] = [{**record,
        "objectPath": (discovery_root / record["objectPath"]).relative_to(root).as_posix(),
    } for record in request["availableObjects"]]
    rebased_request.update(_rebase_native_request(request, discovery_root, root))
    replay_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain(plans: dict[PhaseInstanceId, dict[str, Any]], instance: PhaseInstanceId,
               value: dict[str, Any]) -> None:
        if instance in plans:
            raise ValueError(f"Duplicate Contract phase plan: {instance}")
        plans[instance] = value

    replay = _plan_with_sdk_tooling(
        rebased_request, sdk_validation_tooling,
        apple_policy=sdk_apple_validation_policy,
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
        verified_carrier = verify_carrier(carrier_root, prior_materialized, consumer, object_root=state_root)
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
            sources[instance] = (state_root / record["originalObjectPath"] if "originalObjectPath" in record else
                carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]))
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
            apple_policy=sdk_apple_validation_policy,
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
        apple_policy=sdk_apple_validation_policy,
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


@verification_scoped
def _verified_product_state(
    plan_path: Path, discovery_root: Path, state_root: Path, root: Path,
    environment: Mapping[str, str], sdk_validation_tooling: Mapping[str, Any] | None,
    *, sdk_runtime_consumer=None, authenticated_lookup_consumer=None,
    sdk_apple_validation_policy=None,
    sdk_original_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> _VerifiedProductState:
    # Invocation callbacks may run before retained-result equality is checked;
    # callers must keep captured bytes private until this function returns.
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
    versions = _versions(root, plan["validationCommit"])
    source = sdk_runtime_source(root, plan["validationCommit"], instances=_dependency_closure(requested),
                                runtime_version=versions["runtime-release"], sdk_version=versions["sdk"])
    if request.get("sdkRuntimeSource") != source:
        raise ValueError("Reuse-wave SDK Runtime source differs from original Git policy")
    closure = _dependency_closure(requested, sdk_runtime_external=source is not None)
    authorities, unavailable = _authorities(root, plan["validationCommit"], closure)
    if authorities is None:
        raise ValueError(unavailable or "Product phase authority is unavailable")
    prior_capture = discovery_root / "prior-failed-runtime"
    prior_records = []
    if prior_capture.exists() or prior_capture.is_symlink():
        if not sdk_original_workflow_sha:
            raise ValueError("Prior failed Runtime replay requires caller-pinned workflow authority")
        prior_records = _prior_failed_runtime_objects(
            prior_capture, discovery_root, trusted_workflow_sha=sdk_original_workflow_sha,
            token=environment.get("GITHUB_TOKEN"), plan=plan, consumer_producer=consumer["producer"])
    initial_objects = []
    if request["availableObjects"]:
        supplied_objects = require_array(request["availableObjects"], "Initial availableObjects")
        supplied_ids = []
        for record in supplied_objects:
            require_exact_keys(record, set(_IDENTITY_KEYS) | {
                "buildKey", "receiptSha256", "objectSha256", "objectPath"}, "Initial availableObjects member")
            supplied_ids.append(_identity(record))
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        expected_ids = tuple(sorted((*_dependency_closure((contract,)),
                                     *(_identity(record) for record in prior_records))))
        if tuple(supplied_ids) != expected_ids:
            raise ValueError("Initial availableObjects differ from authenticated Contract/Runtime objects")
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
        initial_objects = sorted((*initial_objects, *prior_records), key=_identity)
    elif prior_records:
        raise ValueError("Prior failed Runtime capture lacks its available object request")
    with tempfile.TemporaryDirectory(prefix="codex-agent-initial-runtime-evidence-", dir=root) as temporary:
        derived = Path(temporary).resolve() / "initial-runtime-validation-handoffs"
        evidence = _initial_runtime_validation_handoffs(
            closure, initial_objects, discovery_root, derived, root,
        )
        prefix = derived.relative_to(root).as_posix()
        initial_evidence = [{**record, "reports": [
            "initial-runtime-validation-handoffs/" + path.removeprefix(prefix + "/")
            for path in record["reports"]
        ]} for record in evidence]
        retained = discovery_root / "initial-runtime-validation-handoffs"
        if (derived.exists() or retained.exists() or retained.is_symlink()) and (
            not derived.exists() or not retained.exists()
            or regular_file_inventory(derived, allow_empty=True) != regular_file_inventory(retained, allow_empty=True)
        ):
            raise ValueError("Initial Runtime validation evidence differs from authenticated original objects")
    expected_fixed = {
        "schemaVersion": 1,
        "requestType": "reuse-wave",
        "repository": plan["repository"],
        "pullRequest": plan["pullRequest"],
        "repositoryRoot": str(root),
        "repositoryRevision": plan["validationCommit"],
        "requested": [_identity_record(instance) for instance in requested],
        "versions": versions,
        "phaseAuthorities": authorities,
        "runtimeValidationEvidence": initial_evidence,
        "availableObjects": initial_objects,
    }
    if source is not None:
        expected_fixed["sdkRuntimeSource"] = source
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
    rebased_request["runtimeValidationEvidence"] = [{**record, "reports": [
        (discovery_root / path).relative_to(root).as_posix() for path in record["reports"]
    ]} for record in initial_evidence]
    rebased_request.update(_rebase_native_request(request, discovery_root, root))

    replay_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
    replay = _plan_with_sdk_tooling(
        rebased_request, sdk_validation_tooling,
        apple_package_origin=_apple_package_origin(plan_path, root, sdk_original_workflow_sha, environment),
        build_plan_consumer=lambda instance, value: _retain_product_plan(replay_plans, instance, value),
        **({"sdk_runtime_consumer": sdk_runtime_consumer}
           if sdk_runtime_consumer is not None and state_root == discovery_root else {}),
        **({"authenticated_lookup_consumer": authenticated_lookup_consumer}
           if authenticated_lookup_consumer is not None and state_root == discovery_root else {}),
        apple_policy=sdk_apple_validation_policy,
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    initial = _canonical_control(discovery_root / "reuse-wave-result.json", "Initial reuse result")
    if replay != initial:
        raise ValueError("Initial reuse result is not reproducible from its authenticated request")

    prior = _canonical_control(state_root / "reuse-wave-result.json", "Reuse result")
    _, prior_materialized, _ = _validate_reuse_result(
        prior, requested, require_complete=False, sdk_runtime_external=source is not None,
    )
    prior_by_instance = {_identity(phase): phase for phase in prior["phases"]}
    sources: dict[PhaseInstanceId, Path] = {}
    prior_carrier_phases: dict[PhaseInstanceId, dict[str, Any]] = {}
    carrier_name = "carrier" if prior["fullReuse"] else "reused-carrier"
    carrier_root = state_root / carrier_name
    if prior_materialized:
        carrier = verify_carrier(carrier_root, prior_materialized, consumer, object_root=state_root)
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
            sources[instance] = (state_root / record["originalObjectPath"] if "originalObjectPath" in record else
                carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]))
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
            _merge_native_comparison_records(state_request, _retained_apple_handoffs(state_root, root), key="sdkAppleValidationEvidence")
            _merge_native_comparison_records(state_request, _retained_aggregate_handoffs(state_root, root), key=_AGGREGATE_REQUEST_KEY)
            prior_ready_plans = {}
            state_replay = _plan_with_sdk_tooling(
                state_request, sdk_validation_tooling,
                apple_package_origin=_apple_package_origin(plan_path, root, sdk_original_workflow_sha, environment),
                build_plan_consumer=lambda instance, value: _retain_product_plan(
                    prior_ready_plans, instance, value,
                ),
                **({"sdk_runtime_consumer": sdk_runtime_consumer} if sdk_runtime_consumer is not None else {}),
                **({"authenticated_lookup_consumer": authenticated_lookup_consumer}
                   if authenticated_lookup_consumer is not None else {}),
                apple_policy=sdk_apple_validation_policy,
                **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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


def _sdk_input_selection(state, root):
    """Route selected SDK content needs; this hint never grants execution trust."""
    consumers = []
    for record in state.prior["phases"]:
        instance = _identity(record)
        if (instance.product == "sdk" and instance.phase != "binary"
                and record["state"] not in {"retained", "reused"}
                and any(dependency.product == "runtime" for dependency in _dependency_closure((instance,)))):
            consumers.append(_identity_record(instance))
    contract = PhaseInstanceId("contract", "contract", "metadata", "common")
    if not consumers or contract not in state.sources:
        return None
    from products.sdk_release_selection import read_sdk_release_selection, read_sdk_runtime_compatibility_policy
    revision = state.producer["commit"]
    policy = read_sdk_release_selection(root, revision)
    ranges = read_sdk_runtime_compatibility_policy(root, revision)
    record = state.prior_carrier_phases[contract]
    original = verify_object(state.sources[contract], build_key=record["buildKey"],
        receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
    receipt = original["receipt"]
    outputs = receipt["outputs"]
    version = state.expected_fixed["versions"]["contract"]
    if (receipt["productVersion"] != version or len(outputs) != 1
            or outputs[0]["kind"] != "contract-bundle"):
        raise ValueError("SDK handoff requires the exact selected Contract payload")
    return {"source": state.rebased_request.get("sdkRuntimeSource", "current-runtime"),
            **policy, **ranges, "contractVersion": version,
            "contractPayloadSha256": require_sha256(outputs[0]["sha256"], "Selected Contract payload digest"),
            "consumers": sorted(consumers, key=lambda value: tuple(value[field] for field in _IDENTITY_KEYS))}


@verification_scoped
def inspect_products(
    plan_path: Path, discovery_root: Path, state_root: Path | None = None, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    include_sdk_selection: bool = False,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    """Re-elect ready plans before target setup without admitting new shards."""
    if type(include_sdk_selection) is not bool:
        raise ValueError("SDK selection inspection must be boolean")
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
        os.environ if environ is None else environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    request = dict(state.rebased_request)
    _merge_native_comparison_records(request, _retained_aggregate_handoffs(state_root, root), key=_AGGREGATE_REQUEST_KEY)
    return {"result": state.prior,
            **({"sdkInputSelection": _sdk_input_selection(state, root)} if include_sdk_selection else {}),
            _AGGREGATE_REQUEST_KEY: request.get(_AGGREGATE_REQUEST_KEY, []),
            "readyPlans": [state.prior_ready_plans[instance] for instance in sorted(state.prior_ready_plans)]}


def _sdk_javascript_worker_instance(instance):
    return instance in (
        PhaseInstanceId("sdk", "javascript", "package", "node"),
        PhaseInstanceId("sdk", "javascript", "validation", "node"),
    )


def _sdk_ios_binary_worker_instance(instance):
    return instance == PhaseInstanceId("sdk", "sdk-ios", "binary", "ios")


SDK_WORKER_FAMILIES = (
    "csharp-binary", "native-package", "ios-package", "javascript-metadata", "native-validation",
    "native-metadata", "ios-validation", "ios-metadata",
    "core-binary", "core-package", "core-validation", "core-metadata",
    "android-binary", "android-package", "android-validation", "android-metadata",
)


def _sdk_family_worker_instance(instance, family):
    if type(family) is not str or family not in SDK_WORKER_FAMILIES:
        raise ValueError("Unsupported SDK worker family")
    if family == "csharp-binary":
        return instance == PhaseInstanceId("sdk", "csharp", "binary", "desktop")
    if family == "native-package":
        return instance in {PhaseInstanceId("sdk", language, "package", "desktop") for language in NATIVE_BINDINGS}
    if family == "native-validation":
        return instance in {PhaseInstanceId("sdk", language, "validation", target)
                            for language in NATIVE_BINDINGS for target in NATIVE_TARGETS}
    if family == "native-metadata":
        return instance in {PhaseInstanceId("sdk", language, "metadata", "desktop") for language in NATIVE_BINDINGS}
    if family == "ios-validation":
        return instance in {PhaseInstanceId("sdk", "sdk-ios", "validation", target)
                            for target in ("ios-arm64", "ios-simulator-arm64")}
    if family == "ios-metadata":
        return instance == PhaseInstanceId("sdk", "sdk-ios", "metadata", "ios")
    if family.startswith("core-"):
        phase = family.removeprefix("core-")
        targets = SDK_FACADE_TARGETS if phase == "validation" else ("common",)
        return instance in {PhaseInstanceId("sdk", "sdk-core", phase, target) for target in targets}
    if family.startswith("android-"):
        return instance == PhaseInstanceId("sdk", "sdk-android", family.removeprefix("android-"), "android")
    return instance == (PhaseInstanceId("sdk", "sdk-ios", "package", "ios") if family == "ios-package"
                        else PhaseInstanceId("sdk", "javascript", "metadata", "node"))


def _runtime_worker_instance(instance):
    return instance.product == "runtime" and instance.component != "runtime-aggregate"


def runtime_worker_matrix(
    plan_path: Path, discovery_root: Path, state_root: Path | None = None, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    """Route only authenticated ready standalone phases, never the cheap aggregate.

    These rows elect jobs, not observed hosts or permission to skip the worker's
    own replay, requested-key check, toolchain observation or supervisor proof.
    """
    inspected = inspect_products(
        plan_path, discovery_root, state_root, repository_root=repository_root,
        environ=environ, sdk_validation_tooling=sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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


def _restore_product_objects(state, instances, destination):
    restored_objects = {}
    for dependency in instances:
        record = state.prior_carrier_phases[dependency]
        name = "-".join((dependency.product, dependency.component, dependency.phase, dependency.target))
        predecessor = destination / name
        predecessor.mkdir()
        restored = restore_object(
            state.sources[dependency], predecessor / "stage",
            build_key=record["buildKey"], receipt_sha256=record["receiptSha256"],
            object_sha256=record["objectSha256"],
        )
        (predecessor / "phase-receipt.json").write_bytes(restored["receiptBytes"])
        restored_objects[dependency] = restored
    return restored_objects


def _capture_sdk_runtime_predecessors(selected, destination):
    """Copy originals while the authenticated carrier is still privately captured."""
    result = {}
    for identity, original in selected["handoff"]["originalPhases"].items():
        if identity.product != "runtime":
            continue
        fields = tuple(getattr(identity, field) for field in _IDENTITY_KEYS)
        directory = destination / "-".join(fields)
        snapshot_regular_tree(original["stage"], directory / "stage")
        raw = selected["handoff"]["receiptBytes"][identity]
        if read_regular_file_bytes(original["receiptPath"]) != raw:
            raise ValueError("SDK Runtime original receipt changed during capture")
        receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
        manifest = verify_output_manifest_identity(directory / "stage", *fields, receipt["productVersion"])
        if tuple(receipt[field] for field in _IDENTITY_KEYS) != fields or receipt["outputs"] != manifest["outputs"]:
            raise ValueError("SDK Runtime original stage does not match its receipt")
        receipt_path = directory / "phase-receipt.json"
        receipt_path.write_bytes(raw)
        result[identity] = {"stage": directory / "stage", "receiptPath": receipt_path,
                            "receipt": receipt, "receiptBytes": raw}
    return result


def _materialize_product_predecessors(state, instance, destination, expected_build_key, root, *,
                                      sdk_runtime_originals=None, original_inventory=None):
    expected_build_key = require_sha256(expected_build_key, "Expected elected build key")
    if instance not in PHASE_INSTANCE_IDS:
        raise ValueError("Unknown product phase instance")
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Product phase is not ready with the expected elected build key")
    external = instance.product == "sdk" and state.rebased_request.get("sdkRuntimeSource") == "released-default"
    dependencies = tuple(dependency for dependency in _dependency_closure((instance,), sdk_runtime_external=external)
                         if dependency != instance)
    runtime_dependencies = tuple(dependency for dependency in _dependency_closure((instance,))
                                 if external and dependency.product == "runtime")
    if any(dependency not in state.sources for dependency in dependencies):
        raise ValueError("Elected product phase lacks an authenticated original predecessor")
    if any(dependency not in (sdk_runtime_originals or {}) for dependency in runtime_dependencies):
        raise ValueError("Elected SDK phase lacks an authenticated original Runtime predecessor")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-product-inputs-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "inputs"
        prepared.mkdir()
        restored_objects = _restore_product_objects(state, dependencies, prepared)
        for dependency in runtime_dependencies:
            original = sdk_runtime_originals[dependency]
            fields = tuple(getattr(dependency, field) for field in _IDENTITY_KEYS)
            predecessor = prepared / "-".join(fields)
            snapshot_regular_tree(original["stage"], predecessor / "stage")
            raw = read_regular_file_bytes(original["receiptPath"])
            if raw != original["receiptBytes"]:
                raise ValueError("Captured SDK Runtime receipt changed before publication")
            receipt = validate_phase_receipt(load_canonical_json_bytes(raw))
            manifest = verify_output_manifest_identity(predecessor / "stage", *fields, receipt["productVersion"])
            if tuple(receipt[field] for field in _IDENTITY_KEYS) != fields or receipt["outputs"] != manifest["outputs"]:
                raise ValueError("Captured SDK Runtime stage does not match its receipt")
            (predecessor / "phase-receipt.json").write_bytes(raw)
            restored_objects[dependency] = {"receipt": receipt, "receiptBytes": raw}
        write_canonical_json(prepared / "phase-plan.json", ready)
        write_canonical_json(prepared / "producer.json", state.producer)
        plan_bytes, producer_bytes = canonical_json_bytes(ready), canonical_json_bytes(state.producer)
        expected_files = []
        for dependency, restored in restored_objects.items():
            prefix = "-".join(getattr(dependency, field) for field in _IDENTITY_KEYS)
            receipt = restored["receipt"]
            receipt_bytes = restored["receiptBytes"]
            manifest = {"schemaVersion": 1, **{field: receipt[field] for field in
                ("product", "component", "phase", "target", "productVersion", "outputs")}}
            manifest_bytes = canonical_json_bytes(manifest)
            expected_files.extend([
                *({"relativePath": f"{prefix}/stage/{record['relativePath']}",
                   "bytes": record["bytes"], "sha256": record["sha256"]} for record in receipt["outputs"]),
                {"relativePath": f"{prefix}/stage/output-manifest.json", "bytes": len(manifest_bytes),
                 "sha256": sha256_bytes(manifest_bytes)},
                {"relativePath": f"{prefix}/phase-receipt.json", "bytes": len(receipt_bytes),
                 "sha256": sha256_bytes(receipt_bytes)},
            ])
        expected_files.extend([
            {"relativePath": "phase-plan.json", "bytes": len(plan_bytes), "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "producer.json", "bytes": len(producer_bytes), "sha256": sha256_bytes(producer_bytes)},
        ])
        expected_files.sort(key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared) != expected_files:
            raise ValueError("Product predecessors differ from authenticated original receipts")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
        if original_inventory is not None:
            original_inventory.extend(expected_files)
    return ready


@verification_scoped
def materialize_product_predecessors(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    instance: PhaseInstanceId, destination: Path, *, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    """Restore the full original closure, not new evidence or execution authority."""
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-runtime-inputs-", dir=root) as temporary:
        originals = {}
        state = _verified_product_state(
            plan_path, discovery_root, state_root, root,
            os.environ if environ is None else environ, sdk_validation_tooling,
            sdk_original_workflow_sha=sdk_original_workflow_sha,
            **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
            sdk_runtime_consumer=lambda selected: originals.update(
                _capture_sdk_runtime_predecessors(selected, Path(temporary) / "originals")),
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        return _materialize_product_predecessors(state, instance, destination, expected_build_key, root,
                                                sdk_runtime_originals=originals)


@verification_scoped
def materialize_sdk_default_inputs(
    plan_path, discovery_root, state_root, destination, *, keyring, keys_directory,
    repository_root=None, environ=None, sdk_validation_tooling=None,
    sdk_apple_validation_policy=None, sdk_original_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
):
    """Stage the elected SDK default, preserving both original provenance chains."""
    from products.runtime_sdk_handoff import stage_runtime_sdk_handoff
    from products.sdk_inputs import INVENTORY_NAME
    from products.sdk_package import _require_capability_output_separate
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)

    def output_safe():
        _require_capability_output_separate(destination, [Path(keyring), Path(keys_directory), discovery_root, state_root])
        if destination.exists() or destination.is_symlink():
            raise ValueError("SDK default destination must not exist")
        _prepare_destination(destination, root).rmdir()  # Only the newly created, empty destination.

    output_safe()
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-default-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "output"
        captured = {}
        runtime_files = []

        def capture(selected):
            if captured:
                raise ValueError("SDK default was captured more than once")
            source = selected["handoff"]["directory"]
            runtime_files.extend(regular_file_inventory(source, allow_empty=True))
            snapshot_regular_tree(source, prepared / "runtime-original", allow_empty=True)
            if regular_file_inventory(prepared / "runtime-original", allow_empty=True) != runtime_files:
                raise ValueError("SDK default Runtime original changed during capture")
            captured.update({"transportSource": selected["transportSource"],
                             "receiptSha256": selected["envelope"]["receiptSha256"],
                             "objectSha256": selected["envelope"]["objectSha256"]})

        state = _verified_product_state(plan_path, discovery_root, state_root, root,
            os.environ if environ is None else environ, sdk_validation_tooling,
            sdk_original_workflow_sha=sdk_original_workflow_sha,
            **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
            sdk_runtime_consumer=capture,
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        selection = _sdk_input_selection(state, root)
        if selection is None or selection["source"] != "released-default" or not captured:
            raise ValueError("SDK default inputs require selected released-default consumer work")
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        (prepared / "current-contract").mkdir()
        restored_contract = _restore_product_objects(state, _dependency_closure((contract,)), prepared / "current-contract")
        write_canonical_json(prepared / "selection.json", selection)
        transport = {**captured, "consumer": state.consumer}
        write_canonical_json(prepared / "transport.json", transport)
        staged_sdk = stage_runtime_sdk_handoff(prepared / "runtime-original", prepared / "sdk-inputs",
            sdk_version=selection["sdkVersion"], compatible_release_range=selection["compatibleReleaseRange"],
            compatible_runtime_compatibility_range=selection["compatibleRuntimeCompatibilityRange"],
            keyring=keyring, keys_directory=keys_directory,
            selection_repository_root=root, selection_revision=state.producer["commit"],
            expected_contract_payload_sha256=selection["contractPayloadSha256"])
        # Both original replay and full SDK authentication have exited before publication.
        expected_files = [
            *({**record, "relativePath": f"runtime-original/{record['relativePath']}"} for record in runtime_files),
            *({**record, "relativePath": f"sdk-inputs/{record['relativePath']}"}
              for record in staged_sdk["inventory"]["files"]),
        ]
        inventory_bytes = canonical_json_bytes(staged_sdk["inventory"])
        if sha256_bytes(inventory_bytes) != staged_sdk["inventorySha256"]:
            raise ValueError("SDK default staged inventory differs from its verified writer")
        expected_files.append({"relativePath": f"sdk-inputs/{INVENTORY_NAME}", "bytes": len(inventory_bytes),
                               "sha256": staged_sdk["inventorySha256"]})
        for identity, restored in restored_contract.items():
            prefix = "current-contract/" + "-".join(getattr(identity, field) for field in _IDENTITY_KEYS)
            receipt = restored["receipt"]
            manifest = {"schemaVersion": 1, **{field: receipt[field] for field in
                ("product", "component", "phase", "target", "productVersion", "outputs")}}
            manifest_bytes, receipt_bytes = canonical_json_bytes(manifest), restored["receiptBytes"]
            expected_files.extend([
                *({"relativePath": f"{prefix}/stage/{record['relativePath']}",
                   "bytes": record["bytes"], "sha256": record["sha256"]} for record in receipt["outputs"]),
                {"relativePath": f"{prefix}/stage/output-manifest.json", "bytes": len(manifest_bytes),
                 "sha256": sha256_bytes(manifest_bytes)},
                {"relativePath": f"{prefix}/phase-receipt.json", "bytes": len(receipt_bytes),
                 "sha256": sha256_bytes(receipt_bytes)},
            ])
        for name, value in (("selection.json", selection), ("transport.json", transport)):
            raw = canonical_json_bytes(value)
            expected_files.append({"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared, allow_empty=True) != expected_files:
            raise ValueError("SDK default inputs differ from authenticated originals")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return selection


@verification_scoped
def materialize_runtime_aggregate_release_evidence(
    plan_path, discovery_root, state_root, destination, *, expected_build_key,
    keyring, keys_directory, repository_root=None, environ=None, sdk_validation_tooling=None,
    sdk_apple_validation_policy=None, sdk_original_workflow_sha=None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
):
    """Select the complete original carrier; selected-stage equality is checked by the caller."""
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    state = _verified_product_state(plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    instance = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
    selected = state.prior_by_instance.get(instance)
    if (selected is None or instance not in state.sources or instance not in state.prior_carrier_phases
            or selected["buildKey"] != require_sha256(expected_build_key, "Aggregate selected key")):
        raise ValueError("Aggregate release evidence lacks its selected original metadata")
    request = dict(state.rebased_request)
    _merge_native_comparison_records(request, _retained_aggregate_handoffs(state_root, root), key=_AGGREGATE_REQUEST_KEY)
    records = [record for record in request.get(_AGGREGATE_REQUEST_KEY, [])
               if record["receiptSha256"] == selected["receiptSha256"]]
    if not records:
        return None
    captured = stage_runtime_aggregate_release_evidence(records, root, destination,
        keyring=keyring, keys_directory=keys_directory)
    return destination / captured[0]["handoffRoot"]


def prepare_runtime_phase(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    instance: PhaseInstanceId, destination: Path, *, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, str]:
    """Prepare original worker inputs; never execute or grant hosted acceptance."""
    if instance not in PHASE_INSTANCE_IDS or instance.product != "runtime" or instance.component == "runtime-aggregate":
        raise ValueError("Unsupported Runtime worker phase")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)
    state = _verified_product_state(
        plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    return _prepare_runtime_phase(state, instance, destination, expected_build_key, root)[0]


@verification_scoped
def materialize_runtime_attestation_inputs(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    destination: Path, *, target: str, expected_build_key: str,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    retained_release_keyring: Path | None = None,
    retained_release_keys_directory: Path | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    """Restore a completed native or aggregate closure, not a new build election.

The protected caller separately authenticates original CI/release sources and
the complete product semantics. This selection never grants signing authority.
"""
    if target not in (*NATIVE_TARGETS, "aggregate"):
        raise ValueError("Runtime attestation selection requires a native or aggregate target")
    if ((retained_release_keyring is None) != (retained_release_keys_directory is None)
            or target == "aggregate" and retained_release_keyring is not None):
        raise ValueError("Retained native release selection requires paired caller policy")
    require_sha256(expected_build_key, "Selected Runtime metadata build key")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(
        root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime attestation selection destination must not exist")
    state = _verified_product_state(plan_path, discovery_root, state_root, root,
        os.environ if environ is None else environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    _runtime_worker_checkout(root, state.producer)
    metadata = PhaseInstanceId("runtime", "runtime-aggregate" if target == "aggregate" else target, "metadata", target)
    selected = state.prior_by_instance.get(metadata)
    instances = _dependency_closure((metadata,))
    if (selected is None or selected["buildKey"] != expected_build_key
            or any(instance not in state.sources or instance not in state.prior_carrier_phases
                   for instance in instances)):
        raise ValueError("Selected Runtime metadata lacks its exact complete retained closure")
    evidence = state.rebased_request["contractEvidence"]
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("Runtime attestation selection requires release Contract evidence")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="runtime-attestation-selection-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "selection"
        inputs = prepared / "predecessors"
        inputs.mkdir(parents=True)
        restored_objects = _restore_product_objects(state, instances, inputs)

        def original(product, component, phase, target):
            identity = PhaseInstanceId(product, component, phase, target)
            if identity not in instances:
                raise ValueError("Runtime attestation requested an unrelated original")
            directory = inputs / "-".join((product, component, phase, target))
            receipt_path = directory / "phase-receipt.json"
            receipt = _canonical_control(receipt_path, "Runtime attestation original receipt")
            return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

        def one_output(value, kind):
            outputs = [record for record in value["receipt"]["outputs"] if record["kind"] == kind]
            if len(outputs) != 1:
                raise ValueError(f"Runtime attestation requires one original {kind} output")
            return value["stage"] / outputs[0]["relativePath"]

        trust = _release_trust(root, state.producer["commit"], prepared)
        if trust is None:
            raise ValueError("Runtime attestation selection has no Git-authoritative release policy")
        contract, version, handoff, _, handoff_files = _capture_runtime_contract(
            root, evidence, original, one_output, prepared, trust)

        retained_inventories = {}
        retained_policy = None

        def publish_selection(selection, retained=()):
            keyring_bytes = git_regular_blob_bytes(root, state.producer["commit"], _KEYRING_PATH,
                                                   max_bytes=64 * 1024)
            keyring_value = load_canonical_json_bytes(keyring_bytes)
            key_records = [record for record in (keyring_value["activeKey"], *keyring_value["retiredKeys"])
                           if record is not None]
            expected_files = [
                {"relativePath": "trust/product-signing-keys.json", "bytes": len(keyring_bytes),
                 "sha256": sha256_bytes(keyring_bytes)},
                *({**record, "relativePath": f"contract-input/{record['relativePath']}"}
                  for record in handoff_files),
            ]
            for record in key_records:
                key_id = record["keyId"]
                raw = git_regular_blob_bytes(root, state.producer["commit"],
                                             f"{_KEYS_ROOT}/{key_id}.pub", max_bytes=64 * 1024)
                expected_files.append({"relativePath": f"trust/keys/{key_id}.pub",
                                       "bytes": len(raw), "sha256": sha256_bytes(raw)})
            for identity, restored in restored_objects.items():
                name = "-".join(getattr(identity, field) for field in _IDENTITY_KEYS)
                stage = f"predecessors/{name}/stage"
                if target != "aggregate" and identity.product == "runtime" and identity.component == target \
                        and identity.target == target and identity.phase in {"binary", "package", "validation", "metadata"}:
                    stage = f"runtime/{target}/{identity.phase}"
                receipt = restored["receipt"]
                manifest = {"schemaVersion": 1, **{field: receipt[field] for field in
                    ("product", "component", "phase", "target", "productVersion", "outputs")}}
                manifest_bytes, receipt_bytes = canonical_json_bytes(manifest), restored["receiptBytes"]
                expected_files.extend([
                    *({"relativePath": f"{stage}/{record['relativePath']}",
                       "bytes": record["bytes"], "sha256": record["sha256"]} for record in receipt["outputs"]),
                    {"relativePath": f"{stage}/output-manifest.json", "bytes": len(manifest_bytes),
                     "sha256": sha256_bytes(manifest_bytes)},
                    {"relativePath": f"predecessors/{name}/phase-receipt.json", "bytes": len(receipt_bytes),
                     "sha256": sha256_bytes(receipt_bytes)},
                ])
            if retained:
                for path in retained:
                    prefix = path.relative_to(prepared).as_posix()
                    expected_files.extend(
                        {**record, "relativePath": f"{prefix}/{record['relativePath']}"}
                        for record in retained_inventories[path])
                policy_bytes, keys_inventory = retained_policy
                if (any(read_regular_file_bytes(
                            retained_release_keyring if name == "product-signing-keys.json"
                            else retained_release_keys_directory / name.removeprefix("keys/"),
                            max_bytes=64 * 1024, reject_symlink_parents=True) != raw
                        for name, raw in policy_bytes.items())
                        or regular_file_inventory(retained_release_keys_directory) != keys_inventory):
                    raise ValueError("Retained Runtime caller policy changed after capture")
            selection_bytes = canonical_json_bytes(selection)
            expected_files.append({"relativePath": "selection.json", "bytes": len(selection_bytes),
                                   "sha256": sha256_bytes(selection_bytes)})
            expected_files.sort(key=lambda record: record["relativePath"])
            if regular_file_inventory(prepared) != expected_files:
                raise ValueError("Runtime attestation selection differs from authenticated originals")
            publish_regular_tree(prepared, destination, expected_inventory=expected_files)

        if target == "aggregate":
            value = original("runtime", "runtime-aggregate", "metadata", "aggregate")
            selection = {
                "schemaVersion": 1, "target": target, "metadata": selected,
                "producer": state.producer, "contractVersion": version,
                "aggregateStage": value["stage"].relative_to(prepared).as_posix(),
                "aggregateReceipt": value["receiptPath"].relative_to(prepared).as_posix(),
                "aggregateManifest": one_output(value, "runtime-aggregate").relative_to(prepared).as_posix(),
                "originals": [{**_identity_record(instance),
                    "receiptSha256": state.prior_carrier_phases[instance]["receiptSha256"],
                    "directory": "predecessors/" + "-".join((instance.product, instance.component,
                                                               instance.phase, instance.target))}
                    for instance in instances],
                "contractHandoff": handoff.relative_to(prepared).as_posix(),
            }
            write_canonical_json(prepared / "selection.json", selection)
            _runtime_worker_checkout(root, state.producer)
            publish_selection(selection)
            return selection
        phase_receipts = {}
        payload = None
        for phase in ("binary", "package", "validation", "metadata"):
            value = original("runtime", target, phase, target)
            moved = prepared / "runtime" / target / phase
            moved.parent.mkdir(parents=True, exist_ok=True)
            if phase == "metadata":
                relative = one_output(value, "runtime-variant").relative_to(value["stage"])
                payload = moved / relative
            value["stage"].rename(moved)  # Move only the freshly restored private copy.
            phase_receipts[phase] = value["receiptPath"].relative_to(prepared).as_posix()
        stem = f"codex-agent-contract-{version}"
        paths = {"stage": contract["stage"], "receipt": contract["receiptPath"],
                 "payload": handoff / f"{stem}.zip", "attestation": handoff / f"{stem}.attestation.json",
                 "signature": handoff / f"{stem}.attestation.sig", "public_key": handoff / "public-key.pub"}
        selection = {
            "schemaVersion": 1, "target": target, "metadata": selected,
            "producer": state.producer, "contractVersion": version,
            "contract": {name: path.relative_to(prepared).as_posix() for name, path in paths.items()},
            "contractReceiptSha256": state.prior_carrier_phases[
                PhaseInstanceId("contract", "contract", "metadata", "common")]["receiptSha256"],
            "receiptSha256s": {phase: state.prior_carrier_phases[
                PhaseInstanceId("runtime", target, phase, target)]["receiptSha256"] for phase in phase_receipts},
            "phaseReceipts": phase_receipts, "runtimeStageRoot": "runtime",
            "variantPayload": payload.relative_to(prepared).as_posix(),
        }
        if retained_release_keyring is not None:
            from products.runtime_variant_handoff import capture_runtime_variant_handoffs
            policy = load_keyring(retained_release_keyring, retained_release_keys_directory)
            policy_bytes = {"product-signing-keys.json": read_regular_file_bytes(
                retained_release_keyring, max_bytes=64 * 1024, reject_symlink_parents=True)}
            for record in (policy["activeKey"], *policy["retiredKeys"]):
                if record is not None:
                    policy_bytes[f"keys/{record['keyId']}.pub"] = read_regular_file_bytes(
                        public_key_path(retained_release_keys_directory, record["keyId"]),
                        max_bytes=64 * 1024, reject_symlink_parents=True)
            retained_policy = (
                policy_bytes, regular_file_inventory(retained_release_keys_directory))
            request = dict(state.rebased_request)
            _merge_native_comparison_records(request, _retained_native_handoffs(state_root, root))
            retained = capture_runtime_variant_handoffs(
                request.get("nativeRuntimeComparisonEvidence", []), root,
                prepared / "retained-release-handoffs", target=target,
                phase_receipts={phase: prepared / path for phase, path in phase_receipts.items()},
                keyring=retained_release_keyring, keys_directory=retained_release_keys_directory,
                original_inventories=retained_inventories, expected_policy=policy_bytes)
            selection["releaseHandoffs"] = [path.relative_to(prepared).as_posix() for path in retained]
        write_canonical_json(prepared / "selection.json", selection)
        _runtime_worker_checkout(root, state.producer)
        publish_selection(selection, retained if retained_release_keyring is not None else ())
    return selection


def _capture_runtime_contract(root, evidence, original, one_output, prepared, trust):
    contract = original("contract", "contract", "metadata", "common")
    version = contract["receipt"]["productVersion"]
    stem = f"codex-agent-contract-{version}"
    handoff = prepared / "contract-input"
    handoff.mkdir()
    expected_files = []
    for source, name, limit in (
        (one_output(contract, "contract-bundle"), f"{stem}.zip", 512 * 1024 * 1024),
        (root / evidence["attestation"], f"{stem}.attestation.json", 16 * 1024 * 1024),
        (root / evidence["attestationSignature"], f"{stem}.attestation.sig", 1024 * 1024),
        (root / evidence["publicKey"], "public-key.pub", 1024 * 1024),
    ):
        raw = read_regular_file_bytes(source, max_bytes=limit, reject_symlink_parents=True)
        (handoff / name).write_bytes(raw)
        expected_files.append({"relativePath": name, "bytes": len(raw), "sha256": sha256_bytes(raw)})
    closure_source = (root / evidence["attestation"]).parent / "execution-closure"
    closure_files = regular_file_inventory(closure_source)
    snapshot_regular_tree(closure_source, handoff / "execution-closure")
    if regular_file_inventory(handoff / "execution-closure") != closure_files:
        raise ValueError("Runtime worker Contract closure changed during capture")
    expected_files.extend({**record, "relativePath": f"execution-closure/{record['relativePath']}"}
                          for record in closure_files)
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
    expected_files.sort(key=lambda record: record["relativePath"])
    if regular_file_inventory(handoff) != expected_files:
        raise ValueError("Runtime worker Contract handoff changed before publication")
    return contract, version, handoff, manifest, expected_files


def _prepare_runtime_phase(state, instance, destination, expected_build_key, root):
    evidence = state.rebased_request["contractEvidence"]
    if evidence is None or evidence["expectedTrustDomain"] != "release":
        raise ValueError("Runtime worker requires authenticated release Contract evidence")
    destination = _prepare_destination(destination, root)
    destination.rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-worker-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "worker"
        prepared.mkdir()
        expected_files = []
        trust = _release_trust(root, state.plan["validationCommit"], prepared,
                               original_inventory=expected_files)
        if trust is None:
            raise ValueError("Runtime worker requires Git-authoritative release policy")
        inputs = prepared / "predecessors"
        predecessor_files = []
        ready = _materialize_product_predecessors(state, instance, inputs, expected_build_key, root,
                                                  original_inventory=predecessor_files)
        expected_files.extend({**record, "relativePath": f"predecessors/{record['relativePath']}"}
                              for record in predecessor_files)

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

        contract, version, handoff, manifest, handoff_files = _capture_runtime_contract(
            root, evidence, original, one_output, prepared, trust)
        expected_files.extend({**record, "relativePath": f"contract-input/{record['relativePath']}"}
                              for record in handoff_files)
        stem = f"codex-agent-contract-{version}"
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
                binary_plan_value = binary_plan(
                    ready, repository_root=root, revision=state.producer["commit"],
                    contract_projection=projection, verified_contract_manifest=manifest,
                    runtime_version=state.expected_fixed["versions"]["runtime-release"])
                write_canonical_json(binary_plan_path, binary_plan_value)
                binary_plan_bytes = canonical_json_bytes(binary_plan_value)
                expected_files.append({"relativePath": "runtime-binary-plan.json",
                                       "bytes": len(binary_plan_bytes), "sha256": sha256_bytes(binary_plan_bytes)})

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
                validation_files = []
                _materialize_runtime_validation_handoffs(
                    (instance,), state.prior_by_instance, state.sources,
                    prepared / "runtime-validation", root, original_inventory=validation_files)
                expected_files.extend({**record, "relativePath": f"runtime-validation/{record['relativePath']}"}
                                      for record in validation_files)
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
        properties_bytes = canonical_json_bytes(properties)
        expected_files.append({"relativePath": "gradle-properties.json", "bytes": len(properties_bytes),
                               "sha256": sha256_bytes(properties_bytes)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared) != expected_files:
            raise ValueError("Runtime worker inputs differ from authenticated originals")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return properties, manifest


def _runtime_worker_checkout(root, producer):
    if (_git_value(root, "rev-parse", "HEAD") != producer["commit"]
            or _git_value(root, "rev-parse", "HEAD^{tree}") != producer["tree"]
            or _git_value(root, "diff", "--name-only", "HEAD")):
        raise ValueError("Runtime worker requires the exact unchanged tracked checkout")
    untracked = _git_value(root, "ls-files", "--others", "--",
                          "runtime", "codex-agent-runtime-desktop", "ci", "gradle", "legal", "build-logic",
                          "codex-agent-core", "codex-agent-sdk", "codex-agent-bindings",
                          "codex-agent-runtime-android", "codex-agent-runtime-ios",
                          ":(glob)**/*.py", ":(glob)**/*.pyc", ":(glob)**/*.pyo",
                          "sitecustomize", "usercustomize", ":(glob)sitecustomize.*", ":(glob)usercustomize.*",
                          ":(exclude).codex/**", ":(exclude)**/build/**",
                          ":(exclude)**/.gradle/**", ":(exclude)**/__pycache__/**")
    if untracked:
        raise ValueError(f"Runtime worker rejects untracked source or build policy: {untracked.splitlines()[:20]!r}")


def _runtime_worker_command(wrapper, properties, environment, *, build_directory="runtime", platform_name=None,
                            init_script=None):
    platform_name = os.name if platform_name is None else platform_name
    if platform_name not in {"posix", "nt"}:
        raise ValueError("Product worker requires an exact supported command platform")
    if build_directory not in {"runtime", "."}:
        raise ValueError("Product worker requires the fixed Runtime or root SDK build")
    verified_fetch = environment.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH", "")
    if verified_fetch not in {"", "true"} or (verified_fetch and build_directory != "runtime"):
        raise ValueError("Verified dependency fetch is only supported for Runtime product workers")
    command = [str(wrapper), *(["--dependency-verification=strict"] if verified_fetch else ["--offline"]),
               "--no-daemon", "--configuration-cache",
               "--configuration-cache-problems=fail", "-p", build_directory, "ciProductPhase",
               *(f"-P{key}={value}" for key, value in sorted(properties.items()))]
    if init_script is not None:
        command[1:1] = ["-I", str(init_script)]
    if platform_name == "nt":
        java_home = environment.get("JAVA_HOME", "")
        if not ntpath.isabs(java_home):
            raise ValueError("Windows Runtime worker requires absolute JAVA_HOME")
        # Use the exact launcher used by gradlew.bat, without a command shell.
        command = [ntpath.join(java_home, "bin", "java.exe"), "-Xmx64m", "-Xms64m",
                   "-Dorg.gradle.appname=gradlew", "-jar",
                   ntpath.join(ntpath.dirname(str(wrapper)), "gradle", "wrapper", "gradle-wrapper.jar"),
                   *command[1:]]
    return command


def _provision_runtime_native_toolchain(root, revision, component, destination, environment):
    if environment.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH") != "true":
        return {}
    runner_temp = Path(environment.get("RUNNER_TEMP", ""))
    if not runner_temp.is_absolute() or not runner_temp.is_dir() or runner_temp.is_symlink():
        raise ValueError("Native Runtime bootstrap requires a regular absolute runner temp directory")
    from products.toolchain_capture_bootstrap import prepare

    if component in {"macos-arm64", "macos-x64", "linux-x64"}:
        konan_home = runner_temp / f"codex-runtime-konan-{component}"
        konan_home.mkdir(mode=0o700)  # Fresh and stable: Kotlin/Native embeds this path in native output.
    else:
        konan_home = Path(tempfile.mkdtemp(prefix="codex-runtime-konan-", dir=runner_temp))
    environment["KONAN_DATA_DIR"] = str(konan_home)
    paths = prepare(root, revision, component, destination / "toolchain-bootstrap", konan_home)
    return {"codexAgent.kotlinPluginJar": paths["plugin"], "codexAgent.nativeArchive": paths["archive"],
            "kotlin.native.home": paths["compiler"]}


def _allow_locked_runtime_node_fetch(instance, environment):
    if (instance.component in {"node-js", "node-wasm"} and instance.phase == "binary" and
            environment.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH") == "true"):
        environment["npm_config_offline"] = "false"
        environment["npm_config_registry"] = "https://registry.npmjs.org/"


def _runtime_worker_environment(root, producer, destination, environ, *, build_directory="runtime"):
    from products.gradle_bootstrap import require_preprovisioned_gradle, seed_sdk_gradle_dependencies
    if build_directory not in {"runtime", "."}:
        raise ValueError("Product worker requires the fixed Runtime or root SDK build")
    if build_directory == "." and environ.get("CODEX_AGENT_VERIFIED_DEPENDENCY_FETCH", ""):
        raise ValueError("SDK product commands remain offline after verified dependency seeding")
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
    properties_path = "gradle/wrapper/gradle-wrapper.properties"
    properties = read_regular_file_bytes(root / properties_path, reject_symlink_parents=True)
    if properties != git_regular_blob_bytes(root, producer["commit"], properties_path, max_bytes=64 * 1024):
        raise ValueError("Runtime worker wrapper properties differ from exact Git source")
    require_preprovisioned_gradle(properties, environment)
    if build_directory == ".":
        seed = destination.parent / (destination.name + "-dependency-seed")
        if seed.exists() or seed.is_symlink():
            raise ValueError("SDK dependency seed namespace must be fresh")
        seed = _prepare_destination(seed, root)
        seed.rmdir()
        seed_sdk_gradle_dependencies(root, producer["commit"], wrapper, environment, seed)
        _runtime_worker_checkout(root, producer)
    return environment, wrapper


def execute_runtime_supervisor(
    plan_path: Path, discovery_root: Path, state_root: Path | None, destination: Path, *,
    expected_build_key: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    from native_wrappers import host_classifier
    from runtime_supervisor import execute_supervisor

    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime supervisor worker destination must not exist")
    environment = dict(os.environ if environ is None else environ)
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    instance = PhaseInstanceId("runtime", "linux-arm64", "binary", "linux-arm64")
    ready = state.prior_ready_plans.get(instance)
    if ready is None or ready["buildKey"] != expected_build_key:
        raise ValueError("Runtime supervisor is not ready with the expected elected build key")
    if host_classifier() != "linux-arm64":
        raise ValueError("Runtime supervisor requires the actual Linux ARM64 host")
    _runtime_worker_environment(root, state.producer, destination / "supervisor-diagnostics", environment)
    properties, manifest = _prepare_runtime_phase(state, instance, destination / "inputs", expected_build_key, root)
    full_plan = _canonical_control(Path(properties["codexAgent.runtimeBinaryPlan"]), "Prepared supervisor binary plan")
    if canonical_json_bytes(full_plan) != canonical_json_bytes(ready):
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
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    supervisor_upload: Mapping[str, Any] | None = None,
    app_server_archive: Path | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
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
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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
    _allow_locked_runtime_node_fetch(instance, environment)
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
        if canonical_json_bytes(full_plan) != canonical_json_bytes(ready):
            raise ValueError("Prepared binary plan differs from the original elected plan")
        verify_supervisor_handoff(
            captured / "original", repository_root=root, revision=state.producer["commit"],
            phase_plan=full_plan, contract_manifest=manifest, producer=state.producer,
            runtime_version=state.expected_fixed["versions"]["runtime-release"])
        properties["codexAgent.desktopSupervisorDirectory"] = str(captured / "original")
    if needs_archive:
        properties.update(_provision_runtime_native_toolchain(
            root, state.producer["commit"], instance.component, destination, environment))
    input_inventory = regular_file_inventory(destination / "inputs", allow_empty=True)
    _runtime_worker_checkout(root, state.producer)
    if stage.exists() or stage.is_symlink():
        raise ValueError("Runtime worker output stage appeared before execution")
    init_script = None
    if instance.component == "node-js" and instance.phase == "binary":
        init_script = root / "codex-agent-runtime-desktop/src/jsMain/gradle/deterministic-compiler.init.gradle"
    elif instance.component in {"macos-arm64", "macos-x64", "linux-x64", "windows-x64"} and instance.phase == "binary":
        source_set = {"macos-arm64": "macosArm64Main", "macos-x64": "macosX64Main",
                      "linux-x64": "linuxX64Main", "windows-x64": "mingwMain"}[instance.component]
        init_script = root / f"codex-agent-runtime-desktop/src/{source_set}/gradle/deterministic-native-link.init.gradle"
        if instance.component == "windows-x64":
            if environment.get("LINK") not in {None, "", "/Brepro"}:
                raise ValueError("Windows worker rejects injected MSVC linker options")
            environment["LINK"] = "/Brepro"
    if init_script is not None:
        if read_regular_file_bytes(init_script, reject_symlink_parents=True) != git_regular_blob_bytes(
                root, state.producer["commit"], init_script.relative_to(root).as_posix(), max_bytes=64 * 1024):
            raise ValueError(f"{instance.component} compiler policy differs from its exact Git source")
    command = _runtime_worker_command(wrapper, properties, environment, init_script=init_script)
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
    if instance.component in NATIVE_TARGETS and instance.phase == "validation":
        from products.runtime_validation_projection import project_native_validation_stage
        project_native_validation_stage(
            stage, Path(properties["codexAgent.runtimePackageStage"]), destination / "raw-validation",
            target=instance.component, version=state.expected_fixed["versions"]["runtime-release"],
            producer=state.producer,
        )
    return finalize_phase_object(
        stage_root=stage, phase_plan={key: ready[key] for key in PHASE_PLAN_KEYS}, producer=state.producer,
        product_version=state.expected_fixed["versions"]["runtime-release"],
        trust_domain="development" if state.plan["event"] == "pull_request" else "release",
        destination=destination / "shard")


def execute_sdk_metadata(
    plan_path: Path, discovery_root: Path, state_root: Path | None, destination: Path, *,
    component: str, expected_build_key: str, compatibility_request: Path,
    runtime_stages: Path, staged_sdks: Path, sdk_validation_tooling: Mapping[str, Any],
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    """Execute only an exact metadata election after replaying its original SDK hosts."""
    from sdk_metadata_phase import execute
    from products.sdk_validation import sdk_validation_provider

    if component not in NATIVE_BINDINGS:
        raise ValueError("SDK metadata worker requires an exact native language")
    instance = PhaseInstanceId("sdk", component, "metadata", "desktop")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("SDK metadata worker destination must not exist")
    for source in (compatibility_request, runtime_stages, staged_sdks):
        _product_materialization_paths(root, Path(source), Path(source), destination)
    environment = dict(os.environ if environ is None else environ)
    with tempfile.TemporaryDirectory(prefix="codex-agent-sdk-runtime-inputs-", dir=root) as temporary:
        originals = {}
        state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling,
            sdk_original_workflow_sha=sdk_original_workflow_sha,
            **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
            sdk_runtime_consumer=lambda selected: originals.update(
                _capture_sdk_runtime_predecessors(selected, Path(temporary) / "originals")),
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        ready = state.prior_ready_plans.get(instance)
        if ready is None or ready["buildKey"] != require_sha256(expected_build_key, "SDK metadata elected key"):
            raise ValueError("SDK metadata is not ready with the expected elected build key")
        _runtime_worker_checkout(root, state.producer)
        inputs = destination / "inputs"
        _materialize_product_predecessors(state, instance, inputs, expected_build_key, root,
                                        **({"sdk_runtime_originals": originals} if originals else {}))

    def original(product, name, phase, target):
        dependency = PhaseInstanceId(product, name, phase, target)
        if dependency not in phase_instance_dependencies(instance):
            raise ValueError("SDK metadata requested an unrelated direct predecessor")
        directory = inputs / "-".join((product, name, phase, target))
        receipt_path = directory / "phase-receipt.json"
        receipt = validate_phase_receipt(_canonical_control(receipt_path, "Original SDK metadata predecessor"))
        if tuple(receipt[field] for field in ("product", "component", "phase", "target")) != (product, name, phase, target):
            raise ValueError("SDK metadata original predecessor identity mismatch")
        return {"stage": directory / "stage", "receiptPath": receipt_path, "receipt": receipt}

    request = dict(state.rebased_request)
    _merge_native_comparison_records(request, _retained_sdk_handoffs(state_root, root), key="sdkValidationEvidence")
    provider = sdk_validation_provider(root, request.get("sdkValidationEvidence", []), repository=root,
        policy_revision=state.producer["commit"], tooling=sdk_validation_tooling)
    if provider is None:
        raise ValueError("SDK metadata requires authenticated original host evidence")
    projections = []
    for dependency in sdk_validation_dependencies(instance):
        value = original(dependency.product, dependency.component, dependency.phase, dependency.target)
        projections.append(provider({**value["receipt"], "receiptSha256": sha256_file(value["receiptPath"])}))
    policy = require_exact_keys(dict(sdk_validation_tooling),
        {"evidence", "publicKey", "javaExecutable", "requiredTrustDomain", "keyring", "keysDirectory"},
        "SDK metadata caller tooling policy")
    return execute(ready, producer=state.producer, sdk_version=state.expected_fixed["versions"]["sdk"],
        trust_domain="development" if state.plan["event"] == "pull_request" else "release",
        repository_root=root, destination=destination / "worker", predecessor=original,
        compatibility_request=Path(compatibility_request), runtime_stages=Path(runtime_stages), staged_sdks=Path(staged_sdks),
        sdk_validation_projections=tuple(projections), tooling_evidence=Path(policy["evidence"]),
        tooling_public_key=Path(policy["publicKey"]), java_executable=Path(policy["javaExecutable"]),
        policy_revision=state.producer["commit"], required_trust_domain=policy["requiredTrustDomain"], environ=environment,
        tooling_keyring=Path(policy["keyring"]) if policy["keyring"] is not None else None,
        tooling_keys_directory=Path(policy["keysDirectory"]) if policy["keysDirectory"] is not None else None)


def execute_runtime_aggregate(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    destination: Path, *, expected_build_key: str, variant_trust_root: Path,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
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
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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


def _worker_job_name(product: str, instance: PhaseInstanceId) -> str:
    component = instance.component if product == "sdk" and instance.component in {
        "sdk-core", "sdk-android"} else f"{product}-{instance.component}"
    return f"product-validation / {component}-{instance.phase}-{instance.target}"


def collect_runtime_workers(
    plan_path: Path, discovery_root: Path, state_root: Path | None, destination: Path, *,
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    runtime_aggregate_only: bool = False,
    sdk_javascript_only: bool = False,
    sdk_ios_binary_only: bool = False,
    sdk_family: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
    sdk_worker_workflow_path: str | None = None, sdk_worker_job_name: str | None = None,
) -> dict[str, Any]:
    """Collect elected Runtime or JavaScript SDK rows without erasing originals.

    This external report is not receipt authority. advance_products verifies
    successful original shards again and enforces its exact elected partition.
    """
    if (any(type(value) is not bool for value in (runtime_aggregate_only, sdk_javascript_only, sdk_ios_binary_only))
            or sum((runtime_aggregate_only, sdk_javascript_only, sdk_ios_binary_only, sdk_family is not None)) > 1):
        raise ValueError("Worker collection scopes must be boolean and mutually exclusive")
    if sdk_family is not None:
        _sdk_family_worker_instance(None, sdk_family)
    if sdk_original_workflow_sha is not None and sdk_original_workflow_sha != trusted_workflow_sha:
        raise ValueError("SDK original workflow pin differs from worker collection pin")
    if (sdk_worker_workflow_path is None) != (sdk_worker_job_name is None):
        raise ValueError("SDK collection child workflow path and job must be pinned together")
    if sdk_worker_workflow_path is not None and (
            sdk_family not in {"core-binary", "core-package", "core-validation", "core-metadata",
                               "android-binary", "android-package"}
            or type(sdk_worker_workflow_path) is not str
            or re.fullmatch(r"\.github/workflows/[a-z0-9-]+\.yml", sdk_worker_workflow_path) is None
            or type(sdk_worker_job_name) is not str or not sdk_worker_job_name):
        raise ValueError("SDK collection requires one valid caller-pinned child route")
    if sdk_family == "core-validation" and sdk_worker_job_name is not None and re.fullmatch(
            r"product-validation / [a-z0-9-]+ / sdk-core-validation-\{target\}", sdk_worker_job_name) is None:
        raise ValueError("Core validation child route requires one exact target job template")
    product = "sdk" if sdk_javascript_only or sdk_ios_binary_only or sdk_family is not None else "runtime"
    root = (Path(__file__).resolve().parents[1] if repository_root is None else repository_root).resolve()
    discovery_root, state_root, destination = _product_materialization_paths(root, discovery_root, state_root, destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime collection destination must not exist")
    environment = os.environ if environ is None else environ
    state = _verified_product_state(plan_path, discovery_root, state_root, root, environment, sdk_validation_tooling,
        sdk_original_workflow_sha=trusted_workflow_sha,
        **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}),
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
    producer = state.producer
    selected = [(instance, ready) for instance, ready in sorted(state.prior_ready_plans.items())
                if (_sdk_family_worker_instance(instance, sdk_family) if sdk_family is not None else
                    _sdk_ios_binary_worker_instance(instance) if sdk_ios_binary_only else
                    _sdk_javascript_worker_instance(instance) if sdk_javascript_only else
                    (instance == PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
                     if runtime_aggregate_only else _runtime_worker_instance(instance)))]
    if sdk_worker_workflow_path is not None:
        if sdk_family != "core-validation" and (len(selected) > 1 or "{" in sdk_worker_job_name
                                                or "}" in sdk_worker_job_name):
            raise ValueError("SDK collection child route requires one exact worker")
    observed, artifacts, jobs = [], [], []
    if selected:
        observed = _observe_ci_producer_jobs(
            {"resume": producer}, jobs_by_phase={"resume": "product-validation / product-resume"},
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        jobs = observed[0]["jobs"]
        if sdk_worker_workflow_path is not None:
            _require_ci_workflow_reference(observed[0]["run"],
                f"codex-agent-labs/codex-agent/{sdk_worker_workflow_path}@{trusted_workflow_sha}",
                trusted_workflow_sha)
        artifacts = paginated_items(
            f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{producer['runId']}/artifacts",
            "artifacts", token)
    for instance, _ready in selected:
        name = (sdk_worker_job_name.replace("{target}", instance.target) if sdk_family == "core-validation"
                and sdk_worker_job_name is not None else sdk_worker_job_name or _worker_job_name(product, instance))
        matrix_key = _ready["buildKey"] if product == "sdk" and sdk_worker_job_name is None else None
        if any(job.get("status") != "completed" for job in
               _matching_ci_jobs(jobs, name, expected_build_key=matrix_key)):
            raise ValueError("An elected Runtime worker is still running; collect after all siblings finish")
        if sdk_family == "ios-validation":
            signer = f"product-validation / sdk-apple-validation-attestation-{instance.target}"
            if any(job.get("name") == signer and job.get("status") != "completed" for job in jobs):
                raise ValueError("An elected Apple signer is still running; collect after all siblings finish")
    _prepare_destination(destination, root).rmdir()
    with tempfile.TemporaryDirectory(prefix="codex-agent-runtime-collection-", dir=root) as temporary:
        prepared = Path(temporary).resolve() / "collection"
        prepared.mkdir()
        rows = []
        for instance, ready in selected:
            name = f"{instance.component}-{instance.phase}-{instance.target}"
            job_name = (sdk_worker_job_name.replace("{target}", instance.target) if sdk_family == "core-validation"
                        and sdk_worker_job_name is not None else sdk_worker_job_name or _worker_job_name(product, instance))
            artifact_name = (f"codex-agent-{product}-worker-{name}-{ready['buildKey'].removeprefix('sha256:')}-"
                             f"{producer['tree']}-attempt-{producer['runAttempt']}")
            row = {**_identity_record(instance), "buildKey": ready["buildKey"],
                   "jobName": job_name, "artifactName": artifact_name, "result": "failure", "reason": None,
                   "artifact": None, "originalDirectory": None, "shardDirectory": None}
            rows.append(row)
            try:
                matrix_key = ready["buildKey"] if product == "sdk" and sdk_worker_job_name is None else None
                matching_jobs = _matching_ci_jobs(jobs, job_name, expected_build_key=matrix_key)
                if len(matching_jobs) != 1:
                    raise ValueError("Runtime worker job is missing or ambiguous")
                job = matching_jobs[0]
                job_name = job["name"]
                row["jobName"] = job_name
                require_integer(job.get("id"), "Runtime worker job ID", 1)
                if (require_integer(job.get("run_id"), "Runtime worker job run", 1) != producer["runId"]
                        or job.get("head_sha") != observed[0]["run"]["head_sha"]):
                    raise ValueError("Runtime worker job differs from the original producer")
                candidates = [item for item in artifacts if isinstance(item, dict) and item.get("name") == artifact_name]
                if len(candidates) != 1:
                    raise ValueError("Runtime worker upload is missing or ambiguous")
                candidate = candidates[0]
                retained = prepared / "rows" / name
                retained.mkdir(parents=True)
                archive = retained / "transport.zip"
                artifact, _ = _download_contract_ci_upload(
                    candidate.get("id"), candidate.get("digest"), artifact_name, producer,
                    observed[0]["run"], token, destination=archive)
                timestamps = [datetime.fromisoformat(require_string(value, "Runtime worker timestamp").replace("Z", "+00:00"))
                              for value in (job.get("started_at"), artifact.get("created_at"), job.get("completed_at"))]
                if (any(value.utcoffset() != timedelta(0) for value in timestamps)
                        or not timestamps[0] <= timestamps[1] <= timestamps[2]):
                    raise ValueError("Runtime upload is outside its original job-attempt window")
                row["artifact"] = artifact
                verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                original = retained / "original"
                safe_extract(archive, original)
                row["originalDirectory"] = original.relative_to(prepared).as_posix()
                if job.get("conclusion") != "success":
                    raise ValueError("Runtime worker job did not succeed; original diagnostics retained")
                verified = verify_phase_shard(original / "shard", instance)
                receipt = verified["receipt"]
                if (receipt["producer"] != producer or receipt["buildKey"] != ready["buildKey"]
                        or receipt["productVersion"] != state.expected_fixed["versions"][
                            "sdk" if product == "sdk" else "runtime-release"]
                        or receipt["trustDomain"] != ("development" if state.plan["event"] == "pull_request" else "release")):
                    raise ValueError("Runtime worker shard differs from its elected plan and producer")
                if sdk_family == "native-validation":
                    carrier = original / "sdk-validation-evidence"
                    records = load_sdk_validation_evidence(carrier)
                    if (len(records) != 1 or records[0]["component"] != instance.component
                            or records[0]["target"] != instance.target
                            or records[0]["receiptSha256"] != sha256_bytes(canonical_json_bytes(receipt))):
                        raise ValueError("SDK validation carrier differs from its elected original shard")
                    authenticated = retained / "sdk-validation-evidence"
                    stage_sdk_validation_evidence(records, carrier, authenticated,
                        repository=root, policy_revision=state.plan["validationCommit"],
                        tooling=sdk_validation_tooling)
                    if verify_phase_shard(original / "shard", instance) != verified:
                        raise ValueError("SDK validation original shard changed during evidence admission")
                    row["sdkValidationEvidenceDirectory"] = authenticated.relative_to(prepared).as_posix()
                if sdk_family == "ios-validation":
                    from sdk_apple_attestation_capture import capture_apple_validation_attestation
                    from products.sdk_apple_validation_admission import stage_collected_apple_validation

                    if sdk_apple_validation_policy is None:
                        raise ValueError("Apple collection requires independent caller admission policy")
                    signer_job = f"product-validation / sdk-apple-validation-attestation-{instance.target}"
                    signer_jobs = [item for item in jobs if item.get("name") == signer_job]
                    if (len(signer_jobs) != 1 or signer_jobs[0].get("conclusion") != "success"
                            or signer_jobs[0].get("run_id") != producer["runId"]
                            or signer_jobs[0].get("head_sha") != observed[0]["run"]["head_sha"]):
                        raise ValueError("Apple signer job is missing, ambiguous or unsuccessful")
                    signer_name = (f"codex-agent-sdk-apple-validation-evidence-{instance.target}-"
                        f"{verified['receiptSha256'].removeprefix('sha256:')}-{producer['tree']}-"
                        f"attempt-{producer['runAttempt']}")
                    signer_artifacts = [item for item in artifacts if isinstance(item, dict)
                                        and item.get("name") == signer_name]
                    if len(signer_artifacts) != 1:
                        raise ValueError("Apple signer upload is missing or ambiguous")
                    signed = signer_artifacts[0]
                    signed_capture = retained / "apple-attestation-upload"
                    capture_apple_validation_attestation(plan_path, signed_capture,
                        target=instance.target, expected_receipt_sha256=verified["receiptSha256"],
                        artifact_id=signed.get("id"), artifact_sha256=signed.get("digest"),
                        trusted_workflow_sha=trusted_workflow_sha, repository_root=root,
                        environ=environment, token=token)
                    signed_inventory = regular_file_inventory(signed_capture, allow_empty=True)
                    authenticated = retained / "sdk-apple-validation-evidence"
                    # Admission cannot publish inside its source repository.
                    # Retain its verified bytes only after that external gate exits.
                    with tempfile.TemporaryDirectory(prefix="apple-collected-admission-") as staging:
                        staged = Path(staging).resolve() / "evidence"
                        stage_collected_apple_validation(original / "shard",
                            signed_capture / "original/sdk-apple-validation-evidence", staged,
                            target=instance.target, repository=root, policy_revision=state.plan["validationCommit"],
                            policy=sdk_apple_validation_policy)
                        staged_inventory = regular_file_inventory(staged, allow_empty=True)
                        snapshot_regular_tree(staged, authenticated, allow_empty=True)
                        if (regular_file_inventory(staged, allow_empty=True) != staged_inventory
                                or regular_file_inventory(authenticated, allow_empty=True) != staged_inventory):
                            raise ValueError("Apple admitted carrier changed during retention")
                    if (verify_phase_shard(original / "shard", instance) != verified
                            or regular_file_inventory(signed_capture, allow_empty=True) != signed_inventory):
                        raise ValueError("Apple original shard or signer evidence changed during collection")
                    row["sdkAppleValidationEvidenceDirectory"] = authenticated.relative_to(prepared).as_posix()
                if sdk_family == "ios-metadata":
                    from products.sdk_apple_validation_admission import AppleValidationAdmission

                    if sdk_apple_validation_policy is None:
                        raise ValueError("Apple metadata collection requires independent caller admission policy")
                    original_inventory = regular_file_inventory(original, allow_empty=True)
                    records = {"sdkAppleValidationEvidence": list(
                        state.rebased_request.get("sdkAppleValidationEvidence", []))}
                    _merge_native_comparison_records(records, _retained_apple_handoffs(state_root, root),
                                                     key="sdkAppleValidationEvidence")
                    predecessors = []
                    for target in ("ios-arm64", "ios-simulator-arm64"):
                        identity = PhaseInstanceId("sdk", "sdk-ios", "validation", target)
                        if identity not in state.sources or identity not in state.prior_carrier_phases:
                            raise ValueError("Apple metadata collection lacks both original validation predecessors")
                        record = state.prior_carrier_phases[identity]
                        predecessor = verify_object(state.sources[identity], build_key=record["buildKey"],
                            receipt_sha256=record["receiptSha256"], object_sha256=record["objectSha256"])
                        predecessors.append({"receipt": predecessor["receipt"],
                            "receiptBytes": predecessor["receiptBytes"],
                            "receiptSha256": record["receiptSha256"], "objectSha256": record["objectSha256"]})
                    AppleValidationAdmission(root, records["sdkAppleValidationEvidence"], repository=root,
                        policy_revision=state.plan["validationCommit"], policy=sdk_apple_validation_policy).verify_metadata(
                            {name: verified[name] for name in
                                ("receipt", "receiptBytes", "receiptSha256", "objectSha256")}, tuple(predecessors))
                    if (verify_phase_shard(original / "shard", instance) != verified
                            or regular_file_inventory(original, allow_empty=True) != original_inventory):
                        raise ValueError("Apple metadata original shard or diagnostics changed during collection")
                row.update(result="success", reason="verified-original-shard",
                           shardDirectory=(original / "shard").relative_to(prepared).as_posix())
            except (ValueError, OSError) as error:
                row["reason"] = str(error)
        result = {"schemaVersion": 1, "producer": producer, "observed": observed, "rows": rows}
        write_canonical_json(prepared / "collection.json", result)
        publish_regular_tree(prepared, destination, allow_empty=True)
    return result


@verification_scoped
def advance_products(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    shard_roots: list[Path], destination: Path,
    github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    native_evidence_roots: tuple[Path, ...] = (),
    adapter_evidence_roots: tuple[Path, ...] = (),
    sdk_evidence_roots: tuple[Path, ...] = (),
    sdk_apple_evidence_roots: tuple[Path, ...] = (),
    sdk_maven_evidence_roots: tuple[Path, ...] = (),
    sdk_metadata_evidence_roots: tuple[Path, ...] = (),
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    aggregate_evidence_roots: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    failed_instances: tuple[PhaseInstanceId, ...] = (),
    runtime_workers_only: bool = False,
    runtime_aggregate_only: bool = False,
    sdk_javascript_only: bool = False,
    sdk_ios_binary_only: bool = False,
    sdk_family: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
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
        os.environ if environ is None else environ, sdk_validation_tooling,
        sdk_original_workflow_sha=sdk_original_workflow_sha,
        sdk_apple_validation_policy=sdk_apple_validation_policy,
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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
    if (any(type(value) is not bool for value in (runtime_workers_only, runtime_aggregate_only, sdk_javascript_only, sdk_ios_binary_only))
            or sum((runtime_workers_only, runtime_aggregate_only, sdk_javascript_only, sdk_ios_binary_only,
                    sdk_family is not None)) > 1):
        raise ValueError("Runtime collection scopes must be boolean and mutually exclusive")
    if sdk_family is not None:
        _sdk_family_worker_instance(None, sdk_family)
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if _sdk_family_worker_instance(instance, sdk_family)}
    elif sdk_ios_binary_only:
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if _sdk_ios_binary_worker_instance(instance)}
    elif sdk_javascript_only:
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if _sdk_javascript_worker_instance(instance)}
    elif runtime_workers_only:
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if _runtime_worker_instance(instance)}
    elif runtime_aggregate_only:
        expected_builds = {instance: phase for instance, phase in expected_builds.items()
                           if instance == PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")}
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
        apple_destination = temporary_root / "result/sdk-apple-validation-evidence"
        prior_apple = state_root / "sdk-apple-validation-evidence"
        if prior_apple.exists() or prior_apple.is_symlink():
            snapshot_regular_tree(prior_apple, apple_destination, allow_empty=True)
        _capture_apple_handoffs(sdk_apple_evidence_roots, apple_destination, root)
        retained_apple = _retained_apple_handoffs(temporary_root / "result", root)
        _merge_native_comparison_records(advanced_request, retained_apple, key="sdkAppleValidationEvidence")
        maven_destination = temporary_root / "result/sdk-maven-evidence"
        prior_maven = state_root / "sdk-maven-evidence"
        if prior_maven.exists() or prior_maven.is_symlink():
            require_regular_directory(prior_maven, "Retained Maven evidence carriers")
            _capture_maven_handoffs(tuple(sorted(prior_maven.iterdir())), maven_destination)
        _capture_maven_handoffs(sdk_maven_evidence_roots, maven_destination)
        metadata_destination = temporary_root / "result/sdk-metadata-evidence"
        prior_metadata = state_root / "sdk-metadata-evidence"
        if prior_metadata.exists() or prior_metadata.is_symlink():
            require_regular_directory(prior_metadata, "Retained metadata evidence carriers")
            _capture_metadata_handoffs(tuple(sorted(prior_metadata.iterdir())), metadata_destination)
        _capture_metadata_handoffs(sdk_metadata_evidence_roots, metadata_destination)
        aggregate_destination = temporary_root / "result/runtime-aggregate-release-evidence"
        prior_aggregate = state_root / "runtime-aggregate-release-evidence"
        if prior_aggregate.exists():
            snapshot_regular_tree(prior_aggregate, aggregate_destination, allow_empty=True)
        aggregate_trust = _release_trust(root, plan["validationCommit"], temporary_root / "aggregate-trust") if aggregate_evidence_roots else None
        _capture_aggregate_handoffs(aggregate_evidence_roots, aggregate_destination, root, aggregate_trust)
        retained_aggregate = _retained_aggregate_handoffs(temporary_root / "result", root)
        _merge_native_comparison_records(advanced_request, retained_aggregate, key=_AGGREGATE_REQUEST_KEY)
        ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
        advanced = _plan_with_sdk_tooling(
            advanced_request, sdk_validation_tooling,
            apple_policy=sdk_apple_validation_policy,
            apple_package_origin=_apple_package_origin(plan_path, root, sdk_original_workflow_sha,
                os.environ if environ is None else environ),
            build_plan_consumer=lambda instance, value: _retain_product_plan(ready_plans, instance, value),
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        supplied = set(sources)
        advanced_by_instance = {_identity(phase): phase for phase in advanced["phases"]}
        if any(advanced_by_instance[instance]["state"] != "retained" for instance in supplied):
            raise ValueError("A supplied product object was not retained by the recomputed plan")
        advanced, selected, selected_phases = _validate_reuse_result(
            advanced, requested, require_complete=False,
            sdk_runtime_external=advanced_request.get("sdkRuntimeSource") == "released-default",
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
        _merge_native_comparison_records(staged_request, retained_apple, key="sdkAppleValidationEvidence")
        _merge_native_comparison_records(staged_request, retained_aggregate, key=_AGGREGATE_REQUEST_KEY)
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
        staged_replay = _plan_with_sdk_tooling(staged_request, sdk_validation_tooling,
            apple_policy=sdk_apple_validation_policy,
            apple_package_origin=_apple_package_origin(plan_path, root, sdk_original_workflow_sha,
                os.environ if environ is None else environ),
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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
        if {"nativeRuntimeComparisonEvidence", _ADAPTER_REQUEST_KEY, _AGGREGATE_REQUEST_KEY, "sdkValidationEvidence", "sdkAppleValidationEvidence"} & final_request.keys():
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
            for key in ("nativeRuntimeComparisonEvidence", _ADAPTER_REQUEST_KEY, _AGGREGATE_REQUEST_KEY, "sdkValidationEvidence", "sdkAppleValidationEvidence"):
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
        publish_regular_tree(staged_destination, destination, allow_empty=True)
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
    carrier = verify_carrier(carrier_root, materialized, consumer, object_root=state_root)
    result_by_instance = {_identity(value): value for value in result["phases"]}
    carrier_by_instance = {_identity(value): value for value in carrier["objects"]}
    if any(
        any(carrier_by_instance[instance][field] != result_by_instance[instance][field]
            for field in (*_IDENTITY_KEYS, "buildKey", "receiptSha256", "objectSha256"))
        for instance in materialized
    ):
        raise ValueError("Contract materialization carrier disagrees with its reuse result")
    record = next(value for value in carrier["objects"] if _identity(value) == requested)
    object_path = (state_root / record["originalObjectPath"] if "originalObjectPath" in record else
        carrier_root / object_relative_path(record["buildKey"], record["receiptSha256"]))
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
        original_receipt = restored["receipt"]
        manifest = {"schemaVersion": 1, **{field: original_receipt[field] for field in
            ("product", "component", "phase", "target", "productVersion", "outputs")}}
        manifest_bytes = canonical_json_bytes(manifest)
        receipt_bytes = restored["receiptBytes"]
        expected_files = sorted([
            *({"relativePath": f"stage/{record['relativePath']}", "bytes": record["bytes"],
               "sha256": record["sha256"]} for record in original_receipt["outputs"]),
            {"relativePath": "stage/output-manifest.json", "bytes": len(manifest_bytes),
             "sha256": sha256_bytes(manifest_bytes)},
            {"relativePath": "receipt/phase-receipt.json", "bytes": len(receipt_bytes),
             "sha256": sha256_bytes(receipt_bytes)},
        ], key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared) != expected_files:
            raise ValueError("Contract handoff differs from its authenticated original object")
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
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
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        prepared = private / "captured"
        safe_extract(archive, prepared / "original")
        if regular_file_inventory(prepared / "original", allow_empty=True) != zipped:
            raise ValueError("Runtime supervisor extraction differs from its exact upload")
        evidence = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                    "buildKey": expected_build_key}
        write_canonical_json(prepared / "capture-transport.json", evidence)
        evidence_bytes = canonical_json_bytes(evidence)
        expected_files = sorted([
            {"relativePath": "capture-transport.json", "bytes": len(evidence_bytes),
             "sha256": sha256_bytes(evidence_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if sha256_file(archive) != artifact_sha256 or regular_file_inventory(prepared, allow_empty=True) != expected_files:
            raise ValueError("Runtime supervisor upload changed before publication")
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return evidence


def _capture_runtime_reference_members(plan, plan_bytes, producer, base, destination, *,
                                       trusted_workflow_sha, token, wanted):
    """Resolve qualified bytes, not enclosing carriers, after fresh source auth.

    The top-level reference envelope has passed its complete upload SHA gate.
    Every inherited byte is hashed against that authenticated envelope, while
    every original source retains its own exact job/attempt/window/workflow gate.
    Product admission and original-phase authentication still run afterwards.
    """
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    from runtime_reference_transport import validate_references, validate_original_references, ORIGINAL_REFERENCE_NAME

    wave = base["stateWave"]
    job = "product-validation / product-resume" if wave == 0 else f"product-validation / runtime-collect-{wave}"
    name = (f"codex-agent-product-resume-{producer['tree']}" if wave == 0 else
            f"codex-agent-runtime-wave-{wave}-state-{producer['tree']}-attempt-{producer['runAttempt']}")
    observed = _observe_ci_producer_jobs({"resume": producer}, jobs_by_phase={"resume": job},
        trusted_workflow_sha=trusted_workflow_sha, token=token)
    artifact = _contract_ci_upload_metadata(base["artifactId"], base["artifactSha256"], name,
        producer, observed[0]["run"], token)
    _require_artifact_job_window(observed[0], job, artifact)
    plan_path = "product-resume-inputs/plan/impact-plan.json"
    wanted = dict(wanted)
    wanted[plan_path] = {"relativePath": plan_path, "bytes": len(plan_bytes), "sha256": sha256_bytes(plan_bytes)}
    destination.mkdir(parents=True)
    with open_reference_archive(artifact, token) as (archive, stream):
        names = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
        roots = {"product-resume-inputs", "product-resume-state"} | ({"runtime-state"} if wave else set())
        if any(path not in {"runtime-references.json", ORIGINAL_REFERENCE_NAME}
               and path.split("/")[0] not in roots for path in names):
            raise ValueError("Original Runtime reference archive has unexpected roots")
        inherited, child = {}, None
        if ORIGINAL_REFERENCE_NAME in names:
            if wave or "runtime-references.json" in names:
                raise ValueError("Original member references require an initial Runtime ancestor")
            entry = archive.getinfo(ORIGINAL_REFERENCE_NAME)
            if entry.file_size > 16 * 1024**2:
                raise ValueError("Original Runtime references exceed the control bound")
            control_digest = base.get("referenceControlSha256")
            if control_digest is None:
                # Legacy callers may pin only the whole archive. Authenticate
                # it before reading any ancestry locator, exactly as below.
                with tempfile.TemporaryDirectory(prefix="runtime-original-reference-control-") as temporary:
                    authenticated_archive = Path(temporary).resolve() / "transport.zip"
                    _reuse_contract_ci_upload(artifact, producer, observed[0]["run"], token,
                        destination=authenticated_archive, limit=16 * 1024**3,
                        artifact_sha256=base["artifactSha256"], size=artifact["size_in_bytes"])
                    verified_zip_contents(authenticated_archive, retained_paths=(),
                        allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                    with zipfile.ZipFile(authenticated_archive) as authenticated:
                        if ({entry.filename for entry in authenticated.infolist() if not entry.is_dir()} != names
                                or authenticated.getinfo(ORIGINAL_REFERENCE_NAME).file_size > 16 * 1024**2):
                            raise ValueError("Original member reference control archive changed")
                        raw_control = authenticated.read(ORIGINAL_REFERENCE_NAME)
            else:
                raw_control = archive.read(entry)
                if sha256_bytes(raw_control) != control_digest:
                    raise ValueError("Original member reference control differs from its authenticated digest")
            references = validate_original_references(load_canonical_json_bytes(raw_control))
            inventory = {row["relativePath"]: row for row in references["inventory"]}
            mappings = {row["relativePath"]: row for row in references["references"]}
            if names - {ORIGINAL_REFERENCE_NAME} != set(inventory) - set(mappings):
                raise ValueError("Original member reference delta differs from its declaration")
            remote = {}
            for path, row in wanted.items():
                if inventory.get(path) != row:
                    raise ValueError("Original member reference changes a qualified byte identity")
                mapping = mappings.get(path)
                if mapping is None:
                    copy_reference_member(archive, path, destination / path, row)
                elif mapping["source"] is None:
                    copy_reference_member(archive, mapping["sourcePath"], destination / path, row)
                else:
                    remote.setdefault(mapping["source"], []).append(mapping)
            resolved = []
            for source in references["sources"]:
                if source["relativePath"] in remote:
                    resolved.append(_capture_runtime_original_reference_members(plan, producer, source,
                        remote[source["relativePath"]], destination,
                        trusted_workflow_sha=trusted_workflow_sha, token=token))
            child = {"originalReferenceSources": resolved}
        elif "runtime-references.json" in names:
            entry = archive.getinfo("runtime-references.json")
            if entry.file_size > 16 * 1024 * 1024:
                raise ValueError("Original Runtime references exceed the control bound")
            # Member hashes qualify payload bytes, not an ancestor's ancestry
            # controls. Older envelopes pin only the whole archive: authenticate
            # that archive before following any nested source mapping.
            control_digest = base.get("referenceControlSha256")
            if control_digest is not None:
                raw_control = archive.read(entry)
                if sha256_bytes(raw_control) != control_digest:
                    raise ValueError("Original Runtime reference control differs from its authenticated digest")
                references = validate_references(load_canonical_json_bytes(raw_control), wave)
            else:
                with tempfile.TemporaryDirectory(prefix="runtime-reference-control-") as temporary:
                    authenticated_archive = Path(temporary).resolve() / "transport.zip"
                    _reuse_contract_ci_upload(artifact, producer, observed[0]["run"], token,
                        destination=authenticated_archive, limit=16 * 1024**3,
                        artifact_sha256=base["artifactSha256"], size=artifact["size_in_bytes"])
                    verified_zip_contents(authenticated_archive, retained_paths=(),
                        allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
                    with zipfile.ZipFile(authenticated_archive) as authenticated:
                        if ({entry.filename for entry in authenticated.infolist() if not entry.is_dir()} != names
                                or authenticated.getinfo("runtime-references.json").file_size > 16 * 1024 * 1024):
                            raise ValueError("Original Runtime reference control archive changed")
                        references = validate_references(load_canonical_json_bytes(
                            authenticated.read("runtime-references.json")), wave)
            inventory = {record["relativePath"]: record for record in references["inventory"]}
            mappings = {record["relativePath"]: record for record in references["references"]}
            if names - {"runtime-references.json"} != set(inventory) - set(mappings):
                raise ValueError("Original Runtime reference delta inventory differs from its declaration")
            for path, record in wanted.items():
                if inventory.get(path) != record:
                    raise ValueError("Nested Runtime reference changes a qualified byte identity")
                if path in mappings:
                    source = mappings[path]["sourcePath"]
                    inherited[source] = {**record, "relativePath": source}
            if inherited:
                with tempfile.TemporaryDirectory(prefix="runtime-reference-members-") as temporary:
                    child_root = Path(temporary).resolve() / "members"
                    child = _capture_runtime_reference_members(plan, plan_bytes, producer,
                        references["base"], child_root, trusted_workflow_sha=trusted_workflow_sha,
                        token=token, wanted=inherited)
                    from runtime_reference_transport import _copy_exact
                    for path, record in wanted.items():
                        if path in mappings:
                            _copy_exact(child_root / mappings[path]["sourcePath"], destination / path, record)
        elif base.get("referenceControlSha256") is not None:
            raise ValueError("Original Runtime reference source lacks its authenticated control")
        for path, record in wanted.items():
            if not (destination / path).exists():
                copy_reference_member(archive, path, destination / path, record)
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
            "verification": "qualified-reference-members", "rangeBytes": stream.transferred,
            "memberETag": stream.etag}
        if names & {"runtime-references.json", ORIGINAL_REFERENCE_NAME} and base.get("referenceControlSha256") is None:
            transport["authenticatedControlArchiveBytes"] = artifact["size_in_bytes"]
        if wave:
            transport["stateWave"] = wave
        if child is not None:
            transport["referenceBase"] = child
    if read_regular_file_bytes(destination / plan_path, reject_symlink_parents=True) != plan_bytes:
        raise ValueError("Original Runtime reference source changes the caller's validated plan")
    return transport


def _authenticate_runtime_original_reference_source(plan, producer, source, *,
                                                     trusted_workflow_sha, token):
    """Fresh GitHub identity gates, independent of body storage or qualification."""
    receipt = source["receipt"]
    original = receipt["producer"]
    if (original["repository"] != plan["repository"] or original["event"] != plan["event"]
            or original["pullRequest"] != producer["pullRequest"]
            or (original["runId"], original["runAttempt"]) >= (producer["runId"], producer["runAttempt"])):
        raise ValueError("Original member source is not an earlier producer for this consumer")
    run = api_json(f"https://api.github.com/repos/{plan['repository']}/actions/runs/"
                   f"{original['runId']}/attempts/{original['runAttempt']}", token)
    workflow = _runtime_prior_workflow_sha(run, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Original member source lacks a reviewed original workflow")
    if source["kind"] == "phase":
        job = f"product-validation / runtime-{receipt['component']}-{receipt['phase']}-{receipt['target']}"
        name = (f"codex-agent-runtime-worker-{receipt['component']}-{receipt['phase']}-{receipt['target']}-"
                f"{receipt['buildKey'][7:]}-{original['tree']}-attempt-{original['runAttempt']}")
    else:
        job = "product-validation / runtime-aggregate-attestation"
        name = f"codex-agent-runtime-aggregate-release-handoff-{original['tree']}-attempt-{original['runAttempt']}"
    observed = _observe_ci_producer_jobs({"source": original}, jobs_by_phase={"source": job},
        trusted_workflow_sha=workflow, token=token)
    artifact = _contract_ci_upload_metadata(source["artifactId"], source["artifactSha256"], name,
        original, observed[0]["run"], token)
    _require_artifact_job_window(observed[0], job, artifact)
    return artifact, original, observed, workflow


def _capture_runtime_original_reference_members(plan, producer, source, references, destination, *,
                                               trusted_workflow_sha, token):
    """Fresh original source gates plus member SHA qualified by the current upload.

    This is the same custody protocol as Runtime wave references. It is never
    phase admission: original-CI and signed-handoff verification still follow.
    """
    from runtime_reference_archive import open_reference_archive, copy_reference_member
    artifact, original, observed, workflow = _authenticate_runtime_original_reference_source(
        plan, producer, source, trusted_workflow_sha=trusted_workflow_sha, token=token)
    receipt = source["receipt"]
    if source["kind"] == "phase":
        from products.verified_evidence import runtime_original_cache
        persistent = runtime_original_cache()
        instance = _identity(receipt)
        job = f"product-validation / runtime-{receipt['component']}-{receipt['phase']}-{receipt['target']}"
        original_job = next(value for value in observed[0]["jobs"] if value.get("name") == job)
        locator = _runtime_original_locator(artifact, workflow, instance, original_job)
        completed = persistent.read(locator) if persistent is not None else None
        if completed is not None:
            if completed["receipt"] != receipt:
                raise ValueError("Cached original member receipt/provenance differs from authenticated reference")
            for row in references:
                persistent.copy_member(completed, row["sourcePath"], destination / row["relativePath"], row)
            return {"artifact": artifact, "captureProducer": original, "observed": observed,
                    "verification": "qualified-reference-members", "rangeBytes": 0, "memberETag": None}
    # Storage only: these expectations came from the authenticated enclosing
    # upload. Fresh original workflow/job/attempt/window gates above always run.
    import hydrated_evidence
    missing = []
    for row in references:
        if not hydrated_evidence.copy(row, destination / row["relativePath"]):
            missing.append(row)
    if not missing:
        return {"artifact": artifact, "captureProducer": original, "observed": observed,
                "verification": "qualified-reference-members", "rangeBytes": 0, "memberETag": None}
    with open_reference_archive(artifact, token) as (archive, stream):
        resolved = {}
        for row in missing:
            source_path = row["sourcePath"]
            target = destination / row["relativePath"]
            if source_path in resolved:
                from runtime_reference_transport import _copy_exact
                _copy_exact(resolved[source_path], target, row)
            else:
                copy_reference_member(archive, source_path, target, row)
                resolved[source_path] = target
            hydrated_evidence.retain(row, target)
        return {"artifact": artifact, "captureProducer": original, "observed": observed,
                "verification": "qualified-reference-members", "rangeBytes": stream.transferred,
                "memberETag": stream.etag}


def _qualified_original_projection(locator):
    from products.restore import _VERIFICATION_SESSION, _stage_fingerprint
    from products.verified_evidence import _source_identity
    session = _VERIFICATION_SESSION.get()
    key = canonical_json_bytes(locator)
    qualified = session.get("qualifiedOriginalProjections", {}).get(key) if session else None
    if qualified is not None and not qualified[0].exists() and not qualified[0].is_symlink():
        # A completed inner operation may have released its temporary custody.
        del session["qualifiedOriginalProjections"][key]
        qualified = None
    if qualified is None and session is not None and session.get("portableQualificationInputs"):
        import reuse_qualification
        try:
            qualified = reuse_qualification.projection(locator, **session["portableQualificationInputs"])
        except reuse_qualification.QualificationIncompatible:
            # Verified but incompatible claims cannot create a witness. The
            # unchanged original authentication path still owns this evidence.
            return None
    if qualified is not None:
        source, fingerprint, _files, policy = qualified
        if policy != _source_identity():
            return None
        if _stage_fingerprint(source.parent) != fingerprint:
            raise ValueError(f"Authenticated original projection custody changed: {source}")
    return qualified


def _register_qualified_original_projections(original, references, transports, *, trusted_workflow_sha):
    """Private custody from a freshly SHA-authenticated reviewed carrier.

    Reference resolution and fresh source CI gates have finished. Replays still
    authenticate original CI and verify the receipt/object/dependencies. This
    process-local witness is never serialized or accepted from cache storage.
    """
    import hydrated_evidence
    from products.restore import _VERIFICATION_SESSION, _stage_fingerprint
    from products.verified_evidence import _source_identity
    session = _VERIFICATION_SESSION.get()
    if hydrated_evidence.root() is None or session is None:
        return
    policy = _source_identity()
    for source, transport in zip(references["sources"], transports, strict=True):
        if source["kind"] != "phase":
            continue
        instance = _identity(source["receipt"])
        projected = Path(original) / source["relativePath"]
        captured = projected.parents[2]
        observation = _canonical_control(captured / "transport/original-ci-phases.json",
                                         "Qualified original phase observation")
        if "recoveryProjection" not in observation:
            continue  # Legacy evidence retains its full cold authentication.
        fresh = {**observation, "observed": transport["observed"],
                 "artifacts": {instance.phase: transport["artifact"]}}
        if _runtime_capture_identity(observation, instance) != _runtime_capture_identity(fresh, instance):
            raise ValueError("Qualified projection changes original authenticated provenance")
        zipped = observation["recoveryProjection"]["originalFiles"][instance.phase]
        expected = [row for row in zipped if not row["relativePath"].startswith("inputs/")]
        if regular_file_inventory(projected, allow_empty=True) != expected:
            raise ValueError("Qualified original projection changes its authenticated inventory")
        verified = verify_phase_shard(projected / "shard", instance)
        if verified["receipt"] != source["receipt"]:
            raise ValueError("Qualified original projection changes its original receipt")
        job_name = f"product-validation / runtime-{instance.component}-{instance.phase}-{instance.target}"
        job = next(value for value in transport["observed"][0]["jobs"] if value.get("name") == job_name)
        run = transport["observed"][0]["run"]
        workflow = _runtime_prior_workflow_sha(run, trusted_workflow_sha)
        locator = _runtime_original_locator(transport["artifact"], workflow, instance, job)
        key = canonical_json_bytes(locator)
        record = projected, _stage_fingerprint(projected.parent), zipped, policy
        existing = session.setdefault("qualifiedOriginalProjections", {}).get(key)
        if existing is not None and existing[2:] != record[2:]:
            raise ValueError("Same original identity has conflicting qualified projections")
        session["qualifiedOriginalProjections"][key] = record


def _publish_runtime_original_reference_handoff(inputs, state, destination):
    from runtime_reference_transport import stage_original_reference_handoff
    sources = []
    prior = Path(state) / "prior-failed-runtime"
    if prior.exists():
        for observation_path in sorted(prior.glob("*/*/*/transport/original-ci-phases.json")):
            captured = observation_path.parent.parent
            component, phase, target = captured.relative_to(prior).parts
            receipt = verify_phase_shard(captured / f"phases/{phase}/original/shard",
                PhaseInstanceId("runtime", component, phase, target))["receipt"]
            observation = _canonical_control(observation_path, "Original Runtime reference observation")
            if "recoveryProjection" not in observation:
                continue
            artifact = observation["artifacts"][phase]
            sources.append({"relativePath": "product-resume-state/" + captured.relative_to(state).as_posix()
                            + f"/phases/{phase}/original", "kind": "phase", "receipt": receipt,
                            "artifactId": artifact["id"], "artifactSha256": artifact["digest"]})
    aggregate_observation = Path(state) / "recovered-runtime-aggregate-upload.json"
    if aggregate_observation.exists():
        observation = _canonical_control(aggregate_observation, "Original aggregate reference observation")
        phase = next(row for row in _canonical_control(Path(state) / "reuse-wave-result.json",
            "Original Runtime reference result")["phases"] if _identity(row) ==
            PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate"))
        handoff = Path(state) / "runtime-aggregate-release-evidence/0/handoffs" / phase["receiptSha256"][7:]
        receipt = validate_phase_receipt(_canonical_control(handoff / "aggregate-input/metadata-receipt.json",
                                                            "Original aggregate reference receipt"))
        if sha256_bytes(canonical_json_bytes(receipt)) != phase["receiptSha256"]:
            raise ValueError("Original aggregate reference changes its selected receipt")
        if receipt["producer"] != observation["captureProducer"]:
            raise ValueError("Original aggregate reference changes its captured producer")
        artifact = observation["artifact"]
        sources.append({"relativePath": "product-resume-state/" + handoff.relative_to(state).as_posix(),
                        "kind": "aggregate", "receipt": receipt,
                        "artifactId": artifact["id"], "artifactSha256": artifact["digest"]})
    return stage_original_reference_handoff({"product-resume-inputs": inputs,
        "product-resume-state": state}, sources, destination)


@verification_scoped
def capture_runtime_resume_upload(
    plan_path: Path, destination: Path, *, artifact_id: int, artifact_sha256: str,
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str, state_wave: int = 0,
    sdk_state_wave: int | None = None, original_run_id: int | None = None,
    original_run_attempt: int | None = None,
) -> dict[str, Any]:
    """Retain the exact resumed upload; full product replay grants admission."""
    require_integer(artifact_id, "Runtime resume artifact ID", 1)
    if type(state_wave) is not int or not 0 <= state_wave <= 5:
        raise ValueError("Runtime state wave must be an integer from zero through five")
    if sdk_state_wave is not None and (type(sdk_state_wave) is not int
            or sdk_state_wave not in range(1, 20) or state_wave != 0):
        raise ValueError("SDK state wave must be one through nineteen, without a Runtime state wave")
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
        producer = _consumer(plan, os.environ if environ is None else environ,
                             original_run_id=original_run_id,
                             original_run_attempt=original_run_attempt)["producer"]
        job_name = "product-validation / product-resume" if state_wave == 0 else f"product-validation / runtime-collect-{state_wave}"
        artifact_name = (f"codex-agent-product-resume-{producer['tree']}" if state_wave == 0 else
                         f"codex-agent-runtime-wave-{state_wave}-state-{producer['tree']}-attempt-{producer['runAttempt']}")
        if sdk_state_wave is not None:
            job_name = f"product-validation / sdk-collect-{sdk_state_wave}"
            artifact_name = (f"codex-agent-sdk-wave-{sdk_state_wave}-state-{producer['tree']}-"
                             f"attempt-{producer['runAttempt']}")
        workflow_policy = {"trusted_workflow_sha": trusted_workflow_sha}
        if sdk_state_wave is not None and 11 <= sdk_state_wave <= 18:
            from ci.sdk_nested_wave_locator import _COLLECTORS
            workflow_name, parent_job = _COLLECTORS[sdk_state_wave]
            job_name = f"product-validation / {parent_job} / sdk-collect-{sdk_state_wave}"
            workflow_policy = {"trusted_workflows_by_phase": {"resume": {
                "path": f".github/workflows/{workflow_name}.yml",
                "sha": trusted_workflow_sha,
            }}}
        observed = _observe_ci_producer_jobs(
            {"resume": producer}, jobs_by_phase={"resume": job_name},
            token=token, **workflow_policy)
        archive = private / "transport.zip"
        artifact, _ = _download_contract_ci_upload(
            artifact_id, artifact_sha256, artifact_name,
            producer, observed[0]["run"], token, destination=archive)
        if sdk_state_wave is not None:
            _require_artifact_job_window(observed[0], job_name, artifact)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
                                             **_CATALOG_ZIP_LIMITS)
        prepared = private / "captured"
        original = prepared / "original"
        safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Runtime resume extraction differs from its exact original archive")
        reference_path = original / "runtime-references.json"
        reference_transport = None
        reference_control_digest = None
        original_reference_path = original / "runtime-original-references.json"
        original_reference_transports = []
        original_references = None
        if original_reference_path.exists() or original_reference_path.is_symlink():
            if state_wave or sdk_state_wave is not None or reference_path.exists():
                raise ValueError("Original references require an initial Runtime resume upload")
            from runtime_reference_transport import resolve_original_reference_handoff
            reference_control_digest = sha256_file(original_reference_path)
            _require_artifact_job_window(observed[0], job_name, artifact)
            def capture_source(source, records, target):
                original_reference_transports.append(_capture_runtime_original_reference_members(
                    plan, producer, source, records, target,
                    trusted_workflow_sha=trusted_workflow_sha, token=token))
            original_references = _canonical_control(original_reference_path, "Runtime original references")
            from hydrated_evidence import hosted
            hosted("restore", original_references, private)
            zipped = resolve_original_reference_handoff(original, original_references, capture_source)
        if reference_path.exists() or reference_path.is_symlink():
            if sdk_state_wave is not None:
                raise ValueError("Runtime reference transport cannot replace an SDK state upload")
            from runtime_reference_transport import validate_references, resolve_reference_handoff
            references = validate_references(_canonical_control(reference_path, "Runtime references"), state_wave)
            reference_control_digest = sha256_file(reference_path)
            base = references["base"]
            if base["artifactId"] == artifact_id:
                raise ValueError("Runtime reference upload cannot refer to itself")
            _require_artifact_job_window(observed[0], job_name, artifact)
            wanted = {record["sourcePath"]: {"relativePath": record["sourcePath"],
                "bytes": record["bytes"], "sha256": record["sha256"]} for record in references["references"]}
            reference_transport = _capture_runtime_reference_members(plan, plan_bytes, producer,
                base, private / "reference-base", trusted_workflow_sha=trusted_workflow_sha,
                token=token, wanted=wanted)
            zipped = resolve_reference_handoff(original, private / "reference-base", references,
                                                state_wave=state_wave)
        expected_roots = {"product-resume-inputs", "product-resume-state"} | (
            {"runtime-state"} if state_wave or sdk_state_wave is not None else set())
        if ({member.name for member in original.iterdir()} != expected_roots
                or any(not member.is_dir() for member in original.iterdir())):
            raise ValueError("Runtime resume upload requires its exact original directories")
        if read_regular_file_bytes(original / "product-resume-inputs/plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Runtime resume upload plan differs from the validated original plan")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed}
        if original_reference_transports:
            transport["originalReferenceSources"] = original_reference_transports
        if reference_control_digest is not None:
            transport["referenceControlSha256"] = reference_control_digest
        if reference_transport is not None:
            transport["referenceBase"] = reference_transport
            transport["referenceControlSha256"] = reference_control_digest
        if state_wave:
            transport["stateWave"] = state_wave
        if sdk_state_wave is not None:
            transport["sdkStateWave"] = sdk_state_wave
            if read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != plan_bytes:
                raise ValueError("Original SDK state capture plan changed during verification")
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if regular_file_inventory(prepared, allow_empty=True) != expected_files:
            raise ValueError("Runtime resume capture changed before publication")
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
        if original_references is not None:
            _register_qualified_original_projections(destination / "original", original_references,
                original_reference_transports, trusted_workflow_sha=trusted_workflow_sha)
            hosted("save", original_references, private)
    return transport


def capture_runtime_aggregate_release_upload(plan_path, destination, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, expected_build_key, expected_metadata_receipt_sha256,
        repository_root=None, environ=None, original_run_id=None, original_run_attempt=None,
        original_producer=None, token):
    """Capture a fixed protected job's exact upload, not its product admission.

    Original signature/content authentication remains in the existing full
    carrier/SDK gate. Nothing in current transport rewrites original provenance.
    """
    from products.sdk_package import _require_capability_output_separate
    from products.sdk_protected_runtime import _original_carrier

    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    key = require_sha256(expected_build_key, "Selected aggregate key")
    digest = require_sha256(expected_metadata_receipt_sha256, "Selected aggregate receipt")
    require_integer(artifact_id, "Aggregate upload ID", 1)
    require_sha256(artifact_sha256, "Aggregate upload digest")
    if not isinstance(token, str) or not token:
        raise ValueError("Aggregate upload capture requires an observation token")

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path])
        if destination.exists() or destination.is_symlink():
            raise ValueError("Aggregate upload destination must not exist")

    output_safe()
    original_plan = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="aggregate-release-upload-") as temporary:
        private = Path(temporary).resolve()
        prepared = private / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(original_plan)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("Aggregate upload capture requires an authorized PR or merge-group plan")
        current = validate_producer(_consumer(
            plan, os.environ if environ is None else environ,
            original_run_id=original_run_id, original_run_attempt=original_run_attempt,
        )["producer"])
        producer = current if original_producer is None else validate_producer(original_producer)
        if original_producer is not None and (
                original_run_id is not None or original_run_attempt is not None
                or producer["repository"] != current["repository"] or producer["event"] != current["event"]
                or producer["pullRequest"] != current["pullRequest"]
                or (producer["runId"], producer["runAttempt"]) >= (current["runId"], current["runAttempt"])):
            raise ValueError("Retained aggregate requires the exact earlier original producer of this plan's PR")
        job = "product-validation / runtime-aggregate-attestation"
        observed = _observe_ci_producer_jobs({"aggregate": producer}, jobs_by_phase={"aggregate": job},
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = f"codex-agent-runtime-aggregate-release-handoff-{producer['tree']}-attempt-{producer['runAttempt']}"
        archive = prepared / "transport.zip"
        artifact, _ = _download_contract_ci_upload(artifact_id, artifact_sha256, name, producer,
            observed[0]["run"], token, destination=archive)
        _require_artifact_job_window(observed[0], job, artifact)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Aggregate upload extraction differs from its exact original archive")
        caller = _canonical_control(original / "caller.json", "Original protected aggregate caller")
        if (caller.get("transportProducer") != producer or caller.get("target") != "aggregate"
                or caller.get("trustedWorkflowSha") != trusted_workflow_sha
                or caller.get("metadataReceiptSha256") != digest):
            raise ValueError("Aggregate protected caller differs from its observed upload or selected receipt")
        _original_carrier(original, digest, key)  # Fixed layout and receipt/key only; never signature authority.
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     "aggregateBuildKey": key, "aggregateReceiptSha256": digest}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(original_plan),
             "sha256": sha256_bytes(original_plan)},
            {"relativePath": "transport.zip", "bytes": archive.stat().st_size, "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != original_plan
                or captured_plan.read_bytes() != original_plan
                or regular_file_inventory(original, allow_empty=True) != zipped
                or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("Aggregate original plan or upload changed before capture publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport


def _verify_retained_sdk_upload_archive(capture, artifact, *, extra_roots=(), apple=False):
    """Check preserved upload bytes; stored transport metadata is not authority."""
    capture = Path(capture)
    regular_file_inventory(capture, allow_empty=True)
    if {path.name for path in capture.iterdir()} != {
            "plan", "original", "transport.zip", "capture-transport.json", *extra_roots}:
        raise ValueError("Retained SDK upload has unexpected roots")
    if {row["relativePath"] for row in regular_file_inventory(capture / "plan")} != {"impact-plan.json"}:
        raise ValueError("Retained SDK upload plan has unexpected files")
    artifact = require_object(artifact, "Retained SDK upload artifact")
    require_integer(artifact.get("id"), "Retained SDK upload artifact ID", 1)
    digest = require_sha256(artifact.get("digest"), "Retained SDK upload digest")
    archive = capture / "transport.zip"
    if sha256_file(archive) != digest:
        raise ValueError("Retained SDK upload archive differs from its original digest")
    zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
        **(_APPLE_UPLOAD_ZIP_LIMITS if apple else _CATALOG_ZIP_LIMITS))
    if regular_file_inventory(capture / "original", allow_empty=True) != zipped:
        raise ValueError("Retained SDK upload content differs from its original archive")


def verify_retained_sdk_ios_upload(capture, receipt_bytes):
    """Replay exact Apple upload consistency inside caller-authenticated evidence.

    This does not observe CI or authenticate a catalog. Full source/tooling and
    semantic replay remains required before admitting the selected receipt.
    """
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    phase, target = receipt["phase"], receipt["target"]
    if ((receipt["product"], receipt["component"]) != ("sdk", "sdk-ios")
            or phase not in {"binary", "package", "validation"}
            or target not in (("ios-arm64", "ios-simulator-arm64") if phase == "validation" else ("ios",))):
        raise ValueError("Retained Apple upload requires an exact original phase receipt")
    capture = Path(capture)
    transport = require_exact_keys(_canonical_control(capture / "capture-transport.json", "Retained Apple transport"),
        {"artifact", "captureProducer", "observed", f"{phase}ReceiptSha256"}, "Retained Apple transport")
    producer = receipt["producer"]
    if (transport["captureProducer"] != producer
            or transport[f"{phase}ReceiptSha256"] != sha256_bytes(receipt_bytes)):
        raise ValueError("Retained Apple transport differs from the exact original receipt")
    _verify_retained_sdk_upload_archive(capture, transport["artifact"], apple=True)
    name = (f"codex-agent-sdk-worker-sdk-ios-{phase}-{target}-{receipt['buildKey'].removeprefix('sha256:')}-"
            f"{producer['tree']}-attempt-{producer['runAttempt']}")
    if transport["artifact"].get("name") != name:
        raise ValueError("Retained Apple artifact differs from its original phase identity")
    shard = verify_phase_shard(capture / "original/shard", _identity(receipt))
    if shard["receiptBytes"] != receipt_bytes:
        raise ValueError("Retained Apple shard differs from its selected receipt")


def capture_sdk_inputs_upload(plan_path, destination, *, artifact_id, artifact_sha256,
        trusted_workflow_sha, expected_source, repository_root=None, environ=None, token,
        original_package_receipt_path=None):
    """Capture exact SDK transport; caller-policy content verification remains separate.

    Historical recovery requires the original iOS package receipt AND its exact
    validated original plan. Current-run environment never replaces that producer.
    """
    from products.inventory import require_regular_directory
    from products.sdk_package import _require_capability_output_separate
    require_integer(artifact_id, "SDK input upload ID", 1)
    require_sha256(artifact_sha256, "SDK input upload digest")
    if not isinstance(expected_source, str) or expected_source not in {"released-default", "current-runtime"}:
        raise ValueError("SDK input capture requires an exact selected source")
    if not isinstance(token, str) or not token:
        raise ValueError("SDK input capture requires an observation token")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    receipt_path = (Path(original_package_receipt_path).absolute()
                    if original_package_receipt_path is not None else None)

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path, *([receipt_path] if receipt_path else [])])
        if destination.exists() or destination.is_symlink():
            raise ValueError("SDK input capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_bytes = None
    original_producer = None
    if receipt_path is not None:
        receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
        receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
        if _identity(receipt) != PhaseInstanceId("sdk", "sdk-ios", "package", "ios"):
            raise ValueError("Historical SDK input capture requires the original iOS package receipt")
        original_producer = receipt["producer"]
    with tempfile.TemporaryDirectory(prefix="sdk-input-upload-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root, **(
            {"expected_revision": original_producer["commit"]} if original_producer is not None else {}))
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("SDK input capture requires an authorized PR or merge-group plan")
        producer_environment = (os.environ if environ is None else environ) if original_producer is None else {
            "GITHUB_RUN_ID": str(original_producer["runId"]),
            "GITHUB_RUN_ATTEMPT": str(original_producer["runAttempt"]),
        }
        producer = validate_producer(_consumer(plan, producer_environment)["producer"])
        if original_producer is not None and producer != original_producer:
            raise ValueError("Historical SDK input plan differs from the original package producer")
        job = "product-validation / sdk-inputs"
        observed = _observe_ci_producer_jobs({"sdk-inputs": producer}, jobs_by_phase={"sdk-inputs": job},
            trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = f"codex-agent-sdk-inputs-{producer['tree']}-attempt-{producer['runAttempt']}"
        archive = prepared / "transport.zip"
        artifact, _ = _download_contract_ci_upload(artifact_id, artifact_sha256, name, producer,
            observed[0]["run"], token, destination=archive)
        _require_artifact_job_window(observed[0], job, artifact)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        safe_extract(archive, original)
        expected = ({"runtime-original", "current-contract", "sdk-inputs", "selection.json", "transport.json"}
                    if expected_source == "released-default" else {"runtime-capture", "sdk-inputs"})
        if {path.name for path in original.iterdir()} != expected:
            raise ValueError("SDK input upload differs from the selected source layout")
        for name in expected - {"selection.json", "transport.json"}:
            require_regular_directory(original / name, "SDK input original directory")
        if expected_source == "released-default":
            selection = _canonical_control(original / "selection.json", "SDK input selection")
            transport = _canonical_control(original / "transport.json", "SDK input original transport")
            if (selection.get("source") != expected_source or not isinstance(transport.get("consumer"), dict)
                    or transport["consumer"].get("producer") != producer):
                raise ValueError("SDK input original selection or consumer differs from observed upload")
        elif read_regular_file_bytes(original / "runtime-capture/plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("SDK input original plan differs from the selected plan")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     "sdkRuntimeSource": expected_source}
        if receipt_bytes is not None:
            transport["packageReceiptSha256"] = sha256_bytes(receipt_bytes)
            (prepared / "original-package-receipt.json").write_bytes(receipt_bytes)
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = [
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes),
             "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "transport.zip", "bytes": archive.stat().st_size, "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ]
        if receipt_bytes is not None:
            expected_files.append({"relativePath": "original-package-receipt.json",
                                   "bytes": len(receipt_bytes), "sha256": sha256_bytes(receipt_bytes)})
        expected_files.sort(key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or (receipt_path is not None and (
                    read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != receipt_bytes
                    or read_regular_file_bytes(prepared / "original-package-receipt.json") != receipt_bytes))
                or captured_plan.read_bytes() != plan_bytes or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != zipped
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("SDK input original plan or upload changed before capture publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport


def capture_sdk_ios_package_upload(plan_path, destination, *, package_receipt_path,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Retain the observed original package upload, not package semantic admission.

    Source/S858 authentication and full original execution replay are still required.
    In particular, neither an uploaded descriptor nor this transport grants those gates.
    """
    return _capture_sdk_ios_upload(plan_path, destination, phase="package", receipt_path=package_receipt_path,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token)


def capture_sdk_ios_binary_upload(plan_path, destination, *, binary_receipt_path,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Retain the observed original binary upload; native semantic admission is separate."""
    return _capture_sdk_ios_upload(plan_path, destination, phase="binary", receipt_path=binary_receipt_path,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token)


def capture_sdk_ios_validation_upload(plan_path, destination, *, validation_receipt_path,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Retain an observed original validation upload; full semantic replay is separate."""
    return _capture_sdk_ios_upload(plan_path, destination, phase="validation", receipt_path=validation_receipt_path,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token)


def capture_elected_sdk_ios_validation_upload(plan_path, destination, *, target, expected_build_key,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Bootstrap a current worker receipt; this is transport, not semantic admission.

    Subsequent preparation/signing independently recaptures the selected original
    receipt and applies all existing gates. No historical receipt is inferred.
    """
    return _capture_sdk_ios_upload(plan_path, destination, phase="validation", receipt_path=None,
        artifact_id=artifact_id, artifact_sha256=artifact_sha256, trusted_workflow_sha=trusted_workflow_sha,
        repository_root=repository_root, environ=environ, token=token,
        elected_target=target, elected_build_key=expected_build_key)


def _capture_sdk_ios_upload(plan_path, destination, *, phase, receipt_path,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root, environ, token,
        elected_target=None, elected_build_key=None):
    from products.sdk_package import _require_capability_output_separate
    from products.signing_isolation import require_no_signing_secret
    bootstrap = receipt_path is None
    environment = os.environ if environ is None else environ
    if bootstrap:
        require_no_signing_secret(environment)
        if phase != "validation" or elected_target not in ("ios-arm64", "ios-simulator-arm64"):
            raise ValueError("Apple receipt bootstrap requires an exact validation target")
        require_sha256(elected_build_key, "Elected Apple validation build key")
    elif elected_target is not None or elected_build_key is not None:
        raise ValueError("Original Apple receipt cannot be replaced by a current election")
    if phase not in ("binary", "package", "validation"):
        raise ValueError("Apple upload capture requires an exact binary, package or validation phase")
    require_integer(artifact_id, f"Apple {phase} upload ID", 1)
    require_sha256(artifact_sha256, f"Apple {phase} upload digest")
    if not isinstance(token, str) or not token:
        raise ValueError(f"Apple {phase} capture requires an observation token")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    receipt_path = Path(receipt_path).absolute() if receipt_path is not None else None

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path, receipt_path])
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"Apple {phase} capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_bytes = (read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
                     if receipt_path is not None else None)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes)) if receipt_bytes is not None else None
    target = elected_target if bootstrap else receipt["target"]
    targets = ("ios-arm64", "ios-simulator-arm64") if phase == "validation" else ("ios",)
    instance = PhaseInstanceId("sdk", "sdk-ios", phase, target)
    if target not in targets or (not bootstrap and _identity(receipt) != instance):
        raise ValueError(f"Apple {phase} capture requires the selected original {phase} receipt")
    producer = receipt["producer"] if receipt is not None else None
    with tempfile.TemporaryDirectory(prefix=f"sdk-ios-{phase}-upload-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError(f"Apple {phase} capture requires an authorized PR or merge-group plan")
        if bootstrap:
            if plan["event"] not in {"pull_request", "merge_group"}:
                raise ValueError("Apple receipt bootstrap requires an authorized PR or merge-group plan")
            producer = validate_producer(_consumer(plan, environment)["producer"])
            bootstrap_plan = canonical_json_bytes(plan)
        build_key = elected_build_key if bootstrap else receipt["buildKey"]
        job = f"product-validation / sdk-sdk-ios-{phase}-{target}"
        original_jobs = paginated_items(
            f"https://api.github.com/repos/codex-agent-labs/codex-agent/actions/runs/{producer['runId']}/attempts/{producer['runAttempt']}/jobs",
            "jobs", token)
        matching = _matching_ci_jobs(original_jobs, job, expected_build_key=build_key)
        if len(matching) != 1:
            raise ValueError("Apple original worker job is missing or ambiguous")
        job = matching[0]["name"]
        observed = _observe_ci_producer_jobs({f"ios-{phase}": producer},
            jobs_by_phase={f"ios-{phase}": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = (f"codex-agent-sdk-worker-sdk-ios-{phase}-{target}-{build_key.removeprefix('sha256:')}-"
                f"{producer['tree']}-attempt-{producer['runAttempt']}")
        archive = prepared / "transport.zip"
        artifact, _ = _download_contract_ci_upload(artifact_id, artifact_sha256, name, producer,
            observed[0]["run"], token, destination=archive)
        _require_artifact_job_window(observed[0], job, artifact)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True,
            **_APPLE_UPLOAD_ZIP_LIMITS)
        original = prepared / "original"
        safe_extract(archive, original)
        verified = verify_phase_shard(original / "shard", instance)
        if bootstrap:
            if verified["receipt"]["producer"] != producer or verified["receipt"]["buildKey"] != build_key:
                raise ValueError("Apple validation bootstrap differs from its current producer or elected key")
            receipt_bytes = verified["receiptBytes"]
        if verified["receiptBytes"] != receipt_bytes:
            raise ValueError(f"Apple uploaded {phase} differs from its selected original receipt")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     f"{phase}ReceiptSha256": sha256_bytes(receipt_bytes)}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes),
             "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "transport.zip", "bytes": archive.stat().st_size, "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or (receipt_path is not None and read_regular_file_bytes(receipt_path,
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != receipt_bytes)
                or captured_plan.read_bytes() != plan_bytes or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != zipped
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError(f"Apple {phase} original inputs or upload changed before publication")
        output_safe()
        if bootstrap:
            require_no_signing_secret(environment)
            if (canonical_json_bytes(plan) != bootstrap_plan
                    or validate_producer(_consumer(plan, environment)["producer"]) != producer):
                raise ValueError("Apple bootstrap plan or current producer changed during capture")
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport


def capture_sdk_javascript_validation_upload(plan_path, destination, *, validation_receipt_path,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Retain observed original validation and its explicit cwd, not content trust."""
    from products.sdk_package import _require_capability_output_separate
    require_integer(artifact_id, "JavaScript validation upload ID", 1)
    require_sha256(artifact_sha256, "JavaScript validation upload digest")
    if not isinstance(token, str) or not token:
        raise ValueError("JavaScript validation capture requires an observation token")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()
    receipt_path = Path(validation_receipt_path).absolute()

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path, receipt_path])
        if destination.exists() or destination.is_symlink():
            raise ValueError("JavaScript validation capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_bytes = read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = validate_phase_receipt(load_canonical_json_bytes(receipt_bytes))
    instance = PhaseInstanceId("sdk", "javascript", "validation", "node")
    if _identity(receipt) != instance:
        raise ValueError("JavaScript validation capture requires the selected original validation receipt")
    producer = receipt["producer"]
    with tempfile.TemporaryDirectory(prefix="sdk-javascript-upload-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("JavaScript validation capture requires an authorized PR or merge-group plan")
        job = "product-validation / sdk-javascript-validation-node"
        observed = _observe_ci_producer_jobs({"javascript-validation": producer},
            jobs_by_phase={"javascript-validation": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = (f"codex-agent-sdk-worker-javascript-validation-node-{receipt['buildKey'].removeprefix('sha256:')}-"
                f"{producer['tree']}-attempt-{producer['runAttempt']}")
        artifact, raw = _download_contract_ci_upload(artifact_id, artifact_sha256, name, producer, observed[0]["run"], token)
        _require_artifact_job_window(observed[0], job, artifact)
        archive = prepared / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        safe_extract(archive, original)
        verified = verify_phase_shard(original / "shard", instance)
        if verified["receiptBytes"] != receipt_bytes:
            raise ValueError("JavaScript uploaded validation differs from its selected original receipt")
        execution = require_exact_keys(_canonical_control(original / "worker/execution.json", "JavaScript validation execution"),
            {"schemaVersion", "producer", "buildKey", "command", "returnCode", "launchError", "elapsedNs", "workingDirectory"},
            "JavaScript validation execution")
        command = require_array(execution["command"], "JavaScript validation command")
        if (require_integer(execution["schemaVersion"], "JavaScript execution schema", 1) != 1
                or execution["producer"] != producer or execution["buildKey"] != receipt["buildKey"]
                or type(execution["returnCode"]) is not int or execution["returnCode"] != 0
                or execution["launchError"] is not None
                or any(type(argument) is not str for argument in command) or command.count("ciProductPhase") != 1):
            raise ValueError("JavaScript validation execution differs from its observed successful producer")
        require_integer(execution["elapsedNs"], "JavaScript validation elapsed time", 0)
        cwd = require_string(execution["workingDirectory"], "Original JavaScript working directory")
        path = PurePosixPath(cwd)
        if (not path.is_absolute() or path.as_posix() != cwd or cwd.startswith("//")
                or ".." in path.parts or "\\" in cwd or any(ord(character) < 32 or ord(character) == 127 for character in cwd)):
            raise ValueError("Original JavaScript working directory must be normalized absolute POSIX")
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
            "validationReceiptSha256": sha256_bytes(receipt_bytes),
            "originalConsumerDirectory": str(path / "codex-agent-sdk/build/npm/consumer")}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes), "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "transport.zip", "bytes": len(raw), "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != receipt_bytes
                or captured_plan.read_bytes() != plan_bytes or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != zipped
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("JavaScript validation original inputs or upload changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport


def capture_sdk_native_prepared_upload(plan_path, destination, *, expected_phase_plan,
        artifact_id, artifact_sha256, trusted_workflow_sha, repository_root=None, environ=None, token):
    """Capture the fixed preparation producer; receiver content admission is separate."""
    from products.restore import PHASE_PLAN_KEYS
    from products.inventory import require_regular_directory
    from products.sdk_package import _require_capability_output_separate
    from sdk_native_prepare import TASK, validate_anchor

    phase = require_exact_keys(expected_phase_plan, PHASE_PLAN_KEYS, "Elected native preparation plan")
    validate_anchor(phase)
    require_sha256(phase["buildKey"], "Native preparation elected key")
    phase_bytes = canonical_json_bytes(phase)
    require_integer(artifact_id, "Native preparation upload ID", 1)
    require_sha256(artifact_sha256, "Native preparation upload digest")
    if not isinstance(token, str) or not token:
        raise ValueError("Native preparation capture requires an observation token")
    root = (Path(__file__).resolve().parents[1] if repository_root is None else Path(repository_root)).resolve(strict=True)
    plan_path, destination = Path(plan_path).absolute(), Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, [root, plan_path])
        if destination.exists() or destination.is_symlink():
            raise ValueError("Native preparation capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    with tempfile.TemporaryDirectory(prefix="sdk-native-upload-") as temporary:
        prepared = Path(temporary).resolve() / "capture"
        captured_plan = prepared / "plan/impact-plan.json"
        captured_plan.parent.mkdir(parents=True)
        captured_plan.write_bytes(plan_bytes)
        plan = _validate_plan(captured_plan, root)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("Native preparation capture requires an authorized PR or merge-group plan")
        producer = validate_producer(_consumer(plan, os.environ if environ is None else environ)["producer"])
        job = "product-validation / sdk-native-prepare"
        observed = _observe_ci_producer_jobs({"native-prepared": producer},
            jobs_by_phase={"native-prepared": job}, trusted_workflow_sha=trusted_workflow_sha, token=token)
        name = f"codex-agent-sdk-native-prepared-{producer['tree']}-attempt-{producer['runAttempt']}"
        artifact, raw = _download_contract_ci_upload(artifact_id, artifact_sha256, name, producer, observed[0]["run"], token)
        _require_artifact_job_window(observed[0], job, artifact)
        archive = prepared / "transport.zip"
        archive.write_bytes(raw)
        zipped, _, _ = verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
        original = prepared / "original"
        safe_extract(archive, original)
        if {path.name for path in original.iterdir()} != {"original-plan", "prepared-sources", "staged-sdks", "diagnostics"}:
            raise ValueError("Native preparation upload has an unexpected layout")
        for directory in original.iterdir():
            require_regular_directory(directory, "Native preparation original directory")
        for directory, names in (("original-plan", {"impact-plan.json", "phase-plan.json"}),
                                 ("diagnostics", {"execution.json", "gradle.log"}),
                                 ("prepared-sources", set(NATIVE_BINDINGS))):
            if {path.name for path in (original / directory).iterdir()} != names:
                raise ValueError("Native preparation upload has an unexpected original inventory")
        for directory in [original / "staged-sdks", *(original / "prepared-sources" / name for name in NATIVE_BINDINGS)]:
            require_regular_directory(directory, "Native preparation content directory")
            if not regular_file_inventory(directory):
                raise ValueError("Native preparation content directory is empty")
        if (read_regular_file_bytes(original / "original-plan/impact-plan.json") != plan_bytes
                or read_regular_file_bytes(original / "original-plan/phase-plan.json") != phase_bytes):
            raise ValueError("Native preparation original plans differ from the caller election")
        execution = require_exact_keys(_canonical_control(original / "diagnostics/execution.json", "Native preparation execution"),
            {"schemaVersion", "producer", "buildKey", "command", "returnCode", "launchError", "elapsedNs"},
            "Native preparation execution")
        command = require_array(execution["command"], "Native preparation command")
        if (require_integer(execution["schemaVersion"], "Native preparation execution schema", 1) != 1
                or execution["producer"] != producer or execution["buildKey"] != phase["buildKey"]
                or type(execution["returnCode"]) is not int or execution["returnCode"] != 0
                or execution["launchError"] is not None
                or any(type(argument) is not str for argument in command) or command.count(TASK) != 1):
            raise ValueError("Native preparation execution differs from its observed successful producer")
        require_integer(execution["elapsedNs"], "Native preparation elapsed time", 0)
        transport = {"artifact": artifact, "captureProducer": producer, "observed": observed,
                     "phasePlan": phase}
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        expected_files = sorted([
            {"relativePath": "plan/impact-plan.json", "bytes": len(plan_bytes), "sha256": sha256_bytes(plan_bytes)},
            {"relativePath": "transport.zip", "bytes": len(raw), "sha256": artifact_sha256},
            {"relativePath": "capture-transport.json", "bytes": len(transport_bytes),
             "sha256": sha256_bytes(transport_bytes)},
            *({**record, "relativePath": f"original/{record['relativePath']}"} for record in zipped),
        ], key=lambda record: record["relativePath"])
        if (read_regular_file_bytes(plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes
                or captured_plan.read_bytes() != plan_bytes or canonical_json_bytes(expected_phase_plan) != phase_bytes
                or sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != zipped
                or regular_file_inventory(prepared, allow_empty=True) != expected_files):
            raise ValueError("Native preparation original plan or upload changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True, expected_inventory=expected_files)
    return transport


def capture_product_resume_inputs(
    plan_path: Path, destination: Path, *, uploads: Mapping[str, Any],
    trusted_workflow_sha: str, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None, token: str,
    trusted_contract_workflow_path: str | None = None,
    trusted_contract_continuation_job: str | None = None,
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
        if (trusted_contract_workflow_path is None) != (trusted_contract_continuation_job is None):
            raise ValueError("Contract original workflow path and job must be pinned together")
        workflow_policy = (
            {"trusted_workflow_sha": trusted_workflow_sha}
            if trusted_contract_workflow_path is None else
            {"trusted_workflows_by_phase": {"metadata": {
                "path": trusted_contract_workflow_path, "sha": trusted_workflow_sha,
            }}, "jobs_by_phase": {"metadata": trusted_contract_continuation_job}})
        observed = _observe_contract_producer_runs(
            {"metadata": producer}, phases=("metadata",),
            token=token, **workflow_policy)
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
            verified_zip_contents(archive, retained_paths=(), allow_empty_members=True, **_CATALOG_ZIP_LIMITS)
            safe_extract(archive, prepared / name)
            artifacts[name] = artifact
        if read_regular_file_bytes(prepared / "plan/impact-plan.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True) != plan_bytes:
            raise ValueError("Captured product plan differs from the validated original plan")
        transport = {"artifacts": artifacts, "captureProducer": producer, "observed": observed}
        write_canonical_json(prepared / "capture-transport.json", transport)
        publish_regular_tree(prepared, destination, allow_empty=True)
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
        keyring_bytes = git_regular_blob_bytes(
            root, plan["validationCommit"], _KEYRING_PATH, max_bytes=64 * 1024)
        keyring = load_canonical_json_bytes(keyring_bytes)
        trust_sources = [("product-signing-keys.json", keyring_bytes)]
        for record in (keyring["activeKey"], *keyring["retiredKeys"]):
            if record is not None:
                relative = f"keys/{record['keyId']}.pub"
                trust_sources.append((relative, git_regular_blob_bytes(
                    root, plan["validationCommit"], f"{_KEYS_ROOT}/{record['keyId']}.pub",
                    max_bytes=64 * 1024)))
        trust_files = sorted((
            {"relativePath": relative, "bytes": len(raw), "sha256": sha256_bytes(raw)}
            for relative, raw in trust_sources
        ), key=lambda record: record["relativePath"])
        if regular_file_inventory(trust.keyring.parent) != trust_files:
            raise ValueError("Completed Contract release trust differs from tracked Git bytes")
        state = private / "state"
        snapshot_regular_tree(state_root, state)
        result = _canonical_control(state / "contract-reuse-result.json", "Completed Contract result")
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        _validate_reuse_result(result, (contract,), require_complete=True)
        handoff = prepared / "contract-input"
        handoff_files = regular_file_inventory(handoff_root)
        snapshot_regular_tree(handoff_root, handoff)
        expected_files = sorted((
            *({**record, "relativePath": f"trust/{record['relativePath']}"} for record in trust_files),
            *({**record, "relativePath": f"contract-input/{record['relativePath']}"} for record in handoff_files),
        ), key=lambda record: record["relativePath"])
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
        if regular_file_inventory(prepared) != expected_files:
            raise ValueError("Completed Contract handoff changed before publication")
        evidence = {
            "attestation": f"contract-input/{stem}.attestation.json",
            "attestationSignature": f"contract-input/{stem}.attestation.sig",
            "publicKey": "contract-input/public-key.pub", "expectedTrustDomain": "release",
            "keyring": _relative(prepared, trust.keyring), "keysDirectory": _relative(prepared, trust.keys),
        }
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return evidence


def _recover_prior_runtime_aggregate_release(plan_path, plan, phase, source, destination, *,
        repository_root, environ, trusted_workflow_sha):
    """Retain the original signed closure after fresh CI and full signature gates."""
    original = verify_object(source, build_key=phase["buildKey"],
        receipt_sha256=phase["receiptSha256"], object_sha256=phase["objectSha256"])["receipt"]["producer"]
    current = _consumer(plan, environ)["producer"]
    if (original["runId"], original["runAttempt"]) >= (current["runId"], current["runAttempt"]):
        return []
    token = environ["GITHUB_TOKEN"]
    run = api_json(f"https://api.github.com/repos/{original['repository']}/actions/runs/"
                   f"{original['runId']}/attempts/{original['runAttempt']}", token)
    workflow = _runtime_prior_workflow_sha(run, trusted_workflow_sha)
    if workflow is None:
        raise ValueError("Retained aggregate source lacks its reviewed original workflow")
    name = f"codex-agent-runtime-aggregate-release-handoff-{original['tree']}-attempt-{original['runAttempt']}"
    uploads = paginated_items(f"https://api.github.com/repos/{original['repository']}/actions/runs/"
                             f"{original['runId']}/artifacts", "artifacts", token)
    matches = [item for item in uploads if item.get("name") == name]
    if not matches:
        return []
    if len(matches) != 1:
        raise ValueError("Retained aggregate release upload is ambiguous")
    artifact = matches[0]
    with tempfile.TemporaryDirectory(prefix="runtime-retained-aggregate-") as temporary:
        private = Path(temporary).resolve()
        transport = _qualified_aggregate_capture(plan, current, original, phase, artifact,
            private / "capture", trusted_workflow_sha=trusted_workflow_sha, token=token)
        if transport is None:
            transport = capture_runtime_aggregate_release_upload(plan_path, private / "capture",
                artifact_id=artifact["id"], artifact_sha256=artifact["digest"], trusted_workflow_sha=workflow,
                expected_build_key=phase["buildKey"], expected_metadata_receipt_sha256=phase["receiptSha256"],
                original_producer=original, repository_root=repository_root, environ=environ, token=token)
        trust = _release_trust(repository_root, plan["validationCommit"], private / "policy")
        if trust is None:
            raise ValueError("Retained aggregate requires caller-owned release verification policy")
        records = stage_runtime_aggregate_release_evidence([
            {"receiptSha256": phase["receiptSha256"], "handoffRoot": "original"}],
            private / "capture", destination / "runtime-aggregate-release-evidence/0",
            keyring=trust.keyring, keys_directory=trust.keys)
        write_canonical_json(destination / "recovered-runtime-aggregate-upload.json", transport)
    return rebase_runtime_aggregate_release_records(records,
        destination / "runtime-aggregate-release-evidence/0", destination)


def _qualified_aggregate_capture(plan, current, original, phase, artifact, destination, *, trusted_workflow_sha, token):
    from products.restore import _VERIFICATION_SESSION
    from products.verified_evidence import _source_identity
    from products.sdk_protected_runtime import _original_carrier
    session = _VERIFICATION_SESSION.get()
    checkpoint = session.get("referenceCheckpoint") if session else None
    if checkpoint is None or checkpoint[2] != _source_identity():
        return None
    _root, refs, _policy = checkpoint
    sources = [source for source in refs["sources"] if source["kind"] == "aggregate"
               and source["receipt"]["buildKey"] == phase["buildKey"]
               and sha256_bytes(canonical_json_bytes(source["receipt"])) == phase["receiptSha256"]
               and source["receipt"]["producer"] == original
               and source["artifactId"] == artifact["id"] and source["artifactSha256"] == artifact["digest"]]
    if not sources:
        return None
    if len(sources) != 1:
        raise ValueError("Qualified aggregate reference is ambiguous")
    source = sources[0]
    rows = [{**row, "relativePath": row["sourcePath"]} for row in refs["references"]
            if row["source"] == source["relativePath"]
            and row["relativePath"].startswith(source["relativePath"] + "/")]
    captured = _capture_runtime_original_reference_members(plan, current, source, rows,
        destination / "original", trusted_workflow_sha=trusted_workflow_sha, token=token)
    workflow = _runtime_prior_workflow_sha(captured["observed"][0]["run"], trusted_workflow_sha)
    caller = _canonical_control(destination / "original/caller.json", "Qualified original aggregate caller")
    if (caller.get("transportProducer") != original or caller.get("target") != "aggregate"
            or caller.get("trustedWorkflowSha") != workflow
            or caller.get("metadataReceiptSha256") != phase["receiptSha256"]):
        raise ValueError("Qualified aggregate caller changes its observed original provenance")
    _original_carrier(destination / "original", phase["receiptSha256"], phase["buildKey"])
    return {key: captured[key] for key in ("artifact", "captureProducer", "observed")} | {
        "aggregateBuildKey": phase["buildKey"], "aggregateReceiptSha256": phase["receiptSha256"]}


@verification_scoped
def resume_products(
    plan_path: Path, discovery_root: Path, state_root: Path, contract_handoff: Path,
    destination: Path, github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    sdk_original_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
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
        snapshot_regular_tree(discovery_root, prepared / "discovery", allow_empty=True)
        maven_discovery = prepared / "discovery/sdk-maven-evidence"
        if maven_discovery.exists() or maven_discovery.is_symlink():
            require_regular_directory(maven_discovery, "Discovered Maven evidence carriers")
            _capture_maven_handoffs(tuple(sorted(maven_discovery.iterdir())), prepared / "sdk-maven-evidence")
        metadata_discovery = prepared / "discovery/sdk-metadata-evidence"
        if metadata_discovery.exists() or metadata_discovery.is_symlink():
            require_regular_directory(metadata_discovery, "Discovered metadata evidence carriers")
            _capture_metadata_handoffs(tuple(sorted(metadata_discovery.iterdir())), prepared / "sdk-metadata-evidence")
        snapshot_regular_tree(state_root, prepared / "contract-state", allow_empty=True)
        original_producer = validate_producer(_canonical_control(
            prepared / "discovery/producer.json", "Original Contract control producer"))
        state_producer = validate_producer(_canonical_control(
            prepared / "contract-state/producer.json", "Original Contract state producer"))
        current_producer = _consumer(plan, environment)["producer"]
        if (any(original_producer[field] != current_producer[field]
                for field in current_producer if field != "runAttempt")
                or original_producer["runAttempt"] > current_producer["runAttempt"]
                or state_producer != original_producer):
            raise ValueError("Original Contract snapshot differs from the current consumer")
        # Replay original transport under its own consumer; new resume output
        # below remains bound to the actual current execution environment.
        contract_environment = {**environment,
            "GITHUB_RUN_ATTEMPT": str(original_producer["runAttempt"])}
        complete = advance_contract(
            captured_plan, prepared / "discovery", prepared / "contract-state", [],
            private / "replayed-contract", private / "contract-outputs",
            repository_root=root, environ=contract_environment, sdk_validation_tooling=sdk_validation_tooling,
            **({"sdk_apple_validation_policy": sdk_apple_validation_policy} if sdk_apple_validation_policy is not None else {}))
        if complete["fullReuse"] is not True:
            raise ValueError("Product resume requires complete original Contract phases")
        evidence_root = prepared / "authenticated-contract"
        evidence = _capture_completed_contract_handoff(
            captured_plan, prepared / "contract-state", contract_handoff, evidence_root,
            repository_root=root, environ=contract_environment)
        contract_request = _wave_control(
            prepared / "discovery/contract-reuse-request.json", "Original Contract request")
        requested = _requested(plan)
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        if contract not in _dependency_closure(requested):
            raise ValueError("Product resume selection has no Contract dependency")
        versions = _versions(root, plan["validationCommit"])
        source = sdk_runtime_source(root, plan["validationCommit"], instances=_dependency_closure(requested),
                                    runtime_version=versions["runtime-release"], sdk_version=versions["sdk"])
        authorities, unavailable = _authorities(root, plan["validationCommit"],
            _dependency_closure(requested, sdk_runtime_external=source is not None))
        if authorities is None:
            raise ValueError(unavailable or "Product phase authority is unavailable")
        wave = _wave_request(
            plan, root, prepared, requested, _versions(root, plan["validationCommit"]), authorities, [],
            _rebase_contract_evidence_paths(evidence, evidence_root, prepared))
        wave["catalogs"] = _rebase_catalog_paths(contract_request["catalogs"], prepared / "discovery", prepared)
        wave.update(_rebase_native_request(contract_request, prepared / "discovery", prepared))
        initial_objects, original_phases = _completed_contract_objects(
            plan, prepared / "contract-state", prepared, contract_environment)
        wave["availableObjects"] = initial_objects
        ready_plans = {}

        def retain(instance, phase_plan):
            if instance in ready_plans:
                raise ValueError("Product resume elected a duplicate ready phase")
            ready_plans[instance] = phase_plan

        reuse = _plan_with_sdk_tooling(wave, sdk_validation_tooling, apple_policy=sdk_apple_validation_policy,
            apple_package_origin=_apple_package_origin(captured_plan, root, sdk_original_workflow_sha, environment),
            build_plan_consumer=retain,
            **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        prior_records = []
        if environment.get("GITHUB_TOKEN") and sdk_original_workflow_sha:
            if environment.get("CODEX_AGENT_HOSTED_CACHE_BACKEND"):
                from hosted_reuse_proof import qualify_checkpoint
                qualify_checkpoint(plan, private / "reference-checkpoint", environment["GITHUB_TOKEN"],
                                   trusted_workflow_sha=sdk_original_workflow_sha)
            attempts = _prior_failed_pr_attempts(
                plan, _consumer(plan, environment)["producer"], environment["GITHUB_TOKEN"])
            artifacts_by_run, jobs_by_attempt, tried = {}, {}, set()
            while attempts:
                wanted = {_identity(phase): phase["buildKey"] for phase in reuse["phases"]
                    if phase["product"] == "runtime" and phase["component"] in _RECOVERABLE_RUNTIME_COMPONENTS
                    and phase["state"] == "build"
                    and (_identity(phase), phase["buildKey"]) not in tried}
                if not wanted:
                    break
                tried.update(wanted.items())
                captured = capture_prior_failed_runtime_phases(
                    plan, _consumer(plan, environment)["producer"], wanted,
                    prepared / "prior-failed-runtime", trusted_workflow_sha=sdk_original_workflow_sha,
                    token=environment["GITHUB_TOKEN"], attempts=attempts,
                    artifacts_by_run=artifacts_by_run, jobs_by_attempt=jobs_by_attempt)
                if not captured:
                    break
                prior_records = _prior_failed_runtime_objects(prepared / "prior-failed-runtime", prepared)
                wave["availableObjects"] = sorted((*initial_objects, *prior_records), key=_identity)
                completed_evidence = {_identity(record) for record in wave["runtimeValidationEvidence"]}
                wave["runtimeValidationEvidence"] = sorted([
                    *wave["runtimeValidationEvidence"],
                    *_initial_runtime_validation_handoffs(
                        tuple(instance for instance in _dependency_closure(requested)
                              if instance not in completed_evidence),
                        wave["availableObjects"], prepared,
                        prepared / "initial-runtime-validation-handoffs", prepared,
                    ),
                ], key=_identity)
                ready_plans.clear()
                reuse = _plan_with_sdk_tooling(wave, sdk_validation_tooling,
                    apple_policy=sdk_apple_validation_policy,
                    apple_package_origin=_apple_package_origin(captured_plan, root, sdk_original_workflow_sha, environment),
                    build_plan_consumer=retain,
                    **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
        _, selected, phases = _validate_reuse_result(reuse, requested, require_complete=False,
            sdk_runtime_external=wave.get("sdkRuntimeSource") == "released-default")
        by_id = {_identity(phase): phase for phase in phases}
        originals = {_identity(phase): phase for phase in original_phases}
        if any(by_id.get(instance, {}).get("state") != "retained" for instance in originals):
            raise ValueError("Product resume did not retain every authenticated Contract object")
        elected_prior = _elected_prior_runtime_records(prior_records, selected, by_id)
        sources = {_identity(record): prepared / record["objectPath"]
                   for record in (*initial_objects, *elected_prior.values())}
        remote_sources = _catalog_object_sources(wave)
        for instance in selected:
            if instance not in sources:
                phase = by_id[instance]
                sources[instance] = remote_sources[(phase["source"], phase["transportSource"]["indexSha256"], phase["buildKey"])]
        aggregate = PhaseInstanceId("runtime", "runtime-aggregate", "metadata", "aggregate")
        if (aggregate in elected_prior and not wave.get(_AGGREGATE_REQUEST_KEY)
                and environment.get("GITHUB_TOKEN") and sdk_original_workflow_sha):
            records = _recover_prior_runtime_aggregate_release(captured_plan, plan, by_id[aggregate],
                sources[aggregate], prepared, repository_root=root, environ=environment,
                trusted_workflow_sha=sdk_original_workflow_sha)
            if records:
                _merge_native_comparison_records(wave, records, key=_AGGREGATE_REQUEST_KEY)
                ready_plans.clear()
                reuse = _plan_with_sdk_tooling(wave, sdk_validation_tooling, apple_policy=sdk_apple_validation_policy,
                    apple_package_origin=_apple_package_origin(captured_plan, root, sdk_original_workflow_sha, environment),
                    build_plan_consumer=retain,
                    **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
                _, release_selected, phases = _validate_reuse_result(reuse, requested, require_complete=False,
                    sdk_runtime_external=wave.get("sdkRuntimeSource") == "released-default")
                release_by_id = {_identity(phase): phase for phase in phases}
                if (release_selected != selected or any(any(release_by_id[identity][field] != by_id[identity][field]
                        for field in ("buildKey", "receiptSha256", "objectSha256")) for identity in selected)):
                    raise ValueError("Retained aggregate release changes the selected immutable phase closure")
                by_id = release_by_id
        carrier_phases = []
        for instance in selected:
            if instance in originals:
                carrier_phases.append(originals[instance])
            elif instance in elected_prior:
                shard = (prepared / "prior-failed-runtime" / instance.component / instance.phase / instance.target /
                         "phases" / instance.phase / "original/shard")
                descriptor = _canonical_control(shard / PHASE_SHARD_NAME, "Prior failed Runtime shard")
                receipt = verify_phase_shard(shard, instance)["receipt"]
                carrier_phases.append({**by_id[instance], "state": "reused", "source": "phase-shard",
                    "transportSource": {"kind": "phase-shard",
                        "descriptorSha256": sha256_bytes(canonical_json_bytes(descriptor)),
                        "producer": receipt["producer"]}, "misses": []})
            else:
                carrier_phases.append(by_id[instance])
        normalized = {"schemaVersion": 1, "result": "complete", "fullReuse": True,
                      "phases": carrier_phases,
                      "matrices": {"contract": [], "runtime": [], "sdk": []}}
        write_carrier(prepared / ("carrier" if reuse["fullReuse"] else "reused-carrier"),
                      normalized, selected, sources, _consumer(plan, environment), object_root=prepared)
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
        publish_regular_tree(prepared, destination, allow_empty=True,
                             expected_inventory=regular_file_inventory(prepared, allow_empty=True))
        _retarget_runtime_original_captures(prepared, destination)
    github_output(github_output_path, {"full_reuse": result["fullReuse"],
        "target_jobs_required": result["targetJobsRequired"], "product_reuse_reason": result["reason"]})
    return result


def discover(
    plan_path: Path, destination: Path, github_output_path: Path, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
    native_evidence_roots: tuple[Path, ...] = (),
    adapter_evidence_roots: tuple[Path, ...] = (),
    sdk_evidence_roots: tuple[Path, ...] = (),
    sdk_apple_evidence_roots: tuple[Path, ...] = (),
    sdk_maven_evidence_roots: tuple[Path, ...] = (),
    sdk_metadata_evidence_roots: tuple[Path, ...] = (),
    sdk_apple_validation_policy: Mapping[str, Any] | None = None,
    aggregate_evidence_roots: tuple[Path, ...] = (),
    sdk_validation_tooling: Mapping[str, Any] | None = None,
    tooling_java_executable: Path | None = None,
    tooling_workflow_sha: str | None = None,
    sdk_facade_metadata_admission=None, sdk_android_metadata_admission=None,
) -> dict[str, Any]:
    automatic_tooling = tooling_java_executable is not None or tooling_workflow_sha is not None
    if automatic_tooling and (tooling_java_executable is None or tooling_workflow_sha is None
                             or sdk_validation_tooling is not None):
        raise ValueError("Automatic tooling requires caller Java/workflow pins and no explicit tooling policy")
    # A failing adapter must never make a missing output look like permission to skip work.
    github_output(github_output_path, {
        "full_reuse": False,
        "target_jobs_required": True,
        "product_reuse_reason": "not-evaluated",
        "contract_next_phase": "none",
        "contract_reconciliation_required": False,
        "tooling_artifact_id": "",
        "tooling_artifact_sha256": "",
        "tooling_transport_producer": "",
        "tooling_required": False,
        "tooling_miss": False,
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

    versions = _versions(root, plan["validationCommit"])
    source = sdk_runtime_source(root, plan["validationCommit"], instances=_dependency_closure(requested),
                                runtime_version=versions["runtime-release"], sdk_version=versions["sdk"])
    closure = _dependency_closure(requested, sdk_runtime_external=source is not None)
    environment = os.environ if environ is None else environ
    trust = _release_trust(root, plan["validationCommit"], destination)
    apple_package_origin = _apple_package_origin(plan_path, root, tooling_workflow_sha, environment)
    tooling_runs: list[int] = []
    needs_tooling = automatic_tooling and any(instance.product == "sdk" and (
        instance.component in NATIVE_BINDINGS and instance.phase in {"validation", "metadata"}
        or instance == PhaseInstanceId("sdk", "javascript", "metadata", "node")
        or instance == PhaseInstanceId("sdk", "sdk-ios", "package", "ios"))
        for instance in closure)
    github_output(github_output_path, {
        "tooling_required": needs_tooling, "tooling_miss": needs_tooling,
    })
    catalogs = _discover_catalogs(plan, destination, trust, environment, versions, root,
        **({"tooling_candidate_runs": tooling_runs} if needs_tooling else {}))
    native_records = _capture_native_handoffs(
        native_evidence_roots, destination / "native-runtime-evidence", destination, trust)
    adapter_records = _capture_native_handoffs(
        adapter_evidence_roots, destination / "adapter-runtime-evidence", destination, trust, adapter=True)
    catalog_sdk_roots = tuple(catalog.sdk_validation_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.sdk_validation_evidence_root is not None)
    if automatic_tooling and not needs_tooling:
        catalog_sdk_roots = ()  # Unrequested SDK proofs cannot require tooling setup.
    if needs_tooling:
        if trust is not None and environment.get("GITHUB_TOKEN"):
            from tooling_discovery import discover_tooling_ci
            with tempfile.TemporaryDirectory(prefix="sdk-tooling-selection-") as temporary:
                original = Path(temporary).resolve() / "discovered"
                selected = discover_tooling_ci(original, root,
                    candidate_run_ids=tooling_runs, trusted_workflow_sha=tooling_workflow_sha,
                    policy_revision=plan["validationCommit"], java_executable=tooling_java_executable,
                    token=environment["GITHUB_TOKEN"])
                retained = destination / "tooling-discovery"
                if selected["toolingPolicy"] is not None:
                    policy = dict(selected["toolingPolicy"])
                    for field in ("evidence", "publicKey", "keyring", "keysDirectory"):
                        policy[field] = str(retained / Path(policy[field]).relative_to(original))
                    selected = {**selected, "toolingPolicy": policy}
                    write_canonical_json(original / "capture/tooling-policy.json", policy)
                write_canonical_json(original / "discovery.json", selected)
                # Only unsigned invocation paths changed. Original signed bytes
                # remain intact, and publication occurs after private verification.
                publish_regular_tree(original, retained, allow_empty=True)
            sdk_validation_tooling = selected["toolingPolicy"]
            if selected["selected"] is not None:
                locator = selected["selected"]
                github_output(github_output_path, {
                    "tooling_artifact_id": locator["artifactId"],
                    "tooling_miss": False,
                    "tooling_artifact_sha256": locator["artifactSha256"],
                    "tooling_transport_producer": canonical_json_bytes(locator["transportProducer"]).decode().strip(),
                })
        if sdk_validation_tooling is None:
            # No invocation authority means no catalog SDK proof admission. The
            # planner still must prove every capability or select missing work.
            catalog_sdk_roots = ()
    sdk_records = _capture_sdk_handoffs((*catalog_sdk_roots, *sdk_evidence_roots), destination / "sdk-validation-evidence", destination,
        repository=root, policy_revision=plan["validationCommit"], tooling=sdk_validation_tooling)
    catalog_apple_roots = tuple(catalog.sdk_apple_validation_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.sdk_apple_validation_evidence_root is not None and any(
            (instance.product, instance.component, instance.phase) == ("sdk", "sdk-ios", "validation")
            for instance in closure))
    if automatic_tooling and sdk_apple_validation_policy is None:
        if sdk_validation_tooling is None:
            # Catalog proofs cannot supply missing current-invocation authority.
            # Explicit proof inputs still fail closed below instead of disappearing.
            catalog_apple_roots = ()
        elif (catalog_apple_roots or sdk_apple_evidence_roots
              or PhaseInstanceId("sdk", "sdk-ios", "package", "ios") in closure):
            if trust is None:
                raise ValueError("Automatic Apple discovery requires current Git release trust")
            from sdk_apple_policy import caller_apple_validation_policy
            sdk_apple_validation_policy = caller_apple_validation_policy(
                Path(plan_path).absolute(), sdk_validation_tooling,
                keyring=trust.keyring, keys_directory=trust.keys, environ=environment)
    apple_records = _capture_apple_handoffs((*catalog_apple_roots, *sdk_apple_evidence_roots),
        destination / "sdk-apple-validation-evidence", destination)
    catalog_maven_roots = tuple(catalog.sdk_maven_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.sdk_maven_evidence_root is not None and any(
            instance.product == "sdk" and instance.component in {"sdk-core", "sdk-android"}
            for instance in closure))
    _capture_maven_handoffs((*catalog_maven_roots, *sdk_maven_evidence_roots),
        destination / "sdk-maven-evidence")
    catalog_metadata_roots = tuple(catalog.sdk_metadata_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.sdk_metadata_evidence_root is not None and any(
            instance.product == "sdk" and instance.component in {"sdk-core", "sdk-android"}
            and instance.phase == "metadata" for instance in closure))
    _capture_metadata_handoffs((*catalog_metadata_roots, *sdk_metadata_evidence_roots),
        destination / "sdk-metadata-evidence")
    catalog_aggregate_roots = tuple(catalog.runtime_aggregate_evidence_root
        for catalog in sorted(catalogs, key=lambda value: SOURCES.index(value.source))
        if catalog.runtime_aggregate_evidence_root is not None)
    aggregate_records = _capture_aggregate_handoffs((*catalog_aggregate_roots, *aggregate_evidence_roots),
        destination / "runtime-aggregate-release-evidence", destination, trust)

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
        _merge_native_comparison_records(contract_request, apple_records, key="sdkAppleValidationEvidence")
        _merge_native_comparison_records(contract_request, aggregate_records, key=_AGGREGATE_REQUEST_KEY)
        write_canonical_json(destination / "contract-reuse-request.json", contract_request)
        contract_ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
        contract_result = _plan_with_sdk_tooling(
            contract_request, sdk_validation_tooling,
            apple_policy=sdk_apple_validation_policy,
            apple_package_origin=apple_package_origin,
            build_plan_consumer=lambda instance, phase_plan: contract_ready_plans.setdefault(
                instance, phase_plan,
            ),
        )
        write_canonical_json(destination / "contract-reuse-result.json", contract_result)
        if contract_result["fullReuse"] is not True:
            if (plan["event"] == "pull_request" and trust is not None
                    and tooling_workflow_sha is not None and environment.get("GITHUB_TOKEN")):
                from contract_retained_recovery import discover_retained_contract
                recovered = discover_retained_contract(
                    destination / "retained-contract", plan=plan,
                    consumer_producer=_consumer(plan, environment)["producer"],
                    contract_request=contract_request, trusted_workflow_sha=tooling_workflow_sha,
                    keyring=trust.keyring, keys_directory=trust.keys, token=environment["GITHUB_TOKEN"],
                    sdk_validation_tooling=sdk_validation_tooling,
                    sdk_apple_validation_policy=sdk_apple_validation_policy)
                if recovered is not None:
                    complete = recovered["result"]["fullReuse"]
                    publish_regular_tree(recovered["carrier"], destination / (
                        "carrier" if complete else "reused-carrier"))
                    write_canonical_json(destination / "contract-reuse-request.json", recovered["request"])
                    write_canonical_json(destination / "contract-reuse-result.json", recovered["result"])
                    write_canonical_json(destination / "reuse-wave-result.json", recovered["result"])
                    write_canonical_json(destination / "producer.json", _consumer(plan, environment)["producer"])
                    ready = recovered["readyPlans"]
                    _write_ready_plans(destination, ready)
                    return _finish(destination, request, _result(
                        requested, complete=False, reason=(
                            "retained-contract-complete" if complete else "retained-contract-prefix"),
                        reuse=recovered["result"],
                    ), github_output_path, contract_reconciliation_required=True,
                        contract_next_phase=_contract_ready_phase(ready))
            if any(phase.get("state") == "reused" for phase in contract_result["phases"]):
                _write_reused_carrier(
                    contract_result,
                    (contract,),
                    catalogs,
                    destination / "reused-carrier",
                    _consumer(plan, environment),
                    require_complete=False,
                    object_root=destination,
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
    _merge_native_comparison_records(wave_request, apple_records, key="sdkAppleValidationEvidence")
    _merge_native_comparison_records(wave_request, aggregate_records, key=_AGGREGATE_REQUEST_KEY)
    write_canonical_json(destination / "reuse-wave-request.json", wave_request)
    ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain_ready_plan(instance: PhaseInstanceId, phase_plan: dict[str, Any]) -> None:
        if instance in ready_plans:
            raise ValueError(f"Duplicate ready phase plan: {instance}")
        ready_plans[instance] = phase_plan

    reuse = _plan_with_sdk_tooling(wave_request, sdk_validation_tooling, apple_policy=sdk_apple_validation_policy,
        apple_package_origin=apple_package_origin,
        build_plan_consumer=retain_ready_plan,
        **_metadata_admissions(sdk_facade_metadata_admission, sdk_android_metadata_admission))
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
        _reverify_complete(reuse, requested, catalogs, destination, _consumer(plan, environment),
                           sdk_runtime_external=source is not None)
    elif any(phase.get("state") == "reused" for phase in reuse["phases"]):
        _write_reused_carrier(
            reuse,
            requested,
            catalogs,
            destination / "reused-carrier",
            _consumer(plan, environment),
            require_complete=False,
            sdk_runtime_external=source is not None,
            object_root=destination,
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
    catalog_command = commands.add_parser("stage-release-catalog")
    for name in ("source-root", "destination", "keyring", "keys-directory"):
        catalog_command.add_argument(f"--{name}", type=Path, required=True)
    catalog_command.add_argument("--repository", required=True)
    catalog_command.add_argument("--source", choices=("stable", "promoted-main"), required=True)
    discover_command = commands.add_parser("discover")
    discover_command.add_argument("--plan", type=Path, required=True)
    discover_command.add_argument("--destination", type=Path, required=True)
    discover_command.add_argument("--handoff", type=Path)
    discover_command.add_argument("--native-runtime-evidence", type=Path, action="append", default=[])
    discover_command.add_argument("--adapter-runtime-evidence", type=Path, action="append", default=[])
    discover_command.add_argument("--github-output", type=Path, required=True)
    discover_command.add_argument("--tooling-java-executable", type=Path)
    discover_command.add_argument("--tooling-workflow-sha")
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
    resume_command.add_argument("--handoff", type=Path)
    resume_command.add_argument("--runtime-matrix", action="store_true",
                                help="Elect Runtime work in the same private verification session")
    for name in ("plan", "discovery-root", "state-root", "contract-handoff", "destination", "github-output"):
        resume_command.add_argument(f"--{name}", type=Path, required=True)
    resume_command.add_argument("--sdk-validation-tooling", type=Path,
                               help="Current caller-owned tooling policy JSON, never a retained request field")
    for command in (products_command, resume_command):
        command.add_argument("--sdk-original-workflow-sha",
                             help="Caller-pinned product workflow SHA for original Apple package replay")
    resume_capture = commands.add_parser("capture-product-resume-inputs")
    resume_capture.add_argument("--plan", type=Path, required=True)
    resume_capture.add_argument("--destination", type=Path, required=True)
    resume_capture.add_argument("--trusted-workflow-sha", required=True)
    resume_capture.add_argument("--trusted-contract-workflow-path")
    resume_capture.add_argument("--trusted-contract-continuation-job")
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
    supervisor_execute.add_argument("--sdk-original-workflow-sha")
    aggregate_execute = commands.add_parser("execute-runtime-aggregate")
    for name in ("plan", "discovery-root", "destination", "variant-trust-root"):
        aggregate_execute.add_argument(f"--{name}", type=Path, required=True)
    aggregate_execute.add_argument("--state-root", type=Path)
    aggregate_execute.add_argument("--expected-build-key", required=True)
    aggregate_execute.add_argument("--sdk-validation-tooling", type=Path)
    aggregate_execute.add_argument("--sdk-original-workflow-sha")
    sdk_metadata = commands.add_parser("execute-sdk-metadata")
    for name in ("plan", "discovery-root", "destination", "compatibility-request",
                 "runtime-stages", "staged-sdks", "sdk-validation-tooling"):
        sdk_metadata.add_argument(f"--{name}", type=Path, required=True)
    sdk_metadata.add_argument("--state-root", type=Path)
    sdk_metadata.add_argument("--component", choices=NATIVE_BINDINGS, required=True)
    sdk_metadata.add_argument("--expected-build-key", required=True)
    sdk_metadata.add_argument("--sdk-original-workflow-sha")
    for command in (discover_command, products_command):
        command.add_argument("--sdk-maven-evidence", type=Path, action="append", default=[])
        command.add_argument("--sdk-metadata-evidence", type=Path, action="append", default=[])
        command.add_argument("--sdk-validation-evidence", type=Path, action="append", default=[])
        command.add_argument("--sdk-apple-validation-evidence", type=Path, action="append", default=[])
        command.add_argument("--runtime-aggregate-release-evidence", type=Path, action="append", default=[])
        command.add_argument("--sdk-validation-tooling", type=Path,
                             help="Current caller-owned tooling policy JSON, never a retained request field")
    for command in (discover_command, products_command, advance_command, resume_command, runtime_collection,
                    sdk_metadata, supervisor_execute, aggregate_execute):
        command.add_argument("--sdk-apple-validation-policy", type=Path,
                             help="Current caller-owned Apple policy JSON, never retained artifact authority")
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
    matrix_command.add_argument("--sdk-apple-validation-policy", type=Path)
    matrix_command.add_argument("--sdk-original-workflow-sha")
    for name in ("materialize-product-predecessors", "prepare-runtime-phase", "execute-runtime-phase"):
        predecessors_command = commands.add_parser(name)
        for argument in ("plan", "discovery-root", "destination"):
            predecessors_command.add_argument(f"--{argument}", type=Path, required=True)
        predecessors_command.add_argument("--state-root", type=Path)
        for argument in (*_IDENTITY_KEYS, "expected-build-key"):
            predecessors_command.add_argument(f"--{argument}", required=True)
        predecessors_command.add_argument("--sdk-validation-tooling", type=Path,
                                          help="Current caller-owned tooling policy JSON")
        predecessors_command.add_argument("--sdk-apple-validation-policy", type=Path)
        predecessors_command.add_argument("--sdk-original-workflow-sha")
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
    for name in ("discover", "advance-products", "resume-products", "collect-runtime-workers",
                 "runtime-worker-matrix", "execute-runtime-supervisor", "execute-sdk-metadata",
                 "execute-runtime-aggregate", "materialize-product-predecessors",
                 "prepare-runtime-phase", "execute-runtime-phase"):
        add_metadata_admission_arguments(commands.choices[name])
    return result


@verification_scoped
def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        with metadata_admission_options(arguments) as admissions:
            tooling = None
            if getattr(arguments, "sdk_validation_tooling", None) is not None:
                tooling = _canonical_control(arguments.sdk_validation_tooling, "Caller SDK tooling policy")
            apple_options = {}
            if getattr(arguments, "sdk_apple_validation_policy", None) is not None:
                apple_options["sdk_apple_validation_policy"] = _canonical_control(
                    arguments.sdk_apple_validation_policy, "Caller Apple validation policy")
            apple_options.update(admissions)
            if arguments.command == "stage-release-catalog":
                stage_release_catalog(arguments.source_root, arguments.destination,
                    repository=arguments.repository, source=arguments.source,
                    keyring=arguments.keyring, keys_directory=arguments.keys_directory)
            elif arguments.command == "discover":
                discover(arguments.plan, arguments.destination, arguments.github_output,
                         native_evidence_roots=tuple(arguments.native_runtime_evidence),
                         aggregate_evidence_roots=tuple(arguments.runtime_aggregate_release_evidence),
                         adapter_evidence_roots=tuple(arguments.adapter_runtime_evidence),
                         sdk_evidence_roots=tuple(arguments.sdk_validation_evidence), sdk_validation_tooling=tooling,
                         **apple_options,
                         **({"sdk_maven_evidence_roots": tuple(arguments.sdk_maven_evidence)}
                            if arguments.sdk_maven_evidence else {}),
                         **({"sdk_metadata_evidence_roots": tuple(arguments.sdk_metadata_evidence)}
                            if arguments.sdk_metadata_evidence else {}),
                         **({"sdk_apple_evidence_roots": tuple(arguments.sdk_apple_validation_evidence)}
                            if arguments.sdk_apple_validation_evidence else {}),
                         **({"tooling_java_executable": arguments.tooling_java_executable,
                             "tooling_workflow_sha": arguments.tooling_workflow_sha}
                            if arguments.tooling_java_executable is not None or arguments.tooling_workflow_sha is not None else {}))
                if arguments.handoff is not None:
                    _publish_discovery_handoff(arguments.destination, arguments.handoff)
            elif arguments.command == "advance-contract":
                advance_contract(
                    arguments.plan,
                    arguments.discovery_root,
                    arguments.state_root,
                    arguments.phase_shard,
                    arguments.destination,
                    arguments.github_output,
                    sdk_validation_tooling=tooling,
                    **apple_options,
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
                    aggregate_evidence_roots=tuple(arguments.runtime_aggregate_release_evidence),
                    adapter_evidence_roots=tuple(arguments.adapter_runtime_evidence),
                    sdk_evidence_roots=tuple(arguments.sdk_validation_evidence), sdk_validation_tooling=tooling,
                    **({"sdk_original_workflow_sha": arguments.sdk_original_workflow_sha}
                       if arguments.sdk_original_workflow_sha is not None else {}),
                    **apple_options,
                    **({"sdk_maven_evidence_roots": tuple(arguments.sdk_maven_evidence)}
                       if arguments.sdk_maven_evidence else {}),
                    **({"sdk_metadata_evidence_roots": tuple(arguments.sdk_metadata_evidence)}
                       if arguments.sdk_metadata_evidence else {}),
                    **({"sdk_apple_evidence_roots": tuple(arguments.sdk_apple_validation_evidence)}
                       if arguments.sdk_apple_validation_evidence else {}),
                    failed_instances=tuple(PhaseInstanceId(*value) for value in arguments.failed_phase),
                    **({"runtime_workers_only": True} if arguments.runtime_workers_only else {}),
                )
            elif arguments.command == "collect-runtime-workers":
                collect_runtime_workers(
                    arguments.plan, arguments.discovery_root, arguments.state_root, arguments.destination,
                    trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""),
                    sdk_validation_tooling=tooling, **apple_options)
            elif arguments.command == "runtime-worker-matrix":
                github_output(arguments.github_output, {"runtime_matrix": '{"include":[]}', "runtime_workers_required": False})
                matrix = runtime_worker_matrix(
                    arguments.plan, arguments.discovery_root, arguments.state_root,
                    sdk_validation_tooling=tooling,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
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
                    expected_build_key=arguments.expected_build_key, sdk_validation_tooling=tooling,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
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
                    trusted_workflow_sha=arguments.trusted_workflow_sha, token=os.environ.get("GITHUB_TOKEN", ""),
                    trusted_contract_workflow_path=arguments.trusted_contract_workflow_path,
                    trusted_contract_continuation_job=arguments.trusted_contract_continuation_job)
            elif arguments.command == "resume-products":
                resume_products(
                    arguments.plan, arguments.discovery_root, arguments.state_root,
                    arguments.contract_handoff, arguments.destination, arguments.github_output,
                    sdk_validation_tooling=tooling,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
                if arguments.runtime_matrix:
                    from runtime_workflow import matrix
                    matrix(arguments.plan, arguments.destination, arguments.destination, arguments.github_output,
                        sdk_validation_tooling=tooling,
                        sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
                if arguments.handoff is not None:
                    _publish_runtime_original_reference_handoff(arguments.plan.parent.parent,
                        arguments.destination, arguments.handoff)
            elif arguments.command == "execute-sdk-metadata":
                execute_sdk_metadata(
                    arguments.plan, arguments.discovery_root, arguments.state_root, arguments.destination,
                    component=arguments.component, expected_build_key=arguments.expected_build_key,
                    compatibility_request=arguments.compatibility_request, runtime_stages=arguments.runtime_stages,
                    staged_sdks=arguments.staged_sdks, sdk_validation_tooling=tooling,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
            elif arguments.command == "execute-runtime-aggregate":
                execute_runtime_aggregate(
                    arguments.plan, arguments.discovery_root, arguments.state_root,
                    arguments.destination, expected_build_key=arguments.expected_build_key,
                    variant_trust_root=arguments.variant_trust_root, sdk_validation_tooling=tooling,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha, **apple_options)
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
                    sdk_validation_tooling=tooling, **apple_options, **additional,
                    sdk_original_workflow_sha=arguments.sdk_original_workflow_sha)
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
