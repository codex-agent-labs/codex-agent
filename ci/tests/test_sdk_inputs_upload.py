"""SDK upload transport over synthetic HTTP, not product/signature admission.

Reuse only the existing transport fixture setup/helpers, never its test methods.
Plan replay and HTTP are substituted; observation, archive and publication gates
are real. Deliberately non-product bytes demonstrate the content-gate boundary.
"""

from copy import deepcopy
import io
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch
import zipfile

from ci.tests import test_runtime_aggregate_upload as fixture
from products.inventory import canonical_json_bytes, regular_file_inventory, sha256_bytes


capture = fixture.capture
JOB = "product-validation / sdk-inputs"


class SdkInputsUploadTest(unittest.TestCase):
    archive = fixture.RuntimeAggregateUploadTest.archive
    api = fixture.RuntimeAggregateUploadTest.api

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = JOB
        self.artifact["name"] = f"codex-agent-sdk-inputs-{self.producer['tree']}-attempt-2"
        self.source("released-default")
        self.original_plan = self.plan_path.read_bytes()

    def source(self, source):
        self.expected_source = source
        self.files = {"sdk-inputs/synthetic-input.json": b"not authenticated SDK product content\n"}
        if source == "released-default":
            self.files.update({
                "runtime-original/original-receipt.json": b"original opaque transport bytes\n",
                "runtime-original/empty-diagnostics.log": b"",
                "current-contract/original-receipt.json": b"current opaque transport bytes\n",
                "selection.json": canonical_json_bytes({"source": source}),
                "transport.json": canonical_json_bytes({"consumer": {"kind": "ci", "producer": self.producer}}),
            })
        else:
            self.files.update({
                "runtime-capture/plan/impact-plan.json": self.plan_path.read_bytes(),
                "runtime-capture/empty-diagnostics.log": b"",
            })
        self.archive()

    def call(self, **changes):
        with patch.object(capture, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return capture.capture_sdk_inputs_upload(self.plan_path, self.output, **{
                "artifact_id": 701, "artifact_sha256": self.artifact["digest"],
                "trusted_workflow_sha": self.pin, "expected_source": self.expected_source,
                "repository_root": self.root,
                "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})

    def test_both_exact_layouts_preserve_original_archive_and_empty_diagnostics(self):
        for source in ("released-default", "current-runtime"):
            with self.subTest(source=source):
                self.source(source)
                self.output = self.work / source
                if source == "current-runtime":
                    # Other jobs may remain live; the fixed upload owner must
                    # already have its exact successful completed attempt.
                    self.run.update(status="in_progress", conclusion=None)
                result = self.call()
                self.assertEqual(self.producer, result["captureProducer"])
                self.assertEqual(source, result["sdkRuntimeSource"])
                self.assertEqual(self.artifact, result["artifact"])
                self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
                self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
                self.assertEqual(result, json.loads((self.output / "capture-transport.json").read_bytes()))
                self.assertEqual({"original", "transport.zip", "plan", "capture-transport.json"},
                                 {path.name for path in self.output.iterdir()})
                for name, raw in self.files.items():
                    self.assertEqual(raw, (self.output / "original" / name).read_bytes())
                self.assertEqual(sorted(self.files), [row["relativePath"] for row in
                    regular_file_inventory(self.output / "original", allow_empty=True)])
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())

    def test_exact_observed_run_job_attempt_pin_and_upload_identity_required(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        cases = ("run", "attempt", "run-status", "job", "job-status", "job-run", "job-head",
                 "duplicate-job", "missing-job", "pin", "commit-tree", "parents", "artifact-run",
                 "artifact-head", "name", "unqualified-name", "digest", "expired", "before", "after")
        for case in cases:
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "run": self.run["id"] = 72
            elif case == "attempt": self.run["run_attempt"] = 1
            elif case == "run-status": self.run["status"] = "queued"
            elif case == "job": self.jobs[0]["name"] = "product-validation / runtime-aggregate-attestation"
            elif case == "job-status": self.jobs[0]["conclusion"] = "failure"
            elif case == "job-run": self.jobs[0]["run_id"] = 72
            elif case == "job-head": self.jobs[0]["head_sha"] = "e" * 40
            elif case == "duplicate-job": self.jobs.append(deepcopy(self.jobs[0]))
            elif case == "missing-job": self.jobs.clear()
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "commit-tree": self.commit["tree"]["sha"] = "e" * 40
            elif case == "parents": self.commit["parents"].reverse()
            elif case == "artifact-run": self.artifact["workflow_run"]["id"] = 72
            elif case == "artifact-head": self.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif case == "name": self.artifact["name"] = self.artifact["name"].replace("attempt-2", "attempt-1")
            elif case == "unqualified-name": self.artifact["name"] = self.artifact["name"].removesuffix("-attempt-2")
            elif case == "digest": self.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "expired": self.artifact["expired"] = True
            elif case == "before": self.artifact["created_at"] = "2026-09-11T09:15:00Z"
            else: self.artifact["created_at"] = "2026-09-11T10:31:00Z"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())

    def test_wrong_source_layout_and_observed_consumer_reject(self):
        for case in ("wrong-layout", "extra-root", "missing-root", "directory-is-file", "wrong-selection",
                     "selection-type", "consumer-type", "wrong-producer", "current-plan"):
            self.source("current-runtime" if case == "current-plan" else "released-default")
            changes = {}
            if case == "wrong-layout": changes["expected_source"] = "current-runtime"
            elif case == "extra-root": self.files["unselected/file"] = b"extra"
            elif case == "missing-root": del self.files["current-contract/original-receipt.json"]
            elif case == "directory-is-file":
                del self.files["current-contract/original-receipt.json"]
                self.files["current-contract"] = b"not a directory"
            elif case == "wrong-selection": self.files["selection.json"] = canonical_json_bytes({"source": "current-runtime"})
            elif case == "selection-type": self.files["selection.json"] = b"[]\n"
            elif case == "consumer-type": self.files["transport.json"] = canonical_json_bytes({"consumer": []})
            elif case == "wrong-producer":
                self.files["transport.json"] = canonical_json_bytes({"consumer": {
                    "producer": {**self.producer, "runAttempt": 1}}})
            else: self.files["runtime-capture/plan/impact-plan.json"] = canonical_json_bytes({**self.plan, "pullRequest": 32})
            self.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call(**changes)
            self.assertFalse(self.output.exists())

    def test_archive_escape_symlink_duplicate_and_tamper_reject(self):
        for case in ("escape", "absolute", "symlink", "duplicate", "tamper"):
            self.source("released-default")
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, raw in self.files.items():
                    archive.writestr(name, raw)
                if case in ("escape", "absolute"):
                    archive.writestr("../escaped" if case == "escape" else "/escaped", b"unsafe")
                elif case == "symlink":
                    link = zipfile.ZipInfo("sdk-inputs/link")
                    link.create_system = 3
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(link, "../../escaped")
                elif case == "duplicate":
                    with self.assertWarns(UserWarning):
                        archive.writestr("selection.json", self.files["selection.json"])
            self.raw = output.getvalue()
            self.artifact.update(digest=sha256_bytes(self.raw), size_in_bytes=len(self.raw))
            if case == "tamper": self.raw += b"changed download bytes"
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())
            self.assertFalse((self.work / "escaped").exists())

    def test_original_plan_and_privately_extracted_input_rechecks_prevent_publication(self):
        extract = capture.safe_extract
        for case in ("source-plan", "captured-plan", "extracted-input", "archive"):
            def mutate_after_real_extract(archive, destination, *args, **kwargs):
                result = extract(archive, destination, *args, **kwargs)
                path = {"source-plan": self.plan_path,
                        "captured-plan": Path(destination).parent / "plan/impact-plan.json",
                        "extracted-input": Path(destination) / "sdk-inputs/synthetic-input.json",
                        "archive": Path(archive)}[case]
                path.write_bytes(path.read_bytes() + b"changed after capture\n")
                return result
            try:
                with self.subTest(case=case), patch.object(capture, "safe_extract", side_effect=mutate_after_real_extract), \
                        self.assertRaisesRegex(ValueError, "changed before capture publication"):
                    self.call()
                self.assertFalse(self.output.exists())
            finally:
                self.plan_path.write_bytes(self.original_plan)

    def test_invalid_authority_and_output_overlap_reject_before_http(self):
        cases = ({"expected_source": "unknown"}, {"expected_source": []}, {"token": None}, {"token": ""},
                 {"artifact_id": True}, {"artifact_id": 0}, {"artifact_sha256": "not-a-digest"})
        for arguments in cases:
            with self.subTest(arguments=arguments), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**arguments)
            observe.assert_not_called()
            self.assertFalse(self.output.exists())
        self.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "authorized"):
            self.call()
        observe.assert_not_called()
        self.plan["remoteBuildAuthorized"] = True
        linked = self.work / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        for destination in (self.root, self.root / "nested", linked / "nested", self.plan_path):
            self.output = destination
            before = regular_file_inventory(self.root)
            with self.subTest(destination=destination), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call()
            observe.assert_not_called()
            self.assertEqual(before, regular_file_inventory(self.root))

    def test_existing_output_is_never_overwritten(self):
        self.call()
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaisesRegex(ValueError, "must not exist"):
            self.call()
        observe.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))


if __name__ == "__main__":
    unittest.main()
