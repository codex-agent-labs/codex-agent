"""Capture the protected Firebase intermediate upload without admitting it.

The caller pins the reviewed workflow and source identities.  This module binds
one official intermediate upload to an already captured final Android upload,
but does not grant Firebase, source, receipt, host, or product authority.
"""

import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

if __package__:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
import sdk_android_upload_locator as upload_locator
from products.inventory import (
    canonical_json_bytes, load_canonical_json_bytes, load_json_bytes,
    publish_regular_tree, read_regular_file_bytes, regular_file_inventory,
    require_array, require_exact_keys, require_integer, require_sha256,
    require_string, sha256_bytes, sha256_file, verified_zip_contents,
    write_canonical_json,
)
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from receipt import INPUT_NAMES, LANE_RECEIPT_SCHEMA_VERSION
from reuse import download_artifact


_OID = re.compile(r"[0-9a-f]{40}")
_BINDING_FILES = (
    "application.apk", "lane-receipt.json", "runtime.aar", "test.apk",
)


def _producer_from_receipt(receipt: dict) -> dict:
    return products.validate_producer({
        "repository": receipt.get("repository"),
        "workflowPath": receipt.get("workflowPath"),
        "commit": receipt.get("validationCommit"),
        "tree": receipt.get("validationTree"),
        "event": receipt.get("event"),
        "runId": receipt.get("runId"),
        "runAttempt": receipt.get("runAttempt"),
        "pullRequest": receipt.get("pullRequest"),
    }, "protected Firebase original producer")


