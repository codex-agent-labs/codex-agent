"""Native preparation transport controls, not SDK/source content admission.

Only plan replay and HTTP are substituted. Observation, ZIP safety and private
publication are real; opaque source/SDK bytes deliberately cannot prove content.
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
from products.receipt import compute_build_key
from products.registry import NATIVE_BINDINGS
from products.restore import PHASE_PLAN_KEYS
from sdk_native_prepare import TASK


capture = fixture.capture
JOB = "product-validation / sdk-native-prepare"


class SdkNativePreparedUploadTest(unittest.TestCase):
    archive = fixture.RuntimeAggregateUploadTest.archive
    api = fixture.RuntimeAggregateUploadTest.api

    def setUp(self):
        fixture.RuntimeAggregateUploadTest.setUp(self)
        self.jobs[0]["name"] = JOB
        self.artifact["name"] = f"codex-agent-sdk-native-prepared-{self.producer['tree']}-attempt-2"
        receipt = {**self.receipt, "product": "sdk", "component": "python", "phase": "package", "target": "desktop"}
        receipt["buildKey"] = compute_build_key(**{name: receipt[name] for name in
                                                  ("product", "component", "phase", "target", "inputs")})
        self.phase = {name: receipt[name] for name in PHASE_PLAN_KEYS}
        self.execution = {"schemaVersion": 1, "producer": self.producer, "buildKey": self.phase["buildKey"],
            "command": ["/synthetic/gradlew", "--offline", TASK], "returnCode": 0,
            "launchError": None, "elapsedNs": 12}
        self.original_plan = self.plan_path.read_bytes()
        self.files = {
            "original-plan/impact-plan.json": self.original_plan,
            "original-plan/phase-plan.json": canonical_json_bytes(self.phase),
            **{f"prepared-sources/{language}/opaque-source": b"synthetic source, not admitted\n"
               for language in NATIVE_BINDINGS},
            "staged-sdks/opaque-sdk": b"synthetic SDK, not admitted\n",
            "diagnostics/gradle.log": b"",
            "diagnostics/execution.json": canonical_json_bytes(self.execution),
        }
        self.archive()

    def call(self, **changes):
        with patch.object(capture, "_validate_plan", return_value=self.plan), \
                patch("reuse.api_request", side_effect=self.api):
            return capture.capture_sdk_native_prepared_upload(self.plan_path, self.output, **{
                "expected_phase_plan": self.phase, "artifact_id": 701,
                "artifact_sha256": self.artifact["digest"], "trusted_workflow_sha": self.pin,
                "repository_root": self.root, "environ": {"GITHUB_RUN_ID": "71", "GITHUB_RUN_ATTEMPT": "2"},
                "token": "synthetic-token", **changes})

    def test_exact_upload_preserves_raw_plans_all_languages_and_empty_log(self):
        result = self.call()
        self.assertEqual(self.producer, result["captureProducer"])
        self.assertEqual(self.artifact, result["artifact"])
        self.assertEqual(self.phase, result["phasePlan"])
        self.assertEqual(self.run, result["observed"][0]["run"])
        self.assertEqual(self.raw, (self.output / "transport.zip").read_bytes())
        self.assertEqual(self.original_plan, (self.output / "plan/impact-plan.json").read_bytes())
        self.assertEqual(result, json.loads((self.output / "capture-transport.json").read_bytes()))
        self.assertEqual(sorted(self.files), [row["relativePath"] for row in
            regular_file_inventory(self.output / "original", allow_empty=True)])
        for name, raw in self.files.items():
            self.assertEqual(raw, (self.output / "original" / name).read_bytes())
        self.assertEqual(self.original_plan, self.plan_path.read_bytes())
        before = regular_file_inventory(self.output, allow_empty=True)
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()
        self.assertEqual(before, regular_file_inventory(self.output, allow_empty=True))

    def test_observed_job_attempt_workflow_digest_and_upload_window_are_exact(self):
        baseline = deepcopy((self.run, self.jobs, self.artifact, self.commit))
        for case in ("job", "job-failure", "job-run", "job-head", "duplicate-job", "attempt", "pin",
                     "artifact-run", "artifact-head", "name", "digest", "before", "after", "tree", "parents"):
            self.run, self.jobs, self.artifact, self.commit = deepcopy(baseline)
            if case == "job": self.jobs[0]["name"] = "product-validation / sdk-inputs"
            elif case == "job-failure": self.jobs[0]["conclusion"] = "failure"
            elif case == "job-run": self.jobs[0]["run_id"] = 72
            elif case == "job-head": self.jobs[0]["head_sha"] = "e" * 40
            elif case == "duplicate-job": self.jobs.append(deepcopy(self.jobs[0]))
            elif case == "attempt": self.run["run_attempt"] = 1
            elif case == "pin": self.run["referenced_workflows"][0]["sha"] = "d" * 40
            elif case == "artifact-run": self.artifact["workflow_run"]["id"] = 72
            elif case == "artifact-head": self.artifact["workflow_run"]["head_sha"] = "e" * 40
            elif case == "name": self.artifact["name"] = self.artifact["name"].replace("attempt-2", "attempt-1")
            elif case == "digest": self.artifact["digest"] = "sha256:" + "d" * 64
            elif case == "before": self.artifact["created_at"] = "2026-09-11T09:59:59Z"
            elif case == "after": self.artifact["created_at"] = "2026-09-11T10:30:01Z"
            elif case == "tree": self.commit["tree"]["sha"] = "e" * 40
            else: self.commit["parents"].reverse()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_exact_layout_plans_and_nonempty_five_language_sources_required(self):
        baseline = deepcopy(self.files)
        for case in ("extra-root", "extra-plan", "extra-diagnostic", "missing-log", "missing-phase", "impact",
                     "phase", "missing-language", "extra-language", "language-file", "empty-source", "empty-sdk"):
            self.files = deepcopy(baseline)
            if case == "extra-root": self.files["other/data"] = b"extra"
            elif case == "extra-plan": self.files["original-plan/extra.json"] = b"{}\n"
            elif case == "extra-diagnostic": self.files["diagnostics/extra"] = b"extra"
            elif case == "missing-log": del self.files["diagnostics/gradle.log"]
            elif case == "missing-phase": del self.files["original-plan/phase-plan.json"]
            elif case == "impact": self.files["original-plan/impact-plan.json"] = canonical_json_bytes({**self.plan, "pullRequest": 32})
            elif case == "phase": self.files["original-plan/phase-plan.json"] = canonical_json_bytes({**self.phase, "buildKey": "sha256:" + "d" * 64})
            elif case == "missing-language": del self.files["prepared-sources/python/opaque-source"]
            elif case == "extra-language": self.files["prepared-sources/javascript/source"] = b"extra"
            elif case == "language-file":
                del self.files["prepared-sources/python/opaque-source"]
                self.files["prepared-sources/python"] = b"not a directory"
            elif case == "empty-source": self.files["prepared-sources/python/opaque-source"] = b""
            else: self.files["staged-sdks/opaque-sdk"] = b""
            self.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_execution_producer_key_fixed_task_and_success_are_bound(self):
        for case in ("extra", "missing", "producer", "key", "task", "duplicate-task", "return-code", "boolean-code",
                     "launch-error", "schema", "elapsed", "command-type"):
            record = deepcopy(self.execution)
            if case == "extra": record["callerSuccess"] = True
            elif case == "missing": del record["elapsedNs"]
            elif case == "producer": record["producer"]["runAttempt"] = 1
            elif case == "key": record["buildKey"] = "sha256:" + "d" * 64
            elif case == "task": record["command"][-1] = "ciProductPhase"
            elif case == "duplicate-task": record["command"].append(TASK)
            elif case == "return-code": record["returnCode"] = 1
            elif case == "boolean-code": record["returnCode"] = False
            elif case == "launch-error": record["launchError"] = "process not launched"
            elif case == "schema": record["schemaVersion"] = 2
            elif case == "elapsed": record["elapsedNs"] = -1
            else: record["command"] = TASK
            self.files["diagnostics/execution.json"] = canonical_json_bytes(record)
            self.archive()
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.call()
            self.assertFalse(self.output.exists())

    def test_malformed_expected_phase_or_missing_authority_rejects_before_http(self):
        phases = [None, [], {**self.phase, "extra": True}, {**self.phase, "component": "javascript"},
                  {**self.phase, "product": "runtime"}, {**self.phase, "phase": "validation"},
                  {**self.phase, "target": "node"}, {**self.phase, "schemaVersion": True},
                  {**self.phase, "buildKey": "bad-key"}]
        for changes in ([{"expected_phase_plan": value} for value in phases] +
                        [{"artifact_id": True}, {"artifact_sha256": "bad"}, {"token": ""}]):
            with self.subTest(changes=changes), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError):
                self.call(**changes)
            observe.assert_not_called()
            self.assertFalse(self.output.exists())
        self.plan["remoteBuildAuthorized"] = False
        with patch.object(capture, "_observe_ci_producer_jobs") as observe, self.assertRaises(ValueError):
            self.call()
        observe.assert_not_called()

    def test_unsafe_archive_or_changed_download_never_publishes(self):
        for case in ("escape", "symlink", "duplicate", "tamper"):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                for name, raw in self.files.items(): archive.writestr(name, raw)
                if case == "escape": archive.writestr("../escape", b"unsafe")
                elif case == "symlink":
                    link = zipfile.ZipInfo("prepared-sources/python/link")
                    link.create_system = 3
                    link.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(link, "../../escape")
                elif case == "duplicate":
                    with self.assertWarns(UserWarning):
                        archive.writestr("diagnostics/gradle.log", b"duplicate")
            self.raw = output.getvalue()
            self.artifact.update(digest=sha256_bytes(self.raw), size_in_bytes=len(self.raw))
            if case == "tamper": self.raw += b"changed"
            with self.subTest(case=case), self.assertRaises(ValueError): self.call()
            self.assertFalse(self.output.exists())
            self.assertFalse((self.work / "escape").exists())

    def test_original_plan_archive_and_private_inputs_rechecked_before_publish(self):
        extract = capture.safe_extract
        original_phase = deepcopy(self.phase)
        for case in ("source-plan", "captured-plan", "source", "archive", "elected-plan"):
            def mutate(archive, destination, *args, **kwargs):
                result = extract(archive, destination, *args, **kwargs)
                if case == "elected-plan":
                    self.phase["inputs"] = {"changed": "after initial capture"}
                    return result
                path = {"source-plan": self.plan_path,
                        "captured-plan": Path(destination).parent / "plan/impact-plan.json",
                        "source": Path(destination) / "prepared-sources/python/opaque-source",
                        "archive": Path(archive)}[case]
                path.write_bytes(path.read_bytes() + b"changed after extraction\n")
                return result
            try:
                with self.subTest(case=case), patch.object(capture, "safe_extract", side_effect=mutate), \
                        self.assertRaises(ValueError): self.call()
                self.assertFalse(self.output.exists())
            finally:
                self.plan_path.write_bytes(self.original_plan)
                self.phase = deepcopy(original_phase)

    def test_late_copy_of_original_source_cannot_publish(self):
        publisher = capture.publish_regular_tree

        def mutate(source, destination, **kwargs):
            original = Path(source) / "original/prepared-sources/python/opaque-source"
            original.write_bytes(original.read_bytes() + b"changed after final check\n")
            return publisher(source, destination, **kwargs)

        with patch.object(capture, "publish_regular_tree", side_effect=mutate), self.assertRaises(ValueError):
            self.call()
        self.assertFalse(self.output.exists())

    def test_output_cannot_overlap_or_alias_original_source(self):
        link = self.work / "linked"
        link.symlink_to(self.root, target_is_directory=True)
        before = regular_file_inventory(self.root)
        for destination in (self.root, self.root / "nested", link / "nested", self.plan_path):
            self.output = destination
            with self.subTest(destination=destination), patch.object(capture, "_observe_ci_producer_jobs") as observe, \
                    self.assertRaises(ValueError): self.call()
            observe.assert_not_called()
            self.assertEqual(before, regular_file_inventory(self.root))


if __name__ == "__main__":
    unittest.main()
