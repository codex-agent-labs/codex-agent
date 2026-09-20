"""Real official transport parsers over mocked HTTP; no semantic/signing proof."""

from copy import deepcopy
import io
import stat
import unittest
from unittest.mock import patch
import warnings
import zipfile

from ci import sdk_apple_preparation_capture as capture
from ci.tests import test_runtime_aggregate_upload as fixtures
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes


class ApplePreparationCaptureTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RuntimeAggregateUploadTest(methodName="runTest")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.configure("ios-arm64")

    def configure(self, target):
        f = self.fixture
        self.target = target
        f.jobs[0]["name"] = f"product-validation / sdk-apple-signing-prepare-{target}"
        f.artifact["name"] = (f"codex-agent-sdk-apple-signing-preparation-{target}-"
                              f"{f.producer['tree']}-attempt-2")
        # Historical receipt identity deliberately differs from the observed
        # preparation producer. Record semantics belong to the protected reader.
        self.historical = {**f.producer, "commit": "d" * 40, "tree": "e" * 40,
                           "runId": 61, "runAttempt": 1}
        f.files = {"preparation.json": canonical_json_bytes({"producer": self.historical,
            "synthetic": "transport only, not a preparation approval"}),
            "capture/original/shard/phase-receipt.json": b"opaque original receipt\n",
            "capture/original/worker/gradle.log": b""}
        f.archive()

    def call(self, **changes):
        f = self.fixture
        with patch.object(capture.products, "_validate_plan", return_value=f.plan), \
                patch("reuse.api_request", side_effect=f.api):
            return capture.capture_apple_signing_preparation(f.plan_path, f.output, **{
                "target": self.target, "artifact_id": 701, "artifact_sha256": f.artifact["digest"],
                "trusted_workflow_sha": f.pin, "repository_root": f.root,
                "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})

    def test_both_targets_preserve_raw_bytes_and_use_current_preparation_producer(self):
        f = self.fixture
        for target in ("ios-arm64", "ios-simulator-arm64"):
            with self.subTest(target=target):
                self.configure(target)
                f.output = f.work / f"capture-{target}"
                before = f.plan_path.read_bytes()
                result = self.call()
                self.assertEqual(f.producer, result["captureProducer"])
                self.assertNotEqual(self.historical, result["captureProducer"])
                self.assertEqual(target, result["target"])
                self.assertEqual({"original", "original-upload.zip", "capture-transport.json"},
                                 {path.name for path in f.output.iterdir()})
                self.assertEqual(f.raw, (f.output / "original-upload.zip").read_bytes())
                for name, raw in f.files.items():
                    self.assertEqual(raw, (f.output / "original" / name).read_bytes())
                self.assertEqual(before, f.plan_path.read_bytes())
                inventory = regular_file_inventory(f.output, allow_empty=True)
                with self.assertRaisesRegex(ValueError, "must not exist"):
                    self.call()
                self.assertEqual(inventory, regular_file_inventory(f.output, allow_empty=True))

    def test_wrong_observed_producer_run_job_pin_window_and_upload_reject(self):
        f = self.fixture
        baseline = deepcopy((f.run, f.jobs, f.artifact, f.commit))
        for case in ("failed", "job", "run", "attempt", "tree", "pin", "window", "missing-window",
                     "name", "historical-name", "digest", "expired", "artifact-run"):
            f.run, f.jobs, f.artifact, f.commit = deepcopy(baseline)
            if case == "failed": f.jobs[0]["conclusion"] = "failure"
            elif case == "job": f.jobs[0]["name"] += "-other"
            elif case == "run": f.run["id"] = 61
            elif case == "attempt": f.run["run_attempt"] = 1
            elif case == "tree": f.commit["tree"]["sha"] = "e" * 40
            elif case == "pin": f.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "window": f.artifact["created_at"] = "2026-09-11T09:15:00Z"
            elif case == "missing-window": del f.artifact["created_at"]
            elif case == "name": f.artifact["name"] += "-other"
            elif case == "historical-name":
                f.artifact["name"] = f"codex-agent-sdk-apple-signing-preparation-{self.target}-{'e' * 40}-attempt-1"
            elif case == "digest": f.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "expired": f.artifact["expired"] = True
            else: f.artifact["workflow_run"]["id"] = 61
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())

    def test_exact_upload_layout_rejects_missing_extra_or_wrong_kind(self):
        f = self.fixture
        for case in ("missing-record", "missing-capture", "extra", "record-directory", "capture-file"):
            self.configure("ios-arm64")
            if case == "missing-record": del f.files["preparation.json"]
            elif case == "missing-capture": f.files = {"preparation.json": f.files["preparation.json"]}
            elif case == "extra": f.files["release-handoff/extra"] = b"extra"
            elif case == "record-directory":
                f.files["preparation.json/record"] = f.files.pop("preparation.json")
            else:
                f.files = {"preparation.json": f.files["preparation.json"], "capture": b"not a directory"}
            f.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())

    def test_malicious_zip_and_raw_archive_tamper_never_publish(self):
        f = self.fixture
        for case in ("traversal", "absolute", "symlink", "duplicate", "tamper"):
            self.configure("ios-arm64")
            if case in ("traversal", "absolute"):
                f.files["../escape" if case == "traversal" else "/escape"] = b"unsafe"
                f.archive()
            elif case == "tamper":
                f.raw += b"changed after official digest"
            else:
                output = io.BytesIO()
                with warnings.catch_warnings(), zipfile.ZipFile(output, "w") as archive:
                    warnings.simplefilter("ignore", UserWarning)
                    for name, raw in f.files.items():
                        archive.writestr(name, raw)
                    if case == "duplicate": archive.writestr("preparation.json", b"duplicate")
                    else:
                        link = zipfile.ZipInfo("capture/link")
                        link.create_system = 3
                        link.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(link, "../../escape")
                f.raw = output.getvalue()
                f.artifact.update(digest=sha256_bytes(f.raw), size_in_bytes=len(f.raw))
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(f.output.exists())
            self.assertFalse((f.work / "escape").exists())

    def test_invalid_inputs_authorization_and_overlap_fail_before_observation(self):
        f = self.fixture
        for changes in ({"target": "aggregate"}, {"target": "ios"}, {"artifact_id": True},
                        {"artifact_sha256": "bad"}, {"token": ""}):
            with self.subTest(changes=changes), patch.object(capture.products, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()
        for event, authorized in (("workflow_dispatch", True), ("pull_request", False)):
            f.plan.update(event=event, remoteBuildAuthorized=authorized)
            with patch.object(capture.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
        f.plan.update(event="pull_request", remoteBuildAuthorized=True)
        for output in (f.root / "nested-output", f.plan_path, f.work):
            f.output = output
            with patch.object(capture.products, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()

    def test_late_original_or_captured_plan_mutation_prevents_publication(self):
        f = self.fixture
        gate = capture.products._require_artifact_job_window
        original_bytes = f.plan_path.read_bytes()
        for selected in ("original", "private"):
            f.plan_path.write_bytes(original_bytes)
            captured = []
            def validate(path, root):
                captured.append(path)
                return f.plan
            def mutate(*args):
                gate(*args)
                (f.plan_path if selected == "original" else captured[0]).write_bytes(b"changed plan\n")
            with self.subTest(selected=selected), \
                    patch.object(capture.products, "_validate_plan", side_effect=validate), \
                    patch("reuse.api_request", side_effect=f.api), \
                    patch.object(capture.products, "_require_artifact_job_window", side_effect=mutate), \
                    self.assertRaisesRegex(ValueError, "changed before publication"):
                capture.capture_apple_signing_preparation(f.plan_path, f.output, target=self.target,
                    artifact_id=701, artifact_sha256=f.artifact["digest"], trusted_workflow_sha=f.pin,
                    repository_root=f.root, environ={"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                    token="synthetic-token")
            self.assertFalse(f.output.exists())


if __name__ == "__main__":
    unittest.main()
