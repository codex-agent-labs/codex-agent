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
from products.contract_attestation import validate_contract_attestation
from products.inventory import (
    canonical_json_bytes,
    git_regular_blob_bytes,
    load_canonical_json_bytes,
    load_json_bytes,
    publish_regular_tree,
    read_regular_file_bytes,
    require_array,
    require_boolean,
    require_exact_keys,
    require_integer,
    require_relative_path,
    require_semver,
    require_sha256,
    require_string,
    sha256_bytes,
    tree_entries,
    verified_zip_contents,
    write_canonical_json,
)
from products.registry import (
    NATIVE_TARGETS,
    PHASE_INSTANCE_IDS,
    PhaseInstanceId,
    phase_instance_dependencies,
    required_toolchain_profile,
)
from products.plan import NOT_APPLICABLE_FLAGS_DIGEST, NOT_APPLICABLE_TOOLCHAIN_DIGEST
from products.runtime_flags import load_runtime_binary_flags_bytes
from products.restore import (
    PHASE_SHARD_KEYS,
    PHASE_SHARD_NAME,
    object_relative_path,
    restore_object,
    verify_carrier,
    verify_object,
    verify_phase_shard,
    write_carrier,
)
from products.receipt import validate_producer
from products.reuse import SOURCES, _dependency_closure, plan_reuse_wave
from products.selection import classify_paths
from products.signatures import load_keyring, public_key_for_metadata
from products.toolchain import load_toolchain_profile_bytes


