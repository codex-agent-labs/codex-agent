#!/usr/bin/env python3
"""Resolve authenticated product reuse before any target job is created."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from typing import Any, Mapping

from impact import validate_legacy_lane_projection, validate_remote_build_authorization
from receipt import safe_extract
from reuse import api_json, download_artifact, github_output, paginated_items, run_matches_pr
from products.aggregate import validate_product_index
from products.inventory import (
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    require_array,
    require_exact_keys,
    require_integer,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    tree_entries,
    verified_zip_contents,
    write_canonical_json,
)
from products.registry import (
    PHASE_INSTANCE_IDS,
    PhaseInstanceId,
    required_contract_components,
    required_toolchain_profile,
)
from products.restore import object_relative_path, restore_object, verify_object, write_carrier
from products.reuse import _dependency_closure, plan_reuse_wave
from products.selection import classify_paths
from products.signatures import load_keyring, public_key_for_metadata


_PLAN_KEYS = {
    "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
    "validationCommit", "validationTree", "mergeReady", "remoteBuildAuthorized",
    "remoteBuildAuthorizationReason", "androidEvidenceRequired", "fullRequested", "full",
    "unknownPaths", "changedPaths", "lanes",
}
_IDENTITY_KEYS = ("product", "component", "phase", "target")
_AUTHORITY_KEYS = {
    *_IDENTITY_KEYS, "toolchainProfileDigest", "flagsDigest", "outputSchemaVersion",
}
_AUTHORITY_PATH = "gradle/release/product-phase-authorities.json"
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
_CATALOG_LIMIT = 2 * 1024 * 1024 * 1024
_CATALOG_ZIP_LIMITS = {
    "max_archive_bytes": _CATALOG_LIMIT,
    "max_central_directory_bytes": 32 * 1024 * 1024,
    "max_members": 8192,
    "max_entry_bytes": 512 * 1024 * 1024,
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


def _same_pr_run(
    artifact: Mapping[str, Any], api: str, repository: str, pull_request: int, token: str,
) -> dict[str, Any]:
    transport = artifact.get("workflow_run")
    if not isinstance(transport, dict):
        raise ValueError("Same-PR product catalog lacks workflow-run transport provenance")
    run_id = require_integer(transport.get("id"), "product catalog workflow run ID", 1)
    head_sha = require_string(transport.get("head_sha"), "product catalog workflow head SHA")
    if _OID.fullmatch(head_sha) is None:
        raise ValueError("Product catalog workflow head SHA is malformed")
    run = api_json(f"{api}/repos/{repository}/actions/runs/{run_id}", token)
    if (
        require_integer(run.get("id"), "product catalog workflow run ID", 1) != run_id
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "pull_request"
        or run.get("path") != ".github/workflows/ci.yml"
        or run.get("head_sha") != head_sha
        or not run_matches_pr(run, pull_request)
    ):
        raise ValueError("Same-PR product catalog did not come from an allowed successful CI run")
    return run


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
    if _AUTHORITY_PATH not in paths:
        return None, "phase-authority-unavailable"
    value = require_exact_keys(
        load_canonical_json_bytes(git_regular_blob_bytes(
            root, revision, _AUTHORITY_PATH, max_bytes=2 * 1024 * 1024,
        )),
        {"schemaVersion", "phases"},
        "product phase authorities",
    )
    if require_integer(value["schemaVersion"], "product phase authorities.schemaVersion", 1) != 1:
        raise ValueError("Unsupported product phase-authority schemaVersion")
    records: dict[PhaseInstanceId, dict[str, Any]] = {}
    ordered: list[PhaseInstanceId] = []
    for index, member in enumerate(require_array(value["phases"], "product phase authorities.phases")):
        label = f"product phase authorities.phases[{index}]"
        record = require_exact_keys(member, _AUTHORITY_KEYS, label)
        instance = _identity(record)
        if instance in records:
            raise ValueError(f"Duplicate product phase authority: {instance}")
        require_sha256(record["toolchainProfileDigest"], f"{label}.toolchainProfileDigest")
        require_sha256(record["flagsDigest"], f"{label}.flagsDigest")
        if require_integer(record["outputSchemaVersion"], f"{label}.outputSchemaVersion", 1) != 1:
            raise ValueError("Unsupported product output schema version")
        records[instance] = record
        ordered.append(instance)
    if ordered != sorted(ordered):
        raise ValueError("Product phase authorities must be sorted")
    if any(instance not in records for instance in closure):
        return None, "phase-authority-unavailable"
    for instance in closure:
        profile = required_toolchain_profile(instance)
        if profile is not None and f"{_PROFILE_ROOT}/{profile}.json" not in paths:
            return None, "toolchain-profile-unavailable"
    return [records[instance] for instance in closure], None


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
            raise ValueError("Same-PR product catalog lacks verified workflow-run provenance")
        run_id = require_integer(workflow_run.get("id"), "product catalog workflow run ID", 1)
        run_attempt = require_integer(
            workflow_run.get("run_attempt"), "product catalog workflow run attempt", 1,
        )
        head_sha = require_string(
            workflow_run.get("head_sha"), "product catalog workflow head SHA",
        )
        if (
            index["context"]["runId"] != run_id
            or index["producer"]["runId"] != run_id
            or index["context"]["runAttempt"] != run_attempt
            or index["producer"]["runAttempt"] != run_attempt
            or index["context"]["commit"] != head_sha
            or index["producer"]["commit"] != head_sha
        ):
            raise ValueError("Same-PR product catalog claims different workflow provenance")
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
    actual = _catalog_files(extracted)
    if not controls.issubset(actual) or not actual.issubset(controls | set(expected_objects.values())):
        raise ValueError("Product catalog file set is incomplete or unexpected")
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
        "objects": request_objects,
    }
    return Catalog(source, index, sha256_bytes(index_bytes), request, objects)


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
            workflow_run = _same_pr_run(
                artifact, api, repository, plan["pullRequest"], token,
            ) if source == "same-pr" else None
            result.append(_materialize_catalog(
                source, artifact, token, destination, repository, plan["pullRequest"], release_trust,
                workflow_run,
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
    return {
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
        "availableObjects": [],
        "catalogs": _catalog_request(catalogs),
    }


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
        bundle = stage.joinpath(*PurePosixPath(bundles[0]["relativePath"]).parts)
        _, retained, _ = verified_zip_contents(
            bundle, retained_paths=("contract-manifest.json",),
            max_archive_bytes=512 * 1024 * 1024, max_members=4096,
            max_entry_bytes=256 * 1024 * 1024, max_total_bytes=1024 * 1024 * 1024,
            max_compression_ratio=200,
        )
        manifest = load_canonical_json_bytes(retained["contract-manifest.json"])
    if catalog.source == "same-pr":
        public_key = destination / catalog.request["publicKey"]
        return {
            "publicKey": _relative(destination, public_key),
            "expectedTrustDomain": "development",
            "keyring": None,
            "keysDirectory": None,
        }
    if release_trust is None:
        raise ValueError("Release Contract reuse lacks tracked release trust")
    public_key = public_key_for_metadata(
        manifest["signing"], load_keyring(release_trust.keyring, release_trust.keys),
        release_trust.keys, allow_retired=True,
    )
    return {
        "publicKey": _relative(destination, public_key),
        "expectedTrustDomain": "release",
        "keyring": _relative(destination, release_trust.keyring),
        "keysDirectory": _relative(destination, release_trust.keys),
    }


def _reverify_complete(
    result: Mapping[str, Any], requested: tuple[PhaseInstanceId, ...],
    catalogs: list[Catalog], destination: Path, consumer: Mapping[str, Any],
) -> None:
    closure = _dependency_closure(requested)
    phases = result.get("phases")
    if not isinstance(phases, list) or len(phases) != len(closure):
        raise ValueError("Complete reuse result does not cover its exact dependency closure")
    actual = []
    sources: dict[PhaseInstanceId, Path] = {}
    for phase in phases:
        instance = _identity(phase)
        actual.append(instance)
        if phase.get("state") != "reused" or phase.get("source") not in {
            "stable", "promoted-main", "same-pr",
        }:
            raise ValueError("Complete reuse result contains an unmaterialized phase")
        catalog = _catalog_for_phase(catalogs, phase)
        object_path = catalog.objects.get(phase["buildKey"])
        if object_path is None:
            raise ValueError("Complete reuse result lacks a persisted object")
        verified = verify_object(
            object_path, build_key=phase["buildKey"], receipt_sha256=phase["receiptSha256"],
            object_sha256=phase["objectSha256"],
        )
        if _identity(verified["receipt"]) != instance:
            raise ValueError("Persisted product object identity disagrees with the reuse result")
        sources[instance] = object_path
    if tuple(actual) != closure:
        raise ValueError("Complete reuse result phase order or identity is invalid")
    write_carrier(destination / "carrier", result, closure, sources, consumer)


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
    github_output_path: Path,
) -> dict[str, Any]:
    write_canonical_json(destination / "request.json", request)
    write_canonical_json(destination / "result.json", result)
    github_output(github_output_path, {
        "full_reuse": result["fullReuse"],
        "target_jobs_required": result["targetJobsRequired"],
        "product_reuse_reason": result["reason"],
    })
    return dict(result)


def discover(
    plan_path: Path, destination: Path, github_output_path: Path, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    # A failing adapter must never make a missing output look like permission to skip work.
    github_output(github_output_path, {
        "full_reuse": False,
        "target_jobs_required": True,
        "product_reuse_reason": "not-evaluated",
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
    authorities, unavailable = _authorities(root, plan["validationCommit"], closure)
    if authorities is None:
        return _finish(destination, request, _result(
            requested, complete=False, reason=unavailable or "phase-authority-unavailable",
        ), github_output_path)
    versions = _versions(root, plan["validationCommit"])
    environment = os.environ if environ is None else environ
    trust = _release_trust(root, plan["validationCommit"], destination)
    catalogs = _discover_catalogs(plan, destination, trust, environment, versions)

    contract_evidence = None
    if any(required_contract_components(instance) for instance in closure) and catalogs:
        contract = PhaseInstanceId("contract", "contract", "metadata", "common")
        contract_request = _wave_request(
            plan, root, destination, (contract,), versions, authorities, catalogs, None,
        )
        write_canonical_json(destination / "contract-reuse-request.json", contract_request)
        contract_result = plan_reuse_wave(contract_request)
        write_canonical_json(destination / "contract-reuse-result.json", contract_result)
        if contract_result["fullReuse"] is True:
            contract_evidence = _contract_evidence(
                plan, destination, catalogs, contract_result, trust,
            )

    wave_request = _wave_request(
        plan, root, destination, requested, versions, authorities, catalogs, contract_evidence,
    )
    write_canonical_json(destination / "reuse-wave-request.json", wave_request)
    reuse = plan_reuse_wave(wave_request)
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
    discover_command.add_argument("--github-output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        discover(arguments.plan, arguments.destination, arguments.github_output)
    except (OSError, ValueError) as error:
        parser().error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
