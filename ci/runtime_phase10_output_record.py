"""Verify a protected Runtime output record against official transport and bytes.

This release-only record is not a reusable product payload or hosted evidence
until the protected workflow retains its exact signed bytes.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse
from ci.receipt import safe_extract
from ci.runtime_phase10_upload_locator import capture_observed_runtime_phase10_upload
from ci.runtime_phase11_bytes import _landed_tree, forward_verified_runtime_phase10_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    publish_regular_tree, sha256_bytes, snapshot_regular_tree, verified_zip_contents,
    write_canonical_json,
)
from ci.products.signatures import (
    load_keyring, require_active_release_key, verify_manifest_signature,
)
from ci.products.signing_isolation import require_no_signing_secret


_PINS = {
    "expected_protected_inventory_sha256", "expected_sidecar_inventory_sha256",
    "expected_metadata_receipt_sha256", "expected_build_key",
    "expected_runtime_version", "expected_manifest_sha256",
    "expected_source_commit", "expected_source_tree", "expected_validation_tree",
    "expected_workflow_sha", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256",
}


def admit_original_runtime_phase10_output_record(
    plan_path: Path, validation_repository: Path, repository_root: Path,
    protected_output: Path, maven_sidecars: Path, pgp_public_key: Path,
    destination: Path, *,
    expected_producer: Mapping, trusted_record_workflow_path: str,
    trusted_record_workflow_sha: str, trusted_record_job_name: str,
    record_artifact_name: str, record_artifact_id: int,
    record_artifact_sha256: str, expected_record_sha256: str,
    expected_signature_sha256: str, trusted_source_commit: str,
    trusted_aggregate_workflow_sha: str, expected_pgp_key_sha256: str,
    token: str, environ=None,
) -> dict:
    """Admit a later-run original only from caller-pinned official record bytes.

    The original producer, route and artifact pins must come from protected
    caller authority, never the downloaded record or current run environment.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime original record destination already exists")
    target = destination.resolve(strict=False)
    for source in (plan_path, validation_repository, repository_root):
        original = Path(source).resolve(strict=True)
        if target == original or target in original.parents:
            raise ValueError("Runtime original record destination overlaps an input")
    for source in (protected_output, maven_sidecars, pgp_public_key):
        original = Path(source).resolve(strict=True)
        if target == original or target in original.parents or original in target.parents:
            raise ValueError("Runtime original record destination overlaps an input")
    producer = product_reuse.validate_producer(dict(expected_producer))
    if producer["event"] not in {"pull_request", "merge_group"} or \
            type(record_artifact_name) is not str or not record_artifact_name or \
            type(trusted_record_job_name) is not str or not trusted_record_job_name or \
            type(token) is not str or not token:
        raise ValueError("Runtime original record requires pinned PR/merge-group transport")
    require_integer(record_artifact_id, "Runtime original record artifact ID", 1)
    for label, value in (("artifact", record_artifact_sha256),
                         ("record", expected_record_sha256),
                         ("signature", expected_signature_sha256)):
        require_sha256(value, f"Runtime original {label} digest")
    plan_bytes = read_regular_file_bytes(
        Path(plan_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    with tempfile.TemporaryDirectory(prefix="rt-original-record-") as temporary:
        root = Path(temporary).resolve()
        original_plan = root / "impact-plan.json"
        original_plan.write_bytes(plan_bytes)
        plan = product_reuse._validate_plan(original_plan, Path(validation_repository))
        if plan["remoteBuildAuthorized"] is not True or any(
            plan[field] != producer[other] for field, other in (
                ("repository", "repository"), ("validationCommit", "commit"),
                ("validationTree", "tree"), ("event", "event"),
                ("pullRequest", "pullRequest"),
            )
        ):
            raise ValueError("Runtime original record producer differs from validated plan")
        observed = product_reuse._observe_ci_producer_jobs(
            {"record": producer}, jobs_by_phase={"record": trusted_record_job_name},
            trusted_workflows_by_phase={"record": {
                "path": trusted_record_workflow_path,
                "sha": trusted_record_workflow_sha,
            }}, token=token,
        )[0]
        archive = root / "official-record.zip"
        artifact, _ = product_reuse._download_contract_ci_upload(
            record_artifact_id, record_artifact_sha256, record_artifact_name,
            producer, observed["run"], token, destination=archive,
        )
        product_reuse._require_artifact_job_window(observed, trusted_record_job_name, artifact)
        inventory, _, _ = verified_zip_contents(
            archive, retained_paths=(), **product_reuse._CATALOG_ZIP_LIMITS,
        )
        if {row["relativePath"] for row in inventory} != {"record.json", "record.sig"}:
            raise ValueError("Runtime original record upload has unexpected files")
        extracted = root / "record"
        safe_extract(archive, extracted)
        if regular_file_inventory(extracted) != inventory:
            raise ValueError("Runtime original record extraction differs from official upload")
        record_path, signature_path = extracted / "record.json", extracted / "record.sig"
        record_bytes = read_regular_file_bytes(record_path, max_bytes=16 * 1024 * 1024)
        signature_bytes = read_regular_file_bytes(signature_path, max_bytes=64 * 1024)
        if sha256_bytes(record_bytes) != expected_record_sha256 or \
                sha256_bytes(signature_bytes) != expected_signature_sha256:
            raise ValueError("Runtime original signed record differs from independent pins")
        # The existing locator reads run identity from its environment. Supply
        # the independently pinned *original* identity, never the consumer run.
        original_environment = {**environment, "GITHUB_RUN_ID": str(producer["runId"]),
                                "GITHUB_RUN_ATTEMPT": str(producer["runAttempt"])}
        record = verify_signed_runtime_phase10_output_record(
            record_path, signature_path, repository_root, protected_output,
            maven_sidecars, pgp_public_key, original_plan,
            validation_repository=validation_repository,
            trusted_source_commit=trusted_source_commit,
            trusted_workflow_sha=trusted_aggregate_workflow_sha,
            expected_pgp_key_sha256=expected_pgp_key_sha256,
            token=token, environ=original_environment,
        )
        if (read_regular_file_bytes(Path(plan_path), max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != plan_bytes
                or read_regular_file_bytes(record_path) != record_bytes
                or read_regular_file_bytes(signature_path) != signature_bytes
                or regular_file_inventory(extracted) != inventory):
            raise ValueError("Runtime original record inputs changed during admission")
        retained = root / "retained"
        snapshot_regular_tree(extracted, retained / "signed-record")
        transport = {"schemaVersion": 1, "artifact": artifact,
                     "producer": producer, "observed": observed,
                     "recordSha256": expected_record_sha256,
                     "signatureSha256": expected_signature_sha256}
        write_canonical_json(retained / "transport.json", transport)
        retained_files = regular_file_inventory(retained)
        if (regular_file_inventory(retained / "signed-record") != inventory
                or regular_file_inventory(extracted) != inventory
                or read_regular_file_bytes(record_path) != record_bytes
                or read_regular_file_bytes(signature_path) != signature_bytes):
            raise ValueError("Runtime original signed record changed before retention")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(retained, destination, expected_inventory=retained_files)
        if (regular_file_inventory(destination) != retained_files
                or regular_file_inventory(destination / "signed-record") != inventory):
            raise ValueError("Runtime retained signed record differs from verified bytes")
        return {"record": record, "recordSha256": expected_record_sha256,
                "signatureSha256": expected_signature_sha256,
                "recordPath": destination / "signed-record/record.json",
                "signaturePath": destination / "signed-record/record.sig",
                "transportPath": destination / "transport.json",
                "retainedFiles": retained_files,
                "officialRecordUpload": transport}


def prepare_runtime_phase10_output_record(
    plan_path: Path, repository_root: Path, protected_output: Path,
    maven_sidecars: Path, pgp_public_key: Path, destination: Path, *,
    phase11_pins: Mapping, validation_repository: Path, trusted_source_commit: str,
    trusted_workflow_sha: str, expected_pgp_key_sha256: str,
    token: str, environ=None,
) -> dict:
    """Prepare unsigned external evidence; the protected signer runs separately."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    repository_root = Path(repository_root)
    pins = require_exact_keys(dict(phase11_pins), _PINS, "Runtime Phase-10 output pins")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Runtime Phase-10 trusted source must be a full Git object ID")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_source_tree"] != product_reuse._git_value(
                repository_root, "rev-parse", f"{trusted_source_commit}^{{tree}}",
            ) or pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Runtime PGP key digest",
            ):
        raise ValueError("Runtime Phase-10 preparation differs from independent pins")
    if _landed_tree(Path(validation_repository)) != pins["expected_validation_tree"]:
        raise ValueError("Runtime Phase-10 validation checkout differs from independent tree")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime Phase-10 prepared record destination already exists")
    for source in (protected_output, maven_sidecars, pgp_public_key):
        source_root = Path(source).resolve(strict=True)
        target_root = destination.resolve(strict=False)
        if target_root == source_root or target_root in source_root.parents or \
                source_root in target_root.parents:
            raise ValueError("Runtime Phase-10 prepared record overlaps finalized input")
    protected_files = regular_file_inventory(protected_output, allow_empty=True)
    sidecar_files = regular_file_inventory(maven_sidecars)
    if pins["expected_protected_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(protected_files),
    ) or pins["expected_sidecar_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(sidecar_files),
    ):
        raise ValueError("Runtime Phase-10 prepared inventory differs from independent pins")
    with tempfile.TemporaryDirectory(prefix="rt-phase10-prepare-") as temporary:
        root = Path(temporary).resolve()
        trust = product_reuse._release_trust(repository_root, trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Runtime release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, _ = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Runtime Phase-10 preparation differs from trusted Git keys")
        pgp_bytes = read_regular_file_bytes(
            Path(pgp_public_key), max_bytes=1024 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(pgp_bytes) != pins["expected_pgp_key_sha256"]:
            raise ValueError("Runtime Phase-10 PGP key differs from independent pin")
        captured_sidecars = root / "maven-sidecars"
        snapshot_regular_tree(maven_sidecars, captured_sidecars)
        if regular_file_inventory(captured_sidecars) != sidecar_files:
            raise ValueError("Runtime Phase-10 sidecars changed during capture")
        capture = root / "official-upload"
        observation = capture_observed_runtime_phase10_upload(
            plan_path, validation_repository, capture,
            trusted_workflow_sha=trusted_workflow_sha,
            expected_build_key=pins["expected_build_key"],
            expected_metadata_receipt_sha256=pins["expected_metadata_receipt_sha256"],
            token=token, environ=environment,
        )
        if pins["expected_validation_tree"] != observation["captureProducer"]["tree"] or \
                regular_file_inventory(capture / "original", allow_empty=True) != protected_files:
            raise ValueError("Runtime Phase-10 preparation differs from official upload")
        pinned_pgp = root / "pgp-public-key.asc"
        pinned_pgp.write_bytes(pgp_bytes)
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        forward_verified_runtime_phase10_bytes(
            capture / "original", captured_sidecars, root / "verified",
            landed_repository=validation_repository, keyring=trust.keyring,
            keys_directory=trust.keys, pgp_public_key=pinned_pgp, **pins,
        )
        record = {
            "schemaVersion": 1, "product": "runtime", "signing": signing,
            "trustedSourceCommit": trusted_source_commit,
            "officialUpload": observation, "phase11Pins": pins,
            "protectedFiles": protected_files, "sidecarFiles": sidecar_files,
        }
        prepared = root / "record"
        prepared.mkdir()
        write_canonical_json(prepared / "record.json", record)
        expected_files = regular_file_inventory(prepared)
        if regular_file_inventory(protected_output, allow_empty=True) != protected_files or \
                regular_file_inventory(maven_sidecars) != sidecar_files or \
                read_regular_file_bytes(Path(pgp_public_key), max_bytes=1024 * 1024,
                                        reject_symlink_parents=True) != pgp_bytes or \
                canonical_json_bytes(dict(phase11_pins)) != canonical_json_bytes(pins):
            raise ValueError("Runtime Phase-10 preparation inputs changed")
        if _landed_tree(Path(validation_repository)) != pins["expected_validation_tree"]:
            raise ValueError("Runtime Phase-10 validation checkout changed during preparation")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return {"recordSha256": sha256_bytes(canonical_json_bytes(record)), "record": record}


def verify_signed_runtime_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    protected_output: Path, maven_sidecars: Path, pgp_public_key: Path,
    plan_path: Path, *, validation_repository: Path, trusted_source_commit: str,
    trusted_workflow_sha: str,
    expected_pgp_key_sha256: str, token: str, environ=None,
) -> dict:
    """Authenticate an exact Phase-10 Runtime set, without signing or admission."""
    require_no_signing_secret(os.environ if environ is None else environ)
    require_no_signing_secret(os.environ)
    repository_root, protected_output, maven_sidecars = map(
        Path, (repository_root, protected_output, maven_sidecars),
    )
    record_bytes = read_regular_file_bytes(
        Path(record_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature_path), max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
        "schemaVersion", "product", "signing", "trustedSourceCommit",
        "officialUpload", "phase11Pins", "protectedFiles", "sidecarFiles",
    }, "Runtime Phase-10 output record")
    if require_integer(record["schemaVersion"], "Runtime output schemaVersion", 1) != 1 or \
            record["product"] != "runtime" or \
            record["trustedSourceCommit"] != trusted_source_commit:
        raise ValueError("Runtime Phase-10 output record source is not independently pinned")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Runtime Phase-10 trusted source must be a full Git object ID")
    pins = require_exact_keys(record["phase11Pins"], _PINS, "Runtime Phase-10 output pins")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Runtime PGP key digest",
            ):
        raise ValueError("Runtime Phase-10 output pins differ from independent authority")
    if pins["expected_source_tree"] != product_reuse._git_value(
        repository_root, "rev-parse", f"{trusted_source_commit}^{{tree}}",
    ):
        raise ValueError("Runtime Phase-10 source tree differs from trusted Git")
    if _landed_tree(Path(validation_repository)) != pins["expected_validation_tree"]:
        raise ValueError("Runtime Phase-10 validation checkout differs from independent tree")
    if type(record["protectedFiles"]) is not list or not record["protectedFiles"] or \
            type(record["sidecarFiles"]) is not list or not record["sidecarFiles"]:
        raise ValueError("Runtime Phase-10 output inventories are empty")
    if pins["expected_protected_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(record["protectedFiles"]),
    ) or pins["expected_sidecar_inventory_sha256"] != sha256_bytes(
        canonical_json_bytes(record["sidecarFiles"]),
    ):
        raise ValueError("Runtime Phase-10 output inventory digest differs from record")

    with tempfile.TemporaryDirectory(prefix="rt-phase10-record-") as temporary:
        root = Path(temporary).resolve()
        trust = product_reuse._release_trust(repository_root, trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Runtime release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if record["signing"] != signing:
            raise ValueError("Runtime Phase-10 output record signer differs from source policy")
        pinned_record = root / "record.json"
        pinned_signature = root / "record.sig"
        pinned_record.write_bytes(record_bytes)
        pinned_signature.write_bytes(signature_bytes)
        verify_manifest_signature(pinned_record, pinned_signature, public, signing)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Runtime Phase-10 verifier policy differs from trusted Git")
        pgp_bytes = read_regular_file_bytes(
            Path(pgp_public_key), max_bytes=1024 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(pgp_bytes) != pins["expected_pgp_key_sha256"]:
            raise ValueError("Runtime Phase-10 PGP key differs from independent pin")
        pinned_pgp = root / "pgp-public-key.asc"
        pinned_pgp.write_bytes(pgp_bytes)
        pinned_sidecars = root / "maven-sidecars"
        snapshot_regular_tree(maven_sidecars, pinned_sidecars)
        if regular_file_inventory(pinned_sidecars) != record["sidecarFiles"]:
            raise ValueError("Runtime Phase-10 sidecars changed during capture")

        # Official capture retains its own original archive and transport
        # provenance; the signed record binds that observation to these bytes.
        capture = root / "official-upload"
        observation = capture_observed_runtime_phase10_upload(
            plan_path, validation_repository, capture,
            trusted_workflow_sha=trusted_workflow_sha,
            expected_build_key=pins["expected_build_key"],
            expected_metadata_receipt_sha256=pins["expected_metadata_receipt_sha256"],
            token=token, environ=environ,
        )
        if record["officialUpload"] != observation or \
                pins["expected_validation_tree"] != observation["captureProducer"]["tree"]:
            raise ValueError("Runtime Phase-10 output record differs from official upload")
        if regular_file_inventory(capture / "original", allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(protected_output, allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(maven_sidecars) != record["sidecarFiles"]:
            raise ValueError("Runtime Phase-10 output record differs from selected bytes")
        require_no_signing_secret(os.environ if environ is None else environ)
        require_no_signing_secret(os.environ)
        forward_verified_runtime_phase10_bytes(
            capture / "original", pinned_sidecars, root / "verified",
            landed_repository=validation_repository, keyring=trust.keyring,
            keys_directory=trust.keys, pgp_public_key=pinned_pgp, **pins,
        )
        if regular_file_inventory(protected_output, allow_empty=True) != record["protectedFiles"] or \
                regular_file_inventory(maven_sidecars) != record["sidecarFiles"] or \
                read_regular_file_bytes(Path(pgp_public_key), max_bytes=1024 * 1024,
                                        reject_symlink_parents=True) != pgp_bytes or \
                read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != record_bytes or \
                read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                        reject_symlink_parents=True) != signature_bytes:
            raise ValueError("Runtime Phase-10 output or signed record changed during verification")
        if _landed_tree(Path(validation_repository)) != pins["expected_validation_tree"]:
            raise ValueError("Runtime Phase-10 validation checkout changed during verification")
        require_no_signing_secret(os.environ if environ is None else environ)
        require_no_signing_secret(os.environ)
    return record


def publish_verified_runtime_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    validation_repository: Path, protected_output: Path, maven_sidecars: Path,
    pgp_public_key: Path, plan_path: Path, destination: Path, *,
    expected_record_sha256: str, expected_signature_sha256: str,
    trusted_source_commit: str, trusted_workflow_sha: str,
    expected_pgp_key_sha256: str, token: str, environ=None,
) -> dict:
    """Verify against official/deep inputs and publish the exact signed pair."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    expected_record_sha256 = require_sha256(expected_record_sha256, "Runtime record pin")
    expected_signature_sha256 = require_sha256(expected_signature_sha256, "Runtime signature pin")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Runtime signed-record destination already exists")
    target = destination.resolve(strict=False)
    for source in (record_path, signature_path, protected_output, maven_sidecars,
                   pgp_public_key):
        root = Path(source).resolve(strict=True)
        if target == root or target in root.parents or root in target.parents:
            raise ValueError("Runtime signed-record destination overlaps an input")
    record_bytes = read_regular_file_bytes(
        Path(record_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature_path), max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    if sha256_bytes(record_bytes) != expected_record_sha256 or \
            sha256_bytes(signature_bytes) != expected_signature_sha256:
        raise ValueError("Runtime signed record differs from independent Phase-10 pins")
    with tempfile.TemporaryDirectory(prefix="rt-phase10-publish-") as temporary:
        prepared = Path(temporary).resolve() / "signed-record"
        prepared.mkdir()
        (prepared / "record.json").write_bytes(record_bytes)
        (prepared / "record.sig").write_bytes(signature_bytes)
        inventory = regular_file_inventory(prepared)
        record = verify_signed_runtime_phase10_output_record(
            prepared / "record.json", prepared / "record.sig", repository_root,
            protected_output, maven_sidecars, pgp_public_key, plan_path,
            validation_repository=validation_repository,
            trusted_source_commit=trusted_source_commit,
            trusted_workflow_sha=trusted_workflow_sha,
            expected_pgp_key_sha256=expected_pgp_key_sha256,
            token=token, environ=environment,
        )
        if (read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != record_bytes
                or read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                           reject_symlink_parents=True) != signature_bytes
                or regular_file_inventory(protected_output, allow_empty=True) !=
                record["protectedFiles"]
                or regular_file_inventory(maven_sidecars) != record["sidecarFiles"]
                or regular_file_inventory(prepared) != inventory):
            raise ValueError("Runtime signed-record input changed before publication")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, expected_inventory=inventory)
    if (regular_file_inventory(destination) != inventory
            or regular_file_inventory(protected_output, allow_empty=True) !=
            record["protectedFiles"]
            or regular_file_inventory(maven_sidecars) != record["sidecarFiles"]
            or read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != record_bytes
            or read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                       reject_symlink_parents=True) != signature_bytes):
        raise ValueError("Published Runtime signed record differs from verified bytes")
    return {"recordSha256": expected_record_sha256,
            "signatureSha256": expected_signature_sha256,
            "publishedFiles": inventory}


def main(argv=None) -> int:
    require_no_signing_secret(os.environ)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    admitted = commands.add_parser("admit-original", allow_abbrev=False)
    for name in ("plan", "validation-repository", "repository-root", "protected-output",
                 "maven-sidecars", "pgp-public-key", "destination", "original-producer"):
        admitted.add_argument(f"--{name}", type=Path, required=True)
    for name in ("expected-original-producer-sha256", "trusted-record-workflow-path",
                 "trusted-record-workflow-sha", "trusted-record-job-name",
                 "record-artifact-name", "record-artifact-id", "record-artifact-sha256",
                 "expected-record-sha256", "expected-signature-sha256",
                 "trusted-source-commit", "trusted-aggregate-workflow-sha",
                 "expected-pgp-key-sha256"):
        admitted.add_argument(f"--{name}", required=True)
    for command in ("prepare", "verify-publish"):
        selected = commands.add_parser(command, allow_abbrev=False)
        for name in ("plan", "repository-root", "validation-repository", "protected-output",
                     "maven-sidecars", "pgp-public-key", "destination"):
            selected.add_argument(f"--{name}", type=Path, required=True)
        for name in ("trusted-source-commit", "trusted-workflow-sha",
                     "expected-pgp-key-sha256"):
            selected.add_argument(f"--{name}", required=True)
        if command == "prepare":
            selected.add_argument("--phase11-pins", type=Path, required=True)
            selected.add_argument("--expected-phase11-pins-sha256", required=True)
        else:
            selected.add_argument("--record", type=Path, required=True)
            selected.add_argument("--signature", type=Path, required=True)
            selected.add_argument("--expected-record-sha256", required=True)
            selected.add_argument("--expected-signature-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "admit-original":
        producer_bytes = read_regular_file_bytes(
            args.original_producer, max_bytes=64 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(producer_bytes) != require_sha256(
            args.expected_original_producer_sha256, "independent Runtime original producer digest",
        ):
            raise ValueError("Runtime original producer differs from independent digest")
        result = admit_original_runtime_phase10_output_record(
            args.plan, args.validation_repository, args.repository_root,
            args.protected_output, args.maven_sidecars, args.pgp_public_key,
            args.destination,
            expected_producer=load_canonical_json_bytes(producer_bytes),
            trusted_record_workflow_path=args.trusted_record_workflow_path,
            trusted_record_workflow_sha=args.trusted_record_workflow_sha,
            trusted_record_job_name=args.trusted_record_job_name,
            record_artifact_name=args.record_artifact_name,
            record_artifact_id=int(args.record_artifact_id),
            record_artifact_sha256=args.record_artifact_sha256,
            expected_record_sha256=args.expected_record_sha256,
            expected_signature_sha256=args.expected_signature_sha256,
            trusted_source_commit=args.trusted_source_commit,
            trusted_aggregate_workflow_sha=args.trusted_aggregate_workflow_sha,
            expected_pgp_key_sha256=args.expected_pgp_key_sha256,
            token=os.environ["GITHUB_TOKEN"], environ=os.environ,
        )
        print(json.dumps({key: (str(value) if isinstance(value, Path) else value)
                          for key, value in result.items() if key != "record" and
                          key != "officialRecordUpload"}, sort_keys=True, separators=(",", ":")))
        return 0
    common = dict(
        trusted_source_commit=args.trusted_source_commit,
        trusted_workflow_sha=args.trusted_workflow_sha,
        expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        token=os.environ["GITHUB_TOKEN"], environ=os.environ,
    )
    if args.command == "prepare":
        pins_bytes = read_regular_file_bytes(
            args.phase11_pins, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )
        if sha256_bytes(pins_bytes) != require_sha256(
            args.expected_phase11_pins_sha256, "independent Runtime Phase-11 pins digest",
        ):
            raise ValueError("Runtime Phase-11 pins file differs from independent digest")
        result = prepare_runtime_phase10_output_record(
            args.plan, args.repository_root, args.protected_output,
            args.maven_sidecars, args.pgp_public_key, args.destination,
            phase11_pins=load_canonical_json_bytes(pins_bytes),
            validation_repository=args.validation_repository, **common,
        )
    else:
        result = publish_verified_runtime_phase10_output_record(
            args.record, args.signature, args.repository_root,
            args.validation_repository, args.protected_output, args.maven_sidecars,
            args.pgp_public_key, args.plan, args.destination,
            expected_record_sha256=args.expected_record_sha256,
            expected_signature_sha256=args.expected_signature_sha256, **common,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