def _verify_binding(
    root: Path,
    candidate_producer: dict,
    original_lane_producer: dict,
    source_commit: str,
    source_tree: str,
):
    binding_bytes = read_regular_file_bytes(
        root / "input-binding.json", max_bytes=64 * 1024, reject_symlink_parents=True)
    binding = load_canonical_json_bytes(binding_bytes)
    binding = require_exact_keys(binding, {
        "schemaVersion", "kind", "candidateCommit", "candidateTree",
        "trustedSourceCommit", "trustedSourceTree", "files",
    }, "Firebase input binding")
    if (require_integer(binding["schemaVersion"], "Firebase input binding schema") != 1
            or binding["kind"] != "firebase-android-input-binding"
            or binding["candidateCommit"] != candidate_producer["commit"]
            or binding["candidateTree"] != candidate_producer["tree"]
            or binding["trustedSourceCommit"] != source_commit
            or binding["trustedSourceTree"] != source_tree):
        raise ValueError("Firebase input binding identity differs from caller policy")
    records = require_array(binding["files"], "Firebase input binding files")
    if len(records) != len(_BINDING_FILES):
        raise ValueError("Firebase input binding file set is invalid")
    checked = []
    for value in records:
        record = require_exact_keys(value, {"relativePath", "bytes", "sha256"},
                                    "Firebase input binding file")
        checked.append(require_string(record["relativePath"], "Firebase bound path"))
        require_integer(record["bytes"], "Firebase bound bytes", 1)
        require_sha256(record["sha256"], "Firebase bound digest")
    if tuple(checked) != _BINDING_FILES:
        raise ValueError("Firebase input binding files are not exact and sorted")
    receipt_bytes = read_regular_file_bytes(
        root / "lane-receipt.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt_record = records[_BINDING_FILES.index("lane-receipt.json")]
    if (receipt_record["bytes"] != len(receipt_bytes)
            or receipt_record["sha256"] != sha256_bytes(receipt_bytes)):
        raise ValueError("Firebase binding does not retain its exact original lane receipt")
    receipt = load_json_bytes(receipt_bytes)
    if (type(receipt) is not dict or require_integer(receipt.get("schemaVersion"),
            "Firebase lane receipt schema") != LANE_RECEIPT_SCHEMA_VERSION
            or _producer_from_receipt(receipt) != original_lane_producer
            or receipt.get("lane") != "android"
            or receipt.get("artifactName") != f"codex-agent-ci-android-{candidate_producer['tree']}"
            or receipt.get("result") != "passed"):
        raise ValueError("Firebase protected lane receipt identity is invalid")
    return binding, binding_bytes, receipt_bytes


def capture_android_firebase_evidence(
    plan_path: Path,
    candidate_root: Path,
    final_capture: Path,
    destination: Path,
    *,
    trusted_workflow_sha: str,
    trusted_android_workflow_sha: str,
    trusted_source_commit: str,
    trusted_source_tree: str,
    environ: Mapping[str, str] | None = None,
    token: str,
) -> dict:
    """Retain one protected intermediate upload and its final-capture linkage."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Firebase evidence capture requires an observation token")
    if (_OID.fullmatch(trusted_source_commit) is None
            or _OID.fullmatch(trusted_source_tree) is None):
        raise ValueError("Firebase evidence capture requires exact caller-pinned source Git identities")
    root = Path(candidate_root).resolve(strict=True)
    source = Path(plan_path).absolute()
    final = Path(final_capture).absolute()
    destination = Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (root, source, final))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Firebase evidence capture destination must not exist")

    output_safe()
    plan_bytes = read_regular_file_bytes(
        source, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    inventory_sources = {
        name: source.parent / "inventories/android" / name for name in INPUT_NAMES.values()
    }
    inventory_bytes = {
        name: read_regular_file_bytes(path, max_bytes=16 * 1024 * 1024,
                                      reject_symlink_parents=True)
        for name, path in inventory_sources.items()
    }
    final_inventory = regular_file_inventory(final, allow_empty=True)
    final_transport_path = final / "capture-transport.json"
    final_archive_path = final / "original-upload.zip"
    final_original_path = final / "original"
    final_receipt_path = final / "original/lane-receipt.json"
    final_transport_bytes = read_regular_file_bytes(
        final_transport_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    final_receipt_bytes = read_regular_file_bytes(
        final_receipt_path, max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    final_transport = load_canonical_json_bytes(final_transport_bytes)
    final_zipped, _, _ = verified_zip_contents(
        final_archive_path, retained_paths=(), allow_empty_members=True,
        **products._CATALOG_ZIP_LIMITS,
    )
    final_original_inventory = regular_file_inventory(final_original_path, allow_empty=True)
    if final_original_inventory != final_zipped:
        raise ValueError("Final Android capture original differs from its exact official ZIP")

    with tempfile.TemporaryDirectory(prefix="android-firebase-capture-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "input-plan/impact-plan.json"
        captured_plan.parent.mkdir()
        captured_plan.write_bytes(plan_bytes)
        captured_inventories = captured_plan.parent / "inventories/android"
        captured_inventories.mkdir(parents=True)
        for name, contents in inventory_bytes.items():
            (captured_inventories / name).write_bytes(contents)
        plan = products._validate_plan(captured_plan, root)
        plan_value = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        final_locator = upload_locator.locate_android_validation_upload(
            source, root, trusted_workflow_sha=trusted_workflow_sha,
            trusted_android_workflow_sha=trusted_android_workflow_sha,
            environ=environment, token=token,
        )
        final_locator = {
            "artifact_id": require_integer(final_locator.get("artifact_id"), "Final Android artifact ID", 1),
            "artifact_sha256": require_sha256(final_locator.get("artifact_sha256"),
                                               "Final Android artifact digest"),
        }
        final_value = require_exact_keys(final_transport, {
            "schemaVersion", "kind", "artifact", "locator", "captureProducer", "laneReceiptSha256",
        }, "final Android transport")
        final_artifact = final_value["artifact"]
        final_receipt = load_json_bytes(final_receipt_bytes)
        final_original_producer = _producer_from_receipt(final_receipt) if type(final_receipt) is dict else None
        stable_producer_fields = (
            "repository", "workflowPath", "commit", "tree", "event", "pullRequest",
        )
        if (require_integer(final_value["schemaVersion"], "Final Android transport schema") != 1
                or final_value["kind"] != "android-evidence-transport"
                or final_value["locator"] != final_locator
                or products.validate_producer(final_value["captureProducer"]) != producer
                or final_value["laneReceiptSha256"] != sha256_bytes(final_receipt_bytes)
                or type(final_artifact) is not dict
                or final_artifact.get("id") != final_locator["artifact_id"]
                or final_artifact.get("digest") != final_locator["artifact_sha256"]
                or type(final_original_producer) is not dict
                or any(final_original_producer[field] != producer[field]
                       for field in stable_producer_fields)
                or final_receipt.get("lane") != "android"
                or final_receipt.get("artifactName") != f"codex-agent-ci-android-{producer['tree']}"
                or sha256_file(final_archive_path) != final_locator["artifact_sha256"]
                or read_regular_file_bytes(final / "plan/impact-plan.json") != plan_bytes
                or any(read_regular_file_bytes(final / "plan/inventories/android" / name) != contents
                       for name, contents in inventory_bytes.items())):
            raise ValueError("Final Android capture differs from its current official locator")

        def unchanged():
            require_no_signing_secret(environment)
            if (read_regular_file_bytes(source, max_bytes=16 * 1024 * 1024,
                                        reject_symlink_parents=True) != plan_bytes
                    or read_regular_file_bytes(captured_plan) != plan_bytes
                    or any(read_regular_file_bytes(inventory_sources[name], max_bytes=16 * 1024 * 1024,
                                                   reject_symlink_parents=True) != contents
                           or read_regular_file_bytes(captured_inventories / name) != contents
                           for name, contents in inventory_bytes.items())
                    or canonical_json_bytes(plan) != plan_value
                    or canonical_json_bytes(products._validate_plan(captured_plan, root)) != plan_value
                    or products.validate_producer(products._consumer(plan, environment)["producer"]) != producer
                    or regular_file_inventory(final, allow_empty=True) != final_inventory
                    or regular_file_inventory(final_original_path, allow_empty=True)
                        != final_original_inventory
                    or final_original_inventory != final_zipped
                    or read_regular_file_bytes(final_transport_path, max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True) != final_transport_bytes
                    or read_regular_file_bytes(final_receipt_path, max_bytes=16 * 1024 * 1024,
                                               reject_symlink_parents=True) != final_receipt_bytes):
                raise ValueError("Firebase capture plan, producer, or final Android capture changed")

        unchanged()
        observation = products._observe_ci_producer_jobs(
            {"firebase": producer}, jobs_by_phase={"firebase": upload_locator.FIREBASE_JOB},
            trusted_workflow_sha=trusted_workflow_sha, token=token,
        )[0]
        unchanged()
        api = f"https://api.github.com/repos/{upload_locator.REPOSITORY}/actions"
        name = f"codex-agent-ci-android-firebase-{producer['commit']}"
        artifacts = products.paginated_items(
            f"{api}/runs/{producer['runId']}/artifacts", "artifacts", token)
        selected = [value for value in artifacts if type(value) is dict
                    and value.get("name") == name and value.get("expired") is False]
        if len(selected) != 1:
            raise ValueError("Protected Firebase upload is missing or ambiguous")
        listed = selected[0]
        artifact_id = require_integer(listed.get("id"), "Firebase artifact ID", 1)
        artifact_sha256 = require_sha256(listed.get("digest"), "Firebase artifact digest")
        url = f"{api}/artifacts/{artifact_id}"
        artifact = products.api_json(url, token)
        if (type(artifact) is not dict or any(artifact.get(field) != listed.get(field) for field in (
                "id", "name", "digest", "expired", "workflow_run", "created_at", "archive_download_url"))
                or artifact.get("archive_download_url") != url + "/zip"
                or type(artifact.get("workflow_run")) is not dict
                or require_integer(artifact["workflow_run"].get("id"), "Firebase artifact run", 1)
                    != producer["runId"]
                or artifact["workflow_run"].get("head_sha") != observation["run"].get("head_sha")):
            raise ValueError("Protected Firebase upload differs from its observed run or listing")
        products._require_artifact_job_window(observation, upload_locator.FIREBASE_JOB, artifact)
        artifact_bytes = canonical_json_bytes(artifact)
        unchanged()
        archive_bytes = download_artifact(artifact, token)

        prepared = private / "captured"
        prepared.mkdir()
        retained_plan = prepared / "plan/impact-plan.json"
        retained_plan.parent.mkdir()
        retained_plan.write_bytes(plan_bytes)
        retained_inventories = retained_plan.parent / "inventories/android"
        retained_inventories.mkdir(parents=True)
        for name, contents in inventory_bytes.items():
            (retained_inventories / name).write_bytes(contents)
        linked = prepared / "linked-final"
        linked.mkdir()
        (linked / "capture-transport.json").write_bytes(final_transport_bytes)
        (linked / "lane-receipt.json").write_bytes(final_receipt_bytes)
        archive = prepared / "original-upload.zip"
        archive.write_bytes(archive_bytes)
        zipped, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS,
        )
        original = prepared / "original"
        products.safe_extract(archive, original)
        original_inventory = regular_file_inventory(original, allow_empty=True)
        if original_inventory != zipped:
            raise ValueError("Protected Firebase extraction differs from the exact original upload")
        paths = {record["relativePath"] for record in original_inventory}
        fixed = {"input-binding.json", "lane-receipt.json", "matrix.json"}
        results = paths - fixed
        if (not fixed.issubset(paths) or not results
                or any(not path.startswith("results/") or not path.endswith(".xml") for path in results)):
            raise ValueError("Protected Firebase upload has an unexpected content layout")
        binding, binding_bytes, receipt_bytes = _verify_binding(
            original, producer, final_original_producer,
            trusted_source_commit, trusted_source_tree,
        )
        locator = {"artifact_id": artifact_id, "artifact_sha256": artifact_sha256}
        transport = {
            "schemaVersion": 1,
            "kind": "android-firebase-transport",
            "artifact": artifact,
            "locator": locator,
            "captureProducer": producer,
            "inputBindingSha256": sha256_bytes(binding_bytes),
            "laneReceiptSha256": sha256_bytes(receipt_bytes),
            "linkedFinalCaptureSha256": sha256_bytes(final_transport_bytes),
            "linkedFinalLaneReceiptSha256": sha256_bytes(final_receipt_bytes),
        }
        write_canonical_json(prepared / "capture-transport.json", transport)
        transport_bytes = canonical_json_bytes(transport)
        prepared_inventory = regular_file_inventory(prepared, allow_empty=True)
        unchanged()
        if (sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != original_inventory
                or original_inventory != zipped
                or load_canonical_json_bytes(binding_bytes) != binding
                or read_regular_file_bytes(original / "input-binding.json") != binding_bytes
                or read_regular_file_bytes(original / "lane-receipt.json") != receipt_bytes
                or read_regular_file_bytes(retained_plan) != plan_bytes
                or any(read_regular_file_bytes(retained_inventories / name) != contents
                       for name, contents in inventory_bytes.items())
                or read_regular_file_bytes(linked / "capture-transport.json") != final_transport_bytes
                or read_regular_file_bytes(linked / "lane-receipt.json") != final_receipt_bytes
                or canonical_json_bytes(artifact) != artifact_bytes
                or read_regular_file_bytes(prepared / "capture-transport.json") != transport_bytes
                or regular_file_inventory(prepared, allow_empty=True) != prepared_inventory):
            raise ValueError("Protected Firebase upload or retained linkage changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
        unchanged()
    require_no_signing_secret(environment)
    return transport
