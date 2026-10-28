"""Elect four original Contract uploads before token-free catalog signing.

The protected workflow supplies independently reviewed S1048 pins. This module
does not create those pins or authorize a protected environment.
"""

from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
from typing import Mapping

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from ci import product_reuse as transport
from ci.contract_catalog_promotion import stage_promoted_contract_catalog
from ci.products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_exact_keys,
    require_integer, require_sha256, sha256_bytes, sha256_file,
    verified_zip_contents, write_canonical_json,
)
from ci.products.receipt import validate_producer
from ci.products.registry import PhaseInstanceId
from ci.products.restore import object_relative_path, verify_phase_shard
from ci.products.signing_isolation import require_no_signing_secret
from ci.receipt import safe_extract


PHASES = ("binary", "package", "validation", "metadata")
PIN_KEYS = {"producer", "workflowPath", "workflowSha", "jobName", "artifactId",
            "artifactSha256", "buildKey", "receiptSha256", "objectSha256", "artifactPath"}
TOKENS = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "ACTIONS_RUNTIME_TOKEN",
          "ACTIONS_ID_TOKEN_REQUEST_TOKEN"}


def _pins(selection: Mapping) -> dict:
    require_exact_keys(selection, set(PHASES), "Contract original phase selection")
    result = {}
    uploads = set()
    for phase in PHASES:
        pin = require_exact_keys(selection[phase], PIN_KEYS, f"Contract {phase} original pin")
        producer = validate_producer(pin["producer"])
        if producer["repository"] != "codex-agent-labs/codex-agent" or \
                producer["workflowPath"] != ".github/workflows/ci.yml" or \
                producer["event"] not in {"pull_request", "merge_group"}:
            raise ValueError(f"Contract {phase} producer is not an eligible original CI attempt")
        for name in ("artifactSha256", "buildKey", "receiptSha256", "objectSha256"):
            require_sha256(pin[name], f"Contract {phase} {name}")
        upload = require_integer(pin["artifactId"], f"Contract {phase} artifact ID", 1)
        if upload in uploads:
            raise ValueError("Contract original phases cannot share an upload ID")
        uploads.add(upload)
        if type(pin["artifactPath"]) is not str or not pin["artifactPath"]:
            raise ValueError(f"Contract {phase} distinguished artifact path is missing")
        result[phase] = pin
    return result


def _verify_shard(root: Path, phase: str, pin: dict, receipt_bytes: bytes) -> Path:
    verified = verify_phase_shard(root, PhaseInstanceId("contract", "contract", phase, "common"))
    receipt = verified["receipt"]
    if (verified["buildKey"] != pin["buildKey"] or
            verified["receiptSha256"] != pin["receiptSha256"] or
            verified["objectSha256"] != pin["objectSha256"] or
            verified["receiptBytes"] != receipt_bytes or
            receipt["producer"] != pin["producer"] or
            sum(row["relativePath"] == pin["artifactPath"] for row in receipt["outputs"]) != 1):
        raise ValueError(f"Contract {phase} original upload differs from S1048 selection")
    return root / object_relative_path(pin["buildKey"], pin["receiptSha256"])


