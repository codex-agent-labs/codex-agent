"""Capture the final Android evidence upload without admitting its semantics.

This retains official transport plus the complete lane bytes and reuses the
existing lane/plan checker.  A later consumer must still authenticate the
mutable-main attach tooling and run the complete Firebase APK/AAR/XML semantic
gate; neither this capture nor its transport record grants that authority.
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Mapping

if __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import product_reuse as products
import sdk_android_upload_locator as upload_locator
from products.inventory import (
    canonical_json_bytes, load_json_bytes, publish_regular_tree,
    read_regular_file_bytes, regular_file_inventory, require_integer,
    require_sha256, sha256_bytes, sha256_file, verified_zip_contents,
    write_canonical_json,
)
from products.sdk_package import _require_capability_output_separate
from products.signing_isolation import require_no_signing_secret
from receipt import INPUT_NAMES
from reuse import download_artifact


_FIREBASE_PREFIX = "payload/external/android-runtime-evidence/"
_FIREBASE_FILES = {
    _FIREBASE_PREFIX + name for name in (
        "android-runtime-evidence.json",
        "firebase-test-matrix.json",
        "RuntimeBootstrapDeviceTest.xml",
        "android-runtime-evidence-debug.apk",
        "android-runtime-evidence-debug-androidTest.apk",
        "codex-agent-runtime-android-release.aar",
        "firebase-android-runtime-verification.json",
    )
}


def _check_lane(plan: Path, lane: Path, value: dict) -> bytes:
    """Run the existing trusted structural checker, then bind the final closure."""
    tree = value["validationTree"]
    command = [
        sys.executable, str(Path(__file__).resolve().with_name("evidence.py")), "check",
        "--artifact", str(lane), "--plan", str(plan),
        "--expected-commit", value["validationCommit"],
        "--expected-artifact", f"codex-agent-ci-android-{tree}",
        "--expected-plan-artifact", f"codex-agent-ci-plan-{tree}",
        "--expected-repository", value["repository"], "--expected-event", value["event"],
    ]
    failure = None
    with tempfile.TemporaryDirectory(prefix="android-evidence-check-") as temporary:
        bytecode = Path(temporary).resolve() / "python-bytecode"
        environment = {
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
            "PYTHONPYCACHEPREFIX": str(bytecode),
            "PYTHONPATH": str(Path(__file__).resolve().parent),
        }
        try:
            subprocess.run(command, check=True, env=environment, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            failure = error
        if bytecode.exists() or bytecode.is_symlink():
            raise ValueError("Android evidence check created its isolated bytecode namespace")
    if failure is not None:
        raise ValueError("Android original lane or impact plan failed its existing evidence check") from failure
    receipt_bytes = read_regular_file_bytes(
        lane / "lane-receipt.json", max_bytes=16 * 1024 * 1024, reject_symlink_parents=True)
    receipt = load_json_bytes(receipt_bytes)
    firebase = {
        record.get("relativePath") for record in receipt.get("evidence", ())
        if type(record) is dict and record.get("kind") == "firebase-runtime-evidence"
    }
    if firebase != _FIREBASE_FILES:
        raise ValueError("Android upload lacks the exact final seven-file Firebase closure")
    return receipt_bytes


def capture_android_evidence(
    plan_path: Path,
    candidate_root: Path,
    destination: Path,
    *,
    trusted_workflow_sha: str,
    trusted_android_workflow_sha: str,
    environ: Mapping[str, str] | None = None,
    token: str,
    expected_revision: str | None = None,
) -> dict:
    """Retain one fixed final upload; return transport metadata, not admission."""
    environment = os.environ if environ is None else environ
    require_no_signing_secret(environment)
    if type(token) is not str or not token:
        raise ValueError("Android evidence capture requires an observation token")
    root = Path(candidate_root).resolve(strict=True)
    source = Path(plan_path).absolute()
    destination = Path(destination).absolute()

    def output_safe():
        _require_capability_output_separate(destination, (root, source))
        if destination.exists() or destination.is_symlink():
            raise ValueError("Android evidence capture destination must not exist")

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
    with tempfile.TemporaryDirectory(prefix="android-evidence-capture-") as temporary:
        private = Path(temporary).resolve()
        captured_plan = private / "input-plan/impact-plan.json"
        captured_plan.parent.mkdir()
        captured_plan.write_bytes(plan_bytes)
        captured_inventories = captured_plan.parent / "inventories/android"
        captured_inventories.mkdir(parents=True)
        for name, contents in inventory_bytes.items():
            (captured_inventories / name).write_bytes(contents)
        plan = products._validate_plan(captured_plan, root, expected_revision=expected_revision)
        plan_value = canonical_json_bytes(plan)
        producer = products.validate_producer(products._consumer(plan, environment)["producer"])
        locator = upload_locator.locate_android_validation_upload(
            source, root, trusted_workflow_sha=trusted_workflow_sha,
            trusted_android_workflow_sha=trusted_android_workflow_sha,
            environ=environment, token=token,
            expected_revision=expected_revision,
        )
        artifact_id = require_integer(locator.get("artifact_id"), "Android artifact ID", 1)
        artifact_sha256 = require_sha256(locator.get("artifact_sha256"), "Android artifact digest")

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
                    or canonical_json_bytes(products._validate_plan(captured_plan, root, expected_revision=expected_revision)) != plan_value
                    or products.validate_producer(products._consumer(plan, environment)["producer"]) != producer):
                raise ValueError("Android capture plan or current producer changed")

        # Do not begin the download after a locator was derived from changed input.
        unchanged()
        api = f"https://api.github.com/repos/{upload_locator.REPOSITORY}/actions"
        url = f"{api}/artifacts/{artifact_id}"
        artifact = products.api_json(url, token)
        expected_name = f"codex-agent-ci-android-{producer['tree']}"
        workflow_run = artifact.get("workflow_run") if type(artifact) is dict else None
        if (type(artifact) is not dict
                or require_integer(artifact.get("id"), "Android artifact ID", 1) != artifact_id
                or artifact.get("name") != expected_name or artifact.get("expired") is not False
                or artifact.get("digest") != artifact_sha256
                or artifact.get("archive_download_url") != url + "/zip"
                or type(workflow_run) is not dict
                or require_integer(workflow_run.get("id"), "Android artifact run", 1) != producer["runId"]):
            raise ValueError("Android artifact changed after its fixed locator was observed")
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
        archive = prepared / "original-upload.zip"
        archive.write_bytes(archive_bytes)
        zipped, _, _ = verified_zip_contents(
            archive, retained_paths=(), allow_empty_members=True,
            **products._CATALOG_ZIP_LIMITS,
        )
        original = prepared / "original"
        products.safe_extract(archive, original)
        if regular_file_inventory(original, allow_empty=True) != zipped:
            raise ValueError("Android extraction differs from the exact original upload")
        receipt_bytes = _check_lane(retained_plan, original, plan)
        transport = {
            "schemaVersion": 1,
            "kind": "android-evidence-transport",
            "artifact": artifact,
            "locator": locator,
            "captureProducer": producer,
            "laneReceiptSha256": sha256_bytes(receipt_bytes),
        }
        write_canonical_json(prepared / "capture-transport.json", transport)
        original_inventory = regular_file_inventory(original, allow_empty=True)
        transport_bytes = canonical_json_bytes(transport)
        unchanged()
        if (sha256_file(archive) != artifact_sha256
                or regular_file_inventory(original, allow_empty=True) != original_inventory
                or original_inventory != zipped
                or read_regular_file_bytes(retained_plan) != plan_bytes
                or any(read_regular_file_bytes(retained_inventories / name) != contents
                       for name, contents in inventory_bytes.items())
                or read_regular_file_bytes(original / "lane-receipt.json",
                                           max_bytes=16 * 1024 * 1024,
                                           reject_symlink_parents=True) != receipt_bytes
                or canonical_json_bytes(artifact) != artifact_bytes
                or read_regular_file_bytes(prepared / "capture-transport.json") != transport_bytes):
            raise ValueError("Android original upload or retained capture changed before publication")
        output_safe()
        publish_regular_tree(prepared, destination, allow_empty=True)
    require_no_signing_secret(environment)
    return transport
