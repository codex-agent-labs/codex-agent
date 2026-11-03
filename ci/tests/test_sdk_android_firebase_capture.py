"""Protected Firebase intermediate transport tests; no semantic admission."""

from copy import deepcopy
import io
import json
import os
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch
import zipfile

from ci import sdk_android_firebase_capture as capture
from ci.tests import test_sdk_android_evidence_capture as final_fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes


class AndroidFirebaseCaptureTest(unittest.TestCase):
    def setUp(self):
        self.final = final_fixture.AndroidEvidenceCaptureTest(methodName="runTest")
        self.addCleanup(self.final.doCleanups)
        self.final.setUp()
        self.addCleanup(self.final.tearDown)
        self.final.call()
        self.root = self.final.root
        self.plan_path = self.final.plan_path
        self.final_capture = self.final.output
        # A rerun may attach/upload in attempt 2 while retaining the original
        # passing Android lane receipt from attempt 1. Keep those producers
        # distinct in every positive transport fixture.
        final_receipt_path = self.final_capture / "original/lane-receipt.json"
        final_receipt = json.loads(final_receipt_path.read_bytes())
        final_receipt["runAttempt"] = 1
        final_receipt_path.write_bytes(canonical_json_bytes(final_receipt))
        final_stream = io.BytesIO()
        final_files = sorted(path for path in (self.final_capture / "original").rglob("*")
                             if path.is_file())
        with zipfile.ZipFile(final_stream, "w") as archive:
            for path in reversed(final_files):
                archive.writestr(
                    path.relative_to(self.final_capture / "original").as_posix(),
                    path.read_bytes(),
                )
        final_archive = final_stream.getvalue()
        (self.final_capture / "original-upload.zip").write_bytes(final_archive)
        final_transport_path = self.final_capture / "capture-transport.json"
        final_transport = json.loads(final_transport_path.read_bytes())
        final_transport["artifact"]["digest"] = sha256_bytes(final_archive)
        final_transport["locator"]["artifact_sha256"] = sha256_bytes(final_archive)
        final_transport["laneReceiptSha256"] = sha256_bytes(final_receipt_path.read_bytes())
        final_transport_path.write_bytes(canonical_json_bytes(final_transport))
        self.environment = self.final.environment
        self.workflow_pin = self.final.workflow_pin
        self.android_pin = self.final.android_pin
        self.source_commit = "8" * 40
        self.source_tree = "9" * 40
        temporary = tempfile.TemporaryDirectory(prefix="android-firebase-capture-test-")
        self.addCleanup(temporary.cleanup)
        self.output = Path(temporary.name).resolve() / "capture"
        self.original = Path(temporary.name).resolve() / "firebase-original"
        (self.original / "results/nested").mkdir(parents=True)
        final_evidence = self.final_capture / "original/payload/external/android-runtime-evidence"
        (self.original / "matrix.json").write_bytes(
            (final_evidence / "firebase-test-matrix.json").read_bytes())
        (self.original / "results/nested/result.xml").write_bytes(
            (final_evidence / "RuntimeBootstrapDeviceTest.xml").read_bytes())
        final_receipt = json.loads((self.final_capture / "original/lane-receipt.json").read_bytes())
        (self.original / "lane-receipt.json").write_bytes(canonical_json_bytes(final_receipt))
        bound = {
            "application.apk": (final_evidence / "android-runtime-evidence-debug.apk").read_bytes(),
            "lane-receipt.json": (self.original / "lane-receipt.json").read_bytes(),
            "runtime.aar": (final_evidence / "codex-agent-runtime-android-release.aar").read_bytes(),
            "test.apk": (final_evidence / "android-runtime-evidence-debug-androidTest.apk").read_bytes(),
        }
        binding = {
            "schemaVersion": 1, "kind": "firebase-android-input-binding",
            "candidateCommit": self.final.plan["validationCommit"],
            "candidateTree": self.final.plan["validationTree"],
            "trustedSourceCommit": self.source_commit, "trustedSourceTree": self.source_tree,
            "files": [{"relativePath": name, "bytes": len(data), "sha256": sha256_bytes(data)}
                      for name, data in sorted(bound.items())],
        }
        (self.original / "input-binding.json").write_bytes(canonical_json_bytes(binding))
        self.archive()
        self.artifact = {
            "id": 702,
            "name": "codex-agent-ci-android-firebase-" + self.final.plan["validationCommit"],
            "expired": False, "digest": sha256_bytes(self.raw),
            "size_in_bytes": len(self.raw),
            "created_at": "2026-09-11T09:30:00Z",
            "archive_download_url": (
                "https://api.github.com/repos/codex-agent-labs/codex-agent/actions/artifacts/702/zip"),
            "workflow_run": {"id": 101, "head_sha": "f" * 40},
        }
        common = {"run_id": 101, "head_sha": "f" * 40,
                  "status": "completed", "conclusion": "success"}
        self.observation = {"run": {"head_sha": "f" * 40}, "jobs": [{
            **common, "id": 81, "name": capture.upload_locator.FIREBASE_JOB,
            "started_at": "2026-09-11T09:00:00Z", "completed_at": "2026-09-11T10:00:00Z",
        }]}
        self.final_transport = json.loads(
            (self.final_capture / "capture-transport.json").read_bytes())

    def archive(self):
        stream = io.BytesIO()
        files = sorted(path for path in self.original.rglob("*") if path.is_file())
        with zipfile.ZipFile(stream, "w") as archive:
            for path in reversed(files):
                archive.writestr(path.relative_to(self.original).as_posix(), path.read_bytes())
        self.raw = stream.getvalue()

    def call(self, **changes):
        arguments = {
            "trusted_workflow_sha": self.workflow_pin,
            "trusted_android_workflow_sha": self.android_pin,
            "trusted_source_commit": self.source_commit,
            "trusted_source_tree": self.source_tree,
            "environ": self.environment, "token": "synthetic-token",
        }
        arguments.update(changes)
        final_locator = self.final_transport["locator"]
        with patch.object(capture.upload_locator, "locate_android_validation_upload",
                          return_value=final_locator), \
                patch.object(capture.products, "_observe_ci_producer_jobs",
                             return_value=(self.observation,)), \
                patch.object(capture.products, "paginated_items",
                             return_value=[deepcopy(self.artifact)]), \
                patch.object(capture.products, "api_json", return_value=deepcopy(self.artifact)), \
                patch.object(capture, "download_artifact", return_value=self.raw):
            return capture.capture_android_firebase_evidence(
                self.plan_path, self.root, self.final_capture, self.output, **arguments)

    def test_exact_unsorted_zip_empty_streams_and_final_linkage_are_retained_without_admission(self):
        final_before = regular_file_inventory(self.final_capture, allow_empty=True)
        result = self.call()
        self.assertEqual(self.raw, (self.output / "original-upload.zip").read_bytes())
        self.assertEqual(b"", (self.output / "original/results/nested/result.xml").read_bytes())
        self.assertEqual(regular_file_inventory(self.original, allow_empty=True),
                         regular_file_inventory(self.output / "original", allow_empty=True))
        self.assertEqual((self.final_capture / "capture-transport.json").read_bytes(),
                         (self.output / "linked-final/capture-transport.json").read_bytes())
        self.assertEqual((self.final_capture / "original/lane-receipt.json").read_bytes(),
                         (self.output / "linked-final/lane-receipt.json").read_bytes())
        self.assertEqual(final_before, regular_file_inventory(self.final_capture, allow_empty=True))
        self.assertEqual("android-firebase-transport", result["kind"])
        self.assertEqual(2, result["captureProducer"]["runAttempt"])
        self.assertEqual(1, json.loads(
            (self.output / "original/lane-receipt.json").read_bytes())["runAttempt"])
        self.assertNotIn("admission", canonical_json_bytes(result).decode())
        self.assertNotIn("trustedSourceCommit", canonical_json_bytes(result).decode())

    def test_final_copy_rejects_late_prepared_transport_change(self):
        publish = capture.publish_regular_tree

        def mutate(source, destination, **kwargs):
            (source / "capture-transport.json").write_bytes(b"late\n")
            return publish(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "pinned inventory"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_prepared_extra_before_inventory_never_becomes_authority(self):
        write = capture.write_canonical_json

        def mutate(path, value):
            write(path, value)
            (path.parent / "unexpected.txt").write_bytes(b"untrusted")

        with patch.object(capture, "write_canonical_json", side_effect=mutate), \
                self.assertRaisesRegex(ValueError, "before publication"):
            self.call()
        self.assertFalse(self.output.exists())

    def test_original_commit_is_replayed_after_checkout_head_advances(self):
        revision = self.final.plan["validationCommit"]
        subprocess.run(["git", "commit", "--allow-empty", "-qm", "later consumer"], cwd=self.root, check=True)
        result = self.call(expected_revision=revision)
        self.assertEqual(revision, result["captureProducer"]["commit"])

    def test_binding_source_receipt_and_old_layout_reject(self):
        baseline = {path.relative_to(self.original).as_posix(): path.read_bytes()
                    for path in self.original.rglob("*") if path.is_file()}
        for case in ("source", "tree", "candidate", "digest", "noncanonical",
                     "receipt", "missing-binding", "extra", "no-results"):
            for path in sorted((path for path in self.original.rglob("*") if path.is_file()), reverse=True):
                path.unlink()
            for name, raw in baseline.items():
                path = self.original / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            if case in {"source", "tree", "candidate", "digest"}:
                binding = json.loads((self.original / "input-binding.json").read_bytes())
                if case == "digest":
                    binding["files"][0]["sha256"] = "not-a-digest"
                else:
                    field = {"source": "trustedSourceCommit", "tree": "trustedSourceTree",
                             "candidate": "candidateCommit"}[case]
                    binding[field] = "f" * 40
                (self.original / "input-binding.json").write_bytes(canonical_json_bytes(binding))
            elif case == "noncanonical":
                binding = self.original / "input-binding.json"
                binding.write_bytes(b" " + binding.read_bytes())
            elif case == "receipt":
                (self.original / "lane-receipt.json").write_bytes(b"changed\n")
            elif case == "missing-binding":
                (self.original / "input-binding.json").unlink()
            elif case == "extra":
                (self.original / "extra.txt").write_bytes(b"extra")
            else:
                (self.original / "results/nested/result.xml").unlink()
            self.archive()
            self.artifact["digest"] = sha256_bytes(self.raw)
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_job_listing_detail_digest_window_and_final_locator_are_exact(self):
        baseline = deepcopy((self.artifact, self.observation, self.final_transport))
        for case in ("missing", "ambiguous", "detail", "run", "head", "url",
                     "window", "final", "missing-size", "oversize", "wrong-size",
                     "detail-size"):
            self.artifact, self.observation, self.final_transport = deepcopy(baseline)
            listings = [deepcopy(self.artifact)]
            detail = deepcopy(self.artifact)
            final_locator = self.final_transport["locator"]
            if case == "missing": listings = []
            elif case == "ambiguous": listings.append(deepcopy(self.artifact))
            elif case == "detail": detail["digest"] = "sha256:" + "f" * 64
            elif case == "run": detail["workflow_run"]["id"] = 102
            elif case == "head": detail["workflow_run"]["head_sha"] = "e" * 40
            elif case == "url": detail["archive_download_url"] = "https://elsewhere.invalid/zip"
            elif case == "window":
                detail["created_at"] = "2026-09-11T10:30:00Z"
                listings[0]["created_at"] = detail["created_at"]
            elif case == "missing-size":
                detail.pop("size_in_bytes")
                listings[0].pop("size_in_bytes")
            elif case == "oversize":
                detail["size_in_bytes"] = capture.products._CATALOG_LIMIT + 1
                listings[0]["size_in_bytes"] = detail["size_in_bytes"]
            elif case == "wrong-size":
                detail["size_in_bytes"] += 1
                listings[0]["size_in_bytes"] += 1
            elif case == "detail-size":
                detail["size_in_bytes"] += 1
            else: final_locator = {**final_locator, "artifact_id": final_locator["artifact_id"] + 1}
            with self.subTest(case=case), patch.object(
                    capture.upload_locator, "locate_android_validation_upload", return_value=final_locator), \
                    patch.object(capture.products, "_observe_ci_producer_jobs",
                                 return_value=(self.observation,)), \
                    patch.object(capture.products, "paginated_items", return_value=listings), \
                    patch.object(capture.products, "api_json", return_value=detail), \
                    patch.object(capture, "download_artifact", return_value=self.raw), \
                    self.assertRaises(ValueError):
                capture.capture_android_firebase_evidence(
                    self.plan_path, self.root, self.final_capture, self.output,
                    trusted_workflow_sha=self.workflow_pin,
                    trusted_android_workflow_sha=self.android_pin,
                    trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
                    environ=self.environment, token="synthetic-token")
            self.assertFalse(self.output.exists())

    def test_final_capture_mutation_secret_stale_and_overlap_never_publish(self):
        transport = self.final_capture / "capture-transport.json"
        raw = transport.read_bytes()

        def mutate(*args, **kwargs):
            transport.write_bytes(b"changed\n")
            return (self.observation,)

        try:
            with patch.object(capture.products, "_observe_ci_producer_jobs", side_effect=mutate), \
                    patch.object(capture.upload_locator, "locate_android_validation_upload",
                                 return_value=self.final_transport["locator"]), \
                    self.assertRaisesRegex(ValueError, "final Android capture changed"):
                capture.capture_android_firebase_evidence(
                    self.plan_path, self.root, self.final_capture, self.output,
                    trusted_workflow_sha=self.workflow_pin,
                    trusted_android_workflow_sha=self.android_pin,
                    trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
                    environ=self.environment, token="synthetic-token")
        finally:
            transport.write_bytes(raw)
        self.assertFalse(self.output.exists())

        with patch.object(capture.upload_locator, "locate_android_validation_upload") as locate, \
                self.assertRaisesRegex(ValueError, "caller-pinned source"):
            capture.capture_android_firebase_evidence(
                self.plan_path, self.root, self.final_capture, self.output,
                trusted_workflow_sha=self.workflow_pin,
                trusted_android_workflow_sha=self.android_pin,
                trusted_source_commit="main", trusted_source_tree=self.source_tree,
                environ=self.environment, token="synthetic-token")
        locate.assert_not_called()

        self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"] = ""
        try:
            with patch.object(capture.upload_locator, "locate_android_validation_upload") as locate, \
                    self.assertRaisesRegex(ValueError, "signing-secret context"):
                capture.capture_android_firebase_evidence(
                    self.plan_path, self.root, self.final_capture, self.output,
                    trusted_workflow_sha=self.workflow_pin,
                    trusted_android_workflow_sha=self.android_pin,
                    trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
                    environ=self.environment, token="synthetic-token")
            locate.assert_not_called()
        finally:
            del self.environment["CODEX_AGENT_PRODUCT_ED25519_PRIVATE_KEY"]
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "destination must not exist"):
            capture.capture_android_firebase_evidence(
                self.plan_path, self.root, self.final_capture, self.output,
                trusted_workflow_sha=self.workflow_pin,
                trusted_android_workflow_sha=self.android_pin,
                trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
                environ=self.environment, token="synthetic-token")
        self.output.rmdir()
        with self.assertRaisesRegex(ValueError, "overlaps"):
            capture.capture_android_firebase_evidence(
                self.plan_path, self.root, self.final_capture, self.final_capture / "nested",
                trusted_workflow_sha=self.workflow_pin,
                trusted_android_workflow_sha=self.android_pin,
                trusted_source_commit=self.source_commit, trusted_source_tree=self.source_tree,
                environ=self.environment, token="synthetic-token")

    def test_preentry_final_original_receipt_and_payload_must_match_official_zip(self):
        receipt = self.final_capture / "original/lane-receipt.json"
        payload = next(path for path in (self.final_capture / "original/payload").rglob("*")
                       if path.is_file())
        transport = self.final_capture / "capture-transport.json"
        receipt_bytes = receipt.read_bytes()
        payload_bytes = payload.read_bytes()
        transport_bytes = transport.read_bytes()
        for case in ("receipt", "payload"):
            receipt.write_bytes(receipt_bytes)
            payload.write_bytes(payload_bytes)
            transport.write_bytes(transport_bytes)
            if case == "receipt":
                receipt.write_bytes(receipt_bytes + b"changed\n")
                value = json.loads(transport_bytes)
                value["laneReceiptSha256"] = sha256_bytes(receipt.read_bytes())
                transport.write_bytes(canonical_json_bytes(value))
            else:
                payload.write_bytes(payload_bytes + b"changed\n")
            with self.subTest(case=case), patch.object(
                    capture.upload_locator, "locate_android_validation_upload") as locate, \
                    self.assertRaisesRegex(ValueError, "exact official ZIP"):
                capture.capture_android_firebase_evidence(
                    self.plan_path, self.root, self.final_capture, self.output,
                    trusted_workflow_sha=self.workflow_pin,
                    trusted_android_workflow_sha=self.android_pin,
                    trusted_source_commit=self.source_commit,
                    trusted_source_tree=self.source_tree,
                    environ=self.environment, token="synthetic-token",
                )
            locate.assert_not_called()
            self.assertFalse(self.output.exists())
        receipt.write_bytes(receipt_bytes)
        payload.write_bytes(payload_bytes)
        transport.write_bytes(transport_bytes)


if __name__ == "__main__":
    unittest.main()