def capture_promotable_contract_originals(handoff: Path, destination: Path, *,
        selection: Mapping, token: str, environ: Mapping[str, str]) -> dict:
    """Token-only capture of independently pinned official phase uploads."""
    require_no_signing_secret(environ)
    require_no_signing_secret(os.environ)
    if type(token) is not str or not token:
        raise ValueError("Contract original capture requires an observation token")
    pins = _pins(selection)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Contract original capture destination already exists")
    handoff_root = Path(handoff).resolve(strict=True)
    output_root = Path(destination).resolve(strict=False)
    if output_root == handoff_root or output_root in handoff_root.parents or \
            handoff_root in output_root.parents:
        raise ValueError("Contract original capture overlaps signed handoff")
    handoff_files = regular_file_inventory(handoff)
    receipts = {phase: read_regular_file_bytes(
        handoff / f"execution-closure/receipts/{phase}.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True) for phase in PHASES}
    for phase in PHASES:
        if sha256_bytes(receipts[phase]) != pins[phase]["receiptSha256"]:
            raise ValueError(f"Contract {phase} handoff differs from S1048 receipt")
    observed = transport._observe_ci_producer_jobs(
        {phase: pins[phase]["producer"] for phase in PHASES},
        jobs_by_phase={phase: pins[phase]["jobName"] for phase in PHASES},
        trusted_workflows_by_phase={phase: {"path": pins[phase]["workflowPath"],
                                            "sha": pins[phase]["workflowSha"]} for phase in PHASES},
        token=token,
    )
    attempts = {(item["run"]["id"], item["run"]["run_attempt"]): item for item in observed}
    with tempfile.TemporaryDirectory(prefix="contract-original-election-") as temporary:
        root = Path(temporary).resolve()
        prepared = root / "prepared"
        prepared.mkdir()
        uploads = {}
        for phase in PHASES:
            pin = pins[phase]
            producer = pin["producer"]
            observation = attempts[producer["runId"], producer["runAttempt"]]
            name = (f"codex-agent-product-phase-contract-contract-{phase}-common-"
                    f"{producer['tree']}")
            archive = prepared / "uploads" / f"{phase}.zip"
            archive.parent.mkdir(exist_ok=True)
            artifact, _ = transport._download_contract_ci_upload(
                pin["artifactId"], pin["artifactSha256"], name, producer,
                observation["run"], token, destination=archive)
            transport._require_artifact_job_window(observation, pin["jobName"], artifact)
            inventory, _, _ = verified_zip_contents(
                archive, retained_paths=(), **transport._CATALOG_ZIP_LIMITS)
            shard = root / "shard" / phase
            safe_extract(archive, shard)
            if regular_file_inventory(shard) != inventory:
                raise ValueError(f"Contract {phase} original upload changed during extraction")
            original = _verify_shard(shard, phase, pin, receipts[phase])
            target = prepared / "objects" / f"{phase}.zip"
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(read_regular_file_bytes(original, max_bytes=1024 * 1024 * 1024,
                                                       reject_symlink_parents=True))
            uploads[phase] = artifact
        write_canonical_json(prepared / "selection.json", pins)
        write_canonical_json(prepared / "transport.json", {"observed": observed, "uploads": uploads,
                                                            "handoffInventory": handoff_files})
        expected = regular_file_inventory(prepared)
        if regular_file_inventory(handoff) != handoff_files or \
                any(sha256_bytes(read_regular_file_bytes(
                    handoff / f"execution-closure/receipts/{phase}.json",
                    max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)) != pins[phase]["receiptSha256"]
                    for phase in PHASES):
            raise ValueError("Contract original handoff changed during election")
        require_no_signing_secret(environ)
        require_no_signing_secret(os.environ)
        publish_regular_tree(prepared, destination, expected_inventory=expected)
    return {"inventorySha256": sha256_bytes(canonical_json_bytes(expected)),
            "uploads": uploads}


def sign_promoted_contract_catalog(handoff: Path, captured: Path, destination: Path, *,
        selection: Mapping, expected_capture_inventory_sha256: str,
        repository: str, context: dict, producer: dict, keyring: Path,
        keys_directory: Path, private_key: Path, environ: Mapping[str, str]) -> dict:
    """Token-free signer rechecks the exact S1048 capture before composition."""
    if TOKENS & set(environ) or TOKENS & set(os.environ):
        raise ValueError("Contract catalog signer must not receive an observation token")
    destination_root = Path(destination).resolve(strict=False)
    if Path(destination).exists() or Path(destination).is_symlink():
        raise ValueError("Contract catalog destination already exists")
    for source in (captured, handoff, keyring, keys_directory, private_key):
        source_root = Path(source).resolve(strict=True)
        if destination_root == source_root or destination_root in source_root.parents or \
                source_root in destination_root.parents:
            raise ValueError("Contract catalog destination overlaps original input")
    pins = _pins(selection)
    inventory = regular_file_inventory(captured)
    if sha256_bytes(canonical_json_bytes(inventory)) != require_sha256(
            expected_capture_inventory_sha256, "Contract S1048 capture inventory"):
        raise ValueError("Contract original capture differs from independent S1048 pin")
    if load_canonical_json_bytes(read_regular_file_bytes(
            captured / "selection.json", max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True)) != pins:
        raise ValueError("Contract captured selection differs from independent S1048 pins")
    evidence = load_canonical_json_bytes(read_regular_file_bytes(
        captured / "transport.json", max_bytes=16 * 1024 * 1024,
        reject_symlink_parents=True))
    require_exact_keys(evidence, {"observed", "uploads", "handoffInventory"},
                       "Contract original transport")
    require_exact_keys(evidence["uploads"], set(PHASES), "Contract original uploads")
    for phase in PHASES:
        upload = evidence["uploads"][phase]
        if upload.get("id") != pins[phase]["artifactId"] or \
                upload.get("digest") != pins[phase]["artifactSha256"]:
            raise ValueError(f"Contract {phase} captured official upload differs from S1048 pin")
    if regular_file_inventory(handoff) != evidence["handoffInventory"]:
        raise ValueError("Contract signed handoff changed since original election")
    objects = {}
    for phase in PHASES:
        pin = pins[phase]
        archive = captured / "uploads" / f"{phase}.zip"
        if sha256_file(archive) != pin["artifactSha256"]:
            raise ValueError(f"Contract {phase} official upload changed")
        with tempfile.TemporaryDirectory(prefix=f"contract-{phase}-recheck-") as temporary:
            root = Path(temporary).resolve()
            inventory_in_zip, _, _ = verified_zip_contents(
                archive, retained_paths=(), **transport._CATALOG_ZIP_LIMITS)
            safe_extract(archive, root / "shard")
            if regular_file_inventory(root / "shard") != inventory_in_zip:
                raise ValueError(f"Contract {phase} upload changed on signer")
            receipt = read_regular_file_bytes(
                handoff / f"execution-closure/receipts/{phase}.json",
                max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
            original = _verify_shard(root / "shard", phase, pin, receipt)
            if sha256_file(original) != sha256_file(captured / "objects" / f"{phase}.zip"):
                raise ValueError(f"Contract {phase} captured object differs from original upload")
        objects[phase] = captured / "objects" / f"{phase}.zip"
    with tempfile.TemporaryDirectory(prefix="contract-promoted-caller-") as temporary:
        staged = Path(temporary).resolve() / "catalog"
        index = stage_promoted_contract_catalog(
            handoff, objects, {phase: {name: pins[phase][name] for name in (
                "buildKey", "receiptSha256", "objectSha256", "artifactPath", "producer")}
                for phase in PHASES}, staged, repository=repository, context=context,
            producer=producer, keyring=keyring, keys_directory=keys_directory,
            private_key=private_key)
        if regular_file_inventory(captured) != inventory:
            raise ValueError("Contract original capture changed during catalog signing")
        publish_regular_tree(staged, destination, expected_inventory=regular_file_inventory(staged))
    return index
