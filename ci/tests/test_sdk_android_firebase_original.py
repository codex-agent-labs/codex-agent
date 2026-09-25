"""Official nested Android artifact composition; all network is mocked."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ci import sdk_android_firebase_original as original
from ci.products.inventory import load_canonical_json_bytes, sha256_bytes, write_canonical_json


class OriginalAndroidFirebaseValidationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="android-firebase-original-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.plan = self.root / "impact-plan.json"; self.plan.write_bytes(b"caller plan")
        self.receipt = self.root / "validation.json"; self.receipt.write_bytes(b"receipt")
        self.producer = {
            "repository": "codex-agent-labs/codex-agent",
            "workflowPath": ".github/workflows/ci.yml",
            "commit": "a" * 40, "tree": "b" * 40,
            "event": "pull_request", "runId": 41, "runAttempt": 8,
            "pullRequest": 7,
        }
        self.original = self.root / "held-original"
        self.final = self.original / "originals/final"
        self.protected = self.original / "originals/protected"
        (self.final / "plan/inventories/android").mkdir(parents=True)
        (self.final / "plan/impact-plan.json").write_bytes(b"historical plan")
        (self.final / "plan/inventories/android/production-inputs.git-tree").write_bytes(b"inventory")
        write_canonical_json(self.final / "capture-transport.json", {
            "schemaVersion": 1, "kind": "android-evidence-transport",
            "locator": {"artifact_id": 701, "artifact_sha256": "sha256:" + "7" * 64},
            "captureProducer": self.producer,
            "laneReceiptSha256": "sha256:" + "8" * 64,
        })
        (self.final / "original/lane-receipt.json").parent.mkdir(parents=True)
        (self.final / "original/lane-receipt.json").write_bytes(b"lane receipt\n")
        (self.final / "original-upload.zip").write_bytes(b"final zip")
        (self.protected / "plan/inventories/android").mkdir(parents=True)
        (self.protected / "plan/impact-plan.json").write_bytes(b"historical plan")
        (self.protected / "plan/inventories/android/production-inputs.git-tree").write_bytes(b"inventory")
        write_canonical_json(self.protected / "capture-transport.json", {
            "schemaVersion": 1, "kind": "android-firebase-transport",
            "locator": {"artifact_id": 702, "artifact_sha256": "sha256:" + "9" * 64},
            "captureProducer": self.producer,
            "laneReceiptSha256": "sha256:" + "3" * 64,
            "inputBindingSha256": "sha256:" + "4" * 64,
        })
        (self.protected / "original-upload.zip").write_bytes(b"protected zip")
        (self.protected / "original/input-binding.json").parent.mkdir(parents=True)
        (self.protected / "original/input-binding.json").write_bytes(b"binding\n")
        linked = self.protected / "linked-final"; linked.mkdir()
        (linked / "capture-transport.json").write_bytes(
            (self.final / "capture-transport.json").read_bytes())
        (linked / "lane-receipt.json").write_bytes(
            (self.final / "original/lane-receipt.json").read_bytes())
        protected_transport = load_canonical_json_bytes(
            (self.protected / "capture-transport.json").read_bytes())
        protected_transport["linkedFinalCaptureSha256"] = sha256_bytes(
            (linked / "capture-transport.json").read_bytes())
        protected_transport["linkedFinalLaneReceiptSha256"] = sha256_bytes(
            (linked / "lane-receipt.json").read_bytes())
        write_canonical_json(self.protected / "capture-transport.json", protected_transport)
        self.environment = {"GITHUB_RUN_ID": "999", "GITHUB_RUN_ATTEMPT": "9"}
        self.events = []
        self.reader_exit_failure = None
        self.arguments = dict(
            validation_artifact_id=901,
            validation_artifact_sha256="sha256:" + "1" * 64,
            trusted_workflow_sha="c" * 40,
            trusted_android_workflow_sha="d" * 40,
            expected_original_run_id=41, expected_original_run_attempt=8,
            package_stage=self.root, package_receipt=self.receipt,
            binary_stage=self.root, binary_receipt=self.receipt,
            compatibility_request=self.receipt, binary_contract_evidence={},
            trusted_source_commit="e" * 40, trusted_source_tree="f" * 40,
            tooling_evidence=self.root, tooling_public_key=self.receipt,
            java_executable=self.receipt, apkanalyzer_executable=self.receipt,
            policy_revision="2" * 40, required_trust_domain="development",
            repository_root=self.root, environ=self.environment, token="token",
        )

    @contextmanager
    def reader(self, plan, receipt, **kwargs):
        self.events.append("reader-enter")
        self.assertEqual(self.plan, plan)
        self.assertEqual(self.receipt, receipt)
        self.assertEqual(901, kwargs["artifact_id"])
        self.assertNotIn("trusted_android_workflow_sha", kwargs)
        if hasattr(self, "expected_route"):
            self.assertEqual(self.expected_route, (
                kwargs["trusted_workflow_path"], kwargs["trusted_job_name"]))
        try:
            yield {"receipt": {"producer": deepcopy(self.producer)},
                   "original": self.original, "stage": self.root}
        finally:
            self.events.append("reader-exit")
            if self.reader_exit_failure is not None:
                raise self.reader_exit_failure

    def capture_final(self, plan, repository, destination, **kwargs):
        self.assertEqual(self.producer["commit"], kwargs["expected_revision"])
        self.events.append("official-final")
        self.assertEqual(self.final / "plan/impact-plan.json", plan)
        self.assertEqual("41", kwargs["environ"]["GITHUB_RUN_ID"])
        self.assertEqual("8", kwargs["environ"]["GITHUB_RUN_ATTEMPT"])
        shutil.copytree(self.final, destination)
        return {"kind": "transport"}

    def capture_protected(self, plan, repository, final, destination, **kwargs):
        self.assertEqual(self.producer["commit"], kwargs["expected_revision"])
        self.events.append("official-protected")
        self.assertEqual("e" * 40, kwargs["trusted_source_commit"])
        self.assertEqual("f" * 40, kwargs["trusted_source_tree"])
        shutil.copytree(self.protected, destination)
        return {"kind": "protected"}

    def context(self, **changes):
        arguments = {**self.arguments, **changes}
        return original.verified_original_android_firebase_validation(
            self.plan, self.receipt, **arguments)

    def call(self, **changes):
        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=self.capture_final), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=self.capture_protected):
            with self.context(**changes) as held:
                self.events.append("caller-use")
                return held

    def test_exact_official_nested_artifacts_are_held_with_full_reader(self):
        value = self.call()
        self.assertEqual(self.producer, value["receipt"]["producer"])
        self.assertEqual(["reader-enter", "official-final", "official-protected",
                          "caller-use", "reader-exit"], self.events)

    def test_nested_validation_route_requires_a_paired_caller_pin(self):
        self.expected_route = (
            ".github/workflows/sdk-android-validation.yml",
            "product-validation / sdk-android-validation-result / sdk-android-validation-android",
        )
        self.call(trusted_workflow_path=self.expected_route[0],
                  trusted_job_name=self.expected_route[1])
        self.events.clear()
        with self.assertRaisesRegex(ValueError, "pinned together"):
            self.call(trusted_workflow_path=self.expected_route[0])
        self.assertNotIn("reader-enter", self.events)

    def test_wrong_run_pin_or_official_nested_bytes_reject(self):
        for changes in ({"expected_original_run_attempt": 7},
                        {"trusted_android_workflow_sha": "main"}):
            self.events.clear()
            with self.subTest(changes=changes), self.assertRaises(ValueError), \
                    patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                    patch.object(original, "capture_android_evidence", side_effect=self.capture_final), \
                    patch.object(original, "capture_android_firebase_evidence", side_effect=self.capture_protected):
                with self.context(**changes):
                    pass
            self.assertNotIn("caller-use", self.events)

        def changed(plan, repository, destination, **kwargs):
            self.capture_final(plan, repository, destination, **kwargs)
            (destination / "original-upload.zip").write_bytes(b"different official zip")
        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=changed), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=self.capture_protected), \
                self.assertRaisesRegex(ValueError, "official artifact"):
            with self.context():
                pass

        def wrong_locator(plan, repository, final, destination, **kwargs):
            self.capture_protected(plan, repository, final, destination, **kwargs)
            path = destination / "capture-transport.json"
            value = load_canonical_json_bytes(path.read_bytes())
            value["locator"]["artifact_id"] += 1
            write_canonical_json(path, value)
        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=self.capture_final), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=wrong_locator), \
                self.assertRaisesRegex(ValueError, "official artifact"):
            with self.context():
                pass

    def test_mutable_artifact_retrieval_metadata_is_not_cross_time_authority(self):
        def current_final(plan, repository, destination, **kwargs):
            self.capture_final(plan, repository, destination, **kwargs)
            path = destination / "capture-transport.json"
            value = load_canonical_json_bytes(path.read_bytes())
            value["artifact"] = {"download_count": 99, "updated_at": "later"}
            write_canonical_json(path, value)

        def current_protected(plan, repository, final, destination, **kwargs):
            self.capture_protected(plan, repository, final, destination, **kwargs)
            path = destination / "capture-transport.json"
            value = load_canonical_json_bytes(path.read_bytes())
            value["artifact"] = {"download_count": 100, "updated_at": "later"}
            write_canonical_json(path, value)
            (destination / "linked-final/capture-transport.json").write_bytes(
                (final / "capture-transport.json").read_bytes())

        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=current_final), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=current_protected):
            with self.context() as held:
                self.assertEqual(self.producer, held["receipt"]["producer"])

    def test_protected_link_mutation_and_reader_exit_failure_reject(self):
        link = self.protected / "linked-final/capture-transport.json"
        raw = link.read_bytes()
        link.write_bytes(b"unlinked\n")
        try:
            with self.assertRaisesRegex(ValueError, "linkage changed"):
                self.call()
        finally:
            link.write_bytes(raw)

        self.events.clear()
        self.reader_exit_failure = ValueError("full reader exit rejected")
        with self.assertRaisesRegex(ValueError, "full reader exit rejected"):
            self.call()

    def test_retained_protected_link_digest_must_match_official_capture(self):
        path = self.protected / "capture-transport.json"
        value = load_canonical_json_bytes(path.read_bytes())
        value["linkedFinalCaptureSha256"] = "sha256:" + "0" * 64
        write_canonical_json(path, value)

        def official_protected(plan, repository, final, destination, **kwargs):
            self.capture_protected(plan, repository, final, destination, **kwargs)
            path = destination / "capture-transport.json"
            value = load_canonical_json_bytes(path.read_bytes())
            value["linkedFinalCaptureSha256"] = sha256_bytes(
                (destination / "linked-final/capture-transport.json").read_bytes())
            write_canonical_json(path, value)

        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=self.capture_final), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=official_protected), \
                self.assertRaisesRegex(ValueError, "official artifact"):
            with self.context():
                pass

    def test_caller_use_mutation_is_caught_before_reader_exit(self):
        with patch.object(original, "verified_original_android_validation", side_effect=self.reader), \
                patch.object(original, "capture_android_evidence", side_effect=self.capture_final), \
                patch.object(original, "capture_android_firebase_evidence", side_effect=self.capture_protected), \
                self.assertRaisesRegex(ValueError, "official Firebase evidence changed"):
            with self.context():
                (self.protected / "original/input-binding.json").write_bytes(b"changed\n")
        self.assertEqual("reader-exit", self.events[-1])


if __name__ == "__main__":
    unittest.main()