_PLAN_KEYS = {
    "schemaVersion", "event", "repository", "pullRequest", "baseCommit", "headCommit",
    "validationCommit", "validationTree", "mergeReady", "remoteBuildAuthorized",
    "remoteBuildAuthorizationReason", "androidEvidenceRequired", "fullRequested", "full",
    "unknownPaths", "changedPaths", "lanes",
}
_IDENTITY_KEYS = ("product", "component", "phase", "target")
_REUSE_RESULT_KEYS = {"schemaVersion", "result", "fullReuse", "phases", "matrices"}
_REUSE_PHASE_KEYS = {
    *_IDENTITY_KEYS, "buildKey", "state", "source", "transportSource",
    "receiptSha256", "objectSha256", "misses",
}
_WAVE_REQUEST_KEYS = {
    "schemaVersion", "requestType", "repository", "pullRequest", "repositoryRoot",
    "repositoryRevision", "artifactRoot", "requested", "versions", "phaseAuthorities",
    "contractEvidence", "availableObjects", "catalogs",
}
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
    contract_attestation: Path | None = None
    contract_attestation_signature: Path | None = None


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
    expected_commit: str, expected_tree: str,
) -> dict[str, Any]:
    transport = artifact.get("workflow_run")
    if not isinstance(transport, dict):
        raise ValueError("Same-PR product catalog lacks workflow-run transport provenance")
    run_id = require_integer(transport.get("id"), "product catalog workflow run ID", 1)
    head_sha = require_string(transport.get("head_sha"), "product catalog workflow head SHA")
    if _OID.fullmatch(head_sha) is None:
        raise ValueError("Product catalog workflow head SHA is malformed")
    run = api_json(f"{api}/repos/{repository}/actions/runs/{run_id}", token)
    head_commit = run.get("head_commit")
    tree = head_commit.get("tree_id") if isinstance(head_commit, dict) else None
    if (
        require_integer(run.get("id"), "product catalog workflow run ID", 1) != run_id
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or run.get("event") != "pull_request"
        or run.get("path") != ".github/workflows/ci.yml"
        or run.get("head_sha") != head_sha
        or head_sha != expected_commit
        or tree != expected_tree
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
        workflow_path = require_string(
            workflow_run.get("path"), "product catalog workflow path",
        )
        head_commit = workflow_run.get("head_commit")
        tree = require_string(
            head_commit.get("tree_id") if isinstance(head_commit, dict) else None,
            "product catalog workflow tree",
        )
        if (
            index["context"]["runId"] != run_id
            or index["producer"]["runId"] != run_id
            or index["context"]["runAttempt"] != run_attempt
            or index["producer"]["runAttempt"] != run_attempt
            or index["context"]["commit"] != head_sha
            or index["producer"]["commit"] != head_sha
            or index["context"]["tree"] != tree
            or index["producer"]["tree"] != tree
            or index["producer"]["workflowPath"] != workflow_path
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
    actual = _catalog_files(extracted)
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
            workflow_run = _same_pr_run(
                artifact, api, repository, plan["pullRequest"], token,
                plan["validationCommit"], plan["validationTree"],
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


def advance_contract(
    plan_path: Path, discovery_root: Path, state_root: Path | None,
    shard_roots: list[Path], destination: Path,
    github_output_path: Path, *, repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
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

    request = require_exact_keys(
        _canonical_control(
            discovery_root / "contract-reuse-request.json", "Contract reuse request",
        ),
        _WAVE_REQUEST_KEYS,
        "Contract reuse request",
    )
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

    rebased_request = dict(request)
    rebased_request["artifactRoot"] = str(root)
    rebased_request["catalogs"] = _rebase_catalog_paths(request["catalogs"], discovery_root, root)
    replay_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain(plans: dict[PhaseInstanceId, dict[str, Any]], instance: PhaseInstanceId,
               value: dict[str, Any]) -> None:
        if instance in plans:
            raise ValueError(f"Duplicate Contract phase plan: {instance}")
        plans[instance] = value

    replay = plan_reuse_wave(
        rebased_request,
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
    carrier_root = state_root / "reused-carrier"
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
        state_replay = plan_reuse_wave(
            state_request,
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
    advanced = plan_reuse_wave(
        advanced_request,
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
        if ready_plans:
            write_canonical_json(staged_destination / "producer.json", producer)
        publish_regular_tree(staged_destination, destination)
    github_output(github_output_path, {
        "contract_complete": advanced["fullReuse"],
        "next_phase_required": bool(ready_plans),
        "next_phase": _contract_ready_phase(ready_plans),
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


def discover(
    plan_path: Path, destination: Path, github_output_path: Path, *,
    repository_root: Path | None = None, environ: Mapping[str, str] | None = None,
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
        write_canonical_json(destination / "contract-reuse-request.json", contract_request)
        contract_ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}
        contract_result = plan_reuse_wave(
            contract_request,
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
    write_canonical_json(destination / "reuse-wave-request.json", wave_request)
    ready_plans: dict[PhaseInstanceId, dict[str, Any]] = {}

    def retain_ready_plan(instance: PhaseInstanceId, phase_plan: dict[str, Any]) -> None:
        if instance in ready_plans:
            raise ValueError(f"Duplicate ready phase plan: {instance}")
        ready_plans[instance] = phase_plan

    reuse = plan_reuse_wave(wave_request, build_plan_consumer=retain_ready_plan)
    _write_ready_plans(destination, ready_plans)
    if ready_plans:
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
    discover_command.add_argument("--github-output", type=Path, required=True)
    advance_command = commands.add_parser("advance-contract")
    advance_command.add_argument("--plan", type=Path, required=True)
    advance_command.add_argument("--discovery-root", type=Path, required=True)
    advance_command.add_argument("--state-root", type=Path)
    advance_command.add_argument("--phase-shard", type=Path, action="append", default=[])
    advance_command.add_argument("--destination", type=Path, required=True)
    advance_command.add_argument("--github-output", type=Path, required=True)
    materialize_command = commands.add_parser("materialize-contract")
    materialize_command.add_argument("--plan", type=Path, required=True)
    materialize_command.add_argument("--state-root", type=Path, required=True)
    materialize_command.add_argument("--phase", required=True)
    materialize_command.add_argument("--destination", type=Path, required=True)
    materialize_command.add_argument("--with-receipt", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "discover":
            discover(arguments.plan, arguments.destination, arguments.github_output)
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
            )
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
