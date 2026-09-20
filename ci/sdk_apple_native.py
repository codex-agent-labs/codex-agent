"""Authenticate the three fresh Apple native lanes for the existing exporter.

This context only binds transport and exact lane-receipt bytes.  The existing
Kotlin import task remains responsible for validating the native semantics.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Any

if __package__:
    from . import product_reuse
    from .receipt import INPUT_NAMES, safe_extract, validate_receipt
    from .products.inventory import (
        canonical_json_bytes,
        load_canonical_json_bytes,
        load_json_bytes,
        read_regular_file_bytes,
        regular_file_inventory,
        require_exact_keys,
        require_integer,
        require_sha256,
        sha256_bytes,
        verified_zip_contents,
        write_canonical_json,
    )
    from .products.receipt import validate_phase_receipt, validate_producer
    from .sdk_apple_source import _original_transport_producer
else:
    import product_reuse
    from receipt import INPUT_NAMES, safe_extract, validate_receipt
    from products.inventory import (
        canonical_json_bytes,
        load_canonical_json_bytes,
        load_json_bytes,
        read_regular_file_bytes,
        regular_file_inventory,
        require_exact_keys,
        require_integer,
        require_sha256,
        sha256_bytes,
        verified_zip_contents,
        write_canonical_json,
    )
    from products.receipt import validate_phase_receipt, validate_producer
    from sdk_apple_source import _original_transport_producer


LANES = ("ios-native-tests", "ios-rust-device", "ios-rust-simulator")
JOBS = {lane: f"product-validation / apple / {lane.removeprefix('ios-')}" for lane in LANES}
NATIVE_FILES = {
    "ios-native-tests": {
        "payload/codex-agent-runtime-ios/build/apple-slice-exports/native-tests/native-tests-proof.json":
            "native-tests-proof.json",
    },
    "ios-rust-device": {
        "payload/codex-agent-runtime-ios/build/apple-slice-exports/codex-agent-ios-arm64.a":
            "codex-agent-ios-arm64.a",
        "payload/codex-agent-runtime-ios/build/apple-slice-exports/codex-agent-ios-arm64-proof.json":
            "codex-agent-ios-arm64-proof.json",
    },
    "ios-rust-simulator": {
        "payload/codex-agent-runtime-ios/build/apple-slice-exports/codex-agent-ios-simulator-arm64.a":
            "codex-agent-ios-simulator-arm64.a",
        "payload/codex-agent-runtime-ios/build/apple-slice-exports/codex-agent-ios-simulator-arm64-proof.json":
            "codex-agent-ios-simulator-arm64-proof.json",
    },
}
NATIVE_RECORDS = {
    "ios-native-tests": {
        ("evidence", next(iter(NATIVE_FILES["ios-native-tests"])), "native-test-proof"),
        ("evidence", "lane-result.txt", "lane-result"),
    },
    "ios-rust-device": {
        ("artifacts", "payload/codex-agent-runtime-ios/build/apple-slice-exports/"
         "codex-agent-ios-arm64.a", "rust-archive"),
        ("evidence", "payload/codex-agent-runtime-ios/build/apple-slice-exports/"
         "codex-agent-ios-arm64-proof.json", "rust-proof"),
    } | {("evidence", "lane-result.txt", "lane-result")},
    "ios-rust-simulator": {
        ("artifacts", "payload/codex-agent-runtime-ios/build/apple-slice-exports/"
         "codex-agent-ios-simulator-arm64.a", "rust-archive"),
        ("evidence", "payload/codex-agent-runtime-ios/build/apple-slice-exports/"
         "codex-agent-ios-simulator-arm64-proof.json", "rust-proof"),
    } | {("evidence", "lane-result.txt", "lane-result")},
}


def _receipt_producer(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return validate_producer({
        "repository": receipt["repository"],
        "workflowPath": receipt["workflowPath"],
        "commit": receipt["validationCommit"],
        "tree": receipt["validationTree"],
        "event": receipt["event"],
        "runId": receipt["runId"],
        "runAttempt": receipt["runAttempt"],
        "pullRequest": receipt["pullRequest"],
    }, "Apple native lane producer")


def _require_native_records(
    receipt: Mapping[str, Any], lane: str, root: Path,
) -> dict[str, Any] | None:
    records = {
        (collection, item["relativePath"], item["kind"])
        for collection in ("artifacts", "evidence")
        for item in receipt[collection]
    }
    provenance = {("evidence", "transport-provenance.json", "transport-provenance")}
    if records == NATIVE_RECORDS[lane]:
        return None
    if records != NATIVE_RECORDS[lane] | provenance:
        raise ValueError("Apple native lane receipt has an unexpected output inventory")
    original = _original_transport_producer(root, receipt, lane_name=lane)
    if original is None:
        raise ValueError("Apple native reused lane lacks its transport provenance")
    return original[0]


@contextmanager
def verified_sdk_apple_native_inputs(
    plan_path: Path,
    *,
    uploads: Mapping[str, Mapping[str, Any]],
    trusted_workflow_sha: str,
    repository_root: Path,
    environ: Mapping[str, str],
    token: str,
    original_binary_receipt_path: Path | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield exact fresh or receipt-selected native evidence while uploads stay verified."""
    if type(token) is not str or not token:
        raise ValueError("Apple native input capture requires an observation token")
    upload_values = require_exact_keys(uploads, LANES, "Apple native uploads")
    selected_uploads = {}
    for lane in LANES:
        upload = require_exact_keys(
            upload_values[lane], {"artifactId", "artifactSha256"},
            f"Apple native {lane} upload",
        )
        selected_uploads[lane] = {
            "artifactId": require_integer(upload["artifactId"], f"Apple native {lane} artifact ID", 1),
            "artifactSha256": require_sha256(
                upload["artifactSha256"], f"Apple native {lane} artifact digest",
            ),
        }
    if len({value["artifactId"] for value in selected_uploads.values()}) != len(LANES):
        raise ValueError("Apple native uploads must have distinct artifact IDs")

    root = Path(repository_root).resolve(strict=True)
    plan_path = Path(plan_path)
    plan_bytes = read_regular_file_bytes(
        plan_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
    )
    original_receipt_path = (Path(original_binary_receipt_path).absolute()
                             if original_binary_receipt_path is not None else None)
    original_receipt_bytes = None
    original_receipt = None
    binary_producer = None
    if original_receipt_path is not None:
        original_receipt_bytes = read_regular_file_bytes(
            original_receipt_path, max_bytes=16 * 1024 * 1024,
            reject_symlink_parents=True,
        )
        original_receipt = validate_phase_receipt(
            load_canonical_json_bytes(original_receipt_bytes),
        )
        if tuple(original_receipt[name] for name in ("product", "component", "phase", "target")) != (
                "sdk", "sdk-ios", "binary", "ios"):
            raise ValueError("Historical Apple native inputs require the original iOS SDK binary receipt")
        binary_producer = validate_producer(
            original_receipt["producer"], "Original iOS SDK binary producer",
        )
    inventory_sources = {
        (lane, name): plan_path.parent / "inventories" / lane / name
        for lane in LANES for name in INPUT_NAMES.values()
    }
    inventory_bytes = {
        identity: read_regular_file_bytes(path, reject_symlink_parents=True)
        for identity, path in inventory_sources.items()
    }

    with tempfile.TemporaryDirectory(prefix="sdk-apple-native-") as temporary:
        private = Path(temporary).resolve()
        private_plan = private / "plan/impact-plan.json"
        private_plan.parent.mkdir()
        private_plan.write_bytes(plan_bytes)
        private_receipt = None
        if original_receipt_bytes is not None:
            private_receipt = private / "original-binary-receipt.json"
            private_receipt.write_bytes(original_receipt_bytes)
        for (lane, name), contents in inventory_bytes.items():
            target = private_plan.parent / "inventories" / lane / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(contents)

        plan_options = ({"expected_revision": binary_producer["commit"]}
                        if binary_producer is not None else {})
        plan = product_reuse._validate_plan(private_plan, root, **plan_options)
        if plan["remoteBuildAuthorized"] is not True or plan["event"] == "workflow_dispatch":
            raise ValueError("Apple native input capture requires an authorized PR or merge-group plan")
        producer_environment = (dict(environ) if binary_producer is None else {
            "GITHUB_RUN_ID": str(binary_producer["runId"]),
            "GITHUB_RUN_ATTEMPT": str(binary_producer["runAttempt"]),
        })
        producer = product_reuse._consumer(plan, producer_environment)["producer"]
        if binary_producer is not None and producer != binary_producer:
            raise ValueError("Historical Apple native plan differs from the original binary producer")
        observed = product_reuse._observe_ci_producer_jobs(
            {lane: producer for lane in LANES}, jobs_by_phase=JOBS,
            trusted_workflow_sha=trusted_workflow_sha, token=token,
        )
        if len(observed) != 1:
            raise ValueError("Apple native lanes must share one current CI attempt")

        artifacts = {}
        receipt_bytes = {}
        receipts = {}
        raw_archives = {}
        lane_inventories = {}
        original_producers = {}
        evidence = private / "native-evidence"
        evidence.mkdir()
        for lane in LANES:
            expected_name = f"codex-agent-ci-{lane}-{producer['tree']}"
            selected = selected_uploads[lane]
            artifact, raw = product_reuse._download_contract_ci_upload(
                selected["artifactId"], selected["artifactSha256"], expected_name,
                producer, observed[0]["run"], token,
            )
            product_reuse._require_artifact_job_window(observed[0], JOBS[lane], artifact)
            archive = private / "archives" / f"{lane}.zip"
            archive.parent.mkdir(exist_ok=True)
            archive.write_bytes(raw)
            verified_zip_contents(
                archive, retained_paths=(), allow_empty_members=True,
                **product_reuse._CATALOG_ZIP_LIMITS,
            )
            captured = private / "lanes" / lane
            safe_extract(archive, captured)
            receipt_path = captured / "lane-receipt.json"
            receipt = validate_receipt(
                receipt_path, private_plan, captured, lane, repository_root=root,
            )
            if receipt["artifactName"] != expected_name or _receipt_producer(receipt) != producer:
                raise ValueError("Apple native lane receipt differs from its current upload producer")
            original_producer = _require_native_records(receipt, lane, captured) or producer
            for source, destination in NATIVE_FILES[lane].items():
                contents = read_regular_file_bytes(
                    captured / source,
                    max_bytes=product_reuse._CATALOG_LIMIT,
                    reject_symlink_parents=True,
                )
                if not contents:
                    raise ValueError("Apple native evidence contains an empty required file")
                if destination.endswith(".json"):
                    proof = load_json_bytes(contents)
                    if (type(proof) is not dict
                            or proof.get("candidateCommit") != original_producer["commit"]
                            or proof.get("candidateTree") != original_producer["tree"]):
                        raise ValueError("Apple native proof differs from its original producer")
                (evidence / destination).write_bytes(contents)
            artifacts[lane] = artifact
            receipt_bytes[lane] = read_regular_file_bytes(
                receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
            )
            receipts[lane] = receipt
            raw_archives[lane] = raw
            lane_inventories[lane] = regular_file_inventory(captured, allow_empty=True)
            original_producers[lane] = original_producer

        evidence_inventory = regular_file_inventory(evidence)
        transport = {
            "schemaVersion": 1,
            "captureProducer": producer,
            "observed": observed,
            "artifacts": artifacts,
            "receiptSha256s": {
                lane: sha256_bytes(receipt_bytes[lane]) for lane in LANES
            },
        }
        if original_receipt_bytes is not None:
            transport["binaryReceiptSha256"] = sha256_bytes(original_receipt_bytes)
        transport_path = private / "native-transport.json"
        write_canonical_json(transport_path, transport)
        transport_bytes = read_regular_file_bytes(
            transport_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True,
        )

        def unchanged() -> None:
            if (read_regular_file_bytes(
                    plan_path, max_bytes=16 * 1024 * 1024,
                    reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(
                        private_plan, max_bytes=16 * 1024 * 1024,
                        reject_symlink_parents=True) != plan_bytes
                    or (original_receipt_path is not None and (
                        read_regular_file_bytes(
                            original_receipt_path, max_bytes=16 * 1024 * 1024,
                            reject_symlink_parents=True) != original_receipt_bytes
                        or read_regular_file_bytes(
                            private_receipt, max_bytes=16 * 1024 * 1024,
                            reject_symlink_parents=True) != original_receipt_bytes
                        or canonical_json_bytes(original_receipt) != original_receipt_bytes))
                    or any(read_regular_file_bytes(
                        path, reject_symlink_parents=True) != inventory_bytes[identity]
                        for identity, path in inventory_sources.items())
                    or any(read_regular_file_bytes(
                        private_plan.parent / "inventories" / lane / name,
                        reject_symlink_parents=True) != inventory_bytes[(lane, name)]
                        for lane in LANES for name in INPUT_NAMES.values())
                    or any(read_regular_file_bytes(
                        private / "archives" / f"{lane}.zip",
                        max_bytes=product_reuse._CATALOG_LIMIT,
                        reject_symlink_parents=True) != raw_archives[lane]
                        for lane in LANES)
                    or any(regular_file_inventory(
                        private / "lanes" / lane, allow_empty=True,
                    ) != lane_inventories[lane] for lane in LANES)
                    or regular_file_inventory(evidence) != evidence_inventory
                    or read_regular_file_bytes(
                        transport_path, max_bytes=16 * 1024 * 1024,
                        reject_symlink_parents=True) != transport_bytes):
                raise ValueError("Apple native original inputs changed during use")
            if product_reuse._validate_plan(private_plan, root, **plan_options) != plan:
                raise ValueError("Apple native plan changed during use")

        unchanged()
        try:
            yield {
                "directory": evidence,
                "captureRoot": private,
                "producer": producer,
                "originalProducers": original_producers,
                "receipts": receipts,
                "receiptBytes": receipt_bytes,
                "transport": transport,
                "inventory": evidence_inventory,
            }
        finally:
            unchanged()
