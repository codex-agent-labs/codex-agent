"""Transport capture tests; Firebase semantic admission remains separate."""

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_android_evidence_capture as capture
from ci.tests import test_ci as fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes


class AndroidEvidenceCaptureTest(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ReceiptTest(methodName="runTest")
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.root = self.f.root.resolve()
        self.plan_path = self.f.plan_path.resolve()
        capture_temporary = tempfile.TemporaryDirectory(prefix="android-evidence-capture-test-")
        self.addCleanup(capture_temporary.cleanup)
        self.capture_root = Path(capture_temporary.name).resolve()
        self.output = self.capture_root / "captured-android"
        self.workflow_pin = "c" * 40
        self.android_pin = "d" * 40
        self.environment = {"GITHUB_RUN_ID": "101", "GITHUB_RUN_ATTEMPT": "2"}
        self.plan = json.loads(self.plan_path.read_bytes())
        self.plan["androidEvidenceRequired"] = True
        self.plan_path.write_text(json.dumps(self.plan, indent=2, sort_keys=True) + "\n")
        self.firebase = self.root / "firebase"
        self.firebase.mkdir()
        for index, name in enumerate(sorted(path.rsplit("/", 1)[1] for path in capture._FIREBASE_FILES)):
            (self.firebase / name).write_bytes(b"" if index == 0 else f"exact:{name}".encode())
        command = [
            sys.executable, str(Path(capture.__file__).with_name("evidence.py")), "attach",
            "--artifact", str(self.f.receipt_root), "--plan", str(self.plan_path),
            "--source", str(self.firebase), "--replace",
            "--expected-commit", self.plan["validationCommit"],
            "--expected-artifact", f"codex-agent-ci-android-{self.plan['validationTree']}",
            "--expected-plan-artifact", f"codex-agent-ci-plan-{self.plan['validationTree']}",
            "--expected-repository", self.plan["repository"], "--expected-event", self.plan["event"],
        ]
        subprocess.run(command, check=True, env={}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.archive()
        self.artifact = {
            "id": 701, "name": f"codex-agent-ci-android-{self.plan['validationTree']}",
            "expired": False, "digest": sha256_bytes(self.raw),
            "created_at": "2026-09-11T10:15:00Z",
            "archive_download_url": (
                "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/701/zip"),
            "workflow_run": {"id": 101, "head_sha": "f" * 40},
        }
        self.requests = []
        clean_environment = {"GIT_ALLOW_PROTOCOL": "file"}
        if "DEVELOPER_DIR" in os.environ:
            clean_environment["DEVELOPER_DIR"] = os.environ["DEVELOPER_DIR"]
        self.enterContext(patch.dict(os.environ, clean_environment, clear=True))

    def archive(self):
        files = sorted(path for path in self.f.receipt_root.rglob("*") if path.is_file())
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for path in reversed(files):
                archive.writestr(path.relative_to(self.f.receipt_root).as_posix(), path.read_bytes())
        self.raw = stream.getvalue()

    def api(self, url, token):
        self.requests.append(url)
        self.assertEqual("synthetic-token", token)
        if url == self.artifact["archive_download_url"]:
            return self.raw
        if url == self.artifact["archive_download_url"].removesuffix("/zip"):
            return json.dumps(self.artifact).encode()
        raise AssertionError(f"Unexpected HTTP request: {url}")

    def call(self, **changes):
        arguments = {
            "trusted_workflow_sha": self.workflow_pin,
            "trusted_android_workflow_sha": self.android_pin,
            "environ": self.environment, "token": "synthetic-token",
        }
        arguments.update(changes)
        locator = {"artifact_id": 701, "artifact_sha256": self.artifact["digest"]}
        with patch.object(capture.upload_locator, "locate_android_validation_upload",
                          return_value=locator) as locate, \
                patch("reuse.api_request", side_effect=self.api):
            result = capture.capture_android_evidence(
                self.plan_path, self.root, self.output, **arguments)
        return result, locate

    def test_exact_zip_plan_lane_and_empty_firebase_bytes_are_retained_without_admission(self):
        before = regular_file_inventory(self.f.receipt_root, allow_empty=True)
        result, locate = self.call()
        self.assertEqual(self.raw, (self.output / "original-upload.zip").read_bytes())
        self.assertEqual(before, regular_file_inventory(self.output / "original", allow_empty=True))
        self.assertEqual(self.plan_path.read_bytes(), (self.output / "plan/impact-plan.json").read_bytes())
        for name in capture.INPUT_NAMES.values():
            self.assertEqual(
                (self.plan_path.parent / "inventories/android" / name).read_bytes(),
                (self.output / "plan/inventories/android" / name).read_bytes())
        for path in capture._FIREBASE_FILES:
            relative = path.removeprefix(capture._FIREBASE_PREFIX)
            self.assertEqual((self.firebase / relative).read_bytes(),
                             (self.output / "original" / path).read_bytes())
        self.assertEqual("android-evidence-transport", result["kind"])
        self.assertEqual(sha256_bytes((self.output / "original/lane-receipt.json").read_bytes()),
                         result["laneReceiptSha256"])
        locate.assert_called_once_with(
            self.plan_path, self.root, trusted_workflow_sha=self.workflow_pin,
            trusted_android_workflow_sha=self.android_pin,
            environ=self.environment, token="synthetic-token")
        self.assertEqual(1, self.requests.count(self.artifact["archive_download_url"]))
        self.assertNotIn("admission", canonical_json_bytes(result).decode())

    def test_transport_detail_digest_unsafe_archive_and_incomplete_closure_reject(self):
        baseline_artifact, baseline_raw = deepcopy(self.artifact), self.raw
        failures = {"name": "artifact changed", "run": "artifact changed",
                    "digest": "digest mismatch", "unsafe": "ZIP member path is not normalized",
                    "closure": "seven-file Firebase closure"}
        for case in failures:
            self.artifact, self.raw = deepcopy(baseline_artifact), baseline_raw
            if case == "name":
                self.artifact["name"] += "-wrong"
            elif case == "run":
                self.artifact["workflow_run"]["id"] = 102
            elif case == "digest":
                self.raw += b"changed"
            elif case == "unsafe":
                stream = io.BytesIO(self.raw)
                with zipfile.ZipFile(stream, "a") as archive:
                    archive.writestr("../escape", b"unsafe")
                self.raw = stream.getvalue()
                self.artifact["digest"] = sha256_bytes(self.raw)
            else:
                receipt = json.loads((self.f.receipt_root / "lane-receipt.json").read_bytes())
                selected = next(item for item in receipt["evidence"]
                                if item["kind"] == "firebase-runtime-evidence")
                selected["kind"] = "untrusted-observation"
                (self.f.receipt_root / "lane-receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n")
                self.archive()
                self.artifact["digest"] = sha256_bytes(self.raw)
            with self.subTest(case=case), self.assertRaisesRegex(ValueError, failures[case]):
                self.call()
            self.assertFalse(self.output.exists())
        self.artifact, self.raw = baseline_artifact, baseline_raw

    def test_changed_plan_after_locator_stops_before_download(self):
        raw = self.plan_path.read_bytes()
        locator = {"artifact_id": 701, "artifact_sha256": self.artifact["digest"]}

        def mutate(*args, **kwargs):
            self.plan_path.write_bytes(b"changed\n")
            return locator

        with patch.object(capture.upload_locator, "locate_android_validation_upload", side_effect=mutate), \
                patch("reuse.api_request") as request, self.assertRaisesRegex(ValueError, "plan"):
            capture.capture_android_evidence(
                self.plan_path, self.root, self.output,
                trusted_workflow_sha=self.workflow_pin,
                trusted_android_workflow_sha=self.android_pin,
                environ=self.environment, token="synthetic-token")
        request.assert_not_called()
        self.plan_path.write_bytes(raw)
        self.assertFalse(self.output.exists())

    def test_lane_check_isolates_bytecode_and_rejects_created_namespace(self):
        environments = []

        def process(_command, **keywords):
            environments.append(keywords["env"])
            prefix = Path(keywords["env"]["PYTHONPYCACHEPREFIX"])
            self.assertFalse(prefix.exists())
            prefix.mkdir()
            return subprocess.CompletedProcess([], 0)

        with patch.object(capture.subprocess, "run", side_effect=process), \
                self.assertRaisesRegex(ValueError, "isolated bytecode namespace"):
            capture._check_lane(self.plan_path, self.f.receipt_root, self.plan)
        self.assertEqual(1, len(environments))
        self.assertEqual("1", environments[0]["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual("1", environments[0]["PYTHONNOUSERSITE"])
        self.assertEqual("1", environments[0]["PYTHONSAFEPATH"])
        self.assertEqual(str(Path(capture.__file__).resolve().parent), environments[0]["PYTHONPATH"])
        self.assertEqual(
            {"PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONSAFEPATH", "PYTHONPYCACHEPREFIX", "PYTHONPATH"},
            set(environments[0]),
        )
        self.assertFalse(self.output.exists())

    def test_late_original_plan_inventory_environment_and_secret_mutations_never_publish(self):
        check = capture._check_lane
        plan_bytes = self.plan_path.read_bytes()
        inventory = self.plan_path.parent / "inventories/android/production-inputs.git-tree"
        inventory_bytes = inventory.read_bytes()
        failures = {"original": "original upload or retained capture changed",
                    "plan": "plan or current producer changed",
                    "inventory": "plan or current producer changed",
                    "environment": "plan or current producer changed",
                    "secret": "signing-secret context"}
        for case in failures:
            self.plan_path.write_bytes(plan_bytes)
            inventory.write_bytes(inventory_bytes)
            self.environment["GITHUB_RUN_ATTEMPT"] = "2"

            def mutate(plan, lane, value):
                result = check(plan, lane, value)
                if case == "original":
                    (lane / next(iter(capture._FIREBASE_FILES))).write_bytes(b"late")
                elif case == "plan":
                    self.plan_path.write_bytes(b"late\n")
                elif case == "inventory":
                    inventory.write_bytes(b"late\n")
                elif case == "environment":
                    self.environment["GITHUB_RUN_ATTEMPT"] = "3"
                else:
                    self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
                return result

            try:
                with self.subTest(case=case), patch.object(capture, "_check_lane", side_effect=mutate), \
                        self.assertRaisesRegex(ValueError, failures[case]):
                    self.call()
                self.assertFalse(self.output.exists())
            finally:
                self.environment.pop("CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY", None)

    def test_secret_stale_and_overlapping_outputs_reject_before_locator(self):
        arguments = dict(
            trusted_workflow_sha=self.workflow_pin,
            trusted_android_workflow_sha=self.android_pin,
            environ=self.environment, token="synthetic-token")
        for selected in (self.environment, os.environ):
            selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
            try:
                with patch.object(capture.upload_locator, "locate_android_validation_upload") as locate, \
                        self.assertRaisesRegex(ValueError, "signing-secret context"):
                    capture.capture_android_evidence(
                        self.plan_path, self.root, self.output, **arguments)
                locate.assert_not_called()
            finally:
                del selected["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]
        self.output.mkdir()
        with patch.object(capture.upload_locator, "locate_android_validation_upload") as locate, \
                self.assertRaisesRegex(ValueError, "destination must not exist"):
            capture.capture_android_evidence(
                self.plan_path, self.root, self.output, **arguments)
        locate.assert_not_called()
        self.output.rmdir()
        with patch.object(capture.upload_locator, "locate_android_validation_upload") as locate, \
                self.assertRaisesRegex(ValueError, "overlaps"):
            capture.capture_android_evidence(
                self.plan_path, self.root, self.root / "nested-output",
                **arguments)
        locate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
