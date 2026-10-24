"""Verify a protected Contract output record against official transport and bytes.

The release workflow must supply the trusted source/workflow and PGP pins
independently. This reader neither signs nor grants authority to a local ZIP.
"""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import json
from pathlib import Path
import os
import re
import sys
import tempfile

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ci import product_reuse
from ci.contract_phase10_upload_locator import observe_contract_phase10_upload
from ci.contract_phase11_bytes import forward_verified_contract_phase10_bytes
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, read_regular_file_bytes,
    regular_file_inventory, require_exact_keys, require_integer, require_sha256,
    publish_regular_tree, sha256_bytes, snapshot_regular_tree,
    write_canonical_json,
)
from ci.products.signing_isolation import require_no_signing_secret
from ci.products.signatures import (
    load_keyring, require_active_release_key, verify_manifest_signature,
)


_PINS = {
    "expected_inventory_sha256", "expected_contract_version",
    "expected_payload_sha256", "expected_metadata_build_key",
    "expected_source_commit", "expected_source_tree",
    "expected_validation_tree", "expected_workflow_sha",
    "expected_caller_sha256", "expected_keyring_sha256",
    "expected_keys_inventory_sha256", "expected_pgp_key_sha256",
}


def prepare_contract_phase10_output_record(
    plan_path: Path, repository_root: Path, validation_repository: Path,
    protected_output: Path,
    destination: Path, *, phase11_pins: Mapping, trusted_source_commit: str,
    trusted_workflow_sha: str, trusted_workflow_path: str,
    trusted_job_name: str, expected_pgp_key_sha256: str,
    artifact_id: int, artifact_sha256: str, token: str, environ=None,
    original_run_id=None, original_run_attempt=None,
) -> dict:
    """Create an unsigned record using reviewed source policy and the validation checkout."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    pins = require_exact_keys(dict(phase11_pins), _PINS, "Contract Phase-10 output pins")
    pins_bytes = canonical_json_bytes(pins)
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Contract Phase-10 trusted source must be a full Git object ID")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_source_tree"] != product_reuse._git_value(
                Path(repository_root), "rev-parse", f"{trusted_source_commit}^{{tree}}",
            ) or pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Contract PGP key digest",
            ):
        raise ValueError("Contract Phase-10 preparation differs from independent pins")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract Phase-10 prepared record destination already exists")
    output_root = Path(protected_output).resolve(strict=True)
    destination_root = destination.resolve(strict=False)
    if destination_root == output_root or destination_root in output_root.parents or \
            output_root in destination_root.parents:
        raise ValueError("Contract Phase-10 prepared record overlaps finalized output")
    output_files = regular_file_inventory(protected_output)
    if pins["expected_inventory_sha256"] != sha256_bytes(canonical_json_bytes(output_files)):
        raise ValueError("Contract Phase-10 prepared inventory differs from independent pin")
    with tempfile.TemporaryDirectory(prefix="ct-phase10-prepare-") as temporary:
        root = Path(temporary).resolve()
        captured_output = root / "output"
        snapshot_regular_tree(protected_output, captured_output)
        if regular_file_inventory(captured_output) != output_files:
            raise ValueError("Contract Phase-10 output changed during preparation capture")
        trust = product_reuse._release_trust(Path(repository_root), trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Contract release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, _ = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Contract Phase-10 preparation differs from trusted Git keys")
        observation = observe_contract_phase10_upload(
            plan_path, validation_repository, captured_output,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            token=token, environ=environment,
            original_run_id=original_run_id,
            original_run_attempt=original_run_attempt,
        )
        if pins["expected_validation_tree"] != observation["producer"]["tree"] or \
                observation["inventorySha256"] != pins["expected_inventory_sha256"]:
            raise ValueError("Contract Phase-10 preparation differs from official upload")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        forward_verified_contract_phase10_bytes(
            captured_output, root / "verified", landed_repository=validation_repository, **pins,
        )
        record = {
            "schemaVersion": 1, "product": "contract", "signing": signing,
            "trustedSourceCommit": trusted_source_commit,
            "officialUpload": observation, "phase11Pins": pins,
            "outputFiles": output_files,
        }
        prepared = root / "record"
        prepared.mkdir()
        write_canonical_json(prepared / "record.json", record)
        expected_files = regular_file_inventory(prepared)
        if regular_file_inventory(protected_output) != output_files or \
                canonical_json_bytes(dict(phase11_pins)) != pins_bytes:
            raise ValueError("Contract Phase-10 preparation inputs changed")
        require_no_signing_secret(environment)
        publish_regular_tree(prepared, destination, expected_inventory=expected_files)
    return {"recordSha256": sha256_bytes(canonical_json_bytes(record)), "record": record}


def verify_signed_contract_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    validation_repository: Path, protected_output: Path, plan_path: Path, *,
    trusted_source_commit: str,
    trusted_workflow_sha: str, trusted_workflow_path: str,
    trusted_job_name: str, expected_pgp_key_sha256: str,
    artifact_id: int, artifact_sha256: str, token: str, environ=None,
    original_run_id=None, original_run_attempt=None,
) -> dict:
    """Require an independently pinned signer, official upload, and exact files.

    ``repository_root`` owns reviewed Git/key policy; ``validation_repository``
    must have the original validated tree, which can differ from that source.
    The record and signature are separate release-only control bytes. The
    returned record is suitable as an S1048 Contract handoff only after the
    protected workflow also retains their exact bytes and digest.
    """
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    repository_root, protected_output = Path(repository_root), Path(protected_output)
    record_bytes = read_regular_file_bytes(
        Path(record_path), max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        Path(signature_path), max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    record = require_exact_keys(load_canonical_json_bytes(record_bytes), {
        "schemaVersion", "product", "signing", "trustedSourceCommit",
        "officialUpload", "phase11Pins", "outputFiles",
    }, "Contract Phase-10 output record")
    if require_integer(record["schemaVersion"], "Contract output schemaVersion", 1) != 1 or \
            record["product"] != "contract" or \
            record["trustedSourceCommit"] != trusted_source_commit:
        raise ValueError("Contract Phase-10 output record source is not independently pinned")
    if type(trusted_source_commit) is not str or re.fullmatch(
        r"[0-9a-f]{40}|[0-9a-f]{64}", trusted_source_commit,
    ) is None:
        raise ValueError("Contract Phase-10 trusted source must be a full Git object ID")
    pins = require_exact_keys(record["phase11Pins"], _PINS, "Contract Phase-10 output pins")
    if pins["expected_source_commit"] != trusted_source_commit or \
            pins["expected_workflow_sha"] != trusted_workflow_sha or \
            pins["expected_pgp_key_sha256"] != require_sha256(
                expected_pgp_key_sha256, "independent Contract PGP key digest",
            ):
        raise ValueError("Contract Phase-10 output pins differ from independent authority")
    if pins["expected_source_tree"] != product_reuse._git_value(
        repository_root, "rev-parse", f"{trusted_source_commit}^{{tree}}",
    ):
        raise ValueError("Contract Phase-10 source tree differs from trusted Git")
    if type(record["outputFiles"]) is not list or not record["outputFiles"]:
        raise ValueError("Contract Phase-10 output inventory is empty")
    inventory_digest = sha256_bytes(canonical_json_bytes(record["outputFiles"]))
    if pins["expected_inventory_sha256"] != inventory_digest:
        raise ValueError("Contract Phase-10 output inventory digest differs from record")

    # Git at the independently supplied source revision, not the transported
    # output, supplies the release verifier policy.
    with tempfile.TemporaryDirectory(prefix="ct-phase10-record-") as temporary:
        root = Path(temporary).resolve()
        pinned_record = root / "record.json"
        pinned_signature = root / "record.sig"
        pinned_record.write_bytes(record_bytes)
        pinned_signature.write_bytes(signature_bytes)
        captured_output = root / "output"
        snapshot_regular_tree(protected_output, captured_output)
        if regular_file_inventory(captured_output) != record["outputFiles"]:
            raise ValueError("Contract Phase-10 output changed during record capture")
        trust = product_reuse._release_trust(repository_root, trusted_source_commit,
                                             root / "source-policy")
        if trust is None:
            raise ValueError("No active source-pinned Contract release keyring")
        policy = load_keyring(trust.keyring, trust.keys)
        active, public = require_active_release_key(policy, trust.keys)
        signing = {name: policy[name] for name in ("algorithm", "namespace", "trustDomain")}
        signing.update(active)
        if record["signing"] != signing:
            raise ValueError("Contract Phase-10 output record signer differs from source policy")
        verify_manifest_signature(pinned_record, pinned_signature, public, signing)
        keyring_bytes = read_regular_file_bytes(
            trust.keyring, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )
        if pins["expected_keyring_sha256"] != sha256_bytes(keyring_bytes) or \
                pins["expected_keys_inventory_sha256"] != sha256_bytes(
                    canonical_json_bytes(regular_file_inventory(trust.keys)),
                ):
            raise ValueError("Contract Phase-10 output verifier policy differs from trusted Git")

        # The locator verifies the official run/job/upload, rather than
        # trusting transport facts copied into this record.
        observation = observe_contract_phase10_upload(
            plan_path, validation_repository, captured_output,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            token=token, environ=environment,
            original_run_id=original_run_id,
            original_run_attempt=original_run_attempt,
        )
        if record["officialUpload"] != observation or \
                pins["expected_validation_tree"] != observation["producer"]["tree"]:
            raise ValueError("Contract Phase-10 output record differs from official upload")
        if regular_file_inventory(captured_output) != record["outputFiles"] or \
                observation["inventorySha256"] != inventory_digest:
            raise ValueError("Contract Phase-10 output record differs from uploaded bytes")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
        forward_verified_contract_phase10_bytes(
            captured_output, root / "verified", landed_repository=validation_repository, **pins,
        )
        if (regular_file_inventory(protected_output) != record["outputFiles"]
                or regular_file_inventory(captured_output) != record["outputFiles"]
                or read_regular_file_bytes(Path(record_path), max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != record_bytes
                or read_regular_file_bytes(Path(signature_path), max_bytes=64 * 1024,
                                           reject_symlink_parents=True) != signature_bytes):
            raise ValueError("Contract Phase-10 output or signed record changed during verification")
        require_no_signing_secret(environment)
        require_no_signing_secret(os.environ)
    return record


def publish_verified_contract_phase10_output_record(
    record_path: Path, signature_path: Path, repository_root: Path,
    validation_repository: Path, protected_output: Path, plan_path: Path,
    destination: Path, *,
    expected_record_sha256: str, expected_signature_sha256: str,
    trusted_source_commit: str, trusted_workflow_sha: str,
    trusted_workflow_path: str, trusted_job_name: str,
    expected_pgp_key_sha256: str, artifact_id: int,
    artifact_sha256: str, token: str, environ=None,
    original_run_id=None, original_run_attempt=None,
) -> dict:
    """Re-observe, deeply verify, then publish only the external signed pair."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    require_no_signing_secret(os.environ)
    expected_record_sha256 = require_sha256(expected_record_sha256, "Contract record pin")
    expected_signature_sha256 = require_sha256(expected_signature_sha256, "Contract signature pin")
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract signed-record destination already exists")
    output_root = Path(protected_output).resolve(strict=True)
    destination_root = destination.resolve(strict=False)
    if destination_root == output_root or destination_root in output_root.parents or \
            output_root in destination_root.parents:
        raise ValueError("Contract signed-record destination overlaps finalized output")
    for source in (Path(record_path), Path(signature_path)):
        source_root = source.resolve(strict=True)
        if destination_root == source_root or destination_root in source_root.parents or \
                source_root in destination_root.parents:
            raise ValueError("Contract signed-record destination overlaps a signed input")
    record_bytes = read_regular_file_bytes(
        record_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    signature_bytes = read_regular_file_bytes(
        signature_path, max_bytes=64 * 1024, reject_symlink_parents=True,
    )
    if sha256_bytes(record_bytes) != expected_record_sha256 or \
            sha256_bytes(signature_bytes) != expected_signature_sha256:
        raise ValueError("Contract signed record differs from independent Phase-10 pins")
    with tempfile.TemporaryDirectory(prefix="ct-phase10-publish-") as temporary:
        prepared = Path(temporary).resolve() / "signed-record"
        prepared.mkdir()
        (prepared / "record.json").write_bytes(record_bytes)
        (prepared / "record.sig").write_bytes(signature_bytes)
        inventory = regular_file_inventory(prepared)
        record = verify_signed_contract_phase10_output_record(
            prepared / "record.json", prepared / "record.sig",
            repository_root, validation_repository, protected_output, plan_path,
            trusted_source_commit=trusted_source_commit,
            trusted_workflow_sha=trusted_workflow_sha,
            trusted_workflow_path=trusted_workflow_path,
            trusted_job_name=trusted_job_name,
            expected_pgp_key_sha256=expected_pgp_key_sha256,
            artifact_id=artifact_id, artifact_sha256=artifact_sha256,
            token=token, environ=environment,
            original_run_id=original_run_id,
            original_run_attempt=original_run_attempt,
        )
        if (read_regular_file_bytes(record_path, max_bytes=16 * 1024 * 1024,
                                    reject_symlink_parents=True) != record_bytes
                or read_regular_file_bytes(signature_path, max_bytes=64 * 1024,
                                           reject_symlink_parents=True) != signature_bytes
                or regular_file_inventory(protected_output) != record["outputFiles"]
                or regular_file_inventory(prepared) != inventory):
            raise ValueError("Contract signed-record input changed before publication")
        require_no_signing_secret(environment)
        publish_regular_tree(prepared, destination, expected_inventory=inventory)
    if (regular_file_inventory(destination) != inventory
            or regular_file_inventory(protected_output) != record["outputFiles"]
            or read_regular_file_bytes(record_path, max_bytes=16 * 1024 * 1024,
                                       reject_symlink_parents=True) != record_bytes
            or read_regular_file_bytes(signature_path, max_bytes=64 * 1024,
                                       reject_symlink_parents=True) != signature_bytes):
        raise ValueError("Published Contract signed record differs from verified bytes")
    return {"recordSha256": expected_record_sha256,
            "signatureSha256": expected_signature_sha256,
            "publishedFiles": inventory}


def main(argv=None) -> int:
    require_no_signing_secret(os.environ)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify-publish"):
        selected = subcommands.add_parser(command, allow_abbrev=False)
        for name in ("plan", "repository-root", "validation-repository",
                     "protected-output", "destination"):
            selected.add_argument(f"--{name}", type=Path, required=True)
        for name in ("trusted-source-commit", "trusted-workflow-sha",
                     "trusted-workflow-path", "trusted-job-name",
                     "expected-pgp-key-sha256", "artifact-id", "artifact-sha256"):
            selected.add_argument(f"--{name}", required=True)
        selected.add_argument("--original-run-id", type=int)
        selected.add_argument("--original-run-attempt", type=int)
        if command == "prepare":
            selected.add_argument("--phase11-pins", type=Path, required=True)
            selected.add_argument("--expected-phase11-pins-sha256", required=True)
        else:
            selected.add_argument("--record", type=Path, required=True)
            selected.add_argument("--signature", type=Path, required=True)
            selected.add_argument("--expected-record-sha256", required=True)
            selected.add_argument("--expected-signature-sha256", required=True)
    args = parser.parse_args(argv)
    common = dict(
        trusted_source_commit=args.trusted_source_commit,
        trusted_workflow_sha=args.trusted_workflow_sha,
        trusted_workflow_path=args.trusted_workflow_path,
        trusted_job_name=args.trusted_job_name,
        expected_pgp_key_sha256=args.expected_pgp_key_sha256,
        artifact_id=int(args.artifact_id), artifact_sha256=args.artifact_sha256,
        token=os.environ["GITHUB_TOKEN"], environ=os.environ,
        original_run_id=args.original_run_id,
        original_run_attempt=args.original_run_attempt,
    )
    if args.command == "prepare":
        pins_bytes = read_regular_file_bytes(
            args.phase11_pins, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        )
        if sha256_bytes(pins_bytes) != require_sha256(
            args.expected_phase11_pins_sha256, "independent Phase-11 pins digest",
        ):
            raise ValueError("Contract Phase-11 pins file differs from independent digest")
        result = prepare_contract_phase10_output_record(
            args.plan, args.repository_root, args.validation_repository,
            args.protected_output,
            args.destination, phase11_pins=load_canonical_json_bytes(pins_bytes), **common,
        )
    else:
        result = publish_verified_contract_phase10_output_record(
            args.record, args.signature, args.repository_root,
            args.validation_repository, args.protected_output, args.plan,
            args.destination,
            expected_record_sha256=args.expected_record_sha256,
            expected_signature_sha256=args.expected_signature_sha256,
            **common,
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
